#!/usr/bin/env python3
"""Materialize approved TTRPG cache assets through exact HTTP or S3 bindings.

The operator mutates only the explicitly selected schema-3 cache database. It
is restart-safe: already materialized rows are verified and skipped, while
pending rows are fetched through public TTRPG routes or the approved `kmqdb`
S3 bucket and written in bounded transactions. AWS credentials, when selected,
remain operator inputs and are never written to the cache or deployment host.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
import sqlite3
import stat
import sys
import threading
from email.utils import format_datetime
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


CACHE_SCHEMA_VERSION = 3
ALLOWED_KINDS = frozenset({"cover", "icon", "image"})
EXPECTED_COLUMNS = (
    "kind",
    "asset_key",
    "content_type",
    "bucket",
    "s3_key",
    "body",
    "size",
    "etag",
    "last_modified",
)
MAX_ASSET_BYTES = 64 * 1024 * 1024


class MaterializationError(RuntimeError):
    """The cache or one fetched asset failed exact verification."""


class NoRedirectHandler(urlrequest.HTTPRedirectHandler):
    def redirect_request(
        self,
        _request,
        _file_pointer,
        _code,
        _message,
        _headers,
        _new_url,
    ):
        return None


@dataclass(frozen=True, slots=True)
class AssetRow:
    kind: str
    asset_key: str
    content_type: str
    size: int
    etag: str
    last_modified: str
    bucket: str = ""
    s3_key: str = ""


@dataclass(frozen=True, slots=True)
class FetchedAsset:
    body: bytes
    content_type: str
    etag: str
    last_modified: str


Fetcher = Callable[[str, AssetRow, float], FetchedAsset]


def clean_origin(value: object) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise MaterializationError("asset origin must be an HTTP(S) origin")
    parsed = urlparse.urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise MaterializationError("asset origin must be an HTTP(S) origin")
    return urlparse.urlunsplit(
        (parsed.scheme, parsed.netloc, "", "", "")
    )


def _asset_parts(row: AssetRow) -> tuple[str, ...]:
    if row.kind not in ALLOWED_KINDS:
        raise MaterializationError("cache contains an unsupported asset kind")
    if not row.asset_key or "\x00" in row.asset_key or "\\" in row.asset_key:
        raise MaterializationError("cache contains an invalid asset key")
    parts = tuple(row.asset_key.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise MaterializationError("cache contains an invalid asset key")
    return parts


def asset_url(origin: str, row: AssetRow) -> str:
    encoded = "/".join(
        urlparse.quote(part, safe="") for part in _asset_parts(row)
    )
    if row.kind == "cover":
        if "/" in encoded:
            raise MaterializationError("cover asset key must be one segment")
        path = f"/.api/sources/{encoded}/cover"
    else:
        path = f"/.api/assets/pf2er/.static/{row.kind}s/{encoded}"
    return clean_origin(origin) + path


def fetch_asset(origin: str, row: AssetRow, timeout: float) -> FetchedAsset:
    if type(timeout) not in {int, float} or timeout <= 0 or timeout > 300:
        raise MaterializationError("asset timeout is invalid")
    request = urlrequest.Request(
        asset_url(origin, row),
        headers={"Accept": "image/*", "User-Agent": "kmqdb-ttrpg-cache-materializer/1"},
        method="GET",
    )
    opener = urlrequest.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=float(timeout)) as response:
            content_type = str(response.headers.get_content_type() or "")
            if content_type != row.content_type or not content_type.startswith("image/"):
                raise MaterializationError(
                    f"asset content type changed: {row.kind}/{row.asset_key}"
                )
            response_etag = str(response.headers.get("ETag") or "")
            if row.etag and not response_etag:
                raise MaterializationError(
                    f"asset ETag is missing: {row.kind}/{row.asset_key}"
                )
            raw_length = str(response.headers.get("Content-Length") or "")
            try:
                response_length = int(raw_length) if raw_length else 0
            except ValueError as exc:
                raise MaterializationError(
                    f"asset content length is invalid: {row.kind}/{row.asset_key}"
                ) from exc
            if response_length < 0 or response_length > MAX_ASSET_BYTES:
                raise MaterializationError(
                    f"asset is too large: {row.kind}/{row.asset_key}"
                )
            limit = (response_length or MAX_ASSET_BYTES) + 1
            body = response.read(limit)
            last_modified = str(response.headers.get("Last-Modified") or "")
    except MaterializationError:
        raise
    except (OSError, TimeoutError, urlerror.URLError) as exc:
        raise MaterializationError(
            f"asset fetch failed: {row.kind}/{row.asset_key}"
        ) from exc
    if response_length and len(body) != response_length:
        raise MaterializationError(
            f"asset size changed: {row.kind}/{row.asset_key}"
        )
    if not body or len(body) > MAX_ASSET_BYTES:
        raise MaterializationError(
            f"asset body is empty: {row.kind}/{row.asset_key}"
        )
    return FetchedAsset(
        body=body,
        content_type=content_type,
        etag=response_etag,
        last_modified=last_modified,
    )


def s3_fetcher(
    *,
    region: str,
    timeout: float = 30.0,
    expected_bucket: str = "kmqdb",
) -> Fetcher:
    if type(region) is not str or not region or "\x00" in region:
        raise MaterializationError("S3 region is invalid")
    if type(expected_bucket) is not str or not expected_bucket:
        raise MaterializationError("S3 bucket is invalid")
    if type(timeout) not in {int, float} or timeout <= 0 or timeout > 300:
        raise MaterializationError("asset timeout is invalid")
    client_state: list[tuple[object, type[Exception], type[Exception]]] = []
    client_lock = threading.Lock()

    def selected_client() -> tuple[object, type[Exception], type[Exception]]:
        with client_lock:
            if client_state:
                return client_state[0]
            try:
                import boto3
                from botocore.config import Config
                from botocore.exceptions import BotoCoreError, ClientError
            except ImportError as exc:
                raise MaterializationError(
                    "boto3 is required for S3 materialization"
                ) from exc
            client = boto3.client(
                "s3",
                region_name=region,
                config=Config(
                    connect_timeout=float(timeout),
                    read_timeout=float(timeout),
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
            selected = (client, BotoCoreError, ClientError)
            client_state.append(selected)
            return selected

    def fetch(_origin: str, row: AssetRow, timeout: float) -> FetchedAsset:
        if type(timeout) not in {int, float} or timeout <= 0 or timeout > 300:
            raise MaterializationError("asset timeout is invalid")
        if row.bucket != expected_bucket or not row.s3_key or "\x00" in row.s3_key:
            raise MaterializationError(
                f"asset has an invalid S3 binding: {row.kind}/{row.asset_key}"
            )
        client, boto_core_error, client_error = selected_client()
        try:
            response = client.get_object(Bucket=row.bucket, Key=row.s3_key)
            response_length = int(response.get("ContentLength") or 0)
            content_type = str(response.get("ContentType") or "")
            response_etag = str(response.get("ETag") or "")
            last_modified_value = response.get("LastModified")
            if response_length < 1 or response_length > MAX_ASSET_BYTES:
                raise MaterializationError(
                    f"asset is too large: {row.kind}/{row.asset_key}"
                )
            if content_type != row.content_type or not content_type.startswith("image/"):
                raise MaterializationError(
                    f"asset content type changed: {row.kind}/{row.asset_key}"
                )
            if row.etag and not response_etag:
                raise MaterializationError(
                    f"asset ETag is missing: {row.kind}/{row.asset_key}"
                )
            body = response["Body"].read(response_length + 1)
        except MaterializationError:
            raise
        except (boto_core_error, client_error, KeyError, OSError, ValueError) as exc:
            raise MaterializationError(
                f"S3 asset fetch failed: {row.kind}/{row.asset_key}"
            ) from exc
        if len(body) != response_length:
            raise MaterializationError(
                f"asset size changed: {row.kind}/{row.asset_key}"
            )
        try:
            last_modified = (
                format_datetime(
                    last_modified_value.astimezone(timezone.utc),
                    usegmt=True,
                )
                if last_modified_value is not None
                else ""
            )
        except (AttributeError, ValueError) as exc:
            raise MaterializationError(
                f"S3 asset timestamp is invalid: {row.kind}/{row.asset_key}"
            ) from exc
        return FetchedAsset(
            body=body,
            content_type=content_type,
            etag=response_etag,
            last_modified=last_modified,
        )

    return fetch


def _cache_connection(path: Path) -> sqlite3.Connection:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise MaterializationError("cache database is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise MaterializationError("cache database must be a regular file")
    if any(
        (path.parent / f"{path.name}{suffix}").exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        raise MaterializationError("cache database has active SQLite sidecars")
    try:
        connection = sqlite3.connect(path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
    except sqlite3.Error as exc:
        raise MaterializationError("cache database could not be opened") from exc
    return connection


def _verified_rows(connection: sqlite3.Connection) -> tuple[AssetRow, ...]:
    try:
        if connection.execute("PRAGMA user_version").fetchone()[0] != CACHE_SCHEMA_VERSION:
            raise MaterializationError("cache database schema is unsupported")
        columns = tuple(
            row[1]
            for row in connection.execute("PRAGMA table_info(binary_assets)")
        )
        if columns != EXPECTED_COLUMNS:
            raise MaterializationError("cache binary-asset schema is invalid")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise MaterializationError("cache database quick check failed")
        malformed = connection.execute(
            """
            SELECT count(*) FROM binary_assets
            WHERE kind NOT IN ('cover','icon','image')
               OR asset_key = ''
               OR content_type NOT LIKE 'image/%'
               OR size < 0
               OR (body IS NULL AND s3_key = '')
               OR (body IS NOT NULL AND size > 0 AND length(body) != size)
            """
        ).fetchone()[0]
        if malformed:
            raise MaterializationError("cache contains invalid binary assets")
        return tuple(
            AssetRow(
                kind=str(row["kind"]),
                asset_key=str(row["asset_key"]),
                content_type=str(row["content_type"]),
                size=int(row["size"]),
                etag=str(row["etag"] or ""),
                last_modified=str(row["last_modified"] or ""),
                bucket=str(row["bucket"] or ""),
                s3_key=str(row["s3_key"] or ""),
            )
            for row in connection.execute(
                """
                SELECT kind, asset_key, content_type, size, etag, last_modified,
                       bucket, s3_key
                FROM binary_assets
                WHERE body IS NULL
                ORDER BY kind, asset_key
                """
            )
        )
    except sqlite3.Error as exc:
        raise MaterializationError("cache database is invalid") from exc


def verify_materialized_cache(path: str | Path) -> int:
    cache = Path(path)
    connection = _cache_connection(cache)
    try:
        pending = _verified_rows(connection)
        if pending:
            raise MaterializationError(
                f"cache still has {len(pending)} unmaterialized assets"
            )
        return int(
            connection.execute("SELECT count(*) FROM binary_assets").fetchone()[0]
        )
    finally:
        connection.close()


def _bounded_results(
    rows: Iterable[AssetRow],
    *,
    origin: str,
    workers: int,
    timeout: float,
    fetcher: Fetcher,
) -> Iterable[tuple[AssetRow, FetchedAsset]]:
    row_iterator = iter(rows)
    pending: dict[Future[FetchedAsset], AssetRow] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for _ in range(workers * 2):
            try:
                row = next(row_iterator)
            except StopIteration:
                break
            pending[executor.submit(fetcher, origin, row, timeout)] = row
        while pending:
            completed, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in completed:
                row = pending.pop(future)
                yield row, future.result()
                try:
                    replacement = next(row_iterator)
                except StopIteration:
                    continue
                pending[executor.submit(fetcher, origin, replacement, timeout)] = replacement


def materialize_cache_assets(
    path: str | Path,
    *,
    origin: str,
    workers: int = 8,
    timeout: float = 30.0,
    fetcher: Fetcher = fetch_asset,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    if type(workers) is not int or workers < 1 or workers > 32:
        raise MaterializationError("asset worker count is invalid")
    selected_origin = clean_origin(origin)
    cache = Path(path)
    connection = _cache_connection(cache)
    try:
        rows = _verified_rows(connection)
        total = len(rows)
        completed = 0
        for row, fetched in _bounded_results(
            rows,
            origin=selected_origin,
            workers=workers,
            timeout=timeout,
            fetcher=fetcher,
        ):
            if (
                not isinstance(fetched, FetchedAsset)
                or not fetched.body
                or len(fetched.body) > MAX_ASSET_BYTES
                or fetched.content_type != row.content_type
                or (row.size > 0 and len(fetched.body) != row.size)
                or (bool(row.etag) and fetched.etag != row.etag)
            ):
                raise MaterializationError(
                    f"fetched asset is invalid: {row.kind}/{row.asset_key}"
                )
            try:
                with connection:
                    cursor = connection.execute(
                        """
                        UPDATE binary_assets
                        SET body = ?, size = ?, etag = ?, last_modified = ?
                        WHERE kind = ? AND asset_key = ? AND body IS NULL
                          AND content_type = ? AND size = ? AND etag = ?
                          AND last_modified = ? AND bucket = ? AND s3_key = ?
                        """,
                        (
                            fetched.body,
                            len(fetched.body),
                            fetched.etag,
                            fetched.last_modified,
                            row.kind,
                            row.asset_key,
                            row.content_type,
                            row.size,
                            row.etag,
                            row.last_modified,
                            row.bucket,
                            row.s3_key,
                        ),
                    )
                if cursor.rowcount != 1:
                    raise MaterializationError(
                        f"cache asset changed during materialization: {row.kind}/{row.asset_key}"
                    )
            except sqlite3.Error as exc:
                raise MaterializationError("cache asset could not be stored") from exc
            completed += 1
            if progress is not None:
                progress(completed, total)
        count = verify_materialized_cache(cache)
        return count
    finally:
        connection.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--origin", help="Existing public TTRPG HTTP(S) origin")
    parser.add_argument("--s3-region", help="Materialize directly from approved S3 bindings")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    if not arguments.check and bool(arguments.origin) == bool(arguments.s3_region):
        parser.error("select exactly one of --origin or --s3-region")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if arguments.check:
            count = verify_materialized_cache(arguments.cache)
            print(f"verified {count} materialized cache assets")
            return 0

        def show_progress(completed: int, total: int) -> None:
            if completed == total or completed % 100 == 0:
                print(f"materialized {completed}/{total} cache assets", flush=True)

        selected_fetcher = (
            s3_fetcher(region=arguments.s3_region, timeout=arguments.timeout)
            if arguments.s3_region
            else fetch_asset
        )
        count = materialize_cache_assets(
            arguments.cache,
            origin=arguments.origin or "https://s3.us-east-1.amazonaws.com",
            workers=arguments.workers,
            timeout=arguments.timeout,
            fetcher=selected_fetcher,
            progress=show_progress,
        )
    except MaterializationError as exc:
        print(f"cache materialization failed: {exc}", file=sys.stderr)
        return 1
    print(f"verified {count} materialized cache assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

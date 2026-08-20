from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from copy import deepcopy
from http import HTTPStatus
from pathlib import Path
from urllib import parse as urlparse

from . import (
    pf2er_compiler,
    pf2er_semantic,
    semantic_service,
    ttrpg_auth,
)
from .pf2er_compiler import source_authority_store
from .pf2er_compiler import source_nodes
from .pf2er_compiler.mechanics import source_authority


LOGGER = logging.getLogger(__name__)
RULESET_ID = "pf2er"
LIBRARY_DATASET = "library/games/ttrpg/pf2er"
LOCAL_RENDERER_DATASET = ".api/assets/pf2er"
PUBLICATION_SECTION_LABELS = ("Front Matter", "Back Matter")
CACHE_SCHEMA_VERSION = 3
ENGINE_VERSION = 1
ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE_PATH = ROOT / "cache" / "cache.db"
RULE_TARGETS_PATH = ROOT / "@static" / "rules-targets.json"
RULE_MENU_PATH = ROOT / "@static" / "rules-menu.json"
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SPELL_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GENERATION_RE = re.compile(r"^[0-9a-f]{64}$")
CSS_IMPORT_RE = re.compile(
    r"@import\s+(?:url\(\s*(?:\"[^\"]*\"|'[^']*'|[^)]*)\s*\)|(?:\"[^\"]*\"|'[^']*'))[^;]*;",
    re.IGNORECASE,
)
ICON_ASSET_EXTENSIONS = (".svg", ".png", ".webp", ".avif")
IMAGE_ASSET_EXTENSIONS = (".webp", ".avif", ".png", ".jpg", ".jpeg")
_RULE_TARGET_CACHE: tuple[tuple[int, int], frozenset[tuple[str, str]]] | None = None
_SPELL_INDEX_CACHE: tuple[
    tuple[int, int, int, int],
    dict[str, tuple[str, tuple[tuple[str, str], ...]]],
] | None = None
_RULE_TARGET_LOCK = threading.Lock()
_AUTHORITY_STORE_LOCK = threading.RLock()
_AUTHORITY_STORE_STATE: tuple[
    Path,
    tuple[int, int, int, int],
    source_authority_store.SourceAuthorityStore,
    tuple[str, str, str],
] | None = None
_TTRPG_AUTH_STORE_LOCK = threading.Lock()
_TTRPG_AUTH_STORE_STATE: tuple[
    Path,
    tuple[int, int],
    ttrpg_auth.TtrpgAuthStore,
] | None = None
_SCOPE_SECRET = (
    os.environ.get("KMQDB_TTRPG_SCOPE_SECRET", "").encode("utf-8")
    or secrets.token_bytes(32)
)


class CacheMiss(Exception):
    pass


class CacheConflict(Exception):
    pass


class CacheUnavailable(Exception):
    pass


AssetStreamResponse = tuple[
    str,
    list[tuple[str, str]],
    Iterable[bytes],
]
AssetStreamer = Callable[..., AssetStreamResponse | None]




def status_line(status: int) -> str:
    try:
        phrase = HTTPStatus(status).phrase
    except ValueError:
        phrase = "Unknown"
    return f"{status} {phrase}"


def response(start_response, status: int, body: bytes, content_type: str, headers=()):
    response_headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("X-Content-Type-Options", "nosniff"),
        *headers,
    ]
    start_response(status_line(status), response_headers)
    return [body]


def json_response(start_response, payload: object, status: int = 200, headers=()):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return response(
        start_response,
        status,
        body,
        "application/json; charset=utf-8",
        headers=[("Cache-Control", "no-store"), *headers],
    )


def api_error(start_response, message: str, status: int = 400):
    return json_response(start_response, {"error": message}, status=status)




def request_query(environ: dict) -> dict[str, list[str]]:
    return urlparse.parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)


def query_value(query: dict[str, list[str]], name: str, default: str = "") -> str:
    values = query.get(name) or []
    return str(values[0]) if values else default


def ttrpg_read_route(parts: list[str]) -> bool:
    return (
        parts == [".api", "bookshelf"]
        or (
            len(parts) == 4
            and parts[:2] == [".api", "sources"]
            and parts[3] in {"publication", "cover", "node"}
        )
        or parts
        in (
            [".api", "rules", "source-node"],
            [".api", "rules", "spell-reference"],
        )
        or (
            len(parts) == 4
            and parts[:2] == [".api", "presentation"]
        )
        or (
            len(parts) > 5
            and parts[:4]
            == [".api", "assets", RULESET_ID, ".static"]
            and parts[4] in {"icons", "images"}
        )
    )






def ttrpg_auth_store() -> ttrpg_auth.TtrpgAuthStore:
    """Return the TTRPG-owned browser-session store."""

    global _TTRPG_AUTH_STORE_STATE

    configured = (
        os.environ.get(
            ttrpg_auth.DATABASE_ENVIRONMENT_VARIABLE
        )
        or ttrpg_auth.DEFAULT_DATABASE_PATH
    )
    database_path = Path(configured).resolve()
    with _TTRPG_AUTH_STORE_LOCK:
        try:
            status = database_path.stat()
            signature = (
                int(status.st_dev),
                int(status.st_ino),
            )
        except FileNotFoundError:
            signature = None
        state = _TTRPG_AUTH_STORE_STATE
        if (
            state is not None
            and state[0] == database_path
            and signature is not None
            and state[1] == signature
        ):
            return state[2]
        store = ttrpg_auth.TtrpgAuthStore(database_path)
        status = database_path.stat()
        _TTRPG_AUTH_STORE_STATE = (
            database_path,
            (int(status.st_dev), int(status.st_ino)),
            store,
        )
        return store




def cache_database_path() -> Path:
    configured = str(os.environ.get("KMQDB_TTRPG_CACHE_DB") or "").strip()
    if not configured:
        return DEFAULT_CACHE_PATH
    path = Path(configured)
    return path if path.is_absolute() else (ROOT / path)


def cache_file_signature(path: Path) -> tuple[int, int, int, int]:
    try:
        status = path.stat()
    except OSError as failure:
        raise CacheUnavailable("content cache is unavailable") from failure
    if not path.is_file():
        raise CacheUnavailable("content cache is unavailable")
    return (
        status.st_dev,
        status.st_ino,
        status.st_size,
        status.st_mtime_ns,
    )


def open_cache_connection(path: Path) -> sqlite3.Connection:
    try:
        return sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
            isolation_level=None,
        )
    except sqlite3.Error as failure:
        raise CacheUnavailable("content cache is unavailable") from failure


def cache_data_version(connection: sqlite3.Connection) -> int:
    cursor = connection.cursor()
    cursor.row_factory = None
    rows = cursor.execute("PRAGMA data_version").fetchall()
    if (
        type(rows) is not list
        or len(rows) != 1
        or type(rows[0]) is not tuple
        or len(rows[0]) != 1
        or type(rows[0][0]) is not int
    ):
        raise CacheUnavailable(
            "content cache data version is invalid"
        )
    return rows[0][0]


def cache_authority_identity(
    connection: sqlite3.Connection,
) -> tuple[str, str, str]:
    cursor = connection.cursor()
    cursor.row_factory = None
    metadata_rows = cursor.execute(
        "SELECT key, value FROM metadata "
        "WHERE key IN ('ruleset', 'source_generation') "
        "ORDER BY key"
    ).fetchall()
    if (
        type(metadata_rows) is not list
        or len(metadata_rows) != 2
        or metadata_rows[0] != ("ruleset", RULESET_ID)
        or type(metadata_rows[1]) is not tuple
        or len(metadata_rows[1]) != 2
        or metadata_rows[1][0] != "source_generation"
        or type(metadata_rows[1][1]) is not str
        or GENERATION_RE.fullmatch(metadata_rows[1][1]) is None
    ):
        raise CacheUnavailable(
            "content cache authority identity is invalid"
        )
    authority_rows = cursor.execute(
        "SELECT singleton, payload FROM authority_snapshot "
        "ORDER BY singleton"
    ).fetchall()
    if (
        type(authority_rows) is not list
        or len(authority_rows) != 1
        or type(authority_rows[0]) is not tuple
        or len(authority_rows[0]) != 2
        or authority_rows[0][0] != 1
        or type(authority_rows[0][1]) is not str
    ):
        raise CacheUnavailable(
            "content cache authority identity is invalid"
        )
    authority_payload = authority_rows[0][1]
    try:
        authority_manifest = json.loads(authority_payload)
    except json.JSONDecodeError as failure:
        raise CacheUnavailable(
            "content cache authority identity is invalid"
        ) from failure
    if (
        type(authority_manifest) is not dict
        or type(authority_manifest.get("digest")) is not str
        or GENERATION_RE.fullmatch(
            authority_manifest["digest"]
        )
        is None
    ):
        raise CacheUnavailable(
            "content cache authority identity is invalid"
        )
    return (
        metadata_rows[1][1],
        authority_manifest["digest"],
        hashlib.sha256(
            authority_payload.encode("utf-8")
        ).hexdigest(),
    )


def begin_validated_cache_snapshot(
    connection: sqlite3.Connection,
    *,
    expected_authority_identity: tuple[str, str, str] | None = None,
    expected_data_version: int | None = None,
) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != CACHE_SCHEMA_VERSION:
        raise CacheUnavailable("content cache schema is unsupported")
    metadata = {
        str(row["key"] or ""): str(row["value"] or "")
        for row in connection.execute(
            "SELECT key, value FROM metadata "
            "WHERE key IN ('ruleset', 'source_generation')"
        )
    }
    if metadata.get("ruleset") != RULESET_ID:
        raise CacheUnavailable("content cache ruleset is invalid")
    if (
        GENERATION_RE.fullmatch(
            metadata.get("source_generation", "")
        )
        is None
    ):
        raise CacheUnavailable(
            "content cache source generation is invalid"
        )
    bookshelf_rows = connection.execute(
        "SELECT singleton, payload FROM bookshelf "
        "ORDER BY singleton"
    ).fetchall()
    if (
        len(bookshelf_rows) != 1
        or bookshelf_rows[0]["singleton"] != 1
        or type(bookshelf_rows[0]["payload"]) is not str
    ):
        raise CacheUnavailable(
            "content cache bookshelf receipt is invalid"
        )
    try:
        bookshelf_receipt = json.loads(
            bookshelf_rows[0]["payload"]
        )
    except json.JSONDecodeError as failure:
        raise CacheUnavailable(
            "content cache bookshelf receipt is invalid"
        ) from failure
    if (
        type(bookshelf_receipt) is not dict
        or type(bookshelf_receipt.get("schema")) is not int
        or bookshelf_receipt["schema"] != 2
        or bookshelf_receipt.get("dataset") != LIBRARY_DATASET
        or type(bookshelf_receipt.get("generation")) is not str
        or GENERATION_RE.fullmatch(
            bookshelf_receipt["generation"]
        )
        is None
        or not hmac.compare_digest(
            bookshelf_receipt["generation"],
            metadata["source_generation"],
        )
    ):
        raise CacheUnavailable(
            "content cache bookshelf receipt is invalid"
        )
    authority_rows = connection.execute(
        "SELECT singleton, payload FROM authority_snapshot "
        "ORDER BY singleton"
    ).fetchall()
    if (
        len(authority_rows) != 1
        or authority_rows[0]["singleton"] != 1
        or type(authority_rows[0]["payload"]) is not str
    ):
        raise CacheUnavailable(
            "content cache authority snapshot is invalid"
        )
    if expected_authority_identity is not None:
        actual_authority_identity = cache_authority_identity(
            connection
        )
        if (
            actual_authority_identity
            != expected_authority_identity
        ):
            raise CacheUnavailable(
                "content cache authority changed before use"
            )
    if (
        expected_data_version is not None
        and cache_data_version(connection) != expected_data_version
    ):
        raise CacheUnavailable(
            "content cache changed before use"
        )


def close_cache_connection(connection: sqlite3.Connection) -> None:
    try:
        if connection.in_transaction:
            connection.rollback()
    finally:
        connection.close()


@contextmanager
def cache_connection():
    path = cache_database_path().resolve()
    if not path.is_file():
        raise CacheUnavailable("content cache is unavailable")
    connection = open_cache_connection(path)
    try:
        begin_validated_cache_snapshot(connection)
    except sqlite3.Error as failure:
        connection.close()
        raise CacheUnavailable("content cache is unavailable") from failure
    except BaseException:
        connection.close()
        raise
    try:
        yield connection
    finally:
        close_cache_connection(connection)


def open_authority_cache_connection() -> tuple[
    sqlite3.Connection,
    source_authority_store.SourceAuthorityStore,
    tuple[str, str, str],
    int,
]:
    global _AUTHORITY_STORE_STATE

    path = cache_database_path().resolve()
    for _attempt in range(3):
        before = cache_file_signature(path)
        connection = open_cache_connection(path)
        try:
            connection.execute("PRAGMA query_only = ON")
            starting_data_version = cache_data_version(connection)
            authority_identity = cache_authority_identity(connection)
            if (
                cache_data_version(connection)
                != starting_data_version
            ):
                connection.close()
                continue
            if cache_file_signature(path) != before:
                connection.close()
                continue
            with _AUTHORITY_STORE_LOCK:
                state = _AUTHORITY_STORE_STATE
                if (
                    state is not None
                    and state[0] == path
                    and state[1] == before
                    and state[3] == authority_identity
                ):
                    store = state[2]
                else:
                    store = (
                        source_authority_store.SourceAuthorityStore
                        .from_connection(connection)
                    )
                ending_authority_identity = (
                    cache_authority_identity(connection)
                )
                ending_data_version = cache_data_version(connection)
                if (
                    ending_authority_identity
                    != authority_identity
                    or ending_data_version
                    != starting_data_version
                    or not hmac.compare_digest(
                        store.digest,
                        authority_identity[1],
                    )
                ):
                    connection.close()
                    continue
                if cache_file_signature(path) != before:
                    connection.close()
                    continue
                if state is None or store is not state[2]:
                    _AUTHORITY_STORE_STATE = (
                        path,
                        before,
                        store,
                        authority_identity,
                    )
            return (
                connection,
                store,
                authority_identity,
                ending_data_version,
            )
        except CacheUnavailable:
            connection.close()
            raise
        except sqlite3.Error as failure:
            connection.close()
            raise CacheUnavailable(
                "content cache is unavailable"
            ) from failure
        except (
            source_authority_store.SourceAuthorityStoreError,
            source_authority.SourceAuthorityError,
        ) as failure:
            connection.close()
            try:
                changed = cache_file_signature(path) != before
            except CacheUnavailable:
                changed = True
            if changed:
                continue
            raise CacheUnavailable(
                "content cache authority is invalid"
            ) from failure
        except BaseException:
            connection.close()
            raise
    raise CacheUnavailable(
        "content cache changed while loading authority"
    )


@contextmanager
def authority_cache_connection():
    (
        connection,
        store,
        authority_identity,
        data_version,
    ) = open_authority_cache_connection()
    try:
        begin_validated_cache_snapshot(
            connection,
            expected_authority_identity=authority_identity,
            expected_data_version=data_version,
        )
    except sqlite3.Error as failure:
        connection.close()
        raise CacheUnavailable("content cache is unavailable") from failure
    except BaseException:
        connection.close()
        raise
    try:
        yield connection, store
    finally:
        close_cache_connection(connection)


def decoded_json(value: object, label: str) -> object:
    try:
        return json.loads(str(value or ""))
    except json.JSONDecodeError as failure:
        raise CacheUnavailable(f"cached {label} is invalid") from failure


def cached_singleton(connection: sqlite3.Connection, table: str) -> dict:
    try:
        row = connection.execute(f"SELECT payload FROM {table} WHERE singleton = 1").fetchone()
    except sqlite3.Error as failure:
        raise CacheUnavailable("content cache is unavailable") from failure
    if row is None:
        raise CacheMiss(f"cached {table} not found")
    payload = decoded_json(row[0], table)
    if not isinstance(payload, dict):
        raise CacheUnavailable(f"cached {table} is invalid")
    return payload


def cached_source(connection: sqlite3.Connection, source_id: str) -> tuple[dict, list[dict]]:
    try:
        row = connection.execute(
            "SELECT payload, toc FROM sources WHERE id = ?",
            (source_id,),
        ).fetchone()
    except sqlite3.Error as failure:
        raise CacheUnavailable("content cache is unavailable") from failure
    if row is None:
        raise CacheMiss(f"source not cached: {source_id}")
    source = decoded_json(row["payload"], "source")
    toc = decoded_json(row["toc"], "source toc")
    if not isinstance(source, dict) or not isinstance(toc, list):
        raise CacheUnavailable("cached source is invalid")
    if str(source.get("id") or "") != source_id:
        raise CacheUnavailable("cached source identity is invalid")
    return source, toc


def cached_section(connection: sqlite3.Connection, section_id: str, source_id: str) -> dict:
    try:
        row = connection.execute(
            "SELECT source_id, payload FROM sections WHERE id = ?",
            (section_id,),
        ).fetchone()
    except sqlite3.Error as failure:
        raise CacheUnavailable("content cache is unavailable") from failure
    if row is None:
        raise CacheConflict(f"source section not cached: {section_id}")
    if str(row["source_id"] or "") != source_id:
        raise CacheConflict(f"source section belongs to another source: {section_id}")
    payload = decoded_json(row["payload"], "source section")
    if not isinstance(payload, dict):
        raise CacheUnavailable("cached source section is invalid")
    result = dict(payload)
    result["parent"] = source_id
    result["source_id"] = source_id
    return result


def cached_upstream_origin(connection: sqlite3.Connection) -> str:
    try:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'upstream_origin'"
        ).fetchone()
    except sqlite3.Error:
        return ""
    return str(row[0] or "").rstrip("/") if row is not None else ""


def public_bookshelf(payload: dict, cached_source_ids: set[str] | None = None) -> dict:
    entries = []
    for item in payload.get("entries") or []:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or "")
        if not SOURCE_ID_RE.fullmatch(source_id):
            continue
        if cached_source_ids is not None and source_id not in cached_source_ids:
            continue
        entries.append(
            {
                "id": source_id,
                "slug": str(item.get("slug") or source_id),
                "name": str(item.get("name") or source_id),
                "date": str(item.get("date") or ""),
                "kind": str(item.get("kind") or ""),
                "parent": str(item.get("parent") or ""),
            }
        )
    return {
        "schema": 1,
        "ruleset": RULESET_ID,
        "name": str(payload.get("name") or "Pathfinder 2E Remaster"),
        "description": str(payload.get("description") or ""),
        "entries": entries,
    }


def cached_source_ids(connection: sqlite3.Connection) -> set[str]:
    try:
        return {
            str(row[0] or "")
            for row in connection.execute("SELECT id FROM sources")
            if row[0]
        }
    except sqlite3.Error as failure:
        raise CacheUnavailable("content cache is unavailable") from failure


def cached_rules_manifest(connection: sqlite3.Connection, source_ids: list[str]) -> dict:
    entries = []
    for source_id in sorted(source_ids):
        if not SOURCE_ID_RE.fullmatch(source_id):
            raise pf2er_compiler.EngineInputError(
                f"rules source id is invalid: {source_id}"
            )
        try:
            row = connection.execute(
                "SELECT payload, toc FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
        except sqlite3.Error as failure:
            raise CacheUnavailable("content cache is unavailable") from failure
        if row is None:
            raise CacheMiss(f"rules source is not cached: {source_id}")
        source = decoded_json(row["payload"], "source")
        if not isinstance(source, dict) or str(source.get("id") or "") != source_id:
            raise CacheUnavailable("cached source identity is invalid")
        digest = hashlib.sha256(
            str(row["payload"]).encode("utf-8")
            + b"\0"
            + str(row["toc"]).encode("utf-8")
        ).hexdigest()
        entries.append(
            {
                "id": source_id,
                "name": str(source.get("name") or source_id),
                "date": str(source.get("date") or ""),
                "digest": digest,
            }
        )
    bundle_digest = hashlib.sha256(
        "\n".join(f"{entry['id']}:{entry['digest']}" for entry in entries).encode("utf-8")
    ).hexdigest()
    return {
        "ruleset": RULESET_ID,
        "engineVersion": ENGINE_VERSION,
        "sources": entries,
        "digest": bundle_digest,
    }


def public_toc_node(node: object) -> dict | None:
    if not isinstance(node, dict):
        return None
    label = str(node.get("label") or "")
    if not label:
        return None
    children = [
        child
        for child in (public_toc_node(item) for item in node.get("children") or [])
        if child is not None
    ]
    return {
        "label": label,
        "locator": str(node.get("locator") or ""),
        "children": children,
    }


def public_publication_toc(forest: object) -> tuple[list[dict], list[str]]:
    nodes = forest if isinstance(forest, list) else []
    selected = []
    roots = []
    for label in PUBLICATION_SECTION_LABELS:
        matches = [node for node in nodes if isinstance(node, dict) and str(node.get("label") or "") == label]
        if len(matches) > 1:
            raise CacheConflict("cached publication section is ambiguous")
        if not matches:
            continue
        public_node = public_toc_node(matches[0])
        if public_node is None:
            continue
        selected.append(public_node)
        if public_node["locator"]:
            roots.append(public_node["locator"])
    return selected, roots


def authentication_fingerprint(environ: dict) -> str:
    identity = "\0".join(
        (
            str(environ.get("HTTP_COOKIE") or ""),
            str(environ.get("HTTP_AUTHORIZATION") or ""),
        )
    ).encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def publication_scope(environ: dict, source_id: str, roots: list[str]) -> str:
    payload = json.dumps(
        {
            "v": 1,
            "source": source_id,
            "roots": roots,
            "auth": authentication_fingerprint(environ),
            "exp": int(time.time()) + 3600,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = b64url_encode(payload)
    signature = b64url_encode(hmac.new(_SCOPE_SECRET, encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def publication_scope_allows(environ: dict, token: str, source_id: str, root: str) -> bool:
    try:
        encoded, signature = token.split(".", 1)
        expected = b64url_encode(hmac.new(_SCOPE_SECRET, encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(b64url_decode(encoded).decode("utf-8"))
    except (binascii.Error, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    try:
        expires = int(payload.get("exp") or 0) if isinstance(payload, dict) else 0
    except (TypeError, ValueError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("v") == 1
        and str(payload.get("source") or "") == source_id
        and str(payload.get("auth") or "") == authentication_fingerprint(environ)
        and expires >= int(time.time())
        and root in {str(value) for value in payload.get("roots") or []}
    )


def rewrite_cached_text(value: str, upstream_origin: str = "") -> str:
    upstream_prefix = f"/{LIBRARY_DATASET}"
    local_prefix = f"/{LOCAL_RENDERER_DATASET}"
    text = str(value)
    if upstream_origin:
        text = text.replace(f"{upstream_origin}{upstream_prefix}", local_prefix)
    return text.replace(upstream_prefix, local_prefix)


def rewrite_cached_value(value: object, upstream_origin: str = ""):
    if isinstance(value, dict):
        return {key: rewrite_cached_value(item, upstream_origin) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_cached_value(item, upstream_origin) for item in value]
    if isinstance(value, str):
        return rewrite_cached_text(value, upstream_origin)
    return value


def public_source(source: object, source_id: str, *, has_cover: bool = True) -> dict:
    raw = source if isinstance(source, dict) else {}
    if str(raw.get("id") or "") != source_id:
        raise CacheUnavailable("cached publication identity is invalid")
    result = {
        key: raw.get(key)
        for key in ("id", "name", "date", "sku", "isbn", "pages")
        if key in raw
    }
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    result["meta"] = {key: value for key, value in meta.items() if key != "images"}
    if has_cover:
        result["cover"] = f"/.api/sources/{urlparse.quote(source_id, safe='')}/cover"
    return result


def asset_is_cached(connection: sqlite3.Connection, kind: str, key: str) -> bool:
    try:
        return connection.execute(
            "SELECT 1 FROM binary_assets WHERE kind = ? AND asset_key = ? LIMIT 1",
            (kind, key),
        ).fetchone() is not None
    except sqlite3.Error as failure:
        raise CacheUnavailable("content cache is unavailable") from failure


def publication_response(connection: sqlite3.Connection, environ: dict, start_response, source_id: str):
    source, forest = cached_source(connection, source_id)
    toc, roots = public_publication_toc(forest)
    origin = cached_upstream_origin(connection)
    exposed_source = public_source(source, source_id, has_cover=asset_is_cached(connection, "cover", source_id))
    exposed_source = rewrite_cached_value(exposed_source, origin)
    return json_response(
        start_response,
        {
            "schema": 1,
            "ruleset": RULESET_ID,
            "source": exposed_source,
            "toc": [
                {"label": "Overview", "locator": "", "kind": "overview", "children": []},
                *toc,
            ],
            "scope": publication_scope(environ, source_id, roots),
        },
    )


def source_toc_node_paths(nodes: list[dict], locator: str, ancestors: list[dict] | None = None) -> list[list[dict]]:
    prefix = list(ancestors or [])
    matches: list[list[dict]] = []
    for node in nodes:
        path = [*prefix, node]
        if str(node.get("locator") or "") == locator:
            matches.append(path)
        matches.extend(source_toc_node_paths(node.get("children") or [], locator, path))
    return matches


def source_toc_path_is_descendant(root_path: list[dict], selected_path: list[dict]) -> bool:
    if not root_path or len(selected_path) < len(root_path):
        return False
    return all(root_node is selected_node for root_node, selected_node in zip(root_path, selected_path))


def source_toc_branch_from_path(path: list[dict]) -> dict | None:
    if not path:
        return None
    branch = {**path[-1], "children": list(path[-1].get("children") or [])}
    for ancestor in reversed(path[:-1]):
        branch = {**ancestor, "children": [branch]}
    return branch


def source_node_target_from_toc(forest: list[dict], locator: str) -> tuple[dict, list[dict]]:
    paths = source_toc_node_paths(forest, locator)
    if not paths:
        raise CacheMiss(f"source locator not cached: {locator}")
    if len(paths) != 1:
        raise CacheConflict(f"source locator is ambiguous: {locator}")
    node = paths[0][-1]
    if not str(node.get("section_id") or ""):
        raise CacheConflict(f"source locator has no content binding: {locator}")
    return node, paths[0]


def normalized_content_path(value: object) -> list[str]:
    return [str(part) for part in value] if isinstance(value, list) else []


def presentation_proxy_manifest(presentation: object) -> dict:
    raw = presentation if isinstance(presentation, dict) else {}
    stylesheets = raw.get("stylesheets") if isinstance(raw.get("stylesheets"), list) else []
    scripts = raw.get("scripts") if isinstance(raw.get("scripts"), list) else []
    return {
        "vocabulary": raw.get("vocabulary") if isinstance(raw.get("vocabulary"), dict) else {},
        "renderer": str(raw.get("renderer") or ""),
        "stylesheets": [f"/.api/presentation/css/{index}" for index, _item in enumerate(stylesheets)],
        "scripts": [f"/.api/presentation/js/{index}" for index, _item in enumerate(scripts)],
    }


def source_node_packet(
    connection: sqlite3.Connection,
    source_id: str,
    root_locator: str,
    selected_locator: str,
) -> dict:
    source, forest = cached_source(connection, source_id)
    root_node, root_path = source_node_target_from_toc(forest, root_locator)
    selected_node, selected_path = source_node_target_from_toc(forest, selected_locator)
    if not source_toc_path_is_descendant(root_path, selected_path):
        raise CacheConflict("selected source locator is outside the mapped root")

    root_section_id = str(root_node.get("section_id") or "")
    selected_section_id = str(selected_node.get("section_id") or "")
    root_section = cached_section(connection, root_section_id, source_id)
    selected_section = root_section if selected_section_id == root_section_id else cached_section(
        connection, selected_section_id, source_id
    )
    chapter_id = str(selected_section.get("chapter_id") or "")
    chapter = cached_section(connection, chapter_id, source_id) if chapter_id else None
    navigation_tree = source_toc_branch_from_path(root_path)
    if navigation_tree is None:
        raise CacheConflict("source root locator has no ToC branch")

    presentation = cached_singleton(connection, "presentation")
    public_source_payload = {
        key: source.get(key)
        for key in ("id", "name", "date", "sku", "isbn", "pages", "vocab", "css", "renderer")
        if key in source
    }
    if "css" in public_source_payload:
        public_source_payload["css"] = CSS_IMPORT_RE.sub("", str(public_source_payload.get("css") or ""))
    packet = {
        "schema": 1,
        "dataset": LOCAL_RENDERER_DATASET,
        "source": public_source_payload,
        "target": {
            "root": {
                "source_id": source_id,
                "locator": root_locator,
                "section_id": root_section_id,
                "content_path": normalized_content_path(root_node.get("content_path")),
                "title": str(root_node.get("label") or root_locator),
            },
            "selected": {
                "source_id": source_id,
                "locator": selected_locator,
                "section_id": selected_section_id,
                "content_path": normalized_content_path(selected_node.get("content_path")),
                "title": str(selected_node.get("label") or selected_locator),
            },
        },
        "toc": navigation_tree,
        "content": {"section": selected_section, "chapter": chapter},
        "presentation": presentation_proxy_manifest(presentation),
    }
    return rewrite_cached_value(packet, cached_upstream_origin(connection))


def allowed_rule_targets() -> frozenset[tuple[str, str]]:
    global _RULE_TARGET_CACHE
    stat = RULE_TARGETS_PATH.stat()
    signature = (stat.st_mtime_ns, stat.st_size)
    with _RULE_TARGET_LOCK:
        if _RULE_TARGET_CACHE is not None and _RULE_TARGET_CACHE[0] == signature:
            return _RULE_TARGET_CACHE[1]
        payload = json.loads(RULE_TARGETS_PATH.read_text(encoding="utf-8"))
        ruleset = payload.get("rulesets", {}).get(RULESET_ID, {})
        entries = ruleset.get("entries") if isinstance(ruleset, dict) else {}
        targets = frozenset(
            (str(target.get("source") or ""), str(target.get("locator") or ""))
            for values in entries.values()
            if isinstance(values, list)
            for target in values
            if isinstance(target, dict) and target.get("source") and target.get("locator")
        ) if isinstance(entries, dict) else frozenset()
        _RULE_TARGET_CACHE = (signature, targets)
        return targets


def _normalized_spell_identity(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _indexed_spells() -> dict[str, tuple[str, tuple[tuple[str, str], ...]]]:
    """Return the current public spell-name index and its exact source targets."""

    global _SPELL_INDEX_CACHE
    menu_stat = RULE_MENU_PATH.stat()
    target_stat = RULE_TARGETS_PATH.stat()
    signature = (
        menu_stat.st_mtime_ns,
        menu_stat.st_size,
        target_stat.st_mtime_ns,
        target_stat.st_size,
    )
    with _RULE_TARGET_LOCK:
        if _SPELL_INDEX_CACHE is not None and _SPELL_INDEX_CACHE[0] == signature:
            return _SPELL_INDEX_CACHE[1]
        menu_payload = json.loads(RULE_MENU_PATH.read_text(encoding="utf-8"))
        target_payload = json.loads(RULE_TARGETS_PATH.read_text(encoding="utf-8"))
        menu_ruleset = menu_payload.get("rulesets", {}).get(RULESET_ID, {})
        target_ruleset = target_payload.get("rulesets", {}).get(RULESET_ID, {})
        menu_entries = menu_ruleset.get("entries")
        target_entries = target_ruleset.get("entries")
        if type(menu_entries) is not list or type(target_entries) is not dict:
            raise CacheUnavailable("public spell index is invalid")
        spells: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {}
        for entry in menu_entries:
            if type(entry) is not dict:
                raise CacheUnavailable("public spell index entry is invalid")
            entry_id = entry.get("id")
            if type(entry_id) is not str or not entry_id.startswith("cc-spells-"):
                continue
            name = entry.get("name")
            identity = _normalized_spell_identity(entry_id.removeprefix("cc-spells-"))
            if type(name) is not str or not name or not identity:
                raise CacheUnavailable("public spell index entry is invalid")
            raw_targets = target_entries.get(entry_id)
            if type(raw_targets) is not list or not raw_targets:
                raise CacheUnavailable("public spell index target is unavailable")
            targets: list[tuple[str, str]] = []
            for target in raw_targets:
                if (
                    type(target) is not dict
                    or set(target) != {"source", "locator"}
                    or type(target.get("source")) is not str
                    or not SOURCE_ID_RE.fullmatch(target["source"])
                    or type(target.get("locator")) is not str
                    or not target["locator"]
                ):
                    raise CacheUnavailable("public spell index target is invalid")
                targets.append((target["source"], target["locator"]))
            if identity in spells:
                raise CacheUnavailable("public spell index identity is ambiguous")
            spells[identity] = (name, tuple(targets))
        _SPELL_INDEX_CACHE = (signature, spells)
        return spells


def indexed_spell_reference(
    connection: sqlite3.Connection,
    spell_id: str,
    spell_name: str,
) -> dict:
    """Resolve one server-issued spell identity through the live TTRPG index."""

    if (
        type(spell_id) is not str
        or SPELL_ID_RE.fullmatch(spell_id) is None
        or type(spell_name) is not str
        or not 1 <= len(spell_name) <= 160
        or any(ord(character) < 32 or ord(character) == 127 for character in spell_name)
    ):
        raise CacheConflict("spell reference identity is invalid")
    identity = _normalized_spell_identity(spell_id)
    indexed = _indexed_spells().get(identity)
    if indexed is None:
        raise CacheMiss("spell is not present in the public rules index")
    official_name, targets = indexed
    if official_name != spell_name:
        raise CacheConflict("server spell name differs from the public rules index")
    if len(targets) != 1:
        raise CacheConflict("spell source is ambiguous in the public rules index")
    source_id, locator = targets[0]
    _source, forest = cached_source(connection, source_id)
    target_node, _target_path = source_node_target_from_toc(forest, locator)
    section_id = str(target_node.get("section_id") or "")
    content_path = normalized_content_path(target_node.get("content_path"))
    if not section_id or not content_path:
        raise CacheUnavailable("indexed spell source binding is invalid")
    section = cached_section(connection, section_id, source_id)
    content = section.get("content")
    if type(content) is not str:
        raise CacheUnavailable("indexed spell source content is invalid")
    try:
        spell = source_nodes.content_target(content, content_path)
        resolved_name = spell.unique("Name")
        description = source_nodes.source_flow_text(
            spell.unique("Description"),
            f"{spell_name} Description",
        )
    except pf2er_compiler.EngineInputError as failure:
        raise CacheUnavailable("indexed spell source record is invalid") from failure
    if resolved_name != official_name or not description:
        raise CacheUnavailable("indexed spell source identity differs")
    return {
        "schema": 1,
        "kind": "pf2er-indexed-spell-reference",
        "spell": {
            "id": spell_id,
            "name": official_name,
            "description": description,
            "source": {"sourceId": source_id, "locator": locator},
        },
    }


def presentation_response(connection: sqlite3.Connection, environ: dict, start_response, kind: str, index: int):
    try:
        row = connection.execute(
            """
            SELECT content_type, body
            FROM presentation_assets
            WHERE kind = ? AND asset_index = ?
            """,
            (kind, index),
        ).fetchone()
    except sqlite3.Error as failure:
        raise CacheUnavailable("content cache is unavailable") from failure
    if row is None:
        raise CacheMiss("presentation asset not cached")
    body = bytes(row["body"] or b"")
    if kind == "css":
        try:
            body = CSS_IMPORT_RE.sub("", body.decode("utf-8")).encode("utf-8")
        except UnicodeDecodeError as failure:
            raise CacheUnavailable("cached presentation asset is invalid") from failure
    if str(environ.get("REQUEST_METHOD") or "GET").upper() == "HEAD":
        head_body = b""
        start_response(
            "200 OK",
            [
                ("Content-Type", str(row["content_type"] or "text/plain; charset=utf-8")),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-cache"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )
        return [head_body]
    return response(
        start_response,
        200,
        body,
        str(row["content_type"] or "text/plain; charset=utf-8"),
        headers=[("Cache-Control", "no-cache")],
    )


def request_etag_matches(environ: dict, etag: str) -> bool:
    supplied = str(environ.get("HTTP_IF_NONE_MATCH") or "").strip()
    if not supplied or not etag:
        return False
    if supplied == "*":
        return True

    def strong_value(value: str) -> str:
        stripped = value.strip()
        return stripped[2:].strip() if stripped.startswith("W/") else stripped

    expected = strong_value(etag)
    return any(
        strong_value(candidate) == expected
        for candidate in supplied.split(",")
    )


def cached_binary_response(
    connection: sqlite3.Connection,
    environ: dict,
    start_response,
    kind: str,
    key: str,
    *,
    asset_streamer: AssetStreamer | None = None,
):
    try:
        row = connection.execute(
            """
            SELECT content_type, bucket, s3_key, body, size, etag, last_modified
            FROM binary_assets
            WHERE kind = ? AND asset_key = ?
            """,
            (kind, key),
        ).fetchone()
    except sqlite3.Error as failure:
        raise CacheUnavailable("content cache is unavailable") from failure
    if row is None:
        raise CacheMiss("binary asset not cached")

    content_type = str(row["content_type"] or "application/octet-stream")
    if not content_type.startswith("image/"):
        raise CacheUnavailable("cached binary asset type is invalid")
    common_headers = [
        ("Cache-Control", "private, no-cache"),
        ("Cross-Origin-Resource-Policy", "same-origin"),
    ]
    if kind == "icon":
        common_headers.append(("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox"))
    etag = str(row["etag"] or "")
    last_modified = str(row["last_modified"] or "")
    if etag and request_etag_matches(environ, etag):
        headers = [
            *common_headers,
            ("ETag", etag),
            ("X-Content-Type-Options", "nosniff"),
        ]
        if last_modified:
            headers.append(("Last-Modified", last_modified))
        start_response("304 Not Modified", headers)
        return [b""]

    if row["body"] is not None:
        body = bytes(row["body"])
        headers = list(common_headers)
        if etag:
            headers.append(("ETag", etag))
        if last_modified:
            headers.append(("Last-Modified", last_modified))
        if str(environ.get("REQUEST_METHOD") or "GET").upper() == "HEAD":
            start_response(
                "200 OK",
                [
                    ("Content-Type", content_type),
                    ("Content-Length", str(len(body))),
                    ("X-Content-Type-Options", "nosniff"),
                    *headers,
                ],
            )
            return [b""]
        return response(start_response, 200, body, content_type, headers=headers)

    s3_key = str(row["s3_key"] or "")
    if not s3_key:
        raise CacheMiss("binary asset has no cached storage binding")
    if asset_streamer is None:
        raise CacheUnavailable("external asset service is unavailable")
    bucket = str(os.environ.get("KMQDB_TTRPG_S3_BUCKET") or row["bucket"] or "").strip() or None
    streamed = asset_streamer(
        s3_key,
        environ,
        bucket=bucket,
        cache_control="private, no-cache",
        extra_headers=tuple(common_headers[1:]),
    )
    if streamed is None:
        raise CacheMiss("binary asset not found")
    status, headers, body = streamed
    start_response(status, [*headers, ("X-Content-Type-Options", "nosniff")])
    return body




class _CachedRulesCatalogSnapshot:
    """One authenticated snapshot over the TTRPG authority cache."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        authority_adapter: object,
        rules_manifest: dict,
        selected_source_ids: tuple[str, ...],
    ) -> None:
        self._connection = connection
        self._authority_adapter = authority_adapter
        self._rules_manifest = deepcopy(rules_manifest)
        try:
            self._semantic_compiler_by_source = {
                source_id: (
                    pf2er_semantic.build_pf2er_creature_compiler_set_for_source(
                        source_id=source_id,
                        selected_source_ids=selected_source_ids,
                    )
                )
                for source_id in pf2er_semantic.PF2ER_CREATURE_BOOK_BY_SOURCE
                if source_id in selected_source_ids
            }
        except pf2er_semantic.PF2ERSemanticCompositionError as failure:
            raise CacheUnavailable(
                "content cache compiler selection is invalid"
            ) from failure

    @property
    def rules_manifest(self) -> dict:
        return deepcopy(self._rules_manifest)

    def load_creature(self, source_id: str, locator: str) -> dict:
        if type(source_id) is not str:
            raise pf2er_compiler.EngineInputError(
                "creature source must be one exact selected source ID"
            )
        compiler_set = self._semantic_compiler_by_source.get(source_id)
        if compiler_set is None:
            raise pf2er_compiler.EngineInputError(
                f"creature source is not selected or supported: {source_id}"
            )
        try:
            return compiler_set.compile_source_creature(
                self._authority_adapter,
                source_id,
                locator,
            )
        except source_authority.SourceAddressError as failure:
            raise pf2er_compiler.EngineInputError(
                "creature source target is invalid: "
                f"{source_id}/{locator}"
            ) from failure
        except source_authority.SourceAuthorityError as failure:
            raise CacheUnavailable(
                "content cache creature authority is invalid"
            ) from failure

    def load_equipment_catalog(self, source_names: set[str]) -> dict:
        return pf2er_compiler.compile_equipment_catalog(
            source_names,
            armor_packet=source_node_packet(
                self._connection,
                "core-pc1",
                "271.1",
                "271.1",
            ),
            shield_packet=source_node_packet(
                self._connection,
                "core-pc1",
                "274.1",
                "274.1",
            ),
            weapons_packet=source_node_packet(
                self._connection,
                "core-pc1",
                "275.1",
                "275.1",
            ),
        )


class _CachedRulesCatalogClient:
    """Open authenticated TTRPG catalog snapshots for local compilers."""

    @contextmanager
    def open_snapshot(self, source_ids: tuple[str, ...]):
        with authority_cache_connection() as (
            connection,
            authority_store,
        ):
            manifest = cached_rules_manifest(connection, list(source_ids))
            try:
                authority_adapter = authority_store.adapter_for(source_ids)
            except (
                source_authority_store.SourceAuthorityStoreError,
                source_authority.SourceAuthorityError,
            ) as failure:
                raise CacheUnavailable(
                    "content cache authority scope is invalid"
                ) from failure
            yield _CachedRulesCatalogSnapshot(
                connection,
                authority_adapter,
                manifest,
                source_ids,
            )


_CACHED_RULES_CATALOG = _CachedRulesCatalogClient()


def _application(
    environ,
    start_response,
    *,
    asset_streamer: AssetStreamer | None,
):
    method = str(environ.get("REQUEST_METHOD", "GET")).upper()
    path = str(environ.get("PATH_INFO") or "/")
    parts = [part for part in path.strip("/").split("/") if part]
    is_auth_route = len(parts) >= 2 and parts[:2] == [".api", "auth"]

    if any(
        part in {".", ".."} or "\\" in part or "\x00" in part
        for part in parts
    ):
        return api_error(start_response, "route not found", 404)

    if (
        len(parts) >= 3
        and parts[:3] == [".api", "catalog", "v1"]
    ):
        try:
            return semantic_service.application(environ, start_response)
        except semantic_service.SemanticServiceConfigurationError:
            return api_error(
                start_response,
                "semantic catalog service is unavailable",
                503,
            )

    query = request_query(environ)
    try:
        if parts == [".api", "auth", "session"]:
            if method != "GET":
                return api_error(
                    start_response,
                    "method not allowed",
                    405,
                )
            principal = ttrpg_auth.principal_from_environ(
                ttrpg_auth_store(),
                environ,
            )
            return json_response(
                start_response,
                {"user": principal},
            )

        if parts == [".api", "auth", "logout"]:
            if method != "POST":
                return api_error(
                    start_response,
                    "method not allowed",
                    405,
                )
            store = ttrpg_auth_store()
            store.revoke_session(
                ttrpg_auth.cookie_session_token(environ)
            )
            return json_response(
                start_response,
                {"ok": True},
                headers=[
                    ttrpg_auth.clear_session_cookie_header(),
                ],
            )

        if parts == [".api", "auth", "sso", "start"]:
            if method != "GET":
                return api_error(
                    start_response,
                    "method not allowed",
                    405,
                )
            pending = ttrpg_auth_store().begin_authorization(
                return_to=query_value(
                    query,
                    "returnTo",
                    ttrpg_auth.DEFAULT_RETURN_TO,
                ),
                browser_token=(
                    ttrpg_auth.cookie_pending_token(environ)
                ),
            )
            return response(
                start_response,
                303,
                (
                    b"Redirecting to central KMQDB "
                    b"authentication.\n"
                ),
                "text/plain; charset=utf-8",
                headers=[
                    ("Location", pending["authorizationUrl"]),
                    ttrpg_auth.pending_cookie_header(
                        pending["browserToken"]
                    ),
                    ("Cache-Control", "no-store"),
                    ("Referrer-Policy", "no-referrer"),
                ],
            )

        if parts == [".api", "auth", "sso", "callback"]:
            if method != "GET":
                return api_error(
                    start_response,
                    "method not allowed",
                    405,
                )
            code = query_value(query, "code")
            state = query_value(query, "state")
            pending = (
                ttrpg_auth_store().consume_authorization(
                    state,
                    browser_token=(
                        ttrpg_auth.cookie_pending_token(environ)
                    ),
                )
            )
            principal = ttrpg_auth.exchange_identity(
                code=code,
                code_verifier=pending["codeVerifier"],
            )
            session, _session_payload = (
                ttrpg_auth_store().create_session(principal)
            )
            return response(
                start_response,
                303,
                b"Authentication complete.\n",
                "text/plain; charset=utf-8",
                headers=[
                    ("Location", pending["returnTo"]),
                    ttrpg_auth.clear_pending_cookie_header(),
                    ttrpg_auth.session_cookie_header(
                        session
                    ),
                    ("Cache-Control", "no-store"),
                    ("Referrer-Policy", "no-referrer"),
                ],
            )

        if ttrpg_read_route(parts) and method not in {"GET", "HEAD"}:
            return api_error(start_response, "method not allowed", 405)

        if parts == [".api", "bookshelf"]:
            with cache_connection() as connection:
                return json_response(
                    start_response,
                    public_bookshelf(
                        cached_singleton(connection, "bookshelf"),
                        cached_source_ids(connection),
                    ),
                )

        if len(parts) == 4 and parts[:2] == [".api", "sources"] and parts[3] == "publication":
            source_id = parts[2]
            if not SOURCE_ID_RE.fullmatch(source_id):
                return api_error(start_response, "invalid source id", 400)
            with cache_connection() as connection:
                return publication_response(connection, environ, start_response, source_id)

        if len(parts) == 4 and parts[:2] == [".api", "sources"] and parts[3] == "cover":
            source_id = parts[2]
            if not SOURCE_ID_RE.fullmatch(source_id):
                return api_error(start_response, "invalid source id", 400)
            with cache_connection() as connection:
                return cached_binary_response(
                    connection,
                    environ,
                    start_response,
                    "cover",
                    source_id,
                    asset_streamer=asset_streamer,
                )

        if len(parts) == 4 and parts[:2] == [".api", "sources"] and parts[3] == "node":
            source_id = parts[2]
            root = query_value(query, "root").strip()
            selected = query_value(query, "selected", root).strip() or root
            scope = query_value(query, "scope").strip()
            if not SOURCE_ID_RE.fullmatch(source_id) or not root or not selected:
                return api_error(start_response, "invalid source-node target", 400)
            if not publication_scope_allows(environ, scope, source_id, root):
                return api_error(start_response, "source-node scope is invalid or expired", 403)
            with cache_connection() as connection:
                return json_response(start_response, source_node_packet(connection, source_id, root, selected))

        if parts == [".api", "rules", "source-node"]:
            source_id = query_value(query, "source").strip()
            root = query_value(query, "root").strip()
            selected = query_value(query, "selected", root).strip() or root
            if not SOURCE_ID_RE.fullmatch(source_id) or not root or not selected:
                return api_error(start_response, "invalid rule source-node target", 400)
            if (source_id, root) not in allowed_rule_targets():
                return api_error(start_response, "rule source-node target is not registered", 404)
            with cache_connection() as connection:
                return json_response(start_response, source_node_packet(connection, source_id, root, selected))

        if parts == [".api", "rules", "spell-reference"]:
            spell_id = query_value(query, "spellId").strip()
            spell_name = query_value(query, "spellName").strip()
            if (
                SPELL_ID_RE.fullmatch(spell_id) is None
                or not spell_name
                or len(spell_name) > 160
            ):
                return api_error(start_response, "invalid spell reference", 400)
            with cache_connection() as connection:
                return json_response(
                    start_response,
                    indexed_spell_reference(connection, spell_id, spell_name),
                )

        if len(parts) == 4 and parts[:2] == [".api", "presentation"]:
            kind, raw_index = parts[2:]
            if kind not in {"css", "js"} or not raw_index.isdigit():
                return api_error(start_response, "presentation target not found", 404)
            with cache_connection() as connection:
                return presentation_response(connection, environ, start_response, kind, int(raw_index))

        asset_prefix = [".api", "assets", RULESET_ID, ".static", "icons"]
        if len(parts) > len(asset_prefix) and parts[:len(asset_prefix)] == asset_prefix:
            icon_parts = parts[len(asset_prefix):]
            if any(icon_parts[-1].endswith(extension) for extension in ICON_ASSET_EXTENSIONS):
                return api_error(start_response, "icon target not found", 404)
            key = "/".join(icon_parts)
            with cache_connection() as connection:
                return cached_binary_response(
                    connection,
                    environ,
                    start_response,
                    "icon",
                    key,
                    asset_streamer=asset_streamer,
                )

        asset_prefix = [".api", "assets", RULESET_ID, ".static", "images"]
        if len(parts) > len(asset_prefix) and parts[:len(asset_prefix)] == asset_prefix:
            image_parts = parts[len(asset_prefix):]
            if any(image_parts[-1].lower().endswith(extension) for extension in IMAGE_ASSET_EXTENSIONS):
                return api_error(start_response, "image target not found", 404)
            key = "/".join(image_parts)
            with cache_connection() as connection:
                return cached_binary_response(
                    connection,
                    environ,
                    start_response,
                    "image",
                    key,
                    asset_streamer=asset_streamer,
                )
    except CacheMiss as failure:
        return api_error(start_response, str(failure), 404)
    except CacheConflict as failure:
        return api_error(start_response, str(failure), 409)
    except CacheUnavailable as failure:
        return api_error(start_response, str(failure), 503)
    except ttrpg_auth.TtrpgAuthenticationError:
        return api_error(
            start_response,
            "central authentication failed",
            400,
        )
    except ttrpg_auth.TtrpgAuthError as failure:
        return api_error(start_response, str(failure), 400)
    except ttrpg_auth.TtrpgAuthUnavailableError:
        return api_error(
            start_response,
            "central authentication is unavailable",
            503,
        )
    except pf2er_compiler.EngineInputError as failure:
        return api_error(start_response, str(failure), 400)
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        sqlite3.Error,
    ) as failure:
        LOGGER.exception(
            "TTRPG service boundary failed for %s %s (%s)",
            method,
            path,
            type(failure).__name__,
        )
        if is_auth_route:
            return api_error(
                start_response,
                "central authentication is unavailable",
                503,
            )
        return api_error(start_response, "content cache is invalid", 500)
    return api_error(start_response, "route not found", 404)


def create_application(
    *,
    asset_streamer: AssetStreamer | None = None,
):
    """Bind the TTRPG WSGI application to an optional external asset port."""

    if asset_streamer is not None and not callable(asset_streamer):
        raise TypeError("asset_streamer must be callable or None")

    def configured_application(environ, start_response):
        return _application(
            environ,
            start_response,
            asset_streamer=asset_streamer,
        )

    return configured_application


application = create_application()


__all__ = [
    "AssetStreamer",
    "application",
    "create_application",
]

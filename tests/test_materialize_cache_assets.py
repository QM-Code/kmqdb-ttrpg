from __future__ import annotations

import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "materialize_cache_assets.py"
)
SPEC = importlib.util.spec_from_file_location(
    "kmqdb_ttrpg_cache_materializer_test",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
materializer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = materializer
SPEC.loader.exec_module(materializer)


def create_cache(path: Path, rows: tuple[tuple, ...]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA user_version=3;
            CREATE TABLE binary_assets (
                kind TEXT NOT NULL,
                asset_key TEXT NOT NULL,
                content_type TEXT NOT NULL,
                bucket TEXT NOT NULL,
                s3_key TEXT NOT NULL,
                body BLOB,
                size INTEGER NOT NULL,
                etag TEXT NOT NULL,
                last_modified TEXT NOT NULL,
                PRIMARY KEY (kind, asset_key)
            ) WITHOUT ROWID;
            """
        )
        connection.executemany(
            "INSERT INTO binary_assets VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()


class MaterializeCacheAssetsTests(unittest.TestCase):
    def test_materializes_pending_rows_and_is_restart_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            create_cache(
                cache,
                (
                    (
                        "cover",
                        "core-pc1",
                        "image/webp",
                        "kmqdb",
                        "cover.webp",
                        None,
                        8,
                        '"new-cover"',
                        "",
                    ),
                    (
                        "icon",
                        "core/icons/Stride",
                        "image/svg+xml",
                        "kmqdb",
                        "stride.svg",
                        b"stride",
                        6,
                        '"stride"',
                        "",
                    ),
                ),
            )
            calls = []

            def fetch(origin, row, timeout):
                calls.append((origin, row.kind, row.asset_key, timeout))
                return materializer.FetchedAsset(
                    body=b"newcover",
                    content_type="image/webp",
                    etag='"new-cover"',
                    last_modified="now",
                )

            count = materializer.materialize_cache_assets(
                cache,
                origin="https://ttrpg.example/",
                workers=2,
                timeout=4,
                fetcher=fetch,
            )
            self.assertEqual(count, 2)
            self.assertEqual(
                calls,
                [("https://ttrpg.example", "cover", "core-pc1", 4)],
            )
            self.assertEqual(materializer.verify_materialized_cache(cache), 2)
            with sqlite3.connect(cache) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT body,size,etag,last_modified FROM binary_assets "
                        "WHERE kind='cover'"
                    ).fetchone(),
                    (b"newcover", 8, '"new-cover"', "now"),
                )
            self.assertEqual(
                materializer.materialize_cache_assets(
                    cache,
                    origin="https://ttrpg.example",
                    fetcher=lambda *_args: self.fail("fetch should not run"),
                ),
                2,
            )

    def test_rejects_wrong_media_type_without_storing_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            create_cache(
                cache,
                (
                    (
                        "image",
                        "core/mc1/creature",
                        "image/webp",
                        "kmqdb",
                        "creature.webp",
                        None,
                        5,
                        '"new-image"',
                        "",
                    ),
                ),
            )
            with self.assertRaisesRegex(
                materializer.MaterializationError,
                "fetched asset is invalid",
            ):
                materializer.materialize_cache_assets(
                    cache,
                    origin="https://ttrpg.example",
                    fetcher=lambda *_args: materializer.FetchedAsset(
                        body=b"wrong",
                        content_type="text/html",
                        etag='"new-image"',
                        last_modified="now",
                    ),
                )
            with sqlite3.connect(cache) as connection:
                self.assertIsNone(
                    connection.execute(
                        "SELECT body FROM binary_assets"
                    ).fetchone()[0]
                )

    def test_rejects_size_or_etag_drift_without_storing_it(self) -> None:
        for fetched in (
            materializer.FetchedAsset(
                body=b"short",
                content_type="image/webp",
                etag='"expected"',
                last_modified="now",
            ),
            materializer.FetchedAsset(
                body=b"expected",
                content_type="image/webp",
                etag='"changed"',
                last_modified="now",
            ),
        ):
            with self.subTest(fetched=fetched):
                with tempfile.TemporaryDirectory() as directory:
                    cache = Path(directory) / "cache.db"
                    create_cache(
                        cache,
                        (
                            (
                                "cover",
                                "core-pc1",
                                "image/webp",
                                "kmqdb",
                                "cover.webp",
                                None,
                                8,
                                '"expected"',
                                "",
                            ),
                        ),
                    )
                    with self.assertRaisesRegex(
                        materializer.MaterializationError,
                        "fetched asset is invalid",
                    ):
                        materializer.materialize_cache_assets(
                            cache,
                            origin="https://ttrpg.example",
                            fetcher=lambda *_args: fetched,
                        )
                    with sqlite3.connect(cache) as connection:
                        self.assertIsNone(
                            connection.execute(
                                "SELECT body FROM binary_assets"
                            ).fetchone()[0]
                        )
    def test_asset_routes_are_exact_and_poison_keys_fail_closed(self) -> None:
        row = materializer.AssetRow(
            kind="icon",
            asset_key="core/gmc/Ornamental Border",
            content_type="image/svg+xml",
            size=1,
            etag="",
            last_modified="",
        )
        self.assertEqual(
            materializer.asset_url("https://ttrpg.example/", row),
            "https://ttrpg.example/.api/assets/pf2er/.static/icons/"
            "core/gmc/Ornamental%20Border",
        )
        with self.assertRaises(materializer.MaterializationError):
            materializer.asset_url(
                "https://ttrpg.example",
                materializer.AssetRow(
                    kind="image",
                    asset_key="core/../secret",
                    content_type="image/webp",
                    size=1,
                    etag="",
                    last_modified="",
                ),
            )

    def test_s3_fetcher_requires_the_exact_approved_bucket(self) -> None:
        # The real boto3 import is exercised by the deployment operator. This
        # unit boundary verifies the row fence before any request is issued.
        fetch = materializer.s3_fetcher(region="us-east-1")
        row = materializer.AssetRow(
            kind="image",
            asset_key="core/mc1/creature",
            content_type="image/webp",
            size=4,
            etag='"etag"',
            last_modified="",
            bucket="wrong-bucket",
            s3_key="image.webp",
        )
        with self.assertRaisesRegex(
            materializer.MaterializationError,
            "invalid S3 binding",
        ):
            fetch("s3://kmqdb", row, 10)

    def test_check_rejects_unmaterialized_and_active_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            create_cache(
                cache,
                (
                    (
                        "cover",
                        "core-pc1",
                        "image/webp",
                        "kmqdb",
                        "cover.webp",
                        None,
                        5,
                        '"cover"',
                        "",
                    ),
                ),
            )
            with self.assertRaisesRegex(
                materializer.MaterializationError,
                "unmaterialized",
            ):
                materializer.verify_materialized_cache(cache)
            (cache.parent / "cache.db-wal").write_bytes(b"")
            with self.assertRaisesRegex(
                materializer.MaterializationError,
                "sidecars",
            ):
                materializer.verify_materialized_cache(cache)


if __name__ == "__main__":
    unittest.main()

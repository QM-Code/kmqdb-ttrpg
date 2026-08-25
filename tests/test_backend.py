from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from subdomains.ttrpg import backend

GENERATION = "a" * 64
PACKAGE_PREFIX = "subdomains.ttrpg."


@dataclass(frozen=True)
class _StoredSourceRow:
    source_id: str
    payload: str
    toc: str


@dataclass(frozen=True)
class _StoredSectionRow:
    section_id: str
    source_id: str
    payload: str


def _compact_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _prepared_authority_rows(
    sources: dict[str, object],
    tocs: dict[str, object],
    sections: dict[str, dict[str, object]],
) -> tuple[
    tuple[_StoredSourceRow, ...],
    tuple[_StoredSectionRow, ...],
    str,
]:
    """Build the exact deployed-cache fixture without the authoring tool."""
    source_rows = tuple(
        _StoredSourceRow(
            source_id=source_id,
            payload=_compact_json(sources[source_id]),
            toc=_compact_json(tocs[source_id]),
        )
        for source_id in sorted(sources)
    )
    section_rows = tuple(
        _StoredSectionRow(
            section_id=section_id,
            source_id=str(sections[section_id]["source_id"]),
            payload=_compact_json(sections[section_id]),
        )
        for section_id in sorted(sections)
    )
    authority = {
        "schema": 1,
        "ruleset": "pf2er",
        "sources": [
            {
                "id": row.source_id,
                "payloadSha256": _sha256_text(row.payload),
                "tocSha256": _sha256_text(row.toc),
            }
            for row in source_rows
        ],
        "sections": [
            {
                "id": row.section_id,
                "sourceId": row.source_id,
                "payloadSha256": _sha256_text(row.payload),
                "contentSha256": _sha256_text(
                    str(json.loads(row.payload)["content"])
                ),
            }
            for row in section_rows
        ],
    }
    authority["digest"] = _sha256_text(_canonical_json(authority))
    return source_rows, section_rows, _canonical_json(authority)


class TtrpgBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name) / "cache.db"
        self.old_cache = os.environ.get("KMQDB_TTRPG_CACHE_DB")
        os.environ["KMQDB_TTRPG_CACHE_DB"] = str(self.cache)
        self.create_cache()
        with backend._AUTHORITY_STORE_LOCK:
            backend._AUTHORITY_STORE_STATE = None

    def tearDown(self) -> None:
        with backend._AUTHORITY_STORE_LOCK:
            backend._AUTHORITY_STORE_STATE = None
        if self.old_cache is None:
            os.environ.pop("KMQDB_TTRPG_CACHE_DB", None)
        else:
            os.environ["KMQDB_TTRPG_CACHE_DB"] = self.old_cache
        self.temp.cleanup()

    def create_cache(
        self,
        *,
        path: Path | None = None,
        generation: str = GENERATION,
        monster_name: str = "Monster Core",
        library_slug: str = "karmak",
    ) -> None:
        destination = path or self.cache
        toc = [
            {
                "label": "Front Matter",
                "locator": "1.1",
                "ref": "front",
                "section_id": "core-pc1:front",
                "content_path": [],
                "children": [
                    {
                        "label": "Credits",
                        "locator": "2.1",
                        "ref": "front",
                        "section_id": "core-pc1:front",
                        "content_path": ["Credits"],
                        "children": [],
                    }
                ],
            },
            {
                "label": "Classes",
                "locator": "40.1",
                "ref": "classes",
                "section_id": "core-pc1:classes",
                "content_path": [],
                "children": [],
            },
            {
                "label": "Back Matter",
                "locator": "460.1",
                "ref": "back",
                "section_id": "core-pc1:back",
                "content_path": [],
                "children": [],
            },
        ]
        source = {
            "id": "core-pc1",
            "name": "Player Core",
            "date": "2023-11-15.01",
            "pages": 464,
            "meta": {
                "description": "Forge Your Legend!",
                "images": {"count": 466, "page1": "002"},
            },
            "css": '@import url("https://fonts.example/font.css"); .x{background:url("/karmak/games/ttrpg/pf2er/.static/icons/x")}',
            "renderer": "/karmak/games/ttrpg/pf2er/.static/renderer.js",
            "vocab": "{}",
        }
        sections = [
            {
                "id": "core-pc1:front",
                "source_id": "core-pc1",
                "name": "Front Matter",
                "chapter": None,
                "chapter_id": "",
                "chapter_name": "",
                "section": "",
                "content": (
                    '{"image":"/karmak/games/ttrpg/pf2er/.static/'
                    'pages/core/pc1/x1024/002.webp"}'
                ),
            },
            {
                "id": "core-pc1:classes",
                "source_id": "core-pc1",
                "name": "Classes",
                "chapter": None,
                "chapter_id": "",
                "chapter_name": "",
                "section": "",
                "content": "{}",
            },
            {
                "id": "core-pc1:back",
                "source_id": "core-pc1",
                "name": "Back Matter",
                "chapter": None,
                "chapter_id": "",
                "chapter_name": "",
                "section": "",
                "content": "{}",
            },
        ]
        sources = {
            "core-gmc": {
                "id": "core-gmc",
                "name": "GM Core",
                "date": "2023-11-15.01",
            },
            "core-mc1": {
                "id": "core-mc1",
                "name": monster_name,
                "date": "2024-03-27.01",
            },
            "core-pc1": source,
        }
        tocs = {
            "core-gmc": [],
            "core-mc1": [],
            "core-pc1": toc,
        }
        (
            source_rows,
            section_rows,
            authority_snapshot,
        ) = _prepared_authority_rows(
            sources,
            tocs,
            {entry["id"]: entry for entry in sections},
        )
        with sqlite3.connect(destination) as connection:
            connection.executescript(
                """
                PRAGMA user_version = 3;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE bookshelf (singleton INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE presentation (singleton INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE presentation_assets (
                    kind TEXT NOT NULL,
                    asset_index INTEGER NOT NULL,
                    content_type TEXT NOT NULL,
                    body BLOB NOT NULL,
                    PRIMARY KEY (kind, asset_index)
                );
                CREATE TABLE sources (id TEXT PRIMARY KEY, payload TEXT NOT NULL, toc TEXT NOT NULL) WITHOUT ROWID;
                CREATE TABLE sections (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, payload TEXT NOT NULL) WITHOUT ROWID;
                CREATE TABLE authority_snapshot (
                    singleton INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                );
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
                );
                """
            )
            connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                [
                    (
                        "library_dataset",
                        f"{library_slug}/games/ttrpg/pf2er",
                    ),
                    ("ruleset", "pf2er"),
                    ("source_generation", generation),
                    ("upstream_origin", "http://library.example"),
                ],
            )
            connection.execute(
                "INSERT INTO bookshelf VALUES (1, ?)",
                (
                    json.dumps(
                        {
                            "schema": 2,
                            "generation": generation,
                            "dataset": (
                                f"{library_slug}/games/ttrpg/pf2er"
                            ),
                            "name": "Pathfinder 2E Remaster",
                            "description": "Books",
                            "entries": [
                                {
                                    "id": "core-pc1",
                                    "slug": "core-pc1",
                                    "name": "Player Core",
                                    "date": "2023-11-15.01",
                                    "kind": "source",
                                    "parent": "core",
                                }
                            ],
                        }
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO presentation VALUES (1, ?)",
                (
                    json.dumps(
                        {
                            "vocabulary": {"blocks": {}},
                            "renderer": "/karmak/games/ttrpg/pf2er/.static/example",
                            "stylesheets": [{"index": 0}],
                            "scripts": [{"index": 0}],
                        }
                    ),
                ),
            )
            connection.executemany(
                "INSERT INTO presentation_assets VALUES (?, ?, ?, ?)",
                [
                    (
                        "css",
                        0,
                        "text/css; charset=utf-8",
                        b'@import url("https://fonts.example/font.css"); .x{color:red}',
                    ),
                    ("js", 0, "application/javascript; charset=utf-8", b"window.cached = true;"),
                ],
            )
            connection.executemany(
                "INSERT INTO sources VALUES (?, ?, ?)",
                [
                    (row.source_id, row.payload, row.toc)
                    for row in source_rows
                ],
            )
            connection.executemany(
                "INSERT INTO sections VALUES (?, ?, ?)",
                [
                    (row.section_id, row.source_id, row.payload)
                    for row in section_rows
                ],
            )
            connection.execute(
                "INSERT INTO authority_snapshot VALUES (1, ?)",
                (authority_snapshot,),
            )
            connection.executemany(
                "INSERT INTO binary_assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("cover", "core-pc1", "image/webp", "kmqdb", "cover-key", b"cover", 5, '"cover"', ""),
                    ("icon", "actions/Free Action", "image/svg+xml", "kmqdb", "icon-key", b"<svg/>", 6, '"icon"', ""),
                    (
                        "icon",
                        "core/mc1/creatures/Goblin Warrior",
                        "image/png",
                        "kmqdb",
                        "goblin-warrior-icon-key",
                        b"goblin-icon",
                        11,
                        '"goblin-icon"',
                        "",
                    ),
                    (
                        "image",
                        "core/gmc/armor/adamantine-armor",
                        "image/webp",
                        "kmqdb",
                        "adamantine-armor-image-key",
                        b"armor-image",
                        11,
                        '"armor-image"',
                        "",
                    ),
                ],
            )

    def call(
        self,
        path: str,
        query: str = "",
        cookie: str = "",
        method: str = "GET",
        json_body: dict | None = None,
        raw_json_body: bytes | None = None,
        last_event_id: str = "",
        if_none_match: str = "",
        remote_addr: str = "127.0.0.1",
        application=None,
    ):
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "HTTP_HOST": "ttrpg.localhost:8011",
            "REMOTE_ADDR": remote_addr,
            "wsgi.url_scheme": "http",
        }
        if json_body is not None and raw_json_body is not None:
            raise ValueError("json_body and raw_json_body are mutually exclusive")
        if json_body is not None or raw_json_body is not None:
            body = (
                raw_json_body
                if raw_json_body is not None
                else json.dumps(
                    json_body,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
            environ.update(
                {
                    "CONTENT_TYPE": "application/json",
                    "CONTENT_LENGTH": str(len(body)),
                    "wsgi.input": io.BytesIO(body),
                }
            )
        if cookie:
            environ["HTTP_COOKIE"] = cookie
        if last_event_id:
            environ["HTTP_LAST_EVENT_ID"] = last_event_id
        if if_none_match:
            environ["HTTP_IF_NONE_MATCH"] = if_none_match
        body = b"".join(
            (application or backend.application)(environ, start_response)
        )
        return captured["status"], dict(captured["headers"]), body, environ

    def publication(self, cookie: str = "session=example"):
        status, headers, body, environ = self.call(
            "/.api/sources/core-pc1/publication",
            cookie=cookie,
        )
        return status, headers, json.loads(body), environ

    def test_removed_game_route_families_use_canonical_ttrpg_not_found(
        self,
    ) -> None:
        paths = (
            "/.api/engine/actions",
            "/.api/encounters/encounter-1",
            "/.api/pf2er/v1/encounter-hosts/host-1",
            "/.api/gladiator/v1/stables/stable-1",
            "/.api/gladiator/v2/operations/operation-1",
            "/.api/gladiator/v3/stores",
            "/.api/auth/api-credentials",
            "/.api/auth/api-credentials/credential-1/revoke",
        )
        for path in paths:
            for method in ("GET", "POST"):
                with self.subTest(path=path, method=method):
                    status, headers, body, _environ = self.call(
                        path,
                        method=method,
                        json_body={} if method == "POST" else None,
                    )
                    self.assertEqual(status, "404 Not Found")
                    self.assertEqual(
                        headers["Content-Type"],
                        "application/json; charset=utf-8",
                    )
                    self.assertEqual(
                        json.loads(body),
                        {"error": "route not found"},
                    )

    def test_backend_import_closure_excludes_game_and_old_rules_packages(
        self,
    ) -> None:
        imported_children = {
            module_name.removeprefix(PACKAGE_PREFIX).split(".", 1)[0]
            for module_name in sys.modules
            if module_name.startswith(PACKAGE_PREFIX)
        }
        self.assertIn("pf2er_compiler", imported_children)
        self.assertNotIn("rules_engine", imported_children)
        self.assertFalse(
            any(
                module_name == "kmqdbweb"
                or module_name.startswith("kmqdbweb.")
                for module_name in sys.modules
            )
        )
        self.assertNotIn(
            "kmqdbweb",
            Path(backend.__file__).read_text(encoding="utf-8"),
        )
        self.assertTrue(
            {
                "agent_protocol",
                "controller_context",
                "creature_bootstrap",
                "encounter_observer",
                "gladiator",
                "gladiator_connection",
                "gladiator_inventory",
                "gladiator_match",
                "gladiator_stable",
                "world_state",
            }.isdisjoint(imported_children),
            imported_children,
        )


    def test_publication_exposes_only_overview_front_and_back_matter(self) -> None:
        status, _headers, payload, environ = self.publication()
        self.assertEqual(status, "200 OK")
        self.assertEqual([node["label"] for node in payload["toc"]], ["Overview", "Front Matter", "Back Matter"])
        self.assertNotIn("dataset", payload)
        self.assertNotIn("presentation", payload)
        self.assertNotIn("images", payload["source"]["meta"])
        self.assertNotIn("css", payload["source"])
        self.assertEqual(payload["source"]["cover"], "/.api/sources/core-pc1/cover")
        self.assertTrue(backend.publication_scope_allows(environ, payload["scope"], "core-pc1", "1.1"))
        self.assertFalse(backend.publication_scope_allows(environ, payload["scope"], "core-pc1", "40.1"))

    def test_source_node_is_resolved_only_from_cached_rows(self) -> None:
        _status, _headers, publication, _environ = self.publication()
        status, _headers, body, _environ = self.call(
            "/.api/sources/core-pc1/node",
            "root=1.1&selected=2.1&scope=" + publication["scope"],
            cookie="session=example",
        )
        packet = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(packet["dataset"], ".api/assets/pf2er")
        self.assertEqual(packet["target"]["selected"]["content_path"], ["Credits"])
        self.assertNotIn("@import", packet["source"]["css"])
        self.assertIn("/.api/assets/pf2er/.static/icons/x", packet["source"]["css"])
        self.assertIn("/.api/assets/pf2er/.static/pages/", packet["content"]["section"]["content"])
        self.assertEqual(packet["presentation"]["stylesheets"], ["/.api/presentation/css/0"])
        self.assertNotIn(
            "karmak/games/ttrpg/pf2er",
            json.dumps(packet),
        )
        self.assertFalse(hasattr(backend, "upstream_request"))

    def test_text_cache_miss_returns_not_found_without_fallback(self) -> None:
        with sqlite3.connect(self.cache) as connection:
            connection.execute("DELETE FROM presentation_assets WHERE kind = 'css'")
        status, _headers, _body, _environ = self.call("/.api/presentation/css/0")
        self.assertEqual(status, "404 Not Found")
        self.assertFalse(hasattr(backend, "urlrequest"))

    def test_bookshelf_never_advertises_an_uncached_source(self) -> None:
        with sqlite3.connect(self.cache) as connection:
            connection.execute("DELETE FROM sources WHERE id = 'core-pc1'")
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(body)["entries"], [])

    def test_bookshelf_does_not_expose_private_ingest_generation(self) -> None:
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "200 OK")
        payload = json.loads(body)
        self.assertNotIn("generation", payload)
        self.assertNotIn("dataset", payload)

    def test_cache_dataset_is_owner_neutral_but_ruleset_scoped(self) -> None:
        with sqlite3.connect(self.cache) as connection:
            connection.execute(
                "UPDATE metadata SET value=? "
                "WHERE key='library_dataset'",
                ("another-owner/games/ttrpg/pf2er",),
            )
            bookshelf = json.loads(
                connection.execute(
                    "SELECT payload FROM bookshelf WHERE singleton=1"
                ).fetchone()[0]
            )
            bookshelf["dataset"] = "another-owner/games/ttrpg/pf2er"
            connection.execute(
                "UPDATE bookshelf SET payload=? WHERE singleton=1",
                (json.dumps(bookshelf),),
            )
        status, _headers, _body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "200 OK")

        with sqlite3.connect(self.cache) as connection:
            connection.execute(
                "UPDATE metadata SET value=? "
                "WHERE key='library_dataset'",
                ("another-owner/games/ttrpg/starfinder2e",),
            )
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"library dataset is invalid", body)

    def test_cache_open_requires_generation_and_authority_snapshot(self) -> None:
        with sqlite3.connect(self.cache) as connection:
            connection.execute(
                "UPDATE metadata SET value='not-a-generation' "
                "WHERE key='source_generation'"
            )
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"source generation is invalid", body)

        with sqlite3.connect(self.cache) as connection:
            connection.execute(
                "UPDATE metadata SET value=? "
                "WHERE key='source_generation'",
                (GENERATION,),
            )
            bookshelf = json.loads(
                connection.execute(
                    "SELECT payload FROM bookshelf WHERE singleton=1"
                ).fetchone()[0]
            )
            bookshelf["generation"] = "b" * 64
            connection.execute(
                "UPDATE bookshelf SET payload=? WHERE singleton=1",
                (json.dumps(bookshelf),),
            )
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"bookshelf receipt is invalid", body)

        with sqlite3.connect(self.cache) as connection:
            bookshelf["generation"] = GENERATION
            connection.execute(
                "UPDATE bookshelf SET payload=? WHERE singleton=1",
                (json.dumps(bookshelf),),
            )
            connection.execute("DELETE FROM authority_snapshot")
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"authority snapshot is invalid", body)

        with sqlite3.connect(self.cache) as connection:
            connection.execute(
                "INSERT INTO authority_snapshot VALUES (2, ?)",
                ("{}",),
            )
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"authority snapshot is invalid", body)

        with sqlite3.connect(self.cache) as connection:
            connection.execute("DELETE FROM authority_snapshot")
            connection.executemany(
                "INSERT INTO authority_snapshot VALUES (?, ?)",
                [(1, "{}"), (2, "{}")],
            )
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"authority snapshot is invalid", body)

    def test_cache_open_rejects_schema_and_bookshelf_receipt_drift(
        self,
    ) -> None:
        with sqlite3.connect(self.cache) as connection:
            connection.execute("PRAGMA user_version = 1")
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"schema is unsupported", body)

        with sqlite3.connect(self.cache) as connection:
            connection.execute(f"PRAGMA user_version = {backend.CACHE_SCHEMA_VERSION}")
            original = connection.execute(
                "SELECT payload FROM bookshelf WHERE singleton=1"
            ).fetchone()[0]

        for label, field, value in (
            ("schema", "schema", 1),
            ("boolean schema", "schema", True),
            ("dataset", "dataset", "library/wrong"),
            ("non-string dataset", "dataset", 2),
        ):
            with self.subTest(label=label):
                payload = json.loads(original)
                payload[field] = value
                with sqlite3.connect(self.cache) as connection:
                    connection.execute(
                        "UPDATE bookshelf SET payload=? "
                        "WHERE singleton=1",
                        (json.dumps(payload),),
                    )
                status, _headers, body, _environ = self.call(
                    "/.api/bookshelf"
                )
                self.assertEqual(
                    status,
                    "503 Service Unavailable",
                )
                self.assertIn(b"bookshelf receipt is invalid", body)
                with sqlite3.connect(self.cache) as connection:
                    connection.execute(
                        "UPDATE bookshelf SET payload=? "
                        "WHERE singleton=1",
                        (original,),
                    )

    def test_presentation_css_is_cached_and_external_imports_are_removed(self) -> None:
        status, headers, body, _environ = self.call("/.api/presentation/css/0")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "text/css; charset=utf-8")
        self.assertNotIn(b"@import", body)
        self.assertIn(b"color:red", body)

    def test_cached_source_assets_are_the_only_binary_routes(self) -> None:
        status, headers, body, _environ = self.call("/.api/sources/core-pc1/cover")
        self.assertEqual((status, headers["Content-Type"], body), ("200 OK", "image/webp", b"cover"))
        status, headers, body, _environ = self.call("/.api/assets/pf2er/.static/icons/actions/Free Action")
        self.assertEqual((status, headers["Content-Type"], body), ("200 OK", "image/svg+xml", b"<svg/>"))
        status, headers, body, _environ = self.call(
            "/.api/assets/pf2er/.static/icons/"
            "core/mc1/creatures/Goblin Warrior"
        )
        self.assertEqual(
            (status, headers["Content-Type"], body),
            ("200 OK", "image/png", b"goblin-icon"),
        )
        status, headers, body, _environ = self.call(
            "/.api/assets/pf2er/.static/images/"
            "core/gmc/armor/adamantine-armor"
        )
        self.assertEqual(
            (status, headers["Content-Type"], body),
            ("200 OK", "image/webp", b"armor-image"),
        )
        status, _headers, _body, _environ = self.call(
            "/.api/assets/pf2er/.static/pages/core/pc1/x1024/002.webp"
        )
        self.assertEqual(status, "404 Not Found")
        status, _headers, _body, _environ = self.call(
            "/.api/assets/pf2er/.static/icons/actions/Free Action.svg"
        )
        self.assertEqual(status, "404 Not Found")
        status, _headers, _body, _environ = self.call(
            "/.api/assets/pf2er/.static/images/"
            "core/gmc/armor/adamantine-armor.webp"
        )
        self.assertEqual(status, "404 Not Found")

    def test_cached_asset_etag_is_resolved_before_storage_fetch(self) -> None:
        with sqlite3.connect(self.cache) as connection:
            connection.execute(
                "UPDATE binary_assets SET body=NULL "
                "WHERE kind='icon' AND asset_key='actions/Free Action'"
            )

        status, headers, body, _environ = self.call(
            "/.api/assets/pf2er/.static/icons/actions/Free Action",
            if_none_match='W/"icon"',
        )

        self.assertEqual(status, "304 Not Modified")
        self.assertEqual(headers["ETag"], '"icon"')
        self.assertEqual(headers["Cache-Control"], "private, no-cache")
        self.assertEqual(body, b"")

        status, _headers, body, _environ = self.call(
            "/.api/assets/pf2er/.static/icons/actions/Free Action"
        )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(
            json.loads(body),
            {"error": "external asset service is unavailable"},
        )

        streamed_calls = []

        def asset_streamer(
            key,
            environ,
            *,
            bucket,
            cache_control,
            extra_headers,
        ):
            streamed_calls.append(
                (key, environ, bucket, cache_control, extra_headers)
            )
            return (
                "200 OK",
                [("Content-Type", "image/svg+xml")],
                [b"streamed-icon"],
            )

        configured_application = backend.create_application(
            asset_streamer=asset_streamer
        )
        with mock.patch.dict(
            os.environ,
            {"KMQDB_TTRPG_S3_BUCKET": ""},
        ):
            status, headers, body, environ = self.call(
                "/.api/assets/pf2er/.static/icons/actions/Free Action",
                application=configured_application,
            )
        self.assertEqual(
            (status, headers["Content-Type"], body),
            ("200 OK", "image/svg+xml", b"streamed-icon"),
        )
        self.assertEqual(
            streamed_calls,
            [
                (
                    "icon-key",
                    environ,
                    "kmqdb",
                    "private, no-cache",
                    (
                        ("Cross-Origin-Resource-Policy", "same-origin"),
                        (
                            "Content-Security-Policy",
                            "default-src 'none'; style-src 'unsafe-inline'; sandbox",
                        ),
                    ),
                )
            ],
        )


    def test_rule_node_requires_an_exact_deployed_target(self) -> None:
        with mock.patch.object(backend, "allowed_rule_targets", return_value=frozenset()):
            status, _headers, _body, _environ = self.call(
                "/.api/rules/source-node",
                "source=core-pc1&root=40.1&selected=40.1",
            )
        self.assertEqual(status, "404 Not Found")

        with mock.patch.object(
            backend,
            "allowed_rule_targets",
            return_value=frozenset({("core-pc1", "40.1")}),
        ):
            status, _headers, body, _environ = self.call(
                "/.api/rules/source-node",
                "source=core-pc1&root=40.1&selected=40.1",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(body)["content"]["section"]["id"], "core-pc1:classes")

    def test_spell_reference_route_resolves_the_live_rules_index(self) -> None:
        packet = {
            "schema": 1,
            "kind": "pf2er-indexed-spell-reference",
            "spell": {
                "id": "heal",
                "name": "Heal",
                "description": "You channel vital energy.",
                "source": {"sourceId": "core-pc1", "locator": "335.2"},
            },
        }
        with mock.patch.object(
            backend,
            "indexed_spell_reference",
            return_value=packet,
        ) as resolver:
            status, _headers, body, _environ = self.call(
                "/.api/rules/spell-reference",
                "spellId=heal&spellName=Heal",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(body), packet)
        self.assertEqual(resolver.call_args.args[1:], ("heal", "Heal"))

        status, _headers, _body, _environ = self.call(
            "/.api/rules/spell-reference",
            "spellId=Heal!&spellName=Heal",
        )
        self.assertEqual(status, "400 Bad Request")

    def test_missing_cache_is_a_service_error_not_an_upstream_request(self) -> None:
        os.environ["KMQDB_TTRPG_CACHE_DB"] = str(Path(self.temp.name) / "missing.db")
        status, _headers, body, _environ = self.call("/.api/bookshelf")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn(b"content cache is unavailable", body)

    def test_authority_store_loads_before_begin_on_the_engine_connection(
        self,
    ) -> None:
        store_class = (
            backend.source_authority_store.SourceAuthorityStore
        )
        original = store_class.from_connection
        observed = []

        def load(connection):
            observed.append((connection, connection.in_transaction))
            return original(connection)

        scope = ("core-gmc", "core-mc1", "core-pc1")
        with mock.patch.object(
            store_class,
            "from_connection",
            side_effect=load,
        ) as loader:
            with backend.authority_cache_connection() as (
                first_connection,
                first_store,
            ):
                self.assertTrue(first_connection.in_transaction)
                first_adapter = first_store.adapter_for(scope)
                generation = first_connection.execute(
                    "SELECT value FROM metadata "
                    "WHERE key='source_generation'"
                ).fetchone()[0]
                self.assertEqual(generation, GENERATION)

            with backend.authority_cache_connection() as (
                second_connection,
                second_store,
            ):
                self.assertTrue(second_connection.in_transaction)
                second_adapter = second_store.adapter_for(scope)

        loader.assert_called_once()
        self.assertEqual(observed, [(first_connection, False)])
        self.assertIs(first_store, second_store)
        self.assertIs(first_adapter, second_adapter)
        self.assertIsNot(first_connection, second_connection)

    def test_authority_store_refreshes_after_atomic_cache_replacement(
        self,
    ) -> None:
        scope = ("core-gmc", "core-mc1", "core-pc1")
        with backend.authority_cache_connection() as (
            first_connection,
            first_store,
        ):
            first_adapter = first_store.adapter_for(scope)
            self.assertEqual(
                first_connection.execute(
                    "SELECT value FROM metadata "
                    "WHERE key='source_generation'"
                ).fetchone()[0],
                GENERATION,
            )

        replacement = Path(self.temp.name) / "replacement.db"
        next_generation = "b" * 64
        self.create_cache(
            path=replacement,
            generation=next_generation,
        )
        os.replace(replacement, self.cache)

        with backend.authority_cache_connection() as (
            second_connection,
            second_store,
        ):
            second_adapter = second_store.adapter_for(scope)
            self.assertEqual(
                second_connection.execute(
                    "SELECT value FROM metadata "
                    "WHERE key='source_generation'"
                ).fetchone()[0],
                next_generation,
            )

        self.assertIsNot(first_store, second_store)
        self.assertIsNot(first_adapter, second_adapter)

    def test_authority_open_retries_replacement_between_stat_and_begin(
        self,
    ) -> None:
        replacement = Path(self.temp.name) / "replacement.db"
        next_generation = "b" * 64
        self.create_cache(
            path=replacement,
            generation=next_generation,
        )
        original_open = backend.open_cache_connection
        calls = []

        def raced_open(path):
            connection = original_open(path)
            calls.append(connection)
            if len(calls) == 1:
                os.replace(replacement, self.cache)
            return connection

        with mock.patch.object(
            backend,
            "open_cache_connection",
            side_effect=raced_open,
        ):
            with backend.authority_cache_connection() as (
                connection,
                store,
            ):
                self.assertEqual(
                    connection.execute(
                        "SELECT value FROM metadata "
                        "WHERE key='source_generation'"
                    ).fetchone()[0],
                    next_generation,
                )
                self.assertEqual(
                    store.source_ids,
                    ("core-gmc", "core-mc1", "core-pc1"),
                )

        self.assertEqual(len(calls), 2)

    def test_authority_store_reuse_rejects_an_atomic_aba_swap(
        self,
    ) -> None:
        scope = ("core-gmc", "core-mc1", "core-pc1")
        generation_b = "b" * 64
        cache_b = Path(self.temp.name) / "cache-b.db"
        held_a = Path(self.temp.name) / "held-a.db"
        held_b = Path(self.temp.name) / "held-b.db"
        self.create_cache(
            path=cache_b,
            generation=generation_b,
            monster_name="Monster Core B",
        )
        original_open = backend.open_cache_connection
        raced = False

        def aba_open(path):
            nonlocal raced
            if raced:
                return original_open(path)
            raced = True
            os.replace(self.cache, held_a)
            os.replace(cache_b, self.cache)
            connection = original_open(path)
            connection.execute("PRAGMA user_version").fetchone()
            os.replace(self.cache, held_b)
            os.replace(held_a, self.cache)
            return connection

        with mock.patch.object(
            backend,
            "open_cache_connection",
            side_effect=aba_open,
        ):
            with backend.authority_cache_connection() as (
                connection_b,
                store_b,
            ):
                generation = connection_b.execute(
                    "SELECT value FROM metadata "
                    "WHERE key='source_generation'"
                ).fetchone()[0]
                adapter_b = store_b.adapter_for(scope)
        self.assertEqual(generation, generation_b)

        with backend.authority_cache_connection() as (
            connection_a,
            store_a,
        ):
            generation = connection_a.execute(
                "SELECT value FROM metadata "
                "WHERE key='source_generation'"
            ).fetchone()[0]
            adapter_a = store_a.adapter_for(scope)
        self.assertEqual(generation, GENERATION)
        self.assertIsNot(store_a, store_b)
        self.assertIsNot(adapter_a, adapter_b)

    def test_authority_transaction_rejects_an_intervening_write(
        self,
    ) -> None:
        original_begin = backend.begin_validated_cache_snapshot
        mutated = False

        def mutate_then_begin(connection, **kwargs):
            nonlocal mutated
            if not mutated:
                mutated = True
                with sqlite3.connect(self.cache) as writer:
                    payload = writer.execute(
                        "SELECT payload FROM sources "
                        "WHERE id='core-mc1'"
                    ).fetchone()[0]
                    writer.execute(
                        "UPDATE sources SET payload=? "
                        "WHERE id='core-mc1'",
                        (payload + " ",),
                    )
            return original_begin(connection, **kwargs)

        with mock.patch.object(
            backend,
            "begin_validated_cache_snapshot",
            side_effect=mutate_then_begin,
        ):
            with self.assertRaisesRegex(
                backend.CacheUnavailable,
                "changed before use",
            ):
                with backend.authority_cache_connection():
                    self.fail("intervening write was accepted")
        self.assertTrue(mutated)

    def test_cache_close_closes_after_rollback_failure(self) -> None:
        connection = sqlite3.connect(":memory:", isolation_level=None)
        connection.execute("BEGIN")

        def deny_rollback(
            action,
            argument,
            _database,
            _trigger,
            _unused,
        ):
            if (
                action == sqlite3.SQLITE_TRANSACTION
                and argument == "ROLLBACK"
            ):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(deny_rollback)
        with self.assertRaises(sqlite3.DatabaseError):
            backend.close_cache_connection(connection)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")












if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
import sqlite3
import stat
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_library_cache.py"
SPEC = importlib.util.spec_from_file_location("kmqdb_ttrpg_cache_sync_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
sync = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync
SPEC.loader.exec_module(sync)

GENERATION = "a" * 64


def cache_values() -> dict:
    return {
        "origin": "https://kmqdb.example",
        "generation": GENERATION,
        "bookshelf": {
            "schema": 2,
            "dataset": sync.LIBRARY_DATASET,
            "generation": GENERATION,
            "entries": [{"id": "z-source"}, {"id": "a-source"}],
        },
        "presentation": {
            "vocabulary": {},
            "renderer": "",
            "stylesheets": [{"index": 0}],
            "scripts": [],
        },
        "presentation_assets": {
            ("css", 0): sync.BinaryPayload(
                b".book{}",
                "text/css; charset=utf-8",
            )
        },
        "sources": {
            "z-source": {"id": "z-source", "name": "Z Source"},
            "a-source": {"id": "a-source", "name": "A Source"},
        },
        "tocs": {
            "z-source": [
                {
                    "title": "Z",
                    "section_id": "z-source:front",
                    "children": [],
                }
            ],
            "a-source": [
                {
                    "title": "A",
                    "section_id": "a-source:front",
                    "children": [],
                }
            ],
        },
        "sections": {
            "z-source:front": {
                "id": "z-source:front",
                "source_id": "z-source",
                "content": '{"^.title":"Z"}',
            },
            "a-source:front": {
                "id": "a-source:front",
                "source_id": "a-source",
                "chapter_id": "a-source:chapter",
                "content": '{"^.title":"A λ"}',
            },
            "a-source:chapter": {
                "id": "a-source:chapter",
                "source_id": "a-source",
                "chapter_id": "",
                "content": '{"^.chapter":"A"}',
            },
        },
        "bucket": "kmqdb-cache",
        "binary_assets": [
            {
                "kind": "cover",
                "key": "a-source",
                "content_type": "image/webp",
                "s3_key": "approved-cover",
                "size": 42,
                "etag": '"etag"',
                "last_modified": "",
                "body": None,
            }
        ],
    }


class VerificationClient:
    origin = "https://kmqdb.example"

    def __init__(
        self,
        bookshelf: dict,
        *,
        on_request=None,
        failure: Exception | None = None,
    ) -> None:
        self.bookshelf = deepcopy(bookshelf)
        self.on_request = on_request
        self.failure = failure
        self.calls = []

    def get_json(self, operation, params=None):
        self.calls.append((operation, deepcopy(params)))
        if self.on_request is not None:
            self.on_request()
        if self.failure is not None:
            raise self.failure
        return deepcopy(self.bookshelf)


def verified_replace(
    destination: Path,
    values: dict,
    *,
    client: VerificationClient | None = None,
) -> VerificationClient:
    verifier = client or VerificationClient(values["bookshelf"])
    sync.replace_cache(
        destination,
        client=verifier,
        **values,
    )
    return verifier


def snapshot_payload(cache: Path) -> tuple[str, dict]:
    with sqlite3.connect(cache) as connection:
        payload = connection.execute(
            "SELECT payload FROM authority_snapshot WHERE singleton=1"
        ).fetchone()[0]
    return payload, json.loads(payload)


class CacheSyncTests(unittest.TestCase):
    def test_ruleset_selection_is_below_generic_ttrpg_membership_scope(self) -> None:
        previous = (
            sync.LIBRARY_SLUG,
            sync.RULESET_ID,
            sync.LIBRARY_DATASET,
            sync.LOCAL_RENDERER_DATASET,
        )
        try:
            sync.configure_ruleset(
                library_slug="karmak", ruleset_id="starfinder2e"
            )
            self.assertEqual(
                sync.LIBRARY_DATASET,
                "karmak/games/ttrpg/starfinder2e",
            )
            self.assertEqual(
                sync.LOCAL_RENDERER_DATASET,
                ".api/assets/starfinder2e",
            )
        finally:
            (
                sync.LIBRARY_SLUG,
                sync.RULESET_ID,
                sync.LIBRARY_DATASET,
                sync.LOCAL_RENDERER_DATASET,
            ) = previous

    def test_core_machine_credential_exchanges_for_refreshing_library_assertion(self) -> None:
        class Response:
            headers = {
                "Content-Type": "application/json",
                "Cache-Control": "no-store",
            }

            def __init__(self, endpoint):
                self.endpoint = endpoint

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return self.endpoint

            def read(self, _limit=None):
                return json.dumps(
                    {
                        "token_type": "urn:kmqdb:identity-token",
                        "identity_token": "signed-library-identity",
                        "expires_in": 120,
                    }
                ).encode("utf-8")

        class Opener:
            def __init__(self):
                self.requests = []

            def open(self, request, timeout=None):
                self.requests.append((request, timeout))
                return Response(request.full_url)

        with tempfile.TemporaryDirectory() as directory:
            credential_file = Path(directory) / "library-machine.credential"
            credential_file.write_text(
                "kmqdb.machine.v1." + "A" * 43 + "\n",
                encoding="utf-8",
            )
            credential_file.chmod(0o600)
            identity = sync.CoreMachineIdentity(
                "https://kmqdb.com", credential_file, timeout=8
            )
            opener = Opener()
            identity.opener = opener
            with mock.patch.object(sync.time, "monotonic", return_value=100.0):
                with ThreadPoolExecutor(max_workers=8) as executor:
                    headers = list(
                        executor.map(
                            lambda _index: identity.authorization_header(),
                            range(8),
                        )
                    )
                first, second = headers[:2]
        self.assertEqual(first, "Bearer signed-library-identity")
        self.assertEqual(second, first)
        self.assertEqual(headers, [first] * 8)
        self.assertEqual(len(opener.requests), 1)
        request, timeout = opener.requests[0]
        self.assertEqual(timeout, 8)
        payload = dict(
            sync.urlparse.parse_qsl(request.data.decode("ascii"))
        )
        self.assertEqual(
            payload,
            {
                "grant_type": sync.MACHINE_CREDENTIAL_GRANT_TYPE,
                "client_id": "library",
                "machine_credential": "kmqdb.machine.v1." + "A" * 43,
            },
        )

    def test_machine_account_accepts_exact_scoped_library_invitation(self) -> None:
        class Response:
            headers = {
                "Content-Type": "application/json",
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
            }

            def __init__(self, endpoint):
                self.endpoint = endpoint

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return self.endpoint

            def read(self, _limit=None):
                return json.dumps(
                    {
                        "schema": 1,
                        "library": {
                            "slug": "karmak",
                            "membershipRole": "reader",
                            "status": "active",
                            "hierarchyScopes": ["games/ttrpg"],
                        },
                    }
                ).encode("utf-8")

        class Opener:
            def __init__(self):
                self.requests = []

            def open(self, request, timeout=None):
                self.requests.append((request, timeout))
                return Response(request.full_url)

        client = sync.LibraryClient(
            "https://lib.kmqdb.com",
            authorization_provider=lambda: "Bearer short-lived-assertion",
            timeout=8,
        )
        opener = Opener()
        client.opener = opener
        token = "kmqdb.library.invite.v1." + "B" * 43
        payload = client.accept_invitation(token)
        self.assertEqual(payload["library"]["slug"], "karmak")
        request, timeout = opener.requests[0]
        self.assertEqual(timeout, 8)
        self.assertEqual(
            request.full_url,
            "https://lib.kmqdb.com/.api/library-invitations/accept",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer short-lived-assertion")
        self.assertEqual(json.loads(request.data), {"token": token})

    def test_atomic_cache_contains_text_rows_and_s3_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache" / "cache.db"
            sync.replace_cache(
                cache,
                client=VerificationClient(
                    {
                        "schema": 2,
                        "dataset": sync.LIBRARY_DATASET,
                        "generation": GENERATION,
                        "entries": [],
                    }
                ),
                origin="https://kmqdb.example",
                generation=GENERATION,
                bookshelf={
                    "schema": 2,
                    "dataset": sync.LIBRARY_DATASET,
                    "generation": GENERATION,
                    "entries": [],
                },
                presentation={"vocabulary": {}, "renderer": "", "stylesheets": [{"index": 0}], "scripts": []},
                presentation_assets={
                    ("css", 0): sync.BinaryPayload(b".book{}", "text/css; charset=utf-8")
                },
                sources={"core-pc1": {"id": "core-pc1", "name": "Player Core"}},
                tocs={"core-pc1": []},
                sections={
                    "core-pc1:front": {
                        "id": "core-pc1:front",
                        "source_id": "core-pc1",
                        "content": "{}",
                    }
                },
                bucket="kmqdb-cache",
                binary_assets=[
                    {
                        "kind": "cover",
                        "key": "core-pc1",
                        "content_type": "image/webp",
                        "s3_key": "approved-cover",
                        "size": 42,
                        "etag": '"etag"',
                        "last_modified": "",
                        "body": None,
                    }
                ],
            )
            self.assertTrue(cache.is_file())
            with sqlite3.connect(cache) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    3,
                )
                self.assertEqual(
                    connection.execute("SELECT value FROM metadata WHERE key='ruleset'").fetchone()[0],
                    "pf2er",
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT value FROM metadata "
                        "WHERE key='library_dataset'"
                    ).fetchone()[0],
                    "karmak/games/ttrpg/pf2er",
                )
                self.assertEqual(connection.execute("SELECT count(*) FROM sources").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT count(*) FROM sections").fetchone()[0], 1)
                row = connection.execute(
                    "SELECT bucket, s3_key, body FROM binary_assets"
                ).fetchone()
                self.assertEqual(row, ("kmqdb-cache", "approved-cover", None))
                self.assertEqual(
                    connection.execute(
                        "SELECT count(*) FROM authority_snapshot"
                    ).fetchone()[0],
                    1,
                )
                sync.verify_authority_snapshot(connection)
                self.assertEqual(
                    connection.execute("PRAGMA integrity_check").fetchone()[0],
                    "ok",
                )

    def test_snapshot_hashes_exact_stored_rows_and_is_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            values = cache_values()
            verified_replace(cache, values)
            payload, snapshot = snapshot_payload(cache)

            self.assertEqual(payload, sync.canonical_json(snapshot))
            self.assertEqual(snapshot["schema"], 1)
            self.assertEqual(snapshot["ruleset"], "pf2er")
            self.assertEqual(
                [item["id"] for item in snapshot["sources"]],
                ["a-source", "z-source"],
            )
            self.assertEqual(
                [item["id"] for item in snapshot["sections"]],
                [
                    "a-source:chapter",
                    "a-source:front",
                    "z-source:front",
                ],
            )
            digest_input = {
                key: snapshot[key]
                for key in ("schema", "ruleset", "sources", "sections")
            }
            self.assertEqual(
                snapshot["digest"],
                sync.text_sha256(sync.canonical_json(digest_input)),
            )

            with sqlite3.connect(cache) as connection:
                source_rows = {
                    row[0]: row[1:]
                    for row in connection.execute(
                        "SELECT id, payload, toc FROM sources"
                    )
                }
                section_rows = {
                    row[0]: row[1:]
                    for row in connection.execute(
                        "SELECT id, source_id, payload FROM sections"
                    )
                }
            source_manifest = {
                item["id"]: item for item in snapshot["sources"]
            }
            for source_id, (stored_payload, stored_toc) in source_rows.items():
                self.assertEqual(
                    source_manifest[source_id]["payloadSha256"],
                    sync.text_sha256(stored_payload),
                )
                self.assertEqual(
                    source_manifest[source_id]["tocSha256"],
                    sync.text_sha256(stored_toc),
                )
                self.assertEqual(
                    stored_payload,
                    sync.compact_json(values["sources"][source_id]),
                )
                self.assertEqual(
                    stored_toc,
                    sync.compact_json(values["tocs"][source_id]),
                )
            section_manifest = {
                item["id"]: item for item in snapshot["sections"]
            }
            for section_id, (source_id, stored_payload) in section_rows.items():
                decoded = json.loads(stored_payload)
                self.assertEqual(
                    section_manifest[section_id],
                    {
                        "id": section_id,
                        "sourceId": source_id,
                        "payloadSha256": sync.text_sha256(stored_payload),
                        "contentSha256": sync.text_sha256(decoded["content"]),
                    },
                )
                self.assertEqual(
                    stored_payload,
                    sync.compact_json(values["sections"][section_id]),
                )

    def test_snapshot_is_a_deterministic_fixed_point_for_mapping_order(
        self,
    ) -> None:
        first = cache_values()
        second = deepcopy(first)
        for field in ("sources", "tocs", "sections"):
            second[field] = dict(reversed(list(second[field].items())))

        first_rows = sync.prepared_authority_rows(
            first["sources"],
            first["tocs"],
            first["sections"],
        )
        second_rows = sync.prepared_authority_rows(
            second["sources"],
            second["tocs"],
            second["sections"],
        )
        self.assertEqual(first_rows, second_rows)
        self.assertEqual(
            first_rows[2],
            sync.authority_snapshot_payload(
                first_rows[0],
                first_rows[1],
            ),
        )

    def test_section_content_changes_snapshot_without_source_or_toc_changes(
        self,
    ) -> None:
        first = cache_values()
        second = deepcopy(first)
        second["sections"]["a-source:front"]["content"] = (
            '{"^.title":"A changed"}'
        )
        first_payload = json.loads(
            sync.prepared_authority_rows(
                first["sources"],
                first["tocs"],
                first["sections"],
            )[2]
        )
        second_payload = json.loads(
            sync.prepared_authority_rows(
                second["sources"],
                second["tocs"],
                second["sections"],
            )[2]
        )
        self.assertEqual(first_payload["sources"], second_payload["sources"])
        first_section = next(
            item
            for item in first_payload["sections"]
            if item["id"] == "a-source:front"
        )
        second_section = next(
            item
            for item in second_payload["sections"]
            if item["id"] == "a-source:front"
        )
        self.assertNotEqual(
            first_section["contentSha256"],
            second_section["contentSha256"],
        )
        self.assertNotEqual(
            first_section["payloadSha256"],
            second_section["payloadSha256"],
        )
        self.assertNotEqual(first_payload["digest"], second_payload["digest"])

    def test_invalid_ids_ownership_and_string_fields_fail_closed(self) -> None:
        mutations = {
            "missing ToC": lambda value: value["tocs"].pop("z-source"),
            "extra ToC": lambda value: value["tocs"].update(
                {"extra": []}
            ),
            "non-string source key": lambda value: value["sources"].update(
                {1: {"id": 1}}
            ),
            "invalid source id": lambda value: (
                value["sources"].__setitem__(
                    "bad/source",
                    value["sources"].pop("a-source"),
                ),
                value["tocs"].__setitem__(
                    "bad/source",
                    value["tocs"].pop("a-source"),
                ),
                value["sources"]["bad/source"].update(
                    {"id": "bad/source"}
                ),
            ),
            "wrong source payload id": lambda value: value["sources"][
                "a-source"
            ].update({"id": "z-source"}),
            "non-object source payload": lambda value: value[
                "sources"
            ].update({"a-source": []}),
            "non-array ToC": lambda value: value["tocs"].update(
                {"a-source": {}}
            ),
            "non-object ToC node": lambda value: value["tocs"][
                "a-source"
            ].__setitem__(0, []),
            "non-array ToC children": lambda value: value["tocs"][
                "a-source"
            ][0].update({"children": {}}),
            "non-string section key": lambda value: value[
                "sections"
            ].update({1: {}}),
            "wrong section payload id": lambda value: value["sections"][
                "a-source:front"
            ].update({"id": "other"}),
            "missing section payload id": lambda value: value["sections"][
                "a-source:front"
            ].pop("id"),
            "non-string section source": lambda value: value["sections"][
                "a-source:front"
            ].update({"source_id": 1}),
            "missing section source": lambda value: value["sections"][
                "a-source:front"
            ].pop("source_id"),
            "unknown section source": lambda value: value["sections"][
                "a-source:front"
            ].update({"source_id": "missing"}),
            "non-string section content": lambda value: value["sections"][
                "a-source:front"
            ].update({"content": {}}),
            "missing section content": lambda value: value["sections"][
                "a-source:front"
            ].pop("content"),
            "non-string ToC section id": lambda value: value["tocs"][
                "a-source"
            ][0].update({"section_id": 1}),
            "non-string ToC locator": lambda value: value["tocs"][
                "a-source"
            ][0].update({"locator": 1}),
            "unknown ToC section": lambda value: value["tocs"]["a-source"][
                0
            ].update({"section_id": "a-source:missing"}),
            "cross-source ToC binding": lambda value: value["tocs"][
                "a-source"
            ][0].update({"section_id": "z-source:front"}),
            "non-string chapter id": lambda value: value["sections"][
                "a-source:front"
            ].update({"chapter_id": 1}),
            "unknown chapter binding": lambda value: value["sections"][
                "a-source:front"
            ].update({"chapter_id": "a-source:missing"}),
            "cross-source chapter binding": lambda value: value["sections"][
                "a-source:front"
            ].update({"chapter_id": "z-source:front"}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                values = cache_values()
                mutate(values)
                with self.assertRaises(sync.SyncFailure):
                    sync.prepared_authority_rows(
                        values["sources"],
                        values["tocs"],
                        values["sections"],
                    )

    def test_duplicate_stored_row_identities_fail_closed(self) -> None:
        values = cache_values()
        source_rows, section_rows, _snapshot = (
            sync.prepared_authority_rows(
                values["sources"],
                values["tocs"],
                values["sections"],
            )
        )
        with self.assertRaises(sync.SyncFailure):
            sync.authority_snapshot_payload(
                (*source_rows, source_rows[0]),
                section_rows,
            )
        with self.assertRaises(sync.SyncFailure):
            sync.authority_snapshot_payload(
                source_rows,
                (*section_rows, section_rows[0]),
            )

    def test_duplicate_keys_and_nonfinite_numbers_fail_closed(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(nonfinite=repr(value)):
                inputs = cache_values()
                inputs["sources"]["a-source"]["invalid"] = value
                with self.assertRaises(sync.SyncFailure):
                    sync.prepared_authority_rows(
                        inputs["sources"],
                        inputs["tocs"],
                        inputs["sections"],
                    )

        values = cache_values()
        source_rows, section_rows, _snapshot = (
            sync.prepared_authority_rows(
                values["sources"],
                values["tocs"],
                values["sections"],
            )
        )
        source = source_rows[0]
        section = section_rows[0]
        adversarial_rows = (
            (
                (
                    sync.StoredSourceRow(
                        source.source_id,
                        '{"id":"a-source","id":"forged"}',
                        source.toc,
                    ),
                    *source_rows[1:],
                ),
                section_rows,
            ),
            (
                (
                    sync.StoredSourceRow(
                        source.source_id,
                        '{"id":"a-source","invalid":NaN}',
                        source.toc,
                    ),
                    *source_rows[1:],
                ),
                section_rows,
            ),
            (
                (
                    sync.StoredSourceRow(
                        source.source_id,
                        '{"id":"a-source","invalid":1e400}',
                        source.toc,
                    ),
                    *source_rows[1:],
                ),
                section_rows,
            ),
            (
                (
                    sync.StoredSourceRow(
                        source.source_id,
                        source.payload,
                        (
                            '[{"section_id":"a-source:front",'
                            '"section_id":"forged"}]'
                        ),
                    ),
                    *source_rows[1:],
                ),
                section_rows,
            ),
            (
                (
                    sync.StoredSourceRow(
                        source.source_id,
                        source.payload,
                        (
                            '[{"section_id":"a-source:front",'
                            '"invalid":1e400}]'
                        ),
                    ),
                    *source_rows[1:],
                ),
                section_rows,
            ),
            (
                source_rows,
                (
                    sync.StoredSectionRow(
                        section.section_id,
                        section.source_id,
                        (
                            '{"id":"a-source:chapter",'
                            '"source_id":"a-source",'
                            '"content":"first","content":"second"}'
                        ),
                    ),
                    *section_rows[1:],
                ),
            ),
            (
                source_rows,
                (
                    sync.StoredSectionRow(
                        section.section_id,
                        section.source_id,
                        (
                            '{"id":"a-source:chapter",'
                            '"source_id":"a-source",'
                            '"content":"safe","invalid":Infinity}'
                        ),
                    ),
                    *section_rows[1:],
                ),
            ),
            (
                source_rows,
                (
                    sync.StoredSectionRow(
                        section.section_id,
                        section.source_id,
                        (
                            '{"id":"a-source:chapter",'
                            '"source_id":"a-source",'
                            '"content":"safe","invalid":1e400}'
                        ),
                    ),
                    *section_rows[1:],
                ),
            ),
        )
        for index, rows in enumerate(adversarial_rows):
            with self.subTest(stored_row_case=index):
                with self.assertRaises(sync.SyncFailure):
                    sync.authority_snapshot_payload(*rows)

    def test_section_content_is_eagerly_validated_without_losing_duplicates(
        self,
    ) -> None:
        for content in ('{"key":1,"key":2}', ""):
            with self.subTest(valid_content=repr(content)):
                values = cache_values()
                values["sections"]["a-source:front"]["content"] = content
                _source_rows, _section_rows, snapshot = (
                    sync.prepared_authority_rows(
                        values["sources"],
                        values["tocs"],
                        values["sections"],
                    )
                )
                manifest = json.loads(snapshot)
                entry = next(
                    item
                    for item in manifest["sections"]
                    if item["id"] == "a-source:front"
                )
                self.assertEqual(
                    entry["contentSha256"],
                    sync.text_sha256(content),
                )

        invalid_content = (
            " ",
            "{",
            "[]",
            "null",
            '{"invalid":NaN}',
            '{"invalid":Infinity}',
            '{"invalid":-Infinity}',
            '{"invalid":1e400}',
            r'{"invalid":"\ud800"}',
            ('{"nested":' * 130) + "{}" + ("}" * 130),
        )
        for content in invalid_content:
            with self.subTest(invalid_content=repr(content)[:80]):
                values = cache_values()
                values["sections"]["a-source:front"]["content"] = content
                with self.assertRaises(sync.SyncFailure):
                    sync.prepared_authority_rows(
                        values["sources"],
                        values["tocs"],
                        values["sections"],
                    )

        with mock.patch.object(
            sync.source_content,
            "MAX_RAW_NODES",
            2,
        ):
            values = cache_values()
            values["sections"]["a-source:front"]["content"] = (
                '{"array":[null]}'
            )
            with self.assertRaises(sync.SyncFailure):
                sync.prepared_authority_rows(
                    values["sources"],
                    values["tocs"],
                    values["sections"],
                )

    def test_split_view_row_subclasses_fail_before_attribute_reads(self) -> None:
        values = cache_values()
        source_rows, section_rows, _snapshot = (
            sync.prepared_authority_rows(
                values["sources"],
                values["tocs"],
                values["sections"],
            )
        )

        class SplitSourceRow(sync.StoredSourceRow):
            def __init__(self, row):
                super().__init__(row.source_id, row.payload, row.toc)
                object.__setattr__(self, "_payload_reads", 0)
                object.__setattr__(self, "_authentic_payload", row.payload)
                object.__setattr__(
                    self,
                    "_forged_payload",
                    '{"id":"forged"}',
                )

            def __getattribute__(self, name):
                if name == "payload":
                    reads = object.__getattribute__(
                        self,
                        "_payload_reads",
                    )
                    object.__setattr__(self, "_payload_reads", reads + 1)
                    field = (
                        "_authentic_payload"
                        if reads == 0
                        else "_forged_payload"
                    )
                    return object.__getattribute__(self, field)
                return object.__getattribute__(self, name)

        class SplitSectionRow(sync.StoredSectionRow):
            def __init__(self, row):
                super().__init__(
                    row.section_id,
                    row.source_id,
                    row.payload,
                )
                object.__setattr__(self, "_source_reads", 0)
                object.__setattr__(
                    self,
                    "_authentic_source",
                    row.source_id,
                )

            def __getattribute__(self, name):
                if name == "source_id":
                    reads = object.__getattribute__(
                        self,
                        "_source_reads",
                    )
                    object.__setattr__(self, "_source_reads", reads + 1)
                    return (
                        object.__getattribute__(
                            self,
                            "_authentic_source",
                        )
                        if reads == 0
                        else "forged"
                    )
                return object.__getattribute__(self, name)

        split_source = SplitSourceRow(source_rows[0])
        with self.assertRaises(sync.SyncFailure):
            sync.authority_snapshot_payload(
                (split_source, *source_rows[1:]),
                section_rows,
            )
        self.assertEqual(
            object.__getattribute__(split_source, "_payload_reads"),
            0,
        )

        split_section = SplitSectionRow(section_rows[0])
        with self.assertRaises(sync.SyncFailure):
            sync.authority_snapshot_payload(
                source_rows,
                (split_section, *section_rows[1:]),
            )
        self.assertEqual(
            object.__getattribute__(split_section, "_source_reads"),
            0,
        )

    def test_authority_bounds_match_consumer_and_source_count_boundary(
        self,
    ) -> None:
        self.assertEqual(
            (
                sync.MAX_IDENTIFIER_BYTES,
                sync.MAX_MANIFEST_SOURCES,
                sync.MAX_MANIFEST_SECTIONS,
                sync.MAX_PATH_STEPS,
                sync.MAX_RAW_DEPTH,
                sync.MAX_RAW_NODES,
                sync.MAX_RAW_BYTES,
                sync.MAX_ROW_BYTES,
            ),
            (
                4_096,
                4_096,
                100_000,
                256,
                128,
                500_000,
                64 * 1024 * 1024,
                128 * 1024 * 1024,
            ),
        )
        self.assertEqual(
            (
                sync.MAX_IDENTIFIER_BYTES,
                sync.MAX_MANIFEST_SOURCES,
                sync.MAX_MANIFEST_SECTIONS,
                sync.MAX_PATH_STEPS,
                sync.MAX_RAW_DEPTH,
                sync.MAX_RAW_NODES,
                sync.MAX_RAW_BYTES,
                sync.MAX_ROW_BYTES,
            ),
            (
                sync.source_content.MAX_IDENTIFIER_BYTES,
                sync.source_content.MAX_MANIFEST_SOURCES,
                sync.source_content.MAX_MANIFEST_SECTIONS,
                sync.source_content.MAX_PATH_STEPS,
                sync.source_content.MAX_RAW_DEPTH,
                sync.source_content.MAX_RAW_NODES,
                sync.source_content.MAX_RAW_BYTES,
                sync.source_content.MAX_ROW_BYTES,
            ),
        )

        sources = {
            f"s{index:04d}": {"id": f"s{index:04d}"}
            for index in range(sync.MAX_MANIFEST_SOURCES)
        }
        tocs = {source_id: [] for source_id in sources}
        source_rows, section_rows, snapshot = (
            sync.prepared_authority_rows(sources, tocs, {})
        )
        self.assertEqual(len(source_rows), 4_096)
        self.assertEqual(section_rows, ())
        self.assertEqual(len(json.loads(snapshot)["sources"]), 4_096)

        sources["s4096"] = {"id": "s4096"}
        tocs["s4096"] = []
        with self.assertRaises(sync.SyncFailure):
            sync.prepared_authority_rows(sources, tocs, {})

    def test_identifier_utf8_byte_boundary_is_exact(self) -> None:
        maximum_source_id = "a" * sync.MAX_IDENTIFIER_BYTES
        source_rows, _section_rows, _snapshot = (
            sync.prepared_authority_rows(
                {maximum_source_id: {"id": maximum_source_id}},
                {maximum_source_id: []},
                {},
            )
        )
        self.assertEqual(source_rows[0].source_id, maximum_source_id)

        excessive_source_id = maximum_source_id + "a"
        with self.assertRaises(sync.SyncFailure):
            sync.prepared_authority_rows(
                {excessive_source_id: {"id": excessive_source_id}},
                {excessive_source_id: []},
                {},
            )

        maximum_section_id = "s:" + ("λ" * 2_047)
        self.assertEqual(
            len(maximum_section_id.encode("utf-8")),
            sync.MAX_IDENTIFIER_BYTES,
        )
        _source_rows, section_rows, _snapshot = (
            sync.prepared_authority_rows(
                {"s": {"id": "s"}},
                {"s": []},
                {
                    maximum_section_id: {
                        "id": maximum_section_id,
                        "source_id": "s",
                        "content": "{}",
                    }
                },
            )
        )
        self.assertEqual(section_rows[0].section_id, maximum_section_id)

        with self.assertRaises(sync.SyncFailure):
            sync.prepared_authority_rows(
                {"s": {"id": "s"}},
                {"s": []},
                {
                    maximum_section_id + "a": {
                        "id": maximum_section_id + "a",
                        "source_id": "s",
                        "content": "{}",
                    }
                },
            )

    def test_json_and_manifest_bounds_fail_closed_before_signing(self) -> None:
        with mock.patch.object(sync, "MAX_RAW_DEPTH", 2):
            self.assertEqual(
                sync.decoded_stored_json('[["ok"]]', "bounded JSON"),
                [["ok"]],
            )
            with self.assertRaises(sync.SyncFailure):
                sync.decoded_stored_json(
                    '[[["too deep"]]]',
                    "bounded JSON",
                )

        with mock.patch.object(sync, "MAX_RAW_NODES", 3):
            self.assertEqual(
                sync.decoded_stored_json("[1,2]", "bounded JSON"),
                [1, 2],
            )
        with mock.patch.object(sync, "MAX_RAW_NODES", 2):
            with self.assertRaises(sync.SyncFailure):
                sync.decoded_stored_json("[1,2]", "bounded JSON")

        with mock.patch.object(sync, "MAX_ROW_BYTES", 5):
            with self.assertRaises(sync.SyncFailure):
                sync.decoded_stored_json('"1234"', "bounded row")

        source_rows = (
            sync.StoredSourceRow("s", '{"id":"s"}', "[]"),
        )
        snapshot = sync.authority_snapshot_payload(source_rows, ())
        with mock.patch.object(
            sync,
            "MAX_ROW_BYTES",
            len(snapshot.encode("utf-8")) - 1,
        ):
            with self.assertRaises(sync.SyncFailure):
                sync.authority_snapshot_payload(source_rows, ())

        section = {
            "s:front": {
                "id": "s:front",
                "source_id": "s",
                "content": "1234",
            }
        }
        with mock.patch.object(
            sync.source_content,
            "MAX_RAW_BYTES",
            3,
        ):
            with self.assertRaises(sync.SyncFailure):
                sync.prepared_authority_rows(
                    {"s": {"id": "s"}},
                    {"s": []},
                    section,
                )

        with mock.patch.object(sync, "MAX_MANIFEST_SECTIONS", 1):
            with self.assertRaises(sync.SyncFailure):
                sync.prepared_authority_rows(
                    {"s": {"id": "s"}},
                    {"s": []},
                    {
                        "s:a": {
                            "id": "s:a",
                            "source_id": "s",
                            "content": "{}",
                        },
                        "s:b": {
                            "id": "s:b",
                            "source_id": "s",
                            "content": "{}",
                        },
                    },
                )

        deeply_nested = {}
        cursor = deeply_nested
        for _index in range(2_000):
            child = {}
            cursor["child"] = child
            cursor = child
        with self.assertRaises(sync.SyncFailure):
            sync.prepared_authority_rows(
                {"s": {"id": "s", "nested": deeply_nested}},
                {"s": []},
                {},
            )

    def test_toc_content_paths_enforce_exact_and_merged_bounds(self) -> None:
        sections = {
            "s:a": {
                "id": "s:a",
                "source_id": "s",
                "content": "{}",
            },
            "s:b": {
                "id": "s:b",
                "source_id": "s",
                "content": "{}",
            },
        }

        def prepare(toc):
            return sync.prepared_authority_rows(
                {"s": {"id": "s"}},
                {"s": toc},
                sections,
            )

        parent_path = [f"p{index}" for index in range(200)]
        child_path = [f"p{index}" for index in range(100, 256)]
        prepare(
            [
                {
                    "section_id": "s:a",
                    "content_path": parent_path,
                    "children": [{"content_path": child_path}],
                }
            ]
        )

        with self.assertRaises(sync.SyncFailure):
            prepare(
                [
                    {
                        "section_id": "s:a",
                        "content_path": parent_path,
                        "children": [
                            {
                                "content_path": [
                                    f"p{index}"
                                    for index in range(100, 257)
                                ]
                            }
                        ],
                    }
                ]
            )

        prepare(
            [
                {
                    "section_id": "s:a",
                    "content_path": [
                        f"a{index}"
                        for index in range(sync.MAX_PATH_STEPS)
                    ],
                    "children": [
                        {
                            "section_id": "s:b",
                            "locator": "",
                            "content_path": [
                                f"b{index}"
                                for index in range(sync.MAX_PATH_STEPS)
                            ],
                        }
                    ],
                }
            ]
        )

        with self.assertRaises(sync.SyncFailure):
            prepare(
                [
                    {
                        "section_id": "s:a",
                        "content_path": [
                            f"p{index}"
                            for index in range(
                                sync.MAX_PATH_STEPS + 1
                            )
                        ],
                    }
                ]
            )
        with self.assertRaises(sync.SyncFailure):
            prepare(
                [{"section_id": "s:a", "locator": " untrimmed "}]
            )

        maximum_part = "λ" * (sync.MAX_IDENTIFIER_BYTES // 2)
        prepare(
            [
                {
                    "section_id": "s:a",
                    "locator": "l" * sync.MAX_IDENTIFIER_BYTES,
                    "content_path": [" raw key ", maximum_part],
                }
            ]
        )
        for invalid_part in ("", "\x00", maximum_part + "a", 1):
            with self.subTest(invalid_part=repr(invalid_part)[:40]):
                with self.assertRaises(sync.SyncFailure):
                    prepare(
                        [
                            {
                                "section_id": "s:a",
                                "content_path": [invalid_part],
                            }
                        ]
                    )
        with self.assertRaises(sync.SyncFailure):
            prepare(
                [
                    {
                        "section_id": "s:a",
                        "locator": "l" * (
                            sync.MAX_IDENTIFIER_BYTES + 1
                        ),
                    }
                ]
            )

    def test_http_json_ingress_rejects_duplicates_and_nonfinite_numbers(
        self,
    ) -> None:
        client = sync.LibraryClient("https://kmqdb.example")
        adversarial_bodies = (
            b'{"source":{"name":"first","name":"second"}}',
            b'{"invalid":NaN}',
            b'{"invalid":Infinity}',
            b'{"invalid":-Infinity}',
            b'{"invalid":1e400}',
        )
        for body in adversarial_bodies:
            with self.subTest(body=body):
                with self.assertRaises(sync.SyncFailure):
                    client.decoded_json(
                        "test",
                        sync.BinaryPayload(body, "application/json"),
                    )

        class Response:
            headers = {"Content-Type": "application/json"}

            def __init__(self):
                self.read_limit = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, limit=None):
                self.read_limit = limit
                return b"x" * 6

        class Opener:
            def __init__(self, response):
                self.response = response

            def open(self, _request, timeout=None):
                return self.response

        response = Response()
        client.opener = Opener(response)
        with mock.patch.object(sync, "MAX_ROW_BYTES", 5):
            with self.assertRaisesRegex(
                sync.SyncFailure,
                "JSON byte bound",
            ):
                client.get_json("bounded")
        self.assertEqual(response.read_limit, 6)

    def test_generation_bound_http_requires_no_store_and_preserves_status(
        self,
    ) -> None:
        bookshelf = {
            "schema": 2,
            "dataset": sync.LIBRARY_DATASET,
            "generation": GENERATION,
            "entries": [],
        }

        class Response:
            def __init__(self, headers):
                self.headers = headers

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit=None):
                return json.dumps(bookshelf).encode("utf-8")

        class ResponseOpener:
            def __init__(self, headers):
                self.headers = headers

            def open(self, _request, timeout=None):
                return Response(self.headers)

        client = sync.LibraryClient("https://kmqdb.example")
        client.opener = ResponseOpener(
            {
                "Content-Type": "application/json",
                "Cache-Control": "private, no-store",
            }
        )
        self.assertEqual(
            sync.generation_from_payload(
                "bookshelf",
                client.get_json("bookshelf"),
            ),
            GENERATION,
        )
        client.opener = ResponseOpener(
            {"Content-Type": "application/json"}
        )
        with self.assertRaisesRegex(
            sync.SyncFailure,
            "Cache-Control: no-store",
        ):
            client.get_json("bookshelf")

        class ErrorOpener:
            def __init__(self, status):
                self.status = status

            def open(self, request, timeout=None):
                raise sync.urlerror.HTTPError(
                    request.full_url,
                    self.status,
                    "generation failure",
                    {
                        "Content-Type": "application/json",
                        "Cache-Control": "no-store",
                    },
                    io.BytesIO(b'{"error":"generation changed"}'),
                )

        for status in (400, 409):
            with self.subTest(status=status):
                client.opener = ErrorOpener(status)
                with self.assertRaises(
                    sync.LibraryRequestFailure
                ) as raised:
                    client.get_json("bookshelf")
                self.assertEqual(raised.exception.status_code, status)
                self.assertEqual(
                    raised.exception.library_message,
                    "generation changed",
                )

    def test_main_uses_one_generation_and_persists_its_receipt(self) -> None:
        class Client:
            origin = "https://kmqdb.example"

            def __init__(self):
                self.calls = []
                self.bookshelf = {
                    "schema": 2,
                    "dataset": sync.LIBRARY_DATASET,
                    "generation": GENERATION,
                    "name": "PF2ER",
                    "entries": [
                        {
                            "id": "core-mc1",
                            "name": "Monster Core",
                        }
                    ],
                }

            def get_json(self, operation, params=None):
                self.calls.append(("GET", operation, deepcopy(params)))
                if operation == "bookshelf":
                    return deepcopy(self.bookshelf)
                if operation == "source-publication":
                    return {
                        "schema": 2,
                        "dataset": sync.LIBRARY_DATASET,
                        "generation": GENERATION,
                        "source": {
                            "id": "core-mc1",
                            "name": "Monster Core",
                        },
                        "toc": [
                            {
                                "label": "Front Matter",
                                "section_id": "core-mc1:front",
                                "children": [],
                            }
                        ],
                    }
                raise AssertionError(operation)

            def post_json(self, operation, payload, params=None):
                self.calls.append(
                    (
                        "POST",
                        operation,
                        deepcopy(params),
                        deepcopy(payload),
                    )
                )
                return {
                    "schema": 2,
                    "dataset": sync.LIBRARY_DATASET,
                    "generation": GENERATION,
                    "missing": [],
                    "entries": [
                        {
                            "id": "core-mc1:front",
                            "source_id": "core-mc1",
                            "content": "{}",
                        }
                    ],
                }

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            credential_file = Path(directory) / "machine.credential"
            client = Client()
            identity = mock.Mock()
            with mock.patch.object(
                sync,
                "LibraryClient",
                return_value=client,
            ), mock.patch.object(
                sync,
                "CoreMachineIdentity",
                return_value=identity,
            ), mock.patch.object(
                sync,
                "fetch_presentation",
                return_value=(
                    {
                        "vocabulary": {},
                        "renderer": "",
                        "stylesheets": [],
                        "scripts": [],
                    },
                    {},
                ),
            ), mock.patch.object(
                sync,
                "fetch_binary_assets",
                return_value=("", []),
            ), mock.patch("builtins.print"):
                self.assertEqual(
                    sync.main(
                        [
                            "--origin",
                            "https://kmqdb.example",
                            "--cache",
                            str(cache),
                            "--machine-credential-file",
                            str(credential_file),
                        ]
                    ),
                    0,
                )

            self.assertEqual(
                client.calls,
                [
                    ("GET", "bookshelf", {"db": sync.LIBRARY_DB}),
                    (
                        "GET",
                        "source-publication",
                        {
                            "db": sync.LIBRARY_DB,
                            "source": "core-mc1",
                            "generation": GENERATION,
                        },
                    ),
                    (
                        "POST",
                        "source-sections",
                        {
                            "db": sync.LIBRARY_DB,
                            "generation": GENERATION,
                        },
                        {"ids": ["core-mc1:front"]},
                    ),
                    (
                        "GET",
                        "bookshelf",
                        {
                            "db": sync.LIBRARY_DB,
                            "generation": GENERATION,
                        },
                    ),
                ],
            )
            with sqlite3.connect(cache) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT value FROM metadata "
                        "WHERE key='source_generation'"
                    ).fetchone()[0],
                    GENERATION,
                )
                stored_bookshelf = json.loads(
                    connection.execute(
                        "SELECT payload FROM bookshelf WHERE singleton=1"
                    ).fetchone()[0]
                )
                self.assertEqual(
                    stored_bookshelf["generation"],
                    GENERATION,
                )

    def test_final_verifier_runs_after_build_and_before_atomic_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            verified_replace(cache, cache_values())
            before = cache.read_bytes()
            replacement = cache_values()
            replacement["sources"]["a-source"]["name"] = "Changed"
            verified = []

            def verifier():
                self.assertEqual(cache.read_bytes(), before)
                temporary = list(
                    cache.parent.glob(f".{cache.name}.*.tmp")
                )
                self.assertEqual(len(temporary), 1)
                with sqlite3.connect(temporary[0]) as connection:
                    sync.verify_authority_snapshot(connection)
                verified.append(True)

            client = VerificationClient(
                replacement["bookshelf"],
                on_request=verifier,
            )
            verified_replace(
                cache,
                replacement,
                client=client,
            )
            self.assertEqual(verified, [True])
            self.assertEqual(
                client.calls,
                [
                    (
                        "bookshelf",
                        {
                            "db": sync.LIBRARY_DB,
                            "generation": GENERATION,
                        },
                    )
                ],
            )
            self.assertNotEqual(cache.read_bytes(), before)

            accepted = cache.read_bytes()

            for status in (400, 409):
                with self.subTest(status=status):
                    conflict = VerificationClient(
                        cache_values()["bookshelf"],
                        failure=sync.LibraryRequestFailure(
                            "bookshelf",
                            status,
                            "source publication generation changed",
                        ),
                    )

                    with self.assertRaises(
                        sync.LibraryRequestFailure
                    ) as raised:
                        verified_replace(
                            cache,
                            cache_values(),
                            client=conflict,
                        )
                    self.assertEqual(
                        raised.exception.status_code,
                        status,
                    )
                    self.assertEqual(cache.read_bytes(), accepted)
                    self.assertEqual(
                        list(
                            cache.parent.glob(
                                f".{cache.name}.*.tmp"
                            )
                        ),
                        [],
                    )

    def test_generation_echo_and_final_bookshelf_fail_closed(self) -> None:
        initial = {
            "schema": 2,
            "dataset": sync.LIBRARY_DATASET,
            "generation": GENERATION,
            "entries": [{"id": "core-mc1"}],
        }

        class Client:
            origin = "https://kmqdb.example"

            def __init__(self, payload):
                self.payload = payload

            def get_json(self, _operation, params=None):
                return deepcopy(self.payload)

            def post_json(self, _operation, _payload, params=None):
                return deepcopy(self.payload)

        changed = {
            **initial,
            "generation": "b" * 64,
            "source": {"id": "core-mc1"},
            "toc": [],
            "missing": [],
            "entries": [],
        }
        with self.assertRaisesRegex(
            sync.SyncFailure,
            "changed generation",
        ):
            sync.fetch_publications(
                Client(changed),
                ["core-mc1"],
                GENERATION,
            )
        with self.assertRaisesRegex(
            sync.SyncFailure,
            "changed generation",
        ):
            sync.fetch_sections(
                Client(changed),
                {"core-mc1:front"},
                {"core-mc1"},
                GENERATION,
            )

        changed_bookshelf = deepcopy(initial)
        changed_bookshelf["entries"][0]["name"] = "Changed"
        with self.assertRaisesRegex(
            sync.SyncFailure,
            "bookshelf changed",
        ):
            sync.verify_final_bookshelf(
                Client(changed_bookshelf),
                GENERATION,
                initial,
            )

    def test_every_generation_response_requires_exact_envelope(self) -> None:
        valid = {
            "schema": 2,
            "dataset": sync.LIBRARY_DATASET,
            "generation": GENERATION,
        }

        class Client:
            origin = "https://kmqdb.example"

            def __init__(self, payload):
                self.payload = payload

            def get_json(self, _operation, params=None):
                return deepcopy(self.payload)

            def post_json(self, _operation, _payload, params=None):
                return deepcopy(self.payload)

        def initial(payload):
            sync.generation_from_payload("bookshelf", payload)

        def publication(payload):
            sync.fetch_publications(
                Client(
                    {
                        **payload,
                        "source": {"id": "core-mc1"},
                        "toc": [],
                    }
                ),
                ["core-mc1"],
                GENERATION,
            )

        def sections(payload):
            sync.fetch_sections(
                Client(
                    {
                        **payload,
                        "missing": [],
                        "entries": [
                            {
                                "id": "core-mc1:front",
                                "source_id": "core-mc1",
                                "content": "{}",
                            }
                        ],
                    }
                ),
                {"core-mc1:front"},
                {"core-mc1"},
                GENERATION,
            )

        def final(payload):
            initial_bookshelf = {
                **valid,
                "entries": [{"id": "core-mc1"}],
            }
            sync.verify_final_bookshelf(
                Client(
                    {
                        **payload,
                        "entries": [{"id": "core-mc1"}],
                    }
                ),
                GENERATION,
                initial_bookshelf,
            )

        mutations = {
            "missing schema": lambda value: value.pop("schema"),
            "wrong schema": lambda value: value.update({"schema": 1}),
            "boolean schema": lambda value: value.update(
                {"schema": True}
            ),
            "missing dataset": lambda value: value.pop("dataset"),
            "wrong dataset": lambda value: value.update(
                {"dataset": "library/wrong"}
            ),
            "non-string dataset": lambda value: value.update(
                {"dataset": 2}
            ),
            "missing generation": lambda value: value.pop(
                "generation"
            ),
            "malformed generation": lambda value: value.update(
                {"generation": "A" * 64}
            ),
            "non-string generation": lambda value: value.update(
                {"generation": 1}
            ),
        }
        for endpoint in (initial, publication, sections, final):
            for label, mutate in mutations.items():
                with self.subTest(
                    endpoint=endpoint.__name__,
                    mutation=label,
                ):
                    payload = deepcopy(valid)
                    mutate(payload)
                    with self.assertRaises(sync.SyncFailure):
                        endpoint(payload)

    def test_fetch_sections_rejects_duplicate_extra_missing_and_bad_ids(
        self,
    ) -> None:
        class Client:
            origin = "https://kmqdb.example"

            def __init__(self, response):
                self.response = response

            def post_json(self, _operation, _payload, params=None):
                return {
                    "schema": 2,
                    "dataset": sync.LIBRARY_DATASET,
                    "generation": GENERATION,
                    **deepcopy(self.response),
                }

        def entry(section_id="a", source_id="core-mc1", **extra):
            return {
                "id": section_id,
                "source_id": source_id,
                "content": "{}",
                **extra,
            }

        cases = (
            (
                "duplicate",
                {"a"},
                {"missing": [], "entries": [entry(), entry()]},
            ),
            (
                "extra",
                {"a"},
                {
                    "missing": [],
                    "entries": [entry(), entry("extra")],
                },
            ),
            (
                "missing",
                {"a", "b"},
                {"missing": [], "entries": [entry()]},
            ),
            (
                "non-string id",
                {"a"},
                {"missing": [], "entries": [entry(1)]},
            ),
            (
                "non-string source id",
                {"a"},
                {"missing": [], "entries": [entry(source_id=1)]},
            ),
            (
                "non-string chapter id",
                {"a"},
                {
                    "missing": [],
                    "entries": [entry(chapter_id=1)],
                },
            ),
        )
        for label, requested, response in cases:
            with self.subTest(label=label):
                with self.assertRaises(sync.SyncFailure):
                    sync.fetch_sections(
                        Client(response),
                        requested,
                        {"core-mc1"},
                        GENERATION,
                    )

    def test_fetch_sections_rejects_cross_batch_rows_and_discovers_chapters(
        self,
    ) -> None:
        class Client:
            origin = "https://kmqdb.example"

            def __init__(self, responder):
                self.responder = responder
                self.calls = []

            def post_json(self, _operation, payload, params=None):
                requested = list(payload["ids"])
                self.calls.append(requested)
                return {
                    "schema": 2,
                    "dataset": sync.LIBRARY_DATASET,
                    "generation": GENERATION,
                    **self.responder(requested, len(self.calls)),
                }

        def entry(section_id, *, chapter_id=None):
            result = {
                "id": section_id,
                "source_id": "core-mc1",
                "content": "{}",
            }
            if chapter_id is not None:
                result["chapter_id"] = chapter_id
            return result

        requested = {f"s{index:03d}" for index in range(201)}
        ordered = sorted(requested)

        def future_batch(first_batch, _call):
            return {
                "missing": [],
                "entries": [
                    *(entry(section_id) for section_id in first_batch),
                    entry(ordered[-1]),
                ],
            }

        with self.assertRaises(sync.SyncFailure):
            sync.fetch_sections(
                Client(future_batch),
                requested,
                {"core-mc1"},
                GENERATION,
            )

        first_returned = ordered[0]

        def prior_batch(batch, call):
            entries = [entry(section_id) for section_id in batch]
            if call == 2:
                entries.append(entry(first_returned))
            return {"missing": [], "entries": entries}

        with self.assertRaises(sync.SyncFailure):
            sync.fetch_sections(
                Client(prior_batch),
                requested,
                {"core-mc1"},
                GENERATION,
            )

        def chapters(batch, _call):
            return {
                "missing": [],
                "entries": [
                    entry(
                        section_id,
                        chapter_id=(
                            "chapter" if section_id == "front" else None
                        ),
                    )
                    for section_id in batch
                ],
            }

        client = Client(chapters)
        sections = sync.fetch_sections(
            client,
            {"front"},
            {"core-mc1"},
            GENERATION,
        )
        self.assertEqual(set(sections), {"front", "chapter"})
        self.assertEqual(client.calls, [["front"], ["chapter"]])

    def test_readback_verifier_detects_row_and_snapshot_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            verified_replace(cache, cache_values())
            with sqlite3.connect(cache) as connection:
                original_source = connection.execute(
                    "SELECT payload FROM sources WHERE id='a-source'"
                ).fetchone()[0]
                connection.execute(
                    "UPDATE sources SET payload=? WHERE id='a-source'",
                    (original_source + " ",),
                )
                with self.assertRaises(sync.SyncFailure):
                    sync.verify_authority_snapshot(connection)
                connection.rollback()

                original_section = connection.execute(
                    "SELECT payload FROM sections "
                    "WHERE id='a-source:front'"
                ).fetchone()[0]
                changed_section = json.loads(original_section)
                changed_section["content"] = "changed"
                connection.execute(
                    "UPDATE sections SET payload=? "
                    "WHERE id='a-source:front'",
                    (sync.compact_json(changed_section),),
                )
                with self.assertRaises(sync.SyncFailure):
                    sync.verify_authority_snapshot(connection)
                connection.rollback()

                original_snapshot = connection.execute(
                    "SELECT payload FROM authority_snapshot "
                    "WHERE singleton=1"
                ).fetchone()[0]
                changed_snapshot = json.loads(original_snapshot)
                changed_snapshot["digest"] = "0" * 64
                connection.execute(
                    "UPDATE authority_snapshot SET payload=? "
                    "WHERE singleton=1",
                    (sync.canonical_json(changed_snapshot),),
                )
                with self.assertRaises(sync.SyncFailure):
                    sync.verify_authority_snapshot(connection)
                connection.rollback()
                sync.verify_authority_snapshot(connection)

    def test_failed_replacement_preserves_active_cache_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            verified_replace(cache, cache_values())
            before = cache.read_bytes()
            invalid = cache_values()
            invalid["sections"]["a-source:front"]["content"] = None
            with self.assertRaises(sync.SyncFailure):
                verified_replace(cache, invalid)
            self.assertEqual(cache.read_bytes(), before)
            with sqlite3.connect(cache) as connection:
                sync.verify_authority_snapshot(connection)
            self.assertEqual(
                list(cache.parent.glob(f".{cache.name}.*.tmp")),
                [],
            )

    def test_replacement_preserves_deployed_cache_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            verified_replace(cache, cache_values())
            self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o640)
            cache.chmod(0o640)
            verified_replace(cache, cache_values())
            self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o640)

    def test_snapshot_remains_private_to_its_singleton_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.db"
            verified_replace(cache, cache_values())
            payload, snapshot = snapshot_payload(cache)
            digest = snapshot["digest"]
            with sqlite3.connect(cache) as connection:
                public_text = [
                    value
                    for query in (
                        "SELECT key || '=' || value FROM metadata",
                        "SELECT payload FROM bookshelf",
                        "SELECT payload FROM presentation",
                        "SELECT payload || toc FROM sources",
                        "SELECT payload FROM sections",
                    )
                    for (value,) in connection.execute(query)
                ]
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table'"
                    )
                }
            self.assertIn("authority_snapshot", tables)
            self.assertEqual(payload.count(digest), 1)
            self.assertTrue(
                all(
                    "authority_snapshot" not in value
                    and digest not in value
                    for value in public_text
                )
            )

    def test_source_normalization_drops_imageset_metadata_and_upstream_paths(self) -> None:
        source = sync.normalized_source(
            {
                "id": "core-pc1",
                "meta": {"description": "Book", "images": {"count": 400}},
                "css": (
                    '@import "https://fonts.example/font.css"; '
                    f'.x{{url(/{sync.LIBRARY_DATASET}/.static/icons/x)}}'
                ),
            },
            "core-pc1",
            "https://kmqdb.example",
        )
        self.assertNotIn("images", source["meta"])
        self.assertNotIn("@import", source["css"])
        self.assertIn("/.api/assets/pf2er/.static/icons/x", source["css"])
        self.assertNotIn(sync.LIBRARY_DATASET, json.dumps(source))

    def test_binary_manifest_rejects_non_allowlisted_kinds(self) -> None:
        class Client:
            def get_json(self, _operation, params=None):
                return {
                    "bucket": "kmqdb",
                    "assets": [
                        {
                            "kind": "page",
                            "key": "core/pc1/x1024/002.webp",
                            "content_type": "image/webp",
                            "s3_key": "forbidden-page",
                        }
                    ],
                }

        with self.assertRaises(sync.SyncFailure):
            sync.fetch_binary_assets(Client(), {"core-pc1"}, download=False, workers=1)

    def test_binary_manifest_keeps_only_selected_source_images(self) -> None:
        class Client:
            def get_json(self, _operation, params=None):
                return {
                    "bucket": "kmqdb",
                    "assets": [
                        {
                            "kind": "image",
                            "key": "core/pc1/equipment/example",
                            "content_type": "image/webp",
                            "s3_key": "selected-image",
                        },
                        {
                            "kind": "image",
                            "key": "core/mc1/creatures/example",
                            "content_type": "image/webp",
                            "s3_key": "unselected-image",
                        },
                        {
                            "kind": "icon",
                            "key": "actions/Free Action",
                            "content_type": "image/svg+xml",
                            "s3_key": "global-icon",
                        },
                    ],
                }

        bucket, assets = sync.fetch_binary_assets(
            Client(),
            {"core-pc1"},
            download=False,
            workers=1,
        )
        self.assertEqual(bucket, "kmqdb")
        self.assertEqual(
            [(asset["kind"], asset["key"]) for asset in assets],
            [
                ("image", "core/pc1/equipment/example"),
                ("icon", "actions/Free Action"),
            ],
        )

    def test_resource_image_download_uses_the_closed_source_image_route(self) -> None:
        class Client:
            def __init__(self):
                self.calls = []

            def get(self, operation, *, rest=(), params=None, accept=""):
                self.calls.append((operation, rest, accept))
                return sync.BinaryPayload(b"image", "image/webp")

        client = Client()
        payload = sync.binary_asset_download(
            client,
            {
                "kind": "image",
                "key": "core/gmc/armor/adamantine-armor",
                "size": 5,
            },
        )
        self.assertEqual(payload.body, b"image")
        self.assertEqual(
            client.calls,
            [
                (
                    "source-image",
                    ("core", "gmc", "armor", "adamantine-armor"),
                    "image/*",
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()

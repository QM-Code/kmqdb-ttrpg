#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import stat
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


TTRPG_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_ROOT = TTRPG_ROOT
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from subdomains.ttrpg import source_content


RULESET_ID = "pf2er"
LIBRARY_SLUG = "karmak"
LIBRARY_DATASET = "karmak/games/ttrpg/pf2er"
LIBRARY_DB = "sqlite"
LOCAL_RENDERER_DATASET = ".api/assets/pf2er"
CACHE_SCHEMA_VERSION = 3
AUTHORITY_SNAPSHOT_SCHEMA = 1
MAX_IDENTIFIER_BYTES = source_content.MAX_IDENTIFIER_BYTES
MAX_MANIFEST_SOURCES = source_content.MAX_MANIFEST_SOURCES
MAX_MANIFEST_SECTIONS = source_content.MAX_MANIFEST_SECTIONS
MAX_PATH_STEPS = source_content.MAX_PATH_STEPS
MAX_RAW_DEPTH = source_content.MAX_RAW_DEPTH
MAX_RAW_NODES = source_content.MAX_RAW_NODES
MAX_RAW_BYTES = source_content.MAX_RAW_BYTES
MAX_ROW_BYTES = source_content.MAX_ROW_BYTES
DEFAULT_CACHE_PATH = TTRPG_ROOT / "cache" / "cache.db"
CSS_IMPORT_RE = re.compile(
    r"@import\s+(?:url\(\s*(?:\"[^\"]*\"|'[^']*'|[^)]*)\s*\)|(?:\"[^\"]*\"|'[^']*'))[^;]*;",
    re.IGNORECASE,
)
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GENERATION_RE = re.compile(r"^[0-9a-f]{64}$")
RULESET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
LIBRARY_SLUG_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
MACHINE_CREDENTIAL_RE = re.compile(
    r"^kmqdb\.machine\.v1\.[A-Za-z0-9_-]{43}$"
)
LIBRARY_INVITATION_RE = re.compile(
    r"^kmqdb\.library\.invite\.v1\.[A-Za-z0-9_-]{43}$"
)
MACHINE_CREDENTIAL_GRANT_TYPE = (
    "urn:kmqdb:params:oauth:grant-type:machine-credential"
)
CORE_LIBRARY_CLIENT_ID = "library"
MAX_CORE_TOKEN_RESPONSE_BYTES = 64 * 1024
GENERATION_BOUND_OPERATIONS = frozenset(
    {"bookshelf", "source-publication", "source-sections"}
)
SEALED_RENDERER_INTERFACE_MARKER = "KMQDB_SEALED_RENDERER_INTERFACE_V1"
SEALED_RENDERER_BUNDLE_MARKER = "KMQDB_SEALED_RENDERER_BUNDLE_V1"
SCHEMA_SQL = f"""
PRAGMA user_version = {CACHE_SCHEMA_VERSION};
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE bookshelf (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    payload TEXT NOT NULL
);
CREATE TABLE presentation (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    payload TEXT NOT NULL
);
CREATE TABLE presentation_assets (
    kind TEXT NOT NULL CHECK (kind IN ('css', 'js')),
    asset_index INTEGER NOT NULL CHECK (asset_index >= 0),
    content_type TEXT NOT NULL,
    body BLOB NOT NULL,
    PRIMARY KEY (kind, asset_index)
) WITHOUT ROWID;
CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    toc TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE sections (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    payload TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX sections_source_id ON sections(source_id);
CREATE TABLE authority_snapshot (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    payload TEXT NOT NULL
);
CREATE TABLE binary_assets (
    kind TEXT NOT NULL CHECK (kind IN ('cover', 'icon', 'image')),
    asset_key TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK (content_type LIKE 'image/%'),
    bucket TEXT NOT NULL DEFAULT '',
    s3_key TEXT NOT NULL DEFAULT '',
    body BLOB,
    size INTEGER NOT NULL DEFAULT 0 CHECK (size >= 0),
    etag TEXT NOT NULL DEFAULT '',
    last_modified TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (kind, asset_key),
    CHECK (body IS NOT NULL OR s3_key <> '')
) WITHOUT ROWID;
"""


class SyncFailure(Exception):
    pass


class LibraryRequestFailure(SyncFailure):
    def __init__(
        self,
        operation: str,
        status_code: int,
        message: str,
    ) -> None:
        self.operation = operation
        self.status_code = status_code
        self.library_message = message
        super().__init__(
            f"library {operation} request failed "
            f"({status_code}): {message}"
        )


class NoRedirectHandler(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, _request, _file_pointer, _code, _message, _headers, _new_url):
        return None


def configure_ruleset(*, library_slug: str, ruleset_id: str) -> None:
    global RULESET_ID, LIBRARY_SLUG, LIBRARY_DATASET, LOCAL_RENDERER_DATASET
    if (
        type(library_slug) is not str
        or LIBRARY_SLUG_RE.fullmatch(library_slug) is None
        or type(ruleset_id) is not str
        or RULESET_ID_RE.fullmatch(ruleset_id) is None
    ):
        raise SyncFailure("library slug or TTRPG ruleset is invalid")
    LIBRARY_SLUG = library_slug
    RULESET_ID = ruleset_id
    LIBRARY_DATASET = f"{library_slug}/games/ttrpg/{ruleset_id}"
    LOCAL_RENDERER_DATASET = f".api/assets/{ruleset_id}"


def read_machine_credential(path: Path) -> str:
    candidate = Path(path)
    if (
        not candidate.is_absolute()
        or candidate.is_symlink()
        or not candidate.is_file()
        or candidate.stat().st_mode & 0o077
        or candidate.stat().st_size > 1024
    ):
        raise SyncFailure("Core machine credential file is invalid")
    try:
        credential = candidate.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as failure:
        raise SyncFailure("Core machine credential file is unavailable") from failure
    if MACHINE_CREDENTIAL_RE.fullmatch(credential) is None:
        raise SyncFailure("Core machine credential file is invalid")
    return credential


def read_library_invitation(path: Path) -> str:
    candidate = Path(path)
    if (
        not candidate.is_absolute()
        or candidate.is_symlink()
        or not candidate.is_file()
        or candidate.stat().st_mode & 0o077
        or candidate.stat().st_size > 1024
    ):
        raise SyncFailure("Library invitation file is invalid")
    try:
        invitation = candidate.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as failure:
        raise SyncFailure("Library invitation file is unavailable") from failure
    if LIBRARY_INVITATION_RE.fullmatch(invitation) is None:
        raise SyncFailure("Library invitation file is invalid")
    return invitation


class CoreMachineIdentity:
    def __init__(
        self,
        origin: str,
        credential_file: Path,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.origin = clean_origin(origin)
        self.credential = read_machine_credential(credential_file)
        self.timeout = timeout
        self.opener = urlrequest.build_opener(NoRedirectHandler())
        self._assertion = ""
        self._refresh_at = 0.0
        self._lock = threading.Lock()

    def authorization_header(self) -> str:
        with self._lock:
            return self._authorization_header_locked()

    def _authorization_header_locked(self) -> str:
        if self._assertion and time.monotonic() < self._refresh_at:
            return "Bearer " + self._assertion
        endpoint = self.origin + "/.api/auth/sso/token"
        body = urlparse.urlencode(
            {
                "grant_type": MACHINE_CREDENTIAL_GRANT_TYPE,
                "client_id": CORE_LIBRARY_CLIENT_ID,
                "machine_credential": self.credential,
            }
        ).encode("ascii")
        request = urlrequest.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "KMQDB-TTRPG-Core-Identity/1",
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.geturl() != endpoint:
                    raise SyncFailure(
                        "Core machine credential exchange redirected"
                    )
                raw = response.read(MAX_CORE_TOKEN_RESPONSE_BYTES + 1)
                headers = response_headers(response.headers)
        except urlerror.HTTPError as failure:
            failure.read(MAX_CORE_TOKEN_RESPONSE_BYTES + 1)
            raise SyncFailure("Core machine credential was rejected") from failure
        except (urlerror.URLError, TimeoutError, OSError) as failure:
            raise SyncFailure("Core identity service is unavailable") from failure
        if len(raw) > MAX_CORE_TOKEN_RESPONSE_BYTES:
            raise SyncFailure("Core machine token response is too large")
        require_no_store("machine-token", headers)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as failure:
            raise SyncFailure("Core machine token response is invalid") from failure
        if (
            type(payload) is not dict
            or set(payload) != {"token_type", "identity_token", "expires_in"}
            or payload["token_type"] != "urn:kmqdb:identity-token"
            or type(payload["identity_token"]) is not str
            or not payload["identity_token"]
            or type(payload["expires_in"]) is not int
            or not 1 <= payload["expires_in"] <= 300
        ):
            raise SyncFailure("Core machine token response is invalid")
        self._assertion = payload["identity_token"]
        self._refresh_at = time.monotonic() + max(
            1, payload["expires_in"] - 30
        )
        return "Bearer " + self._assertion


def compact_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def utf8_size(value: str, label: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as failure:
        raise SyncFailure(f"{label} is not valid UTF-8 text") from failure


def validated_json_value(
    value: object,
    label: str,
    *,
    depth: int = 0,
    counter: list[int] | None = None,
) -> object:
    if counter is None:
        counter = [0]
    if depth > MAX_RAW_DEPTH:
        raise SyncFailure(f"{label} exceeds its JSON depth bound")
    counter[0] += 1
    if counter[0] > MAX_RAW_NODES:
        raise SyncFailure(f"{label} exceeds its JSON node bound")

    value_type = type(value)
    if value_type is dict:
        result = {}
        for key, item in dict.items(value):
            if type(key) is not str:
                raise SyncFailure(
                    f"{label} contains a non-string object key"
                )
            result[key] = validated_json_value(
                item,
                label,
                depth=depth + 1,
                counter=counter,
            )
        return result
    if value_type is list:
        return [
            validated_json_value(
                item,
                label,
                depth=depth + 1,
                counter=counter,
            )
            for item in value
        ]
    if value is None or value_type in {bool, int, str}:
        return value
    if value_type is float:
        if not math.isfinite(value):
            raise SyncFailure(f"{label} contains a non-finite number")
        return value
    raise SyncFailure(
        f"{label} contains a non-JSON value: {value_type.__name__}"
    )


def canonical_json(value: object) -> str:
    try:
        encoded = json.dumps(
            validated_json_value(value, "canonical JSON"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as failure:
        raise SyncFailure("value is not canonical JSON") from failure
    if utf8_size(encoded, "canonical JSON") > MAX_ROW_BYTES:
        raise SyncFailure("canonical JSON exceeds its byte bound")
    return encoded


def text_sha256(value: str) -> str:
    if type(value) is not str:
        raise SyncFailure("authority snapshot hash input must be a string")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredSourceRow:
    source_id: str
    payload: str
    toc: str


@dataclass(frozen=True)
class StoredSectionRow:
    section_id: str
    source_id: str
    payload: str


def require_identifier(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
    ):
        raise SyncFailure(f"{label} must be a non-empty, trimmed string")
    if utf8_size(value, label) > MAX_IDENTIFIER_BYTES:
        raise SyncFailure(f"{label} exceeds its byte bound")
    return value


def decoded_stored_json(value: object, label: str) -> object:
    if type(value) is not str:
        raise SyncFailure(f"{label} must be a string")
    if utf8_size(value, label) > MAX_ROW_BYTES:
        raise SyncFailure(f"{label} exceeds its byte bound")

    def strict_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, item in pairs:
            if key in result:
                raise SyncFailure(
                    f"{label} contains a duplicate object key: {key}"
                )
            result[key] = item
        return result

    def reject_nonfinite(constant: str) -> object:
        raise SyncFailure(
            f"{label} contains a non-finite number: {constant}"
        )

    def finite_float(encoded: str) -> float:
        result = float(encoded)
        if not math.isfinite(result):
            raise SyncFailure(
                f"{label} contains a number outside the finite range"
            )
        return result

    try:
        parsed = json.loads(
            value,
            object_pairs_hook=strict_object,
            parse_constant=reject_nonfinite,
            parse_float=finite_float,
        )
    except SyncFailure:
        raise
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ) as failure:
        raise SyncFailure(f"{label} is not valid JSON") from failure
    return validated_json_value(parsed, label)


def require_path_part(value: object, label: str) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise SyncFailure(f"{label} must be a non-empty string")
    if utf8_size(value, label) > MAX_IDENTIFIER_BYTES:
        raise SyncFailure(f"{label} exceeds its byte bound")
    return value


def merged_content_path(
    current: tuple[str, ...],
    candidate: tuple[str, ...],
    label: str,
) -> tuple[str, ...]:
    overlap_limit = min(len(current), len(candidate))
    overlap = 0
    for size in range(overlap_limit, 0, -1):
        if current[-size:] == candidate[:size]:
            overlap = size
            break
    merged = (*current, *candidate[overlap:])
    if len(merged) > MAX_PATH_STEPS:
        raise SyncFailure(f"{label} exceeds its merged path-step bound")
    return merged


def toc_references(
    nodes: object,
    *,
    source_id: str,
    label: str,
    counter: list[int] | None = None,
    active_section: str | None = None,
    active_path: tuple[str, ...] = (),
) -> list[tuple[str, str]]:
    if type(nodes) is not list:
        raise SyncFailure(f"{label} must be an array")
    if counter is None:
        counter = [0]
    references: list[tuple[str, str]] = []
    for index, node in enumerate(nodes):
        counter[0] += 1
        if counter[0] > MAX_RAW_NODES:
            raise SyncFailure(f"{label} exceeds its ToC node bound")
        node_label = f"{label}[{index}]"
        if type(node) is not dict:
            raise SyncFailure(f"{node_label} must be an object")
        node_section = active_section
        node_path = active_path
        if "section_id" in node:
            section_id = require_identifier(
                node["section_id"],
                f"{node_label}.section_id",
            )
            references.append((source_id, section_id))
            if section_id != active_section:
                node_path = ()
            node_section = section_id
        if "locator" in node:
            locator = node["locator"]
            if type(locator) is not str:
                raise SyncFailure(
                    f"{node_label}.locator must be a string"
                )
            if locator:
                require_identifier(
                    locator,
                    f"{node_label}.locator",
                )
        content_path = node.get("content_path", [])
        if type(content_path) is not list:
            raise SyncFailure(f"{node_label}.content_path must be an array")
        if len(content_path) > MAX_PATH_STEPS:
            raise SyncFailure(
                f"{node_label}.content_path exceeds its path-step bound"
            )
        exact_content_path = tuple(
            require_path_part(
                part,
                f"{node_label}.content_path[{part_index}]",
            )
            for part_index, part in enumerate(content_path)
        )
        if node_section is not None and exact_content_path:
            node_path = merged_content_path(
                node_path,
                exact_content_path,
                f"{node_label}.content_path",
            )
        if "children" in node:
            references.extend(
                toc_references(
                    node["children"],
                    source_id=source_id,
                    label=f"{node_label}.children",
                    counter=counter,
                    active_section=node_section,
                    active_path=node_path,
                )
            )
    return references


def authority_snapshot_payload(
    source_rows: object,
    section_rows: object,
) -> str:
    if type(source_rows) not in {list, tuple}:
        raise SyncFailure("authority snapshot source rows must be ordered")
    if type(section_rows) not in {list, tuple}:
        raise SyncFailure("authority snapshot section rows must be ordered")
    if len(source_rows) > MAX_MANIFEST_SOURCES:
        raise SyncFailure(
            "authority snapshot exceeds its source-count bound"
        )
    if len(section_rows) > MAX_MANIFEST_SECTIONS:
        raise SyncFailure(
            "authority snapshot exceeds its section-count bound"
        )

    sources_by_id: dict[str, StoredSourceRow] = {}
    source_entries = []
    toc_bindings: list[tuple[str, str]] = []
    for index, row in enumerate(source_rows):
        if type(row) is not StoredSourceRow:
            raise SyncFailure(
                f"authority snapshot source row {index} is invalid"
            )
        source_id = require_identifier(
            row.source_id,
            f"authority snapshot source row {index} id",
        )
        if SOURCE_ID_RE.fullmatch(source_id) is None:
            raise SyncFailure(
                f"authority snapshot source id is invalid: {source_id}"
            )
        if source_id in sources_by_id:
            raise SyncFailure(
                f"authority snapshot source id is duplicated: {source_id}"
            )
        source_payload = decoded_stored_json(
            row.payload,
            f"authority snapshot source {source_id} payload",
        )
        if (
            type(source_payload) is not dict
            or type(source_payload.get("id")) is not str
            or source_payload["id"] != source_id
        ):
            raise SyncFailure(
                f"authority snapshot source payload has the wrong id: "
                f"{source_id}"
            )
        toc = decoded_stored_json(
            row.toc,
            f"authority snapshot source {source_id} ToC",
        )
        toc_bindings.extend(
            toc_references(
                toc,
                source_id=source_id,
                label=f"authority snapshot source {source_id} ToC",
            )
        )
        sources_by_id[source_id] = row
        source_entries.append(
            {
                "id": source_id,
                "payloadSha256": text_sha256(row.payload),
                "tocSha256": text_sha256(row.toc),
            }
        )

    sections_by_id: dict[str, StoredSectionRow] = {}
    section_entries = []
    chapter_bindings: list[tuple[str, str]] = []
    for index, row in enumerate(section_rows):
        if type(row) is not StoredSectionRow:
            raise SyncFailure(
                f"authority snapshot section row {index} is invalid"
            )
        section_id = require_identifier(
            row.section_id,
            f"authority snapshot section row {index} id",
        )
        source_id = require_identifier(
            row.source_id,
            f"authority snapshot section {section_id} source id",
        )
        if section_id in sections_by_id:
            raise SyncFailure(
                f"authority snapshot section id is duplicated: {section_id}"
            )
        if source_id not in sources_by_id:
            raise SyncFailure(
                f"authority snapshot section has an unknown source: "
                f"{section_id}"
            )
        section_payload = decoded_stored_json(
            row.payload,
            f"authority snapshot section {section_id} payload",
        )
        if type(section_payload) is not dict:
            raise SyncFailure(
                f"authority snapshot section payload is not an object: "
                f"{section_id}"
            )
        if (
            type(section_payload.get("id")) is not str
            or section_payload["id"] != section_id
        ):
            raise SyncFailure(
                f"authority snapshot section payload has the wrong id: "
                f"{section_id}"
            )
        if (
            type(section_payload.get("source_id")) is not str
            or section_payload["source_id"] != source_id
        ):
            raise SyncFailure(
                f"authority snapshot section payload has the wrong source: "
                f"{section_id}"
            )
        content = section_payload.get("content")
        if type(content) is not str:
            raise SyncFailure(
                f"authority snapshot section content must be a string: "
                f"{section_id}"
            )
        try:
            source_content.validate_source_content(content)
        except (
            source_content.SourceContentError,
            TypeError,
            UnicodeError,
        ) as failure:
            raise SyncFailure(
                f"authority snapshot section content is invalid: "
                f"{section_id}"
            ) from failure
        if "chapter_id" in section_payload:
            chapter_id = section_payload["chapter_id"]
            if type(chapter_id) is not str:
                raise SyncFailure(
                    f"authority snapshot section chapter id must be a "
                    f"string: {section_id}"
                )
            if chapter_id:
                chapter_bindings.append(
                    (
                        source_id,
                        require_identifier(
                            chapter_id,
                            f"authority snapshot section {section_id} "
                            "chapter id",
                        ),
                    )
                )
        sections_by_id[section_id] = row
        section_entries.append(
            {
                "id": section_id,
                "sourceId": source_id,
                "payloadSha256": text_sha256(row.payload),
                "contentSha256": text_sha256(content),
            }
        )

    for source_id, section_id in (*toc_bindings, *chapter_bindings):
        section = sections_by_id.get(section_id)
        if section is None:
            raise SyncFailure(
                f"authority snapshot references an unknown section: "
                f"{section_id}"
            )
        if section.source_id != source_id:
            raise SyncFailure(
                f"authority snapshot section ownership is invalid: "
                f"{section_id}"
            )

    authority = {
        "schema": AUTHORITY_SNAPSHOT_SCHEMA,
        "ruleset": RULESET_ID,
        "sources": sorted(source_entries, key=lambda item: item["id"]),
        "sections": sorted(section_entries, key=lambda item: item["id"]),
    }
    authority["digest"] = text_sha256(canonical_json(authority))
    payload = canonical_json(authority)
    if utf8_size(payload, "authority snapshot") > MAX_ROW_BYTES:
        raise SyncFailure("authority snapshot exceeds its byte bound")
    return payload


def prepared_authority_rows(
    sources: object,
    tocs: object,
    sections: object,
) -> tuple[
    tuple[StoredSourceRow, ...],
    tuple[StoredSectionRow, ...],
    str,
]:
    for value, label in (
        (sources, "cache sources"),
        (tocs, "cache ToCs"),
        (sections, "cache sections"),
    ):
        if type(value) is not dict:
            raise SyncFailure(f"{label} must be an object")
        for key in value:
            require_identifier(key, f"{label} key")

    source_ids = set(sources)
    if source_ids != set(tocs):
        raise SyncFailure("cache source and ToC ids do not match")
    if len(source_ids) > MAX_MANIFEST_SOURCES:
        raise SyncFailure("cache exceeds its source-count bound")
    if len(sections) > MAX_MANIFEST_SECTIONS:
        raise SyncFailure("cache exceeds its section-count bound")
    source_rows = []
    for source_id in sorted(source_ids):
        try:
            payload = compact_json(sources[source_id])
            toc = compact_json(tocs[source_id])
        except (TypeError, ValueError, RecursionError) as failure:
            raise SyncFailure(
                f"cache source row is not JSON-compatible: {source_id}"
            ) from failure
        source_rows.append(
            StoredSourceRow(
                source_id=source_id,
                payload=payload,
                toc=toc,
            )
        )

    section_rows = []
    for section_id in sorted(sections):
        section = sections[section_id]
        if type(section) is not dict:
            raise SyncFailure(
                f"cache section payload must be an object: {section_id}"
            )
        source_id = section.get("source_id")
        if type(source_id) is not str:
            raise SyncFailure(
                f"cache section source id must be a string: {section_id}"
            )
        try:
            payload = compact_json(section)
        except (TypeError, ValueError, RecursionError) as failure:
            raise SyncFailure(
                f"cache section row is not JSON-compatible: {section_id}"
            ) from failure
        section_rows.append(
            StoredSectionRow(
                section_id=section_id,
                source_id=source_id,
                payload=payload,
            )
        )

    frozen_source_rows = tuple(source_rows)
    frozen_section_rows = tuple(section_rows)
    snapshot = authority_snapshot_payload(
        frozen_source_rows,
        frozen_section_rows,
    )
    return frozen_source_rows, frozen_section_rows, snapshot


def verify_authority_snapshot(connection: sqlite3.Connection) -> None:
    source_rows = tuple(
        StoredSourceRow(*row)
        for row in connection.execute(
            "SELECT id, payload, toc FROM sources ORDER BY id"
        )
    )
    section_rows = tuple(
        StoredSectionRow(*row)
        for row in connection.execute(
            "SELECT id, source_id, payload FROM sections ORDER BY id"
        )
    )
    snapshot_rows = connection.execute(
        "SELECT singleton, payload FROM authority_snapshot"
    ).fetchall()
    if len(snapshot_rows) != 1 or snapshot_rows[0][0] != 1:
        raise SyncFailure(
            "generated cache has an invalid authority snapshot singleton"
        )
    expected = authority_snapshot_payload(source_rows, section_rows)
    if type(snapshot_rows[0][1]) is not str or snapshot_rows[0][1] != expected:
        raise SyncFailure(
            "generated cache authority snapshot does not match its rows"
        )


def clean_origin(value: str) -> str:
    parsed = urlparse.urlsplit(str(value or "").strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise SyncFailure("library origin must be an HTTP(S) origin without a path")
    return f"{parsed.scheme}://{parsed.netloc}"


@dataclass(frozen=True)
class BinaryPayload:
    body: bytes
    content_type: str
    headers: tuple[tuple[str, str], ...] = ()


def response_header_values(
    headers: tuple[tuple[str, str], ...],
    name: str,
) -> tuple[str, ...]:
    expected = name.casefold()
    return tuple(
        value
        for key, value in headers
        if key.casefold() == expected
    )


def require_no_store(
    operation: str,
    headers: tuple[tuple[str, str], ...],
) -> None:
    if operation not in GENERATION_BOUND_OPERATIONS:
        return
    directives = {
        directive.strip().casefold()
        for value in response_header_values(headers, "Cache-Control")
        for directive in value.split(",")
        if directive.strip()
    }
    if "no-store" not in directives:
        raise SyncFailure(
            f"library {operation} response is missing "
            "Cache-Control: no-store"
        )


def response_headers(values: object) -> tuple[tuple[str, str], ...]:
    try:
        items = values.items()
    except AttributeError:
        return ()
    return tuple((str(key), str(value)) for key, value in items)


def generation_from_payload(
    operation: str,
    payload: dict,
    *,
    expected: str | None = None,
) -> str:
    if type(payload) is not dict:
        raise SyncFailure(
            f"library {operation} returned the wrong payload shape"
        )
    if type(payload.get("schema")) is not int or payload["schema"] != 2:
        raise SyncFailure(
            f"library {operation} returned the wrong schema"
        )
    if (
        type(payload.get("dataset")) is not str
        or payload["dataset"] != LIBRARY_DATASET
    ):
        raise SyncFailure(
            f"library {operation} returned the wrong dataset"
        )
    generation = require_generation_token(
        payload.get("generation"),
        f"library {operation} response generation",
    )
    if expected is not None:
        expected = require_generation_token(
            expected,
            "expected source publication generation",
        )
        if not hmac.compare_digest(generation, expected):
            raise SyncFailure(
                f"library {operation} returned a changed generation"
            )
    return generation


def require_generation_token(value: object, label: str) -> str:
    if (
        type(value) is not str
        or GENERATION_RE.fullmatch(value) is None
    ):
        raise SyncFailure(f"{label} is malformed")
    return value


class LibraryClient:
    def __init__(
        self,
        origin: str,
        *,
        authorization_provider=None,
        timeout: float = 30.0,
    ):
        if authorization_provider is not None and not callable(authorization_provider):
            raise SyncFailure("Library authorization provider is invalid")
        self.origin = clean_origin(origin)
        self.authorization_provider = authorization_provider
        self.timeout = timeout
        self.opener = urlrequest.build_opener(NoRedirectHandler())

    def url(self, operation: str, *, rest: tuple[str, ...] = (), params: dict[str, object] | None = None) -> str:
        dataset = "/".join(urlparse.quote(part, safe="") for part in LIBRARY_DATASET.split("/"))
        path = f"{self.origin}/{dataset}/.api/{urlparse.quote(operation, safe='')}"
        for part in rest:
            path += f"/{urlparse.quote(str(part), safe='')}"
        query = urlparse.urlencode(params or {}, doseq=True)
        return f"{path}?{query}" if query else path

    def accept_invitation(self, token: str) -> dict:
        if LIBRARY_INVITATION_RE.fullmatch(str(token or "")) is None:
            raise SyncFailure("Library invitation is invalid")
        endpoint = self.origin + "/.api/library-invitations/accept"
        authorization = (
            self.authorization_provider()
            if self.authorization_provider is not None
            else ""
        )
        if not authorization:
            raise SyncFailure("Library invitation authorization is unavailable")
        body = compact_json({"token": token}).encode("utf-8")
        request = urlrequest.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": authorization,
                "Content-Type": "application/json",
                "User-Agent": "KMQDB-TTRPG-Cache-Sync/1",
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.geturl() != endpoint:
                    raise SyncFailure("Library invitation acceptance redirected")
                raw = response.read(MAX_ROW_BYTES + 1)
                headers = response_headers(response.headers)
        except urlerror.HTTPError as failure:
            failure.read(MAX_ROW_BYTES + 1)
            raise SyncFailure("Library invitation was rejected") from failure
        except (urlerror.URLError, TimeoutError, OSError) as failure:
            raise SyncFailure("Library invitation service is unavailable") from failure
        if len(raw) > MAX_ROW_BYTES:
            raise SyncFailure("Library invitation response is too large")
        require_no_store("library-invitation", headers)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as failure:
            raise SyncFailure("Library invitation response is invalid") from failure
        library = payload.get("library") if type(payload) is dict else None
        if (
            type(payload) is not dict
            or set(payload) != {"schema", "library"}
            or payload["schema"] != 1
            or type(library) is not dict
            or library.get("slug") != LIBRARY_SLUG
            or library.get("membershipRole") != "reader"
            or library.get("status") != "active"
            or library.get("hierarchyScopes") != ["games/ttrpg"]
        ):
            raise SyncFailure("Library invitation response is invalid")
        return payload

    def request(
        self,
        operation: str,
        *,
        rest: tuple[str, ...] = (),
        params: dict[str, object] | None = None,
        accept: str = "application/json",
        json_body: object | None = None,
    ) -> BinaryPayload:
        headers = {"Accept": accept, "User-Agent": "KMQDB-TTRPG-Cache-Sync/1"}
        authorization = (
            self.authorization_provider()
            if self.authorization_provider is not None
            else ""
        )
        if authorization:
            headers["Authorization"] = authorization
        body = None
        if json_body is not None:
            body = compact_json(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urlrequest.Request(
            self.url(operation, rest=rest, params=params),
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if accept == "application/json":
                    body = response.read(MAX_ROW_BYTES + 1)
                    if len(body) > MAX_ROW_BYTES:
                        raise SyncFailure(
                            f"library {operation} response exceeds its "
                            "JSON byte bound"
                        )
                else:
                    body = response.read()
                content_type = str(response.headers.get("Content-Type") or "application/octet-stream")
                headers = response_headers(response.headers)
                require_no_store(operation, headers)
        except urlerror.HTTPError as failure:
            headers = response_headers(failure.headers)
            require_no_store(operation, headers)
            body = failure.read(MAX_ROW_BYTES + 1)
            if len(body) > MAX_ROW_BYTES:
                raise SyncFailure(
                    f"library {operation} error response exceeds its "
                    "JSON byte bound"
                ) from failure
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            message = str(payload.get("error") or failure.reason) if isinstance(payload, dict) else str(failure.reason)
            raise LibraryRequestFailure(
                operation,
                failure.code,
                message,
            ) from failure
        except (urlerror.URLError, TimeoutError, OSError) as failure:
            raise SyncFailure(f"library {operation} request failed: {failure}") from failure
        return BinaryPayload(
            body=body,
            content_type=content_type,
            headers=headers,
        )

    def get(self, operation: str, *, rest: tuple[str, ...] = (), params: dict[str, object] | None = None, accept: str = "application/json") -> BinaryPayload:
        return self.request(operation, rest=rest, params=params, accept=accept)

    def get_json(self, operation: str, *, params: dict[str, object] | None = None) -> dict:
        response = self.get(operation, params=params)
        return self.decoded_json(operation, response)

    def post_json(self, operation: str, payload: object, *, params: dict[str, object] | None = None) -> dict:
        response = self.request(operation, params=params, json_body=payload)
        return self.decoded_json(operation, response)

    def decoded_json(self, operation: str, response: BinaryPayload) -> dict:
        try:
            text = response.body.decode("utf-8")
        except UnicodeDecodeError as failure:
            raise SyncFailure(f"library {operation} returned invalid JSON") from failure
        payload = decoded_stored_json(
            text,
            f"library {operation} response",
        )
        if type(payload) is not dict:
            raise SyncFailure(f"library {operation} returned the wrong payload shape")
        dataset = payload.get("dataset", "")
        if type(dataset) is not str:
            raise SyncFailure(f"library {operation} returned the wrong dataset")
        if dataset and dataset != LIBRARY_DATASET:
            raise SyncFailure(f"library {operation} returned the wrong dataset")
        return payload


def normalize_cached_text(value: str, origin: str) -> str:
    upstream_prefix = f"/{LIBRARY_DATASET}"
    local_prefix = f"/{LOCAL_RENDERER_DATASET}"
    return str(value).replace(f"{origin}{upstream_prefix}", local_prefix).replace(upstream_prefix, local_prefix)


def normalize_cached_value(value: object, origin: str):
    if isinstance(value, dict):
        return {key: normalize_cached_value(item, origin) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_cached_value(item, origin) for item in value]
    if isinstance(value, str):
        return normalize_cached_text(value, origin)
    return value


def normalized_source(source: object, source_id: str, origin: str) -> dict:
    if not isinstance(source, dict) or str(source.get("id") or "") != source_id:
        raise SyncFailure(f"publication response has the wrong source: {source_id}")
    payload = normalize_cached_value(source, origin)
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    payload["meta"] = {key: value for key, value in meta.items() if key != "images"}
    if "css" in payload:
        payload["css"] = CSS_IMPORT_RE.sub("", str(payload.get("css") or ""))
    return payload


def toc_section_ids(nodes: object) -> set[str]:
    result: set[str] = set()
    if not isinstance(nodes, list):
        return result
    for node in nodes:
        if not isinstance(node, dict):
            continue
        section_id = str(node.get("section_id") or "")
        if section_id:
            result.add(section_id)
        result.update(toc_section_ids(node.get("children")))
    return result


def chunks(values: list[str], size: int = 200):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def fetch_publications(
    client: LibraryClient,
    source_ids: list[str],
    generation: str,
) -> tuple[dict[str, dict], dict[str, list[dict]], set[str]]:
    generation = require_generation_token(
        generation,
        "source publication generation",
    )
    sources: dict[str, dict] = {}
    tocs: dict[str, list[dict]] = {}
    section_ids: set[str] = set()
    for source_id in source_ids:
        payload = client.get_json(
            "source-publication",
            params={
                "db": LIBRARY_DB,
                "source": source_id,
                "generation": generation,
            },
        )
        generation_from_payload(
            "source-publication",
            payload,
            expected=generation,
        )
        toc = payload.get("toc")
        if not isinstance(toc, list):
            raise SyncFailure(f"publication response has an invalid ToC: {source_id}")
        normalized_toc = normalize_cached_value(toc, client.origin)
        sources[source_id] = normalized_source(payload.get("source"), source_id, client.origin)
        tocs[source_id] = normalized_toc
        section_ids.update(toc_section_ids(normalized_toc))
    return sources, tocs, section_ids


def fetch_sections(
    client: LibraryClient,
    initial_ids: set[str],
    source_ids: set[str],
    generation: str,
) -> dict[str, dict]:
    if type(initial_ids) is not set or type(source_ids) is not set:
        raise SyncFailure("source-section ids must be exact sets")
    generation = require_generation_token(
        generation,
        "source publication generation",
    )
    for section_id in initial_ids:
        require_identifier(section_id, "requested section id")
    for source_id in source_ids:
        source_id = require_identifier(source_id, "selected source id")
        if SOURCE_ID_RE.fullmatch(source_id) is None:
            raise SyncFailure(f"selected source id is invalid: {source_id}")

    sections: dict[str, dict] = {}
    pending = set(initial_ids)
    seen_returned_ids: set[str] = set()
    while pending:
        requested = sorted(pending)
        pending.clear()
        for batch in chunks(requested):
            requested_batch = set(batch)
            payload = client.post_json(
                "source-sections",
                {"ids": batch},
                params={
                    "db": LIBRARY_DB,
                    "generation": generation,
                },
            )
            generation_from_payload(
                "source-sections",
                payload,
                expected=generation,
            )
            missing = payload.get("missing", [])
            if type(missing) is not list or any(
                type(value) is not str for value in missing
            ):
                raise SyncFailure(
                    "source-sections returned an invalid missing list"
                )
            if missing:
                raise SyncFailure(f"library cache source sections are missing: {', '.join(missing[:5])}")
            entries = payload.get("entries")
            if type(entries) is not list:
                raise SyncFailure("source-sections returned the wrong payload shape")
            returned: set[str] = set()
            for item in entries:
                if type(item) is not dict:
                    raise SyncFailure("source-sections returned an invalid entry")
                section_id = require_identifier(
                    item.get("id"),
                    "source-sections entry id",
                )
                if section_id in seen_returned_ids or section_id in returned:
                    raise SyncFailure(
                        "source-sections returned a duplicate entry: "
                        f"{section_id}"
                    )
                if section_id not in requested_batch:
                    raise SyncFailure(
                        "source-sections returned an unrequested entry: "
                        f"{section_id}"
                    )
                source_id = require_identifier(
                    item.get("source_id"),
                    f"source-sections entry {section_id} source id",
                )
                if (
                    SOURCE_ID_RE.fullmatch(source_id) is None
                    or source_id not in source_ids
                ):
                    raise SyncFailure(f"source-sections returned an invalid binding: {section_id}")
                returned.add(section_id)
                normalized = normalize_cached_value(item, client.origin)
                sections[section_id] = normalized
                chapter_id = normalized.get("chapter_id", "")
                if type(chapter_id) is not str:
                    raise SyncFailure(
                        "source-sections returned an invalid chapter id: "
                        f"{section_id}"
                    )
                if chapter_id:
                    require_identifier(
                        chapter_id,
                        f"source-sections entry {section_id} chapter id",
                    )
                if chapter_id and chapter_id not in sections:
                    pending.add(chapter_id)
            if returned != requested_batch:
                absent = requested_batch - returned
                raise SyncFailure(
                    "source-sections omitted requested rows: "
                    f"{', '.join(sorted(absent)[:5])}"
                )
            seen_returned_ids.update(returned)
        pending.difference_update(sections)
    return sections


def fetch_presentation(client: LibraryClient) -> tuple[dict, dict[tuple[str, int], BinaryPayload]]:
    payload = client.get_json("source-presentation")
    presentation = payload.get("presentation")
    if not isinstance(presentation, dict):
        raise SyncFailure("source-presentation returned the wrong manifest shape")
    presentation = normalize_cached_value(presentation, client.origin)
    assets: dict[tuple[str, int], BinaryPayload] = {}
    script_texts: list[str] = []
    for kind, field, accept in (
        ("css", "stylesheets", "text/css"),
        ("js", "scripts", "application/javascript, text/javascript"),
    ):
        entries = presentation.get(field)
        if not isinstance(entries, list):
            raise SyncFailure(f"source-presentation has an invalid {field} manifest")
        expected_indexes = list(range(len(entries)))
        indexes = [int(item.get("index")) for item in entries if isinstance(item, dict) and str(item.get("index", "")).isdigit()]
        if indexes != expected_indexes:
            raise SyncFailure(f"source-presentation has a non-contiguous {field} manifest")
        for index in indexes:
            response = client.get(
                "source-presentation",
                params={"kind": kind, "index": index},
                accept=accept,
            )
            try:
                text = normalize_cached_text(response.body.decode("utf-8"), client.origin)
            except UnicodeDecodeError as failure:
                raise SyncFailure(f"source-presentation {kind}/{index} is not UTF-8") from failure
            if kind == "css":
                text = CSS_IMPORT_RE.sub("", text)
            else:
                script_texts.append(text)
            content_type = response.content_type
            if "charset=" not in content_type.lower():
                content_type = f"{content_type.split(';', 1)[0]}; charset=utf-8"
            assets[(kind, index)] = BinaryPayload(text.encode("utf-8"), content_type)
    if str(presentation.get("renderer") or ""):
        interfaces = [
            text
            for text in script_texts
            if SEALED_RENDERER_INTERFACE_MARKER in text
        ]
        bundles = [
            text
            for text in script_texts
            if SEALED_RENDERER_BUNDLE_MARKER in text
        ]
        if len(interfaces) != 1 or len(bundles) != 1:
            raise SyncFailure(
                "source-presentation does not provide one sealed renderer interface and bundle"
            )
        if "Function(" in interfaces[0]:
            raise SyncFailure(
                "source-presentation renderer interface uses dynamic code evaluation"
            )
    return presentation, assets


def binary_asset_download(client: LibraryClient, asset: dict) -> BinaryPayload:
    kind = str(asset.get("kind") or "")
    key = str(asset.get("key") or "")
    if kind == "cover":
        response = client.get(
            "source-cover",
            params={"db": LIBRARY_DB, "source": key},
            accept="image/*",
        )
    elif kind == "icon":
        response = client.get(
            "source-icon",
            rest=tuple(key.split("/")),
            accept="image/*",
        )
    elif kind == "image":
        response = client.get(
            "source-image",
            rest=tuple(key.split("/")),
            accept="image/*",
        )
    else:
        raise SyncFailure(f"unsupported binary asset kind: {kind}")
    if not response.content_type.lower().startswith("image/"):
        raise SyncFailure(f"library returned a non-image binary asset: {kind}/{key}")
    expected_size = int(asset.get("size") or 0)
    if expected_size and len(response.body) != expected_size:
        raise SyncFailure(f"library returned the wrong binary asset size: {kind}/{key}")
    return response


def fetch_binary_assets(
    client: LibraryClient,
    source_ids: set[str],
    *,
    download: bool,
    workers: int,
) -> tuple[str, list[dict]]:
    payload = client.get_json("source-assets", params={"db": LIBRARY_DB})
    bucket = str(payload.get("bucket") or "")
    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list):
        raise SyncFailure("source-assets returned the wrong payload shape")
    assets = []
    seen: set[tuple[str, str]] = set()
    source_image_prefixes = tuple(
        tuple(source_id.split("-"))
        for source_id in source_ids
    )
    for raw in raw_assets:
        if not isinstance(raw, dict):
            raise SyncFailure("source-assets returned an invalid entry")
        asset = dict(raw)
        kind = str(asset.get("kind") or "")
        key = str(asset.get("key") or "")
        if kind == "cover" and key not in source_ids:
            continue
        key_parts = tuple(key.split("/"))
        if kind in {"icon", "image"} and (
            not key
            or any(
                part in {"", ".", ".."} or "\\" in part or "\x00" in part
                for part in key_parts
            )
        ):
            raise SyncFailure(f"source-assets returned an invalid {kind} key: {key}")
        if kind == "image" and not any(
            len(key_parts) > len(prefix) and key_parts[:len(prefix)] == prefix
            for prefix in source_image_prefixes
        ):
            continue
        if kind not in {"cover", "icon", "image"} or not key:
            raise SyncFailure("source-assets returned an unsupported asset")
        identity = (kind, key)
        if identity in seen:
            raise SyncFailure(f"source-assets returned a duplicate asset: {kind}/{key}")
        seen.add(identity)
        content_type = str(asset.get("content_type") or "")
        if not content_type.startswith("image/"):
            raise SyncFailure(f"source-assets returned a non-image asset: {kind}/{key}")
        if not str(asset.get("s3_key") or "") and not download:
            raise SyncFailure(f"source-assets has no S3 binding: {kind}/{key}")
        asset["body"] = None
        assets.append(asset)

    if download and assets:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {executor.submit(binary_asset_download, client, asset): asset for asset in assets}
            for future in as_completed(futures):
                asset = futures[future]
                payload = future.result()
                asset["body"] = payload.body
                asset["content_type"] = payload.content_type.split(";", 1)[0]
    return bucket, assets


def create_cache(
    path: Path,
    *,
    origin: str,
    generation: str,
    bookshelf: dict,
    presentation: dict,
    presentation_assets: dict[tuple[str, int], BinaryPayload],
    sources: dict[str, dict],
    tocs: dict[str, list[dict]],
    sections: dict[str, dict],
    bucket: str,
    binary_assets: list[dict],
) -> None:
    generation = require_generation_token(
        generation,
        "source publication generation",
    )
    generation_from_payload(
        "bookshelf",
        bookshelf,
        expected=generation,
    )
    source_rows, section_rows, authority_snapshot = prepared_authority_rows(
        sources,
        tocs,
        sections,
    )
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_SQL)
        metadata = {
            "library_dataset": LIBRARY_DATASET,
            "ruleset": RULESET_ID,
            "source_generation": generation,
            "upstream_origin": origin,
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "source_count": str(len(source_rows)),
            "section_count": str(len(section_rows)),
            "binary_asset_count": str(len(binary_assets)),
        }
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            sorted(metadata.items()),
        )
        connection.execute(
            "INSERT INTO bookshelf(singleton, payload) VALUES (1, ?)",
            (compact_json(normalize_cached_value(bookshelf, origin)),),
        )
        connection.execute(
            "INSERT INTO presentation(singleton, payload) VALUES (1, ?)",
            (compact_json(presentation),),
        )
        connection.executemany(
            "INSERT INTO presentation_assets(kind, asset_index, content_type, body) VALUES (?, ?, ?, ?)",
            [
                (kind, index, payload.content_type, payload.body)
                for (kind, index), payload in sorted(presentation_assets.items())
            ],
        )
        connection.executemany(
            "INSERT INTO sources(id, payload, toc) VALUES (?, ?, ?)",
            [
                (row.source_id, row.payload, row.toc)
                for row in source_rows
            ],
        )
        connection.executemany(
            "INSERT INTO sections(id, source_id, payload) VALUES (?, ?, ?)",
            [
                (row.section_id, row.source_id, row.payload)
                for row in section_rows
            ],
        )
        connection.execute(
            "INSERT INTO authority_snapshot(singleton, payload) "
            "VALUES (1, ?)",
            (authority_snapshot,),
        )
        connection.executemany(
            """
            INSERT INTO binary_assets(
                kind, asset_key, content_type, bucket, s3_key, body,
                size, etag, last_modified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(asset.get("kind") or ""),
                    str(asset.get("key") or ""),
                    str(asset.get("content_type") or "application/octet-stream").split(";", 1)[0],
                    bucket,
                    str(asset.get("s3_key") or ""),
                    asset.get("body"),
                    int(asset.get("size") or (len(asset.get("body")) if asset.get("body") is not None else 0)),
                    str(asset.get("etag") or ""),
                    str(asset.get("last_modified") or ""),
                )
                for asset in binary_assets
            ],
        )
        failures = connection.execute("PRAGMA integrity_check").fetchall()
        if failures != [("ok",)]:
            raise SyncFailure(f"generated cache failed integrity_check: {failures}")
        verify_authority_snapshot(connection)
        connection.commit()


def replace_cache(
    destination: Path,
    *,
    client: LibraryClient,
    origin: str,
    generation: str,
    bookshelf: dict,
    presentation: dict,
    presentation_assets: dict[tuple[str, int], BinaryPayload],
    sources: dict[str, dict],
    tocs: dict[str, list[dict]],
    sections: dict[str, dict],
    bucket: str,
    binary_assets: list[dict],
) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    try:
        destination_identity = destination.stat()
    except FileNotFoundError:
        destination_identity = None
    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        create_cache(
            temporary,
            origin=origin,
            generation=generation,
            bookshelf=bookshelf,
            presentation=presentation,
            presentation_assets=presentation_assets,
            sources=sources,
            tocs=tocs,
            sections=sections,
            bucket=bucket,
            binary_assets=binary_assets,
        )
        if destination_identity is None:
            temporary.chmod(0o640)
        else:
            temporary.chmod(stat.S_IMODE(destination_identity.st_mode))
            temporary_identity = temporary.stat()
            if (
                temporary_identity.st_uid != destination_identity.st_uid
                or temporary_identity.st_gid != destination_identity.st_gid
            ):
                os.chown(
                    temporary,
                    destination_identity.st_uid,
                    destination_identity.st_gid,
                )
        verify_final_bookshelf(client, generation, bookshelf)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Atomically synchronize one selected TTRPG ruleset cache from the Library API."
    )
    parser.add_argument(
        "--origin",
        default=os.environ.get("KMQDB_TTRPG_LIBRARY_ORIGIN", ""),
        help="Main library HTTP(S) origin (or KMQDB_TTRPG_LIBRARY_ORIGIN).",
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument(
        "--library-slug",
        default=os.environ.get("KMQDB_TTRPG_LIBRARY_SLUG", "karmak"),
        help="Library membership slug (default: karmak).",
    )
    parser.add_argument(
        "--ruleset",
        default=os.environ.get("KMQDB_TTRPG_RULESET", "pf2er"),
        help="Selected ruleset below games/ttrpg (default: pf2er).",
    )
    parser.add_argument("--source", action="append", default=[], help="Build a cache containing only this source; repeatable.")
    parser.add_argument("--download-assets", action="store_true", help="Store approved binary assets in SQLite instead of relying only on their S3 bindings.")
    parser.add_argument("--asset-workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--core-origin",
        default=os.environ.get("KMQDB_CORE_ORIGIN", "https://kmqdb.com"),
        help="Core identity origin (default: https://kmqdb.com).",
    )
    parser.add_argument(
        "--machine-credential-file",
        type=Path,
        default=(
            Path(os.environ["KMQDB_TTRPG_LIBRARY_MACHINE_CREDENTIAL_FILE"])
            if os.environ.get("KMQDB_TTRPG_LIBRARY_MACHINE_CREDENTIAL_FILE")
            else None
        ),
        help="Absolute mode-0600 Core machine credential file.",
    )
    parser.add_argument(
        "--library-invitation-file",
        type=Path,
        default=(
            Path(os.environ["KMQDB_TTRPG_LIBRARY_INVITATION_FILE"])
            if os.environ.get("KMQDB_TTRPG_LIBRARY_INVITATION_FILE")
            else None
        ),
        help="Optional one-use mode-0600 Library invitation token file.",
    )
    return parser.parse_args(argv)


def verify_final_bookshelf(
    client: LibraryClient,
    generation: str,
    initial_bookshelf: dict,
) -> None:
    generation = require_generation_token(
        generation,
        "source publication generation",
    )
    final_bookshelf = client.get_json(
        "bookshelf",
        params={
            "db": LIBRARY_DB,
            "generation": generation,
        },
    )
    generation_from_payload(
        "bookshelf",
        final_bookshelf,
        expected=generation,
    )
    if not hmac.compare_digest(
        canonical_json(final_bookshelf),
        canonical_json(initial_bookshelf),
    ):
        raise SyncFailure(
            "library bookshelf changed within one source publication "
            "generation"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    configure_ruleset(
        library_slug=args.library_slug,
        ruleset_id=args.ruleset,
    )
    if not args.origin:
        raise SyncFailure("--origin or KMQDB_TTRPG_LIBRARY_ORIGIN is required")
    if args.timeout <= 0:
        raise SyncFailure("--timeout must be positive")
    if args.asset_workers <= 0:
        raise SyncFailure("--asset-workers must be positive")
    if args.machine_credential_file is None:
        raise SyncFailure(
            "--machine-credential-file or KMQDB_TTRPG_LIBRARY_MACHINE_CREDENTIAL_FILE is required"
        )
    machine_identity = CoreMachineIdentity(
        args.core_origin,
        args.machine_credential_file,
        timeout=args.timeout,
    )
    client = LibraryClient(
        args.origin,
        authorization_provider=machine_identity.authorization_header,
        timeout=args.timeout,
    )
    if args.library_invitation_file is not None:
        client.accept_invitation(
            read_library_invitation(args.library_invitation_file)
        )
    bookshelf = client.get_json("bookshelf", params={"db": LIBRARY_DB})
    generation = generation_from_payload("bookshelf", bookshelf)
    available = [
        str(entry.get("id") or "")
        for entry in bookshelf.get("entries") or []
        if isinstance(entry, dict) and SOURCE_ID_RE.fullmatch(str(entry.get("id") or ""))
    ]
    requested = list(dict.fromkeys(str(value).strip() for value in args.source if str(value).strip()))
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise SyncFailure(f"requested sources are not on the bookshelf: {', '.join(unknown)}")
    source_ids = requested or available
    if not source_ids:
        raise SyncFailure("library bookshelf contains no cacheable sources")

    presentation, presentation_assets = fetch_presentation(client)
    sources, tocs, section_ids = fetch_publications(
        client,
        source_ids,
        generation,
    )
    sections = fetch_sections(
        client,
        section_ids,
        set(source_ids),
        generation,
    )
    bucket, binary_assets = fetch_binary_assets(
        client,
        set(source_ids),
        download=args.download_assets,
        workers=args.asset_workers,
    )
    replace_cache(
        args.cache,
        client=client,
        origin=client.origin,
        generation=generation,
        bookshelf=bookshelf,
        presentation=presentation,
        presentation_assets=presentation_assets,
        sources=sources,
        tocs=tocs,
        sections=sections,
        bucket=bucket,
        binary_assets=binary_assets,
    )
    print(
        f"wrote {args.cache.resolve()} "
        f"({len(sources)} sources, {len(sections)} sections, "
        f"{len(binary_assets)} approved binary assets)"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyncFailure as failure:
        print(f"sync failed: {failure}", file=sys.stderr)
        raise SystemExit(1)

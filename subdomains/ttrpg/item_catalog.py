"""Deterministic, read-only PF2ER persistent-item catalog artifact.

The source library cache remains the canonical input.  This module owns only
the generated catalog container and its runtime validation; it never reads the
library, compiles source content, or mutates persistent owner inventory.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Iterable, Mapping


RULESET_ID = "pf2er"
CATALOG_KIND = "pf2er-item-catalog"
CATALOG_SCHEMA_VERSION = 1
DATABASE_ENVIRONMENT_VARIABLE = "KMQDB_TTRPG_ITEM_CATALOG_DB"
DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "cache" / "item-catalog.db"
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

_SCHEMA = f"""
PRAGMA user_version = {CATALOG_SCHEMA_VERSION};
PRAGMA foreign_keys = ON;

CREATE TABLE manifest (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    payload TEXT NOT NULL
);

CREATE TABLE definitions (
    definition_digest TEXT PRIMARY KEY CHECK (
        length(definition_digest) = 64
    ),
    definition_id TEXT NOT NULL UNIQUE,
    item_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
) WITHOUT ROWID;

CREATE INDEX definitions_by_item
    ON definitions(item_id, definition_id);

CREATE TABLE aliases (
    normalized_source_name TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('canonical', 'deferred')
    ),
    definition_digest TEXT,
    blocker_json TEXT,
    CHECK (
        (
            status = 'canonical'
            AND definition_digest IS NOT NULL
            AND blocker_json IS NULL
        )
        OR
        (
            status = 'deferred'
            AND definition_digest IS NULL
            AND blocker_json IS NOT NULL
        )
    ),
    FOREIGN KEY (definition_digest)
        REFERENCES definitions(definition_digest)
) WITHOUT ROWID;
"""

_EXPECTED_COLUMNS = {
    "manifest": ("singleton", "payload"),
    "definitions": (
        "definition_digest",
        "definition_id",
        "item_id",
        "kind",
        "payload",
    ),
    "aliases": (
        "normalized_source_name",
        "source_name",
        "status",
        "definition_digest",
        "blocker_json",
    ),
}


class ItemCatalogError(Exception):
    """Base class for generated item-catalog failures."""


class ItemCatalogUnavailable(ItemCatalogError):
    """The generated catalog is missing, malformed, or untrusted."""


class ItemCatalogMiss(ItemCatalogError):
    """No reviewed catalog alias exists for one source-authored name."""


class ItemCatalogDeferred(ItemCatalogError):
    """A reviewed source-authored name intentionally remains unsupported."""

    def __init__(
        self,
        source_name: object,
        *,
        reason_kind: str,
        reason_message: str,
    ) -> None:
        self.source_name = source_name
        self.reason_kind = reason_kind
        self.reason_message = reason_message
        super().__init__(
            "item catalog source name is deferred: "
            f"{source_name} ({reason_kind})"
        )


def normalized_source_name(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as failure:
        raise ItemCatalogUnavailable(
            "item catalog value is not canonical JSON"
        ) from failure


def json_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _decoded_canonical_json(value: object, label: str) -> object:
    if type(value) is not str:
        raise ItemCatalogUnavailable(f"{label} is not stored JSON")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as failure:
        raise ItemCatalogUnavailable(f"{label} is invalid JSON") from failure
    if canonical_json(decoded) != value:
        raise ItemCatalogUnavailable(f"{label} is not canonical JSON")
    return decoded


def _required_text(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
    ):
        raise ItemCatalogUnavailable(
            f"{label} must be nonempty trimmed text"
        )
    return value


def _required_digest(value: object, label: str) -> str:
    digest = _required_text(value, label)
    if DIGEST_RE.fullmatch(digest) is None:
        raise ItemCatalogUnavailable(f"{label} is not a SHA-256 digest")
    return digest


def _definition_row(payload: object) -> tuple[str, str, str, str, str]:
    if type(payload) is not dict:
        raise ItemCatalogUnavailable(
            "item definition must be an object"
        )
    normalized = deepcopy(payload)
    if normalized.get("schema") != 1:
        raise ItemCatalogUnavailable(
            "item definition schema is unsupported"
        )
    if normalized.get("kind") != "pf2er-item-definition":
        raise ItemCatalogUnavailable("item definition kind is invalid")
    if normalized.get("rulesetId") != RULESET_ID:
        raise ItemCatalogUnavailable(
            "item definition ruleset is invalid"
        )
    definition_id = _required_text(
        normalized.get("definitionId"),
        "item definition id",
    )
    item_id = _required_text(
        normalized.get("itemId"),
        "canonical item id",
    )
    item_kind = _required_text(
        normalized.get("itemKind"),
        "item kind",
    )
    presentation = normalized.get("presentation")
    if presentation is not None:
        if type(presentation) is not dict:
            raise ItemCatalogUnavailable(
                "item definition presentation is invalid"
            )
        presentation_name = _required_text(
            presentation.get("name"),
            "item presentation name",
        )
        presentation_source = presentation.get("source")
        if type(presentation_source) is not dict:
            raise ItemCatalogUnavailable(
                "item presentation source is invalid"
            )
        source_id = _required_text(
            presentation_source.get("sourceId"),
            "item presentation source id",
        )
        locator = _required_text(
            presentation_source.get("locator"),
            "item presentation source locator",
        )
        if set(presentation) != {"name", "source"} or set(
            presentation_source
        ) != {"sourceId", "locator"}:
            raise ItemCatalogUnavailable(
                "item presentation contract has unknown fields"
            )
        if normalized.get("source") != {
            "sourceId": source_id,
            "locator": locator,
        }:
            raise ItemCatalogUnavailable(
                "item definition source disagrees with presentation"
            )
        if item_kind == "weapon" and normalized.get("name") != presentation_name:
            raise ItemCatalogUnavailable(
                "weapon definition name disagrees with presentation"
            )
    payload_json = canonical_json(normalized)
    return (
        hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
        definition_id,
        item_id,
        item_kind,
        payload_json,
    )


def _alias_row(
    payload: object,
) -> tuple[str, str, str, str | None, str | None]:
    if type(payload) is not dict:
        raise ItemCatalogUnavailable("item alias must be an object")
    source_name = _required_text(
        payload.get("sourceName"),
        "item alias source name",
    )
    normalized = normalized_source_name(source_name)
    if not normalized:
        raise ItemCatalogUnavailable(
            "item alias normalized source name is empty"
        )
    status = payload.get("status")
    if status == "canonical":
        definition_digest = _required_digest(
            payload.get("definitionDigest"),
            "item alias definition digest",
        )
        return (
            normalized,
            source_name,
            status,
            definition_digest,
            None,
        )
    if status == "deferred":
        blocker = payload.get("blocker")
        if type(blocker) is not dict:
            raise ItemCatalogUnavailable(
                "deferred item alias lacks a blocker"
            )
        _required_text(
            blocker.get("kind"),
            "item alias blocker kind",
        )
        _required_text(
            blocker.get("message"),
            "item alias blocker message",
        )
        return (
            normalized,
            source_name,
            status,
            None,
            canonical_json(blocker),
        )
    raise ItemCatalogUnavailable("item alias status is invalid")


def _catalog_content(
    *,
    compiler: Mapping[str, object],
    source_generation: str,
    source_authority_digest: str,
    source_snapshot_digest: str,
    definition_rows: Iterable[tuple[str, str, str, str, str]],
    alias_rows: Iterable[
        tuple[str, str, str, str | None, str | None]
    ],
) -> dict[str, object]:
    return {
        "schema": 1,
        "rulesetId": RULESET_ID,
        "compiler": dict(compiler),
        "source": {
            "generation": source_generation,
            "authorityDigest": source_authority_digest,
            "snapshotDigest": source_snapshot_digest,
        },
        "definitions": [
            {
                "definitionDigest": row[0],
                "definitionId": row[1],
                "itemId": row[2],
                "kind": row[3],
                "payload": row[4],
            }
            for row in sorted(definition_rows)
        ],
        "aliases": [
            {
                "normalizedSourceName": row[0],
                "sourceName": row[1],
                "status": row[2],
                "definitionDigest": row[3],
                "blocker": row[4],
            }
            for row in sorted(alias_rows)
        ],
    }


def _manifest_payload(
    *,
    compiler: Mapping[str, object],
    source_generation: str,
    source_authority_digest: str,
    source_snapshot_digest: str,
    definition_rows: list[tuple[str, str, str, str, str]],
    alias_rows: list[
        tuple[str, str, str, str | None, str | None]
    ],
    generated_at: str,
) -> dict[str, object]:
    content = _catalog_content(
        compiler=compiler,
        source_generation=source_generation,
        source_authority_digest=source_authority_digest,
        source_snapshot_digest=source_snapshot_digest,
        definition_rows=definition_rows,
        alias_rows=alias_rows,
    )
    return {
        "schema": CATALOG_SCHEMA_VERSION,
        "kind": CATALOG_KIND,
        "rulesetId": RULESET_ID,
        "compiler": dict(compiler),
        "source": {
            "generation": source_generation,
            "authorityDigest": source_authority_digest,
            "snapshotDigest": source_snapshot_digest,
        },
        "counts": {
            "definitions": len(definition_rows),
            "aliases": len(alias_rows),
            "canonicalAliases": sum(
                row[2] == "canonical" for row in alias_rows
            ),
            "deferredAliases": sum(
                row[2] == "deferred" for row in alias_rows
            ),
        },
        "catalogDigest": json_digest(content),
        "generatedAt": generated_at,
    }


def create_item_catalog(
    path: Path,
    *,
    compiler: Mapping[str, object],
    source_generation: str,
    source_authority_digest: str,
    source_snapshot_digest: str,
    definitions: Iterable[object],
    aliases: Iterable[object],
    generated_at: str | None = None,
) -> dict[str, object]:
    """Create one complete catalog at an unused path."""

    generation = _required_digest(
        source_generation,
        "source generation",
    )
    authority_digest = _required_digest(
        source_authority_digest,
        "source authority digest",
    )
    snapshot_digest = _required_digest(
        source_snapshot_digest,
        "source snapshot digest",
    )
    compiler_payload = dict(compiler)
    _required_text(
        compiler_payload.get("id"),
        "item catalog compiler id",
    )
    if (
        type(compiler_payload.get("version")) is not int
        or compiler_payload["version"] < 1
    ):
        raise ItemCatalogUnavailable(
            "item catalog compiler version is invalid"
        )

    definition_rows = [_definition_row(item) for item in definitions]
    definition_digests = {row[0] for row in definition_rows}
    definition_ids = {row[1] for row in definition_rows}
    if (
        len(definition_digests) != len(definition_rows)
        or len(definition_ids) != len(definition_rows)
    ):
        raise ItemCatalogUnavailable(
            "item catalog definitions are duplicated"
        )

    alias_rows = [_alias_row(item) for item in aliases]
    if len({row[0] for row in alias_rows}) != len(alias_rows):
        raise ItemCatalogUnavailable(
            "item catalog aliases are duplicated"
        )
    if any(
        row[2] == "canonical"
        and row[3] not in definition_digests
        for row in alias_rows
    ):
        raise ItemCatalogUnavailable(
            "item catalog alias references an unknown definition"
        )

    generated = generated_at or datetime.now(timezone.utc).isoformat()
    _required_text(generated, "item catalog generated time")
    manifest = _manifest_payload(
        compiler=compiler_payload,
        source_generation=generation,
        source_authority_digest=authority_digest,
        source_snapshot_digest=snapshot_digest,
        definition_rows=definition_rows,
        alias_rows=alias_rows,
        generated_at=generated,
    )

    with sqlite3.connect(path) as connection:
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT INTO manifest(singleton, payload) VALUES (1, ?)",
            (canonical_json(manifest),),
        )
        connection.executemany(
            "INSERT INTO definitions "
            "(definition_digest, definition_id, item_id, kind, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            sorted(definition_rows),
        )
        connection.executemany(
            "INSERT INTO aliases "
            "(normalized_source_name, source_name, status, "
            " definition_digest, blocker_json) "
            "VALUES (?, ?, ?, ?, ?)",
            sorted(alias_rows),
        )
        foreign_key_failures = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if foreign_key_failures:
            raise ItemCatalogUnavailable(
                "generated item catalog failed foreign_key_check"
            )
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchall()
        if integrity != [("ok",)]:
            raise ItemCatalogUnavailable(
                "generated item catalog failed integrity_check"
            )
        connection.commit()
    return deepcopy(manifest)


def replace_item_catalog(
    destination: Path,
    **values: object,
) -> dict[str, object]:
    """Atomically replace a generated catalog after complete validation."""

    target = destination.resolve()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    with tempfile.NamedTemporaryFile(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        manifest = create_item_catalog(
            temporary,
            **values,
        )
        load_item_catalog(temporary)
        temporary.chmod(0o644)
        os.replace(temporary, target)
        return manifest
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class ItemCatalog:
    """Validated in-memory projection of one immutable catalog generation."""

    manifest: dict[str, Any]
    definitions: dict[str, dict[str, Any]]
    aliases: dict[str, dict[str, Any]]
    item_presentations: dict[str, dict[str, Any]]

    def resolve(self, source_name: object) -> dict[str, Any]:
        normalized = normalized_source_name(source_name)
        alias = self.aliases.get(normalized)
        if alias is None:
            raise ItemCatalogMiss(
                f"item catalog source name is unknown: {source_name}"
            )
        if alias["status"] == "deferred":
            blocker = alias["blocker"]
            raise ItemCatalogDeferred(
                source_name,
                reason_kind=str(blocker["kind"]),
                reason_message=str(blocker["message"]),
            )
        definition = self.definitions.get(
            str(alias["definitionDigest"])
        )
        if definition is None:
            raise ItemCatalogUnavailable(
                "item catalog alias lost its definition"
            )
        return deepcopy(definition)

    def definition(self, definition_digest: str) -> dict[str, Any]:
        definition = self.definitions.get(definition_digest)
        if definition is None:
            raise ItemCatalogMiss(
                "item catalog definition is unknown: "
                f"{definition_digest}"
            )
        return deepcopy(definition)

    def item_presentation(self, item_id: object) -> dict[str, Any] | None:
        """Return current compiled base presentation for one item identity."""

        presentation = self.item_presentations.get(str(item_id or ""))
        return deepcopy(presentation) if presentation is not None else None


def load_item_catalog(path: Path | None = None) -> ItemCatalog:
    """Load and fully verify one generated catalog using read-only SQLite."""

    configured = path
    if configured is None:
        configured = Path(
            os.environ.get(DATABASE_ENVIRONMENT_VARIABLE)
            or DEFAULT_CATALOG_PATH
        )
    resolved = configured.resolve()
    try:
        connection = sqlite3.connect(
            f"{resolved.as_uri()}?mode=ro",
            uri=True,
            isolation_level=None,
        )
    except sqlite3.Error as failure:
        raise ItemCatalogUnavailable(
            "item catalog is unavailable"
        ) from failure
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        version = int(
            connection.execute("PRAGMA user_version").fetchone()[0]
        )
        if version != CATALOG_SCHEMA_VERSION:
            raise ItemCatalogUnavailable(
                "item catalog schema is unsupported"
            )
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if tables != set(_EXPECTED_COLUMNS):
            raise ItemCatalogUnavailable(
                "item catalog tables are invalid"
            )
        for table, expected in _EXPECTED_COLUMNS.items():
            actual = tuple(
                str(row["name"])
                for row in connection.execute(
                    f"PRAGMA table_info({table})"
                )
            )
            if actual != expected:
                raise ItemCatalogUnavailable(
                    f"item catalog table is invalid: {table}"
                )

        manifest_rows = connection.execute(
            "SELECT singleton, payload FROM manifest"
        ).fetchall()
        if (
            len(manifest_rows) != 1
            or int(manifest_rows[0]["singleton"]) != 1
        ):
            raise ItemCatalogUnavailable(
                "item catalog manifest is invalid"
            )
        manifest = _decoded_canonical_json(
            manifest_rows[0]["payload"],
            "item catalog manifest",
        )
        if (
            type(manifest) is not dict
            or manifest.get("schema") != CATALOG_SCHEMA_VERSION
            or manifest.get("kind") != CATALOG_KIND
            or manifest.get("rulesetId") != RULESET_ID
            or type(manifest.get("compiler")) is not dict
            or type(manifest.get("source")) is not dict
            or type(manifest.get("counts")) is not dict
        ):
            raise ItemCatalogUnavailable(
                "item catalog manifest contract is invalid"
            )

        definition_rows = []
        definitions: dict[str, dict[str, Any]] = {}
        item_presentations: dict[str, dict[str, Any]] = {}
        for row in connection.execute(
            "SELECT definition_digest, definition_id, item_id, "
            "kind, payload FROM definitions ORDER BY definition_digest"
        ):
            payload = _decoded_canonical_json(
                row["payload"],
                "item definition",
            )
            normalized = _definition_row(payload)
            stored = (
                str(row["definition_digest"]),
                str(row["definition_id"]),
                str(row["item_id"]),
                str(row["kind"]),
                str(row["payload"]),
            )
            if normalized != stored:
                raise ItemCatalogUnavailable(
                    "item definition row disagrees with its payload"
                )
            definition_rows.append(stored)
            definitions[stored[0]] = payload
            presentation = payload.get("presentation")
            if isinstance(presentation, dict):
                public_presentation = {
                    "name": str(payload["name"]),
                    "sourceName": str(presentation["name"]),
                    "source": deepcopy(presentation["source"]),
                }
                prior = item_presentations.get(stored[2])
                if prior is not None and prior != public_presentation:
                    raise ItemCatalogUnavailable(
                        "item catalog has conflicting presentations for "
                        f"{stored[2]}"
                    )
                item_presentations[stored[2]] = public_presentation

        alias_rows = []
        aliases: dict[str, dict[str, Any]] = {}
        for row in connection.execute(
            "SELECT normalized_source_name, source_name, status, "
            "definition_digest, blocker_json FROM aliases "
            "ORDER BY normalized_source_name"
        ):
            blocker = (
                _decoded_canonical_json(
                    row["blocker_json"],
                    "item alias blocker",
                )
                if row["blocker_json"] is not None
                else None
            )
            alias_payload = {
                "sourceName": str(row["source_name"]),
                "status": str(row["status"]),
                **(
                    {
                        "definitionDigest": str(
                            row["definition_digest"]
                        )
                    }
                    if row["definition_digest"] is not None
                    else {"blocker": blocker}
                ),
            }
            normalized = _alias_row(alias_payload)
            stored = (
                str(row["normalized_source_name"]),
                str(row["source_name"]),
                str(row["status"]),
                (
                    str(row["definition_digest"])
                    if row["definition_digest"] is not None
                    else None
                ),
                (
                    str(row["blocker_json"])
                    if row["blocker_json"] is not None
                    else None
                ),
            )
            if normalized != stored:
                raise ItemCatalogUnavailable(
                    "item alias row disagrees with its payload"
                )
            alias_rows.append(stored)
            aliases[stored[0]] = alias_payload

        source = manifest["source"]
        content = _catalog_content(
            compiler=manifest["compiler"],
            source_generation=_required_digest(
                source.get("generation"),
                "catalog source generation",
            ),
            source_authority_digest=_required_digest(
                source.get("authorityDigest"),
                "catalog source authority digest",
            ),
            source_snapshot_digest=_required_digest(
                source.get("snapshotDigest"),
                "catalog source snapshot digest",
            ),
            definition_rows=definition_rows,
            alias_rows=alias_rows,
        )
        if manifest.get("catalogDigest") != json_digest(content):
            raise ItemCatalogUnavailable(
                "item catalog digest is invalid"
            )
        expected_counts = {
            "definitions": len(definition_rows),
            "aliases": len(alias_rows),
            "canonicalAliases": sum(
                row[2] == "canonical" for row in alias_rows
            ),
            "deferredAliases": sum(
                row[2] == "deferred" for row in alias_rows
            ),
        }
        if manifest["counts"] != expected_counts:
            raise ItemCatalogUnavailable(
                "item catalog counts are invalid"
            )
        foreign_key_failures = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if foreign_key_failures:
            raise ItemCatalogUnavailable(
                "item catalog foreign keys are invalid"
            )
        return ItemCatalog(
            manifest=deepcopy(manifest),
            definitions=definitions,
            aliases=aliases,
            item_presentations=item_presentations,
        )
    except sqlite3.Error as failure:
        raise ItemCatalogUnavailable(
            "item catalog is unavailable"
        ) from failure
    finally:
        connection.close()


__all__ = [
    "CATALOG_KIND",
    "CATALOG_SCHEMA_VERSION",
    "DATABASE_ENVIRONMENT_VARIABLE",
    "DEFAULT_CATALOG_PATH",
    "ItemCatalog",
    "ItemCatalogDeferred",
    "ItemCatalogError",
    "ItemCatalogMiss",
    "ItemCatalogUnavailable",
    "canonical_json",
    "create_item_catalog",
    "json_digest",
    "load_item_catalog",
    "normalized_source_name",
    "replace_item_catalog",
]

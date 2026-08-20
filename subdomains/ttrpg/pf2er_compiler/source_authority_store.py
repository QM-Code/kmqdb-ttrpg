"""Server-private cache-to-authority integration for PF2ER rules.

The browser and request layers may choose public source IDs, but they never
construct or replace the trusted objects retained here.  A store is created
only from exact rows read from one local schema-v3 SQLite cache.  It retains
one :class:`AuthoritySnapshot` and memoizes one
:class:`SourceAuthorityAdapter` identity for each exact canonical source
scope.

This module is deliberately outside ``rules_engine.mechanics``.  Mechanic
families receive an adapter from server state and remain unaware of SQLite,
cache paths, and transport concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from typing import final

from .mechanics.source_authority import (
    MAX_MANIFEST_SECTIONS,
    MAX_MANIFEST_SOURCES,
    AuthoritySnapshot,
    SourceAuthorityAdapter,
)


CACHE_SCHEMA_VERSION = 3

_AUTHORITY_COLUMNS = (
    (0, "singleton", "INTEGER", 0, None, 1),
    (1, "payload", "TEXT", 1, None, 0),
)
_SOURCE_COLUMNS = (
    (0, "id", "TEXT", 1, None, 1),
    (1, "payload", "TEXT", 1, None, 0),
    (2, "toc", "TEXT", 1, None, 0),
)
_SECTION_COLUMNS = (
    (0, "id", "TEXT", 1, None, 1),
    (1, "source_id", "TEXT", 1, None, 0),
    (2, "payload", "TEXT", 1, None, 0),
)
_PRESENTATION_COLUMNS = (
    (0, "singleton", "INTEGER", 0, None, 1),
    (1, "payload", "TEXT", 1, None, 0),
)
_TABLE_COLUMNS = (
    ("authority_snapshot", _AUTHORITY_COLUMNS),
    ("presentation", _PRESENTATION_COLUMNS),
    ("sources", _SOURCE_COLUMNS),
    ("sections", _SECTION_COLUMNS),
)


class SourceAuthorityStoreError(RuntimeError):
    """The local cache cannot establish one exact trusted authority."""


def _execute(
    connection: sqlite3.Connection,
    statement: str,
    parameters: tuple[object, ...] = (),
) -> sqlite3.Cursor:
    cursor = connection.cursor()
    cursor.row_factory = None
    return cursor.execute(statement, parameters)


def _exact_integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise SourceAuthorityStoreError(f"{label} must be an integer")
    return value


def _single_integer_row(
    connection: sqlite3.Connection,
    statement: str,
    label: str,
) -> int:
    rows = _execute(connection, statement).fetchall()
    if (
        type(rows) is not list
        or len(rows) != 1
        or type(rows[0]) is not tuple
        or len(rows[0]) != 1
    ):
        raise SourceAuthorityStoreError(
            f"{label} did not return one exact row"
        )
    return _exact_integer(rows[0][0], label)


def _presentation_vocabulary(payload: str) -> dict[str, object]:
    def exact_object(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise SourceAuthorityStoreError(
                    "authority presentation contains duplicate fields"
                )
            result[key] = value
        return result

    try:
        parsed = json.loads(
            payload,
            object_pairs_hook=exact_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                SourceAuthorityStoreError(
                    "authority presentation contains a non-finite number"
                )
            ),
        )
    except SourceAuthorityStoreError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as failure:
        raise SourceAuthorityStoreError(
            "authority presentation is not valid JSON"
        ) from failure
    if type(parsed) is not dict:
        raise SourceAuthorityStoreError(
            "authority presentation must be an object"
        )
    vocabulary = dict.get(parsed, "vocabulary")
    if type(vocabulary) is not dict:
        raise SourceAuthorityStoreError(
            "authority presentation vocabulary must be an object"
        )
    return vocabulary


def _database_path(connection: sqlite3.Connection) -> Path:
    rows = _execute(connection, "PRAGMA database_list").fetchall()
    if (
        type(rows) is not list
        or len(rows) != 1
        or type(rows[0]) is not tuple
        or len(rows[0]) != 3
        or rows[0][0] != 0
        or rows[0][1] != "main"
        or type(rows[0][2]) is not str
        or not rows[0][2]
    ):
        raise SourceAuthorityStoreError(
            "authority cache must be one unattached local main database"
        )
    try:
        path = Path(rows[0][2]).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as failure:
        raise SourceAuthorityStoreError(
            "authority cache database path is invalid"
        ) from failure
    if not path.is_file():
        raise SourceAuthorityStoreError(
            "authority cache database path is not a regular file"
        )
    return path


def _file_signature(path: Path) -> tuple[int, int, int, int]:
    try:
        status = path.stat()
    except OSError as failure:
        raise SourceAuthorityStoreError(
            "authority cache database cannot be inspected"
        ) from failure
    if not path.is_file():
        raise SourceAuthorityStoreError(
            "authority cache database is not a regular file"
        )
    return (
        status.st_dev,
        status.st_ino,
        status.st_size,
        status.st_mtime_ns,
    )


def _require_table_shapes(connection: sqlite3.Connection) -> None:
    for table_name, expected_columns in _TABLE_COLUMNS:
        schema_rows = _execute(
            connection,
            "SELECT type, name, tbl_name "
            "FROM main.sqlite_schema WHERE name = ?",
            (table_name,),
        ).fetchall()
        if schema_rows != [("table", table_name, table_name)]:
            raise SourceAuthorityStoreError(
                f"authority cache table is missing or shadowed: {table_name}"
            )
        columns = _execute(
            connection,
            f"PRAGMA main.table_info({table_name})"
        ).fetchall()
        if tuple(columns) != expected_columns:
            raise SourceAuthorityStoreError(
                f"authority cache table shape is invalid: {table_name}"
            )


def _exact_source_rows(
    rows: list[tuple[object, ...]],
    expected_count: int,
) -> tuple[
    dict[str, str],
    dict[str, str],
    tuple[str, ...],
]:
    if len(rows) != expected_count:
        raise SourceAuthorityStoreError(
            "authority cache source row count changed during read"
        )
    source_payloads: dict[str, str] = {}
    source_tocs: dict[str, str] = {}
    ordered_ids: list[str] = []
    for index, row in enumerate(rows):
        if (
            type(row) is not tuple
            or len(row) != 3
            or type(row[0]) is not str
            or type(row[1]) is not str
            or type(row[2]) is not str
        ):
            raise SourceAuthorityStoreError(
                f"authority cache source row {index} is malformed"
            )
        source_id, payload, toc = row
        if source_id in source_payloads:
            raise SourceAuthorityStoreError(
                f"authority cache source row is duplicated: {source_id}"
            )
        ordered_ids.append(source_id)
        source_payloads[source_id] = payload
        source_tocs[source_id] = toc
    source_ids = tuple(ordered_ids)
    if (
        source_ids != tuple(sorted(source_ids))
        or len(source_ids) != len(set(source_ids))
    ):
        raise SourceAuthorityStoreError(
            "authority cache source rows are not uniquely sorted"
        )
    return source_payloads, source_tocs, source_ids


def _exact_section_rows(
    rows: list[tuple[object, ...]],
    expected_count: int,
) -> tuple[dict[str, str], dict[str, str]]:
    if len(rows) != expected_count:
        raise SourceAuthorityStoreError(
            "authority cache section row count changed during read"
        )
    section_payloads: dict[str, str] = {}
    section_source_ids: dict[str, str] = {}
    ordered_ids: list[str] = []
    for index, row in enumerate(rows):
        if (
            type(row) is not tuple
            or len(row) != 3
            or type(row[0]) is not str
            or type(row[1]) is not str
            or type(row[2]) is not str
        ):
            raise SourceAuthorityStoreError(
                f"authority cache section row {index} is malformed"
            )
        section_id, source_id, payload = row
        if section_id in section_payloads:
            raise SourceAuthorityStoreError(
                f"authority cache section row is duplicated: {section_id}"
            )
        ordered_ids.append(section_id)
        section_payloads[section_id] = payload
        section_source_ids[section_id] = source_id
    section_ids = tuple(ordered_ids)
    if (
        section_ids != tuple(sorted(section_ids))
        or len(section_ids) != len(set(section_ids))
    ):
        raise SourceAuthorityStoreError(
            "authority cache section rows are not uniquely sorted"
        )
    return section_payloads, section_source_ids


def _load_snapshot(
    connection: sqlite3.Connection,
) -> tuple[AuthoritySnapshot, tuple[str, ...]]:
    if type(connection) is not sqlite3.Connection:
        raise TypeError(
            "authority store requires an exact sqlite3.Connection"
        )
    if connection.in_transaction:
        raise SourceAuthorityStoreError(
            "authority cache connection already has an active transaction"
        )
    database_path = _database_path(connection)
    starting_signature = _file_signature(database_path)
    try:
        _execute(connection, "PRAGMA query_only = ON")
        if (
            _single_integer_row(
                connection,
                "PRAGMA query_only",
                "authority cache query-only mode",
            )
            != 1
        ):
            raise SourceAuthorityStoreError(
                "authority cache connection is not read-only"
            )
        starting_data_version = _single_integer_row(
            connection,
            "PRAGMA data_version",
            "authority cache data version",
        )
        _execute(connection, "BEGIN")
        try:
            version = _single_integer_row(
                connection,
                "PRAGMA user_version",
                "authority cache schema version",
            )
            if version != CACHE_SCHEMA_VERSION:
                raise SourceAuthorityStoreError(
                    "authority cache schema version is unsupported"
                )
            _require_table_shapes(connection)

            snapshot_count = _single_integer_row(
                connection,
                "SELECT count(*) FROM main.authority_snapshot",
                "authority snapshot row count",
            )
            source_count = _single_integer_row(
                connection,
                "SELECT count(*) FROM main.sources",
                "authority source row count",
            )
            section_count = _single_integer_row(
                connection,
                "SELECT count(*) FROM main.sections",
                "authority section row count",
            )
            presentation_count = _single_integer_row(
                connection,
                "SELECT count(*) FROM main.presentation",
                "authority presentation row count",
            )
            if snapshot_count != 1:
                raise SourceAuthorityStoreError(
                    "authority cache requires one exact snapshot row"
                )
            if presentation_count != 1:
                raise SourceAuthorityStoreError(
                    "authority cache requires one exact presentation row"
                )
            if (
                source_count < 0
                or source_count > MAX_MANIFEST_SOURCES
                or section_count < 0
                or section_count > MAX_MANIFEST_SECTIONS
            ):
                raise SourceAuthorityStoreError(
                    "authority cache row cardinality exceeds its bounds"
                )

            snapshot_rows = _execute(
                connection,
                "SELECT singleton, payload "
                "FROM main.authority_snapshot ORDER BY singleton"
            ).fetchall()
            if (
                type(snapshot_rows) is not list
                or len(snapshot_rows) != 1
                or type(snapshot_rows[0]) is not tuple
                or len(snapshot_rows[0]) != 2
                or type(snapshot_rows[0][0]) is not int
                or snapshot_rows[0][0] != 1
                or type(snapshot_rows[0][1]) is not str
            ):
                raise SourceAuthorityStoreError(
                    "authority cache snapshot singleton is malformed"
                )
            source_rows = _execute(
                connection,
                "SELECT id, payload, toc FROM main.sources ORDER BY id"
            ).fetchall()
            section_rows = _execute(
                connection,
                "SELECT id, source_id, payload "
                "FROM main.sections ORDER BY id"
            ).fetchall()
            presentation_rows = _execute(
                connection,
                "SELECT singleton, payload "
                "FROM main.presentation ORDER BY singleton",
            ).fetchall()
            if (
                type(presentation_rows) is not list
                or len(presentation_rows) != 1
                or type(presentation_rows[0]) is not tuple
                or len(presentation_rows[0]) != 2
                or presentation_rows[0][0] != 1
                or type(presentation_rows[0][1]) is not str
            ):
                raise SourceAuthorityStoreError(
                    "authority cache presentation singleton is malformed"
                )
            hierarchy_vocabulary = _presentation_vocabulary(
                presentation_rows[0][1]
            )
            (
                source_payloads,
                source_tocs,
                source_ids,
            ) = _exact_source_rows(source_rows, source_count)
            (
                section_payloads,
                section_source_ids,
            ) = _exact_section_rows(section_rows, section_count)

            snapshot = AuthoritySnapshot.from_rows(
                snapshot_rows[0][1],
                source_payloads=source_payloads,
                source_tocs=source_tocs,
                section_payloads=section_payloads,
                section_source_ids=section_source_ids,
                hierarchy_vocabulary=hierarchy_vocabulary,
            )
            ending_data_version = _single_integer_row(
                connection,
                "PRAGMA data_version",
                "authority cache ending data version",
            )
            if ending_data_version != starting_data_version:
                raise SourceAuthorityStoreError(
                    "authority cache mutated during its read transaction"
                )
            _execute(connection, "COMMIT")
        except BaseException:
            if connection.in_transaction:
                _execute(connection, "ROLLBACK")
            raise
        committed_data_version = _single_integer_row(
            connection,
            "PRAGMA data_version",
            "authority cache committed data version",
        )
        if committed_data_version != starting_data_version:
            raise SourceAuthorityStoreError(
                "authority cache mutated during its read transaction"
            )
    except sqlite3.Error as failure:
        raise SourceAuthorityStoreError(
            "authority cache read failed"
        ) from failure
    if _file_signature(database_path) != starting_signature:
        raise SourceAuthorityStoreError(
            "authority cache path changed during its read transaction"
        )
    return snapshot, source_ids


@final
@dataclass(frozen=True, slots=True, init=False, eq=False)
class SourceAuthorityStore:
    """One server-owned authority snapshot and its exact adapter identities."""

    _snapshot: AuthoritySnapshot = field(repr=False, compare=False)
    _source_ids: tuple[str, ...] = field(repr=False)
    _adapters: dict[
        tuple[str, ...],
        SourceAuthorityAdapter,
    ] = field(repr=False, compare=False)
    _lock: RLock = field(repr=False, compare=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "SourceAuthorityStore must be created with "
            "from_path or from_connection"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("SourceAuthorityStore subclasses are not supported")

    @classmethod
    def from_path(
        cls,
        path: str | os.PathLike[str],
    ) -> SourceAuthorityStore:
        """Load one detached authority from a local cache opened read-only."""

        if cls is not SourceAuthorityStore:
            raise TypeError(
                "SourceAuthorityStore subclasses are not supported"
            )
        try:
            raw_path = os.fspath(path)
        except TypeError as failure:
            raise SourceAuthorityStoreError(
                "authority cache path is invalid"
            ) from failure
        if type(raw_path) is not str or not raw_path:
            raise SourceAuthorityStoreError(
                "authority cache path must be nonempty filesystem text"
            )
        if raw_path.startswith("file:") or "://" in raw_path:
            raise SourceAuthorityStoreError(
                "authority cache URI input is not accepted"
            )
        try:
            resolved = Path(raw_path).resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as failure:
            raise SourceAuthorityStoreError(
                "authority cache path is invalid"
            ) from failure
        if not resolved.is_file():
            raise SourceAuthorityStoreError(
                "authority cache path is not a regular file"
            )
        uri = f"{resolved.as_uri()}?mode=ro"
        try:
            connection = sqlite3.connect(
                uri,
                uri=True,
                isolation_level=None,
            )
        except sqlite3.Error as failure:
            raise SourceAuthorityStoreError(
                "authority cache cannot be opened read-only"
            ) from failure
        try:
            snapshot, source_ids = _load_snapshot(connection)
        finally:
            connection.close()
        return _new_store(snapshot, source_ids)

    @classmethod
    def from_connection(
        cls,
        connection: sqlite3.Connection,
    ) -> SourceAuthorityStore:
        """Load from one caller-owned connection, forcing query-only mode."""

        if cls is not SourceAuthorityStore:
            raise TypeError(
                "SourceAuthorityStore subclasses are not supported"
            )
        snapshot, source_ids = _load_snapshot(connection)
        return _new_store(snapshot, source_ids)

    @property
    def digest(self) -> str:
        if type(self) is not SourceAuthorityStore:
            raise TypeError("source authority store must be exact")
        return self._snapshot.digest

    @property
    def source_ids(self) -> tuple[str, ...]:
        if type(self) is not SourceAuthorityStore:
            raise TypeError("source authority store must be exact")
        return self._source_ids

    def adapter_for(
        self,
        source_ids: tuple[str, ...],
        /,
    ) -> SourceAuthorityAdapter:
        """Return the retained adapter for one exact canonical source scope."""

        if type(self) is not SourceAuthorityStore:
            raise TypeError("source authority store must be exact")
        if type(source_ids) is not tuple:
            raise TypeError("authority adapter scope must be an exact tuple")
        if (
            not source_ids
            or any(type(item) is not str for item in source_ids)
            or source_ids != tuple(sorted(source_ids))
            or len(source_ids) != len(set(source_ids))
        ):
            raise SourceAuthorityStoreError(
                "authority adapter scope must be nonempty, unique, and sorted"
            )
        unknown = tuple(
            source_id
            for source_id in source_ids
            if source_id not in self._source_ids
        )
        if unknown:
            raise SourceAuthorityStoreError(
                "authority adapter scope contains unknown sources: "
                f"{unknown}"
            )
        with self._lock:
            adapter = self._adapters.get(source_ids)
            if adapter is None:
                adapter = self._snapshot.adapter(source_ids)
                self._adapters[source_ids] = adapter
            return adapter

    def __copy__(self) -> SourceAuthorityStore:
        raise TypeError("SourceAuthorityStore cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> SourceAuthorityStore:
        raise TypeError("SourceAuthorityStore cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("SourceAuthorityStore cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("SourceAuthorityStore cannot be pickled")


def _new_store(
    snapshot: AuthoritySnapshot,
    source_ids: tuple[str, ...],
) -> SourceAuthorityStore:
    if (
        type(snapshot) is not AuthoritySnapshot
        or type(source_ids) is not tuple
        or any(type(item) is not str for item in source_ids)
        or source_ids != tuple(sorted(source_ids))
        or len(source_ids) != len(set(source_ids))
    ):
        raise SourceAuthorityStoreError(
            "loaded authority store state is invalid"
        )
    result = object.__new__(SourceAuthorityStore)
    object.__setattr__(result, "_snapshot", snapshot)
    object.__setattr__(result, "_source_ids", source_ids)
    object.__setattr__(result, "_adapters", {})
    object.__setattr__(result, "_lock", RLock())
    return result


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "SourceAuthorityStore",
    "SourceAuthorityStoreError",
]

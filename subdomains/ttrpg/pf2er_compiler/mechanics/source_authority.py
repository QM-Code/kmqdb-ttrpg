"""Verified, duplicate-preserving source authority contracts.

This module is deliberately below the PF2ER mechanic-family layer.  It knows
how to validate exact cache rows, resolve a ToC locator to an exact raw JSON
address, and issue source receipts.  It does not know how to query a cache,
normalize a creature, or interpret any game mechanic.

``AuthoritySnapshot`` and ``SourceAuthorityAdapter`` are trusted,
server-private contexts.  The server constructs them from its authenticated
local cache, retains their exact identities, and never accepts either object
from browser, request, plugin, or other serialized input.  They are not
cryptographic capabilities.  Python code able to use ``object.__setattr__``,
extract closure cells, or monkeypatch their methods already has server code
execution and is outside this boundary.

The server's authority store is responsible for retaining the adapter and
invoking mechanic-family compilers with it.  A request may select public data
such as source IDs or submit a serialized claim, but it never supplies the
adapter used for verification.

``SourceReceipt`` is an untrusted serialized claim.  Parsing and validating
its own digest never makes it authoritative.  Only
``SourceAuthorityAdapter.reload`` can turn it back into a verified selection,
and reload always resolves the claim against the adapter's trusted
``AuthoritySnapshot``.

Verified carriers, selections, and rule receipts are likewise untrusted when
received from a caller or retained across a boundary.  Mechanic entry points
use the server-owned adapter and call ``validate_selection``,
``validate_rule``, or ``require_shared_authority`` before reading evidence.
Those methods structurally re-resolve the public claims against the retained
immutable indexes.  A validated rule still has to match one of that mechanic
family's immutable reviewed ``RuleRequirement`` values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, TypeAlias, final

from ...source_content import (
    MAX_IDENTIFIER_BYTES,
    MAX_MANIFEST_SECTIONS,
    MAX_MANIFEST_SOURCES,
    MAX_PATH_STEPS,
    MAX_RAW_BYTES,
    MAX_RAW_DEPTH,
    MAX_RAW_NODES,
    MAX_ROW_BYTES,
    SourceContentError,
    ValidatedSourceArray,
    ValidatedSourceMember,
    ValidatedSourceObject,
    ValidatedSourceValue,
    validate_source_content as _validate_source_content,
)
from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RawSourceValue,
)


AUTHORITY_SCHEMA = 1
AUTHORITY_RULESET = "pf2er"
RECEIPT_SCHEMA = 1
RECEIPT_KIND = "pf2er-source-receipt"

_SHA256_LENGTH = 64
_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class SourceAuthorityError(ValueError):
    """Base class for rejected source-authority claims."""


class AuthorityManifestError(SourceAuthorityError):
    """The authority snapshot or one of its exact rows is invalid."""


class SourceAddressError(SourceAuthorityError):
    """An exact source address is malformed or cannot be resolved."""


class SourceReceiptError(SourceAuthorityError):
    """A serialized receipt is malformed or disagrees with authority."""


class StaleSourceReceiptError(SourceReceiptError):
    """A receipt belongs to another authority snapshot."""


class SourceReviewError(SourceAuthorityError):
    """Verified provider evidence differs from its reviewed expectation."""


def _require_exact_keys(
    value: object,
    expected: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise SourceAuthorityError(f"{label} must be an object")
    actual = frozenset(dict.keys(value))
    if actual != expected or any(type(key) is not str for key in actual):
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SourceAuthorityError(
            f"{label} fields are invalid; missing={missing}, extra={extra}"
        )
    return value


def _require_text(
    value: object,
    label: str,
    *,
    trimmed: bool = True,
) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise SourceAuthorityError(f"{label} must be a non-empty string")
    if trimmed and value != value.strip():
        raise SourceAuthorityError(f"{label} must be trimmed")
    if len(value.encode("utf-8")) > MAX_IDENTIFIER_BYTES:
        raise SourceAuthorityError(f"{label} exceeds its byte bound")
    return value


def _require_source_id(value: object, label: str) -> str:
    result = _require_text(value, label)
    if _SOURCE_ID_RE.fullmatch(result) is None:
        raise SourceAuthorityError(f"{label} has invalid source-id syntax")
    return result


def _require_sha256(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SourceAuthorityError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _require_nonnegative_bounded_int(
    value: object,
    label: str,
    *,
    maximum: int,
) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        raise SourceAuthorityError(
            f"{label} must be an integer from 0 through {maximum}"
        )
    return value


def text_sha256(value: str, /) -> str:
    """Hash one exact stored text value as UTF-8."""

    if type(value) is not str:
        raise TypeError("text_sha256 requires a string")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _closed_json_value(
    value: object,
    *,
    depth: int = 0,
    counter: list[int] | None = None,
) -> object:
    if counter is None:
        counter = [0]
    if depth > MAX_RAW_DEPTH:
        raise SourceAuthorityError(
            "canonical JSON exceeds its depth bound"
        )
    counter[0] += 1
    if counter[0] > MAX_RAW_NODES:
        raise SourceAuthorityError(
            "canonical JSON exceeds its node bound"
        )
    value_type = type(value)
    if value_type is dict:
        result: dict[str, object] = {}
        for key, item in dict.items(value):
            if type(key) is not str:
                raise SourceAuthorityError(
                    "canonical JSON object keys must be exact strings"
                )
            result[key] = _closed_json_value(
                item,
                depth=depth + 1,
                counter=counter,
            )
        return result
    if value_type is list:
        return [
            _closed_json_value(
                item,
                depth=depth + 1,
                counter=counter,
            )
            for item in value
        ]
    if value is None or value_type in {bool, int, str}:
        return value
    if value_type is float:
        if not math.isfinite(value):
            raise SourceAuthorityError(
                "canonical JSON numbers must be finite"
            )
        return value
    raise SourceAuthorityError(
        "canonical JSON rejects subclassed or non-JSON value: "
        f"{value_type.__name__}"
    )


def canonical_json_bytes(value: object, /) -> bytes:
    """Return the schema's canonical JSON encoding."""

    try:
        encoded = json.dumps(
            _closed_json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as failure:
        raise SourceAuthorityError(
            "value is not canonical JSON-compatible"
        ) from failure
    if len(encoded) > MAX_ROW_BYTES:
        raise SourceAuthorityError(
            "canonical JSON exceeds its byte bound"
        )
    return encoded


def authority_manifest_digest(value: dict[str, Any], /) -> str:
    """Hash a manifest payload that does not yet contain ``digest``."""

    _require_exact_keys(
        value,
        frozenset({"schema", "ruleset", "sources", "sections"}),
        "authority manifest digest payload",
    )
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _reject_json_constant(value: str) -> None:
    raise SourceAuthorityError(f"non-finite JSON number is invalid: {value}")


def _finite_json_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise SourceAuthorityError(
            f"JSON number overflows a finite float: {value}"
        )
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SourceAuthorityError(
                f"ordinary JSON object member is duplicated: {key}"
            )
        result[key] = value
    return result


def _strict_json(value: str, label: str) -> Any:
    if type(value) is not str:
        raise SourceAuthorityError(f"{label} must be exact stored text")
    if len(value.encode("utf-8")) > MAX_ROW_BYTES:
        raise SourceAuthorityError(f"{label} exceeds its byte bound")
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
    except SourceAuthorityError:
        raise
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ) as failure:
        raise SourceAuthorityError(f"{label} is not strict JSON") from failure
    return _closed_json_value(parsed)


def _validated_raw_value(
    value: ValidatedSourceValue,
) -> RawSourceValue:
    value_type = type(value)
    if value_type is ValidatedSourceObject:
        if any(
            type(member) is not ValidatedSourceMember
            for member in value.members
        ):
            raise TypeError(
                "validated source object contains an invalid member"
            )
        return RawSourceObject(
            members=tuple(
                RawSourceMember(
                    member.key,
                    _validated_raw_value(member.value),
                )
                for member in value.members
            )
        )
    if value_type is ValidatedSourceArray:
        return RawSourceArray(
            items=tuple(
                _validated_raw_value(item)
                for item in value.items
            )
        )
    if value is None or value_type in {bool, int, float, str}:
        return value
    raise TypeError(
        "validated source content contains an invalid value: "
        f"{value_type.__name__}"
    )


def _ordered_source_json(value: str, label: str) -> RawSourceObject:
    try:
        parsed = _validate_source_content(value)
    except (SourceContentError, TypeError) as failure:
        raise SourceAuthorityError(
            f"{label} is not duplicate-preserving JSON"
        ) from failure
    if parsed is None:
        raise SourceAddressError(
            f"{label} is the authenticated no-content sentinel"
        )
    raw = _validated_raw_value(parsed)
    if type(raw) is not RawSourceObject:
        raise SourceAuthorityError(f"{label} must be a JSON object")
    return raw


class _RawWriter:
    __slots__ = ("body", "nodes")

    def __init__(self) -> None:
        self.body = bytearray()
        self.nodes = 0

    def append(self, value: str | bytes) -> None:
        if type(value) is str:
            encoded = str.encode(value, "utf-8")
        elif type(value) is bytes:
            encoded = value
        else:
            raise TypeError("_RawWriter.append requires exact str or bytes")
        if len(self.body) + len(encoded) > MAX_RAW_BYTES:
            raise SourceAuthorityError(
                "canonical raw source exceeds its byte bound"
            )
        self.body.extend(encoded)

    def node(self, depth: int) -> None:
        if depth > MAX_RAW_DEPTH:
            raise SourceAuthorityError(
                "canonical raw source exceeds its depth bound"
            )
        self.nodes += 1
        if self.nodes > MAX_RAW_NODES:
            raise SourceAuthorityError(
                "canonical raw source exceeds its node bound"
            )


def _write_raw(value: RawSourceValue, writer: _RawWriter, depth: int) -> None:
    writer.node(depth)
    value_type = type(value)
    if value_type is RawSourceObject:
        if type(value.members) is not tuple:
            raise TypeError(
                "canonical raw source object members must be an exact tuple"
            )
        writer.append(b"{")
        for index, member in enumerate(value.members):
            if type(member) is not RawSourceMember:
                raise TypeError(
                    "canonical raw source members must be exact "
                    "RawSourceMember values"
                )
            if type(member.key) is not str:
                raise TypeError(
                    "canonical raw source member keys must be exact strings"
                )
            if index:
                writer.append(b",")
            writer.append(
                json.dumps(
                    member.key,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            writer.append(b":")
            _write_raw(member.value, writer, depth + 1)
        writer.append(b"}")
        return
    if value_type is RawSourceArray:
        if type(value.items) is not tuple:
            raise TypeError(
                "canonical raw source array items must be an exact tuple"
            )
        writer.append(b"[")
        for index, item in enumerate(value.items):
            if index:
                writer.append(b",")
            _write_raw(item, writer, depth + 1)
        writer.append(b"]")
        return
    if value_type is dict:
        raise TypeError(
            "canonical raw source rejects mappings because they cannot "
            "prove duplicate preservation"
        )
    if value_type is float and not math.isfinite(value):
        raise SourceAuthorityError(
            "canonical raw source numbers must be finite"
        )
    if value is None or value_type in {bool, int, float, str}:
        try:
            writer.append(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
        except (TypeError, ValueError) as failure:
            raise SourceAuthorityError(
                "canonical raw source primitive is invalid"
            ) from failure
        return
    raise TypeError(
        "canonical raw source value is invalid: "
        f"{type(value).__name__}"
    )


def canonical_raw_bytes(value: RawSourceValue, /) -> bytes:
    """Encode exact raw JSON while retaining member order and duplicates."""

    writer = _RawWriter()
    _write_raw(value, writer, 0)
    return bytes(writer.body)


def raw_source_sha256(value: RawSourceValue, /) -> str:
    return hashlib.sha256(canonical_raw_bytes(value)).hexdigest()


def raw_member_sha256(member: RawSourceMember, /) -> str:
    if type(member) is not RawSourceMember:
        raise TypeError("raw_member_sha256 requires RawSourceMember")
    return raw_source_sha256(
        RawSourceObject(members=(member,))
    )


def validate_section_content(value: str, /) -> None:
    """Validate one exact signed section-content string.

    The exact empty string is the cache's authenticated no-content sentinel.
    Every nonempty value must be a duplicate-preserving JSON object within all
    raw source bounds.  Whitespace-only and other malformed values are not
    sentinels and fail closed.
    """

    try:
        _validate_source_content(value)
    except (SourceContentError, TypeError) as failure:
        raise SourceAuthorityError(
            "section content is invalid"
        ) from failure


@final
@dataclass(frozen=True, slots=True)
class RawMemberStep:
    """Select an exact object pair by absolute, zero-based ordinal."""

    raw_key: str
    member_ordinal: int

    def __post_init__(self) -> None:
        if type(self) is not RawMemberStep:
            raise TypeError("RawMemberStep subclasses are not supported")
        if type(self.raw_key) is not str:
            raise TypeError("RawMemberStep.raw_key must be a string")
        if len(self.raw_key.encode("utf-8")) > MAX_IDENTIFIER_BYTES:
            raise SourceAddressError(
                "RawMemberStep.raw_key exceeds its byte bound"
            )
        _require_nonnegative_bounded_int(
            self.member_ordinal,
            "RawMemberStep.member_ordinal",
            maximum=MAX_RAW_NODES,
        )

    def as_serialized(self) -> dict[str, Any]:
        if type(self) is not RawMemberStep:
            raise TypeError("RawMemberStep subclasses cannot serialize")
        return {
            "kind": "member",
            "rawKey": self.raw_key,
            "memberOrdinal": self.member_ordinal,
        }

    @classmethod
    def from_serialized(cls, value: object) -> RawMemberStep:
        if cls is not RawMemberStep:
            raise TypeError("RawMemberStep subclasses are not supported")
        raw = _require_exact_keys(
            value,
            frozenset({"kind", "rawKey", "memberOrdinal"}),
            "raw member path step",
        )
        if raw["kind"] != "member":
            raise SourceAddressError("raw member path step kind is invalid")
        return RawMemberStep(
            raw_key=raw["rawKey"],
            member_ordinal=raw["memberOrdinal"],
        )


@final
@dataclass(frozen=True, slots=True)
class RawIndexStep:
    """Select an exact array item by zero-based ordinal."""

    item_ordinal: int

    def __post_init__(self) -> None:
        if type(self) is not RawIndexStep:
            raise TypeError("RawIndexStep subclasses are not supported")
        _require_nonnegative_bounded_int(
            self.item_ordinal,
            "RawIndexStep.item_ordinal",
            maximum=MAX_RAW_NODES,
        )

    def as_serialized(self) -> dict[str, Any]:
        if type(self) is not RawIndexStep:
            raise TypeError("RawIndexStep subclasses cannot serialize")
        return {
            "kind": "index",
            "itemOrdinal": self.item_ordinal,
        }

    @classmethod
    def from_serialized(cls, value: object) -> RawIndexStep:
        if cls is not RawIndexStep:
            raise TypeError("RawIndexStep subclasses are not supported")
        raw = _require_exact_keys(
            value,
            frozenset({"kind", "itemOrdinal"}),
            "raw index path step",
        )
        if raw["kind"] != "index":
            raise SourceAddressError("raw index path step kind is invalid")
        return RawIndexStep(item_ordinal=raw["itemOrdinal"])


RawPathStep: TypeAlias = RawMemberStep | RawIndexStep
RawPath: TypeAlias = tuple[RawPathStep, ...]
_FrozenRaw: TypeAlias = tuple[Any, ...]
_FrozenPath: TypeAlias = tuple[tuple[Any, ...], ...]


def _freeze_cached_raw(
    value: RawSourceValue,
) -> tuple[_FrozenRaw, bytes]:
    """Freeze exact raw JSON into tuple/primitive-only authenticated data."""

    value_type = type(value)
    if value_type is RawSourceObject:
        if type(value.members) is not tuple or any(
            type(member) is not RawSourceMember
            for member in value.members
        ):
            raise TypeError("cached raw object members are invalid")
        body = bytearray(b"{")
        frozen_members: list[tuple[str, str, _FrozenRaw]] = []
        for index, member in enumerate(value.members):
            if type(member.key) is not str:
                raise TypeError("cached raw member key must be exact text")
            key = json.dumps(
                member.key,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            child, child_body = _freeze_cached_raw(member.value)
            if index:
                body.extend(b",")
            body.extend(key)
            body.extend(b":")
            body.extend(child_body)
            member_body = b"{" + key + b":" + child_body + b"}"
            frozen_members.append(
                (
                    member.key,
                    hashlib.sha256(member_body).hexdigest(),
                    child,
                )
            )
        body.extend(b"}")
        encoded = bytes(body)
        if len(encoded) > MAX_RAW_BYTES:
            raise SourceAuthorityError(
                "cached raw object exceeds its byte bound"
            )
        return (
            "object",
            hashlib.sha256(encoded).hexdigest(),
            tuple(frozen_members),
        ), encoded
    if value_type is RawSourceArray:
        if type(value.items) is not tuple:
            raise TypeError("cached raw array items are invalid")
        body = bytearray(b"[")
        frozen_items: list[_FrozenRaw] = []
        for index, item in enumerate(value.items):
            child, child_body = _freeze_cached_raw(item)
            if index:
                body.extend(b",")
            body.extend(child_body)
            frozen_items.append(child)
        body.extend(b"]")
        encoded = bytes(body)
        if len(encoded) > MAX_RAW_BYTES:
            raise SourceAuthorityError(
                "cached raw array exceeds its byte bound"
            )
        return (
            "array",
            hashlib.sha256(encoded).hexdigest(),
            tuple(frozen_items),
        ), encoded
    if value is None or value_type in {bool, int, float, str}:
        if value_type is float and not math.isfinite(value):
            raise SourceAuthorityError(
                "cached raw number must be finite"
            )
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return (
            "primitive",
            hashlib.sha256(encoded).hexdigest(),
            value,
        ), encoded
    raise TypeError(
        f"cached raw value has an invalid type: {value_type.__name__}"
    )


def _cached_raw_digest(value: _FrozenRaw) -> str:
    if (
        type(value) is not tuple
        or len(value) != 3
        or value[0] not in {"object", "array", "primitive"}
    ):
        raise AuthorityManifestError(
            "authority cached raw value is invalid"
        )
    return _require_sha256(
        value[1],
        "authority cached raw digest",
    )


def _materialize_cached_raw(value: _FrozenRaw) -> RawSourceValue:
    digest = _cached_raw_digest(value)
    kind = value[0]
    payload = value[2]
    if kind == "object":
        if type(payload) is not tuple:
            raise AuthorityManifestError(
                "authority cached raw object is invalid"
            )
        members: list[RawSourceMember] = []
        for item in payload:
            if (
                type(item) is not tuple
                or len(item) != 3
                or type(item[0]) is not str
            ):
                raise AuthorityManifestError(
                    "authority cached raw member is invalid"
                )
            _require_sha256(
                item[1],
                "authority cached raw member digest",
            )
            members.append(
                RawSourceMember(
                    item[0],
                    _materialize_cached_raw(item[2]),
                )
            )
        result: RawSourceValue = RawSourceObject(
            members=tuple(members)
        )
    elif kind == "array":
        if type(payload) is not tuple:
            raise AuthorityManifestError(
                "authority cached raw array is invalid"
            )
        result = RawSourceArray(
            items=tuple(
                _materialize_cached_raw(item)
                for item in payload
            )
        )
    else:
        if (
            payload is not None
            and type(payload) not in {bool, int, float, str}
        ):
            raise AuthorityManifestError(
                "authority cached raw primitive is invalid"
            )
        if type(payload) is float and not math.isfinite(payload):
            raise AuthorityManifestError(
                "authority cached raw number is invalid"
            )
        result = payload
    if raw_source_sha256(result) != digest:
        raise AuthorityManifestError(
            "authority cached raw value disagrees with its digest"
        )
    return result


def _freeze_cached_path(path: RawPath) -> _FrozenPath:
    path = _path(path, "authority cached raw path")
    result: list[tuple[Any, ...]] = []
    for step in path:
        if type(step) is RawMemberStep:
            result.append(
                ("member", step.raw_key, step.member_ordinal)
            )
        else:
            result.append(("index", step.item_ordinal))
    return tuple(result)


def _materialize_cached_path(path: _FrozenPath) -> RawPath:
    if type(path) is not tuple or len(path) > MAX_PATH_STEPS:
        raise AuthorityManifestError(
            "authority cached raw path is invalid"
        )
    result: list[RawPathStep] = []
    for step in path:
        if (
            type(step) is tuple
            and len(step) == 3
            and step[0] == "member"
            and type(step[1]) is str
        ):
            result.append(RawMemberStep(step[1], step[2]))
        elif (
            type(step) is tuple
            and len(step) == 2
            and step[0] == "index"
        ):
            result.append(RawIndexStep(step[1]))
        else:
            raise AuthorityManifestError(
                "authority cached raw path step is invalid"
            )
    return tuple(result)


def _resolve_cached_path(
    root: _FrozenRaw,
    path: RawPath,
) -> tuple[_FrozenRaw, str | None]:
    current = root
    selected_member_digest: str | None = None
    for index, step in enumerate(
        _path(path, "authority cached resolution path")
    ):
        _cached_raw_digest(current)
        if type(step) is RawMemberStep:
            if current[0] != "object" or type(current[2]) is not tuple:
                raise SourceAddressError(
                    f"path step {index} requires an object"
                )
            members = current[2]
            if step.member_ordinal >= len(members):
                raise SourceAddressError(
                    f"path step {index} member ordinal is out of range"
                )
            member = members[step.member_ordinal]
            if (
                type(member) is not tuple
                or len(member) != 3
                or member[0] != step.raw_key
            ):
                raise SourceAddressError(
                    f"path step {index} raw key disagrees with its ordinal"
                )
            selected_member_digest = _require_sha256(
                member[1],
                "authority cached member digest",
            )
            current = member[2]
        elif type(step) is RawIndexStep:
            if current[0] != "array" or type(current[2]) is not tuple:
                raise SourceAddressError(
                    f"path step {index} requires an array"
                )
            if step.item_ordinal >= len(current[2]):
                raise SourceAddressError(
                    f"path step {index} item ordinal is out of range"
                )
            current = current[2][step.item_ordinal]
    _cached_raw_digest(current)
    return current, selected_member_digest


def _step_serialized(step: RawPathStep) -> dict[str, Any]:
    if type(step) is RawMemberStep:
        return {
            "kind": "member",
            "rawKey": step.raw_key,
            "memberOrdinal": step.member_ordinal,
        }
    if type(step) is RawIndexStep:
        return {
            "kind": "index",
            "itemOrdinal": step.item_ordinal,
        }
    raise SourceAddressError(
        "only exact raw path-step types can serialize"
    )


def _path(value: object, label: str) -> RawPath:
    if type(value) not in {list, tuple}:
        raise SourceAddressError(f"{label} must be an ordered path")
    if len(value) > MAX_PATH_STEPS:
        raise SourceAddressError(f"{label} exceeds its step bound")
    result = tuple(value)
    if any(
        type(step) not in {RawMemberStep, RawIndexStep}
        for step in result
    ):
        raise SourceAddressError(
            f"{label} must contain only exact raw path steps"
        )
    return result


def _serialized_path(value: object, label: str) -> RawPath:
    if type(value) is not list:
        raise SourceAddressError(f"{label} must be an array")
    if len(value) > MAX_PATH_STEPS:
        raise SourceAddressError(f"{label} exceeds its step bound")
    result: list[RawPathStep] = []
    for index, step_value in enumerate(value):
        if type(step_value) is not dict:
            raise SourceAddressError(f"{label}[{index}] must be an object")
        kind = dict.get(step_value, "kind")
        if kind == "member":
            result.append(RawMemberStep.from_serialized(step_value))
        elif kind == "index":
            result.append(RawIndexStep.from_serialized(step_value))
        else:
            raise SourceAddressError(
                f"{label}[{index}] has an unknown path-step kind"
            )
    return tuple(result)


@final
@dataclass(frozen=True, slots=True)
class TextSpan:
    """A non-empty, zero-based Python-string span."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if type(self) is not TextSpan:
            raise TypeError("TextSpan subclasses are not supported")
        _require_nonnegative_bounded_int(
            self.start,
            "TextSpan.start",
            maximum=MAX_RAW_BYTES,
        )
        _require_nonnegative_bounded_int(
            self.end,
            "TextSpan.end",
            maximum=MAX_RAW_BYTES,
        )
        if self.end <= self.start:
            raise SourceAddressError(
                "TextSpan.end must be greater than TextSpan.start"
            )

    def as_serialized(self) -> dict[str, int]:
        if type(self) is not TextSpan:
            raise TypeError("TextSpan subclasses cannot serialize")
        return {"start": self.start, "end": self.end}

    @classmethod
    def from_serialized(cls, value: object) -> TextSpan:
        if cls is not TextSpan:
            raise TypeError("TextSpan subclasses are not supported")
        raw = _require_exact_keys(
            value,
            frozenset({"start", "end"}),
            "text span",
        )
        return TextSpan(start=raw["start"], end=raw["end"])


@final
@dataclass(frozen=True, slots=True)
class SourceAddress:
    """Exact raw address beneath one verified ToC locator."""

    source_id: str
    locator: str
    section_id: str
    target_path: RawPath = ()
    carrier_path: RawPath = ()
    selection_path: RawPath = ()
    span: TextSpan | None = None

    def __post_init__(self) -> None:
        if type(self) is not SourceAddress:
            raise TypeError("SourceAddress subclasses are not supported")
        _require_source_id(
            self.source_id,
            "SourceAddress.source_id",
        )
        for field_name in ("locator", "section_id"):
            _require_text(
                getattr(self, field_name),
                f"SourceAddress.{field_name}",
            )
        for field_name in (
            "target_path",
            "carrier_path",
            "selection_path",
        ):
            object.__setattr__(
                self,
                field_name,
                _path(
                    getattr(self, field_name),
                    f"SourceAddress.{field_name}",
                ),
            )
        total_steps = (
            len(self.target_path)
            + len(self.carrier_path)
            + len(self.selection_path)
        )
        if total_steps > MAX_PATH_STEPS:
            raise SourceAddressError(
                "SourceAddress combined paths exceed their step bound"
            )
        if self.span is not None and type(self.span) is not TextSpan:
            raise TypeError("SourceAddress.span must be TextSpan or None")

    def as_serialized(self) -> dict[str, Any]:
        if type(self) is not SourceAddress:
            raise TypeError("SourceAddress subclasses cannot serialize")
        _require_source_id(
            self.source_id,
            "SourceAddress.source_id",
        )
        _require_text(self.locator, "SourceAddress.locator")
        _require_text(self.section_id, "SourceAddress.section_id")
        if any(
            type(getattr(self, field_name)) is not tuple
            for field_name in (
                "target_path",
                "carrier_path",
                "selection_path",
            )
        ):
            raise SourceAddressError(
                "stored SourceAddress paths must be exact tuples"
            )
        target_path = _path(
            self.target_path,
            "SourceAddress.target_path",
        )
        carrier_path = _path(
            self.carrier_path,
            "SourceAddress.carrier_path",
        )
        selection_path = _path(
            self.selection_path,
            "SourceAddress.selection_path",
        )
        if (
            len(target_path)
            + len(carrier_path)
            + len(selection_path)
            > MAX_PATH_STEPS
        ):
            raise SourceAddressError(
                "SourceAddress combined paths exceed their step bound"
            )
        if self.span is not None and type(self.span) is not TextSpan:
            raise SourceAddressError(
                "SourceAddress.span must be exact TextSpan or None"
            )
        return {
            "sourceId": self.source_id,
            "locator": self.locator,
            "sectionId": self.section_id,
            "targetPath": [
                _step_serialized(step) for step in target_path
            ],
            "carrierPath": [
                _step_serialized(step) for step in carrier_path
            ],
            "selectionPath": [
                _step_serialized(step) for step in selection_path
            ],
            "span": (
                {"start": self.span.start, "end": self.span.end}
                if self.span is not None
                else None
            ),
        }

    @classmethod
    def from_serialized(cls, value: object) -> SourceAddress:
        if cls is not SourceAddress:
            raise TypeError("SourceAddress subclasses are not supported")
        raw = _require_exact_keys(
            value,
            frozenset(
                {
                    "sourceId",
                    "locator",
                    "sectionId",
                    "targetPath",
                    "carrierPath",
                    "selectionPath",
                    "span",
                }
            ),
            "source address",
        )
        span = (
            None
            if raw["span"] is None
            else TextSpan.from_serialized(raw["span"])
        )
        return SourceAddress(
            source_id=raw["sourceId"],
            locator=raw["locator"],
            section_id=raw["sectionId"],
            target_path=_serialized_path(
                raw["targetPath"],
                "source address targetPath",
            ),
            carrier_path=_serialized_path(
                raw["carrierPath"],
                "source address carrierPath",
            ),
            selection_path=_serialized_path(
                raw["selectionPath"],
                "source address selectionPath",
            ),
            span=span,
        )


@final
@dataclass(frozen=True, slots=True)
class SourceReceipt:
    """An immutable but unverified serialized source claim."""

    ruleset: str
    authority_digest: str
    address: SourceAddress
    block_sha256: str
    member_sha256: str | None
    value_sha256: str
    selection_sha256: str

    def __post_init__(self) -> None:
        if type(self) is not SourceReceipt:
            raise TypeError("SourceReceipt subclasses are not supported")
        _require_text(self.ruleset, "SourceReceipt.ruleset")
        _require_sha256(
            self.authority_digest,
            "SourceReceipt.authority_digest",
        )
        if type(self.address) is not SourceAddress:
            raise TypeError("SourceReceipt.address must be SourceAddress")
        for field_name in (
            "block_sha256",
            "value_sha256",
            "selection_sha256",
        ):
            _require_sha256(
                getattr(self, field_name),
                f"SourceReceipt.{field_name}",
            )
        if self.member_sha256 is not None:
            _require_sha256(
                self.member_sha256,
                "SourceReceipt.member_sha256",
            )

    def _without_digest(self) -> dict[str, Any]:
        if type(self) is not SourceReceipt:
            raise TypeError("SourceReceipt subclasses cannot serialize")
        _require_text(self.ruleset, "SourceReceipt.ruleset")
        _require_sha256(
            self.authority_digest,
            "SourceReceipt.authority_digest",
        )
        if type(self.address) is not SourceAddress:
            raise SourceReceiptError(
                "source receipt address must be exact SourceAddress"
            )
        for field_name in (
            "block_sha256",
            "value_sha256",
            "selection_sha256",
        ):
            _require_sha256(
                getattr(self, field_name),
                f"SourceReceipt.{field_name}",
            )
        if self.member_sha256 is not None:
            _require_sha256(
                self.member_sha256,
                "SourceReceipt.member_sha256",
            )
        return {
            "schema": RECEIPT_SCHEMA,
            "kind": RECEIPT_KIND,
            "ruleset": self.ruleset,
            "authorityDigest": self.authority_digest,
            "address": SourceAddress.as_serialized(self.address),
            "hashes": {
                "blockSha256": self.block_sha256,
                "memberSha256": self.member_sha256,
                "valueSha256": self.value_sha256,
                "selectionSha256": self.selection_sha256,
            },
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(self._without_digest())
        ).hexdigest()

    def as_serialized(self) -> dict[str, Any]:
        if type(self) is not SourceReceipt:
            raise TypeError("SourceReceipt subclasses cannot serialize")
        return {**self._without_digest(), "digest": self.digest}

    def as_json(self) -> str:
        if type(self) is not SourceReceipt:
            raise TypeError("SourceReceipt subclasses cannot serialize")
        return canonical_json_bytes(self.as_serialized()).decode("utf-8")

    @classmethod
    def from_serialized(cls, value: object) -> SourceReceipt:
        if cls is not SourceReceipt:
            raise TypeError("SourceReceipt subclasses are not supported")
        raw = _require_exact_keys(
            value,
            frozenset(
                {
                    "schema",
                    "kind",
                    "ruleset",
                    "authorityDigest",
                    "address",
                    "hashes",
                    "digest",
                }
            ),
            "source receipt",
        )
        if (
            type(raw["schema"]) is not int
            or raw["schema"] != RECEIPT_SCHEMA
        ):
            raise SourceReceiptError("source receipt schema is unsupported")
        if (
            type(raw["kind"]) is not str
            or raw["kind"] != RECEIPT_KIND
        ):
            raise SourceReceiptError("source receipt kind is unsupported")
        hashes = _require_exact_keys(
            raw["hashes"],
            frozenset(
                {
                    "blockSha256",
                    "memberSha256",
                    "valueSha256",
                    "selectionSha256",
                }
            ),
            "source receipt hashes",
        )
        receipt = SourceReceipt(
            ruleset=raw["ruleset"],
            authority_digest=raw["authorityDigest"],
            address=SourceAddress.from_serialized(raw["address"]),
            block_sha256=hashes["blockSha256"],
            member_sha256=hashes["memberSha256"],
            value_sha256=hashes["valueSha256"],
            selection_sha256=hashes["selectionSha256"],
        )
        supplied_digest = _require_sha256(
            raw["digest"],
            "source receipt digest",
        )
        if supplied_digest != receipt.digest:
            raise SourceReceiptError("source receipt digest disagrees")
        return receipt

    @classmethod
    def from_json(cls, value: str) -> SourceReceipt:
        parsed = _strict_json(value, "source receipt")
        return cls.from_serialized(parsed)


@dataclass(frozen=True, slots=True)
class _SourceEntry:
    source_id: str
    payload_sha256: str
    toc_sha256: str

    def as_serialized(self) -> dict[str, str]:
        if type(self) is not _SourceEntry:
            raise TypeError("source authority entry must be exact")
        _require_source_id(self.source_id, "source authority entry id")
        _require_sha256(
            self.payload_sha256,
            "source authority entry payload hash",
        )
        _require_sha256(
            self.toc_sha256,
            "source authority entry ToC hash",
        )
        return {
            "id": self.source_id,
            "payloadSha256": self.payload_sha256,
            "tocSha256": self.toc_sha256,
        }


@dataclass(frozen=True, slots=True)
class _SectionEntry:
    section_id: str
    source_id: str
    payload_sha256: str
    content_sha256: str

    def as_serialized(self) -> dict[str, str]:
        if type(self) is not _SectionEntry:
            raise TypeError("section authority entry must be exact")
        _require_text(self.section_id, "section authority entry id")
        _require_source_id(
            self.source_id,
            "section authority entry source id",
        )
        _require_sha256(
            self.payload_sha256,
            "section authority entry payload hash",
        )
        _require_sha256(
            self.content_sha256,
            "section authority entry content hash",
        )
        return {
            "id": self.section_id,
            "sourceId": self.source_id,
            "payloadSha256": self.payload_sha256,
            "contentSha256": self.content_sha256,
        }


def _exact_text_rows(
    value: object,
    expected_ids: tuple[str, ...],
    label: str,
) -> dict[str, str]:
    if type(value) is not dict:
        raise AuthorityManifestError(f"{label} must be a mapping")
    if (
        any(type(key) is not str for key in dict.keys(value))
        or frozenset(dict.keys(value)) != frozenset(expected_ids)
    ):
        raise AuthorityManifestError(
            f"{label} keys do not exactly match the authority manifest"
        )
    result: dict[str, str] = {}
    for row_id in expected_ids:
        row = value[row_id]
        if type(row) is not str:
            raise AuthorityManifestError(
                f"{label}[{row_id!r}] must be exact stored text"
            )
        if len(row.encode("utf-8")) > MAX_ROW_BYTES:
            raise AuthorityManifestError(
                f"{label}[{row_id!r}] exceeds its byte bound"
            )
        result[row_id] = row
    return result


def _exact_identifier_rows(
    value: object,
    expected_ids: tuple[str, ...],
    label: str,
) -> dict[str, str]:
    if type(value) is not dict:
        raise AuthorityManifestError(f"{label} must be an exact dict")
    if (
        any(type(key) is not str for key in dict.keys(value))
        or frozenset(dict.keys(value)) != frozenset(expected_ids)
    ):
        raise AuthorityManifestError(
            f"{label} keys do not exactly match the authority manifest"
        )
    result: dict[str, str] = {}
    for row_id in expected_ids:
        result[row_id] = _require_source_id(
            dict.__getitem__(value, row_id),
            f"{label}[{row_id!r}]",
        )
    return result


def _build_snapshot_section_root(
    snapshot: object,
    section_id: str,
) -> tuple[Any, ...]:
    if type(section_id) is not str:
        raise TypeError("snapshot root section id must be exact text")
    section_index = getattr(snapshot, "_section_index", None)
    if type(section_index) is not MappingProxyType:
        raise AuthorityManifestError(
            "authority section index is invalid"
        )
    try:
        indexed = section_index[section_id]
    except KeyError as failure:
        raise SourceAddressError(
            f"section is outside this authority snapshot: {section_id}"
        ) from failure
    if type(indexed) is not tuple or len(indexed) != 3:
        raise AuthorityManifestError(
            "authority section index entry is invalid"
        )
    content = snapshot._section_content(section_id)
    expected_content_sha256 = indexed[2]
    if text_sha256(content) != expected_content_sha256:
        raise AuthorityManifestError(
            f"section content hash disagrees: {section_id}"
        )
    if content == "":
        return (expected_content_sha256, None, None)
    raw_root = _ordered_source_json(
        content,
        f"section content {section_id}",
    )
    frozen_root, _root_bytes = _freeze_cached_raw(raw_root)
    actual_root_sha256 = _cached_raw_digest(frozen_root)
    return (
        expected_content_sha256,
        actual_root_sha256,
        frozen_root,
    )


@final
@dataclass(frozen=True, slots=True, init=False)
class AuthoritySnapshot:
    """A validated local-cache manifest retained as server-private context.

    ``as_serialized`` and ``as_json`` expose only the manifest claim.  There
    is deliberately no wire constructor: the server must rebuild a snapshot
    with ``from_rows`` from its own authenticated cache rows.
    """

    ruleset: str
    digest: str
    _sources: tuple[tuple[str, str, str], ...] = field(repr=False)
    _sections: tuple[tuple[str, str, str, str], ...] = field(
        repr=False
    )
    _source_id_set: frozenset[str] = field(repr=False)
    _section_index: MappingProxyType[
        str, tuple[str, str, str]
    ] = field(repr=False)
    _source_tocs: MappingProxyType[str, str] = field(repr=False)
    _section_payloads: MappingProxyType[str, str] = field(repr=False)
    _section_roots: MappingProxyType[str, tuple[Any, ...]] = field(
        repr=False
    )
    _root_loader: Any = field(repr=False, compare=False)
    _locator_index: MappingProxyType[
        tuple[str, str], tuple[Any, ...]
    ] = field(repr=False)
    _label_fields_by_source: MappingProxyType[
        str,
        tuple[tuple[str, tuple[str, ...]], ...],
    ] = field(repr=False)
    _index_digest: str = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "AuthoritySnapshot must be created with "
            "AuthoritySnapshot.from_rows"
        )

    @classmethod
    def from_rows(
        cls,
        manifest: str | dict[str, Any],
        *,
        source_payloads: dict[str, str],
        source_tocs: dict[str, str],
        section_payloads: dict[str, str],
        section_source_ids: dict[str, str],
        hierarchy_vocabulary: dict[str, Any] | None = None,
    ) -> AuthoritySnapshot:
        if cls is not AuthoritySnapshot:
            raise TypeError("AuthoritySnapshot subclasses are not supported")
        if type(manifest) is str:
            parsed_manifest = _strict_json(
                manifest,
                "authority manifest",
            )
            if (
                canonical_json_bytes(parsed_manifest).decode("utf-8")
                != manifest
            ):
                raise AuthorityManifestError(
                    "authority manifest text must use canonical serialization"
                )
        elif type(manifest) is dict:
            parsed_manifest = manifest
        else:
            raise AuthorityManifestError(
                "authority manifest must be JSON text or an object"
            )
        root = _require_exact_keys(
            parsed_manifest,
            frozenset(
                {"schema", "ruleset", "sources", "sections", "digest"}
            ),
            "authority manifest",
        )
        if (
            type(root["schema"]) is not int
            or root["schema"] != AUTHORITY_SCHEMA
        ):
            raise AuthorityManifestError(
                "authority manifest schema is unsupported"
            )
        if (
            type(root["ruleset"]) is not str
            or root["ruleset"] != AUTHORITY_RULESET
        ):
            raise AuthorityManifestError(
                "authority manifest ruleset is unsupported"
            )
        if type(root["sources"]) is not list:
            raise AuthorityManifestError(
                "authority manifest sources must be an array"
            )
        if type(root["sections"]) is not list:
            raise AuthorityManifestError(
                "authority manifest sections must be an array"
            )
        if (
            len(root["sources"]) > MAX_MANIFEST_SOURCES
            or len(root["sections"]) > MAX_MANIFEST_SECTIONS
        ):
            raise AuthorityManifestError(
                "authority manifest exceeds its entry bounds"
            )

        sources: list[_SourceEntry] = []
        for index, source_value in enumerate(root["sources"]):
            source = _require_exact_keys(
                source_value,
                frozenset({"id", "payloadSha256", "tocSha256"}),
                f"authority manifest sources[{index}]",
            )
            sources.append(
                _SourceEntry(
                    source_id=_require_source_id(
                        source["id"],
                        f"authority manifest sources[{index}].id",
                    ),
                    payload_sha256=_require_sha256(
                        source["payloadSha256"],
                        f"authority manifest sources[{index}].payloadSha256",
                    ),
                    toc_sha256=_require_sha256(
                        source["tocSha256"],
                        f"authority manifest sources[{index}].tocSha256",
                    ),
                )
            )
        source_ids = tuple(item.source_id for item in sources)
        if source_ids != tuple(sorted(source_ids)) or len(source_ids) != len(
            set(source_ids)
        ):
            raise AuthorityManifestError(
                "authority manifest sources must be uniquely sorted by id"
            )

        sections: list[_SectionEntry] = []
        for index, section_value in enumerate(root["sections"]):
            section = _require_exact_keys(
                section_value,
                frozenset(
                    {
                        "id",
                        "sourceId",
                        "payloadSha256",
                        "contentSha256",
                    }
                ),
                f"authority manifest sections[{index}]",
            )
            sections.append(
                _SectionEntry(
                    section_id=_require_text(
                        section["id"],
                        f"authority manifest sections[{index}].id",
                    ),
                    source_id=_require_source_id(
                        section["sourceId"],
                        f"authority manifest sections[{index}].sourceId",
                    ),
                    payload_sha256=_require_sha256(
                        section["payloadSha256"],
                        f"authority manifest sections[{index}].payloadSha256",
                    ),
                    content_sha256=_require_sha256(
                        section["contentSha256"],
                        f"authority manifest sections[{index}].contentSha256",
                    ),
                )
            )
        section_ids = tuple(item.section_id for item in sections)
        if section_ids != tuple(sorted(section_ids)) or len(section_ids) != len(
            set(section_ids)
        ):
            raise AuthorityManifestError(
                "authority manifest sections must be uniquely sorted by id"
            )
        unknown_owners = sorted(
            {
                item.source_id
                for item in sections
                if item.source_id not in source_ids
            }
        )
        if unknown_owners:
            raise AuthorityManifestError(
                "authority manifest sections have unknown source owners: "
                f"{unknown_owners}"
            )

        manifest_without_digest = {
            "schema": AUTHORITY_SCHEMA,
            "ruleset": AUTHORITY_RULESET,
            "sources": [item.as_serialized() for item in sources],
            "sections": [item.as_serialized() for item in sections],
        }
        expected_digest = authority_manifest_digest(
            manifest_without_digest
        )
        supplied_digest = _require_sha256(
            root["digest"],
            "authority manifest digest",
        )
        if supplied_digest != expected_digest:
            raise AuthorityManifestError(
                "authority manifest digest disagrees"
            )

        exact_source_payloads = _exact_text_rows(
            source_payloads,
            source_ids,
            "source payload rows",
        )
        exact_source_tocs = _exact_text_rows(
            source_tocs,
            source_ids,
            "source ToC rows",
        )
        exact_section_payloads = _exact_text_rows(
            section_payloads,
            section_ids,
            "section payload rows",
        )
        exact_section_source_ids = _exact_identifier_rows(
            section_source_ids,
            section_ids,
            "section source-id rows",
        )

        if hierarchy_vocabulary is None:
            hierarchy_vocabulary = {}
        if type(hierarchy_vocabulary) is not dict:
            raise AuthorityManifestError(
                "authority hierarchy vocabulary must be an object"
            )
        parsed_tocs: dict[str, list[Any]] = {}
        label_fields_by_source: dict[
            str,
            tuple[tuple[str, tuple[str, ...]], ...],
        ] = {}
        for entry in sources:
            payload_text = exact_source_payloads[entry.source_id]
            toc_text = exact_source_tocs[entry.source_id]
            if text_sha256(payload_text) != entry.payload_sha256:
                raise AuthorityManifestError(
                    f"source payload hash disagrees: {entry.source_id}"
                )
            if text_sha256(toc_text) != entry.toc_sha256:
                raise AuthorityManifestError(
                    f"source ToC hash disagrees: {entry.source_id}"
                )
            payload = _strict_json(
                payload_text,
                f"source payload {entry.source_id}",
            )
            toc = _strict_json(
                toc_text,
                f"source ToC {entry.source_id}",
            )
            if type(payload) is not dict:
                raise AuthorityManifestError(
                    f"source payload must be an object: {entry.source_id}"
                )
            if dict.get(payload, "id") != entry.source_id:
                raise AuthorityManifestError(
                    f"source payload id disagrees: {entry.source_id}"
                )
            if type(toc) is not list:
                raise AuthorityManifestError(
                    f"source ToC must be an array: {entry.source_id}"
                )
            parsed_tocs[entry.source_id] = toc
            label_fields_by_source[entry.source_id] = (
                _source_label_fields(
                    hierarchy_vocabulary,
                    payload,
                    entry.source_id,
                )
            )

        chapter_bindings: list[tuple[str, str]] = []
        for entry in sections:
            if (
                exact_section_source_ids[entry.section_id]
                != entry.source_id
            ):
                raise AuthorityManifestError(
                    "section source-id row disagrees with manifest: "
                    f"{entry.section_id}"
                )
            payload_text = exact_section_payloads[entry.section_id]
            if text_sha256(payload_text) != entry.payload_sha256:
                raise AuthorityManifestError(
                    f"section payload hash disagrees: {entry.section_id}"
                )
            payload = _strict_json(
                payload_text,
                f"section payload {entry.section_id}",
            )
            if type(payload) is not dict:
                raise AuthorityManifestError(
                    f"section payload must be an object: {entry.section_id}"
                )
            if dict.get(payload, "id") != entry.section_id:
                raise AuthorityManifestError(
                    f"section payload id disagrees: {entry.section_id}"
                )
            if dict.get(payload, "source_id") != entry.source_id:
                raise AuthorityManifestError(
                    f"section payload source disagrees: {entry.section_id}"
                )
            content = dict.get(payload, "content")
            if type(content) is not str:
                raise AuthorityManifestError(
                    f"section content must be a string: {entry.section_id}"
                )
            if text_sha256(content) != entry.content_sha256:
                raise AuthorityManifestError(
                    f"section content hash disagrees: {entry.section_id}"
                )
            try:
                validate_section_content(content)
            except (SourceAuthorityError, TypeError) as failure:
                raise AuthorityManifestError(
                    f"section content is invalid: {entry.section_id}"
                ) from failure
            if "chapter_id" in payload:
                chapter_id = payload["chapter_id"]
                if type(chapter_id) is not str:
                    raise AuthorityManifestError(
                        "section chapter_id must be a string: "
                        f"{entry.section_id}"
                    )
                if chapter_id:
                    chapter_bindings.append(
                        (entry.source_id, chapter_id)
                    )

        section_owners = {
            item.section_id: item.source_id for item in sections
        }
        toc_bindings: list[tuple[str, str]] = []
        for source_id, toc in dict.items(parsed_tocs):
            try:
                nodes = _validate_toc_forest(toc)
            except SourceAddressError as failure:
                raise AuthorityManifestError(
                    f"source ToC is invalid: {source_id}"
                ) from failure
            for node in nodes:
                if "section_id" not in node:
                    continue
                section_id = node["section_id"]
                if type(section_id) is not str or not section_id:
                    raise AuthorityManifestError(
                        f"source ToC section binding is invalid: {source_id}"
                    )
                toc_bindings.append((source_id, section_id))
        for source_id, section_id in (*toc_bindings, *chapter_bindings):
            if dict.get(section_owners, section_id) != source_id:
                raise AuthorityManifestError(
                    "authority row reference has missing or foreign section: "
                    f"{source_id}/{section_id}"
                )

        locator_index = _build_locator_index(parsed_tocs)
        index_digest = _authority_index_digest(
            locator_index,
            label_fields_by_source,
        )
        result = object.__new__(AuthoritySnapshot)
        object.__setattr__(result, "ruleset", AUTHORITY_RULESET)
        object.__setattr__(result, "digest", supplied_digest)
        object.__setattr__(
            result,
            "_sources",
            tuple(
                (
                    entry.source_id,
                    entry.payload_sha256,
                    entry.toc_sha256,
                )
                for entry in sources
            ),
        )
        object.__setattr__(
            result,
            "_sections",
            tuple(
                (
                    entry.section_id,
                    entry.source_id,
                    entry.payload_sha256,
                    entry.content_sha256,
                )
                for entry in sections
            ),
        )
        object.__setattr__(
            result,
            "_source_id_set",
            frozenset(source_ids),
        )
        object.__setattr__(
            result,
            "_section_index",
            MappingProxyType(
                {
                    entry.section_id: (
                        entry.source_id,
                        entry.payload_sha256,
                        entry.content_sha256,
                    )
                    for entry in sections
                }
            ),
        )
        object.__setattr__(
            result,
            "_source_tocs",
            MappingProxyType(exact_source_tocs),
        )
        object.__setattr__(
            result,
            "_section_payloads",
            MappingProxyType(exact_section_payloads),
        )
        object.__setattr__(
            result,
            "_locator_index",
            MappingProxyType(locator_index),
        )
        object.__setattr__(
            result,
            "_label_fields_by_source",
            MappingProxyType(label_fields_by_source),
        )
        object.__setattr__(result, "_index_digest", index_digest)
        root_store: dict[str, tuple[Any, ...]] = {}

        def load_root(section_id: str) -> tuple[Any, ...]:
            cached = root_store.get(section_id)
            if cached is None:
                cached = _build_snapshot_section_root(
                    result,
                    section_id,
                )
                root_store[section_id] = cached
            return cached

        object.__setattr__(
            result,
            "_section_roots",
            MappingProxyType(root_store),
        )
        object.__setattr__(result, "_root_loader", load_root)
        result._validate_cached_indexes()
        return result

    def _validate_cached_indexes(self) -> None:
        if (
            type(self) is not AuthoritySnapshot
            or type(self._sources) is not tuple
            or type(self._sections) is not tuple
            or type(self._source_id_set) is not frozenset
            or type(self._section_index) is not MappingProxyType
            or type(self._section_roots) is not MappingProxyType
            or type(self._root_loader)
            is not type(_build_snapshot_section_root)
            or type(self._locator_index) is not MappingProxyType
            or type(self._label_fields_by_source) is not MappingProxyType
        ):
            raise AuthorityManifestError(
                "authority snapshot immutable indexes are invalid"
            )
        _require_sha256(
            self._index_digest,
            "authority snapshot immutable index digest",
        )

    def as_serialized(self) -> dict[str, Any]:
        if type(self) is not AuthoritySnapshot:
            raise TypeError(
                "AuthoritySnapshot subclasses cannot serialize"
            )
        self._validate_cached_indexes()
        if (
            type(self._sources) is not tuple
            or any(
                type(item) is not tuple or len(item) != 3
                for item in self._sources
            )
            or type(self._sections) is not tuple
            or any(
                type(item) is not tuple or len(item) != 4
                for item in self._sections
            )
        ):
            raise AuthorityManifestError(
                "authority snapshot entries are invalid"
            )
        _require_text(self.ruleset, "authority snapshot ruleset")
        if self.ruleset != AUTHORITY_RULESET:
            raise AuthorityManifestError(
                "authority snapshot ruleset is unsupported"
            )
        _require_sha256(self.digest, "authority snapshot digest")
        result = {
            "schema": AUTHORITY_SCHEMA,
            "ruleset": self.ruleset,
            "sources": [
                _SourceEntry(
                    source_id=item[0],
                    payload_sha256=item[1],
                    toc_sha256=item[2],
                ).as_serialized()
                for item in self._sources
            ],
            "sections": [
                _SectionEntry(
                    section_id=item[0],
                    source_id=item[1],
                    payload_sha256=item[2],
                    content_sha256=item[3],
                ).as_serialized()
                for item in self._sections
            ],
            "digest": self.digest,
        }
        expected_digest = authority_manifest_digest(
            {
                "schema": result["schema"],
                "ruleset": result["ruleset"],
                "sources": result["sources"],
                "sections": result["sections"],
            }
        )
        if expected_digest != self.digest:
            raise AuthorityManifestError(
                "authority snapshot entries disagree with its digest"
            )
        return result

    def as_json(self) -> str:
        if type(self) is not AuthoritySnapshot:
            raise TypeError(
                "AuthoritySnapshot subclasses cannot serialize"
            )
        return canonical_json_bytes(self.as_serialized()).decode("utf-8")

    def adapter(
        self,
        allowed_source_ids: tuple[str, ...],
    ) -> SourceAuthorityAdapter:
        if type(self) is not AuthoritySnapshot:
            raise TypeError(
                "AuthoritySnapshot subclasses cannot create adapters"
            )
        self.as_serialized()
        return SourceAuthorityAdapter(self, allowed_source_ids)

    def __copy__(self) -> AuthoritySnapshot:
        raise TypeError("AuthoritySnapshot cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> AuthoritySnapshot:
        raise TypeError("AuthoritySnapshot cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("AuthoritySnapshot cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("AuthoritySnapshot cannot be pickled")

    def _source_entry(self, source_id: str) -> _SourceEntry:
        _require_source_id(source_id, "authority source id")
        self._validate_cached_indexes()
        matches = [item for item in self._sources if item[0] == source_id]
        if len(matches) != 1:
            raise SourceAddressError(
                f"source is outside this authority snapshot: {source_id}"
            )
        item = matches[0]
        return _SourceEntry(
            source_id=item[0],
            payload_sha256=item[1],
            toc_sha256=item[2],
        )

    def _section_entry(self, section_id: str) -> _SectionEntry:
        _require_text(section_id, "authority section id")
        self._validate_cached_indexes()
        try:
            item = self._section_index[section_id]
        except KeyError as failure:
            raise SourceAddressError(
                f"section is outside this authority snapshot: {section_id}"
            ) from failure
        if type(item) is not tuple or len(item) != 3:
            raise AuthorityManifestError(
                "authority section index entry is invalid"
            )
        return _SectionEntry(
            section_id=section_id,
            source_id=item[0],
            payload_sha256=item[1],
            content_sha256=item[2],
        )

    def _cached_section_root(
        self,
        section_id: str,
    ) -> _FrozenRaw:
        self._validate_cached_indexes()
        entry = self._section_entry(section_id)
        cached = self._root_loader(section_id)
        if (
            type(cached) is not tuple
            or len(cached) != 3
            or cached[0] != entry.content_sha256
        ):
            raise AuthorityManifestError(
                "authority cached section root is invalid"
            )
        if cached[2] is None:
            raise SourceAddressError(
                "source section content is the authenticated "
                "no-content sentinel"
            )
        if (
            type(cached[1]) is not str
            or _cached_raw_digest(cached[2]) != cached[1]
        ):
            raise AuthorityManifestError(
                "authority cached section root value disagrees"
            )
        return cached[2]

    def _section_content(self, section_id: str) -> str:
        entry = self._section_entry(section_id)
        if type(self._section_payloads) is not MappingProxyType:
            raise AuthorityManifestError(
                "authority section rows must be immutable"
            )
        try:
            payload_text = self._section_payloads[section_id]
        except KeyError as failure:
            raise SourceAddressError(
                f"section is outside this authority snapshot: {section_id}"
            ) from failure
        if (
            type(payload_text) is not str
            or text_sha256(payload_text) != entry.payload_sha256
        ):
            raise AuthorityManifestError(
                f"section payload row disagrees: {section_id}"
            )
        payload = _strict_json(
            payload_text,
            f"section payload {section_id}",
        )
        if (
            type(payload) is not dict
            or dict.get(payload, "id") != entry.section_id
            or dict.get(payload, "source_id") != entry.source_id
        ):
            raise AuthorityManifestError(
                f"section payload identity disagrees: {section_id}"
            )
        content = dict.get(payload, "content")
        if (
            type(content) is not str
            or text_sha256(content) != entry.content_sha256
        ):
            raise AuthorityManifestError(
                f"section content hash disagrees: {section_id}"
            )
        validate_section_content(content)
        return content

    def _toc(self, source_id: str) -> list[Any]:
        entry = self._source_entry(source_id)
        if type(self._source_tocs) is not MappingProxyType:
            raise AuthorityManifestError(
                "authority ToC rows must be immutable"
            )
        try:
            toc_text = self._source_tocs[source_id]
        except KeyError as failure:
            raise SourceAddressError(
                f"source is outside this authority snapshot: {source_id}"
            ) from failure
        if (
            type(toc_text) is not str
            or text_sha256(toc_text) != entry.toc_sha256
        ):
            raise AuthorityManifestError(
                f"source ToC row disagrees: {source_id}"
            )
        toc = _strict_json(toc_text, f"source ToC {source_id}")
        if type(toc) is not list:
            raise AuthorityManifestError(
                f"source ToC must be an array: {source_id}"
            )
        try:
            _validate_toc_forest(toc)
        except SourceAddressError as failure:
            raise AuthorityManifestError(
                f"source ToC is invalid: {source_id}"
            ) from failure
        return toc

    def _cached_locator_binding(
        self,
        source_id: str,
        locator: str,
    ) -> tuple[str, tuple[str, ...]]:
        self._validate_cached_indexes()
        self._source_entry(source_id)
        _require_text(locator, "source locator")
        try:
            cached = self._locator_index[(source_id, locator)]
        except KeyError as failure:
            raise SourceAddressError(
                "source locator is missing or ambiguous: "
                f"{source_id}/{locator}"
            ) from failure
        if (
            type(cached) is not tuple
            or not cached
            or cached[0] not in {"ok", "error"}
        ):
            raise AuthorityManifestError(
                "authority cached locator entry is invalid"
            )
        if cached[0] == "error":
            if len(cached) != 2 or type(cached[1]) is not str:
                raise AuthorityManifestError(
                    "authority cached locator failure is invalid"
                )
            raise SourceAddressError(cached[1])
        if (
            len(cached) != 4
            or type(cached[1]) is not str
            or type(cached[2]) is not tuple
            or any(type(part) is not str for part in cached[2])
            or (
                cached[3] is not None
                and type(cached[3]) is not str
            )
        ):
            raise AuthorityManifestError(
                "authority cached locator target is invalid"
            )
        section_id = cached[1]
        if self._section_entry(section_id).source_id != source_id:
            raise AuthorityManifestError(
                "authority cached locator owner disagrees"
            )
        return section_id, cached[2]


def _semantic_key(raw_key: str) -> str:
    if raw_key.startswith("^."):
        parts = raw_key.split(".", 2)
        return parts[2] if len(parts) == 3 else raw_key
    if len(raw_key) > 2 and raw_key[1] == "." and raw_key[0] in "!%@#":
        return raw_key[2:]
    return raw_key


def _vocabulary_operators(
    value: object,
    label: str,
) -> dict[str, dict[str, Any]]:
    if value is None or value == "":
        return {}
    if type(value) is str:
        value = _strict_json(value, label)
    if type(value) is not dict:
        raise AuthorityManifestError(f"{label} must be an object")
    operators = dict.get(value, "operators", {})
    if type(operators) is not dict:
        raise AuthorityManifestError(
            f"{label}.operators must be an object"
        )
    result: dict[str, dict[str, Any]] = {}
    for raw_key, definition in dict.items(operators):
        if (
            type(raw_key) is not str
            or not raw_key
            or type(definition) is not dict
        ):
            raise AuthorityManifestError(
                f"{label}.operators contains an invalid definition"
            )
        result[raw_key] = dict(definition)
    return result


def _source_label_fields(
    hierarchy_vocabulary: dict[str, Any],
    source_payload: dict[str, Any],
    source_id: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Project effective special-block label fields for one source."""

    merged = _vocabulary_operators(
        hierarchy_vocabulary,
        "authority hierarchy vocabulary",
    )
    source_operators = _vocabulary_operators(
        dict.get(source_payload, "vocab"),
        f"source vocabulary {source_id}",
    )
    for raw_key, definition in dict.items(source_operators):
        merged[raw_key] = {
            **dict.get(merged, raw_key, {}),
            **definition,
        }
    result: list[tuple[str, tuple[str, ...]]] = []
    for raw_key in sorted(merged):
        definition = merged[raw_key]
        if dict.get(definition, "behavior") != "special-block":
            continue
        configured = dict.get(
            definition,
            "label_field",
            dict.get(definition, "label_fields", "Name"),
        )
        raw_fields = (
            configured
            if type(configured) is list
            else [configured]
        )
        if (
            not raw_fields
            or any(type(field) is not str or not field for field in raw_fields)
            or len(raw_fields) != len(set(raw_fields))
        ):
            raise AuthorityManifestError(
                f"source vocabulary {source_id} has invalid label fields: "
                f"{raw_key}"
            )
        result.append((raw_key, tuple(raw_fields)))
    return tuple(result)


def _semantic_member_label(
    member: RawSourceMember,
    label_fields: tuple[tuple[str, tuple[str, ...]], ...],
) -> str | None:
    """Return a vocabulary-declared label carried by one special block."""

    if (
        type(member) is not RawSourceMember
        or type(member.value) is not RawSourceObject
    ):
        return None
    matching_fields: tuple[str, ...] | None = None
    matching_key = ""
    for operator_key, fields in label_fields:
        if not member.key.startswith(operator_key):
            continue
        exact = len(member.key) == len(operator_key)
        boundary = (
            operator_key.endswith(".")
            or member.key[len(operator_key) :].startswith(".")
        )
        if (
            (exact or boundary)
            and len(operator_key) > len(matching_key)
        ):
            matching_key = operator_key
            matching_fields = fields
    if matching_fields is None:
        return None
    for field in matching_fields:
        values = member.value.values(field)
        if len(values) > 1:
            return None
        if len(values) == 1 and type(values[0]) is str:
            label = values[0].strip()
            if label:
                return label
    return None


def _toc_node_paths(
    forest: object,
) -> tuple[tuple[dict[str, Any], ...], ...]:
    if type(forest) is not list:
        raise SourceAddressError("source ToC forest must be an array")
    result: list[tuple[dict[str, Any], ...]] = []
    pending: list[tuple[object, tuple[dict[str, Any], ...]]] = [
        (node, ())
        for node in reversed(forest)
    ]
    visited = 0
    while pending:
        raw_node, ancestors = pending.pop()
        visited += 1
        if visited > MAX_RAW_NODES:
            raise SourceAddressError("source ToC exceeds its node bound")
        if type(raw_node) is not dict:
            raise SourceAddressError("source ToC node must be an object")
        path = (*ancestors, raw_node)
        result.append(path)
        children = dict.get(raw_node, "children", [])
        if type(children) is not list:
            raise SourceAddressError(
                "source ToC node children must be an array"
            )
        pending.extend(
            (child, path)
            for child in reversed(children)
        )
    return tuple(result)


def _toc_nodes(forest: object) -> tuple[dict[str, Any], ...]:
    return tuple(path[-1] for path in _toc_node_paths(forest))


def _merge_relative_path(
    current: tuple[str, ...],
    candidate: tuple[str, ...],
) -> tuple[str, ...]:
    overlap_limit = min(len(current), len(candidate))
    overlap = 0
    for size in range(overlap_limit, 0, -1):
        if current[-size:] == candidate[:size]:
            overlap = size
            break
    merged = (*current, *candidate[overlap:])
    if len(merged) > MAX_PATH_STEPS:
        raise SourceAddressError(
            "merged source ToC content path exceeds its step bound"
        )
    return merged


def _validate_toc_forest(
    forest: object,
) -> tuple[dict[str, Any], ...]:
    """Validate every ToC path before a snapshot can become authority."""

    if type(forest) is not list:
        raise SourceAddressError("source ToC forest must be an array")
    result: list[dict[str, Any]] = []
    pending: list[
        tuple[object, str | None, tuple[str, ...]]
    ] = [
        (node, None, ())
        for node in reversed(forest)
    ]
    visited = 0
    while pending:
        raw_node, inherited_section, inherited_path = pending.pop()
        visited += 1
        if visited > MAX_RAW_NODES:
            raise SourceAddressError("source ToC exceeds its node bound")
        if type(raw_node) is not dict:
            raise SourceAddressError("source ToC node must be an object")
        node = raw_node
        active_section = inherited_section
        merged_path = inherited_path
        if dict.__contains__(node, "section_id"):
            section_id = dict.__getitem__(node, "section_id")
            try:
                section_id = _require_text(
                    section_id,
                    "source ToC node section_id",
                )
            except SourceAuthorityError as failure:
                raise SourceAddressError(str(failure)) from failure
            if section_id != active_section:
                merged_path = ()
            active_section = section_id
        if dict.__contains__(node, "locator"):
            locator = dict.__getitem__(node, "locator")
            if type(locator) is not str:
                raise SourceAddressError(
                    "source ToC node locator must be an exact string"
                )
            if locator:
                try:
                    _require_text(
                        locator,
                        "source ToC node locator",
                    )
                except SourceAuthorityError as failure:
                    raise SourceAddressError(str(failure)) from failure
        content_path = dict.get(node, "content_path", [])
        if type(content_path) is not list:
            raise SourceAddressError(
                "source ToC node content_path must be an array"
            )
        if len(content_path) > MAX_PATH_STEPS:
            raise SourceAddressError(
                "source ToC node content_path exceeds its step bound"
            )
        exact_path: list[str] = []
        for part in content_path:
            try:
                exact_path.append(
                    _require_text(
                        part,
                        "source ToC content_path item",
                        trimmed=False,
                    )
                )
            except SourceAuthorityError as failure:
                raise SourceAddressError(str(failure)) from failure
        if active_section is not None and exact_path:
            merged_path = _merge_relative_path(
                merged_path,
                tuple(exact_path),
            )
        children = dict.get(node, "children", [])
        if type(children) is not list:
            raise SourceAddressError(
                "source ToC node children must be an array"
            )
        result.append(node)
        pending.extend(
            (child, active_section, merged_path)
            for child in reversed(children)
        )
    return tuple(result)


def _toc_path_binding(
    node_path: tuple[dict[str, Any], ...],
) -> tuple[str, tuple[str, ...]]:
    if (
        type(node_path) is not tuple
        or not node_path
        or any(type(node) is not dict for node in node_path)
    ):
        raise SourceAddressError("source ToC node path is invalid")
    node = node_path[-1]
    section_id = dict.get(node, "section_id")
    if type(section_id) is not str or not section_id:
        raise SourceAddressError(
            "source locator has no section binding"
        )
    active_section: str | None = None
    merged: tuple[str, ...] = ()
    for ancestor in node_path:
        ancestor_section = dict.get(ancestor, "section_id")
        if ancestor_section is not None:
            if type(ancestor_section) is not str or not ancestor_section:
                raise SourceAddressError(
                    "source ToC ancestor section binding is invalid"
                )
            if ancestor_section != active_section:
                merged = ()
            active_section = ancestor_section
        content_path = dict.get(ancestor, "content_path", [])
        if type(content_path) is not list:
            raise SourceAddressError(
                "source ToC ancestor content path must be an array"
            )
        if any(type(part) is not str or not part for part in content_path):
            raise SourceAddressError(
                "source ToC ancestor content path is invalid"
            )
        if active_section == section_id and content_path:
            merged = _merge_relative_path(
                merged,
                tuple(content_path),
            )
    return section_id, merged


def _build_locator_index(
    parsed_tocs: dict[str, list[Any]],
) -> dict[tuple[str, str], tuple[Any, ...]]:
    """Build immutable locator semantics from authenticated ToC rows."""

    result: dict[tuple[str, str], tuple[Any, ...]] = {}
    for source_id in sorted(parsed_tocs):
        paths_by_locator: dict[
            str, list[tuple[dict[str, Any], ...]]
        ] = {}
        for node_path in _toc_node_paths(parsed_tocs[source_id]):
            locator = dict.get(node_path[-1], "locator")
            if type(locator) is str and locator:
                paths_by_locator.setdefault(locator, []).append(node_path)
        for locator in sorted(paths_by_locator):
            key = (source_id, locator)
            matches = paths_by_locator[locator]
            if len(matches) != 1:
                result[key] = (
                    "error",
                    "source locator is missing or ambiguous: "
                    f"{source_id}/{locator}",
                )
                continue
            try:
                section_id, semantic_path = _toc_path_binding(
                    matches[0]
                )
                try:
                    target_label: str | None = _require_text(
                        dict.get(matches[0][-1], "label"),
                        "source ToC node label",
                    )
                except SourceAuthorityError:
                    target_label = None
                result[key] = (
                    "ok",
                    section_id,
                    semantic_path,
                    target_label,
                )
            except (SourceAuthorityError, TypeError) as failure:
                result[key] = ("error", str(failure))
    return result


def _authority_index_digest(
    locator_index: dict[tuple[str, str], tuple[Any, ...]],
    label_fields_by_source: dict[
        str,
        tuple[tuple[str, tuple[str, ...]], ...],
    ],
) -> str:
    locator_rows: list[list[Any]] = []
    for source_id, locator in sorted(locator_index):
        cached = locator_index[(source_id, locator)]
        if type(cached) is not tuple or not cached:
            raise AuthorityManifestError(
                "authority locator index is invalid"
            )
        if cached[0] == "error":
            locator_rows.append(
                [source_id, locator, "error", cached[1]]
            )
        elif cached[0] == "ok" and len(cached) == 4:
            locator_rows.append(
                [
                    source_id,
                    locator,
                    "ok",
                    cached[1],
                    list(cached[2]),
                    cached[3],
                ]
            )
        else:
            raise AuthorityManifestError(
                "authority locator index entry is invalid"
            )
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "locators": locator_rows,
                "labelFields": [
                    [
                        source_id,
                        [
                            [operator, list(fields)]
                            for operator, fields
                            in label_fields_by_source[source_id]
                        ],
                    ]
                    for source_id in sorted(label_fields_by_source)
                ],
            }
        )
    ).hexdigest()


def _toc_target(
    snapshot: AuthoritySnapshot,
    source_id: str,
    locator: str,
) -> tuple[str, tuple[str, ...]]:
    section_id, semantic_path = (
        snapshot._cached_locator_binding(source_id, locator)
    )
    return section_id, semantic_path


def _transparent_semantic_roots(
    root: RawSourceObject,
    path: RawPath,
) -> tuple[tuple[RawSourceObject, RawPath], ...]:
    """Expose objects nested only beneath source-flow ``~.`` wrappers."""

    if type(root) is not RawSourceObject or type(path) is not tuple:
        raise SourceAddressError(
            "transparent semantic search root is invalid"
        )
    result: list[tuple[RawSourceObject, RawPath]] = []
    pending: list[tuple[RawSourceValue, RawPath]] = [(root, path)]
    visited = 0
    while pending:
        value, current_path = pending.pop()
        visited += 1
        if visited > MAX_RAW_NODES:
            raise SourceAddressError(
                "transparent semantic search exceeds its node bound"
            )
        if len(current_path) > MAX_PATH_STEPS:
            raise SourceAddressError(
                "transparent semantic path exceeds its step bound"
            )
        if type(value) is RawSourceArray:
            if type(value.items) is not tuple:
                raise SourceAddressError(
                    "transparent semantic array is invalid"
                )
            pending.extend(
                (
                    item,
                    (*current_path, RawIndexStep(index)),
                )
                for index, item in reversed(
                    tuple(enumerate(value.items))
                )
            )
            continue
        if type(value) is not RawSourceObject:
            continue
        if type(value.members) is not tuple or any(
            type(member) is not RawSourceMember
            for member in value.members
        ):
            raise SourceAddressError(
                "transparent semantic object is invalid"
            )
        result.append((value, current_path))
        for ordinal in range(len(value.members) - 1, -1, -1):
            member = value.members[ordinal]
            if member.key.startswith("~."):
                pending.append(
                    (
                        member.value,
                        (
                            *current_path,
                            RawMemberStep(member.key, ordinal),
                        ),
                    )
                )
    return tuple(result)


def _semantic_suffix_matches(
    root: RawSourceObject,
    semantic_path: tuple[str, ...],
    label_fields: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> tuple[tuple[RawSourceObject, RawPath], ...]:
    candidates: tuple[tuple[RawSourceObject, RawPath], ...] = (
        (root, ()),
    )
    for part in semantic_path:
        exact_matches: list[tuple[RawSourceValue, RawPath]] = []
        semantic_matches: list[tuple[RawSourceValue, RawPath]] = []
        labeled_block_matches: list[
            tuple[RawSourceValue, RawPath]
        ] = []
        for current, current_path in candidates:
            for search_root, search_path in _transparent_semantic_roots(
                current,
                current_path,
            ):
                for ordinal, member in enumerate(search_root.members):
                    match = (
                        member.value,
                        (
                            *search_path,
                            RawMemberStep(member.key, ordinal),
                        ),
                    )
                    if member.key == part:
                        exact_matches.append(match)
                    elif _semantic_key(member.key) == part:
                        semantic_matches.append(match)
                    elif _semantic_member_label(
                        member,
                        label_fields,
                    ) == part:
                        # Label-field blocks are addressed by their declared
                        # semantic label. Retain the containing object as the
                        # locator anchor so the block remains an exact carrier
                        # selected by its duplicate-preserving member ordinal.
                        labeled_block_matches.append(
                            (search_root, search_path)
                        )
        selected = (
            exact_matches
            or semantic_matches
            or labeled_block_matches
        )
        if len(selected) > MAX_RAW_NODES:
            raise SourceAddressError(
                "semantic source search exceeds its candidate bound"
            )
        if len(selected) > 1:
            raise SourceAddressError(
                f"semantic source path is ambiguous at: {part}"
            )
        candidates = tuple(
            (value, path)
            for value, path in selected
            if type(value) is RawSourceObject
        )
        if not candidates:
            return ()
    return candidates


def _semantic_target_path(
    root: RawSourceObject,
    semantic_path: tuple[str, ...],
    label_fields: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> tuple[RawSourceObject, RawPath]:
    if type(root) is not RawSourceObject:
        raise SourceAddressError(
            "semantic source path root must be exact RawSourceObject"
        )
    if type(semantic_path) is not tuple or any(
        type(part) is not str or not part
        for part in semantic_path
    ):
        raise SourceAddressError(
            "semantic source path must be an exact nonempty-string tuple"
        )
    if not semantic_path:
        return root, ()
    # ToC descendants can restart a path relative to their active section.
    # Prefer the longest suffix that has one exact raw realization.  Source
    # flow wrappers (for example ``~.aside``) remain explicit in the returned
    # raw path even though they are transparent to the ToC semantic path.
    for start in range(len(semantic_path)):
        suffix = semantic_path[start:]
        matches = _semantic_suffix_matches(
            root,
            suffix,
            label_fields,
        )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SourceAddressError(
                "semantic source path is ambiguous at suffix: "
                f"{suffix}"
            )
    raise SourceAddressError(
        "semantic source path is missing: "
        f"{semantic_path}"
    )


def _resolve_exact_path(
    root: RawSourceValue,
    path: RawPath,
) -> tuple[RawSourceValue, RawSourceMember | None]:
    if type(path) is not tuple or any(
        type(step) not in {RawMemberStep, RawIndexStep}
        for step in path
    ):
        raise SourceAddressError(
            "exact source path must contain exact path-step types"
        )
    current = root
    selected_member: RawSourceMember | None = None
    for index, step in enumerate(path):
        if type(step) is RawMemberStep:
            if type(current) is not RawSourceObject:
                raise SourceAddressError(
                    f"path step {index} requires an object"
                )
            if type(current.members) is not tuple or any(
                type(member) is not RawSourceMember
                for member in current.members
            ):
                raise SourceAddressError(
                    f"path step {index} encountered an invalid raw object"
                )
            if step.member_ordinal >= len(current.members):
                raise SourceAddressError(
                    f"path step {index} member ordinal is out of range"
                )
            member = current.members[step.member_ordinal]
            if member.key != step.raw_key:
                raise SourceAddressError(
                    f"path step {index} raw key disagrees with its ordinal"
                )
            selected_member = member
            current = member.value
        elif type(step) is RawIndexStep:
            if type(current) is not RawSourceArray:
                raise SourceAddressError(
                    f"path step {index} requires an array"
                )
            if type(current.items) is not tuple:
                raise SourceAddressError(
                    f"path step {index} encountered an invalid raw array"
                )
            if step.item_ordinal >= len(current.items):
                raise SourceAddressError(
                    f"path step {index} item ordinal is out of range"
                )
            current = current.items[step.item_ordinal]
        else:
            raise SourceAddressError(
                f"path step {index} has an invalid type"
            )
    return current, selected_member


def _adapter_index_digest(
    section_roots: dict[str, tuple[Any, ...]],
    locator_index: dict[tuple[str, str], tuple[Any, ...]],
) -> str:
    root_rows: list[list[Any]] = []
    for section_id in sorted(section_roots):
        cached = section_roots[section_id]
        if (
            type(cached) is not tuple
            or len(cached) != 3
            or type(cached[0]) is not str
        ):
            raise AuthorityManifestError(
                "adapter cached section root is invalid"
            )
        root_rows.append([section_id, cached[0], cached[1]])
    locator_rows: list[list[Any]] = []
    for source_id, locator in sorted(locator_index):
        cached = locator_index[(source_id, locator)]
        if type(cached) is not tuple or not cached:
            raise AuthorityManifestError(
                "adapter cached locator is invalid"
            )
        if cached[0] == "error" and len(cached) == 2:
            locator_rows.append(
                [source_id, locator, "error", cached[1]]
            )
        elif cached[0] == "ok" and len(cached) == 6:
            locator_rows.append(
                [
                    source_id,
                    locator,
                    "ok",
                    cached[1],
                    [list(step) for step in cached[2]],
                    cached[3],
                    list(cached[4]),
                    cached[5],
                ]
            )
        else:
            raise AuthorityManifestError(
                "adapter cached locator entry is invalid"
            )
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "sectionRoots": root_rows,
                "locators": locator_rows,
            }
        )
    ).hexdigest()


def _build_adapter_resolution_index(
    snapshot: AuthoritySnapshot,
    allowed_source_ids: tuple[str, ...],
) -> tuple[
    dict[str, tuple[Any, ...]],
    dict[tuple[str, str], tuple[Any, ...]],
    str,
]:
    snapshot._validate_cached_indexes()
    allowed = frozenset(allowed_source_ids)
    section_roots: dict[str, tuple[Any, ...]] = {}
    materialized_roots: dict[str, RawSourceObject] = {}
    locator_index: dict[tuple[str, str], tuple[Any, ...]] = {}
    for key in sorted(snapshot._locator_index):
        source_id, locator = key
        if source_id not in allowed:
            continue
        binding = snapshot._locator_index[key]
        if binding[0] == "error":
            locator_index[key] = binding
            continue
        if (
            type(binding) is not tuple
            or len(binding) != 4
            or binding[0] != "ok"
            or type(binding[1]) is not str
            or type(binding[2]) is not tuple
            or (
                binding[3] is not None
                and type(binding[3]) is not str
            )
        ):
            raise AuthorityManifestError(
                "snapshot cached locator binding is invalid"
            )
        section_id = binding[1]
        try:
            if section_id not in section_roots:
                snapshot._cached_section_root(section_id)
                section_roots[section_id] = (
                    snapshot._section_roots[section_id]
                )
            cached_root = section_roots[section_id]
            frozen_root = cached_root[2]
            if type(frozen_root) is not tuple:
                raise SourceAddressError(
                    "source section content is the authenticated "
                    "no-content sentinel"
                )
            raw_root = materialized_roots.get(section_id)
            if raw_root is None:
                materialized = _materialize_cached_raw(frozen_root)
                if type(materialized) is not RawSourceObject:
                    raise AuthorityManifestError(
                        "cached source section root is not an object"
                    )
                raw_root = materialized
                materialized_roots[section_id] = raw_root
            target, target_path = _semantic_target_path(
                raw_root,
                binding[2],
                snapshot._label_fields_by_source[source_id],
            )
            frozen_target, _member_digest = _resolve_cached_path(
                frozen_root,
                target_path,
            )
            target_digest = _cached_raw_digest(frozen_target)
            if target_digest != raw_source_sha256(target):
                raise AuthorityManifestError(
                    "adapter locator target disagrees with cached source"
                )
            locator_index[key] = (
                "ok",
                section_id,
                _freeze_cached_path(target_path),
                target_digest,
                tuple(binding[2]),
                binding[3],
            )
        except (SourceAuthorityError, TypeError) as failure:
            locator_index[key] = ("error", str(failure))
    return (
        section_roots,
        locator_index,
        _adapter_index_digest(section_roots, locator_index),
    )


def _resolution_expectation(
    adapter: SourceAuthorityAdapter,
    address: SourceAddress,
) -> tuple[
    _FrozenRaw,
    str,
    _FrozenRaw,
    str | None,
    str,
    _FrozenRaw,
    str,
]:
    """Re-resolve an address against tuple-only immutable source indexes."""

    if (
        type(adapter) is not SourceAuthorityAdapter
        or type(address) is not SourceAddress
    ):
        raise TypeError(
            "source resolution expectation requires exact contracts"
        )
    (
        section_id,
        _semantic_path,
        target_path,
        frozen_target,
    ) = adapter._cached_locator_target(
        address.source_id,
        address.locator,
    )
    if section_id != address.section_id:
        raise SourceAddressError(
            "source address section disagrees with verified ToC"
        )
    if target_path != address.target_path:
        raise SourceAddressError(
            "source address target path disagrees with verified ToC"
        )
    frozen_carrier, _carrier_member_digest = _resolve_cached_path(
        frozen_target,
        address.carrier_path,
    )
    if frozen_carrier[0] != "object":
        raise SourceAddressError(
            "source carrier path must select an object"
        )
    frozen_value, member_digest = _resolve_cached_path(
        frozen_carrier,
        address.selection_path,
    )
    frozen_selection = frozen_value
    if address.span is not None:
        if (
            frozen_value[0] != "primitive"
            or type(frozen_value[2]) is not str
        ):
            raise SourceAddressError(
                "text span selection requires a string value"
            )
        if address.span.end > len(frozen_value[2]):
            raise SourceAddressError(
                "text span selection is out of range"
            )
        frozen_selection, _selection_bytes = _freeze_cached_raw(
            frozen_value[2][address.span.start:address.span.end]
        )
    return (
        frozen_carrier,
        _cached_raw_digest(frozen_carrier),
        frozen_value,
        member_digest,
        _cached_raw_digest(frozen_value),
        frozen_selection,
        _cached_raw_digest(frozen_selection),
    )


@final
@dataclass(frozen=True, slots=True)
class _AuthorityContext:
    """Exact server-owned adapter/snapshot binding.

    This is an identity anchor for structurally revalidated values, not an
    unforgeable token.  It never crosses a serialization boundary.
    """

    snapshot: AuthoritySnapshot = field(repr=False, compare=False)
    allowed_source_ids: tuple[str, ...]
    adapter: SourceAuthorityAdapter = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self) is not _AuthorityContext:
            raise TypeError(
                "_AuthorityContext subclasses are not supported"
            )
        if (
            type(self.snapshot) is not AuthoritySnapshot
            or type(self.adapter) is not SourceAuthorityAdapter
            or self.adapter._snapshot is not self.snapshot
            or self.adapter._allowed_source_ids
            is not self.allowed_source_ids
        ):
            raise TypeError("authority context binding is invalid")
        if (
            not self.allowed_source_ids
            or len(self.allowed_source_ids) > MAX_MANIFEST_SOURCES
            or self.allowed_source_ids
            != tuple(sorted(self.allowed_source_ids))
            or len(self.allowed_source_ids)
            != len(set(self.allowed_source_ids))
        ):
            raise SourceReceiptError(
                "authority context source scope is invalid"
            )
        for source_id in self.allowed_source_ids:
            _require_source_id(
                source_id,
                "authority context source id",
            )

@final
@dataclass(frozen=True, slots=True, init=False)
class VerifiedSourceCarrier:
    """An exact raw object authenticated by one authority snapshot."""

    ruleset: str
    authority_digest: str
    source_id: str
    locator: str
    section_id: str
    target_path: RawPath
    carrier_path: RawPath
    raw_block: RawSourceObject = field(repr=False)
    block_sha256: str
    _capability: _AuthorityContext = field(repr=False, compare=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "VerifiedSourceCarrier can only be constructed by a "
            "SourceAuthorityAdapter"
        )

    def select(
        self,
        selection_path: tuple[RawPathStep, ...]
        | list[RawPathStep] = (),
        *,
        span: TextSpan | None = None,
    ) -> VerifiedSourceSelection:
        if type(self) is not VerifiedSourceCarrier:
            raise TypeError("verified source carrier must be exact")
        if self._capability.adapter._capability is not self._capability:
            raise SourceReceiptError(
                "verified source carrier context is invalid"
            )
        path = _path(selection_path, "verified selection path")
        address = SourceAddress(
            source_id=self.source_id,
            locator=self.locator,
            section_id=self.section_id,
            target_path=self.target_path,
            carrier_path=self.carrier_path,
            selection_path=path,
            span=span,
        )
        return self._capability.adapter.resolve(address)


@final
@dataclass(frozen=True, slots=True, init=False)
class VerifiedSourceSelection:
    """One exact value, member, array item, block, or text span."""

    carrier: VerifiedSourceCarrier
    address: SourceAddress
    raw_value: RawSourceValue = field(repr=False)
    raw_member: RawSourceMember | None = field(repr=False)
    selected_value: RawSourceValue = field(repr=False)
    value_sha256: str
    member_sha256: str | None
    selection_sha256: str
    _capability: _AuthorityContext = field(repr=False, compare=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "VerifiedSourceSelection can only be constructed from a "
            "verified carrier"
        )

    @property
    def block_sha256(self) -> str:
        if type(self) is not VerifiedSourceSelection:
            raise TypeError("verified source selection must be exact")
        if (
            type(self.carrier) is not VerifiedSourceCarrier
            or self.carrier._capability is not self._capability
        ):
            raise SourceReceiptError(
                "verified source selection context is invalid"
            )
        return self.carrier.block_sha256

    @property
    def receipt(self) -> SourceReceipt:
        if type(self) is not VerifiedSourceSelection:
            raise TypeError("verified source selection must be exact")
        if (
            type(self.carrier) is not VerifiedSourceCarrier
            or self.carrier._capability is not self._capability
        ):
            raise SourceReceiptError(
                "verified source selection context is invalid"
            )
        return SourceReceipt(
            ruleset=self.carrier.ruleset,
            authority_digest=self.carrier.authority_digest,
            address=self.address,
            block_sha256=self.block_sha256,
            member_sha256=self.member_sha256,
            value_sha256=self.value_sha256,
            selection_sha256=self.selection_sha256,
        )


def _verified_carrier(
    *,
    snapshot: AuthoritySnapshot,
    address: SourceAddress,
    raw_block: RawSourceObject,
    context: _AuthorityContext,
) -> VerifiedSourceCarrier:
    if (
        type(snapshot) is not AuthoritySnapshot
        or type(address) is not SourceAddress
        or type(raw_block) is not RawSourceObject
        or type(context) is not _AuthorityContext
        or context.snapshot is not snapshot
    ):
        raise TypeError("authority context belongs to another snapshot")
    result = object.__new__(VerifiedSourceCarrier)
    object.__setattr__(result, "ruleset", snapshot.ruleset)
    object.__setattr__(result, "authority_digest", snapshot.digest)
    object.__setattr__(result, "source_id", address.source_id)
    object.__setattr__(result, "locator", address.locator)
    object.__setattr__(result, "section_id", address.section_id)
    object.__setattr__(result, "target_path", address.target_path)
    object.__setattr__(result, "carrier_path", address.carrier_path)
    object.__setattr__(result, "raw_block", raw_block)
    object.__setattr__(
        result,
        "block_sha256",
        raw_source_sha256(raw_block),
    )
    object.__setattr__(result, "_capability", context)
    return result


def _verified_selection(
    carrier: VerifiedSourceCarrier,
    address: SourceAddress,
    context: _AuthorityContext,
) -> VerifiedSourceSelection:
    if (
        type(carrier) is not VerifiedSourceCarrier
        or type(address) is not SourceAddress
        or type(context) is not _AuthorityContext
        or context is not carrier._capability
        or context.snapshot.digest != carrier.authority_digest
    ):
        raise TypeError("verified carrier context is invalid")
    raw_value, raw_member = _resolve_exact_path(
        carrier.raw_block,
        address.selection_path,
    )
    selected_value: RawSourceValue = raw_value
    if address.span is not None:
        if type(raw_value) is not str:
            raise SourceAddressError(
                "text span selection requires a string value"
            )
        if address.span.end > len(raw_value):
            raise SourceAddressError(
                "text span selection is out of range"
            )
        selected_value = raw_value[address.span.start:address.span.end]

    result = object.__new__(VerifiedSourceSelection)
    object.__setattr__(result, "carrier", carrier)
    object.__setattr__(result, "address", address)
    object.__setattr__(result, "raw_value", raw_value)
    object.__setattr__(result, "raw_member", raw_member)
    object.__setattr__(result, "selected_value", selected_value)
    object.__setattr__(
        result,
        "value_sha256",
        raw_source_sha256(raw_value),
    )
    object.__setattr__(
        result,
        "member_sha256",
        (
            raw_member_sha256(raw_member)
            if type(raw_member) is RawSourceMember
            else None
        ),
    )
    object.__setattr__(
        result,
        "selection_sha256",
        raw_source_sha256(selected_value),
    )
    object.__setattr__(result, "_capability", context)
    return result


@final
@dataclass(frozen=True, slots=True)
class RuleRequirement:
    """A declarative provider target plus reviewed stable source hashes."""

    rule_id: str
    source_id: str
    locator: str
    carrier_path: RawPath = ()
    selection_path: RawPath = ()
    span: TextSpan | None = None
    expected_block_sha256: str | None = None
    expected_member_sha256: str | None = None
    expected_value_sha256: str | None = None
    expected_selection_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self) is not RuleRequirement:
            raise TypeError("RuleRequirement subclasses are not supported")
        _require_source_id(
            self.source_id,
            "RuleRequirement.source_id",
        )
        for field_name in ("rule_id", "locator"):
            _require_text(
                getattr(self, field_name),
                f"RuleRequirement.{field_name}",
            )
        for field_name in ("carrier_path", "selection_path"):
            object.__setattr__(
                self,
                field_name,
                _path(
                    getattr(self, field_name),
                    f"RuleRequirement.{field_name}",
                ),
            )
        if len(self.carrier_path) + len(self.selection_path) > MAX_PATH_STEPS:
            raise SourceAddressError(
                "RuleRequirement paths exceed their combined step bound"
            )
        if self.span is not None and type(self.span) is not TextSpan:
            raise TypeError("RuleRequirement.span must be TextSpan or None")
        expected = (
            self.expected_block_sha256,
            self.expected_member_sha256,
            self.expected_value_sha256,
            self.expected_selection_sha256,
        )
        if all(item is None for item in expected):
            raise SourceReviewError(
                "RuleRequirement must pin at least one reviewed hash"
            )
        for index, item in enumerate(expected):
            if item is not None:
                _require_sha256(
                    item,
                    (
                        "RuleRequirement reviewed hash "
                        f"{index}"
                    ),
                )

    def as_serialized(self) -> dict[str, Any]:
        if type(self) is not RuleRequirement:
            raise TypeError("RuleRequirement must be exact")
        if (
            type(self.carrier_path) is not tuple
            or type(self.selection_path) is not tuple
        ):
            raise SourceAddressError(
                "stored RuleRequirement paths must be exact tuples"
            )
        validated = RuleRequirement(
            rule_id=self.rule_id,
            source_id=self.source_id,
            locator=self.locator,
            carrier_path=self.carrier_path,
            selection_path=self.selection_path,
            span=self.span,
            expected_block_sha256=self.expected_block_sha256,
            expected_member_sha256=self.expected_member_sha256,
            expected_value_sha256=self.expected_value_sha256,
            expected_selection_sha256=(
                self.expected_selection_sha256
            ),
        )
        return {
            "ruleId": validated.rule_id,
            "sourceId": validated.source_id,
            "locator": validated.locator,
            "carrierPath": [
                _step_serialized(step)
                for step in validated.carrier_path
            ],
            "selectionPath": [
                _step_serialized(step)
                for step in validated.selection_path
            ],
            "span": (
                TextSpan.as_serialized(validated.span)
                if validated.span is not None
                else None
            ),
            "expectedHashes": {
                "blockSha256": validated.expected_block_sha256,
                "memberSha256": validated.expected_member_sha256,
                "valueSha256": validated.expected_value_sha256,
                "selectionSha256": (
                    validated.expected_selection_sha256
                ),
            },
        }


@final
@dataclass(frozen=True, slots=True, init=False)
class VerifiedRuleReceipt:
    """An authority-resolved provider plus its reviewed requirement."""

    rule_id: str
    requirement: RuleRequirement
    selection: VerifiedSourceSelection
    receipt: SourceReceipt
    _capability: _AuthorityContext = field(repr=False, compare=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "VerifiedRuleReceipt can only be constructed by a "
            "SourceAuthorityAdapter"
        )

    def as_serialized(self) -> dict[str, Any]:
        if type(self) is not VerifiedRuleReceipt:
            raise TypeError("verified rule receipt must be exact")
        self._capability.adapter.validate_rule(self)
        return {
            "ruleId": self.rule_id,
            "requirement": RuleRequirement.as_serialized(
                self.requirement
            ),
            "source": SourceReceipt.as_serialized(self.receipt),
        }


def _fingerprint_parts(*parts: bytes) -> bytes:
    body = bytearray()
    for part in parts:
        if type(part) is not bytes:
            raise TypeError("fingerprint parts must be exact bytes")
        body.extend(len(part).to_bytes(8, "big"))
        body.extend(part)
    return hashlib.sha256(bytes(body)).digest()


def _carrier_fingerprint(value: VerifiedSourceCarrier) -> bytes:
    if type(value) is not VerifiedSourceCarrier:
        raise TypeError("carrier fingerprint requires exact carrier")
    _require_text(value.ruleset, "verified carrier ruleset")
    _require_sha256(
        value.authority_digest,
        "verified carrier authority digest",
    )
    _require_source_id(value.source_id, "verified carrier source id")
    _require_text(value.locator, "verified carrier locator")
    _require_text(value.section_id, "verified carrier section id")
    _require_sha256(
        value.block_sha256,
        "verified carrier block hash",
    )
    if (
        type(value.target_path) is not tuple
        or type(value.carrier_path) is not tuple
    ):
        raise SourceAddressError(
            "verified carrier paths must be exact tuples"
        )
    target_path = _path(value.target_path, "verified carrier target path")
    carrier_path = _path(
        value.carrier_path,
        "verified carrier carrier path",
    )
    if len(target_path) + len(carrier_path) > MAX_PATH_STEPS:
        raise SourceAddressError(
            "verified carrier paths exceed their combined bound"
        )
    metadata = canonical_json_bytes(
        {
            "ruleset": value.ruleset,
            "authorityDigest": value.authority_digest,
            "sourceId": value.source_id,
            "locator": value.locator,
            "sectionId": value.section_id,
            "targetPath": [
                _step_serialized(step) for step in target_path
            ],
            "carrierPath": [
                _step_serialized(step) for step in carrier_path
            ],
            "blockSha256": value.block_sha256,
        }
    )
    raw = canonical_raw_bytes(value.raw_block)
    if raw_source_sha256(value.raw_block) != value.block_sha256:
        raise SourceReceiptError(
            "verified carrier raw block hash disagrees"
        )
    return _fingerprint_parts(metadata, raw)


@final
@dataclass(frozen=True, slots=True, order=True)
class SourceTocTarget:
    """Immutable authenticated ToC projection for deterministic traversal."""

    source_id: str
    locator: str
    label: str
    content_path: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self) is not SourceTocTarget:
            raise TypeError("SourceTocTarget subclasses are not supported")
        _require_source_id(self.source_id, "SourceTocTarget.source_id")
        _require_text(self.locator, "SourceTocTarget.locator")
        _require_text(self.label, "SourceTocTarget.label")
        if type(self.content_path) is not tuple:
            raise SourceAddressError(
                "SourceTocTarget.content_path must be an exact tuple"
            )
        for part in self.content_path:
            _require_text(part, "SourceTocTarget.content_path item")


@final
@dataclass(frozen=True, slots=True, init=False, eq=False)
class SourceAuthorityAdapter:
    """Server-owned resolver context for one snapshot and exact source set.

    Adapters have no serialized form or wire constructor.  Request handlers
    must obtain the retained adapter from server state and pass only public
    claims such as ``SourceAddress`` or ``SourceReceipt`` into its methods.
    """

    _snapshot: AuthoritySnapshot = field(repr=False, compare=False)
    _allowed_source_ids: tuple[str, ...] = field(repr=False)
    _capability: _AuthorityContext = field(repr=False, compare=False)
    _section_roots: MappingProxyType[
        str, tuple[Any, ...]
    ] = field(repr=False, compare=False)
    _locator_index: MappingProxyType[
        tuple[str, str], tuple[Any, ...]
    ] = field(repr=False, compare=False)
    _index_digest: str = field(repr=False, compare=False)

    def __init__(
        self,
        snapshot: AuthoritySnapshot,
        allowed_source_ids: tuple[str, ...],
    ) -> None:
        if type(self) is not SourceAuthorityAdapter:
            raise TypeError(
                "SourceAuthorityAdapter subclasses are not supported"
            )
        if type(snapshot) is not AuthoritySnapshot:
            raise TypeError(
                "SourceAuthorityAdapter requires AuthoritySnapshot"
            )
        if type(allowed_source_ids) is not tuple:
            raise TypeError(
                "allowed_source_ids must be an exact tuple"
            )
        if (
            not allowed_source_ids
            or len(allowed_source_ids) > MAX_MANIFEST_SOURCES
            or any(type(item) is not str for item in allowed_source_ids)
            or allowed_source_ids != tuple(sorted(allowed_source_ids))
            or len(allowed_source_ids) != len(set(allowed_source_ids))
        ):
            raise SourceAddressError(
                "allowed_source_ids must be nonempty, unique, and sorted"
            )
        for source_id in allowed_source_ids:
            _require_source_id(
                source_id,
                "allowed_source_ids item",
            )
        unknown = tuple(
            source_id
            for source_id in allowed_source_ids
            if source_id not in snapshot._source_id_set
        )
        if unknown:
            raise SourceAddressError(
                "allowed sources are outside the authority snapshot: "
                f"{unknown}"
            )
        # Revalidate the retained manifest claim before deriving one context.
        snapshot.as_serialized()
        object.__setattr__(self, "_snapshot", snapshot)
        object.__setattr__(
            self,
            "_allowed_source_ids",
            allowed_source_ids,
        )
        (
            section_roots,
            locator_index,
            index_digest,
        ) = _build_adapter_resolution_index(
            snapshot,
            allowed_source_ids,
        )
        object.__setattr__(
            self,
            "_section_roots",
            MappingProxyType(section_roots),
        )
        object.__setattr__(
            self,
            "_locator_index",
            MappingProxyType(locator_index),
        )
        object.__setattr__(self, "_index_digest", index_digest)
        context = _AuthorityContext(
            snapshot=snapshot,
            allowed_source_ids=allowed_source_ids,
            adapter=self,
        )
        object.__setattr__(self, "_capability", context)
        self._validated_scope()

    @property
    def snapshot(self) -> AuthoritySnapshot:
        self._validated_scope()
        return self._snapshot

    @property
    def allowed_source_ids(self) -> tuple[str, ...]:
        return self._validated_scope()

    def __copy__(self) -> SourceAuthorityAdapter:
        raise TypeError("SourceAuthorityAdapter cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> SourceAuthorityAdapter:
        raise TypeError("SourceAuthorityAdapter cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("SourceAuthorityAdapter cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("SourceAuthorityAdapter cannot be pickled")

    def _validated_scope(self) -> tuple[str, ...]:
        if type(self) is not SourceAuthorityAdapter:
            raise TypeError("source authority adapter must be exact")
        snapshot = getattr(self, "_snapshot", None)
        allowed_source_ids = getattr(
            self,
            "_allowed_source_ids",
            None,
        )
        context = getattr(self, "_capability", None)
        if (
            type(snapshot) is not AuthoritySnapshot
            or type(allowed_source_ids) is not tuple
            or type(context) is not _AuthorityContext
            or type(getattr(self, "_section_roots", None))
            is not MappingProxyType
            or type(getattr(self, "_locator_index", None))
            is not MappingProxyType
        ):
            raise SourceReceiptError(
                "source authority adapter state is invalid"
            )
        if (
            context.adapter is not self
            or context.snapshot is not snapshot
            or context.allowed_source_ids is not allowed_source_ids
        ):
            raise SourceReceiptError(
                "source authority adapter context disagrees"
            )
        _require_sha256(
            getattr(self, "_index_digest", None),
            "source authority adapter index digest",
        )
        snapshot._validate_cached_indexes()
        if (
            type(allowed_source_ids) is not tuple
            or not allowed_source_ids
            or len(allowed_source_ids) > MAX_MANIFEST_SOURCES
            or any(
                type(source_id) is not str
                for source_id in allowed_source_ids
            )
            or allowed_source_ids
            != tuple(sorted(allowed_source_ids))
            or len(allowed_source_ids)
            != len(set(allowed_source_ids))
        ):
            raise SourceReceiptError(
                "source authority adapter scope is invalid"
            )
        if any(
            source_id not in snapshot._source_id_set
            for source_id in allowed_source_ids
        ):
            raise SourceReceiptError(
                "source authority adapter scope is outside its snapshot"
            )
        return allowed_source_ids

    def _require_allowed_source(self, source_id: str) -> None:
        if source_id not in self._validated_scope():
            raise SourceAddressError(
                f"source is not selected for this adapter: {source_id}"
            )

    def iter_toc_targets(self) -> tuple[SourceTocTarget, ...]:
        """Return the selected scope's exact, deterministic ToC targets.

        The projection deliberately exposes no cached index representation,
        raw source storage, or authority capability.  Point resolution remains
        an explicit authenticated operation through ``address`` and ``resolve``.
        """

        allowed = self._validated_scope()
        keys = tuple(
            sorted(
                key
                for key in self._locator_index
                if key[0] in allowed
                and type(self._locator_index[key]) is tuple
                and self._locator_index[key][0] == "ok"
            )
        )
        targets: list[SourceTocTarget] = []
        for source_id, locator in keys:
            # These public point reads revalidate both the adapter index and
            # the retained snapshot projection, including ambiguity failures.
            targets.append(
                SourceTocTarget(
                    source_id=source_id,
                    locator=locator,
                    label=self.toc_label(source_id, locator),
                    content_path=self.toc_content_path(source_id, locator),
                )
            )
        return tuple(targets)

    def _cached_locator_target(
        self,
        source_id: str,
        locator: str,
    ) -> tuple[str, tuple[str, ...], RawPath, _FrozenRaw]:
        self._validated_scope()
        try:
            cached = self._locator_index[(source_id, locator)]
        except KeyError as failure:
            raise SourceAddressError(
                "source locator is missing or ambiguous: "
                f"{source_id}/{locator}"
            ) from failure
        if (
            type(cached) is not tuple
            or not cached
            or cached[0] not in {"ok", "error"}
        ):
            raise AuthorityManifestError(
                "adapter cached locator entry is invalid"
            )
        if cached[0] == "error":
            if len(cached) != 2 or type(cached[1]) is not str:
                raise AuthorityManifestError(
                    "adapter cached locator failure is invalid"
                )
            raise SourceAddressError(cached[1])
        if (
            len(cached) != 6
            or type(cached[1]) is not str
            or type(cached[2]) is not tuple
            or type(cached[3]) is not str
            or type(cached[4]) is not tuple
            or (
                cached[5] is not None
                and type(cached[5]) is not str
            )
        ):
            raise AuthorityManifestError(
                "adapter cached locator target is invalid"
            )
        section_id = cached[1]
        if self._snapshot._section_entry(section_id).source_id != source_id:
            raise AuthorityManifestError(
                "adapter cached locator owner disagrees"
            )
        try:
            section_root = self._section_roots[section_id]
        except KeyError as failure:
            raise AuthorityManifestError(
                "adapter cached section root is missing"
            ) from failure
        if (
            type(section_root) is not tuple
            or len(section_root) != 3
            or type(section_root[2]) is not tuple
        ):
            raise AuthorityManifestError(
                "adapter cached section root is invalid"
            )
        target_path = _materialize_cached_path(cached[2])
        frozen_target, _member_digest = _resolve_cached_path(
            section_root[2],
            target_path,
        )
        if _cached_raw_digest(frozen_target) != cached[3]:
            raise AuthorityManifestError(
                "adapter cached locator target digest disagrees"
            )
        return section_id, cached[4], target_path, frozen_target

    def toc_label(
        self,
        source_id: str,
        locator: str,
        /,
    ) -> str:
        """Return one authenticated exact ToC label for a selected locator."""

        source_id = _require_source_id(
            source_id,
            "source target-label source_id",
        )
        self._require_allowed_source(source_id)
        locator = _require_text(
            locator,
            "source target-label locator",
        )
        self._cached_locator_target(source_id, locator)
        cached = self._locator_index[(source_id, locator)]
        snapshot_cached = self._snapshot._locator_index.get(
            (source_id, locator)
        )
        if (
            type(cached) is not tuple
            or len(cached) != 6
            or type(snapshot_cached) is not tuple
            or len(snapshot_cached) != 4
            or cached[5] != snapshot_cached[3]
        ):
            raise AuthorityManifestError(
                "adapter ToC label disagrees with its authority "
                "snapshot"
            )
        label = cached[5]
        if type(label) is not str:
            raise SourceAddressError(
                "source locator has no exact authenticated target label: "
                f"{source_id}/{locator}"
            )
        return label

    def toc_content_path(
        self,
        source_id: str,
        locator: str,
        /,
    ) -> tuple[str, ...]:
        """Return one authenticated semantic ToC path for a locator."""

        source_id = _require_source_id(
            source_id,
            "source content-path source_id",
        )
        self._require_allowed_source(source_id)
        locator = _require_text(
            locator,
            "source content-path locator",
        )
        (
            _section_id,
            semantic_path,
            _target_path,
            _frozen_target,
        ) = self._cached_locator_target(source_id, locator)
        snapshot_cached = self._snapshot._locator_index.get(
            (source_id, locator)
        )
        if (
            type(snapshot_cached) is not tuple
            or len(snapshot_cached) != 4
            or snapshot_cached[0] != "ok"
            or semantic_path != snapshot_cached[2]
        ):
            raise AuthorityManifestError(
                "adapter ToC content path disagrees with its authority "
                "snapshot"
            )
        return semantic_path

    def address(
        self,
        *,
        source_id: str,
        locator: str,
        carrier_path: tuple[RawPathStep, ...]
        | list[RawPathStep] = (),
        selection_path: tuple[RawPathStep, ...]
        | list[RawPathStep] = (),
        span: TextSpan | None = None,
    ) -> SourceAddress:
        source_id = _require_source_id(
            source_id,
            "source address source_id",
        )
        self._require_allowed_source(source_id)
        locator = _require_text(locator, "source address locator")
        (
            section_id,
            _semantic_path,
            target_path,
            _frozen_target,
        ) = self._cached_locator_target(source_id, locator)
        entry = self._snapshot._section_entry(section_id)
        if entry.source_id != source_id:
            raise SourceAddressError(
                "source locator section belongs to another source"
            )
        address = SourceAddress(
            source_id=source_id,
            locator=locator,
            section_id=section_id,
            target_path=target_path,
            carrier_path=_path(
                carrier_path,
                "source address carrier_path",
            ),
            selection_path=_path(
                selection_path,
                "source address selection_path",
            ),
            span=span,
        )
        # Validate every exact path without materializing caller-visible raw
        # objects.  ``resolve`` performs the one fresh materialization.
        _resolution_expectation(self, address)
        return address

    def resolve(self, address: SourceAddress) -> VerifiedSourceSelection:
        if type(address) is not SourceAddress:
            raise TypeError(
                "SourceAuthorityAdapter.resolve requires SourceAddress"
            )
        address = SourceAddress.from_serialized(
            SourceAddress.as_serialized(address)
        )
        self._require_allowed_source(address.source_id)
        (
            frozen_carrier,
            expected_block_sha256,
            _frozen_value,
            expected_member_sha256,
            expected_value_sha256,
            _frozen_selection,
            expected_selection_sha256,
        ) = _resolution_expectation(self, address)
        raw_block = _materialize_cached_raw(frozen_carrier)
        if type(raw_block) is not RawSourceObject:
            raise AuthorityManifestError(
                "authority cached carrier did not materialize an object"
            )
        carrier = _verified_carrier(
            snapshot=self._snapshot,
            address=address,
            raw_block=raw_block,
            context=self._capability,
        )
        selection = _verified_selection(
            carrier,
            address,
            self._capability,
        )
        if (
            selection.block_sha256 != expected_block_sha256
            or selection.member_sha256 != expected_member_sha256
            or selection.value_sha256 != expected_value_sha256
            or selection.selection_sha256
            != expected_selection_sha256
        ):
            raise AuthorityManifestError(
                "materialized source selection disagrees with its "
                "immutable index"
            )
        return selection

    def validate_selection(
        self,
        selection: VerifiedSourceSelection,
    ) -> VerifiedSourceSelection:
        """Re-resolve one issued selection against this exact adapter."""

        if type(self) is not SourceAuthorityAdapter:
            raise TypeError("source authority adapter must be exact")
        self._validated_scope()
        if type(selection) is not VerifiedSourceSelection:
            raise TypeError(
                "validate_selection requires VerifiedSourceSelection"
            )
        if (
            type(selection.carrier) is not VerifiedSourceCarrier
            or type(selection.address) is not SourceAddress
            or type(selection._capability) is not _AuthorityContext
        ):
            raise SourceReceiptError(
                "verified selection fields must use exact contracts"
            )
        if (
            selection._capability is not self._capability
            or selection.carrier._capability is not self._capability
            or self._capability.snapshot is not self._snapshot
        ):
            raise SourceReceiptError(
                "verified selection belongs to another authority context"
            )
        address = SourceAddress.from_serialized(
            SourceAddress.as_serialized(selection.address)
        )
        self._require_allowed_source(address.source_id)
        (
            _frozen_carrier,
            expected_block_sha256,
            _frozen_value,
            expected_member_sha256,
            expected_value_sha256,
            _frozen_selection,
            expected_selection_sha256,
        ) = _resolution_expectation(self, address)
        carrier = selection.carrier
        if (
            carrier.ruleset != self._snapshot.ruleset
            or carrier.authority_digest != self._snapshot.digest
            or carrier.source_id != address.source_id
            or carrier.locator != address.locator
            or carrier.section_id != address.section_id
            or carrier.target_path != address.target_path
            or carrier.carrier_path != address.carrier_path
            or carrier.block_sha256 != expected_block_sha256
            or selection.value_sha256 != expected_value_sha256
            or selection.member_sha256 != expected_member_sha256
            or selection.selection_sha256
            != expected_selection_sha256
        ):
            raise SourceReceiptError(
                "verified selection disagrees with current authority"
            )
        try:
            if (
                type(carrier.raw_block) is not RawSourceObject
                or raw_source_sha256(carrier.raw_block)
                != expected_block_sha256
            ):
                raise SourceReceiptError(
                    "verified carrier raw block disagrees with authority"
                )
            derived_value, derived_member = _resolve_exact_path(
                carrier.raw_block,
                address.selection_path,
            )
            derived_member_sha256 = (
                None
                if derived_member is None
                else raw_member_sha256(derived_member)
            )
            supplied_member_sha256 = (
                None
                if selection.raw_member is None
                else raw_member_sha256(selection.raw_member)
            )
            derived_selection: RawSourceValue = derived_value
            if address.span is not None:
                if (
                    type(derived_value) is not str
                    or address.span.end > len(derived_value)
                ):
                    raise SourceReceiptError(
                        "verified selection span disagrees with authority"
                    )
                derived_selection = derived_value[
                    address.span.start:address.span.end
                ]
            if (
                raw_source_sha256(derived_value)
                != expected_value_sha256
                or raw_source_sha256(selection.raw_value)
                != expected_value_sha256
                or derived_member_sha256 != expected_member_sha256
                or supplied_member_sha256 != expected_member_sha256
                or raw_source_sha256(derived_selection)
                != expected_selection_sha256
                or raw_source_sha256(selection.selected_value)
                != expected_selection_sha256
            ):
                raise SourceReceiptError(
                    "verified selection raw values disagree with authority"
                )
        except (
            SourceAuthorityError,
            TypeError,
            ValueError,
        ) as failure:
            if type(failure) is SourceReceiptError:
                raise
            raise SourceReceiptError(
                "verified selection raw values are invalid"
            ) from failure
        return selection

    def validate_rule(
        self,
        rule: VerifiedRuleReceipt,
    ) -> VerifiedRuleReceipt:
        """Re-resolve one provider rule and its retained requirement.

        The caller must separately require that ``rule.requirement`` is one
        of its own immutable reviewed requirements.
        """

        if type(self) is not SourceAuthorityAdapter:
            raise TypeError("source authority adapter must be exact")
        self._validated_scope()
        if type(rule) is not VerifiedRuleReceipt:
            raise TypeError(
                "validate_rule requires VerifiedRuleReceipt"
            )
        if (
            type(rule.requirement) is not RuleRequirement
            or type(rule.selection) is not VerifiedSourceSelection
            or type(rule.receipt) is not SourceReceipt
            or type(rule._capability) is not _AuthorityContext
        ):
            raise SourceReceiptError(
                "verified rule fields must use exact authority contracts"
            )
        _require_text(rule.rule_id, "verified rule id")
        RuleRequirement.as_serialized(rule.requirement)
        if (
            rule._capability is not self._capability
            or rule.selection._capability is not self._capability
        ):
            raise SourceReceiptError(
                "verified rule belongs to another authority context"
            )
        requirement = RuleRequirement(
            rule_id=rule.requirement.rule_id,
            source_id=rule.requirement.source_id,
            locator=rule.requirement.locator,
            carrier_path=rule.requirement.carrier_path,
            selection_path=rule.requirement.selection_path,
            span=rule.requirement.span,
            expected_block_sha256=(
                rule.requirement.expected_block_sha256
            ),
            expected_member_sha256=(
                rule.requirement.expected_member_sha256
            ),
            expected_value_sha256=(
                rule.requirement.expected_value_sha256
            ),
            expected_selection_sha256=(
                rule.requirement.expected_selection_sha256
            ),
        )
        if rule.rule_id != requirement.rule_id:
            raise SourceReceiptError(
                "verified rule id disagrees with its requirement"
            )
        selection = self.validate_selection(rule.selection)
        expected_address = self.address(
            source_id=requirement.source_id,
            locator=requirement.locator,
            carrier_path=requirement.carrier_path,
            selection_path=requirement.selection_path,
            span=requirement.span,
        )
        if (
            canonical_json_bytes(
                SourceAddress.as_serialized(selection.address)
            )
            != canonical_json_bytes(
                SourceAddress.as_serialized(expected_address)
            )
        ):
            raise SourceReceiptError(
                "verified rule selection disagrees with its requirement"
            )
        expected_pairs = (
            (
                "block",
                requirement.expected_block_sha256,
                selection.block_sha256,
            ),
            (
                "member",
                requirement.expected_member_sha256,
                selection.member_sha256,
            ),
            (
                "value",
                requirement.expected_value_sha256,
                selection.value_sha256,
            ),
            (
                "selection",
                requirement.expected_selection_sha256,
                selection.selection_sha256,
            ),
        )
        for label, expected, actual in expected_pairs:
            if expected is not None and expected != actual:
                raise SourceReviewError(
                    f"reviewed rule {label} hash disagrees: "
                    f"{requirement.rule_id}"
                )
        if (
            canonical_json_bytes(
                SourceReceipt.as_serialized(rule.receipt)
            )
            != canonical_json_bytes(
                SourceReceipt.as_serialized(selection.receipt)
            )
        ):
            raise SourceReceiptError(
                "verified rule receipt disagrees with its selection"
            )
        return rule

    def require_shared_authority(
        self,
        consumer: VerifiedSourceSelection,
        ordered_providers: tuple[VerifiedRuleReceipt, ...],
    ) -> None:
        """Require consumer and ordered providers from this one context."""

        self._validated_scope()
        if type(ordered_providers) is not tuple:
            raise TypeError("ordered providers must be an exact tuple")
        if (
            not ordered_providers
            or len(ordered_providers) > MAX_RAW_NODES
            or any(
                type(provider) is not VerifiedRuleReceipt
                for provider in ordered_providers
            )
        ):
            raise SourceReceiptError(
                "ordered providers must contain exact verified rules"
            )
        self.validate_selection(consumer)
        for provider in ordered_providers:
            if provider._capability is not self._capability:
                raise SourceReceiptError(
                    "consumer and providers do not share authority"
                )
            self.validate_rule(provider)

    def reload(
        self,
        receipt: SourceReceipt,
    ) -> VerifiedSourceSelection:
        self._validated_scope()
        if type(receipt) is not SourceReceipt:
            raise TypeError(
                "SourceAuthorityAdapter.reload requires SourceReceipt"
            )
        receipt = SourceReceipt.from_serialized(
            SourceReceipt.as_serialized(receipt)
        )
        if receipt.ruleset != self._snapshot.ruleset:
            raise StaleSourceReceiptError(
                "source receipt ruleset disagrees with authority"
            )
        if receipt.authority_digest != self._snapshot.digest:
            raise StaleSourceReceiptError(
                "source receipt belongs to another authority snapshot"
            )
        selection = self.resolve(receipt.address)
        actual = selection.receipt
        for field_name in (
            "block_sha256",
            "member_sha256",
            "value_sha256",
            "selection_sha256",
        ):
            if getattr(receipt, field_name) != getattr(actual, field_name):
                raise SourceReceiptError(
                    f"source receipt {field_name} disagrees with authority"
                )
        if receipt.digest != actual.digest:
            raise SourceReceiptError(
                "source receipt canonical digest disagrees with authority"
            )
        return selection

    def reload_json(self, value: str) -> VerifiedSourceSelection:
        self._validated_scope()
        return self.reload(SourceReceipt.from_json(value))

    def resolve_rule(
        self,
        requirement: RuleRequirement,
    ) -> VerifiedRuleReceipt:
        self._validated_scope()
        if type(requirement) is not RuleRequirement:
            raise TypeError(
                "SourceAuthorityAdapter.resolve_rule requires "
                "RuleRequirement"
            )
        requirement = RuleRequirement(
            rule_id=requirement.rule_id,
            source_id=requirement.source_id,
            locator=requirement.locator,
            carrier_path=requirement.carrier_path,
            selection_path=requirement.selection_path,
            span=requirement.span,
            expected_block_sha256=(
                requirement.expected_block_sha256
            ),
            expected_member_sha256=(
                requirement.expected_member_sha256
            ),
            expected_value_sha256=(
                requirement.expected_value_sha256
            ),
            expected_selection_sha256=(
                requirement.expected_selection_sha256
            ),
        )
        address = self.address(
            source_id=requirement.source_id,
            locator=requirement.locator,
            carrier_path=requirement.carrier_path,
            selection_path=requirement.selection_path,
            span=requirement.span,
        )
        selection = self.resolve(address)
        expected_pairs = (
            (
                "block",
                requirement.expected_block_sha256,
                selection.block_sha256,
            ),
            (
                "member",
                requirement.expected_member_sha256,
                selection.member_sha256,
            ),
            (
                "value",
                requirement.expected_value_sha256,
                selection.value_sha256,
            ),
            (
                "selection",
                requirement.expected_selection_sha256,
                selection.selection_sha256,
            ),
        )
        for label, expected, actual in expected_pairs:
            if expected is not None and expected != actual:
                raise SourceReviewError(
                    f"reviewed rule {label} hash disagrees: "
                    f"{requirement.rule_id}"
                )
        result = object.__new__(VerifiedRuleReceipt)
        object.__setattr__(result, "rule_id", requirement.rule_id)
        object.__setattr__(result, "requirement", requirement)
        object.__setattr__(result, "selection", selection)
        object.__setattr__(result, "receipt", selection.receipt)
        object.__setattr__(result, "_capability", self._capability)
        return result


__all__ = [
    "AUTHORITY_RULESET",
    "AUTHORITY_SCHEMA",
    "AuthorityManifestError",
    "AuthoritySnapshot",
    "MAX_IDENTIFIER_BYTES",
    "MAX_MANIFEST_SECTIONS",
    "MAX_MANIFEST_SOURCES",
    "MAX_PATH_STEPS",
    "MAX_RAW_BYTES",
    "MAX_RAW_DEPTH",
    "MAX_RAW_NODES",
    "MAX_ROW_BYTES",
    "RawIndexStep",
    "RawMemberStep",
    "RawPath",
    "RawPathStep",
    "RuleRequirement",
    "SourceAddress",
    "SourceAddressError",
    "SourceAuthorityAdapter",
    "SourceAuthorityError",
    "SourceReceipt",
    "SourceReceiptError",
    "SourceReviewError",
    "SourceTocTarget",
    "StaleSourceReceiptError",
    "TextSpan",
    "VerifiedRuleReceipt",
    "VerifiedSourceCarrier",
    "VerifiedSourceSelection",
    "authority_manifest_digest",
    "canonical_json_bytes",
    "canonical_raw_bytes",
    "raw_member_sha256",
    "raw_source_sha256",
    "text_sha256",
    "validate_section_content",
]

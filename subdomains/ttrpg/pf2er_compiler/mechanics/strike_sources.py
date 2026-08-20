"""Lossless, compile/link-only PF2ER Strike source foundation.

This module deliberately stops before encounter execution.  It retains the
ordered source objects and their duplicate-aware addresses, recognizes only
reviewed structural shapes, and records everything else as a typed deferred
dependency.  It does not mount a mechanic family, import an orchestrator, or
choose rules by creature name.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields as dataclass_fields
import hashlib
import json
import math
import re
from types import FunctionType, MappingProxyType
from typing import Any, Literal, TypeAlias
from weakref import WeakKeyDictionary

from ...source_content import MAX_PATH_STEPS
from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RawSourcePathStep,
    RawSourceValue,
    StrikeRiderSource,
)
from .source_values import parse_decimal_integer
from .source_authority import (
    RawIndexStep,
    RawMemberStep,
    SourceAddress,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)


StrikeMode: TypeAlias = Literal["melee", "ranged"]
DeferredDependencyKind: TypeAlias = Literal[
    "compound-damage",
    "effect",
    "equipment",
    "runtime",
]

_HASH_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
_ATTACK_RE = re.compile(r"(?P<sign>[+-])(?P<value>[0-9]+)", re.ASCII)
_AMOUNT = r"\d+(?:d\d+)?(?:[+\-\u2013]\d+)?"
_DAMAGE_TYPES = (
    "acid",
    "bleed",
    "bludgeoning",
    "cold",
    "electricity",
    "fire",
    "force",
    "mental",
    "piercing",
    "poison",
    "precision",
    "slashing",
    "sonic",
    "spirit",
    "unholy",
    "vitality",
    "void",
)
_DAMAGE_TYPE_PATTERN = "|".join(_DAMAGE_TYPES)
_DAMAGE_COMPONENT_RE = re.compile(
    rf"^{_AMOUNT}\s+(?:persistent\s+)?"
    rf"(?P<type>{_DAMAGE_TYPE_PATTERN})(?:\b|$)",
    re.IGNORECASE,
)
_DAMAGE_COMPONENT_SCAN_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<amount>{_AMOUNT})\s+"
    rf"(?P<persistent>persistent\s+)?"
    rf"(?P<type>{_DAMAGE_TYPE_PATTERN})(?:\b|$)",
    re.IGNORECASE,
)
_TYPE_CHOICE_SCAN_RE = re.compile(
    rf"(?<![A-Za-z0-9]){_AMOUNT}\s+"
    rf"(?P<first>{_DAMAGE_TYPE_PATTERN}), "
    rf"(?P<second>{_DAMAGE_TYPE_PATTERN}), or "
    rf"(?P<third>{_DAMAGE_TYPE_PATTERN})(?:\b|$)",
    re.IGNORECASE,
)
_ANY_AMOUNT_RE = re.compile(rf"^{_AMOUNT}\b", re.IGNORECASE)
_SAFE_DAMAGE_RE = re.compile(
    rf"^(?P<base>\d+(?:d\d+)?)"
    rf"(?:(?P<sign>[+\-\u2013])(?P<modifier>\d+))?"
    rf"\s+(?P<persistent>persistent\s+)?"
    rf"(?P<type>{_DAMAGE_TYPE_PATTERN})$",
    re.IGNORECASE,
)
_TOP_LEVEL_CONNECTORS = (" plus ", " and ", " or ")
_CARRIER_KEYS = frozenset(("Damage", "Effect", "Effects"))
_KNOWN_STRIKE_KEYS = frozenset(
    ("Name", "Attack", "Traits", "Damage", "Effect", "Effects")
)
_TRAIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "range-increment",
        re.compile(r"^range increment (?P<feet>\d+) feet$", re.I),
    ),
    (
        "range-maximum",
        re.compile(r"^range (?P<feet>\d+) feet$", re.I),
    ),
    ("reload", re.compile(r"^reload (?P<actions>\d+)$", re.I)),
    (
        "thrown-distance",
        re.compile(r"^thrown (?P<feet>\d+) feet$", re.I),
    ),
    ("thrown-bare", re.compile(r"^thrown$", re.I)),
    (
        "reach-distance",
        re.compile(r"^reach (?P<feet>\d+) feet$", re.I),
    ),
    ("reach-bare", re.compile(r"^reach$", re.I)),
    (
        "deadly",
        re.compile(r"^deadly (?P<dice>(?:\d+)?d\d+)$", re.I),
    ),
    ("fatal", re.compile(r"^fatal (?P<dice>d\d+)$", re.I)),
    ("volley", re.compile(r"^volley (?P<feet>\d+) feet$", re.I)),
    (
        "versatile",
        re.compile(r"^versatile (?P<type>[A-Za-z]+)$", re.I),
    ),
    (
        "two-hand",
        re.compile(r"^two-hand(?:ed)? (?P<dice>(?:\d+)?d\d+)$", re.I),
    ),
)
_GEOMETRY_TRAIT_CATEGORIES = frozenset(
    (
        "range-increment",
        "range-maximum",
        "reload",
        "thrown-distance",
        "thrown-bare",
        "reach-distance",
        "reach-bare",
    )
)

_MAX_SIGNED_64 = (1 << 63) - 1
_MAX_TEXT_BYTES = 4_096
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 100_000
_MAX_JSON_BYTES = 1 << 20
_MAX_BLOCK_MEMBERS = 512
_MAX_STRIKES_PER_BLOCK = 512
_MAX_ADDRESS_PATH_STEPS = MAX_PATH_STEPS


class StrikeSourceError(ValueError):
    """Lossless source could not be recognized without guessing."""


class StrikeCompilerLinkError(StrikeSourceError):
    """A compiler patch did not resolve against the retained source."""


def _require_string(value: object, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be an exact string")
    if (
        not value
        or value != value.strip()
        or "\x00" in value
        or len(value.encode("utf-8")) > _MAX_TEXT_BYTES
    ):
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    return value


def _require_ordinal(value: object, label: str) -> int:
    if (
        type(value) is not int
        or value < 0
        or value > _MAX_SIGNED_64
    ):
        raise ValueError(
            f"{label} must be a bounded nonnegative integer"
        )
    return value


def _require_hash(value: object, label: str) -> str:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _ordered_tuple(value: object, label: str) -> tuple[Any, ...]:
    if type(value) not in (list, tuple):
        raise TypeError(f"{label} must be an explicit ordered sequence")
    return tuple(value)


def _bounded_ordered_tuple(
    value: object,
    label: str,
    maximum: int,
) -> tuple[Any, ...]:
    if type(value) not in (list, tuple):
        raise TypeError(f"{label} must be an explicit ordered sequence")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds its step bound")
    return tuple(value)


def _require_exact_mapping(
    value: object,
    keys: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    observed = frozenset(value)
    if observed != keys:
        missing = sorted(keys.difference(observed))
        extra = sorted(observed.difference(keys))
        raise ValueError(
            f"{label} has the wrong fields; "
            f"missing={missing}, extra={extra}"
        )
    if any(type(key) is not str for key in value):
        raise TypeError(f"{label} keys must be exact strings")
    return value


def _walk_json(
    value: Any,
    *,
    freeze: bool,
) -> Any:
    active: set[int] = set()
    nodes = 0

    def visit(item: Any, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise ValueError("review/projection exceeds its node bound")
        if depth > _MAX_JSON_DEPTH:
            raise ValueError("review/projection exceeds its depth bound")
        item_type = type(item)
        if item_type in (dict, MappingProxyType):
            identity = id(item)
            if identity in active:
                raise ValueError("review/projection contains a cycle")
            active.add(identity)
            try:
                result: dict[str, Any] = {}
                for key, child in item.items():
                    if type(key) is not str:
                        raise TypeError(
                            "review/projection keys must be exact strings"
                        )
                    if key in result:
                        raise ValueError(
                            "review/projection keys must be unique"
                        )
                    result[key] = visit(child, depth + 1)
            finally:
                active.remove(identity)
            return MappingProxyType(result) if freeze else result
        if item_type in (list, tuple):
            identity = id(item)
            if identity in active:
                raise ValueError("review/projection contains a cycle")
            active.add(identity)
            try:
                result = tuple(
                    visit(child, depth + 1)
                    for child in item
                )
            finally:
                active.remove(identity)
            return result if freeze else list(result)
        if item_type is float:
            if not math.isfinite(item):
                raise ValueError(
                    "review/projection numbers must be finite"
                )
            return item
        if item is None or item_type in (bool, int, str):
            if (
                item_type is int
                and (item < -_MAX_SIGNED_64 - 1 or item > _MAX_SIGNED_64)
            ):
                raise ValueError(
                    "review/projection integer exceeds signed-64"
                )
            if (
                item_type is str
                and (
                    "\x00" in item
                    or len(item.encode("utf-8")) > _MAX_TEXT_BYTES
                )
            ):
                raise ValueError(
                    "review/projection string exceeds its bound"
                )
            return item
        raise TypeError(
            "review/projection value is not exact JSON: "
            f"{item_type.__name__}"
        )

    result = visit(value, 0)
    thawed = result
    if freeze:
        thawed = _walk_json(result, freeze=False)
    if len(canonical_json_bytes(thawed)) > _MAX_JSON_BYTES:
        raise ValueError("review/projection exceeds its byte bound")
    return result


def _freeze_json(value: Any) -> Any:
    return _walk_json(value, freeze=True)


def _thaw_json(value: Any) -> Any:
    return _walk_json(value, freeze=False)


def raw_source_payload(value: RawSourceValue) -> Any:
    """Return the packet-compatible ordered JSON envelope for raw source."""

    if type(value) is RawSourceObject:
        return {
            "$orderedObject": [
                [member.key, raw_source_payload(member.value)]
                for member in value.members
            ]
        }
    if type(value) is RawSourceArray:
        return [raw_source_payload(item) for item in value.items]
    if (
        value is None
        or type(value) in (bool, int, str)
        or type(value) is float and math.isfinite(value)
    ):
        return value
    raise TypeError(
        "raw_source_payload requires a frozen RawSourceValue"
    )


def raw_source_sha256(value: RawSourceValue) -> str:
    """Hash exact raw source order, duplicate keys, spelling, and values."""

    payload = json.dumps(
        raw_source_payload(value),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_source_sha256(value: Mapping[str, Any]) -> str:
    """Hash a source address independently of mapping insertion order."""

    payload = json.dumps(
        _thaw_json(value),
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def semantic_source_key(raw_key: str) -> str:
    """Return the library semantic spelling without altering raw identity."""

    if raw_key.startswith("^."):
        parts = raw_key.split(".", 2)
        return parts[2] if len(parts) == 3 else raw_key
    if len(raw_key) > 2 and raw_key[1] == "." and raw_key[0] in "!%@#":
        return raw_key[2:]
    return raw_key


def normalized_source_text(value: object) -> str:
    return " ".join(str(value or "").split())


def strike_label_key(value: object) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "-",
        normalized_source_text(value).casefold(),
    ).strip("-")


@dataclass(frozen=True, slots=True)
class StrikeContainerPathSegment:
    raw_key: str
    semantic_key: str
    occurrence: int
    member_ordinal: int
    value_sha256: str

    def __post_init__(self) -> None:
        if type(self) is not StrikeContainerPathSegment:
            raise TypeError(
                "StrikeContainerPathSegment subclasses are not supported"
            )
        _require_string(
            self.raw_key,
            "Strike container raw_key",
        )
        _require_string(
            self.semantic_key,
            "Strike container semantic_key",
        )
        if self.semantic_key != semantic_source_key(self.raw_key):
            raise ValueError(
                "Strike container semantic_key changed raw key identity"
            )
        _require_ordinal(self.occurrence, "Strike container occurrence")
        _require_ordinal(
            self.member_ordinal,
            "Strike container member_ordinal",
        )
        _require_hash(
            self.value_sha256,
            "Strike container value_sha256",
        )

    @classmethod
    def from_serialized(
        cls,
        value: object,
        /,
    ) -> StrikeContainerPathSegment:
        if cls is not StrikeContainerPathSegment:
            raise TypeError(
                "StrikeContainerPathSegment subclasses are not supported"
            )
        raw = _require_exact_mapping(
            value,
            frozenset(
                {
                    "rawKey",
                    "semanticKey",
                    "occurrence",
                    "memberOrdinal",
                    "valueSha256",
                }
            ),
            "Strike container path segment",
        )
        return StrikeContainerPathSegment(
            raw_key=raw["rawKey"],
            semantic_key=raw["semanticKey"],
            occurrence=raw["occurrence"],
            member_ordinal=raw["memberOrdinal"],
            value_sha256=raw["valueSha256"],
        )

    def as_serialized(self) -> dict[str, Any]:
        return {
            "rawKey": self.raw_key,
            "semanticKey": self.semantic_key,
            "occurrence": self.occurrence,
            "memberOrdinal": self.member_ordinal,
            "valueSha256": self.value_sha256,
        }


@dataclass(frozen=True, slots=True)
class StrikeBlockAddress:
    source_id: str
    section_id: str
    locator: str
    toc_content_path: tuple[str, ...]
    resolved_container_path: tuple[StrikeContainerPathSegment, ...]
    block_raw_key: str
    block_occurrence: int
    block_member_ordinal: int
    ordered_block_sha256: str
    block_id: str
    section_ordinal: int

    def __post_init__(self) -> None:
        if type(self) is not StrikeBlockAddress:
            raise TypeError("StrikeBlockAddress subclasses are not supported")
        for field_name in (
            "source_id",
            "section_id",
            "locator",
            "block_id",
        ):
            _require_string(
                getattr(self, field_name),
                f"StrikeBlockAddress.{field_name}",
            )
        if not self.section_id.startswith(f"{self.source_id}:"):
            raise ValueError(
                "StrikeBlockAddress.section_id must belong to source_id"
            )
        path = _bounded_ordered_tuple(
            self.toc_content_path,
            "StrikeBlockAddress.toc_content_path",
            _MAX_ADDRESS_PATH_STEPS,
        )
        for index, part in enumerate(path):
            _require_string(
                part,
                f"StrikeBlockAddress.toc_content_path[{index}]",
            )
        object.__setattr__(self, "toc_content_path", path)

        resolved = _bounded_ordered_tuple(
            self.resolved_container_path,
            "StrikeBlockAddress.resolved_container_path",
            _MAX_ADDRESS_PATH_STEPS,
        )
        if not resolved or any(
            type(item) is not StrikeContainerPathSegment
            for item in resolved
        ):
            raise TypeError(
                "StrikeBlockAddress.resolved_container_path must contain "
                "one or more StrikeContainerPathSegment values"
            )
        if len(path) + len(resolved) > _MAX_ADDRESS_PATH_STEPS:
            raise ValueError(
                "StrikeBlockAddress combined path exceeds its step bound"
            )
        object.__setattr__(self, "resolved_container_path", resolved)
        if self.block_raw_key != "^.creature":
            raise ValueError(
                "StrikeBlockAddress.block_raw_key must be ^.creature"
            )
        _require_ordinal(
            self.block_occurrence,
            "StrikeBlockAddress.block_occurrence",
        )
        _require_ordinal(
            self.block_member_ordinal,
            "StrikeBlockAddress.block_member_ordinal",
        )
        _require_hash(
            self.ordered_block_sha256,
            "StrikeBlockAddress.ordered_block_sha256",
        )
        _require_ordinal(
            self.section_ordinal,
            "StrikeBlockAddress.section_ordinal",
        )
        _freeze_json(self.as_serialized())

    @classmethod
    def from_serialized(
        cls,
        value: object,
        /,
    ) -> StrikeBlockAddress:
        if cls is not StrikeBlockAddress:
            raise TypeError("StrikeBlockAddress subclasses are not supported")
        raw = _require_exact_mapping(
            value,
            frozenset(
                {
                    "sourceId",
                    "sectionId",
                    "locator",
                    "tocContentPath",
                    "resolvedContainerPath",
                    "blockMember",
                    "blockId",
                    "sectionOrdinal",
                }
            ),
            "Strike block address",
        )
        block = _require_exact_mapping(
            raw["blockMember"],
            frozenset(
                {
                    "rawKey",
                    "occurrence",
                    "memberOrdinal",
                    "orderedBlockSha256",
                }
            ),
            "Strike block address blockMember",
        )
        path = _bounded_ordered_tuple(
            raw["tocContentPath"],
            "Strike block address tocContentPath",
            _MAX_ADDRESS_PATH_STEPS,
        )
        resolved = _bounded_ordered_tuple(
            raw["resolvedContainerPath"],
            "Strike block address resolvedContainerPath",
            _MAX_ADDRESS_PATH_STEPS,
        )
        if len(path) + len(resolved) > _MAX_ADDRESS_PATH_STEPS:
            raise ValueError(
                "Strike block address combined path exceeds its step bound"
            )
        return StrikeBlockAddress(
            source_id=raw["sourceId"],
            section_id=raw["sectionId"],
            locator=raw["locator"],
            toc_content_path=path,
            resolved_container_path=tuple(
                StrikeContainerPathSegment.from_serialized(item)
                for item in resolved
            ),
            block_raw_key=block["rawKey"],
            block_occurrence=block["occurrence"],
            block_member_ordinal=block["memberOrdinal"],
            ordered_block_sha256=block["orderedBlockSha256"],
            block_id=raw["blockId"],
            section_ordinal=raw["sectionOrdinal"],
        )

    def as_serialized(self) -> dict[str, Any]:
        return {
            "sourceId": self.source_id,
            "sectionId": self.section_id,
            "locator": self.locator,
            "tocContentPath": list(self.toc_content_path),
            "resolvedContainerPath": [
                item.as_serialized()
                for item in self.resolved_container_path
            ],
            "blockMember": {
                "rawKey": self.block_raw_key,
                "occurrence": self.block_occurrence,
                "memberOrdinal": self.block_member_ordinal,
                "orderedBlockSha256": self.ordered_block_sha256,
            },
            "blockId": self.block_id,
            "sectionOrdinal": self.section_ordinal,
        }

    @property
    def address_sha256(self) -> str:
        return canonical_source_sha256(self.as_serialized())


@dataclass(frozen=True, slots=True)
class StrikeOuterAddress:
    raw_key: Literal["Melee", "Ranged"]
    occurrence: int
    member_ordinal: int

    def __post_init__(self) -> None:
        if type(self) is not StrikeOuterAddress:
            raise TypeError("StrikeOuterAddress subclasses are not supported")
        if self.raw_key not in ("Melee", "Ranged"):
            raise ValueError(
                "StrikeOuterAddress.raw_key must be Melee or Ranged"
            )
        _require_ordinal(
            self.occurrence,
            "StrikeOuterAddress.occurrence",
        )
        _require_ordinal(
            self.member_ordinal,
            "StrikeOuterAddress.member_ordinal",
        )

    @classmethod
    def from_serialized(
        cls,
        value: object,
        /,
    ) -> StrikeOuterAddress:
        if cls is not StrikeOuterAddress:
            raise TypeError("StrikeOuterAddress subclasses are not supported")
        raw = _require_exact_mapping(
            value,
            frozenset({"rawKey", "occurrence", "memberOrdinal"}),
            "Strike outer address",
        )
        return StrikeOuterAddress(
            raw_key=raw["rawKey"],
            occurrence=raw["occurrence"],
            member_ordinal=raw["memberOrdinal"],
        )

    @property
    def mode(self) -> StrikeMode:
        return "melee" if self.raw_key == "Melee" else "ranged"

    def as_serialized(self) -> dict[str, Any]:
        return {
            "rawKey": self.raw_key,
            "occurrence": self.occurrence,
            "memberOrdinal": self.member_ordinal,
        }


@dataclass(frozen=True, slots=True)
class StrikeSourceAddress:
    block: StrikeBlockAddress
    outer: StrikeOuterAddress
    strike_ordinal: int

    def __post_init__(self) -> None:
        if type(self) is not StrikeSourceAddress:
            raise TypeError("StrikeSourceAddress subclasses are not supported")
        if type(self.block) is not StrikeBlockAddress:
            raise TypeError(
                "StrikeSourceAddress.block must be a StrikeBlockAddress"
            )
        if type(self.outer) is not StrikeOuterAddress:
            raise TypeError(
                "StrikeSourceAddress.outer must be a StrikeOuterAddress"
            )
        _require_ordinal(
            self.strike_ordinal,
            "StrikeSourceAddress.strike_ordinal",
        )

    @classmethod
    def from_serialized(
        cls,
        value: object,
        /,
    ) -> StrikeSourceAddress:
        if cls is not StrikeSourceAddress:
            raise TypeError("StrikeSourceAddress subclasses are not supported")
        raw = _require_exact_mapping(
            value,
            frozenset(
                {
                    "sourceId",
                    "sectionId",
                    "locator",
                    "tocContentPath",
                    "resolvedContainerPath",
                    "blockMember",
                    "blockId",
                    "sectionOrdinal",
                    "strikeOuterField",
                    "strikeOrdinal",
                }
            ),
            "Strike source address",
        )
        block_raw = {
            key: raw[key]
            for key in (
                "sourceId",
                "sectionId",
                "locator",
                "tocContentPath",
                "resolvedContainerPath",
                "blockMember",
                "blockId",
                "sectionOrdinal",
            )
        }
        return StrikeSourceAddress(
            block=StrikeBlockAddress.from_serialized(block_raw),
            outer=StrikeOuterAddress.from_serialized(
                raw["strikeOuterField"]
            ),
            strike_ordinal=raw["strikeOrdinal"],
        )

    def as_serialized(self) -> dict[str, Any]:
        return {
            **self.block.as_serialized(),
            "strikeOuterField": self.outer.as_serialized(),
            "strikeOrdinal": self.strike_ordinal,
        }

    @property
    def address_sha256(self) -> str:
        return canonical_source_sha256(self.as_serialized())


def _source_receipt_bytes(value: object, label: str) -> bytes:
    if type(value) is not SourceReceipt:
        raise TypeError(f"{label} must be an exact SourceReceipt")
    return canonical_json_bytes(SourceReceipt.as_serialized(value))


def _validated_creature_selection(
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
) -> VerifiedSourceSelection:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "Strike compilation requires an exact SourceAuthorityAdapter"
        )
    if type(consumer) is not VerifiedSourceSelection:
        raise TypeError(
            "Strike compilation requires an exact VerifiedSourceSelection"
        )
    verified = authority.validate_selection(consumer)
    if type(verified) is not VerifiedSourceSelection:
        raise TypeError(
            "Strike authority returned a non-exact verified selection"
        )
    address = verified.address
    if (
        type(address) is not SourceAddress
        or address.source_id not in {"core-mc1", "core-mc2"}
        or address.span is not None
        or address.selection_path != ()
        or not address.carrier_path
        or (
            len(address.target_path)
            + len(address.carrier_path)
            > 256
        )
    ):
        raise StrikeSourceError(
            "Strike consumer must be one exact supported Monster Core "
            "creature block"
        )
    carrier_step = address.carrier_path[-1]
    if (
        type(carrier_step) is not RawMemberStep
        or carrier_step.raw_key != "^.creature"
    ):
        raise StrikeSourceError(
            "Strike consumer must end at an exact ^.creature carrier"
        )
    raw_block = verified.raw_value
    if (
        type(raw_block) is not RawSourceObject
        or type(verified.carrier.raw_block) is not RawSourceObject
        or raw_block is not verified.carrier.raw_block
    ):
        raise StrikeSourceError(
            "Strike consumer must select its exact creature carrier object"
        )
    if (
        not raw_block.members
        or len(raw_block.members) > _MAX_BLOCK_MEMBERS
        or any(type(member) is not RawSourceMember for member in raw_block.members)
    ):
        raise StrikeSourceError(
            "Strike creature block exceeds its exact member contract"
        )
    name_values = raw_block.values("Name")
    if (
        len(name_values) != 1
        or type(name_values[0]) is not str
        or not name_values[0].strip()
    ):
        raise StrikeSourceError(
            "Strike creature block requires one exact Name string"
        )
    receipt = verified.receipt
    if (
        receipt.block_sha256 != verified.block_sha256
        or receipt.value_sha256 != verified.value_sha256
        or receipt.selection_sha256 != verified.selection_sha256
        or receipt.member_sha256 is not None
    ):
        raise StrikeSourceError(
            "Strike creature receipt disagrees with its verified block"
        )
    return verified


def _diagnostic_block_address(
    verified: VerifiedSourceSelection,
) -> StrikeBlockAddress:
    """Derive an untrusted display/debug address from verified authority."""

    source = verified.address
    carrier_step = source.carrier_path[-1]
    if type(carrier_step) is not RawMemberStep:
        raise StrikeSourceError("Strike carrier step is not exact")
    raw_block = verified.raw_value
    if type(raw_block) is not RawSourceObject:
        raise StrikeSourceError("Strike carrier value is not an object")
    ordered_sha256 = raw_source_sha256(raw_block)
    # This diagnostic digest deliberately retains the historical packet
    # envelope.  The authenticated receipt uses source_authority's distinct
    # canonical-raw digest and remains the only authority boundary.
    prefix_steps = (
        *source.target_path,
        *source.carrier_path[:-1],
    )
    target_path = tuple(
        json.dumps(
            step.as_serialized(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for step in prefix_steps
    )
    if not target_path:
        target_path = (source.section_id,)
    resolved_segments = []
    for ordinal, step in enumerate(prefix_steps):
        if type(step) is RawMemberStep:
            raw_key = step.raw_key
            member_ordinal = step.member_ordinal
        elif type(step) is RawIndexStep:
            raw_key = f"[{step.item_ordinal}]"
            member_ordinal = step.item_ordinal
        else:
            raise StrikeSourceError(
                "Strike diagnostic path contains a non-exact step"
            )
        prefix_digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    "authoritySelectionSha256": (
                        verified.selection_sha256
                    ),
                    "pathPrefix": [
                        item.as_serialized()
                        for item in prefix_steps[: ordinal + 1]
                    ],
                }
            )
        ).hexdigest()
        resolved_segments.append(
            StrikeContainerPathSegment(
                raw_key=raw_key,
                semantic_key=semantic_source_key(raw_key),
                occurrence=0,
                member_ordinal=member_ordinal,
                value_sha256=prefix_digest,
            )
        )
    if not resolved_segments:
        resolved_segments.append(
            StrikeContainerPathSegment(
                raw_key="@authority-target",
                semantic_key="@authority-target",
                occurrence=0,
                member_ordinal=0,
                value_sha256=hashlib.sha256(
                    canonical_json_bytes(
                        {
                            "authoritySelectionSha256": (
                                verified.selection_sha256
                            )
                        }
                    )
                ).hexdigest(),
            )
        )
    return StrikeBlockAddress(
        source_id=source.source_id,
        section_id=source.section_id,
        locator=source.locator,
        toc_content_path=target_path,
        resolved_container_path=tuple(resolved_segments),
        block_raw_key=carrier_step.raw_key,
        block_occurrence=0,
        block_member_ordinal=carrier_step.member_ordinal,
        ordered_block_sha256=ordered_sha256,
        block_id=f"authority:{verified.selection_sha256}",
        section_ordinal=carrier_step.member_ordinal,
    )


@dataclass(frozen=True, slots=True, init=False)
class StrikeBlockSource:
    address: StrikeBlockAddress
    raw_block: RawSourceObject
    source_receipt: SourceReceipt
    _authority: SourceAuthorityAdapter = field(
        repr=False,
        compare=False,
    )
    _consumer: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "StrikeBlockSource can only be constructed by the Strike compiler"
        )

    def __copy__(self) -> StrikeBlockSource:
        raise TypeError("StrikeBlockSource cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> StrikeBlockSource:
        raise TypeError("StrikeBlockSource cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("StrikeBlockSource cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("StrikeBlockSource cannot be pickled")


def _validate_block_source(value: object) -> StrikeBlockSource:
    if type(value) is not StrikeBlockSource:
        raise TypeError("Strike block source must be exact")
    if type(value._authority) is not SourceAuthorityAdapter:
        raise TypeError("Strike block source authority must be exact")
    if type(value._consumer) is not VerifiedSourceSelection:
        raise TypeError("Strike block source consumer must be exact")
    verified = _validated_creature_selection(
        value._authority,
        value._consumer,
    )
    if (
        type(value.address) is not StrikeBlockAddress
        or type(value.raw_block) is not RawSourceObject
        or value.raw_block is not verified.raw_value
        or value.address != _diagnostic_block_address(verified)
        or _source_receipt_bytes(
            value.source_receipt,
            "StrikeBlockSource.source_receipt",
        )
        != _source_receipt_bytes(
            verified.receipt,
            "verified Strike creature receipt",
        )
    ):
        raise StrikeSourceError(
            "Strike block source disagrees with authenticated authority"
        )
    return value


def _new_block_source(
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
) -> StrikeBlockSource:
    verified = _validated_creature_selection(authority, consumer)
    result = object.__new__(StrikeBlockSource)
    object.__setattr__(
        result,
        "address",
        _diagnostic_block_address(verified),
    )
    object.__setattr__(result, "raw_block", verified.raw_value)
    object.__setattr__(result, "source_receipt", verified.receipt)
    object.__setattr__(result, "_authority", authority)
    object.__setattr__(result, "_consumer", verified)
    return _validate_block_source(result)


@dataclass(frozen=True, slots=True)
class StrikeReviewEvidence:
    cohort: str
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_string(self.cohort, "StrikeReviewEvidence.cohort")
        if not isinstance(self.evidence, Mapping):
            raise TypeError(
                "StrikeReviewEvidence.evidence must be a mapping"
            )
        object.__setattr__(self, "evidence", _freeze_json(self.evidence))

    @property
    def evidence_sha256(self) -> str:
        return canonical_source_sha256(self.evidence)

    def as_serialized(self) -> dict[str, Any]:
        return {
            "cohort": self.cohort,
            "evidence": _thaw_json(self.evidence),
            "evidenceSha256": self.evidence_sha256,
        }


@dataclass(frozen=True, slots=True)
class StrikeMemberSource:
    source_address: StrikeSourceAddress
    raw_member: RawSourceMember
    semantic_key: str
    occurrence: int
    member_ordinal: int
    raw_value_sha256: str
    address_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_address, StrikeSourceAddress):
            raise TypeError(
                "StrikeMemberSource.source_address must be a "
                "StrikeSourceAddress"
            )
        if not isinstance(self.raw_member, RawSourceMember):
            raise TypeError(
                "StrikeMemberSource.raw_member must be a RawSourceMember"
            )
        if self.semantic_key != semantic_source_key(self.raw_member.key):
            raise ValueError(
                "StrikeMemberSource.semantic_key changed raw key identity"
            )
        _require_ordinal(
            self.occurrence,
            "StrikeMemberSource.occurrence",
        )
        _require_ordinal(
            self.member_ordinal,
            "StrikeMemberSource.member_ordinal",
        )
        if self.raw_value_sha256 != raw_source_sha256(
            self.raw_member.value
        ):
            raise ValueError(
                "StrikeMemberSource.raw_value_sha256 is stale"
            )
        _require_hash(
            self.address_sha256,
            "StrikeMemberSource.address_sha256",
        )
        if self.address_sha256 != canonical_source_sha256(
            {
                **self.source_address.as_serialized(),
                "member": {
                    "rawKey": self.raw_member.key,
                    "semanticKey": self.semantic_key,
                    "occurrence": self.occurrence,
                    "memberOrdinal": self.member_ordinal,
                },
            }
        ):
            raise ValueError(
                "StrikeMemberSource.address_sha256 is stale"
            )


@dataclass(frozen=True, slots=True)
class StrikeTraitSource:
    source_address: StrikeSourceAddress
    member_ordinal: int
    member_occurrence: int
    trait_ordinal: int
    raw_value: RawSourceValue
    raw_text: str | None
    normalized_text: str | None
    category: str
    parsed: Mapping[str, Any]
    raw_value_sha256: str
    address_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_address, StrikeSourceAddress):
            raise TypeError(
                "StrikeTraitSource.source_address must be a "
                "StrikeSourceAddress"
            )
        for field_name in (
            "member_ordinal",
            "member_occurrence",
            "trait_ordinal",
        ):
            _require_ordinal(
                getattr(self, field_name),
                f"StrikeTraitSource.{field_name}",
            )
        if self.raw_text is not None and not isinstance(
            self.raw_text,
            str,
        ):
            raise TypeError(
                "StrikeTraitSource.raw_text must be a string or None"
            )
        if self.normalized_text is not None and not isinstance(
            self.normalized_text,
            str,
        ):
            raise TypeError(
                "StrikeTraitSource.normalized_text must be a string or None"
            )
        _require_string(self.category, "StrikeTraitSource.category")
        if not isinstance(self.parsed, Mapping):
            raise TypeError(
                "StrikeTraitSource.parsed must be a mapping"
            )
        object.__setattr__(self, "parsed", _freeze_json(self.parsed))
        if self.raw_value_sha256 != raw_source_sha256(self.raw_value):
            raise ValueError(
                "StrikeTraitSource.raw_value_sha256 is stale"
            )
        _require_hash(
            self.address_sha256,
            "StrikeTraitSource.address_sha256",
        )
        if self.address_sha256 != canonical_source_sha256(
            {
                **self.source_address.as_serialized(),
                "trait": {"traitOrdinal": self.trait_ordinal},
            }
        ):
            raise ValueError(
                "StrikeTraitSource.address_sha256 is stale"
            )


@dataclass(frozen=True, slots=True)
class StrikeRangeProfile:
    mode: StrikeMode
    geometry_kind: str
    status: Literal[
        "structurally-recognized",
        "requires-rule-reconciliation",
        "fail-closed",
    ]
    feet: int | None
    reload_actions: int | None
    reload_explicit: bool
    descriptor_address_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.mode not in ("melee", "ranged"):
            raise ValueError(
                "StrikeRangeProfile.mode must be melee or ranged"
            )
        _require_string(
            self.geometry_kind,
            "StrikeRangeProfile.geometry_kind",
        )
        if self.status not in (
            "structurally-recognized",
            "requires-rule-reconciliation",
            "fail-closed",
        ):
            raise ValueError("StrikeRangeProfile.status is invalid")
        for field_name in ("feet", "reload_actions"):
            value = getattr(self, field_name)
            if value is not None:
                _require_ordinal(
                    value,
                    f"StrikeRangeProfile.{field_name}",
                )
        if type(self.reload_explicit) is not bool:
            raise TypeError(
                "StrikeRangeProfile.reload_explicit must be a boolean"
            )
        descriptors = _ordered_tuple(
            self.descriptor_address_sha256,
            "StrikeRangeProfile.descriptor_address_sha256",
        )
        for index, digest in enumerate(descriptors):
            _require_hash(
                digest,
                "StrikeRangeProfile.descriptor_address_sha256"
                f"[{index}]",
            )
        object.__setattr__(
            self,
            "descriptor_address_sha256",
            descriptors,
        )

    def as_serialized(self) -> dict[str, Any]:
        if self.mode == "melee":
            return {
                "mode": self.mode,
                "geometryKind": self.geometry_kind,
                "status": self.status,
                "reachFeet": self.feet,
                "descriptorAddressSha256": list(
                    self.descriptor_address_sha256
                ),
            }
        return {
            "mode": self.mode,
            "geometryKind": self.geometry_kind,
            "status": self.status,
            "feet": self.feet,
            "reloadActions": self.reload_actions,
            "reloadExplicit": self.reload_explicit,
            "descriptorAddressSha256": list(
                self.descriptor_address_sha256
            ),
        }


@dataclass(frozen=True, slots=True)
class StrikeCarrierTerm:
    carrier_address_sha256: str
    term_ordinal: int
    connector_before: str | None
    start: int
    end: int
    raw_text: str
    raw_text_sha256: str
    candidate_class: str
    tail_ordinal: int | None
    rider_ordinal: int | None
    rider_address_sha256: str | None

    def __post_init__(self) -> None:
        _require_hash(
            self.carrier_address_sha256,
            "StrikeCarrierTerm.carrier_address_sha256",
        )
        for field_name in ("term_ordinal", "start", "end"):
            _require_ordinal(
                getattr(self, field_name),
                f"StrikeCarrierTerm.{field_name}",
            )
        if self.end < self.start:
            raise ValueError(
                "StrikeCarrierTerm.end must not precede start"
            )
        if self.connector_before is not None and (
            self.connector_before not in _TOP_LEVEL_CONNECTORS
        ):
            raise ValueError(
                "StrikeCarrierTerm.connector_before is invalid"
            )
        if not isinstance(self.raw_text, str):
            raise TypeError(
                "StrikeCarrierTerm.raw_text must be a string"
            )
        _require_hash(
            self.raw_text_sha256,
            "StrikeCarrierTerm.raw_text_sha256",
        )
        if self.raw_text_sha256 != raw_source_sha256(self.raw_text):
            raise ValueError(
                "StrikeCarrierTerm.raw_text_sha256 is stale"
            )
        _require_string(
            self.candidate_class,
            "StrikeCarrierTerm.candidate_class",
        )
        if self.tail_ordinal is not None:
            _require_ordinal(
                self.tail_ordinal,
                "StrikeCarrierTerm.tail_ordinal",
            )
        if self.rider_ordinal is None:
            if self.rider_address_sha256 is not None:
                raise ValueError(
                    "non-rider term cannot carry a rider address"
                )
        else:
            _require_ordinal(
                self.rider_ordinal,
                "StrikeCarrierTerm.rider_ordinal",
            )
            _require_hash(
                self.rider_address_sha256,
                "StrikeCarrierTerm.rider_address_sha256",
            )


@dataclass(frozen=True, slots=True)
class StrikeDamageComponentCandidate:
    component_ordinal: int
    source_text: str
    start: int
    end: int
    damage_type: str
    persistent: bool

    def __post_init__(self) -> None:
        for field_name in ("component_ordinal", "start", "end"):
            _require_ordinal(
                getattr(self, field_name),
                f"StrikeDamageComponentCandidate.{field_name}",
            )
        if self.end < self.start:
            raise ValueError(
                "StrikeDamageComponentCandidate.end must not precede start"
            )
        if not isinstance(self.source_text, str):
            raise TypeError(
                "StrikeDamageComponentCandidate.source_text must be a "
                "string"
            )
        _require_string(
            self.damage_type,
            "StrikeDamageComponentCandidate.damage_type",
        )
        if type(self.persistent) is not bool:
            raise TypeError(
                "StrikeDamageComponentCandidate.persistent must be boolean"
            )


@dataclass(frozen=True, slots=True)
class StrikeDamageProjection:
    source_text: str
    dice_count: int | None
    die_size: int | None
    flat_amount: int | None
    modifier: int
    damage_type: str
    persistent: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source_text, str):
            raise TypeError(
                "StrikeDamageProjection.source_text must be a string"
            )
        if self.dice_count is None:
            if self.die_size is not None or self.flat_amount is None:
                raise ValueError(
                    "flat damage projection has inconsistent amount fields"
                )
        else:
            _require_ordinal(
                self.dice_count,
                "StrikeDamageProjection.dice_count",
            )
            if self.dice_count == 0:
                raise ValueError(
                    "StrikeDamageProjection.dice_count must be positive"
                )
            if self.die_size is None:
                raise ValueError(
                    "dice damage projection requires die_size"
                )
            _require_ordinal(
                self.die_size,
                "StrikeDamageProjection.die_size",
            )
            if self.die_size == 0 or self.flat_amount is not None:
                raise ValueError(
                    "dice damage projection has inconsistent amount fields"
                )
        if type(self.modifier) is not int:
            raise TypeError(
                "StrikeDamageProjection.modifier must be an integer"
            )
        _require_string(
            self.damage_type,
            "StrikeDamageProjection.damage_type",
        )
        if type(self.persistent) is not bool:
            raise TypeError(
                "StrikeDamageProjection.persistent must be boolean"
            )


def _safe_damage_projection(
    source_text: str,
) -> StrikeDamageProjection | None:
    if type(source_text) is not str:
        return None
    match = _SAFE_DAMAGE_RE.fullmatch(source_text)
    if match is None:
        return None
    base = match.group("base")
    sign = match.group("sign")
    modifier_text = match.group("modifier")
    if modifier_text is None:
        modifier = 0
    else:
        parsed_modifier = parse_decimal_integer(modifier_text)
        if parsed_modifier is None:
            return None
        modifier = parsed_modifier
        if sign in ("-", "\u2013"):
            modifier = -modifier
    if "d" in base:
        dice_count_text, die_size_text = base.split("d", 1)
        dice_count = parse_decimal_integer(dice_count_text)
        die_size = parse_decimal_integer(die_size_text)
        if (
            dice_count is None
            or die_size is None
            or dice_count <= 0
            or die_size <= 0
        ):
            return None
        flat_amount = None
    else:
        dice_count = None
        die_size = None
        flat_amount = parse_decimal_integer(base)
        if flat_amount is None:
            return None
    return StrikeDamageProjection(
        source_text=source_text,
        dice_count=dice_count,
        die_size=die_size,
        flat_amount=flat_amount,
        modifier=modifier,
        damage_type=match.group("type").casefold(),
        persistent=bool(match.group("persistent")),
    )


@dataclass(frozen=True, slots=True)
class StrikeCarrierSource:
    source_address: StrikeSourceAddress
    raw_member: RawSourceMember
    occurrence: int
    member_ordinal: int
    carrier_ordinal: int
    raw_value_sha256: str
    address_sha256: str
    raw_text: str | None
    shape: str
    terms: tuple[StrikeCarrierTerm, ...]
    component_candidates: tuple[StrikeDamageComponentCandidate, ...]
    damage_type_candidates: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_address, StrikeSourceAddress):
            raise TypeError(
                "StrikeCarrierSource.source_address must be a "
                "StrikeSourceAddress"
            )
        if (
            not isinstance(self.raw_member, RawSourceMember)
            or self.raw_member.key not in _CARRIER_KEYS
        ):
            raise TypeError(
                "StrikeCarrierSource.raw_member must be an exact "
                "Damage/Effect/Effects RawSourceMember"
            )
        for field_name in (
            "occurrence",
            "member_ordinal",
            "carrier_ordinal",
        ):
            _require_ordinal(
                getattr(self, field_name),
                f"StrikeCarrierSource.{field_name}",
            )
        if self.raw_value_sha256 != raw_source_sha256(
            self.raw_member.value
        ):
            raise ValueError(
                "StrikeCarrierSource.raw_value_sha256 is stale"
            )
        _require_hash(
            self.address_sha256,
            "StrikeCarrierSource.address_sha256",
        )
        address = {
            **self.source_address.as_serialized(),
            "carrier": {
                "rawKey": self.raw_member.key,
                "occurrence": self.occurrence,
                "memberOrdinal": self.member_ordinal,
                "carrierOrdinal": self.carrier_ordinal,
            },
        }
        if self.address_sha256 != canonical_source_sha256(address):
            raise ValueError(
                "StrikeCarrierSource.address_sha256 is stale"
            )
        if self.raw_text is not None and not isinstance(
            self.raw_text,
            str,
        ):
            raise TypeError(
                "StrikeCarrierSource.raw_text must be a string or None"
            )
        _require_string(self.shape, "StrikeCarrierSource.shape")
        terms = _ordered_tuple(
            self.terms,
            "StrikeCarrierSource.terms",
        )
        if any(not isinstance(term, StrikeCarrierTerm) for term in terms):
            raise TypeError(
                "StrikeCarrierSource.terms must contain "
                "StrikeCarrierTerm values"
            )
        for index, term in enumerate(terms):
            if term.carrier_address_sha256 != self.address_sha256:
                raise ValueError(
                    "StrikeCarrierSource term belongs to another carrier"
                )
            if term.term_ordinal != index:
                raise ValueError(
                    "StrikeCarrierSource term ordinals are not consecutive"
                )
            if self.raw_text is None:
                raise ValueError(
                    "non-text Strike carrier cannot contain text terms"
                )
            if self.raw_text[term.start : term.end] != term.raw_text:
                raise ValueError(
                    "StrikeCarrierSource term span is stale"
                )
            if index == 0 and term.connector_before is not None:
                raise ValueError(
                    "first Strike carrier term cannot have a connector"
                )
            if index > 0 and term.connector_before is None:
                raise ValueError(
                    "later Strike carrier term requires a connector"
                )
            if term.rider_ordinal is not None:
                expected_rider_address = canonical_source_sha256(
                    {
                        **address,
                        "rider": {
                            "riderOrdinal": term.rider_ordinal,
                            "termOrdinal": term.term_ordinal,
                        },
                    }
                )
                if term.rider_address_sha256 != expected_rider_address:
                    raise ValueError(
                        "StrikeCarrierSource rider address is stale"
                    )
        components = _ordered_tuple(
            self.component_candidates,
            "StrikeCarrierSource.component_candidates",
        )
        if any(
            not isinstance(item, StrikeDamageComponentCandidate)
            for item in components
        ):
            raise TypeError(
                "StrikeCarrierSource.component_candidates must contain "
                "StrikeDamageComponentCandidate values"
            )
        for index, component in enumerate(components):
            if component.component_ordinal != index:
                raise ValueError(
                    "Strike damage component ordinals are not consecutive"
                )
            if (
                self.raw_text is None
                or self.raw_text[component.start : component.end]
                != component.source_text
            ):
                raise ValueError(
                    "Strike damage component span is stale"
                )
        damage_types = _ordered_tuple(
            self.damage_type_candidates,
            "StrikeCarrierSource.damage_type_candidates",
        )
        if any(not isinstance(item, str) for item in damage_types):
            raise TypeError(
                "StrikeCarrierSource.damage_type_candidates must contain "
                "strings"
            )
        object.__setattr__(self, "terms", terms)
        object.__setattr__(self, "component_candidates", components)
        object.__setattr__(
            self,
            "damage_type_candidates",
            damage_types,
        )

    @property
    def rider_terms(self) -> tuple[StrikeCarrierTerm, ...]:
        return tuple(
            term
            for term in self.terms
            if term.rider_ordinal is not None
        )

    @property
    def safe_damage_projection(self) -> StrikeDamageProjection | None:
        if (
            self.raw_member.key != "Damage"
            or self.shape != "single-component"
            or self.raw_text is None
            or len(self.component_candidates) != 1
            or self.component_candidates[0].source_text != self.raw_text
        ):
            return None
        return _safe_damage_projection(self.raw_text)


@dataclass(frozen=True, slots=True)
class StrikeItemCandidate:
    kind: str
    text: str
    label_key: str

    def __post_init__(self) -> None:
        _require_string(self.kind, "StrikeItemCandidate.kind")
        _require_string(self.text, "StrikeItemCandidate.text")
        _require_string(self.label_key, "StrikeItemCandidate.label_key")


@dataclass(frozen=True, slots=True)
class StrikeItemToken:
    item_ordinal: int
    raw_value: RawSourceValue
    raw_text: str | None
    raw_value_sha256: str
    address_sha256: str
    base_candidates: tuple[StrikeItemCandidate, ...]

    def __post_init__(self) -> None:
        _require_ordinal(
            self.item_ordinal,
            "StrikeItemToken.item_ordinal",
        )
        if self.raw_text is not None and not isinstance(
            self.raw_text,
            str,
        ):
            raise TypeError(
                "StrikeItemToken.raw_text must be a string or None"
            )
        if self.raw_value_sha256 != raw_source_sha256(self.raw_value):
            raise ValueError(
                "StrikeItemToken.raw_value_sha256 is stale"
            )
        _require_hash(
            self.address_sha256,
            "StrikeItemToken.address_sha256",
        )
        candidates = _ordered_tuple(
            self.base_candidates,
            "StrikeItemToken.base_candidates",
        )
        if any(
            not isinstance(item, StrikeItemCandidate)
            for item in candidates
        ):
            raise TypeError(
                "StrikeItemToken.base_candidates must contain "
                "StrikeItemCandidate values"
            )
        object.__setattr__(self, "base_candidates", candidates)


@dataclass(frozen=True, slots=True)
class StrikeItemsField:
    block_address: StrikeBlockAddress
    raw_member: RawSourceMember
    occurrence: int
    member_ordinal: int
    raw_value_sha256: str
    address_sha256: str
    tokens: tuple[StrikeItemToken, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.block_address, StrikeBlockAddress):
            raise TypeError(
                "StrikeItemsField.block_address must be a "
                "StrikeBlockAddress"
            )
        if (
            not isinstance(self.raw_member, RawSourceMember)
            or self.raw_member.key != "Items"
        ):
            raise TypeError(
                "StrikeItemsField.raw_member must be an exact Items member"
            )
        for field_name in ("occurrence", "member_ordinal"):
            _require_ordinal(
                getattr(self, field_name),
                f"StrikeItemsField.{field_name}",
            )
        if self.raw_value_sha256 != raw_source_sha256(
            self.raw_member.value
        ):
            raise ValueError(
                "StrikeItemsField.raw_value_sha256 is stale"
            )
        _require_hash(
            self.address_sha256,
            "StrikeItemsField.address_sha256",
        )
        field_address_value = {
            **self.block_address.as_serialized(),
            "itemsField": {
                "rawKey": "Items",
                "occurrence": self.occurrence,
                "memberOrdinal": self.member_ordinal,
            },
        }
        expected = canonical_source_sha256(field_address_value)
        if self.address_sha256 != expected:
            raise ValueError(
                "StrikeItemsField.address_sha256 is stale"
            )
        tokens = _ordered_tuple(
            self.tokens,
            "StrikeItemsField.tokens",
        )
        if any(not isinstance(item, StrikeItemToken) for item in tokens):
            raise TypeError(
                "StrikeItemsField.tokens must contain StrikeItemToken values"
            )
        raw_values = (
            self.raw_member.value.items
            if isinstance(self.raw_member.value, RawSourceArray)
            else (self.raw_member.value,)
        )
        if len(tokens) != len(raw_values):
            raise ValueError(
                "StrikeItemsField token count changed raw inventory"
            )
        for index, (token, raw_value) in enumerate(
            zip(tokens, raw_values, strict=True)
        ):
            if (
                token.item_ordinal != index
                or token.raw_value != raw_value
                or token.raw_text
                != (raw_value if isinstance(raw_value, str) else None)
                or token.address_sha256
                != canonical_source_sha256(
                    {
                        **field_address_value,
                        "item": {"itemOrdinal": index},
                    }
                )
                or token.base_candidates
                != (
                    _item_candidates(raw_value)
                    if isinstance(raw_value, str)
                    else ()
                )
            ):
                raise ValueError(
                    "StrikeItemsField token projection is stale"
                )
        object.__setattr__(self, "tokens", tokens)


@dataclass(frozen=True, slots=True)
class StrikeEquipmentEvidence:
    evidence_kind: str
    items_field_address_sha256: str
    item_address_sha256: str
    item_ordinal: int
    raw_text: str
    candidate_text: str

    def __post_init__(self) -> None:
        _require_string(
            self.evidence_kind,
            "StrikeEquipmentEvidence.evidence_kind",
        )
        _require_hash(
            self.items_field_address_sha256,
            "StrikeEquipmentEvidence.items_field_address_sha256",
        )
        _require_hash(
            self.item_address_sha256,
            "StrikeEquipmentEvidence.item_address_sha256",
        )
        _require_ordinal(
            self.item_ordinal,
            "StrikeEquipmentEvidence.item_ordinal",
        )
        _require_string(
            self.raw_text,
            "StrikeEquipmentEvidence.raw_text",
        )
        _require_string(
            self.candidate_text,
            "StrikeEquipmentEvidence.candidate_text",
        )


@dataclass(frozen=True, slots=True)
class StrikeDeferredDependency:
    kind: DeferredDependencyKind
    requirement_id: str
    source_span_address_sha256: str
    reason: str

    def __post_init__(self) -> None:
        if self.kind not in (
            "compound-damage",
            "effect",
            "equipment",
            "runtime",
        ):
            raise ValueError(
                "StrikeDeferredDependency.kind is invalid"
            )
        _require_string(
            self.requirement_id,
            "StrikeDeferredDependency.requirement_id",
        )
        _require_hash(
            self.source_span_address_sha256,
            "StrikeDeferredDependency.source_span_address_sha256",
        )
        _require_string(
            self.reason,
            "StrikeDeferredDependency.reason",
        )


@dataclass(frozen=True, slots=True)
class StrikeStructuralProjection:
    attack_bonus: int
    range_profile: StrikeRangeProfile
    damage: tuple[StrikeDamageProjection, ...]
    damage_complete: bool

    def __post_init__(self) -> None:
        if type(self.attack_bonus) is not int:
            raise TypeError(
                "StrikeStructuralProjection.attack_bonus must be an integer"
            )
        if not isinstance(self.range_profile, StrikeRangeProfile):
            raise TypeError(
                "StrikeStructuralProjection.range_profile must be a "
                "StrikeRangeProfile"
            )
        damage = _ordered_tuple(
            self.damage,
            "StrikeStructuralProjection.damage",
        )
        if any(
            not isinstance(item, StrikeDamageProjection)
            for item in damage
        ):
            raise TypeError(
                "StrikeStructuralProjection.damage must contain "
                "StrikeDamageProjection values"
            )
        if type(self.damage_complete) is not bool:
            raise TypeError(
                "StrikeStructuralProjection.damage_complete must be boolean"
            )
        object.__setattr__(self, "damage", damage)


@dataclass(frozen=True, slots=True)
class StrikeSource:
    address: StrikeSourceAddress
    raw_outer_member: RawSourceMember
    raw_object: RawSourceObject
    raw_outer_sha256: str
    raw_object_sha256: str
    mode: StrikeMode
    source_name: str
    label_key: str
    semantic_action_id: str
    attack_source_text: str
    members: tuple[StrikeMemberSource, ...]
    traits: tuple[StrikeTraitSource, ...]
    range_profile: StrikeRangeProfile
    carriers: tuple[StrikeCarrierSource, ...]
    equipment_evidence: tuple[StrikeEquipmentEvidence, ...]
    review_evidence: tuple[StrikeReviewEvidence, ...]
    projection: StrikeStructuralProjection
    deferred_dependencies: tuple[StrikeDeferredDependency, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.address, StrikeSourceAddress):
            raise TypeError(
                "StrikeSource.address must be a StrikeSourceAddress"
            )
        if not isinstance(self.raw_outer_member, RawSourceMember):
            raise TypeError(
                "StrikeSource.raw_outer_member must be a RawSourceMember"
            )
        if self.raw_outer_member.key != self.address.outer.raw_key:
            raise ValueError(
                "StrikeSource outer field changed source identity"
            )
        if not isinstance(self.raw_outer_member.value, RawSourceArray):
            raise TypeError(
                "StrikeSource raw outer member must contain an array"
            )
        if self.address.strike_ordinal >= len(
            self.raw_outer_member.value.items
        ):
            raise ValueError(
                "StrikeSource strike ordinal no longer resolves"
            )
        if not isinstance(self.raw_object, RawSourceObject):
            raise TypeError(
                "StrikeSource.raw_object must be a RawSourceObject"
            )
        if (
            self.raw_outer_member.value.items[
                self.address.strike_ordinal
            ]
            != self.raw_object
        ):
            raise ValueError(
                "StrikeSource raw object is not selected by its address"
            )
        if self.raw_outer_sha256 != raw_source_sha256(
            self.raw_outer_member.value
        ):
            raise ValueError("StrikeSource.raw_outer_sha256 is stale")
        if self.raw_object_sha256 != raw_source_sha256(self.raw_object):
            raise ValueError("StrikeSource.raw_object_sha256 is stale")
        if self.mode != self.address.outer.mode:
            raise ValueError("StrikeSource.mode changed outer field identity")
        _require_string(self.source_name, "StrikeSource.source_name")
        if self.raw_object.values("Name") != (self.source_name,):
            raise ValueError(
                "StrikeSource.source_name changed exact raw Name"
            )
        if self.label_key != strike_label_key(self.source_name):
            raise ValueError("StrikeSource.label_key is stale")
        if self.semantic_action_id != (
            f"strike:{self.label_key}:{self.mode}"
        ):
            raise ValueError(
                "StrikeSource.semantic_action_id must be mode-qualified"
            )
        if not isinstance(self.attack_source_text, str):
            raise TypeError(
                "StrikeSource.attack_source_text must be a string"
            )
        if self.raw_object.values("Attack") != (
            self.attack_source_text,
        ):
            raise ValueError(
                "StrikeSource.attack_source_text changed exact raw Attack"
            )
        for field_name, item_type in (
            ("members", StrikeMemberSource),
            ("traits", StrikeTraitSource),
            ("carriers", StrikeCarrierSource),
            ("equipment_evidence", StrikeEquipmentEvidence),
            ("review_evidence", StrikeReviewEvidence),
            ("deferred_dependencies", StrikeDeferredDependency),
        ):
            items = _ordered_tuple(
                getattr(self, field_name),
                f"StrikeSource.{field_name}",
            )
            if any(not isinstance(item, item_type) for item in items):
                raise TypeError(
                    f"StrikeSource.{field_name} contains the wrong type"
                )
            object.__setattr__(self, field_name, items)
        if not isinstance(self.range_profile, StrikeRangeProfile):
            raise TypeError(
                "StrikeSource.range_profile must be a StrikeRangeProfile"
            )
        if not isinstance(self.projection, StrikeStructuralProjection):
            raise TypeError(
                "StrikeSource.projection must be a "
                "StrikeStructuralProjection"
            )
        if self.members != _member_sources(
            self.address,
            self.raw_object,
        ):
            raise ValueError(
                "StrikeSource member projection is stale"
            )
        if self.traits != _trait_sources(
            self.address,
            self.raw_object,
        ):
            raise ValueError(
                "StrikeSource trait projection is stale"
            )
        if self.range_profile != _range_profile(
            self.mode,
            self.traits,
        ):
            raise ValueError(
                "StrikeSource range projection is stale"
            )
        if self.carriers != _carrier_sources(
            self.address,
            self.raw_object,
        ):
            raise ValueError(
                "StrikeSource carrier projection is stale"
            )
        attack_value = parse_decimal_integer(self.attack_source_text)
        if (
            attack_value is None
            or self.projection.attack_bonus != attack_value
            or self.projection.range_profile != self.range_profile
        ):
            raise ValueError(
                "StrikeSource structural projection is stale"
            )
        safe_damage_candidates = tuple(
            projection
            for carrier in self.carriers
            if (
                projection := carrier.safe_damage_projection
            )
            is not None
        )
        damage_complete = (
            len(self.carriers) == 1
            and self.carriers[0].raw_member.key == "Damage"
            and self.carriers[0].shape == "single-component"
            and len(safe_damage_candidates) == 1
            and not safe_damage_candidates[0].persistent
        )
        expected_damage = (
            safe_damage_candidates if damage_complete else ()
        )
        if (
            self.projection.damage != expected_damage
            or self.projection.damage_complete != damage_complete
        ):
            raise ValueError(
                "StrikeSource damage projection is stale"
            )
        if self.deferred_dependencies != _deferred_dependencies(
            self.address,
            self.members,
            self.traits,
            self.range_profile,
            self.carriers,
            self.equipment_evidence,
        ):
            raise ValueError(
                "StrikeSource deferred dependency projection is stale"
            )

    @property
    def carrier_pattern(self) -> tuple[str, ...]:
        return tuple(carrier.raw_member.key for carrier in self.carriers)

    @property
    def equipment_evidence_status(self) -> str:
        if not self.equipment_evidence:
            return "none"
        if len(self.equipment_evidence) == 1:
            return "one-source-inventory-candidate"
        return "ambiguous-source-inventory-candidates"

    @property
    def execution_ready(self) -> bool:
        """Structural recognition is never runtime authority."""

        return False


@dataclass(frozen=True, slots=True)
class StrikeIdentityCollision:
    label_key: str
    modes: tuple[StrikeMode, ...]
    semantic_action_ids: tuple[str, ...]
    source_address_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_string(
            self.label_key,
            "StrikeIdentityCollision.label_key",
        )
        modes = _ordered_tuple(
            self.modes,
            "StrikeIdentityCollision.modes",
        )
        if any(mode not in ("melee", "ranged") for mode in modes):
            raise ValueError(
                "StrikeIdentityCollision.modes contains an invalid mode"
            )
        action_ids = _ordered_tuple(
            self.semantic_action_ids,
            "StrikeIdentityCollision.semantic_action_ids",
        )
        addresses = _ordered_tuple(
            self.source_address_sha256,
            "StrikeIdentityCollision.source_address_sha256",
        )
        for digest in addresses:
            _require_hash(
                digest,
                "StrikeIdentityCollision source address",
            )
        object.__setattr__(self, "modes", modes)
        object.__setattr__(self, "semantic_action_ids", action_ids)
        object.__setattr__(self, "source_address_sha256", addresses)


@dataclass(frozen=True, slots=True)
class StrikeSourceBundle:
    block_source: StrikeBlockSource
    items_fields: tuple[StrikeItemsField, ...]
    strikes: tuple[StrikeSource, ...]
    same_mode_collisions: tuple[StrikeIdentityCollision, ...]
    cross_mode_collisions: tuple[StrikeIdentityCollision, ...]

    def __post_init__(self) -> None:
        if type(self) is not StrikeSourceBundle:
            raise TypeError("StrikeSourceBundle subclasses are not supported")
        if type(self.block_source) is not StrikeBlockSource:
            raise TypeError(
                "StrikeSourceBundle.block_source must be a "
                "StrikeBlockSource"
            )
        _validate_block_source(self.block_source)
        for field_name, item_type in (
            ("items_fields", StrikeItemsField),
            ("strikes", StrikeSource),
            ("same_mode_collisions", StrikeIdentityCollision),
            ("cross_mode_collisions", StrikeIdentityCollision),
        ):
            items = _ordered_tuple(
                getattr(self, field_name),
                f"StrikeSourceBundle.{field_name}",
            )
            if any(type(item) is not item_type for item in items):
                raise TypeError(
                    f"StrikeSourceBundle.{field_name} contains the wrong type"
                )
            object.__setattr__(self, field_name, items)
        raw_members = self.block_source.raw_block.members
        expected_items = []
        expected_strikes = []
        occurrences: Counter[str] = Counter()
        for member_ordinal, member in enumerate(raw_members):
            occurrence = occurrences[member.key]
            occurrences[member.key] += 1
            if (
                member.key.strip() in ("Melee", "Ranged")
                and member.key not in ("Melee", "Ranged")
            ):
                raise ValueError(
                    "StrikeSourceBundle block has a conflicting Strike key"
                )
            if member.key == "Items":
                expected_items.append((member_ordinal, occurrence))
            if member.key not in ("Melee", "Ranged"):
                continue
            if not isinstance(member.value, RawSourceArray):
                raise ValueError(
                    "StrikeSourceBundle outer Strike field is not an array"
                )
            expected_strikes.extend(
                (
                    member.key,
                    member_ordinal,
                    occurrence,
                    strike_ordinal,
                )
                for strike_ordinal in range(len(member.value.items))
            )
        observed_items = [
            (field.member_ordinal, field.occurrence)
            for field in self.items_fields
        ]
        if observed_items != expected_items:
            raise ValueError(
                "StrikeSourceBundle inventory index is incomplete"
            )
        observed_strikes = [
            (
                strike.address.outer.raw_key,
                strike.address.outer.member_ordinal,
                strike.address.outer.occurrence,
                strike.address.strike_ordinal,
            )
            for strike in self.strikes
        ]
        if observed_strikes != expected_strikes:
            raise ValueError(
                "StrikeSourceBundle Strike index is incomplete"
            )
        for field in self.items_fields:
            if (
                field.block_address != self.block_source.address
                or field.member_ordinal >= len(raw_members)
                or raw_members[field.member_ordinal] != field.raw_member
                or sum(
                    member.key == "Items"
                    for member in raw_members[: field.member_ordinal]
                )
                != field.occurrence
            ):
                raise ValueError(
                    "StrikeSourceBundle inventory source link is stale"
                )
        for strike in self.strikes:
            outer = strike.address.outer
            if (
                strike.address.block != self.block_source.address
                or outer.member_ordinal >= len(raw_members)
                or raw_members[outer.member_ordinal]
                != strike.raw_outer_member
                or sum(
                    member.key == outer.raw_key
                    for member in raw_members[: outer.member_ordinal]
                )
                != outer.occurrence
            ):
                raise ValueError(
                    "StrikeSourceBundle Strike source link is stale"
                )
        expected_same, expected_cross = _identity_collisions(
            self.strikes
        )
        if (
            self.same_mode_collisions != expected_same
            or self.cross_mode_collisions != expected_cross
        ):
            raise ValueError(
                "StrikeSourceBundle identity collision index is stale"
            )

    @property
    def identity_safe(self) -> bool:
        return not self.same_mode_collisions

    def __copy__(self) -> StrikeSourceBundle:
        raise TypeError("StrikeSourceBundle cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> StrikeSourceBundle:
        raise TypeError("StrikeSourceBundle cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("StrikeSourceBundle cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("StrikeSourceBundle cannot be pickled")


class StrikeIntegrationProjection:
    """One source-revalidated, compile-only Strike integration contract."""

    __slots__ = (
        "_bundle",
        "_payload",
        "projection_sha256",
        "__weakref__",
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "StrikeIntegrationProjection is issued only by "
            "project_strike_bundle()"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError(
            "StrikeIntegrationProjection subclasses are unsupported"
        )

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("StrikeIntegrationProjection is immutable")

    def __delattr__(self, _name: str) -> None:
        raise TypeError("StrikeIntegrationProjection is immutable")

    def __copy__(self) -> StrikeIntegrationProjection:
        raise TypeError("StrikeIntegrationProjection cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> StrikeIntegrationProjection:
        raise TypeError("StrikeIntegrationProjection cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("StrikeIntegrationProjection cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("StrikeIntegrationProjection cannot be pickled")


@dataclass(frozen=True, slots=True)
class StrikeCompilerPatch:
    source_address_sha256: str
    raw_value_sha256: str
    compiler_id: str
    projection: Mapping[str, Any]
    rider_ordinal: int | None = None
    rider_address_sha256: str | None = None
    raw_text_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self) is not StrikeCompilerPatch:
            raise TypeError("StrikeCompilerPatch subclasses are not supported")
        _require_hash(
            self.source_address_sha256,
            "StrikeCompilerPatch.source_address_sha256",
        )
        _require_hash(
            self.raw_value_sha256,
            "StrikeCompilerPatch.raw_value_sha256",
        )
        _require_string(
            self.compiler_id,
            "StrikeCompilerPatch.compiler_id",
        )
        if type(self.projection) not in (dict, MappingProxyType):
            raise TypeError(
                "StrikeCompilerPatch.projection must be an exact mapping"
            )
        object.__setattr__(
            self,
            "projection",
            _freeze_json(self.projection),
        )
        rider_fields = (
            self.rider_ordinal,
            self.rider_address_sha256,
            self.raw_text_sha256,
        )
        if any(value is not None for value in rider_fields):
            if any(value is None for value in rider_fields):
                raise ValueError(
                    "StrikeCompilerPatch rider link must provide ordinal, "
                    "address hash, and raw text hash together"
                )
            _require_ordinal(
                self.rider_ordinal,
                "StrikeCompilerPatch.rider_ordinal",
            )
            _require_hash(
                self.rider_address_sha256,
                "StrikeCompilerPatch.rider_address_sha256",
            )
            _require_hash(
                self.raw_text_sha256,
                "StrikeCompilerPatch.raw_text_sha256",
            )


@dataclass(frozen=True, slots=True)
class StrikeCompilerRegistration:
    """One immutable reviewed compiler claim.

    The registry is intentionally empty until the equipment, ammunition, and
    unarmed providers can issue source-authority receipts.
    """

    compiler_id: str
    source_address_sha256: str
    raw_value_sha256: str
    projection_sha256: str
    rider_ordinal: int | None = None
    rider_address_sha256: str | None = None
    raw_text_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self) is not StrikeCompilerRegistration:
            raise TypeError(
                "StrikeCompilerRegistration subclasses are not supported"
            )
        _require_string(
            self.compiler_id,
            "StrikeCompilerRegistration.compiler_id",
        )
        for field_name in (
            "source_address_sha256",
            "raw_value_sha256",
            "projection_sha256",
        ):
            _require_hash(
                getattr(self, field_name),
                f"StrikeCompilerRegistration.{field_name}",
            )
        rider_fields = (
            self.rider_ordinal,
            self.rider_address_sha256,
            self.raw_text_sha256,
        )
        if any(item is not None for item in rider_fields):
            if any(item is None for item in rider_fields):
                raise ValueError(
                    "Strike compiler registration rider fields are atomic"
                )
            _require_ordinal(
                self.rider_ordinal,
                "StrikeCompilerRegistration.rider_ordinal",
            )
            _require_hash(
                self.rider_address_sha256,
                "StrikeCompilerRegistration.rider_address_sha256",
            )
            _require_hash(
                self.raw_text_sha256,
                "StrikeCompilerRegistration.raw_text_sha256",
            )


@dataclass(frozen=True, slots=True, init=False)
class ResolvedStrikeCompilerPatch:
    patch: StrikeCompilerPatch
    registration: StrikeCompilerRegistration
    strike: StrikeSource
    carrier: StrikeCarrierSource
    rider: StrikeCarrierTerm | None
    _bundle: StrikeSourceBundle = field(repr=False, compare=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "ResolvedStrikeCompilerPatch is issued only by the reviewed "
            "Strike compiler resolver"
        )

    def __copy__(self) -> ResolvedStrikeCompilerPatch:
        raise TypeError("ResolvedStrikeCompilerPatch cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> ResolvedStrikeCompilerPatch:
        raise TypeError("ResolvedStrikeCompilerPatch cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("ResolvedStrikeCompilerPatch cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("ResolvedStrikeCompilerPatch cannot be pickled")


def _new_resolved_strike_compiler_patch(
    *,
    bundle: StrikeSourceBundle,
    patch: StrikeCompilerPatch,
    registration: StrikeCompilerRegistration,
    strike: StrikeSource,
    carrier: StrikeCarrierSource,
    rider: StrikeCarrierTerm | None,
) -> ResolvedStrikeCompilerPatch:
    result = object.__new__(ResolvedStrikeCompilerPatch)
    object.__setattr__(result, "patch", patch)
    object.__setattr__(result, "registration", registration)
    object.__setattr__(result, "strike", strike)
    object.__setattr__(result, "carrier", carrier)
    object.__setattr__(result, "rider", rider)
    object.__setattr__(result, "_bundle", bundle)
    return result


def _member_sources(
    address: StrikeSourceAddress,
    raw_object: RawSourceObject,
) -> tuple[StrikeMemberSource, ...]:
    occurrences: Counter[str] = Counter()
    result = []
    for member_ordinal, member in enumerate(raw_object.members):
        occurrence = occurrences[member.key]
        occurrences[member.key] += 1
        semantic_key = semantic_source_key(member.key)
        member_address = {
            **address.as_serialized(),
            "member": {
                "rawKey": member.key,
                "semanticKey": semantic_key,
                "occurrence": occurrence,
                "memberOrdinal": member_ordinal,
            },
        }
        result.append(
            StrikeMemberSource(
                source_address=address,
                raw_member=member,
                semantic_key=semantic_key,
                occurrence=occurrence,
                member_ordinal=member_ordinal,
                raw_value_sha256=raw_source_sha256(member.value),
                address_sha256=canonical_source_sha256(member_address),
            )
        )
    return tuple(result)


def _classify_trait(raw_text: str) -> tuple[str, Mapping[str, Any]]:
    text = normalized_source_text(raw_text)
    for category, pattern in _TRAIT_PATTERNS:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        parsed = {}
        for key, value in match.groupdict().items():
            if value is not None and value.isdigit():
                parsed_value = parse_decimal_integer(value)
                if parsed_value is None:
                    return "invalid-numeric-trait", {}
                parsed[key] = parsed_value
            else:
                parsed[key] = value
        return category, parsed
    return "other-required-trait", {}


def _trait_sources(
    address: StrikeSourceAddress,
    raw_object: RawSourceObject,
) -> tuple[StrikeTraitSource, ...]:
    occurrences: Counter[str] = Counter()
    result = []
    trait_ordinal = 0
    for member_ordinal, member in enumerate(raw_object.members):
        occurrence = occurrences[member.key]
        occurrences[member.key] += 1
        if member.key != "Traits":
            continue
        values = (
            member.value.items
            if isinstance(member.value, RawSourceArray)
            else (member.value,)
        )
        for raw_value in values:
            if isinstance(raw_value, str):
                raw_text = raw_value
                normalized = normalized_source_text(raw_text).casefold()
                category, parsed = _classify_trait(raw_text)
            else:
                raw_text = None
                normalized = None
                category = "invalid-non-string-trait"
                parsed = {}
            trait_address = {
                **address.as_serialized(),
                "trait": {"traitOrdinal": trait_ordinal},
            }
            result.append(
                StrikeTraitSource(
                    source_address=address,
                    member_ordinal=member_ordinal,
                    member_occurrence=occurrence,
                    trait_ordinal=trait_ordinal,
                    raw_value=raw_value,
                    raw_text=raw_text,
                    normalized_text=normalized,
                    category=category,
                    parsed=parsed,
                    raw_value_sha256=raw_source_sha256(raw_value),
                    address_sha256=canonical_source_sha256(
                        trait_address
                    ),
                )
            )
            trait_ordinal += 1
    return tuple(result)


def _range_profile(
    mode: StrikeMode,
    traits: Sequence[StrikeTraitSource],
) -> StrikeRangeProfile:
    by_category: dict[str, list[StrikeTraitSource]] = defaultdict(list)
    for trait in traits:
        by_category[trait.category].append(trait)

    allowed_geometry = (
        {
            "reach-distance",
            "reach-bare",
            # A thrown trait remains weapon/resource evidence on the melee
            # profile; it is not that profile's targeting geometry.
            "thrown-distance",
            "thrown-bare",
        }
        if mode == "melee"
        else {
            "range-increment",
            "range-maximum",
            "reload",
            "thrown-distance",
            "thrown-bare",
        }
    )
    incompatible = tuple(
        trait
        for trait in traits
        if trait.category in _GEOMETRY_TRAIT_CATEGORIES
        and trait.category not in allowed_geometry
    )
    if incompatible:
        descriptors = tuple(
            trait.address_sha256
            for trait in traits
            if trait.category in _GEOMETRY_TRAIT_CATEGORIES
        )
        return StrikeRangeProfile(
            mode=mode,
            geometry_kind="mode-incompatible-range-geometry",
            status="fail-closed",
            feet=None,
            reload_actions=None,
            reload_explicit=False,
            descriptor_address_sha256=descriptors,
        )

    if mode == "melee":
        reach = by_category["reach-distance"]
        bare = by_category["reach-bare"]
        if not reach and not bare:
            geometry = "default-reach"
            status = "structurally-recognized"
        elif len(reach) == 1 and not bare:
            geometry = "explicit-reach"
            status = "structurally-recognized"
        elif len(bare) == 1 and not reach:
            geometry = "bare-reach"
            status = "requires-rule-reconciliation"
        else:
            geometry = "ambiguous-reach"
            status = "fail-closed"
        feet = (
            int(reach[0].parsed["feet"])
            if len(reach) == 1 and not bare
            else None
        )
        return StrikeRangeProfile(
            mode=mode,
            geometry_kind=geometry,
            status=status,
            feet=feet,
            reload_actions=None,
            reload_explicit=False,
            descriptor_address_sha256=tuple(
                item.address_sha256 for item in (*reach, *bare)
            ),
        )

    increments = by_category["range-increment"]
    maximums = by_category["range-maximum"]
    reloads = by_category["reload"]
    thrown_distance = by_category["thrown-distance"]
    thrown_bare = by_category["thrown-bare"]
    descriptor_count = (
        len(increments)
        + len(maximums)
        + len(thrown_distance)
        + len(thrown_bare)
    )
    if (
        len(increments) == 1
        and not maximums
        and not thrown_distance
        and not thrown_bare
        and len(reloads) <= 1
    ):
        geometry = (
            "increment-explicit-reload"
            if reloads
            else "increment-source-unspecified-resource"
        )
        status = "structurally-recognized"
        feet = int(increments[0].parsed["feet"])
    elif (
        len(maximums) == 1
        and descriptor_count == 1
        and not reloads
    ):
        geometry = "absolute-maximum"
        status = "structurally-recognized"
        feet = int(maximums[0].parsed["feet"])
    elif (
        len(thrown_distance) == 1
        and descriptor_count == 1
        and not reloads
    ):
        geometry = "thrown-distance"
        status = "structurally-recognized"
        feet = int(thrown_distance[0].parsed["feet"])
    elif (
        len(increments) == 1
        and len(thrown_bare) == 1
        and descriptor_count == 2
        and not reloads
        and not maximums
        and not thrown_distance
    ):
        geometry = "increment-plus-bare-thrown"
        status = "requires-rule-reconciliation"
        feet = int(increments[0].parsed["feet"])
    elif descriptor_count == 0 and not reloads:
        geometry = "missing-range-geometry"
        status = "fail-closed"
        feet = None
    else:
        geometry = "ambiguous-range-geometry"
        status = "fail-closed"
        feet = None
    descriptors = (
        *increments,
        *maximums,
        *reloads,
        *thrown_distance,
        *thrown_bare,
    )
    return StrikeRangeProfile(
        mode=mode,
        geometry_kind=geometry,
        status=status,
        feet=feet,
        reload_actions=(
            int(reloads[0].parsed["actions"])
            if len(reloads) == 1
            else None
        ),
        reload_explicit=len(reloads) == 1,
        descriptor_address_sha256=tuple(
            item.address_sha256 for item in descriptors
        ),
    )


def _split_top_level_terms(text: str) -> list[dict[str, Any]]:
    result = []
    depth = 0
    start = 0
    connector_before: str | None = None
    index = 0
    while index < len(text):
        character = text[index]
        if character == "(":
            depth += 1
            index += 1
            continue
        if character == ")" and depth:
            depth -= 1
            index += 1
            continue
        matched = None
        if depth == 0:
            for connector in _TOP_LEVEL_CONNECTORS:
                if text.startswith(connector, index):
                    matched = connector
                    break
        if matched is None:
            index += 1
            continue
        result.append(
            {
                "term_ordinal": len(result),
                "connector_before": connector_before,
                "start": start,
                "end": index,
                "raw_text": text[start:index],
            }
        )
        connector_before = matched
        index += len(matched)
        start = index
    result.append(
        {
            "term_ordinal": len(result),
            "connector_before": connector_before,
            "start": start,
            "end": len(text),
            "raw_text": text[start:],
        }
    )
    return result


def _classify_carrier_term(raw_text: str, carrier_key: str) -> str:
    text = normalized_source_text(raw_text)
    text = re.sub(
        r"^(?:plus|and|or)\s+",
        "",
        text,
        flags=re.I,
    )
    if carrier_key != "Damage":
        return "named-effect-candidate"
    if re.match(r"^(?:see|varies\b)", text, re.I):
        return "delegated-damage-reference"
    if _DAMAGE_COMPONENT_RE.match(text):
        return "damage-component-candidate"
    if _ANY_AMOUNT_RE.match(text):
        return "damage-like-rider-candidate"
    return "named-effect-candidate"


def _damage_shape(
    raw_text: str | None,
    carrier_key: str,
    candidate_classes: Sequence[str],
) -> str:
    if carrier_key == "Effect":
        return "effect-only-singular"
    if carrier_key == "Effects":
        return "effect-only-plural"
    if raw_text is None:
        return "non-text-damage-carrier"
    text = normalized_source_text(raw_text)
    if re.match(r"^(?:see|varies\b)", text, re.I):
        return "delegated-damage-reference"
    damage_count = sum(
        item == "damage-component-candidate"
        for item in candidate_classes
    )
    rider_count = sum(
        item in (
            "named-effect-candidate",
            "damage-like-rider-candidate",
        )
        for item in candidate_classes
    )
    lowered = text.casefold()
    if not damage_count:
        return "non-damage-in-damage-carrier"
    if (
        "persistent damage" in lowered
        and "splash damage of the same type" in lowered
    ):
        return "type-choice-persistent-splash"
    if (
        "if the target is " in lowered
        or " to plants)" in lowered
        or " vs. " in lowered
    ):
        return "conditional-or-alternative-damage"
    if damage_count > 1 and rider_count:
        return "compound-damage-with-riders"
    if damage_count > 1:
        return "compound-damage"
    if rider_count:
        return "single-component-with-riders"
    return "single-component"


def _carrier_sources(
    address: StrikeSourceAddress,
    raw_object: RawSourceObject,
) -> tuple[StrikeCarrierSource, ...]:
    occurrences: Counter[str] = Counter()
    carrier_ordinal = 0
    result = []
    for member_ordinal, member in enumerate(raw_object.members):
        occurrence = occurrences[member.key]
        occurrences[member.key] += 1
        if member.key not in _CARRIER_KEYS:
            continue
        carrier_address_value = {
            **address.as_serialized(),
            "carrier": {
                "rawKey": member.key,
                "occurrence": occurrence,
                "memberOrdinal": member_ordinal,
                "carrierOrdinal": carrier_ordinal,
            },
        }
        carrier_address = canonical_source_sha256(
            carrier_address_value
        )
        raw_text = (
            member.value
            if isinstance(member.value, str)
            else None
        )
        raw_terms = (
            _split_top_level_terms(raw_text)
            if raw_text is not None
            else []
        )
        candidate_classes = [
            _classify_carrier_term(
                term["raw_text"],
                member.key,
            )
            for term in raw_terms
        ]
        terms = []
        rider_ordinal = 0
        for term, candidate_class in zip(
            raw_terms,
            candidate_classes,
            strict=True,
        ):
            is_rider = candidate_class in (
                "named-effect-candidate",
                "damage-like-rider-candidate",
            )
            current_rider_ordinal = rider_ordinal if is_rider else None
            rider_address = None
            if current_rider_ordinal is not None:
                rider_address = canonical_source_sha256(
                    {
                        **carrier_address_value,
                        "rider": {
                            "riderOrdinal": current_rider_ordinal,
                            "termOrdinal": term["term_ordinal"],
                        },
                    }
                )
                rider_ordinal += 1
            raw_term_text = term["raw_text"]
            terms.append(
                StrikeCarrierTerm(
                    carrier_address_sha256=carrier_address,
                    term_ordinal=term["term_ordinal"],
                    connector_before=term["connector_before"],
                    start=term["start"],
                    end=term["end"],
                    raw_text=raw_term_text,
                    raw_text_sha256=raw_source_sha256(raw_term_text),
                    candidate_class=candidate_class,
                    tail_ordinal=(
                        term["term_ordinal"] - 1
                        if term["term_ordinal"] > 0
                        else None
                    ),
                    rider_ordinal=current_rider_ordinal,
                    rider_address_sha256=rider_address,
                )
            )
        components = []
        if raw_text is not None:
            for component_ordinal, match in enumerate(
                _DAMAGE_COMPONENT_SCAN_RE.finditer(raw_text)
            ):
                components.append(
                    StrikeDamageComponentCandidate(
                        component_ordinal=component_ordinal,
                        source_text=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        damage_type=match.group("type").casefold(),
                        persistent=bool(match.group("persistent")),
                    )
                )
        type_candidates = [
            component.damage_type for component in components
        ]
        if raw_text is not None:
            choice = _TYPE_CHOICE_SCAN_RE.search(raw_text)
            if choice is not None:
                type_candidates.extend(
                    (
                        choice.group("second").casefold(),
                        choice.group("third").casefold(),
                    )
                )
        unique_types = tuple(dict.fromkeys(type_candidates))
        result.append(
            StrikeCarrierSource(
                source_address=address,
                raw_member=member,
                occurrence=occurrence,
                member_ordinal=member_ordinal,
                carrier_ordinal=carrier_ordinal,
                raw_value_sha256=raw_source_sha256(member.value),
                address_sha256=carrier_address,
                raw_text=raw_text,
                shape=_damage_shape(
                    raw_text,
                    member.key,
                    candidate_classes,
                ),
                terms=tuple(terms),
                component_candidates=tuple(components),
                damage_type_candidates=unique_types,
            )
        )
        carrier_ordinal += 1
    return tuple(result)


def _item_candidates(raw_text: str) -> tuple[StrikeItemCandidate, ...]:
    text = normalized_source_text(
        re.sub(r"</?i>", "", raw_text, flags=re.I)
    )
    candidates = [("exact", text)]
    counted = re.fullmatch(r"(?P<base>.+?) \((?P<count>\d+)\)", text)
    if counted:
        candidates.append(("count-qualified", counted.group("base")))
    bundle = re.fullmatch(
        r"(?P<base>.+?) \(\d+ (?:arrows|bolts|bullets)\)",
        text,
        re.I,
    )
    if bundle:
        candidates.append(("launcher-bundle", bundle.group("base")))
    potency = re.fullmatch(r"\+\d+ (?P<base>.+)", text)
    if potency:
        candidates.append(("potency-qualified", potency.group("base")))
    if text.casefold().startswith("keen returning "):
        candidates.append(
            (
                "named-rune-qualified",
                text[len("keen returning ") :],
            )
        )
    result = []
    seen = set()
    for kind, candidate_text in candidates:
        key = strike_label_key(candidate_text)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(
            StrikeItemCandidate(
                kind=kind,
                text=candidate_text,
                label_key=key,
            )
        )
    return tuple(result)


def _compile_items_member(
    block_address: StrikeBlockAddress,
    raw_member: RawSourceMember,
    *,
    occurrence: int,
    member_ordinal: int,
) -> StrikeItemsField:
    """Compile one exact source inventory field without inferring equipment."""

    if not isinstance(raw_member, RawSourceMember):
        raise TypeError(
            "_compile_items_member raw_member must be a RawSourceMember"
        )
    if raw_member.key != "Items":
        raise StrikeSourceError(
            "_compile_items_member requires an exact Items member"
        )
    _require_ordinal(occurrence, "Items occurrence")
    _require_ordinal(member_ordinal, "Items member ordinal")
    field_address_value = {
        **block_address.as_serialized(),
        "itemsField": {
            "rawKey": "Items",
            "occurrence": occurrence,
            "memberOrdinal": member_ordinal,
        },
    }
    field_address = canonical_source_sha256(field_address_value)
    values = (
        raw_member.value.items
        if isinstance(raw_member.value, RawSourceArray)
        else (raw_member.value,)
    )
    if len(values) > _MAX_BLOCK_MEMBERS:
        raise StrikeSourceError(
            "Items field exceeds its exact token bound"
        )
    tokens = []
    for item_ordinal, raw_value in enumerate(values):
        token_address = canonical_source_sha256(
            {
                **field_address_value,
                "item": {"itemOrdinal": item_ordinal},
            }
        )
        raw_text = raw_value if isinstance(raw_value, str) else None
        tokens.append(
            StrikeItemToken(
                item_ordinal=item_ordinal,
                raw_value=raw_value,
                raw_text=raw_text,
                raw_value_sha256=raw_source_sha256(raw_value),
                address_sha256=token_address,
                base_candidates=(
                    _item_candidates(raw_text)
                    if raw_text is not None
                    else ()
                ),
            )
        )
    return StrikeItemsField(
        block_address=block_address,
        raw_member=raw_member,
        occurrence=occurrence,
        member_ordinal=member_ordinal,
        raw_value_sha256=raw_source_sha256(raw_member.value),
        address_sha256=field_address,
        tokens=tuple(tokens),
    )


def _compile_items_from_block_source(
    block_source: StrikeBlockSource,
    member_ordinal: int,
    /,
) -> StrikeItemsField:
    """Compile one Items member selected from a hash-verified raw block."""

    if type(block_source) is not StrikeBlockSource:
        raise TypeError(
            "_compile_items_from_block_source requires a StrikeBlockSource"
        )
    _validate_block_source(block_source)
    _require_ordinal(member_ordinal, "Items member ordinal")
    members = block_source.raw_block.members
    if member_ordinal >= len(members):
        raise StrikeSourceError(
            "Items member ordinal does not resolve in the verified block"
        )
    member = members[member_ordinal]
    if member.key != "Items":
        raise StrikeSourceError(
            "selected verified block member is not exact Items"
        )
    occurrence = sum(
        candidate.key == "Items"
        for candidate in members[:member_ordinal]
    )
    return _compile_items_member(
        block_source.address,
        member,
        occurrence=occurrence,
        member_ordinal=member_ordinal,
    )


def _equipment_evidence(
    label_key: str,
    items_fields: Sequence[StrikeItemsField],
) -> tuple[StrikeEquipmentEvidence, ...]:
    result = []
    for field in items_fields:
        for token in field.tokens:
            for candidate in token.base_candidates:
                if candidate.label_key != label_key:
                    continue
                if token.raw_text is None:
                    continue
                result.append(
                    StrikeEquipmentEvidence(
                        evidence_kind=candidate.kind,
                        items_field_address_sha256=field.address_sha256,
                        item_address_sha256=token.address_sha256,
                        item_ordinal=token.item_ordinal,
                        raw_text=token.raw_text,
                        candidate_text=candidate.text,
                    )
                )
    return tuple(result)


def _dependency(
    kind: DeferredDependencyKind,
    requirement_id: str,
    source_span_address_sha256: str,
    reason: str,
) -> StrikeDeferredDependency:
    return StrikeDeferredDependency(
        kind=kind,
        requirement_id=requirement_id,
        source_span_address_sha256=source_span_address_sha256,
        reason=reason,
    )


def _deferred_dependencies(
    address: StrikeSourceAddress,
    members: Sequence[StrikeMemberSource],
    traits: Sequence[StrikeTraitSource],
    range_profile: StrikeRangeProfile,
    carriers: Sequence[StrikeCarrierSource],
    evidence: Sequence[StrikeEquipmentEvidence],
) -> tuple[StrikeDeferredDependency, ...]:
    result = [
        _dependency(
            "runtime",
            "strike-resolution-runtime",
            address.address_sha256,
            "compile/link-only foundation has no encounter transition",
        )
    ]
    if range_profile.status != "structurally-recognized":
        result.append(
            _dependency(
                "runtime",
                f"range-geometry:{range_profile.geometry_kind}",
                address.address_sha256,
                "source geometry requires rules reconciliation",
            )
        )
    if address.outer.mode == "ranged":
        result.append(
            _dependency(
                "runtime",
                "exclusive-ranged-resource-policy",
                address.address_sha256,
                "range and reload syntax do not prove ammunition or item use",
            )
        )
    if range_profile.geometry_kind in (
        "thrown-distance",
        "increment-plus-bare-thrown",
    ):
        result.append(
            _dependency(
                "equipment",
                "canonical-thrown-item-link",
                address.address_sha256,
                "thrown syntax does not prove a canonical carried item",
            )
        )
    for member in members:
        if member.raw_member.key not in _KNOWN_STRIKE_KEYS:
            result.append(
                _dependency(
                    "runtime",
                    f"unconsumed-strike-member:{member.semantic_key}",
                    member.address_sha256,
                    "unknown Strike member remains unconsumed",
                )
            )
    consumed_geometry_addresses = set(
        range_profile.descriptor_address_sha256
    )
    for trait in traits:
        if trait.category in _GEOMETRY_TRAIT_CATEGORIES:
            if trait.address_sha256 in consumed_geometry_addresses:
                continue
            result.append(
                _dependency(
                    "runtime",
                    (
                        "mode-incompatible-or-unconsumed-geometry:"
                        f"{trait.category}"
                    ),
                    trait.address_sha256,
                    "geometry trait was not consumed by this Strike mode",
                )
            )
            continue
        result.append(
            _dependency(
                "runtime",
                f"strike-trait:{trait.category}",
                trait.address_sha256,
                "trait behavior is not part of the source foundation",
            )
        )
    for carrier in carriers:
        shape = carrier.shape
        if carrier.raw_member.key in ("Effect", "Effects"):
            result.append(
                _dependency(
                    "effect",
                    f"strike-carrier:{carrier.raw_member.key.casefold()}",
                    carrier.address_sha256,
                    "named Strike effect requires a family compiler",
                )
            )
        elif shape in (
            "compound-damage",
            "compound-damage-with-riders",
            "conditional-or-alternative-damage",
            "type-choice-persistent-splash",
        ):
            result.append(
                _dependency(
                    "compound-damage",
                    f"strike-damage-shape:{shape}",
                    carrier.address_sha256,
                    "compound damage requires a reviewed damage compiler",
                )
            )
        elif shape in (
            "single-component-with-riders",
            "non-damage-in-damage-carrier",
        ):
            result.append(
                _dependency(
                    "effect",
                    f"strike-damage-shape:{shape}",
                    carrier.address_sha256,
                    "rider/effect source text requires a family compiler",
                )
            )
        elif shape in (
            "delegated-damage-reference",
            "non-text-damage-carrier",
        ):
            result.append(
                _dependency(
                    "runtime",
                    f"strike-damage-shape:{shape}",
                    carrier.address_sha256,
                    "damage source cannot be projected locally",
                )
            )
        elif carrier.safe_damage_projection is None:
            result.append(
                _dependency(
                    "runtime",
                    f"strike-damage-shape:{shape}",
                    carrier.address_sha256,
                    "damage text is not one safe reviewed projection",
                )
            )
        projection = carrier.safe_damage_projection
        if projection is not None and projection.persistent:
            result.append(
                _dependency(
                    "runtime",
                    "persistent-damage-runtime",
                    carrier.address_sha256,
                    "persistent damage requires its dedicated runtime",
                )
            )
    damage_carriers = [
        carrier
        for carrier in carriers
        if carrier.raw_member.key == "Damage"
    ]
    if len(damage_carriers) > 1:
        result.append(
            _dependency(
                "compound-damage",
                "multiple-damage-carriers",
                address.address_sha256,
                "multiple Damage members require an explicit composition",
            )
        )
    for item in evidence:
        result.append(
            _dependency(
                "equipment",
                "canonical-strike-item-link",
                item.item_address_sha256,
                "inventory label evidence is not a canonical item binding",
            )
        )
    if not carriers:
        result.append(
            _dependency(
                "effect",
                "missing-strike-carrier",
                address.address_sha256,
                "Strike has no Damage, Effect, or Effects carrier",
            )
        )
    unique = {}
    for item in result:
        key = (
            item.kind,
            item.requirement_id,
            item.source_span_address_sha256,
            item.reason,
        )
        unique.setdefault(key, item)
    return tuple(unique.values())


def _compile_strike_source(
    address: StrikeSourceAddress,
    raw_outer_member: RawSourceMember,
    *,
    items_fields: Sequence[StrikeItemsField] = (),
    review_evidence: Sequence[StrikeReviewEvidence] = (),
) -> StrikeSource:
    """Compile one exact Strike while retaining its complete source shape."""

    if not isinstance(address, StrikeSourceAddress):
        raise TypeError(
            "_compile_strike_source address must be a StrikeSourceAddress"
        )
    if not isinstance(raw_outer_member, RawSourceMember):
        raise TypeError(
            "_compile_strike_source raw_outer_member must be a "
            "RawSourceMember"
        )
    if raw_outer_member.key != address.outer.raw_key:
        raise StrikeSourceError(
            "Strike outer field does not match its source address"
        )
    if not isinstance(raw_outer_member.value, RawSourceArray):
        raise StrikeSourceError(
            "Strike outer field must contain a raw array"
        )
    if address.strike_ordinal >= len(raw_outer_member.value.items):
        raise StrikeSourceError(
            "Strike ordinal does not resolve in the outer array"
        )
    raw_object = raw_outer_member.value.items[address.strike_ordinal]
    if not isinstance(raw_object, RawSourceObject):
        raise StrikeSourceError(
            "Strike array member must be a raw ordered object"
        )
    if (
        not raw_object.members
        or len(raw_object.members) > _MAX_BLOCK_MEMBERS
    ):
        raise StrikeSourceError(
            "Strike object exceeds its exact member bound"
        )
    fields = _ordered_tuple(items_fields, "items_fields")
    if any(not isinstance(item, StrikeItemsField) for item in fields):
        raise TypeError(
            "items_fields must contain StrikeItemsField values"
        )
    if any(item.block_address != address.block for item in fields):
        raise StrikeSourceError(
            "inventory evidence belongs to a different source block"
        )
    reviews = _ordered_tuple(review_evidence, "review_evidence")
    if any(
        not isinstance(item, StrikeReviewEvidence)
        for item in reviews
    ):
        raise TypeError(
            "review_evidence must contain StrikeReviewEvidence values"
        )

    for semantic_key in ("Name", "Attack"):
        conflicts = [
            member.key
            for member in raw_object.members
            if member.key.strip() == semantic_key
            and member.key != semantic_key
        ]
        values = raw_object.values(semantic_key)
        if conflicts or len(values) != 1 or not isinstance(values[0], str):
            raise StrikeSourceError(
                f"Strike {semantic_key} must be one exact string member"
            )
    for key in ("Traits", "Damage", "Effect", "Effects"):
        if any(
            member.key.strip() == key and member.key != key
            for member in raw_object.members
        ):
            raise StrikeSourceError(
                f"Strike {key} has a whitespace-conflicting source key"
            )

    source_name = raw_object.values("Name")[0]
    _require_string(source_name, "Strike Name")
    label_key = strike_label_key(source_name)
    if not label_key:
        raise StrikeSourceError(
            "Strike Name does not produce a semantic label"
        )
    attack_source_text = raw_object.values("Attack")[0]
    _require_string(attack_source_text, "Strike Attack")
    attack_match = _ATTACK_RE.fullmatch(attack_source_text)
    if attack_match is None:
        raise StrikeSourceError(
            "Strike Attack is not one exact signed integer"
        )
    attack_bonus = parse_decimal_integer(attack_source_text)
    if attack_bonus is None:
        raise StrikeSourceError(
            "Strike Attack exceeds the bounded source integer contract"
        )

    members = _member_sources(address, raw_object)
    traits = _trait_sources(address, raw_object)
    range_profile = _range_profile(address.outer.mode, traits)
    carriers = _carrier_sources(address, raw_object)
    equipment = _equipment_evidence(label_key, fields)
    safe_damage_candidates = tuple(
        projection
        for carrier in carriers
        if (projection := carrier.safe_damage_projection) is not None
    )
    damage_complete = (
        len(carriers) == 1
        and carriers[0].raw_member.key == "Damage"
        and carriers[0].shape == "single-component"
        and len(safe_damage_candidates) == 1
        and not safe_damage_candidates[0].persistent
    )
    safe_damage = safe_damage_candidates if damage_complete else ()
    deferred = _deferred_dependencies(
        address,
        members,
        traits,
        range_profile,
        carriers,
        equipment,
    )
    return StrikeSource(
        address=address,
        raw_outer_member=raw_outer_member,
        raw_object=raw_object,
        raw_outer_sha256=raw_source_sha256(raw_outer_member.value),
        raw_object_sha256=raw_source_sha256(raw_object),
        mode=address.outer.mode,
        source_name=source_name,
        label_key=label_key,
        semantic_action_id=(
            f"strike:{label_key}:{address.outer.mode}"
        ),
        attack_source_text=attack_source_text,
        members=members,
        traits=traits,
        range_profile=range_profile,
        carriers=carriers,
        equipment_evidence=equipment,
        review_evidence=reviews,
        projection=StrikeStructuralProjection(
            attack_bonus=attack_bonus,
            range_profile=range_profile,
            damage=safe_damage,
            damage_complete=damage_complete,
        ),
        deferred_dependencies=deferred,
    )


def _compile_strike_from_block_source(
    block_source: StrikeBlockSource,
    address: StrikeSourceAddress,
    /,
    *,
    review_evidence: Sequence[StrikeReviewEvidence] = (),
) -> StrikeSource:
    """Compile one Strike selected from a hash-verified raw creature block."""

    if type(block_source) is not StrikeBlockSource:
        raise TypeError(
            "_compile_strike_from_block_source requires a StrikeBlockSource"
        )
    _validate_block_source(block_source)
    if type(address) is not StrikeSourceAddress:
        raise TypeError(
            "compile_strike_source address must be a StrikeSourceAddress"
        )
    if address.block != block_source.address:
        raise StrikeSourceError(
            "Strike address belongs to a different verified block"
        )
    members = block_source.raw_block.members
    outer = address.outer
    if outer.member_ordinal >= len(members):
        raise StrikeSourceError(
            "Strike outer member ordinal does not resolve in verified block"
        )
    raw_outer_member = members[outer.member_ordinal]
    if raw_outer_member.key != outer.raw_key:
        raise StrikeSourceError(
            "Strike outer field does not resolve at its verified ordinal"
        )
    occurrence = sum(
        member.key == outer.raw_key
        for member in members[: outer.member_ordinal]
    )
    if occurrence != outer.occurrence:
        raise StrikeSourceError(
            "Strike outer field occurrence is stale"
        )
    items_fields = tuple(
        _compile_items_from_block_source(block_source, member_ordinal)
        for member_ordinal, member in enumerate(members)
        if member.key == "Items"
    )
    return _compile_strike_source(
        address,
        raw_outer_member,
        items_fields=items_fields,
        review_evidence=review_evidence,
    )


def _identity_collisions(
    strikes: Sequence[StrikeSource],
) -> tuple[
    tuple[StrikeIdentityCollision, ...],
    tuple[StrikeIdentityCollision, ...],
]:
    by_action: dict[str, list[StrikeSource]] = defaultdict(list)
    by_label: dict[str, list[StrikeSource]] = defaultdict(list)
    for strike in strikes:
        by_action[strike.semantic_action_id].append(strike)
        by_label[strike.label_key].append(strike)

    same_mode = []
    for action_id, profiles in by_action.items():
        if len(profiles) < 2:
            continue
        same_mode.append(
            StrikeIdentityCollision(
                label_key=profiles[0].label_key,
                modes=tuple(profile.mode for profile in profiles),
                semantic_action_ids=tuple(
                    profile.semantic_action_id for profile in profiles
                ),
                source_address_sha256=tuple(
                    profile.address.address_sha256
                    for profile in profiles
                ),
            )
        )
    cross_mode = []
    for label_key, profiles in by_label.items():
        modes = tuple(dict.fromkeys(profile.mode for profile in profiles))
        if set(modes) != {"melee", "ranged"}:
            continue
        ordered = sorted(
            profiles,
            key=lambda item: (
                0 if item.mode == "melee" else 1,
                item.address.outer.member_ordinal,
                item.address.strike_ordinal,
            ),
        )
        cross_mode.append(
            StrikeIdentityCollision(
                label_key=label_key,
                modes=tuple(
                    dict.fromkeys(item.mode for item in ordered)
                ),
                semantic_action_ids=tuple(
                    item.semantic_action_id for item in ordered
                ),
                source_address_sha256=tuple(
                    item.address.address_sha256 for item in ordered
                ),
            )
        )
    return tuple(same_mode), tuple(cross_mode)


def _compile_block_source(
    block_source: StrikeBlockSource,
    *,
    review_evidence_by_address: Mapping[
        str,
        Sequence[StrikeReviewEvidence],
    ]
    | None = None,
) -> StrikeSourceBundle:
    """Compile every exact Melee/Ranged member in one verified raw block."""

    if type(block_source) is not StrikeBlockSource:
        raise TypeError(
            "_compile_block_source requires a StrikeBlockSource"
        )
    _validate_block_source(block_source)
    review_index = review_evidence_by_address or {}
    if not isinstance(review_index, Mapping):
        raise TypeError(
            "review_evidence_by_address must be a mapping or None"
        )

    occurrences: Counter[str] = Counter()
    items_fields = []
    outer_members = []
    for member_ordinal, member in enumerate(
        block_source.raw_block.members
    ):
        occurrence = occurrences[member.key]
        occurrences[member.key] += 1
        if member.key.strip() in ("Melee", "Ranged") and (
            member.key not in ("Melee", "Ranged")
        ):
            raise StrikeSourceError(
                "creature block has a whitespace-conflicting Strike field"
            )
        if member.key == "Items":
            items_fields.append(
                _compile_items_member(
                    block_source.address,
                    member,
                    occurrence=occurrence,
                    member_ordinal=member_ordinal,
                )
            )
        if member.key in ("Melee", "Ranged"):
            if (
                type(member.value) is RawSourceArray
                and len(member.value.items) > _MAX_STRIKES_PER_BLOCK
            ):
                raise StrikeSourceError(
                    "creature Strike array exceeds its exact count bound"
                )
            outer_members.append(
                (member_ordinal, occurrence, member)
            )

    strikes = []
    used_review_addresses = set()
    for member_ordinal, occurrence, member in outer_members:
        if not isinstance(member.value, RawSourceArray):
            raise StrikeSourceError(
                "creature Melee/Ranged field must be an array"
            )
        outer = StrikeOuterAddress(
            raw_key=member.key,
            occurrence=occurrence,
            member_ordinal=member_ordinal,
        )
        for strike_ordinal in range(len(member.value.items)):
            if len(strikes) >= _MAX_STRIKES_PER_BLOCK:
                raise StrikeSourceError(
                    "creature block exceeds its total Strike count bound"
                )
            address = StrikeSourceAddress(
                block=block_source.address,
                outer=outer,
                strike_ordinal=strike_ordinal,
            )
            reviews = review_index.get(address.address_sha256, ())
            if address.address_sha256 in review_index:
                used_review_addresses.add(address.address_sha256)
            strikes.append(
                _compile_strike_source(
                    address,
                    member,
                    items_fields=items_fields,
                    review_evidence=reviews,
                )
            )
    stale_reviews = set(review_index).difference(used_review_addresses)
    if stale_reviews:
        raise StrikeSourceError(
            "review evidence contains stale Strike source addresses"
        )
    same_mode, cross_mode = _identity_collisions(strikes)
    return StrikeSourceBundle(
        block_source=block_source,
        items_fields=tuple(items_fields),
        strikes=tuple(strikes),
        same_mode_collisions=same_mode,
        cross_mode_collisions=cross_mode,
    )


def _resolve_registered_strike_compiler_patch(
    bundle: StrikeSourceBundle,
    patch: StrikeCompilerPatch,
    registration: StrikeCompilerRegistration,
    /,
) -> ResolvedStrikeCompilerPatch:
    """Resolve one already-reviewed immutable registration."""

    _validate_bundle(bundle)
    if type(patch) is not StrikeCompilerPatch:
        raise TypeError(
            "Strike compiler patch must be exact"
        )
    if type(registration) is not StrikeCompilerRegistration:
        raise TypeError("Strike compiler registration must be exact")
    actual_registration = (
        patch.compiler_id,
        patch.source_address_sha256,
        patch.raw_value_sha256,
        canonical_source_sha256(patch.projection),
        patch.rider_ordinal,
        patch.rider_address_sha256,
        patch.raw_text_sha256,
    )
    reviewed_registration = (
        registration.compiler_id,
        registration.source_address_sha256,
        registration.raw_value_sha256,
        registration.projection_sha256,
        registration.rider_ordinal,
        registration.rider_address_sha256,
        registration.raw_text_sha256,
    )
    if actual_registration != reviewed_registration:
        raise StrikeCompilerLinkError(
            "compiler patch is not the exact reviewed registration"
        )
    matches = []
    for strike in bundle.strikes:
        for carrier in strike.carriers:
            if carrier.address_sha256 == patch.source_address_sha256:
                matches.append((strike, carrier))
    if len(matches) != 1:
        raise StrikeCompilerLinkError(
            "compiler link source address does not resolve exactly once"
        )
    strike, carrier = matches[0]
    if patch.raw_value_sha256 != carrier.raw_value_sha256:
        raise StrikeCompilerLinkError(
            "compiler link raw value hash is stale"
        )
    if patch.rider_ordinal is None:
        return _new_resolved_strike_compiler_patch(
            bundle=bundle,
            patch=patch,
            registration=registration,
            strike=strike,
            carrier=carrier,
            rider=None,
        )
    riders = [
        term
        for term in carrier.terms
        if term.rider_ordinal == patch.rider_ordinal
    ]
    if len(riders) != 1:
        raise StrikeCompilerLinkError(
            "compiler link rider ordinal does not resolve exactly once"
        )
    rider = riders[0]
    if patch.rider_address_sha256 != rider.rider_address_sha256:
        raise StrikeCompilerLinkError(
            "compiler link rider address is stale"
        )
    if patch.raw_text_sha256 != rider.raw_text_sha256:
        raise StrikeCompilerLinkError(
            "compiler link rider text hash is stale"
        )
    return _new_resolved_strike_compiler_patch(
        bundle=bundle,
        patch=patch,
        registration=registration,
        strike=strike,
        carrier=carrier,
        rider=rider,
    )


def _validate_bundle(value: object) -> StrikeSourceBundle:
    """Re-derive a public artifact from the retained authenticated block."""

    if type(value) is not StrikeSourceBundle:
        raise TypeError("Strike source bundle must be exact")
    block_source = _validate_block_source(value.block_source)
    canonical_block_source = _new_block_source(
        block_source._authority,
        block_source._consumer,
    )
    expected = _compile_block_source(canonical_block_source)
    if not _exact_rederived_match(value, expected):
        raise StrikeSourceError(
            "Strike source bundle disagrees with authenticated source"
        )
    return expected


def _exact_rederived_match(observed: object, expected: object) -> bool:
    """Compare an artifact without invoking attacker-controlled equality."""

    active: set[tuple[int, int]] = set()
    nodes = 0

    def visit(left: object, right: object, depth: int) -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            return False
        if left is right:
            return True
        right_type = type(right)
        if type(left) is not right_type:
            return False
        if right is None:
            return True
        if right_type in (bool, int, str):
            return left == right
        if right_type is float:
            return left.hex() == right.hex()

        pair = (id(left), id(right))
        if pair in active:
            return False
        active.add(pair)
        try:
            if right_type is tuple:
                if len(left) != len(right):
                    return False
                return all(
                    visit(left_item, right_item, depth + 1)
                    for left_item, right_item in zip(
                        left,
                        right,
                        strict=True,
                    )
                )
            if right_type is MappingProxyType:
                left_keys = tuple(left.keys())
                right_keys = tuple(right.keys())
                if (
                    any(type(key) is not str for key in left_keys)
                    or left_keys != right_keys
                ):
                    return False
                return all(
                    visit(left[key], right[key], depth + 1)
                    for key in right_keys
                )
            if hasattr(right_type, "__dataclass_fields__"):
                return all(
                    visit(
                        object.__getattribute__(left, item.name),
                        object.__getattribute__(right, item.name),
                        depth + 1,
                    )
                    for item in dataclass_fields(right_type)
                )
            return False
        except (AttributeError, KeyError, TypeError, ValueError):
            return False
        finally:
            active.remove(pair)

    return visit(observed, expected, 0)


def _projected_occurrence_id(strike: StrikeSource) -> str:
    outer = strike.address.outer
    return (
        f"{strike.address.block.block_id}#"
        f"{strike.semantic_action_id}:"
        f"{outer.member_ordinal:03d}:"
        f"{strike.address.strike_ordinal:03d}"
    )


def _damage_projection_payload(
    projection: StrikeDamageProjection,
    carrier: StrikeCarrierSource,
    component: StrikeDamageComponentCandidate,
) -> dict[str, Any]:
    return {
        "carrierAddressSha256": carrier.address_sha256,
        "componentOrdinal": component.component_ordinal,
        "sourceText": projection.source_text,
        "sourceSpan": {
            "start": component.start,
            "end": component.end,
        },
        "dice": (
            None
            if projection.dice_count is None
            else {
                "count": projection.dice_count,
                "sides": projection.die_size,
            }
        ),
        "flatAmount": projection.flat_amount,
        "modifier": projection.modifier,
        "damageType": projection.damage_type,
        "persistent": projection.persistent,
    }


def _integration_requirement(
    kind: str,
    requirement_id: str,
    source_address_sha256: str,
    reason: str,
) -> dict[str, Any]:
    _require_string(kind, "Strike integration requirement kind")
    _require_string(
        requirement_id,
        "Strike integration requirement id",
    )
    _require_hash(
        source_address_sha256,
        "Strike integration requirement source address",
    )
    _require_string(reason, "Strike integration requirement reason")
    return {
        "kind": kind,
        "requirementId": requirement_id,
        "sourceAddressSha256": source_address_sha256,
        "reason": reason,
    }


def _integration_targeting(
    strike: StrikeSource,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    profile = strike.range_profile
    deferrals: list[dict[str, Any]] = []
    if strike.mode == "melee":
        if profile.geometry_kind == "default-reach":
            targeting = {
                "status": "mechanically-complete",
                "kind": "creature-default-reach",
                "reachFeet": None,
                "requiresCreatureReachProjection": True,
            }
        elif profile.geometry_kind == "explicit-reach":
            targeting = {
                "status": "mechanically-complete",
                "kind": "explicit-reach",
                "reachFeet": profile.feet,
                "requiresCreatureReachProjection": False,
            }
        else:
            targeting = {
                "status": "deferred",
                "kind": profile.geometry_kind,
                "reachFeet": profile.feet,
                "requiresCreatureReachProjection": True,
            }
            deferrals.append(
                _integration_requirement(
                    "targeting",
                    f"melee-range:{profile.geometry_kind}",
                    strike.address.address_sha256,
                    "melee reach is not one exact default or explicit "
                    "distance",
                )
            )
        targeting["descriptorAddressSha256"] = list(
            profile.descriptor_address_sha256
        )
        return targeting, tuple(deferrals)

    if profile.geometry_kind in (
        "increment-explicit-reload",
        "increment-source-unspecified-resource",
        "absolute-maximum",
        "thrown-distance",
        "increment-plus-bare-thrown",
    ):
        targeting_status = "mechanically-complete"
    else:
        targeting_status = "deferred"
        deferrals.append(
            _integration_requirement(
                "targeting",
                f"ranged-geometry:{profile.geometry_kind}",
                strike.address.address_sha256,
                "ranged targeting distance is absent, ambiguous, or "
                "mode-incompatible",
            )
        )
    if profile.geometry_kind in (
        "increment-explicit-reload",
        "increment-source-unspecified-resource",
        "increment-plus-bare-thrown",
    ):
        distance_kind = "range-increment"
    elif profile.geometry_kind == "thrown-distance":
        distance_kind = "thrown-range-increment"
    elif profile.geometry_kind == "absolute-maximum":
        distance_kind = "absolute-maximum"
    else:
        distance_kind = profile.geometry_kind
    if profile.geometry_kind == "increment-explicit-reload":
        resource_policy = "explicit-reload"
    elif profile.geometry_kind in (
        "thrown-distance",
        "increment-plus-bare-thrown",
    ):
        resource_policy = "thrown-source"
    elif profile.geometry_kind == "increment-source-unspecified-resource":
        resource_policy = "source-unspecified"
    elif profile.geometry_kind == "absolute-maximum":
        resource_policy = "not-stated"
    else:
        resource_policy = "unresolved"
    targeting = {
        "status": targeting_status,
        "kind": distance_kind,
        "feet": profile.feet,
        "reloadActions": profile.reload_actions,
        "reloadExplicit": profile.reload_explicit,
        "resourcePolicy": resource_policy,
        "descriptorAddressSha256": list(
            profile.descriptor_address_sha256
        ),
    }
    return targeting, tuple(deferrals)


def _integration_damage(
    strike: StrikeSource,
) -> tuple[
    dict[str, Any],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    components: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    deferrals: list[dict[str, Any]] = []
    carrier_payloads = []
    damage_carriers = tuple(
        carrier
        for carrier in strike.carriers
        if carrier.raw_member.key == "Damage"
    )
    effect_carriers = tuple(
        carrier
        for carrier in strike.carriers
        if carrier.raw_member.key in ("Effect", "Effects")
    )

    for carrier in strike.carriers:
        projected_components = []
        for candidate in carrier.component_candidates:
            projection = _safe_damage_projection(
                candidate.source_text
            )
            if projection is not None:
                payload = _damage_projection_payload(
                    projection,
                    carrier,
                    candidate,
                )
                components.append(payload)
                projected_components.append(payload)
        carrier_payloads.append(
            {
                "sourceAddressSha256": carrier.address_sha256,
                "rawKey": carrier.raw_member.key,
                "occurrence": carrier.occurrence,
                "memberOrdinal": carrier.member_ordinal,
                "carrierOrdinal": carrier.carrier_ordinal,
                "rawValueSha256": carrier.raw_value_sha256,
                "rawText": carrier.raw_text,
                "shape": carrier.shape,
                "damageTypeCandidates": list(
                    carrier.damage_type_candidates
                ),
                "components": projected_components,
                "terms": [
                    {
                        "termOrdinal": term.term_ordinal,
                        "connectorBefore": term.connector_before,
                        "sourceSpan": {
                            "start": term.start,
                            "end": term.end,
                        },
                        "rawText": term.raw_text,
                        "rawTextSha256": term.raw_text_sha256,
                        "candidateClass": term.candidate_class,
                        "tailOrdinal": term.tail_ordinal,
                        "riderOrdinal": term.rider_ordinal,
                        "riderAddressSha256": (
                            term.rider_address_sha256
                        ),
                    }
                    for term in carrier.terms
                ],
            }
        )

        if carrier.raw_member.key in ("Effect", "Effects"):
            deferrals.append(
                _integration_requirement(
                    "effect",
                    (
                        "strike-effect:"
                        f"{carrier.raw_member.key.casefold()}"
                    ),
                    carrier.address_sha256,
                    "effect source is preserved for its dedicated "
                    "compiler",
                )
            )
            continue
        if carrier.shape == "delegated-damage-reference":
            blockers.append(
                _integration_requirement(
                    "damage",
                    "delegated-damage-reference",
                    carrier.address_sha256,
                    "damage delegates to another source and cannot be "
                    "projected here",
                )
            )
        elif carrier.shape == "type-choice-persistent-splash":
            blockers.append(
                _integration_requirement(
                    "damage",
                    "damage-type-choice-and-splash",
                    carrier.address_sha256,
                    "damage type, persistent damage, and splash damage "
                    "require one explicit choice-aware compiler",
                )
            )
        elif carrier.shape == "conditional-or-alternative-damage":
            blockers.append(
                _integration_requirement(
                    "damage",
                    "conditional-or-alternative-damage",
                    carrier.address_sha256,
                    "target-dependent damage cannot be flattened into an "
                    "unconditional packet",
                )
            )
        elif carrier.shape in (
            "non-damage-in-damage-carrier",
            "non-text-damage-carrier",
        ):
            blockers.append(
                _integration_requirement(
                    "damage",
                    f"strike-damage-shape:{carrier.shape}",
                    carrier.address_sha256,
                    "Damage contains no mechanically complete numeric "
                    "component",
                )
            )
        elif carrier.shape in (
            "single-component",
            "single-component-with-riders",
            "compound-damage",
            "compound-damage-with-riders",
        ):
            if (
                not projected_components
                or len(projected_components)
                != len(carrier.component_candidates)
            ):
                blockers.append(
                    _integration_requirement(
                        "damage",
                        "unprojectable-damage-component",
                        carrier.address_sha256,
                        "one or more exact damage components do not match "
                        "the bounded numeric grammar",
                    )
                )
            if len(carrier.damage_type_candidates) > len(
                {
                    component["damageType"]
                    for component in projected_components
                }
            ):
                blockers.append(
                    _integration_requirement(
                        "damage",
                        "damage-type-choice-required",
                        carrier.address_sha256,
                        "source offers more damage types than one "
                        "deterministic packet can select",
                    )
                )
            if any(
                component["persistent"]
                for component in projected_components
            ):
                blockers.append(
                    _integration_requirement(
                        "damage",
                        "persistent-damage-resolution",
                        carrier.address_sha256,
                        "persistent damage is an effect state, not immediate "
                        "Strike damage",
                    )
                )
            for rider in carrier.rider_terms:
                deferrals.append(
                    _integration_requirement(
                        "effect",
                        "strike-damage-rider",
                        (
                            rider.rider_address_sha256
                            or carrier.address_sha256
                        ),
                        "damage rider is retained for its dedicated "
                        "effect compiler",
                    )
                )
        else:
            blockers.append(
                _integration_requirement(
                    "damage",
                    f"strike-damage-shape:{carrier.shape}",
                    carrier.address_sha256,
                    "damage shape has no reviewed integration projection",
                )
            )

    if len(damage_carriers) > 1:
        blockers.append(
            _integration_requirement(
                "damage",
                "multiple-damage-carriers",
                strike.address.address_sha256,
                "multiple Damage members remain distinct and require an "
                "explicit composition contract",
            )
        )
    explicit_no_damage = (
        not damage_carriers
        and bool(effect_carriers)
        and len(effect_carriers) == len(strike.carriers)
    )
    if explicit_no_damage:
        blockers.append(
            _integration_requirement(
                "effect",
                "effect-only-strike-resolution",
                strike.address.address_sha256,
                "source explicitly supplies an effect-only Strike; no zero "
                "damage packet may be invented",
            )
        )
    elif not strike.carriers:
        blockers.append(
            _integration_requirement(
                "damage",
                "missing-strike-carrier",
                strike.address.address_sha256,
                "source supplies no Damage, Effect, or Effects carrier",
            )
        )
    immediate_complete = (
        bool(damage_carriers)
        and bool(components)
        and not blockers
    )
    if immediate_complete:
        status = "exact-immediate-components"
    elif explicit_no_damage:
        status = "exact-no-damage-effect-only"
    else:
        status = "deferred"
    return (
        {
            "status": status,
            "immediateComplete": immediate_complete,
            "explicitNoDamage": explicit_no_damage,
            "components": components,
            "carriers": carrier_payloads,
        },
        tuple(blockers),
        tuple(deferrals),
    )


def _integration_payload(
    bundle: StrikeSourceBundle,
) -> dict[str, Any]:
    if type(bundle) is not StrikeSourceBundle:
        raise TypeError(
            "Strike integration projection requires an exact source bundle"
        )
    projected_ids = tuple(
        _projected_occurrence_id(strike)
        for strike in bundle.strikes
    )
    if len(projected_ids) != len(set(projected_ids)):
        raise StrikeSourceError(
            "source-occurrence Strike ids are not unique"
        )
    label_occurrences: Counter[str] = Counter()
    records = []
    for strike, projected_id in zip(
        bundle.strikes,
        projected_ids,
        strict=True,
    ):
        label_occurrence = label_occurrences[strike.label_key]
        label_occurrences[strike.label_key] += 1
        targeting, targeting_blockers = _integration_targeting(
            strike
        )
        damage, damage_blockers, damage_deferrals = (
            _integration_damage(strike)
        )
        blockers = (*targeting_blockers, *damage_blockers)
        mechanically_complete = (
            not blockers
            and targeting["status"] == "mechanically-complete"
            and damage["immediateComplete"]
        )
        records.append(
            {
                "id": projected_id,
                "normalizedLabel": strike.label_key,
                "normalizedLabelOccurrence": label_occurrence,
                "sourceActionId": strike.semantic_action_id,
                "sourceAddressSha256": (
                    strike.address.address_sha256
                ),
                "sourceName": strike.source_name,
                "mode": strike.mode,
                "attackModifier": strike.projection.attack_bonus,
                "targeting": targeting,
                "traits": [
                    {
                        "traitOrdinal": trait.trait_ordinal,
                        "rawText": trait.raw_text,
                        "normalizedText": trait.normalized_text,
                        "category": trait.category,
                        "parsed": _thaw_json(trait.parsed),
                        "sourceAddressSha256": trait.address_sha256,
                        "rawValueSha256": trait.raw_value_sha256,
                    }
                    for trait in strike.traits
                ],
                "damage": damage,
                "mechanicallyComplete": mechanically_complete,
                "integrationBlockers": list(blockers),
                "deferredDependencies": [
                    {
                        "kind": dependency.kind,
                        "requirementId": dependency.requirement_id,
                        "sourceAddressSha256": (
                            dependency.source_span_address_sha256
                        ),
                        "reason": dependency.reason,
                    }
                    for dependency in strike.deferred_dependencies
                ]
                + list(damage_deferrals),
            }
        )
    ready = sum(record["mechanicallyComplete"] for record in records)
    payload = {
        "schema": 1,
        "kind": "pf2er-strike-integration-projection",
        "status": "compile-only",
        "runtimeSupported": False,
        "registryStatus": "unregistered",
        "integrationContract": {
            "idPolicy": "exact-source-occurrence-v1",
            "admissionField": "mechanicallyComplete",
            "admissionRule": (
                "admit a creature only when every retained source Strike "
                "occurrence is mechanicallyComplete"
            ),
            "damageRollPolicy": (
                "one ordered roll per projected immediate component; "
                "components must never be merged"
            ),
            "noDamagePolicy": (
                "explicitNoDamage never authorizes an invented zero-damage "
                "packet"
            ),
            "deferredPolicy": (
                "deferredDependencies remain compile-only and do not imply "
                "runtime support"
            ),
        },
        "source": {
            "blockAddress": bundle.block_source.address.as_serialized(),
            "receipt": SourceReceipt.as_serialized(
                bundle.block_source.source_receipt
            ),
        },
        "counts": {
            "sourceStrikeOccurrences": len(records),
            "uniqueProjectedIds": len(set(projected_ids)),
            "mechanicallyCompleteStrikes": ready,
            "deferredStrikes": len(records) - ready,
            "sameModeCollisionGroups": len(
                bundle.same_mode_collisions
            ),
            "crossModeCollisionGroups": len(
                bundle.cross_mode_collisions
            ),
        },
        "facadeReady": bool(records) and ready == len(records),
        "strikes": records,
    }
    return _thaw_json(_freeze_json(payload))


def _as_shared_strike_rider_source(
    strike: StrikeSource,
    carrier: StrikeCarrierSource,
    rider: StrikeCarrierTerm,
    /,
) -> StrikeRiderSource:
    """Adapt an exact all-``plus`` Damage tail to the frozen rider contract."""

    if carrier not in strike.carriers:
        raise StrikeSourceError(
            "Strike rider carrier does not belong to the Strike"
        )
    if rider not in carrier.terms or rider.rider_ordinal is None:
        raise StrikeSourceError(
            "Strike rider term does not belong to the carrier"
        )
    if (
        carrier.raw_member.key != "Damage"
        or carrier.raw_text is None
        or not carrier.terms
        or carrier.terms[0].candidate_class
        != "damage-component-candidate"
        or any(
            term.rider_ordinal is None
            for term in carrier.terms[1:]
        )
        or any(
            term.connector_before != " plus "
            for term in carrier.terms[1:]
        )
        or rider.term_ordinal != rider.rider_ordinal + 1
    ):
        raise StrikeSourceError(
            "carrier cannot be losslessly represented by the shared "
            "plus-rider contract"
        )
    return StrikeRiderSource(
        raw_strike_member=strike.raw_outer_member,
        strike_member_ordinal=strike.address.outer.member_ordinal,
        strike_ordinal=strike.address.strike_ordinal,
        damage_member_ordinal=carrier.member_ordinal,
        rider_ordinal=rider.rider_ordinal,
        strike_id=strike.semantic_action_id,
        source_id=strike.address.block.source_id,
        locator=strike.address.block.locator,
        section_id=strike.address.block.section_id,
        content_path=tuple(
            [
                *(
                    RawSourcePathStep(
                        item.raw_key,
                        item.member_ordinal,
                    )
                    for item in (
                        strike.address.block.resolved_container_path
                    )
                ),
                RawSourcePathStep(
                    strike.address.block.block_raw_key,
                    strike.address.block.block_member_ordinal,
                ),
            ]
        ),
    )


def _install_strike_public_api() -> tuple[Any, ...]:
    """Seal the compile boundary around exact server-owned authority.

    The returned closures do not use caller-editable defaults.  They also
    reject rebinding of compiler functions, class validators, or the grammar
    constants captured when this module completed initialization.
    """

    namespace = globals()
    excluded_names = frozenset(
        {
            "_install_strike_public_api",
            "compile_items_member",
            "compile_strike_block",
            "compile_strike_source",
            "resolve_strike_compiler_patch",
            "resolve_strike_compiler_patches",
            "reviewed_strike_compiler_registrations",
            "as_shared_strike_rider_source",
            "project_strike_bundle",
            "serialize_strike_integration_projection",
        }
    )
    tracked_functions = tuple(
        (name, value)
        for name, value in namespace.items()
        if (
            type(value) is FunctionType
            and value.__module__ == __name__
            and name not in excluded_names
        )
    )
    tracked_defaults = tuple(
        (
            function,
            function.__defaults__,
            (
                None
                if function.__kwdefaults__ is None
                else dict(function.__kwdefaults__)
            ),
            function.__kwdefaults__,
        )
        for _name, function in tracked_functions
    )
    tracked_class_bindings = tuple(
        (name, value)
        for name, value in namespace.items()
        if (
            type(value) is type
            and value.__module__ == __name__
            and (
                value.__name__.startswith("Strike")
                or value is ResolvedStrikeCompilerPatch
            )
        )
    )
    tracked_classes = tuple(
        value
        for _name, value in tracked_class_bindings
    )
    tracked_class_dictionaries = tuple(
        (
            class_value,
            frozenset(vars(class_value)),
            tuple(vars(class_value).items()),
        )
        for class_value in tracked_classes
    )
    tracked_field_shapes = tuple(
        (
            class_value,
            tuple(
                (item.name, item.init, item.compare, item.repr)
                for item in dataclass_fields(class_value)
            ),
        )
        for class_value in tracked_classes
        if hasattr(class_value, "__dataclass_fields__")
    )
    tracked_constants = (
        ("RawSourceArray", RawSourceArray),
        ("RawSourceMember", RawSourceMember),
        ("RawSourceObject", RawSourceObject),
        ("RawIndexStep", RawIndexStep),
        ("RawMemberStep", RawMemberStep),
        ("SourceAddress", SourceAddress),
        ("SourceAuthorityAdapter", SourceAuthorityAdapter),
        ("SourceReceipt", SourceReceipt),
        ("VerifiedSourceSelection", VerifiedSourceSelection),
        ("StrikeRiderSource", StrikeRiderSource),
        ("canonical_json_bytes", canonical_json_bytes),
        ("dataclass_fields", dataclass_fields),
        ("parse_decimal_integer", parse_decimal_integer),
        ("WeakKeyDictionary", WeakKeyDictionary),
        ("_HASH_RE", _HASH_RE),
        ("_ATTACK_RE", _ATTACK_RE),
        ("_AMOUNT", _AMOUNT),
        ("_DAMAGE_TYPES", _DAMAGE_TYPES),
        ("_DAMAGE_TYPE_PATTERN", _DAMAGE_TYPE_PATTERN),
        ("_DAMAGE_COMPONENT_RE", _DAMAGE_COMPONENT_RE),
        ("_DAMAGE_COMPONENT_SCAN_RE", _DAMAGE_COMPONENT_SCAN_RE),
        ("_TYPE_CHOICE_SCAN_RE", _TYPE_CHOICE_SCAN_RE),
        ("_ANY_AMOUNT_RE", _ANY_AMOUNT_RE),
        ("_SAFE_DAMAGE_RE", _SAFE_DAMAGE_RE),
        ("_TRAIT_PATTERNS", _TRAIT_PATTERNS),
        ("_GEOMETRY_TRAIT_CATEGORIES", _GEOMETRY_TRAIT_CATEGORIES),
        ("_CARRIER_KEYS", _CARRIER_KEYS),
        ("_KNOWN_STRIKE_KEYS", _KNOWN_STRIKE_KEYS),
        ("_TOP_LEVEL_CONNECTORS", _TOP_LEVEL_CONNECTORS),
        ("_MAX_SIGNED_64", _MAX_SIGNED_64),
        ("_MAX_TEXT_BYTES", _MAX_TEXT_BYTES),
        ("_MAX_JSON_DEPTH", _MAX_JSON_DEPTH),
        ("_MAX_JSON_NODES", _MAX_JSON_NODES),
        ("_MAX_JSON_BYTES", _MAX_JSON_BYTES),
        ("_MAX_BLOCK_MEMBERS", _MAX_BLOCK_MEMBERS),
        ("_MAX_STRIKES_PER_BLOCK", _MAX_STRIKES_PER_BLOCK),
        ("_MAX_ADDRESS_PATH_STEPS", _MAX_ADDRESS_PATH_STEPS),
    )
    tracked_authority_attributes = (
        (
            SourceAuthorityAdapter,
            "validate_selection",
            SourceAuthorityAdapter.validate_selection,
        ),
        (
            SourceReceipt,
            "as_serialized",
            SourceReceipt.as_serialized,
        ),
        (
            SourceAddress,
            "as_serialized",
            SourceAddress.as_serialized,
        ),
        (
            RawMemberStep,
            "as_serialized",
            RawMemberStep.as_serialized,
        ),
        (
            RawIndexStep,
            "as_serialized",
            RawIndexStep.as_serialized,
        ),
        (
            RawSourceObject,
            "values",
            RawSourceObject.values,
        ),
        (
            VerifiedSourceSelection,
            "receipt",
            VerifiedSourceSelection.receipt,
        ),
        (
            VerifiedSourceSelection,
            "block_sha256",
            VerifiedSourceSelection.block_sha256,
        ),
    )
    tracked_dependency_class_dictionaries = tuple(
        (
            class_value,
            frozenset(vars(class_value)),
            tuple(vars(class_value).items()),
        )
        for class_value in (
            RawSourceArray,
            RawSourceMember,
            RawSourceObject,
            RawIndexStep,
            RawMemberStep,
            SourceAddress,
            SourceAuthorityAdapter,
            SourceReceipt,
            VerifiedSourceSelection,
        )
    )

    def code_functions(value: object) -> tuple[FunctionType, ...]:
        if type(value) is FunctionType:
            return (value,)
        if type(value) in (staticmethod, classmethod):
            function = value.__func__
            return (function,) if type(function) is FunctionType else ()
        if type(value) is property:
            return tuple(
                function
                for function in (value.fget, value.fset, value.fdel)
                if type(function) is FunctionType
            )
        return ()

    code_candidates = [
        function
        for _name, function in tracked_functions
    ]
    for _class_value, _keys, items in (
        *tracked_class_dictionaries,
        *tracked_dependency_class_dictionaries,
    ):
        for _attribute, value in items:
            code_candidates.extend(code_functions(value))
    for _name, value in tracked_constants:
        code_candidates.extend(code_functions(value))
    for _class_value, _attribute, value in (
        tracked_authority_attributes
    ):
        code_candidates.extend(code_functions(value))
    deduplicated_code_candidates: list[FunctionType] = []
    for function in code_candidates:
        if not any(
            existing is function
            for existing in deduplicated_code_candidates
        ):
            deduplicated_code_candidates.append(function)
    tracked_code_objects = tuple(
        (function, function.__code__)
        for function in deduplicated_code_candidates
    )

    block_source_factory = _new_block_source
    block_compiler = _compile_block_source
    bundle_validator = _validate_bundle
    item_compiler = _compile_items_from_block_source
    strike_compiler = _compile_strike_from_block_source
    patch_resolver = _resolve_registered_strike_compiler_patch
    shared_rider_adapter = _as_shared_strike_rider_source
    integration_projector = _integration_payload
    ordinal_validator = _require_ordinal
    bundle_type = StrikeSourceBundle
    integration_type = StrikeIntegrationProjection
    patch_type = StrikeCompilerPatch
    registration_type = StrikeCompilerRegistration
    object_new = object.__new__
    object_getattribute = object.__getattribute__
    object_setattr = object.__setattr__
    integration_registry: WeakKeyDictionary[
        StrikeIntegrationProjection,
        tuple[StrikeSourceBundle, str],
    ] = WeakKeyDictionary()
    reviewed_registrations: tuple[StrikeCompilerRegistration, ...] = ()

    def integrity_guard() -> None:
        for name, expected in tracked_functions:
            if namespace.get(name) is not expected:
                raise StrikeSourceError(
                    f"Strike compiler module binding changed: {name}"
                )
        for function, expected_code in tracked_code_objects:
            if function.__code__ is not expected_code:
                raise StrikeSourceError(
                    "Strike compiler function code was rebound: "
                    f"{function.__qualname__}"
                )
        for name, expected in tracked_class_bindings:
            if namespace.get(name) is not expected:
                raise StrikeSourceError(
                    f"Strike compiler class binding changed: {name}"
                )
        for function, defaults, kw_snapshot, kw_object in tracked_defaults:
            if function.__defaults__ is not defaults:
                raise StrikeSourceError(
                    "Strike compiler function defaults were rebound"
                )
            if function.__kwdefaults__ is not kw_object:
                raise StrikeSourceError(
                    "Strike compiler keyword defaults were rebound"
                )
            if (
                kw_snapshot is not None
                and function.__kwdefaults__ != kw_snapshot
            ):
                raise StrikeSourceError(
                    "Strike compiler keyword defaults were mutated"
                )
        for class_value, expected_keys, expected_items in (
            tracked_class_dictionaries
        ):
            observed = vars(class_value)
            if frozenset(observed) != expected_keys:
                raise StrikeSourceError(
                    "Strike compiler class dictionary changed: "
                    f"{class_value.__name__}"
                )
            for attribute, expected in expected_items:
                if observed[attribute] is not expected:
                    raise StrikeSourceError(
                        "Strike compiler class attribute was rebound: "
                        f"{class_value.__name__}.{attribute}"
                    )
        for class_value, expected_shape in tracked_field_shapes:
            observed_shape = tuple(
                (item.name, item.init, item.compare, item.repr)
                for item in dataclass_fields(class_value)
            )
            if observed_shape != expected_shape:
                raise StrikeSourceError(
                    "Strike compiler dataclass shape was mutated: "
                    f"{class_value.__name__}"
                )
        for name, expected in tracked_constants:
            if namespace.get(name) is not expected:
                raise StrikeSourceError(
                    f"Strike compiler grammar binding changed: {name}"
                )
        for class_value, attribute, expected in (
            tracked_authority_attributes
        ):
            if getattr(class_value, attribute, None) is not expected:
                raise StrikeSourceError(
                    "Strike compiler authority contract was rebound: "
                    f"{class_value.__name__}.{attribute}"
                )
        for class_value, expected_keys, expected_items in (
            tracked_dependency_class_dictionaries
        ):
            observed = vars(class_value)
            if frozenset(observed) != expected_keys:
                raise StrikeSourceError(
                    "Strike compiler dependency class dictionary changed: "
                    f"{class_value.__name__}"
                )
            for attribute, expected in expected_items:
                if observed[attribute] is not expected:
                    raise StrikeSourceError(
                        "Strike compiler dependency class attribute was "
                        "rebound: "
                        f"{class_value.__name__}.{attribute}"
                    )

    def compile_block(
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
        /,
    ) -> StrikeSourceBundle:
        integrity_guard()
        result = block_compiler(
            block_source_factory(authority, consumer),
            review_evidence_by_address={},
        )
        if type(result) is not bundle_type:
            raise TypeError("Strike compiler returned a non-exact bundle")
        integrity_guard()
        bundle_validator(result)
        integrity_guard()
        return result

    def compile_item(
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
        member_ordinal: int,
        /,
    ) -> StrikeItemsField:
        integrity_guard()
        ordinal_validator(member_ordinal, "Items member ordinal")
        block_source = block_source_factory(authority, consumer)
        result = item_compiler(block_source, member_ordinal)
        bundle = block_compiler(
            block_source,
            review_evidence_by_address={},
        )
        matches = tuple(
            item
            for item in bundle.items_fields
            if item.member_ordinal == member_ordinal
        )
        if len(matches) != 1 or result != matches[0]:
            raise StrikeSourceError(
                "Items compiler result disagrees with authenticated block"
            )
        integrity_guard()
        return result

    def compile_strike(
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
        outer_member_ordinal: int,
        strike_ordinal: int,
        /,
    ) -> StrikeSource:
        integrity_guard()
        ordinal_validator(
            outer_member_ordinal,
            "Strike outer member ordinal",
        )
        ordinal_validator(strike_ordinal, "Strike ordinal")
        block_source = block_source_factory(authority, consumer)
        members = block_source.raw_block.members
        if outer_member_ordinal >= len(members):
            raise StrikeSourceError(
                "Strike outer member ordinal does not resolve"
            )
        raw_outer = members[outer_member_ordinal]
        if (
            type(raw_outer) is not RawSourceMember
            or raw_outer.key not in ("Melee", "Ranged")
            or type(raw_outer.value) is not RawSourceArray
            or strike_ordinal >= len(raw_outer.value.items)
        ):
            raise StrikeSourceError(
                "Strike ordinal does not select one exact Strike object"
            )
        occurrence = sum(
            member.key == raw_outer.key
            for member in members[:outer_member_ordinal]
        )
        address = StrikeSourceAddress(
            block=block_source.address,
            outer=StrikeOuterAddress(
                raw_key=raw_outer.key,
                occurrence=occurrence,
                member_ordinal=outer_member_ordinal,
            ),
            strike_ordinal=strike_ordinal,
        )
        result = strike_compiler(
            block_source,
            address,
            review_evidence=(),
        )
        bundle = block_compiler(
            block_source,
            review_evidence_by_address={},
        )
        matches = tuple(
            item
            for item in bundle.strikes
            if item.address == address
        )
        if len(matches) != 1 or result != matches[0]:
            raise StrikeSourceError(
                "single Strike result disagrees with authenticated block"
            )
        integrity_guard()
        return result

    def reviewed() -> tuple[StrikeCompilerRegistration, ...]:
        integrity_guard()
        return reviewed_registrations

    def resolve_patch(
        bundle: StrikeSourceBundle,
        patch: StrikeCompilerPatch,
        /,
    ) -> ResolvedStrikeCompilerPatch:
        integrity_guard()
        if type(bundle) is not bundle_type:
            raise TypeError("Strike compiler resolver requires exact bundle")
        if type(patch) is not patch_type:
            raise TypeError("Strike compiler resolver requires exact patch")
        bundle_validator(bundle)
        matches = tuple(
            registration
            for registration in reviewed_registrations
            if (
                type(registration) is registration_type
                and registration.compiler_id == patch.compiler_id
                and registration.source_address_sha256
                == patch.source_address_sha256
            )
        )
        if len(matches) != 1:
            raise StrikeCompilerLinkError(
                "Strike compiler patch has no exact reviewed registration"
            )
        result = patch_resolver(bundle, patch, matches[0])
        integrity_guard()
        return result

    def resolve_patches(
        bundle: StrikeSourceBundle,
        patches: Sequence[StrikeCompilerPatch],
        /,
    ) -> tuple[ResolvedStrikeCompilerPatch, ...]:
        integrity_guard()
        if type(bundle) is not bundle_type:
            raise TypeError("Strike compiler resolver requires exact bundle")
        if type(patches) is not tuple:
            raise TypeError("Strike compiler patches must be an exact tuple")
        bundle_validator(bundle)
        if not patches:
            return ()
        if any(type(patch) is not patch_type for patch in patches):
            raise TypeError("Strike compiler patches must be exact")
        results = tuple(resolve_patch(bundle, patch) for patch in patches)
        claims = tuple(
            (
                result.patch.source_address_sha256,
                result.patch.rider_address_sha256,
            )
            for result in results
        )
        if len(claims) != len(set(claims)):
            raise StrikeCompilerLinkError(
                "compiler patches claim overlapping source spans"
            )
        integrity_guard()
        return results

    def adapt_shared_rider(
        bundle: StrikeSourceBundle,
        strike: StrikeSource,
        carrier: StrikeCarrierSource,
        rider: StrikeCarrierTerm,
        /,
    ) -> StrikeRiderSource:
        integrity_guard()
        bundle_validator(bundle)
        if (
            type(strike) is not StrikeSource
            or not any(item is strike for item in bundle.strikes)
            or type(carrier) is not StrikeCarrierSource
            or not any(item is carrier for item in strike.carriers)
            or type(rider) is not StrikeCarrierTerm
            or not any(item is rider for item in carrier.terms)
        ):
            raise StrikeSourceError(
                "shared Strike rider must retain exact bundle identity"
            )
        result = shared_rider_adapter(strike, carrier, rider)
        integrity_guard()
        return result

    def project_bundle(
        bundle: StrikeSourceBundle,
        /,
    ) -> StrikeIntegrationProjection:
        integrity_guard()
        if type(bundle) is not bundle_type:
            raise TypeError(
                "Strike integration projection requires an exact bundle"
            )
        canonical_bundle = bundle_validator(bundle)
        payload = integration_projector(canonical_bundle)
        digest = canonical_source_sha256(payload)
        result = object_new(integration_type)
        object_setattr(result, "_bundle", bundle)
        object_setattr(result, "_payload", _freeze_json(payload))
        object_setattr(result, "projection_sha256", digest)
        integration_registry[result] = (bundle, digest)
        integrity_guard()
        return result

    def serialize_projection(
        projection: StrikeIntegrationProjection,
        /,
    ) -> dict[str, Any]:
        integrity_guard()
        if type(projection) is not integration_type:
            raise TypeError(
                "Strike integration serializer requires an exact artifact"
            )
        issued = integration_registry.get(projection)
        if issued is None:
            raise StrikeSourceError(
                "Strike integration projection was not issued"
            )
        try:
            bundle = object_getattribute(projection, "_bundle")
            payload = object_getattribute(projection, "_payload")
            digest = object_getattribute(
                projection,
                "projection_sha256",
            )
        except (AttributeError, TypeError) as failure:
            raise StrikeSourceError(
                "Strike integration projection state is invalid"
            ) from failure
        if (
            bundle is not issued[0]
            or digest != issued[1]
            or type(bundle) is not bundle_type
            or type(payload) is not MappingProxyType
            or type(digest) is not str
        ):
            raise StrikeSourceError(
                "Strike integration projection authority changed"
            )
        canonical_bundle = bundle_validator(bundle)
        expected = integration_projector(canonical_bundle)
        if (
            canonical_source_sha256(expected) != digest
            or _thaw_json(payload) != expected
        ):
            raise StrikeSourceError(
                "Strike integration projection disagrees with source"
            )
        integrity_guard()
        return expected

    return (
        compile_item,
        compile_block,
        compile_strike,
        resolve_patch,
        resolve_patches,
        reviewed,
        adapt_shared_rider,
        project_bundle,
        serialize_projection,
    )


(
    compile_items_member,
    compile_strike_block,
    compile_strike_source,
    resolve_strike_compiler_patch,
    resolve_strike_compiler_patches,
    reviewed_strike_compiler_registrations,
    as_shared_strike_rider_source,
    project_strike_bundle,
    serialize_strike_integration_projection,
) = _install_strike_public_api()


__all__ = [
    "DeferredDependencyKind",
    "ResolvedStrikeCompilerPatch",
    "StrikeBlockAddress",
    "StrikeBlockSource",
    "StrikeCarrierSource",
    "StrikeCarrierTerm",
    "StrikeCompilerLinkError",
    "StrikeCompilerPatch",
    "StrikeCompilerRegistration",
    "StrikeContainerPathSegment",
    "StrikeDamageComponentCandidate",
    "StrikeDamageProjection",
    "StrikeDeferredDependency",
    "StrikeEquipmentEvidence",
    "StrikeIdentityCollision",
    "StrikeIntegrationProjection",
    "StrikeItemCandidate",
    "StrikeItemsField",
    "StrikeItemToken",
    "StrikeMemberSource",
    "StrikeMode",
    "StrikeOuterAddress",
    "StrikeRangeProfile",
    "StrikeReviewEvidence",
    "StrikeSource",
    "StrikeSourceAddress",
    "StrikeSourceBundle",
    "StrikeSourceError",
    "StrikeStructuralProjection",
    "as_shared_strike_rider_source",
    "canonical_source_sha256",
    "compile_items_member",
    "compile_strike_block",
    "compile_strike_source",
    "normalized_source_text",
    "project_strike_bundle",
    "raw_source_payload",
    "raw_source_sha256",
    "reviewed_strike_compiler_registrations",
    "resolve_strike_compiler_patch",
    "resolve_strike_compiler_patches",
    "semantic_source_key",
    "serialize_strike_integration_projection",
    "strike_label_key",
]

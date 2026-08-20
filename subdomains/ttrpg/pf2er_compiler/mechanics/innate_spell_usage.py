"""Compile exact Monster Core innate-spell availability.

This family is deliberately compile/link only.  It derives every consumer,
Player Core spell provider, and rules provider from one server-owned
``SourceAuthorityAdapter``.  Public callers can choose verified selections,
but they cannot construct trusted source objects or replace the retained
authority context.

The linked artifact records at-will, constant, and contextual cantrip
availability.  It does not expose Cast a Spell transitions or spell effects,
and it cannot be mounted in the runtime registry.  The one reviewed
``mindreading`` source spelling remains an exact catalog-mismatch deferral;
this module never aliases it to ``mind reading``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import html
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Literal, TypeAlias, final
from weakref import WeakKeyDictionary

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RawSourceValue,
)
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    raw_source_sha256,
)
from .source_values import parse_decimal_integer


FAMILY_ID = "innate-spell-usage"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"
MECHANIC_TYPES = (
    "innate-at-will-spell",
    "constant-spell",
    "innate-cantrip",
)
EXPECTED_PLAYER_CORE_SPELLS = 491

UsageKind: TypeAlias = Literal[
    "limited",
    "at-will",
    "constant",
    "context-cantrip",
]
EntryKind: TypeAlias = Literal[
    "ranked",
    "cantrip",
    "constant",
    "unranked",
]
ConstantEntryRole: TypeAlias = Literal[
    "group-header",
    "rank-continuation",
]
MarkupKind: TypeAlias = Literal["italic", "plain"]

_INNATE_HEADER_RE = re.compile(
    r"^(?P<tradition>Arcane|Divine|Occult|Primal) Innate Spells$",
    re.ASCII,
)
_RANK_RE = re.compile(
    r"^(?P<rank>1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)$",
    re.ASCII,
)
_CANTRIP_RE = re.compile(
    r"^Cantrips "
    r"\((?P<rank>1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\)$",
    re.ASCII,
)
_CONSTANT_RE = re.compile(
    r"^Constant"
    r"(?: \((?P<rank>1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\))?$",
    re.ASCII,
)
_CONSTANT_CONTINUATION_RE = re.compile(
    r"^\((?P<rank>1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\)$",
    re.ASCII,
)
_ITALIC_NAME_RE = re.compile(
    r"^\s*<i>(?P<name>.*?)</i>(?P<tail>.*)$",
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_AT_WILL_RE = re.compile(r"\bat will\b", re.IGNORECASE)
_ACCEPTED_FIELD_ORDERS = (
    ("DC", "Entries"),
    ("DC", "Attack", "Entries"),
    ("Focus Points", "DC", "Entries"),
)
_RANK_TABLE = (
    ("1st", 1),
    ("2nd", 2),
    ("3rd", 3),
    ("4th", 4),
    ("5th", 5),
    ("6th", 6),
    ("7th", 7),
    ("8th", 8),
    ("9th", 9),
    ("10th", 10),
)


class InnateSpellSourceShapeError(ValueError):
    """A verified Monster Core source violated the reviewed grammar."""


class SpellCatalogLinkError(ValueError):
    """A verified Player Core provider set cannot link one usage."""


class SpellCatalogAmbiguityError(SpellCatalogLinkError):
    """More than one exact verified catalog provider has the same name."""


class SpellCatalogSemanticError(SpellCatalogLinkError):
    """One exact verified provider conflicts with source rank or kind."""


class InnateSpellArtifactError(ValueError):
    """A compiled artifact no longer agrees with its authority."""


@dataclass(frozen=True, slots=True)
class _MentionData:
    source_mention_ordinal: int
    usage_ordinal: int | None
    entry_pair_ordinal: int | None
    entry_key_occurrence: int | None
    value_item_ordinal: int | None
    mention_ordinal: int
    char_start: int
    char_end: int
    entry_key: str | None
    entry_kind: EntryKind
    constant_entry_role: ConstantEntryRole | None
    tradition: str
    source_rank: int | None
    usage_kind: UsageKind
    raw_scalar: str
    raw_scalar_sha256: str
    raw_chunk: str
    raw_name: str
    normalized_name: str
    raw_annotation: str
    qualifier_fragments: tuple[str, ...]
    markup: MarkupKind


@dataclass(frozen=True, slots=True)
class _EntryGroupData:
    entry_pair_ordinal: int | None
    entry_key_occurrence: int | None
    raw_key: str
    raw_value: RawSourceValue = field(repr=False)
    raw_value_sha256: str
    entry_kind: EntryKind
    constant_entry_role: ConstantEntryRole | None
    rank: int | None
    mentions: tuple[_MentionData, ...]


@dataclass(frozen=True, slots=True)
class _DuplicateGroupData:
    normalized_name: str
    mention_ordinals: tuple[int, ...]
    usage_kinds: tuple[UsageKind, ...]


@dataclass(frozen=True, slots=True)
class _CompiledData:
    consumer: VerifiedSourceSelection = field(repr=False, compare=False)
    creature_name: str
    spellcasting_member_ordinal: int
    spellcasting_member_occurrence: int
    casting_member_ordinal: int
    casting_member_occurrence: int
    raw_header: str
    tradition: str
    dc: int
    attack: int | None
    focus_points: int | None
    field_order: tuple[str, ...]
    entries_member_ordinal: int
    entry_groups: tuple[_EntryGroupData, ...]
    usages: tuple[_MentionData, ...]
    duplicate_name_groups: tuple[_DuplicateGroupData, ...]


@dataclass(frozen=True, slots=True)
class _CatalogData:
    provider: VerifiedSourceSelection = field(repr=False, compare=False)
    catalog_block_id: str
    name: str
    normalized_name: str
    rank: int
    kind: str
    actions: str | None
    cast: str | None
    traditions: tuple[str, ...]
    field_shape: tuple[str, ...]


def _bind_closed_primitives() -> tuple[Callable[..., Any], ...]:
    """Bind parser and serializer policy away from module rebinding."""

    sha256 = hashlib.sha256
    dumps = json.dumps
    html_unescape = html.unescape
    regex_split = re.split
    tag_re = _TAG_RE
    italic_name_re = _ITALIC_NAME_RE
    at_will_re = _AT_WILL_RE
    apostrophe_translation = str.maketrans({"’": "'", "‘": "'"})
    raw_object_type = RawSourceObject
    raw_array_type = RawSourceArray
    raw_member_type = RawSourceMember
    source_receipt_serializer = SourceReceipt.as_serialized
    decimal_parser = parse_decimal_integer
    source_error = InnateSpellSourceShapeError
    family_id = FAMILY_ID
    player_core_source_id = PLAYER_CORE_SOURCE_ID

    def canonical_digest(value: object) -> str:
        return sha256(
            dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    def text_sha256(value: str) -> str:
        if type(value) is not str:
            raise TypeError("source text must be exact")
        return sha256(value.encode("utf-8")).hexdigest()

    def raw_wire(value: RawSourceValue) -> Any:
        value_type = type(value)
        if value_type is raw_object_type:
            return {
                "$orderedObject": [
                    [member.key, raw_wire(member.value)]
                    for member in value.members
                ]
            }
        if value_type is raw_array_type:
            return [raw_wire(item) for item in value.items]
        if value is None or value_type in (bool, int, float, str):
            return value
        raise TypeError(
            "verified raw source contains an inexact value: "
            f"{value_type.__name__}"
        )

    def rank_number(
        spelling: str,
        rank_table: tuple[tuple[str, int], ...],
    ) -> int:
        if type(spelling) is not str:
            raise source_error("spell rank must be exact text")
        for candidate, rank in rank_table:
            if spelling == candidate:
                return rank
        raise source_error(
            f"unsupported spell rank spelling: {spelling!r}"
        )

    def normalized_spell_name(value: str) -> str:
        if type(value) is not str:
            raise TypeError("spell name must be exact text")
        without_tags = tag_re.sub("", html_unescape(value))
        typography_normalized = without_tags.translate(
            apostrophe_translation
        )
        return " ".join(typography_normalized.split()).casefold()

    def split_top_level_commas(
        value: str,
    ) -> tuple[tuple[str, int, int], ...]:
        if type(value) is not str:
            raise source_error(
                "spell entry values must be exact strings"
            )
        depth = 0
        starts = [0]
        for index, character in enumerate(value):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth < 0:
                    raise source_error(
                        f"unbalanced spell annotation: {value!r}"
                    )
            elif character == "," and depth == 0:
                starts.append(index + 1)
        if depth:
            raise source_error(
                f"unbalanced spell annotation: {value!r}"
            )
        boundaries = tuple(position - 1 for position in starts[1:]) + (
            len(value),
        )
        result: list[tuple[str, int, int]] = []
        for start, end in zip(starts, boundaries):
            while start < end and value[start].isspace():
                start += 1
            while end > start and value[end - 1].isspace():
                end -= 1
            if start == end:
                raise source_error(f"empty spell mention: {value!r}")
            result.append((value[start:end], start, end))
        return tuple(result)

    def parsed_chunk(value: str) -> tuple[str, str, MarkupKind]:
        if type(value) is not str:
            raise TypeError("spell chunk must be exact text")
        italic = italic_name_re.fullmatch(value)
        if italic is not None:
            name = italic.group("name").strip()
            annotation = italic.group("tail").strip()
            markup: MarkupKind = "italic"
        else:
            boundary = value.find("(")
            name = (value if boundary < 0 else value[:boundary]).strip()
            annotation = (
                "" if boundary < 0 else value[boundary:]
            ).strip()
            markup = "plain"
        if not name:
            raise source_error(
                f"spell mention has no name: {value!r}"
            )
        return name, annotation, markup

    def qualifier_fragments(
        annotation: str,
        usage_kind: UsageKind,
    ) -> tuple[str, ...]:
        if type(annotation) is not str:
            raise TypeError("spell annotation must be exact text")
        if not annotation:
            return ()
        inner = annotation
        if inner.startswith("(") and inner.endswith(")"):
            inner = inner[1:-1]
        parts = tuple(
            part.strip()
            for part in regex_split(r"[,;]", inner)
            if part.strip()
        )
        if usage_kind == "at-will":
            return tuple(
                part for part in parts
                if part.casefold() != "at will"
            )
        return parts

    def source_strings(value: RawSourceValue) -> tuple[str, ...]:
        if type(value) is str:
            return (value,)
        if type(value) is raw_array_type:
            result: list[str] = []
            for item in value.items:
                result.extend(source_strings(item))
            return tuple(result)
        return ()

    def unique_member(
        value: RawSourceObject,
        key: str,
    ) -> tuple[int, RawSourceMember]:
        if type(value) is not raw_object_type or type(key) is not str:
            raise TypeError(
                "unique source-member lookup requires exact types"
            )
        matches = tuple(
            (index, member)
            for index, member in enumerate(value.members)
            if type(member) is raw_member_type and member.key == key
        )
        if len(matches) != 1:
            raise source_error(
                f"source block requires one exact {key!r} member; "
                f"found {len(matches)}"
            )
        return matches[0]

    def optional_member(
        value: RawSourceObject,
        key: str,
    ) -> RawSourceValue | None:
        if type(value) is not raw_object_type or type(key) is not str:
            raise TypeError(
                "optional source-member lookup requires exact types"
            )
        matches = tuple(
            member.value
            for member in value.members
            if type(member) is raw_member_type and member.key == key
        )
        if len(matches) > 1:
            raise source_error(
                f"source block has duplicate {key!r} members"
            )
        return matches[0] if matches else None

    def source_integer(
        value: RawSourceValue,
        label: str,
        *,
        positive: bool = False,
        nonnegative: bool = False,
    ) -> int:
        if type(value) is not str:
            raise source_error(
                f"{label} must be exact decimal text"
            )
        result = decimal_parser(value)
        if result is None:
            raise source_error(
                f"{label} must be a signed 64-bit ASCII decimal string"
            )
        if positive and result <= 0:
            raise source_error(f"{label} must be positive")
        if nonnegative and result < 0:
            raise source_error(f"{label} must be nonnegative")
        return result

    def mention_wire(value: _MentionData) -> dict[str, Any]:
        return {
            "address": {
                "sourceMentionOrdinal": value.source_mention_ordinal,
                "usageOrdinal": value.usage_ordinal,
                "entryPairOrdinal": value.entry_pair_ordinal,
                "entryKeyOccurrence": value.entry_key_occurrence,
                "valueItemOrdinal": value.value_item_ordinal,
                "mentionOrdinal": value.mention_ordinal,
                "charStart": value.char_start,
                "charEnd": value.char_end,
            },
            "entryKey": value.entry_key,
            "entryKind": value.entry_kind,
            "constantEntryRole": value.constant_entry_role,
            "tradition": value.tradition,
            "sourceRank": value.source_rank,
            "usageKind": value.usage_kind,
            "rawScalar": value.raw_scalar,
            "rawScalarSha256": value.raw_scalar_sha256,
            "rawChunk": value.raw_chunk,
            "rawName": value.raw_name,
            "normalizedName": value.normalized_name,
            "rawAnnotation": value.raw_annotation,
            "qualifierFragments": list(value.qualifier_fragments),
            "markup": value.markup,
        }

    def mechanic_types(value: _CompiledData) -> tuple[str, ...]:
        kinds = {mention.usage_kind for mention in value.usages}
        result: list[str] = []
        if "at-will" in kinds:
            result.append("innate-at-will-spell")
        if "constant" in kinds:
            result.append("constant-spell")
        if "context-cantrip" in kinds:
            result.append("innate-cantrip")
        return tuple(result)

    def compiled_wire(value: _CompiledData) -> dict[str, Any]:
        return {
            "compileSupported": True,
            "linkSupported": False,
            "runtimeSupported": False,
            "registryStatus": "unregistered",
            "familyId": family_id,
            "mechanicTypes": list(mechanic_types(value)),
            "source": source_receipt_serializer(
                value.consumer.receipt
            ),
            "creatureName": value.creature_name,
            "spellcastingMemberOrdinal": (
                value.spellcasting_member_ordinal
            ),
            "spellcastingMemberOccurrence": (
                value.spellcasting_member_occurrence
            ),
            "castingMemberOrdinal": value.casting_member_ordinal,
            "castingMemberOccurrence": value.casting_member_occurrence,
            "casting": {
                "rawHeader": value.raw_header,
                "tradition": value.tradition,
                "dc": value.dc,
                "attack": value.attack,
                "focusPoints": value.focus_points,
                "fieldOrder": list(value.field_order),
                "entriesMemberOrdinal": value.entries_member_ordinal,
            },
            "entryGroups": [
                {
                    "entryPairOrdinal": group.entry_pair_ordinal,
                    "entryKeyOccurrence": group.entry_key_occurrence,
                    "entryKind": group.entry_kind,
                    "constantEntryRole": group.constant_entry_role,
                    "rank": group.rank,
                    "rawValueSha256": group.raw_value_sha256,
                    "rawMember": {
                        "key": group.raw_key,
                        "value": raw_wire(group.raw_value),
                    },
                    "mentions": [
                        mention_wire(mention)
                        for mention in group.mentions
                    ],
                }
                for group in value.entry_groups
            ],
            "usages": [
                mention_wire(mention) for mention in value.usages
            ],
            "duplicateNameGroups": [
                {
                    "normalizedName": group.normalized_name,
                    "appearanceCount": len(group.mention_ordinals),
                    "usageKinds": list(group.usage_kinds),
                    "sourceMentionOrdinals": list(
                        group.mention_ordinals
                    ),
                }
                for group in value.duplicate_name_groups
            ],
        }

    def catalog_record_wire(value: _CatalogData) -> dict[str, Any]:
        return {
            "catalogBlockId": value.catalog_block_id,
            "source": source_receipt_serializer(
                value.provider.receipt
            ),
            "name": value.name,
            "normalizedName": value.normalized_name,
            "rank": value.rank,
            "kind": value.kind,
            "actions": value.actions,
            "cast": value.cast,
            "traditions": list(value.traditions),
            "fieldShape": list(value.field_shape),
        }

    def catalog_wire(
        records: tuple[_CatalogData, ...],
    ) -> dict[str, Any]:
        serialized = [
            catalog_record_wire(record) for record in records
        ]
        return {
            "schema": 1,
            "sourceId": player_core_source_id,
            "spellBlocks": len(records),
            "uniqueNormalizedNames": len(
                {record.normalized_name for record in records}
            ),
            "records": serialized,
            "catalogDigest": canonical_digest(serialized),
        }

    return (
        canonical_digest,
        text_sha256,
        raw_wire,
        rank_number,
        normalized_spell_name,
        split_top_level_commas,
        parsed_chunk,
        qualifier_fragments,
        source_strings,
        unique_member,
        optional_member,
        source_integer,
        mention_wire,
        mechanic_types,
        compiled_wire,
        catalog_record_wire,
        catalog_wire,
    )


(
    _canonical_digest,
    _text_sha256,
    _raw_wire,
    _rank_number,
    _normalized_spell_name,
    _split_top_level_commas,
    _parsed_chunk,
    _qualifier_fragments,
    _source_strings,
    _unique_member,
    _optional_member,
    _source_integer,
    _mention_wire,
    _mechanic_types,
    _compiled_wire,
    _catalog_record_wire,
    _catalog_wire,
) = _bind_closed_primitives()
del _bind_closed_primitives


def _validation_gateway(
    label: str,
) -> tuple[
    Callable[[Callable[[object], Any]], None],
    Callable[[object], Any],
]:
    validator: Callable[[object], Any] | None = None

    def bind(value: Callable[[object], Any]) -> None:
        nonlocal validator
        if validator is not None:
            raise RuntimeError(f"{label} validator is already bound")
        validator = value

    def validate(value: object) -> Any:
        if validator is None:
            raise RuntimeError(f"{label} validator is not bound")
        return validator(value)

    return bind, validate


def _validated_method(
    validator: Callable[[object], Any],
    serializer: Callable[[Any], dict[str, Any]],
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    def decorate(
        method: Callable[..., dict[str, Any]],
    ) -> Callable[..., dict[str, Any]]:
        def validated(instance: object) -> dict[str, Any]:
            return method(instance, validator(instance), serializer)

        return validated

    return decorate


_bind_patch_validator, _patch_validator = _validation_gateway(
    "innate spell patch"
)
_bind_catalog_validator, _catalog_validator = _validation_gateway(
    "innate spell catalog"
)
_bind_linked_validator, _linked_validator = _validation_gateway(
    "linked innate spell patch"
)

_patch_public_method = _validated_method(
    _patch_validator,
    _compiled_wire,
)
_catalog_public_method = _validated_method(
    _catalog_validator,
    _catalog_wire,
)


class _ClosedArtifactType(type):
    """Prevent post-definition replacement of artifact class contracts."""

    def __setattr__(
        cls,
        _name: str,
        _value: object,
    ) -> None:
        raise TypeError("innate spell artifact classes are immutable")

    def __delattr__(cls, _name: str) -> None:
        raise TypeError("innate spell artifact classes are immutable")


@final
class InnateSpellcastingPatch(metaclass=_ClosedArtifactType):
    """One authority-derived compile-only innate spellcasting carrier."""

    __slots__ = (
        "_authority",
        "_consumer",
        "_source_receipt_digest",
        "_structure_sha256",
        "__weakref__",
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "InnateSpellcastingPatch can only be created by "
            "compile_innate_spell_usage()"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("InnateSpellcastingPatch subclasses are unsupported")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("InnateSpellcastingPatch is immutable")

    def __delattr__(self, _name: str) -> None:
        raise TypeError("InnateSpellcastingPatch is immutable")

    def __getattribute__(
        self,
        name: str,
        _base_getattribute: Callable[[object, str], Any]
        = object.__getattribute__,
        _validate: Callable[[object], Any] = _patch_validator,
        _serialize: Callable[[Any], dict[str, Any]] = _compiled_wire,
    ) -> Any:
        if name == "as_serialized":
            def serialize() -> dict[str, Any]:
                return _serialize(_validate(self))

            return serialize
        return _base_getattribute(self, name)

    @_patch_public_method
    def as_serialized(
        self,
        value: _CompiledData,
        serializer: Callable[[_CompiledData], dict[str, Any]],
    ) -> dict[str, Any]:
        return serializer(value)

    def __copy__(self) -> InnateSpellcastingPatch:
        raise TypeError("InnateSpellcastingPatch cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> InnateSpellcastingPatch:
        raise TypeError("InnateSpellcastingPatch cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("InnateSpellcastingPatch cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("InnateSpellcastingPatch cannot be pickled")


@final
class SpellCatalogIndex(metaclass=_ClosedArtifactType):
    """The exact 491-record Player Core spell provider index."""

    __slots__ = (
        "_authority",
        "_providers",
        "_provider_receipt_digests",
        "_catalog_sha256",
        "__weakref__",
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "SpellCatalogIndex can only be created by "
            "build_spell_catalog()"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("SpellCatalogIndex subclasses are unsupported")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("SpellCatalogIndex is immutable")

    def __delattr__(self, _name: str) -> None:
        raise TypeError("SpellCatalogIndex is immutable")

    def __getattribute__(
        self,
        name: str,
        _base_getattribute: Callable[[object, str], Any]
        = object.__getattribute__,
        _validate: Callable[[object], Any] = _catalog_validator,
        _serialize: Callable[[Any], dict[str, Any]] = _catalog_wire,
    ) -> Any:
        if name == "as_serialized":
            def serialize() -> dict[str, Any]:
                return _serialize(_validate(self))

            return serialize
        return _base_getattribute(self, name)

    @_catalog_public_method
    def as_serialized(
        self,
        value: tuple[_CatalogData, ...],
        serializer: Callable[
            [tuple[_CatalogData, ...]],
            dict[str, Any],
        ],
    ) -> dict[str, Any]:
        return serializer(value)

    def __copy__(self) -> SpellCatalogIndex:
        raise TypeError("SpellCatalogIndex cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> SpellCatalogIndex:
        raise TypeError("SpellCatalogIndex cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("SpellCatalogIndex cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("SpellCatalogIndex cannot be pickled")


def _linked_public_method(
    validator: Callable[[object], dict[str, Any]],
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    def decorate(
        method: Callable[..., dict[str, Any]],
    ) -> Callable[..., dict[str, Any]]:
        def validated(instance: object) -> dict[str, Any]:
            value = validator(instance)
            return method(instance, value)

        return validated

    return decorate


_linked_method = _linked_public_method(_linked_validator)


@final
class LinkedInnateSpellcastingPatch(metaclass=_ClosedArtifactType):
    """One verified compile/link artifact; runtime remains unavailable."""

    __slots__ = (
        "_authority",
        "_compiled",
        "_catalog",
        "_compiled_sha256",
        "_catalog_sha256",
        "_linked_sha256",
        "__weakref__",
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "LinkedInnateSpellcastingPatch can only be created by "
            "link_innate_spellcasting_patch()"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError(
            "LinkedInnateSpellcastingPatch subclasses are unsupported"
        )

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("LinkedInnateSpellcastingPatch is immutable")

    def __delattr__(self, _name: str) -> None:
        raise TypeError("LinkedInnateSpellcastingPatch is immutable")

    def __getattribute__(
        self,
        name: str,
        _base_getattribute: Callable[[object, str], Any]
        = object.__getattribute__,
        _validate: Callable[[object], dict[str, Any]]
        = _linked_validator,
    ) -> Any:
        if name == "as_serialized":
            def serialize() -> dict[str, Any]:
                return _validate(self)

            return serialize
        return _base_getattribute(self, name)

    @_linked_method
    def as_serialized(
        self,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return value

    def __copy__(self) -> LinkedInnateSpellcastingPatch:
        raise TypeError("LinkedInnateSpellcastingPatch cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> LinkedInnateSpellcastingPatch:
        raise TypeError("LinkedInnateSpellcastingPatch cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("LinkedInnateSpellcastingPatch cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("LinkedInnateSpellcastingPatch cannot be pickled")


del _patch_public_method
del _catalog_public_method
del _linked_method


def _build_implementation() -> tuple[
    Callable[
        [VerifiedSourceSelection, SourceAuthorityAdapter],
        InnateSpellcastingPatch | None,
    ],
    Callable[
        [tuple[VerifiedSourceSelection, ...], SourceAuthorityAdapter],
        SpellCatalogIndex,
    ],
    Callable[
        [
            InnateSpellcastingPatch,
            SpellCatalogIndex,
            SourceAuthorityAdapter,
        ],
        LinkedInnateSpellcastingPatch,
    ],
    Callable[[object], _CompiledData],
    Callable[[object], tuple[_CatalogData, ...]],
    Callable[[object], dict[str, Any]],
]:
    _module_bindings = globals()
    (
        FAMILY_ID,
        MONSTER_CORE_SOURCE_ID,
        PLAYER_CORE_SOURCE_ID,
        MECHANIC_TYPES,
        EXPECTED_PLAYER_CORE_SPELLS,
        _INNATE_HEADER_RE,
        _RANK_RE,
        _CANTRIP_RE,
        _CONSTANT_RE,
        _CONSTANT_CONTINUATION_RE,
        _AT_WILL_RE,
        _ACCEPTED_FIELD_ORDERS,
        _RANK_TABLE,
        _canonical_digest,
        _text_sha256,
        _rank_number,
        _normalized_spell_name,
        _split_top_level_commas,
        _parsed_chunk,
        _qualifier_fragments,
        _source_strings,
        _unique_member,
        _optional_member,
        _source_integer,
        _mention_wire,
        _compiled_wire,
        _catalog_record_wire,
        _catalog_wire,
        raw_source_sha256,
        RawSourceArray,
        RawSourceMember,
        RawSourceObject,
        RawMemberStep,
        RuleRequirement,
        SourceAuthorityAdapter,
        VerifiedRuleReceipt,
        VerifiedSourceSelection,
        InnateSpellSourceShapeError,
        SpellCatalogAmbiguityError,
        SpellCatalogSemanticError,
        InnateSpellArtifactError,
        _MentionData,
        _EntryGroupData,
        _DuplicateGroupData,
        _CompiledData,
        _CatalogData,
        InnateSpellcastingPatch,
        SpellCatalogIndex,
        LinkedInnateSpellcastingPatch,
        WeakKeyDictionary,
    ) = tuple(
        _module_bindings[name]
        for name in (
            "FAMILY_ID",
            "MONSTER_CORE_SOURCE_ID",
            "PLAYER_CORE_SOURCE_ID",
            "MECHANIC_TYPES",
            "EXPECTED_PLAYER_CORE_SPELLS",
            "_INNATE_HEADER_RE",
            "_RANK_RE",
            "_CANTRIP_RE",
            "_CONSTANT_RE",
            "_CONSTANT_CONTINUATION_RE",
            "_AT_WILL_RE",
            "_ACCEPTED_FIELD_ORDERS",
            "_RANK_TABLE",
            "_canonical_digest",
            "_text_sha256",
            "_rank_number",
            "_normalized_spell_name",
            "_split_top_level_commas",
            "_parsed_chunk",
            "_qualifier_fragments",
            "_source_strings",
            "_unique_member",
            "_optional_member",
            "_source_integer",
            "_mention_wire",
            "_compiled_wire",
            "_catalog_record_wire",
            "_catalog_wire",
            "raw_source_sha256",
            "RawSourceArray",
            "RawSourceMember",
            "RawSourceObject",
            "RawMemberStep",
            "RuleRequirement",
            "SourceAuthorityAdapter",
            "VerifiedRuleReceipt",
            "VerifiedSourceSelection",
            "InnateSpellSourceShapeError",
            "SpellCatalogAmbiguityError",
            "SpellCatalogSemanticError",
            "InnateSpellArtifactError",
            "_MentionData",
            "_EntryGroupData",
            "_DuplicateGroupData",
            "_CompiledData",
            "_CatalogData",
            "InnateSpellcastingPatch",
            "SpellCatalogIndex",
            "LinkedInnateSpellcastingPatch",
            "WeakKeyDictionary",
        )
    )
    patch_type = InnateSpellcastingPatch
    catalog_type = SpellCatalogIndex
    linked_type = LinkedInnateSpellcastingPatch
    authority_validate_selection_method = (
        SourceAuthorityAdapter.validate_selection
    )
    authority_resolve_rule_method = SourceAuthorityAdapter.resolve_rule
    authority_require_shared_method = (
        SourceAuthorityAdapter.require_shared_authority
    )
    type_getattribute = type.__getattribute__
    authority_class_contract = tuple(
        type_getattribute(SourceAuthorityAdapter, "__dict__").items()
    )

    def require_authority_class_contract() -> None:
        try:
            current = type_getattribute(
                SourceAuthorityAdapter,
                "__dict__",
            )
            if (
                len(current) != len(authority_class_contract)
                or any(
                    name not in current or current[name] is not expected
                    for name, expected in authority_class_contract
                )
            ):
                raise InnateSpellArtifactError(
                    "source authority class contract changed"
                )
        except InnateSpellArtifactError:
            raise
        except (AttributeError, TypeError) as failure:
            raise InnateSpellArtifactError(
                "source authority class contract is invalid"
            ) from failure

    def authority_validate_selection(
        authority: SourceAuthorityAdapter,
        selection: VerifiedSourceSelection,
    ) -> VerifiedSourceSelection:
        require_authority_class_contract()
        result = authority_validate_selection_method(
            authority,
            selection,
        )
        require_authority_class_contract()
        return result

    def authority_resolve_rule(
        authority: SourceAuthorityAdapter,
        requirement: RuleRequirement,
    ) -> VerifiedRuleReceipt:
        require_authority_class_contract()
        result = authority_resolve_rule_method(
            authority,
            requirement,
        )
        require_authority_class_contract()
        return result

    def authority_require_shared(
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
        providers: tuple[VerifiedRuleReceipt, ...],
    ) -> None:
        require_authority_class_contract()
        authority_require_shared_method(
            authority,
            consumer,
            providers,
        )
        require_authority_class_contract()
    verified_rule_serializer = VerifiedRuleReceipt.as_serialized
    patch_registry: WeakKeyDictionary[
        InnateSpellcastingPatch,
        tuple[
            SourceAuthorityAdapter,
            VerifiedSourceSelection,
            str,
            str,
        ],
    ] = WeakKeyDictionary()
    catalog_registry: WeakKeyDictionary[
        SpellCatalogIndex,
        tuple[
            SourceAuthorityAdapter,
            tuple[VerifiedSourceSelection, ...],
            tuple[str, ...],
            str,
        ],
    ] = WeakKeyDictionary()
    linked_registry: WeakKeyDictionary[
        LinkedInnateSpellcastingPatch,
        tuple[
            SourceAuthorityAdapter,
            InnateSpellcastingPatch,
            SpellCatalogIndex,
            str,
            str,
            str,
        ],
    ] = WeakKeyDictionary()
    rank_table = tuple(_RANK_TABLE)
    accepted_field_orders = tuple(_ACCEPTED_FIELD_ORDERS)
    mechanic_types = tuple(MECHANIC_TYPES)
    catalog_sections = (
        "core-pc1:ch07-spells",
        "core-pc1:ch07-focus-spells",
        "core-pc1:ch07-rituals",
    )

    rule_specs = (
        (
            "at-will",
            "core-mc1:ability-glossary#at-will-spells",
            "core-mc1",
            "358.2",
            (("^.ability", 4),),
            "6af5f9b5c3f42af01ac8a08cf16d18efbf1075a85105a3b6d70825ecc69298cd",
        ),
        (
            "constant",
            "core-mc1:ability-glossary#constant-spells",
            "core-mc1",
            "358.2",
            (("^.ability", 8),),
            "1ae97306f019492ccbdf0eec48d41da195226e9c0ea03cd0244ed463313d20da",
        ),
        (
            "cantrip",
            "core-pc1:cantrips",
            "core-pc1",
            "298.1",
            (),
            "636a20b16e1981ef23673864f2eeb68471083cc01847580a193b80d9d9fecd20",
        ),
        (
            "innate",
            "core-pc1:innate-spells",
            "core-pc1",
            "298.7",
            (),
            "f2d392fec9d7ad71c8c772594f0ab782403e51593dc0c0751bff4d13c91d04d0",
        ),
        (
            "casting",
            "core-pc1:casting-spells",
            "core-pc1",
            "299.2",
            (),
            "e72af12260d392ccd01ddb21c5e0ac2d5c77b75b4cd55be9145c6cc1a36ad21b",
        ),
        (
            "durations",
            "core-pc1:durations",
            "core-pc1",
            "302.3",
            (),
            "884efa757814676d3724cff31135986761164140dc3501883c1c5f3a0c92e789",
        ),
    )
    dependency_specs = (
        (
            "cast-a-spell-action-economy",
            "encounter-action-economy",
            "consume the verified spell's exact normal Actions or Cast activity",
        ),
        (
            "spell-target-defense-effect-resolution",
            "spell-target",
            "targeting, areas, defenses, spell attacks, saves, and spell effects",
        ),
        (
            "long-cast-mode-and-interruption",
            "encounter-action-economy",
            "minute/hour casting outside encounters plus disruption and loss",
        ),
        (
            "spell-cast-action-metadata",
            "encounter-action-economy",
            "an authoritative Player Core Actions or Cast source field",
        ),
        (
            "constant-initial-effect-state",
            "constant-effect-state",
            "initialize the verified effect without performing Cast a Spell",
        ),
        (
            "constant-unlimited-duration",
            "duration-state",
            "unlimited duration with Dismiss and source-specific termination",
        ),
        (
            "constant-counteract-deactivation",
            "constant-effect-state",
            "counteract removes the active effect without removing availability",
        ),
        (
            "constant-reactivation-cast",
            "encounter-action-economy",
            "reactivate a counteracted Constant spell using normal "
            "spellcasting Actions or Cast",
        ),
    )
    dependencies_by_id = {
        item[0]: item for item in dependency_specs
    }

    def require_consumer(
        consumer: object,
        authority: object,
    ) -> VerifiedSourceSelection:
        if type(authority) is not SourceAuthorityAdapter:
            raise TypeError(
                "innate spell compilation requires an exact "
                "SourceAuthorityAdapter"
            )
        if type(consumer) is not VerifiedSourceSelection:
            raise TypeError(
                "innate spell compilation requires an exact "
                "VerifiedSourceSelection"
            )
        authority_validate_selection(authority, consumer)
        address = consumer.address
        if (
            address.source_id != MONSTER_CORE_SOURCE_ID
            or address.selection_path != ()
            or address.span is not None
            or type(consumer.raw_value) is not RawSourceObject
            or type(consumer.selected_value) is not RawSourceObject
            or consumer.raw_value != consumer.selected_value
            or consumer.value_sha256 != consumer.block_sha256
        ):
            raise InnateSpellSourceShapeError(
                "consumer must select one exact whole core-mc1 creature block"
            )
        return consumer

    def parse_entry_kind(
        raw_key: str,
    ) -> tuple[EntryKind, int | None] | None:
        ranked = _RANK_RE.fullmatch(raw_key)
        if ranked is not None:
            return (
                "ranked",
                _rank_number(ranked.group("rank"), rank_table),
            )
        cantrip = _CANTRIP_RE.fullmatch(raw_key)
        if cantrip is not None:
            return (
                "cantrip",
                _rank_number(cantrip.group("rank"), rank_table),
            )
        constant = _CONSTANT_RE.fullmatch(raw_key)
        if constant is not None:
            spelling = constant.group("rank")
            return (
                "constant",
                (
                    _rank_number(spelling, rank_table)
                    if spelling is not None
                    else None
                ),
            )
        return None

    def mention_values(
        *,
        raw_value: RawSourceValue,
        entry_key: str | None,
        entry_kind: EntryKind,
        constant_entry_role: ConstantEntryRole | None,
        tradition: str,
        rank: int | None,
        entry_pair_ordinal: int | None,
        entry_key_occurrence: int | None,
        source_mention_start: int,
        usage_start: int,
    ) -> tuple[tuple[_MentionData, ...], int, int]:
        if type(raw_value) is str:
            scalars = ((None, raw_value),)
        elif type(raw_value) is RawSourceArray:
            if any(type(item) is not str for item in raw_value.items):
                raise InnateSpellSourceShapeError(
                    "spell entry arrays must contain only exact strings"
                )
            scalars = tuple(enumerate(raw_value.items))
        else:
            raise InnateSpellSourceShapeError(
                "spell entry value must be a string or exact array"
            )
        source_mention_ordinal = source_mention_start
        usage_ordinal = usage_start
        mentions: list[_MentionData] = []
        for item_ordinal, scalar in scalars:
            parsed: list[
                tuple[int, str, int, int, str, str, MarkupKind]
            ] = []
            for mention_ordinal, (chunk, start, end) in enumerate(
                _split_top_level_commas(scalar)
            ):
                name, annotation, markup = _parsed_chunk(chunk)
                parsed.append(
                    (
                        mention_ordinal,
                        chunk,
                        start,
                        end,
                        name,
                        annotation,
                        markup,
                    )
                )
            if len({item[6] for item in parsed}) > 1:
                raise InnateSpellSourceShapeError(
                    "one packed scalar cannot mix italic and plain names"
                )
            for (
                mention_ordinal,
                chunk,
                start,
                end,
                name,
                annotation,
                markup,
            ) in parsed:
                marker_count = len(_AT_WILL_RE.findall(annotation))
                if marker_count > 1:
                    raise InnateSpellSourceShapeError(
                        "spell mention has multiple at-will markers"
                    )
                if entry_kind == "constant":
                    usage_kind: UsageKind = "constant"
                elif entry_kind == "cantrip":
                    usage_kind = "context-cantrip"
                elif marker_count == 1:
                    usage_kind = "at-will"
                else:
                    usage_kind = "limited"
                current_usage_ordinal = (
                    None if usage_kind == "limited" else usage_ordinal
                )
                mentions.append(
                    _MentionData(
                        source_mention_ordinal=source_mention_ordinal,
                        usage_ordinal=current_usage_ordinal,
                        entry_pair_ordinal=entry_pair_ordinal,
                        entry_key_occurrence=entry_key_occurrence,
                        value_item_ordinal=item_ordinal,
                        mention_ordinal=mention_ordinal,
                        char_start=start,
                        char_end=end,
                        entry_key=entry_key,
                        entry_kind=entry_kind,
                        constant_entry_role=constant_entry_role,
                        tradition=tradition,
                        source_rank=rank,
                        usage_kind=usage_kind,
                        raw_scalar=scalar,
                        raw_scalar_sha256=_text_sha256(scalar),
                        raw_chunk=chunk,
                        raw_name=name,
                        normalized_name=_normalized_spell_name(name),
                        raw_annotation=annotation,
                        qualifier_fragments=_qualifier_fragments(
                            annotation,
                            usage_kind,
                        ),
                        markup=markup,
                    )
                )
                source_mention_ordinal += 1
                if current_usage_ordinal is not None:
                    usage_ordinal += 1
        return tuple(mentions), source_mention_ordinal, usage_ordinal

    def parse_casting(
        *,
        consumer: VerifiedSourceSelection,
        creature_name: str,
        spellcasting_member_ordinal: int,
        spellcasting_member_occurrence: int,
        casting_member_ordinal: int,
        casting_member_occurrence: int,
        raw_header: str,
        casting_block: RawSourceObject,
    ) -> _CompiledData | None:
        header = _INNATE_HEADER_RE.fullmatch(raw_header)
        if header is None:
            return None
        tradition = header.group("tradition").casefold()
        field_order = tuple(
            member.key for member in casting_block.members
        )
        if field_order not in accepted_field_orders:
            raise InnateSpellSourceShapeError(
                f"unsupported casting field order: {field_order!r}"
            )
        _, dc_member = _unique_member(casting_block, "DC")
        entries_ordinal, entries_member = _unique_member(
            casting_block,
            "Entries",
        )
        dc = _source_integer(
            dc_member.value,
            "casting DC",
            positive=True,
        )
        attack_value = _optional_member(casting_block, "Attack")
        attack = (
            _source_integer(attack_value, "casting Attack")
            if attack_value is not None
            else None
        )
        focus_value = _optional_member(
            casting_block,
            "Focus Points",
        )
        focus_points = (
            _source_integer(
                focus_value,
                "casting Focus Points",
                nonnegative=True,
            )
            if focus_value is not None
            else None
        )

        groups: list[_EntryGroupData] = []
        unknown_entries: list[str] = []
        source_mention_ordinal = 0
        usage_ordinal = 0
        entries = entries_member.value
        if type(entries) is str:
            mentions, source_mention_ordinal, usage_ordinal = (
                mention_values(
                    raw_value=entries,
                    entry_key=None,
                    entry_kind="unranked",
                    constant_entry_role=None,
                    tradition=tradition,
                    rank=None,
                    entry_pair_ordinal=None,
                    entry_key_occurrence=None,
                    source_mention_start=source_mention_ordinal,
                    usage_start=usage_ordinal,
                )
            )
            if (
                len(mentions) != 1
                or mentions[0].usage_kind != "at-will"
            ):
                raise InnateSpellSourceShapeError(
                    "scalar Entries must be the reviewed single "
                    "unranked at-will shape"
                )
            groups.append(
                _EntryGroupData(
                    entry_pair_ordinal=None,
                    entry_key_occurrence=None,
                    raw_key="Entries",
                    raw_value=entries,
                    raw_value_sha256=raw_source_sha256(entries),
                    entry_kind="unranked",
                    constant_entry_role=None,
                    rank=None,
                    mentions=mentions,
                )
            )
        elif type(entries) is RawSourceObject:
            key_occurrences: dict[str, int] = {}
            constant_group_open = False
            for entry_pair_ordinal, entry_member in enumerate(
                entries.members
            ):
                if type(entry_member) is not RawSourceMember:
                    raise InnateSpellSourceShapeError(
                        "Entries contains an inexact member"
                    )
                occurrence = key_occurrences.get(entry_member.key, 0)
                key_occurrences[entry_member.key] = occurrence + 1
                parsed_kind = parse_entry_kind(entry_member.key)
                continuation = _CONSTANT_CONTINUATION_RE.fullmatch(
                    entry_member.key
                )
                constant_role: ConstantEntryRole | None = None
                if continuation is not None:
                    if not constant_group_open:
                        raise InnateSpellSourceShapeError(
                            "orphan or nonadjacent Constant rank "
                            f"continuation: {entry_member.key!r}"
                        )
                    parsed_kind = (
                        "constant",
                        _rank_number(
                            continuation.group("rank"),
                            rank_table,
                        ),
                    )
                    constant_role = "rank-continuation"
                if parsed_kind is None:
                    constant_group_open = False
                    if entry_member.key.startswith("Constant") or any(
                        _AT_WILL_RE.search(item)
                        for item in _source_strings(entry_member.value)
                    ):
                        raise InnateSpellSourceShapeError(
                            "target usage has unsupported entry key: "
                            f"{entry_member.key!r}"
                        )
                    unknown_entries.append(entry_member.key)
                    continue
                entry_kind, rank = parsed_kind
                if entry_kind == "constant" and constant_role is None:
                    constant_role = "group-header"
                constant_group_open = entry_kind == "constant"
                (
                    mentions,
                    source_mention_ordinal,
                    usage_ordinal,
                ) = mention_values(
                    raw_value=entry_member.value,
                    entry_key=entry_member.key,
                    entry_kind=entry_kind,
                    constant_entry_role=constant_role,
                    tradition=tradition,
                    rank=rank,
                    entry_pair_ordinal=entry_pair_ordinal,
                    entry_key_occurrence=occurrence,
                    source_mention_start=source_mention_ordinal,
                    usage_start=usage_ordinal,
                )
                groups.append(
                    _EntryGroupData(
                        entry_pair_ordinal=entry_pair_ordinal,
                        entry_key_occurrence=occurrence,
                        raw_key=entry_member.key,
                        raw_value=entry_member.value,
                        raw_value_sha256=raw_source_sha256(
                            entry_member.value
                        ),
                        entry_kind=entry_kind,
                        constant_entry_role=constant_role,
                        rank=rank,
                        mentions=mentions,
                    )
                )
        else:
            raise InnateSpellSourceShapeError(
                "Entries must be an ordered object or reviewed scalar"
            )
        all_mentions = tuple(
            mention for group in groups for mention in group.mentions
        )
        if not any(
            mention.usage_kind in ("at-will", "constant")
            for mention in all_mentions
        ):
            return None
        if unknown_entries:
            raise InnateSpellSourceShapeError(
                "target casting block has unsupported entry keys: "
                f"{tuple(unknown_entries)!r}"
            )
        usages = tuple(
            mention
            for mention in all_mentions
            if mention.usage_kind != "limited"
        )
        names: list[str] = []
        grouped: dict[str, list[_MentionData]] = {}
        for mention in all_mentions:
            if mention.normalized_name not in grouped:
                names.append(mention.normalized_name)
                grouped[mention.normalized_name] = []
            grouped[mention.normalized_name].append(mention)
        duplicate_groups = tuple(
            _DuplicateGroupData(
                normalized_name=name,
                mention_ordinals=tuple(
                    mention.source_mention_ordinal
                    for mention in grouped[name]
                ),
                usage_kinds=tuple(
                    mention.usage_kind for mention in grouped[name]
                ),
            )
            for name in names
            if len(grouped[name]) > 1
        )
        return _CompiledData(
            consumer=consumer,
            creature_name=creature_name,
            spellcasting_member_ordinal=spellcasting_member_ordinal,
            spellcasting_member_occurrence=(
                spellcasting_member_occurrence
            ),
            casting_member_ordinal=casting_member_ordinal,
            casting_member_occurrence=casting_member_occurrence,
            raw_header=raw_header,
            tradition=tradition,
            dc=dc,
            attack=attack,
            focus_points=focus_points,
            field_order=field_order,
            entries_member_ordinal=entries_ordinal,
            entry_groups=tuple(groups),
            usages=usages,
            duplicate_name_groups=duplicate_groups,
        )

    def compile_structure(
        consumer: VerifiedSourceSelection,
        authority: SourceAuthorityAdapter,
    ) -> _CompiledData | None:
        consumer = require_consumer(consumer, authority)
        creature = consumer.raw_value
        _, name_member = _unique_member(creature, "Name")
        if type(name_member.value) is not str or not name_member.value:
            raise InnateSpellSourceShapeError(
                "creature Name must be exact nonempty text"
            )
        creature_name = name_member.value
        results: list[_CompiledData] = []
        spellcasting_occurrence = 0
        for spellcasting_ordinal, member in enumerate(creature.members):
            if member.key != "Spellcasting":
                continue
            current_spellcasting_occurrence = spellcasting_occurrence
            spellcasting_occurrence += 1
            if type(member.value) is not RawSourceObject:
                raise InnateSpellSourceShapeError(
                    "Spellcasting must be an exact ordered object"
                )
            header_occurrences: dict[str, int] = {}
            for casting_ordinal, casting_member in enumerate(
                member.value.members
            ):
                occurrence = header_occurrences.get(
                    casting_member.key,
                    0,
                )
                header_occurrences[casting_member.key] = occurrence + 1
                if _INNATE_HEADER_RE.fullmatch(
                    casting_member.key
                ) is None:
                    continue
                if type(casting_member.value) is not RawSourceObject:
                    raise InnateSpellSourceShapeError(
                        "innate casting member must be an exact object"
                    )
                parsed = parse_casting(
                    consumer=consumer,
                    creature_name=creature_name,
                    spellcasting_member_ordinal=spellcasting_ordinal,
                    spellcasting_member_occurrence=(
                        current_spellcasting_occurrence
                    ),
                    casting_member_ordinal=casting_ordinal,
                    casting_member_occurrence=occurrence,
                    raw_header=casting_member.key,
                    casting_block=casting_member.value,
                )
                if parsed is not None:
                    results.append(parsed)
        if len(results) > 1:
            raise InnateSpellSourceShapeError(
                "one creature has multiple target innate casting carriers"
            )
        return results[0] if results else None

    def catalog_sort_key(
        provider: VerifiedSourceSelection,
    ) -> tuple[int, tuple[int, ...], str]:
        address = provider.address
        try:
            section_ordinal = catalog_sections.index(
                address.section_id
            )
        except ValueError as failure:
            raise SpellCatalogSemanticError(
                "catalog provider belongs to an unsupported section"
            ) from failure
        source_path = address.target_path + address.carrier_path
        if (
            not source_path
            or any(type(step) is not RawMemberStep for step in source_path)
        ):
            raise SpellCatalogSemanticError(
                "catalog provider requires one exact object-member path"
            )
        return (
            section_ordinal,
            tuple(step.member_ordinal for step in source_path),
            provider.receipt.digest,
        )

    def catalog_structure(
        providers: tuple[VerifiedSourceSelection, ...],
        authority: SourceAuthorityAdapter,
    ) -> tuple[_CatalogData, ...]:
        if type(authority) is not SourceAuthorityAdapter:
            raise TypeError(
                "spell catalog requires an exact SourceAuthorityAdapter"
            )
        if type(providers) is not tuple:
            raise TypeError(
                "spell catalog providers must be one exact tuple"
            )
        if len(providers) != EXPECTED_PLAYER_CORE_SPELLS:
            raise SpellCatalogSemanticError(
                "Player Core spell catalog requires exactly "
                f"{EXPECTED_PLAYER_CORE_SPELLS} verified providers"
            )
        if any(
            type(provider) is not VerifiedSourceSelection
            for provider in providers
        ):
            raise TypeError(
                "spell catalog providers must be exact verified selections"
            )
        ordered = tuple(sorted(providers, key=catalog_sort_key))
        receipt_digests = tuple(
            provider.receipt.digest for provider in ordered
        )
        if len(receipt_digests) != len(set(receipt_digests)):
            raise SpellCatalogSemanticError(
                "spell catalog contains duplicate providers"
            )
        section_ordinals: dict[str, int] = {}
        records: list[_CatalogData] = []
        for provider in ordered:
            authority_validate_selection(authority, provider)
            address = provider.address
            source_path = address.target_path + address.carrier_path
            if (
                address.source_id != PLAYER_CORE_SOURCE_ID
                or address.selection_path != ()
                or address.span is not None
                or type(provider.raw_value) is not RawSourceObject
                or type(provider.selected_value) is not RawSourceObject
                or provider.raw_value != provider.selected_value
                or provider.value_sha256 != provider.block_sha256
                or not source_path
                or type(source_path[-1]) is not RawMemberStep
                or not source_path[-1].raw_key.startswith(
                    "^.spell."
                )
            ):
                raise SpellCatalogSemanticError(
                    "catalog provider must select one exact core-pc1 "
                    "spell block"
                )
            block = provider.raw_value
            _, name_member = _unique_member(block, "Name")
            _, rank_member = _unique_member(block, "Rank")
            _, kind_member = _unique_member(block, "Kind")
            if (
                type(name_member.value) is not str
                or not name_member.value
                or type(rank_member.value) is not int
                or not 1 <= rank_member.value <= 10
                or type(kind_member.value) is not str
                or kind_member.value
                not in ("spell", "cantrip", "focus", "Ritual")
            ):
                raise SpellCatalogSemanticError(
                    "catalog spell identity fields are malformed"
                )
            actions = _optional_member(block, "Actions")
            cast = _optional_member(block, "Cast")
            if actions is not None and type(actions) is not str:
                raise SpellCatalogSemanticError(
                    "catalog Actions must be exact text"
                )
            if cast is not None and type(cast) is not str:
                raise SpellCatalogSemanticError(
                    "catalog Cast must be exact text"
                )
            traditions_value = _optional_member(block, "Traditions")
            if traditions_value is None:
                traditions: tuple[str, ...] = ()
            elif type(traditions_value) is RawSourceArray and all(
                type(item) is str for item in traditions_value.items
            ):
                traditions = tuple(
                    item.casefold() for item in traditions_value.items
                )
            else:
                raise SpellCatalogSemanticError(
                    "catalog Traditions must be an exact string array"
                )
            if (
                len(traditions) != len(set(traditions))
                or any(
                    item not in ("arcane", "divine", "occult", "primal")
                    for item in traditions
                )
            ):
                raise SpellCatalogSemanticError(
                    "catalog Traditions are invalid"
                )
            section_id = address.section_id
            section_ordinal = section_ordinals.get(section_id, 0)
            section_ordinals[section_id] = section_ordinal + 1
            records.append(
                _CatalogData(
                    provider=provider,
                    catalog_block_id=(
                        f"{section_id}#spell-{section_ordinal:03d}"
                    ),
                    name=name_member.value,
                    normalized_name=_normalized_spell_name(
                        name_member.value
                    ),
                    rank=rank_member.value,
                    kind=kind_member.value,
                    actions=actions,
                    cast=cast,
                    traditions=traditions,
                    field_shape=tuple(
                        member.key for member in block.members
                    ),
                )
            )
        names = tuple(record.normalized_name for record in records)
        if len(names) != len(set(names)):
            raise SpellCatalogAmbiguityError(
                "verified Player Core catalog names are not unique"
            )
        return tuple(records)

    def new_rule_requirement(
        spec: tuple[
            str,
            str,
            str,
            str,
            tuple[tuple[str, int], ...],
            str,
        ],
    ) -> tuple[str, RuleRequirement]:
        (
            kind,
            rule_id,
            source_id,
            locator,
            raw_path,
            expected_block,
        ) = spec
        return (
            kind,
            RuleRequirement(
                rule_id=rule_id,
                source_id=source_id,
                locator=locator,
                carrier_path=tuple(
                    RawMemberStep(raw_key, ordinal)
                    for raw_key, ordinal in raw_path
                ),
                expected_block_sha256=expected_block,
            ),
        )

    def resolve_rules(
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
    ) -> dict[str, VerifiedRuleReceipt]:
        rules = {
            kind: authority_resolve_rule(authority, requirement)
            for kind, requirement in (
                new_rule_requirement(spec) for spec in rule_specs
            )
        }
        authority_require_shared(
            authority,
            consumer,
            tuple(rules.values()),
        )
        return rules

    def dependency_wire(dependency_id: str) -> dict[str, Any]:
        dependency = dependencies_by_id[dependency_id]
        return {
            "id": dependency[0],
            "phase": "runtime",
            "relation": dependency[1],
            "requiredContract": dependency[2],
            "status": "deferred",
            "blocks": "registry-activation",
        }

    def usage_dependencies(
        usage: _MentionData,
        catalog: _CatalogData,
    ) -> tuple[str, ...]:
        result = ["spell-target-defense-effect-resolution"]
        if usage.usage_kind in ("at-will", "context-cantrip"):
            result.insert(0, "cast-a-spell-action-economy")
            if catalog.cast is not None:
                result.append("long-cast-mode-and-interruption")
        if usage.usage_kind == "constant":
            result.extend(
                (
                    "constant-initial-effect-state",
                    "constant-unlimited-duration",
                    "constant-counteract-deactivation",
                    "constant-reactivation-cast",
                )
            )
        if catalog.actions is None and catalog.cast is None:
            result.append("spell-cast-action-metadata")
        return tuple(result)

    def usage_rules(
        usage_kind: UsageKind,
        rules: dict[str, VerifiedRuleReceipt],
    ) -> tuple[VerifiedRuleReceipt, ...]:
        if usage_kind == "at-will":
            keys = ("at-will", "innate", "casting")
        elif usage_kind == "constant":
            keys = ("constant", "innate", "casting", "durations")
        elif usage_kind == "context-cantrip":
            keys = ("cantrip", "innate", "casting")
        else:
            raise SpellCatalogSemanticError(
                "limited mentions are not linkable usages"
            )
        return tuple(rules[key] for key in keys)

    def linked_structure(
        compiled: _CompiledData,
        records: tuple[_CatalogData, ...],
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        rules = resolve_rules(authority, compiled.consumer)
        by_name = {
            record.normalized_name: record for record in records
        }
        linked: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []
        for usage in compiled.usages:
            catalog = by_name.get(usage.normalized_name)
            if catalog is None:
                mismatches.append(
                    {
                        "type": "exact-source-catalog-mismatch",
                        "phase": "source-repair",
                        "status": "deferred",
                        "blocks": "link-and-registry-activation",
                        "sourceMention": _mention_wire(usage),
                        "normalizedName": usage.normalized_name,
                        "candidateCount": 0,
                        "requiredContract": (
                            "one exact source-validated Player Core "
                            "catalog name; aliases and fuzzy matching "
                            "are forbidden"
                        ),
                    }
                )
                continue
            authority_validate_selection(authority, catalog.provider)
            effective_rank = (
                usage.source_rank
                if usage.source_rank is not None
                else catalog.rank
            )
            if effective_rank < catalog.rank:
                raise SpellCatalogSemanticError(
                    f"source rank {effective_rank} is below catalog "
                    f"rank {catalog.rank} for "
                    f"{usage.normalized_name!r}"
                )
            if (
                usage.usage_kind == "context-cantrip"
                and catalog.kind != "cantrip"
            ):
                raise SpellCatalogSemanticError(
                    "context cantrip did not link to a cantrip provider"
                )
            if catalog.actions is not None:
                action_shape = "actions"
                action_value = catalog.actions
            elif catalog.cast is not None:
                action_shape = "long-cast"
                action_value = catalog.cast
            else:
                action_shape = "missing"
                action_value = None
            dependency_ids = usage_dependencies(usage, catalog)
            verified_rules = usage_rules(usage.usage_kind, rules)
            authority_require_shared(
                authority,
                compiled.consumer,
                verified_rules,
            )
            if usage.usage_kind == "constant":
                availability: dict[str, Any] = {
                    "frequency": "constant",
                    "initialEffectWithoutCasting": True,
                    "duration": "unlimited",
                    "reactivationUsesNormalSpellcastingActions": True,
                }
                mechanic_type = "constant-spell"
            else:
                availability = {
                    "frequency": "unlimited",
                    "consumesSpellSlot": False,
                    "consumesDailyUse": False,
                    "automaticHeightening": (
                        usage.usage_kind == "context-cantrip"
                    ),
                    "consumesFocusPoints": False,
                }
                mechanic_type = (
                    "innate-cantrip"
                    if usage.usage_kind == "context-cantrip"
                    else "innate-at-will-spell"
                )
            linked.append(
                {
                    "compileSupported": True,
                    "linkSupported": True,
                    "runtimeSupported": False,
                    "registryStatus": "unregistered",
                    "mechanic": {
                        "type": mechanic_type,
                        "familyId": FAMILY_ID,
                        "kind": "spell-availability",
                        "availability": availability,
                        "tradition": usage.tradition,
                        "sourceRank": usage.source_rank,
                        "effectiveRank": effective_rank,
                        "catalogRank": catalog.rank,
                        "rankDelta": effective_rank - catalog.rank,
                        "catalogKind": catalog.kind,
                        "actionShape": action_shape,
                        "actionValue": action_value,
                        "sourceTraditionListedByCatalog": (
                            usage.tradition in catalog.traditions
                        ),
                        "qualifierFragments": list(
                            usage.qualifier_fragments
                        ),
                    },
                    "sourceMention": _mention_wire(usage),
                    "catalog": _catalog_record_wire(catalog),
                    "rules": [
                        verified_rule_serializer(rule)
                        for rule in verified_rules
                    ],
                    "runtimeDependencies": [
                        dependency_wire(dependency_id)
                        for dependency_id in dependency_ids
                    ],
                    "deferredMechanics": list(dependency_ids),
                }
            )
        compiled_wire = _compiled_wire(compiled)
        return {
            **compiled_wire,
            "linkSupported": not mismatches,
            "runtimeSupported": False,
            "registryStatus": "unregistered",
            "catalog": {
                "sourceId": PLAYER_CORE_SOURCE_ID,
                "spellBlocks": len(records),
                "catalogDigest": _canonical_digest(
                    [
                        _catalog_record_wire(record)
                        for record in records
                    ]
                ),
            },
            "linkedUsages": linked,
            "catalogMismatches": mismatches,
        }

    def new_patch(
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
        data: _CompiledData,
    ) -> InnateSpellcastingPatch:
        result = object.__new__(patch_type)
        object.__setattr__(result, "_authority", authority)
        object.__setattr__(result, "_consumer", consumer)
        object.__setattr__(
            result,
            "_source_receipt_digest",
            consumer.receipt.digest,
        )
        object.__setattr__(
            result,
            "_structure_sha256",
            _canonical_digest(_compiled_wire(data)),
        )
        patch_registry[result] = (
            authority,
            consumer,
            consumer.receipt.digest,
            object.__getattribute__(result, "_structure_sha256"),
        )
        return result

    def validate_patch(value: object) -> _CompiledData:
        if type(value) is not patch_type:
            raise TypeError("innate spell patch must be exact")
        try:
            expected = patch_registry[value]
        except KeyError as failure:
            raise InnateSpellArtifactError(
                "innate spell patch was not issued by this compiler"
            ) from failure
        try:
            authority = object.__getattribute__(value, "_authority")
            consumer = object.__getattribute__(value, "_consumer")
            receipt_digest = object.__getattribute__(
                value,
                "_source_receipt_digest",
            )
            structure_sha256 = object.__getattribute__(
                value,
                "_structure_sha256",
            )
        except (AttributeError, TypeError) as failure:
            raise InnateSpellArtifactError(
                "innate spell patch state is invalid"
            ) from failure
        if (
            authority is not expected[0]
            or consumer is not expected[1]
            or receipt_digest != expected[2]
            or structure_sha256 != expected[3]
            or
            type(authority) is not SourceAuthorityAdapter
            or type(consumer) is not VerifiedSourceSelection
            or type(receipt_digest) is not str
            or type(structure_sha256) is not str
        ):
            raise InnateSpellArtifactError(
                "innate spell patch state is invalid"
            )
        authority_validate_selection(authority, consumer)
        if consumer.receipt.digest != receipt_digest:
            raise InnateSpellArtifactError(
                "innate spell patch source identity changed"
            )
        data = compile_structure(consumer, authority)
        if data is None:
            raise InnateSpellArtifactError(
                "innate spell patch no longer compiles"
            )
        if _canonical_digest(_compiled_wire(data)) != structure_sha256:
            raise InnateSpellArtifactError(
                "innate spell patch structure changed"
            )
        return data

    def new_catalog(
        authority: SourceAuthorityAdapter,
        providers: tuple[VerifiedSourceSelection, ...],
        records: tuple[_CatalogData, ...],
    ) -> SpellCatalogIndex:
        ordered = tuple(record.provider for record in records)
        result = object.__new__(catalog_type)
        object.__setattr__(result, "_authority", authority)
        object.__setattr__(result, "_providers", ordered)
        object.__setattr__(
            result,
            "_provider_receipt_digests",
            tuple(provider.receipt.digest for provider in ordered),
        )
        object.__setattr__(
            result,
            "_catalog_sha256",
            _canonical_digest(_catalog_wire(records)),
        )
        catalog_registry[result] = (
            authority,
            ordered,
            object.__getattribute__(
                result,
                "_provider_receipt_digests",
            ),
            object.__getattribute__(result, "_catalog_sha256"),
        )
        return result

    def validate_catalog(value: object) -> tuple[_CatalogData, ...]:
        if type(value) is not catalog_type:
            raise TypeError("spell catalog index must be exact")
        try:
            expected = catalog_registry[value]
        except KeyError as failure:
            raise InnateSpellArtifactError(
                "spell catalog index was not issued by this compiler"
            ) from failure
        try:
            authority = object.__getattribute__(value, "_authority")
            providers = object.__getattribute__(value, "_providers")
            receipt_digests = object.__getattribute__(
                value,
                "_provider_receipt_digests",
            )
            catalog_sha256 = object.__getattribute__(
                value,
                "_catalog_sha256",
            )
        except (AttributeError, TypeError) as failure:
            raise InnateSpellArtifactError(
                "spell catalog index state is invalid"
            ) from failure
        if (
            authority is not expected[0]
            or providers is not expected[1]
            or receipt_digests is not expected[2]
            or catalog_sha256 != expected[3]
            or
            type(authority) is not SourceAuthorityAdapter
            or type(providers) is not tuple
            or type(receipt_digests) is not tuple
            or type(catalog_sha256) is not str
        ):
            raise InnateSpellArtifactError(
                "spell catalog index state is invalid"
            )
        records = catalog_structure(providers, authority)
        actual_receipts = tuple(
            record.provider.receipt.digest for record in records
        )
        if actual_receipts != receipt_digests:
            raise InnateSpellArtifactError(
                "spell catalog provider identity changed"
            )
        if _canonical_digest(_catalog_wire(records)) != catalog_sha256:
            raise InnateSpellArtifactError(
                "spell catalog structure changed"
            )
        return records

    def new_linked(
        authority: SourceAuthorityAdapter,
        compiled: InnateSpellcastingPatch,
        catalog: SpellCatalogIndex,
        value: dict[str, Any],
    ) -> LinkedInnateSpellcastingPatch:
        result = object.__new__(linked_type)
        object.__setattr__(result, "_authority", authority)
        object.__setattr__(result, "_compiled", compiled)
        object.__setattr__(result, "_catalog", catalog)
        object.__setattr__(
            result,
            "_compiled_sha256",
            object.__getattribute__(compiled, "_structure_sha256"),
        )
        object.__setattr__(
            result,
            "_catalog_sha256",
            object.__getattribute__(catalog, "_catalog_sha256"),
        )
        object.__setattr__(
            result,
            "_linked_sha256",
            _canonical_digest(value),
        )
        linked_registry[result] = (
            authority,
            compiled,
            catalog,
            object.__getattribute__(result, "_compiled_sha256"),
            object.__getattribute__(result, "_catalog_sha256"),
            object.__getattribute__(result, "_linked_sha256"),
        )
        return result

    def validate_linked(value: object) -> dict[str, Any]:
        if type(value) is not linked_type:
            raise TypeError("linked innate spell patch must be exact")
        try:
            expected = linked_registry[value]
        except KeyError as failure:
            raise InnateSpellArtifactError(
                "linked innate spell patch was not issued by this compiler"
            ) from failure
        try:
            authority = object.__getattribute__(value, "_authority")
            compiled = object.__getattribute__(value, "_compiled")
            catalog = object.__getattribute__(value, "_catalog")
            compiled_sha256 = object.__getattribute__(
                value,
                "_compiled_sha256",
            )
            catalog_sha256 = object.__getattribute__(
                value,
                "_catalog_sha256",
            )
            linked_sha256 = object.__getattribute__(
                value,
                "_linked_sha256",
            )
        except (AttributeError, TypeError) as failure:
            raise InnateSpellArtifactError(
                "linked innate spell patch state is invalid"
            ) from failure
        if (
            authority is not expected[0]
            or compiled is not expected[1]
            or catalog is not expected[2]
            or compiled_sha256 != expected[3]
            or catalog_sha256 != expected[4]
            or linked_sha256 != expected[5]
            or
            type(authority) is not SourceAuthorityAdapter
            or type(compiled) is not patch_type
            or type(catalog) is not catalog_type
            or type(compiled_sha256) is not str
            or type(catalog_sha256) is not str
            or type(linked_sha256) is not str
            or object.__getattribute__(compiled, "_authority")
            is not authority
            or object.__getattribute__(catalog, "_authority")
            is not authority
            or object.__getattribute__(compiled, "_structure_sha256")
            != compiled_sha256
            or object.__getattribute__(catalog, "_catalog_sha256")
            != catalog_sha256
        ):
            raise InnateSpellArtifactError(
                "linked innate spell patch authority changed"
            )
        compiled_data = validate_patch(compiled)
        catalog_data = validate_catalog(catalog)
        result = linked_structure(
            compiled_data,
            catalog_data,
            authority,
        )
        if _canonical_digest(result) != linked_sha256:
            raise InnateSpellArtifactError(
                "linked innate spell patch structure changed"
            )
        return result

    def compile_public(
        consumer: VerifiedSourceSelection,
        authority: SourceAuthorityAdapter,
        /,
    ) -> InnateSpellcastingPatch | None:
        data = compile_structure(consumer, authority)
        if data is None:
            return None
        return new_patch(authority, consumer, data)

    def catalog_public(
        providers: tuple[VerifiedSourceSelection, ...],
        authority: SourceAuthorityAdapter,
        /,
    ) -> SpellCatalogIndex:
        records = catalog_structure(providers, authority)
        return new_catalog(authority, providers, records)

    def link_public(
        compiled: InnateSpellcastingPatch,
        catalog: SpellCatalogIndex,
        authority: SourceAuthorityAdapter,
        /,
    ) -> LinkedInnateSpellcastingPatch:
        if type(authority) is not SourceAuthorityAdapter:
            raise TypeError(
                "innate spell linking requires an exact "
                "SourceAuthorityAdapter"
            )
        data = validate_patch(compiled)
        records = validate_catalog(catalog)
        if (
            object.__getattribute__(compiled, "_authority") is not authority
            or object.__getattribute__(catalog, "_authority") is not authority
        ):
            raise InnateSpellArtifactError(
                "compiled source and catalog must share one authority"
            )
        value = linked_structure(data, records, authority)
        return new_linked(
            authority,
            compiled,
            catalog,
            value,
        )

    # Retain these closure values so module/class/global rebinding cannot alter
    # the active implementation.
    _ = mechanic_types
    return (
        compile_public,
        catalog_public,
        link_public,
        validate_patch,
        validate_catalog,
        validate_linked,
    )


(
    compile_innate_spell_usage,
    build_spell_catalog,
    link_innate_spellcasting_patch,
    _bound_validate_patch,
    _bound_validate_catalog,
    _bound_validate_linked,
) = _build_implementation()

compile_innate_spell_usage.__name__ = "compile_innate_spell_usage"
compile_innate_spell_usage.__qualname__ = "compile_innate_spell_usage"
build_spell_catalog.__name__ = "build_spell_catalog"
build_spell_catalog.__qualname__ = "build_spell_catalog"
link_innate_spellcasting_patch.__name__ = (
    "link_innate_spellcasting_patch"
)
link_innate_spellcasting_patch.__qualname__ = (
    "link_innate_spellcasting_patch"
)

_bind_patch_validator(_bound_validate_patch)
_bind_catalog_validator(_bound_validate_catalog)
_bind_linked_validator(_bound_validate_linked)

del _bound_validate_patch
del _bound_validate_catalog
del _bound_validate_linked
del _bind_patch_validator
del _bind_catalog_validator
del _bind_linked_validator
del _build_implementation

FRAGMENT = MappingProxyType(
    {
        "familyId": FAMILY_ID,
        "mechanicTypes": MECHANIC_TYPES,
        "compileSupported": True,
        "linkSupported": True,
        "runtimeSupported": False,
        "registryStatus": "unregistered",
    }
)


__all__ = [
    "EXPECTED_PLAYER_CORE_SPELLS",
    "FAMILY_ID",
    "FRAGMENT",
    "MECHANIC_TYPES",
    "InnateSpellArtifactError",
    "InnateSpellSourceShapeError",
    "InnateSpellcastingPatch",
    "LinkedInnateSpellcastingPatch",
    "SpellCatalogAmbiguityError",
    "SpellCatalogIndex",
    "SpellCatalogLinkError",
    "SpellCatalogSemanticError",
    "build_spell_catalog",
    "compile_innate_spell_usage",
    "link_innate_spellcasting_patch",
]

"""Frozen contracts shared by PF2ER mechanics families and orchestrators."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Literal, Protocol, TypeAlias


AbilityKind: TypeAlias = Literal["activity", "passive", "reaction"]
ActionCost: TypeAlias = Literal[1, 2, 3, "reaction"] | None
SerializedObject: TypeAlias = dict[str, Any]
ReadonlyObject: TypeAlias = Mapping[str, Any]
ParticipantIndex: TypeAlias = Mapping[str, Mapping[str, Any]]
RendererKey: TypeAlias = tuple[str, str]
SpellEffectHandlerKey: TypeAlias = tuple[str, str]
RawSourcePrimitive: TypeAlias = str | int | float | bool | None


def _require_key(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")


def _require_callable(value: Any, label: str) -> None:
    if not callable(value):
        raise TypeError(f"{label} must be callable")


def _require_nonnegative_ordinal(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _ordered_tuple(value: Any, label: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            f"{label} must be an explicit ordered sequence (list or tuple)"
        )
    return tuple(value)


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    result = _ordered_tuple(value, label)
    if any(not isinstance(item, str) for item in result):
        raise TypeError(f"{label} must contain only strings")
    return result


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("compiled mechanic keys must be strings")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("compiled mechanic numbers must be finite")
        return value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(
        f"compiled mechanic value is not JSON-compatible: {type(value).__name__}"
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class RawSourceArray:
    """An immutable JSON array retained before source normalization."""

    items: tuple[Any, ...]

    def __post_init__(self) -> None:
        items = _ordered_tuple(self.items, "RawSourceArray.items")
        object.__setattr__(
            self,
            "items",
            tuple(_freeze_raw_source_value(item) for item in items),
        )


@dataclass(frozen=True, slots=True)
class RawSourceMember:
    """One exact JSON object member, including its unnormalized key."""

    key: str
    value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.key, str):
            raise TypeError("RawSourceMember.key must be a string")
        object.__setattr__(
            self,
            "value",
            _freeze_raw_source_value(self.value),
        )


@dataclass(frozen=True, slots=True)
class RawSourceObject:
    """An immutable, ordered, duplicate-preserving JSON object."""

    members: tuple[RawSourceMember, ...]

    def __post_init__(self) -> None:
        raw_members = _ordered_tuple(
            self.members,
            "RawSourceObject.members",
        )
        members = []
        for index, raw_member in enumerate(raw_members):
            if isinstance(raw_member, RawSourceMember):
                member = raw_member
            elif (
                isinstance(raw_member, (list, tuple))
                and len(raw_member) == 2
            ):
                member = RawSourceMember(
                    key=raw_member[0],
                    value=raw_member[1],
                )
            else:
                raise TypeError(
                    f"RawSourceObject.members[{index}] must be a "
                    "RawSourceMember or key/value pair"
                )
            members.append(member)
        object.__setattr__(self, "members", tuple(members))

    @classmethod
    def from_pairs(
        cls,
        pairs: list[tuple[str, Any]] | tuple[tuple[str, Any], ...],
        /,
    ) -> RawSourceObject:
        """Freeze explicit object pairs without passing through a mapping."""

        return cls(members=pairs)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(member.key for member in self.members)

    def values(self, key: str, /) -> tuple[Any, ...]:
        """Return every exact-key occurrence in source order."""

        if not isinstance(key, str):
            raise TypeError("RawSourceObject lookup key must be a string")
        return tuple(
            member.value
            for member in self.members
            if member.key == key
        )


@dataclass(frozen=True, slots=True)
class RawSourcePathStep:
    """One exact object-pair selection in a duplicate-aware source path."""

    raw_key: str
    member_ordinal: int

    def __post_init__(self) -> None:
        if not isinstance(self.raw_key, str):
            raise TypeError("RawSourcePathStep.raw_key must be a string")
        if not self.raw_key:
            raise ValueError(
                "RawSourcePathStep.raw_key must be non-empty"
            )
        _require_nonnegative_ordinal(
            self.member_ordinal,
            "RawSourcePathStep.member_ordinal",
        )

    def as_serialized(self) -> SerializedObject:
        return {
            "rawKey": self.raw_key,
            "memberOrdinal": self.member_ordinal,
        }


RawSourceValue: TypeAlias = (
    RawSourcePrimitive | RawSourceArray | RawSourceObject
)


def _freeze_raw_source_value(value: Any) -> RawSourceValue:
    if isinstance(value, (RawSourceArray, RawSourceObject)):
        return value
    if isinstance(value, Mapping):
        raise TypeError(
            "raw source objects must be supplied as RawSourceObject; "
            "mappings cannot prove duplicate preservation"
        )
    if isinstance(value, (list, tuple)):
        return RawSourceArray(items=value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("raw source numbers must be finite")
        return value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(
        f"raw source value is not JSON-compatible: {type(value).__name__}"
    )


@dataclass(frozen=True, slots=True)
class AbilitySource:
    """Immutable normalized facts plus the exact source member."""

    source_label: str
    action_cost: ActionCost
    kind: AbilityKind
    traits: tuple[str, ...]
    trigger: str
    description: str
    source_id: str
    locator: str
    creature_name: str
    raw_member: RawSourceMember

    def __post_init__(self) -> None:
        for field_name in (
            "source_label",
            "trigger",
            "description",
            "source_id",
            "locator",
            "creature_name",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"AbilitySource.{field_name} must be a string")
        for field_name in (
            "source_label",
            "source_id",
            "locator",
            "creature_name",
        ):
            _require_key(getattr(self, field_name), f"AbilitySource.{field_name}")

        traits = _string_tuple(self.traits, "AbilitySource.traits")
        object.__setattr__(self, "traits", traits)
        if not isinstance(self.raw_member, RawSourceMember):
            raise TypeError(
                "AbilitySource.raw_member must be a RawSourceMember"
            )

        if self.action_cost is None:
            expected_kind: AbilityKind = "passive"
        elif type(self.action_cost) is int and self.action_cost in (1, 2, 3):
            expected_kind = "activity"
        elif type(self.action_cost) is str and self.action_cost == "reaction":
            expected_kind = "reaction"
        else:
            raise ValueError("AbilitySource.action_cost is invalid")
        if self.kind != expected_kind:
            raise ValueError(
                "AbilitySource.kind does not match AbilitySource.action_cost"
            )


@dataclass(frozen=True, slots=True)
class RuleReference:
    """Exact source reference emitted with a supported compiled mechanic."""

    source_id: str
    locator: str

    def __post_init__(self) -> None:
        _require_key(self.source_id, "RuleReference.source_id")
        _require_key(self.locator, "RuleReference.locator")

    def as_serialized(self) -> SerializedObject:
        return {
            "sourceId": self.source_id,
            "locator": self.locator,
        }


@dataclass(frozen=True, slots=True)
class AbilityCompilerPatch:
    """One complete supported-ability patch returned by a matching compiler."""

    mechanic: Mapping[str, Any]
    rule: RuleReference
    traits: tuple[str, ...] | None = None
    deferred_mechanics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.rule, RuleReference):
            raise TypeError("AbilityCompilerPatch.rule must be a RuleReference")
        if not isinstance(self.mechanic, Mapping):
            raise TypeError("AbilityCompilerPatch.mechanic must be a mapping")
        frozen_mechanic = _freeze_json(self.mechanic)
        mechanic_type = frozen_mechanic.get("type")
        _require_key(mechanic_type, "AbilityCompilerPatch.mechanic.type")
        object.__setattr__(self, "mechanic", frozen_mechanic)

        if self.traits is not None:
            traits = _string_tuple(
                self.traits,
                "AbilityCompilerPatch.traits",
            )
            object.__setattr__(self, "traits", traits)

        deferred = _string_tuple(
            self.deferred_mechanics,
            "AbilityCompilerPatch.deferred_mechanics",
        )
        if any(not item for item in deferred):
            raise ValueError(
                "AbilityCompilerPatch.deferred_mechanics must contain "
                "non-empty strings"
            )
        object.__setattr__(self, "deferred_mechanics", deferred)

    @property
    def mechanic_type(self) -> str:
        return str(self.mechanic["type"])

    def as_ability_update(self) -> SerializedObject:
        result: SerializedObject = {
            "supported": True,
            "mechanic": _thaw_json(self.mechanic),
            "rule": self.rule.as_serialized(),
        }
        if self.traits is not None:
            result["traits"] = list(self.traits)
        if self.deferred_mechanics:
            result["deferredMechanics"] = list(self.deferred_mechanics)
        return result


class AbilityCompiler(Protocol):
    def __call__(
        self,
        source: AbilitySource,
        /,
    ) -> AbilityCompilerPatch | None: ...


@dataclass(frozen=True, slots=True)
class AnnotatedStatSource:
    """One exact scalar stat member selected by a source orchestrator."""

    field_name: str
    raw_member: RawSourceMember
    source_id: str
    locator: str
    creature_name: str

    def __post_init__(self) -> None:
        _require_key(self.field_name, "AnnotatedStatSource.field_name")
        if not isinstance(self.raw_member, RawSourceMember):
            raise TypeError(
                "AnnotatedStatSource.raw_member must be a RawSourceMember"
            )
        if not isinstance(self.raw_member.value, str):
            raise TypeError(
                "AnnotatedStatSource raw member value must be a string"
            )
        for field_name in ("source_id", "locator", "creature_name"):
            _require_key(
                getattr(self, field_name),
                f"AnnotatedStatSource.{field_name}",
            )

    @property
    def raw_field_name(self) -> str:
        return self.raw_member.key

    @property
    def source_value(self) -> str:
        return self.raw_member.value


@dataclass(frozen=True, slots=True)
class AnnotatedStatPatch:
    """A parsed stat scalar and its complete normalized passive ability."""

    stat_value: int
    ability_id: str
    ability_name: str
    ability: AbilityCompilerPatch

    def __post_init__(self) -> None:
        if type(self.stat_value) is not int or self.stat_value <= 0:
            raise ValueError(
                "AnnotatedStatPatch.stat_value must be a positive integer"
            )
        _require_key(self.ability_id, "AnnotatedStatPatch.ability_id")
        _require_key(self.ability_name, "AnnotatedStatPatch.ability_name")
        if not isinstance(self.ability, AbilityCompilerPatch):
            raise TypeError(
                "AnnotatedStatPatch.ability must be an AbilityCompilerPatch"
            )

    @property
    def mechanic_type(self) -> str:
        return self.ability.mechanic_type

    def as_serialized(self) -> SerializedObject:
        return {
            "statValue": self.stat_value,
            "ability": {
                "id": self.ability_id,
                "name": self.ability_name,
                **self.ability.as_ability_update(),
            },
        }


class AnnotatedStatCompiler(Protocol):
    def __call__(
        self,
        source: AnnotatedStatSource,
        /,
    ) -> AnnotatedStatPatch | None: ...


@dataclass(frozen=True, slots=True)
class AnnotatedStatCompilerRegistration:
    compiler_id: str
    mechanic_type: str
    compiler: AnnotatedStatCompiler

    def __post_init__(self) -> None:
        _require_key(self.compiler_id, "annotated-stat compiler_id")
        _require_key(
            self.mechanic_type,
            "annotated-stat compiler mechanic_type",
        )
        _require_callable(self.compiler, "annotated-stat compiler")

    def match(
        self,
        source: AnnotatedStatSource,
        /,
    ) -> AnnotatedStatPatch | None:
        if not isinstance(source, AnnotatedStatSource):
            return None
        patch = self.compiler(source)
        if patch is None:
            return None
        if not isinstance(patch, AnnotatedStatPatch):
            raise TypeError(
                f"annotated-stat compiler {self.compiler_id!r} returned "
                f"{type(patch).__name__}, not AnnotatedStatPatch or None"
            )
        if (
            patch.ability.rule.source_id != source.source_id
            or patch.ability.rule.locator != source.locator
        ):
            raise ValueError(
                f"annotated-stat compiler {self.compiler_id!r} changed its "
                "source identity"
            )
        if patch.mechanic_type != self.mechanic_type:
            raise ValueError(
                f"annotated-stat compiler {self.compiler_id!r} returned "
                f"mechanic type {patch.mechanic_type!r}, expected "
                f"{self.mechanic_type!r}"
            )
        return patch


class AnnotatedStatCompilerAmbiguityError(ValueError):
    """More than one ordered compiler accepted one annotated stat."""


def match_annotated_stat_compilers(
    source: AnnotatedStatSource,
    registrations: list[AnnotatedStatCompilerRegistration]
    | tuple[AnnotatedStatCompilerRegistration, ...],
    /,
) -> AnnotatedStatPatch | None:
    """Return the sole match while preserving zero/one/many semantics."""

    matches: list[tuple[str, AnnotatedStatPatch]] = []
    for registration in _ordered_tuple(
        registrations,
        "annotated-stat compiler registrations",
    ):
        if not isinstance(registration, AnnotatedStatCompilerRegistration):
            raise TypeError(
                "annotated-stat compiler registrations must contain only "
                "AnnotatedStatCompilerRegistration values"
            )
        patch = registration.match(source)
        if patch is not None:
            matches.append((registration.compiler_id, patch))
    if len(matches) > 1:
        compiler_ids = ", ".join(repr(item[0]) for item in matches)
        raise AnnotatedStatCompilerAmbiguityError(
            "multiple annotated-stat compilers matched in registration "
            f"order: {compiler_ids}"
        )
    return matches[0][1] if matches else None


@dataclass(frozen=True, slots=True)
class StrikeRiderSource:
    """Exact Strike carrier and duplicate-aware source/linker identity.

    The source adapter must first preflight the containing creature object,
    reject duplicate or conflicting Melee/Ranged members, and supply the
    selected member with its absolute pair ordinal.  This contract then
    verifies every ordinal inside that trusted member and derives rider text
    from its exact raw Damage string.  It does not claim to validate the
    complete PF2ER damage grammar.
    """

    raw_strike_member: RawSourceMember
    strike_member_ordinal: int
    strike_ordinal: int
    damage_member_ordinal: int
    rider_ordinal: int
    strike_id: str
    source_id: str
    locator: str
    section_id: str
    content_path: tuple[RawSourcePathStep, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "strike_id",
            "source_id",
            "locator",
            "section_id",
        ):
            _require_key(
                getattr(self, field_name),
                f"StrikeRiderSource.{field_name}",
            )
        section_prefix = f"{self.source_id}:"
        if (
            not self.section_id.startswith(section_prefix)
            or self.section_id == section_prefix
        ):
            raise ValueError(
                "StrikeRiderSource.section_id must belong to source_id"
            )

        if not isinstance(self.raw_strike_member, RawSourceMember):
            raise TypeError(
                "StrikeRiderSource.raw_strike_member must be a "
                "RawSourceMember"
            )
        if self.raw_strike_member.key not in ("Melee", "Ranged"):
            raise ValueError(
                "StrikeRiderSource raw Strike member key must be exactly "
                "Melee or Ranged"
            )
        if not isinstance(self.raw_strike_member.value, RawSourceArray):
            raise TypeError(
                "StrikeRiderSource raw Strike member value must be a "
                "RawSourceArray"
            )

        for field_name in (
            "strike_member_ordinal",
            "strike_ordinal",
            "damage_member_ordinal",
            "rider_ordinal",
        ):
            _require_nonnegative_ordinal(
                getattr(self, field_name),
                f"StrikeRiderSource.{field_name}",
            )

        strikes = self.raw_strike_member.value.items
        if self.strike_ordinal >= len(strikes):
            raise ValueError(
                "StrikeRiderSource.strike_ordinal does not resolve in the "
                "raw Strike array"
            )
        strike = strikes[self.strike_ordinal]
        if not isinstance(strike, RawSourceObject):
            raise TypeError(
                "StrikeRiderSource selected raw Strike must be a "
                "RawSourceObject"
            )

        damage_candidates = tuple(
            index
            for index, member in enumerate(strike.members)
            if member.key.strip() == "Damage"
        )
        if damage_candidates != (self.damage_member_ordinal,):
            raise ValueError(
                "StrikeRiderSource requires one exact Damage member with no "
                "duplicate or whitespace-conflicting key"
            )
        damage_member = strike.members[self.damage_member_ordinal]
        if damage_member.key != "Damage":
            raise ValueError(
                "StrikeRiderSource Damage member key must be exact"
            )
        if not isinstance(damage_member.value, str):
            raise TypeError(
                "StrikeRiderSource raw Damage value must be a string"
            )

        components = damage_member.value.split(" plus ")
        if (
            len(components) < 2
            or any(
                not component or component != component.strip()
                for component in components
            )
        ):
            raise ValueError(
                "StrikeRiderSource raw Damage has malformed rider "
                "component boundaries"
            )
        riders = components[1:]
        if self.rider_ordinal >= len(riders):
            raise ValueError(
                "StrikeRiderSource.rider_ordinal does not resolve in raw "
                "Damage"
            )

        object.__setattr__(
            self,
            "content_path",
            _ordered_tuple(
                self.content_path,
                "StrikeRiderSource.content_path",
            ),
        )
        for index, step in enumerate(self.content_path):
            if not isinstance(step, RawSourcePathStep):
                raise TypeError(
                    f"StrikeRiderSource.content_path[{index}] must be a "
                    "RawSourcePathStep"
                )

    @property
    def raw_strike(self) -> RawSourceObject:
        return self.raw_strike_member.value.items[self.strike_ordinal]

    @property
    def raw_damage_member(self) -> RawSourceMember:
        return self.raw_strike.members[self.damage_member_ordinal]

    @property
    def damage_source_text(self) -> str:
        return self.raw_damage_member.value

    @property
    def rider_components(self) -> tuple[str, ...]:
        return tuple(self.damage_source_text.split(" plus ")[1:])

    @property
    def source_text(self) -> str:
        return self.rider_components[self.rider_ordinal]

    def as_source_identity(self) -> SerializedObject:
        return {
            "sourceId": self.source_id,
            "locator": self.locator,
            "sectionId": self.section_id,
            "contentPath": [
                step.as_serialized()
                for step in self.content_path
            ],
            "strikeField": self.raw_strike_member.key,
            "strikeMemberOrdinal": self.strike_member_ordinal,
            "strikeOrdinal": self.strike_ordinal,
            "damageMemberOrdinal": self.damage_member_ordinal,
            "riderOrdinal": self.rider_ordinal,
        }


@dataclass(frozen=True, slots=True)
class StrikeRiderCompilerPatch:
    """One complete immutable Strike follow-up emitted by a compiler."""

    source: StrikeRiderSource
    follow_up: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.source, StrikeRiderSource):
            raise TypeError(
                "StrikeRiderCompilerPatch.source must be a StrikeRiderSource"
            )
        if not isinstance(self.follow_up, Mapping):
            raise TypeError(
                "StrikeRiderCompilerPatch.follow_up must be a mapping"
            )
        follow_up = _freeze_json(self.follow_up)
        _require_key(
            follow_up.get("kind"),
            "StrikeRiderCompilerPatch.follow_up.kind",
        )
        if follow_up.get("sourceText") != self.source.source_text:
            raise ValueError(
                "StrikeRiderCompilerPatch did not preserve source text"
            )
        if follow_up.get("strikeId") != self.source.strike_id:
            raise ValueError(
                "StrikeRiderCompilerPatch did not preserve Strike identity"
            )
        if follow_up.get("source") != _freeze_json(
            self.source.as_source_identity()
        ):
            raise ValueError(
                "StrikeRiderCompilerPatch did not preserve source identity"
            )
        object.__setattr__(self, "follow_up", follow_up)

    @property
    def follow_up_kind(self) -> str:
        return str(self.follow_up["kind"])

    def as_follow_up(self) -> SerializedObject:
        return _thaw_json(self.follow_up)


class StrikeRiderCompiler(Protocol):
    def __call__(
        self,
        source: StrikeRiderSource,
        /,
    ) -> StrikeRiderCompilerPatch | None: ...


@dataclass(frozen=True, slots=True)
class StrikeRiderCompilerRegistration:
    compiler_id: str
    follow_up_kind: str
    compiler: StrikeRiderCompiler

    def __post_init__(self) -> None:
        _require_key(self.compiler_id, "Strike rider compiler_id")
        _require_key(self.follow_up_kind, "Strike rider follow_up_kind")
        _require_callable(self.compiler, "Strike rider compiler")

    def match(
        self,
        source: StrikeRiderSource,
        /,
    ) -> StrikeRiderCompilerPatch | None:
        if not isinstance(source, StrikeRiderSource):
            return None
        patch = self.compiler(source)
        if patch is None:
            return None
        if not isinstance(patch, StrikeRiderCompilerPatch):
            raise TypeError(
                f"Strike rider compiler {self.compiler_id!r} returned "
                f"{type(patch).__name__}, not "
                "StrikeRiderCompilerPatch or None"
            )
        if patch.source != source:
            raise ValueError(
                f"Strike rider compiler {self.compiler_id!r} changed its "
                "source identity"
            )
        if patch.follow_up_kind != self.follow_up_kind:
            raise ValueError(
                f"Strike rider compiler {self.compiler_id!r} returned "
                f"{patch.follow_up_kind!r}, expected "
                f"{self.follow_up_kind!r}"
            )
        return patch


class StrikeRiderCompilerAmbiguityError(ValueError):
    """More than one ordered compiler accepted one Strike rider."""


def match_strike_rider_compilers(
    source: StrikeRiderSource,
    registrations: list[StrikeRiderCompilerRegistration]
    | tuple[StrikeRiderCompilerRegistration, ...],
    /,
) -> StrikeRiderCompilerPatch | None:
    """Return the sole match while preserving zero/one/many semantics."""

    matches: list[tuple[str, StrikeRiderCompilerPatch]] = []
    for registration in _ordered_tuple(
        registrations,
        "Strike rider compiler registrations",
    ):
        if not isinstance(registration, StrikeRiderCompilerRegistration):
            raise TypeError(
                "Strike rider compiler registrations must contain only "
                "StrikeRiderCompilerRegistration values"
            )
        patch = registration.match(source)
        if patch is not None:
            matches.append((registration.compiler_id, patch))
    if len(matches) > 1:
        compiler_ids = ", ".join(repr(item[0]) for item in matches)
        raise StrikeRiderCompilerAmbiguityError(
            "multiple Strike rider compilers matched in registration "
            f"order: {compiler_ids}"
        )
    return matches[0][1] if matches else None


class ActivityOptionBuilder(Protocol):
    def __call__(
        self,
        state: ReadonlyObject,
        actor: ReadonlyObject,
        ability: ReadonlyObject,
        /,
    ) -> Sequence[SerializedObject]: ...


class ActivityResolver(Protocol):
    def __call__(
        self,
        state: SerializedObject,
        actor_id: str,
        action: ReadonlyObject,
        ability: ReadonlyObject,
        runtime_context: ActivityRuntimeContext | None,
        /,
    ) -> SerializedObject: ...


CompoundActivityRequestKind: TypeAlias = Literal[
    "host-input",
    "land-move",
    "basic-save-damage",
]


class CompoundActivityStarter(Protocol):
    def __call__(
        self,
        state: ReadonlyObject,
        actor_id: str,
        action: ReadonlyObject,
        ability: ReadonlyObject,
        /,
    ) -> SerializedObject: ...


class CompoundActivityResumer(Protocol):
    def __call__(
        self,
        state: ReadonlyObject,
        actor_id: str,
        checkpoint: ReadonlyObject,
        transaction_result: ReadonlyObject,
        /,
    ) -> SerializedObject: ...


class CompoundActivityCheckpointValidator(Protocol):
    def __call__(
        self,
        checkpoint: ReadonlyObject,
        /,
    ) -> None: ...


class HostActivityInputEnricher(Protocol):
    def __call__(
        self,
        state: ReadonlyObject,
        actor: ReadonlyObject,
        ability: ReadonlyObject,
        intent: ReadonlyObject,
        /,
    ) -> SerializedObject: ...


@dataclass(frozen=True, order=True, slots=True)
class ControllerIntentDescriptor:
    """One package-owned controller action and its public argument keys."""

    action_id: str
    argument_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_key(self.action_id, "controller intent action_id")
        keys = _string_tuple(
            self.argument_keys,
            "ControllerIntentDescriptor.argument_keys",
        )
        for key in keys:
            _require_key(key, "controller intent argument key")
        if len(set(keys)) != len(keys):
            raise ValueError(
                "controller intent argument keys must not contain duplicates"
            )
        object.__setattr__(self, "argument_keys", tuple(sorted(keys)))

    def to_dict(self) -> SerializedObject:
        return {
            "actionId": self.action_id,
            "argumentKeys": list(self.argument_keys),
        }


class ControllerIntentDescriptorBuilder(Protocol):
    def __call__(
        self,
        ability: ReadonlyObject,
        /,
    ) -> ControllerIntentDescriptor: ...


class ControllerActionEnricher(Protocol):
    """Complete one package-owned non-Activity controller action."""

    def __call__(
        self,
        state: ReadonlyObject,
        actor_id: str,
        intent: ReadonlyObject,
        roll_d20: Callable[[], int],
        /,
    ) -> SerializedObject: ...


class ControllerPendingDecisionProjector(Protocol):
    def __call__(
        self,
        decision: ReadonlyObject,
        /,
    ) -> SerializedObject: ...


class ReactionResolver(Protocol):
    def __call__(
        self,
        state: SerializedObject,
        actor_id: str,
        action: ReadonlyObject,
        ability: ReadonlyObject,
        decision: ReadonlyObject,
        /,
    ) -> SerializedObject: ...


class ReactionQueueBuilder(Protocol):
    def __call__(
        self,
        state: ReadonlyObject,
        queued: ReadonlyObject,
        /,
    ) -> SerializedObject | None: ...


class PostEventHook(Protocol):
    def __call__(
        self,
        state: ReadonlyObject,
        event: ReadonlyObject,
        /,
    ) -> Sequence[SerializedObject]: ...


class PendingDecisionResolver(Protocol):
    def __call__(
        self,
        state: SerializedObject,
        actor_id: str,
        action: ReadonlyObject,
        /,
    ) -> SerializedObject: ...


class PostActionResultHook(Protocol):
    def __call__(
        self,
        state: SerializedObject,
        actor_id: str,
        event: SerializedObject,
        /,
    ) -> SerializedObject: ...


class TurnStartObserver(Protocol):
    def __call__(
        self,
        state: SerializedObject,
        participant_id: str,
        /,
    ) -> ReadonlyObject: ...


class MovementInsideKeyBuilder(Protocol):
    def __call__(
        self,
        state: SerializedObject,
        target_id: str,
        /,
    ) -> set[tuple[str, str]]: ...


class MovementEntryCandidateBuilder(Protocol):
    def __call__(
        self,
        state: SerializedObject,
        target_id: str,
        position: ReadonlyObject,
        occupied: Sequence[ReadonlyObject],
        before_keys: set[tuple[str, str]],
        /,
    ) -> tuple[Sequence[SerializedObject], set[tuple[str, str]]]: ...


class MovementDecisionQueuer(Protocol):
    def __call__(
        self,
        state: SerializedObject,
        candidates: Sequence[ReadonlyObject],
        resume: ReadonlyObject,
        /,
    ) -> SerializedObject | None: ...


class BattlegroundAdjudicationNormalizer(Protocol):
    """Normalize one package-owned private battleground ruling matrix."""

    def __call__(
        self,
        payload: object,
        *,
        participants: Sequence[ReadonlyObject],
        definitions: Mapping[str, ReadonlyObject],
    ) -> SerializedObject | None: ...


class StateValidator(Protocol):
    """Reject invalid package-owned state without changing it."""

    def __call__(self, state: SerializedObject, /) -> None: ...


class SpellEffectOptionBuilder(Protocol):
    """Project availability for one selected package-owned spell effect."""

    def __call__(
        self,
        state: ReadonlyObject,
        actor: ReadonlyObject,
        spell: ReadonlyObject,
        action_count: int | None,
        /,
    ) -> SerializedObject: ...


class SpellEffectResolver(Protocol):
    """Resolve one selected package-owned spell effect."""

    def __call__(
        self,
        state: SerializedObject,
        actor_id: str,
        action: ReadonlyObject,
        spell: ReadonlyObject,
        /,
    ) -> SerializedObject: ...


class EventRenderer(Protocol):
    def __call__(
        self,
        event: ReadonlyObject,
        participants: ParticipantIndex,
        definitions: ParticipantIndex,
        /,
    ) -> str: ...


class PublicStateProjector(Protocol):
    def __call__(
        self,
        state: ReadonlyObject,
        context: ReadonlyObject,
        /,
    ) -> SerializedObject: ...


@dataclass(frozen=True, slots=True)
class AbilityCompilerRegistration:
    compiler_id: str
    mechanic_type: str
    compiler: AbilityCompiler

    def __post_init__(self) -> None:
        _require_key(self.compiler_id, "compiler_id")
        _require_key(self.mechanic_type, "compiler mechanic_type")
        _require_callable(self.compiler, "compiler")

    def match(
        self,
        source: AbilitySource,
    ) -> AbilityCompilerPatch | None:
        patch = self.compiler(source)
        if patch is None:
            return None
        if not isinstance(patch, AbilityCompilerPatch):
            raise TypeError(
                f"compiler {self.compiler_id!r} returned "
                f"{type(patch).__name__}, not AbilityCompilerPatch or None"
            )
        if patch.mechanic_type != self.mechanic_type:
            raise ValueError(
                f"compiler {self.compiler_id!r} returned mechanic type "
                f"{patch.mechanic_type!r}, expected {self.mechanic_type!r}"
            )
        return patch


@dataclass(frozen=True, slots=True)
class ActivityHandlerRegistration:
    mechanic_type: str
    build_options: ActivityOptionBuilder
    resolve: ActivityResolver

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "activity mechanic_type")
        _require_callable(self.build_options, "activity build_options")
        _require_callable(self.resolve, "activity resolve")


@dataclass(frozen=True, slots=True)
class CompoundActivityHandlerRegistration:
    """One closed package-owned multi-stage Activity state machine.

    The handler owns only its immutable checkpoint and choice of the next
    kernel transaction.  It never receives reaction-window callbacks and it
    never commits movement, saves, damage, or event sequence numbers.
    """

    mechanic_type: str
    start: CompoundActivityStarter
    resume: CompoundActivityResumer
    validate_checkpoint: CompoundActivityCheckpointValidator

    def __post_init__(self) -> None:
        _require_key(
            self.mechanic_type,
            "compound activity mechanic_type",
        )
        _require_callable(self.start, "compound activity start")
        _require_callable(self.resume, "compound activity resume")
        _require_callable(
            self.validate_checkpoint,
            "compound activity validate_checkpoint",
        )


@dataclass(frozen=True, slots=True)
class HostActivityInputEnricherRegistration:
    mechanic_type: str
    enrich: HostActivityInputEnricher

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "host activity enricher mechanic_type")
        _require_callable(self.enrich, "host activity enrich")


@dataclass(frozen=True, slots=True)
class ControllerIntentDescriptorRegistration:
    mechanic_type: str
    describe: ControllerIntentDescriptorBuilder

    def __post_init__(self) -> None:
        _require_key(
            self.mechanic_type,
            "controller intent descriptor mechanic_type",
        )
        _require_callable(self.describe, "controller intent describe")


@dataclass(frozen=True, slots=True)
class ControllerActionRegistration:
    """One package-owned pending-decision action exposed to controllers."""

    mechanic_type: str
    action_type: str
    descriptor: ControllerIntentDescriptor
    project_pending: ControllerPendingDecisionProjector
    enrich: ControllerActionEnricher

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "controller action mechanic_type")
        _require_key(self.action_type, "controller action type")
        if not isinstance(self.descriptor, ControllerIntentDescriptor):
            raise TypeError(
                "controller action descriptor must be a "
                "ControllerIntentDescriptor"
            )
        _require_callable(
            self.project_pending,
            "controller action project_pending",
        )
        _require_callable(self.enrich, "controller action enrich")


@dataclass(frozen=True, slots=True)
class ReactionHandlerRegistration:
    mechanic_type: str
    resolve: ReactionResolver

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "reaction mechanic_type")
        _require_callable(self.resolve, "reaction resolve")


@dataclass(frozen=True, slots=True)
class ReactionQueueHandlerRegistration:
    queue_kind: str
    build_decision: ReactionQueueBuilder

    def __post_init__(self) -> None:
        _require_key(self.queue_kind, "reaction queue_kind")
        _require_callable(self.build_decision, "reaction build_decision")


@dataclass(frozen=True, slots=True)
class PostEventHookRegistration:
    hook_id: str
    observe: PostEventHook

    def __post_init__(self) -> None:
        _require_key(self.hook_id, "post-event hook_id")
        _require_callable(self.observe, "post-event observe")


@dataclass(frozen=True, slots=True)
class PendingDecisionHandlerRegistration:
    mechanic_type: str
    decision_type: str
    resolve: PendingDecisionResolver

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "pending decision mechanic_type")
        _require_key(self.decision_type, "pending decision type")
        _require_callable(self.resolve, "pending decision resolve")


@dataclass(frozen=True, slots=True)
class PostActionResultHookRegistration:
    mechanic_type: str
    hook_id: str
    action_type: str
    apply: PostActionResultHook

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "post-action mechanic_type")
        _require_key(self.hook_id, "post-action hook_id")
        _require_key(self.action_type, "post-action action_type")
        _require_callable(self.apply, "post-action apply")


@dataclass(frozen=True, slots=True)
class TurnStartHookRegistration:
    mechanic_type: str
    hook_id: str
    ordinal: int
    observe: TurnStartObserver

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "turn-start mechanic_type")
        _require_key(self.hook_id, "turn-start hook_id")
        object.__setattr__(
            self,
            "ordinal",
            _require_nonnegative_ordinal(
                self.ordinal,
                "turn-start ordinal",
            ),
        )
        _require_callable(self.observe, "turn-start observe")


@dataclass(frozen=True, slots=True)
class MovementExposureRegistration:
    mechanic_type: str
    exposure_id: str
    inside_keys: MovementInsideKeyBuilder
    entry_candidates: MovementEntryCandidateBuilder
    queue_decisions: MovementDecisionQueuer

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "movement exposure mechanic_type")
        _require_key(self.exposure_id, "movement exposure_id")
        _require_callable(self.inside_keys, "movement exposure inside_keys")
        _require_callable(
            self.entry_candidates,
            "movement exposure entry_candidates",
        )
        _require_callable(
            self.queue_decisions,
            "movement exposure queue_decisions",
        )


@dataclass(frozen=True, slots=True)
class ActivityRuntimeContext:
    """Selected non-serialized runtime services available to an activity."""

    movement_exposures: Mapping[str, MovementExposureRegistration]

    def __post_init__(self) -> None:
        if not isinstance(self.movement_exposures, Mapping):
            raise TypeError(
                "activity runtime movement_exposures must be a mapping"
            )
        normalized: dict[str, MovementExposureRegistration] = {}
        for exposure_id, registration in sorted(
            self.movement_exposures.items()
        ):
            _require_key(
                exposure_id,
                "activity runtime movement exposure_id",
            )
            if not isinstance(
                registration,
                MovementExposureRegistration,
            ):
                raise TypeError(
                    "activity runtime movement exposures must contain only "
                    "MovementExposureRegistration values"
                )
            if registration.exposure_id != exposure_id:
                raise ValueError(
                    "activity runtime movement exposure key does not match "
                    "its registration"
                )
            normalized[exposure_id] = registration
        object.__setattr__(
            self,
            "movement_exposures",
            MappingProxyType(normalized),
        )


@dataclass(frozen=True, slots=True)
class BattlegroundAdjudicationNormalizerRegistration:
    mechanic_type: str
    adjudication_key: str
    normalize: BattlegroundAdjudicationNormalizer

    def __post_init__(self) -> None:
        _require_key(
            self.mechanic_type,
            "battleground adjudication mechanic_type",
        )
        _require_key(
            self.adjudication_key,
            "battleground adjudication key",
        )
        _require_callable(
            self.normalize,
            "battleground adjudication normalize",
        )


@dataclass(frozen=True, slots=True)
class StateValidatorRegistration:
    mechanic_type: str
    validator_id: str
    validate: StateValidator

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "state validator mechanic_type")
        _require_key(self.validator_id, "state validator_id")
        _require_callable(self.validate, "state validator validate")


@dataclass(frozen=True, slots=True)
class SpellEffectHandlerRegistration:
    """One exact effect/mechanic handler owned by a selected family."""

    effect_type: str
    mechanic_type: str
    build_option: SpellEffectOptionBuilder
    resolve: SpellEffectResolver

    def __post_init__(self) -> None:
        _require_key(self.effect_type, "spell effect_type")
        _require_key(self.mechanic_type, "spell effect mechanic_type")
        _require_callable(self.build_option, "spell effect build_option")
        _require_callable(self.resolve, "spell effect resolve")

    @property
    def key(self) -> SpellEffectHandlerKey:
        return self.effect_type, self.mechanic_type


@dataclass(frozen=True, slots=True)
class EventRendererRegistration:
    event_type: str
    mechanic_type: str
    renderer: EventRenderer

    def __post_init__(self) -> None:
        _require_key(self.event_type, "renderer event_type")
        _require_key(self.mechanic_type, "renderer mechanic_type")
        _require_callable(self.renderer, "renderer")

    @property
    def key(self) -> RendererKey:
        return self.event_type, self.mechanic_type


@dataclass(frozen=True, slots=True)
class PublicStateProjectorRegistration:
    """One package-owned contribution to a public encounter projection."""

    mechanic_type: str
    projector_id: str
    project: PublicStateProjector

    def __post_init__(self) -> None:
        _require_key(self.mechanic_type, "public projector mechanic_type")
        _require_key(self.projector_id, "public projector_id")
        _require_callable(self.project, "public projector")


@dataclass(frozen=True, slots=True)
class MechanicFamilyFragment:
    """One family's complete, statically registered extension surface."""

    family_id: str
    mechanic_types: tuple[str, ...] = ()
    ability_compilers: tuple[AbilityCompilerRegistration, ...] = ()
    activity_handlers: tuple[ActivityHandlerRegistration, ...] = ()
    compound_activity_handlers: tuple[
        CompoundActivityHandlerRegistration,
        ...,
    ] = ()
    host_activity_input_enrichers: tuple[
        HostActivityInputEnricherRegistration,
        ...,
    ] = ()
    controller_intent_descriptors: tuple[
        ControllerIntentDescriptorRegistration,
        ...,
    ] = ()
    controller_actions: tuple[ControllerActionRegistration, ...] = ()
    reaction_handlers: tuple[ReactionHandlerRegistration, ...] = ()
    reaction_queue_handlers: tuple[
        ReactionQueueHandlerRegistration,
        ...,
    ] = ()
    post_event_hooks: tuple[PostEventHookRegistration, ...] = ()
    pending_decision_handlers: tuple[
        PendingDecisionHandlerRegistration,
        ...,
    ] = ()
    post_action_result_hooks: tuple[
        PostActionResultHookRegistration,
        ...,
    ] = ()
    turn_start_hooks: tuple[TurnStartHookRegistration, ...] = ()
    movement_exposures: tuple[MovementExposureRegistration, ...] = ()
    battleground_adjudication_normalizers: tuple[
        BattlegroundAdjudicationNormalizerRegistration,
        ...,
    ] = ()
    state_validators: tuple[StateValidatorRegistration, ...] = ()
    spell_effect_handlers: tuple[SpellEffectHandlerRegistration, ...] = ()
    event_renderers: tuple[EventRendererRegistration, ...] = ()
    public_state_projectors: tuple[
        PublicStateProjectorRegistration,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        _require_key(self.family_id, "family_id")
        object.__setattr__(
            self,
            "mechanic_types",
            _string_tuple(
                self.mechanic_types,
                "MechanicFamilyFragment.mechanic_types",
            ),
        )
        for field_name in (
            "ability_compilers",
            "activity_handlers",
            "compound_activity_handlers",
            "host_activity_input_enrichers",
            "controller_intent_descriptors",
            "controller_actions",
            "reaction_handlers",
            "reaction_queue_handlers",
            "post_event_hooks",
            "pending_decision_handlers",
            "post_action_result_hooks",
            "turn_start_hooks",
            "movement_exposures",
            "battleground_adjudication_normalizers",
            "state_validators",
            "spell_effect_handlers",
            "event_renderers",
            "public_state_projectors",
        ):
            object.__setattr__(
                self,
                field_name,
                _ordered_tuple(
                    getattr(self, field_name),
                    f"MechanicFamilyFragment.{field_name}",
                ),
            )
        for mechanic_type in self.mechanic_types:
            _require_key(mechanic_type, "family mechanic_type")


__all__ = [
    "AbilityCompiler",
    "AbilityCompilerPatch",
    "AbilityCompilerRegistration",
    "AbilityKind",
    "AbilitySource",
    "ActionCost",
    "ActivityHandlerRegistration",
    "ActivityOptionBuilder",
    "ActivityResolver",
    "ActivityRuntimeContext",
    "CompoundActivityCheckpointValidator",
    "CompoundActivityHandlerRegistration",
    "CompoundActivityRequestKind",
    "CompoundActivityResumer",
    "CompoundActivityStarter",
    "AnnotatedStatCompiler",
    "AnnotatedStatCompilerAmbiguityError",
    "AnnotatedStatCompilerRegistration",
    "AnnotatedStatPatch",
    "AnnotatedStatSource",
    "BattlegroundAdjudicationNormalizer",
    "BattlegroundAdjudicationNormalizerRegistration",
    "ControllerIntentDescriptor",
    "ControllerIntentDescriptorBuilder",
    "ControllerIntentDescriptorRegistration",
    "ControllerActionEnricher",
    "ControllerActionRegistration",
    "ControllerPendingDecisionProjector",
    "EventRenderer",
    "EventRendererRegistration",
    "HostActivityInputEnricher",
    "HostActivityInputEnricherRegistration",
    "MechanicFamilyFragment",
    "MovementDecisionQueuer",
    "MovementEntryCandidateBuilder",
    "MovementExposureRegistration",
    "MovementInsideKeyBuilder",
    "ParticipantIndex",
    "PendingDecisionHandlerRegistration",
    "PendingDecisionResolver",
    "PostActionResultHook",
    "PostActionResultHookRegistration",
    "PostEventHook",
    "PostEventHookRegistration",
    "PublicStateProjector",
    "PublicStateProjectorRegistration",
    "RawSourceArray",
    "RawSourceMember",
    "RawSourceObject",
    "RawSourcePathStep",
    "RawSourcePrimitive",
    "RawSourceValue",
    "ReactionHandlerRegistration",
    "ReactionQueueBuilder",
    "ReactionQueueHandlerRegistration",
    "ReactionResolver",
    "ReadonlyObject",
    "RendererKey",
    "RuleReference",
    "SerializedObject",
    "StateValidator",
    "StateValidatorRegistration",
    "SpellEffectHandlerKey",
    "SpellEffectHandlerRegistration",
    "SpellEffectOptionBuilder",
    "SpellEffectResolver",
    "StrikeRiderCompiler",
    "StrikeRiderCompilerAmbiguityError",
    "StrikeRiderCompilerPatch",
    "StrikeRiderCompilerRegistration",
    "StrikeRiderSource",
    "TurnStartHookRegistration",
    "TurnStartObserver",
    "match_annotated_stat_compilers",
    "match_strike_rider_compilers",
]

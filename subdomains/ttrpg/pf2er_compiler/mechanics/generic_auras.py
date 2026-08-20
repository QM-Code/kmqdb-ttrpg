"""Compile the reviewed Monster Core Aura corpus without runtime activation.

``Aura`` is a source convention rather than one executable mechanic.  This
module authenticates the complete reviewed Core MC1 Aura corpus, preserves its
five duplicate-aware source shapes, resolves every convention/effect provider
through one server-owned :class:`SourceAuthorityAdapter`, and emits immutable
compile-only artifacts.

The public compiler deliberately accepts no caller-authored review packet or
link evidence.  A caller supplies one exact ``VerifiedSourceSelection`` and
the adapter that created it.  The compiler resolves the reviewed consumer and
all providers again from a private address table.  Emanation prose, controller
abilities, copied values, and otherwise-valid rules from another authority do
not manufacture Aura membership.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Literal, TypeAlias, final

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RawSourceValue,
    SerializedObject,
)
from .source_authority import (
    AuthoritySnapshot,
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceAddress,
    SourceAuthorityAdapter,
    SourceReceipt,
    TextSpan,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
)


FAMILY_ID = "generic-aura"
MONSTER_CORE_SOURCE_ID = "core-mc1"
MAX_AURA_SOURCE_BYTES = 65_536
MAX_AURA_SOURCE_MEMBERS = 32
MAX_AURA_TRAITS = 32
MAX_AURA_PARAGRAPHS = 16
REVIEWED_AURA_RECORD_COUNT = 95
REVIEWED_AURA_CREATURE_COUNT = 91
REVIEWED_AURA_DECLARATION_COUNT = 96
REVIEWED_AURA_NEAR_MISS_COUNT = 79
REVIEWED_AURA_IDENTITY_SHA256 = (
    "bf047c4aa1d42279dc2f359a42a40194b9b6249fab3193c332d63b85b277697b"
)
REVIEWED_AURA_SEMANTIC_SHA256 = (
    "c6757ff3a565079b851bd0d9e2d7a63e5d4b583a959e2b83297ee7d56ed592ea"
)
REVIEWED_AURA_NEAR_MISS_SHA256 = (
    "7fa93ef9b1f37b0ccc7b9a68d4b37dcaf0ce1fffd996e78722646c9852f1e4ba"
)
REVIEWED_AURA_LINK_SHA256 = (
    "f2fc8e1f52287c546e05425299515dfb3a701e9ab2dcc34b07fa7912f46c7aba"
)

AuraEncoding: TypeAlias = Literal[
    "inline-scalar",
    "structured-passive",
    "structured-action",
    "structured-reaction",
    "ordered-paragraph-flow",
]
AuraGrammarCohort: TypeAlias = Literal[
    "action-bearing-aura",
    "direct-local-aura",
    "frightful-presence-overlay",
    "frightful-presence-shorthand",
    "generic-damage-only-shorthand",
    "local-same-name-inheritance",
    "section-rule-overlay",
    "stench-shorthand",
]
AuraRouteFamily: TypeAlias = Literal[
    "action-aura-local",
    "frightful-presence",
    "frightful-presence-overlay",
    "generic-aura-damage-only",
    "local-aura-effect",
    "local-aura-inheritance",
    "nymphs-beauty",
    "stench",
]
DeferredAuraKind: TypeAlias = Literal[
    "action-aura-runtime",
    "generic-aura-runtime",
    "linked-effect-runtime",
    "local-effect-adapter",
    "non-grid-domain",
    "source-repair",
    "specialized-family-handoff",
    "timing-policy",
]
ActionCost: TypeAlias = int | Literal["reaction"] | None
_PathClaim: TypeAlias = tuple[tuple[object, ...], ...]

_ENCODINGS = frozenset(
    {
        "inline-scalar",
        "structured-passive",
        "structured-action",
        "structured-reaction",
        "ordered-paragraph-flow",
    }
)
_COHORTS = frozenset(
    {
        "action-bearing-aura",
        "direct-local-aura",
        "frightful-presence-overlay",
        "frightful-presence-shorthand",
        "generic-damage-only-shorthand",
        "local-same-name-inheritance",
        "section-rule-overlay",
        "stench-shorthand",
    }
)
_ROUTE_FAMILIES = frozenset(
    {
        "action-aura-local",
        "frightful-presence",
        "frightful-presence-overlay",
        "generic-aura-damage-only",
        "local-aura-effect",
        "local-aura-inheritance",
        "nymphs-beauty",
        "stench",
    }
)
_AREA_SOURCE_SYNTAX = frozenset(
    {
        "claimed-domain-radius",
        "domain-distance",
        "embedded-foot-emanation",
        "leading-feet",
        "linked-section-rule",
        "trigger-range",
    }
)
_GEOMETRY_MODELS = frozenset(
    {
        "claimed-island-domain",
        "participant-centered-domain",
        "participant-emanation",
        "reaction-trigger-radius",
    }
)
_EXPOSURE_TRIGGERS = frozenset(
    {"each-round-ambiguous", "end-turn", "entry", "start-turn"}
)
_SAVE_KINDS = frozenset({"Fortitude", "Reflex", "Will"})
_SENSORY_TRAITS = frozenset({"auditory", "olfactory", "visual"})
_SENSORY_ADJACENT_TRAITS = frozenset({"light", "sonic"})
_DEFERRED_KINDS = frozenset(
    {
        "action-aura-runtime",
        "generic-aura-runtime",
        "linked-effect-runtime",
        "local-effect-adapter",
        "non-grid-domain",
        "source-repair",
        "specialized-family-handoff",
        "timing-policy",
    }
)
_LINK_KINDS = frozenset(
    {
        "exact-aura-trait-convention",
        "exact-specialized-shorthand",
        "exact-specialized-overlay",
        "exact-local-same-name-inheritance",
        "exact-section-shared-rule-overlay",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ABILITY_KEY_RE = re.compile(r"^!\.(?P<label>.+)$", re.DOTALL)
_TRAIT_GROUP_RE = re.compile(r"\((?P<traits>[^()]*)\)", re.DOTALL)
_LEADING_TRAIT_GROUP_RE = re.compile(
    r"^\s*\((?P<traits>[^()]*)\)",
    re.DOTALL,
)


class AuraCompileError(ValueError):
    """Aura-shaped source was unsupported, inconsistent, or ambiguous."""


class AuraAddressabilityError(ValueError):
    """An Aura production is not the reviewed exact source selection."""


class AuraLinkError(ValueError):
    """An exact Aura provider could not be resolved under shared authority."""


def _trimmed(
    value: object,
    label: str,
    _exact_type: Any = type,
) -> str:
    if _exact_type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    return value


def _sha256(
    value: object,
    label: str,
    _exact_type: Any = type,
    _digest_pattern: re.Pattern[str] = _SHA256_RE,
) -> str:
    if (
        _exact_type(value) is not str
        or _digest_pattern.fullmatch(value) is None
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive(
    value: object,
    label: str,
    _exact_type: Any = type,
) -> int:
    if _exact_type(value) is not int or value <= 0 or value > (1 << 63) - 1:
        raise ValueError(f"{label} must be a positive signed-64 integer")
    return value


def _exact_strings(
    value: object,
    label: str,
    *,
    allowed: frozenset[str] | None = None,
    maximum: int = MAX_AURA_TRAITS,
    unique: bool = True,
    _exact_type: Any = type,
    _list_type: type[list[object]] = list,
    _tuple_type: type[tuple[object, ...]] = tuple,
    _length: Any = len,
    _set_type: Any = set,
    _reject_any: Any = any,
) -> tuple[str, ...]:
    if _exact_type(value) not in {_list_type, _tuple_type}:
        raise TypeError(f"{label} must be an exact ordered sequence")
    if _length(value) > maximum:
        raise ValueError(f"{label} exceeds its bound")
    result = _tuple_type(value)
    if _reject_any(
        _exact_type(item) is not str or not item for item in result
    ):
        raise TypeError(f"{label} must contain exact non-empty strings")
    if unique and _length(result) != _length(_set_type(result)):
        raise ValueError(f"{label} contains duplicates")
    if allowed is not None and _reject_any(
        item not in allowed for item in result
    ):
        raise ValueError(f"{label} contains an unsupported value")
    return result


@final
@dataclass(frozen=True, slots=True)
class AuraRuleTarget:
    """Public description of one canonical reviewed provider."""

    rule_id: str
    authority_locator: str
    printed_locator: str
    source_ordinal: int
    expected_selection_sha256: str

    def __post_init__(self) -> None:
        if type(self) is not AuraRuleTarget:
            raise TypeError("AuraRuleTarget subclasses are not supported")
        _trimmed(self.rule_id, "AuraRuleTarget.rule_id")
        _trimmed(
            self.authority_locator,
            "AuraRuleTarget.authority_locator",
        )
        _trimmed(self.printed_locator, "AuraRuleTarget.printed_locator")
        if type(self.source_ordinal) is not int or self.source_ordinal < 0:
            raise ValueError("AuraRuleTarget.source_ordinal is invalid")
        _sha256(
            self.expected_selection_sha256,
            "AuraRuleTarget.expected_selection_sha256",
        )

    def as_serialized(self) -> SerializedObject:
        if type(self) is not AuraRuleTarget:
            raise TypeError("AuraRuleTarget must be exact")
        self.__post_init__()
        return {
            "ruleId": self.rule_id,
            "sourceId": MONSTER_CORE_SOURCE_ID,
            "authorityLocator": self.authority_locator,
            "printedLocator": self.printed_locator,
            "sourceOrdinal": self.source_ordinal,
            "expectedSelectionSha256": self.expected_selection_sha256,
        }


AURA_RULE = AuraRuleTarget(
    rule_id="core-mc1:ability-glossary#^.ability[003]",
    authority_locator="358.2",
    printed_locator="358.6",
    source_ordinal=3,
    expected_selection_sha256=(
        "3f30455106cbb35f3f791ee121f33ea5612636ffd692c4fbbe825667ffb2ec39"
    ),
)
FRIGHTFUL_PRESENCE_RULE = AuraRuleTarget(
    rule_id="core-mc1:ability-glossary#^.ability[014]",
    authority_locator="358.2",
    printed_locator="359.6",
    source_ordinal=14,
    expected_selection_sha256=(
        "0b12b73e5bed46f72f225f50048136f6871b4cc051ec2cf0ea1d956915e7dc92"
    ),
)
STENCH_RULE = AuraRuleTarget(
    rule_id="core-mc1:ability-glossary#^.ability[030]",
    authority_locator="358.2",
    printed_locator="360.5",
    source_ordinal=30,
    expected_selection_sha256=(
        "189c0083d5b9ae7db0abc7a4af237abbb3548e09cb903a2b254a0362afb1f968"
    ),
)
NYMPHS_BEAUTY_RULE = AuraRuleTarget(
    rule_id="core-mc1:nymph#shared-nymphs-beauty",
    authority_locator="245.4",
    printed_locator="245.4",
    source_ordinal=3,
    expected_selection_sha256=(
        "8e0dc7c2b1beb09d5b1b5cee55beb2b07e1dedc87726fea9f67697c691f3036b"
    ),
)


@final
@dataclass(frozen=True, slots=True)
class AuraArea:
    source_syntax: str
    geometry_model: str
    value: int
    unit: str
    radius_feet: int | None
    combat_grid_eligible: bool

    def __post_init__(
        self,
        _exact_type: Any = type,
        _self_type: type[AuraArea] = None,
        _positive_value: Any = _positive,
        _trim: Any = _trimmed,
        _bool_type: type[bool] = bool,
    ) -> None:
        if _self_type is None:
            _self_type = AuraArea
        if _exact_type(self) is not _self_type:
            raise TypeError("AuraArea subclasses are not supported")
        if self.source_syntax not in _AREA_SOURCE_SYNTAX:
            raise ValueError("AuraArea.source_syntax is invalid")
        if self.geometry_model not in _GEOMETRY_MODELS:
            raise ValueError("AuraArea.geometry_model is invalid")
        _positive_value(self.value, "AuraArea.value")
        _trim(self.unit, "AuraArea.unit")
        if _exact_type(self.combat_grid_eligible) is not _bool_type:
            raise TypeError("AuraArea.combat_grid_eligible must be exact bool")
        if self.radius_feet is not None:
            _positive_value(self.radius_feet, "AuraArea.radius_feet")
        if self.combat_grid_eligible:
            if (
                self.unit != "feet"
                or self.radius_feet != self.value
                or self.value % 5
            ):
                raise ValueError("grid Aura area is not exact 5-foot geometry")
        elif self.radius_feet is not None:
            raise ValueError("non-grid Aura area cannot claim feet")

    def as_serialized(self) -> SerializedObject:
        if type(self) is not AuraArea:
            raise TypeError("AuraArea must be exact")
        self.__post_init__()
        result: SerializedObject = {
            "sourceSyntax": self.source_syntax,
            "geometryModel": self.geometry_model,
            "value": self.value,
            "unit": self.unit,
            "combatGridEligible": self.combat_grid_eligible,
        }
        if self.radius_feet is not None:
            result["radiusFeet"] = self.radius_feet
        return result


@final
@dataclass(frozen=True, slots=True)
class AuraTemporaryImmunity:
    duration: int
    unit: str
    grant: str
    scope: str

    def __post_init__(
        self,
        _exact_type: Any = type,
        _positive_value: Any = _positive,
        _trim: Any = _trimmed,
        _getattr: Any = getattr,
    ) -> None:
        if _exact_type(self) is not AuraTemporaryImmunity:
            raise TypeError(
                "AuraTemporaryImmunity subclasses are not supported"
            )
        _positive_value(
            self.duration,
            "AuraTemporaryImmunity.duration",
        )
        for field_name in ("unit", "grant", "scope"):
            _trim(
                _getattr(self, field_name),
                f"AuraTemporaryImmunity.{field_name}",
            )

    def as_serialized(self) -> SerializedObject:
        if type(self) is not AuraTemporaryImmunity:
            raise TypeError("AuraTemporaryImmunity must be exact")
        self.__post_init__()
        return {
            "duration": self.duration,
            "unit": self.unit,
            "grant": self.grant,
            "scope": self.scope,
        }


@final
@dataclass(frozen=True, slots=True)
class AuraBehavior:
    exposure_triggers: tuple[str, ...]
    save_kinds: tuple[str, ...]
    temporary_immunity: AuraTemporaryImmunity | None
    sensory_traits: tuple[str, ...]
    sensory_adjacent_traits: tuple[str, ...]
    generic_damage_only_once_per_round: bool
    runnable_source: bool

    def __post_init__(
        self,
        _exact_type: Any = type,
        _setattr: Any = object.__setattr__,
        _exact_sequence: Any = _exact_strings,
        _getattr: Any = getattr,
        _bool_type: type[bool] = bool,
    ) -> None:
        if _exact_type(self) is not AuraBehavior:
            raise TypeError("AuraBehavior subclasses are not supported")
        _setattr(
            self,
            "exposure_triggers",
            _exact_sequence(
                self.exposure_triggers,
                "AuraBehavior.exposure_triggers",
                allowed=_EXPOSURE_TRIGGERS,
            ),
        )
        _setattr(
            self,
            "save_kinds",
            _exact_sequence(
                self.save_kinds,
                "AuraBehavior.save_kinds",
                allowed=_SAVE_KINDS,
            ),
        )
        _setattr(
            self,
            "sensory_traits",
            _exact_sequence(
                self.sensory_traits,
                "AuraBehavior.sensory_traits",
                allowed=_SENSORY_TRAITS,
            ),
        )
        _setattr(
            self,
            "sensory_adjacent_traits",
            _exact_sequence(
                self.sensory_adjacent_traits,
                "AuraBehavior.sensory_adjacent_traits",
                allowed=_SENSORY_ADJACENT_TRAITS,
            ),
        )
        if (
            self.temporary_immunity is not None
            and _exact_type(self.temporary_immunity)
            is not AuraTemporaryImmunity
        ):
            raise TypeError("AuraBehavior temporary immunity is not exact")
        for field_name in (
            "generic_damage_only_once_per_round",
            "runnable_source",
        ):
            if _exact_type(_getattr(self, field_name)) is not _bool_type:
                raise TypeError(f"AuraBehavior.{field_name} must be exact bool")

    def as_serialized(self) -> SerializedObject:
        if type(self) is not AuraBehavior:
            raise TypeError("AuraBehavior must be exact")
        self.__post_init__()
        return {
            "exposureTriggers": [
                item for item in self.exposure_triggers
            ],
            "saveKinds": [item for item in self.save_kinds],
            "temporaryImmunity": (
                None
                if self.temporary_immunity is None
                else {
                    "duration": self.temporary_immunity.duration,
                    "unit": self.temporary_immunity.unit,
                    "grant": self.temporary_immunity.grant,
                    "scope": self.temporary_immunity.scope,
                }
            ),
            "sensoryTraits": [item for item in self.sensory_traits],
            "sensoryAdjacentTraits": [
                item for item in self.sensory_adjacent_traits
            ],
            "genericDamageOnlyOncePerRound": (
                self.generic_damage_only_once_per_round
            ),
            "runnableSource": self.runnable_source,
        }


@final
@dataclass(frozen=True, slots=True)
class AuraSourceIssue:
    kind: str
    severity: str
    detail: str

    def __post_init__(
        self,
        _exact_type: Any = type,
        _trim: Any = _trimmed,
        _getattr: Any = getattr,
    ) -> None:
        if _exact_type(self) is not AuraSourceIssue:
            raise TypeError("AuraSourceIssue subclasses are not supported")
        for field_name in ("kind", "severity", "detail"):
            _trim(
                _getattr(self, field_name),
                f"AuraSourceIssue.{field_name}",
            )

    def as_serialized(self) -> SerializedObject:
        if type(self) is not AuraSourceIssue:
            raise TypeError("AuraSourceIssue must be exact")
        self.__post_init__()
        return {
            "kind": self.kind,
            "severity": self.severity,
            "detail": self.detail,
        }


@final
@dataclass(frozen=True, slots=True)
class AuraDamageOnly:
    radius_feet: int
    dice_count: int
    die_sides: int
    damage_type: str
    save_dc: int
    save_kind: str
    source_text: str

    def __post_init__(
        self,
        _exact_type: Any = type,
        _positive_value: Any = _positive,
        _trim: Any = _trimmed,
        _getattr: Any = getattr,
    ) -> None:
        if _exact_type(self) is not AuraDamageOnly:
            raise TypeError("AuraDamageOnly subclasses are not supported")
        for field_name in (
            "radius_feet",
            "dice_count",
            "die_sides",
            "save_dc",
        ):
            _positive_value(
                _getattr(self, field_name),
                f"AuraDamageOnly.{field_name}",
            )
        _trim(self.damage_type, "AuraDamageOnly.damage_type")
        if self.save_kind not in _SAVE_KINDS:
            raise ValueError("AuraDamageOnly.save_kind is invalid")
        _trim(self.source_text, "AuraDamageOnly.source_text")

    def as_serialized(self) -> SerializedObject:
        if type(self) is not AuraDamageOnly:
            raise TypeError("AuraDamageOnly must be exact")
        self.__post_init__()
        return {
            "type": "generic-aura-damage-only",
            "radiusFeet": self.radius_feet,
            "damage": {
                "dice": {
                    "count": self.dice_count,
                    "sides": self.die_sides,
                },
                "type": self.damage_type,
            },
            "save": {
                "dc": self.save_dc,
                "kind": self.save_kind,
                "basic": True,
            },
            "exposureTriggers": ["entry", "start-turn"],
            "oncePerRound": True,
            "sourceText": self.source_text,
        }


@final
@dataclass(frozen=True, slots=True)
class DeferredAuraMechanic:
    kind: DeferredAuraKind
    phase: Literal["source", "link", "runtime"]
    source_text: str
    required_contract: str

    def __post_init__(
        self,
        _exact_type: Any = type,
        _trim: Any = _trimmed,
    ) -> None:
        if _exact_type(self) is not DeferredAuraMechanic:
            raise TypeError(
                "DeferredAuraMechanic subclasses are not supported"
            )
        if self.kind not in _DEFERRED_KINDS:
            raise ValueError("DeferredAuraMechanic.kind is invalid")
        if self.phase not in {"source", "link", "runtime"}:
            raise ValueError("DeferredAuraMechanic.phase is invalid")
        _trim(self.source_text, "DeferredAuraMechanic.source_text")
        _trim(
            self.required_contract,
            "DeferredAuraMechanic.required_contract",
        )

    def as_serialized(self) -> SerializedObject:
        if type(self) is not DeferredAuraMechanic:
            raise TypeError("DeferredAuraMechanic must be exact")
        self.__post_init__()
        return {
            "kind": self.kind,
            "phase": self.phase,
            "sourceText": self.source_text,
            "requiredContract": self.required_contract,
            "status": "deferred",
            "blocks": "registry-activation",
        }


@final
@dataclass(frozen=True, slots=True)
class AuraEffectRoute:
    family_id: AuraRouteFamily
    provider_id: str | None
    link_kind: str | None

    def __post_init__(
        self,
        _exact_type: Any = type,
        _trim: Any = _trimmed,
    ) -> None:
        if _exact_type(self) is not AuraEffectRoute:
            raise TypeError("AuraEffectRoute subclasses are not supported")
        if self.family_id not in _ROUTE_FAMILIES:
            raise ValueError("AuraEffectRoute.family_id is invalid")
        if self.provider_id is not None:
            _trim(self.provider_id, "AuraEffectRoute.provider_id")
        if self.link_kind is not None and self.link_kind not in _LINK_KINDS:
            raise ValueError("AuraEffectRoute.link_kind is invalid")

    def as_serialized(self) -> SerializedObject:
        if type(self) is not AuraEffectRoute:
            raise TypeError("AuraEffectRoute must be exact")
        self.__post_init__()
        result: SerializedObject = {
            "familyId": self.family_id,
            "supportState": "compile-link-only",
        }
        if self.provider_id is not None:
            result["providerId"] = self.provider_id
        if self.link_kind is not None:
            result["linkKind"] = self.link_kind
        return result


@dataclass(frozen=True, slots=True)
class _RawAuraProjection:
    encoding: AuraEncoding
    traits: tuple[str, ...]
    action_cost: ActionCost
    trigger: str
    effect_text: str
    top_level_member_keys: tuple[str, ...]
    aura_declaration_count: int


@dataclass(frozen=True, slots=True)
class _ReviewedAuraSpec:
    record_id: str
    block_sequence: int
    ability_ordinal: int
    locator: str
    creature_name: str
    raw_key: str
    carrier_path: tuple[RawMemberStep | RawIndexStep, ...]
    member_ordinal: int
    expected_block_sha256: str
    expected_member_sha256: str
    expected_selection_sha256: str
    encoding: AuraEncoding
    grammar_cohort: AuraGrammarCohort
    traits: tuple[str, ...]
    action_cost: ActionCost
    trigger: str
    top_level_member_keys: tuple[str, ...]
    aura_declaration_count: int
    area: AuraArea
    behavior: AuraBehavior
    issues: tuple[AuraSourceIssue, ...]
    route_family: AuraRouteFamily
    effect_provider: str | None
    effect_link_kind: str | None
    damage_only: tuple[int, int, int, str, int, str] | None


@dataclass(frozen=True, slots=True)
class _ProviderSpec:
    code: str
    rule_id: str
    relation: Literal["aura-convention", "effect"]
    link_kind: str
    locator: str
    carrier_path: tuple[RawMemberStep | RawIndexStep, ...]
    selection_path: tuple[RawMemberStep | RawIndexStep, ...]
    expected_block_sha256: str | None
    expected_member_sha256: str | None
    expected_selection_sha256: str


def _new_provider_spec(
    *,
    code: str,
    rule_id: str,
    relation: Literal["aura-convention", "effect"],
    link_kind: str,
    locator: str,
    carrier_path: tuple[RawMemberStep | RawIndexStep, ...],
    selection_path: tuple[RawMemberStep | RawIndexStep, ...],
    expected_block_sha256: str | None,
    expected_member_sha256: str | None,
    expected_selection_sha256: str,
    _provider_type: type[_ProviderSpec] = _ProviderSpec,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
) -> _ProviderSpec:
    result = _new(_provider_type)
    _setattr(result, "code", code)
    _setattr(result, "rule_id", rule_id)
    _setattr(result, "relation", relation)
    _setattr(result, "link_kind", link_kind)
    _setattr(result, "locator", locator)
    _setattr(result, "carrier_path", carrier_path)
    _setattr(result, "selection_path", selection_path)
    _setattr(
        result,
        "expected_block_sha256",
        expected_block_sha256,
    )
    _setattr(
        result,
        "expected_member_sha256",
        expected_member_sha256,
    )
    _setattr(
        result,
        "expected_selection_sha256",
        expected_selection_sha256,
    )
    return result


_RAW_REVIEWED_SPECS: tuple[dict[str, Any], ...] = (
    {'record_id': 'core-mc1/aeon#creature-002/ability-000',
     'block_sequence': 3,
     'ability_ordinal': 0,
     'locator': '9.3',
     'creature_name': 'Akhana',
     'raw_key': '!.Envisioning',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 13,
     'expected_block_sha256': '1b7a3bca6e2345564dbdb90f4d8d2e2a66274098809eaa9ad0e8b7cd35e30ccd',
     'expected_member_sha256': '17aeb1446d368ab858a2acfdbd4548cb66f5f55c4f4183e6b9c5113b081412de',
     'expected_selection_sha256': 'f4de3c1e714f827f18ea0f49c9e9f51b38507799886297244a06749f8e3eb649',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 100,
              'unit': 'feet',
              'radiusFeet': 100,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/aeon#creature-003/ability-000',
     'block_sequence': 4,
     'ability_ordinal': 0,
     'locator': '10.2',
     'creature_name': 'Pleroma',
     'raw_key': '!.Envisioning',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 13,
     'expected_block_sha256': '8992cfca200a8a0cce1faa6f77ad7f339355b30621ce1f529f96f234cf7564a6',
     'expected_member_sha256': '16226d55b5b674c0c09dd7f55982be84c2fade8718cebc12b5ff592f4ff694ae',
     'expected_selection_sha256': 'ebc62809a4f42689bb1a0a4b1e5d4a7cd144bb6d29178d04c9c0362afa5d5f24',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'local-same-name-inheritance',
     'traits': ('aura', 'divine', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 100,
              'unit': 'feet',
              'radiusFeet': 100,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-inheritance',
     'effect_provider': 'record:core-mc1/aeon#creature-002/ability-000',
     'effect_link_kind': 'exact-local-same-name-inheritance',
     'damage_only': None},
    {'record_id': 'core-mc1/alghollthu#creature-001/ability-000',
     'block_sequence': 6,
     'ability_ordinal': 0,
     'locator': '12.5',
     'creature_name': 'Vidileth',
     'raw_key': '!.Numbing Lights',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 14,
     'expected_block_sha256': '4464c26de1f7cb4a3409d0264a7e4a64600342aee2b6b4f0beb0e55a52150101',
     'expected_member_sha256': '9f5edb74031c1aa2e37dcb0ac12695d0409423af5f603411c7ac2f054f8ddadf',
     'expected_selection_sha256': 'a113211dc09ad32b566576074b43d42b72d55c6bd5e21bdc361e4863309c62c3',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'light', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['each-round-ambiguous'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': ['light'],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': ({'kind': 'runtime-timing-ambiguous',
                 'severity': 'not-runnable-without-policy',
                 'detail': 'The source says each round without selecting a participant '
                           'turn anchor.'},),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/angel#creature-001/ability-000',
     'block_sequence': 8,
     'ability_ordinal': 0,
     'locator': '15.1',
     'creature_name': 'Choral',
     'raw_key': '!.Harmonizing Aura',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 20,
     'expected_block_sha256': '5ff5a1d1aba8c3bd1a66a1e84e86b0ed3a7f044d5ab6a3d14a0001fe08ac2ac0',
     'expected_member_sha256': 'b5140e649dee9cd81c87c8965931b40f8e622aa801af8e7ad9f75763205fbe46',
     'expected_selection_sha256': '2386d491b155768d9105f71ec207be47fd636affcd77705cc4bcff314eedc89c',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine', 'sonic'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': ['sonic'],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/angel#creature-002/ability-000',
     'block_sequence': 9,
     'ability_ordinal': 0,
     'locator': '15.4',
     'creature_name': 'Balisse',
     'raw_key': "!.Confessor's Aura",
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 21,
     'expected_block_sha256': 'ceeb058f5053a20ce29e4930fcffe2274be133470ddbd90a164942f6218ab306',
     'expected_member_sha256': 'd56bf81d59b691d35a279e2ff004dd8f4d6acef0830d777e93997023af3affdf',
     'expected_selection_sha256': 'f354530bc27f98b1c22f891b2eb0c9a0a2818fee33b8e3cc71f4a7fba9da3863',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/angel#creature-003/ability-000',
     'block_sequence': 10,
     'ability_ordinal': 0,
     'locator': '16.3',
     'creature_name': 'Tabellia',
     'raw_key': "!.Traveler's Aura",
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 20,
     'expected_block_sha256': 'fbb814b3cf9db3297ee2c52980986771057e881b828f5bc7a28b547e495567c5',
     'expected_member_sha256': '76bef3ab29bab87ff130710853e1e2ee4bdb715beabb5ab1cd0a10cc0182f84b',
     'expected_selection_sha256': '6feef0e72567cf9996564cfd9bfad9686dcdd790aefd1af9a4f6a6cd01172f09',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/archon#creature-004/ability-000',
     'block_sequence': 29,
     'ability_ordinal': 0,
     'locator': '29.2',
     'creature_name': 'Giylea',
     'raw_key': '!.All-Knowing Eyes',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 21,
     'expected_block_sha256': '20099405daba3266fa3c0751d20e30772bfdfd720675c10705118555808d3811',
     'expected_member_sha256': 'd642b02bbdd9df61ffa1e98f1b2a690882e0a7b8d7307c65e95c3ed20728d328',
     'expected_selection_sha256': '5f9ae252383a60ef2081fc09af48f6e9a983f74769a2eaed07541ff50ff41ee4',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine', 'mental', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['end-turn'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/bandersnatch#creature-000/ability-001',
     'block_sequence': 37,
     'ability_ordinal': 1,
     'locator': '36.1',
     'creature_name': 'Bandersnatch',
     'raw_key': '!.Confusing Gaze',
     'carrier_path': (('member', 'Bandersnatch', 1),
                      ('member', 'Bandersnatch', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 20,
     'expected_block_sha256': '23d7206d0506cebd4f7f5fe8761e09adfb11df2650cc0b6a7613c468d7848745',
     'expected_member_sha256': 'c9bcfe13458d8b088b79e83293d8ef1af4fb942cb9367ff8dbd9a50572f5f304',
     'expected_selection_sha256': '562f981ffc33fa5e0618c5902d359f44a54c09087ead8373fbea8ddff7011a68',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'emotion', 'mental', 'primal', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['end-turn'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/basilisk#creature-000/ability-000',
     'block_sequence': 40,
     'ability_ordinal': 0,
     'locator': '39.1',
     'creature_name': 'Basilisk',
     'raw_key': '!.Petrifying Glance',
     'carrier_path': (('member', 'Basilisk', 1),
                      ('member', 'Basilisk', 0),
                      ('member', '^.creature', 5)),
     'member_ordinal': 20,
     'expected_block_sha256': 'b25856320622c281d1bd8205c5c4fbdcd1223670cf96106abdf522c4fb2e2fa0',
     'expected_member_sha256': 'a894975f9e51aae6aa9b8d5c94db5fdf94873ccdd0114362ca5f04e055be4e00',
     'expected_selection_sha256': 'ef1e1b5784df049742cea329cf9bf27be562c417e24a1c321bd4657c1d98273d',
     'encoding': 'structured-reaction',
     'grammar_cohort': 'action-bearing-aura',
     'traits': ('arcane', 'aura', 'visual'),
     'action_cost': 'reaction',
     'trigger': 'A creature within 30 feet that the basilisk can see starts its turn',
     'top_level_member_keys': ('Action', 'Traits', 'Trigger', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'trigger-range',
              'geometryModel': 'reaction-trigger-radius',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'action-aura-local',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/beetle#creature-000/ability-000',
     'block_sequence': 45,
     'ability_ordinal': 0,
     'locator': '42.4',
     'creature_name': 'Flash Beetle',
     'raw_key': '!.Luminescent Aura',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 17,
     'expected_block_sha256': 'caf25731505b3001bad1917b08bb42c3bc6c15c5d73a27eeebb3a0d96e299f33',
     'expected_member_sha256': '3bca7c8db1c02299a8555ee26acb5e88d13d95f2d4a008a1edb8949527514667',
     'expected_selection_sha256': '42affe093b34cf2c8bb59ceab1860225391bc0ef2367b15ae2aa843c20331956',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'light'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 10,
              'unit': 'feet',
              'radiusFeet': 10,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': ['light'],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/bogwid#creature-000/ability-000',
     'block_sequence': 52,
     'ability_ordinal': 0,
     'locator': '46.1',
     'creature_name': 'Bogwid',
     'raw_key': '!.Revolting Aura',
     'carrier_path': (('member', 'Bogwid', 1),
                      ('member', 'Bogwid', 0),
                      ('member', '^.creature', 2)),
     'member_ordinal': 18,
     'expected_block_sha256': '0845658e41f0ffb3f825597759067b1a55faa0a9634648a93c709ba0d7518795',
     'expected_member_sha256': '5779442cd51f2c2882d152524fe2269870344c0e150d9d14c5a1eef3244a7a65',
     'expected_selection_sha256': '9fb2864abe3e3b32de688780f676e5fb36c3f0051bac2cad3db984b48cc9cfe5',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/daemon#creature-002/ability-001',
     'block_sequence': 86,
     'ability_ordinal': 1,
     'locator': '74.1',
     'creature_name': 'Leukodaemon',
     'raw_key': '!.Infectious Aura',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 22,
     'expected_block_sha256': '749a4b5c6233f3548dc808ad3001ecf724f329f3e9dc526f2f7479c42fe6bd49',
     'expected_member_sha256': 'c60616cd2254aec1be5747d5aeb4bcebf885c1361b4743ca3f8f48ad56396789',
     'expected_selection_sha256': '741afe3cd32853100ddac31e7ccbda841f215e26e4b7c91150cb72b8752f23b9',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'disease'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/demon#creature-002/ability-000',
     'block_sequence': 90,
     'ability_ordinal': 0,
     'locator': '78.1',
     'creature_name': 'Succubus',
     'raw_key': '!.Seductive Presence',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 20,
     'expected_block_sha256': '0d7d6fe8d6121896e438dcb30060c62f93b771b363c6788bf7e64deb51552380',
     'expected_member_sha256': '395d02cbfaa4d68b06ce1cae0899541ffcf203450ec14e00799f4fdf8b3b42c5',
     'expected_selection_sha256': 'b272fa4fac15b4bb7257fed52bc17b0738f4d79f6324a116ede6f0d3a36179be',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'emotion', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 10,
              'unit': 'feet',
              'radiusFeet': 10,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/demon#creature-004/ability-000',
     'block_sequence': 92,
     'ability_ordinal': 0,
     'locator': '80.1',
     'creature_name': 'Seraptis',
     'raw_key': '!.Blood Healing',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 20,
     'expected_block_sha256': '99794dc1eb679d6fbfa67e38482a5497af28d7923eba4d25891ac3a376f3fe5f',
     'expected_member_sha256': '6f29c50bbf5d3a9690bb61814bfeac27b7d61bb04fb793e9a02bfc55b219c913',
     'expected_selection_sha256': '8eac1aa5838c78bfcfc9305dd8bac7fcdf8e3f40012dc140a16770659b3253d2',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'healing', 'vitality'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/demon#creature-005/ability-000',
     'block_sequence': 93,
     'ability_ordinal': 0,
     'locator': '81.1',
     'creature_name': 'Shemhazian',
     'raw_key': '!.Paralyzing Gaze',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 19,
     'expected_block_sha256': '7dc9a6c6f00e19261cfe6c13d825767787c56b628b1ce172d395f9d6520f3025',
     'expected_member_sha256': 'a2ca260d35372b728775f4c0eeb10925e49fbd861f88422c3104d5b112bb5433',
     'expected_selection_sha256': '2673ca1e1b90a69f246fd38e93aaab8af8d0d8ae31cda80af046862e0a0df941',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine', 'unholy', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['end-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/demon#creature-006/ability-000',
     'block_sequence': 94,
     'ability_ordinal': 0,
     'locator': '82.1',
     'creature_name': 'Vrolikai',
     'raw_key': '!.Death-Stealing Gaze',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 20,
     'expected_block_sha256': 'a3150454864ff1c2e5685daec6ab8fc9bb82fe211cdf8593cf7e98c28c4e488a',
     'expected_member_sha256': '044859b4c2e0048d08a1532652bf56b08ec203dab78a2b2e54b5304bbbe35851',
     'expected_selection_sha256': 'c6611f3b526c6fef57daf995bfdd8e2ed1e01723740b93b75576a5194e8a6e43',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['end-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/devil#creature-003/ability-000',
     'block_sequence': 101,
     'ability_ordinal': 0,
     'locator': '88.3',
     'creature_name': 'Sarglagon',
     'raw_key': '!.Heavy Aura',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 21,
     'expected_block_sha256': '4cc0a04b107af3ef3a68d0cb9fa0df920e5f8976f5c725c42a25bc0f21701114',
     'expected_member_sha256': '2798d7f33a4d192eb74e6f096a59c5353f9296b7aacc70517a3c62b008bbb621',
     'expected_selection_sha256': '1a1a1e34bceac608b66187fe63d4745503332eb0f5610c2b398719fbb5ae470b',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine', 'incapacitation'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 10,
              'unit': 'feet',
              'radiusFeet': 10,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 10,
                                        'unit': 'minutes',
                                        'grant': 'after-save-all-results',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/devil#creature-006/ability-001',
     'block_sequence': 104,
     'ability_ordinal': 1,
     'locator': '92.2',
     'creature_name': 'Nessari',
     'raw_key': "!.Commander's Aura",
     'carrier_path': (('member', '^.creature', 5),),
     'member_ordinal': 22,
     'expected_block_sha256': '02aef8e9de00832deb749267530b62e2cb2fb299f0d83e0404ee920243cb7f54',
     'expected_member_sha256': '52544d8accce728516ab4ca4c80e44a92a834939d3183a5dad929674c0836471',
     'expected_selection_sha256': 'bf5a51e6dc989810e3e1806f6b6013c2be7eefc6d80402b60f1e68e455e16d9e',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 100,
              'unit': 'feet',
              'radiusFeet': 100,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/devil#creature-006/ability-002',
     'block_sequence': 104,
     'ability_ordinal': 2,
     'locator': '92.2',
     'creature_name': 'Nessari',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 5),),
     'member_ordinal': 23,
     'expected_block_sha256': '02aef8e9de00832deb749267530b62e2cb2fb299f0d83e0404ee920243cb7f54',
     'expected_member_sha256': '017f71e9f65f38f9ffc44a448e1a808416be3f9fa448595c484a34921d5ce904',
     'expected_selection_sha256': '8c9d8e972ae33fc9b7b1516d2ea285ccb26c38d71cddcc28ee5b229512c66d58',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'divine', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dezullon#creature-000/ability-000',
     'block_sequence': 105,
     'ability_ordinal': 0,
     'locator': '94.1',
     'creature_name': 'Dezullon',
     'raw_key': '!.Stench',
     'carrier_path': (('member', 'Dezullon', 1),
                      ('member', 'Dezullon', 0),
                      ('member', '^.creature', 4)),
     'member_ordinal': 18,
     'expected_block_sha256': 'e2e92265b16c6d37c4d912857208847343aad0fac45de833c9731d2293786a68',
     'expected_member_sha256': 'e88de1378737771472058f89e3c70de58e9ef820a160c1f5a25857f3feada4c4',
     'expected_selection_sha256': '3f7170513c3bf9fb85c8a8673e33236ce9f802be6ff1623b85bd9b52a125541f',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dominion-of-the-black#creature-003/ability-002',
     'block_sequence': 124,
     'ability_ordinal': 2,
     'locator': '107.1',
     'creature_name': 'Gosreg',
     'raw_key': '!.Unsettled Aura',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 23,
     'expected_block_sha256': 'b3fdf0e8b2cebcf5bbe10948addee22717b1b1fd28bbb16158172ba79ec4df51',
     'expected_member_sha256': 'ac8399f57343964f66b7c662c99c85eb0ef4e80a67887b82356f94d85fd129d3',
     'expected_selection_sha256': 'ef649cd78deac276fb9213ae38490ae519d99939d5d415d8a82671abdd1a5f94',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'mental', 'occult'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-000/ability-001',
     'block_sequence': 125,
     'ability_ordinal': 1,
     'locator': '108.4',
     'creature_name': 'Young Adamantine Dragon',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 24,
     'expected_block_sha256': 'bcca5fd723f6d78876f227348d6928c4405d3a0c5bcb9a2cc24c90194271ac3d',
     'expected_member_sha256': 'b3d72b1bda5181205ec1437b412e46598e6ade41a502ac3e72714e03a562ed05',
     'expected_selection_sha256': '786706feba892811bd94d982c1af371b000a27a563cbd729a8771a5b83c01972',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 90,
              'unit': 'feet',
              'radiusFeet': 90,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-001/ability-001',
     'block_sequence': 126,
     'ability_ordinal': 1,
     'locator': '108.4',
     'creature_name': 'Adult Adamantine Dragon',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 24,
     'expected_block_sha256': '66ec0887183736dd2e6f70bc54da3b88a2316099931a1720c48c7f83a0fdadae',
     'expected_member_sha256': '04d10d148b4af4b80a627f897d82a5ef970fbcc2f166b2b0829b66adaceddcd3',
     'expected_selection_sha256': '30fc11b3f7cc8d60eb2a6500a32a15f6a0e724732e6d23f6c3d88f22568b6353',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 90,
              'unit': 'feet',
              'radiusFeet': 90,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-002/ability-001',
     'block_sequence': 127,
     'ability_ordinal': 1,
     'locator': '108.4',
     'creature_name': 'Ancient Adamantine Dragon',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 3),),
     'member_ordinal': 25,
     'expected_block_sha256': '02ad93ffa70bd7ceb63fcf1f966a94752b067247895d0e5ae5d3c0dcd65d3bf9',
     'expected_member_sha256': '64d64eab80e61838db356e6323cb29ea48d3047189af315eaefa753769dbda5d',
     'expected_selection_sha256': '4cc2a5274b7ddb6cd8ea8e1a2b2e91da09a1db847c510957504be2d6dd913760',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 90,
              'unit': 'feet',
              'radiusFeet': 90,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-006/ability-001',
     'block_sequence': 131,
     'ability_ordinal': 1,
     'locator': '112.4',
     'creature_name': 'Young Diabolic Dragon',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 23,
     'expected_block_sha256': 'b5d4bb1e6c7a1f1b827176748c20f6893cf3a1695e150999dff5f084e55b405c',
     'expected_member_sha256': 'f0f4c4f5fae59ca741784193e31c3707f361798d204695678169fa2f389b033f',
     'expected_selection_sha256': '7ff5a46832025142cfb5458d6e8c69694370526528990d84c4b1084831609f64',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 90,
              'unit': 'feet',
              'radiusFeet': 90,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-007/ability-001',
     'block_sequence': 132,
     'ability_ordinal': 1,
     'locator': '112.4',
     'creature_name': 'Adult Diabolic Dragon',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 23,
     'expected_block_sha256': 'b71f5cadeff233a7e165eb4d16323cc68a93532a08829eb70a9949af13d52d42',
     'expected_member_sha256': 'e8c24dc299226812a1b89b47a87609c0191293045be7b5aa419a1482ec763847',
     'expected_selection_sha256': '0518430dd1454b8cb2a9e1d1fce1a4ec35a27adce14b13ef0163e15067f5beec',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 90,
              'unit': 'feet',
              'radiusFeet': 90,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-008/ability-001',
     'block_sequence': 133,
     'ability_ordinal': 1,
     'locator': '112.4',
     'creature_name': 'Ancient Diabolic Dragon',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 3),),
     'member_ordinal': 24,
     'expected_block_sha256': 'e202b39ef58d4efb1a275a05e59c7d8cabdda0c977e3ac107b0d2761ae3deba6',
     'expected_member_sha256': 'ea6fc79c266400dc58ec46ee0aca362cee73039fcdbdc522a1fa24819e881568',
     'expected_selection_sha256': 'f938796055c3569519b7d3aad864b2dd203c836a7bf57a234b2dea7992b7b55f',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 90,
              'unit': 'feet',
              'radiusFeet': 90,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-009/ability-001',
     'block_sequence': 134,
     'ability_ordinal': 1,
     'locator': '114.4',
     'creature_name': 'Young Empyreal Dragon',
     'raw_key': '!.Inspiring Presence',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 23,
     'expected_block_sha256': '101f195f43b41788789cc618d3a4ff8b5c14a73483f904732afececa6c54c3b9',
     'expected_member_sha256': 'a79343b6fb6467ec0182e25238c0f95ca73d4580510eca87fabef15dc6e39a19',
     'expected_selection_sha256': 'e52a1592e41ff3c831fdbd0e802cadd95440779e21a7a03286afd182e5d9db53',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'emotion', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-010/ability-001',
     'block_sequence': 135,
     'ability_ordinal': 1,
     'locator': '114.4',
     'creature_name': 'Adult Empyreal Dragon',
     'raw_key': '!.Inspiring Presence',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 23,
     'expected_block_sha256': '5d68770ca8caf1232f5d9534ec2222e662d0a618dd8dec80fac0799f1de4cdd9',
     'expected_member_sha256': '1c512e7a6a153a12fbe8e3028c146678f05fdba11b0cf66ed0c46564dae45914',
     'expected_selection_sha256': '0ecbd346cec9bc53aea037b1c10bdd336e2ef41bbda0e9a4485d980ce4bea026',
     'encoding': 'structured-passive',
     'grammar_cohort': 'local-same-name-inheritance',
     'traits': ('aura', 'emotion', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 40,
              'unit': 'feet',
              'radiusFeet': 40,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-inheritance',
     'effect_provider': 'record:core-mc1/dragon#creature-009/ability-001',
     'effect_link_kind': 'exact-local-same-name-inheritance',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-011/ability-001',
     'block_sequence': 136,
     'ability_ordinal': 1,
     'locator': '114.4',
     'creature_name': 'Ancient Empyreal Dragon',
     'raw_key': '!.Inspiring Presence',
     'carrier_path': (('member', '^.creature', 3),),
     'member_ordinal': 24,
     'expected_block_sha256': '9dfb7db7a6701159aa1e29ff6591df76e19e9e1130e29cdfe0081661217b0132',
     'expected_member_sha256': '9e7d17a541adbb2c1dc444faea3df6df10a0b63396c8d27b83c40cbd0c5026ac',
     'expected_selection_sha256': '69215f47874b8ad8a8962bef74b096ee1367440e515b2ea39d913716a376e550',
     'encoding': 'structured-passive',
     'grammar_cohort': 'local-same-name-inheritance',
     'traits': ('aura', 'emotion', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 60,
              'unit': 'feet',
              'radiusFeet': 60,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-inheritance',
     'effect_provider': 'record:core-mc1/dragon#creature-009/ability-001',
     'effect_link_kind': 'exact-local-same-name-inheritance',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-013/ability-000',
     'block_sequence': 138,
     'ability_ordinal': 0,
     'locator': '116.4',
     'creature_name': 'Adult Fortune Dragon',
     'raw_key': '!.Aura of Disruption',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 19,
     'expected_block_sha256': '4400b1b28e31b70057a8c474a3a31d8097c810aae6fd4d1c09b586bc35aeaef2',
     'expected_member_sha256': '304d8c770fd39555542f09c67f5dc3b57d1706a8978200e36ac48810880bb328',
     'expected_selection_sha256': 'e452e308162d1af9c57c9ce771a1346e8429c91a99ba8bd03da005abd70e98f1',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('arcane', 'aura'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 120,
              'unit': 'feet',
              'radiusFeet': 120,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-015/ability-001',
     'block_sequence': 140,
     'ability_ordinal': 1,
     'locator': '119.2',
     'creature_name': 'Young Horned Dragon',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 22,
     'expected_block_sha256': 'bced116c2767a74f9dbd1473920b90ca3806955dfb37b3489cb2643ae50b7797',
     'expected_member_sha256': 'aecffaed71cac15a36a16fc52bd0ce6e35a61609ae59b6d47470dd559d6f1d91',
     'expected_selection_sha256': '22b7c623b705fd3d69b2d7854d119e05c1f5d4e2fc0ed9afd635cca996174eeb',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 90,
              'unit': 'feet',
              'radiusFeet': 90,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-016/ability-001',
     'block_sequence': 141,
     'ability_ordinal': 1,
     'locator': '119.2',
     'creature_name': 'Adult Horned Dragon',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 22,
     'expected_block_sha256': '154e08f1ae77e6e0e96873e30529aae4aac7b30eb91f3ba9c2f356aedafe15b8',
     'expected_member_sha256': '31c63296985c4a696fab8612da87298a089618ae454d9a3c49367b8c75208828',
     'expected_selection_sha256': '6deb2e3742bb0e98e694ec3c5f29ce438d99237d6771cc80b440a325e6591a77',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 90,
              'unit': 'feet',
              'radiusFeet': 90,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon#creature-017/ability-001',
     'block_sequence': 142,
     'ability_ordinal': 1,
     'locator': '119.2',
     'creature_name': 'Ancient Horned Dragon',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 3),),
     'member_ordinal': 23,
     'expected_block_sha256': 'f5ef32aec24c36debf6eddb62573beb963ad0dc852daddf2a9bb12275f44268f',
     'expected_member_sha256': 'cb3be2979a90cf0425278307ade28fd5762b4be42c62ce3cdafb1459f07da9de',
     'expected_selection_sha256': '534a46bc32d9ef7e3735bb25fed73af4c30dffe62133873a86e24744625e5705',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 2,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 90,
              'unit': 'feet',
              'radiusFeet': 90,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': False},
     'issues': ({'kind': 'source-malformed-merged-boundary',
                 'severity': 'compile-reject',
                 'detail': 'Miasma is merged after the complete Frightful Presence '
                           'shorthand; the second Aura declaration must not be truncated '
                           'or synthesized by the consumer.'},),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dragon-turtle#creature-000/ability-002',
     'block_sequence': 149,
     'ability_ordinal': 2,
     'locator': '126.1',
     'creature_name': 'Dragon Turtle',
     'raw_key': '!.Conjure Storm',
     'carrier_path': (('member', 'Dragon Turtle', 1),
                      ('member', 'Dragon Turtle', 0),
                      ('member', '^.creature', 2)),
     'member_ordinal': 23,
     'expected_block_sha256': 'd26df50df7cbfd14b64c27556586595bf98f9c356c5b9ef67bf947becae9c748',
     'expected_member_sha256': 'dc3e57df17f698ac9885a0caa64f30ffbf94fec189918c80fdbd387c5634a55c',
     'expected_selection_sha256': '6c08bc64e0aefc11297f8c73e012b48bfcc285051944176a5b7d08c68259b7cd',
     'encoding': 'structured-action',
     'grammar_cohort': 'action-bearing-aura',
     'traits': ('air', 'aura', 'primal', 'water'),
     'action_cost': 1,
     'trigger': '',
     'top_level_member_keys': ('Action', 'Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'embedded-foot-emanation',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'action-aura-local',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/dullahan#creature-000/ability-000',
     'block_sequence': 157,
     'ability_ordinal': 0,
     'locator': '134.1',
     'creature_name': 'Dullahan',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', 'Dullahan', 1),
                      ('member', 'Dullahan', 0),
                      ('member', '^.creature', 3)),
     'member_ordinal': 22,
     'expected_block_sha256': '5d7d3fba00d77469d0bf2033d11fb512a5ec67837d0a132c11f6f59c5e2af84f',
     'expected_member_sha256': '9688e8fa33a7fcdfb7508f08b90ca8379ec9a97c21add1ff055d762ed83e53d2',
     'expected_selection_sha256': '8aaf132ed7849f7190ca141f927d7c52ca67c4985e47ce7b98415a875bd2b40e',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/dybbuk#creature-000/ability-000',
     'block_sequence': 160,
     'ability_ordinal': 0,
     'locator': '136.1',
     'creature_name': 'Dybbuk',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', 'Dybbuk', 1),
                      ('member', 'Dybbuk', 0),
                      ('member', '^.creature', 4)),
     'member_ordinal': 21,
     'expected_block_sha256': '4d1b7dd089785f21d55de789d685e65f0abc1bb0b9ac6ed9a369606bb965f6df',
     'expected_member_sha256': 'd01cb1ad8674f6df8384e7752809e0014f2d8cbb8b451fe316bfa59e055953ec',
     'expected_selection_sha256': '2365126b553b83ca6732944e150007111b348fa0b6880d820090dffc5c9913ba',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'divine', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/elemental-air#creature-001/ability-000',
     'block_sequence': 167,
     'ability_ordinal': 0,
     'locator': '140.4',
     'creature_name': 'Living Whirlwind',
     'raw_key': '!.High Winds',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 19,
     'expected_block_sha256': 'e5d41df77b5788f2b1bd47c2f6d189fb539a1eb5fb5f361fbd18d69abe630e31',
     'expected_member_sha256': 'fa4cf980f7d61f67f3609e9cec12fb638e675cab1c2722eb91e8c72c8dac864f',
     'expected_selection_sha256': 'b757f21cedf562ab04675b9c7ededb64868b1534cb4e1cb450dc544948c2f145',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('air', 'aura'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/elemental-air#creature-003/ability-000',
     'block_sequence': 169,
     'ability_ordinal': 0,
     'locator': '141.2',
     'creature_name': 'Elemental Hurricane',
     'raw_key': '!.High Winds',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 19,
     'expected_block_sha256': '4de0ef54ec07a8d573ebb06fdd05e3493945af31f7c9abd7ee5d3e068f4dc114',
     'expected_member_sha256': '98cc54d4998bd0a460f07d20c2bf61beb6f63f0e811b9b21b0d8b6b3f7ba4e40',
     'expected_selection_sha256': 'b6370a9141ff2bd919ea3df53f1740f5e4fba3b6448a40746167ab7ea131c187',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'local-same-name-inheritance',
     'traits': ('air', 'aura'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 40,
              'unit': 'feet',
              'radiusFeet': 40,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-inheritance',
     'effect_provider': 'record:core-mc1/elemental-air#creature-001/ability-000',
     'effect_link_kind': 'exact-local-same-name-inheritance',
     'damage_only': None},
    {'record_id': 'core-mc1/elemental-earth#creature-002/ability-001',
     'block_sequence': 172,
     'ability_ordinal': 1,
     'locator': '142.6',
     'creature_name': 'Stone Mauler',
     'raw_key': '!.Spike Stones',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 20,
     'expected_block_sha256': 'd5dbcd95d5633d86251aad4038366c95bad63c32071d7efdaa67d8acd2f6a4ae',
     'expected_member_sha256': 'e7f2968c3d61088156fb6c5f7b9e3223dfdd53cfe30735fea4df325344b9f820',
     'expected_selection_sha256': 'b2e7ee9049d80add8a5be790454777b8229546420288941684f62fa490d3a14e',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'earth', 'primal'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 5,
              'unit': 'feet',
              'radiusFeet': 5,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/elemental-earth#creature-003/ability-001',
     'block_sequence': 173,
     'ability_ordinal': 1,
     'locator': '143.2',
     'creature_name': 'Elemental Avalanche',
     'raw_key': '!.Spike Stones',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 20,
     'expected_block_sha256': 'e8f4a9ed62e0c7b458f0287fc2c1655e95ae66e4db782ca094d697bec9f38368',
     'expected_member_sha256': '5bff891f324cbdccfc9f52d8cb90ba172ab22f90ae83509dacc5d3bb95a8bd10',
     'expected_selection_sha256': 'b9b3c06d4a4fba35e235179df501e46be5a0feb5b570b4a698074a85b4d4cbbd',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'local-same-name-inheritance',
     'traits': ('aura', 'earth', 'primal'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 10,
              'unit': 'feet',
              'radiusFeet': 10,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-inheritance',
     'effect_provider': 'record:core-mc1/elemental-earth#creature-002/ability-001',
     'effect_link_kind': 'exact-local-same-name-inheritance',
     'damage_only': None},
    {'record_id': 'core-mc1/elemental-fire#creature-000/ability-001',
     'block_sequence': 174,
     'ability_ordinal': 1,
     'locator': '144.2',
     'creature_name': 'Cinder Rat',
     'raw_key': '!.Fetid Fumes',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 20,
     'expected_block_sha256': 'df513374d993164d1b100150caadb73df87b48b7b1624ff904317e2bd8d7c34d',
     'expected_member_sha256': 'e3e9ce9d66fad0cf93605ba27d835ad482d4318292afef474105703008b4ede0',
     'expected_selection_sha256': '958d6b1fbe9efe8f31a74f800de626f107cec331b814ca38e3b7211f77162940',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'fire'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 5,
              'unit': 'feet',
              'radiusFeet': 5,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/elemental-fire#creature-002/ability-002',
     'block_sequence': 176,
     'ability_ordinal': 2,
     'locator': '144.6',
     'creature_name': 'Firewyrm',
     'raw_key': '!.Intense Heat',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 22,
     'expected_block_sha256': '3609f8def7618b1e656b5aee88d231d0376dad9b274fc2ebed9db2b493c93121',
     'expected_member_sha256': '3607168dfb2508884169095775da15869e16c5f5b918b6ea54b9d1390e914c2b',
     'expected_selection_sha256': '70558f0815d8607585e9206beee8071d52c5c54e5132a066655688bf8c8f4a65',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'generic-damage-only-shorthand',
     'traits': ('aura', 'fire'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 10,
              'unit': 'feet',
              'radiusFeet': 10,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Reflex'],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': True,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'generic-aura-damage-only',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': {'radius_feet': 10,
                     'dice_count': 4,
                     'die_sides': 6,
                     'damage_type': 'fire',
                     'save_dc': 25,
                     'save_kind': 'Reflex'}},
    {'record_id': 'core-mc1/elemental-fire#creature-003/ability-002',
     'block_sequence': 177,
     'ability_ordinal': 2,
     'locator': '145.2',
     'creature_name': 'Elemental Inferno',
     'raw_key': '!.Intense Heat',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 22,
     'expected_block_sha256': '5ae090fca8cf41aeea9df4307225f0f04d3d1b66230b5542ba4cd829b6e56a84',
     'expected_member_sha256': 'a0c86a8fcd0b75c85c124b19d880b94698f7d578dad11bb1af7a1a3aa5d80dfb',
     'expected_selection_sha256': 'd9a3571bc33d8f666c8c77a8d9f5b5fddda32f1e16992d9ceb6f265e14fb2824',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'generic-damage-only-shorthand',
     'traits': ('aura', 'fire'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 10,
              'unit': 'feet',
              'radiusFeet': 10,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Reflex'],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': True,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'generic-aura-damage-only',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': {'radius_feet': 10,
                     'dice_count': 7,
                     'die_sides': 6,
                     'damage_type': 'fire',
                     'save_dc': 28,
                     'save_kind': 'Reflex'}},
    {'record_id': 'core-mc1/elemental-water#creature-001/ability-001',
     'block_sequence': 183,
     'ability_ordinal': 1,
     'locator': '148.4',
     'creature_name': 'Living Waterfall',
     'raw_key': '!.Vortex',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 21,
     'expected_block_sha256': 'a02d03831fb186e27a307f0b6437cdf5ce843e5e1969bd987c5e2bdd817d6fd7',
     'expected_member_sha256': '826ff642900613ff81fcd9331bff27414664d67b0135e6d71661b1fc9a5dc891',
     'expected_selection_sha256': '4776273e6ec84747f4539b4d07b43fb4d70de9b6015021ee5906c6fc835fd49c',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'water'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/elemental-water#creature-002/ability-000',
     'block_sequence': 184,
     'ability_ordinal': 0,
     'locator': '148.6',
     'creature_name': 'Quatoid',
     'raw_key': '!.Calming Bioluminescence',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 20,
     'expected_block_sha256': '49b3b3b9c11da733c91f2b26c928547680d6de7fa6c5b2118e237b1a77cb6e15',
     'expected_member_sha256': 'dbaac41e6b5f13361269dc13e820977b29d2b4abc38d45c17fc9a143c3ed9d5f',
     'expected_selection_sha256': 'd9d256eb14dacdca4d5b3609ada213358acf00b1740b64cd25a4304ccac9d238',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'emotion', 'mental', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/elemental-water#creature-003/ability-001',
     'block_sequence': 185,
     'ability_ordinal': 1,
     'locator': '149.2',
     'creature_name': 'Elemental Tsunami',
     'raw_key': '!.Vortex',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 21,
     'expected_block_sha256': '53c28c4cce25ba0cdf0762f786a03f99abffe6e14bc0a7c571e0ffa2794c938c',
     'expected_member_sha256': 'cb2c02c6546d81637af5392191279ab306621a31518b15d6f5092b9c19c53863',
     'expected_selection_sha256': '336509c52d9671b0a3536c160edd45e971d94b2f1bf936ce3af7d3f451a003d1',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'local-same-name-inheritance',
     'traits': ('aura', 'water'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 50,
              'unit': 'feet',
              'radiusFeet': 50,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-inheritance',
     'effect_provider': 'record:core-mc1/elemental-water#creature-001/ability-001',
     'effect_link_kind': 'exact-local-same-name-inheritance',
     'damage_only': None},
    {'record_id': 'core-mc1/fleshwarp#creature-000/ability-001',
     'block_sequence': 190,
     'ability_ordinal': 1,
     'locator': '152.2',
     'creature_name': 'Grothlut',
     'raw_key': '!.Piteous Moan',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 22,
     'expected_block_sha256': '6582728c6d8dce3e3d4396e8cfc8c7cd0ccffb5e8628e9e018eab2fcde11e2d5',
     'expected_member_sha256': 'c4960f031bc529319ccf7728582361885103fa7bf47a03ff73509f2ed0644136',
     'expected_selection_sha256': '205de9f0e8b1ec01c88454dfd861b252026637eaa7becf86002a6636767ad63f',
     'encoding': 'structured-action',
     'grammar_cohort': 'action-bearing-aura',
     'traits': ('auditory', 'aura', 'concentrate', 'emotion', 'mental', 'occult'),
     'action_cost': 2,
     'trigger': '',
     'top_level_member_keys': ('Action', 'Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 60,
              'unit': 'feet',
              'radiusFeet': 60,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'after-save-all-results',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': ['auditory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'action-aura-local',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/genie#creature-000/ability-000',
     'block_sequence': 195,
     'ability_ordinal': 0,
     'locator': '156.2',
     'creature_name': 'Jann',
     'raw_key': '!.Commanding Presence',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 20,
     'expected_block_sha256': '7e01471358ac34b1c4055e88e9e73c4c6ad51280bdbd76604d28fc1a631ebc6b',
     'expected_member_sha256': '275358b43dccda95a74e0c173bbca0910a10961353718e02a5dd207b13bf7b5c',
     'expected_selection_sha256': 'f668d0d23e35ee5615bb02f5b4aa3569a091e149be9305cb05c55806ae7d8ee1',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'after-save-all-results',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/genie#creature-001/ability-000',
     'block_sequence': 196,
     'ability_ordinal': 0,
     'locator': '157.1',
     'creature_name': 'Jaathoom',
     'raw_key': '!.Cloud of Visions',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 14,
     'expected_block_sha256': 'e83fab2d001788c8e958d7dcfe4950448269008e0a0670aca621a532086e39a4',
     'expected_member_sha256': '5e2a5a02e358b374bd67a0e9558ad74686fbc4ec3df13803dfbe8021def9e898',
     'expected_selection_sha256': '4399b741605acac72fb0776967fd05acfc29b0a722486bfa9e40e7b8f3fdf669',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('arcane', 'aura', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 60,
              'unit': 'feet',
              'radiusFeet': 60,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/genie#creature-001/ability-002',
     'block_sequence': 196,
     'ability_ordinal': 2,
     'locator': '157.1',
     'creature_name': 'Jaathoom',
     'raw_key': '!.Turbulent Skies',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 21,
     'expected_block_sha256': 'e83fab2d001788c8e958d7dcfe4950448269008e0a0670aca621a532086e39a4',
     'expected_member_sha256': '723144979a4b6b78cbed3bf3e448d3ccffe564dfa80e223a1b952c7c5c7b5c0f',
     'expected_selection_sha256': '553f4ffe3c5fb3fb23c8156c3dd6b44aba7307d633271a3c087baaffc91950d2',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('air', 'arcane', 'aura'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/genie#creature-003/ability-000',
     'block_sequence': 198,
     'ability_ordinal': 0,
     'locator': '158.3',
     'creature_name': 'Faydhaan',
     'raw_key': '!.Turbulent Seas',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 20,
     'expected_block_sha256': 'daa1584adc98f95d9580482112ebaef545b88906088466edb182e819d0b97cab',
     'expected_member_sha256': '2e2d257cd200fcf2a2ae279c910389d0808925775a7f366d95d271eac2962639',
     'expected_selection_sha256': 'b11c84800265ac6d1634603aa13fc084b6c1d52fe45ca9b4418b2a1bfabf6c24',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'water'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 40,
              'unit': 'feet',
              'radiusFeet': 40,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/ghoul#creature-000/ability-000',
     'block_sequence': 202,
     'ability_ordinal': 0,
     'locator': '163.1',
     'creature_name': 'Ghoul Stalker',
     'raw_key': '!.Stench',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 19,
     'expected_block_sha256': '37393861060ee8655e94bedfe594ae56bb6da6b5624b14b0029de96340798910',
     'expected_member_sha256': 'cb3fe4dce467ea2c3d23dc56ec9b6b2b34d4b5e81111500a8ee7196f79a715c0',
     'expected_selection_sha256': 'b2459d682df48c4b8e50bb4d132d2427a3a98cb7e9acde9721c9d428e64e9748',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 10,
              'unit': 'feet',
              'radiusFeet': 10,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/ghoul#creature-001/ability-001',
     'block_sequence': 203,
     'ability_ordinal': 1,
     'locator': '163.3',
     'creature_name': 'Ghoul Soldier',
     'raw_key': '!.Stench',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 21,
     'expected_block_sha256': '39e503087d3683e829d5916e66ff0dcc9e26fd53db868a631af4e02cdd642f0e',
     'expected_member_sha256': 'e5662e5d6f1f01933f1c40ac95370af7ff6c81f1ba448fd9ef1dc858bc13ae57',
     'expected_selection_sha256': '0ace65f3983c3dfa9ca505b34f2739f79dd6121ef987996b0462326abf7caaab',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 10,
              'unit': 'feet',
              'radiusFeet': 10,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/gimmerling#creature-000/ability-001',
     'block_sequence': 211,
     'ability_ordinal': 1,
     'locator': '170.1',
     'creature_name': 'Gimmerling',
     'raw_key': '!.Treacherous Aura',
     'carrier_path': (('member', 'Gimmerling', 1),
                      ('member', 'Gimmerling', 0),
                      ('member', '^.creature', 3)),
     'member_ordinal': 21,
     'expected_block_sha256': '0642191655dea9fe009d3dbe2dc1b2ef677f012b2d61808fc51e2f1ed127731a',
     'expected_member_sha256': '991f7ebf517a4bd8c3b55d19f3fb467ac857bd6dfddc1c4d1c9b800d586a3ad9',
     'expected_selection_sha256': 'd3a8d3e15fec9b99c1622b4407495275da1662fe6874d74e09eda2ddfb466ead',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'primal'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 15,
              'unit': 'feet',
              'radiusFeet': 15,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/globster#creature-000/ability-000',
     'block_sequence': 212,
     'ability_ordinal': 0,
     'locator': '171.1',
     'creature_name': 'Globster',
     'raw_key': '!.Stench',
     'carrier_path': (('member', 'Globster', 1),
                      ('member', 'Globster', 0),
                      ('member', '^.creature', 5)),
     'member_ordinal': 19,
     'expected_block_sha256': '2f9566b640431c483c3eeef1801be51f0551a08387a73fe59c31b5f77f4cf446',
     'expected_member_sha256': '49ef04d058d0c60f00580cd1cc67439402600075e3889a89fa1b3f199d71a8d1',
     'expected_selection_sha256': '312aca4e7b3dcf82795c8cb7aa4e4d405ad223fa878e05d36f6761d47ffc88cd',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/gremlin#creature-001/ability-000',
     'block_sequence': 225,
     'ability_ordinal': 0,
     'locator': '180.4',
     'creature_name': 'Pugwampi',
     'raw_key': '!.Unluck Aura',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 20,
     'expected_block_sha256': '85e6aa9d0fcf47ef975120f17b990b0684e29d363135a28e63e975d9db645c67',
     'expected_member_sha256': '96a22e2b83fe011acb3bd81345a04d18bb8b23f37c4ba62dac9883d980d6e6dd',
     'expected_selection_sha256': '7e5ca46d4b96eda0c7fbda24fe35b9445eee18d942aa614a047bda6c95cf6659',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'mental', 'misfortune', 'primal'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 24,
                                        'unit': 'hours',
                                        'grant': 'save-success',
                                        'scope': 'all-pugwampi-unluck-auras'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/grikkitog#creature-000/ability-002',
     'block_sequence': 228,
     'ability_ordinal': 2,
     'locator': '183.1',
     'creature_name': 'Grikkitog',
     'raw_key': '!.Infestation Aura',
     'carrier_path': (('member', 'Grikkitog', 1),
                      ('member', 'Grikkitog', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 21,
     'expected_block_sha256': '766bfdadcc8208c8fed2a25dc0ce1cb753815cda5dfa65cb4f090782b5973083',
     'expected_member_sha256': '4d25b642afd9ebbaa8fba76f61f94356cdd4e44ee86de1589fb5f45e55d0fa68',
     'expected_selection_sha256': '122f1181dc59e1375143757f89cead0cf97a5588626d520b67c6b0b7b2b9739b',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'earth', 'occult'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 120,
              'unit': 'feet',
              'radiusFeet': 120,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/grim-reaper#creature-000/ability-001',
     'block_sequence': 229,
     'ability_ordinal': 1,
     'locator': '184.1',
     'creature_name': 'Grim Reaper',
     'raw_key': '!.Aura of Misfortune',
     'carrier_path': (('member', 'Grim Reaper', 1),
                      ('member', 'Grim Reaper', 2),
                      ('member', '^.creature', 3)),
     'member_ordinal': 23,
     'expected_block_sha256': 'a7de2542bdbe8ae17d79ae3036237c4ab6ad92c1e97ee3b99d4f34a7e22fa489',
     'expected_member_sha256': '1e32eef68cbe74ba205925346efb3c990fe14e1da41053578539160b984231eb',
     'expected_selection_sha256': '7368283eb18a11dba25f079cb6f1021fb12274b9c1126e8a4c230318c5986a91',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine', 'misfortune'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/grim-reaper#creature-001/ability-001',
     'block_sequence': 230,
     'ability_ordinal': 1,
     'locator': '185.1',
     'creature_name': 'Lesser Death',
     'raw_key': '!.Aura of Misfortune',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 22,
     'expected_block_sha256': '29161c64045709433a811c7c980e593356e8b60b6d2e0bf8ea66a39604492951',
     'expected_member_sha256': '89679b263a32bb2245cd4f98cb6f8770cb66af663c8b454bb2e665eeb299399f',
     'expected_selection_sha256': '7961b15426c2cec6d041e1b4fd17af04d4201c5fd9881b0a98b0af14e276ce53',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'local-same-name-inheritance',
     'traits': ('aura', 'divine', 'misfortune'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-inheritance',
     'effect_provider': 'record:core-mc1/grim-reaper#creature-000/ability-001',
     'effect_link_kind': 'exact-local-same-name-inheritance',
     'damage_only': None},
    {'record_id': 'core-mc1/guthallath#creature-000/ability-000',
     'block_sequence': 232,
     'ability_ordinal': 0,
     'locator': '187.1',
     'creature_name': 'Guthallath',
     'raw_key': '!.Erosion Aura',
     'carrier_path': (('member', 'Guthallath', 1),
                      ('member', 'Guthallath', 0),
                      ('member', '^.creature', 2)),
     'member_ordinal': 20,
     'expected_block_sha256': '2287a4a0cd25fcdab796631c8f46bd89680db7b9f963067877aa2b29083b133d',
     'expected_member_sha256': '7d802624b1182bf8cc3bf1204eb2b77c15a48f5c9212073638ef6335b7a3ae42',
     'expected_selection_sha256': '5d4e583fe069be03ae533cffd8838a6fedf34245eb20ac45ec508b3416469466',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'primal'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 120,
              'unit': 'feet',
              'radiusFeet': 120,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/harpy#creature-000/ability-001',
     'block_sequence': 239,
     'ability_ordinal': 1,
     'locator': '193.1',
     'creature_name': 'Harpy',
     'raw_key': '!.Stench',
     'carrier_path': (('member', 'Harpy', 1),
                      ('member', 'Harpy', 0),
                      ('member', '^.creature', 4)),
     'member_ordinal': 19,
     'expected_block_sha256': 'afc96a53e279c971add0bbe55487aa72f4574776a1ab4ccd4ae8eebb247c94eb',
     'expected_member_sha256': 'd92a7c3e6a2ebeaccec14d39a137ee61737ec0d7fb3d97084050dc532d87382c',
     'expected_selection_sha256': 'cf28df5073f10fe2a1cf90bd93ee18da30590a0f48965c587de4df6f60b56374',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/kraken#creature-000/ability-000',
     'block_sequence': 268,
     'ability_ordinal': 0,
     'locator': '212.1',
     'creature_name': 'Kraken',
     'raw_key': '!.Altered Weather',
     'carrier_path': (('member', 'Kraken', 1),
                      ('member', 'Kraken', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 21,
     'expected_block_sha256': 'b8502c80360df3f9cdad4cdb099087552d834fbb262c4b916fd47bff45003d2d',
     'expected_member_sha256': '6323a2b16d688169337cf94d73b3dc7c6e97f12a3cf79e093d8c780ca5158de5',
     'expected_selection_sha256': 'ebce9a1847106870abb083e15744a444814afc13df4b4592bf3aba63ac241ee1',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'primal'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'domain-distance',
              'geometryModel': 'participant-centered-domain',
              'value': 2,
              'unit': 'miles',
              'combatGridEligible': False},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': ({'kind': 'non-grid-domain-aura',
                 'severity': 'defer-from-battleground-runtime',
                 'detail': 'The source area is a miles-scale domain and is not an ordinary '
                           'participant-centered combat-grid emanation.'},),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/lich#creature-000/ability-000',
     'block_sequence': 275,
     'ability_ordinal': 0,
     'locator': '219.2',
     'creature_name': 'Lich',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 22,
     'expected_block_sha256': '4cad465e11b8f00914bd4bfa2692776c915d71e09c1f3569020012f507accaee',
     'expected_member_sha256': 'fd138746a878288e98f30cfba6ebf2087985161cf93deb57654ff8eb46480376',
     'expected_selection_sha256': '18d27cb9326a22c70ad660d55b6421f50b4f0e5e031c4f76004ba78100e23905',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 60,
              'unit': 'feet',
              'radiusFeet': 60,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/medusa#creature-000/ability-000',
     'block_sequence': 289,
     'ability_ordinal': 0,
     'locator': '230.1',
     'creature_name': 'Medusa',
     'raw_key': '!.Petrifying Gaze',
     'carrier_path': (('member', 'Medusa', 1),
                      ('member', 'Medusa', 0),
                      ('member', '^.creature', 2)),
     'member_ordinal': 19,
     'expected_block_sha256': 'ce5dbac4e9c712802328a33026834a5190ddaaf770b4c49031c90d499c29f578',
     'expected_member_sha256': '1f4b9ae983239bd095601f3e7c0c118c332feeac9135f36426c4ac0911e3c073',
     'expected_selection_sha256': 'a0637e4ef39fd2bc1cfa25eaf213590a77f4fb782ba2b7bc2f4488390cd918a9',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('arcane', 'aura', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['end-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/mummy#creature-001/ability-001',
     'block_sequence': 295,
     'ability_ordinal': 1,
     'locator': '235.1',
     'creature_name': 'Mummy Pharaoh',
     'raw_key': '!.Undead Mastery',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 23,
     'expected_block_sha256': 'b605ac720c2fee31685b4785ea6e10b6b5fc01c6b8945325940142f76d4d9188',
     'expected_member_sha256': '4f4beb9f6abd177085a3e09d4aa6f42ae2907fb11920269f6211bdb733dd8e6e',
     'expected_selection_sha256': '18fa795bce04af950ac29ef65b9e25c676a94110dc55db7494904549780ec397',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 100,
              'unit': 'feet',
              'radiusFeet': 100,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/mummy#creature-001/ability-005',
     'block_sequence': 295,
     'ability_ordinal': 5,
     'locator': '235.1',
     'creature_name': 'Mummy Pharaoh',
     'raw_key': '!.Veil of Sand',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 29,
     'expected_block_sha256': 'b605ac720c2fee31685b4785ea6e10b6b5fc01c6b8945325940142f76d4d9188',
     'expected_member_sha256': 'cbfdf2e1f8e770abe9f22e78dec4482273df3405996b6f515c63e98abd28e68e',
     'expected_selection_sha256': '675c378b687e5d941463df24625d933ea2a8f11eafe2d92464c587830fa6f4b5',
     'encoding': 'structured-action',
     'grammar_cohort': 'action-bearing-aura',
     'traits': ('aura', 'divine', 'earth'),
     'action_cost': 1,
     'trigger': '',
     'top_level_member_keys': ('Action', 'Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'embedded-foot-emanation',
              'geometryModel': 'participant-emanation',
              'value': 5,
              'unit': 'feet',
              'radiusFeet': 5,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['end-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'action-aura-local',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/nightmare#creature-000/ability-000',
     'block_sequence': 298,
     'ability_ordinal': 0,
     'locator': '238.1',
     'creature_name': 'Nightmare',
     'raw_key': '!.Smoke',
     'carrier_path': (('member', 'Nightmare', 1),
                      ('member', 'Nightmare', 1),
                      ('member', '^.creature', 1)),
     'member_ordinal': 13,
     'expected_block_sha256': '00fbee171ea45566b748f725ba2f0164785276baf931930c1c4a2974520ead18',
     'expected_member_sha256': 'de0ff6fd988cfb475934e4a1846d8da5e45817090cf5363a0248ce385eeb0c5f',
     'expected_selection_sha256': 'aaf458ddddf9f030aa72187746d454edac65d398241c4505750295acf1b5b389',
     'encoding': 'ordered-paragraph-flow',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura',),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('~.p', '~.p'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 15,
              'unit': 'feet',
              'radiusFeet': 15,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'after-save-all-results',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': ({'kind': 'current-consumer-shape-gap',
                 'severity': 'compiler-foundation',
                 'detail': 'The primary (aura) token is in duplicate-preserved ~.p flow, '
                           'not a Traits field or scalar ability value.'},),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/nightmare#creature-001/ability-000',
     'block_sequence': 299,
     'ability_ordinal': 0,
     'locator': '238.3',
     'creature_name': 'Greater Nightmare',
     'raw_key': '!.Smoke',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 13,
     'expected_block_sha256': '6be8f61e6bc00a142b67f759981c3b3297d6a5d9ecea45365a96be3878e0e668',
     'expected_member_sha256': '20cdd3a2f9821721ce296ef75ea96f22545413154ee3118f26b40f74f828a781',
     'expected_selection_sha256': '5a6a241bb6ced0e5c3f82633d038cf3de60e900ac56c7edac2419a6b9e350a22',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'local-same-name-inheritance',
     'traits': ('aura',),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'after-save-all-results',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-inheritance',
     'effect_provider': 'record:core-mc1/nightmare#creature-000/ability-000',
     'effect_link_kind': 'exact-local-same-name-inheritance',
     'damage_only': None},
    {'record_id': 'core-mc1/nuckelavee#creature-000/ability-000',
     'block_sequence': 303,
     'ability_ordinal': 0,
     'locator': '243.1',
     'creature_name': 'Nuckelavee',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', 'Nuckelavee', 1),
                      ('member', 'Nuckelavee', 0),
                      ('member', '^.creature', 3)),
     'member_ordinal': 21,
     'expected_block_sha256': '4a3049064cb7903bc14a5f08502598ca4fa783f2a3d92edc3668e615669d9af6',
     'expected_member_sha256': 'd7f2870d3259b71e5449b4d4743a971d9bcc30ecaf140b74a6d34b3f3472b233',
     'expected_selection_sha256': 'e8e75e2bd7ee971431b5bfc8e96645b346fc487b33fbbaa255120e975c3fbfe3',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/nymph#creature-002/ability-002',
     'block_sequence': 306,
     'ability_ordinal': 2,
     'locator': '246.2',
     'creature_name': 'Naiad Queen',
     'raw_key': "!.Nymph's Beauty",
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 23,
     'expected_block_sha256': '16bf8ec1074aa2de47d7711ef3136ff641f1d30fc43dcaaa15d74a04e9d3f608',
     'expected_member_sha256': 'f7e6baeb7778d23b50a606c407e6e44470285af77f63295ef1d0e6f2de3f43d5',
     'expected_selection_sha256': '2906d780e066891aa29222168ffd88be1efb3575225e33583d2031c717bdb748',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'section-rule-overlay',
     'traits': ('aura', 'emotion', 'mental', 'primal', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['start-turn'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'nymphs-beauty',
     'effect_provider': 'nymph',
     'effect_link_kind': 'exact-section-shared-rule-overlay',
     'damage_only': None},
    {'record_id': 'core-mc1/nymph#creature-003/ability-002',
     'block_sequence': 307,
     'ability_ordinal': 2,
     'locator': '247.2',
     'creature_name': 'Dryad Queen',
     'raw_key': "!.Nymph's Beauty",
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 22,
     'expected_block_sha256': '0b1946f3e1cafa3b0eee04475e9f8dbc5794ac43ce4aa6bac82e6654ed15a590',
     'expected_member_sha256': '6cf35e7ecaff95c4e72d74e54880a1a28c8ac30ef5f8d1227e99b9c2be9d7f32',
     'expected_selection_sha256': '9b468f31e68a08e8e155fa73912ac8b775c961a280b66228237a9be804103710',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'section-rule-overlay',
     'traits': ('aura', 'emotion', 'incapacitation', 'mental', 'primal', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'linked-section-rule',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['start-turn'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': None,
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'nymphs-beauty',
     'effect_provider': 'nymph',
     'effect_link_kind': 'exact-section-shared-rule-overlay',
     'damage_only': None},
    {'record_id': 'core-mc1/ofalth#creature-000/ability-001',
     'block_sequence': 309,
     'ability_ordinal': 1,
     'locator': '249.2',
     'creature_name': 'Larval Ofalth',
     'raw_key': '!.Stench',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 20,
     'expected_block_sha256': '7ca4478d25cd3ac6195ae7f689fbb97313c0abeafe6f77302ac463d3407578a6',
     'expected_member_sha256': '99bc06307136fb954b96f77bd278832b961312ede4e8c63e4e134218bbf1f95a',
     'expected_selection_sha256': '508f064b78ff672f8b6b13c62752e618c8ca11e00ca9c1a1537cbc576860f6c2',
     'encoding': 'structured-passive',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/ofalth#creature-001/ability-002',
     'block_sequence': 310,
     'ability_ordinal': 2,
     'locator': '249.4',
     'creature_name': 'Ofalth',
     'raw_key': '!.Stench',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 21,
     'expected_block_sha256': 'a91f5c13e47b5a3e9f3e5e2cdc3881f4de49db2d812be9692096ecdd83e57fdc',
     'expected_member_sha256': '576f29f166c5b003a6a1912c0693fc1a3de51f29d59508c68255f9127bc59976',
     'expected_selection_sha256': 'c91ce8d603fd081a955b0b19079f5224260a612c9dc930ac77b6a8c6f2dfb48a',
     'encoding': 'structured-passive',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/oni#creature-003/ability-002',
     'block_sequence': 317,
     'ability_ordinal': 2,
     'locator': '254.3',
     'creature_name': 'Island Oni',
     'raw_key': '!.Lost Oni Island',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 23,
     'expected_block_sha256': '4265b04ec5af63995a3486494e6f6923b16f56031cdb3931717283b1c6723eeb',
     'expected_member_sha256': '4bd964a853b84b3669edbdc2ef49f027408974c9ce46783ca54ce652e502b1a0',
     'expected_selection_sha256': 'cfa3fc912fa04c720d037e4090687a16576dd87fa2a9d74637e0910bfa4c3827',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'primal'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'claimed-domain-radius',
              'geometryModel': 'claimed-island-domain',
              'value': 1,
              'unit': 'mile',
              'combatGridEligible': False},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': ({'kind': 'non-grid-domain-aura',
                 'severity': 'defer-from-battleground-runtime',
                 'detail': 'The source area is a miles-scale domain and is not an ordinary '
                           'participant-centered combat-grid emanation.'},),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/phoenix#creature-000/ability-000',
     'block_sequence': 330,
     'ability_ordinal': 0,
     'locator': '264.1',
     'creature_name': 'Phoenix',
     'raw_key': '!.Shroud of Flame',
     'carrier_path': (('member', 'Phoenix', 1),
                      ('member', 'Phoenix', 0),
                      ('member', '^.creature', 4)),
     'member_ordinal': 22,
     'expected_block_sha256': 'f7dc3028ea13f09b38fba30a7ed32a749d8c8227973ca96e1567b9beeb5c2dd2',
     'expected_member_sha256': 'bc610fcc9368821e78cdb3027c8446f57541e8383401910091949d38d0948e1c',
     'expected_selection_sha256': '28e9231f27ef2d619962b22979a6a73ba812b83dc5254a2264b0d93c92ef6a28',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'fire', 'primal'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': ['Reflex'],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/protean#creature-002/ability-002',
     'block_sequence': 339,
     'ability_ordinal': 2,
     'locator': '272.1',
     'creature_name': 'Keketar',
     'raw_key': '!.Spatial Ripture',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 21,
     'expected_block_sha256': '3188c51dd4a4679c2c4b4e4189a5136a31ff3364d91c053c18b4855aba099bf8',
     'expected_member_sha256': '4586b409e28072e79c9b6eac5b9b08ada9abdb4936c066ac9c4f632a8bb9a8c6',
     'expected_selection_sha256': '6093586b4f8d0efbae23d707fe44c51251d409c704764ae1189cb106261dfc7d',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/psychopomp#creature-001/ability-000',
     'block_sequence': 341,
     'ability_ordinal': 0,
     'locator': '275.2',
     'creature_name': 'Vanth',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 2),),
     'member_ordinal': 22,
     'expected_block_sha256': '10730095a0c606a20aef2b941013e0bfca2128c604ed5b8eb101ef76b27697e6',
     'expected_member_sha256': 'c85f2f5d0be2fd40a2c861a378930e81cad16de35eec305d94175257d4bb8693',
     'expected_selection_sha256': '8b5815e33bd4be119047f6eb869213bac2eae50d8415080730686c7b14e9a2bf',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/psychopomp#creature-003/ability-000',
     'block_sequence': 343,
     'ability_ordinal': 0,
     'locator': '276.4',
     'creature_name': 'Yamaraj',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 22,
     'expected_block_sha256': '1904f72cc3ddfd5363297b75cfba880f3dc6982236bd133057f1efb660f1fe38',
     'expected_member_sha256': 'baa6d2ea5e66d7f6d4f5f087bce393df353c7d034d89a472e81ff1ec0cf33307',
     'expected_selection_sha256': '0e12be956e905fdb527a7e40f406c1a58caccc9601cecb5bec96d704c752fd7b',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 60,
              'unit': 'feet',
              'radiusFeet': 60,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/quai-dau-to#creature-000/ability-001',
     'block_sequence': 351,
     'ability_ordinal': 1,
     'locator': '284.1',
     'creature_name': 'Quai Dau To',
     'raw_key': '!.Frightful Sight',
     'carrier_path': (('member', 'Quai Dau To', 1),
                      ('member', 'Quai Dau To', 0),
                      ('member', '^.creature', 2)),
     'member_ordinal': 20,
     'expected_block_sha256': '66ae521f9ea0001cc59249b1151f185b8d7c1406a811ed4101e03a70fd01b078',
     'expected_member_sha256': '3a0752487808141bfc32784506b41b187f388118c30d22398870f4c59779e918',
     'expected_selection_sha256': '7047cbcf8f57affd5951c972c5caa3dceceb8f97e06bc3d44bf914d76049309b',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-overlay',
     'traits': ('aura', 'emotion', 'fear', 'mental', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 60,
              'unit': 'feet',
              'radiusFeet': 60,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence-overlay',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-overlay',
     'damage_only': None},
    {'record_id': 'core-mc1/sargassum-heap#creature-000/ability-000',
     'block_sequence': 364,
     'ability_ordinal': 0,
     'locator': '295.1',
     'creature_name': 'Sargassum Heap',
     'raw_key': '!.Mirage Spores',
     'carrier_path': (('member', 'Sargassum Heap', 1),
                      ('member', 'Sargassum Heap', 1),
                      ('member', '^.creature', 1)),
     'member_ordinal': 20,
     'expected_block_sha256': 'da5c2f321a384501b6181dd9e52c21b16b8cb7f22aa117ab6e37058d2db143b8',
     'expected_member_sha256': '8b5aa52873b07724b6631ac45715a8b26e4094cc07b746e1db9b5da4fe8b8be8',
     'expected_selection_sha256': 'f801670be1eb97081263b00314d3d9833be5880112e3ba8bd3cf045edab1060e',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'incapacitation', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 120,
              'unit': 'feet',
              'radiusFeet': 120,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 24,
                                        'unit': 'hours',
                                        'grant': 'save-success',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/sargassum-heap#creature-001/ability-000',
     'block_sequence': 365,
     'ability_ordinal': 0,
     'locator': '295.3',
     'creature_name': 'Doldrums Heap',
     'raw_key': '!.Mirage Spores',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 20,
     'expected_block_sha256': '050fb489ea283deae453555bf4231daf95ed686b189b5786d400f9d6eb33b9e4',
     'expected_member_sha256': '2284b727528d2146a64e36fff79d1cfb18b680caa6585983e1732d81ef7b07a6',
     'expected_selection_sha256': '5dcabf9935261904f6804203beab4b1edc2083e4e66d94f304b1720951f47045',
     'encoding': 'inline-scalar',
     'grammar_cohort': 'local-same-name-inheritance',
     'traits': ('aura', 'incapacitation', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': (),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 300,
              'unit': 'feet',
              'radiusFeet': 300,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 24,
                                        'unit': 'hours',
                                        'grant': 'save-success',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-inheritance',
     'effect_provider': 'record:core-mc1/sargassum-heap#creature-000/ability-000',
     'effect_link_kind': 'exact-local-same-name-inheritance',
     'damage_only': None},
    {'record_id': 'core-mc1/scarecrow#creature-000/ability-000',
     'block_sequence': 367,
     'ability_ordinal': 0,
     'locator': '297.1',
     'creature_name': 'Scarecrow',
     'raw_key': "!.Scarecrow's Leer",
     'carrier_path': (('member', 'Scarecrow', 1),
                      ('member', 'Scarecrow', 0),
                      ('member', '^.creature', 2)),
     'member_ordinal': 20,
     'expected_block_sha256': 'dbf811c3a8f23c79dfce3325e14b5733d65df8179195700b898484f89ea692f6',
     'expected_member_sha256': '6e23cae3eacb015a3c62547fa15f26bc5b10600b2be233b3b9af948fbd63af5e',
     'expected_selection_sha256': '57248a2b0e3f7aed0be711f81f2921b2e7dbc51efc04bd8f35cbe6152466ec59',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'emotion', 'fear', 'mental', 'occult', 'visual'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 40,
              'unit': 'feet',
              'radiusFeet': 40,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 24,
                                        'unit': 'hours',
                                        'grant': 'critical-success-only',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': ['visual'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/shining-child#creature-000/ability-001',
     'block_sequence': 383,
     'ability_ordinal': 1,
     'locator': '308.1',
     'creature_name': 'Shining Child',
     'raw_key': '!.Blinding Aura',
     'carrier_path': (('member', 'Shining Child', 1),
                      ('member', 'Shining Child', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 20,
     'expected_block_sha256': 'ccaaa603b36ce181b76a67019950280062b0a17bd7329476882f32e157159995',
     'expected_member_sha256': '4d5ed11b0e19cdf8f25760098dd154cd1242c0beb901d9eae4d92a5a3624737d',
     'expected_selection_sha256': '52b48795ed47e106e1e7cb33c031815d703d471199ef7aaf3ffc10d8559ef635',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('arcane', 'aura', 'incapacitation', 'light'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 60,
              'unit': 'feet',
              'radiusFeet': 60,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 24,
                                        'unit': 'hours',
                                        'grant': 'save-success',
                                        'scope': 'local-text-does-not-fully-specify-cross-source-scope'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': ['light'],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/skulltaker#creature-000/ability-001',
     'block_sequence': 391,
     'ability_ordinal': 1,
     'locator': '314.1',
     'creature_name': 'Skulltaker',
     'raw_key': '!.Shard Storm',
     'carrier_path': (('member', 'Skulltaker', 1),
                      ('member', 'Skulltaker', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 22,
     'expected_block_sha256': 'a7a6dfdc7bfa1b9e10148d28cd21b86304632669d20ca794d034a831bc49bb07',
     'expected_member_sha256': '1443412d5f8822e7585324955e0bbbef581f8e45445f882b0064df38258b25ac',
     'expected_selection_sha256': '5e3cfb8170b84919121bacb0fa168d36e998568d6bbc00d47967a469c4047be8',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('air', 'aura', 'divine'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 10,
              'unit': 'feet',
              'radiusFeet': 10,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Will', 'Reflex'],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/stone-bulwark#creature-000/ability-000',
     'block_sequence': 406,
     'ability_ordinal': 0,
     'locator': '324.1',
     'creature_name': 'Stone Bulwark',
     'raw_key': '!.Statuary Aura',
     'carrier_path': (('member', 'Stone Bulwark', 1),
                      ('member', 'Stone Bulwark', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 20,
     'expected_block_sha256': '5db57b59dede72911ef64ea82cacfbc36980cce87b9afb1e309c9c0aaa984941',
     'expected_member_sha256': '846d4592ea2ddb19942a4a5787536dfeacf2d29c9a101a328af2a8fc5393a7cc',
     'expected_selection_sha256': '3e8f38e0557da83f6470aabc3a21fd27e003923bb04d342df9c61f72f51aee22',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('arcane', 'aura', 'earth'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/terotricus#creature-000/ability-000',
     'block_sequence': 408,
     'ability_ordinal': 0,
     'locator': '326.1',
     'creature_name': 'Terotricus',
     'raw_key': '!.Spore Cloud',
     'carrier_path': (('member', 'Terotricus', 1),
                      ('member', 'Terotricus', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 22,
     'expected_block_sha256': 'dd6f39f571070c275d77cb41ff7a5d13b1cf242629a1def89b6709d103caf146',
     'expected_member_sha256': '821155a41b80fe744a2040576edab0a4372108c111f81af251c322d11c7269b5',
     'expected_selection_sha256': 'f5e1305037815ce60a7da779d9c96d794c09ea90c9bfb2334c46447249be3a03',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'disease'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/treerazer#creature-000/ability-000',
     'block_sequence': 411,
     'ability_ordinal': 0,
     'locator': '328.1',
     'creature_name': 'Treerazer',
     'raw_key': '!.Aura of Corruption',
     'carrier_path': (('member', 'Treerazer', 1),
                      ('member', 'Treerazer', 1),
                      ('member', '^.creature', 1)),
     'member_ordinal': 23,
     'expected_block_sha256': 'b12bb5af34690ece9c13af1bc1f292b53378659bdff88b6f7bdc78cbd6021bbc',
     'expected_member_sha256': 'ea0eb737b3af771c1971960b831cda35c1aceebe9ed1f32c56d03d8c145c3c5f',
     'expected_selection_sha256': 'c5f4c613184ba72e0b01110430a0820ff753c198a9cca2b48dd9e32f1309f75c',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'plant', 'primal'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 120,
              'unit': 'feet',
              'radiusFeet': 120,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['each-round-ambiguous'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': ({'kind': 'runtime-timing-ambiguous',
                 'severity': 'not-runnable-without-policy',
                 'detail': 'The source says each round without selecting a participant '
                           'turn anchor.'},),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/vilderavn#creature-000/ability-000',
     'block_sequence': 422,
     'ability_ordinal': 0,
     'locator': '340.1',
     'creature_name': 'Vilderavn',
     'raw_key': '!.Aura of Disquietude',
     'carrier_path': (('member', 'Vilderavn', 1),
                      ('member', 'Vilderavn', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 20,
     'expected_block_sha256': 'eacec6a7f34bc6543e6ecc97dfa7dc6092881d3097f6d838230e6ea44582edfa',
     'expected_member_sha256': 'ab6cd9bba34de1b1df2432d6cfddc17deda71a7493b42f953f178bbad5c6a8a7',
     'expected_selection_sha256': 'ff823652234cd235c710e155d8263cebf80c428cd60ebedb0a0ab0027deee919',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-overlay',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence-overlay',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-overlay',
     'damage_only': None},
    {'record_id': 'core-mc1/warsworn#creature-000/ability-000',
     'block_sequence': 425,
     'ability_ordinal': 0,
     'locator': '342.1',
     'creature_name': 'Warsworn',
     'raw_key': '!.Animated Weapons',
     'carrier_path': (('member', 'Warsworn', 1),
                      ('member', 'Warsworn', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 20,
     'expected_block_sha256': '8e82a5d33259b0948c586764b703b221630baf80162eb1558c2beeebe9724f88',
     'expected_member_sha256': '70bc09bb6fd2978067c00014f5c7772c39872d83e283abae54036d1817ca8dbc',
     'expected_selection_sha256': 'c32fe1b062704e235432e25a86f0430264fb4d28305a460c26f487b3c2deb3fe',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'divine'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 100,
              'unit': 'feet',
              'radiusFeet': 100,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/warsworn#creature-000/ability-001',
     'block_sequence': 425,
     'ability_ordinal': 1,
     'locator': '342.1',
     'creature_name': 'Warsworn',
     'raw_key': '!.Frightful Presence',
     'carrier_path': (('member', 'Warsworn', 1),
                      ('member', 'Warsworn', 0),
                      ('member', '^.creature', 1)),
     'member_ordinal': 21,
     'expected_block_sha256': '8e82a5d33259b0948c586764b703b221630baf80162eb1558c2beeebe9724f88',
     'expected_member_sha256': '7ce61398b38c0dec9a05fb878856e21a46e54b04f40c2fa02d0a1699f05cf65c',
     'expected_selection_sha256': 'fdcb9ab82f57aaf8cfcacc4b3585f4f6779463765849041cc7265b9cb32003b4',
     'encoding': 'structured-passive',
     'grammar_cohort': 'frightful-presence-shorthand',
     'traits': ('aura', 'emotion', 'fear', 'mental'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 100,
              'unit': 'feet',
              'radiusFeet': 100,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry'],
                  'saveKinds': ['Will'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'all-save-results',
                                        'scope': 'source-participant-frightful-presence'},
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'frightful-presence',
     'effect_provider': 'frightful',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/will-o-wisp#creature-000/ability-000',
     'block_sequence': 433,
     'ability_ordinal': 0,
     'locator': '349.1',
     'creature_name': "Will-o'-Wisp",
     'raw_key': '!.Glow',
     'carrier_path': (('member', 'Will-o’-Wisp', 1),
                      ('member', 'Will-o’-Wisp', 0),
                      ('member', '^.creature', 3)),
     'member_ordinal': 19,
     'expected_block_sha256': 'b9e8276b6ce39df8512f17ccf282985f00cc3e2994c1dbbb3fc53bdb215ee9b8',
     'expected_member_sha256': '82375797f7018837c3a953b2d90043a8382145cbb548fd251f646b1297774c4b',
     'expected_selection_sha256': '02e0c8da07d6f3b193fedd46678692b99a8a8f9f8e1d15f5a06e47c4d3fbd45f',
     'encoding': 'structured-passive',
     'grammar_cohort': 'direct-local-aura',
     'traits': ('aura', 'light'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 20,
              'unit': 'feet',
              'radiusFeet': 20,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': [],
                  'saveKinds': [],
                  'temporaryImmunity': None,
                  'sensoryTraits': [],
                  'sensoryAdjacentTraits': ['light'],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'local-aura-effect',
     'effect_provider': None,
     'effect_link_kind': None,
     'damage_only': None},
    {'record_id': 'core-mc1/xulgath#creature-000/ability-000',
     'block_sequence': 437,
     'ability_ordinal': 0,
     'locator': '352.3',
     'creature_name': 'Xulgath Warrior',
     'raw_key': '!.Stench',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 19,
     'expected_block_sha256': '15c7d884be0ee9258dcec4f9d409048d79c12f3c757bd2ca4450285a2a066683',
     'expected_member_sha256': 'fadce6baa9aafd34ae9b523fcc475552f1f52e46d927422059e98ca98b5b22e0',
     'expected_selection_sha256': 'e2cd4ecac5b116841d36eeea2458f2343cff83686830a1b96fa2145c8c123ac4',
     'encoding': 'structured-passive',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/xulgath#creature-001/ability-000',
     'block_sequence': 438,
     'ability_ordinal': 0,
     'locator': '353.1',
     'creature_name': 'Xulgath Skulker',
     'raw_key': '!.Stench',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 19,
     'expected_block_sha256': '4d6275f89d9c12d08bc2e0e335e12e9935228b0c2b84ad6d4b7685f0e5013ed0',
     'expected_member_sha256': 'fadce6baa9aafd34ae9b523fcc475552f1f52e46d927422059e98ca98b5b22e0',
     'expected_selection_sha256': 'e2cd4ecac5b116841d36eeea2458f2343cff83686830a1b96fa2145c8c123ac4',
     'encoding': 'structured-passive',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
    {'record_id': 'core-mc1/xulgath#creature-002/ability-000',
     'block_sequence': 439,
     'ability_ordinal': 0,
     'locator': '353.4',
     'creature_name': 'Xulgath Leader',
     'raw_key': '!.Stench',
     'carrier_path': (('member', '^.creature', 1),),
     'member_ordinal': 19,
     'expected_block_sha256': 'c21757edb5c27a3655a9d30c3ccf8e662e950f8e5cce129498856acde377e4f6',
     'expected_member_sha256': '99bc06307136fb954b96f77bd278832b961312ede4e8c63e4e134218bbf1f95a',
     'expected_selection_sha256': '508f064b78ff672f8b6b13c62752e618c8ca11e00ca9c1a1537cbc576860f6c2',
     'encoding': 'structured-passive',
     'grammar_cohort': 'stench-shorthand',
     'traits': ('aura', 'olfactory'),
     'action_cost': None,
     'trigger': '',
     'top_level_member_keys': ('Traits', 'Description'),
     'aura_declaration_count': 1,
     'area': {'sourceSyntax': 'leading-feet',
              'geometryModel': 'participant-emanation',
              'value': 30,
              'unit': 'feet',
              'radiusFeet': 30,
              'combatGridEligible': True},
     'behavior': {'exposureTriggers': ['entry', 'start-turn'],
                  'saveKinds': ['Fortitude'],
                  'temporaryImmunity': {'duration': 1,
                                        'unit': 'minute',
                                        'grant': 'save-success-or-sickened-recovery',
                                        'scope': 'all-stench-auras'},
                  'sensoryTraits': ['olfactory'],
                  'sensoryAdjacentTraits': [],
                  'genericDamageOnlyOncePerRound': False,
                  'runnableSource': True},
     'issues': (),
     'route_family': 'stench',
     'effect_provider': 'stench',
     'effect_link_kind': 'exact-specialized-shorthand',
     'damage_only': None},
)


def _path_from_claim(value: object, label: str) -> tuple[
    RawMemberStep | RawIndexStep, ...
]:
    if type(value) is not tuple or len(value) > 32:
        raise ValueError(f"{label} must be a bounded exact tuple")
    result: list[RawMemberStep | RawIndexStep] = []
    for index, claim in enumerate(value):
        if type(claim) is not tuple or not claim:
            raise TypeError(f"{label}[{index}] is invalid")
        if (
            len(claim) == 3
            and claim[0] == "member"
            and type(claim[1]) is str
            and type(claim[2]) is int
        ):
            result.append(RawMemberStep(claim[1], claim[2]))
        elif (
            len(claim) == 2
            and claim[0] == "index"
            and type(claim[1]) is int
        ):
            result.append(RawIndexStep(claim[1]))
        else:
            raise TypeError(f"{label}[{index}] is invalid")
    return tuple(result)


def _exact_dict(
    value: object,
    expected: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    if frozenset(dict.keys(value)) != expected:
        raise ValueError(f"{label} fields are invalid")
    if any(type(key) is not str for key in dict.keys(value)):
        raise TypeError(f"{label} keys must be exact strings")
    return value


def _area_from_raw(value: object) -> AuraArea:
    raw = _exact_dict(
        value,
        frozenset(
            {
                "sourceSyntax",
                "geometryModel",
                "value",
                "unit",
                "combatGridEligible",
            }
            | ({"radiusFeet"} if type(value) is dict and "radiusFeet" in value else set())
        ),
        "reviewed Aura area",
    )
    return AuraArea(
        source_syntax=raw["sourceSyntax"],
        geometry_model=raw["geometryModel"],
        value=raw["value"],
        unit=raw["unit"],
        radius_feet=raw.get("radiusFeet"),
        combat_grid_eligible=raw["combatGridEligible"],
    )


def _immunity_from_raw(value: object) -> AuraTemporaryImmunity | None:
    if value is None:
        return None
    raw = _exact_dict(
        value,
        frozenset({"duration", "unit", "grant", "scope"}),
        "reviewed Aura temporary immunity",
    )
    return AuraTemporaryImmunity(
        duration=raw["duration"],
        unit=raw["unit"],
        grant=raw["grant"],
        scope=raw["scope"],
    )


def _behavior_from_raw(value: object) -> AuraBehavior:
    raw = _exact_dict(
        value,
        frozenset(
            {
                "exposureTriggers",
                "saveKinds",
                "temporaryImmunity",
                "sensoryTraits",
                "sensoryAdjacentTraits",
                "genericDamageOnlyOncePerRound",
                "runnableSource",
            }
        ),
        "reviewed Aura behavior",
    )
    return AuraBehavior(
        exposure_triggers=_exact_strings(
            raw["exposureTriggers"],
            "reviewed Aura exposure triggers",
            allowed=_EXPOSURE_TRIGGERS,
        ),
        save_kinds=_exact_strings(
            raw["saveKinds"],
            "reviewed Aura save kinds",
            allowed=_SAVE_KINDS,
        ),
        temporary_immunity=_immunity_from_raw(raw["temporaryImmunity"]),
        sensory_traits=_exact_strings(
            raw["sensoryTraits"],
            "reviewed Aura sensory traits",
            allowed=_SENSORY_TRAITS,
        ),
        sensory_adjacent_traits=_exact_strings(
            raw["sensoryAdjacentTraits"],
            "reviewed Aura sensory-adjacent traits",
            allowed=_SENSORY_ADJACENT_TRAITS,
        ),
        generic_damage_only_once_per_round=raw[
            "genericDamageOnlyOncePerRound"
        ],
        runnable_source=raw["runnableSource"],
    )


def _issues_from_raw(value: object) -> tuple[AuraSourceIssue, ...]:
    if type(value) is not tuple or len(value) > 16:
        raise TypeError("reviewed Aura issues must be an exact tuple")
    result: list[AuraSourceIssue] = []
    for item in value:
        raw = _exact_dict(
            item,
            frozenset({"kind", "severity", "detail"}),
            "reviewed Aura issue",
        )
        result.append(
            AuraSourceIssue(
                kind=raw["kind"],
                severity=raw["severity"],
                detail=raw["detail"],
            )
        )
    return tuple(result)


def _damage_from_raw(
    value: object,
) -> tuple[int, int, int, str, int, str] | None:
    if value is None:
        return None
    raw = _exact_dict(
        value,
        frozenset(
            {
                "radius_feet",
                "dice_count",
                "die_sides",
                "damage_type",
                "save_dc",
                "save_kind",
            }
        ),
        "reviewed Aura damage shorthand",
    )
    result = (
        raw["radius_feet"],
        raw["dice_count"],
        raw["die_sides"],
        raw["damage_type"],
        raw["save_dc"],
        raw["save_kind"],
    )
    AuraDamageOnly(*result, source_text="reviewed")
    return result


def _build_reviewed_specs(
    rows: object,
) -> tuple[_ReviewedAuraSpec, ...]:
    if type(rows) is not tuple or len(rows) != REVIEWED_AURA_RECORD_COUNT:
        raise RuntimeError("reviewed Aura table has the wrong record count")
    required = frozenset(
        {
            "record_id",
            "block_sequence",
            "ability_ordinal",
            "locator",
            "creature_name",
            "raw_key",
            "carrier_path",
            "member_ordinal",
            "expected_block_sha256",
            "expected_member_sha256",
            "expected_selection_sha256",
            "encoding",
            "grammar_cohort",
            "traits",
            "action_cost",
            "trigger",
            "top_level_member_keys",
            "aura_declaration_count",
            "area",
            "behavior",
            "issues",
            "route_family",
            "effect_provider",
            "effect_link_kind",
            "damage_only",
        }
    )
    result: list[_ReviewedAuraSpec] = []
    for index, item in enumerate(rows):
        raw = _exact_dict(item, required, f"reviewed Aura row {index}")
        for field_name in (
            "record_id",
            "locator",
            "creature_name",
            "raw_key",
        ):
            _trimmed(raw[field_name], f"reviewed Aura {field_name}")
        if (
            type(raw["block_sequence"]) is not int
            or raw["block_sequence"] <= 0
            or type(raw["ability_ordinal"]) is not int
            or raw["ability_ordinal"] < 0
            or type(raw["member_ordinal"]) is not int
            or raw["member_ordinal"] < 0
        ):
            raise ValueError("reviewed Aura ordinal is invalid")
        for field_name in (
            "expected_block_sha256",
            "expected_member_sha256",
            "expected_selection_sha256",
        ):
            _sha256(raw[field_name], f"reviewed Aura {field_name}")
        if raw["encoding"] not in _ENCODINGS:
            raise ValueError("reviewed Aura encoding is invalid")
        if raw["grammar_cohort"] not in _COHORTS:
            raise ValueError("reviewed Aura cohort is invalid")
        if raw["route_family"] not in _ROUTE_FAMILIES:
            raise ValueError("reviewed Aura route is invalid")
        action_cost = raw["action_cost"]
        if (
            action_cost is not None
            and action_cost != "reaction"
            and (
                type(action_cost) is not int
                or action_cost not in {1, 2, 3}
            )
        ):
            raise ValueError("reviewed Aura action cost is invalid")
        if type(raw["trigger"]) is not str:
            raise TypeError("reviewed Aura trigger must be exact string")
        if (
            type(raw["aura_declaration_count"]) is not int
            or raw["aura_declaration_count"] <= 0
        ):
            raise ValueError("reviewed Aura declaration count is invalid")
        effect_provider = raw["effect_provider"]
        effect_link_kind = raw["effect_link_kind"]
        if effect_provider is not None:
            _trimmed(effect_provider, "reviewed Aura effect provider")
        if (
            effect_link_kind is not None
            and effect_link_kind not in _LINK_KINDS
        ):
            raise ValueError("reviewed Aura effect link is invalid")
        if (effect_provider is None) != (effect_link_kind is None):
            raise ValueError("reviewed Aura provider/link pair is incomplete")
        result.append(
            _ReviewedAuraSpec(
                record_id=raw["record_id"],
                block_sequence=raw["block_sequence"],
                ability_ordinal=raw["ability_ordinal"],
                locator=raw["locator"],
                creature_name=raw["creature_name"],
                raw_key=raw["raw_key"],
                carrier_path=_path_from_claim(
                    raw["carrier_path"],
                    "reviewed Aura carrier path",
                ),
                member_ordinal=raw["member_ordinal"],
                expected_block_sha256=raw["expected_block_sha256"],
                expected_member_sha256=raw["expected_member_sha256"],
                expected_selection_sha256=raw[
                    "expected_selection_sha256"
                ],
                encoding=raw["encoding"],
                grammar_cohort=raw["grammar_cohort"],
                traits=_exact_strings(
                    raw["traits"],
                    "reviewed Aura traits",
                ),
                action_cost=action_cost,
                trigger=raw["trigger"],
                top_level_member_keys=_exact_strings(
                    raw["top_level_member_keys"],
                    "reviewed Aura top-level keys",
                    maximum=MAX_AURA_SOURCE_MEMBERS,
                    unique=False,
                ),
                aura_declaration_count=raw["aura_declaration_count"],
                area=_area_from_raw(raw["area"]),
                behavior=_behavior_from_raw(raw["behavior"]),
                issues=_issues_from_raw(raw["issues"]),
                route_family=raw["route_family"],
                effect_provider=effect_provider,
                effect_link_kind=effect_link_kind,
                damage_only=_damage_from_raw(raw["damage_only"]),
            )
        )
    specs = tuple(result)
    if specs != tuple(
        sorted(
            specs,
            key=lambda spec: (
                spec.block_sequence,
                spec.ability_ordinal,
                spec.record_id,
            ),
        )
    ):
        raise RuntimeError("reviewed Aura table is not in canonical order")
    if len({spec.record_id for spec in specs}) != len(specs):
        raise RuntimeError("reviewed Aura table has duplicate record IDs")
    if (
        len({spec.creature_name for spec in specs})
        != REVIEWED_AURA_CREATURE_COUNT
        or sum(spec.aura_declaration_count for spec in specs)
        != REVIEWED_AURA_DECLARATION_COUNT
    ):
        raise RuntimeError("reviewed Aura census invariants drifted")
    return specs


_REVIEWED_SPECS = _build_reviewed_specs(_RAW_REVIEWED_SPECS)
del _RAW_REVIEWED_SPECS


_FIXED_PROVIDER_SPECS = (
    _ProviderSpec(
        code="aura",
        rule_id="core-mc1:ability-glossary#^.ability[003]",
        relation="aura-convention",
        link_kind="exact-aura-trait-convention",
        locator="358.2",
        carrier_path=(RawMemberStep("^.ability", 5),),
        selection_path=(),
        expected_block_sha256=(
            "3f30455106cbb35f3f791ee121f33ea5612636ffd692c4fbbe825667ffb2ec39"
        ),
        expected_member_sha256=None,
        expected_selection_sha256=(
            "3f30455106cbb35f3f791ee121f33ea5612636ffd692c4fbbe825667ffb2ec39"
        ),
    ),
    _ProviderSpec(
        code="frightful",
        rule_id="core-mc1:ability-glossary#^.ability[014]",
        relation="effect",
        link_kind="exact-specialized-shorthand",
        locator="358.2",
        carrier_path=(RawMemberStep("^.ability", 16),),
        selection_path=(),
        expected_block_sha256=(
            "0b12b73e5bed46f72f225f50048136f6871b4cc051ec2cf0ea1d956915e7dc92"
        ),
        expected_member_sha256=None,
        expected_selection_sha256=(
            "0b12b73e5bed46f72f225f50048136f6871b4cc051ec2cf0ea1d956915e7dc92"
        ),
    ),
    _ProviderSpec(
        code="stench",
        rule_id="core-mc1:ability-glossary#^.ability[030]",
        relation="effect",
        link_kind="exact-specialized-shorthand",
        locator="358.2",
        carrier_path=(RawMemberStep("^.ability", 32),),
        selection_path=(),
        expected_block_sha256=(
            "189c0083d5b9ae7db0abc7a4af237abbb3548e09cb903a2b254a0362afb1f968"
        ),
        expected_member_sha256=None,
        expected_selection_sha256=(
            "189c0083d5b9ae7db0abc7a4af237abbb3548e09cb903a2b254a0362afb1f968"
        ),
    ),
    _ProviderSpec(
        code="nymph",
        rule_id="core-mc1:nymph#shared-nymphs-beauty",
        relation="effect",
        link_kind="exact-section-shared-rule-overlay",
        locator="245.4",
        carrier_path=(),
        selection_path=(RawMemberStep("~.p", 3),),
        expected_block_sha256=(
            "27989f98135b154fbe2ef8714fbe92d6021191e38f49e1e51b6d132eaa74d277"
        ),
        expected_member_sha256=(
            "2def1857a4dacce8f8401abdf63d4b8540301511d5646873959451ad9ff1f570"
        ),
        expected_selection_sha256=(
            "8e0dc7c2b1beb09d5b1b5cee55beb2b07e1dedc87726fea9f67697c691f3036b"
        ),
    ),
)


# These are current-cache address overlays for reviewed Aura members whose
# selected bytes did not change.  The historical review graph above remains
# the provenance record; this tuple accounts for narrowed ToC target paths,
# presentation members inserted into the surrounding creature block, and two
# reviewed adjacent-field repairs that left the selected Aura member bytes
# unchanged.  The final digest is the current surrounding block digest
# required by SourceAuthorityAdapter.resolve_rule().
_CURRENT_CONSUMER_REBINDS = (
    (
        "core-mc1/alghollthu#creature-001/ability-000",
        (("member", "^.creature", 1),),
        14,
        "26f0610e87922e1dce5087e60380da68984cb6255515e3c719b6cf3aa676e5da",
    ),
    (
        "core-mc1/bandersnatch#creature-000/ability-001",
        (
            ("member", "Bandersnatch", 1),
            ("member", "Bandersnatch", 0),
            ("member", "^.creature", 1),
        ),
        21,
        "d47c722070f9c0c7bd863597e25a89593ebd43bb34512ace28ff846c781cfc4b",
    ),
    (
        "core-mc1/basilisk#creature-000/ability-000",
        (
            ("member", "Basilisk", 1),
            ("member", "Basilisk", 0),
            ("member", "^.creature", 5),
        ),
        22,
        "ebbda7228c25c9d3f1f783562f3300d080371b1bb8fac26026f838882df39fb3",
    ),
    (
        "core-mc1/dragon#creature-000/ability-001",
        (
            ("member", "Young Adamantine Dragon", 1),
            ("member", "^.creature", 0),
        ),
        24,
        "bcca5fd723f6d78876f227348d6928c4405d3a0c5bcb9a2cc24c90194271ac3d",
    ),
    (
        "core-mc1/dragon#creature-001/ability-001",
        (
            ("member", "Adult Adamantine Dragon", 2),
            ("member", "^.creature", 0),
        ),
        24,
        "66ec0887183736dd2e6f70bc54da3b88a2316099931a1720c48c7f83a0fdadae",
    ),
    (
        "core-mc1/dragon#creature-002/ability-001",
        (
            ("member", "Ancient Adamantine Dragon", 3),
            ("member", "^.creature", 0),
        ),
        25,
        "02ad93ffa70bd7ceb63fcf1f966a94752b067247895d0e5ae5d3c0dcd65d3bf9",
    ),
    (
        "core-mc1/dragon#creature-006/ability-001",
        (
            ("member", "Young Diabolic Dragon", 1),
            ("member", "^.creature", 0),
        ),
        23,
        "b5d4bb1e6c7a1f1b827176748c20f6893cf3a1695e150999dff5f084e55b405c",
    ),
    (
        "core-mc1/dragon#creature-007/ability-001",
        (
            ("member", "Adult Diabolic Dragon", 2),
            ("member", "^.creature", 0),
        ),
        23,
        "b71f5cadeff233a7e165eb4d16323cc68a93532a08829eb70a9949af13d52d42",
    ),
    (
        "core-mc1/dragon#creature-008/ability-001",
        (
            ("member", "Ancient Diabolic Dragon", 3),
            ("member", "^.creature", 0),
        ),
        24,
        "e202b39ef58d4efb1a275a05e59c7d8cabdda0c977e3ac107b0d2761ae3deba6",
    ),
    (
        "core-mc1/dragon#creature-009/ability-001",
        (
            ("member", "Young Empyreal Dragon", 1),
            ("member", "^.creature", 0),
        ),
        23,
        "101f195f43b41788789cc618d3a4ff8b5c14a73483f904732afececa6c54c3b9",
    ),
    (
        "core-mc1/dragon#creature-010/ability-001",
        (
            ("member", "Adult Empyreal Dragon", 2),
            ("member", "^.creature", 0),
        ),
        23,
        "5d68770ca8caf1232f5d9534ec2222e662d0a618dd8dec80fac0799f1de4cdd9",
    ),
    (
        "core-mc1/dragon#creature-011/ability-001",
        (
            ("member", "Ancient Empyreal Dragon", 3),
            ("member", "^.creature", 0),
        ),
        24,
        "9dfb7db7a6701159aa1e29ff6591df76e19e9e1130e29cdfe0081661217b0132",
    ),
    (
        "core-mc1/dragon#creature-013/ability-000",
        (
            ("member", "Adult Fortune Dragon", 2),
            ("member", "^.creature", 0),
        ),
        19,
        "4400b1b28e31b70057a8c474a3a31d8097c810aae6fd4d1c09b586bc35aeaef2",
    ),
    (
        "core-mc1/dragon#creature-015/ability-001",
        (
            ("member", "Young Horned Dragon", 1),
            ("member", "^.creature", 0),
        ),
        22,
        "bced116c2767a74f9dbd1473920b90ca3806955dfb37b3489cb2643ae50b7797",
    ),
    (
        "core-mc1/dragon#creature-016/ability-001",
        (
            ("member", "Adult Horned Dragon", 2),
            ("member", "^.creature", 0),
        ),
        22,
        "154e08f1ae77e6e0e96873e30529aae4aac7b30eb91f3ba9c2f356aedafe15b8",
    ),
    (
        "core-mc1/dragon#creature-017/ability-001",
        (
            ("member", "Ancient Horned Dragon", 3),
            ("member", "^.creature", 0),
        ),
        23,
        "26c5540d51e6fdd280e728137888f137d4b6848fe38c821888ab1b9e482c565e",
    ),
    (
        "core-mc1/dragon-turtle#creature-000/ability-002",
        (
            ("member", "Dragon Turtle", 1),
            ("member", "Dragon Turtle", 0),
            ("member", "^.creature", 2),
        ),
        24,
        "d7fb09f7ff3e5dd35e33425b48d4abec1ab92475cd1aae32547997f5de8c106a",
    ),
    (
        "core-mc1/dullahan#creature-000/ability-000",
        (
            ("member", "Dullahan", 1),
            ("member", "Dullahan", 0),
            ("member", "^.creature", 3),
        ),
        23,
        "3a43cc65d94571dfea521187d9e056b2fbed7bd77e073ede100c0c703f8735cc",
    ),
    (
        "core-mc1/harpy#creature-000/ability-001",
        (
            ("member", "Harpy", 1),
            ("member", "Harpy", 0),
            ("member", "^.creature", 4),
        ),
        20,
        "0fe89d0cd0894b007935d8f93e4813bb7b9a28ac1235d671789c776af45b9fe5",
    ),
    (
        "core-mc1/kraken#creature-000/ability-000",
        (
            ("member", "Kraken", 1),
            ("member", "Kraken", 0),
            ("member", "^.creature", 1),
        ),
        22,
        "f6a711688f42ab103cb9cf6c6a48c03a1147b941354b89f9cc618b74d415560b",
    ),
    (
        "core-mc1/lich#creature-000/ability-000",
        (("member", "^.creature", 1),),
        23,
        "b41002c1049f0b7113fb5d1de9de6954e2935963340964018815940f04b615fd",
    ),
    (
        "core-mc1/medusa#creature-000/ability-000",
        (
            ("member", "Medusa", 1),
            ("member", "Medusa", 0),
            ("member", "^.creature", 2),
        ),
        21,
        "107dbaf886acaded78fdbd0d3edd1c4c802645d5c5923875f8d3a57eb7429819",
    ),
    (
        "core-mc1/nightmare#creature-000/ability-000",
        (
            ("member", "Nightmare", 1),
            ("member", "Nightmare", 1),
            ("member", "^.creature", 1),
        ),
        14,
        "1fbc75f0ca01579397340c19209c7d8b2b47bfb6d5c70e49ec4be5b80d3b76f7",
    ),
    (
        "core-mc1/phoenix#creature-000/ability-000",
        (
            ("member", "Phoenix", 1),
            ("member", "Phoenix", 0),
            ("member", "^.creature", 4),
        ),
        23,
        "d2411c880848ab2ba27c490a331eb2f9e9a50976b9edf6086e4636c7f71959d9",
    ),
    (
        "core-mc1/scarecrow#creature-000/ability-000",
        (
            ("member", "Scarecrow", 1),
            ("member", "Scarecrow", 0),
            ("member", "^.creature", 2),
        ),
        21,
        "9cec4f8c0bd151c4b403b01aade829e0c14baa98a88cbced665ea82bd3ee023e",
    ),
    (
        "core-mc1/shining-child#creature-000/ability-001",
        (
            ("member", "Shining Child", 1),
            ("member", "Shining Child", 0),
            ("member", "^.creature", 1),
        ),
        21,
        "ccda771d5991c70b5fc2d6e658258e226ce4f67cbebeb4991105bbe34d828c02",
    ),
)


def _current_consumer_binding(
    spec: _ReviewedAuraSpec,
    _rebinds: tuple[
        tuple[str, tuple[tuple[object, ...], ...], int, str],
        ...,
    ] = _CURRENT_CONSUMER_REBINDS,
    _path_builder: Any = _path_from_claim,
    _tuple_type: Any = tuple,
    _length: Any = len,
    _set_type: Any = set,
) -> tuple[
    tuple[RawMemberStep | RawIndexStep, ...],
    int,
    str,
]:
    if (
        _length(_rebinds) != 26
        or _length(_set_type(row[0] for row in _rebinds)) != 26
    ):
        raise AuraAddressabilityError(
            "current Aura binding table is invalid"
        )
    matches = _tuple_type(
        row for row in _rebinds if row[0] == spec.record_id
    )
    if _length(matches) > 1:
        raise AuraAddressabilityError(
            "current Aura binding is ambiguous"
        )
    if not matches:
        return (
            spec.carrier_path,
            spec.member_ordinal,
            spec.expected_block_sha256,
        )
    _record_id, raw_path, member_ordinal, block_sha256 = matches[0]
    _sha256(block_sha256, "current Aura block digest")
    if type(member_ordinal) is not int or member_ordinal < 0:
        raise AuraAddressabilityError(
            "current Aura member ordinal is invalid"
        )
    return (
        _path_builder(raw_path, "current Aura carrier path"),
        member_ordinal,
        block_sha256,
    )


def _consumer_requirement(
    spec: _ReviewedAuraSpec,
    requirement_type: type[RuleRequirement],
    _source_id: str = MONSTER_CORE_SOURCE_ID,
    _member_step_type: type[RawMemberStep] = RawMemberStep,
    _current_binding: Any = _current_consumer_binding,
) -> RuleRequirement:
    carrier_path, member_ordinal, block_sha256 = _current_binding(spec)
    return requirement_type(
        rule_id=spec.record_id,
        source_id=_source_id,
        locator=spec.locator,
        carrier_path=carrier_path,
        selection_path=(
            _member_step_type(spec.raw_key, member_ordinal),
        ),
        expected_block_sha256=block_sha256,
        expected_member_sha256=spec.expected_member_sha256,
        expected_value_sha256=spec.expected_selection_sha256,
        expected_selection_sha256=spec.expected_selection_sha256,
    )


def _fixed_provider_requirement(
    spec: _ProviderSpec,
    requirement_type: type[RuleRequirement],
    _source_id: str = MONSTER_CORE_SOURCE_ID,
) -> RuleRequirement:
    return requirement_type(
        rule_id=spec.rule_id,
        source_id=_source_id,
        locator=spec.locator,
        carrier_path=spec.carrier_path,
        selection_path=spec.selection_path,
        expected_block_sha256=spec.expected_block_sha256,
        expected_member_sha256=spec.expected_member_sha256,
        expected_value_sha256=spec.expected_selection_sha256,
        expected_selection_sha256=spec.expected_selection_sha256,
    )


def _local_provider_spec(
    code: str,
    specs: tuple[_ReviewedAuraSpec, ...],
    _make_provider: Any = _new_provider_spec,
    _member_step_type: type[RawMemberStep] = RawMemberStep,
    _current_binding: Any = _current_consumer_binding,
    _tuple_type: Any = tuple,
    _length: Any = len,
) -> _ProviderSpec:
    if not code.startswith("record:"):
        raise AuraLinkError("local Aura provider code is invalid")
    record_id = code.removeprefix("record:")
    matches = _tuple_type(
        spec for spec in specs if spec.record_id == record_id
    )
    if _length(matches) != 1:
        raise AuraLinkError(
            f"local Aura provider is absent or ambiguous: {record_id}"
        )
    provider = matches[0]
    carrier_path, member_ordinal, block_sha256 = _current_binding(
        provider
    )
    return _make_provider(
        code=code,
        rule_id=provider.record_id,
        relation="effect",
        link_kind="exact-local-same-name-inheritance",
        locator=provider.locator,
        carrier_path=carrier_path,
        selection_path=(
            _member_step_type(
                provider.raw_key,
                member_ordinal,
            ),
        ),
        expected_block_sha256=block_sha256,
        expected_member_sha256=provider.expected_member_sha256,
        expected_selection_sha256=provider.expected_selection_sha256,
    )


def _provider_specs_for(
    spec: _ReviewedAuraSpec,
    specs: tuple[_ReviewedAuraSpec, ...],
    fixed: tuple[_ProviderSpec, ...],
    _local_provider: Any = _local_provider_spec,
    _make_provider: Any = _new_provider_spec,
    _tuple_type: Any = tuple,
    _length: Any = len,
) -> tuple[_ProviderSpec, ...]:
    aura = _tuple_type(item for item in fixed if item.code == "aura")
    if _length(aura) != 1:
        raise AuraLinkError("reviewed Aura convention provider is invalid")
    if spec.effect_provider is None:
        return aura
    if spec.effect_provider.startswith("record:"):
        effect = _local_provider(spec.effect_provider, specs)
    else:
        matches = _tuple_type(
            item for item in fixed if item.code == spec.effect_provider
        )
        if _length(matches) != 1:
            raise AuraLinkError(
                f"reviewed Aura effect provider is invalid: "
                f"{spec.effect_provider}"
            )
        selected = matches[0]
        effect = _make_provider(
            code=selected.code,
            rule_id=selected.rule_id,
            relation=selected.relation,
            link_kind=(
                spec.effect_link_kind
                if spec.effect_link_kind is not None
                else selected.link_kind
            ),
            locator=selected.locator,
            carrier_path=selected.carrier_path,
            selection_path=selected.selection_path,
            expected_block_sha256=selected.expected_block_sha256,
            expected_member_sha256=selected.expected_member_sha256,
            expected_selection_sha256=(
                selected.expected_selection_sha256
            ),
        )
    if effect.link_kind != spec.effect_link_kind:
        raise AuraLinkError("reviewed Aura effect provider relation drifted")
    return (*aura, effect)


def _raw_serialized(
    value: RawSourceValue,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _array_type: type[RawSourceArray] = RawSourceArray,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _trim: Any = _trimmed,
    _set_type: Any = set,
    _exact_type: Any = type,
    _identity: Any = id,
    _tuple_type: type[tuple[object, ...]] = tuple,
    _primitive_types: frozenset[type[object]] = frozenset(
        (bool, int, float, str)
    ),
) -> Any:
    active: set[int] = _set_type()
    visited = 0

    def visit(item: RawSourceValue, depth: int) -> Any:
        nonlocal visited
        visited += 1
        if depth > 32 or visited > 4_096:
            raise AuraCompileError("Aura raw source exceeds its node bound")
        if _exact_type(item) is _object_type:
            identity = _identity(item)
            if identity in active:
                raise AuraCompileError("Aura raw source contains a cycle")
            active.add(identity)
            try:
                if _exact_type(item.members) is not _tuple_type:
                    raise TypeError("Aura raw object members must be exact")
                pairs: list[list[Any]] = []
                for member in item.members:
                    if _exact_type(member) is not _member_type:
                        raise TypeError(
                            "Aura raw object contains a foreign member"
                        )
                    pairs.append(
                        [
                            _trim(member.key, "Aura raw member key"),
                            visit(member.value, depth + 1),
                        ]
                    )
                return {"$orderedObject": pairs}
            finally:
                active.remove(identity)
        if _exact_type(item) is _array_type:
            identity = _identity(item)
            if identity in active:
                raise AuraCompileError("Aura raw source contains a cycle")
            active.add(identity)
            try:
                if _exact_type(item.items) is not _tuple_type:
                    raise TypeError("Aura raw array items must be exact")
                return [visit(child, depth + 1) for child in item.items]
            finally:
                active.remove(identity)
        if item is None or _exact_type(item) in _primitive_types:
            return item
        raise TypeError("Aura raw source contains a non-exact value")

    return visit(value, 0)


def _raw_strings(
    value: RawSourceValue,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _array_type: type[RawSourceArray] = RawSourceArray,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _set_type: Any = set,
    _exact_type: Any = type,
    _identity: Any = id,
    _tuple_type: Any = tuple,
) -> tuple[str, ...]:
    active: set[int] = _set_type()
    visited = 0

    def visit(item: RawSourceValue, depth: int) -> tuple[str, ...]:
        nonlocal visited
        visited += 1
        if depth > 32 or visited > 4_096:
            raise AuraCompileError("Aura raw source exceeds its node bound")
        if _exact_type(item) is str:
            return (item,)
        if _exact_type(item) is _array_type:
            identity = _identity(item)
            if identity in active:
                raise AuraCompileError("Aura raw source contains a cycle")
            active.add(identity)
            try:
                result: list[str] = []
                for child in item.items:
                    result.extend(visit(child, depth + 1))
                return _tuple_type(result)
            finally:
                active.remove(identity)
        if _exact_type(item) is _object_type:
            identity = _identity(item)
            if identity in active:
                raise AuraCompileError("Aura raw source contains a cycle")
            active.add(identity)
            try:
                result = []
                for member in item.members:
                    if _exact_type(member) is not _member_type:
                        raise TypeError(
                            "Aura raw source contains a foreign member"
                        )
                    result.extend(visit(member.value, depth + 1))
                return _tuple_type(result)
            finally:
                active.remove(identity)
        return ()

    return visit(value, 0)


def _trait_tokens(
    value: str,
    _exact_type: Any = type,
    _tuple_type: Any = tuple,
    _reject_any: Any = any,
) -> tuple[str, ...]:
    if _exact_type(value) is not str:
        raise TypeError("Aura trait text must be exact string")
    result = _tuple_type(item.strip() for item in value.split(","))
    if _reject_any(not item for item in result):
        raise AuraCompileError("Aura trait group contains an empty token")
    return result


def _array_strings(
    value: RawSourceValue,
    label: str,
    _array_type: type[RawSourceArray] = RawSourceArray,
    _exact_type: Any = type,
    _length: Any = len,
    _set_type: Any = set,
    _exact_sequence: Any = _exact_strings,
) -> tuple[str, ...]:
    raw: object = (
        value.items if _exact_type(value) is _array_type else (value,)
    )
    result = _exact_sequence(raw, label)
    if _length(result) != _length(
        _set_type(item.casefold() for item in result)
    ):
        raise AuraCompileError(f"{label} contains case-folded duplicates")
    return result


def _unique_member(
    value: RawSourceObject,
    key: str,
    *,
    required: bool,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _exact_type: Any = type,
    _tuple_type: Any = tuple,
    _length: Any = len,
) -> RawSourceMember | None:
    if (
        _exact_type(value) is not _object_type
        or _exact_type(value.members) is not _tuple_type
    ):
        raise TypeError("Aura source object must be exact")
    members = _tuple_type(
        member
        for member in value.members
        if _exact_type(member) is _member_type and member.key == key
    )
    if _length(members) > 1:
        raise AuraCompileError(f"Aura source has duplicate {key} members")
    if not members:
        if required:
            raise AuraCompileError(f"Aura source is missing {key}")
        return None
    return members[0]


def _flow_text(
    value: RawSourceValue,
    label: str,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _exact_type: Any = type,
    _tuple_type: type[tuple[object, ...]] = tuple,
    _length: Any = len,
    _reject_any: Any = any,
    _max_paragraphs: int = MAX_AURA_PARAGRAPHS,
    _trim: Any = _trimmed,
) -> str:
    if _exact_type(value) is str:
        return _trim(value, label)
    if _exact_type(value) is not _object_type:
        raise AuraCompileError(f"{label} must be string or paragraph flow")
    if (
        _exact_type(value.members) is not _tuple_type
        or not value.members
        or _length(value.members) > _max_paragraphs
        or _reject_any(
            _exact_type(member) is not _member_type
            or member.key != "~.p"
            or _exact_type(member.value) is not str
            for member in value.members
        )
    ):
        raise AuraCompileError(
            f"{label} is not a bounded duplicate-preserving paragraph flow"
        )
    return "\n\n".join(
        _trim(member.value, f"{label} paragraph")
        for member in value.members
    )


def _action_cost(
    value: str | None,
    _exact_type: Any = type,
) -> ActionCost:
    if value is None:
        return None
    if _exact_type(value) is not str:
        raise TypeError("Aura Action must be exact string")
    costs: dict[str, int | Literal["reaction"]] = {
        "single": 1,
        "two": 2,
        "three": 3,
        "reaction": "reaction",
    }
    try:
        return costs[value]
    except KeyError as failure:
        raise AuraCompileError(f"Aura Action is unsupported: {value}") from failure


def _new_projection(
    *,
    encoding: AuraEncoding,
    traits: tuple[str, ...],
    action_cost: ActionCost,
    trigger: str,
    effect_text: str,
    top_level_member_keys: tuple[str, ...],
    aura_declaration_count: int,
    _projection_type: type[_RawAuraProjection] = _RawAuraProjection,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
) -> _RawAuraProjection:
    result = _new(_projection_type)
    _setattr(result, "encoding", encoding)
    _setattr(result, "traits", traits)
    _setattr(result, "action_cost", action_cost)
    _setattr(result, "trigger", trigger)
    _setattr(result, "effect_text", effect_text)
    _setattr(
        result,
        "top_level_member_keys",
        top_level_member_keys,
    )
    _setattr(
        result,
        "aura_declaration_count",
        aura_declaration_count,
    )
    return result


def _raw_projection(
    member: RawSourceMember,
    _leading_group: re.Pattern[str] = _LEADING_TRAIT_GROUP_RE,
    _all_groups: re.Pattern[str] = _TRAIT_GROUP_RE,
    _tokens: Any = _trait_tokens,
    _trim: Any = _trimmed,
    _unique: Any = _unique_member,
    _array_values: Any = _array_strings,
    _flow: Any = _flow_text,
    _cost: Any = _action_cost,
    _strings: Any = _raw_strings,
    _make_projection: Any = _new_projection,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _exact_type: Any = type,
    _tuple_type: Any = tuple,
    _set_type: Any = set,
    _length: Any = len,
    _reject_any: Any = any,
    _max_members: int = MAX_AURA_SOURCE_MEMBERS,
    _max_traits: int = MAX_AURA_TRAITS,
) -> _RawAuraProjection | None:
    if (
        _exact_type(member) is not _member_type
        or _exact_type(member.key) is not str
    ):
        raise TypeError("Aura projection requires exact RawSourceMember")
    value = member.value
    if _exact_type(value) is str:
        prefix = _leading_group.match(value)
        if prefix is None:
            return None
        traits = _tokens(prefix.group("traits"))
        if "aura" not in _tuple_type(
            item.casefold() for item in traits
        ):
            return None
        encoding: AuraEncoding = "inline-scalar"
        action: ActionCost = None
        trigger = ""
        effect_text = _trim(value, "Aura scalar")
        top_level_member_keys: tuple[str, ...] = ()
        structured_declarations = 0
    elif _exact_type(value) is _object_type:
        if _length(value.members) > _max_members:
            raise AuraCompileError("Aura source exceeds the member bound")
        traits_member = _unique(value, "Traits", required=False)
        if traits_member is None:
            if (
                not value.members
                or _reject_any(
                    _exact_type(item) is not _member_type
                    or item.key != "~.p"
                    for item in value.members
                )
            ):
                return None
            effect_text = _flow(value, "Aura paragraph flow")
            prefix = _leading_group.match(effect_text)
            if prefix is None:
                return None
            traits = _tokens(prefix.group("traits"))
            if "aura" not in _tuple_type(
                item.casefold() for item in traits
            ):
                return None
            encoding = "ordered-paragraph-flow"
            action = None
            trigger = ""
            top_level_member_keys = _tuple_type(
                member.key for member in value.members
            )
            structured_declarations = 0
        else:
            traits = _array_values(traits_member.value, "Aura Traits")
            if "aura" not in _tuple_type(
                item.casefold() for item in traits
            ):
                return None
            description_member = _unique(
                value,
                "Description",
                required=True,
            )
            if description_member is None:
                raise AssertionError("required Aura Description vanished")
            effect_text = _flow(
                description_member.value,
                "Aura Description",
            )
            action_member = _unique(value, "Action", required=False)
            trigger_member = _unique(value, "Trigger", required=False)
            if (
                action_member is not None
                and _exact_type(action_member.value) is not str
            ):
                raise AuraCompileError("Aura Action must be exact string")
            if (
                trigger_member is not None
                and _exact_type(trigger_member.value) is not str
            ):
                raise AuraCompileError("Aura Trigger must be exact string")
            raw_action = (
                None
                if action_member is None
                else _trim(action_member.value, "Aura Action")
            )
            action = _cost(raw_action)
            trigger = (
                ""
                if trigger_member is None
                else _trim(trigger_member.value, "Aura Trigger")
            )
            if action == "reaction":
                if not trigger:
                    raise AuraCompileError("Aura reaction requires Trigger")
                encoding = "structured-reaction"
            elif action is not None:
                if trigger:
                    raise AuraCompileError(
                        "non-reaction Aura cannot carry Trigger"
                    )
                encoding = "structured-action"
            else:
                if trigger:
                    raise AuraCompileError(
                        "passive Aura cannot carry Trigger"
                    )
                encoding = "structured-passive"
            top_level_member_keys = _tuple_type(
                member.key for member in value.members
            )
            expected_keys = {
                "structured-passive": ("Traits", "Description"),
                "structured-action": (
                    "Action",
                    "Traits",
                    "Description",
                ),
                "structured-reaction": (
                    "Action",
                    "Traits",
                    "Trigger",
                    "Description",
                ),
            }[encoding]
            if top_level_member_keys != expected_keys:
                raise AuraCompileError(
                    "Aura structured member shape is not exact"
                )
            structured_declarations = 1
    else:
        return None

    lexical_declarations = 0
    for text in _strings(value):
        for match in _all_groups.finditer(text):
            tokens = _tokens(match.group("traits"))
            if "aura" in _tuple_type(
                item.casefold() for item in tokens
            ):
                lexical_declarations += 1
    declaration_count = structured_declarations + lexical_declarations
    if not 1 <= _length(traits) <= _max_traits:
        raise AuraCompileError("Aura trait sequence is empty or oversized")
    if _length(traits) != _length(
        _set_type(item.casefold() for item in traits)
    ):
        raise AuraCompileError("Aura trait sequence contains duplicates")
    return _make_projection(
        encoding=encoding,
        traits=traits,
        action_cost=action,
        trigger=trigger,
        effect_text=effect_text,
        top_level_member_keys=top_level_member_keys,
        aura_declaration_count=declaration_count,
    )


def _has_primary_aura_trait_structure(
    raw_member: object,
    projection: Any,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _exact_type: Any = type,
) -> bool:
    if _exact_type(raw_member) is not _member_type:
        raise TypeError("has_primary_aura_trait requires exact RawSourceMember")
    return projection(raw_member) is not None


def _primary_trait_contract(structure: Any, projection: Any) -> Any:
    def has_primary_aura_trait(
        raw_member: RawSourceMember,
        /,
    ) -> bool:
        """Whether exact primary ability grammar declares the Aura trait."""

        return structure(raw_member, projection)

    return has_primary_aura_trait


has_primary_aura_trait = _primary_trait_contract(
    _has_primary_aura_trait_structure,
    _raw_projection,
)
del _primary_trait_contract


def _copy_area(
    value: AuraArea,
    _area_type: type[AuraArea] = AuraArea,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
    _validate: Any = AuraArea.__post_init__,
) -> AuraArea:
    result = _new(_area_type)
    _setattr(result, "source_syntax", value.source_syntax)
    _setattr(result, "geometry_model", value.geometry_model)
    _setattr(result, "value", value.value)
    _setattr(result, "unit", value.unit)
    _setattr(result, "radius_feet", value.radius_feet)
    _setattr(
        result,
        "combat_grid_eligible",
        value.combat_grid_eligible,
    )
    _validate(result)
    return result


def _copy_immunity(
    value: AuraTemporaryImmunity | None,
    _immunity_type: type[AuraTemporaryImmunity] = AuraTemporaryImmunity,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
    _validate: Any = AuraTemporaryImmunity.__post_init__,
) -> AuraTemporaryImmunity | None:
    if value is None:
        return None
    result = _new(_immunity_type)
    _setattr(result, "duration", value.duration)
    _setattr(result, "unit", value.unit)
    _setattr(result, "grant", value.grant)
    _setattr(result, "scope", value.scope)
    _validate(result)
    return result


def _copy_behavior(
    value: AuraBehavior,
    _behavior_type: type[AuraBehavior] = AuraBehavior,
    _copy_immunity_value: Any = _copy_immunity,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
    _validate: Any = AuraBehavior.__post_init__,
) -> AuraBehavior:
    result = _new(_behavior_type)
    _setattr(result, "exposure_triggers", value.exposure_triggers)
    _setattr(result, "save_kinds", value.save_kinds)
    _setattr(
        result,
        "temporary_immunity",
        _copy_immunity_value(value.temporary_immunity),
    )
    _setattr(result, "sensory_traits", value.sensory_traits)
    _setattr(
        result,
        "sensory_adjacent_traits",
        value.sensory_adjacent_traits,
    )
    _setattr(
        result,
        "generic_damage_only_once_per_round",
        value.generic_damage_only_once_per_round,
    )
    _setattr(result, "runnable_source", value.runnable_source)
    _validate(result)
    return result


def _copy_issue_value(
    value: AuraSourceIssue,
    *,
    issue_type: type[AuraSourceIssue],
    new: Any,
    setattribute: Any,
    validate: Any,
) -> AuraSourceIssue:
    result = new(issue_type)
    setattribute(result, "kind", value.kind)
    setattribute(result, "severity", value.severity)
    setattribute(result, "detail", value.detail)
    validate(result)
    return result


def _copy_issues(
    values: tuple[AuraSourceIssue, ...],
    _issue_type: type[AuraSourceIssue] = AuraSourceIssue,
    _tuple_type: Any = tuple,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
    _validate: Any = AuraSourceIssue.__post_init__,
    _copy_one: Any = _copy_issue_value,
) -> tuple[AuraSourceIssue, ...]:
    return _tuple_type(
        _copy_one(
            value,
            issue_type=_issue_type,
            new=_new,
            setattribute=_setattr,
            validate=_validate,
        )
        for value in values
    )


def _damage_for(
    spec: _ReviewedAuraSpec,
    projection: _RawAuraProjection,
    _damage_type: type[AuraDamageOnly] = AuraDamageOnly,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
    _validate: Any = AuraDamageOnly.__post_init__,
) -> AuraDamageOnly | None:
    if spec.damage_only is None:
        return None
    (
        radius_feet,
        dice_count,
        die_sides,
        damage_type,
        save_dc,
        save_kind,
    ) = spec.damage_only
    damage = _new(_damage_type)
    _setattr(damage, "radius_feet", radius_feet)
    _setattr(damage, "dice_count", dice_count)
    _setattr(damage, "die_sides", die_sides)
    _setattr(damage, "damage_type", damage_type)
    _setattr(damage, "save_dc", save_dc)
    _setattr(damage, "save_kind", save_kind)
    _setattr(damage, "source_text", projection.effect_text)
    _validate(damage)
    if (
        damage.radius_feet != spec.area.radius_feet
        or spec.behavior.exposure_triggers != ("entry", "start-turn")
        or spec.behavior.save_kinds != (damage.save_kind,)
        or not spec.behavior.generic_damage_only_once_per_round
    ):
        raise AuraCompileError("Aura damage shorthand review drifted")
    return damage


def _new_deferral(
    *,
    kind: DeferredAuraKind,
    phase: Literal["source", "link", "runtime"],
    source_text: str,
    required_contract: str,
    _deferral_type: type[DeferredAuraMechanic] = DeferredAuraMechanic,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
    _validate: Any = DeferredAuraMechanic.__post_init__,
) -> DeferredAuraMechanic:
    result = _new(_deferral_type)
    _setattr(result, "kind", kind)
    _setattr(result, "phase", phase)
    _setattr(result, "source_text", source_text)
    _setattr(result, "required_contract", required_contract)
    _validate(result)
    return result


def _new_route(
    *,
    family_id: AuraRouteFamily,
    provider_id: str | None,
    link_kind: str | None,
    _route_type: type[AuraEffectRoute] = AuraEffectRoute,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
    _validate: Any = AuraEffectRoute.__post_init__,
) -> AuraEffectRoute:
    result = _new(_route_type)
    _setattr(result, "family_id", family_id)
    _setattr(result, "provider_id", provider_id)
    _setattr(result, "link_kind", link_kind)
    _validate(result)
    return result


def _deferrals_for(
    spec: _ReviewedAuraSpec,
    projection: _RawAuraProjection,
    _make_deferral: Any = _new_deferral,
    _list_type: Any = list,
    _tuple_type: Any = tuple,
    _reject_any: Any = any,
) -> tuple[DeferredAuraMechanic, ...]:
    result: list[DeferredAuraMechanic] = _list_type()
    if spec.grammar_cohort in {
        "frightful-presence-shorthand",
        "stench-shorthand",
    }:
        result.append(
            _make_deferral(
                kind="specialized-family-handoff",
                phase="link",
                source_text=projection.effect_text,
                required_contract=(
                    "exact specialized compiler plus shared Aura shell runtime"
                ),
            )
        )
    elif spec.grammar_cohort in {
        "frightful-presence-overlay",
        "local-same-name-inheritance",
        "section-rule-overlay",
    }:
        result.append(
            _make_deferral(
                kind="linked-effect-runtime",
                phase="runtime",
                source_text=projection.effect_text,
                required_contract=(
                    "resolved provider effect plus local Aura overrides"
                ),
            )
        )
    elif spec.grammar_cohort == "generic-damage-only-shorthand":
        result.append(
            _make_deferral(
                kind="generic-aura-runtime",
                phase="runtime",
                source_text=projection.effect_text,
                required_contract=(
                    "Aura membership and target+aura+round exposure identity"
                ),
            )
        )
    elif spec.grammar_cohort == "action-bearing-aura":
        result.append(
            _make_deferral(
                kind="action-aura-runtime",
                phase="runtime",
                source_text=projection.effect_text,
                required_contract=(
                    "activation, dismissal, duration, and local effect adapter"
                ),
            )
        )
    else:
        result.append(
            _make_deferral(
                kind="local-effect-adapter",
                phase="runtime",
                source_text=projection.effect_text,
                required_contract="reviewed exact local Aura effect adapter",
            )
        )
    if not spec.area.combat_grid_eligible:
        result.append(
            _make_deferral(
                kind="non-grid-domain",
                phase="runtime",
                source_text=projection.effect_text,
                required_contract=(
                    "campaign-scale claimed-domain geometry and lifecycle"
                ),
            )
        )
    if "each-round-ambiguous" in spec.behavior.exposure_triggers:
        result.append(
            _make_deferral(
                kind="timing-policy",
                phase="runtime",
                source_text=projection.effect_text,
                required_contract=(
                    "explicit participant-turn anchor for each-round exposure"
                ),
            )
        )
    if _reject_any(
        issue.severity == "compile-reject" for issue in spec.issues
    ):
        result.append(
            _make_deferral(
                kind="source-repair",
                phase="source",
                source_text=projection.effect_text,
                required_contract=(
                    "one repaired semantic ability boundary and fresh source hash"
                ),
            )
        )
    return _tuple_type(result)


def _validate_area_text(
    area: AuraArea,
    projection: _RawAuraProjection,
    _escape: Any = re.escape,
    _search: Any = re.search,
    _ascii: Any = re.ASCII,
    _text_type: Any = str,
) -> None:
    value = _escape(_text_type(area.value))
    if area.source_syntax == "leading-feet":
        if projection.encoding in {
            "inline-scalar",
            "ordered-paragraph-flow",
        }:
            pattern = rf"^[ \t]*\([^()]*\)[ \t]*{value} feet\b"
        else:
            pattern = rf"^[ \t]*{value} feet\b"
        haystack = projection.effect_text
    elif area.source_syntax == "embedded-foot-emanation":
        pattern = rf"\b{value}-foot emanation\b"
        haystack = projection.effect_text
    elif area.source_syntax == "trigger-range":
        pattern = rf"\bwithin {value} feet\b"
        haystack = projection.trigger
    elif area.source_syntax == "domain-distance":
        pattern = rf"\bwithin {value} miles?\b"
        haystack = projection.effect_text
    elif area.source_syntax == "claimed-domain-radius":
        pattern = rf"\b(?:up to )?{value}-mile radius\b"
        haystack = projection.effect_text
    else:
        return
    if _search(pattern, haystack, _ascii) is None:
        raise AuraCompileError(
            "reviewed Aura area is absent from exact source text"
        )


def _projection_matches(
    spec: _ReviewedAuraSpec,
    projection: _RawAuraProjection,
    _validate_area: Any = _validate_area_text,
) -> None:
    if (
        projection.encoding != spec.encoding
        or projection.traits != spec.traits
        or projection.action_cost != spec.action_cost
        or projection.trigger != spec.trigger
        or projection.top_level_member_keys
        != spec.top_level_member_keys
        or projection.aura_declaration_count
        != spec.aura_declaration_count
    ):
        raise AuraCompileError(
            f"reviewed Aura projection drifted: {spec.record_id}"
        )
    _validate_area(spec.area, projection)
    if (
        (spec.grammar_cohort == "action-bearing-aura")
        != (projection.action_cost is not None)
    ):
        raise AuraCompileError("Aura action cohort drifted")
    if (
        (spec.grammar_cohort == "generic-damage-only-shorthand")
        != (spec.damage_only is not None)
    ):
        raise AuraCompileError("Aura damage cohort drifted")


def _carrier_creature_name(
    carrier: VerifiedSourceCarrier,
    _carrier_type: type[VerifiedSourceCarrier] = VerifiedSourceCarrier,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _exact_type: Any = type,
    _getattribute: Any = object.__getattribute__,
    _tuple_type: Any = tuple,
    _length: Any = len,
) -> str:
    if _exact_type(carrier) is not _carrier_type:
        raise AuraAddressabilityError("Aura carrier is not exact")
    block = _getattribute(carrier, "raw_block")
    if _exact_type(block) is not _object_type:
        raise AuraAddressabilityError("Aura carrier is not an object")
    names = _tuple_type(
        member.value
        for member in block.members
        if (
            _exact_type(member) is _member_type
            and member.key == "Name"
            and _exact_type(member.value) is str
        )
    )
    if _length(names) != 1:
        raise AuraAddressabilityError(
            "Aura creature carrier has no unique exact Name"
        )
    return names[0]


def _selection_fields(
    value: VerifiedSourceSelection,
    _selection_type: type[VerifiedSourceSelection] = VerifiedSourceSelection,
    _exact_type: Any = type,
    _getattribute: Any = object.__getattribute__,
) -> tuple[object, ...]:
    if _exact_type(value) is not _selection_type:
        raise AuraAddressabilityError("Aura selection is not exact")
    return (
        _getattribute(value, "address"),
        _getattribute(value, "block_sha256"),
        _getattribute(value, "member_sha256"),
        _getattribute(value, "value_sha256"),
        _getattribute(value, "selection_sha256"),
    )


def _same_selection(
    left: VerifiedSourceSelection,
    right: VerifiedSourceSelection,
    _fields: Any = _selection_fields,
    _address_type: type[SourceAddress] = SourceAddress,
    _exact_type: Any = type,
) -> bool:
    left_fields = _fields(left)
    right_fields = _fields(right)
    left_address = left_fields[0]
    right_address = right_fields[0]
    return (
        _exact_type(left_address) is _address_type
        and _exact_type(right_address) is _address_type
        and left_address.source_id == right_address.source_id
        and left_address.locator == right_address.locator
        and left_address.section_id == right_address.section_id
        and left_address.target_path == right_address.target_path
        and left_address.carrier_path == right_address.carrier_path
        and left_address.selection_path == right_address.selection_path
        and left_address.span == right_address.span
        and left_fields[1:] == right_fields[1:]
    )


def _serialize_step(
    step: RawMemberStep | RawIndexStep,
    _exact_type: Any = type,
    _member_step_type: type[RawMemberStep] = RawMemberStep,
    _index_step_type: type[RawIndexStep] = RawIndexStep,
) -> SerializedObject:
    if _exact_type(step) is _member_step_type:
        return {
            "kind": "member",
            "rawKey": step.raw_key,
            "memberOrdinal": step.member_ordinal,
        }
    if _exact_type(step) is _index_step_type:
        return {
            "kind": "index",
            "itemOrdinal": step.item_ordinal,
        }
    raise AuraAddressabilityError("Aura source path contains foreign step")


def _serialize_address(
    address: SourceAddress,
    _serialize_path_step: Any = _serialize_step,
    _exact_type: Any = type,
    _address_type: type[SourceAddress] = SourceAddress,
    _span_type: type[TextSpan] = TextSpan,
) -> SerializedObject:
    if _exact_type(address) is not _address_type:
        raise AuraAddressabilityError("Aura source address is not exact")
    if (
        address.span is not None
        and _exact_type(address.span) is not _span_type
    ):
        raise AuraAddressabilityError("Aura source span is not exact")
    return {
        "sourceId": address.source_id,
        "locator": address.locator,
        "sectionId": address.section_id,
        "targetPath": [
            _serialize_path_step(step) for step in address.target_path
        ],
        "carrierPath": [
            _serialize_path_step(step) for step in address.carrier_path
        ],
        "selectionPath": [
            _serialize_path_step(step) for step in address.selection_path
        ],
        "span": (
            None
            if address.span is None
            else {"start": address.span.start, "end": address.span.end}
        ),
    }


def _serialize_receipt(
    receipt: SourceReceipt,
    _serialize_source_address: Any = _serialize_address,
    _json_dumps: Any = json.dumps,
    _sha256_digest: Any = hashlib.sha256,
    _exact_type: Any = type,
    _receipt_type: type[SourceReceipt] = SourceReceipt,
) -> SerializedObject:
    if _exact_type(receipt) is not _receipt_type:
        raise AuraAddressabilityError("Aura source receipt is not exact")
    body: SerializedObject = {
        "schema": 1,
        "kind": "pf2er-source-receipt",
        "ruleset": receipt.ruleset,
        "authorityDigest": receipt.authority_digest,
        "address": _serialize_source_address(receipt.address),
        "hashes": {
            "blockSha256": receipt.block_sha256,
            "memberSha256": receipt.member_sha256,
            "valueSha256": receipt.value_sha256,
            "selectionSha256": receipt.selection_sha256,
        },
    }
    encoded = _json_dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {**body, "digest": _sha256_digest(encoded).hexdigest()}


def _serialize_requirement(
    requirement: RuleRequirement,
    _serialize_path_step: Any = _serialize_step,
    _exact_type: Any = type,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
) -> SerializedObject:
    if _exact_type(requirement) is not _requirement_type:
        raise AuraLinkError("Aura provider requirement is not exact")
    return {
        "ruleId": requirement.rule_id,
        "sourceId": requirement.source_id,
        "locator": requirement.locator,
        "carrierPath": [
            _serialize_path_step(step)
            for step in requirement.carrier_path
        ],
        "selectionPath": [
            _serialize_path_step(step)
            for step in requirement.selection_path
        ],
        "span": (
            None
            if requirement.span is None
            else {
                "start": requirement.span.start,
                "end": requirement.span.end,
            }
        ),
        "expectedHashes": {
            "blockSha256": requirement.expected_block_sha256,
            "memberSha256": requirement.expected_member_sha256,
            "valueSha256": requirement.expected_value_sha256,
            "selectionSha256": (
                requirement.expected_selection_sha256
            ),
        },
    }


def _serialize_rule(
    rule: VerifiedRuleReceipt,
    _serialize_rule_requirement: Any = _serialize_requirement,
    _serialize_source_receipt: Any = _serialize_receipt,
    _exact_type: Any = type,
    _rule_type: type[VerifiedRuleReceipt] = VerifiedRuleReceipt,
    _getattribute: Any = object.__getattribute__,
) -> SerializedObject:
    if _exact_type(rule) is not _rule_type:
        raise AuraLinkError("Aura verified provider is not exact")
    return {
        "ruleId": _getattribute(rule, "rule_id"),
        "requirement": _serialize_rule_requirement(
            _getattribute(rule, "requirement")
        ),
        "source": _serialize_source_receipt(
            _getattribute(rule, "receipt")
        ),
    }


def _serialize_area_value(
    value: AuraArea,
    _exact_type: Any = type,
    _value_type: type[AuraArea] = AuraArea,
) -> SerializedObject:
    if _exact_type(value) is not _value_type:
        raise AuraCompileError("compiled Aura area is not exact")
    result: SerializedObject = {
        "sourceSyntax": value.source_syntax,
        "geometryModel": value.geometry_model,
        "value": value.value,
        "unit": value.unit,
        "combatGridEligible": value.combat_grid_eligible,
    }
    if value.radius_feet is not None:
        result["radiusFeet"] = value.radius_feet
    return result


def _serialize_behavior_value(
    value: AuraBehavior,
    _exact_type: Any = type,
    _value_type: type[AuraBehavior] = AuraBehavior,
    _immunity_type: type[AuraTemporaryImmunity] = AuraTemporaryImmunity,
) -> SerializedObject:
    if _exact_type(value) is not _value_type:
        raise AuraCompileError("compiled Aura behavior is not exact")
    immunity = value.temporary_immunity
    if immunity is not None and _exact_type(immunity) is not _immunity_type:
        raise AuraCompileError("compiled Aura immunity is not exact")
    return {
        "exposureTriggers": [
            item for item in value.exposure_triggers
        ],
        "saveKinds": [item for item in value.save_kinds],
        "temporaryImmunity": (
            None
            if immunity is None
            else {
                "duration": immunity.duration,
                "unit": immunity.unit,
                "grant": immunity.grant,
                "scope": immunity.scope,
            }
        ),
        "sensoryTraits": [item for item in value.sensory_traits],
        "sensoryAdjacentTraits": [
            item for item in value.sensory_adjacent_traits
        ],
        "genericDamageOnlyOncePerRound": (
            value.generic_damage_only_once_per_round
        ),
        "runnableSource": value.runnable_source,
    }


def _serialize_issue_value(
    value: AuraSourceIssue,
    _exact_type: Any = type,
    _value_type: type[AuraSourceIssue] = AuraSourceIssue,
) -> SerializedObject:
    if _exact_type(value) is not _value_type:
        raise AuraCompileError("compiled Aura issue is not exact")
    return {
        "kind": value.kind,
        "severity": value.severity,
        "detail": value.detail,
    }


def _serialize_damage_value(
    value: AuraDamageOnly,
    _exact_type: Any = type,
    _value_type: type[AuraDamageOnly] = AuraDamageOnly,
) -> SerializedObject:
    if _exact_type(value) is not _value_type:
        raise AuraCompileError("compiled Aura damage is not exact")
    return {
        "type": "generic-aura-damage-only",
        "radiusFeet": value.radius_feet,
        "damage": {
            "dice": {
                "count": value.dice_count,
                "sides": value.die_sides,
            },
            "type": value.damage_type,
        },
        "save": {
            "dc": value.save_dc,
            "kind": value.save_kind,
            "basic": True,
        },
        "exposureTriggers": ["entry", "start-turn"],
        "oncePerRound": True,
        "sourceText": value.source_text,
    }


def _serialize_route_value(
    value: AuraEffectRoute,
    _exact_type: Any = type,
    _value_type: type[AuraEffectRoute] = AuraEffectRoute,
) -> SerializedObject:
    if _exact_type(value) is not _value_type:
        raise AuraCompileError("compiled Aura effect route is not exact")
    result: SerializedObject = {
        "familyId": value.family_id,
        "supportState": "compile-link-only",
    }
    if value.provider_id is not None:
        result["providerId"] = value.provider_id
    if value.link_kind is not None:
        result["linkKind"] = value.link_kind
    return result


def _serialize_deferral_value(
    value: DeferredAuraMechanic,
    _exact_type: Any = type,
    _value_type: type[DeferredAuraMechanic] = DeferredAuraMechanic,
) -> SerializedObject:
    if _exact_type(value) is not _value_type:
        raise AuraCompileError("compiled Aura deferral is not exact")
    return {
        "kind": value.kind,
        "phase": value.phase,
        "sourceText": value.source_text,
        "requiredContract": value.required_contract,
        "status": "deferred",
        "blocks": "registry-activation",
    }


@dataclass(frozen=True, slots=True)
class _ArtifactState:
    spec: _ReviewedAuraSpec
    projection: _RawAuraProjection
    consumer_rule: VerifiedRuleReceipt
    provider_specs: tuple[_ProviderSpec, ...]
    providers: tuple[VerifiedRuleReceipt, ...]
    area: AuraArea
    behavior: AuraBehavior
    issues: tuple[AuraSourceIssue, ...]
    damage_only: AuraDamageOnly | None
    deferrals: tuple[DeferredAuraMechanic, ...]
    effect_route: AuraEffectRoute


def _new_artifact_state(
    *,
    spec: _ReviewedAuraSpec,
    projection: _RawAuraProjection,
    consumer_rule: VerifiedRuleReceipt,
    provider_specs: tuple[_ProviderSpec, ...],
    providers: tuple[VerifiedRuleReceipt, ...],
    area: AuraArea,
    behavior: AuraBehavior,
    issues: tuple[AuraSourceIssue, ...],
    damage_only: AuraDamageOnly | None,
    deferrals: tuple[DeferredAuraMechanic, ...],
    effect_route: AuraEffectRoute,
    _state_type: type[_ArtifactState] = _ArtifactState,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
) -> _ArtifactState:
    result = _new(_state_type)
    _setattr(result, "spec", spec)
    _setattr(result, "projection", projection)
    _setattr(result, "consumer_rule", consumer_rule)
    _setattr(result, "provider_specs", provider_specs)
    _setattr(result, "providers", providers)
    _setattr(result, "area", area)
    _setattr(result, "behavior", behavior)
    _setattr(result, "issues", issues)
    _setattr(result, "damage_only", damage_only)
    _setattr(result, "deferrals", deferrals)
    _setattr(result, "effect_route", effect_route)
    return result


def _class_hook_guard_contract(
    classes: tuple[type[object], ...],
    constructor_classes: tuple[type[object], ...],
    method_classes: tuple[type[object], ...],
    error_type: type[AuraAddressabilityError],
    _type_getattribute: Any = type.__getattribute__,
    _tuple_type: Any = tuple,
) -> Any:
    expected = _tuple_type(
        (
            class_type,
            _type_getattribute(class_type, "__getattribute__"),
            _tuple_type(
                (
                    slot_name,
                    _type_getattribute(class_type, slot_name),
                )
                for slot_name in _type_getattribute(
                    class_type,
                    "__slots__",
                )
            ),
        )
        for class_type in classes
    )
    expected_initializers = _tuple_type(
        (
            class_type,
            _tuple_type(
                (
                    method_name,
                    _type_getattribute(class_type, method_name),
                )
                for method_name in (
                    "__new__",
                    "__init__",
                    "__post_init__",
                )
                if (
                    method_name != "__post_init__"
                    or method_name in _type_getattribute(
                        class_type,
                        "__dict__",
                    )
                )
            ),
        )
        for class_type in constructor_classes
    )
    ignored_class_fields = {
        "__annotations__",
        "__dataclass_fields__",
        "__dataclass_params__",
        "__dict__",
        "__doc__",
        "__match_args__",
        "__module__",
        "__slots__",
        "__weakref__",
    }
    def exact_class_fields(
        class_type: type[object],
    ) -> tuple[tuple[str, object], ...]:
        class_fields = _type_getattribute(class_type, "__dict__")
        slots = _type_getattribute(class_type, "__slots__")
        return _tuple_type(
            (field_name, class_fields[field_name])
            for field_name in class_fields
            if (
                field_name not in ignored_class_fields
                and field_name not in slots
            )
        )

    expected_methods = _tuple_type(
        (class_type, exact_class_fields(class_type))
        for class_type in method_classes
    )

    def guard() -> None:
        for class_type, expected_getattribute, expected_slots in expected:
            if (
                _type_getattribute(class_type, "__getattribute__")
                is not expected_getattribute
            ):
                raise error_type(
                    "compiled Aura internal class hooks were rebound"
                )
            for slot_name, expected_descriptor in expected_slots:
                if (
                    _type_getattribute(class_type, slot_name)
                    is not expected_descriptor
                ):
                    raise error_type(
                        "compiled Aura internal class fields were rebound"
                    )
        for class_type, constructor_methods in expected_initializers:
            for method_name, expected_method in constructor_methods:
                if (
                    _type_getattribute(class_type, method_name)
                    is not expected_method
                ):
                    raise error_type(
                        "compiled Aura authority constructors were rebound"
                    )
        for class_type, class_methods in expected_methods:
            current_fields = _type_getattribute(
                class_type,
                "__dict__",
            )
            for field_name, expected_method in class_methods:
                if (
                    current_fields.get(field_name)
                    is not expected_method
                ):
                    raise error_type(
                        "compiled Aura authority methods were rebound"
                    )

    return guard


_require_exact_class_hooks = _class_hook_guard_contract(
    (
        _RawAuraProjection,
        _ReviewedAuraSpec,
        _ProviderSpec,
        AuraArea,
        AuraTemporaryImmunity,
        AuraBehavior,
        AuraSourceIssue,
        AuraDamageOnly,
        DeferredAuraMechanic,
        AuraEffectRoute,
        _ArtifactState,
        RawSourceMember,
        RawSourceObject,
        RawSourceArray,
        RawMemberStep,
        RawIndexStep,
        TextSpan,
        SourceAddress,
        RuleRequirement,
        SourceReceipt,
        VerifiedSourceCarrier,
        VerifiedSourceSelection,
        VerifiedRuleReceipt,
        AuthoritySnapshot,
        SourceAuthorityAdapter,
    ),
    (
        RawSourceMember,
        RawSourceObject,
        RawSourceArray,
        RawMemberStep,
        RawIndexStep,
        TextSpan,
        SourceAddress,
        RuleRequirement,
        SourceReceipt,
        VerifiedSourceCarrier,
        VerifiedSourceSelection,
        VerifiedRuleReceipt,
    ),
    (
        RawSourceMember,
        RawSourceObject,
        RawSourceArray,
        RawMemberStep,
        RawIndexStep,
        TextSpan,
        SourceAddress,
        RuleRequirement,
        SourceReceipt,
        VerifiedSourceCarrier,
        VerifiedSourceSelection,
        VerifiedRuleReceipt,
        AuthoritySnapshot,
        SourceAuthorityAdapter,
    ),
    AuraAddressabilityError,
)
del _class_hook_guard_contract


def _review_graph_guard_contract(
    specs: tuple[_ReviewedAuraSpec, ...],
    providers: tuple[_ProviderSpec, ...],
    error_type: type[AuraAddressabilityError],
    _exact_type: Any = type,
    _object_getattribute: Any = object.__getattribute__,
    _tuple_type: Any = tuple,
    _set_type: Any = set,
    _identity: Any = id,
    _json_dumps: Any = json.dumps,
    _sha256_digest: Any = hashlib.sha256,
) -> tuple[str, Any]:
    record_types = (
        (
            _ReviewedAuraSpec,
            "reviewed-spec",
            _ReviewedAuraSpec.__slots__,
        ),
        (
            _ProviderSpec,
            "provider-spec",
            _ProviderSpec.__slots__,
        ),
        (AuraArea, "area", AuraArea.__slots__),
        (
            AuraTemporaryImmunity,
            "temporary-immunity",
            AuraTemporaryImmunity.__slots__,
        ),
        (AuraBehavior, "behavior", AuraBehavior.__slots__),
        (AuraSourceIssue, "source-issue", AuraSourceIssue.__slots__),
        (RawMemberStep, "member-step", RawMemberStep.__slots__),
        (RawIndexStep, "index-step", RawIndexStep.__slots__),
    )

    def digest() -> str:
        active: set[int] = _set_type()

        def visit(value: object) -> object:
            value_type = _exact_type(value)
            if value is None or value_type in (bool, int, str):
                return value
            if value_type is _tuple_type:
                identity = _identity(value)
                if identity in active:
                    raise error_type(
                        "reviewed Aura graph contains a cycle"
                    )
                active.add(identity)
                try:
                    return [
                        "tuple",
                        [visit(item) for item in value],
                    ]
                finally:
                    active.remove(identity)
            for class_type, type_tag, slot_names in record_types:
                if value_type is class_type:
                    identity = _identity(value)
                    if identity in active:
                        raise error_type(
                            "reviewed Aura graph contains a cycle"
                        )
                    active.add(identity)
                    try:
                        return [
                            type_tag,
                            [
                                [
                                    slot_name,
                                    visit(
                                        _object_getattribute(
                                            value,
                                            slot_name,
                                        )
                                    ),
                                ]
                                for slot_name in slot_names
                            ],
                        ]
                    finally:
                        active.remove(identity)
            raise error_type(
                "reviewed Aura graph contains a foreign value"
            )

        encoded = _json_dumps(
            [visit(specs), visit(providers)],
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return _sha256_digest(encoded).hexdigest()

    expected_digest = digest()

    def guard() -> None:
        if digest() != expected_digest:
            raise error_type("reviewed Aura graph integrity failed")

    return expected_digest, guard


REVIEWED_AURA_GRAPH_SHA256 = (
    "8f5818c8f78aeca702bc55c431e73869acf7a7ef0091f1c4451e0a6e2fdb8d7c"
)
(
    _loaded_review_graph_sha256,
    _require_exact_review_graph,
) = _review_graph_guard_contract(
    _REVIEWED_SPECS,
    _FIXED_PROVIDER_SPECS,
    AuraAddressabilityError,
)
if _loaded_review_graph_sha256 != REVIEWED_AURA_GRAPH_SHA256:
    raise RuntimeError("reviewed Aura graph digest drifted during import")
del _loaded_review_graph_sha256
del _review_graph_guard_contract


def _artifact_validation_gateway() -> tuple[
    Any,
    Any,
]:
    validator: Any = None

    def bind(value: Any) -> None:
        nonlocal validator
        if validator is not None:
            raise RuntimeError("Aura artifact validator is already bound")
        validator = value

    def validate(value: object) -> _ArtifactState:
        if validator is None:
            raise RuntimeError("Aura artifact validator is not bound")
        return validator(value)

    return bind, validate


_bind_artifact_validator, _artifact_validation_method = (
    _artifact_validation_gateway()
)
del _artifact_validation_gateway


def _artifact_public_contract(validate: Any) -> Any:
    def decorate(method: Any) -> Any:
        def validated(instance: object, *args: object, **kwargs: object) -> Any:
            if args or kwargs:
                raise TypeError(
                    "compiled Aura public accessors accept no arguments"
                )
            state = validate(instance)
            return method(instance, state)

        return validated

    return decorate


_artifact_public = _artifact_public_contract(
    _artifact_validation_method
)
del _artifact_public_contract
del _artifact_validation_method


@final
@dataclass(frozen=True, slots=True, init=False)
class CompiledAuraSource:
    """One authority-bound, compile-only Aura source and provider graph."""

    _spec_index: int
    _consumer: VerifiedSourceSelection = field(repr=False, compare=False)
    _authority: SourceAuthorityAdapter = field(repr=False, compare=False)
    _runtime_ready: bool

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "CompiledAuraSource must be created by compile_generic_aura()"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("CompiledAuraSource subclasses are not supported")

    def __copy__(self) -> object:
        raise TypeError("CompiledAuraSource cannot be copied")

    def __deepcopy__(self, _memo: dict[int, object]) -> object:
        raise TypeError("CompiledAuraSource cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("CompiledAuraSource cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CompiledAuraSource cannot be pickled")

    @property
    @_artifact_public
    def record_id(self, state: _ArtifactState) -> str:
        return state.spec.record_id

    @property
    @_artifact_public
    def traits(self, state: _ArtifactState) -> tuple[str, ...]:
        return state.projection.traits

    @property
    @_artifact_public
    def action_cost(self, state: _ArtifactState) -> ActionCost:
        return state.projection.action_cost

    @property
    @_artifact_public
    def trigger(self, state: _ArtifactState) -> str:
        return state.projection.trigger

    @property
    @_artifact_public
    def effect_text(self, state: _ArtifactState) -> str:
        return state.projection.effect_text

    @property
    @_artifact_public
    def area(self, state: _ArtifactState) -> AuraArea:
        return state.area

    @property
    @_artifact_public
    def behavior(self, state: _ArtifactState) -> AuraBehavior:
        return state.behavior

    @property
    @_artifact_public
    def issues(self, state: _ArtifactState) -> tuple[AuraSourceIssue, ...]:
        return state.issues

    @property
    @_artifact_public
    def damage_only(self, state: _ArtifactState) -> AuraDamageOnly | None:
        return state.damage_only

    @property
    @_artifact_public
    def deferred_mechanics(
        self,
        state: _ArtifactState,
    ) -> tuple[DeferredAuraMechanic, ...]:
        return state.deferrals

    @property
    @_artifact_public
    def effect_route(self, state: _ArtifactState) -> AuraEffectRoute:
        return state.effect_route

    @property
    @_artifact_public
    def consumer(
        self,
        state: _ArtifactState,
        _getattribute: Any = object.__getattribute__,
    ) -> SourceReceipt:
        return _getattribute(state.consumer_rule, "receipt")

    @property
    @_artifact_public
    def verified_providers(
        self,
        state: _ArtifactState,
        _getattribute: Any = object.__getattribute__,
        _tuple_type: Any = tuple,
    ) -> tuple[SourceReceipt, ...]:
        return _tuple_type(
            _getattribute(provider, "receipt")
            for provider in state.providers
        )

    @property
    @_artifact_public
    def runtime_ready(self, _state: _ArtifactState) -> bool:
        return False

    @_artifact_public
    def as_serialized(
        self,
        state: _ArtifactState,
        _serialize_verified_rule: Any = _serialize_rule,
        _serialize_raw: Any = _raw_serialized,
        _serialize_area: Any = _serialize_area_value,
        _serialize_behavior: Any = _serialize_behavior_value,
        _serialize_issue: Any = _serialize_issue_value,
        _serialize_damage: Any = _serialize_damage_value,
        _serialize_route: Any = _serialize_route_value,
        _serialize_deferral: Any = _serialize_deferral_value,
        _family_id: str = FAMILY_ID,
        _source_id: str = MONSTER_CORE_SOURCE_ID,
        _strict_zip: Any = zip,
        _getattribute: Any = object.__getattribute__,
        _exact_type: Any = type,
        _member_type: type[RawSourceMember] = RawSourceMember,
    ) -> SerializedObject:
        consumer = _serialize_verified_rule(state.consumer_rule)
        provider_rows = []
        for provider_spec, provider in _strict_zip(
            state.provider_specs,
            state.providers,
            strict=True,
        ):
            provider_rows.append(
                {
                    "relation": provider_spec.relation,
                    "linkKind": provider_spec.link_kind,
                    **_serialize_verified_rule(provider),
                }
            )
        selected = _getattribute(
            _getattribute(state.consumer_rule, "selection"),
            "raw_member",
        )
        if _exact_type(selected) is not _member_type:
            raise AuraAddressabilityError("compiled Aura lost raw member")
        return {
            "schema": 1,
            "kind": "pf2er-generic-aura-compile-artifact",
            "supportState": "compile-only",
            "runtimeReady": False,
            "familyId": _family_id,
            "recordId": state.spec.record_id,
            "sourceOrder": {
                "blockSequence": state.spec.block_sequence,
                "abilityOrdinal": state.spec.ability_ordinal,
            },
            "consumer": consumer,
            "source": {
                "sourceId": _source_id,
                "locator": state.spec.locator,
                "creatureName": state.spec.creature_name,
            },
            "rawMember": {
                "key": selected.key,
                "value": _serialize_raw(selected.value),
            },
            "encoding": state.projection.encoding,
            "topLevelMemberKeys": [
                item for item in state.projection.top_level_member_keys
            ],
            "grammarCohort": state.spec.grammar_cohort,
            "traits": [item for item in state.projection.traits],
            "actionCost": state.projection.action_cost,
            "trigger": state.projection.trigger or None,
            "effectText": state.projection.effect_text,
            "auraDeclarationCount": (
                state.projection.aura_declaration_count
            ),
            "area": _serialize_area(state.area),
            "behavior": _serialize_behavior(state.behavior),
            "issues": [
                _serialize_issue(issue)
                for issue in state.issues
            ],
            "damageOnly": (
                None
                if state.damage_only is None
                else _serialize_damage(state.damage_only)
            ),
            "providers": provider_rows,
            "effectRoute": _serialize_route(state.effect_route),
            "deferredMechanics": [
                _serialize_deferral(deferral)
                for deferral in state.deferrals
            ],
        }


del _artifact_public


def _validate_artifact_structure(
    artifact: object,
    class_hook_guard: Any,
    review_graph_guard: Any,
    artifact_type: type[CompiledAuraSource],
    specs: tuple[_ReviewedAuraSpec, ...],
    fixed_providers: tuple[_ProviderSpec, ...],
    authority_type: type[SourceAuthorityAdapter],
    selection_type: type[VerifiedSourceSelection],
    requirement_type: type[RuleRequirement],
    validate_selection: Any,
    resolve_rule: Any,
    validate_rule: Any,
    require_shared_authority: Any,
    raw_projection: Any,
    same_selection: Any,
    projection_matches: Any,
    consumer_requirement: Any,
    provider_specs_for: Any,
    fixed_provider_requirement: Any,
    carrier_creature_name: Any,
    projection_type: type[_RawAuraProjection],
    copy_area: Any,
    copy_behavior: Any,
    copy_issues: Any,
    damage_for: Any,
    deferrals_for: Any,
    make_route: Any,
    make_state: Any,
    exact_type: Any = type,
    int_type: type[int] = int,
    bool_type: type[bool] = bool,
    raw_member_type: type[RawSourceMember] = RawSourceMember,
    tuple_type: Any = tuple,
    getattribute: Any = object.__getattribute__,
    length: Any = len,
) -> _ArtifactState:
    class_hook_guard()
    review_graph_guard()
    if exact_type(artifact) is not artifact_type:
        raise TypeError("compiled Aura artifact must be exact")
    try:
        spec_index = getattribute(artifact, "_spec_index")
        consumer = getattribute(artifact, "_consumer")
        authority = getattribute(artifact, "_authority")
        runtime_ready = getattribute(artifact, "_runtime_ready")
    except (AttributeError, TypeError) as failure:
        raise AuraAddressabilityError(
            "compiled Aura artifact state is incomplete"
        ) from failure
    if (
        exact_type(spec_index) is not int_type
        or spec_index < 0
        or spec_index >= length(specs)
        or exact_type(consumer) is not selection_type
        or exact_type(authority) is not authority_type
        or exact_type(runtime_ready) is not bool_type
        or runtime_ready
    ):
        raise AuraAddressabilityError(
            "compiled Aura artifact state is invalid"
        )
    spec = specs[spec_index]
    validate_selection(authority, consumer)
    expected_consumer = resolve_rule(
        authority,
        consumer_requirement(spec, requirement_type),
    )
    validate_rule(authority, expected_consumer)
    expected_selection = getattribute(
        expected_consumer,
        "selection",
    )
    if not same_selection(consumer, expected_selection):
        raise AuraAddressabilityError(
            "Aura consumer is not the reviewed exact selection"
        )
    carrier = getattribute(consumer, "carrier")
    if carrier_creature_name(carrier) != spec.creature_name:
        raise AuraAddressabilityError("Aura creature identity drifted")
    raw_member = getattribute(consumer, "raw_member")
    if (
        exact_type(raw_member) is not raw_member_type
        or raw_member.key != spec.raw_key
    ):
        raise AuraAddressabilityError("Aura raw member identity drifted")
    projection = raw_projection(raw_member)
    if exact_type(projection) is not projection_type:
        raise AuraCompileError("reviewed Aura no longer has Aura grammar")
    projection_matches(spec, projection)

    provider_specs = provider_specs_for(spec, specs, fixed_providers)
    providers = tuple_type(
        resolve_rule(
            authority,
            fixed_provider_requirement(
                provider_spec,
                requirement_type,
            ),
        )
        for provider_spec in provider_specs
    )
    for provider in providers:
        validate_rule(authority, provider)
    require_shared_authority(authority, consumer, providers)

    area = copy_area(spec.area)
    behavior = copy_behavior(spec.behavior)
    issues = copy_issues(spec.issues)
    damage_only = damage_for(spec, projection)
    deferrals = deferrals_for(spec, projection)
    provider_id = (
        None
        if spec.effect_provider is None
        else (
            spec.effect_provider.removeprefix("record:")
            if spec.effect_provider.startswith("record:")
            else provider_specs[-1].rule_id
        )
    )
    route = make_route(
        family_id=spec.route_family,
        provider_id=provider_id,
        link_kind=spec.effect_link_kind,
    )
    return make_state(
        spec=spec,
        projection=projection,
        consumer_rule=expected_consumer,
        provider_specs=provider_specs,
        providers=providers,
        area=area,
        behavior=behavior,
        issues=issues,
        damage_only=damage_only,
        deferrals=deferrals,
        effect_route=route,
    )


def _artifact_validator_contract(
    structural_validator: Any,
    *dependencies: object,
) -> Any:
    def validate(artifact: object) -> _ArtifactState:
        return structural_validator(
            artifact,
            *dependencies,
        )

    return validate


_validate_artifact = _artifact_validator_contract(
    _validate_artifact_structure,
    _require_exact_class_hooks,
    _require_exact_review_graph,
    CompiledAuraSource,
    _REVIEWED_SPECS,
    _FIXED_PROVIDER_SPECS,
    SourceAuthorityAdapter,
    VerifiedSourceSelection,
    RuleRequirement,
    SourceAuthorityAdapter.validate_selection,
    SourceAuthorityAdapter.resolve_rule,
    SourceAuthorityAdapter.validate_rule,
    SourceAuthorityAdapter.require_shared_authority,
    _raw_projection,
    _same_selection,
    _projection_matches,
    _consumer_requirement,
    _provider_specs_for,
    _fixed_provider_requirement,
    _carrier_creature_name,
    _RawAuraProjection,
    _copy_area,
    _copy_behavior,
    _copy_issues,
    _damage_for,
    _deferrals_for,
    _new_route,
    _new_artifact_state,
)
_bind_artifact_validator(_validate_artifact)
del _bind_artifact_validator
del _artifact_validator_contract


def _new_artifact(
    *,
    spec_index: int,
    consumer: VerifiedSourceSelection,
    authority: SourceAuthorityAdapter,
    _new: Any = object.__new__,
    _setattr: Any = object.__setattr__,
    _artifact_type: type[CompiledAuraSource] = CompiledAuraSource,
) -> CompiledAuraSource:
    artifact = _new(_artifact_type)
    _setattr(artifact, "_spec_index", spec_index)
    _setattr(artifact, "_consumer", consumer)
    _setattr(artifact, "_authority", authority)
    _setattr(artifact, "_runtime_ready", False)
    return artifact


def _spec_index(
    consumer: VerifiedSourceSelection,
    specs: tuple[_ReviewedAuraSpec, ...],
    _address_type: type[SourceAddress] = SourceAddress,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _member_step_type: type[RawMemberStep] = RawMemberStep,
    _current_binding: Any = _current_consumer_binding,
    _getattribute: Any = object.__getattribute__,
    _exact_type: Any = type,
    _tuple_type: Any = tuple,
    _enumerate: Any = enumerate,
    _length: Any = len,
) -> int | None:
    address = _getattribute(consumer, "address")
    raw_member = _getattribute(consumer, "raw_member")
    if (
        _exact_type(address) is not _address_type
        or _exact_type(raw_member) is not _member_type
    ):
        return None
    selection_hash = _getattribute(
        consumer,
        "selection_sha256",
    )
    candidates = _tuple_type(
        index
        for index, spec in _enumerate(specs)
        if (
            spec.locator == address.locator
            and spec.raw_key == raw_member.key
            and spec.expected_selection_sha256 == selection_hash
        )
    )
    if _length(candidates) > 1:
        exact = _tuple_type(
            index
            for index in candidates
            if (
                address.carrier_path
                == _current_binding(specs[index])[0]
                and address.selection_path
                == (
                    _member_step_type(
                        specs[index].raw_key,
                        _current_binding(specs[index])[1],
                    ),
                )
            )
        )
        if _length(exact) == 1:
            return exact[0]
    return candidates[0] if _length(candidates) == 1 else None


def _compile_generic_aura_structure(
    consumer: object,
    authority: object,
    authority_type: type[SourceAuthorityAdapter],
    selection_type: type[VerifiedSourceSelection],
    specs: tuple[_ReviewedAuraSpec, ...],
    validate_selection: Any,
    raw_projection: Any,
    find_spec_index: Any,
    new_artifact: Any,
    validate_artifact: Any,
    artifact_type: type[CompiledAuraSource],
    raw_member_type: type[RawSourceMember],
    raw_object_type: type[RawSourceObject],
    exact_type: Any,
    getattribute: Any,
    reject_any: Any,
    class_hook_guard: Any,
    review_graph_guard: Any,
) -> CompiledAuraSource | None:
    class_hook_guard()
    review_graph_guard()
    if exact_type(authority) is not authority_type:
        raise TypeError(
            "Aura authority must be an exact SourceAuthorityAdapter"
        )
    if exact_type(consumer) is not selection_type:
        raise TypeError(
            "Aura consumer must be an exact VerifiedSourceSelection"
        )
    validate_selection(authority, consumer)
    raw_member = getattribute(consumer, "raw_member")
    if exact_type(raw_member) is not raw_member_type:
        selected = getattribute(consumer, "selected_value")
        if (
            exact_type(selected) is raw_object_type
            and selected.values("Name") == (
            "Aura",
            )
        ):
            raise AuraAddressabilityError(
                "ability-glossary Aura is a provider, not a creature consumer"
            )
        return None
    projection = raw_projection(raw_member)
    if projection is None:
        return None
    index = find_spec_index(consumer, specs)
    if index is None:
        raise AuraAddressabilityError(
            "Aura-shaped source is outside the reviewed exact corpus"
        )
    spec = specs[index]
    if reject_any(
        issue.severity == "compile-reject" for issue in spec.issues
    ):
        raise AuraCompileError(
            f"reviewed Aura source requires repair before compilation: "
            f"{spec.record_id}"
        )
    artifact = new_artifact(
        spec_index=index,
        consumer=consumer,
        authority=authority,
    )
    if exact_type(artifact) is not artifact_type:
        raise TypeError("Aura compiler returned a foreign artifact")
    validate_artifact(artifact)
    return artifact


def _compiler_contract(
    structural_compiler: Any,
    result_exact_type: Any,
    result_type: type[CompiledAuraSource],
    *dependencies: object,
) -> Any:
    def compile(
        consumer: object,
        authority: object,
        /,
    ) -> CompiledAuraSource | None:
        result = structural_compiler(
            consumer,
            authority,
            *dependencies,
        )
        if (
            result is not None
            and result_exact_type(result) is not result_type
        ):
            raise TypeError("Aura compiler returned a foreign result")
        return result

    return compile


compile_generic_aura = _compiler_contract(
    _compile_generic_aura_structure,
    type,
    CompiledAuraSource,
    SourceAuthorityAdapter,
    VerifiedSourceSelection,
    _REVIEWED_SPECS,
    SourceAuthorityAdapter.validate_selection,
    _raw_projection,
    _spec_index,
    _new_artifact,
    _validate_artifact,
    CompiledAuraSource,
    RawSourceMember,
    RawSourceObject,
    type,
    object.__getattribute__,
    any,
    _require_exact_class_hooks,
    _require_exact_review_graph,
)
compile_generic_aura.__name__ = "compile_generic_aura"
compile_generic_aura.__qualname__ = "compile_generic_aura"
compile_generic_aura.__doc__ = (
    "Compile one exact, authority-bound reviewed Core MC1 Aura production."
)
del _compiler_contract


def _corpus_compiler_contract(
    compiler: Any,
    artifact_type: type[CompiledAuraSource],
    validate_artifact: Any,
    max_records: int,
    exact_type: Any = type,
    tuple_type: Any = tuple,
    list_type: Any = list,
    set_type: Any = set,
    length: Any = len,
    sort: Any = sorted,
    getattribute: Any = object.__getattribute__,
) -> Any:
    def compile_corpus(
        consumers: tuple[VerifiedSourceSelection, ...],
        authority: SourceAuthorityAdapter,
        /,
    ) -> tuple[CompiledAuraSource, ...]:
        if exact_type(consumers) is not tuple_type:
            raise TypeError("Aura corpus consumers must be an exact tuple")
        if length(consumers) > max_records:
            raise AuraCompileError("Aura corpus exceeds its reviewed bound")
        result: list[CompiledAuraSource] = list_type()
        seen: set[str] = set_type()
        for consumer in consumers:
            artifact = compiler(consumer, authority)
            if artifact is None:
                continue
            if exact_type(artifact) is not artifact_type:
                raise TypeError("Aura corpus compiler returned foreign result")
            state = validate_artifact(artifact)
            record_id = state.spec.record_id
            if record_id in seen:
                raise AuraAddressabilityError(
                    f"duplicate Aura consumer: {record_id}"
                )
            seen.add(record_id)
            result.append(artifact)
        return tuple_type(
            sort(
                result,
                key=lambda artifact: (
                    getattribute(artifact, "_spec_index")
                ),
            )
        )

    return compile_corpus


compile_generic_aura_corpus = _corpus_compiler_contract(
    compile_generic_aura,
    CompiledAuraSource,
    _validate_artifact,
    REVIEWED_AURA_RECORD_COUNT,
)
compile_generic_aura_corpus.__name__ = "compile_generic_aura_corpus"
compile_generic_aura_corpus.__qualname__ = "compile_generic_aura_corpus"
compile_generic_aura_corpus.__doc__ = (
    "Compile a bounded ordered tuple of authority-bound Aura selections."
)
del _corpus_compiler_contract


# The compiler and validator retain the immutable review graph by closure.
# Removing module-level handles makes global poisoning irrelevant to trust.
del _CURRENT_CONSUMER_REBINDS
del _FIXED_PROVIDER_SPECS
del _REVIEWED_SPECS


__all__ = [
    "AURA_RULE",
    "FRIGHTFUL_PRESENCE_RULE",
    "FAMILY_ID",
    "MONSTER_CORE_SOURCE_ID",
    "NYMPHS_BEAUTY_RULE",
    "REVIEWED_AURA_CREATURE_COUNT",
    "REVIEWED_AURA_DECLARATION_COUNT",
    "REVIEWED_AURA_GRAPH_SHA256",
    "REVIEWED_AURA_IDENTITY_SHA256",
    "REVIEWED_AURA_LINK_SHA256",
    "REVIEWED_AURA_NEAR_MISS_COUNT",
    "REVIEWED_AURA_NEAR_MISS_SHA256",
    "REVIEWED_AURA_RECORD_COUNT",
    "REVIEWED_AURA_SEMANTIC_SHA256",
    "STENCH_RULE",
    "AuraAddressabilityError",
    "AuraArea",
    "AuraBehavior",
    "AuraCompileError",
    "AuraDamageOnly",
    "AuraEffectRoute",
    "AuraLinkError",
    "AuraRuleTarget",
    "AuraSourceIssue",
    "AuraTemporaryImmunity",
    "CompiledAuraSource",
    "DeferredAuraMechanic",
    "compile_generic_aura",
    "compile_generic_aura_corpus",
    "has_primary_aura_trait",
]

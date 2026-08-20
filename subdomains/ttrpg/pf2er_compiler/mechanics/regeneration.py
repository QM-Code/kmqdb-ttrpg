"""Compile every reviewed Monster Core regeneration HP carrier.

This family is deliberately compile-only.  It accepts only a source selection
that has been authenticated against the private local-cache authority, reloads
that selection before reading it, and resolves the Monster Core Regeneration
glossary from a hash-pinned provider requirement.  Consumer HP evidence,
creature-local linked abilities, and provider-rule evidence remain separate.

Regeneration needs state and transition ordering that the encounter runtime
does not yet own: start/end-turn scheduling, suppression generations, damage
trigger ordering (including persistent damage), dying and zero-HP resolution,
and the Hydra and Phoenix special cases.  The compiler therefore emits exact,
typed metadata and typed deferrals without claiming runtime readiness or
registering a handler.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal, TypeAlias

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    SerializedObject,
)
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    SourceReviewError,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
)
from .source_values import MAX_SOURCE_INTEGER, parse_decimal_integer


FAMILY_ID = "regeneration"
COMPILER_ID = "monster-core-regeneration"
MECHANIC_TYPE = "regeneration"
MONSTER_CORE_SOURCE_ID = "core-mc1"
REGISTRY_STATUS = "compile-only"
MAX_REGENERATION_SOURCE_BYTES = 65_536
MAX_CREATURE_NAME_BYTES = 1_024
MAX_HIT_POINT_POOLS = 2
MAX_SUPPRESSION_SELECTORS = 4
MAX_LOCAL_SOURCES = 2
MAX_DEFERRED_REQUIREMENTS = 32

REGENERATION_RULE_REQUIREMENT = RuleRequirement(
    rule_id="monster-core-regeneration",
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
    carrier_path=(RawMemberStep("^.ability", 28),),
    expected_block_sha256=(
        "20ba13a29036e4672568c150314b49ff6347603dc31265d639b123ffffb0b153"
    ),
)

SelectorKind: TypeAlias = Literal["damage-type", "material", "trait"]
FormulaKind: TypeAlias = Literal["fixed", "per-active-head"]
SourceShape: TypeAlias = Literal[
    "fixed-page-reference",
    "fixed-unpaged",
    "hydra-linked",
    "phoenix-linked",
]
SuppressionMode: TypeAlias = Literal[
    "listed-damage",
    "all-heads-severed-and-stumps-cauterized",
]
ReactivationTiming: TypeAlias = Literal[
    "end-owner-next-turn",
    "terminal-no-reactivation",
]
SuppressionGeneration: TypeAlias = Literal[
    "refresh-on-each-triggering-damage-event",
    "stable-head-and-stump-generations",
]
SuppressionApplication: TypeAlias = Literal[
    "before-triggering-damage-hit-point-commit",
    "after-head-and-stump-state-transition",
]
PersistentDamagePolicy: TypeAlias = Literal[
    "each-damage-instance-can-trigger-listed-deactivation",
    "requires-exact-stump-targeting-and-remains-deferred",
]
DeferredKind: TypeAlias = Literal[
    "turn-start-recovery",
    "end-next-turn-reactivation",
    "suppression-trigger-ordering",
    "suppression-generation-state",
    "persistent-damage-triggering",
    "dying-cap",
    "zero-hit-point-resolution",
    "healing-hit-point-commit",
    "material-selector-matching",
    "trait-selector-matching",
    "multiple-hit-point-pools",
    "head-targeting",
    "head-damage-reset",
    "stump-cauterization",
    "dynamic-regeneration-amount",
    "post-regeneration-save",
    "head-regrowth",
    "head-count-reactions",
    "terminal-head-state-death",
    "self-resurrection-delay",
    "self-resurrection-remains",
    "self-resurrection-area-lock",
    "self-resurrection-frequency",
    "self-resurrection-ritual",
]

_SELECTOR_KINDS = frozenset({"damage-type", "material", "trait"})
_FORMULA_KINDS = frozenset({"fixed", "per-active-head"})
_SOURCE_SHAPES = frozenset(
    {
        "fixed-page-reference",
        "fixed-unpaged",
        "hydra-linked",
        "phoenix-linked",
    }
)
_SUPPRESSION_MODES = frozenset(
    {
        "listed-damage",
        "all-heads-severed-and-stumps-cauterized",
    }
)
_REACTIVATION_TIMINGS = frozenset(
    {"end-owner-next-turn", "terminal-no-reactivation"}
)
_SUPPRESSION_GENERATIONS = frozenset(
    {
        "refresh-on-each-triggering-damage-event",
        "stable-head-and-stump-generations",
    }
)
_SUPPRESSION_APPLICATIONS = frozenset(
    {
        "before-triggering-damage-hit-point-commit",
        "after-head-and-stump-state-transition",
    }
)
_PERSISTENT_DAMAGE_POLICIES = frozenset(
    {
        "each-damage-instance-can-trigger-listed-deactivation",
        "requires-exact-stump-targeting-and-remains-deferred",
    }
)
_DEFERRED_KINDS = frozenset(
    {
        "turn-start-recovery",
        "end-next-turn-reactivation",
        "suppression-trigger-ordering",
        "suppression-generation-state",
        "persistent-damage-triggering",
        "dying-cap",
        "zero-hit-point-resolution",
        "healing-hit-point-commit",
        "material-selector-matching",
        "trait-selector-matching",
        "multiple-hit-point-pools",
        "head-targeting",
        "head-damage-reset",
        "stump-cauterization",
        "dynamic-regeneration-amount",
        "post-regeneration-save",
        "head-regrowth",
        "head-count-reactions",
        "terminal-head-state-death",
        "self-resurrection-delay",
        "self-resurrection-remains",
        "self-resurrection-area-lock",
        "self-resurrection-frequency",
        "self-resurrection-ritual",
    }
)

CANONICAL_DAMAGE_TYPES = frozenset(
    {
        "acid",
        "bludgeoning",
        "cold",
        "electricity",
        "fire",
        "force",
        "mental",
        "physical",
        "piercing",
        "poison",
        "slashing",
        "sonic",
        "spirit",
        "vitality",
        "void",
    }
)
REVIEWED_NON_DAMAGE_SELECTORS = {
    "cold iron": "material",
    "holy": "trait",
    "unholy": "trait",
}
REVIEWED_UNPAGED_FIXED_FORMS = {
    (
        "Pleroma",
        335,
        20,
        (("damage-type", "spirit"),),
    ),
    (
        "Nessari",
        335,
        30,
        (("trait", "holy"),),
    ),
}

_FIXED_HP_RE = re.compile(
    r"^(?P<hit_points>[1-9][0-9]*), regeneration "
    r"(?P<amount>[1-9][0-9]*) "
    r"\(deactivated by "
    r"(?P<selectors>[a-z]+(?: [a-z]+)*(?: or [a-z]+(?: [a-z]+)*)*)"
    r"(?P<page>; page [1-9][0-9]*)?\)"
    r"(?P<self_resurrection>, self-resurrection)?$",
    re.ASCII,
)
_HYDRA_HP_RE = re.compile(
    r"^body (?P<body>[1-9][0-9]*), hydra regeneration; "
    r"head (?P<head>[1-9][0-9]*), head regrowth$",
    re.ASCII,
)
_HYDRA_REGENERATION_RE = re.compile(
    r"^The hydra has regeneration \(page 360\) equal to "
    r"(?P<coefficient>[1-9][0-9]*) × the number of heads it has\. "
    r"If a hydra’s body is missing any heads and the remaining stumps "
    r"have not been cauterized, the hydra attempts a DC "
    r"(?P<dc>[1-9][0-9]*) Fortitude save after it regains Hit Points "
    r"from regeneration\. On a success, one uncauterized stump regrows "
    r"two heads; on a critical success, two uncauterized stumps regrow "
    r"into two heads each\. The hydra can never grow more than double "
    r"the number of heads it ordinarily has\. The hydra’s regeneration "
    r"only fully deactivates if all its heads are severed and all stumps "
    r"are cauterized, at which point it dies\.$",
    re.ASCII,
)
_HEAD_REGROWTH_RE = re.compile(
    r"^A hydra ordinarily has (?P<ordinary>five) heads\. "
    r"A creature can attempt to sever one of the hydra’s heads by "
    r"specifically targeting it and dealing damage equal to the head’s "
    r"Hit Points\. A head that is not completely severed returns to full "
    r"Hit Points at the end of any creature’s turn\. "
    r"A hydra can regrow a severed head using hydra regeneration\. "
    r"A creature can prevent this regrowth by dealing "
    r"(?P<selectors>[a-z]+(?: or [a-z]+)*) damage to the stump, "
    r"cauterizing it\. Single-target acid or fire effects need to be "
    r"targeted at a specific stump, but effects that deal splash damage "
    r"or affect areas covering the hydra’s whole space cauterize all "
    r"stumps if they deal acid or fire damage\. If the attack that "
    r"severs a head deals any acid or fire damage, the stump is "
    r"cauterized instantly\. If all five heads are cauterized, the "
    r"hydra dies\.$",
    re.ASCII,
)
_SELF_RESURRECTION_RE = re.compile(
    r"^When a phoenix dies, they collapse into a pile of smoldering "
    r"ashes before returning to life fully healed "
    r"(?P<count>[1-9][0-9]*)d(?P<sides>[1-9][0-9]*) rounds later, "
    r"as if subject to a (?P<rank>[1-9][0-9]*)th-rank "
    r"<i>resurrect</i> ritual\. Self-resurrection happens only if there "
    r"are some remains to resurrect; for instance, a phoenix killed by "
    r"a <i>disintegrate</i> spell can't use this ability\. A phoenix "
    r"whose remains rest within an area devoted to an unholy deity by "
    r"<i>consecrate</i> can't self-resurrect until their remains are no "
    r"longer in that area\. A phoenix can self-resurrect only once per "
    r"year\.$",
    re.ASCII,
)


def _require_trimmed(
    value: object,
    label: str,
    *,
    maximum_bytes: int = MAX_REGENERATION_SOURCE_BYTES,
) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > maximum_bytes
    ):
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    return value


def _require_positive(value: object, label: str) -> int:
    if (
        type(value) is not int
        or value <= 0
        or value > MAX_SOURCE_INTEGER
    ):
        raise ValueError(
            f"{label} must be a positive signed 64-bit integer"
        )
    return value


def _positive_source_integer(
    value: str,
    _maximum=MAX_SOURCE_INTEGER,
    _parse=parse_decimal_integer,
) -> int | None:
    if len(value) > 19:
        return None
    result = _parse(value)
    if result is None or result <= 0 or result > _maximum:
        return None
    return result


def _bounded_source_text(
    value: object,
    _maximum_bytes=MAX_REGENERATION_SOURCE_BYTES,
) -> str | None:
    if type(value) is not str:
        return None
    if len(value.encode("utf-8")) > _maximum_bytes:
        return None
    return value


def _normalized(
    value: object,
    _bounded=_bounded_source_text,
) -> str | None:
    text = _bounded(value)
    if text is None:
        return None
    return " ".join(text.split())


@dataclass(frozen=True, slots=True)
class HitPointPool:
    pool_id: str
    maximum: int
    initial_count: int

    def __post_init__(
        self,
        _trimmed=_require_trimmed,
        _positive=_require_positive,
    ) -> None:
        _trimmed(self.pool_id, "HitPointPool.pool_id")
        _positive(self.maximum, "HitPointPool.maximum")
        _positive(self.initial_count, "HitPointPool.initial_count")

    def as_serialized(self) -> SerializedObject:
        return {
            "id": self.pool_id,
            "maximum": self.maximum,
            "initialCount": self.initial_count,
        }


@dataclass(frozen=True, slots=True)
class SuppressionSelector:
    kind: SelectorKind
    value: str

    def __post_init__(
        self,
        _kinds=_SELECTOR_KINDS,
        _trimmed=_require_trimmed,
    ) -> None:
        if type(self.kind) is not str or self.kind not in _kinds:
            raise ValueError("SuppressionSelector.kind is invalid")
        _trimmed(self.value, "SuppressionSelector.value")

    def as_serialized(self) -> SerializedObject:
        return {"kind": self.kind, "value": self.value}


@dataclass(frozen=True, slots=True)
class RecoveryFormula:
    kind: FormulaKind
    fixed_amount: int | None = None
    amount_per_active_head: int | None = None

    def __post_init__(
        self,
        _kinds=_FORMULA_KINDS,
        _positive=_require_positive,
    ) -> None:
        if type(self.kind) is not str or self.kind not in _kinds:
            raise ValueError("RecoveryFormula.kind is invalid")
        if self.kind == "fixed":
            _positive(
                self.fixed_amount,
                "RecoveryFormula.fixed_amount",
            )
            if self.amount_per_active_head is not None:
                raise ValueError(
                    "fixed recovery cannot have an active-head coefficient"
                )
        else:
            _positive(
                self.amount_per_active_head,
                "RecoveryFormula.amount_per_active_head",
            )
            if self.fixed_amount is not None:
                raise ValueError(
                    "active-head recovery cannot have a fixed amount"
                )

    def as_serialized(self) -> SerializedObject:
        if self.kind == "fixed":
            return {"kind": self.kind, "amount": self.fixed_amount}
        return {
            "kind": self.kind,
            "amountPerActiveHead": self.amount_per_active_head,
        }


@dataclass(frozen=True, slots=True)
class HydraMetadata:
    ordinary_heads: int
    maximum_heads: int
    regrowth_save_dc: int
    success_stumps: int
    critical_success_stumps: int
    heads_per_regrown_stump: int
    cauterization_selectors: tuple[SuppressionSelector, ...]

    def __post_init__(
        self,
        _positive=_require_positive,
        _selector_type=SuppressionSelector,
    ) -> None:
        for field_name in (
            "ordinary_heads",
            "maximum_heads",
            "regrowth_save_dc",
            "success_stumps",
            "critical_success_stumps",
            "heads_per_regrown_stump",
        ):
            _positive(
                getattr(self, field_name),
                f"HydraMetadata.{field_name}",
            )
        if self.maximum_heads != self.ordinary_heads * 2:
            raise ValueError("HydraMetadata maximum must be double ordinary")
        if (
            type(self.cauterization_selectors) is not tuple
            or not self.cauterization_selectors
            or any(
                type(item) is not _selector_type
                for item in self.cauterization_selectors
            )
            or any(
                item.kind != "damage-type"
                for item in self.cauterization_selectors
            )
            or len(
                {item.value for item in self.cauterization_selectors}
            )
            != len(self.cauterization_selectors)
        ):
            raise ValueError(
                "HydraMetadata.cauterization_selectors are invalid"
            )
        if (
            self.ordinary_heads,
            self.maximum_heads,
            self.regrowth_save_dc,
            self.success_stumps,
            self.critical_success_stumps,
            self.heads_per_regrown_stump,
            tuple(
                (item.kind, item.value)
                for item in self.cauterization_selectors
            ),
        ) != (
            5,
            10,
            25,
            1,
            2,
            2,
            (("damage-type", "acid"), ("damage-type", "fire")),
        ):
            raise ValueError(
                "HydraMetadata must retain the exact reviewed source shape"
            )

    def as_serialized(self) -> SerializedObject:
        return {
            "ordinaryHeads": self.ordinary_heads,
            "maximumHeads": self.maximum_heads,
            "headDamage": {
                "severAtMaximum": True,
                "partialDamageReset": "end-any-creature-turn",
            },
            "regrowthSave": {
                "timing": "after-regeneration-recovery",
                "save": "fortitude",
                "dc": self.regrowth_save_dc,
                "successStumps": self.success_stumps,
                "criticalSuccessStumps": self.critical_success_stumps,
                "headsPerStump": self.heads_per_regrown_stump,
            },
            "cauterization": {
                "selectors": [
                    item.as_serialized()
                    for item in self.cauterization_selectors
                ],
                "singleTargetScope": "specific-stump",
                "wholeSpaceSplashOrAreaScope": "all-stumps",
                "severingAttackTiming": "instant",
            },
            "terminalConditions": {
                "headRegrowthClause": "five-head-stumps-cauterized",
                "regenerationClause": (
                    "all-heads-severed-and-all-stumps-cauterized"
                ),
                "outcome": "owner-dies",
            },
        }


@dataclass(frozen=True, slots=True)
class SelfResurrectionMetadata:
    delay_die_count: int
    delay_die_sides: int
    ritual_rank: int

    def __post_init__(
        self,
        _positive=_require_positive,
    ) -> None:
        _positive(
            self.delay_die_count,
            "SelfResurrectionMetadata.delay_die_count",
        )
        _positive(
            self.delay_die_sides,
            "SelfResurrectionMetadata.delay_die_sides",
        )
        _positive(
            self.ritual_rank,
            "SelfResurrectionMetadata.ritual_rank",
        )
        if (
            self.delay_die_count,
            self.delay_die_sides,
            self.ritual_rank,
        ) != (1, 4, 7):
            raise ValueError(
                "SelfResurrectionMetadata must retain the reviewed shape"
            )

    def as_serialized(self) -> SerializedObject:
        return {
            "trigger": "owner-dies",
            "returnHitPoints": "fully-healed",
            "delay": {
                "dice": {
                    "count": self.delay_die_count,
                    "sides": self.delay_die_sides,
                },
                "unit": "round",
            },
            "ritual": {"name": "resurrect", "rank": self.ritual_rank},
            "requiresRemains": True,
            "blockedWhileRemainsIn": "unholy-consecrated-area",
            "frequency": {"count": 1, "unit": "year"},
        }


@dataclass(frozen=True, slots=True)
class DeferredRequirement:
    kind: DeferredKind
    evidence: str

    def __post_init__(
        self,
        _kinds=_DEFERRED_KINDS,
        _trimmed=_require_trimmed,
    ) -> None:
        if type(self.kind) is not str or self.kind not in _kinds:
            raise ValueError("DeferredRequirement.kind is invalid")
        _trimmed(self.evidence, "DeferredRequirement.evidence")

    def as_serialized(self) -> SerializedObject:
        return {"kind": self.kind, "evidence": self.evidence}


@dataclass(frozen=True, slots=True)
class VerifiedLocalSource:
    role: str
    selection: VerifiedSourceSelection

    def __post_init__(
        self,
        _trimmed=_require_trimmed,
        _selection_type=VerifiedSourceSelection,
    ) -> None:
        _trimmed(self.role, "VerifiedLocalSource.role")
        if type(self.selection) is not _selection_type:
            raise TypeError(
                "VerifiedLocalSource.selection must be an exact "
                "VerifiedSourceSelection"
            )

    def as_serialized(self) -> SerializedObject:
        return {
            "role": self.role,
            "source": self.selection.receipt.as_serialized(),
        }


@dataclass(frozen=True, slots=True)
class RegenerationPatch:
    creature_name: str
    source_text: str
    source_shape: SourceShape
    hit_point_pools: tuple[HitPointPool, ...]
    formula: RecoveryFormula
    suppression_mode: SuppressionMode
    suppression_generation: SuppressionGeneration
    suppression_application: SuppressionApplication
    persistent_damage_policy: PersistentDamagePolicy
    deactivation_selectors: tuple[SuppressionSelector, ...]
    reactivation_timing: ReactivationTiming
    reference_page: int | None
    hydra: HydraMetadata | None
    self_resurrection: SelfResurrectionMetadata | None
    consumer_source: VerifiedSourceSelection
    local_sources: tuple[VerifiedLocalSource, ...]
    provider_rule: VerifiedRuleReceipt
    deferred_requirements: tuple[DeferredRequirement, ...]

    def __post_init__(
        self,
        _trimmed=_require_trimmed,
        _bounded_text=_bounded_source_text,
        _creature_name_bytes=MAX_CREATURE_NAME_BYTES,
        _pool_type=HitPointPool,
        _selector_type=SuppressionSelector,
        _local_type=VerifiedLocalSource,
        _deferred_type=DeferredRequirement,
        _max_pools=MAX_HIT_POINT_POOLS,
        _max_deferrals=MAX_DEFERRED_REQUIREMENTS,
        _max_selectors=MAX_SUPPRESSION_SELECTORS,
        _max_locals=MAX_LOCAL_SOURCES,
        _formula_type=RecoveryFormula,
        _suppression_modes=_SUPPRESSION_MODES,
        _suppression_generations=_SUPPRESSION_GENERATIONS,
        _suppression_applications=_SUPPRESSION_APPLICATIONS,
        _persistent_policies=_PERSISTENT_DAMAGE_POLICIES,
        _reactivation_timings=_REACTIVATION_TIMINGS,
        _positive=_require_positive,
        _hydra_type=HydraMetadata,
        _resurrection_type=SelfResurrectionMetadata,
        _selection_type=VerifiedSourceSelection,
        _rule_type=VerifiedRuleReceipt,
        _receipt_type=SourceReceipt,
        _requirement_type=RuleRequirement,
        _member_step_type=RawMemberStep,
        _raw_member_type=RawSourceMember,
        _requirement=REGENERATION_RULE_REQUIREMENT,
        _monster_source_id=MONSTER_CORE_SOURCE_ID,
        _source_shapes=_SOURCE_SHAPES,
        _selection_receipt=VerifiedSourceSelection.receipt.fget,
        _selection_block_sha=VerifiedSourceSelection.block_sha256.fget,
        _rule_serialize=VerifiedRuleReceipt.as_serialized,
        _requirement_serialize=RuleRequirement.as_serialized,
        _adapter_type=SourceAuthorityAdapter,
        _validate_selection=SourceAuthorityAdapter.validate_selection,
        _validate_rule=SourceAuthorityAdapter.validate_rule,
        _require_shared=SourceAuthorityAdapter.require_shared_authority,
    ) -> None:
        _trimmed(
            self.creature_name,
            "RegenerationPatch.creature_name",
            maximum_bytes=_creature_name_bytes,
        )
        if _bounded_text(self.source_text) is None:
            raise ValueError(
                "RegenerationPatch.source_text exceeds its exact byte bound"
            )
        if (
            type(self.source_shape) is not str
            or self.source_shape not in _source_shapes
        ):
            raise ValueError("RegenerationPatch.source_shape is invalid")
        for field_name, expected_type in (
            ("hit_point_pools", _pool_type),
            ("deactivation_selectors", _selector_type),
            ("local_sources", _local_type),
            ("deferred_requirements", _deferred_type),
        ):
            value = getattr(self, field_name)
            if type(value) is not tuple or any(
                type(item) is not expected_type for item in value
            ):
                raise TypeError(
                    f"RegenerationPatch.{field_name} has invalid values"
                )
        if (
            not self.hit_point_pools
            or len(self.hit_point_pools) > _max_pools
            or not self.deferred_requirements
            or len(self.deferred_requirements) > _max_deferrals
            or len(self.deactivation_selectors)
            > _max_selectors
            or len(self.local_sources) > _max_locals
        ):
            raise ValueError(
                "RegenerationPatch collection bounds are invalid"
            )
        if len({item.pool_id for item in self.hit_point_pools}) != len(
            self.hit_point_pools
        ):
            raise ValueError("RegenerationPatch HP pool ids are duplicated")
        if len(
            {
                (item.kind, item.value)
                for item in self.deactivation_selectors
            }
        ) != len(self.deactivation_selectors):
            raise ValueError(
                "RegenerationPatch suppression selectors are duplicated"
            )
        if len({item.role for item in self.local_sources}) != len(
            self.local_sources
        ):
            raise ValueError("RegenerationPatch local source roles duplicate")
        if len(
            {item.kind for item in self.deferred_requirements}
        ) != len(self.deferred_requirements):
            raise ValueError(
                "RegenerationPatch deferred requirements are duplicated"
            )
        for item in self.hit_point_pools:
            item.__post_init__()
        for item in self.deactivation_selectors:
            item.__post_init__()
        for item in self.local_sources:
            item.__post_init__()
        for item in self.deferred_requirements:
            item.__post_init__()
        if type(self.formula) is not _formula_type:
            raise TypeError("RegenerationPatch.formula is invalid")
        self.formula.__post_init__()
        if (
            type(self.suppression_mode) is not str
            or self.suppression_mode not in _suppression_modes
        ):
            raise ValueError("RegenerationPatch.suppression_mode is invalid")
        if (
            type(self.suppression_generation) is not str
            or self.suppression_generation not in _suppression_generations
        ):
            raise ValueError(
                "RegenerationPatch.suppression_generation is invalid"
            )
        if (
            type(self.suppression_application) is not str
            or self.suppression_application not in _suppression_applications
        ):
            raise ValueError(
                "RegenerationPatch.suppression_application is invalid"
            )
        if (
            type(self.persistent_damage_policy) is not str
            or self.persistent_damage_policy
            not in _persistent_policies
        ):
            raise ValueError(
                "RegenerationPatch.persistent_damage_policy is invalid"
            )
        if (
            type(self.reactivation_timing) is not str
            or self.reactivation_timing not in _reactivation_timings
        ):
            raise ValueError(
                "RegenerationPatch.reactivation_timing is invalid"
            )
        if self.reference_page is not None:
            _positive(
                self.reference_page,
                "RegenerationPatch.reference_page",
            )
        if self.hydra is not None and type(self.hydra) is not _hydra_type:
            raise TypeError("RegenerationPatch.hydra is invalid")
        if self.hydra is not None:
            self.hydra.__post_init__()
        if (
            self.self_resurrection is not None
            and type(self.self_resurrection) is not _resurrection_type
        ):
            raise TypeError("RegenerationPatch.self_resurrection is invalid")
        if self.self_resurrection is not None:
            self.self_resurrection.__post_init__()
        if type(self.consumer_source) is not _selection_type:
            raise TypeError(
                "RegenerationPatch.consumer_source must be verified"
            )
        if type(self.provider_rule) is not _rule_type:
            raise TypeError(
                "RegenerationPatch.provider_rule must be verified"
            )
        consumer_receipt = _selection_receipt(self.consumer_source)
        consumer_address = self.consumer_source.address
        if (
            type(consumer_receipt) is not _receipt_type
            or consumer_address.source_id != _monster_source_id
            or consumer_address.span is not None
            or len(consumer_address.selection_path) != 1
            or type(consumer_address.selection_path[0])
            is not _member_step_type
            or consumer_address.selection_path[0].raw_key != "HP"
            or type(self.consumer_source.raw_member) is not _raw_member_type
            or self.consumer_source.raw_member.key != "HP"
            or self.consumer_source.raw_value != self.source_text
            or self.consumer_source.selected_value != self.source_text
        ):
            raise ValueError(
                "RegenerationPatch consumer is not the exact HP source"
            )
        names = tuple(
            member.value
            for member in self.consumer_source.carrier.raw_block.members
            if type(member) is _raw_member_type and member.key == "Name"
        )
        if names != (self.creature_name,):
            raise ValueError(
                "RegenerationPatch creature name disagrees with its source"
            )

        provider_selection = self.provider_rule.selection
        provider_receipt = self.provider_rule.receipt
        if (
            type(provider_selection) is not _selection_type
            or type(provider_receipt) is not _receipt_type
            or type(self.provider_rule.requirement)
            is not _requirement_type
            or _requirement_serialize(self.provider_rule.requirement)
            != _requirement_serialize(_requirement)
            or provider_receipt != _selection_receipt(provider_selection)
            or self.provider_rule.rule_id
            != _requirement.rule_id
            or provider_selection.address.source_id
            != _requirement.source_id
            or provider_selection.address.locator
            != _requirement.locator
            or provider_selection.address.carrier_path
            != _requirement.carrier_path
            or provider_selection.address.selection_path
            != _requirement.selection_path
            or provider_selection.address.span
            != _requirement.span
            or (
                _requirement.expected_block_sha256
                is not None
                and _selection_block_sha(provider_selection)
                != _requirement.expected_block_sha256
            )
            or provider_receipt.digest == consumer_receipt.digest
        ):
            raise ValueError(
                "RegenerationPatch provider is not the reviewed rule source"
            )
        provider_capability = self.provider_rule._capability
        adapter = provider_capability.adapter
        if type(adapter) is not _adapter_type:
            raise TypeError(
                "RegenerationPatch provider has no exact source authority"
            )
        _validate_selection(adapter, self.consumer_source)
        for local_source in self.local_sources:
            _validate_selection(adapter, local_source.selection)
        _validate_rule(adapter, self.provider_rule)
        _require_shared(adapter, self.consumer_source, (self.provider_rule,))
        _rule_serialize(self.provider_rule)

        authority_digest = consumer_receipt.authority_digest
        if (
            provider_receipt.authority_digest != authority_digest
            or any(
                _selection_receipt(item.selection).authority_digest
                != authority_digest
                for item in self.local_sources
            )
        ):
            raise ValueError(
                "RegenerationPatch source views belong to split authorities"
            )
        expected_local_roles = {
            "fixed-page-reference": (),
            "fixed-unpaged": (),
            "hydra-linked": ("head-regrowth", "hydra-regeneration"),
            "phoenix-linked": ("self-resurrection",),
        }[self.source_shape]
        if tuple(item.role for item in self.local_sources) != expected_local_roles:
            raise ValueError(
                "RegenerationPatch local source roles disagree with shape"
            )
        expected_local_keys = {
            "head-regrowth": "!.Head Regrowth",
            "hydra-regeneration": "!.Hydra Regeneration",
            "self-resurrection": "!.Self-Resurrection",
        }
        for local in self.local_sources:
            selection = local.selection
            address = selection.address
            expected_key = expected_local_keys[local.role]
            if (
                address.source_id != consumer_address.source_id
                or address.locator != consumer_address.locator
                or address.section_id != consumer_address.section_id
                or address.target_path != consumer_address.target_path
                or address.carrier_path != consumer_address.carrier_path
                or _selection_block_sha(selection)
                != _selection_block_sha(self.consumer_source)
                or address.span is not None
                or len(address.selection_path) != 1
                or type(address.selection_path[0]) is not _member_step_type
                or address.selection_path[0].raw_key != expected_key
                or type(selection.raw_member) is not _raw_member_type
                or selection.raw_member.key != expected_key
                or _selection_receipt(selection).digest
                == consumer_receipt.digest
            ):
                raise ValueError(
                    "RegenerationPatch local source is not linked to consumer"
                )
        if self.suppression_mode == "listed-damage":
            if (
                self.suppression_generation
                != "refresh-on-each-triggering-damage-event"
                or self.suppression_application
                != "before-triggering-damage-hit-point-commit"
                or self.persistent_damage_policy
                != (
                    "each-damage-instance-can-trigger-listed-deactivation"
                )
                or self.reactivation_timing != "end-owner-next-turn"
                or self.hydra is not None
                or not self.deactivation_selectors
            ):
                raise ValueError(
                    "listed-damage regeneration has inconsistent state"
                )
        elif (
            self.suppression_generation
            != "stable-head-and-stump-generations"
            or self.suppression_application
            != "after-head-and-stump-state-transition"
            or self.persistent_damage_policy
            != "requires-exact-stump-targeting-and-remains-deferred"
            or self.reactivation_timing != "terminal-no-reactivation"
            or self.hydra is None
            or self.deactivation_selectors
        ):
            raise ValueError(
                "Hydra regeneration has inconsistent terminal state"
            )
        shape_facts = (
            self.reference_page,
            self.hydra is not None,
            self.self_resurrection is not None,
        )
        expected_shape_facts = {
            "fixed-page-reference": (360, False, False),
            "fixed-unpaged": (None, False, False),
            "hydra-linked": (360, True, False),
            "phoenix-linked": (360, False, True),
        }
        if shape_facts != expected_shape_facts[self.source_shape]:
            raise ValueError(
                "RegenerationPatch source shape disagrees with metadata"
            )

    def as_serialized(
        self,
        _mechanic_type=MECHANIC_TYPE,
        _status=REGISTRY_STATUS,
        _family_id=FAMILY_ID,
        _compiler_id=COMPILER_ID,
        _pool_serialize=HitPointPool.as_serialized,
        _formula_serialize=RecoveryFormula.as_serialized,
        _selector_serialize=SuppressionSelector.as_serialized,
        _hydra_serialize=HydraMetadata.as_serialized,
        _resurrection_serialize=SelfResurrectionMetadata.as_serialized,
        _receipt_get=VerifiedSourceSelection.receipt.fget,
        _receipt_serialize=SourceReceipt.as_serialized,
        _local_serialize=VerifiedLocalSource.as_serialized,
        _rule_serialize=VerifiedRuleReceipt.as_serialized,
        _deferred_serialize=DeferredRequirement.as_serialized,
    ) -> SerializedObject:
        mechanic: SerializedObject = {
            "type": _mechanic_type,
            "status": _status,
            "sourceShape": self.source_shape,
            "hitPointPools": [
                _pool_serialize(item) for item in self.hit_point_pools
            ],
            "recovery": _formula_serialize(self.formula),
            "schedule": {
                "recovery": "beginning-owner-turn",
                "reactivation": self.reactivation_timing,
            },
            "suppression": {
                "mode": self.suppression_mode,
                "selectors": [
                    _selector_serialize(item)
                    for item in self.deactivation_selectors
                ],
                "apply": self.suppression_application,
                "generation": self.suppression_generation,
                "persistentDamage": self.persistent_damage_policy,
            },
            "dying": {
                "maximumWhileActive": 3,
                "suppressionCanPermitDying4": True,
            },
            "sourceText": self.source_text,
        }
        if self.reference_page is not None:
            mechanic["referencePage"] = self.reference_page
        if self.hydra is not None:
            mechanic["hydra"] = _hydra_serialize(self.hydra)
        if self.self_resurrection is not None:
            mechanic["selfResurrection"] = (
                _resurrection_serialize(self.self_resurrection)
            )
        return {
            "family": _family_id,
            "compiler": _compiler_id,
            "creature": {
                "name": self.creature_name,
                "sourceId": self.consumer_source.address.source_id,
                "locator": self.consumer_source.address.locator,
            },
            "mechanic": mechanic,
            "consumerSource": (
                _receipt_serialize(_receipt_get(self.consumer_source))
            ),
            "localSources": [
                _local_serialize(item) for item in self.local_sources
            ],
            "providerRules": [_rule_serialize(self.provider_rule)],
            "deferredMechanics": [
                _deferred_serialize(item)
                for item in self.deferred_requirements
            ],
        }


def _build_closed_serialized_validator():
    max_depth = 64
    max_nodes = 16_384
    max_string_bytes = MAX_REGENERATION_SOURCE_BYTES
    max_integer = MAX_SOURCE_INTEGER

    def validate(value: object) -> None:
        active: set[int] = set()
        nodes = 0

        def visit(item: object, depth: int) -> None:
            nonlocal nodes
            nodes += 1
            if nodes > max_nodes:
                raise ValueError("serialized object exceeds its node bound")
            if depth > max_depth:
                raise ValueError("serialized object exceeds its depth bound")
            if item is None or type(item) is bool:
                return
            if type(item) is int:
                if item < -max_integer or item > max_integer:
                    raise ValueError(
                        "serialized integer exceeds signed 64-bit bounds"
                    )
                return
            if type(item) is str:
                if len(item.encode("utf-8")) > max_string_bytes:
                    raise ValueError(
                        "serialized string exceeds its byte bound"
                    )
                return
            if type(item) not in (dict, list):
                raise TypeError(
                    "serialized values must use exact JSON container types"
                )
            identity = id(item)
            if identity in active:
                raise ValueError("serialized object contains a cycle")
            active.add(identity)
            try:
                if type(item) is dict:
                    for key, child in item.items():
                        if type(key) is not str:
                            raise TypeError(
                                "serialized object keys must be exact strings"
                            )
                        visit(key, depth + 1)
                        visit(child, depth + 1)
                else:
                    for child in item:
                        visit(child, depth + 1)
            finally:
                active.remove(identity)

        visit(value, 0)

    return validate


_VALIDATE_CLOSED_SERIALIZED = _build_closed_serialized_validator()


def _install_public_record_contract(record_type: type) -> None:
    expected_type = record_type
    original_post_init = record_type.__post_init__
    original_serialize = record_type.as_serialized
    validate_serialized = _VALIDATE_CLOSED_SERIALIZED

    def validate(value: object) -> None:
        if type(value) is not expected_type:
            raise TypeError(
                f"{expected_type.__name__} requires its exact public type"
            )
        try:
            original_post_init(value)
        except AttributeError as error:
            raise TypeError(
                f"{expected_type.__name__} is structurally incomplete"
            ) from error
        except RecursionError as error:
            raise ValueError(
                f"{expected_type.__name__} contains a structural cycle"
            ) from error

    def serialize(value: object) -> SerializedObject:
        validate(value)
        try:
            result = original_serialize(value)
            validate_serialized(result)
        except RecursionError as error:
            raise ValueError(
                f"{expected_type.__name__} serialization contains a cycle"
            ) from error
        return result

    record_type.__post_init__ = validate
    record_type.as_serialized = serialize


for _PUBLIC_RECORD_TYPE in (
    HitPointPool,
    SuppressionSelector,
    RecoveryFormula,
    HydraMetadata,
    SelfResurrectionMetadata,
    DeferredRequirement,
    VerifiedLocalSource,
):
    _install_public_record_contract(_PUBLIC_RECORD_TYPE)


def _install_patch_contract(patch_type: type):
    expected_type = patch_type
    field_names = (
        "creature_name",
        "source_text",
        "source_shape",
        "hit_point_pools",
        "formula",
        "suppression_mode",
        "suppression_generation",
        "suppression_application",
        "persistent_damage_policy",
        "deactivation_selectors",
        "reactivation_timing",
        "reference_page",
        "hydra",
        "self_resurrection",
        "consumer_source",
        "local_sources",
        "provider_rule",
        "deferred_requirements",
    )
    validate_structure = patch_type.__post_init__
    serialize_structure = patch_type.as_serialized
    validate_serialized = _VALIDATE_CLOSED_SERIALIZED

    def validate(value: object) -> None:
        if type(value) is not expected_type:
            raise TypeError(
                "RegenerationPatch requires its exact public type"
            )
        try:
            validate_structure(value)
        except AttributeError as error:
            raise TypeError(
                "RegenerationPatch is structurally incomplete"
            ) from error
        except RecursionError as error:
            raise ValueError(
                "RegenerationPatch contains a structural cycle"
            ) from error

    def serialize(value: object) -> SerializedObject:
        validate(value)
        try:
            result = serialize_structure(value)
            validate_serialized(result)
        except RecursionError as error:
            raise ValueError(
                "RegenerationPatch serialization contains a cycle"
            ) from error
        return result

    def create(**values: object):
        if (
            type(values) is not dict
            or tuple(values) != field_names
        ):
            raise TypeError(
                "RegenerationPatch factory requires every exact field"
            )
        return expected_type(**values)

    patch_type.__post_init__ = validate
    patch_type.as_serialized = serialize
    return create


_CREATE_REGENERATION_PATCH = _install_patch_contract(RegenerationPatch)


def _unique_direct_member(
    selection: VerifiedSourceSelection,
    authority: SourceAuthorityAdapter,
    raw_key: str,
    _raw_object_type=RawSourceObject,
    _raw_member_type=RawSourceMember,
    _member_step_type=RawMemberStep,
) -> VerifiedSourceSelection | None:
    block = selection.carrier.raw_block
    if type(block) is not _raw_object_type:
        return None
    matches = tuple(
        (index, member)
        for index, member in enumerate(block.members)
        if type(member) is _raw_member_type and member.key == raw_key
    )
    if len(matches) != 1:
        return None
    ordinal, _member = matches[0]
    return authority.resolve(
        authority.address(
            source_id=selection.address.source_id,
            locator=selection.address.locator,
            carrier_path=selection.address.carrier_path,
            selection_path=(_member_step_type(raw_key, ordinal),),
        )
    )


def _trusted_hp_selection(
    source: object,
    authority: object,
    _selection_type=VerifiedSourceSelection,
    _authority_type=SourceAuthorityAdapter,
    _source_id=MONSTER_CORE_SOURCE_ID,
    _member_step_type=RawMemberStep,
    _raw_member_type=RawSourceMember,
    _raw_object_type=RawSourceObject,
    _name_bytes=MAX_CREATURE_NAME_BYTES,
    _bounded=_bounded_source_text,
) -> tuple[VerifiedSourceSelection, str, str] | None:
    if type(source) is not _selection_type:
        raise TypeError(
            "regeneration source must be an exact VerifiedSourceSelection"
        )
    if type(authority) is not _authority_type:
        raise TypeError(
            "regeneration authority must be an exact SourceAuthorityAdapter"
        )
    verified = authority.reload(source.receipt)
    authority.validate_selection(source)
    address = verified.address
    if (
        address.source_id != _source_id
        or address.span is not None
        or type(address.selection_path) is not tuple
        or len(address.selection_path) != 1
        or type(address.selection_path[0]) is not _member_step_type
        or address.selection_path[0].raw_key != "HP"
        or type(verified.raw_member) is not _raw_member_type
        or verified.raw_member.key != "HP"
        or type(verified.raw_value) is not str
        or type(verified.selected_value) is not str
        or verified.raw_value != verified.selected_value
    ):
        return None
    block = verified.carrier.raw_block
    if type(block) is not _raw_object_type:
        return None
    hp_members = tuple(
        (index, member)
        for index, member in enumerate(block.members)
        if type(member) is _raw_member_type and member.key == "HP"
    )
    name_members = tuple(
        member
        for member in block.members
        if type(member) is _raw_member_type and member.key == "Name"
    )
    step = address.selection_path[0]
    if (
        len(hp_members) != 1
        or hp_members[0][0] != step.member_ordinal
        or hp_members[0][1] != verified.raw_member
        or len(name_members) != 1
        or type(name_members[0].value) is not str
    ):
        return None
    creature_name = name_members[0].value
    if (
        not creature_name
        or creature_name != creature_name.strip()
        or len(creature_name.encode("utf-8")) > _name_bytes
        or _bounded(verified.raw_value) is None
    ):
        return None
    return verified, creature_name, verified.raw_value


def _deactivation_selectors(
    value: str,
    _damage_types=CANONICAL_DAMAGE_TYPES,
    _reviewed_non_damage=tuple(REVIEWED_NON_DAMAGE_SELECTORS.items()),
    _selector_type=SuppressionSelector,
) -> tuple[SuppressionSelector, ...] | None:
    reviewed_non_damage = dict(_reviewed_non_damage)
    atoms = value.split(" or ")
    if not atoms or any(not atom for atom in atoms):
        return None
    if len(atoms) != len(set(atoms)):
        return None
    result: list[SuppressionSelector] = []
    for atom in atoms:
        if atom in _damage_types:
            kind: SelectorKind = "damage-type"
        else:
            reviewed = reviewed_non_damage.get(atom)
            if reviewed is None:
                return None
            kind = reviewed
        result.append(_selector_type(kind=kind, value=atom))
    return tuple(result)


def _common_deferrals(
    selectors: tuple[SuppressionSelector, ...],
    _deferred_type=DeferredRequirement,
) -> list[DeferredRequirement]:
    result = [
        _deferred_type(
            "turn-start-recovery",
            "Monster Core Regeneration provider rule",
        ),
        _deferred_type(
            "end-next-turn-reactivation",
            "Monster Core Regeneration provider rule",
        ),
        _deferred_type(
            "suppression-trigger-ordering",
            "deactivate before triggering damage commits Hit Points",
        ),
        _deferred_type(
            "suppression-generation-state",
            "later trigger damage must supersede an older reactivation",
        ),
        _deferred_type(
            "persistent-damage-triggering",
            "each persistent-damage instance is its own damage event",
        ),
        _deferred_type(
            "dying-cap",
            "active regeneration prevents dying from increasing beyond 3",
        ),
        _deferred_type(
            "zero-hit-point-resolution",
            "suppression can permit the triggering damage to reach dying 4",
        ),
        _deferred_type(
            "healing-hit-point-commit",
            "recovery must use bounded current and maximum Hit Points",
        ),
    ]
    if any(item.kind == "material" for item in selectors):
        result.append(
            _deferred_type(
                "material-selector-matching",
                "cold iron is a material selector, not a damage type",
            )
        )
    if any(item.kind == "trait" for item in selectors):
        result.append(
            _deferred_type(
                "trait-selector-matching",
                "holy and unholy are trait selectors, not damage types",
            )
        )
    return result


def _hydra_deferrals(
    _deferred_type=DeferredRequirement,
) -> list[DeferredRequirement]:
    return [
        _deferred_type(
            "turn-start-recovery",
            "Hydra Regeneration uses the Monster Core provider schedule",
        ),
        _deferred_type(
            "suppression-trigger-ordering",
            "terminal suppression follows exact head and stump transitions",
        ),
        _deferred_type(
            "suppression-generation-state",
            "head and stump generations must retain exact identities",
        ),
        _deferred_type(
            "persistent-damage-triggering",
            "persistent acid or fire needs an exact stump-target decision",
        ),
        _deferred_type(
            "dying-cap",
            "active regeneration prevents dying from increasing beyond 3",
        ),
        _deferred_type(
            "zero-hit-point-resolution",
            "terminal head and stump state can end regeneration and kill",
        ),
        _deferred_type(
            "healing-hit-point-commit",
            "dynamic recovery must use bounded body Hit Points",
        ),
    ]


def _linked_ordered_paragraphs(
    source: VerifiedSourceSelection,
    _raw_object_type=RawSourceObject,
    _raw_member_type=RawSourceMember,
    _maximum_bytes=MAX_REGENERATION_SOURCE_BYTES,
) -> tuple[str, ...] | None:
    if type(source.raw_value) is not _raw_object_type:
        return None
    paragraphs: list[str] = []
    total_bytes = 0
    for member in source.raw_value.members:
        if (
            type(member) is not _raw_member_type
            or member.key != "~.p"
            or type(member.value) is not str
        ):
            return None
        total_bytes += len(member.value.encode("utf-8"))
        if total_bytes > _maximum_bytes:
            return None
        paragraphs.append(member.value)
    if not paragraphs:
        return None
    return tuple(paragraphs)


def _compile_hydra(
    source: VerifiedSourceSelection,
    authority: SourceAuthorityAdapter,
    creature_name: str,
    source_text: str,
    match: re.Match[str],
    provider: VerifiedRuleReceipt,
    _positive_integer=_positive_source_integer,
    _unique_member=_unique_direct_member,
    _ordered_paragraphs=_linked_ordered_paragraphs,
    _normalize=_normalized,
    _head_pattern=_HEAD_REGROWTH_RE,
    _regeneration_pattern=_HYDRA_REGENERATION_RE,
    _selector_parser=_deactivation_selectors,
    _base_deferrals=_hydra_deferrals,
    _deferred_type=DeferredRequirement,
    _patch_factory=_CREATE_REGENERATION_PATCH,
    _pool_type=HitPointPool,
    _formula_type=RecoveryFormula,
    _hydra_type=HydraMetadata,
    _local_source_type=VerifiedLocalSource,
) -> RegenerationPatch | None:
    body_hp = _positive_integer(match.group("body"))
    head_hp = _positive_integer(match.group("head"))
    if body_hp is None or head_hp is None:
        return None
    head_regrowth = _unique_member(
        source,
        authority,
        "!.Head Regrowth",
    )
    hydra_regeneration = _unique_member(
        source,
        authority,
        "!.Hydra Regeneration",
    )
    if head_regrowth is None or hydra_regeneration is None:
        return None
    authority.validate_selection(head_regrowth)
    authority.validate_selection(hydra_regeneration)
    authority.validate_rule(provider)
    authority.require_shared_authority(source, (provider,))
    paragraphs = _ordered_paragraphs(head_regrowth)
    regeneration_text = _normalize(hydra_regeneration.raw_value)
    if paragraphs is None or len(paragraphs) != 2 or regeneration_text is None:
        return None
    head_match = _head_pattern.fullmatch(
        " ".join(" ".join(item.split()) for item in paragraphs)
    )
    regeneration_match = _regeneration_pattern.fullmatch(
        regeneration_text
    )
    if head_match is None or regeneration_match is None:
        return None
    ordinary_heads = 5 if head_match.group("ordinary") == "five" else None
    coefficient = _positive_integer(
        regeneration_match.group("coefficient")
    )
    save_dc = _positive_integer(regeneration_match.group("dc"))
    selectors = _selector_parser(head_match.group("selectors"))
    if (
        creature_name != "Hydra"
        or body_hp != 90
        or head_hp != 15
        or ordinary_heads is None
        or coefficient is None
        or coefficient != 3
        or save_dc is None
        or selectors is None
        or tuple(item.value for item in selectors) != ("acid", "fire")
    ):
        return None
    deferred = _base_deferrals()
    deferred.extend(
        (
            _deferred_type(
                "multiple-hit-point-pools",
                "Hydra body and each head have separate Hit Point pools",
            ),
            _deferred_type(
                "head-targeting",
                "a creature can target a particular Hydra head",
            ),
            _deferred_type(
                "head-damage-reset",
                "an incompletely severed head heals at end of any turn",
            ),
            _deferred_type(
                "stump-cauterization",
                "acid and fire can cauterize one or all exact stumps",
            ),
            _deferred_type(
                "dynamic-regeneration-amount",
                "Hydra recovery is three times its current head count",
            ),
            _deferred_type(
                "post-regeneration-save",
                "the Fortitude save occurs after recovery",
            ),
            _deferred_type(
                "head-regrowth",
                "success degrees regrow different stump counts",
            ),
            _deferred_type(
                "head-count-reactions",
                "head count changes the separate Reactive Heads mechanic",
            ),
            _deferred_type(
                "terminal-head-state-death",
                "all five heads cauterized is a terminal death state",
            ),
        )
    )
    return _patch_factory(
        creature_name=creature_name,
        source_text=source_text,
        source_shape="hydra-linked",
        hit_point_pools=(
            _pool_type("body", body_hp, 1),
            _pool_type("head", head_hp, ordinary_heads),
        ),
        formula=_formula_type(
            "per-active-head",
            amount_per_active_head=coefficient,
        ),
        suppression_mode="all-heads-severed-and-stumps-cauterized",
        suppression_generation="stable-head-and-stump-generations",
        suppression_application="after-head-and-stump-state-transition",
        persistent_damage_policy=(
            "requires-exact-stump-targeting-and-remains-deferred"
        ),
        deactivation_selectors=(),
        reactivation_timing="terminal-no-reactivation",
        reference_page=360,
        hydra=_hydra_type(
            ordinary_heads=ordinary_heads,
            maximum_heads=ordinary_heads * 2,
            regrowth_save_dc=save_dc,
            success_stumps=1,
            critical_success_stumps=2,
            heads_per_regrown_stump=2,
            cauterization_selectors=selectors,
        ),
        self_resurrection=None,
        consumer_source=source,
        local_sources=(
            _local_source_type("head-regrowth", head_regrowth),
            _local_source_type(
                "hydra-regeneration",
                hydra_regeneration,
            ),
        ),
        provider_rule=provider,
        deferred_requirements=tuple(deferred),
    )


def _compile_self_resurrection(
    source: VerifiedSourceSelection,
    authority: SourceAuthorityAdapter,
    _unique_member=_unique_direct_member,
    _raw_object_type=RawSourceObject,
    _raw_member_type=RawSourceMember,
    _raw_array_type=RawSourceArray,
    _normalize=_normalized,
    _pattern=_SELF_RESURRECTION_RE,
    _positive_integer=_positive_source_integer,
    _metadata_type=SelfResurrectionMetadata,
    _local_source_type=VerifiedLocalSource,
) -> tuple[SelfResurrectionMetadata, VerifiedLocalSource] | None:
    linked = _unique_member(
        source,
        authority,
        "!.Self-Resurrection",
    )
    if linked is None or type(linked.raw_value) is not _raw_object_type:
        return None
    members = linked.raw_value.members
    if (
        type(members) is not tuple
        or len(members) != 2
        or any(type(member) is not _raw_member_type for member in members)
        or tuple(member.key for member in members)
        != ("Traits", "Description")
        or type(members[0].value) is not _raw_array_type
        or members[0].value.items != ("healing", "primal")
        or type(members[1].value) is not str
    ):
        return None
    description = _normalize(members[1].value)
    if description is None:
        return None
    match = _pattern.fullmatch(description)
    if match is None:
        return None
    count = _positive_integer(match.group("count"))
    sides = _positive_integer(match.group("sides"))
    rank = _positive_integer(match.group("rank"))
    if count is None or sides is None or rank is None:
        return None
    return (
        _metadata_type(count, sides, rank),
        _local_source_type("self-resurrection", linked),
    )


def compile_regeneration(
    source: object,
    authority: object,
    /,
    *,
    _trusted_source=_trusted_hp_selection,
    _normalize=_normalized,
    _hydra_pattern=_HYDRA_HP_RE,
    _provider_requirement=REGENERATION_RULE_REQUIREMENT,
    _requirement_type=RuleRequirement,
    _requirement_serialize=RuleRequirement.as_serialized,
    _review_error=SourceReviewError,
    _hydra_compiler=_compile_hydra,
    _fixed_pattern=_FIXED_HP_RE,
    _positive_integer=_positive_source_integer,
    _selector_parser=_deactivation_selectors,
    _self_resurrection_compiler=_compile_self_resurrection,
    _reviewed_unpaged=frozenset(REVIEWED_UNPAGED_FIXED_FORMS),
    _common_deferred=_common_deferrals,
    _deferred_type=DeferredRequirement,
    _pool_type=HitPointPool,
    _formula_type=RecoveryFormula,
    _patch_factory=_CREATE_REGENERATION_PATCH,
) -> RegenerationPatch | None:
    """Compile one authenticated Monster Core HP member, if regenerative."""

    trusted = _trusted_source(source, authority)
    if trusted is None:
        return None
    verified, creature_name, source_text = trusted
    normalized = _normalize(source_text)
    if normalized is None:
        return None

    hydra_match = _hydra_pattern.fullmatch(normalized)
    if hydra_match is not None:
        provider = authority.resolve_rule(_provider_requirement)
        if (
            type(provider.requirement) is not _requirement_type
            or _requirement_serialize(provider.requirement)
            != _requirement_serialize(_provider_requirement)
        ):
            raise _review_error(
                "regeneration provider requirement disagrees with review"
            )
        return _hydra_compiler(
            verified,
            authority,
            creature_name,
            source_text,
            hydra_match,
            provider,
        )

    match = _fixed_pattern.fullmatch(normalized)
    if match is None:
        return None
    hit_points = _positive_integer(match.group("hit_points"))
    amount = _positive_integer(match.group("amount"))
    selectors = _selector_parser(match.group("selectors"))
    if hit_points is None or amount is None or selectors is None:
        return None
    page_text = match.group("page")
    reference_page: int | None = None
    if page_text is not None:
        reference_page = _positive_integer(
            page_text.removeprefix("; page ")
        )
        if reference_page != 360:
            return None

    self_resurrection: SelfResurrectionMetadata | None = None
    local_sources: tuple[VerifiedLocalSource, ...] = ()
    if match.group("self_resurrection") is not None:
        if (
            creature_name != "Phoenix"
            or hit_points != 300
            or amount != 20
            or tuple(
                (item.kind, item.value) for item in selectors
            )
            != (("damage-type", "cold"), ("trait", "unholy"))
            or reference_page != 360
        ):
            return None
        compiled_self_resurrection = _self_resurrection_compiler(
            verified,
            authority,
        )
        if compiled_self_resurrection is None:
            return None
        self_resurrection, local_source = compiled_self_resurrection
        local_sources = (local_source,)
    elif reference_page is None and (
        creature_name,
        hit_points,
        amount,
        tuple((item.kind, item.value) for item in selectors),
    ) not in _reviewed_unpaged:
        return None

    provider = authority.resolve_rule(_provider_requirement)
    if (
        type(provider.requirement) is not _requirement_type
        or _requirement_serialize(provider.requirement)
        != _requirement_serialize(_provider_requirement)
    ):
        raise _review_error(
            "regeneration provider requirement disagrees with review"
        )
    authority.validate_rule(provider)
    authority.require_shared_authority(verified, (provider,))
    for local_source in local_sources:
        authority.validate_selection(local_source.selection)
    deferred = _common_deferred(selectors)
    if self_resurrection is not None:
        deferred.extend(
            (
                _deferred_type(
                    "self-resurrection-delay",
                    "Phoenix returns after a rolled round delay",
                ),
                _deferred_type(
                    "self-resurrection-remains",
                    "Self-Resurrection requires surviving remains",
                ),
                _deferred_type(
                    "self-resurrection-area-lock",
                    "unholy consecration can suspend the return",
                ),
                _deferred_type(
                    "self-resurrection-frequency",
                    "Self-Resurrection is limited to once per year",
                ),
                _deferred_type(
                    "self-resurrection-ritual",
                    "the return follows a seventh-rank resurrect ritual",
                ),
            )
        )
    return _patch_factory(
        creature_name=creature_name,
        source_text=source_text,
        source_shape=(
            "phoenix-linked"
            if self_resurrection is not None
            else (
                "fixed-page-reference"
                if reference_page is not None
                else "fixed-unpaged"
            )
        ),
        hit_point_pools=(_pool_type("body", hit_points, 1),),
        formula=_formula_type("fixed", fixed_amount=amount),
        suppression_mode="listed-damage",
        suppression_generation=(
            "refresh-on-each-triggering-damage-event"
        ),
        suppression_application=(
            "before-triggering-damage-hit-point-commit"
        ),
        persistent_damage_policy=(
            "each-damage-instance-can-trigger-listed-deactivation"
        ),
        deactivation_selectors=selectors,
        reactivation_timing="end-owner-next-turn",
        reference_page=reference_page,
        hydra=None,
        self_resurrection=self_resurrection,
        consumer_source=verified,
        local_sources=local_sources,
        provider_rule=provider,
        deferred_requirements=tuple(deferred),
    )


def _bind_public_compiler(unbound_compiler):
    reviewed_compiler = unbound_compiler

    def bound_compile_regeneration(
        source: object,
        authority: object,
        /,
    ) -> RegenerationPatch | None:
        return reviewed_compiler(source, authority)

    return bound_compile_regeneration


compile_regeneration = _bind_public_compiler(compile_regeneration)


__all__ = [
    "COMPILER_ID",
    "DeferredRequirement",
    "FAMILY_ID",
    "HitPointPool",
    "HydraMetadata",
    "MECHANIC_TYPE",
    "MONSTER_CORE_SOURCE_ID",
    "REGISTRY_STATUS",
    "REGENERATION_RULE_REQUIREMENT",
    "RecoveryFormula",
    "RegenerationPatch",
    "SelfResurrectionMetadata",
    "SourceShape",
    "SuppressionSelector",
    "VerifiedLocalSource",
    "compile_regeneration",
]

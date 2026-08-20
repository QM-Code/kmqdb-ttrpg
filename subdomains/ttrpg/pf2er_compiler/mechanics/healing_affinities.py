"""Compile Monster Core Fast Healing and Void Healing source annotations.

The current runtime registry owns named creature abilities, while these two
families are authored compositionally inside the raw ``HP`` member.  One HP
value can also contain both families and unrelated sibling annotations.  This
module therefore exposes a lossless, compile/link-only seam over exact
verifier-issued consumer selections and hash-pinned provider rules.  It
deliberately performs no registry or runtime activation.

Creature-local producers, suppressors, and affinity overrides are classified
separately as deferred records.  Their exact source shapes are retained for a
future runtime lane; they are never inferred from a creature name or from a
``healing`` substring.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any

from .contracts import (
    AbilityCompilerPatch,
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RuleReference,
    SerializedObject,
)
from .source_authority import (
    AUTHORITY_RULESET,
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    TextSpan,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
)
from .source_values import MAX_SOURCE_INTEGER, parse_decimal_integer


FAMILY_ID = "healing-affinities"
FAST_HEALING_MECHANIC_TYPE = "fast-healing"
VOID_HEALING_MECHANIC_TYPE = "void-healing"
MONSTER_CORE_SOURCE_ID = "core-mc1"

# These are compiler input limits, not rules values.  They keep an untrusted
# source carrier from turning a small grammar match into unbounded work while
# remaining far above every reviewed Core MC1 production.
MAX_HP_SOURCE_BYTES = 65_536
MAX_HP_TOKENS = 256
MAX_DEFERRED_SOURCE_MEMBERS = 1_024
MAX_SOURCE_TEXT_BYTES = 65_536
MAX_DEFERRED_MECHANICS = 64

FAST_HEALING_GLOSSARY_RULE = RuleReference(
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
)
VOID_HEALING_GLOSSARY_RULE = RuleReference(
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
)
FAST_HEALING_GLOSSARY_REQUIREMENT = RuleRequirement(
    rule_id="fast-healing-glossary",
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
    carrier_path=(RawMemberStep("^.ability", 14),),
    expected_block_sha256=(
        "f83490e709ad9c2933c45cf60b2f7b6ff7f5bafb38f02b37a976407e48a9d035"
    ),
)
VOID_HEALING_GLOSSARY_REQUIREMENT = RuleRequirement(
    rule_id="void-healing-glossary",
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
    carrier_path=(RawMemberStep("^.ability", 39),),
    expected_block_sha256=(
        "32c3101779d3af2048bcf6b45c580a0947788ea288b0f1e2f13398fda83e67da"
    ),
)
HIT_POINTS_REQUIREMENT = RuleRequirement(
    rule_id="hit-points-and-healing",
    source_id="core-pc1",
    locator="410.2",
    expected_block_sha256=(
        "81aa542ca1c16f15262c6a93fc69a5b38b9eda5647362bde637b131cc78cd869"
    ),
)
FAST_HEALING_PLAYER_REQUIREMENT = RuleRequirement(
    rule_id="fast-healing-and-regeneration",
    source_id="core-pc1",
    locator="410.4",
    expected_block_sha256=(
        "506aded94143e23549e0af1b931249735e88e680c59e962e464d60f67ab8089d"
    ),
)
START_TURN_REQUIREMENT = RuleRequirement(
    rule_id="start-your-turn",
    source_id="core-pc1",
    locator="435.8",
    expected_block_sha256=(
        "412cf21f6f82dfe98f3f3679ad31420c77b175d313f601738bd7f8db02487600"
    ),
)
ENERGY_DAMAGE_REQUIREMENT = RuleRequirement(
    rule_id="energy-damage",
    source_id="core-pc1",
    locator="409.3",
    expected_block_sha256=(
        "078d20b62dd5a522e8d44b44a0c7333f7c767b4b3375353f607132247a2788c9"
    ),
)
APPLY_IWR_REQUIREMENT = RuleRequirement(
    rule_id="apply-immunities-weaknesses-resistances",
    source_id="core-pc1",
    locator="407.3",
    expected_block_sha256=(
        "70d4b59f1e222320d84c65c73eee11d14210e6800d7ecdbd3ce000da6f13bc21"
    ),
)

RULE_REQUIREMENTS = (
    FAST_HEALING_GLOSSARY_REQUIREMENT,
    HIT_POINTS_REQUIREMENT,
    FAST_HEALING_PLAYER_REQUIREMENT,
    START_TURN_REQUIREMENT,
    VOID_HEALING_GLOSSARY_REQUIREMENT,
    ENERGY_DAMAGE_REQUIREMENT,
    APPLY_IWR_REQUIREMENT,
)

_CANONICAL_POSITIVE_INTEGER_RE = re.compile(r"^[1-9][0-9]*$", re.ASCII)
_PARENTHESIZED_FAST_HEALING_RE = re.compile(
    r"^(?P<hit_points>[1-9][0-9]*) "
    r"\(fast healing (?P<amount>[1-9][0-9]*)\)$",
    re.ASCII,
)
_FAST_HEALING_RE = re.compile(
    r"^fast healing (?P<amount>[1-9][0-9]*)"
    r"(?: \((?P<qualifier>"
    r"page 359|"
    r"in open air|"
    r"while underground|"
    r"while touching fire|"
    r"while underwater"
    r")\))?$",
    re.ASCII,
)
_VOID_HEALING_RE = re.compile(
    r"^void healing(?: \(page (?P<page>360)\))?$",
    re.ASCII,
)
_RESERVED_HEALING_PHRASE_RE = re.compile(
    r"(?<![A-Za-z])(?:fast|void) healing(?![A-Za-z])",
    re.IGNORECASE | re.ASCII,
)

_FAST_HEALING_CONDITIONS = MappingProxyType({
    "in open air": MappingProxyType({
        "kind": "environment",
        "predicate": "open-air",
        "sourceText": "in open air",
    }),
    "while underground": MappingProxyType({
        "kind": "environment",
        "predicate": "underground",
        "sourceText": "while underground",
    }),
    "while touching fire": MappingProxyType({
        "kind": "contact",
        "predicate": "fire",
        "sourceText": "while touching fire",
    }),
    "while underwater": MappingProxyType({
        "kind": "environment",
        "predicate": "underwater",
        "sourceText": "while underwater",
    }),
})


class HealingAffinitiesCompileError(ValueError):
    """A family-shaped source value was structurally ambiguous."""


class HealingAffinitiesAddressabilityError(ValueError):
    """Verified evidence does not satisfy the reviewed source contract."""


def _require_nonnegative_integer(value: object, label: str) -> None:
    if (
        type(value) is not int
        or value < 0
        or value > MAX_SOURCE_INTEGER
    ):
        raise ValueError(
            f"{label} must be a non-negative signed 64-bit integer"
        )


def _require_trimmed_text(value: object, label: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{label} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    if (
        len(value) > MAX_SOURCE_TEXT_BYTES
        or len(value.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES
    ):
        raise ValueError(f"{label} exceeds its UTF-8 byte bound")


@dataclass(frozen=True, slots=True)
class _VerifiedHPStat:
    """Exact HP text derived from one verified creature carrier."""

    source_value: str

    def __post_init__(self) -> None:
        if type(self.source_value) is not str:
            raise TypeError("_VerifiedHPStat.source_value must be a string")


@dataclass(frozen=True, slots=True)
class PreservedHPAnnotation:
    """One unconsumed top-level HP annotation in exact source order."""

    ordinal: int
    raw: str

    def __post_init__(self) -> None:
        _require_nonnegative_integer(
            self.ordinal,
            "PreservedHPAnnotation.ordinal",
        )
        _require_trimmed_text(self.raw, "PreservedHPAnnotation.raw")

    def as_serialized(self) -> SerializedObject:
        return {
            "ordinal": self.ordinal,
            "raw": self.raw,
        }


@dataclass(frozen=True, slots=True)
class CompiledHealingAbility:
    """One supported healing ability retained inside a composite HP patch."""

    ordinal: int
    ability_id: str
    ability_name: str
    ability: AbilityCompilerPatch

    def __post_init__(self) -> None:
        _require_nonnegative_integer(
            self.ordinal,
            "CompiledHealingAbility.ordinal",
        )
        _require_trimmed_text(
            self.ability_id,
            "CompiledHealingAbility.ability_id",
        )
        _require_trimmed_text(
            self.ability_name,
            "CompiledHealingAbility.ability_name",
        )
        if type(self.ability) is not AbilityCompilerPatch:
            raise TypeError(
                "CompiledHealingAbility.ability must be an "
                "AbilityCompilerPatch"
            )
        if type(self.ability.rule) is not RuleReference:
            raise TypeError(
                "CompiledHealingAbility rule must be an exact RuleReference"
            )

    @property
    def mechanic_type(self) -> str:
        return self.ability.mechanic_type

    @property
    def runtime_ready(self) -> bool:
        # This family is compile/link-only.  A complete static description is
        # not a claim that a registry mount and runtime handler exist.
        return False

    def as_serialized(self) -> SerializedObject:
        return {
            "ordinal": self.ordinal,
            "id": self.ability_id,
            "name": self.ability_name,
            "runtimeReady": self.runtime_ready,
            **self.ability.as_ability_update(),
        }


@dataclass(frozen=True, slots=True)
class HealingAffinitiesPatch:
    """One maximum-HP scalar plus every owned compositional annotation."""

    stat_value: int
    abilities: tuple[CompiledHealingAbility, ...]
    unconsumed_annotations: tuple[PreservedHPAnnotation, ...]
    source: VerifiedSourceSelection
    providers: tuple[VerifiedRuleReceipt, ...]

    def __post_init__(self) -> None:
        if (
            type(self.stat_value) is not int
            or self.stat_value <= 0
            or self.stat_value > MAX_SOURCE_INTEGER
        ):
            raise ValueError(
                "HealingAffinitiesPatch.stat_value must be a positive "
                "signed 64-bit integer"
            )
        if type(self.abilities) is not tuple or not self.abilities:
            raise ValueError(
                "HealingAffinitiesPatch.abilities must be a non-empty tuple"
            )
        if len(self.abilities) > 2:
            raise ValueError(
                "HealingAffinitiesPatch.abilities exceeds its family bound"
            )
        if type(self.unconsumed_annotations) is not tuple:
            raise TypeError(
                "HealingAffinitiesPatch.unconsumed_annotations must be a "
                "tuple"
            )
        if (
            len(self.abilities) + len(self.unconsumed_annotations)
            > MAX_HP_TOKENS - 1
        ):
            raise ValueError(
                "HealingAffinitiesPatch annotations exceed their token bound"
            )
        if any(
            type(item) is not CompiledHealingAbility
            for item in self.abilities
        ):
            raise TypeError(
                "HealingAffinitiesPatch.abilities must contain only "
                "CompiledHealingAbility values"
            )
        if any(
            type(item) is not PreservedHPAnnotation
            for item in self.unconsumed_annotations
        ):
            raise TypeError(
                "HealingAffinitiesPatch.unconsumed_annotations must contain "
                "only PreservedHPAnnotation values"
            )

        ability_types = tuple(
            item.mechanic_type for item in self.abilities
        )
        if len(ability_types) != len(set(ability_types)):
            raise HealingAffinitiesCompileError(
                "duplicate healing-affinity mechanic in one HP member"
            )
        ordinals = tuple(item.ordinal for item in self.abilities) + tuple(
            item.ordinal for item in self.unconsumed_annotations
        )
        if len(ordinals) != len(set(ordinals)):
            raise HealingAffinitiesCompileError(
                "duplicate HP annotation ordinal"
            )
        if tuple(sorted(ordinals)) != tuple(range(len(ordinals))):
            raise HealingAffinitiesCompileError(
                "HP annotation ordinals are not contiguous from source zero"
            )
        if tuple(item.ordinal for item in self.abilities) != tuple(
            sorted(item.ordinal for item in self.abilities)
        ) or tuple(
            item.ordinal for item in self.unconsumed_annotations
        ) != tuple(
            sorted(
                item.ordinal for item in self.unconsumed_annotations
            )
        ):
            raise HealingAffinitiesCompileError(
                "HP annotations are not in exact source order"
            )
        if type(self.source) is not VerifiedSourceSelection:
            raise TypeError(
                "HealingAffinitiesPatch.source must be verifier-issued"
            )
        if (
            type(self.providers) is not tuple
            or len(self.providers) != 7
            or any(
                type(item) is not VerifiedRuleReceipt
                for item in self.providers
            )
        ):
            raise TypeError(
                "HealingAffinitiesPatch.providers must be the exact "
                "verified rule tuple"
            )

    @property
    def runtime_ready(self) -> bool:
        return False

    @property
    def source_receipt(self) -> SourceReceipt:
        return self.source.receipt

    def as_serialized(self) -> SerializedObject:
        return {
            "statValue": self.stat_value,
            "runtimeReady": self.runtime_ready,
            "source": self.source.receipt.as_serialized(),
            "rules": {
                provider.rule_id: provider.as_serialized()
                for provider in self.providers
            },
            "abilities": [
                ability.as_serialized() for ability in self.abilities
            ],
            "unconsumedAnnotations": [
                annotation.as_serialized()
                for annotation in self.unconsumed_annotations
            ],
        }


@dataclass(frozen=True, slots=True)
class DeferredHealingRecord:
    """One exact creature-local source record awaiting runtime support."""

    ordinal: int
    raw_key: str
    source_label: str
    family: str
    classification: str
    source_text: str
    source: VerifiedSourceSelection
    providers: tuple[VerifiedRuleReceipt, ...]
    deferred_mechanics: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonnegative_integer(
            self.ordinal,
            "DeferredHealingRecord.ordinal",
        )
        for field_name in (
            "raw_key",
            "source_label",
            "family",
            "classification",
            "source_text",
        ):
            _require_trimmed_text(
                getattr(self, field_name),
                f"DeferredHealingRecord.{field_name}",
            )
        if self.family not in (
            FAST_HEALING_MECHANIC_TYPE,
            VOID_HEALING_MECHANIC_TYPE,
        ):
            raise ValueError("DeferredHealingRecord.family is invalid")
        if type(self.deferred_mechanics) is not tuple:
            raise TypeError(
                "DeferredHealingRecord.deferred_mechanics must be a tuple"
            )
        if (
            not self.deferred_mechanics
            or len(self.deferred_mechanics) > MAX_DEFERRED_MECHANICS
        ):
            raise ValueError(
                "DeferredHealingRecord.deferred_mechanics must be a "
                "non-empty bounded tuple of strings"
            )
        for index, item in enumerate(self.deferred_mechanics):
            _require_trimmed_text(
                item,
                (
                    "DeferredHealingRecord.deferred_mechanics"
                    f"[{index}]"
                ),
            )
        if len(self.deferred_mechanics) != len(
            set(self.deferred_mechanics)
        ):
            raise ValueError(
                "DeferredHealingRecord.deferred_mechanics must be unique"
            )
        if type(self.source) is not VerifiedSourceSelection:
            raise TypeError(
                "DeferredHealingRecord.source must be verifier-issued"
            )
        if (
            type(self.providers) is not tuple
            or len(self.providers) != 7
            or any(
                type(item) is not VerifiedRuleReceipt
                for item in self.providers
            )
        ):
            raise TypeError(
                "DeferredHealingRecord.providers must be the exact "
                "verified rule tuple"
            )

    def as_serialized(self) -> SerializedObject:
        return {
            "ordinal": self.ordinal,
            "rawKey": self.raw_key,
            "sourceLabel": self.source_label,
            "family": self.family,
            "classification": self.classification,
            "sourceText": self.source_text,
            "source": self.source.receipt.as_serialized(),
            "rules": {
                provider.rule_id: provider.as_serialized()
                for provider in self.providers
            },
            "supported": False,
            "deferredMechanics": list(self.deferred_mechanics),
        }


@dataclass(frozen=True, slots=True)
class _DeferredSourceSpec:
    family: str
    classification: str
    deferred_mechanics: tuple[str, ...]


_FIRE_HEALING_DESCRIPTION = (
    "As long as a magma worm is in contact with a fire or body of magma at "
    "least as large as itself, it gains fast healing 20. When struck by a "
    "magical fire effect from anything other than itself, a magma worm "
    "regains Hit Points equal to half the fire damage the effect would "
    "otherwise deal."
)
_SOUL_SPELL_DESCRIPTION = (
    "If a venedaemon ingest a soul gem from a cacodaemon, they can recover "
    "an expended spell slot instead of gaining fast healing. The spell "
    "slot’s rank can be no higher than half the level of the creature whose "
    "soul was consumed, rounded up."
)
_SOUL_SIPHON_DESCRIPTION = (
    "If a small or larger creature dies within 10 feet of an astradaemon, "
    "the daemon draws its soul into their body as a free action with the "
    "divine and death traits. The victim's body quickly rots away, and the "
    "astradaemon gains fast healing 20 for 1 minute."
)
_GRIM_REAPER_VOID_DESCRIPTION = (
    "The Grim Reaper can choose whether or not it takes vitality damage."
)
_LESSER_DEATH_VOID_DESCRIPTION = (
    "A lesser death can choose whether or not it takes vitality damage."
)
_FILTH_WALLOW_DESCRIPTION = (
    "An ofalth gains fast healing 2 when in an area with a high "
    "concentration of debris or excrement, such as a refuse heap or sewer."
)
_LIGHTNING_DRINKER_DESCRIPTION = (
    "Whenever a yamaraj would take electricity damage if not for its "
    "immunity, its fast healing increases to 40 on its next turn. During "
    "that turn, if it uses Beetle Breath, the beetles deal 2d12 additional "
    "electricity damage."
)
_RED_CAP_DESCRIPTION = (
    "A redcap's woolen hat is dyed with the blood of their victims. If the "
    "redcap loses their cap, they no longer benefit from fast healing and "
    "take a -4 status penalty to their damage rolls. They can create a new "
    "cap in 10 minutes, but that cap doesn't grant them powers until the "
    "redcap has turned it red with Blood Soak. A cap has no benefit for "
    "creatures other than the redcap who made it."
)
_VOIDS_EMBRACE_DESCRIPTION = (
    "If the victim succeeds at a saving throw against this curse while in "
    "sunlight, the curse ends. While you have this curse, you bypass the "
    "resistance of the wraith that cursed you; <b>Stage 1</b> the victim is "
    "dazzled in any light (1 hour); <b>Stage 2</b> the victim gains "
    "lifesense 30 feet but is blinded in any light (1 hour); <b>Stage 3</b> "
    "as stage 2, but the creature also has void healing (1 hour); "
    "<b>Stage 4</b> the victim becomes unconscious and can't awaken (1 "
    "day); <b>Stage 5</b> the creature dies and becomes a wraith, its body "
    "crumbling to ash"
)

_DEFERRED_EXACT_SOURCE_VALUES = MappingProxyType({
    ("!.Fire Healing", _FIRE_HEALING_DESCRIPTION): (
        _FIRE_HEALING_DESCRIPTION
    ),
    ("!.Soul Spell", _SOUL_SPELL_DESCRIPTION): _SOUL_SPELL_DESCRIPTION,
    ("!.Soul Siphon", _SOUL_SIPHON_DESCRIPTION): (
        _SOUL_SIPHON_DESCRIPTION
    ),
    ("!.Void Healing", _GRIM_REAPER_VOID_DESCRIPTION): (
        _GRIM_REAPER_VOID_DESCRIPTION
    ),
    ("!.Void Healing", _LESSER_DEATH_VOID_DESCRIPTION): (
        _LESSER_DEATH_VOID_DESCRIPTION
    ),
    ("!.Filth Wallow", _FILTH_WALLOW_DESCRIPTION): (
        RawSourceObject.from_pairs(
            (("Description", _FILTH_WALLOW_DESCRIPTION),)
        )
    ),
    ("!.Lightning Drinker", _LIGHTNING_DRINKER_DESCRIPTION): (
        RawSourceObject.from_pairs(
            (("Description", _LIGHTNING_DRINKER_DESCRIPTION),)
        )
    ),
    ("!.Red Cap", _RED_CAP_DESCRIPTION): RawSourceObject.from_pairs(
        (
            ("Traits", RawSourceArray(items=("primal",))),
            ("Description", _RED_CAP_DESCRIPTION),
        )
    ),
    ("!.Void's Embrace", _VOIDS_EMBRACE_DESCRIPTION): (
        RawSourceObject.from_pairs(
            (
                (
                    "Traits",
                    RawSourceArray(
                        items=("curse", "death", "divine", "void")
                    ),
                ),
                ("Saving Throw", "DC 24 Will"),
                ("Description", _VOIDS_EMBRACE_DESCRIPTION),
            )
        )
    ),
})

_DEFERRED_SOURCE_SPECS = MappingProxyType({
    (
        "!.Fire Healing",
        _FIRE_HEALING_DESCRIPTION,
    ): _DeferredSourceSpec(
        family=FAST_HEALING_MECHANIC_TYPE,
        classification="conditional-fast-healing-producer",
        deferred_mechanics=(
            "world-state-contact",
            "damage-to-healing-conversion",
        ),
    ),
    (
        "!.Soul Spell",
        _SOUL_SPELL_DESCRIPTION,
    ): _DeferredSourceSpec(
        family=FAST_HEALING_MECHANIC_TYPE,
        classification=(
            "contextual-fast-healing-alternative-reference"
        ),
        deferred_mechanics=("soul-gem-choice-context",),
    ),
    (
        "!.Soul Siphon",
        _SOUL_SIPHON_DESCRIPTION,
    ): _DeferredSourceSpec(
        family=FAST_HEALING_MECHANIC_TYPE,
        classification="temporary-fast-healing-producer",
        deferred_mechanics=(
            "nearby-death-trigger",
            "timed-exact-id-effect",
        ),
    ),
    (
        "!.Void Healing",
        _GRIM_REAPER_VOID_DESCRIPTION,
    ): _DeferredSourceSpec(
        family=VOID_HEALING_MECHANIC_TYPE,
        classification="vitality-damage-choice-override",
        deferred_mechanics=("pending-vitality-damage-choice",),
    ),
    (
        "!.Void Healing",
        _LESSER_DEATH_VOID_DESCRIPTION,
    ): _DeferredSourceSpec(
        family=VOID_HEALING_MECHANIC_TYPE,
        classification="vitality-damage-choice-override",
        deferred_mechanics=("pending-vitality-damage-choice",),
    ),
    (
        "!.Filth Wallow",
        _FILTH_WALLOW_DESCRIPTION,
    ): _DeferredSourceSpec(
        family=FAST_HEALING_MECHANIC_TYPE,
        classification="conditional-fast-healing-producer",
        deferred_mechanics=("world-state-area-concentration",),
    ),
    (
        "!.Lightning Drinker",
        _LIGHTNING_DRINKER_DESCRIPTION,
    ): _DeferredSourceSpec(
        family=FAST_HEALING_MECHANIC_TYPE,
        classification="next-turn-fast-healing-amount-modifier",
        deferred_mechanics=("next-turn-exact-id-modifier",),
    ),
    (
        "!.Red Cap",
        _RED_CAP_DESCRIPTION,
    ): _DeferredSourceSpec(
        family=FAST_HEALING_MECHANIC_TYPE,
        classification=(
            "equipment-controlled-fast-healing-suppression"
        ),
        deferred_mechanics=("equipment-empowerment-state",),
    ),
    (
        "!.Void's Embrace",
        _VOIDS_EMBRACE_DESCRIPTION,
    ): _DeferredSourceSpec(
        family=VOID_HEALING_MECHANIC_TYPE,
        classification="affliction-stage-void-healing-producer",
        deferred_mechanics=("affliction-stage-exact-id-effect",),
    ),
})
_DEFERRED_RAW_KEYS = frozenset(
    raw_key for raw_key, _source_text in _DEFERRED_SOURCE_SPECS
)


def _positive_source_integer(value: str) -> int | None:
    if _CANONICAL_POSITIVE_INTEGER_RE.fullmatch(value) is None:
        return None
    result = parse_decimal_integer(value)
    if result is None or result <= 0 or result > MAX_SOURCE_INTEGER:
        return None
    return result


def _split_top_level_commas(value: str) -> tuple[str, ...] | None:
    """Split the exact ``, `` HP production without flattening parentheses."""

    if (
        type(value) is not str
        or len(value) > MAX_HP_SOURCE_BYTES
        or len(value.encode("utf-8")) > MAX_HP_SOURCE_BYTES
    ):
        return None
    result: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(value):
        character = value[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return None
        elif character == "," and depth == 0:
            if index + 1 >= len(value) or value[index + 1] != " ":
                return None
            token = value[start:index]
            if not token or token != token.strip():
                return None
            if len(result) >= MAX_HP_TOKENS:
                return None
            result.append(token)
            start = index + 2
            index += 1
        index += 1
    if depth != 0:
        return None
    token = value[start:]
    if not token or token != token.strip():
        return None
    if len(result) >= MAX_HP_TOKENS:
        return None
    result.append(token)
    return tuple(result)


def _bind_provider_validator(
    requirements: tuple[RuleRequirement, ...],
) -> Callable[
    [
        SourceAuthorityAdapter,
        VerifiedSourceSelection,
        object,
    ],
    tuple[VerifiedRuleReceipt, ...],
]:
    def clone_path(
        path: tuple[RawMemberStep | RawIndexStep, ...],
    ) -> tuple[RawMemberStep | RawIndexStep, ...]:
        return tuple(
            RawMemberStep(step.raw_key, step.member_ordinal)
            if type(step) is RawMemberStep
            else RawIndexStep(step.item_ordinal)
            for step in path
        )

    reviewed_requirements = tuple(
        RuleRequirement(
            rule_id=requirement.rule_id,
            source_id=requirement.source_id,
            locator=requirement.locator,
            carrier_path=clone_path(requirement.carrier_path),
            selection_path=clone_path(requirement.selection_path),
            span=(
                None
                if requirement.span is None
                else TextSpan(
                    requirement.span.start,
                    requirement.span.end,
                )
            ),
            expected_block_sha256=requirement.expected_block_sha256,
            expected_member_sha256=requirement.expected_member_sha256,
            expected_value_sha256=requirement.expected_value_sha256,
            expected_selection_sha256=(
                requirement.expected_selection_sha256
            ),
        )
        for requirement in requirements
    )

    def validate(
        authority: SourceAuthorityAdapter,
        source: VerifiedSourceSelection,
        providers: object,
    ) -> tuple[VerifiedRuleReceipt, ...]:
        if type(providers) is not tuple:
            raise TypeError(
                "Healing Affinities providers must be an exact ordered tuple"
            )
        if len(providers) != len(reviewed_requirements):
            raise HealingAffinitiesAddressabilityError(
                "Healing Affinities requires every verifier-issued provider"
            )
        if any(type(item) is not VerifiedRuleReceipt for item in providers):
            raise TypeError(
                "Healing Affinities providers must contain only exact "
                "VerifiedRuleReceipt values"
            )
        authority.require_shared_authority(source, providers)
        for requirement, provider in zip(
            reviewed_requirements,
            providers,
            strict=True,
        ):
            if (
                provider.rule_id != requirement.rule_id
                or provider.requirement != requirement
                or provider.receipt != provider.selection.receipt
            ):
                raise HealingAffinitiesAddressabilityError(
                    "Healing Affinities provider order or reviewed identity "
                    f"disagrees: {requirement.rule_id}"
                )
        return providers

    return validate


_validated_providers = _bind_provider_validator(RULE_REQUIREMENTS)


def _verified_creature_block(
    authority: SourceAuthorityAdapter,
    source: object,
) -> RawSourceObject | None:
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "Healing Affinities requires a VerifiedSourceSelection"
        )
    authority.validate_selection(source)
    carrier = source.carrier
    address = source.address
    if (
        type(carrier) is not VerifiedSourceCarrier
        or carrier.ruleset != AUTHORITY_RULESET
        or carrier.source_id != MONSTER_CORE_SOURCE_ID
        or type(address.carrier_path) is not tuple
        or not address.carrier_path
        or type(address.carrier_path[-1]) is not RawMemberStep
        or address.carrier_path[-1].raw_key != "^.creature"
        or type(address.selection_path) is not tuple
        or address.selection_path
        or address.span is not None
        or type(carrier.raw_block) is not RawSourceObject
        or source.raw_value is not carrier.raw_block
        or source.selected_value is not source.raw_value
        or source.raw_member is not None
    ):
        return None
    if len(carrier.raw_block.members) > MAX_DEFERRED_SOURCE_MEMBERS:
        raise HealingAffinitiesCompileError(
            "raw source exceeds its member bound"
        )
    if any(
        type(member) is not RawSourceMember
        or type(member.key) is not str
        for member in carrier.raw_block.members
    ):
        raise HealingAffinitiesCompileError(
            "raw source contains non-exact members"
        )
    return carrier.raw_block


def _verified_hp_source(
    authority: SourceAuthorityAdapter,
    source: object,
) -> _VerifiedHPStat | None:
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "compile_healing_affinities requires a "
            "VerifiedSourceSelection"
        )
    authority.validate_selection(source)
    carrier = source.carrier
    address = source.address
    if (
        type(carrier) is not VerifiedSourceCarrier
        or carrier.ruleset != AUTHORITY_RULESET
        or carrier.source_id != MONSTER_CORE_SOURCE_ID
        or type(address.carrier_path) is not tuple
        or not address.carrier_path
        or type(address.carrier_path[-1]) is not RawMemberStep
        or address.carrier_path[-1].raw_key != "^.creature"
        or type(address.selection_path) is not tuple
        or len(address.selection_path) != 1
        or type(address.selection_path[0]) is not RawMemberStep
        or address.selection_path[0].raw_key != "HP"
        or address.span is not None
        or type(carrier.raw_block) is not RawSourceObject
        or type(source.raw_member) is not RawSourceMember
        or source.raw_member.key != "HP"
        or type(source.raw_value) is not str
        or source.selected_value is not source.raw_value
    ):
        return None
    block = carrier.raw_block
    if len(block.members) > MAX_DEFERRED_SOURCE_MEMBERS:
        raise HealingAffinitiesCompileError(
            "raw source exceeds its member bound"
        )
    step = address.selection_path[0]
    if step.member_ordinal >= len(block.members):
        raise HealingAffinitiesCompileError(
            "verified HP member ordinal is out of range"
        )
    member = block.members[step.member_ordinal]
    if (
        type(member) is not RawSourceMember
        or member is not source.raw_member
        or member.value is not source.raw_value
    ):
        raise HealingAffinitiesCompileError(
            "verified HP selection disagrees with its carrier"
        )
    hp_members = tuple(
        item for item in block.members if item.key == "HP"
    )
    if len(hp_members) != 1 or hp_members[0] is not member:
        raise HealingAffinitiesCompileError(
            "verified creature requires one exact HP member"
        )
    name_members = tuple(
        item for item in block.members if item.key == "Name"
    )
    if (
        len(name_members) != 1
        or type(name_members[0]) is not RawSourceMember
        or type(name_members[0].value) is not str
    ):
        raise HealingAffinitiesCompileError(
            "verified creature requires one exact Name member"
        )
    _require_trimmed_text(
        name_members[0].value,
        "verified creature Name",
    )
    return _VerifiedHPStat(
        source_value=source.raw_value,
    )


def _source_identity(
    source: VerifiedSourceSelection,
) -> SerializedObject:
    return source.receipt.as_serialized()


def _compile_fast_healing(
    source: _VerifiedHPStat,
    verified_source: VerifiedSourceSelection,
    providers: tuple[VerifiedRuleReceipt, ...],
    *,
    rule: RuleReference,
    ordinal: int,
    annotation_text: str,
    amount_text: str,
    qualifier: str | None,
) -> CompiledHealingAbility | None:
    amount = _positive_source_integer(amount_text)
    if amount is None:
        return None

    condition: dict[str, Any] = {"kind": "always"}
    reference_page: int | None = None
    deferred_mechanics: tuple[str, ...] = ()
    if qualifier == "page 359":
        reference_page = 359
    elif qualifier is not None:
        typed_condition = _FAST_HEALING_CONDITIONS.get(qualifier)
        if typed_condition is None:
            return None
        condition = dict(typed_condition)
        deferred_mechanics = ("world-state-predicate",)

    mechanic: dict[str, Any] = {
        "type": FAST_HEALING_MECHANIC_TYPE,
        "amount": amount,
        "condition": condition,
        "automatic": True,
        "actionCost": None,
        "roll": None,
        "timing": "owner-start-turn-choice-order-group",
        "maximumHPCap": True,
        "deathGuard": False,
        "sourceText": source.source_value,
        "annotationText": annotation_text,
        "source": _source_identity(verified_source),
        "rules": {
            provider.rule_id: provider.as_serialized()
            for provider in providers[:4]
        },
    }
    if reference_page is not None:
        mechanic["referencePage"] = reference_page

    return CompiledHealingAbility(
        ordinal=ordinal,
        ability_id="fast-healing",
        ability_name="Fast Healing",
        ability=AbilityCompilerPatch(
            mechanic=mechanic,
            rule=rule,
            deferred_mechanics=deferred_mechanics,
        ),
    )


def _compile_void_healing(
    source: _VerifiedHPStat,
    verified_source: VerifiedSourceSelection,
    providers: tuple[VerifiedRuleReceipt, ...],
    *,
    rule: RuleReference,
    ordinal: int,
    annotation_text: str,
    page_text: str | None,
) -> CompiledHealingAbility:
    mechanic: dict[str, Any] = {
        "type": VOID_HEALING_MECHANIC_TYPE,
        "mode": "void",
        "damagePolicy": {
            "vitality": "eligible-for-damage",
            "void": "typed-damage-immunity",
        },
        "healingPolicy": {
            "healing-vitality": "not-healed",
            "void-effect-that-heals-undead": "healed",
            "untyped-regain-hit-points": "not-blocked-by-this-rule",
        },
        "notEquivalentToUndeadTrait": True,
        "sourceText": source.source_value,
        "annotationText": annotation_text,
        "source": _source_identity(verified_source),
        "rules": {
            provider.rule_id: provider.as_serialized()
            for provider in providers[4:]
        },
    }
    if page_text is not None:
        mechanic["referencePage"] = 360

    return CompiledHealingAbility(
        ordinal=ordinal,
        ability_id="void-healing",
        ability_name="Void Healing",
        ability=AbilityCompilerPatch(
            mechanic=mechanic,
            rule=rule,
        ),
    )


def _compile_healing_affinities(
    authority: object,
    source: object,
    providers: object,
    provider_validator: Callable[
        [
            SourceAuthorityAdapter,
            VerifiedSourceSelection,
            object,
        ],
        tuple[VerifiedRuleReceipt, ...],
    ],
    fast_healing_rule: RuleReference,
    void_healing_rule: RuleReference,
    /,
) -> HealingAffinitiesPatch | None:
    """Compile one verifier-issued Core MC1 ``HP`` member."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "compile_healing_affinities requires an exact "
            "SourceAuthorityAdapter"
        )
    normalized = _verified_hp_source(authority, source)
    if normalized is None:
        return None
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "compile_healing_affinities requires verifier-issued source"
        )
    verified_providers = provider_validator(
        authority,
        source,
        providers,
    )
    if (
        len(normalized.source_value) > MAX_HP_SOURCE_BYTES
        or len(normalized.source_value.encode("utf-8"))
        > MAX_HP_SOURCE_BYTES
    ):
        return None

    parenthesized = _PARENTHESIZED_FAST_HEALING_RE.fullmatch(
        normalized.source_value
    )
    if parenthesized is not None:
        hit_points = _positive_source_integer(
            parenthesized.group("hit_points")
        )
        if hit_points is None:
            return None
        ability = _compile_fast_healing(
            normalized,
            source,
            verified_providers,
            rule=fast_healing_rule,
            ordinal=0,
            annotation_text=(
                f"fast healing {parenthesized.group('amount')}"
            ),
            amount_text=parenthesized.group("amount"),
            qualifier=None,
        )
        if ability is None:
            return None
        return HealingAffinitiesPatch(
            stat_value=hit_points,
            abilities=(ability,),
            unconsumed_annotations=(),
            source=source,
            providers=verified_providers,
        )

    tokens = _split_top_level_commas(normalized.source_value)
    if tokens is None or len(tokens) < 2:
        return None
    hit_points = _positive_source_integer(tokens[0])
    if hit_points is None:
        return None

    abilities_and_annotations: list[
        CompiledHealingAbility | PreservedHPAnnotation
    ] = []
    seen_mechanics: set[str] = set()
    for ordinal, token in enumerate(tokens[1:]):
        fast_match = _FAST_HEALING_RE.fullmatch(token)
        if fast_match is not None:
            if FAST_HEALING_MECHANIC_TYPE in seen_mechanics:
                raise HealingAffinitiesCompileError(
                    "duplicate fast healing annotation"
                )
            ability = _compile_fast_healing(
                normalized,
                source,
                verified_providers,
                rule=fast_healing_rule,
                ordinal=ordinal,
                annotation_text=token,
                amount_text=fast_match.group("amount"),
                qualifier=fast_match.group("qualifier"),
            )
            if ability is None:
                return None
            abilities_and_annotations.append(ability)
            seen_mechanics.add(FAST_HEALING_MECHANIC_TYPE)
            continue

        void_match = _VOID_HEALING_RE.fullmatch(token)
        if void_match is not None:
            if VOID_HEALING_MECHANIC_TYPE in seen_mechanics:
                raise HealingAffinitiesCompileError(
                    "duplicate void healing annotation"
                )
            abilities_and_annotations.append(
                _compile_void_healing(
                    normalized,
                    source,
                    verified_providers,
                    rule=void_healing_rule,
                    ordinal=ordinal,
                    annotation_text=token,
                    page_text=void_match.group("page"),
                )
            )
            seen_mechanics.add(VOID_HEALING_MECHANIC_TYPE)
            continue

        if _RESERVED_HEALING_PHRASE_RE.search(token) is not None:
            return None
        abilities_and_annotations.append(
            PreservedHPAnnotation(ordinal=ordinal, raw=token)
        )

    abilities = tuple(
        item
        for item in abilities_and_annotations
        if type(item) is CompiledHealingAbility
    )
    if not abilities:
        return None
    unconsumed = tuple(
        item
        for item in abilities_and_annotations
        if type(item) is PreservedHPAnnotation
    )
    return HealingAffinitiesPatch(
        stat_value=hit_points,
        abilities=abilities,
        unconsumed_annotations=unconsumed,
        source=source,
        providers=verified_providers,
    )


def _bind_public_compiler(
    unbound_compiler: Callable[
        [
            object,
            object,
            object,
            Callable[
                [
                    SourceAuthorityAdapter,
                    VerifiedSourceSelection,
                    object,
                ],
                tuple[VerifiedRuleReceipt, ...],
            ],
            RuleReference,
            RuleReference,
        ],
        HealingAffinitiesPatch | None,
    ],
    provider_validator: Callable[
        [
            SourceAuthorityAdapter,
            VerifiedSourceSelection,
            object,
        ],
        tuple[VerifiedRuleReceipt, ...],
    ],
    fast_healing_rule: RuleReference,
    void_healing_rule: RuleReference,
) -> Callable[
    [object, object, object],
    HealingAffinitiesPatch | None,
]:
    reviewed_compiler = unbound_compiler
    reviewed_validator = provider_validator
    reviewed_fast_healing_rule = RuleReference(
        source_id=fast_healing_rule.source_id,
        locator=fast_healing_rule.locator,
    )
    reviewed_void_healing_rule = RuleReference(
        source_id=void_healing_rule.source_id,
        locator=void_healing_rule.locator,
    )

    def compile_healing_affinities(
        authority: object,
        source: object,
        providers: object,
        /,
    ) -> HealingAffinitiesPatch | None:
        return reviewed_compiler(
            authority,
            source,
            providers,
            reviewed_validator,
            reviewed_fast_healing_rule,
            reviewed_void_healing_rule,
        )

    return compile_healing_affinities


compile_healing_affinities = _bind_public_compiler(
    _compile_healing_affinities,
    _validated_providers,
    FAST_HEALING_GLOSSARY_RULE,
    VOID_HEALING_GLOSSARY_RULE,
)


def link_healing_affinities(
    authority: object,
    source: object,
    providers: object,
    /,
) -> HealingAffinitiesPatch | None:
    """Select exactly one verified HP member from a creature carrier."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "link_healing_affinities requires an exact "
            "SourceAuthorityAdapter"
        )
    raw_stats = _verified_creature_block(authority, source)
    if raw_stats is None:
        return None
    hp_members = tuple(
        (ordinal, member)
        for ordinal, member in enumerate(raw_stats.members)
        if member.key == "HP"
    )
    if len(hp_members) > 1:
        raise HealingAffinitiesCompileError(
            "raw source contains duplicate HP members"
        )
    if not hp_members or type(hp_members[0][1].value) is not str:
        return None
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "link_healing_affinities requires verifier-issued source"
        )
    hp_ordinal, hp_member = hp_members[0]
    selection = source.carrier.select(
        (RawMemberStep(hp_member.key, hp_ordinal),)
    )
    return compile_healing_affinities(
        authority,
        selection,
        providers,
    )


def _raw_source_values_are_exact(
    actual: object,
    expected: object,
) -> bool:
    """Compare reviewed raw values without accepting virtual/subclass shapes."""

    if type(actual) is not type(expected):
        return False
    if type(expected) is RawSourceObject:
        if len(actual.members) != len(expected.members):
            return False
        for actual_member, expected_member in zip(
            actual.members,
            expected.members,
            strict=True,
        ):
            if (
                type(actual_member) is not RawSourceMember
                or type(expected_member) is not RawSourceMember
                or type(actual_member.key) is not str
                or actual_member.key != expected_member.key
                or not _raw_source_values_are_exact(
                    actual_member.value,
                    expected_member.value,
                )
            ):
                return False
        return True
    if type(expected) is RawSourceArray:
        return (
            len(actual.items) == len(expected.items)
            and all(
                _raw_source_values_are_exact(
                    actual_item,
                    expected_item,
                )
                for actual_item, expected_item in zip(
                    actual.items,
                    expected.items,
                    strict=True,
                )
            )
        )
    return actual == expected


def _deferred_source_match(
    raw_member: RawSourceMember,
) -> tuple[str, _DeferredSourceSpec] | None:
    if type(raw_member) is not RawSourceMember:
        return None
    if (
        type(raw_member.key) is not str
        or raw_member.key not in _DEFERRED_RAW_KEYS
    ):
        return None
    for identity, spec in _DEFERRED_SOURCE_SPECS.items():
        raw_key, source_text = identity
        if raw_member.key != raw_key:
            continue
        expected_value = _DEFERRED_EXACT_SOURCE_VALUES[identity]
        if _raw_source_values_are_exact(
            raw_member.value,
            expected_value,
        ):
            return source_text, spec
    return None


def _link_deferred_healing_records(
    authority: object,
    source: object,
    providers: object,
    provider_validator: Callable[
        [
            SourceAuthorityAdapter,
            VerifiedSourceSelection,
            object,
        ],
        tuple[VerifiedRuleReceipt, ...],
    ],
    /,
) -> tuple[DeferredHealingRecord, ...]:
    """Classify exact local records while retaining them as unsupported."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "link_deferred_healing_records requires an exact "
            "SourceAuthorityAdapter"
        )
    raw_abilities = _verified_creature_block(authority, source)
    if raw_abilities is None:
        return ()
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "link_deferred_healing_records requires verifier-issued source"
        )
    verified_providers = provider_validator(
        authority,
        source,
        providers,
    )

    for raw_key in _DEFERRED_RAW_KEYS:
        if sum(
            member.key == raw_key for member in raw_abilities.members
        ) > 1:
            raise HealingAffinitiesCompileError(
                f"raw source contains duplicate {raw_key!r} members"
            )

    records: list[DeferredHealingRecord] = []
    for ordinal, raw_member in enumerate(raw_abilities.members):
        if raw_member.key not in _DEFERRED_RAW_KEYS:
            continue
        matched = _deferred_source_match(raw_member)
        if matched is None:
            continue
        description, spec = matched
        selection = source.carrier.select(
            (RawMemberStep(raw_member.key, ordinal),)
        )
        authority.validate_selection(selection)
        records.append(
            DeferredHealingRecord(
                ordinal=ordinal,
                raw_key=raw_member.key,
                source_label=raw_member.key.removeprefix("!."),
                family=spec.family,
                classification=spec.classification,
                source_text=description,
                source=selection,
                providers=verified_providers,
                deferred_mechanics=spec.deferred_mechanics,
            )
        )

    return tuple(records)


def _bind_deferred_linker(
    unbound_linker: Callable[
        [
            object,
            object,
            object,
            Callable[
                [
                    SourceAuthorityAdapter,
                    VerifiedSourceSelection,
                    object,
                ],
                tuple[VerifiedRuleReceipt, ...],
            ],
        ],
        tuple[DeferredHealingRecord, ...],
    ],
    provider_validator: Callable[
        [
            SourceAuthorityAdapter,
            VerifiedSourceSelection,
            object,
        ],
        tuple[VerifiedRuleReceipt, ...],
    ],
) -> Callable[
    [object, object, object],
    tuple[DeferredHealingRecord, ...],
]:
    reviewed_linker = unbound_linker
    reviewed_validator = provider_validator

    def link_deferred_healing_records(
        authority: object,
        source: object,
        providers: object,
        /,
    ) -> tuple[DeferredHealingRecord, ...]:
        return reviewed_linker(
            authority,
            source,
            providers,
            reviewed_validator,
        )

    return link_deferred_healing_records


link_deferred_healing_records = _bind_deferred_linker(
    _link_deferred_healing_records,
    _validated_providers,
)


__all__ = [
    "CompiledHealingAbility",
    "DeferredHealingRecord",
    "FAMILY_ID",
    "FAST_HEALING_GLOSSARY_REQUIREMENT",
    "FAST_HEALING_MECHANIC_TYPE",
    "FAST_HEALING_PLAYER_REQUIREMENT",
    "HealingAffinitiesAddressabilityError",
    "HealingAffinitiesCompileError",
    "HealingAffinitiesPatch",
    "HIT_POINTS_REQUIREMENT",
    "ENERGY_DAMAGE_REQUIREMENT",
    "APPLY_IWR_REQUIREMENT",
    "PreservedHPAnnotation",
    "RULE_REQUIREMENTS",
    "START_TURN_REQUIREMENT",
    "VOID_HEALING_MECHANIC_TYPE",
    "VOID_HEALING_GLOSSARY_REQUIREMENT",
    "compile_healing_affinities",
    "link_deferred_healing_records",
    "link_healing_affinities",
]

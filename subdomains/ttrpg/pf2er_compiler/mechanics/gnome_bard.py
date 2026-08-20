"""Compile the Gnome Bard's exact dance and damage reactions.

Runtime state and suspension remain owned by ``encounter``.  This module
admits only the reviewed Monster Core carrier and exposes closed normalized
mechanics plus small pure helpers shared by that runtime.
"""

from __future__ import annotations

from typing import Any

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceArray,
    RawSourceObject,
    RuleReference,
)


SOURCE = RuleReference("core-mc1", "172.2")
DEGREE_RULE = RuleReference("core-pc1", "401.4")
SAVING_THROW_RULE = RuleReference("core-pc1", "404.1")
INCAPACITATION_RULE = RuleReference("core-pc1", "452.1")
TURN_START_RULE = RuleReference("core-pc1", "435.8")
DAMAGE_RESISTANCE_RULE = RuleReference("core-pc1", "408.7")
TELEPORTATION_RULE = RuleReference("core-pc1", "452.1")

DO_A_JIG_ABILITY_ID = "do-a-jig"
DO_A_JIG_MECHANIC_TYPE = "next-turn-action-loss-saving-throw"
DO_A_JIG_TRAITS = (
    "auditory",
    "incapacitation",
    "occult",
    "mental",
)
DO_A_JIG_DC = 19
DO_A_JIG_RANGE_FEET = 30

GNOMISH_SHIFT_ABILITY_ID = "gnomish-shift"
GNOMISH_SHIFT_MECHANIC_TYPE = (
    "triggering-damage-resistance-teleport-reaction"
)
GNOMISH_SHIFT_TRAITS = ("primal", "teleportation")
GNOMISH_SHIFT_TRIGGER = "The gnome bard would take damage."
GNOMISH_SHIFT_DESCRIPTION = (
    "The gnome bard gains resistance 2 to the triggering damage and "
    "teleports to an adjacent space."
)
GNOMISH_SHIFT_RESISTANCE = 2

_DO_A_JIG_INTRODUCTION = (
    "The gnome bard plays a ditty that inspires dance. One creature within "
    "30 feet must make a Will saving throw DC 19."
)
_DO_A_JIG_SUCCESS = "Success The target is unaffected."
_DO_A_JIG_FAILURE = (
    "Failure The target must waste 1 action on its next turn dancing."
)
_DO_A_JIG_CRITICAL_FAILURE = (
    "Critical Failure The target must waste 2 actions on its next turn "
    "dancing."
)
DO_A_JIG_DESCRIPTION = "\n\n".join(
    (
        _DO_A_JIG_INTRODUCTION,
        _DO_A_JIG_SUCCESS,
        _DO_A_JIG_FAILURE,
        _DO_A_JIG_CRITICAL_FAILURE,
    )
)


def _rule(reference: RuleReference) -> dict[str, str]:
    return {
        "sourceId": reference.source_id,
        "locator": reference.locator,
    }


def _exact_do_a_jig_description(value: object) -> bool:
    return (
        type(value) is RawSourceObject
        and tuple(
            (member.key, member.value)
            for member in value.members
        )
        == (
            ("~.p", _DO_A_JIG_INTRODUCTION),
            ("~.p", _DO_A_JIG_SUCCESS),
            ("~.p", _DO_A_JIG_FAILURE),
            ("~.p", _DO_A_JIG_CRITICAL_FAILURE),
        )
    )


def compile_do_a_jig(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact Gnome Bard action-loss activity."""

    value = source.raw_member.value
    if (
        source.source_id != SOURCE.source_id
        or source.locator != SOURCE.locator
        or source.creature_name != "Gnome Bard"
        or source.source_label != "Do a Jig"
        or source.raw_member.key != "!.Do a Jig"
        or source.kind != "activity"
        or source.action_cost != 1
        or source.traits != DO_A_JIG_TRAITS
        or source.trigger
        or source.description != DO_A_JIG_DESCRIPTION
        or type(value) is not RawSourceObject
        or tuple(member.key for member in value.members)
        != ("Action", "Traits", "Description")
        or value.members[0].value != "single"
        or type(value.members[1].value) is not RawSourceArray
        or value.members[1].value.items != DO_A_JIG_TRAITS
        or not _exact_do_a_jig_description(value.members[2].value)
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": DO_A_JIG_MECHANIC_TYPE,
            "targeting": {
                "count": 1,
                "relation": "creature",
                "sideNeutral": True,
                "rangeFeet": DO_A_JIG_RANGE_FEET,
                "requiresLineOfEffect": True,
                "requiresDetection": True,
                "targetingFlatCheck": True,
            },
            "savingThrow": {
                "type": "will",
                "dc": DO_A_JIG_DC,
                "basic": False,
            },
            "outcomes": {
                "criticalSuccess": {"unaffected": True},
                "success": {"unaffected": True},
                "failure": {
                    "actionsLost": 1,
                    "timing": "target-next-turn",
                    "activity": "dancing",
                },
                "criticalFailure": {
                    "actionsLost": 2,
                    "timing": "target-next-turn",
                    "activity": "dancing",
                },
            },
            "immunities": {
                "traits": ["auditory", "mental"],
                "outcome": "unaffected",
            },
            "rules": {
                "savingThrow": _rule(SAVING_THROW_RULE),
                "degreeOfSuccess": _rule(DEGREE_RULE),
                "incapacitation": _rule(INCAPACITATION_RULE),
                "turnStart": _rule(TURN_START_RULE),
            },
        },
        rule=SOURCE,
    )


def compile_gnomish_shift(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact Gnome Bard pre-damage reaction."""

    value = source.raw_member.value
    if (
        source.source_id != SOURCE.source_id
        or source.locator != SOURCE.locator
        or source.creature_name != "Gnome Bard"
        or source.source_label != "Gnomish Shift"
        or source.raw_member.key != "!.Gnomish Shift"
        or source.kind != "reaction"
        or source.action_cost != "reaction"
        or source.traits != GNOMISH_SHIFT_TRAITS
        or source.trigger != GNOMISH_SHIFT_TRIGGER
        or source.description != GNOMISH_SHIFT_DESCRIPTION
        or type(value) is not RawSourceObject
        or tuple(member.key for member in value.members)
        != ("Action", "Traits", "Trigger", "Description")
        or value.members[0].value != "reaction"
        or type(value.members[1].value) is not RawSourceArray
        or value.members[1].value.items != GNOMISH_SHIFT_TRAITS
        or value.members[2].value != GNOMISH_SHIFT_TRIGGER
        or value.members[3].value != GNOMISH_SHIFT_DESCRIPTION
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": GNOMISH_SHIFT_MECHANIC_TYPE,
            "trigger": {
                "timing": "before-damage",
                "condition": "owner-would-take-positive-damage",
            },
            "resistance": {
                "value": GNOMISH_SHIFT_RESISTANCE,
                "scope": "triggering-damage",
                "combination": "ordinary-resistance-maximum",
            },
            "teleport": {
                "destination": "controller-selected-adjacent-space",
                "distanceFeet": 5,
                "requiresLegalDestination": True,
                "movementTraits": [],
            },
            "runtimeBoundary": {
                "supportedProducerActions": ["Strike", "CastSpell"],
                "unsupportedProducerPolicy": "fail-closed",
            },
            "rules": {
                "resistance": _rule(DAMAGE_RESISTANCE_RULE),
                "teleportation": _rule(TELEPORTATION_RULE),
            },
        },
        rule=SOURCE,
    )


def action_loss_for_degree(degree: str) -> int:
    """Return the exact next-turn loss for one adjusted save degree."""

    if degree in {"critical-success", "success"}:
        return 0
    if degree == "failure":
        return 1
    if degree == "critical-failure":
        return 2
    raise ValueError("Do a Jig degree is invalid")


def apply_gnomish_shift_resistance(
    after_weakness: int,
    ordinary_resistance: int,
) -> tuple[int, int]:
    """Apply the non-stacking resistance 2 to one triggering damage type."""

    if (
        type(after_weakness) is not int
        or after_weakness < 0
        or type(ordinary_resistance) is not int
        or ordinary_resistance < 0
    ):
        raise ValueError("Gnomish Shift resistance inputs are invalid")
    effective = max(ordinary_resistance, GNOMISH_SHIFT_RESISTANCE)
    after = max(0, after_weakness - effective)
    return after, min(after_weakness, effective)


FRAGMENT = MechanicFamilyFragment(
    family_id="gnome-bard",
    mechanic_types=(
        DO_A_JIG_MECHANIC_TYPE,
        GNOMISH_SHIFT_MECHANIC_TYPE,
    ),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id=DO_A_JIG_ABILITY_ID,
            mechanic_type=DO_A_JIG_MECHANIC_TYPE,
            compiler=compile_do_a_jig,
        ),
        AbilityCompilerRegistration(
            compiler_id=GNOMISH_SHIFT_ABILITY_ID,
            mechanic_type=GNOMISH_SHIFT_MECHANIC_TYPE,
            compiler=compile_gnomish_shift,
        ),
    ),
)


__all__ = [
    "DAMAGE_RESISTANCE_RULE",
    "DEGREE_RULE",
    "DO_A_JIG_ABILITY_ID",
    "DO_A_JIG_DC",
    "DO_A_JIG_DESCRIPTION",
    "DO_A_JIG_MECHANIC_TYPE",
    "DO_A_JIG_RANGE_FEET",
    "DO_A_JIG_TRAITS",
    "FRAGMENT",
    "GNOMISH_SHIFT_ABILITY_ID",
    "GNOMISH_SHIFT_DESCRIPTION",
    "GNOMISH_SHIFT_MECHANIC_TYPE",
    "GNOMISH_SHIFT_RESISTANCE",
    "GNOMISH_SHIFT_TRAITS",
    "GNOMISH_SHIFT_TRIGGER",
    "INCAPACITATION_RULE",
    "SAVING_THROW_RULE",
    "SOURCE",
    "TELEPORTATION_RULE",
    "TURN_START_RULE",
    "action_loss_for_degree",
    "apply_gnomish_shift_resistance",
    "compile_do_a_jig",
    "compile_gnomish_shift",
]

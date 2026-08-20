"""Compile and adjudicate the Catfolk Pouncer's Cat's Luck reaction.

The compiler admits only the exact Monster Core ability.  Runtime helpers in
this module remain pure: encounter suspension, resource state, and event
ordering stay with the central encounter transition owner.
"""

from __future__ import annotations

from copy import deepcopy
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


CAT_LUCK_ABILITY_ID = "cat-s-luck"
CAT_LUCK_LABEL = "Cat's Luck"
CAT_LUCK_MECHANIC_TYPE = "failed-reflex-save-fortune-reroll"
CAT_LUCK_SOURCE = RuleReference("core-mc1", "52.2")
FORTUNE_RULE = RuleReference("core-pc1", "400.1")
DAILY_PREPARATIONS_RULE = RuleReference("core-pc1", "439.7")
SAVING_THROW_RULE = RuleReference("core-pc1", "404.1")

CAT_LUCK_TRIGGER = (
    "The catfolk pouncer fails or critically fails a Reflex saving throw"
)
CAT_LUCK_DESCRIPTION = (
    "Frequency once per day; Effect Reroll that saving throw and take the "
    "better result."
)

_DEGREES = (
    "critical-failure",
    "failure",
    "success",
    "critical-success",
)


def _rule(reference: RuleReference) -> dict[str, str]:
    return {
        "sourceId": reference.source_id,
        "locator": reference.locator,
    }


def compile_cats_luck(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact Catfolk Pouncer reaction source grammar."""

    if (
        source.source_label != CAT_LUCK_LABEL
        or source.source_id != CAT_LUCK_SOURCE.source_id
        or source.locator != CAT_LUCK_SOURCE.locator
        or source.creature_name != "Catfolk Pouncer"
        or source.kind != "reaction"
        or source.action_cost != "reaction"
        or source.traits != ("fortune",)
        or source.trigger != CAT_LUCK_TRIGGER
        or source.description != CAT_LUCK_DESCRIPTION
        or source.raw_member.key != "!.Cat's Luck"
    ):
        return None
    value = source.raw_member.value
    if (
        type(value) is not RawSourceObject
        or tuple(member.key for member in value.members)
        != ("Action", "Traits", "Trigger", "Description")
        or value.members[0].value != "reaction"
        or type(value.members[1].value) is not RawSourceArray
        or value.members[1].value.items != ("fortune",)
        or value.members[2].value != CAT_LUCK_TRIGGER
        or value.members[3].value != CAT_LUCK_DESCRIPTION
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": CAT_LUCK_MECHANIC_TYPE,
            "trigger": {
                "savingThrow": "reflex",
                "degrees": ["failure", "critical-failure"],
                "owner": "saving-creature",
                "timing": "after-failed-save-before-effects",
            },
            "reroll": {
                "die": "d20",
                "mandatoryWhenUsed": True,
                "resolution": "better-result",
                "hostOwned": True,
            },
            "frequency": {
                "maximum": 1,
                "period": "day",
                "resetsAt": "daily-preparations",
                "rule": _rule(DAILY_PREPARATIONS_RULE),
            },
            "fortune": {
                "maximumEffectsOnRoll": 1,
                "rule": _rule(FORTUNE_RULE),
            },
            "rules": {
                "savingThrow": _rule(SAVING_THROW_RULE),
                "fortune": _rule(FORTUNE_RULE),
                "dailyPreparations": _rule(DAILY_PREPARATIONS_RULE),
            },
        },
        rule=CAT_LUCK_SOURCE,
    )


def cat_luck_trigger_applies(
    *,
    reaction_available: bool,
    daily_uses_remaining: int,
    save_type: str,
    degree: str,
    fortune_effects_on_roll: int = 0,
) -> bool:
    """Return whether the exact post-save reaction window opens."""

    return (
        reaction_available is True
        and daily_uses_remaining > 0
        and save_type == "reflex"
        and degree in {"failure", "critical-failure"}
        and fortune_effects_on_roll == 0
    )


def _degree(total: int, dc: int, die_roll: int) -> str:
    if total >= dc + 10:
        index = 3
    elif total >= dc:
        index = 2
    elif total <= dc - 10:
        index = 0
    else:
        index = 1
    if die_roll == 20:
        index = min(3, index + 1)
    elif die_roll == 1:
        index = max(0, index - 1)
    return _DEGREES[index]


def rerolled_reflex_save(
    original: dict[str, Any],
    reroll: int,
) -> dict[str, Any]:
    """Recompute one exact Reflex save with the same DC and modifiers."""

    if (
        not isinstance(original, dict)
        or original.get("type") != "reflex"
        or isinstance(reroll, bool)
        or not isinstance(reroll, int)
        or not 1 <= reroll <= 20
    ):
        raise ValueError("Cat's Luck requires an exact Reflex d20 reroll")
    original_roll = original.get("roll")
    total = original.get("total")
    dc = original.get("dc")
    if (
        isinstance(original_roll, bool)
        or not isinstance(original_roll, int)
        or not 1 <= original_roll <= 20
        or isinstance(total, bool)
        or not isinstance(total, int)
        or isinstance(dc, bool)
        or not isinstance(dc, int)
    ):
        raise ValueError("Cat's Luck original saving throw is invalid")
    result = deepcopy(original)
    result["roll"] = reroll
    result["total"] = total - original_roll + reroll
    unadjusted = _degree(result["total"], dc, reroll)
    result["unadjustedDegree"] = unadjusted
    incapacitation = result.get("incapacitationAdjustment")
    degree = unadjusted
    if isinstance(incapacitation, dict) and incapacitation.get("applied") is True:
        degree = _DEGREES[min(3, _DEGREES.index(degree) + 1)]
    result["degree"] = degree
    if result.get("basic") is True:
        result["damageOutcome"] = {
            "critical-success": "none",
            "success": "half",
            "failure": "full",
            "critical-failure": "double",
        }[degree]
    return result


def better_reflex_save(
    original: dict[str, Any],
    rerolled: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Choose the authored better result without allowing a worse reroll."""

    original_roll = original.get("roll")
    reroll = rerolled.get("roll")
    if (
        isinstance(original_roll, bool)
        or not isinstance(original_roll, int)
        or isinstance(reroll, bool)
        or not isinstance(reroll, int)
    ):
        raise ValueError("Cat's Luck saving throws have invalid d20 results")
    if reroll > original_roll:
        return "reroll", deepcopy(rerolled)
    return "original", deepcopy(original)


FRAGMENT = MechanicFamilyFragment(
    family_id="cats-luck",
    mechanic_types=(CAT_LUCK_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="cats-luck",
            mechanic_type=CAT_LUCK_MECHANIC_TYPE,
            compiler=compile_cats_luck,
        ),
    ),
)


__all__ = [
    "CAT_LUCK_ABILITY_ID",
    "CAT_LUCK_MECHANIC_TYPE",
    "CAT_LUCK_SOURCE",
    "DAILY_PREPARATIONS_RULE",
    "FORTUNE_RULE",
    "FRAGMENT",
    "SAVING_THROW_RULE",
    "better_reflex_save",
    "cat_luck_trigger_applies",
    "compile_cats_luck",
    "rerolled_reflex_save",
]

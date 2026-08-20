"""Compile the Goblin War Chanter's exact Goblin Song activity.

The Monster Core ability delegates its check traits and restrictions to a
sung Performance check.  The normalized mechanic therefore retains both the
complete creature-authored outcomes and the exact Player Core Performance,
trait, degree-of-success, and duration authorities used by runtime.
"""

from __future__ import annotations

from typing import Any

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceObject,
    RuleReference,
)


SOURCE_ID = "core-mc1"
WAR_CHANTER_LOCATOR = "175.3"
ABILITY_ID = "goblin-song"
MECHANIC_TYPE = "multi-target-performance-will-status-penalty"

PERFORMANCE_RULE = {"sourceId": "core-pc1", "locator": "243.4"}
TRAIT_RULE = {"sourceId": "core-pc1", "locator": "452.1"}
DEGREE_RULE = {"sourceId": "core-pc1", "locator": "401.4"}
DURATION_RULE = {"sourceId": "core-pc1", "locator": "426.2"}

_INTRODUCTION = (
    "The war chanter sings annoying goblin songs, distracting foes with "
    "silly and repetitive lyrics. The chanter attempts a Performance check "
    "against the Will DCs of up to two enemies within 30 feet. This has the "
    "usual traits and restrictions for a Performance check."
)
_CRITICAL_SUCCESS = (
    "Critical Success The target takes a –1 status penalty to Perception "
    "checks and Will saves for 1 minute."
)
_SUCCESS = (
    "Success As critical success, but the target is affected for only 1 round."
)
_CRITICAL_FAILURE = (
    "Critical Failure The target is temporarily immune to Goblin Song for "
    "1 hour."
)
_DESCRIPTION = "\n\n".join(
    (
        _INTRODUCTION,
        _CRITICAL_SUCCESS,
        _SUCCESS,
        _CRITICAL_FAILURE,
    )
)
_ACTION_TRAITS = ("auditory", "concentrate", "linguistic")


def _exact_description(value: object) -> bool:
    if type(value) is not RawSourceObject:
        return False
    return tuple(
        (member.key, member.value)
        for member in value.members
    ) == (
        ("~.p", _INTRODUCTION),
        ("~.p", _CRITICAL_SUCCESS),
        ("~.p", _SUCCESS),
        ("~.p", _CRITICAL_FAILURE),
    )


def _mechanic() -> dict[str, Any]:
    return {
        "type": MECHANIC_TYPE,
        "check": {
            "skill": "performance",
            "sharedRoll": True,
            "defense": "will-dc",
        },
        "targeting": {
            "maximumTargets": 2,
            "minimumTargets": 1,
            "rangeFeet": 30,
            "relation": "other-creature",
            "sideNeutral": True,
            "requiresLineOfEffect": True,
            "requiresDetection": True,
        },
        "eligibility": {
            "auditory": {
                "targetMustHear": True,
                "sourceMustProduceSound": True,
            },
            "linguistic": {
                "targetMustUnderstandUsedLanguage": True,
                "selection": "shared-language",
            },
        },
        "outcomes": {
            "criticalSuccess": {
                "statusPenalty": {
                    "type": "status",
                    "value": -1,
                    "appliesTo": [
                        "perception-checks",
                        "will-saves",
                    ],
                },
                "duration": {"rounds": 10, "source": "1 minute"},
            },
            "success": {
                "statusPenalty": {
                    "type": "status",
                    "value": -1,
                    "appliesTo": [
                        "perception-checks",
                        "will-saves",
                    ],
                },
                "duration": {"rounds": 1, "source": "1 round"},
            },
            "failure": {"unaffected": True},
            "criticalFailure": {
                "temporaryImmunity": {
                    "abilityId": ABILITY_ID,
                    "scope": "all-sources",
                },
                "duration": {"rounds": 600, "source": "1 hour"},
            },
        },
        "rules": {
            "performance": PERFORMANCE_RULE,
            "traits": TRAIT_RULE,
            "degreeOfSuccess": DEGREE_RULE,
            "duration": DURATION_RULE,
        },
    }


def compile_goblin_song(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact authenticated War Chanter source member."""

    raw_value = source.raw_member.value
    description = (
        raw_value.members[1].value
        if type(raw_value) is RawSourceObject
        and len(raw_value.members) == 2
        else None
    )
    if (
        source.source_id != SOURCE_ID
        or source.locator != WAR_CHANTER_LOCATOR
        or source.creature_name != "Goblin War Chanter"
        or source.source_label != "Goblin Song"
        or source.raw_member.key != "!.Goblin Song"
        or source.kind != "activity"
        or source.action_cost != 1
        or source.traits
        or source.trigger
        or source.description != _DESCRIPTION
        or type(raw_value) is not RawSourceObject
        or tuple(member.key for member in raw_value.members)
        != ("Action", "Description")
        or raw_value.members[0].value != "single"
        or not _exact_description(description)
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=_mechanic(),
        rule=RuleReference(SOURCE_ID, WAR_CHANTER_LOCATOR),
        traits=_ACTION_TRAITS,
    )


FRAGMENT = MechanicFamilyFragment(
    family_id=ABILITY_ID,
    mechanic_types=(MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id=ABILITY_ID,
            mechanic_type=MECHANIC_TYPE,
            compiler=compile_goblin_song,
        ),
    ),
)


__all__ = [
    "ABILITY_ID",
    "DEGREE_RULE",
    "DURATION_RULE",
    "FRAGMENT",
    "MECHANIC_TYPE",
    "PERFORMANCE_RULE",
    "TRAIT_RULE",
    "compile_goblin_song",
]

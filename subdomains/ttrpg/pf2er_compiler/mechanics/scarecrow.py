"""Compile the Scarecrow's exact Leer aura and Baleful Glow toggle."""

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


SOURCE_ID = "core-mc1"
LOCATOR = "297.1"
CREATURE_NAME = "Scarecrow"
BALEFUL_GLOW_ABILITY_ID = "baleful-glow"
BALEFUL_GLOW_MECHANIC_TYPE = "scarecrow-baleful-glow"
LEER_ABILITY_ID = "scarecrow-s-leer"
LEER_MECHANIC_TYPE = "scarecrow-leer"

CREATURE_RULE = {"sourceId": SOURCE_ID, "locator": LOCATOR}
TRAIT_RULE = {"sourceId": "core-pc1", "locator": "452.1"}
EMANATION_RULE = {"sourceId": "core-pc1", "locator": "428.4"}
LIGHT_RULE = {"sourceId": "core-pc1", "locator": "432.2"}
BRIGHT_LIGHT_RULE = {"sourceId": "core-pc1", "locator": "432.3"}
OFF_GUARD_RULE = {"sourceId": "core-pc1", "locator": "445.2"}
DURATION_RULE = {"sourceId": "core-pc1", "locator": "426.2"}
WILL_RULE = {"sourceId": "core-pc1", "locator": "404.1"}
FRIGHTENED_RULE = {"sourceId": "core-pc1", "locator": "444.4"}
FASCINATED_RULE = {"sourceId": "core-pc1", "locator": "443.9"}
AVERT_GAZE_RULE = {"sourceId": "core-pc1", "locator": "419.1"}

# Monster Core does not give "avian" a trait. These exact source addresses are
# the reviewed current-core carriers whose source presentation identifies them
# as birds or avian creatures. Adding another carrier is an explicit source
# review, never a name substring heuristic.
AVIAN_CREATURE_SOURCE_ADDRESSES = (
    ("core-mc1", "137.2"),  # Eagle
    ("core-mc1", "137.4"),  # Giant Eagle
    ("core-mc1", "325.1"),  # Tengu Sneak
)

LEER_PARAGRAPHS = (
    "40 feet. The scarecrow's eyes flicker with an unnerving glow. A creature "
    "can't reduce its frightened condition below 1 as long as it's in the "
    "aura. When a creature enters or starts its turn in the aura, it must "
    "attempt a DC 18 Will save. Birds and other avian creatures take a -2 "
    "circumstance penalty to this save.",
    "<b>Critical Success</b> The creature is unaffected and is then "
    "temporarily immune for 24 hours.",
    "<b>Success</b> The creature is frightened 1.",
    "<b>Failure</b> The creature is frightened 2 and is fascinated by the "
    "scarecrow until the end of its next turn.",
    "<b>Critical Failure</b> As failure, but frightened 3.",
)
LEER_DESCRIPTION = "\n\n".join(LEER_PARAGRAPHS)
LEER_TRAITS = ("aura", "emotion", "fear", "mental", "occult", "visual")

BALEFUL_GLOW_DESCRIPTION = (
    "The scarecrow's head bursts into ghostly, heatless flame that sheds "
    "bright light in a 20-foot emanation (and dim light to the next 20 "
    "feet). If the scarecrow uses this ability on the first round of "
    "combat, any creature that has not acted yet is startled, becoming "
    "off-guard against the scarecrow for 1 round. The scarecrow can "
    "suppress the light by using this action again."
)
BALEFUL_GLOW_TRAITS = ("concentrate", "mental", "light", "occult")


def _leer_mechanic() -> dict[str, Any]:
    return {
        "type": LEER_MECHANIC_TYPE,
        "geometry": {
            "type": "emanation",
            "radiusFeet": 40,
            "requiresLineOfSight": True,
            "sourceAffected": False,
        },
        "triggers": ["entry", "start-turn"],
        "requiresTargetToLook": True,
        "savingThrow": {"type": "will", "dc": 18, "hostOwned": True},
        "avianCircumstancePenalty": {
            "value": -2,
            "sourceAddresses": [
                {"sourceId": source_id, "locator": locator}
                for source_id, locator in AVIAN_CREATURE_SOURCE_ADDRESSES
            ],
        },
        "frightenedFloor": 1,
        "outcomes": {
            "critical-success": {
                "unaffected": True,
                "temporaryImmunity": {"value": 24, "unit": "hours"},
            },
            "success": {"frightened": 1},
            "failure": {"frightened": 2, "fascinated": True},
            "critical-failure": {"frightened": 3, "fascinated": True},
        },
        "rules": {
            "ability": CREATURE_RULE,
            "traits": TRAIT_RULE,
            "emanation": EMANATION_RULE,
            "savingThrow": WILL_RULE,
            "frightened": FRIGHTENED_RULE,
            "fascinated": FASCINATED_RULE,
            "avertGaze": AVERT_GAZE_RULE,
            "duration": DURATION_RULE,
        },
    }


def compile_scarecrows_leer(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the duplicate-preserving Monster Core 297.1 passive."""

    value = source.raw_member.value
    if (
        source.source_id != SOURCE_ID
        or source.locator != LOCATOR
        or source.creature_name != CREATURE_NAME
        or source.source_label != "Scarecrow's Leer"
        or source.raw_member.key != "!.Scarecrow's Leer"
        or source.kind != "passive"
        or source.action_cost is not None
        or source.traits != LEER_TRAITS
        or source.trigger
        or source.description != LEER_DESCRIPTION
        or type(value) is not RawSourceObject
        or tuple(member.key for member in value.members)
        != ("Traits", "Description")
        or type(value.members[0].value) is not RawSourceArray
        or value.members[0].value.items != LEER_TRAITS
        or type(value.members[1].value) is not RawSourceObject
        or tuple(member.key for member in value.members[1].value.members)
        != ("~.p", "~.p", "~.p", "~.p", "~.p")
        or tuple(
            member.value for member in value.members[1].value.members
        )
        != LEER_PARAGRAPHS
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=_leer_mechanic(),
        rule=RuleReference(SOURCE_ID, LOCATOR),
    )


def _mechanic() -> dict[str, Any]:
    return {
        "type": BALEFUL_GLOW_MECHANIC_TYPE,
        "toggle": {
            "activeInitially": False,
            "suppressWithSameAction": True,
        },
        "illumination": {
            "area": {
                "type": "emanation",
                "brightRadiusFeet": 20,
                "dimOuterRadiusFeet": 40,
            },
            # A pale blue spectral flame: conspicuously colored but not hot.
            "displayRgb": [130, 205, 255],
        },
        "firstRound": {
            "targets": "creatures-that-have-not-acted",
            "condition": "off-guard",
            "relation": "against-source-only",
            "durationRounds": 1,
            "immuneTrait": "mental",
        },
        "rules": {
            "ability": CREATURE_RULE,
            "traits": TRAIT_RULE,
            "emanation": EMANATION_RULE,
            "light": LIGHT_RULE,
            "brightLight": BRIGHT_LIGHT_RULE,
            "offGuard": OFF_GUARD_RULE,
            "duration": DURATION_RULE,
        },
    }


def compile_baleful_glow(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the reviewed Monster Core 297.1 action object."""

    value = source.raw_member.value
    if (
        source.source_id != SOURCE_ID
        or source.locator != LOCATOR
        or source.creature_name != CREATURE_NAME
        or source.source_label != "Baleful Glow"
        or source.raw_member.key != "!.Baleful Glow"
        or source.kind != "activity"
        or source.action_cost != 1
        or source.traits != BALEFUL_GLOW_TRAITS
        or source.trigger
        or source.description != BALEFUL_GLOW_DESCRIPTION
        or type(value) is not RawSourceObject
        or tuple(member.key for member in value.members)
        != ("Action", "Traits", "Description")
        or value.members[0].value != "single"
        or type(value.members[1].value) is not RawSourceArray
        or value.members[1].value.items != BALEFUL_GLOW_TRAITS
        or value.members[2].value != BALEFUL_GLOW_DESCRIPTION
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=_mechanic(),
        rule=RuleReference(SOURCE_ID, LOCATOR),
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="scarecrow",
    mechanic_types=(LEER_MECHANIC_TYPE, BALEFUL_GLOW_MECHANIC_TYPE),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id=LEER_ABILITY_ID,
            mechanic_type=LEER_MECHANIC_TYPE,
            compiler=compile_scarecrows_leer,
        ),
        AbilityCompilerRegistration(
            compiler_id=BALEFUL_GLOW_ABILITY_ID,
            mechanic_type=BALEFUL_GLOW_MECHANIC_TYPE,
            compiler=compile_baleful_glow,
        ),
    ),
)


__all__ = [
    "BALEFUL_GLOW_ABILITY_ID",
    "BALEFUL_GLOW_TRAITS",
    "BALEFUL_GLOW_MECHANIC_TYPE",
    "CREATURE_RULE",
    "CREATURE_NAME",
    "FRAGMENT",
    "LEER_ABILITY_ID",
    "LEER_DESCRIPTION",
    "LEER_MECHANIC_TYPE",
    "LEER_TRAITS",
    "LOCATOR",
    "SOURCE_ID",
    "compile_baleful_glow",
    "compile_scarecrows_leer",
]

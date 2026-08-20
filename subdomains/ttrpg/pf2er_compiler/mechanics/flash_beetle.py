"""Compile the Flash Beetle's linked light aura and flash activity.

The two Monster Core abilities form one fail-closed mechanic family: the
passive aura is the light source that Light Flash consumes for 24 hours.
Runtime state and encounter event ordering remain with the central encounter
and illumination owners.
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


SOURCE_ID = "core-mc1"
LOCATOR = "42.4"
CREATURE_NAME = "Flash Beetle"

AURA_ABILITY_ID = "luminescent-aura"
AURA_MECHANIC_TYPE = "flash-beetle-luminescent-aura"
FLASH_ABILITY_ID = "light-flash"
FLASH_MECHANIC_TYPE = "flash-beetle-light-flash"

CREATURE_RULE = {"sourceId": SOURCE_ID, "locator": LOCATOR}
AURA_TRAIT_RULE = {"sourceId": "core-pc1", "locator": "452.1"}
LIGHT_TRAIT_RULE = {"sourceId": "core-pc1", "locator": "452.1"}
CONCENTRATE_TRAIT_RULE = {"sourceId": "core-pc1", "locator": "452.1"}
EMANATION_RULE = {"sourceId": "core-pc1", "locator": "428.4"}
LIGHT_RULE = {"sourceId": "core-pc1", "locator": "432.2"}
BRIGHT_LIGHT_RULE = {"sourceId": "core-pc1", "locator": "432.3"}
SAVING_THROW_RULE = {"sourceId": "core-pc1", "locator": "404.1"}
DURATION_RULE = {"sourceId": "core-pc1", "locator": "426.2"}
DAZZLED_RULE = {"sourceId": "core-pc1", "locator": "442.12"}
CONCEALED_RULE = {"sourceId": "core-pc1", "locator": "434.6"}

AURA_DESCRIPTION = (
    "(aura, light) 10 feet. The flash beetle’s bioluminescent organs fill "
    "the area with bright light."
)
FLASH_DESCRIPTION = (
    "The flash beetle creates a brilliant flash of light. All creatures in "
    "its luminescent aura must succeed at a DC 17 Fortitude save or be "
    "dazzled for 1 minute. The flash beetle’s glow then goes out, disabling "
    "its aura for 24 hours, during which time it cannot use Light Flash."
)


def _aura_mechanic() -> dict[str, Any]:
    return {
        "type": AURA_MECHANIC_TYPE,
        "area": {
            "type": "emanation",
            "radiusFeet": 10,
            "sideNeutral": True,
        },
        "illumination": {
            "emission": {
                "brightRadiusFeet": 10,
                "dimOuterRadiusFeet": 20,
            },
            "displayRgb": [165, 255, 96],
        },
        "activation": {
            "activeInitially": True,
            "disabledByAbilityId": FLASH_ABILITY_ID,
            "lockoutSeconds": 86400,
            "encounterReset": False,
        },
        "rules": {
            "ability": CREATURE_RULE,
            "auraTrait": AURA_TRAIT_RULE,
            "lightTrait": LIGHT_TRAIT_RULE,
            "emanation": EMANATION_RULE,
            "light": LIGHT_RULE,
            "brightLight": BRIGHT_LIGHT_RULE,
        },
    }


def _flash_mechanic() -> dict[str, Any]:
    return {
        "type": FLASH_MECHANIC_TYPE,
        "area": {
            "type": "emanation",
            "radiusFeet": 10,
            "sideNeutral": True,
            "includeSource": "actor-choice",
            "requiresLineOfEffect": True,
        },
        "savingThrow": {
            "type": "fortitude",
            "dc": 17,
            "hostOwned": True,
            "independentPerTarget": True,
        },
        "outcomes": {
            "criticalSuccess": {"unaffected": True},
            "success": {"unaffected": True},
            "failure": {
                "condition": "dazzled",
                "duration": {"rounds": 10, "source": "1 minute"},
            },
            "criticalFailure": {
                "condition": "dazzled",
                "duration": {"rounds": 10, "source": "1 minute"},
            },
        },
        "lockout": {
            "durationSeconds": 86400,
            "source": "24 hours",
            "disablesAbilityIds": [
                AURA_ABILITY_ID,
                FLASH_ABILITY_ID,
            ],
            "encounterReset": False,
        },
        "rules": {
            "ability": CREATURE_RULE,
            "concentrateTrait": CONCENTRATE_TRAIT_RULE,
            "lightTrait": LIGHT_TRAIT_RULE,
            "emanation": EMANATION_RULE,
            "savingThrow": SAVING_THROW_RULE,
            "duration": DURATION_RULE,
            "dazzled": DAZZLED_RULE,
            "concealed": CONCEALED_RULE,
        },
    }


def compile_luminescent_aura(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact passive scalar at Monster Core 42.4."""

    if (
        source.source_id != SOURCE_ID
        or source.locator != LOCATOR
        or source.creature_name != CREATURE_NAME
        or source.source_label != "Luminescent Aura"
        or source.raw_member.key != "!.Luminescent Aura"
        or source.kind != "passive"
        or source.action_cost is not None
        or source.traits
        or source.trigger
        or source.description != AURA_DESCRIPTION
        or source.raw_member.value != AURA_DESCRIPTION
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=_aura_mechanic(),
        rule=RuleReference(SOURCE_ID, LOCATOR),
        traits=("aura", "light"),
    )


def compile_light_flash(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact one-action Light Flash source object."""

    value = source.raw_member.value
    if (
        source.source_id != SOURCE_ID
        or source.locator != LOCATOR
        or source.creature_name != CREATURE_NAME
        or source.source_label != "Light Flash"
        or source.raw_member.key != "!.Light Flash"
        or source.kind != "activity"
        or source.action_cost != 1
        or source.traits != ("concentrate", "light")
        or source.trigger
        or source.description != FLASH_DESCRIPTION
        or type(value) is not RawSourceObject
        or tuple(member.key for member in value.members)
        != ("Action", "Traits", "Description")
        or value.members[0].value != "single"
        or type(value.members[1].value) is not RawSourceArray
        or value.members[1].value.items != ("concentrate", "light")
        or value.members[2].value != FLASH_DESCRIPTION
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=_flash_mechanic(),
        rule=RuleReference(SOURCE_ID, LOCATOR),
    )


def _fail_closed(ability: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(ability)
    result["supported"] = False
    result.pop("mechanic", None)
    result.pop("rule", None)
    deferred = [
        item
        for item in result.get("deferredMechanics", [])
        if item != "source-integrity:flash-beetle-linked-abilities"
    ]
    deferred.append("source-integrity:flash-beetle-linked-abilities")
    result["deferredMechanics"] = deferred
    return result


def link_flash_beetle_abilities(
    abilities: list[dict[str, Any]],
    *,
    source_id: str,
    locator: str,
    creature_name: str,
) -> list[dict[str, Any]]:
    """Require the exact aura/flash pair and emit mutual link identities."""

    if (
        source_id != SOURCE_ID
        or locator != LOCATOR
        or creature_name != CREATURE_NAME
    ):
        return abilities
    by_id = {
        ability.get("id"): ability
        for ability in abilities
        if isinstance(ability, dict)
    }
    aura = by_id.get(AURA_ABILITY_ID)
    flash = by_id.get(FLASH_ABILITY_ID)
    valid = (
        len(by_id) == len(abilities)
        and isinstance(aura, dict)
        and isinstance(flash, dict)
        and aura.get("supported") is True
        and flash.get("supported") is True
        and aura.get("mechanic", {}).get("type") == AURA_MECHANIC_TYPE
        and flash.get("mechanic", {}).get("type") == FLASH_MECHANIC_TYPE
        and aura.get("rule") == CREATURE_RULE
        and flash.get("rule") == CREATURE_RULE
    )
    result = deepcopy(abilities)
    for index, ability in enumerate(result):
        ability_id = ability.get("id")
        if ability_id not in {AURA_ABILITY_ID, FLASH_ABILITY_ID}:
            continue
        if not valid:
            result[index] = _fail_closed(ability)
            continue
        mechanic = deepcopy(ability["mechanic"])
        mechanic["linkedAbilityId"] = (
            FLASH_ABILITY_ID
            if ability_id == AURA_ABILITY_ID
            else AURA_ABILITY_ID
        )
        ability["mechanic"] = mechanic
    return result


def ability_pair(
    definition: dict[str, Any],
    /,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return the authenticated compiled pair for one creature definition."""

    source = definition.get("source")
    if (
        not isinstance(source, dict)
        or source.get("sourceId") != SOURCE_ID
        or source.get("locator") != LOCATOR
        or definition.get("name") != CREATURE_NAME
    ):
        return None
    abilities = definition.get("abilities")
    if not isinstance(abilities, list):
        raise ValueError("Flash Beetle definition abilities are invalid")
    indexes = definition.get("candidateIndexes")
    if indexes is None:
        by_id = {
            ability.get("id"): ability
            for ability in abilities
            if isinstance(ability, dict)
        }
        aura = by_id.get(AURA_ABILITY_ID)
        flash = by_id.get(FLASH_ABILITY_ID)
    else:
        positions = (
            indexes.get("abilities")
            if isinstance(indexes, dict)
            else None
        )
        if not isinstance(positions, dict):
            raise ValueError(
                "Flash Beetle definition ability index is invalid"
            )

        def indexed_ability(ability_id: str) -> dict[str, Any] | None:
            position = positions.get(ability_id)
            if position is None:
                return None
            if (
                isinstance(position, bool)
                or not isinstance(position, int)
                or not 0 <= position < len(abilities)
                or not isinstance(abilities[position], dict)
                or abilities[position].get("id") != ability_id
            ):
                raise ValueError(
                    "Flash Beetle definition ability index is invalid"
                )
            return abilities[position]

        aura = indexed_ability(AURA_ABILITY_ID)
        flash = indexed_ability(FLASH_ABILITY_ID)
    if explicitly_unsupported_pair(definition, aura, flash):
        return None
    if (
        not isinstance(aura, dict)
        or not isinstance(flash, dict)
        or aura.get("supported") is not True
        or flash.get("supported") is not True
        or aura.get("rule") != CREATURE_RULE
        or flash.get("rule") != CREATURE_RULE
        or aura.get("mechanic", {}).get("type") != AURA_MECHANIC_TYPE
        or flash.get("mechanic", {}).get("type") != FLASH_MECHANIC_TYPE
        or aura["mechanic"].get("linkedAbilityId") != FLASH_ABILITY_ID
        or flash["mechanic"].get("linkedAbilityId") != AURA_ABILITY_ID
    ):
        raise ValueError("Flash Beetle linked ability pair is invalid")
    return aura, flash


def explicitly_unsupported_pair(
    definition: dict[str, Any],
    aura: dict[str, Any] | None,
    flash: dict[str, Any] | None,
    /,
) -> bool:
    """Recognize an authenticated source-only historical ability pair."""

    source = definition.get("source")
    unsupported = definition.get("unsupportedMechanics")
    return (
        isinstance(source, dict)
        and source.get("sourceId") == SOURCE_ID
        and source.get("locator") == LOCATOR
        and definition.get("name") == CREATURE_NAME
        and isinstance(aura, dict)
        and isinstance(flash, dict)
        and aura.get("id") == AURA_ABILITY_ID
        and flash.get("id") == FLASH_ABILITY_ID
        and aura.get("supported") is False
        and flash.get("supported") is False
        and "mechanic" not in aura
        and "mechanic" not in flash
        and "rule" not in aura
        and "rule" not in flash
        and isinstance(unsupported, list)
        and all(isinstance(item, str) for item in unsupported)
        and {"Luminescent Aura", "Light Flash"}.issubset(unsupported)
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="flash-beetle",
    mechanic_types=(AURA_MECHANIC_TYPE, FLASH_MECHANIC_TYPE),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id=AURA_ABILITY_ID,
            mechanic_type=AURA_MECHANIC_TYPE,
            compiler=compile_luminescent_aura,
        ),
        AbilityCompilerRegistration(
            compiler_id=FLASH_ABILITY_ID,
            mechanic_type=FLASH_MECHANIC_TYPE,
            compiler=compile_light_flash,
        ),
    ),
)


__all__ = [
    "AURA_ABILITY_ID",
    "AURA_MECHANIC_TYPE",
    "CREATURE_RULE",
    "DAZZLED_RULE",
    "DURATION_RULE",
    "FLASH_ABILITY_ID",
    "FLASH_MECHANIC_TYPE",
    "FRAGMENT",
    "LOCATOR",
    "SOURCE_ID",
    "ability_pair",
    "compile_light_flash",
    "compile_luminescent_aura",
    "explicitly_unsupported_pair",
    "link_flash_beetle_abilities",
]

"""Exact compiler and bounded runtime contract for the Core MC1 Warg.

The source-wide Swallow Whole compiler remains authoritative for the linked
ability, feeder, and provider dossier.  This module owns only the Warg's
ordinary ability projection plus the executable reaction and containment
shape admitted by the current encounter engine.
"""

from __future__ import annotations

from collections.abc import Mapping
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
LOCATOR = "341.2"
CREATURE_NAME = "Warg"

AVENGING_BITE_ABILITY_ID = "avenging-bite"
AVENGING_BITE_MECHANIC_TYPE = "ally-attacked-jaws-strike-reaction"
AVENGING_BITE_TRIGGER = (
    "A creature within reach of the warg's jaws attacks one of the warg's "
    "allies."
)
AVENGING_BITE_DESCRIPTION = (
    "The warg makes a jaws Strike against the triggering creature."
)

SWALLOW_WHOLE_ABILITY_ID = "swallow-whole"
SWALLOW_WHOLE_MECHANIC_TYPE = "swallow-whole-containment"
SWALLOW_WHOLE_SOURCE_TEXT = (
    "Small, 1d6+2 bludgeoning, Rupture 9 (page 360)"
)
SWALLOW_WHOLE_PROVIDER = {"sourceId": "core-mc1", "locator": "358.2"}
SWALLOW_WHOLE_ACTION_COST = 1
SWALLOW_WHOLE_MAXIMUM_SIZE = "small"
SWALLOW_WHOLE_MAXIMUM_SIZE_RANK = 1
SWALLOW_WHOLE_ESCAPE_DC = 18
SWALLOW_WHOLE_RUPTURE_THRESHOLD = 9
SWALLOW_WHOLE_DAMAGE = {
    "dice": {"count": 1, "sides": 6},
    "modifier": 2,
    "type": "bludgeoning",
}
SWALLOW_WHOLE_RUPTURE_DAMAGE_TYPES = ("piercing", "slashing")
SWALLOW_WHOLE_RUNTIME_BOUNDARIES = (
    "breath-and-suffocation",
    "light-bulk-internal-weapon-boundary",
    "death-corpse-extraction",
)


def _exact_object(
    source: AbilitySource,
    *,
    raw_key: str,
    pairs: tuple[tuple[str, object], ...],
) -> bool:
    value = source.raw_member.value
    return (
        source.raw_member.key == raw_key
        and type(value) is RawSourceObject
        and len(value.members) == len(pairs)
        and all(
            member.key == key and member.value == expected
            for member, (key, expected)
            in zip(value.members, pairs, strict=True)
        )
    )


def compile_avenging_bite(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the Warg's exact pre-roll jaws reaction."""

    if (
        source.source_id != SOURCE_ID
        or source.locator != LOCATOR
        or source.creature_name != CREATURE_NAME
        or source.source_label != "Avenging Bite"
        or source.kind != "reaction"
        or source.action_cost != "reaction"
        or source.traits != ()
        or source.trigger != AVENGING_BITE_TRIGGER
        or source.description != AVENGING_BITE_DESCRIPTION
        or not _exact_object(
            source,
            raw_key="!.Avenging Bite",
            pairs=(
                ("Action", "reaction"),
                ("Trigger", AVENGING_BITE_TRIGGER),
                ("Description", AVENGING_BITE_DESCRIPTION),
            ),
        )
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": AVENGING_BITE_MECHANIC_TYPE,
            "strikeId": "jaws",
            "target": "triggering-creature",
            "trigger": {
                "event": "ally-targeted-by-attack",
                "relation": "within-jaws-strike-reach",
                "timing": "before-triggering-attack-roll",
                "allyExcludesReactor": True,
            },
            "multipleAttackPenalty": {
                "applies": False,
                "counts": False,
            },
        },
        rule=RuleReference(SOURCE_ID, LOCATOR),
    )


def compile_warg_swallow_whole(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Project the exact Warg ability; authority linking occurs separately."""

    if (
        source.source_id != SOURCE_ID
        or source.locator != LOCATOR
        or source.creature_name != CREATURE_NAME
        or source.source_label != "Swallow Whole"
        or source.kind != "activity"
        or source.action_cost != 1
        or source.traits != ("attack",)
        or source.trigger
        or source.description != SWALLOW_WHOLE_SOURCE_TEXT
        or not _exact_object(
            source,
            raw_key="!.Swallow Whole",
            pairs=(
                ("Action", "single"),
                ("Traits", RawSourceArray(("attack",))),
                ("Description", SWALLOW_WHOLE_SOURCE_TEXT),
            ),
        )
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": SWALLOW_WHOLE_MECHANIC_TYPE,
            "feederStrikeId": "jaws",
            "requiredHeldCondition": ["grabbed", "restrained"],
            "maximumTargetSize": SWALLOW_WHOLE_MAXIMUM_SIZE,
            "maximumTargetSizeRank": SWALLOW_WHOLE_MAXIMUM_SIZE_RANK,
            "check": {
                "skill": "athletics",
                "defense": "reflex",
                "traits": ["attack"],
            },
            "damage": deepcopy(SWALLOW_WHOLE_DAMAGE),
            "escapeDC": SWALLOW_WHOLE_ESCAPE_DC,
            "ruptureThreshold": SWALLOW_WHOLE_RUPTURE_THRESHOLD,
            "ruptureDamageTypes": list(
                SWALLOW_WHOLE_RUPTURE_DAMAGE_TYPES
            ),
            "runtimeBoundaries": list(
                SWALLOW_WHOLE_RUNTIME_BOUNDARIES
            ),
            "provider": deepcopy(SWALLOW_WHOLE_PROVIDER),
        },
        rule=RuleReference(SOURCE_ID, LOCATOR),
        deferred_mechanics=SWALLOW_WHOLE_RUNTIME_BOUNDARIES,
    )


def bind_swallow_whole_compilation(
    patch: AbilityCompilerPatch,
    compilation: Mapping[str, Any],
    /,
) -> AbilityCompilerPatch:
    """Bind the Warg patch to the generic authority-backed compilation."""

    if (
        not isinstance(patch, AbilityCompilerPatch)
        or patch.mechanic_type != SWALLOW_WHOLE_MECHANIC_TYPE
        or not isinstance(compilation, Mapping)
        or compilation.get("familyId") != "swallow-whole"
        or compilation.get("consumerRuleId") != "swallow-whole:warg"
        or compilation.get("feederRuleId")
        != "swallow-feeder:warg:jaws"
        or compilation.get("provider") != SWALLOW_WHOLE_PROVIDER
        or str(compilation.get("maximumTargetSize") or "").casefold()
        != SWALLOW_WHOLE_MAXIMUM_SIZE
        or compilation.get("damage") != [SWALLOW_WHOLE_DAMAGE]
        or compilation.get("escapeDC") != SWALLOW_WHOLE_ESCAPE_DC
        or compilation.get("ruptureThreshold")
        != SWALLOW_WHOLE_RUPTURE_THRESHOLD
        or compilation.get("genericRuntimeReady") is not False
        or compilation.get("runtimeActivation")
        != "bounded-warg-containment"
        or patch.mechanic.get("maximumTargetSize")
        != str(compilation.get("maximumTargetSize") or "").casefold()
        or patch.mechanic.get("damage")
        != compilation.get("damage")[0]
        or patch.mechanic.get("escapeDC")
        != compilation.get("escapeDC")
        or patch.mechanic.get("ruptureThreshold")
        != compilation.get("ruptureThreshold")
        or patch.mechanic.get("provider")
        != compilation.get("provider")
    ):
        raise ValueError(
            "Warg Swallow Whole registry and authority compilations disagree"
        )
    mechanic = patch.as_ability_update()["mechanic"]
    mechanic.update(
        {
            "maximumTargetSize": str(
                compilation["maximumTargetSize"]
            ).casefold(),
            "damage": deepcopy(compilation["damage"][0]),
            "escapeDC": compilation["escapeDC"],
            "ruptureThreshold": compilation["ruptureThreshold"],
            "provider": deepcopy(compilation["provider"]),
            "authorityCompilation": deepcopy(dict(compilation)),
        }
    )
    return AbilityCompilerPatch(
        mechanic=mechanic,
        rule=patch.rule,
        traits=patch.traits,
        deferred_mechanics=patch.deferred_mechanics,
    )


def swallow_whole_runtime_spec(
    definition: Mapping[str, Any],
    ability: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Validate and return the authority-linked runtime mechanic."""

    compilation = definition.get("swallowWholeCompilation")
    mechanic = ability.get("mechanic")
    if (
        definition.get("id") != f"{SOURCE_ID}:{LOCATOR}"
        or definition.get("name") != CREATURE_NAME
        or not isinstance(compilation, Mapping)
        or compilation.get("familyId") != "swallow-whole"
        or compilation.get("consumerRuleId") != "swallow-whole:warg"
        or compilation.get("feederRuleId")
        != "swallow-feeder:warg:jaws"
        or compilation.get("genericRuntimeReady") is not False
        or compilation.get("runtimeActivation")
        != "bounded-warg-containment"
        or ability.get("id") != SWALLOW_WHOLE_ABILITY_ID
        or ability.get("supported") is not True
        or ability.get("kind") != "activity"
        or ability.get("actionCost") != SWALLOW_WHOLE_ACTION_COST
        or ability.get("traits") != ["attack"]
        or ability.get("rule")
        != {"sourceId": SOURCE_ID, "locator": LOCATOR}
        or not isinstance(mechanic, Mapping)
        or mechanic.get("type") != SWALLOW_WHOLE_MECHANIC_TYPE
        or mechanic.get("feederStrikeId") != "strike:jaws:melee"
        or mechanic.get("requiredHeldCondition")
        != ["grabbed", "restrained"]
        or mechanic.get("maximumTargetSizeRank")
        != SWALLOW_WHOLE_MAXIMUM_SIZE_RANK
        or mechanic.get("ruptureDamageTypes")
        != list(SWALLOW_WHOLE_RUPTURE_DAMAGE_TYPES)
        or mechanic.get("runtimeBoundaries")
        != list(SWALLOW_WHOLE_RUNTIME_BOUNDARIES)
        or mechanic.get("authorityCompilation") != compilation
        or mechanic.get("maximumTargetSize")
        != str(compilation.get("maximumTargetSize") or "").casefold()
        or mechanic.get("damage")
        != (
            compilation.get("damage", [None])[0]
            if isinstance(compilation.get("damage"), list)
            and len(compilation.get("damage")) == 1
            else None
        )
        or mechanic.get("escapeDC") != compilation.get("escapeDC")
        or mechanic.get("ruptureThreshold")
        != compilation.get("ruptureThreshold")
        or mechanic.get("provider") != compilation.get("provider")
    ):
        raise ValueError(
            "Warg Swallow Whole runtime compilation is invalid"
        )
    return deepcopy(dict(mechanic))


def containment_effects(
    state: dict[str, Any],
    *,
    source_id: str | None = None,
    target_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return exact active Warg Swallow Whole containment records."""

    effects = state.get("effects", [])
    if not isinstance(effects, list):
        raise ValueError("Swallow Whole encounter state is invalid")
    swallowed_effects = [
        effect
        for effect in effects
        if isinstance(effect, dict)
        and isinstance(effect.get("containment"), dict)
        and effect["containment"].get("kind") == "swallowed"
    ]
    if not swallowed_effects:
        return []
    participants = state.get("participants")
    definitions = state.get("definitions")
    if (
        not isinstance(participants, list)
        or any(not isinstance(item, dict) for item in participants)
        or not isinstance(definitions, dict)
    ):
        raise ValueError("Swallow Whole encounter state is invalid")
    participants_by_id = {
        str(participant.get("id") or ""): participant
        for participant in participants
    }
    participant_ids = {
        participant_id
        for participant_id in participants_by_id
        if participant_id
    }
    result = []
    for effect in swallowed_effects:
        containment = effect.get("containment")
        source = str(effect.get("sourceParticipantId") or "")
        target = str(effect.get("targetParticipantId") or "")
        source_participant = participants_by_id.get(source)
        source_definition_id = (
            str(source_participant.get("creatureId") or "")
            if isinstance(source_participant, dict)
            else ""
        )
        source_definition = definitions.get(source_definition_id)
        if (
            effect.get("kind") != "grapple"
            or not source
            or not target
            or source == target
            or source not in participant_ids
            or target not in participant_ids
            or source_definition_id != "core-mc1:341.2"
            or not isinstance(source_definition, dict)
            or source_definition.get("name") != CREATURE_NAME
            or not isinstance(source_definition.get("source"), dict)
            or source_definition["source"].get("sourceId") != SOURCE_ID
            or source_definition["source"].get("locator") != LOCATOR
            or effect.get("condition") != "grabbed"
            or effect.get("escape")
            != {
                "dc": SWALLOW_WHOLE_ESCAPE_DC,
                "basis": "swallow-whole-athletics-dc",
                "rule": {"sourceId": "core-pc1", "locator": "416.6"},
            }
            or "expires" in effect
            or containment
            != {
                "kind": "swallowed",
                "sourceAbilityId": SWALLOW_WHOLE_ABILITY_ID,
                "source": {"sourceId": SOURCE_ID, "locator": LOCATOR},
                "provider": SWALLOW_WHOLE_PROVIDER,
                "damage": SWALLOW_WHOLE_DAMAGE,
                "escapeDC": SWALLOW_WHOLE_ESCAPE_DC,
                "ruptureThreshold": SWALLOW_WHOLE_RUPTURE_THRESHOLD,
                "ruptureDamageTypes": list(
                    SWALLOW_WHOLE_RUPTURE_DAMAGE_TYPES
                ),
                "slowedValue": 1,
                "breathTracking": "deferred",
                "lightBulkWeaponBoundary": "fail-closed",
                "internalAttackBoundary": "unarmed-and-supported-spells-only",
            }
        ):
            raise ValueError("Swallow Whole containment effect is invalid")
        if source_id is not None and source != source_id:
            continue
        if target_id is not None and target != target_id:
            continue
        result.append(effect)
    return result


def containment_summary(effect: dict[str, Any]) -> dict[str, Any]:
    containment = effect["containment"]
    return {
        "effectId": str(effect["id"]),
        "sourceParticipantId": str(effect["sourceParticipantId"]),
        "targetParticipantId": str(effect["targetParticipantId"]),
        "condition": "grabbed",
        "slowedValue": 1,
        "escapeDC": SWALLOW_WHOLE_ESCAPE_DC,
        "ruptureThreshold": SWALLOW_WHOLE_RUPTURE_THRESHOLD,
        "damage": deepcopy(SWALLOW_WHOLE_DAMAGE),
        "source": deepcopy(containment["source"]),
        "provider": deepcopy(containment["provider"]),
    }


FRAGMENT = MechanicFamilyFragment(
    family_id="warg",
    mechanic_types=(
        AVENGING_BITE_MECHANIC_TYPE,
        SWALLOW_WHOLE_MECHANIC_TYPE,
    ),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id=AVENGING_BITE_ABILITY_ID,
            mechanic_type=AVENGING_BITE_MECHANIC_TYPE,
            compiler=compile_avenging_bite,
        ),
        AbilityCompilerRegistration(
            compiler_id=SWALLOW_WHOLE_ABILITY_ID,
            mechanic_type=SWALLOW_WHOLE_MECHANIC_TYPE,
            compiler=compile_warg_swallow_whole,
        ),
    ),
)


__all__ = [
    "AVENGING_BITE_ABILITY_ID",
    "AVENGING_BITE_MECHANIC_TYPE",
    "AVENGING_BITE_TRIGGER",
    "FRAGMENT",
    "LOCATOR",
    "SOURCE_ID",
    "SWALLOW_WHOLE_ABILITY_ID",
    "SWALLOW_WHOLE_ACTION_COST",
    "SWALLOW_WHOLE_DAMAGE",
    "SWALLOW_WHOLE_ESCAPE_DC",
    "SWALLOW_WHOLE_MAXIMUM_SIZE_RANK",
    "SWALLOW_WHOLE_MECHANIC_TYPE",
    "SWALLOW_WHOLE_PROVIDER",
    "SWALLOW_WHOLE_RUPTURE_DAMAGE_TYPES",
    "SWALLOW_WHOLE_RUPTURE_THRESHOLD",
    "bind_swallow_whole_compilation",
    "compile_avenging_bite",
    "compile_warg_swallow_whole",
    "containment_effects",
    "containment_summary",
    "swallow_whole_runtime_spec",
]

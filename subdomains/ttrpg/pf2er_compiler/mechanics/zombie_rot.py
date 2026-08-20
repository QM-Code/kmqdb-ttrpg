"""Source-exact Zombie Rot compilation and bounded exposure mechanics.

Zombie Rot is a disease with one-day stages.  The encounter engine has no
campaign clock, cure service, or creature-transformation authority, so this
module deliberately admits only the part that can resolve honestly inside a
bounded fight: a successful Strike hit can force the initial save and
create stage 1 or stage 2 state.  The complete authored progression remains
compiled data with explicit runtime deferrals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from types import MappingProxyType
from typing import Any

from ..errors import EngineInputError
from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceArray,
    RawSourceObject,
    RuleReference,
)
from .source_authority import raw_source_sha256


MECHANIC_TYPE = "disease-affliction"
ABILITY_ID = "zombie-rot"
AFFLICTION_KEY = "disease:zombie-rot"
SOURCE = {"sourceId": "core-mc1", "locator": "356.6"}

DISEASE_GLOSSARY_RULE = {"sourceId": "core-mc1", "locator": "358.2"}
STRIKE_RULE = {"sourceId": "core-pc1", "locator": "418.4"}
AFFLICTIONS_RULE = {"sourceId": "core-pc1", "locator": "430.1"}
INITIAL_SAVE_RULE = {"sourceId": "core-pc1", "locator": "430.4"}
STAGE_PROGRESSION_RULE = {"sourceId": "core-pc1", "locator": "430.7"}
STAGE_EFFECT_RULE = {"sourceId": "core-pc1", "locator": "430.8"}
MULTIPLE_EXPOSURES_RULE = {"sourceId": "core-pc1", "locator": "430.9"}
DEATH_RULE = {"sourceId": "core-pc1", "locator": "411.5"}

SOURCE_DESCRIPTION = (
    "An infected creature can't heal damage it takes from zombie rot until "
    "it has been cured of the disease; <b>Stage 1</b> carrier with no ill "
    "effect (1 day); <b>Stage 2</b> 1d6 void damage (1 day); "
    "<b>Stage 3</b> 1d6 void damage (1 day); <b>Stage 4</b> 1d6 void damage "
    "(1 day); <b>Stage 5</b> dead, rising as a plague zombie immediately"
)
SOURCE_TRAITS = ("disease", "divine", "void")
SOURCE_SAVE = "DC 18 Fortitude"

# Current cache review receipt.  These paths are duplicate-preserving raw
# member ordinals, not inferred semantic labels.  The carrier digest covers
# the complete current Plague Zombie block; the selection digest covers the
# exact Zombie Rot ordered object.
SOURCE_RECEIPT = MappingProxyType(
    {
        "sourceId": "core-mc1",
        "locator": "356.6",
        "sectionId": "core-mc1:zombie",
        "targetPath": (("Zombie", 1),),
        "carrierPath": (("^.creature", 4),),
        "selectionPath": (("!.Zombie Rot", 26),),
        "carrierBlockSha256": (
            "e66ffe5a2e0894c0c8a3b6e1a352c7aaaa5d8c39c847a76db5223b858e5f0d5d"
        ),
        "selectionSha256": (
            "155b958d21b310f60d647730dba6be2167a9c37a776572a2b3304eb5aeeab8c0"
        ),
    }
)

DEFERRED_MECHANICS = (
    "zombie-rot:daily-stage-progression-and-cross-encounter-persistence",
    "zombie-rot:treatment-cure-and-recovery",
    "zombie-rot:terminal-death-and-plague-zombie-rising",
)

_DAY = {"value": 1, "unit": "days"}
_VOID_DAMAGE = {
    "dice": {"count": 1, "sides": 6},
    "modifier": 0,
    "type": "void",
    "healingRestriction": "until-disease-cured",
    "rule": deepcopy(STAGE_EFFECT_RULE),
}
_STAGES = [
    {
        "number": 1,
        "duration": deepcopy(_DAY),
        "effects": {"carrier": True, "damage": None, "terminal": None},
    },
    *[
        {
            "number": number,
            "duration": deepcopy(_DAY),
            "effects": {
                "carrier": False,
                "damage": deepcopy(_VOID_DAMAGE),
                "terminal": None,
            },
        }
        for number in (2, 3, 4)
    ],
    {
        "number": 5,
        "duration": None,
        "effects": {
            "carrier": False,
            "damage": None,
            "terminal": {
                "dead": True,
                "risesAs": "plague-zombie",
                "timing": "immediately",
            },
        },
    },
]

_EXPECTED_MECHANIC = {
    "type": MECHANIC_TYPE,
    "afflictionKey": AFFLICTION_KEY,
    "afflictionType": "disease",
    "delivery": {
        "kind": "strike-rider",
        "trigger": "strike-hit-exposure",
    },
    "savingThrow": {"type": "fortitude", "dc": 18},
    "initialSave": {
        "failureStage": 1,
        "criticalFailureStage": 2,
        "hostOwned": True,
    },
    "multipleExposures": "no-effect-while-active",
    "stages": deepcopy(_STAGES),
    "healingRestriction": {
        "scope": "damage-from-this-affliction",
        "until": "disease-cured",
        "tracking": "outstanding-damage-ledger",
    },
    "runtime": {
        "supported": "initial-exposure",
        "progressionBoundary": "campaign-clock",
    },
    "rules": {
        "ability": deepcopy(SOURCE),
        "diseaseGlossary": deepcopy(DISEASE_GLOSSARY_RULE),
        "strike": deepcopy(STRIKE_RULE),
        "afflictions": deepcopy(AFFLICTIONS_RULE),
        "initialSave": deepcopy(INITIAL_SAVE_RULE),
        "stageProgression": deepcopy(STAGE_PROGRESSION_RULE),
        "stageEffects": deepcopy(STAGE_EFFECT_RULE),
        "multipleExposures": deepcopy(MULTIPLE_EXPOSURES_RULE),
        "death": deepcopy(DEATH_RULE),
    },
}

_SAVE_DEGREES = frozenset(
    {"critical-success", "success", "failure", "critical-failure"}
)
_STRIKE_DEGREES = frozenset(
    {"critical-success", "success", "failure", "critical-failure"}
)
_EFFECT_KEYS = frozenset(
    {
        "id",
        "kind",
        "afflictionKey",
        "afflictionType",
        "sourceParticipantId",
        "targetParticipantId",
        "sourceAbilityId",
        "stage",
        "stageDuration",
        "outstandingUnhealableDamage",
        "creation",
        "rule",
        "progressionBoundary",
    }
)


def _exact_source_object(source: AbilitySource) -> bool:
    value = source.raw_member.value
    return bool(
        source.raw_member.key == "!.Zombie Rot"
        and type(value) is RawSourceObject
        and tuple(member.key for member in value.members)
        == ("Traits", "Saving Throw", "Description")
        and type(value.members[0].value) is RawSourceArray
        and value.members[0].value.items == SOURCE_TRAITS
        and value.members[1].value == SOURCE_SAVE
        and value.members[2].value == SOURCE_DESCRIPTION
        and raw_source_sha256(value) == SOURCE_RECEIPT["selectionSha256"]
    )


def compile_zombie_rot(source: AbilitySource, /) -> AbilityCompilerPatch | None:
    """Compile the exact reviewed Plague Zombie disease ability."""

    if (
        source.source_id != SOURCE["sourceId"]
        or source.locator != SOURCE["locator"]
        or source.creature_name != "Plague Zombie"
        or source.source_label != "Zombie Rot"
        or source.kind != "passive"
        or source.action_cost is not None
        or source.traits != SOURCE_TRAITS
        or source.trigger
        or source.description != SOURCE_DESCRIPTION
        or not _exact_source_object(source)
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=deepcopy(_EXPECTED_MECHANIC),
        rule=RuleReference(SOURCE["sourceId"], SOURCE["locator"]),
        traits=SOURCE_TRAITS,
        deferred_mechanics=DEFERRED_MECHANICS,
    )


def zombie_rot_spec(ability: Mapping[str, Any], /) -> dict[str, Any]:
    """Validate one compiled runtime projection and return its mechanic."""

    mechanic = ability.get("mechanic")
    if (
        ability.get("id") != ABILITY_ID
        or ability.get("name") != "Zombie Rot"
        or ability.get("supported") is not True
        or ability.get("kind") != "passive"
        or ability.get("actionCost") is not None
        or ability.get("traits") != list(SOURCE_TRAITS)
        or ability.get("rule") != SOURCE
        or ability.get("deferredMechanics") != list(DEFERRED_MECHANICS)
        or not isinstance(mechanic, Mapping)
        or mechanic != _EXPECTED_MECHANIC
    ):
        raise EngineInputError("Zombie Rot mechanic is invalid")
    return deepcopy(dict(mechanic))


def initial_exposure_disposition(
    ability: Mapping[str, Any],
    *,
    targeting_succeeded: object,
    strike_degree: object | None,
    active_effect: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the exact host-roll contract for one Strike rider exposure."""

    mechanic = zombie_rot_spec(ability)
    if type(targeting_succeeded) is not bool:
        raise EngineInputError("Zombie Rot targeting result is invalid")
    if not targeting_succeeded:
        if strike_degree is not None:
            raise EngineInputError(
                "failed Zombie Rot targeting cannot have a Strike degree"
            )
        return {"kind": "no-exposure", "reason": "targeting-failed"}
    if not isinstance(strike_degree, str) or strike_degree not in _STRIKE_DEGREES:
        raise EngineInputError("Zombie Rot Strike degree is invalid")
    if active_effect is not None:
        validate_zombie_rot_effect(active_effect, ability=ability)
    if strike_degree not in {"success", "critical-success"}:
        return {"kind": "no-exposure", "reason": "strike-missed"}
    if active_effect is not None:
        return {
            "kind": "repeat-exposure-ignored",
            "reason": "same-disease-already-active",
            "rule": deepcopy(mechanic["rules"]["multipleExposures"]),
        }
    return {
        "kind": "initial-save",
        "savingThrow": deepcopy(mechanic["savingThrow"]),
        "hostOwned": True,
    }


def initial_stage_for_save(
    ability: Mapping[str, Any],
    save_degree: object,
) -> int | None:
    """Map one host-resolved initial Fortitude result to disease stage."""

    mechanic = zombie_rot_spec(ability)
    if not isinstance(save_degree, str) or save_degree not in _SAVE_DEGREES:
        raise EngineInputError("Zombie Rot saving throw degree is invalid")
    if save_degree == "failure":
        return int(mechanic["initialSave"]["failureStage"])
    if save_degree == "critical-failure":
        return int(mechanic["initialSave"]["criticalFailureStage"])
    return None


def stage_damage_profile(
    ability: Mapping[str, Any],
    stage: object,
) -> dict[str, Any] | None:
    """Return the exact damage contract for one authored Zombie Rot stage."""

    mechanic = zombie_rot_spec(ability)
    if isinstance(stage, bool) or not isinstance(stage, int):
        raise EngineInputError("Zombie Rot stage is invalid")
    stages = mechanic["stages"]
    if stage < 1 or stage > len(stages):
        raise EngineInputError("Zombie Rot stage is outside its source range")
    damage = stages[stage - 1]["effects"]["damage"]
    return deepcopy(damage)


def build_zombie_rot_effect(
    ability: Mapping[str, Any],
    *,
    source_participant_id: object,
    target_participant_id: object,
    event_sequence: object,
    initiative_step: object,
    round_number: object,
    stage: object,
    outstanding_unhealable_damage: object,
) -> dict[str, Any]:
    """Build bounded stage-1/2 state after an initial exposure."""

    mechanic = zombie_rot_spec(ability)
    for value, label in (
        (source_participant_id, "source participant"),
        (target_participant_id, "target participant"),
    ):
        if not isinstance(value, str) or not value or value != value.strip():
            raise EngineInputError(f"Zombie Rot {label} is invalid")
    for value, label, minimum in (
        (event_sequence, "event sequence", 1),
        (initiative_step, "initiative step", 0),
        (round_number, "round", 1),
        (outstanding_unhealable_damage, "restricted damage", 0),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise EngineInputError(f"Zombie Rot {label} is invalid")
    if stage not in {1, 2}:
        raise EngineInputError("Zombie Rot initial stage must be 1 or 2")
    if stage == 1 and outstanding_unhealable_damage != 0:
        raise EngineInputError("Zombie Rot stage 1 cannot restrict damage")
    effect = {
        "id": (
            f"affliction:{event_sequence}:{target_participant_id}:zombie-rot"
        ),
        "kind": "long-term-affliction",
        "afflictionKey": AFFLICTION_KEY,
        "afflictionType": "disease",
        "sourceParticipantId": source_participant_id,
        "targetParticipantId": target_participant_id,
        "sourceAbilityId": ABILITY_ID,
        "stage": stage,
        "stageDuration": deepcopy(mechanic["stages"][stage - 1]["duration"]),
        "outstandingUnhealableDamage": outstanding_unhealable_damage,
        "creation": {
            "eventSequence": event_sequence,
            "initiativeStep": initiative_step,
            "round": round_number,
        },
        "rule": deepcopy(SOURCE),
        "progressionBoundary": "campaign-clock",
    }
    validate_zombie_rot_effect(effect, ability=ability)
    return effect


def validate_zombie_rot_effect(
    effect: Mapping[str, Any],
    *,
    ability: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Fail closed on forged bounded Zombie Rot state."""

    mechanic = zombie_rot_spec(ability)
    creation = effect.get("creation") if isinstance(effect, Mapping) else None
    stage = effect.get("stage") if isinstance(effect, Mapping) else None
    damage = (
        effect.get("outstandingUnhealableDamage")
        if isinstance(effect, Mapping)
        else None
    )
    source_id = (
        effect.get("sourceParticipantId")
        if isinstance(effect, Mapping)
        else None
    )
    target_id = (
        effect.get("targetParticipantId")
        if isinstance(effect, Mapping)
        else None
    )
    expected_id = (
        f"affliction:{creation.get('eventSequence')}:{target_id}:zombie-rot"
        if isinstance(creation, Mapping)
        else None
    )
    if (
        not isinstance(effect, Mapping)
        or set(effect) != _EFFECT_KEYS
        or effect.get("id") != expected_id
        or effect.get("kind") != "long-term-affliction"
        or effect.get("afflictionKey") != AFFLICTION_KEY
        or effect.get("afflictionType") != "disease"
        or not isinstance(source_id, str)
        or not source_id
        or source_id != source_id.strip()
        or not isinstance(target_id, str)
        or not target_id
        or target_id != target_id.strip()
        or effect.get("sourceAbilityId") != ABILITY_ID
        or stage not in {1, 2}
        or effect.get("stageDuration")
        != mechanic["stages"][int(stage) - 1]["duration"]
        or isinstance(damage, bool)
        or not isinstance(damage, int)
        or damage < 0
        or (stage == 1 and damage != 0)
        or not isinstance(creation, Mapping)
        or set(creation) != {"eventSequence", "initiativeStep", "round"}
        or any(
            isinstance(creation.get(key), bool)
            or not isinstance(creation.get(key), int)
            or int(creation[key]) < minimum
            for key, minimum in (
                ("eventSequence", 1),
                ("initiativeStep", 0),
                ("round", 1),
            )
        )
        or effect.get("rule") != SOURCE
        or effect.get("progressionBoundary") != "campaign-clock"
    ):
        raise EngineInputError("Zombie Rot effect evidence is invalid")
    return effect


def apply_healing_restriction(
    *,
    target_participant_id: object,
    current_hit_points: object,
    maximum_hit_points: object,
    requested_healing: object,
    effects: Sequence[Mapping[str, Any]],
    ability: Mapping[str, Any],
) -> dict[str, int]:
    """Apply the authored unhealable-disease-damage ledger to one heal."""

    if (
        not isinstance(target_participant_id, str)
        or not target_participant_id
        or target_participant_id != target_participant_id.strip()
    ):
        raise EngineInputError("Zombie Rot healing target is invalid")
    for value, label, minimum in (
        (current_hit_points, "current Hit Points", 0),
        (maximum_hit_points, "maximum Hit Points", 1),
        (requested_healing, "requested healing", 0),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise EngineInputError(f"Zombie Rot {label} is invalid")
    if current_hit_points > maximum_hit_points:
        raise EngineInputError("Zombie Rot Hit Points exceed maximum")
    if isinstance(effects, (str, bytes)) or not isinstance(effects, Sequence):
        raise EngineInputError("Zombie Rot effects must be an ordered sequence")
    matching = []
    for effect in effects:
        if not isinstance(effect, Mapping):
            raise EngineInputError("Zombie Rot effects contain invalid state")
        if (
            effect.get("afflictionKey") == AFFLICTION_KEY
            and effect.get("targetParticipantId") == target_participant_id
        ):
            validate_zombie_rot_effect(effect, ability=ability)
            matching.append(effect)
    if len(matching) > 1:
        raise EngineInputError("multiple active Zombie Rot effects are invalid")
    restricted = sum(
        int(effect["outstandingUnhealableDamage"])
        for effect in matching
    )
    disease_cap = max(0, maximum_hit_points - restricted)
    ordinary_after = min(maximum_hit_points, current_hit_points + requested_healing)
    after = max(current_hit_points, min(disease_cap, ordinary_after))
    applied = after - current_hit_points
    return {
        "before": current_hit_points,
        "requested": requested_healing,
        "applied": applied,
        "after": after,
        "ordinaryMaximum": maximum_hit_points,
        "diseaseHealingCap": disease_cap,
        "outstandingUnhealableDamage": restricted,
        "blockedByZombieRot": ordinary_after - after,
    }


FRAGMENT = MechanicFamilyFragment(
    family_id="zombie-rot",
    mechanic_types=(MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="zombie-rot",
            mechanic_type=MECHANIC_TYPE,
            compiler=compile_zombie_rot,
        ),
    ),
)


__all__ = [
    "ABILITY_ID",
    "AFFLICTION_KEY",
    "AFFLICTIONS_RULE",
    "DEATH_RULE",
    "DEFERRED_MECHANICS",
    "DISEASE_GLOSSARY_RULE",
    "FRAGMENT",
    "INITIAL_SAVE_RULE",
    "MECHANIC_TYPE",
    "MULTIPLE_EXPOSURES_RULE",
    "SOURCE",
    "SOURCE_DESCRIPTION",
    "SOURCE_RECEIPT",
    "SOURCE_SAVE",
    "SOURCE_TRAITS",
    "STAGE_EFFECT_RULE",
    "STAGE_PROGRESSION_RULE",
    "STRIKE_RULE",
    "apply_healing_restriction",
    "build_zombie_rot_effect",
    "compile_zombie_rot",
    "initial_exposure_disposition",
    "initial_stage_for_save",
    "stage_damage_profile",
    "validate_zombie_rot_effect",
    "zombie_rot_spec",
]

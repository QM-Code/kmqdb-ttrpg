"""Compile and plan Strikes against a creature held by the actor.

The encounter layer remains the sole owner of Strike and condition
resolution.  This module only compiles Maul/Wrestle and turns their activity
requests and ordinary Strike results into small deterministic plans.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import re
from typing import Any

from ..errors import EngineInputError
from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RuleReference,
)


MECHANIC_TYPE = "grabbed-target-strikes"

_TARGET_RELATION = "grabbed-or-restrained-by-source"
_SHARED_MAP = "shared-at-activity-start"
_NORMAL_MAP = "normal"
_HIT_DEGREES = ("success", "critical-success")
_ALL_DEGREES = {
    "critical-failure",
    "failure",
    "success",
    "critical-success",
}
_STRIKE_FIELDS = {
    "targetingFlatCheckRoll",
    "attackRoll",
    "damageRolls",
    "additionalDamageRolls",
    "precisionDamageRolls",
    "packAttackDamageRolls",
    "deadlyDamageRolls",
    "effectRolls",
    "damageType",
}
_RULES = {
    "activity": {"sourceId": "core-pc1", "locator": "414.4"},
    "strike": {"sourceId": "core-pc1", "locator": "418.4"},
    "multipleAttackPenalty": {
        "sourceId": "core-pc1",
        "locator": "402.1",
    },
    "grabbed": {"sourceId": "core-pc1", "locator": "444.5"},
    "restrained": {"sourceId": "core-pc1", "locator": "446.3"},
}
_PRONE_RULE = {"sourceId": "core-pc1", "locator": "445.6"}

_MAUL_RE = re.compile(
    r"^The (?P<subject>[A-Za-z][A-Za-z '\u2019-]*) makes two "
    r"(?P<strike>[A-Za-z][A-Za-z -]*?) Strikes against a creature it has "
    r"grabbed\. Both count toward its multiple attack penalty, but the "
    r"penalty increases only after both attacks are made\.$",
    re.IGNORECASE,
)
_WRESTLE_RE = re.compile(
    r"^The (?P<subject>[A-Za-z][A-Za-z '\u2019-]*) makes a "
    r"(?P<strike>[A-Za-z][A-Za-z -]*?) Strike against a creature it is "
    r"grabbing\. If the attack hits, that creature is knocked prone\.$",
    re.IGNORECASE,
)


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _compile(
    source: AbilitySource,
    *,
    label: str,
    pattern: re.Pattern[str],
    strike_count: int,
    map_mode: str,
    prone_on_hit: bool,
) -> AbilityCompilerPatch | None:
    match = pattern.fullmatch(_normalized(source.description))
    if (
        match is None
        or match.group("subject").casefold()
        != _normalized(source.creature_name).casefold()
        or source.kind != "activity"
        or source.action_cost != 1
        or source.trigger.strip()
        or source.source_label.casefold() != label
    ):
        return None

    mechanic: dict[str, Any] = {
        "type": MECHANIC_TYPE,
        "targetRelation": _TARGET_RELATION,
        # The source label remains unlinked until the encounter compiler can
        # prove one matching definition-local Strike.
        "strikeName": match.group("strike"),
        "strikeCount": strike_count,
        "multipleAttackPenalty": {
            "mode": map_mode,
            "postActivityAttackCountIncrement": strike_count,
        },
        "rules": _RULES,
    }
    if prone_on_hit:
        mechanic["onHit"] = {
            "degrees": list(_HIT_DEGREES),
            "condition": "prone",
            "rule": _PRONE_RULE,
        }
    return AbilityCompilerPatch(
        mechanic=mechanic,
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_maul(source: AbilitySource, /) -> AbilityCompilerPatch | None:
    """Compile two claw Strikes that share the activity-start MAP."""

    return _compile(
        source,
        label="maul",
        pattern=_MAUL_RE,
        strike_count=2,
        map_mode=_SHARED_MAP,
        prone_on_hit=False,
    )


def compile_wrestle(source: AbilitySource, /) -> AbilityCompilerPatch | None:
    """Compile one normal-MAP claw Strike that knocks prone on a hit."""

    return _compile(
        source,
        label="wrestle",
        pattern=_WRESTLE_RE,
        strike_count=1,
        map_mode=_NORMAL_MAP,
        prone_on_hit=True,
    )


def _spec(
    ability: Mapping[str, Any],
) -> tuple[str, str, int, str, Mapping[str, Any] | None]:
    if not isinstance(ability, Mapping):
        raise EngineInputError("grabbed-target Strike ability must be an object")
    ability_id = ability.get("id")
    mechanic = ability.get("mechanic")
    if (
        not isinstance(ability_id, str)
        or not ability_id
        or ability.get("supported") is not True
        or ability.get("kind") != "activity"
        or ability.get("actionCost") != 1
        or not isinstance(mechanic, Mapping)
        or mechanic.get("type") != MECHANIC_TYPE
        or mechanic.get("targetRelation") != _TARGET_RELATION
    ):
        raise EngineInputError("grabbed-target Strike ability is invalid")

    strike_name = mechanic.get("strikeName")
    strike_count = mechanic.get("strikeCount")
    map_definition = mechanic.get("multipleAttackPenalty")
    if (
        not isinstance(strike_name, str)
        or not strike_name
        or strike_name != strike_name.strip()
        or type(strike_count) is not int
        or strike_count not in {1, 2}
        or not isinstance(map_definition, Mapping)
    ):
        raise EngineInputError(f"{ability_id} mechanic is invalid")
    map_mode = map_definition.get("mode")
    if (
        map_definition.get("postActivityAttackCountIncrement") != strike_count
        or (strike_count == 2 and map_mode != _SHARED_MAP)
        or (strike_count == 1 and map_mode != _NORMAL_MAP)
    ):
        raise EngineInputError(f"{ability_id} MAP mechanic is invalid")

    on_hit = mechanic.get("onHit")
    if strike_count == 1:
        if (
            not isinstance(on_hit, Mapping)
            or tuple(on_hit.get("degrees") or ()) != _HIT_DEGREES
            or on_hit.get("condition") != "prone"
            or on_hit.get("rule") != _PRONE_RULE
        ):
            raise EngineInputError(f"{ability_id} on-hit mechanic is invalid")
    elif on_hit is not None:
        raise EngineInputError(f"{ability_id} must not have an on-hit mechanic")
    return ability_id, strike_name, strike_count, str(map_mode), on_hit


def build_grabbed_strike_activity_options(
    state: Mapping[str, Any],
    actor: Mapping[str, Any],
    ability: Mapping[str, Any],
    /,
) -> list[dict[str, Any]]:
    """Project the live creatures grabbed or restrained by ``actor``."""

    ability_id, strike_name, strike_count, _map_mode, on_hit = _spec(ability)
    actor_id = actor.get("id") if isinstance(actor, Mapping) else None
    participants = state.get("participants") if isinstance(state, Mapping) else None
    effects = state.get("effects", []) if isinstance(state, Mapping) else None
    if (
        not isinstance(actor_id, str)
        or not actor_id
        or not isinstance(participants, list)
        or any(not isinstance(item, Mapping) for item in participants)
        or not isinstance(effects, list)
        or any(not isinstance(item, Mapping) for item in effects)
    ):
        raise EngineInputError("grabbed-target Strike option state is invalid")

    active_targets = {
        item["id"]
        for item in participants
        if isinstance(item.get("id"), str)
        and item["id"] != actor_id
        and not item.get("defeated")
        and not item.get("incapacitated")
    }
    effects_by_target: dict[str, list[Mapping[str, Any]]] = {}
    for effect in effects:
        target_id = effect.get("targetParticipantId")
        if (
            effect.get("kind") == "grapple"
            and effect.get("sourceParticipantId") == actor_id
            and target_id in active_targets
            and effect.get("condition") in {"grabbed", "restrained"}
            and isinstance(effect.get("id"), str)
            and effect["id"]
        ):
            effects_by_target.setdefault(str(target_id), []).append(effect)

    legal_targets = [
        {
            "targetId": participant["id"],
            "conditions": sorted(
                {str(item["condition"]) for item in effects_by_target[participant["id"]]}
            ),
            "sourceEffectIds": [
                str(item["id"]) for item in effects_by_target[participant["id"]]
            ],
        }
        for participant in participants
        if participant.get("id") in effects_by_target
    ]
    mechanic = ability["mechanic"]
    option = {
        "abilityId": ability_id,
        "actionCost": 1,
        "traits": [
            "attack",
            *[
                trait
                for trait in ability.get("traits") or []
                if trait != "attack"
            ],
        ],
        "available": bool(legal_targets),
        "blockedBy": [],
        "legalTargets": legal_targets,
        "strikeName": strike_name,
        "strikeCount": strike_count,
        "multipleAttackPenalty": deepcopy(
            mechanic["multipleAttackPenalty"]
        ),
    }
    if on_hit is not None:
        option["onHit"] = deepcopy(on_hit)
    return [option]


def _strike_request(
    value: Mapping[str, Any],
    *,
    label: str,
    target_id: str,
    strike_name: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EngineInputError(f"{label} must be an object")
    unexpected = set(value).difference(_STRIKE_FIELDS)
    attack_roll = value.get("attackRoll")
    targeting_flat_check_roll = value.get(
        "targetingFlatCheckRoll"
    )
    if unexpected:
        raise EngineInputError(
            f"{label} contains unsupported fields: "
            f"{', '.join(sorted(unexpected))}"
        )
    if (
        targeting_flat_check_roll is not None
        and (
            isinstance(targeting_flat_check_roll, bool)
            or not isinstance(targeting_flat_check_roll, int)
            or not 1 <= targeting_flat_check_roll <= 20
        )
    ):
        raise EngineInputError(
            f"{label} targetingFlatCheckRoll must be a d20 result"
        )
    if (
        attack_roll is None
        and targeting_flat_check_roll is not None
    ):
        pass
    elif (
        isinstance(attack_roll, bool)
        or not isinstance(attack_roll, int)
        or not 1 <= attack_roll <= 20
    ):
        raise EngineInputError(f"{label} attackRoll must be a d20 result")
    return {
        "type": "Strike",
        "strikeName": strike_name,
        "targetId": target_id,
        **deepcopy(dict(value)),
    }


def validate_grabbed_strike_activity(
    action: Mapping[str, Any],
    ability: Mapping[str, Any],
    held_target_ids: Sequence[str],
    /,
    *,
    attacks_this_turn: int,
) -> dict[str, Any]:
    """Return ordered ordinary-Strike inputs plus the exact MAP plan."""

    ability_id, strike_name, strike_count, map_mode, on_hit = _spec(ability)
    if not isinstance(action, Mapping):
        raise EngineInputError(f"{ability_id} action must be an object")
    if (
        action.get("type") != "Activity"
        or action.get("abilityId") != ability_id
    ):
        raise EngineInputError(f"{ability_id} activity identity is invalid")
    if (
        not isinstance(held_target_ids, Sequence)
        or isinstance(held_target_ids, (str, bytes))
        or any(not isinstance(item, str) or not item for item in held_target_ids)
        or len(set(held_target_ids)) != len(held_target_ids)
    ):
        raise EngineInputError("held target IDs must be a unique ordered array")
    target_id = action.get("targetId")
    if target_id not in held_target_ids:
        raise EngineInputError(
            f"{ability_id} target is not grabbed or restrained by the actor"
        )
    if (
        isinstance(attacks_this_turn, bool)
        or not isinstance(attacks_this_turn, int)
        or attacks_this_turn < 0
    ):
        raise EngineInputError("attacksThisTurn must be a nonnegative integer")

    if strike_count == 2:
        unexpected = set(action).difference(
            {"type", "abilityId", "targetId", "strikes"}
        )
        raw_strikes = action.get("strikes")
        if unexpected:
            raise EngineInputError(
                f"{ability_id} contains unsupported fields: "
                f"{', '.join(sorted(unexpected))}"
            )
        if not isinstance(raw_strikes, list) or len(raw_strikes) != 2:
            raise EngineInputError(f"{ability_id} requires exactly 2 Strike inputs")
        strike_inputs = [
            _strike_request(
                item,
                label=f"{ability_id} strikes[{index}]",
                target_id=str(target_id),
                strike_name=strike_name,
            )
            for index, item in enumerate(raw_strikes)
        ]
    else:
        unexpected = set(action).difference(
            {"type", "abilityId", "targetId", *_STRIKE_FIELDS}
        )
        if unexpected:
            raise EngineInputError(
                f"{ability_id} contains unsupported fields: "
                f"{', '.join(sorted(unexpected))}"
            )
        strike_inputs = [
            _strike_request(
                {key: value for key, value in action.items() if key in _STRIKE_FIELDS},
                label=ability_id,
                target_id=str(target_id),
                strike_name=strike_name,
            )
        ]

    first_attack_number = attacks_this_turn + 1
    attack_numbers = (
        [first_attack_number] * strike_count
        if map_mode == _SHARED_MAP
        else list(range(first_attack_number, first_attack_number + strike_count))
    )
    return {
        "abilityId": ability_id,
        "targetId": target_id,
        "strikeName": strike_name,
        "strikeCount": strike_count,
        "strikeSteps": [
            {"attackNumber": number, "request": request}
            for number, request in zip(attack_numbers, strike_inputs, strict=True)
        ],
        "multipleAttackPenalty": {
            "mode": map_mode,
            "attacksThisTurnBefore": attacks_this_turn,
            "attackNumbers": attack_numbers,
            "postActivityAttackCountIncrement": strike_count,
            "attacksThisTurnAfter": attacks_this_turn + strike_count,
        },
        "onHit": deepcopy(on_hit),
    }


def summarize_grabbed_strike_resolution(
    ability: Mapping[str, Any],
    strike_events: Sequence[Mapping[str, Any]],
    /,
) -> dict[str, Any]:
    """Validate Strike results and identify Wrestle's prone application."""

    ability_id, strike_name, strike_count, map_mode, on_hit = _spec(ability)
    if (
        not isinstance(strike_events, Sequence)
        or isinstance(strike_events, (str, bytes))
        or len(strike_events) != strike_count
    ):
        raise EngineInputError(
            f"{ability_id} requires exactly {strike_count} Strike results"
        )

    target_id = None
    attack_numbers: list[int] = []
    degrees: list[str] = []
    hits: list[int] = []
    for ordinal, event in enumerate(strike_events, start=1):
        if not isinstance(event, Mapping):
            raise EngineInputError(f"{ability_id} Strike result is invalid")
        current_target = event.get("targetId")
        attack_number = event.get("attackNumber")
        degree = event.get("degree")
        if (
            not isinstance(current_target, str)
            or not current_target
            or (target_id is not None and current_target != target_id)
            or str(event.get("strikeName") or "").casefold()
            != strike_name.casefold()
            or isinstance(attack_number, bool)
            or not isinstance(attack_number, int)
            or attack_number <= 0
            or degree not in _ALL_DEGREES
        ):
            raise EngineInputError(f"{ability_id} Strike result is invalid")
        target_id = current_target
        attack_numbers.append(attack_number)
        degrees.append(str(degree))
        if degree in _HIT_DEGREES:
            hits.append(ordinal)

    if map_mode == _SHARED_MAP and len(set(attack_numbers)) != 1:
        raise EngineInputError(
            f"{ability_id} Strikes must use one activity-start MAP value"
        )
    if map_mode == _NORMAL_MAP and attack_numbers != list(
        range(attack_numbers[0], attack_numbers[0] + strike_count)
    ):
        raise EngineInputError(f"{ability_id} Strikes have invalid MAP progression")

    condition = None
    if on_hit is not None and hits:
        condition = {
            "targetId": target_id,
            "condition": "prone",
            "triggeringStrikeOrdinals": hits,
            "rule": deepcopy(_PRONE_RULE),
        }
    return {
        "abilityId": ability_id,
        "targetId": target_id,
        "strikeCount": strike_count,
        "attackNumbers": attack_numbers,
        "degrees": degrees,
        "hitStrikeOrdinals": hits,
        "postActivityAttackCountIncrement": strike_count,
        "onHitCondition": condition,
    }


FRAGMENT = MechanicFamilyFragment(
    family_id="grabbed-strike-activities",
    mechanic_types=(MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="maul",
            mechanic_type=MECHANIC_TYPE,
            compiler=compile_maul,
        ),
        AbilityCompilerRegistration(
            compiler_id="wrestle",
            mechanic_type=MECHANIC_TYPE,
            compiler=compile_wrestle,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "MECHANIC_TYPE",
    "build_grabbed_strike_activity_options",
    "compile_maul",
    "compile_wrestle",
    "summarize_grabbed_strike_resolution",
    "validate_grabbed_strike_activity",
]

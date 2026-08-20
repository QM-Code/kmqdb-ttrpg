"""Compile and execute the reviewed Goblin Scuttle reaction family."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, fields
from typing import Any, Callable, Mapping

from ..errors import EngineInputError
from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RuleReference,
)


GOBLIN_SCUTTLE_LABEL = "Goblin Scuttle"
GOBLIN_SCUTTLE_MECHANIC_TYPE = (
    "ally-ended-move-adjacent-step-reaction"
)
GOBLIN_SCUTTLE_SOURCE_ID = "core-mc1"
GOBLIN_SCUTTLE_QUEUE_KIND = "goblin-scuttle"
GOBLIN_SCUTTLE_POST_EVENT_HOOK_ID = "goblin-scuttle-after-move"
GOBLIN_WARRIOR_LOCATOR = "174.2"
INHERITED_LOCATORS = frozenset(("174.4", "175.1", "175.3"))
FULL_TRIGGER = "a goblin ally ends a move action adjacent to the warrior"
FULL_DESCRIPTION = "the goblin warrior steps."
INHERITED_DESCRIPTION = "as goblin warrior."


@dataclass(frozen=True, slots=True)
class ScuttleRuntimeHost:
    """Narrow encounter-kernel operations used by Goblin Scuttle."""

    participant_map: Callable[[dict[str, Any]], dict[str, dict[str, Any]]]
    definition_for: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    ability_by_mechanic: Callable[[dict[str, Any], str], dict[str, Any] | None]
    participant_distance: Callable[[dict[str, Any], str, str], int]
    legal_step_destinations: Callable[
        [dict[str, Any], dict[str, Any]], list[dict[str, int]]
    ]
    land_speed_feet: Callable[..., int | None]
    coordinate: Callable[[Any, str], dict[str, int]]
    movement_step_is_legal: Callable[
        [dict[str, Any], dict[str, Any], dict[str, int], dict[str, int]],
        list[dict[str, int]],
    ]
    release_grapples_by_source: Callable[[dict[str, Any], str], list[str]]
    step_rule: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "step_rule":
                if not isinstance(value, Mapping):
                    raise TypeError("Scuttle host step_rule must be a mapping")
            elif not callable(value):
                raise TypeError(f"Scuttle host {field.name} must be callable")


def _mechanic_for(ability: Mapping[str, Any]) -> Mapping[str, Any]:
    mechanic = ability.get("mechanic")
    if (
        not isinstance(mechanic, Mapping)
        or mechanic.get("type") != GOBLIN_SCUTTLE_MECHANIC_TYPE
        or mechanic.get("allyTrait") != "goblin"
        or mechanic.get("distanceFeet") != 5
        or mechanic.get("movement") != "step"
        or mechanic.get("stepFeet") != 5
    ):
        raise EngineInputError("Goblin Scuttle mechanic is invalid")
    return mechanic


def _eligible_context(
    state: dict[str, Any],
    participant_id: str,
    trigger_participant_id: str,
    host: ScuttleRuntimeHost,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, int]]] | None:
    participants = host.participant_map(state)
    participant = participants.get(participant_id)
    trigger = participants.get(trigger_participant_id)
    if participant is None or trigger is None or participant_id == trigger_participant_id:
        return None
    trigger_definition = host.definition_for(state, trigger)
    if (
        participant.get("side") != trigger.get("side")
        or participant.get("defeated")
        or participant.get("incapacitated")
        or not participant.get("reactionAvailable")
        or "goblin" not in trigger_definition.get("traits", [])
        or host.participant_distance(
            state, trigger_participant_id, participant_id
        ) != 5
    ):
        return None
    ability = host.ability_by_mechanic(
        host.definition_for(state, participant),
        GOBLIN_SCUTTLE_MECHANIC_TYPE,
    )
    if ability is None:
        return None
    _mechanic_for(ability)
    destinations = host.legal_step_destinations(state, participant)
    if not destinations:
        return None
    return participant, ability, destinations


def observe_post_event(
    state: Mapping[str, Any],
    event: Mapping[str, Any],
    host: ScuttleRuntimeHost,
) -> tuple[dict[str, Any], ...]:
    """Census initiative-ordered Scuttle candidates after a completed move."""

    if event.get("endedMoveAction") is not True:
        return ()
    if state.get("pendingDecision") is not None:
        return ()
    sequence = event.get("sequence")
    mover_id = event.get("actorId")
    if type(sequence) is not int or sequence <= 0:
        raise EngineInputError("Goblin Scuttle trigger event sequence is invalid")
    if not isinstance(mover_id, str) or not mover_id:
        raise EngineInputError("Goblin Scuttle trigger participant is invalid")
    mutable_state = state  # host callbacks do not mutate during census
    participants = host.participant_map(mutable_state)  # type: ignore[arg-type]
    mover = participants.get(mover_id)
    if mover is None:
        return ()
    if "goblin" not in host.definition_for(  # type: ignore[arg-type]
        mutable_state, mover
    ).get("traits", []):
        return ()
    turn = state.get("turn")
    order = turn.get("order") if isinstance(turn, Mapping) else None
    if not isinstance(order, list) or any(
        not isinstance(participant_id, str) for participant_id in order
    ):
        raise EngineInputError("Goblin Scuttle initiative order is invalid")
    candidates = []
    for participant_id in order:
        if _eligible_context(
            mutable_state,  # type: ignore[arg-type]
            participant_id,
            mover_id,
            host,
        ) is not None:
            candidates.append(
                {
                    "kind": GOBLIN_SCUTTLE_QUEUE_KIND,
                    "participantId": participant_id,
                    "triggerParticipantId": mover_id,
                    "triggerEventSequence": sequence,
                }
            )
    return tuple(candidates)


def build_pending_decision(
    state: Mapping[str, Any],
    queued: Mapping[str, Any],
    host: ScuttleRuntimeHost,
) -> dict[str, Any] | None:
    """Re-prove a queued candidate and build its bounded decision."""

    if set(queued) != {
        "kind",
        "participantId",
        "triggerParticipantId",
        "triggerEventSequence",
    } or queued.get("kind") != GOBLIN_SCUTTLE_QUEUE_KIND:
        raise EngineInputError("queued Goblin Scuttle candidate is invalid")
    participant_id = queued.get("participantId")
    trigger_id = queued.get("triggerParticipantId")
    sequence = queued.get("triggerEventSequence")
    if (
        not isinstance(participant_id, str)
        or not participant_id
        or not isinstance(trigger_id, str)
        or not trigger_id
        or type(sequence) is not int
        or sequence <= 0
    ):
        raise EngineInputError("queued Goblin Scuttle candidate is invalid")
    context = _eligible_context(
        state,  # type: ignore[arg-type]
        participant_id,
        trigger_id,
        host,
    )
    if context is None:
        return None
    _participant, ability, destinations = context
    return {
        "type": "Reaction",
        "participantId": participant_id,
        "triggerParticipantId": trigger_id,
        "trigger": "goblin-ally-ended-move-adjacent",
        "triggerEventSequence": sequence,
        "options": [
            {
                "abilityId": ability["id"],
                "use": [True, False],
                "reactionCost": 1,
                "destination": {
                    "type": "coordinate",
                    "legalValues": deepcopy(destinations),
                },
                "rule": deepcopy(ability["rule"]),
            }
        ],
    }


def resolve_reaction(
    state: dict[str, Any],
    actor_id: str,
    action: Mapping[str, Any],
    ability: Mapping[str, Any],
    decision: Mapping[str, Any],
    host: ScuttleRuntimeHost,
) -> dict[str, Any]:
    """Resolve accept/decline and perform the accepted five-foot Step."""

    use = action.get("use")
    expected_fields = {"type", "abilityId", "use"}
    if use is True:
        expected_fields.add("destination")
    if (
        set(action) != expected_fields
        or action.get("type") != "Reaction"
        or action.get("abilityId") != ability.get("id")
        or type(use) is not bool
    ):
        raise EngineInputError("Goblin Scuttle reaction input is invalid")
    _mechanic_for(ability)
    trigger_id = decision.get("triggerParticipantId")
    if (
        decision.get("type") != "Reaction"
        or decision.get("participantId") != actor_id
        or decision.get("trigger") != "goblin-ally-ended-move-adjacent"
        or not isinstance(trigger_id, str)
    ):
        raise EngineInputError("pending Goblin Scuttle decision is invalid")
    context = _eligible_context(state, actor_id, trigger_id, host)
    if context is None:
        raise EngineInputError("Goblin Scuttle trigger is no longer valid")
    participant, active_ability, legal = context
    if active_ability.get("id") != ability.get("id"):
        raise EngineInputError("pending Goblin Scuttle ability is invalid")
    movement = None
    if use:
        host.land_speed_feet(
            host.definition_for(state, participant),
            required_for="Goblin Scuttle",
        )
        selected = host.coordinate(
            action.get("destination"), "Goblin Scuttle destination"
        )
        if selected not in legal:
            raise EngineInputError(
                "Goblin Scuttle destination is not a legal 5-foot Step"
            )
        previous = deepcopy(participant["position"])
        participant["occupiedSquares"] = host.movement_step_is_legal(
            state, participant, previous, selected
        )
        participant["position"] = deepcopy(selected)
        released = host.release_grapples_by_source(state, actor_id)
        participant["reactionAvailable"] = False
        movement = {
            "type": "Step",
            "from": previous,
            "to": deepcopy(selected),
            "distanceFeet": 5,
            "triggersMovementReactions": False,
            "releasedEffectIds": released,
            "rule": deepcopy(dict(host.step_rule)),
        }
    return {
        "triggerParticipantId": trigger_id,
        "movement": movement,
    }


def _normalized_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _reviewed_rule_reference(
    source: AbilitySource,
) -> RuleReference | None:
    normalized_description = _normalized_text(source.description)
    normalized_trigger = _normalized_text(source.trigger.rstrip(";"))
    if (
        normalized_trigger == FULL_TRIGGER
        and normalized_description == FULL_DESCRIPTION
    ):
        return RuleReference(source.source_id, source.locator)
    if (
        source.source_id == GOBLIN_SCUTTLE_SOURCE_ID
        and source.locator in INHERITED_LOCATORS
        and normalized_description == INHERITED_DESCRIPTION
    ):
        return RuleReference(
            GOBLIN_SCUTTLE_SOURCE_ID,
            GOBLIN_WARRIOR_LOCATOR,
        )
    return None


def compile_goblin_scuttle(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the full reaction or its exact reviewed inherited reference."""

    rule = _reviewed_rule_reference(source)
    if rule is None:
        return None
    if source.source_label.casefold() != GOBLIN_SCUTTLE_LABEL.casefold():
        return None
    if source.kind != "reaction" or source.action_cost != "reaction":
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": GOBLIN_SCUTTLE_MECHANIC_TYPE,
            "allyTrait": "goblin",
            "distanceFeet": 5,
            "movement": "step",
            "stepFeet": 5,
        },
        rule=rule,
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="goblin-scuttle",
    mechanic_types=(GOBLIN_SCUTTLE_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="goblin-scuttle",
            mechanic_type=GOBLIN_SCUTTLE_MECHANIC_TYPE,
            compiler=compile_goblin_scuttle,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "GOBLIN_SCUTTLE_MECHANIC_TYPE",
    "GOBLIN_SCUTTLE_POST_EVENT_HOOK_ID",
    "GOBLIN_SCUTTLE_QUEUE_KIND",
    "ScuttleRuntimeHost",
    "build_pending_decision",
    "compile_goblin_scuttle",
    "observe_post_event",
    "resolve_reaction",
]

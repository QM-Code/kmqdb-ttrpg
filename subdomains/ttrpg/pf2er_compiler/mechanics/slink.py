"""Source-authenticated Viper Slink compilation and family runtime.

The family owns the bounded clean-map land-Stride branch.  Composition owns
registration and supplies ordinary encounter operations through
``SlinkRuntimeHost``.  Climb, Swim, Tiny shared-space movement, and nested
non-reaction movement exposures remain explicit structured deferrals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, fields
from types import MappingProxyType
from typing import Any, Callable, final

from ..errors import EngineInputError
from .contracts import RawSourceMember, RawSourceObject
from .source_authority import (
    RawMemberStep,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedSourceSelection,
)


FAMILY_ID = "slink"
ENTITY_ID = "pf2er:slink"
PROVIDER_RULE_ID = "pf2er.rule:viper-slink"
MECHANIC_TYPE = "creature-ended-movement-nearby-escape-reaction"
SOURCE_ID = "core-mc1"
SOURCE_LOCATOR = "316.2"
SOURCE_CREATURE_NAME = "Viper"
SOURCE_MEMBER_KEY = "!.Slink"
SOURCE_SELECTION_SHA256 = (
    "b5fc193c9d555ee547fce840d5b46b25b7b4a915cadf6b2a69a2ef10ce87b4de"
)
QUEUE_KIND = "slink"
POST_EVENT_HOOK_ID = "slink-after-move"
MAXIMUM_DISTANCE_FEET = 10
MAX_LEGAL_PATHS = 256
MAX_PATH_SQUARES = 2

SOURCE_TRIGGER = (
    "A creature ends its movement adjacent to the viper or within the "
    "viper's space."
)
SOURCE_DESCRIPTION = (
    "The viper Strides, Climbs, or Swims up to 10 feet (or up to the "
    "relevant Speed, if that Speed is less than 10 feet). It must end its "
    "movement in a location that isn't within 5 feet of a foe. This movement "
    "doesn't trigger reactions."
)

RUNTIME_DEFERRALS = (
    MappingProxyType(
        {
            "kind": "movement-mode",
            "value": "climb",
            "reason": "selected runtime has no package-owned Climb path adapter",
        }
    ),
    MappingProxyType(
        {
            "kind": "movement-mode",
            "value": "swim",
            "reason": "selected runtime has no package-owned Swim path adapter",
        }
    ),
    MappingProxyType(
        {
            "kind": "geometry",
            "value": "tiny-shared-space",
            "reason": "conscious-creature shared-space movement is unsupported",
        }
    ),
    MappingProxyType(
        {
            "kind": "continuation",
            "value": "nested-nonreaction-movement-exposure",
            "reason": "the bounded branch rejects nested movement interruptions",
        }
    ),
)


def _semantic_projection() -> dict[str, Any]:
    return {
        "supported": True,
        "entityId": ENTITY_ID,
        "ruleRef": PROVIDER_RULE_ID,
        "traits": [],
        "mechanic": {
            "type": MECHANIC_TYPE,
            "family": FAMILY_ID,
            "trigger": {
                "actor": "another-creature",
                "timing": "ended-movement",
                "proximityFeet": [0, 5],
                "requiresMovementReactionTrigger": True,
                "forcedMovement": False,
            },
            "reactionCost": 1,
            "movement": {
                "choices": ["stride", "climb", "swim"],
                "maximumFeet": MAXIMUM_DISTANCE_FEET,
                "boundedByRelevantSpeed": True,
                "endpoint": {
                    "minimumDistanceFromEveryFoeFeet": 10,
                },
                "triggersMovementReactions": False,
            },
            "runtime": {
                "readyDomains": ["clean-map-land-stride"],
                "algorithmicallyComplete": False,
                "deferrals": [dict(item) for item in RUNTIME_DEFERRALS],
            },
        },
    }


@final
@dataclass(frozen=True, slots=True, init=False)
class CompiledSlink:
    """Opaque authority-backed compile result with a source-free projection."""

    _authority: SourceAuthorityAdapter = field(repr=False)
    _source: VerifiedSourceSelection = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("CompiledSlink can only be built by compile_slink")

    def _validated_source(self) -> VerifiedSourceSelection:
        source = self._authority.validate_selection(self._source)
        if _source_matches(source) is not True:
            raise EngineInputError("compiled Slink source is stale")
        return source

    @property
    def source_receipt(self) -> SourceReceipt:
        return self._validated_source().receipt

    def as_ability_update(self) -> dict[str, Any]:
        self._validated_source()
        return _semantic_projection()


def _source_matches(source: VerifiedSourceSelection) -> bool:
    if (
        type(source) is not VerifiedSourceSelection
        or source.address.source_id != SOURCE_ID
        or source.address.locator != SOURCE_LOCATOR
        or source.address.span is not None
        or len(source.address.carrier_path) != 1
        or type(source.address.carrier_path[0]) is not RawMemberStep
        or source.address.carrier_path[0].raw_key != "^.creature"
        or len(source.address.selection_path) != 1
        or type(source.address.selection_path[0]) is not RawMemberStep
        or source.address.selection_path[0].raw_key != SOURCE_MEMBER_KEY
        or source.selection_sha256 != SOURCE_SELECTION_SHA256
        or type(source.raw_member) is not RawSourceMember
        or source.raw_member.key != SOURCE_MEMBER_KEY
        or type(source.raw_value) is not RawSourceObject
        or source.selected_value is not source.raw_value
        or type(source.carrier.raw_block) is not RawSourceObject
    ):
        return False
    names = source.carrier.raw_block.values("Name")
    raw = source.raw_value
    return bool(
        names == (SOURCE_CREATURE_NAME,)
        and tuple(member.key for member in raw.members)
        == ("Action", "Trigger", "Description")
        and raw.values("Action") == ("reaction",)
        and raw.values("Trigger") == (SOURCE_TRIGGER,)
        and raw.values("Description") == (SOURCE_DESCRIPTION,)
    )


def select_slink_source(
    authority: SourceAuthorityAdapter,
) -> VerifiedSourceSelection:
    """Resolve Viper's sole exact Slink member from retained authority."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("Slink requires an exact SourceAuthorityAdapter")
    carrier = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=SOURCE_ID,
                locator=SOURCE_LOCATOR,
                carrier_path=(RawMemberStep("^.creature", 1),),
            )
        )
    )
    block = carrier.selected_value
    if type(block) is not RawSourceObject:
        raise EngineInputError("Viper source carrier is not an object")
    matches = tuple(
        (ordinal, member)
        for ordinal, member in enumerate(block.members)
        if member.key == SOURCE_MEMBER_KEY
    )
    if len(matches) != 1:
        raise EngineInputError("Viper must contain exactly one Slink member")
    ordinal, _member = matches[0]
    return authority.validate_selection(
        carrier.carrier.select((RawMemberStep(SOURCE_MEMBER_KEY, ordinal),))
    )


def compile_slink(
    authority: object,
    source: object,
    /,
) -> CompiledSlink | None:
    """Compile only the exact adapter-revalidated Viper Slink member."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("Slink requires an exact SourceAuthorityAdapter")
    if type(source) is not VerifiedSourceSelection:
        raise TypeError("Slink requires an exact VerifiedSourceSelection")
    verified = authority.validate_selection(source)
    if not _source_matches(verified):
        return None
    result = object.__new__(CompiledSlink)
    object.__setattr__(result, "_authority", authority)
    object.__setattr__(result, "_source", verified)
    result._validated_source()
    return result


@dataclass(frozen=True, slots=True)
class SlinkRuntimeHost:
    """Narrow kernel operations required by the family algorithm."""

    participant_map: Callable[[dict[str, Any]], dict[str, dict[str, Any]]]
    definition_for: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    ability_by_mechanic: Callable[[dict[str, Any], str], dict[str, Any] | None]
    participant_distance: Callable[[dict[str, Any], str, str], int]
    foe_ids: Callable[[dict[str, Any], str], Sequence[str]]
    distance_from_position: Callable[
        [dict[str, Any], dict[str, Any], Mapping[str, int], str], int
    ]
    event_receipt_map: Callable[
        [dict[str, Any]], Mapping[int, Mapping[str, Any]]
    ]
    land_speed_feet: Callable[..., int | None]
    legal_land_paths: Callable[..., Sequence[Mapping[str, Any]]]
    apply_land_path: Callable[..., Mapping[str, Any]]

    def __post_init__(self) -> None:
        for contract_field in fields(self):
            if not callable(getattr(self, contract_field.name)):
                raise TypeError(
                    f"Slink host {contract_field.name} must be callable"
                )


def _mechanic_for(ability: Mapping[str, Any]) -> Mapping[str, Any]:
    mechanic = ability.get("mechanic")
    if (
        ability.get("supported") is not True
        or ability.get("ruleRef") != PROVIDER_RULE_ID
        or not isinstance(mechanic, Mapping)
        or mechanic != _semantic_projection()["mechanic"]
    ):
        raise EngineInputError("Slink mechanic is invalid")
    return mechanic


def _active(participant: Mapping[str, Any]) -> bool:
    hit_points = participant.get("hitPoints")
    return bool(
        participant.get("defeated") is not True
        and participant.get("incapacitated") is not True
        and participant.get("reactionAvailable") is True
        and (
            not isinstance(hit_points, Mapping)
            or type(hit_points.get("current")) is not int
            or int(hit_points["current"]) > 0
        )
    )


def _coordinate(value: object, label: str) -> dict[str, int]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"x", "y"}
        or type(value.get("x")) is not int
        or type(value.get("y")) is not int
    ):
        raise EngineInputError(f"{label} is invalid")
    return {"x": int(value["x"]), "y": int(value["y"])}


def _path(value: object, label: str) -> list[dict[str, int]]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > MAX_PATH_SQUARES
    ):
        raise EngineInputError(f"{label} must contain one or two squares")
    result = [
        _coordinate(square, f"{label}[{index}]")
        for index, square in enumerate(value)
    ]
    if len({(square["x"], square["y"]) for square in result}) != len(result):
        raise EngineInputError(f"{label} repeats a square")
    return result


def _validated_path_witness(
    witness: object,
    *,
    maximum_feet: int,
) -> dict[str, Any]:
    if not isinstance(witness, Mapping) or set(witness) != {
        "path",
        "position",
        "occupiedSquares",
        "movementSpentFeet",
        "diagonalStepsBefore",
        "diagonalStepsAfter",
        "deferredExposureKinds",
        "releasedEffectIds",
    }:
        raise EngineInputError("Slink land-path witness is invalid")
    path = _path(witness.get("path"), "Slink land path")
    position = _coordinate(witness.get("position"), "Slink endpoint")
    occupied = witness.get("occupiedSquares")
    spent = witness.get("movementSpentFeet")
    before = witness.get("diagonalStepsBefore")
    after = witness.get("diagonalStepsAfter")
    deferred = witness.get("deferredExposureKinds")
    released = witness.get("releasedEffectIds")
    if (
        position != path[-1]
        or not isinstance(occupied, list)
        or not occupied
        or any(
            _coordinate(square, "Slink occupied square") != square
            for square in occupied
        )
        or type(spent) is not int
        or not 0 < spent <= maximum_feet
        or before != 0
        or type(after) is not int
        or after < 0
        or deferred != []
        or not isinstance(released, list)
        or any(type(effect_id) is not str or not effect_id for effect_id in released)
        or released != sorted(set(released))
    ):
        raise EngineInputError("Slink land-path witness is invalid")
    return {
        "path": path,
        "position": position,
        "occupiedSquares": deepcopy(occupied),
        "movementSpentFeet": spent,
        "diagonalStepsBefore": 0,
        "diagonalStepsAfter": after,
        "deferredExposureKinds": [],
        "releasedEffectIds": list(released),
    }


def _legal_options(
    state: dict[str, Any],
    participant: dict[str, Any],
    ability: Mapping[str, Any],
    host: SlinkRuntimeHost,
) -> tuple[int, list[dict[str, Any]]]:
    _mechanic_for(ability)
    speed = host.land_speed_feet(
        state,
        participant,
        required_for="Slink",
    )
    if type(speed) is not int or speed <= 0:
        return 0, []
    maximum = min(MAXIMUM_DISTANCE_FEET, speed)
    raw_witnesses = host.legal_land_paths(
        state,
        participant,
        maximum_feet=maximum,
        starting_diagonal_count=0,
        triggers_movement_reactions=False,
        reject_nested_exposures=True,
    )
    if (
        not isinstance(raw_witnesses, Sequence)
        or isinstance(raw_witnesses, (str, bytes))
        or len(raw_witnesses) > MAX_LEGAL_PATHS
    ):
        raise EngineInputError("Slink legal land-path census is invalid")
    foes = tuple(host.foe_ids(state, str(participant["id"])))
    if (
        any(type(foe_id) is not str or not foe_id for foe_id in foes)
        or len(foes) != len(set(foes))
    ):
        raise EngineInputError("Slink foe census is invalid")
    result: list[dict[str, Any]] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    for raw in raw_witnesses:
        witness = _validated_path_witness(raw, maximum_feet=maximum)
        key = tuple((square["x"], square["y"]) for square in witness["path"])
        if key in seen:
            raise EngineInputError("Slink legal path is duplicated")
        seen.add(key)
        if all(
            host.distance_from_position(
                state,
                participant,
                witness["position"],
                foe_id,
            )
            > 5
            for foe_id in foes
        ):
            result.append(witness)
    result.sort(
        key=lambda item: (
            item["movementSpentFeet"],
            tuple((square["y"], square["x"]) for square in item["path"]),
        )
    )
    return maximum, result


def _eligible_context(
    state: dict[str, Any],
    participant_id: str,
    trigger_participant_id: str,
    host: SlinkRuntimeHost,
) -> tuple[dict[str, Any], dict[str, Any], int, list[dict[str, Any]]] | None:
    participants = host.participant_map(state)
    participant = participants.get(participant_id)
    trigger = participants.get(trigger_participant_id)
    if (
        participant is None
        or trigger is None
        or participant_id == trigger_participant_id
        or not _active(participant)
        or host.participant_distance(state, participant_id, trigger_participant_id)
        not in {0, 5}
    ):
        return None
    ability = host.ability_by_mechanic(
        host.definition_for(state, participant), MECHANIC_TYPE
    )
    if ability is None:
        return None
    maximum, options = _legal_options(state, participant, ability, host)
    if not options:
        return None
    return participant, ability, maximum, options


def _trigger_receipt(
    state: dict[str, Any],
    trigger_participant_id: str,
    trigger_event_sequence: int,
    host: SlinkRuntimeHost,
) -> Mapping[str, Any]:
    receipts = host.event_receipt_map(state)
    if not isinstance(receipts, Mapping):
        raise EngineInputError("Slink event receipt index is invalid")
    event = receipts.get(trigger_event_sequence)
    participants = host.participant_map(state)
    trigger = participants.get(trigger_participant_id)
    if (
        not isinstance(event, Mapping)
        or event.get("sequence") != trigger_event_sequence
        or event.get("actorId") != trigger_participant_id
        or event.get("endedMoveAction") is not True
        or event.get("triggersMovementReactions") is not True
        or (
            event.get("forcedMovement") is not None
            and event.get("forcedMovement") is not False
        )
        or trigger is None
        or event.get("position") != trigger.get("position")
        or event.get("occupiedSquares") != trigger.get("occupiedSquares")
        or not isinstance(event.get("path"), list)
        or not event["path"]
        or event["path"][-1] != event.get("position")
    ):
        raise EngineInputError(
            "Slink trigger event receipt or completed movement pose is invalid"
        )
    return event


def observe_post_event(
    state: Mapping[str, Any],
    event: Mapping[str, Any],
    host: SlinkRuntimeHost,
) -> tuple[dict[str, Any], ...]:
    """Return initiative-ordered candidates after an exact qualifying move."""

    if (
        event.get("endedMoveAction") is not True
        or event.get("triggersMovementReactions") is not True
        or (
            event.get("forcedMovement") is not None
            and event.get("forcedMovement") is not False
        )
    ):
        return ()
    if state.get("pendingDecision") is not None:
        return ()
    sequence = event.get("sequence")
    mover_id = event.get("actorId")
    if type(sequence) is not int or sequence <= 0:
        raise EngineInputError("Slink trigger event sequence is invalid")
    if type(mover_id) is not str or not mover_id:
        raise EngineInputError("Slink trigger participant is invalid")
    mutable = state  # family callbacks are read-only during census
    participants = host.participant_map(mutable)  # type: ignore[arg-type]
    if mover_id not in participants:
        return ()
    mover = participants[mover_id]
    if (
        event.get("position") != mover.get("position")
        or event.get("occupiedSquares") != mover.get("occupiedSquares")
        or not isinstance(event.get("path"), list)
        or not event["path"]
        or event["path"][-1] != event.get("position")
    ):
        raise EngineInputError("Slink trigger movement pose is invalid")
    turn = state.get("turn")
    order = turn.get("order") if isinstance(turn, Mapping) else None
    if (
        not isinstance(order, list)
        or any(type(participant_id) is not str for participant_id in order)
        or len(order) != len(set(order))
    ):
        raise EngineInputError("Slink initiative order is invalid")
    return tuple(
        {
            "kind": QUEUE_KIND,
            "participantId": participant_id,
            "triggerParticipantId": mover_id,
            "triggerEventSequence": sequence,
        }
        for participant_id in order
        if _eligible_context(
            mutable,  # type: ignore[arg-type]
            participant_id,
            mover_id,
            host,
        )
        is not None
    )


def build_pending_decision(
    state: Mapping[str, Any],
    queued: Mapping[str, Any],
    host: SlinkRuntimeHost,
) -> dict[str, Any] | None:
    """Reprove one queued candidate and expose only current legal paths."""

    if set(queued) != {
        "kind",
        "participantId",
        "triggerParticipantId",
        "triggerEventSequence",
    } or queued.get("kind") != QUEUE_KIND:
        raise EngineInputError("queued Slink candidate is invalid")
    participant_id = queued.get("participantId")
    trigger_id = queued.get("triggerParticipantId")
    sequence = queued.get("triggerEventSequence")
    if (
        type(participant_id) is not str
        or not participant_id
        or type(trigger_id) is not str
        or not trigger_id
        or type(sequence) is not int
        or sequence <= 0
    ):
        raise EngineInputError("queued Slink candidate is invalid")
    _trigger_receipt(
        state,  # type: ignore[arg-type]
        trigger_id,
        sequence,
        host,
    )
    context = _eligible_context(
        state,  # type: ignore[arg-type]
        participant_id,
        trigger_id,
        host,
    )
    if context is None:
        return None
    _participant, ability, maximum, options = context
    return {
        "type": "Reaction",
        "mechanicType": MECHANIC_TYPE,
        "participantId": participant_id,
        "triggerParticipantId": trigger_id,
        "triggerEventSequence": sequence,
        "trigger": "another-creature-ended-reactive-movement-nearby",
        "options": [
            {
                "abilityId": ability["id"],
                "use": [True, False],
                "reactionCost": 1,
                "movementMode": "land",
                "maximumDistanceFeet": maximum,
                "legalPaths": [deepcopy(item["path"]) for item in options],
                "ruleRef": PROVIDER_RULE_ID,
            }
        ],
    }


def resolve_reaction(
    state: dict[str, Any],
    actor_id: str,
    action: Mapping[str, Any],
    ability: Mapping[str, Any],
    decision: Mapping[str, Any],
    host: SlinkRuntimeHost,
) -> dict[str, Any]:
    """Resolve accept/decline after re-proving trigger, path, and endpoint."""

    use = action.get("use")
    expected = {"type", "abilityId", "use"}
    if use is True:
        expected.update({"movementMode", "path"})
    if (
        set(action) != expected
        or action.get("type") != "Reaction"
        or action.get("abilityId") != ability.get("id")
        or type(use) is not bool
    ):
        raise EngineInputError("Slink reaction input is invalid")
    _mechanic_for(ability)
    trigger_id = decision.get("triggerParticipantId")
    if (
        decision.get("type") != "Reaction"
        or decision.get("mechanicType") != MECHANIC_TYPE
        or decision.get("participantId") != actor_id
        or decision.get("trigger")
        != "another-creature-ended-reactive-movement-nearby"
        or type(trigger_id) is not str
    ):
        raise EngineInputError("pending Slink decision is invalid")
    sequence = decision.get("triggerEventSequence")
    if type(sequence) is not int or sequence <= 0:
        raise EngineInputError("pending Slink trigger event sequence is invalid")
    _trigger_receipt(state, trigger_id, sequence, host)
    context = _eligible_context(state, actor_id, trigger_id, host)
    if context is None:
        raise EngineInputError("Slink trigger or options are no longer valid")
    participant, current_ability, maximum, options = context
    if current_ability.get("id") != ability.get("id"):
        raise EngineInputError("pending Slink ability is invalid")
    movement = None
    if use:
        if action.get("movementMode") != "land":
            raise EngineInputError("bounded Slink supports only land Stride")
        path = _path(action.get("path"), "Slink path")
        matching = [item for item in options if item["path"] == path]
        if len(matching) != 1:
            raise EngineInputError("Slink path is not currently legal")
        witness = matching[0]
        turn = state.get("turn")
        active_diagonals = (
            turn.get("diagonalStepsThisTurn")
            if isinstance(turn, Mapping)
            else None
        )
        if type(active_diagonals) is not int or active_diagonals < 0:
            raise EngineInputError("active turn diagonal counter is invalid")
        raw_movement = host.apply_land_path(
            state,
            participant,
            path,
            maximum_feet=maximum,
            starting_diagonal_count=0,
            triggers_movement_reactions=False,
            reject_nested_exposures=True,
        )
        applied = _validated_path_witness(
            raw_movement,
            maximum_feet=maximum,
        )
        if applied != witness:
            raise EngineInputError("resolved Slink path disagrees with preview")
        current_turn = state.get("turn")
        if (
            not isinstance(current_turn, Mapping)
            or current_turn.get("diagonalStepsThisTurn") != active_diagonals
        ):
            raise EngineInputError("Slink changed the active turn diagonal counter")
        participant["reactionAvailable"] = False
        movement = {
            "type": "Stride",
            "movementMode": "land",
            **deepcopy(applied),
            "triggersMovementReactions": False,
            "activeTurnDiagonalStepsUnchanged": {
                "before": active_diagonals,
                "after": active_diagonals,
            },
        }
    return {
        "mechanicType": MECHANIC_TYPE,
        "abilityId": ability["id"],
        "ruleRef": PROVIDER_RULE_ID,
        "triggerParticipantId": trigger_id,
        "triggerEventSequence": decision["triggerEventSequence"],
        "used": use,
        "movement": movement,
    }


def validate_runtime_state(
    state: dict[str, Any],
    host: SlinkRuntimeHost,
) -> None:
    """Authenticate every serialized Slink interruption against live evidence."""

    pending = state.get("pendingDecision")
    if isinstance(pending, Mapping) and pending.get("mechanicType") == MECHANIC_TYPE:
        sequence = pending.get("triggerEventSequence")
        trigger_id = pending.get("triggerParticipantId")
        if type(sequence) is not int or type(trigger_id) is not str:
            raise EngineInputError("pending Slink trigger authority is invalid")
        _trigger_receipt(state, trigger_id, sequence, host)
        rebuilt = build_pending_decision(
            state,
            {
                "kind": QUEUE_KIND,
                "participantId": pending.get("participantId"),
                "triggerParticipantId": trigger_id,
                "triggerEventSequence": sequence,
            },
            host,
        )
        if rebuilt != pending:
            raise EngineInputError("pending Slink decision is not reproducible")
    queue = state.get("pendingReactionQueue")
    if queue is None:
        return
    if not isinstance(queue, list):
        raise EngineInputError("pending reaction queue is invalid")
    for candidate in queue:
        if not isinstance(candidate, Mapping) or candidate.get("kind") != QUEUE_KIND:
            continue
        participant_id = candidate.get("participantId")
        trigger_id = candidate.get("triggerParticipantId")
        sequence = candidate.get("triggerEventSequence")
        if (
            type(participant_id) is not str
            or type(trigger_id) is not str
            or type(sequence) is not int
        ):
            raise EngineInputError("queued Slink trigger authority is invalid")
        _trigger_receipt(state, trigger_id, sequence, host)


def project_public_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    """Return a closed, semantic, source-free controller projection."""

    if (
        decision.get("type") != "Reaction"
        or decision.get("mechanicType") != MECHANIC_TYPE
        or set(decision) != {
            "type",
            "mechanicType",
            "participantId",
            "triggerParticipantId",
            "triggerEventSequence",
            "trigger",
            "options",
        }
        or not isinstance(decision.get("options"), list)
        or len(decision["options"]) != 1
    ):
        raise EngineInputError("pending Slink decision projection is invalid")
    result = deepcopy(dict(decision))
    option = result["options"][0]
    if not isinstance(option, dict) or option.get("ruleRef") != PROVIDER_RULE_ID:
        raise EngineInputError("pending Slink option projection is invalid")
    forbidden = {"source", "sourceId", "locator", "receipt", "rules"}
    stack: list[object] = [result]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if forbidden.intersection(item):
                raise EngineInputError("Slink public projection leaked source data")
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return result


def render_reaction_event(event: Mapping[str, Any]) -> str:
    """Render one source-free Slink reaction result."""

    if (
        event.get("mechanicType") != MECHANIC_TYPE
        or event.get("ruleRef") != PROVIDER_RULE_ID
        or type(event.get("used")) is not bool
    ):
        raise EngineInputError("Slink event is invalid")
    if event["used"] is False:
        if event.get("movement") is not None:
            raise EngineInputError("declined Slink event cannot move")
        return "Slink declined."
    movement = event.get("movement")
    if (
        not isinstance(movement, Mapping)
        or movement.get("type") != "Stride"
        or movement.get("triggersMovementReactions") is not False
    ):
        raise EngineInputError("accepted Slink event movement is invalid")
    spent = movement.get("movementSpentFeet")
    if type(spent) is not int or spent <= 0:
        raise EngineInputError("accepted Slink distance is invalid")
    return f"Slink used: Stride {spent} feet without triggering reactions."


__all__ = [
    "CompiledSlink",
    "ENTITY_ID",
    "FAMILY_ID",
    "MAXIMUM_DISTANCE_FEET",
    "MECHANIC_TYPE",
    "POST_EVENT_HOOK_ID",
    "PROVIDER_RULE_ID",
    "QUEUE_KIND",
    "RUNTIME_DEFERRALS",
    "SOURCE_DESCRIPTION",
    "SOURCE_SELECTION_SHA256",
    "SOURCE_TRIGGER",
    "SlinkRuntimeHost",
    "build_pending_decision",
    "compile_slink",
    "observe_post_event",
    "project_public_decision",
    "render_reaction_event",
    "resolve_reaction",
    "validate_runtime_state",
    "select_slink_source",
]

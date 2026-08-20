"""Compile the Orc Commander's exact Battle Cry activity."""

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
    RawSourceArray,
    RawSourceObject,
    RuleReference,
)
from .source_authority import (
    RawMemberStep,
    SourceAuthorityAdapter,
    raw_source_sha256,
)


SOURCE_ID = "core-mc1"
LOCATOR = "259.3"
SECTION_ID = "core-mc1:orc"
CREATURE_NAME = "Orc Commander"
ABILITY_ID = "battle-cry"
MECHANIC_TYPE = "orc-battle-cry-status-bonus"

TRAITS = ("auditory", "concentrate", "emotion", "mental")
DESCRIPTION = (
    "Bellowing mightily, the orc commander gives themself and all orc "
    "allies within 60 feet a +1 status bonus to attack and damage rolls "
    "until the start of the orc commander's next turn."
)

ABILITY_RULE = {"sourceId": SOURCE_ID, "locator": LOCATOR}
DUPLICATE_EFFECTS_RULE = {"sourceId": "core-pc1", "locator": "399.1"}
STATUS_BONUS_RULE = {"sourceId": "core-pc1", "locator": "400.2"}
DURATION_RULE = {"sourceId": "core-pc1", "locator": "426.2"}
RANGE_RULE = {"sourceId": "core-pc1", "locator": "426.3"}
LINE_OF_EFFECT_RULE = {"sourceId": "core-pc1", "locator": "426.6"}
TRAIT_RULE = {"sourceId": "core-pc1", "locator": "452.1"}

SOURCE_RECEIPT = {
    "targetPath": (("Orc", 1),),
    "carrierPath": (("^.creature", 4),),
    "selectionPath": (("!.Battle Cry", 26),),
    "carrierBlockSha256": (
        "9082b1c4194f81c6b37ea7fba8f61c2b7694c96c73ffc758fc2672881abf5a52"
    ),
    "selectionSha256": (
        "854c34dddc20a3b7892dd5bdf58f086fb3aae6fc4897282dd984c4d184824145"
    ),
}

_EXACT_VALUE = RawSourceObject(
    (
        ("Action", "single"),
        ("Traits", RawSourceArray(TRAITS)),
        ("Description", DESCRIPTION),
    )
)


@dataclass(frozen=True, slots=True)
class BattleCryHost:
    """Kernel operations required by the Battle Cry runtime algorithm."""

    definition_for: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    participant_map: Callable[[dict[str, Any]], dict[str, dict[str, Any]]]
    participant_distance: Callable[[dict[str, Any], str, str], int]
    participants_have_line_of_effect: Callable[[dict[str, Any], str, str], bool]
    trait_immune: Callable[[dict[str, Any], dict[str, Any], str], bool]
    require_action: Callable[..., tuple[dict[str, Any], dict[str, Any]]]
    require_action_traits: Callable[[dict[str, Any], str, str, set[str]], None]
    state_effects: Callable[[dict[str, Any]], list[dict[str, Any]]]
    remove_effect_ids: Callable[[dict[str, Any], list[str]], list[str]]
    next_event_sequence: Callable[[dict[str, Any]], int]
    action_event: Callable[..., dict[str, Any]]
    event_receipt: Callable[[dict[str, Any], int], dict[str, Any] | None]

    def __post_init__(self) -> None:
        for field in fields(self):
            if not callable(getattr(self, field.name)):
                raise TypeError(f"Battle Cry host {field.name} must be callable")


def _mechanic() -> dict[str, Any]:
    return {
        "type": MECHANIC_TYPE,
        "targeting": {
            "selection": "automatic-at-use",
            "recipients": ["self", "orc-allies"],
            "rangeFeet": 60,
            "requiresLineOfEffect": True,
            "fixedForDuration": True,
        },
        "bonuses": [
            {
                "type": "status",
                "value": 1,
                "appliesTo": "attack-rolls",
            },
            {
                "type": "status",
                "value": 1,
                "appliesTo": "damage-rolls",
            },
        ],
        "duration": {
            "unit": "rounds",
            "value": 1,
            "expires": "start-of-source-next-turn",
        },
        "duplicateEffects": "newer-equal-effect-governs",
        "rules": {
            "ability": deepcopy(ABILITY_RULE),
            "duplicateEffects": deepcopy(DUPLICATE_EFFECTS_RULE),
            "statusBonuses": deepcopy(STATUS_BONUS_RULE),
            "duration": deepcopy(DURATION_RULE),
            "range": deepcopy(RANGE_RULE),
            "lineOfEffect": deepcopy(LINE_OF_EFFECT_RULE),
            "traits": deepcopy(TRAIT_RULE),
        },
    }


def compile_battle_cry(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact current Monster Core Battle Cry member."""

    if (
        source.source_id != SOURCE_ID
        or source.locator != LOCATOR
        or source.creature_name != CREATURE_NAME
        or source.source_label != "Battle Cry"
        or source.raw_member.key != "!.Battle Cry"
        or source.kind != "activity"
        or source.action_cost != 1
        or source.traits != TRAITS
        or source.trigger
        or source.description != DESCRIPTION
        or source.raw_member.value != _EXACT_VALUE
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=_mechanic(),
        rule=RuleReference(SOURCE_ID, LOCATOR),
        traits=TRAITS,
    )


def battle_cry_spec(value: object, /) -> dict[str, Any]:
    """Return the exact admitted runtime mechanic or reject it."""

    mechanic = value.get("mechanic") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("id") != ABILITY_ID
        or value.get("name") != "Battle Cry"
        or value.get("kind") != "activity"
        or value.get("actionCost") != 1
        or value.get("traits") != list(TRAITS)
        or value.get("description") != DESCRIPTION
        or value.get("supported") is not True
        or value.get("rule") != ABILITY_RULE
        or mechanic != _mechanic()
    ):
        raise EngineInputError("Orc Commander Battle Cry mechanic is invalid")
    return deepcopy(mechanic)


def ability_for_definition(
    definition: Mapping[str, Any],
    /,
) -> dict[str, Any] | None:
    """Return the definition's sole exact admitted Battle Cry ability."""

    matches = [
        ability
        for ability in definition.get("abilities") or []
        if (
            isinstance(ability, dict)
            and ability.get("id") == ABILITY_ID
            and ability.get("supported") is True
        )
    ]
    if len(matches) > 1:
        raise EngineInputError("creature has ambiguous Battle Cry abilities")
    if not matches:
        return None
    battle_cry_spec(matches[0])
    return matches[0]


def recipient_contexts(
    state: dict[str, Any],
    actor: dict[str, Any],
    host: BattleCryHost,
    /,
) -> list[dict[str, Any]]:
    """Resolve the fixed self-and-orc-ally recipient set."""

    ability = ability_for_definition(host.definition_for(state, actor))
    if ability is None:
        return []
    mechanic = battle_cry_spec(ability)
    range_feet = int(mechanic["targeting"]["rangeFeet"])
    contexts = []
    for target in state["participants"]:
        target_id = str(target["id"])
        is_self = target_id == actor["id"]
        target_traits = set(
            host.definition_for(state, target).get("traits") or []
        )
        is_orc_ally = (
            not is_self
            and target.get("side") == actor.get("side")
            and "orc" in target_traits
        )
        if not is_self and not is_orc_ally:
            continue
        inactive = bool(
            target.get("defeated")
            or target.get("incapacitated")
            or int(target.get("hitPoints", {}).get("current", 0)) <= 0
        )
        distance = (
            0
            if is_self
            else host.participant_distance(
                state,
                str(actor["id"]),
                target_id,
            )
        )
        line_of_effect = (
            True
            if is_self
            else host.participants_have_line_of_effect(
                state,
                str(actor["id"]),
                target_id,
            )
        )
        immune_traits = [
            trait
            for trait in ("auditory", "emotion", "mental")
            if host.trait_immune(state, target, trait)
        ]
        affected = bool(
            not inactive
            and distance <= range_feet
            and line_of_effect
            and not immune_traits
        )
        contexts.append(
            {
                "targetId": target_id,
                "recipient": "self" if is_self else "orc-ally",
                "distanceFeet": distance,
                "rangeFeet": range_feet,
                "lineOfEffect": line_of_effect,
                "immuneTraits": immune_traits,
                "affected": affected,
                "unaffectedReasons": [
                    reason
                    for reason, applies in (
                        ("inactive", inactive),
                        ("outside-range", distance > range_feet),
                        ("no-line-of-effect", not line_of_effect),
                        ("trait-immunity", bool(immune_traits)),
                    )
                    if applies
                ],
            }
        )
    if not any(context["targetId"] == actor["id"] for context in contexts):
        raise EngineInputError("Battle Cry source recipient is missing")
    return contexts


def _effect_without_remaining(
    effect: dict[str, Any],
) -> tuple[dict[str, Any], int | None]:
    snapshot = deepcopy(effect)
    duration = snapshot.get("duration")
    remaining = (
        duration.pop("remaining", None)
        if isinstance(duration, dict)
        else None
    )
    return snapshot, remaining


def _validate_effect(
    state: dict[str, Any],
    effect: dict[str, Any],
    host: BattleCryHost,
) -> None:
    expected_keys = {
        "id",
        "kind",
        "sourceParticipantId",
        "targetParticipantId",
        "sourceAbilityId",
        "source",
        "traits",
        "bonuses",
        "duration",
        "creation",
        "rule",
        "rules",
    }
    participants = host.participant_map(state)
    source_id = str(effect.get("sourceParticipantId") or "")
    target_id = str(effect.get("targetParticipantId") or "")
    source = participants.get(source_id)
    target = participants.get(target_id)
    ability = (
        ability_for_definition(host.definition_for(state, source))
        if source is not None
        else None
    )
    mechanic = battle_cry_spec(ability) if ability is not None else None
    target_traits = (
        set(host.definition_for(state, target).get("traits") or [])
        if target is not None
        else set()
    )
    creation = effect.get("creation")
    duration = effect.get("duration")
    remaining = duration.get("remaining") if isinstance(duration, dict) else None
    turn = state.get("turn")
    order = turn.get("order") if isinstance(turn, dict) else None
    current_step = turn.get("initiativeStep") if isinstance(turn, dict) else None
    if (
        set(effect) != expected_keys
        or effect.get("kind") != MECHANIC_TYPE
        or source is None
        or target is None
        or ability is None
        or mechanic is None
        or effect.get("sourceAbilityId") != ABILITY_ID
        or effect.get("source") != ABILITY_RULE
        or effect.get("rule") != ABILITY_RULE
        or effect.get("rules") != mechanic["rules"]
        or effect.get("traits") != list(TRAITS)
        or effect.get("bonuses") != mechanic["bonuses"]
        or not (
            target_id == source_id
            or (
                target.get("side") == source.get("side")
                and "orc" in target_traits
            )
        )
        or any(
            host.trait_immune(state, target, trait)
            for trait in TRAITS
            if trait in {"auditory", "emotion", "mental"}
        )
        or not isinstance(creation, dict)
        or set(creation) != {"eventSequence", "initiativeStep", "round"}
        or isinstance(creation.get("eventSequence"), bool)
        or not isinstance(creation.get("eventSequence"), int)
        or int(creation["eventSequence"]) <= 0
        or isinstance(creation.get("initiativeStep"), bool)
        or not isinstance(creation.get("initiativeStep"), int)
        or int(creation["initiativeStep"]) < 0
        or isinstance(creation.get("round"), bool)
        or not isinstance(creation.get("round"), int)
        or int(creation["round"]) < 1
        or not isinstance(duration, dict)
        or set(duration)
        != {"unit", "remaining", "decrementAt", "sourceUnit", "rule"}
        or duration.get("unit") != "rounds"
        or duration.get("decrementAt")
        != {"phase": "start-turn", "participantId": source_id}
        or duration.get("sourceUnit")
        != "until the start of the source's next turn"
        or duration.get("rule") != DURATION_RULE
        or isinstance(remaining, bool)
        or not isinstance(remaining, int)
        or not isinstance(order, list)
        or not order
        or isinstance(current_step, bool)
        or not isinstance(current_step, int)
        or current_step < int(creation["initiativeStep"])
        or remaining
        != 1 - ((current_step - int(creation["initiativeStep"])) // len(order))
    ):
        raise EngineInputError("Battle Cry effect contract is invalid")
    event_sequence = int(creation["eventSequence"])
    expected_id = f"{MECHANIC_TYPE}:{event_sequence}:{source_id}:{target_id}"
    creation_event = host.event_receipt(state, event_sequence)
    results = (
        creation_event.get("targetResults")
        if isinstance(creation_event, dict)
        else None
    )
    matches = (
        [
            result
            for result in results
            if (
                isinstance(result, dict)
                and result.get("targetId") == target_id
                and result.get("affected") is True
                and isinstance(result.get("effect"), dict)
                and result["effect"].get("id") == effect.get("id")
            )
        ]
        if isinstance(results, list)
        else []
    )
    current_snapshot, _current_remaining = _effect_without_remaining(effect)
    event_snapshot, initial_remaining = (
        _effect_without_remaining(matches[0]["effect"])
        if len(matches) == 1
        else ({}, None)
    )
    if (
        effect.get("id") != expected_id
        or not isinstance(creation_event, dict)
        or creation_event.get("type") != "activity"
        or creation_event.get("actorId") != source_id
        or creation_event.get("abilityId") != ABILITY_ID
        or creation_event.get("initiativeStep") != creation["initiativeStep"]
        or creation_event.get("round") != creation["round"]
        or len(matches) != 1
        or initial_remaining != 1
        or event_snapshot != current_snapshot
    ):
        raise EngineInputError("Battle Cry creation event is invalid")


def active_effects(
    state: dict[str, Any],
    host: BattleCryHost,
    /,
    *,
    target_id: str | None = None,
) -> list[dict[str, Any]]:
    """Validate and return fixed-recipient Battle Cry status bonuses."""

    result = []
    seen_ids: set[str] = set()
    seen_sources_and_targets: set[tuple[str, str]] = set()
    for effect in host.state_effects(state):
        if effect.get("kind") != MECHANIC_TYPE:
            continue
        _validate_effect(state, effect, host)
        effect_id = str(effect.get("id") or "")
        key = (
            str(effect.get("sourceParticipantId") or ""),
            str(effect.get("targetParticipantId") or ""),
        )
        if (
            not effect_id
            or effect_id in seen_ids
            or key in seen_sources_and_targets
        ):
            raise EngineInputError("Battle Cry effect identity is invalid")
        seen_ids.add(effect_id)
        seen_sources_and_targets.add(key)
        if target_id is None or key[1] == target_id:
            result.append(effect)
    return result


def build_activity_options(
    state: dict[str, Any],
    actor: dict[str, Any],
    ability: dict[str, Any],
    host: BattleCryHost,
    /,
) -> tuple[dict[str, Any], ...]:
    """Project Battle Cry using its automatic current recipient witness."""

    compiled = ability_for_definition(host.definition_for(state, actor))
    if compiled is None:
        return ()
    if compiled is not ability:
        raise EngineInputError("Battle Cry compiled ability is invalid")
    mechanic = battle_cry_spec(ability)
    blocked = []
    turn = state.get("turn")
    if (
        not isinstance(turn, dict)
        or turn.get("activeParticipantId") != actor.get("id")
        or turn.get("phase") != "acting"
    ):
        blocked.append("not-active-turn")
    if int((turn or {}).get("actionsRemaining", 0)) < 1:
        blocked.append("insufficient-actions")
    contexts = recipient_contexts(state, actor, host)
    return (
        {
            "abilityId": ABILITY_ID,
            "abilityName": "Battle Cry",
            "actionCost": 1,
            "traits": list(TRAITS),
            "available": not blocked,
            "blockedBy": blocked,
            "targetResults": contexts,
            "affectedTargetIds": [
                context["targetId"]
                for context in contexts
                if context["affected"]
            ],
            "bonuses": deepcopy(mechanic["bonuses"]),
            "duration": deepcopy(mechanic["duration"]),
            "rule": deepcopy(ability["rule"]),
            "rules": deepcopy(mechanic["rules"]),
        },
    )


def resolve_activity(
    state: dict[str, Any],
    actor_id: str,
    action: Mapping[str, Any],
    ability: dict[str, Any],
    host: BattleCryHost,
    /,
) -> dict[str, Any]:
    """Grant fixed one-round status bonuses to self and nearby orc allies."""

    if set(action) != {"type", "abilityId"}:
        raise EngineInputError(
            "Battle Cry payload must contain exactly type and abilityId"
        )
    actor, _participants = host.require_action(state, actor_id, cost=1)
    if (
        ability.get("id") != ABILITY_ID
        or ability_for_definition(host.definition_for(state, actor)) is not ability
    ):
        raise EngineInputError("Battle Cry compiled ability is invalid")
    mechanic = battle_cry_spec(ability)
    host.require_action_traits(state, actor_id, "Battle Cry", set(TRAITS))
    contexts = recipient_contexts(state, actor, host)
    replaced_effect_ids = host.remove_effect_ids(
        state,
        [
            str(effect["id"])
            for effect in active_effects(state, host)
            if effect.get("sourceParticipantId") == actor_id
        ],
    )
    event_sequence = host.next_event_sequence(state)
    creation = {
        "eventSequence": event_sequence,
        "initiativeStep": int(state["turn"]["initiativeStep"]),
        "round": int(state["turn"]["round"]),
    }
    effects_by_target: dict[str, dict[str, Any]] = {}
    for context in contexts:
        if context["affected"] is not True:
            continue
        target_id = str(context["targetId"])
        effect = {
            "id": f"{MECHANIC_TYPE}:{event_sequence}:{actor_id}:{target_id}",
            "kind": MECHANIC_TYPE,
            "sourceParticipantId": actor_id,
            "targetParticipantId": target_id,
            "sourceAbilityId": ABILITY_ID,
            "source": deepcopy(ABILITY_RULE),
            "traits": list(TRAITS),
            "bonuses": deepcopy(mechanic["bonuses"]),
            "duration": {
                "unit": "rounds",
                "remaining": 1,
                "decrementAt": {
                    "phase": "start-turn",
                    "participantId": actor_id,
                },
                "sourceUnit": "until the start of the source's next turn",
                "rule": deepcopy(DURATION_RULE),
            },
            "creation": deepcopy(creation),
            "rule": deepcopy(ABILITY_RULE),
            "rules": deepcopy(mechanic["rules"]),
        }
        host.state_effects(state).append(effect)
        effects_by_target[target_id] = effect
    actions_before = int(state["turn"]["actionsRemaining"])
    state["turn"]["actionsRemaining"] = actions_before - 1
    target_results = [
        {
            **deepcopy(context),
            "effect": deepcopy(effects_by_target.get(str(context["targetId"]))),
        }
        for context in contexts
    ]
    return host.action_event(
        state,
        "activity",
        actor_id,
        mechanicType=MECHANIC_TYPE,
        abilityId=ABILITY_ID,
        abilityName="Battle Cry",
        actionCost=1,
        actions={
            "before": actions_before,
            "after": int(state["turn"]["actionsRemaining"]),
        },
        traits=list(TRAITS),
        targetResults=target_results,
        affectedTargetIds=list(effects_by_target),
        bonuses=deepcopy(mechanic["bonuses"]),
        duration=deepcopy(mechanic["duration"]),
        replacedEffectIds=replaced_effect_ids,
        initiativeStep=int(state["turn"]["initiativeStep"]),
        round=int(state["turn"]["round"]),
        rule=deepcopy(ability["rule"]),
        rules=deepcopy(mechanic["rules"]),
    )


def _participant_name(
    participant_id: object,
    participants: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
) -> str:
    normalized = str(participant_id or "")
    participant = participants.get(normalized)
    definition = (
        definitions.get(participant.get("creatureId"))
        if isinstance(participant, Mapping)
        else None
    )
    creature_name = (
        str(definition.get("name") or normalized)
        if isinstance(definition, Mapping)
        else normalized
    )
    return f"{creature_name} ({normalized})"


def render_event(
    event: Mapping[str, Any],
    participants: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
    /,
) -> str:
    """Render one exact Battle Cry activity event."""

    if (
        not isinstance(event, Mapping)
        or event.get("type") != "activity"
        or event.get("mechanicType") != MECHANIC_TYPE
        or event.get("abilityId") != ABILITY_ID
    ):
        raise EngineInputError("Battle Cry transcript event is invalid")
    affected_ids = event.get("affectedTargetIds")
    target_results = event.get("targetResults")
    if (
        not isinstance(affected_ids, list)
        or any(not isinstance(item, str) or not item for item in affected_ids)
        or not isinstance(target_results, list)
        or any(not isinstance(item, Mapping) for item in target_results)
    ):
        raise EngineInputError("Battle Cry transcript targets are invalid")
    affected = [
        _participant_name(target_id, participants, definitions)
        for target_id in affected_ids
    ]
    excluded = [
        result
        for result in target_results
        if result.get("affected") is False
    ]
    for result in excluded:
        reasons = result.get("unaffectedReasons")
        if (
            not isinstance(result.get("targetId"), str)
            or not isinstance(reasons, list)
            or any(not isinstance(reason, str) for reason in reasons)
        ):
            raise EngineInputError(
                "Battle Cry transcript unaffected target is invalid"
            )
    actor = _participant_name(event.get("actorId"), participants, definitions)
    text = (
        f"{actor} uses Battle Cry. "
        + (
            f"{', '.join(affected)} gain a +1 status bonus to attack "
            "and damage rolls until the start of the commander's next turn."
            if affected
            else "No creature gains the bonus."
        )
    )
    if excluded:
        text += " Unaffected: " + "; ".join(
            _participant_name(result.get("targetId"), participants, definitions)
            + " ("
            + ", ".join(
                str(reason).replace("-", " ")
                for reason in result.get("unaffectedReasons") or []
            )
            + ")"
            for result in excluded
        ) + "."
    return text


def verify_current_source(
    authority: SourceAuthorityAdapter,
    /,
) -> dict[str, Any]:
    """Prove the exact duplicate-aware current source member and receipt."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("Battle Cry source proof requires exact authority")
    carrier_key, carrier_ordinal = SOURCE_RECEIPT["carrierPath"][0]
    selection_key, selection_ordinal = SOURCE_RECEIPT["selectionPath"][0]
    selection = authority.resolve(
        authority.address(
            source_id=SOURCE_ID,
            locator=LOCATOR,
            carrier_path=(
                RawMemberStep(carrier_key, carrier_ordinal),
            ),
            selection_path=(
                RawMemberStep(selection_key, selection_ordinal),
            ),
        )
    )
    address = selection.address
    if (
        address.section_id != SECTION_ID
        or tuple(
            (item.raw_key, item.member_ordinal)
            for item in address.target_path
        )
        != SOURCE_RECEIPT["targetPath"]
        or tuple(
            (item.raw_key, item.member_ordinal)
            for item in address.carrier_path
        )
        != SOURCE_RECEIPT["carrierPath"]
        or tuple(
            (item.raw_key, item.member_ordinal)
            for item in address.selection_path
        )
        != SOURCE_RECEIPT["selectionPath"]
        or selection.receipt.block_sha256
        != SOURCE_RECEIPT["carrierBlockSha256"]
        or selection.receipt.selection_sha256
        != SOURCE_RECEIPT["selectionSha256"]
        or raw_source_sha256(selection.raw_value)
        != SOURCE_RECEIPT["selectionSha256"]
        or selection.raw_value != _EXACT_VALUE
        or selection.carrier.raw_block.values("Name")
        != (CREATURE_NAME,)
    ):
        raise EngineInputError("Orc Commander Battle Cry source proof failed")
    return {
        "sourceId": SOURCE_ID,
        "locator": LOCATOR,
        "sectionId": SECTION_ID,
        "targetPath": [list(item) for item in SOURCE_RECEIPT["targetPath"]],
        "carrierPath": [list(item) for item in SOURCE_RECEIPT["carrierPath"]],
        "selectionPath": [list(item) for item in SOURCE_RECEIPT["selectionPath"]],
        "carrierBlockSha256": SOURCE_RECEIPT["carrierBlockSha256"],
        "selectionSha256": SOURCE_RECEIPT["selectionSha256"],
        "receiptDigest": selection.receipt.digest,
    }


FRAGMENT = MechanicFamilyFragment(
    family_id=ABILITY_ID,
    mechanic_types=(MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id=ABILITY_ID,
            mechanic_type=MECHANIC_TYPE,
            compiler=compile_battle_cry,
        ),
    ),
)


__all__ = [
    "ABILITY_ID",
    "ABILITY_RULE",
    "BattleCryHost",
    "CREATURE_NAME",
    "DESCRIPTION",
    "DUPLICATE_EFFECTS_RULE",
    "DURATION_RULE",
    "FRAGMENT",
    "LINE_OF_EFFECT_RULE",
    "LOCATOR",
    "MECHANIC_TYPE",
    "RANGE_RULE",
    "SECTION_ID",
    "SOURCE_ID",
    "SOURCE_RECEIPT",
    "STATUS_BONUS_RULE",
    "TRAITS",
    "TRAIT_RULE",
    "ability_for_definition",
    "active_effects",
    "battle_cry_spec",
    "build_activity_options",
    "compile_battle_cry",
    "recipient_contexts",
    "render_event",
    "resolve_activity",
    "verify_current_source",
]

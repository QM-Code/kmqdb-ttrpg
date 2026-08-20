"""Source-exact inherited Zombie Slow and Plague Zombie Bite contracts.

Zombie Rot owns disease exposure and lifecycle state in ``zombie_rot``.  This
module owns the inherited permanent Slow restriction shared by the admitted
Zombie Brute and Plague Zombie, plus the Plague Zombie's one-action jaws Strike
against a creature it has grabbed or restrained.  Runtime helpers are
deliberately pure; the encounter layer remains responsible for action spending,
ordinary Strike resolution, effects, and event emission.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any

from ..errors import EngineInputError
from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RuleReference,
)
from .source_authority import (
    RawMemberStep,
    SourceAuthorityAdapter,
    raw_source_sha256,
)


SOURCE_ID = "core-mc1"
LOCATOR = "356.6"
SECTION_ID = "core-mc1:zombie"
CREATURE_NAME = "Plague Zombie"
ZOMBIE_BRUTE_LOCATOR = "357.2"
ZOMBIE_BRUTE_NAME = "Zombie Brute"

SLOW_MECHANIC_TYPE = "permanent-slowed-no-reactions"
ZOMBIE_BITE_MECHANIC_TYPE = "plague-zombie-bite"

SLOW_ABILITY_ID = "slow"
ZOMBIE_BITE_ABILITY_ID = "zombie-bite"
FIST_STRIKE_ID = "strike:fist:melee"
ZOMBIE_BITE_STRIKE_ID = "strike:zombie-bite-jaws:melee"
ZOMBIE_ROT_ABILITY_ID = "zombie-rot"

PRELINK_ACTIVATION = "requires-definition-link"
LINKED_ACTIVATION = "definition-linked"

SLOW_SOURCE_TEXT = "As zombie shambler."
INHERITED_SLOW_SOURCE_TEXT = (
    "A zombie is permanently slowed 1 and can't use reactions."
)
ZOMBIE_BITE_REQUIREMENTS = (
    "The zombie has a creature grabbed or restrained."
)
ZOMBIE_BITE_EFFECT = (
    "The zombie makes a jaws unarmed melee Strike against that creature "
    "with an attack modifier of +9 that deals 1d12+4 piercing damage and "
    "exposes the creature to zombie rot."
)

ACTIVITY_RULE = {"sourceId": "core-pc1", "locator": "414.4"}
STRIKE_RULE = {"sourceId": "core-pc1", "locator": "418.4"}
ATTACK_ROLL_RULE = {"sourceId": "core-pc1", "locator": "402.1"}
GRABBED_RULE = {"sourceId": "core-pc1", "locator": "444.5"}
RESTRAINED_RULE = {"sourceId": "core-pc1", "locator": "446.3"}
SLOWED_RULE = {"sourceId": "core-pc1", "locator": "446.5"}

_SOURCE_TARGET_PATH = (("Zombie", 1),)
_PLAGUE_CARRIER_PATH = (("^.creature", 4),)
_SHAMBLER_CARRIER_PATH = (("^.creature", 3),)
_ZOMBIE_BRUTE_CARRIER_PATH = (("^.creature", 6),)
_PLAGUE_BLOCK_SHA256 = (
    "e66ffe5a2e0894c0c8a3b6e1a352c7aaaa5d8c39c847a76db5223b858e5f0d5d"
)
_SHAMBLER_BLOCK_SHA256 = (
    "73b4d8c77d84bf3cc40a0a889a8b7e4c628fa47f1020cb11e794d41e663569b5"
)
_ZOMBIE_BRUTE_BLOCK_SHA256 = (
    "1a9607f80f14628f6354112cff8d8c7dd1c67aa4548d6238b7b16e539b0d2b9c"
)
_SLOW_SHA256 = (
    "64878cfbb8a3f5b1eedfd3827f691c43197cd24c77e450c8b95359b6dc055d52"
)
_SHAMBLER_SLOW_SHA256 = (
    "a12bb932fe5c1fcf682387d4bab22547e96fea4f25b01553dbedf03480c4da49"
)
_BITE_SHA256 = (
    "ae3734655d45b39b8f050829711a16cd3bb38de4ee05e86e64b4bf94c5cc0a2f"
)
_FIST_SHA256 = (
    "d412bf0b1080ec4433c6d4f9f044b49a4db978f01b149ef785003b20f9027fc1"
)

SOURCE_RECEIPTS = {
    "slow": {
        "sourceId": SOURCE_ID,
        "locator": LOCATOR,
        "sectionId": SECTION_ID,
        "targetPath": _SOURCE_TARGET_PATH,
        "carrierPath": _PLAGUE_CARRIER_PATH,
        "selectionPath": (("!.Slow", 15),),
        "carrierBlockSha256": _PLAGUE_BLOCK_SHA256,
        "selectionSha256": _SLOW_SHA256,
    },
    "inheritedSlow": {
        "sourceId": SOURCE_ID,
        "locator": LOCATOR,
        "sectionId": SECTION_ID,
        "targetPath": _SOURCE_TARGET_PATH,
        "carrierPath": _SHAMBLER_CARRIER_PATH,
        "selectionPath": (("!.Slow", 15),),
        "carrierBlockSha256": _SHAMBLER_BLOCK_SHA256,
        "selectionSha256": _SHAMBLER_SLOW_SHA256,
    },
    "zombieBite": {
        "sourceId": SOURCE_ID,
        "locator": LOCATOR,
        "sectionId": SECTION_ID,
        "targetPath": _SOURCE_TARGET_PATH,
        "carrierPath": _PLAGUE_CARRIER_PATH,
        "selectionPath": (("!.Zombie Bite", 25),),
        "carrierBlockSha256": _PLAGUE_BLOCK_SHA256,
        "selectionSha256": _BITE_SHA256,
    },
    # This receipt proves the one-entry Melee carrier.  The selected value is
    # the complete Melee array, not a fabricated address for its fist item.
    "fistCarrier": {
        "sourceId": SOURCE_ID,
        "locator": LOCATOR,
        "sectionId": SECTION_ID,
        "targetPath": _SOURCE_TARGET_PATH,
        "carrierPath": _PLAGUE_CARRIER_PATH,
        "selectionPath": (("Melee", 24),),
        "carrierBlockSha256": _PLAGUE_BLOCK_SHA256,
        "selectionSha256": _FIST_SHA256,
    },
}

ZOMBIE_BRUTE_SOURCE_RECEIPTS = {
    "slow": {
        "sourceId": SOURCE_ID,
        "locator": ZOMBIE_BRUTE_LOCATOR,
        "sectionId": SECTION_ID,
        "targetPath": _SOURCE_TARGET_PATH,
        "carrierPath": _ZOMBIE_BRUTE_CARRIER_PATH,
        "selectionPath": (("!.Slow", 15),),
        "carrierBlockSha256": _ZOMBIE_BRUTE_BLOCK_SHA256,
        "selectionSha256": _SLOW_SHA256,
    },
    "inheritedSlow": {
        "sourceId": SOURCE_ID,
        "locator": ZOMBIE_BRUTE_LOCATOR,
        "sectionId": SECTION_ID,
        "targetPath": _SOURCE_TARGET_PATH,
        "carrierPath": _SHAMBLER_CARRIER_PATH,
        "selectionPath": (("!.Slow", 15),),
        "carrierBlockSha256": _SHAMBLER_BLOCK_SHA256,
        "selectionSha256": _SHAMBLER_SLOW_SHA256,
    },
}

_EXACT_SLOW = RawSourceObject.from_pairs(
    (("Description", SLOW_SOURCE_TEXT),)
)
_EXACT_SHAMBLER_SLOW = RawSourceObject.from_pairs(
    (("Description", INHERITED_SLOW_SOURCE_TEXT),)
)
_EXACT_BITE = RawSourceObject.from_pairs(
    (
        ("Action", "single"),
        ("Requirements", ZOMBIE_BITE_REQUIREMENTS),
        ("Effect", ZOMBIE_BITE_EFFECT),
    )
)
_EXACT_FIST = RawSourceArray(
    (
        RawSourceObject.from_pairs(
            (
                ("Name", "fist"),
                ("Attack", "+9"),
                (
                    "Damage",
                    "1d8+4 bludgeoning plus Grab (page 359) and zombie rot",
                ),
            )
        ),
    )
)

_STRIKE_INPUT_FIELDS = frozenset(
    {
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
)
_STRIKE_DEGREES = frozenset(
    {"critical-failure", "failure", "success", "critical-success"}
)


def _source_path(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sourceId": receipt["sourceId"],
        "locator": receipt["locator"],
        "sectionId": receipt["sectionId"],
        "targetPath": [
            {"rawKey": key, "memberOrdinal": ordinal}
            for key, ordinal in receipt["targetPath"]
        ],
        "carrierPath": [
            {"rawKey": key, "memberOrdinal": ordinal}
            for key, ordinal in receipt["carrierPath"]
        ],
        "selectionPath": [
            {"rawKey": key, "memberOrdinal": ordinal}
            for key, ordinal in receipt["selectionPath"]
        ],
        "carrierBlockSha256": receipt["carrierBlockSha256"],
        "selectionSha256": receipt["selectionSha256"],
    }


def _exact_ability_source(
    source: AbilitySource,
    *,
    label: str,
    raw_value: RawSourceObject,
    action_cost: int | None,
    description: str,
    locator: str = LOCATOR,
    creature_name: str = CREATURE_NAME,
) -> bool:
    return bool(
        source.source_id == SOURCE_ID
        and source.locator == locator
        and source.creature_name == creature_name
        and source.source_label == label
        and source.action_cost == action_cost
        and source.kind == ("activity" if action_cost is not None else "passive")
        and source.traits == ()
        and source.trigger == ""
        and source.description == description
        and source.raw_member.key == f"!.{label}"
        and source.raw_member.value == raw_value
    )


def compile_plague_zombie_slow(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact inherited Slow member on Plague Zombie."""

    if not _exact_ability_source(
        source,
        label="Slow",
        raw_value=_EXACT_SLOW,
        action_cost=None,
        description=SLOW_SOURCE_TEXT,
    ) or raw_source_sha256(source.raw_member.value) != _SLOW_SHA256:
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": SLOW_MECHANIC_TYPE,
            "permanentCondition": {
                "condition": "slowed",
                "value": 1,
                "duration": {"kind": "permanent"},
            },
            "startTurn": {"actionsLost": 1},
            "reactionRestriction": {"canUseReactions": False},
            "inheritedFrom": _source_path(SOURCE_RECEIPTS["inheritedSlow"]),
            "source": _source_path(SOURCE_RECEIPTS["slow"]),
            "rules": {"slowed": deepcopy(SLOWED_RULE)},
        },
        rule=RuleReference(SOURCE_ID, LOCATOR),
    )


def compile_zombie_brute_slow(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact inherited Slow member on Zombie Brute."""

    if not _exact_ability_source(
        source,
        label="Slow",
        raw_value=_EXACT_SLOW,
        action_cost=None,
        description=SLOW_SOURCE_TEXT,
        locator=ZOMBIE_BRUTE_LOCATOR,
        creature_name=ZOMBIE_BRUTE_NAME,
    ) or raw_source_sha256(source.raw_member.value) != _SLOW_SHA256:
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": SLOW_MECHANIC_TYPE,
            "permanentCondition": {
                "condition": "slowed",
                "value": 1,
                "duration": {"kind": "permanent"},
            },
            "startTurn": {"actionsLost": 1},
            "reactionRestriction": {"canUseReactions": False},
            "inheritedFrom": _source_path(
                ZOMBIE_BRUTE_SOURCE_RECEIPTS["inheritedSlow"]
            ),
            "source": _source_path(ZOMBIE_BRUTE_SOURCE_RECEIPTS["slow"]),
            "rules": {"slowed": deepcopy(SLOWED_RULE)},
        },
        rule=RuleReference(SOURCE_ID, ZOMBIE_BRUTE_LOCATOR),
    )


def _bite_strike_template() -> dict[str, Any]:
    component = {
        "sourceText": "1d12+4 piercing",
        "dice": {"count": 1, "sides": 12},
        "flatAmount": None,
        "modifier": 4,
        "type": "piercing",
        "persistent": False,
    }
    return {
        "id": ZOMBIE_BITE_STRIKE_ID,
        "name": "jaws",
        "kind": "melee",
        "attackModifier": 9,
        "traits": [],
        "unarmed": True,
        "reachFeet": 5,
        "damage": {
            "sourceText": "1d12+4 piercing",
            "dice": {"count": 1, "sides": 12},
            "flatAmount": None,
            "modifier": 4,
            "type": "piercing",
            "components": [component],
            "riderEffects": [],
        },
        "followUps": [],
        "sourceDeferredDependencies": [],
    }


def compile_zombie_bite(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the exact held-target jaws Strike and its Rot link."""

    if not _exact_ability_source(
        source,
        label="Zombie Bite",
        raw_value=_EXACT_BITE,
        action_cost=1,
        # The generic source projector currently exposes Description only;
        # this ordered ability authors its prose under Requirements/Effect.
        description="",
    ) or raw_source_sha256(source.raw_member.value) != _BITE_SHA256:
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": ZOMBIE_BITE_MECHANIC_TYPE,
            "requirements": {
                "targetRelation": "grabbed-or-restrained-by-source",
                "conditions": ["grabbed", "restrained"],
            },
            "strike": _bite_strike_template(),
            "multipleAttackPenalty": {
                "mode": "normal",
                "postActivityAttackCountIncrement": 1,
            },
            "delivery": {
                "abilityId": ZOMBIE_ROT_ABILITY_ID,
                "trigger": "strike-hit-exposure",
                "activation": PRELINK_ACTIVATION,
            },
            "source": _source_path(SOURCE_RECEIPTS["zombieBite"]),
            "rules": {
                "activity": deepcopy(ACTIVITY_RULE),
                "strike": deepcopy(STRIKE_RULE),
                "multipleAttackPenalty": deepcopy(ATTACK_ROLL_RULE),
                "grabbed": deepcopy(GRABBED_RULE),
                "restrained": deepcopy(RESTRAINED_RULE),
            },
        },
        rule=RuleReference(SOURCE_ID, LOCATOR),
    )


def _slow_spec(ability: Mapping[str, Any], /) -> dict[str, Any]:
    source = AbilitySource(
        source_label="Slow",
        action_cost=None,
        kind="passive",
        traits=(),
        trigger="",
        description=SLOW_SOURCE_TEXT,
        source_id=SOURCE_ID,
        locator=LOCATOR,
        creature_name=CREATURE_NAME,
        raw_member=RawSourceMember("!.Slow", _EXACT_SLOW),
    )
    patch = compile_plague_zombie_slow(source)
    assert patch is not None
    expected = {
        "id": SLOW_ABILITY_ID,
        "name": "Slow",
        "kind": "passive",
        "actionCost": None,
        "traits": [],
        **patch.as_ability_update(),
    }
    if not isinstance(ability, Mapping) or any(
        ability.get(key) != value for key, value in expected.items()
    ):
        raise EngineInputError("Plague Zombie Slow mechanic is invalid")
    return deepcopy(expected["mechanic"])


def _zombie_brute_slow_spec(
    ability: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    source = AbilitySource(
        source_label="Slow",
        action_cost=None,
        kind="passive",
        traits=(),
        trigger="",
        description=SLOW_SOURCE_TEXT,
        source_id=SOURCE_ID,
        locator=ZOMBIE_BRUTE_LOCATOR,
        creature_name=ZOMBIE_BRUTE_NAME,
        raw_member=RawSourceMember("!.Slow", _EXACT_SLOW),
    )
    patch = compile_zombie_brute_slow(source)
    assert patch is not None
    expected = {
        "id": SLOW_ABILITY_ID,
        "name": "Slow",
        "kind": "passive",
        "actionCost": None,
        "traits": [],
        **patch.as_ability_update(),
    }
    if not isinstance(ability, Mapping) or any(
        ability.get(key) != value for key, value in expected.items()
    ):
        raise EngineInputError("Zombie Brute Slow mechanic is invalid")
    return deepcopy(expected["mechanic"])


def zombie_slow_spec(ability: Mapping[str, Any], /) -> dict[str, Any]:
    """Validate either admitted source-exact inherited Zombie Slow."""

    rule = ability.get("rule") if isinstance(ability, Mapping) else None
    locator = rule.get("locator") if isinstance(rule, Mapping) else None
    if locator == LOCATOR:
        return _slow_spec(ability)
    if locator == ZOMBIE_BRUTE_LOCATOR:
        return _zombie_brute_slow_spec(ability)
    raise EngineInputError("inherited Zombie Slow mechanic is invalid")


def _bite_spec(
    ability: Mapping[str, Any],
    /,
    *,
    activation: str = LINKED_ACTIVATION,
) -> dict[str, Any]:
    if activation not in {PRELINK_ACTIVATION, LINKED_ACTIVATION}:
        raise EngineInputError("Zombie Bite activation is invalid")
    source = AbilitySource(
        source_label="Zombie Bite",
        action_cost=1,
        kind="activity",
        traits=(),
        trigger="",
        description="",
        source_id=SOURCE_ID,
        locator=LOCATOR,
        creature_name=CREATURE_NAME,
        raw_member=RawSourceMember("!.Zombie Bite", _EXACT_BITE),
    )
    patch = compile_zombie_bite(source)
    assert patch is not None
    mechanic = deepcopy(patch.as_ability_update()["mechanic"])
    mechanic["delivery"]["activation"] = activation
    expected = {
        "id": ZOMBIE_BITE_ABILITY_ID,
        "name": "Zombie Bite",
        "kind": "activity",
        "actionCost": 1,
        "traits": [],
        **patch.as_ability_update(),
        "mechanic": mechanic,
    }
    if not isinstance(ability, Mapping) or any(
        ability.get(key) != value for key, value in expected.items()
    ):
        raise EngineInputError("Zombie Bite mechanic is invalid")
    return deepcopy(expected["mechanic"])


def plague_zombie_start_turn_constraints(
    ability: Mapping[str, Any],
    /,
    *,
    base_actions: object,
) -> dict[str, Any]:
    """Project permanent Slowed 1 without creating an expiring effect."""

    mechanic = _slow_spec(ability)
    if (
        isinstance(base_actions, bool)
        or not isinstance(base_actions, int)
        or base_actions < 0
    ):
        raise EngineInputError("Plague Zombie base actions are invalid")
    actions_lost = int(mechanic["startTurn"]["actionsLost"])
    return {
        "baseActions": base_actions,
        "slowedValue": 1,
        "actionsLost": actions_lost,
        "actionsGranted": max(0, base_actions - actions_lost),
        "reactionAvailable": False,
        "duration": deepcopy(mechanic["permanentCondition"]["duration"]),
        "rule": deepcopy(mechanic["rules"]["slowed"]),
    }


def plague_zombie_reaction_block(
    ability: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Return the always-on reaction gate authored by Slow."""

    mechanic = _slow_spec(ability)
    return {
        "blocked": mechanic["reactionRestriction"]["canUseReactions"] is False,
        "abilityId": SLOW_ABILITY_ID,
        "rule": {"sourceId": SOURCE_ID, "locator": LOCATOR},
    }


def zombie_slow_start_turn_constraints(
    ability: Mapping[str, Any],
    /,
    *,
    base_actions: object,
) -> dict[str, Any]:
    """Project either admitted permanent Slowed 1 restriction."""

    mechanic = zombie_slow_spec(ability)
    if (
        isinstance(base_actions, bool)
        or not isinstance(base_actions, int)
        or base_actions < 0
    ):
        raise EngineInputError("Zombie base actions are invalid")
    actions_lost = int(mechanic["startTurn"]["actionsLost"])
    return {
        "baseActions": base_actions,
        "slowedValue": 1,
        "actionsLost": actions_lost,
        "actionsGranted": max(0, base_actions - actions_lost),
        "reactionAvailable": False,
        "duration": deepcopy(mechanic["permanentCondition"]["duration"]),
        "rule": deepcopy(mechanic["rules"]["slowed"]),
    }


def zombie_slow_reaction_block(
    ability: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Return the always-on reaction gate for either inherited Slow."""

    mechanic = zombie_slow_spec(ability)
    rule = ability.get("rule")
    assert isinstance(rule, Mapping)
    return {
        "blocked": mechanic["reactionRestriction"]["canUseReactions"] is False,
        "abilityId": SLOW_ABILITY_ID,
        "rule": deepcopy(dict(rule)),
    }


def linked_zombie_bite_strike(
    ability: Mapping[str, Any],
    zombie_rot_ability: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Bind the embedded jaws Strike to the exact Zombie Rot contract."""

    return _zombie_bite_strike_for_activation(
        ability,
        zombie_rot_ability,
        activation=LINKED_ACTIVATION,
    )


def _zombie_bite_strike_for_activation(
    ability: Mapping[str, Any],
    zombie_rot_ability: Mapping[str, Any],
    /,
    *,
    activation: str,
) -> dict[str, Any]:
    mechanic = _bite_spec(ability, activation=activation)
    rot = _zombie_rot_link_spec(zombie_rot_ability)
    if mechanic["delivery"] != {
        "abilityId": ZOMBIE_ROT_ABILITY_ID,
        "trigger": rot["delivery"]["trigger"],
        "activation": activation,
    }:
        raise EngineInputError("Zombie Bite and Zombie Rot delivery disagree")
    strike = deepcopy(mechanic["strike"])
    strike["damage"]["riderEffects"] = [
        {
            "name": "Zombie Rot",
            "sourceText": "exposes the creature to zombie rot",
            "supported": True,
            "abilityId": ZOMBIE_ROT_ABILITY_ID,
            "trigger": rot["delivery"]["trigger"],
        }
    ]
    return strike


def activate_zombie_bite_link(
    ability: Mapping[str, Any],
    zombie_rot_ability: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Return the exact production Bite after authenticating Zombie Rot."""

    _zombie_bite_strike_for_activation(
        ability,
        zombie_rot_ability,
        activation=PRELINK_ACTIVATION,
    )
    activated = deepcopy(dict(ability))
    activated["mechanic"]["delivery"]["activation"] = LINKED_ACTIVATION
    linked_zombie_bite_strike(activated, zombie_rot_ability)
    return activated


def _zombie_rot_link_spec(
    ability: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Validate only the narrow cross-family contract Bite consumes.

    Zombie Rot owns its stages, effect state, and full validation.  Mechanics
    families cannot import peer families, so this linker proves only the
    identity and delivery fields required to hand a successful Bite to that
    separately registered family.
    """

    mechanic = ability.get("mechanic") if isinstance(ability, Mapping) else None
    if (
        not isinstance(ability, Mapping)
        or ability.get("id") != ZOMBIE_ROT_ABILITY_ID
        or ability.get("name") != "Zombie Rot"
        or ability.get("supported") is not True
        or ability.get("kind") != "passive"
        or ability.get("actionCost") is not None
        or ability.get("traits") != ["disease", "divine", "void"]
        or ability.get("rule")
        != {"sourceId": SOURCE_ID, "locator": LOCATOR}
        or not isinstance(mechanic, Mapping)
        or mechanic.get("type") != "disease-affliction"
        or mechanic.get("afflictionKey") != "disease:zombie-rot"
        or mechanic.get("afflictionType") != "disease"
        or mechanic.get("delivery")
        != {"kind": "strike-rider", "trigger": "strike-hit-exposure"}
        or mechanic.get("savingThrow")
        != {"type": "fortitude", "dc": 18}
        or mechanic.get("runtime")
        != {
            "supported": "initial-exposure",
            "progressionBoundary": "campaign-clock",
        }
    ):
        raise EngineInputError("Zombie Rot link contract is invalid")
    return deepcopy(dict(mechanic))


def _held_target_contexts(
    state: Mapping[str, Any],
    actor_id: str,
) -> list[dict[str, Any]]:
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
        raise EngineInputError("Zombie Bite option state is invalid")
    live = {
        item.get("id")
        for item in participants
        if isinstance(item.get("id"), str)
        and item.get("id") != actor_id
        and not item.get("defeated")
        and not item.get("incapacitated")
    }
    held: dict[str, list[Mapping[str, Any]]] = {}
    for effect in effects:
        target_id = effect.get("targetParticipantId")
        if (
            effect.get("kind") == "grapple"
            and effect.get("sourceParticipantId") == actor_id
            and target_id in live
            and effect.get("condition") in {"grabbed", "restrained"}
            and isinstance(effect.get("id"), str)
            and effect.get("id")
        ):
            held.setdefault(str(target_id), []).append(effect)
    return [
        {
            "targetId": participant["id"],
            "conditions": sorted(
                {str(item["condition"]) for item in held[participant["id"]]}
            ),
            "sourceEffectIds": [
                str(item["id"]) for item in held[participant["id"]]
            ],
        }
        for participant in participants
        if participant.get("id") in held
    ]


def build_zombie_bite_activity_options(
    state: Mapping[str, Any],
    actor: Mapping[str, Any],
    ability: Mapping[str, Any],
    zombie_rot_ability: Mapping[str, Any],
    /,
) -> list[dict[str, Any]]:
    """List only live creatures held by this zombie as Bite targets."""

    mechanic = _bite_spec(ability)
    linked_zombie_bite_strike(ability, zombie_rot_ability)
    actor_id = actor.get("id") if isinstance(actor, Mapping) else None
    if not isinstance(actor_id, str) or not actor_id:
        raise EngineInputError("Zombie Bite actor is invalid")
    legal_targets = _held_target_contexts(state, actor_id)
    return [
        {
            "abilityId": ZOMBIE_BITE_ABILITY_ID,
            "actionCost": 1,
            "traits": ["attack"],
            "available": bool(legal_targets),
            "blockedBy": [],
            "legalTargets": legal_targets,
            "strikeName": "jaws",
            "strikeCount": 1,
            "multipleAttackPenalty": deepcopy(
                mechanic["multipleAttackPenalty"]
            ),
            "zombieRot": {
                "abilityId": ZOMBIE_ROT_ABILITY_ID,
                "trigger": mechanic["delivery"]["trigger"],
            },
        }
    ]


def _strike_request(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EngineInputError("Zombie Bite Strike input must be an object")
    unexpected = set(value).difference(_STRIKE_INPUT_FIELDS)
    if unexpected:
        raise EngineInputError(
            "Zombie Bite contains unsupported Strike fields: "
            f"{', '.join(sorted(unexpected))}"
        )
    flat_roll = value.get("targetingFlatCheckRoll")
    attack_roll = value.get("attackRoll")
    for roll, label in (
        (flat_roll, "targetingFlatCheckRoll"),
        (attack_roll, "attackRoll"),
    ):
        if roll is not None and (
            isinstance(roll, bool)
            or not isinstance(roll, int)
            or not 1 <= roll <= 20
        ):
            raise EngineInputError(f"Zombie Bite {label} must be a d20 result")
    if attack_roll is None and flat_roll is None:
        raise EngineInputError("Zombie Bite attackRoll is required")
    return {
        "type": "Strike",
        "strikeName": "jaws",
        **deepcopy(dict(value)),
    }


def validate_zombie_bite_action(
    action: Mapping[str, Any],
    ability: Mapping[str, Any],
    zombie_rot_ability: Mapping[str, Any],
    held_target_ids: Sequence[str],
    /,
    *,
    attacks_this_turn: object,
) -> dict[str, Any]:
    """Return one ordinary subordinate-Strike request and normal MAP plan."""

    _bite_spec(ability)
    strike = linked_zombie_bite_strike(ability, zombie_rot_ability)
    if not isinstance(action, Mapping):
        raise EngineInputError("Zombie Bite action must be an object")
    if (
        not isinstance(held_target_ids, Sequence)
        or isinstance(held_target_ids, (str, bytes))
        or any(not isinstance(item, str) or not item for item in held_target_ids)
        or len(set(held_target_ids)) != len(held_target_ids)
    ):
        raise EngineInputError("Zombie Bite held target IDs are invalid")
    target_id = action.get("targetId")
    if (
        action.get("type") != "Activity"
        or action.get("abilityId") != ZOMBIE_BITE_ABILITY_ID
        or target_id not in held_target_ids
    ):
        raise EngineInputError(
            "Zombie Bite target is not grabbed or restrained by the zombie"
        )
    if (
        isinstance(attacks_this_turn, bool)
        or not isinstance(attacks_this_turn, int)
        or attacks_this_turn < 0
    ):
        raise EngineInputError("Zombie Bite attacksThisTurn is invalid")
    unexpected = set(action).difference(
        {"type", "abilityId", "targetId", *_STRIKE_INPUT_FIELDS}
    )
    if unexpected:
        raise EngineInputError(
            "Zombie Bite contains unsupported fields: "
            f"{', '.join(sorted(unexpected))}"
        )
    request = _strike_request(
        {key: value for key, value in action.items() if key in _STRIKE_INPUT_FIELDS}
    )
    request["targetId"] = str(target_id)
    attack_number = attacks_this_turn + 1
    return {
        "abilityId": ZOMBIE_BITE_ABILITY_ID,
        "targetId": target_id,
        "strikeDefinition": strike,
        "strikeRequest": request,
        "multipleAttackPenalty": {
            "mode": "normal",
            "attacksThisTurnBefore": attacks_this_turn,
            "attackNumbers": [attack_number],
            "postActivityAttackCountIncrement": 1,
            "attacksThisTurnAfter": attack_number,
        },
    }


def zombie_bite_exposure_disposition(
    ability: Mapping[str, Any],
    zombie_rot_ability: Mapping[str, Any],
    strike_result: Mapping[str, Any],
    /,
    *,
    active_effect: Mapping[str, Any] | None,
    exposure_resolver: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Validate the jaws result and inject the Zombie Rot family resolver."""

    strike = linked_zombie_bite_strike(ability, zombie_rot_ability)
    if not callable(exposure_resolver):
        raise EngineInputError("Zombie Rot exposure resolver is invalid")
    targeting_outcome = (
        strike_result.get("targetingOutcome")
        if isinstance(strike_result, Mapping)
        else None
    )
    degree = (
        strike_result.get("degree")
        if isinstance(strike_result, Mapping)
        else None
    )
    if (
        not isinstance(strike_result, Mapping)
        or strike_result.get("strikeId") != strike["id"]
        or str(strike_result.get("strikeName") or "").casefold() != "jaws"
        or targeting_outcome not in {"failure", "success", "not-required"}
        or (
            targeting_outcome == "failure"
            and degree is not None
        )
        or (
            targeting_outcome != "failure"
            and degree not in _STRIKE_DEGREES
        )
    ):
        raise EngineInputError("Zombie Bite Strike result is invalid")
    result = exposure_resolver(
        zombie_rot_ability,
        targeting_succeeded=targeting_outcome != "failure",
        strike_degree=degree,
        active_effect=active_effect,
    )
    if not isinstance(result, dict) or not isinstance(result.get("kind"), str):
        raise EngineInputError("Zombie Rot exposure result is invalid")
    return deepcopy(result)


def _validate_plague_zombie_definition_links(
    definition: Mapping[str, Any],
    /,
    *,
    bite_activation: str,
) -> dict[str, Any]:
    source = definition.get("source") if isinstance(definition, Mapping) else None
    if (
        not isinstance(definition, Mapping)
        or definition.get("name") != CREATURE_NAME
        or not isinstance(source, Mapping)
        or source.get("sourceId") != SOURCE_ID
        or source.get("locator") != LOCATOR
        or source.get("sectionId") != SECTION_ID
        or source.get("contentPath") != ["Zombie", CREATURE_NAME]
        or definition.get("space", {}).get("defaultReachFeet") != 5
    ):
        raise EngineInputError("Plague Zombie definition identity is invalid")
    abilities = definition.get("abilities")
    strikes = definition.get("strikes")
    if not isinstance(abilities, list) or not isinstance(strikes, list):
        raise EngineInputError("Plague Zombie definition is incomplete")
    by_id = {
        item.get("id"): item
        for item in abilities
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    if len(by_id) != len(abilities):
        raise EngineInputError("Plague Zombie abilities are ambiguous")
    _slow_spec(by_id.get(SLOW_ABILITY_ID, {}))
    bite = by_id.get(ZOMBIE_BITE_ABILITY_ID, {})
    rot = by_id.get(ZOMBIE_ROT_ABILITY_ID, {})
    linked_bite = _zombie_bite_strike_for_activation(
        bite,
        rot,
        activation=bite_activation,
    )

    fists = [
        item
        for item in strikes
        if isinstance(item, Mapping) and item.get("id") == FIST_STRIKE_ID
    ]
    if len(fists) != 1:
        raise EngineInputError("Plague Zombie Fist Strike is missing or ambiguous")
    fist = fists[0]
    damage = fist.get("damage")
    rot_riders = (
        [
            item
            for item in damage.get("riderEffects", [])
            if isinstance(item, Mapping)
            and str(item.get("name") or "").casefold() == "zombie rot"
        ]
        if isinstance(damage, Mapping)
        else []
    )
    grab_follow_ups = [
        item
        for item in fist.get("followUps", [])
        if isinstance(item, Mapping)
        and str(item.get("name") or "").casefold() == "grab"
    ]
    if (
        fist.get("name") != "fist"
        or fist.get("kind") != "melee"
        or fist.get("attackModifier") != 9
        or fist.get("reachFeet") != 5
        or not isinstance(damage, Mapping)
        or damage.get("dice") != {"count": 1, "sides": 8}
        or damage.get("modifier") != 4
        or damage.get("type") != "bludgeoning"
        or len(rot_riders) != 1
        or rot_riders[0].get("supported") is not True
        or rot_riders[0].get("abilityId") != ZOMBIE_ROT_ABILITY_ID
        or len(grab_follow_ups) != 1
        or grab_follow_ups[0].get("supported") is not True
    ):
        raise EngineInputError(
            "Plague Zombie Fist, Grab, and Zombie Rot links are invalid"
        )
    return {
        "slowAbilityId": SLOW_ABILITY_ID,
        "zombieBiteAbilityId": ZOMBIE_BITE_ABILITY_ID,
        "zombieRotAbilityId": ZOMBIE_ROT_ABILITY_ID,
        "fistStrikeId": FIST_STRIKE_ID,
        "zombieBiteStrike": linked_bite,
    }


def activate_plague_zombie_definition_links(
    definition: dict[str, Any],
    /,
) -> dict[str, Any]:
    """Authenticate the prelink definition and activate its Bite delivery."""

    if not isinstance(definition, dict):
        raise EngineInputError("Plague Zombie definition must be mutable")
    _validate_plague_zombie_definition_links(
        definition,
        bite_activation=PRELINK_ACTIVATION,
    )
    abilities = definition["abilities"]
    bite_indexes = [
        index
        for index, ability in enumerate(abilities)
        if isinstance(ability, Mapping)
        and ability.get("id") == ZOMBIE_BITE_ABILITY_ID
    ]
    rot = next(
        ability
        for ability in abilities
        if isinstance(ability, Mapping)
        and ability.get("id") == ZOMBIE_ROT_ABILITY_ID
    )
    abilities[bite_indexes[0]] = activate_zombie_bite_link(
        abilities[bite_indexes[0]],
        rot,
    )
    validate_plague_zombie_definition_links(definition)
    return definition


def validate_plague_zombie_definition_links(
    definition: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Accept only a production-linked Slow, Bite, Fist, Grab, and Rot set."""

    return _validate_plague_zombie_definition_links(
        definition,
        bite_activation=LINKED_ACTIVATION,
    )


def verify_current_source(
    authority: SourceAuthorityAdapter,
    /,
) -> dict[str, Any]:
    """Resolve and prove the exact current duplicate-aware source members."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("Plague Zombie source proof requires exact authority")
    expected_values = {
        "slow": _EXACT_SLOW,
        "inheritedSlow": _EXACT_SHAMBLER_SLOW,
        "zombieBite": _EXACT_BITE,
        "fistCarrier": _EXACT_FIST,
    }
    result: dict[str, Any] = {}
    for key, receipt in SOURCE_RECEIPTS.items():
        carrier_key, carrier_ordinal = receipt["carrierPath"][0]
        selection_key, selection_ordinal = receipt["selectionPath"][0]
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
        names = selection.carrier.raw_block.values("Name")
        expected_name = (
            "Zombie Shambler" if key == "inheritedSlow" else CREATURE_NAME
        )
        if (
            address.source_id != SOURCE_ID
            or address.locator != LOCATOR
            or address.section_id != SECTION_ID
            or tuple(
                (item.raw_key, item.member_ordinal)
                for item in address.target_path
            )
            != receipt["targetPath"]
            or tuple(
                (item.raw_key, item.member_ordinal)
                for item in address.carrier_path
            )
            != receipt["carrierPath"]
            or tuple(
                (item.raw_key, item.member_ordinal)
                for item in address.selection_path
            )
            != receipt["selectionPath"]
            or selection.receipt.block_sha256
            != receipt["carrierBlockSha256"]
            or selection.receipt.selection_sha256
            != receipt["selectionSha256"]
            or raw_source_sha256(selection.raw_value)
            != receipt["selectionSha256"]
            or selection.raw_value != expected_values[key]
            or names != (expected_name,)
        ):
            raise EngineInputError(
                f"Plague Zombie source proof failed: {key}"
            )
        result[key] = {
            **_source_path(receipt),
            "receiptDigest": selection.receipt.digest,
        }
    return result


def verify_zombie_brute_source(
    authority: SourceAuthorityAdapter,
    /,
) -> dict[str, Any]:
    """Resolve the Brute Slow and its exact inherited Shambler provider."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("Zombie Brute source proof requires exact authority")
    expected_values = {
        "slow": _EXACT_SLOW,
        "inheritedSlow": _EXACT_SHAMBLER_SLOW,
    }
    result: dict[str, Any] = {}
    for key, receipt in ZOMBIE_BRUTE_SOURCE_RECEIPTS.items():
        carrier_key, carrier_ordinal = receipt["carrierPath"][0]
        selection_key, selection_ordinal = receipt["selectionPath"][0]
        selection = authority.resolve(
            authority.address(
                source_id=SOURCE_ID,
                locator=ZOMBIE_BRUTE_LOCATOR,
                carrier_path=(
                    RawMemberStep(carrier_key, carrier_ordinal),
                ),
                selection_path=(
                    RawMemberStep(selection_key, selection_ordinal),
                ),
            )
        )
        address = selection.address
        expected_name = (
            "Zombie Shambler" if key == "inheritedSlow" else ZOMBIE_BRUTE_NAME
        )
        if (
            address.source_id != SOURCE_ID
            or address.locator != ZOMBIE_BRUTE_LOCATOR
            or address.section_id != SECTION_ID
            or tuple(
                (item.raw_key, item.member_ordinal)
                for item in address.target_path
            )
            != receipt["targetPath"]
            or tuple(
                (item.raw_key, item.member_ordinal)
                for item in address.carrier_path
            )
            != receipt["carrierPath"]
            or tuple(
                (item.raw_key, item.member_ordinal)
                for item in address.selection_path
            )
            != receipt["selectionPath"]
            or selection.receipt.block_sha256
            != receipt["carrierBlockSha256"]
            or selection.receipt.selection_sha256
            != receipt["selectionSha256"]
            or raw_source_sha256(selection.raw_value)
            != receipt["selectionSha256"]
            or selection.raw_value != expected_values[key]
            or selection.carrier.raw_block.values("Name") != (expected_name,)
        ):
            raise EngineInputError(
                f"Zombie Brute source proof failed: {key}"
            )
        result[key] = {
            **_source_path(receipt),
            "receiptDigest": selection.receipt.digest,
        }
    return result


FRAGMENT = MechanicFamilyFragment(
    family_id="plague-zombie-abilities",
    mechanic_types=(SLOW_MECHANIC_TYPE, ZOMBIE_BITE_MECHANIC_TYPE),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="plague-zombie-slow",
            mechanic_type=SLOW_MECHANIC_TYPE,
            compiler=compile_plague_zombie_slow,
        ),
        AbilityCompilerRegistration(
            compiler_id="zombie-brute-slow",
            mechanic_type=SLOW_MECHANIC_TYPE,
            compiler=compile_zombie_brute_slow,
        ),
        AbilityCompilerRegistration(
            compiler_id="plague-zombie-bite",
            mechanic_type=ZOMBIE_BITE_MECHANIC_TYPE,
            compiler=compile_zombie_bite,
        ),
    ),
)


__all__ = [
    "CREATURE_NAME",
    "FIST_STRIKE_ID",
    "FRAGMENT",
    "LINKED_ACTIVATION",
    "LOCATOR",
    "PRELINK_ACTIVATION",
    "SLOW_ABILITY_ID",
    "SLOW_MECHANIC_TYPE",
    "SOURCE_ID",
    "SOURCE_RECEIPTS",
    "ZOMBIE_BITE_ABILITY_ID",
    "ZOMBIE_BITE_MECHANIC_TYPE",
    "ZOMBIE_BITE_STRIKE_ID",
    "ZOMBIE_BRUTE_LOCATOR",
    "ZOMBIE_BRUTE_NAME",
    "ZOMBIE_BRUTE_SOURCE_RECEIPTS",
    "activate_plague_zombie_definition_links",
    "activate_zombie_bite_link",
    "build_zombie_bite_activity_options",
    "compile_plague_zombie_slow",
    "compile_zombie_brute_slow",
    "compile_zombie_bite",
    "linked_zombie_bite_strike",
    "plague_zombie_reaction_block",
    "plague_zombie_start_turn_constraints",
    "validate_plague_zombie_definition_links",
    "validate_zombie_bite_action",
    "verify_current_source",
    "verify_zombie_brute_source",
    "zombie_slow_reaction_block",
    "zombie_slow_spec",
    "zombie_slow_start_turn_constraints",
    "zombie_bite_exposure_disposition",
]

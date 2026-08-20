"""Source-bound Zombie Brute Slow and Improved Push definition linkage."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ..errors import EngineInputError


SOURCE_ID = "core-mc1"
LOCATOR = "357.2"
SECTION_ID = "core-mc1:zombie"
CREATURE_NAME = "Zombie Brute"
FIST_STRIKE_ID = "strike:fist:melee"
IMPROVED_PUSH_ID = "improved-push"
IMPROVED_PUSH_NAME = "Improved Push"
SLOW_ABILITY_ID = "slow"
SLOW_MECHANIC_TYPE = "permanent-slowed-no-reactions"
FORCED_MOVEMENT_FAMILY_ID = "forced-movement"
MECHANIC_TYPE = "strike-forced-movement-follow-up"
CONSUMER_RULE_ID = "forced-movement-consumer:zombie-brute-fist"

CREATURE_RULE = {"sourceId": SOURCE_ID, "locator": LOCATOR}
IMPROVED_PUSH_RULE = {"sourceId": SOURCE_ID, "locator": "358.2"}
SHOVE_RULE = {"sourceId": "core-pc1", "locator": "235.6"}
COMPARE_TO_DC_RULE = {"sourceId": "core-pc1", "locator": "401.2"}
DEGREE_RULE = {"sourceId": "core-pc1", "locator": "401.4"}
ATTACK_ROLL_RULE = {"sourceId": "core-pc1", "locator": "402.1"}
SUBORDINATE_ACTION_RULE = {"sourceId": "core-pc1", "locator": "414.4"}
TRIGGERED_ACTION_RULE = {"sourceId": "core-pc1", "locator": "414.6"}
STRIDE_RULE = {"sourceId": "core-pc1", "locator": "418.3"}
STRIKE_RULE = {"sourceId": "core-pc1", "locator": "418.4"}
FORCED_MOVEMENT_RULE = {"sourceId": "core-pc1", "locator": "422.7"}

_DAMAGE_SOURCE_TEXT = (
    "1d12+5 bludgeoning plus Improved Push 5 feet (page 359)"
)
_RIDER_SOURCE_TEXT = "Improved Push 5 feet (page 359)"


def _slow_spec(ability: Mapping[str, Any], /) -> dict[str, Any]:
    mechanic = ability.get("mechanic") if isinstance(ability, Mapping) else None
    expected_source = {
        "sourceId": SOURCE_ID,
        "locator": LOCATOR,
        "sectionId": SECTION_ID,
        "targetPath": [{"rawKey": "Zombie", "memberOrdinal": 1}],
        "carrierPath": [{"rawKey": "^.creature", "memberOrdinal": 6}],
        "selectionPath": [{"rawKey": "!.Slow", "memberOrdinal": 15}],
        "carrierBlockSha256": (
            "1a9607f80f14628f6354112cff8d8c7dd1c67aa4548d6238b7b16e539b0d2b9c"
        ),
        "selectionSha256": (
            "64878cfbb8a3f5b1eedfd3827f691c43197cd24c77e450c8b95359b6dc055d52"
        ),
    }
    expected_inherited = {
        **deepcopy(expected_source),
        "carrierPath": [{"rawKey": "^.creature", "memberOrdinal": 3}],
        "carrierBlockSha256": (
            "73b4d8c77d84bf3cc40a0a889a8b7e4c628fa47f1020cb11e794d41e663569b5"
        ),
        "selectionSha256": (
            "a12bb932fe5c1fcf682387d4bab22547e96fea4f25b01553dbedf03480c4da49"
        ),
    }
    expected = {
        "type": SLOW_MECHANIC_TYPE,
        "permanentCondition": {
            "condition": "slowed",
            "value": 1,
            "duration": {"kind": "permanent"},
        },
        "startTurn": {"actionsLost": 1},
        "reactionRestriction": {"canUseReactions": False},
        "inheritedFrom": expected_inherited,
        "source": expected_source,
        "rules": {
            "slowed": {"sourceId": "core-pc1", "locator": "446.5"}
        },
    }
    if (
        not isinstance(ability, Mapping)
        or ability.get("id") != SLOW_ABILITY_ID
        or ability.get("name") != "Slow"
        or ability.get("kind") != "passive"
        or ability.get("actionCost") is not None
        or ability.get("traits") != []
        or ability.get("supported") is not True
        or ability.get("rule") != CREATURE_RULE
        or mechanic != expected
    ):
        raise EngineInputError("Zombie Brute Slow mechanic is invalid")
    return deepcopy(expected)


def _follow_up() -> dict[str, Any]:
    return {
        "id": IMPROVED_PUSH_ID,
        "name": IMPROVED_PUSH_NAME,
        "appendage": FIST_STRIKE_ID,
        "supported": True,
        "trigger": "successful-strike",
        "triggerWindow": "triggered-on-hit",
        "actionCost": 0,
        "traits": ["attack"],
        "check": "athletics",
        "defense": "fortitude-dc",
        "multipleAttackPenalty": {"applies": False, "counts": False},
        "maximumTargetSizeDelta": 1,
        "successMaximumFeet": 5,
        "criticalSuccessMaximumFeet": 10,
        "criticalFailure": "source-falls-prone",
        "pathConstraint": "straight-away-from-source",
        "allowsSourceFollowStride": True,
        "sourceText": _RIDER_SOURCE_TEXT,
        "rule": deepcopy(IMPROVED_PUSH_RULE),
        "sourceRule": deepcopy(CREATURE_RULE),
        "rules": {
            "shove": deepcopy(SHOVE_RULE),
            "compareToDC": deepcopy(COMPARE_TO_DC_RULE),
            "degreeOfSuccess": deepcopy(DEGREE_RULE),
            "attackRoll": deepcopy(ATTACK_ROLL_RULE),
            "subordinateAction": deepcopy(SUBORDINATE_ACTION_RULE),
            "triggeredAction": deepcopy(TRIGGERED_ACTION_RULE),
            "forcedMovement": deepcopy(FORCED_MOVEMENT_RULE),
            "stride": deepcopy(STRIDE_RULE),
        },
    }


def activate_definition(
    definition: dict[str, Any],
    compilation: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Activate one authenticated Brute fist rider as a free Shove follow-up."""

    if not isinstance(definition, dict):
        raise EngineInputError("Zombie Brute definition must be mutable")
    if (
        not isinstance(compilation, Mapping)
        or compilation.get("family") != FORCED_MOVEMENT_FAMILY_ID
        or compilation.get("mechanicType") != MECHANIC_TYPE
        or compilation.get("sourceId") != SOURCE_ID
        or compilation.get("locator") != LOCATOR
        or compilation.get("strikeId") != "fist"
        or compilation.get("damageSourceText") != _DAMAGE_SOURCE_TEXT
        or compilation.get("sourceText") != _RIDER_SOURCE_TEXT
        or compilation.get("sourceVariant") != "improved-push"
        or compilation.get("sourceCoupling") != "direct"
        or compilation.get("successDistanceFeet") != 5
        or compilation.get("window") != "triggered-on-hit"
        or compilation.get("actionCost") != 0
        or compilation.get("consumerRule", {}).get("ruleId")
        != CONSUMER_RULE_ID
        or compilation.get("activationStatus") != "deferred"
    ):
        raise EngineInputError(
            "Zombie Brute Improved Push compilation is invalid"
        )
    source = definition.get("source")
    abilities = definition.get("abilities")
    strikes = definition.get("strikes")
    if (
        definition.get("name") != CREATURE_NAME
        or not isinstance(source, Mapping)
        or source.get("sourceId") != SOURCE_ID
        or source.get("locator") != LOCATOR
        or source.get("sectionId") != SECTION_ID
        or source.get("contentPath") != ["Zombie", CREATURE_NAME]
        or definition.get("space", {}).get("defaultReachFeet") != 10
        or not isinstance(abilities, list)
        or not isinstance(strikes, list)
    ):
        raise EngineInputError("Zombie Brute definition identity is invalid")
    slow = [
        ability
        for ability in abilities
        if isinstance(ability, Mapping)
        and ability.get("id") == SLOW_ABILITY_ID
    ]
    fists = [
        strike
        for strike in strikes
        if isinstance(strike, dict) and strike.get("id") == FIST_STRIKE_ID
    ]
    if len(slow) != 1 or len(fists) != 1:
        raise EngineInputError("Zombie Brute Slow or fist is ambiguous")
    _slow_spec(slow[0])
    fist = fists[0]
    damage = fist.get("damage")
    riders = damage.get("riderEffects") if isinstance(damage, dict) else None
    if (
        fist.get("name") != "fist"
        or fist.get("kind") != "melee"
        or fist.get("attackModifier") != 11
        or fist.get("reachFeet") != 10
        or fist.get("traits") != ["reach 10 feet"]
        or not isinstance(damage, dict)
        or damage.get("sourceText") != _DAMAGE_SOURCE_TEXT
        or damage.get("dice") != {"count": 1, "sides": 12}
        or damage.get("modifier") != 5
        or damage.get("type") != "bludgeoning"
        or riders
        != [
            {
                "name": "Improved Push 5 feet",
                "sourceText": _RIDER_SOURCE_TEXT,
                "supported": False,
            }
        ]
        or fist.get("followUps") != []
    ):
        raise EngineInputError("Zombie Brute fist source projection is invalid")

    damage["riderEffects"] = []
    fist["followUps"] = [_follow_up()]
    unsupported = definition.get("unsupportedMechanics")
    if not isinstance(unsupported, list) or "Improved Push 5 feet" not in unsupported:
        raise EngineInputError(
            "Zombie Brute unsupported rider admission is invalid"
        )
    definition["unsupportedMechanics"] = [
        item for item in unsupported if item != "Improved Push 5 feet"
    ]
    definition["improvedPushCompilation"] = {
        "activation": "bounded-runtime",
        "consumerRuleId": CONSUMER_RULE_ID,
        "sourceCompilation": deepcopy(dict(compilation)),
        "runtimeDeferrals": [
            "hazard-ledge-and-falling-resolution",
        ],
    }
    validate_definition_links(definition)
    return definition


def validate_definition_links(
    definition: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Validate the digest-bound Slow, fist, and Improved Push linkage."""

    source = definition.get("source") if isinstance(definition, Mapping) else None
    if (
        not isinstance(definition, Mapping)
        or definition.get("name") != CREATURE_NAME
        or not isinstance(source, Mapping)
        or source.get("sourceId") != SOURCE_ID
        or source.get("locator") != LOCATOR
        or source.get("sectionId") != SECTION_ID
        or source.get("contentPath") != ["Zombie", CREATURE_NAME]
    ):
        raise EngineInputError("Zombie Brute definition identity is invalid")
    abilities = definition.get("abilities")
    strikes = definition.get("strikes")
    if not isinstance(abilities, list) or not isinstance(strikes, list):
        raise EngineInputError("Zombie Brute definition is incomplete")
    slow = [
        item
        for item in abilities
        if isinstance(item, Mapping)
        and item.get("id") == SLOW_ABILITY_ID
    ]
    fists = [
        item
        for item in strikes
        if isinstance(item, Mapping) and item.get("id") == FIST_STRIKE_ID
    ]
    if len(slow) != 1 or len(fists) != 1:
        raise EngineInputError("Zombie Brute Slow or fist is ambiguous")
    _slow_spec(slow[0])
    fist = fists[0]
    damage = fist.get("damage")
    follow_ups = fist.get("followUps")
    compilation = definition.get("improvedPushCompilation")
    source_compilation = (
        compilation.get("sourceCompilation")
        if isinstance(compilation, Mapping)
        else None
    )
    if (
        fist.get("name") != "fist"
        or fist.get("kind") != "melee"
        or fist.get("attackModifier") != 11
        or fist.get("reachFeet") != 10
        or not isinstance(damage, Mapping)
        or damage.get("sourceText") != _DAMAGE_SOURCE_TEXT
        or damage.get("dice") != {"count": 1, "sides": 12}
        or damage.get("modifier") != 5
        or damage.get("type") != "bludgeoning"
        or damage.get("riderEffects") != []
        or follow_ups != [_follow_up()]
        or not isinstance(compilation, Mapping)
        or compilation.get("activation") != "bounded-runtime"
        or compilation.get("consumerRuleId") != CONSUMER_RULE_ID
        or compilation.get("runtimeDeferrals")
        != ["hazard-ledge-and-falling-resolution"]
        or not isinstance(source_compilation, Mapping)
        or source_compilation.get("family") != FORCED_MOVEMENT_FAMILY_ID
        or source_compilation.get("mechanicType") != MECHANIC_TYPE
        or source_compilation.get("sourceId") != SOURCE_ID
        or source_compilation.get("locator") != LOCATOR
        or source_compilation.get("strikeId") != "fist"
        or source_compilation.get("sourceText") != _RIDER_SOURCE_TEXT
        or source_compilation.get("activationStatus") != "deferred"
        or definition.get("unsupportedMechanics") != []
    ):
        raise EngineInputError("Zombie Brute definition links are invalid")
    return {
        "slowAbilityId": SLOW_ABILITY_ID,
        "fistStrikeId": FIST_STRIKE_ID,
        "improvedPushId": IMPROVED_PUSH_ID,
        "followUp": deepcopy(follow_ups[0]),
    }


def improved_push_spec(value: Mapping[str, Any], /) -> dict[str, Any]:
    """Validate and return one activated Improved Push follow-up."""

    expected = _follow_up()
    if not isinstance(value, Mapping) or any(
        value.get(key) != item for key, item in expected.items()
    ) or set(value) != set(expected):
        raise EngineInputError("Zombie Brute Improved Push follow-up is invalid")
    return deepcopy(expected)


__all__ = [
    "CONSUMER_RULE_ID",
    "CREATURE_NAME",
    "CREATURE_RULE",
    "FIST_STRIKE_ID",
    "IMPROVED_PUSH_ID",
    "IMPROVED_PUSH_NAME",
    "IMPROVED_PUSH_RULE",
    "LOCATOR",
    "MECHANIC_TYPE",
    "SOURCE_ID",
    "activate_definition",
    "improved_push_spec",
    "validate_definition_links",
]

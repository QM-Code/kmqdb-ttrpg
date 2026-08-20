"""Compile immediate saving-throw control riders on damaging Strikes."""

from __future__ import annotations

import re
from typing import Any

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceMember,
    RuleReference,
)


FAMILY_ID = "damaging-strike-save-control"
MECHANIC_TYPE = "damaging-strike-save-control"
ENSNARE_ABILITY_ID = "ensnare"

SAVE_RULE = RuleReference("core-pc1", "404.1")
DEGREE_RULE = RuleReference("core-pc1", "401.4")
DUPLICATE_EFFECTS_RULE = RuleReference("core-pc1", "399.1")
DAMAGE_RULE = RuleReference("core-pc1", "406.1")
DAMAGE_DEFENSE_ORDER_RULE = RuleReference("core-pc1", "407.3")
DAMAGE_APPLICATION_RULE = RuleReference("core-pc1", "407.4")
SPEED_RULE = RuleReference("core-pc1", "420.3")
LAND_SPEED_RULE = RuleReference("core-pc1", "420.4")
DURATION_RULE = RuleReference("core-pc1", "426.2")
IMMOBILIZED_RULE = RuleReference("core-pc1", "444.9")

_ENSNARE_RE = re.compile(
    r"\AWhen the (?P<source>[a-z][a-z ]*) damages a creature with a "
    r"(?P<first_strike>[a-z][a-z -]*) or (?P<second_strike>[a-z][a-z -]*) "
    r"Strike, (?P<narrative>[^.]+)\. The target must attempt a DC "
    r"(?P<dc>[0-9]+) Reflex save\. On a failure, the target takes a "
    r"-(?P<penalty>[0-9]+)-foot status penalty to its Speed for "
    r"(?P<failure_rounds>[0-9]+) round; on a critical failure, the target "
    r"is immobilized for (?P<immobilized_rounds>[0-9]+) round and the "
    r"penalty to Speed lasts for (?P<critical_minutes>[0-9]+) minute\.\Z",
    re.ASCII,
)


def _rule(reference: RuleReference) -> dict[str, str]:
    return reference.as_serialized()


def compile_damaging_strike_save_control(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the reviewed Ensnare grammar without naming its creature."""

    from .source_values import parse_decimal_integer

    if (
        source.source_label != "Ensnare"
        or source.action_cost is not None
        or source.kind != "passive"
        or source.traits
        or source.trigger
        or type(source.raw_member) is not RawSourceMember
        or source.raw_member.key != "!.Ensnare"
        or type(source.raw_member.value) is not str
        or source.raw_member.value != source.description
    ):
        return None
    match = _ENSNARE_RE.fullmatch(source.description)
    if match is None:
        return None
    dc = parse_decimal_integer(match.group("dc"))
    penalty = parse_decimal_integer(match.group("penalty"))
    failure_rounds = parse_decimal_integer(match.group("failure_rounds"))
    immobilized_rounds = parse_decimal_integer(
        match.group("immobilized_rounds")
    )
    critical_minutes = parse_decimal_integer(
        match.group("critical_minutes")
    )
    strike_labels = [
        match.group("first_strike"),
        match.group("second_strike"),
    ]
    if (
        dc is None
        or penalty is None
        or failure_rounds is None
        or immobilized_rounds is None
        or critical_minutes is None
        or dc <= 0
        or penalty <= 0
        or failure_rounds <= 0
        or immobilized_rounds <= 0
        or critical_minutes <= 0
        or len(strike_labels) != len(set(strike_labels))
        or any(label != label.strip() for label in strike_labels)
    ):
        return None
    critical_penalty_rounds = critical_minutes * 10
    movement_modifier = {
        "statistic": "speed",
        "scope": {
            "kind": "named-speed",
            "movementMode": "land",
        },
        "type": "status",
        "valueFeet": -penalty,
    }
    return AbilityCompilerPatch(
        mechanic={
            "type": MECHANIC_TYPE,
            "trigger": "strike-deals-positive-post-defense-damage",
            "strikeLabels": strike_labels,
            "savingThrow": {"type": "reflex", "dc": dc},
            "outcomes": {
                "critical-success": {"unaffected": True},
                "success": {"unaffected": True},
                "failure": {
                    "movementModifiers": [movement_modifier],
                    "speedPenaltyDuration": {
                        "unit": "rounds",
                        "value": failure_rounds,
                    },
                    "immobilized": False,
                },
                "critical-failure": {
                    "movementModifiers": [movement_modifier],
                    "speedPenaltyDuration": {
                        "unit": "rounds",
                        "value": critical_penalty_rounds,
                        "sourceUnit": f"{critical_minutes} minute",
                    },
                    "immobilized": True,
                    "immobilizedDuration": {
                        "unit": "rounds",
                        "value": immobilized_rounds,
                    },
                },
            },
            "rules": {
                "duplicateEffects": _rule(DUPLICATE_EFFECTS_RULE),
                "damage": _rule(DAMAGE_RULE),
                "damageDefenseOrder": _rule(DAMAGE_DEFENSE_ORDER_RULE),
                "damageApplication": _rule(DAMAGE_APPLICATION_RULE),
                "savingThrow": _rule(SAVE_RULE),
                "degreeOfSuccess": _rule(DEGREE_RULE),
                "speed": _rule(SPEED_RULE),
                "landSpeed": _rule(LAND_SPEED_RULE),
                "duration": _rule(DURATION_RULE),
                "immobilized": _rule(IMMOBILIZED_RULE),
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def ensnare_spec(ability: dict[str, Any], /) -> dict[str, Any]:
    """Return one closed, source-derived Ensnare mechanic or fail closed."""

    mechanic = ability.get("mechanic")
    source = ability.get("rule")
    if (
        ability.get("id") != ENSNARE_ABILITY_ID
        or ability.get("name") != "Ensnare"
        or ability.get("supported") is not True
        or ability.get("kind") != "passive"
        or ability.get("actionCost") is not None
        or ability.get("traits") != []
        or not isinstance(source, dict)
        or set(source) != {"sourceId", "locator"}
        or type(source.get("sourceId")) is not str
        or not source["sourceId"]
        or type(source.get("locator")) is not str
        or not source["locator"]
        or not isinstance(mechanic, dict)
        or set(mechanic)
        != {
            "type",
            "trigger",
            "strikeLabels",
            "strikeIds",
            "savingThrow",
            "outcomes",
            "rules",
        }
        or mechanic.get("type") != MECHANIC_TYPE
        or mechanic.get("trigger")
        != "strike-deals-positive-post-defense-damage"
    ):
        raise ValueError("Ensnare compiled mechanic is invalid")
    labels = mechanic.get("strikeLabels")
    strike_ids = mechanic.get("strikeIds")
    saving_throw = mechanic.get("savingThrow")
    outcomes = mechanic.get("outcomes")
    rules = mechanic.get("rules")
    if (
        not isinstance(labels, list)
        or not labels
        or any(type(label) is not str or not label for label in labels)
        or len(labels) != len(set(labels))
        or not isinstance(strike_ids, list)
        or len(strike_ids) != len(labels)
        or any(
            type(strike_id) is not str or not strike_id
            for strike_id in strike_ids
        )
        or len(strike_ids) != len(set(strike_ids))
        or not isinstance(saving_throw, dict)
        or set(saving_throw) != {"type", "dc"}
        or saving_throw.get("type") != "reflex"
        or type(saving_throw.get("dc")) is not int
        or saving_throw["dc"] <= 0
        or not isinstance(outcomes, dict)
        or set(outcomes)
        != {
            "critical-success",
            "success",
            "failure",
            "critical-failure",
        }
        or outcomes.get("critical-success") != {"unaffected": True}
        or outcomes.get("success") != {"unaffected": True}
        or rules
        != {
            "duplicateEffects": _rule(DUPLICATE_EFFECTS_RULE),
            "damage": _rule(DAMAGE_RULE),
            "damageDefenseOrder": _rule(DAMAGE_DEFENSE_ORDER_RULE),
            "damageApplication": _rule(DAMAGE_APPLICATION_RULE),
            "savingThrow": _rule(SAVE_RULE),
            "degreeOfSuccess": _rule(DEGREE_RULE),
            "speed": _rule(SPEED_RULE),
            "landSpeed": _rule(LAND_SPEED_RULE),
            "duration": _rule(DURATION_RULE),
            "immobilized": _rule(IMMOBILIZED_RULE),
        }
    ):
        raise ValueError("Ensnare compiled mechanic is invalid")

    failure = outcomes.get("failure")
    critical_failure = outcomes.get("critical-failure")
    if (
        not isinstance(failure, dict)
        or set(failure)
        != {
            "movementModifiers",
            "speedPenaltyDuration",
            "immobilized",
        }
        or failure.get("immobilized") is not False
        or not isinstance(critical_failure, dict)
        or set(critical_failure)
        != {
            "movementModifiers",
            "speedPenaltyDuration",
            "immobilized",
            "immobilizedDuration",
        }
        or critical_failure.get("immobilized") is not True
        or failure.get("movementModifiers")
        != critical_failure.get("movementModifiers")
    ):
        raise ValueError("Ensnare compiled outcomes are invalid")
    modifiers = failure["movementModifiers"]
    if (
        not isinstance(modifiers, list)
        or len(modifiers) != 1
        or modifiers[0]
        != {
            "statistic": "speed",
            "scope": {
                "kind": "named-speed",
                "movementMode": "land",
            },
            "type": "status",
            "valueFeet": modifiers[0].get("valueFeet"),
        }
        or type(modifiers[0].get("valueFeet")) is not int
        or modifiers[0]["valueFeet"] >= 0
    ):
        raise ValueError("Ensnare movement modifier is invalid")

    failure_duration = failure.get("speedPenaltyDuration")
    critical_duration = critical_failure.get("speedPenaltyDuration")
    immobilized_duration = critical_failure.get("immobilizedDuration")
    if (
        not isinstance(failure_duration, dict)
        or set(failure_duration) != {"unit", "value"}
        or failure_duration.get("unit") != "rounds"
        or type(failure_duration.get("value")) is not int
        or failure_duration["value"] <= 0
        or not isinstance(critical_duration, dict)
        or set(critical_duration) != {"unit", "value", "sourceUnit"}
        or critical_duration.get("unit") != "rounds"
        or type(critical_duration.get("value")) is not int
        or critical_duration["value"] <= 0
        or not re.fullmatch(
            r"[1-9][0-9]* minute",
            str(critical_duration.get("sourceUnit") or ""),
            re.ASCII,
        )
        or critical_duration["value"]
        != int(critical_duration["sourceUnit"].split()[0]) * 10
        or not isinstance(immobilized_duration, dict)
        or set(immobilized_duration) != {"unit", "value"}
        or immobilized_duration.get("unit") != "rounds"
        or type(immobilized_duration.get("value")) is not int
        or immobilized_duration["value"] <= 0
    ):
        raise ValueError("Ensnare durations are invalid")
    return mechanic


FRAGMENT = MechanicFamilyFragment(
    family_id=FAMILY_ID,
    mechanic_types=(MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="damaging-strike-ensnare",
            mechanic_type=MECHANIC_TYPE,
            compiler=compile_damaging_strike_save_control,
        ),
    ),
)


__all__ = [
    "DAMAGE_RULE",
    "DAMAGE_APPLICATION_RULE",
    "DAMAGE_DEFENSE_ORDER_RULE",
    "DEGREE_RULE",
    "DUPLICATE_EFFECTS_RULE",
    "DURATION_RULE",
    "ENSNARE_ABILITY_ID",
    "FAMILY_ID",
    "FRAGMENT",
    "IMMOBILIZED_RULE",
    "LAND_SPEED_RULE",
    "MECHANIC_TYPE",
    "SAVE_RULE",
    "SPEED_RULE",
    "compile_damaging_strike_save_control",
    "ensnare_spec",
]

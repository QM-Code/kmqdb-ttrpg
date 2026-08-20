"""Compile source-authored compound Stride activities."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import re
from typing import Any

from ..errors import EngineInputError
from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceObject,
    RuleReference,
)
from .source_values import parse_decimal_integer


GALLOP_ABILITY_ID = "gallop"
GALLOP_CREATURE_NAME = "Skeletal Horse"
GALLOP_LOCATOR = "313.1"
GALLOP_SOURCE_ID = "core-mc1"
GALLOP_SPEED_INCREASE_FEET = 10

SPRINT_ABILITY_ID = "sprint"
SPRINT_CREATURE_NAME = "Hadrosaurid"
SPRINT_LOCATOR = "98.2"
SPRINT_SOURCE_ID = "core-mc1"
SPRINT_SPEED_INCREASE_FEET = 20
SPRINT_FREQUENCY_ROUNDS = 10
SPRINT_FREQUENCY_SOURCE = "once per minute"
SPRINT_SPEED_BONUS_TYPE = "circumstance"

DOUBLE_STRIDE_SPEED_BOOST_MECHANIC_TYPE = "double-stride-speed-boost"


_CHARGE_RE = re.compile(
    r"\bStrides twice and then makes a "
    r"(?P<strike>[A-Za-z][A-Za-z -]*?) Strike\. "
    r"As long as it moved at least (?P<minimum>\d+) feet, it gains a "
    r"\+(?P<bonus>\d+) circumstance bonus to its attack roll\."
    r"(?: A (?P<maximum_size>[A-Za-z]+) or smaller creature struck by "
    r"this attack must succeed at a DC (?P<save_dc>\d+) Reflex save or "
    r"be knocked prone by the force of the blow\.)?$",
    re.IGNORECASE,
)
_POUNCE_RE = re.compile(
    r"^The (?P<subject>[A-Za-z][A-Za-z '\u2019-]*) Strides and makes a "
    r"Strike at the end of that movement\. If the "
    r"(?P<hidden_subject>[A-Za-z][A-Za-z '\u2019-]*) began this action "
    r"hidden, (?P<pronoun>it|they) (?P<verb>remains|remain) hidden until "
    r"after (?:this ability[’']s Strike|the ability[’']s Strike|the "
    r"attack)\.$",
    re.IGNORECASE,
)
_GALLOP_RE = re.compile(
    r"^The horse Strides twice, with its Speed increased by "
    r"(?P<increase>\d+) feet\.$",
    re.IGNORECASE,
)
_SPRINT_EFFECT = (
    "The hadrosaurid Strides twice. It has a +20-foot circumstance bonus "
    "to its Speed during these Strides."
)
_SPRINT_RAW_VALUE = RawSourceObject(
    (
        ("Action", "two"),
        ("Frequency", SPRINT_FREQUENCY_SOURCE),
        ("Effect", _SPRINT_EFFECT),
    )
)


def _double_stride_rules(
    *,
    circumstance_bonus: bool,
    frequency: bool,
) -> dict[str, dict[str, str]]:
    rules = {
        "subordinateActions": {
            "sourceId": "core-pc1",
            "locator": "414.4",
        },
        "stride": {
            "sourceId": "core-pc1",
            "locator": "418.3",
        },
        "speed": {
            "sourceId": "core-pc1",
            "locator": "420.3",
        },
    }
    if circumstance_bonus:
        rules["circumstanceBonus"] = {
            "sourceId": "core-pc1",
            "locator": "400.2",
        }
    if frequency:
        rules["duration"] = {
            "sourceId": "core-pc1",
            "locator": "426.2",
        }
    return rules


def _gallop_mechanic() -> dict[str, Any]:
    return {
        "type": DOUBLE_STRIDE_SPEED_BOOST_MECHANIC_TYPE,
        "strideCount": 2,
        "speedIncreaseFeet": GALLOP_SPEED_INCREASE_FEET,
        "movementMode": "land",
        "rules": _double_stride_rules(
            circumstance_bonus=False,
            frequency=False,
        ),
    }


def _sprint_mechanic() -> dict[str, Any]:
    return {
        "type": DOUBLE_STRIDE_SPEED_BOOST_MECHANIC_TYPE,
        "strideCount": 2,
        "speedIncreaseFeet": SPRINT_SPEED_INCREASE_FEET,
        "speedBonusType": SPRINT_SPEED_BONUS_TYPE,
        "movementMode": "land",
        "frequency": {
            "maximum": 1,
            "period": {
                "unit": "rounds",
                "value": SPRINT_FREQUENCY_ROUNDS,
                "source": "1 minute",
            },
            "decrementAt": "owner-start-turn",
        },
        "rules": _double_stride_rules(
            circumstance_bonus=True,
            frequency=True,
        ),
    }


def _semantic_sprint_mechanic() -> dict[str, Any]:
    """Exact source-free Sprint contract emitted by the semantic package."""

    return {
        "type": DOUBLE_STRIDE_SPEED_BOOST_MECHANIC_TYPE,
        "movementMode": "land",
        "strideCount": 2,
        "speedIncreaseFeet": SPRINT_SPEED_INCREASE_FEET,
        "speedBonusType": SPRINT_SPEED_BONUS_TYPE,
        "frequency": {
            "maximum": 1,
            "period": {
                "unit": "rounds",
                "value": SPRINT_FREQUENCY_ROUNDS,
            },
            "decrementAt": "owner-start-turn",
        },
        "ruleRefs": {
            "circumstanceBonus": "pf2er.rule:circumstance-bonus",
            "duration": "pf2er.rule:duration",
            "speed": "pf2er.rule:speed",
            "stride": "pf2er.rule:stride",
            "subordinateActions": "pf2er.rule:subordinate-actions",
        },
    }


def _normalized_double_stride_profile(
    profile: Mapping[str, Any],
    ability: Mapping[str, Any],
    *,
    source_free: bool,
) -> dict[str, Any]:
    mechanic = ability["mechanic"]
    if source_free:
        rule_evidence: object = {"ruleRef": ability["ruleRef"]}
        rules_evidence = {
            key: {"ruleRef": value}
            for key, value in mechanic["ruleRefs"].items()
        }
    else:
        rule_evidence = deepcopy(ability["rule"])
        rules_evidence = deepcopy(mechanic["rules"])
    normalized = deepcopy(dict(profile))
    normalized.update(
        {
            "sourceFree": source_free,
            "ruleEvidence": deepcopy(rule_evidence),
            "rulesEvidence": rules_evidence,
            "frequency": deepcopy(mechanic.get("frequency")),
            "movementMode": mechanic["movementMode"],
            "strideCount": mechanic["strideCount"],
            "speedIncreaseFeet": mechanic["speedIncreaseFeet"],
        }
    )
    return normalized


def double_stride_speed_boost_spec(
    definition: Mapping[str, Any],
    ability: Mapping[str, Any],
    /,
) -> dict[str, Any]:
    """Validate and identify one exact executable boosted double Stride."""

    source = definition.get("source") if isinstance(definition, Mapping) else None
    ability_id = ability.get("id") if isinstance(ability, Mapping) else None
    profiles = {
        GALLOP_ABILITY_ID: {
            "creatureName": GALLOP_CREATURE_NAME,
            "sourceId": GALLOP_SOURCE_ID,
            "locator": GALLOP_LOCATOR,
            "abilityName": "Gallop",
            "description": (
                "The horse Strides twice, with its Speed increased by 10 feet."
            ),
            "mechanic": _gallop_mechanic(),
            "speedBonusType": None,
            "frequencyRounds": 0,
        },
        SPRINT_ABILITY_ID: {
            "creatureName": SPRINT_CREATURE_NAME,
            "sourceId": SPRINT_SOURCE_ID,
            "locator": SPRINT_LOCATOR,
            "abilityName": "Sprint",
            "description": "",
            "mechanic": _sprint_mechanic(),
            "speedBonusType": SPRINT_SPEED_BONUS_TYPE,
            "frequencyRounds": SPRINT_FREQUENCY_ROUNDS,
        },
    }
    profile = profiles.get(str(ability_id or ""))
    if (
        ability_id == SPRINT_ABILITY_ID
        and definition.get("schema") == 2
        and definition.get("kind") == "pf2er-creature"
        and definition.get("id") == "pf2er:hadrosaurid"
        and definition.get("name") == SPRINT_CREATURE_NAME
        and set(ability)
        == {
            "id",
            "name",
            "kind",
            "actionCost",
            "traits",
            "supported",
            "ruleRef",
            "mechanic",
        }
        and ability.get("name") == "Sprint"
        and ability.get("kind") == "activity"
        and ability.get("actionCost") == 2
        and ability.get("traits") == []
        and ability.get("supported") is True
        and ability.get("ruleRef") == "pf2er.rule:hadrosaurid-sprint"
        and ability.get("mechanic") == _semantic_sprint_mechanic()
    ):
        assert profile is not None
        return _normalized_double_stride_profile(
            profile,
            ability,
            source_free=True,
        )
    if (
        profile is None
        or not isinstance(source, Mapping)
        or definition.get("name") != profile["creatureName"]
        or source.get("sourceId") != profile["sourceId"]
        or source.get("locator") != profile["locator"]
        or ability.get("name") != profile["abilityName"]
        or ability.get("kind") != "activity"
        or ability.get("actionCost") != 2
        or ability.get("traits") != []
        or ability.get("description") != profile["description"]
        or ability.get("supported") is not True
        or ability.get("rule")
        != {
            "sourceId": profile["sourceId"],
            "locator": profile["locator"],
        }
        or ability.get("mechanic") != profile["mechanic"]
    ):
        raise EngineInputError(
            "boosted double-Stride creature ability is invalid"
        )
    return _normalized_double_stride_profile(
        profile,
        ability,
        source_free=False,
    )


def compile_charge(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the current two-Stride, fixed-Strike Charge grammar."""

    match = _CHARGE_RE.search(source.description)
    if match is None:
        return None
    minimum_movement = parse_decimal_integer(match.group("minimum"))
    attack_bonus = parse_decimal_integer(match.group("bonus"))
    save_dc = (
        parse_decimal_integer(match.group("save_dc"))
        if match.group("maximum_size")
        else None
    )
    if (
        minimum_movement is None
        or attack_bonus is None
        or (match.group("maximum_size") and save_dc is None)
    ):
        return None
    if source.kind != "activity" or source.action_cost != 2:
        return None
    # The printed label validates an already identified source grammar; it is
    # not a dispatch key for selecting this compiler.
    if not source.source_label.casefold().endswith(" charge"):
        return None

    mechanic = {
        "type": "double-stride-strike",
        "strideCount": 2,
        "strikeId": re.sub(
            r"[^a-z0-9]+",
            "-",
            match.group("strike").casefold(),
        ).strip("-"),
        "minimumMovementFeet": minimum_movement,
        "attackBonus": {
            "type": "circumstance",
            "value": attack_bonus,
        },
    }
    if match.group("maximum_size"):
        mechanic["onHitSave"] = {
            "maximumTargetSize": match.group("maximum_size").casefold(),
            "type": "reflex",
            "dc": save_dc,
            "failureCondition": "prone",
        }
    return AbilityCompilerPatch(
        mechanic=mechanic,
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_pounce(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the current generic Stride-then-any-Strike Pounce grammar."""

    description = " ".join(source.description.split())
    match = _POUNCE_RE.fullmatch(description)
    canonical_name = " ".join(source.creature_name.split()).casefold()
    if match is None or not canonical_name:
        return None
    pronoun = match.group("pronoun").casefold()
    verb = match.group("verb").casefold()
    if (
        match.group("subject").casefold() != canonical_name
        or match.group("hidden_subject").casefold() != canonical_name
        or (pronoun, verb) not in {("it", "remains"), ("they", "remain")}
    ):
        return None
    if source.kind != "activity" or source.action_cost != 1:
        return None
    # Preserve the reviewed Pounce boundary only after semantic identification.
    if source.source_label.casefold() != "pounce":
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": "stride-strike",
            "strideCount": 1,
            "strikeSelection": "any",
            "hiddenState": {
                "preservedFrom": "activity-start",
                "until": "after-strike",
            },
            "rules": {
                "subordinateActions": {
                    "sourceId": "core-pc1",
                    "locator": "414.4",
                },
                "stride": {
                    "sourceId": "core-pc1",
                    "locator": "418.3",
                },
                "strike": {
                    "sourceId": "core-pc1",
                    "locator": "418.4",
                },
                "multipleAttackPenalty": {
                    "sourceId": "core-pc1",
                    "locator": "402.1",
                },
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        deferred_mechanics=("hidden-state-retention",),
    )


def compile_gallop(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the Skeletal Horse's exact two-Stride Gallop grammar."""

    match = _GALLOP_RE.fullmatch(" ".join(source.description.split()))
    increase = (
        parse_decimal_integer(match.group("increase"))
        if match is not None
        else None
    )
    if (
        match is None
        or increase != GALLOP_SPEED_INCREASE_FEET
        or source.source_label.casefold() != GALLOP_ABILITY_ID
        or source.creature_name.casefold()
        != GALLOP_CREATURE_NAME.casefold()
        or source.source_id != GALLOP_SOURCE_ID
        or source.locator != GALLOP_LOCATOR
        or source.kind != "activity"
        or source.action_cost != 2
        or source.traits
    ):
        return None

    return AbilityCompilerPatch(
        mechanic=_gallop_mechanic(),
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_sprint(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the Hadrosaurid's exact boosted double-Stride activity."""

    if (
        source.source_id != SPRINT_SOURCE_ID
        or source.locator != SPRINT_LOCATOR
        or source.creature_name != SPRINT_CREATURE_NAME
        or source.source_label != "Sprint"
        or source.raw_member.key != "!.Sprint"
        or source.raw_member.value != _SPRINT_RAW_VALUE
        or source.kind != "activity"
        or source.action_cost != 2
        or source.traits
        or source.trigger
        or source.description not in {"", _SPRINT_EFFECT}
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=_sprint_mechanic(),
        rule=RuleReference(SPRINT_SOURCE_ID, SPRINT_LOCATOR),
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="stride-strike",
    mechanic_types=(
        "double-stride-strike",
        DOUBLE_STRIDE_SPEED_BOOST_MECHANIC_TYPE,
        "stride-strike",
    ),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="charge",
            mechanic_type="double-stride-strike",
            compiler=compile_charge,
        ),
        AbilityCompilerRegistration(
            compiler_id="pounce",
            mechanic_type="stride-strike",
            compiler=compile_pounce,
        ),
        AbilityCompilerRegistration(
            compiler_id="skeletal-horse-gallop",
            mechanic_type=DOUBLE_STRIDE_SPEED_BOOST_MECHANIC_TYPE,
            compiler=compile_gallop,
        ),
        AbilityCompilerRegistration(
            compiler_id="hadrosaurid-sprint",
            mechanic_type=DOUBLE_STRIDE_SPEED_BOOST_MECHANIC_TYPE,
            compiler=compile_sprint,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "GALLOP_ABILITY_ID",
    "GALLOP_CREATURE_NAME",
    "GALLOP_LOCATOR",
    "GALLOP_SOURCE_ID",
    "GALLOP_SPEED_INCREASE_FEET",
    "DOUBLE_STRIDE_SPEED_BOOST_MECHANIC_TYPE",
    "SPRINT_ABILITY_ID",
    "SPRINT_CREATURE_NAME",
    "SPRINT_FREQUENCY_ROUNDS",
    "SPRINT_FREQUENCY_SOURCE",
    "SPRINT_LOCATOR",
    "SPRINT_SOURCE_ID",
    "SPRINT_SPEED_BONUS_TYPE",
    "SPRINT_SPEED_INCREASE_FEET",
    "compile_charge",
    "double_stride_speed_boost_spec",
    "compile_gallop",
    "compile_pounce",
    "compile_sprint",
]

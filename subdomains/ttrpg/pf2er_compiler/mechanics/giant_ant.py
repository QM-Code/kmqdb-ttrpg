"""Exact Monster Core Giant Ant Haul Away mechanics.

The source compiler owns identification of the duplicate-preserving
``core-mc1:21.3`` activity.  The encounter layer remains responsible for
shared movement, reactions, hazards, positions, and grapple-effect state.
"""

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
from .source_values import reviewed_giant_ant_venom_source


MECHANIC_TYPE = "haul-grabbed-creature"
SOURCE = {"sourceId": "core-mc1", "locator": "21.3"}
STRIDE_RULE = {"sourceId": "core-pc1", "locator": "418.3"}
SUBORDINATE_ACTIONS_RULE = {
    "sourceId": "core-pc1",
    "locator": "414.4",
}
MOVEMENT_TYPES_RULE = {"sourceId": "core-pc1", "locator": "420.3"}
ENCUMBERED_RULE = {"sourceId": "core-pc1", "locator": "443.7"}
GRABBED_RULE = {"sourceId": "core-pc1", "locator": "444.5"}
RESTRAINED_RULE = {"sourceId": "core-pc1", "locator": "446.3"}

_REQUIREMENTS = (
    "The giant ant has a Large or smaller creature grabbed."
)
_DESCRIPTION = (
    "The giant ant Strides up to its full Speed, carrying the grabbed "
    "creature with it. It is encumbered if the grabbed creature is Medium "
    "or larger."
)
_VENOM_DESCRIPTION = (
    "(poison) Saving Throw DC 18 Fortitude; Maximum Duration 4 rounds; "
    "Stage 1 1d8 poison and enfeebled 1 (1 round); Stage 2 1d10 poison "
    "and enfeebled 2 (1 round); Stage 3 1d12 poison and enfeebled 3 "
    "(1 round)"
)
_REQUIREMENTS_RE = re.compile(
    r"^The (?P<subject>[A-Za-z][A-Za-z '\u2019-]*) has a "
    r"(?P<maximum>[A-Za-z]+) or smaller creature grabbed\.$",
    re.IGNORECASE,
)
_DESCRIPTION_RE = re.compile(
    r"^The (?P<subject>[A-Za-z][A-Za-z '\u2019-]*) Strides up to its full "
    r"Speed, carrying the grabbed creature with it\. It is encumbered if "
    r"the grabbed creature is (?P<threshold>[A-Za-z]+) or larger\.$",
    re.IGNORECASE,
)
_SIZE_RANKS = {
    "tiny": 0,
    "small": 1,
    "medium": 2,
    "large": 3,
    "huge": 4,
    "gargantuan": 5,
}
_EXPECTED_MECHANIC = {
    "type": MECHANIC_TYPE,
    "targetRelation": "grabbed-or-restrained-by-source",
    "maximumTargetSize": "large",
    "movement": {
        "action": "Stride",
        "mode": "land",
        "maximum": "full-speed",
        "carriesTarget": True,
        "preservesSelectedGrab": True,
    },
    "encumbered": {
        "minimumTargetSize": "medium",
        "conditions": {"clumsy": 1},
        "speed": {
            "scope": "all-speeds",
            "type": "untyped",
            "valueFeet": -10,
            "minimumFeet": 5,
        },
        "rule": ENCUMBERED_RULE,
    },
    "rules": {
        "stride": STRIDE_RULE,
        "subordinateActions": SUBORDINATE_ACTIONS_RULE,
        "movementTypes": MOVEMENT_TYPES_RULE,
        "grabbed": GRABBED_RULE,
        "restrained": RESTRAINED_RULE,
    },
}


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _exact_activity_object(source: AbilitySource) -> bool:
    raw = source.raw_member
    value = raw.value
    return (
        raw.key == "!.Haul Away"
        and isinstance(value, RawSourceObject)
        and value.keys == ("Action", "Requirements", "Description")
        and value.values("Action") == ("two",)
        and value.values("Requirements") == (_REQUIREMENTS,)
        and value.values("Description") == (_DESCRIPTION,)
    )


def compile_haul_away(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the reviewed Giant Ant activity from exact source evidence."""

    requirements = None
    raw_value = source.raw_member.value
    if isinstance(raw_value, RawSourceObject):
        values = raw_value.values("Requirements")
        if len(values) == 1 and isinstance(values[0], str):
            requirements = _normalized(values[0])
    requirement_match = (
        _REQUIREMENTS_RE.fullmatch(requirements)
        if requirements is not None
        else None
    )
    description_match = _DESCRIPTION_RE.fullmatch(
        _normalized(source.description)
    )
    creature_name = _normalized(source.creature_name).casefold()
    if (
        requirement_match is None
        or description_match is None
        or requirement_match.group("subject").casefold() != creature_name
        or description_match.group("subject").casefold() != creature_name
        or requirement_match.group("maximum").casefold() != "large"
        or description_match.group("threshold").casefold() != "medium"
        or source.source_id != SOURCE["sourceId"]
        or source.locator != SOURCE["locator"]
        or source.source_label.casefold() != "haul away"
        or source.kind != "activity"
        or source.action_cost != 2
        or source.traits
        or source.trigger.strip()
        or not _exact_activity_object(source)
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=deepcopy(_EXPECTED_MECHANIC),
        rule=RuleReference(SOURCE["sourceId"], SOURCE["locator"]),
        # A subordinate Stride gives the activity the move trait.
        traits=("move",),
    )


reviewed_venom_source = reviewed_giant_ant_venom_source


def haul_away_spec(ability: Mapping[str, Any], /) -> dict[str, Any]:
    """Validate one compiled runtime projection and return its mechanic."""

    mechanic = ability.get("mechanic")
    if (
        ability.get("supported") is not True
        or ability.get("kind") != "activity"
        or ability.get("actionCost") != 2
        or ability.get("traits") != ["move"]
        or ability.get("rule") != SOURCE
        or not isinstance(mechanic, Mapping)
        or mechanic != _EXPECTED_MECHANIC
    ):
        raise EngineInputError("Giant Ant Haul Away mechanic is invalid")
    return deepcopy(dict(mechanic))


def target_size_rank(size: object, /) -> int:
    """Return one reviewed PF2ER size rank."""

    if not isinstance(size, str) or size.casefold() not in _SIZE_RANKS:
        raise EngineInputError("Haul Away target size is invalid")
    return _SIZE_RANKS[size.casefold()]


def encumbered_speed(
    speed: Mapping[str, Any],
    *,
    target_size: object,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Apply Haul Away's source-triggered Encumbered Speed reduction."""

    target_rank = target_size_rank(target_size)
    if (
        not isinstance(speed, Mapping)
        or isinstance(speed.get("totalFeet"), bool)
        or not isinstance(speed.get("totalFeet"), int)
        or int(speed["totalFeet"]) < 5
        or not isinstance(speed.get("modifiers"), list)
    ):
        raise EngineInputError("Haul Away Speed is invalid")
    result = deepcopy(dict(speed))
    if target_rank < _SIZE_RANKS["medium"]:
        return result, None
    modifier = {
        "type": "untyped",
        "valueFeet": -10,
        "source": "encumbered",
        "scopes": ["all-speeds"],
        "rule": deepcopy(ENCUMBERED_RULE),
    }
    result["modifiers"].append(deepcopy(modifier))
    result["minimumFeet"] = 5
    result["totalFeet"] = max(5, int(speed["totalFeet"]) - 10)
    return result, {
        "active": True,
        "conditions": {"clumsy": 1},
        "speedModifier": modifier,
        "rule": deepcopy(ENCUMBERED_RULE),
    }


FRAGMENT = MechanicFamilyFragment(
    family_id="giant-ant",
    mechanic_types=(MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="giant-ant-haul-away",
            mechanic_type=MECHANIC_TYPE,
            compiler=compile_haul_away,
        ),
    ),
)


__all__ = [
    "ENCUMBERED_RULE",
    "FRAGMENT",
    "GRABBED_RULE",
    "MECHANIC_TYPE",
    "MOVEMENT_TYPES_RULE",
    "RESTRAINED_RULE",
    "SOURCE",
    "STRIDE_RULE",
    "SUBORDINATE_ACTIONS_RULE",
    "compile_haul_away",
    "encumbered_speed",
    "haul_away_spec",
    "reviewed_venom_source",
    "target_size_rank",
]

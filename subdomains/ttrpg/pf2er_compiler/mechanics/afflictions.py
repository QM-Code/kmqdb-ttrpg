"""Compile the bounded round-based staged poison affliction grammar."""

from __future__ import annotations

import re
from typing import Any

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RuleReference,
)
from .source_values import (
    parse_decimal_integer,
    reviewed_giant_ant_venom_source,
)


AFFLICTION_MECHANIC_TYPE = "affliction"
BOLD_TAG_RE = re.compile(r"</?b>", re.IGNORECASE)
AFFLICTION_TRAITS_RE = re.compile(
    r"^\((?P<traits>[^()]+)\)\s*(?P<body>.+)$"
)
AFFLICTION_SAVE_RE = re.compile(
    r"^Saving Throw DC (?P<dc>\d+) "
    r"(?P<save>Fortitude|Reflex|Will)$",
    re.IGNORECASE,
)
AFFLICTION_MAXIMUM_RE = re.compile(
    r"^Maximum Duration (?P<value>\d+) "
    r"(?P<unit>round|rounds)$",
    re.IGNORECASE,
)
AFFLICTION_STAGE_RE = re.compile(
    r"^Stage (?P<number>\d+) (?P<effect>.+) "
    r"\((?P<interval>\d+) (?P<unit>round|rounds)\)$",
    re.IGNORECASE,
)
AFFLICTION_STAGE_DAMAGE_RE = re.compile(
    r"^(?P<count>\d+)d(?P<sides>\d+)\s+"
    r"(?P<type>[A-Za-z][A-Za-z-]*)"
    r"(?:\s+damage)?(?P<remainder>.*)$",
    re.IGNORECASE,
)
AFFLICTION_STAGE_CONDITION_RE = re.compile(
    r"^(?P<name>off-guard|clumsy|enfeebled|fatigued)"
    r"(?:\s+(?P<value>\d+))?$",
    re.IGNORECASE,
)
VALUED_AFFLICTION_CONDITIONS = frozenset(
    {
        "clumsy",
        "enfeebled",
    }
)
SUPPORTED_AFFLICTION_TRAITS = frozenset({"poison"})


def _parse_stage_effect(value: str) -> dict[str, Any] | None:
    """Compile the existing bounded damage and condition vocabulary."""

    text = str(value or "").strip().rstrip(".")
    if not text:
        return None
    damage = None
    condition_text = text
    damage_match = AFFLICTION_STAGE_DAMAGE_RE.fullmatch(text)
    if damage_match:
        dice_count = parse_decimal_integer(damage_match.group("count"))
        dice_sides = parse_decimal_integer(damage_match.group("sides"))
        if (
            dice_count is None
            or dice_count <= 0
            or dice_sides is None
            or dice_sides <= 0
        ):
            return None
        damage = {
            "dice": {
                "count": dice_count,
                "sides": dice_sides,
            },
            "modifier": 0,
            "type": damage_match.group("type").casefold(),
        }
        condition_text = damage_match.group("remainder").strip()
        condition_text = re.sub(
            r"^(?:,\s*)?(?:and\s+)?",
            "",
            condition_text,
            flags=re.IGNORECASE,
        )
    elif text.casefold() == "no effect":
        condition_text = ""

    conditions = []
    if condition_text:
        normalized = re.sub(
            r",\s*and\s+",
            ",",
            condition_text,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"\s+and\s+",
            ",",
            normalized,
            flags=re.IGNORECASE,
        )
        for raw_condition in normalized.split(","):
            match = AFFLICTION_STAGE_CONDITION_RE.fullmatch(
                raw_condition.strip()
            )
            if not match:
                return None
            name = match.group("name").casefold()
            raw_value = match.group("value")
            if (
                name in VALUED_AFFLICTION_CONDITIONS
            ) != (raw_value is not None):
                return None
            condition: dict[str, Any] = {"name": name}
            if raw_value is not None:
                condition_value = parse_decimal_integer(raw_value)
                if condition_value is None or condition_value <= 0:
                    return None
                condition["value"] = condition_value
            conditions.append(condition)
    if (
        damage is None
        and not conditions
        and text.casefold() != "no effect"
    ):
        return None
    return {
        "damage": damage,
        "conditions": conditions,
    }


def compile_affliction(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile one complete poison affliction without a printed-label gate."""

    # Generic affliction admission is intentionally independent of printed
    # creature and ability identity.  Only the reviewed Giant Ant source
    # coordinate enters its creature-specific exactness seam; asking the
    # Giant Ant matcher about every affliction would eagerly inspect labels
    # that this grammar does not otherwise use.
    if (
        source.source_id == "core-mc1"
        and source.locator == "21.3"
        and reviewed_giant_ant_venom_source(source) is False
    ):
        return None
    normalized = " ".join(
        BOLD_TAG_RE.sub("", str(source.description or "")).split()
    ).rstrip(".")
    inline_traits: list[str] = []
    trait_match = AFFLICTION_TRAITS_RE.fullmatch(normalized)
    if trait_match:
        inline_traits = [
            item.strip().casefold()
            for item in trait_match.group("traits").split(",")
        ]
        if any(not item for item in inline_traits):
            return None
        normalized = trait_match.group("body")
    traits = list(
        dict.fromkeys(
            [
                *source.traits,
                *inline_traits,
            ]
        )
    )
    if set(traits) != SUPPORTED_AFFLICTION_TRAITS:
        return None

    fields = [field.strip() for field in normalized.split(";")]
    if len(fields) < 3 or any(not field for field in fields):
        return None
    save_match = AFFLICTION_SAVE_RE.fullmatch(fields[0])
    maximum_match = AFFLICTION_MAXIMUM_RE.fullmatch(fields[1])
    if not save_match or not maximum_match:
        return None
    save_dc = parse_decimal_integer(save_match.group("dc"))
    maximum_duration = parse_decimal_integer(
        maximum_match.group("value")
    )
    if (
        save_dc is None
        or save_dc <= 0
        or maximum_duration is None
        or maximum_duration <= 0
    ):
        return None

    stages = []
    for expected_number, field in enumerate(fields[2:], start=1):
        stage_match = AFFLICTION_STAGE_RE.fullmatch(field)
        stage_number = (
            parse_decimal_integer(stage_match.group("number"))
            if stage_match is not None
            else None
        )
        if (
            not stage_match
            or stage_number != expected_number
        ):
            return None
        stage_interval = parse_decimal_integer(
            stage_match.group("interval")
        )
        if stage_interval is None or stage_interval <= 0:
            return None
        effects = _parse_stage_effect(stage_match.group("effect"))
        if effects is None:
            return None
        stages.append(
            {
                "number": expected_number,
                "interval": {
                    "value": stage_interval,
                    "unit": "rounds",
                },
                "effects": effects,
            }
        )
    if not stages:
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": AFFLICTION_MECHANIC_TYPE,
            "afflictionType": "poison",
            "savingThrow": {
                "type": save_match.group("save").casefold(),
                "dc": save_dc,
            },
            "maximumDuration": {
                "value": maximum_duration,
                "unit": "rounds",
            },
            "stages": stages,
            "rules": {
                "afflictions": {
                    "sourceId": "core-pc1",
                    "locator": "430.1",
                },
                "damageAndConditions": {
                    "sourceId": "core-pc1",
                    "locator": "430.8",
                },
                "multipleExposures": {
                    "sourceId": "core-pc1",
                    "locator": "430.9",
                },
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        traits=traits,
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="afflictions",
    mechanic_types=(AFFLICTION_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="affliction",
            mechanic_type=AFFLICTION_MECHANIC_TYPE,
            compiler=compile_affliction,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "compile_affliction",
]

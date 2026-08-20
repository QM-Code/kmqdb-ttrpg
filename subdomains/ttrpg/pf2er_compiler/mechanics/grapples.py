"""Compile reviewed Constrict and Tighten Coils source grammars."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RuleReference,
)
from .source_values import parse_decimal_integer


CONSTRICT_MECHANIC_TYPE = "held-target-basic-save-damage"
TIGHTEN_COILS_MECHANIC_TYPE = "escape-dc-increase-reaction"

CONSTRICT_RE = re.compile(
    r"^(?P<damage>.+?),\s+DC\s+(?P<dc>\d+)\s+"
    r"\(page (?P<page>\d+)\)\.?$",
    re.IGNORECASE,
)
CONSTRICT_DAMAGE_COMPONENT_RE = re.compile(
    r"^(?P<count>\d+)d(?P<sides>\d+)(?P<modifier>[+-]\d+)?\s+"
    r"(?P<damage_type>[A-Za-z][A-Za-z -]*)$",
    re.IGNORECASE,
)
HELD_CREATURE_ESCAPE_TRIGGER_RE = re.compile(
    r"^A creature grabbed or restrained by the "
    r"(?P<source>[A-Za-z][A-Za-z '\u2019-]*) attempts to Escape\.$",
    re.IGNORECASE,
)
ESCAPE_DC_INCREASE_RE = re.compile(
    r"^The DC of the Escape check is increased by (?P<value>\d+)\.$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _ConstrictGlossary:
    reference_page: int
    rule: RuleReference


_CONSTRICT_GLOSSARIES: Mapping[str, _ConstrictGlossary] = MappingProxyType(
    {
        "core-mc1": _ConstrictGlossary(
            reference_page=358,
            rule=RuleReference(source_id="core-mc1", locator="358.2"),
        ),
        "core-mc2": _ConstrictGlossary(
            reference_page=360,
            rule=RuleReference(source_id="core-mc2", locator="360.2"),
        ),
    }
)


def compile_constrict(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile one reviewed, source-bound Constrict damage expression."""

    description = " ".join(source.description.split())
    match = CONSTRICT_RE.fullmatch(description)
    if match is None:
        return None
    damage_components = []
    for raw_component in re.split(
        r"\s+plus\s+",
        match.group("damage"),
        flags=re.IGNORECASE,
    ):
        component_match = CONSTRICT_DAMAGE_COMPONENT_RE.fullmatch(
            raw_component
        )
        if component_match is None:
            return None
        count = parse_decimal_integer(component_match.group("count"))
        sides = parse_decimal_integer(component_match.group("sides"))
        raw_modifier = component_match.group("modifier")
        modifier = (
            0
            if raw_modifier is None
            else parse_decimal_integer(raw_modifier)
        )
        if (
            count is None
            or sides is None
            or modifier is None
            or count <= 0
            or sides <= 0
        ):
            return None
        damage_type = (
            component_match.group("damage_type")
            .strip()
            .casefold()
        )
        if "plus" in damage_type.split():
            return None
        damage_components.append(
            {
                "dice": {
                    "count": count,
                    "sides": sides,
                },
                "modifier": modifier,
                "type": damage_type,
            }
        )
    save_dc = parse_decimal_integer(match.group("dc"))
    reference_page = parse_decimal_integer(match.group("page"))
    if (
        not damage_components
        or save_dc is None
        or reference_page is None
        or save_dc <= 0
        or reference_page <= 0
    ):
        return None
    glossary = _CONSTRICT_GLOSSARIES.get(source.source_id)
    if (
        glossary is None
        or reference_page != glossary.reference_page
    ):
        return None
    if source.source_label.casefold() != "constrict":
        return None
    if source.kind != "activity" or source.action_cost != 1:
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": CONSTRICT_MECHANIC_TYPE,
            "targetRelation": "grabbed-or-restrained-by-source",
            "targetSelection": "any-positive-number",
            "sharedDamageRoll": True,
            "savingThrow": {
                "type": "fortitude",
                "dc": save_dc,
                "basic": True,
            },
            "damage": {
                **damage_components[0],
                "components": damage_components,
            },
            "rules": {
                "constrict": glossary.rule.as_serialized(),
                "basicSave": {
                    "sourceId": "core-pc1",
                    "locator": "404.1",
                },
                "damage": {
                    "sourceId": "core-pc1",
                    "locator": "406.1",
                },
                "doublingAndHalving": {
                    "sourceId": "core-pc1",
                    "locator": "407.1",
                },
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_tighten_coils(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the exact held-creature Escape DC reaction grammar."""

    trigger = " ".join(source.trigger.split())
    description = " ".join(source.description.split())
    trigger_match = HELD_CREATURE_ESCAPE_TRIGGER_RE.fullmatch(trigger)
    adjustment = ESCAPE_DC_INCREASE_RE.fullmatch(description)
    if trigger_match is None or adjustment is None:
        return None
    adjustment_value = parse_decimal_integer(adjustment.group("value"))
    if adjustment_value is None:
        return None
    if adjustment_value <= 0:
        return None
    if source.source_label.casefold() != "tighten coils":
        return None
    if source.kind != "reaction" or source.action_cost != "reaction":
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": TIGHTEN_COILS_MECHANIC_TYPE,
            "targetRelation": "grabbed-or-restrained-by-source",
            "triggerAction": "Escape",
            "dcAdjustment": adjustment_value,
            "rules": {
                "escape": {
                    "sourceId": "core-pc1",
                    "locator": "416.6",
                },
                "reactions": {
                    "sourceId": "core-pc1",
                    "locator": "436.5",
                },
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="grapples",
    mechanic_types=(
        CONSTRICT_MECHANIC_TYPE,
        TIGHTEN_COILS_MECHANIC_TYPE,
    ),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="constrict",
            mechanic_type=CONSTRICT_MECHANIC_TYPE,
            compiler=compile_constrict,
        ),
        AbilityCompilerRegistration(
            compiler_id="tighten-coils",
            mechanic_type=TIGHTEN_COILS_MECHANIC_TYPE,
            compiler=compile_tighten_coils,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "compile_constrict",
    "compile_tighten_coils",
]

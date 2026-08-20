"""Compile source-authored conditional Strike damage abilities."""

from __future__ import annotations

import re

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceMember,
    RawSourceObject,
    RuleReference,
)
from .source_values import parse_decimal_integer


SNEAK_ATTACK_RE = re.compile(
    r"\bdeals\s+(?:"
    r"(?P<leading_count>\d+)d(?P<leading_sides>\d+)\s+extra|"
    r"an\s+extra\s+(?P<trailing_count>\d+)d(?P<trailing_sides>\d+)"
    r")\s+precision\s+damage\s+to\s+"
    r"off-guard\s+creatures\.?$",
    re.IGNORECASE,
)
PACK_ATTACK_RE = re.compile(
    r"\b(?:"
    r"(?:the [A-Za-z][A-Za-z \u2019-]*['\u2019]s|its) Strikes deal|"
    r"(?:the [A-Za-z][A-Za-z \u2019-]*|it) deals"
    r") "
    r"(?P<count>\d+)d(?P<sides>\d+) extra damage to "
    r"(?:creatures|any creature that['\u2019]s) within reach of at least "
    r"(?P<allies>two|\d+) of (?:the [A-Za-z][A-Za-z \u2019-]*['\u2019]s|its) allies\.?$",
    re.IGNORECASE,
)
CLAWING_FEAR_DESCRIPTION = (
    "The scarecrow's strikes deal an additional 1d6 mental damage to "
    "frightened creatures."
)
WARG_PACK_ATTACK_RE = re.compile(
    r"\AThe warg['\u2019]s Strikes deal "
    r"(?P<count>\d+)d(?P<sides>\d+) extra damage to creatures within "
    r"the reach of at least (?P<allies>two|\d+) of the "
    r"warg['\u2019]s allies\.?\Z",
    re.IGNORECASE,
)
DESCRIPTION_ONLY_PACK_ATTACK_SOURCES = frozenset(
    (
        ("core-mc1", "341.2", "Warg"),
        ("core-mc1", "350.2", "Wolf"),
    )
)
SCALAR_PACK_ATTACK_SOURCES = frozenset(
    (
        ("core-mc1", "50.5", "Lion"),
        ("core-mc1", "96.5", "Velociraptor"),
    )
)


def _pack_attack_raw_member_matches(
    source: AbilitySource,
    /,
) -> bool:
    """Require the reviewed raw Pack Attack production and envelope."""

    if (
        source.source_label != "Pack Attack"
        or source.action_cost is not None
        or source.kind != "passive"
        or source.traits != ()
        or source.trigger != ""
        or type(source.raw_member) is not RawSourceMember
        or source.raw_member.key != "!.Pack Attack"
    ):
        return False

    raw_value = source.raw_member.value
    source_identity = (
        source.source_id,
        source.locator,
        source.creature_name,
    )
    if source_identity in SCALAR_PACK_ATTACK_SOURCES:
        return type(raw_value) is str and raw_value == source.description

    if type(raw_value) is RawSourceObject:
        if raw_value.keys != ("Description",):
            return False
        description_values = raw_value.values("Description")
        return (
            len(description_values) == 1
            and type(description_values[0]) is str
            and description_values[0] == source.description
        )

    if source_identity in DESCRIPTION_ONLY_PACK_ATTACK_SOURCES:
        return False
    return type(raw_value) is str and raw_value == source.description


def compile_sneak_attack(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the current off-guard precision-damage grammar."""

    match = SNEAK_ATTACK_RE.search(source.description)
    if match is None:
        return None
    count = parse_decimal_integer(
        match.group("leading_count")
        or match.group("trailing_count")
    )
    sides = parse_decimal_integer(
        match.group("leading_sides")
        or match.group("trailing_sides")
    )
    if (
        count is None
        or sides is None
        or count <= 0
        or sides <= 0
    ):
        return None
    if source.source_label.casefold() != "sneak attack":
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": "conditional-damage",
            "targetCondition": "off-guard",
            "damage": {
                "dice": {
                    "count": count,
                    "sides": sides,
                },
                "modifier": 0,
                "type": "precision",
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_pack_attack(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the current allies-in-reach damage grammar."""

    match = PACK_ATTACK_RE.search(source.description)
    if (
        match is None
        and source.source_id == "core-mc1"
        and source.locator == "341.2"
        and source.creature_name == "Warg"
    ):
        match = WARG_PACK_ATTACK_RE.fullmatch(source.description)
    if match is None:
        return None
    count = parse_decimal_integer(match.group("count"))
    sides = parse_decimal_integer(match.group("sides"))
    allies = match.group("allies")
    minimum_allies = (
        2
        if allies.casefold() == "two"
        else parse_decimal_integer(allies)
    )
    if (
        count is None
        or sides is None
        or minimum_allies is None
        or count <= 0
        or sides <= 0
        or minimum_allies <= 0
    ):
        return None
    if not _pack_attack_raw_member_matches(source):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": "conditional-damage",
            "targetRelation": "within-allies-reach",
            "minimumAllies": minimum_allies,
            "damage": {
                "dice": {
                    "count": count,
                    "sides": sides,
                },
                "modifier": 0,
                "type": "same-as-strike",
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_clawing_fear(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the Scarecrow's exact frightened-target damage rider."""

    raw_value = source.raw_member.value
    raw_matches = raw_value == CLAWING_FEAR_DESCRIPTION
    if type(raw_value) is RawSourceObject:
        raw_matches = (
            raw_value.keys == ("Description",)
            and raw_value.values("Description")
            == (CLAWING_FEAR_DESCRIPTION,)
        )
    if (
        source.source_id != "core-mc1"
        or source.locator != "297.1"
        or source.creature_name != "Scarecrow"
        or source.source_label != "Clawing Fear"
        or source.raw_member.key != "!.Clawing Fear"
        or source.kind != "passive"
        or source.action_cost is not None
        or source.traits
        or source.trigger
        or source.description != CLAWING_FEAR_DESCRIPTION
        or not raw_matches
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": "conditional-damage",
            "targetCondition": "frightened",
            "damage": {
                "dice": {"count": 1, "sides": 6},
                "modifier": 0,
                "type": "mental",
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="conditional-damage",
    mechanic_types=("conditional-damage",),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="sneak-attack",
            mechanic_type="conditional-damage",
            compiler=compile_sneak_attack,
        ),
        AbilityCompilerRegistration(
            compiler_id="pack-attack",
            mechanic_type="conditional-damage",
            compiler=compile_pack_attack,
        ),
        AbilityCompilerRegistration(
            compiler_id="clawing-fear",
            mechanic_type="conditional-damage",
            compiler=compile_clawing_fear,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "compile_clawing_fear",
    "compile_pack_attack",
    "compile_sneak_attack",
]

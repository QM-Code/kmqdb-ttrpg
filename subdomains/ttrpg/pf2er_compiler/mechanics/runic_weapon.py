"""Exact Player Core Runic Weapon descriptor and shared rune constants."""

from __future__ import annotations

from typing import Any

from .contracts import RawSourceObject
from .source_authority import VerifiedSourceSelection


SPELL_ID = "runic-weapon"
SOURCE = {"sourceId": "core-pc1", "locator": "354.3"}
EFFECT_FAMILY = "target-weapon-striking-runes"
EFFECT_KIND = "spell-weapon-striking-runes"
ATTACK_ITEM_BONUS = 1
DAMAGE_DICE_COUNT = 2
DURATION_ROUNDS = 10
DURATION_SOURCE = "1 minute"
TOUCH_DISTANCE_FEET = 5

DESCRIPTION = (
    "The weapon glimmers with magic as temporary runes carve down its "
    "length. The target becomes a +1 striking weapon, gaining a +1 item "
    "bonus to attack rolls and increasing the number of weapon damage dice "
    "to two."
)
HEIGHTENED_SIXTH = "The weapon is +2 greater striking."
HEIGHTENED_NINTH = "The weapon is +3 major striking."

EFFECT_DEFINITION = {
    "type": EFFECT_FAMILY,
    "range": {
        "kind": "touch",
        "maximumDistanceFeet": TOUCH_DISTANCE_FEET,
    },
    "target": "one-weapon-unattended-or-wielded-by-willing-creature",
    "attackItemBonus": ATTACK_ITEM_BONUS,
    "damageDiceCount": DAMAGE_DICE_COUNT,
    "duration": {
        "rounds": DURATION_ROUNDS,
        "source": DURATION_SOURCE,
    },
    "heightened": {
        "6th": {"potencyBonus": 2, "strikingRune": "greater"},
        "9th": {"potencyBonus": 3, "strikingRune": "major"},
    },
}


def _unique_member(
    value: RawSourceObject,
    key: str,
    *,
    error_type: type[ValueError],
) -> object:
    matches = tuple(
        member
        for member in value.members
        if member.key == key
    )
    if len(matches) != 1:
        raise error_type(
            f"Runic Weapon requires one exact {key!r} member; "
            f"found {len(matches)}"
        )
    return matches[0].value


def compile_descriptor(
    provider: VerifiedSourceSelection,
    *,
    error_type: type[ValueError],
) -> dict[str, Any]:
    """Compile the exact reviewed rank-1 Runic Weapon provider."""

    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise error_type(
            "Runic Weapon provider is not an exact block"
        )
    expected_scalars = {
        "Range": "touch",
        "Targets": (
            "1 weapon that is unattended or wielded by a willing creature"
        ),
        "Duration": DURATION_SOURCE,
    }
    for key, expected in expected_scalars.items():
        if _unique_member(
            value,
            key,
            error_type=error_type,
        ) != expected:
            raise error_type(
                f"Runic Weapon reviewed {key} differs"
            )
    description = _unique_member(
        value,
        "Description",
        error_type=error_type,
    )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=error_type,
    )
    if (
        type(description) is not RawSourceObject
        or tuple(member.key for member in description.members)
        != ("~.p",)
        or description.members[0].value != DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members)
        != ("6th", "9th")
        or heightened.members[0].value != HEIGHTENED_SIXTH
        or heightened.members[1].value != HEIGHTENED_NINTH
    ):
        raise error_type(
            "Runic Weapon reviewed effect or heightening text differs"
        )
    return {
        "type": EFFECT_FAMILY,
        "range": {
            "kind": "touch",
            "maximumDistanceFeet": TOUCH_DISTANCE_FEET,
        },
        "target": (
            "one-weapon-unattended-or-wielded-by-willing-creature"
        ),
        "attackItemBonus": ATTACK_ITEM_BONUS,
        "damageDiceCount": DAMAGE_DICE_COUNT,
        "duration": {
            "rounds": DURATION_ROUNDS,
            "source": DURATION_SOURCE,
        },
        "heightened": {
            "6th": {
                "potencyBonus": 2,
                "strikingRune": "greater",
            },
            "9th": {
                "potencyBonus": 3,
                "strikingRune": "major",
            },
        },
    }


__all__ = [
    "ATTACK_ITEM_BONUS",
    "DAMAGE_DICE_COUNT",
    "DURATION_ROUNDS",
    "DURATION_SOURCE",
    "EFFECT_DEFINITION",
    "EFFECT_FAMILY",
    "EFFECT_KIND",
    "SOURCE",
    "SPELL_ID",
    "TOUCH_DISTANCE_FEET",
    "compile_descriptor",
]

"""Normalized rank-1 Heal spell contract shared by reviewed carriers.

The Player Core provider remains the authority for the prose.  This module
owns only the closed runtime descriptor that both source compilers emit after
independently validating that exact provider.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


HEAL_SPELL_ID = "heal"
HEAL_SOURCE = {"sourceId": "core-pc1", "locator": "335.2"}

HEAL_EFFECT_DEFINITION = {
    "type": "variable-vitality-healing-and-damage",
    "vitalityAmount": {
        "dice": {"count": 1, "size": 8},
    },
    "actionForms": {
        "1": {
            "actionCost": 1,
            "additionalTraits": [],
            "range": {
                "kind": "touch",
                "maximumDistanceFeet": 5,
            },
            "target": "one-willing-living-or-one-undead-creature",
        },
        "2": {
            "actionCost": 2,
            "additionalTraits": ["concentrate"],
            "range": {
                "kind": "distance",
                "maximumDistanceFeet": 30,
            },
            "target": "one-willing-living-or-one-undead-creature",
            "livingHealingModifier": 8,
        },
        "3": {
            "actionCost": 3,
            "additionalTraits": ["concentrate"],
            "area": {
                "shape": "emanation",
                "radiusFeet": 30,
                "origin": "caster",
            },
            "targets": ["all-living", "all-undead"],
        },
    },
    "undeadSavingThrow": {
        "type": "fortitude",
        "basic": True,
        "dcSource": "casting",
    },
    "heightened": {
        "everyRanks": 1,
        "vitalityDice": {"count": 1, "size": 8},
        "twoActionLivingHealingModifier": 8,
    },
}


def heal_effect_definition() -> dict[str, Any]:
    """Return an isolated exact descriptor for a compiled spell row."""

    return deepcopy(HEAL_EFFECT_DEFINITION)


def heal_action_form(
    effect: Any,
    action_count: Any,
) -> dict[str, Any]:
    """Select one exact reviewed action form or fail closed."""

    if effect != HEAL_EFFECT_DEFINITION:
        raise ValueError("Heal compiled effect is invalid")
    if isinstance(action_count, bool) or not isinstance(action_count, int):
        raise ValueError("Heal actionCount must be an integer")
    form = HEAL_EFFECT_DEFINITION["actionForms"].get(str(action_count))
    if form is None:
        raise ValueError("Heal actionCount must be 1, 2, or 3")
    return deepcopy(form)


__all__ = [
    "HEAL_EFFECT_DEFINITION",
    "HEAL_SOURCE",
    "HEAL_SPELL_ID",
    "heal_action_form",
    "heal_effect_definition",
]

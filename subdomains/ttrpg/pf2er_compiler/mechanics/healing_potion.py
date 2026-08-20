"""Closed runtime contract for GM Core Healing Potion variants."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SOURCE = {"sourceId": "core-gmc", "locator": "259.5"}
ACTIVATING_ITEMS_RULE = {"sourceId": "core-gmc", "locator": "220.1"}
CONSUMABLE_RULE = {"sourceId": "core-gmc", "locator": "255.1"}
ITEM_ID_PREFIX = "core-gmc:item:healing-potion-"
VARIANTS = {
    "minor": {
        "level": 1,
        "price": "4 gp",
        "healing": {
            "dice": {"count": 1, "sides": 8},
            "modifier": 0,
        },
    },
    "lesser": {
        "level": 3,
        "price": "12 gp",
        "healing": {
            "dice": {"count": 2, "sides": 8},
            "modifier": 5,
        },
    },
    "moderate": {
        "level": 6,
        "price": "50 gp",
        "healing": {
            "dice": {"count": 3, "sides": 8},
            "modifier": 10,
        },
    },
    "greater": {
        "level": 12,
        "price": "400 gp",
        "healing": {
            "dice": {"count": 6, "sides": 8},
            "modifier": 20,
        },
    },
    "major": {
        "level": 18,
        "price": "5,000 gp",
        "healing": {
            "dice": {"count": 8, "sides": 8},
            "modifier": 30,
        },
    },
}


def item_id(variant: str) -> str:
    if variant not in VARIANTS:
        raise ValueError("Healing Potion variant is unsupported")
    return ITEM_ID_PREFIX + variant


def definition_name(variant: str) -> str:
    if variant not in VARIANTS:
        raise ValueError("Healing Potion variant is unsupported")
    return f"Healing Potion ({variant.title()})"


def mechanics(variant: str) -> dict[str, Any]:
    """Return the exact catalog/runtime item mechanics for one variant."""

    profile = VARIANTS.get(variant)
    if profile is None:
        raise ValueError("Healing Potion variant is unsupported")
    return {
        "schema": 1,
        "id": item_id(variant),
        "name": definition_name(variant),
        "kind": "consumable",
        "consumableKind": "healing-potion",
        "variant": variant,
        "level": int(profile["level"]),
        "rarity": "common",
        "price": str(profile["price"]),
        "bulk": "light",
        "traits": [
            "consumable",
            "healing",
            "magical",
            "potion",
            "vitality",
        ],
        "hands": {
            "holding": 1,
            "requiredToUse": 1,
            "freeHandCompletesUse": False,
        },
        "activation": {
            "actionCost": 1,
            "traits": ["manipulate"],
            "target": "self",
            "effect": {
                "type": "hit-point-healing",
                "healing": deepcopy(profile["healing"]),
            },
        },
        "consumedOnUse": True,
        "source": deepcopy(SOURCE),
        "rules": {
            "activation": deepcopy(ACTIVATING_ITEMS_RULE),
            "consumable": deepcopy(CONSUMABLE_RULE),
        },
    }


def validated_mechanics(value: object) -> dict[str, Any]:
    """Return one exact supported potion definition or fail closed."""

    if not isinstance(value, dict):
        raise ValueError("Healing Potion mechanics are invalid")
    variant = value.get("variant")
    if not isinstance(variant, str):
        raise ValueError("Healing Potion variant is invalid")
    expected = mechanics(variant)
    if value != expected:
        raise ValueError("Healing Potion mechanics changed")
    return deepcopy(expected)


__all__ = [
    "ACTIVATING_ITEMS_RULE",
    "CONSUMABLE_RULE",
    "ITEM_ID_PREFIX",
    "SOURCE",
    "VARIANTS",
    "definition_name",
    "item_id",
    "mechanics",
    "validated_mechanics",
]

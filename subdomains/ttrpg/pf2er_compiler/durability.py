"""Pure PF2ER item-durability mechanics.

The encounter engine owns exact item custody and event sequencing.  This
module owns only source-backed durability profiles and deterministic
damage/repair calculations over one exact live item.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .errors import EngineInputError


ITEM_DAMAGE_RULE = {"sourceId": "core-pc1", "locator": "269.10"}
OBJECT_IMMUNITIES_RULE = {
    "sourceId": "core-pc1",
    "locator": "269.11",
}
BROKEN_RULE = {"sourceId": "core-pc1", "locator": "442.7"}
REPAIR_RULE = {"sourceId": "core-pc1", "locator": "236.6"}
SHODDY_RULE = {"sourceId": "core-pc1", "locator": "270.2"}
MATERIAL_STATISTICS_RULE = {
    "sourceId": "core-gmc",
    "locator": "252.2",
}

OBJECT_IMMUNE_DAMAGE_TYPES = frozenset(
    {
        "bleed",
        "mental",
        "poison",
        "spirit",
        "vitality",
        "void",
    }
)
OBJECT_IMMUNE_EFFECT_TRAITS = frozenset(
    {
        "death",
        "disease",
        "healing",
        "nonlethal",
    }
)
ARMOR_BROKEN_STATUS_PENALTIES = {
    "light": -1,
    "medium": -2,
    "heavy": -3,
}

# These are deliberately bounded profiles, not material inference.  Each key
# names an exact row in GM Core's ordinary-material table and retains that
# row's example basis for compiler/test review.
ORDINARY_MATERIAL_PROFILES: dict[str, dict[str, Any]] = {
    "thin-iron-or-steel": {
        "material": "thin iron or steel",
        "hardness": 5,
        "maximumHitPoints": 20,
        "brokenThreshold": 10,
        "exampleBasis": "sword",
        "rule": deepcopy(MATERIAL_STATISTICS_RULE),
    },
    "leather": {
        "material": "leather",
        "hardness": 4,
        "maximumHitPoints": 16,
        "brokenThreshold": 8,
        "exampleBasis": "leather armor",
        "rule": deepcopy(MATERIAL_STATISTICS_RULE),
    },
    "iron-or-steel": {
        "material": "iron or steel",
        "hardness": 9,
        "maximumHitPoints": 36,
        "brokenThreshold": 18,
        "exampleBasis": "iron or steel armor",
        "rule": deepcopy(MATERIAL_STATISTICS_RULE),
    },
}

# Slice-4 test carriers are exact reviewed item identities.  Other equipment
# remains durability-blocked until its construction/material is compiled.
ITEM_PROFILE_KEYS = {
    "core-pc1:item:longsword": "thin-iron-or-steel",
    "core-pc1:item:shortsword": "thin-iron-or-steel",
    "core-pc1:item:leather": "leather",
    "core-pc1:item:breastplate": "iron-or-steel",
    "core-pc1:item:chain-mail": "iron-or-steel",
    "core-pc1:item:full-plate": "iron-or-steel",
}


def _integer(
    value: object,
    label: str,
    *,
    minimum: int = 0,
) -> int:
    if type(value) is not int or value < minimum:
        raise EngineInputError(f"{label} is invalid")
    return value


def reviewed_item_profile(item_id: object) -> dict[str, Any] | None:
    """Return one explicitly reviewed ordinary-material item profile."""

    key = ITEM_PROFILE_KEYS.get(str(item_id or ""))
    if key is None:
        return None
    return deepcopy(ORDINARY_MATERIAL_PROFILES[key])


def _base_profile(definition: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = definition.get("durability")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise EngineInputError("item durability profile is invalid")
    hardness = _integer(raw.get("hardness"), "item Hardness")
    maximum = _integer(
        raw.get("maximumHitPoints"),
        "item maximum Hit Points",
        minimum=1,
    )
    threshold = _integer(
        raw.get("brokenThreshold"),
        "item Broken Threshold",
        minimum=1,
    )
    if threshold >= maximum:
        raise EngineInputError(
            "item Broken Threshold must be below maximum Hit Points"
        )
    rule = raw.get("rule")
    if (
        not isinstance(rule, Mapping)
        or not str(rule.get("sourceId") or "")
        or not str(rule.get("locator") or "")
    ):
        raise EngineInputError(
            "item durability profile lacks source provenance"
        )
    result = deepcopy(dict(raw))
    result.update(
        {
            "hardness": hardness,
            "maximumHitPoints": maximum,
            "brokenThreshold": threshold,
            "rule": deepcopy(dict(rule)),
        }
    )
    return result


def durability_profile(
    definition: Mapping[str, Any],
    *,
    quality: object = None,
) -> dict[str, Any] | None:
    """Resolve an exact item's effective profile, including shoddy quality."""

    profile = _base_profile(definition)
    if profile is None:
        return None
    normalized_quality = str(quality or "").strip().casefold()
    if normalized_quality not in {"", "ordinary", "shoddy"}:
        raise EngineInputError(
            f"item durability quality is unsupported: {quality}"
        )
    if normalized_quality != "shoddy":
        return profile
    maximum = max(1, int(profile["maximumHitPoints"]) // 2)
    threshold = max(1, int(profile["brokenThreshold"]) // 2)
    if threshold >= maximum:
        raise EngineInputError(
            "shoddy durability profile has no valid Broken Threshold"
        )
    profile.update(
        {
            "maximumHitPoints": maximum,
            "brokenThreshold": threshold,
            "quality": "shoddy",
            "qualityAdjustment": {
                "hitPointsFactor": {
                    "numerator": 1,
                    "denominator": 2,
                },
                "brokenThresholdFactor": {
                    "numerator": 1,
                    "denominator": 2,
                },
                "hardnessUnchanged": True,
                "rule": deepcopy(SHODDY_RULE),
            },
        }
    )
    return profile


def validate_live_item(
    item: Mapping[str, Any],
    definition: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Validate current HP against the item's exact effective profile."""

    profile = durability_profile(
        definition,
        quality=item.get("quality"),
    )
    current = item.get("currentHitPoints")
    if profile is None:
        if current is not None:
            raise EngineInputError(
                "non-durable item has current Hit Points"
            )
        return None
    current_hp = _integer(
        current,
        "item current Hit Points",
        minimum=1,
    )
    if current_hp > int(profile["maximumHitPoints"]):
        raise EngineInputError(
            "item current Hit Points exceed its maximum"
        )
    return profile


def _function_state(
    definition: Mapping[str, Any],
    *,
    current_hit_points: int,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    destroyed = current_hit_points <= 0
    broken = (
        not destroyed
        and current_hit_points <= int(profile["brokenThreshold"])
    )
    item_kind = str(definition.get("kind") or "")
    result: dict[str, Any] = {
        "destroyed": destroyed,
        "broken": broken,
        "normalFunctionAvailable": not destroyed and not broken,
        "grantsBonuses": not destroyed and not broken,
    }
    if item_kind == "armor":
        category = str(definition.get("armorCategory") or "")
        if category not in ARMOR_BROKEN_STATUS_PENALTIES:
            raise EngineInputError(
                "durable armor category is invalid"
            )
        result.update(
            {
                "armorCategory": category,
                "armorClassItemBonusRetained": not destroyed,
                "armorClassStatusPenalty": (
                    ARMOR_BROKEN_STATUS_PENALTIES[category]
                    if broken
                    else 0
                ),
                "normalFunctionAvailable": not destroyed,
                "grantsBonuses": not destroyed,
            }
        )
    return result


def item_condition(
    item: Mapping[str, Any],
    definition: Mapping[str, Any],
) -> dict[str, Any]:
    profile = validate_live_item(item, definition)
    if profile is None:
        return {
            "durable": False,
            "broken": False,
            "destroyed": False,
            "normalFunctionAvailable": True,
            "grantsBonuses": True,
        }
    return {
        "durable": True,
        **_function_state(
            definition,
            current_hit_points=int(item["currentHitPoints"]),
            profile=profile,
        ),
        "hardness": int(profile["hardness"]),
        "maximumHitPoints": int(profile["maximumHitPoints"]),
        "brokenThreshold": int(profile["brokenThreshold"]),
    }


def apply_item_damage(
    item: Mapping[str, Any],
    definition: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    damage_type: object,
    incoming_damage: object,
    effect_traits: object = (),
) -> dict[str, Any]:
    """Return one deterministic successor item and complete damage evidence."""

    profile = validate_live_item(item, definition)
    if profile is None:
        raise EngineInputError(
            "target item has no compiled durability profile"
        )
    if not isinstance(source, Mapping) or not source:
        raise EngineInputError("item damage source is invalid")
    normalized_type = str(damage_type or "").strip().casefold()
    if not normalized_type:
        raise EngineInputError("item damage type is invalid")
    incoming = _integer(
        incoming_damage,
        "incoming item damage",
    )
    if not isinstance(effect_traits, (list, tuple, set, frozenset)):
        raise EngineInputError("item damage effect traits are invalid")
    traits = sorted(
        {
            str(trait).strip().casefold()
            for trait in effect_traits
            if str(trait).strip()
        }
    )
    if len(traits) != len(effect_traits):
        raise EngineInputError(
            "item damage effect traits are empty or duplicated"
        )
    matched_immunities = sorted(
        {
            *(
                [normalized_type]
                if normalized_type in OBJECT_IMMUNE_DAMAGE_TYPES
                else []
            ),
            *OBJECT_IMMUNE_EFFECT_TRAITS.intersection(traits),
        }
    )
    immune = bool(matched_immunities)
    hardness = int(profile["hardness"])
    prevented_by_hardness = (
        0 if immune else min(incoming, hardness)
    )
    applied = (
        0
        if immune
        else max(0, incoming - hardness)
    )
    before_hp = int(item["currentHitPoints"])
    after_hp = max(0, before_hp - applied)
    before_function = _function_state(
        definition,
        current_hit_points=before_hp,
        profile=profile,
    )
    after_function = _function_state(
        definition,
        current_hit_points=after_hp,
        profile=profile,
    )
    before_broken = bool(before_function["broken"])
    after_broken = bool(after_function["broken"])
    destroyed = bool(after_function["destroyed"])
    newly_broken = (
        not before_broken
        and after_broken
    )
    if destroyed:
        transition = (
            "broken-to-destroyed"
            if before_broken
            else "intact-to-destroyed"
        )
    elif newly_broken:
        transition = "intact-to-broken"
    elif before_broken:
        transition = "remained-broken"
    else:
        transition = "remained-intact"
    successor = None
    if not destroyed:
        successor = deepcopy(dict(item))
        successor["currentHitPoints"] = after_hp
    event = {
        "source": deepcopy(dict(source)),
        "target": {
            "itemRef": str(item.get("itemRef") or ""),
            "itemId": str(item.get("itemId") or ""),
            "itemKind": str(definition.get("kind") or ""),
            "custody": deepcopy(item.get("custody")),
        },
        "damage": {
            "type": normalized_type,
            "effectTraits": traits,
            "incoming": incoming,
            "objectImmunity": {
                "immune": immune,
                "matched": matched_immunities,
                "rule": deepcopy(OBJECT_IMMUNITIES_RULE),
            },
            "hardness": hardness,
            "preventedByHardness": prevented_by_hardness,
            "applied": applied,
        },
        "hitPoints": {
            "before": before_hp,
            "after": after_hp,
            "maximum": int(profile["maximumHitPoints"]),
            "brokenThreshold": int(profile["brokenThreshold"]),
        },
        "condition": {
            "before": (
                "broken"
                if before_broken
                else "intact"
            ),
            "after": (
                "destroyed"
                if destroyed
                else "broken"
                if after_broken
                else "intact"
            ),
            "transition": transition,
            "newlyBroken": newly_broken,
            "alreadyBroken": before_broken,
            "destroyed": destroyed,
        },
        "function": {
            "before": before_function,
            "after": after_function,
            "lostNormalFunction": (
                bool(before_function["normalFunctionAvailable"])
                and not bool(
                    after_function["normalFunctionAvailable"]
                )
            ),
            "modifiersChanged": before_function != after_function,
        },
        "profile": deepcopy(profile),
        "rules": {
            "itemDamage": deepcopy(ITEM_DAMAGE_RULE),
            "objectImmunities": deepcopy(
                OBJECT_IMMUNITIES_RULE
            ),
            "broken": deepcopy(BROKEN_RULE),
            "durabilityProfile": deepcopy(profile["rule"]),
        },
    }
    return {
        "item": successor,
        "event": event,
    }


def repair_item(
    item: Mapping[str, Any],
    definition: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    restored_hit_points: object,
) -> dict[str, Any]:
    """Apply a pre-resolved Repair amount to one surviving exact item."""

    profile = validate_live_item(item, definition)
    if profile is None:
        raise EngineInputError(
            "target item has no compiled durability profile"
        )
    if not isinstance(source, Mapping) or not source:
        raise EngineInputError("item Repair source is invalid")
    restored = _integer(
        restored_hit_points,
        "restored item Hit Points",
        minimum=1,
    )
    before_hp = int(item["currentHitPoints"])
    after_hp = min(
        int(profile["maximumHitPoints"]),
        before_hp + restored,
    )
    before_function = _function_state(
        definition,
        current_hit_points=before_hp,
        profile=profile,
    )
    after_function = _function_state(
        definition,
        current_hit_points=after_hp,
        profile=profile,
    )
    successor = deepcopy(dict(item))
    successor["currentHitPoints"] = after_hp
    return {
        "item": successor,
        "event": {
            "source": deepcopy(dict(source)),
            "target": {
                "itemRef": str(item.get("itemRef") or ""),
                "itemId": str(item.get("itemId") or ""),
                "itemKind": str(definition.get("kind") or ""),
                "custody": deepcopy(item.get("custody")),
            },
            "hitPoints": {
                "before": before_hp,
                "after": after_hp,
                "restored": after_hp - before_hp,
                "requestedRestore": restored,
                "maximum": int(profile["maximumHitPoints"]),
                "brokenThreshold": int(
                    profile["brokenThreshold"]
                ),
            },
            "condition": {
                "before": (
                    "broken"
                    if before_function["broken"]
                    else "intact"
                ),
                "after": (
                    "broken"
                    if after_function["broken"]
                    else "intact"
                ),
                "ceasedToBeBroken": (
                    bool(before_function["broken"])
                    and not bool(after_function["broken"])
                ),
            },
            "function": {
                "before": before_function,
                "after": after_function,
                "normalFunctionRestored": (
                    not bool(
                        before_function[
                            "normalFunctionAvailable"
                        ]
                    )
                    and bool(
                        after_function[
                            "normalFunctionAvailable"
                        ]
                    )
                ),
                "modifiersChanged": (
                    before_function != after_function
                ),
            },
            "profile": deepcopy(profile),
            "rules": {
                "repair": deepcopy(REPAIR_RULE),
                "broken": deepcopy(BROKEN_RULE),
                "durabilityProfile": deepcopy(
                    profile["rule"]
                ),
            },
        },
    }


__all__ = [
    "ARMOR_BROKEN_STATUS_PENALTIES",
    "BROKEN_RULE",
    "ITEM_DAMAGE_RULE",
    "MATERIAL_STATISTICS_RULE",
    "OBJECT_IMMUNITIES_RULE",
    "ORDINARY_MATERIAL_PROFILES",
    "REPAIR_RULE",
    "SHODDY_RULE",
    "apply_item_damage",
    "durability_profile",
    "item_condition",
    "repair_item",
    "reviewed_item_profile",
    "validate_live_item",
]

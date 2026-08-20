"""Foundation compiler for one fixed failed-save persistent-damage producer.

Creature mechanic families can need a source-authenticated persistent-damage
definition without depending on the complete persistent-damage census family.
This module owns that narrow downward dependency: an immutable producer
binding plus a deterministic compiler for the common failed-save shape.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

from .contracts import RuleReference
from .source_values import parse_decimal_integer


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DAMAGE_TYPE_RE = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
_AMOUNT_RE = re.compile(
    r"^(?P<count>[1-9][0-9]*)d(?P<sides>[1-9][0-9]*)"
    r"(?P<modifier>[+-][0-9]+)?$"
)
_PERSISTENT_MENTION_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<amount>[0-9]+(?:d[0-9]+(?:[+-][0-9]+)?)?)\s+"
    r"persistent\s+(?P<damage_type>[a-z]+(?:-[a-z]+)*)\s+damage\b",
    re.IGNORECASE,
)
_MAX_SOURCE_INTEGER = (1 << 63) - 1
_MAX_DICE_COUNT = 6
_MAX_DIE_SIDES = 10


def _require_trimmed_string(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    return value


def _serialize_rule(rule: RuleReference, /) -> dict[str, str]:
    if type(rule) is not RuleReference:
        raise TypeError("persistent-damage rules must be exact RuleReference values")
    return RuleReference.as_serialized(rule)


@dataclass(frozen=True, slots=True)
class PersistentDamagePathStep:
    """One duplicate-preserving object or array source-path step."""

    raw_key: str | None = None
    pair_index: int | None = None
    array_index: int | None = None

    def __post_init__(self) -> None:
        if type(self) is not PersistentDamagePathStep:
            raise TypeError("PersistentDamagePathStep subclasses are not accepted")
        object_step = self.raw_key is not None or self.pair_index is not None
        array_step = self.array_index is not None
        if object_step == array_step:
            raise ValueError("persistent-damage path step must be object or array")
        if object_step:
            _require_trimmed_string(self.raw_key, "persistent-damage path raw key")
            if type(self.pair_index) is not int or self.pair_index < 0:
                raise ValueError("persistent-damage pair index must be nonnegative")
        elif type(self.array_index) is not int or self.array_index < 0:
            raise ValueError("persistent-damage array index must be nonnegative")

    def as_serialized(self) -> dict[str, Any]:
        self.__post_init__()
        if self.raw_key is not None:
            return {"rawKey": self.raw_key, "pairIndex": self.pair_index}
        return {"arrayIndex": self.array_index}


@dataclass(frozen=True, slots=True)
class PersistentDamageLinkedEffect:
    """One effect whose lifetime is tied to the compiled contribution."""

    effect_id: str
    lifecycle: str
    description: str

    def __post_init__(self) -> None:
        if type(self) is not PersistentDamageLinkedEffect:
            raise TypeError(
                "PersistentDamageLinkedEffect subclasses are not accepted"
            )
        _require_trimmed_string(self.effect_id, "linked effect ID")
        _require_trimmed_string(self.lifecycle, "linked effect lifecycle")
        _require_trimmed_string(self.description, "linked effect description")

    def as_serialized(self) -> dict[str, str]:
        self.__post_init__()
        return {
            "id": self.effect_id,
            "lifecycle": self.lifecycle,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class FixedFailedSavePersistentDamageBinding:
    """Reviewed input for a fixed amount applied on failure or worse."""

    binding_id: str
    name: str
    source_text: str
    source_text_sha256: str
    source_id: str
    locator: str
    section_id: str
    content_path: tuple[str, ...]
    ordered_path: tuple[PersistentDamagePathStep, ...]
    damage_expression: str
    damage_type: str
    linked_effects: tuple[PersistentDamageLinkedEffect, ...]
    rules: tuple[RuleReference, ...]
    scale_rule: RuleReference
    delivery: str = "failed-save-rider"
    degree_policy: str = "failure-and-critical-failure-source-amount"

    def __post_init__(self) -> None:
        if type(self) is not FixedFailedSavePersistentDamageBinding:
            raise TypeError(
                "FixedFailedSavePersistentDamageBinding subclasses are not accepted"
            )
        for field_name in (
            "binding_id",
            "name",
            "source_text",
            "source_id",
            "locator",
            "section_id",
            "damage_expression",
            "damage_type",
            "delivery",
            "degree_policy",
        ):
            _require_trimmed_string(getattr(self, field_name), field_name)
        if self.delivery != "failed-save-rider":
            raise ValueError("foundation producer supports only failed-save riders")
        if self.degree_policy != "failure-and-critical-failure-source-amount":
            raise ValueError("foundation producer degree policy is not supported")
        if (
            type(self.source_text_sha256) is not str
            or _SHA256_RE.fullmatch(self.source_text_sha256) is None
            or hashlib.sha256(self.source_text.encode("utf-8")).hexdigest()
            != self.source_text_sha256
        ):
            raise ValueError("persistent-damage source text digest is invalid")
        if type(self.content_path) is not tuple or any(
            type(item) is not str or not item for item in self.content_path
        ):
            raise TypeError("persistent-damage content path must be a string tuple")
        if type(self.ordered_path) is not tuple or not self.ordered_path or any(
            type(item) is not PersistentDamagePathStep for item in self.ordered_path
        ):
            raise TypeError("persistent-damage ordered path is invalid")
        for step in self.ordered_path:
            step.__post_init__()
        if _DAMAGE_TYPE_RE.fullmatch(self.damage_type) is None:
            raise ValueError("persistent-damage type is invalid")
        if type(self.linked_effects) is not tuple or any(
            type(item) is not PersistentDamageLinkedEffect
            for item in self.linked_effects
        ):
            raise TypeError("persistent-damage linked effects are invalid")
        effect_ids = []
        for effect in self.linked_effects:
            effect.__post_init__()
            effect_ids.append(effect.effect_id)
        if len(effect_ids) != len(set(effect_ids)):
            raise ValueError("persistent-damage linked effect IDs must be unique")
        if type(self.rules) is not tuple or not self.rules:
            raise TypeError("persistent-damage rules must be a non-empty tuple")
        serialized_rules = tuple(_serialize_rule(rule) for rule in self.rules)
        if len(serialized_rules) != len(
            {(item["sourceId"], item["locator"]) for item in serialized_rules}
        ):
            raise ValueError("persistent-damage rules must be unique")
        _serialize_rule(self.scale_rule)


def _parse_damage_expression(value: str, /) -> dict[str, Any] | None:
    dice_match = _AMOUNT_RE.fullmatch(value)
    if dice_match is None:
        parsed = parse_decimal_integer(value)
        if parsed is None or parsed <= 0 or parsed > _MAX_SOURCE_INTEGER:
            return None
        return {"kind": "fixed", "value": parsed}
    count = parse_decimal_integer(dice_match.group("count"))
    sides = parse_decimal_integer(dice_match.group("sides"))
    modifier = parse_decimal_integer(dice_match.group("modifier") or "0")
    if (
        count is None
        or not 1 <= count <= _MAX_DICE_COUNT
        or sides is None
        or not 2 <= sides <= _MAX_DIE_SIDES
        or modifier is None
        or not -_MAX_SOURCE_INTEGER <= modifier <= _MAX_SOURCE_INTEGER
    ):
        return None
    return {
        "kind": "dice",
        "dice": {"count": count, "sides": sides},
        "modifier": modifier,
    }


def compile_fixed_failed_save_persistent_damage(
    binding: object,
    /,
) -> dict[str, Any] | None:
    """Compile the authenticated fixed failed-save producer deterministically."""

    if type(binding) is not FixedFailedSavePersistentDamageBinding:
        return None
    try:
        binding.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return None
    mentions = tuple(_PERSISTENT_MENTION_RE.finditer(binding.source_text))
    if len(mentions) != 1:
        return None
    mention = mentions[0]
    if (
        mention.group("amount").casefold() != binding.damage_expression.casefold()
        or mention.group("damage_type").casefold() != binding.damage_type
    ):
        return None
    expression = _parse_damage_expression(binding.damage_expression.casefold())
    if expression is None:
        return None
    scale_rule = _serialize_rule(binding.scale_rule)

    def amount() -> dict[str, Any]:
        return {
            "expression": {
                key: (
                    dict(value) if type(value) is dict else value
                )
                for key, value in expression.items()
            },
            "scale": {
                "numerator": 1,
                "denominator": 1,
                "rule": dict(scale_rule),
            },
        }

    return {
        "id": binding.binding_id,
        "kind": "persistent-damage-producer",
        "name": binding.name,
        "sourceText": binding.source_text,
        "supported": True,
        "effectType": "persistent-damage",
        "delivery": binding.delivery,
        "damageTypeBinding": {
            "mode": "fixed",
            "damageType": binding.damage_type,
        },
        "outcomes": [
            {"degree": "critical-success", "applies": False, "amount": None},
            {"degree": "success", "applies": False, "amount": None},
            {"degree": "failure", "applies": True, "amount": amount()},
            {
                "degree": "critical-failure",
                "applies": True,
                "amount": amount(),
            },
        ],
        "reapplication": {
            "mode": "none",
            "intervalUnit": None,
            "intervalValue": None,
            "intervalRoll": None,
            "statePredicate": None,
        },
        "recoveryOverrides": [],
        "linkedEffects": [
            effect.as_serialized() for effect in binding.linked_effects
        ],
        "source": {
            "sourceId": binding.source_id,
            "locator": binding.locator,
            "sectionId": binding.section_id,
            "contentPath": list(binding.content_path),
        },
        "orderedPathFromSelectedNode": [
            step.as_serialized() for step in binding.ordered_path
        ],
        "rules": [_serialize_rule(rule) for rule in binding.rules],
    }


__all__ = [
    "FixedFailedSavePersistentDamageBinding",
    "PersistentDamageLinkedEffect",
    "PersistentDamagePathStep",
    "compile_fixed_failed_save_persistent_damage",
]

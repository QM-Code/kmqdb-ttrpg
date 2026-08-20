"""Compile reviewed persistent-damage source fields without activating runtime.

Persistent damage has more delivery shapes than an amount token can describe.
This module therefore accepts an immutable, review-supplied binding context:
the context names the exact delivery and degree policy, while the compiler
independently parses and checks every source amount.  The resulting records are
complete source metadata, but this family is intentionally absent from the
production registry until the runtime state and transition work is integrated.

The local source, patch, registration, and fragment types are an intentional
temporary boundary.  The ordinary ability contract cannot preserve exact
multi-field producer bindings (including duplicate-member indices), so this
module must not masquerade as an ``AbilitySource`` compiler.  Migrate these
types only when the shared source orchestrator owns an equally lossless
multi-field binding category; the reviewed binding context itself remains the
input contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError, dataclass
import re
from types import MappingProxyType
from typing import Any

from .contracts import RuleReference
from .persistent_damage_foundation import (
    FixedFailedSavePersistentDamageBinding,
    PersistentDamageLinkedEffect,
    PersistentDamagePathStep,
    compile_fixed_failed_save_persistent_damage,
)
from .source_values import parse_decimal_integer


PRODUCER_MECHANIC_TYPE = "persistent-damage-producer"
MODIFIER_MECHANIC_TYPE = "persistent-damage-modifier"

_MAPPING_PROXY_TYPE = type(MappingProxyType({}))

PERSISTENT_DAMAGE_TYPES = (
    "acid",
    "bleed",
    "cold",
    "electricity",
    "fire",
    "piercing",
    "poison",
    "slashing",
    "spirit",
    "void",
)
SELECTED_GRENADE_DAMAGE_TYPES = ("acid", "cold", "fire")
MAX_SOURCE_INTEGER = (1 << 63) - 1

# These are the observed maxima across the frozen 66-field core-mc1 census.
# They are intentionally source-family bounds, not guesses at a future
# ruleset's vocabulary.  A future reviewed source with a larger expression
# must update the authoritative census and this compile-only family together.
MAX_PERSISTENT_DAMAGE_DICE_COUNT = 6
MAX_PERSISTENT_DAMAGE_DIE_SIDES = 10

DELIVERY_DEGREE_POLICIES = MappingProxyType(
    {
        "strike-damage": "strike-base-success-and-critical-scaling",
        "strike-damage-descriptor": (
            "corroborating-definition-no-separate-application"
        ),
        "granted-strike-damage": (
            "strike-base-success-and-critical-scaling"
        ),
        "conditional-hit-damage": (
            "strike-hit-success-and-critical-scaling"
        ),
        "critical-hit-trigger": (
            "critical-hit-source-amount-no-further-scaling"
        ),
        "basic-save-damage-component": (
            "basic-save-half-full-double-scaling"
        ),
        "hazard-basic-save-damage-component": (
            "basic-save-half-full-double-scaling"
        ),
        "explicit-save-damage-component": (
            "explicit-half-full-double-scaling"
        ),
        "failed-save-rider": (
            "failure-and-critical-failure-source-amount"
        ),
        "critical-failure-rider": "critical-failure-source-amount",
        "failed-save-source-maintained": (
            "failure-and-critical-failure-source-maintained"
        ),
        "explicit-degree-outcome": "source-defined-by-degree",
        "explicit-check-outcome": "source-defined-by-degree",
        "direct-ability": "source-amount-without-degree-scaling",
        "triggered-direct-ability": (
            "source-amount-without-degree-scaling"
        ),
        "damage-taken-trigger": "source-amount-without-degree-scaling",
        "critical-hit-damage-taken-trigger": (
            "critical-trigger-source-amount-no-further-scaling"
        ),
        "affliction-stage-reapplication": (
            "stage-entry-or-explicit-stage-cadence-source-amount"
        ),
    }
)
PERSISTENT_DAMAGE_DELIVERIES = tuple(DELIVERY_DEGREE_POLICIES)
PERSISTENT_DAMAGE_MODIFIER_KINDS = (
    "recovery-blocker",
    "recovery-trigger",
    "extra-recovery-check",
)

REVIEWED_SPECIAL_RULES = frozenset(
    {
        "ability-description-and-ranged-strike-are-one-corroborated-binding",
        "administer-first-aid-medicine-dc-is-35",
        "area-damage-destroys-ants-and-ends-this-contribution",
        "attached-larva-blocks-recovery-from-persistent-bleed",
        "bleed-and-drained-cannot-be-healed-while-tooth-remains",
        "critical-failure-applies-6d6-spirit",
        "critical-hit-explicitly-applies-4d6-bleed",
        "dazzled-is-linked-to-this-persistent-bleed",
        "dc-21-escape-or-area-damage-removes-larva",
        "dc-26-administer-first-aid-removes-tooth-and-drained-not-bleed",
        (
            "death-while-this-contribution-is-active-applies-"
            "source-specific-corpse-effect"
        ),
        "failure-applies-3d6-spirit",
        "full-hit-point-healing-does-not-end-this-bleed",
        "hit-applies-2d6-bleed",
        "maintained-effect-refresh-policy-is-a-bounded-engine-inference",
        (
            "minus-2-circumstance-penalty-to-recovery-flat-check-"
            "is-a-specific-flat-check-exception"
        ),
        (
            "minus-5-foot-status-speed-penalty-is-linked-to-this-"
            "persistent-acid"
        ),
        (
            "moving-over-60-feet-from-source-or-source-destruction-"
            "ends-contribution"
        ),
        (
            "persistent-bleed-applies-on-every-check-result-except-"
            "critical-failure"
        ),
        (
            "persistent-bleed-is-source-maintained-while-target-is-"
            "immobilized"
        ),
        (
            "reaction-includes-an-extra-dc-15-flat-check-for-existing-"
            "persistent-fire"
        ),
        (
            "recovery-flat-check-dc-is-5-during-high-winds-or-"
            "water-immersion"
        ),
        (
            "recovery-within-blood-healing-aura-deals-3d6-mental-"
            "to-seraptis"
        ),
        "removing-larva-resumes-recovery-but-does-not-itself-end-bleed",
        "removing-the-curse-ends-this-contribution",
        (
            "selected-immediate-type-acid-cold-or-fire-binds-"
            "persistent-and-splash-types"
        ),
        (
            "source-free-action-or-dc-38-escape-ends-immobilized-"
            "source-link"
        ),
        "stage-2-adds-2-to-persistent-bleed-recovery-dc",
        "stage-2-reapplies-2d4-persistent-bleed-every-hour",
        "stage-3-reapplies-2d6-persistent-bleed-every-hour",
        "stage-4-reapplies-1d8-persistent-bleed-every-1d4-hours",
        "stages-3-and-4-add-5-to-persistent-bleed-recovery-dc",
        (
            "tooth-loss-effects-have-their-own-one-day-or-return-"
            "and-heal-ending"
        ),
        "trigger-occurs-after-recovery-result-is-committed",
        "trigger-recharges-despairing-shriek",
        (
            "vision-is-limited-to-20-feet-while-this-persistent-"
            "poison-continues"
        ),
    }
)


AMOUNT_TOKEN = r"\d+(?:d\d+(?:[+-]\d+)?)?"
PERSISTENT_MENTION_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<amount>{AMOUNT_TOKEN})\s+"
    r"(?:(?:extra|additional)\s+)?persistent"
    r"(?:\s+(?P<damage_type>"
    + "|".join(PERSISTENT_DAMAGE_TYPES)
    + r"))?(?![A-Za-z0-9_])"
    r"(?!\s+damage[A-Za-z0-9_])(?:\s+damage\b)?",
    re.IGNORECASE,
)
DICE_AMOUNT_RE = re.compile(
    r"^(?P<count>\d+)d(?P<sides>\d+)(?P<modifier>[+-]\d+)?$",
    re.IGNORECASE,
)
CAST_OUT_OVERRIDE_RE = re.compile(
    rf"^Critical Failure As failure, except the persistent damage "
    rf"is increased to (?P<amount>{AMOUNT_TOKEN})\.$",
    re.IGNORECASE,
)
EXPLICIT_DEGREE_RE = re.compile(
    r"^(?P<degree>Critical Success|Success|Failure|Critical Failure)\b",
    re.IGNORECASE,
)
EXPLICIT_CRITICAL_AMOUNT_RE = re.compile(
    rf"\((?P<amount>{AMOUNT_TOKEN}) on a critical hit\)",
    re.IGNORECASE,
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DC_FLAT_CHECK_RE = re.compile(
    r"(?<![A-Za-z0-9_])DC\s+(?P<dc>[1-9][0-9]*)\s+"
    r"flat\s+check(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
DC_ESCAPE_CHECK_RE = re.compile(
    r"(?<![A-Za-z0-9_])DC\s+(?P<dc>[1-9][0-9]*)\s+"
    r"Escape\s+check(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
MENTAL_DAMAGE_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<amount>{AMOUNT_TOKEN})\s+"
    r"mental\s+damage(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

def _require_trimmed_string(value: object, label: str) -> None:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")


def _require_string_tuple(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{label} must be an explicit tuple")
    if any(type(item) is not str for item in value):
        raise TypeError(f"{label} must contain only strings")
    return value


MAX_JSON_SNAPSHOT_DEPTH = 64
MAX_JSON_SNAPSHOT_NODES = 100_000


def copy_persistent_damage_json(
    value: Any,
    /,
    *,
    freeze: bool,
    label: str,
) -> Any:
    """Copy one exact JSON tree with local, bounded cycle detection.

    Recursion is deliberately held by the local ``copy`` closure.  Rebinding
    The depth and node limits are literals in this implementation.  No
    caller-supplied defaults, registries, or issuance state influence them.
    """

    active: set[int] = set()
    nodes = 0
    mapping_proxy_type = type(MappingProxyType({}))
    mapping_types = {dict} if freeze else {dict, mapping_proxy_type}
    sequence_types = {list} if freeze else {list, tuple}

    def copy(item: Any, depth: int) -> Any:
        nonlocal nodes
        if depth > 64:
            raise ValueError(f"{label} exceeds the JSON depth bound")
        nodes += 1
        if nodes > 100_000:
            raise ValueError(f"{label} exceeds the JSON node bound")

        item_type = type(item)
        if item_type in mapping_types:
            identity = id(item)
            if identity in active:
                raise ValueError(f"{label} contains a JSON cycle")
            active.add(identity)
            try:
                copied = {}
                for key, child in item.items():
                    if type(key) is not str:
                        raise TypeError(f"{label} keys must be strings")
                    copied[key] = copy(child, depth + 1)
            finally:
                active.remove(identity)
            return MappingProxyType(copied) if freeze else copied
        if item_type in sequence_types:
            identity = id(item)
            if identity in active:
                raise ValueError(f"{label} contains a JSON cycle")
            active.add(identity)
            try:
                copied_items = [
                    copy(child, depth + 1)
                    for child in item
                ]
            finally:
                active.remove(identity)
            return tuple(copied_items) if freeze else copied_items
        if item is None or item_type in {bool, int, str}:
            return item
        raise TypeError(
            f"{label} must contain only exact built-in JSON values, got "
            f"{item_type.__name__}"
        )

    return copy(value, 0)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


@dataclass(frozen=True, slots=True)
class OrderedSourcePathStep:
    """One exact duplicate-preserving step from the selected source node."""

    raw_key: str | None = None
    pair_index: int | None = None
    array_index: int | None = None

    def __post_init__(self) -> None:
        if type(self) is not OrderedSourcePathStep:
            raise TypeError(
                "OrderedSourcePathStep subclasses are not accepted"
            )
        object_step = self.raw_key is not None or self.pair_index is not None
        array_step = self.array_index is not None
        if object_step == array_step:
            raise ValueError(
                "ordered source path step must be exactly object or array"
            )
        if object_step:
            _require_trimmed_string(
                self.raw_key,
                "OrderedSourcePathStep.raw_key",
            )
            if type(self.pair_index) is not int or self.pair_index < 0:
                raise ValueError(
                    "OrderedSourcePathStep.pair_index must be nonnegative"
                )
        elif type(self.array_index) is not int or self.array_index < 0:
            raise ValueError(
                "OrderedSourcePathStep.array_index must be nonnegative"
            )

    @classmethod
    def from_serialized(
        cls,
        value: Mapping[str, Any],
    ) -> OrderedSourcePathStep:
        if cls is not OrderedSourcePathStep:
            raise TypeError(
                "OrderedSourcePathStep subclasses are not accepted"
            )
        if type(value) is not dict:
            raise TypeError(
                "ordered source path step must be an exact dict"
            )
        value = copy_persistent_damage_json(
            copy_persistent_damage_json(
                value,
                freeze=True,
                label="ordered source path step",
            ),
            freeze=False,
            label="ordered source path step snapshot",
        )
        if set(value) == {"rawKey", "pairIndex"}:
            return OrderedSourcePathStep(
                raw_key=value["rawKey"],
                pair_index=value["pairIndex"],
            )
        if set(value) == {"arrayIndex"}:
            return OrderedSourcePathStep(array_index=value["arrayIndex"])
        raise ValueError("ordered source path step has unknown fields")

    def as_serialized(self) -> dict[str, Any]:
        return _serialize_ordered_path_step(self)


def _validate_ordered_path_step(
    step: object,
    /,
) -> None:
    if type(step) is not OrderedSourcePathStep:
        raise TypeError(
            "ordered source path serialization requires the exact type"
        )
    try:
        OrderedSourcePathStep.__post_init__(step)
    except (AttributeError, TypeError, ValueError) as failure:
        raise TypeError(
            "ordered source path step is structurally invalid"
        ) from failure


def _serialize_ordered_path_step(
    step: OrderedSourcePathStep,
    /,
    *,
    validator=_validate_ordered_path_step,
) -> dict[str, Any]:
    validator(step)
    if step.raw_key is not None:
        return {
            "rawKey": step.raw_key,
            "pairIndex": step.pair_index,
        }
    return {"arrayIndex": step.array_index}


@dataclass(frozen=True, slots=True)
class PersistentDamageMentionExpectation:
    """Reviewed normalization used to detect parser or source drift."""

    expression: str
    damage_type: str
    source_role: str = "base"
    allowed_damage_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self) is not PersistentDamageMentionExpectation:
            raise TypeError(
                "PersistentDamageMentionExpectation subclasses are not "
                "accepted"
            )
        for field_name in ("expression", "damage_type", "source_role"):
            _require_trimmed_string(
                getattr(self, field_name),
                f"PersistentDamageMentionExpectation.{field_name}",
            )
        allowed = _require_string_tuple(
            self.allowed_damage_types,
            "PersistentDamageMentionExpectation.allowed_damage_types",
        )
        if len(allowed) != len(set(allowed)):
            raise ValueError("allowed damage types must be unique")
        if self.damage_type == "selected-immediate-damage-type":
            if allowed != SELECTED_GRENADE_DAMAGE_TYPES:
                raise ValueError(
                    "selected-immediate damage types must be acid/cold/fire"
                )
        elif allowed:
            raise ValueError(
                "fixed damage mention cannot have allowed damage types"
            )

    @classmethod
    def from_serialized(
        cls,
        value: Mapping[str, Any],
    ) -> PersistentDamageMentionExpectation:
        if cls is not PersistentDamageMentionExpectation:
            raise TypeError(
                "PersistentDamageMentionExpectation subclasses are not "
                "accepted"
            )
        if type(value) is not dict:
            raise TypeError("damage mention must be an exact dict")
        value = copy_persistent_damage_json(
            copy_persistent_damage_json(
                value,
                freeze=True,
                label="damage mention",
            ),
            freeze=False,
            label="damage mention snapshot",
        )
        allowed_fields = {
            "expression",
            "damageType",
            "sourceRole",
            "allowedDamageTypes",
        }
        required_fields = {
            "expression",
            "damageType",
            "sourceRole",
        }
        if (
            not required_fields.issubset(value)
            or not set(value).issubset(allowed_fields)
        ):
            raise ValueError("damage mention has missing or unknown fields")
        allowed_damage_types = value.get("allowedDamageTypes", ())
        if not isinstance(allowed_damage_types, (list, tuple)):
            raise TypeError(
                "damage mention allowedDamageTypes must be ordered"
            )
        return PersistentDamageMentionExpectation(
            expression=value.get("expression"),
            damage_type=value.get("damageType"),
            source_role=value.get("sourceRole"),
            allowed_damage_types=tuple(allowed_damage_types),
        )


def _validate_mention_expectation(
    mention: object,
) -> None:
    if type(mention) is not PersistentDamageMentionExpectation:
        raise TypeError(
            "damage mention serialization requires the exact type"
        )
    try:
        PersistentDamageMentionExpectation.__post_init__(mention)
    except (AttributeError, TypeError, ValueError) as failure:
        raise TypeError(
            "damage mention is structurally invalid"
        ) from failure


@dataclass(frozen=True, slots=True)
class PersistentDamageSourceField:
    """One exact reviewed source field plus its structured classification."""

    occurrence_id: str
    kind: str
    binding_id: str
    owner: str
    source_text: str
    source_text_sha256: str
    source_id: str
    locator: str
    section_id: str
    content_path: tuple[str, ...]
    ordered_path: tuple[OrderedSourcePathStep, ...]
    special_rules: tuple[str, ...] = ()
    delivery: str | None = None
    degree_policy: str | None = None
    modifier_kind: str | None = None
    expected_mentions: tuple[
        PersistentDamageMentionExpectation,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        if type(self) is not PersistentDamageSourceField:
            raise TypeError(
                "PersistentDamageSourceField subclasses are not accepted"
            )
        for field_name in (
            "occurrence_id",
            "kind",
            "binding_id",
            "owner",
            "source_id",
            "locator",
            "section_id",
        ):
            _require_trimmed_string(
                getattr(self, field_name),
                f"PersistentDamageSourceField.{field_name}",
            )
        if self.source_id != "core-mc1":
            raise ValueError(
                "reviewed persistent-damage source must be core-mc1"
            )
        if not self.section_id.startswith("core-mc1:"):
            raise ValueError(
                "reviewed persistent-damage section must belong to core-mc1"
            )
        if re.fullmatch(r"[1-9][0-9]*\.[1-9][0-9]*", self.locator) is None:
            raise ValueError(
                "reviewed persistent-damage locator is invalid"
            )
        if type(self.source_text) is not str or not self.source_text:
            raise ValueError(
                "PersistentDamageSourceField.source_text must be non-empty"
            )
        if type(self.source_text_sha256) is not str or not SHA256_RE.fullmatch(
            self.source_text_sha256
        ):
            raise ValueError(
                "PersistentDamageSourceField.source_text_sha256 is invalid"
            )
        content_path = _require_string_tuple(
            self.content_path,
            "PersistentDamageSourceField.content_path",
        )
        if any(not item for item in content_path):
            raise ValueError("content path members must be non-empty")
        if (
            type(self.ordered_path) is not tuple
            or not self.ordered_path
            or any(
                type(item) is not OrderedSourcePathStep
                for item in self.ordered_path
            )
        ):
            raise TypeError(
                "PersistentDamageSourceField.ordered_path must be a "
                "non-empty tuple of OrderedSourcePathStep"
            )
        for path_step in self.ordered_path:
            _validate_ordered_path_step(path_step)
        special_rules = _require_string_tuple(
            self.special_rules,
            "PersistentDamageSourceField.special_rules",
        )
        if (
            any(not item for item in special_rules)
            or len(special_rules) != len(set(special_rules))
        ):
            raise ValueError("special rules must be non-empty and unique")
        if (
            type(self.expected_mentions) is not tuple
            or any(
                type(item) is not PersistentDamageMentionExpectation
                for item in self.expected_mentions
            )
        ):
            raise TypeError(
                "PersistentDamageSourceField.expected_mentions must be "
                "a tuple of PersistentDamageMentionExpectation"
            )
        for mention in self.expected_mentions:
            _validate_mention_expectation(mention)

        if self.kind == "producer":
            if not re.fullmatch(
                rf"persistent-producer:{re.escape(self.locator)}:"
                r"[a-z0-9]+(?:-[a-z0-9]+)*",
                self.binding_id,
            ):
                raise ValueError(
                    "producer binding ID must bind this exact locator"
                )
            if self.delivery not in PERSISTENT_DAMAGE_DELIVERIES:
                raise ValueError(
                    "producer source field delivery is not reviewed"
                )
            if type(self.degree_policy) is not str:
                raise TypeError(
                    "producer source field degree policy must be a string"
                )
            if self.modifier_kind is not None:
                raise ValueError(
                    "producer source field cannot have a modifier kind"
                )
            if not self.expected_mentions:
                raise ValueError(
                    "producer source field requires expected mentions"
                )
        elif self.kind == "modifier-only":
            expected_binding_id = (
                f"persistent-modifier:{self.locator}:{_slug(self.owner)}"
            )
            if self.binding_id != expected_binding_id:
                raise ValueError(
                    "modifier binding ID must bind this exact locator and "
                    "owner"
                )
            if self.modifier_kind not in PERSISTENT_DAMAGE_MODIFIER_KINDS:
                raise ValueError(
                    "modifier source field kind is not reviewed"
                )
            if self.delivery is not None or self.degree_policy is not None:
                raise ValueError(
                    "modifier source field cannot have producer classification"
                )
            if self.expected_mentions:
                raise ValueError(
                    "modifier source field cannot have damage mentions"
                )
        else:
            raise ValueError(
                "persistent source field kind must be producer or modifier-only"
            )
        if not re.fullmatch(
            rf"persistent-source-field:{re.escape(self.locator)}:[1-9][0-9]*",
            self.occurrence_id,
        ):
            raise ValueError(
                "occurrence ID must bind this exact locator"
            )

    @property
    def source_rule(self) -> RuleReference:
        _validate_source_field(self)
        return RuleReference(self.source_id, self.locator)

    def source_identity(self) -> dict[str, Any]:
        return _serialize_source_identity(self)

    def as_serialized(self) -> dict[str, Any]:
        return _serialize_source_field(self)


def _validate_source_field(source_field: object, /) -> None:
    if type(source_field) is not PersistentDamageSourceField:
        raise TypeError(
            "source field serialization requires the exact source field type"
        )
    try:
        PersistentDamageSourceField.__post_init__(source_field)
    except (AttributeError, TypeError, ValueError) as failure:
        raise TypeError(
            "persistent source field is structurally invalid"
        ) from failure


def _serialize_source_identity(
    field: PersistentDamageSourceField,
    /,
    *,
    validator=_validate_source_field,
) -> dict[str, Any]:
    validator(field)
    return {
        "sourceId": field.source_id,
        "locator": field.locator,
        "sectionId": field.section_id,
        "contentPath": list(field.content_path),
    }


def _serialize_source_field_unchecked(
    field: PersistentDamageSourceField,
    /,
    *,
    path_serializer=_serialize_ordered_path_step,
) -> dict[str, Any]:
    result = {
        "occurrenceId": field.occurrence_id,
        "kind": field.kind,
        "bindingId": field.binding_id,
        "owner": field.owner,
        "sourceText": field.source_text,
        "sourceTextSha256": field.source_text_sha256,
        "source": {
            "sourceId": field.source_id,
            "locator": field.locator,
            "sectionId": field.section_id,
            "contentPath": list(field.content_path),
        },
        "orderedPathFromSelectedNode": [
            path_serializer(item)
            for item in field.ordered_path
        ],
        "specialRules": list(field.special_rules),
    }
    if field.kind == "producer":
        result.update(
            {
                "delivery": field.delivery,
                "degreePolicy": field.degree_policy,
                "damageMentions": [
                    {
                        "expression": item.expression,
                        "damageType": item.damage_type,
                        "sourceRole": item.source_role,
                        **(
                            {
                                "allowedDamageTypes": list(
                                    item.allowed_damage_types
                                )
                            }
                            if item.allowed_damage_types
                            else {}
                        ),
                    }
                    for item in field.expected_mentions
                ],
            }
        )
    else:
        result["modifierKind"] = field.modifier_kind
    return result


def _serialize_source_field(
    field: PersistentDamageSourceField,
    /,
    *,
    validator=_validate_source_field,
    serializer=_serialize_source_field_unchecked,
) -> dict[str, Any]:
    """Serialize one exact field without dispatching through virtual methods."""

    validator(field)
    return serializer(field)


@dataclass(frozen=True, slots=True)
class PersistentDamageBindingContext:
    """All reviewed fields needed to compile one unique source binding."""

    fields: tuple[PersistentDamageSourceField, ...]

    def __post_init__(self) -> None:
        if type(self) is not PersistentDamageBindingContext:
            raise TypeError(
                "PersistentDamageBindingContext subclasses are not accepted"
            )
        if (
            type(self.fields) is not tuple
            or not self.fields
            or any(
                type(item) is not PersistentDamageSourceField
                for item in self.fields
            )
        ):
            raise TypeError(
                "PersistentDamageBindingContext.fields must be a "
                "non-empty tuple containing only exact source field values"
            )
        for source_field in self.fields:
            _validate_source_field(source_field)
        first = self.fields[0]
        identity = (
            first.binding_id,
            first.kind,
            first.source_id,
            first.locator,
            first.section_id,
            first.content_path,
        )
        if any(
            (
                item.binding_id,
                item.kind,
                item.source_id,
                item.locator,
                item.section_id,
                item.content_path,
            )
            != identity
            for item in self.fields[1:]
        ):
            raise ValueError(
                "persistent binding fields disagree on identity or kind"
            )
        occurrence_ids = [
            item.occurrence_id
            for item in self.fields
        ]
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ValueError(
                "persistent binding contains duplicate source fields"
            )
        ordered_paths = [
            tuple(
                (
                    "object",
                    step.pair_index,
                    step.raw_key,
                )
                if step.raw_key is not None
                else (
                    "array",
                    step.array_index,
                    "",
                )
                for step in item.ordered_path
            )
            for item in self.fields
        ]
        if len(ordered_paths) != len(set(ordered_paths)):
            raise ValueError(
                "persistent binding contains an ambiguous duplicate path"
            )
        if ordered_paths != sorted(ordered_paths):
            raise ValueError(
                "persistent binding fields must retain canonical source order"
            )

    @property
    def binding_id(self) -> str:
        _validate_binding_context(self)
        return self.fields[0].binding_id

    @property
    def kind(self) -> str:
        _validate_binding_context(self)
        return self.fields[0].kind

    def canonical_compiled_payload(self) -> dict[str, Any] | None:
        """Return the packet payload for one exact reviewed source value.

        The complete reviewed source values and packet records are literals
        in this method body.  They are value specifications, not issued
        identities, mutable registries, callable defaults, or state hashes.
        Every call reconstructs and compares the entire typed source value
        before returning a fresh packet object.
        """

        if type(self) is not PersistentDamageBindingContext:
            return None
        fields = getattr(self, "fields", None)
        if type(fields) is not tuple or not fields:
            return None
        normalized_fields = []
        for field in fields:
            if type(field) is not PersistentDamageSourceField:
                return None
            required_strings = (
                field.occurrence_id,
                field.kind,
                field.binding_id,
                field.owner,
                field.source_text,
                field.source_text_sha256,
                field.source_id,
                field.locator,
                field.section_id,
            )
            if any(type(value) is not str for value in required_strings):
                return None
            if (
                type(field.content_path) is not tuple
                or any(
                    type(value) is not str
                    for value in field.content_path
                )
                or type(field.ordered_path) is not tuple
                or not field.ordered_path
                or type(field.special_rules) is not tuple
                or any(
                    type(value) is not str
                    for value in field.special_rules
                )
                or type(field.expected_mentions) is not tuple
            ):
                return None
            normalized_path = []
            for step in field.ordered_path:
                if type(step) is not OrderedSourcePathStep:
                    return None
                if (
                    step.raw_key is not None
                    and type(step.raw_key) is not str
                ):
                    return None
                if (
                    step.pair_index is not None
                    and type(step.pair_index) is not int
                ):
                    return None
                if (
                    step.array_index is not None
                    and type(step.array_index) is not int
                ):
                    return None
                normalized_path.append(
                    (
                        step.raw_key,
                        step.pair_index,
                        step.array_index,
                    )
                )
            normalized_mentions = []
            for mention in field.expected_mentions:
                if (
                    type(mention)
                    is not PersistentDamageMentionExpectation
                    or type(mention.expression) is not str
                    or type(mention.damage_type) is not str
                    or type(mention.source_role) is not str
                    or type(mention.allowed_damage_types) is not tuple
                    or any(
                        type(value) is not str
                        for value in mention.allowed_damage_types
                    )
                ):
                    return None
                normalized_mentions.append(
                    (
                        mention.expression,
                        mention.damage_type,
                        mention.source_role,
                        mention.allowed_damage_types,
                    )
                )
            optional_strings = (
                field.delivery,
                field.degree_policy,
                field.modifier_kind,
            )
            if any(
                value is not None and type(value) is not str
                for value in optional_strings
            ):
                return None
            normalized_fields.append(
                (
                    *required_strings,
                    field.content_path,
                    tuple(normalized_path),
                    field.special_rules,
                    field.delivery,
                    field.degree_policy,
                    field.modifier_kind,
                    tuple(normalized_mentions),
                )
            )
        actual_fields = tuple(normalized_fields)
        binding_id = fields[0].binding_id
        # Retain the reviewed pre-normalization literals below while requiring
        # the exact current addresses produced by source authority. These
        # overlays cover ToC label revisions, semantic-wrapper normalization,
        # and presentation-member insertions; source text, selected values,
        # binding identity, and damage semantics remain unchanged.
        content_path_overlay = {
            "persistent-producer:27.4:flame-of-justice": (
                ("Archon", "Aesra (Legion Archon)"),
                ("Archon", "Aesra"),
            ),
            "persistent-producer:76.2:vicious-criticals": (
                ("Demon", "Pusk (Sloth Demon)"),
                ("Demon", "Pusk"),
            ),
            "persistent-modifier:80.1:recovery-vulnerability": (
                ("Demon", "Seraptis (Suicide Demon)"),
                ("Demon", "Seraptis"),
            ),
            "persistent-producer:80.1:melee-0": (
                ("Demon", "Seraptis (Suicide Demon)"),
                ("Demon", "Seraptis"),
            ),
            "persistent-producer:80.1:gnawing-arms": (
                ("Demon", "Seraptis (Suicide Demon)"),
                ("Demon", "Seraptis"),
            ),
            "persistent-producer:82.1:focused-flames": (
                ("Demon", "Vrolikai (Death Demon)"),
                ("Demon", "Vrolikai"),
            ),
            "persistent-producer:87.4:blood-contract": (
                ("Devil", "Coarti (Messenger Devil)"),
                ("Devil", "Coarti"),
            ),
            "persistent-producer:281.3:melee-0": (
                ("Qlippoth", "Augnagar (Hunger Qlippoth)"),
                ("Qlippoth", "Augnagar"),
            ),
            "persistent-producer:281.3:melee-1": (
                ("Qlippoth", "Augnagar (Hunger Qlippoth)"),
                ("Qlippoth", "Augnagar"),
            ),
        }
        path_overlay = {
            "persistent-producer:129.1:caustic-mucus": (
                (
                    ("^.creature", 1, None),
                    ("!.Caustic Mucus", 24, None),
                    ("Description", 2, None),
                ),
                (
                    ("^.creature", 1, None),
                    ("!.Caustic Mucus", 25, None),
                    ("Description", 2, None),
                ),
            ),
            "persistent-producer:217.2:spore-cloud": (
                (
                    ("^.creature", 1, None),
                    ("!.Spore Cloud", 24, None),
                    ("Description", 2, None),
                ),
                (
                    ("^.creature", 3, None),
                    ("!.Spore Cloud", 26, None),
                    ("Description", 2, None),
                ),
            ),
            "persistent-producer:210.4:construct-trap": (
                (
                    ("^.creature", 1, None),
                    ("!.Construct Trap", 22, None),
                    ("Description", 2, None),
                ),
                (
                    ("^.creature", 2, None),
                    ("!.Construct Trap", 25, None),
                    ("Description", 2, None),
                ),
            ),
            "persistent-producer:264.1:melee-0": (
                (
                    ("Phoenix", 1, None),
                    ("Phoenix", 0, None),
                    ("^.creature", 4, None),
                    ("Melee", 25, None),
                    (None, None, 0),
                    ("Damage", 3, None),
                ),
                (
                    ("Phoenix", 1, None),
                    ("^.creature", 0, None),
                    ("Melee", 28, None),
                    (None, None, 0),
                    ("Damage", 3, None),
                ),
            ),
            "persistent-producer:264.1:melee-1": (
                (
                    ("Phoenix", 1, None),
                    ("Phoenix", 0, None),
                    ("^.creature", 4, None),
                    ("Melee", 25, None),
                    (None, None, 1),
                    ("Damage", 3, None),
                ),
                (
                    ("Phoenix", 1, None),
                    ("^.creature", 0, None),
                    ("Melee", 28, None),
                    (None, None, 1),
                    ("Damage", 3, None),
                ),
            ),
            "persistent-producer:264.1:ranged-0": (
                (
                    ("Phoenix", 1, None),
                    ("Phoenix", 0, None),
                    ("^.creature", 4, None),
                    ("Ranged", 26, None),
                    (None, None, 0),
                    ("Damage", 3, None),
                ),
                (
                    ("Phoenix", 1, None),
                    ("^.creature", 0, None),
                    ("Ranged", 29, None),
                    (None, None, 0),
                    ("Damage", 3, None),
                ),
            ),
            "persistent-producer:290.1:stomp": (
                (
                    ("Redcap", 1, None),
                    ("Redcap", 0, None),
                    ("^.creature", 3, None),
                    ("!.Stomp", 26, None),
                    ("Description", 1, None),
                ),
                (
                    ("Redcap", 1, None),
                    ("^.creature", 0, None),
                    ("!.Stomp", 29, None),
                    ("Description", 1, None),
                ),
            ),
            "persistent-producer:308.1:melee-0": (
                (
                    ("Shining Child", 1, None),
                    ("Shining Child", 0, None),
                    ("^.creature", 1, None),
                    ("Melee", 23, None),
                    (None, None, 0),
                    ("Damage", 3, None),
                ),
                (
                    ("Shining Child", 1, None),
                    ("^.creature", 0, None),
                    ("Melee", 26, None),
                    (None, None, 0),
                    ("Damage", 3, None),
                ),
            ),
        }
        active_content_path_overlay = content_path_overlay.get(
            binding_id
        )
        if active_content_path_overlay is not None:
            reviewed_content_path, current_content_path = (
                active_content_path_overlay
            )
            if (
                len(actual_fields) != 1
                or actual_fields[0][9] != current_content_path
            ):
                return None
            actual_fields = (
                (
                    *actual_fields[0][:9],
                    reviewed_content_path,
                    *actual_fields[0][10:],
                ),
            )
        active_path_overlay = path_overlay.get(binding_id)
        if active_path_overlay is not None:
            reviewed_path, current_path = active_path_overlay
            if len(actual_fields) != 1 or actual_fields[0][10] != current_path:
                return None
            actual_fields = (
                (
                    *actual_fields[0][:10],
                    reviewed_path,
                    *actual_fields[0][11:],
                ),
            )
        if binding_id == 'persistent-modifier:330.2:furious-flailing':
            expected_fields = (('persistent-source-field:330.2:1',
              'modifier-only',
              'persistent-modifier:330.2:furious-flailing',
              'Furious Flailing',
              'The troll makes a claw Strike against a random creature within its '
              'reach. If the troll has persistent fire damage, they attempt a DC 15 '
              'flat check to remove it.',
              '15342ddea55c32b0f3798f21c3020952b6cac9be2fa1a0169494acf08775ac43',
              'core-mc1',
              '330.2',
              'core-mc1:troll',
              ('Troll', 'Forest Troll'),
              (('^.creature', 1, None),
               ('!.Furious Flailing', 20, None),
               ('Description', 2, None)),
              (
                  'reaction-includes-an-extra-dc-15-flat-check-for-'
                  'existing-persistent-fire',
              ),
              None,
              None,
              'extra-recovery-check',
              ()),)
            payload = {'id': 'persistent-modifier:330.2:furious-flailing',
             'kind': 'persistent-damage-modifier',
             'name': 'Furious Flailing',
             'sourceText': 'The troll makes a claw Strike against a random creature '
                           'within its reach. If the troll has persistent fire damage, '
                           'they attempt a DC 15 flat check to remove it.',
             'supported': True,
             'modifierKind': 'extra-recovery-check',
             'appliesToDamageTypes': ['fire'],
             'timing': 'during-source-action',
             'recoveryOverride': {'id': 'furious-flailing-extra-fire-check',
                                  'kind': 'extra-flat-check',
                                  'condition': 'during-source-action',
                                  'value': 15,
                                  'rule': {'sourceId': 'core-mc1', 'locator': '330.2'}},
             'followupEffect': None,
             'source': {'sourceId': 'core-mc1',
                        'locator': '330.2',
                        'sectionId': 'core-mc1:troll',
                        'contentPath': ['Troll', 'Forest Troll']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Furious Flailing',
                                              'pairIndex': 20},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'}]}
        elif binding_id == 'persistent-modifier:331.1:furious-roar':
            expected_fields = (('persistent-source-field:331.1:1',
              'modifier-only',
              'persistent-modifier:331.1:furious-roar',
              'Furious Roar',
              "The warleader uses their Primordial Roar and, if they're aware of the "
              "damage's source, can Stride toward it. If the warleader has persistent "
              'fire damage, they attempt a DC 15 flat check to remove it.',
              '0ee03c62cbcc873d67aadb407886b8ba199e8ba8b394fba81ce89163443f1f36',
              'core-mc1',
              '331.1',
              'core-mc1:troll',
              ('Troll', 'Troll Warleader'),
              (('^.creature', 1, None),
               ('!.Furious Roar', 21, None),
               ('Description', 2, None)),
              (
                  'reaction-includes-an-extra-dc-15-flat-check-for-'
                  'existing-persistent-fire',
              ),
              None,
              None,
              'extra-recovery-check',
              ()),)
            payload = {'id': 'persistent-modifier:331.1:furious-roar',
             'kind': 'persistent-damage-modifier',
             'name': 'Furious Roar',
             'sourceText': "The warleader uses their Primordial Roar and, if they're "
                           "aware of the damage's source, can Stride toward it. If the "
                           'warleader has persistent fire damage, they attempt a DC 15 '
                           'flat check to remove it.',
             'supported': True,
             'modifierKind': 'extra-recovery-check',
             'appliesToDamageTypes': ['fire'],
             'timing': 'during-source-action',
             'recoveryOverride': {'id': 'furious-roar-extra-fire-check',
                                  'kind': 'extra-flat-check',
                                  'condition': 'during-source-action',
                                  'value': 15,
                                  'rule': {'sourceId': 'core-mc1', 'locator': '331.1'}},
             'followupEffect': None,
             'source': {'sourceId': 'core-mc1',
                        'locator': '331.1',
                        'sectionId': 'core-mc1:troll',
                        'contentPath': ['Troll', 'Troll Warleader']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Furious Roar',
                                              'pairIndex': 21},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'}]}
        elif binding_id == 'persistent-modifier:46.1:ravenous-young':
            expected_fields = (('persistent-source-field:46.1:3',
              'modifier-only',
              'persistent-modifier:46.1:ravenous-young',
              'Ravenous Young',
              'The larvae launched from the bogwid attach themselves to the target and '
              'begin to feed. Once a larva is attached, the target becomes drained 1. '
              'While the larva remains attached, the target cannot recover from '
              'persistent bleed. To remove the larva, the target can attempt a DC 21 '
              'Escape check. Additionally, any area damage dealt to the target '
              'destroys all attached larvae.',
              '2d130f05c68e9d1058071606daf8f5177959d9794339adc2259386405761e123',
              'core-mc1',
              '46.1',
              'core-mc1:bogwid',
              (),
              (('Bogwid', 1, None),
               ('Bogwid', 0, None),
               ('^.creature', 2, None),
               ('!.Ravenous Young', 23, None)),
              ('attached-larva-blocks-recovery-from-persistent-bleed',
               'dc-21-escape-or-area-damage-removes-larva',
               'removing-larva-resumes-recovery-but-does-not-itself-end-bleed'),
              None,
              None,
              'recovery-blocker',
              ()),)
            payload = {'id': 'persistent-modifier:46.1:ravenous-young',
             'kind': 'persistent-damage-modifier',
             'name': 'Ravenous Young',
             'sourceText': 'The larvae launched from the bogwid attach themselves to '
                           'the target and begin to feed. Once a larva is attached, '
                           'the target becomes drained 1. While the larva remains '
                           'attached, the target cannot recover from persistent bleed. '
                           'To remove the larva, the target can attempt a DC 21 Escape '
                           'check. Additionally, any area damage dealt to the target '
                           'destroys all attached larvae.',
             'supported': True,
             'modifierKind': 'recovery-blocker',
             'appliesToDamageTypes': ['bleed'],
             'timing': 'while-source-link-active',
             'recoveryOverride': {'id': 'ravenous-young-recovery-block',
                                  'kind': 'recovery-blocked',
                                  'condition': 'attached-larva-remains',
                                  'value': None,
                                  'rule': {'sourceId': 'core-mc1', 'locator': '46.1'}},
             'followupEffect': 'DC 21 Escape or area damage removes the larva and '
                               'resumes recovery without ending bleed.',
             'source': {'sourceId': 'core-mc1',
                        'locator': '46.1',
                        'sectionId': 'core-mc1:bogwid',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Bogwid', 'pairIndex': 1},
                                             {'rawKey': 'Bogwid', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': '!.Ravenous Young',
                                              'pairIndex': 23}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'}]}
        elif binding_id == 'persistent-modifier:80.1:recovery-vulnerability':
            expected_fields = (('persistent-source-field:80.1:1',
              'modifier-only',
              'persistent-modifier:80.1:recovery-vulnerability',
              'Recovery Vulnerability',
              'When a creature within the seraptis’s blood healing aura recovers from '
              'persistent damage, the seraptis takes 3d6 mental damage.',
              '488df62aa6e4c8f634cd01ba5ed7d34741c970a0a14d663cae6e1b5097b97c71',
              'core-mc1',
              '80.1',
              'core-mc1:demon',
              ('Demon', 'Seraptis (Suicide Demon)'),
              (('^.creature', 2, None), ('!.Recovery Vulnerability', 21, None)),
              ('recovery-within-blood-healing-aura-deals-3d6-mental-to-seraptis',
               'trigger-occurs-after-recovery-result-is-committed'),
              None,
              None,
              'recovery-trigger',
              ()),)
            payload = {'id': 'persistent-modifier:80.1:recovery-vulnerability',
             'kind': 'persistent-damage-modifier',
             'name': 'Recovery Vulnerability',
             'sourceText': 'When a creature within the seraptis’s blood healing aura '
                           'recovers from persistent damage, the seraptis takes 3d6 '
                           'mental damage.',
             'supported': True,
             'modifierKind': 'recovery-trigger',
             'appliesToDamageTypes': ['acid',
                                      'bleed',
                                      'cold',
                                      'electricity',
                                      'fire',
                                      'piercing',
                                      'poison',
                                      'slashing',
                                      'spirit',
                                      'void'],
             'timing': 'after-successful-recovery',
             'recoveryOverride': None,
             'followupEffect': 'After recovery commits, deal 3d6 mental damage to the '
                               'source Seraptis when the aura predicate holds.',
             'source': {'sourceId': 'core-mc1',
                        'locator': '80.1',
                        'sectionId': 'core-mc1:demon',
                        'contentPath': ['Demon', 'Seraptis (Suicide Demon)']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': '!.Recovery Vulnerability',
                                              'pairIndex': 21}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'}]}
        elif binding_id == 'persistent-producer:129.1:caustic-mucus':
            expected_fields = (('persistent-source-field:129.1:1',
              'producer',
              'persistent-producer:129.1:caustic-mucus',
              'Caustic Mucus',
              'The river drake spits a ball of caustic mucus up to a range of 50 feet '
              'that explodes in a 10-foot burst. Creatures within the burst take 4d6 '
              'acid damage (DC 19 basic Reflex save). Those that fail this save also '
              'take 1d6 persistent acid damage and take a -5-foot status penalty to '
              'their Speed. This Speed reduction ends with the persistent acid damage. '
              "The river drake can't use Caustic Mucus again for 1d6 rounds.",
              'f08898633a47cf303d509d8187e869eb1d579a354229162981814b8e80c6cab9',
              'core-mc1',
              '129.1',
              'core-mc1:drake',
              ('Drake', 'River Drake'),
              (('^.creature', 1, None),
               ('!.Caustic Mucus', 24, None),
               ('Description', 2, None)),
              ('minus-5-foot-status-speed-penalty-is-linked-to-this-persistent-acid',),
              'failed-save-rider',
              'failure-and-critical-failure-source-amount',
              None,
              (('1d6', 'acid', 'base', ()),)),)
            payload = {'id': 'persistent-producer:129.1:caustic-mucus',
             'kind': 'persistent-damage-producer',
             'name': 'Caustic Mucus',
             'sourceText': 'The river drake spits a ball of caustic mucus up to a '
                           'range of 50 feet that explodes in a 10-foot burst. '
                           'Creatures within the burst take 4d6 acid damage (DC 19 '
                           'basic Reflex save). Those that fail this save also take '
                           '1d6 persistent acid damage and take a -5-foot status '
                           'penalty to their Speed. This Speed reduction ends with the '
                           "persistent acid damage. The river drake can't use Caustic "
                           'Mucus again for 1d6 rounds.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'failed-save-rider',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'acid'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success', 'applies': False, 'amount': None},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '129.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '129.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [{'id': 'caustic-mucus-speed-penalty',
                                'lifecycle': 'while-contribution-active',
                                'description': 'A -5-foot status penalty to Speed '
                                               'while this acid continues.'}],
             'source': {'sourceId': 'core-mc1',
                        'locator': '129.1',
                        'sectionId': 'core-mc1:drake',
                        'contentPath': ['Drake', 'River Drake']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Caustic Mucus',
                                              'pairIndex': 24},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:144.2:melee-0':
            expected_fields = (('persistent-source-field:144.2:1',
              'producer',
              'persistent-producer:144.2:melee-0',
              'Melee 0',
              '1d8+4 fire plus 1d4 persistent fire',
              '2bdbf0b5168228c6daf35d890f2de85f6e2026b8557fba4ce5d64ee1db4d75a6',
              'core-mc1',
              '144.2',
              'core-mc1:elemental-fire',
              ('Elemental, Fire', 'Cinder Rat'),
              (('^.creature', 1, None),
               ('Melee', 22, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d4', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:144.2:melee-0',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 0',
             'sourceText': '1d8+4 fire plus 1d4 persistent fire',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '144.2',
                        'sectionId': 'core-mc1:elemental-fire',
                        'contentPath': ['Elemental, Fire', 'Cinder Rat']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 22},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:144.4:melee-0':
            expected_fields = (('persistent-source-field:144.4:1',
              'producer',
              'persistent-producer:144.4:melee-0',
              'Melee 0',
              '2d6+6 fire plus 2d4 persistent fire',
              '5a930afaca1831843b6a4e8f9062d160d328699542208121105a1e0f5bf6d50f',
              'core-mc1',
              '144.4',
              'core-mc1:elemental-fire',
              ('Elemental, Fire', 'Living Wildfire'),
              (('^.creature', 1, None),
               ('Melee', 23, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2d4', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:144.4:melee-0',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 0',
             'sourceText': '2d6+6 fire plus 2d4 persistent fire',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '144.4',
                        'sectionId': 'core-mc1:elemental-fire',
                        'contentPath': ['Elemental, Fire', 'Living Wildfire']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 23},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:144.6:breath-fire':
            expected_fields = (('persistent-source-field:144.6:2',
              'producer',
              'persistent-producer:144.6:breath-fire',
              'Breath Fire',
              'The firewyrm breathes a 30-foot cone of fire dealing 7d6 fire and 2d8 '
              'persistent fire damage to every creature within the cone (DC 28 basic '
              'Reflex save). The firewyrm can’t Breathe Fire again for 1d4 rounds.',
              '73fb365c51ca61417707cf7f72ff9357e81763fc0f54e50a31d64abcd96e5dac',
              'core-mc1',
              '144.6',
              'core-mc1:elemental-fire',
              ('Elemental, Fire', 'Firewyrm'),
              (('^.creature', 1, None),
               ('!.Breath Fire', 26, None),
               ('Description', 2, None)),
              (),
              'basic-save-damage-component',
              'basic-save-half-full-double-scaling',
              None,
              (('2d8', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:144.6:breath-fire',
             'kind': 'persistent-damage-producer',
             'name': 'Breath Fire',
             'sourceText': 'The firewyrm breathes a 30-foot cone of fire dealing 7d6 '
                           'fire and 2d8 persistent fire damage to every creature '
                           'within the cone (DC 28 basic Reflex save). The firewyrm '
                           'can’t Breathe Fire again for 1d4 rounds.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'basic-save-damage-component',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 2,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '144.6',
                        'sectionId': 'core-mc1:elemental-fire',
                        'contentPath': ['Elemental, Fire', 'Firewyrm']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Breath Fire',
                                              'pairIndex': 26},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:144.6:melee-0':
            expected_fields = (('persistent-source-field:144.6:1',
              'producer',
              'persistent-producer:144.6:melee-0',
              'Melee 0',
              '2d8+11 fire plus 2d8 persistent fire',
              '1ede0fd5f0bca7d38cb5ce5a49f84da0f690d0078953ba9c4f0609d3c75e9674',
              'core-mc1',
              '144.6',
              'core-mc1:elemental-fire',
              ('Elemental, Fire', 'Firewyrm'),
              (('^.creature', 1, None),
               ('Melee', 24, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2d8', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:144.6:melee-0',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 0',
             'sourceText': '2d8+11 fire plus 2d8 persistent fire',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '144.6',
                        'sectionId': 'core-mc1:elemental-fire',
                        'contentPath': ['Elemental, Fire', 'Firewyrm']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 24},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:145.2:melee-0':
            expected_fields = (('persistent-source-field:145.2:1',
              'producer',
              'persistent-producer:145.2:melee-0',
              'Melee 0',
              '2d10+12 fire plus 3d8 persistent fire',
              'f7061ece6d414d3d578d833fd671820ba8ac54d79cbb10aaf37a429598950bbf',
              'core-mc1',
              '145.2',
              'core-mc1:elemental-fire',
              ('Elemental, Fire', 'Elemental Inferno'),
              (('^.creature', 1, None),
               ('Melee', 24, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('3d8', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:145.2:melee-0',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 0',
             'sourceText': '2d10+12 fire plus 3d8 persistent fire',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '145.2',
                        'sectionId': 'core-mc1:elemental-fire',
                        'contentPath': ['Elemental, Fire', 'Elemental Inferno']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 24},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:147.1:flame-breath':
            expected_fields = (('persistent-source-field:147.1:1',
              'producer',
              'persistent-producer:147.1:flame-breath',
              'Flame Breath',
              'The fire scamp breathes flames in a 15-foot cone that deals 2d4 fire '
              'damage to each creature within the area (DC 17 basic Reflex save). '
              'Creatures that fail the save also take 1d4 persistent fire damage. The '
              'fire scamp can’t use Flame Breath again for 1d4 rounds.',
              '45fdcd1eec6e7f700c25450a02e3cf2613dd20eb31a254af8d46f65cfcf92d76',
              'core-mc1',
              '147.1',
              'core-mc1:elemental-scamp',
              ('Elemental, Scamp', 'Fire Scamp'),
              (('^.creature', 2, None),
               ('!.Flame Breath', 24, None),
               ('Description', 2, None)),
              (),
              'failed-save-rider',
              'failure-and-critical-failure-source-amount',
              None,
              (('1d4', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:147.1:flame-breath',
             'kind': 'persistent-damage-producer',
             'name': 'Flame Breath',
             'sourceText': 'The fire scamp breathes flames in a 15-foot cone that '
                           'deals 2d4 fire damage to each creature within the area (DC '
                           '17 basic Reflex save). Creatures that fail the save also '
                           'take 1d4 persistent fire damage. The fire scamp can’t use '
                           'Flame Breath again for 1d4 rounds.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'failed-save-rider',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success', 'applies': False, 'amount': None},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '147.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '147.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '147.1',
                        'sectionId': 'core-mc1:elemental-scamp',
                        'contentPath': ['Elemental, Scamp', 'Fire Scamp']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': '!.Flame Breath',
                                              'pairIndex': 24},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:158.3:skewer':
            expected_fields = (('persistent-source-field:158.3:1',
              'producer',
              'persistent-producer:158.3:skewer',
              'Skewer',
              'The faydhaan makes a trident Strike, dealing an extra 2d6 persistent '
              'bleed damage on a hit (4d6 on a critical hit).',
              '8fc6eb6709a729cd8280bdfaba0ada7d57735337a0a3e1b81232dc4c5d8b9280',
              'core-mc1',
              '158.3',
              'core-mc1:genie',
              ('Genie', 'Faydhaan'),
              (('^.creature', 1, None),
               ('!.Skewer', 27, None),
               ('Description', 1, None)),
              ('hit-applies-2d6-bleed', 'critical-hit-explicitly-applies-4d6-bleed'),
              'conditional-hit-damage',
              'strike-hit-success-and-critical-scaling',
              None,
              (('2d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:158.3:skewer',
             'kind': 'persistent-damage-producer',
             'name': 'Skewer',
             'sourceText': 'The faydhaan makes a trident Strike, dealing an extra 2d6 '
                           'persistent bleed damage on a hit (4d6 on a critical hit).',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'conditional-hit-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '158.3'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 4, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '158.3'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '158.3',
                        'sectionId': 'core-mc1:genie',
                        'contentPath': ['Genie', 'Faydhaan']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Skewer', 'pairIndex': 27},
                                             {'rawKey': 'Description', 'pairIndex': 1}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:164.2:twist-the-hook':
            expected_fields = (('persistent-source-field:164.2:1',
              'producer',
              'persistent-producer:164.2:twist-the-hook',
              'Twist the Hook',
              'The marsh giant makes a melee Strike with its gaff. If it hits, it '
              'twists and yanks the gaff to knock the target prone and create an awful '
              'wound, dealing 2d6 persistent bleed damage to the creature.',
              '9033c24471f9c722adddc5ac74c8530182c7d0590e4298179141eea4b33b2214',
              'core-mc1',
              '164.2',
              'core-mc1:giant',
              ('Giant', 'Marsh Giant'),
              (('^.creature', 3, None),
               ('!.Twist the Hook', 24, None),
               ('Description', 1, None)),
              (),
              'conditional-hit-damage',
              'strike-hit-success-and-critical-scaling',
              None,
              (('2d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:164.2:twist-the-hook',
             'kind': 'persistent-damage-producer',
             'name': 'Twist the Hook',
             'sourceText': 'The marsh giant makes a melee Strike with its gaff. If it '
                           'hits, it twists and yanks the gaff to knock the target '
                           'prone and create an awful wound, dealing 2d6 persistent '
                           'bleed damage to the creature.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'conditional-hit-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '164.2'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '164.2',
                        'sectionId': 'core-mc1:giant',
                        'contentPath': ['Giant', 'Marsh Giant']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 3},
                                             {'rawKey': '!.Twist the Hook',
                                              'pairIndex': 24},
                                             {'rawKey': 'Description', 'pairIndex': 1}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:166.2:ranged-0':
            expected_fields = (('persistent-source-field:166.2:1',
              'producer',
              'persistent-producer:166.2:ranged-0',
              'Ranged 0',
              '4d6 fire plus 2d6 persistent fire',
              'dabd5a6988f574c94c4a9631739a5a664fb1a2dbfe5bc84d6e3747de1c6cfdc4',
              'core-mc1',
              '166.2',
              'core-mc1:giant',
              ('Giant', 'Fire Giant'),
              (('^.creature', 3, None),
               ('Ranged', 24, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2d6', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:166.2:ranged-0',
             'kind': 'persistent-damage-producer',
             'name': 'Ranged 0',
             'sourceText': '4d6 fire plus 2d6 persistent fire',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '166.2',
                        'sectionId': 'core-mc1:giant',
                        'contentPath': ['Giant', 'Fire Giant']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 3},
                                             {'rawKey': 'Ranged', 'pairIndex': 24},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:183.1:barbed-maw':
            expected_fields = (('persistent-source-field:183.1:1',
              'producer',
              'persistent-producer:183.1:barbed-maw',
              'Barbed Maw',
              'The grikkitog sinks its barbed teeth into the target, which must '
              'succeed at a DC 34 Reflex save or be immobilized. While immobilized, '
              'the victim takes 3d8 persistent bleed damage and the grikkitog feeds '
              'upon its flesh. The creature is immobilized until the grikkitog ends '
              'the effect as a free action or the target succeeds at a DC 38 check to '
              'Escape. The grikkitog can immobilize any number of creatures with these '
              'maws.',
              'ed14076fce6b675ef1a6dd536f518ced35d4a54beeba969f52d1b1c6aa475587',
              'core-mc1',
              '183.1',
              'core-mc1:grikkitog',
              (),
              (('Grikkitog', 1, None),
               ('Grikkitog', 0, None),
               ('^.creature', 1, None),
               ('!.Barbed Maw', 24, None),
               ('Description', 2, None)),
              ('persistent-bleed-is-source-maintained-while-target-is-immobilized',
               'source-free-action-or-dc-38-escape-ends-immobilized-source-link',
               'maintained-effect-refresh-policy-is-a-bounded-engine-inference'),
              'failed-save-source-maintained',
              'failure-and-critical-failure-source-maintained',
              None,
              (('3d8', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:183.1:barbed-maw',
             'kind': 'persistent-damage-producer',
             'name': 'Barbed Maw',
             'sourceText': 'The grikkitog sinks its barbed teeth into the target, '
                           'which must succeed at a DC 34 Reflex save or be '
                           'immobilized. While immobilized, the victim takes 3d8 '
                           'persistent bleed damage and the grikkitog feeds upon its '
                           'flesh. The creature is immobilized until the grikkitog '
                           'ends the effect as a free action or the target succeeds at '
                           'a DC 38 check to Escape. The grikkitog can immobilize any '
                           'number of creatures with these maws.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'failed-save-source-maintained',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success', 'applies': False, 'amount': None},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '183.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '183.1'}}}}],
             'reapplication': {'mode': 'source-maintained',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': (
                                   'target-remains-immobilized-by-source'
                               )},
             'recoveryOverrides': [{'id': 'barbed-maw-release-or-escape',
                                    'kind': 'automatic-source-end',
                                    'condition': 'barbed-maw-release-or-escape',
                                    'value': None,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '183.1'}}],
             'linkedEffects': [{'id': 'barbed-maw-immobilized',
                                'lifecycle': 'while-contribution-active',
                                'description': 'The source maintains bleed while the '
                                               'target is immobilized.'}],
             'source': {'sourceId': 'core-mc1',
                        'locator': '183.1',
                        'sectionId': 'core-mc1:grikkitog',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Grikkitog', 'pairIndex': 1},
                                             {'rawKey': 'Grikkitog', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Barbed Maw',
                                              'pairIndex': 24},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:19.4:burn-alive':
            expected_fields = (('persistent-source-field:19.4:1',
              'producer',
              'persistent-producer:19.4:burn-alive',
              'Burn Alive',
              'The statue grinds a creature it has grabbed or restrained into the '
              'red-hot coals of its brazier. The target takes 3d8 fire damage and 1d8 '
              'persistent fire damage.',
              'ef3314e6ca8fd681733a4e8412cd9ccc5f183107eca0334e822f8bea52980c3b',
              'core-mc1',
              '19.4',
              'core-mc1:animated-object',
              ('Animated Object', 'Giant Animated Statue'),
              (('^.creature', 1, None),
               ('!.Burn Alive', 23, None),
               ('Description', 2, None)),
              (),
              'direct-ability',
              'source-amount-without-degree-scaling',
              None,
              (('1d8', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:19.4:burn-alive',
             'kind': 'persistent-damage-producer',
             'name': 'Burn Alive',
             'sourceText': 'The statue grinds a creature it has grabbed or restrained '
                           'into the red-hot coals of its brazier. The target takes '
                           '3d8 fire damage and 1d8 persistent fire damage.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'direct-ability',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'no-check',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '19.4'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '19.4',
                        'sectionId': 'core-mc1:animated-object',
                        'contentPath': ['Animated Object', 'Giant Animated Statue']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Burn Alive',
                                              'pairIndex': 23},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:20.3:spray-acid':
            expected_fields = (('persistent-source-field:20.3:1',
              'producer',
              'persistent-producer:20.3:spray-acid',
              'Spray Acid',
              'Frequency once per hour; Effect The ankhrav spews acid in a 30-foot '
              'cone, dealing 3d6 acid damage and 1d6 persistent acid damage (DC 20 '
              'basic Reflex save).',
              'e590d67c8441e8227c19c97e54d857f188d0c0402bcfce2da3ee4a3bc26c5bc9',
              'core-mc1',
              '20.3',
              'core-mc1:ankhrav',
              ('Ankhrav', 'Ankhrav'),
              (('^.creature', 1, None),
               ('!.Spray Acid', 21, None),
               ('Description', 2, None)),
              (),
              'basic-save-damage-component',
              'basic-save-half-full-double-scaling',
              None,
              (('1d6', 'acid', 'base', ()),)),)
            payload = {'id': 'persistent-producer:20.3:spray-acid',
             'kind': 'persistent-damage-producer',
             'name': 'Spray Acid',
             'sourceText': 'Frequency once per hour; Effect The ankhrav spews acid in '
                           'a 30-foot cone, dealing 3d6 acid damage and 1d6 persistent '
                           'acid damage (DC 20 basic Reflex save).',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'basic-save-damage-component',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'acid'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 2,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '20.3',
                        'sectionId': 'core-mc1:ankhrav',
                        'contentPath': ['Ankhrav', 'Ankhrav']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Spray Acid',
                                              'pairIndex': 21},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:20.5:spray-acid':
            expected_fields = (('persistent-source-field:20.5:1',
              'producer',
              'persistent-producer:20.5:spray-acid',
              'Spray Acid',
              'The hive mother spews acid in a 60-foot cone, dealing 8d6 acid damage '
              "and 1d6 persistent acid damage (DC 26 basic Reflex save). It can't "
              'Spray Acid again for 1d4 rounds.',
              'cb95b21c597d00260dd15ef302e6f2547b4582a42b655d3958fbab736341184d',
              'core-mc1',
              '20.5',
              'core-mc1:ankhrav',
              ('Ankhrav', 'Ankhrav Hive Mother'),
              (('^.creature', 1, None),
               ('!.Spray Acid', 23, None),
               ('Description', 2, None)),
              (),
              'basic-save-damage-component',
              'basic-save-half-full-double-scaling',
              None,
              (('1d6', 'acid', 'base', ()),)),)
            payload = {'id': 'persistent-producer:20.5:spray-acid',
             'kind': 'persistent-damage-producer',
             'name': 'Spray Acid',
             'sourceText': 'The hive mother spews acid in a 60-foot cone, dealing 8d6 '
                           'acid damage and 1d6 persistent acid damage (DC 26 basic '
                           "Reflex save). It can't Spray Acid again for 1d4 rounds.",
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'basic-save-damage-component',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'acid'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 2,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '20.5',
                        'sectionId': 'core-mc1:ankhrav',
                        'contentPath': ['Ankhrav', 'Ankhrav Hive Mother']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Spray Acid',
                                              'pairIndex': 23},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:202.4:alchemical-grenade':
            expected_fields = (('persistent-source-field:202.4:1',
              'producer',
              'persistent-producer:202.4:alchemical-grenade',
              'Alchemical Grenades',
              'A hryngar bombardier carries 6 alchemical grenades that deal either '
              'acid, cold, or fire damage plus 1 persistent damage and 1 splash damage '
              'of the same type (typically two of each). The bombardier replenishes '
              'these grenades each day using easily collected materials.',
              '077bcb87e86c4940cbe6337f6b7aa18cc43038cf97e7748432f701a705889068',
              'core-mc1',
              '202.4',
              'core-mc1:hryngar',
              ('Hryngar', 'Hryngar Bombardier'),
              (('^.creature', 1, None), ('!.Alchemical Grenades', 14, None)),
              ('selected-immediate-type-acid-cold-or-fire-binds-'
               'persistent-and-splash-types',
               'ability-description-and-ranged-strike-are-one-corroborated-binding'),
              'strike-damage-descriptor',
              'corroborating-definition-no-separate-application',
              None,
              (('1',
                'selected-immediate-damage-type',
                'base',
                ('acid', 'cold', 'fire')),)),
             ('persistent-source-field:202.4:2',
              'producer',
              'persistent-producer:202.4:alchemical-grenade',
              'Ranged 0',
              '1d6 acid, cold, or fire plus 1 persistent damage and 1 splash damage of '
              'the same type',
              '65b81db436d40a59cbb903faee460e4bbccd3c79357ee0552b1c2163fa18fbb0',
              'core-mc1',
              '202.4',
              'core-mc1:hryngar',
              ('Hryngar', 'Hryngar Bombardier'),
              (('^.creature', 1, None),
               ('Ranged', 23, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1',
                'selected-immediate-damage-type',
                'base',
                ('acid', 'cold', 'fire')),)))
            payload = {'id': 'persistent-producer:202.4:alchemical-grenade',
             'kind': 'persistent-damage-producer',
             'name': 'Ranged 0',
             'sourceText': '1d6 acid, cold, or fire plus 1 persistent damage and 1 '
                           'splash damage of the same type',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'selected-immediate-damage-type',
                                   'allowedDamageTypes': ['acid', 'cold', 'fire']},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 1},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 1},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '202.4',
                        'sectionId': 'core-mc1:hryngar',
                        'contentPath': ['Hryngar', 'Hryngar Bombardier']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Ranged', 'pairIndex': 23},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:21.5:cling':
            expected_fields = (('persistent-source-field:21.5:1',
              'producer',
              'persistent-producer:21.5:cling',
              'Cling',
              'The swarm takes 1d6 damage as ants cling to the creature and continue '
              'biting, dealing 3d6 persistent piercing damage. High winds or immersion '
              'in water reduces the DC of the flat check to end this persistent damage '
              'to 5. Any area damage dealt to the creature destroys these clinging '
              'ants.',
              'c4afc3f310fbd2de87e47e88bba685a5af4590f36b09cea97fb5408966c5f87f',
              'core-mc1',
              '21.5',
              'core-mc1:ant',
              ('Ant', 'Army Ant Swarm'),
              (('^.creature', 1, None), ('!.Cling', 20, None), ('Effect', 2, None)),
              ('recovery-flat-check-dc-is-5-during-high-winds-or-water-immersion',
               'area-damage-destroys-ants-and-ends-this-contribution'),
              'triggered-direct-ability',
              'source-amount-without-degree-scaling',
              None,
              (('3d6', 'piercing', 'base', ()),)),)
            payload = {'id': 'persistent-producer:21.5:cling',
             'kind': 'persistent-damage-producer',
             'name': 'Cling',
             'sourceText': 'The swarm takes 1d6 damage as ants cling to the creature '
                           'and continue biting, dealing 3d6 persistent piercing '
                           'damage. High winds or immersion in water reduces the DC of '
                           'the flat check to end this persistent damage to 5. Any '
                           'area damage dealt to the creature destroys these clinging '
                           'ants.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'triggered-direct-ability',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'piercing'},
             'outcomes': [{'degree': 'no-check',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '21.5'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [{'id': 'high-winds-or-immersion-dc',
                                    'kind': 'flat-check-dc-set',
                                    'condition': 'high-winds-or-water-immersion',
                                    'value': 5,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '21.5'}},
                                   {'id': 'area-damage-destroys-clinging-ants',
                                    'kind': 'automatic-source-end',
                                    'condition': 'area-damage-destroys-clinging-ants',
                                    'value': None,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '21.5'}}],
             'linkedEffects': [{'id': 'clinging-ants',
                                'lifecycle': 'while-contribution-active',
                                'description': 'Clinging ants remain until recovery or '
                                               'sourced destruction.'}],
             'source': {'sourceId': 'core-mc1',
                        'locator': '21.5',
                        'sectionId': 'core-mc1:ant',
                        'contentPath': ['Ant', 'Army Ant Swarm']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Cling', 'pairIndex': 20},
                                             {'rawKey': 'Effect', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.2'}]}
        elif binding_id == 'persistent-producer:210.4:construct-trap':
            expected_fields = (('persistent-source-field:210.4:1',
              'producer',
              'persistent-producer:210.4:construct-trap',
              'Construct Trap',
              'The kobold scout creates a rudimentary trap on any square adjacent to '
              'it. This must be on a surface, such as a floor, wall, or ceiling. The '
              'trap activates the next time a creature moves adjacent to it. The '
              'creature takes 1d6 piercing damage and 1 persistent bleed damage with a '
              'DC 16 basic Reflex save. The trap is destroyed when activated or after '
              '1 hour, whichever comes first. The scout typically carries enough raw '
              'materials to make one trap.',
              '59a57b1b37046b89afb544d8e0f0a5e68d959bc7fdda1c4adc710afe2e482721',
              'core-mc1',
              '210.4',
              'core-mc1:kobold',
              ('Kobold', 'Kobold Scout'),
              (('^.creature', 1, None),
               ('!.Construct Trap', 22, None),
               ('Description', 2, None)),
              (),
              'hazard-basic-save-damage-component',
              'basic-save-half-full-double-scaling',
              None,
              (('1', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:210.4:construct-trap',
             'kind': 'persistent-damage-producer',
             'name': 'Construct Trap',
             'sourceText': 'The kobold scout creates a rudimentary trap on any square '
                           'adjacent to it. This must be on a surface, such as a '
                           'floor, wall, or ceiling. The trap activates the next time '
                           'a creature moves adjacent to it. The creature takes 1d6 '
                           'piercing damage and 1 persistent bleed damage with a DC 16 '
                           'basic Reflex save. The trap is destroyed when activated or '
                           'after 1 hour, whichever comes first. The scout typically '
                           'carries enough raw materials to make one trap.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'hazard-basic-save-damage-component',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 1},
                                      'scale': {'numerator': 1,
                                                'denominator': 2,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 1},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 1},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '210.4',
                        'sectionId': 'core-mc1:kobold',
                        'contentPath': ['Kobold', 'Kobold Scout']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Construct Trap',
                                              'pairIndex': 22},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:213.1:poison-tooth':
            expected_fields = (('persistent-source-field:213.1:1',
              'producer',
              'persistent-producer:213.1:poison-tooth',
              'Poison Tooth',
              '<b>Requirements</b> The krooth damaged a creature with its jaws on its '
              'most recent action this turn; <b>Effect</b> The krooth snaps off one of '
              'its teeth in the creature it hit. The creature takes 1d6 persistent '
              'bleed damage and is drained 1. Neither can be healed while the tooth '
              'remains. Removing the tooth safely requires a successful DC 26 check to '
              'Administer First Aid. Instead of ending bleeding or stabilizing, this '
              "removes the tooth and the drained condition, but it doesn't "
              'automatically end the bleed damage.',
              '12dbb8622f7c615b2d0eb73d75904f7058d22a428fd1e9ea5c60aa759d42a932',
              'core-mc1',
              '213.1',
              'core-mc1:krooth',
              (),
              (('Krooth', 1, None),
               ('Krooth', 0, None),
               ('^.creature', 3, None),
               ('!.Poison Tooth', 22, None),
               ('Description', 2, None)),
              ('bleed-and-drained-cannot-be-healed-while-tooth-remains',
               'dc-26-administer-first-aid-removes-tooth-and-drained-not-bleed'),
              'direct-ability',
              'source-amount-without-degree-scaling',
              None,
              (('1d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:213.1:poison-tooth',
             'kind': 'persistent-damage-producer',
             'name': 'Poison Tooth',
             'sourceText': '<b>Requirements</b> The krooth damaged a creature with its '
                           'jaws on its most recent action this turn; <b>Effect</b> '
                           'The krooth snaps off one of its teeth in the creature it '
                           'hit. The creature takes 1d6 persistent bleed damage and is '
                           'drained 1. Neither can be healed while the tooth remains. '
                           'Removing the tooth safely requires a successful DC 26 '
                           'check to Administer First Aid. Instead of ending bleeding '
                           'or stabilizing, this removes the tooth and the drained '
                           "condition, but it doesn't automatically end the bleed "
                           'damage.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'direct-ability',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'no-check',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '213.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [{'id': 'krooth-tooth-and-drained',
                                'lifecycle': 'independent-duration',
                                'description': 'The embedded tooth blocks healing of '
                                               'bleed and drained.'},
                               {'id': 'krooth-tooth-first-aid',
                                'lifecycle': 'independent-duration',
                                'description': 'DC 26 First Aid removes the tooth and '
                                               'drained, not bleed.'}],
             'source': {'sourceId': 'core-mc1',
                        'locator': '213.1',
                        'sectionId': 'core-mc1:krooth',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Krooth', 'pairIndex': 1},
                                             {'rawKey': 'Krooth', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 3},
                                             {'rawKey': '!.Poison Tooth',
                                              'pairIndex': 22},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:217.2:spore-cloud':
            expected_fields = (('persistent-source-field:217.2:1',
              'producer',
              'persistent-producer:217.2:spore-cloud',
              'Spore Cloud',
              'A fungus leshy can unleash a cloud of spores that irritates the eyes '
              'and throats of non-fungus creatures in a 15-foot emanation. Each '
              'creature must succeed at a DC 16 Fortitude save or take 1 persistent '
              'poison damage. A creature has its vision reduced as long as the '
              'persistent damage continues and can see only within 20 feet.',
              'fa44aa265404854d5cbe04d55e76dcfd5624f349fc9409d765dc542bbd0a3ee8',
              'core-mc1',
              '217.2',
              'core-mc1:leshy',
              ('Leshy', 'Fungus Leshy'),
              (('^.creature', 1, None),
               ('!.Spore Cloud', 24, None),
               ('Description', 2, None)),
              ('vision-is-limited-to-20-feet-while-this-persistent-poison-continues',),
              'failed-save-rider',
              'failure-and-critical-failure-source-amount',
              None,
              (('1', 'poison', 'base', ()),)),)
            source_field = fields[0]
            payload = compile_fixed_failed_save_persistent_damage(
                FixedFailedSavePersistentDamageBinding(
                    binding_id=source_field.binding_id,
                    name=source_field.owner,
                    source_text=source_field.source_text,
                    source_text_sha256=source_field.source_text_sha256,
                    source_id=source_field.source_id,
                    locator=source_field.locator,
                    section_id=source_field.section_id,
                    content_path=source_field.content_path,
                    ordered_path=tuple(
                        PersistentDamagePathStep(
                            raw_key=step.raw_key,
                            pair_index=step.pair_index,
                            array_index=step.array_index,
                        )
                        for step in source_field.ordered_path
                    ),
                    damage_expression="1",
                    damage_type="poison",
                    linked_effects=(
                        PersistentDamageLinkedEffect(
                            effect_id="spore-cloud-vision-limit",
                            lifecycle="while-contribution-active",
                            description=(
                                "Vision is limited to 20 feet while this poison "
                                "continues."
                            ),
                        ),
                    ),
                    rules=(
                        RuleReference("core-pc1", "406.2"),
                        RuleReference("core-pc1", "407.1"),
                        RuleReference("core-pc1", "400.1"),
                        RuleReference("core-pc1", "436.3"),
                        RuleReference("core-pc1", "445.4"),
                        RuleReference("core-pc1", "409.6"),
                    ),
                    scale_rule=RuleReference("core-mc1", "217.2"),
                )
            )
            if payload is None:
                return None
        elif binding_id == 'persistent-producer:220.2:magma-breath':
            expected_fields = (('persistent-source-field:220.2:1',
              'producer',
              'persistent-producer:220.2:magma-breath',
              'Magma Breath',
              'The crag linnorm breathes out a stream of magma in a 120-foot line that '
              'deals 12d6 fire damage to creatures within the area (DC 34 basic Reflex '
              'save). Any creature that fails its save also takes 4d6 persistent fire '
              "damage. The linnorm can't use Magma Breath again for 1d4 rounds. The "
              "magma remains until the start of the linnorm's next turn. If the "
              'linnorm was on the ground, the magma remains as a burning line on the '
              'ground directly under the line of the Magma Breath; if the linnorm was '
              'airborne, the magma rains down in a sheet 60 feet high. Any creature '
              'that moves across or through the magma takes 6d6 fire damage (DC 34 '
              "basic Reflex save). At the start of the linnorm's next turn, the magma "
              'cools to a thin layer of brittle stone, or the magma rain finishes '
              'falling and turns to harmless pebbles. The cooled magma quickly '
              'degrades to powder and sand over the course of several hours.',
              '06a21d3a60e38ac5cc3d4b5e251fc8b65945ecb97e8d86d37102d41334476353',
              'core-mc1',
              '220.2',
              'core-mc1:linnorm',
              ('Linnorm', 'Crag Linnorm'),
              (('^.creature', 1, None),
               ('!.Magma Breath', 28, None),
               ('Description', 2, None)),
              (),
              'failed-save-rider',
              'failure-and-critical-failure-source-amount',
              None,
              (('4d6', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:220.2:magma-breath',
             'kind': 'persistent-damage-producer',
             'name': 'Magma Breath',
             'sourceText': 'The crag linnorm breathes out a stream of magma in a '
                           '120-foot line that deals 12d6 fire damage to creatures '
                           'within the area (DC 34 basic Reflex save). Any creature '
                           'that fails its save also takes 4d6 persistent fire damage. '
                           "The linnorm can't use Magma Breath again for 1d4 rounds. "
                           "The magma remains until the start of the linnorm's next "
                           'turn. If the linnorm was on the ground, the magma remains '
                           'as a burning line on the ground directly under the line of '
                           'the Magma Breath; if the linnorm was airborne, the magma '
                           'rains down in a sheet 60 feet high. Any creature that '
                           'moves across or through the magma takes 6d6 fire damage '
                           "(DC 34 basic Reflex save). At the start of the linnorm's "
                           'next turn, the magma cools to a thin layer of brittle '
                           'stone, or the magma rain finishes falling and turns to '
                           'harmless pebbles. The cooled magma quickly degrades to '
                           'powder and sand over the course of several hours.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'failed-save-rider',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success', 'applies': False, 'amount': None},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 4, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '220.2'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 4, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '220.2'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '220.2',
                        'sectionId': 'core-mc1:linnorm',
                        'contentPath': ['Linnorm', 'Crag Linnorm']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Magma Breath',
                                              'pairIndex': 28},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:243.1:blight-breath':
            expected_fields = (('persistent-source-field:243.1:1',
              'producer',
              'persistent-producer:243.1:blight-breath',
              'Blight Breath',
              'The nuckelavee breathes a 30-foot cone of foulness, dealing 8d6 void '
              'damage to living creatures in the area with a DC 28 basic Fortitude '
              'save. A creature that fails also takes 2d6 persistent bleed damage. The '
              "nuckelavee can't use Blight Breath again for 1d4 rounds.",
              '731b93c6677adbca31bac8c9e6b29046329ee41ed443213791f3b29ba9977a57',
              'core-mc1',
              '243.1',
              'core-mc1:nuckelavee',
              (),
              (('Nuckelavee', 1, None),
               ('Nuckelavee', 0, None),
               ('^.creature', 3, None),
               ('!.Blight Breath', 27, None),
               ('Description', 2, None)),
              (),
              'failed-save-rider',
              'failure-and-critical-failure-source-amount',
              None,
              (('2d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:243.1:blight-breath',
             'kind': 'persistent-damage-producer',
             'name': 'Blight Breath',
             'sourceText': 'The nuckelavee breathes a 30-foot cone of foulness, '
                           'dealing 8d6 void damage to living creatures in the area '
                           'with a DC 28 basic Fortitude save. A creature that fails '
                           'also takes 2d6 persistent bleed damage. The nuckelavee '
                           "can't use Blight Breath again for 1d4 rounds.",
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'failed-save-rider',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success', 'applies': False, 'amount': None},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '243.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '243.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '243.1',
                        'sectionId': 'core-mc1:nuckelavee',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Nuckelavee', 'pairIndex': 1},
                                             {'rawKey': 'Nuckelavee', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 3},
                                             {'rawKey': '!.Blight Breath',
                                              'pairIndex': 27},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:249.2:wretched-weeps':
            expected_fields = (('persistent-source-field:249.2:1',
              'producer',
              'persistent-producer:249.2:wretched-weeps',
              'Wretched Weeps',
              '(disease) <b>Saving Throw</b> DC 19 Fortitude; <b>Stage 1</b> carrier '
              'with no ill effect (1 day); <b>Stage 2</b> 2d4 persistent bleed every '
              'hour and enfeebled 1 (1 day); <b>Stage 3</b> 2d6 persistent bleed every '
              'hour and enfeebled 2 (1 day)',
              '82c06d0f721830834a710bb451fa63e3f5fdcd6bdc7a6f0a3b3f6b44f7d43269',
              'core-mc1',
              '249.2',
              'core-mc1:ofalth',
              ('Ofalth', 'Larval Ofalth'),
              (('^.creature', 1, None), ('!.Wretched Weeps', 25, None)),
              ('stage-2-reapplies-2d4-persistent-bleed-every-hour',
               'stage-3-reapplies-2d6-persistent-bleed-every-hour'),
              'affliction-stage-reapplication',
              'stage-entry-or-explicit-stage-cadence-source-amount',
              None,
              (('2d4', 'bleed', 'base', ()), ('2d6', 'bleed', 'base', ()))),)
            payload = {'id': 'persistent-producer:249.2:wretched-weeps',
             'kind': 'persistent-damage-producer',
             'name': 'Wretched Weeps',
             'sourceText': '(disease) <b>Saving Throw</b> DC 19 Fortitude; <b>Stage '
                           '1</b> carrier with no ill effect (1 day); <b>Stage 2</b> '
                           '2d4 persistent bleed every hour and enfeebled 1 (1 day); '
                           '<b>Stage 3</b> 2d6 persistent bleed every hour and '
                           'enfeebled 2 (1 day)',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'affliction-stage-reapplication',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'no-check',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '249.2'}}}},
                          {'degree': 'no-check',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '249.2'}}}}],
             'reapplication': {'mode': 'affliction-stage-cadence',
                               'intervalUnit': 'hour',
                               'intervalValue': 1,
                               'intervalRoll': None,
                               'statePredicate': 'affliction-stage-2-or-3-active'},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '249.2',
                        'sectionId': 'core-mc1:ofalth',
                        'contentPath': ['Ofalth', 'Larval Ofalth']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Wretched Weeps',
                                              'pairIndex': 25}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'},
                       {'sourceId': 'core-pc1', 'locator': '430.7'},
                       {'sourceId': 'core-pc1', 'locator': '430.8'}]}
        elif binding_id == 'persistent-producer:252.2:melee-1':
            expected_fields = (('persistent-source-field:252.2:1',
              'producer',
              'persistent-producer:252.2:melee-1',
              'Melee 1',
              '2d6+9 piercing plus 1d6 persistent bleed',
              '3b184e525662f744ddd5a3d3d9989681001dc32d3f8973bd9260d69b4f801beb',
              'core-mc1',
              '252.2',
              'core-mc1:oni',
              ('Oni', 'Mountain Oni'),
              (('^.creature', 1, None),
               ('Melee', 23, None),
               (None, None, 1),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:252.2:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '2d6+9 piercing plus 1d6 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '252.2',
                        'sectionId': 'core-mc1:oni',
                        'contentPath': ['Oni', 'Mountain Oni']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 23},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:253.1:melee-1':
            expected_fields = (('persistent-source-field:253.1:1',
              'producer',
              'persistent-producer:253.1:melee-1',
              'Melee 1',
              '2d6+16 piercing plus 1d6 persistent bleed',
              '6b17ebee387b3acedd9e90997a77f04cdffc0b907d2eaa10da2e7cbf8fa1aece',
              'core-mc1',
              '253.1',
              'core-mc1:oni',
              ('Oni', 'Snow Oni'),
              (('^.creature', 2, None),
               ('Melee', 25, None),
               (None, None, 1),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:253.1:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '2d6+16 piercing plus 1d6 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '253.1',
                        'sectionId': 'core-mc1:oni',
                        'contentPath': ['Oni', 'Snow Oni']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': 'Melee', 'pairIndex': 25},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:254.1:melee-1':
            expected_fields = (('persistent-source-field:254.1:1',
              'producer',
              'persistent-producer:254.1:melee-1',
              'Melee 1',
              '2d6+14 piercing plus 1d8 persistent bleed',
              '613788d3151438b4a0acbdfabd828394c1131f11619e1cac7e997a8b413996cb',
              'core-mc1',
              '254.1',
              'core-mc1:oni',
              ('Oni', 'Caldera Oni'),
              (('^.creature', 1, None),
               ('Melee', 25, None),
               (None, None, 1),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d8', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:254.1:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '2d6+14 piercing plus 1d8 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '254.1',
                        'sectionId': 'core-mc1:oni',
                        'contentPath': ['Oni', 'Caldera Oni']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 25},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:254.3:melee-1':
            expected_fields = (('persistent-source-field:254.3:1',
              'producer',
              'persistent-producer:254.3:melee-1',
              'Melee 1',
              '3d6+10 piercing plus 2d6 persistent electricity and Improved Grab (page '
              '359)',
              '76c217954dc6b6b6605a0799a058f506e2368010725b9becd5fbf439948e60d3',
              'core-mc1',
              '254.3',
              'core-mc1:oni',
              ('Oni', 'Island Oni'),
              (('^.creature', 2, None),
               ('Melee', 26, None),
               (None, None, 1),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2d6', 'electricity', 'base', ()),)),)
            payload = {'id': 'persistent-producer:254.3:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '3d6+10 piercing plus 2d6 persistent electricity and '
                           'Improved Grab (page 359)',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'electricity'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '254.3',
                        'sectionId': 'core-mc1:oni',
                        'contentPath': ['Oni', 'Island Oni']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': 'Melee', 'pairIndex': 26},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:257.1:tomb-curse':
            expected_fields = (('persistent-source-field:257.1:1',
              'producer',
              'persistent-producer:257.1:tomb-curse',
              'Tomb Curse',
              "A creature hit by a tomb jelly's pseudopod takes 1d6 persistent void "
              'damage. If the creature dies while it has this persistent damage, its '
              'corpse is affected by <i>peaceful rest</i>, except the tomb jelly can '
              'still dissolve its flesh.',
              'e152fc1d266ab05830d307ca47890fafe019e2466d83dbbc8f11a466a8567e9e',
              'core-mc1',
              '257.1',
              'core-mc1:ooze',
              ('Ooze', 'Tomb Jelly'),
              (('^.creature', 1, None),
               ('!.Tomb Curse', 23, None),
               ('Description', 1, None)),
              (
                  'death-while-this-contribution-is-active-applies-'
                  'source-specific-corpse-effect',
              ),
              'conditional-hit-damage',
              'strike-hit-success-and-critical-scaling',
              None,
              (('1d6', 'void', 'base', ()),)),)
            payload = {'id': 'persistent-producer:257.1:tomb-curse',
             'kind': 'persistent-damage-producer',
             'name': 'Tomb Curse',
             'sourceText': "A creature hit by a tomb jelly's pseudopod takes 1d6 "
                           'persistent void damage. If the creature dies while it has '
                           'this persistent damage, its corpse is affected by '
                           '<i>peaceful rest</i>, except the tomb jelly can still '
                           'dissolve its flesh.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'conditional-hit-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'void'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '257.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [{'id': 'tomb-curse-corpse-effect',
                                'lifecycle': 'on-death-while-active',
                                'description': 'Apply the Tomb Curse corpse '
                                               'consequence on death.'}],
             'source': {'sourceId': 'core-mc1',
                        'locator': '257.1',
                        'sectionId': 'core-mc1:ooze',
                        'contentPath': ['Ooze', 'Tomb Jelly']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Tomb Curse',
                                              'pairIndex': 23},
                                             {'rawKey': 'Description', 'pairIndex': 1}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:264.1:melee-0':
            expected_fields = (('persistent-source-field:264.1:1',
              'producer',
              'persistent-producer:264.1:melee-0',
              'Melee 0',
              '1d12+9 piercing plus 3d8 fire and 2d10 persistent fire',
              '290d319e6a76799cdaf8c1bf9c3651be1483d7a9359ca59439596a3a2859b57c',
              'core-mc1',
              '264.1',
              'core-mc1:phoenix',
              (),
              (('Phoenix', 1, None),
               ('Phoenix', 0, None),
               ('^.creature', 4, None),
               ('Melee', 25, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2d10', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:264.1:melee-0',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 0',
             'sourceText': '1d12+9 piercing plus 3d8 fire and 2d10 persistent fire',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 10},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 10},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '264.1',
                        'sectionId': 'core-mc1:phoenix',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Phoenix', 'pairIndex': 1},
                                             {'rawKey': 'Phoenix', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 4},
                                             {'rawKey': 'Melee', 'pairIndex': 25},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:264.1:melee-1':
            expected_fields = (('persistent-source-field:264.1:2',
              'producer',
              'persistent-producer:264.1:melee-1',
              'Melee 1',
              '1d6+6 piercing plus 3d8 fire and 2d10 persistent fire',
              'fb6cd8067a6b11d2d895771c4f5dc9b7e1e2583ccaabf26d1add58d4c8ab99fc',
              'core-mc1',
              '264.1',
              'core-mc1:phoenix',
              (),
              (('Phoenix', 1, None),
               ('Phoenix', 0, None),
               ('^.creature', 4, None),
               ('Melee', 25, None),
               (None, None, 1),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2d10', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:264.1:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '1d6+6 piercing plus 3d8 fire and 2d10 persistent fire',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 10},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 10},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '264.1',
                        'sectionId': 'core-mc1:phoenix',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Phoenix', 'pairIndex': 1},
                                             {'rawKey': 'Phoenix', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 4},
                                             {'rawKey': 'Melee', 'pairIndex': 25},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:264.1:ranged-0':
            expected_fields = (('persistent-source-field:264.1:3',
              'producer',
              'persistent-producer:264.1:ranged-0',
              'Ranged 0',
              '6d6 fire plus 2d10 persistent fire',
              'c07e44a4a9fc7d0fc24a1ca500d97cc298bfe411fe6612b1b288741117f0f24e',
              'core-mc1',
              '264.1',
              'core-mc1:phoenix',
              (),
              (('Phoenix', 1, None),
               ('Phoenix', 0, None),
               ('^.creature', 4, None),
               ('Ranged', 26, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2d10', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:264.1:ranged-0',
             'kind': 'persistent-damage-producer',
             'name': 'Ranged 0',
             'sourceText': '6d6 fire plus 2d10 persistent fire',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 10},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 10},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '264.1',
                        'sectionId': 'core-mc1:phoenix',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Phoenix', 'pairIndex': 1},
                                             {'rawKey': 'Phoenix', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 4},
                                             {'rawKey': 'Ranged', 'pairIndex': 26},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:27.4:flame-of-justice':
            expected_fields = (('persistent-source-field:27.4:1',
              'producer',
              'persistent-producer:27.4:flame-of-justice',
              'Flame of Justice',
              "(divine, holy) An aesra's spirit of righteousness manifests as a "
              'two-handed sword of fire. If disarmed or thrown as a ranged weapon, the '
              'flame of justice vanishes after landing or dealing damage and reappears '
              "in the aesra's hands again instantly. On a critical hit, the target "
              'also takes 2d6 persistent fire damage.',
              '1cee4314d270559c188d08095c4e141ec6c90edc503e195a7ceabebf116cd96b',
              'core-mc1',
              '27.4',
              'core-mc1:archon',
              ('Archon', 'Aesra (Legion Archon)'),
              (('^.creature', 1, None), ('!.Flame of Justice', 27, None)),
              (),
              'critical-hit-trigger',
              'critical-hit-source-amount-no-further-scaling',
              None,
              (('2d6', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:27.4:flame-of-justice',
             'kind': 'persistent-damage-producer',
             'name': 'Flame of Justice',
             'sourceText': "(divine, holy) An aesra's spirit of righteousness "
                           'manifests as a two-handed sword of fire. If disarmed or '
                           'thrown as a ranged weapon, the flame of justice vanishes '
                           'after landing or dealing damage and reappears in the '
                           "aesra's hands again instantly. On a critical hit, the "
                           'target also takes 2d6 persistent fire damage.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'critical-hit-trigger',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '27.4'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '27.4',
                        'sectionId': 'core-mc1:archon',
                        'contentPath': ['Archon', 'Aesra (Legion Archon)']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Flame of Justice',
                                              'pairIndex': 27}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:276.4:beetle-breath':
            expected_fields = (('persistent-source-field:276.4:1',
              'producer',
              'persistent-producer:276.4:beetle-breath',
              'Beetle Breath',
              'The yamaraj breathes a blast of beetles in a 50-foot cone that deals '
              '14d8 slashing damage and 4d8 persistent slashing damage to creatures in '
              'the area with a DC 42 Reflex save. It can’t use Beetle Breath again for '
              '1d4 rounds.',
              '10e9fb1593425d0887706873cd88c860982e738ebf34a51263dc348286840643',
              'core-mc1',
              '276.4',
              'core-mc1:psychopomp',
              ('Psychopomp', 'Yamaraj'),
              (('^.creature', 1, None),
               ('!.Beetle Breath', 27, None),
               ('Description', 2, None),
               ('~.p', 0, None)),
              (),
              'explicit-save-damage-component',
              'explicit-half-full-double-scaling',
              None,
              (('4d8', 'slashing', 'base', ()),)),)
            payload = {'id': 'persistent-producer:276.4:beetle-breath',
             'kind': 'persistent-damage-producer',
             'name': 'Beetle Breath',
             'sourceText': 'The yamaraj breathes a blast of beetles in a 50-foot cone '
                           'that deals 14d8 slashing damage and 4d8 persistent '
                           'slashing damage to creatures in the area with a DC 42 '
                           'Reflex save. It can’t use Beetle Breath again for 1d4 '
                           'rounds.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'explicit-save-damage-component',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'slashing'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 4, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 2,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 4, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 4, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '276.4',
                        'sectionId': 'core-mc1:psychopomp',
                        'contentPath': ['Psychopomp', 'Yamaraj']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Beetle Breath',
                                              'pairIndex': 27},
                                             {'rawKey': 'Description', 'pairIndex': 2},
                                             {'rawKey': '~.p', 'pairIndex': 0}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.2'}]}
        elif binding_id == 'persistent-producer:278.5:melee-0':
            expected_fields = (('persistent-source-field:278.5:1',
              'producer',
              'persistent-producer:278.5:melee-0',
              'Melee 0',
              '2d10+10 piercing plus 1d8 persistent bleed',
              '90a91200e36836301070c28508fce3ba6278d05aaaf4cbf6d0e7cec0f9e865de',
              'core-mc1',
              '278.5',
              'core-mc1:pterosaur',
              ('Pterosaur', 'Quetzalcoatlus'),
              (('^.creature', 2, None),
               ('Melee', 18, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d8', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:278.5:melee-0',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 0',
             'sourceText': '2d10+10 piercing plus 1d8 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '278.5',
                        'sectionId': 'core-mc1:pterosaur',
                        'contentPath': ['Pterosaur', 'Quetzalcoatlus']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': 'Melee', 'pairIndex': 18},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:279.1:change-shape':
            expected_fields = (('persistent-source-field:279.1:2',
              'producer',
              'persistent-producer:279.1:change-shape',
              'Change Shape',
              'The pukwudgie takes on the physical form of a giant porcupine or '
              'resumes their natural form (page 358). In porcupine form, their size '
              'changes to Medium, they lose their weapon Strikes, and they gain a '
              'quill Strike (+18 for 2d8+6 piercing plus 1d8 persistent poison).',
              'a412572ae0a0327942f4bcf801321e69dda940331c21220805d9190ab7e4acc4',
              'core-mc1',
              '279.1',
              'core-mc1:pukwudgie',
              (),
              (('Pukwudgie', 1, None),
               ('Pukwudgie', 0, None),
               ('^.creature', 5, None),
               ('!.Change Shape', 26, None),
               ('Description', 2, None)),
              (),
              'granted-strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d8', 'poison', 'base', ()),)),)
            payload = {'id': 'persistent-producer:279.1:change-shape',
             'kind': 'persistent-damage-producer',
             'name': 'Change Shape',
             'sourceText': 'The pukwudgie takes on the physical form of a giant '
                           'porcupine or resumes their natural form (page 358). In '
                           'porcupine form, their size changes to Medium, they lose '
                           'their weapon Strikes, and they gain a quill Strike (+18 '
                           'for 2d8+6 piercing plus 1d8 persistent poison).',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'granted-strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'poison'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '279.1',
                        'sectionId': 'core-mc1:pukwudgie',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Pukwudgie', 'pairIndex': 1},
                                             {'rawKey': 'Pukwudgie', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 5},
                                             {'rawKey': '!.Change Shape',
                                              'pairIndex': 26},
                                             {'rawKey': 'Description', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.6'}]}
        elif binding_id == 'persistent-producer:279.1:defensive-quills':
            expected_fields = (('persistent-source-field:279.1:1',
              'producer',
              'persistent-producer:279.1:defensive-quills',
              'Defensive Quills',
              'A creature that hits a pukwudgie with an unarmed Strike or a non-reach '
              'melee Strike takes 3d8 piercing damage (basic Reflex save). On a '
              'critical failure, the creature also takes 1d6 persistent poison damage '
              'from the poisoned quills.',
              'b246b25ce89d64934a9a680795810283c75a0816e13f39691d4e663e59c0c7d7',
              'core-mc1',
              '279.1',
              'core-mc1:pukwudgie',
              (),
              (('Pukwudgie', 1, None),
               ('Pukwudgie', 0, None),
               ('^.creature', 5, None),
               ('!.Defensive Quills', 21, None),
               ('Description', 0, None)),
              (),
              'critical-failure-rider',
              'critical-failure-source-amount',
              None,
              (('1d6', 'poison', 'base', ()),)),)
            payload = {'id': 'persistent-producer:279.1:defensive-quills',
             'kind': 'persistent-damage-producer',
             'name': 'Defensive Quills',
             'sourceText': 'A creature that hits a pukwudgie with an unarmed Strike or '
                           'a non-reach melee Strike takes 3d8 piercing damage (basic '
                           'Reflex save). On a critical failure, the creature also '
                           'takes 1d6 persistent poison damage from the poisoned '
                           'quills.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'critical-failure-rider',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'poison'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success', 'applies': False, 'amount': None},
                          {'degree': 'failure', 'applies': False, 'amount': None},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '279.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '279.1',
                        'sectionId': 'core-mc1:pukwudgie',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Pukwudgie', 'pairIndex': 1},
                                             {'rawKey': 'Pukwudgie', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 5},
                                             {'rawKey': '!.Defensive Quills',
                                              'pairIndex': 21},
                                             {'rawKey': 'Description', 'pairIndex': 0}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.6'}]}
        elif binding_id == 'persistent-producer:281.3:melee-0':
            expected_fields = (('persistent-source-field:281.3:1',
              'producer',
              'persistent-producer:281.3:melee-0',
              'Melee 0',
              '3d12+14 piercing plus 3d6 persistent bleed and rotting curse',
              '9ff39ee253ec3293f168c5a0a8385d3eeb3cf2322b88adc8a9e1f0af7fea71d4',
              'core-mc1',
              '281.3',
              'core-mc1:qlippoth',
              ('Qlippoth', 'Augnagar (Hunger Qlippoth)'),
              (('^.creature', 2, None),
               ('Melee', 22, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('3d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:281.3:melee-0',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 0',
             'sourceText': '3d12+14 piercing plus 3d6 persistent bleed and rotting '
                           'curse',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '281.3',
                        'sectionId': 'core-mc1:qlippoth',
                        'contentPath': ['Qlippoth', 'Augnagar (Hunger Qlippoth)']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': 'Melee', 'pairIndex': 22},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:281.3:melee-1':
            expected_fields = (('persistent-source-field:281.3:2',
              'producer',
              'persistent-producer:281.3:melee-1',
              'Melee 1',
              '3d8+14 slashing plus 3d6 persistent bleed',
              '8da677f573f0fd5f0c309242f96a053e8a226ff8692eb6bd9fef94c6e6647402',
              'core-mc1',
              '281.3',
              'core-mc1:qlippoth',
              ('Qlippoth', 'Augnagar (Hunger Qlippoth)'),
              (('^.creature', 2, None),
               ('Melee', 22, None),
               (None, None, 1),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('3d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:281.3:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '3d8+14 slashing plus 3d6 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '281.3',
                        'sectionId': 'core-mc1:qlippoth',
                        'contentPath': ['Qlippoth', 'Augnagar (Hunger Qlippoth)']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': 'Melee', 'pairIndex': 22},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:289.2:alchemical-grenade':
            expected_fields = (('persistent-source-field:289.2:1',
              'producer',
              'persistent-producer:289.2:alchemical-grenade',
              'Alchemical Grenades',
              'The grenadier carries 6 alchemical grenades that deal either acid, '
              'cold, or fire damage plus 2 persistent damage and 2 splash damage of '
              'the same type (typically two of each). The grenadier replenishes these '
              'each day using scavenged materials.',
              'b0c2de02fba453e18f4fc7835b4d151a679e3a2bd35f2c4d49e58eb0908c9695',
              'core-mc1',
              '289.2',
              'core-mc1:ratfolk',
              ('Ratfolk', 'Ratfolk Grenadier'),
              (('^.creature', 1, None),
               ('!.Alchemical Grenades', 14, None),
               ('Description', 0, None)),
              ('selected-immediate-type-acid-cold-or-fire-binds-'
               'persistent-and-splash-types',
               'ability-description-and-ranged-strike-are-one-corroborated-binding'),
              'strike-damage-descriptor',
              'corroborating-definition-no-separate-application',
              None,
              (('2',
                'selected-immediate-damage-type',
                'base',
                ('acid', 'cold', 'fire')),)),
             ('persistent-source-field:289.2:2',
              'producer',
              'persistent-producer:289.2:alchemical-grenade',
              'Ranged 1',
              '2d6 acid, cold, or fire plus 2 persistent damage and 2 splash damage of '
              'the same type',
              '34d8169a2cce27459289010fb746901ec123ce5c7fc1bbdd57226a7c1f47769e',
              'core-mc1',
              '289.2',
              'core-mc1:ratfolk',
              ('Ratfolk', 'Ratfolk Grenadier'),
              (('^.creature', 1, None),
               ('Ranged', 22, None),
               (None, None, 1),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2',
                'selected-immediate-damage-type',
                'base',
                ('acid', 'cold', 'fire')),)))
            payload = {'id': 'persistent-producer:289.2:alchemical-grenade',
             'kind': 'persistent-damage-producer',
             'name': 'Ranged 1',
             'sourceText': '2d6 acid, cold, or fire plus 2 persistent damage and 2 '
                           'splash damage of the same type',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'selected-immediate-damage-type',
                                   'allowedDamageTypes': ['acid', 'cold', 'fire']},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 2},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 2},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '289.2',
                        'sectionId': 'core-mc1:ratfolk',
                        'contentPath': ['Ratfolk', 'Ratfolk Grenadier']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Ranged', 'pairIndex': 22},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:290.1:stomp':
            expected_fields = (('persistent-source-field:290.1:1',
              'producer',
              'persistent-producer:290.1:stomp',
              'Stomp',
              'The redcap Strides up to half their Speed and makes a boot Strike at '
              'any point during that movement. If the boot Strike hits a prone '
              'creature, it deals an extra 2d6 persistent bleed damage.',
              'd9429f2195db6a2fc2705f9c4912371c41c2222bf465e5605e8a8f7f68c9c1cf',
              'core-mc1',
              '290.1',
              'core-mc1:redcap',
              (),
              (('Redcap', 1, None),
               ('Redcap', 0, None),
               ('^.creature', 3, None),
               ('!.Stomp', 26, None),
               ('Description', 1, None)),
              (),
              'conditional-hit-damage',
              'strike-hit-success-and-critical-scaling',
              None,
              (('2d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:290.1:stomp',
             'kind': 'persistent-damage-producer',
             'name': 'Stomp',
             'sourceText': 'The redcap Strides up to half their Speed and makes a boot '
                           'Strike at any point during that movement. If the boot '
                           'Strike hits a prone creature, it deals an extra 2d6 '
                           'persistent bleed damage.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'conditional-hit-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '290.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '290.1',
                        'sectionId': 'core-mc1:redcap',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Redcap', 'pairIndex': 1},
                                             {'rawKey': 'Redcap', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 3},
                                             {'rawKey': '!.Stomp', 'pairIndex': 26},
                                             {'rawKey': 'Description', 'pairIndex': 1}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:300.2:melee-1':
            expected_fields = (('persistent-source-field:300.2:1',
              'producer',
              'persistent-producer:300.2:melee-1',
              'Melee 1',
              '1d4+4 piercing plus 1d4 persistent bleed',
              '130ea390e4a83620f81795fd142b957d6a641d82cfdc136989e3082f467ac959',
              'core-mc1',
              '300.2',
              'core-mc1:sedacthy',
              ('Sedacthy', 'Sedacthy Scout'),
              (('^.creature', 1, None),
               ('Melee', 21, None),
               (None, None, 1),
               ('Damage', 2, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d4', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:300.2:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '1d4+4 piercing plus 1d4 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '300.2',
                        'sectionId': 'core-mc1:sedacthy',
                        'contentPath': ['Sedacthy', 'Sedacthy Scout']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 21},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:300.4:melee-1':
            expected_fields = (('persistent-source-field:300.4:1',
              'producer',
              'persistent-producer:300.4:melee-1',
              'Melee 1',
              '1d4+8 piercing plus 1d4 persistent bleed',
              '4c39c3a1990c535e563558a52adb5d2e33e0518216c4c9740906f83ecf741980',
              'core-mc1',
              '300.4',
              'core-mc1:sedacthy',
              ('Sedacthy', 'Sedacthy Marauder'),
              (('^.creature', 1, None),
               ('Melee', 22, None),
               (None, None, 1),
               ('Damage', 2, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d4', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:300.4:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '1d4+8 piercing plus 1d4 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '300.4',
                        'sectionId': 'core-mc1:sedacthy',
                        'contentPath': ['Sedacthy', 'Sedacthy Marauder']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 22},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:301.1:melee-1':
            expected_fields = (('persistent-source-field:301.1:1',
              'producer',
              'persistent-producer:301.1:melee-1',
              'Melee 1',
              '1d6+8 piercing plus 1d4 persistent bleed',
              '4c311acf9a9e48ef609079152acad71e40afba195f3b343c6ca364422bf9ec87',
              'core-mc1',
              '301.1',
              'core-mc1:sedacthy',
              ('Sedacthy', 'Sedacthy Speaker'),
              (('^.creature', 1, None),
               ('Melee', 22, None),
               (None, None, 1),
               ('Damage', 2, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d4', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:301.1:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '1d6+8 piercing plus 1d4 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '301.1',
                        'sectionId': 'core-mc1:sedacthy',
                        'contentPath': ['Sedacthy', 'Sedacthy Speaker']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 22},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 2}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:302.2:thin-of-blood':
            expected_fields = (('persistent-source-field:302.2:1',
              'producer',
              'persistent-producer:302.2:thin-of-blood',
              'Thin of Blood',
              'Zyss serpentfolk recover slowly from injuries. When they take physical '
              'damage from a critical hit, they gain 1d4 persistent bleed damage. They '
              'take a -2 circumstance penalty to flat checks to recover from '
              'persistent damage and saving throws against afflictions.',
              'e01ec6f2b1fd1d268082b645feaa4f3056c9df0ad7b2796b083c5347de962aad',
              'core-mc1',
              '302.2',
              'core-mc1:serpentfolk',
              ('Serpentfolk', 'Zyss Serpentfolk'),
              (('^.creature', 1, None),
               ('!.Thin of Blood', 15, None),
               ('Description', 0, None)),
              (
                  'minus-2-circumstance-penalty-to-recovery-flat-check-'
                  'is-a-specific-flat-check-exception',
              ),
              'critical-hit-damage-taken-trigger',
              'critical-trigger-source-amount-no-further-scaling',
              None,
              (('1d4', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:302.2:thin-of-blood',
             'kind': 'persistent-damage-producer',
             'name': 'Thin of Blood',
             'sourceText': 'Zyss serpentfolk recover slowly from injuries. When they '
                           'take physical damage from a critical hit, they gain 1d4 '
                           'persistent bleed damage. They take a -2 circumstance '
                           'penalty to flat checks to recover from persistent damage '
                           'and saving throws against afflictions.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'critical-hit-damage-taken-trigger',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '302.2'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [{'id': 'thin-of-blood-face-adjustment',
                                    'kind': 'flat-check-face-adjustment',
                                    'condition': 'thin-of-blood',
                                    'value': -2,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '302.2'}}],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '302.2',
                        'sectionId': 'core-mc1:serpentfolk',
                        'contentPath': ['Serpentfolk', 'Zyss Serpentfolk']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Thin of Blood',
                                              'pairIndex': 15},
                                             {'rawKey': 'Description', 'pairIndex': 0}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:308.1:melee-0':
            expected_fields = (('persistent-source-field:308.1:1',
              'producer',
              'persistent-producer:308.1:melee-0',
              'Melee 0',
              '3d4+5 bludgeoning plus 4d6 fire and 2d4 persistent fire',
              '0da025c319a109351a5d7283d39dfa782122707805b9e3a1ffd4f318dbda9c5b',
              'core-mc1',
              '308.1',
              'core-mc1:shining-child',
              (),
              (('Shining Child', 1, None),
               ('Shining Child', 0, None),
               ('^.creature', 1, None),
               ('Melee', 23, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2d4', 'fire', 'base', ()),)),)
            payload = {'id': 'persistent-producer:308.1:melee-0',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 0',
             'sourceText': '3d4+5 bludgeoning plus 4d6 fire and 2d4 persistent fire',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'fire'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '308.1',
                        'sectionId': 'core-mc1:shining-child',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Shining Child',
                                              'pairIndex': 1},
                                             {'rawKey': 'Shining Child',
                                              'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 23},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:327.2:tooth-tug':
            expected_fields = (('persistent-source-field:327.2:1',
              'producer',
              'persistent-producer:327.2:tooth-tug',
              'Tooth Tug',
              "The tooth fairy attempts a Thievery check against the creature's "
              'Fortitude DC, dealing 2 persistent bleed damage on any result but a '
              'critical failure. On a critical success, it also pulls out one of the '
              "target's teeth. If the creature loses a tooth, it takes a -1 status "
              'penalty to Charisma-based skill checks and must succeed at a DC 5 flat '
              'check to Cast a Spell unless that spell has the subtle trait. These '
              'effects last for 1 day, or until the stolen tooth is returned and the '
              'target regains at least 1 Hit Point.',
              '2556fb0e06d538cbd36d2291838fb07f5fb7d15ee781b6cd4921575829e09fc8',
              'core-mc1',
              '327.2',
              'core-mc1:tooth-fairy',
              ('Tooth Fairy', 'Tooth Fairy'),
              (('^.creature', 1, None),
               ('!.Tooth Tug', 24, None),
               ('Description', 3, None)),
              ('persistent-bleed-applies-on-every-check-result-except-critical-failure',
               'tooth-loss-effects-have-their-own-one-day-or-return-and-heal-ending'),
              'explicit-check-outcome',
              'source-defined-by-degree',
              None,
              (('2', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:327.2:tooth-tug',
             'kind': 'persistent-damage-producer',
             'name': 'Tooth Tug',
             'sourceText': 'The tooth fairy attempts a Thievery check against the '
                           "creature's Fortitude DC, dealing 2 persistent bleed damage "
                           'on any result but a critical failure. On a critical '
                           "success, it also pulls out one of the target's teeth. If "
                           'the creature loses a tooth, it takes a -1 status penalty '
                           'to Charisma-based skill checks and must succeed at a DC 5 '
                           'flat check to Cast a Spell unless that spell has the '
                           'subtle trait. These effects last for 1 day, or until the '
                           'stolen tooth is returned and the target regains at least 1 '
                           'Hit Point.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'explicit-check-outcome',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 2},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '327.2'}}}},
                          {'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 2},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '327.2'}}}},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 2},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '327.2'}}}},
                          {'degree': 'critical-failure',
                           'applies': False,
                           'amount': None}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [{'id': 'tooth-loss',
                                'lifecycle': 'independent-duration',
                                'description': 'Tooth loss lasts one day or until the '
                                               'tooth is returned and healed.'}],
             'source': {'sourceId': 'core-mc1',
                        'locator': '327.2',
                        'sectionId': 'core-mc1:tooth-fairy',
                        'contentPath': ['Tooth Fairy', 'Tooth Fairy']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Tooth Tug', 'pairIndex': 24},
                                             {'rawKey': 'Description', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:327.4:pry':
            expected_fields = (('persistent-source-field:327.4:1',
              'producer',
              'persistent-producer:327.4:pry',
              'Pry',
              "The tooth fairies try to pry out one of their target's teeth. One enemy "
              "in the swarm's space takes 4d6 bludgeoning damage with a DC 20 basic "
              'Reflex save. On a failed save, the target takes 2 persistent bleed '
              "damage and loses a tooth. This has the same effect as the tooth fairy's "
              'Tooth Tug.',
              '59e585430a1330651fc41f83e6732f928ad35d5ba5e6e0a5ed7410fac1fa9097',
              'core-mc1',
              '327.4',
              'core-mc1:tooth-fairy',
              ('Tooth Fairy', 'Tooth Fairy Swarm'),
              (('^.creature', 1, None), ('!.Pry', 23, None), ('Description', 1, None)),
              ('tooth-loss-effects-have-their-own-one-day-or-return-and-heal-ending',),
              'failed-save-rider',
              'failure-and-critical-failure-source-amount',
              None,
              (('2', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:327.4:pry',
             'kind': 'persistent-damage-producer',
             'name': 'Pry',
             'sourceText': "The tooth fairies try to pry out one of their target's "
                           "teeth. One enemy in the swarm's space takes 4d6 "
                           'bludgeoning damage with a DC 20 basic Reflex save. On a '
                           'failed save, the target takes 2 persistent bleed damage '
                           'and loses a tooth. This has the same effect as the tooth '
                           "fairy's Tooth Tug.",
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'failed-save-rider',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success', 'applies': False, 'amount': None},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 2},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '327.4'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 2},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '327.4'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [{'id': 'tooth-loss',
                                'lifecycle': 'independent-duration',
                                'description': 'Tooth loss lasts one day or until the '
                                               'tooth is returned and healed.'}],
             'source': {'sourceId': 'core-mc1',
                        'locator': '327.4',
                        'sectionId': 'core-mc1:tooth-fairy',
                        'contentPath': ['Tooth Fairy', 'Tooth Fairy Swarm']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Pry', 'pairIndex': 23},
                                             {'rawKey': 'Description', 'pairIndex': 1}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:340.1:bloodbird':
            expected_fields = (('persistent-source-field:340.1:1',
              'producer',
              'persistent-producer:340.1:bloodbird',
              'Bloodbird',
              "A creature hit by a vilderavn's melee attack becomes cursed. It takes "
              "2d6 persistent bleed damage that's difficult to stanch. The DC to stop "
              'the bleeding using Administer First Aid is 35, and healing the creature '
              "to full HP doesn't automatically end the bleeding. Removing the curse "
              'ends the bleeding.',
              '03ccaa89556c5fc309a866b7ffdd673b370e17b14a73232dbc19406cefcb1baa',
              'core-mc1',
              '340.1',
              'core-mc1:vilderavn',
              (),
              (('Vilderavn', 1, None),
               ('Vilderavn', 0, None),
               ('^.creature', 1, None),
               ('!.Bloodbird', 25, None),
               ('Description', 1, None)),
              ('administer-first-aid-medicine-dc-is-35',
               'full-hit-point-healing-does-not-end-this-bleed',
               'removing-the-curse-ends-this-contribution'),
              'conditional-hit-damage',
              'strike-hit-success-and-critical-scaling',
              None,
              (('2d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:340.1:bloodbird',
             'kind': 'persistent-damage-producer',
             'name': 'Bloodbird',
             'sourceText': "A creature hit by a vilderavn's melee attack becomes "
                           "cursed. It takes 2d6 persistent bleed damage that's "
                           'difficult to stanch. The DC to stop the bleeding using '
                           'Administer First Aid is 35, and healing the creature to '
                           "full HP doesn't automatically end the bleeding. Removing "
                           'the curse ends the bleeding.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'conditional-hit-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '340.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [{'id': 'bloodbird-first-aid-dc',
                                    'kind': 'medicine-dc-set',
                                    'condition': 'administer-first-aid',
                                    'value': 35,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '340.1'}},
                                   {'id': 'bloodbird-full-hp-suppression',
                                    'kind': 'full-hp-auto-end-suppressed',
                                    'condition': 'healed-to-full-hit-points',
                                    'value': None,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '340.1'}},
                                   {'id': 'remove-curse',
                                    'kind': 'automatic-source-end',
                                    'condition': 'remove-curse',
                                    'value': None,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '340.1'}}],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '340.1',
                        'sectionId': 'core-mc1:vilderavn',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Vilderavn', 'pairIndex': 1},
                                             {'rawKey': 'Vilderavn', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Bloodbird', 'pairIndex': 25},
                                             {'rawKey': 'Description', 'pairIndex': 1}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:40.3:blood-feast':
            expected_fields = (('persistent-source-field:40.3:1',
              'producer',
              'persistent-producer:40.3:blood-feast',
              'Blood Feast',
              'Each enemy in the bat swarm’s space takes 1d4 piercing damage (DC 16 '
              'basic Reflex save). Creatures that fail this save also take 1 '
              'persistent bleed damage.',
              '9ed282f5ddd9509ec0cd39106f42bbf94336a438aa57b085626819b86928b0df',
              'core-mc1',
              '40.3',
              'core-mc1:bat',
              ('Bat', 'Vampire Bat Swarm'),
              (('^.creature', 1, None),
               ('!.Blood Feast', 22, None),
               ('Description', 1, None)),
              (),
              'failed-save-rider',
              'failure-and-critical-failure-source-amount',
              None,
              (('1', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:40.3:blood-feast',
             'kind': 'persistent-damage-producer',
             'name': 'Blood Feast',
             'sourceText': 'Each enemy in the bat swarm’s space takes 1d4 piercing '
                           'damage (DC 16 basic Reflex save). Creatures that fail this '
                           'save also take 1 persistent bleed damage.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'failed-save-rider',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success', 'applies': False, 'amount': None},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 1},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '40.3'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'fixed', 'value': 1},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '40.3'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '40.3',
                        'sectionId': 'core-mc1:bat',
                        'contentPath': ['Bat', 'Vampire Bat Swarm']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Blood Feast',
                                              'pairIndex': 22},
                                             {'rawKey': 'Description', 'pairIndex': 1}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:46.1:bogwid-fever':
            expected_fields = (('persistent-source-field:46.1:2',
              'producer',
              'persistent-producer:46.1:bogwid-fever',
              'Bogwid Fever',
              '(disease); Saving Throw DC 20 Fortitude; Onset 1 day; Stage 1 enfeebled '
              '1 (1 day); Stage 2 enfeebled 2, and the DC to recover from persistent '
              'bleed is increased by 2 (1 day); Stage 3 enfeebled 3, and the DC to '
              'recover from persistent bleed is increased by 5 (1 day); Stage 4 '
              'enfeebled 4, the DC to recover from persistent bleed is increased by 5, '
              'and you take 1d8 persistent bleed damage every 1d4 hours (1 day)',
              '5177f15b02f8050e9336be127d2ae1b06253f5953826cfeece11ea0f1e7592ae',
              'core-mc1',
              '46.1',
              'core-mc1:bogwid',
              (),
              (('Bogwid', 1, None),
               ('Bogwid', 0, None),
               ('^.creature', 2, None),
               ('!.Bogwid Fever', 22, None)),
              ('stage-2-adds-2-to-persistent-bleed-recovery-dc',
               'stages-3-and-4-add-5-to-persistent-bleed-recovery-dc',
               'stage-4-reapplies-1d8-persistent-bleed-every-1d4-hours'),
              'affliction-stage-reapplication',
              'stage-entry-or-explicit-stage-cadence-source-amount',
              None,
              (('1d8', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:46.1:bogwid-fever',
             'kind': 'persistent-damage-producer',
             'name': 'Bogwid Fever',
             'sourceText': '(disease); Saving Throw DC 20 Fortitude; Onset 1 day; '
                           'Stage 1 enfeebled 1 (1 day); Stage 2 enfeebled 2, and the '
                           'DC to recover from persistent bleed is increased by 2 (1 '
                           'day); Stage 3 enfeebled 3, and the DC to recover from '
                           'persistent bleed is increased by 5 (1 day); Stage 4 '
                           'enfeebled 4, the DC to recover from persistent bleed is '
                           'increased by 5, and you take 1d8 persistent bleed damage '
                           'every 1d4 hours (1 day)',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'affliction-stage-reapplication',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'no-check',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '46.1'}}}}],
             'reapplication': {'mode': 'affliction-stage-cadence',
                               'intervalUnit': 'hour',
                               'intervalValue': None,
                               'intervalRoll': {'kind': 'dice',
                                                'dice': {'count': 1, 'sides': 4},
                                                'modifier': 0},
                               'statePredicate': 'affliction-stage-4-active'},
             'recoveryOverrides': [{'id': 'bogwid-fever-stage-2-dc',
                                    'kind': 'flat-check-dc-increase',
                                    'condition': 'bogwid-fever-stage-2',
                                    'value': 2,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '46.1'}},
                                   {'id': 'bogwid-fever-stages-3-4-dc',
                                    'kind': 'flat-check-dc-increase',
                                    'condition': 'bogwid-fever-stage-3-or-4',
                                    'value': 5,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '46.1'}}],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '46.1',
                        'sectionId': 'core-mc1:bogwid',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Bogwid', 'pairIndex': 1},
                                             {'rawKey': 'Bogwid', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': '!.Bogwid Fever',
                                              'pairIndex': 22}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'},
                       {'sourceId': 'core-pc1', 'locator': '430.7'},
                       {'sourceId': 'core-pc1', 'locator': '430.8'}]}
        elif binding_id == 'persistent-producer:46.1:ranged-0':
            expected_fields = (('persistent-source-field:46.1:1',
              'producer',
              'persistent-producer:46.1:ranged-0',
              'Ranged 0',
              '2d8 persistent bleed',
              'd471c85512b7654bedab47e62a7ff23b7875580ae27c7149108ea9e74f90f697',
              'core-mc1',
              '46.1',
              'core-mc1:bogwid',
              (),
              (('Bogwid', 1, None),
               ('Bogwid', 0, None),
               ('^.creature', 2, None),
               ('Ranged', 21, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('2d8', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:46.1:ranged-0',
             'kind': 'persistent-damage-producer',
             'name': 'Ranged 0',
             'sourceText': '2d8 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 8},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '46.1',
                        'sectionId': 'core-mc1:bogwid',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Bogwid', 'pairIndex': 1},
                                             {'rawKey': 'Bogwid', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': 'Ranged', 'pairIndex': 21},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:51.4:pierce-armor':
            expected_fields = (('persistent-source-field:51.4:1',
              'producer',
              'persistent-producer:51.4:pierce-armor',
              'Pierce Armor',
              "The smilodon makes a fangs Strike against a creature that's grabbed or "
              'restrained. If the attack hits, the creature is knocked prone; if the '
              'creature is wearing armor with Hardness 10 or lower, the armor is '
              "broken. If this Strike breaks a creature's armor or damages a creature "
              'who is unarmored or wearing broken armor, the creature also takes 2d6 '
              "persistent bleed damage. This Strike doesn't further damage armor "
              "that's already broken.",
              'c0d3d886f99e270228f6c2b79ca480b0c25e3b8bae40f2a56606903a5dbb5358',
              'core-mc1',
              '51.4',
              'core-mc1:cat',
              ('Cat', 'Smilodon'),
              (('^.creature', 1, None),
               ('!.Pierce Armor', 19, None),
               ('Description', 1, None)),
              (),
              'conditional-hit-damage',
              'strike-hit-success-and-critical-scaling',
              None,
              (('2d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:51.4:pierce-armor',
             'kind': 'persistent-damage-producer',
             'name': 'Pierce Armor',
             'sourceText': 'The smilodon makes a fangs Strike against a creature '
                           "that's grabbed or restrained. If the attack hits, the "
                           'creature is knocked prone; if the creature is wearing '
                           'armor with Hardness 10 or lower, the armor is broken. If '
                           "this Strike breaks a creature's armor or damages a "
                           'creature who is unarmored or wearing broken armor, the '
                           'creature also takes 2d6 persistent bleed damage. This '
                           "Strike doesn't further damage armor that's already broken.",
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'conditional-hit-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '51.4'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '51.4',
                        'sectionId': 'core-mc1:cat',
                        'contentPath': ['Cat', 'Smilodon']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Pierce Armor',
                                              'pairIndex': 19},
                                             {'rawKey': 'Description', 'pairIndex': 1}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:64.1:cast-out':
            expected_fields = (('persistent-source-field:64.1:1',
              'producer',
              'persistent-producer:64.1:cast-out',
              'Cast Out',
              'Failure The creature takes full damage and 3d6 persistent spirit '
              'damage. The persistent damage ends if the creature moves over 60 feet '
              'from the clay effigy or the effigy is destroyed.',
              '5d73ee67625101acd8407e3fe543a46bb403d5601464c12bf16f853b1abcb44e',
              'core-mc1',
              '64.1',
              'core-mc1:clay-effigy',
              (),
              (('Clay Effigy', 1, None),
               ('Clay Effigy', 0, None),
               ('^.creature', 3, None),
               ('!.Cast Out', 24, None),
               ('Description', 2, None),
               ('~.p', 3, None)),
              ('failure-applies-3d6-spirit',
               'critical-failure-applies-6d6-spirit',
               'moving-over-60-feet-from-source-or-source-destruction-'
               'ends-contribution'),
              'explicit-degree-outcome',
              'source-defined-by-degree',
              None,
              (('3d6', 'spirit', 'base', ()),)),
             ('persistent-source-field:64.1:2',
              'producer',
              'persistent-producer:64.1:cast-out',
              'Cast Out',
              'Critical Failure As failure, except the persistent damage is increased '
              'to 6d6.',
              '64e86aa843538320a5eb045899dd777f46933c8f483a17e69778026dc8631cd7',
              'core-mc1',
              '64.1',
              'core-mc1:clay-effigy',
              (),
              (('Clay Effigy', 1, None),
               ('Clay Effigy', 0, None),
               ('^.creature', 3, None),
               ('!.Cast Out', 24, None),
               ('Description', 2, None),
               ('~.p', 4, None)),
              ('failure-applies-3d6-spirit',
               'critical-failure-applies-6d6-spirit',
               'moving-over-60-feet-from-source-or-source-destruction-'
               'ends-contribution'),
              'explicit-degree-outcome',
              'source-defined-by-degree',
              None,
              (('6d6', 'spirit', 'critical-failure-override', ()),)))
            payload = {'id': 'persistent-producer:64.1:cast-out',
             'kind': 'persistent-damage-producer',
             'name': 'Cast Out',
             'sourceText': 'Failure The creature takes full damage and 3d6 persistent '
                           'spirit damage. The persistent damage ends if the creature '
                           'moves over 60 feet from the clay effigy or the effigy is '
                           'destroyed.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'explicit-degree-outcome',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'spirit'},
             'outcomes': [{'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 3, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '64.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 6, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '64.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [{'id': 'cast-out-distance-or-source-destruction',
                                    'kind': 'automatic-source-end',
                                    'condition': (
                                        'cast-out-distance-or-source-'
                                        'destruction'
                                    ),
                                    'value': None,
                                    'rule': {'sourceId': 'core-mc1',
                                             'locator': '64.1'}}],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '64.1',
                        'sectionId': 'core-mc1:clay-effigy',
                        'contentPath': []},
             'orderedPathFromSelectedNode': [{'rawKey': 'Clay Effigy', 'pairIndex': 1},
                                             {'rawKey': 'Clay Effigy', 'pairIndex': 0},
                                             {'rawKey': '^.creature', 'pairIndex': 3},
                                             {'rawKey': '!.Cast Out', 'pairIndex': 24},
                                             {'rawKey': 'Description', 'pairIndex': 2},
                                             {'rawKey': '~.p', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.4'}]}
        elif binding_id == 'persistent-producer:76.2:vicious-criticals':
            expected_fields = (('persistent-source-field:76.2:1',
              'producer',
              'persistent-producer:76.2:vicious-criticals',
              'Vicious Criticals',
              'A pusk makes the most of any weakness it finds. Whenever a pusk scores '
              'a critical hit with its claw Strike, the target takes an additional 1d6 '
              'persistent bleed damage.',
              '9676e97fbf687128aca89c7518f221abb9f861a5d0fcf411da08e08a7d572472',
              'core-mc1',
              '76.2',
              'core-mc1:demon',
              ('Demon', 'Pusk (Sloth Demon)'),
              (('^.creature', 2, None), ('!.Vicious Criticals', 25, None)),
              (),
              'critical-hit-trigger',
              'critical-hit-source-amount-no-further-scaling',
              None,
              (('1d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:76.2:vicious-criticals',
             'kind': 'persistent-damage-producer',
             'name': 'Vicious Criticals',
             'sourceText': 'A pusk makes the most of any weakness it finds. Whenever a '
                           'pusk scores a critical hit with its claw Strike, the '
                           'target takes an additional 1d6 persistent bleed damage.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'critical-hit-trigger',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '76.2'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '76.2',
                        'sectionId': 'core-mc1:demon',
                        'contentPath': ['Demon', 'Pusk (Sloth Demon)']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': '!.Vicious Criticals',
                                              'pairIndex': 25}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:80.1:gnawing-arms':
            expected_fields = (('persistent-source-field:80.1:3',
              'producer',
              'persistent-producer:80.1:gnawing-arms',
              'Gnawing Arms',
              'The seraptis’s arm mouths gnaw on those creatures, dealing each of them '
              '2d6+8 piercing damage with a DC 37 basic Fortitude save. Creatures that '
              'fail the save also take 2d6 persistent bleed damage.',
              '3a922ba342900f9951693d00bb63a659f1f5b42e9ca6b4aab717713f78782376',
              'core-mc1',
              '80.1',
              'core-mc1:demon',
              ('Demon', 'Seraptis (Suicide Demon)'),
              (('^.creature', 2, None),
               ('!.Gnawing Arms', 27, None),
               ('Description', 3, None)),
              (),
              'failed-save-rider',
              'failure-and-critical-failure-source-amount',
              None,
              (('2d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:80.1:gnawing-arms',
             'kind': 'persistent-damage-producer',
             'name': 'Gnawing Arms',
             'sourceText': 'The seraptis’s arm mouths gnaw on those creatures, dealing '
                           'each of them 2d6+8 piercing damage with a DC 37 basic '
                           'Fortitude save. Creatures that fail the save also take 2d6 '
                           'persistent bleed damage.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'failed-save-rider',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': False,
                           'amount': None},
                          {'degree': 'success', 'applies': False, 'amount': None},
                          {'degree': 'failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '80.1'}}}},
                          {'degree': 'critical-failure',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '80.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '80.1',
                        'sectionId': 'core-mc1:demon',
                        'contentPath': ['Demon', 'Seraptis (Suicide Demon)']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': '!.Gnawing Arms',
                                              'pairIndex': 27},
                                             {'rawKey': 'Description', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:80.1:melee-0':
            expected_fields = (('persistent-source-field:80.1:2',
              'producer',
              'persistent-producer:80.1:melee-0',
              'Melee 0',
              '2d6+16 slashing plus 2d6 mental and 1d6 persistent bleed',
              'f288e9cdb0315b99624a0f8480ed9a19d04d67b2809d6dbefae3e9d618892b6b',
              'core-mc1',
              '80.1',
              'core-mc1:demon',
              ('Demon', 'Seraptis (Suicide Demon)'),
              (('^.creature', 2, None),
               ('Melee', 23, None),
               (None, None, 0),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:80.1:melee-0',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 0',
             'sourceText': '2d6+16 slashing plus 2d6 mental and 1d6 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '80.1',
                        'sectionId': 'core-mc1:demon',
                        'contentPath': ['Demon', 'Seraptis (Suicide Demon)']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': 'Melee', 'pairIndex': 23},
                                             {'arrayIndex': 0},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:82.1:focused-flames':
            expected_fields = (('persistent-source-field:82.1:1',
              'producer',
              'persistent-producer:82.1:focused-flames',
              'Focused Flames',
              'Critical Success The target takes an additional 2d6 void damage for '
              'each knife beyond the first (typically 6d6 extra damage) and takes 4d6 '
              'persistent void damage.',
              '4b3d2117d015c4d1a29911777276f3c845933c294371a241e665fd646c870695',
              'core-mc1',
              '82.1',
              'core-mc1:demon',
              ('Demon', 'Vrolikai (Death Demon)'),
              (('^.creature', 2, None),
               ('!.Focused Flames', 26, None),
               ('Description', 1, None),
               ('~.p', 1, None)),
              (),
              'explicit-degree-outcome',
              'source-defined-by-degree',
              None,
              (('4d6', 'void', 'base', ()),)),)
            payload = {'id': 'persistent-producer:82.1:focused-flames',
             'kind': 'persistent-damage-producer',
             'name': 'Focused Flames',
             'sourceText': 'Critical Success The target takes an additional 2d6 void '
                           'damage for each knife beyond the first (typically 6d6 '
                           'extra damage) and takes 4d6 persistent void damage.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'explicit-degree-outcome',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'void'},
             'outcomes': [{'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 4, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '82.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '82.1',
                        'sectionId': 'core-mc1:demon',
                        'contentPath': ['Demon', 'Vrolikai (Death Demon)']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': '!.Focused Flames',
                                              'pairIndex': 26},
                                             {'rawKey': 'Description', 'pairIndex': 1},
                                             {'rawKey': '~.p', 'pairIndex': 1}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.3'}]}
        elif binding_id == 'persistent-producer:87.4:blood-contract':
            expected_fields = (('persistent-source-field:87.4:1',
              'producer',
              'persistent-producer:87.4:blood-contract',
              'Blood Contract',
              'When the coarti takes damage from their holy weakness, blood flows '
              'freely from their eyes and the contract carved into their skin. They '
              'take 1d6 persistent bleed damage and are dazzled as long as the '
              'persistent damage continues, but their Despairing Shriek recharges.',
              '4ba9490b067164583b668c5c54ca98ed2711568d082e3b3065749d485cb0c3d0',
              'core-mc1',
              '87.4',
              'core-mc1:devil',
              ('Devil', 'Coarti (Messenger Devil)'),
              (('^.creature', 2, None), ('!.Blood Contract', 22, None)),
              ('dazzled-is-linked-to-this-persistent-bleed',
               'trigger-recharges-despairing-shriek'),
              'damage-taken-trigger',
              'source-amount-without-degree-scaling',
              None,
              (('1d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:87.4:blood-contract',
             'kind': 'persistent-damage-producer',
             'name': 'Blood Contract',
             'sourceText': 'When the coarti takes damage from their holy weakness, '
                           'blood flows freely from their eyes and the contract carved '
                           'into their skin. They take 1d6 persistent bleed damage and '
                           'are dazzled as long as the persistent damage continues, '
                           'but their Despairing Shriek recharges.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'damage-taken-trigger',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'no-check',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '87.4'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [{'id': 'blood-contract-dazzled',
                                'lifecycle': 'while-contribution-active',
                                'description': 'Dazzled while this persistent bleed '
                                               'continues.'},
                               {'id': 'despairing-shriek-recharge',
                                'lifecycle': 'on-application',
                                'description': 'Recharge Despairing Shriek when Blood '
                                               'Contract triggers.'}],
             'source': {'sourceId': 'core-mc1',
                        'locator': '87.4',
                        'sectionId': 'core-mc1:devil',
                        'contentPath': ['Devil', 'Coarti (Messenger Devil)']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 2},
                                             {'rawKey': '!.Blood Contract',
                                              'pairIndex': 22}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:97.2:melee-1':
            expected_fields = (('persistent-source-field:97.2:1',
              'producer',
              'persistent-producer:97.2:melee-1',
              'Melee 1',
              '1d6+3 slashing plus 1d4 persistent bleed',
              '7e445a074cc820d865e999fcc5f768c1974135ca32307bc244f3c91a433ad68e',
              'core-mc1',
              '97.2',
              'core-mc1:dinosaur',
              ('Dinosaur', 'Deinonychus'),
              (('^.creature', 1, None),
               ('Melee', 18, None),
               (None, None, 1),
               ('Damage', 3, None)),
              (),
              'strike-damage',
              'strike-base-success-and-critical-scaling',
              None,
              (('1d4', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:97.2:melee-1',
             'kind': 'persistent-damage-producer',
             'name': 'Melee 1',
             'sourceText': '1d6+3 slashing plus 1d4 persistent bleed',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'strike-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 1, 'sides': 4},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '97.2',
                        'sectionId': 'core-mc1:dinosaur',
                        'contentPath': ['Dinosaur', 'Deinonychus']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': 'Melee', 'pairIndex': 18},
                                             {'arrayIndex': 1},
                                             {'rawKey': 'Damage', 'pairIndex': 3}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        elif binding_id == 'persistent-producer:99.5:vicious-gore':
            expected_fields = (('persistent-source-field:99.5:1',
              'producer',
              'persistent-producer:99.5:vicious-gore',
              'Vicious Gore',
              'A triceratops deals 2d6 extra persistent bleed damage to prone targets '
              'it hits with its horns.',
              'cacea51cf43833100a717f3e176bbe73e22af2c30e7cedd362fdd92720b22c34',
              'core-mc1',
              '99.5',
              'core-mc1:dinosaur',
              ('Dinosaur', 'Triceratops'),
              (('^.creature', 1, None), ('!.Vicious Gore', 22, None)),
              (),
              'conditional-hit-damage',
              'strike-hit-success-and-critical-scaling',
              None,
              (('2d6', 'bleed', 'base', ()),)),)
            payload = {'id': 'persistent-producer:99.5:vicious-gore',
             'kind': 'persistent-damage-producer',
             'name': 'Vicious Gore',
             'sourceText': 'A triceratops deals 2d6 extra persistent bleed damage to '
                           'prone targets it hits with its horns.',
             'supported': True,
             'effectType': 'persistent-damage',
             'delivery': 'conditional-hit-damage',
             'damageTypeBinding': {'mode': 'fixed', 'damageType': 'bleed'},
             'outcomes': [{'degree': 'success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 1,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-mc1',
                                                         'locator': '99.5'}}}},
                          {'degree': 'critical-success',
                           'applies': True,
                           'amount': {'expression': {'kind': 'dice',
                                                     'dice': {'count': 2, 'sides': 6},
                                                     'modifier': 0},
                                      'scale': {'numerator': 2,
                                                'denominator': 1,
                                                'rule': {'sourceId': 'core-pc1',
                                                         'locator': '407.1'}}}}],
             'reapplication': {'mode': 'none',
                               'intervalUnit': None,
                               'intervalValue': None,
                               'intervalRoll': None,
                               'statePredicate': None},
             'recoveryOverrides': [],
             'linkedEffects': [],
             'source': {'sourceId': 'core-mc1',
                        'locator': '99.5',
                        'sectionId': 'core-mc1:dinosaur',
                        'contentPath': ['Dinosaur', 'Triceratops']},
             'orderedPathFromSelectedNode': [{'rawKey': '^.creature', 'pairIndex': 1},
                                             {'rawKey': '!.Vicious Gore',
                                              'pairIndex': 22}],
             'rules': [{'sourceId': 'core-pc1', 'locator': '406.2'},
                       {'sourceId': 'core-pc1', 'locator': '407.1'},
                       {'sourceId': 'core-pc1', 'locator': '400.1'},
                       {'sourceId': 'core-pc1', 'locator': '436.3'},
                       {'sourceId': 'core-pc1', 'locator': '445.4'},
                       {'sourceId': 'core-pc1', 'locator': '409.7'}]}
        else:
            return None
        if actual_fields != expected_fields:
            return None
        if active_path_overlay is not None:
            payload["orderedPathFromSelectedNode"] = [
                (
                    {"rawKey": raw_key, "pairIndex": pair_index}
                    if raw_key is not None
                    else {"arrayIndex": array_index}
                )
                for raw_key, pair_index, array_index in current_path
            ]
        return payload


def _validate_binding_context(
    context: object,
) -> None:
    if type(context) is not PersistentDamageBindingContext:
        raise TypeError(
            "binding authentication requires the exact context type"
        )
    try:
        PersistentDamageBindingContext.__post_init__(context)
    except (AttributeError, TypeError, ValueError) as failure:
        raise TypeError(
            "persistent binding context is structurally invalid"
        ) from failure




def source_field_from_census(
    selected: Mapping[str, Any],
    occurrence: Mapping[str, Any],
) -> PersistentDamageSourceField:
    """Convert one validated census occurrence into immutable compiler input."""

    if type(selected) is not dict or type(occurrence) is not dict:
        raise TypeError(
            "census source field inputs must be exact dicts"
        )
    selected = copy_persistent_damage_json(
        copy_persistent_damage_json(
            selected,
            freeze=True,
            label="selected census source",
        ),
        freeze=False,
        label="selected census source snapshot",
    )
    occurrence = copy_persistent_damage_json(
        copy_persistent_damage_json(
            occurrence,
            freeze=True,
            label="census occurrence",
        ),
        freeze=False,
        label="census occurrence snapshot",
    )
    if set(selected) != {
        "source_id",
        "locator",
        "section_id",
        "content_path",
        "title",
    }:
        raise ValueError(
            "selected census source has missing or unknown fields"
        )
    _require_trimmed_string(
        selected.get("title"),
        "selected census source title",
    )
    content_path = selected.get("content_path")
    if not isinstance(content_path, (list, tuple)):
        raise TypeError(
            "selected census content_path must be ordered"
        )
    kind = occurrence.get("kind")
    producer_fields = {
        "id",
        "kind",
        "owner",
        "orderedPathFromSelectedNode",
        "sourceText",
        "sourceTextSha256",
        "specialRules",
        "producerBindingId",
        "delivery",
        "degreePolicy",
        "damageMentions",
    }
    modifier_fields = {
        "id",
        "kind",
        "owner",
        "orderedPathFromSelectedNode",
        "sourceText",
        "sourceTextSha256",
        "specialRules",
        "modifierKind",
    }
    expected_fields = (
        producer_fields
        if kind == "producer"
        else modifier_fields
        if kind == "modifier-only"
        else None
    )
    if expected_fields is None or set(occurrence) != expected_fields:
        raise ValueError(
            "census occurrence has missing or unknown fields"
        )
    ordered_path = occurrence.get("orderedPathFromSelectedNode")
    special_rules = occurrence.get("specialRules")
    if not isinstance(ordered_path, (list, tuple)):
        raise TypeError(
            "census occurrence ordered path must be ordered"
        )
    if not isinstance(special_rules, (list, tuple)):
        raise TypeError(
            "census occurrence special rules must be ordered"
        )
    damage_mentions = occurrence.get("damageMentions", ())
    if not isinstance(damage_mentions, (list, tuple)):
        raise TypeError(
            "census occurrence damage mentions must be ordered"
        )
    owner = occurrence.get("owner")
    locator = selected.get("locator")
    binding_id = occurrence.get("producerBindingId")
    if kind == "modifier-only":
        binding_id = (
            f"persistent-modifier:{locator}:{_slug(str(owner or ''))}"
        )
    return PersistentDamageSourceField(
        occurrence_id=occurrence.get("id"),
        kind=kind,
        binding_id=binding_id,
        owner=owner,
        source_text=occurrence.get("sourceText"),
        source_text_sha256=occurrence.get("sourceTextSha256"),
        source_id=selected.get("source_id"),
        locator=locator,
        section_id=selected.get("section_id"),
        content_path=tuple(content_path),
        ordered_path=tuple(
            OrderedSourcePathStep.from_serialized(item)
            for item in ordered_path
        ),
        special_rules=tuple(special_rules),
        delivery=occurrence.get("delivery"),
        degree_policy=occurrence.get("degreePolicy"),
        modifier_kind=occurrence.get("modifierKind"),
        expected_mentions=tuple(
            PersistentDamageMentionExpectation.from_serialized(item)
            for item in damage_mentions
        ),
    )


def _parse_bounded_decimal(
    value: object,
    /,
    *,
    decimal_parser=parse_decimal_integer,
    maximum=MAX_SOURCE_INTEGER,
) -> int | None:
    """Use the shared conversion and retain an explicit local source bound."""

    if not isinstance(value, str):
        return None
    unsigned = value[1:] if value.startswith(("+", "-")) else value
    if not unsigned or len(unsigned) > 19:
        return None
    parsed = decimal_parser(value)
    if (
        parsed is None
        or parsed < -maximum
        or parsed > maximum
    ):
        return None
    return parsed


def _parse_damage_expression(
    source_expression: str,
    /,
    *,
    DICE_AMOUNT_RE=DICE_AMOUNT_RE,
    _parse_bounded_decimal=_parse_bounded_decimal,
    MAX_PERSISTENT_DAMAGE_DICE_COUNT=(
        MAX_PERSISTENT_DAMAGE_DICE_COUNT
    ),
    MAX_PERSISTENT_DAMAGE_DIE_SIDES=MAX_PERSISTENT_DAMAGE_DIE_SIDES,
) -> Mapping[str, Any] | None:
    dice_match = DICE_AMOUNT_RE.fullmatch(source_expression)
    if dice_match is None:
        value = _parse_bounded_decimal(source_expression)
        if value is None or value <= 0:
            return None
        return {
            "kind": "fixed",
            "value": value,
        }
    count = _parse_bounded_decimal(dice_match.group("count"))
    sides = _parse_bounded_decimal(dice_match.group("sides"))
    modifier = _parse_bounded_decimal(
        dice_match.group("modifier") or "0"
    )
    if (
        count is None
        or count <= 0
        or count > MAX_PERSISTENT_DAMAGE_DICE_COUNT
        or sides is None
        or sides < 2
        or sides > MAX_PERSISTENT_DAMAGE_DIE_SIDES
        or modifier is None
    ):
        return None
    return {
        "kind": "dice",
        "dice": {
            "count": count,
            "sides": sides,
        },
        "modifier": modifier,
    }


def parse_persistent_damage_amount(
    value: object,
) -> dict[str, Any] | None:
    """Parse exactly one narrow ``amount persistent type`` component."""

    if not isinstance(value, str):
        return None
    match = PERSISTENT_MENTION_RE.fullmatch(value)
    if match is None or match.group("damage_type") is None:
        return None
    expression = _parse_damage_expression(
        match.group("amount").casefold()
    )
    if expression is None:
        return None
    return {
        "damageType": match.group("damage_type").casefold(),
        "expression": copy_persistent_damage_json(
            expression,
            freeze=False,
            label="parsed persistent-damage expression",
        ),
    }




def validate_compiled_persistent_damage_record(
    record: object,
    /,
) -> tuple[dict[str, Any], PersistentDamageBindingContext]:
    """Invoke the record's self-contained structural validator."""

    if type(record) not in {
        CompiledPersistentDamageProducer,
        CompiledPersistentDamageModifier,
    }:
        raise TypeError(
            "compiled persistent record requires an exact record type"
        )
    return record.validate()


class _CompiledPersistentDamageRecord:
    __slots__ = ("_payload", "_source_fields")

    expected_kind = ""

    def __init__(
        self,
        payload: dict[str, Any],
        source_fields: tuple[PersistentDamageSourceField, ...],
    ) -> None:
        if type(self) not in {
            CompiledPersistentDamageProducer,
            CompiledPersistentDamageModifier,
        }:
            raise TypeError(
                "compiled persistent record subclasses are not accepted"
            )
        if type(payload) is not dict:
            raise TypeError(
                "compiled persistent payload must be one exact dict"
            )
        if type(source_fields) is not tuple or not source_fields:
            raise TypeError(
                "compiled persistent source receipt must be a non-empty "
                "tuple"
            )
        object.__setattr__(
            self,
            "_payload",
            copy_persistent_damage_json(
                payload,
                freeze=True,
                label="compiled persistent payload",
            ),
        )
        object.__setattr__(self, "_source_fields", source_fields)
        self.validate()

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise FrozenInstanceError(
            "cannot assign to a compiled persistent record"
        )

    def validate(
        self,
    ) -> tuple[dict[str, Any], PersistentDamageBindingContext]:
        if type(self) not in {
            CompiledPersistentDamageProducer,
            CompiledPersistentDamageModifier,
        }:
            raise TypeError(
                "compiled persistent record requires an exact record type"
            )
        payload = getattr(self, "_payload", None)
        source_fields = getattr(self, "_source_fields", None)
        mapping_proxy_type = type(MappingProxyType({}))
        if type(payload) is not mapping_proxy_type:
            raise TypeError(
                "compiled persistent record payload is not a frozen snapshot"
            )
        if type(source_fields) is not tuple or not source_fields:
            raise TypeError(
                "compiled persistent source receipt must be a non-empty tuple"
            )
        try:
            context = PersistentDamageBindingContext(source_fields)
        except (AttributeError, TypeError, ValueError) as failure:
            raise TypeError(
                "compiled persistent source receipt is structurally invalid"
            ) from failure
        expected = context.canonical_compiled_payload()
        if expected is None:
            raise ValueError(
                "compiled persistent source receipt is not a reviewed binding"
            )
        expected_kind = (
            "persistent-damage-producer"
            if type(self) is CompiledPersistentDamageProducer
            else "persistent-damage-modifier"
        )
        if expected.get("kind") != expected_kind:
            raise ValueError(
                "compiled persistent record type disagrees with its source"
            )

        active: set[int] = set()
        nodes = 0
        recursively_frozen = True

        def thaw(item: Any, depth: int) -> Any:
            nonlocal nodes, recursively_frozen
            if depth > 64:
                raise ValueError(
                    "compiled persistent record exceeds the JSON depth bound"
                )
            nodes += 1
            if nodes > 100_000:
                raise ValueError(
                    "compiled persistent record exceeds the JSON node bound"
                )
            item_type = type(item)
            if item_type in {dict, mapping_proxy_type}:
                if item_type is dict:
                    recursively_frozen = False
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "compiled persistent record contains a JSON cycle"
                    )
                active.add(identity)
                try:
                    copied = {}
                    for key, child in item.items():
                        if type(key) is not str:
                            raise TypeError(
                                "compiled persistent record keys must be "
                                "strings"
                            )
                        copied[key] = thaw(child, depth + 1)
                finally:
                    active.remove(identity)
                return copied
            if item_type in {list, tuple}:
                if item_type is list:
                    recursively_frozen = False
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "compiled persistent record contains a JSON cycle"
                    )
                active.add(identity)
                try:
                    return [
                        thaw(child, depth + 1)
                        for child in item
                    ]
                finally:
                    active.remove(identity)
            if item is None or item_type in {bool, int, str}:
                return item
            raise TypeError(
                "compiled persistent record contains a non-JSON value"
            )

        current = thaw(payload, 0)
        if not recursively_frozen:
            raise TypeError(
                "compiled persistent record is not a recursively frozen "
                "snapshot"
            )

        def exact_json_equal(left: Any, right: Any) -> bool:
            if type(left) is not type(right):
                return False
            if type(left) is dict:
                return (
                    len(left) == len(right)
                    and all(
                        key in right
                        and exact_json_equal(value, right[key])
                        for key, value in left.items()
                    )
                )
            if type(left) is list:
                return (
                    len(left) == len(right)
                    and all(
                        exact_json_equal(left_item, right_item)
                        for left_item, right_item in zip(left, right)
                    )
                )
            return left == right

        if not exact_json_equal(current, expected):
            raise ValueError(
                "compiled persistent record differs from canonical source "
                "derivation"
            )
        return current, context

    @property
    def payload(self) -> Mapping[str, Any]:
        current, _context = self.validate()
        active: set[int] = set()
        nodes = 0

        def freeze(item: Any, depth: int) -> Any:
            nonlocal nodes
            if depth > 64:
                raise ValueError(
                    "compiled persistent record exceeds the JSON depth bound"
                )
            nodes += 1
            if nodes > 100_000:
                raise ValueError(
                    "compiled persistent record exceeds the JSON node bound"
                )
            item_type = type(item)
            if item_type is dict:
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "compiled persistent record contains a JSON cycle"
                    )
                active.add(identity)
                try:
                    copied = {
                        key: freeze(child, depth + 1)
                        for key, child in item.items()
                    }
                finally:
                    active.remove(identity)
                return MappingProxyType(copied)
            if item_type is list:
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "compiled persistent record contains a JSON cycle"
                    )
                active.add(identity)
                try:
                    return tuple(
                        freeze(child, depth + 1)
                        for child in item
                    )
                finally:
                    active.remove(identity)
            if item is None or item_type in {bool, int, str}:
                return item
            raise TypeError(
                "compiled persistent record contains a non-JSON value"
            )

        frozen = freeze(current, 0)
        if type(frozen) is not type(MappingProxyType({})):
            raise TypeError(
                "compiled persistent record did not produce a mapping"
            )
        return frozen

    @property
    def source_fields(
        self,
    ) -> tuple[PersistentDamageSourceField, ...]:
        self.validate()
        return self._source_fields

    @property
    def id(self) -> str:
        current, _context = self.validate()
        return str(current["id"])

    def as_serialized(self) -> dict[str, Any]:
        current, _context = self.validate()
        return current


class CompiledPersistentDamageProducer(_CompiledPersistentDamageRecord):
    """Canonical compile result for one unique producer binding."""

    __slots__ = ()
    expected_kind = "persistent-damage-producer"

    @property
    def delivery_classes(self) -> tuple[str, ...]:
        _current, context = self.validate()
        return tuple(
            source_field.delivery
            for source_field in context.fields
            if source_field.delivery is not None
        )


class CompiledPersistentDamageModifier(_CompiledPersistentDamageRecord):
    """Canonical compile result for one modifier-only source field."""

    __slots__ = ()
    expected_kind = "persistent-damage-modifier"


def compile_persistent_damage_producer(
    source: object,
    /,
) -> CompiledPersistentDamageProducer | None:
    """Compile one complete literal-reviewed producer binding."""

    if type(source) is not PersistentDamageBindingContext:
        return None
    payload = source.canonical_compiled_payload()
    if (
        payload is None
        or payload.get("kind") != "persistent-damage-producer"
    ):
        return None
    return CompiledPersistentDamageProducer(payload, source.fields)


def compile_persistent_damage_modifier(
    source: object,
    /,
) -> CompiledPersistentDamageModifier | None:
    """Compile one complete literal-reviewed modifier binding."""

    if type(source) is not PersistentDamageBindingContext:
        return None
    payload = source.canonical_compiled_payload()
    if (
        payload is None
        or payload.get("kind") != "persistent-damage-modifier"
    ):
        return None
    return CompiledPersistentDamageModifier(payload, source.fields)


def canonical_persistent_damage_mechanic(
    source: object,
    /,
) -> dict[str, Any] | None:
    """Return the exact local patch mechanic for one reviewed source."""

    if type(source) is not PersistentDamageBindingContext:
        return None
    payload = source.canonical_compiled_payload()
    if payload is None:
        return None
    kind = payload.get("kind")
    if kind == "persistent-damage-producer":
        mechanic_type = "persistent-damage-producer"
    elif kind == "persistent-damage-modifier":
        mechanic_type = "persistent-damage-modifier"
    else:
        return None
    return {
        "type": mechanic_type,
        "compiledSource": payload,
    }


def validate_persistent_damage_compiler_patch(
    patch: object,
    /,
) -> tuple[
    PersistentDamageBindingContext,
    dict[str, Any],
    RuleReference,
]:
    """Invoke the patch's self-contained structural validator."""

    if type(patch) is not PersistentDamageCompilerPatch:
        raise TypeError(
            "compiler patch validation requires the exact patch type"
        )
    return patch.validate()


class PersistentDamageCompilerPatch:
    """Canonical local patch for one reviewed multi-field source binding."""

    __slots__ = ("_source", "_mechanic", "_rule")

    def __init__(
        self,
        source: PersistentDamageBindingContext,
        mechanic: dict[str, Any],
        rule: RuleReference,
    ) -> None:
        if type(self) is not PersistentDamageCompilerPatch:
            raise TypeError(
                "PersistentDamageCompilerPatch subclasses are not accepted"
            )
        if type(mechanic) is not dict:
            raise TypeError(
                "persistent compiler patch mechanic must be one exact dict"
            )
        object.__setattr__(self, "_source", source)
        object.__setattr__(
            self,
            "_mechanic",
            copy_persistent_damage_json(
                mechanic,
                freeze=True,
                label="persistent compiler patch mechanic",
            ),
        )
        object.__setattr__(self, "_rule", rule)
        self.validate()

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise FrozenInstanceError(
            "cannot assign to a persistent-damage compiler patch"
        )

    def validate(
        self,
    ) -> tuple[
        PersistentDamageBindingContext,
        dict[str, Any],
        RuleReference,
    ]:
        if type(self) is not PersistentDamageCompilerPatch:
            raise TypeError(
                "compiler patch validation requires the exact patch type"
            )
        source = getattr(self, "_source", None)
        mechanic = getattr(self, "_mechanic", None)
        rule = getattr(self, "_rule", None)
        if type(source) is not PersistentDamageBindingContext:
            raise TypeError(
                "persistent compiler patch source is structurally invalid"
            )
        payload = source.canonical_compiled_payload()
        if payload is None:
            raise ValueError(
                "persistent compiler patch source is not a canonical binding"
            )
        mechanic_type = payload.get("kind")
        if mechanic_type not in {
            "persistent-damage-producer",
            "persistent-damage-modifier",
        }:
            raise ValueError(
                "persistent compiler patch source has an invalid kind"
            )
        expected_mechanic = {
            "type": mechanic_type,
            "compiledSource": payload,
        }
        mapping_proxy_type = type(MappingProxyType({}))
        if type(mechanic) is not mapping_proxy_type:
            raise TypeError(
                "persistent compiler patch mechanic is not a frozen snapshot"
            )

        active: set[int] = set()
        nodes = 0
        recursively_frozen = True

        def thaw(item: Any, depth: int) -> Any:
            nonlocal nodes, recursively_frozen
            if depth > 64:
                raise ValueError(
                    "persistent compiler patch exceeds the JSON depth bound"
                )
            nodes += 1
            if nodes > 100_000:
                raise ValueError(
                    "persistent compiler patch exceeds the JSON node bound"
                )
            item_type = type(item)
            if item_type in {dict, mapping_proxy_type}:
                if item_type is dict:
                    recursively_frozen = False
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "persistent compiler patch contains a JSON cycle"
                    )
                active.add(identity)
                try:
                    copied = {}
                    for key, child in item.items():
                        if type(key) is not str:
                            raise TypeError(
                                "persistent compiler patch keys must be "
                                "strings"
                            )
                        copied[key] = thaw(child, depth + 1)
                finally:
                    active.remove(identity)
                return copied
            if item_type in {list, tuple}:
                if item_type is list:
                    recursively_frozen = False
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "persistent compiler patch contains a JSON cycle"
                    )
                active.add(identity)
                try:
                    return [
                        thaw(child, depth + 1)
                        for child in item
                    ]
                finally:
                    active.remove(identity)
            if item is None or item_type in {bool, int, str}:
                return item
            raise TypeError(
                "persistent compiler patch contains a non-JSON value"
            )

        current_mechanic = thaw(mechanic, 0)
        if not recursively_frozen:
            raise TypeError(
                "persistent compiler patch is not a recursively frozen "
                "snapshot"
            )

        def exact_json_equal(left: Any, right: Any) -> bool:
            if type(left) is not type(right):
                return False
            if type(left) is dict:
                return (
                    len(left) == len(right)
                    and all(
                        key in right
                        and exact_json_equal(value, right[key])
                        for key, value in left.items()
                    )
                )
            if type(left) is list:
                return (
                    len(left) == len(right)
                    and all(
                        exact_json_equal(left_item, right_item)
                        for left_item, right_item in zip(left, right)
                    )
                )
            return left == right

        if not exact_json_equal(current_mechanic, expected_mechanic):
            raise ValueError(
                "persistent compiler patch differs from canonical source "
                "derivation"
            )
        expected_rule = RuleReference(
            source.fields[0].source_id,
            source.fields[0].locator,
        )
        if (
            type(rule) is not RuleReference
            or type(rule.source_id) is not str
            or type(rule.locator) is not str
            or rule.source_id != expected_rule.source_id
            or rule.locator != expected_rule.locator
        ):
            raise ValueError(
                "persistent compiler patch rule changed source identity"
            )
        return source, current_mechanic, expected_rule

    @property
    def source(self) -> PersistentDamageBindingContext:
        source, _mechanic, _rule = self.validate()
        return source

    @property
    def mechanic(self) -> Mapping[str, Any]:
        _source, mechanic, _rule = self.validate()
        active: set[int] = set()
        nodes = 0

        def freeze(item: Any, depth: int) -> Any:
            nonlocal nodes
            if depth > 64:
                raise ValueError(
                    "persistent compiler patch exceeds the JSON depth bound"
                )
            nodes += 1
            if nodes > 100_000:
                raise ValueError(
                    "persistent compiler patch exceeds the JSON node bound"
                )
            item_type = type(item)
            if item_type is dict:
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "persistent compiler patch contains a JSON cycle"
                    )
                active.add(identity)
                try:
                    copied = {
                        key: freeze(child, depth + 1)
                        for key, child in item.items()
                    }
                finally:
                    active.remove(identity)
                return MappingProxyType(copied)
            if item_type is list:
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "persistent compiler patch contains a JSON cycle"
                    )
                active.add(identity)
                try:
                    return tuple(
                        freeze(child, depth + 1)
                        for child in item
                    )
                finally:
                    active.remove(identity)
            if item is None or item_type in {bool, int, str}:
                return item
            raise TypeError(
                "persistent compiler patch contains a non-JSON value"
            )

        frozen = freeze(mechanic, 0)
        if type(frozen) is not type(MappingProxyType({})):
            raise TypeError(
                "persistent compiler patch did not produce a mapping"
            )
        return frozen

    @property
    def rule(self) -> RuleReference:
        _source, _mechanic, rule = self.validate()
        return rule

    @property
    def mechanic_type(self) -> str:
        _source, mechanic, _rule = self.validate()
        return str(mechanic["type"])

    def as_serialized(self) -> dict[str, Any]:
        _source, mechanic, rule = self.validate()
        return {
            "mechanic": mechanic,
            "rule": RuleReference.as_serialized(rule),
        }


def compile_persistent_damage_producer_patch(
    source: object,
    /,
) -> PersistentDamageCompilerPatch | None:
    """Adapt the canonical producer value to a local patch."""

    if type(source) is not PersistentDamageBindingContext:
        return None
    payload = source.canonical_compiled_payload()
    if (
        payload is None
        or payload.get("kind") != "persistent-damage-producer"
    ):
        return None
    return PersistentDamageCompilerPatch(
        source,
        {
            "type": "persistent-damage-producer",
            "compiledSource": payload,
        },
        RuleReference(
            source.fields[0].source_id,
            source.fields[0].locator,
        ),
    )


def compile_persistent_damage_modifier_patch(
    source: object,
    /,
) -> PersistentDamageCompilerPatch | None:
    """Adapt the canonical modifier value to a local patch."""

    if type(source) is not PersistentDamageBindingContext:
        return None
    payload = source.canonical_compiled_payload()
    if (
        payload is None
        or payload.get("kind") != "persistent-damage-modifier"
    ):
        return None
    return PersistentDamageCompilerPatch(
        source,
        {
            "type": "persistent-damage-modifier",
            "compiledSource": payload,
        },
        RuleReference(
            source.fields[0].source_id,
            source.fields[0].locator,
        ),
    )


def validate_persistent_damage_compiler_registration(
    registration: object,
    /,
) -> tuple[str, str, str]:
    """Invoke the registration's self-contained structural validator."""

    if type(registration) is not PersistentDamageCompilerRegistration:
        raise TypeError(
            "persistent-damage registration requires the exact type"
        )
    return registration.validate()


class PersistentDamageCompilerRegistration:
    """One complete structurally reviewed unregistered compiler value."""

    __slots__ = ("_compiler_id", "_source_kind", "_mechanic_type")

    def __init__(
        self,
        compiler_id: str,
        source_kind: str,
        mechanic_type: str,
    ) -> None:
        if type(self) is not PersistentDamageCompilerRegistration:
            raise TypeError(
                "PersistentDamageCompilerRegistration subclasses are not "
                "accepted"
            )
        object.__setattr__(self, "_compiler_id", compiler_id)
        object.__setattr__(self, "_source_kind", source_kind)
        object.__setattr__(self, "_mechanic_type", mechanic_type)
        self.validate()

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise FrozenInstanceError(
            "cannot assign to a persistent-damage registration"
        )

    def validate(self) -> tuple[str, str, str]:
        if type(self) is not PersistentDamageCompilerRegistration:
            raise TypeError(
                "persistent-damage registration requires the exact type"
            )
        current = (
            getattr(self, "_compiler_id", None),
            getattr(self, "_source_kind", None),
            getattr(self, "_mechanic_type", None),
        )
        if any(type(value) is not str for value in current):
            raise TypeError(
                "persistent-damage registration fields must be exact strings"
            )
        if current not in (
            (
                "persistent-damage-producer-source",
                "producer",
                "persistent-damage-producer",
            ),
            (
                "persistent-damage-modifier-source",
                "modifier-only",
                "persistent-damage-modifier",
            ),
        ):
            raise ValueError(
                "persistent-damage registration is not in the immutable "
                "reviewed specification"
            )
        return current

    @property
    def compiler_id(self) -> str:
        compiler_id, _source_kind, _mechanic_type = self.validate()
        return compiler_id

    @property
    def source_kind(self) -> str:
        _compiler_id, source_kind, _mechanic_type = self.validate()
        return source_kind

    @property
    def mechanic_type(self) -> str:
        _compiler_id, _source_kind, mechanic_type = self.validate()
        return mechanic_type

    def match(
        self,
        source: object,
        /,
    ) -> PersistentDamageCompilerPatch | None:
        compiler_id, source_kind, mechanic_type = self.validate()
        if type(source) is not PersistentDamageBindingContext:
            return None
        payload = source.canonical_compiled_payload()
        if (
            payload is None
            or source.kind != source_kind
            or payload.get("kind") != mechanic_type
        ):
            return None
        patch = PersistentDamageCompilerPatch(
            source,
            {
                "type": mechanic_type,
                "compiledSource": payload,
            },
            RuleReference(
                source.fields[0].source_id,
                source.fields[0].locator,
            ),
        )
        patch_source, mechanic, _rule = patch.validate()
        if (
            patch_source != source
            or mechanic.get("type") != mechanic_type
        ):
            raise ValueError(
                f"persistent-damage compiler {compiler_id!r} changed its "
                "reviewed source or mechanic"
            )
        return patch


class PersistentDamageCompilerAmbiguityError(ValueError):
    """More than one ordered structured-binding compiler accepted a source."""


def match_persistent_damage_compilers(
    source: object,
    registrations: list[PersistentDamageCompilerRegistration]
    | tuple[PersistentDamageCompilerRegistration, ...],
    /,
) -> PersistentDamageCompilerPatch | None:
    """Return the sole structured-binding match with zero/one/many semantics."""

    if type(registrations) not in {list, tuple}:
        raise TypeError(
            "persistent-damage compiler registrations must be ordered"
        )
    matches: list[tuple[str, PersistentDamageCompilerPatch]] = []
    for registration in registrations:
        if type(registration) is not PersistentDamageCompilerRegistration:
            raise TypeError(
                "persistent-damage compiler registrations contain an "
                "invalid value"
            )
        registration.validate()
        patch = registration.match(source)
        if patch is not None:
            matches.append((registration.compiler_id, patch))
    if len(matches) > 1:
        compiler_ids = ", ".join(repr(item[0]) for item in matches)
        raise PersistentDamageCompilerAmbiguityError(
            "multiple persistent-damage compilers matched in registration "
            f"order: {compiler_ids}"
        )
    return matches[0][1] if matches else None


def validate_persistent_damage_family_fragment(
    fragment: object,
    /,
) -> tuple[
    str,
    tuple[str, ...],
    tuple[PersistentDamageCompilerRegistration, ...],
]:
    """Invoke the fragment's self-contained structural validator."""

    if type(fragment) is not PersistentDamageFamilyFragment:
        raise TypeError(
            "persistent-damage family fragment requires the exact type"
        )
    return fragment.validate()


class PersistentDamageFamilyFragment:
    """Unregistered canonical family metadata."""

    __slots__ = ("_family_id", "_mechanic_types", "_source_compilers")

    def __init__(
        self,
        family_id: str,
        mechanic_types: tuple[str, ...],
        source_compilers: tuple[
            PersistentDamageCompilerRegistration,
            ...,
        ],
    ) -> None:
        if type(self) is not PersistentDamageFamilyFragment:
            raise TypeError(
                "PersistentDamageFamilyFragment subclasses are not accepted"
            )
        object.__setattr__(self, "_family_id", family_id)
        object.__setattr__(self, "_mechanic_types", mechanic_types)
        object.__setattr__(self, "_source_compilers", source_compilers)
        self.validate()

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise FrozenInstanceError(
            "cannot assign to a persistent-damage family fragment"
        )

    def validate(
        self,
    ) -> tuple[
        str,
        tuple[str, ...],
        tuple[PersistentDamageCompilerRegistration, ...],
    ]:
        if type(self) is not PersistentDamageFamilyFragment:
            raise TypeError(
                "persistent-damage family fragment requires the exact type"
            )
        family_id = getattr(self, "_family_id", None)
        mechanic_types = getattr(self, "_mechanic_types", None)
        source_compilers = getattr(self, "_source_compilers", None)
        if (
            type(family_id) is not str
            or type(mechanic_types) is not tuple
            or type(source_compilers) is not tuple
            or any(
                type(mechanic_type) is not str
                for mechanic_type in mechanic_types
            )
        ):
            raise TypeError(
                "persistent-damage family fragment collections must be tuples"
            )
        registrations = []
        for registration in source_compilers:
            if type(registration) is not (
                PersistentDamageCompilerRegistration
            ):
                raise TypeError(
                    "persistent-damage family fragment contains an invalid "
                    "registration"
                )
            registrations.append(registration.validate())
        current = (
            family_id,
            mechanic_types,
            tuple(item[0] for item in registrations),
        )
        if current != (
            "persistent-damage",
            (
                "persistent-damage-producer",
                "persistent-damage-modifier",
            ),
            (
                "persistent-damage-producer-source",
                "persistent-damage-modifier-source",
            ),
        ):
            raise ValueError(
                "persistent-damage family fragment differs from the "
                "immutable reviewed specification"
            )
        return family_id, mechanic_types, source_compilers

    @property
    def family_id(self) -> str:
        family_id, _mechanic_types, _source_compilers = self.validate()
        return family_id

    @property
    def mechanic_types(self) -> tuple[str, ...]:
        _family_id, mechanic_types, _source_compilers = self.validate()
        return mechanic_types

    @property
    def source_compilers(
        self,
    ) -> tuple[PersistentDamageCompilerRegistration, ...]:
        _family_id, _mechanic_types, source_compilers = self.validate()
        return source_compilers


FRAGMENT = PersistentDamageFamilyFragment(
    "persistent-damage",
    ("persistent-damage-producer", "persistent-damage-modifier"),
    (
        PersistentDamageCompilerRegistration(
            "persistent-damage-producer-source",
            "producer",
            "persistent-damage-producer",
        ),
        PersistentDamageCompilerRegistration(
            "persistent-damage-modifier-source",
            "modifier-only",
            "persistent-damage-modifier",
        ),
    ),
)


__all__ = [
    "CompiledPersistentDamageModifier",
    "CompiledPersistentDamageProducer",
    "DELIVERY_DEGREE_POLICIES",
    "FRAGMENT",
    "MAX_PERSISTENT_DAMAGE_DICE_COUNT",
    "MAX_PERSISTENT_DAMAGE_DIE_SIDES",
    "MODIFIER_MECHANIC_TYPE",
    "OrderedSourcePathStep",
    "PERSISTENT_DAMAGE_DELIVERIES",
    "PERSISTENT_DAMAGE_MODIFIER_KINDS",
    "PERSISTENT_DAMAGE_TYPES",
    "PRODUCER_MECHANIC_TYPE",
    "PersistentDamageBindingContext",
    "PersistentDamageCompilerAmbiguityError",
    "PersistentDamageCompilerPatch",
    "PersistentDamageCompilerRegistration",
    "PersistentDamageFamilyFragment",
    "PersistentDamageMentionExpectation",
    "PersistentDamageSourceField",
    "canonical_persistent_damage_mechanic",
    "compile_persistent_damage_modifier",
    "compile_persistent_damage_modifier_patch",
    "compile_persistent_damage_producer",
    "compile_persistent_damage_producer_patch",
    "copy_persistent_damage_json",
    "match_persistent_damage_compilers",
    "parse_persistent_damage_amount",
    "source_field_from_census",
    "validate_compiled_persistent_damage_record",
    "validate_persistent_damage_compiler_patch",
    "validate_persistent_damage_compiler_registration",
    "validate_persistent_damage_family_fragment",
]

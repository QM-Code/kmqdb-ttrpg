"""Compile the bounded Core MC1 ``Immunities`` source family.

This module is intentionally compile-only.  It authenticates one exact
``Immunities`` member through the source-authority adapter, preserves
the authored scalar/array shape, order, and duplicates, and classifies every
token without registering any runtime behavior.

Only an unqualified token that names one currently reviewed pure damage type
is emitted as a supported damage predicate.  Composite damage/trait
immunities, special damage semantics, conditions, effect families, linked
rules, and source-qualified forms remain typed deferrals.  In particular,
``mental`` and ``poison`` are not narrowed to damage-only immunity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal, TypeAlias

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
)
from .source_authority import (
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)


FAMILY_ID = "damage-immunities"
MECHANIC_TYPE = "damage-immunity"
MONSTER_CORE_SOURCE_ID = "core-mc1"

MAX_SIGNED_64 = (1 << 63) - 1
MAX_CARRIER_MEMBERS = 256
MAX_IMMUNITY_TOKENS = 256
MAX_TOKEN_BYTES = 4_096
MAX_CREATURE_NAME_BYTES = 4_096

SupportStatus: TypeAlias = Literal["supported", "deferred"]
ImmunityKind: TypeAlias = Literal[
    "damage-type",
    "damage-and-effect-trait",
    "persistent-damage",
    "precision-damage",
    "critical-hit",
    "nonlethal-source",
    "damage-delivery",
    "condition",
    "effect-family",
    "named-rule",
    "qualified-damage",
    "complex-effect",
    "printed-example-placeholder",
    "unclassified",
]


class DamageImmunityCompileError(ValueError):
    """The selected source cannot be compiled losslessly."""


@dataclass(frozen=True, slots=True)
class _TokenSpec:
    support: SupportStatus
    kind: ImmunityKind
    normalized_term: str
    provider_rule_ids: tuple[str, ...]
    damage_type: str | None
    page_reference: int | None
    deferred_dependency: str | None


def _require_exact_text(
    value: object,
    label: str,
    *,
    maximum_bytes: int,
    trimmed: bool,
) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise DamageImmunityCompileError(
            f"{label} must be a non-empty string without NUL"
        )
    if trimmed and value != value.strip():
        raise DamageImmunityCompileError(f"{label} must be trimmed")
    if len(value.encode("utf-8")) > maximum_bytes:
        raise DamageImmunityCompileError(f"{label} exceeds its byte bound")
    return value


def _require_signed64_ordinal(
    value: object,
    label: str,
    _maximum: int = (1 << 63) - 1,
) -> int:
    if type(value) is not int or value < 0 or value > _maximum:
        raise DamageImmunityCompileError(
            f"{label} must be an integer from 0 through {_maximum}"
        )
    return value


def _canonical_positive_integer(
    value: str,
    label: str,
    _maximum: int = (1 << 63) - 1,
) -> int:
    if not value or (len(value) > 1 and value.startswith("0")):
        raise DamageImmunityCompileError(
            f"{label} must be a canonical positive integer"
        )
    if len(value) > len(str(_maximum)) or (
        len(value) == len(str(_maximum))
        and value > str(_maximum)
    ):
        raise DamageImmunityCompileError(f"{label} exceeds signed-64")
    result = int(value)
    if result < 1:
        raise DamageImmunityCompileError(f"{label} must be positive")
    return result


def _reviewed_rule_requirements(
    needs_damage_types: bool,
    _rule_type: type[RuleRequirement] = RuleRequirement,
) -> tuple[RuleRequirement, ...]:
    """Rebuild the reviewed provider pins from local immutable literals."""

    if type(needs_damage_types) is not bool:
        raise TypeError("needs_damage_types must be exact bool")
    requirements = (
        _rule_type(
            rule_id="pc1-immunity",
            source_id="core-pc1",
            locator="408.2",
            expected_selection_sha256=(
                "d7df47027e4560e84fbd5931fdbb6637b9ed1dd2c1cbbc413d7034254a25d531"
            ),
        ),
    )
    if needs_damage_types:
        requirements += (
            _rule_type(
                rule_id="pc1-damage-types",
                source_id="core-pc1",
                locator="409.1",
                expected_selection_sha256=(
                    "b5e918eb06281d4b10f2a3f157110a16e86f31b85fa6efab2e9c9b6bfbf64200"
                ),
            ),
        )
    return requirements


def _canonical_token_spec(
    source_text: str,
    _spec_type: type[_TokenSpec] = _TokenSpec,
    _require_text: Any = _require_exact_text,
    _parse_positive: Any = _canonical_positive_integer,
    _swarm_mind_pattern: re.Pattern[str] = re.compile(
        r"swarm mind \(page (?P<page>[0-9]+)\)",
        flags=re.ASCII,
    ),
) -> _TokenSpec:
    """Derive the only permitted disposition from one exact source token."""

    _require_text(
        source_text,
        "immunity source token",
        maximum_bytes=4_096,
        trimmed=False,
    )
    if not source_text.strip():
        raise DamageImmunityCompileError(
            "immunity source token is effectively empty"
        )

    pure_damage_types = (
        "acid",
        "bludgeoning",
        "cold",
        "electricity",
        "fire",
        "slashing",
        "sonic",
        "spirit",
        "vitality",
        "void",
    )
    conditions = (
        "blinded",
        "confused",
        "controlled",
        "dazzled",
        "doomed",
        "drained",
        "fascinated",
        "fatigued",
        "grabbed",
        "off-guard",
        "paralyzed",
        "petrified",
        "prone",
        "restrained",
        "sickened",
        "unconscious",
    )
    effect_families = (
        "curse",
        "death effects",
        "disease",
        "emotion",
        "fear",
        "fortune",
        "healing",
        "magic",
        "misfortune",
        "petrification",
        "polymorph",
        "possession",
        "sleep",
        "visual",
    )
    immunity_rule = ("pc1-immunity",)
    immunity_and_damage_rules = (
        "pc1-immunity",
        "pc1-damage-types",
    )

    if source_text in pure_damage_types:
        return _spec_type(
            support="supported",
            kind="damage-type",
            normalized_term=source_text,
            provider_rule_ids=immunity_and_damage_rules,
            damage_type=source_text,
            page_reference=None,
            deferred_dependency=None,
        )
    if source_text in ("mental", "poison"):
        return _spec_type(
            support="deferred",
            kind="damage-and-effect-trait",
            normalized_term=source_text,
            provider_rule_ids=immunity_and_damage_rules,
            damage_type=source_text,
            page_reference=None,
            deferred_dependency="trait-bearing-effect-immunity",
        )
    if source_text == "bleed":
        return _spec_type(
            support="deferred",
            kind="persistent-damage",
            normalized_term=source_text,
            provider_rule_ids=immunity_and_damage_rules,
            damage_type="bleed",
            page_reference=None,
            deferred_dependency="persistent-bleed-immunity",
        )
    if source_text == "precision":
        return _spec_type(
            support="deferred",
            kind="precision-damage",
            normalized_term=source_text,
            provider_rule_ids=immunity_and_damage_rules,
            damage_type="precision",
            page_reference=None,
            deferred_dependency="precision-component-immunity",
        )
    if source_text == "critical hits":
        return _spec_type(
            support="deferred",
            kind="critical-hit",
            normalized_term="critical-hit",
            provider_rule_ids=immunity_rule,
            damage_type=None,
            page_reference=None,
            deferred_dependency="critical-hit-immunity-resolution",
        )
    if source_text == "nonlethal attacks":
        return _spec_type(
            support="deferred",
            kind="nonlethal-source",
            normalized_term="nonlethal",
            provider_rule_ids=immunity_rule,
            damage_type=None,
            page_reference=None,
            deferred_dependency="nonlethal-source-immunity",
        )
    if source_text == "area damage":
        return _spec_type(
            support="deferred",
            kind="damage-delivery",
            normalized_term="area-damage",
            provider_rule_ids=immunity_rule,
            damage_type=None,
            page_reference=None,
            deferred_dependency="area-damage-source-provenance",
        )
    if source_text in conditions:
        return _spec_type(
            support="deferred",
            kind="condition",
            normalized_term=source_text,
            provider_rule_ids=immunity_rule,
            damage_type=None,
            page_reference=None,
            deferred_dependency="condition-immunity-lifecycle",
        )
    if source_text in effect_families:
        return _spec_type(
            support="deferred",
            kind="effect-family",
            normalized_term=source_text,
            provider_rule_ids=immunity_rule,
            damage_type=None,
            page_reference=None,
            deferred_dependency="effect-family-and-trait-provenance",
        )

    swarm_mind = _swarm_mind_pattern.fullmatch(source_text)
    if swarm_mind is not None:
        return _spec_type(
            support="deferred",
            kind="named-rule",
            normalized_term="swarm-mind",
            provider_rule_ids=immunity_rule,
            damage_type=None,
            page_reference=_parse_positive(
                swarm_mind.group("page"),
                "swarm mind page reference",
            ),
            deferred_dependency="monster-core-swarm-mind-provider",
        )
    if source_text == "ward contract":
        return _spec_type(
            support="deferred",
            kind="named-rule",
            normalized_term=source_text,
            provider_rule_ids=immunity_rule,
            damage_type=None,
            page_reference=None,
            deferred_dependency="ward-contract-source-link",
        )
    if source_text == "electricity (see lightning drinker)":
        return _spec_type(
            support="deferred",
            kind="qualified-damage",
            normalized_term="electricity",
            provider_rule_ids=immunity_rule,
            damage_type="electricity",
            page_reference=None,
            deferred_dependency="lightning-drinker-qualified-immunity",
        )
    if (
        source_text
        == "effects that would transform their body or soul to an undead"
    ):
        return _spec_type(
            support="deferred",
            kind="complex-effect",
            normalized_term="undead-transformation",
            provider_rule_ids=immunity_rule,
            damage_type=None,
            page_reference=None,
            deferred_dependency="body-and-soul-transformation-immunity",
        )
    if (
        source_text
        == "Any immunities, weaknesses, or resistances are listed here."
    ):
        return _spec_type(
            support="deferred",
            kind="printed-example-placeholder",
            normalized_term="printed-stat-block-example",
            provider_rule_ids=immunity_rule,
            damage_type=None,
            page_reference=None,
            deferred_dependency="non-creature-example-exclusion",
        )
    return _spec_type(
        support="deferred",
        kind="unclassified",
        normalized_term=source_text.strip(),
        provider_rule_ids=immunity_rule,
        damage_type=None,
        page_reference=None,
        deferred_dependency="unreviewed-immunity-token",
    )


def _receipt(
    value: object,
    label: str,
    _receipt_type: type[SourceReceipt] = SourceReceipt,
) -> SourceReceipt:
    if type(value) is not _receipt_type:
        raise TypeError(f"{label} must be an exact SourceReceipt")
    _receipt_type.as_serialized(value)
    return value


def _receipt_bytes(
    value: object,
    label: str,
    _encode: Any = canonical_json_bytes,
) -> bytes:
    receipt = _receipt(value, label)
    return _encode(SourceReceipt.as_serialized(receipt))


def _requirement_bytes(
    value: object,
    label: str,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _encode: Any = canonical_json_bytes,
) -> bytes:
    if type(value) is not _requirement_type:
        raise TypeError(f"{label} must be an exact RuleRequirement")
    return _encode(_requirement_type.as_serialized(value))


def _validate_token(
    value: object,
    _derive_spec: Any = _canonical_token_spec,
    _requirements: Any = _reviewed_rule_requirements,
) -> DamageImmunityToken:
    if type(value) is not DamageImmunityToken:
        raise TypeError("damage immunity token must be exact")
    if type(value.authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "DamageImmunityToken.authority must be an exact "
            "SourceAuthorityAdapter"
        )
    if type(value.consumer) is not VerifiedSourceSelection:
        raise TypeError(
            "DamageImmunityToken.consumer must be an exact "
            "VerifiedSourceSelection"
        )
    if (
        type(value.provider_rules) is not tuple
        or not value.provider_rules
        or any(
            type(rule) is not VerifiedRuleReceipt
            for rule in value.provider_rules
        )
    ):
        raise TypeError(
            "DamageImmunityToken.provider_rules must contain exact "
            "verified rules"
        )
    value.authority.require_shared_authority(
        value.consumer,
        value.provider_rules,
    )
    # ``require_shared_authority`` publicly re-resolves the consumer and every
    # provider before returning; retain that exact already-validated view.
    verified = value.consumer
    _require_signed64_ordinal(
        value.ordinal,
        "DamageImmunityToken.ordinal",
    )
    spec = _derive_spec(value.source_text)
    source = _receipt(value.source, "DamageImmunityToken.source")
    if _receipt_bytes(
        source,
        "DamageImmunityToken.source",
    ) != _receipt_bytes(
        verified.receipt,
        "DamageImmunityToken.consumer.receipt",
    ):
        raise DamageImmunityCompileError(
            "damage immunity token receipt disagrees with its "
            "verified consumer"
        )
    if (
        type(verified.raw_value) is not str
        or verified.raw_value != value.source_text
    ):
        raise DamageImmunityCompileError(
            "damage immunity token text disagrees with its "
            "authenticated source token"
        )
    address = source.address
    if (
        address.source_id != "core-mc1"
        or address.span is not None
        or not address.carrier_path
        or len(address.selection_path) not in (1, 2)
        or (
            len(address.target_path)
            + len(address.carrier_path)
            + len(address.selection_path)
            > 256
        )
    ):
        raise DamageImmunityCompileError(
            "damage immunity token source is not a Core MC1 field item"
        )
    carrier_tail = address.carrier_path[-1]
    field_step = address.selection_path[0]
    if (
        type(carrier_tail) is not RawMemberStep
        or carrier_tail.raw_key != "^.creature"
        or type(field_step) is not RawMemberStep
        or field_step.raw_key != "Immunities"
    ):
        raise DamageImmunityCompileError(
            "damage immunity token source is not an Immunities member"
        )
    if len(address.selection_path) == 1:
        if value.ordinal != 0:
            raise DamageImmunityCompileError(
                "scalar immunity token ordinal must be zero"
            )
    else:
        item_step = address.selection_path[1]
        if (
            type(item_step) is not RawIndexStep
            or item_step.item_ordinal != value.ordinal
        ):
            raise DamageImmunityCompileError(
                "array immunity token source ordinal disagrees"
            )
    if (
        type(value.support) is not str
        or type(value.kind) is not str
        or type(value.normalized_term) is not str
        or type(value.provider_rule_ids) is not tuple
        or any(
            type(rule_id) is not str
            for rule_id in value.provider_rule_ids
        )
        or (
            value.damage_type is not None
            and type(value.damage_type) is not str
        )
        or (
            value.page_reference is not None
            and type(value.page_reference) is not int
        )
        or (
            value.deferred_dependency is not None
            and type(value.deferred_dependency) is not str
        )
    ):
        raise TypeError(
            "damage immunity token fields must use exact canonical types"
        )
    actual = (
        value.support,
        value.kind,
        value.normalized_term,
        value.provider_rule_ids,
        value.damage_type,
        value.page_reference,
        value.deferred_dependency,
    )
    expected = (
        spec.support,
        spec.kind,
        spec.normalized_term,
        spec.provider_rule_ids,
        spec.damage_type,
        spec.page_reference,
        spec.deferred_dependency,
    )
    if actual != expected:
        raise DamageImmunityCompileError(
            "damage immunity token disagrees with its canonical source text"
        )
    requirements = _requirements(
        "pc1-damage-types" in spec.provider_rule_ids
    )
    if (
        tuple(rule.rule_id for rule in value.provider_rules)
        != spec.provider_rule_ids
        or tuple(
            _requirement_bytes(
                rule.requirement,
                "DamageImmunityToken provider requirement",
            )
            for rule in value.provider_rules
        )
        != tuple(
            _requirement_bytes(
                requirement,
                "reviewed damage immunity requirement",
            )
            for requirement in requirements
        )
    ):
        raise DamageImmunityCompileError(
            "damage immunity token providers disagree with exact "
            "reviewed requirements"
        )
    return value


@dataclass(frozen=True, slots=True)
class DamageImmunityToken:
    """One exact authored immunity token and its compile disposition."""

    ordinal: int
    source_text: str
    support: SupportStatus
    kind: ImmunityKind
    normalized_term: str
    authority: SourceAuthorityAdapter = field(
        repr=False,
        compare=False,
    )
    consumer: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )
    provider_rules: tuple[VerifiedRuleReceipt, ...] = field(
        repr=False,
        compare=False,
    )
    source: SourceReceipt
    provider_rule_ids: tuple[str, ...]
    damage_type: str | None = None
    page_reference: int | None = None
    deferred_dependency: str | None = None

    def __post_init__(self) -> None:
        _validate_token(self)

    def as_serialized(self) -> dict[str, Any]:
        _validate_token(self)
        result: dict[str, Any] = {
            "ordinal": self.ordinal,
            "sourceText": self.source_text,
            "support": self.support,
            "kind": self.kind,
            "normalizedTerm": self.normalized_term,
            "consumerSource": self.source.as_serialized(),
            "providerRuleIds": list(self.provider_rule_ids),
            "providerRules": [
                rule.as_serialized() for rule in self.provider_rules
            ],
        }
        if self.damage_type is not None:
            result["damageType"] = self.damage_type
        if self.page_reference is not None:
            result["pageReference"] = self.page_reference
        if self.deferred_dependency is not None:
            result["deferredDependency"] = self.deferred_dependency
        if self.support == "supported":
            result["mechanic"] = {
                "type": "damage-immunity",
                "predicate": {
                    "kind": "exact-damage-type",
                    "damageType": self.damage_type,
                },
            }
        return result


@dataclass(frozen=True, slots=True)
class DamageImmunityPatch:
    """Lossless compile-only result for one exact source field."""

    source_id: str
    locator: str
    creature_name: str
    field_shape: Literal["scalar", "array"]
    authority: SourceAuthorityAdapter = field(
        repr=False,
        compare=False,
    )
    consumer: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )
    creature_name_selection: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )
    field_source: SourceReceipt
    creature_name_source: SourceReceipt
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    tokens: tuple[DamageImmunityToken, ...]

    def __post_init__(self) -> None:
        _validate_patch(self)

    @property
    def supported_tokens(self) -> tuple[DamageImmunityToken, ...]:
        _validate_patch(self)
        return tuple(
            token for token in self.tokens
            if token.support == "supported"
        )

    @property
    def deferred_tokens(self) -> tuple[DamageImmunityToken, ...]:
        _validate_patch(self)
        return tuple(
            token for token in self.tokens
            if token.support == "deferred"
        )

    def as_serialized(self) -> dict[str, Any]:
        _validate_patch(self)
        supported_count = sum(
            token.support == "supported" for token in self.tokens
        )
        deferred_count = len(self.tokens) - supported_count
        return {
            "family": "damage-immunities",
            "mechanicType": "damage-immunity",
            "sourceId": self.source_id,
            "locator": self.locator,
            "creatureName": self.creature_name,
            "field": "Immunities",
            "fieldShape": self.field_shape,
            "consumerSources": {
                "field": self.field_source.as_serialized(),
                "creatureName": self.creature_name_source.as_serialized(),
            },
            "providerRules": [
                rule.as_serialized() for rule in self.provider_rules
            ],
            "tokens": [token.as_serialized() for token in self.tokens],
            "runtime": {
                "status": "not-registered",
                "supportedPredicateCount": supported_count,
                "deferredTokenCount": deferred_count,
            },
        }


def _validate_authority_bundle(
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
    providers: tuple[VerifiedRuleReceipt, ...],
) -> None:
    """Use only the authority layer's public exact-object validators."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("damage immunity authority adapter must be exact")
    if type(consumer) is not VerifiedSourceSelection:
        raise TypeError("damage immunity consumer must be exact")
    if (
        type(providers) is not tuple
        or not providers
        or any(type(rule) is not VerifiedRuleReceipt for rule in providers)
    ):
        raise TypeError("damage immunity providers must be exact")
    authority.require_shared_authority(consumer, providers)


def _provider_rules(
    authority: SourceAuthorityAdapter,
    source_texts: tuple[str, ...],
    _requirements: Any = _reviewed_rule_requirements,
    _derive_spec: Any = _canonical_token_spec,
) -> tuple[VerifiedRuleReceipt, ...]:
    if type(source_texts) is not tuple or not source_texts or any(
        type(source_text) is not str
        for source_text in source_texts
    ):
        raise TypeError(
            "damage immunity provider resolution requires exact source text"
        )
    needs_damage_types = any(
        "pc1-damage-types" in _derive_spec(source_text).provider_rule_ids
        for source_text in source_texts
    )
    requirements = _requirements(needs_damage_types)
    result = tuple(
        authority.resolve_rule(requirement)
        for requirement in requirements
    )
    return result


def _classify_token(
    source_text: str,
    ordinal: int,
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
    available_provider_rules: tuple[VerifiedRuleReceipt, ...],
    _derive_spec: Any = _canonical_token_spec,
) -> DamageImmunityToken:
    spec = _derive_spec(source_text)
    provider_rules = tuple(
        rule
        for rule in available_provider_rules
        if rule.rule_id in spec.provider_rule_ids
    )
    return DamageImmunityToken(
        ordinal=ordinal,
        source_text=source_text,
        support=spec.support,
        kind=spec.kind,
        normalized_term=spec.normalized_term,
        authority=authority,
        consumer=consumer,
        provider_rules=provider_rules,
        source=consumer.receipt,
        provider_rule_ids=spec.provider_rule_ids,
        damage_type=spec.damage_type,
        page_reference=spec.page_reference,
        deferred_dependency=spec.deferred_dependency,
    )


def _exact_member_indexes(
    raw_block: RawSourceObject,
    raw_key: str,
) -> tuple[int, ...]:
    return tuple(
        index
        for index, member in enumerate(raw_block.members)
        if type(member) is RawSourceMember and member.key == raw_key
    )


def _validate_patch(
    value: object,
    _requirements: Any = _reviewed_rule_requirements,
) -> DamageImmunityPatch:
    """Re-derive every public field from authenticated source selections."""

    if type(value) is not DamageImmunityPatch:
        raise TypeError("damage immunity patch must be exact")
    if type(value.source_id) is not str or value.source_id != "core-mc1":
        raise DamageImmunityCompileError(
            "DamageImmunityPatch.source_id must be core-mc1"
        )
    _require_exact_text(
        value.locator,
        "DamageImmunityPatch.locator",
        maximum_bytes=4_096,
        trimmed=True,
    )
    _require_exact_text(
        value.creature_name,
        "DamageImmunityPatch.creature_name",
        maximum_bytes=4_096,
        trimmed=True,
    )
    if (
        type(value.field_shape) is not str
        or value.field_shape not in ("scalar", "array")
    ):
        raise DamageImmunityCompileError(
            "DamageImmunityPatch.field_shape is invalid"
        )
    if type(value.consumer) is not VerifiedSourceSelection:
        raise TypeError("DamageImmunityPatch.consumer must be exact")
    if type(value.creature_name_selection) is not VerifiedSourceSelection:
        raise TypeError(
            "DamageImmunityPatch.creature_name_selection must be exact"
        )
    if type(value.tokens) is not tuple or not value.tokens or any(
        type(token) is not DamageImmunityToken
        for token in value.tokens
    ):
        raise TypeError(
            "DamageImmunityPatch.tokens must contain exact tokens"
        )
    if len(value.tokens) > 256:
        raise DamageImmunityCompileError(
            "DamageImmunityPatch.tokens exceed their count bound"
        )

    _validate_authority_bundle(
        value.authority,
        value.consumer,
        value.provider_rules,
    )
    value.authority.validate_selection(value.creature_name_selection)
    field_receipt = _receipt(
        value.field_source,
        "DamageImmunityPatch.field_source",
    )
    name_receipt = _receipt(
        value.creature_name_source,
        "DamageImmunityPatch.creature_name_source",
    )
    if _receipt_bytes(
        field_receipt,
        "DamageImmunityPatch.field_source",
    ) != _receipt_bytes(
        value.consumer.receipt,
        "DamageImmunityPatch.consumer.receipt",
    ):
        raise DamageImmunityCompileError(
            "patch field receipt disagrees with its verified consumer"
        )
    if _receipt_bytes(
        name_receipt,
        "DamageImmunityPatch.creature_name_source",
    ) != _receipt_bytes(
        value.creature_name_selection.receipt,
        "DamageImmunityPatch.creature_name_selection.receipt",
    ):
        raise DamageImmunityCompileError(
            "patch name receipt disagrees with its verified selection"
        )

    address = value.consumer.address
    if (
        address.source_id != "core-mc1"
        or address.source_id != value.source_id
        or address.locator != value.locator
        or address.span is not None
        or not address.carrier_path
        or len(address.selection_path) != 1
    ):
        raise DamageImmunityCompileError(
            "patch consumer address is not an exact Immunities selection"
        )
    if (
        len(address.target_path)
        + len(address.carrier_path)
        + len(address.selection_path)
        > 256
    ):
        raise DamageImmunityCompileError(
            "patch consumer address exceeds its path bound"
        )
    carrier_tail = address.carrier_path[-1]
    field_step = address.selection_path[0]
    if (
        type(carrier_tail) is not RawMemberStep
        or carrier_tail.raw_key != "^.creature"
        or type(field_step) is not RawMemberStep
        or field_step.raw_key != "Immunities"
    ):
        raise DamageImmunityCompileError(
            "patch consumer is outside an exact creature Immunities field"
        )

    raw_block = value.consumer.carrier.raw_block
    if type(raw_block) is not RawSourceObject:
        raise TypeError("patch consumer carrier must be an exact raw object")
    if len(raw_block.members) > 256:
        raise DamageImmunityCompileError(
            "patch consumer carrier exceeds its member bound"
        )
    field_indexes = _exact_member_indexes(raw_block, "Immunities")
    name_indexes = _exact_member_indexes(raw_block, "Name")
    if field_indexes != (field_step.member_ordinal,):
        raise DamageImmunityCompileError(
            "patch consumer requires exactly one absolute Immunities member"
        )
    if len(name_indexes) != 1:
        raise DamageImmunityCompileError(
            "patch consumer requires exactly one Name member"
        )
    if (
        type(value.consumer.raw_member) is not RawSourceMember
        or value.consumer.raw_member
        != raw_block.members[field_step.member_ordinal]
    ):
        raise DamageImmunityCompileError(
            "patch consumer raw member disagrees with its carrier"
        )
    creature_name = _require_exact_text(
        raw_block.members[name_indexes[0]].value,
        "patch creature Name",
        maximum_bytes=4_096,
        trimmed=True,
    )
    expected_name_selection = value.consumer.carrier.select(
        (RawMemberStep("Name", name_indexes[0]),)
    )
    if (
        creature_name != value.creature_name
        or _receipt_bytes(
            value.creature_name_selection.receipt,
            "DamageImmunityPatch.creature_name_selection.receipt",
        )
        != _receipt_bytes(
            expected_name_selection.receipt,
            "expected creature Name receipt",
        )
    ):
        raise DamageImmunityCompileError(
            "patch creature name disagrees with authenticated source"
        )

    raw_value = value.consumer.raw_value
    if type(raw_value) is str:
        expected_shape: Literal["scalar", "array"] = "scalar"
        raw_tokens = (raw_value,)
    elif type(raw_value) is RawSourceArray:
        expected_shape = "array"
        raw_tokens = raw_value.items
    else:
        raise DamageImmunityCompileError(
            "patch Immunities value has an invalid source shape"
        )
    if (
        value.field_shape != expected_shape
        or not raw_tokens
        or len(raw_tokens) != len(value.tokens)
        or len(raw_tokens) > 256
    ):
        raise DamageImmunityCompileError(
            "patch tokens disagree with the authenticated source shape"
        )

    for ordinal, (raw_token, token) in enumerate(
        zip(raw_tokens, value.tokens, strict=True)
    ):
        source_text = _require_exact_text(
            raw_token,
            f"patch Immunities token {ordinal}",
            maximum_bytes=4_096,
            trimmed=False,
        )
        _validate_token(token)
        expected_selection = (
            value.consumer
            if expected_shape == "scalar"
            else value.consumer.carrier.select(
                (
                    field_step,
                    RawIndexStep(ordinal),
                )
            )
        )
        if (
            token.ordinal != ordinal
            or token.source_text != source_text
            or token.authority is not value.authority
            or _receipt_bytes(
                token.consumer.receipt,
                "DamageImmunityToken.consumer.receipt",
            )
            != _receipt_bytes(
                expected_selection.receipt,
                "expected immunity token receipt",
            )
            or _receipt_bytes(
                token.source,
                "DamageImmunityToken.source",
            )
            != _receipt_bytes(
                expected_selection.receipt,
                "expected immunity token receipt",
            )
        ):
            raise DamageImmunityCompileError(
                "patch token disagrees with its authenticated source item"
            )

    needs_damage_types = any(
        "pc1-damage-types" in token.provider_rule_ids
        for token in value.tokens
    )
    requirements = _requirements(needs_damage_types)
    if (
        len(value.provider_rules) != len(requirements)
        or tuple(rule.rule_id for rule in value.provider_rules)
        != tuple(item.rule_id for item in requirements)
        or tuple(
            _requirement_bytes(
                rule.requirement,
                "DamageImmunityPatch provider requirement",
            )
            for rule in value.provider_rules
        )
        != tuple(
            _requirement_bytes(
                requirement,
                "reviewed damage immunity requirement",
            )
            for requirement in requirements
        )
    ):
        raise DamageImmunityCompileError(
            "patch providers disagree with exact reviewed requirements"
        )
    available_rule_ids = tuple(
        requirement.rule_id for requirement in requirements
    )
    if any(
        not set(token.provider_rule_ids).issubset(available_rule_ids)
        for token in value.tokens
    ):
        raise DamageImmunityCompileError(
            "patch token refers to an unavailable provider rule"
        )
    return value


def _validated_consumer(
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
) -> VerifiedSourceSelection:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "damage immunity compiler requires an exact "
            "SourceAuthorityAdapter"
        )
    if type(consumer) is not VerifiedSourceSelection:
        raise TypeError(
            "damage immunity compiler requires an exact verified selection"
        )
    # Require the public authority validator to re-resolve and compare the
    # entire caller-held view before any source value is observed.
    return authority.validate_selection(consumer)


def compile_damage_immunities(
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
) -> DamageImmunityPatch:
    """Compile one verifier-issued Core MC1 ``Immunities`` selection."""

    verified = _validated_consumer(authority, consumer)
    address = verified.address
    if address.source_id != "core-mc1":
        raise DamageImmunityCompileError(
            "damage immunity consumer must come from core-mc1"
        )
    if address.span is not None:
        raise DamageImmunityCompileError(
            "damage immunity consumer cannot be a text span"
        )
    combined_path_length = (
        len(address.target_path)
        + len(address.carrier_path)
        + len(address.selection_path)
    )
    if combined_path_length > 256:
        raise DamageImmunityCompileError(
            "damage immunity source path exceeds its bound"
        )
    if not address.carrier_path:
        raise DamageImmunityCompileError(
            "damage immunity consumer has no creature carrier"
        )
    carrier_tail = address.carrier_path[-1]
    if (
        type(carrier_tail) is not RawMemberStep
        or carrier_tail.raw_key != "^.creature"
    ):
        raise DamageImmunityCompileError(
            "damage immunity carrier must be an exact ^.creature member"
        )
    if len(address.selection_path) != 1:
        raise DamageImmunityCompileError(
            "damage immunity consumer must select one exact field member"
        )
    field_step = address.selection_path[0]
    if (
        type(field_step) is not RawMemberStep
        or field_step.raw_key != "Immunities"
    ):
        raise DamageImmunityCompileError(
            "damage immunity consumer must select Immunities"
        )

    raw_block = verified.carrier.raw_block
    if type(raw_block) is not RawSourceObject:
        raise TypeError(
            "damage immunity carrier must be an exact RawSourceObject"
        )
    if len(raw_block.members) > 256:
        raise DamageImmunityCompileError(
            "damage immunity carrier exceeds its member bound"
        )
    field_indexes = _exact_member_indexes(raw_block, "Immunities")
    if len(field_indexes) != 1:
        raise DamageImmunityCompileError(
            "creature must contain exactly one Immunities member"
        )
    if field_step.member_ordinal != field_indexes[0]:
        raise DamageImmunityCompileError(
            "Immunities path ordinal disagrees with the carrier"
        )
    if (
        type(verified.raw_member) is not RawSourceMember
        or verified.raw_member.key != "Immunities"
    ):
        raise DamageImmunityCompileError(
            "verified selection did not retain the Immunities member"
        )

    name_indexes = _exact_member_indexes(raw_block, "Name")
    if len(name_indexes) != 1:
        raise DamageImmunityCompileError(
            "creature must contain exactly one Name member"
        )
    name_value = raw_block.members[name_indexes[0]].value
    creature_name = _require_exact_text(
        name_value,
        "creature Name",
        maximum_bytes=4_096,
        trimmed=True,
    )
    name_selection = verified.carrier.select(
        (RawMemberStep("Name", name_indexes[0]),)
    )

    raw_value = verified.raw_value
    if type(raw_value) is str:
        field_shape: Literal["scalar", "array"] = "scalar"
        raw_tokens = (raw_value,)
    elif type(raw_value) is RawSourceArray:
        field_shape = "array"
        raw_tokens = raw_value.items
    else:
        raise DamageImmunityCompileError(
            "Immunities must be a scalar string or an array of strings"
        )
    if not raw_tokens:
        raise DamageImmunityCompileError("Immunities cannot be empty")
    if len(raw_tokens) > 256:
        raise DamageImmunityCompileError(
            "Immunities exceeds its token count bound"
        )

    pending_tokens: list[
        tuple[str, int, VerifiedSourceSelection]
    ] = []
    for ordinal, raw_token in enumerate(raw_tokens):
        source_text = _require_exact_text(
            raw_token,
            f"Immunities token {ordinal}",
            maximum_bytes=4_096,
            trimmed=False,
        )
        if not source_text.strip():
            raise DamageImmunityCompileError(
                f"Immunities token {ordinal} is effectively empty"
            )
        token_selection = (
            verified
            if field_shape == "scalar"
            else verified.carrier.select(
                (
                    field_step,
                    RawIndexStep(ordinal),
                )
            )
        )
        pending_tokens.append(
            (source_text, ordinal, token_selection)
        )

    provider_rules = _provider_rules(
        authority,
        tuple(
            source_text
            for source_text, _ordinal, _selection in pending_tokens
        ),
    )
    compiled_tokens = tuple(
        _classify_token(
            source_text,
            ordinal,
            authority,
            token_selection,
            provider_rules,
        )
        for source_text, ordinal, token_selection in pending_tokens
    )
    return DamageImmunityPatch(
        source_id=address.source_id,
        locator=address.locator,
        creature_name=creature_name,
        field_shape=field_shape,
        authority=authority,
        consumer=verified,
        creature_name_selection=name_selection,
        field_source=verified.receipt,
        creature_name_source=name_selection.receipt,
        provider_rules=provider_rules,
        tokens=compiled_tokens,
    )


__all__ = [
    "DamageImmunityCompileError",
    "DamageImmunityPatch",
    "DamageImmunityToken",
    "FAMILY_ID",
    "MAX_CARRIER_MEMBERS",
    "MAX_CREATURE_NAME_BYTES",
    "MAX_IMMUNITY_TOKENS",
    "MAX_SIGNED_64",
    "MAX_TOKEN_BYTES",
    "MECHANIC_TYPE",
    "compile_damage_immunities",
]

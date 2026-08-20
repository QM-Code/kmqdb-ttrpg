"""Compile verified Core MC1 All-Around Vision source carriers.

All-Around Vision appears in two source shapes:

* an annotation on an ``AC`` or ``HP`` scalar; and
* Grikkitog's named ``Manifold Vision`` passive.

The compiler accepts only selections and provider receipts revalidated by
one explicit shared source-authority adapter.  It preserves the selected raw
member and, for Troll Warleader, the linked ``Shed Armor`` member as separate
verified evidence.  Compiled artifacts retain that adapter and evidence,
revalidate them, and re-derive every public field before serialization; a
byte-identical reconstruction is valid, while an invented projection is not.
The result is deliberately compile-only:
attack-relative flanking, off-guard attribution, Sneak Attack eligibility,
and conditional state still require runtime contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Literal, TypeAlias, final

from .contracts import RawSourceArray, RawSourceMember, RawSourceObject
from .source_authority import (
    AUTHORITY_RULESET,
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
    canonical_json_bytes,
    raw_member_sha256,
    raw_source_sha256,
)
from .source_values import parse_decimal_integer


FAMILY_ID = "all-around-vision"
COMPILER_ID = "all-around-vision-verified-source"
MECHANIC_TYPE = "flanking-immunity"
MONSTER_CORE_SOURCE_ID = "core-mc1"

MAX_SOURCE_TEXT_BYTES = 16_384
MAX_CREATURE_NAME_BYTES = 1_024
MAX_STAT_VALUE = 999

ALL_AROUND_VISION_RULE_ID = "all-around-vision"
FLANKING_RULE_ID = "flanking"
OFF_GUARD_RULE_ID = "off-guard"
SNEAK_ATTACK_RULE_ID = "sneak-attack"

ALL_AROUND_VISION_RULE = RuleRequirement(
    rule_id=ALL_AROUND_VISION_RULE_ID,
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
    carrier_path=(RawMemberStep("^.ability", 2),),
    selection_path=(RawMemberStep("Description", 1),),
    expected_selection_sha256=(
        "dbcceb8b8d5d6d88ce30796df8917aa08d4165eabd6cb7ada1ef13b06fd48e55"
    ),
)
FLANKING_RULE = RuleRequirement(
    rule_id=FLANKING_RULE_ID,
    source_id="core-pc1",
    locator="425.2",
    selection_path=(RawMemberStep("~.p", 1),),
    expected_selection_sha256=(
        "5d4569ec52f6f5bccc232bbc399aeb31ee45a1bc61d07eab8f67ea9f57ce0697"
    ),
)
OFF_GUARD_RULE = RuleRequirement(
    rule_id=OFF_GUARD_RULE_ID,
    source_id="core-pc1",
    locator="445.2",
    selection_path=(
        RawMemberStep("Description", 2),
        RawMemberStep("~.p", 0),
    ),
    expected_selection_sha256=(
        "890c9221a9cc5e47efab548b3d226442321bc95959df791f6c297ff99a480b51"
    ),
)
SNEAK_ATTACK_RULE = RuleRequirement(
    rule_id=SNEAK_ATTACK_RULE_ID,
    source_id="core-pc1",
    locator="167.1",
    selection_path=(
        RawMemberStep("Description", 4),
        RawMemberStep("~.p", 0),
    ),
    expected_selection_sha256=(
        "ccc148c2ec0f9601f9bf6ca6b161c89ad84e7b9e07a24289e2e9c2735b26352f"
    ),
)

RULE_REQUIREMENTS = (
    ALL_AROUND_VISION_RULE,
    FLANKING_RULE,
    OFF_GUARD_RULE,
    SNEAK_ATTACK_RULE,
)


def _rule_requirement_fingerprint(value: object, /) -> str:
    if type(value) is not tuple or any(
        type(item) is not RuleRequirement for item in value
    ):
        raise TypeError(
            "reviewed All-Around Vision requirements must be an exact tuple"
        )
    return hashlib.sha256(
        canonical_json_bytes(
            [
                RuleRequirement.as_serialized(item)
                for item in value
            ]
        )
    ).hexdigest()


_RULE_REQUIREMENT_FINGERPRINT = _rule_requirement_fingerprint(
    RULE_REQUIREMENTS
)

_COMMA_PAGE_RE = re.compile(
    r"^(?P<value>[1-9][0-9]*), all-around vision \(page 358\)$",
    re.ASCII,
)
_SEMICOLON_RE = re.compile(
    r"^(?P<value>[1-9][0-9]*); all-around vision"
    r"(?: \(page 358\))?$",
    re.ASCII,
)
_SHED_ARMOR_STAT_RE = re.compile(
    r"^(?P<armored>[1-9][0-9]*) "
    r"\((?P<unarmored>[1-9][0-9]*) plus all-around vision "
    r"after Shed Armor\)$",
    re.ASCII,
)
_SHED_ARMOR_DESCRIPTION_RE = re.compile(
    r"^The warleader cuts their armor loose from their flesh\. "
    r"They immediately heal 60 Hit Points in a surge of regeneration "
    r"as they grow twisted limbs and malformed faces\. "
    r"Without their armor, the warleader's AC drops to "
    r"(?P<unarmored>[1-9][0-9]*) but they gain all-around vision "
    r"\(page (?P<page>[1-9][0-9]*)\) from the new faces\. "
    r"Putting the armor back on takes 10 minutes, and this ability "
    r"can't be used again until 1 hour has passed\.$",
    re.ASCII,
)
_MANIFOLD_VISION_TEXT = (
    "While its core is implanted, the grikkitog can see through the eyes "
    "it creates throughout the area of its infestation aura, gaining the "
    "benefits of all-around vision (page 358)."
)

ConditionKind: TypeAlias = Literal[
    "always",
    "after-shed-armor",
    "while-core-implanted",
]
DeferralPhase: TypeAlias = Literal["source-link", "runtime"]
DeferralRelation: TypeAlias = Literal[
    "attack-flanking",
    "attack-off-guard",
    "attack-damage",
    "participant-state",
]


class AllAroundVisionSourceError(ValueError):
    """A family-shaped verified carrier is malformed or ambiguous."""


class AllAroundVisionLinkError(ValueError):
    """Verified provider evidence does not match the reviewed rule set."""


def _exact_contract_fields(
    value: object,
    exact_type: type,
    field_names: tuple[str, ...],
    label: str,
    /,
) -> tuple[object, ...]:
    if type(value) is not exact_type:
        raise TypeError(f"{label} must use its exact contract type")
    try:
        return tuple(
            object.__getattribute__(value, field_name)
            for field_name in field_names
        )
    except (AttributeError, RecursionError) as failure:
        raise ValueError(f"{label} is incomplete or cyclic") from failure


def _require_exact_text(
    value: object,
    label: str,
    *,
    maximum_bytes: int,
) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise AllAroundVisionSourceError(
            f"{label} must be an exact non-empty trimmed string"
        )
    if len(value.encode("utf-8")) > maximum_bytes:
        raise AllAroundVisionSourceError(f"{label} exceeds its byte bound")
    return value


def _bounded_stat(value: object) -> int | None:
    parsed = parse_decimal_integer(value)
    if (
        type(parsed) is not int
        or parsed <= 0
        or parsed > MAX_STAT_VALUE
    ):
        return None
    return parsed


def _exact_member(
    block: RawSourceObject,
    raw_key: str,
    /,
) -> tuple[int, RawSourceMember]:
    if type(block) is not RawSourceObject or type(block.members) is not tuple:
        raise AllAroundVisionSourceError(
            "verified consumer block must be an exact RawSourceObject"
        )
    exact: list[tuple[int, RawSourceMember]] = []
    conflicts: list[int] = []
    for ordinal, member in enumerate(block.members):
        if type(member) is not RawSourceMember:
            raise AllAroundVisionSourceError(
                "verified consumer block contains a non-exact raw member"
            )
        if type(member.key) is not str:
            raise AllAroundVisionSourceError(
                "verified consumer block contains a non-exact raw key"
            )
        if member.key == raw_key:
            exact.append((ordinal, member))
        elif member.key.strip() == raw_key:
            conflicts.append(ordinal)
    if len(exact) != 1 or conflicts:
        raise AllAroundVisionSourceError(
            f"verified consumer requires one exact {raw_key!r} member "
            "without whitespace-conflicting siblings"
        )
    return exact[0]


def _selected_consumer_member(
    source: VerifiedSourceSelection,
    /,
) -> tuple[VerifiedSourceCarrier, int, RawSourceMember]:
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "All-Around Vision requires an exact VerifiedSourceSelection"
        )
    try:
        source.receipt
    except (AttributeError, TypeError) as failure:
        raise AllAroundVisionSourceError(
            "All-Around Vision consumer cannot produce an authority receipt"
        ) from failure
    carrier = source.carrier
    if type(carrier) is not VerifiedSourceCarrier:
        raise AllAroundVisionSourceError(
            "verified consumer has an invalid carrier type"
        )
    address = source.address
    if (
        type(address.selection_path) is not tuple
        or len(address.selection_path) != 1
        or type(address.selection_path[0]) is not RawMemberStep
        or address.span is not None
    ):
        raise AllAroundVisionSourceError(
            "verified consumer must select one complete top-level member"
        )
    step = address.selection_path[0]
    block = carrier.raw_block
    if type(block) is not RawSourceObject or type(block.members) is not tuple:
        raise AllAroundVisionSourceError(
            "verified consumer block has an invalid raw type"
        )
    if step.member_ordinal >= len(block.members):
        raise AllAroundVisionSourceError(
            "verified consumer member ordinal is out of range"
        )
    member = block.members[step.member_ordinal]
    if (
        type(member) is not RawSourceMember
        or member is not source.raw_member
        or member.key != step.raw_key
        or source.raw_value is not member.value
        or source.selected_value is not member.value
    ):
        raise AllAroundVisionSourceError(
            "verified consumer selection disagrees with its raw carrier"
        )
    exact_ordinal, exact_member = _exact_member(block, member.key)
    if exact_ordinal != step.member_ordinal or exact_member is not member:
        raise AllAroundVisionSourceError(
            "verified consumer does not select the sole exact raw member"
        )
    return carrier, step.member_ordinal, member


def _creature_name(block: RawSourceObject, /) -> str:
    _ordinal, member = _exact_member(block, "Name")
    return _require_exact_text(
        member.value,
        "creature Name",
        maximum_bytes=MAX_CREATURE_NAME_BYTES,
    )


@final
@dataclass(frozen=True, slots=True)
class AllAroundVisionCondition:
    """The exact state in which the passive is present."""

    kind: ConditionKind
    state_key: str | None
    inactive_stat_value: int | None
    active_stat_value: int | None

    def __post_init__(self) -> None:
        (
            kind,
            state_key,
            inactive_stat_value,
            active_stat_value,
        ) = _exact_contract_fields(
            self,
            AllAroundVisionCondition,
            (
                "kind",
                "state_key",
                "inactive_stat_value",
                "active_stat_value",
            ),
            "AllAroundVisionCondition",
        )
        if type(kind) is not str:
            raise TypeError(
                "AllAroundVisionCondition.kind must be an exact string"
            )
        if state_key is not None and type(state_key) is not str:
            raise TypeError(
                "AllAroundVisionCondition.state_key must be an exact string "
                "or None"
            )
        if kind == "always":
            if (
                state_key is not None
                or inactive_stat_value is not None
                or active_stat_value is not None
            ):
                raise ValueError(
                    "an always condition cannot carry conditional state"
                )
            return
        expected_state = {
            "after-shed-armor": "shed-armor-used",
            "while-core-implanted": "core-implanted",
        }.get(kind)
        if expected_state is None or state_key != expected_state:
            raise ValueError(
                "AllAroundVisionCondition has an invalid conditional state"
            )
        if kind == "after-shed-armor":
            for value in (inactive_stat_value, active_stat_value):
                if (
                    type(value) is not int
                    or value <= 0
                    or value > MAX_STAT_VALUE
                ):
                    raise ValueError(
                        "Shed Armor condition requires bounded AC values"
                    )
        elif (
            inactive_stat_value is not None
            or active_stat_value is not None
        ):
            raise ValueError(
                "implanted-core condition cannot carry stat values"
            )

    def as_serialized(self) -> dict[str, Any]:
        self.__post_init__()
        result: dict[str, Any] = {
            "kind": self.kind,
            "stateKey": self.state_key,
        }
        if self.inactive_stat_value is not None:
            result["inactiveStatValue"] = self.inactive_stat_value
        if self.active_stat_value is not None:
            result["activeStatValue"] = self.active_stat_value
        return result


@final
@dataclass(frozen=True, slots=True)
class AllAroundVisionDeferral:
    """One typed contract required before registry activation."""

    dependency_id: str
    phase: DeferralPhase
    relation: DeferralRelation
    required_contract: str

    def __post_init__(self) -> None:
        (
            dependency_id,
            phase,
            relation,
            required_contract,
        ) = _exact_contract_fields(
            self,
            AllAroundVisionDeferral,
            (
                "dependency_id",
                "phase",
                "relation",
                "required_contract",
            ),
            "AllAroundVisionDeferral",
        )
        for field_name, value in (
            ("dependency_id", dependency_id),
            ("required_contract", required_contract),
        ):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(
                    f"AllAroundVisionDeferral.{field_name} is invalid"
                )
        if type(phase) is not str:
            raise TypeError(
                "AllAroundVisionDeferral.phase must be an exact string"
            )
        if phase not in ("source-link", "runtime"):
            raise ValueError("AllAroundVisionDeferral.phase is invalid")
        if type(relation) is not str:
            raise TypeError(
                "AllAroundVisionDeferral.relation must be an exact string"
            )
        if relation not in (
            "attack-flanking",
            "attack-off-guard",
            "attack-damage",
            "participant-state",
        ):
            raise ValueError("AllAroundVisionDeferral.relation is invalid")

    def as_serialized(self) -> dict[str, str]:
        self.__post_init__()
        return {
            "id": self.dependency_id,
            "phase": self.phase,
            "relation": self.relation,
            "requiredContract": self.required_contract,
            "status": "deferred",
            "blocks": "registry-activation",
        }


_DEFERRAL_SPECS = (
    (
        "attack-relative-flanking",
        "runtime",
        "attack-flanking",
        (
            "attack-relative flanking evaluation across attacker, ally, "
            "target footprint, reach, weapon, and ability-to-act state"
        ),
    ),
    (
        "flanking-off-guard-source-attribution",
        "runtime",
        "attack-off-guard",
        (
            "off-guard condition state attributed to its source so only the "
            "flanking source is suppressed"
        ),
    ),
    (
        "sneak-attack-after-flanking-suppression",
        "runtime",
        "attack-damage",
        (
            "Sneak Attack eligibility evaluated from the target's remaining "
            "attack-relative off-guard sources"
        ),
    ),
    (
        "all-around-vision-condition-state",
        "runtime",
        "participant-state",
        (
            "source-backed always, Shed Armor, and implanted-core state "
            "transitions with digest-stable expiration and restoration"
        ),
    ),
)


def _fresh_deferrals() -> tuple[AllAroundVisionDeferral, ...]:
    return tuple(
        AllAroundVisionDeferral(
            dependency_id=dependency_id,
            phase=phase,
            relation=relation,
            required_contract=required_contract,
        )
        for (
            dependency_id,
            phase,
            relation,
            required_contract,
        ) in _DEFERRAL_SPECS
    )


def _deferral_fingerprint(
    value: object,
    /,
) -> str:
    if type(value) is not tuple:
        raise TypeError(
            "All-Around Vision deferrals must be an exact tuple"
        )
    fields: list[tuple[str, str, str, str]] = []
    for item in value:
        if type(item) is not AllAroundVisionDeferral:
            raise TypeError(
                "All-Around Vision deferrals must use exact contracts"
            )
        item.__post_init__()
        fields.append(
            (
                item.dependency_id,
                item.phase,
                item.relation,
                item.required_contract,
            )
        )
    return hashlib.sha256(
        canonical_json_bytes([list(item) for item in fields])
    ).hexdigest()


_DEFERRAL_FINGERPRINT = hashlib.sha256(
    canonical_json_bytes([list(item) for item in _DEFERRAL_SPECS])
).hexdigest()

DEFERRALS = _fresh_deferrals()


@final
@dataclass(frozen=True, slots=True)
class ReviewedErrataDecision:
    """One reviewed publication erratum preserved without source rewriting."""

    decision_id: str
    publication_source_id: str
    consumer_locator: str
    raw_citation: str
    resolved_rule_source_id: str
    resolved_rule_locator: str

    def __post_init__(self) -> None:
        field_names = (
            "decision_id",
            "publication_source_id",
            "consumer_locator",
            "raw_citation",
            "resolved_rule_source_id",
            "resolved_rule_locator",
        )
        values = _exact_contract_fields(
            self,
            ReviewedErrataDecision,
            field_names,
            "ReviewedErrataDecision",
        )
        for field_name, value in zip(
            field_names,
            values,
        ):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(
                    f"ReviewedErrataDecision.{field_name} is invalid"
                )

    def as_serialized(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "id": self.decision_id,
            "classification": "publication-errata",
            "disposition": "preserve-source-link-reviewed-provider",
            "publicationSourceId": self.publication_source_id,
            "consumerLocator": self.consumer_locator,
            "rawCitation": self.raw_citation,
            "resolvedRule": {
                "sourceId": self.resolved_rule_source_id,
                "locator": self.resolved_rule_locator,
            },
        }


@final
@dataclass(frozen=True, slots=True)
class AllAroundVisionPatch:
    """One authority-linked, non-executable family compile artifact."""

    _adapter: SourceAuthorityAdapter = field(repr=False, compare=False)
    creature_name: str
    carrier_kind: Literal["annotated-stat", "named-ability"]
    raw_key: str
    source_text: str
    stat_value: int | None
    condition: AllAroundVisionCondition
    consumer_sources: tuple[VerifiedSourceSelection, ...] = field(
        repr=False
    )
    consumer_records: tuple[SourceReceipt, ...]
    providers: tuple[VerifiedRuleReceipt, ...]
    deferrals: tuple[AllAroundVisionDeferral, ...]
    errata_decision: ReviewedErrataDecision | None
    runtime_ready: bool

    def __post_init__(self) -> None:
        _validated_patch_payload(self, serialize=False)

    @property
    def mechanic_type(self) -> str:
        _validated_patch_payload(self, serialize=False)
        return MECHANIC_TYPE

    def as_serialized(self) -> dict[str, Any]:
        result = _validated_patch_payload(self, serialize=True)
        if type(result) is not dict:
            raise AssertionError("serialized patch payload is unavailable")
        return result


def _verified_providers(
    source: VerifiedSourceSelection,
    providers: object,
    /,
) -> tuple[VerifiedRuleReceipt, ...]:
    if type(providers) is not tuple:
        raise AllAroundVisionLinkError(
            "All-Around Vision providers must be an exact ordered tuple"
        )
    try:
        requirement_fingerprint = _rule_requirement_fingerprint(
            RULE_REQUIREMENTS
        )
    except (AttributeError, RecursionError, TypeError, ValueError) as failure:
        raise AllAroundVisionLinkError(
            "reviewed All-Around Vision requirements are noncanonical"
        ) from failure
    if requirement_fingerprint != _RULE_REQUIREMENT_FINGERPRINT:
        raise AllAroundVisionLinkError(
            "reviewed All-Around Vision requirements were altered"
        )
    if len(providers) != len(RULE_REQUIREMENTS):
        raise AllAroundVisionLinkError(
            "All-Around Vision requires all reviewed provider rules"
        )
    authority_digest = source.carrier.authority_digest
    verified: list[VerifiedRuleReceipt] = []
    for requirement, provider in zip(RULE_REQUIREMENTS, providers):
        if type(provider) is not VerifiedRuleReceipt:
            raise AllAroundVisionLinkError(
                "All-Around Vision provider has an invalid verified type"
            )
        try:
            (
                rule_id,
                retained_requirement,
                selection,
                receipt,
            ) = _exact_contract_fields(
                provider,
                VerifiedRuleReceipt,
                (
                    "rule_id",
                    "requirement",
                    "selection",
                    "receipt",
                ),
                "VerifiedRuleReceipt",
            )
            if type(retained_requirement) is not RuleRequirement:
                raise TypeError(
                    "verified provider requirement must be exact"
                )
            retained_requirement_bytes = canonical_json_bytes(
                RuleRequirement.as_serialized(retained_requirement)
            )
            reviewed_requirement_bytes = canonical_json_bytes(
                RuleRequirement.as_serialized(requirement)
            )
        except (AttributeError, RecursionError, TypeError, ValueError) as failure:
            raise AllAroundVisionLinkError(
                "All-Around Vision provider cannot produce canonical "
                "review evidence"
            ) from failure
        if (
            type(selection) is not VerifiedSourceSelection
            or type(receipt) is not SourceReceipt
            or type(selection.carrier) is not VerifiedSourceCarrier
        ):
            raise AllAroundVisionLinkError(
                "All-Around Vision provider has invalid verified types"
            )
        if (
            type(rule_id) is not str
            or rule_id != requirement.rule_id
            or retained_requirement_bytes != reviewed_requirement_bytes
        ):
            raise AllAroundVisionLinkError(
                "All-Around Vision provider order or identity disagrees"
            )
        address = selection.address
        if (
            selection.carrier.ruleset != AUTHORITY_RULESET
            or selection.carrier.authority_digest != authority_digest
            or address.source_id != requirement.source_id
            or address.locator != requirement.locator
            or address.carrier_path != requirement.carrier_path
            or address.selection_path != requirement.selection_path
            or address.span != requirement.span
            or receipt != selection.receipt
        ):
            raise AllAroundVisionLinkError(
                f"All-Around Vision provider evidence disagrees: "
                f"{requirement.rule_id}"
            )
        expected_hashes = (
            (
                requirement.expected_block_sha256,
                selection.block_sha256,
            ),
            (
                requirement.expected_member_sha256,
                selection.member_sha256,
            ),
            (
                requirement.expected_value_sha256,
                selection.value_sha256,
            ),
            (
                requirement.expected_selection_sha256,
                selection.selection_sha256,
            ),
        )
        if any(
            expected is not None and expected != actual
            for expected, actual in expected_hashes
        ):
            raise AllAroundVisionLinkError(
                f"All-Around Vision provider hash disagrees: "
                f"{requirement.rule_id}"
            )
        verified.append(provider)
    return tuple(verified)


def _compile_unconditional(
    *,
    raw_key: str,
    source_text: str,
) -> tuple[int, AllAroundVisionCondition] | None:
    match = _COMMA_PAGE_RE.fullmatch(source_text)
    grammar = "comma" if match is not None else None
    if match is None:
        match = _SEMICOLON_RE.fullmatch(source_text)
        if match is not None:
            grammar = "semicolon"
    if match is None:
        return None
    stat_value = _bounded_stat(match.group("value"))
    if stat_value is None:
        return None
    if raw_key not in ("AC", "HP"):
        return None
    if raw_key == "HP" and grammar != "comma":
        return None
    return (
        stat_value,
        AllAroundVisionCondition(
            kind="always",
            state_key=None,
            inactive_stat_value=None,
            active_stat_value=None,
        ),
    )


def _compile_shed_armor(
    *,
    source: VerifiedSourceSelection,
    block: RawSourceObject,
    creature_name: str,
    raw_key: str,
    source_text: str,
    linked_sources: tuple[VerifiedSourceSelection, ...],
) -> tuple[
    int,
    AllAroundVisionCondition,
    SourceReceipt,
    ReviewedErrataDecision | None,
] | None:
    match = _SHED_ARMOR_STAT_RE.fullmatch(source_text)
    if match is None or raw_key != "AC":
        return None
    if creature_name != "Troll Warleader":
        raise AllAroundVisionSourceError(
            "Shed Armor All-Around Vision grammar belongs to Troll Warleader"
        )
    armored = _bounded_stat(match.group("armored"))
    unarmored = _bounded_stat(match.group("unarmored"))
    if armored is None or unarmored is None:
        return None

    shed_ordinal, shed_member = _exact_member(block, "!.Shed Armor")
    if (
        len(linked_sources) != 1
        or type(linked_sources[0]) is not VerifiedSourceSelection
    ):
        raise AllAroundVisionSourceError(
            "Troll Warleader requires one verified Shed Armor selection"
        )
    linked_selection = linked_sources[0]
    try:
        linked_receipt = linked_selection.receipt
    except (AttributeError, TypeError) as failure:
        raise AllAroundVisionSourceError(
            "Troll Warleader Shed Armor lacks an authority receipt"
        ) from failure
    linked_address = linked_selection.address
    expected_linked_path = (
        RawMemberStep("!.Shed Armor", shed_ordinal),
    )
    if (
        type(linked_selection.carrier) is not VerifiedSourceCarrier
        or linked_selection.carrier.authority_digest
        != source.carrier.authority_digest
        or linked_selection.carrier.block_sha256
        != source.carrier.block_sha256
        or linked_selection.carrier.source_id
        != source.carrier.source_id
        or linked_address.locator != source.address.locator
        or linked_address.section_id != source.address.section_id
        or linked_address.target_path != source.address.target_path
        or linked_address.carrier_path != source.address.carrier_path
        or linked_address.selection_path != expected_linked_path
        or linked_address.span is not None
        or type(linked_selection.raw_member) is not RawSourceMember
        or linked_selection.raw_member != shed_member
        or linked_selection.raw_value != shed_member.value
        or linked_selection.selected_value != shed_member.value
        or linked_selection.member_sha256 != raw_member_sha256(shed_member)
        or linked_selection.value_sha256
        != raw_source_sha256(shed_member.value)
        or linked_selection.selection_sha256
        != raw_source_sha256(shed_member.value)
    ):
        raise AllAroundVisionSourceError(
            "verified Shed Armor selection disagrees with the AC carrier"
        )
    shed_value = shed_member.value
    if (
        type(shed_value) is not RawSourceObject
        or type(shed_value.members) is not tuple
        or tuple(
            member.key
            if type(member) is RawSourceMember
            else None
            for member in shed_value.members
        )
        != ("Action", "Traits", "Description")
    ):
        raise AllAroundVisionSourceError(
            "Troll Warleader Shed Armor source shape is invalid"
        )
    for member in shed_value.members:
        if type(member) is not RawSourceMember:
            raise AllAroundVisionSourceError(
                "Troll Warleader Shed Armor has a non-exact raw member"
            )
    action, traits, description = (
        member.value for member in shed_value.members
    )
    if type(action) is not str or action != "single":
        raise AllAroundVisionSourceError(
            "Troll Warleader Shed Armor Action must be exact single"
        )
    if (
        type(traits) is not RawSourceArray
        or type(traits.items) is not tuple
        or traits.items != ("manipulate",)
        or any(type(item) is not str for item in traits.items)
    ):
        raise AllAroundVisionSourceError(
            "Troll Warleader Shed Armor Traits are invalid"
        )
    description = _require_exact_text(
        description,
        "Troll Warleader Shed Armor Description",
        maximum_bytes=MAX_SOURCE_TEXT_BYTES,
    )
    description_match = _SHED_ARMOR_DESCRIPTION_RE.fullmatch(description)
    if description_match is None:
        raise AllAroundVisionSourceError(
            "Troll Warleader Shed Armor Description has unsupported grammar"
        )
    described_ac = _bounded_stat(description_match.group("unarmored"))
    citation_page = _bounded_stat(description_match.group("page"))
    if described_ac != unarmored or citation_page is None:
        raise AllAroundVisionSourceError(
            "Troll Warleader Shed Armor disagrees with its AC annotation"
        )
    if citation_page != 359:
        raise AllAroundVisionSourceError(
            "Troll Warleader Shed Armor has unreviewed citation drift"
        )
    errata_decision = ReviewedErrataDecision(
        decision_id=(
            "troll-warleader-shed-armor-all-around-vision-page"
        ),
        publication_source_id=MONSTER_CORE_SOURCE_ID,
        consumer_locator=source.address.locator,
        raw_citation=f"page {citation_page}",
        resolved_rule_source_id=MONSTER_CORE_SOURCE_ID,
        resolved_rule_locator=ALL_AROUND_VISION_RULE.locator,
    )
    return (
        armored,
        AllAroundVisionCondition(
            kind="after-shed-armor",
            state_key="shed-armor-used",
            inactive_stat_value=armored,
            active_stat_value=unarmored,
        ),
        linked_receipt,
        errata_decision,
    )


def _compile_manifold_vision(
    *,
    creature_name: str,
    raw_key: str,
    source_text: str,
) -> AllAroundVisionCondition | None:
    if raw_key != "!.Manifold Vision":
        return None
    if source_text != _MANIFOLD_VISION_TEXT:
        return None
    if creature_name != "Grikkitog":
        raise AllAroundVisionSourceError(
            "Manifold Vision grammar belongs to Grikkitog"
        )
    return AllAroundVisionCondition(
        kind="while-core-implanted",
        state_key="core-implanted",
        inactive_stat_value=None,
        active_stat_value=None,
    )


@dataclass(frozen=True, slots=True)
class _DerivedAllAroundVision:
    creature_name: str
    carrier_kind: Literal["annotated-stat", "named-ability"]
    raw_key: str
    source_text: str
    stat_value: int | None
    condition: AllAroundVisionCondition
    consumer_records: tuple[SourceReceipt, ...]
    errata_decision: ReviewedErrataDecision | None


def _derive_all_around_vision(
    source: VerifiedSourceSelection,
    linked_sources: tuple[VerifiedSourceSelection, ...],
    /,
) -> _DerivedAllAroundVision | None:
    carrier, _selected_ordinal, raw_member = (
        _selected_consumer_member(source)
    )
    if (
        carrier.ruleset != AUTHORITY_RULESET
        or carrier.source_id != MONSTER_CORE_SOURCE_ID
    ):
        return None
    if type(raw_member.key) is not str or type(raw_member.value) is not str:
        return None
    source_text = raw_member.value
    if len(source_text.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES:
        return None

    block = carrier.raw_block
    creature_name = _creature_name(block)
    direct = _compile_unconditional(
        raw_key=raw_member.key,
        source_text=source_text,
    )
    if direct is not None:
        if linked_sources:
            raise AllAroundVisionSourceError(
                "unconditional All-Around Vision cannot carry linked sources"
            )
        stat_value, condition = direct
        return _DerivedAllAroundVision(
            creature_name=creature_name,
            carrier_kind="annotated-stat",
            raw_key=raw_member.key,
            source_text=source_text,
            stat_value=stat_value,
            condition=condition,
            consumer_records=(source.receipt,),
            errata_decision=None,
        )

    shed = _compile_shed_armor(
        source=source,
        block=block,
        creature_name=creature_name,
        raw_key=raw_member.key,
        source_text=source_text,
        linked_sources=linked_sources,
    )
    if shed is not None:
        stat_value, condition, shed_receipt, errata_decision = shed
        return _DerivedAllAroundVision(
            creature_name=creature_name,
            carrier_kind="annotated-stat",
            raw_key=raw_member.key,
            source_text=source_text,
            stat_value=stat_value,
            condition=condition,
            consumer_records=(source.receipt, shed_receipt),
            errata_decision=errata_decision,
        )

    condition = _compile_manifold_vision(
        creature_name=creature_name,
        raw_key=raw_member.key,
        source_text=source_text,
    )
    if condition is None:
        return None
    if linked_sources:
        raise AllAroundVisionSourceError(
            "Manifold Vision cannot carry extra linked sources"
        )
    return _DerivedAllAroundVision(
        creature_name=creature_name,
        carrier_kind="named-ability",
        raw_key=raw_member.key,
        source_text=source_text,
        stat_value=None,
        condition=condition,
        consumer_records=(source.receipt,),
        errata_decision=None,
    )


def _validate_consumer_authority(
    adapter: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    /,
) -> None:
    try:
        adapter.validate_selection(source)
    except (AttributeError, RecursionError) as failure:
        raise AllAroundVisionSourceError(
            "All-Around Vision consumer authority evidence is incomplete "
            "or cyclic"
        ) from failure


def _require_shared_authority(
    adapter: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    providers: tuple[VerifiedRuleReceipt, ...],
    /,
) -> None:
    try:
        adapter.require_shared_authority(source, providers)
    except (AttributeError, RecursionError) as failure:
        raise AllAroundVisionLinkError(
            "All-Around Vision shared authority evidence is incomplete "
            "or cyclic"
        ) from failure


def _canonical_receipt_bytes(
    receipt: object,
    label: str,
    /,
) -> bytes:
    if type(receipt) is not SourceReceipt:
        raise TypeError(f"{label} must be an exact SourceReceipt")
    try:
        return canonical_json_bytes(
            SourceReceipt.as_serialized(receipt)
        )
    except (AttributeError, RecursionError, TypeError, ValueError) as failure:
        raise ValueError(
            f"{label} is incomplete, cyclic, or noncanonical"
        ) from failure


def _canonical_condition_bytes(
    condition: object,
    label: str,
    /,
) -> bytes:
    if type(condition) is not AllAroundVisionCondition:
        raise TypeError(
            f"{label} must be an exact AllAroundVisionCondition"
        )
    try:
        return canonical_json_bytes(
            AllAroundVisionCondition.as_serialized(condition)
        )
    except (AttributeError, RecursionError, TypeError, ValueError) as failure:
        raise ValueError(
            f"{label} is incomplete, cyclic, or noncanonical"
        ) from failure


def _canonical_errata_bytes(
    decision: object,
    label: str,
    /,
) -> bytes | None:
    if decision is None:
        return None
    if type(decision) is not ReviewedErrataDecision:
        raise TypeError(
            f"{label} must be an exact ReviewedErrataDecision or None"
        )
    try:
        return canonical_json_bytes(
            ReviewedErrataDecision.as_serialized(decision)
        )
    except (AttributeError, RecursionError, TypeError, ValueError) as failure:
        raise ValueError(
            f"{label} is incomplete, cyclic, or noncanonical"
        ) from failure


def _validated_patch_payload(
    patch: object,
    *,
    serialize: bool,
) -> dict[str, Any] | None:
    field_names = (
        "_adapter",
        "creature_name",
        "carrier_kind",
        "raw_key",
        "source_text",
        "stat_value",
        "condition",
        "consumer_sources",
        "consumer_records",
        "providers",
        "deferrals",
        "errata_decision",
        "runtime_ready",
    )
    (
        adapter,
        creature_name,
        carrier_kind,
        raw_key,
        source_text,
        stat_value,
        condition,
        consumer_sources,
        consumer_records,
        providers,
        deferrals,
        errata_decision,
        runtime_ready,
    ) = _exact_contract_fields(
        patch,
        AllAroundVisionPatch,
        field_names,
        "AllAroundVisionPatch",
    )
    if type(adapter) is not SourceAuthorityAdapter:
        raise TypeError(
            "AllAroundVisionPatch._adapter must be an exact "
            "SourceAuthorityAdapter"
        )
    if type(consumer_sources) is not tuple or not consumer_sources:
        raise TypeError(
            "AllAroundVisionPatch.consumer_sources must be a nonempty "
            "exact tuple"
        )
    if any(
        type(item) is not VerifiedSourceSelection
        for item in consumer_sources
    ):
        raise TypeError(
            "AllAroundVisionPatch.consumer_sources must contain exact "
            "verified selections"
        )
    if type(providers) is not tuple or any(
        type(item) is not VerifiedRuleReceipt for item in providers
    ):
        raise TypeError(
            "AllAroundVisionPatch.providers must be an exact verified tuple"
        )
    source = consumer_sources[0]
    linked_sources = consumer_sources[1:]
    for linked_source in linked_sources:
        _validate_consumer_authority(adapter, linked_source)
    _require_shared_authority(adapter, source, providers)

    try:
        derived = _derive_all_around_vision(source, linked_sources)
    except (AttributeError, RecursionError) as failure:
        raise AllAroundVisionSourceError(
            "All-Around Vision consumer carrier is incomplete or cyclic"
        ) from failure
    if derived is None:
        raise AllAroundVisionSourceError(
            "AllAroundVisionPatch consumer is not a reviewed family carrier"
        )

    if type(creature_name) is not str or not creature_name:
        raise ValueError("AllAroundVisionPatch.creature_name is invalid")
    if type(carrier_kind) is not str or carrier_kind not in (
        "annotated-stat",
        "named-ability",
    ):
        raise ValueError("AllAroundVisionPatch.carrier_kind is invalid")
    if type(raw_key) is not str or not raw_key:
        raise ValueError("AllAroundVisionPatch.raw_key is invalid")
    if type(source_text) is not str:
        raise TypeError("AllAroundVisionPatch.source_text is invalid")
    if stat_value is not None and type(stat_value) is not int:
        raise TypeError("AllAroundVisionPatch.stat_value is invalid")
    if runtime_ready is not False:
        raise ValueError(
            "All-Around Vision cannot claim runtime readiness"
        )
    if (
        creature_name != derived.creature_name
        or carrier_kind != derived.carrier_kind
        or raw_key != derived.raw_key
        or source_text != derived.source_text
        or stat_value != derived.stat_value
        or _canonical_condition_bytes(
            condition,
            "AllAroundVisionPatch.condition",
        )
        != _canonical_condition_bytes(
            derived.condition,
            "derived All-Around Vision condition",
        )
        or _canonical_errata_bytes(
            errata_decision,
            "AllAroundVisionPatch.errata_decision",
        )
        != _canonical_errata_bytes(
            derived.errata_decision,
            "derived All-Around Vision errata",
        )
    ):
        raise ValueError(
            "AllAroundVisionPatch fields disagree with verified consumer "
            "evidence"
        )
    if (
        type(consumer_records) is not tuple
        or len(consumer_records) != len(derived.consumer_records)
    ):
        raise TypeError(
            "AllAroundVisionPatch.consumer_records must be an exact complete "
            "tuple"
        )
    if any(
        _canonical_receipt_bytes(actual, "consumer receipt")
        != _canonical_receipt_bytes(expected, "derived consumer receipt")
        for actual, expected in zip(
            consumer_records,
            derived.consumer_records,
        )
    ):
        raise ValueError(
            "AllAroundVisionPatch consumer receipts disagree with verified "
            "sources"
        )
    verified_providers = _verified_providers(source, providers)
    if verified_providers != providers:
        raise AssertionError("verified provider order was not retained")
    if _deferral_fingerprint(deferrals) != _DEFERRAL_FINGERPRINT:
        raise ValueError(
            "AllAroundVisionPatch has incomplete runtime deferrals"
        )

    if not serialize:
        return None
    condition_payload = AllAroundVisionCondition.as_serialized(condition)
    errata_payload = (
        []
        if errata_decision is None
        else [ReviewedErrataDecision.as_serialized(errata_decision)]
    )
    result = {
        "familyId": FAMILY_ID,
        "supportState": "compile-only",
        "runtimeReady": False,
        "creatureName": creature_name,
        "carrier": {
            "kind": carrier_kind,
            "rawKey": raw_key,
            "sourceText": source_text,
            "statValue": stat_value,
        },
        "mechanic": {
            "type": MECHANIC_TYPE,
            "preventsFlanking": True,
            "doesNotPreventOtherOffGuardSources": True,
            "condition": condition_payload,
        },
        "consumerRecords": [
            SourceReceipt.as_serialized(item)
            for item in consumer_records
        ],
        "providers": [
            {
                "ruleId": item.rule_id,
                "requirement": RuleRequirement.as_serialized(
                    item.requirement
                ),
                "source": SourceReceipt.as_serialized(item.receipt),
            }
            for item in providers
        ],
        "deferredMechanics": [
            AllAroundVisionDeferral.as_serialized(item)
            for item in deferrals
        ],
        "reviewedErrata": errata_payload,
    }
    canonical_json_bytes(result)
    return result


def compile_all_around_vision(
    adapter: object,
    source: object,
    providers: object,
    linked_sources: object = (),
    /,
) -> AllAroundVisionPatch | None:
    """Compile one adapter-revalidated carrier without runtime activation."""

    if type(adapter) is not SourceAuthorityAdapter:
        raise TypeError(
            "All-Around Vision requires an exact SourceAuthorityAdapter"
        )
    if type(source) is not VerifiedSourceSelection:
        return None
    if type(providers) is not tuple or any(
        type(item) is not VerifiedRuleReceipt for item in providers
    ):
        raise AllAroundVisionLinkError(
            "All-Around Vision providers must be an exact verified tuple"
        )
    if type(linked_sources) is not tuple or any(
        type(item) is not VerifiedSourceSelection
        for item in linked_sources
    ):
        raise AllAroundVisionSourceError(
            "linked All-Around Vision sources must be an exact tuple"
        )

    _require_shared_authority(adapter, source, providers)
    for linked_source in linked_sources:
        _validate_consumer_authority(adapter, linked_source)

    try:
        derived = _derive_all_around_vision(source, linked_sources)
    except (AttributeError, RecursionError) as failure:
        raise AllAroundVisionSourceError(
            "All-Around Vision consumer carrier is incomplete or cyclic"
        ) from failure
    if derived is None:
        return None

    verified_providers = _verified_providers(source, providers)
    return AllAroundVisionPatch(
        _adapter=adapter,
        creature_name=derived.creature_name,
        carrier_kind=derived.carrier_kind,
        raw_key=derived.raw_key,
        source_text=derived.source_text,
        stat_value=derived.stat_value,
        condition=derived.condition,
        consumer_sources=(source, *linked_sources),
        consumer_records=derived.consumer_records,
        providers=verified_providers,
        deferrals=_fresh_deferrals(),
        errata_decision=derived.errata_decision,
        runtime_ready=False,
    )


__all__ = [
    "ALL_AROUND_VISION_RULE",
    "AllAroundVisionCondition",
    "AllAroundVisionDeferral",
    "AllAroundVisionLinkError",
    "AllAroundVisionPatch",
    "AllAroundVisionSourceError",
    "COMPILER_ID",
    "DEFERRALS",
    "FAMILY_ID",
    "FLANKING_RULE",
    "MECHANIC_TYPE",
    "OFF_GUARD_RULE",
    "ReviewedErrataDecision",
    "RULE_REQUIREMENTS",
    "SNEAK_ATTACK_RULE",
    "compile_all_around_vision",
]

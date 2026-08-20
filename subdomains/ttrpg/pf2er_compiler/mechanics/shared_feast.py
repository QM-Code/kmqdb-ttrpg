"""Compile the exact Core MC1 Sedacthy Shared Feast source family.

The publication does not contain a ``Shared Feast`` ability on the Sedacthy
Scout.  It contains ``Shared Attack``.  The Marauder and Speaker each contain
``Shared Feast`` with the exact text ``As sedacthy scout.``  This compiler
preserves that mismatch as reviewed source evidence; it does not rename the
Scout ability or pretend the inherited entries are self-contained.

Each compiled record is derived from one authority-reloaded ability receipt,
the exact local melee jaws carrier, the exact Scout base ability, and four
Player Core rule providers resolved through one shared
``SourceAuthorityAdapter``.  The result is deliberately compile-only.  Source
name resolution, subordinate Strikes, ally choice, reaction spending, target
identity, alternate attacks, multiple attack penalty, and the jaws persistent
bleed rider all remain typed runtime deferrals.  There is no registry fragment,
runtime linker, or activation hook in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeAlias, final

from .contracts import RawSourceMember, RawSourceObject
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


FAMILY_ID = "shared-feast"
COMPILER_ID = "shared-feast-verified-source"
MECHANIC_TYPE = "shared-feast-source-family"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"
BASE_LOCATOR = "300.2"
BASE_RAW_ABILITY_NAME = "Shared Attack"
INHERITED_RAW_ABILITY_NAME = "Shared Feast"
INHERITANCE_SOURCE_TEXT = "As sedacthy scout."
PRIMARY_STRIKE_NAME = "jaws"
CONSUMER_REQUIREMENT_COUNT = 6
PROVIDER_REQUIREMENT_COUNT = 4
MAX_SOURCE_TEXT_BYTES = 1_024

ProductionKind: TypeAlias = Literal[
    "base-shared-attack",
    "shared-feast-inheritance",
]
DeferralPhase: TypeAlias = Literal["source-link", "runtime"]
DeferralKind: TypeAlias = Literal[
    "published-name-resolution",
    "primary-subordinate-strike",
    "on-hit-ally-choice",
    "granted-reaction-strike",
    "same-target-binding",
    "alternate-attack-adjudication",
    "multiple-attack-penalty",
    "persistent-bleed-rider-link",
]


@dataclass(frozen=True, slots=True)
class _ProductionSpec:
    locator: str
    creature_name: str
    production: ProductionKind
    ability_rule_id: str
    raw_ability_name: str
    ability_ordinal: int
    ability_block_sha256: str
    ability_member_sha256: str
    ability_value_sha256: str
    ability_source_text: str
    melee_ordinal: int
    jaws_rule_id: str
    jaws_block_sha256: str
    jaws_member_sha256: str
    jaws_value_sha256: str
    attack_source_text: str
    attack_modifier: int
    damage_source_text: str


_PRODUCTION_SPECS: tuple[_ProductionSpec, ...] = (
    _ProductionSpec(
        locator="300.2",
        creature_name="Sedacthy Scout",
        production="base-shared-attack",
        ability_rule_id=(
            "shared-feast-ability:sedacthy-scout-shared-attack"
        ),
        raw_ability_name="Shared Attack",
        ability_ordinal=23,
        ability_block_sha256=(
            "1b4590d39798c644298946ebb0a75d266"
            "b2730d14e456ef39551170d5ec0b5e9"
        ),
        ability_member_sha256=(
            "a3c72ccc2ca5dd5534d77a50833009a0"
            "6fdee6ae3740fbba7757377e4423ffe6"
        ),
        ability_value_sha256=(
            "829771cccae4aefd06b7be7e7af09564"
            "b121dc91cfac8aaef16562ff125fe973"
        ),
        ability_source_text=(
            "The sedacthy makes a jaws Strike. If it hits, an ally of their "
            "choice can spend a reaction to make a jaws Strike against the "
            "same target. Allies with beaks or similar attacks can use those "
            "instead of jaws."
        ),
        melee_ordinal=21,
        jaws_rule_id="shared-feast-jaws:sedacthy-scout",
        jaws_block_sha256=(
            "83c41a0c24aed54518ad35d7361ed6e9"
            "89286bd8e0634e7244bd6c8ddda3ee8c"
        ),
        jaws_member_sha256=(
            "0d828628b00df5469be4c6e9d3cf0bd9"
            "4f4e7bc28feaff4b1d507c47049eb247"
        ),
        jaws_value_sha256=(
            "d3d5f96bb7fbd4dae6a341f7a1e7b05"
            "9121e9da1958ac80b562e0d0dc5589ea8"
        ),
        attack_source_text="+10",
        attack_modifier=10,
        damage_source_text=(
            "1d4+4 piercing plus 1d4 persistent bleed"
        ),
    ),
    _ProductionSpec(
        locator="300.4",
        creature_name="Sedacthy Marauder",
        production="shared-feast-inheritance",
        ability_rule_id="shared-feast-ability:sedacthy-marauder",
        raw_ability_name="Shared Feast",
        ability_ordinal=25,
        ability_block_sha256=(
            "f6671e869800333c0f28e3bc12d9601a"
            "2d325a3209224201a59a34c5787a4ca1"
        ),
        ability_member_sha256=(
            "5d15f98ce8f666f1438db7e15359b9d7"
            "2567798e056a9e42babd64cb2e7b671b"
        ),
        ability_value_sha256=(
            "3cd4943a46338b56d0374c7724e6aab4"
            "e59104fe28dd96441f1eaa4100e33a11"
        ),
        ability_source_text="As sedacthy scout.",
        melee_ordinal=22,
        jaws_rule_id="shared-feast-jaws:sedacthy-marauder",
        jaws_block_sha256=(
            "61052dc5fab6a21a562b2e55ccbc70ee"
            "3438658429d4d264b205feac646d94ce"
        ),
        jaws_member_sha256=(
            "bf3ef00236d6683b0a9ffab4974796b9"
            "f3606c5f19c419354893fa3bdd5813ec"
        ),
        jaws_value_sha256=(
            "9d38b6a6c5880ada6d0cbd77010021cd"
            "edb6a6d7bafc23fe68f2301b5a87aad2"
        ),
        attack_source_text="+14",
        attack_modifier=14,
        damage_source_text=(
            "1d4+8 piercing plus 1d4 persistent bleed"
        ),
    ),
    _ProductionSpec(
        locator="301.1",
        creature_name="Sedacthy Speaker",
        production="shared-feast-inheritance",
        ability_rule_id="shared-feast-ability:sedacthy-speaker",
        raw_ability_name="Shared Feast",
        ability_ordinal=27,
        ability_block_sha256=(
            "f6671e869800333c0f28e3bc12d9601a"
            "2d325a3209224201a59a34c5787a4ca1"
        ),
        ability_member_sha256=(
            "5d15f98ce8f666f1438db7e15359b9d7"
            "2567798e056a9e42babd64cb2e7b671b"
        ),
        ability_value_sha256=(
            "3cd4943a46338b56d0374c7724e6aab4"
            "e59104fe28dd96441f1eaa4100e33a11"
        ),
        ability_source_text="As sedacthy scout.",
        melee_ordinal=22,
        jaws_rule_id="shared-feast-jaws:sedacthy-speaker",
        jaws_block_sha256=(
            "3f797b61c0495c776b2b20fccffa7193"
            "d4e61b6ca7413143426caab2b442abaf"
        ),
        jaws_member_sha256=(
            "a27573f566c8e1f7d53e1366ebb11d90"
            "26267e24c15ad9e308a3f2f26c21cfca"
        ),
        jaws_value_sha256=(
            "c830bced5665dd9abfeccc21a6d6ab62"
            "fb060cc1842252719b5753a9aeefec59"
        ),
        attack_source_text="+16",
        attack_modifier=16,
        damage_source_text=(
            "1d6+8 piercing plus 1d4 persistent bleed"
        ),
    ),
)

# rule id, source id, locator, exact target block hash
_PROVIDER_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (
        "player-core-subordinate-actions",
        "core-pc1",
        "414.4",
        "6cca42e564d687b1b3fd6ce074ad87b1a8e055f7f0dd8fe0383bad3a81e4fa1d",
    ),
    (
        "player-core-actions-with-triggers",
        "core-pc1",
        "414.6",
        "aca6a47fc0d1e9269f4477375a80c4176bca46c7d361dd1ea4922102651299bf",
    ),
    (
        "player-core-strike",
        "core-pc1",
        "418.4",
        "4cea8c4d82ad0a9ea60102ae21613d1e401270c1b2e6d97ad7fc10041bda273a",
    ),
    (
        "player-core-multiple-attack-penalty",
        "core-pc1",
        "402.1",
        "9cee690b7622ad76a92678b16cacada0c963ba08172569a6bde16aaff0e5f42e",
    ),
)

_BASE_ABILITY_RULE_ID = _PRODUCTION_SPECS[0].ability_rule_id


class SharedFeastCompileError(ValueError):
    """Reviewed Shared Feast evidence is malformed or incomplete."""


def _ability_requirement(
    spec: _ProductionSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _member_step_type: type[RawMemberStep] = RawMemberStep,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec.ability_rule_id,
        source_id="core-mc1",
        locator=spec.locator,
        carrier_path=(
            _member_step_type(raw_key="^.creature", member_ordinal=1),
            _member_step_type(
                raw_key=f"!.{spec.raw_ability_name}",
                member_ordinal=spec.ability_ordinal,
            ),
        ),
        selection_path=(
            _member_step_type(raw_key="Description", member_ordinal=1),
        ),
        expected_block_sha256=spec.ability_block_sha256,
        expected_member_sha256=spec.ability_member_sha256,
        expected_value_sha256=spec.ability_value_sha256,
        expected_selection_sha256=spec.ability_value_sha256,
    )


def _jaws_requirement(
    spec: _ProductionSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _member_step_type: type[RawMemberStep] = RawMemberStep,
    _index_step_type: type[RawIndexStep] = RawIndexStep,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec.jaws_rule_id,
        source_id="core-mc1",
        locator=spec.locator,
        carrier_path=(
            _member_step_type(raw_key="^.creature", member_ordinal=1),
            _member_step_type(
                raw_key="Melee",
                member_ordinal=spec.melee_ordinal,
            ),
            _index_step_type(item_ordinal=1),
        ),
        selection_path=(
            _member_step_type(raw_key="Damage", member_ordinal=2),
        ),
        expected_block_sha256=spec.jaws_block_sha256,
        expected_member_sha256=spec.jaws_member_sha256,
        expected_value_sha256=spec.jaws_value_sha256,
        expected_selection_sha256=spec.jaws_value_sha256,
    )


def _provider_requirement(
    spec: tuple[str, str, str, str],
    _requirement_type: type[RuleRequirement] = RuleRequirement,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec[0],
        source_id=spec[1],
        locator=spec[2],
        expected_block_sha256=spec[3],
        expected_value_sha256=spec[3],
        expected_selection_sha256=spec[3],
    )


def _consumer_requirements(
    specs: tuple[_ProductionSpec, ...],
    ability_requirement_impl: Callable[
        [_ProductionSpec],
        RuleRequirement,
    ],
    jaws_requirement_impl: Callable[
        [_ProductionSpec],
        RuleRequirement,
    ],
) -> tuple[RuleRequirement, ...]:
    result: list[RuleRequirement] = []
    for spec in specs:
        result.extend(
            (
                ability_requirement_impl(spec),
                jaws_requirement_impl(spec),
            )
        )
    return tuple(result)


def _provider_requirements(
    specs: tuple[tuple[str, str, str, str], ...],
    provider_requirement_impl: Callable[
        [tuple[str, str, str, str]],
        RuleRequirement,
    ],
) -> tuple[RuleRequirement, ...]:
    return tuple(provider_requirement_impl(spec) for spec in specs)


@final
@dataclass(frozen=True, slots=True)
class SharedFeastNameResolution:
    """The exact published name mismatch retained as compile evidence."""

    classification: Literal["published-name-mismatch"]
    base_raw_ability_name: Literal["Shared Attack"]
    inherited_raw_ability_name: Literal["Shared Feast"]
    inheritance_source_text: Literal["As sedacthy scout."]
    base_source_id: Literal["core-mc1"]
    base_locator: Literal["300.2"]
    disposition: Literal[
        "preserve-distinct-names-and-defer-runtime-resolution"
    ]

    def __post_init__(self) -> None:
        raise TypeError("Shared Feast name-resolution contract is not bound")

    def as_serialized(self) -> dict[str, Any]:
        raise TypeError("Shared Feast name-resolution contract is not bound")


@final
@dataclass(frozen=True, slots=True)
class SharedFeastDeferral:
    """One exact mechanic that remains outside this compile-only family."""

    mechanic_id: DeferralKind
    phase: DeferralPhase
    provider_rule_ids: tuple[str, ...]
    blocking_reason: str

    def __post_init__(self) -> None:
        raise TypeError("Shared Feast deferral contract is not bound")

    def as_serialized(self) -> dict[str, Any]:
        raise TypeError("Shared Feast deferral contract is not bound")


_DEFERRAL_SPECS: tuple[
    tuple[DeferralKind, DeferralPhase, tuple[str, ...], str],
    ...,
] = (
    (
        "published-name-resolution",
        "source-link",
        (),
        (
            "The Scout publishes Shared Attack while inherited entries "
            "publish Shared Feast."
        ),
    ),
    (
        "primary-subordinate-strike",
        "runtime",
        (
            "player-core-subordinate-actions",
            "player-core-strike",
            "player-core-multiple-attack-penalty",
        ),
        "The activity's primary jaws Strike is not executable here.",
    ),
    (
        "on-hit-ally-choice",
        "runtime",
        ("player-core-subordinate-actions",),
        "Choosing one eligible ally after a hit requires encounter state.",
    ),
    (
        "granted-reaction-strike",
        "runtime",
        (
            "player-core-actions-with-triggers",
            "player-core-strike",
        ),
        "Reaction availability and the granted Strike require turn state.",
    ),
    (
        "same-target-binding",
        "runtime",
        ("player-core-strike",),
        "The granted Strike must bind the primary Strike's exact target.",
    ),
    (
        "alternate-attack-adjudication",
        "runtime",
        ("player-core-strike",),
        "Beaks are named, while similar attacks require adjudication.",
    ),
    (
        "multiple-attack-penalty",
        "runtime",
        ("player-core-multiple-attack-penalty",),
        "Each acting participant's attack history requires runtime state.",
    ),
    (
        "persistent-bleed-rider-link",
        "source-link",
        (),
        "Each local jaws Strike retains an unresolved persistent bleed rider.",
    ),
)


def _bind_nested_contracts(
    deferral_specs: tuple[
        tuple[DeferralKind, DeferralPhase, tuple[str, ...], str],
        ...,
    ],
) -> tuple[
    Callable[[], SharedFeastNameResolution],
    Callable[[object], dict[str, Any]],
    Callable[[], tuple[SharedFeastDeferral, ...]],
    Callable[[object], dict[str, Any]],
]:
    resolution_type = SharedFeastNameResolution
    deferral_type = SharedFeastDeferral
    resolution_values = (
        "published-name-mismatch",
        "Shared Attack",
        "Shared Feast",
        "As sedacthy scout.",
        "core-mc1",
        "300.2",
        "preserve-distinct-names-and-defer-runtime-resolution",
    )
    canonical_deferrals = tuple(
        (
            mechanic_id,
            phase,
            tuple(provider_rule_ids),
            blocking_reason,
        )
        for (
            mechanic_id,
            phase,
            provider_rule_ids,
            blocking_reason,
        ) in deferral_specs
    )

    def validate_resolution(value: object) -> None:
        if type(value) is not resolution_type:
            raise TypeError(
                "name resolution must be exact SharedFeastNameResolution"
            )
        try:
            actual = tuple(
                object.__getattribute__(value, field_name)
                for field_name in resolution_type.__slots__
            )
        except (AttributeError, RecursionError) as failure:
            raise ValueError(
                "Shared Feast name resolution is incomplete or cyclic"
            ) from failure
        if actual != resolution_values or any(
            type(item) is not str for item in actual
        ):
            raise ValueError(
                "Shared Feast name resolution differs from reviewed source"
            )

    def serialize_resolution(value: object) -> dict[str, Any]:
        validate_resolution(value)
        assert type(value) is resolution_type
        return {
            "classification": value.classification,
            "base": {
                "sourceId": value.base_source_id,
                "locator": value.base_locator,
                "rawAbilityName": value.base_raw_ability_name,
            },
            "inherited": {
                "rawAbilityName": value.inherited_raw_ability_name,
                "sourceText": value.inheritance_source_text,
            },
            "disposition": value.disposition,
            "runtimeResolution": "deferred",
        }

    def make_resolution() -> SharedFeastNameResolution:
        return resolution_type(*resolution_values)

    def validate_deferral(value: object) -> None:
        if type(value) is not deferral_type:
            raise TypeError("Shared Feast deferral must use its exact type")
        try:
            actual = (
                object.__getattribute__(value, "mechanic_id"),
                object.__getattribute__(value, "phase"),
                object.__getattribute__(value, "provider_rule_ids"),
                object.__getattribute__(value, "blocking_reason"),
            )
        except (AttributeError, RecursionError) as failure:
            raise ValueError(
                "Shared Feast deferral is incomplete or cyclic"
            ) from failure
        if (
            actual not in canonical_deferrals
            or type(actual[0]) is not str
            or type(actual[1]) is not str
            or type(actual[2]) is not tuple
            or any(type(item) is not str for item in actual[2])
            or type(actual[3]) is not str
        ):
            raise ValueError(
                "Shared Feast deferral differs from the reviewed contract"
            )

    def serialize_deferral(value: object) -> dict[str, Any]:
        validate_deferral(value)
        assert type(value) is deferral_type
        return {
            "mechanicId": value.mechanic_id,
            "phase": value.phase,
            "providerRuleIds": list(value.provider_rule_ids),
            "blockingReason": value.blocking_reason,
            "status": "deferred",
        }

    def fresh_deferrals() -> tuple[SharedFeastDeferral, ...]:
        return tuple(deferral_type(*spec) for spec in canonical_deferrals)

    resolution_type.__post_init__ = validate_resolution
    resolution_type.as_serialized = serialize_resolution
    deferral_type.__post_init__ = validate_deferral
    deferral_type.as_serialized = serialize_deferral
    return (
        make_resolution,
        serialize_resolution,
        fresh_deferrals,
        serialize_deferral,
    )


(
    _make_name_resolution,
    _serialize_name_resolution,
    _fresh_deferrals,
    _serialize_deferral,
) = _bind_nested_contracts(_DEFERRAL_SPECS)


@final
@dataclass(frozen=True, slots=True)
class CompiledSharedFeast:
    """One authority-linked, non-executable Sedacthy family production."""

    source_id: str
    locator: str
    creature_name: str
    production: ProductionKind
    raw_ability_name: str
    action_cost: int
    source_text: str
    primary_strike_name: str
    primary_strike_kind: Literal["melee"]
    attack_modifier: int
    damage_source_text: str
    name_resolution: SharedFeastNameResolution
    ability_rule: VerifiedRuleReceipt
    base_ability_rule: VerifiedRuleReceipt
    jaws_rule: VerifiedRuleReceipt
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    deferrals: tuple[SharedFeastDeferral, ...]
    runtime_ready: bool

    def __post_init__(self) -> None:
        raise TypeError("compiled Shared Feast contract is not bound")

    def as_serialized(
        self,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        raise TypeError("compiled Shared Feast contract is not bound")


def _initialized_slots(
    value: object,
    exact_type: type,
    label: str,
) -> tuple[object, ...]:
    if type(value) is not exact_type:
        raise TypeError(f"{label} must use its exact contract type")
    try:
        return tuple(
            object.__getattribute__(value, field_name)
            for field_name in exact_type.__slots__
        )
    except (AttributeError, RecursionError) as failure:
        raise ValueError(f"{label} is incomplete or cyclic") from failure


def _exact_text(
    value: object,
    label: str,
    _maximum_source_text_bytes: int = MAX_SOURCE_TEXT_BYTES,
) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > _maximum_source_text_bytes
    ):
        raise ValueError(f"{label} must be exact bounded source text")
    return value


def _validate_compiled_structure(
    value: object,
    resolution_serializer: Callable[[object], dict[str, Any]],
    deferral_serializer: Callable[[object], dict[str, Any]],
    _compiled_type: type[CompiledSharedFeast] = CompiledSharedFeast,
    _deferral_type: type[SharedFeastDeferral] = SharedFeastDeferral,
    _rule_receipt_type: type[VerifiedRuleReceipt] = VerifiedRuleReceipt,
    _initialized_slots_impl: Callable[
        [object, type, str],
        tuple[object, ...],
    ] = _initialized_slots,
    _exact_text_impl: Callable[[object, str], str] = _exact_text,
) -> None:
    fields = _initialized_slots_impl(
        value,
        _compiled_type,
        "compiled Shared Feast",
    )
    assert type(value) is _compiled_type
    if (
        type(value.source_id) is not str
        or value.source_id != "core-mc1"
        or type(value.locator) is not str
        or value.locator not in ("300.2", "300.4", "301.1")
    ):
        raise ValueError("compiled Shared Feast source identity is invalid")
    _exact_text_impl(value.creature_name, "compiled creature name")
    if (
        type(value.production) is not str
        or value.production
        not in ("base-shared-attack", "shared-feast-inheritance")
    ):
        raise ValueError("compiled Shared Feast production is invalid")
    if (
        type(value.raw_ability_name) is not str
        or value.raw_ability_name not in ("Shared Attack", "Shared Feast")
        or type(value.action_cost) is not int
        or value.action_cost != 2
    ):
        raise ValueError("compiled Shared Feast ability fields are invalid")
    _exact_text_impl(
        value.source_text,
        "compiled Shared Feast source text",
    )
    if (
        type(value.primary_strike_name) is not str
        or value.primary_strike_name != "jaws"
        or type(value.primary_strike_kind) is not str
        or value.primary_strike_kind != "melee"
        or type(value.attack_modifier) is not int
        or value.attack_modifier <= 0
        or value.attack_modifier > 999
    ):
        raise ValueError("compiled Shared Feast jaws fields are invalid")
    _exact_text_impl(value.damage_source_text, "compiled jaws damage")
    resolution_serializer(value.name_resolution)
    for rule_name in (
        "ability_rule",
        "base_ability_rule",
        "jaws_rule",
    ):
        if type(getattr(value, rule_name)) is not _rule_receipt_type:
            raise TypeError(f"compiled Shared Feast {rule_name} is invalid")
    if (
        type(value.provider_rules) is not tuple
        or any(
            type(item) is not _rule_receipt_type
            for item in value.provider_rules
        )
    ):
        raise TypeError("compiled Shared Feast providers are invalid")
    if (
        type(value.deferrals) is not tuple
        or not value.deferrals
        or any(
            type(item) is not _deferral_type
            for item in value.deferrals
        )
    ):
        raise TypeError("compiled Shared Feast deferrals are invalid")
    for deferral in value.deferrals:
        deferral_serializer(deferral)
    if value.runtime_ready is not False:
        raise ValueError("Shared Feast cannot claim runtime readiness")
    if len(fields) != len(_compiled_type.__slots__):
        raise AssertionError("compiled Shared Feast field census is invalid")


def _same_requirement(
    left: object,
    right: RuleRequirement,
    canonical_bytes: Callable[[Any], bytes],
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _serialize_requirement: Callable[
        [RuleRequirement],
        dict[str, Any],
    ] = RuleRequirement.as_serialized,
) -> bool:
    if (
        type(left) is not _requirement_type
        or type(right) is not _requirement_type
    ):
        return False
    try:
        return canonical_bytes(
            _serialize_requirement(left)
        ) == canonical_bytes(
            _serialize_requirement(right)
        )
    except (AttributeError, RecursionError, TypeError, ValueError):
        return False


def _same_receipt(
    left: object,
    right: object,
    canonical_bytes: Callable[[Any], bytes],
    _receipt_type: type[SourceReceipt] = SourceReceipt,
    _serialize_receipt: Callable[
        [SourceReceipt],
        dict[str, Any],
    ] = SourceReceipt.as_serialized,
) -> bool:
    if type(left) is not _receipt_type or type(right) is not _receipt_type:
        return False
    try:
        return canonical_bytes(
            _serialize_receipt(left)
        ) == canonical_bytes(
            _serialize_receipt(right)
        )
    except (AttributeError, RecursionError, TypeError, ValueError):
        return False


def _ability_shape(
    selection: VerifiedSourceSelection,
    spec: _ProductionSpec,
    _raw_object_type: type[RawSourceObject] = RawSourceObject,
    _raw_member_type: type[RawSourceMember] = RawSourceMember,
    _error_type: type[SharedFeastCompileError] = SharedFeastCompileError,
) -> None:
    block = selection.carrier.raw_block
    if (
        type(block) is not _raw_object_type
        or type(block.members) is not tuple
        or len(block.members) != 2
        or any(type(item) is not _raw_member_type for item in block.members)
        or tuple(item.key for item in block.members)
        != ("Action", "Description")
        or type(block.members[0].value) is not str
        or block.members[0].value != "two"
        or type(block.members[1].value) is not str
        or block.members[1].value != spec.ability_source_text
        or type(selection.raw_value) is not str
        or selection.raw_value != spec.ability_source_text
        or type(selection.selected_value) is not str
        or selection.selected_value != spec.ability_source_text
    ):
        raise _error_type(
            "verified Shared Feast ability differs from reviewed source"
        )


def _jaws_shape(
    selection: VerifiedSourceSelection,
    spec: _ProductionSpec,
    _raw_object_type: type[RawSourceObject] = RawSourceObject,
    _raw_member_type: type[RawSourceMember] = RawSourceMember,
    _error_type: type[SharedFeastCompileError] = SharedFeastCompileError,
) -> None:
    block = selection.carrier.raw_block
    if (
        type(block) is not _raw_object_type
        or type(block.members) is not tuple
        or len(block.members) != 3
        or any(type(item) is not _raw_member_type for item in block.members)
        or tuple(item.key for item in block.members)
        != ("Name", "Attack", "Damage")
        or block.members[0].value != "jaws"
        or type(block.members[1].value) is not str
        or block.members[1].value != spec.attack_source_text
        or type(block.members[2].value) is not str
        or block.members[2].value != spec.damage_source_text
        or type(selection.raw_value) is not str
        or selection.raw_value != spec.damage_source_text
        or type(selection.selected_value) is not str
        or selection.selected_value != spec.damage_source_text
    ):
        raise _error_type(
            "verified local jaws differs from reviewed source"
        )


def _resolve_exact_rule(
    authority: SourceAuthorityAdapter,
    requirement: RuleRequirement,
    canonical_bytes: Callable[[Any], bytes],
    same_requirement_impl: Callable[
        [object, RuleRequirement, Callable[[Any], bytes]],
        bool,
    ],
    _rule_receipt_type: type[VerifiedRuleReceipt] = VerifiedRuleReceipt,
    _error_type: type[SharedFeastCompileError] = SharedFeastCompileError,
) -> VerifiedRuleReceipt:
    rule = authority.validate_rule(authority.resolve_rule(requirement))
    authority.validate_selection(rule.selection)
    if (
        type(rule) is not _rule_receipt_type
        or rule.rule_id != requirement.rule_id
        or not same_requirement_impl(
            rule.requirement,
            requirement,
            canonical_bytes,
        )
    ):
        raise _error_type(
            f"verified rule differs from review: {requirement.rule_id}"
        )
    return rule


def _find_consumer(
    authority: SourceAuthorityAdapter,
    receipt: SourceReceipt,
    specs: tuple[_ProductionSpec, ...],
    canonical_bytes: Callable[[Any], bytes],
    ability_requirement_impl: Callable[
        [_ProductionSpec],
        RuleRequirement,
    ],
    resolve_exact_rule_impl: Callable[..., VerifiedRuleReceipt],
    same_requirement_impl: Callable[
        [object, RuleRequirement, Callable[[Any], bytes]],
        bool,
    ],
    same_receipt_impl: Callable[
        [object, object, Callable[[Any], bytes]],
        bool,
    ],
    _authority_type: type[SourceAuthorityAdapter] = SourceAuthorityAdapter,
    _receipt_type: type[SourceReceipt] = SourceReceipt,
    _error_type: type[SharedFeastCompileError] = SharedFeastCompileError,
) -> tuple[VerifiedSourceSelection, VerifiedRuleReceipt, _ProductionSpec]:
    if type(authority) is not _authority_type:
        raise TypeError(
            "Shared Feast compilation requires SourceAuthorityAdapter"
        )
    if type(receipt) is not _receipt_type:
        raise TypeError(
            "Shared Feast compilation requires an exact SourceReceipt"
        )
    selection = authority.validate_selection(authority.reload(receipt))
    candidates = tuple(
        spec
        for spec in specs
        if selection.address.source_id == "core-mc1"
        and selection.address.locator == spec.locator
    )
    matches: list[tuple[VerifiedRuleReceipt, _ProductionSpec]] = []
    for spec in candidates:
        rule = resolve_exact_rule_impl(
            authority,
            ability_requirement_impl(spec),
            canonical_bytes,
            same_requirement_impl,
        )
        if same_receipt_impl(
            rule.receipt,
            selection.receipt,
            canonical_bytes,
        ):
            matches.append((rule, spec))
    if len(matches) != 1:
        raise _error_type(
            "consumer is not one exact reviewed Shared Feast production"
        )
    rule, spec = matches[0]
    authority.require_shared_authority(selection, (rule,))
    return selection, rule, spec


def _provider_map(
    specs: tuple[tuple[str, str, str, str], ...],
) -> dict[str, tuple[str, str, str, str]]:
    result: dict[str, tuple[str, str, str, str]] = {}
    for spec in specs:
        if type(spec[0]) is not str or spec[0] in result:
            raise AssertionError("reviewed Shared Feast providers are invalid")
        result[spec[0]] = spec
    return result


def _resolve_evidence(
    authority: SourceAuthorityAdapter,
    ability_selection: VerifiedSourceSelection,
    ability_rule: VerifiedRuleReceipt,
    spec: _ProductionSpec,
    production_specs: tuple[_ProductionSpec, ...],
    provider_specs: tuple[tuple[str, str, str, str], ...],
    canonical_bytes: Callable[[Any], bytes],
    ability_requirement_impl: Callable[
        [_ProductionSpec],
        RuleRequirement,
    ],
    jaws_requirement_impl: Callable[
        [_ProductionSpec],
        RuleRequirement,
    ],
    provider_requirement_impl: Callable[
        [tuple[str, str, str, str]],
        RuleRequirement,
    ],
    resolve_exact_rule_impl: Callable[..., VerifiedRuleReceipt],
    same_requirement_impl: Callable[
        [object, RuleRequirement, Callable[[Any], bytes]],
        bool,
    ],
    _base_ability_rule_id: str = _BASE_ABILITY_RULE_ID,
) -> tuple[
    VerifiedRuleReceipt,
    VerifiedRuleReceipt,
    tuple[VerifiedRuleReceipt, ...],
]:
    base_rule = (
        ability_rule
        if spec.ability_rule_id == _base_ability_rule_id
        else resolve_exact_rule_impl(
            authority,
            ability_requirement_impl(production_specs[0]),
            canonical_bytes,
            same_requirement_impl,
        )
    )
    jaws_rule = resolve_exact_rule_impl(
        authority,
        jaws_requirement_impl(spec),
        canonical_bytes,
        same_requirement_impl,
    )
    providers = tuple(
        resolve_exact_rule_impl(
            authority,
            provider_requirement_impl(provider_spec),
            canonical_bytes,
            same_requirement_impl,
        )
        for provider_spec in provider_specs
    )
    rules = (
        (ability_rule, jaws_rule, *providers)
        if base_rule is ability_rule
        else (ability_rule, base_rule, jaws_rule, *providers)
    )
    authority.require_shared_authority(ability_selection, rules)
    return base_rule, jaws_rule, providers


def _canonical_compiled(
    spec: _ProductionSpec,
    ability_rule: VerifiedRuleReceipt,
    base_ability_rule: VerifiedRuleReceipt,
    jaws_rule: VerifiedRuleReceipt,
    providers: tuple[VerifiedRuleReceipt, ...],
    make_resolution: Callable[[], SharedFeastNameResolution],
    fresh_deferrals: Callable[[], tuple[SharedFeastDeferral, ...]],
    _compiled_type: type[CompiledSharedFeast] = CompiledSharedFeast,
) -> CompiledSharedFeast:
    return _compiled_type(
        source_id="core-mc1",
        locator=spec.locator,
        creature_name=spec.creature_name,
        production=spec.production,
        raw_ability_name=spec.raw_ability_name,
        action_cost=2,
        source_text=spec.ability_source_text,
        primary_strike_name="jaws",
        primary_strike_kind="melee",
        attack_modifier=spec.attack_modifier,
        damage_source_text=spec.damage_source_text,
        name_resolution=make_resolution(),
        ability_rule=ability_rule,
        base_ability_rule=base_ability_rule,
        jaws_rule=jaws_rule,
        provider_rules=providers,
        deferrals=fresh_deferrals(),
        runtime_ready=False,
    )


def _compiled_payload(
    value: CompiledSharedFeast,
    serialize_resolution: Callable[[object], dict[str, Any]],
    serialize_deferral: Callable[[object], dict[str, Any]],
    _serialize_rule_receipt: Callable[
        [VerifiedRuleReceipt],
        dict[str, Any],
    ] = VerifiedRuleReceipt.as_serialized,
) -> dict[str, Any]:
    return {
        "familyId": "shared-feast",
        "compilerId": "shared-feast-verified-source",
        "supportState": "compile-only",
        "runtimeReady": False,
        "sourceId": value.source_id,
        "locator": value.locator,
        "creatureName": value.creature_name,
        "production": value.production,
        "ability": {
            "rawName": value.raw_ability_name,
            "actionCost": value.action_cost,
            "sourceText": value.source_text,
        },
        "localPrimaryStrike": {
            "name": value.primary_strike_name,
            "kind": value.primary_strike_kind,
            "attackModifier": value.attack_modifier,
            "damageSourceText": value.damage_source_text,
        },
        "authoredEffect": {
            "primaryAction": "jaws-strike",
            "onPrimaryHit": {
                "choiceOwner": "activity-actor",
                "chosenActor": "ally",
                "cost": "reaction",
                "grantedAction": "strike",
                "target": "same-target",
                "namedAlternatives": ["jaws", "beak"],
                "similarAttackPolicy": "deferred-adjudication",
            },
        },
        "nameResolution": serialize_resolution(value.name_resolution),
        "consumerEvidence": {
            "ability": _serialize_rule_receipt(
                value.ability_rule
            ),
            "baseAbility": _serialize_rule_receipt(
                value.base_ability_rule
            ),
            "localJaws": _serialize_rule_receipt(
                value.jaws_rule
            ),
        },
        "providers": [
            _serialize_rule_receipt(item)
            for item in value.provider_rules
        ],
        "deferredMechanics": [
            serialize_deferral(item) for item in value.deferrals
        ],
    }


def _validated_shape(
    authority: SourceAuthorityAdapter,
    value: CompiledSharedFeast,
    production_specs: tuple[_ProductionSpec, ...],
    provider_specs: tuple[tuple[str, str, str, str], ...],
    canonical_bytes: Callable[[Any], bytes],
    validate_structure: Callable[[object], None],
    payload_impl: Callable[[CompiledSharedFeast], dict[str, Any]],
    ability_requirement_impl: Callable[
        [_ProductionSpec],
        RuleRequirement,
    ],
    jaws_requirement_impl: Callable[
        [_ProductionSpec],
        RuleRequirement,
    ],
    provider_requirement_impl: Callable[
        [tuple[str, str, str, str]],
        RuleRequirement,
    ],
    same_requirement_impl: Callable[
        [object, RuleRequirement, Callable[[Any], bytes]],
        bool,
    ],
    ability_shape_impl: Callable[
        [VerifiedSourceSelection, _ProductionSpec],
        None,
    ],
    jaws_shape_impl: Callable[
        [VerifiedSourceSelection, _ProductionSpec],
        None,
    ],
    provider_map_impl: Callable[
        [tuple[tuple[str, str, str, str], ...]],
        dict[str, tuple[str, str, str, str]],
    ],
    _authority_type: type[SourceAuthorityAdapter] = SourceAuthorityAdapter,
    _error_type: type[SharedFeastCompileError] = SharedFeastCompileError,
) -> tuple[
    _ProductionSpec,
    VerifiedRuleReceipt,
    VerifiedRuleReceipt,
    VerifiedRuleReceipt,
    tuple[VerifiedRuleReceipt, ...],
    dict[str, Any],
]:
    if type(authority) is not _authority_type:
        raise TypeError(
            "compiled Shared Feast requires SourceAuthorityAdapter"
        )
    validate_structure(value)
    ability_rule = authority.validate_rule(value.ability_rule)
    candidates = tuple(
        spec
        for spec in production_specs
        if spec.ability_rule_id == ability_rule.rule_id
    )
    if len(candidates) != 1:
        raise _error_type(
            "compiled ability is outside the reviewed source family"
        )
    spec = candidates[0]
    expected_ability = ability_requirement_impl(spec)
    if not same_requirement_impl(
        ability_rule.requirement,
        expected_ability,
        canonical_bytes,
    ):
        raise _error_type(
            "compiled ability retained the wrong reviewed requirement"
        )
    ability_selection = authority.validate_selection(
        ability_rule.selection
    )
    ability_shape_impl(ability_selection, spec)

    base_rule = authority.validate_rule(value.base_ability_rule)
    expected_base = ability_requirement_impl(production_specs[0])
    if not same_requirement_impl(
        base_rule.requirement,
        expected_base,
        canonical_bytes,
    ):
        raise _error_type(
            "compiled base ability differs from reviewed Shared Attack"
        )
    base_selection = authority.validate_selection(base_rule.selection)
    ability_shape_impl(base_selection, production_specs[0])

    jaws_rule = authority.validate_rule(value.jaws_rule)
    expected_jaws = jaws_requirement_impl(spec)
    if not same_requirement_impl(
        jaws_rule.requirement,
        expected_jaws,
        canonical_bytes,
    ):
        raise _error_type(
            "compiled jaws retained the wrong reviewed requirement"
        )
    jaws_selection = authority.validate_selection(jaws_rule.selection)
    jaws_shape_impl(jaws_selection, spec)

    if (
        type(value.provider_rules) is not tuple
        or tuple(item.rule_id for item in value.provider_rules)
        != tuple(item[0] for item in provider_specs)
    ):
        raise SharedFeastCompileError(
            "compiled provider order or membership is invalid"
        )
    provider_by_id = provider_map_impl(provider_specs)
    verified_providers: list[VerifiedRuleReceipt] = []
    for provider in value.provider_rules:
        verified = authority.validate_rule(provider)
        expected_provider = provider_requirement_impl(
            provider_by_id[verified.rule_id]
        )
        if not same_requirement_impl(
            verified.requirement,
            expected_provider,
            canonical_bytes,
        ):
            raise _error_type(
                "compiled provider retained the wrong reviewed requirement"
            )
        authority.validate_selection(verified.selection)
        verified_providers.append(verified)

    rules = (
        (ability_rule, jaws_rule, *tuple(verified_providers))
        if base_rule is ability_rule
        else (
            ability_rule,
            base_rule,
            jaws_rule,
            *tuple(verified_providers),
        )
    )
    authority.require_shared_authority(ability_selection, rules)
    authority.require_shared_authority(
        base_selection,
        (base_rule,),
    )
    authority.require_shared_authority(
        jaws_selection,
        (jaws_rule,),
    )
    payload = payload_impl(value)
    canonical_bytes(payload)
    return (
        spec,
        ability_rule,
        base_rule,
        jaws_rule,
        tuple(verified_providers),
        payload,
    )


def _validate_compiled(
    authority: SourceAuthorityAdapter,
    value: CompiledSharedFeast,
    production_specs: tuple[_ProductionSpec, ...],
    provider_specs: tuple[tuple[str, str, str, str], ...],
    canonical_bytes: Callable[[Any], bytes],
    validate_structure: Callable[[object], None],
    payload_impl: Callable[[CompiledSharedFeast], dict[str, Any]],
    make_resolution: Callable[[], SharedFeastNameResolution],
    fresh_deferrals: Callable[[], tuple[SharedFeastDeferral, ...]],
    validated_shape_impl: Callable[..., tuple[Any, ...]],
    canonical_compiled_impl: Callable[..., CompiledSharedFeast],
    ability_requirement_impl: Callable[
        [_ProductionSpec],
        RuleRequirement,
    ],
    jaws_requirement_impl: Callable[
        [_ProductionSpec],
        RuleRequirement,
    ],
    provider_requirement_impl: Callable[
        [tuple[str, str, str, str]],
        RuleRequirement,
    ],
    same_requirement_impl: Callable[
        [object, RuleRequirement, Callable[[Any], bytes]],
        bool,
    ],
    ability_shape_impl: Callable[
        [VerifiedSourceSelection, _ProductionSpec],
        None,
    ],
    jaws_shape_impl: Callable[
        [VerifiedSourceSelection, _ProductionSpec],
        None,
    ],
    provider_map_impl: Callable[
        [tuple[tuple[str, str, str, str], ...]],
        dict[str, tuple[str, str, str, str]],
    ],
    _error_type: type[SharedFeastCompileError] = SharedFeastCompileError,
) -> CompiledSharedFeast:
    (
        spec,
        ability_rule,
        base_rule,
        jaws_rule,
        providers,
        supplied_payload,
    ) = validated_shape_impl(
        authority,
        value,
        production_specs,
        provider_specs,
        canonical_bytes,
        validate_structure,
        payload_impl,
        ability_requirement_impl,
        jaws_requirement_impl,
        provider_requirement_impl,
        same_requirement_impl,
        ability_shape_impl,
        jaws_shape_impl,
        provider_map_impl,
    )
    canonical = canonical_compiled_impl(
        spec,
        ability_rule,
        base_rule,
        jaws_rule,
        providers,
        make_resolution,
        fresh_deferrals,
    )
    canonical_payload = validated_shape_impl(
        authority,
        canonical,
        production_specs,
        provider_specs,
        canonical_bytes,
        validate_structure,
        payload_impl,
        ability_requirement_impl,
        jaws_requirement_impl,
        provider_requirement_impl,
        same_requirement_impl,
        ability_shape_impl,
        jaws_shape_impl,
        provider_map_impl,
    )[-1]
    if canonical_bytes(supplied_payload) != canonical_bytes(
        canonical_payload
    ):
        raise _error_type(
            "compiled Shared Feast differs from canonical source derivation"
        )
    return value


def _bind_reviewed_api(
    production_specs: tuple[_ProductionSpec, ...],
    provider_specs: tuple[tuple[str, str, str, str], ...],
    deferral_specs: tuple[
        tuple[DeferralKind, DeferralPhase, tuple[str, ...], str],
        ...,
    ],
) -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    production_type = _ProductionSpec
    reviewed_productions = tuple(
        production_type(
            *(
                object.__getattribute__(spec, field_name)
                for field_name in production_type.__slots__
            )
        )
        for spec in production_specs
    )
    reviewed_providers = tuple(tuple(spec) for spec in provider_specs)
    reviewed_deferrals = tuple(
        (
            mechanic_id,
            phase,
            tuple(provider_rule_ids),
            blocking_reason,
        )
        for (
            mechanic_id,
            phase,
            provider_rule_ids,
            blocking_reason,
        ) in deferral_specs
    )
    authority_type = SourceAuthorityAdapter
    receipt_type = SourceReceipt
    compiled_type = CompiledSharedFeast
    canonical_bytes = canonical_json_bytes
    ability_requirement_impl = _ability_requirement
    jaws_requirement_impl = _jaws_requirement
    provider_requirement_impl = _provider_requirement
    consumer_requirements_impl = _consumer_requirements
    provider_requirements_impl = _provider_requirements
    same_requirement_impl = _same_requirement
    same_receipt_impl = _same_receipt
    resolve_exact_rule_impl = _resolve_exact_rule
    find_consumer_impl = _find_consumer
    provider_map_impl = _provider_map
    resolve_evidence_impl = _resolve_evidence
    ability_shape_impl = _ability_shape
    jaws_shape_impl = _jaws_shape
    canonical_compiled_impl = _canonical_compiled
    validated_shape_impl = _validated_shape
    validate_compiled_base = _validate_compiled
    validate_structure_base = _validate_compiled_structure
    make_resolution = _make_name_resolution
    serialize_resolution = _serialize_name_resolution
    fresh_deferrals = _fresh_deferrals
    serialize_deferral = _serialize_deferral
    compiled_payload_base = _compiled_payload

    if (
        len(reviewed_productions) != 3
        or len(reviewed_providers) != 4
        or len(reviewed_deferrals) != 8
    ):
        raise AssertionError("reviewed Shared Feast contract is incomplete")

    def validate_structure(value: object) -> None:
        validate_structure_base(
            value,
            serialize_resolution,
            serialize_deferral,
        )

    def payload_impl(value: CompiledSharedFeast) -> dict[str, Any]:
        return compiled_payload_base(
            value,
            serialize_resolution,
            serialize_deferral,
        )

    def validate_impl(
        authority: SourceAuthorityAdapter,
        value: CompiledSharedFeast,
    ) -> CompiledSharedFeast:
        return validate_compiled_base(
            authority,
            value,
            reviewed_productions,
            reviewed_providers,
            canonical_bytes,
            validate_structure,
            payload_impl,
            make_resolution,
            fresh_deferrals,
            validated_shape_impl,
            canonical_compiled_impl,
            ability_requirement_impl,
            jaws_requirement_impl,
            provider_requirement_impl,
            same_requirement_impl,
            ability_shape_impl,
            jaws_shape_impl,
            provider_map_impl,
        )

    def shared_feast_consumer_requirements(
    ) -> tuple[RuleRequirement, ...]:
        """Return fresh exact ability and local-jaws requirements."""

        return consumer_requirements_impl(
            reviewed_productions,
            ability_requirement_impl,
            jaws_requirement_impl,
        )

    def shared_feast_provider_requirements(
    ) -> tuple[RuleRequirement, ...]:
        """Return fresh exact Player Core provider requirements."""

        return provider_requirements_impl(
            reviewed_providers,
            provider_requirement_impl,
        )

    def compile_shared_feast(
        authority: SourceAuthorityAdapter,
        ability_receipt: SourceReceipt,
        /,
    ) -> CompiledSharedFeast:
        """Compile one authority-reloaded reviewed production."""

        if type(authority) is not authority_type:
            raise TypeError(
                "Shared Feast compilation requires SourceAuthorityAdapter"
            )
        if type(ability_receipt) is not receipt_type:
            raise TypeError(
                "Shared Feast compilation requires an exact SourceReceipt"
            )
        selection, ability_rule, spec = find_consumer_impl(
            authority,
            ability_receipt,
            reviewed_productions,
            canonical_bytes,
            ability_requirement_impl,
            resolve_exact_rule_impl,
            same_requirement_impl,
            same_receipt_impl,
        )
        ability_shape_impl(selection, spec)
        base_rule, jaws_rule, providers = resolve_evidence_impl(
            authority,
            selection,
            ability_rule,
            spec,
            reviewed_productions,
            reviewed_providers,
            canonical_bytes,
            ability_requirement_impl,
            jaws_requirement_impl,
            provider_requirement_impl,
            resolve_exact_rule_impl,
            same_requirement_impl,
        )
        jaws_shape_impl(
            authority.validate_selection(jaws_rule.selection),
            spec,
        )
        result = canonical_compiled_impl(
            spec,
            ability_rule,
            base_rule,
            jaws_rule,
            providers,
            make_resolution,
            fresh_deferrals,
        )
        return validate_impl(authority, result)

    def compile_shared_feast_census(
        authority: SourceAuthorityAdapter,
        /,
    ) -> tuple[CompiledSharedFeast, ...]:
        """Compile all three reviewed productions in source order."""

        if type(authority) is not authority_type:
            raise TypeError(
                "Shared Feast census requires SourceAuthorityAdapter"
            )
        result: list[CompiledSharedFeast] = []
        for spec in reviewed_productions:
            ability_rule = resolve_exact_rule_impl(
                authority,
                ability_requirement_impl(spec),
                canonical_bytes,
                same_requirement_impl,
            )
            result.append(
                compile_shared_feast(authority, ability_rule.receipt)
            )
        compiled = tuple(result)
        if len(compiled) != 3:
            raise AssertionError("reviewed Shared Feast census is incomplete")
        return compiled

    def validate_compiled_shared_feast(
        authority: SourceAuthorityAdapter,
        value: CompiledSharedFeast,
        /,
    ) -> CompiledSharedFeast:
        """Revalidate and canonically rederive every public field."""

        return validate_impl(authority, value)

    def compiled_post_init(value: CompiledSharedFeast) -> None:
        if type(value) is not compiled_type:
            raise TypeError(
                "compiled Shared Feast must use its exact contract type"
            )
        validate_structure(value)

    def compiled_as_serialized(
        value: CompiledSharedFeast,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        validate_impl(authority, value)
        result = payload_impl(value)
        canonical_bytes(result)
        return result

    return (
        shared_feast_consumer_requirements,
        shared_feast_provider_requirements,
        compile_shared_feast,
        compile_shared_feast_census,
        validate_compiled_shared_feast,
        compiled_post_init,
        compiled_as_serialized,
    )


(
    shared_feast_consumer_requirements,
    shared_feast_provider_requirements,
    compile_shared_feast,
    compile_shared_feast_census,
    validate_compiled_shared_feast,
    _compiled_post_init,
    _compiled_as_serialized,
) = _bind_reviewed_api(
    _PRODUCTION_SPECS,
    _PROVIDER_SPECS,
    _DEFERRAL_SPECS,
)
CompiledSharedFeast.__post_init__ = _compiled_post_init
CompiledSharedFeast.as_serialized = _compiled_as_serialized


__all__ = [
    "BASE_LOCATOR",
    "BASE_RAW_ABILITY_NAME",
    "COMPILER_ID",
    "CONSUMER_REQUIREMENT_COUNT",
    "CompiledSharedFeast",
    "FAMILY_ID",
    "INHERITANCE_SOURCE_TEXT",
    "INHERITED_RAW_ABILITY_NAME",
    "MECHANIC_TYPE",
    "PRIMARY_STRIKE_NAME",
    "PROVIDER_REQUIREMENT_COUNT",
    "SharedFeastCompileError",
    "SharedFeastDeferral",
    "SharedFeastNameResolution",
    "compile_shared_feast",
    "compile_shared_feast_census",
    "shared_feast_consumer_requirements",
    "shared_feast_provider_requirements",
    "validate_compiled_shared_feast",
]

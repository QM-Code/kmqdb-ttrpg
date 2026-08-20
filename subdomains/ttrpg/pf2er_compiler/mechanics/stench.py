"""Compile the reviewed Monster Core Stench aura source grammars."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, fields
from fractions import Fraction
import json
import re
from types import MappingProxyType
from typing import Any, Callable, final

from ..errors import EngineInputError
from ..geometry import grid_distance_feet
from ..ranged_cover import squares_with_line_of_effect_from_point

from .contracts import (
    AbilityCompilerRegistration,
    AbilityCompilerPatch,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RawSourceValue,
    RuleReference,
)
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
)
from .source_values import parse_decimal_integer


STENCH_LABEL = "Stench"
STENCH_MECHANIC_TYPE = "stench-aura"
STENCH_SOURCE_ID = "core-mc1"
STENCH_TRAITS = ("aura", "olfactory")
STENCH_FAMILY = "stench"
STENCH_SAVE_EVENT_TYPE = "stench-save"
STENCH_IMMUNITY_ROUNDS = 10
STENCH_ABILITY_RULE_REF = "pf2er.rule:xulgath-warrior-stench"
OLFACTORY_AURA_ELIGIBILITY = frozenset(
    {
        "affected",
        "source-excluded",
        "gm-exempt",
        "cannot-smell",
    }
)
_SEMANTIC_ID_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*:"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)
STENCH_RULE_REFS = MappingProxyType(
    {
        "aura": "pf2er.rule:aura",
        "duration": "pf2er.rule:duration",
        "emanation": "pf2er.rule:emanation",
        "fortitude": "pf2er.rule:fortitude-save",
        "sickened": "pf2er.rule:sickened",
        "slowed": "pf2er.rule:slowed",
        "stench": STENCH_ABILITY_RULE_REF,
        "traits": "pf2er.rule:traits",
        "turnStart": "pf2er.rule:turn-start",
    }
)
STENCH_RUNTIME_OWNER = MappingProxyType(
    {"kind": "mechanic", "mechanicType": STENCH_MECHANIC_TYPE}
)
# The reviewed rules-engine source envelope is pinned locally so mechanics
# families remain import-independent.
MAX_STENCH_SOURCE_BYTES = 65_536
AURA_PROVIDER_RULE = MappingProxyType(
    {
        "ruleId": "core-mc1:ability-glossary#^.ability[003]",
        "sourceId": STENCH_SOURCE_ID,
        "locator": "358.2",
        "sourceOrdinal": 5,
        "sha256": (
            "3f30455106cbb35f3f791ee121f33ea5612636ffd692c4fbbe825667ffb2ec39"
        ),
        "digestField": "providerOrderedRuleSha256",
    }
)
STENCH_PROVIDER_RULE = MappingProxyType(
    {
        "ruleId": "core-mc1:ability-glossary#^.ability[030]",
        "sourceId": STENCH_SOURCE_ID,
        "locator": "358.2",
        "sourceOrdinal": 32,
        "sha256": (
            "189c0083d5b9ae7db0abc7a4af237abbb3548e09cb903a2b254a0362afb1f968"
        ),
        "digestField": "providerOrderedRuleSha256",
    }
)


@dataclass(frozen=True, slots=True)
class StenchRuntimeHost:
    """Narrow encounter-kernel operations used by the Stench family."""

    participant_map: Callable[[dict[str, Any]], dict[str, dict[str, Any]]]
    definition_for: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    ability_by_mechanic: Callable[[dict[str, Any], str], dict[str, Any] | None]
    supported_ability: Callable[
        [dict[str, Any], str], dict[str, Any] | None
    ]
    state_effects: Callable[[dict[str, Any]], list[dict[str, Any]]]
    next_event_sequence: Callable[[dict[str, Any]], int]
    remove_effect_ids: Callable[[dict[str, Any], list[str]], list[str]]
    event_receipt_map: Callable[[dict[str, Any]], dict[int, dict[str, Any]]]
    participant_distance: Callable[[dict[str, Any], str, str], int]
    participants_have_line_of_effect: Callable[
        [dict[str, Any], str, str], bool
    ]
    normalize_olfactory_aura_adjudications: Callable[..., dict[str, Any] | None]
    map_relations: Callable[..., dict[str, Any]]
    effective_actor_dc: Callable[..., dict[str, Any]]
    effective_saving_throw: Callable[..., dict[str, Any]]
    d20_roll: Callable[[Any, str], int]
    attack_degree: Callable[[int, int, int], str]
    apply_condition_effect: Callable[..., dict[str, Any]]
    apply_sickened_contribution: Callable[..., dict[str, Any]]
    sickened_contribution_digest: Callable[[Any], str]
    action_event: Callable[..., dict[str, Any]]
    continue_suspended_stride: Callable[[dict[str, Any]], dict[str, Any]]
    continue_suspended_fly: Callable[[dict[str, Any]], dict[str, Any]]
    continue_turn_start: Callable[..., dict[str, Any]]

    def __post_init__(self) -> None:
        for field in fields(self):
            if not callable(getattr(self, field.name)):
                raise TypeError(
                    f"Stench runtime host {field.name} must be callable"
                )


def stench_provider_requirements() -> tuple[
    RuleRequirement,
    RuleRequirement,
]:
    """Return the reviewed duplicate-member provider selections."""

    return (
        RuleRequirement(
            rule_id=AURA_PROVIDER_RULE["ruleId"],
            source_id=STENCH_SOURCE_ID,
            locator=AURA_PROVIDER_RULE["locator"],
            carrier_path=(RawMemberStep("^.ability", 5),),
            expected_value_sha256=AURA_PROVIDER_RULE["sha256"],
        ),
        RuleRequirement(
            rule_id=STENCH_PROVIDER_RULE["ruleId"],
            source_id=STENCH_SOURCE_ID,
            locator=STENCH_PROVIDER_RULE["locator"],
            carrier_path=(RawMemberStep("^.ability", 32),),
            expected_value_sha256=STENCH_PROVIDER_RULE["sha256"],
        ),
    )


def _raw_serialized(value: RawSourceValue) -> object:
    if type(value) is RawSourceObject:
        if type(value.members) is not tuple or any(
            type(member) is not RawSourceMember
            or type(member.key) is not str
            for member in value.members
        ):
            raise TypeError(
                "raw source object must contain exact RawSourceMember values"
            )
        return {
            "$orderedObject": [
                [member.key, _raw_serialized(member.value)]
                for member in value.members
            ]
        }
    if type(value) is RawSourceArray:
        if type(value.items) is not tuple:
            raise TypeError(
                "raw source array items must be an exact tuple"
            )
        return [_raw_serialized(item) for item in value.items]
    if type(value) not in (str, int, float, bool, type(None)):
        raise TypeError("raw source primitive has a non-exact type")
    return value


def _raw_source_bytes(value: RawSourceValue) -> int:
    return len(
        json.dumps(
            _raw_serialized(value),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _is_exact_ability_source(source: object) -> bool:
    if type(source) is not AbilitySource:
        return False
    try:
        text_fields_are_exact = all(
            type(getattr(source, field_name)) is str
            for field_name in (
                "source_label",
                "kind",
                "trigger",
                "description",
                "source_id",
                "locator",
                "creature_name",
            )
        )
        traits = source.traits
        raw_member = source.raw_member
    except AttributeError:
        return False
    if not text_fields_are_exact:
        return False
    if type(traits) is not tuple or any(
        type(trait) is not str for trait in traits
    ):
        return False
    if type(raw_member) is not RawSourceMember:
        return False
    return type(raw_member.key) is str


def _stench_parameters(source: object) -> tuple[int, int] | None:
    """Return grid-aligned radius and DC from one exact raw production."""

    if not _is_exact_ability_source(source):
        return None
    assert type(source) is AbilitySource
    raw_member = source.raw_member
    if raw_member.key != "!.Stench":
        return None

    raw_value = raw_member.value
    normalized_traits: tuple[str, ...]
    if type(raw_value) is RawSourceObject:
        if type(raw_value.members) is not tuple or len(
            raw_value.members
        ) != 2:
            return None
        traits_member, description_member = raw_value.members
        if (
            type(traits_member) is not RawSourceMember
            or type(description_member) is not RawSourceMember
            or type(traits_member.key) is not str
            or type(description_member.key) is not str
            or traits_member.key != "Traits"
            or description_member.key != "Description"
            or type(traits_member.value) is not RawSourceArray
            or type(traits_member.value.items) is not tuple
            or any(
                type(trait) is not str
                for trait in traits_member.value.items
            )
            or traits_member.value.items != ("aura", "olfactory")
            or type(description_member.value) is not str
        ):
            return None
        description = " ".join(description_member.value.split())
        normalized_traits = ("aura", "olfactory")
        match = re.fullmatch(
            r"(?P<radius>[1-9][0-9]*) feet, "
            r"DC (?P<dc>[1-9][0-9]*) \(page 360\)",
            description,
        )
    elif type(raw_value) is str:
        description = " ".join(raw_value.split())
        normalized_traits = ()
        match = re.fullmatch(
            r"\(aura, olfactory\) "
            r"(?P<radius>[1-9][0-9]*) feet, "
            r"DC (?P<dc>[1-9][0-9]*) \(page 360\)",
            description,
        )
    else:
        return None
    if _raw_source_bytes(raw_value) > 65_536:
        return None
    if (
        match is None
        or source.traits != normalized_traits
        or " ".join(source.description.split()) != description
    ):
        return None

    radius_feet = parse_decimal_integer(match.group("radius"))
    save_dc = parse_decimal_integer(match.group("dc"))
    if (
        radius_feet is None
        or save_dc is None
        or radius_feet <= 0
        or radius_feet % 5
        or save_dc <= 0
    ):
        return None
    return radius_feet, save_dc


def _compile_stench_unbound(
    source: object,
    /,
) -> AbilityCompilerPatch | None:
    """Parse one exact Stench production without claiming source authority."""

    parameters = _stench_parameters(source)
    if parameters is None:
        return None
    if (
        source.source_id != "core-mc1"
        or source.source_label != "Stench"
        or source.action_cost is not None
        or source.kind != "passive"
        or source.trigger
    ):
        return None
    radius_feet, save_dc = parameters

    return AbilityCompilerPatch(
        mechanic={
            "type": "stench-aura",
            "family": "stench",
            "geometry": {
                "type": "emanation",
                "radiusFeet": radius_feet,
                "boundary": "inclusive",
            },
            "triggers": [
                "outside-to-inside",
                "target-start-turn-inside",
            ],
            "savingThrow": {
                "type": "fortitude",
                "dc": save_dc,
            },
            "outcomes": {
                "critical-success": {
                    "temporaryImmunity": {
                        "family": "stench",
                        "duration": {
                            "unit": "rounds",
                            "value": 10,
                            "sourceUnit": "minutes",
                            "sourceValue": 1,
                        },
                    },
                },
                "success": {
                    "temporaryImmunity": {
                        "family": "stench",
                        "duration": {
                            "unit": "rounds",
                            "value": 10,
                            "sourceUnit": "minutes",
                            "sourceValue": 1,
                        },
                    },
                },
                "failure": {
                    "condition": "sickened",
                    "value": 1,
                },
                "critical-failure": {
                    "condition": "sickened",
                    "value": 1,
                    "linkedCondition": {
                        "condition": "slowed",
                        "value": 1,
                        "while": "target remains sickened",
                    },
                },
            },
            "rules": {
                "aura": {
                    **AURA_PROVIDER_RULE,
                },
                "stench": {
                    **STENCH_PROVIDER_RULE,
                },
                "traits": {
                    "sourceId": "core-pc1",
                    "locator": "452.1",
                },
                "emanation": {
                    "sourceId": "core-pc1",
                    "locator": "428.4",
                },
                "duration": {
                    "sourceId": "core-pc1",
                    "locator": "426.2",
                },
                "turnStart": {
                    "sourceId": "core-pc1",
                    "locator": "435.8",
                },
                "fortitude": {
                    "sourceId": "core-pc1",
                    "locator": "404.1",
                },
                "sickened": {
                    "sourceId": "core-pc1",
                    "locator": "446.4",
                },
                "slowed": {
                    "sourceId": "core-pc1",
                    "locator": "446.5",
                },
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        traits=("aura", "olfactory"),
    )


@final
class VerifiedStenchCompilation:
    """A compile-only view that rederives all output on every access."""

    __slots__ = (
        "_authority",
        "_consumer",
        "_ordered_providers",
        "_source",
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "VerifiedStenchCompilation can only be returned by "
            "compile_stench_verified"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError(
            "VerifiedStenchCompilation cannot be subclassed"
        )

    def _validated_state(
        self,
    ) -> tuple[
        AbilityCompilerPatch,
        SourceAuthorityAdapter,
        AbilitySource,
        VerifiedSourceSelection,
        tuple[VerifiedRuleReceipt, VerifiedRuleReceipt],
    ]:
        if type(self) is not __class__:
            raise TypeError(
                "VerifiedStenchCompilation subclasses are unsupported"
            )

        # Import the contracts here rather than trusting rebindable names in
        # this mechanic-family module.  The artifact is a structural view over
        # current authority, not a sealed cache of a previously issued patch.
        import json as _json
        import re as _re

        from .contracts import (
            AbilityCompilerPatch as _AbilityCompilerPatch,
            AbilitySource as _AbilitySource,
            RawSourceArray as _RawSourceArray,
            RawSourceMember as _RawSourceMember,
            RawSourceObject as _RawSourceObject,
            RuleReference as _RuleReference,
        )
        from .source_authority import (
            RawIndexStep as _RawIndexStep,
            RawMemberStep as _RawMemberStep,
            RuleRequirement as _RuleRequirement,
            SourceAddress as _SourceAddress,
            SourceAuthorityAdapter as _SourceAuthorityAdapter,
            SourceAuthorityError as _SourceAuthorityError,
            SourceReceipt as _SourceReceipt,
            VerifiedRuleReceipt as _VerifiedRuleReceipt,
            VerifiedSourceCarrier as _VerifiedSourceCarrier,
            VerifiedSourceSelection as _VerifiedSourceSelection,
        )

        def reject() -> None:
            raise TypeError(
                "VerifiedStenchCompilation failed structural revalidation"
            )

        def exact_path(value: object) -> tuple[object, ...]:
            if type(value) is not tuple:
                reject()
            for step in value:
                if type(step) is _RawMemberStep:
                    if (
                        type(step.raw_key) is not str
                        or type(step.member_ordinal) is not int
                        or step.member_ordinal < 0
                    ):
                        reject()
                elif type(step) is _RawIndexStep:
                    if (
                        type(step.item_ordinal) is not int
                        or step.item_ordinal < 0
                    ):
                        reject()
                else:
                    reject()
            return value

        def stench_value(
            value: object,
        ) -> tuple[str, tuple[str, ...], int, int, bytes]:
            if type(value) is _RawSourceObject:
                if (
                    type(value.members) is not tuple
                    or len(value.members) != 2
                ):
                    reject()
                traits_member, description_member = value.members
                if (
                    type(traits_member) is not _RawSourceMember
                    or type(description_member) is not _RawSourceMember
                    or type(traits_member.key) is not str
                    or type(description_member.key) is not str
                    or traits_member.key != "Traits"
                    or description_member.key != "Description"
                    or type(traits_member.value) is not _RawSourceArray
                    or type(traits_member.value.items) is not tuple
                    or any(
                        type(trait) is not str
                        for trait in traits_member.value.items
                    )
                    or traits_member.value.items
                    != ("aura", "olfactory")
                    or type(description_member.value) is not str
                ):
                    reject()
                description = " ".join(
                    description_member.value.split()
                )
                normalized_traits = ("aura", "olfactory")
                match = _re.fullmatch(
                    r"(?P<radius>[1-9][0-9]*) feet, "
                    r"DC (?P<dc>[1-9][0-9]*) \(page 360\)",
                    description,
                )
                serialized = _json.dumps(
                    {
                        "$orderedObject": [
                            [
                                "Traits",
                                ["aura", "olfactory"],
                            ],
                            [
                                "Description",
                                description_member.value,
                            ],
                        ]
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            elif type(value) is str:
                description = " ".join(value.split())
                normalized_traits = ()
                match = _re.fullmatch(
                    r"\(aura, olfactory\) "
                    r"(?P<radius>[1-9][0-9]*) feet, "
                    r"DC (?P<dc>[1-9][0-9]*) \(page 360\)",
                    description,
                )
                serialized = _json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            else:
                reject()
            if len(serialized) > 65_536 or match is None:
                reject()
            radius_text = match.group("radius")
            dc_text = match.group("dc")
            if len(radius_text) > 19 or len(dc_text) > 19:
                reject()
            radius_feet = int(radius_text)
            save_dc = int(dc_text)
            if (
                radius_feet <= 0
                or radius_feet > 9_223_372_036_854_775_807
                or radius_feet % 5
                or save_dc <= 0
                or save_dc > 9_223_372_036_854_775_807
            ):
                reject()
            return (
                description,
                normalized_traits,
                radius_feet,
                save_dc,
                serialized,
            )

        def exact_source(
            value: object,
        ) -> tuple[int, int, bytes]:
            if type(value) is not _AbilitySource:
                reject()
            for field_name in (
                "source_label",
                "kind",
                "trigger",
                "description",
                "source_id",
                "locator",
                "creature_name",
            ):
                if type(getattr(value, field_name)) is not str:
                    reject()
            if (
                not value.locator
                or value.locator != value.locator.strip()
                or not value.creature_name
                or value.creature_name != value.creature_name.strip()
                or type(value.traits) is not tuple
                or any(
                    type(trait) is not str
                    for trait in value.traits
                )
                or type(value.raw_member) is not _RawSourceMember
                or type(value.raw_member.key) is not str
                or value.raw_member.key != "!.Stench"
                or value.source_id != "core-mc1"
                or value.source_label != "Stench"
                or value.action_cost is not None
                or value.kind != "passive"
                or value.trigger != ""
            ):
                reject()
            (
                description,
                normalized_traits,
                radius_feet,
                save_dc,
                serialized,
            ) = stench_value(value.raw_member.value)
            if (
                value.traits != normalized_traits
                or " ".join(value.description.split()) != description
            ):
                reject()
            return radius_feet, save_dc, serialized

        def exact_address(value: object) -> None:
            if type(value) is not _SourceAddress:
                reject()
            for field_name in ("source_id", "locator", "section_id"):
                field = getattr(value, field_name)
                if (
                    type(field) is not str
                    or not field
                    or field != field.strip()
                ):
                    reject()
            exact_path(value.target_path)
            exact_path(value.carrier_path)
            exact_path(value.selection_path)

        def exact_carrier(value: object) -> None:
            if type(value) is not _VerifiedSourceCarrier:
                reject()
            for field_name in (
                "ruleset",
                "authority_digest",
                "source_id",
                "locator",
                "section_id",
                "block_sha256",
            ):
                if type(getattr(value, field_name)) is not str:
                    reject()
            exact_path(value.target_path)
            exact_path(value.carrier_path)
            if (
                value.ruleset != "pf2er"
                or type(value.raw_block) is not _RawSourceObject
                or type(value.raw_block.members) is not tuple
                or any(
                    type(member) is not _RawSourceMember
                    or type(member.key) is not str
                    for member in value.raw_block.members
                )
            ):
                reject()

        def exact_receipt(value: object) -> None:
            if (
                type(value) is not _SourceReceipt
                or type(value.ruleset) is not str
                or type(value.authority_digest) is not str
                or type(value.address) is not _SourceAddress
                or type(value.block_sha256) is not str
                or (
                    value.member_sha256 is not None
                    and type(value.member_sha256) is not str
                )
                or type(value.value_sha256) is not str
                or type(value.selection_sha256) is not str
            ):
                reject()
            exact_address(value.address)

        try:
            authority = object.__getattribute__(self, "_authority")
            source = object.__getattribute__(self, "_source")
            consumer = object.__getattribute__(self, "_consumer")
            providers = object.__getattribute__(
                self,
                "_ordered_providers",
            )
            if (
                type(authority) is not _SourceAuthorityAdapter
                or type(source) is not _AbilitySource
                or type(consumer) is not _VerifiedSourceSelection
                or type(providers) is not tuple
                or len(providers) != 2
                or any(
                    type(provider) is not _VerifiedRuleReceipt
                    for provider in providers
                )
            ):
                reject()

            # This performs the mandatory fresh address resolution against the
            # exact adapter before any consumer or provider fact is trusted.
            _SourceAuthorityAdapter.require_shared_authority(
                authority,
                consumer,
                providers,
            )

            radius_feet, save_dc, source_bytes = exact_source(source)

            exact_address(consumer.address)
            exact_carrier(consumer.carrier)
            exact_receipt(consumer.receipt)
            address = consumer.address
            carrier = consumer.carrier
            if (
                address.source_id != "core-mc1"
                or address.source_id != source.source_id
                or address.locator != source.locator
                or address.span is not None
                or len(address.selection_path) != 1
                or type(address.selection_path[0])
                is not _RawMemberStep
                or address.selection_path[0].raw_key != "!.Stench"
                or carrier.source_id != address.source_id
                or carrier.locator != address.locator
                or carrier.section_id != address.section_id
                or carrier.target_path != address.target_path
                or carrier.carrier_path != address.carrier_path
                or consumer.receipt.address != address
                or type(consumer.raw_member) is not _RawSourceMember
                or type(consumer.raw_member.key) is not str
                or consumer.raw_member.key != "!.Stench"
            ):
                reject()
            member_ordinal = address.selection_path[0].member_ordinal
            if member_ordinal >= len(carrier.raw_block.members):
                reject()
            selected_member = carrier.raw_block.members[member_ordinal]
            if (
                type(selected_member) is not _RawSourceMember
                or type(selected_member.key) is not str
                or selected_member.key != "!.Stench"
            ):
                reject()
            selected_parts = stench_value(selected_member.value)
            member_parts = stench_value(consumer.raw_member.value)
            raw_parts = stench_value(consumer.raw_value)
            selected_value_parts = stench_value(
                consumer.selected_value
            )
            creature_names = tuple(
                member.value
                for member in carrier.raw_block.members
                if member.key == "Name"
            )
            if (
                len(creature_names) != 1
                or type(creature_names[0]) is not str
                or creature_names[0] != source.creature_name
                or selected_parts[4] != source_bytes
                or member_parts[4] != source_bytes
                or raw_parts[4] != source_bytes
                or selected_value_parts[4] != source_bytes
                or selected_parts[:4] != member_parts[:4]
                or selected_parts[:4] != raw_parts[:4]
                or selected_parts[:4] != selected_value_parts[:4]
            ):
                reject()

            reviewed_requirements = (
                _RuleRequirement(
                    rule_id=(
                        "core-mc1:ability-glossary#^.ability[003]"
                    ),
                    source_id="core-mc1",
                    locator="358.2",
                    carrier_path=(
                        _RawMemberStep("^.ability", 5),
                    ),
                    expected_value_sha256=(
                        "3f30455106cbb35f3f791ee121f33ea5612636ffd"
                        "692c4fbbe825667ffb2ec39"
                    ),
                ),
                _RuleRequirement(
                    rule_id=(
                        "core-mc1:ability-glossary#^.ability[030]"
                    ),
                    source_id="core-mc1",
                    locator="358.2",
                    carrier_path=(
                        _RawMemberStep("^.ability", 32),
                    ),
                    expected_value_sha256=(
                        "189c0083d5b9ae7db0abc7a4af237abbb3548e09c"
                        "b903a2b254a0362afb1f968"
                    ),
                ),
            )
            provider_names = ("Aura", "Stench")
            for provider, requirement, provider_name in zip(
                providers,
                reviewed_requirements,
                provider_names,
                strict=True,
            ):
                if (
                    type(provider.requirement)
                    is not _RuleRequirement
                    or provider.requirement != requirement
                    or type(provider.rule_id) is not str
                    or provider.rule_id != requirement.rule_id
                    or type(provider.selection)
                    is not _VerifiedSourceSelection
                    or type(provider.receipt) is not _SourceReceipt
                ):
                    reject()
                provider_selection = provider.selection
                provider_address = provider_selection.address
                provider_carrier = provider_selection.carrier
                exact_address(provider_address)
                exact_carrier(provider_carrier)
                exact_receipt(provider.receipt)
                exact_receipt(provider_selection.receipt)
                if (
                    provider_address.source_id != "core-mc1"
                    or provider_address.locator != "358.2"
                    or provider_address.section_id
                    != "core-mc1:ability-glossary"
                    or provider_address.carrier_path
                    != requirement.carrier_path
                    or provider_address.selection_path != ()
                    or provider_address.span is not None
                    or provider_carrier.source_id
                    != provider_address.source_id
                    or provider_carrier.locator
                    != provider_address.locator
                    or provider_carrier.section_id
                    != provider_address.section_id
                    or provider_carrier.target_path
                    != provider_address.target_path
                    or provider_carrier.carrier_path
                    != provider_address.carrier_path
                    or provider_selection.raw_member is not None
                    or type(provider_selection.raw_value)
                    is not _RawSourceObject
                    or type(provider_selection.selected_value)
                    is not _RawSourceObject
                    or provider.receipt
                    != provider_selection.receipt
                ):
                    reject()
                raw_rule = provider_selection.raw_value
                if (
                    type(raw_rule.members) is not tuple
                    or any(
                        type(member) is not _RawSourceMember
                        or type(member.key) is not str
                        for member in raw_rule.members
                    )
                ):
                    reject()
                names = tuple(
                    member.value
                    for member in raw_rule.members
                    if member.key == "Name"
                )
                if (
                    len(names) != 1
                    or type(names[0]) is not str
                    or names[0] != provider_name
                ):
                    reject()

            patch = _AbilityCompilerPatch(
                mechanic={
                    "type": "stench-aura",
                    "family": "stench",
                    "geometry": {
                        "type": "emanation",
                        "radiusFeet": radius_feet,
                        "boundary": "inclusive",
                    },
                    "triggers": [
                        "outside-to-inside",
                        "target-start-turn-inside",
                    ],
                    "savingThrow": {
                        "type": "fortitude",
                        "dc": save_dc,
                    },
                    "outcomes": {
                        "critical-success": {
                            "temporaryImmunity": {
                                "family": "stench",
                                "duration": {
                                    "unit": "rounds",
                                    "value": 10,
                                    "sourceUnit": "minutes",
                                    "sourceValue": 1,
                                },
                            },
                        },
                        "success": {
                            "temporaryImmunity": {
                                "family": "stench",
                                "duration": {
                                    "unit": "rounds",
                                    "value": 10,
                                    "sourceUnit": "minutes",
                                    "sourceValue": 1,
                                },
                            },
                        },
                        "failure": {
                            "condition": "sickened",
                            "value": 1,
                        },
                        "critical-failure": {
                            "condition": "sickened",
                            "value": 1,
                            "linkedCondition": {
                                "condition": "slowed",
                                "value": 1,
                                "while": (
                                    "target remains sickened"
                                ),
                            },
                        },
                    },
                    "rules": {
                        "aura": {
                            "ruleId": (
                                "core-mc1:ability-glossary"
                                "#^.ability[003]"
                            ),
                            "sourceId": "core-mc1",
                            "locator": "358.2",
                            "sourceOrdinal": 5,
                            "sha256": (
                                "3f30455106cbb35f3f791ee121f33ea5612636ffd"
                                "692c4fbbe825667ffb2ec39"
                            ),
                            "digestField": (
                                "providerOrderedRuleSha256"
                            ),
                        },
                        "stench": {
                            "ruleId": (
                                "core-mc1:ability-glossary"
                                "#^.ability[030]"
                            ),
                            "sourceId": "core-mc1",
                            "locator": "358.2",
                            "sourceOrdinal": 32,
                            "sha256": (
                                "189c0083d5b9ae7db0abc7a4af237abbb3548e09c"
                                "b903a2b254a0362afb1f968"
                            ),
                            "digestField": (
                                "providerOrderedRuleSha256"
                            ),
                        },
                        "traits": {
                            "sourceId": "core-pc1",
                            "locator": "452.1",
                        },
                        "emanation": {
                            "sourceId": "core-pc1",
                            "locator": "428.4",
                        },
                        "duration": {
                            "sourceId": "core-pc1",
                            "locator": "426.2",
                        },
                        "turnStart": {
                            "sourceId": "core-pc1",
                            "locator": "435.8",
                        },
                        "fortitude": {
                            "sourceId": "core-pc1",
                            "locator": "404.1",
                        },
                        "sickened": {
                            "sourceId": "core-pc1",
                            "locator": "446.4",
                        },
                        "slowed": {
                            "sourceId": "core-pc1",
                            "locator": "446.5",
                        },
                    },
                },
                rule=_RuleReference("core-mc1", source.locator),
                traits=("aura", "olfactory"),
            )
            return patch, authority, source, consumer, providers
        except (
            AttributeError,
            IndexError,
            KeyError,
            OverflowError,
            RecursionError,
            _SourceAuthorityError,
            TypeError,
            ValueError,
        ) as failure:
            raise TypeError(
                "VerifiedStenchCompilation failed structural revalidation"
            ) from failure

    @property
    def authority(self) -> SourceAuthorityAdapter:
        return self._validated_state()[1]

    @property
    def source(self) -> AbilitySource:
        return self._validated_state()[2]

    @property
    def patch(self) -> AbilityCompilerPatch:
        return self._validated_state()[0]

    @property
    def consumer(self) -> VerifiedSourceSelection:
        return self._validated_state()[3]

    @property
    def providers(
        self,
    ) -> tuple[VerifiedRuleReceipt, VerifiedRuleReceipt]:
        return self._validated_state()[4]

    @property
    def mechanic(self) -> Mapping[str, Any]:
        return self._validated_state()[0].mechanic

    @property
    def rule(self) -> RuleReference:
        return self._validated_state()[0].rule

    @property
    def traits(self) -> tuple[str, ...] | None:
        return self._validated_state()[0].traits

    @property
    def deferred_mechanics(self) -> tuple[str, ...]:
        return self._validated_state()[0].deferred_mechanics

    @property
    def consumer_receipt(self) -> SourceReceipt:
        return self._validated_state()[3].receipt

    @property
    def provider_receipts(self) -> tuple[SourceReceipt, SourceReceipt]:
        providers = self._validated_state()[4]
        return providers[0].receipt, providers[1].receipt

    def as_ability_update(self) -> dict[str, Any]:
        """Revalidate and return the public projection without receipts."""

        return self._validated_state()[0].as_ability_update()


def compile_stench_verified(
    source: AbilitySource,
    /,
    *,
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
    ordered_providers: tuple[
        VerifiedRuleReceipt,
        VerifiedRuleReceipt,
    ],
) -> VerifiedStenchCompilation | None:
    """Compile Stench only from shared-authority capability objects."""

    result = object.__new__(VerifiedStenchCompilation)
    object.__setattr__(result, "_authority", authority)
    object.__setattr__(result, "_source", source)
    object.__setattr__(result, "_consumer", consumer)
    object.__setattr__(
        result,
        "_ordered_providers",
        ordered_providers,
    )
    try:
        result._validated_state()
    except TypeError:
        return None
    return result


def compile_stench(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Recognize Stench; production authority binding happens in the registry."""

    return _compile_stench_unbound(source)


def bind_verified_compilation(
    patch: AbilityCompilerPatch,
    compilation: object,
    /,
) -> AbilityCompilerPatch:
    """Promote only the patch rederived from one live verified compilation."""

    if (
        not isinstance(patch, AbilityCompilerPatch)
        or type(compilation) is not VerifiedStenchCompilation
    ):
        raise ValueError("Stench authority compilation is invalid")
    verified_patch = compilation.patch
    if patch != verified_patch:
        raise ValueError(
            "Stench source grammar disagrees with verified authority"
        )
    return verified_patch


def semantic_rule_contract(
    ability: Mapping[str, Any],
) -> tuple[str, dict[str, str]]:
    """Prove the exact source-free rule identities for runtime Stench."""

    from .conditions import exact_semantic_rule_ref

    rule_ref = ability.get("ruleRef")
    mechanic = ability.get("mechanic")
    rule_refs = (
        mechanic.get("ruleRefs")
        if isinstance(mechanic, Mapping)
        else None
    )
    try:
        normalized_rule_ref = exact_semantic_rule_ref(
            rule_ref,
            "Stench ability rule",
        )
        if not isinstance(rule_refs, Mapping) or set(rule_refs) != set(
            STENCH_RULE_REFS
        ):
            raise ValueError("Stench mechanic rule references are incomplete")
        normalized_rule_refs = {
            role: exact_semantic_rule_ref(
                rule_refs[role],
                f"Stench {role} rule",
            )
            for role in STENCH_RULE_REFS
        }
    except ValueError as failure:
        raise EngineInputError(str(failure)) from failure
    if (
        normalized_rule_ref != STENCH_ABILITY_RULE_REF
        or normalized_rule_refs != dict(STENCH_RULE_REFS)
        or normalized_rule_refs["stench"] != normalized_rule_ref
    ):
        raise EngineInputError("Stench semantic rule contract is invalid")
    return normalized_rule_ref, normalized_rule_refs


def source_abilities(
    state: dict[str, Any],
    host: StenchRuntimeHost,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return Stench sources in initiative order."""

    participants = host.participant_map(state)
    turn = state.get("turn")
    order = (
        turn.get("order")
        if isinstance(turn, Mapping)
        else None
    ) or [
        participant["id"]
        for participant in state.get("participants") or []
    ]
    result = []
    for participant_id in order:
        source = participants.get(str(participant_id))
        if source is None:
            raise EngineInputError("Stench initiative participant is invalid")
        ability = host.ability_by_mechanic(
            host.definition_for(state, source),
            STENCH_MECHANIC_TYPE,
        )
        if ability is not None:
            semantic_rule_contract(ability)
            result.append((source, ability))
    return result


def normalize_adjudications(
    payload: Any,
    *,
    participants: list[dict[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, str]]] | None:
    """Validate the host's complete private Stench eligibility matrix."""

    expected = []
    for source in participants:
        definition = definitions[source["creatureId"]]
        for ability in definition.get("abilities") or []:
            if (
                ability.get("supported") is not True
                or ability.get("mechanic", {}).get("type")
                != STENCH_MECHANIC_TYPE
            ):
                continue
            for target in participants:
                expected.append(
                    (
                        str(source["id"]),
                        str(ability["id"]),
                        str(target["id"]),
                    )
                )
    if not expected and payload is None:
        return None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"olfactoryAuras"}
        or not isinstance(payload.get("olfactoryAuras"), list)
    ):
        raise EngineInputError(
            "adjudications must contain exactly olfactoryAuras"
        )
    rows_by_key: dict[tuple[str, str, str], dict[str, str]] = {}
    for index, row in enumerate(payload["olfactoryAuras"]):
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "sourceParticipantId",
                "abilityId",
                "targetParticipantId",
                "eligibility",
            }
        ):
            raise EngineInputError(
                f"adjudications.olfactoryAuras[{index}] is invalid"
            )
        if any(
            type(row[field]) is not str or not row[field]
            for field in (
                "sourceParticipantId",
                "abilityId",
                "targetParticipantId",
            )
        ) or row["eligibility"] not in OLFACTORY_AURA_ELIGIBILITY:
            raise EngineInputError(
                f"adjudications.olfactoryAuras[{index}] values are invalid"
            )
        key = (
            row["sourceParticipantId"],
            row["abilityId"],
            row["targetParticipantId"],
        )
        if key in rows_by_key:
            raise EngineInputError(
                "adjudications.olfactoryAuras contains a duplicate row"
            )
        rows_by_key[key] = {
            "sourceParticipantId": key[0],
            "abilityId": key[1],
            "targetParticipantId": key[2],
            "eligibility": row["eligibility"],
        }
    if set(rows_by_key) != set(expected):
        raise EngineInputError(
            "adjudications.olfactoryAuras must be the complete exact "
            "Stench source-by-participant matrix"
        )
    return {"olfactoryAuras": [rows_by_key[key] for key in expected]}


def validated_olfactory_aura_rows(
    state: dict[str, Any],
    host: StenchRuntimeHost,
) -> dict[tuple[str, str, str], str]:
    """Validate the exact private host adjudication matrix."""

    participants = state.get("participants")
    definitions = state.get("definitions")
    if not isinstance(participants, list) or not isinstance(definitions, dict):
        raise EngineInputError("olfactory aura encounter sources are invalid")
    selected_definitions: dict[str, dict[str, Any]] = {}
    for participant in participants:
        creature_id = str(participant.get("creatureId") or "")
        if creature_id in selected_definitions:
            continue
        definition = definitions.get(creature_id)
        if not isinstance(definition, dict):
            raise EngineInputError(
                f"creature definition is missing: {creature_id}"
            )
        ability = host.ability_by_mechanic(
            definition,
            STENCH_MECHANIC_TYPE,
        )
        selected_definitions[creature_id] = {
            "abilities": [] if ability is None else [ability]
        }
    adjudications = state.get("adjudications")
    supplied = (
        {"olfactoryAuras": adjudications["olfactoryAuras"]}
        if isinstance(adjudications, dict) and "olfactoryAuras" in adjudications
        else None
    )
    normalized = host.normalize_olfactory_aura_adjudications(
        supplied,
        participants=participants,
        definitions=selected_definitions,
    )
    if normalized is None:
        if source_abilities(state, host):
            raise EngineInputError("Stench requires olfactory aura adjudications")
        return {}
    if supplied != normalized:
        raise EngineInputError("olfactory aura adjudications are not canonical")
    return {
        (
            str(row["sourceParticipantId"]),
            str(row["abilityId"]),
            str(row["targetParticipantId"]),
        ): str(row["eligibility"])
        for row in normalized["olfactoryAuras"]
    }


def _validated_save_candidate(
    state: dict[str, Any],
    candidate: Mapping[str, Any],
    host: StenchRuntimeHost,
    rows: Mapping[tuple[str, str, str], str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return the exact live source, target, and ability for one save."""

    if (
        set(candidate)
        != {
            "sourceParticipantId",
            "abilityId",
            "targetParticipantId",
            "trigger",
            "ruleRef",
            "mechanicType",
        }
        or candidate.get("mechanicType") != STENCH_MECHANIC_TYPE
        or candidate.get("trigger")
        not in {"outside-to-inside", "target-start-turn-inside"}
    ):
        raise EngineInputError("pending Stench save candidate is invalid")
    participants = host.participant_map(state)
    source_id = str(candidate.get("sourceParticipantId") or "")
    target_id = str(candidate.get("targetParticipantId") or "")
    ability_id = str(candidate.get("abilityId") or "")
    source = participants.get(source_id)
    target = participants.get(target_id)
    ability = (
        host.supported_ability(
            host.definition_for(state, source),
            ability_id,
        )
        if source is not None
        else None
    )
    rule_ref = (
        semantic_rule_contract(ability)[0]
        if ability is not None
        else None
    )
    if (
        source is None
        or target is None
        or ability is None
        or ability.get("mechanic", {}).get("type") != STENCH_MECHANIC_TYPE
        or candidate.get("ruleRef") != rule_ref
        or rows.get((source_id, ability_id, target_id)) != "affected"
        or not source_is_active(source)
        or target_has_immunity(state, target_id, host)
        or not target_is_inside(state, source, target, ability, host)
    ):
        raise EngineInputError("pending Stench save candidate is stale")
    return source, target, ability


def _expected_pending_save(
    state: dict[str, Any],
    pending: Mapping[str, Any],
    host: StenchRuntimeHost,
    rows: Mapping[tuple[str, str, str], str],
) -> dict[str, Any]:
    candidate = {
        "sourceParticipantId": pending.get("sourceParticipantId"),
        "abilityId": pending.get("abilityId"),
        "targetParticipantId": pending.get("targetParticipantId"),
        "trigger": pending.get("trigger"),
        "ruleRef": pending.get("ruleRef"),
        "mechanicType": pending.get("mechanicType"),
    }
    source, target, ability = _validated_save_candidate(
        state,
        candidate,
        host,
        rows,
    )
    rule_ref, rule_refs = semantic_rule_contract(ability)
    saving_throw = ability.get("mechanic", {}).get("savingThrow")
    if (
        not isinstance(saving_throw, Mapping)
        or saving_throw.get("type") != "fortitude"
        or type(saving_throw.get("dc")) is not int
        or int(saving_throw["dc"]) <= 0
    ):
        raise EngineInputError("Stench saving throw is invalid")
    base_dc = int(saving_throw["dc"])
    dc_breakdown = host.effective_actor_dc(
        state,
        source,
        base_dc=base_dc,
        dc_kind="stench-aura",
    )
    return {
        "type": "StenchSave",
        "mechanicType": STENCH_MECHANIC_TYPE,
        "participantId": str(target["id"]),
        "sourceParticipantId": str(source["id"]),
        "targetParticipantId": str(target["id"]),
        "abilityId": str(ability["id"]),
        "trigger": candidate["trigger"],
        "savingThrow": {
            "type": "fortitude",
            "baseDC": base_dc,
            "dc": int(dc_breakdown["total"]),
            "dcBreakdown": deepcopy(dc_breakdown),
            "rollField": "fortitudeSaveRoll",
        },
        "ruleRef": rule_ref,
        "ruleRefs": deepcopy(rule_refs),
    }


def _owned_runtime_state(
    state: dict[str, Any],
    *,
    create: bool = False,
) -> dict[str, Any] | None:
    """Return this family's entry in the generic mechanic-state namespace."""

    namespace = state.get("mechanicState")
    if namespace is None:
        if not create:
            return None
        namespace = {}
        state["mechanicState"] = namespace
    if not isinstance(namespace, dict):
        raise EngineInputError("encounter mechanic state is invalid")
    owned = namespace.get(STENCH_MECHANIC_TYPE)
    if owned is None:
        if not create:
            return None
        owned = {"mechanicType": STENCH_MECHANIC_TYPE}
        namespace[STENCH_MECHANIC_TYPE] = owned
    if (
        not isinstance(owned, dict)
        or owned.get("mechanicType") != STENCH_MECHANIC_TYPE
    ):
        raise EngineInputError("Stench runtime ownership marker is invalid")
    return owned


def _prune_owned_runtime_state(state: dict[str, Any]) -> None:
    namespace = state.get("mechanicState")
    if not isinstance(namespace, dict):
        return
    owned = namespace.get(STENCH_MECHANIC_TYPE)
    if isinstance(owned, dict) and set(owned) == {"mechanicType"}:
        namespace.pop(STENCH_MECHANIC_TYPE, None)
    if not namespace:
        state.pop("mechanicState", None)


def _validated_stench_sickened_contribution(
    state: dict[str, Any],
    contribution: Mapping[str, Any],
    host: StenchRuntimeHost,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Prove one Sickened contribution came from an exact Stench save."""

    try:
        digest = host.sickened_contribution_digest(contribution)
    except (TypeError, ValueError) as failure:
        raise EngineInputError(
            "Stench Sickened contribution evidence is invalid"
        ) from failure
    participants = host.participant_map(state)
    source_id = str(contribution.get("sourceParticipantId") or "")
    target_id = str(contribution.get("targetParticipantId") or "")
    ability_id = str(contribution.get("sourceAbilityId") or "")
    source = participants.get(source_id)
    target = participants.get(target_id)
    ability = (
        host.supported_ability(
            host.definition_for(state, source),
            ability_id,
        )
        if source is not None
        else None
    )
    rule_ref = None
    rule_refs = None
    if ability is not None:
        rule_ref, rule_refs = semantic_rule_contract(ability)
    creation = contribution.get("creation")
    event = (
        host.event_receipt_map(state).get(creation.get("eventSequence"))
        if isinstance(creation, Mapping)
        and type(creation.get("eventSequence")) is int
        else None
    )
    event_contribution = (
        event.get("sickenedEffect")
        if isinstance(event, Mapping)
        else None
    )
    try:
        event_contribution_digest = (
            host.sickened_contribution_digest(event_contribution)
            if isinstance(event_contribution, Mapping)
            else None
        )
    except (TypeError, ValueError) as failure:
        raise EngineInputError(
            "Stench Sickened creation evidence is invalid"
        ) from failure
    linked_ids = contribution.get("linkedEffectIds")
    expected_degree = (
        "critical-failure"
        if isinstance(linked_ids, list) and len(linked_ids) == 1
        else "failure"
        if linked_ids == []
        else None
    )
    saving_throw = event.get("savingThrow") if isinstance(event, Mapping) else None
    created_ids = (
        event.get("createdEffectIds") if isinstance(event, Mapping) else None
    )
    if (
        contribution.get("kind") != "condition"
        or contribution.get("condition") != "sickened"
        or contribution.get("sourceFamily") != STENCH_FAMILY
        or contribution.get("runtimeOwner") != dict(STENCH_RUNTIME_OWNER)
        or contribution.get("initialValue") != 1
        or source is None
        or target is None
        or ability is None
        or ability.get("mechanic", {}).get("type") != STENCH_MECHANIC_TYPE
        or contribution.get("ruleRefs")
        != {
            "source": rule_ref,
            "sickened": rule_refs.get("sickened") if rule_refs else None,
            "fortitude": rule_refs.get("fortitude") if rule_refs else None,
        }
        or not isinstance(creation, Mapping)
        or creation.get("eventType") != STENCH_SAVE_EVENT_TYPE
        or not isinstance(event, Mapping)
        or event.get("type") != STENCH_SAVE_EVENT_TYPE
        or event.get("mechanicType") != STENCH_MECHANIC_TYPE
        or event.get("actorId") != target_id
        or event.get("sourceParticipantId") != source_id
        or event.get("targetParticipantId") != target_id
        or event.get("abilityId") != ability_id
        or event.get("degree") != expected_degree
        or event.get("ruleRef") != rule_ref
        or event.get("ruleRefs") != rule_refs
        or not isinstance(saving_throw, Mapping)
        or saving_throw.get("dc") != contribution.get("recovery", {}).get("dc")
        or not isinstance(created_ids, list)
        or created_ids.count(contribution.get("id")) != 1
        or event.get("createdSickenedEffectDigests")
        != {str(contribution.get("id")): digest}
        or event_contribution_digest != digest
    ):
        raise EngineInputError(
            "Stench Sickened contribution provenance is invalid"
        )
    return ability, dict(event), digest


def _validate_stench_condition_effects(
    state: dict[str, Any],
    host: StenchRuntimeHost,
    owned_effects: list[Mapping[str, Any]],
) -> None:
    """Validate every active condition owned by the Stench mechanic."""

    claimed = [
        effect
        for effect in owned_effects
        if effect.get("kind") == "condition"
    ]
    sickened = {
        str(effect.get("id")): effect
        for effect in claimed
        if effect.get("condition") == "sickened"
    }
    for contribution in sickened.values():
        _validated_stench_sickened_contribution(state, contribution, host)
    for effect in claimed:
        if effect.get("condition") == "sickened":
            continue
        if effect.get("condition") != "slowed":
            raise EngineInputError(
                "Stench condition contribution type is invalid"
            )
        source_id = str(effect.get("sourceParticipantId") or "")
        target_id = str(effect.get("targetParticipantId") or "")
        ability_id = str(effect.get("sourceAbilityId") or "")
        source = host.participant_map(state).get(source_id)
        ability = (
            host.supported_ability(
                host.definition_for(state, source),
                ability_id,
            )
            if source is not None
            else None
        )
        rule_ref = None
        rule_refs = None
        if ability is not None:
            rule_ref, rule_refs = semantic_rule_contract(ability)
        metadata = effect.get("metadata")
        linked_id = (
            str(metadata.get("endsWithEffectId") or "")
            if isinstance(metadata, Mapping)
            else ""
        )
        contribution = sickened.get(linked_id)
        event = None
        if contribution is not None:
            _ability, event, _digest = _validated_stench_sickened_contribution(
                state,
                contribution,
                host,
            )
        created_ids = (
            event.get("createdEffectIds")
            if isinstance(event, Mapping)
            else None
        )
        if (
            ability is None
            or ability.get("mechanic", {}).get("type") != STENCH_MECHANIC_TYPE
            or contribution is None
            or contribution.get("sourceParticipantId") != source_id
            or contribution.get("targetParticipantId") != target_id
            or contribution.get("sourceAbilityId") != ability_id
            or effect.get("runtimeOwner") != dict(STENCH_RUNTIME_OWNER)
            or effect.get("sourceFamily") != STENCH_FAMILY
            or contribution.get("creation", {}).get("eventSequence")
            != event.get("sequence")
            or contribution.get("linkedEffectIds") != [effect.get("id")]
            or effect.get("kind") != "condition"
            or effect.get("value") != 1
            or effect.get("ruleRef")
            != (rule_refs.get("slowed") if rule_refs else None)
            or effect.get("duration") != {"endsWithEffectId": linked_id}
            or effect.get("metadata") != {"endsWithEffectId": linked_id}
            or effect.get("stackKey")
            != f"{source_id}:{ability_id}:stench-slowed"
            or event.get("degree") != "critical-failure"
            or event.get("ruleRef") != rule_ref
            or event.get("slowedEffect") != effect
            or not isinstance(created_ids, list)
            or created_ids.count(effect.get("id")) != 1
        ):
            raise EngineInputError(
                "Stench Slowed contribution provenance is invalid"
            )


def _validate_stench_evidence_accounting(
    state: dict[str, Any],
    owned_effects: list[Mapping[str, Any]],
    host: StenchRuntimeHost,
) -> None:
    """Require every live Stench-tagged receipt to support owned state."""

    accounted_sequences: set[int] = set()
    for effect in owned_effects:
        creation = effect.get("creation")
        if isinstance(creation, Mapping) and type(
            creation.get("eventSequence")
        ) is int:
            accounted_sequences.add(int(creation["eventSequence"]))
        source_save_sequence = effect.get("sourceStenchSaveEventSequence")
        if type(source_save_sequence) is int:
            accounted_sequences.add(source_save_sequence)

    for sequence, event in host.event_receipt_map(state).items():
        if event.get("mechanicType") != STENCH_MECHANIC_TYPE:
            continue
        if (
            event.get("type") not in {STENCH_SAVE_EVENT_TYPE, "retch"}
            or sequence not in accounted_sequences
        ):
            raise EngineInputError(
                "Stench runtime evidence is not accounted for by owned state"
            )


def validate_runtime_state(
    state: dict[str, Any],
    host: StenchRuntimeHost,
) -> None:
    """Validate the complete package-owned Stench lifecycle state."""

    owned_state = _owned_runtime_state(state)
    if owned_state is not None and set(owned_state) - {
        "mechanicType",
        "pendingSaveQueue",
        "resume",
        "immunityEventInProgress",
    }:
        raise EngineInputError("Stench runtime state fields are invalid")
    if owned_state is not None and "immunityEventInProgress" in owned_state:
        raise EngineInputError(
            "Stench immunity construction marker escaped transition resolution"
        )
    effects = [
        effect
        for effect in host.state_effects(state)
        if isinstance(effect, Mapping)
    ]
    owned_effects = [
        effect
        for effect in effects
        if effect.get("runtimeOwner") == dict(STENCH_RUNTIME_OWNER)
    ]
    for effect in effects:
        if effect.get("runtimeOwner") == dict(STENCH_RUNTIME_OWNER):
            if effect.get("kind") == "temporary-immunity":
                if effect.get("family") != STENCH_FAMILY:
                    raise EngineInputError(
                        "Stench temporary immunity family is invalid"
                    )
                continue
            if (
                effect.get("kind") == "condition"
                and effect.get("condition") in {"sickened", "slowed"}
            ):
                continue
            raise EngineInputError("Stench-owned effect shape is invalid")
        if (
            effect.get("family") == STENCH_FAMILY
            or effect.get("sourceFamily") == STENCH_FAMILY
        ):
            raise EngineInputError(
                "Stench effect runtime ownership marker is invalid"
            )
    _validate_stench_condition_effects(state, host, owned_effects)
    rows = validated_olfactory_aura_rows(state, host)
    immunity_effects(state, host)
    _validate_stench_evidence_accounting(state, owned_effects, host)

    raw_queue = (
        owned_state.get("pendingSaveQueue")
        if owned_state is not None
        else None
    )
    queue: list[Mapping[str, Any]] = []
    if (
        raw_queue is None
        and owned_state is not None
        and "pendingSaveQueue" in owned_state
    ):
        raise EngineInputError("pending Stench save queue is invalid")
    if raw_queue is not None:
        if (
            not isinstance(raw_queue, list)
            or not raw_queue
            or any(not isinstance(item, Mapping) for item in raw_queue)
        ):
            raise EngineInputError("pending Stench save queue is invalid")
        queue = raw_queue
        keys = []
        for candidate in queue:
            _validated_save_candidate(state, candidate, host, rows)
            keys.append(
                (
                    candidate["sourceParticipantId"],
                    candidate["abilityId"],
                    candidate["targetParticipantId"],
                    candidate["trigger"],
                    candidate["ruleRef"],
                    candidate["mechanicType"],
                )
            )
        if len(keys) != len(set(keys)):
            raise EngineInputError(
                "pending Stench save queue contains duplicate candidates"
            )

    pending = state.get("pendingDecision")
    pending_stench = (
        pending
        if isinstance(pending, Mapping)
        and pending.get("type") == "StenchSave"
        else None
    )
    if pending_stench is not None:
        if pending_stench.get("mechanicType") != STENCH_MECHANIC_TYPE:
            raise EngineInputError(
                "pending Stench save ownership marker is invalid"
            )
        if dict(pending_stench) != _expected_pending_save(
            state,
            pending_stench,
            host,
            rows,
        ):
            raise EngineInputError("pending Stench save is not canonical")
    if queue and pending_stench is None:
        raise EngineInputError(
            "pending Stench save queue lacks its active decision"
        )
    if queue and pending_stench is not None:
        pending_key = (
            pending_stench["sourceParticipantId"],
            pending_stench["abilityId"],
            pending_stench["targetParticipantId"],
            pending_stench["trigger"],
            pending_stench["ruleRef"],
            pending_stench["mechanicType"],
        )
        if pending_key in keys:
            raise EngineInputError(
                "pending Stench save queue repeats its active decision"
            )

    resume = owned_state.get("resume") if owned_state is not None else None
    if (
        resume is None
        and owned_state is not None
        and "resume" in owned_state
    ):
        raise EngineInputError("Stench save continuation is invalid")
    has_runtime_work = pending_stench is not None or bool(queue)
    if has_runtime_work != (resume is not None):
        raise EngineInputError(
            "Stench save queue and continuation are inconsistent"
        )
    if resume is None:
        return
    if not isinstance(resume, Mapping):
        raise EngineInputError("Stench save continuation is invalid")
    if resume.get("type") == "turn-start":
        if (
            set(resume)
            != {"type", "triggerEventSequence", "mechanicType"}
            or resume.get("mechanicType") != STENCH_MECHANIC_TYPE
            or type(resume.get("triggerEventSequence")) is not int
            or int(resume["triggerEventSequence"]) < 1
        ):
            raise EngineInputError("Stench turn-start continuation is invalid")
        return
    action_type = {
        "suspended-stride": "Stride",
        "suspended-fly": "Fly",
    }.get(resume.get("type"))
    suspended = state.get("suspendedAction")
    if (
        action_type is None
        or set(resume)
        != {"type", "suspendedActionId", "mechanicType"}
        or resume.get("mechanicType") != STENCH_MECHANIC_TYPE
        or not isinstance(suspended, Mapping)
        or suspended.get("id") != resume.get("suspendedActionId")
        or suspended.get("actionType") != action_type
    ):
        raise EngineInputError("Stench movement continuation is invalid")


def immunity_effects(
    state: dict[str, Any],
    host: StenchRuntimeHost,
    *,
    target_id: str | None = None,
) -> list[dict[str, Any]]:
    """Validate absolute-clock, all-source Stench immunities."""

    participants = host.participant_map(state)
    turn = state.get("turn")
    order = turn.get("order") if isinstance(turn, Mapping) else None
    if not isinstance(order, list) or not order:
        return []
    events = host.event_receipt_map(state)
    result = []
    for effect in host.state_effects(state):
        if (
            not isinstance(effect, dict)
            or effect.get("kind") != "temporary-immunity"
            or effect.get("runtimeOwner") != dict(STENCH_RUNTIME_OWNER)
        ):
            continue
        creation = effect.get("creation")
        source_id = str(effect.get("sourceParticipantId") or "")
        subject_id = str(effect.get("targetParticipantId") or "")
        source = participants.get(source_id)
        ability = (
            host.supported_ability(
                host.definition_for(state, source),
                str(effect.get("sourceAbilityId") or ""),
            )
            if source is not None
            else None
        )
        ability_rule_ref = (
            semantic_rule_contract(ability)[0]
            if ability is not None
            else None
        )
        if (
            set(effect)
            != {
                "id",
                "kind",
                "family",
                "sourceParticipantId",
                "targetParticipantId",
                "sourceAbilityId",
                "runtimeOwner",
                "sourceStenchSaveEventSequence",
                "creation",
                "expiresAtInitiativeStep",
                "duration",
                "ruleRef",
            }
            or effect.get("family") != STENCH_FAMILY
            or source_id not in participants
            or subject_id not in participants
            or ability is None
            or ability.get("mechanic", {}).get("type") != STENCH_MECHANIC_TYPE
            or effect.get("runtimeOwner") != dict(STENCH_RUNTIME_OWNER)
            or not isinstance(creation, dict)
            or set(creation) != {"eventSequence", "initiativeStep", "round"}
            or any(
                isinstance(creation.get(field), bool)
                or not isinstance(creation.get(field), int)
                for field in ("eventSequence", "initiativeStep", "round")
            )
            or effect.get("expiresAtInitiativeStep")
            != int(creation["initiativeStep"])
            + STENCH_IMMUNITY_ROUNDS * len(order)
            or effect.get("duration")
            != {
                "unit": "rounds",
                "value": STENCH_IMMUNITY_ROUNDS,
                "sourceUnit": "minutes",
                "sourceValue": 1,
            }
            or effect.get("ruleRef") != ability_rule_ref
            or isinstance(
                effect.get("sourceStenchSaveEventSequence"), bool
            )
            or not isinstance(
                effect.get("sourceStenchSaveEventSequence"), int
            )
            or int(effect["sourceStenchSaveEventSequence"]) < 1
        ):
            raise EngineInputError("Stench temporary immunity effect is invalid")
        event = events.get(int(creation["eventSequence"]))
        created_ids = (
            event.get("createdEffectIds")
            if isinstance(event, dict)
            else None
        )
        event_type = event.get("type") if isinstance(event, dict) else None
        save_evidence_is_exact = (
            event_type == STENCH_SAVE_EVENT_TYPE
            and event.get("mechanicType") == STENCH_MECHANIC_TYPE
            and event.get("sourceParticipantId") == source_id
            and event.get("targetParticipantId") == subject_id
            and event.get("abilityId") == effect.get("sourceAbilityId")
            and event.get("degree") in {"critical-success", "success"}
            and event.get("ruleRefs")
            == (semantic_rule_contract(ability)[1] if ability else None)
            and event.get("stenchImmunity") == effect
        )
        retch_evidence_is_exact = False
        if event_type == "retch" and isinstance(event, dict):
            selected = event.get("selectedContribution")
            if isinstance(selected, Mapping):
                selected_ability, _creation_event, _digest = (
                    _validated_stench_sickened_contribution(
                        state,
                        selected,
                        host,
                    )
                )
                selected_rule_ref = semantic_rule_contract(
                    selected_ability
                )[0]
                selected_rule_refs = selected.get("ruleRefs")
                retch_evidence_is_exact = (
                    event.get("mechanicType") == STENCH_MECHANIC_TYPE
                    and event.get("actorId") == subject_id
                    and event.get("effectId") == selected.get("id")
                    and selected.get("sourceParticipantId") == source_id
                    and selected.get("targetParticipantId") == subject_id
                    and selected.get("sourceAbilityId")
                    == effect.get("sourceAbilityId")
                    and selected.get("creation", {}).get("eventSequence")
                    == effect.get("sourceStenchSaveEventSequence")
                    and event.get("ruleRef") == selected_rule_ref
                    and event.get("ruleRefs") == selected_rule_refs
                    and event.get("degree")
                    in {"critical-success", "success"}
                    and event.get("contribution", {}).get("after") == 0
                    and event.get("stenchImmunity") == effect
                )
        if (
            not isinstance(event, dict)
            or not (save_evidence_is_exact or retch_evidence_is_exact)
            or (
                event_type == STENCH_SAVE_EVENT_TYPE
                and effect.get("sourceStenchSaveEventSequence")
                != creation.get("eventSequence")
            )
            or event.get("createdStenchImmunityEffectId") != effect["id"]
            or event.get("ruleRef") != effect["ruleRef"]
            or not isinstance(created_ids, list)
            or created_ids.count(effect["id"]) != 1
        ):
            raise EngineInputError(
                "Stench temporary immunity creation evidence is invalid"
            )
        if target_id is None or subject_id == target_id:
            result.append(effect)
    return result


def target_has_immunity(
    state: dict[str, Any],
    target_id: str,
    host: StenchRuntimeHost,
) -> bool:
    owned_state = _owned_runtime_state(state)
    in_progress = (
        owned_state.get("immunityEventInProgress")
        if owned_state is not None
        else None
    )
    if in_progress == host.next_event_sequence(state):
        return any(
            isinstance(effect, dict)
            and effect.get("kind") == "temporary-immunity"
            and effect.get("family") == STENCH_FAMILY
            and effect.get("targetParticipantId") == target_id
            and effect.get("creation", {}).get("eventSequence")
            == in_progress
            for effect in host.state_effects(state)
        )
    return bool(immunity_effects(state, host, target_id=target_id))


def source_is_active(source: Mapping[str, Any]) -> bool:
    return not (
        source.get("defeated")
        or source.get("incapacitated")
        or int(source.get("hitPoints", {}).get("current", 0)) <= 0
    )


def target_is_inside(
    state: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    ability: Mapping[str, Any],
    host: StenchRuntimeHost,
) -> bool:
    radius = ability.get("mechanic", {}).get("geometry", {}).get(
        "radiusFeet"
    )
    if isinstance(radius, bool) or not isinstance(radius, int) or radius <= 0:
        raise EngineInputError("Stench emanation radius is invalid")
    if source["id"] == target["id"]:
        return True
    return (
        host.participant_distance(
            state,
            str(source["id"]),
            str(target["id"]),
        )
        <= radius
        and host.participants_have_line_of_effect(
            state,
            str(source["id"]),
            str(target["id"]),
        )
    )


def inside_keys(
    state: dict[str, Any],
    target_id: str,
    host: StenchRuntimeHost,
) -> set[tuple[str, str]]:
    participants = host.participant_map(state)
    target = participants.get(target_id)
    if target is None:
        raise EngineInputError("Stench target participant is invalid")
    rows = validated_olfactory_aura_rows(state, host)
    if target_has_immunity(state, target_id, host):
        return set()
    result = set()
    for source, ability in source_abilities(state, host):
        key = (str(source["id"]), str(ability["id"]), target_id)
        if (
            rows.get(key) == "affected"
            and source_is_active(source)
            and target_is_inside(state, source, target, ability, host)
        ):
            result.add((key[0], key[1]))
    return result


def entry_candidates_for_pose(
    state: dict[str, Any],
    host: StenchRuntimeHost,
    *,
    target_id: str,
    position: dict[str, int],
    occupied: list[dict[str, int]],
    before_keys: set[tuple[str, str]],
) -> tuple[list[dict[str, str]], set[tuple[str, str]]]:
    trial = deepcopy(state)
    target = host.participant_map(trial).get(target_id)
    if target is None:
        raise EngineInputError("Stench movement target is invalid")
    target["position"] = deepcopy(position)
    target["occupiedSquares"] = deepcopy(occupied)
    trial["spatialRelations"] = host.map_relations(
        trial["participants"],
        trial["definitions"],
    )
    after_keys = inside_keys(trial, target_id, host)
    entered = after_keys - before_keys
    candidates = [
        {
            "sourceParticipantId": source_id,
            "abilityId": ability_id,
            "targetParticipantId": target_id,
            "trigger": "outside-to-inside",
            "ruleRef": rule_ref,
            "mechanicType": STENCH_MECHANIC_TYPE,
        }
        for source_id, ability_id, rule_ref in [
            (
                str(source["id"]),
                str(ability["id"]),
                semantic_rule_contract(ability)[0],
            )
            for source, ability in source_abilities(trial, host)
        ]
        if (source_id, ability_id) in entered
    ]
    return candidates, after_keys


def expire_immunities(
    state: dict[str, Any],
    host: StenchRuntimeHost,
) -> list[str]:
    current_step = int(state.get("turn", {}).get("initiativeStep", 0))
    expired = [
        str(effect["id"])
        for effect in immunity_effects(state, host)
        if current_step >= int(effect["expiresAtInitiativeStep"])
    ]
    return host.remove_effect_ids(state, expired)


def create_immunity(
    state: dict[str, Any],
    host: StenchRuntimeHost,
    *,
    target_id: str,
    source_id: str,
    ability_id: str,
    event_sequence: int,
    rule_ref: str,
    replace_existing: bool = False,
    source_stench_save_event_sequence: int | None = None,
) -> tuple[dict[str, Any], list[str]]:
    from .conditions import exact_semantic_rule_ref

    try:
        normalized_rule_ref = exact_semantic_rule_ref(
            rule_ref,
            "Stench temporary immunity rule",
        )
    except ValueError as failure:
        raise EngineInputError(str(failure)) from failure
    if normalized_rule_ref != STENCH_ABILITY_RULE_REF:
        raise EngineInputError("Stench temporary immunity rule is invalid")
    existing = immunity_effects(state, host, target_id=target_id)
    if existing and not replace_existing:
        raise EngineInputError("Stench temporary immunity is already active")
    replaced_effect_ids = host.remove_effect_ids(
        state,
        [str(effect["id"]) for effect in existing],
    )
    turn = state.get("turn") or {}
    order = turn.get("order")
    if not isinstance(order, list) or not order:
        raise EngineInputError(
            "Stench temporary immunity requires initiative order"
        )
    creation_step = int(turn.get("initiativeStep", 0))
    source_save_sequence = (
        event_sequence
        if source_stench_save_event_sequence is None
        else source_stench_save_event_sequence
    )
    if (
        isinstance(source_save_sequence, bool)
        or not isinstance(source_save_sequence, int)
        or source_save_sequence < 1
    ):
        raise EngineInputError(
            "Stench immunity source save sequence is invalid"
        )
    effect = {
        "id": f"temporary-immunity:stench:{event_sequence}:{target_id}",
        "kind": "temporary-immunity",
        "family": STENCH_FAMILY,
        "sourceParticipantId": source_id,
        "targetParticipantId": target_id,
        "sourceAbilityId": ability_id,
        "runtimeOwner": dict(STENCH_RUNTIME_OWNER),
        "sourceStenchSaveEventSequence": source_save_sequence,
        "creation": {
            "eventSequence": event_sequence,
            "initiativeStep": creation_step,
            "round": int(turn.get("round", 1)),
        },
        "expiresAtInitiativeStep": (
            creation_step + STENCH_IMMUNITY_ROUNDS * len(order)
        ),
        "duration": {
            "unit": "rounds",
            "value": STENCH_IMMUNITY_ROUNDS,
            "sourceUnit": "minutes",
            "sourceValue": 1,
        },
        "ruleRef": normalized_rule_ref,
    }
    if any(
        candidate.get("id") == effect["id"]
        for candidate in host.state_effects(state)
        if isinstance(candidate, dict)
    ):
        raise EngineInputError(
            "Stench temporary immunity identity is duplicated"
        )
    host.state_effects(state).append(effect)
    return effect, replaced_effect_ids


def start_candidates(
    state: dict[str, Any],
    target_id: str,
    host: StenchRuntimeHost,
) -> list[dict[str, str]]:
    inside = inside_keys(state, target_id, host)
    return [
        {
            "sourceParticipantId": str(source["id"]),
            "abilityId": str(ability["id"]),
            "targetParticipantId": target_id,
            "trigger": "target-start-turn-inside",
            "ruleRef": semantic_rule_contract(ability)[0],
            "mechanicType": STENCH_MECHANIC_TYPE,
        }
        for source, ability in source_abilities(state, host)
        if (str(source["id"]), str(ability["id"])) in inside
    ]


def activate_next_save_decision(
    state: dict[str, Any],
    host: StenchRuntimeHost,
) -> dict[str, Any] | None:
    owned_state = _owned_runtime_state(state)
    queue = (
        owned_state.get("pendingSaveQueue")
        if owned_state is not None
        else None
    )
    if not isinstance(queue, list):
        if owned_state is not None:
            owned_state.pop("pendingSaveQueue", None)
        _prune_owned_runtime_state(state)
        return None
    participants = host.participant_map(state)
    rows = validated_olfactory_aura_rows(state, host)
    while queue:
        candidate = queue.pop(0)
        if (
            not isinstance(candidate, dict)
            or set(candidate)
            != {
                "sourceParticipantId",
                "abilityId",
                "targetParticipantId",
                "trigger",
                "ruleRef",
                "mechanicType",
            }
            or candidate.get("mechanicType") != STENCH_MECHANIC_TYPE
            or candidate.get("trigger")
            not in {"outside-to-inside", "target-start-turn-inside"}
        ):
            raise EngineInputError("pending Stench save queue is invalid")
        source_id = str(candidate["sourceParticipantId"])
        target_id = str(candidate["targetParticipantId"])
        ability_id = str(candidate["abilityId"])
        source = participants.get(source_id)
        target = participants.get(target_id)
        ability = (
            host.supported_ability(
                host.definition_for(state, source),
                ability_id,
            )
            if source is not None
            else None
        )
        ability_rule_ref = None
        ability_rule_refs = None
        if ability is not None:
            ability_rule_ref, ability_rule_refs = semantic_rule_contract(ability)
        if (
            source is None
            or target is None
            or ability is None
            or ability.get("mechanic", {}).get("type") != STENCH_MECHANIC_TYPE
            or candidate.get("ruleRef") != ability_rule_ref
            or rows.get((source_id, ability_id, target_id)) != "affected"
            or not source_is_active(source)
            or target_has_immunity(state, target_id, host)
            or not target_is_inside(state, source, target, ability, host)
        ):
            continue
        saving_throw = ability["mechanic"].get("savingThrow")
        if (
            not isinstance(saving_throw, dict)
            or saving_throw.get("type") != "fortitude"
            or isinstance(saving_throw.get("dc"), bool)
            or not isinstance(saving_throw.get("dc"), int)
            or int(saving_throw["dc"]) <= 0
        ):
            raise EngineInputError("Stench saving throw is invalid")
        base_dc = int(saving_throw["dc"])
        dc_breakdown = host.effective_actor_dc(
            state,
            source,
            base_dc=base_dc,
            dc_kind="stench-aura",
        )
        pending = {
            "type": "StenchSave",
            "mechanicType": STENCH_MECHANIC_TYPE,
            "participantId": target_id,
            "sourceParticipantId": source_id,
            "targetParticipantId": target_id,
            "abilityId": ability_id,
            "trigger": candidate["trigger"],
            "savingThrow": {
                "type": "fortitude",
                "baseDC": base_dc,
                "dc": int(dc_breakdown["total"]),
                "dcBreakdown": deepcopy(dc_breakdown),
                "rollField": "fortitudeSaveRoll",
            },
            "ruleRef": ability_rule_ref,
            "ruleRefs": deepcopy(ability_rule_refs),
        }
        state["pendingDecision"] = pending
        if not queue:
            owned_state.pop("pendingSaveQueue", None)
        return pending
    owned_state.pop("pendingSaveQueue", None)
    _prune_owned_runtime_state(state)
    return None


def queue_save_decisions(
    state: dict[str, Any],
    host: StenchRuntimeHost,
    *,
    candidates: list[dict[str, str]],
    resume: dict[str, Any],
) -> dict[str, Any] | None:
    owned_state = _owned_runtime_state(state)
    if owned_state is not None and (
        owned_state.get("pendingSaveQueue") or owned_state.get("resume")
    ):
        raise EngineInputError("Stench save continuation is already active")
    if not candidates:
        return None
    keys = [
        (
            candidate.get("sourceParticipantId"),
            candidate.get("abilityId"),
            candidate.get("targetParticipantId"),
            candidate.get("trigger"),
            candidate.get("ruleRef"),
            candidate.get("mechanicType"),
        )
        for candidate in candidates
        if isinstance(candidate, dict)
    ]
    if len(keys) != len(candidates) or len(keys) != len(set(keys)):
        raise EngineInputError(
            "Stench exposure candidates are invalid or duplicated"
        )
    if any(
        candidate.get("mechanicType") != STENCH_MECHANIC_TYPE
        for candidate in candidates
    ):
        raise EngineInputError("Stench exposure ownership marker is invalid")
    owned_state = _owned_runtime_state(state, create=True)
    assert owned_state is not None
    owned_state["pendingSaveQueue"] = deepcopy(candidates)
    owned_state["resume"] = {
        **deepcopy(resume),
        "mechanicType": STENCH_MECHANIC_TYPE,
    }
    pending = activate_next_save_decision(state, host)
    if pending is None:
        owned_state = _owned_runtime_state(state)
        if owned_state is not None:
            owned_state.pop("resume", None)
        _prune_owned_runtime_state(state)
    return pending


def finish_resume(
    state: dict[str, Any],
    host: StenchRuntimeHost,
    *,
    event_sequence: int,
) -> dict[str, Any] | None:
    owned_state = _owned_runtime_state(state)
    resume = (
        owned_state.pop("resume", None)
        if owned_state is not None
        else None
    )
    _prune_owned_runtime_state(state)
    if not isinstance(resume, dict):
        return None
    if (
        resume.get("type") == "suspended-stride"
        and set(resume)
        == {"type", "suspendedActionId", "mechanicType"}
        and resume.get("mechanicType") == STENCH_MECHANIC_TYPE
    ):
        suspended = state.get("suspendedAction")
        if not isinstance(suspended, dict) or suspended.get("id") != resume[
            "suspendedActionId"
        ]:
            raise EngineInputError("Stench suspended Stride continuation is stale")
        return host.continue_suspended_stride(state)
    if (
        resume.get("type") == "suspended-fly"
        and set(resume)
        == {"type", "suspendedActionId", "mechanicType"}
        and resume.get("mechanicType") == STENCH_MECHANIC_TYPE
    ):
        suspended = state.get("suspendedAction")
        if not isinstance(suspended, dict) or suspended.get("id") != resume[
            "suspendedActionId"
        ]:
            raise EngineInputError("Stench suspended Fly continuation is stale")
        return host.continue_suspended_fly(state)
    if (
        resume.get("type") == "turn-start"
        and set(resume)
        == {"type", "triggerEventSequence", "mechanicType"}
        and resume.get("mechanicType") == STENCH_MECHANIC_TYPE
    ):
        return host.continue_turn_start(
            state,
            trigger_event_sequence=int(resume["triggerEventSequence"]),
        )
    raise EngineInputError("Stench save continuation is invalid")


def resolve_save_decision(
    state: dict[str, Any],
    actor_id: str,
    action: Mapping[str, Any],
    host: StenchRuntimeHost,
) -> dict[str, Any]:
    """Resolve one queued Stench exposure through the family algorithm."""

    pending = state.get("pendingDecision")
    if not isinstance(pending, dict) or pending.get("type") != "StenchSave":
        raise EngineInputError("encounter has no pending Stench save")
    if actor_id != pending.get("participantId"):
        raise EngineInputError(
            "pending Stench save belongs to another participant"
        )
    if set(action) != {"type", "fortitudeSaveRoll"}:
        raise EngineInputError("StenchSave payload is invalid")
    participants = host.participant_map(state)
    source_id = str(pending.get("sourceParticipantId") or "")
    target_id = str(pending.get("targetParticipantId") or "")
    ability_id = str(pending.get("abilityId") or "")
    source = participants.get(source_id)
    target = participants.get(target_id)
    ability = (
        host.supported_ability(
            host.definition_for(state, source),
            ability_id,
        )
        if source is not None
        else None
    )
    ability_rule_ref = None
    ability_rule_refs = None
    if ability is not None:
        ability_rule_ref, ability_rule_refs = semantic_rule_contract(ability)
    rows = validated_olfactory_aura_rows(state, host)
    authored_saving_throw = (
        ability.get("mechanic", {}).get("savingThrow")
        if isinstance(ability, dict)
        else None
    )
    raw_base_dc = (
        authored_saving_throw.get("dc")
        if isinstance(authored_saving_throw, dict)
        else None
    )
    base_dc = (
        int(raw_base_dc)
        if (
            not isinstance(raw_base_dc, bool)
            and isinstance(raw_base_dc, int)
            and raw_base_dc > 0
        )
        else 0
    )
    dc_breakdown = (
        host.effective_actor_dc(
            state,
            source,
            base_dc=base_dc,
            dc_kind="stench-aura",
        )
        if source is not None and base_dc > 0
        else None
    )
    if (
        source is None
        or target is None
        or target_id != actor_id
        or ability is None
        or ability.get("mechanic", {}).get("type") != STENCH_MECHANIC_TYPE
        or rows.get((source_id, ability_id, target_id)) != "affected"
        or not source_is_active(source)
        or target_has_immunity(state, target_id, host)
        or not target_is_inside(state, source, target, ability, host)
        or not isinstance(dc_breakdown, dict)
        or pending.get("savingThrow")
        != {
            "type": "fortitude",
            "baseDC": base_dc,
            "dc": int(dc_breakdown["total"]),
            "dcBreakdown": dc_breakdown,
            "rollField": "fortitudeSaveRoll",
        }
        or pending.get("ruleRef") != ability_rule_ref
        or pending.get("ruleRefs") != ability_rule_refs
    ):
        raise EngineInputError("pending Stench save is no longer valid")
    roll = host.d20_roll(
        action.get("fortitudeSaveRoll"),
        "StenchSave fortitudeSaveRoll",
    )
    fortitude = host.effective_saving_throw(
        state,
        target,
        "fortitude",
        effect_traits={"aura", "olfactory"},
    )
    modifiers = deepcopy(fortitude["modifiers"])
    total = (
        roll
        + int(fortitude["base"])
        + sum(int(item["value"]) for item in modifiers)
    )
    save_dc = int(dc_breakdown["total"])
    degree = host.attack_degree(total, save_dc, roll)
    saving_throw = {
        "type": "fortitude",
        "roll": roll,
        "modifier": int(fortitude["base"]),
        "situationalModifiers": modifiers,
        "total": total,
        "dc": save_dc,
        "dcBreakdown": deepcopy(dc_breakdown),
        "degree": degree,
    }
    event_sequence = host.next_event_sequence(state)
    created_effect_ids: list[str] = []
    created_sickened_digests: dict[str, str] = {}
    immunity = None
    sickened = None
    slowed = None
    if degree in {"critical-success", "success"}:
        immunity, replaced_immunity_ids = create_immunity(
            state,
            host,
            target_id=target_id,
            source_id=source_id,
            ability_id=ability_id,
            event_sequence=event_sequence,
            rule_ref=str(ability_rule_ref),
        )
        if replaced_immunity_ids:
            raise EngineInputError("Stench save cannot replace active immunity")
        owned_state = _owned_runtime_state(state, create=True)
        assert owned_state is not None
        owned_state["immunityEventInProgress"] = event_sequence
        created_effect_ids.append(str(immunity["id"]))
    elif degree == "critical-failure":
        expected_sickened_id = (
            f"condition:sickened:{event_sequence}:{target_id}:1"
        )
        slowed = host.apply_condition_effect(
            state,
            target_id=target_id,
            condition="slowed",
            source_id=source_id,
            value=1,
            duration={"endsWithEffectId": expected_sickened_id},
            source_ability_id=ability_id,
            source_family=STENCH_FAMILY,
            stack_key=f"{source_id}:{ability_id}:stench-slowed",
            metadata={"endsWithEffectId": expected_sickened_id},
            rule_ref=ability_rule_refs["slowed"],
            runtime_owner=STENCH_RUNTIME_OWNER,
        )
        created_effect_ids.append(str(slowed["id"]))
    if degree in {"failure", "critical-failure"}:
        sickened = host.apply_sickened_contribution(
            state,
            target_id=target_id,
            source_id=source_id,
            source_ability_id=ability_id,
            source_family=STENCH_FAMILY,
            value=1,
            recovery_dc=save_dc,
            source_rule_ref=str(ability_rule_ref),
            creation_event_type=STENCH_SAVE_EVENT_TYPE,
            runtime_owner=STENCH_RUNTIME_OWNER,
            linked_effect_ids=([] if slowed is None else [str(slowed["id"])]),
        )
        created_effect_ids.append(str(sickened["id"]))
        created_sickened_digests[str(sickened["id"])] = (
            host.sickened_contribution_digest(sickened)
        )
        if (
            slowed is not None
            and slowed.get("metadata", {}).get("endsWithEffectId")
            != sickened["id"]
        ):
            raise EngineInputError("Stench Slowed linkage is invalid")
    state.pop("pendingDecision", None)
    next_pending = activate_next_save_decision(state, host)
    continuation = None
    if next_pending is None:
        continuation = finish_resume(
            state,
            host,
            event_sequence=event_sequence,
        )
    event = host.action_event(
        state,
        STENCH_SAVE_EVENT_TYPE,
        actor_id,
        mechanicType=STENCH_MECHANIC_TYPE,
        sourceParticipantId=source_id,
        targetParticipantId=target_id,
        abilityId=ability_id,
        trigger=pending["trigger"],
        savingThrow=saving_throw,
        degree=degree,
        createdEffectIds=created_effect_ids,
        createdSickenedEffectDigests=created_sickened_digests,
        sickenedEffect=deepcopy(sickened),
        slowedEffect=deepcopy(slowed),
        stenchImmunity=deepcopy(immunity),
        nextPendingDecision=deepcopy(state.get("pendingDecision")),
        continuation=deepcopy(continuation),
        ruleRef=ability_rule_ref,
        ruleRefs=deepcopy(ability_rule_refs),
    )
    if immunity is not None:
        event["createdStenchImmunityEffectId"] = str(immunity["id"])
    owned_state = _owned_runtime_state(state)
    if owned_state is not None:
        owned_state.pop("immunityEventInProgress", None)
    _prune_owned_runtime_state(state)
    return event


def apply_retch_immunity_upgrade(
    state: dict[str, Any],
    actor_id: str,
    event: dict[str, Any],
    host: StenchRuntimeHost,
) -> dict[str, Any]:
    """Grant all-source Stench immunity after successful family Retch."""

    selected = event.get("selectedContribution")
    contribution = event.get("contribution")
    if (
        not isinstance(selected, dict)
        or selected.get("sourceFamily") != STENCH_FAMILY
        or not isinstance(contribution, dict)
        or contribution.get("after") != 0
    ):
        return event
    selected_ability, _creation_event, _digest = (
        _validated_stench_sickened_contribution(
            state,
            selected,
            host,
        )
    )
    selected_rule_ref = semantic_rule_contract(selected_ability)[0]
    selected_rule_refs = selected.get("ruleRefs")
    if (
        event.get("type") != "retch"
        or event.get("actorId") != actor_id
        or event.get("effectId") != selected.get("id")
        or selected.get("targetParticipantId") != actor_id
        or event.get("degree") not in {"critical-success", "success"}
        or event.get("ruleRef") != selected_rule_ref
        or event.get("ruleRefs") != selected_rule_refs
    ):
        raise EngineInputError("Stench Retch provenance is invalid")
    immunity, replaced_immunity_ids = create_immunity(
        state,
        host,
        target_id=actor_id,
        source_id=str(selected["sourceParticipantId"]),
        ability_id=str(selected["sourceAbilityId"]),
        event_sequence=int(event["sequence"]),
        rule_ref=str(selected["ruleRefs"]["source"]),
        replace_existing=True,
        source_stench_save_event_sequence=int(
            selected["creation"]["eventSequence"]
        ),
    )
    event["createdStenchImmunityEffectId"] = str(immunity["id"])
    event["stenchImmunity"] = deepcopy(immunity)
    event["createdEffectIds"] = [str(immunity["id"])]
    event["replacedStenchImmunityEffectIds"] = deepcopy(
        replaced_immunity_ids
    )
    event["removedEffectIds"] = [
        *event.get("removedEffectIds", []),
        *(
            effect_id
            for effect_id in replaced_immunity_ids
            if effect_id not in event.get("removedEffectIds", [])
        ),
    ]
    event["mechanicType"] = STENCH_MECHANIC_TYPE
    return event


def enrich_controller_save(
    state: Mapping[str, Any],
    actor_id: str,
    intent: Mapping[str, Any],
    roll_d20: Callable[[], int],
) -> dict[str, Any]:
    """Validate then enrich an owned Stench save controller intent."""

    pending = state.get("pendingDecision")
    if (
        set(intent) != {"type"}
        or intent.get("type") != "StenchSave"
        or not isinstance(pending, Mapping)
        or pending.get("type") != "StenchSave"
        or pending.get("mechanicType") != STENCH_MECHANIC_TYPE
        or pending.get("participantId") != actor_id
    ):
        raise ValueError("controller has no owned Stench save decision")
    roll = roll_d20()
    if type(roll) is not int or not 1 <= roll <= 20:
        raise ValueError("controller Stench save roll is invalid")
    return {"type": "StenchSave", "fortitudeSaveRoll": roll}


def project_controller_pending_decision(
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the closed controller-visible Stench save decision."""

    saving_throw = decision.get("savingThrow")
    required = {
        "type",
        "participantId",
        "sourceParticipantId",
        "targetParticipantId",
        "abilityId",
        "trigger",
        "savingThrow",
    }
    if (
        decision.get("type") != "StenchSave"
        or decision.get("mechanicType") != STENCH_MECHANIC_TYPE
        or not required.issubset(decision)
        or not isinstance(saving_throw, Mapping)
        or saving_throw.get("type") != "fortitude"
        or type(saving_throw.get("dc")) is not int
        or int(saving_throw["dc"]) <= 0
    ):
        raise ValueError("pending Stench save is invalid")
    return {
        key: (
            {
                "type": "fortitude",
                "dc": int(saving_throw["dc"]),
            }
            if key == "savingThrow"
            else deepcopy(decision[key])
        )
        for key in required
    }


def _public_aura_squares(
    state: dict[str, Any],
    source: Mapping[str, Any],
    *,
    radius_feet: int,
    width: int,
    height: int,
) -> list[dict[str, int]]:
    footprint = source.get("occupiedSquares")
    if (
        not isinstance(footprint, list)
        or not footprint
        or any(
            not isinstance(square, Mapping)
            or set(square) != {"x", "y"}
            or type(square.get("x")) is not int
            or type(square.get("y")) is not int
            or not 0 <= int(square["x"]) < width
            or not 0 <= int(square["y"]) < height
            for square in footprint
        )
    ):
        raise EngineInputError("passive Stench aura footprint is invalid")
    axis_reach = radius_feet // 5
    minimum_x = max(
        0,
        min(int(square["x"]) for square in footprint) - axis_reach,
    )
    maximum_x = min(
        width - 1,
        max(int(square["x"]) for square in footprint) + axis_reach,
    )
    minimum_y = max(
        0,
        min(int(square["y"]) for square in footprint) - axis_reach,
    )
    maximum_y = min(
        height - 1,
        max(int(square["y"]) for square in footprint) + axis_reach,
    )
    candidates = {
        (x, y)
        for y in range(minimum_y, maximum_y + 1)
        for x in range(minimum_x, maximum_x + 1)
        if min(
            grid_distance_feet(dict(origin), {"x": x, "y": y})
            for origin in footprint
        )
        <= radius_feet
    }
    reachable: set[tuple[int, int]] = set()
    for origin in footprint:
        reachable.update(
            squares_with_line_of_effect_from_point(
                state,
                (
                    Fraction(int(origin["x"]) * 2 + 1, 2),
                    Fraction(int(origin["y"]) * 2 + 1, 2),
                ),
                candidates,
            )
        )
    return [
        {"x": x, "y": y}
        for x, y in sorted(
            reachable,
            key=lambda square: (square[1], square[0]),
        )
    ]


def _public_projection_context(
    state: dict[str, Any],
    context: Mapping[str, Any],
    host: StenchRuntimeHost,
) -> tuple[int, int, set[str], set[str]]:
    if set(context) != {
        "width",
        "height",
        "participantIds",
        "semanticParticipantIds",
        "trustedOwnedState",
    }:
        raise EngineInputError("Stench public projection context is invalid")
    width = context.get("width")
    height = context.get("height")
    participant_ids = context.get("participantIds")
    semantic_ids = context.get("semanticParticipantIds")
    if (
        type(width) is not int
        or width <= 0
        or type(height) is not int
        or height <= 0
        or type(context.get("trustedOwnedState")) is not bool
        or not isinstance(participant_ids, list)
        or any(type(item) is not str or not item for item in participant_ids)
        or participant_ids != sorted(set(participant_ids))
        or not isinstance(semantic_ids, list)
        or any(type(item) is not str or not item for item in semantic_ids)
        or semantic_ids != sorted(set(semantic_ids))
        or not set(semantic_ids).issubset(participant_ids)
    ):
        raise EngineInputError("Stench public projection context is invalid")
    state_ids = set(host.participant_map(state))
    if state_ids != set(participant_ids):
        raise EngineInputError(
            "Stench public projection participant census is invalid"
        )
    return width, height, state_ids, set(semantic_ids)


def _validated_stench_source_identity(
    state: dict[str, Any],
    source: Mapping[str, Any],
    semantic_ids: set[str],
    host: StenchRuntimeHost,
) -> tuple[str, Mapping[str, Any]]:
    source_id = source.get("id")
    creature_id = source.get("creatureId")
    if type(source_id) is not str or not source_id or type(creature_id) is not str:
        raise EngineInputError("selected Stench source identity is invalid")
    definition = host.definition_for(state, dict(source))
    if definition.get("schema") == 2:
        if (
            source_id not in semantic_ids
            or _SEMANTIC_ID_RE.fullmatch(creature_id) is None
            or definition.get("kind") != "pf2er-creature"
            or definition.get("id") != creature_id
            or "source" in definition
        ):
            raise EngineInputError("semantic Stench source identity is invalid")
    elif definition.get("schema") == 1:
        if source_id in semantic_ids:
            raise EngineInputError("legacy Stench source identity is invalid")
    else:
        raise EngineInputError("selected Stench source identity is invalid")
    return source_id, definition


def project_public_state(
    state: Mapping[str, Any],
    context: Mapping[str, Any],
    host: StenchRuntimeHost,
) -> dict[str, Any]:
    """Project the selected semantic Stench family's browser-safe state."""

    if not isinstance(state, dict) or not isinstance(context, Mapping):
        raise EngineInputError("Stench public projection input is invalid")
    width, height, participant_ids, semantic_ids = (
        _public_projection_context(state, context, host)
    )

    # Validate the complete private adjudication matrix without publishing any
    # target row, eligibility value, or other GM-only olfactory evidence.
    validated_olfactory_aura_rows(state, host)
    passive_auras: list[dict[str, Any]] = []
    aura_index: dict[tuple[str, str], dict[str, Any]] = {}
    for source, ability in source_abilities(state, host):
        if not source_is_active(source):
            continue
        source_id, definition = _validated_stench_source_identity(
            state,
            source,
            semantic_ids,
            host,
        )
        ability_id = ability.get("id")
        mechanic = ability.get("mechanic")
        geometry = (
            mechanic.get("geometry")
            if isinstance(mechanic, Mapping)
            else None
        )
        radius_feet = (
            geometry.get("radiusFeet")
            if isinstance(geometry, Mapping)
            else None
        )
        rule_ref, rule_refs = semantic_rule_contract(ability)
        if (
            type(ability_id) is not str
            or not ability_id
            or ability.get("supported") is not True
            or ability.get("kind") != "passive"
            or ability.get("actionCost") is not None
            or ability.get("traits") != list(STENCH_TRAITS)
            or not isinstance(mechanic, Mapping)
            or mechanic.get("type") != STENCH_MECHANIC_TYPE
            or mechanic.get("family") != STENCH_FAMILY
            or type(radius_feet) is not int
            or radius_feet <= 0
            or radius_feet % 5
            or dict(geometry)
            != {
                "type": "emanation",
                "radiusFeet": radius_feet,
                "boundary": "inclusive",
            }
            or definition.get("schema") == 2
            and ("rule" in ability or "rules" in mechanic)
            or (source_id, ability_id) in aura_index
        ):
            raise EngineInputError("compiled passive Stench aura is invalid")
        aura = {
            "sourceParticipantId": source_id,
            "abilityId": ability_id,
            "radiusFeet": radius_feet,
            "squares": _public_aura_squares(
                state,
                source,
                radius_feet=radius_feet,
                width=width,
                height=height,
            ),
            "ruleRef": rule_ref,
            "ruleRefs": deepcopy(rule_refs),
        }
        passive_auras.append(aura)
        aura_index[(source_id, ability_id)] = aura

    participant_conditions: dict[str, list[dict[str, Any]]] = {}
    turn = state.get("turn")
    order = turn.get("order") if isinstance(turn, Mapping) else None
    current_step = (
        turn.get("initiativeStep") if isinstance(turn, Mapping) else None
    )
    if (
        not isinstance(order, list)
        or not order
        or set(order) != participant_ids
        or len(order) != len(participant_ids)
        or type(current_step) is not int
        or current_step < 0
    ):
        raise EngineInputError("Stench public projection turn is invalid")
    for effect in immunity_effects(state, host):
        target_id = str(effect["targetParticipantId"])
        source_id = str(effect["sourceParticipantId"])
        if target_id not in participant_ids or source_id not in participant_ids:
            raise EngineInputError(
                "Stench immunity participant is invalid"
            )
        source = host.participant_map(state)[source_id]
        _validated_stench_source_identity(state, source, semantic_ids, host)
        expires_at = effect.get("expiresAtInitiativeStep")
        if type(expires_at) is not int or expires_at <= current_step:
            raise EngineInputError("Stench temporary immunity timing is invalid")
        remaining = (expires_at - current_step + len(order) - 1) // len(order)
        participant_conditions.setdefault(target_id, []).append(
            {
                "name": (
                    "Stench immunity "
                    f"({remaining} round"
                    f"{'' if remaining == 1 else 's'} remaining)"
                ),
                "sourceParticipantId": source_id,
                "ruleRef": STENCH_ABILITY_RULE_REF,
            }
        )

    contribution: dict[str, Any] = {
        "fields": (
            {"passiveAuras": passive_auras}
            if passive_auras
            else {}
        ),
        "participantConditions": participant_conditions,
    }
    pending = state.get("pendingDecision")
    if isinstance(pending, Mapping) and pending.get("type") == "StenchSave":
        required = {
            "type",
            "mechanicType",
            "participantId",
            "sourceParticipantId",
            "targetParticipantId",
            "abilityId",
            "trigger",
            "savingThrow",
            "ruleRef",
            "ruleRefs",
        }
        saving_throw = pending.get("savingThrow")
        source_id = pending.get("sourceParticipantId")
        target_id = pending.get("targetParticipantId")
        ability_id = pending.get("abilityId")
        matching_aura = aura_index.get((source_id, ability_id))
        if (
            set(pending) != required
            or pending.get("mechanicType") != STENCH_MECHANIC_TYPE
            or type(source_id) is not str
            or source_id not in participant_ids
            or type(target_id) is not str
            or target_id not in participant_ids
            or pending.get("participantId") != target_id
            or pending.get("trigger")
            not in {"outside-to-inside", "target-start-turn-inside"}
            or matching_aura is None
            or pending.get("ruleRef") != matching_aura["ruleRef"]
            or pending.get("ruleRefs") != matching_aura["ruleRefs"]
            or not isinstance(saving_throw, Mapping)
            or set(saving_throw)
            != {"type", "baseDC", "dc", "dcBreakdown", "rollField"}
            or saving_throw.get("type") != "fortitude"
            or saving_throw.get("rollField") != "fortitudeSaveRoll"
            or type(saving_throw.get("baseDC")) is not int
            or int(saving_throw["baseDC"]) <= 0
            or type(saving_throw.get("dc")) is not int
            or int(saving_throw["dc"]) <= 0
            or not isinstance(saving_throw.get("dcBreakdown"), Mapping)
        ):
            raise EngineInputError("pending Stench save is invalid")
        contribution["pendingDecision"] = {
            "type": "StenchSave",
            "participantId": target_id,
            "sourceParticipantId": source_id,
            "targetParticipantId": target_id,
            "abilityId": ability_id,
            "trigger": pending["trigger"],
            "savingThrow": {
                "type": "fortitude",
                "dc": int(saving_throw["dc"]),
            },
            "ruleRef": matching_aura["ruleRef"],
            "ruleRefs": deepcopy(matching_aura["ruleRefs"]),
        }
    return contribution


FRAGMENT = MechanicFamilyFragment(
    family_id="stench",
    mechanic_types=(STENCH_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="monster-core-stench",
            mechanic_type=STENCH_MECHANIC_TYPE,
            compiler=compile_stench,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "OLFACTORY_AURA_ELIGIBILITY",
    "STENCH_ABILITY_RULE_REF",
    "STENCH_FAMILY",
    "STENCH_IMMUNITY_ROUNDS",
    "STENCH_MECHANIC_TYPE",
    "STENCH_RULE_REFS",
    "STENCH_SAVE_EVENT_TYPE",
    "StenchRuntimeHost",
    "VerifiedStenchCompilation",
    "activate_next_save_decision",
    "apply_retch_immunity_upgrade",
    "bind_verified_compilation",
    "compile_stench",
    "compile_stench_verified",
    "create_immunity",
    "entry_candidates_for_pose",
    "enrich_controller_save",
    "expire_immunities",
    "finish_resume",
    "immunity_effects",
    "inside_keys",
    "normalize_adjudications",
    "project_public_state",
    "queue_save_decisions",
    "project_controller_pending_decision",
    "resolve_save_decision",
    "semantic_rule_contract",
    "source_abilities",
    "source_is_active",
    "start_candidates",
    "stench_provider_requirements",
    "target_has_immunity",
    "target_is_inside",
    "validate_runtime_state",
    "validated_olfactory_aura_rows",
]

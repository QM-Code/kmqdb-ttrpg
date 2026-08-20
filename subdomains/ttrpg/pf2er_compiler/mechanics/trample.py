"""Compile and execute the reviewed Monster Core Trample source family.

The compiler projection remains compile/link-only until a selected rules
environment mounts the optional Trample runtime.  The family-local runtime
then executes the supported simple-map activity through a narrow kernel host;
difficult or hazardous terrain and generic multi-target reaction
serialization remain explicit completeness deferrals.

The public compiler accepts an exact ``SourceAuthorityAdapter`` and fully
revalidates its consumer and provider claims.  The linker does not accept a
caller-built Strike index: it reconstructs the complete local Melee/Ranged
inventory from the same verified creature carrier and revalidates exact
Strike/Damage receipts from that carrier.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field, fields
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Literal, TypeAlias, final

from ..errors import EngineInputError
from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
)
from .source_authority import (
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceReceipt,
    SourceAuthorityAdapter,
    TextSpan,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
)
from .source_values import parse_decimal_integer


FAMILY_ID = "trample"
COMPILER_ID = "trample"
ABILITY_ID = "pf2er:trample"
MECHANIC_TYPE = "stride-through-basic-save-damage"
RUNTIME_FAMILY_ID = "pf2er-trample-runtime"
RUNTIME_PACKAGE_ID = "gladiator:pf2er-trample-runtime@1.0.0"
RUNTIME_CAPABILITY_ID = "gladiator:pf2er-trample-activity@1.0.0"
MONSTER_CORE_SOURCE_ID = "core-mc1"
TRAMPLE_GLOSSARY_LOCATOR = "358.2"
TRAMPLE_REFERENCE_PAGE = 360

MAX_CREATURE_MEMBERS = 4_096
MAX_LOCAL_STRIKES = 256
MAX_SOURCE_TEXT_BYTES = 4_096
MAX_CREATURE_NAME_BYTES = 512
MAX_STRIKE_NAME_BYTES = 256
MAX_SAVE_DC = 10_000
MAX_DAMAGE_DICE = 10_000
MAX_DAMAGE_DIE_SIDES = 10_000
MAX_DAMAGE_MODIFIER_ABS = 1_000_000
MAX_DAMAGE_TYPE_BYTES = 128
MAX_PROJECTION_DEPTH = 64
MAX_PROJECTION_NODES = 20_000
MAX_PROJECTION_CONTAINER_ITEMS = 4_096
MAX_PROJECTION_TEXT_BYTES = 1_000_000
MAX_RUNTIME_PATH_STEPS = 1_024
MAX_RUNTIME_TARGETS = 256
MAX_RUNTIME_FOOTPRINT_SQUARES = 64

TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS = (
    "difficult-terrain",
    "hazardous-terrain",
    "generic-multi-target-damage-reaction-serialization",
)

_SIZE_RANKS = MappingProxyType(
    {
        "Tiny": 0,
        "Small": 1,
        "Medium": 2,
        "Large": 3,
        "Huge": 4,
        "Gargantuan": 5,
    }
)
_POSITIVE_DECIMAL = r"[1-9][0-9]*"
_TRAMPLE_DESCRIPTION_RE = re.compile(
    rf"^(?P<maximum_size>"
    rf"Tiny|Small|Medium|Large|Huge|Gargantuan"
    rf") or smaller, "
    rf"(?P<strike>[a-z][a-z0-9' -]*), "
    rf"DC (?P<dc>{_POSITIVE_DECIMAL}) "
    rf"\(page (?P<page>{_POSITIVE_DECIMAL})\)$",
    re.ASCII,
)
_DAMAGE_COMPONENT_RE = re.compile(
    rf"^(?P<count>{_POSITIVE_DECIMAL})"
    rf"d(?P<sides>{_POSITIVE_DECIMAL})"
    rf"(?P<modifier>[+-][0-9]+)? "
    rf"(?P<damage_type>[A-Za-z][A-Za-z -]*?)$",
    re.ASCII,
)
_NUMERIC_DAMAGE_PREFIX_RE = re.compile(r"^[0-9]+d", re.ASCII)


def _rule(
    rule_id: str,
    source_id: str,
    locator: str,
    block_sha256: str,
    *,
    carrier_path: tuple[RawMemberStep, ...] = (),
) -> RuleRequirement:
    return RuleRequirement(
        rule_id=rule_id,
        source_id=source_id,
        locator=locator,
        carrier_path=carrier_path,
        expected_block_sha256=block_sha256,
    )


# These hashes pin the exact reviewed provider blocks in the local PF2ER
# authority snapshot.  The authority digest may change when unrelated rows
# are refreshed; these stable block hashes may not.
TRAMPLE_RULE_REQUIREMENTS = MappingProxyType(
    {
        "trample-glossary": _rule(
            "trample-glossary",
            "core-mc1",
            "358.2",
            "02c0549ccadd9b8ae8f927e701f363ade8391727cc4fa223a90b937f705f397b",
            carrier_path=(RawMemberStep("^.ability", 37),),
        ),
        "degree-of-success": _rule(
            "degree-of-success",
            "core-pc1",
            "401.4",
            "05a8ea41e782723a63bed00663d4a4ffadfb446edf869af24b4f2f8a61d3c033",
        ),
        "basic-reflex-save": _rule(
            "basic-reflex-save",
            "core-pc1",
            "404.1",
            "711bf9ea76187cd3bc4040c06867a23efe04f111779b6717a4ac375aa3759239",
        ),
        "doubling-and-halving-damage": _rule(
            "doubling-and-halving-damage",
            "core-pc1",
            "407.1",
            "c68abb8b952f2c89fba6ac33fe588824cd763f9c641364871198a98a3f565943",
        ),
        "damage-defenses": _rule(
            "damage-defenses",
            "core-pc1",
            "407.3",
            "70d4b59f1e222320d84c65c73eee11d14210e6800d7ecdbd3ce000da6f13bc21",
        ),
        "subordinate-actions": _rule(
            "subordinate-actions",
            "core-pc1",
            "414.4",
            "6cca42e564d687b1b3fd6ce074ad87b1a8e055f7f0dd8fe0383bad3a81e4fa1d",
        ),
        "gaining-and-losing-actions": _rule(
            "gaining-and-losing-actions",
            "core-pc1",
            "415.2",
            "c0d99a4b3fcbf74fb36cbf34078f736851804d5bfcc9ae9233b672666ebd4896",
        ),
        "disruption": _rule(
            "disruption",
            "core-pc1",
            "415.3",
            "e4cbbde8bdd6b5e20a99f8e66687e3b98620ba4eb4be67b169de239b0de6bcc9",
        ),
        "stride": _rule(
            "stride",
            "core-pc1",
            "418.3",
            "a15ba248a6375c3a4f8a4c300b16b4fd2c0f433cb0d6b582e1bbfc49fce9193f",
        ),
        "movement": _rule(
            "movement",
            "core-pc1",
            "420.1",
            "8057ab6ad13dab84b0fed6a4c6fa0fd595989a68a5d8946b9bdfce3de5a63cf0",
        ),
        "land-speed": _rule(
            "land-speed",
            "core-pc1",
            "420.4",
            "625d62f213cadf80d6dd6bff2a2b57ea558174462211db5b36f1d99891fa4433",
        ),
        "grid-movement": _rule(
            "grid-movement",
            "core-pc1",
            "421.5",
            "1610c62fb122a577e3f69ec6b2e3f1273f6cb7e535ee9d5529291637a3b9ce67",
        ),
        "diagonal-movement": _rule(
            "diagonal-movement",
            "core-pc1",
            "421.6",
            "8932a0244b193fd5fb2dc7ebb8a0623cbf9304d52daa9d03845578a5259ed210",
        ),
        "size-space-reach": _rule(
            "size-space-reach",
            "core-pc1",
            "421.8",
            "57f6c8bd51c2367bedfda5464ec295229a54363d5576a671fbda1fda3ab01fb6",
        ),
        "creature-space-movement": _rule(
            "creature-space-movement",
            "core-pc1",
            "422.3",
            "62ef4117bd8ca96e49011793c59b7325af76e8c57f60291aa0f0cd7e1b07a3e0",
        ),
        "difficult-terrain": _rule(
            "difficult-terrain",
            "core-pc1",
            "423.4",
            "f9fd32133b57ac1fd215780b357c66f5cafd1e9707f11b19d8e0e9ac8e431663",
        ),
        "hazardous-terrain": _rule(
            "hazardous-terrain",
            "core-pc1",
            "423.6",
            "2db44c3550d4dc17042f03a119dd8e750f262c221b6f55686bfed6ec4ee8b172",
        ),
    }
)


RuntimeDeferralKind: TypeAlias = Literal[
    "doubled-speed-movement",
    "footprint-and-transient-overlap",
    "movement-reaction-windows",
    "basic-reflex-resolution",
    "linked-strike-damage-resolution",
]
ReviewedRequirements: TypeAlias = tuple[
    tuple[str, RuleRequirement],
    ...,
]


@final
@dataclass(frozen=True, slots=True)
class RuntimeDeferral:
    kind: RuntimeDeferralKind
    provider_rule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        raise TypeError("RuntimeDeferral contract is not bound")

    def as_serialized(self) -> dict[str, Any]:
        raise TypeError("RuntimeDeferral contract is not bound")


def _bind_runtime_deferral_contract():
    canonical_pairs = (
        (
            "doubled-speed-movement",
            (
                "trample-glossary",
                "subordinate-actions",
                "gaining-and-losing-actions",
                "stride",
                "movement",
                "land-speed",
                "grid-movement",
                "diagonal-movement",
                "difficult-terrain",
                "hazardous-terrain",
            ),
        ),
        (
            "footprint-and-transient-overlap",
            (
                "trample-glossary",
                "size-space-reach",
                "creature-space-movement",
            ),
        ),
        (
            "movement-reaction-windows",
            (
                "trample-glossary",
                "disruption",
            ),
        ),
        (
            "basic-reflex-resolution",
            (
                "trample-glossary",
                "degree-of-success",
                "basic-reflex-save",
                "doubling-and-halving-damage",
            ),
        ),
        (
            "linked-strike-damage-resolution",
            (
                "trample-glossary",
                "damage-defenses",
            ),
        ),
    )

    def validate(value: RuntimeDeferral) -> None:
        if (
            type(value) is not RuntimeDeferral
            or type(value.kind) is not str
            or type(value.provider_rule_ids) is not tuple
            or any(
                type(rule_id) is not str
                for rule_id in value.provider_rule_ids
            )
            or (value.kind, value.provider_rule_ids)
            not in canonical_pairs
        ):
            raise TypeError(
                "RuntimeDeferral must match one exact canonical pair"
            )

    def serialize(value: RuntimeDeferral) -> dict[str, Any]:
        validate(value)
        return {
            "kind": value.kind,
            "providerRuleIds": list(value.provider_rule_ids),
        }

    def build() -> tuple[RuntimeDeferral, ...]:
        return tuple(
            RuntimeDeferral(kind, provider_rule_ids)
            for kind, provider_rule_ids in canonical_pairs
        )

    return validate, serialize, build


(
    _runtime_deferral_validate,
    _runtime_deferral_serialize,
    _build_runtime_deferrals,
) = _bind_runtime_deferral_contract()
RuntimeDeferral.__post_init__ = _runtime_deferral_validate
RuntimeDeferral.as_serialized = _runtime_deferral_serialize
_RUNTIME_DEFERRALS = _build_runtime_deferrals()


def _closed_json_transform(
    value: Any,
    *,
    freeze: bool,
    label: str,
) -> Any:
    active: set[int] = set()
    node_count = 0

    def visit(item: Any, depth: int) -> Any:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_PROJECTION_NODES:
            raise EngineInputError(
                f"{label} exceeds its node bound"
            )
        if depth > MAX_PROJECTION_DEPTH:
            raise EngineInputError(
                f"{label} exceeds its depth bound"
            )
        if item is None or type(item) in {bool, int}:
            return item
        if type(item) is str:
            if len(item.encode("utf-8")) > MAX_PROJECTION_TEXT_BYTES:
                raise EngineInputError(
                    f"{label} exceeds its text bound"
                )
            return item

        mapping_type = dict if freeze else MappingProxyType
        sequence_type = list if freeze else tuple
        if type(item) is mapping_type:
            if len(item) > MAX_PROJECTION_CONTAINER_ITEMS:
                raise EngineInputError(
                    f"{label} mapping exceeds its item bound"
                )
            identity = id(item)
            if identity in active:
                raise EngineInputError(f"{label} contains a cycle")
            active.add(identity)
            try:
                result = {}
                for key, child in item.items():
                    if type(key) is not str:
                        raise EngineInputError(
                            f"{label} mapping key is not exact text"
                        )
                    if (
                        len(key.encode("utf-8"))
                        > MAX_PROJECTION_TEXT_BYTES
                    ):
                        raise EngineInputError(
                            f"{label} mapping key exceeds its text bound"
                        )
                    result[key] = visit(child, depth + 1)
            finally:
                active.remove(identity)
            return MappingProxyType(result) if freeze else result
        if type(item) is sequence_type:
            if len(item) > MAX_PROJECTION_CONTAINER_ITEMS:
                raise EngineInputError(
                    f"{label} sequence exceeds its item bound"
                )
            identity = id(item)
            if identity in active:
                raise EngineInputError(f"{label} contains a cycle")
            active.add(identity)
            try:
                result = [
                    visit(child, depth + 1)
                    for child in item
                ]
            finally:
                active.remove(identity)
            return tuple(result) if freeze else result
        raise EngineInputError(
            f"{label} is not closed JSON: {type(item).__name__}"
        )

    return visit(value, 0)


def _freeze_json(value: Any) -> Any:
    return _closed_json_transform(
        value,
        freeze=True,
        label="Trample projection",
    )


def _thaw_json(value: Any) -> Any:
    return _closed_json_transform(
        value,
        freeze=False,
        label="Trample stored projection",
    )


@final
@dataclass(
    frozen=True,
    slots=True,
    init=False,
)
class CompiledTrample:
    """Opaque authority-backed compile result."""

    _authority: SourceAuthorityAdapter = field(repr=False)
    _source: VerifiedSourceSelection = field(repr=False)
    _rules: tuple[VerifiedRuleReceipt, ...] = field(repr=False)
    _ability: Mapping[str, Any] = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "CompiledTrample can only be constructed by compile_trample"
        )

    @property
    def source_receipt(self) -> SourceReceipt:
        self._authority.validate_selection(self._source)
        return self._source.receipt

    def as_ability_update(self) -> dict[str, Any]:
        return _thaw_json(self._ability)

@final
@dataclass(frozen=True, slots=True, init=False)
class LinkedTrample:
    """Opaque Trample result linked to one verified local Strike carrier."""

    _compiled: CompiledTrample = field(repr=False)
    _strike: VerifiedSourceSelection = field(repr=False)
    _damage: VerifiedSourceSelection = field(repr=False)
    _ability: Mapping[str, Any] = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "LinkedTrample can only be constructed by "
            "link_trample_strike"
        )

    @property
    def strike_receipt(self) -> SourceReceipt:
        self._compiled._authority.validate_selection(self._strike)
        return self._strike.receipt

    @property
    def damage_receipt(self) -> SourceReceipt:
        self._compiled._authority.validate_selection(self._damage)
        return self._damage.receipt

    def as_ability_update(self) -> dict[str, Any]:
        return _thaw_json(self._ability)


def _utf8_bound(value: str, maximum: int, label: str) -> str:
    if type(value) is not str:
        raise EngineInputError(f"{label} must be exact text")
    if len(value.encode("utf-8")) > maximum:
        raise EngineInputError(f"{label} exceeds its byte bound")
    return value


def _bounded_positive_decimal(
    value: str,
    *,
    maximum: int,
) -> int | None:
    parsed = parse_decimal_integer(value)
    if parsed is None or parsed <= 0 or parsed > maximum:
        return None
    return parsed


def _strike_id(source_name: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "-",
        source_name.casefold(),
    ).strip("-")


def _source_parameters(
    source: VerifiedSourceSelection,
) -> tuple[str, str, str, int] | None:
    if (
        type(source) is not VerifiedSourceSelection
        or source.address.source_id != MONSTER_CORE_SOURCE_ID
        or source.address.span is not None
        or type(source.address.selection_path) is not tuple
        or len(source.address.selection_path) != 1
        or type(source.address.selection_path[0]) is not RawMemberStep
        or source.address.selection_path[0].raw_key != "!.Trample"
        or not source.address.carrier_path
        or type(source.address.carrier_path[-1]) is not RawMemberStep
        or source.address.carrier_path[-1].raw_key != "^.creature"
        or type(source.raw_member) is not RawSourceMember
        or source.raw_member.key != "!.Trample"
        or type(source.raw_value) is not RawSourceObject
        or source.selected_value is not source.raw_value
        or type(source.carrier.raw_block) is not RawSourceObject
    ):
        return None

    block = source.carrier.raw_block
    if len(block.members) > MAX_CREATURE_MEMBERS:
        raise EngineInputError("Trample creature block exceeds member bound")
    names = block.values("Name")
    if len(names) != 1 or type(names[0]) is not str:
        return None
    creature_name = _utf8_bound(
        names[0],
        MAX_CREATURE_NAME_BYTES,
        "Trample creature Name",
    )
    if not creature_name or creature_name != creature_name.strip():
        return None

    raw_value = source.raw_value
    if (
        len(raw_value.members) != 2
        or raw_value.keys.count("Action") != 1
        or raw_value.keys.count("Description") != 1
        or frozenset(raw_value.keys) != {"Action", "Description"}
    ):
        return None
    action = raw_value.values("Action")[0]
    description = raw_value.values("Description")[0]
    if action != "three" or type(description) is not str:
        return None
    _utf8_bound(
        description,
        MAX_SOURCE_TEXT_BYTES,
        "Trample Description",
    )
    match = _TRAMPLE_DESCRIPTION_RE.fullmatch(description)
    if match is None:
        return None
    strike_name = _utf8_bound(
        match.group("strike"),
        MAX_STRIKE_NAME_BYTES,
        "Trample listed Strike name",
    )
    save_dc = _bounded_positive_decimal(
        match.group("dc"),
        maximum=MAX_SAVE_DC,
    )
    page = _bounded_positive_decimal(
        match.group("page"),
        maximum=TRAMPLE_REFERENCE_PAGE,
    )
    if save_dc is None or page != TRAMPLE_REFERENCE_PAGE:
        return None
    return (
        creature_name,
        match.group("maximum_size"),
        strike_name,
        save_dc,
    )


def _validated_rules(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    rule_receipts: object,
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
    expected_contract_fingerprint: str,
) -> tuple[VerifiedRuleReceipt, ...]:
    _require_contract(
        requirements,
        deferrals,
        expected_contract_fingerprint,
    )
    if type(rule_receipts) is not dict:
        raise TypeError("Trample rule receipts must be one exact mapping")
    rule_ids = tuple(rule_id for rule_id, _item in requirements)
    if (
        frozenset(rule_receipts)
        != frozenset(rule_ids)
        or any(type(key) is not str for key in rule_receipts)
    ):
        raise EngineInputError(
            "Trample rule receipts are incomplete or contain extras"
        )

    result = []
    for rule_id, requirement in requirements:
        receipt = rule_receipts[rule_id]
        if type(receipt) is not VerifiedRuleReceipt:
            raise TypeError(
                "Trample rule receipt must be an exact "
                f"VerifiedRuleReceipt: {rule_id}"
            )
        result.append(receipt)

    receipts = tuple(result)
    authority.require_shared_authority(source, receipts)
    for receipt, (rule_id, requirement) in zip(
        receipts, requirements, strict=True
    ):
        selection = receipt.selection
        if (
            type(selection) is not VerifiedSourceSelection
            or receipt.rule_id != rule_id
            or receipt.requirement != requirement
            or receipt.receipt != selection.receipt
            or selection.carrier.ruleset != source.carrier.ruleset
            or selection.carrier.authority_digest
            != source.carrier.authority_digest
            or selection.address.source_id != requirement.source_id
            or selection.address.locator != requirement.locator
            or selection.address.carrier_path
            != requirement.carrier_path
            or selection.address.selection_path
            != requirement.selection_path
            or selection.address.span != requirement.span
            or (
                requirement.expected_block_sha256 is not None
                and selection.block_sha256
                != requirement.expected_block_sha256
            )
            or (
                requirement.expected_member_sha256 is not None
                and selection.member_sha256
                != requirement.expected_member_sha256
            )
            or (
                requirement.expected_value_sha256 is not None
                and selection.value_sha256
                != requirement.expected_value_sha256
            )
            or (
                requirement.expected_selection_sha256 is not None
                and selection.selection_sha256
                != requirement.expected_selection_sha256
            )
        ):
            raise EngineInputError(
                f"Trample verified rule receipt disagrees: {rule_id}"
            )
    return receipts


def _serialized_rules(
    receipts: tuple[VerifiedRuleReceipt, ...],
    requirements: ReviewedRequirements,
) -> dict[str, Any]:
    if len(receipts) != len(requirements):
        raise EngineInputError(
            "Trample provider proof has the wrong cardinality"
        )
    result = {}
    for receipt, (rule_id, requirement) in zip(
        receipts, requirements, strict=True
    ):
        if (
            type(receipt) is not VerifiedRuleReceipt
            or receipt.rule_id != rule_id
            or receipt.requirement != requirement
        ):
            raise EngineInputError(
                f"Trample provider proof is noncanonical: {rule_id}"
            )
        result[rule_id] = receipt.as_serialized()
    return result


def _contract_payload(
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
) -> dict[str, Any]:
    return {
        "schema": 1,
        "requirements": [
            {
                "ruleId": rule_id,
                "requirement": requirement.as_serialized(),
            }
            for rule_id, requirement in requirements
        ],
        "deferrals": [
            item.as_serialized()
            for item in deferrals
        ],
    }


def _contract_fingerprint(
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
) -> str:
    try:
        payload = _contract_payload(requirements, deferrals)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (AttributeError, TypeError, ValueError) as failure:
        raise EngineInputError(
            "Trample reviewed contract is malformed"
        ) from failure
    return hashlib.sha256(encoded).hexdigest()


def _require_contract(
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
    expected_fingerprint: str,
) -> None:
    if (
        type(requirements) is not tuple
        or len(requirements) != 17
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not RuleRequirement
            or item[0] != item[1].rule_id
            for item in requirements
        )
    ):
        raise EngineInputError(
            "Trample reviewed provider contract is not exact"
        )
    rule_ids = tuple(item[0] for item in requirements)
    if len(frozenset(rule_ids)) != 17:
        raise EngineInputError(
            "Trample reviewed provider IDs are not unique"
        )
    if (
        type(deferrals) is not tuple
        or len(deferrals) != 5
        or any(
            type(item) is not RuntimeDeferral
            or type(item.kind) is not str
            or type(item.provider_rule_ids) is not tuple
            or any(
                type(rule_id) is not str
                for rule_id in item.provider_rule_ids
            )
            for item in deferrals
        )
    ):
        raise EngineInputError(
            "Trample runtime deferral contract is not exact"
        )
    cited_ids = {
        rule_id
        for item in deferrals
        for rule_id in item.provider_rule_ids
    }
    if cited_ids != set(rule_ids):
        raise EngineInputError(
            "Trample runtime deferrals do not cite the full provider set"
        )
    if (
        type(expected_fingerprint) is not str
        or len(expected_fingerprint) != 64
        or _contract_fingerprint(requirements, deferrals)
        != expected_fingerprint
    ):
        raise EngineInputError(
            "Trample reviewed contract fingerprint disagrees"
        )


def _derive_compiled_ability(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    receipts: tuple[VerifiedRuleReceipt, ...],
    parameters: tuple[str, str, str, int],
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
    contract_fingerprint: str,
) -> dict[str, Any]:
    _require_contract(
        requirements,
        deferrals,
        contract_fingerprint,
    )
    creature_name, maximum_size, strike_name, save_dc = parameters
    listed_id = _strike_id(strike_name)
    if not listed_id:
        raise EngineInputError("Trample listed Strike ID is empty")

    source_receipt = source.receipt.as_serialized()
    if requirements[0][0] != "trample-glossary":
        raise EngineInputError(
            "Trample glossary provider position is noncanonical"
        )
    glossary = receipts[0]
    return {
        "supported": True,
        "mechanic": {
            "type": MECHANIC_TYPE,
            "actionCost": 3,
            "movement": {
                "subordinateAction": "Stride",
                "movementMode": "land",
                "speedMultiplier": 2,
                "targetTransit": "listed-size-or-smaller",
                "legalEndpoint": "ordinary-occupiable-nonoverlapping-space",
            },
            "targeting": {
                "selection": "first-space-entry",
                "maximumSize": maximum_size.casefold(),
                "maximumSizeRank": _SIZE_RANKS[maximum_size],
                "sameTargetLimit": 1,
                "identity": "participantId",
                "includesAllies": True,
            },
            "listedStrikeSourceName": strike_name,
            "listedStrikeId": listed_id,
            "listedStrikeResolution": (
                "verified-complete-local-melee-index"
            ),
            "sharedDamageRoll": True,
            "savingThrow": {
                "type": "reflex",
                "dc": save_dc,
                "basic": True,
            },
            "multipleAttackPenalty": {
                "reads": False,
                "changes": False,
            },
            "source": {
                "creatureName": creature_name,
                "rawDescription": source.raw_value.values(
                    "Description"
                )[0],
                "receipt": source_receipt,
            },
            "sourceRecords": [
                {
                    "kind": "named-ability",
                    "source": source_receipt,
                },
                {
                    "kind": "page-reference",
                    "page": TRAMPLE_REFERENCE_PAGE,
                    "source": glossary.receipt.as_serialized(),
                },
            ],
            "rules": _serialized_rules(receipts, requirements),
            "runtime": {
                "status": "deferred",
                "deferrals": [
                    item.as_serialized()
                    for item in deferrals
                ],
            },
            "contractProof": {
                "schema": 1,
                "sha256": contract_fingerprint,
                "providerCount": len(requirements),
                "deferralCount": len(deferrals),
            },
        },
        "rule": {
            "sourceId": MONSTER_CORE_SOURCE_ID,
            "locator": TRAMPLE_GLOSSARY_LOCATOR,
        },
        "traits": [],
    }


def _new_compiled(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    receipts: tuple[VerifiedRuleReceipt, ...],
    parameters: tuple[str, str, str, int],
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
    contract_fingerprint: str,
) -> CompiledTrample:
    ability = _derive_compiled_ability(
        authority,
        source,
        receipts,
        parameters,
        requirements,
        deferrals,
        contract_fingerprint,
    )
    result = object.__new__(CompiledTrample)
    object.__setattr__(result, "_authority", authority)
    object.__setattr__(result, "_source", source)
    object.__setattr__(result, "_rules", receipts)
    object.__setattr__(result, "_ability", _freeze_json(ability))
    return result


def _compile_trample_impl(
    authority: object,
    source: object,
    rule_receipts: object,
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
    contract_fingerprint: str,
) -> CompiledTrample | None:
    """Compile one exact verifier-issued Core MC1 ``!.Trample`` member."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "compile_trample requires an exact SourceAuthorityAdapter"
        )
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "compile_trample requires a VerifiedSourceSelection"
        )
    authority.validate_selection(source)
    parameters = _source_parameters(source)
    if parameters is None:
        return None
    receipts = _validated_rules(
        authority,
        source,
        rule_receipts,
        requirements,
        deferrals,
        contract_fingerprint,
    )
    return _new_compiled(
        authority,
        source,
        receipts,
        parameters,
        requirements,
        deferrals,
        contract_fingerprint,
    )


def _validated_compiled(
    value: object,
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
    contract_fingerprint: str,
) -> tuple[CompiledTrample, dict[str, Any]]:
    _require_contract(
        requirements,
        deferrals,
        contract_fingerprint,
    )
    if type(value) is not CompiledTrample:
        raise TypeError(
            "Trample linker requires an exact CompiledTrample"
        )
    try:
        authority = value._authority
        source = value._source
        rules = value._rules
        ability = value._ability
    except AttributeError as failure:
        raise EngineInputError(
            "Trample compiled capability is incomplete"
        ) from failure
    if (
        type(authority) is not SourceAuthorityAdapter
        or type(source) is not VerifiedSourceSelection
        or type(rules) is not tuple
        or len(rules) != len(requirements)
        or any(type(item) is not VerifiedRuleReceipt for item in rules)
    ):
        raise EngineInputError("Trample compiled capability is forged")
    authority.validate_selection(source)
    parameters = _source_parameters(source)
    if parameters is None:
        raise EngineInputError(
            "Trample compiled source is no longer canonical"
        )
    try:
        supplied_rules = {
            item.rule_id: item
            for item in rules
        }
    except AttributeError as failure:
        raise EngineInputError(
            "Trample compiled provider proof is incomplete"
        ) from failure
    receipts = _validated_rules(
        authority,
        source,
        supplied_rules,
        requirements,
        deferrals,
        contract_fingerprint,
    )
    expected = _derive_compiled_ability(
        authority,
        source,
        receipts,
        parameters,
        requirements,
        deferrals,
        contract_fingerprint,
    )
    actual = _thaw_json(ability)
    if expected != actual:
        raise EngineInputError("Trample compiled capability is stale")
    return value, expected


def _complete_strike_index(
    compiled: CompiledTrample,
) -> tuple[
    tuple[str, str, int, int, RawSourceObject],
    ...,
]:
    block = compiled._source.carrier.raw_block
    if type(block) is not RawSourceObject:
        raise EngineInputError("Trample creature carrier is not exact")
    if len(block.members) > MAX_CREATURE_MEMBERS:
        raise EngineInputError("Trample creature block exceeds member bound")

    result = []
    identities: dict[str, str] = {}
    for outer_ordinal, member in enumerate(block.members):
        if (
            member.key.strip() in {"Melee", "Ranged"}
            and member.key not in {"Melee", "Ranged"}
        ):
            raise EngineInputError(
                "Trample creature has a whitespace-conflicting Strike field"
            )
        if member.key not in {"Melee", "Ranged"}:
            continue
        if type(member.value) is not RawSourceArray:
            raise EngineInputError(
                "Trample creature Strike field must be an exact array"
            )
        mode = "melee" if member.key == "Melee" else "ranged"
        for strike_ordinal, item in enumerate(member.value.items):
            if len(result) >= MAX_LOCAL_STRIKES:
                raise EngineInputError(
                    "Trample local Strike index exceeds its bound"
                )
            if type(item) is not RawSourceObject:
                raise EngineInputError(
                    "Trample local Strike entry must be an exact object"
                )
            names = item.values("Name")
            if len(names) != 1 or type(names[0]) is not str:
                raise EngineInputError(
                    "Trample local Strike has no exact unique Name"
                )
            name = _utf8_bound(
                names[0],
                MAX_STRIKE_NAME_BYTES,
                "Trample local Strike Name",
            )
            if not name or name != name.strip():
                raise EngineInputError(
                    "Trample local Strike Name is not canonical"
                )
            identity = _strike_id(name)
            if not identity:
                raise EngineInputError(
                    "Trample local Strike ID is empty"
                )
            if identity in identities:
                raise EngineInputError(
                    "Trample complete local Strike index has an "
                    f"identity collision: {identity}"
                )
            identities[identity] = name
            result.append(
                (
                    mode,
                    name,
                    outer_ordinal,
                    strike_ordinal,
                    item,
                )
            )
    return tuple(result)


def _damage_component(
    source_text: str,
    *,
    authority: SourceAuthorityAdapter,
    start: int,
    selection_path: tuple[
        RawMemberStep | RawIndexStep,
        ...,
    ],
    source: VerifiedSourceSelection,
) -> dict[str, Any] | None:
    match = _DAMAGE_COMPONENT_RE.fullmatch(source_text)
    if match is None:
        return None
    count = _bounded_positive_decimal(
        match.group("count"),
        maximum=MAX_DAMAGE_DICE,
    )
    sides = _bounded_positive_decimal(
        match.group("sides"),
        maximum=MAX_DAMAGE_DIE_SIDES,
    )
    modifier_text = match.group("modifier")
    modifier = (
        parse_decimal_integer(modifier_text)
        if modifier_text is not None
        else 0
    )
    damage_type = _utf8_bound(
        match.group("damage_type"),
        MAX_DAMAGE_TYPE_BYTES,
        "Trample Strike damage type",
    )
    if (
        count is None
        or sides is None
        or modifier is None
        or abs(modifier) > MAX_DAMAGE_MODIFIER_ABS
        or not damage_type
        or damage_type != damage_type.strip()
    ):
        raise EngineInputError(
            "Trample listed Strike damage number is out of bounds"
        )
    span = TextSpan(start, start + len(source_text))
    selection = source.carrier.select(selection_path, span=span)
    authority.validate_selection(selection)
    return {
        "sourceText": source_text,
        "dice": {
            "count": count,
            "sides": sides,
        },
        "modifier": modifier,
        "type": damage_type.casefold(),
        "source": selection.receipt.as_serialized(),
    }


def _damage_boundary(
    source_text: str,
    *,
    authority: SourceAuthorityAdapter,
    selection_path: tuple[
        RawMemberStep | RawIndexStep,
        ...,
    ],
    source: VerifiedSourceSelection,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    _utf8_bound(
        source_text,
        MAX_SOURCE_TEXT_BYTES,
        "Trample listed Strike Damage",
    )
    separator = " plus "
    first_separator = source_text.find(separator)
    if first_separator < 0:
        first_text = source_text
        tail_text = None
        tail_start = None
    else:
        if source_text.find(
            separator,
            first_separator + len(separator),
        ) >= 0:
            raise EngineInputError(
                "Trample listed Strike Damage has multiple unreviewed tails"
            )
        first_text = source_text[:first_separator]
        tail_start = first_separator + len(separator)
        tail_text = source_text[tail_start:]

    first = _damage_component(
        first_text,
        authority=authority,
        start=0,
        selection_path=selection_path,
        source=source,
    )
    if first is None:
        raise EngineInputError(
            "Trample listed Strike Damage is not understood"
        )
    components = [first]
    if tail_text is None:
        return components, None
    if not tail_text:
        raise EngineInputError(
            "Trample listed Strike Damage tail is empty"
        )
    second = _damage_component(
        tail_text,
        authority=authority,
        start=tail_start,
        selection_path=selection_path,
        source=source,
    )
    if second is not None:
        components.append(second)
        return components, None
    if _NUMERIC_DAMAGE_PREFIX_RE.match(tail_text):
        raise EngineInputError(
            "Trample listed Strike secondary damage is malformed"
        )
    suffix = source.carrier.select(
        selection_path,
        span=TextSpan(tail_start, len(source_text)),
    )
    authority.validate_selection(suffix)
    return (
        components,
        {
            "kind": "non-damage-source-tail",
            "sourceText": tail_text,
            "source": suffix.receipt.as_serialized(),
        },
    )


def _derive_linked(
    value: CompiledTrample,
    ability: dict[str, Any],
) -> tuple[
    VerifiedSourceSelection,
    VerifiedSourceSelection,
    dict[str, Any],
]:
    mechanic = ability["mechanic"]
    listed_name = mechanic["listedStrikeSourceName"]
    listed_id = mechanic["listedStrikeId"]

    matches = [
        item
        for item in _complete_strike_index(value)
        if item[1] == listed_name
    ]
    if not matches:
        raise EngineInputError(
            f"Trample listed Strike is missing: {listed_name}"
        )
    if len(matches) != 1:
        raise EngineInputError(
            f"Trample listed Strike is ambiguous: {listed_name}"
        )
    mode, strike_name, outer_ordinal, strike_ordinal, strike = matches[0]
    if mode != "melee":
        raise EngineInputError(
            f"Trample listed Strike is not Melee: {listed_name}"
        )
    if _strike_id(strike_name) != listed_id:
        raise EngineInputError(
            "Trample listed Strike identity is stale"
        )

    damage_members = [
        (member_ordinal, member)
        for member_ordinal, member in enumerate(strike.members)
        if member.key == "Damage"
    ]
    if len(damage_members) != 1:
        raise EngineInputError(
            "Trample listed Strike requires one exact Damage carrier"
        )
    damage_ordinal, damage_member = damage_members[0]
    if type(damage_member.value) is not str:
        raise EngineInputError(
            "Trample listed Strike Damage carrier must be exact text"
        )

    outer_key = "Melee"
    strike_path = (
        RawMemberStep(outer_key, outer_ordinal),
        RawIndexStep(strike_ordinal),
    )
    damage_path = (
        *strike_path,
        RawMemberStep("Damage", damage_ordinal),
    )
    strike_selection = value._source.carrier.select(strike_path)
    damage_selection = value._source.carrier.select(damage_path)
    value._authority.validate_selection(strike_selection)
    value._authority.validate_selection(damage_selection)
    components, excluded_tail = _damage_boundary(
        damage_member.value,
        authority=value._authority,
        selection_path=damage_path,
        source=value._source,
    )

    mechanic["listedStrike"] = {
        "id": listed_id,
        "name": listed_name,
        "kind": "melee",
        "makesStrike": False,
        "strikeSource": strike_selection.receipt.as_serialized(),
        "damageCarrierSource": damage_selection.receipt.as_serialized(),
        "damageSourceText": damage_member.value,
        "damageComponents": components,
        "damageQualifiers": [],
        "excludedNonDamageTail": excluded_tail,
    }
    return strike_selection, damage_selection, ability


def _validated_linked(
    value: object,
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
    contract_fingerprint: str,
) -> tuple[LinkedTrample, dict[str, Any]]:
    if type(value) is not LinkedTrample:
        raise TypeError(
            "Trample projection requires an exact LinkedTrample"
        )
    try:
        compiled = value._compiled
        strike = value._strike
        damage = value._damage
        ability = value._ability
    except AttributeError as failure:
        raise EngineInputError(
            "Trample linked capability is incomplete"
        ) from failure
    if (
        type(compiled) is not CompiledTrample
        or type(strike) is not VerifiedSourceSelection
        or type(damage) is not VerifiedSourceSelection
    ):
        raise EngineInputError("Trample linked capability is forged")
    compiled, base_ability = _validated_compiled(
        compiled,
        requirements,
        deferrals,
        contract_fingerprint,
    )
    compiled._authority.validate_selection(strike)
    compiled._authority.validate_selection(damage)
    expected_strike, expected_damage, expected = _derive_linked(
        compiled,
        base_ability,
    )
    if (
        strike.receipt != expected_strike.receipt
        or damage.receipt != expected_damage.receipt
        or _thaw_json(ability) != expected
    ):
        raise EngineInputError("Trample linked capability is stale")
    return value, expected


def _link_trample_strike_impl(
    compiled: object,
    requirements: ReviewedRequirements,
    deferrals: tuple[RuntimeDeferral, ...],
    contract_fingerprint: str,
) -> LinkedTrample:
    """Link Trample to its one exact local Melee Strike and Damage member."""

    value, ability = _validated_compiled(
        compiled,
        requirements,
        deferrals,
        contract_fingerprint,
    )
    strike_selection, damage_selection, linked_ability = _derive_linked(
        value,
        ability,
    )
    result = object.__new__(LinkedTrample)
    object.__setattr__(result, "_compiled", value)
    object.__setattr__(result, "_strike", strike_selection)
    object.__setattr__(result, "_damage", damage_selection)
    object.__setattr__(
        result,
        "_ability",
        _freeze_json(linked_ability),
    )
    return result


def _copy_requirement(
    requirement: RuleRequirement,
) -> RuleRequirement:
    return RuleRequirement(
        rule_id=requirement.rule_id,
        source_id=requirement.source_id,
        locator=requirement.locator,
        carrier_path=requirement.carrier_path,
        selection_path=requirement.selection_path,
        span=requirement.span,
        expected_block_sha256=requirement.expected_block_sha256,
        expected_member_sha256=requirement.expected_member_sha256,
        expected_value_sha256=requirement.expected_value_sha256,
        expected_selection_sha256=(
            requirement.expected_selection_sha256
        ),
    )


def _bind_reviewed_contract():
    # Public module bindings are descriptive API, not trust anchors.  The
    # compiler and both projection surfaces close over private exact copies
    # plus their fingerprint so rebinding or mutating the public view cannot
    # shrink the provider proof or its typed runtime deferrals.
    requirements: ReviewedRequirements = tuple(
        (rule_id, _copy_requirement(requirement))
        for rule_id, requirement in TRAMPLE_RULE_REQUIREMENTS.items()
    )
    deferrals = tuple(
        RuntimeDeferral(
            item.kind,
            tuple(item.provider_rule_ids),
        )
        for item in _RUNTIME_DEFERRALS
    )
    fingerprint = _contract_fingerprint(requirements, deferrals)
    _require_contract(requirements, deferrals, fingerprint)

    compile_impl = _compile_trample_impl
    link_impl = _link_trample_strike_impl
    validate_compiled = _validated_compiled
    validate_linked = _validated_linked

    def compile_trample(
        authority: object,
        source: object,
        rule_receipts: object,
        /,
    ) -> CompiledTrample | None:
        """Compile one adapter-revalidated Core MC1 Trample member."""

        return compile_impl(
            authority,
            source,
            rule_receipts,
            requirements,
            deferrals,
            fingerprint,
        )

    def link_trample_strike(
        compiled: object,
        /,
    ) -> LinkedTrample:
        """Link one revalidated Trample to its complete local Strike view."""

        return link_impl(
            compiled,
            requirements,
            deferrals,
            fingerprint,
        )

    def compiled_projection(
        value: CompiledTrample,
    ) -> dict[str, Any]:
        _compiled, projection = validate_compiled(
            value,
            requirements,
            deferrals,
            fingerprint,
        )
        return projection

    def linked_projection(
        value: LinkedTrample,
    ) -> dict[str, Any]:
        _linked, projection = validate_linked(
            value,
            requirements,
            deferrals,
            fingerprint,
        )
        return projection

    return (
        compile_trample,
        link_trample_strike,
        compiled_projection,
        linked_projection,
    )


(
    compile_trample,
    link_trample_strike,
    _compiled_projection,
    _linked_projection,
) = _bind_reviewed_contract()
CompiledTrample.as_ability_update = _compiled_projection
LinkedTrample.as_ability_update = _linked_projection


@dataclass(frozen=True, slots=True)
class TrampleRuntimeHost:
    """Narrow encounter-kernel services used by the Trample activity.

    The family owns ordering and continuation data.  The host owns only
    already-implemented kernel operations and the selected-environment fence.
    """

    participant_map: Callable[[dict[str, Any]], dict[str, dict[str, Any]]]
    definition_for: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    land_speed_feet: Callable[[dict[str, Any]], int]
    participant_size_rank: Callable[[dict[str, Any], str], int]
    selected_activity_evidence: Callable[..., dict[str, Any]]
    validate_activity_evidence: Callable[..., None]
    validate_continuation: Callable[..., None]
    begin_activity: Callable[..., None]
    plan_land_stride: Callable[..., dict[str, Any]]
    commit_land_step: Callable[..., dict[str, Any]]
    open_reaction_window: Callable[..., dict[str, Any] | None]
    resolve_reaction_window: Callable[..., dict[str, Any]]
    resolve_reflex_save: Callable[..., dict[str, Any]]
    resolve_shared_damage: Callable[..., list[dict[str, Any]]]
    scale_basic_save_damage: Callable[..., dict[str, Any]]
    preview_damage_defenses: Callable[..., dict[str, Any]]
    apply_damage: Callable[..., dict[str, Any]]
    publish_continuation: Callable[[dict[str, Any], str | None], None]
    begin_resume: Callable[[dict[str, Any], str], None]

    def __post_init__(self) -> None:
        for descriptor in fields(self):
            if not callable(getattr(self, descriptor.name)):
                raise TypeError(
                    f"Trample runtime host {descriptor.name} must be callable"
                )


def _runtime_canonical_sha256(value: object, label: str) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as failure:
        raise EngineInputError(f"{label} is not canonical JSON") from failure
    return hashlib.sha256(encoded).hexdigest()


def _runtime_coordinate(value: object, label: str) -> dict[str, int]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"x", "y"}
        or type(value.get("x")) is not int
        or type(value.get("y")) is not int
    ):
        raise EngineInputError(f"{label} is invalid")
    return {"x": int(value["x"]), "y": int(value["y"])}


def _runtime_window(
    value: object,
    expected_kind: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if (
        not isinstance(value, Mapping)
        or set(value) != {"kind", "token"}
        or value.get("kind") != expected_kind
        or type(value.get("token")) is not str
        or not value["token"]
    ):
        raise EngineInputError("Trample reaction window is invalid")
    return deepcopy(dict(value))


def _runtime_evidence(
    value: object,
    *,
    actor_id: str,
    source_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    expected = {
        "activityId",
        "actorId",
        "abilityId",
        "mechanicType",
        "runtimePackageId",
        "runtimeCapabilityId",
        "environmentDigest",
        "sourceReceipt",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value.get("actorId") != actor_id
        or value.get("mechanicType") != MECHANIC_TYPE
        or value.get("runtimePackageId") != RUNTIME_PACKAGE_ID
        or value.get("runtimeCapabilityId") != RUNTIME_CAPABILITY_ID
        or value.get("sourceReceipt") != source_receipt
        or any(
            type(value.get(key)) is not str or not value[key]
            for key in ("activityId", "abilityId")
        )
        or type(value.get("environmentDigest")) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", value["environmentDigest"])
    ):
        raise EngineInputError(
            "Trample selected runtime evidence is invalid"
        )
    return deepcopy(dict(value))


def _runtime_plan(
    value: object,
    *,
    requested_path: list[dict[str, int]],
    maximum_distance: int,
    maximum_size_rank: int,
    state: dict[str, Any],
    actor_id: str,
    host: TrampleRuntimeHost,
) -> dict[str, Any]:
    expected = {
        "distanceFeet",
        "path",
        "steps",
        "endpoint",
        "endpointOccupiedSquares",
        "endpointLegalNonoverlap",
        "difficultTerrain",
        "hazardousTerrain",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise EngineInputError("Trample land-Stride plan is invalid")
    distance = value.get("distanceFeet")
    path = value.get("path")
    steps = value.get("steps")
    if (
        type(distance) is not int
        or not 0 < distance <= maximum_distance
        or not isinstance(path, list)
        or not isinstance(steps, list)
        or not path
        or len(path) > MAX_RUNTIME_PATH_STEPS
        or len(steps) != len(path)
        or value.get("endpointLegalNonoverlap") is not True
    ):
        raise EngineInputError("Trample land-Stride plan is invalid")
    normalized_path = [
        _runtime_coordinate(item, "Trample planned path coordinate")
        for item in path
    ]
    if normalized_path != requested_path:
        raise EngineInputError("Trample planned path changed the request")
    if value.get("difficultTerrain") is not False:
        raise EngineInputError(
            "Trample difficult terrain is a completeness deferral"
        )
    if value.get("hazardousTerrain") is not False:
        raise EngineInputError(
            "Trample hazardous terrain is a completeness deferral"
        )
    normalized_steps = []
    participants = host.participant_map(state)
    if not isinstance(participants, dict) or actor_id not in participants:
        raise EngineInputError("Trample participant index is invalid")
    for ordinal, (step, position) in enumerate(
        zip(steps, normalized_path, strict=True)
    ):
        if (
            not isinstance(step, Mapping)
            or set(step)
            != {"position", "occupiedSquares", "enteredParticipantIds"}
            or _runtime_coordinate(
                step.get("position"),
                "Trample planned step position",
            )
            != position
            or not isinstance(step.get("occupiedSquares"), list)
            or not step["occupiedSquares"]
            or len(step["occupiedSquares"]) > MAX_RUNTIME_FOOTPRINT_SQUARES
            or not isinstance(step.get("enteredParticipantIds"), list)
        ):
            raise EngineInputError(
                f"Trample planned step {ordinal} is invalid"
            )
        occupied = [
            _runtime_coordinate(item, "Trample occupied square")
            for item in step["occupiedSquares"]
        ]
        entered = step["enteredParticipantIds"]
        if (
            len(entered) != len(set(entered))
            or len(entered) > MAX_RUNTIME_TARGETS
            or any(
                type(target_id) is not str
                or not target_id
                or target_id == actor_id
                or target_id not in participants
                for target_id in entered
            )
        ):
            raise EngineInputError("Trample planned target entry is invalid")
        for target_id in entered:
            rank = host.participant_size_rank(state, target_id)
            if type(rank) is not int or rank < 0:
                raise EngineInputError("Trample target size rank is invalid")
            if rank > maximum_size_rank:
                raise EngineInputError(
                    "Trample path enters a creature larger than its limit"
                )
        normalized_steps.append(
            {
                "position": position,
                "occupiedSquares": occupied,
                "enteredParticipantIds": list(entered),
            }
        )
    endpoint = _runtime_coordinate(value.get("endpoint"), "Trample endpoint")
    endpoint_occupied = [
        _runtime_coordinate(item, "Trample endpoint occupied square")
        for item in value["endpointOccupiedSquares"]
    ] if (
        isinstance(value.get("endpointOccupiedSquares"), list)
        and len(value["endpointOccupiedSquares"])
        <= MAX_RUNTIME_FOOTPRINT_SQUARES
    ) else None
    if (
        endpoint != normalized_path[-1]
        or not endpoint_occupied
        or endpoint_occupied != normalized_steps[-1]["occupiedSquares"]
    ):
        raise EngineInputError("Trample endpoint proof is invalid")
    return {
        "distanceFeet": distance,
        "path": normalized_path,
        "steps": normalized_steps,
        "endpoint": endpoint,
        "endpointOccupiedSquares": endpoint_occupied,
        "endpointLegalNonoverlap": True,
        "difficultTerrain": False,
        "hazardousTerrain": False,
    }


def _runtime_save_degree(total: int, dc: int, roll: int) -> str:
    if total >= dc + 10:
        index = 3
    elif total >= dc:
        index = 2
    elif total <= dc - 10:
        index = 0
    else:
        index = 1
    if roll == 20:
        index = min(3, index + 1)
    elif roll == 1:
        index = max(0, index - 1)
    return (
        "critical-failure",
        "failure",
        "success",
        "critical-success",
    )[index]


def _runtime_save(value: object, *, target_id: str, dc: int) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or value.get("type") != "reflex"
        or value.get("targetParticipantId") != target_id
        or value.get("dc") != dc
        or value.get("basic") is not True
        or value.get("degree")
        not in {
            "critical-success",
            "success",
            "failure",
            "critical-failure",
        }
        or type(value.get("roll")) is not int
        or not 1 <= value["roll"] <= 20
        or type(value.get("total")) is not int
        or value.get("degree")
        != _runtime_save_degree(value["total"], dc, value["roll"])
    ):
        raise EngineInputError("Trample Reflex save result is invalid")
    return deepcopy(dict(value))


def _seal_runtime_continuation(body: dict[str, Any]) -> dict[str, Any]:
    if "sha256" in body:
        raise EngineInputError("Trample continuation body is invalid")
    sealed = deepcopy(body)
    sealed["sha256"] = _runtime_canonical_sha256(
        body,
        "Trample continuation",
    )
    return sealed


def _open_runtime_continuation(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or type(value.get("sha256")) is not str:
        raise EngineInputError("Trample continuation is invalid")
    body = deepcopy(dict(value))
    claimed = body.pop("sha256")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", claimed)
        or _runtime_canonical_sha256(body, "Trample continuation") != claimed
    ):
        raise EngineInputError("Trample continuation was tampered with")
    required = {
        "schema",
        "kind",
        "mechanicType",
        "activityId",
        "actorId",
        "abilityId",
        "stage",
        "stageOrdinal",
        "plan",
        "movementCursor",
        "enteredTargetIds",
        "targetCursor",
        "sharedDamage",
        "targetResults",
        "currentTargetId",
        "currentSavingThrow",
        "currentDamage",
        "currentTargetResult",
        "pendingWindow",
        "action",
        "hostEvidence",
        "completenessDeferrals",
    }
    entered = body.get("enteredTargetIds")
    results = body.get("targetResults")
    plan = body.get("plan")
    if (
        set(body) != required
        or body.get("schema") != 1
        or body.get("kind") != "pf2er-trample-activity-continuation"
        or body.get("mechanicType") != MECHANIC_TYPE
        or body.get("completenessDeferrals")
        != list(TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS)
        or type(body.get("stageOrdinal")) is not int
        or body["stageOrdinal"] < 0
        or type(body.get("movementCursor")) is not int
        or body["movementCursor"] < 0
        or type(body.get("targetCursor")) is not int
        or body["targetCursor"] < 0
        or not isinstance(entered, list)
        or any(type(target_id) is not str or not target_id for target_id in entered)
        or len(entered) != len(set(entered))
        or not isinstance(results, list)
        or any(
            not isinstance(result, Mapping)
            or type(result.get("targetParticipantId")) is not str
            or not result["targetParticipantId"]
            for result in results
        )
        or len(
            {
                result.get("targetParticipantId")
                for result in results
            }
        ) != len(results)
        or not isinstance(plan, Mapping)
        or not isinstance(plan.get("steps"), list)
        or body["movementCursor"] > len(plan["steps"])
        or body["targetCursor"] > len(entered)
        or body["targetCursor"] != len(results)
        or [result.get("targetParticipantId") for result in results]
        != entered[: body["targetCursor"]]
    ):
        raise EngineInputError("Trample continuation shape is invalid")
    stage = body["stage"]
    current_target = body["currentTargetId"]
    pending = body["pendingWindow"]
    expected_window = {
        "movement-reaction": "movement",
        "save-reaction": "save",
        "damage-reaction": "damage",
        "zero-hp-reaction": "zero-hp",
    }.get(stage)
    if expected_window is None:
        raise EngineInputError("Trample continuation order is invalid")
    if _runtime_window(pending, expected_window) is None:
        raise EngineInputError("Trample continuation has no reaction window")
    if stage == "movement-reaction":
        if (
            body["movementCursor"] >= len(plan["steps"])
            or current_target is not None
            or body["currentSavingThrow"] is not None
            or body["currentDamage"] is not None
            or body["currentTargetResult"] is not None
        ):
            raise EngineInputError("Trample continuation order is invalid")
    else:
        if (
            body["movementCursor"] != len(plan["steps"])
            or body["targetCursor"] >= len(entered)
            or current_target != entered[body["targetCursor"]]
            or body["currentSavingThrow"] is None
        ):
            raise EngineInputError("Trample continuation order is invalid")
        if stage == "save-reaction" and (
            body["currentDamage"] is not None
            or body["currentTargetResult"] is not None
        ):
            raise EngineInputError("Trample continuation order is invalid")
        if stage == "damage-reaction" and (
            body["currentDamage"] is None
            or body["currentTargetResult"] is not None
        ):
            raise EngineInputError("Trample continuation order is invalid")
        if stage == "zero-hp-reaction" and body["currentTargetResult"] is None:
            raise EngineInputError("Trample continuation order is invalid")
    return body


def _suspend_trample(
    state: dict[str, Any],
    body: dict[str, Any],
    host: TrampleRuntimeHost,
) -> dict[str, Any]:
    sealed = _seal_runtime_continuation(body)
    host.publish_continuation(state, sealed["sha256"])
    return {
        "schema": 1,
        "status": "suspended",
        "event": None,
        "continuation": sealed,
    }


def _complete_trample(
    state: dict[str, Any],
    body: dict[str, Any],
    host: TrampleRuntimeHost,
) -> dict[str, Any]:
    host.publish_continuation(state, None)
    return {
        "schema": 1,
        "status": "complete",
        "continuation": None,
        "event": {
            "type": "trample",
            "actorId": body["actorId"],
            "abilityId": body["abilityId"],
            "actionCost": 3,
            "movement": {
                "type": "Stride",
                "mode": "land",
                "speedMultiplier": 2,
                "distanceFeet": body["plan"]["distanceFeet"],
                "path": deepcopy(body["plan"]["path"]),
                "endpoint": deepcopy(body["plan"]["endpoint"]),
                "triggersReactions": True,
            },
            "targetParticipantIds": list(body["enteredTargetIds"]),
            "sharedDamage": deepcopy(body["sharedDamage"]),
            "targetResults": deepcopy(body["targetResults"]),
            "multipleAttackPenalty": {"read": False, "advanced": False},
            "hostEvidence": deepcopy(body["hostEvidence"]),
            "completenessDeferrals": list(
                TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS
            ),
        },
    }


def _advance_trample(
    state: dict[str, Any],
    body: dict[str, Any],
    host: TrampleRuntimeHost,
) -> dict[str, Any]:
    plan = body["plan"]
    action = body["action"]
    actor_id = body["actorId"]
    while body["movementCursor"] < len(plan["steps"]):
        cursor = body["movementCursor"]
        step = plan["steps"][cursor]
        window = _runtime_window(
            host.open_reaction_window(
                state,
                "movement",
                {
                    "activityId": body["activityId"],
                    "actorId": actor_id,
                    "stepOrdinal": cursor,
                    "step": deepcopy(step),
                },
            ),
            "movement",
        )
        if window is not None:
            body["stage"] = "movement-reaction"
            body["pendingWindow"] = window
            body["stageOrdinal"] += 1
            return _suspend_trample(state, body, host)
        host.commit_land_step(state, actor_id, deepcopy(step))
        body["movementCursor"] += 1
        for target_id in step["enteredParticipantIds"]:
            if target_id not in body["enteredTargetIds"]:
                if len(body["enteredTargetIds"]) >= MAX_RUNTIME_TARGETS:
                    raise EngineInputError("Trample target bound exceeded")
                body["enteredTargetIds"].append(target_id)

    if body["sharedDamage"] is None:
        if set(action["savingThrowRolls"]) != set(body["enteredTargetIds"]):
            raise EngineInputError(
                "Trample Reflex rolls must match first-entry targets exactly"
            )
        shared = host.resolve_shared_damage(
            deepcopy(action["damageComponents"]),
            deepcopy(action["damageRolls"]),
        )
        if not isinstance(shared, list) or not shared or any(
            not isinstance(component, Mapping)
            or type(component.get("total")) is not int
            or component["total"] < 0
            or type(component.get("type")) is not str
            or not component["type"]
            for component in shared
        ) or len(shared) != len(action["damageComponents"]) or [
            component["type"] for component in shared
        ] != [
            component["type"] for component in action["damageComponents"]
        ]:
            raise EngineInputError("Trample shared damage result is invalid")
        body["sharedDamage"] = deepcopy(shared)

    while body["targetCursor"] < len(body["enteredTargetIds"]):
        target_id = body["enteredTargetIds"][body["targetCursor"]]
        if body["currentSavingThrow"] is None:
            roll = action["savingThrowRolls"].get(target_id)
            if type(roll) is not int or not 1 <= roll <= 20:
                raise EngineInputError(
                    f"Trample requires one Reflex d20 for {target_id}"
                )
            save = _runtime_save(
                host.resolve_reflex_save(
                    state,
                    target_id,
                    action["savingThrowDC"],
                    roll,
                ),
                target_id=target_id,
                dc=action["savingThrowDC"],
            )
            body["currentTargetId"] = target_id
            body["currentSavingThrow"] = save
            window = _runtime_window(
                host.open_reaction_window(
                    state,
                    "save",
                    {
                        "activityId": body["activityId"],
                        "actorId": actor_id,
                        "targetParticipantId": target_id,
                        "savingThrow": deepcopy(save),
                    },
                ),
                "save",
            )
            if window is not None:
                body["stage"] = "save-reaction"
                body["pendingWindow"] = window
                body["stageOrdinal"] += 1
                return _suspend_trample(state, body, host)

        if body["currentDamage"] is None:
            damage = host.scale_basic_save_damage(
                deepcopy(body["sharedDamage"]),
                body["currentSavingThrow"]["degree"],
            )
            if (
                not isinstance(damage, Mapping)
                or not isinstance(damage.get("components"), list)
                or not damage["components"]
                or any(
                    not isinstance(component, Mapping)
                    or type(component.get("total")) is not int
                    or component["total"] < 0
                    or type(component.get("type")) is not str
                    or not component["type"]
                    for component in damage["components"]
                )
                or type(damage.get("total")) is not int
                or damage["total"] < 0
                or damage["total"]
                != sum(
                    component["total"]
                    for component in damage["components"]
                )
            ):
                raise EngineInputError(
                    "Trample basic-save damage result is invalid"
                )
            preview = host.preview_damage_defenses(
                state,
                target_id,
                deepcopy(dict(damage)),
            )
            if (
                not isinstance(preview, Mapping)
                or type(preview.get("appliedTotal")) is not int
                or preview["appliedTotal"] < 0
            ):
                raise EngineInputError("Trample damage preview is invalid")
            body["currentDamage"] = {
                "scaled": deepcopy(dict(damage)),
                "preview": deepcopy(dict(preview)),
            }
            window = _runtime_window(
                host.open_reaction_window(
                    state,
                    "damage",
                    {
                        "activityId": body["activityId"],
                        "actorId": actor_id,
                        "targetParticipantId": target_id,
                        "damage": deepcopy(body["currentDamage"]),
                    },
                ),
                "damage",
            )
            if window is not None:
                if len(body["enteredTargetIds"]) > 1:
                    raise EngineInputError(
                        "Trample generic multi-target damage reactions are a "
                        "completeness deferral"
                    )
                body["stage"] = "damage-reaction"
                body["pendingWindow"] = window
                body["stageOrdinal"] += 1
                return _suspend_trample(state, body, host)

        if body["currentTargetResult"] is None:
            applied = host.apply_damage(
                state,
                target_id,
                deepcopy(body["currentDamage"]["scaled"]),
            )
            if (
                not isinstance(applied, Mapping)
                or applied.get("targetParticipantId") != target_id
                or type(applied.get("appliedTotal")) is not int
                or applied["appliedTotal"] < 0
                or type(applied.get("zeroHpTriggered")) is not bool
                or applied["appliedTotal"]
                != body["currentDamage"]["preview"]["appliedTotal"]
            ):
                raise EngineInputError("Trample applied damage is invalid")
            body["currentTargetResult"] = {
                "targetParticipantId": target_id,
                "savingThrow": deepcopy(body["currentSavingThrow"]),
                "damage": deepcopy(dict(applied)),
            }
            if applied["zeroHpTriggered"]:
                window = _runtime_window(
                    host.open_reaction_window(
                        state,
                        "zero-hp",
                        {
                            "activityId": body["activityId"],
                            "actorId": actor_id,
                            "targetParticipantId": target_id,
                            "damage": deepcopy(dict(applied)),
                        },
                    ),
                    "zero-hp",
                )
                if window is not None:
                    body["stage"] = "zero-hp-reaction"
                    body["pendingWindow"] = window
                    body["stageOrdinal"] += 1
                    return _suspend_trample(state, body, host)

        body["targetResults"].append(body["currentTargetResult"])
        body["targetCursor"] += 1
        body["currentTargetId"] = None
        body["currentSavingThrow"] = None
        body["currentDamage"] = None
        body["currentTargetResult"] = None

    body["stage"] = "complete"
    body["pendingWindow"] = None
    return _complete_trample(state, body, host)


def start_trample(
    linked: object,
    state: dict[str, Any],
    actor_id: str,
    action: Mapping[str, Any],
    host: TrampleRuntimeHost,
) -> dict[str, Any]:
    """Start one source-linked simple-map Trample activity."""

    if type(host) is not TrampleRuntimeHost:
        raise TypeError("Trample runtime requires an exact TrampleRuntimeHost")
    if type(linked) is not LinkedTrample:
        raise TypeError("Trample runtime requires an exact LinkedTrample")
    ability = linked.as_ability_update()
    mechanic = ability["mechanic"]
    expected_action = {
        "type",
        "abilityId",
        "path",
        "savingThrowRolls",
        "damageRolls",
    }
    if (
        not isinstance(state, dict)
        or type(actor_id) is not str
        or not actor_id
        or not isinstance(action, Mapping)
        or set(action) != expected_action
        or action.get("type") != "Trample"
        or type(action.get("abilityId")) is not str
        or not action["abilityId"]
        or not isinstance(action.get("path"), list)
        or not action["path"]
        or not isinstance(action.get("savingThrowRolls"), Mapping)
        or not isinstance(action.get("damageRolls"), list)
    ):
        raise EngineInputError("Trample action input is invalid")
    requested_path = [
        _runtime_coordinate(item, "Trample requested path coordinate")
        for item in action["path"]
    ]
    participants = host.participant_map(state)
    actor = participants.get(actor_id) if isinstance(participants, dict) else None
    if not isinstance(actor, dict):
        raise EngineInputError("Trample actor is missing")
    definition = host.definition_for(state, actor)
    speed = host.land_speed_feet(definition)
    if type(speed) is not int or speed <= 0:
        raise EngineInputError("Trample actor land Speed is invalid")
    evidence = _runtime_evidence(
        host.selected_activity_evidence(
            state,
            actor_id,
            action["abilityId"],
            deepcopy(ability),
        ),
        actor_id=actor_id,
        source_receipt=mechanic["source"]["receipt"],
    )
    if evidence["abilityId"] != action["abilityId"]:
        raise EngineInputError("Trample selected ability changed")
    host.validate_activity_evidence(state, deepcopy(evidence))
    plan = _runtime_plan(
        host.plan_land_stride(
            state,
            actor_id,
            deepcopy(requested_path),
            speed * 2,
            mechanic["targeting"]["maximumSizeRank"],
        ),
        requested_path=requested_path,
        maximum_distance=speed * 2,
        maximum_size_rank=mechanic["targeting"]["maximumSizeRank"],
        state=state,
        actor_id=actor_id,
        host=host,
    )
    normalized_action = {
        "type": "Trample",
        "abilityId": action["abilityId"],
        "path": requested_path,
        "savingThrowRolls": deepcopy(dict(action["savingThrowRolls"])),
        "damageRolls": deepcopy(action["damageRolls"]),
        "savingThrowDC": mechanic["savingThrow"]["dc"],
        "damageComponents": deepcopy(
            mechanic["listedStrike"]["damageComponents"]
        ),
    }
    host.begin_activity(
        state,
        actor_id,
        3,
        deepcopy(evidence),
    )
    body = {
        "schema": 1,
        "kind": "pf2er-trample-activity-continuation",
        "mechanicType": MECHANIC_TYPE,
        "activityId": evidence["activityId"],
        "actorId": actor_id,
        "abilityId": action["abilityId"],
        "stage": "movement",
        "stageOrdinal": 0,
        "plan": plan,
        "movementCursor": 0,
        "enteredTargetIds": [],
        "targetCursor": 0,
        "sharedDamage": None,
        "targetResults": [],
        "currentTargetId": None,
        "currentSavingThrow": None,
        "currentDamage": None,
        "currentTargetResult": None,
        "pendingWindow": None,
        "action": normalized_action,
        "hostEvidence": evidence,
        "completenessDeferrals": list(
            TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS
        ),
    }
    return _advance_trample(state, body, host)


def resume_trample(
    state: dict[str, Any],
    continuation: Mapping[str, Any],
    decision: Mapping[str, Any],
    host: TrampleRuntimeHost,
) -> dict[str, Any]:
    """Resume exactly one sealed Trample reaction window."""

    if type(host) is not TrampleRuntimeHost:
        raise TypeError("Trample runtime requires an exact TrampleRuntimeHost")
    body = _open_runtime_continuation(continuation)
    digest = continuation["sha256"]
    stage = body["stage"]
    expected_kind = {
        "movement-reaction": "movement",
        "save-reaction": "save",
        "damage-reaction": "damage",
        "zero-hp-reaction": "zero-hp",
    }.get(stage)
    if expected_kind is None:
        raise EngineInputError("Trample continuation order is invalid")
    window = _runtime_window(body["pendingWindow"], expected_kind)
    if window is None:
        raise EngineInputError("Trample continuation has no reaction window")
    host.validate_activity_evidence(
        state,
        deepcopy(body["hostEvidence"]),
    )
    host.validate_continuation(state, deepcopy(body))
    outcome = host.resolve_reaction_window(
        state,
        expected_kind,
        deepcopy(window),
        deepcopy(dict(decision)),
    )
    if not isinstance(outcome, Mapping):
        raise EngineInputError("Trample reaction outcome is invalid")
    body["pendingWindow"] = None
    if expected_kind == "movement":
        if dict(outcome) != {"completed": True}:
            raise EngineInputError("Trample movement reaction is unresolved")
        host.begin_resume(state, digest)
        step = body["plan"]["steps"][body["movementCursor"]]
        host.commit_land_step(state, body["actorId"], deepcopy(step))
        body["movementCursor"] += 1
        for target_id in step["enteredParticipantIds"]:
            if target_id not in body["enteredTargetIds"]:
                body["enteredTargetIds"].append(target_id)
    elif expected_kind == "save":
        if set(outcome) != {"savingThrow"}:
            raise EngineInputError("Trample save reaction is unresolved")
        revised_save = _runtime_save(
            outcome["savingThrow"],
            target_id=body["currentTargetId"],
            dc=body["action"]["savingThrowDC"],
        )
        original_save = body["currentSavingThrow"]
        if (
            revised_save["total"] - revised_save["roll"]
            != original_save["total"] - original_save["roll"]
            or revised_save["roll"] < original_save["roll"]
        ):
            raise EngineInputError("Trample save reaction result is impossible")
        host.begin_resume(state, digest)
        body["currentSavingThrow"] = revised_save
    elif expected_kind == "damage":
        if dict(outcome) != {"completed": True}:
            raise EngineInputError("Trample damage reaction is unresolved")
        preview = host.preview_damage_defenses(
            state,
            body["currentTargetId"],
            deepcopy(body["currentDamage"]["scaled"]),
        )
        if (
            not isinstance(preview, Mapping)
            or type(preview.get("appliedTotal")) is not int
            or preview["appliedTotal"] < 0
        ):
            raise EngineInputError("Trample damage preview is invalid")
        host.begin_resume(state, digest)
        body["currentDamage"]["preview"] = deepcopy(dict(preview))
    else:
        if dict(outcome) != {"completed": True}:
            raise EngineInputError("Trample zero-HP reaction is unresolved")
        host.begin_resume(state, digest)
    body["stage"] = "movement" if expected_kind == "movement" else "targets"
    return _advance_trample(state, body, host)


_COMPOUND_SCHEMA = 1
_COMPOUND_KIND = "pf2er-trample-compound-activity"
_COMPOUND_STAGES = frozenset({"damage-pool", "movement", "targets"})
_CARDINAL_DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1))


def _compound_participant_map(
    state: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    participants = state.get("participants")
    if not isinstance(participants, list):
        raise ValueError("Trample participants are invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for participant in participants:
        participant_id = (
            participant.get("id") if isinstance(participant, Mapping) else None
        )
        if (
            not isinstance(participant_id, str)
            or not participant_id
            or participant_id in result
        ):
            raise ValueError("Trample participant identity is invalid")
        result[participant_id] = participant
    return result


def _compound_definition(
    state: Mapping[str, Any],
    participant: Mapping[str, Any],
) -> Mapping[str, Any]:
    definitions = state.get("definitions")
    definition_id = participant.get("creatureId")
    definition = (
        definitions.get(definition_id)
        if isinstance(definitions, Mapping)
        and isinstance(definition_id, str)
        else None
    )
    if not isinstance(definition, Mapping):
        raise ValueError("Trample participant definition is invalid")
    return definition


def _compound_coordinate(value: object, label: str) -> dict[str, int]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"x", "y"}
        or type(value.get("x")) is not int
        or type(value.get("y")) is not int
    ):
        raise ValueError(f"{label} is invalid")
    return {"x": int(value["x"]), "y": int(value["y"])}


def _compound_mechanic_contract(
    ability: Mapping[str, Any],
) -> dict[str, Any]:
    mechanic = ability.get("mechanic")
    movement = mechanic.get("movement") if isinstance(mechanic, Mapping) else None
    targeting = mechanic.get("targeting") if isinstance(mechanic, Mapping) else None
    saving_throw = (
        mechanic.get("savingThrow") if isinstance(mechanic, Mapping) else None
    )
    listed = mechanic.get("listedStrike") if isinstance(mechanic, Mapping) else None
    multiple_attack_penalty = (
        mechanic.get("multipleAttackPenalty")
        if isinstance(mechanic, Mapping)
        else None
    )
    runtime = mechanic.get("runtime") if isinstance(mechanic, Mapping) else None
    strike_id = listed.get("strikeId") if isinstance(listed, Mapping) else None
    maximum_rank = (
        targeting.get("maximumSizeRank")
        if isinstance(targeting, Mapping)
        else None
    )
    dc = saving_throw.get("dc") if isinstance(saving_throw, Mapping) else None
    deferrals = (
        runtime.get("completenessDeferrals")
        if isinstance(runtime, Mapping)
        else None
    )
    if (
        ability.get("kind") != "activity"
        or ability.get("actionCost") != 3
        or not isinstance(mechanic, Mapping)
        or mechanic.get("type") != MECHANIC_TYPE
        or movement
        != {
            "legalEndpoint": "ordinary-occupiable-nonoverlapping-space",
            "movementMode": "land",
            "speedMultiplier": 2,
            "subordinateAction": "Stride",
            "targetTransit": "listed-size-or-smaller",
        }
        or not isinstance(targeting, Mapping)
        or targeting.get("includesAllies") is not True
        or targeting.get("sameTargetLimit") != 1
        or targeting.get("selection") != "first-space-entry"
        or isinstance(maximum_rank, bool)
        or not isinstance(maximum_rank, int)
        or maximum_rank < 0
        or saving_throw
        != {"type": "reflex", "dc": dc, "basic": True}
        or isinstance(dc, bool)
        or not isinstance(dc, int)
        or dc <= 0
        or mechanic.get("sharedDamageRoll") is not True
        or multiple_attack_penalty != {"changes": False, "reads": False}
        or not isinstance(strike_id, str)
        or not strike_id
        or not isinstance(listed.get("damage"), Mapping)
        or not isinstance(listed["damage"].get("components"), list)
        or not listed["damage"]["components"]
        or deferrals != list(TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS)
    ):
        raise ValueError("Trample ability contract is invalid")
    return {
        "strikeId": strike_id,
        "savingThrowDC": dc,
        "maximumSizeRank": maximum_rank,
        "traits": deepcopy(list(ability.get("traits") or [])),
        "completenessDeferrals": list(TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS),
    }


def _compound_size_rank(
    state: Mapping[str, Any],
    participant: Mapping[str, Any],
) -> int:
    space = _compound_definition(state, participant).get("space")
    rank = space.get("sizeRank") if isinstance(space, Mapping) else None
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
        raise ValueError("Trample participant size is invalid")
    return rank


def _compound_map_has_deferred_terrain(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if (
                isinstance(key, str)
                and ("difficult" in key.casefold() or "hazardous" in key.casefold())
                and child not in (None, False, [], {}, ())
            ):
                return True
            if _compound_map_has_deferred_terrain(child):
                return True
    elif isinstance(value, list):
        return any(_compound_map_has_deferred_terrain(item) for item in value)
    return False


def _compound_route(
    state: Mapping[str, Any],
    actor_id: str,
    maximum_size_rank: int,
) -> dict[str, Any]:
    participants = _compound_participant_map(state)
    actor = participants.get(actor_id)
    if actor is None:
        raise ValueError("Trample actor is missing")
    definition = _compound_definition(state, actor)
    speeds = definition.get("speeds")
    speed = speeds.get("land") if isinstance(speeds, Mapping) else None
    if isinstance(speed, bool) or not isinstance(speed, int) or speed <= 0:
        raise ValueError("Trample requires a positive land Speed")
    maximum_feet = speed * 2
    map_value = state.get("map")
    grid = map_value.get("grid") if isinstance(map_value, Mapping) else None
    width = grid.get("width") if isinstance(grid, Mapping) else None
    height = grid.get("height") if isinstance(grid, Mapping) else None
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width <= 0
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height <= 0
    ):
        raise ValueError("Trample requires a bounded square grid")
    if _compound_map_has_deferred_terrain(map_value):
        raise ValueError(
            "Trample difficult or hazardous terrain is a completeness deferral"
        )
    origin = _compound_coordinate(actor.get("position"), "Trample origin")
    occupied = actor.get("occupiedSquares")
    if not isinstance(occupied, list) or not occupied:
        raise ValueError("Trample actor footprint is invalid")
    offsets = [
        {
            "x": square["x"] - origin["x"],
            "y": square["y"] - origin["y"],
        }
        for square in (
            _compound_coordinate(item, "Trample actor footprint")
            for item in occupied
        )
    ]
    blocked = {
        (square["x"], square["y"])
        for square in (
            _compound_coordinate(item, "Trample blocked square")
            for item in (
                map_value.get("blockedSquares", [])
                if isinstance(map_value, Mapping)
                and isinstance(map_value.get("blockedSquares", []), list)
                else []
            )
        )
    }
    occupant_squares: dict[str, set[tuple[int, int]]] = {}
    for participant_id, participant in participants.items():
        if participant_id == actor_id or participant.get("defeated") is True:
            continue
        raw_squares = participant.get("occupiedSquares")
        if not isinstance(raw_squares, list) or not raw_squares:
            raise ValueError("Trample target footprint is invalid")
        occupant_squares[participant_id] = {
            (square["x"], square["y"])
            for square in (
                _compound_coordinate(item, "Trample target footprint")
                for item in raw_squares
            )
        }
    candidates: list[tuple[int, int, int, list[dict[str, int]], list[str]]] = []
    for direction_ordinal, (delta_x, delta_y) in enumerate(_CARDINAL_DIRECTIONS):
        path: list[dict[str, int]] = []
        entered: set[str] = set()
        route_blocked = False
        for step_ordinal in range(1, maximum_feet // 5 + 1):
            position = {
                "x": origin["x"] + delta_x * step_ordinal,
                "y": origin["y"] + delta_y * step_ordinal,
            }
            footprint = {
                (position["x"] + offset["x"], position["y"] + offset["y"])
                for offset in offsets
            }
            if any(
                x < 0 or y < 0 or x >= width or y >= height or (x, y) in blocked
                for x, y in footprint
            ):
                break
            path.append(position)
            overlapping = sorted(
                participant_id
                for participant_id, squares in occupant_squares.items()
                if footprint.intersection(squares)
            )
            for participant_id in overlapping:
                if _compound_size_rank(state, participants[participant_id]) > maximum_size_rank:
                    route_blocked = True
                    break
                entered.add(participant_id)
            if route_blocked:
                break
            if entered and not overlapping:
                candidates.append(
                    (
                        -len(entered),
                        len(path),
                        direction_ordinal,
                        deepcopy(path),
                        sorted(entered),
                    )
                )
        if route_blocked:
            continue
    if not candidates:
        raise ValueError(
            "Trample has no deterministic clean-map path through an eligible creature"
        )
    _negative_count, _length, _direction, path, target_ids = min(candidates)
    return {
        "path": path,
        "maximumFeet": maximum_feet,
        "transientOccupantIds": target_ids,
    }


def _compound_damage_pool(value: object, strike_id: str) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value)
        != {"kind", "strikeId", "components", "hostTransactionId", "poolDigest"}
        or value.get("kind") != "listed-strike-damage"
        or value.get("strikeId") != strike_id
        or not isinstance(value.get("components"), list)
        or not value["components"]
        or not isinstance(value.get("hostTransactionId"), str)
        or not value["hostTransactionId"]
        or not isinstance(value.get("poolDigest"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["poolDigest"])
    ):
        raise ValueError("Trample listed-Strike damage pool is invalid")
    for component in value["components"]:
        if (
            not isinstance(component, Mapping)
            or set(component) != {"type", "dice", "rolls", "modifier", "total"}
            or not isinstance(component.get("type"), str)
            or not component["type"]
            or not isinstance(component.get("dice"), Mapping)
            or set(component["dice"]) != {"count", "sides"}
            or isinstance(component["dice"].get("count"), bool)
            or not isinstance(component["dice"].get("count"), int)
            or component["dice"]["count"] <= 0
            or isinstance(component["dice"].get("sides"), bool)
            or not isinstance(component["dice"].get("sides"), int)
            or component["dice"]["sides"] <= 0
            or not isinstance(component.get("rolls"), list)
            or len(component["rolls"]) != component["dice"]["count"]
            or any(
                type(roll) is not int or not 1 <= roll <= component["dice"]["sides"]
                for roll in component["rolls"]
            )
            or type(component.get("modifier")) is not int
            or component.get("total") != sum(component["rolls"]) + component["modifier"]
        ):
            raise ValueError("Trample damage pool component is invalid")
    unsigned = {key: deepcopy(item) for key, item in value.items() if key != "poolDigest"}
    expected = hashlib.sha256(
        json.dumps(
            {"domain": "damage-pool", "value": unsigned},
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if value["poolDigest"] != expected:
        raise ValueError("Trample damage pool digest is invalid")
    return deepcopy(dict(value))


def validate_compound_checkpoint(checkpoint: Mapping[str, Any]) -> None:
    """Reject malformed, reordered, or duplicated package-owned state."""

    if not isinstance(checkpoint, Mapping) or set(checkpoint) != {
        "schema",
        "kind",
        "stage",
        "actorId",
        "abilityId",
        "contract",
        "route",
        "damagePool",
        "targetIds",
        "targetCursor",
        "targetResults",
        "movement",
    }:
        raise ValueError("Trample checkpoint shape is invalid")
    contract = checkpoint.get("contract")
    route = checkpoint.get("route")
    target_ids = checkpoint.get("targetIds")
    results = checkpoint.get("targetResults")
    cursor = checkpoint.get("targetCursor")
    stage = checkpoint.get("stage")
    if (
        checkpoint.get("schema") != _COMPOUND_SCHEMA
        or checkpoint.get("kind") != _COMPOUND_KIND
        or stage not in _COMPOUND_STAGES
        or not isinstance(checkpoint.get("actorId"), str)
        or not checkpoint["actorId"]
        or not isinstance(checkpoint.get("abilityId"), str)
        or not checkpoint["abilityId"]
        or not isinstance(contract, Mapping)
        or set(contract)
        != {"strikeId", "savingThrowDC", "maximumSizeRank", "traits", "completenessDeferrals"}
        or not isinstance(route, Mapping)
        or set(route) != {"path", "maximumFeet", "transientOccupantIds"}
        or not isinstance(route.get("path"), list)
        or not route["path"]
        or len(route["path"]) > MAX_RUNTIME_PATH_STEPS
        or any(
            _compound_coordinate(item, "Trample checkpoint path") != item
            for item in route["path"]
        )
        or type(route.get("maximumFeet")) is not int
        or route["maximumFeet"] <= 0
        or not isinstance(route.get("transientOccupantIds"), list)
        or route["transientOccupantIds"] != sorted(set(route["transientOccupantIds"]))
        or not isinstance(target_ids, list)
        or len(target_ids) != len(set(target_ids))
        or any(type(target_id) is not str or not target_id for target_id in target_ids)
        or type(cursor) is not int
        or not 0 <= cursor <= len(target_ids)
        or not isinstance(results, list)
        or len(results) != cursor
        or [result.get("targetId") for result in results if isinstance(result, Mapping)]
        != target_ids[:cursor]
    ):
        raise ValueError("Trample checkpoint contract is invalid")
    if stage == "damage-pool" and (
        checkpoint["damagePool"] is not None
        or target_ids
        or cursor
        or results
        or checkpoint["movement"] is not None
    ):
        raise ValueError("Trample checkpoint order is invalid")
    if stage == "movement" and (
        not isinstance(checkpoint["damagePool"], Mapping)
        or target_ids
        or cursor
        or results
        or checkpoint["movement"] is not None
    ):
        raise ValueError("Trample checkpoint order is invalid")
    if stage == "targets" and (
        not isinstance(checkpoint["damagePool"], Mapping)
        or not target_ids
        or not isinstance(checkpoint["movement"], Mapping)
    ):
        raise ValueError("Trample checkpoint order is invalid")
    if checkpoint["damagePool"] is not None:
        _compound_damage_pool(checkpoint["damagePool"], str(contract["strikeId"]))


def _compound_request_for_target(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    target_id = checkpoint["targetIds"][checkpoint["targetCursor"]]
    return {
        "kind": "basic-save-damage",
        "targetId": target_id,
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dc": checkpoint["contract"]["savingThrowDC"],
        },
        "damagePool": deepcopy(checkpoint["damagePool"]),
        "traits": deepcopy(checkpoint["contract"]["traits"]),
    }


def start_compound_activity(
    state: Mapping[str, Any],
    actor_id: str,
    action: Mapping[str, Any],
    ability: Mapping[str, Any],
) -> dict[str, Any]:
    """Start Trample with no future host input embedded in the action."""

    if (
        not isinstance(action, Mapping)
        or set(action) != {"type", "abilityId"}
        or action.get("type") != "Activity"
        or action.get("abilityId") != ability.get("id")
    ):
        raise ValueError("Trample start action is invalid")
    contract = _compound_mechanic_contract(ability)
    route = _compound_route(state, actor_id, contract["maximumSizeRank"])
    checkpoint = {
        "schema": _COMPOUND_SCHEMA,
        "kind": _COMPOUND_KIND,
        "stage": "damage-pool",
        "actorId": actor_id,
        "abilityId": str(ability["id"]),
        "contract": contract,
        "route": route,
        "damagePool": None,
        "targetIds": [],
        "targetCursor": 0,
        "targetResults": [],
        "movement": None,
    }
    validate_compound_checkpoint(checkpoint)
    return {
        "checkpoint": checkpoint,
        "request": {
            "kind": "host-input",
            "input": {
                "kind": "listed-strike-damage",
                "strikeId": contract["strikeId"],
            },
        },
    }


def resume_compound_activity(
    state: Mapping[str, Any],
    actor_id: str,
    checkpoint: Mapping[str, Any],
    transaction_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Advance exactly one sealed generic transaction result."""

    validate_compound_checkpoint(checkpoint)
    if actor_id != checkpoint["actorId"] or not isinstance(transaction_result, Mapping):
        raise ValueError("Trample continuation owner is invalid")
    stage = checkpoint["stage"]
    if stage == "damage-pool":
        if transaction_result.get("kind") != "host-input":
            raise ValueError("Trample expected its listed-Strike damage pool")
        participants = _compound_participant_map(state)
        actor = participants.get(actor_id)
        definition = _compound_definition(state, actor) if actor is not None else None
        ability = (
            next(
                (
                    item
                    for item in definition.get("abilities", [])
                    if isinstance(item, Mapping)
                    and item.get("id") == checkpoint["abilityId"]
                ),
                None,
            )
            if isinstance(definition, Mapping)
            else None
        )
        if ability is None or _compound_mechanic_contract(ability) != checkpoint["contract"]:
            raise ValueError("Trample selected ability changed before continuation")
        if _compound_route(state, actor_id, checkpoint["contract"]["maximumSizeRank"]) != checkpoint["route"]:
            raise ValueError("Trample selected route changed before continuation")
        updated = deepcopy(dict(checkpoint))
        updated["stage"] = "movement"
        updated["damagePool"] = _compound_damage_pool(
            transaction_result.get("input"),
            checkpoint["contract"]["strikeId"],
        )
        validate_compound_checkpoint(updated)
        return {
            "checkpoint": updated,
            "request": {
                "kind": "land-move",
                **deepcopy(checkpoint["route"]),
            },
        }
    if stage == "movement":
        movement = transaction_result.get("movement")
        if transaction_result.get("kind") != "land-move" or not isinstance(movement, Mapping):
            raise ValueError("Trample expected its land movement result")
        if not movement.get("endedMoveAction"):
            outcome = movement.get("suspendedActionOutcome")
            if not isinstance(outcome, Mapping) or outcome.get("status") not in {
                "disrupted",
                "actor-unable-to-continue",
            }:
                raise ValueError("Trample land movement did not finish")
            return {
                "eventPayload": {
                    "trampleResult": {
                        "disrupted": True,
                        "movement": deepcopy(dict(movement)),
                        "targetParticipantIds": [],
                        "targetResults": [],
                        "multipleAttackPenalty": {"read": False, "advanced": False},
                        "completenessDeferrals": list(TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS),
                    }
                }
            }
        if (
            movement.get("path") != checkpoint["route"]["path"]
            or movement.get("requestedMaximumFeet") != checkpoint["route"]["maximumFeet"]
            or movement.get("baseLandSpeedFeet") * 2 != checkpoint["route"]["maximumFeet"]
            or movement.get("transientOccupantIds") != checkpoint["route"]["transientOccupantIds"]
        ):
            raise ValueError("Trample movement evidence changed")
        entered = movement.get("enteredParticipants")
        if not isinstance(entered, list) or any(
            not isinstance(item, Mapping)
            or set(item) != {"participantId", "pathIndexes"}
            or not isinstance(item.get("participantId"), str)
            or not isinstance(item.get("pathIndexes"), list)
            or not item["pathIndexes"]
            or any(type(index) is not int or index < 0 for index in item["pathIndexes"])
            for item in entered
        ):
            raise ValueError("Trample first-entry evidence is invalid")
        entered_ids = [str(item["participantId"]) for item in entered]
        if sorted(entered_ids) != checkpoint["route"]["transientOccupantIds"]:
            raise ValueError("Trample movement lost its exact target census")
        target_ids = [
            str(item["participantId"])
            for item in sorted(
                entered,
                key=lambda item: (min(item["pathIndexes"]), str(item["participantId"])),
            )
        ]
        updated = deepcopy(dict(checkpoint))
        updated.update(
            {
                "stage": "targets",
                "targetIds": target_ids,
                "movement": deepcopy(dict(movement)),
            }
        )
        validate_compound_checkpoint(updated)
        return {"checkpoint": updated, "request": _compound_request_for_target(updated)}
    if transaction_result.get("kind") != "basic-save-damage":
        raise ValueError("Trample expected one target's basic Reflex result")
    target_result = transaction_result.get("targetResult")
    expected_target = checkpoint["targetIds"][checkpoint["targetCursor"]]
    if (
        not isinstance(target_result, Mapping)
        or target_result.get("targetId") != expected_target
        or not isinstance(target_result.get("savingThrow"), Mapping)
        or target_result["savingThrow"].get("type") != "reflex"
        or not isinstance(target_result.get("damage"), Mapping)
    ):
        raise ValueError("Trample target result is invalid")
    updated = deepcopy(dict(checkpoint))
    updated["targetResults"].append(deepcopy(dict(target_result)))
    updated["targetCursor"] += 1
    validate_compound_checkpoint(updated)
    if updated["targetCursor"] < len(updated["targetIds"]):
        return {"checkpoint": updated, "request": _compound_request_for_target(updated)}
    return {
        "eventPayload": {
            "trampleResult": {
                "disrupted": False,
                "movement": deepcopy(updated["movement"]),
                "targetParticipantIds": list(updated["targetIds"]),
                "sharedDamagePool": deepcopy(updated["damagePool"]),
                "targetResults": deepcopy(updated["targetResults"]),
                "multipleAttackPenalty": {"read": False, "advanced": False},
                "completenessDeferrals": list(TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS),
            }
        }
    }


def _render_participant(
    participant_id: object,
    participants: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
) -> str:
    if not isinstance(participant_id, str) or not participant_id:
        raise EngineInputError("Trample transcript participant is invalid")
    participant = participants.get(participant_id)
    definition = (
        definitions.get(str(participant.get("creatureId") or ""))
        if isinstance(participant, Mapping)
        else None
    )
    if not isinstance(participant, Mapping) or not isinstance(definition, Mapping):
        raise EngineInputError("Trample transcript participant is missing")
    name = definition.get("name")
    if not isinstance(name, str) or not name:
        raise EngineInputError("Trample transcript participant name is invalid")
    return f"{name} ({participant_id})"


def _render_event_actor(
    event: Mapping[str, Any],
    participants: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
    event_type: str,
) -> str:
    if (
        not isinstance(event, Mapping)
        or event.get("type") != event_type
        or event.get("mechanicType") != MECHANIC_TYPE
        or event.get("abilityId") != ABILITY_ID
    ):
        raise EngineInputError("Trample transcript event is invalid")
    return _render_participant(
        event.get("actorId"),
        participants,
        definitions,
    )


def render_compound_activity_started_event(
    event: Mapping[str, Any],
    participants: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
) -> str:
    actor = _render_event_actor(
        event,
        participants,
        definitions,
        "compound-activity-started",
    )
    if (
        event.get("actionCost") != 3
        or event.get("compoundActivity") is not True
        or event.get("compoundActivityStage") != 0
        or event.get("compoundRequestKind") != "host-input"
    ):
        raise EngineInputError("Trample start transcript event is invalid")
    return f"{actor} begins Trample."


def render_compound_host_input_event(
    event: Mapping[str, Any],
    participants: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
) -> str:
    actor = _render_event_actor(
        event,
        participants,
        definitions,
        "compound-host-input",
    )
    pool = event.get("input")
    strike_id = pool.get("strikeId") if isinstance(pool, Mapping) else None
    if (
        event.get("actionCost") != 0
        or not isinstance(strike_id, str)
        or not strike_id
    ):
        raise EngineInputError("Trample host-input transcript event is invalid")
    _compound_damage_pool(pool, strike_id)
    return f"{actor} rolls Trample's shared damage once."


def render_compound_activity_continued_event(
    event: Mapping[str, Any],
    participants: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
) -> str:
    actor = _render_event_actor(
        event,
        participants,
        definitions,
        "compound-activity-continued",
    )
    stage = event.get("compoundActivityStage")
    request_kind = event.get("compoundRequestKind")
    if (
        event.get("actionCost") != 0
        or event.get("actionCostPaidAtStart") != 3
        or event.get("compoundActivity") is not True
        or (stage, request_kind)
        not in {(1, "land-move"), (2, "basic-save-damage")}
    ):
        raise EngineInputError("Trample continuation transcript event is invalid")
    phase = "movement" if request_kind == "land-move" else "target saves"
    return f"{actor} continues Trample with {phase}."


def render_compound_basic_save_damage_event(
    event: Mapping[str, Any],
    participants: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
) -> str:
    _render_event_actor(
        event,
        participants,
        definitions,
        "compound-basic-save-damage",
    )
    results = event.get("targetResults")
    if (
        event.get("actionCost") != 0
        or not isinstance(results, list)
        or len(results) != 1
        or not isinstance(results[0], Mapping)
    ):
        raise EngineInputError("Trample save transcript event is invalid")
    result = results[0]
    saving_throw = result.get("savingThrow")
    damage = result.get("damage")
    if (
        not isinstance(saving_throw, Mapping)
        or saving_throw.get("type") != "reflex"
        or saving_throw.get("basic") is not True
        or saving_throw.get("degree")
        not in {"critical-success", "success", "failure", "critical-failure"}
        or not isinstance(damage, Mapping)
        or type(damage.get("appliedTotal")) is not int
        or damage["appliedTotal"] < 0
    ):
        raise EngineInputError("Trample save transcript result is invalid")
    target = _render_participant(
        result.get("targetId"),
        participants,
        definitions,
    )
    return (
        f"{target} makes a basic Reflex save against Trample: "
        f"{saving_throw['degree']}; {damage['appliedTotal']} damage applied."
    )


def render_activity_event(
    event: Mapping[str, Any],
    participants: Mapping[str, Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
) -> str:
    actor = _render_event_actor(
        event,
        participants,
        definitions,
        "activity",
    )
    result = event.get("trampleResult")
    if (
        event.get("actionCost") != 0
        or event.get("actionCostPaidAtStart") != 3
        or event.get("compoundActivity") is not True
        or not isinstance(result, Mapping)
        or type(result.get("disrupted")) is not bool
        or result.get("multipleAttackPenalty")
        != {"read": False, "advanced": False}
        or result.get("completenessDeferrals")
        != list(TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS)
    ):
        raise EngineInputError("Trample completion transcript event is invalid")
    if result["disrupted"]:
        if result.get("targetParticipantIds") != [] or result.get("targetResults") != []:
            raise EngineInputError("disrupted Trample transcript event is invalid")
        return f"{actor}'s Trample ends after its movement is disrupted."
    target_ids = result.get("targetParticipantIds")
    target_results = result.get("targetResults")
    pool = result.get("sharedDamagePool")
    strike_id = pool.get("strikeId") if isinstance(pool, Mapping) else None
    if (
        not isinstance(target_ids, list)
        or not target_ids
        or len(target_ids) != len(set(target_ids))
        or not isinstance(target_results, list)
        or [
            item.get("targetId")
            for item in target_results
            if isinstance(item, Mapping)
        ]
        != target_ids
        or not isinstance(strike_id, str)
        or not strike_id
    ):
        raise EngineInputError("Trample completion targets are invalid")
    _compound_damage_pool(pool, strike_id)
    targets = ", ".join(
        _render_participant(target_id, participants, definitions)
        for target_id in target_ids
    )
    return f"{actor} completes Trample against {targets}."


__all__ = [
    "ABILITY_ID",
    "COMPILER_ID",
    "CompiledTrample",
    "FAMILY_ID",
    "LinkedTrample",
    "MECHANIC_TYPE",
    "RUNTIME_CAPABILITY_ID",
    "RUNTIME_FAMILY_ID",
    "RUNTIME_PACKAGE_ID",
    "RuntimeDeferral",
    "TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS",
    "TRAMPLE_RULE_REQUIREMENTS",
    "TrampleRuntimeHost",
    "compile_trample",
    "link_trample_strike",
    "render_activity_event",
    "render_compound_activity_continued_event",
    "render_compound_activity_started_event",
    "render_compound_basic_save_damage_event",
    "render_compound_host_input_event",
    "resume_compound_activity",
    "resume_trample",
    "start_compound_activity",
    "start_trample",
    "validate_compound_checkpoint",
]

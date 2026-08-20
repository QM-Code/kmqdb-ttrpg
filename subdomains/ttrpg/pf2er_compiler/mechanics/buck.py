"""Compile the bounded Monster Core Buck shorthand without activating it.

Monster Core creature blocks carry Buck as the exact ordered object
``{"Action":"reaction","Description":"DC <n> (page 358)"}``.  The complete
reaction lives in the Monster Core ability glossary.  This module verifies
both sides through one trusted source-authority adapter, preserves receipts
for the carrier and its two records, and emits the runtime work that remains
deferred.

There is deliberately no registry fragment or encounter transition here.
Mount, Command an Animal, mounted co-occupancy, the Reflex save, falling and
landing consequences, and reaction timing must exist as shared mechanics
before Buck can become executable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Literal, Mapping, TypeAlias, final

from .contracts import RawSourceMember, RawSourceObject
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
    canonical_raw_bytes,
    raw_member_sha256,
    raw_source_sha256,
)


FAMILY_ID = "buck"
MECHANIC_TYPE = "buck"
MONSTER_CORE_SOURCE_ID = "core-mc1"
GLOSSARY_LOCATOR = "358.2"
GLOSSARY_PRINTED_PAGE = 358
MAX_BUCK_DC = 10_000
MAX_BUCK_SOURCE_BYTES = 128

DependencyPhase: TypeAlias = Literal["source-link", "runtime"]
DeferredMechanic: TypeAlias = Literal[
    "mount-action",
    "command-an-animal-action",
    "mounted-co-occupancy",
    "reflex-save",
    "dismount-and-landing",
    "prone-condition",
    "falling-damage",
    "reaction-window",
]

_LOCATOR_RE = re.compile(r"^[0-9]+\.[0-9]+$", re.ASCII)
_DESCRIPTION_RE = re.compile(
    rf"^DC (?P<dc>[1-9][0-9]*) \(page {GLOSSARY_PRINTED_PAGE}\)$",
    re.ASCII,
)
_LOCAL_KEYS = ("Action", "Description")
_GLOSSARY_KEYS = ("Name", "Action", "Description", "Trigger", "Effect")
_GLOSSARY_BLOCK_SHA256 = (
    "6f1b6588658d2ac4d4fc1b6c25c9ba8fea4ab6d4149d168b8a0aae6ad99092d9"
)
_DEPENDENCY_SPECS = (
    (
        "verified-mount-action",
        "source-link",
        "mount-action",
        "source-verified Mount action, rider entry, and mount identity",
    ),
    (
        "verified-command-an-animal-action",
        "source-link",
        "command-an-animal-action",
        "source-verified Command an Animal action while riding",
    ),
    (
        "mounted-co-occupancy",
        "runtime",
        "mounted-co-occupancy",
        "rider and mount share an explicit mounted spatial relation",
    ),
    (
        "reflex-saving-throw",
        "runtime",
        "reflex-save",
        "explicit Reflex roll and four-degree save resolution",
    ),
    (
        "dismount-and-landing",
        "runtime",
        "dismount-and-landing",
        "remove the mounted relation and choose a rules-valid landing square",
    ),
    (
        "prone-on-landing",
        "runtime",
        "prone-condition",
        "source-backed prone application after an unsuccessful Buck save",
    ),
    (
        "normal-and-critical-falling-damage",
        "runtime",
        "falling-damage",
        (
            "normal fall damage plus the critical-failure 1d6 bludgeoning "
            "component"
        ),
    ),
    (
        "buck-reaction-window",
        "runtime",
        "reaction-window",
        (
            "pre-resolution reaction window for the triggering Mount or "
            "Command an Animal action"
        ),
    ),
)


class BuckCompileError(ValueError):
    """A verified source carrier does not match the bounded Buck grammar."""


@final
@dataclass(frozen=True, slots=True)
class DeferredBuckDependency:
    """One typed missing mechanic that blocks registry activation."""

    dependency_id: str
    phase: DependencyPhase
    mechanic: DeferredMechanic
    required_contract: str

    def __post_init__(self) -> None:
        raise TypeError("DeferredBuckDependency contract is not bound")

    def as_serialized(self) -> dict[str, str]:
        raise TypeError("DeferredBuckDependency contract is not bound")


def _bind_dependency_contract():
    canonical_specs = tuple(tuple(item) for item in _DEPENDENCY_SPECS)

    def validate(value: DeferredBuckDependency) -> None:
        if (
            type(value) is not DeferredBuckDependency
            or type(value.dependency_id) is not str
            or type(value.phase) is not str
            or type(value.mechanic) is not str
            or type(value.required_contract) is not str
            or (
                value.dependency_id,
                value.phase,
                value.mechanic,
                value.required_contract,
            )
            not in canonical_specs
        ):
            raise TypeError(
                "DeferredBuckDependency must match one exact canonical spec"
            )

    def serialize(value: DeferredBuckDependency) -> dict[str, str]:
        validate(value)
        return {
            "id": value.dependency_id,
            "phase": value.phase,
            "mechanic": value.mechanic,
            "requiredContract": value.required_contract,
            "status": "deferred",
            "blocks": "registry-activation",
        }

    def build() -> tuple[DeferredBuckDependency, ...]:
        return tuple(
            DeferredBuckDependency(*spec)
            for spec in canonical_specs
        )

    return validate, serialize, build


(
    _validate_dependency,
    _serialize_dependency,
    _build_dependencies,
) = _bind_dependency_contract()
DeferredBuckDependency.__post_init__ = _validate_dependency
DeferredBuckDependency.as_serialized = _serialize_dependency
BUCK_DEPENDENCIES = _build_dependencies()


BUCK_GLOSSARY_RULE = RuleRequirement(
    rule_id="monster-core-buck",
    source_id=MONSTER_CORE_SOURCE_ID,
    locator=GLOSSARY_LOCATOR,
    carrier_path=(
        RawMemberStep(raw_key="^.ability", member_ordinal=6),
    ),
    expected_block_sha256=_GLOSSARY_BLOCK_SHA256,
)


@final
@dataclass(frozen=True, slots=True, init=False)
class BuckSourceRecord:
    """Opaque authority-backed Action or Description source record."""

    _authority: SourceAuthorityAdapter = field(repr=False)
    _receipt: SourceReceipt = field(repr=False)
    _field_name: str = field(repr=False)
    _source_text: str = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "BuckSourceRecord can only be constructed by compile_buck"
        )

    @property
    def field_name(self) -> Literal["Action", "Description"]:
        raise TypeError("BuckSourceRecord contract is not bound")

    @property
    def source_text(self) -> str:
        raise TypeError("BuckSourceRecord contract is not bound")

    @property
    def receipt(self) -> SourceReceipt:
        raise TypeError("BuckSourceRecord contract is not bound")

    def as_serialized(self) -> dict[str, Any]:
        raise TypeError("BuckSourceRecord contract is not bound")


@final
@dataclass(frozen=True, slots=True, init=False)
class CompiledBuck:
    """Opaque, revalidated Buck compile result."""

    _authority: SourceAuthorityAdapter = field(repr=False)
    _consumer_receipt: SourceReceipt = field(repr=False)
    _projection: Mapping[str, Any] = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("CompiledBuck can only be constructed by compile_buck")

    @property
    def source_id(self) -> str:
        raise TypeError("CompiledBuck contract is not bound")

    @property
    def locator(self) -> str:
        raise TypeError("CompiledBuck contract is not bound")

    @property
    def action_cost(self) -> Literal["reaction"]:
        raise TypeError("CompiledBuck contract is not bound")

    @property
    def reflex_dc(self) -> int:
        raise TypeError("CompiledBuck contract is not bound")

    @property
    def printed_page(self) -> Literal[358]:
        raise TypeError("CompiledBuck contract is not bound")

    @property
    def source_receipt(self) -> SourceReceipt:
        raise TypeError("CompiledBuck contract is not bound")

    @property
    def records(self) -> tuple[BuckSourceRecord, BuckSourceRecord]:
        raise TypeError("CompiledBuck contract is not bound")

    @property
    def provider_rule(self) -> VerifiedRuleReceipt:
        raise TypeError("CompiledBuck contract is not bound")

    @property
    def dependencies(self) -> tuple[DeferredBuckDependency, ...]:
        raise TypeError("CompiledBuck contract is not bound")

    def as_serialized(self) -> dict[str, Any]:
        raise TypeError("CompiledBuck contract is not bound")


def _closed_json_transform(
    value: Any,
    *,
    freeze: bool,
    label: str,
) -> Any:
    """Copy a finite JSON projection while rejecting aliases and cycles."""

    maximum_depth = 32
    maximum_nodes = 4_096
    maximum_items = 1_024
    maximum_text_bytes = 1_024
    active: set[int] = set()
    node_count = 0

    def visit(item: Any, depth: int) -> Any:
        nonlocal node_count
        node_count += 1
        if node_count > maximum_nodes:
            raise BuckCompileError(f"{label} exceeds its node bound")
        if depth > maximum_depth:
            raise BuckCompileError(f"{label} exceeds its depth bound")
        if item is None or type(item) in {bool, int}:
            return item
        if type(item) is str:
            if len(item.encode("utf-8")) > maximum_text_bytes:
                raise BuckCompileError(f"{label} exceeds its text bound")
            return item

        mapping_type = dict if freeze else MappingProxyType
        if type(item) is mapping_type:
            if len(item) > maximum_items:
                raise BuckCompileError(
                    f"{label} mapping exceeds its item bound"
                )
            identity = id(item)
            if identity in active:
                raise BuckCompileError(f"{label} contains a cycle")
            active.add(identity)
            try:
                copied: dict[str, Any] = {}
                for key, nested in item.items():
                    if type(key) is not str:
                        raise BuckCompileError(
                            f"{label} contains a non-string key"
                        )
                    if len(key.encode("utf-8")) > maximum_text_bytes:
                        raise BuckCompileError(
                            f"{label} contains an oversized key"
                        )
                    copied[key] = visit(nested, depth + 1)
            finally:
                active.remove(identity)
            return MappingProxyType(copied) if freeze else copied

        sequence_type = list if freeze else tuple
        if type(item) is sequence_type:
            if len(item) > maximum_items:
                raise BuckCompileError(
                    f"{label} sequence exceeds its item bound"
                )
            identity = id(item)
            if identity in active:
                raise BuckCompileError(f"{label} contains a cycle")
            active.add(identity)
            try:
                copied_items = [
                    visit(nested, depth + 1)
                    for nested in item
                ]
            finally:
                active.remove(identity)
            return tuple(copied_items) if freeze else copied_items

        raise BuckCompileError(f"{label} is not closed JSON")

    return visit(value, 0)


def _freeze_json(value: Any) -> Mapping[str, Any]:
    frozen = _closed_json_transform(
        value,
        freeze=True,
        label="Buck derived projection",
    )
    if type(frozen) is not MappingProxyType:
        raise BuckCompileError("Buck projection root must be an object")
    return frozen


def _thaw_json(value: Any) -> dict[str, Any]:
    thawed = _closed_json_transform(
        value,
        freeze=False,
        label="Buck stored projection",
    )
    if type(thawed) is not dict:
        raise BuckCompileError("Buck stored projection root must be an object")
    return thawed


def _require_consumer_root(
    selection: VerifiedSourceSelection,
    *,
    source_id: str,
    locator_re: re.Pattern[str],
) -> tuple[VerifiedSourceCarrier, RawSourceObject]:
    if type(selection) is not VerifiedSourceSelection:
        raise TypeError(
            "Buck consumer must reload as VerifiedSourceSelection"
        )
    address = selection.address
    carrier = selection.carrier
    if type(carrier) is not VerifiedSourceCarrier:
        raise TypeError("Buck consumer carrier is not verified")
    if (
        carrier.source_id != source_id
        or type(carrier.locator) is not str
        or locator_re.fullmatch(carrier.locator) is None
        or address.selection_path != ()
        or address.span is not None
        or not address.carrier_path
        or type(address.carrier_path[-1]) is not RawMemberStep
        or address.carrier_path[-1].raw_key != "!.Buck"
        or selection.raw_member is not None
        or selection.raw_value is not selection.selected_value
        or selection.selected_value is not carrier.raw_block
        or type(carrier.raw_block) is not RawSourceObject
    ):
        raise BuckCompileError(
            "Buck consumer must select one exact core-mc1 !.Buck carrier"
        )
    return carrier, carrier.raw_block


def _require_local_shape(
    block: RawSourceObject,
    *,
    local_keys: tuple[str, str],
    description_re: re.Pattern[str],
    maximum_source_bytes: int,
    maximum_dc: int,
) -> tuple[str, str, int]:
    if len(canonical_raw_bytes(block)) > maximum_source_bytes:
        raise BuckCompileError("Buck source object exceeds its byte bound")
    if (
        type(block.members) is not tuple
        or len(block.members) != 2
        or any(type(member) is not RawSourceMember for member in block.members)
        or tuple(member.key for member in block.members) != local_keys
    ):
        raise BuckCompileError(
            "Buck requires exact ordered Action and Description records"
        )
    action = block.members[0].value
    description = block.members[1].value
    if type(action) is not str or action != "reaction":
        raise BuckCompileError("Buck Action must be the exact reaction slug")
    if type(description) is not str:
        raise BuckCompileError("Buck Description must be an exact string")
    if len(description.encode("utf-8")) > maximum_source_bytes:
        raise BuckCompileError("Buck Description exceeds its byte bound")
    match = description_re.fullmatch(description)
    if match is None:
        raise BuckCompileError(
            "Buck Description must be exactly 'DC <n> (page 358)'"
        )
    dc_text = match.group("dc")
    if len(dc_text) > len(str(maximum_dc)):
        raise BuckCompileError("Buck DC exceeds its finite bound")
    dc = int(dc_text)
    if type(dc) is not int or not 1 <= dc <= maximum_dc:
        raise BuckCompileError("Buck DC exceeds its finite bound")
    return action, description, dc


def _require_provider_shape(
    rule: VerifiedRuleReceipt,
    *,
    requirement: RuleRequirement,
    glossary_keys: tuple[str, ...],
    expected_block_sha256: str,
) -> None:
    if type(rule) is not VerifiedRuleReceipt:
        raise TypeError("Buck provider rule is not verified")
    selection = rule.selection
    block = selection.selected_value
    if (
        type(selection) is not VerifiedSourceSelection
        or rule.rule_id != requirement.rule_id
        or type(rule.requirement) is not RuleRequirement
        or rule.requirement != requirement
        or rule.receipt != selection.receipt
        or rule.receipt.block_sha256 != expected_block_sha256
        or selection.address.source_id != requirement.source_id
        or selection.address.locator != requirement.locator
        or selection.address.carrier_path != requirement.carrier_path
        or selection.address.selection_path != requirement.selection_path
        or selection.address.span != requirement.span
        or type(block) is not RawSourceObject
        or type(block.members) is not tuple
        or len(block.members) != len(glossary_keys)
        or any(type(member) is not RawSourceMember for member in block.members)
        or tuple(member.key for member in block.members) != glossary_keys
        or type(block.members[0].value) is not str
        or block.members[0].value != "Buck"
        or type(block.members[1].value) is not str
        or block.members[1].value != "reaction"
    ):
        raise BuckCompileError(
            "verified Monster Core Buck glossary provider is invalid"
        )


def _new_record(
    authority: SourceAuthorityAdapter,
    carrier: VerifiedSourceCarrier,
    *,
    ordinal: int,
    field_name: str,
    source_text: str,
) -> BuckSourceRecord:
    issued = carrier.select(
        (
            RawMemberStep(
                raw_key=field_name,
                member_ordinal=ordinal,
            ),
        )
    )
    verified = authority.validate_selection(
        authority.reload(issued.receipt)
    )
    if (
        type(verified) is not VerifiedSourceSelection
        or type(verified.selected_value) is not str
        or verified.selected_value != source_text
    ):
        raise BuckCompileError("Buck source record failed authority replay")
    result = object.__new__(BuckSourceRecord)
    object.__setattr__(result, "_authority", authority)
    object.__setattr__(result, "_receipt", verified.receipt)
    object.__setattr__(result, "_field_name", field_name)
    object.__setattr__(result, "_source_text", source_text)
    return result


def _contract_fingerprint(
    provider_spec: tuple[Any, ...],
    dependency_specs: tuple[tuple[str, str, str, str], ...],
) -> str:
    payload = {
        "schema": 1,
        "provider": provider_spec,
        "dependencies": dependency_specs,
    }
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as failure:
        raise BuckCompileError(
            "Buck reviewed contract is not closed JSON"
        ) from failure
    return hashlib.sha256(encoded).hexdigest()


def _bind_reviewed_contract():
    """Close compiler/projections over reviewed values, not public aliases."""

    source_id = str(MONSTER_CORE_SOURCE_ID)
    glossary_locator = str(GLOSSARY_LOCATOR)
    printed_page = int(GLOSSARY_PRINTED_PAGE)
    maximum_dc = int(MAX_BUCK_DC)
    maximum_source_bytes = int(MAX_BUCK_SOURCE_BYTES)
    local_keys = tuple(_LOCAL_KEYS)
    glossary_keys = tuple(_GLOSSARY_KEYS)
    locator_re = re.compile(_LOCATOR_RE.pattern, re.ASCII)
    description_re = re.compile(_DESCRIPTION_RE.pattern, re.ASCII)
    provider_spec = (
        "monster-core-buck",
        source_id,
        glossary_locator,
        (("^.ability", 6),),
        _GLOSSARY_BLOCK_SHA256,
    )
    dependency_specs = tuple(
        tuple(spec)
        for spec in _DEPENDENCY_SPECS
    )
    fingerprint_function = _contract_fingerprint
    fingerprint = fingerprint_function(
        provider_spec,
        dependency_specs,
    )

    authority_type = SourceAuthorityAdapter
    receipt_type = SourceReceipt
    selection_type = VerifiedSourceSelection
    carrier_type = VerifiedSourceCarrier
    rule_receipt_type = VerifiedRuleReceipt
    requirement_type = RuleRequirement
    member_step_type = RawMemberStep
    raw_member_type = RawSourceMember
    record_type = BuckSourceRecord
    compiled_type = CompiledBuck
    dependency_type = DeferredBuckDependency
    raw_member_hash = raw_member_sha256
    raw_source_hash = raw_source_sha256
    json_dumps = json.dumps

    require_consumer_root = _require_consumer_root
    require_local_shape = _require_local_shape
    require_provider_shape = _require_provider_shape
    new_record = _new_record
    closed_json_transform = _closed_json_transform

    def freeze_json(value: Any) -> Mapping[str, Any]:
        frozen = closed_json_transform(
            value,
            freeze=True,
            label="Buck derived projection",
        )
        if type(frozen) is not MappingProxyType:
            raise BuckCompileError(
                "Buck projection root must be an object"
            )
        return frozen

    def thaw_json(value: Any) -> dict[str, Any]:
        thawed = closed_json_transform(
            value,
            freeze=False,
            label="Buck stored projection",
        )
        if type(thawed) is not dict:
            raise BuckCompileError(
                "Buck stored projection root must be an object"
            )
        return thawed

    def projection_bytes(value: dict[str, Any]) -> bytes:
        try:
            return json_dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as failure:
            raise BuckCompileError(
                "Buck projection is not canonical JSON"
            ) from failure

    def require_contract() -> None:
        if (
            type(provider_spec) is not tuple
            or len(provider_spec) != 5
            or provider_spec[0] != "monster-core-buck"
            or provider_spec[1] != "core-mc1"
            or provider_spec[2] != "358.2"
            or provider_spec[3] != (("^.ability", 6),)
            or provider_spec[4] != (
                "6f1b6588658d2ac4d4fc1b6c25c9ba8fea4ab6d4149d168b8a0aae6ad99092d9"
            )
            or type(dependency_specs) is not tuple
            or len(dependency_specs) != 8
            or any(
                type(spec) is not tuple
                or len(spec) != 4
                or any(type(item) is not str for item in spec)
                for spec in dependency_specs
            )
            or fingerprint_function(
                provider_spec,
                dependency_specs,
            )
            != fingerprint
        ):
            raise BuckCompileError(
                "Buck reviewed contract fingerprint disagrees"
            )

    def build_requirement() -> RuleRequirement:
        require_contract()
        rule_id, rule_source, locator, path, expected_hash = provider_spec
        return requirement_type(
            rule_id=rule_id,
            source_id=rule_source,
            locator=locator,
            carrier_path=tuple(
                member_step_type(raw_key, ordinal)
                for raw_key, ordinal in path
            ),
            expected_block_sha256=expected_hash,
        )

    def build_dependencies() -> tuple[DeferredBuckDependency, ...]:
        require_contract()
        result = tuple(
            dependency_type(*spec)
            for spec in dependency_specs
        )
        if (
            len(result) != 8
            or any(type(item) is not dependency_type for item in result)
        ):
            raise BuckCompileError(
                "Buck dependency contract could not be reconstructed"
            )
        return result

    def validate_record(
        value: object,
    ) -> tuple[VerifiedSourceSelection, str, str]:
        if type(value) is not record_type:
            raise TypeError(
                "Buck source projection requires an exact BuckSourceRecord"
            )
        try:
            authority = value._authority
            receipt = value._receipt
            field_name = value._field_name
            source_text = value._source_text
        except AttributeError as failure:
            raise BuckCompileError(
                "Buck source record is incomplete"
            ) from failure
        if (
            type(authority) is not authority_type
            or type(receipt) is not receipt_type
            or type(field_name) is not str
            or field_name not in local_keys
            or type(source_text) is not str
            or not source_text
            or source_text != source_text.strip()
            or len(source_text.encode("utf-8")) > maximum_source_bytes
        ):
            raise BuckCompileError("Buck source record is forged")
        selection = authority.validate_selection(
            authority.reload(receipt)
        )
        ordinal = local_keys.index(field_name)
        path = selection.address.selection_path
        if (
            type(selection) is not selection_type
            or type(selection.carrier) is not carrier_type
            or selection.receipt != receipt
            or selection.address.source_id != source_id
            or type(path) is not tuple
            or len(path) != 1
            or type(path[0]) is not member_step_type
            or path[0].raw_key != field_name
            or path[0].member_ordinal != ordinal
            or selection.address.span is not None
            or not selection.address.carrier_path
            or type(selection.address.carrier_path[-1])
            is not member_step_type
            or selection.address.carrier_path[-1].raw_key != "!.Buck"
            or type(selection.raw_member) is not raw_member_type
            or selection.raw_member.key != field_name
            or type(selection.raw_member.value) is not str
            or selection.raw_member.value != source_text
            or type(selection.selected_value) is not str
            or selection.selected_value != source_text
            or receipt.member_sha256
            != raw_member_hash(
                raw_member_type(key=field_name, value=source_text)
            )
            or receipt.value_sha256 != raw_source_hash(source_text)
            or receipt.selection_sha256 != raw_source_hash(source_text)
        ):
            raise BuckCompileError(
                "Buck source record no longer selects its exact member"
            )
        return selection, field_name, source_text

    def record_field_name(value: BuckSourceRecord) -> str:
        _selection, field_name, _source_text = validate_record(value)
        return field_name

    def record_source_text(value: BuckSourceRecord) -> str:
        _selection, _field_name, source_text = validate_record(value)
        return source_text

    def record_receipt(value: BuckSourceRecord) -> SourceReceipt:
        selection, _field_name, _source_text = validate_record(value)
        return selection.receipt

    def record_projection(value: BuckSourceRecord) -> dict[str, Any]:
        selection, field_name, source_text = validate_record(value)
        return {
            "field": field_name,
            "sourceText": source_text,
            "source": selection.receipt.as_serialized(),
        }

    def derive(
        authority: SourceAuthorityAdapter,
        consumer_receipt: SourceReceipt,
    ) -> tuple[
        VerifiedSourceSelection,
        VerifiedRuleReceipt,
        tuple[BuckSourceRecord, BuckSourceRecord],
        tuple[DeferredBuckDependency, ...],
        int,
        dict[str, Any],
    ]:
        require_contract()
        if type(authority) is not authority_type:
            raise TypeError(
                "compile_buck requires an exact SourceAuthorityAdapter"
            )
        if type(consumer_receipt) is not receipt_type:
            raise TypeError("compile_buck requires an exact SourceReceipt")

        consumer = authority.validate_selection(
            authority.reload(consumer_receipt)
        )
        carrier, block = require_consumer_root(
            consumer,
            source_id=source_id,
            locator_re=locator_re,
        )
        action, description, dc = require_local_shape(
            block,
            local_keys=local_keys,
            description_re=description_re,
            maximum_source_bytes=maximum_source_bytes,
            maximum_dc=maximum_dc,
        )

        requirement = build_requirement()
        provider = authority.validate_rule(
            authority.resolve_rule(requirement)
        )
        authority.require_shared_authority(consumer, (provider,))
        require_provider_shape(
            provider,
            requirement=requirement,
            glossary_keys=glossary_keys,
            expected_block_sha256=provider_spec[4],
        )
        if (
            type(provider) is not rule_receipt_type
            or provider.receipt.authority_digest
            != consumer.receipt.authority_digest
        ):
            raise BuckCompileError(
                "Buck consumer and provider belong to different authority views"
            )

        records = (
            new_record(
                authority,
                carrier,
                ordinal=0,
                field_name=local_keys[0],
                source_text=action,
            ),
            new_record(
                authority,
                carrier,
                ordinal=1,
                field_name=local_keys[1],
                source_text=description,
            ),
        )
        dependencies = build_dependencies()
        projection = {
            "family": "buck",
            "mechanicType": "buck",
            "sourceId": source_id,
            "locator": carrier.locator,
            "actionCost": action,
            "save": {"type": "reflex", "dc": dc},
            "printedPage": printed_page,
            "source": consumer.receipt.as_serialized(),
            "records": [
                record_projection(record)
                for record in records
            ],
            "providerRule": provider.as_serialized(),
            "deferredMechanics": [
                dependency.as_serialized()
                for dependency in dependencies
            ],
            "runtimeStatus": "deferred",
            "contractProof": {
                "schema": 1,
                "sha256": fingerprint,
                "providerCount": 1,
                "deferralCount": len(dependency_specs),
            },
        }
        return (
            consumer,
            provider,
            records,
            dependencies,
            dc,
            projection,
        )

    def validate_compiled(
        value: object,
    ) -> tuple[
        VerifiedSourceSelection,
        VerifiedRuleReceipt,
        tuple[BuckSourceRecord, BuckSourceRecord],
        tuple[DeferredBuckDependency, ...],
        int,
        dict[str, Any],
    ]:
        if type(value) is not compiled_type:
            raise TypeError(
                "Buck projection requires an exact CompiledBuck"
            )
        try:
            authority = value._authority
            consumer_receipt = value._consumer_receipt
            stored_projection = value._projection
        except AttributeError as failure:
            raise BuckCompileError(
                "Buck compiled capability is incomplete"
            ) from failure
        if (
            type(authority) is not authority_type
            or type(consumer_receipt) is not receipt_type
        ):
            raise BuckCompileError("Buck compiled capability is forged")
        derived = derive(authority, consumer_receipt)
        expected = derived[-1]
        actual = thaw_json(stored_projection)
        if projection_bytes(actual) != projection_bytes(expected):
            raise BuckCompileError(
                "Buck compiled capability projection is stale"
            )
        return derived

    def compile_buck(
        authority: object,
        consumer_receipt: object,
        /,
    ) -> CompiledBuck:
        """Reload, rederive, and compile one exact local Buck shorthand."""

        derived = derive(authority, consumer_receipt)
        consumer = derived[0]
        projection = derived[-1]
        result = object.__new__(compiled_type)
        object.__setattr__(result, "_authority", authority)
        object.__setattr__(
            result,
            "_consumer_receipt",
            consumer.receipt,
        )
        object.__setattr__(
            result,
            "_projection",
            freeze_json(projection),
        )
        return result

    def compiled_source_id(value: CompiledBuck) -> str:
        consumer = validate_compiled(value)[0]
        return consumer.address.source_id

    def compiled_locator(value: CompiledBuck) -> str:
        consumer = validate_compiled(value)[0]
        return consumer.address.locator

    def compiled_action_cost(value: CompiledBuck) -> str:
        projection = validate_compiled(value)[-1]
        return projection["actionCost"]

    def compiled_reflex_dc(value: CompiledBuck) -> int:
        return validate_compiled(value)[4]

    def compiled_printed_page(value: CompiledBuck) -> int:
        validate_compiled(value)
        return printed_page

    def compiled_source_receipt(value: CompiledBuck) -> SourceReceipt:
        return validate_compiled(value)[0].receipt

    def compiled_records(
        value: CompiledBuck,
    ) -> tuple[BuckSourceRecord, BuckSourceRecord]:
        return validate_compiled(value)[2]

    def compiled_provider_rule(value: CompiledBuck) -> VerifiedRuleReceipt:
        return validate_compiled(value)[1]

    def compiled_dependencies(
        value: CompiledBuck,
    ) -> tuple[DeferredBuckDependency, ...]:
        return validate_compiled(value)[3]

    def compiled_projection(value: CompiledBuck) -> dict[str, Any]:
        return validate_compiled(value)[-1]

    return (
        compile_buck,
        record_field_name,
        record_source_text,
        record_receipt,
        record_projection,
        compiled_source_id,
        compiled_locator,
        compiled_action_cost,
        compiled_reflex_dc,
        compiled_printed_page,
        compiled_source_receipt,
        compiled_records,
        compiled_provider_rule,
        compiled_dependencies,
        compiled_projection,
    )


(
    compile_buck,
    _record_field_name,
    _record_source_text,
    _record_receipt,
    _record_projection,
    _compiled_source_id,
    _compiled_locator,
    _compiled_action_cost,
    _compiled_reflex_dc,
    _compiled_printed_page,
    _compiled_source_receipt,
    _compiled_records,
    _compiled_provider_rule,
    _compiled_dependencies,
    _compiled_projection,
) = _bind_reviewed_contract()
BuckSourceRecord.field_name = property(_record_field_name)
BuckSourceRecord.source_text = property(_record_source_text)
BuckSourceRecord.receipt = property(_record_receipt)
BuckSourceRecord.as_serialized = _record_projection
CompiledBuck.source_id = property(_compiled_source_id)
CompiledBuck.locator = property(_compiled_locator)
CompiledBuck.action_cost = property(_compiled_action_cost)
CompiledBuck.reflex_dc = property(_compiled_reflex_dc)
CompiledBuck.printed_page = property(_compiled_printed_page)
CompiledBuck.source_receipt = property(_compiled_source_receipt)
CompiledBuck.records = property(_compiled_records)
CompiledBuck.provider_rule = property(_compiled_provider_rule)
CompiledBuck.dependencies = property(_compiled_dependencies)
CompiledBuck.as_serialized = _compiled_projection


__all__ = [
    "BUCK_DEPENDENCIES",
    "BUCK_GLOSSARY_RULE",
    "BuckCompileError",
    "BuckSourceRecord",
    "CompiledBuck",
    "DeferredBuckDependency",
    "FAMILY_ID",
    "GLOSSARY_LOCATOR",
    "GLOSSARY_PRINTED_PAGE",
    "MAX_BUCK_DC",
    "MAX_BUCK_SOURCE_BYTES",
    "MECHANIC_TYPE",
    "compile_buck",
]

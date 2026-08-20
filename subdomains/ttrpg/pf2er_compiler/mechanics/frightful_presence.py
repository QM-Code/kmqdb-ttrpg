"""Compile the reviewed Monster Core Frightful Presence shorthand.

This family is deliberately compile-only. It requires exact, shared-authority
addresses for both the creature production and its reviewed glossary provider,
but the encounter engine does not yet implement first-entry Aura processing.
Consequently this module emits an immutable, explicitly deferred artifact and
uses a local fragment type that the runtime registry cannot mount.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, Literal, final

from .contracts import (
    AbilitySource,
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    SerializedObject,
)
from .source_authority import (
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceAddress,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
)


FRIGHTFUL_PRESENCE_MECHANIC_TYPE = "first-entry-saving-throw-aura"
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))

DeferralPhase = Literal["runtime"]
DeferralRelation = Literal["aura-entry"]


def _require_key(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    return value


def _parse_source_integer(value: object) -> int | None:
    if (
        type(value) is not str
        or not value
        or value[0] == "0"
        or any(character not in "0123456789" for character in value)
        or len(value) > 19
        or (
            len(value) == 19
            and value > "9223372036854775807"
        )
    ):
        return None
    return int(value)


def _freeze_json(value: Any) -> Any:
    active: set[int] = set()
    visited = 0

    def visit(item: Any, depth: int) -> Any:
        nonlocal visited
        visited += 1
        if (
            depth > 32
            or visited > 4_096
        ):
            raise ValueError(
                "Frightful Presence mechanic exceeds its structural bound"
            )
        if type(item) is dict:
            identity = id(item)
            if identity in active:
                raise ValueError(
                    "Frightful Presence mechanic cannot contain cycles"
                )
            active.add(identity)
            try:
                frozen: dict[str, Any] = {}
                for key, child in dict.items(item):
                    if type(key) is not str:
                        raise TypeError(
                            "Frightful Presence mechanic keys must be "
                            "strings"
                        )
                    frozen[key] = visit(child, depth + 1)
                return MappingProxyType(frozen)
            finally:
                active.remove(identity)
        if type(item) in (list, tuple):
            identity = id(item)
            if identity in active:
                raise ValueError(
                    "Frightful Presence mechanic cannot contain cycles"
                )
            active.add(identity)
            try:
                return tuple(
                    visit(child, depth + 1)
                    for child in item
                )
            finally:
                active.remove(identity)
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError(
                    "Frightful Presence mechanic numbers must be finite"
                )
            return item
        if type(item) is int:
            if item < -(1 << 63) or item > (1 << 63) - 1:
                raise ValueError(
                    "Frightful Presence mechanic integers must fit "
                    "signed-64"
                )
            return item
        if item is None or type(item) in (bool, str):
            return item
        raise TypeError(
            "Frightful Presence mechanic value is not JSON-compatible: "
            f"{type(item).__name__}"
        )

    return visit(value, 0)


def _thaw_json(value: Any) -> Any:
    if type(value) is _MAPPING_PROXY_TYPE:
        return {key: _thaw_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw_json(item) for item in value]
    if value is not None and type(value) not in (bool, int, float, str):
        raise TypeError(
            "Frightful Presence mechanic contains an untrusted value"
        )
    return value

def _patch_validation_gateway() -> tuple[
    Callable[[Callable[[object], None]], None],
    Callable[[object], None],
]:
    validator: Callable[[object], None] | None = None

    def bind(value: Callable[[object], None]) -> None:
        nonlocal validator
        if validator is not None:
            raise RuntimeError(
                "Frightful Presence patch validator is already bound"
            )
        validator = value

    def validate(value: object) -> None:
        if validator is None:
            raise RuntimeError(
                "Frightful Presence patch validator is not bound"
            )
        validator(value)

    return bind, validate


_bind_patch_validator, _bound_patch_validator = (
    _patch_validation_gateway()
)
del _patch_validation_gateway


def _patch_validation_method(
    validator: Callable[[object], None],
) -> Callable[[object], None]:
    def validate(value: object) -> None:
        validator(value)

    return validate


_validate_patch_method = _patch_validation_method(
    _bound_patch_validator
)
del _patch_validation_method
del _bound_patch_validator


def _late_validation_method(
    label: str,
) -> tuple[Callable[[Callable[[object], None]], None], Callable[[object], None]]:
    validator: Callable[[object], None] | None = None

    def bind(value: Callable[[object], None]) -> None:
        nonlocal validator
        if validator is not None:
            raise RuntimeError(f"{label} validator is already bound")
        validator = value

    def validate(value: object) -> None:
        if validator is None:
            raise RuntimeError(f"{label} validator is not bound")
        validator(value)

    return bind, validate


_bind_deferral_validator, _deferral_validation_method = (
    _late_validation_method("Frightful Presence deferral")
)
_bind_receipt_validator, _receipt_validation_method = (
    _late_validation_method("Frightful Presence receipt")
)
del _late_validation_method


def _validated_method_contract(
    validator: Callable[[object], None],
    *dependencies: object,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Bind authorization and implementation dependencies to one method."""

    def decorate(method: Callable[..., Any]) -> Callable[..., Any]:
        def validated(
            instance: object,
            *args: object,
            **kwargs: object,
        ) -> Any:
            validator(instance)
            return method(
                instance,
                *dependencies,
                *args,
                **kwargs,
            )

        return validated

    return decorate


_deferral_public_method = _validated_method_contract(
    _deferral_validation_method
)


@final
@dataclass(frozen=True, slots=True)
class FrightfulPresenceDeferral:
    """One typed contract that blocks runtime registration."""

    dependency_id: str
    phase: DeferralPhase
    relation: DeferralRelation
    required_contract: str

    def __post_init__(self) -> None:
        if type(self) is not FrightfulPresenceDeferral:
            raise TypeError(
                "FrightfulPresenceDeferral subclasses are not supported"
            )
        values = tuple(
            object.__getattribute__(self, field_name)
            for field_name in (
                "dependency_id",
                "phase",
                "relation",
                "required_contract",
            )
        )
        if any(type(value) is not str for value in values):
            raise TypeError(
                "FrightfulPresenceDeferral fields must be exact strings"
            )
        for field_name in ("dependency_id", "required_contract"):
            _require_key(
                object.__getattribute__(self, field_name),
                f"FrightfulPresenceDeferral.{field_name}",
            )
        if object.__getattribute__(self, "phase") != "runtime":
            raise ValueError(
                "FrightfulPresenceDeferral.phase is invalid"
            )
        if object.__getattribute__(self, "relation") != "aura-entry":
            raise ValueError(
                "FrightfulPresenceDeferral.relation is invalid"
            )

    @_deferral_public_method
    def as_serialized(self) -> SerializedObject:
        return {
            "id": object.__getattribute__(self, "dependency_id"),
            "phase": object.__getattribute__(self, "phase"),
            "relation": object.__getattribute__(self, "relation"),
            "requiredContract": object.__getattribute__(self, "required_contract"),
            "status": "deferred",
            "blocks": "registry-activation",
        }


del _deferral_public_method


def _validate_deferral(
    deferral: object,
) -> None:
    if type(deferral) is not FrightfulPresenceDeferral:
        raise TypeError(
            "Frightful Presence deferrals must have the exact typed contract"
        )
    try:
        values = (
            object.__getattribute__(deferral, "dependency_id"),
            object.__getattribute__(deferral, "phase"),
            object.__getattribute__(deferral, "relation"),
            object.__getattribute__(deferral, "required_contract"),
        )
    except (AttributeError, TypeError) as error:
        raise TypeError(
            "Frightful Presence deferral is incomplete"
        ) from error
    if any(type(value) is not str for value in values):
        raise TypeError(
            "Frightful Presence deferral fields must be exact strings"
        )
    if values != (
        "aura-entry-runtime",
        "runtime",
        "aura-entry",
        (
            "first-entry emanation detection, Will save resolution, "
            "frightened state, and source-scoped temporary immunity"
        ),
    ):
        raise ValueError(
            "Frightful Presence deferral is not a reviewed dependency"
        )


_bind_deferral_validator(_validate_deferral)
del _bind_deferral_validator
del _deferral_validation_method


_receipt_public_method = _validated_method_contract(
    _receipt_validation_method
)


@final
@dataclass(frozen=True, slots=True, init=False)
class FrightfulPresenceRuleReceipt:
    """The exact reviewed Monster Core glossary provider."""

    rule_id: str
    source_id: str
    locator: str
    source_ordinal: int
    ordered_rule_sha256: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "FrightfulPresenceRuleReceipt must be created by its factory"
        )

    @_receipt_public_method
    def as_serialized(self) -> SerializedObject:
        return {
            "ruleId": object.__getattribute__(self, "rule_id"),
            "sourceId": object.__getattribute__(self, "source_id"),
            "locator": object.__getattribute__(self, "locator"),
            "sourceOrdinal": object.__getattribute__(self, "source_ordinal"),
            "orderedRuleSha256": object.__getattribute__(self, "ordered_rule_sha256"),
        }


del _receipt_public_method


_PROVIDER_FIELDS = (
    "core-mc1:ability-glossary#^.ability[014]",
    "core-mc1",
    "359.6",
    14,
    "db722797edaec1846d9863704ca5108d9c668cc6cec02bcd5bb11146ee88ce24",
)


def _new_rule_receipt(
    *,
    rule_id: str,
    source_id: str,
    locator: str,
    source_ordinal: int,
    ordered_rule_sha256: str,
) -> FrightfulPresenceRuleReceipt:
    receipt = object.__new__(FrightfulPresenceRuleReceipt)
    object.__setattr__(receipt, "rule_id", rule_id)
    object.__setattr__(receipt, "source_id", source_id)
    object.__setattr__(receipt, "locator", locator)
    object.__setattr__(receipt, "source_ordinal", source_ordinal)
    object.__setattr__(
        receipt,
        "ordered_rule_sha256",
        ordered_rule_sha256,
    )
    _validate_rule_receipt(receipt, require_provider=False)
    return receipt


def _validate_rule_receipt(
    receipt: object,
    *,
    require_provider: bool,
) -> None:
    if type(receipt) is not FrightfulPresenceRuleReceipt:
        raise TypeError(
            "Frightful Presence provider must be an exact receipt"
        )
    try:
        values = (
            object.__getattribute__(receipt, "rule_id"),
            object.__getattribute__(receipt, "source_id"),
            object.__getattribute__(receipt, "locator"),
            object.__getattribute__(receipt, "source_ordinal"),
            object.__getattribute__(receipt, "ordered_rule_sha256"),
        )
    except (AttributeError, TypeError) as error:
        raise TypeError(
            "Frightful Presence provider receipt is incomplete"
        ) from error
    for field_name, value in zip(
        ("rule_id", "source_id", "locator"),
        values[:3],
        strict=True,
    ):
        _require_key(
            value,
            f"FrightfulPresenceRuleReceipt.{field_name}",
        )
    source_ordinal = values[3]
    if (
        type(source_ordinal) is not int
        or source_ordinal < 0
        or source_ordinal > (1 << 63) - 1
    ):
        raise ValueError(
            "FrightfulPresenceRuleReceipt.source_ordinal must be a "
            "signed-64 nonnegative integer"
        )
    digest = values[4]
    if (
        type(digest) is not str
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(
            "FrightfulPresenceRuleReceipt.ordered_rule_sha256 must be "
            "a lowercase SHA-256 digest"
        )
    if require_provider and values != (
        "core-mc1:ability-glossary#^.ability[014]",
        "core-mc1",
        "359.6",
        14,
        "db722797edaec1846d9863704ca5108d9c668cc6cec02bcd5bb11146ee88ce24",
    ):
        raise ValueError(
            "Frightful Presence patch has the wrong glossary provider"
        )


def _public_receipt_contract(
    structural_validator: Callable[..., None],
) -> Callable[[object], None]:
    def validate(receipt: object) -> None:
        structural_validator(receipt, require_provider=True)

    return validate


_bind_receipt_validator(
    _public_receipt_contract(_validate_rule_receipt)
)
del _bind_receipt_validator
del _receipt_validation_method
del _public_receipt_contract


FRIGHTFUL_PRESENCE_RULE = _new_rule_receipt(
    rule_id=_PROVIDER_FIELDS[0],
    source_id=_PROVIDER_FIELDS[1],
    locator=_PROVIDER_FIELDS[2],
    source_ordinal=_PROVIDER_FIELDS[3],
    ordered_rule_sha256=_PROVIDER_FIELDS[4],
)

def _new_rule_requirement() -> RuleRequirement:
    return RuleRequirement(
        rule_id="core-mc1:ability-glossary#^.ability[014]",
        source_id="core-mc1",
        locator="358.2",
        carrier_path=(RawMemberStep("^.ability", 16),),
        expected_value_sha256=(
            "0b12b73e5bed46f72f225f50048136f6871b4cc051ec2cf0ea1d956915e7dc92"
        ),
    )


FRIGHTFUL_PRESENCE_RULE_REQUIREMENT = _new_rule_requirement()


def _mechanic_for_structure(
    radius_feet: int,
    save_dc: int,
    freeze_json: Callable[[Any], Any],
) -> Mapping[str, Any]:
    if (
        type(radius_feet) is not int
        or radius_feet <= 0
        or radius_feet > (1 << 63) - 1
        or radius_feet % 5
        or type(save_dc) is not int
        or save_dc <= 0
        or save_dc > (1 << 63) - 1
    ):
        raise ValueError(
            "Frightful Presence mechanic has invalid radius or DC"
        )
    mechanic = {
        "type": "first-entry-saving-throw-aura",
        "geometry": "emanation",
        "radiusFeet": radius_feet,
        "sourceAffected": False,
        "alliesAffectedByDefault": True,
        "trigger": "first-entry",
        "savingThrow": {
            "type": "will",
            "dc": save_dc,
        },
        "incapacitation": False,
        "outcomes": {
            "critical-success": {
                "frightened": 0,
                "temporaryImmunity": True,
            },
            "success": {
                "frightened": 1,
                "temporaryImmunity": True,
            },
            "failure": {
                "frightened": 2,
                "temporaryImmunity": True,
            },
            "critical-failure": {
                "frightened": 4,
                "temporaryImmunity": True,
            },
        },
        "temporaryImmunity": {
            "abilityId": "frightful-presence",
            "scope": "source-participant-ability",
            "duration": {
                "unit": "rounds",
                "value": 10,
                "decrementAt": {
                    "participant": "source",
                    "phase": "start-turn",
                },
            },
        },
        "rules": {
            "frightfulPresence": {
                "ruleId": "core-mc1:ability-glossary#^.ability[014]",
                "sourceId": "core-mc1",
                "locator": "359.6",
                "sourceOrdinal": 14,
                "orderedRuleSha256": (
                    "db722797edaec1846d9863704ca5108d9c668cc6cec02bcd5"
                    "bb11146ee88ce24"
                ),
            },
            **{
                name: {"sourceId": source_id, "locator": locator}
                for name, source_id, locator in (
                    ("traitGlossary", "core-pc1", "452.1"),
                    ("emanation", "core-pc1", "428.4"),
                    ("gridMovement", "core-pc1", "421.5"),
                    ("diagonalMovement", "core-pc1", "421.6"),
                    ("stride", "core-pc1", "418.3"),
                    ("immunity", "core-pc1", "408.2"),
                    ("willAndDefenses", "core-pc1", "404.1"),
                    ("degreeOfSuccess", "core-pc1", "401.4"),
                    ("statusPenalties", "core-pc1", "400.2"),
                    ("duplicateEffects", "core-pc1", "399.1"),
                    ("duration", "core-pc1", "426.2"),
                    ("conditions", "core-pc1", "442.1"),
                    ("frightened", "core-pc1", "444.4"),
                    ("startTurn", "core-pc1", "435.8"),
                    ("endTurn", "core-pc1", "436.3"),
                )
            },
        },
    }
    return freeze_json(mechanic)


def _mechanic_contract(
    structural_builder: Callable[..., Mapping[str, Any]],
    freeze_json: Callable[[Any], Any],
) -> Callable[[int, int], Mapping[str, Any]]:
    def build(
        radius_feet: int,
        save_dc: int,
    ) -> Mapping[str, Any]:
        return structural_builder(
            radius_feet,
            save_dc,
            freeze_json,
        )

    return build


_mechanic_for = _mechanic_contract(
    _mechanic_for_structure,
    _freeze_json,
)
del _mechanic_contract


def _mechanic_method(
    builder: Callable[[int, int], Mapping[str, Any]],
) -> Callable[[object], Mapping[str, Any]]:
    def build(value: object) -> Mapping[str, Any]:
        return builder(
            object.__getattribute__(value, "_radius_feet"),
            object.__getattribute__(value, "_save_dc"),
        )

    return build


_canonical_mechanic_method = _mechanic_method(_mechanic_for)
del _mechanic_method


def _thaw_method(
    thaw_json: Callable[[Any], Any],
) -> Callable[[object, Any], Any]:
    def thaw(_value: object, frozen: Any) -> Any:
        return thaw_json(frozen)

    return thaw


_canonical_thaw_method = _thaw_method(_thaw_json)
del _thaw_method


_patch_public_method = _validated_method_contract(
    _validate_patch_method,
    _canonical_mechanic_method,
    _canonical_thaw_method,
    FrightfulPresenceRuleReceipt.as_serialized,
    FrightfulPresenceDeferral.as_serialized,
)


@final
@dataclass(frozen=True, slots=True, init=False)
class FrightfulPresenceCompilerPatch:
    """One non-executable compile artifact awaiting verified adaptation."""

    _source: AbilitySource = field(repr=False, compare=False)
    _authority: SourceAuthorityAdapter = field(
        repr=False,
        compare=False,
    )
    _consumer_selection: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )
    _provider_rule: VerifiedRuleReceipt = field(
        repr=False,
        compare=False,
    )
    _radius_feet: int
    _save_dc: int
    consumer_receipt: SourceReceipt
    provider_source_receipt: SourceReceipt
    provider: FrightfulPresenceRuleReceipt
    traits: tuple[str, ...]
    deferrals: tuple[FrightfulPresenceDeferral, ...]
    runtime_ready: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "FrightfulPresenceCompilerPatch must be created by "
            "compile_frightful_presence()"
        )

    @property
    @_patch_public_method
    def mechanic(
        self,
        canonical_mechanic: Callable[[object], Mapping[str, Any]],
        _canonical_thaw: Callable[[object, Any], Any],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_deferral: Callable[[object], SerializedObject],
    ) -> Mapping[str, Any]:
        return canonical_mechanic(self)

    @property
    @_patch_public_method
    def mechanic_type(
        self,
        _canonical_mechanic: Callable[[object], Mapping[str, Any]],
        _canonical_thaw: Callable[[object, Any], Any],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_deferral: Callable[[object], SerializedObject],
    ) -> str:
        return "first-entry-saving-throw-aura"

    @_patch_public_method
    def as_serialized(
        self,
        canonical_mechanic: Callable[[object], Mapping[str, Any]],
        canonical_thaw: Callable[[object, Any], Any],
        serialize_provider: Callable[[object], SerializedObject],
        serialize_deferral: Callable[[object], SerializedObject],
    ) -> SerializedObject:
        consumer_receipt = object.__getattribute__(self, "consumer_receipt")
        provider_receipt = object.__getattribute__(self, "provider_source_receipt")
        consumer_address = object.__getattribute__(consumer_receipt, "address")
        provider = object.__getattribute__(self, "provider")
        return {
            "supportState": "compile-only",
            "runtimeReady": False,
            "mechanic": canonical_thaw(
                self,
                canonical_mechanic(self),
            ),
            "consumer": {
                "sourceId": object.__getattribute__(consumer_address, "source_id"),
                "locator": object.__getattribute__(consumer_address, "locator"),
                "receiptDigest": consumer_receipt.digest,
            },
            "provider": {
                **serialize_provider(provider),
                "receiptDigest": provider_receipt.digest,
            },
            "traits": list(object.__getattribute__(self, "traits")),
            "deferrals": [
                serialize_deferral(deferral)
                for deferral in object.__getattribute__(self, "deferrals")
            ],
        }

    @property
    @_patch_public_method
    def consumer(
        self,
        _canonical_mechanic: Callable[[object], Mapping[str, Any]],
        _canonical_thaw: Callable[[object, Any], Any],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_deferral: Callable[[object], SerializedObject],
    ) -> SourceReceipt:
        return object.__getattribute__(self, "consumer_receipt")

    @property
    @_patch_public_method
    def verified_provider(
        self,
        _canonical_mechanic: Callable[[object], Mapping[str, Any]],
        _canonical_thaw: Callable[[object, Any], Any],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_deferral: Callable[[object], SerializedObject],
    ) -> SourceReceipt:
        return object.__getattribute__(self, "provider_source_receipt")

    @property
    @_patch_public_method
    def deferred_mechanics(
        self,
        _canonical_mechanic: Callable[[object], Mapping[str, Any]],
        _canonical_thaw: Callable[[object, Any], Any],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_deferral: Callable[[object], SerializedObject],
    ) -> tuple[str, ...]:
        return tuple(
            deferral.dependency_id
            for deferral in object.__getattribute__(self, "deferrals")
        )


del _patch_public_method
del _validated_method_contract
del _canonical_mechanic_method
del _canonical_thaw_method


def _new_patch_structure(
    *,
    source: AbilitySource,
    authority: SourceAuthorityAdapter,
    consumer_selection: VerifiedSourceSelection,
    provider_rule: VerifiedRuleReceipt,
    radius_feet: int,
    save_dc: int,
    traits: tuple[str, ...],
    new_rule_receipt: Callable[..., FrightfulPresenceRuleReceipt],
    validate_patch: Callable[[object], None],
) -> FrightfulPresenceCompilerPatch:
    patch = object.__new__(FrightfulPresenceCompilerPatch)
    object.__setattr__(patch, "_source", source)
    object.__setattr__(patch, "_authority", authority)
    object.__setattr__(
        patch,
        "_consumer_selection",
        consumer_selection,
    )
    object.__setattr__(patch, "_provider_rule", provider_rule)
    object.__setattr__(patch, "_radius_feet", radius_feet)
    object.__setattr__(patch, "_save_dc", save_dc)
    object.__setattr__(
        patch,
        "consumer_receipt",
        consumer_selection.receipt,
    )
    object.__setattr__(
        patch,
        "provider_source_receipt",
        provider_rule.receipt,
    )
    object.__setattr__(
        patch,
        "provider",
        new_rule_receipt(
            rule_id="core-mc1:ability-glossary#^.ability[014]",
            source_id="core-mc1",
            locator="359.6",
            source_ordinal=14,
            ordered_rule_sha256=(
                "db722797edaec1846d9863704ca5108d9c668cc6cec02bcd5"
                "bb11146ee88ce24"
            ),
        ),
    )
    object.__setattr__(patch, "traits", traits)
    object.__setattr__(
        patch,
        "deferrals",
        (
            FrightfulPresenceDeferral(
                dependency_id="aura-entry-runtime",
                phase="runtime",
                relation="aura-entry",
                required_contract=(
                    "first-entry emanation detection, Will save resolution, "
                    "frightened state, and source-scoped temporary immunity"
                ),
            ),
        ),
    )
    object.__setattr__(patch, "runtime_ready", False)
    validate_patch(patch)
    return patch


def _new_patch_contract(
    structural_factory: Callable[..., FrightfulPresenceCompilerPatch],
    new_rule_receipt: Callable[..., FrightfulPresenceRuleReceipt],
    validate_patch: Callable[[object], None],
) -> Callable[..., FrightfulPresenceCompilerPatch]:
    def create(
        *,
        source: AbilitySource,
        authority: SourceAuthorityAdapter,
        consumer_selection: VerifiedSourceSelection,
        provider_rule: VerifiedRuleReceipt,
        radius_feet: int,
        save_dc: int,
        traits: tuple[str, ...],
    ) -> FrightfulPresenceCompilerPatch:
        return structural_factory(
            source=source,
            authority=authority,
            consumer_selection=consumer_selection,
            provider_rule=provider_rule,
            radius_feet=radius_feet,
            save_dc=save_dc,
            traits=traits,
            new_rule_receipt=new_rule_receipt,
            validate_patch=validate_patch,
        )

    return create


_new_patch = _new_patch_contract(
    _new_patch_structure,
    _new_rule_receipt,
    _validate_patch_method,
)
del _new_patch_contract
del _validate_patch_method


def _validate_patch_structure(
    patch: object,
    mechanic_for: Callable[[int, int], Mapping[str, Any]],
    verified_parameters: Callable[
        [object, object, object, object],
        tuple[
            int,
            int,
            tuple[str, ...],
            SourceReceipt,
            SourceReceipt,
        ] | None,
    ],
    validate_rule_receipt: Callable[..., None],
    validate_deferral: Callable[[object], None],
) -> None:
    if type(patch) is not FrightfulPresenceCompilerPatch:
        raise TypeError(
            "Frightful Presence result must be an exact compiler patch"
        )
    try:
        source = object.__getattribute__(patch, "_source")
        authority = object.__getattribute__(patch, "_authority")
        consumer_selection = object.__getattribute__(
            patch,
            "_consumer_selection",
        )
        provider_rule = object.__getattribute__(patch, "_provider_rule")
        radius_feet = object.__getattribute__(patch, "_radius_feet")
        save_dc = object.__getattribute__(patch, "_save_dc")
        consumer_receipt = object.__getattribute__(patch, "consumer_receipt")
        provider_source_receipt = object.__getattribute__(
            patch,
            "provider_source_receipt",
        )
        provider = object.__getattribute__(patch, "provider")
        traits = object.__getattribute__(patch, "traits")
        deferrals = object.__getattribute__(patch, "deferrals")
        runtime_ready = object.__getattribute__(patch, "runtime_ready")
    except (AttributeError, TypeError) as error:
        raise TypeError(
            "Frightful Presence compiler patch is incomplete"
        ) from error
    mechanic_for(radius_feet, save_dc)
    verified = verified_parameters(
        source,
        consumer_selection,
        provider_rule,
        authority,
    )
    if verified is None:
        raise ValueError(
            "Frightful Presence patch is not backed by its authority"
        )
    (
        verified_radius,
        verified_dc,
        verified_traits,
        fresh_consumer_receipt,
        fresh_provider_receipt,
    ) = verified
    if (
        radius_feet != verified_radius
        or save_dc != verified_dc
        or traits != verified_traits
    ):
        raise ValueError(
            "Frightful Presence patch disagrees with verified source"
        )
    if (
        type(consumer_receipt) is not SourceReceipt
        or type(provider_source_receipt) is not SourceReceipt
        or consumer_receipt.as_serialized()
        != fresh_consumer_receipt.as_serialized()
        or provider_source_receipt.as_serialized()
        != fresh_provider_receipt.as_serialized()
    ):
        raise ValueError(
            "Frightful Presence patch receipts disagree with authority"
        )
    validate_rule_receipt(provider, require_provider=True)
    if (
        type(traits) is not tuple
        or any(type(trait) is not str for trait in traits)
        or traits not in (
            ("aura", "emotion", "fear", "mental"),
            ("aura", "divine", "emotion", "fear", "mental"),
        )
    ):
        raise ValueError(
            "Frightful Presence patch has unsupported traits"
        )
    if (
        type(deferrals) is not tuple
        or len(deferrals) != 1
        or any(
            type(deferral) is not FrightfulPresenceDeferral
            for deferral in deferrals
        )
    ):
        raise ValueError(
            "Frightful Presence patch has incomplete deferrals"
        )
    for deferral in deferrals:
        validate_deferral(deferral)
    if tuple(
        object.__getattribute__(deferrals[0], field_name)
        for field_name in (
            "dependency_id",
            "phase",
            "relation",
            "required_contract",
        )
    ) != (
        "aura-entry-runtime",
        "runtime",
        "aura-entry",
        (
            "first-entry emanation detection, Will save resolution, "
            "frightened state, and source-scoped temporary immunity"
        ),
    ):
        raise ValueError(
            "Frightful Presence patch has incorrect deferrals"
        )
    if type(runtime_ready) is not bool or runtime_ready is not False:
        raise ValueError(
            "Frightful Presence cannot claim runtime readiness"
        )


def _description_numbers(
    value: str,
) -> tuple[str, str, str] | None:
    body = value[:-1] if value.endswith(".") else value
    radius, radius_separator, remainder = body.partition(
        " feet, DC "
    )
    if not radius_separator:
        return None
    save_dc, dc_separator, page_clause = remainder.partition(
        " (page "
    )
    if (
        not dc_separator
        or not page_clause.endswith(")")
    ):
        return None
    page = page_clause[:-1]
    for number in (radius, save_dc, page):
        if (
            not number
            or number[0] == "0"
            or any(
                character not in "0123456789"
                for character in number
            )
        ):
            return None
    return radius, save_dc, page


def _inline_description_contract(
    description_numbers: Callable[
        [str],
        tuple[str, str, str] | None,
    ],
) -> Callable[
    [str],
    tuple[
        tuple[str, ...] | None,
        tuple[str, str, str] | None,
    ],
]:
    def parse(
        value: str,
    ) -> tuple[
        tuple[str, ...] | None,
        tuple[str, str, str] | None,
    ]:
        candidates = (
            (
                ("aura", "emotion", "fear", "mental"),
                "(aura, emotion, fear, mental) ",
            ),
            (
                ("aura", "divine", "emotion", "fear", "mental"),
                "(aura, divine, emotion, fear, mental) ",
            ),
        )
        for traits, prefix in candidates:
            if value.startswith(prefix):
                return traits, description_numbers(value[len(prefix):])
        return None, None

    return parse


_inline_description = _inline_description_contract(_description_numbers)
del _inline_description_contract


def _source_match_structure(
    source: object,
    description_numbers: Callable[
        [str],
        tuple[str, str, str] | None,
    ],
    inline_description: Callable[
        [str],
        tuple[
            tuple[str, ...] | None,
            tuple[str, str, str] | None,
        ],
    ],
) -> tuple[
    tuple[str, str, str],
    tuple[str, ...],
    str,
    str,
    str,
    None,
    str,
    str,
    str,
    RawSourceMember,
] | None:
    if type(source) is not AbilitySource:
        return None
    try:
        source_label = object.__getattribute__(source, "source_label")
        action_cost = object.__getattribute__(source, "action_cost")
        kind = object.__getattribute__(source, "kind")
        source_traits = object.__getattribute__(source, "traits")
        trigger = object.__getattribute__(source, "trigger")
        normalized_description = object.__getattribute__(source, "description")
        source_id = object.__getattribute__(source, "source_id")
        locator = object.__getattribute__(source, "locator")
        creature_name = object.__getattribute__(source, "creature_name")
        raw_member = object.__getattribute__(source, "raw_member")
    except (AttributeError, TypeError):
        return None
    if (
        any(
            type(value) is not str
            for value in (
                source_label,
                kind,
                trigger,
                normalized_description,
                source_id,
                locator,
                creature_name,
            )
        )
        or action_cost is not None
        or type(source_traits) is not tuple
        or any(type(trait) is not str for trait in source_traits)
        or type(raw_member) is not RawSourceMember
    ):
        return None
    try:
        raw_key = object.__getattribute__(raw_member, "key")
        raw_value = object.__getattribute__(raw_member, "value")
    except (AttributeError, TypeError):
        return None
    if (
        type(raw_key) is not str
        or raw_key != "!.Frightful Presence"
    ):
        return None

    normalized_traits: tuple[str, ...]
    if type(raw_value) is RawSourceObject:
        try:
            raw_members = object.__getattribute__(raw_value, "members")
        except (AttributeError, TypeError):
            return None
        if (
            type(raw_members) is not tuple
            or len(raw_members) != 2
            or any(
                type(member) is not RawSourceMember
                for member in raw_members
            )
        ):
            return None
        traits_member, description_member = raw_members
        try:
            traits_key = object.__getattribute__(traits_member, "key")
            raw_traits = object.__getattribute__(traits_member, "value")
            description_key = object.__getattribute__(description_member, "key")
            description = object.__getattribute__(description_member, "value")
        except (AttributeError, TypeError):
            return None
        if (
            type(traits_key) is not str
            or traits_key != "Traits"
            or type(description_key) is not str
            or description_key != "Description"
            or type(raw_traits) is not RawSourceArray
            or type(description) is not str
        ):
            return None
        try:
            parsed_traits = object.__getattribute__(raw_traits, "items")
        except (AttributeError, TypeError):
            return None
        if (
            type(parsed_traits) is not tuple
            or any(type(trait) is not str for trait in parsed_traits)
            or parsed_traits not in (
                ("aura", "emotion", "fear", "mental"),
                ("aura", "divine", "emotion", "fear", "mental"),
            )
        ):
            return None
        normalized_traits = parsed_traits
        numbers = description_numbers(description)
    elif type(raw_value) is str:
        description = raw_value
        parsed_traits, numbers = inline_description(description)
        normalized_traits = ()
    else:
        return None
    if (
        numbers is None
        or parsed_traits is None
        or parsed_traits not in (
            ("aura", "emotion", "fear", "mental"),
            ("aura", "divine", "emotion", "fear", "mental"),
        )
        or source_traits != normalized_traits
        or normalized_description != description
    ):
        return None
    return (
        numbers,
        parsed_traits,
        source_id,
        locator,
        source_label,
        action_cost,
        kind,
        trigger,
        creature_name,
        raw_member,
    )


def _source_match_contract(
    structural_parser: Callable[..., object],
    description_numbers: Callable[
        [str],
        tuple[str, str, str] | None,
    ],
    inline_description: Callable[
        [str],
        tuple[
            tuple[str, ...] | None,
            tuple[str, str, str] | None,
        ],
    ],
) -> Callable[[object], object]:
    def parse(source: object) -> object:
        return structural_parser(
            source,
            description_numbers,
            inline_description,
        )

    return parse


_source_match = _source_match_contract(
    _source_match_structure,
    _description_numbers,
    _inline_description,
)
del _source_match_contract


def _unbound_parameters_structure(
    source: object,
    source_match_parser: Callable[[object], object],
    parse_source_integer: Callable[[object], int | None],
) -> tuple[
    int,
    int,
    tuple[str, ...],
    str,
    str,
    str,
    RawSourceMember,
] | None:
    source_match = source_match_parser(source)
    if source_match is None:
        return None
    (
        numbers,
        traits,
        source_id,
        locator,
        source_label,
        action_cost,
        kind,
        trigger,
        creature_name,
        raw_member,
    ) = source_match

    radius_feet = parse_source_integer(numbers[0])
    save_dc = parse_source_integer(numbers[1])
    reference_page = parse_source_integer(numbers[2])
    if (
        radius_feet is None
        or save_dc is None
        or reference_page is None
    ):
        return None
    if (
        radius_feet <= 0
        or radius_feet % 5
        or save_dc <= 0
        or reference_page != 359
    ):
        return None

    # Page 359 is the reviewed core-mc1 glossary production. A full match is
    # intentional: Ancient Horned Dragon currently appends an incomplete
    # Miasma ability after this prefix and must remain rejected.
    if source_id != "core-mc1":
        return None
    if source_label != "Frightful Presence":
        return None
    if (
        action_cost is not None
        or kind != "passive"
        or trigger
    ):
        return None
    return (
        radius_feet,
        save_dc,
        traits,
        source_id,
        locator,
        creature_name,
        raw_member,
    )


def _unbound_parameters_contract(
    structural_parser: Callable[..., object],
    source_match_parser: Callable[[object], object],
    parse_source_integer: Callable[[object], int | None],
) -> Callable[[object], object]:
    def parse(source: object) -> object:
        return structural_parser(
            source,
            source_match_parser,
            parse_source_integer,
        )

    return parse


_unbound_parameters = _unbound_parameters_contract(
    _unbound_parameters_structure,
    _source_match,
    _parse_source_integer,
)
del _unbound_parameters_contract


def _exact_authority_path(value: object) -> bool:
    return type(value) is tuple and all(
        type(step) in (RawMemberStep, RawIndexStep)
        for step in value
    )


def _reviewed_requirement_matches(
    requirement: object,
) -> bool:
    if type(requirement) is not RuleRequirement:
        return False
    try:
        rule_id = object.__getattribute__(requirement, "rule_id")
        source_id = object.__getattribute__(requirement, "source_id")
        locator = object.__getattribute__(requirement, "locator")
        carrier_path = object.__getattribute__(requirement, "carrier_path")
        selection_path = object.__getattribute__(requirement, "selection_path")
        span = object.__getattribute__(requirement, "span")
        expected_block = object.__getattribute__(
            requirement,
            "expected_block_sha256",
        )
        expected_member = object.__getattribute__(
            requirement,
            "expected_member_sha256",
        )
        expected_value = object.__getattribute__(
            requirement,
            "expected_value_sha256",
        )
        expected_selection = object.__getattribute__(
            requirement,
            "expected_selection_sha256",
        )
    except (AttributeError, TypeError):
        return False
    if (
        type(rule_id) is not str
        or type(source_id) is not str
        or type(locator) is not str
        or type(carrier_path) is not tuple
        or len(carrier_path) != 1
        or type(carrier_path[0]) is not RawMemberStep
        or type(object.__getattribute__(carrier_path[0], "raw_key")) is not str
        or type(object.__getattribute__(carrier_path[0], "member_ordinal")) is not int
        or type(selection_path) is not tuple
        or selection_path != ()
        or span is not None
        or expected_block is not None
        or expected_member is not None
        or type(expected_value) is not str
        or expected_selection is not None
    ):
        return False
    return (
        rule_id,
        source_id,
        locator,
        object.__getattribute__(carrier_path[0], "raw_key"),
        object.__getattribute__(carrier_path[0], "member_ordinal"),
        expected_value,
    ) == (
        "core-mc1:ability-glossary#^.ability[014]",
        "core-mc1",
        "358.2",
        "^.ability",
        16,
        "0b12b73e5bed46f72f225f50048136f6871b4cc051ec2cf0ea1d956915e7dc92",
    )


def _resolve_reviewed_provider(
    authority: SourceAuthorityAdapter,
) -> VerifiedRuleReceipt:
    return authority.resolve_rule(
        RuleRequirement(
            rule_id="core-mc1:ability-glossary#^.ability[014]",
            source_id="core-mc1",
            locator="358.2",
            carrier_path=(
                RawMemberStep("^.ability", 16),
            ),
            expected_value_sha256=(
                "0b12b73e5bed46f72f225f50048136f6871b4cc051ec2cf0ea1d"
                "956915e7dc92"
            ),
        )
    )


def _provider_matches_structure(
    provider: object,
    authority: SourceAuthorityAdapter,
    reviewed_requirement_matches: Callable[[object], bool],
    exact_authority_path: Callable[[object], bool],
) -> bool:
    if type(provider) is not VerifiedRuleReceipt:
        return False
    authority.validate_rule(provider)
    if (
        not reviewed_requirement_matches(provider.requirement)
        or type(provider.selection) is not VerifiedSourceSelection
        or type(provider.receipt) is not SourceReceipt
        or type(provider.rule_id) is not str
        or provider.rule_id
        != "core-mc1:ability-glossary#^.ability[014]"
    ):
        return False
    selection = provider.selection
    address = selection.address
    if (
        type(address) is not SourceAddress
        or type(address.source_id) is not str
        or address.source_id != "core-mc1"
        or type(address.locator) is not str
        or address.locator != "358.2"
        or address.span is not None
        or not exact_authority_path(address.target_path)
        or not exact_authority_path(address.carrier_path)
        or not exact_authority_path(address.selection_path)
        or len(address.carrier_path) != 1
        or type(address.carrier_path[0]) is not RawMemberStep
        or type(
            object.__getattribute__(address.carrier_path[0], "raw_key")
        ) is not str
        or type(
            object.__getattribute__(address.carrier_path[0], "member_ordinal")
        ) is not int
        or object.__getattribute__(address.carrier_path[0], "raw_key")
        != "^.ability"
        or object.__getattribute__(address.carrier_path[0], "member_ordinal")
        != 16
        or address.selection_path != ()
        or type(selection.raw_value) is not RawSourceObject
        or selection.selected_value is not selection.raw_value
    ):
        return False
    members = object.__getattribute__(selection.raw_value, "members")
    if (
        type(members) is not tuple
        or any(type(member) is not RawSourceMember for member in members)
    ):
        return False
    names = tuple(
        object.__getattribute__(member, "value")
        for member in members
        if (
            type(object.__getattribute__(member, "key")) is str
            and object.__getattribute__(member, "key") == "Name"
        )
    )
    return (
        len(names) == 1
        and type(names[0]) is str
        and names[0] == "Frightful Presence"
    )


def _provider_matches_contract(
    structural_matcher: Callable[..., bool],
    reviewed_requirement_matches: Callable[[object], bool],
    exact_authority_path: Callable[[object], bool],
) -> Callable[[object, SourceAuthorityAdapter], bool]:
    def matches(
        provider: object,
        authority: SourceAuthorityAdapter,
    ) -> bool:
        return structural_matcher(
            provider,
            authority,
            reviewed_requirement_matches,
            exact_authority_path,
        )

    return matches


_provider_matches = _provider_matches_contract(
    _provider_matches_structure,
    _reviewed_requirement_matches,
    _exact_authority_path,
)
del _provider_matches_contract


def _verified_parameters_structure(
    source: object,
    consumer: object,
    provider: object,
    authority: object,
    unbound_parameters: Callable[[object], object],
    provider_matches: Callable[
        [object, SourceAuthorityAdapter],
        bool,
    ],
    exact_authority_path: Callable[[object], bool],
) -> tuple[
    int,
    int,
    tuple[str, ...],
    SourceReceipt,
    SourceReceipt,
] | None:
    parameters = unbound_parameters(source)
    if parameters is None:
        return None
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "Frightful Presence authority must be an exact "
            "SourceAuthorityAdapter"
        )
    if type(consumer) is not VerifiedSourceSelection:
        raise TypeError(
            "Frightful Presence consumer must be an exact "
            "VerifiedSourceSelection"
        )
    if type(provider) is not VerifiedRuleReceipt:
        raise TypeError(
            "Frightful Presence provider must be an exact "
            "VerifiedRuleReceipt"
        )
    authority.validate_selection(consumer)
    if not provider_matches(provider, authority):
        return None
    authority.require_shared_authority(consumer, (provider,))
    consumer_receipt = consumer.receipt
    fresh = authority.reload(consumer_receipt)
    (
        radius_feet,
        save_dc,
        traits,
        source_id,
        locator,
        creature_name,
        raw_member,
    ) = parameters
    address = fresh.address
    carrier = fresh.carrier
    if (
        type(address) is not SourceAddress
        or type(carrier) is not VerifiedSourceCarrier
        or type(carrier.raw_block) is not RawSourceObject
        or type(carrier.raw_block.members) is not tuple
        or any(
            type(member) is not RawSourceMember
            for member in carrier.raw_block.members
        )
        or not exact_authority_path(address.target_path)
        or not exact_authority_path(address.carrier_path)
        or not exact_authority_path(address.selection_path)
        or address.span is not None
        or len(address.selection_path) != 1
        or type(address.selection_path[0]) is not RawMemberStep
        or address.selection_path[0].raw_key
        != "!.Frightful Presence"
        or address.selection_path[0].member_ordinal
        >= len(carrier.raw_block.members)
        or address.source_id != source_id
        or address.locator != locator
        or carrier.ruleset != "pf2er"
        or carrier.source_id != source_id
        or carrier.locator != locator
        or type(fresh.raw_member) is not RawSourceMember
        or type(fresh.raw_member.key) is not str
        or fresh.raw_member.key != "!.Frightful Presence"
        or fresh.raw_member
        is not carrier.raw_block.members[
            address.selection_path[0].member_ordinal
        ]
        or fresh.raw_value is not fresh.raw_member.value
        or fresh.selected_value is not fresh.raw_value
        or raw_member != fresh.raw_member
    ):
        return None
    names = tuple(
        object.__getattribute__(member, "value")
        for member in carrier.raw_block.members
        if (
            type(object.__getattribute__(member, "key")) is str
            and object.__getattribute__(member, "key") == "Name"
        )
    )
    if (
        len(names) != 1
        or type(names[0]) is not str
        or names[0] != creature_name
    ):
        return None
    return (
        radius_feet,
        save_dc,
        traits,
        consumer_receipt,
        provider.receipt,
    )


def _verified_parameters_contract(
    structural_validator: Callable[..., object],
    unbound_parameters: Callable[[object], object],
    provider_matches: Callable[
        [object, SourceAuthorityAdapter],
        bool,
    ],
    exact_authority_path: Callable[[object], bool],
) -> Callable[[object, object, object, object], object]:
    def validate(
        source: object,
        consumer: object,
        provider: object,
        authority: object,
    ) -> object:
        return structural_validator(
            source,
            consumer,
            provider,
            authority,
            unbound_parameters,
            provider_matches,
            exact_authority_path,
        )

    return validate


_verified_parameters = _verified_parameters_contract(
    _verified_parameters_structure,
    _unbound_parameters,
    _provider_matches,
    _exact_authority_path,
)
del _verified_parameters_contract


def _patch_validator_contract(
    structural_validator: Callable[..., None],
    mechanic_for: Callable[[int, int], Mapping[str, Any]],
    verified_parameters: Callable[
        [object, object, object, object],
        tuple[
            int,
            int,
            tuple[str, ...],
            SourceReceipt,
            SourceReceipt,
        ] | None,
    ],
    validate_rule_receipt: Callable[..., None],
    validate_deferral: Callable[[object], None],
) -> Callable[[object], None]:
    def validate(patch: object) -> None:
        structural_validator(
            patch,
            mechanic_for,
            verified_parameters,
            validate_rule_receipt,
            validate_deferral,
        )

    return validate


_validate_patch = _patch_validator_contract(
    _validate_patch_structure,
    _mechanic_for,
    _verified_parameters,
    _validate_rule_receipt,
    _validate_deferral,
)
_bind_patch_validator(_validate_patch)
del _bind_patch_validator
del _patch_validator_contract


def _compile_frightful_presence_structure(
    source: object,
    consumer: object,
    authority: object,
    authority_type: type[SourceAuthorityAdapter],
    unbound_parameters: Callable[[object], object],
    resolve_reviewed_provider: Callable[
        [SourceAuthorityAdapter],
        VerifiedRuleReceipt,
    ],
    verified_parameters: Callable[
        [object, object, object, object],
        object,
    ],
    new_patch: Callable[..., FrightfulPresenceCompilerPatch],
    validate_patch: Callable[[object], None],
) -> FrightfulPresenceCompilerPatch | None:
    """Compile one authority-bound Frightful Presence production."""

    if type(authority) is not authority_type:
        raise TypeError(
            "Frightful Presence authority must be an exact "
            "SourceAuthorityAdapter"
        )
    if unbound_parameters(source) is None:
        return None
    provider = resolve_reviewed_provider(authority)
    parameters = verified_parameters(
        source,
        consumer,
        provider,
        authority,
    )
    if parameters is None:
        return None
    radius_feet, save_dc, traits, _consumer_receipt, _provider_receipt = (
        parameters
    )
    patch = new_patch(
        source=source,
        authority=authority,
        consumer_selection=consumer,
        provider_rule=provider,
        radius_feet=radius_feet,
        save_dc=save_dc,
        traits=traits,
    )
    if type(patch) is not FrightfulPresenceCompilerPatch:
        raise TypeError(
            "Frightful Presence compiler returned a foreign patch"
        )
    validate_patch(patch)
    return patch


def _compiler_contract(
    structural_compiler: Callable[..., object],
    authority_type: type[SourceAuthorityAdapter],
    unbound_parameters: Callable[[object], object],
    resolve_reviewed_provider: Callable[
        [SourceAuthorityAdapter],
        VerifiedRuleReceipt,
    ],
    verified_parameters: Callable[
        [object, object, object, object],
        object,
    ],
    new_patch: Callable[..., FrightfulPresenceCompilerPatch],
    validate_patch: Callable[[object], None],
) -> Callable[
    [object, object, object],
    FrightfulPresenceCompilerPatch | None,
]:
    def compile(
        source: object,
        consumer: object,
        authority: object,
        /,
    ) -> FrightfulPresenceCompilerPatch | None:
        result = structural_compiler(
            source,
            consumer,
            authority,
            authority_type,
            unbound_parameters,
            resolve_reviewed_provider,
            verified_parameters,
            new_patch,
            validate_patch,
        )
        if result is not None and type(result) is not FrightfulPresenceCompilerPatch:
            raise TypeError(
                "Frightful Presence compiler returned a foreign result"
            )
        return result

    return compile


compile_frightful_presence = _compiler_contract(
    _compile_frightful_presence_structure,
    SourceAuthorityAdapter,
    _unbound_parameters,
    _resolve_reviewed_provider,
    _verified_parameters,
    _new_patch,
    _validate_patch,
)
compile_frightful_presence.__name__ = "compile_frightful_presence"
compile_frightful_presence.__qualname__ = "compile_frightful_presence"
compile_frightful_presence.__doc__ = (
    "Compile one authority-bound Frightful Presence production."
)
del _compiler_contract


def _registration_validation_gateway() -> tuple[
    Callable[
        [
            Callable[
                [object],
                Callable[
                    [object, object, object],
                    FrightfulPresenceCompilerPatch | None,
                ],
            ]
        ],
        None,
    ],
    Callable[
        [object],
        Callable[
            [object, object, object],
            FrightfulPresenceCompilerPatch | None,
        ],
    ],
]:
    validator: Callable[
        [object],
        Callable[
            [object, object, object],
            FrightfulPresenceCompilerPatch | None,
        ],
    ] | None = None

    def bind(
        value: Callable[
            [object],
            Callable[
                [object, object, object],
                FrightfulPresenceCompilerPatch | None,
            ],
        ],
    ) -> None:
        nonlocal validator
        if validator is not None:
            raise RuntimeError(
                "Frightful Presence registration validator is already bound"
            )
        validator = value

    def validate(
        value: object,
    ) -> Callable[
        [object, object, object],
        FrightfulPresenceCompilerPatch | None,
    ]:
        if validator is None:
            raise RuntimeError(
                "Frightful Presence registration validator is not bound"
            )
        return validator(value)

    return bind, validate


_bind_registration_validator, _registration_validation_method = (
    _registration_validation_gateway()
)
del _registration_validation_gateway


def _registration_match_contract(
    validate_registration: Callable[
        [object],
        Callable[
            [object, object, object],
            FrightfulPresenceCompilerPatch | None,
        ],
    ],
    validate_patch: Callable[[object], None],
) -> Callable[
    [object, object, object, object],
    FrightfulPresenceCompilerPatch | None,
]:
    def match(
        registration: object,
        source: object,
        consumer: object,
        authority: object,
    ) -> FrightfulPresenceCompilerPatch | None:
        compiler = validate_registration(registration)
        patch = compiler(source, consumer, authority)
        if patch is None:
            return None
        validate_patch(patch)
        return patch

    return match


_registration_match_method = _registration_match_contract(
    _registration_validation_method,
    _validate_patch,
)
del _registration_match_contract


@final
@dataclass(frozen=True, slots=True, init=False)
class FrightfulPresenceCompilerRegistration:
    """Local registration that cannot enter the shared runtime registry."""

    compiler_id: str
    mechanic_type: str
    compiler: Callable[
        [object, object, object],
        FrightfulPresenceCompilerPatch | None,
    ]
    match = _registration_match_method

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "FrightfulPresenceCompilerRegistration must be created by "
            "its factory"
        )


del _registration_match_method


def _registration_contract(
    canonical_compiler: Callable[
        [object, object, object],
        FrightfulPresenceCompilerPatch | None,
    ],
) -> tuple[
    Callable[[], FrightfulPresenceCompilerRegistration],
    Callable[
        [object],
        Callable[
            [object, object, object],
            FrightfulPresenceCompilerPatch | None,
        ],
    ],
]:
    def new_registration() -> FrightfulPresenceCompilerRegistration:
        registration = object.__new__(
            FrightfulPresenceCompilerRegistration
        )
        object.__setattr__(
            registration,
            "compiler_id",
            "frightful-presence",
        )
        object.__setattr__(
            registration,
            "mechanic_type",
            "first-entry-saving-throw-aura",
        )
        object.__setattr__(
            registration,
            "compiler",
            canonical_compiler,
        )
        validate_registration(registration)
        return registration

    def validate_registration(
        registration: object,
    ) -> Callable[
        [object, object, object],
        FrightfulPresenceCompilerPatch | None,
    ]:
        if type(registration) is not FrightfulPresenceCompilerRegistration:
            raise TypeError(
                "Frightful Presence registration must have the exact "
                "local type"
            )
        try:
            compiler_id = object.__getattribute__(registration, "compiler_id")
            mechanic_type = object.__getattribute__(registration, "mechanic_type")
            compiler = object.__getattribute__(registration, "compiler")
        except (AttributeError, TypeError) as error:
            raise TypeError(
                "Frightful Presence registration is incomplete"
            ) from error
        if (
            type(compiler_id) is not str
            or compiler_id != "frightful-presence"
            or type(mechanic_type) is not str
            or mechanic_type != "first-entry-saving-throw-aura"
            or compiler is not canonical_compiler
        ):
            raise ValueError(
                "Frightful Presence registration is not canonical"
            )
        return canonical_compiler

    return new_registration, validate_registration


_new_registration, _validate_registration = _registration_contract(
    compile_frightful_presence
)
del _registration_contract
_bind_registration_validator(_validate_registration)
del _bind_registration_validator
del _registration_validation_method


@final
@dataclass(frozen=True, slots=True, init=False)
class FrightfulPresenceFamilyFragment:
    """Compile-only fragment rejected by the shared runtime registry."""

    family_id: str
    mechanic_types: tuple[str, ...]
    ability_compilers: tuple[
        FrightfulPresenceCompilerRegistration,
        ...,
    ]
    runtime_ready: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "FrightfulPresenceFamilyFragment must be created by its factory"
        )


def _new_fragment() -> FrightfulPresenceFamilyFragment:
    fragment = object.__new__(FrightfulPresenceFamilyFragment)
    object.__setattr__(fragment, "family_id", "frightful-presence")
    object.__setattr__(
        fragment,
        "mechanic_types",
        ("first-entry-saving-throw-aura",),
    )
    object.__setattr__(
        fragment,
        "ability_compilers",
        (_new_registration(),),
    )
    object.__setattr__(fragment, "runtime_ready", False)
    _validate_fragment(fragment)
    return fragment


def _validate_fragment(
    fragment: object,
) -> None:
    if type(fragment) is not FrightfulPresenceFamilyFragment:
        raise TypeError(
            "Frightful Presence fragment must have the exact local type"
        )
    try:
        family_id = object.__getattribute__(fragment, "family_id")
        mechanic_types = object.__getattribute__(fragment, "mechanic_types")
        ability_compilers = object.__getattribute__(fragment, "ability_compilers")
        runtime_ready = object.__getattribute__(fragment, "runtime_ready")
    except (AttributeError, TypeError) as error:
        raise TypeError(
            "Frightful Presence fragment is incomplete"
        ) from error
    if (
        type(family_id) is not str
        or family_id != "frightful-presence"
        or type(mechanic_types) is not tuple
        or any(
            type(mechanic_type) is not str
            for mechanic_type in mechanic_types
        )
        or mechanic_types != ("first-entry-saving-throw-aura",)
        or type(ability_compilers) is not tuple
        or len(ability_compilers) != 1
        or type(ability_compilers[0])
        is not FrightfulPresenceCompilerRegistration
        or type(runtime_ready) is not bool
        or runtime_ready is not False
    ):
        raise ValueError(
            "Frightful Presence fragment is not canonical"
        )
    _validate_registration(ability_compilers[0])


FRAGMENT = _new_fragment()


__all__ = [
    "FRAGMENT",
    "FRIGHTFUL_PRESENCE_RULE",
    "FRIGHTFUL_PRESENCE_RULE_REQUIREMENT",
    "FrightfulPresenceCompilerPatch",
    "FrightfulPresenceCompilerRegistration",
    "FrightfulPresenceDeferral",
    "FrightfulPresenceFamilyFragment",
    "FrightfulPresenceRuleReceipt",
    "compile_frightful_presence",
]

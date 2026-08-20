"""Compile exact Monster Core Telepathy declarations from Languages fields.

Telepathy is a token inside one creature's duplicate-preserving ``Languages``
member.  It is not a named ability and does not grant a sense.  This module
therefore owns a local source-field compiler category until the shared source
orchestrator grows that category.

Compilation requires one exact ``Languages`` member and the reviewed
``Telepathy`` glossary entry to be resolved by the same retained
``SourceAuthorityAdapter``.  The result is deliberately compile/link-only:
language identity, target eligibility, delivery, range or contact, and
observer-state interactions remain ordered typed deferrals.  The local
fragment cannot be mounted in the shared runtime registry.

The eventual migration is mechanical:

* move the duplicate-preserving source and compiler contracts into
  ``mechanics.contracts`` when the source orchestrator owns source fields;
* add ``language_capability_compilers`` to the shared family fragment only
  after the relational runtime contracts exist;
* have the source linker merge this verified patch with authoritative
  language identities; and
* delete these local category contracts after that cut.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256 as _sha256_factory
from json import dumps as _json_dumps
import math
import re
from types import MappingProxyType
from typing import Any, Literal, Protocol, TypeAlias, final

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    SerializedObject,
)
from .source_authority import (
    MAX_RAW_BYTES,
    MAX_RAW_DEPTH,
    MAX_RAW_NODES,
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceAddress,
    SourceAuthorityAdapter,
    SourceReceipt,
    TextSpan,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
    canonical_json_bytes,
    canonical_raw_bytes,
)
from .source_values import parse_decimal_integer


FAMILY_ID = "telepathy"
MECHANIC_TYPE = "telepathy"
COMPILER_ID = "monster-core-telepathy"
LANGUAGES_FIELD_NAME = "Languages"
MONSTER_CORE_SOURCE_ID = "core-mc1"

TelepathyMode: TypeAlias = Literal["radius", "touch"]
DependencyPhase: TypeAlias = Literal["source-link", "runtime"]
DependencyRelation: TypeAlias = Literal[
    "participant-definition",
    "source-target",
    "source-area-target",
    "communication-delivery",
]

_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
_LOCATOR_RE = re.compile(r"^[1-9][0-9]*\.[1-9][0-9]*$", re.ASCII)
_RADIUS_RE = re.compile(
    r"^telepathy (?P<range>[1-9][0-9]*) feet"
    r"(?P<page> \(page 360\))?$",
    re.ASCII,
)
_TOUCH_RE = re.compile(
    r"^telepathy \((?P<qualifier>touch|touch only); page 360\)$",
    re.ASCII,
)


class TelepathySourceAmbiguityError(ValueError):
    """One Languages carrier contains contradictory Telepathy declarations."""


class LanguageCapabilityCompilerAmbiguityError(ValueError):
    """More than one ordered source-field compiler accepted one consumer."""


def _external_contract_guard_contract(
    contract_types: tuple[type, ...],
) -> Callable[[], None]:
    snapshots = tuple(
        (
            contract_type,
            tuple(
                type.__getattribute__(
                    contract_type,
                    "__dict__",
                ).items()
            ),
        )
        for contract_type in contract_types
    )

    def guard() -> None:
        for contract_type, expected_items in snapshots:
            current = type.__getattribute__(
                contract_type,
                "__dict__",
            )
            if (
                len(current) != len(expected_items)
                or any(
                    current.get(name) is not expected
                    for name, expected in expected_items
                )
            ):
                raise TypeError(
                    "Telepathy external authority contracts were rebound"
                )

    return guard


_guard_external_contracts = _external_contract_guard_contract(
    (
        RawSourceArray,
        RawSourceMember,
        RawSourceObject,
        RawIndexStep,
        RawMemberStep,
        TextSpan,
        SourceAddress,
        SourceReceipt,
        RuleRequirement,
        VerifiedRuleReceipt,
        VerifiedSourceCarrier,
        VerifiedSourceSelection,
        SourceAuthorityAdapter,
    )
)
del _external_contract_guard_contract


def _captured_raw_contract(
    raw_object_type: type[RawSourceObject],
    raw_member_type: type[RawSourceMember],
    raw_array_type: type[RawSourceArray],
    json_dumps: Callable[..., str],
    sha256_factory: Callable[[bytes], Any],
    max_bytes: int,
    max_depth: int,
    max_nodes: int,
) -> tuple[
    Callable[[object], str],
    Callable[[RawSourceMember], str],
]:
    object_members_descriptor = raw_object_type.__dict__["members"]
    member_key_descriptor = raw_member_type.__dict__["key"]
    member_value_descriptor = raw_member_type.__dict__["value"]
    array_items_descriptor = raw_array_type.__dict__["items"]

    def encode(
        value: object,
        *,
        root_member: RawSourceMember | None = None,
    ) -> bytes:
        body = bytearray()
        nodes = 0
        active: set[int] = set()

        def append(value: str | bytes) -> None:
            encoded = (
                value.encode("utf-8")
                if type(value) is str
                else value
            )
            if type(encoded) is not bytes:
                raise TypeError(
                    "Telepathy raw encoder accepts exact str or bytes"
                )
            if len(body) + len(encoded) > max_bytes:
                raise ValueError(
                    "Telepathy captured raw source exceeds its byte bound"
                )
            body.extend(encoded)

        def write(item: object, depth: int) -> None:
            nonlocal nodes
            if depth > max_depth:
                raise ValueError(
                    "Telepathy captured raw source exceeds its depth bound"
                )
            nodes += 1
            if nodes > max_nodes:
                raise ValueError(
                    "Telepathy captured raw source exceeds its node bound"
                )
            item_type = type(item)
            if item_type is raw_object_type:
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "Telepathy captured raw source contains a cycle"
                    )
                active.add(identity)
                try:
                    members = object_members_descriptor.__get__(
                        item,
                        raw_object_type,
                    )
                    if (
                        type(members) is not tuple
                        or len(members) > max_nodes
                    ):
                        raise TypeError(
                            "Telepathy captured object members are invalid"
                        )
                    append(b"{")
                    for index, member in enumerate(members):
                        if type(member) is not raw_member_type:
                            raise TypeError(
                                "Telepathy captured member must be exact"
                            )
                        key = member_key_descriptor.__get__(
                            member,
                            raw_member_type,
                        )
                        if type(key) is not str:
                            raise TypeError(
                                "Telepathy captured key must be exact text"
                            )
                        if index:
                            append(b",")
                        append(
                            json_dumps(
                                key,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        )
                        append(b":")
                        write(
                            member_value_descriptor.__get__(
                                member,
                                raw_member_type,
                            ),
                            depth + 1,
                        )
                    append(b"}")
                finally:
                    active.remove(identity)
                return
            if item_type is raw_array_type:
                identity = id(item)
                if identity in active:
                    raise ValueError(
                        "Telepathy captured raw source contains a cycle"
                    )
                active.add(identity)
                try:
                    items = array_items_descriptor.__get__(
                        item,
                        raw_array_type,
                    )
                    if (
                        type(items) is not tuple
                        or len(items) > max_nodes
                    ):
                        raise TypeError(
                            "Telepathy captured array items are invalid"
                        )
                    append(b"[")
                    for index, child in enumerate(items):
                        if index:
                            append(b",")
                        write(child, depth + 1)
                    append(b"]")
                finally:
                    active.remove(identity)
                return
            if item_type is float and not math.isfinite(item):
                raise ValueError(
                    "Telepathy captured number must be finite"
                )
            if (
                item is None
                or item_type in (bool, int, float, str)
            ):
                append(
                    json_dumps(
                        item,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                )
                return
            raise TypeError(
                "Telepathy captured raw source has a foreign value"
            )

        if root_member is None:
            write(value, 0)
        else:
            if type(root_member) is not raw_member_type:
                raise TypeError(
                    "Telepathy captured member hash requires exact member"
                )
            nodes = 1
            key = member_key_descriptor.__get__(
                root_member,
                raw_member_type,
            )
            if type(key) is not str:
                raise TypeError(
                    "Telepathy captured member key must be exact text"
                )
            append(b"{")
            append(
                json_dumps(
                    key,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            append(b":")
            write(
                member_value_descriptor.__get__(
                    root_member,
                    raw_member_type,
                ),
                1,
            )
            append(b"}")
        return bytes(body)

    def raw_hash(value: object) -> str:
        return sha256_factory(encode(value)).hexdigest()

    def member_hash(member: RawSourceMember) -> str:
        return sha256_factory(
            encode(None, root_member=member)
        ).hexdigest()

    return raw_hash, member_hash


_captured_raw_hash, _captured_member_hash = _captured_raw_contract(
    RawSourceObject,
    RawSourceMember,
    RawSourceArray,
    _json_dumps,
    _sha256_factory,
    MAX_RAW_BYTES,
    MAX_RAW_DEPTH,
    MAX_RAW_NODES,
)
del _captured_raw_contract
del _json_dumps


class _SealedTelepathyType(type):
    """Prevent public contract classes from being rebound or subclassed."""

    def __new__(
        metaclass: type,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        **kwargs: object,
    ) -> type:
        if any(
            type.__getattribute__(base, "__dict__").get(
                "_telepathy_type_sealed",
                False,
            )
            for base in bases
        ):
            raise TypeError("sealed Telepathy contract types cannot be subclassed")
        return super().__new__(
            metaclass,
            name,
            bases,
            namespace,
            **kwargs,
        )

    def __setattr__(
        cls,
        name: str,
        value: object,
    ) -> None:
        if type.__getattribute__(cls, "__dict__").get(
            "_telepathy_type_sealed",
            False,
        ):
            raise TypeError("sealed Telepathy contract types cannot be rebound")
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if type.__getattribute__(cls, "__dict__").get(
            "_telepathy_type_sealed",
            False,
        ):
            raise TypeError("sealed Telepathy contract types cannot be rebound")
        super().__delattr__(name)


def _seal_telepathy_type(contract_type: type) -> None:
    type.__setattr__(
        contract_type,
        "_telepathy_type_sealed",
        True,
    )


def _require_key(value: object, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be an exact string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    if len(value.encode("utf-8")) > 4_096:
        raise ValueError(f"{label} exceeds its UTF-8 byte bound")
    return value


def _require_source_token(value: object, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be an exact string")
    if len(value.encode("utf-8")) > 4_096:
        raise ValueError(f"{label} exceeds its UTF-8 byte bound")
    return value


def _freeze_json_structure(
    value: Any,
    mapping_proxy_type: type,
    isfinite: Callable[[float], bool],
) -> Any:
    active: set[int] = set()
    visited = 0

    def visit(item: Any, depth: int) -> Any:
        nonlocal visited
        visited += 1
        if depth > 32 or visited > 4_096:
            raise ValueError(
                "Telepathy payload exceeds its structural bound"
            )
        if type(item) is dict:
            identity = id(item)
            if identity in active:
                raise ValueError("Telepathy payload cannot contain cycles")
            active.add(identity)
            try:
                frozen: dict[str, Any] = {}
                for key, child in dict.items(item):
                    if type(key) is not str:
                        raise TypeError(
                            "Telepathy payload keys must be exact strings"
                        )
                    frozen[key] = visit(child, depth + 1)
                return mapping_proxy_type(frozen)
            finally:
                active.remove(identity)
        if type(item) in (list, tuple):
            identity = id(item)
            if identity in active:
                raise ValueError("Telepathy payload cannot contain cycles")
            active.add(identity)
            try:
                return tuple(
                    visit(child, depth + 1)
                    for child in item
                )
            finally:
                active.remove(identity)
        if type(item) is float:
            if not isfinite(item):
                raise ValueError(
                    "Telepathy payload numbers must be finite"
                )
            return item
        if type(item) is int:
            if item < -(1 << 63) or item > (1 << 63) - 1:
                raise ValueError(
                    "Telepathy payload integers must fit signed-64"
                )
            return item
        if item is None or type(item) in (bool, str):
            return item
        raise TypeError(
            "Telepathy payload contains a non-JSON value: "
            f"{type(item).__name__}"
        )

    return visit(value, 0)


def _freeze_json_contract(
    structural_freezer: Callable[..., Any],
    mapping_proxy_type: type,
    isfinite: Callable[[float], bool],
) -> Callable[[Any], Any]:
    def freeze(value: Any) -> Any:
        return structural_freezer(
            value,
            mapping_proxy_type,
            isfinite,
        )

    return freeze


_freeze_json = _freeze_json_contract(
    _freeze_json_structure,
    MappingProxyType,
    math.isfinite,
)
del _freeze_json_contract


def _thaw_json_structure(
    value: Any,
    mapping_proxy_type: type,
) -> Any:
    active: set[int] = set()
    visited = 0

    def visit(item: Any, depth: int) -> Any:
        nonlocal visited
        visited += 1
        if depth > 32 or visited > 4_096:
            raise ValueError(
                "Telepathy payload exceeds its structural bound"
            )
        if type(item) is mapping_proxy_type:
            identity = id(item)
            if identity in active:
                raise ValueError("Telepathy payload cannot contain cycles")
            active.add(identity)
            try:
                return {
                    key: visit(child, depth + 1)
                    for key, child in item.items()
                }
            finally:
                active.remove(identity)
        if type(item) is tuple:
            identity = id(item)
            if identity in active:
                raise ValueError("Telepathy payload cannot contain cycles")
            active.add(identity)
            try:
                return [
                    visit(child, depth + 1)
                    for child in item
                ]
            finally:
                active.remove(identity)
        if item is not None and type(item) not in (bool, int, float, str):
            raise TypeError(
                "Telepathy payload contains an untrusted frozen value"
            )
        return item

    return visit(value, 0)


def _thaw_json_contract(
    structural_thawer: Callable[..., Any],
    mapping_proxy_type: type,
) -> Callable[[Any], Any]:
    def thaw(value: Any) -> Any:
        return structural_thawer(value, mapping_proxy_type)

    return thaw


_thaw_json = _thaw_json_contract(
    _thaw_json_structure,
    _MAPPING_PROXY_TYPE,
)
del _thaw_json_contract


def _late_validation_method(
    label: str,
) -> tuple[
    Callable[[Callable[[object], None]], None],
    Callable[[object], None],
]:
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


def _validated_method_contract(
    validator: Callable[[object], None],
    *dependencies: object,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
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


def _raw_languages_serialized_structure(
    value: object,
    raw_array_type: type[RawSourceArray],
) -> object:
    if type(value) is str:
        return value
    if type(value) is not raw_array_type:
        raise TypeError("Languages value must be an exact string or array")
    items = object.__getattribute__(value, "items")
    if (
        type(items) is not tuple
        or len(items) > 4_096
        or any(type(item) is not str for item in items)
    ):
        raise TypeError("Languages array must contain exact strings")
    return {
        "kind": "array",
        "items": list(items),
    }


def _raw_languages_serializer_contract(
    structural_serializer: Callable[..., object],
    raw_array_type: type[RawSourceArray],
) -> Callable[[object], object]:
    def serialize(value: object) -> object:
        return structural_serializer(value, raw_array_type)

    return serialize


_raw_languages_serialized = _raw_languages_serializer_contract(
    _raw_languages_serialized_structure,
    RawSourceArray,
)
del _raw_languages_serializer_contract


_bind_source_validator, _source_validation_method = (
    _late_validation_method("Telepathy source")
)


def _source_initializer_contract(
    validator: Callable[[object], None],
) -> Callable[..., None]:
    def initialize(
        source: object,
        *,
        raw_member: RawSourceMember,
        source_id: str,
        locator: str,
        creature_name: str,
    ) -> None:
        object.__setattr__(source, "_raw_member", raw_member)
        object.__setattr__(source, "_source_id", source_id)
        object.__setattr__(source, "_locator", locator)
        object.__setattr__(source, "_creature_name", creature_name)
        validator(source)

    return initialize


_source_initializer = _source_initializer_contract(
    _source_validation_method
)
del _source_initializer_contract

_source_public_method = _validated_method_contract(
    _source_validation_method,
    _raw_languages_serialized,
)


@final
@dataclass(frozen=True, slots=True, init=False)
class LanguageCapabilitySource(metaclass=_SealedTelepathyType):
    """A public claim paired with one authority-selected Languages member."""

    _raw_member: RawSourceMember = field(repr=False)
    _source_id: str
    _locator: str
    _creature_name: str

    __init__ = _source_initializer

    @property
    @_source_public_method
    def raw_member(
        self,
        _serialize_raw: Callable[[object], object],
    ) -> RawSourceMember:
        return object.__getattribute__(self, "_raw_member")

    @property
    @_source_public_method
    def source_id(
        self,
        _serialize_raw: Callable[[object], object],
    ) -> str:
        return object.__getattribute__(self, "_source_id")

    @property
    @_source_public_method
    def locator(
        self,
        _serialize_raw: Callable[[object], object],
    ) -> str:
        return object.__getattribute__(self, "_locator")

    @property
    @_source_public_method
    def creature_name(
        self,
        _serialize_raw: Callable[[object], object],
    ) -> str:
        return object.__getattribute__(self, "_creature_name")

    @property
    @_source_public_method
    def language_entries(
        self,
        _serialize_raw: Callable[[object], object],
    ) -> tuple[str, ...]:
        value = object.__getattribute__(
            object.__getattribute__(self, "_raw_member"),
            "value",
        )
        if type(value) is str:
            return (value,)
        return tuple(object.__getattribute__(value, "items"))

    @property
    @_source_public_method
    def source_shape(
        self,
        _serialize_raw: Callable[[object], object],
    ) -> str:
        value = object.__getattribute__(
            object.__getattribute__(self, "_raw_member"),
            "value",
        )
        return "scalar" if type(value) is str else "array"

    @_source_public_method
    def as_serialized(
        self,
        serialize_raw: Callable[[object], object],
    ) -> SerializedObject:
        member = object.__getattribute__(self, "_raw_member")
        value = object.__getattribute__(member, "value")
        return {
            "sourceId": object.__getattribute__(self, "_source_id"),
            "locator": object.__getattribute__(self, "_locator"),
            "creatureName": object.__getattribute__(
                self,
                "_creature_name",
            ),
            "fieldName": "Languages",
            "sourceShape": "scalar" if type(value) is str else "array",
            "rawMember": {
                "key": object.__getattribute__(member, "key"),
                "value": serialize_raw(value),
            },
        }


del _source_initializer
del _source_public_method


def _validate_source_structure(
    source: object,
    source_type: type[LanguageCapabilitySource],
    raw_member_type: type[RawSourceMember],
    raw_array_type: type[RawSourceArray],
    require_key: Callable[[object, str], str],
    require_source_token: Callable[[object, str], str],
    canonical_raw_encoder: Callable[[object], bytes],
    locator_pattern: re.Pattern[str],
) -> None:
    if type(source) is not source_type:
        raise TypeError(
            "Telepathy source must have the exact "
            "LanguageCapabilitySource type"
        )
    try:
        raw_member = object.__getattribute__(source, "_raw_member")
        source_id = object.__getattribute__(source, "_source_id")
        locator = object.__getattribute__(source, "_locator")
        creature_name = object.__getattribute__(
            source,
            "_creature_name",
        )
    except (AttributeError, TypeError) as failure:
        raise TypeError("Telepathy source is incomplete") from failure
    if type(raw_member) is not raw_member_type:
        raise TypeError(
            "Telepathy source raw member must be exact RawSourceMember"
        )
    try:
        key = object.__getattribute__(raw_member, "key")
        value = object.__getattribute__(raw_member, "value")
    except (AttributeError, TypeError) as failure:
        raise TypeError("Telepathy source raw member is incomplete") from failure
    if type(key) is not str or key != "Languages":
        raise ValueError(
            "Telepathy source must preserve the exact Languages key"
        )
    require_key(source_id, "LanguageCapabilitySource.source_id")
    require_key(locator, "LanguageCapabilitySource.locator")
    require_key(creature_name, "LanguageCapabilitySource.creature_name")
    if locator_pattern.fullmatch(locator) is None:
        raise ValueError(
            "LanguageCapabilitySource.locator must be numeric"
        )
    if type(value) is str:
        require_source_token(
            value,
            "LanguageCapabilitySource Languages scalar",
        )
    elif type(value) is raw_array_type:
        try:
            items = object.__getattribute__(value, "items")
        except (AttributeError, TypeError) as failure:
            raise TypeError(
                "LanguageCapabilitySource Languages array is incomplete"
            ) from failure
        if (
            type(items) is not tuple
            or len(items) > 4_096
        ):
            raise ValueError(
                "LanguageCapabilitySource Languages array is not bounded"
            )
        for index, item in enumerate(items):
            require_source_token(
                item,
                f"LanguageCapabilitySource Languages[{index}]",
            )
    else:
        raise TypeError(
            "LanguageCapabilitySource Languages value must be an exact "
            "string or RawSourceArray"
        )
    canonical_raw_encoder(value)


def _source_validator_contract(
    structural_validator: Callable[..., None],
    source_type: type[LanguageCapabilitySource],
    raw_member_type: type[RawSourceMember],
    raw_array_type: type[RawSourceArray],
    require_key: Callable[[object, str], str],
    require_source_token: Callable[[object, str], str],
    canonical_raw_encoder: Callable[[object], bytes],
    locator_pattern: re.Pattern[str],
) -> Callable[[object], None]:
    def validate(source: object) -> None:
        structural_validator(
            source,
            source_type,
            raw_member_type,
            raw_array_type,
            require_key,
            require_source_token,
            canonical_raw_encoder,
            locator_pattern,
        )

    return validate


_validate_source = _source_validator_contract(
    _validate_source_structure,
    LanguageCapabilitySource,
    RawSourceMember,
    RawSourceArray,
    _require_key,
    _require_source_token,
    canonical_raw_bytes,
    _LOCATOR_RE,
)
_bind_source_validator(_validate_source)
_seal_telepathy_type(LanguageCapabilitySource)
del _bind_source_validator
del _source_validation_method
del _source_validator_contract


_bind_dependency_validator, _dependency_validation_method = (
    _late_validation_method("Telepathy dependency")
)
_dependency_public_method = _validated_method_contract(
    _dependency_validation_method
)


@final
@dataclass(frozen=True, slots=True, init=False)
class RelationalCommunicationDependency(metaclass=_SealedTelepathyType):
    """One reviewed typed contract blocking Telepathy runtime activation."""

    _dependency_id: str
    _phase: DependencyPhase
    _relation: DependencyRelation
    _required_contract: str
    _modes: tuple[TelepathyMode, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "RelationalCommunicationDependency must be created by "
            "the Telepathy compiler"
        )

    @property
    @_dependency_public_method
    def dependency_id(self) -> str:
        return object.__getattribute__(self, "_dependency_id")

    @property
    @_dependency_public_method
    def phase(self) -> DependencyPhase:
        return object.__getattribute__(self, "_phase")

    @property
    @_dependency_public_method
    def relation(self) -> DependencyRelation:
        return object.__getattribute__(self, "_relation")

    @property
    @_dependency_public_method
    def required_contract(self) -> str:
        return object.__getattribute__(self, "_required_contract")

    @property
    @_dependency_public_method
    def modes(self) -> tuple[TelepathyMode, ...]:
        return object.__getattribute__(self, "_modes")

    @_dependency_public_method
    def as_serialized(self) -> SerializedObject:
        return {
            "id": object.__getattribute__(self, "_dependency_id"),
            "phase": object.__getattribute__(self, "_phase"),
            "relation": object.__getattribute__(self, "_relation"),
            "requiredContract": object.__getattribute__(
                self,
                "_required_contract",
            ),
            "modes": list(object.__getattribute__(self, "_modes")),
            "status": "deferred",
            "blocks": "registry-activation",
        }


del _dependency_public_method


def _dependency_specs(
    mode: TelepathyMode,
) -> tuple[
    tuple[str, str, str, str, tuple[TelepathyMode, ...]],
    ...,
]:
    common: tuple[
        tuple[str, str, str, str, tuple[TelepathyMode, ...]],
        ...,
    ] = (
        (
            "authoritative-language-identities",
            "source-link",
            "participant-definition",
            (
                "ordered ordinary language identities plus source-backed "
                "dynamic language grants"
            ),
            ("radius", "touch"),
        ),
        (
            "shared-language-eligibility",
            "runtime",
            "source-target",
            (
                "current source and target language-identity intersection"
            ),
            ("radius", "touch"),
        ),
        (
            "mental-target-eligibility",
            "runtime",
            "source-target",
            (
                "mental-trait immunity and eligibility without thought "
                "access"
            ),
            ("radius", "touch"),
        ),
        (
            "normal-speech-information-channel",
            "runtime",
            "communication-delivery",
            (
                "mental delivery limited to information normal speech can "
                "convey"
            ),
            ("radius", "touch"),
        ),
        (
            "no-detection-state-grant",
            "runtime",
            "source-target",
            (
                "communication eligibility must not reveal location or "
                "change observed, hidden, undetected, or unnoticed state"
            ),
            ("radius", "touch"),
        ),
        (
            "telepathy-relational-modifiers",
            "runtime",
            "source-area-target",
            (
                "restricted channels, dynamic languages, suppression "
                "fields, and specific-target links remain separately typed "
                "mechanics"
            ),
            ("radius", "touch"),
        ),
    )
    if mode == "radius":
        final_spec = (
            "occupied-square-range",
            "runtime",
            "source-target",
            (
                "inclusive minimum alternating-grid distance between "
                "occupied squares"
            ),
            ("radius",),
        )
    elif mode == "touch":
        final_spec = (
            "physical-contact",
            "runtime",
            "source-target",
            (
                "actual physical contact represented independently from "
                "adjacency"
            ),
            ("touch",),
        )
    else:
        raise ValueError("Telepathy dependency mode is invalid")
    return (*common, final_spec)


def _validate_dependency_structure(
    dependency: object,
    dependency_type: type[RelationalCommunicationDependency],
    specs_for_mode: Callable[[TelepathyMode], tuple[tuple[Any, ...], ...]],
    require_key: Callable[[object, str], str],
) -> None:
    if type(dependency) is not dependency_type:
        raise TypeError(
            "Telepathy dependency must have the exact typed contract"
        )
    try:
        values = (
            object.__getattribute__(dependency, "_dependency_id"),
            object.__getattribute__(dependency, "_phase"),
            object.__getattribute__(dependency, "_relation"),
            object.__getattribute__(dependency, "_required_contract"),
            object.__getattribute__(dependency, "_modes"),
        )
    except (AttributeError, TypeError) as failure:
        raise TypeError("Telepathy dependency is incomplete") from failure
    if any(type(value) is not str for value in values[:4]):
        raise TypeError(
            "Telepathy dependency scalar fields must be exact strings"
        )
    require_key(values[0], "Telepathy dependency id")
    require_key(values[3], "Telepathy dependency contract")
    modes = values[4]
    if (
        type(modes) is not tuple
        or not modes
        or any(type(mode) is not str for mode in modes)
    ):
        raise TypeError(
            "Telepathy dependency modes must be an exact non-empty tuple"
        )
    reviewed = {
        spec
        for mode in ("radius", "touch")
        for spec in specs_for_mode(mode)
    }
    if values not in reviewed:
        raise ValueError(
            "Telepathy dependency is not one reviewed deferral"
        )


def _dependency_validator_contract(
    structural_validator: Callable[..., None],
    dependency_type: type[RelationalCommunicationDependency],
    specs_for_mode: Callable[[TelepathyMode], tuple[tuple[Any, ...], ...]],
    require_key: Callable[[object, str], str],
) -> Callable[[object], None]:
    def validate(dependency: object) -> None:
        structural_validator(
            dependency,
            dependency_type,
            specs_for_mode,
            require_key,
        )

    return validate


_validate_dependency = _dependency_validator_contract(
    _validate_dependency_structure,
    RelationalCommunicationDependency,
    _dependency_specs,
    _require_key,
)
_bind_dependency_validator(_validate_dependency)
_seal_telepathy_type(RelationalCommunicationDependency)
del _bind_dependency_validator
del _dependency_validation_method
del _dependency_validator_contract


def _dependency_factory_contract(
    dependency_type: type[RelationalCommunicationDependency],
    validator: Callable[[object], None],
) -> Callable[..., RelationalCommunicationDependency]:
    def new(
        dependency_id: str,
        phase: DependencyPhase,
        relation: DependencyRelation,
        required_contract: str,
        modes: tuple[TelepathyMode, ...],
    ) -> RelationalCommunicationDependency:
        dependency = object.__new__(dependency_type)
        object.__setattr__(
            dependency,
            "_dependency_id",
            dependency_id,
        )
        object.__setattr__(dependency, "_phase", phase)
        object.__setattr__(dependency, "_relation", relation)
        object.__setattr__(
            dependency,
            "_required_contract",
            required_contract,
        )
        object.__setattr__(dependency, "_modes", modes)
        validator(dependency)
        return dependency

    return new


_new_dependency = _dependency_factory_contract(
    RelationalCommunicationDependency,
    _validate_dependency,
)
del _dependency_factory_contract


def _dependencies_contract(
    specs_for_mode: Callable[[TelepathyMode], tuple[tuple[Any, ...], ...]],
    factory: Callable[..., RelationalCommunicationDependency],
) -> Callable[[TelepathyMode], tuple[RelationalCommunicationDependency, ...]]:
    def build(
        mode: TelepathyMode,
    ) -> tuple[RelationalCommunicationDependency, ...]:
        return tuple(factory(*spec) for spec in specs_for_mode(mode))

    return build


_dependencies_for = _dependencies_contract(
    _dependency_specs,
    _new_dependency,
)
del _dependencies_contract


_bind_receipt_validator, _receipt_validation_method = (
    _late_validation_method("Telepathy provider receipt")
)
_receipt_public_method = _validated_method_contract(
    _receipt_validation_method
)


@final
@dataclass(frozen=True, slots=True, init=False)
class TelepathyRuleReceipt(metaclass=_SealedTelepathyType):
    """The exact reviewed import-side Monster Core glossary identity."""

    _rule_id: str
    _source_id: str
    _locator: str
    _matching_key_ordinal: int
    _absolute_member_ordinal: int
    _ordered_member_sha256: str
    _ordered_value_sha256: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "TelepathyRuleReceipt must be created by its factory"
        )

    @property
    @_receipt_public_method
    def rule_id(self) -> str:
        return object.__getattribute__(self, "_rule_id")

    @property
    @_receipt_public_method
    def source_id(self) -> str:
        return object.__getattribute__(self, "_source_id")

    @property
    @_receipt_public_method
    def locator(self) -> str:
        return object.__getattribute__(self, "_locator")

    @property
    @_receipt_public_method
    def matching_key_ordinal(self) -> int:
        return object.__getattribute__(self, "_matching_key_ordinal")

    @property
    @_receipt_public_method
    def absolute_member_ordinal(self) -> int:
        return object.__getattribute__(self, "_absolute_member_ordinal")

    @property
    @_receipt_public_method
    def ordered_member_sha256(self) -> str:
        return object.__getattribute__(self, "_ordered_member_sha256")

    @property
    @_receipt_public_method
    def ordered_value_sha256(self) -> str:
        return object.__getattribute__(self, "_ordered_value_sha256")

    @_receipt_public_method
    def as_serialized(self) -> SerializedObject:
        return {
            "ruleId": object.__getattribute__(self, "_rule_id"),
            "sourceId": object.__getattribute__(self, "_source_id"),
            "locator": object.__getattribute__(self, "_locator"),
            "matchingKeyOrdinal": object.__getattribute__(
                self,
                "_matching_key_ordinal",
            ),
            "absoluteMemberOrdinal": object.__getattribute__(
                self,
                "_absolute_member_ordinal",
            ),
            "orderedMemberSha256": object.__getattribute__(
                self,
                "_ordered_member_sha256",
            ),
            "orderedValueSha256": object.__getattribute__(
                self,
                "_ordered_value_sha256",
            ),
        }


del _receipt_public_method


def _provider_fields() -> tuple[str, str, str, int, int, str, str]:
    return (
        "core-mc1:ability-glossary#^.ability[033]",
        "core-mc1",
        "358.2",
        33,
        35,
        "2257f12121ba6dc9459643efbba9fb476c6767979199e1c4f49c3af6fc38d50a",
        "0024942041f95f836bf0023411767b2cd194d75736a226ca2c8279795d8baacf",
    )


def _validate_rule_receipt_structure(
    receipt: object,
    receipt_type: type[TelepathyRuleReceipt],
    provider_fields: Callable[
        [],
        tuple[str, str, str, int, int, str, str],
    ],
    require_key: Callable[[object, str], str],
) -> None:
    if type(receipt) is not receipt_type:
        raise TypeError(
            "Telepathy provider must be an exact TelepathyRuleReceipt"
        )
    names = (
        "_rule_id",
        "_source_id",
        "_locator",
        "_matching_key_ordinal",
        "_absolute_member_ordinal",
        "_ordered_member_sha256",
        "_ordered_value_sha256",
    )
    try:
        values = tuple(
            object.__getattribute__(receipt, name)
            for name in names
        )
    except (AttributeError, TypeError) as failure:
        raise TypeError(
            "Telepathy provider receipt is incomplete"
        ) from failure
    for index, name in enumerate(names[:3]):
        require_key(
            values[index],
            f"TelepathyRuleReceipt.{name}",
        )
    for index, name in ((3, names[3]), (4, names[4])):
        if (
            type(values[index]) is not int
            or not 0 <= values[index] <= (1 << 63) - 1
        ):
            raise ValueError(
                f"TelepathyRuleReceipt.{name} must fit signed-64"
            )
    for index, name in ((5, names[5]), (6, names[6])):
        digest = values[index]
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in digest
            )
        ):
            raise ValueError(
                f"TelepathyRuleReceipt.{name} must be lowercase SHA-256"
            )
    if values != provider_fields():
        raise ValueError(
            "Telepathy provider receipt is not the reviewed glossary rule"
        )


def _receipt_validator_contract(
    structural_validator: Callable[..., None],
    receipt_type: type[TelepathyRuleReceipt],
    provider_fields: Callable[
        [],
        tuple[str, str, str, int, int, str, str],
    ],
    require_key: Callable[[object, str], str],
) -> Callable[[object], None]:
    def validate(receipt: object) -> None:
        structural_validator(
            receipt,
            receipt_type,
            provider_fields,
            require_key,
        )

    return validate


_validate_rule_receipt = _receipt_validator_contract(
    _validate_rule_receipt_structure,
    TelepathyRuleReceipt,
    _provider_fields,
    _require_key,
)
_bind_receipt_validator(_validate_rule_receipt)
_seal_telepathy_type(TelepathyRuleReceipt)
del _bind_receipt_validator
del _receipt_validation_method
del _receipt_validator_contract


def _rule_receipt_factory_contract(
    receipt_type: type[TelepathyRuleReceipt],
    provider_fields: Callable[
        [],
        tuple[str, str, str, int, int, str, str],
    ],
    validator: Callable[[object], None],
) -> Callable[[], TelepathyRuleReceipt]:
    def new() -> TelepathyRuleReceipt:
        receipt = object.__new__(receipt_type)
        for name, value in zip(
            (
                "_rule_id",
                "_source_id",
                "_locator",
                "_matching_key_ordinal",
                "_absolute_member_ordinal",
                "_ordered_member_sha256",
                "_ordered_value_sha256",
            ),
            provider_fields(),
            strict=True,
        ):
            object.__setattr__(receipt, name, value)
        validator(receipt)
        return receipt

    return new


_new_rule_receipt = _rule_receipt_factory_contract(
    TelepathyRuleReceipt,
    _provider_fields,
    _validate_rule_receipt,
)
del _rule_receipt_factory_contract


TELEPATHY_GLOSSARY = _new_rule_receipt()


def _new_rule_requirement() -> RuleRequirement:
    return RuleRequirement(
        rule_id="core-mc1:ability-glossary#^.ability[033]",
        source_id="core-mc1",
        locator="358.2",
        carrier_path=(RawMemberStep("^.ability", 35),),
        expected_value_sha256=(
            "472fd10f0a1f1f616ff947eacf7bcff4a44de9ed26200366e21653d2b0b9331e"
        ),
    )


TELEPATHY_RULE_REQUIREMENT = _new_rule_requirement()


def _parse_token_structure(
    source_text: object,
    radius_pattern: re.Pattern[str],
    touch_pattern: re.Pattern[str],
    parse_integer: Callable[[str], int | None],
) -> tuple[
    TelepathyMode,
    int | None,
    str | None,
    str,
    int | None,
] | None:
    if type(source_text) is not str:
        return None
    radius = radius_pattern.fullmatch(source_text)
    if radius is not None:
        range_feet = parse_integer(radius.group("range"))
        if range_feet is None or range_feet <= 0:
            return None
        page_reference = 360 if radius.group("page") else None
        grammar = (
            "numeric-radius-page-360"
            if page_reference is not None
            else "numeric-radius"
        )
        return "radius", range_feet, None, grammar, page_reference
    touch = touch_pattern.fullmatch(source_text)
    if touch is None:
        return None
    qualifier = touch.group("qualifier")
    grammar = (
        "touch-only-page-360"
        if qualifier == "touch only"
        else "touch-page-360"
    )
    return "touch", None, qualifier, grammar, 360


def _parse_token_contract(
    structural_parser: Callable[..., object],
    radius_pattern: re.Pattern[str],
    touch_pattern: re.Pattern[str],
    parse_integer: Callable[[str], int | None],
) -> Callable[[object], object]:
    def parse(source_text: object) -> object:
        return structural_parser(
            source_text,
            radius_pattern,
            touch_pattern,
            parse_integer,
        )

    return parse


_parse_token = _parse_token_contract(
    _parse_token_structure,
    _RADIUS_RE,
    _TOUCH_RE,
    parse_decimal_integer,
)
del _parse_token_contract


def _unbound_parameters_structure(
    source: object,
    source_type: type[LanguageCapabilitySource],
    validate_source: Callable[[object], None],
    parse_token: Callable[[object], object],
    source_hash: Callable[[object], str],
) -> tuple[
    int,
    str,
    str,
    TelepathyMode,
    int | None,
    str | None,
    str,
    int | None,
    tuple[str, ...],
    str,
    str,
    str,
    RawSourceMember,
] | None:
    if type(source) is not source_type:
        return None
    validate_source(source)
    raw_member = object.__getattribute__(source, "_raw_member")
    raw_value = object.__getattribute__(raw_member, "value")
    entries = (
        (raw_value,)
        if type(raw_value) is str
        else tuple(object.__getattribute__(raw_value, "items"))
    )
    if (
        not entries
        or any(
            not entry or entry != entry.strip()
            for entry in entries
        )
    ):
        return None
    matches: list[tuple[int, str, tuple[Any, ...]]] = []
    malformed_candidate = False
    for index, source_text in enumerate(entries):
        parsed = parse_token(source_text)
        if parsed is not None:
            if type(parsed) is not tuple or len(parsed) != 5:
                raise TypeError(
                    "Telepathy token parser returned a foreign result"
                )
            matches.append((index, source_text, parsed))
        elif "telepathy" in source_text.casefold():
            malformed_candidate = True
    if malformed_candidate:
        return None
    if len(matches) > 1:
        raise TelepathySourceAmbiguityError(
            "multiple exact Telepathy declarations occur in Languages"
        )
    if not matches:
        return None
    source_index, source_text, parsed = matches[0]
    mode, range_feet, touch_qualifier, grammar, page_reference = parsed
    remaining = entries[:source_index] + entries[source_index + 1 :]
    return (
        source_index,
        source_text,
        source_hash(source_text),
        mode,
        range_feet,
        touch_qualifier,
        grammar,
        page_reference,
        remaining,
        object.__getattribute__(source, "_source_id"),
        object.__getattribute__(source, "_locator"),
        object.__getattribute__(source, "_creature_name"),
        raw_member,
    )


def _unbound_parameters_contract(
    structural_parser: Callable[..., object],
    source_type: type[LanguageCapabilitySource],
    validate_source: Callable[[object], None],
    parse_token: Callable[[object], object],
    source_hash: Callable[[object], str],
) -> Callable[[object], object]:
    def parse(source: object) -> object:
        return structural_parser(
            source,
            source_type,
            validate_source,
            parse_token,
            source_hash,
        )

    return parse


_unbound_parameters = _unbound_parameters_contract(
    _unbound_parameters_structure,
    LanguageCapabilitySource,
    _validate_source,
    _parse_token,
    _captured_raw_hash,
)
del _unbound_parameters_contract


def _exact_authority_path(
    value: object,
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
) -> bool:
    return (
        type(value) is tuple
        and len(value) <= 64
        and all(
            type(step) in (member_step_type, index_step_type)
            for step in value
        )
    )


def _receipt_projection_structure(
    receipt: object,
    receipt_type: type[SourceReceipt],
    address_type: type[SourceAddress],
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
    span_type: type[TextSpan],
    receipt_descriptors: tuple[object, ...],
    address_descriptors: tuple[object, ...],
    member_step_descriptors: tuple[object, ...],
    index_step_descriptors: tuple[object, ...],
    span_descriptors: tuple[object, ...],
) -> tuple[object, ...]:
    if type(receipt) is not receipt_type:
        raise TypeError("Telepathy receipt projection requires an exact receipt")
    try:
        (
            ruleset,
            authority_digest,
            address,
            block_sha256,
            member_sha256,
            value_sha256,
            selection_sha256,
        ) = tuple(
            descriptor.__get__(receipt, receipt_type)
            for descriptor in receipt_descriptors
        )
    except (AttributeError, TypeError) as failure:
        raise TypeError("Telepathy receipt is incomplete") from failure

    def digest(value: object, label: str) -> str:
        if (
            type(value) is not str
            or len(value) != 64
            or any(
                character not in "0123456789abcdef"
                for character in value
            )
        ):
            raise ValueError(f"{label} must be lowercase SHA-256")
        return value

    if (
        type(ruleset) is not str
        or not ruleset
        or len(ruleset.encode("utf-8")) > 4_096
    ):
        raise ValueError("Telepathy receipt ruleset is invalid")
    digest(authority_digest, "Telepathy receipt authority digest")
    digest(block_sha256, "Telepathy receipt block digest")
    if member_sha256 is not None:
        digest(member_sha256, "Telepathy receipt member digest")
    digest(value_sha256, "Telepathy receipt value digest")
    digest(selection_sha256, "Telepathy receipt selection digest")
    if type(address) is not address_type:
        raise TypeError("Telepathy receipt address must be exact")
    try:
        (
            source_id,
            locator,
            section_id,
            target_path,
            carrier_path,
            selection_path,
            span,
        ) = tuple(
            descriptor.__get__(address, address_type)
            for descriptor in address_descriptors
        )
    except (AttributeError, TypeError) as failure:
        raise TypeError("Telepathy receipt address is incomplete") from failure
    for value, label in (
        (source_id, "source id"),
        (locator, "locator"),
        (section_id, "section id"),
    ):
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or len(value.encode("utf-8")) > 4_096
        ):
            raise ValueError(f"Telepathy receipt {label} is invalid")

    def path_projection(path: object) -> tuple[tuple[object, ...], ...]:
        if type(path) is not tuple or len(path) > 64:
            raise TypeError("Telepathy receipt path must be an exact tuple")
        projected: list[tuple[object, ...]] = []
        for step in path:
            if type(step) is member_step_type:
                raw_key = member_step_descriptors[0].__get__(
                    step,
                    member_step_type,
                )
                ordinal = member_step_descriptors[1].__get__(
                    step,
                    member_step_type,
                )
                if (
                    type(raw_key) is not str
                    or not raw_key
                    or len(raw_key.encode("utf-8")) > 4_096
                    or type(ordinal) is not int
                    or not 0 <= ordinal <= (1 << 63) - 1
                ):
                    raise ValueError(
                        "Telepathy receipt member path step is invalid"
                    )
                projected.append(("member", raw_key, ordinal))
            elif type(step) is index_step_type:
                ordinal = index_step_descriptors[0].__get__(
                    step,
                    index_step_type,
                )
                if (
                    type(ordinal) is not int
                    or not 0 <= ordinal <= (1 << 63) - 1
                ):
                    raise ValueError(
                        "Telepathy receipt index path step is invalid"
                    )
                projected.append(("index", ordinal))
            else:
                raise TypeError(
                    "Telepathy receipt path has a foreign step"
                )
        return tuple(projected)

    target = path_projection(target_path)
    carrier = path_projection(carrier_path)
    selection = path_projection(selection_path)
    if len(target) + len(carrier) + len(selection) > 64:
        raise ValueError("Telepathy receipt combined path exceeds its bound")
    if span is None:
        span_projection: tuple[int, int] | None = None
    elif type(span) is span_type:
        start = span_descriptors[0].__get__(span, span_type)
        end = span_descriptors[1].__get__(span, span_type)
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= (1 << 63) - 1
        ):
            raise ValueError("Telepathy receipt span is invalid")
        span_projection = (start, end)
    else:
        raise TypeError("Telepathy receipt span must be exact")
    return (
        ruleset,
        authority_digest,
        (
            source_id,
            locator,
            section_id,
            target,
            carrier,
            selection,
            span_projection,
        ),
        block_sha256,
        member_sha256,
        value_sha256,
        selection_sha256,
    )


def _receipt_projection_contract(
    structural_projector: Callable[..., tuple[object, ...]],
    receipt_type: type[SourceReceipt],
    address_type: type[SourceAddress],
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
    span_type: type[TextSpan],
) -> Callable[[object], tuple[object, ...]]:
    receipt_descriptors = tuple(
        receipt_type.__dict__[name]
        for name in (
            "ruleset",
            "authority_digest",
            "address",
            "block_sha256",
            "member_sha256",
            "value_sha256",
            "selection_sha256",
        )
    )
    address_descriptors = tuple(
        address_type.__dict__[name]
        for name in (
            "source_id",
            "locator",
            "section_id",
            "target_path",
            "carrier_path",
            "selection_path",
            "span",
        )
    )
    member_step_descriptors = tuple(
        member_step_type.__dict__[name]
        for name in ("raw_key", "member_ordinal")
    )
    index_step_descriptors = (
        index_step_type.__dict__["item_ordinal"],
    )
    span_descriptors = tuple(
        span_type.__dict__[name]
        for name in ("start", "end")
    )

    def project(receipt: object) -> tuple[object, ...]:
        return structural_projector(
            receipt,
            receipt_type,
            address_type,
            member_step_type,
            index_step_type,
            span_type,
            receipt_descriptors,
            address_descriptors,
            member_step_descriptors,
            index_step_descriptors,
            span_descriptors,
        )

    return project


_receipt_projection = _receipt_projection_contract(
    _receipt_projection_structure,
    SourceReceipt,
    SourceAddress,
    RawMemberStep,
    RawIndexStep,
    TextSpan,
)
del _receipt_projection_contract


def _serialize_receipt_structure(
    receipt: object,
    receipt_projection: Callable[[object], tuple[object, ...]],
    canonical_json_encoder: Callable[[Any], bytes],
    sha256_factory: Callable[[bytes], Any],
) -> SerializedObject:
    (
        ruleset,
        authority_digest,
        address,
        block_sha256,
        member_sha256,
        value_sha256,
        selection_sha256,
    ) = receipt_projection(receipt)
    (
        source_id,
        locator,
        section_id,
        target_path,
        carrier_path,
        selection_path,
        span,
    ) = address

    def path_wire(
        path: tuple[tuple[object, ...], ...],
    ) -> list[SerializedObject]:
        return [
            (
                {
                    "kind": "member",
                    "rawKey": step[1],
                    "memberOrdinal": step[2],
                }
                if step[0] == "member"
                else {
                    "kind": "index",
                    "itemOrdinal": step[1],
                }
            )
            for step in path
        ]

    body: SerializedObject = {
        "schema": 1,
        "kind": "pf2er-source-receipt",
        "ruleset": ruleset,
        "authorityDigest": authority_digest,
        "address": {
            "sourceId": source_id,
            "locator": locator,
            "sectionId": section_id,
            "targetPath": path_wire(target_path),
            "carrierPath": path_wire(carrier_path),
            "selectionPath": path_wire(selection_path),
            "span": (
                None
                if span is None
                else {
                    "start": span[0],
                    "end": span[1],
                }
            ),
        },
        "hashes": {
            "blockSha256": block_sha256,
            "memberSha256": member_sha256,
            "valueSha256": value_sha256,
            "selectionSha256": selection_sha256,
        },
    }
    return {
        **body,
        "digest": sha256_factory(
            canonical_json_encoder(body)
        ).hexdigest(),
    }


def _receipt_serializer_contract(
    structural_serializer: Callable[..., SerializedObject],
    receipt_projection: Callable[[object], tuple[object, ...]],
    canonical_json_encoder: Callable[[Any], bytes],
    sha256_factory: Callable[[bytes], Any],
) -> Callable[[object], SerializedObject]:
    def serialize(receipt: object) -> SerializedObject:
        return structural_serializer(
            receipt,
            receipt_projection,
            canonical_json_encoder,
            sha256_factory,
        )

    return serialize


_serialize_receipt = _receipt_serializer_contract(
    _serialize_receipt_structure,
    _receipt_projection,
    canonical_json_bytes,
    _sha256_factory,
)
del _receipt_serializer_contract
del _sha256_factory


def _selection_claim_structure(
    selection: object,
    authority: object,
    selection_type: type[VerifiedSourceSelection],
    carrier_type: type[VerifiedSourceCarrier],
    authority_type: type[SourceAuthorityAdapter],
    address_type: type[SourceAddress],
    receipt_type: type[SourceReceipt],
    raw_object_type: type[RawSourceObject],
    raw_member_type: type[RawSourceMember],
    raw_array_type: type[RawSourceArray],
    selection_descriptors: tuple[object, ...],
    carrier_descriptors: tuple[object, ...],
    authority_capability_descriptor: object,
    raw_object_members_descriptor: object,
    raw_member_descriptors: tuple[object, ...],
    raw_array_items_descriptor: object,
    raw_hash: Callable[[object], str],
    member_hash: Callable[[RawSourceMember], str],
    receipt_projection: Callable[[object], tuple[object, ...]],
    guard_external_contracts: Callable[[], None],
) -> tuple[Any, ...]:
    guard_external_contracts()
    if type(selection) is not selection_type:
        raise TypeError("Telepathy selection claim must be exact")
    if type(authority) is not authority_type:
        raise TypeError("Telepathy selection authority must be exact")
    try:
        (
            carrier,
            address,
            raw_value,
            raw_member,
            selected_value,
            member_sha256,
            value_sha256,
            selection_sha256,
            selection_capability,
        ) = tuple(
            descriptor.__get__(selection, selection_type)
            for descriptor in selection_descriptors
        )
    except (AttributeError, TypeError) as failure:
        raise TypeError(
            "Telepathy selection claim is incomplete"
        ) from failure
    if type(carrier) is not carrier_type:
        raise TypeError("Telepathy selection carrier must be exact")
    if type(address) is not address_type:
        raise TypeError("Telepathy selection address must be exact")
    try:
        (
            ruleset,
            authority_digest,
            carrier_source_id,
            carrier_locator,
            raw_block,
            block_sha256,
            carrier_capability,
        ) = tuple(
            descriptor.__get__(carrier, carrier_type)
            for descriptor in carrier_descriptors
        )
        authority_capability = authority_capability_descriptor.__get__(
            authority,
            authority_type,
        )
    except (AttributeError, TypeError) as failure:
        raise TypeError(
            "Telepathy selection authority binding is incomplete"
        ) from failure
    if (
        selection_capability is not authority_capability
        or carrier_capability is not authority_capability
    ):
        raise ValueError(
            "Telepathy selection belongs to another authority context"
        )
    if (
        type(carrier_source_id) is not str
        or type(carrier_locator) is not str
        or type(raw_block) is not raw_object_type
    ):
        raise TypeError(
            "Telepathy selection carrier fields are not exact"
        )
    receipt = object.__new__(receipt_type)
    for name, value in (
        ("ruleset", ruleset),
        ("authority_digest", authority_digest),
        ("address", address),
        ("block_sha256", block_sha256),
        ("member_sha256", member_sha256),
        ("value_sha256", value_sha256),
        ("selection_sha256", selection_sha256),
    ):
        object.__setattr__(receipt, name, value)
    projected_receipt = receipt_projection(receipt)
    if (
        raw_hash(raw_block) != block_sha256
        or raw_hash(raw_value) != value_sha256
        or raw_hash(selected_value) != selection_sha256
    ):
        raise ValueError(
            "Telepathy selection raw values disagree with their receipt"
        )
    if raw_member is None:
        if member_sha256 is not None:
            raise ValueError(
                "Telepathy selection member receipt is inconsistent"
            )
        raw_member_key = None
        raw_member_value = None
    elif type(raw_member) is raw_member_type:
        raw_member_key = raw_member_descriptors[0].__get__(
            raw_member,
            raw_member_type,
        )
        raw_member_value = raw_member_descriptors[1].__get__(
            raw_member,
            raw_member_type,
        )
        if (
            type(raw_member_key) is not str
            or member_hash(raw_member) != member_sha256
        ):
            raise ValueError(
                "Telepathy selection member disagrees with its receipt"
            )
    else:
        raise TypeError(
            "Telepathy selection raw member must be exact or absent"
        )

    block_members = raw_object_members_descriptor.__get__(
        raw_block,
        raw_object_type,
    )
    if (
        type(block_members) is not tuple
        or not block_members
        or len(block_members) > 4_096
        or any(
            type(member) is not raw_member_type
            for member in block_members
        )
    ):
        raise TypeError(
            "Telepathy selection carrier members are not exact"
        )

    def member_records(
        members: tuple[RawSourceMember, ...],
    ) -> tuple[
        tuple[
            RawSourceMember,
            str,
            object,
            tuple[object, ...] | None,
        ],
        ...,
    ]:
        records = tuple(
            (
                member,
                raw_member_descriptors[0].__get__(
                    member,
                    raw_member_type,
                ),
                raw_member_descriptors[1].__get__(
                    member,
                    raw_member_type,
                ),
                (
                    raw_array_items_descriptor.__get__(
                        raw_member_descriptors[1].__get__(
                            member,
                            raw_member_type,
                        ),
                        raw_array_type,
                    )
                    if type(
                        raw_member_descriptors[1].__get__(
                            member,
                            raw_member_type,
                        )
                    )
                    is raw_array_type
                    else None
                ),
            )
            for member in members
        )
        if any(
            type(record[1]) is not str
            or (
                record[3] is not None
                and type(record[3]) is not tuple
            )
            for record in records
        ):
            raise TypeError(
                "Telepathy selection member records are not exact"
            )
        return records

    block_records = member_records(block_members)
    if type(raw_value) is raw_object_type:
        value_members = raw_object_members_descriptor.__get__(
            raw_value,
            raw_object_type,
        )
        if (
            type(value_members) is not tuple
            or len(value_members) > 4_096
            or any(
                type(member) is not raw_member_type
                for member in value_members
            )
        ):
            raise TypeError(
                "Telepathy selected object members are not exact"
            )
        value_records = member_records(value_members)
        value_items = None
    elif type(raw_value) is raw_array_type:
        value_items = raw_array_items_descriptor.__get__(
            raw_value,
            raw_array_type,
        )
        if (
            type(value_items) is not tuple
            or len(value_items) > 4_096
        ):
            raise TypeError(
                "Telepathy selected array items are not exact"
            )
        value_records = None
    else:
        value_records = None
        value_items = None
    result = (
        receipt,
        address,
        projected_receipt,
        carrier_source_id,
        carrier_locator,
        raw_block,
        block_records,
        raw_member,
        raw_member_key,
        raw_member_value,
        raw_value,
        selected_value,
        value_records,
        value_items,
    )
    guard_external_contracts()
    return result


def _selection_claim_contract(
    structural_claim: Callable[..., tuple[Any, ...]],
    selection_type: type[VerifiedSourceSelection],
    carrier_type: type[VerifiedSourceCarrier],
    authority_type: type[SourceAuthorityAdapter],
    address_type: type[SourceAddress],
    receipt_type: type[SourceReceipt],
    raw_object_type: type[RawSourceObject],
    raw_member_type: type[RawSourceMember],
    raw_array_type: type[RawSourceArray],
    raw_hash: Callable[[object], str],
    member_hash: Callable[[RawSourceMember], str],
    receipt_projection: Callable[[object], tuple[object, ...]],
    guard_external_contracts: Callable[[], None],
) -> Callable[[object, object], tuple[Any, ...]]:
    selection_descriptors = tuple(
        selection_type.__dict__[name]
        for name in (
            "carrier",
            "address",
            "raw_value",
            "raw_member",
            "selected_value",
            "member_sha256",
            "value_sha256",
            "selection_sha256",
            "_capability",
        )
    )
    carrier_descriptors = tuple(
        carrier_type.__dict__[name]
        for name in (
            "ruleset",
            "authority_digest",
            "source_id",
            "locator",
            "raw_block",
            "block_sha256",
            "_capability",
        )
    )
    authority_capability_descriptor = (
        authority_type.__dict__["_capability"]
    )
    raw_object_members_descriptor = (
        raw_object_type.__dict__["members"]
    )
    raw_member_descriptors = tuple(
        raw_member_type.__dict__[name]
        for name in ("key", "value")
    )
    raw_array_items_descriptor = (
        raw_array_type.__dict__["items"]
    )

    def claim(
        selection: object,
        authority: object,
    ) -> tuple[Any, ...]:
        return structural_claim(
            selection,
            authority,
            selection_type,
            carrier_type,
            authority_type,
            address_type,
            receipt_type,
            raw_object_type,
            raw_member_type,
            raw_array_type,
            selection_descriptors,
            carrier_descriptors,
            authority_capability_descriptor,
            raw_object_members_descriptor,
            raw_member_descriptors,
            raw_array_items_descriptor,
            raw_hash,
            member_hash,
            receipt_projection,
            guard_external_contracts,
        )

    return claim


_selection_claim = _selection_claim_contract(
    _selection_claim_structure,
    VerifiedSourceSelection,
    VerifiedSourceCarrier,
    SourceAuthorityAdapter,
    SourceAddress,
    SourceReceipt,
    RawSourceObject,
    RawSourceMember,
    RawSourceArray,
    _captured_raw_hash,
    _captured_member_hash,
    _receipt_projection,
    _guard_external_contracts,
)
del _selection_claim_contract


def _reviewed_requirement_matches_structure(
    requirement: object,
    requirement_type: type[RuleRequirement],
    member_step_type: type[RawMemberStep],
    requirement_descriptors: tuple[object, ...],
    member_step_descriptors: tuple[object, ...],
) -> bool:
    if type(requirement) is not requirement_type:
        return False
    try:
        values = tuple(
            descriptor.__get__(requirement, requirement_type)
            for descriptor in requirement_descriptors
        )
    except (AttributeError, TypeError):
        return False
    carrier_path = values[3]
    selection_path = values[4]
    if (
        type(carrier_path) is not tuple
        or len(carrier_path) != 1
        or type(carrier_path[0]) is not member_step_type
        or type(selection_path) is not tuple
        or selection_path != ()
    ):
        return False
    step = carrier_path[0]
    try:
        raw_key = member_step_descriptors[0].__get__(
            step,
            member_step_type,
        )
        member_ordinal = member_step_descriptors[1].__get__(
            step,
            member_step_type,
        )
    except (AttributeError, TypeError):
        return False
    return (
        type(values[0]) is str
        and values[0] == "core-mc1:ability-glossary#^.ability[033]"
        and type(values[1]) is str
        and values[1] == "core-mc1"
        and type(values[2]) is str
        and values[2] == "358.2"
        and type(raw_key) is str
        and raw_key == "^.ability"
        and type(member_ordinal) is int
        and member_ordinal == 35
        and selection_path == ()
        and values[5] is None
        and values[6] is None
        and values[7] is None
        and type(values[8]) is str
        and values[8]
        == "472fd10f0a1f1f616ff947eacf7bcff4a44de9ed26200366e21653d2b0b9331e"
        and values[9] is None
    )


def _reviewed_requirement_matcher_contract(
    structural_matcher: Callable[..., bool],
    requirement_type: type[RuleRequirement],
    member_step_type: type[RawMemberStep],
) -> Callable[[object], bool]:
    requirement_descriptors = tuple(
        requirement_type.__dict__[name]
        for name in (
            "rule_id",
            "source_id",
            "locator",
            "carrier_path",
            "selection_path",
            "span",
            "expected_block_sha256",
            "expected_member_sha256",
            "expected_value_sha256",
            "expected_selection_sha256",
        )
    )
    member_step_descriptors = tuple(
        member_step_type.__dict__[name]
        for name in ("raw_key", "member_ordinal")
    )

    def matches(requirement: object) -> bool:
        return structural_matcher(
            requirement,
            requirement_type,
            member_step_type,
            requirement_descriptors,
            member_step_descriptors,
        )

    return matches


_reviewed_requirement_matches = _reviewed_requirement_matcher_contract(
    _reviewed_requirement_matches_structure,
    RuleRequirement,
    RawMemberStep,
)
del _reviewed_requirement_matcher_contract


def _resolve_provider_contract(
    requirement_factory: Callable[[], RuleRequirement],
    resolve_rule: Callable[
        [SourceAuthorityAdapter, RuleRequirement],
        VerifiedRuleReceipt,
    ],
) -> Callable[[SourceAuthorityAdapter], VerifiedRuleReceipt]:
    def resolve(
        authority: SourceAuthorityAdapter,
    ) -> VerifiedRuleReceipt:
        return resolve_rule(authority, requirement_factory())

    return resolve


_resolve_reviewed_provider = _resolve_provider_contract(
    _new_rule_requirement,
    SourceAuthorityAdapter.resolve_rule,
)
del _resolve_provider_contract


def _provider_matches_structure(
    provider: object,
    authority: SourceAuthorityAdapter,
    rule_type: type[VerifiedRuleReceipt],
    selection_type: type[VerifiedSourceSelection],
    address_type: type[SourceAddress],
    raw_object_type: type[RawSourceObject],
    raw_array_type: type[RawSourceArray],
    raw_member_type: type[RawSourceMember],
    member_step_type: type[RawMemberStep],
    receipt_type: type[SourceReceipt],
    requirement_matches: Callable[[object], bool],
    validate_rule: Callable[
        [SourceAuthorityAdapter, VerifiedRuleReceipt],
        VerifiedRuleReceipt,
    ],
    selection_claim: Callable[
        [object, object],
        tuple[Any, ...],
    ],
    rule_receipt_descriptor: object,
    receipt_projection: Callable[[object], tuple[object, ...]],
) -> bool:
    if type(provider) is not rule_type:
        return False
    validate_rule(authority, provider)
    try:
        requirement = object.__getattribute__(provider, "requirement")
        selection = object.__getattribute__(provider, "selection")
        receipt = rule_receipt_descriptor.__get__(provider, rule_type)
        rule_id = object.__getattribute__(provider, "rule_id")
    except (AttributeError, TypeError):
        return False
    if (
        not requirement_matches(requirement)
        or type(selection) is not selection_type
        or type(receipt) is not receipt_type
        or type(rule_id) is not str
        or rule_id != "core-mc1:ability-glossary#^.ability[033]"
    ):
        return False
    claim = selection_claim(selection, authority)
    if type(claim) is not tuple or len(claim) != 14:
        raise TypeError("Telepathy provider claim is not canonical")
    (
        claim_receipt,
        address,
        projected_claim,
        carrier_source_id,
        carrier_locator,
        raw_block,
        _block_records,
        raw_member,
        _raw_member_key,
        _raw_member_value,
        raw_value,
        selected_value,
        value_records,
        _value_items,
    ) = claim
    (
        claim_ruleset,
        _claim_authority_digest,
        projected_address,
        _claim_block_sha256,
        _claim_member_sha256,
        value_sha256,
        selection_sha256,
    ) = projected_claim
    (
        address_source_id,
        address_locator,
        _address_section_id,
        _target_path,
        carrier_path,
        selection_path,
        address_span,
    ) = projected_address
    if (
        type(address) is not address_type
        or claim_ruleset != "pf2er"
        or type(address_source_id) is not str
        or address_source_id != "core-mc1"
        or type(address_locator) is not str
        or address_locator != "358.2"
        or carrier_source_id != address_source_id
        or carrier_locator != address_locator
        or address_span is not None
        or type(selection_path) is not tuple
        or selection_path != ()
    ):
        return False
    if (
        type(carrier_path) is not tuple
        or len(carrier_path) != 1
        or carrier_path[0] != ("member", "^.ability", 35)
    ):
        return False
    if (
        type(raw_value) is not raw_object_type
        or selected_value is not raw_value
        or raw_block is not raw_value
        or raw_member is not None
        or type(value_records) is not tuple
    ):
        return False
    members = value_records
    member_keys = tuple(record[1] for record in members)
    if (
        type(members) is not tuple
        or len(members) != 3
        or any(type(key) is not str for key in member_keys)
        or member_keys != ("Name", "Traits", "Description")
    ):
        return False
    name = members[0][2]
    traits = members[1][2]
    description = members[2][2]
    trait_items = members[1][3]
    if (
        type(name) is not str
        or name != "Telepathy"
        or type(trait_items) is not tuple
        or len(trait_items) != 3
        or any(type(item) is not str for item in trait_items)
        or trait_items != ("aura", "magical", "mental")
        or type(description) is not str
        or description != (
            "A monster with telepathy can communicate mentally with any "
            "creatures within the listed radius, as long as they share a "
            "language. This doesn't give any special access to their "
            "thoughts and communicates no more information than normal "
            "speech would."
        )
        or type(value_sha256) is not str
        or value_sha256
        != "472fd10f0a1f1f616ff947eacf7bcff4a44de9ed26200366e21653d2b0b9331e"
        or type(selection_sha256) is not str
        or selection_sha256 != value_sha256
        or receipt_projection(receipt)
        != receipt_projection(claim_receipt)
    ):
        return False
    return True


def _provider_matcher_contract(
    structural_matcher: Callable[..., bool],
    rule_type: type[VerifiedRuleReceipt],
    selection_type: type[VerifiedSourceSelection],
    address_type: type[SourceAddress],
    raw_object_type: type[RawSourceObject],
    raw_array_type: type[RawSourceArray],
    raw_member_type: type[RawSourceMember],
    member_step_type: type[RawMemberStep],
    receipt_type: type[SourceReceipt],
    requirement_matches: Callable[[object], bool],
    validate_rule: Callable[
        [SourceAuthorityAdapter, VerifiedRuleReceipt],
        VerifiedRuleReceipt,
    ],
    selection_claim: Callable[
        [object, object],
        tuple[Any, ...],
    ],
    rule_receipt_descriptor: object,
    receipt_projection: Callable[[object], tuple[object, ...]],
) -> Callable[[object, SourceAuthorityAdapter], bool]:
    def matches(
        provider: object,
        authority: SourceAuthorityAdapter,
    ) -> bool:
        return structural_matcher(
            provider,
            authority,
            rule_type,
            selection_type,
            address_type,
            raw_object_type,
            raw_array_type,
            raw_member_type,
            member_step_type,
            receipt_type,
            requirement_matches,
            validate_rule,
            selection_claim,
            rule_receipt_descriptor,
            receipt_projection,
        )

    return matches


_provider_matches = _provider_matcher_contract(
    _provider_matches_structure,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    SourceAddress,
    RawSourceObject,
    RawSourceArray,
    RawSourceMember,
    RawMemberStep,
    SourceReceipt,
    _reviewed_requirement_matches,
    SourceAuthorityAdapter.validate_rule,
    _selection_claim,
    VerifiedRuleReceipt.__dict__["receipt"],
    _receipt_projection,
)
del _provider_matcher_contract


def _verified_parameters_structure(
    source: object,
    consumer: object,
    provider: object,
    authority: object,
    authority_type: type[SourceAuthorityAdapter],
    selection_type: type[VerifiedSourceSelection],
    rule_type: type[VerifiedRuleReceipt],
    carrier_type: type[VerifiedSourceCarrier],
    address_type: type[SourceAddress],
    receipt_type: type[SourceReceipt],
    raw_object_type: type[RawSourceObject],
    raw_member_type: type[RawSourceMember],
    raw_array_type: type[RawSourceArray],
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
    unbound_parameters: Callable[[object], object],
    provider_matches: Callable[
        [object, SourceAuthorityAdapter],
        bool,
    ],
    exact_path: Callable[[object, type, type], bool],
    validate_source: Callable[[object], None],
    raw_hash: Callable[[object], str],
    member_hash: Callable[[RawSourceMember], str],
    validate_selection: Callable[
        [SourceAuthorityAdapter, VerifiedSourceSelection],
        VerifiedSourceSelection,
    ],
    require_shared_authority: Callable[
        [
            SourceAuthorityAdapter,
            VerifiedSourceSelection,
            tuple[VerifiedRuleReceipt, ...],
        ],
        None,
    ],
    resolve_selection: Callable[
        [SourceAuthorityAdapter, SourceAddress],
        VerifiedSourceSelection,
    ],
    selection_claim: Callable[
        [object, object],
        tuple[Any, ...],
    ],
    receipt_projection: Callable[[object], tuple[object, ...]],
    rule_receipt_descriptor: object,
    guard_external_contracts: Callable[[], None],
) -> tuple[Any, ...] | None:
    guard_external_contracts()
    parameters = unbound_parameters(source)
    if parameters is None:
        return None
    if type(authority) is not authority_type:
        raise TypeError(
            "Telepathy authority must be an exact SourceAuthorityAdapter"
        )
    if type(consumer) is not selection_type:
        raise TypeError(
            "Telepathy consumer must be an exact VerifiedSourceSelection"
        )
    if type(provider) is not rule_type:
        raise TypeError(
            "Telepathy provider must be an exact VerifiedRuleReceipt"
        )
    guard_external_contracts()
    validate_selection(authority, consumer)
    guard_external_contracts()
    if not provider_matches(provider, authority):
        return None
    guard_external_contracts()
    require_shared_authority(authority, consumer, (provider,))
    guard_external_contracts()
    consumer_claim = selection_claim(
        consumer,
        authority,
    )
    if type(consumer_claim) is not tuple or len(consumer_claim) != 14:
        raise TypeError("Telepathy consumer claim is not canonical")
    consumer_receipt = consumer_claim[0]
    consumer_address = consumer_claim[1]
    consumer_projection = consumer_claim[2]
    if (
        type(consumer_receipt) is not receipt_type
        or type(consumer_address) is not address_type
        or type(consumer_projection) is not tuple
    ):
        raise TypeError("Telepathy consumer claim fields must be exact")
    guard_external_contracts()
    fresh = resolve_selection(authority, consumer_address)
    guard_external_contracts()
    if type(fresh) is not selection_type:
        raise TypeError("Telepathy authority returned a foreign selection")
    validate_selection(authority, fresh)
    guard_external_contracts()
    fresh_claim = selection_claim(fresh, authority)
    if type(fresh_claim) is not tuple or len(fresh_claim) != 14:
        raise TypeError("Telepathy canonical claim is not exact")
    (
        fresh_receipt,
        fresh_address,
        fresh_projection,
        carrier_source_id,
        carrier_locator,
        raw_block,
        members,
        fresh_member,
        fresh_member_key,
        fresh_member_value,
        fresh_value,
        selected_value,
        _value_records,
        fresh_value_items,
    ) = fresh_claim
    if (
        type(fresh_receipt) is not receipt_type
        or type(fresh_address) is not address_type
        or consumer_projection != fresh_projection
        or receipt_projection(consumer_receipt) != fresh_projection
        or receipt_projection(fresh_receipt) != fresh_projection
    ):
        raise ValueError(
            "Telepathy consumer claim disagrees with canonical resolution"
        )
    (
        source_index,
        source_text,
        source_value_sha256,
        mode,
        range_feet,
        touch_qualifier,
        grammar,
        page_reference,
        remaining,
        source_id,
        locator,
        creature_name,
        source_member,
    ) = parameters
    (
        fresh_ruleset,
        _fresh_authority_digest,
        address_projection,
        _fresh_block_sha256,
        fresh_member_sha256,
        fresh_value_sha256,
        fresh_selection_sha256,
    ) = fresh_projection
    (
        address_source_id,
        address_locator,
        _address_section_id,
        _target_path,
        carrier_path,
        selection_path,
        address_span,
    ) = address_projection
    if (
        type(fresh_address) is not address_type
        or type(raw_block) is not raw_object_type
        or fresh_ruleset != "pf2er"
        or address_span is not None
        or address_source_id != source_id
        or address_locator != locator
        or source_id != "core-mc1"
        or carrier_source_id != source_id
        or carrier_locator != locator
    ):
        return None
    if (
        not carrier_path
        or type(carrier_path[-1]) is not tuple
        or len(carrier_path[-1]) != 3
        or carrier_path[-1][0] != "member"
        or carrier_path[-1][1] != "^.creature"
        or len(selection_path) != 1
        or type(selection_path[0]) is not tuple
        or selection_path[0][:2] != ("member", "Languages")
    ):
        return None
    field_ordinal = selection_path[0][2]
    if (
        type(members) is not tuple
        or not members
        or len(members) > 4_096
        or type(field_ordinal) is not int
        or field_ordinal >= len(members)
    ):
        return None
    if (
        type(fresh_member) is not raw_member_type
        or fresh_member is not members[field_ordinal][0]
        or fresh_member_key != "Languages"
        or fresh_member_value is not fresh_value
        or selected_value is not fresh_value
        or member_hash(source_member) != member_hash(fresh_member)
        or fresh_member_sha256 != member_hash(fresh_member)
        or fresh_value_sha256 != raw_hash(fresh_value)
        or fresh_selection_sha256 != fresh_value_sha256
    ):
        return None
    normalized_languages = tuple(
        record
        for record in members
        if record[1].strip().casefold() == "languages"
    )
    exact_languages = tuple(
        record for record in members if record[1] == "Languages"
    )
    names = tuple(
        record[2] for record in members if record[1] == "Name"
    )
    if (
        len(normalized_languages) != 1
        or len(exact_languages) != 1
        or exact_languages[0][0] is not fresh_member
        or len(names) != 1
        or type(names[0]) is not str
        or names[0] != creature_name
    ):
        return None
    if type(fresh_value) is str:
        fresh_entries = (fresh_value,)
    elif type(fresh_value) is raw_array_type:
        fresh_entries = fresh_value_items
    else:
        return None
    if (
        type(fresh_entries) is not tuple
        or any(type(entry) is not str for entry in fresh_entries)
        or source_index >= len(fresh_entries)
        or fresh_entries[source_index] != source_text
        or remaining
        != fresh_entries[:source_index] + fresh_entries[source_index + 1 :]
        or source_value_sha256 != raw_hash(source_text)
    ):
        return None
    validate_source(source)
    guard_external_contracts()
    return (
        source_index,
        source_text,
        source_value_sha256,
        mode,
        range_feet,
        touch_qualifier,
        grammar,
        page_reference,
        remaining,
        fresh_receipt,
        rule_receipt_descriptor.__get__(provider, rule_type),
    )


def _verified_parameters_contract(
    structural_validator: Callable[..., object],
    authority_type: type[SourceAuthorityAdapter],
    selection_type: type[VerifiedSourceSelection],
    rule_type: type[VerifiedRuleReceipt],
    carrier_type: type[VerifiedSourceCarrier],
    address_type: type[SourceAddress],
    receipt_type: type[SourceReceipt],
    raw_object_type: type[RawSourceObject],
    raw_member_type: type[RawSourceMember],
    raw_array_type: type[RawSourceArray],
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
    unbound_parameters: Callable[[object], object],
    provider_matches: Callable[[object, SourceAuthorityAdapter], bool],
    exact_path: Callable[[object, type, type], bool],
    validate_source: Callable[[object], None],
    raw_hash: Callable[[object], str],
    member_hash: Callable[[RawSourceMember], str],
    validate_selection: Callable[
        [SourceAuthorityAdapter, VerifiedSourceSelection],
        VerifiedSourceSelection,
    ],
    require_shared_authority: Callable[
        [
            SourceAuthorityAdapter,
            VerifiedSourceSelection,
            tuple[VerifiedRuleReceipt, ...],
        ],
        None,
    ],
    resolve_selection: Callable[
        [SourceAuthorityAdapter, SourceAddress],
        VerifiedSourceSelection,
    ],
    selection_claim: Callable[
        [object, object],
        tuple[Any, ...],
    ],
    receipt_projection: Callable[[object], tuple[object, ...]],
    rule_receipt_descriptor: object,
    guard_external_contracts: Callable[[], None],
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
            authority_type,
            selection_type,
            rule_type,
            carrier_type,
            address_type,
            receipt_type,
            raw_object_type,
            raw_member_type,
            raw_array_type,
            member_step_type,
            index_step_type,
            unbound_parameters,
            provider_matches,
            exact_path,
            validate_source,
            raw_hash,
            member_hash,
            validate_selection,
            require_shared_authority,
            resolve_selection,
            selection_claim,
            receipt_projection,
            rule_receipt_descriptor,
            guard_external_contracts,
        )

    return validate


_verified_parameters = _verified_parameters_contract(
    _verified_parameters_structure,
    SourceAuthorityAdapter,
    VerifiedSourceSelection,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    SourceAddress,
    SourceReceipt,
    RawSourceObject,
    RawSourceMember,
    RawSourceArray,
    RawMemberStep,
    RawIndexStep,
    _unbound_parameters,
    _provider_matches,
    _exact_authority_path,
    _validate_source,
    _captured_raw_hash,
    _captured_member_hash,
    SourceAuthorityAdapter.validate_selection,
    SourceAuthorityAdapter.require_shared_authority,
    SourceAuthorityAdapter.resolve,
    _selection_claim,
    _receipt_projection,
    VerifiedRuleReceipt.__dict__["receipt"],
    _guard_external_contracts,
)
del _verified_parameters_contract


def _mechanic_for_structure(
    mode: TelepathyMode,
    range_feet: int | None,
    touch_qualifier: str | None,
    freeze_json: Callable[[Any], Any],
) -> Mapping[str, Any]:
    if mode == "radius":
        if (
            type(range_feet) is not int
            or not 1 <= range_feet <= (1 << 63) - 1
            or touch_qualifier is not None
        ):
            raise ValueError("radius Telepathy parameters are invalid")
    elif mode == "touch":
        if (
            range_feet is not None
            or touch_qualifier not in ("touch", "touch only")
        ):
            raise ValueError("touch Telepathy parameters are invalid")
    else:
        raise ValueError("Telepathy mode is invalid")
    mechanic: dict[str, Any] = {
        "type": "telepathy",
        "familyId": "telepathy",
        "kind": "passive",
        "actionCost": None,
        "channel": "mental",
        "traits": ["aura", "magical", "mental"],
        "mode": mode,
        "touchQualifier": touch_qualifier,
        "requiresSharedLanguage": True,
        "capabilityTokenIsLanguage": False,
        "thoughtAccess": False,
        "informationLimit": "normal-speech",
        "visibilityRequired": False,
        "detectionGranted": False,
        "rules": {
            "telepathy": {
                "ruleId": "core-mc1:ability-glossary#^.ability[033]",
                "sourceId": "core-mc1",
                "locator": "358.2",
                "matchingKeyOrdinal": 33,
                "absoluteMemberOrdinal": 35,
                "orderedMemberSha256": (
                    "2257f12121ba6dc9459643efbba9fb476c6767979199e1c4"
                    "f49c3af6fc38d50a"
                ),
                "orderedValueSha256": (
                    "0024942041f95f836bf0023411767b2cd194d75736a226ca"
                    "2c8279795d8baacf"
                ),
            }
        },
    }
    if mode == "radius":
        mechanic["rangeFeet"] = range_feet
    return freeze_json(mechanic)


def _mechanic_contract(
    structural_builder: Callable[..., Mapping[str, Any]],
    freeze_json: Callable[[Any], Any],
) -> Callable[
    [TelepathyMode, int | None, str | None],
    Mapping[str, Any],
]:
    def build(
        mode: TelepathyMode,
        range_feet: int | None,
        touch_qualifier: str | None,
    ) -> Mapping[str, Any]:
        return structural_builder(
            mode,
            range_feet,
            touch_qualifier,
            freeze_json,
        )

    return build


_mechanic_for = _mechanic_contract(
    _mechanic_for_structure,
    _freeze_json,
)
del _mechanic_contract


def _canonical_mechanic_contract(
    builder: Callable[
        [TelepathyMode, int | None, str | None],
        Mapping[str, Any],
    ],
) -> Callable[[object], Mapping[str, Any]]:
    def build(patch: object) -> Mapping[str, Any]:
        return builder(
            object.__getattribute__(patch, "_mode"),
            object.__getattribute__(patch, "_range_feet"),
            object.__getattribute__(patch, "_touch_qualifier"),
        )

    return build


_canonical_mechanic = _canonical_mechanic_contract(_mechanic_for)
del _canonical_mechanic_contract


_bind_patch_validator, _patch_validation_method = (
    _late_validation_method("Telepathy patch")
)


def _patch_copy_blocker(label: str) -> Callable[..., object]:
    def blocked(*_args: object, **_kwargs: object) -> object:
        raise TypeError(f"{label} cannot be copied or pickled")

    return blocked


_patch_public_method = _validated_method_contract(
    _patch_validation_method,
    _canonical_mechanic,
    _thaw_json,
    LanguageCapabilitySource.as_serialized,
    TelepathyRuleReceipt.as_serialized,
    RelationalCommunicationDependency.as_serialized,
    _serialize_receipt,
)


@final
@dataclass(frozen=True, slots=True, init=False)
class TelepathyCompilerPatch(metaclass=_SealedTelepathyType):
    """One verified passive channel with runtime explicitly deferred."""

    _source: LanguageCapabilitySource = field(
        repr=False,
        compare=False,
    )
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
    _source_index: int
    _source_text: str
    _source_value_sha256: str
    _mode: TelepathyMode
    _range_feet: int | None
    _touch_qualifier: str | None
    _grammar: str
    _page_reference: int | None
    _remaining_language_entries: tuple[str, ...]
    _consumer_receipt: SourceReceipt
    _provider_source_receipt: SourceReceipt
    _provider: TelepathyRuleReceipt
    _dependencies: tuple[RelationalCommunicationDependency, ...]
    _runtime_ready: bool

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "TelepathyCompilerPatch must be created by compile_telepathy"
        )

    __copy__ = _patch_copy_blocker("TelepathyCompilerPatch")
    __deepcopy__ = _patch_copy_blocker("TelepathyCompilerPatch")
    __reduce__ = _patch_copy_blocker("TelepathyCompilerPatch")
    __reduce_ex__ = _patch_copy_blocker("TelepathyCompilerPatch")

    @property
    @_patch_public_method
    def source(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> LanguageCapabilitySource:
        return object.__getattribute__(self, "_source")

    @property
    @_patch_public_method
    def source_index(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> int:
        return object.__getattribute__(self, "_source_index")

    @property
    @_patch_public_method
    def source_text(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> str:
        return object.__getattribute__(self, "_source_text")

    @property
    @_patch_public_method
    def source_value_sha256(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> str:
        return object.__getattribute__(self, "_source_value_sha256")

    @property
    @_patch_public_method
    def mode(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> TelepathyMode:
        return object.__getattribute__(self, "_mode")

    @property
    @_patch_public_method
    def range_feet(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> int | None:
        return object.__getattribute__(self, "_range_feet")

    @property
    @_patch_public_method
    def touch_qualifier(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> str | None:
        return object.__getattribute__(self, "_touch_qualifier")

    @property
    @_patch_public_method
    def grammar(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> str:
        return object.__getattribute__(self, "_grammar")

    @property
    @_patch_public_method
    def page_reference(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> int | None:
        return object.__getattribute__(self, "_page_reference")

    @property
    @_patch_public_method
    def remaining_language_entries(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> tuple[str, ...]:
        return object.__getattribute__(
            self,
            "_remaining_language_entries",
        )

    @property
    @_patch_public_method
    def provider(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> TelepathyRuleReceipt:
        return object.__getattribute__(self, "_provider")

    @property
    @_patch_public_method
    def dependencies(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> tuple[RelationalCommunicationDependency, ...]:
        return object.__getattribute__(self, "_dependencies")

    @property
    @_patch_public_method
    def mechanic(
        self,
        canonical_mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> Mapping[str, Any]:
        return canonical_mechanic(self)

    @property
    @_patch_public_method
    def mechanic_type(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> str:
        return "telepathy"

    @property
    @_patch_public_method
    def consumer(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> SourceReceipt:
        return object.__getattribute__(self, "_consumer_receipt")

    @property
    @_patch_public_method
    def verified_provider(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> SourceReceipt:
        return object.__getattribute__(
            self,
            "_provider_source_receipt",
        )

    @property
    @_patch_public_method
    def runtime_ready(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> bool:
        return object.__getattribute__(self, "_runtime_ready")

    @property
    @_patch_public_method
    def deferred_mechanics(
        self,
        _mechanic: Callable[[object], Mapping[str, Any]],
        _thaw: Callable[[Any], Any],
        _serialize_source: Callable[[object], SerializedObject],
        _serialize_provider: Callable[[object], SerializedObject],
        _serialize_dependency: Callable[[object], SerializedObject],
        _serialize_receipt: Callable[[object], SerializedObject],
    ) -> tuple[str, ...]:
        return tuple(
            object.__getattribute__(dependency, "dependency_id")
            for dependency in object.__getattribute__(
                self,
                "_dependencies",
            )
        )

    @_patch_public_method
    def as_serialized(
        self,
        canonical_mechanic: Callable[[object], Mapping[str, Any]],
        thaw: Callable[[Any], Any],
        serialize_source: Callable[[object], SerializedObject],
        serialize_provider: Callable[[object], SerializedObject],
        serialize_dependency: Callable[[object], SerializedObject],
        serialize_receipt: Callable[[object], SerializedObject],
    ) -> SerializedObject:
        source = object.__getattribute__(self, "_source")
        consumer = object.__getattribute__(self, "_consumer_receipt")
        provider_receipt = object.__getattribute__(
            self,
            "_provider_source_receipt",
        )
        provider = object.__getattribute__(self, "_provider")
        source_wire = serialize_source(source)
        source_wire["receipt"] = serialize_receipt(consumer)
        return {
            "compileSupported": True,
            "linkSupported": True,
            "runtimeSupported": False,
            "registryStatus": "unregistered",
            "mechanic": thaw(canonical_mechanic(self)),
            "grammar": object.__getattribute__(self, "_grammar"),
            "pageReference": object.__getattribute__(
                self,
                "_page_reference",
            ),
            "sourceToken": {
                "field": "Languages",
                "sourceIndex": object.__getattribute__(
                    self,
                    "_source_index",
                ),
                "sourceText": object.__getattribute__(
                    self,
                    "_source_text",
                ),
                "sourceValueSha256": object.__getattribute__(
                    self,
                    "_source_value_sha256",
                ),
            },
            "source": source_wire,
            "provider": {
                **serialize_provider(provider),
                "receipt": serialize_receipt(provider_receipt),
            },
            "remainingLanguageEntries": list(
                object.__getattribute__(
                    self,
                    "_remaining_language_entries",
                )
            ),
            "runtimeDependencies": [
                serialize_dependency(dependency)
                for dependency in object.__getattribute__(
                    self,
                    "_dependencies",
                )
            ],
            "deferredMechanics": [
                object.__getattribute__(dependency, "dependency_id")
                for dependency in object.__getattribute__(
                    self,
                    "_dependencies",
                )
            ],
        }


del _patch_copy_blocker
del _patch_public_method


def _new_patch_structure(
    *,
    source: LanguageCapabilitySource,
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
    provider_rule: VerifiedRuleReceipt,
    parameters: tuple[Any, ...],
    patch_type: type[TelepathyCompilerPatch],
    new_rule_receipt: Callable[[], TelepathyRuleReceipt],
    dependencies_for: Callable[
        [TelepathyMode],
        tuple[RelationalCommunicationDependency, ...],
    ],
    validate_patch: Callable[[object], None],
) -> TelepathyCompilerPatch:
    (
        source_index,
        source_text,
        source_value_sha256,
        mode,
        range_feet,
        touch_qualifier,
        grammar,
        page_reference,
        remaining,
        consumer_receipt,
        provider_receipt,
    ) = parameters
    patch = object.__new__(patch_type)
    for name, value in (
        ("_source", source),
        ("_authority", authority),
        ("_consumer_selection", consumer),
        ("_provider_rule", provider_rule),
        ("_source_index", source_index),
        ("_source_text", source_text),
        ("_source_value_sha256", source_value_sha256),
        ("_mode", mode),
        ("_range_feet", range_feet),
        ("_touch_qualifier", touch_qualifier),
        ("_grammar", grammar),
        ("_page_reference", page_reference),
        ("_remaining_language_entries", remaining),
        ("_consumer_receipt", consumer_receipt),
        ("_provider_source_receipt", provider_receipt),
        ("_provider", new_rule_receipt()),
        ("_dependencies", dependencies_for(mode)),
        ("_runtime_ready", False),
    ):
        object.__setattr__(patch, name, value)
    validate_patch(patch)
    return patch


def _patch_factory_gateway() -> tuple[
    Callable[[Callable[[object], None]], None],
    Callable[..., TelepathyCompilerPatch],
]:
    validator: Callable[[object], None] | None = None

    def bind(value: Callable[[object], None]) -> None:
        nonlocal validator
        if validator is not None:
            raise RuntimeError("Telepathy patch factory is already bound")
        validator = value

    def new(
        *,
        source: LanguageCapabilitySource,
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
        provider_rule: VerifiedRuleReceipt,
        parameters: tuple[Any, ...],
        structural_factory: Callable[..., TelepathyCompilerPatch],
        patch_type: type[TelepathyCompilerPatch],
        new_rule_receipt: Callable[[], TelepathyRuleReceipt],
        dependencies_for: Callable[
            [TelepathyMode],
            tuple[RelationalCommunicationDependency, ...],
        ],
    ) -> TelepathyCompilerPatch:
        if validator is None:
            raise RuntimeError("Telepathy patch factory is not bound")
        return structural_factory(
            source=source,
            authority=authority,
            consumer=consumer,
            provider_rule=provider_rule,
            parameters=parameters,
            patch_type=patch_type,
            new_rule_receipt=new_rule_receipt,
            dependencies_for=dependencies_for,
            validate_patch=validator,
        )

    return bind, new


_bind_patch_factory, _patch_factory_gateway_method = (
    _patch_factory_gateway()
)
del _patch_factory_gateway


def _new_patch_contract(
    gateway: Callable[..., TelepathyCompilerPatch],
    structural_factory: Callable[..., TelepathyCompilerPatch],
    patch_type: type[TelepathyCompilerPatch],
    new_rule_receipt: Callable[[], TelepathyRuleReceipt],
    dependencies_for: Callable[
        [TelepathyMode],
        tuple[RelationalCommunicationDependency, ...],
    ],
) -> Callable[..., TelepathyCompilerPatch]:
    def new(
        *,
        source: LanguageCapabilitySource,
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
        provider_rule: VerifiedRuleReceipt,
        parameters: tuple[Any, ...],
    ) -> TelepathyCompilerPatch:
        return gateway(
            source=source,
            authority=authority,
            consumer=consumer,
            provider_rule=provider_rule,
            parameters=parameters,
            structural_factory=structural_factory,
            patch_type=patch_type,
            new_rule_receipt=new_rule_receipt,
            dependencies_for=dependencies_for,
        )

    return new


_new_patch = _new_patch_contract(
    _patch_factory_gateway_method,
    _new_patch_structure,
    TelepathyCompilerPatch,
    _new_rule_receipt,
    _dependencies_for,
)
del _new_patch_contract
del _patch_factory_gateway_method


def _dependency_values(
    dependency: object,
) -> tuple[object, ...]:
    return tuple(
        object.__getattribute__(dependency, name)
        for name in (
            "dependency_id",
            "phase",
            "relation",
            "required_contract",
            "modes",
        )
    )


def _validate_patch_structure(
    patch: object,
    patch_type: type[TelepathyCompilerPatch],
    source_type: type[LanguageCapabilitySource],
    authority_type: type[SourceAuthorityAdapter],
    selection_type: type[VerifiedSourceSelection],
    rule_type: type[VerifiedRuleReceipt],
    receipt_type: type[SourceReceipt],
    provider_type: type[TelepathyRuleReceipt],
    dependency_type: type[RelationalCommunicationDependency],
    verified_parameters: Callable[
        [object, object, object, object],
        object,
    ],
    validate_provider: Callable[[object], None],
    validate_dependency: Callable[[object], None],
    dependencies_for: Callable[
        [TelepathyMode],
        tuple[RelationalCommunicationDependency, ...],
    ],
    dependency_values: Callable[[object], tuple[object, ...]],
    receipt_projection: Callable[[object], tuple[object, ...]],
    canonical_mechanic: Callable[[object], Mapping[str, Any]],
    thaw_json: Callable[[Any], Any],
    canonical_json_encoder: Callable[[Any], bytes],
) -> None:
    if type(patch) is not patch_type:
        raise TypeError(
            "Telepathy patch must have the exact TelepathyCompilerPatch type"
        )
    names = (
        "_source",
        "_authority",
        "_consumer_selection",
        "_provider_rule",
        "_source_index",
        "_source_text",
        "_source_value_sha256",
        "_mode",
        "_range_feet",
        "_touch_qualifier",
        "_grammar",
        "_page_reference",
        "_remaining_language_entries",
        "_consumer_receipt",
        "_provider_source_receipt",
        "_provider",
        "_dependencies",
        "_runtime_ready",
    )
    try:
        values = {
            name: object.__getattribute__(patch, name)
            for name in names
        }
    except (AttributeError, TypeError) as failure:
        raise TypeError("Telepathy patch is incomplete") from failure
    if (
        type(values["_source"]) is not source_type
        or type(values["_authority"]) is not authority_type
        or type(values["_consumer_selection"]) is not selection_type
        or type(values["_provider_rule"]) is not rule_type
        or type(values["_consumer_receipt"]) is not receipt_type
        or type(values["_provider_source_receipt"]) is not receipt_type
        or type(values["_provider"]) is not provider_type
        or type(values["_dependencies"]) is not tuple
        or any(
            type(item) is not dependency_type
            for item in values["_dependencies"]
        )
        or values["_runtime_ready"] is not False
    ):
        raise TypeError("Telepathy patch fields have foreign types")
    source_index = values["_source_index"]
    source_text = values["_source_text"]
    source_value_sha256 = values["_source_value_sha256"]
    mode = values["_mode"]
    range_feet = values["_range_feet"]
    touch_qualifier = values["_touch_qualifier"]
    grammar = values["_grammar"]
    page_reference = values["_page_reference"]
    remaining = values["_remaining_language_entries"]
    if (
        type(source_index) is not int
        or not 0 <= source_index <= 4_096
        or type(source_text) is not str
        or len(source_text.encode("utf-8")) > 4_096
        or type(source_value_sha256) is not str
        or len(source_value_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in source_value_sha256
        )
        or type(mode) is not str
        or mode not in ("radius", "touch")
        or (
            mode == "radius"
            and (
                type(range_feet) is not int
                or not 1 <= range_feet <= (1 << 63) - 1
                or touch_qualifier is not None
            )
        )
        or (
            mode == "touch"
            and (
                range_feet is not None
                or type(touch_qualifier) is not str
                or touch_qualifier not in ("touch", "touch only")
            )
        )
        or type(grammar) is not str
        or grammar
        not in (
            "numeric-radius",
            "numeric-radius-page-360",
            "touch-page-360",
            "touch-only-page-360",
        )
        or (
            page_reference is not None
            and (
                type(page_reference) is not int
                or page_reference != 360
            )
        )
        or type(remaining) is not tuple
        or len(remaining) > 4_096
        or any(
            type(entry) is not str
            or len(entry.encode("utf-8")) > 4_096
            for entry in remaining
        )
    ):
        raise TypeError("Telepathy patch scalar fields are not canonical")
    parameters = verified_parameters(
        values["_source"],
        values["_consumer_selection"],
        values["_provider_rule"],
        values["_authority"],
    )
    if parameters is None:
        raise ValueError(
            "Telepathy patch no longer matches its verified source"
        )
    if (
        type(parameters) is not tuple
        or len(parameters) != 11
        or type(parameters[9]) is not receipt_type
        or type(parameters[10]) is not receipt_type
    ):
        raise TypeError("Telepathy verified parameters are not canonical")
    expected_scalars = parameters[:9]
    actual_scalars = tuple(
        values[name]
        for name in (
            "_source_index",
            "_source_text",
            "_source_value_sha256",
            "_mode",
            "_range_feet",
            "_touch_qualifier",
            "_grammar",
            "_page_reference",
            "_remaining_language_entries",
        )
    )
    if actual_scalars != expected_scalars:
        raise ValueError(
            "Telepathy patch semantics changed after compilation"
        )
    if (
        receipt_projection(values["_consumer_receipt"])
        != receipt_projection(parameters[9])
        or receipt_projection(values["_provider_source_receipt"])
        != receipt_projection(parameters[10])
    ):
        raise ValueError("Telepathy patch receipts changed")
    validate_provider(values["_provider"])
    expected_dependencies = dependencies_for(values["_mode"])
    if (
        len(values["_dependencies"]) != len(expected_dependencies)
        or tuple(
            dependency_values(item)
            for item in values["_dependencies"]
        )
        != tuple(
            dependency_values(item)
            for item in expected_dependencies
        )
    ):
        raise ValueError(
            "Telepathy patch deferrals are not the complete reviewed order"
        )
    for dependency in values["_dependencies"]:
        validate_dependency(dependency)
    mechanic = canonical_mechanic(patch)
    wire = thaw_json(mechanic)
    canonical_json_encoder(wire)


def _patch_validator_contract(
    structural_validator: Callable[..., None],
    patch_type: type[TelepathyCompilerPatch],
    source_type: type[LanguageCapabilitySource],
    authority_type: type[SourceAuthorityAdapter],
    selection_type: type[VerifiedSourceSelection],
    rule_type: type[VerifiedRuleReceipt],
    receipt_type: type[SourceReceipt],
    provider_type: type[TelepathyRuleReceipt],
    dependency_type: type[RelationalCommunicationDependency],
    verified_parameters: Callable[
        [object, object, object, object],
        object,
    ],
    validate_provider: Callable[[object], None],
    validate_dependency: Callable[[object], None],
    dependencies_for: Callable[
        [TelepathyMode],
        tuple[RelationalCommunicationDependency, ...],
    ],
    dependency_values: Callable[[object], tuple[object, ...]],
    receipt_projection: Callable[[object], tuple[object, ...]],
    canonical_mechanic: Callable[[object], Mapping[str, Any]],
    thaw_json: Callable[[Any], Any],
    canonical_json_encoder: Callable[[Any], bytes],
) -> Callable[[object], None]:
    def validate(patch: object) -> None:
        structural_validator(
            patch,
            patch_type,
            source_type,
            authority_type,
            selection_type,
            rule_type,
            receipt_type,
            provider_type,
            dependency_type,
            verified_parameters,
            validate_provider,
            validate_dependency,
            dependencies_for,
            dependency_values,
            receipt_projection,
            canonical_mechanic,
            thaw_json,
            canonical_json_encoder,
        )

    return validate


_validate_patch = _patch_validator_contract(
    _validate_patch_structure,
    TelepathyCompilerPatch,
    LanguageCapabilitySource,
    SourceAuthorityAdapter,
    VerifiedSourceSelection,
    VerifiedRuleReceipt,
    SourceReceipt,
    TelepathyRuleReceipt,
    RelationalCommunicationDependency,
    _verified_parameters,
    _validate_rule_receipt,
    _validate_dependency,
    _dependencies_for,
    _dependency_values,
    _receipt_projection,
    _canonical_mechanic,
    _thaw_json,
    canonical_json_bytes,
)
_bind_patch_validator(_validate_patch)
_bind_patch_factory(_validate_patch)
_seal_telepathy_type(TelepathyCompilerPatch)
del _bind_patch_validator
del _bind_patch_factory
del _patch_validation_method
del _patch_validator_contract


def _compile_telepathy_structure(
    source: object,
    consumer: object,
    authority: object,
    authority_type: type[SourceAuthorityAdapter],
    unbound_parameters: Callable[[object], object],
    resolve_provider: Callable[
        [SourceAuthorityAdapter],
        VerifiedRuleReceipt,
    ],
    verified_parameters: Callable[
        [object, object, object, object],
        object,
    ],
    new_patch: Callable[..., TelepathyCompilerPatch],
    validate_patch: Callable[[object], None],
    patch_type: type[TelepathyCompilerPatch],
    guard_external_contracts: Callable[[], None],
) -> TelepathyCompilerPatch | None:
    guard_external_contracts()
    if type(authority) is not authority_type:
        raise TypeError(
            "Telepathy authority must be an exact SourceAuthorityAdapter"
        )
    if unbound_parameters(source) is None:
        return None
    provider = resolve_provider(authority)
    guard_external_contracts()
    parameters = verified_parameters(
        source,
        consumer,
        provider,
        authority,
    )
    if parameters is None:
        return None
    patch = new_patch(
        source=source,
        authority=authority,
        consumer=consumer,
        provider_rule=provider,
        parameters=parameters,
    )
    if type(patch) is not patch_type:
        raise TypeError("Telepathy compiler returned a foreign patch")
    validate_patch(patch)
    guard_external_contracts()
    return patch


def _compiler_contract(
    structural_compiler: Callable[..., object],
    authority_type: type[SourceAuthorityAdapter],
    unbound_parameters: Callable[[object], object],
    resolve_provider: Callable[
        [SourceAuthorityAdapter],
        VerifiedRuleReceipt,
    ],
    verified_parameters: Callable[
        [object, object, object, object],
        object,
    ],
    new_patch: Callable[..., TelepathyCompilerPatch],
    validate_patch: Callable[[object], None],
    patch_type: type[TelepathyCompilerPatch],
    guard_external_contracts: Callable[[], None],
) -> Callable[
    [object, object, object],
    TelepathyCompilerPatch | None,
]:
    def compile(
        source: object,
        consumer: object,
        authority: object,
        /,
    ) -> TelepathyCompilerPatch | None:
        result = structural_compiler(
            source,
            consumer,
            authority,
            authority_type,
            unbound_parameters,
            resolve_provider,
            verified_parameters,
            new_patch,
            validate_patch,
            patch_type,
            guard_external_contracts,
        )
        if result is not None and type(result) is not patch_type:
            raise TypeError(
                "Telepathy compiler returned a foreign result"
            )
        return result

    return compile


compile_telepathy = _compiler_contract(
    _compile_telepathy_structure,
    SourceAuthorityAdapter,
    _unbound_parameters,
    _resolve_reviewed_provider,
    _verified_parameters,
    _new_patch,
    _validate_patch,
    TelepathyCompilerPatch,
    _guard_external_contracts,
)
compile_telepathy.__name__ = "compile_telepathy"
compile_telepathy.__qualname__ = "compile_telepathy"
compile_telepathy.__doc__ = (
    "Compile one authority-bound Monster Core Telepathy declaration."
)
del _compiler_contract


class LanguageCapabilityCompiler(Protocol):
    def __call__(
        self,
        source: object,
        consumer: object,
        authority: object,
        /,
    ) -> TelepathyCompilerPatch | None: ...


def _registration_validation_gateway() -> tuple[
    Callable[[Callable[[object], LanguageCapabilityCompiler]], None],
    Callable[[object], LanguageCapabilityCompiler],
]:
    validator: Callable[[object], LanguageCapabilityCompiler] | None = None

    def bind(
        value: Callable[[object], LanguageCapabilityCompiler],
    ) -> None:
        nonlocal validator
        if validator is not None:
            raise RuntimeError(
                "Telepathy registration validator is already bound"
            )
        validator = value

    def validate(value: object) -> LanguageCapabilityCompiler:
        if validator is None:
            raise RuntimeError(
                "Telepathy registration validator is not bound"
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
        LanguageCapabilityCompiler,
    ],
    validate_patch: Callable[[object], None],
) -> Callable[
    [object, object, object, object],
    TelepathyCompilerPatch | None,
]:
    def match(
        registration: object,
        source: object,
        consumer: object,
        authority: object,
    ) -> TelepathyCompilerPatch | None:
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
class LanguageCapabilityCompilerRegistration(metaclass=_SealedTelepathyType):
    """Local ordered registration for exact Languages-field consumers."""

    compiler_id: str
    mechanic_type: str
    compiler: LanguageCapabilityCompiler

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "LanguageCapabilityCompilerRegistration must be created "
            "by its factory"
        )

    match = _registration_match_method


del _registration_match_method


def _registration_contract(
    registration_type: type[LanguageCapabilityCompilerRegistration],
    canonical_compiler: LanguageCapabilityCompiler,
) -> tuple[
    Callable[[], LanguageCapabilityCompilerRegistration],
    Callable[[object], LanguageCapabilityCompiler],
]:
    def validate(
        registration: object,
    ) -> LanguageCapabilityCompiler:
        if type(registration) is not registration_type:
            raise TypeError(
                "Telepathy registration must have the exact local type"
            )
        try:
            compiler_id = object.__getattribute__(
                registration,
                "compiler_id",
            )
            mechanic_type = object.__getattribute__(
                registration,
                "mechanic_type",
            )
            compiler = object.__getattribute__(
                registration,
                "compiler",
            )
        except (AttributeError, TypeError) as failure:
            raise TypeError(
                "Telepathy registration is incomplete"
            ) from failure
        if (
            type(compiler_id) is not str
            or type(mechanic_type) is not str
        ):
            raise TypeError(
                "Telepathy registration identifiers must be exact strings"
            )
        if (
            compiler_id != "monster-core-telepathy"
            or mechanic_type != "telepathy"
            or compiler is not canonical_compiler
        ):
            raise ValueError(
                "Telepathy registration is not canonical"
            )
        return canonical_compiler

    def new() -> LanguageCapabilityCompilerRegistration:
        registration = object.__new__(registration_type)
        object.__setattr__(
            registration,
            "compiler_id",
            "monster-core-telepathy",
        )
        object.__setattr__(
            registration,
            "mechanic_type",
            "telepathy",
        )
        object.__setattr__(
            registration,
            "compiler",
            canonical_compiler,
        )
        validate(registration)
        return registration

    return new, validate


_new_registration, _validate_registration = _registration_contract(
    LanguageCapabilityCompilerRegistration,
    compile_telepathy,
)
del _registration_contract
_bind_registration_validator(_validate_registration)
_seal_telepathy_type(LanguageCapabilityCompilerRegistration)
del _bind_registration_validator
del _registration_validation_method


COMPILER_REGISTRATIONS = (_new_registration(),)


def _matcher_structure(
    source: object,
    consumer: object,
    authority: object,
    registrations: object,
    authority_type: type[SourceAuthorityAdapter],
    registration_type: type[LanguageCapabilityCompilerRegistration],
    patch_type: type[TelepathyCompilerPatch],
    validate_registration: Callable[
        [object],
        LanguageCapabilityCompiler,
    ],
    registration_match: Callable[..., object],
) -> TelepathyCompilerPatch | None:
    if type(authority) is not authority_type:
        raise TypeError(
            "Telepathy authority must be an exact SourceAuthorityAdapter"
        )
    if type(registrations) is not tuple:
        raise TypeError(
            "language-capability registrations must be an exact tuple"
        )
    if len(registrations) > 4_096:
        raise ValueError(
            "language-capability registrations exceed their bound"
        )
    matches: list[tuple[str, TelepathyCompilerPatch]] = []
    for registration in registrations:
        if type(registration) is not registration_type:
            raise TypeError(
                "language-capability registrations contain a foreign type"
            )
        validate_registration(registration)
        patch = registration_match(
            registration,
            source,
            consumer,
            authority,
        )
        if patch is not None:
            if type(patch) is not patch_type:
                raise TypeError(
                    "language-capability registration returned a foreign "
                    "patch"
                )
            matches.append(
                (
                    object.__getattribute__(
                        registration,
                        "compiler_id",
                    ),
                    patch,
                )
            )
    if len(matches) > 1:
        compiler_ids = ", ".join(repr(item[0]) for item in matches)
        raise LanguageCapabilityCompilerAmbiguityError(
            "multiple language-capability compilers matched in order: "
            f"{compiler_ids}"
        )
    return matches[0][1] if matches else None


def _matcher_contract(
    structural_matcher: Callable[..., object],
    authority_type: type[SourceAuthorityAdapter],
    registration_type: type[LanguageCapabilityCompilerRegistration],
    patch_type: type[TelepathyCompilerPatch],
    validate_registration: Callable[
        [object],
        LanguageCapabilityCompiler,
    ],
    registration_match: Callable[..., object],
) -> Callable[..., TelepathyCompilerPatch | None]:
    def match(
        source: object,
        consumer: object,
        authority: object,
        registrations: object,
        /,
    ) -> TelepathyCompilerPatch | None:
        result = structural_matcher(
            source,
            consumer,
            authority,
            registrations,
            authority_type,
            registration_type,
            patch_type,
            validate_registration,
            registration_match,
        )
        if result is not None and type(result) is not patch_type:
            raise TypeError(
                "language-capability matcher returned a foreign result"
            )
        return result

    return match


match_language_capability_compilers = _matcher_contract(
    _matcher_structure,
    SourceAuthorityAdapter,
    LanguageCapabilityCompilerRegistration,
    TelepathyCompilerPatch,
    _validate_registration,
    LanguageCapabilityCompilerRegistration.match,
)
del _matcher_contract


def _language_compiler_contract(
    matcher: Callable[..., TelepathyCompilerPatch | None],
    registrations: tuple[LanguageCapabilityCompilerRegistration, ...],
) -> Callable[
    [object, object, object],
    TelepathyCompilerPatch | None,
]:
    def compile(
        source: object,
        consumer: object,
        authority: object,
        /,
    ) -> TelepathyCompilerPatch | None:
        return matcher(
            source,
            consumer,
            authority,
            registrations,
        )

    return compile


compile_language_capability = _language_compiler_contract(
    match_language_capability_compilers,
    COMPILER_REGISTRATIONS,
)
del _language_compiler_contract


def _linker_contract(
    patch_type: type[TelepathyCompilerPatch],
    validate_patch: Callable[[object], None],
    serialize_patch: Callable[[object], SerializedObject],
) -> Callable[[object], SerializedObject]:
    def link(patch: object, /) -> SerializedObject:
        if type(patch) is not patch_type:
            raise TypeError(
                "link_telepathy_patch requires an exact "
                "TelepathyCompilerPatch"
            )
        validate_patch(patch)
        source = object.__getattribute__(patch, "_source")
        member = object.__getattribute__(source, "_raw_member")
        raw_value = object.__getattribute__(member, "value")
        entries = (
            (raw_value,)
            if type(raw_value) is str
            else tuple(object.__getattribute__(raw_value, "items"))
        )
        return {
            "rawLanguageEntries": list(entries),
            "remainingLanguageEntries": list(
                object.__getattribute__(
                    patch,
                    "_remaining_language_entries",
                )
            ),
            "communicationCapabilities": [serialize_patch(patch)],
            "runtimeReady": False,
        }

    return link


link_telepathy_patch = _linker_contract(
    TelepathyCompilerPatch,
    _validate_patch,
    TelepathyCompilerPatch.as_serialized,
)
del _linker_contract


def _compile_and_link_contract(
    compiler: Callable[
        [object, object, object],
        TelepathyCompilerPatch | None,
    ],
    linker: Callable[[object], SerializedObject],
) -> Callable[[object, object, object], SerializedObject | None]:
    def compile_and_link(
        source: object,
        consumer: object,
        authority: object,
        /,
    ) -> SerializedObject | None:
        patch = compiler(source, consumer, authority)
        return linker(patch) if patch is not None else None

    return compile_and_link


compile_and_link_telepathy = _compile_and_link_contract(
    compile_language_capability,
    link_telepathy_patch,
)
del _compile_and_link_contract


@final
@dataclass(frozen=True, slots=True, init=False)
class LanguageCapabilityFamilyFragment(metaclass=_SealedTelepathyType):
    """Local unmounted fragment for the future shared source-field category."""

    family_id: str
    mechanic_types: tuple[str, ...]
    language_capability_compilers: tuple[
        LanguageCapabilityCompilerRegistration,
        ...,
    ]
    runtime_ready: bool

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "LanguageCapabilityFamilyFragment must be created by its factory"
        )


def _validate_fragment(
    fragment: object,
) -> None:
    if type(fragment) is not LanguageCapabilityFamilyFragment:
        raise TypeError(
            "Telepathy fragment must have the exact local type"
        )
    try:
        family_id = object.__getattribute__(fragment, "family_id")
        mechanic_types = object.__getattribute__(
            fragment,
            "mechanic_types",
        )
        registrations = object.__getattribute__(
            fragment,
            "language_capability_compilers",
        )
        runtime_ready = object.__getattribute__(
            fragment,
            "runtime_ready",
        )
    except (AttributeError, TypeError) as failure:
        raise TypeError("Telepathy fragment is incomplete") from failure
    if (
        type(family_id) is not str
        or type(mechanic_types) is not tuple
        or len(mechanic_types) != 1
        or type(mechanic_types[0]) is not str
    ):
        raise TypeError(
            "Telepathy fragment identifiers must use exact contracts"
        )
    if (
        family_id != "telepathy"
        or mechanic_types != ("telepathy",)
        or type(registrations) is not tuple
        or len(registrations) != 1
        or runtime_ready is not False
    ):
        raise ValueError("Telepathy fragment is not canonical")
    _validate_registration(registrations[0])


def _new_fragment() -> LanguageCapabilityFamilyFragment:
    fragment = object.__new__(LanguageCapabilityFamilyFragment)
    object.__setattr__(fragment, "family_id", "telepathy")
    object.__setattr__(fragment, "mechanic_types", ("telepathy",))
    object.__setattr__(
        fragment,
        "language_capability_compilers",
        COMPILER_REGISTRATIONS,
    )
    object.__setattr__(fragment, "runtime_ready", False)
    _validate_fragment(fragment)
    return fragment


FRAGMENT = _new_fragment()


_seal_telepathy_type(LanguageCapabilityFamilyFragment)
del _seal_telepathy_type
del _validated_method_contract
del _late_validation_method


__all__ = [
    "COMPILER_ID",
    "COMPILER_REGISTRATIONS",
    "FAMILY_ID",
    "FRAGMENT",
    "LANGUAGES_FIELD_NAME",
    "LanguageCapabilityCompilerAmbiguityError",
    "LanguageCapabilityCompilerRegistration",
    "LanguageCapabilityFamilyFragment",
    "LanguageCapabilitySource",
    "MECHANIC_TYPE",
    "RelationalCommunicationDependency",
    "TELEPATHY_GLOSSARY",
    "TELEPATHY_RULE_REQUIREMENT",
    "TelepathyCompilerPatch",
    "TelepathyRuleReceipt",
    "TelepathySourceAmbiguityError",
    "compile_and_link_telepathy",
    "compile_language_capability",
    "compile_telepathy",
    "link_telepathy_patch",
    "match_language_capability_compilers",
]

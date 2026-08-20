"""Compile Core MC1 weaknesses and resistances behind the source facade.

This module is deliberately compiler-only. It classifies every authored
``Weaknesses`` and ``Resistances`` token from one exact creature selected by
the caller's retained :class:`SourceAuthorityAdapter`, verifies only the
hash-pinned Player Core and GM Core providers needed by that profile, and
returns a sanitized compile-time projection.

No public damage component, aggregation, linking, resolution, registry, HP,
or encounter API is defined here. Typed source dependencies remain explicit
clause deferrals and every public projection remains runtime-inactive.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from functools import wraps
import hashlib
import html
from inspect import signature as inspect_signature
import re
from typing import Literal, TypeAlias, final
from weakref import WeakValueDictionary

from .contracts import RawSourceArray, RawSourceObject
from .source_authority import (
    RawIndexStep,
    RawMemberStep,
    RawPathStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)


FAMILY_ID = "damage-defenses"
MECHANIC_TYPE = "damage-defense"
MONSTER_CORE_SOURCE_ID = "core-mc1"
SOURCE_SCOPE = ("core-gmc", "core-mc1", "core-pc1")
REGISTRY_STATUS = "unregistered"
ACTIVATION_STATUS = "deferred"

MAX_SIGNED_64 = (1 << 63) - 1
MAX_FIELD_ENTRIES = 8
MAX_FIELD_TEXT_BYTES = 4_096
MAX_CREATURE_SCAN_NODES = 8_192
MAX_CREATURE_SCAN_DEPTH = 24
MAX_IDENTIFIER_BYTES = 128

DefenseField: TypeAlias = Literal["Weaknesses", "Resistances"]
FieldShape: TypeAlias = Literal["scalar", "array"]
SupportStatus: TypeAlias = Literal["supported", "deferred"]
PredicateKind: TypeAlias = Literal[
    "damage-type",
    "physical-family",
    "material",
    "effect-trait",
    "damage-category",
    "delivery",
    "weapon-group",
    "universal",
    "named-bundle",
    "named-predicate",
    "legacy-alignment",
    "untyped",
    "unclassified",
]
AtomDimension: TypeAlias = Literal[
    "damage-type",
    "material",
    "effect-trait",
    "feature",
]


class DamageDefenseCompileError(ValueError):
    """Authenticated creature source is structurally ambiguous."""


_SIMPLE_VALUE_RE = re.compile(
    r"^(?P<label>[a-z]+(?: [a-z]+)*) (?P<value>[1-9][0-9]*)$",
    re.ASCII,
)
_PHYSICAL_EXCEPTION_RE = re.compile(
    r"^physical (?P<value>[1-9][0-9]*) "
    r"\(except (?P<exception>[a-z]+(?: [a-z]+)*(?: or [a-z]+(?: [a-z]+)*)?)\)$",
    re.ASCII,
)
_SPELL_EXCEPTION_RE = re.compile(
    r"^spells (?P<value>[1-9][0-9]*) "
    r"\(except (?P<exception>.+)\)$",
    re.ASCII,
)
_UNTYPED_EXCEPTION_RE = re.compile(
    r"^(?P<value>[1-9][0-9]*) \(except (?P<exception>.+)\)$",
    re.ASCII,
)
_UNIVERSAL_QUALIFIED_RE = re.compile(
    r"^all(?: damage)? (?P<value>[1-9][0-9]*) "
    r"\(except (?P<exceptions>force, ghost touch, "
    r"(?:or spirit|spirit, or vitality)); double resistance "
    r"(?P<wording>against|vs\.) non-magical\)$",
    re.ASCII,
)
_SEE_RE = re.compile(
    r"^(?P<label>[a-z]+(?: [a-z]+)*) (?P<value>[1-9][0-9]*) "
    r"\(see (?P<reference>[a-z]+(?: [a-z]+)*)\)$",
    re.ASCII,
)
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", re.ASCII)
_DEPENDENCY_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?::[a-z][a-z0-9]*(?:-[a-z0-9]+)*)?$",
    re.ASCII,
)

_DAMAGE_TYPES = frozenset(
    {
        "acid",
        "bleed",
        "bludgeoning",
        "cold",
        "electricity",
        "fire",
        "force",
        "mental",
        "piercing",
        "poison",
        "slashing",
        "sonic",
        "spirit",
        "vitality",
        "void",
    }
)
_PHYSICAL_DAMAGE_TYPES = frozenset(
    {"bleed", "bludgeoning", "piercing", "slashing"}
)
_MATERIALS = frozenset(
    {"adamantine", "cold-iron", "dawnsilver", "silver"}
)
_MAGICAL_TRAITS = frozenset(
    {"arcane", "divine", "magical", "occult", "primal"}
)


def _assert_reviewed_configuration() -> None:
    if (
        FAMILY_ID != "damage-defenses"
        or MECHANIC_TYPE != "damage-defense"
        or MONSTER_CORE_SOURCE_ID != "core-mc1"
        or SOURCE_SCOPE != ("core-gmc", "core-mc1", "core-pc1")
        or REGISTRY_STATUS != "unregistered"
        or ACTIVATION_STATUS != "deferred"
        or MAX_SIGNED_64 != (1 << 63) - 1
        or MAX_FIELD_ENTRIES != 8
        or MAX_FIELD_TEXT_BYTES != 4_096
        or MAX_CREATURE_SCAN_NODES != 8_192
        or MAX_CREATURE_SCAN_DEPTH != 24
        or MAX_IDENTIFIER_BYTES != 128
        or _DAMAGE_TYPES
        != frozenset(
            {
                "acid",
                "bleed",
                "bludgeoning",
                "cold",
                "electricity",
                "fire",
                "force",
                "mental",
                "piercing",
                "poison",
                "slashing",
                "sonic",
                "spirit",
                "vitality",
                "void",
            }
        )
        or _PHYSICAL_DAMAGE_TYPES
        != frozenset({"bleed", "bludgeoning", "piercing", "slashing"})
        or _MATERIALS
        != frozenset(
            {"adamantine", "cold-iron", "dawnsilver", "silver"}
        )
        or _MAGICAL_TRAITS
        != frozenset(
            {"arcane", "divine", "magical", "occult", "primal"}
        )
    ):
        raise DamageDefenseCompileError(
            "reviewed damage-defense configuration was rebound"
        )
    try:
        provider_digest = hashlib.sha256(
            canonical_json_bytes(
                [
                    RuleRequirement.as_serialized(item)
                    for item in _provider_requirements()
                ]
            )
        ).hexdigest()
    except (TypeError, ValueError) as failure:
        raise DamageDefenseCompileError(
            "reviewed damage-defense providers are invalid"
        ) from failure
    if (
        provider_digest
        != "2d532a6883e654fe6e50f79005b7d1067327f9db64bae650032ff8529da4d94f"
    ):
        raise DamageDefenseCompileError(
            "reviewed damage-defense providers were rebound"
        )


@final
@dataclass(frozen=True, slots=True)
class DamagePredicateAtom:
    """One exact atom in a conjunctive exception predicate."""

    dimension: AtomDimension
    term: str

    def __post_init__(self) -> None:
        if type(self) is not DamagePredicateAtom:
            raise TypeError("DamagePredicateAtom subclasses are unsupported")
        if self.dimension not in (
            "damage-type",
            "material",
            "effect-trait",
            "feature",
        ):
            raise ValueError("damage predicate atom dimension is invalid")
        _require_identifier(self.term, "damage predicate atom term")


@final
@dataclass(frozen=True, slots=True)
class DamagePredicateException:
    """One exception alternative; all atoms in it must match."""

    atoms: tuple[DamagePredicateAtom, ...]

    def __post_init__(self) -> None:
        if type(self) is not DamagePredicateException:
            raise TypeError(
                "DamagePredicateException subclasses are unsupported"
            )
        if (
            type(self.atoms) is not tuple
            or not self.atoms
            or any(type(item) is not DamagePredicateAtom for item in self.atoms)
        ):
            raise TypeError(
                "DamagePredicateException.atoms must be a nonempty exact tuple"
            )
        if len(self.atoms) != len(set(self.atoms)):
            raise ValueError("damage predicate exception atoms must be unique")


@final
@dataclass(frozen=True, slots=True)
class DamageDefenseClause:
    """One lossless authored weakness or resistance projection."""

    field: DefenseField
    ordinal: int
    source_text: str
    source_receipt: SourceReceipt
    support: SupportStatus
    predicate_kind: PredicateKind
    term: str | None
    value: int | None
    exceptions: tuple[DamagePredicateException, ...]
    nonmagical_multiplier: int
    provider_rule_ids: tuple[str, ...]
    deferred_dependency: str | None

    def __post_init__(self) -> None:
        if type(self) is not DamageDefenseClause:
            raise TypeError("DamageDefenseClause subclasses are unsupported")
        if self.field not in ("Weaknesses", "Resistances"):
            raise ValueError("damage defense field is invalid")
        _require_ordinal(self.ordinal, "damage defense ordinal")
        _require_source_text(self.source_text, "damage defense source text")
        if type(self.source_receipt) is not SourceReceipt:
            raise TypeError("damage defense source receipt must be exact")
        if self.support not in ("supported", "deferred"):
            raise ValueError("damage defense support status is invalid")
        if self.predicate_kind not in (
            "damage-type",
            "physical-family",
            "material",
            "effect-trait",
            "damage-category",
            "delivery",
            "weapon-group",
            "universal",
            "named-bundle",
            "named-predicate",
            "legacy-alignment",
            "untyped",
            "unclassified",
        ):
            raise ValueError("damage defense predicate kind is invalid")
        if self.term is not None:
            _require_identifier(self.term, "damage defense term")
        if self.value is not None:
            _require_positive_integer(self.value, "damage defense value")
        if (
            type(self.exceptions) is not tuple
            or any(
                type(item) is not DamagePredicateException
                for item in self.exceptions
            )
        ):
            raise TypeError("damage defense exceptions must be an exact tuple")
        if self.nonmagical_multiplier not in (1, 2):
            raise ValueError("nonmagical multiplier must be 1 or 2")
        _require_identifier_tuple(
            self.provider_rule_ids,
            "damage defense provider rule ids",
            allow_empty=False,
        )
        if self.support == "supported":
            if self.value is None or self.deferred_dependency is not None:
                raise ValueError(
                    "supported damage defense must have a value and no blocker"
                )
        else:
            if (
                type(self.deferred_dependency) is not str
                or not self.deferred_dependency
            ):
                raise ValueError(
                    "deferred damage defense requires a typed dependency"
                )


@final
@dataclass(frozen=True, slots=True, weakref_slot=True)
class CompiledDamageDefenseProfile:
    """Lossless compile artifact for one exact creature block."""

    creature_name: str
    source_receipt: SourceReceipt
    weakness_shape: FieldShape | None
    resistance_shape: FieldShape | None
    weaknesses: tuple[DamageDefenseClause, ...]
    resistances: tuple[DamageDefenseClause, ...]
    _selection: VerifiedSourceSelection
    _artifact_token: object = dataclass_field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self) is not CompiledDamageDefenseProfile:
            raise TypeError(
                "CompiledDamageDefenseProfile subclasses are unsupported"
            )
        _require_trimmed_text(self.creature_name, "creature name")
        if type(self.source_receipt) is not SourceReceipt:
            raise TypeError("profile source receipt must be exact")
        for field_name in ("weakness_shape", "resistance_shape"):
            if getattr(self, field_name) not in (None, "scalar", "array"):
                raise ValueError(f"{field_name} is invalid")
        for field_name, expected_field in (
            ("weaknesses", "Weaknesses"),
            ("resistances", "Resistances"),
        ):
            clauses = getattr(self, field_name)
            if (
                type(clauses) is not tuple
                or any(type(item) is not DamageDefenseClause for item in clauses)
                or any(item.field != expected_field for item in clauses)
                or tuple(item.ordinal for item in clauses)
                != tuple(range(len(clauses)))
            ):
                raise ValueError(f"profile {field_name} are not canonical")
        if type(self._selection) is not VerifiedSourceSelection:
            raise TypeError("profile selection must be exact verified evidence")

    def __copy__(self) -> CompiledDamageDefenseProfile:
        raise TypeError("compiled damage defense profiles cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> CompiledDamageDefenseProfile:
        raise TypeError("compiled damage defense profiles cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("compiled damage defense profiles cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("compiled damage defense profiles cannot be pickled")


def _build_artifact_minter() -> tuple[object, object]:
    """Keep compiler authority in a closure, not on module state."""

    compiled_artifacts: WeakValueDictionary[
        object,
        CompiledDamageDefenseProfile,
    ] = WeakValueDictionary()
    def mint_compiled(
        *,
        creature_name: str,
        source_receipt: SourceReceipt,
        weakness_shape: FieldShape | None,
        resistance_shape: FieldShape | None,
        weaknesses: tuple[DamageDefenseClause, ...],
        resistances: tuple[DamageDefenseClause, ...],
        selection: VerifiedSourceSelection,
    ) -> CompiledDamageDefenseProfile:
        token = object()
        value = CompiledDamageDefenseProfile(
            creature_name=creature_name,
            source_receipt=source_receipt,
            weakness_shape=weakness_shape,
            resistance_shape=resistance_shape,
            weaknesses=weaknesses,
            resistances=resistances,
            _selection=selection,
            _artifact_token=token,
        )
        compiled_artifacts[token] = value
        return value

    def require_compiled(value: CompiledDamageDefenseProfile) -> None:
        if compiled_artifacts.get(value._artifact_token) is not value:
            raise DamageDefenseCompileError(
                "compiled damage defense profile was not compiler-minted"
            )

    return mint_compiled, require_compiled


(
    _mint_compiled_profile,
    _require_minted_compiled_profile,
) = _build_artifact_minter()


def _require_trimmed_text(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
        or len(value.encode("utf-8")) > MAX_FIELD_TEXT_BYTES
    ):
        raise DamageDefenseCompileError(
            f"{label} must be bounded nonempty trimmed text"
        )
    return value


def _require_source_text(value: object, label: str) -> str:
    return _require_trimmed_text(value, label)


def _require_identifier(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > MAX_IDENTIFIER_BYTES
        or _IDENTIFIER_RE.fullmatch(value) is None
    ):
        raise ValueError(f"{label} must be a canonical identifier")
    return value


def _require_identifier_tuple(
    value: object,
    label: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or (not allow_empty and not value)
        or any(type(item) is not str for item in value)
    ):
        raise TypeError(f"{label} must be an exact tuple of strings")
    for item in value:
        _require_identifier(item, f"{label} item")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    if value != tuple(sorted(value)):
        raise ValueError(f"{label} must be in canonical sorted order")
    return value


def _require_dependency_tuple(
    value: object,
    label: str,
) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or any(
            type(item) is not str
            or len(item.encode("utf-8")) > MAX_IDENTIFIER_BYTES
            or _DEPENDENCY_RE.fullmatch(item) is None
            for item in value
        )
    ):
        raise TypeError(f"{label} must be an exact tuple of dependencies")
    if len(value) != len(set(value)) or value != tuple(sorted(value)):
        raise ValueError(f"{label} must be unique and canonically sorted")
    return value


def _require_ordinal(value: object, label: str) -> int:
    if type(value) is not int or value < 0 or value > MAX_SIGNED_64:
        raise ValueError(f"{label} must be a nonnegative signed-64 integer")
    return value


def _require_positive_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 1 or value > MAX_SIGNED_64:
        raise ValueError(f"{label} must be a positive signed-64 integer")
    return value


def _require_nonnegative_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0 or value > MAX_SIGNED_64:
        raise DamageDefenseInputError(
            f"{label} must be a nonnegative signed-64 integer"
        )
    return value


def _parse_positive(value: str) -> int:
    if (
        not value
        or (len(value) > 1 and value.startswith("0"))
        or len(value) > len(str(MAX_SIGNED_64))
        or (
            len(value) == len(str(MAX_SIGNED_64))
            and value > str(MAX_SIGNED_64)
        )
    ):
        raise DamageDefenseCompileError(
            "damage defense value is not canonical signed-64"
        )
    return _require_positive_integer(int(value), "damage defense value")


def _provider_requirements() -> tuple[RuleRequirement, ...]:
    """Rebuild the reviewed provider pins from local immutable literals."""

    member = RawMemberStep
    specs = (
        ("pc1-apply-iwr", "core-pc1", "407.3", (), "70d4b59f1e222320d84c65c73eee11d14210e6800d7ecdbd3ce000da6f13bc21"),
        ("pc1-immunity", "core-pc1", "408.2", (), "d7df47027e4560e84fbd5931fdbb6637b9ed1dd2c1cbbc413d7034254a25d531"),
        ("pc1-weakness", "core-pc1", "408.6", (), "fda5c3a1fd046125c78dd4de06f694e15464cb4629da57cdc1473bcb0f03e6f3"),
        ("pc1-resistance", "core-pc1", "408.7", (), "1adbcc30d0074c46f9ab596b8eed6e7b37987456c4b88ab6017475e633010442"),
        ("pc1-damage-types", "core-pc1", "409.1", (), "b5e918eb06281d4b10f2a3f157110a16e86f31b85fa6efab2e9c9b6bfbf64200"),
        ("pc1-bleed-damage", "core-pc1", "409.7", (), "e0831a7c4ddf9d6129f0d12bfa93c9f262d6b732152410c473b32fc481752cc6"),
        ("pc1-physical-damage", "core-pc1", "409.2", (), "85faabb924b323e01432c28b280ca7e22c7a84ddead7f78f09cfcb33a6a16963"),
        ("pc1-precision-damage", "core-pc1", "409.8", (), "b314f679c0f88854580c7a5523463a034cb35fe1ab5212810888f102aaec7cba"),
        ("pc1-precious-materials", "core-pc1", "409.9", (), "d5cf34314059c8e4deb94af723d995b8901d09727aaaf6fe6ad94ce948cfb64d"),
        ("pc1-areas", "core-pc1", "428.1", (), "d69f6b4606d5873a1129ae227fbe003b6631fe0c70e7c65e41a8ae3c37abdfeb"),
        ("pc1-casting-spells", "core-pc1", "299.2", (), "e72af12260d392ccd01ddb21c5e0ac2d5c77b75b4cd55be9145c6cc1a36ad21b"),
        ("pc1-weapon-group", "core-pc1", "276.8", (), "a3d4515d6c946cc255b85e1312e20314945b72068c83524af5376df5367c5e17"),
        ("pc1-martial-melee-weapon-table", "core-pc1", "275.1", (member("~.table", 12),), "dd5b5f5441f97b6f84b1bd428b664f97fdcad151160e067c1892d981069b2f1c"),
        ("pc1-advanced-melee-weapon-table", "core-pc1", "275.1", (member("~.table", 13),), "aebeb736fe24ede4a049633ab17e8b6ef872f2c69993af2e15645263b0f69016"),
        ("pc1-alchemical-bombs", "core-pc1", "292.4", (), "cc544feccb1783bb4a1e525254fb33fcab6775b68f4be6027cbaecb629e9701f"),
        ("pc1-area-glossary", "core-pc1", "452.1", (member("!.area", 41),), "2e10e744d7d5e194c0f1e16bdc0b66b631851f25fa3885ff3afc56d13edcebd9"),
        ("pc1-acid-trait", "core-pc1", "452.1", (member("!.acid (trait)", 7),), "dc569d2fb45ffe153adca814d0dd09b2bf4f48c1dbd0aa68cdaf30485c5ee054"),
        ("pc1-cold-trait", "core-pc1", "452.1", (member("!.cold (trait)", 104),), "fc5500af2a4ba8dc12ac8ac2c95379ed3ca8afc4d50ce92e0c82c0f76e71db6c"),
        ("pc1-earth-trait", "core-pc1", "452.1", (member("!.earth (trait)", 206),), "eab28bc1b4ef65245797f118f941daa23333d948e9f58214511378fad94a48fa"),
        ("pc1-fire-trait", "core-pc1", "452.1", (member("!.fire (trait)", 245),), "2289a47315579abc9691978ce60970dd9cad692b20bf7cbb13cb991ff5be2b88"),
        ("pc1-holy-trait", "core-pc1", "452.1", (member("!.holy (trait)", 311),), "231389b240570c492b0992d5229f1b1a078b04949d339e2776f8505deefa6233"),
        ("pc1-magical-trait", "core-pc1", "452.1", (member("!.magical (trait)", 364),), "05e178404fa38d5c9d2f53c3b558241b26b2909ddaf8401c7b05f8c08df88fe8"),
        ("pc1-sonic-trait", "core-pc1", "452.1", (member("!.sonic (trait)", 529),), "3461f86fe9804777c542b1aee72c855d043e46d2eb6bc63ebe630d3131f7e2d0"),
        ("pc1-splash-trait", "core-pc1", "452.1", (member("!.splash (trait)", 543),), "3df300a831c55b128ee452313449b968c5cb8da1aa55eac4c725eb7d47c607ec"),
        ("pc1-spell-glossary", "core-pc1", "452.1", (member("!.spell", 535),), "fa2ccd87e17dd911e6e8b34fdc9625292d2af45093bf71d82288a1093d162e92"),
        ("pc1-unholy-trait", "core-pc1", "452.1", (member("!.unholy (trait)", 614),), "2ca86fb0bb660ed1f95e63f10a28d24226d07c5fe3de7222361e0e7ac3490a86"),
        ("pc1-water-trait", "core-pc1", "452.1", (member("!.water (trait)", 631),), "394eee8cb09c82fad8effbdcf6d1b450ba563f05019baef0a58cc5916b9390fb"),
        ("gmc-ghost-touch", "core-gmc", "238.1", (), "7a028ec31dd5b331717b934e15053990b39c841d66ed656673eff20ae41c0a94"),
        ("gmc-holy-rune", "core-gmc", "238.3", (), "ae02d276e99dcfd57e55a6498063fb9c7269f293e9a459d138e6ce2a7be36e4a"),
        ("gmc-unholy-rune", "core-gmc", "239.4", (), "3cfdf0e556ed70466f18f373bf82e909617187405a63ce17ff20fb38773a189c"),
        ("gmc-splash-trait", "core-gmc", "244.3", (), "59b1a1f37c4f9ce70cc4ae9a04778d95f0a8f92ec036c68e70c45ff8c49b8fca"),
        ("gmc-adamantine", "core-gmc", "253.2", (), "e490652d2f016bff78a3249da4125592265ff22acfd86ac8b75839963bb900d5"),
        ("gmc-adamantine-weapon", "core-gmc", "240.3", (), "a1d62a94b4343bd8946e18ac7013a2904891340cb8a5cd1d034c0a456a5f787e"),
        ("gmc-cold-iron", "core-gmc", "253.4", (), "8526930605322431f25d4c87c8b6b47126ee302ef6b5ac0acc526e6a7d53a5ef"),
        ("gmc-cold-iron-weapon", "core-gmc", "240.4", (), "4b5bed5815af1e1314f33a23cd4804af2e487f3f89a29731552ad48e623453f8"),
        ("gmc-dawnsilver", "core-gmc", "253.6", (), "2bc4bb1d1c6092ed61ee78654206490e88371941ab477da83b7a29740dc4d440"),
        ("gmc-dawnsilver-weapon", "core-gmc", "240.5", (), "e4e41b688b9d8acf40df236094d12e61bbbaa232906507d81630d10c3a5460cc"),
        ("gmc-silver", "core-gmc", "254.6", (), "d6be15d5952d127a3e8172a63a6102c750d5d5b8c6f3df979ea29c8c6e8acd06"),
        ("gmc-silver-weapon", "core-gmc", "240.8", (), "6052aa07f7fd1ea1c98a92534d9b295722b5d64c0dca36f85184ed1a2f37dba7"),
    )
    return tuple(
        RuleRequirement(
            rule_id=rule_id,
            source_id=source_id,
            locator=locator,
            selection_path=selection_path,
            expected_selection_sha256=selection_sha256,
        )
        for (
            rule_id,
            source_id,
            locator,
            selection_path,
            selection_sha256,
        ) in specs
    )


def damage_defense_provider_requirements() -> tuple[RuleRequirement, ...]:
    """Return fresh immutable reviewed provider requirements."""

    _assert_reviewed_configuration()
    return _provider_requirements()


def _base_provider_ids(field: DefenseField) -> tuple[str, ...]:
    return (
        "pc1-apply-iwr",
        "pc1-immunity",
        "pc1-weakness" if field == "Weaknesses" else "pc1-resistance",
    )


def _providers_for(
    field: DefenseField,
    predicate_kind: PredicateKind,
    term: str | None,
    *,
    has_ghost_touch: bool = False,
    has_magical: bool = False,
) -> tuple[str, ...]:
    values = list(_base_provider_ids(field))
    if predicate_kind in ("damage-type", "universal"):
        values.append("pc1-damage-types")
        if term == "bleed":
            values.append("pc1-bleed-damage")
    if predicate_kind == "physical-family":
        values.extend(
            (
                "pc1-damage-types",
                "pc1-bleed-damage",
                "pc1-physical-damage",
            )
        )
    if predicate_kind == "material":
        values.append("pc1-precious-materials")
        if term == "adamantine":
            values.extend(("gmc-adamantine", "gmc-adamantine-weapon"))
        elif term == "cold-iron":
            values.extend(("gmc-cold-iron", "gmc-cold-iron-weapon"))
        elif term == "silver":
            values.extend(
                (
                    "gmc-dawnsilver",
                    "gmc-dawnsilver-weapon",
                    "gmc-silver",
                    "gmc-silver-weapon",
                )
            )
    if predicate_kind == "effect-trait":
        if term in ("acid", "cold", "fire", "sonic"):
            values.append(f"pc1-{term}-trait")
        elif term == "holy":
            values.extend(("pc1-holy-trait", "gmc-holy-rune"))
        elif term == "unholy":
            values.extend(("pc1-unholy-trait", "gmc-unholy-rune"))
        elif term == "earth":
            values.append("pc1-earth-trait")
        elif term == "water":
            values.append("pc1-water-trait")
    if predicate_kind == "damage-category":
        if term == "precision":
            values.append("pc1-precision-damage")
        elif term == "splash":
            values.extend(
                (
                    "pc1-alchemical-bombs",
                    "pc1-splash-trait",
                    "gmc-splash-trait",
                )
            )
    if predicate_kind == "delivery":
        values.extend(("pc1-areas", "pc1-area-glossary"))
    if predicate_kind == "weapon-group":
        values.append("pc1-weapon-group")
        if term == "axe":
            values.extend(
                (
                    "pc1-martial-melee-weapon-table",
                    "pc1-advanced-melee-weapon-table",
                )
            )
    if predicate_kind == "universal" and has_ghost_touch:
        values.append("gmc-ghost-touch")
    if has_magical:
        values.append("pc1-magical-trait")
    if predicate_kind == "untyped" and term == "spell":
        values.extend(("pc1-casting-spells", "pc1-spell-glossary"))
    return tuple(sorted(set(values)))


def _atom(dimension: AtomDimension, term: str) -> DamagePredicateAtom:
    return DamagePredicateAtom(dimension=dimension, term=term)


def _exception(
    *atoms: DamagePredicateAtom,
) -> DamagePredicateException:
    return DamagePredicateException(atoms=tuple(atoms))


def _make_clause(
    *,
    field: DefenseField,
    ordinal: int,
    source_text: str,
    source_receipt: SourceReceipt,
    support: SupportStatus,
    predicate_kind: PredicateKind,
    term: str | None,
    value: int | None,
    exceptions: tuple[DamagePredicateException, ...] = (),
    multiplier: int = 1,
    dependency: str | None = None,
    provider_ids: tuple[str, ...] | None = None,
) -> DamageDefenseClause:
    if provider_ids is None:
        provider_ids = _providers_for(field, predicate_kind, term)
    return DamageDefenseClause(
        field=field,
        ordinal=ordinal,
        source_text=source_text,
        source_receipt=source_receipt,
        support=support,
        predicate_kind=predicate_kind,
        term=term,
        value=value,
        exceptions=exceptions,
        nonmagical_multiplier=multiplier,
        provider_rule_ids=provider_ids,
        deferred_dependency=dependency,
    )


def _classify_clause(
    field: DefenseField,
    ordinal: int,
    source_text: str,
    source_receipt: SourceReceipt,
) -> DamageDefenseClause:
    _require_source_text(source_text, "damage defense entry")

    def _clause(**kwargs: object) -> DamageDefenseClause:
        return _make_clause(  # type: ignore[arg-type]
            source_receipt=source_receipt,
            **kwargs,
        )

    recognized = html.unescape(
        source_text.replace("<i>", "").replace("</i>", "")
    )

    see_match = _SEE_RE.fullmatch(recognized)
    if see_match is not None:
        value = _parse_positive(see_match.group("value"))
        label = see_match.group("label")
        reference = see_match.group("reference").replace(" ", "-")
        kind: PredicateKind = (
            "effect-trait" if label == "holy" else "named-predicate"
        )
        term = label.replace(" ", "-")
        return _clause(
            field=field,
            ordinal=ordinal,
            source_text=source_text,
            support="deferred",
            predicate_kind=kind,
            term=term,
            value=value,
            dependency=f"named-rule:{reference}",
        )

    universal = _UNIVERSAL_QUALIFIED_RE.fullmatch(recognized)
    if universal is not None and field == "Resistances":
        value = _parse_positive(universal.group("value"))
        raw_exceptions = universal.group("exceptions")
        exceptions = [
            _exception(_atom("damage-type", "force")),
            _exception(_atom("feature", "ghost-touch")),
            _exception(_atom("damage-type", "spirit")),
        ]
        if "vitality" in raw_exceptions:
            exceptions.append(
                _exception(_atom("damage-type", "vitality"))
            )
        return _clause(
            field=field,
            ordinal=ordinal,
            source_text=source_text,
            support="supported",
            predicate_kind="universal",
            term="all-damage",
            value=value,
            exceptions=tuple(exceptions),
            multiplier=2,
            provider_ids=_providers_for(
                field,
                "universal",
                "all-damage",
                has_ghost_touch=True,
                has_magical=True,
            ),
        )

    physical = _PHYSICAL_EXCEPTION_RE.fullmatch(recognized)
    if physical is not None and field == "Resistances":
        value = _parse_positive(physical.group("value"))
        raw_exception = physical.group("exception")
        alternatives: tuple[DamagePredicateException, ...] | None = None
        has_magical = False
        if raw_exception in ("adamantine", "cold iron", "silver"):
            material = raw_exception.replace(" ", "-")
            alternatives = (_exception(_atom("material", material)),)
        elif raw_exception in ("bludgeoning", "slashing"):
            alternatives = (
                _exception(_atom("damage-type", raw_exception)),
            )
        elif raw_exception == "adamantine or bludgeoning":
            alternatives = (
                _exception(_atom("material", "adamantine")),
                _exception(_atom("damage-type", "bludgeoning")),
            )
        elif raw_exception == "magical bludgeoning":
            alternatives = (
                _exception(
                    _atom("effect-trait", "magical"),
                    _atom("damage-type", "bludgeoning"),
                ),
            )
            has_magical = True
        elif raw_exception == "magical silver":
            alternatives = (
                _exception(
                    _atom("effect-trait", "magical"),
                    _atom("material", "silver"),
                ),
            )
            has_magical = True
        if alternatives is None:
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="deferred",
                predicate_kind="physical-family",
                term="physical",
                value=value,
                dependency="unrecognized-physical-exception",
            )
        provider_ids = list(
            _providers_for(
                field,
                "physical-family",
                "physical",
                has_magical=has_magical,
            )
        )
        for alternative in alternatives:
            for atom in alternative.atoms:
                if atom.dimension == "material":
                    provider_ids.extend(
                        _providers_for(field, "material", atom.term)
                    )
        return _clause(
            field=field,
            ordinal=ordinal,
            source_text=source_text,
            support="supported",
            predicate_kind="physical-family",
            term="physical",
            value=value,
            exceptions=alternatives,
            provider_ids=tuple(sorted(set(provider_ids))),
        )

    spell = _SPELL_EXCEPTION_RE.fullmatch(recognized)
    if spell is not None and field == "Resistances":
        value = _parse_positive(spell.group("value"))
        raw_exception = spell.group("exception")
        alternatives: tuple[DamagePredicateException, ...] | None = None
        support: SupportStatus = "supported"
        dependency: str | None = None
        if raw_exception == "cold, earth, or water":
            alternatives = (
                _exception(_atom("effect-trait", "cold")),
                _exception(_atom("effect-trait", "earth")),
                _exception(_atom("effect-trait", "water")),
            )
        elif raw_exception in ("fire", "sonic"):
            alternatives = (
                _exception(_atom("effect-trait", raw_exception)),
            )
        elif raw_exception == "acid and spells that cause rust":
            alternatives = (
                _exception(_atom("effect-trait", "acid")),
                _exception(_atom("feature", "rust")),
            )
            support = "deferred"
            dependency = "spell-semantics:rust-causing"
        if alternatives is None:
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="deferred",
                predicate_kind="untyped",
                term="spell",
                value=value,
                dependency="unrecognized-spell-exception",
                provider_ids=_providers_for(field, "untyped", "spell"),
            )
        provider_ids = list(_providers_for(field, "untyped", "spell"))
        for alternative in alternatives:
            for atom in alternative.atoms:
                if atom.dimension == "effect-trait":
                    provider_ids.extend(
                        _providers_for(
                            field,
                            "effect-trait",
                            atom.term,
                        )
                    )
        return _clause(
            field=field,
            ordinal=ordinal,
            source_text=source_text,
            support=support,
            predicate_kind="untyped",
            term="spell",
            value=value,
            exceptions=alternatives,
            provider_ids=tuple(sorted(set(provider_ids))),
            dependency=dependency,
        )

    untyped = _UNTYPED_EXCEPTION_RE.fullmatch(recognized)
    if untyped is not None:
        return _clause(
            field=field,
            ordinal=ordinal,
            source_text=source_text,
            support="deferred",
            predicate_kind="untyped",
            term=None,
            value=_parse_positive(untyped.group("value")),
            dependency="missing-base-predicate",
        )

    simple = _SIMPLE_VALUE_RE.fullmatch(recognized)
    if simple is not None:
        label = simple.group("label")
        value = _parse_positive(simple.group("value"))
        if label in _DAMAGE_TYPES:
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="supported",
                predicate_kind="damage-type",
                term=label,
                value=value,
            )
        if label == "physical":
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="supported",
                predicate_kind="physical-family",
                term="physical",
                value=value,
            )
        if label in ("cold iron", "silver"):
            material = label.replace(" ", "-")
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="supported",
                predicate_kind="material",
                term=material,
                value=value,
            )
        if label in ("holy", "unholy", "earth", "water"):
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="supported",
                predicate_kind="effect-trait",
                term=label,
                value=value,
            )
        if label == "area damage":
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="supported",
                predicate_kind="delivery",
                term="area",
                value=value,
            )
        if label == "splash damage":
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="supported",
                predicate_kind="damage-category",
                term="splash",
                value=value,
            )
        if label == "precision":
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="supported",
                predicate_kind="damage-category",
                term="precision",
                value=value,
            )
        if label == "axes":
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="supported",
                predicate_kind="weapon-group",
                term="axe",
                value=value,
            )
        if label == "all damage" and field == "Resistances":
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="supported",
                predicate_kind="universal",
                term="all-damage",
                value=value,
            )
        if label == "elemental resistance":
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="deferred",
                predicate_kind="named-bundle",
                term="elemental-resistance",
                value=value,
                dependency="named-bundle:elemental-resistance",
            )
        if label == "protean anatomy":
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="deferred",
                predicate_kind="named-predicate",
                term="protean-anatomy",
                value=value,
                dependency="named-rule:protean-anatomy",
            )
        if label == "evil":
            return _clause(
                field=field,
                ordinal=ordinal,
                source_text=source_text,
                support="deferred",
                predicate_kind="legacy-alignment",
                term="evil",
                value=value,
                dependency="obsolete-alignment-source",
            )
        return _clause(
            field=field,
            ordinal=ordinal,
            source_text=source_text,
            support="deferred",
            predicate_kind="unclassified",
            term=label.replace(" ", "-"),
            value=value,
            dependency="unrecognized-valued-predicate",
        )

    if recognized in (
        "bean panic",
        "brain loss",
        "divine revulsion",
        "light vulnerability",
    ):
        return _clause(
            field=field,
            ordinal=ordinal,
            source_text=source_text,
            support="deferred",
            predicate_kind="named-predicate",
            term=recognized.replace(" ", "-"),
            value=None,
            dependency=f"named-rule:{recognized.replace(' ', '-')}",
        )

    return _clause(
        field=field,
        ordinal=ordinal,
        source_text=source_text,
        support="deferred",
        predicate_kind="unclassified",
        term=None,
        value=None,
        dependency="unrecognized-source-shape",
    )


def _find_creature_paths(value: object) -> tuple[tuple[object, ...], ...]:
    paths: list[tuple[object, ...]] = []
    stack: list[tuple[object, tuple[object, ...], int]] = [(value, (), 0)]
    nodes = 0
    while stack:
        current, path, depth = stack.pop()
        nodes += 1
        if nodes > MAX_CREATURE_SCAN_NODES:
            raise DamageDefenseCompileError(
                "creature source scan exceeded its node bound"
            )
        if depth > MAX_CREATURE_SCAN_DEPTH:
            raise DamageDefenseCompileError(
                "creature source scan exceeded its depth bound"
            )
        if type(current) is RawSourceObject:
            for index in range(len(current.members) - 1, -1, -1):
                source_member = current.members[index]
                step = RawMemberStep(source_member.key, index)
                next_path = (*path, step)
                if source_member.key == "^.creature":
                    if type(source_member.value) is not RawSourceObject:
                        raise DamageDefenseCompileError(
                            "creature source member is not an object"
                        )
                    paths.append(next_path)
                else:
                    stack.append((source_member.value, next_path, depth + 1))
        elif type(current) is RawSourceArray:
            for index in range(len(current.items) - 1, -1, -1):
                stack.append(
                    (
                        current.items[index],
                        (*path, RawIndexStep(index)),
                        depth + 1,
                    )
                )
    return tuple(paths)


def _field_entries(
    authority: SourceAuthorityAdapter,
    selection: VerifiedSourceSelection,
    block: RawSourceObject,
    field: DefenseField,
) -> tuple[
    FieldShape | None,
    tuple[tuple[str, SourceReceipt], ...],
]:
    members = tuple(
        (index, member)
        for index, member in enumerate(block.members)
        if member.key == field
    )
    if not members:
        return None, ()
    if len(members) != 1:
        raise DamageDefenseCompileError(
            f"creature has duplicate {field} source members"
        )
    member_ordinal, field_member = members[0]
    raw = field_member.value
    field_path = (
        *selection.address.selection_path,
        RawMemberStep(field, member_ordinal),
    )

    def receipt_for(
        path: tuple[RawPathStep, ...],
    ) -> SourceReceipt:
        selected = authority.resolve(
            authority.address(
                source_id=selection.address.source_id,
                locator=selection.address.locator,
                carrier_path=selection.address.carrier_path,
                selection_path=path,
            )
        )
        return selected.receipt

    if type(raw) is str:
        _require_source_text(raw, f"creature {field}")
        return "scalar", ((raw, receipt_for(field_path)),)
    if type(raw) is not RawSourceArray:
        raise DamageDefenseCompileError(
            f"creature {field} must be a string or exact array"
        )
    if not raw.items or len(raw.items) > MAX_FIELD_ENTRIES:
        raise DamageDefenseCompileError(
            f"creature {field} array has an invalid entry count"
        )
    if any(type(item) is not str for item in raw.items):
        raise DamageDefenseCompileError(
            f"creature {field} array entries must be strings"
        )
    entries: list[tuple[str, SourceReceipt]] = []
    for index, entry in enumerate(raw.items):
        _require_source_text(entry, f"creature {field} entry")
        entries.append(
            (
                entry,
                receipt_for((*field_path, RawIndexStep(index))),
            )
        )
    return "array", tuple(entries)


def _compile_selection(
    authority: SourceAuthorityAdapter,
    selection: VerifiedSourceSelection,
) -> CompiledDamageDefenseProfile:
    selection = authority.validate_selection(selection)
    if selection.address.source_id != MONSTER_CORE_SOURCE_ID:
        raise DamageDefenseCompileError(
            "damage defenses require a Core MC1 creature"
        )
    block = selection.selected_value
    if type(block) is not RawSourceObject:
        raise DamageDefenseCompileError(
            "damage defense consumer must select one creature object"
        )
    names = block.values("Name")
    if len(names) != 1 or type(names[0]) is not str:
        raise DamageDefenseCompileError(
            "creature requires one exact Name source member"
        )
    creature_name = _require_trimmed_text(names[0], "creature name")
    weakness_shape, weakness_entries = _field_entries(
        authority,
        selection,
        block,
        "Weaknesses",
    )
    resistance_shape, resistance_entries = _field_entries(
        authority,
        selection,
        block,
        "Resistances",
    )
    weaknesses = tuple(
        _classify_clause(
            "Weaknesses",
            index,
            entry,
            receipt,
        )
        for index, (entry, receipt) in enumerate(weakness_entries)
    )
    resistances = tuple(
        _classify_clause(
            "Resistances",
            index,
            entry,
            receipt,
        )
        for index, (entry, receipt) in enumerate(resistance_entries)
    )
    return _mint_compiled_profile(
        creature_name=creature_name,
        source_receipt=selection.receipt,
        weakness_shape=weakness_shape,
        resistance_shape=resistance_shape,
        weaknesses=weaknesses,
        resistances=resistances,
        selection=selection,
    )


def _validate_authority(authority: SourceAuthorityAdapter) -> None:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "damage defenses require an exact SourceAuthorityAdapter"
        )
    if not set(SOURCE_SCOPE).issubset(authority.allowed_source_ids):
        raise DamageDefenseCompileError(
            "damage defenses require the reviewed Core source scope"
        )


def compile_damage_defense_profile(
    authority: SourceAuthorityAdapter,
    source_id: str,
    locator: str,
    /,
) -> CompiledDamageDefenseProfile:
    """Compile one exact uniquely targeted Core MC1 creature."""

    _assert_reviewed_configuration()
    _validate_authority(authority)
    if type(source_id) is not str or source_id != MONSTER_CORE_SOURCE_ID:
        raise DamageDefenseCompileError(
            "damage defense source_id must be core-mc1"
        )
    _require_trimmed_text(locator, "damage defense locator")
    target = authority.resolve(
        authority.address(source_id=source_id, locator=locator)
    )
    paths = _find_creature_paths(target.selected_value)
    expected_name = authority.toc_label(source_id, locator)
    matching = []
    for path in paths:
        selection = authority.resolve(
            authority.address(
                source_id=source_id,
                locator=locator,
                selection_path=path,
            )
        )
        block = selection.selected_value
        names = (
            block.values("Name")
            if type(block) is RawSourceObject
            else ()
        )
        if (
            len(names) == 1
            and type(names[0]) is str
            and names[0].strip() == expected_name
        ):
            matching.append(selection)
    if len(matching) != 1:
        raise DamageDefenseCompileError(
            "damage defense locator must identify exactly one creature "
            "by its authenticated ToC label"
        )
    compiled = _compile_selection(authority, matching[0])
    _verify_compiled_providers(authority, compiled)
    return compiled


def _all_clauses(
    value: CompiledDamageDefenseProfile,
) -> tuple[DamageDefenseClause, ...]:
    return (*value.weaknesses, *value.resistances)


def _required_provider_ids(
    value: CompiledDamageDefenseProfile,
) -> tuple[str, ...]:
    ids = {"pc1-apply-iwr", "pc1-immunity"}
    for clause in _all_clauses(value):
        ids.update(clause.provider_rule_ids)
    ordered = tuple(
        requirement.rule_id
        for requirement in _provider_requirements()
        if requirement.rule_id in ids
    )
    if len(ordered) != len(ids):
        raise DamageDefenseCompileError(
            "compiled profile references an unknown provider"
        )
    return ordered


def _verify_compiled_providers(
    authority: SourceAuthorityAdapter,
    value: CompiledDamageDefenseProfile,
) -> None:
    """Verify only the profile's pinned Core providers on the same adapter."""

    requirements = {
        item.rule_id: item for item in _provider_requirements()
    }
    providers = tuple(
        authority.resolve_rule(requirements[rule_id])
        for rule_id in _required_provider_ids(value)
    )
    authority.require_shared_authority(value._selection, providers)


def validate_compiled_damage_defense_profile(
    authority: SourceAuthorityAdapter,
    value: CompiledDamageDefenseProfile,
    /,
) -> CompiledDamageDefenseProfile:
    """Recompile a retained consumer receipt and require exact equality."""

    _assert_reviewed_configuration()
    _validate_authority(authority)
    if type(value) is not CompiledDamageDefenseProfile:
        raise TypeError("compiled damage defense profile must be exact")
    _require_minted_compiled_profile(value)
    selection = authority.reload(value.source_receipt)
    rebuilt = _compile_selection(authority, selection)
    if _compiled_payload(rebuilt) != _compiled_payload(value):
        raise DamageDefenseCompileError(
            "compiled damage defense profile disagrees with source"
        )
    if value._selection is not selection:
        authority.validate_selection(value._selection)
        if value._selection.receipt != selection.receipt:
            raise DamageDefenseCompileError(
                "compiled damage defense retained selection disagrees"
            )
    _verify_compiled_providers(authority, value)
    return value


def _atom_matches(
    atom: DamagePredicateAtom,
    subject: DamageComponent | DamageTrigger,
) -> bool:
    if atom.dimension == "damage-type":
        return (
            type(subject) is DamageComponent
            and subject.damage_type == atom.term
        )
    if atom.dimension == "material":
        return (
            type(subject) is DamageComponent
            and atom.term in subject.materials
        )
    if atom.dimension == "feature":
        return (
            type(subject) is DamageComponent
            and atom.term in subject.features
        )
    if atom.dimension == "effect-trait":
        if atom.term == "magical":
            return bool(_MAGICAL_TRAITS.intersection(subject.effect_traits))
        return atom.term in subject.effect_traits
    raise DamageDefenseInputError("unrecognized exception atom dimension")


def _is_excepted(
    clause: DamageDefenseClause,
    subject: DamageComponent | DamageTrigger,
) -> bool:
    return any(
        all(_atom_matches(atom, subject) for atom in alternative.atoms)
        for alternative in clause.exceptions
    )


def _base_matches(
    clause: DamageDefenseClause,
    subject: DamageComponent | DamageTrigger,
) -> bool:
    kind = clause.predicate_kind
    term = clause.term
    if kind == "damage-type":
        return (
            type(subject) is DamageComponent
            and subject.damage_type == term
        )
    if kind == "physical-family":
        return (
            type(subject) is DamageComponent
            and subject.damage_type in _PHYSICAL_DAMAGE_TYPES
        )
    if kind == "material":
        if type(subject) is not DamageComponent:
            return False
        if term == "silver" and clause.field == "Weaknesses":
            return bool(
                {"silver", "dawnsilver"}.intersection(subject.materials)
            )
        return term in subject.materials
    if kind == "effect-trait":
        return term in subject.effect_traits
    if kind == "damage-category":
        if type(subject) is not DamageComponent:
            return False
        if term == "precision":
            return subject.precision_amount > 0
        if term == "splash":
            return subject.splash_amount > 0
        raise DamageDefenseInputError(
            "unrecognized damage category predicate"
        )
    if kind == "delivery":
        return (
            type(subject) is DamageComponent
            and term in subject.delivery_traits
        )
    if kind == "weapon-group":
        return (
            type(subject) is DamageComponent
            and subject.weapon_group == term
        )
    if kind == "universal":
        return type(subject) is DamageComponent
    if kind == "untyped" and term == "spell":
        return (
            type(subject) is DamageComponent
            and "spell" in subject.delivery_traits
        )
    raise DamageDefenseDeferredError(
        f"damage predicate is not executable: {kind}"
    )


def _matches(
    clause: DamageDefenseClause,
    subject: DamageComponent | DamageTrigger,
) -> bool:
    if clause.support != "supported":
        raise DamageDefenseDeferredError(
            f"deferred damage predicate: {clause.deferred_dependency}"
        )
    return _base_matches(clause, subject) and not _is_excepted(
        clause,
        subject,
    )


def _effective_resistance(
    clause: DamageDefenseClause,
    component: DamageComponent,
) -> int:
    if clause.value is None:
        raise DamageDefenseDeferredError(
            "executable resistance has no numeric value"
        )
    multiplier = 1
    if clause.nonmagical_multiplier == 2 and not (
        _MAGICAL_TRAITS.intersection(component.effect_traits)
    ):
        multiplier = 2
    value = clause.value * multiplier
    if value > MAX_SIGNED_64:
        raise DamageDefenseInputError("effective resistance overflowed")
    return value


def _checked_add(left: int, right: int, label: str) -> int:
    value = left + right
    if value > MAX_SIGNED_64:
        raise DamageDefenseInputError(f"{label} overflowed signed-64")
    return value


def _validate_damage_instance(value: DamageInstance) -> None:
    if type(value) is not DamageInstance:
        raise TypeError("damage must be an exact DamageInstance")
    rebuilt_components = tuple(
        DamageComponent(
            damage_type=item.damage_type,
            amount=item.amount,
            precision_amount=item.precision_amount,
            splash_amount=item.splash_amount,
            materials=item.materials,
            effect_traits=item.effect_traits,
            delivery_traits=item.delivery_traits,
            weapon_group=item.weapon_group,
            features=item.features,
        )
        for item in value.components
    )
    rebuilt_triggers = tuple(
        DamageTrigger(
            effect_traits=item.effect_traits,
        )
        for item in value.triggers
    )
    rebuilt = DamageInstance(
        components=rebuilt_components,
        triggers=rebuilt_triggers,
        phase=value.phase,
    )
    if rebuilt != value:
        raise DamageDefenseInputError(
            "damage instance disagrees with its canonical reconstruction"
        )


def _select_highest(
    candidates: tuple[DamageDefenseClause, ...],
    *,
    resistance_component: DamageComponent | None = None,
) -> DamageDefenseClause | None:
    if not candidates:
        return None

    def value_for(clause: DamageDefenseClause) -> int:
        if clause.value is None:
            raise DamageDefenseDeferredError(
                "executable damage defense has no numeric value"
            )
        return (
            _effective_resistance(clause, resistance_component)
            if resistance_component is not None
            else clause.value
        )

    highest = max(value_for(clause) for clause in candidates)
    selected = tuple(
        clause
        for clause in candidates
        if value_for(clause) == highest
    )
    if len(selected) != 1:
        raise DamageDefenseAmbiguityError(
            "equal highest damage defenses require an explicit choice"
        )
    return selected[0]


def _resistance_scope_amount(
    clause: DamageDefenseClause,
    component: DamageComponent,
    after_weakness: int,
) -> int:
    if clause.predicate_kind != "damage-category":
        return after_weakness
    if clause.term == "precision":
        return component.precision_amount
    if clause.term == "splash":
        return component.splash_amount
    raise DamageDefenseInputError("unknown category resistance scope")


def _removed_damage_defense_resolver(
    authority: SourceAuthorityAdapter,
    profile: LinkedDamageDefenseProfile,
    damage: DamageInstance,
    /,
) -> DamageDefenseResolution:
    """Apply highest matching weakness then resistance without side effects."""

    _assert_reviewed_configuration()
    validate_linked_damage_defense_profile(authority, profile)
    _validate_damage_instance(damage)
    if not profile.resolution_ready:
        raise DamageDefenseDeferredError(
            "damage defense profile has blocking dependencies: "
            + ", ".join(profile.blocking_dependencies)
        )
    weakness_clauses = profile.compiled.weaknesses
    resistance_clauses = profile.compiled.resistances
    components = damage.components
    triggers = damage.triggers

    weakness_matches = tuple(
        clause
        for clause in weakness_clauses
        if any(_matches(clause, item) for item in components)
        or any(_matches(clause, item) for item in triggers)
    )
    selected_weakness = _select_highest(
        weakness_matches,
    )
    weakness_by_component = [0 for _item in components]
    selected_weakness_by_component: list[
        DamageDefenseClause | None
    ] = [None for _item in components]
    standalone_weakness = 0
    if selected_weakness is not None:
        if selected_weakness.value is None:
            raise DamageDefenseDeferredError(
                "selected weakness has no numeric value"
            )
        matched_components = tuple(
            index
            for index, component in enumerate(components)
            if _matches(selected_weakness, component)
        )
        matched_trigger = any(
            _matches(selected_weakness, trigger)
            for trigger in triggers
        )
        if (
            len(matched_components) > 1
            or (matched_trigger and matched_components)
        ):
            raise DamageDefenseAmbiguityError(
                "weakness matches multiple damage allocations"
            )
        if (
            not matched_trigger
            and matched_components
        ):
            target_index = matched_components[0]
            weakness_by_component[target_index] = selected_weakness.value
            selected_weakness_by_component[target_index] = (
                selected_weakness
            )
        else:
            # Source-only weaknesses add damage at event scope.  They must
            # not be disguised as an invented physical damage component.
            standalone_weakness = selected_weakness.value

    # Ordinary resistance is selected once across the whole damage instance.
    # A resistance explicitly authored against all damage is the PC1 exception:
    # it applies separately to each damage type.
    ordinary_resistance_matches = tuple(
        clause
        for clause in resistance_clauses
        if clause.predicate_kind != "universal"
        and any(_matches(clause, component) for component in components)
    )
    selected_ordinary_resistance = _select_highest(
        ordinary_resistance_matches,
    )
    universal_resistance_by_component = tuple(
        _select_highest(
            tuple(
                clause
                for clause in resistance_clauses
                if clause.predicate_kind == "universal"
                and _matches(clause, component)
            ),
            resistance_component=component,
        )
        for component in components
    )
    if (
        selected_ordinary_resistance is not None
        and any(
            item is not None
            for item in universal_resistance_by_component
        )
    ):
        raise DamageDefenseDeferredError(
            "combined ordinary and all-damage resistance requires "
            "an explicit ordering rule"
        )

    after_weakness = tuple(
        _checked_add(
            component.amount,
            weakness_by_component[index],
            "damage after weakness",
        )
        for index, component in enumerate(components)
    )
    resistance_prevented = [0 for _item in components]
    selected_resistance_by_component: list[
        DamageDefenseClause | None
    ] = [None for _item in components]

    if selected_ordinary_resistance is not None:
        if selected_ordinary_resistance.value is None:
            raise DamageDefenseDeferredError(
                "selected resistance has no numeric value"
            )
        matched = tuple(
            index
            for index, component in enumerate(components)
            if _matches(selected_ordinary_resistance, component)
        )
        scope_by_component = {
            index: _resistance_scope_amount(
                selected_ordinary_resistance,
                components[index],
                after_weakness[index],
            )
            for index in matched
        }
        scope_total = 0
        for amount in scope_by_component.values():
            scope_total = _checked_add(
                scope_total,
                amount,
                "ordinary resistance scope",
            )
        prevented_remaining = min(
            scope_total,
            selected_ordinary_resistance.value,
        )
        # The aggregate scope is rules-significant; this allocation is only
        # the deterministic per-type ledger.  Largest scopes are reduced
        # first, with damage type as the stable tie-break.
        for index in sorted(
            matched,
            key=lambda item: (
                -scope_by_component[item],
                components[item].damage_type,
            ),
        ):
            prevented = min(
                scope_by_component[index],
                prevented_remaining,
            )
            resistance_prevented[index] = prevented
            if prevented:
                selected_resistance_by_component[index] = (
                    selected_ordinary_resistance
                )
            prevented_remaining -= prevented
    else:
        for index, selected_resistance in enumerate(
            universal_resistance_by_component
        ):
            if selected_resistance is None:
                continue
            prevented = min(
                after_weakness[index],
                _effective_resistance(
                    selected_resistance,
                    components[index],
                ),
            )
            resistance_prevented[index] = prevented
            selected_resistance_by_component[index] = selected_resistance

    results: list[DamageTypeResolution] = []
    original_total = 0
    resistance_total = 0
    component_final_total = 0
    for index, component in enumerate(components):
        final_amount = (
            after_weakness[index] - resistance_prevented[index]
        )
        result = DamageTypeResolution(
            damage_type=component.damage_type,
            original_amount=component.amount,
            weakness_added=weakness_by_component[index],
            after_weakness=after_weakness[index],
            resistance_prevented=resistance_prevented[index],
            final_amount=final_amount,
            selected_weakness=selected_weakness_by_component[index],
            selected_resistance=selected_resistance_by_component[index],
        )
        results.append(result)
        original_total = _checked_add(
            original_total,
            component.amount,
            "original damage total",
        )
        resistance_total = _checked_add(
            resistance_total,
            resistance_prevented[index],
            "resistance total",
        )
        component_final_total = _checked_add(
            component_final_total,
            final_amount,
            "component final damage total",
        )
    weakness_total = (
        0 if selected_weakness is None else selected_weakness.value
    )
    if type(weakness_total) is not int:
        raise DamageDefenseDeferredError(
            "selected weakness has no numeric value"
        )
    final_total = _checked_add(
        component_final_total,
        standalone_weakness,
        "final damage total",
    )
    return DamageDefenseResolution(
        creature_name=profile.compiled.creature_name,
        components=tuple(results),
        original_total=original_total,
        weakness_total=weakness_total,
        resistance_total=resistance_total,
        final_total=final_total,
        selected_weakness=selected_weakness,
        standalone_weakness_amount=standalone_weakness,
        selected_ordinary_resistance=selected_ordinary_resistance,
    )


def _atom_as_serialized(value: DamagePredicateAtom) -> dict[str, object]:
    return {"dimension": value.dimension, "term": value.term}


def _clause_payload(value: DamageDefenseClause) -> dict[str, object]:
    if type(value) is not DamageDefenseClause:
        raise TypeError("damage defense clause must be exact")
    return {
        "ordinal": value.ordinal,
        "sourceText": value.source_text,
        "support": value.support,
        "predicateKind": value.predicate_kind,
        "term": value.term,
        "value": value.value,
        "exceptions": [
            [_atom_as_serialized(atom) for atom in item.atoms]
            for item in value.exceptions
        ],
        "nonmagicalMultiplier": value.nonmagical_multiplier,
        "providerRuleIds": list(value.provider_rule_ids),
        "deferredDependency": value.deferred_dependency,
    }


def _compiled_payload(
    value: CompiledDamageDefenseProfile,
) -> dict[str, object]:
    if type(value) is not CompiledDamageDefenseProfile:
        raise TypeError("compiled damage defense profile must be exact")
    blocking_dependencies = sorted(
        {
            item.deferred_dependency
            for item in _all_clauses(value)
            if item.deferred_dependency is not None
        }
    )
    return {
        "schema": 1,
        "familyId": FAMILY_ID,
        "mechanicType": MECHANIC_TYPE,
        "creatureName": value.creature_name,
        "profileSupport": (
            "deferred" if blocking_dependencies else "supported"
        ),
        "blockingDependencies": blocking_dependencies,
        "fields": [
            {
                "field": "Weaknesses",
                "shape": value.weakness_shape,
                "entries": [
                    _clause_payload(item) for item in value.weaknesses
                ],
            },
            {
                "field": "Resistances",
                "shape": value.resistance_shape,
                "entries": [
                    _clause_payload(item) for item in value.resistances
                ],
            },
        ],
        "registryStatus": REGISTRY_STATUS,
        "activationStatus": ACTIVATION_STATUS,
        "runtimeActivated": False,
    }


def compiled_damage_defense_as_serialized(
    authority: SourceAuthorityAdapter,
    value: CompiledDamageDefenseProfile,
    /,
) -> dict[str, object]:
    """Serialize a compiler-minted profile after exact source revalidation."""

    _assert_reviewed_configuration()
    validate_compiled_damage_defense_profile(authority, value)
    return _compiled_payload(value)


def compiled_damage_defense_digest(
    authority: SourceAuthorityAdapter,
    value: CompiledDamageDefenseProfile,
    /,
) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            compiled_damage_defense_as_serialized(authority, value)
        )
    ).hexdigest()


def _install_public_api_seal() -> None:
    """Bind every public entry point to the reviewed module implementation."""

    public_names = (
        "damage_defense_provider_requirements",
        "compile_damage_defense_profile",
        "validate_compiled_damage_defense_profile",
        "compiled_damage_defense_as_serialized",
        "compiled_damage_defense_digest",
    )
    module_globals = globals()
    original_public = {
        name: module_globals[name]
        for name in public_names
    }
    protected = {
        name: value
        for name, value in tuple(module_globals.items())
        if (
            not name.startswith("__")
            and name not in public_names
            and name != "_install_public_api_seal"
        )
    }
    expected_public: dict[str, object] = {}
    original_configuration_guard = _assert_reviewed_configuration

    def sealed_guard() -> None:
        if any(
            module_globals.get(name) is not expected
            for name, expected in protected.items()
        ) or any(
            module_globals.get(name) is not expected
            for name, expected in expected_public.items()
        ):
            raise DamageDefenseCompileError(
                "reviewed damage-defense implementation was rebound"
            )
        original_configuration_guard()

    def guarded(function: object) -> object:
        reviewed_signature = inspect_signature(function)

        @wraps(function)
        def invoke(*args: object, **kwargs: object) -> object:
            sealed_guard()
            return function(*args, **kwargs)  # type: ignore[operator]

        delattr(invoke, "__wrapped__")
        invoke.__signature__ = reviewed_signature  # type: ignore[attr-defined]
        return invoke

    for name, function in original_public.items():
        module_globals[name] = guarded(function)
    expected_public.update(
        (name, module_globals[name])
        for name in public_names
    )


_install_public_api_seal()


__all__ = [
    "ACTIVATION_STATUS",
    "CompiledDamageDefenseProfile",
    "DamageDefenseClause",
    "DamageDefenseCompileError",
    "DamagePredicateAtom",
    "DamagePredicateException",
    "FAMILY_ID",
    "MECHANIC_TYPE",
    "REGISTRY_STATUS",
    "SOURCE_SCOPE",
    "compile_damage_defense_profile",
    "compiled_damage_defense_as_serialized",
    "compiled_damage_defense_digest",
    "damage_defense_provider_requirements",
    "validate_compiled_damage_defense_profile",
]

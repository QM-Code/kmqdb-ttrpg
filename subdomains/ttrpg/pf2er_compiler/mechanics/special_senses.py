"""Compile the reviewed Scent, Tremorsense, and Lifesense source fields.

This module is deliberately compile/link-only.  The shared family registry
does not yet have a source-field compiler category, and the encounter model
does not yet have observer-relative detection state.  The local immutable
contracts below prove that boundary without registering a fake named ability
or inventing runtime behavior.

Migration is intentionally narrow:

* Move the duplicate-preserving ``SenseCreatureCarrier``, ``SenseSource``,
  provider blockers, and compiler contracts into ``mechanics.contracts`` when
  the source orchestrator has a source-field category.
* Add ``sense_compilers`` to the shared family fragment and registry only when
  observer-relative detection consumes the compiled definitions.
* Preserve the verified Perception selection, ordered provider receipts,
  companion selections, and zero/one/many ambiguity semantics during that
  move.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import re
from types import MappingProxyType
from typing import Any, Literal, Protocol, TypeAlias, final

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
)
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAddress,
    SourceAddressError,
    SourceAuthorityAdapter,
    SourceAuthorityError,
    SourceReceipt,
    SourceReviewError,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
    canonical_raw_bytes,
    raw_member_sha256,
    raw_source_sha256,
)
from .source_values import MAX_SOURCE_INTEGER, parse_decimal_integer


MONSTER_CORE_SOURCE_ID = "core-mc1"
PERCEPTION_FIELD = "Perception"

SenseFamily: TypeAlias = Literal["scent", "tremorsense", "lifesense"]
SenseChannel: TypeAlias = Literal[
    "olfactory",
    "surface-vibration",
    "vital-essence",
]
SensePrecision: TypeAlias = Literal["precise", "imprecise", "vague"]
CompanionRelation: TypeAlias = Literal["local", "inherited"]
ProviderBlockerReason: TypeAlias = Literal[
    "source-not-selected",
    "source-address-unresolved",
    "reviewed-hash-mismatch",
    "authority-rejected",
]

_SENSE_FAMILIES: tuple[SenseFamily, ...] = (
    "scent",
    "tremorsense",
    "lifesense",
)
_SENSE_CHANNELS: tuple[SenseChannel, ...] = (
    "olfactory",
    "surface-vibration",
    "vital-essence",
)
_SENSE_PRECISIONS: tuple[SensePrecision, ...] = (
    "precise",
    "imprecise",
    "vague",
)
_COMPANION_RELATIONS: tuple[CompanionRelation, ...] = (
    "local",
    "inherited",
)
_PROVIDER_BLOCKER_REASONS: tuple[ProviderBlockerReason, ...] = (
    "source-not-selected",
    "source-address-unresolved",
    "reviewed-hash-mismatch",
    "authority-rejected",
)
SENSE_FAMILIES = _SENSE_FAMILIES
SENSE_CHANNELS = _SENSE_CHANNELS
SENSE_PRECISIONS = _SENSE_PRECISIONS
COMPANION_RELATIONS = _COMPANION_RELATIONS
PROVIDER_BLOCKER_REASONS = _PROVIDER_BLOCKER_REASONS

MIGRATION_NOTES = (
    "Move the duplicate-preserving SenseCreatureCarrier, SenseSource, "
    "provider blockers, and compiler contracts into mechanics.contracts "
    "when the source orchestrator has a source-field category.",
    "Add sense_compilers to the shared family fragment and registry only "
    "when observer-relative detection consumes the compiled definitions.",
    "Preserve the verified Perception selection, ordered provider receipts, "
    "companion selections, and zero/one/many ambiguity semantics during "
    "that move.",
)

_LOCATOR_RE = re.compile(r"^[1-9][0-9]*\.[1-9][0-9]*$", re.ASCII)
_KNOWN_FAMILY_PREFIX_RE = re.compile(
    r"^(?:"
    r"scent|"
    r"sin[ \t\n\r\f\v]+scent|"
    r"blood[ \t\n\r\f\v]+scent|"
    r"tremorsense|"
    r"lifesense"
    r")(?:$|[^a-z])",
    re.ASCII | re.IGNORECASE,
)
_MAX_IDENTIFIER_BYTES = 4_096
_MAX_SOURCE_TOKEN_BYTES = 4_096
_MAX_COLLECTION_ITEMS = 4_096
_MAX_CARRIER_BYTES = 4 * 1024 * 1024
_PERCEPTION_MODIFIER_RE = re.compile(
    r"^(?P<base>[+-][0-9]+)"
    r"(?: \((?P<sense_motive>[+-][0-9]+) to Sense Motive\))?$",
    re.ASCII,
)
_RANGED_SENSE_RE = MappingProxyType({
    "scent": re.compile(
        r"^scent(?: \((?P<precision>precise|imprecise|vague)\))? "
        r"(?P<range>[1-9][0-9]*) feet$",
        re.ASCII,
    ),
    "tremorsense": re.compile(
        r"^tremorsense"
        r"(?: \((?P<precision>precise|imprecise|vague)\))? "
        r"(?P<range>[1-9][0-9]*) feet$",
        re.ASCII,
    ),
    "lifesense": re.compile(
        r"^lifesense"
        r"(?: \((?P<precision>precise|imprecise|vague)\))? "
        r"(?P<range>[1-9][0-9]*) feet"
        r"(?P<page> \(page 359\))?$",
        re.ASCII,
    ),
})
_SIN_SCENT_RE = re.compile(
    r"^sin scent \((?P<precision>precise|imprecise|vague)\) "
    r"(?P<range>[1-9][0-9]*) feet$",
    re.ASCII,
)

_SIN_DESCRIPTION = (
    "A sinspawn can smell creatures that reflect its sin as the scent "
    "ability. The GM determines which creatures are appropriately sinful."
)
_BLOOD_DESCRIPTION = (
    "The shark can smell blood in the water from up to 1 mile away."
)
_BLOOD_INHERITANCE = "As great white shark."

_SIN_DEFINITION_SHA256 = (
    "d99af7d3d62538c5d9a0cc82d1eeffc31e5486b9fcce379d439253f65ce26da3"
)
_GREAT_WHITE_DEFINITION_SHA256 = (
    "5cf6c1cdbc03771379fc09ab45e6cc0d182b8de6f442c22c8576ef848ecde53d"
)
_MEGALODON_DEFINITION_SHA256 = (
    "e86f577a1a6cedcc9b2076e4d7f991b198e1db00505fd0616e810647d05575cd"
)

_SIN_BLOCK_SHA256 = (
    "6ccad4d0bc09c486fb801b13921ba87a5a42e35c713e3342f05a565cc54a8a9a"
)
_GREAT_WHITE_BLOCK_SHA256 = (
    "69e053c7ac7ac49f20f3949d3bba9b1c25d05c3a0fe224b8f7bdd70e513fddb4"
)
_MEGALODON_BLOCK_SHA256 = (
    "1d324828ff4e18363beb48055b3f689c7f46ee11bf24a2e6ea17883331218a6f"
)


def _require_key(value: object, label: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{label} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{label} exceeds its UTF-8 byte bound")


def _require_nonnegative_integer(value: object, label: str) -> None:
    if (
        type(value) is not int
        or value < 0
        or value > MAX_SOURCE_INTEGER
    ):
        raise ValueError(
            f"{label} must be a non-negative signed 64-bit integer"
        )


def _require_source_token(value: object, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be an exact string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > _MAX_SOURCE_TOKEN_BYTES:
        raise ValueError(f"{label} exceeds its UTF-8 byte bound")
    return value


PRECISE_RULE = RuleRequirement(
    rule_id="precise-senses",
    source_id="core-pc1",
    locator="433.1",
    expected_block_sha256=(
        "bcfd6e0903072c9191408000ce7a599b48cf196a25f89212f4c655e4c039619d"
    ),
)
IMPRECISE_RULE = RuleRequirement(
    rule_id="imprecise-senses",
    source_id="core-pc1",
    locator="433.2",
    expected_block_sha256=(
        "9f200ee5255f8bd7a02c9858aba1160ad19c29b3e09505cea112ff3b4b8823d1"
    ),
)
VAGUE_RULE = RuleRequirement(
    rule_id="vague-senses",
    source_id="core-pc1",
    locator="433.3",
    expected_block_sha256=(
        "469ae7a8231fbb1aba59ee1ae07541ea26d2a8f29a7f72327e7abd814a4ed156"
    ),
)
OTHER_SENSES_RULE = RuleRequirement(
    rule_id="detecting-with-other-senses",
    source_id="core-pc1",
    locator="432.6",
    carrier_path=(RawMemberStep("~.aside", 4),),
    expected_block_sha256=(
        "c43f8caa81261268e60d84d71589f331bcf379582e7afdbc34ea22b841bc7189"
    ),
)
SCENT_RULE = RuleRequirement(
    rule_id="scent",
    source_id="core-pc1",
    locator="433.8",
    expected_block_sha256=(
        "f85cf166a15b84e3f667b88c3232f687f0dfc9b16e226c7683134ff07e3ef44b"
    ),
)
TREMORSENSE_RULE = RuleRequirement(
    rule_id="tremorsense",
    source_id="core-pc1",
    locator="433.9",
    expected_block_sha256=(
        "85ff8b68deb37d0c93cd42eab2b46a2344d9d9e558398818c7145726a6729238"
    ),
)
OBSERVED_RULE = RuleRequirement(
    rule_id="observed",
    source_id="core-pc1",
    locator="434.2",
    expected_block_sha256=(
        "038b71d1754038e7e448dcc737a142bb8a051fe70559d502b93b6d0d32a1da7b"
    ),
)
HIDDEN_RULE = RuleRequirement(
    rule_id="hidden",
    source_id="core-pc1",
    locator="434.3",
    expected_block_sha256=(
        "e554898da2b5c6d59dab8a1d67e82a5834b3f283d13c263dab955d83e6091b5e"
    ),
)
UNDETECTED_RULE = RuleRequirement(
    rule_id="undetected",
    source_id="core-pc1",
    locator="434.4",
    expected_block_sha256=(
        "71bbdd2ee53303fc2c776cf8e5b151bb50e98a83fff2d683ef3c585755c5444a"
    ),
)
CONCEALED_RULE = RuleRequirement(
    rule_id="concealed",
    source_id="core-pc1",
    locator="434.6",
    expected_block_sha256=(
        "962131df90bda85c27ad9988ba1d3d7d5ee792688b3fe5245a18ae12b4587f87"
    ),
)
INVISIBLE_RULE = RuleRequirement(
    rule_id="invisible",
    source_id="core-pc1",
    locator="434.7",
    expected_block_sha256=(
        "9b127fc1e4f59580bc4bc375b049f42fcd0f92beb47196631937e1d82b0bd924"
    ),
)
FLAT_CHECKS_RULE = RuleRequirement(
    rule_id="flat-checks",
    source_id="core-pc1",
    locator="400.1",
    carrier_path=(RawMemberStep("~.aside", 14),),
    expected_block_sha256=(
        "4d885327ea2efa894d58d901fe2d3e5a6e05b8bb004d627423d028894f63b0a7"
    ),
)
CREATURE_DESIGN_SENSES_RULE = RuleRequirement(
    rule_id="creature-design-senses",
    source_id="core-gmc",
    locator="115.2",
    expected_block_sha256=(
        "0a4d09c02efa38f3de5e77c72e067ea7fb77e25729ca296904c47def09e390b1"
    ),
)

FOUNDATIONAL_RULES = (
    PRECISE_RULE,
    IMPRECISE_RULE,
    VAGUE_RULE,
    OTHER_SENSES_RULE,
    SCENT_RULE,
    TREMORSENSE_RULE,
    OBSERVED_RULE,
    HIDDEN_RULE,
    UNDETECTED_RULE,
    CONCEALED_RULE,
    INVISIBLE_RULE,
    FLAT_CHECKS_RULE,
    CREATURE_DESIGN_SENSES_RULE,
)

LIFESENSE_GLOSSARY = RuleRequirement(
    rule_id="lifesense-glossary",
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
    carrier_path=(RawMemberStep("^.ability", 21),),
    expected_block_sha256=(
        "5b99df686ca25779b9d39f84d8f85cde5ba43e7de311285cd707fcc7779c5919"
    ),
)
SCENT_GLOSSARY = RuleRequirement(
    rule_id="scent-glossary",
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
    carrier_path=(RawMemberStep("^.ability", 30),),
    expected_block_sha256=(
        "59d1da95ffb68a66c6e73de70e4be1ec0d669c039c5412becfe1c0607c442aa4"
    ),
)
TREMORSENSE_GLOSSARY = RuleRequirement(
    rule_id="tremorsense-glossary",
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
    carrier_path=(RawMemberStep("^.ability", 38),),
    expected_block_sha256=(
        "797ca105d2d1e6a93818547648966c231a0233c18af644667b97579373422894"
    ),
)

GLOSSARY_RULES: tuple[RuleRequirement, ...] = (
    SCENT_GLOSSARY,
    TREMORSENSE_GLOSSARY,
    LIFESENSE_GLOSSARY,
)


def _copied_requirement(value: RuleRequirement) -> RuleRequirement:
    return RuleRequirement(
        rule_id=value.rule_id,
        source_id=value.source_id,
        locator=value.locator,
        carrier_path=value.carrier_path,
        selection_path=value.selection_path,
        span=value.span,
        expected_block_sha256=value.expected_block_sha256,
        expected_member_sha256=value.expected_member_sha256,
        expected_value_sha256=value.expected_value_sha256,
        expected_selection_sha256=value.expected_selection_sha256,
    )


# Internal reviewed descriptors do not alias the exported discovery values.
# Rebinding or mutating a public constant therefore cannot change compilation.
_REVIEWED_FOUNDATIONAL_RULES = tuple(
    _copied_requirement(requirement)
    for requirement in FOUNDATIONAL_RULES
)
_REVIEWED_GLOSSARY_RULES = tuple(
    _copied_requirement(requirement)
    for requirement in GLOSSARY_RULES
)


def _raw_serialized(value: Any) -> Any:
    """Return a JSON value that retains array order and object duplicates."""

    if type(value) is RawSourceArray:
        if type(value.items) is not tuple:
            raise TypeError("raw source arrays require exact tuple items")
        return {
            "kind": "array",
            "items": [_raw_serialized(item) for item in value.items],
        }
    if type(value) is RawSourceObject:
        if type(value.members) is not tuple or any(
            type(member) is not RawSourceMember
            or type(member.key) is not str
            for member in value.members
        ):
            raise TypeError(
                "raw source objects require exact ordered members"
            )
        return {
            "kind": "object",
            "members": [
                {
                    "key": member.key,
                    "value": _raw_serialized(member.value),
                }
                for member in value.members
            ],
        }
    if value is None or type(value) in (bool, int, float, str):
        canonical_raw_bytes(value)
        return value
    raise TypeError("raw source primitive has a non-exact type")


def _raw_member_serialized(member: RawSourceMember) -> dict[str, Any]:
    return {
        "key": member.key,
        "value": _raw_serialized(member.value),
    }


class SenseSourceAmbiguityError(ValueError):
    """The full Perception carrier is duplicate or internally ambiguous."""


class SenseSourceAuthorityError(ValueError):
    """A source or provider failed the selected-source authority gate."""


@final
@dataclass(frozen=True, slots=True)
class SenseProviderBlocker:
    """One required provider that the selected-source authority cannot issue."""

    rule_id: str
    source_id: str
    locator: str
    reason: ProviderBlockerReason

    def __post_init__(self) -> None:
        if type(self) is not SenseProviderBlocker:
            raise TypeError("SenseProviderBlocker subclasses are unsupported")
        _require_key(self.rule_id, "SenseProviderBlocker.rule_id")
        _require_key(self.source_id, "SenseProviderBlocker.source_id")
        _require_key(self.locator, "SenseProviderBlocker.locator")
        if _LOCATOR_RE.fullmatch(self.locator) is None:
            raise ValueError("SenseProviderBlocker.locator must be numeric")
        if (
            type(self.reason) is not str
            or self.reason not in _PROVIDER_BLOCKER_REASONS
        ):
            raise ValueError("SenseProviderBlocker.reason is invalid")

    def as_serialized(self) -> dict[str, str]:
        SenseProviderBlocker.__post_init__(self)
        return {
            "ruleId": self.rule_id,
            "sourceId": self.source_id,
            "locator": self.locator,
            "reason": self.reason,
            "status": "blocked",
        }


@final
@dataclass(frozen=True, slots=True)
class SenseProviderEvidence:
    """Reusable provider evidence fully checked against one immutable scope."""

    authority: SourceAuthorityAdapter = field(
        repr=False,
        compare=False,
    )
    family: SenseFamily
    rules: tuple[VerifiedRuleReceipt, ...]
    blockers: tuple[SenseProviderBlocker, ...]

    def __post_init__(self) -> None:
        if type(self) is not SenseProviderEvidence:
            raise TypeError("SenseProviderEvidence subclasses are unsupported")
        if type(self.authority) is not SourceAuthorityAdapter:
            raise TypeError(
                "SenseProviderEvidence.authority must be an exact "
                "SourceAuthorityAdapter"
            )
        if (
            type(self.family) is not str
            or self.family not in _SENSE_FAMILIES
        ):
            raise ValueError("SenseProviderEvidence.family is invalid")
        _validate_provider_evidence(
            self.authority,
            self.family,
            self.rules,
            self.blockers,
            resolve_authority=True,
        )

    def validate_for(
        self,
        consumer: VerifiedSourceSelection,
        /,
    ) -> None:
        """Recheck structure and bind one consumer to this exact adapter."""

        _validate_provider_evidence(
            self.authority,
            self.family,
            self.rules,
            self.blockers,
            resolve_authority=False,
        )
        try:
            if self.rules:
                self.authority.require_shared_authority(
                    consumer,
                    self.rules,
                )
            else:
                self.authority.validate_selection(consumer)
        except (SourceAuthorityError, TypeError, AttributeError) as failure:
            raise SenseSourceAuthorityError(
                "sense consumer failed explicit provider authority"
            ) from failure


@final
@dataclass(frozen=True, slots=True)
class SenseCreatureCarrier:
    """One authority-verified creature selected at its Perception member."""

    authority: SourceAuthorityAdapter = field(
        repr=False,
        compare=False,
    )
    selection: VerifiedSourceSelection

    def __post_init__(self) -> None:
        if type(self) is not SenseCreatureCarrier:
            raise TypeError("SenseCreatureCarrier subclasses are unsupported")
        if type(self.authority) is not SourceAuthorityAdapter:
            raise TypeError(
                "SenseCreatureCarrier.authority must be an exact "
                "SourceAuthorityAdapter"
            )
        if type(self.selection) is not VerifiedSourceSelection:
            raise TypeError(
                "SenseCreatureCarrier.selection must be an exact "
                "VerifiedSourceSelection"
            )
        try:
            verified = self.authority.validate_selection(self.selection)
        except SourceAuthorityError as failure:
            raise SenseSourceAuthorityError(
                "SenseCreatureCarrier selection failed authority validation"
            ) from failure
        object.__setattr__(self, "selection", verified)
        self._require_shape(verified)

    @staticmethod
    def _require_shape(selection: VerifiedSourceSelection) -> None:
        if type(selection) is not VerifiedSourceSelection:
            raise TypeError(
                "SenseCreatureCarrier requires an exact verified selection"
            )
        address = selection.address
        carrier = selection.carrier
        if type(address) is not SourceAddress:
            raise TypeError(
                "SenseCreatureCarrier address must be exact SourceAddress"
            )
        if type(carrier) is not VerifiedSourceCarrier:
            raise TypeError(
                "SenseCreatureCarrier raw carrier must be verified"
            )
        if (
            address.span is not None
            or type(address.selection_path) is not tuple
            or len(address.selection_path) != 1
            or type(address.selection_path[0]) is not RawMemberStep
        ):
            raise ValueError(
                "SenseCreatureCarrier must select one complete Perception "
                "member"
            )
        field_step = address.selection_path[0]
        if field_step.raw_key != PERCEPTION_FIELD:
            raise ValueError(
                "SenseCreatureCarrier selection must be exact Perception"
            )
        if (
            type(address.carrier_path) is not tuple
            or not address.carrier_path
            or type(address.carrier_path[-1]) is not RawMemberStep
            or address.carrier_path[-1].raw_key != "^.creature"
        ):
            raise ValueError(
                "SenseCreatureCarrier must select an exact creature carrier"
            )
        raw_block = carrier.raw_block
        if type(raw_block) is not RawSourceObject:
            raise TypeError(
                "SenseCreatureCarrier raw block must be RawSourceObject"
            )
        if (
            type(raw_block.members) is not tuple
            or not raw_block.members
            or len(raw_block.members) > _MAX_COLLECTION_ITEMS
            or any(
                type(member) is not RawSourceMember
                or type(member.key) is not str
                for member in raw_block.members
            )
        ):
            raise ValueError(
                "SenseCreatureCarrier raw block has an invalid exact member "
                "collection"
            )
        if len(canonical_raw_bytes(raw_block)) > _MAX_CARRIER_BYTES:
            raise ValueError(
                "SenseCreatureCarrier raw block exceeds its byte bound"
            )
        if field_step.member_ordinal >= len(raw_block.members):
            raise ValueError(
                "SenseCreatureCarrier Perception ordinal is out of range"
            )
        raw_member = raw_block.members[field_step.member_ordinal]
        if (
            type(selection.raw_member) is not RawSourceMember
            or selection.raw_member is not raw_member
            or raw_member.key != PERCEPTION_FIELD
            or selection.raw_value is not raw_member.value
            or selection.selected_value is not selection.raw_value
            or type(selection.raw_value) is not RawSourceArray
        ):
            raise ValueError(
                "SenseCreatureCarrier Perception selection disagrees with "
                "its exact raw member"
            )
        if (
            selection.block_sha256 != raw_source_sha256(raw_block)
            or selection.member_sha256 != raw_member_sha256(raw_member)
            or selection.value_sha256
            != raw_source_sha256(selection.raw_value)
            or selection.selection_sha256 != selection.value_sha256
        ):
            raise ValueError(
                "SenseCreatureCarrier verified hashes do not replay"
            )
        normalized_names = [
            member
            for member in raw_block.members
            if member.key.strip().casefold() == "name"
        ]
        names = raw_block.values("Name")
        if (
            len(normalized_names) != 1
            or len(names) != 1
            or type(names[0]) is not str
        ):
            raise ValueError(
                "SenseCreatureCarrier requires one exact Name member"
            )
        _require_key(names[0], "SenseCreatureCarrier creature Name")
        if (
            type(carrier.source_id) is not str
            or type(carrier.locator) is not str
            or type(carrier.section_id) is not str
            or _LOCATOR_RE.fullmatch(carrier.locator) is None
            or carrier.source_id != address.source_id
            or carrier.locator != address.locator
            or carrier.section_id != address.section_id
        ):
            raise ValueError(
                "SenseCreatureCarrier verified source identity is incoherent"
            )

    def validated_selection(self) -> VerifiedSourceSelection:
        try:
            selection = self.authority.validate_selection(self.selection)
        except (SourceAuthorityError, TypeError) as failure:
            raise SenseSourceAuthorityError(
                "SenseCreatureCarrier selection is no longer authoritative"
            ) from failure
        self._require_shape(selection)
        return selection

    @property
    def raw_block(self) -> RawSourceObject:
        return self.selection.carrier.raw_block

    @property
    def source_id(self) -> str:
        return self.selection.address.source_id

    @property
    def locator(self) -> str:
        return self.selection.address.locator

    @property
    def section_id(self) -> str:
        return self.selection.address.section_id

    @property
    def creature_name(self) -> str:
        value = self.raw_block.values("Name")[0]
        assert type(value) is str
        return value

    @property
    def block_sha256(self) -> str:
        return self.selection.block_sha256

    @property
    def receipt(self) -> SourceReceipt:
        return self.selection.receipt

    def as_serialized(self) -> dict[str, Any]:
        self.validated_selection()
        return {
            "sourceId": self.source_id,
            "locator": self.locator,
            "sectionId": self.section_id,
            "creatureName": self.creature_name,
            "blockSha256": self.block_sha256,
            "receipt": self.receipt.as_serialized(),
        }


@final
@dataclass(frozen=True, slots=True)
class SenseCompanionSource:
    """One exact local definition or explicitly resolved inherited target."""

    relation: CompanionRelation
    carrier: SenseCreatureCarrier
    selection: VerifiedSourceSelection

    def __post_init__(self) -> None:
        if type(self) is not SenseCompanionSource:
            raise TypeError("SenseCompanionSource subclasses are unsupported")
        if type(self.relation) is not str:
            raise TypeError(
                "SenseCompanionSource.relation must be a string"
            )
        if self.relation not in _COMPANION_RELATIONS:
            raise ValueError(
                "SenseCompanionSource.relation must be local or inherited"
            )
        if type(self.carrier) is not SenseCreatureCarrier:
            raise TypeError(
                "SenseCompanionSource.carrier must be a "
                "SenseCreatureCarrier"
            )
        if type(self.selection) is not VerifiedSourceSelection:
            raise TypeError(
                "SenseCompanionSource.selection must be an exact "
                "VerifiedSourceSelection"
            )
        try:
            verified = self.carrier.authority.validate_selection(
                self.selection
            )
        except SourceAuthorityError as failure:
            raise SenseSourceAuthorityError(
                "SenseCompanionSource selection failed authority validation"
            ) from failure
        object.__setattr__(self, "selection", verified)
        carrier_selection = self.carrier.selection
        self.carrier._require_shape(carrier_selection)
        address = verified.address
        carrier_address = carrier_selection.address
        if (
            type(address) is not SourceAddress
            or type(address.selection_path) is not tuple
            or len(address.selection_path) != 1
            or type(address.selection_path[0]) is not RawMemberStep
            or address.span is not None
        ):
            raise ValueError(
                "SenseCompanionSource must select one complete direct member"
            )
        if (
            address.source_id != carrier_address.source_id
            or address.locator != carrier_address.locator
            or address.section_id != carrier_address.section_id
            or address.target_path != carrier_address.target_path
            or address.carrier_path != carrier_address.carrier_path
            or verified.block_sha256 != carrier_selection.block_sha256
            or verified.carrier.raw_block != self.carrier.raw_block
        ):
            raise SenseSourceAuthorityError(
                "SenseCompanionSource changed its verified creature carrier"
            )
        step = address.selection_path[0]
        if (
            step.member_ordinal >= len(self.carrier.raw_block.members)
            or not step.raw_key.startswith("!.")
            or len(step.raw_key) <= 2
        ):
            raise ValueError(
                "SenseCompanionSource member is not an exact named ability"
            )
        selected_member = self.carrier.raw_block.members[
            step.member_ordinal
        ]
        if (
            type(verified.raw_member) is not RawSourceMember
            or verified.raw_member != selected_member
            or selected_member.key != step.raw_key
            or verified.raw_value != selected_member.value
            or verified.selected_value != verified.raw_value
            or verified.member_sha256
            != raw_member_sha256(selected_member)
            or verified.value_sha256
            != raw_source_sha256(selected_member.value)
        ):
            raise ValueError(
                "SenseCompanionSource verified member does not replay"
            )
        normalized_key = self.raw_member.key.strip().casefold()
        matches = [
            member
            for member in self.carrier.raw_block.members
            if member.key.strip().casefold() == normalized_key
        ]
        if len(matches) != 1:
            raise SenseCompanionAmbiguityError(
                "SenseCompanionSource companion member is duplicate or "
                "near-duplicate"
            )
        if self.description is None:
            raise ValueError(
                "SenseCompanionSource requires exactly one Description member"
            )

    @property
    def raw_member(self) -> RawSourceMember:
        raw_member = self.selection.raw_member
        assert type(raw_member) is RawSourceMember
        return raw_member

    @property
    def member_ordinal(self) -> int:
        step = self.selection.address.selection_path[0]
        assert type(step) is RawMemberStep
        return step.member_ordinal

    @property
    def raw_member_occurrence(self) -> int:
        return sum(
            member.key == self.raw_member.key
            for member in self.carrier.raw_block.members[
                : self.member_ordinal
            ]
        )

    @property
    def matching_member_count(self) -> int:
        return sum(
            member.key == self.raw_member.key
            for member in self.carrier.raw_block.members
        )

    @property
    def definition_sha256(self) -> str:
        return self.selection.value_sha256

    @property
    def description(self) -> str | None:
        value = self.raw_member.value
        if (
            type(value) is not RawSourceObject
            or value.keys != ("Description",)
        ):
            return None
        description = value.values("Description")
        return (
            description[0]
            if len(description) == 1
            and type(description[0]) is str
            else None
        )

    @property
    def source_id(self) -> str:
        return self.carrier.source_id

    @property
    def locator(self) -> str:
        return self.carrier.locator

    @property
    def section_id(self) -> str:
        return self.carrier.section_id

    @property
    def creature_name(self) -> str:
        return self.carrier.creature_name

    @property
    def block_sha256(self) -> str:
        return self.carrier.block_sha256

    def as_serialized(self) -> dict[str, Any]:
        SenseCompanionSource.__post_init__(self)
        result = self.carrier.as_serialized()
        result.update(
            {
                "relation": self.relation,
                "memberOrdinal": self.member_ordinal,
                "rawMemberOccurrence": self.raw_member_occurrence,
                "matchingMemberCount": self.matching_member_count,
                "definitionSha256": self.definition_sha256,
                "receipt": self.selection.receipt.as_serialized(),
                "description": self.description,
                "rawMember": _raw_member_serialized(self.raw_member),
            }
        )
        return result


def _normalized_sense_id(raw_sense: str) -> str | None:
    if type(raw_sense) is not str:
        return None
    for family, pattern in _RANGED_SENSE_RE.items():
        match = pattern.fullmatch(raw_sense)
        if match is not None and _positive_range(match) is not None:
            return family
    match = _SIN_SCENT_RE.fullmatch(raw_sense)
    if match is not None and _positive_range(match) is not None:
        return "sin-scent"
    if raw_sense == "blood scent":
        return "blood-scent"
    return None


def _known_family_candidate(raw_sense: str) -> bool:
    """Whether an exact token purports to use one supported family grammar."""

    return (
        type(raw_sense) is str
        and _KNOWN_FAMILY_PREFIX_RE.match(raw_sense) is not None
    )


@final
@dataclass(frozen=True, slots=True)
class SenseSource:
    """One selected sense inside a complete exact Perception carrier."""

    carrier: SenseCreatureCarrier
    sense_index: int
    companions: tuple[SenseCompanionSource, ...] = ()

    def __post_init__(self) -> None:
        if type(self) is not SenseSource:
            raise TypeError("SenseSource subclasses are unsupported")
        if type(self.carrier) is not SenseCreatureCarrier:
            raise TypeError(
                "SenseSource.carrier must be a SenseCreatureCarrier"
            )
        selection = self.carrier.selection
        self.carrier._require_shape(selection)
        normalized_matches = [
            member
            for member in self.carrier.raw_block.members
            if member.key.strip().casefold() == PERCEPTION_FIELD.casefold()
        ]
        if len(normalized_matches) != 1:
            raise SenseSourceAmbiguityError(
                "SenseSource Perception member is duplicate or near-duplicate"
            )
        if self.raw_member.key != PERCEPTION_FIELD:
            raise ValueError(
                "SenseSource requires the exact Perception member"
            )
        if (
            selection.value_sha256
            != raw_source_sha256(self.raw_member.value)
            or selection.member_sha256
            != raw_member_sha256(self.raw_member)
        ):
            raise ValueError(
                "SenseSource Perception verified hashes do not replay"
            )
        raw_value = self.raw_member.value
        if type(raw_value) is not RawSourceArray:
            raise TypeError(
                "SenseSource.raw_member value must be a RawSourceArray"
            )
        if type(raw_value.items) is not tuple or len(raw_value.items) != 2:
            raise ValueError(
                "SenseSource Perception array must contain modifier and senses"
            )
        modifier, raw_senses = raw_value.items
        if type(modifier) is str:
            _require_source_token(
                modifier,
                "SenseSource Perception modifier",
            )
        modifier_match = (
            _PERCEPTION_MODIFIER_RE.fullmatch(modifier)
            if type(modifier) is str
            else None
        )
        if modifier_match is None or any(
            value is not None and parse_decimal_integer(value) is None
            for value in modifier_match.groupdict().values()
        ):
            raise ValueError(
                "SenseSource Perception modifier must be an exact bounded "
                "signed decimal"
            )
        if type(raw_senses) is not RawSourceArray:
            raise TypeError(
                "SenseSource Perception senses must be a RawSourceArray"
            )
        if type(raw_senses.items) is not tuple:
            raise TypeError(
                "SenseSource Perception senses require an exact tuple"
            )
        if not raw_senses.items:
            raise ValueError(
                "SenseSource Perception senses must not be empty"
            )
        if len(raw_senses.items) > _MAX_COLLECTION_ITEMS:
            raise ValueError(
                "SenseSource Perception senses exceed their item bound"
            )
        for index, raw_sense in enumerate(raw_senses.items):
            _require_source_token(
                raw_sense,
                f"SenseSource Perception sense[{index}]",
            )
        _require_nonnegative_integer(
            self.sense_index,
            "SenseSource.sense_index",
        )
        if self.sense_index >= len(raw_senses.items):
            raise ValueError("SenseSource.sense_index is outside senses array")
        normalized_ids = [
            sense_id
            for raw_sense in raw_senses.items
            if (sense_id := _normalized_sense_id(raw_sense)) is not None
        ]
        malformed_known = [
            raw_sense
            for raw_sense in raw_senses.items
            if _known_family_candidate(raw_sense)
            and _normalized_sense_id(raw_sense) is None
        ]
        if malformed_known:
            raise SenseSourceAmbiguityError(
                "SenseSource has malformed known-family sense siblings: "
                + ", ".join(repr(item) for item in malformed_known)
            )
        duplicates = sorted(
            {
                sense_id
                for sense_id in normalized_ids
                if normalized_ids.count(sense_id) > 1
            }
        )
        if duplicates:
            raise SenseSourceAmbiguityError(
                "SenseSource has duplicate normalized sense IDs: "
                + ", ".join(repr(item) for item in duplicates)
            )
        if type(self.companions) is not tuple:
            raise TypeError("SenseSource.companions must be an explicit tuple")
        if len(self.companions) > _MAX_COLLECTION_ITEMS:
            raise ValueError(
                "SenseSource.companions exceed their item bound"
            )
        for companion in self.companions:
            if type(companion) is not SenseCompanionSource:
                raise TypeError(
                    "SenseSource.companions must contain only "
                    "SenseCompanionSource values"
                )
            if companion.carrier.authority is not self.carrier.authority:
                raise SenseSourceAuthorityError(
                    "SenseSource companions must use the selected-source "
                    "authority adapter"
                )
            companion_address = companion.selection.address
            carrier_address = companion.carrier.selection.address
            if (
                companion_address.source_id != carrier_address.source_id
                or companion_address.locator != carrier_address.locator
                or companion_address.section_id != carrier_address.section_id
                or companion_address.target_path
                != carrier_address.target_path
                or companion_address.carrier_path
                != carrier_address.carrier_path
            ):
                raise SenseSourceAuthorityError(
                    "SenseSource companion changed its verified carrier"
                )

    @property
    def field_name(self) -> str:
        return self.raw_member.key

    @property
    def raw_member(self) -> RawSourceMember:
        raw_member = self.carrier.selection.raw_member
        assert type(raw_member) is RawSourceMember
        return raw_member

    @property
    def field_member_ordinal(self) -> int:
        step = self.carrier.selection.address.selection_path[0]
        assert type(step) is RawMemberStep
        return step.member_ordinal

    @property
    def raw_member_occurrence(self) -> int:
        return sum(
            member.key == self.raw_member.key
            for member in self.carrier.raw_block.members[
                : self.field_member_ordinal
            ]
        )

    @property
    def matching_field_member_count(self) -> int:
        return sum(
            member.key == self.raw_member.key
            for member in self.carrier.raw_block.members
        )

    @property
    def source_id(self) -> str:
        return self.carrier.source_id

    @property
    def locator(self) -> str:
        return self.carrier.locator

    @property
    def section_id(self) -> str:
        return self.carrier.section_id

    @property
    def creature_name(self) -> str:
        return self.carrier.creature_name

    @property
    def block_sha256(self) -> str:
        return self.carrier.block_sha256

    @property
    def perception_value_sha256(self) -> str:
        return self.carrier.selection.value_sha256

    @property
    def perception_modifier_source(self) -> str:
        return self.raw_member.value.items[0]

    @property
    def raw_senses(self) -> tuple[str, ...]:
        return self.raw_member.value.items[1].items

    @property
    def raw_sense(self) -> str:
        return self.raw_senses[self.sense_index]

    def as_serialized(self) -> dict[str, Any]:
        SenseSource.__post_init__(self)
        self.carrier.validated_selection()
        result = self.carrier.as_serialized()
        result.update(
            {
                "fieldName": self.field_name,
                "fieldMemberOrdinal": self.field_member_ordinal,
                "rawMemberOccurrence": self.raw_member_occurrence,
                "matchingFieldMemberCount": (
                    self.matching_field_member_count
                ),
                "perceptionValueSha256": self.perception_value_sha256,
                "senseIndex": self.sense_index,
                "rawSense": self.raw_sense,
                "rawMember": _raw_member_serialized(self.raw_member),
            }
        )
        return result


@final
@dataclass(frozen=True, slots=True)
class SenseCompilerPatch:
    """One verified, compile-only sense definition."""

    sense_id: str
    family: SenseFamily
    channel: SenseChannel
    explicit_precision: SensePrecision | None
    effective_precision: SensePrecision | None
    precision_basis: str
    range_feet: int
    grammar: str
    page_reference: int | None
    eligibility: tuple[str, ...]
    source: SenseSource
    provider_evidence: SenseProviderEvidence
    linked_companions: tuple[SenseCompanionSource, ...] = ()
    deferred_mechanics: tuple[str, ...] = (
        "observer-relative-detection",
    )

    def __post_init__(self) -> None:
        if type(self) is not SenseCompilerPatch:
            raise TypeError("SenseCompilerPatch subclasses are unsupported")
        _require_key(self.sense_id, "SenseCompilerPatch.sense_id")
        if (
            type(self.family) is not str
            or self.family not in _SENSE_FAMILIES
        ):
            raise ValueError("SenseCompilerPatch.family is invalid")
        if (
            type(self.channel) is not str
            or self.channel not in _SENSE_CHANNELS
        ):
            raise ValueError("SenseCompilerPatch.channel is invalid")
        for field_name in ("explicit_precision", "effective_precision"):
            value = getattr(self, field_name)
            if value is not None and (
                type(value) is not str or value not in _SENSE_PRECISIONS
            ):
                raise ValueError(
                    f"SenseCompilerPatch.{field_name} is invalid"
                )
        _require_key(
            self.precision_basis,
            "SenseCompilerPatch.precision_basis",
        )
        if (
            type(self.range_feet) is not int
            or not 1 <= self.range_feet <= MAX_SOURCE_INTEGER
        ):
            raise ValueError(
                "SenseCompilerPatch.range_feet must be a positive signed "
                "64-bit integer"
            )
        _require_key(self.grammar, "SenseCompilerPatch.grammar")
        if self.page_reference is not None and (
            type(self.page_reference) is not int
            or not 1 <= self.page_reference <= MAX_SOURCE_INTEGER
        ):
            raise ValueError(
                "SenseCompilerPatch.page_reference must be positive or None"
            )
        if (
            type(self.eligibility) is not tuple
            or not self.eligibility
            or len(self.eligibility) > _MAX_COLLECTION_ITEMS
        ):
            raise ValueError(
                "SenseCompilerPatch.eligibility must be a bounded non-empty "
                "tuple"
            )
        for item in self.eligibility:
            _require_key(item, "SenseCompilerPatch eligibility item")
        if type(self.source) is not SenseSource:
            raise TypeError(
                "SenseCompilerPatch.source must be an exact SenseSource"
            )
        SenseSource.__post_init__(self.source)
        if type(self.provider_evidence) is not SenseProviderEvidence:
            raise TypeError(
                "SenseCompilerPatch.provider_evidence must be exact "
                "SenseProviderEvidence"
            )
        self.source.carrier._require_shape(
            self.source.carrier.selection
        )
        if (
            type(self.linked_companions) is not tuple
            or len(self.linked_companions) > _MAX_COLLECTION_ITEMS
            or any(
                type(companion) is not SenseCompanionSource
                for companion in self.linked_companions
            )
        ):
            raise TypeError(
                "SenseCompilerPatch.linked_companions must be a bounded "
                "exact tuple"
            )
        for companion in self.linked_companions:
            SenseCompanionSource.__post_init__(companion)
        if (
            type(self.deferred_mechanics) is not tuple
            or not self.deferred_mechanics
            or len(self.deferred_mechanics) > _MAX_COLLECTION_ITEMS
        ):
            raise TypeError(
                "SenseCompilerPatch.deferred_mechanics must be a bounded "
                "non-empty tuple"
            )
        for item in self.deferred_mechanics:
            _require_key(item, "SenseCompilerPatch deferred mechanic")
        if len(set(self.deferred_mechanics)) != len(
            self.deferred_mechanics
        ):
            raise ValueError(
                "SenseCompilerPatch deferred mechanics must be unique"
            )
        self._validate_family_contract()
        self._validate_provider_contract()

    def _validate_provider_contract(self) -> None:
        if type(self.provider_evidence) is not SenseProviderEvidence:
            raise TypeError(
                "SenseCompilerPatch.provider_evidence must be exact "
                "SenseProviderEvidence"
            )
        if self.provider_evidence.family != self.family:
            raise ValueError(
                "SenseCompilerPatch provider evidence changed family"
            )
        if (
            self.provider_evidence.authority
            is not self.source.carrier.authority
        ):
            raise SenseSourceAuthorityError(
                "SenseCompilerPatch consumer and providers use different "
                "explicit adapters"
            )
        self.provider_evidence.validate_for(
            self.source.carrier.selection
        )

    def _validate_family_contract(self) -> None:
        family_channels: dict[SenseFamily, SenseChannel] = {
            "scent": "olfactory",
            "tremorsense": "surface-vibration",
            "lifesense": "vital-essence",
        }
        if self.channel != family_channels[self.family]:
            raise ValueError(
                "SenseCompilerPatch channel is incoherent with family"
            )
        if _normalized_sense_id(self.source.raw_sense) != self.sense_id:
            raise ValueError(
                "SenseCompilerPatch sense ID is incoherent with source"
            )
        ordinary_eligibility: dict[
            SenseFamily,
            tuple[str, ...],
        ] = {
            "scent": ("subject-emits-aroma",),
            "tremorsense": (
                "same-solid-surface",
                "subject-moving-or-burrowing",
            ),
            "lifesense": (
                "subject-vitality-signature-living-or-undead",
                "distinguishes-vitality-from-void",
            ),
        }
        defaults: dict[SenseFamily, SensePrecision] = {
            "scent": "vague",
            "tremorsense": "imprecise",
            "lifesense": "precise",
        }
        if self.grammar == f"{self.family}-range":
            source_match = _RANGED_SENSE_RE[self.family].fullmatch(
                self.source.raw_sense
            )
            source_range = (
                _positive_range(source_match)
                if source_match is not None
                else None
            )
            source_explicit = (
                source_match.group("precision")
                if source_match is not None
                else None
            )
            source_page = (
                359
                if source_match is not None
                and source_match.groupdict().get("page")
                else None
            )
            if (
                self.sense_id != self.family
                or self.range_feet != source_range
                or self.explicit_precision != source_explicit
                or self.page_reference != source_page
                or self.eligibility
                != ordinary_eligibility[self.family]
                or self.linked_companions
            ):
                raise ValueError(
                    "ordinary sense patch fields are family-incoherent"
                )
            if (
                self.family != "lifesense"
                and self.page_reference is not None
            ):
                raise ValueError(
                    "only lifesense can carry a page reference"
                )
            if self.explicit_precision is None:
                if (
                    self.effective_precision != defaults[self.family]
                    or self.precision_basis
                    != f"{self.family}-family-default"
                ):
                    raise ValueError(
                        "ordinary default precision is family-incoherent"
                    )
            elif (
                self.effective_precision != self.explicit_precision
                or self.precision_basis != "source-explicit"
            ):
                raise ValueError(
                    "explicit precision must remain source-explicit"
                )
            expected_deferred = ("observer-relative-detection",)
        elif self.grammar == "named-scent-companion":
            source_match = _SIN_SCENT_RE.fullmatch(self.source.raw_sense)
            source_range = (
                _positive_range(source_match)
                if source_match is not None
                else None
            )
            source_precision = (
                source_match.group("precision")
                if source_match is not None
                else None
            )
            if (
                self.sense_id != "sin-scent"
                or self.family != "scent"
                or self.range_feet != source_range
                or self.page_reference is not None
                or self.eligibility
                != ("subject-reflects-associated-sin",)
                or len(self.linked_companions) != 1
                or self.linked_companions[0].relation != "local"
                or self.explicit_precision != source_precision
                or self.explicit_precision is None
                or self.effective_precision != self.explicit_precision
                or self.precision_basis != "source-explicit"
            ):
                raise ValueError(
                    "named scent companion patch is incoherent"
                )
            companion = self.linked_companions[0]
            if (
                not _same_verified_carrier(
                    companion.carrier,
                    self.source.carrier,
                )
                or not _companion_is(
                    companion,
                    relation="local",
                    raw_key="!.Sin Scent",
                    description=_SIN_DESCRIPTION,
                    source_id=MONSTER_CORE_SOURCE_ID,
                    locator="310.1",
                    section_id="core-mc1:sinspawn",
                    creature_name="Sinspawn",
                    block_sha256=_SIN_BLOCK_SHA256,
                    definition_sha256=_SIN_DEFINITION_SHA256,
                )
            ):
                raise ValueError(
                    "named scent patch lacks its exact local companion"
                )
            expected_deferred = (
                "observer-relative-detection",
                "gm-adjudicated-associated-sin",
            )
        elif self.grammar == "blood-scent-companion":
            relations = tuple(
                companion.relation
                for companion in self.linked_companions
            )
            if (
                self.sense_id != "blood-scent"
                or self.family != "scent"
                or self.page_reference is not None
                or self.eligibility != ("subject-blood-in-water",)
                or relations not in (("local",), ("local", "inherited"))
                or self.explicit_precision is not None
                or self.effective_precision is not None
                or self.precision_basis != "companion-unresolved"
                or self.range_feet != 5280
            ):
                raise ValueError(
                    "blood scent companion patch is incoherent"
                )
            local = self.linked_companions[0]
            if not _same_verified_carrier(
                local.carrier,
                self.source.carrier,
            ):
                raise ValueError(
                    "blood scent patch local companion changed carrier"
                )
            if relations == ("local",):
                exact_companions = _companion_is(
                    local,
                    relation="local",
                    raw_key="!.Blood Scent",
                    description=_BLOOD_DESCRIPTION,
                    source_id=MONSTER_CORE_SOURCE_ID,
                    locator="307.2",
                    section_id="core-mc1:shark",
                    creature_name="Great White Shark",
                    block_sha256=_GREAT_WHITE_BLOCK_SHA256,
                    definition_sha256=_GREAT_WHITE_DEFINITION_SHA256,
                )
            else:
                inherited = self.linked_companions[1]
                exact_companions = (
                    _companion_is(
                        local,
                        relation="local",
                        raw_key="!.Blood Scent",
                        description=_BLOOD_INHERITANCE,
                        source_id=MONSTER_CORE_SOURCE_ID,
                        locator="307.4",
                        section_id="core-mc1:shark",
                        creature_name="Megalodon",
                        block_sha256=_MEGALODON_BLOCK_SHA256,
                        definition_sha256=_MEGALODON_DEFINITION_SHA256,
                    )
                    and _companion_is(
                        inherited,
                        relation="inherited",
                        raw_key="!.Blood Scent",
                        description=_BLOOD_DESCRIPTION,
                        source_id=MONSTER_CORE_SOURCE_ID,
                        locator="307.2",
                        section_id="core-mc1:shark",
                        creature_name="Great White Shark",
                        block_sha256=_GREAT_WHITE_BLOCK_SHA256,
                        definition_sha256=_GREAT_WHITE_DEFINITION_SHA256,
                    )
                )
            if not exact_companions:
                raise ValueError(
                    "blood scent patch lacks exact companion provenance"
                )
            expected_deferred = (
                "observer-relative-detection",
                "blood-scent-precision",
            )
        else:
            raise ValueError(
                "SenseCompilerPatch grammar is not coherent with family"
            )
        if self.provider_blockers:
            expected_deferred = (
                *expected_deferred,
                "source-provider-resolution",
            )
        if self.deferred_mechanics != expected_deferred:
            raise ValueError(
                "SenseCompilerPatch deferred mechanics are incoherent"
            )
        if self.effective_precision is not None:
            expected = _precision_requirement(
                self.effective_precision
            )
            if (
                self.precision_rule is None
                and not self.provider_is_blocked(expected.rule_id)
            ):
                raise ValueError(
                    "resolved precision lacks provider evidence or blocker"
                )

    def provider(self, rule_id: str) -> VerifiedRuleReceipt | None:
        return next(
            (
                rule
                for rule in self.provider_evidence.rules
                if rule.rule_id == rule_id
            ),
            None,
        )

    def provider_is_blocked(self, rule_id: str) -> bool:
        return any(
            blocker.rule_id == rule_id
            for blocker in self.provider_evidence.blockers
        )

    @property
    def provider_rules(self) -> tuple[VerifiedRuleReceipt, ...]:
        return self.provider_evidence.rules

    @property
    def provider_blockers(self) -> tuple[SenseProviderBlocker, ...]:
        return self.provider_evidence.blockers

    @property
    def family_rule(self) -> VerifiedRuleReceipt | None:
        requirement = {
            "scent": _REVIEWED_FOUNDATIONAL_RULES[4],
            "tremorsense": _REVIEWED_FOUNDATIONAL_RULES[5],
            "lifesense": None,
        }[self.family]
        return (
            None
            if requirement is None
            else self.provider(requirement.rule_id)
        )

    @property
    def precision_rule(self) -> VerifiedRuleReceipt | None:
        return (
            None
            if self.effective_precision is None
            else self.provider(
                _precision_requirement(
                    self.effective_precision
                ).rule_id
            )
        )

    @property
    def glossary(self) -> VerifiedRuleReceipt | None:
        return self.provider(
            _glossary_requirement(self.family).rule_id
        )

    @property
    def foundational_rules(self) -> tuple[VerifiedRuleReceipt, ...]:
        foundational_ids = {
            requirement.rule_id
            for requirement in _REVIEWED_FOUNDATIONAL_RULES
        }
        return tuple(
            rule
            for rule in self.provider_rules
            if rule.rule_id in foundational_ids
        )

    def as_serialized(self) -> dict[str, Any]:
        SenseCompilerPatch.__post_init__(self)
        providers = [
            _verified_rule_serialized(rule)
            for rule in self.provider_rules
        ]
        provider_by_id = {
            rule.rule_id: serialized
            for rule, serialized in zip(
                self.provider_rules,
                providers,
                strict=True,
            )
        }
        precision_rule = self.precision_rule
        family_rule = self.family_rule
        glossary = self.glossary
        precision = {
            "explicit": self.explicit_precision,
            "effective": self.effective_precision,
            "basis": self.precision_basis,
            "rule": (
                provider_by_id[precision_rule.rule_id]
                if precision_rule is not None
                else None
            ),
        }
        return {
            "senseId": self.sense_id,
            "family": self.family,
            "channel": self.channel,
            "precision": precision,
            "range": {
                "feet": self.range_feet,
                "boundary": "inclusive",
            },
            "grammar": self.grammar,
            "pageReference": self.page_reference,
            "eligibility": list(self.eligibility),
            "source": self.source.as_serialized(),
            "rules": {
                "family": (
                    provider_by_id[family_rule.rule_id]
                    if family_rule is not None
                    else None
                ),
                "glossary": (
                    provider_by_id[glossary.rule_id]
                    if glossary is not None
                    else None
                ),
                "providers": providers,
                "blockers": [
                    blocker.as_serialized()
                    for blocker in self.provider_blockers
                ],
            },
            "linkedCompanions": [
                companion.as_serialized()
                for companion in self.linked_companions
            ],
            "compilerReady": not self.provider_blockers,
            "runtimeReady": False,
            "activation": "compile-only",
            "deferredMechanics": list(self.deferred_mechanics),
        }


class SenseCompiler(Protocol):
    def __call__(
        self,
        source: SenseSource,
        /,
    ) -> SenseCompilerPatch | None: ...


@final
@dataclass(frozen=True, slots=True)
class SenseCompilerRegistration:
    """One ordered, fail-closed source-field compiler registration."""

    compiler_id: str
    family: SenseFamily
    compiler: SenseCompiler

    def __post_init__(self) -> None:
        if type(self) is not SenseCompilerRegistration:
            raise TypeError(
                "SenseCompilerRegistration subclasses are unsupported"
            )
        _require_key(
            self.compiler_id,
            "SenseCompilerRegistration.compiler_id",
        )
        if type(self.family) is not str:
            raise TypeError(
                "SenseCompilerRegistration.family must be a string"
            )
        if self.family not in _SENSE_FAMILIES:
            raise ValueError("SenseCompilerRegistration.family is invalid")
        if not callable(self.compiler):
            raise TypeError(
                "SenseCompilerRegistration.compiler must be callable"
            )

    def match(
        self,
        source: SenseSource,
        /,
    ) -> SenseCompilerPatch | None:
        SenseCompilerRegistration.__post_init__(self)
        if type(source) is not SenseSource:
            return None
        patch = self.compiler(source)
        if patch is None:
            return None
        if type(patch) is not SenseCompilerPatch:
            raise TypeError(
                f"sense compiler {self.compiler_id!r} returned "
                f"{type(patch).__name__}, not SenseCompilerPatch or None"
            )
        SenseCompilerPatch.__post_init__(patch)
        if patch.family != self.family:
            raise ValueError(
                f"sense compiler {self.compiler_id!r} returned family "
                f"{patch.family!r}, expected {self.family!r}"
            )
        if patch.source is not source:
            raise ValueError(
                f"sense compiler {self.compiler_id!r} changed its exact "
                "source identity"
            )
        return patch


@final
@dataclass(frozen=True, slots=True)
class SenseFamilyFragment:
    """Local, unregistered fragment proposed for source-field compilers."""

    family_id: str
    sense_compilers: tuple[SenseCompilerRegistration, ...]

    def __post_init__(self) -> None:
        if type(self) is not SenseFamilyFragment:
            raise TypeError("SenseFamilyFragment subclasses are unsupported")
        _require_key(self.family_id, "SenseFamilyFragment.family_id")
        if type(self.sense_compilers) is not tuple:
            raise TypeError(
                "SenseFamilyFragment.sense_compilers must be a tuple"
            )
        if not self.sense_compilers:
            raise ValueError(
                "SenseFamilyFragment requires at least one compiler"
            )
        compiler_ids: set[str] = set()
        families: set[str] = set()
        for registration in self.sense_compilers:
            if type(registration) is not SenseCompilerRegistration:
                raise TypeError(
                    "SenseFamilyFragment.sense_compilers must contain only "
                    "SenseCompilerRegistration values"
                )
            if registration.compiler_id in compiler_ids:
                raise ValueError(
                    "SenseFamilyFragment has duplicate compiler id "
                    f"{registration.compiler_id!r}"
                )
            if registration.family in families:
                raise ValueError(
                    "SenseFamilyFragment has duplicate family "
                    f"{registration.family!r}"
                )
            compiler_ids.add(registration.compiler_id)
            families.add(registration.family)


class SenseCompilerAmbiguityError(ValueError):
    """More than one ordered source-field compiler accepted one sense."""


class SenseCompanionAmbiguityError(ValueError):
    """More than one exact companion occupied a required relation."""


def match_sense_compilers(
    source: SenseSource,
    registrations: list[SenseCompilerRegistration]
    | tuple[SenseCompilerRegistration, ...],
    /,
) -> SenseCompilerPatch | None:
    """Return the sole match while preserving zero/one/many semantics."""

    if type(registrations) not in (list, tuple):
        raise TypeError(
            "sense compiler registrations must be an ordered list or tuple"
        )
    matches: list[tuple[str, SenseCompilerPatch]] = []
    for registration in registrations:
        if type(registration) is not SenseCompilerRegistration:
            raise TypeError(
                "sense compiler registrations must contain only "
                "SenseCompilerRegistration values"
            )
        patch = registration.match(source)
        if patch is not None:
            matches.append((registration.compiler_id, patch))
    if len(matches) > 1:
        compiler_ids = ", ".join(repr(item[0]) for item in matches)
        raise SenseCompilerAmbiguityError(
            "multiple sense compilers matched in registration order: "
            f"{compiler_ids}"
        )
    return matches[0][1] if matches else None


def compile_sense_collection(
    source: SenseSource,
    registrations: list[SenseCompilerRegistration]
    | tuple[SenseCompilerRegistration, ...],
    /,
) -> tuple[SenseCompilerPatch, ...]:
    """Compile every token in one validated Perception carrier in order."""

    if type(source) is not SenseSource:
        raise TypeError("source must be a SenseSource")
    SenseSource.__post_init__(source)
    source.carrier.validated_selection()
    patches: list[SenseCompilerPatch] = []
    for sense_index in range(len(source.raw_senses)):
        selected = SenseSource(
            carrier=source.carrier,
            sense_index=sense_index,
            companions=source.companions,
        )
        patch = match_sense_compilers(selected, registrations)
        if patch is not None:
            patches.append(patch)
    sense_ids = [patch.sense_id for patch in patches]
    duplicates = sorted(
        {
            sense_id
            for sense_id in sense_ids
            if sense_ids.count(sense_id) > 1
        }
    )
    if duplicates:
        raise SenseSourceAmbiguityError(
            "compiled collection has duplicate sense IDs: "
            + ", ".join(repr(item) for item in duplicates)
        )
    return tuple(patches)


def _source_field_matches(source: object) -> bool:
    if type(source) is not SenseSource:
        return False
    SenseSource.__post_init__(source)
    for companion in source.companions:
        SenseCompanionSource.__post_init__(companion)
    source.carrier.validated_selection()
    return (
        source.source_id == MONSTER_CORE_SOURCE_ID
        and source.field_name == PERCEPTION_FIELD
        and source.raw_member.key == PERCEPTION_FIELD
        and source.raw_member_occurrence == 0
        and source.matching_field_member_count == 1
    )


def _positive_range(match: re.Match[str]) -> int | None:
    range_feet = parse_decimal_integer(match.group("range"))
    if range_feet is None or range_feet <= 0:
        return None
    return range_feet


def _precision_requirement(
    precision: SensePrecision,
) -> RuleRequirement:
    return {
        "precise": _REVIEWED_FOUNDATIONAL_RULES[0],
        "imprecise": _REVIEWED_FOUNDATIONAL_RULES[1],
        "vague": _REVIEWED_FOUNDATIONAL_RULES[2],
    }[precision]


def _glossary_requirement(
    family: SenseFamily,
) -> RuleRequirement:
    return {
        "scent": _REVIEWED_GLOSSARY_RULES[0],
        "tremorsense": _REVIEWED_GLOSSARY_RULES[1],
        "lifesense": _REVIEWED_GLOSSARY_RULES[2],
    }[family]


def _expected_provider_requirements(
    family: SenseFamily,
) -> tuple[RuleRequirement, ...]:
    return (
        *_REVIEWED_FOUNDATIONAL_RULES,
        _glossary_requirement(family),
    )


def _verified_rule_matches_requirement(
    rule: VerifiedRuleReceipt,
    requirement: RuleRequirement,
    authority: SourceAuthorityAdapter | None = None,
) -> bool:
    if type(rule) is not VerifiedRuleReceipt or type(
        requirement
    ) is not RuleRequirement:
        return False
    try:
        selection = rule.selection
        receipt = rule.receipt
        retained_requirement = rule.requirement
    except AttributeError:
        return False
    if (
        type(selection) is not VerifiedSourceSelection
        or type(receipt) is not SourceReceipt
        or type(retained_requirement) is not RuleRequirement
    ):
        return False
    try:
        if authority is None:
            rule.as_serialized()
        elif type(authority) is SourceAuthorityAdapter:
            authority.validate_rule(rule)
        else:
            return False
        address = selection.address
        raw_member = selection.raw_member
        replayed_member_sha256 = (
            raw_member_sha256(raw_member)
            if type(raw_member) is RawSourceMember
            else None
        )
        replayed = (
            raw_source_sha256(selection.carrier.raw_block),
            replayed_member_sha256,
            raw_source_sha256(selection.raw_value),
            raw_source_sha256(selection.selected_value),
        )
        actual = (
            selection.block_sha256,
            selection.member_sha256,
            selection.value_sha256,
            selection.selection_sha256,
        )
        receipt.as_serialized()
        selection_receipt = selection.receipt
    except (
        AttributeError,
        SourceAuthorityError,
        TypeError,
        ValueError,
    ):
        return False
    if type(address) is not SourceAddress or replayed != actual:
        return False
    expected_pairs = (
        (requirement.expected_block_sha256, selection.block_sha256),
        (requirement.expected_member_sha256, selection.member_sha256),
        (requirement.expected_value_sha256, selection.value_sha256),
        (
            requirement.expected_selection_sha256,
            selection.selection_sha256,
        ),
    )
    return (
        rule.rule_id == requirement.rule_id
        and retained_requirement == requirement
        and receipt == selection_receipt
        and address.source_id == requirement.source_id
        and address.locator == requirement.locator
        and address.carrier_path == requirement.carrier_path
        and address.selection_path == requirement.selection_path
        and address.span == requirement.span
        and all(
            expected is None or expected == actual
            for expected, actual in expected_pairs
        )
    )


def _validate_provider_evidence(
    authority: SourceAuthorityAdapter,
    family: SenseFamily,
    rules: tuple[VerifiedRuleReceipt, ...],
    blockers: tuple[SenseProviderBlocker, ...],
    *,
    resolve_authority: bool,
) -> None:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "provider evidence authority must be exact "
            "SourceAuthorityAdapter"
        )
    if type(family) is not str or family not in _SENSE_FAMILIES:
        raise ValueError("provider evidence family is invalid")
    if type(rules) is not tuple or any(
        type(rule) is not VerifiedRuleReceipt
        for rule in rules
    ):
        raise TypeError(
            "provider evidence rules must be an exact tuple of "
            "VerifiedRuleReceipt values"
        )
    if type(blockers) is not tuple or any(
        type(blocker) is not SenseProviderBlocker
        for blocker in blockers
    ):
        raise TypeError(
            "provider evidence blockers must be an exact tuple of "
            "SenseProviderBlocker values"
        )
    expected = _expected_provider_requirements(family)
    expected_ids = tuple(item.rule_id for item in expected)
    try:
        rule_ids = tuple(item.rule_id for item in rules)
        blocker_ids = tuple(item.rule_id for item in blockers)
    except AttributeError as failure:
        raise SenseSourceAuthorityError(
            "provider evidence is incomplete"
        ) from failure
    if (
        len(rule_ids) != len(set(rule_ids))
        or len(blocker_ids) != len(set(blocker_ids))
        or set(rule_ids) & set(blocker_ids)
        or set(rule_ids) | set(blocker_ids) != set(expected_ids)
        or rule_ids
        != tuple(item for item in expected_ids if item in set(rule_ids))
        or blocker_ids
        != tuple(item for item in expected_ids if item in set(blocker_ids))
    ):
        raise ValueError(
            "provider evidence does not partition ordered requirements"
        )
    requirements = {item.rule_id: item for item in expected}
    for rule in rules:
        if not _verified_rule_matches_requirement(
            rule,
            requirements[rule.rule_id],
            authority,
        ):
            raise SenseSourceAuthorityError(
                "provider receipt disagrees with reviewed requirement"
            )
    for blocker in blockers:
        requirement = requirements[blocker.rule_id]
        try:
            replayed_blocker = SenseProviderBlocker(
                rule_id=blocker.rule_id,
                source_id=blocker.source_id,
                locator=blocker.locator,
                reason=blocker.reason,
            )
        except (AttributeError, TypeError, ValueError) as failure:
            raise SenseSourceAuthorityError(
                "provider blocker is structurally invalid"
            ) from failure
        if (
            replayed_blocker != blocker
            or type(blocker) is not SenseProviderBlocker
            or blocker.source_id != requirement.source_id
            or blocker.locator != requirement.locator
        ):
            raise ValueError(
                "provider blocker changed its reviewed requirement"
            )
    if resolve_authority:
        try:
            if rules:
                authority.require_shared_authority(
                    rules[0].selection,
                    rules,
                )
            else:
                authority.snapshot
        except (SourceAuthorityError, TypeError, AttributeError) as failure:
            raise SenseSourceAuthorityError(
                "provider receipts failed explicit authority re-resolution"
            ) from failure
    for blocker in blockers:
        requirement = requirements[blocker.rule_id]
        try:
            authority.resolve_rule(requirement)
        except SourceAuthorityError as failure:
            if _provider_blocker(requirement, failure) != blocker:
                raise SenseSourceAuthorityError(
                    "provider blocker disagrees with authority "
                    "re-resolution"
                ) from failure
        else:
            raise SenseSourceAuthorityError(
                "provider blocker claims an available provider"
            )


def _verified_rule_serialized(
    rule: VerifiedRuleReceipt,
) -> dict[str, Any]:
    """Serialize provider evidence already authenticated by patch linkage."""

    if type(rule) is not VerifiedRuleReceipt:
        raise TypeError(
            "provider serialization requires VerifiedRuleReceipt"
        )
    if (
        type(rule.requirement) is not RuleRequirement
        or type(rule.receipt) is not SourceReceipt
        or type(rule.selection) is not VerifiedSourceSelection
        or rule.receipt != rule.selection.receipt
    ):
        raise SenseSourceAuthorityError(
            "provider serialization evidence is incoherent"
        )
    return {
        "ruleId": rule.rule_id,
        "requirement": rule.requirement.as_serialized(),
        "source": rule.receipt.as_serialized(),
    }


def _provider_blocker(
    requirement: RuleRequirement,
    failure: SourceAuthorityError,
) -> SenseProviderBlocker:
    if type(failure) is SourceReviewError:
        reason: ProviderBlockerReason = "reviewed-hash-mismatch"
    elif type(failure) is SourceAddressError:
        reason = (
            "source-not-selected"
            if "not selected" in str(failure)
            else "source-address-unresolved"
        )
    else:
        reason = "authority-rejected"
    return SenseProviderBlocker(
        rule_id=requirement.rule_id,
        source_id=requirement.source_id,
        locator=requirement.locator,
        reason=reason,
    )


@lru_cache(maxsize=32)
def _provider_evidence_for_authority(
    authority: SourceAuthorityAdapter,
    family: SenseFamily,
) -> SenseProviderEvidence:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "provider evidence requires exact SourceAuthorityAdapter"
        )
    rules: list[VerifiedRuleReceipt] = []
    blockers: list[SenseProviderBlocker] = []
    for requirement in _expected_provider_requirements(family):
        try:
            rule = authority.resolve_rule(requirement)
        except SourceAuthorityError as failure:
            blockers.append(_provider_blocker(requirement, failure))
            continue
        if (
            type(rule) is not VerifiedRuleReceipt
            or not _verified_rule_matches_requirement(rule, requirement)
        ):
            raise SenseSourceAuthorityError(
                "selected-source authority issued malformed provider evidence"
            )
        rules.append(rule)
    return SenseProviderEvidence(
        authority=authority,
        family=family,
        rules=tuple(rules),
        blockers=tuple(blockers),
    )


def _resolve_provider_evidence(
    source: SenseSource,
    family: SenseFamily,
) -> SenseProviderEvidence:
    authority = source.carrier.authority
    return _provider_evidence_for_authority(authority, family)


def _provider_deferred(
    blockers: tuple[SenseProviderBlocker, ...],
) -> tuple[str, ...]:
    return ("source-provider-resolution",) if blockers else ()


def _same_verified_carrier(
    left: SenseCreatureCarrier,
    right: SenseCreatureCarrier,
) -> bool:
    if (
        type(left) is not SenseCreatureCarrier
        or type(right) is not SenseCreatureCarrier
        or left.authority is not right.authority
    ):
        return False
    left_selection = left.selection
    right_selection = right.selection
    left._require_shape(left_selection)
    right._require_shape(right_selection)
    left_address = left_selection.address
    right_address = right_selection.address
    return (
        left_address.source_id == right_address.source_id
        and left_address.locator == right_address.locator
        and left_address.section_id == right_address.section_id
        and left_address.target_path == right_address.target_path
        and left_address.carrier_path == right_address.carrier_path
        and left_selection.block_sha256 == right_selection.block_sha256
    )


def _exact_companions(
    source: SenseSource,
    *,
    raw_key: str,
    relation: CompanionRelation,
) -> tuple[SenseCompanionSource, ...]:
    return tuple(
        companion
        for companion in source.companions
        if companion.raw_member.key == raw_key
        and companion.relation == relation
    )


def _sole_exact_companion(
    source: SenseSource,
    *,
    raw_key: str,
    relation: CompanionRelation,
) -> SenseCompanionSource | None:
    matches = _exact_companions(
        source,
        raw_key=raw_key,
        relation=relation,
    )
    if len(matches) > 1:
        raise SenseCompanionAmbiguityError(
            f"multiple {relation} {raw_key!r} companions were supplied"
        )
    return matches[0] if matches else None


def _companion_is(
    companion: SenseCompanionSource,
    *,
    relation: CompanionRelation,
    raw_key: str,
    description: str,
    source_id: str,
    locator: str,
    section_id: str,
    creature_name: str,
    block_sha256: str,
    definition_sha256: str,
) -> bool:
    return (
        companion.relation == relation
        and companion.raw_member.key == raw_key
        and companion.description == description
        and companion.source_id == source_id
        and companion.locator == locator
        and companion.section_id == section_id
        and companion.creature_name == creature_name
        and companion.block_sha256 == block_sha256
        and companion.definition_sha256 == definition_sha256
        and companion.raw_member_occurrence == 0
    )


def _ordinary_patch(
    source: SenseSource,
    *,
    family: SenseFamily,
    channel: SenseChannel,
    default_precision: SensePrecision,
    eligibility: tuple[str, ...],
) -> SenseCompilerPatch | None:
    match = _RANGED_SENSE_RE[family].fullmatch(source.raw_sense)
    if match is None:
        return None
    range_feet = _positive_range(match)
    if range_feet is None:
        return None
    explicit = match.group("precision")
    effective: SensePrecision = explicit or default_precision
    page_reference = 359 if match.groupdict().get("page") else None
    provider_evidence = _resolve_provider_evidence(
        source,
        family,
    )
    deferred_mechanics = (
        "observer-relative-detection",
        *_provider_deferred(provider_evidence.blockers),
    )
    return SenseCompilerPatch(
        sense_id=family,
        family=family,
        channel=channel,
        explicit_precision=explicit,
        effective_precision=effective,
        precision_basis=(
            "source-explicit"
            if explicit is not None
            else f"{family}-family-default"
        ),
        range_feet=range_feet,
        grammar=f"{family}-range",
        page_reference=page_reference,
        eligibility=eligibility,
        source=source,
        provider_evidence=provider_evidence,
        deferred_mechanics=deferred_mechanics,
    )


def _compile_sin_scent(
    source: SenseSource,
) -> SenseCompilerPatch | None:
    match = _SIN_SCENT_RE.fullmatch(source.raw_sense)
    if match is None:
        return None
    range_feet = _positive_range(match)
    if range_feet is None:
        return None
    companion = _sole_exact_companion(
        source,
        raw_key="!.Sin Scent",
        relation="local",
    )
    if companion is None or not _companion_is(
        companion,
        relation="local",
        raw_key="!.Sin Scent",
        description=_SIN_DESCRIPTION,
        source_id=MONSTER_CORE_SOURCE_ID,
        locator="310.1",
        section_id="core-mc1:sinspawn",
        creature_name="Sinspawn",
        block_sha256=_SIN_BLOCK_SHA256,
        definition_sha256=_SIN_DEFINITION_SHA256,
    ):
        return None
    if (
        not _same_verified_carrier(source.carrier, companion.carrier)
    ):
        return None
    precision: SensePrecision = match.group("precision")
    provider_evidence = _resolve_provider_evidence(
        source,
        "scent",
    )
    return SenseCompilerPatch(
        sense_id="sin-scent",
        family="scent",
        channel="olfactory",
        explicit_precision=precision,
        effective_precision=precision,
        precision_basis="source-explicit",
        range_feet=range_feet,
        grammar="named-scent-companion",
        page_reference=None,
        eligibility=("subject-reflects-associated-sin",),
        source=source,
        provider_evidence=provider_evidence,
        linked_companions=(companion,),
        deferred_mechanics=(
            "observer-relative-detection",
            "gm-adjudicated-associated-sin",
            *_provider_deferred(provider_evidence.blockers),
        ),
    )


def _compile_blood_scent(
    source: SenseSource,
) -> SenseCompilerPatch | None:
    if source.raw_sense != "blood scent":
        return None
    local = _sole_exact_companion(
        source,
        raw_key="!.Blood Scent",
        relation="local",
    )
    if local is None:
        return None

    linked: tuple[SenseCompanionSource, ...]
    if _companion_is(
        local,
        relation="local",
        raw_key="!.Blood Scent",
        description=_BLOOD_DESCRIPTION,
        source_id=MONSTER_CORE_SOURCE_ID,
        locator="307.2",
        section_id="core-mc1:shark",
        creature_name="Great White Shark",
        block_sha256=_GREAT_WHITE_BLOCK_SHA256,
        definition_sha256=_GREAT_WHITE_DEFINITION_SHA256,
    ):
        if (
            not _same_verified_carrier(source.carrier, local.carrier)
        ):
            return None
        linked = (local,)
    elif _companion_is(
        local,
        relation="local",
        raw_key="!.Blood Scent",
        description=_BLOOD_INHERITANCE,
        source_id=MONSTER_CORE_SOURCE_ID,
        locator="307.4",
        section_id="core-mc1:shark",
        creature_name="Megalodon",
        block_sha256=_MEGALODON_BLOCK_SHA256,
        definition_sha256=_MEGALODON_DEFINITION_SHA256,
    ):
        if (
            not _same_verified_carrier(source.carrier, local.carrier)
        ):
            return None
        inherited = _sole_exact_companion(
            source,
            raw_key="!.Blood Scent",
            relation="inherited",
        )
        if inherited is None or not _companion_is(
            inherited,
            relation="inherited",
            raw_key="!.Blood Scent",
            description=_BLOOD_DESCRIPTION,
            source_id=MONSTER_CORE_SOURCE_ID,
            locator="307.2",
            section_id="core-mc1:shark",
            creature_name="Great White Shark",
            block_sha256=_GREAT_WHITE_BLOCK_SHA256,
            definition_sha256=_GREAT_WHITE_DEFINITION_SHA256,
        ):
            return None
        linked = (local, inherited)
    else:
        return None

    provider_evidence = _resolve_provider_evidence(
        source,
        "scent",
    )
    return SenseCompilerPatch(
        sense_id="blood-scent",
        family="scent",
        channel="olfactory",
        explicit_precision=None,
        effective_precision=None,
        precision_basis="companion-unresolved",
        range_feet=5280,
        grammar="blood-scent-companion",
        page_reference=None,
        eligibility=("subject-blood-in-water",),
        source=source,
        provider_evidence=provider_evidence,
        linked_companions=linked,
        deferred_mechanics=(
            "observer-relative-detection",
            "blood-scent-precision",
            *_provider_deferred(provider_evidence.blockers),
        ),
    )


def compile_scent(
    source: SenseSource,
    /,
) -> SenseCompilerPatch | None:
    """Compile ordinary Scent or one of two exact linked source variants."""

    if not _source_field_matches(source):
        return None
    ordinary = _ordinary_patch(
        source,
        family="scent",
        channel="olfactory",
        default_precision="vague",
        eligibility=("subject-emits-aroma",),
    )
    if ordinary is not None:
        return ordinary
    sin_scent = _compile_sin_scent(source)
    if sin_scent is not None:
        return sin_scent
    return _compile_blood_scent(source)


def compile_tremorsense(
    source: SenseSource,
    /,
) -> SenseCompilerPatch | None:
    """Compile the exact ordinary Tremorsense source-field grammar."""

    if not _source_field_matches(source):
        return None
    return _ordinary_patch(
        source,
        family="tremorsense",
        channel="surface-vibration",
        default_precision="imprecise",
        eligibility=(
            "same-solid-surface",
            "subject-moving-or-burrowing",
        ),
    )


def compile_lifesense(
    source: SenseSource,
    /,
) -> SenseCompilerPatch | None:
    """Compile Lifesense with its reviewed family-local precise default."""

    if not _source_field_matches(source):
        return None
    return _ordinary_patch(
        source,
        family="lifesense",
        channel="vital-essence",
        default_precision="precise",
        eligibility=(
            "subject-vitality-signature-living-or-undead",
            "distinguishes-vitality-from-void",
        ),
    )


FRAGMENT = SenseFamilyFragment(
    family_id="special-senses",
    sense_compilers=(
        SenseCompilerRegistration(
            compiler_id="scent",
            family="scent",
            compiler=compile_scent,
        ),
        SenseCompilerRegistration(
            compiler_id="tremorsense",
            family="tremorsense",
            compiler=compile_tremorsense,
        ),
        SenseCompilerRegistration(
            compiler_id="lifesense",
            family="lifesense",
            compiler=compile_lifesense,
        ),
    ),
)


__all__ = [
    "FOUNDATIONAL_RULES",
    "FRAGMENT",
    "GLOSSARY_RULES",
    "LIFESENSE_GLOSSARY",
    "MIGRATION_NOTES",
    "PROVIDER_BLOCKER_REASONS",
    "SCENT_GLOSSARY",
    "SenseCompanionAmbiguityError",
    "SenseCompanionSource",
    "SenseCreatureCarrier",
    "SenseCompilerAmbiguityError",
    "SenseCompilerPatch",
    "SenseCompilerRegistration",
    "SenseFamilyFragment",
    "SenseProviderBlocker",
    "SenseProviderEvidence",
    "SenseSource",
    "SenseSourceAmbiguityError",
    "SenseSourceAuthorityError",
    "TREMORSENSE_GLOSSARY",
    "compile_sense_collection",
    "compile_lifesense",
    "compile_scent",
    "compile_tremorsense",
    "match_sense_compilers",
]

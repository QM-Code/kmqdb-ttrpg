"""Compile exact Monster Core vision tokens from verified Perception fields.

Darkvision, greater darkvision, and low-light vision are authored inside a
creature's raw ``Perception`` member.  This module keeps that source shape
intact and accepts only selections re-resolved by the server-owned
``SourceAuthorityAdapter``.  The four reviewed glossary/rule providers must
come from the same authority context and in one exact order.

The encounter illumination consumer executes these profiles directly. It
still mounts no registry fragment because a visual sense is passive state,
not an action mechanic. Effect-created obscurers other than the admitted
Darkness profile, and a mixed-light-level footprint ruling, remain deferred.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from types import MappingProxyType
from typing import Any, Callable, final

from ...source_content import (
    MAX_RAW_BYTES,
    MAX_RAW_DEPTH,
    MAX_RAW_NODES,
)
from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
)
from .source_authority import (
    AUTHORITY_RULESET,
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
)


VISION_SENSE_FAMILY_ID = "vision-senses"
VISION_SENSE_MECHANIC_TYPE = "vision-sense-profile"
PERCEPTION_FIELD_NAME = "Perception"
MONSTER_CORE_SOURCE_ID = "core-mc1"

# Family input limits.  The authority layer has broader payload limits; these
# keep this small grammar bounded well above every reviewed Core MC1 value.
MAX_CREATURE_MEMBERS = 1_024
MAX_PERCEPTION_SOURCE_BYTES = 65_536
MAX_PERCEPTION_TOKENS = 256
MAX_SENSE_TOKEN_BYTES = 8_192
MAX_SIGNED_64 = (1 << 63) - 1

DARKVISION_GLOSSARY_REQUIREMENT = RuleRequirement(
    rule_id="darkvision-monster-glossary",
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
    carrier_path=(RawMemberStep("^.ability", 11),),
    expected_block_sha256=(
        "5360333cdf2a8ab0811a78b3c14410e17673fcd408786a482212751e5c09adf5"
    ),
)
DARKVISION_PLAYER_REQUIREMENT = RuleRequirement(
    rule_id="darkvision-and-greater-darkvision",
    source_id="core-pc1",
    locator="433.5",
    expected_block_sha256=(
        "8e30872b227aa9ed75888109e6cb02c189089b2963444d02525c9611c4636719"
    ),
)
LOW_LIGHT_GLOSSARY_REQUIREMENT = RuleRequirement(
    rule_id="low-light-vision-monster-glossary",
    source_id=MONSTER_CORE_SOURCE_ID,
    locator="358.2",
    carrier_path=(RawMemberStep("^.ability", 23),),
    expected_block_sha256=(
        "f31b4b795aa2151d74b304ccf350f6bdfad03b4354515d6ee6a2047501ca1315"
    ),
)
LOW_LIGHT_PLAYER_REQUIREMENT = RuleRequirement(
    rule_id="low-light-vision",
    source_id="core-pc1",
    locator="433.7",
    expected_block_sha256=(
        "0adb5ced9ea1c9320b0a39d9ba886fc06e92ff48e0b75fb4eff1b3b2521330ac"
    ),
)

RULE_REQUIREMENTS = (
    DARKVISION_GLOSSARY_REQUIREMENT,
    DARKVISION_PLAYER_REQUIREMENT,
    LOW_LIGHT_GLOSSARY_REQUIREMENT,
    LOW_LIGHT_PLAYER_REQUIREMENT,
)


class VisionSenseCompileError(ValueError):
    """A family-shaped source value is malformed or contradictory."""


class VisionSenseSourceAmbiguityError(VisionSenseCompileError):
    """One Perception member has multiple incompatible vision grants."""


class VisionSenseAddressabilityError(VisionSenseCompileError):
    """Verified evidence differs from this family's reviewed contract."""


@final
@dataclass(frozen=True, slots=True, init=False, eq=False)
class VisionSenseCompilerPatch:
    """Opaque compile-only result backed by one retained authority context.

    Public projections are reconstructed on every access.  The source and
    provider objects returned by properties are fresh authority resolutions,
    so mutating a projection cannot alter this patch or another patch.
    """

    _authority: SourceAuthorityAdapter
    _source: VerifiedSourceSelection
    _providers: tuple[VerifiedRuleReceipt, ...]
    _project: Callable[[object, str], object]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "VisionSenseCompilerPatch can only be constructed by the "
            "verified vision compiler"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("VisionSenseCompilerPatch subclasses are not supported")

    @property
    def source(self) -> VerifiedSourceSelection:
        return self._project(self, "source")  # type: ignore[return-value]

    @property
    def source_receipt(self) -> SourceReceipt:
        return self._project(  # type: ignore[return-value]
            self,
            "source-receipt",
        )

    @property
    def providers(self) -> tuple[VerifiedRuleReceipt, ...]:
        return self._project(self, "providers")  # type: ignore[return-value]

    @property
    def rules(self) -> tuple[VerifiedRuleReceipt, ...]:
        """Fresh provider projections retained for inspection."""

        return self.providers

    @property
    def sense_index(self) -> int:
        return self._project(self, "sense-index")  # type: ignore[return-value]

    @property
    def source_text(self) -> str:
        return self._project(self, "source-text")  # type: ignore[return-value]

    @property
    def modifier_source_text(self) -> str:
        return self._project(  # type: ignore[return-value]
            self,
            "modifier-source-text",
        )

    @property
    def sense_tokens(self) -> tuple[str, ...]:
        return self._project(self, "sense-tokens")  # type: ignore[return-value]

    @property
    def mechanic(self) -> MappingProxyType:
        return self._project(self, "mechanic")  # type: ignore[return-value]

    @property
    def mechanic_type(self) -> str:
        return self._project(self, "mechanic-type")  # type: ignore[return-value]

    @property
    def deferred_mechanics(self) -> tuple[str, ...]:
        return self._project(  # type: ignore[return-value]
            self,
            "deferred-mechanics",
        )

    @property
    def runtime_ready(self) -> bool:
        return True

    def as_serialized(self) -> dict[str, Any]:
        return self._project(self, "serialized")  # type: ignore[return-value]

    def __copy__(self) -> VisionSenseCompilerPatch:
        raise TypeError("VisionSenseCompilerPatch cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> VisionSenseCompilerPatch:
        raise TypeError("VisionSenseCompilerPatch cannot be deep-copied")

    def __reduce__(self) -> object:
        raise TypeError("VisionSenseCompilerPatch cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("VisionSenseCompilerPatch cannot be pickled")


def _clone_path(
    path: tuple[RawMemberStep | RawIndexStep, ...],
    *,
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
) -> tuple[RawMemberStep | RawIndexStep, ...]:
    return tuple(
        member_step_type(step.raw_key, step.member_ordinal)
        if type(step) is member_step_type
        else index_step_type(step.item_ordinal)
        for step in path
    )


def _clone_requirement(
    requirement: RuleRequirement,
    *,
    requirement_type: type[RuleRequirement],
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
    text_span_type: type[TextSpan],
) -> RuleRequirement:
    return requirement_type(
        rule_id=requirement.rule_id,
        source_id=requirement.source_id,
        locator=requirement.locator,
        carrier_path=_clone_path(
            requirement.carrier_path,
            member_step_type=member_step_type,
            index_step_type=index_step_type,
        ),
        selection_path=_clone_path(
            requirement.selection_path,
            member_step_type=member_step_type,
            index_step_type=index_step_type,
        ),
        span=(
            None
            if requirement.span is None
            else text_span_type(
                requirement.span.start,
                requirement.span.end,
            )
        ),
        expected_block_sha256=requirement.expected_block_sha256,
        expected_member_sha256=requirement.expected_member_sha256,
        expected_value_sha256=requirement.expected_value_sha256,
        expected_selection_sha256=requirement.expected_selection_sha256,
    )


def _build_vision_entrypoints(
    requirements: tuple[RuleRequirement, ...],
) -> tuple[
    Callable[[object, object, object], VisionSenseCompilerPatch | None],
    Callable[[object, object, object], VisionSenseCompilerPatch | None],
    Callable[[object, object], dict[str, Any]],
    Callable[[object, object, object], dict[str, Any] | None],
]:
    """Bind reviewed data and implementation objects into private closures."""

    adapter_type = SourceAuthorityAdapter
    selection_type = VerifiedSourceSelection
    carrier_type = VerifiedSourceCarrier
    rule_receipt_type = VerifiedRuleReceipt
    requirement_type = RuleRequirement
    address_type = SourceAddress
    receipt_type = SourceReceipt
    member_step_type = RawMemberStep
    index_step_type = RawIndexStep
    text_span_type = TextSpan
    raw_object_type = RawSourceObject
    raw_array_type = RawSourceArray
    raw_member_type = RawSourceMember
    patch_type = VisionSenseCompilerPatch
    mapping_proxy_type = MappingProxyType
    compile_error_type = VisionSenseCompileError
    ambiguity_error_type = VisionSenseSourceAmbiguityError
    addressability_error_type = VisionSenseAddressabilityError
    sha256 = hashlib.sha256
    isfinite = math.isfinite
    authority_ruleset = AUTHORITY_RULESET
    monster_source_id = "core-mc1"
    field_name = "Perception"
    mechanic_type = "vision-sense-profile"
    max_raw_depth = MAX_RAW_DEPTH
    max_raw_nodes = MAX_RAW_NODES
    max_raw_bytes = MAX_RAW_BYTES
    max_signed_64 = MAX_SIGNED_64
    max_creature_members = MAX_CREATURE_MEMBERS
    max_source_bytes = MAX_PERCEPTION_SOURCE_BYTES
    max_tokens = MAX_PERCEPTION_TOKENS
    max_token_bytes = MAX_SENSE_TOKEN_BYTES
    deferred = (
        "other-effect-created-sight-obscurers",
        "mixed-footprint-light-level-ruling",
    )
    specs = (
        (
            "darkvision",
            "darkvision",
            "darkvision",
            "precise",
            "black-and-white-in-dim-or-darkness",
        ),
        (
            "greater darkvision",
            "darkvision",
            "greater-darkvision",
            "precise",
            "black-and-white-in-dim-or-darkness",
        ),
        (
            "low-light vision",
            "low-light-vision",
            "low-light",
            "precise",
            "normal",
        ),
    )
    no_vision_token = "no vision"
    reviewed_requirements = tuple(
        _clone_requirement(
            requirement,
            requirement_type=requirement_type,
            member_step_type=member_step_type,
            index_step_type=index_step_type,
            text_span_type=text_span_type,
        )
        for requirement in requirements
    )

    def reject_raw_cycles_and_bounds(value: object) -> None:
        active: set[int] = set()
        nodes = 0
        byte_count = 0

        def walk(item: object, depth: int) -> None:
            nonlocal nodes, byte_count
            if depth > max_raw_depth:
                raise compile_error_type(
                    "raw source exceeds its depth bound"
                )
            nodes += 1
            if nodes > max_raw_nodes:
                raise compile_error_type(
                    "raw source exceeds its node bound"
                )
            item_type = type(item)
            if item_type is raw_object_type:
                identity = id(item)
                if identity in active:
                    raise compile_error_type(
                        "raw source contains a cycle"
                    )
                active.add(identity)
                try:
                    if type(item.members) is not tuple:
                        raise TypeError(
                            "raw object members must be an exact tuple"
                        )
                    for member in item.members:
                        if (
                            type(member) is not raw_member_type
                            or type(member.key) is not str
                        ):
                            raise TypeError(
                                "raw object contains a non-exact member"
                            )
                        byte_count += len(member.key.encode("utf-8"))
                        if byte_count > max_raw_bytes:
                            raise compile_error_type(
                                "raw source exceeds its byte bound"
                            )
                        walk(member.value, depth + 1)
                finally:
                    active.remove(identity)
                return
            if item_type is raw_array_type:
                identity = id(item)
                if identity in active:
                    raise compile_error_type(
                        "raw source contains a cycle"
                    )
                active.add(identity)
                try:
                    if type(item.items) is not tuple:
                        raise TypeError(
                            "raw array items must be an exact tuple"
                        )
                    for child in item.items:
                        walk(child, depth + 1)
                finally:
                    active.remove(identity)
                return
            if item is None or item_type is bool:
                return
            if item_type is int:
                if abs(item) > max_signed_64:
                    raise compile_error_type(
                        "raw integer exceeds its signed 64-bit bound"
                    )
                return
            if item_type is float:
                if not isfinite(item):
                    raise compile_error_type(
                        "raw number must be finite"
                    )
                return
            if item_type is str:
                byte_count += len(item.encode("utf-8"))
                if byte_count > max_raw_bytes:
                    raise compile_error_type(
                        "raw source exceeds its byte bound"
                    )
                return
            raise TypeError(
                "raw source contains a non-exact JSON value: "
                f"{item_type.__name__}"
            )

        walk(value, 0)

    def require_selection_shell(source: object) -> VerifiedSourceSelection:
        if type(source) is not selection_type:
            raise TypeError(
                "Vision Senses requires an exact VerifiedSourceSelection"
            )
        if (
            type(source.carrier) is not carrier_type
            or type(source.address) is not address_type
            or type(source.carrier.raw_block) is not raw_object_type
            or (
                source.raw_member is not None
                and type(source.raw_member) is not raw_member_type
            )
        ):
            raise addressability_error_type(
                "Vision Senses selection fields are not exact contracts"
            )
        reject_raw_cycles_and_bounds(source.carrier.raw_block)
        reject_raw_cycles_and_bounds(source.raw_value)
        reject_raw_cycles_and_bounds(source.selected_value)
        if source.raw_member is not None:
            reject_raw_cycles_and_bounds(source.raw_member.value)
        return source

    def require_authority(authority: object) -> SourceAuthorityAdapter:
        if type(authority) is not adapter_type:
            raise TypeError(
                "Vision Senses requires an exact SourceAuthorityAdapter"
            )
        return authority

    def validate_providers(
        authority: SourceAuthorityAdapter,
        source: VerifiedSourceSelection,
        providers: object,
        *,
        clone: bool,
    ) -> tuple[VerifiedRuleReceipt, ...]:
        if type(providers) is not tuple:
            raise TypeError(
                "Vision Senses providers must be an exact ordered tuple"
            )
        if len(providers) != len(reviewed_requirements):
            raise addressability_error_type(
                "Vision Senses requires all four reviewed providers"
            )
        if any(type(item) is not rule_receipt_type for item in providers):
            raise TypeError(
                "Vision Senses providers must contain exact "
                "VerifiedRuleReceipt values"
            )
        for provider in providers:
            if type(provider.selection) is not selection_type:
                raise TypeError(
                    "Vision Senses provider selection must be exact"
                )
            require_selection_shell(provider.selection)
        authority.require_shared_authority(source, providers)
        for requirement, provider in zip(
            reviewed_requirements,
            providers,
            strict=True,
        ):
            if (
                provider.rule_id != requirement.rule_id
                or type(provider.requirement) is not requirement_type
                or provider.requirement != requirement
                or type(provider.receipt) is not receipt_type
                or provider.receipt != provider.selection.receipt
            ):
                raise addressability_error_type(
                    "Vision Senses provider order or reviewed identity "
                    f"disagrees: {requirement.rule_id}"
                )
        if not clone:
            return providers
        return tuple(
            authority.resolve_rule(requirement)
            for requirement in reviewed_requirements
        )

    def exact_creature_block(
        authority: SourceAuthorityAdapter,
        source: object,
        *,
        whole_block: bool,
    ) -> RawSourceObject | None:
        selection = require_selection_shell(source)
        authority.validate_selection(selection)
        carrier = selection.carrier
        address = selection.address
        if (
            carrier.ruleset != authority_ruleset
            or carrier.source_id != monster_source_id
        ):
            return None
        if (
            type(address.carrier_path) is not tuple
            or not address.carrier_path
            or type(address.carrier_path[-1]) is not member_step_type
            or address.carrier_path[-1].raw_key != "^.creature"
            or address.span is not None
            or type(carrier.raw_block) is not raw_object_type
            or len(carrier.raw_block.members) > max_creature_members
        ):
            return None
        if whole_block:
            if (
                type(address.selection_path) is not tuple
                or address.selection_path
                or selection.raw_value is not carrier.raw_block
                or selection.selected_value is not selection.raw_value
                or selection.raw_member is not None
            ):
                return None
        return carrier.raw_block

    def normalized_perception(
        authority: SourceAuthorityAdapter,
        source: object,
    ) -> tuple[str, tuple[str, ...], int] | None:
        block = exact_creature_block(
            authority,
            source,
            whole_block=False,
        )
        if block is None:
            return None
        selection = source
        address = selection.address
        if (
            type(address.selection_path) is not tuple
            or len(address.selection_path) != 1
            or type(address.selection_path[0]) is not member_step_type
            or address.selection_path[0].raw_key != field_name
            or type(selection.raw_member) is not raw_member_type
            or selection.raw_member.key != field_name
            or selection.selected_value is not selection.raw_value
        ):
            return None
        step = address.selection_path[0]
        if step.member_ordinal >= len(block.members):
            raise addressability_error_type(
                "verified Perception ordinal is out of range"
            )
        member = block.members[step.member_ordinal]
        if (
            type(member) is not raw_member_type
            or member is not selection.raw_member
            or member.value is not selection.raw_value
        ):
            raise addressability_error_type(
                "verified Perception selection disagrees with its carrier"
            )
        names = tuple(item for item in block.members if item.key == "Name")
        perceptions = tuple(
            item for item in block.members if item.key == field_name
        )
        if (
            len(names) != 1
            or type(names[0]) is not raw_member_type
            or type(names[0].value) is not str
            or not names[0].value
            or names[0].value != names[0].value.strip()
        ):
            raise compile_error_type(
                "verified creature requires one exact Name member"
            )
        if len(perceptions) != 1 or perceptions[0] is not member:
            raise ambiguity_error_type(
                "verified creature requires one exact Perception member"
            )

        value = selection.raw_value
        if type(value) is str:
            encoded = value.encode("utf-8")
            if (
                not value
                or value != value.strip()
                or len(encoded) > max_source_bytes
            ):
                raise compile_error_type(
                    "Perception modifier string is malformed or oversized"
                )
            return value, (), step.member_ordinal
        if (
            type(value) is not raw_array_type
            or type(value.items) is not tuple
            or len(value.items) != 2
        ):
            raise compile_error_type(
                "Perception must be a modifier string or exact "
                "[modifier, senses] array"
            )
        modifier, raw_senses = value.items
        if (
            type(modifier) is not str
            or not modifier
            or modifier != modifier.strip()
            or len(modifier.encode("utf-8"))
            > max_source_bytes
            or type(raw_senses) is not raw_array_type
            or type(raw_senses.items) is not tuple
        ):
            raise compile_error_type(
                "Perception modifier-and-senses production is malformed"
            )
        if len(raw_senses.items) > max_tokens:
            raise compile_error_type(
                "Perception sense list exceeds its token bound"
            )
        tokens: list[str] = []
        total_bytes = len(modifier.encode("utf-8"))
        for token in raw_senses.items:
            if type(token) is not str:
                raise TypeError(
                    "Perception sense tokens must be exact strings"
                )
            token_bytes = len(token.encode("utf-8"))
            if (
                not token
                or token != token.strip()
                or token_bytes > max_token_bytes
            ):
                raise compile_error_type(
                    "Perception sense token is empty, untrimmed, or oversized"
                )
            total_bytes += token_bytes
            if total_bytes > max_source_bytes:
                raise compile_error_type(
                    "Perception source exceeds its byte bound"
                )
            tokens.append(token)
        return modifier, tuple(tokens), step.member_ordinal

    def sole_spec(
        tokens: tuple[str, ...],
    ) -> tuple[int, tuple[str, str, str, str, str]] | None:
        matches: list[
            tuple[int, tuple[str, str, str, str, str]]
        ] = []
        for index, token in enumerate(tokens):
            for spec in specs:
                if token == spec[0]:
                    matches.append((index, spec))
                    break
        if len(matches) > 1:
            labels = ", ".join(repr(item[1][0]) for item in matches)
            raise ambiguity_error_type(
                "multiple supported Perception vision tokens: " + labels
            )
        if matches and no_vision_token in tokens:
            raise ambiguity_error_type(
                "contradictory Perception vision and no-vision tokens"
            )
        return matches[0] if matches else None

    def fresh_state(
        patch: object,
    ) -> tuple[
        SourceAuthorityAdapter,
        VerifiedSourceSelection,
        tuple[VerifiedRuleReceipt, ...],
        str,
        tuple[str, ...],
        int,
        int,
        tuple[str, str, str, str, str],
    ]:
        if type(patch) is not patch_type:
            raise TypeError(
                "Vision Senses projection requires an exact "
                "VisionSenseCompilerPatch"
            )
        authority = require_authority(patch._authority)
        source = require_selection_shell(patch._source)
        normalized = normalized_perception(authority, source)
        if normalized is None:
            raise addressability_error_type(
                "Vision Senses patch source no longer matches its contract"
            )
        modifier, tokens, member_ordinal = normalized
        providers = validate_providers(
            authority,
            source,
            patch._providers,
            clone=False,
        )
        match = sole_spec(tokens)
        if match is None:
            raise addressability_error_type(
                "Vision Senses patch source no longer has a supported token"
            )
        sense_index, spec = match
        return (
            authority,
            source,
            providers,
            modifier,
            tokens,
            member_ordinal,
            sense_index,
            spec,
        )

    def mechanic_for(
        source_text: str,
        sense_index: int,
        spec: tuple[str, str, str, str, str],
    ) -> dict[str, object]:
        _token, family_id, grade, acuity, color_mode = spec
        return {
            "type": mechanic_type,
            "familyId": family_id,
            "acuity": acuity,
            "grade": grade,
            "colorMode": color_mode,
            "rangeFeet": None,
            "sourceText": source_text,
            "sourceTokenIndex": sense_index,
        }

    def project(patch: object, mode: str) -> object:
        (
            authority,
            source,
            _providers,
            modifier,
            tokens,
            member_ordinal,
            sense_index,
            spec,
        ) = fresh_state(patch)
        source_text = spec[0]
        if mode == "source":
            return authority.reload(source.receipt)
        if mode == "source-receipt":
            return authority.reload(source.receipt).receipt
        if mode == "providers":
            return tuple(
                authority.resolve_rule(requirement)
                for requirement in reviewed_requirements
            )
        if mode == "sense-index":
            return sense_index
        if mode == "source-text":
            return source_text
        if mode == "modifier-source-text":
            return modifier
        if mode == "sense-tokens":
            return tuple(tokens)
        if mode == "mechanic":
            return mapping_proxy_type(
                mechanic_for(source_text, sense_index, spec)
            )
        if mode == "deferred-mechanics":
            return tuple(deferred)
        if mode != "serialized":
            raise ValueError("unknown Vision Senses projection")

        fresh_source = authority.reload(source.receipt)
        fresh_providers = tuple(
            authority.resolve_rule(requirement)
            for requirement in reviewed_requirements
        )
        return {
            "compileSupported": True,
            "runtimeSupported": True,
            "mechanic": mechanic_for(source_text, sense_index, spec),
            "sourceToken": {
                "field": field_name,
                "memberOrdinal": member_ordinal,
                "senseIndex": sense_index,
                "sourceText": source_text,
                "sourceTextSha256": sha256(
                    source_text.encode("utf-8")
                ).hexdigest(),
            },
            "source": fresh_source.receipt.as_serialized(),
            "rules": [
                provider.as_serialized()
                for provider in fresh_providers
            ],
            "deferredMechanics": list(deferred),
        }

    def new_patch(
        authority: SourceAuthorityAdapter,
        source: VerifiedSourceSelection,
        providers: tuple[VerifiedRuleReceipt, ...],
    ) -> VisionSenseCompilerPatch:
        result = object.__new__(patch_type)
        object.__setattr__(result, "_authority", authority)
        object.__setattr__(result, "_source", source)
        object.__setattr__(result, "_providers", providers)
        object.__setattr__(result, "_project", project)
        return result

    def compile_entry(
        authority: object,
        source: object,
        providers: object,
        /,
    ) -> VisionSenseCompilerPatch | None:
        verified_authority = require_authority(authority)
        normalized = normalized_perception(verified_authority, source)
        if normalized is None:
            return None
        _modifier, tokens, _member_ordinal = normalized
        verified_providers = validate_providers(
            verified_authority,
            source,
            providers,
            clone=True,
        )
        if sole_spec(tokens) is None:
            return None
        fresh_source = verified_authority.reload(source.receipt)
        return new_patch(
            verified_authority,
            fresh_source,
            verified_providers,
        )

    def link_entry(
        authority: object,
        source: object,
        providers: object,
        /,
    ) -> VisionSenseCompilerPatch | None:
        verified_authority = require_authority(authority)
        block = exact_creature_block(
            verified_authority,
            source,
            whole_block=True,
        )
        if block is None:
            return None
        perception_members = tuple(
            (ordinal, member)
            for ordinal, member in enumerate(block.members)
            if member.key == field_name
        )
        if len(perception_members) > 1:
            raise ambiguity_error_type(
                "raw creature contains duplicate Perception members"
            )
        if not perception_members:
            return None
        ordinal, member = perception_members[0]
        if type(member) is not raw_member_type:
            raise TypeError("raw Perception member is not exact")
        selection = source.carrier.select(
            (member_step_type(field_name, ordinal),)
        )
        return compile_entry(
            verified_authority,
            selection,
            providers,
        )

    def project_entry(
        authority: object,
        patch: object,
        /,
    ) -> dict[str, Any]:
        verified_authority = require_authority(authority)
        if type(patch) is not patch_type:
            raise TypeError(
                "link_vision_sense_patch requires an exact "
                "VisionSenseCompilerPatch"
            )
        if patch._authority is not verified_authority:
            raise addressability_error_type(
                "Vision Senses patch belongs to another authority context"
            )
        serialized = project(patch, "serialized")
        state = fresh_state(patch)
        return {
            "modifierSourceText": state[3],
            "senses": list(state[4]),
            "vision": serialized,
        }

    def compile_and_link_entry(
        authority: object,
        source: object,
        providers: object,
        /,
    ) -> dict[str, Any] | None:
        patch = link_entry(authority, source, providers)
        if patch is None:
            return None
        return project_entry(authority, patch)

    return (
        compile_entry,
        link_entry,
        project_entry,
        compile_and_link_entry,
    )


(
    compile_vision_sense,
    link_vision_sense,
    link_vision_sense_patch,
    compile_and_link_vision_sense,
) = _build_vision_entrypoints(RULE_REQUIREMENTS)


__all__ = [
    "DARKVISION_GLOSSARY_REQUIREMENT",
    "DARKVISION_PLAYER_REQUIREMENT",
    "LOW_LIGHT_GLOSSARY_REQUIREMENT",
    "LOW_LIGHT_PLAYER_REQUIREMENT",
    "MAX_CREATURE_MEMBERS",
    "MAX_PERCEPTION_SOURCE_BYTES",
    "MAX_PERCEPTION_TOKENS",
    "MAX_SENSE_TOKEN_BYTES",
    "MONSTER_CORE_SOURCE_ID",
    "PERCEPTION_FIELD_NAME",
    "RULE_REQUIREMENTS",
    "VISION_SENSE_FAMILY_ID",
    "VISION_SENSE_MECHANIC_TYPE",
    "VisionSenseAddressabilityError",
    "VisionSenseCompileError",
    "VisionSenseCompilerPatch",
    "VisionSenseSourceAmbiguityError",
    "compile_and_link_vision_sense",
    "compile_vision_sense",
    "link_vision_sense",
    "link_vision_sense_patch",
]

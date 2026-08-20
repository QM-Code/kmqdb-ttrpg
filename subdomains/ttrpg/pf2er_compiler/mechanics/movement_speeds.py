"""Compile exact Monster Core Speed fields into typed movement facts.

This family is compile/link-only and deliberately unregistered.  Every
consumer Speed field, inherited local ability, and provider rule is resolved
through one retained :class:`SourceAuthorityAdapter`.  Public claims are
revalidated and compiler-derived again whenever they are projected.

The closed grammar preserves every comma and semicolon token.  Numeric modes
are source-backed by the Player Core movement rules.  A nonnumeric token must
resolve to exactly one ability in the same duplicate-preserving creature
block or to one exact constant spell.  The eight inherited ``As ...`` links
in the reviewed Core Monster 1 corpus additionally require an immutable
source-and-target review decision.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RawSourceValue,
    SerializedObject,
)
from .source_authority import (
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
)


FAMILY_ID = "movement-speeds"
COMPILER_ID = "movement-speeds"
MONSTER_CORE_SOURCE_ID = "core-mc1"
MONSTER_CORE_SPEED_LOCATOR = "5.3"

MAX_SPEED_SOURCE_BYTES = 512
MAX_SPEED_TOKENS = 16
MAX_SPEED_TOKEN_BYTES = 128
MAX_SOURCE_BLOCK_MEMBERS = 256
MAX_SOURCE_KEY_BYTES = 128
MAX_SOURCE_STRING_BYTES = 8_192
MAX_SOURCE_NODES = 256
MAX_SOURCE_DEPTH = 8
MAX_CONTENT_PATH_STEPS = 32
MAX_CONSTANT_SPELLS_PER_RANK = 32
MAX_CONSTANT_SPELL_SOURCE_BYTES = 512
MAX_INHERITANCE_BINDINGS = 16
MAX_IDENTIFIER_BYTES = 4_096
MAX_SOURCE_INTEGER = (1 << 63) - 1

LAND_MODE = "land"
SPECIAL_MODES = ("burrow", "climb", "fly", "swim")
MOVEMENT_MODES = (LAND_MODE, *SPECIAL_MODES)

INHERITANCE_REVIEW_SCHEMA = 1
INHERITANCE_REVIEWER_ID = "kmqdb:core-mc1-movement-speed-foundation"


@dataclass(frozen=True, slots=True)
class ResolvedMovementAbilityReference:
    """One exact reviewed ``As ...`` source-to-target decision."""

    authority: SourceAuthorityAdapter
    source_selection: VerifiedSourceSelection
    target_selection: VerifiedSourceSelection
    review_record_sha256: str
    decision_digest: str

    def __post_init__(self) -> None:
        raise RuntimeError(
            "ResolvedMovementAbilityReference contract is not bound"
        )


@dataclass(frozen=True, slots=True)
class MovementSpeedSource:
    """One exact Speed member and its duplicate-preserving creature block."""

    authority: SourceAuthorityAdapter
    speed_selection: VerifiedSourceSelection
    inherited_ability_bindings: tuple[
        ResolvedMovementAbilityReference,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        raise RuntimeError("MovementSpeedSource contract is not bound")


@dataclass(frozen=True, slots=True)
class MovementSpeedRuleBundle:
    """The exact reviewed provider rules used by this compiler family."""

    authority: SourceAuthorityAdapter
    receipts: tuple[VerifiedRuleReceipt, ...]

    def __post_init__(self) -> None:
        raise RuntimeError("MovementSpeedRuleBundle contract is not bound")


@dataclass(frozen=True, slots=True)
class MovementSpeedToken:
    source_text: str
    separator_after: str | None

    def __post_init__(self) -> None:
        raise RuntimeError("MovementSpeedToken contract is not bound")


@dataclass(frozen=True, slots=True)
class MovementTerrainRestriction:
    restriction_type: str
    fact_name: str
    fact_value: str

    def __post_init__(self) -> None:
        raise RuntimeError(
            "MovementTerrainRestriction contract is not bound"
        )


@dataclass(frozen=True, slots=True)
class MovementMode:
    mode: str
    feet: int
    source_text: str
    source_token: int
    restriction: MovementTerrainRestriction | None
    provider_rule_id: str

    def __post_init__(self) -> None:
        raise RuntimeError("MovementMode contract is not bound")


@dataclass(frozen=True, slots=True)
class MovementAbilityReference:
    ability_id: str
    label: str
    authority_kind: str
    mechanic_id: str
    source_text: str
    source_token: int
    markup: str
    authority_json: str
    rule_source_id: str
    rule_locator: str
    provider_rule_id: str | None
    inherited_target: ResolvedMovementAbilityReference | None = None

    def __post_init__(self) -> None:
        raise RuntimeError(
            "MovementAbilityReference contract is not bound"
        )


@dataclass(frozen=True, slots=True)
class MovementSpeedPatch:
    source: MovementSpeedSource
    rules: MovementSpeedRuleBundle
    tokens: tuple[MovementSpeedToken, ...]
    modes: tuple[MovementMode, ...]
    abilities: tuple[MovementAbilityReference, ...]
    deferred_mechanics: tuple[str, ...]

    def __post_init__(self) -> None:
        raise RuntimeError("MovementSpeedPatch contract is not bound")


def _bind_raw_source_contract(
    raw_object_type: type[RawSourceObject],
    raw_array_type: type[RawSourceArray],
    raw_member_type: type[RawSourceMember],
):
    """Capture bounded duplicate-preserving source primitives."""

    maximum_depth = 8
    maximum_nodes = 256
    maximum_members = 256
    maximum_key_bytes = 128
    maximum_string_bytes = 8_192
    maximum_encoded_bytes = 8_192
    maximum_integer = (1 << 63) - 1
    invalid = object()
    json_dumps = json.dumps
    sha256 = hashlib.sha256
    isfinite = math.isfinite
    raw_get = object.__getattribute__

    def bounded_payload(
        value: RawSourceValue,
        *,
        depth: int,
        nodes: list[int],
    ) -> Any:
        if depth > maximum_depth:
            return invalid
        nodes[0] += 1
        if nodes[0] > maximum_nodes:
            return invalid
        if type(value) is raw_object_type:
            members_value = raw_get(value, "members")
            if len(members_value) > maximum_members:
                return invalid
            members = []
            for member in members_value:
                key = raw_get(member, "key")
                if (
                    type(member) is not raw_member_type
                    or len(key.encode("utf-8"))
                    > maximum_key_bytes
                ):
                    return invalid
                item = bounded_payload(
                    raw_get(member, "value"),
                    depth=depth + 1,
                    nodes=nodes,
                )
                if item is invalid:
                    return invalid
                members.append([key, item])
            return {"$orderedObject": members}
        if type(value) is raw_array_type:
            items = []
            for raw_item in raw_get(value, "items"):
                item = bounded_payload(
                    raw_item,
                    depth=depth + 1,
                    nodes=nodes,
                )
                if item is invalid:
                    return invalid
                items.append(item)
            return items
        if type(value) is str:
            if len(value.encode("utf-8")) > maximum_string_bytes:
                return invalid
            return value
        if value is None or type(value) is bool:
            return value
        if type(value) is int:
            if value < -maximum_integer - 1 or value > maximum_integer:
                return invalid
            return value
        if type(value) is float:
            return value if isfinite(value) else invalid
        return invalid

    def ordered_hash(value: RawSourceValue, /) -> str | None:
        payload = bounded_payload(value, depth=0, nodes=[0])
        if payload is invalid:
            return None
        encoded = json_dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > maximum_encoded_bytes:
            return None
        return sha256(encoded).hexdigest()

    def block_name(value: RawSourceObject, /) -> str:
        if type(value) is not raw_object_type:
            raise TypeError("movement source block must be exact")
        candidates = tuple(
            member
            for member in raw_get(value, "members")
            if raw_get(member, "key").strip() == "Name"
        )
        if (
            len(candidates) != 1
            or raw_get(candidates[0], "key") != "Name"
            or type(raw_get(candidates[0], "value")) is not str
            or not raw_get(candidates[0], "value")
            or raw_get(candidates[0], "value")
            != raw_get(candidates[0], "value").strip()
            or len(
                raw_get(candidates[0], "value").encode("utf-8")
            )
            > 4_096
        ):
            raise ValueError(
                "movement source block requires one exact bounded Name"
            )
        return raw_get(candidates[0], "value")

    def exact_occurrence(
        value: RawSourceObject,
        absolute_ordinal: int,
        raw_key: str,
    ) -> tuple[int, int]:
        if (
            type(value) is not raw_object_type
            or type(absolute_ordinal) is not int
            or absolute_ordinal < 0
            or absolute_ordinal >= len(raw_get(value, "members"))
            or type(raw_key) is not str
        ):
            raise ValueError("movement source member address is invalid")
        exact = tuple(
            index
            for index, member in enumerate(raw_get(value, "members"))
            if raw_get(member, "key") == raw_key
        )
        if absolute_ordinal not in exact:
            raise ValueError(
                "movement source member ordinal disagrees with its key"
            )
        return exact.index(absolute_ordinal), len(exact)

    return ordered_hash, block_name, exact_occurrence


(
    _ordered_source_sha256,
    _block_name,
    _exact_member_occurrence,
) = _bind_raw_source_contract(
    RawSourceObject,
    RawSourceArray,
    RawSourceMember,
)
del _bind_raw_source_contract


def _bind_claim_projection_contract(
    receipt_type: type[SourceReceipt],
    address_type: type[SourceAddress],
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
    span_type: type[TextSpan],
    requirement_type: type[RuleRequirement],
    rule_type: type[VerifiedRuleReceipt],
    carrier_type: type[VerifiedSourceCarrier],
    selection_type: type[VerifiedSourceSelection],
):
    """Project authority claims without dispatching through class hooks."""

    receipt_schema = 1
    receipt_kind = "pf2er-source-receipt"
    maximum_identifier_bytes = 4_096
    maximum_path_steps = 32
    maximum_integer = (1 << 63) - 1
    source_id_pattern = re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        re.ASCII,
    )
    sha256 = hashlib.sha256
    canonical_json = canonical_json_bytes
    raw_get = object.__getattribute__

    def require_text(value: object, label: str) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or len(value.encode("utf-8")) > maximum_identifier_bytes
        ):
            raise ValueError(f"{label} must be exact bounded text")
        return value

    def require_source_id(value: object, label: str) -> str:
        text = require_text(value, label)
        if source_id_pattern.fullmatch(text) is None:
            raise ValueError(f"{label} is invalid")
        return text

    def require_integer(value: object, label: str) -> int:
        if (
            type(value) is not int
            or value < 0
            or value > maximum_integer
        ):
            raise ValueError(f"{label} must be a bounded ordinal")
        return value

    def require_sha(
        value: object,
        label: str,
        *,
        optional: bool = False,
    ) -> str | None:
        if optional and value is None:
            return None
        if (
            type(value) is not str
            or len(value) != 64
            or any(
                character not in "0123456789abcdef"
                for character in value
            )
        ):
            raise ValueError(f"{label} must be a lowercase SHA-256")
        return value

    def serialize_step(step: object) -> SerializedObject:
        if type(step) is member_step_type:
            raw_key = raw_get(step, "raw_key")
            ordinal = raw_get(step, "member_ordinal")
            require_text(raw_key, "raw member path key")
            require_integer(
                ordinal,
                "raw member path ordinal",
            )
            return {
                "kind": "member",
                "rawKey": raw_key,
                "memberOrdinal": ordinal,
            }
        if type(step) is index_step_type:
            ordinal = raw_get(step, "item_ordinal")
            require_integer(
                ordinal,
                "raw index path ordinal",
            )
            return {
                "kind": "index",
                "itemOrdinal": ordinal,
            }
        raise TypeError("authority path step must be exact")

    def serialize_path(value: object, label: str) -> list[SerializedObject]:
        if (
            type(value) is not tuple
            or len(value) > maximum_path_steps
        ):
            raise ValueError(f"{label} is not one exact bounded path")
        return [serialize_step(step) for step in value]

    def serialize_span(value: object) -> SerializedObject | None:
        if value is None:
            return None
        if type(value) is not span_type:
            raise TypeError("authority text span must be exact")
        start = require_integer(
            raw_get(value, "start"),
            "authority span start",
        )
        end = require_integer(
            raw_get(value, "end"),
            "authority span end",
        )
        if end <= start:
            raise ValueError("authority text span must be non-empty")
        return {"start": start, "end": end}

    def serialize_address(value: object) -> SerializedObject:
        if type(value) is not address_type:
            raise TypeError("authority source address must be exact")
        target = serialize_path(
            raw_get(value, "target_path"),
            "authority target path",
        )
        carrier = serialize_path(
            raw_get(value, "carrier_path"),
            "authority carrier path",
        )
        selection = serialize_path(
            raw_get(value, "selection_path"),
            "authority selection path",
        )
        if len(target) + len(carrier) + len(selection) > maximum_path_steps:
            raise ValueError(
                "authority address paths exceed their combined bound"
            )
        return {
            "sourceId": require_source_id(
                raw_get(value, "source_id"),
                "authority address source id",
            ),
            "locator": require_text(
                raw_get(value, "locator"),
                "authority address locator",
            ),
            "sectionId": require_text(
                raw_get(value, "section_id"),
                "authority address section id",
            ),
            "targetPath": target,
            "carrierPath": carrier,
            "selectionPath": selection,
            "span": serialize_span(raw_get(value, "span")),
        }

    def receipt_payload(
        *,
        ruleset: object,
        authority_digest: object,
        address: object,
        block_sha256: object,
        member_sha256: object,
        value_sha256: object,
        selection_sha256: object,
    ) -> tuple[SerializedObject, str]:
        body = {
            "schema": receipt_schema,
            "kind": receipt_kind,
            "ruleset": require_text(ruleset, "source receipt ruleset"),
            "authorityDigest": require_sha(
                authority_digest,
                "source receipt authority digest",
            ),
            "address": serialize_address(address),
            "hashes": {
                "blockSha256": require_sha(
                    block_sha256,
                    "source receipt block digest",
                ),
                "memberSha256": require_sha(
                    member_sha256,
                    "source receipt member digest",
                    optional=True,
                ),
                "valueSha256": require_sha(
                    value_sha256,
                    "source receipt value digest",
                ),
                "selectionSha256": require_sha(
                    selection_sha256,
                    "source receipt selection digest",
                ),
            },
        }
        return body, sha256(canonical_json(body)).hexdigest()

    def serialize_receipt(value: object) -> SerializedObject:
        if type(value) is not receipt_type:
            raise TypeError("source receipt must be exact")
        body, digest = receipt_payload(
            ruleset=raw_get(value, "ruleset"),
            authority_digest=raw_get(value, "authority_digest"),
            address=raw_get(value, "address"),
            block_sha256=raw_get(value, "block_sha256"),
            member_sha256=raw_get(value, "member_sha256"),
            value_sha256=raw_get(value, "value_sha256"),
            selection_sha256=raw_get(value, "selection_sha256"),
        )
        return {**body, "digest": digest}

    def serialize_selection_receipt(
        value: object,
    ) -> SerializedObject:
        if (
            type(value) is not selection_type
            or type(raw_get(value, "carrier")) is not carrier_type
            or type(raw_get(value, "address")) is not address_type
        ):
            raise TypeError("verified source selection must be exact")
        carrier = raw_get(value, "carrier")
        address = raw_get(value, "address")
        if (
            raw_get(carrier, "source_id")
            != raw_get(address, "source_id")
            or raw_get(carrier, "locator")
            != raw_get(address, "locator")
            or raw_get(carrier, "section_id")
            != raw_get(address, "section_id")
            or serialize_path(
                raw_get(carrier, "target_path"),
                "verified carrier target path",
            )
            != serialize_path(
                raw_get(address, "target_path"),
                "verified address target path",
            )
            or serialize_path(
                raw_get(carrier, "carrier_path"),
                "verified carrier path",
            )
            != serialize_path(
                raw_get(address, "carrier_path"),
                "verified address carrier path",
            )
        ):
            raise ValueError(
                "verified selection carrier and address disagree"
            )
        body, digest = receipt_payload(
            ruleset=raw_get(carrier, "ruleset"),
            authority_digest=raw_get(carrier, "authority_digest"),
            address=address,
            block_sha256=raw_get(carrier, "block_sha256"),
            member_sha256=raw_get(value, "member_sha256"),
            value_sha256=raw_get(value, "value_sha256"),
            selection_sha256=raw_get(value, "selection_sha256"),
        )
        return {**body, "digest": digest}

    def selection_receipt_digest(value: object) -> str:
        return str(serialize_selection_receipt(value)["digest"])

    def serialize_requirement(value: object) -> SerializedObject:
        if type(value) is not requirement_type:
            raise TypeError("reviewed rule requirement must be exact")
        carrier = serialize_path(
            raw_get(value, "carrier_path"),
            "reviewed rule carrier path",
        )
        selection = serialize_path(
            raw_get(value, "selection_path"),
            "reviewed rule selection path",
        )
        if len(carrier) + len(selection) > maximum_path_steps:
            raise ValueError(
                "reviewed rule paths exceed their combined bound"
            )
        expected = (
            require_sha(
                raw_get(value, "expected_block_sha256"),
                "reviewed block digest",
                optional=True,
            ),
            require_sha(
                raw_get(value, "expected_member_sha256"),
                "reviewed member digest",
                optional=True,
            ),
            require_sha(
                raw_get(value, "expected_value_sha256"),
                "reviewed value digest",
                optional=True,
            ),
            require_sha(
                raw_get(value, "expected_selection_sha256"),
                "reviewed selection digest",
                optional=True,
            ),
        )
        if all(item is None for item in expected):
            raise ValueError(
                "reviewed rule must pin at least one source digest"
            )
        return {
            "ruleId": require_text(
                raw_get(value, "rule_id"),
                "reviewed rule id",
            ),
            "sourceId": require_source_id(
                raw_get(value, "source_id"),
                "reviewed rule source id",
            ),
            "locator": require_text(
                raw_get(value, "locator"),
                "reviewed rule locator",
            ),
            "carrierPath": carrier,
            "selectionPath": selection,
            "span": serialize_span(raw_get(value, "span")),
            "expectedHashes": {
                "blockSha256": expected[0],
                "memberSha256": expected[1],
                "valueSha256": expected[2],
                "selectionSha256": expected[3],
            },
        }

    def serialize_rule(value: object) -> SerializedObject:
        if (
            type(value) is not rule_type
            or type(raw_get(value, "requirement")) is not requirement_type
            or type(raw_get(value, "selection")) is not selection_type
            or type(raw_get(value, "receipt")) is not receipt_type
        ):
            raise TypeError("verified provider rule must be exact")
        raw_requirement = raw_get(value, "requirement")
        requirement = serialize_requirement(raw_requirement)
        selection_receipt = serialize_selection_receipt(
            raw_get(value, "selection")
        )
        supplied_receipt = serialize_receipt(
            raw_get(value, "receipt")
        )
        if (
            raw_get(value, "rule_id")
            != raw_get(raw_requirement, "rule_id")
            or supplied_receipt != selection_receipt
        ):
            raise ValueError(
                "verified provider rule claim is inconsistent"
            )
        return {
            "ruleId": raw_get(value, "rule_id"),
            "requirement": requirement,
            "source": selection_receipt,
        }

    return (
        serialize_receipt,
        serialize_selection_receipt,
        selection_receipt_digest,
        serialize_requirement,
        serialize_rule,
    )


(
    _serialize_source_receipt,
    _serialize_selection_receipt,
    _selection_receipt_digest,
    _serialize_rule_requirement,
    _serialize_verified_rule,
) = _bind_claim_projection_contract(
    SourceReceipt,
    SourceAddress,
    RawMemberStep,
    RawIndexStep,
    TextSpan,
    RuleRequirement,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
)
del _bind_claim_projection_contract


def _bind_inheritance_contract(
    binding_type: type[ResolvedMovementAbilityReference],
    adapter_type: type[SourceAuthorityAdapter],
    selection_type: type[VerifiedSourceSelection],
    member_step_type: type[RawMemberStep],
    raw_member_type: type[RawSourceMember],
    raw_object_type: type[RawSourceObject],
    ordered_hash: Any,
    block_name: Any,
    exact_occurrence: Any,
    serialize_selection_receipt: Any,
    selection_receipt_digest: Any,
):
    """Capture the eight reviewed Core Monster inheritance decisions."""

    schema = 1
    reviewer = "kmqdb:core-mc1-movement-speed-foundation"
    source_id = "core-mc1"
    maximum_identifier_bytes = 4_096
    as_reference = re.compile(r"^As [^\n]+\.$")
    sha256 = hashlib.sha256
    canonical_json = canonical_json_bytes
    validate_selection = adapter_type.validate_selection
    address = adapter_type.address
    resolve = adapter_type.resolve
    raw_get = object.__getattribute__
    object_new = object.__new__
    object_setattr = object.__setattr__
    records = (
        (
            "44.4",
            "Boggard Warrior",
            "eaefeb8e740df5d6ac730be25afa52f5fe3ff3e453763dd0f73247205042aeca",
            "!.Swamp Passage",
            22,
            "23c47648dad31608364a3baa68b1d2cccbbd87255bccfc2c7589b11ff71c1476",
            "44.2",
            "Boggard Scout",
            "d1741a8d6df3ba45b423f072f7bda27ea7ae868d9b0780cf0470dd71eca8c982",
            "!.Swamp Passage",
            22,
            1,
            "cf3bced6827713fec08c749913953e4e9243bc04ff8a0dcfccda22845f585426",
        ),
        (
            "45.2",
            "Boggard Swampseer",
            "e20c08399fd3a95048e4b941903fd9fc9708618bec4d98e43eb03959791868dd",
            "!.Swamp Passage",
            24,
            "23c47648dad31608364a3baa68b1d2cccbbd87255bccfc2c7589b11ff71c1476",
            "44.2",
            "Boggard Scout",
            "d1741a8d6df3ba45b423f072f7bda27ea7ae868d9b0780cf0470dd71eca8c982",
            "!.Swamp Passage",
            22,
            1,
            "cf3bced6827713fec08c749913953e4e9243bc04ff8a0dcfccda22845f585426",
        ),
        (
            "142.4",
            "Living Landslide",
            "7ab0ac80a64c7b03c68e5a6ae851296309761852c52a403fb11a3139bcc011f3",
            "!.Earth Glide",
            23,
            "911dc8673da689a6b6282df19275d421ac27c47e966842e984e4bdc839d62293",
            "142.2",
            "Sod Hound",
            "b497056374d7ac2ab25cdeb48e5e0993814efa625842562e250802349f7731c3",
            "!.Earth Glide",
            21,
            1,
            "48571744fedf51aa2116271abf2e6f734622cb6ea9e4b18a5dd7fdefc5387a7a",
        ),
        (
            "142.6",
            "Stone Mauler",
            "cb2cc4980ea444a0a4bbe60093f6d44fcd1760947cb4754095102b672e6c999c",
            "!.Earth Glide",
            25,
            "911dc8673da689a6b6282df19275d421ac27c47e966842e984e4bdc839d62293",
            "142.2",
            "Sod Hound",
            "b497056374d7ac2ab25cdeb48e5e0993814efa625842562e250802349f7731c3",
            "!.Earth Glide",
            21,
            1,
            "48571744fedf51aa2116271abf2e6f734622cb6ea9e4b18a5dd7fdefc5387a7a",
        ),
        (
            "143.2",
            "Elemental Avalanche",
            "34f04fd7ca13cdc40dfb0292b04f48a35d6790afaa627c783d6b718da7aeeb22",
            "!.Earth Glide",
            25,
            "911dc8673da689a6b6282df19275d421ac27c47e966842e984e4bdc839d62293",
            "142.2",
            "Sod Hound",
            "b497056374d7ac2ab25cdeb48e5e0993814efa625842562e250802349f7731c3",
            "!.Earth Glide",
            21,
            1,
            "48571744fedf51aa2116271abf2e6f734622cb6ea9e4b18a5dd7fdefc5387a7a",
        ),
        (
            "120.1",
            "Adult Horned Dragon",
            "b938aa98d7d6bec306f7ace48adc893dad2c9e51135b5d3d8bb5c2df38686dae",
            "!.Forest Passage",
            26,
            "90c7f09bc7b68a0c6bd334f488a67cdc42162a9f808e09de696810d92405db2b",
            "119.3",
            "Young Horned Dragon",
            "a9ecd72b8c2f74a4f69adc79d086648ac4b9d6f1bb6735655ac393394100b746",
            "!.Forest Passage",
            26,
            1,
            "7ae206161635b3e6dab2fb6ffaadbd0dca68f66c01e2ac7768b596431df36dc7",
        ),
        (
            "121.2",
            "Ancient Horned Dragon",
            "e46176caf6258b9838a0f8ab24384dacd8ea5cd02f941babed63877a3e9dc6e3",
            "!.Forest Passage",
            27,
            "90c7f09bc7b68a0c6bd334f488a67cdc42162a9f808e09de696810d92405db2b",
            "119.3",
            "Young Horned Dragon",
            "a9ecd72b8c2f74a4f69adc79d086648ac4b9d6f1bb6735655ac393394100b746",
            "!.Forest Passage",
            26,
            1,
            "7ae206161635b3e6dab2fb6ffaadbd0dca68f66c01e2ac7768b596431df36dc7",
        ),
        (
            "121.2",
            "Ancient Horned Dragon",
            "e46176caf6258b9838a0f8ab24384dacd8ea5cd02f941babed63877a3e9dc6e3",
            "!.Trackless Journey",
            29,
            "8b32a75563ae20285eb6256d4b63f1ce301f251e56a122d2ec6d91651b18b24f",
            "120.1",
            "Adult Horned Dragon",
            "b938aa98d7d6bec306f7ace48adc893dad2c9e51135b5d3d8bb5c2df38686dae",
            "!.Trackless Journey",
            29,
            1,
            "3c8923a5a3f0ba531cdae66158acf6fd1e695a8ac7a3f0dd5f169e65edf53cc6",
        ),
    )

    def require_sha(value: object, label: str) -> str:
        if (
            type(value) is not str
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"{label} must be a lowercase SHA-256")
        return value

    def selection_facts(
        authority: SourceAuthorityAdapter,
        selection: VerifiedSourceSelection,
        label: str,
    ) -> tuple[
        VerifiedSourceSelection,
        str,
        str,
        str,
        int,
        int,
        str,
    ]:
        if type(authority) is not adapter_type:
            raise TypeError(f"{label} authority must be exact")
        if type(selection) is not selection_type:
            raise TypeError(f"{label} selection must be exact")
        verified = validate_selection(authority, selection)
        serialize_selection_receipt(verified)
        address = raw_get(verified, "address")
        selection_path = raw_get(address, "selection_path")
        carrier_path = raw_get(address, "carrier_path")
        raw_member = raw_get(verified, "raw_member")
        selected_value = raw_get(verified, "selected_value")
        if (
            raw_get(address, "source_id") != source_id
            or raw_get(address, "span") is not None
            or len(selection_path) != 1
            or type(selection_path[0]) is not member_step_type
            or not carrier_path
            or raw_get(carrier_path[-1], "raw_key")
            != "^.creature"
            or any(
                raw_get(step, "raw_key") == "^.creature"
                for step in carrier_path[:-1]
            )
            or type(raw_member) is not raw_member_type
            or raw_get(raw_member, "key")
            != raw_get(selection_path[0], "raw_key")
            or not raw_get(raw_member, "key").startswith("!.")
            or type(selected_value) is not str
            or selected_value != raw_get(raw_member, "value")
        ):
            raise ValueError(
                f"{label} must select one exact local ability member"
            )
        block = raw_get(
            raw_get(verified, "carrier"),
            "raw_block",
        )
        if type(block) is not raw_object_type:
            raise TypeError(f"{label} carrier block must be exact")
        block_sha = ordered_hash(block)
        if block_sha is None:
            raise ValueError(f"{label} carrier exceeds family bounds")
        step = selection_path[0]
        member_ordinal = raw_get(step, "member_ordinal")
        block_members = raw_get(block, "members")
        if (
            member_ordinal >= len(block_members)
            or block_members[member_ordinal] is not raw_member
        ):
            raise ValueError(f"{label} member ordinal is invalid")
        occurrence, occurrences = exact_occurrence(
            block,
            member_ordinal,
            raw_get(raw_member, "key"),
        )
        name = block_name(block)
        return (
            verified,
            name,
            block_sha,
            raw_get(raw_member, "key"),
            member_ordinal,
            occurrences,
            raw_get(verified, "selection_sha256"),
        )

    def reviewed_record(
        authority: SourceAuthorityAdapter,
        source: VerifiedSourceSelection,
        target: VerifiedSourceSelection,
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        (
            source,
            source_name,
            source_block_sha,
            source_key,
            source_ordinal,
            source_occurrences,
            source_value_sha,
        ) = selection_facts(authority, source, "inheritance source")
        (
            target,
            target_name,
            target_block_sha,
            target_key,
            target_ordinal,
            target_occurrences,
            target_value_sha,
        ) = selection_facts(authority, target, "inheritance target")
        if (
            source_occurrences != 1
            or target_key != source_key
            or raw_get(
                raw_get(source, "address"),
                "source_id",
            )
            != raw_get(
                raw_get(target, "address"),
                "source_id",
            )
            or source_key[2:].casefold() != target_key[2:].casefold()
            or as_reference.fullmatch(
                raw_get(source, "selected_value")
            )
            is None
            or as_reference.fullmatch(
                raw_get(target, "selected_value")
            )
            is not None
        ):
            raise ValueError(
                "reviewed inheritance source and target are inconsistent"
            )
        matched = tuple(
            record
            for record in records
            if (
                raw_get(raw_get(source, "address"), "locator"),
                source_name,
                source_block_sha,
                source_key,
                source_ordinal,
                source_value_sha,
                raw_get(raw_get(target, "address"), "locator"),
                target_name,
                target_block_sha,
                target_key,
                target_ordinal,
                target_occurrences,
                target_value_sha,
            )
            == record
        )
        if len(matched) != 1:
            raise ValueError(
                "movement inheritance is not one reviewed decision"
            )
        record = matched[0]
        serialized = {
            "schema": schema,
            "reviewer": reviewer,
            "source": {
                "sourceId": source_id,
                "locator": record[0],
                "creatureName": record[1],
                "orderedBlockSha256": record[2],
                "rawKey": record[3],
                "memberOrdinal": record[4],
                "selectionSha256": record[5],
            },
            "target": {
                "sourceId": source_id,
                "locator": record[6],
                "creatureName": record[7],
                "orderedBlockSha256": record[8],
                "rawKey": record[9],
                "memberOrdinal": record[10],
                "rawKeyOccurrences": record[11],
                "selectionSha256": record[12],
            },
        }
        return record, serialized

    def expected_digests(
        authority: SourceAuthorityAdapter,
        source: VerifiedSourceSelection,
        target: VerifiedSourceSelection,
    ) -> tuple[str, str]:
        _record, serialized = reviewed_record(authority, source, target)
        record_sha = sha256(canonical_json(serialized)).hexdigest()
        decision = {
            "schema": schema,
            "reviewer": reviewer,
            "recordSha256": record_sha,
            "sourceReceiptDigest": selection_receipt_digest(source),
            "targetReceiptDigest": selection_receipt_digest(target),
        }
        return (
            record_sha,
            sha256(canonical_json(decision)).hexdigest(),
        )

    def post_init(self: ResolvedMovementAbilityReference) -> None:
        if (
            type(self) is not binding_type
            or type(raw_get(self, "authority")) is not adapter_type
            or type(raw_get(self, "source_selection"))
            is not selection_type
            or type(raw_get(self, "target_selection"))
            is not selection_type
        ):
            raise TypeError(
                "resolved movement inheritance fields are invalid"
            )
        require_sha(
            raw_get(self, "review_record_sha256"),
            "inheritance review record digest",
        )
        require_sha(
            raw_get(self, "decision_digest"),
            "inheritance decision digest",
        )

    def validate(
        self: ResolvedMovementAbilityReference,
    ) -> None:
        post_init(self)
        expected = expected_digests(
            raw_get(self, "authority"),
            raw_get(self, "source_selection"),
            raw_get(self, "target_selection"),
        )
        if (
            raw_get(self, "review_record_sha256"),
            raw_get(self, "decision_digest"),
        ) != expected:
            raise ValueError(
                "movement inheritance review digest disagrees"
            )

    def serialize(
        self: ResolvedMovementAbilityReference,
    ) -> SerializedObject:
        validate(self)
        authority = raw_get(self, "authority")
        source_selection = raw_get(self, "source_selection")
        target_selection = raw_get(self, "target_selection")
        _record, reviewed = reviewed_record(
            authority,
            source_selection,
            target_selection,
        )
        target = target_selection
        target_address = raw_get(target, "address")
        target_block = raw_get(
            raw_get(target, "carrier"),
            "raw_block",
        )
        target_member = raw_get(target, "raw_member")
        target_path = raw_get(target_address, "selection_path")
        return {
            "targetDefinitionId": (
                f"{raw_get(target_address, 'source_id')}/verified#"
                f"{selection_receipt_digest(target)}"
            ),
            "targetSourceId": raw_get(target_address, "source_id"),
            "targetLocator": raw_get(target_address, "locator"),
            "targetCreatureName": block_name(target_block),
            "targetRawKey": raw_get(target_member, "key"),
            "targetMemberOrdinal": (
                raw_get(target_path[0], "member_ordinal")
            ),
            "targetRawValueKind": "string",
            "targetAbilitySha256": raw_get(
                target,
                "selection_sha256",
            ),
            "resolutionReason": "reviewed-as-reference",
            "review": {
                "schema": schema,
                "reviewer": reviewer,
                "recordSha256": raw_get(
                    self,
                    "review_record_sha256",
                ),
                "decisionDigest": raw_get(
                    self,
                    "decision_digest",
                ),
                "record": reviewed,
            },
            "sourceReceipt": (
                serialize_selection_receipt(source_selection)
            ),
            "targetReceipt": (
                serialize_selection_receipt(target_selection)
            ),
        }

    def bind(
        authority: SourceAuthorityAdapter,
        source_selection: VerifiedSourceSelection,
        target_selection: VerifiedSourceSelection,
        /,
    ) -> ResolvedMovementAbilityReference:
        if type(authority) is not adapter_type:
            raise TypeError(
                "bind_reviewed_movement_inheritance requires exact authority"
            )
        record_sha, decision_digest = expected_digests(
            authority,
            source_selection,
            target_selection,
        )
        result = object_new(binding_type)
        object_setattr(result, "authority", authority)
        object_setattr(result, "source_selection", source_selection)
        object_setattr(result, "target_selection", target_selection)
        object_setattr(result, "review_record_sha256", record_sha)
        object_setattr(result, "decision_digest", decision_digest)
        validate(result)
        return result

    def bind_for_source(
        authority: SourceAuthorityAdapter,
        creature_selection: VerifiedSourceSelection,
        /,
    ) -> tuple[ResolvedMovementAbilityReference, ...]:
        """Materialize every reviewed inheritance owned by one creature."""

        if type(authority) is not adapter_type:
            raise TypeError(
                "reviewed movement inheritance requires exact authority"
            )
        creature = validate_selection(authority, creature_selection)
        creature_address = raw_get(creature, "address")
        block = raw_get(creature, "selected_value")
        if type(block) is not raw_object_type:
            raise TypeError(
                "reviewed movement inheritance requires a creature block"
            )
        block_sha = ordered_hash(block)
        locator = raw_get(creature_address, "locator")
        name = block_name(block)
        owned = tuple(
            record
            for record in records
            if (
                record[0],
                record[1],
                record[2],
            )
            == (locator, name, block_sha)
        )
        result = []
        for record in owned:
            source_member = validate_selection(
                authority,
                raw_get(creature, "carrier").select(
                    (member_step_type(record[3], record[4]),)
                ),
            )
            target_root = validate_selection(
                authority,
                resolve(
                    authority,
                    address(
                        authority,
                        source_id=source_id,
                        locator=record[6],
                    ),
                ),
            )
            root_value = raw_get(target_root, "selected_value")
            if type(root_value) is not raw_object_type:
                raise ValueError(
                    "reviewed movement inheritance target is not an object"
                )

            matches: list[tuple[RawMemberStep, ...]] = []

            def visit(
                node: RawSourceObject,
                path: tuple[RawMemberStep, ...] = (),
            ) -> None:
                for ordinal, member in enumerate(
                    raw_get(node, "members")
                ):
                    step = member_step_type(
                        raw_get(member, "key"),
                        ordinal,
                    )
                    value = raw_get(member, "value")
                    if raw_get(member, "key") == "^.creature":
                        if (
                            type(value) is raw_object_type
                            and ordered_hash(value) == record[8]
                            and block_name(value) == record[7]
                        ):
                            matches.append((*path, step))
                    elif type(value) is raw_object_type:
                        visit(value, (*path, step))

            visit(root_value)
            if len(matches) != 1:
                raise ValueError(
                    "reviewed movement inheritance target is ambiguous"
                )
            target_creature = validate_selection(
                authority,
                resolve(
                    authority,
                    address(
                        authority,
                        source_id=source_id,
                        locator=record[6],
                        carrier_path=matches[0],
                    ),
                ),
            )
            target_member = validate_selection(
                authority,
                raw_get(target_creature, "carrier").select(
                    (member_step_type(record[9], record[10]),)
                ),
            )
            result.append(
                bind(authority, source_member, target_member)
            )
        return tuple(result)

    return post_init, validate, serialize, bind, bind_for_source


(
    ResolvedMovementAbilityReference.__post_init__,
    ResolvedMovementAbilityReference._validate,
    ResolvedMovementAbilityReference.as_serialized,
    bind_reviewed_movement_inheritance,
    bind_reviewed_movement_inheritance_for_source,
) = _bind_inheritance_contract(
    ResolvedMovementAbilityReference,
    SourceAuthorityAdapter,
    VerifiedSourceSelection,
    RawMemberStep,
    RawSourceMember,
    RawSourceObject,
    _ordered_source_sha256,
    _block_name,
    _exact_member_occurrence,
    _serialize_selection_receipt,
    _selection_receipt_digest,
)
del _bind_inheritance_contract


def _bind_source_contract(
    source_type: type[MovementSpeedSource],
    binding_type: type[ResolvedMovementAbilityReference],
    adapter_type: type[SourceAuthorityAdapter],
    selection_type: type[VerifiedSourceSelection],
    member_step_type: type[RawMemberStep],
    raw_member_type: type[RawSourceMember],
    raw_object_type: type[RawSourceObject],
    ordered_hash: Any,
    block_name: Any,
    binding_validate: Any,
    serialize_selection_receipt: Any,
    selection_receipt_digest: Any,
):
    """Capture the exact bounded Speed consumer contract."""

    maximum_source_bytes = 512
    maximum_path_steps = 32
    maximum_key_bytes = 128
    maximum_bindings = 16
    source_id_value = "core-mc1"
    speed_rule = ("core-mc1", "5.3")
    validate_selection = adapter_type.validate_selection
    raw_get = object.__getattribute__

    def validate(self: MovementSpeedSource) -> None:
        authority = raw_get(self, "authority")
        selection = raw_get(self, "speed_selection")
        bindings = raw_get(self, "inherited_ability_bindings")
        if type(self) is not source_type:
            raise TypeError("MovementSpeedSource must be exact")
        if type(authority) is not adapter_type:
            raise TypeError(
                "MovementSpeedSource.authority must be exact"
            )
        if type(selection) is not selection_type:
            raise TypeError(
                "MovementSpeedSource.speed_selection must be verified"
            )
        if (
            type(bindings) is not tuple
            or len(bindings) > maximum_bindings
            or any(type(item) is not binding_type for item in bindings)
        ):
            raise TypeError(
                "MovementSpeedSource inheritance bindings must be exact"
        )
        verified = validate_selection(authority, selection)
        serialize_selection_receipt(verified)
        object.__setattr__(self, "speed_selection", verified)
        address = raw_get(verified, "address")
        target_path = raw_get(address, "target_path")
        carrier_path = raw_get(address, "carrier_path")
        selection_path = raw_get(address, "selection_path")
        if (
            raw_get(address, "source_id") != source_id_value
            or raw_get(address, "span") is not None
            or len(selection_path) != 1
            or type(selection_path[0]) is not member_step_type
            or not carrier_path
            or any(
                type(step) is not member_step_type
                for step in (
                    *target_path,
                    *carrier_path,
                    *selection_path,
                )
            )
            or raw_get(carrier_path[-1], "raw_key") != "^.creature"
            or any(
                raw_get(step, "raw_key") == "^.creature"
                for step in carrier_path[:-1]
            )
            or len(
                (
                    *target_path,
                    *carrier_path,
                    *selection_path,
                )
            )
            > maximum_path_steps
            or any(
                len(raw_get(step, "raw_key").encode("utf-8"))
                > maximum_key_bytes
                for step in (
                    *target_path,
                    *carrier_path,
                    *selection_path,
                )
            )
        ):
            raise ValueError(
                "MovementSpeedSource address is outside family bounds"
            )
        block = raw_get(
            raw_get(verified, "carrier"),
            "raw_block",
        )
        block_sha = ordered_hash(block)
        if (
            type(block) is not raw_object_type
            or block_sha is None
        ):
            raise ValueError(
                "MovementSpeedSource block exceeds family bounds"
            )
        step = selection_path[0]
        member = raw_get(verified, "raw_member")
        selected_value = raw_get(verified, "selected_value")
        block_members = raw_get(block, "members")
        member_ordinal = raw_get(step, "member_ordinal")
        if (
            type(member) is not raw_member_type
            or raw_get(member, "key") != "Speed"
            or raw_get(step, "raw_key") != "Speed"
            or member_ordinal >= len(block_members)
            or block_members[member_ordinal] is not member
            or type(selected_value) is not str
            or selected_value != raw_get(member, "value")
            or not selected_value
            or selected_value != selected_value.strip()
            or len(selected_value.encode("utf-8"))
            > maximum_source_bytes
        ):
            raise ValueError(
                "MovementSpeedSource must select one exact bounded Speed"
            )
        candidates = tuple(
            index
            for index, candidate in enumerate(block_members)
            if raw_get(candidate, "key").strip() == "Speed"
        )
        if candidates != (member_ordinal,):
            raise ValueError(
                "MovementSpeedSource requires one exact Speed without "
                "key collisions"
            )
        block_name(block)
        seen_bindings = set()
        for binding in bindings:
            if raw_get(binding, "authority") is not authority:
                raise TypeError(
                    "movement inheritance belongs to another authority"
                )
            binding_validate(binding)
            digest = selection_receipt_digest(
                raw_get(binding, "source_selection")
            )
            if digest in seen_bindings:
                raise ValueError(
                    "movement inheritance bindings contain duplicates"
                )
            seen_bindings.add(digest)

    def source_id(self: MovementSpeedSource) -> str:
        selection = raw_get(self, "speed_selection")
        return raw_get(raw_get(selection, "address"), "source_id")

    def locator(self: MovementSpeedSource) -> str:
        selection = raw_get(self, "speed_selection")
        return raw_get(raw_get(selection, "address"), "locator")

    def section_id(self: MovementSpeedSource) -> str:
        selection = raw_get(self, "speed_selection")
        return raw_get(raw_get(selection, "address"), "section_id")

    def definition_id(self: MovementSpeedSource) -> str:
        return (
            f"{source_id(self)}/verified#"
            f"{selection_receipt_digest(raw_get(self, 'speed_selection'))}"
        )

    def creature_name(self: MovementSpeedSource) -> str:
        return block_name(raw_block(self))

    def raw_member(self: MovementSpeedSource) -> RawSourceMember:
        value = raw_get(
            raw_get(self, "speed_selection"),
            "raw_member",
        )
        if type(value) is not raw_member_type:
            raise ValueError("verified Speed member is unavailable")
        return value

    def raw_block(self: MovementSpeedSource) -> RawSourceObject:
        selection = raw_get(self, "speed_selection")
        carrier = raw_get(selection, "carrier")
        value = raw_get(carrier, "raw_block")
        if type(value) is not raw_object_type:
            raise ValueError("verified Speed block is unavailable")
        return value

    def source_text(self: MovementSpeedSource) -> str:
        value = raw_get(
            raw_get(self, "speed_selection"),
            "selected_value",
        )
        if type(value) is not str:
            raise ValueError("verified Speed text is unavailable")
        return value

    def ordered_block_sha256(self: MovementSpeedSource) -> str:
        value = ordered_hash(raw_block(self))
        if value is None:
            raise ValueError("verified Speed block exceeds family bounds")
        return value

    def speed_member_ordinal(self: MovementSpeedSource) -> int:
        selection = raw_get(self, "speed_selection")
        address = raw_get(selection, "address")
        path = raw_get(address, "selection_path")
        return raw_get(path[0], "member_ordinal")

    def content_path(
        self: MovementSpeedSource,
    ) -> tuple[RawMemberStep, ...]:
        selection = raw_get(self, "speed_selection")
        address = raw_get(selection, "address")
        return (
            raw_get(address, "target_path")
            + raw_get(address, "carrier_path")[:-1]
        )

    def serialize(self: MovementSpeedSource) -> SerializedObject:
        validate(self)
        return {
            "sourceId": source_id(self),
            "locator": locator(self),
            "sectionId": section_id(self),
            "definitionId": definition_id(self),
            "creatureName": creature_name(self),
            "orderedBlockSha256": ordered_block_sha256(self),
            "contentPath": [
                {
                    "rawKey": raw_get(step, "raw_key"),
                    "memberOrdinal": raw_get(
                        step,
                        "member_ordinal",
                    ),
                }
                for step in content_path(self)
            ],
            "blockMemberOrdinal": (
                raw_get(
                    raw_get(
                        raw_get(
                            raw_get(self, "speed_selection"),
                            "address",
                        ),
                        "carrier_path",
                    )[-1],
                    "member_ordinal",
                )
            ),
            "speedField": {
                "rawKey": raw_get(raw_member(self), "key"),
                "memberOrdinal": speed_member_ordinal(self),
                "sourceText": source_text(self),
                "fieldRule": {
                    "sourceId": speed_rule[0],
                    "locator": speed_rule[1],
                },
                "sourceReceipt": (
                    serialize_selection_receipt(
                        raw_get(self, "speed_selection")
                    )
                ),
            },
        }

    return (
        validate,
        source_id,
        locator,
        section_id,
        definition_id,
        creature_name,
        raw_member,
        raw_block,
        source_text,
        ordered_block_sha256,
        speed_member_ordinal,
        content_path,
        serialize,
    )


(
    MovementSpeedSource.__post_init__,
    _movement_source_id,
    _movement_locator,
    _movement_section_id,
    _movement_definition_id,
    _movement_creature_name,
    _movement_raw_member,
    _movement_raw_block,
    _movement_source_text,
    _movement_ordered_block_sha256,
    _movement_speed_member_ordinal,
    _movement_content_path,
    MovementSpeedSource.as_source_identity,
) = _bind_source_contract(
    MovementSpeedSource,
    ResolvedMovementAbilityReference,
    SourceAuthorityAdapter,
    VerifiedSourceSelection,
    RawMemberStep,
    RawSourceMember,
    RawSourceObject,
    _ordered_source_sha256,
    _block_name,
    ResolvedMovementAbilityReference._validate,
    _serialize_selection_receipt,
    _selection_receipt_digest,
)
MovementSpeedSource._validate = MovementSpeedSource.__post_init__
MovementSpeedSource.source_id = property(_movement_source_id)
MovementSpeedSource.locator = property(_movement_locator)
MovementSpeedSource.section_id = property(_movement_section_id)
MovementSpeedSource.definition_id = property(_movement_definition_id)
MovementSpeedSource.creature_name = property(_movement_creature_name)
MovementSpeedSource.raw_member = property(_movement_raw_member)
MovementSpeedSource.raw_block = property(_movement_raw_block)
MovementSpeedSource.source_text = property(_movement_source_text)
MovementSpeedSource.ordered_block_sha256 = property(
    _movement_ordered_block_sha256
)
MovementSpeedSource.speed_member_ordinal = property(
    _movement_speed_member_ordinal
)
MovementSpeedSource.content_path = property(_movement_content_path)
del _bind_source_contract
del _movement_source_id
del _movement_locator
del _movement_section_id
del _movement_definition_id
del _movement_creature_name
del _movement_raw_member
del _movement_raw_block
del _movement_source_text
del _movement_ordered_block_sha256
del _movement_speed_member_ordinal
del _movement_content_path


def _bind_provider_requirement_builder():
    reviewed = (
        (
            "creature-speed",
            "core-mc1",
            "5.3",
            "be28b67dcaa2beb364fbf5ef560176b73e752ee6b967b472dec6479583ee4f47",
        ),
        (
            "land-speed",
            "core-pc1",
            "420.4",
            "625d62f213cadf80d6dd6bff2a2b57ea558174462211db5b36f1d99891fa4433",
        ),
        (
            "burrow-speed",
            "core-pc1",
            "420.5",
            "182d265baf33de7699aac65a4d308db7b776fbbabb5a4beb8d3d13736e02c694",
        ),
        (
            "climb-speed",
            "core-pc1",
            "420.6",
            "48323d454709d0174b347c46b1ec670b5cc40f6713ec7352f75663376bcffcf5",
        ),
        (
            "fly-speed",
            "core-pc1",
            "420.7",
            "9f0ed8d31209ace931dbebf5f18814fdcb12634bbfff178c6ea298dad277a521",
        ),
        (
            "swim-speed",
            "core-pc1",
            "420.8",
            "4c0b0e8b3ee7b532e7eec15104125017c8a6c414250a98d383d804da7f063859",
        ),
        (
            "spell-fly",
            "core-pc1",
            "332.4",
            "07054029fdffbab856c39edca2046f1971c716131cf3e333da6049f2fa3dc52b",
        ),
        (
            "spell-unfettered-movement",
            "core-pc1",
            "365.1",
            "1b13d06460cc8b0841f0766fadfe8d16b43c003f6fe38458f750a952e9dbad1f",
        ),
        (
            "spell-water-walk",
            "core-pc1",
            "369.2",
            "1e6a66db4fb08fbea008e66cb2f42e51d827af456cf02737aff561a57d1e7e09",
        ),
    )
    requirement_type = RuleRequirement
    object_new = object.__new__
    object_setattr = object.__setattr__

    def materialize(
        rule_id: str,
        source_id: str,
        locator: str,
        selection_sha: str,
    ) -> RuleRequirement:
        result = object_new(requirement_type)
        object_setattr(result, "rule_id", rule_id)
        object_setattr(result, "source_id", source_id)
        object_setattr(result, "locator", locator)
        object_setattr(result, "carrier_path", ())
        object_setattr(result, "selection_path", ())
        object_setattr(result, "span", None)
        object_setattr(result, "expected_block_sha256", None)
        object_setattr(result, "expected_member_sha256", None)
        object_setattr(result, "expected_value_sha256", None)
        object_setattr(
            result,
            "expected_selection_sha256",
            selection_sha,
        )
        return result

    def reviewed_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(
            materialize(
                rule_id,
                source_id,
                locator,
                selection_sha,
            )
            for rule_id, source_id, locator, selection_sha in reviewed
        )

    return reviewed_requirements


provider_rule_requirements = _bind_provider_requirement_builder()
del _bind_provider_requirement_builder


def _bind_rule_bundle_contract(
    bundle_type: type[MovementSpeedRuleBundle],
    source_type: type[MovementSpeedSource],
    adapter_type: type[SourceAuthorityAdapter],
    receipt_type: type[VerifiedRuleReceipt],
    requirements_builder: Any,
    serialize_requirement: Any,
    serialize_rule: Any,
):
    """Capture exact provider validation beneath mutable module globals."""

    validate_rule = adapter_type.validate_rule
    require_shared = adapter_type.require_shared_authority
    resolve_rule = adapter_type.resolve_rule
    source_validate = source_type._validate
    raw_get = object.__getattribute__
    object_new = object.__new__
    object_setattr = object.__setattr__

    def validate(
        self: MovementSpeedRuleBundle,
    ) -> tuple[VerifiedRuleReceipt, ...]:
        authority = raw_get(self, "authority")
        receipts = raw_get(self, "receipts")
        if (
            type(self) is not bundle_type
            or type(authority) is not adapter_type
            or type(receipts) is not tuple
            or any(type(item) is not receipt_type for item in receipts)
        ):
            raise TypeError(
                "MovementSpeedRuleBundle fields are invalid"
            )
        requirements = requirements_builder()
        if (
            len(receipts) != len(requirements)
        ):
            raise ValueError(
                "MovementSpeedRuleBundle requirements are incomplete"
            )
        for receipt, requirement in zip(
            receipts,
            requirements,
            strict=True,
        ):
            validate_rule(authority, receipt)
            serialize_rule(receipt)
            if serialize_requirement(
                raw_get(receipt, "requirement")
            ) != serialize_requirement(requirement):
                raise ValueError(
                    "MovementSpeedRuleBundle requirement set is invalid"
                )
        return receipts

    def post_init(self: MovementSpeedRuleBundle) -> None:
        validate(self)

    def require_source(
        self: MovementSpeedRuleBundle,
        source: MovementSpeedSource,
        /,
    ) -> None:
        receipts = validate(self)
        if type(source) is not source_type:
            raise TypeError(
                "MovementSpeedRuleBundle source must be exact"
            )
        source_validate(source)
        source_authority = raw_get(source, "authority")
        authority = raw_get(self, "authority")
        if source_authority is not authority:
            raise TypeError(
                "movement source and providers require one exact authority"
            )
        require_shared(
            authority,
            raw_get(source, "speed_selection"),
            receipts,
        )

    def serialize(
        self: MovementSpeedRuleBundle,
    ) -> list[SerializedObject]:
        return [
            serialize_rule(item)
            for item in validate(self)
        ]

    def bind(
        authority: SourceAuthorityAdapter,
        /,
    ) -> MovementSpeedRuleBundle:
        if type(authority) is not adapter_type:
            raise TypeError(
                "bind_movement_speed_rules requires exact authority"
            )
        result = object_new(bundle_type)
        object_setattr(result, "authority", authority)
        object_setattr(
            result,
            "receipts",
            tuple(
                resolve_rule(authority, requirement)
                for requirement in requirements_builder()
            ),
        )
        validate(result)
        return result

    return post_init, validate, require_source, serialize, bind


(
    MovementSpeedRuleBundle.__post_init__,
    MovementSpeedRuleBundle._validate,
    MovementSpeedRuleBundle.require_source,
    MovementSpeedRuleBundle.as_serialized,
    bind_movement_speed_rules,
) = _bind_rule_bundle_contract(
    MovementSpeedRuleBundle,
    MovementSpeedSource,
    SourceAuthorityAdapter,
    VerifiedRuleReceipt,
    provider_rule_requirements,
    _serialize_rule_requirement,
    _serialize_verified_rule,
)
del _bind_rule_bundle_contract


def _bind_derivation_contract(
    source_type: type[MovementSpeedSource],
    rules_type: type[MovementSpeedRuleBundle],
    binding_type: type[ResolvedMovementAbilityReference],
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
    token_type: type[MovementSpeedToken],
    restriction_type: type[MovementTerrainRestriction],
    mode_type: type[MovementMode],
    ability_type: type[MovementAbilityReference],
    raw_object_type: type[RawSourceObject],
    raw_array_type: type[RawSourceArray],
    raw_member_type: type[RawSourceMember],
    ordered_hash: Any,
    exact_occurrence: Any,
    binding_validate: Any,
):
    """Capture the closed Speed grammar and all reviewed source productions."""

    land_mode = "land"
    special_modes = ("burrow", "climb", "fly", "swim")
    movement_modes = (land_mode, *special_modes)
    maximum_source_bytes = 512
    maximum_tokens = 16
    maximum_token_bytes = 128
    maximum_constant_spells = 32
    maximum_constant_source_bytes = 512
    maximum_integer = (1 << 63) - 1
    mode_rules = (
        ("land", "land-speed", "core-pc1", "420.4"),
        ("burrow", "burrow-speed", "core-pc1", "420.5"),
        ("climb", "climb-speed", "core-pc1", "420.6"),
        ("fly", "fly-speed", "core-pc1", "420.7"),
        ("swim", "swim-speed", "core-pc1", "420.8"),
    )
    terrain_restrictions = (
        ("burrow", "sand only", "medium-only", "medium", "sand"),
        ("burrow", "snow only", "medium-only", "medium", "snow"),
        ("climb", "ice only", "surface-only", "surface", "ice"),
    )
    local_mechanics = (
        ("earth glide", "earth-glide"),
        ("forest passage", "forest-passage"),
        ("glide", "glide"),
        ("ice stride", "ice-stride"),
        ("inflate", "inflate"),
        ("smooth swimmer", "smooth-swimmer"),
        ("swamp passage", "swamp-passage"),
        ("swiftness", "swiftness"),
        ("trackless journey", "trackless-journey"),
        ("trickster’s step", "tricksters-step"),
        ("unimpeded journey", "unimpeded-journey"),
        ("unstoppable burrow", "unstoppable-burrow"),
    )
    local_hashes = (
        (
            "earth-glide",
            (
                "48571744fedf51aa2116271abf2e6f734622cb6ea9e4b18a5dd7fdefc5387a7a",
                "751d46cf43e663ddad8cba5f7b847c247d411105ac0bcd7c7f53666c56e3a65a",
                "80b10be7899e06f05fb5b6522a53bd2ec10fd33418e2310a009105140cf48e26",
                "911dc8673da689a6b6282df19275d421ac27c47e966842e984e4bdc839d62293",
                "cc8bf3d3825c51ab9429afd8c209d46c4156c7791ee62e739445e0696a03f928",
            ),
        ),
        (
            "forest-passage",
            (
                "757708edfc3376cf7a0e3c4bbad47da49eb7db54771344c4f19151c40c460dd0",
                "7ae206161635b3e6dab2fb6ffaadbd0dca68f66c01e2ac7768b596431df36dc7",
                "90c7f09bc7b68a0c6bd334f488a67cdc42162a9f808e09de696810d92405db2b",
            ),
        ),
        (
            "glide",
            (
                "864431db43dce191453ce56a53bd984b6eaf3b02cc72bcc7ce01c82fbeb186ff",
            ),
        ),
        (
            "ice-stride",
            (
                "f6a0662b9cf7e50d0e756c059fb54a26c625f53ff2fd7cb607795ebde4043772",
            ),
        ),
        (
            "inflate",
            (
                "356f1227be5893d6882e109974b13a1da81caa916bd7bd2aecb00dc051857769",
            ),
        ),
        (
            "smooth-swimmer",
            (
                "3cd53ac0ca8c3a85681ee510e482d78a1fe676504ce666b1ccb7ced49ac51d79",
            ),
        ),
        (
            "swamp-passage",
            (
                "23c47648dad31608364a3baa68b1d2cccbbd87255bccfc2c7589b11ff71c1476",
                "cf3bced6827713fec08c749913953e4e9243bc04ff8a0dcfccda22845f585426",
            ),
        ),
        (
            "swiftness",
            (
                "8afde3fa4127e9eec6b09985fc01e203222a957e5d6642a686e388826600d2dc",
                "8eb08a79b3056b2beb3616c210f745bdb6485abc83b46bf7691bf157b7871176",
            ),
        ),
        (
            "trackless-journey",
            (
                "3c8923a5a3f0ba531cdae66158acf6fd1e695a8ac7a3f0dd5f169e65edf53cc6",
                "8b32a75563ae20285eb6256d4b63f1ce301f251e56a122d2ec6d91651b18b24f",
            ),
        ),
        (
            "tricksters-step",
            (
                "7cde159e2ad3d7ed0ed661c3dc158acfd806a8967b886f65372a13e6f626176d",
            ),
        ),
        (
            "unimpeded-journey",
            (
                "06e0822bf8b32797f1b5e7be26a6cf17648e2fffe91261d1ff3718786f902745",
            ),
        ),
        (
            "unstoppable-burrow",
            (
                "420955f41d46a0f9f7cd61ec65a97d6a41ecbdac017a53af8b9f1de65324d7dd",
            ),
        ),
    )
    constant_rules = (
        ("fly", "fly", "spell-fly", "core-pc1", "332.4"),
        (
            "unfettered movement",
            "unfettered-movement",
            "spell-unfettered-movement",
            "core-pc1",
            "365.1",
        ),
        (
            "water walk",
            "water-walk",
            "spell-water-walk",
            "core-pc1",
            "369.2",
        ),
    )
    innate_fields = (
        "Arcane Innate Spells",
        "Divine Innate Spells",
        "Occult Innate Spells",
        "Primal Innate Spells",
    )
    numeric_speed = re.compile(
        r"^(?:(?P<mode>[A-Za-z]+) )?"
        r"(?P<feet>[0-9]+) feet"
        r"(?: \((?P<restriction>[^()]*)\))?$",
        re.ASCII,
    )
    plain_reference = re.compile(
        r"^[A-Za-z][A-Za-z'’ -]*$",
        re.ASCII,
    )
    italic_reference = re.compile(
        r"^<i>(?P<label>[A-Za-z][A-Za-z'’ -]*)</i>$",
        re.ASCII,
    )
    as_reference = re.compile(r"^As [^\n]+\.$")
    constant_rank = re.compile(
        r"^Constant "
        r"\((?:1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\)$",
        re.ASCII,
    )
    json_dumps = json.dumps
    sha256 = hashlib.sha256
    source_validate = source_type._validate
    rules_require_source = rules_type.require_source
    source_text = source_type.source_text.fget
    source_raw_block = source_type.raw_block.fget
    source_id = source_type.source_id.fget
    source_locator = source_type.locator.fget
    object_new = object.__new__
    object_setattr = object.__setattr__
    raw_get = object.__getattribute__

    def make_token(
        source_text_value: str,
        separator_after: str | None,
    ) -> MovementSpeedToken:
        result = object_new(token_type)
        object_setattr(result, "source_text", source_text_value)
        object_setattr(result, "separator_after", separator_after)
        return result

    def make_restriction(
        restriction_kind: str,
        fact_name: str,
        fact_value: str,
    ) -> MovementTerrainRestriction:
        result = object_new(restriction_type)
        object_setattr(result, "restriction_type", restriction_kind)
        object_setattr(result, "fact_name", fact_name)
        object_setattr(result, "fact_value", fact_value)
        return result

    def make_mode(
        mode: str,
        feet: int,
        source_text_value: str,
        source_token: int,
        restriction: MovementTerrainRestriction | None,
        provider_rule_id: str,
    ) -> MovementMode:
        result = object_new(mode_type)
        object_setattr(result, "mode", mode)
        object_setattr(result, "feet", feet)
        object_setattr(result, "source_text", source_text_value)
        object_setattr(result, "source_token", source_token)
        object_setattr(result, "restriction", restriction)
        object_setattr(result, "provider_rule_id", provider_rule_id)
        return result

    def make_ability(
        *,
        ability_id: str,
        label: str,
        authority_kind: str,
        mechanic_id: str,
        source_text_value: str,
        source_token: int,
        markup: str,
        authority_json_value: str,
        rule_source_id: str,
        rule_locator: str,
        provider_rule_id: str | None,
        inherited_target: ResolvedMovementAbilityReference | None,
    ) -> MovementAbilityReference:
        result = object_new(ability_type)
        object_setattr(result, "ability_id", ability_id)
        object_setattr(result, "label", label)
        object_setattr(result, "authority_kind", authority_kind)
        object_setattr(result, "mechanic_id", mechanic_id)
        object_setattr(result, "source_text", source_text_value)
        object_setattr(result, "source_token", source_token)
        object_setattr(result, "markup", markup)
        object_setattr(result, "authority_json", authority_json_value)
        object_setattr(result, "rule_source_id", rule_source_id)
        object_setattr(result, "rule_locator", rule_locator)
        object_setattr(result, "provider_rule_id", provider_rule_id)
        object_setattr(result, "inherited_target", inherited_target)
        return result

    def normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    def parse_integer(value: str) -> int | None:
        if (
            type(value) is not str
            or not value
            or len(value) > 19
            or any(character not in "0123456789" for character in value)
        ):
            return None
        result = int(value)
        return result if result <= maximum_integer else None

    def provider_spec(rule_id: str) -> tuple[str, str]:
        for _mode, candidate, source_id, locator in mode_rules:
            if candidate == rule_id:
                return source_id, locator
        for (
            _label,
            _mechanic,
            candidate,
            source_id,
            locator,
        ) in constant_rules:
            if candidate == rule_id:
                return source_id, locator
        if rule_id == "creature-speed":
            return "core-mc1", "5.3"
        raise ValueError("movement provider rule id is invalid")

    def authority_json(value: dict[str, Any]) -> str:
        return json_dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def raw_kind(value: RawSourceValue) -> str:
        if type(value) is raw_object_type:
            return "object"
        if type(value) is raw_array_type:
            return "array"
        if value is None:
            return "null"
        if type(value) is bool:
            return "boolean"
        if type(value) in (int, float):
            return "number"
        if type(value) is str:
            return "string"
        raise TypeError("movement source value kind is invalid")

    def tokenize(value: str) -> tuple[MovementSpeedToken, ...] | None:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or len(value.encode("utf-8")) > maximum_source_bytes
        ):
            return None
        raw_tokens: list[tuple[str, str | None]] = []
        start = 0
        depth = 0
        for index, character in enumerate(value):
            if character == "(":
                depth += 1
                if depth > 1:
                    return None
            elif character == ")":
                depth -= 1
                if depth < 0:
                    return None
            elif character in ",;" and depth == 0:
                raw_tokens.append((value[start:index].strip(), character))
                start = index + 1
        if depth:
            return None
        raw_tokens.append((value[start:].strip(), None))
        if (
            len(raw_tokens) > maximum_tokens
            or any(
                not token
                or len(token.encode("utf-8")) > maximum_token_bytes
                for token, _separator in raw_tokens
            )
        ):
            return None
        return tuple(
            make_token(token, separator)
            for token, separator in raw_tokens
        )

    def local_index(
        block: RawSourceObject,
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        candidates: dict[str, list[tuple[int, RawSourceMember]]] = {}
        for index, member in enumerate(raw_get(block, "members")):
            raw_key = raw_get(member, "key")
            if (
                type(member) is not raw_member_type
                or not raw_key.startswith("!.")
            ):
                continue
            label = raw_key[2:]
            if (
                not label
                or label != label.strip()
                or len(label.encode("utf-8")) > maximum_token_bytes
            ):
                continue
            normalized = normalize(label)
            members = candidates.get(normalized)
            if members is None:
                members = []
                candidates[normalized] = members
            members.append((index, member))
        result = {}
        for normalized, members in candidates.items():
            count = len(members)
            result[normalized] = tuple(
                (
                    raw_get(member, "key")[2:],
                    member,
                    index,
                    occurrence,
                    count,
                )
                for occurrence, (index, member) in enumerate(members)
            )
        return result

    def constant_index(
        block: RawSourceObject,
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        result: dict[str, list[tuple[Any, ...]]] = {}
        block_members = raw_get(block, "members")
        spellcasting_indices = tuple(
            index
            for index, member in enumerate(block_members)
            if raw_get(member, "key").strip() == "Spellcasting"
        )
        if (
            len(spellcasting_indices) != 1
            or raw_get(
                block_members[spellcasting_indices[0]],
                "key",
            )
            != "Spellcasting"
        ):
            return {}
        spellcasting_index = spellcasting_indices[0]
        spellcasting = raw_get(
            block_members[spellcasting_index],
            "value",
        )
        spellcasting_members = (
            raw_get(spellcasting, "members")
            if type(spellcasting) is raw_object_type
            else ()
        )
        if (
            type(spellcasting) is not raw_object_type
            or len(spellcasting_members) > 32
        ):
            return {}
        tradition_counts: dict[str, int] = {}
        for member in spellcasting_members:
            key = raw_get(member, "key")
            tradition_counts[key] = tradition_counts.get(key, 0) + 1
        for tradition_index, tradition in enumerate(
            spellcasting_members
        ):
            tradition_key = raw_get(tradition, "key")
            tradition_value = raw_get(tradition, "value")
            tradition_members = (
                raw_get(tradition_value, "members")
                if type(tradition_value) is raw_object_type
                else ()
            )
            if (
                tradition_key not in innate_fields
                or tradition_counts[tradition_key] != 1
                or type(tradition_value) is not raw_object_type
                or len(tradition_members) > 32
            ):
                continue
            entry_indices = tuple(
                index
                for index, member in enumerate(tradition_members)
                if raw_get(member, "key").strip() == "Entries"
            )
            if (
                len(entry_indices) != 1
                or raw_get(
                    tradition_members[entry_indices[0]],
                    "key",
                )
                != "Entries"
                or type(
                    raw_get(
                        tradition_members[entry_indices[0]],
                        "value",
                    )
                )
                is not raw_object_type
            ):
                continue
            entries_index = entry_indices[0]
            entries = raw_get(
                tradition_members[entries_index],
                "value",
            )
            entries_members = raw_get(entries, "members")
            if len(entries_members) > 64:
                continue
            rank_counts: dict[str, int] = {}
            for member in entries_members:
                key = raw_get(member, "key")
                rank_counts[key] = rank_counts.get(key, 0) + 1
            for rank_index, rank in enumerate(entries_members):
                rank_key = raw_get(rank, "key")
                rank_value = raw_get(rank, "value")
                if (
                    constant_rank.fullmatch(rank_key) is None
                    or rank_counts[rank_key] != 1
                ):
                    continue
                if type(rank_value) is str:
                    values = (rank_value,)
                elif (
                    type(rank_value) is raw_array_type
                    and len(raw_get(rank_value, "items"))
                    <= maximum_constant_spells
                    and all(
                        type(item) is str
                        for item in raw_get(rank_value, "items")
                    )
                ):
                    values = raw_get(rank_value, "items")
                else:
                    continue
                if any(
                    len(value.encode("utf-8"))
                    > maximum_constant_source_bytes
                    or italic_reference.fullmatch(value) is None
                    for value in values
                ):
                    continue
                for value_index, value in enumerate(values):
                    match = italic_reference.fullmatch(value)
                    label = match.group("label")
                    path = (
                        ("Spellcasting", spellcasting_index),
                        (tradition_key, tradition_index),
                        ("Entries", entries_index),
                        (rank_key, rank_index),
                    )
                    if type(rank_value) is raw_array_type:
                        path = (*path, ("$index", value_index))
                    normalized = normalize(label)
                    candidates = result.get(normalized)
                    if candidates is None:
                        candidates = []
                        result[normalized] = candidates
                    candidates.append(
                        (label, value, path, 0)
                    )
        return {key: tuple(values) for key, values in result.items()}

    def reference_label(token: str) -> tuple[str, str] | None:
        italic = italic_reference.fullmatch(token)
        if italic is not None:
            return italic.group("label"), "italic"
        if (
            "<" in token
            or ">" in token
            or plain_reference.fullmatch(token) is None
        ):
            return None
        return token, "plain"

    def parse_mode(
        token: MovementSpeedToken,
        token_index: int,
    ) -> MovementMode | None:
        token_source_text = raw_get(token, "source_text")
        match = numeric_speed.fullmatch(token_source_text)
        if match is None:
            return None
        raw_mode = match.group("mode")
        if raw_mode is None:
            if token_index != 0:
                return None
            mode = land_mode
        else:
            mode = normalize(raw_mode)
            if mode not in special_modes:
                return None
        feet = parse_integer(match.group("feet"))
        if feet is None or feet <= 0 or feet % 5:
            return None
        restriction = None
        restriction_text = match.group("restriction")
        if restriction_text is not None:
            matches = tuple(
                item
                for item in terrain_restrictions
                if item[0] == mode
                and item[1] == normalize(restriction_text)
            )
            if len(matches) != 1:
                return None
            item = matches[0]
            restriction = make_restriction(
                item[2],
                item[3],
                item[4],
            )
        rule_id = next(
            item[1] for item in mode_rules if item[0] == mode
        )
        return make_mode(
            mode,
            feet,
            token_source_text,
            token_index,
            restriction,
            rule_id,
        )

    def same_carrier(
        first: VerifiedSourceSelection,
        second: VerifiedSourceSelection,
    ) -> bool:
        def path_facts(path: object) -> tuple[tuple[Any, ...], ...]:
            if type(path) is not tuple:
                return ()
            return tuple(
                (
                    "member",
                    raw_get(step, "raw_key"),
                    raw_get(step, "member_ordinal"),
                )
                if type(step) is member_step_type
                else (
                    "index",
                    raw_get(step, "item_ordinal"),
                )
                for step in path
            )

        first_address = raw_get(first, "address")
        second_address = raw_get(second, "address")
        return (
            (
                raw_get(first_address, "source_id"),
                raw_get(first_address, "locator"),
                raw_get(first_address, "section_id"),
                path_facts(raw_get(first_address, "target_path")),
                path_facts(raw_get(first_address, "carrier_path")),
                raw_get(raw_get(first, "carrier"), "block_sha256"),
            )
            == (
                raw_get(second_address, "source_id"),
                raw_get(second_address, "locator"),
                raw_get(second_address, "section_id"),
                path_facts(raw_get(second_address, "target_path")),
                path_facts(raw_get(second_address, "carrier_path")),
                raw_get(raw_get(second, "carrier"), "block_sha256"),
            )
        )

    def binding_index(
        source: MovementSpeedSource,
    ) -> dict[tuple[str, int], ResolvedMovementAbilityReference] | None:
        result = {}
        for binding in raw_get(
            source,
            "inherited_ability_bindings",
        ):
            binding_validate(binding)
            selected = raw_get(binding, "source_selection")
            if (
                raw_get(binding, "authority")
                is not raw_get(source, "authority")
                or not same_carrier(
                    selected,
                    raw_get(source, "speed_selection"),
                )
            ):
                return None
            selected_address = raw_get(selected, "address")
            step = raw_get(selected_address, "selection_path")[0]
            selected_member = raw_get(selected, "raw_member")
            occurrence, _count = exact_occurrence(
                source_raw_block(source),
                raw_get(step, "member_ordinal"),
                raw_get(selected_member, "key"),
            )
            key = (raw_get(selected_member, "key"), occurrence)
            if key in result:
                return None
            result[key] = binding
        return result

    def compile_local(
        source: MovementSpeedSource,
        token: MovementSpeedToken,
        token_index: int,
        label: str,
        markup: str,
        authority: tuple[Any, ...],
        bindings: dict[
            tuple[str, int],
            ResolvedMovementAbilityReference,
        ],
        used_bindings: set[tuple[str, int]],
    ) -> MovementAbilityReference | None:
        normalized = normalize(label)
        mechanic_matches = tuple(
            mechanic
            for candidate, mechanic in local_mechanics
            if candidate == normalized
        )
        if len(mechanic_matches) != 1:
            return None
        mechanic_id = mechanic_matches[0]
        raw_label, member, member_ordinal, occurrence, occurrences = authority
        member_value = raw_get(member, "value")
        member_key = raw_get(member, "key")
        source_sha = ordered_hash(member_value)
        allowed_hashes = next(
            hashes
            for candidate, hashes in local_hashes
            if candidate == mechanic_id
        )
        if source_sha is None or source_sha not in allowed_hashes:
            return None
        binding_key = (member_key, occurrence)
        binding = bindings.get(binding_key)
        inherited = (
            type(member_value) is str
            and as_reference.fullmatch(member_value) is not None
        )
        if inherited:
            if binding is None:
                return None
            binding_validate(binding)
            source_selection = raw_get(binding, "source_selection")
            source_step = raw_get(
                raw_get(source_selection, "address"),
                "selection_path",
            )[0]
            source_selection_member = raw_get(
                source_selection,
                "raw_member",
            )
            if (
                raw_get(source_step, "member_ordinal") != member_ordinal
                or raw_get(source_selection_member, "key") != member_key
                or ordered_hash(
                    raw_get(source_selection_member, "value")
                )
                != source_sha
                or raw_get(source_selection, "selection_sha256")
                != source_sha
                or normalize(
                    raw_get(
                        raw_get(
                            raw_get(binding, "target_selection"),
                            "raw_member",
                        ),
                        "key",
                    )[2:]
                )
                != normalized
            ):
                return None
            used_bindings.add(binding_key)
        elif binding is not None:
            return None
        proof = authority_json(
            {
                "rawKey": member_key,
                "rawKeyOccurrence": occurrence,
                "rawKeyOccurrences": occurrences,
                "topLevelMemberOrdinal": member_ordinal,
                "rawValueKind": raw_kind(member_value),
                "orderedSourceSha256": source_sha,
            }
        )
        return make_ability(
            ability_id=mechanic_id,
            label=label,
            authority_kind="local-ability",
            mechanic_id=mechanic_id,
            source_text_value=raw_get(token, "source_text"),
            source_token=token_index,
            markup=markup,
            authority_json_value=proof,
            rule_source_id=source_id(source),
            rule_locator=source_locator(source),
            provider_rule_id=None,
            inherited_target=binding,
        )

    def compile_constant(
        token: MovementSpeedToken,
        token_index: int,
        label: str,
        markup: str,
        authority: tuple[Any, ...],
    ) -> MovementAbilityReference | None:
        normalized = normalize(label)
        matches = tuple(
            item for item in constant_rules if item[0] == normalized
        )
        if len(matches) != 1:
            return None
        (
            _normalized,
            mechanic_id,
            provider_rule_id,
            rule_source_id,
            rule_locator,
        ) = matches[0]
        raw_label, source_value, field_path, italic_occurrence = authority
        if normalize(raw_label) != normalized:
            return None
        proof = authority_json(
            {
                "fieldPath": [
                    {
                        "rawKey": raw_key,
                        "memberOrdinal": ordinal,
                    }
                    for raw_key, ordinal in field_path
                ],
                "sourceValue": source_value,
                "sourceValueSha256": sha256(
                    source_value.encode("utf-8")
                ).hexdigest(),
                "italicOccurrence": italic_occurrence,
            }
        )
        return make_ability(
            ability_id=mechanic_id,
            label=label,
            authority_kind="constant-spell",
            mechanic_id=mechanic_id,
            source_text_value=raw_get(token, "source_text"),
            source_token=token_index,
            markup=markup,
            authority_json_value=proof,
            rule_source_id=rule_source_id,
            rule_locator=rule_locator,
            provider_rule_id=provider_rule_id,
            inherited_target=None,
        )

    def derive(
        source: MovementSpeedSource,
        rules: MovementSpeedRuleBundle,
    ) -> tuple[
        tuple[MovementSpeedToken, ...],
        tuple[MovementMode, ...],
        tuple[MovementAbilityReference, ...],
        tuple[str, ...],
    ] | None:
        if type(source) is not source_type or type(rules) is not rules_type:
            return None
        source_validate(source)
        rules_require_source(rules, source)
        tokens = tokenize(source_text(source))
        if tokens is None:
            return None
        local = local_index(source_raw_block(source))
        constants = constant_index(source_raw_block(source))
        bindings = binding_index(source)
        if bindings is None:
            return None
        modes = []
        abilities = []
        seen_modes = set()
        seen_references = set()
        used_bindings = set()
        seen_reference = False
        for token_index, token in enumerate(tokens):
            token_source_text = raw_get(token, "source_text")
            if numeric_speed.fullmatch(token_source_text) is not None:
                if seen_reference:
                    return None
                mode = parse_mode(token, token_index)
                if (
                    mode is None
                    or raw_get(mode, "mode") in seen_modes
                ):
                    return None
                seen_modes.add(raw_get(mode, "mode"))
                modes.append(mode)
                continue
            seen_reference = True
            parsed = reference_label(token_source_text)
            if parsed is None:
                return None
            label, markup = parsed
            normalized = normalize(label)
            local_matches = local.get(normalized, ())
            constant_matches = constants.get(normalized, ())
            if (
                len(local_matches) > 1
                or len(constant_matches) > 1
                or (local_matches and constant_matches)
                or (not local_matches and not constant_matches)
            ):
                return None
            authority_kind = (
                "local-ability"
                if local_matches
                else "constant-spell"
            )
            identity = (authority_kind, normalized)
            if identity in seen_references:
                return None
            seen_references.add(identity)
            if local_matches:
                ability = compile_local(
                    source,
                    token,
                    token_index,
                    label,
                    markup,
                    local_matches[0],
                    bindings,
                    used_bindings,
                )
            else:
                ability = compile_constant(
                    token,
                    token_index,
                    label,
                    markup,
                    constant_matches[0],
                )
            if ability is None:
                return None
            abilities.append(ability)
        if not modes or used_bindings != set(bindings):
            return None
        deferred = ["movement-service-integration"]
        deferred.extend(
            f"movement-mode:{raw_get(mode, 'mode')}"
            for mode in modes
            if raw_get(mode, "mode") != land_mode
        )
        deferred.extend(
            f"movement-ability:{raw_get(ability, 'mechanic_id')}"
            for ability in abilities
        )
        return (
            tuple(tokens),
            tuple(modes),
            tuple(abilities),
            tuple(deferred),
        )

    return (
        movement_modes,
        mode_rules,
        constant_rules,
        terrain_restrictions,
        provider_spec,
        tokenize,
        derive,
    )


(
    _CANONICAL_MOVEMENT_MODES,
    _CANONICAL_MODE_RULES,
    _CANONICAL_CONSTANT_RULES,
    _CANONICAL_TERRAIN_RESTRICTIONS,
    _provider_rule_spec,
    _tokenize,
    _derive_movement_speeds,
) = _bind_derivation_contract(
    MovementSpeedSource,
    MovementSpeedRuleBundle,
    ResolvedMovementAbilityReference,
    RawMemberStep,
    RawIndexStep,
    MovementSpeedToken,
    MovementTerrainRestriction,
    MovementMode,
    MovementAbilityReference,
    RawSourceObject,
    RawSourceArray,
    RawSourceMember,
    _ordered_source_sha256,
    _exact_member_occurrence,
    ResolvedMovementAbilityReference._validate,
)
del _bind_derivation_contract


def _bind_public_movement_contract(
    source_type: type[MovementSpeedSource],
    rules_type: type[MovementSpeedRuleBundle],
    binding_type: type[ResolvedMovementAbilityReference],
    token_type: type[MovementSpeedToken],
    restriction_type: type[MovementTerrainRestriction],
    mode_type: type[MovementMode],
    ability_type: type[MovementAbilityReference],
    patch_type: type[MovementSpeedPatch],
    movement_modes: tuple[str, ...],
    mode_rules: tuple[tuple[str, str, str, str], ...],
    constant_rules: tuple[tuple[str, str, str, str, str], ...],
    terrain_restrictions: tuple[
        tuple[str, str, str, str, str],
        ...,
    ],
    provider_spec: Any,
    derive: Any,
):
    """Bind all public projections to one private canonical derivation."""

    maximum_identifier_bytes = 4_096
    maximum_token_bytes = 128
    maximum_tokens = 16
    maximum_source_members = 256
    maximum_path_steps = 32
    maximum_constant_source_bytes = 512
    maximum_integer = (1 << 63) - 1
    source_id_value = "core-mc1"
    allowed_separators = (None, ",", ";")
    allowed_markups = ("plain", "italic")
    allowed_authority_kinds = ("local-ability", "constant-spell")
    allowed_raw_kinds = (
        "array",
        "boolean",
        "null",
        "number",
        "object",
        "string",
    )
    local_mechanics = (
        "earth-glide",
        "forest-passage",
        "glide",
        "ice-stride",
        "inflate",
        "smooth-swimmer",
        "swamp-passage",
        "swiftness",
        "trackless-journey",
        "tricksters-step",
        "unimpeded-journey",
        "unstoppable-burrow",
    )
    restriction_specs = tuple(
        (mode, restriction_kind, fact_name, fact_value)
        for (
            mode,
            _source_text,
            restriction_kind,
            fact_name,
            fact_value,
        ) in terrain_restrictions
    )
    mode_rule_specs = tuple(
        (mode, rule_id, rule_source_id, rule_locator)
        for mode, rule_id, rule_source_id, rule_locator in mode_rules
    )
    constant_rule_specs = tuple(
        (
            mechanic_id,
            rule_id,
            rule_source_id,
            rule_locator,
        )
        for (
            _label,
            mechanic_id,
            rule_id,
            rule_source_id,
            rule_locator,
        ) in constant_rules
    )
    source_validate = source_type._validate
    source_serialize = source_type.as_source_identity
    rules_require_source = rules_type.require_source
    rules_serialize = rules_type.as_serialized
    binding_validate = binding_type._validate
    binding_serialize = binding_type.as_serialized
    json_loads = json.loads
    json_dumps = json.dumps
    sha256 = hashlib.sha256
    raw_get = object.__getattribute__
    object_new = object.__new__
    object_setattr = object.__setattr__

    def make_patch(
        source: MovementSpeedSource,
        rules: MovementSpeedRuleBundle,
        tokens: tuple[MovementSpeedToken, ...],
        modes: tuple[MovementMode, ...],
        abilities: tuple[MovementAbilityReference, ...],
        deferred: tuple[str, ...],
    ) -> MovementSpeedPatch:
        result = object_new(patch_type)
        object_setattr(result, "source", source)
        object_setattr(result, "rules", rules)
        object_setattr(result, "tokens", tokens)
        object_setattr(result, "modes", modes)
        object_setattr(result, "abilities", abilities)
        object_setattr(result, "deferred_mechanics", deferred)
        return result

    def require_text(
        value: object,
        label: str,
        /,
        *,
        maximum_bytes: int = maximum_identifier_bytes,
    ) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or len(value.encode("utf-8")) > maximum_bytes
        ):
            raise ValueError(
                f"{label} must be a bounded non-empty trimmed string"
            )
        return value

    def require_index(
        value: object,
        label: str,
        /,
        *,
        upper_bound: int = maximum_integer,
    ) -> int:
        if (
            type(value) is not int
            or value < 0
            or value > upper_bound
        ):
            raise ValueError(
                f"{label} must be a bounded nonnegative integer"
            )
        return value

    def require_sha(value: object, label: str, /) -> str:
        if (
            type(value) is not str
            or len(value) != 64
            or any(
                character not in "0123456789abcdef"
                for character in value
            )
        ):
            raise ValueError(f"{label} must be a lowercase SHA-256")
        return value

    def canonical_json(value: object, /) -> str:
        return json_dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def parse_authority_json(value: object, /) -> dict[str, Any]:
        require_text(value, "movement ability authority JSON")
        try:
            parsed = json_loads(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "movement ability authority JSON is invalid"
            ) from error
        if type(parsed) is not dict or canonical_json(parsed) != value:
            raise ValueError(
                "movement ability authority JSON is not canonical"
            )
        return parsed

    def validate_token(self: MovementSpeedToken) -> None:
        if type(self) is not token_type:
            raise TypeError("MovementSpeedToken must be exact")
        require_text(
            raw_get(self, "source_text"),
            "MovementSpeedToken.source_text",
            maximum_bytes=maximum_token_bytes,
        )
        if raw_get(self, "separator_after") not in allowed_separators:
            raise ValueError(
                "MovementSpeedToken.separator_after is invalid"
            )

    def serialize_token(
        self: MovementSpeedToken,
    ) -> SerializedObject:
        validate_token(self)
        return {
            "sourceText": raw_get(self, "source_text"),
            "separatorAfter": raw_get(self, "separator_after"),
        }

    def validate_restriction(
        self: MovementTerrainRestriction,
    ) -> None:
        if type(self) is not restriction_type:
            raise TypeError("MovementTerrainRestriction must be exact")
        actual = (
            raw_get(self, "restriction_type"),
            raw_get(self, "fact_name"),
            raw_get(self, "fact_value"),
        )
        if actual not in tuple(item[1:] for item in restriction_specs):
            raise ValueError(
                "MovementTerrainRestriction is not canonical"
            )

    def serialize_restriction(
        self: MovementTerrainRestriction,
    ) -> SerializedObject:
        validate_restriction(self)
        restriction_kind = raw_get(self, "restriction_type")
        fact_name = raw_get(self, "fact_name")
        fact_value = raw_get(self, "fact_value")
        return {
            "type": restriction_kind,
            fact_name: fact_value,
        }

    def validate_mode(self: MovementMode) -> None:
        if type(self) is not mode_type:
            raise TypeError("MovementMode must be exact")
        mode = raw_get(self, "mode")
        if type(mode) is not str or mode not in movement_modes:
            raise ValueError("MovementMode.mode is invalid")
        feet = raw_get(self, "feet")
        if (
            type(feet) is not int
            or feet <= 0
            or feet > maximum_integer
            or feet % 5
        ):
            raise ValueError(
                "MovementMode.feet must be a positive 5-foot increment"
            )
        require_text(
            raw_get(self, "source_text"),
            "MovementMode.source_text",
            maximum_bytes=maximum_token_bytes,
        )
        require_index(
            raw_get(self, "source_token"),
            "MovementMode.source_token",
            upper_bound=maximum_tokens - 1,
        )
        restriction = raw_get(self, "restriction")
        if restriction is not None:
            if type(restriction) is not restriction_type:
                raise TypeError("MovementMode.restriction is invalid")
            validate_restriction(restriction)
            fact = (
                mode,
                raw_get(restriction, "restriction_type"),
                raw_get(restriction, "fact_name"),
                raw_get(restriction, "fact_value"),
            )
            if fact not in restriction_specs:
                raise ValueError(
                    "MovementMode restriction disagrees with its mode"
                )
        matches = tuple(
            item for item in mode_rule_specs if item[0] == mode
        )
        if (
            len(matches) != 1
            or raw_get(self, "provider_rule_id") != matches[0][1]
        ):
            raise ValueError(
                "MovementMode provider rule is not canonical"
            )

    def serialize_mode(self: MovementMode) -> SerializedObject:
        validate_mode(self)
        provider_rule_id = raw_get(self, "provider_rule_id")
        restriction = raw_get(self, "restriction")
        rule_source_id, rule_locator = provider_spec(
            provider_rule_id
        )
        return {
            "feet": raw_get(self, "feet"),
            "sourceText": raw_get(self, "source_text"),
            "sourceToken": raw_get(self, "source_token"),
            "restriction": (
                serialize_restriction(restriction)
                if restriction is not None
                else None
            ),
            "providerRuleId": provider_rule_id,
            "rule": {
                "sourceId": rule_source_id,
                "locator": rule_locator,
            },
        }

    def validate_local_authority(
        self: MovementAbilityReference,
        authority: dict[str, Any],
    ) -> None:
        if set(authority) != {
            "rawKey",
            "rawKeyOccurrence",
            "rawKeyOccurrences",
            "topLevelMemberOrdinal",
            "rawValueKind",
            "orderedSourceSha256",
        }:
            raise ValueError("local movement authority keys are invalid")
        raw_key = require_text(
            authority.get("rawKey"),
            "local movement authority raw key",
            maximum_bytes=maximum_token_bytes,
        )
        occurrence = require_index(
            authority.get("rawKeyOccurrence"),
            "local movement authority occurrence",
            upper_bound=maximum_source_members - 1,
        )
        occurrences = authority.get("rawKeyOccurrences")
        if (
            type(occurrences) is not int
            or occurrences <= 0
            or occurrences > maximum_source_members
            or occurrence >= occurrences
        ):
            raise ValueError(
                "local movement authority occurrence count is invalid"
            )
        require_index(
            authority.get("topLevelMemberOrdinal"),
            "local movement authority member ordinal",
            upper_bound=maximum_source_members - 1,
        )
        if (
            not raw_key.startswith("!.")
            or raw_key[2:].casefold()
            != raw_get(self, "label").casefold()
            or authority.get("rawValueKind") not in allowed_raw_kinds
        ):
            raise ValueError("local movement authority is inconsistent")
        require_sha(
            authority.get("orderedSourceSha256"),
            "local movement authority source digest",
        )
        if (
            raw_get(self, "ability_id") not in local_mechanics
            or raw_get(self, "mechanic_id")
            != raw_get(self, "ability_id")
            or raw_get(self, "rule_source_id") != source_id_value
            or raw_get(self, "provider_rule_id") is not None
        ):
            raise ValueError(
                "local movement ability rule identity is invalid"
            )
        inherited = raw_get(self, "inherited_target")
        if inherited is not None:
            if type(inherited) is not binding_type:
                raise TypeError(
                    "local movement inherited target is invalid"
                )
            binding_validate(inherited)

    def validate_constant_authority(
        self: MovementAbilityReference,
        authority: dict[str, Any],
    ) -> None:
        if set(authority) != {
            "fieldPath",
            "sourceValue",
            "sourceValueSha256",
            "italicOccurrence",
        }:
            raise ValueError(
                "constant-spell movement authority keys are invalid"
            )
        path = authority.get("fieldPath")
        if (
            type(path) is not list
            or not path
            or len(path) > maximum_path_steps
        ):
            raise ValueError(
                "constant-spell movement field path is invalid"
            )
        for index, step in enumerate(path):
            if type(step) is not dict or set(step) != {
                "rawKey",
                "memberOrdinal",
            }:
                raise ValueError(
                    "constant-spell movement path step is invalid"
                )
            raw_key = require_text(
                step.get("rawKey"),
                "constant-spell movement path key",
                maximum_bytes=maximum_token_bytes,
            )
            require_index(
                step.get("memberOrdinal"),
                "constant-spell movement path ordinal",
                upper_bound=maximum_integer,
            )
            if raw_key == "$index" and index != len(path) - 1:
                raise ValueError(
                    "constant-spell array index must terminate its path"
                )
        source_value = require_text(
            authority.get("sourceValue"),
            "constant-spell movement source value",
            maximum_bytes=maximum_constant_source_bytes,
        )
        if (
            not source_value.startswith("<i>")
            or not source_value.endswith("</i>")
            or " ".join(source_value[3:-4].casefold().split())
            != " ".join(raw_get(self, "label").casefold().split())
            or authority.get("italicOccurrence") != 0
            or authority.get("sourceValueSha256")
            != sha256(source_value.encode("utf-8")).hexdigest()
            or raw_get(self, "inherited_target") is not None
            or raw_get(self, "ability_id")
            != raw_get(self, "mechanic_id")
        ):
            raise ValueError(
                "constant-spell movement authority is inconsistent"
            )
        matches = tuple(
            item
            for item in constant_rule_specs
            if item[0] == raw_get(self, "mechanic_id")
        )
        if (
            len(matches) != 1
            or (
                raw_get(self, "provider_rule_id"),
                raw_get(self, "rule_source_id"),
                raw_get(self, "rule_locator"),
            )
            != matches[0][1:]
        ):
            raise ValueError(
                "constant-spell movement provider is invalid"
            )

    def validate_ability(self: MovementAbilityReference) -> None:
        if type(self) is not ability_type:
            raise TypeError("MovementAbilityReference must be exact")
        for field_name in (
            "ability_id",
            "label",
            "mechanic_id",
            "source_text",
            "rule_source_id",
            "rule_locator",
        ):
            require_text(
                raw_get(self, field_name),
                f"MovementAbilityReference.{field_name}",
            )
        if raw_get(self, "authority_kind") not in (
            allowed_authority_kinds
        ):
            raise ValueError(
                "MovementAbilityReference.authority_kind is invalid"
            )
        if raw_get(self, "markup") not in allowed_markups:
            raise ValueError(
                "MovementAbilityReference.markup is invalid"
            )
        require_index(
            raw_get(self, "source_token"),
            "MovementAbilityReference.source_token",
            upper_bound=maximum_tokens - 1,
        )
        label = raw_get(self, "label")
        markup = raw_get(self, "markup")
        expected_source = (
            label
            if markup == "plain"
            else f"<i>{label}</i>"
        )
        if raw_get(self, "source_text") != expected_source:
            raise ValueError(
                "MovementAbilityReference source text and markup disagree"
            )
        authority = parse_authority_json(
            raw_get(self, "authority_json")
        )
        if raw_get(self, "authority_kind") == "local-ability":
            validate_local_authority(self, authority)
        else:
            validate_constant_authority(self, authority)

    def serialize_ability(
        self: MovementAbilityReference,
    ) -> SerializedObject:
        validate_ability(self)
        inherited = raw_get(self, "inherited_target")
        return {
            "id": raw_get(self, "ability_id"),
            "label": raw_get(self, "label"),
            "kind": raw_get(self, "authority_kind"),
            "mechanicId": raw_get(self, "mechanic_id"),
            "sourceText": raw_get(self, "source_text"),
            "sourceToken": raw_get(self, "source_token"),
            "markup": raw_get(self, "markup"),
            "authority": parse_authority_json(
                raw_get(self, "authority_json")
            ),
            "rule": {
                "sourceId": raw_get(self, "rule_source_id"),
                "locator": raw_get(self, "rule_locator"),
                "providerRuleId": raw_get(
                    self,
                    "provider_rule_id",
                ),
            },
            "inheritedTarget": (
                binding_serialize(inherited)
                if inherited is not None
                else None
            ),
            "runtimeStatus": "deferred",
        }

    def validate_patch(self: MovementSpeedPatch) -> None:
        source = raw_get(self, "source")
        rules = raw_get(self, "rules")
        if (
            type(self) is not patch_type
            or type(source) is not source_type
            or type(rules) is not rules_type
        ):
            raise TypeError("MovementSpeedPatch source/rules are invalid")
        source_validate(source)
        rules_require_source(rules, source)
        tokens = raw_get(self, "tokens")
        modes = raw_get(self, "modes")
        abilities = raw_get(self, "abilities")
        deferred = raw_get(self, "deferred_mechanics")
        if (
            type(tokens) is not tuple
            or len(tokens) > maximum_tokens
            or any(type(item) is not token_type for item in tokens)
            or type(modes) is not tuple
            or any(type(item) is not mode_type for item in modes)
            or type(abilities) is not tuple
            or any(type(item) is not ability_type for item in abilities)
            or type(deferred) is not tuple
            or any(type(item) is not str for item in deferred)
        ):
            raise TypeError("MovementSpeedPatch fields are invalid")
        for item in tokens:
            validate_token(item)
        for item in modes:
            validate_mode(item)
        for item in abilities:
            validate_ability(item)
        for item in deferred:
            require_text(item, "MovementSpeedPatch deferred mechanic")
        expected = derive(source, rules)
        if expected is None:
            raise ValueError(
                "MovementSpeedPatch is not compiler-derived"
            )
        (
            expected_tokens,
            expected_modes,
            expected_abilities,
            expected_deferred,
        ) = expected
        actual_projection = {
            "tokens": [serialize_token(item) for item in tokens],
            "modes": [
                {
                    "mode": raw_get(item, "mode"),
                    "value": serialize_mode(item),
                }
                for item in modes
            ],
            "abilities": [
                serialize_ability(item) for item in abilities
            ],
            "deferred": list(deferred),
        }
        expected_projection = {
            "tokens": [
                serialize_token(item) for item in expected_tokens
            ],
            "modes": [
                {
                    "mode": raw_get(item, "mode"),
                    "value": serialize_mode(item),
                }
                for item in expected_modes
            ],
            "abilities": [
                serialize_ability(item)
                for item in expected_abilities
            ],
            "deferred": list(expected_deferred),
        }
        if actual_projection != expected_projection:
            raise ValueError(
                "MovementSpeedPatch is not compiler-derived"
            )

    def has_land_speed(self: MovementSpeedPatch) -> bool:
        validate_patch(self)
        return any(
            raw_get(item, "mode") == "land"
            for item in raw_get(self, "modes")
        )

    def serialize_patch(
        self: MovementSpeedPatch,
    ) -> SerializedObject:
        validate_patch(self)
        source = raw_get(self, "source")
        rules = raw_get(self, "rules")
        tokens = raw_get(self, "tokens")
        modes = raw_get(self, "modes")
        abilities = raw_get(self, "abilities")
        deferred = raw_get(self, "deferred_mechanics")
        return {
            "source": source_serialize(source),
            "providerProofs": rules_serialize(rules),
            "tokens": [serialize_token(item) for item in tokens],
            "modes": {
                raw_get(item, "mode"): serialize_mode(item)
                for item in modes
            },
            "abilities": [
                serialize_ability(item) for item in abilities
            ],
            "hasLandSpeed": any(
                raw_get(item, "mode") == "land"
                for item in modes
            ),
            "runtimeReady": False,
            "deferredMechanics": list(deferred),
        }

    def compile_family(
        source: object,
        rules: object,
        /,
    ) -> MovementSpeedPatch | None:
        if type(source) is not source_type or type(rules) is not rules_type:
            return None
        source_validate(source)
        rules_require_source(rules, source)
        derived = derive(source, rules)
        if derived is None:
            return None
        tokens, modes, abilities, deferred = derived
        result = make_patch(
            source,
            rules,
            tokens,
            modes,
            abilities,
            deferred,
        )
        validate_patch(result)
        return result

    return (
        validate_token,
        serialize_token,
        validate_restriction,
        serialize_restriction,
        validate_mode,
        serialize_mode,
        validate_ability,
        serialize_ability,
        validate_patch,
        has_land_speed,
        serialize_patch,
        compile_family,
    )


(
    MovementSpeedToken.__post_init__,
    MovementSpeedToken.as_serialized,
    MovementTerrainRestriction.__post_init__,
    MovementTerrainRestriction.as_serialized,
    MovementMode.__post_init__,
    MovementMode.as_serialized,
    MovementAbilityReference.__post_init__,
    MovementAbilityReference.as_serialized,
    MovementSpeedPatch._validate,
    _movement_has_land_speed,
    MovementSpeedPatch.as_serialized,
    compile_movement_speeds,
) = _bind_public_movement_contract(
    MovementSpeedSource,
    MovementSpeedRuleBundle,
    ResolvedMovementAbilityReference,
    MovementSpeedToken,
    MovementTerrainRestriction,
    MovementMode,
    MovementAbilityReference,
    MovementSpeedPatch,
    _CANONICAL_MOVEMENT_MODES,
    _CANONICAL_MODE_RULES,
    _CANONICAL_CONSTANT_RULES,
    _CANONICAL_TERRAIN_RESTRICTIONS,
    _provider_rule_spec,
    _derive_movement_speeds,
)
MovementSpeedPatch.__post_init__ = MovementSpeedPatch._validate
MovementSpeedPatch.has_land_speed = property(_movement_has_land_speed)
del _bind_public_movement_contract
del _movement_has_land_speed


__all__ = [
    "COMPILER_ID",
    "FAMILY_ID",
    "INHERITANCE_REVIEWER_ID",
    "INHERITANCE_REVIEW_SCHEMA",
    "LAND_MODE",
    "MAX_CONSTANT_SPELLS_PER_RANK",
    "MAX_CONSTANT_SPELL_SOURCE_BYTES",
    "MAX_CONTENT_PATH_STEPS",
    "MAX_IDENTIFIER_BYTES",
    "MAX_INHERITANCE_BINDINGS",
    "MAX_SOURCE_BLOCK_MEMBERS",
    "MAX_SOURCE_DEPTH",
    "MAX_SOURCE_INTEGER",
    "MAX_SOURCE_KEY_BYTES",
    "MAX_SOURCE_NODES",
    "MAX_SOURCE_STRING_BYTES",
    "MAX_SPEED_SOURCE_BYTES",
    "MAX_SPEED_TOKEN_BYTES",
    "MAX_SPEED_TOKENS",
    "MONSTER_CORE_SOURCE_ID",
    "MONSTER_CORE_SPEED_LOCATOR",
    "MOVEMENT_MODES",
    "MovementAbilityReference",
    "MovementMode",
    "MovementSpeedPatch",
    "MovementSpeedRuleBundle",
    "MovementSpeedSource",
    "MovementSpeedToken",
    "MovementTerrainRestriction",
    "ResolvedMovementAbilityReference",
    "SPECIAL_MODES",
    "bind_movement_speed_rules",
    "bind_reviewed_movement_inheritance",
    "bind_reviewed_movement_inheritance_for_source",
    "compile_movement_speeds",
    "provider_rule_requirements",
]

"""Compile the reviewed Core MC1 Draconic Frenzy/Momentum families.

This is a compile-only boundary.  It accepts a server-owned source-authority
adapter, an exact selected family member, exact reviewed provider receipts,
and (only when authored prose requires them) exact cross-creature reference
selections.  Creature-local Melee, Breath, and Spellcasting dependencies are
always reselected through the same adapter from the selected creature block.

No browser claim, normalized creature object, packet identity, locator-only
map, mutable registry, or caller-built local index is authoritative here.
The returned opaque patch revalidates and rederives its complete projection
on every serialization.  Runtime execution remains explicitly deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Literal, TypeAlias, final

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
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
    raw_source_sha256,
)
from .source_values import parse_decimal_integer


FAMILY_ID = "draconic-sequences"
FRENZY_COMPILER_ID = "draconic-frenzy"
FRENZY_MECHANIC_TYPE = "draconic-frenzy"
MOMENTUM_COMPILER_ID = "draconic-momentum"
MOMENTUM_MECHANIC_TYPE = "draconic-momentum"
MONSTER_CORE_SOURCE_ID = "core-mc1"
FRENZY_RAW_KEY = "!.Draconic Frenzy"
MOMENTUM_RAW_KEY = "!.Draconic Momentum"

MAX_CREATURE_MEMBERS = 4_096
MAX_MELEE_STRIKES = 16
MAX_SOURCE_TEXT_BYTES = 8_192
MAX_CREATURE_NAME_BYTES = 512
MAX_STRIKE_NAME_BYTES = 256
MAX_PROJECTION_BYTES = 2_000_000
MAX_PROJECTION_DEPTH = 128
MAX_PROJECTION_NODES = 20_000
MAX_CONTAINER_ITEMS = 4_096

_SIGNED_DECIMAL_RE = re.compile(r"^[+-](?:0|[1-9][0-9]*)$", re.ASCII)
_SPELL_SLOT_ENTRY_RE = re.compile(
    r"^(?:1st|2nd|3rd|(?:[4-9]|10)th) "
    r"\((?P<count>[1-9][0-9]*) (?P<unit>slot|slots)\)$",
    re.ASCII,
)
class DraconicCompileError(ValueError):
    """A verified family-shaped source record is unsupported or ambiguous."""


class DraconicLinkError(EngineInputError):
    """A verified local dependency cannot bind the authored family record."""


def _fresh_rule_requirements() -> tuple[
    tuple[str, RuleRequirement],
    ...,
]:
    """Rebuild every reviewed provider pin from literals."""

    return (
        (
            "activities",
            RuleRequirement(
                rule_id="activities",
                source_id="core-pc1",
                locator="414.4",
                expected_block_sha256=(
                    "6cca42e564d687b1b3fd6ce074ad87b1"
                    "a8e055f7f0dd8fe0383bad3a81e4fa1d"
                ),
            ),
        ),
        (
            "subordinate-actions",
            RuleRequirement(
                rule_id="subordinate-actions",
                source_id="core-pc1",
                locator="414.1",
                selection_path=(
                    RawMemberStep("~.aside", 9),
                    RawMemberStep("In-Depth Action Rules", 0),
                    RawMemberStep("Subordinate Actions", 2),
                ),
                expected_block_sha256=(
                    "57b6ebdb98b389cefba4727fde8d79cb2"
                    "9065e0ba1a0590a0ce95cd1f99db111"
                ),
                expected_member_sha256=(
                    "49e68c4e366f5d154418719580f8cf7c"
                    "7d7bd5f8ac43fc55efdf935614097c27"
                ),
                expected_value_sha256=(
                    "f8ca1dc227aeca2dea8d47e75a52b440"
                    "43a8c8a68931d96a19b9eade1ba3141d"
                ),
            ),
        ),
        (
            "simultaneous-actions",
            RuleRequirement(
                rule_id="simultaneous-actions",
                source_id="core-pc1",
                locator="414.1",
                selection_path=(
                    RawMemberStep("~.aside", 9),
                    RawMemberStep("In-Depth Action Rules", 0),
                    RawMemberStep("Simultaneous Actions", 1),
                ),
                expected_block_sha256=(
                    "57b6ebdb98b389cefba4727fde8d79cb2"
                    "9065e0ba1a0590a0ce95cd1f99db111"
                ),
                expected_member_sha256=(
                    "7dcc718e384c4e0df65f9749be287e3d"
                    "0638b3d54ff32311c1f2806acaf3fe4b"
                ),
                expected_value_sha256=(
                    "c5e0044052b86b4ff7ec61f107bc5fa7"
                    "a214a2df49babef476b7add2d2df1556"
                ),
            ),
        ),
        (
            "disrupting-actions",
            RuleRequirement(
                rule_id="disrupting-actions",
                source_id="core-pc1",
                locator="415.3",
                expected_block_sha256=(
                    "e4cbbde8bdd6b5e20a99f8e66687e3b9"
                    "8620ba4eb4be67b169de239b0de6bcc9"
                ),
            ),
        ),
        (
            "strike",
            RuleRequirement(
                rule_id="strike",
                source_id="core-pc1",
                locator="418.4",
                expected_block_sha256=(
                    "4cea8c4d82ad0a9ea60102ae21613d1e"
                    "401270c1b2e6d97ad7fc10041bda273a"
                ),
            ),
        ),
        (
            "multiple-attack-penalty",
            RuleRequirement(
                rule_id="multiple-attack-penalty",
                source_id="core-pc1",
                locator="402.1",
                selection_path=(
                    RawMemberStep("Multiple Attack Penalty", 8),
                ),
                expected_block_sha256=(
                    "9cee690b7622ad76a92678b16cacada0"
                    "c963ba08172569a6bde16aaff0e5f42e"
                ),
                expected_member_sha256=(
                    "756c178e5fa866e7ab065f55b764a0e1"
                    "cafdaa233774368092f12f578974debc"
                ),
                expected_value_sha256=(
                    "597336c640f963331cfa2482426eb9476"
                    "6802aad85e25fee3a6215ef79c987fa"
                ),
            ),
        ),
        (
            "range-and-reach",
            RuleRequirement(
                rule_id="range-and-reach",
                source_id="core-pc1",
                locator="426.3",
                expected_block_sha256=(
                    "b9db9ee1c4a6c7297ab9128a8d019e6c"
                    "b7b6d2416ea376f3f8dffbf4efdb04b4"
                ),
            ),
        ),
        (
            "targets",
            RuleRequirement(
                rule_id="targets",
                source_id="core-pc1",
                locator="426.4",
                expected_block_sha256=(
                    "1ece0e73d0f743d7c6dc56f06076484e"
                    "9f24c54cc05d2fbcd9febcb1d97eb482"
                ),
            ),
        ),
        (
            "degree-of-success",
            RuleRequirement(
                rule_id="degree-of-success",
                source_id="core-pc1",
                locator="401.4",
                expected_block_sha256=(
                    "05a8ea41e782723a63bed00663d4a4ffa"
                    "dfb446edf869af24b4f2f8a61d3c033"
                ),
            ),
        ),
        (
            "duration",
            RuleRequirement(
                rule_id="duration",
                source_id="core-pc1",
                locator="426.2",
                expected_block_sha256=(
                    "abae8acd3b37239c6a931639213e2a82d"
                    "c7013498d3577007064f9cc1076bcc0"
                ),
            ),
        ),
        (
            "start-turn",
            RuleRequirement(
                rule_id="start-turn",
                source_id="core-pc1",
                locator="435.8",
                expected_block_sha256=(
                    "412cf21f6f82dfe98f3f3679ad31420c"
                    "77b175d313f601738bd7f8db02487600"
                ),
            ),
        ),
    )


_FRENZY_RULE_IDS = (
    "activities",
    "subordinate-actions",
    "simultaneous-actions",
    "disrupting-actions",
    "strike",
    "multiple-attack-penalty",
    "range-and-reach",
    "targets",
)
_MOMENTUM_RULE_IDS = (
    "degree-of-success",
    "strike",
    "duration",
    "start-turn",
)


def _requirements_for(
    rule_ids: tuple[str, ...],
) -> tuple[RuleRequirement, ...]:
    all_rules = _fresh_rule_requirements()
    by_id = {rule_id: requirement for rule_id, requirement in all_rules}
    return tuple(by_id[rule_id] for rule_id in rule_ids)


FRENZY_RULE_REQUIREMENTS = _requirements_for(_FRENZY_RULE_IDS)
MOMENTUM_RULE_REQUIREMENTS = _requirements_for(_MOMENTUM_RULE_IDS)
DRACONIC_SPELLCASTERS_CONFIGURATION_RULE = RuleRequirement(
    rule_id="draconic-spellcasters-configuration",
    source_id="core-mc1",
    locator="108.2",
    selection_path=(RawMemberStep("~.p", 0),),
    expected_block_sha256=(
        "6e9339a10a1892f1ba83fdfd1103d704"
        "45f44411016c96d936ab98bc2379a184"
    ),
    expected_member_sha256=(
        "6e9339a10a1892f1ba83fdfd1103d704"
        "45f44411016c96d936ab98bc2379a184"
    ),
    expected_value_sha256=(
        "684759b8527a177f422d325bfd0568776"
        "2fee106e1dc650a4b2b4e8bb8f30491"
    ),
)


RuntimeDeferralKind: TypeAlias = Literal[
    "compound-strike-activity",
    "compound-activity-disruption",
    "shared-turn-multiple-attack-penalty",
    "just-in-time-strike-targeting",
    "post-strike-trigger-windows",
    "post-strike-critical-trigger",
    "exact-ability-cooldown-effect",
    "fortune-spontaneous-slot-restoration",
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


def _bind_runtime_deferrals():
    canonical_pairs = (
        (
            "compound-strike-activity",
            (
                "activities",
                "subordinate-actions",
                "simultaneous-actions",
                "strike",
            ),
        ),
        (
            "compound-activity-disruption",
            ("activities", "disrupting-actions"),
        ),
        (
            "shared-turn-multiple-attack-penalty",
            ("strike", "multiple-attack-penalty"),
        ),
        (
            "just-in-time-strike-targeting",
            ("range-and-reach", "targets"),
        ),
        (
            "post-strike-trigger-windows",
            ("simultaneous-actions", "disrupting-actions"),
        ),
        (
            "post-strike-critical-trigger",
            ("degree-of-success", "strike"),
        ),
        (
            "exact-ability-cooldown-effect",
            ("duration", "start-turn"),
        ),
        (
            "fortune-spontaneous-slot-restoration",
            ("duration", "start-turn"),
        ),
    )

    def validate(value: RuntimeDeferral) -> None:
        if (
            type(value) is not RuntimeDeferral
            or type(value.kind) is not str
            or type(value.provider_rule_ids) is not tuple
            or any(type(item) is not str for item in value.provider_rule_ids)
            or (value.kind, value.provider_rule_ids) not in pairs
        ):
            raise TypeError(
                "RuntimeDeferral must be one exact reviewed pair"
            )

    def serialize(value: RuntimeDeferral) -> dict[str, Any]:
        validate(value)
        return {
            "id": value.kind,
            "category": "runtime",
            "phase": "runtime",
            "providerRuleIds": list(value.provider_rule_ids),
            "status": "deferred",
            "blocks": "runtime-activation",
        }

    def build() -> tuple[RuntimeDeferral, ...]:
        return tuple(
            RuntimeDeferral(kind, provider_rule_ids)
            for kind, provider_rule_ids in canonical_pairs
        )

    pairs = canonical_pairs
    return validate, serialize, build


(
    _validate_runtime_deferral,
    _serialize_runtime_deferral,
    _build_runtime_deferrals,
) = _bind_runtime_deferrals()
RuntimeDeferral.__post_init__ = _validate_runtime_deferral
RuntimeDeferral.as_serialized = _serialize_runtime_deferral
_ALL_RUNTIME_DEFERRALS = _build_runtime_deferrals()


def _raw_payload(value: object, *, depth: int = 0) -> object:
    if depth > MAX_PROJECTION_DEPTH:
        raise DraconicLinkError("Draconic raw projection exceeds depth bound")
    if type(value) is RawSourceObject:
        return {
            "$orderedObject": [
                [member.key, _raw_payload(member.value, depth=depth + 1)]
                for member in value.members
            ]
        }
    if type(value) is RawSourceArray:
        return [
            _raw_payload(item, depth=depth + 1)
            for item in value.items
        ]
    if value is None or type(value) in {bool, int, float, str}:
        return value
    raise DraconicLinkError(
        f"Draconic raw source is not exact: {type(value).__name__}"
    )


def _closed_json(value: object) -> object:
    active: set[int] = set()
    nodes = 0

    def visit(item: object, depth: int) -> object:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_PROJECTION_NODES:
            raise DraconicLinkError(
                "Draconic projection exceeds node bound"
            )
        if depth > MAX_PROJECTION_DEPTH:
            raise DraconicLinkError(
                "Draconic projection exceeds depth bound"
            )
        if item is None or type(item) in {bool, int, float, str}:
            return item
        if type(item) is dict:
            if len(item) > MAX_CONTAINER_ITEMS:
                raise DraconicLinkError(
                    "Draconic projection object exceeds item bound"
                )
            identity = id(item)
            if identity in active:
                raise DraconicLinkError(
                    "Draconic projection contains a cycle"
                )
            active.add(identity)
            try:
                result = {}
                for key, child in item.items():
                    if type(key) is not str:
                        raise DraconicLinkError(
                            "Draconic projection key is not exact text"
                        )
                    result[key] = visit(child, depth + 1)
            finally:
                active.remove(identity)
            return result
        if type(item) is list:
            if len(item) > MAX_CONTAINER_ITEMS:
                raise DraconicLinkError(
                    "Draconic projection array exceeds item bound"
                )
            identity = id(item)
            if identity in active:
                raise DraconicLinkError(
                    "Draconic projection contains a cycle"
                )
            active.add(identity)
            try:
                result = [visit(child, depth + 1) for child in item]
            finally:
                active.remove(identity)
            return result
        raise DraconicLinkError(
            f"Draconic projection is not closed JSON: {type(item).__name__}"
        )

    result = visit(value, 0)
    encoded = canonical_json_bytes(result)
    if len(encoded) > MAX_PROJECTION_BYTES:
        raise DraconicLinkError(
            "Draconic projection exceeds byte bound"
        )
    return result


def _projection_sha256(value: dict[str, Any]) -> str:
    closed = _closed_json(value)
    if type(closed) is not dict:
        raise DraconicLinkError("Draconic projection must be an object")
    return hashlib.sha256(canonical_json_bytes(closed)).hexdigest()


def _raw_values(source: RawSourceObject, key: str) -> tuple[object, ...]:
    return tuple(
        member.value for member in source.members if member.key == key
    )


def _utf8_text(
    value: object,
    *,
    maximum: int,
    label: str,
) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or not value.isprintable()
        or len(value.encode("utf-8")) > maximum
    ):
        raise DraconicCompileError(
            f"{label} must be bounded trimmed printable text"
        )
    return value


def _require_authority(authority: object) -> SourceAuthorityAdapter:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "Draconic compilation requires exact SourceAuthorityAdapter"
        )
    if authority.allowed_source_ids != ("core-mc1", "core-pc1"):
        raise DraconicCompileError(
            "Draconic authority must select only Core MC1 and PC1"
        )
    return authority


def _creature_context(
    authority: SourceAuthorityAdapter,
    source: object,
    *,
    expected_key: str,
) -> tuple[VerifiedSourceSelection, str, RawSourceMember]:
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "Draconic source must be exact VerifiedSourceSelection"
        )
    source = authority.validate_selection(source)
    address = source.address
    if (
        address.source_id != "core-mc1"
        or address.span is not None
        or type(address.carrier_path) is not tuple
        or not address.carrier_path
        or type(address.carrier_path[-1]) is not RawMemberStep
        or address.carrier_path[-1].raw_key != "^.creature"
        or type(address.selection_path) is not tuple
        or len(address.selection_path) != 1
        or type(address.selection_path[0]) is not RawMemberStep
        or address.selection_path[0].raw_key != expected_key
        or type(source.carrier.raw_block) is not RawSourceObject
        or type(source.raw_member) is not RawSourceMember
        or source.raw_member.key != expected_key
        or source.selected_value is not source.raw_value
    ):
        raise DraconicCompileError(
            "Draconic source is not one exact direct creature member"
        )
    block = source.carrier.raw_block
    if len(block.members) > MAX_CREATURE_MEMBERS:
        raise DraconicCompileError(
            "Draconic creature block exceeds member bound"
        )
    key_members = tuple(
        (ordinal, member)
        for ordinal, member in enumerate(block.members)
        if member.key == expected_key
    )
    if len(key_members) != 1:
        raise DraconicCompileError(
            f"Draconic creature has {len(key_members)} exact "
            f"{expected_key!r} members"
        )
    ordinal, raw_member = key_members[0]
    step = address.selection_path[0]
    if step.member_ordinal != ordinal or raw_member != source.raw_member:
        raise DraconicCompileError(
            "Draconic selected member disagrees with its creature"
        )
    names = _raw_values(block, "Name")
    if len(names) != 1:
        raise DraconicCompileError(
            "Draconic creature must have one exact Name"
        )
    creature_name = _utf8_text(
        names[0],
        maximum=MAX_CREATURE_NAME_BYTES,
        label="Draconic creature Name",
    )
    return source, creature_name, raw_member


def _same_creature(
    first: VerifiedSourceSelection,
    second: VerifiedSourceSelection,
) -> bool:
    first_address = first.address
    second_address = second.address
    return (
        first_address.source_id == second_address.source_id
        and first_address.locator == second_address.locator
        and first_address.section_id == second_address.section_id
        and first_address.target_path == second_address.target_path
        and first_address.carrier_path == second_address.carrier_path
        and first.block_sha256 == second.block_sha256
    )


def _resolve_direct_member(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    raw_key: str,
    *,
    required: bool,
) -> VerifiedSourceSelection | None:
    block = source.carrier.raw_block
    candidates = tuple(
        ordinal
        for ordinal, member in enumerate(block.members)
        if member.key == raw_key
    )
    conflicting = tuple(
        member
        for member in block.members
        if member.key.strip() == raw_key and member.key != raw_key
    )
    if conflicting or len(candidates) > 1:
        raise DraconicLinkError(
            f"Draconic local {raw_key!r} member is ambiguous"
        )
    if not candidates:
        if required:
            raise DraconicLinkError(
                f"Draconic creature lacks exact {raw_key!r}"
            )
        return None
    selected = authority.resolve(
        authority.address(
            source_id=source.address.source_id,
            locator=source.address.locator,
            carrier_path=source.address.carrier_path,
            selection_path=(
                RawMemberStep(raw_key, candidates[0]),
            ),
        )
    )
    if not _same_creature(source, selected):
        raise DraconicLinkError(
            f"Draconic local {raw_key!r} escaped its creature"
        )
    return selected


def _prior_reference(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    reference: object,
    *,
    raw_key: str,
    expected_name: str,
) -> tuple[VerifiedSourceSelection, str, RawSourceMember]:
    if type(reference) is not VerifiedSourceSelection:
        raise DraconicCompileError(
            "authored Draconic inheritance requires one exact selection"
        )
    reference, creature_name, raw_member = _creature_context(
        authority,
        reference,
        expected_key=raw_key,
    )
    source_address = source.address
    reference_address = reference.address
    if (
        len(source_address.carrier_path) < 2
        or len(reference_address.carrier_path) < 2
    ):
        raise DraconicCompileError(
            "Draconic inheritance target is not the named preceding "
            "same-section creature"
        )
    source_heading = source_address.carrier_path[-2]
    reference_heading = reference_address.carrier_path[-2]
    source_creature = source_address.carrier_path[-1]
    reference_creature = reference_address.carrier_path[-1]
    if (
        source_address.source_id != reference_address.source_id
        or source_address.locator != reference_address.locator
        or source_address.section_id != reference_address.section_id
        or source_address.target_path != reference_address.target_path
        or source_address.carrier_path[:-2]
        != reference_address.carrier_path[:-2]
        or type(source_heading) is not RawMemberStep
        or type(reference_heading) is not RawMemberStep
        or type(source_creature) is not RawMemberStep
        or type(reference_creature) is not RawMemberStep
        or source_creature.raw_key != "^.creature"
        or reference_creature.raw_key != "^.creature"
        or source_creature.member_ordinal != 0
        or reference_creature.member_ordinal != 0
        or reference_heading.member_ordinal
        >= source_heading.member_ordinal
        or creature_name.casefold() != expected_name
    ):
        raise DraconicCompileError(
            "Draconic inheritance target is not the named preceding "
            "same-section creature"
        )
    return reference, creature_name, raw_member


def _validated_rules(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    providers: object,
    requirements: tuple[RuleRequirement, ...],
) -> tuple[VerifiedRuleReceipt, ...]:
    if type(providers) is not tuple:
        raise TypeError(
            "Draconic provider receipts must be one exact ordered tuple"
        )
    if (
        len(providers) != len(requirements)
        or any(type(item) is not VerifiedRuleReceipt for item in providers)
    ):
        raise DraconicCompileError(
            "Draconic provider receipts do not match the family proof"
        )
    authority.require_shared_authority(source, providers)
    result = []
    for supplied, expected in zip(providers, requirements):
        authority.validate_rule(supplied)
        if canonical_json_bytes(
            supplied.requirement.as_serialized()
        ) != canonical_json_bytes(expected.as_serialized()):
            raise DraconicCompileError(
                f"Draconic provider requirement changed: "
                f"{expected.rule_id}"
            )
        result.append(supplied)
    return tuple(result)


def _provider_projection(
    providers: tuple[VerifiedRuleReceipt, ...],
) -> list[dict[str, Any]]:
    return [provider.as_serialized() for provider in providers]


def _configuration_excludes_family(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    configuration: object,
    requirement: RuleRequirement,
) -> bool:
    if configuration is None:
        return False
    if type(configuration) is not VerifiedRuleReceipt:
        raise TypeError(
            "Draconic spellcaster configuration must be an exact "
            "VerifiedRuleReceipt"
        )
    authority.require_shared_authority(source, (configuration,))
    authority.validate_rule(configuration)
    if canonical_json_bytes(
        configuration.requirement.as_serialized()
    ) != canonical_json_bytes(requirement.as_serialized()):
        raise DraconicCompileError(
            "Draconic spellcaster configuration rule changed"
        )
    return True


def _concrete_frenzy(
    description: object,
) -> tuple[str, tuple[str, str, str]] | None:
    if type(description) is not str:
        return None
    lower_words = r"[a-z]+(?: [a-z]+)*"
    pattern = re.compile(
        rf"^The (?P<subject>{lower_words}) makes "
        r"(?P<first_count>one|two) (?P<first>[a-z]+) "
        r"(?P<first_plural>Strike|Strikes) and "
        r"(?P<second_count>one|two) (?P<second>[a-z]+) "
        r"(?P<second_plural>Strike|Strikes) in any order\.$",
        re.ASCII,
    )
    match = pattern.fullmatch(description)
    if match is None:
        return None
    counts = {"one": 1, "two": 2}
    first_count = counts[match.group("first_count")]
    second_count = counts[match.group("second_count")]
    if (
        match.group("first_plural")
        != ("Strike" if first_count == 1 else "Strikes")
        or match.group("second_plural")
        != ("Strike" if second_count == 1 else "Strikes")
        or first_count + second_count != 3
        or match.group("first") == match.group("second")
    ):
        return None
    sequence = (
        *([match.group("first")] * first_count),
        *([match.group("second")] * second_count),
    )
    return match.group("subject"), sequence


def _frenzy_description(value: object) -> str | None:
    if (
        type(value) is not RawSourceObject
        or tuple(member.key for member in value.members)
        != ("Action", "Description")
    ):
        return None
    actions = _raw_values(value, "Action")
    descriptions = _raw_values(value, "Description")
    if (
        actions != ("two",)
        or len(descriptions) != 1
        or type(descriptions[0]) is not str
    ):
        return None
    return descriptions[0]


def _resolve_frenzy(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    inheritance: object,
) -> tuple[
    str,
    tuple[str, str, str],
    str,
    str,
    VerifiedSourceSelection | None,
] | None:
    raw_description = _frenzy_description(source.raw_value)
    if raw_description is None:
        return None
    _utf8_text(
        raw_description,
        maximum=MAX_SOURCE_TEXT_BYTES,
        label="Draconic Frenzy Description",
    )
    concrete = _concrete_frenzy(raw_description)
    if concrete is not None:
        if inheritance is not None:
            raise DraconicCompileError(
                "concrete Draconic Frenzy cannot accept inheritance"
            )
        return (
            concrete[0],
            concrete[1],
            raw_description,
            "concrete",
            None,
        )
    match = re.fullmatch(
        r"^As (?P<target>young [a-z]+(?: [a-z]+)* dragon)\.$",
        raw_description,
        re.ASCII,
    )
    if match is None:
        return None
    reference, _name, member = _prior_reference(
        authority,
        source,
        inheritance,
        raw_key="!.Draconic Frenzy",
        expected_name=match.group("target"),
    )
    resolved_description = _frenzy_description(member.value)
    resolved = _concrete_frenzy(resolved_description)
    if resolved_description is None or resolved is None:
        raise DraconicCompileError(
            "Draconic Frenzy inheritance target is not concrete"
        )
    return (
        resolved[0],
        resolved[1],
        resolved_description,
        "explicit-inheritance",
        reference,
    )


def _unique_strike_value(
    strike: RawSourceObject,
    key: str,
    *,
    required: bool,
) -> object | None:
    exact = _raw_values(strike, key)
    conflicting = tuple(
        member
        for member in strike.members
        if member.key.strip() == key and member.key != key
    )
    if conflicting or len(exact) > 1:
        raise DraconicLinkError(
            f"raw Melee Strike has ambiguous {key!r}"
        )
    if not exact:
        if required:
            raise DraconicLinkError(
                f"raw Melee Strike lacks exact {key!r}"
            )
        return None
    return exact[0]


def _melee_strikes(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
) -> tuple[
    VerifiedSourceSelection,
    tuple[dict[str, Any], ...],
]:
    melee = _resolve_direct_member(
        authority,
        source,
        "Melee",
        required=True,
    )
    if melee is None or type(melee.raw_value) is not RawSourceArray:
        raise DraconicLinkError("Draconic Melee must be one exact array")
    items = melee.raw_value.items
    if not items or len(items) > MAX_MELEE_STRIKES:
        raise DraconicLinkError(
            "Draconic Melee Strike count is outside its bound"
        )
    melee_step = melee.address.selection_path[0]
    names: set[str] = set()
    result = []
    for ordinal, strike in enumerate(items):
        if type(strike) is not RawSourceObject:
            raise DraconicLinkError(
                "Draconic Melee Strike must be an exact object"
            )
        name = _unique_strike_value(strike, "Name", required=True)
        attack = _unique_strike_value(strike, "Attack", required=True)
        traits = _unique_strike_value(strike, "Traits", required=False)
        damage = _unique_strike_value(strike, "Damage", required=False)
        effects = _unique_strike_value(strike, "Effects", required=False)
        if (
            type(name) is not str
            or not name
            or name != name.strip()
            or len(name.encode("utf-8")) > MAX_STRIKE_NAME_BYTES
            or name in names
            or type(attack) is not str
            or _SIGNED_DECIMAL_RE.fullmatch(attack) is None
            or parse_decimal_integer(attack) is None
            or (
                traits is not None
                and (
                    type(traits) is not RawSourceArray
                    or any(type(item) is not str for item in traits.items)
                )
            )
            or (damage is not None and type(damage) is not str)
            or (effects is not None and type(effects) is not str)
        ):
            raise DraconicLinkError(
                "Draconic Melee Strike shape is invalid"
            )
        names.add(name)
        strike_selection = authority.resolve(
            authority.address(
                source_id=source.address.source_id,
                locator=source.address.locator,
                carrier_path=source.address.carrier_path,
                selection_path=(
                    melee_step,
                    RawIndexStep(ordinal),
                ),
            )
        )
        result.append(
            {
                "listOrdinal": ordinal,
                "rawName": name,
                "attackSourceText": attack,
                "attackModifier": parse_decimal_integer(attack),
                "traits": (
                    list(traits.items)
                    if type(traits) is RawSourceArray
                    else []
                ),
                "damageSourceText": damage,
                "effectsSourceText": effects,
                "rawStrikeSha256": raw_source_sha256(strike),
                "source": strike_selection.receipt.as_serialized(),
                "rawStrike": _raw_payload(strike),
            }
        )
    return melee, tuple(result)


# These are the only reviewed exact consumer block/family-selection pairs
# where the authored singular token ``claw`` binds local raw ``claws``.
_REVIEWED_CLAW_ALIASES = (
    (
        "b5d4bb1e6c7a1f1b827176748c20f6893cf3a1695e150999dff5f084e55b405c",
        "311b7dd61d4ca7a31421046d91e584787f7eea4bd3b090bc16d27284fee14042",
    ),
    (
        "b71f5cadeff233a7e165eb4d16323cc68a93532a08829eb70a9949af13d52d42",
        "8a89cfb976bd717a4f878fc12ed7c401557eae4106df231c16295020471ce573",
    ),
    (
        "e202b39ef58d4efb1a275a05e59c7d8cabdda0c977e3ac107b0d2761ae3deba6",
        "8a89cfb976bd717a4f878fc12ed7c401557eae4106df231c16295020471ce573",
    ),
    (
        "101f195f43b41788789cc618d3a4ff8b5c14a73483f904732afececa6c54c3b9",
        "a25c5b024563c7b54c041fdae1f9a2405ed42cbe1a1231f152563a7e0c691e9a",
    ),
    (
        "5d68770ca8caf1232f5d9534ec2222e662d0a618dd8dec80fac0799f1de4cdd9",
        "4d70a132f461b467eac3799e7766916d314564290cb8bb793a035c41c264a5ed",
    ),
    (
        "9dfb7db7a6701159aa1e29ff6591df76e19e9e1130e29cdfe0081661217b0132",
        "4d70a132f461b467eac3799e7766916d314564290cb8bb793a035c41c264a5ed",
    ),
    (
        "dd3c5de134b116dff5f512a5f9cf4b0c3008665a53a7fae9e5d9e5bceeec4d0f",
        "311b7dd61d4ca7a31421046d91e584787f7eea4bd3b090bc16d27284fee14042",
    ),
    (
        "d727b6237fad87f24a23c076f3dd48e6287dc1678066485fa17792963ba19b5f",
        "8e96d792405f47b6ca141b2368987df3847173333c1e8ec8f5358d95fc986545",
    ),
    (
        "79b9181730d71cb24fb7bd076b891b6e6111aa1ab5fa54aac5007fa8a4124f0d",
        "8e96d792405f47b6ca141b2368987df3847173333c1e8ec8f5358d95fc986545",
    ),
)


def _bind_frenzy_strikes(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    tokens: tuple[str, str, str],
    aliases: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    melee, strikes = _melee_strikes(authority, source)
    selected_by_token: dict[str, dict[str, Any]] = {}
    selected = []
    for token in dict.fromkeys(tokens):
        matches = [item for item in strikes if item["rawName"] == token]
        binding_mode = "exact-raw-name"
        if (
            token == "claw"
            and (source.block_sha256, source.selection_sha256) in aliases
        ):
            plural = [
                item for item in strikes if item["rawName"] == "claws"
            ]
            if len(matches) + len(plural) != 1:
                raise DraconicLinkError(
                    "reviewed claw-to-claws source alias is ambiguous"
                )
            if not matches:
                matches = plural
                binding_mode = "reviewed-claw-to-claws-source-alias"
        if len(matches) != 1:
            raise DraconicLinkError(
                f"listed Strike token {token!r} has "
                f"{len(matches)} exact local bindings"
            )
        definition = {
            "listedToken": token,
            "bindingMode": binding_mode,
            **matches[0],
        }
        selected_by_token[token] = definition
        selected.append(definition)
    positions = []
    for ordinal, token in enumerate(tokens):
        definition = selected_by_token[token]
        positions.append(
            {
                "sequenceOrdinal": ordinal,
                "listedToken": token,
                "rawStrikeName": definition["rawName"],
                "strikeListOrdinal": definition["listOrdinal"],
                "rawStrikeSha256": definition["rawStrikeSha256"],
                "bindingMode": definition["bindingMode"],
                "multipleAttackPenalty": {
                    "usesSharedTurnCount": True,
                    "advancesAfterAttempt": True,
                    "agileFromCurrentStrike": (
                        "agile" in definition["traits"]
                    ),
                },
            }
        )
    return {
        "status": "linked",
        "sourceField": "Melee",
        "source": melee.receipt.as_serialized(),
        "positions": positions,
        "selectedStrikeDefinitions": selected,
    }


def _parse_momentum(
    description: object,
) -> tuple[str, str, tuple[str, ...]] | None:
    if type(description) is not str:
        return None
    if description == (
        "Whenever they score a critical hit with a Strike, the dragon "
        "chooses to either recharge Disruptive Breath or regain one "
        "expended spontaneous spell slot."
    ):
        return (
            "choice-recharge-or-spontaneous-slot",
            "Disruptive Breath",
            (
                "recharge-target-ability",
                "regain-one-expended-spontaneous-spell-slot",
            ),
        )
    title_words = r"[A-Z][A-Za-z]*(?: [A-Za-z]+)*"
    patterns = (
        re.compile(
            r"^The dragon recharges their "
            rf"(?P<target>{title_words} Breath) whenever they score a "
            r"critical hit with a Strike\.$",
            re.ASCII,
        ),
        re.compile(
            r"^When the dragon scores a critical hit with a Strike, they "
            rf"recharge (?P<target>{title_words} Breath)\.$",
            re.ASCII,
        ),
    )
    matches = [
        match
        for pattern in patterns
        if (match := pattern.fullmatch(description)) is not None
    ]
    if len(matches) != 1:
        return None
    return "recharge-breath", matches[0].group("target"), ()


def _resolve_momentum(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    inheritance: object,
) -> tuple[
    str,
    str,
    tuple[str, ...],
    str,
    str,
    VerifiedSourceSelection | None,
] | None:
    raw_description = source.raw_value
    if type(raw_description) is not str:
        return None
    _utf8_text(
        raw_description,
        maximum=MAX_SOURCE_TEXT_BYTES,
        label="Draconic Momentum Description",
    )
    concrete = _parse_momentum(raw_description)
    if concrete is not None:
        if inheritance is not None:
            raise DraconicCompileError(
                "concrete Draconic Momentum cannot accept inheritance"
            )
        return (
            concrete[0],
            concrete[1],
            concrete[2],
            raw_description,
            "concrete",
            None,
        )
    match = re.fullmatch(
        r"^As (?P<target>young [a-z]+(?: [a-z]+)* dragon)\.$",
        raw_description,
        re.ASCII,
    )
    if match is None:
        return None
    reference, _name, member = _prior_reference(
        authority,
        source,
        inheritance,
        raw_key="!.Draconic Momentum",
        expected_name=match.group("target"),
    )
    resolved = _parse_momentum(member.value)
    if resolved is None or type(member.value) is not str:
        raise DraconicCompileError(
            "Draconic Momentum inheritance target is not concrete"
        )
    return (
        resolved[0],
        resolved[1],
        resolved[2],
        member.value,
        "explicit-inheritance",
        reference,
    )


def _breath_binding(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    target_label: str,
    cooldown_source: object,
) -> dict[str, Any]:
    breath = _resolve_direct_member(
        authority,
        source,
        f"!.{target_label}",
        required=True,
    )
    if breath is None or type(breath.raw_value) is not RawSourceObject:
        raise DraconicLinkError(
            "Momentum target Breath must be an exact object"
        )
    value = breath.raw_value
    if tuple(member.key for member in value.members) != (
        "Action",
        "Traits",
        "Description",
    ):
        raise DraconicLinkError(
            "Momentum target Breath has wrong member order"
        )
    actions = _raw_values(value, "Action")
    traits_values = _raw_values(value, "Traits")
    descriptions = _raw_values(value, "Description")
    if (
        actions != ("two",)
        or len(traits_values) != 1
        or type(traits_values[0]) is not RawSourceArray
        or any(type(item) is not str for item in traits_values[0].items)
        or len(descriptions) != 1
        or type(descriptions[0]) is not str
    ):
        raise DraconicLinkError(
            "Momentum target Breath production is invalid"
        )
    description = descriptions[0]
    _utf8_text(
        description,
        maximum=MAX_SOURCE_TEXT_BYTES,
        label="Momentum target Breath Description",
    )
    title_words = r"[A-Z][A-Za-z]*(?: [A-Za-z]+)*"
    cooldown_pattern = re.compile(
        rf"\bcan’t use (?P<target>{title_words}) again for 1d4 rounds\.",
        re.ASCII,
    )
    local_matches = list(cooldown_pattern.finditer(description))
    cooldown_receipt: dict[str, Any]
    if local_matches:
        if (
            len(local_matches) != 1
            or local_matches[0].group("target") != target_label
            or cooldown_source is not None
        ):
            raise DraconicLinkError(
                "Momentum local cooldown source is ambiguous"
            )
        cooldown_receipt = {
            "inherited": False,
            "source": breath.receipt.as_serialized(),
            "sourceText": local_matches[0].group(0),
        }
    else:
        match = re.fullmatch(
            r"^As (?P<target>young [a-z]+(?: [a-z]+)* dragon), "
            r"but \S+(?: \S+)*\.$",
            description,
            re.ASCII,
        )
        if match is None:
            raise DraconicLinkError(
                "Momentum Breath lacks exact cooldown production"
            )
        try:
            reference, _name, member = _prior_reference(
                authority,
                source,
                cooldown_source,
                raw_key=f"!.{target_label}",
                expected_name=match.group("target"),
            )
        except DraconicCompileError as failure:
            raise DraconicLinkError(
                "Momentum inherited cooldown source identity is invalid"
            ) from failure
        reference_value = member.value
        if (
            type(reference_value) is not RawSourceObject
            or tuple(item.key for item in reference_value.members)
            != ("Action", "Traits", "Description")
        ):
            raise DraconicLinkError(
                "Momentum inherited cooldown source is malformed"
            )
        reference_actions = _raw_values(reference_value, "Action")
        reference_traits = _raw_values(reference_value, "Traits")
        reference_descriptions = _raw_values(
            reference_value,
            "Description",
        )
        if (
            reference_actions != ("two",)
            or len(reference_traits) != 1
            or type(reference_traits[0]) is not RawSourceArray
            or any(
                type(item) is not str
                for item in reference_traits[0].items
            )
            or len(reference_descriptions) != 1
            or type(reference_descriptions[0]) is not str
        ):
            raise DraconicLinkError(
                "Momentum inherited cooldown has no exact Description"
            )
        reference_matches = list(
            cooldown_pattern.finditer(reference_descriptions[0])
        )
        if (
            len(reference_matches) != 1
            or reference_matches[0].group("target") != target_label
        ):
            raise DraconicLinkError(
                "Momentum inherited cooldown does not name target"
            )
        cooldown_receipt = {
            "inherited": True,
            "source": reference.receipt.as_serialized(),
            "sourceText": reference_matches[0].group(0),
        }
    return {
        "status": "linked",
        "rawKey": f"!.{target_label}",
        "source": breath.receipt.as_serialized(),
        "actionSourceText": "two",
        "actionCost": 2,
        "traits": list(traits_values[0].items),
        "rawDescription": description,
        "rawValue": _raw_payload(value),
        "cooldownSource": cooldown_receipt,
    }


def _is_spell_slot_entry(value: object) -> bool:
    if type(value) is not str:
        return False
    match = _SPELL_SLOT_ENTRY_RE.fullmatch(value)
    if match is None:
        return False
    count = parse_decimal_integer(match.group("count"))
    return (
        count is not None
        and count > 0
        and ((count == 1) == (match.group("unit") == "slot"))
    )


def _spellcasting_binding(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
) -> dict[str, Any]:
    spellcasting = _resolve_direct_member(
        authority,
        source,
        "Spellcasting",
        required=True,
    )
    if spellcasting is None or type(spellcasting.raw_value) is not RawSourceObject:
        raise DraconicLinkError(
            "Fortune Spellcasting must be one exact object"
        )
    value = spellcasting.raw_value
    if tuple(member.key for member in value.members) != (
        "Arcane Spontaneous Spells",
    ):
        raise DraconicLinkError(
            "Fortune Spellcasting has wrong outer production"
        )
    spontaneous_values = _raw_values(
        value,
        "Arcane Spontaneous Spells",
    )
    if (
        len(spontaneous_values) != 1
        or type(spontaneous_values[0]) is not RawSourceObject
    ):
        raise DraconicLinkError(
            "Fortune spontaneous Spellcasting is ambiguous"
        )
    spontaneous = spontaneous_values[0]
    if tuple(member.key for member in spontaneous.members) != (
        "DC",
        "Attack",
        "Entries",
    ):
        raise DraconicLinkError(
            "Fortune spontaneous Spellcasting is incomplete"
        )
    dc_values = _raw_values(spontaneous, "DC")
    attack_values = _raw_values(spontaneous, "Attack")
    entries_values = _raw_values(spontaneous, "Entries")
    if (
        len(dc_values) != 1
        or type(dc_values[0]) is not str
        or parse_decimal_integer(dc_values[0]) is None
        or parse_decimal_integer(dc_values[0]) <= 0
        or len(attack_values) != 1
        or type(attack_values[0]) is not str
        or _SIGNED_DECIMAL_RE.fullmatch(attack_values[0]) is None
        or parse_decimal_integer(attack_values[0]) is None
        or len(entries_values) != 1
        or type(entries_values[0]) is not RawSourceObject
        or not entries_values[0].members
    ):
        raise DraconicLinkError(
            "Fortune spontaneous Spellcasting has no slot catalog"
        )
    entry_names = tuple(member.key for member in entries_values[0].members)
    if (
        len(entry_names) != len(set(entry_names))
        or not any(_is_spell_slot_entry(name) for name in entry_names)
    ):
        raise DraconicLinkError(
            "Fortune spontaneous Spellcasting has no exact slot entry"
        )
    return {
        "resourceKind": "arcane-spontaneous-spell-slots",
        "source": spellcasting.receipt.as_serialized(),
        "rawSpontaneousSourceSha256": raw_source_sha256(spontaneous),
        "rawSpontaneousSource": _raw_payload(spontaneous),
        "selection": "one-exact-expended-slot-id",
    }


def _source_projection(
    source: VerifiedSourceSelection,
    creature_name: str,
    raw_description: str,
    resolved_description: str,
    production: str,
    inheritance: VerifiedSourceSelection | None,
) -> dict[str, Any]:
    result = {
        "creatureName": creature_name,
        "rawKey": source.raw_member.key,
        "rawDescription": raw_description,
        "resolvedDescription": resolved_description,
        "production": production,
        "source": source.receipt.as_serialized(),
    }
    if inheritance is not None:
        result["resolvedBase"] = inheritance.receipt.as_serialized()
    return result


def _runtime_deferrals_for(
    family: str,
    variant: str | None,
    all_deferrals: tuple[RuntimeDeferral, ...],
) -> tuple[RuntimeDeferral, ...]:
    if family == "draconic-frenzy":
        wanted = {
            "compound-strike-activity",
            "compound-activity-disruption",
            "shared-turn-multiple-attack-penalty",
            "just-in-time-strike-targeting",
            "post-strike-trigger-windows",
        }
    else:
        wanted = {
            "post-strike-critical-trigger",
            "exact-ability-cooldown-effect",
        }
        if variant == "choice-recharge-or-spontaneous-slot":
            wanted.add("fortune-spontaneous-slot-restoration")
    result = tuple(item for item in all_deferrals if item.kind in wanted)
    if len(result) != len(wanted):
        raise DraconicCompileError(
            "Draconic runtime deferral contract is incomplete"
        )
    return result


def _compile_projection(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    providers: tuple[VerifiedRuleReceipt, ...],
    inheritance: VerifiedSourceSelection | None,
    cooldown_source: VerifiedSourceSelection | None,
    configuration: VerifiedRuleReceipt | None,
    *,
    family: str,
    requirements: tuple[RuleRequirement, ...],
    configuration_requirement: RuleRequirement,
    aliases: tuple[tuple[str, str], ...],
    all_deferrals: tuple[RuntimeDeferral, ...],
) -> dict[str, Any] | None:
    raw_key = (
        "!.Draconic Frenzy"
        if family == "draconic-frenzy"
        else "!.Draconic Momentum"
    )
    source, creature_name, _raw_member = _creature_context(
        authority,
        source,
        expected_key=raw_key,
    )
    providers = _validated_rules(
        authority,
        source,
        providers,
        requirements,
    )
    if _configuration_excludes_family(
        authority,
        source,
        configuration,
        configuration_requirement,
    ):
        return None
    if family == "draconic-frenzy":
        if cooldown_source is not None:
            raise DraconicCompileError(
                "Draconic Frenzy cannot accept a cooldown source"
            )
        resolved = _resolve_frenzy(authority, source, inheritance)
        if resolved is None:
            return None
        (
            subject,
            tokens,
            resolved_description,
            production,
            resolved_base,
        ) = resolved
        raw_description = _frenzy_description(source.raw_value)
        if raw_description is None:
            return None
        binding = _bind_frenzy_strikes(
            authority,
            source,
            tokens,
            aliases,
        )
        deferrals = _runtime_deferrals_for(
            family,
            None,
            all_deferrals,
        )
        mechanic = {
            "type": "draconic-frenzy",
            "actionCost": 2,
            "sequence": {
                "count": 3,
                "subjectSourceText": subject,
                "listedStrikeTokens": list(tokens),
                "orderPolicy": "any-permutation-of-listed-multiset",
                "binding": binding,
            },
            "multipleAttackPenalty": {
                "state": "shared-turn",
                "appliesTo": "each-subordinate-strike-attempt",
                "advancesOnEveryAttempt": True,
                "agilePolicy": "current-strike",
                "preexistingCountCarriesIn": True,
            },
            "targeting": {
                "decision": "before-each-strike-attempt",
                "revalidateReachAndLegality": True,
                "sameTargetRequired": False,
                "resumeFromAuthoritativeSuccessorState": True,
            },
            "movement": {
                "granted": False,
                "interleavedNonTriggeredActions": False,
            },
            "triggerWindows": "between-subordinate-strike-attempts",
            "source": _source_projection(
                source,
                creature_name,
                raw_description,
                resolved_description,
                production,
                resolved_base,
            ),
            "providerRules": _provider_projection(providers),
            "runtimeSupported": False,
            "deferredDependencies": [
                item.as_serialized() for item in deferrals
            ],
        }
    else:
        resolved = _resolve_momentum(authority, source, inheritance)
        if resolved is None:
            return None
        (
            variant,
            target_label,
            choices,
            resolved_description,
            production,
            resolved_base,
        ) = resolved
        raw_description = source.raw_value
        if type(raw_description) is not str:
            return None
        breath_binding = _breath_binding(
            authority,
            source,
            target_label,
            cooldown_source,
        )
        slot_binding = (
            _spellcasting_binding(authority, source)
            if variant == "choice-recharge-or-spontaneous-slot"
            else None
        )
        deferrals = _runtime_deferrals_for(
            family,
            variant,
            all_deferrals,
        )
        mechanic = {
            "type": "draconic-momentum",
            "actionCost": None,
            "trigger": {
                "event": "strike-resolved",
                "finalDegree": "critical-success",
                "sourceMustBeStrike": True,
                "oneWindowPerCriticalStrike": True,
            },
            "variant": variant,
            "targetAbility": {
                "label": target_label,
                "binding": breath_binding,
            },
            "choices": list(choices),
            "cooldown": {
                "roll": {"count": 1, "sides": 4},
                "unit": "round",
                "tick": "owner-start-turn",
                "readyAtZero": True,
                "momentumEffect": (
                    "remove-exact-target-ability-cooldown"
                ),
                "alreadyReadyPolicy": "idempotent",
            },
            "source": _source_projection(
                source,
                creature_name,
                raw_description,
                resolved_description,
                production,
                resolved_base,
            ),
            "providerRules": _provider_projection(providers),
            "runtimeSupported": False,
            "deferredDependencies": [
                item.as_serialized() for item in deferrals
            ],
        }
        if slot_binding is not None:
            mechanic["spontaneousSlotBinding"] = slot_binding
    result = {
        "supported": True,
        "mechanic": mechanic,
        "rule": {
            "sourceId": source.address.source_id,
            "locator": source.address.locator,
        },
        "traits": [],
        "deferredMechanics": [item.kind for item in deferrals],
    }
    closed = _closed_json(result)
    if type(closed) is not dict:
        raise AssertionError("Draconic projection lost object root")
    return closed


@final
@dataclass(frozen=True, slots=True, init=False)
class DraconicCompilerPatch:
    """Opaque, authority-backed, final compile result."""

    _authority: SourceAuthorityAdapter = field(repr=False)
    _source: VerifiedSourceSelection = field(repr=False)
    _providers: tuple[VerifiedRuleReceipt, ...] = field(repr=False)
    _inheritance: VerifiedSourceSelection | None = field(repr=False)
    _cooldown_source: VerifiedSourceSelection | None = field(repr=False)
    _family: str
    _projection_digest: str = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "DraconicCompilerPatch can only be constructed by a "
            "Draconic compiler"
        )

    @property
    def mechanic_type(self) -> str:
        raise TypeError("DraconicCompilerPatch contract is not bound")

    @property
    def source_receipt(self) -> SourceReceipt:
        raise TypeError("DraconicCompilerPatch contract is not bound")

    def as_ability_update(self) -> dict[str, Any]:
        raise TypeError("DraconicCompilerPatch contract is not bound")


def _copy_requirement(requirement: RuleRequirement) -> RuleRequirement:
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
        expected_selection_sha256=requirement.expected_selection_sha256,
    )


def _bind_reviewed_contract():
    frenzy_requirements = tuple(
        _copy_requirement(item)
        for item in _requirements_for(_FRENZY_RULE_IDS)
    )
    momentum_requirements = tuple(
        _copy_requirement(item)
        for item in _requirements_for(_MOMENTUM_RULE_IDS)
    )
    configuration_requirement = _copy_requirement(
        DRACONIC_SPELLCASTERS_CONFIGURATION_RULE
    )
    aliases = tuple((block, ability) for block, ability in _REVIEWED_CLAW_ALIASES)
    all_deferrals = tuple(
        RuntimeDeferral(item.kind, tuple(item.provider_rule_ids))
        for item in _ALL_RUNTIME_DEFERRALS
    )
    derive = _compile_projection

    def validate_patch(
        value: object,
    ) -> tuple[DraconicCompilerPatch, dict[str, Any]]:
        if type(value) is not DraconicCompilerPatch:
            raise DraconicLinkError(
                "Draconic projection requires exact compiler patch"
            )
        try:
            authority = value._authority
            source = value._source
            providers = value._providers
            inheritance = value._inheritance
            cooldown_source = value._cooldown_source
            family = value._family
            digest = value._projection_digest
        except AttributeError as failure:
            raise DraconicLinkError(
                "Draconic compiler patch is incomplete"
            ) from failure
        authority = _require_authority(authority)
        if family == "draconic-frenzy":
            requirements = frenzy_requirements
        elif family == "draconic-momentum":
            requirements = momentum_requirements
        else:
            raise DraconicLinkError(
                "Draconic compiler patch family is invalid"
            )
        if (
            type(providers) is not tuple
            or (
                inheritance is not None
                and type(inheritance) is not VerifiedSourceSelection
            )
            or (
                cooldown_source is not None
                and type(cooldown_source) is not VerifiedSourceSelection
            )
            or type(digest) is not str
        ):
            raise DraconicLinkError(
                "Draconic compiler patch fields are forged"
            )
        try:
            projection = derive(
                authority,
                source,
                providers,
                inheritance,
                cooldown_source,
                None,
                family=family,
                requirements=requirements,
                configuration_requirement=configuration_requirement,
                aliases=aliases,
                all_deferrals=all_deferrals,
            )
        except (DraconicCompileError, TypeError, ValueError) as failure:
            raise DraconicLinkError(
                "Draconic compiler patch no longer validates"
            ) from failure
        if (
            projection is None
            or _projection_sha256(projection) != digest
        ):
            raise DraconicLinkError(
                "Draconic compiler patch projection changed"
            )
        return value, projection

    def compile_family(
        authority: object,
        source: object,
        providers: object,
        inheritance: object,
        cooldown_source: object,
        configuration: object,
        *,
        family: str,
    ) -> DraconicCompilerPatch | None:
        authority = _require_authority(authority)
        if family == "draconic-frenzy":
            requirements = frenzy_requirements
        else:
            requirements = momentum_requirements
        projection = derive(
            authority,
            source,
            providers,
            inheritance,
            cooldown_source,
            configuration,
            family=family,
            requirements=requirements,
            configuration_requirement=configuration_requirement,
            aliases=aliases,
            all_deferrals=all_deferrals,
        )
        if projection is None:
            return None
        result = object.__new__(DraconicCompilerPatch)
        object.__setattr__(result, "_authority", authority)
        object.__setattr__(result, "_source", source)
        object.__setattr__(result, "_providers", providers)
        object.__setattr__(result, "_inheritance", inheritance)
        object.__setattr__(result, "_cooldown_source", cooldown_source)
        object.__setattr__(result, "_family", family)
        object.__setattr__(
            result,
            "_projection_digest",
            _projection_sha256(projection),
        )
        validate_patch(result)
        return result

    def compile_draconic_frenzy(
        authority: object,
        source: object,
        providers: object,
        inheritance: object = None,
        configuration: object = None,
        /,
    ) -> DraconicCompilerPatch | None:
        """Compile and source-link one exact Draconic Frenzy record."""

        return compile_family(
            authority,
            source,
            providers,
            inheritance,
            None,
            configuration,
            family="draconic-frenzy",
        )

    def compile_draconic_momentum(
        authority: object,
        source: object,
        providers: object,
        inheritance: object = None,
        cooldown_source: object = None,
        configuration: object = None,
        /,
    ) -> DraconicCompilerPatch | None:
        """Compile and source-link one exact Draconic Momentum record."""

        return compile_family(
            authority,
            source,
            providers,
            inheritance,
            cooldown_source,
            configuration,
            family="draconic-momentum",
        )

    def patch_projection(value: DraconicCompilerPatch) -> dict[str, Any]:
        _patch, projection = validate_patch(value)
        closed = _closed_json(projection)
        if type(closed) is not dict:
            raise DraconicLinkError(
                "Draconic compiler projection lost object root"
            )
        return closed

    def patch_mechanic_type(value: DraconicCompilerPatch) -> str:
        _patch, projection = validate_patch(value)
        mechanic = projection["mechanic"]
        if type(mechanic) is not dict or type(mechanic["type"]) is not str:
            raise DraconicLinkError(
                "Draconic mechanic type is malformed"
            )
        return mechanic["type"]

    def patch_source_receipt(value: DraconicCompilerPatch) -> SourceReceipt:
        patch, _projection = validate_patch(value)
        patch._authority.validate_selection(patch._source)
        return patch._source.receipt

    return (
        compile_draconic_frenzy,
        compile_draconic_momentum,
        patch_projection,
        patch_mechanic_type,
        patch_source_receipt,
    )


(
    compile_draconic_frenzy,
    compile_draconic_momentum,
    _patch_projection,
    _patch_mechanic_type,
    _patch_source_receipt,
) = _bind_reviewed_contract()
DraconicCompilerPatch.as_ability_update = _patch_projection
DraconicCompilerPatch.mechanic_type = property(_patch_mechanic_type)
DraconicCompilerPatch.source_receipt = property(_patch_source_receipt)


__all__ = [
    "DraconicCompileError",
    "DraconicCompilerPatch",
    "DraconicLinkError",
    "DRACONIC_SPELLCASTERS_CONFIGURATION_RULE",
    "FAMILY_ID",
    "FRENZY_COMPILER_ID",
    "FRENZY_MECHANIC_TYPE",
    "FRENZY_RAW_KEY",
    "FRENZY_RULE_REQUIREMENTS",
    "MOMENTUM_COMPILER_ID",
    "MOMENTUM_MECHANIC_TYPE",
    "MOMENTUM_RAW_KEY",
    "MOMENTUM_RULE_REQUIREMENTS",
    "RuntimeDeferral",
    "compile_draconic_frenzy",
    "compile_draconic_momentum",
]

"""Compile lossless Core MC1 ability envelopes and explicit Action members.

The creature-level compiler authenticates one complete ``^.creature`` carrier
and retains every direct ``!.Ability`` occurrence in source order.  Structured
abilities remain duplicate-aware all the way through nested objects and
arrays, so repeated paragraph members are addressable evidence instead of a
mapping collision.  The lower-level compiler classifies only the five exact
Action tokens present in Monster Core.  Neither layer infers action costs from
prose, aliases, icons, missing fields, or Python truthiness.

Outputs keep consumer evidence separate from Player Core and Monster Core
provider-rule receipts.  Named effects, response windows, frequency ledgers,
and runtime activation remain typed deferrals; no registry or transition
handler is exported from this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, TypeAlias, final

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RawSourceValue,
)
from .source_authority import (
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
    canonical_json_bytes,
    canonical_raw_bytes,
    raw_member_sha256,
    raw_source_sha256,
)


FAMILY_ID = "explicit-action-costs"
MONSTER_CORE_SOURCE_ID = "core-mc1"

MAX_ABILITY_BYTES = 8_192
MAX_ABILITY_MEMBERS = 16
MAX_ABILITY_MEMBER_ORDINAL = 63
MAX_ADDRESS_STEPS = 64
MAX_PROVIDER_RULES = 5
MAX_CREATURE_ABILITIES = 64
MAX_ABILITY_OCCURRENCES = 128
MAX_ABILITY_OCCURRENCE_DEPTH = 24

ActionToken: TypeAlias = Literal[
    "single",
    "two",
    "three",
    "reaction",
    "free",
]
CompiledActionCost: TypeAlias = Literal[
    1,
    2,
    3,
    "reaction",
    "free",
]
CompiledActionKind: TypeAlias = Literal[
    "action",
    "activity",
    "reaction",
    "free-action",
]
AbilityEnvelopeKind: TypeAlias = Literal[
    "passive",
    "action",
    "activity",
    "reaction",
    "free-action",
]
AbilityEnvelopeShape: TypeAlias = Literal["prose", "structured"]
FieldRole: TypeAlias = Literal[
    "action",
    "description",
    "effect",
    "frequency",
    "requirements",
    "trigger",
    "other",
]
ResponseClassification: TypeAlias = Literal[
    "turn-action",
    "triggered-response",
    "source-link-required",
    "ambiguous-trigger",
]
FrequencyClassification: TypeAlias = Literal[
    "not-structured",
    "explicit",
    "ambiguous",
]
DeferralPhase: TypeAlias = Literal["source-link", "runtime"]
DeferralCategory: TypeAlias = Literal[
    "activation",
    "response-window",
    "frequency",
]


class ActionCostCompileError(ValueError):
    """An explicit Action member or its verified evidence is unsupported."""


@dataclass(frozen=True, slots=True)
class _ActionSemantics:
    token: ActionToken
    cost: CompiledActionCost
    kind: CompiledActionKind


_ACTION_SEMANTICS = MappingProxyType(
    {
        "single": _ActionSemantics("single", 1, "action"),
        "two": _ActionSemantics("two", 2, "activity"),
        "three": _ActionSemantics("three", 3, "activity"),
        "reaction": _ActionSemantics(
            "reaction",
            "reaction",
            "reaction",
        ),
        "free": _ActionSemantics("free", "free", "free-action"),
    }
)

_FIELD_ROLES = MappingProxyType(
    {
        "Action": "action",
        "Description": "description",
        "Effect": "effect",
        "Frequency": "frequency",
        "Requirements": "requirements",
        "Trigger": "trigger",
    }
)


def _paragraph_requirement(
    *,
    rule_id: str,
    source_id: str,
    locator: str,
    member_ordinal: int,
    member_sha256: str,
    value_sha256: str,
) -> RuleRequirement:
    return RuleRequirement(
        rule_id=rule_id,
        source_id=source_id,
        locator=locator,
        selection_path=(RawMemberStep("~.p", member_ordinal),),
        expected_member_sha256=member_sha256,
        expected_value_sha256=value_sha256,
    )


# These pins select only the exact provider text needed by this family.  The
# action-symbol targets are small structured records, so their complete raw
# objects are pinned.  The prose rules use one reviewed duplicate-aware
# paragraph selection rather than treating a whole page as one rule.
CREATURE_ACTION_FORMAT_RULE = _paragraph_requirement(
    rule_id="creature-action-format",
    source_id="core-mc1",
    locator="5.3",
    member_ordinal=2,
    member_sha256=(
        "bdcd3a660dd6aa4c8a9c38bfac8ed431"
        "2d270fe8707751f9543575c6ec46c59e"
    ),
    value_sha256=(
        "c1775ee3e85c0048a616f75d17c1de57"
        "2a3454311a908f83456d3d6e70ba9af9"
    ),
)
SINGLE_ACTION_TYPE_RULE = RuleRequirement(
    rule_id="single-action-type",
    source_id="core-pc1",
    locator="15.7",
    expected_block_sha256=(
        "682d8ac9dda1100a1b18c0de57fa544e"
        "673906d04eed1cf04d11cb3274c581d7"
    ),
)
TWO_ACTION_TYPE_RULE = RuleRequirement(
    rule_id="two-action-type",
    source_id="core-pc1",
    locator="15.8",
    expected_block_sha256=(
        "7f8b68bbb72b41cc84d14001622731441"
        "c2ca9ce246e24306924b2ed4d2669d1"
    ),
)
THREE_ACTION_TYPE_RULE = RuleRequirement(
    rule_id="three-action-type",
    source_id="core-pc1",
    locator="15.9",
    expected_block_sha256=(
        "61caee223356600db8c77dc1b25475198"
        "fdf92cabdc143e045a1fc60490c461b"
    ),
)
REACTION_ACTION_TYPE_RULE = RuleRequirement(
    rule_id="reaction-action-type",
    source_id="core-pc1",
    locator="15.10",
    expected_block_sha256=(
        "c7155356543459809c4dc24f511b895c"
        "b2c5d3f723cf9a81dbd8449d4cec5aa7"
    ),
)
FREE_ACTION_TYPE_RULE = RuleRequirement(
    rule_id="free-action-type",
    source_id="core-pc1",
    locator="15.11",
    expected_block_sha256=(
        "aa1a65febaf11d47dabc5b71842c4e40"
        "44c786facd7d8b65ed9e87e38c5f0ce0"
    ),
)
SINGLE_ACTION_ECONOMY_RULE = _paragraph_requirement(
    rule_id="single-action-economy",
    source_id="core-pc1",
    locator="15.3",
    member_ordinal=0,
    member_sha256=(
        "d31649c5dd6d77129fe6450aa13baaaa"
        "fbf09093f9d4f2ae792b138729a1c783"
    ),
    value_sha256=(
        "9cfc352a937e0c010fc08f5a43ab1089"
        "0c1bb7541f448150e5913aaa04c32b6f"
    ),
)
REACTION_ECONOMY_RULE = _paragraph_requirement(
    rule_id="reaction-economy",
    source_id="core-pc1",
    locator="15.4",
    member_ordinal=0,
    member_sha256=(
        "2838b66d9b67af8d6dc93e7283c2b70b"
        "f875b294731a729d6b703a649b7b04f2"
    ),
    value_sha256=(
        "3c322b82717e696930d1e72ee5c8305b"
        "57ef2fcee7816ab01c3395e1be71842b"
    ),
)
FREE_ACTION_ECONOMY_RULE = _paragraph_requirement(
    rule_id="free-action-economy",
    source_id="core-pc1",
    locator="15.5",
    member_ordinal=0,
    member_sha256=(
        "8dfcf9039bd4b13be617fe3774e79c0a"
        "f9920eef9cf5789c64770ba8e4ce1287"
    ),
    value_sha256=(
        "f7d70d6d3c6ce568af2bfe01ee1cccd"
        "7a73e19246cbda0919d688706c2046447"
    ),
)
ACTIVITY_ECONOMY_RULE = _paragraph_requirement(
    rule_id="activity-economy",
    source_id="core-pc1",
    locator="414.4",
    member_ordinal=2,
    member_sha256=(
        "8f275188d9032c525c520f173f6e8082"
        "9605f53d64690eb44c4a83521b9f9abb"
    ),
    value_sha256=(
        "347747935c693813fcb817fa21d1a111e"
        "aac453f0abaff7ba3c5bbad39838d02"
    ),
)
TRIGGER_LIMITATIONS_RULE = _paragraph_requirement(
    rule_id="trigger-limitations",
    source_id="core-pc1",
    locator="414.6",
    member_ordinal=0,
    member_sha256=(
        "f50caa7df2b30a1c3ab6a400162ab650"
        "080b9db44e6609e71144747c4df64984"
    ),
    value_sha256=(
        "c8162eee21e315ea0cbadabcbbded42dd"
        "a6ba560480e0a76d9b38c36cae41493"
    ),
)

PROVIDER_RULE_REQUIREMENTS = (
    CREATURE_ACTION_FORMAT_RULE,
    SINGLE_ACTION_TYPE_RULE,
    TWO_ACTION_TYPE_RULE,
    THREE_ACTION_TYPE_RULE,
    REACTION_ACTION_TYPE_RULE,
    FREE_ACTION_TYPE_RULE,
    SINGLE_ACTION_ECONOMY_RULE,
    REACTION_ECONOMY_RULE,
    FREE_ACTION_ECONOMY_RULE,
    ACTIVITY_ECONOMY_RULE,
    TRIGGER_LIMITATIONS_RULE,
)
_PROVIDER_RULE_BY_ID = MappingProxyType(
    {
        requirement.rule_id: requirement
        for requirement in PROVIDER_RULE_REQUIREMENTS
    }
)
_RULE_IDS_BY_TOKEN = MappingProxyType(
    {
        "single": (
            "creature-action-format",
            "single-action-type",
            "single-action-economy",
        ),
        "two": (
            "creature-action-format",
            "two-action-type",
            "activity-economy",
        ),
        "three": (
            "creature-action-format",
            "three-action-type",
            "activity-economy",
        ),
        "reaction": (
            "creature-action-format",
            "reaction-action-type",
            "reaction-economy",
            "trigger-limitations",
        ),
        "free": (
            "creature-action-format",
            "free-action-type",
            "free-action-economy",
            "trigger-limitations",
        ),
    }
)


def _semantics_for_token(
    token: object,
    /,
) -> _ActionSemantics:
    if type(token) is str:
        if token == "single":
            return _ActionSemantics("single", 1, "action")
        if token == "two":
            return _ActionSemantics("two", 2, "activity")
        if token == "three":
            return _ActionSemantics("three", 3, "activity")
        if token == "reaction":
            return _ActionSemantics(
                "reaction",
                "reaction",
                "reaction",
            )
        if token == "free":
            return _ActionSemantics("free", "free", "free-action")
    raise ActionCostCompileError(
        "Action token must be one exact Core MC1 scalar"
    )


def _field_role(
    raw_key: object,
    /,
) -> FieldRole:
    if type(raw_key) is not str:
        raise TypeError("explicit Action raw field key must be exact str")
    return {
        "Action": "action",
        "Description": "description",
        "Effect": "effect",
        "Frequency": "frequency",
        "Requirements": "requirements",
        "Trigger": "trigger",
    }.get(raw_key, "other")


def _ability_label(
    raw_key: object,
    /,
) -> str:
    if type(raw_key) is not str or not raw_key.startswith("!."):
        raise ActionCostCompileError(
            "explicit Action ability member is outside its grammar"
        )
    label = raw_key[2:]
    if (
        not label
        or label != label.strip()
        or not label.isprintable()
        or len(raw_key.encode("utf-8")) > 512
    ):
        raise ActionCostCompileError(
            "explicit Action ability member is outside its grammar"
        )
    return label


def _require_family_authority(
    authority: object,
    /,
) -> SourceAuthorityAdapter:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "explicit Action evidence requires exact "
            "SourceAuthorityAdapter"
        )
    scope = authority.allowed_source_ids
    if "core-mc1" not in scope or "core-pc1" not in scope:
        raise ActionCostCompileError(
            "explicit Action authority must select Core MC1 and PC1"
        )
    return authority


def _require_structured_field_text(
    value: object,
    role: FieldRole,
    /,
) -> str:
    if (
        role not in ("trigger", "frequency")
        or type(value) is not str
        or not value
        or value != value.strip()
        or not value.isprintable()
    ):
        raise ActionCostCompileError(
            f"explicit Action structured {role} must be "
            "non-empty trimmed printable text"
        )
    return value


def _require_one_ability_context(
    fields: tuple[ActionSourceField, ...],
    /,
) -> None:
    if not fields:
        return
    first = fields[0]
    first_address = first.receipt.address
    first_context = (
        first.receipt.ruleset,
        first.receipt.authority_digest,
        first_address.source_id,
        first_address.locator,
        first_address.section_id,
        first_address.target_path,
        first_address.carrier_path,
        first_address.selection_path[:-1],
        first_address.span,
    )
    if any(
        field.authority is not first.authority
        or (
            field.receipt.ruleset,
            field.receipt.authority_digest,
            field.receipt.address.source_id,
            field.receipt.address.locator,
            field.receipt.address.section_id,
            field.receipt.address.target_path,
            field.receipt.address.carrier_path,
            field.receipt.address.selection_path[:-1],
            field.receipt.address.span,
        )
        != first_context
        for field in fields
    ):
        raise ActionCostCompileError(
            "explicit Action metadata fields must share one exact ability"
        )


def _fresh_reviewed_rule_requirements() -> tuple[RuleRequirement, ...]:
    """Rebuild reviewed rules from literals, never mutable module bindings."""

    specs = (
        (
            "creature-action-format",
            "core-mc1",
            "5.3",
            "~.p",
            2,
            None,
            "bdcd3a660dd6aa4c8a9c38bfac8ed431"
            "2d270fe8707751f9543575c6ec46c59e",
            "c1775ee3e85c0048a616f75d17c1de57"
            "2a3454311a908f83456d3d6e70ba9af9",
        ),
        (
            "single-action-type",
            "core-pc1",
            "15.7",
            None,
            None,
            "682d8ac9dda1100a1b18c0de57fa544e"
            "673906d04eed1cf04d11cb3274c581d7",
            None,
            None,
        ),
        (
            "two-action-type",
            "core-pc1",
            "15.8",
            None,
            None,
            "7f8b68bbb72b41cc84d14001622731441"
            "c2ca9ce246e24306924b2ed4d2669d1",
            None,
            None,
        ),
        (
            "three-action-type",
            "core-pc1",
            "15.9",
            None,
            None,
            "61caee223356600db8c77dc1b25475198"
            "fdf92cabdc143e045a1fc60490c461b",
            None,
            None,
        ),
        (
            "reaction-action-type",
            "core-pc1",
            "15.10",
            None,
            None,
            "c7155356543459809c4dc24f511b895c"
            "b2c5d3f723cf9a81dbd8449d4cec5aa7",
            None,
            None,
        ),
        (
            "free-action-type",
            "core-pc1",
            "15.11",
            None,
            None,
            "aa1a65febaf11d47dabc5b71842c4e40"
            "44c786facd7d8b65ed9e87e38c5f0ce0",
            None,
            None,
        ),
        (
            "single-action-economy",
            "core-pc1",
            "15.3",
            "~.p",
            0,
            None,
            "d31649c5dd6d77129fe6450aa13baaaa"
            "fbf09093f9d4f2ae792b138729a1c783",
            "9cfc352a937e0c010fc08f5a43ab1089"
            "0c1bb7541f448150e5913aaa04c32b6f",
        ),
        (
            "reaction-economy",
            "core-pc1",
            "15.4",
            "~.p",
            0,
            None,
            "2838b66d9b67af8d6dc93e7283c2b70b"
            "f875b294731a729d6b703a649b7b04f2",
            "3c322b82717e696930d1e72ee5c8305b"
            "57ef2fcee7816ab01c3395e1be71842b",
        ),
        (
            "free-action-economy",
            "core-pc1",
            "15.5",
            "~.p",
            0,
            None,
            "8dfcf9039bd4b13be617fe3774e79c0a"
            "f9920eef9cf5789c64770ba8e4ce1287",
            "f7d70d6d3c6ce568af2bfe01ee1cccd"
            "7a73e19246cbda0919d688706c2046447",
        ),
        (
            "activity-economy",
            "core-pc1",
            "414.4",
            "~.p",
            2,
            None,
            "8f275188d9032c525c520f173f6e8082"
            "9605f53d64690eb44c4a83521b9f9abb",
            "347747935c693813fcb817fa21d1a111e"
            "aac453f0abaff7ba3c5bbad39838d02",
        ),
        (
            "trigger-limitations",
            "core-pc1",
            "414.6",
            "~.p",
            0,
            None,
            "f50caa7df2b30a1c3ab6a400162ab650"
            "080b9db44e6609e71144747c4df64984",
            "c8162eee21e315ea0cbadabcbbded42dd"
            "a6ba560480e0a76d9b38c36cae41493",
        ),
    )
    result: list[RuleRequirement] = []
    for (
        rule_id,
        source_id,
        locator,
        raw_key,
        member_ordinal,
        block_sha256,
        member_sha256,
        value_sha256,
    ) in specs:
        selection_path = (
            ()
            if raw_key is None
            else (RawMemberStep(raw_key, member_ordinal),)
        )
        result.append(
            RuleRequirement(
                rule_id=rule_id,
                source_id=source_id,
                locator=locator,
                selection_path=selection_path,
                expected_block_sha256=block_sha256,
                expected_member_sha256=member_sha256,
                expected_value_sha256=value_sha256,
            )
        )
    return tuple(result)


def _canonical_rule_requirements(
    token: object,
    /,
) -> tuple[RuleRequirement, ...]:
    _semantics_for_token(token)
    if token == "single":
        indices = (0, 1, 6)
    elif token == "two":
        indices = (0, 2, 9)
    elif token == "three":
        indices = (0, 3, 9)
    elif token == "reaction":
        indices = (0, 4, 7, 10)
    else:
        indices = (0, 5, 8, 10)
    reviewed = _fresh_reviewed_rule_requirements()
    return tuple(reviewed[index] for index in indices)


def _canonical_rule_requirement(
    rule_id: object,
    /,
) -> RuleRequirement:
    if type(rule_id) is not str:
        raise TypeError("provider rule id must be exact str")
    matches = tuple(
        item
        for item in _fresh_reviewed_rule_requirements()
        if item.rule_id == rule_id
    )
    if len(matches) != 1:
        raise ValueError("provider rule id is not reviewed")
    return matches[0]


def rule_requirements_for_action(
    token: ActionToken,
    /,
) -> tuple[RuleRequirement, ...]:
    """Return the exact reviewed provider rules for one exact token."""

    return _canonical_rule_requirements(token)


@final
@dataclass(frozen=True, slots=True)
class ActionSourceField:
    """One verified, ordered member of the selected ability."""

    authority: SourceAuthorityAdapter = field(
        repr=False,
        compare=False,
    )
    member_ordinal: int
    role: FieldRole
    raw_member: RawSourceMember
    receipt: SourceReceipt

    def __post_init__(self) -> None:
        if type(self) is not ActionSourceField:
            raise TypeError("ActionSourceField subclasses are not supported")
        authority = _require_family_authority(self.authority)
        if (
            type(self.member_ordinal) is not int
            or self.member_ordinal < 0
            or self.member_ordinal > 63
        ):
            raise ValueError(
                "ActionSourceField.member_ordinal is outside its bound"
            )
        if type(self.role) is not str or self.role not in (
            "action",
            "description",
            "effect",
            "frequency",
            "requirements",
            "trigger",
            "other",
        ):
            raise ValueError("ActionSourceField.role is invalid")
        if type(self.raw_member) is not RawSourceMember:
            raise TypeError(
                "ActionSourceField.raw_member must be exact RawSourceMember"
            )
        if type(self.receipt) is not SourceReceipt:
            raise TypeError(
                "ActionSourceField.receipt must be exact SourceReceipt"
            )
        SourceReceipt.as_serialized(self.receipt)
        address = self.receipt.address
        paths = (
            address.target_path,
            address.carrier_path,
            address.selection_path,
        )
        if (
            any(type(candidate) is not tuple for candidate in paths)
            or any(len(candidate) > 64 for candidate in paths)
            or sum(len(candidate) for candidate in paths) > 64
            or any(
                type(step) not in (RawMemberStep, RawIndexStep)
                for candidate in paths
                for step in candidate
            )
        ):
            raise ActionCostCompileError(
                "ActionSourceField address exceeds the family path bound"
            )
        path = address.selection_path
        if (
            type(path) is not tuple
            or len(path) != 2
            or type(path[0]) is not RawMemberStep
            or type(path[1]) is not RawMemberStep
        ):
            raise ValueError(
                "ActionSourceField receipt must select one exact member"
            )
        _ability_label(path[0].raw_key)
        step = path[-1]
        if (
            step.raw_key != self.raw_member.key
            or step.member_ordinal != self.member_ordinal
        ):
            raise ValueError(
                "ActionSourceField receipt path disagrees with raw member"
            )
        if self.role != _field_role(self.raw_member.key):
            raise ValueError(
                "ActionSourceField role disagrees with its raw member"
            )
        if self.role in ("trigger", "frequency"):
            _require_structured_field_text(
                self.raw_member.value,
                self.role,
            )
        verified = authority.reload(self.receipt)
        parent = VerifiedSourceCarrier.select(
            verified.carrier,
            (path[0],),
        )
        if type(parent) is not VerifiedSourceSelection:
            raise TypeError(
                "ActionSourceField parent ability selection is invalid"
            )
        authority.validate_selection(parent)
        raw_ability, _ability_step = _require_verified_ability(parent)
        action_members = tuple(
            (index, member)
            for index, member in enumerate(raw_ability.members)
            if member.key == "Action"
        )
        if len(action_members) != 1 or action_members[0][0] != 0:
            raise ActionCostCompileError(
                "ActionSourceField parent must have one first Action"
            )
        _semantics_for_token(action_members[0][1].value)
        if (
            self.member_ordinal >= len(raw_ability.members)
            or raw_ability.members[self.member_ordinal] != self.raw_member
        ):
            raise ActionCostCompileError(
                "ActionSourceField member does not replay in its ability"
            )
        if (
            verified.raw_member != self.raw_member
            or verified.raw_value != self.raw_member.value
            or canonical_json_bytes(
                SourceReceipt.as_serialized(verified.receipt)
            )
            != canonical_json_bytes(
                SourceReceipt.as_serialized(self.receipt)
            )
            or self.receipt.address.span is not None
            or self.receipt.member_sha256
            != raw_member_sha256(self.raw_member)
            or self.receipt.value_sha256
            != raw_source_sha256(self.raw_member.value)
            or self.receipt.selection_sha256
            != self.receipt.value_sha256
        ):
            raise ValueError(
                "ActionSourceField receipt hashes disagree with raw member"
            )

    def as_serialized(self) -> dict[str, Any]:
        ActionSourceField.__post_init__(self)
        return {
            "memberOrdinal": self.member_ordinal,
            "role": self.role,
            "rawKey": self.raw_member.key,
            "rawMemberJson": canonical_raw_bytes(
                RawSourceObject(members=(self.raw_member,))
            ).decode("utf-8"),
            "source": SourceReceipt.as_serialized(self.receipt),
        }


@final
@dataclass(frozen=True, slots=True)
class ResponseWindowMetadata:
    """Compile-time response shape without claiming executable timing."""

    classification: ResponseClassification
    action_cost: CompiledActionCost
    trigger_fields: tuple[ActionSourceField, ...]

    def __post_init__(self) -> None:
        if type(self) is not ResponseWindowMetadata:
            raise TypeError(
                "ResponseWindowMetadata subclasses are not supported"
            )
        if type(self.classification) is not str or self.classification not in (
            "turn-action",
            "triggered-response",
            "source-link-required",
            "ambiguous-trigger",
        ):
            raise ValueError(
                "ResponseWindowMetadata.classification is invalid"
            )
        if not (
            (
                type(self.action_cost) is int
                and self.action_cost in (1, 2, 3)
            )
            or (
                type(self.action_cost) is str
                and self.action_cost in ("reaction", "free")
            )
        ):
            raise ValueError(
                "ResponseWindowMetadata.action_cost is invalid"
            )
        if type(self.trigger_fields) is not tuple:
            raise TypeError(
                "ResponseWindowMetadata.trigger_fields must be a tuple"
            )
        if any(
            type(field) is not ActionSourceField
            or field.role != "trigger"
            for field in self.trigger_fields
        ):
            raise TypeError(
                "ResponseWindowMetadata.trigger_fields are invalid"
            )
        for field in self.trigger_fields:
            ActionSourceField.__post_init__(field)
        _require_one_ability_context(self.trigger_fields)
        if type(self.action_cost) is int:
            if self.trigger_fields:
                raise ValueError(
                    "turn Action response metadata cannot retain triggers"
                )
            expected = "turn-action"
        elif len(self.trigger_fields) == 1:
            expected = "triggered-response"
        elif not self.trigger_fields:
            expected = "source-link-required"
        else:
            expected = "ambiguous-trigger"
        if self.classification != expected:
            raise ValueError(
                "ResponseWindowMetadata.classification disagrees"
            )

    def as_serialized(self) -> dict[str, Any]:
        ResponseWindowMetadata.__post_init__(self)
        return {
            "classification": self.classification,
            "actionCost": self.action_cost,
            "triggerMemberOrdinals": [
                field.member_ordinal for field in self.trigger_fields
            ],
            "status": (
                "compiled"
                if self.classification
                in ("turn-action", "triggered-response")
                else "deferred"
            ),
        }


@final
@dataclass(frozen=True, slots=True)
class FrequencyMetadata:
    """Exact structured Frequency members and their compile-time status."""

    classification: FrequencyClassification
    fields: tuple[ActionSourceField, ...]

    def __post_init__(self) -> None:
        if type(self) is not FrequencyMetadata:
            raise TypeError("FrequencyMetadata subclasses are not supported")
        if type(self.classification) is not str or self.classification not in (
            "not-structured",
            "explicit",
            "ambiguous",
        ):
            raise ValueError("FrequencyMetadata.classification is invalid")
        if type(self.fields) is not tuple:
            raise TypeError("FrequencyMetadata.fields must be a tuple")
        if any(
            type(field) is not ActionSourceField
            or field.role != "frequency"
            for field in self.fields
        ):
            raise TypeError("FrequencyMetadata.fields are invalid")
        for field in self.fields:
            ActionSourceField.__post_init__(field)
        _require_one_ability_context(self.fields)
        expected = (
            "not-structured"
            if not self.fields
            else "explicit"
            if len(self.fields) == 1
            else "ambiguous"
        )
        if self.classification != expected:
            raise ValueError(
                "FrequencyMetadata.classification disagrees"
            )

    def as_serialized(self) -> dict[str, Any]:
        FrequencyMetadata.__post_init__(self)
        return {
            "classification": self.classification,
            "memberOrdinals": [
                field.member_ordinal for field in self.fields
            ],
            "runtimeLedgerRequired": bool(self.fields),
        }


@final
@dataclass(frozen=True, slots=True)
class DeferredActionCostMechanic:
    """One typed missing source-link or runtime contract."""

    dependency_id: str
    phase: DeferralPhase
    category: DeferralCategory
    required_contract: str

    def __post_init__(self) -> None:
        if type(self) is not DeferredActionCostMechanic:
            raise TypeError(
                "DeferredActionCostMechanic subclasses are not supported"
            )
        for field_name in ("dependency_id", "required_contract"):
            value = getattr(self, field_name)
            if (
                type(value) is not str
                or not value
                or value != value.strip()
                or len(value.encode("utf-8")) > 1_024
            ):
                raise ValueError(
                    f"DeferredActionCostMechanic.{field_name} is invalid"
                )
        if type(self.phase) is not str or self.phase not in (
            "source-link",
            "runtime",
        ):
            raise ValueError(
                "DeferredActionCostMechanic.phase is invalid"
            )
        if type(self.category) is not str or self.category not in (
            "activation",
            "response-window",
            "frequency",
        ):
            raise ValueError(
                "DeferredActionCostMechanic.category is invalid"
            )

    def as_serialized(self) -> dict[str, str]:
        DeferredActionCostMechanic.__post_init__(self)
        return {
            "id": self.dependency_id,
            "phase": self.phase,
            "category": self.category,
            "requiredContract": self.required_contract,
            "status": "deferred",
            "blocks": "registry-activation",
        }


@final
@dataclass(frozen=True, slots=True)
class ProviderRuleEvidence:
    """One verified provider receipt retained separately from the consumer."""

    authority: SourceAuthorityAdapter = field(
        repr=False,
        compare=False,
    )
    rule_id: str
    requirement: RuleRequirement
    receipt: SourceReceipt

    def __post_init__(self) -> None:
        if type(self) is not ProviderRuleEvidence:
            raise TypeError(
                "ProviderRuleEvidence subclasses are not supported"
            )
        authority = _require_family_authority(self.authority)
        if (
            type(self.rule_id) is not str
            or not self.rule_id
            or self.rule_id != self.rule_id.strip()
        ):
            raise ValueError(
                "ProviderRuleEvidence.rule_id must be non-empty and trimmed"
            )
        if type(self.receipt) is not SourceReceipt:
            raise TypeError(
                "ProviderRuleEvidence.receipt must be exact SourceReceipt"
            )
        if type(self.requirement) is not RuleRequirement:
            raise TypeError(
                "ProviderRuleEvidence.requirement must be exact "
                "RuleRequirement"
            )
        reviewed = _canonical_rule_requirement(self.rule_id)
        if (
            canonical_json_bytes(
                RuleRequirement.as_serialized(self.requirement)
            )
            != canonical_json_bytes(
                RuleRequirement.as_serialized(reviewed)
            )
        ):
            raise ValueError(
                "ProviderRuleEvidence requirement is not the reviewed rule"
            )
        receipt = SourceReceipt.from_serialized(
            SourceReceipt.as_serialized(self.receipt)
        )
        verified = authority.reload(receipt)
        if canonical_json_bytes(
            SourceReceipt.as_serialized(verified.receipt)
        ) != canonical_json_bytes(
            SourceReceipt.as_serialized(receipt)
        ):
            raise ValueError(
                "ProviderRuleEvidence receipt disagrees with authority"
            )
        address = receipt.address
        if (
            address.source_id != reviewed.source_id
            or address.locator != reviewed.locator
            or address.carrier_path != reviewed.carrier_path
            or address.selection_path != reviewed.selection_path
            or address.span != reviewed.span
        ):
            raise ValueError(
                "ProviderRuleEvidence receipt address disagrees with "
                "its reviewed rule"
            )
        reviewed_hashes = (
            (reviewed.expected_block_sha256, receipt.block_sha256),
            (reviewed.expected_member_sha256, receipt.member_sha256),
            (reviewed.expected_value_sha256, receipt.value_sha256),
            (
                reviewed.expected_selection_sha256,
                receipt.selection_sha256,
            ),
        )
        if any(
            expected is not None and expected != actual
            for expected, actual in reviewed_hashes
        ):
            raise ValueError(
                "ProviderRuleEvidence receipt hashes disagree with "
                "its reviewed rule"
            )

    def as_serialized(self) -> dict[str, Any]:
        ProviderRuleEvidence.__post_init__(self)
        return {
            "ruleId": self.rule_id,
            "requirement": RuleRequirement.as_serialized(
                self.requirement
            ),
            "source": SourceReceipt.as_serialized(self.receipt),
        }


@final
@dataclass(frozen=True, slots=True)
class CompiledExplicitActionCost:
    """One lossless, provider-linked explicit creature Action declaration.

    The retained authority inputs are intentionally not serialized.  They
    make construction and every later serialization replay the public fields
    from authenticated source instead of trusting a frozen dataclass as an
    issuance seal.
    """

    authority: SourceAuthorityAdapter = field(repr=False, compare=False)
    source: VerifiedSourceSelection = field(repr=False, compare=False)
    verified_provider_rules: tuple[VerifiedRuleReceipt, ...] = field(
        repr=False,
        compare=False,
    )
    ability_label: str
    token: ActionToken
    action_cost: CompiledActionCost
    kind: CompiledActionKind
    raw_ability: RawSourceObject
    ability_receipt: SourceReceipt
    fields: tuple[ActionSourceField, ...]
    provider_rules: tuple[ProviderRuleEvidence, ...]
    response_window: ResponseWindowMetadata
    frequency: FrequencyMetadata
    deferrals: tuple[DeferredActionCostMechanic, ...]

    def __post_init__(self) -> None:
        if type(self) is not CompiledExplicitActionCost:
            raise TypeError(
                "CompiledExplicitActionCost subclasses are not supported"
            )
        if type(self.authority) is not SourceAuthorityAdapter:
            raise TypeError(
                "CompiledExplicitActionCost.authority must be exact "
                "SourceAuthorityAdapter"
            )
        scope = self.authority.allowed_source_ids
        if "core-mc1" not in scope or "core-pc1" not in scope:
            raise ValueError(
                "CompiledExplicitActionCost authority scope is invalid"
            )
        if type(self.source) is not VerifiedSourceSelection:
            raise TypeError(
                "CompiledExplicitActionCost.source must be exact "
                "VerifiedSourceSelection"
            )
        if (
            type(self.verified_provider_rules) is not tuple
            or not self.verified_provider_rules
            or len(self.verified_provider_rules) > 5
            or any(
                type(rule) is not VerifiedRuleReceipt
                for rule in self.verified_provider_rules
            )
        ):
            raise TypeError(
                "CompiledExplicitActionCost.verified_provider_rules "
                "are invalid"
            )
        self.authority.validate_selection(self.source)
        raw_ability, ability_step = _require_verified_ability(self.source)
        action_members = tuple(
            (index, member)
            for index, member in enumerate(raw_ability.members)
            if member.key == "Action"
        )
        if len(action_members) != 1 or action_members[0][0] != 0:
            raise ValueError(
                "CompiledExplicitActionCost source has no unique first Action"
            )
        source_token = action_members[0][1].value
        semantics = _semantics_for_token(source_token)
        canonical_fields = _field_evidence(
            self.authority,
            self.source,
            ability_step,
            raw_ability,
        )
        canonical_providers = _require_provider_rules(
            authority=self.authority,
            source=self.source,
            token=semantics.token,
            provider_rules=self.verified_provider_rules,
            consumer_receipt=canonical_fields[0].receipt,
        )
        canonical_response = _response_metadata(
            semantics.cost,
            canonical_fields,
        )
        canonical_frequency = _frequency_metadata(canonical_fields)
        canonical_deferrals = _deferrals(
            canonical_response,
            canonical_frequency,
        )
        if (
            type(self.ability_label) is not str
            or self.ability_label != _ability_label(ability_step.raw_key)
        ):
            raise ValueError(
                "CompiledExplicitActionCost.ability_label disagrees "
                "with source"
            )
        if self.token != semantics.token or type(self.token) is not str:
            raise ValueError(
                "CompiledExplicitActionCost.token disagrees with source"
            )
        if (
            self.action_cost != semantics.cost
            or type(self.action_cost) is not type(semantics.cost)
            or type(self.kind) is not str
            or self.kind != semantics.kind
        ):
            raise ValueError(
                "CompiledExplicitActionCost semantics disagree"
            )
        if type(self.raw_ability) is not RawSourceObject:
            raise TypeError(
                "CompiledExplicitActionCost.raw_ability must be exact "
                "RawSourceObject"
            )
        if (
            canonical_raw_bytes(self.raw_ability)
            != canonical_raw_bytes(raw_ability)
        ):
            raise ValueError(
                "CompiledExplicitActionCost.raw_ability disagrees with source"
            )
        if type(self.ability_receipt) is not SourceReceipt:
            raise TypeError(
                "CompiledExplicitActionCost.ability_receipt must be exact "
                "SourceReceipt"
            )
        if (
            canonical_json_bytes(
                SourceReceipt.as_serialized(self.ability_receipt)
            )
            != canonical_json_bytes(
                SourceReceipt.as_serialized(self.source.receipt)
            )
        ):
            raise ValueError(
                "CompiledExplicitActionCost.ability_receipt disagrees "
                "with source"
            )
        if (
            type(self.fields) is not tuple
            or len(self.fields) != len(canonical_fields)
            or any(
                type(field) is not ActionSourceField
                or field.authority is not self.authority
                for field in self.fields
            )
        ):
            raise TypeError(
                "CompiledExplicitActionCost.fields are invalid"
            )
        if canonical_json_bytes(
            [
                ActionSourceField.as_serialized(item)
                for item in self.fields
            ]
        ) != canonical_json_bytes(
            [
                ActionSourceField.as_serialized(item)
                for item in canonical_fields
            ]
        ):
            raise ValueError(
                "CompiledExplicitActionCost.fields disagree with authority"
            )
        if (
            type(self.provider_rules) is not tuple
            or len(self.provider_rules) != len(canonical_providers)
            or any(
                type(rule) is not ProviderRuleEvidence
                or rule.authority is not self.authority
                for rule in self.provider_rules
            )
        ):
            raise TypeError(
                "CompiledExplicitActionCost.provider_rules are invalid"
            )
        if canonical_json_bytes(
            [
                ProviderRuleEvidence.as_serialized(item)
                for item in self.provider_rules
            ]
        ) != canonical_json_bytes(
            [
                ProviderRuleEvidence.as_serialized(item)
                for item in canonical_providers
            ]
        ):
            raise ValueError(
                "CompiledExplicitActionCost.provider_rules disagree "
                "with authority"
            )
        if type(self.response_window) is not ResponseWindowMetadata:
            raise TypeError(
                "CompiledExplicitActionCost.response_window is invalid"
            )
        if any(
            field.authority is not self.authority
            for field in self.response_window.trigger_fields
        ):
            raise ValueError(
                "CompiledExplicitActionCost response authority disagrees"
            )
        expected_trigger_fields = tuple(
            field for field in self.fields if field.role == "trigger"
        )
        if canonical_json_bytes(
            [
                ActionSourceField.as_serialized(field)
                for field in self.response_window.trigger_fields
            ]
        ) != canonical_json_bytes(
            [
                ActionSourceField.as_serialized(field)
                for field in expected_trigger_fields
            ]
        ):
            raise ValueError(
                "CompiledExplicitActionCost response fields disagree"
            )
        if canonical_json_bytes(
            ResponseWindowMetadata.as_serialized(self.response_window)
        ) != canonical_json_bytes(
            ResponseWindowMetadata.as_serialized(canonical_response)
        ):
            raise ValueError(
                "CompiledExplicitActionCost response metadata disagrees"
            )
        if type(self.frequency) is not FrequencyMetadata:
            raise TypeError(
                "CompiledExplicitActionCost.frequency is invalid"
            )
        if any(
            field.authority is not self.authority
            for field in self.frequency.fields
        ):
            raise ValueError(
                "CompiledExplicitActionCost frequency authority disagrees"
            )
        expected_frequency_fields = tuple(
            field for field in self.fields if field.role == "frequency"
        )
        if canonical_json_bytes(
            [
                ActionSourceField.as_serialized(field)
                for field in self.frequency.fields
            ]
        ) != canonical_json_bytes(
            [
                ActionSourceField.as_serialized(field)
                for field in expected_frequency_fields
            ]
        ):
            raise ValueError(
                "CompiledExplicitActionCost frequency fields disagree"
            )
        if canonical_json_bytes(
            FrequencyMetadata.as_serialized(self.frequency)
        ) != canonical_json_bytes(
            FrequencyMetadata.as_serialized(canonical_frequency)
        ):
            raise ValueError(
                "CompiledExplicitActionCost frequency metadata disagrees"
            )
        if type(self.deferrals) is not tuple or any(
            type(item) is not DeferredActionCostMechanic
            for item in self.deferrals
        ):
            raise TypeError(
                "CompiledExplicitActionCost.deferrals are invalid"
            )
        if len(self.deferrals) != len(canonical_deferrals):
            raise ValueError(
                "CompiledExplicitActionCost.deferrals are incomplete"
            )
        if canonical_json_bytes(
            [
                DeferredActionCostMechanic.as_serialized(item)
                for item in self.deferrals
            ]
        ) != canonical_json_bytes(
            [
                DeferredActionCostMechanic.as_serialized(item)
                for item in canonical_deferrals
            ]
        ):
            raise ValueError(
                "CompiledExplicitActionCost.deferrals disagree"
            )

    @property
    def action_field(self) -> ActionSourceField:
        return self.fields[0]

    @property
    def consumer_receipt(self) -> SourceReceipt:
        return self.action_field.receipt

    def fields_for_role(
        self,
        role: FieldRole,
        /,
    ) -> tuple[ActionSourceField, ...]:
        return tuple(field for field in self.fields if field.role == role)

    @property
    def descriptions(self) -> tuple[ActionSourceField, ...]:
        return self.fields_for_role("description")

    @property
    def effects(self) -> tuple[ActionSourceField, ...]:
        return self.fields_for_role("effect")

    @property
    def frequencies(self) -> tuple[ActionSourceField, ...]:
        return self.fields_for_role("frequency")

    @property
    def requirements(self) -> tuple[ActionSourceField, ...]:
        return self.fields_for_role("requirements")

    @property
    def triggers(self) -> tuple[ActionSourceField, ...]:
        return self.fields_for_role("trigger")

    def as_serialized(self) -> dict[str, Any]:
        CompiledExplicitActionCost.__post_init__(self)
        return {
            "family": "explicit-action-costs",
            "abilityLabel": self.ability_label,
            "token": self.token,
            "actionCost": self.action_cost,
            "kind": self.kind,
            "rawAbilityJson": canonical_raw_bytes(
                self.raw_ability
            ).decode("utf-8"),
            "abilitySource": SourceReceipt.as_serialized(
                self.ability_receipt
            ),
            "consumerSource": SourceReceipt.as_serialized(
                self.consumer_receipt
            ),
            "fields": [
                field.as_serialized() for field in self.fields
            ],
            "providerRules": [
                rule.as_serialized() for rule in self.provider_rules
            ],
            "responseWindow": self.response_window.as_serialized(),
            "frequency": self.frequency.as_serialized(),
            "deferred": [
                deferral.as_serialized()
                for deferral in self.deferrals
            ],
            "activation": "compile-only",
        }


def _require_verified_ability(
    source: VerifiedSourceSelection,
) -> tuple[RawSourceObject, RawMemberStep]:
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "explicit Action compiler requires exact "
            "VerifiedSourceSelection"
        )
    if type(source.carrier) is not VerifiedSourceCarrier:
        raise TypeError(
            "explicit Action compiler requires an exact verified carrier"
        )
    address = source.address
    paths = (
        address.target_path,
        address.carrier_path,
        address.selection_path,
    )
    if any(type(path) is not tuple for path in paths):
        raise TypeError("verified Action address paths must be tuples")
    if any(len(path) > 64 for path in paths):
        raise ActionCostCompileError(
            "verified Action address exceeds the family path bound"
        )
    if sum(len(path) for path in paths) > 64:
        raise ActionCostCompileError(
            "verified Action address exceeds the combined path bound"
        )
    for path in paths:
        if any(
            type(step) not in (RawMemberStep, RawIndexStep)
            for step in path
        ):
            raise TypeError(
                "verified Action address contains a non-exact path step"
            )
    if (
        source.carrier.source_id != "core-mc1"
        or address.source_id != "core-mc1"
    ):
        raise ActionCostCompileError(
            "explicit Action source must be Core MC1"
        )
    if (
        not address.carrier_path
        or type(address.carrier_path[-1]) is not RawMemberStep
        or address.carrier_path[-1].raw_key != "^.creature"
    ):
        raise ActionCostCompileError(
            "explicit Action carrier must be one exact creature block"
        )
    if (
        len(address.selection_path) != 1
        or type(address.selection_path[0]) is not RawMemberStep
    ):
        raise ActionCostCompileError(
            "explicit Action selection must be one direct ability member"
        )
    ability_step = address.selection_path[0]
    if (
        ability_step.member_ordinal > 63
    ):
        raise ActionCostCompileError(
            "explicit Action ability member is outside its grammar"
        )
    _ability_label(ability_step.raw_key)
    if type(source.raw_member) is not RawSourceMember:
        raise TypeError(
            "explicit Action ability must retain its exact raw member"
        )
    if (
        source.raw_member.key != ability_step.raw_key
        or type(source.raw_value) is not RawSourceObject
        or source.raw_member.value != source.raw_value
    ):
        raise ActionCostCompileError(
            "explicit Action ability selection disagrees with its raw member"
        )
    carrier_members = source.carrier.raw_block.members
    if ability_step.member_ordinal >= len(carrier_members):
        raise ActionCostCompileError(
            "explicit Action ability ordinal is out of range"
        )
    if carrier_members[ability_step.member_ordinal] != source.raw_member:
        raise ActionCostCompileError(
            "explicit Action ability ordinal does not replay"
        )
    if (
        source.member_sha256 != raw_member_sha256(source.raw_member)
        or source.value_sha256 != raw_source_sha256(source.raw_value)
        or source.selection_sha256 != source.value_sha256
    ):
        raise ActionCostCompileError(
            "explicit Action verified hashes do not replay"
        )
    raw_ability = source.raw_value
    if not 1 <= len(raw_ability.members) <= 16:
        raise ActionCostCompileError(
            "explicit Action ability exceeds its member bound"
        )
    if len(canonical_raw_bytes(raw_ability)) > 8_192:
        raise ActionCostCompileError(
            "explicit Action ability exceeds its byte bound"
        )
    return raw_ability, ability_step


def _field_evidence(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    ability_step: RawMemberStep,
    raw_ability: RawSourceObject,
) -> tuple[ActionSourceField, ...]:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("field evidence requires exact source authority")
    result: list[ActionSourceField] = []
    for member_ordinal, raw_member in enumerate(raw_ability.members):
        if member_ordinal > 63:
            raise ActionCostCompileError(
                "explicit Action field ordinal exceeds its bound"
            )
        selection_path = (
            ability_step,
            RawMemberStep(raw_member.key, member_ordinal),
        )
        if len(selection_path) > 64:
            raise ActionCostCompileError(
                "explicit Action field path exceeds its bound"
            )
        selected = VerifiedSourceCarrier.select(
            source.carrier,
            selection_path,
        )
        if type(selected) is not VerifiedSourceSelection:
            raise TypeError(
                "verified carrier returned a non-exact selection"
            )
        authority.validate_selection(selected)
        if (
            selected.raw_member != raw_member
            or selected.raw_value != raw_member.value
            or selected.member_sha256 != raw_member_sha256(raw_member)
            or selected.value_sha256
            != raw_source_sha256(raw_member.value)
        ):
            raise ActionCostCompileError(
                "explicit Action field selection does not replay"
            )
        role = _field_role(raw_member.key)
        result.append(
            ActionSourceField(
                authority=authority,
                member_ordinal=member_ordinal,
                role=role,
                raw_member=raw_member,
                receipt=selected.receipt,
            )
        )
    return tuple(result)


def _require_provider_rules(
    *,
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    token: ActionToken,
    provider_rules: tuple[VerifiedRuleReceipt, ...],
    consumer_receipt: SourceReceipt,
) -> tuple[ProviderRuleEvidence, ...]:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "explicit Action compiler requires exact SourceAuthorityAdapter"
        )
    if type(provider_rules) is not tuple:
        raise TypeError(
            "explicit Action provider rules must be an exact tuple"
        )
    expected = _canonical_rule_requirements(token)
    if (
        len(provider_rules) != len(expected)
        or len(provider_rules) > 5
    ):
        raise ActionCostCompileError(
            "explicit Action provider rule set is incomplete or expanded"
        )
    authority.require_shared_authority(source, provider_rules)
    result: list[ProviderRuleEvidence] = []
    for index, (provided, requirement) in enumerate(
        zip(provider_rules, expected, strict=True)
    ):
        if type(provided) is not VerifiedRuleReceipt:
            raise TypeError(
                f"provider rule {index} must be exact VerifiedRuleReceipt"
            )
        authority.validate_rule(provided)
        if type(provided.selection) is not VerifiedSourceSelection:
            raise TypeError(
                f"provider rule {index} has an invalid verified selection"
            )
        if type(provided.receipt) is not SourceReceipt:
            raise TypeError(
                f"provider rule {index} has an invalid source receipt"
            )
        selection = provided.selection
        receipt = provided.receipt
        address = selection.address
        if (
            provided.rule_id != requirement.rule_id
            or canonical_json_bytes(
                RuleRequirement.as_serialized(provided.requirement)
            )
            != canonical_json_bytes(
                RuleRequirement.as_serialized(requirement)
            )
            or receipt != selection.receipt
            or address.source_id != requirement.source_id
            or address.locator != requirement.locator
            or address.carrier_path != requirement.carrier_path
            or address.selection_path != requirement.selection_path
            or address.span != requirement.span
        ):
            raise ActionCostCompileError(
                f"provider rule {index} disagrees with reviewed identity"
            )
        if (
            receipt.authority_digest
            != source.carrier.authority_digest
            or selection.carrier.authority_digest
            != source.carrier.authority_digest
        ):
            raise ActionCostCompileError(
                f"provider rule {index} belongs to another authority"
            )
        expected_hashes = (
            (
                requirement.expected_block_sha256,
                selection.block_sha256,
            ),
            (
                requirement.expected_member_sha256,
                selection.member_sha256,
            ),
            (
                requirement.expected_value_sha256,
                selection.value_sha256,
            ),
            (
                requirement.expected_selection_sha256,
                selection.selection_sha256,
            ),
        )
        if any(
            reviewed is not None and reviewed != actual
            for reviewed, actual in expected_hashes
        ):
            raise ActionCostCompileError(
                f"provider rule {index} differs from reviewed source"
            )
        if receipt.digest == consumer_receipt.digest:
            raise ActionCostCompileError(
                "provider rule receipt cannot substitute for consumer source"
            )
        result.append(
            ProviderRuleEvidence(
                authority=authority,
                rule_id=provided.rule_id,
                requirement=requirement,
                receipt=receipt,
            )
        )
    return tuple(result)


def _response_metadata(
    cost: CompiledActionCost,
    fields: tuple[ActionSourceField, ...],
) -> ResponseWindowMetadata:
    triggers = tuple(
        field for field in fields if field.role == "trigger"
    )
    if cost in (1, 2, 3):
        if triggers:
            raise ActionCostCompileError(
                "turn action has an unsupported structured Trigger"
            )
        classification: ResponseClassification = "turn-action"
    elif len(triggers) == 1:
        classification = "triggered-response"
    elif not triggers:
        # This deliberately does not assert that a free action is untriggered:
        # two reviewed Core MC1 records have flattened structured clauses, and
        # other families can own inherited or family-specific response text.
        classification = "source-link-required"
    else:
        classification = "ambiguous-trigger"
    return ResponseWindowMetadata(
        classification=classification,
        action_cost=cost,
        trigger_fields=triggers,
    )


def _frequency_metadata(
    fields: tuple[ActionSourceField, ...],
) -> FrequencyMetadata:
    frequencies = tuple(
        field for field in fields if field.role == "frequency"
    )
    if not frequencies:
        classification: FrequencyClassification = "not-structured"
    elif len(frequencies) == 1:
        classification = "explicit"
    else:
        classification = "ambiguous"
    return FrequencyMetadata(
        classification=classification,
        fields=frequencies,
    )


def _deferrals(
    response: ResponseWindowMetadata,
    frequency: FrequencyMetadata,
) -> tuple[DeferredActionCostMechanic, ...]:
    result = [
        DeferredActionCostMechanic(
            dependency_id="explicit-action-runtime-integration",
            phase="runtime",
            category="activation",
            required_contract=(
                "shared action-economy and activity transition integration"
            ),
        )
    ]
    if response.action_cost in ("reaction", "free"):
        result.append(
            DeferredActionCostMechanic(
                dependency_id="response-window-runtime",
                phase="runtime",
                category="response-window",
                required_contract=(
                    "one authoritative trigger event and response-window "
                    "ownership, ordering, and consumption contract"
                ),
            )
        )
        if response.classification != "triggered-response":
            result.append(
                DeferredActionCostMechanic(
                    dependency_id="structured-trigger-source-link",
                    phase="source-link",
                    category="response-window",
                    required_contract=(
                        "family-specific or repaired structured Trigger "
                        "evidence; prose is not parsed by this family"
                    ),
                )
            )
    if frequency.fields:
        result.append(
            DeferredActionCostMechanic(
                dependency_id="frequency-ledger-runtime",
                phase="runtime",
                category="frequency",
                required_contract=(
                    "source-owned per-turn, per-round, per-encounter, and "
                    "per-day use ledger"
                ),
            )
        )
    if frequency.classification == "ambiguous":
        result.append(
            DeferredActionCostMechanic(
                dependency_id="frequency-source-ambiguity",
                phase="source-link",
                category="frequency",
                required_contract=(
                    "one unambiguous structured Frequency declaration"
                ),
            )
        )
    return tuple(result)


def compile_explicit_action_cost(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    provider_rules: tuple[VerifiedRuleReceipt, ...],
    /,
) -> CompiledExplicitActionCost:
    """Compile one verified direct ``!.Ability`` Action declaration."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "explicit Action compiler requires exact SourceAuthorityAdapter"
        )
    scope = authority.allowed_source_ids
    if "core-mc1" not in scope or "core-pc1" not in scope:
        raise ActionCostCompileError(
            "explicit Action authority must select Core MC1 and PC1"
        )
    authority.validate_selection(source)
    raw_ability, ability_step = _require_verified_ability(source)
    action_members = tuple(
        (index, member)
        for index, member in enumerate(raw_ability.members)
        if member.key == "Action"
    )
    if len(action_members) != 1:
        raise ActionCostCompileError(
            "explicit Action ability must contain exactly one Action member"
        )
    action_ordinal, action_member = action_members[0]
    if action_ordinal != 0:
        raise ActionCostCompileError(
            "explicit Action must be the first ordered ability member"
        )
    token = action_member.value
    if type(token) is not str:
        raise ActionCostCompileError(
            "Action must be one exact scalar token: single, two, three, "
            "reaction, or free"
        )
    semantics = _semantics_for_token(token)
    fields = _field_evidence(
        authority,
        source,
        ability_step,
        raw_ability,
    )
    action_field = fields[0]
    if (
        action_field.role != "action"
        or action_field.raw_member != action_member
    ):
        raise ActionCostCompileError(
            "compiled Action field disagrees with ordered source"
        )
    providers = _require_provider_rules(
        authority=authority,
        source=source,
        token=semantics.token,
        provider_rules=provider_rules,
        consumer_receipt=action_field.receipt,
    )
    response = _response_metadata(semantics.cost, fields)
    frequency = _frequency_metadata(fields)
    return CompiledExplicitActionCost(
        authority=authority,
        source=source,
        verified_provider_rules=provider_rules,
        ability_label=_ability_label(ability_step.raw_key),
        token=semantics.token,
        action_cost=semantics.cost,
        kind=semantics.kind,
        raw_ability=raw_ability,
        ability_receipt=source.receipt,
        fields=fields,
        provider_rules=providers,
        response_window=response,
        frequency=frequency,
        deferrals=_deferrals(response, frequency),
    )


@final
@dataclass(frozen=True, slots=True)
class AbilitySourceOccurrence:
    """One exact ordered object-member occurrence inside an ability.

    ``relative_path`` begins at the selected ``!.Ability`` value.  It can
    therefore retain repeated ``~.p`` members and members reached through
    nested arrays without converting either object to a mapping.
    """

    authority: SourceAuthorityAdapter = field(repr=False, compare=False)
    ability_source: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )
    occurrence_ordinal: int
    relative_path: tuple[RawMemberStep | RawIndexStep, ...]
    raw_member: RawSourceMember
    receipt: SourceReceipt

    def __post_init__(self) -> None:
        if type(self) is not AbilitySourceOccurrence:
            raise TypeError(
                "AbilitySourceOccurrence subclasses are not supported"
            )
        authority = _require_family_authority(self.authority)
        if type(self.ability_source) is not VerifiedSourceSelection:
            raise TypeError(
                "AbilitySourceOccurrence ability source must be an exact "
                "VerifiedSourceSelection"
        )
        authority.validate_selection(self.ability_source)
        _require_ability_envelope_address(
            self.ability_source,
            reserved_steps=0,
        )
        if (
            type(self.occurrence_ordinal) is not int
            or self.occurrence_ordinal < 0
            or self.occurrence_ordinal >= 128
        ):
            raise ValueError(
                "AbilitySourceOccurrence ordinal is outside its bound"
            )
        if (
            type(self.relative_path) is not tuple
            or not self.relative_path
            or len(self.relative_path) > 24
            or type(self.relative_path[-1]) is not RawMemberStep
            or any(
                type(step) not in (RawMemberStep, RawIndexStep)
                for step in self.relative_path
            )
        ):
            raise ValueError(
                "AbilitySourceOccurrence path is invalid"
            )
        for step in self.relative_path:
            if type(step) is RawMemberStep:
                RawMemberStep.__post_init__(step)
            else:
                RawIndexStep.__post_init__(step)
        if type(self.raw_member) is not RawSourceMember:
            raise TypeError(
                "AbilitySourceOccurrence raw member must be exact"
            )
        if type(self.raw_member.key) is not str:
            raise TypeError(
                "AbilitySourceOccurrence raw key must be exact str"
            )
        if type(self.receipt) is not SourceReceipt:
            raise TypeError(
                "AbilitySourceOccurrence receipt must be exact"
            )
        address = self.ability_source.address
        full_path = (
            *address.selection_path,
            *self.relative_path,
        )
        if (
            len(full_path) > 64
            or len(address.target_path)
            + len(address.carrier_path)
            + len(full_path)
            > 64
        ):
            raise ActionCostCompileError(
                "ability occurrence address exceeds its bound"
            )
        selected = VerifiedSourceCarrier.select(
            self.ability_source.carrier,
            full_path,
        )
        if type(selected) is not VerifiedSourceSelection:
            raise TypeError(
                "ability occurrence selection is invalid"
            )
        authority.validate_selection(selected)
        last = self.relative_path[-1]
        ordered_occurrences = _walk_ability_occurrence_members(
            self.ability_source.raw_value
        )
        if self.occurrence_ordinal >= len(ordered_occurrences):
            raise ValueError(
                "ability occurrence disagrees with authority"
            )
        canonical_path, canonical_member = ordered_occurrences[
            self.occurrence_ordinal
        ]
        if (
            self.relative_path != canonical_path
            or raw_member_sha256(self.raw_member)
            != raw_member_sha256(canonical_member)
            or last.raw_key != self.raw_member.key
            or selected.member_sha256
            != raw_member_sha256(self.raw_member)
            or selected.value_sha256
            != raw_source_sha256(self.raw_member.value)
            or canonical_json_bytes(
                SourceReceipt.as_serialized(selected.receipt)
            )
            != canonical_json_bytes(
                SourceReceipt.as_serialized(self.receipt)
            )
        ):
            raise ValueError(
                "ability occurrence disagrees with authority"
            )

    def as_serialized(self) -> dict[str, Any]:
        AbilitySourceOccurrence.__post_init__(self)
        return {
            "occurrenceOrdinal": self.occurrence_ordinal,
            "relativePath": [
                (
                    RawMemberStep.as_serialized(step)
                    if type(step) is RawMemberStep
                    else RawIndexStep.as_serialized(step)
                )
                for step in self.relative_path
            ],
            "rawKey": self.raw_member.key,
            "rawMemberJson": canonical_raw_bytes(
                RawSourceObject((self.raw_member,))
            ).decode("utf-8"),
            "source": SourceReceipt.as_serialized(self.receipt),
        }

    def __copy__(self) -> AbilitySourceOccurrence:
        raise TypeError("AbilitySourceOccurrence cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> AbilitySourceOccurrence:
        raise TypeError("AbilitySourceOccurrence cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("AbilitySourceOccurrence cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("AbilitySourceOccurrence cannot be pickled")


@final
@dataclass(frozen=True, slots=True)
class AbilityActionEnvelope:
    """Typed action-economy claim for one exact ability occurrence."""

    authority: SourceAuthorityAdapter = field(repr=False, compare=False)
    ability_source: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )
    explicit_action: CompiledExplicitActionCost | None = field(
        repr=False,
        compare=False,
    )
    token: ActionToken | None
    action_cost: CompiledActionCost | None
    kind: AbilityEnvelopeKind
    action_member_ordinal: int | None

    def __post_init__(self) -> None:
        if type(self) is not AbilityActionEnvelope:
            raise TypeError(
                "AbilityActionEnvelope subclasses are not supported"
            )
        authority = _require_family_authority(self.authority)
        if type(self.ability_source) is not VerifiedSourceSelection:
            raise TypeError(
                "AbilityActionEnvelope source must be exact "
                "VerifiedSourceSelection"
        )
        authority.validate_selection(self.ability_source)
        _require_ability_envelope_address(
            self.ability_source,
            reserved_steps=0,
        )
        if type(self.kind) is not str:
            raise TypeError(
                "AbilityActionEnvelope kind must be exact str"
            )
        raw_value = self.ability_source.raw_value
        shape = _require_ability_envelope_value(raw_value)
        if shape == "prose":
            action_members: tuple[
                tuple[int, RawSourceMember], ...
            ] = ()
        else:
            action_members = tuple(
                (ordinal, member)
                for ordinal, member in enumerate(raw_value.members)
                if member.key == "Action"
            )
        if not action_members:
            if (
                self.explicit_action is not None
                or self.token is not None
                or self.action_cost is not None
                or self.kind != "passive"
                or self.action_member_ordinal is not None
            ):
                raise ValueError(
                    "passive ability action envelope disagrees with source"
                )
            return
        if len(action_members) != 1 or action_members[0][0] != 0:
            raise ActionCostCompileError(
                "ability envelope requires one first ordered Action member"
            )
        action_ordinal, action_member = action_members[0]
        semantics = _semantics_for_token(action_member.value)
        if type(self.explicit_action) is not CompiledExplicitActionCost:
            raise TypeError(
                "explicit ability action envelope requires compiled evidence"
            )
        if (
            self.explicit_action.authority is not authority
            or self.explicit_action.source is not self.ability_source
        ):
            raise ValueError(
                "explicit ability action evidence belongs to another source"
            )
        CompiledExplicitActionCost.__post_init__(self.explicit_action)
        if (
            self.token != semantics.token
            or type(self.token) is not str
            or self.action_cost != semantics.cost
            or type(self.action_cost) is not type(semantics.cost)
            or self.kind != semantics.kind
            or self.action_member_ordinal != action_ordinal
            or type(self.action_member_ordinal) is not int
        ):
            raise ValueError(
                "ability action envelope semantics disagree with source"
            )

    def as_serialized(self) -> dict[str, Any]:
        AbilityActionEnvelope.__post_init__(self)
        explicit = self.explicit_action
        return {
            "token": self.token,
            "actionCost": self.action_cost,
            "kind": self.kind,
            "actionMemberOrdinal": self.action_member_ordinal,
            "providerRules": (
                []
                if explicit is None
                else [
                    ProviderRuleEvidence.as_serialized(rule)
                    for rule in explicit.provider_rules
                ]
            ),
            "responseWindow": (
                None
                if explicit is None
                else ResponseWindowMetadata.as_serialized(
                    explicit.response_window
                )
            ),
            "frequency": (
                None
                if explicit is None
                else FrequencyMetadata.as_serialized(explicit.frequency)
            ),
            "deferred": (
                []
                if explicit is None
                else [
                    DeferredActionCostMechanic.as_serialized(item)
                    for item in explicit.deferrals
                ]
            ),
            "runtimeReady": False,
        }

    def __copy__(self) -> AbilityActionEnvelope:
        raise TypeError("AbilityActionEnvelope cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> AbilityActionEnvelope:
        raise TypeError("AbilityActionEnvelope cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("AbilityActionEnvelope cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("AbilityActionEnvelope cannot be pickled")


@final
@dataclass(frozen=True, slots=True)
class DeferredAbilityEnvelopeMechanic:
    """One exact handoff from source shape to a later effect compiler."""

    dependency_id: str
    required_contract: str

    def __post_init__(self) -> None:
        if type(self) is not DeferredAbilityEnvelopeMechanic:
            raise TypeError(
                "DeferredAbilityEnvelopeMechanic subclasses are unsupported"
            )
        for name in ("dependency_id", "required_contract"):
            value = getattr(self, name)
            if (
                type(value) is not str
                or not value
                or value != value.strip()
                or len(value.encode("utf-8")) > 1_024
            ):
                raise ValueError(
                    f"DeferredAbilityEnvelopeMechanic.{name} is invalid"
                )

    def as_serialized(self) -> dict[str, str]:
        DeferredAbilityEnvelopeMechanic.__post_init__(self)
        return {
            "id": self.dependency_id,
            "phase": "source-link",
            "category": "ability-effect",
            "requiredContract": self.required_contract,
            "status": "deferred",
            "blocks": "effect-runtime-activation",
        }

    def __copy__(self) -> DeferredAbilityEnvelopeMechanic:
        raise TypeError(
            "DeferredAbilityEnvelopeMechanic cannot be copied"
        )

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> DeferredAbilityEnvelopeMechanic:
        raise TypeError(
            "DeferredAbilityEnvelopeMechanic cannot be copied"
        )

    def __reduce__(self) -> object:
        raise TypeError(
            "DeferredAbilityEnvelopeMechanic cannot be pickled"
        )

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError(
            "DeferredAbilityEnvelopeMechanic cannot be pickled"
        )


def _require_ability_envelope_address(
    source: VerifiedSourceSelection,
    /,
    *,
    reserved_steps: int,
) -> None:
    """Enforce the shared exact-path bound before selecting descendants."""

    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "ability envelope address requires exact "
            "VerifiedSourceSelection"
        )
    if type(reserved_steps) is not int or reserved_steps not in (0, 1):
        raise TypeError("ability envelope reserved path depth is invalid")
    address = source.address
    paths = (
        address.target_path,
        address.carrier_path,
        address.selection_path,
    )
    if (
        any(type(path) is not tuple for path in paths)
        or any(len(path) > 64 for path in paths)
        or sum(len(path) for path in paths) + reserved_steps > 64
        or any(
            type(step) not in (RawMemberStep, RawIndexStep)
            for path in paths
            for step in path
        )
        or address.span is not None
    ):
        raise ActionCostCompileError(
            "ability envelope address exceeds its exact path bound"
        )
    for path in paths:
        for step in path:
            if type(step) is RawMemberStep:
                RawMemberStep.__post_init__(step)
            else:
                RawIndexStep.__post_init__(step)


def _require_creature_envelope_source(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    /,
) -> tuple[RawSourceObject, str]:
    authority = _require_family_authority(authority)
    if type(source) is not VerifiedSourceSelection:
        raise TypeError(
            "ability envelope compiler requires exact "
            "VerifiedSourceSelection"
        )
    authority.validate_selection(source)
    _require_ability_envelope_address(source, reserved_steps=1)
    address = source.address
    if (
        address.source_id != "core-mc1"
        or not address.carrier_path
        or type(address.carrier_path[-1]) is not RawMemberStep
        or address.carrier_path[-1].raw_key != "^.creature"
        or address.selection_path
        or address.span is not None
        or type(source.raw_value) is not RawSourceObject
        or type(source.selected_value) is not RawSourceObject
        or source.raw_value != source.selected_value
        or source.raw_value != source.carrier.raw_block
    ):
        raise ActionCostCompileError(
            "ability envelopes require one exact Core MC1 creature carrier"
        )
    block = source.raw_value
    names = tuple(
        member.value
        for member in block.members
        if member.key == "Name"
    )
    if (
        len(names) != 1
        or type(names[0]) is not str
        or not names[0]
        or names[0] != names[0].strip()
        or names[0]
        != authority.toc_label("core-mc1", address.locator)
    ):
        raise ActionCostCompileError(
            "ability envelope creature name disagrees with authority"
        )
    ability_count = sum(
        1 for member in block.members if member.key.startswith("!.")
    )
    if ability_count > 64:
        raise ActionCostCompileError(
            "creature ability envelope count exceeds its bound"
        )
    return block, names[0]


def _require_ability_envelope_value(
    value: RawSourceValue,
    /,
) -> AbilityEnvelopeShape:
    """Bound one prose or structured ability without changing its shape."""

    if type(value) is str:
        shape: AbilityEnvelopeShape = "prose"
    elif type(value) is RawSourceObject:
        shape = "structured"
        if not 1 <= len(value.members) <= 16:
            raise ActionCostCompileError(
                "structured ability envelope exceeds its member bound"
            )
    else:
        raise ActionCostCompileError(
            "ability envelope source shape is unsupported"
        )
    if len(canonical_raw_bytes(value)) > 8_192:
        raise ActionCostCompileError(
            "ability envelope exceeds its byte bound"
        )
    return shape


def _walk_ability_occurrence_members(
    value: RawSourceValue,
    path: tuple[RawMemberStep | RawIndexStep, ...] = (),
    /,
) -> tuple[
    tuple[
        tuple[RawMemberStep | RawIndexStep, ...],
        RawSourceMember,
    ],
    ...,
]:
    result: list[
        tuple[
            tuple[RawMemberStep | RawIndexStep, ...],
            RawSourceMember,
        ]
    ] = []
    active: set[int] = set()

    def walk(
        node: RawSourceValue,
        current: tuple[RawMemberStep | RawIndexStep, ...],
    ) -> None:
        if len(current) > 24:
            raise ActionCostCompileError(
                "ability occurrence depth exceeds its bound"
            )
        if type(node) not in (RawSourceObject, RawSourceArray):
            return
        identity = id(node)
        if identity in active:
            raise ActionCostCompileError(
                "ability occurrence graph contains a cycle"
            )
        active.add(identity)
        try:
            if type(node) is RawSourceObject:
                for member_ordinal, member in enumerate(node.members):
                    if member_ordinal > 63:
                        raise ActionCostCompileError(
                            "ability occurrence member ordinal exceeds "
                            "its bound"
                        )
                    step = RawMemberStep(
                        member.key,
                        member_ordinal,
                    )
                    member_path = (*current, step)
                    result.append((member_path, member))
                    if len(result) > 128:
                        raise ActionCostCompileError(
                            "ability occurrence count exceeds its bound"
                        )
                    walk(member.value, member_path)
            else:
                for item_ordinal, item in enumerate(node.items):
                    walk(
                        item,
                        (*current, RawIndexStep(item_ordinal)),
                    )
        finally:
            active.remove(identity)

    walk(value, path)
    return tuple(result)


def _ability_occurrences(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    /,
) -> tuple[AbilitySourceOccurrence, ...]:
    result: list[AbilitySourceOccurrence] = []
    for occurrence_ordinal, (relative_path, member) in enumerate(
        _walk_ability_occurrence_members(source.raw_value)
    ):
        selected = VerifiedSourceCarrier.select(
            source.carrier,
            (*source.address.selection_path, *relative_path),
        )
        if type(selected) is not VerifiedSourceSelection:
            raise TypeError(
                "ability occurrence resolver returned an invalid selection"
            )
        authority.validate_selection(selected)
        result.append(
            AbilitySourceOccurrence(
                authority=authority,
                ability_source=source,
                occurrence_ordinal=occurrence_ordinal,
                relative_path=relative_path,
                raw_member=member,
                receipt=selected.receipt,
            )
        )
    return tuple(result)


def _ability_action_envelope(
    authority: SourceAuthorityAdapter,
    source: VerifiedSourceSelection,
    /,
) -> AbilityActionEnvelope:
    raw_value = source.raw_value
    shape = _require_ability_envelope_value(raw_value)
    if shape == "prose":
        action_members: tuple[tuple[int, RawSourceMember], ...] = ()
    else:
        action_members = tuple(
            (ordinal, member)
            for ordinal, member in enumerate(raw_value.members)
            if member.key == "Action"
        )
    if not action_members:
        return AbilityActionEnvelope(
            authority=authority,
            ability_source=source,
            explicit_action=None,
            token=None,
            action_cost=None,
            kind="passive",
            action_member_ordinal=None,
        )
    if len(action_members) != 1 or action_members[0][0] != 0:
        raise ActionCostCompileError(
            "ability envelope requires one first ordered Action member"
        )
    action_ordinal, action_member = action_members[0]
    semantics = _semantics_for_token(action_member.value)
    providers = tuple(
        authority.resolve_rule(requirement)
        for requirement in _canonical_rule_requirements(
            semantics.token
        )
    )
    explicit = compile_explicit_action_cost(
        authority,
        source,
        providers,
    )
    return AbilityActionEnvelope(
        authority=authority,
        ability_source=source,
        explicit_action=explicit,
        token=semantics.token,
        action_cost=semantics.cost,
        kind=semantics.kind,
        action_member_ordinal=action_ordinal,
    )


def _canonical_ability_envelope_deferrals(
) -> tuple[DeferredAbilityEnvelopeMechanic, ...]:
    return (
        DeferredAbilityEnvelopeMechanic(
            dependency_id="named-ability-effect-compiler",
            required_contract=(
                "a mechanic-family compiler that consumes this exact "
                "ordered ability source without inferring effects here"
            ),
        ),
    )


@final
@dataclass(frozen=True, slots=True)
class CompiledAbilityEnvelope:
    """One lossless ability shell with action cost but no effect claim."""

    authority: SourceAuthorityAdapter = field(repr=False, compare=False)
    creature_source: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )
    ability_source: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )
    member_ordinal: int
    ability_label: str
    shape: AbilityEnvelopeShape
    raw_member: RawSourceMember
    occurrences: tuple[AbilitySourceOccurrence, ...]
    action: AbilityActionEnvelope
    deferrals: tuple[DeferredAbilityEnvelopeMechanic, ...]

    def __post_init__(self) -> None:
        if type(self) is not CompiledAbilityEnvelope:
            raise TypeError(
                "CompiledAbilityEnvelope subclasses are not supported"
            )
        authority = _require_family_authority(self.authority)
        block, _name = _require_creature_envelope_source(
            authority,
            self.creature_source,
        )
        if (
            type(self.member_ordinal) is not int
            or self.member_ordinal < 0
            or self.member_ordinal > 63
            or self.member_ordinal >= len(block.members)
        ):
            raise ValueError(
                "CompiledAbilityEnvelope member ordinal is invalid"
            )
        expected_member = block.members[self.member_ordinal]
        if (
            type(self.raw_member) is not RawSourceMember
            or raw_member_sha256(self.raw_member)
            != raw_member_sha256(expected_member)
            or not expected_member.key.startswith("!.")
            or type(self.ability_label) is not str
            or self.ability_label != _ability_label(expected_member.key)
        ):
            raise ValueError(
                "CompiledAbilityEnvelope identity disagrees with source"
            )
        if type(self.ability_source) is not VerifiedSourceSelection:
            raise TypeError(
                "CompiledAbilityEnvelope ability source must be exact"
        )
        authority.validate_selection(self.ability_source)
        _require_ability_envelope_address(
            self.ability_source,
            reserved_steps=0,
        )
        expected_path = (
            RawMemberStep(
                expected_member.key,
                self.member_ordinal,
            ),
        )
        if (
            self.ability_source.carrier.authority_digest
            != self.creature_source.carrier.authority_digest
            or self.ability_source.carrier.source_id
            != self.creature_source.carrier.source_id
            or self.ability_source.carrier.locator
            != self.creature_source.carrier.locator
            or self.ability_source.carrier.section_id
            != self.creature_source.carrier.section_id
            or self.ability_source.carrier.target_path
            != self.creature_source.carrier.target_path
            or self.ability_source.carrier.carrier_path
            != self.creature_source.carrier.carrier_path
            or self.ability_source.carrier.block_sha256
            != self.creature_source.carrier.block_sha256
            or self.ability_source.address.selection_path != expected_path
            or raw_member_sha256(self.ability_source.raw_member)
            != raw_member_sha256(expected_member)
            or raw_source_sha256(self.ability_source.raw_value)
            != raw_source_sha256(expected_member.value)
        ):
            raise ValueError(
                "CompiledAbilityEnvelope selection disagrees with creature"
            )
        expected_shape = _require_ability_envelope_value(
            expected_member.value
        )
        if (
            type(self.shape) is not str
            or self.shape != expected_shape
        ):
            raise ValueError(
                "CompiledAbilityEnvelope shape disagrees with source"
            )
        if type(self.occurrences) is not tuple:
            raise TypeError(
                "CompiledAbilityEnvelope occurrences must be a tuple"
            )
        canonical_occurrences = _walk_ability_occurrence_members(
            self.ability_source.raw_value
        )
        if (
            len(self.occurrences) != len(canonical_occurrences)
        ):
            raise ValueError(
                "CompiledAbilityEnvelope occurrences disagree with source"
            )
        for occurrence_ordinal, (
            occurrence,
            (relative_path, raw_member),
        ) in enumerate(
            zip(
                self.occurrences,
                canonical_occurrences,
                strict=True,
            )
        ):
            if (
                type(occurrence) is not AbilitySourceOccurrence
                or occurrence.authority is not authority
                or occurrence.ability_source is not self.ability_source
                or occurrence.occurrence_ordinal != occurrence_ordinal
                or occurrence.relative_path != relative_path
                or occurrence.raw_member != raw_member
            ):
                raise ValueError(
                    "CompiledAbilityEnvelope occurrences disagree "
                    "with source"
                )
            AbilitySourceOccurrence.__post_init__(occurrence)
        if (
            type(self.action) is not AbilityActionEnvelope
            or self.action.authority is not authority
            or self.action.ability_source is not self.ability_source
        ):
            raise TypeError(
                "CompiledAbilityEnvelope action claim is invalid"
            )
        AbilityActionEnvelope.__post_init__(self.action)
        canonical_deferrals = _canonical_ability_envelope_deferrals()
        if (
            type(self.deferrals) is not tuple
            or any(
                type(item) is not DeferredAbilityEnvelopeMechanic
                for item in self.deferrals
            )
            or canonical_json_bytes(
                [
                    DeferredAbilityEnvelopeMechanic.as_serialized(item)
                    for item in self.deferrals
                ]
            )
            != canonical_json_bytes(
                [
                    DeferredAbilityEnvelopeMechanic.as_serialized(item)
                    for item in canonical_deferrals
                ]
            )
        ):
            raise ValueError(
                "CompiledAbilityEnvelope deferrals are incomplete"
            )

    @property
    def source_shape_features(self) -> tuple[str, ...]:
        CompiledAbilityEnvelope.__post_init__(self)
        return _source_shape_features(self)

    def as_serialized(self) -> dict[str, Any]:
        CompiledAbilityEnvelope.__post_init__(self)
        features = _source_shape_features(self)
        return {
            "memberOrdinal": self.member_ordinal,
            "abilityLabel": self.ability_label,
            "shape": self.shape,
            "rawAbilityMemberJson": canonical_raw_bytes(
                RawSourceObject((self.raw_member,))
            ).decode("utf-8"),
            "abilitySource": SourceReceipt.as_serialized(
                self.ability_source.receipt
            ),
            "orderedOccurrences": [
                AbilitySourceOccurrence.as_serialized(item)
                for item in self.occurrences
            ],
            "action": AbilityActionEnvelope.as_serialized(self.action),
            "sourceShapeFeatures": list(features),
            "deferred": [
                DeferredAbilityEnvelopeMechanic.as_serialized(item)
                for item in self.deferrals
            ],
            "effectStatus": "deferred",
            "runtimeReady": False,
        }

    def __copy__(self) -> CompiledAbilityEnvelope:
        raise TypeError("CompiledAbilityEnvelope cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> CompiledAbilityEnvelope:
        raise TypeError("CompiledAbilityEnvelope cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("CompiledAbilityEnvelope cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CompiledAbilityEnvelope cannot be pickled")


def _source_shape_features(
    envelope: CompiledAbilityEnvelope,
    /,
) -> tuple[str, ...]:
    """Derive non-semantic source-shape markers from a validated envelope."""

    if type(envelope) is not CompiledAbilityEnvelope:
        raise TypeError("source-shape features require an exact envelope")
    features: list[str] = []
    if envelope.action.token == "free":
        features.append("explicit-free-action")
    if (
        type(envelope.raw_member.value) is RawSourceObject
        and sum(
            1
            for member in envelope.raw_member.value.members
            if member.key == "~.p"
        )
        > 1
    ):
        features.append("duplicate-ordered-paragraphs")
    return tuple(features)


@final
@dataclass(frozen=True, slots=True)
class CompiledCreatureAbilityEnvelopes:
    """All direct ability occurrences for one exact creature carrier."""

    authority: SourceAuthorityAdapter = field(repr=False, compare=False)
    creature_source: VerifiedSourceSelection = field(
        repr=False,
        compare=False,
    )
    creature_name: str
    abilities: tuple[CompiledAbilityEnvelope, ...]

    def __post_init__(self) -> None:
        if type(self) is not CompiledCreatureAbilityEnvelopes:
            raise TypeError(
                "CompiledCreatureAbilityEnvelopes subclasses are unsupported"
            )
        authority = _require_family_authority(self.authority)
        block, creature_name = _require_creature_envelope_source(
            authority,
            self.creature_source,
        )
        if (
            type(self.creature_name) is not str
            or self.creature_name != creature_name
        ):
            raise ValueError(
                "compiled ability-envelope creature name disagrees"
            )
        expected = tuple(
            (ordinal, member)
            for ordinal, member in enumerate(block.members)
            if member.key.startswith("!.")
        )
        if (
            type(self.abilities) is not tuple
            or len(self.abilities) != len(expected)
            or len(self.abilities) > 64
        ):
            raise ValueError(
                "compiled ability-envelope collection is incomplete"
            )
        for envelope, (ordinal, member) in zip(
            self.abilities,
            expected,
            strict=True,
        ):
            if (
                type(envelope) is not CompiledAbilityEnvelope
                or envelope.authority is not authority
                or envelope.creature_source is not self.creature_source
                or envelope.member_ordinal != ordinal
                or raw_member_sha256(envelope.raw_member)
                != raw_member_sha256(member)
            ):
                raise ValueError(
                    "compiled ability-envelope order disagrees with source"
                )
            CompiledAbilityEnvelope.__post_init__(envelope)

    def as_serialized(self) -> dict[str, Any]:
        CompiledCreatureAbilityEnvelopes.__post_init__(self)
        serialized = [
            CompiledAbilityEnvelope.as_serialized(item)
            for item in self.abilities
        ]
        explicit_count = sum(
            1 for item in self.abilities if item.action.token is not None
        )
        occurrence_count = sum(
            len(item.occurrences) for item in self.abilities
        )
        paragraph_count = sum(
            1
            for item in self.abilities
            for occurrence in item.occurrences
            if occurrence.raw_member.key == "~.p"
        )
        features = tuple(
            feature
            for item in self.abilities
            for feature in _source_shape_features(item)
        )
        return {
            "family": "ability-action-envelopes",
            "creatureName": self.creature_name,
            "creatureSource": SourceReceipt.as_serialized(
                self.creature_source.receipt
            ),
            "abilityCount": len(self.abilities),
            "explicitActionCount": explicit_count,
            "orderedOccurrenceCount": occurrence_count,
            "paragraphOccurrenceCount": paragraph_count,
            "sourceShapeFeatures": list(features),
            "abilities": serialized,
            "effectStatus": "deferred",
            "runtimeReady": False,
            "activation": "compile-only",
        }

    def __copy__(self) -> CompiledCreatureAbilityEnvelopes:
        raise TypeError(
            "CompiledCreatureAbilityEnvelopes cannot be copied"
        )

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> CompiledCreatureAbilityEnvelopes:
        raise TypeError(
            "CompiledCreatureAbilityEnvelopes cannot be copied"
        )

    def __reduce__(self) -> object:
        raise TypeError(
            "CompiledCreatureAbilityEnvelopes cannot be pickled"
        )

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError(
            "CompiledCreatureAbilityEnvelopes cannot be pickled"
        )


def compile_ability_envelopes(
    authority: SourceAuthorityAdapter,
    creature_source: VerifiedSourceSelection,
    /,
) -> CompiledCreatureAbilityEnvelopes:
    """Compile every direct creature ability into one lossless shell.

    Provider rules are resolved internally from the same retained authority.
    Callers cannot inject action-cost rules, flattened fields, or inferred
    prose costs.  Named effects remain explicitly deferred.
    """

    authority = _require_family_authority(authority)
    block, creature_name = _require_creature_envelope_source(
        authority,
        creature_source,
    )
    abilities: list[CompiledAbilityEnvelope] = []
    for member_ordinal, member in enumerate(block.members):
        if not member.key.startswith("!."):
            continue
        if member_ordinal > 63:
            raise ActionCostCompileError(
                "ability envelope member ordinal exceeds its bound"
            )
        source = VerifiedSourceCarrier.select(
            creature_source.carrier,
            (RawMemberStep(member.key, member_ordinal),),
        )
        if type(source) is not VerifiedSourceSelection:
            raise TypeError(
                "ability envelope selection is invalid"
            )
        authority.validate_selection(source)
        _require_ability_envelope_address(
            source,
            reserved_steps=0,
        )
        shape = _require_ability_envelope_value(member.value)
        abilities.append(
            CompiledAbilityEnvelope(
                authority=authority,
                creature_source=creature_source,
                ability_source=source,
                member_ordinal=member_ordinal,
                ability_label=_ability_label(member.key),
                shape=shape,
                raw_member=member,
                occurrences=_ability_occurrences(authority, source),
                action=_ability_action_envelope(authority, source),
                deferrals=_canonical_ability_envelope_deferrals(),
            )
        )
    result = CompiledCreatureAbilityEnvelopes(
        authority=authority,
        creature_source=creature_source,
        creature_name=creature_name,
        abilities=tuple(abilities),
    )
    return result


def _bind_ability_envelope_integrity(
    occurrence_type: type[AbilitySourceOccurrence],
    action_type: type[AbilityActionEnvelope],
    deferral_type: type[DeferredAbilityEnvelopeMechanic],
    envelope_type: type[CompiledAbilityEnvelope],
    collection_type: type[CompiledCreatureAbilityEnvelopes],
    compile_impl: Any,
) -> Any:
    """Bind the public action-cost surface to its import-time implementation."""

    module_state = globals()
    missing = object()
    safe_callable = callable
    safe_error = ActionCostCompileError
    safe_getattr = getattr
    safe_len = len
    safe_type = type
    safe_type_error = TypeError
    safe_tuple = tuple
    builtins_binding = module_state["__builtins__"]
    if safe_type(builtins_binding) is dict:
        builtin_state = builtins_binding
    else:
        builtin_state = safe_getattr(builtins_binding, "__dict__")
    builtin_dependencies = safe_tuple(
        (name, value)
        for name, value in builtin_state.items()
        if not name.startswith("__")
    )
    global_dependencies: tuple[tuple[str, object], ...] = ()
    envelope_types = (
        occurrence_type,
        action_type,
        deferral_type,
        envelope_type,
        collection_type,
    )
    lower_artifact_types = (
        ActionSourceField,
        ProviderRuleEvidence,
        ResponseWindowMetadata,
        FrequencyMetadata,
        DeferredActionCostMechanic,
        CompiledExplicitActionCost,
    )
    contract_types = (
        RawSourceArray,
        RawSourceMember,
        RawSourceObject,
        RawIndexStep,
        RawMemberStep,
        RuleRequirement,
        SourceAuthorityAdapter,
        SourceReceipt,
        VerifiedRuleReceipt,
        VerifiedSourceCarrier,
        VerifiedSourceSelection,
        _ActionSemantics,
        *lower_artifact_types,
        *envelope_types,
    )
    class_contracts: tuple[
        tuple[type[Any], tuple[tuple[str, object], ...]],
        ...,
    ] = ()

    def require_integrity() -> None:
        if not class_contracts:
            raise safe_error(
                "ability envelope integrity guard is unavailable"
            )
        if (
            module_state.get("__builtins__", missing)
            is not builtins_binding
        ):
            raise safe_error(
                "ability envelope builtin namespace was rebound"
            )
        for name, expected in builtin_dependencies:
            if (
                module_state.get(name, missing) is not missing
                or builtin_state.get(name, missing) is not expected
            ):
                raise safe_error(
                    "ability envelope builtin dependency was rebound"
                )
        for name, expected in global_dependencies:
            if module_state.get(name, missing) is not expected:
                raise safe_error(
                    "ability envelope compiler dependency was rebound"
                )
        for owner, expected_items in class_contracts:
            current = safe_getattr(owner, "__dict__", missing)
            if (
                current is missing
                or safe_len(current) != safe_len(expected_items)
            ):
                raise safe_error(
                    "ability envelope contract hook was rebound"
                )
            for name, expected in expected_items:
                if current.get(name, missing) is not expected:
                    raise safe_error(
                        "ability envelope contract hook was rebound"
                    )

    def guarded_validator(original: Any) -> Any:
        def validate(self: object) -> None:
            require_integrity()
            original(self)

        return validate

    def guarded_serializer(original: Any) -> Any:
        def serialize(self: object) -> dict[str, Any]:
            require_integrity()
            return original(self)

        return serialize

    for artifact_type in lower_artifact_types:
        artifact_type.__post_init__ = guarded_validator(
            artifact_type.__post_init__
        )
        artifact_type.as_serialized = guarded_serializer(
            artifact_type.as_serialized
        )

    original_occurrence_validate = occurrence_type.__post_init__
    original_occurrence_serialize = occurrence_type.as_serialized
    original_action_validate = action_type.__post_init__
    original_action_serialize = action_type.as_serialized
    original_deferral_validate = deferral_type.__post_init__
    original_deferral_serialize = deferral_type.as_serialized
    original_envelope_validate = envelope_type.__post_init__
    original_envelope_serialize = envelope_type.as_serialized
    original_collection_validate = collection_type.__post_init__
    original_collection_serialize = collection_type.as_serialized
    original_features = envelope_type.__dict__["source_shape_features"]
    if type(original_features) is not property:
        raise TypeError("ability envelope feature hook is invalid")

    occurrence_type.__post_init__ = guarded_validator(
        original_occurrence_validate
    )
    occurrence_type.as_serialized = guarded_serializer(
        original_occurrence_serialize
    )
    action_type.__post_init__ = guarded_validator(
        original_action_validate
    )
    action_type.as_serialized = guarded_serializer(
        original_action_serialize
    )
    deferral_type.__post_init__ = guarded_validator(
        original_deferral_validate
    )
    deferral_type.as_serialized = guarded_serializer(
        original_deferral_serialize
    )
    envelope_type.__post_init__ = guarded_validator(
        original_envelope_validate
    )
    envelope_type.as_serialized = guarded_serializer(
        original_envelope_serialize
    )
    collection_type.__post_init__ = guarded_validator(
        original_collection_validate
    )
    collection_type.as_serialized = guarded_serializer(
        original_collection_serialize
    )

    def guarded_features(self: object) -> tuple[str, ...]:
        require_integrity()
        getter = original_features.fget
        if getter is None:
            raise safe_error(
                "ability envelope feature getter is unavailable"
            )
        return getter(self)

    envelope_type.source_shape_features = property(guarded_features)

    explicit_type = CompiledExplicitActionCost
    original_explicit_compile = compile_explicit_action_cost
    original_rule_requirements = rule_requirements_for_action

    def compile_explicit_guarded(
        authority: SourceAuthorityAdapter,
        source: VerifiedSourceSelection,
        provider_rules: tuple[VerifiedRuleReceipt, ...],
        /,
    ) -> CompiledExplicitActionCost:
        require_integrity()
        result = original_explicit_compile(
            authority,
            source,
            provider_rules,
        )
        require_integrity()
        if safe_type(result) is not explicit_type:
            raise safe_type_error(
                "explicit Action compiler returned an invalid contract"
            )
        explicit_type.__post_init__(result)
        return result

    def rule_requirements_guarded(
        token: ActionToken,
        /,
    ) -> tuple[RuleRequirement, ...]:
        require_integrity()
        result = original_rule_requirements(token)
        require_integrity()
        if (
            safe_type(result) is not tuple
            or any(safe_type(item) is not RuleRequirement for item in result)
        ):
            raise safe_type_error(
                "action rule requirements returned an invalid contract"
            )
        return result

    module_state["compile_explicit_action_cost"] = compile_explicit_guarded
    module_state["rule_requirements_for_action"] = rule_requirements_guarded
    excluded_globals = {
        "_bind_ability_envelope_integrity",
        "compile_ability_envelopes",
    }
    global_dependencies = safe_tuple(
        (name, value)
        for name, value in module_state.items()
        if (
            not name.startswith("__")
            and name not in excluded_globals
            and safe_callable(value)
        )
    )
    class_contracts = safe_tuple(
        (
            owner,
            safe_tuple(
                safe_getattr(owner, "__dict__").items()
            ),
        )
        for owner in contract_types
    )

    def compile_guarded(
        authority: SourceAuthorityAdapter,
        creature_source: VerifiedSourceSelection,
        /,
    ) -> CompiledCreatureAbilityEnvelopes:
        require_integrity()
        result = compile_impl(authority, creature_source)
        require_integrity()
        if safe_type(result) is not collection_type:
            raise safe_type_error(
                "ability envelope compiler returned an invalid contract"
            )
        collection_type.__post_init__(result)
        return result

    return compile_guarded


compile_ability_envelopes = _bind_ability_envelope_integrity(
    AbilitySourceOccurrence,
    AbilityActionEnvelope,
    DeferredAbilityEnvelopeMechanic,
    CompiledAbilityEnvelope,
    CompiledCreatureAbilityEnvelopes,
    compile_ability_envelopes,
)
del _bind_ability_envelope_integrity


__all__ = [
    "ACTIVITY_ECONOMY_RULE",
    "ActionCostCompileError",
    "AbilityActionEnvelope",
    "AbilityEnvelopeKind",
    "AbilityEnvelopeShape",
    "ActionSourceField",
    "AbilitySourceOccurrence",
    "CompiledAbilityEnvelope",
    "CompiledCreatureAbilityEnvelopes",
    "CompiledExplicitActionCost",
    "CREATURE_ACTION_FORMAT_RULE",
    "DeferredAbilityEnvelopeMechanic",
    "DeferredActionCostMechanic",
    "FAMILY_ID",
    "FREE_ACTION_ECONOMY_RULE",
    "FREE_ACTION_TYPE_RULE",
    "FrequencyMetadata",
    "MAX_ABILITY_BYTES",
    "MAX_ABILITY_OCCURRENCES",
    "MAX_ABILITY_OCCURRENCE_DEPTH",
    "MAX_ABILITY_MEMBER_ORDINAL",
    "MAX_ABILITY_MEMBERS",
    "MAX_ADDRESS_STEPS",
    "MAX_CREATURE_ABILITIES",
    "MAX_PROVIDER_RULES",
    "MONSTER_CORE_SOURCE_ID",
    "PROVIDER_RULE_REQUIREMENTS",
    "ProviderRuleEvidence",
    "REACTION_ACTION_TYPE_RULE",
    "REACTION_ECONOMY_RULE",
    "ResponseWindowMetadata",
    "SINGLE_ACTION_ECONOMY_RULE",
    "SINGLE_ACTION_TYPE_RULE",
    "THREE_ACTION_TYPE_RULE",
    "TRIGGER_LIMITATIONS_RULE",
    "TWO_ACTION_TYPE_RULE",
    "compile_ability_envelopes",
    "compile_explicit_action_cost",
    "rule_requirements_for_action",
]

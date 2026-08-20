"""Compile the reviewed Giant Amoeba ability projections.

The three selective fragments in this module are deliberately unregistered.
``AbilitySource`` does not carry source-authority evidence, so production
registration must remain gated on :func:`verify_giant_amoeba_source_links`
and on the runtime mechanics named by each patch's deferrals.

This is intentionally not a general ooze framework.  It accepts only the
current ``core-mc2:241.1`` Giant Amoeba productions and authenticates only
their exact Gutter Ooze and Monster Core 2 Engulf providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RuleReference,
)
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
)


SOURCE_ID = "core-mc2"
LOCATOR = "241.1"
CREATURE_NAME = "Giant Amoeba"
GUTTER_OOZE_NAME = "Gutter Ooze"

MOTION_SENSE_MECHANIC_TYPE = "giant-amoeba-motion-sense"
WEAK_ACID_MECHANIC_TYPE = "giant-amoeba-weak-acid"
ENVELOP_MECHANIC_TYPE = "giant-amoeba-envelop"

INHERITED_REFERENCE = "As gutter ooze."
GUTTER_MOTION_SENSE_DESCRIPTION = (
    "A gutter ooze can sense nearby creatures through vibration and air "
    "or water movement."
)
GUTTER_WEAK_ACID_DESCRIPTION = (
    "A gutter ooze’s acid damages only organic material—not metal, stone, "
    "or other inorganic substances."
)
ENVELOP_REQUIREMENTS = (
    "The giant amoeba begins its turn with a target its size or smaller "
    "grabbed"
)
ENVELOP_EFFECT = (
    "The giant amoeba maintains the Grab and extends pseudopods to surround "
    "the creature and pull it inside the amoeba’s body. This thereafter has "
    "the same effect as if the amoeba had Engulfed the creature (DC 17, 1d6 "
    "acid, Escape DC 17, Rupture 3; page 361)."
)

MOTION_SENSE_DEFERRALS = (
    "source-provider-link",
    "observer-relative-motion-detection",
    "motion-sense-precision",
)
WEAK_ACID_DEFERRALS = (
    "source-provider-link",
    "target-material-classification",
    "acid-damage-material-filtering",
)
ENVELOP_DEFERRALS = (
    "engulf-breath-suffocation",
    "engulf-light-bulk-internal-weapon-boundary",
)

_GIANT_AMOEBA_BLOCK_SHA256 = (
    "cfc84607d83c0831d2b5d39a3f854ee61c3212bf3d3eaf069af5a9133e81af74"
)
_GUTTER_OOZE_BLOCK_SHA256 = (
    "f764577b00b9f414a21cbb9bb2b739088374a49ebb2dffe73e033099d5a4b313"
)

_MOTION_SENSE_CONSUMER = RuleRequirement(
    rule_id="giant-amoeba-motion-sense",
    source_id=SOURCE_ID,
    locator=LOCATOR,
    carrier_path=(RawMemberStep("^.creature", 2),),
    selection_path=(RawMemberStep("!.Motion Sense", 14),),
    expected_block_sha256=_GIANT_AMOEBA_BLOCK_SHA256,
    expected_member_sha256=(
        "91cb3378611ccef4ff73cfb1cc9776f9e5bf61ef7729badd6edfc1d432f31e4f"
    ),
    expected_value_sha256=(
        "122f18f4a121b5d28a168e65f1fc1a0b36194442ca2c5a630c728cc498b4f58a"
    ),
    expected_selection_sha256=(
        "122f18f4a121b5d28a168e65f1fc1a0b36194442ca2c5a630c728cc498b4f58a"
    ),
)
_MOTION_SENSE_PERCEPTION = RuleRequirement(
    rule_id="giant-amoeba-motion-sense-perception",
    source_id=SOURCE_ID,
    locator=LOCATOR,
    carrier_path=(RawMemberStep("^.creature", 2),),
    selection_path=(RawMemberStep("Perception", 6),),
    expected_block_sha256=_GIANT_AMOEBA_BLOCK_SHA256,
    expected_member_sha256=(
        "7e5fbbe7bfcd300e7a4f1f1877e3adf988d6de503519832d1d0b85f0e143361b"
    ),
    expected_value_sha256=(
        "9844d31636989b6f3ffc0acb10e6fe09ff21c85ee375f8a77aca86c4757b1dd7"
    ),
    expected_selection_sha256=(
        "9844d31636989b6f3ffc0acb10e6fe09ff21c85ee375f8a77aca86c4757b1dd7"
    ),
)
_GUTTER_MOTION_SENSE = RuleRequirement(
    rule_id="gutter-ooze-motion-sense-provider",
    source_id=SOURCE_ID,
    locator=LOCATOR,
    carrier_path=(RawMemberStep("^.creature", 1),),
    selection_path=(RawMemberStep("!.Motion Sense", 13),),
    expected_block_sha256=_GUTTER_OOZE_BLOCK_SHA256,
    expected_member_sha256=(
        "721435fad81132a61cf30af6f6834eb9964177ad9b2d140f15a9b279be0ca4d4"
    ),
    expected_value_sha256=(
        "a03da8d3649033fee6b50a53bd6bc7e712b27c091dd11af2b1bf6b2ac4619fea"
    ),
    expected_selection_sha256=(
        "a03da8d3649033fee6b50a53bd6bc7e712b27c091dd11af2b1bf6b2ac4619fea"
    ),
)
_WEAK_ACID_CONSUMER = RuleRequirement(
    rule_id="giant-amoeba-weak-acid",
    source_id=SOURCE_ID,
    locator=LOCATOR,
    carrier_path=(RawMemberStep("^.creature", 2),),
    selection_path=(RawMemberStep("!.Weak Acid", 26),),
    expected_block_sha256=_GIANT_AMOEBA_BLOCK_SHA256,
    expected_member_sha256=(
        "2d858478c11ec0110269e6eed0bd19232eb769e2b85f0ee88e0ff978d0e64185"
    ),
    expected_value_sha256=(
        "122f18f4a121b5d28a168e65f1fc1a0b36194442ca2c5a630c728cc498b4f58a"
    ),
    expected_selection_sha256=(
        "122f18f4a121b5d28a168e65f1fc1a0b36194442ca2c5a630c728cc498b4f58a"
    ),
)
_GUTTER_WEAK_ACID = RuleRequirement(
    rule_id="gutter-ooze-weak-acid-provider",
    source_id=SOURCE_ID,
    locator=LOCATOR,
    carrier_path=(RawMemberStep("^.creature", 1),),
    selection_path=(RawMemberStep("!.Weak Acid", 24),),
    expected_block_sha256=_GUTTER_OOZE_BLOCK_SHA256,
    expected_member_sha256=(
        "e028c8e2c5066dea52e8dfb367160b66adf2efdf456816e79f257e9da54d094d"
    ),
    expected_value_sha256=(
        "43e8bac25bf72efb94d297ec936f0c7383bed8a7a30ce030fd884e81f1a60899"
    ),
    expected_selection_sha256=(
        "43e8bac25bf72efb94d297ec936f0c7383bed8a7a30ce030fd884e81f1a60899"
    ),
)
_ENVELOP_CONSUMER = RuleRequirement(
    rule_id="giant-amoeba-envelop",
    source_id=SOURCE_ID,
    locator=LOCATOR,
    carrier_path=(RawMemberStep("^.creature", 2),),
    selection_path=(RawMemberStep("!.Envelop", 25),),
    expected_block_sha256=_GIANT_AMOEBA_BLOCK_SHA256,
    expected_member_sha256=(
        "747052b8f3a3df948cc8fbf8e54caa416f6838b27724de849875690615b504a9"
    ),
    expected_value_sha256=(
        "c94bceb541ca95984c5b942fd4c1d2d594f020abfe55c97c4be40f12ad17869a"
    ),
    expected_selection_sha256=(
        "c94bceb541ca95984c5b942fd4c1d2d594f020abfe55c97c4be40f12ad17869a"
    ),
)
_MONSTER_CORE_2_ENGULF = RuleRequirement(
    rule_id="monster-core-2-engulf-provider",
    source_id=SOURCE_ID,
    locator="360.2",
    carrier_path=(RawMemberStep("^.ability", 12),),
    expected_block_sha256=(
        "35d4439f599cc73d3ebe6046a9d254c7a4ce1b109f68bdabd3d8683c7e374e39"
    ),
    expected_value_sha256=(
        "35d4439f599cc73d3ebe6046a9d254c7a4ce1b109f68bdabd3d8683c7e374e39"
    ),
    expected_selection_sha256=(
        "35d4439f599cc73d3ebe6046a9d254c7a4ce1b109f68bdabd3d8683c7e374e39"
    ),
)

_LINK_REQUIREMENTS = (
    (
        "motion-sense",
        _MOTION_SENSE_CONSUMER,
        (_MOTION_SENSE_PERCEPTION, _GUTTER_MOTION_SENSE),
        MOTION_SENSE_DEFERRALS,
    ),
    (
        "weak-acid",
        _WEAK_ACID_CONSUMER,
        (_GUTTER_WEAK_ACID,),
        WEAK_ACID_DEFERRALS,
    ),
    (
        "envelop",
        _ENVELOP_CONSUMER,
        (_MONSTER_CORE_2_ENGULF,),
        ENVELOP_DEFERRALS,
    ),
)


class AmoebaSourceLinkError(ValueError):
    """Reviewed Giant Amoeba source or provider evidence changed."""


@dataclass(frozen=True, slots=True)
class AmoebaAbilitySourceLink:
    """One ability and its exact same-authority provider receipts."""

    ability_id: str
    consumer: VerifiedRuleReceipt
    providers: tuple[VerifiedRuleReceipt, ...]
    runtime_blockers: tuple[str, ...]
    _authority: SourceAuthorityAdapter = field(
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if type(self) is not AmoebaAbilitySourceLink:
            raise TypeError(
                "AmoebaAbilitySourceLink subclasses are unsupported"
            )
        _validate_source_link(self._authority, self)

    def as_serialized(
        self,
        authority: SourceAuthorityAdapter,
        /,
    ) -> dict[str, Any]:
        _validate_source_link(authority, self)
        return {
            "abilityId": self.ability_id,
            "consumer": self.consumer.as_serialized(),
            "providers": [
                provider.as_serialized()
                for provider in self.providers
            ],
            "runtimeReady": False,
            "runtimeBlockers": list(self.runtime_blockers),
        }


def _resolve_reviewed_rule(
    authority: SourceAuthorityAdapter,
    requirement: RuleRequirement,
) -> VerifiedRuleReceipt:
    rule = authority.validate_rule(authority.resolve_rule(requirement))
    if (
        type(rule) is not VerifiedRuleReceipt
        or rule.rule_id != requirement.rule_id
        or rule.requirement != requirement
    ):
        raise AmoebaSourceLinkError(
            f"reviewed source rule changed: {requirement.rule_id}"
        )
    return rule


def _exact_object(
    selection: VerifiedSourceSelection,
    pairs: tuple[tuple[str, object], ...],
) -> bool:
    value = selection.selected_value
    return (
        type(value) is RawSourceObject
        and len(value.members) == len(pairs)
        and all(
            type(member) is RawSourceMember
            and member.key == expected_key
            and member.value == expected_value
            for member, (expected_key, expected_value)
            in zip(value.members, pairs, strict=True)
        )
    )


def _validate_reviewed_semantics(
    ability_id: str,
    consumer: VerifiedRuleReceipt,
    providers: tuple[VerifiedRuleReceipt, ...],
) -> None:
    consumer_value = consumer.selection.selected_value
    if ability_id == "motion-sense":
        perception, gutter = providers
        perception_value = perception.selection.selected_value
        valid = (
            consumer_value == INHERITED_REFERENCE
            and type(perception_value) is RawSourceArray
            and perception_value.items
            == (
                "+4",
                RawSourceArray(
                    ("motion sense 60 feet", "no vision")
                ),
            )
            and gutter.selection.selected_value
            == GUTTER_MOTION_SENSE_DESCRIPTION
        )
    elif ability_id == "weak-acid":
        valid = (
            consumer_value == INHERITED_REFERENCE
            and providers[0].selection.selected_value
            == GUTTER_WEAK_ACID_DESCRIPTION
        )
    elif ability_id == "envelop":
        engulf = providers[0].selection
        engulf_value = engulf.selected_value
        valid = (
            _exact_object(
                consumer.selection,
                (
                    ("Action", "three"),
                    ("Requirements", ENVELOP_REQUIREMENTS),
                    ("Effect", ENVELOP_EFFECT),
                ),
            )
            and type(engulf_value) is RawSourceObject
            and engulf_value.values("Name") == ("Engulf",)
            and engulf_value.values("Action") == ("two",)
            and len(engulf_value.values("Description")) == 1
            and type(engulf_value.values("Description")[0])
            is RawSourceObject
            and engulf_value.values("Description")[0].keys
            == ("~.p", "~.p", "~.p")
        )
    else:
        valid = False
    if not valid:
        raise AmoebaSourceLinkError(
            f"reviewed Giant Amoeba {ability_id!r} semantics changed"
        )


def _validate_source_link(
    authority: SourceAuthorityAdapter,
    link: AmoebaAbilitySourceLink,
) -> None:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "Giant Amoeba source links require SourceAuthorityAdapter"
        )
    if link._authority is not authority:
        raise AmoebaSourceLinkError(
            "Giant Amoeba source link belongs to another authority"
        )
    specification = next(
        (
            item
            for item in _LINK_REQUIREMENTS
            if item[0] == link.ability_id
        ),
        None,
    )
    if specification is None:
        raise AmoebaSourceLinkError(
            "Giant Amoeba source link ability is not reviewed"
        )
    _, consumer_requirement, provider_requirements, blockers = specification
    consumer = authority.validate_rule(link.consumer)
    providers = tuple(
        authority.validate_rule(provider)
        for provider in link.providers
    )
    if (
        consumer.rule_id != consumer_requirement.rule_id
        or consumer.requirement != consumer_requirement
        or tuple(provider.rule_id for provider in providers)
        != tuple(
            requirement.rule_id
            for requirement in provider_requirements
        )
        or any(
            provider.requirement != requirement
            for provider, requirement
            in zip(providers, provider_requirements, strict=True)
        )
        or link.runtime_blockers != blockers
    ):
        raise AmoebaSourceLinkError(
            "Giant Amoeba source link differs from review"
        )
    authority.require_shared_authority(
        consumer.selection,
        (consumer, *providers),
    )
    _validate_reviewed_semantics(link.ability_id, consumer, providers)


def verify_giant_amoeba_source_links(
    authority: SourceAuthorityAdapter,
    /,
) -> tuple[AmoebaAbilitySourceLink, ...]:
    """Authenticate every local ability and cross-source provider exactly."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "Giant Amoeba source verification requires "
            "SourceAuthorityAdapter"
        )
    links = []
    for ability_id, consumer_requirement, provider_requirements, blockers in (
        _LINK_REQUIREMENTS
    ):
        consumer = _resolve_reviewed_rule(authority, consumer_requirement)
        providers = tuple(
            _resolve_reviewed_rule(authority, requirement)
            for requirement in provider_requirements
        )
        links.append(
            AmoebaAbilitySourceLink(
                ability_id=ability_id,
                consumer=consumer,
                providers=providers,
                runtime_blockers=blockers,
                _authority=authority,
            )
        )
    return tuple(links)


def _source_matches(
    source: AbilitySource,
    *,
    label: str,
    action_cost: int | None,
    kind: str,
    description: str,
    raw_value: object,
) -> bool:
    return (
        type(source) is AbilitySource
        and source.source_id == SOURCE_ID
        and source.locator == LOCATOR
        and source.creature_name == CREATURE_NAME
        and source.source_label == label
        and source.action_cost == action_cost
        and source.kind == kind
        and source.traits == ()
        and source.trigger == ""
        and source.description == description
        and type(source.raw_member) is RawSourceMember
        and source.raw_member.key == f"!.{label}"
        and source.raw_member.value == raw_value
    )


def compile_motion_sense(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Project the exact inherited Giant Amoeba Motion Sense source."""

    if not _source_matches(
        source,
        label="Motion Sense",
        action_cost=None,
        kind="passive",
        description=INHERITED_REFERENCE,
        raw_value=INHERITED_REFERENCE,
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": MOTION_SENSE_MECHANIC_TYPE,
            "rangeFeet": 60,
            "vision": "none",
            "detectionChannels": [
                "vibration",
                "air-movement",
                "water-movement",
            ],
            "precision": None,
            "sourceProvider": {
                "sourceId": SOURCE_ID,
                "locator": LOCATOR,
                "creatureName": GUTTER_OOZE_NAME,
                "abilityName": "Motion Sense",
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        deferred_mechanics=MOTION_SENSE_DEFERRALS,
    )


def compile_weak_acid(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Project the exact inherited Giant Amoeba Weak Acid source."""

    if not _source_matches(
        source,
        label="Weak Acid",
        action_cost=None,
        kind="passive",
        description=INHERITED_REFERENCE,
        raw_value=INHERITED_REFERENCE,
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": WEAK_ACID_MECHANIC_TYPE,
            "damageType": "acid",
            "damagedMaterial": "organic",
            "excludedMaterials": [
                "metal",
                "stone",
                "other-inorganic",
            ],
            "sourceProvider": {
                "sourceId": SOURCE_ID,
                "locator": LOCATOR,
                "creatureName": GUTTER_OOZE_NAME,
                "abilityName": "Weak Acid",
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        deferred_mechanics=WEAK_ACID_DEFERRALS,
    )


def compile_envelop(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Project the exact three-action Giant Amoeba Envelop production."""

    raw_value = RawSourceObject(
        (
            ("Action", "three"),
            ("Requirements", ENVELOP_REQUIREMENTS),
            ("Effect", ENVELOP_EFFECT),
        )
    )
    if not _source_matches(
        source,
        label="Envelop",
        action_cost=3,
        kind="activity",
        description="",
        raw_value=raw_value,
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": ENVELOP_MECHANIC_TYPE,
            "requirements": {
                "timing": "begins-owner-turn",
                "targetCondition": "grabbed-by-owner",
                "maximumTargetSize": "owner-size",
            },
            "maintainsGrab": True,
            "pullsTarget": "inside-owner-body",
            "thereafter": "engulfed",
            "engulfParameters": {
                "listedDc": 17,
                "damage": {
                    "dice": {
                        "count": 1,
                        "sides": 6,
                    },
                    "modifier": 0,
                    "type": "acid",
                },
                "escapeDc": 17,
                "rupture": 3,
            },
            "sourceProvider": {
                "sourceId": SOURCE_ID,
                "locator": "360.2",
                "abilityName": "Engulf",
                "page": 361,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        deferred_mechanics=ENVELOP_DEFERRALS,
    )


MOTION_SENSE_FRAGMENT = MechanicFamilyFragment(
    family_id="giant-amoeba-motion-sense",
    mechanic_types=(MOTION_SENSE_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="giant-amoeba-motion-sense",
            mechanic_type=MOTION_SENSE_MECHANIC_TYPE,
            compiler=compile_motion_sense,
        ),
    ),
)

WEAK_ACID_FRAGMENT = MechanicFamilyFragment(
    family_id="giant-amoeba-weak-acid",
    mechanic_types=(WEAK_ACID_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="giant-amoeba-weak-acid",
            mechanic_type=WEAK_ACID_MECHANIC_TYPE,
            compiler=compile_weak_acid,
        ),
    ),
)

ENVELOP_FRAGMENT = MechanicFamilyFragment(
    family_id="giant-amoeba-envelop",
    mechanic_types=(ENVELOP_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="giant-amoeba-envelop",
            mechanic_type=ENVELOP_MECHANIC_TYPE,
            compiler=compile_envelop,
        ),
    ),
)

FRAGMENT = MechanicFamilyFragment(
    family_id="giant-amoeba-abilities",
    mechanic_types=(
        MOTION_SENSE_MECHANIC_TYPE,
        WEAK_ACID_MECHANIC_TYPE,
        ENVELOP_MECHANIC_TYPE,
    ),
    ability_compilers=(
        *MOTION_SENSE_FRAGMENT.ability_compilers,
        *WEAK_ACID_FRAGMENT.ability_compilers,
        *ENVELOP_FRAGMENT.ability_compilers,
    ),
)


__all__ = [
    "CREATURE_NAME",
    "ENVELOP_DEFERRALS",
    "ENVELOP_EFFECT",
    "ENVELOP_FRAGMENT",
    "ENVELOP_MECHANIC_TYPE",
    "ENVELOP_REQUIREMENTS",
    "FRAGMENT",
    "GUTTER_MOTION_SENSE_DESCRIPTION",
    "GUTTER_OOZE_NAME",
    "GUTTER_WEAK_ACID_DESCRIPTION",
    "INHERITED_REFERENCE",
    "LOCATOR",
    "MOTION_SENSE_DEFERRALS",
    "MOTION_SENSE_FRAGMENT",
    "MOTION_SENSE_MECHANIC_TYPE",
    "SOURCE_ID",
    "WEAK_ACID_DEFERRALS",
    "WEAK_ACID_FRAGMENT",
    "WEAK_ACID_MECHANIC_TYPE",
    "AmoebaAbilitySourceLink",
    "AmoebaSourceLinkError",
    "compile_envelop",
    "compile_motion_sense",
    "compile_weak_acid",
    "verify_giant_amoeba_source_links",
]

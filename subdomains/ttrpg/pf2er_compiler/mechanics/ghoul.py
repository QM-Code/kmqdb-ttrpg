"""Compile the reviewed Monster Core Ghoul-family ability shorthands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceArray,
    RawSourceObject,
    RuleReference,
)
from .source_authority import RawMemberStep, SourceAuthorityAdapter


SOURCE_ID = "core-mc1"
LOCATOR = "163.1"
CREATURE_NAME = "Ghoul Stalker"
CREATURE_RULE = {"sourceId": SOURCE_ID, "locator": LOCATOR}
CREATURE_PROFILES = {
    ("163.1", "Ghoul Stalker"): {
        "consumeFleshDescription": "1d6 HP",
        "consumeFleshDice": 1,
        "ghoulWhispersDescription": "DC 17",
        "ghoulWhispersDC": 17,
        "graveKnowledgeDescription": "(occult) +7 skill modifier",
        "graveKnowledgeModifier": 7,
        "swiftLeapDescription": None,
    },
    ("163.3", "Ghoul Soldier"): {
        "consumeFleshDescription": "2d6 HP",
        "consumeFleshDice": 2,
        "ghoulWhispersDescription": "DC 18",
        "ghoulWhispersDC": 18,
        "graveKnowledgeDescription": "(occult) +8 skill modifier",
        "graveKnowledgeModifier": 8,
        "swiftLeapDescription": "",
    },
}
CREATURE_LOCATORS = frozenset(
    locator for locator, _creature_name in CREATURE_PROFILES
)
TRAITS_RULE = {"sourceId": "core-pc1", "locator": "452.1"}
HIT_POINTS_RULE = {"sourceId": "core-pc1", "locator": "410.2"}
DEATH_RULE = {"sourceId": "core-pc1", "locator": "411.5"}
DURATION_RULE = {"sourceId": "core-pc1", "locator": "426.2"}
SAVING_THROW_RULE = {"sourceId": "core-pc1", "locator": "404.1"}
AFFLICTION_RULE = {"sourceId": "core-pc1", "locator": "430.1"}
AFFLICTION_DAMAGE_RULE = {"sourceId": "core-pc1", "locator": "430.8"}
GRABBED_RULE = {"sourceId": "core-pc1", "locator": "444.5"}
PARALYZED_RULE = {"sourceId": "core-pc1", "locator": "445.3"}
RESTRAINED_RULE = {"sourceId": "core-pc1", "locator": "446.3"}
SICKENED_RULE = {"sourceId": "core-pc1", "locator": "446.4"}
UNCONSCIOUS_RULE = {"sourceId": "core-pc1", "locator": "446.8"}
SKILL_CHECK_RULE = {"sourceId": "core-pc1", "locator": "405.2"}
LEAP_RULE = {"sourceId": "core-pc1", "locator": "417.1"}
MOVEMENT_RULE = {"sourceId": "core-pc1", "locator": "420.1"}
DIAGONAL_MOVEMENT_RULE = {"sourceId": "core-pc1", "locator": "421.6"}
REACTION_RULE = {"sourceId": "core-pc1", "locator": "436.5"}
HIGH_SKILL_RULE = {"sourceId": "core-gmc", "locator": "116.2"}
HIGH_SPELL_DC_RULE = {"sourceId": "core-gmc", "locator": "121.2"}

CONSUME_FLESH_ABILITY_ID = "consume-flesh"
CONSUME_FLESH_MECHANIC_TYPE = "ghoul-consume-flesh"
GHOUL_WHISPERS_ABILITY_ID = "ghoul-whispers"
GHOUL_WHISPERS_MECHANIC_TYPE = "ghoul-whispers"
GRAVE_KNOWLEDGE_ABILITY_ID = "grave-knowledge"
GRAVE_KNOWLEDGE_MECHANIC_TYPE = "ghoul-grave-knowledge"
SWIFT_LEAP_ABILITY_ID = "swift-leap"
SWIFT_LEAP_MECHANIC_TYPE = "ghoul-swift-leap"

CONSUME_FLESH_PROVIDER_SHA256 = (
    "c877e4cd5d50776d6143bb4f940266c1f3e0b52a4174291534a630a16c569f25"
)
GHOUL_WHISPERS_PROVIDER_SHA256 = (
    "9831fb8ea9d9bae1f492b546e38a52f050ff6f06751e2fda269b47b88ac70d0c"
)
FORBIDDEN_CRAVINGS_PROVIDER_SHA256 = (
    "d4fd900e27b14ee9b3811c7ea4822f49c479150dba67f2774d370fa39844106c"
)
GRAVE_KNOWLEDGE_PROVIDER_SHA256 = (
    "a76c8e3174d9c7776b452380b32e7a1a9b9761e31e00ba103f2ca7453bf37d71"
)
GRAVE_KNOWLEDGE_FACT_PROVIDER_SHA256 = (
    "f9a27d284e55a9cb92fee6c9367488e7612c1abe88ca3204186f37184f6c57e2"
)
SWIFT_LEAP_PROVIDER_SHA256 = (
    "0fb149f411e9e530f05f41fda40bfd33ae7c05205daed13f40ebcb07e8a6583f"
)

_PROVIDER_PATH = (
    RawMemberStep("Creating Ghouls", 2),
    RawMemberStep("Ghoul Abilities", 3),
)
_PROVIDER_SELECTIONS = {
    CONSUME_FLESH_MECHANIC_TYPE: (
        ("^.action", 8, CONSUME_FLESH_PROVIDER_SHA256),
    ),
    GHOUL_WHISPERS_MECHANIC_TYPE: (
        ("^.action", 9, GHOUL_WHISPERS_PROVIDER_SHA256),
        ("!.Forbidden Cravings", 10, FORBIDDEN_CRAVINGS_PROVIDER_SHA256),
    ),
    GRAVE_KNOWLEDGE_MECHANIC_TYPE: (
        ("!.Grave Knowledge", 11, GRAVE_KNOWLEDGE_PROVIDER_SHA256),
        ("~.p", 12, GRAVE_KNOWLEDGE_FACT_PROVIDER_SHA256),
    ),
    SWIFT_LEAP_MECHANIC_TYPE: (
        ("^.action", 13, SWIFT_LEAP_PROVIDER_SHA256),
    ),
}


def verified_authority_mechanics(
    authority: SourceAuthorityAdapter,
) -> dict[str, dict[str, Any]]:
    """Resolve every inherited Ghoul rule through the exact source carrier."""

    result: dict[str, dict[str, Any]] = {}
    for mechanic_type, requirements in _PROVIDER_SELECTIONS.items():
        digests = []
        for raw_key, ordinal, expected_digest in requirements:
            selection = authority.resolve(
                authority.address(
                    source_id=SOURCE_ID,
                    locator=LOCATOR,
                    carrier_path=_PROVIDER_PATH,
                    selection_path=(RawMemberStep(raw_key, ordinal),),
                )
            )
            digest = selection.receipt.selection_sha256
            if digest != expected_digest:
                raise ValueError(
                    "Ghoul inherited ability source changed: "
                    f"{raw_key}[{ordinal}]"
                )
            digests.append(digest)
        result[mechanic_type] = {
            "providerSelectionSha256": digests,
        }
    return result


def bind_authority_mechanic(
    patch: AbilityCompilerPatch,
    authority_mechanic: Mapping[str, Any],
) -> AbilityCompilerPatch:
    """Require the exact inherited provider set before enabling a shorthand."""

    expected = [
        digest
        for _raw_key, _ordinal, digest
        in _PROVIDER_SELECTIONS[patch.mechanic_type]
    ]
    if (
        not isinstance(authority_mechanic, Mapping)
        or set(authority_mechanic) != {"providerSelectionSha256"}
        or authority_mechanic.get("providerSelectionSha256") != expected
    ):
        raise ValueError(
            f"Ghoul authority binding failed: {patch.mechanic_type}"
        )
    return patch


def _creature_profile(source: AbilitySource) -> Mapping[str, Any] | None:
    if source.source_id != SOURCE_ID:
        return None
    return CREATURE_PROFILES.get((source.locator, source.creature_name))


def _creature_rule(source: AbilitySource) -> dict[str, str]:
    return {"sourceId": source.source_id, "locator": source.locator}


def _exact_object(
    source: AbilitySource,
    *,
    name: str,
    traits: tuple[str, ...],
    description: str | None,
) -> bool:
    if _creature_profile(source) is None:
        return False
    value = source.raw_member.value
    keys = (
        ("Action", "Traits")
        if description is None
        else ("Action", "Traits", "Description")
    )
    return bool(
        source.source_label == name
        and source.raw_member.key == f"!.{name}"
        and source.kind == "activity"
        and source.action_cost == 1
        and source.traits == traits
        and not source.trigger
        and source.description == (description or "")
        and type(value) is RawSourceObject
        and tuple(member.key for member in value.members) == keys
        and value.members[0].value == "single"
        and type(value.members[1].value) is RawSourceArray
        and value.members[1].value.items == traits
        and (
            description is None
            or value.members[2].value == description
        )
    )


def compile_consume_flesh(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    profile = _creature_profile(source)
    if profile is None:
        return None
    if not _exact_object(
        source,
        name="Consume Flesh",
        traits=("manipulate",),
        description=str(profile["consumeFleshDescription"]),
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": CONSUME_FLESH_MECHANIC_TYPE,
            "target": {
                "kind": "dead-participant-corpse",
                "maximumDistanceFeet": 5,
                "maximumAge": {"value": 1, "unit": "hours"},
            },
            "healing": {
                "dice": {
                    "count": int(profile["consumeFleshDice"]),
                    "sides": 6,
                },
                "scaling": "plus-one-die-per-two-levels",
            },
            "oncePerCorpse": True,
            "rules": {
                "ability": _creature_rule(source),
                "traits": TRAITS_RULE,
                "hitPoints": HIT_POINTS_RULE,
                "death": DEATH_RULE,
                "duration": DURATION_RULE,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_ghoul_whispers(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    profile = _creature_profile(source)
    if profile is None:
        return None
    if not _exact_object(
        source,
        name="Ghoul Whispers",
        traits=("auditory", "linguistic", "occult"),
        description=str(profile["ghoulWhispersDescription"]),
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": GHOUL_WHISPERS_MECHANIC_TYPE,
            "target": {
                "maximumDistanceFeet": 5,
                "requiredStates": [
                    "grabbed",
                    "paralyzed",
                    "restrained",
                    "unconscious",
                ],
            },
            "savingThrow": {
                "type": "will",
                "dc": int(profile["ghoulWhispersDC"]),
            },
            "affliction": {
                "id": "forbidden-cravings",
                "type": "curse",
                "stages": [
                    {"number": 1, "duration": {"value": 1, "unit": "days"}},
                    {
                        "number": 2,
                        "duration": {"value": 1, "unit": "days"},
                        "damage": {"dice": {"count": 2, "sides": 6}, "type": "void"},
                        "condition": {"name": "sickened", "value": 1, "endsWhen": "consumes-raw-meat"},
                    },
                    {"number": 3, "asStage": 2},
                    {"number": 4, "rawMeatDependent": True},
                    {"number": 5, "ghoulTransformation": True},
                ],
                "encounterRuntime": "initial-exposure",
                "longTermProgression": "campaign-clock",
            },
            "rules": {
                "ability": _creature_rule(source),
                "traits": TRAITS_RULE,
                "savingThrow": SAVING_THROW_RULE,
                "affliction": AFFLICTION_RULE,
                "afflictionDamageAndConditions": AFFLICTION_DAMAGE_RULE,
                "grabbed": GRABBED_RULE,
                "paralyzed": PARALYZED_RULE,
                "restrained": RESTRAINED_RULE,
                "sickened": SICKENED_RULE,
                "unconscious": UNCONSCIOUS_RULE,
                "highSpellDC": HIGH_SPELL_DC_RULE,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        deferred_mechanics=(
            "forbidden-cravings:daily-stage-progression-and-ghoul-transformation",
            "forbidden-cravings:cross-encounter-campaign-persistence",
        ),
    )


# Grave Knowledge is deliberately not registered in ``FRAGMENT``. Its source
# carrier is passive and does not define the invented one-action Activity
# envelope used by the earlier bounded implementation. Keep the exact-source
# parser here as dormant groundwork until a source-faithful action contract is
# designed; production compilation must leave the ability unsupported.
def compile_grave_knowledge(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    profile = _creature_profile(source)
    if profile is None:
        return None
    if not (
        source.source_label == "Grave Knowledge"
        and source.raw_member.key == "!.Grave Knowledge"
        and source.kind == "passive"
        and source.action_cost is None
        and source.traits == ()
        and not source.trigger
        and source.description == profile["graveKnowledgeDescription"]
        and source.raw_member.value == profile["graveKnowledgeDescription"]
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": GRAVE_KNOWLEDGE_MECHANIC_TYPE,
            "frequency": {"value": 1, "unit": "hours"},
            "memoryMaximumAge": {"value": 7, "unit": "days"},
            "skillModifier": int(profile["graveKnowledgeModifier"]),
            "proficiency": "trained",
            "modes": ["skill-check", "automatic-fact"],
            "runtimeBoundaries": [
                "one-action-encounter-skill-checks",
            ],
            "rules": {
                "ability": _creature_rule(source),
                "duration": DURATION_RULE,
                "skillCheck": SKILL_CHECK_RULE,
                "highSkillModifier": HIGH_SKILL_RULE,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        traits=("occult",),
        deferred_mechanics=(
            "grave-knowledge:non-one-action-skill-check-timing",
            "grave-knowledge:automatic-specific-fact-adjudication",
            "grave-knowledge:cross-encounter-seven-day-memory",
        ),
    )


def compile_swift_leap(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    profile = _creature_profile(source)
    if profile is None:
        return None
    if not _exact_object(
        source,
        name="Swift Leap",
        traits=("move",),
        description=profile["swiftLeapDescription"],
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": SWIFT_LEAP_MECHANIC_TYPE,
            "distance": {"basis": "half-effective-land-speed"},
            "movement": "jump",
            "triggersReactions": False,
            "runtimeBoundaries": [
                "tactical-plane-path-without-elevation-or-overflight",
            ],
            "rules": {
                "ability": _creature_rule(source),
                "traits": TRAITS_RULE,
                "leap": LEAP_RULE,
                "movement": MOVEMENT_RULE,
                "diagonalMovement": DIAGONAL_MOVEMENT_RULE,
                "reactions": REACTION_RULE,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        deferred_mechanics=(
            "swift-leap:elevation-overflight-and-midpath-effect-composition",
        ),
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="ghoul",
    mechanic_types=(
        CONSUME_FLESH_MECHANIC_TYPE,
        GHOUL_WHISPERS_MECHANIC_TYPE,
        SWIFT_LEAP_MECHANIC_TYPE,
    ),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id=CONSUME_FLESH_ABILITY_ID,
            mechanic_type=CONSUME_FLESH_MECHANIC_TYPE,
            compiler=compile_consume_flesh,
        ),
        AbilityCompilerRegistration(
            compiler_id=GHOUL_WHISPERS_ABILITY_ID,
            mechanic_type=GHOUL_WHISPERS_MECHANIC_TYPE,
            compiler=compile_ghoul_whispers,
        ),
        AbilityCompilerRegistration(
            compiler_id=SWIFT_LEAP_ABILITY_ID,
            mechanic_type=SWIFT_LEAP_MECHANIC_TYPE,
            compiler=compile_swift_leap,
        ),
    ),
)


__all__ = [
    "CONSUME_FLESH_ABILITY_ID",
    "CONSUME_FLESH_MECHANIC_TYPE",
    "CREATURE_NAME",
    "CREATURE_LOCATORS",
    "CREATURE_PROFILES",
    "CREATURE_RULE",
    "FRAGMENT",
    "GHOUL_WHISPERS_ABILITY_ID",
    "GHOUL_WHISPERS_MECHANIC_TYPE",
    "GRAVE_KNOWLEDGE_ABILITY_ID",
    "GRAVE_KNOWLEDGE_MECHANIC_TYPE",
    "LOCATOR",
    "SOURCE_ID",
    "SWIFT_LEAP_ABILITY_ID",
    "SWIFT_LEAP_MECHANIC_TYPE",
    "bind_authority_mechanic",
    "verified_authority_mechanics",
]

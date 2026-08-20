"""Exact Animated Armor Construct Armor compilation and runtime state.

Monster Core ``core-mc1:18.5`` inherits the operative Hardness and break
triggers from Animated Broom while supplying its own broken Armor Class.
The provider's contradictory Broom-only Armor Class scalar is deliberately
retained as excluded evidence, never as an Animated Armor runtime value.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceArray,
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


ABILITY_ID = "construct-armor"
ABILITY_LABEL = "Construct Armor"
MECHANIC_TYPE = "animated-construct-armor"
SOURCE_ID = "core-mc1"
ANIMATED_ARMOR_LOCATOR = "18.5"
ANIMATED_BROOM_LOCATOR = "18.3"
ANIMATED_ARMOR_NAME = "Animated Armor"
ANIMATED_BROOM_NAME = "Animated Broom"
BASE_ARMOR_CLASS = 17
BROKEN_ARMOR_CLASS = 13
MAXIMUM_HIT_POINTS = 20
HARDNESS = 9
BREAK_BELOW_HIT_POINTS = 10

ANIMATED_ARMOR_AC_SOURCE = (
    "17 (13 when broken); construct armor"
)
ANIMATED_ARMOR_HP_SOURCE = "20; Hardness 9"
ANIMATED_ARMOR_ABILITY_SOURCE = (
    "As animated broom, but reduced to AC 13 when broken."
)
ANIMATED_BROOM_ABILITY_SOURCE = (
    "Like normal objects, an animated broom has Hardness. "
    "This Hardness reduces any damage it takes by an amount equal to the "
    "Hardness. Once an animated broom is reduced to less than half its Hit "
    "Points, or immediately upon being damaged by a critical hit, its "
    "construct armor breaks, removing the Hardness and reducing its Armor "
    "Class to 14."
)

_ANIMATED_ARMOR_AC_RE = re.compile(
    r"^(?P<base>[1-9][0-9]*) "
    r"\((?P<broken>[1-9][0-9]*) when broken\); construct armor$",
    re.ASCII,
)
_ANIMATED_ARMOR_HP_RE = re.compile(
    r"^(?P<hit_points>[1-9][0-9]*); "
    r"Hardness (?P<hardness>[1-9][0-9]*)$",
    re.ASCII,
)
_ANIMATED_ARMOR_ABILITY_RE = re.compile(
    r"^As animated broom, but reduced to AC "
    r"(?P<broken>[1-9][0-9]*) when broken\.$",
    re.ASCII,
)
_ANIMATED_BROOM_ABILITY_RE = re.compile(
    r"^Like normal objects, an animated broom has Hardness\. "
    r"This Hardness reduces any damage it takes by an amount equal to the "
    r"Hardness\. Once an animated broom is reduced to less than half its Hit "
    r"Points, or immediately upon being damaged by a critical hit, its "
    r"construct armor breaks, removing the Hardness and reducing its Armor "
    r"Class to (?P<broken>[1-9][0-9]*)\.$",
    re.ASCII,
)

_EXPECTED_IMMUNITIES = (
    "bleed",
    "death effects",
    "disease",
    "doomed",
    "drained",
    "fatigued",
    "healing",
    "mental",
    "nonlethal attacks",
    "paralyzed",
    "poison",
    "sickened",
    "spirit",
    "unconscious",
    "vitality",
    "void",
)

_RULE_REQUIREMENTS = (
    RuleRequirement(
        rule_id="pc1-item-damage",
        source_id="core-pc1",
        locator="269.10",
        expected_block_sha256=(
            "c2c2dfbcaaaf3fff748cf539e19740e8a1f1b1d07dce96e6f0dd0d6763ba3756"
        ),
    ),
    RuleRequirement(
        rule_id="pc1-object-immunities",
        source_id="core-pc1",
        locator="269.11",
        expected_block_sha256=(
            "8ea3f3355196931b66c162bbd2e195086dfeadd1330211f955a8fd275e6f6e7a"
        ),
    ),
    RuleRequirement(
        rule_id="pc1-broken-condition",
        source_id="core-pc1",
        locator="442.7",
        expected_block_sha256=(
            "32135329b72076529f012eb51fc3f9f6c4cb0b13597016ebcdf9cf0a61f104bf"
        ),
    ),
)

_ACTIVATED_STAT_DEFERRALS = frozenset(
    {
        "annotated-stats:AC:conditional",
        "annotated-stats:AC:threshold",
        "annotated-stats:HP:threshold",
    }
)


class AnimatedConstructArmorError(ValueError):
    """The exact Animated Armor inheritance or runtime state is invalid."""


def compile_construct_armor_source(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Register the exact consumer ability before authority enrichment."""

    if (
        source.source_id != SOURCE_ID
        or source.locator != ANIMATED_ARMOR_LOCATOR
        or source.creature_name != ANIMATED_ARMOR_NAME
        or source.source_label != ABILITY_LABEL
        or source.kind != "passive"
        or source.action_cost is not None
        or source.traits
        or source.trigger
        or source.description != ANIMATED_ARMOR_ABILITY_SOURCE
        or source.raw_member.key != "!.Construct Armor"
        or source.raw_member.value != ANIMATED_ARMOR_ABILITY_SOURCE
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": MECHANIC_TYPE,
            "authorityLink": "required",
        },
        rule=RuleReference(SOURCE_ID, ANIMATED_ARMOR_LOCATOR),
    )


def bind_authority_mechanic(
    patch: AbilityCompilerPatch,
    mechanic: Mapping[str, Any],
    /,
) -> AbilityCompilerPatch:
    """Replace only the registered placeholder with its verified mechanic."""

    if (
        not isinstance(patch, AbilityCompilerPatch)
        or patch.mechanic
        != {
            "type": MECHANIC_TYPE,
            "authorityLink": "required",
        }
        or patch.rule.as_serialized()
        != {
            "sourceId": SOURCE_ID,
            "locator": ANIMATED_ARMOR_LOCATOR,
        }
        or patch.traits is not None
        or patch.deferred_mechanics
        or not isinstance(mechanic, Mapping)
        or mechanic.get("type") != MECHANIC_TYPE
    ):
        raise AnimatedConstructArmorError(
            "Animated Construct Armor registry binding is invalid"
        )
    return AbilityCompilerPatch(
        mechanic=mechanic,
        rule=patch.rule,
    )


def _selection(
    creature: VerifiedSourceSelection,
    raw_key: str,
) -> VerifiedSourceSelection:
    block = creature.selected_value
    if type(block) is not RawSourceObject:
        raise AnimatedConstructArmorError(
            "Animated Armor consumer must be an exact creature block"
        )
    matches = tuple(
        ordinal
        for ordinal, member in enumerate(block.members)
        if member.key == raw_key
    )
    if len(matches) != 1:
        raise AnimatedConstructArmorError(
            f"Animated Armor {raw_key} source is missing or duplicated"
        )
    return creature.carrier.select(
        (RawMemberStep(raw_key, matches[0]),)
    )


def _source_evidence(
    selection: VerifiedSourceSelection,
) -> dict[str, Any]:
    return {
        "sourceId": selection.address.source_id,
        "locator": selection.address.locator,
        "blockSha256": selection.block_sha256,
        "valueSha256": selection.value_sha256,
        "selectionSha256": selection.selection_sha256,
    }


def _rule_evidence(rule: VerifiedRuleReceipt) -> dict[str, Any]:
    return {
        "sourceId": rule.requirement.source_id,
        "locator": rule.requirement.locator,
        "blockSha256": rule.selection.block_sha256,
    }


def _provider_ability(
    authority: SourceAuthorityAdapter,
) -> VerifiedSourceSelection:
    root = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=SOURCE_ID,
                locator=ANIMATED_BROOM_LOCATOR,
            )
        )
    )
    raw_root = root.selected_value
    if type(raw_root) is not RawSourceObject:
        raise AnimatedConstructArmorError(
            "Animated Broom provider target must be an exact object"
        )
    providers = []
    for creature_ordinal, member in enumerate(raw_root.members):
        value = member.value
        if (
            member.key != "^.creature"
            or type(value) is not RawSourceObject
            or value.values("Name") != (ANIMATED_BROOM_NAME,)
        ):
            continue
        ability_ordinals = tuple(
            ordinal
            for ordinal, ability_member in enumerate(value.members)
            if ability_member.key == "!.Construct Armor"
        )
        if len(ability_ordinals) != 1:
            raise AnimatedConstructArmorError(
                "Animated Broom Construct Armor provider is ambiguous"
            )
        providers.append(
            authority.validate_selection(
                authority.resolve(
                    authority.address(
                        source_id=SOURCE_ID,
                        locator=ANIMATED_BROOM_LOCATOR,
                        carrier_path=(
                            RawMemberStep(
                                "^.creature",
                                creature_ordinal,
                            ),
                        ),
                        selection_path=(
                            RawMemberStep(
                                "!.Construct Armor",
                                ability_ordinals[0],
                            ),
                        ),
                    )
                )
            )
        )
    if len(providers) != 1:
        raise AnimatedConstructArmorError(
            "Animated Broom Construct Armor provider is missing or duplicated"
        )
    return providers[0]


def compile_animated_construct_armor(
    authority: SourceAuthorityAdapter,
    creature: VerifiedSourceSelection,
    /,
) -> dict[str, Any] | None:
    """Compile only the exact source-bound Animated Armor inheritance."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "Animated Construct Armor requires an exact "
            "SourceAuthorityAdapter"
        )
    if type(creature) is not VerifiedSourceSelection:
        raise TypeError(
            "Animated Construct Armor requires an exact verified creature"
        )
    creature = authority.validate_selection(creature)
    address = creature.address
    name_selection = _selection(creature, "Name")
    name = name_selection.selected_value
    if (
        address.source_id != SOURCE_ID
        or address.locator != ANIMATED_ARMOR_LOCATOR
        or name != ANIMATED_ARMOR_NAME
    ):
        return None
    if authority.toc_label(SOURCE_ID, ANIMATED_ARMOR_LOCATOR) != name:
        raise AnimatedConstructArmorError(
            "Animated Armor source target label drifted"
        )

    level = _selection(creature, "Level")
    size = _selection(creature, "Size")
    traits = _selection(creature, "Traits")
    armor_class = _selection(creature, "AC")
    hit_points = _selection(creature, "HP")
    immunities = _selection(creature, "Immunities")
    local_ability = _selection(creature, "!.Construct Armor")
    if level.selected_value != 2 or size.selected_value != "Medium":
        raise AnimatedConstructArmorError(
            "Animated Armor level or size drifted"
        )
    if (
        type(traits.selected_value) is not RawSourceArray
        or traits.selected_value.items != ("construct", "mindless")
    ):
        raise AnimatedConstructArmorError(
            "Animated Armor traits drifted"
        )
    if (
        type(immunities.selected_value) is not RawSourceArray
        or immunities.selected_value.items != _EXPECTED_IMMUNITIES
    ):
        raise AnimatedConstructArmorError(
            "Animated Armor construct immunities drifted"
        )

    raw_ac = armor_class.selected_value
    raw_hp = hit_points.selected_value
    raw_local_ability = local_ability.selected_value
    if (
        type(raw_ac) is not str
        or type(raw_hp) is not str
        or type(raw_local_ability) is not str
    ):
        raise AnimatedConstructArmorError(
            "Animated Armor annotated stats or ability are not text"
        )
    ac_match = _ANIMATED_ARMOR_AC_RE.fullmatch(raw_ac)
    hp_match = _ANIMATED_ARMOR_HP_RE.fullmatch(raw_hp)
    local_match = _ANIMATED_ARMOR_ABILITY_RE.fullmatch(
        raw_local_ability
    )
    if (
        ac_match is None
        or hp_match is None
        or local_match is None
        or raw_ac != ANIMATED_ARMOR_AC_SOURCE
        or raw_hp != ANIMATED_ARMOR_HP_SOURCE
        or raw_local_ability != ANIMATED_ARMOR_ABILITY_SOURCE
    ):
        raise AnimatedConstructArmorError(
            "Animated Armor Construct Armor source grammar drifted"
        )
    base_ac = int(ac_match.group("base"))
    stat_broken_ac = int(ac_match.group("broken"))
    local_broken_ac = int(local_match.group("broken"))
    maximum_hp = int(hp_match.group("hit_points"))
    hardness = int(hp_match.group("hardness"))
    if (
        base_ac != BASE_ARMOR_CLASS
        or stat_broken_ac != BROKEN_ARMOR_CLASS
        or local_broken_ac != stat_broken_ac
        or maximum_hp != MAXIMUM_HIT_POINTS
        or hardness != HARDNESS
    ):
        raise AnimatedConstructArmorError(
            "Animated Armor local stat and ability values disagree"
        )

    provider = _provider_ability(authority)
    provider_text = provider.selected_value
    provider_match = (
        _ANIMATED_BROOM_ABILITY_RE.fullmatch(provider_text)
        if type(provider_text) is str
        else None
    )
    if (
        provider_match is None
        or provider_text != ANIMATED_BROOM_ABILITY_SOURCE
    ):
        raise AnimatedConstructArmorError(
            "Animated Broom Construct Armor provider drifted"
        )
    provider_broken_ac = int(provider_match.group("broken"))
    if provider_broken_ac == BROKEN_ARMOR_CLASS:
        raise AnimatedConstructArmorError(
            "Animated Broom excluded scalar no longer proves an override"
        )

    rules = tuple(
        authority.resolve_rule(requirement)
        for requirement in _RULE_REQUIREMENTS
    )
    authority.require_shared_authority(
        creature,
        rules,
    )
    return {
        "type": MECHANIC_TYPE,
        "baseArmorClass": base_ac,
        "brokenArmorClass": stat_broken_ac,
        "maximumHitPoints": maximum_hp,
        "hardness": hardness,
        "breakThreshold": {
            "kind": "strictly-below-half-hit-points",
            "hitPoints": BREAK_BELOW_HIT_POINTS,
        },
        "breakOnCriticalHitDamage": True,
        "brokenEffects": {
            "removeHardness": True,
            "armorClass": stat_broken_ac,
        },
        "inheritance": {
            "provider": {
                **_source_evidence(provider),
                "creatureName": ANIMATED_BROOM_NAME,
                "abilityId": ABILITY_ID,
                "sourceText": provider_text,
            },
            "inheritedClauses": [
                "hardness-reduces-each-damage-event",
                "break-strictly-below-half-hit-points",
                "break-on-critical-hit-damage",
                "broken-removes-hardness",
            ],
            "excludedProviderScalar": {
                "field": "brokenArmorClass",
                "value": provider_broken_ac,
                "status": "not-inherited",
                "reason": (
                    "Animated Armor supplies its own broken Armor Class"
                ),
            },
            "consumerOverride": {
                "statLineValue": stat_broken_ac,
                "abilityValue": local_broken_ac,
                "agreement": True,
            },
        },
        "source": {
            "creature": _source_evidence(creature),
            "armorClass": _source_evidence(armor_class),
            "hitPoints": _source_evidence(hit_points),
            "ability": _source_evidence(local_ability),
            "immunities": _source_evidence(immunities),
        },
        "rules": {
            rule.rule_id: _rule_evidence(rule)
            for rule in rules
        },
        "unsupportedObjectDamageExceptions": [
            {
                "id": "direct-object-targeting",
                "reason": (
                    "Construct Armor applies only after an effect has "
                    "legally resolved damage against Animated Armor as a "
                    "creature; general attended-object targeting is not "
                    "implemented"
                ),
            },
            {
                "id": "exceptional-item-damage",
                "reason": (
                    "abilities that directly break or damage carried items "
                    "require their own source compiler"
                ),
            },
            {
                "id": "gm-discretion-object-conditions",
                "reason": (
                    "GM-discretion object condition exceptions are not "
                    "inferred"
                ),
            },
        ],
    }


def activate_definition(
    definition: dict[str, Any],
    mechanic: Mapping[str, Any],
) -> dict[str, Any]:
    """Link the exact compiled passive into one legacy creature projection."""

    if (
        definition.get("id")
        != f"{SOURCE_ID}:{ANIMATED_ARMOR_LOCATOR}"
        or definition.get("name") != ANIMATED_ARMOR_NAME
        or mechanic.get("type") != MECHANIC_TYPE
    ):
        raise AnimatedConstructArmorError(
            "Animated Armor definition link target is invalid"
        )
    abilities = definition.get("abilities")
    matches = [
        ability
        for ability in abilities or []
        if isinstance(ability, dict)
        and ability.get("id") == ABILITY_ID
    ]
    if (
        not isinstance(abilities, list)
        or len(matches) != 1
        or matches[0].get("name") != ABILITY_LABEL
        or matches[0].get("kind") != "passive"
        or matches[0].get("description")
        != ANIMATED_ARMOR_ABILITY_SOURCE
    ):
        raise AnimatedConstructArmorError(
            "Animated Armor ability projection is missing or ambiguous"
        )
    ability = matches[0]
    if (
        ability.get("supported") is not True
        or ability.get("rule")
        != {
            "sourceId": SOURCE_ID,
            "locator": ANIMATED_ARMOR_LOCATOR,
        }
        or ability.get("mechanic") != dict(mechanic)
    ):
        raise AnimatedConstructArmorError(
            "Animated Armor registry projection disagrees with authority"
        )

    definition["unsupportedMechanics"] = [
        item
        for item in definition.get("unsupportedMechanics") or []
        if item != ABILITY_LABEL
    ]
    definition["deferredMechanics"] = [
        item
        for item in definition.get("deferredMechanics") or []
        if item not in _ACTIVATED_STAT_DEFERRALS
    ]
    stat_compilation = definition.get("statCompilation")
    if isinstance(stat_compilation, dict):
        families = stat_compilation.get("families")
        annotated = (
            families.get("annotatedStats")
            if isinstance(families, dict)
            else None
        )
        if not isinstance(annotated, dict):
            raise AnimatedConstructArmorError(
                "Animated Armor annotated-stat projection is missing"
            )
        for field_name in ("AC", "HP"):
            field = annotated.get(field_name)
            if not isinstance(field, dict):
                raise AnimatedConstructArmorError(
                    f"Animated Armor annotated {field_name} is missing"
                )
            field["runtimeSupported"] = True
            runtime = field.get("runtime")
            if not isinstance(runtime, dict):
                raise AnimatedConstructArmorError(
                    f"Animated Armor annotated {field_name} runtime is invalid"
                )
            runtime["status"] = "activated"
            runtime["deferrals"] = []
        deferred = stat_compilation.get("runtimeDeferredMechanics")
        if not isinstance(deferred, list):
            raise AnimatedConstructArmorError(
                "Animated Armor stat deferral projection is invalid"
            )
        stat_compilation["runtimeDeferredMechanics"] = [
            item
            for item in deferred
            if item not in _ACTIVATED_STAT_DEFERRALS
        ]
        stat_compilation["runtimeReady"] = not bool(
            stat_compilation["runtimeDeferredMechanics"]
        )
    return definition


FRAGMENT = MechanicFamilyFragment(
    family_id="animated-construct-armor",
    mechanic_types=(MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id=ABILITY_ID,
            mechanic_type=MECHANIC_TYPE,
            compiler=compile_construct_armor_source,
        ),
    ),
)


def _validated_selected_mechanic(
    definition: Mapping[str, Any],
    ability: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate one already-indexed Construct Armor ability."""

    mechanic = ability.get("mechanic")
    if (
        ability.get("id") != ABILITY_ID
        or ability.get("supported") is not True
        or not isinstance(mechanic, Mapping)
        or mechanic.get("type") != MECHANIC_TYPE
    ):
        raise AnimatedConstructArmorError(
            "Animated Construct Armor definition is invalid"
        )
    if (
        definition.get("id")
        != f"{SOURCE_ID}:{ANIMATED_ARMOR_LOCATOR}"
        or definition.get("name") != ANIMATED_ARMOR_NAME
        or int(definition.get("defenses", {}).get("armorClass", -1))
        != BASE_ARMOR_CLASS
        or int(
            definition.get("defenses", {}).get(
                "maximumHitPoints",
                -1,
            )
        )
        != MAXIMUM_HIT_POINTS
        or mechanic.get("baseArmorClass") != BASE_ARMOR_CLASS
        or mechanic.get("brokenArmorClass") != BROKEN_ARMOR_CLASS
        or mechanic.get("maximumHitPoints") != MAXIMUM_HIT_POINTS
        or mechanic.get("hardness") != HARDNESS
        or mechanic.get("breakThreshold")
        != {
            "kind": "strictly-below-half-hit-points",
            "hitPoints": BREAK_BELOW_HIT_POINTS,
        }
        or mechanic.get("breakOnCriticalHitDamage") is not True
        or mechanic.get("brokenEffects")
        != {
            "removeHardness": True,
            "armorClass": BROKEN_ARMOR_CLASS,
        }
    ):
        raise AnimatedConstructArmorError(
            "Animated Construct Armor definition drifted"
        )
    return mechanic


def mechanic_from_definition(
    definition: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Return and validate the exact linked mechanic, if present."""

    matches = [
        ability
        for ability in definition.get("abilities") or []
        if isinstance(ability, Mapping)
        and ability.get("id") == ABILITY_ID
        and ability.get("supported") is True
        and isinstance(ability.get("mechanic"), Mapping)
        and ability["mechanic"].get("type") == MECHANIC_TYPE
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise AnimatedConstructArmorError(
            "Animated Construct Armor definition is ambiguous"
        )
    return _validated_selected_mechanic(definition, matches[0])


def initial_participant_state(
    definition: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Create the only legal intact opening state for the exact mechanic."""

    mechanic = mechanic_from_definition(definition)
    if mechanic is None:
        return None
    return {
        "abilityId": ABILITY_ID,
        "broken": False,
    }


def validate_participant_state(
    definition: Mapping[str, Any],
    participant: Mapping[str, Any],
    *,
    selected_ability: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    """Reject missing, forged, or HP-inconsistent Construct Armor state."""

    mechanic = (
        mechanic_from_definition(definition)
        if selected_ability is None
        else _validated_selected_mechanic(
            definition,
            selected_ability,
        )
    )
    state = participant.get("constructArmor")
    if mechanic is None:
        if state is not None:
            raise AnimatedConstructArmorError(
                "participant invented Construct Armor state"
            )
        return None
    if (
        not isinstance(state, Mapping)
        or set(state) != {"abilityId", "broken"}
        or state.get("abilityId") != ABILITY_ID
        or type(state.get("broken")) is not bool
    ):
        raise AnimatedConstructArmorError(
            "participant Construct Armor state is invalid"
        )
    hit_points = participant.get("hitPoints")
    if (
        not isinstance(hit_points, Mapping)
        or isinstance(hit_points.get("current"), bool)
        or not isinstance(hit_points.get("current"), int)
        or isinstance(hit_points.get("maximum"), bool)
        or not isinstance(hit_points.get("maximum"), int)
        or hit_points.get("maximum") != MAXIMUM_HIT_POINTS
        or not 0 <= int(hit_points["current"]) <= MAXIMUM_HIT_POINTS
        or (
            int(hit_points["current"]) < BREAK_BELOW_HIT_POINTS
            and state.get("broken") is not True
        )
    ):
        raise AnimatedConstructArmorError(
            "participant Construct Armor HP state is invalid"
        )
    return state


def effective_armor_class(
    definition: Mapping[str, Any],
    participant: Mapping[str, Any],
) -> int | None:
    """Return the intact or broken source Armor Class."""

    state = validate_participant_state(definition, participant)
    if state is None:
        return None
    return (
        BROKEN_ARMOR_CLASS
        if state["broken"]
        else BASE_ARMOR_CLASS
    )


def resolve_incoming_damage(
    definition: Mapping[str, Any],
    participant: Mapping[str, Any],
    *,
    post_defense_damage: int,
    critical_hit: bool,
) -> dict[str, Any] | None:
    """Resolve Hardness once and the one-way Construct Armor transition."""

    state = validate_participant_state(definition, participant)
    if state is None:
        return None
    if (
        isinstance(post_defense_damage, bool)
        or not isinstance(post_defense_damage, int)
        or post_defense_damage < 0
        or type(critical_hit) is not bool
    ):
        raise AnimatedConstructArmorError(
            "Construct Armor incoming damage context is invalid"
        )
    broken_before = bool(state["broken"])
    hardness = (
        0
        if broken_before or post_defense_damage == 0
        else HARDNESS
    )
    prevented = min(post_defense_damage, hardness)
    applied = max(0, post_defense_damage - hardness)
    hit_points_before = int(participant["hitPoints"]["current"])
    hit_points_after = max(0, hit_points_before - applied)
    critical_trigger = bool(
        not broken_before
        and critical_hit
        and applied > 0
    )
    threshold_trigger = bool(
        not broken_before
        and hit_points_after < BREAK_BELOW_HIT_POINTS
    )
    newly_broken = critical_trigger or threshold_trigger
    broken_after = broken_before or newly_broken
    causes = []
    if critical_trigger:
        causes.append("critical-hit-damage")
    if threshold_trigger:
        causes.append("below-half-hit-points")
    return {
        "postDefenseDamage": post_defense_damage,
        "hardness": hardness,
        "preventedByHardness": prevented,
        "appliedDamage": applied,
        "hitPointsBefore": hit_points_before,
        "hitPointsAfter": hit_points_after,
        "brokenBefore": broken_before,
        "brokenAfter": broken_after,
        "newlyBroken": newly_broken,
        "breakCauses": causes,
        "criticalHit": critical_hit,
        "stateAfter": {
            "abilityId": ABILITY_ID,
            "broken": broken_after,
        },
        "rules": deepcopy(dict(mechanic_from_definition(definition)["rules"])),
    }


__all__ = [
    "ABILITY_ID",
    "ABILITY_LABEL",
    "ANIMATED_ARMOR_ABILITY_SOURCE",
    "ANIMATED_ARMOR_AC_SOURCE",
    "ANIMATED_ARMOR_LOCATOR",
    "ANIMATED_ARMOR_NAME",
    "ANIMATED_ARMOR_HP_SOURCE",
    "ANIMATED_BROOM_ABILITY_SOURCE",
    "ANIMATED_BROOM_LOCATOR",
    "AnimatedConstructArmorError",
    "BASE_ARMOR_CLASS",
    "BREAK_BELOW_HIT_POINTS",
    "BROKEN_ARMOR_CLASS",
    "FRAGMENT",
    "HARDNESS",
    "MAXIMUM_HIT_POINTS",
    "MECHANIC_TYPE",
    "activate_definition",
    "bind_authority_mechanic",
    "compile_animated_construct_armor",
    "compile_construct_armor_source",
    "effective_armor_class",
    "initial_participant_state",
    "mechanic_from_definition",
    "resolve_incoming_damage",
    "validate_participant_state",
]

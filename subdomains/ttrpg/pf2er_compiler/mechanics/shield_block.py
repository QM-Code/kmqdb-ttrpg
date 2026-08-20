"""Compile the reviewed Monster Core Shield Block reference grammar."""

from __future__ import annotations

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceObject,
    RuleReference,
)


ABILITY_ID = "shield-block"
ABILITY_LABEL = "Shield Block"
MECHANIC_TYPE = "raised-shield-damage-reaction"
MONSTER_CORE_RULE = RuleReference("core-mc1", "358.2")
PLAYER_CORE_RULE = RuleReference("core-pc1", "262.4")
RAISE_A_SHIELD_RULE = RuleReference("core-pc1", "419.9")
SHIELD_STATISTICS_RULE = RuleReference("core-pc1", "274.1")
ITEM_DAMAGE_RULE = RuleReference("core-pc1", "269.10")
DAMAGE_ORDER_RULE = RuleReference("core-pc1", "407.3")
PHYSICAL_DAMAGE_RULE = RuleReference("core-pc1", "409.2")
TRIGGERED_ACTIONS_RULE = RuleReference("core-pc1", "414.6")
TURN_START_RULE = RuleReference("core-pc1", "435.8")

_LOCAL_REFERENCE_TEXTS = frozenset(
    {
        "(page 360)",
        "page 360",
    }
)
QUALIFYING_DAMAGE_TYPES = (
    "bludgeoning",
    "piercing",
    "slashing",
)


def _rule(reference: RuleReference) -> dict[str, str]:
    return {
        "sourceId": reference.source_id,
        "locator": reference.locator,
    }


def compile_shield_block(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact page-reference form used by Monster Core."""

    if (
        source.source_id != "core-mc1"
        or source.source_label != ABILITY_LABEL
        or source.kind != "reaction"
        or source.action_cost != "reaction"
        or source.traits
        or source.trigger != ""
        or source.description not in _LOCAL_REFERENCE_TEXTS
        or source.raw_member.key != "!.Shield Block"
    ):
        return None
    value = source.raw_member.value
    if (
        type(value) is not RawSourceObject
        or tuple(member.key for member in value.members)
        != ("Action", "Description")
        or value.members[0].value != "reaction"
        or value.members[1].value != source.description
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": MECHANIC_TYPE,
            "requiresRaisedShield": True,
            "requiresDamageFromAttack": True,
            "qualifyingDamageTypes": list(
                QUALIFYING_DAMAGE_TYPES
            ),
            "prevention": "shield-hardness-once",
            "allocation": (
                "same-remaining-to-creature-and-shield"
            ),
            "rules": {
                "monsterAbility": _rule(MONSTER_CORE_RULE),
                "playerAbility": _rule(PLAYER_CORE_RULE),
                "raiseShield": _rule(RAISE_A_SHIELD_RULE),
                "shieldStatistics": _rule(
                    SHIELD_STATISTICS_RULE
                ),
                "itemDamage": _rule(ITEM_DAMAGE_RULE),
                "damageOrder": _rule(DAMAGE_ORDER_RULE),
                "physicalDamage": _rule(PHYSICAL_DAMAGE_RULE),
                "triggeredActions": _rule(
                    TRIGGERED_ACTIONS_RULE
                ),
                "turnStart": _rule(TURN_START_RULE),
            },
        },
        rule=MONSTER_CORE_RULE,
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="shield-block",
    mechanic_types=(MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="shield-block",
            mechanic_type=MECHANIC_TYPE,
            compiler=compile_shield_block,
        ),
    ),
)


__all__ = [
    "ABILITY_ID",
    "ABILITY_LABEL",
    "DAMAGE_ORDER_RULE",
    "FRAGMENT",
    "ITEM_DAMAGE_RULE",
    "MECHANIC_TYPE",
    "MONSTER_CORE_RULE",
    "PHYSICAL_DAMAGE_RULE",
    "PLAYER_CORE_RULE",
    "QUALIFYING_DAMAGE_TYPES",
    "RAISE_A_SHIELD_RULE",
    "SHIELD_STATISTICS_RULE",
    "TRIGGERED_ACTIONS_RULE",
    "TURN_START_RULE",
    "compile_shield_block",
]

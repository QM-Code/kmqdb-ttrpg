"""Compile three reviewed creature-specific triggered reactions.

Tail Lash and Giant Crab Scuttle store their authored effect in an ``Effect``
member rather than ``Description``.  Their compilers therefore authenticate
the complete duplicate-preserving raw object instead of treating the empty
normalized description as missing source.  Biting Snakes uses the ordinary
``Description`` shape but is held to the same exact-source boundary.

This module deliberately stops at compilation and small trigger predicates.
The encounter suspension, Strike resolution, AC adjustment, and movement
protocols remain central integration concerns.
"""

from __future__ import annotations

from collections.abc import Mapping

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceObject,
    RuleReference,
)


TAIL_LASH_LABEL = "Tail Lash"
TAIL_LASH_MECHANIC_TYPE = "pre-roll-tail-strike-reaction"
TAIL_LASH_SOURCE_ID = "core-mc1"
TAIL_LASH_LOCATOR = "129.1"
TAIL_LASH_TRIGGER = (
    "A creature within reach of the river drake's tail uses an action "
    "to Strike or attempt a skill check;"
)
TAIL_LASH_EFFECT = (
    "The river drake attempts to Strike the triggering creature with "
    "their tail. If it hits, the target takes a -2 circumstance penalty "
    "to the triggering roll."
)

BITING_SNAKES_LABEL = "Biting Snakes"
BITING_SNAKES_MECHANIC_TYPE = "turn-end-adjacent-strike-reaction"
BITING_SNAKES_SOURCE_ID = "core-mc1"
BITING_SNAKES_LOCATOR = "230.1"
BITING_SNAKES_TRIGGER = (
    "A creature ends its turn adjacent to the medusa."
)
BITING_SNAKES_DESCRIPTION = (
    "The medusa makes a snake fangs Strike against the creature."
)

GIANT_CRAB_SCUTTLE_LABEL = "Scuttle"
GIANT_CRAB_SCUTTLE_MECHANIC_TYPE = (
    "targeted-by-attack-ac-stride-reaction"
)
GIANT_CRAB_SCUTTLE_SOURCE_ID = "core-mc2"
GIANT_CRAB_SCUTTLE_LOCATOR = "77.2"
GIANT_CRAB_SCUTTLE_TRIGGER = (
    "A creature that the giant crab can see targets the crab with an "
    "attack while the giant crab isn’t prone"
)
GIANT_CRAB_SCUTTLE_EFFECT = (
    "The giant crab scuttles to the side and gains a +2 circumstance "
    "bonus to AC against the triggering attack. After the attack "
    "resolves, the crab can Stride up to its speed in a straight line "
    "as part of the reaction."
)


def _exact_raw_fields(
    source: AbilitySource,
    /,
    *,
    raw_key: str,
    expected: tuple[tuple[str, str], ...],
) -> Mapping[str, str] | None:
    """Return an exact, ordered scalar object or fail closed."""

    if source.raw_member.key != raw_key:
        return None
    value = source.raw_member.value
    if type(value) is not RawSourceObject:
        return None
    if tuple(member.key for member in value.members) != tuple(
        key for key, _expected_value in expected
    ):
        return None
    fields: dict[str, str] = {}
    for member, (expected_key, expected_value) in zip(
        value.members,
        expected,
        strict=True,
    ):
        if (
            member.key != expected_key
            or type(member.value) is not str
            or member.value != expected_value
        ):
            return None
        fields[member.key] = member.value
    return fields


def _is_exact_reaction(
    source: AbilitySource,
    /,
    *,
    label: str,
    source_id: str,
    locator: str,
) -> bool:
    return (
        source.source_label == label
        and source.source_id == source_id
        and source.locator == locator
        and source.kind == "reaction"
        and source.action_cost == "reaction"
        and source.traits == ()
    )


def compile_tail_lash(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the River Drake's exact pre-roll Tail Lash reaction."""

    fields = _exact_raw_fields(
        source,
        raw_key="!.Tail Lash",
        expected=(
            ("Action", "reaction"),
            ("Trigger", TAIL_LASH_TRIGGER),
            ("Effect", TAIL_LASH_EFFECT),
        ),
    )
    if fields is None:
        return None
    if not _is_exact_reaction(
        source,
        label=TAIL_LASH_LABEL,
        source_id=TAIL_LASH_SOURCE_ID,
        locator=TAIL_LASH_LOCATOR,
    ):
        return None
    if (
        source.trigger != fields["Trigger"]
        or source.description != ""
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": TAIL_LASH_MECHANIC_TYPE,
            "strikeId": "tail",
            "target": "triggering-creature",
            "trigger": {
                "event": "action-use",
                "actionKinds": ["strike", "skill-check"],
                "relation": "within-tail-strike-reach",
                "timing": "before-triggering-roll",
            },
            "onHit": {
                "triggeringRollCircumstancePenalty": -2,
            },
            "multipleAttackPenalty": {
                "applies": False,
                "counts": False,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_biting_snakes(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the Medusa's exact adjacent turn-end Strike reaction."""

    fields = _exact_raw_fields(
        source,
        raw_key="!.Biting Snakes",
        expected=(
            ("Action", "reaction"),
            ("Trigger", BITING_SNAKES_TRIGGER),
            ("Description", BITING_SNAKES_DESCRIPTION),
        ),
    )
    if fields is None:
        return None
    if not _is_exact_reaction(
        source,
        label=BITING_SNAKES_LABEL,
        source_id=BITING_SNAKES_SOURCE_ID,
        locator=BITING_SNAKES_LOCATOR,
    ):
        return None
    if (
        source.trigger != fields["Trigger"]
        or source.description != fields["Description"]
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": BITING_SNAKES_MECHANIC_TYPE,
            "strikeId": "snake-fangs",
            "target": "triggering-creature",
            "trigger": {
                "event": "turn-end",
                "relation": "adjacent",
                "timing": "after-triggering-turn",
            },
            "multipleAttackPenalty": {
                "applies": False,
                "counts": False,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_giant_crab_scuttle(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the Giant Crab's exact defensive Scuttle reaction."""

    fields = _exact_raw_fields(
        source,
        raw_key="!.Scuttle",
        expected=(
            ("Action", "reaction"),
            ("Trigger", GIANT_CRAB_SCUTTLE_TRIGGER),
            ("Effect", GIANT_CRAB_SCUTTLE_EFFECT),
        ),
    )
    if fields is None:
        return None
    if not _is_exact_reaction(
        source,
        label=GIANT_CRAB_SCUTTLE_LABEL,
        source_id=GIANT_CRAB_SCUTTLE_SOURCE_ID,
        locator=GIANT_CRAB_SCUTTLE_LOCATOR,
    ):
        return None
    if (
        source.trigger != fields["Trigger"]
        or source.description != ""
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": GIANT_CRAB_SCUTTLE_MECHANIC_TYPE,
            "trigger": {
                "event": "targeted-by-attack",
                "requiresVisibleAttacker": True,
                "requiresNotProne": True,
                "timing": "before-triggering-attack",
            },
            "armorClass": {
                "circumstanceBonus": 2,
                "appliesTo": "triggering-attack",
            },
            "afterAttack": {
                "movement": "Stride",
                "maximumDistance": "speed",
                "path": "straight-line",
                "optional": True,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def tail_lash_trigger_applies(
    *,
    reaction_available: bool,
    triggering_creature_is_reactor: bool,
    triggering_action_kind: str,
    triggering_roll_pending: bool,
    triggering_creature_in_tail_reach: bool,
    tail_strike_available: bool,
) -> bool:
    """Decide the exact Tail Lash trigger without resolving its Strike."""

    return (
        reaction_available is True
        and triggering_creature_is_reactor is False
        and triggering_action_kind in {"strike", "skill-check"}
        and triggering_roll_pending is True
        and triggering_creature_in_tail_reach is True
        and tail_strike_available is True
    )


def biting_snakes_trigger_applies(
    *,
    reaction_available: bool,
    triggering_creature_is_reactor: bool,
    triggering_creature_ended_turn: bool,
    triggering_creature_adjacent: bool,
    snake_fangs_strike_available: bool,
) -> bool:
    """Decide the exact Biting Snakes trigger without resolving its Strike."""

    return (
        reaction_available is True
        and triggering_creature_is_reactor is False
        and triggering_creature_ended_turn is True
        and triggering_creature_adjacent is True
        and snake_fangs_strike_available is True
    )


def giant_crab_scuttle_trigger_applies(
    *,
    reaction_available: bool,
    triggering_creature_is_reactor: bool,
    triggering_attack_targets_reactor: bool,
    triggering_creature_visible: bool,
    triggering_attack_pending: bool,
    reactor_prone: bool,
) -> bool:
    """Decide the exact Giant Crab Scuttle trigger before the attack."""

    return (
        reaction_available is True
        and triggering_creature_is_reactor is False
        and triggering_attack_targets_reactor is True
        and triggering_creature_visible is True
        and triggering_attack_pending is True
        and reactor_prone is False
    )


TAIL_LASH_FRAGMENT = MechanicFamilyFragment(
    family_id="tail-lash",
    mechanic_types=(TAIL_LASH_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="tail-lash",
            mechanic_type=TAIL_LASH_MECHANIC_TYPE,
            compiler=compile_tail_lash,
        ),
    ),
)

BITING_SNAKES_FRAGMENT = MechanicFamilyFragment(
    family_id="biting-snakes",
    mechanic_types=(BITING_SNAKES_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="biting-snakes",
            mechanic_type=BITING_SNAKES_MECHANIC_TYPE,
            compiler=compile_biting_snakes,
        ),
    ),
)

GIANT_CRAB_SCUTTLE_FRAGMENT = MechanicFamilyFragment(
    family_id="giant-crab-scuttle",
    mechanic_types=(GIANT_CRAB_SCUTTLE_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="giant-crab-scuttle",
            mechanic_type=GIANT_CRAB_SCUTTLE_MECHANIC_TYPE,
            compiler=compile_giant_crab_scuttle,
        ),
    ),
)

FRAGMENT = MechanicFamilyFragment(
    family_id="triggered-creature-reactions",
    mechanic_types=(
        *TAIL_LASH_FRAGMENT.mechanic_types,
        *BITING_SNAKES_FRAGMENT.mechanic_types,
        *GIANT_CRAB_SCUTTLE_FRAGMENT.mechanic_types,
    ),
    ability_compilers=(
        *TAIL_LASH_FRAGMENT.ability_compilers,
        *BITING_SNAKES_FRAGMENT.ability_compilers,
        *GIANT_CRAB_SCUTTLE_FRAGMENT.ability_compilers,
    ),
)


__all__ = [
    "BITING_SNAKES_FRAGMENT",
    "BITING_SNAKES_MECHANIC_TYPE",
    "FRAGMENT",
    "GIANT_CRAB_SCUTTLE_FRAGMENT",
    "GIANT_CRAB_SCUTTLE_MECHANIC_TYPE",
    "TAIL_LASH_FRAGMENT",
    "TAIL_LASH_MECHANIC_TYPE",
    "biting_snakes_trigger_applies",
    "compile_biting_snakes",
    "compile_giant_crab_scuttle",
    "compile_tail_lash",
    "giant_crab_scuttle_trigger_applies",
    "tail_lash_trigger_applies",
]

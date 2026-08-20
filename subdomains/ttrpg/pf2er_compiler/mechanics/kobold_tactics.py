"""Compile and expose narrow runtime contracts for kobold tactics.

The reviewed Monster Core source has one complete Scamper definition on the
Kobold Warrior and one exact inherited reference on the Kobold Scout.  This
module accepts only those duplicate-preserving raw members.  Construct Trap is
likewise confined to the complete Kobold Scout definition.

The runtime helpers intentionally own only the source-specific predicates and
damage scaling.  Ordinary Stride legality, action accounting, map surfaces,
participant occupancy, reactions, damage defenses, persistent-damage
lifecycle, and encounter time remain central engine responsibilities.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceArray,
    RawSourceObject,
    RuleReference,
)


KOBOLD_SOURCE_ID = "core-mc1"
KOBOLD_WARRIOR_LOCATOR = "210.2"
KOBOLD_SCOUT_LOCATOR = "210.4"

CONSTRUCT_TRAP_MECHANIC_TYPE = "kobold-construct-trap"
SCAMPER_MECHANIC_TYPE = "kobold-scamper"

CONSTRUCT_TRAP_ACTION_COST = 3
CONSTRUCT_TRAP_SAVE_DC = 16
CONSTRUCT_TRAP_INITIAL_MATERIAL_USES = 1
SCAMPER_ACTION_COST = 1
SCAMPER_SPEED_BONUS_FEET = 5
SCAMPER_REACTION_AC_BONUS = 2

_CONSTRUCT_TRAP_DESCRIPTION = (
    "The kobold scout creates a rudimentary trap on any square adjacent to "
    "it. This must be on a surface, such as a floor, wall, or ceiling. The "
    "trap activates the next time a creature moves adjacent to it. The "
    "creature takes 1d6 piercing damage and 1 persistent bleed damage with a "
    "DC 16 basic Reflex save. The trap is destroyed when activated or after "
    "1 hour, whichever comes first. The scout typically carries enough raw "
    "materials to make one trap."
)
_SCAMPER_REQUIREMENTS = (
    "The kobold warrior is adjacent to at least one enemy."
)
_SCAMPER_EFFECT = (
    "The kobold warrior Strides up to their Speed plus 5 feet and gains a +2 "
    "circumstance bonus to AC against reactions triggered by this movement. "
    "They must end this movement in a space that's not adjacent to any enemy."
)
_SCOUT_SCAMPER_REFERENCE = "As kobold warrior."

SerializedSquare: TypeAlias = Mapping[str, int]
_Coordinate: TypeAlias = tuple[int, int]


def _exact_object(
    value: object,
    expected_members: tuple[tuple[str, object], ...],
    /,
) -> bool:
    if type(value) is not RawSourceObject:
        return False
    members = value.members
    if len(members) != len(expected_members):
        return False
    return all(
        member.key == expected_key and member.value == expected_value
        for member, (expected_key, expected_value)
        in zip(members, expected_members, strict=True)
    )


def _common_source_match(
    source: AbilitySource,
    *,
    source_label: str,
    locator: str,
    creature_name: str,
    action_cost: int,
) -> bool:
    return (
        source.source_id == KOBOLD_SOURCE_ID
        and source.locator == locator
        and source.creature_name == creature_name
        and source.source_label == source_label
        and source.raw_member.key == f"!.{source_label}"
        and source.kind == "activity"
        and source.action_cost == action_cost
        and source.trigger == ""
    )


def compile_construct_trap(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the complete reviewed Kobold Scout trap definition."""

    if not _common_source_match(
        source,
        source_label="Construct Trap",
        locator=KOBOLD_SCOUT_LOCATOR,
        creature_name="Kobold Scout",
        action_cost=CONSTRUCT_TRAP_ACTION_COST,
    ):
        return None
    if (
        source.traits != ("manipulate",)
        or source.description != _CONSTRUCT_TRAP_DESCRIPTION
        or not _exact_object(
            source.raw_member.value,
            (
                ("Action", "three"),
                ("Traits", RawSourceArray(("manipulate",))),
                ("Description", _CONSTRUCT_TRAP_DESCRIPTION),
            ),
        )
    ):
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": CONSTRUCT_TRAP_MECHANIC_TYPE,
            "placement": {
                "relation": "adjacent",
                "surfaceRequired": True,
            },
            "activation": {
                "trigger": "creature-moves-adjacent",
                "destroyTrap": True,
            },
            "save": {
                "type": "reflex",
                "dc": CONSTRUCT_TRAP_SAVE_DC,
                "basic": True,
            },
            "damage": {
                "components": [
                    {
                        "type": "piercing",
                        "dice": {"count": 1, "sides": 6},
                    },
                    {
                        "type": "bleed",
                        "persistent": True,
                        "value": 1,
                    },
                ],
            },
            "expiration": {
                "value": 1,
                "unit": "hour",
                "destroyTrap": True,
            },
            "rawMaterialUses": CONSTRUCT_TRAP_INITIAL_MATERIAL_USES,
        },
        rule=RuleReference(KOBOLD_SOURCE_ID, KOBOLD_SCOUT_LOCATOR),
    )


def _scamper_mechanic() -> dict[str, Any]:
    return {
        "type": SCAMPER_MECHANIC_TYPE,
        "requirements": {
            "enemyAdjacentAtStart": True,
        },
        "movement": {
            "type": "stride",
            "speedBonusFeet": SCAMPER_SPEED_BONUS_FEET,
        },
        "reactionDefense": {
            "armorClassBonus": {
                "type": "circumstance",
                "value": SCAMPER_REACTION_AC_BONUS,
            },
            "scope": "reactions-triggered-by-this-movement",
        },
        "endRequirement": {
            "enemyAdjacent": False,
        },
        "definitionSource": {
            "sourceId": KOBOLD_SOURCE_ID,
            "locator": KOBOLD_WARRIOR_LOCATOR,
        },
    }


def compile_kobold_scamper(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the Warrior definition or the Scout's exact inheritance."""

    is_warrior = _common_source_match(
        source,
        source_label="Scamper",
        locator=KOBOLD_WARRIOR_LOCATOR,
        creature_name="Kobold Warrior",
        action_cost=SCAMPER_ACTION_COST,
    )
    if is_warrior:
        if (
            source.traits
            or source.description
            or not _exact_object(
                source.raw_member.value,
                (
                    ("Action", "single"),
                    ("Requirements", _SCAMPER_REQUIREMENTS),
                    ("Effect", _SCAMPER_EFFECT),
                ),
            )
        ):
            return None
    else:
        is_scout = _common_source_match(
            source,
            source_label="Scamper",
            locator=KOBOLD_SCOUT_LOCATOR,
            creature_name="Kobold Scout",
            action_cost=SCAMPER_ACTION_COST,
        )
        if (
            not is_scout
            or source.traits
            or source.description != _SCOUT_SCAMPER_REFERENCE
            or not _exact_object(
                source.raw_member.value,
                (
                    ("Action", "single"),
                    ("Description", _SCOUT_SCAMPER_REFERENCE),
                ),
            )
        ):
            return None

    return AbilityCompilerPatch(
        mechanic=_scamper_mechanic(),
        rule=RuleReference(KOBOLD_SOURCE_ID, KOBOLD_WARRIOR_LOCATOR),
    )


def _coordinate(value: SerializedSquare, label: str) -> _Coordinate:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"x", "y"}
        or type(value.get("x")) is not int
        or type(value.get("y")) is not int
        or value["x"] < 0
        or value["y"] < 0
    ):
        raise ValueError(f"{label} must be one nonnegative x/y square")
    return value["x"], value["y"]


def _coordinates(
    values: Sequence[SerializedSquare],
    label: str,
    *,
    require_nonempty: bool,
) -> frozenset[_Coordinate]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{label} must be an explicit ordered sequence")
    result = frozenset(
        _coordinate(value, f"{label}[{index}]")
        for index, value in enumerate(values)
    )
    if require_nonempty and not result:
        raise ValueError(f"{label} must not be empty")
    return result


def _adjacent(left: _Coordinate, right: _Coordinate) -> bool:
    return left != right and max(
        abs(left[0] - right[0]),
        abs(left[1] - right[1]),
    ) == 1


def legal_construct_trap_squares(
    actor_squares: Sequence[SerializedSquare],
    surface_squares: Sequence[SerializedSquare],
    /,
) -> tuple[dict[str, int], ...]:
    """Return only explicitly supplied surfaces adjacent to the actor.

    ``surface_squares`` is deliberately a required input.  The helper does
    not infer that an in-bounds, unoccupied, blocked, or opaque square is a
    floor, wall, or ceiling.
    """

    actor = _coordinates(
        actor_squares,
        "actor_squares",
        require_nonempty=True,
    )
    surfaces = _coordinates(
        surface_squares,
        "surface_squares",
        require_nonempty=False,
    )
    legal = sorted(
        (
            square
            for square in surfaces
            if square not in actor
            and any(_adjacent(square, occupied) for occupied in actor)
        ),
        key=lambda square: (square[1], square[0]),
    )
    return tuple({"x": x, "y": y} for x, y in legal)


def construct_trap_triggered_by_move(
    trap_square: SerializedSquare,
    before_squares: Sequence[SerializedSquare],
    after_squares: Sequence[SerializedSquare],
    /,
) -> bool:
    """Return whether one move newly brought a creature adjacent to a trap."""

    trap = _coordinate(trap_square, "trap_square")
    before = _coordinates(
        before_squares,
        "before_squares",
        require_nonempty=True,
    )
    after = _coordinates(
        after_squares,
        "after_squares",
        require_nonempty=True,
    )
    was_adjacent = any(_adjacent(trap, square) for square in before)
    is_adjacent = any(_adjacent(trap, square) for square in after)
    return not was_adjacent and is_adjacent


def construct_trap_damage(
    save_degree: str,
    piercing_roll: int,
    /,
) -> dict[str, int]:
    """Scale both trap components through its basic Reflex save."""

    if save_degree not in {
        "critical-success",
        "success",
        "failure",
        "critical-failure",
    }:
        raise ValueError("save_degree must be one basic-save degree")
    if type(piercing_roll) is not int or not 1 <= piercing_roll <= 6:
        raise ValueError("piercing_roll must be one d6 result")

    if save_degree == "critical-success":
        numerator, denominator = 0, 1
    elif save_degree == "success":
        numerator, denominator = 1, 2
    elif save_degree == "failure":
        numerator, denominator = 1, 1
    else:
        numerator, denominator = 2, 1

    def scale(value: int, *, minimum_one: bool) -> int:
        if numerator == 0:
            return 0
        result = value * numerator // denominator
        return max(1, result) if minimum_one else result

    return {
        "piercing": scale(piercing_roll, minimum_one=True),
        # An integer-valued persistent component can be reduced to 0; unlike
        # a resolved damage roll it does not invoke the minimum-1 safeguard.
        "persistentBleed": scale(1, minimum_one=False),
    }


def scamper_start_requirement_met(
    actor_squares: Sequence[SerializedSquare],
    enemy_squares: Sequence[SerializedSquare],
    /,
) -> bool:
    """Evaluate only Scamper's source-authored starting adjacency."""

    actor = _coordinates(
        actor_squares,
        "actor_squares",
        require_nonempty=True,
    )
    enemies = _coordinates(
        enemy_squares,
        "enemy_squares",
        require_nonempty=False,
    )
    return any(
        _adjacent(actor_square, enemy_square)
        for actor_square in actor
        for enemy_square in enemies
    )


def scamper_end_requirement_met(
    actor_endpoint_squares: Sequence[SerializedSquare],
    enemy_squares: Sequence[SerializedSquare],
    /,
) -> bool:
    """Evaluate only Scamper's source-authored endpoint restriction."""

    return not scamper_start_requirement_met(
        actor_endpoint_squares,
        enemy_squares,
    )


def scamper_movement_limit_feet(speed_feet: int, /) -> int:
    """Return the source-authored Speed-plus-5-foot movement limit."""

    if (
        type(speed_feet) is not int
        or speed_feet <= 0
        or speed_feet % 5
    ):
        raise ValueError("speed_feet must be a positive multiple of 5")
    return speed_feet + SCAMPER_SPEED_BONUS_FEET


def scamper_reaction_armor_class_bonus(
    triggered_by_this_movement: bool,
    /,
) -> int:
    """Scope Scamper's circumstance bonus to its own movement reactions."""

    if type(triggered_by_this_movement) is not bool:
        raise TypeError("triggered_by_this_movement must be boolean")
    return (
        SCAMPER_REACTION_AC_BONUS
        if triggered_by_this_movement
        else 0
    )


CONSTRUCT_TRAP_FRAGMENT = MechanicFamilyFragment(
    family_id="kobold-construct-trap",
    mechanic_types=(CONSTRUCT_TRAP_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="kobold-construct-trap",
            mechanic_type=CONSTRUCT_TRAP_MECHANIC_TYPE,
            compiler=compile_construct_trap,
        ),
    ),
)

SCAMPER_FRAGMENT = MechanicFamilyFragment(
    family_id="kobold-scamper",
    mechanic_types=(SCAMPER_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="kobold-scamper",
            mechanic_type=SCAMPER_MECHANIC_TYPE,
            compiler=compile_kobold_scamper,
        ),
    ),
)

FRAGMENT = MechanicFamilyFragment(
    family_id="kobold-tactics",
    mechanic_types=(
        CONSTRUCT_TRAP_MECHANIC_TYPE,
        SCAMPER_MECHANIC_TYPE,
    ),
    ability_compilers=(
        *CONSTRUCT_TRAP_FRAGMENT.ability_compilers,
        *SCAMPER_FRAGMENT.ability_compilers,
    ),
)


__all__ = [
    "CONSTRUCT_TRAP_INITIAL_MATERIAL_USES",
    "CONSTRUCT_TRAP_FRAGMENT",
    "CONSTRUCT_TRAP_MECHANIC_TYPE",
    "FRAGMENT",
    "SCAMPER_FRAGMENT",
    "SCAMPER_MECHANIC_TYPE",
    "compile_construct_trap",
    "compile_kobold_scamper",
    "construct_trap_damage",
    "construct_trap_triggered_by_move",
    "legal_construct_trap_squares",
    "scamper_end_requirement_met",
    "scamper_movement_limit_feet",
    "scamper_reaction_armor_class_bonus",
    "scamper_start_requirement_met",
]

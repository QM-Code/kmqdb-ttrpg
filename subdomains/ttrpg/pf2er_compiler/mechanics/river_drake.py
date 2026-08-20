"""Compile and support the reviewed River Drake action abilities.

The three compilers in this module intentionally accept only the exact
``core-mc1:129.1`` River Drake productions.  Their mechanic projections retain
the complete source contract while the small pure helpers own only behavior
that does not require encounter-state, map-geometry, or damage-engine access.

Central encounter integration remains responsible for selecting a legal burst
origin and targets, applying basic-save damage and persistent-damage effects,
resolving subordinate Strikes and movement, and storing the resulting
cooldown and daily-use counters.
"""

from __future__ import annotations

from dataclasses import dataclass
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


RIVER_DRAKE_SOURCE_ID = "core-mc1"
RIVER_DRAKE_LOCATOR = "129.1"
RIVER_DRAKE_NAME = "River Drake"

CAUSTIC_MUCUS_MECHANIC_TYPE = "caustic-mucus"
DRACONIC_FRENZY_MECHANIC_TYPE = "draconic-frenzy"
SPEED_SURGE_MECHANIC_TYPE = "speed-surge"

CAUSTIC_MUCUS_DESCRIPTION = (
    "The river drake spits a ball of caustic mucus up to a range of 50 "
    "feet that explodes in a 10-foot burst. Creatures within the burst "
    "take 4d6 acid damage (DC 19 basic Reflex save). Those that fail this "
    "save also take 1d6 persistent acid damage and take a -5-foot status "
    "penalty to their Speed. This Speed reduction ends with the persistent "
    "acid damage. The river drake can't use Caustic Mucus again for 1d6 "
    "rounds."
)
DRACONIC_FRENZY_DESCRIPTION = (
    "The river drake makes one fangs Strike and two tail Strikes in any "
    "order."
)
SPEED_SURGE_DESCRIPTION = (
    "Frequency three times per day; Effect The river drake Strides or "
    "Flies twice."
)

CAUSTIC_MUCUS_MAXIMUM_RECHARGE_ROUNDS = 6
SPEED_SURGE_DAILY_USES = 3
_FRENZY_STRIKE_MULTISET = {"fangs": 1, "tail": 2}
_SPEED_SURGE_MOVEMENT_MODES = frozenset(("stride", "fly"))


class RiverDrakeRuntimeError(ValueError):
    """A pure River Drake runtime contract received an invalid value."""


def _raw_ability_matches(
    source: AbilitySource,
    *,
    label: str,
    fields: tuple[tuple[str, object], ...],
) -> bool:
    raw_member = source.raw_member
    if (
        type(raw_member) is not RawSourceMember
        or raw_member.key != f"!.{label}"
        or type(raw_member.value) is not RawSourceObject
        or len(raw_member.value.members) != len(fields)
    ):
        return False
    for member, (expected_key, expected_value) in zip(
        raw_member.value.members,
        fields,
        strict=True,
    ):
        if type(member) is not RawSourceMember or member.key != expected_key:
            return False
        if type(expected_value) is tuple:
            if (
                type(member.value) is not RawSourceArray
                or member.value.items != expected_value
            ):
                return False
        elif member.value != expected_value:
            return False
    return True


def _river_drake_source_matches(
    source: AbilitySource,
    *,
    label: str,
    action_cost: int,
    traits: tuple[str, ...],
    description: str,
    raw_fields: tuple[tuple[str, object], ...],
) -> bool:
    return (
        type(source) is AbilitySource
        and source.source_id == RIVER_DRAKE_SOURCE_ID
        and source.locator == RIVER_DRAKE_LOCATOR
        and source.creature_name == RIVER_DRAKE_NAME
        and source.source_label == label
        and source.action_cost == action_cost
        and source.kind == "activity"
        and source.traits == traits
        and source.trigger == ""
        and source.description == description
        and _raw_ability_matches(
            source,
            label=label,
            fields=raw_fields,
        )
    )


def compile_caustic_mucus(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the exact River Drake Caustic Mucus production."""

    if not _river_drake_source_matches(
        source,
        label="Caustic Mucus",
        action_cost=2,
        traits=("acid", "primal"),
        description=CAUSTIC_MUCUS_DESCRIPTION,
        raw_fields=(
            ("Action", "two"),
            ("Traits", ("acid", "primal")),
            ("Description", CAUSTIC_MUCUS_DESCRIPTION),
        ),
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": CAUSTIC_MUCUS_MECHANIC_TYPE,
            "rangeFeet": 50,
            "area": {
                "type": "burst",
                "radiusFeet": 10,
            },
            "targetSelection": "all-creatures-in-area",
            "savingThrow": {
                "type": "reflex",
                "dc": 19,
                "basic": True,
            },
            "damage": {
                "dice": {
                    "count": 4,
                    "sides": 6,
                },
                "modifier": 0,
                "type": "acid",
            },
            "failureRider": {
                "degrees": [
                    "failure",
                    "critical-failure",
                ],
                "persistentDamage": {
                    "dice": {
                        "count": 1,
                        "sides": 6,
                    },
                    "modifier": 0,
                    "type": "acid",
                },
                "speedPenalty": {
                    "type": "status",
                    "stat": "Speed",
                    "valueFeet": -5,
                    "lifecycle": "while-persistent-damage-active",
                },
            },
            "recharge": {
                "unavailableFor": {
                    "roll": {
                        "count": 1,
                        "sides": 6,
                    },
                    "unit": "rounds",
                },
                "decrementAt": "owner-start-turn",
                "readyAt": 0,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_draconic_frenzy(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the exact River Drake Draconic Frenzy production."""

    if not _river_drake_source_matches(
        source,
        label="Draconic Frenzy",
        action_cost=2,
        traits=(),
        description=DRACONIC_FRENZY_DESCRIPTION,
        raw_fields=(
            ("Action", "two"),
            ("Description", DRACONIC_FRENZY_DESCRIPTION),
        ),
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": DRACONIC_FRENZY_MECHANIC_TYPE,
            "strikeMultiset": [
                {
                    "strikeId": "fangs",
                    "count": 1,
                },
                {
                    "strikeId": "tail",
                    "count": 2,
                },
            ],
            "order": "any",
            "targetSelection": "before-each-strike",
            "sameTargetRequired": False,
            "multipleAttackPenalty": {
                "carryInCurrentTurnCount": True,
                "advanceAfterEveryAttempt": True,
                "useCurrentStrikeTraits": True,
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_speed_surge(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the exact River Drake Speed Surge production."""

    if not _river_drake_source_matches(
        source,
        label="Speed Surge",
        action_cost=1,
        traits=("move",),
        description=SPEED_SURGE_DESCRIPTION,
        raw_fields=(
            ("Action", "single"),
            ("Traits", ("move",)),
            ("Description", SPEED_SURGE_DESCRIPTION),
        ),
    ):
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": SPEED_SURGE_MECHANIC_TYPE,
            "frequency": {
                "uses": SPEED_SURGE_DAILY_USES,
                "period": "day",
            },
            "movements": {
                "count": 2,
                "allowedActions": [
                    "Stride",
                    "Fly",
                ],
                "selection": "for-each-movement",
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def _bounded_integer(
    value: object,
    *,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise RiverDrakeRuntimeError(
            f"{label} must be an integer from {minimum} to {maximum}"
        )
    return value


def start_caustic_mucus_recharge(d6_roll: object, /) -> int:
    """Return the exact number of rounds for which Mucus is unavailable."""

    return _bounded_integer(
        d6_roll,
        label="Caustic Mucus recharge roll",
        minimum=1,
        maximum=CAUSTIC_MUCUS_MAXIMUM_RECHARGE_ROUNDS,
    )


def advance_caustic_mucus_recharge(
    rounds_remaining: object,
    /,
) -> int:
    """Advance one owner-start-turn cooldown tick, clamped at ready."""

    remaining = _bounded_integer(
        rounds_remaining,
        label="Caustic Mucus recharge rounds",
        minimum=0,
        maximum=CAUSTIC_MUCUS_MAXIMUM_RECHARGE_ROUNDS,
    )
    return max(0, remaining - 1)


def caustic_mucus_is_ready(rounds_remaining: object, /) -> bool:
    """Return whether a validated cooldown counter permits another use."""

    remaining = _bounded_integer(
        rounds_remaining,
        label="Caustic Mucus recharge rounds",
        minimum=0,
        maximum=CAUSTIC_MUCUS_MAXIMUM_RECHARGE_ROUNDS,
    )
    return remaining == 0


@dataclass(frozen=True, slots=True)
class CausticMucusFailureRider:
    """One failed-save persistent-acid contribution and its linked penalty."""

    persistent_acid_damage: int

    def __post_init__(self) -> None:
        _bounded_integer(
            self.persistent_acid_damage,
            label="Caustic Mucus persistent acid damage roll",
            minimum=1,
            maximum=6,
        )

    def as_serialized(self) -> dict[str, Any]:
        return {
            "persistentDamage": {
                "amount": self.persistent_acid_damage,
                "type": "acid",
            },
            "linkedEffect": {
                "type": "status-penalty",
                "stat": "Speed",
                "valueFeet": -5,
                "lifecycle": "while-persistent-damage-active",
            },
        }


def caustic_mucus_failure_rider(
    persistent_damage_roll: object,
    /,
) -> CausticMucusFailureRider:
    """Build the exact rider applied on failure or critical failure."""

    damage = _bounded_integer(
        persistent_damage_roll,
        label="Caustic Mucus persistent acid damage roll",
        minimum=1,
        maximum=6,
    )
    return CausticMucusFailureRider(damage)


@dataclass(frozen=True, slots=True)
class DraconicFrenzyStep:
    """One subordinate Strike with its shared-turn attack number."""

    strike_id: str
    attack_number: int

    def __post_init__(self) -> None:
        if self.strike_id not in _FRENZY_STRIKE_MULTISET:
            raise RiverDrakeRuntimeError(
                "Draconic Frenzy strike must be fangs or tail"
            )
        if type(self.attack_number) is not int or self.attack_number < 1:
            raise RiverDrakeRuntimeError(
                "Draconic Frenzy attack number must be a positive integer"
            )

    def as_serialized(self) -> dict[str, Any]:
        return {
            "strikeId": self.strike_id,
            "attackNumber": self.attack_number,
        }


def plan_draconic_frenzy(
    strike_ids: object,
    attacks_this_turn: object,
    /,
) -> tuple[DraconicFrenzyStep, ...]:
    """Validate one allowed ordering and carry MAP across all three attacks."""

    if type(strike_ids) not in (list, tuple) or len(strike_ids) != 3:
        raise RiverDrakeRuntimeError(
            "Draconic Frenzy requires exactly three ordered strike ids"
        )
    if any(type(strike_id) is not str for strike_id in strike_ids):
        raise RiverDrakeRuntimeError(
            "Draconic Frenzy strike ids must be exact strings"
        )
    counts = {
        strike_id: strike_ids.count(strike_id)
        for strike_id in set(strike_ids)
    }
    if counts != _FRENZY_STRIKE_MULTISET:
        raise RiverDrakeRuntimeError(
            "Draconic Frenzy requires one fangs and two tail Strikes"
        )
    prior_attacks = _bounded_integer(
        attacks_this_turn,
        label="attacks this turn",
        minimum=0,
        maximum=1_000_000,
    )
    return tuple(
        DraconicFrenzyStep(
            strike_id=strike_id,
            attack_number=prior_attacks + ordinal + 1,
        )
        for ordinal, strike_id in enumerate(strike_ids)
    )


def speed_surge_movement_sequence(
    movement_modes: object,
    /,
) -> tuple[str, str]:
    """Validate the two independently selected Speed Surge move actions."""

    if (
        type(movement_modes) not in (list, tuple)
        or len(movement_modes) != 2
        or any(type(mode) is not str for mode in movement_modes)
    ):
        raise RiverDrakeRuntimeError(
            "Speed Surge requires exactly two movement modes"
        )
    normalized = tuple(mode.casefold() for mode in movement_modes)
    if any(mode not in _SPEED_SURGE_MOVEMENT_MODES for mode in normalized):
        raise RiverDrakeRuntimeError(
            "Speed Surge movement modes must be Stride or Fly"
        )
    return normalized


def spend_speed_surge_use(uses_remaining: object, /) -> int:
    """Spend one of the River Drake's three daily Speed Surge uses."""

    remaining = _bounded_integer(
        uses_remaining,
        label="Speed Surge uses remaining",
        minimum=0,
        maximum=SPEED_SURGE_DAILY_USES,
    )
    if remaining == 0:
        raise RiverDrakeRuntimeError(
            "Speed Surge has no daily uses remaining"
        )
    return remaining - 1


CAUSTIC_MUCUS_FRAGMENT = MechanicFamilyFragment(
    family_id="river-drake-caustic-mucus",
    mechanic_types=(CAUSTIC_MUCUS_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="caustic-mucus",
            mechanic_type=CAUSTIC_MUCUS_MECHANIC_TYPE,
            compiler=compile_caustic_mucus,
        ),
    ),
)

DRACONIC_FRENZY_FRAGMENT = MechanicFamilyFragment(
    family_id="river-drake-draconic-frenzy",
    mechanic_types=(DRACONIC_FRENZY_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="river-drake-draconic-frenzy",
            mechanic_type=DRACONIC_FRENZY_MECHANIC_TYPE,
            compiler=compile_draconic_frenzy,
        ),
    ),
)

SPEED_SURGE_FRAGMENT = MechanicFamilyFragment(
    family_id="river-drake-speed-surge",
    mechanic_types=(SPEED_SURGE_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="speed-surge",
            mechanic_type=SPEED_SURGE_MECHANIC_TYPE,
            compiler=compile_speed_surge,
        ),
    ),
)

FRAGMENT = MechanicFamilyFragment(
    family_id="river-drake",
    mechanic_types=(
        CAUSTIC_MUCUS_MECHANIC_TYPE,
        DRACONIC_FRENZY_MECHANIC_TYPE,
        SPEED_SURGE_MECHANIC_TYPE,
    ),
    ability_compilers=(
        *CAUSTIC_MUCUS_FRAGMENT.ability_compilers,
        *DRACONIC_FRENZY_FRAGMENT.ability_compilers,
        *SPEED_SURGE_FRAGMENT.ability_compilers,
    ),
)


__all__ = [
    "CAUSTIC_MUCUS_FRAGMENT",
    "CAUSTIC_MUCUS_MECHANIC_TYPE",
    "DRACONIC_FRENZY_FRAGMENT",
    "DRACONIC_FRENZY_MECHANIC_TYPE",
    "FRAGMENT",
    "SPEED_SURGE_FRAGMENT",
    "SPEED_SURGE_MECHANIC_TYPE",
    "CausticMucusFailureRider",
    "DraconicFrenzyStep",
    "RiverDrakeRuntimeError",
    "advance_caustic_mucus_recharge",
    "caustic_mucus_failure_rider",
    "caustic_mucus_is_ready",
    "compile_caustic_mucus",
    "compile_draconic_frenzy",
    "compile_speed_surge",
    "plan_draconic_frenzy",
    "spend_speed_surge_use",
    "speed_surge_movement_sequence",
    "start_caustic_mucus_recharge",
]

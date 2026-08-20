"""PF2ER authority bindings and explicit global mechanic composition."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from . import conditional_damage as _conditional_damage
from . import ferocity as _ferocity
from . import stride_strike as _stride_strike
from . import gaze as _gaze
from . import scuttle as _scuttle
from . import grapples as _grapples
from . import reactive_strike as _reactive_strike
from . import conditions as _conditions
from . import afflictions as _afflictions
from . import battle_cry as _battle_cry
from . import fungus_leshy as _fungus_leshy
from . import goblin_song as _goblin_song
from . import grabbed_strike_activities as _grabbed_strike_activities
from . import kobold_tactics as _kobold_tactics
from . import river_drake as _river_drake
from . import triggered_creature_reactions as _triggered_creature_reactions
from . import cats_luck as _cats_luck
from . import amoeba_abilities as _amoeba_abilities
from . import shield_block as _shield_block
from . import animated_construct_armor as _animated_construct_armor
from . import gnome_bard as _gnome_bard
from . import warg as _warg
from . import giant_ant as _giant_ant
from . import flash_beetle as _flash_beetle
from . import scarecrow as _scarecrow
from . import stench as _stench
from . import ghoul as _ghoul
from . import plague_zombie_abilities as _plague_zombie_abilities
from . import strike_save_control as _strike_save_control
from . import zombie_rot as _zombie_rot
from .contracts import AbilityCompilerPatch
from .runtime_registry import (
    MechanicRegistry,
    RegistryConfigurationError,
    build_registry,
)


CREATURE_AUTHORITY_REQUIREMENTS = MappingProxyType(
    {
        ("core-mc1", "18.5"): frozenset(("core-pc1",)),
        ("core-mc1", "21.3"): frozenset(("core-pc1",)),
        ("core-mc1", "42.4"): frozenset(("core-pc1",)),
        ("core-mc1", "163.1"): frozenset(("core-gmc", "core-pc1")),
        ("core-mc1", "163.3"): frozenset(("core-gmc", "core-pc1")),
        ("core-mc1", "216.4"): frozenset(("core-pc1",)),
        ("core-mc1", "217.2"): frozenset(("core-pc1",)),
        ("core-mc1", "259.3"): frozenset(("core-pc1",)),
        ("core-mc1", "297.1"): frozenset(("core-pc1",)),
        ("core-mc1", "313.1"): frozenset(("core-pc1",)),
        ("core-mc1", "341.2"): frozenset(("core-pc1",)),
        ("core-mc1", "352.3"): frozenset(("core-pc1",)),
        ("core-mc1", "356.6"): frozenset(("core-pc1",)),
        ("core-mc1", "357.2"): frozenset(("core-gmc", "core-pc1")),
    }
)
CREATURE_RULE_AUTHORITY_LOCATORS = MappingProxyType(
    {
        ("core-mc1", "21.3"): (
            ("core-pc1", "414.4"),
            ("core-pc1", "418.3"),
            ("core-pc1", "420.3"),
            ("core-pc1", "430.1"),
            ("core-pc1", "430.8"),
            ("core-pc1", "430.9"),
            ("core-pc1", "443.7"),
            ("core-pc1", "444.5"),
            ("core-pc1", "446.3"),
        ),
        ("core-mc1", "42.4"): (
            ("core-pc1", "404.1"),
            ("core-pc1", "426.2"),
            ("core-pc1", "428.4"),
            ("core-pc1", "432.2"),
            ("core-pc1", "432.3"),
            ("core-pc1", "434.6"),
            ("core-pc1", "442.12"),
            ("core-pc1", "452.1"),
        ),
        ("core-mc1", "163.1"): (
            ("core-gmc", "116.2"),
            ("core-gmc", "121.2"),
            ("core-pc1", "404.1"),
            ("core-pc1", "405.2"),
            ("core-pc1", "410.2"),
            ("core-pc1", "411.5"),
            ("core-pc1", "415.2"),
            ("core-pc1", "417.1"),
            ("core-pc1", "418.3"),
            ("core-pc1", "420.1"),
            ("core-pc1", "420.3"),
            ("core-pc1", "421.6"),
            ("core-pc1", "426.2"),
            ("core-pc1", "428.4"),
            ("core-pc1", "430.1"),
            ("core-pc1", "430.8"),
            ("core-pc1", "435.8"),
            ("core-pc1", "436.5"),
            ("core-pc1", "444.5"),
            ("core-pc1", "445.3"),
            ("core-pc1", "446.3"),
            ("core-pc1", "446.4"),
            ("core-pc1", "446.5"),
            ("core-pc1", "446.8"),
            ("core-pc1", "452.1"),
        ),
        ("core-mc1", "163.3"): (
            ("core-gmc", "116.2"),
            ("core-gmc", "121.2"),
            ("core-pc1", "404.1"),
            ("core-pc1", "405.2"),
            ("core-pc1", "410.2"),
            ("core-pc1", "411.5"),
            ("core-pc1", "415.2"),
            ("core-pc1", "417.1"),
            ("core-pc1", "418.3"),
            ("core-pc1", "420.1"),
            ("core-pc1", "420.3"),
            ("core-pc1", "421.6"),
            ("core-pc1", "426.2"),
            ("core-pc1", "428.4"),
            ("core-pc1", "430.1"),
            ("core-pc1", "430.8"),
            ("core-pc1", "435.8"),
            ("core-pc1", "436.5"),
            ("core-pc1", "444.5"),
            ("core-pc1", "445.3"),
            ("core-pc1", "446.3"),
            ("core-pc1", "446.4"),
            ("core-pc1", "446.5"),
            ("core-pc1", "446.8"),
            ("core-pc1", "452.1"),
        ),
        ("core-mc1", "216.4"): (
            ("core-pc1", "399.1"),
            ("core-pc1", "401.4"),
            ("core-pc1", "404.1"),
            ("core-pc1", "406.1"),
            ("core-pc1", "407.3"),
            ("core-pc1", "407.4"),
            ("core-pc1", "420.3"),
            ("core-pc1", "420.4"),
            ("core-pc1", "426.2"),
            ("core-pc1", "444.9"),
        ),
        ("core-mc1", "217.2"): (
            ("core-pc1", "399.1"),
            ("core-pc1", "401.4"),
            ("core-pc1", "404.1"),
            ("core-pc1", "406.2"),
            ("core-pc1", "407.1"),
            ("core-pc1", "408.2"),
            ("core-pc1", "409.6"),
            ("core-pc1", "426.3"),
            ("core-pc1", "426.6"),
            ("core-pc1", "427.2"),
            ("core-pc1", "428.4"),
            ("core-pc1", "436.3"),
            ("core-pc1", "445.4"),
            ("core-pc1", "452.1"),
        ),
        ("core-mc1", "259.3"): (
            ("core-pc1", "399.1"),
            ("core-pc1", "400.2"),
            ("core-pc1", "426.2"),
            ("core-pc1", "426.3"),
            ("core-pc1", "426.6"),
            ("core-pc1", "452.1"),
        ),
        ("core-mc1", "297.1"): (
            ("core-pc1", "426.2"),
            ("core-pc1", "428.4"),
            ("core-pc1", "432.2"),
            ("core-pc1", "432.3"),
            ("core-pc1", "445.2"),
            ("core-pc1", "452.1"),
        ),
        ("core-mc1", "313.1"): (
            ("core-pc1", "414.4"),
            ("core-pc1", "418.3"),
            ("core-pc1", "420.3"),
        ),
        ("core-mc1", "352.3"): (
            ("core-pc1", "404.1"),
            ("core-pc1", "426.2"),
            ("core-pc1", "428.4"),
            ("core-pc1", "435.8"),
            ("core-pc1", "446.4"),
            ("core-pc1", "446.5"),
            ("core-pc1", "452.1"),
        ),
        ("core-mc1", "356.6"): (
            ("core-mc1", "358.2"),
            ("core-pc1", "402.1"),
            ("core-pc1", "411.5"),
            ("core-pc1", "414.4"),
            ("core-pc1", "418.4"),
            ("core-pc1", "430.1"),
            ("core-pc1", "430.4"),
            ("core-pc1", "430.7"),
            ("core-pc1", "430.8"),
            ("core-pc1", "430.9"),
            ("core-pc1", "444.5"),
            ("core-pc1", "446.3"),
            ("core-pc1", "446.5"),
        ),
        ("core-mc1", "357.2"): (
            ("core-mc1", "358.2"),
            ("core-pc1", "235.6"),
            ("core-pc1", "401.2"),
            ("core-pc1", "401.4"),
            ("core-pc1", "402.1"),
            ("core-pc1", "414.4"),
            ("core-pc1", "414.6"),
            ("core-pc1", "418.3"),
            ("core-pc1", "418.4"),
            ("core-pc1", "421.1"),
            ("core-pc1", "421.5"),
            ("core-pc1", "421.6"),
            ("core-pc1", "421.8"),
            ("core-pc1", "422.3"),
            ("core-pc1", "422.7"),
            ("core-pc1", "423.6"),
            ("core-pc1", "446.5"),
        ),
    }
)


def bind_ability_authority(
    patch: AbilityCompilerPatch,
    *,
    authority_mechanics: Mapping[str, Mapping],
    authority_compilations: Mapping[str, object],
) -> AbilityCompilerPatch | None:
    """Apply a family-owned authority binder after registry matching."""

    if not isinstance(patch, AbilityCompilerPatch):
        raise TypeError("authority binding requires an ability compiler patch")
    if patch.mechanic_type == _animated_construct_armor.MECHANIC_TYPE:
        mechanic = authority_mechanics.get(patch.mechanic_type)
        return (
            None
            if mechanic is None
            else _animated_construct_armor.bind_authority_mechanic(
                patch,
                mechanic,
            )
        )
    if patch.mechanic_type == _warg.SWALLOW_WHOLE_MECHANIC_TYPE:
        compilation = authority_compilations.get(patch.mechanic_type)
        return (
            None
            if compilation is None
            else _warg.bind_swallow_whole_compilation(
                patch,
                compilation,
            )
        )
    if patch.mechanic_type == _stench.STENCH_MECHANIC_TYPE:
        compilation = authority_compilations.get(patch.mechanic_type)
        return (
            None
            if compilation is None
            else _stench.bind_verified_compilation(
                patch,
                compilation,
            )
        )
    if patch.mechanic_type in {
        _ghoul.CONSUME_FLESH_MECHANIC_TYPE,
        _ghoul.GHOUL_WHISPERS_MECHANIC_TYPE,
        _ghoul.GRAVE_KNOWLEDGE_MECHANIC_TYPE,
        _ghoul.SWIFT_LEAP_MECHANIC_TYPE,
    }:
        mechanic = authority_mechanics.get(patch.mechanic_type)
        return (
            None
            if mechanic is None
            else _ghoul.bind_authority_mechanic(patch, mechanic)
        )
    return patch


FAMILY_FRAGMENTS = (
    _conditional_damage.FRAGMENT,
    _ferocity.FRAGMENT,
    _stride_strike.FRAGMENT,
    _gaze.FRAGMENT,
    _scuttle.FRAGMENT,
    _grapples.FRAGMENT,
    _reactive_strike.FRAGMENT,
    _conditions.FRAGMENT,
    _afflictions.FRAGMENT,
    _goblin_song.FRAGMENT,
    _battle_cry.FRAGMENT,
    _fungus_leshy.FRAGMENT,
    _river_drake.CAUSTIC_MUCUS_FRAGMENT,
    _river_drake.DRACONIC_FRENZY_FRAGMENT,
    _river_drake.SPEED_SURGE_FRAGMENT,
    _grabbed_strike_activities.FRAGMENT,
    _kobold_tactics.CONSTRUCT_TRAP_FRAGMENT,
    _triggered_creature_reactions.TAIL_LASH_FRAGMENT,
    _triggered_creature_reactions.BITING_SNAKES_FRAGMENT,
    _triggered_creature_reactions.GIANT_CRAB_SCUTTLE_FRAGMENT,
    _cats_luck.FRAGMENT,
    _amoeba_abilities.ENVELOP_FRAGMENT,
    _shield_block.FRAGMENT,
    _animated_construct_armor.FRAGMENT,
    _gnome_bard.FRAGMENT,
    _warg.FRAGMENT,
    _giant_ant.FRAGMENT,
    _flash_beetle.FRAGMENT,
    _scarecrow.FRAGMENT,
    _stench.FRAGMENT,
    _ghoul.FRAGMENT,
    _plague_zombie_abilities.FRAGMENT,
    _strike_save_control.FRAGMENT,
    _zombie_rot.FRAGMENT,
)
REGISTRY = build_registry(FAMILY_FRAGMENTS)

ABILITY_COMPILERS = REGISTRY.ability_compilers
ACTIVITY_HANDLERS = REGISTRY.activity_handlers
REACTION_HANDLERS = REGISTRY.reaction_handlers
REACTION_QUEUE_HANDLERS = REGISTRY.reaction_queue_handlers
POST_EVENT_HOOKS = REGISTRY.post_event_hooks
EVENT_RENDERERS = REGISTRY.event_renderers


__all__ = [
    "FAMILY_FRAGMENTS",
    "CREATURE_AUTHORITY_REQUIREMENTS",
    "CREATURE_RULE_AUTHORITY_LOCATORS",
    "REGISTRY",
    "ABILITY_COMPILERS",
    "ACTIVITY_HANDLERS",
    "REACTION_HANDLERS",
    "REACTION_QUEUE_HANDLERS",
    "POST_EVENT_HOOKS",
    "EVENT_RENDERERS",
    "MechanicRegistry",
    "RegistryConfigurationError",
    "bind_ability_authority",
    "build_registry",
]

"""Compose source-backed creature stat families behind one authority seam.

This module is an internal bridge between the exact Core MC1 source facade
and independently reviewed source-family compilers. Scalar base values,
mechanically complete Strike occurrences, and exact ability action envelopes
may be projected into the existing runtime definition only after their frozen
compiler has separated them from lossless source authority. Everything else
remains compile-only unless its validated plan explicitly declares a bounded
partial activation; all remaining mechanics carry explicit deferrals.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import re
from typing import Any, Callable

from . import errors as _errors
from .mechanics.annotated_stats import (
    CompiledAnnotatedStat as _CompiledAnnotatedStat,
    compile_annotated_stat as _compile_annotated_stat,
)
from .mechanics.damage_defenses import (
    compile_damage_defense_profile as _compile_damage_defense_profile,
    compiled_damage_defense_as_serialized as _serialize_damage_defenses,
)
from .mechanics.action_costs import (
    CompiledCreatureAbilityEnvelopes as _CompiledCreatureAbilityEnvelopes,
    compile_ability_envelopes as _compile_ability_envelopes,
)
from .mechanics.conditional_saves import (
    CompiledConditionalSave as _CompiledConditionalSave,
    compile_conditional_save as _compile_conditional_save,
    conditional_save_provider_requirements as _conditional_save_requirements,
)
from .mechanics.contracts import (
    RawSourceArray as _RawSourceArray,
    RawSourceObject as _RawSourceObject,
)
from .mechanics.damage_immunities import (
    DamageImmunityPatch as _DamageImmunityPatch,
    compile_damage_immunities as _compile_damage_immunities,
)
from .mechanics.movement_speeds import (
    MovementSpeedPatch as _MovementSpeedPatch,
    MovementSpeedSource as _MovementSpeedSource,
    bind_movement_speed_rules as _bind_movement_speed_rules,
    bind_reviewed_movement_inheritance_for_source as _bind_movement_inheritance,
    compile_movement_speeds as _compile_movement_speeds,
)
from .mechanics.size_space_reach import (
    CreatureGeometrySource as _CreatureGeometrySource,
    SizeSpaceReachPatch as _SizeSpaceReachPatch,
    bind_size_space_reach_rules as _bind_size_space_reach_rules,
    compile_size_space_reach as _compile_size_space_reach,
)
from .mechanics.source_authority import (
    RawMemberStep as _RawMemberStep,
    SourceAuthorityAdapter as _SourceAuthorityAdapter,
    SourceAuthorityError as _SourceAuthorityError,
    VerifiedSourceCarrier as _VerifiedSourceCarrier,
    VerifiedSourceSelection as _VerifiedSourceSelection,
)
from .mechanics.special_senses import (
    FRAGMENT as _SPECIAL_SENSE_FRAGMENT,
    SenseCompilerPatch as _SenseCompilerPatch,
    SenseCreatureCarrier as _SenseCreatureCarrier,
    SenseSource as _SenseSource,
    compile_sense_collection as _compile_sense_collection,
)
from .mechanics.spontaneous_spellcasting import (
    COMPILER_ID as _SPELLCASTING_COMPILER_ID,
    FAMILY_ID as _SPELLCASTING_FAMILY_ID,
    GNOME_BARD_LOCATOR as _GNOME_BARD_LOCATOR,
    GOBLIN_PYRO_LOCATOR as _GOBLIN_PYRO_LOCATOR,
    GOBLIN_WAR_CHANTER_LOCATOR as _GOBLIN_WAR_CHANTER_LOCATOR,
    KOBOLD_CAVERN_MAGE_LOCATOR as _KOBOLD_CAVERN_MAGE_LOCATOR,
    CompiledSpontaneousSpellcasting as _CompiledSpontaneousSpellcasting,
    compile_spontaneous_spellcasting as _compile_spontaneous_spellcasting,
)
from .mechanics.prepared_spellcasting import (
    AIUVARIN_ELEMENTALIST_LOCATOR as _AIUVARIN_ELEMENTALIST_LOCATOR,
    COMPILER_ID as _PREPARED_SPELLCASTING_COMPILER_ID,
    FAMILY_ID as _PREPARED_SPELLCASTING_FAMILY_ID,
    LIZARDFOLK_STARGAZER_LOCATOR as _LIZARDFOLK_STARGAZER_LOCATOR,
    CompiledPreparedSpellcasting as _CompiledPreparedSpellcasting,
    compile_prepared_spellcasting as _compile_prepared_spellcasting,
)
from .mechanics.heal_spell import (
    HEAL_EFFECT_DEFINITION as _HEAL_EFFECT_DEFINITION,
)
from .mechanics.runic_weapon import (
    EFFECT_DEFINITION as _RUNIC_WEAPON_EFFECT_DEFINITION,
)
from .mechanics.strike_sources import (
    compile_strike_block as _compile_strike_block,
    project_strike_bundle as _project_strike_bundle,
    serialize_strike_integration_projection as _serialize_strike_projection,
)
from .mechanics.vision_senses import (
    RULE_REQUIREMENTS as _VISION_RULE_REQUIREMENTS,
    compile_and_link_vision_sense as _compile_and_link_vision_sense,
)


_REQUIRED_SOURCE_SCOPE = frozenset(
    ("core-gmc", "core-mc1", "core-pc1")
)
_CREATURE_SOURCE_IDS = frozenset(("core-mc1", "core-mc2"))
_CONDITIONAL_SAVE_FIELDS = ("Fort", "Will")
_ANNOTATED_STAT_FIELDS = ("HP", "AC")
_DAMAGE_DEFENSE_FIELDS = ("Weaknesses", "Resistances")
_SPECIAL_SENSE_MARKERS = ("scent", "tremorsense", "lifesense")
_MOVEMENT_MODES = ("land", "burrow", "climb", "fly", "swim")
_SPELLCASTING_FIELD = "Spellcasting"
_SPELLCASTING_PROVIDERS = (
    ("breathe-fire", "319.2"),
    ("grease", "333.8"),
    ("ignition", "336.5"),
    ("light", "340.8"),
    ("tangle-vine", "362.4"),
    ("telekinetic-hand", "362.6"),
    ("bless", "318.3"),
    ("soothe", "357.6"),
    ("figment", "331.6"),
    ("courageous-anthem", "370.5"),
    ("message", "343.2"),
    ("telekinetic-projectile", "363.2"),
    ("fleet-step", "332.1"),
    ("heal", "335.2"),
    ("pummeling-rubble", "351.4"),
    ("runic-weapon", "354.3"),
    ("charm", "320.1"),
    ("command", "321.1"),
    ("daze", "322.7"),
    ("prestidigitation", "351.1"),
    ("summon-instrument", "361.3"),
    ("runic-body", "354.2"),
    ("pest-form", "348.5"),
    ("summon-animal", "360.3"),
    ("guidance", "334.2"),
    ("stabilize", "359.3"),
    ("caustic-blast", "319.6"),
    ("detect-magic", "323.2"),
    ("know-the-way", "340.5"),
    ("gentle-landing", "333.3"),
    ("gust-of-wind", "334.3"),
    ("illusory-disguise", "337.1"),
    ("thunderstrike", "363.5"),
    ("electric-arc", "328.2"),
    ("shield", "356.7"),
)
_SPELLCASTING_PROVIDER_BY_ID = dict(_SPELLCASTING_PROVIDERS)
_SPELLCASTING_PROVIDER_TRADITIONS = {
    "breathe-fire": ["arcane", "primal"],
    "grease": ["arcane", "primal"],
    "ignition": ["arcane", "primal"],
    "light": ["arcane", "divine", "occult", "primal"],
    "tangle-vine": ["arcane", "primal"],
    "telekinetic-hand": ["arcane", "occult"],
    "bless": ["divine", "occult"],
    "soothe": ["occult"],
    "figment": ["arcane", "occult"],
    "courageous-anthem": [],
    "message": ["arcane", "divine", "occult"],
    "telekinetic-projectile": ["arcane", "occult"],
    "fleet-step": ["arcane", "primal"],
    "heal": ["divine", "primal"],
    "pummeling-rubble": ["arcane", "primal"],
    "runic-weapon": ["arcane", "divine", "occult", "primal"],
    "caustic-blast": ["arcane", "primal"],
    "detect-magic": ["arcane", "divine", "occult", "primal"],
    "know-the-way": ["divine", "occult", "primal"],
    "charm": ["arcane", "occult", "primal"],
    "command": ["arcane", "divine", "occult"],
    "daze": ["arcane", "divine", "occult"],
    "prestidigitation": ["arcane", "divine", "occult", "primal"],
    "summon-instrument": ["arcane", "divine", "occult"],
    "runic-body": ["arcane", "divine", "occult", "primal"],
    "pest-form": ["arcane", "primal"],
    "summon-animal": ["arcane", "primal"],
    "guidance": ["divine", "occult", "primal"],
    "stabilize": ["divine", "primal"],
    "gentle-landing": ["arcane", "primal"],
    "gust-of-wind": ["arcane", "primal"],
    "illusory-disguise": ["arcane", "occult"],
    "thunderstrike": ["arcane", "primal"],
    "electric-arc": ["arcane", "primal"],
    "shield": ["arcane", "divine", "occult"],
}
_PREPARED_SPELLCASTING_CREATURE_LOCATORS = frozenset(
    (
        _LIZARDFOLK_STARGAZER_LOCATOR,
        _AIUVARIN_ELEMENTALIST_LOCATOR,
    )
)
_SPELLCASTING_CREATURE_LOCATORS = frozenset(
    (
        _GOBLIN_PYRO_LOCATOR,
        _GOBLIN_WAR_CHANTER_LOCATOR,
        _GNOME_BARD_LOCATOR,
        _KOBOLD_CAVERN_MAGE_LOCATOR,
        *_PREPARED_SPELLCASTING_CREATURE_LOCATORS,
    )
)
_SPELLCASTING_GOVERNING_RULES = (
    ("spell-slots", "297.3"),
    ("spontaneous-spells", "297.5"),
    ("cantrips", "298.1"),
    ("casting-spells", "299.2"),
    ("areas", "300.7"),
    ("basic-saving-throws", "302.8"),
)
_PREPARED_SPELLCASTING_GOVERNING_RULES = (
    ("spell-slots", "297.3"),
    ("prepared-spells", "297.4"),
    ("cantrips", "298.1"),
    ("casting-spells", "299.2"),
    ("areas", "300.7"),
    ("basic-saving-throws", "302.8"),
    ("duration", "426.2"),
)
_SPELLCASTING_DERIVED_ATTACK_RULE = ("dc-from-modifier", "401.2")
_SPELLCASTING_MOVEMENT_RULES = (
    ("movement-types", "420.3"),
    ("land-speed", "420.4"),
)
_SPELLCASTING_ATTACK_EVIDENCE = {
    _GOBLIN_PYRO_LOCATOR: {
        "mode": "authored",
        "authoredMemberPresent": True,
        "value": 6,
    },
    _GOBLIN_WAR_CHANTER_LOCATOR: {
        "mode": "authored",
        "authoredMemberPresent": True,
        "value": 7,
    },
    _GNOME_BARD_LOCATOR: {
        "mode": "authored",
        "authoredMemberPresent": True,
        "value": 11,
    },
    _KOBOLD_CAVERN_MAGE_LOCATOR: {
        "mode": "derived",
        "authoredMemberPresent": False,
        "inputDc": 18,
        "formula": "DC - 10",
        "value": 8,
        "rule": {
            "id": "dc-from-modifier",
            "provider": {
                "sourceId": "core-pc1",
                "locator": "401.2",
            },
        },
    },
    _LIZARDFOLK_STARGAZER_LOCATOR: {
        "mode": "authored",
        "authoredMemberPresent": True,
        "value": 10,
    },
    _AIUVARIN_ELEMENTALIST_LOCATOR: {
        "mode": "derived",
        "authoredMemberPresent": False,
        "inputDc": 18,
        "formula": "DC - 10",
        "value": 8,
        "rule": {
            "id": "dc-from-modifier",
            "provider": {
                "sourceId": "core-pc1",
                "locator": "401.2",
            },
        },
    },
}
_SPELLCASTING_EXPLICIT_GRANTS = {
    (_GOBLIN_WAR_CHANTER_LOCATOR, "courageous-anthem"),
    (_GNOME_BARD_LOCATOR, "courageous-anthem"),
    (_KOBOLD_CAVERN_MAGE_LOCATOR, "figment"),
}
_SPELLCASTING_EXECUTABLE_BY_LOCATOR = {
    _GOBLIN_PYRO_LOCATOR: (
        "breathe-fire",
        "grease",
        "ignition",
        "light",
        "tangle-vine",
        "telekinetic-hand",
    ),
    _GOBLIN_WAR_CHANTER_LOCATOR: (
        "bless",
        "soothe",
        "courageous-anthem",
        "telekinetic-hand",
        "telekinetic-projectile",
    ),
    _GNOME_BARD_LOCATOR: (
        "courageous-anthem",
        "summon-instrument",
    ),
    _KOBOLD_CAVERN_MAGE_LOCATOR: (
        "fleet-step",
        "heal",
        "pummeling-rubble",
        "runic-weapon",
        "caustic-blast",
        "tangle-vine",
    ),
    _LIZARDFOLK_STARGAZER_LOCATOR: (
        "heal",
        "runic-body",
    ),
    _AIUVARIN_ELEMENTALIST_LOCATOR: (
        "thunderstrike",
        "electric-arc",
    ),
}
_AIUVARIN_ELEMENTALIST_PREPARED_SPELL_IDS = (
    "gentle-landing",
    "gust-of-wind",
    "illusory-disguise",
    "thunderstrike",
)
_AIUVARIN_ELEMENTALIST_CANTRIP_IDS = (
    "detect-magic",
    "electric-arc",
    "light",
    "message",
    "shield",
)
_AIUVARIN_ELEMENTALIST_SPELL_EXPECTATIONS = {
    "gentle-landing": (
        "Gentle Landing",
        ("reaction", None, ()),
        (
            "reaction-spellcasting",
            "falling-state",
            "falling-damage",
        ),
    ),
    "gust-of-wind": (
        "Gust of Wind",
        ("two", 2, (2,)),
        (
            "line-area",
            "persistent-area",
            "forced-movement",
            "flying-state",
            "environmental-effects",
        ),
    ),
    "illusory-disguise": (
        "Illusory Disguise",
        ("two", 2, (2,)),
        (
            "disguise-state",
            "impersonate",
            "dismiss",
        ),
    ),
    "thunderstrike": (
        "Thunderstrike",
        ("two", 2, (2,)),
        (),
    ),
    "detect-magic": (
        "Detect Magic",
        ("two", 2, (2,)),
        (
            "magic-detection",
            "effect-rank-detection",
        ),
    ),
    "electric-arc": (
        "Electric Arc",
        ("two", 2, (2,)),
        (),
    ),
    "light": (
        "Light",
        ("two", 2, (2,)),
        ("prepared-carrier-light-provider",),
    ),
    "message": (
        "Message",
        ("single", 1, (1,)),
        (
            "private-communication",
            "target-reply-timing",
        ),
    ),
    "shield": (
        "Shield",
        ("single", 1, (1,)),
        (
            "spell-shield",
            "magical-shield-block",
            "recast-lockout",
        ),
    ),
}
_KOBOLD_CAVERN_MAGE_REVIEWED_EFFECTS = {
    "heal": _HEAL_EFFECT_DEFINITION,
    "fleet-step": {
        "type": "self-movement-modifier",
        "target": "self",
        "movementModifiers": [
            {
                "statistic": "speed",
                "scope": {
                    "kind": "named-speed",
                    "movementMode": "land",
                },
                "type": "status",
                "valueFeet": 30,
            }
        ],
        "duration": {
            "rounds": 10,
            "source": "1 minute",
        },
    },
    "pummeling-rubble": {
        "type": "cone-basic-save-damage",
        "area": {
            "shape": "cone",
            "distanceFeet": 15,
            "origin": "caster",
        },
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dcSource": "casting",
        },
        "damage": {
            "dice": {"count": 2, "size": 4},
            "type": "bludgeoning",
        },
        "outcomes": {
            "failure": {"pushFeet": 5},
            "criticalFailure": {"pushFeet": 10},
        },
        "heightened": {
            "everyRanks": 1,
            "damageDice": {"count": 2, "size": 4},
        },
    },
    "runic-weapon": _RUNIC_WEAPON_EFFECT_DEFINITION,
    "caustic-blast": {
        "type": "ranged-burst-basic-save-damage",
        "rangeFeet": 30,
        "area": {
            "shape": "burst",
            "radiusFeet": 5,
            "origin": {"kind": "selected-grid-vertex"},
        },
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dcSource": "casting",
        },
        "damage": {
            "dice": {"count": 1, "size": 8},
            "type": "acid",
        },
        "outcomes": {
            "criticalFailure": {
                "persistentDamage": {
                    "flatAmount": 1,
                    "type": "acid",
                },
            },
        },
        "heightened": {
            "everyRanks": 2,
            "initialDamageDice": {"count": 1, "size": 8},
            "criticalPersistentDamageFlatAmount": 1,
        },
    },
    "tangle-vine": {
        "type": "spell-attack-speed-control",
        "rangeFeet": 30,
        "target": "one-creature",
        "defense": "armor-class",
        "attackMode": "ranged",
        "outcomes": {
            "criticalSuccess": {
                "immobilized": True,
                "movementModifiers": [
                    {
                        "statistic": "speed",
                        "scope": {"kind": "all-speeds"},
                        "type": "circumstance",
                        "valueFeet": -10,
                    },
                ],
                "duration": {"rounds": 1},
                "escape": {
                    "dcSource": "casting",
                    "removes": [
                        "speed-penalty",
                        "immobilized",
                    ],
                },
            },
            "success": {
                "immobilized": False,
                "movementModifiers": [
                    {
                        "statistic": "speed",
                        "scope": {"kind": "all-speeds"},
                        "type": "circumstance",
                        "valueFeet": -10,
                    },
                ],
                "duration": {"rounds": 1},
                "escape": {
                    "dcSource": "casting",
                    "removes": ["speed-penalty"],
                },
            },
            "failure": {"unaffected": True},
        },
        "heightened": {
            "2nd": {"rounds": 2},
            "4th": {"minutes": 1},
        },
    },
}
_LIZARDFOLK_STARGAZER_REVIEWED_EFFECTS = {
    "heal": _HEAL_EFFECT_DEFINITION,
    "runic-body": {
        "type": "target-unarmed-striking-runes",
        "range": {
            "kind": "touch",
            "maximumDistanceFeet": 5,
        },
        "target": "one-willing-creature",
        "attackItemBonus": 1,
        "damageDiceCount": 2,
        "duration": {
            "rounds": 10,
            "source": "1 minute",
        },
        "heightened": {
            "6th": {
                "potencyBonus": 2,
                "strikingRune": "greater",
            },
            "9th": {
                "potencyBonus": 3,
                "strikingRune": "major",
            },
        },
    },
}
_AIUVARIN_ELEMENTALIST_REVIEWED_EFFECTS = {
    "thunderstrike": {
        "type": "single-target-basic-save-multi-damage-and-condition",
        "rangeFeet": 120,
        "target": "one-creature",
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dcSource": "casting",
        },
        "damageComponents": [
            {
                "dice": {"count": 1, "size": 12},
                "type": "electricity",
            },
            {
                "dice": {"count": 1, "size": 4},
                "type": "sonic",
            },
        ],
        "conditionalTarget": {
            "predicate": "wearing-metal-armor-or-made-of-metal",
            "savingThrowModifier": {
                "type": "circumstance",
                "value": -1,
            },
            "ifDamaged": {
                "condition": {
                    "id": "clumsy",
                    "value": 1,
                    "duration": {"rounds": 1},
                },
            },
        },
        "heightened": {
            "everyRanks": 1,
            "damageComponents": [
                {
                    "dice": {"count": 1, "size": 12},
                    "type": "electricity",
                },
                {
                    "dice": {"count": 1, "size": 4},
                    "type": "sonic",
                },
            ],
        },
    },
    "electric-arc": {
        "type": "multi-target-basic-save-damage",
        "rangeFeet": 30,
        "targets": {
            "kind": "creature",
            "minimum": 1,
            "maximum": 2,
            "distinct": True,
        },
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dcSource": "casting",
        },
        "damage": {
            "dice": {"count": 2, "size": 4},
            "type": "electricity",
        },
        "heightened": {
            "everyRanks": 1,
            "damageDice": {"count": 1, "size": 4},
        },
    },
}


def _spellcasting_rules_for_locator(
    locator: str,
    /,
) -> tuple[tuple[str, str], ...]:
    if locator in _PREPARED_SPELLCASTING_CREATURE_LOCATORS:
        return _PREPARED_SPELLCASTING_GOVERNING_RULES + (
            (_SPELLCASTING_DERIVED_ATTACK_RULE,)
            if locator == _AIUVARIN_ELEMENTALIST_LOCATOR
            else ()
        )
    return _SPELLCASTING_GOVERNING_RULES + (
        (
            _SPELLCASTING_DERIVED_ATTACK_RULE,
            *_SPELLCASTING_MOVEMENT_RULES,
            ("duration", "426.2"),
        )
        if locator == _KOBOLD_CAVERN_MAGE_LOCATOR
        else ()
    )


def _spellcasting_authorization(
    *,
    locator: str,
    spell_id: str,
    tradition: str,
) -> dict[str, Any]:
    provider_traditions = _SPELLCASTING_PROVIDER_TRADITIONS[spell_id]
    if (locator, spell_id) in _SPELLCASTING_EXPLICIT_GRANTS:
        return {
            "mode": "explicit-repertoire-grant",
            "tradition": tradition,
            "providerTraditions": list(provider_traditions),
            "source": {
                "sourceId": "core-mc1",
                "locator": locator,
            },
        }
    return {
        "mode": "tradition",
        "tradition": tradition,
    }
_PLAN_FIELDS = frozenset(
    (
        "Name",
        "Size",
        "Speed",
        "Perception",
        "HP",
        "AC",
        "Fort",
        "Will",
        "Weaknesses",
        "Resistances",
        "Immunities",
    )
)
_PLAIN_SIGNED_SAVE_RE = re.compile(r"^[+-][0-9]+$", re.ASCII)


def _canonical_json(value: Any, /) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class CreatureStatCompilationPlan:
    """Immutable internal projection derived from one exact creature block."""

    source_id: str
    locator: str
    block_sha256: str
    projection_json: str
    base_values: tuple[tuple[str, int], ...]
    legacy_space_json: str | None
    runtime_deferrals: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self) is not CreatureStatCompilationPlan:
            raise TypeError(
                "CreatureStatCompilationPlan subclasses are unsupported"
            )
        if (
            type(self.source_id) is not str
            or self.source_id != "core-mc1"
            or type(self.locator) is not str
            or not self.locator
            or type(self.block_sha256) is not str
            or len(self.block_sha256) != 64
            or type(self.projection_json) is not str
            or type(self.base_values) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or item[0] not in {"HP", "AC", "Fort", "Will"}
                or type(item[1]) is not int
                for item in self.base_values
            )
            or tuple(field for field, _value in self.base_values)
            != tuple(
                sorted(field for field, _value in self.base_values)
            )
            or len(self.base_values)
            != len({field for field, _value in self.base_values})
            or (
                self.legacy_space_json is not None
                and type(self.legacy_space_json) is not str
            )
            or type(self.runtime_deferrals) is not tuple
            or any(
                type(item) is not str or not item
                for item in self.runtime_deferrals
            )
            or self.runtime_deferrals
            != tuple(sorted(set(self.runtime_deferrals)))
        ):
            raise TypeError(
                "CreatureStatCompilationPlan state is invalid"
            )
        projection = json.loads(self.projection_json)
        if (
            type(projection) is not dict
            or projection.get("schema") != 1
            or projection.get("status") != "compiled"
            or projection.get("runtimeReady") is not False
            or _canonical_json(projection) != self.projection_json
        ):
            raise TypeError(
                "CreatureStatCompilationPlan projection is invalid"
            )
        if self.legacy_space_json is not None:
            legacy_space = json.loads(self.legacy_space_json)
            if (
                type(legacy_space) is not dict
                or _canonical_json(legacy_space)
                != self.legacy_space_json
            ):
                raise TypeError(
                    "CreatureStatCompilationPlan legacy space is invalid"
                )


@dataclass(frozen=True, slots=True)
class CreatureStrikeCompilationPlan:
    """One exact source-occurrence Strike projection for a creature."""

    source_id: str
    locator: str
    block_sha256: str
    projection_json: str

    def __post_init__(self) -> None:
        if type(self) is not CreatureStrikeCompilationPlan:
            raise TypeError(
                "CreatureStrikeCompilationPlan subclasses are unsupported"
            )
        if (
            type(self.source_id) is not str
            or self.source_id not in _CREATURE_SOURCE_IDS
            or type(self.locator) is not str
            or not self.locator
            or type(self.block_sha256) is not str
            or len(self.block_sha256) != 64
            or type(self.projection_json) is not str
        ):
            raise TypeError(
                "CreatureStrikeCompilationPlan state is invalid"
            )
        projection = json.loads(self.projection_json)
        strikes = (
            projection.get("strikes")
            if type(projection) is dict
            else None
        )
        counts = (
            projection.get("counts")
            if type(projection) is dict
            else None
        )
        contract = (
            projection.get("integrationContract")
            if type(projection) is dict
            else None
        )
        source = (
            projection.get("source")
            if type(projection) is dict
            else None
        )
        receipt = (
            source.get("receipt")
            if type(source) is dict
            else None
        )
        address = (
            receipt.get("address")
            if type(receipt) is dict
            else None
        )
        hashes = (
            receipt.get("hashes")
            if type(receipt) is dict
            else None
        )
        occurrence_ids = (
            tuple(item.get("id") for item in strikes)
            if type(strikes) is list
            and all(type(item) is dict for item in strikes)
            else ()
        )
        if (
            type(projection) is not dict
            or projection.get("schema") != 1
            or projection.get("kind")
            != "pf2er-strike-integration-projection"
            or projection.get("status") != "compile-only"
            or projection.get("runtimeSupported") is not False
            or projection.get("registryStatus") != "unregistered"
            or type(contract) is not dict
            or contract.get("idPolicy")
            != "exact-source-occurrence-v1"
            or type(projection.get("facadeReady")) is not bool
            or type(strikes) is not list
            or not strikes
            or type(counts) is not dict
            or counts.get("sourceStrikeOccurrences") != len(strikes)
            or counts.get("uniqueProjectedIds")
            != len(set(occurrence_ids))
            or len(occurrence_ids) != len(set(occurrence_ids))
            or any(
                type(item) is not str or not item
                for item in occurrence_ids
            )
            or type(address) is not dict
            or address.get("sourceId") != self.source_id
            or address.get("locator") != self.locator
            or type(hashes) is not dict
            or hashes.get("selectionSha256") != self.block_sha256
            or _canonical_json(projection) != self.projection_json
        ):
            raise TypeError(
                "CreatureStrikeCompilationPlan projection is invalid"
            )


@dataclass(frozen=True, slots=True)
class CreatureAbilityCompilationPlan:
    """Exact ordered action envelopes for every direct creature ability."""

    source_id: str
    locator: str
    block_sha256: str
    projection_json: str

    def __post_init__(self) -> None:
        if type(self) is not CreatureAbilityCompilationPlan:
            raise TypeError(
                "CreatureAbilityCompilationPlan subclasses are unsupported"
            )
        if (
            type(self.source_id) is not str
            or self.source_id != "core-mc1"
            or type(self.locator) is not str
            or not self.locator
            or type(self.block_sha256) is not str
            or len(self.block_sha256) != 64
            or type(self.projection_json) is not str
        ):
            raise TypeError(
                "CreatureAbilityCompilationPlan state is invalid"
            )
        projection = json.loads(self.projection_json)
        abilities = (
            projection.get("abilities")
            if type(projection) is dict
            else None
        )
        source = (
            projection.get("creatureSource")
            if type(projection) is dict
            else None
        )
        address = (
            source.get("address")
            if type(source) is dict
            else None
        )
        hashes = (
            source.get("hashes")
            if type(source) is dict
            else None
        )
        member_ordinals = (
            tuple(item.get("memberOrdinal") for item in abilities)
            if type(abilities) is list
            and all(type(item) is dict for item in abilities)
            else ()
        )
        if (
            type(projection) is not dict
            or projection.get("family") != "ability-action-envelopes"
            or projection.get("effectStatus") != "deferred"
            or projection.get("runtimeReady") is not False
            or projection.get("activation") != "compile-only"
            or type(projection.get("creatureName")) is not str
            or not projection["creatureName"]
            or type(abilities) is not list
            or projection.get("abilityCount") != len(abilities)
            or member_ordinals != tuple(sorted(member_ordinals))
            or len(member_ordinals) != len(set(member_ordinals))
            or any(
                type(item) is not int or item < 0 or item > 63
                for item in member_ordinals
            )
            or type(address) is not dict
            or address.get("sourceId") != self.source_id
            or address.get("locator") != self.locator
            or type(hashes) is not dict
            or hashes.get("selectionSha256") != self.block_sha256
            or _canonical_json(projection) != self.projection_json
        ):
            raise TypeError(
                "CreatureAbilityCompilationPlan projection is invalid"
            )
        for ability in abilities:
            action = ability.get("action")
            deferred = ability.get("deferred")
            if (
                type(ability.get("abilityLabel")) is not str
                or not ability["abilityLabel"]
                or ability.get("shape") not in {"prose", "structured"}
                or type(ability.get("rawAbilityMemberJson")) is not str
                or not ability["rawAbilityMemberJson"]
                or ability.get("effectStatus") != "deferred"
                or ability.get("runtimeReady") is not False
                or type(action) is not dict
                or action.get("runtimeReady") is not False
                or type(deferred) is not list
                or not any(
                    type(item) is dict
                    and item.get("id")
                    == "named-ability-effect-compiler"
                    and item.get("status") == "deferred"
                    and item.get("blocks")
                    == "effect-runtime-activation"
                    for item in deferred
                )
            ):
                raise TypeError(
                    "CreatureAbilityCompilationPlan ability is invalid"
                )
            token = action.get("token")
            cost = action.get("actionCost")
            kind = action.get("kind")
            if (token, cost, kind) not in {
                (None, None, "passive"),
                ("single", 1, "action"),
                ("two", 2, "activity"),
                ("three", 3, "activity"),
                ("reaction", "reaction", "reaction"),
                ("free", "free", "free-action"),
            }:
                raise TypeError(
                    "CreatureAbilityCompilationPlan action is invalid"
                )


def _validate_creature_spellcasting_plan(
    plan: "CreatureSpellcastingCompilationPlan",
) -> None:
    if type(plan) is not CreatureSpellcastingCompilationPlan:
        raise TypeError(
            "CreatureSpellcastingCompilationPlan subclasses are unsupported"
        )
    if (
        type(plan.source_id) is not str
        or plan.source_id != "core-mc1"
        or type(plan.locator) is not str
        or plan.locator not in _SPELLCASTING_CREATURE_LOCATORS
        or type(plan.block_sha256) is not str
        or len(plan.block_sha256) != 64
        or type(plan.projection_json) is not str
    ):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan state is invalid"
        )
    projection = json.loads(plan.projection_json)
    prepared = (
        plan.locator in _PREPARED_SPELLCASTING_CREATURE_LOCATORS
    )
    expected_family_id = (
        _PREPARED_SPELLCASTING_FAMILY_ID
        if prepared
        else _SPELLCASTING_FAMILY_ID
    )
    expected_compiler_id = (
        _PREPARED_SPELLCASTING_COMPILER_ID
        if prepared
        else _SPELLCASTING_COMPILER_ID
    )
    if (
        type(projection) is not dict
        or set(projection)
        != {
            "schema",
            "kind",
            "familyId",
            "compilerId",
            "supportState",
            "compileSupported",
            "runtimeActivation",
            "creatureSource",
            "casting",
            "spells",
            "governingRules",
        }
        or projection.get("schema") != 1
        or projection.get("kind")
        != "pf2er-creature-spellcasting-plan"
        or projection.get("familyId") != expected_family_id
        or projection.get("compilerId") != expected_compiler_id
        or projection.get("supportState") != "partial-runtime"
        or projection.get("compileSupported") is not True
        or projection.get("creatureSource")
        != {"sourceId": plan.source_id, "locator": plan.locator}
        or _canonical_json(projection) != plan.projection_json
    ):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan projection is invalid"
        )
    casting = projection.get("casting")
    expected_attack_evidence = _SPELLCASTING_ATTACK_EVIDENCE.get(
        plan.locator
    )
    expected_casting_fields = {
        "id",
        "mode",
        "tradition",
        "dc",
        "attack",
        "attackEvidence",
        "preparedSpells" if prepared else "slots",
        "cantrips",
    }
    if (
        type(casting) is not dict
        or set(casting) != expected_casting_fields
        or casting.get("mode")
        != ("prepared" if prepared else "spontaneous")
        or casting.get("tradition")
        not in {"arcane", "divine", "occult", "primal"}
        or casting.get("id")
        != (
            f"{casting.get('tradition')}-"
            f"{'prepared' if prepared else 'spontaneous'}-spells"
        )
        or casting.get("attackEvidence") != expected_attack_evidence
        or isinstance(casting.get("dc"), bool)
        or not isinstance(casting.get("dc"), int)
        or casting["dc"] <= 0
        or (
            casting.get("attack") is not None
            and (
                isinstance(casting.get("attack"), bool)
                or not isinstance(casting.get("attack"), int)
            )
        )
    ):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan casting is invalid"
        )
    slots = casting.get("slots")
    prepared_spells = casting.get("preparedSpells")
    cantrips = casting.get("cantrips")
    if (
        (
            prepared
            and (
                type(prepared_spells) is not list
                or not prepared_spells
                or any(
                    type(item) is not dict
                    or set(item) != {"rank", "spellId", "maximum"}
                    or isinstance(item.get("rank"), bool)
                    or not isinstance(item.get("rank"), int)
                    or not 1 <= item["rank"] <= 10
                    or item.get("spellId")
                    not in _SPELLCASTING_PROVIDER_BY_ID
                    or isinstance(item.get("maximum"), bool)
                    or not isinstance(item.get("maximum"), int)
                    or item["maximum"] <= 0
                    for item in prepared_spells
                )
            )
        )
        or (
            not prepared
            and (
                type(slots) is not list
                or not slots
                or any(
                    type(slot) is not dict
                    or set(slot) != {"rank", "maximum", "spellIds"}
                    or isinstance(slot.get("rank"), bool)
                    or not isinstance(slot.get("rank"), int)
                    or not 1 <= slot["rank"] <= 10
                    or isinstance(slot.get("maximum"), bool)
                    or not isinstance(slot.get("maximum"), int)
                    or slot["maximum"] <= 0
                    or type(slot.get("spellIds")) is not list
                    or not slot["spellIds"]
                    or any(
                        type(spell_id) is not str
                        or spell_id not in _SPELLCASTING_PROVIDER_BY_ID
                        for spell_id in slot["spellIds"]
                    )
                    for slot in slots
                )
                or len({slot["rank"] for slot in slots})
                != len(slots)
            )
        )
        or type(cantrips) is not dict
        or set(cantrips) != {"rank", "spellIds"}
        or isinstance(cantrips.get("rank"), bool)
        or not isinstance(cantrips.get("rank"), int)
        or not 1 <= cantrips["rank"] <= 10
        or type(cantrips.get("spellIds")) is not list
        or not cantrips["spellIds"]
        or any(
            type(spell_id) is not str
            or spell_id not in _SPELLCASTING_PROVIDER_BY_ID
            for spell_id in cantrips["spellIds"]
        )
    ):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan repertoire is invalid"
        )
    repertoire_ids = (
        [
            item["spellId"]
            for item in prepared_spells
        ]
        if prepared
        else [
            spell_id
            for slot in slots
            for spell_id in slot["spellIds"]
        ]
    ) + list(cantrips["spellIds"])
    if len(repertoire_ids) != len(set(repertoire_ids)):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan repertoire is duplicated"
        )
    if plan.locator == _AIUVARIN_ELEMENTALIST_LOCATOR and (
        casting["id"] != "arcane-prepared-spells"
        or casting["tradition"] != "arcane"
        or casting["dc"] != 18
        or casting["attack"] != 8
        or prepared_spells
        != [
            {"rank": 1, "spellId": spell_id, "maximum": 1}
            for spell_id in _AIUVARIN_ELEMENTALIST_PREPARED_SPELL_IDS
        ]
        or cantrips
        != {
            "rank": 1,
            "spellIds": list(
                _AIUVARIN_ELEMENTALIST_CANTRIP_IDS
            ),
        }
    ):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan Aiuvarin carrier is invalid"
        )
    activation = projection.get("runtimeActivation")
    if (
        type(activation) is not dict
        or set(activation)
        != {"status", "executableSpellIds", "deferredSpellIds"}
        or activation.get("status") != "partial"
        or type(activation.get("executableSpellIds")) is not list
        or type(activation.get("deferredSpellIds")) is not list
    ):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan activation is invalid"
        )
    executable = activation["executableSpellIds"]
    deferred = activation["deferredSpellIds"]
    expected_executable = list(
        _SPELLCASTING_EXECUTABLE_BY_LOCATOR[plan.locator]
    )
    expected_deferred = [
        spell_id
        for spell_id in repertoire_ids
        if spell_id not in expected_executable
    ]
    if (
        any(type(spell_id) is not str for spell_id in executable + deferred)
        or len(executable + deferred) != len(set(executable + deferred))
        or set(executable + deferred) != set(repertoire_ids)
        or executable != expected_executable
        or deferred != expected_deferred
        or executable != [
            spell_id for spell_id in repertoire_ids if spell_id in executable
        ]
        or deferred != [
            spell_id for spell_id in repertoire_ids if spell_id in deferred
        ]
    ):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan projection is invalid: "
            "activation is inconsistent"
        )
    spells = projection.get("spells")
    if (
        type(spells) is not list
        or len(spells) != len(repertoire_ids)
        or [spell.get("id") for spell in spells if type(spell) is dict]
        != repertoire_ids
    ):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan spells are invalid"
        )
    for spell in spells:
        spell_id = spell["id"]
        execution = spell.get("execution")
        is_active = spell_id in executable
        expected_locator = _SPELLCASTING_PROVIDER_BY_ID[spell_id]
        expected_traditions = _SPELLCASTING_PROVIDER_TRADITIONS[spell_id]
        expected_authorization = _spellcasting_authorization(
            locator=plan.locator,
            spell_id=spell_id,
            tradition=casting["tradition"],
        )
        expected_reviewed_effect = (
            _KOBOLD_CAVERN_MAGE_REVIEWED_EFFECTS.get(spell_id)
            if plan.locator == _KOBOLD_CAVERN_MAGE_LOCATOR
            else (
                _LIZARDFOLK_STARGAZER_REVIEWED_EFFECTS.get(
                    spell_id
                )
                if plan.locator == _LIZARDFOLK_STARGAZER_LOCATOR
                else (
                    _AIUVARIN_ELEMENTALIST_REVIEWED_EFFECTS.get(
                        spell_id
                    )
                    if plan.locator == _AIUVARIN_ELEMENTALIST_LOCATOR
                    else None
                )
            )
        )
        action_shape = (
            spell.get("rawActionCost"),
            spell.get("actionCost"),
            tuple(spell.get("actionVariants") or ()),
        )
        expected_aiuvarin_spell = (
            _AIUVARIN_ELEMENTALIST_SPELL_EXPECTATIONS.get(spell_id)
            if plan.locator == _AIUVARIN_ELEMENTALIST_LOCATOR
            else None
        )
        if (
            set(spell)
            != {
                "id",
                "name",
                "rank",
                "kind",
                "actionCost",
                "rawActionCost",
                "actionVariants",
                "traits",
                "traditions",
                "repertoireAuthorization",
                "provider",
                "compiledEffect",
                "execution",
            }
            or type(spell.get("name")) is not str
            or not spell["name"]
            or isinstance(spell.get("rank"), bool)
            or not isinstance(spell.get("rank"), int)
            or not 1 <= spell["rank"] <= 10
            or spell.get("kind") not in {"spell", "cantrip"}
            or type(spell.get("actionVariants")) is not list
            or any(
                type(cost) is not int or not 1 <= cost <= 3
                for cost in spell["actionVariants"]
            )
            or action_shape
            not in {
                ("single", 1, (1,)),
                ("two", 2, (2,)),
                ("three", 3, (3,)),
                ("single-to-three", None, (1, 2, 3)),
                ("reaction", None, ()),
            }
            or (
                action_shape == ("reaction", None, ())
                and (
                    plan.locator != _AIUVARIN_ELEMENTALIST_LOCATOR
                    or spell_id != "gentle-landing"
                )
            )
            or type(spell.get("traits")) is not list
            or not spell["traits"]
            or type(spell.get("traditions")) is not list
            or spell["traditions"] != expected_traditions
            or spell.get("repertoireAuthorization")
            != expected_authorization
            or spell.get("provider")
            != {"sourceId": "core-pc1", "locator": expected_locator}
            or (
                spell.get("compiledEffect") is not None
                and type(spell.get("compiledEffect")) is not dict
            )
            or (is_active and type(spell.get("compiledEffect")) is not dict)
            or (
                plan.locator == _AIUVARIN_ELEMENTALIST_LOCATOR
                and spell.get("compiledEffect") != expected_reviewed_effect
            )
            or (
                plan.locator != _AIUVARIN_ELEMENTALIST_LOCATOR
                and expected_reviewed_effect is not None
                and spell.get("compiledEffect") != expected_reviewed_effect
            )
            or type(execution) is not dict
            or set(execution)
            != {
                "executable",
                "status",
                "runtimeSupported",
                "runtimeDependencies",
            }
            or execution.get("executable") is not is_active
            or execution.get("runtimeSupported") is not is_active
            or execution.get("status")
            != ("active" if is_active else "deferred")
            or type(execution.get("runtimeDependencies")) is not list
            or (
                expected_aiuvarin_spell is not None
                and (
                    spell["name"] != expected_aiuvarin_spell[0]
                    or action_shape != expected_aiuvarin_spell[1]
                    or execution["runtimeDependencies"]
                    != list(expected_aiuvarin_spell[2])
                )
            )
            or (
                is_active
                and execution["runtimeDependencies"] != []
            )
            or (
                not is_active
                and not execution["runtimeDependencies"]
            )
        ):
            raise TypeError(
                "CreatureSpellcastingCompilationPlan spell is invalid"
            )
    rules = projection.get("governingRules")
    expected_rules = _spellcasting_rules_for_locator(plan.locator)
    if (
        type(rules) is not list
        or tuple(
            (
                rule.get("id"),
                rule.get("provider", {}).get("locator")
                if type(rule) is dict
                and type(rule.get("provider")) is dict
                else None,
            )
            for rule in rules
        )
        != expected_rules
        or any(
            type(rule) is not dict
            or set(rule) != {"id", "provider"}
            or rule.get("provider")
            != {
                "sourceId": "core-pc1",
                "locator": locator,
            }
            for rule, (_rule_id, locator) in zip(
                rules,
                expected_rules,
                strict=True,
            )
        )
    ):
        raise TypeError(
            "CreatureSpellcastingCompilationPlan rules are invalid"
        )


@dataclass(frozen=True, slots=True)
class CreatureSpellcastingCompilationPlan:
    """Sanitized partial-runtime plan for a reviewed creature casting."""

    source_id: str
    locator: str
    block_sha256: str
    projection_json: str

    def __post_init__(self) -> None:
        _validate_creature_spellcasting_plan(self)


@dataclass(frozen=True, slots=True)
class _ProviderContext:
    geometry_rules: Any
    movement_rules: Any
    vision_rules: tuple[Any, ...]
    conditional_save_rules: tuple[Any, ...]


def _family_failure(
    family: str,
    failure: BaseException,
    /,
) -> _errors.EngineInputError:
    cause: BaseException | None = failure
    while cause is not None:
        if isinstance(cause, _SourceAuthorityError):
            raise cause
        cause = cause.__cause__
    if isinstance(failure, _errors.EngineInputError):
        return failure
    return _errors.EngineInputError(
        f"source-backed {family} compilation failed: {failure}"
    )


def _compact_geometry(value: dict[str, Any], /) -> dict[str, Any]:
    return {
        key: value[key]
        for key in (
            "size",
            "footprint",
            "naturalReach",
            "strikeReach",
            "profileLinkReady",
            "runtimeReady",
            "deferrals",
        )
    }


def _compact_movement(value: dict[str, Any], /) -> dict[str, Any]:
    """Publish movement semantics without internal authority receipts."""

    tokens = value.get("tokens")
    modes = value.get("modes")
    abilities = value.get("abilities")
    deferred = value.get("deferredMechanics")
    if (
        type(tokens) is not list
        or any(
            type(item) is not dict
            or set(item) != {"sourceText", "separatorAfter"}
            or type(item.get("sourceText")) is not str
            or item.get("separatorAfter") not in {",", ";", None}
            for item in tokens
        )
        or type(modes) is not dict
        or not modes
        or any(mode not in _MOVEMENT_MODES for mode in modes)
        or type(abilities) is not list
        or type(value.get("hasLandSpeed")) is not bool
        or value.get("hasLandSpeed") != ("land" in modes)
        or value.get("runtimeReady") is not False
        or type(deferred) is not list
        or any(type(item) is not str or not item for item in deferred)
    ):
        raise TypeError("movement-speed public projection is invalid")

    public_modes: dict[str, dict[str, Any]] = {}
    for mode, raw_mode in modes.items():
        if (
            type(raw_mode) is not dict
            or set(raw_mode)
            != {
                "feet",
                "sourceText",
                "sourceToken",
                "restriction",
                "providerRuleId",
                "rule",
            }
            or type(raw_mode.get("feet")) is not int
            or raw_mode["feet"] <= 0
            or raw_mode["feet"] % 5
            or type(raw_mode.get("sourceText")) is not str
            or type(raw_mode.get("sourceToken")) is not int
            or raw_mode["sourceToken"] < 0
            or type(raw_mode.get("providerRuleId")) is not str
            or type(raw_mode.get("rule")) is not dict
            or set(raw_mode["rule"]) != {"sourceId", "locator"}
            or any(
                type(raw_mode["rule"].get(key)) is not str
                or not raw_mode["rule"][key]
                for key in ("sourceId", "locator")
            )
            or (
                raw_mode.get("restriction") is not None
                and type(raw_mode["restriction"]) is not dict
            )
        ):
            raise TypeError(
                "movement-speed public mode projection is invalid"
            )
        public_modes[mode] = {
            key: raw_mode[key]
            for key in (
                "feet",
                "sourceText",
                "sourceToken",
                "restriction",
                "providerRuleId",
                "rule",
            )
        }

    public_abilities = []
    for ability in abilities:
        inherited = (
            ability.get("inheritedTarget")
            if type(ability) is dict
            else None
        )
        if (
            type(ability) is not dict
            or any(
                key not in ability
                for key in (
                    "id",
                    "label",
                    "kind",
                    "mechanicId",
                    "sourceText",
                    "sourceToken",
                    "markup",
                    "rule",
                    "inheritedTarget",
                    "runtimeStatus",
                )
            )
            or any(
                type(ability.get(key)) is not str
                or not ability[key]
                for key in (
                    "id",
                    "label",
                    "kind",
                    "mechanicId",
                    "sourceText",
                    "markup",
                    "runtimeStatus",
                )
            )
            or type(ability.get("sourceToken")) is not int
            or ability["sourceToken"] < 0
            or type(ability.get("rule")) is not dict
            or set(ability["rule"])
            != {"sourceId", "locator", "providerRuleId"}
            or type(ability["rule"].get("sourceId")) is not str
            or type(ability["rule"].get("locator")) is not str
            or (
                ability["rule"].get("providerRuleId") is not None
                and type(ability["rule"]["providerRuleId"]) is not str
            )
            or (
                inherited is not None
                and (
                    type(inherited) is not dict
                    or any(
                        key not in inherited
                        for key in (
                            "targetSourceId",
                            "targetLocator",
                            "targetCreatureName",
                            "targetRawKey",
                            "targetMemberOrdinal",
                            "targetRawValueKind",
                            "targetAbilitySha256",
                            "resolutionReason",
                            "review",
                        )
                    )
                    or type(inherited.get("review")) is not dict
                    or any(
                        key not in inherited["review"]
                        for key in (
                            "schema",
                            "reviewer",
                            "recordSha256",
                            "decisionDigest",
                        )
                    )
                )
            )
        ):
            raise TypeError(
                "movement-speed public ability projection is invalid"
            )
        public_inherited = (
            None
            if inherited is None
            else {
                "targetSourceId": inherited["targetSourceId"],
                "targetLocator": inherited["targetLocator"],
                "targetCreatureName": inherited[
                    "targetCreatureName"
                ],
                "targetRawKey": inherited["targetRawKey"],
                "targetMemberOrdinal": inherited[
                    "targetMemberOrdinal"
                ],
                "targetRawValueKind": inherited[
                    "targetRawValueKind"
                ],
                "targetAbilitySha256": inherited[
                    "targetAbilitySha256"
                ],
                "resolutionReason": inherited["resolutionReason"],
                "review": {
                    key: inherited["review"][key]
                    for key in (
                        "schema",
                        "reviewer",
                        "recordSha256",
                        "decisionDigest",
                    )
                },
            }
        )
        public_abilities.append(
            {
                "id": ability["id"],
                "label": ability["label"],
                "kind": ability["kind"],
                "mechanicId": ability["mechanicId"],
                "sourceText": ability["sourceText"],
                "sourceToken": ability["sourceToken"],
                "markup": ability["markup"],
                "rule": {
                    key: ability["rule"][key]
                    for key in (
                        "sourceId",
                        "locator",
                        "providerRuleId",
                    )
                },
                "inheritedTarget": public_inherited,
                "runtimeStatus": ability["runtimeStatus"],
            }
        )

    return {
        "tokens": [
            {
                "sourceText": item["sourceText"],
                "separatorAfter": item["separatorAfter"],
            }
            for item in tokens
        ],
        "modes": public_modes,
        "abilities": public_abilities,
        "hasLandSpeed": value["hasLandSpeed"],
        "runtimeReady": False,
        "deferredMechanics": list(deferred),
    }


def _compact_vision(value: dict[str, Any], /) -> dict[str, Any]:
    vision = value["vision"]
    return {
        "modifierSourceText": value["modifierSourceText"],
        "senses": value["senses"],
        "vision": {
            key: vision[key]
            for key in (
                "compileSupported",
                "runtimeSupported",
                "mechanic",
                "sourceToken",
                "deferredMechanics",
            )
        },
    }


def _compact_special_sense(
    value: dict[str, Any],
    /,
) -> dict[str, Any]:
    precision = value["precision"]
    return {
        "senseId": value["senseId"],
        "family": value["family"],
        "channel": value["channel"],
        "sourceText": value["source"]["rawSense"],
        "precision": {
            key: precision[key]
            for key in ("explicit", "effective", "basis")
        },
        "range": value["range"],
        "grammar": value["grammar"],
        "pageReference": value["pageReference"],
        "eligibility": value["eligibility"],
        "providerBlockers": value["rules"]["blockers"],
        "compilerReady": value["compilerReady"],
        "runtimeReady": value["runtimeReady"],
        "activation": value["activation"],
        "deferredMechanics": value["deferredMechanics"],
    }


def _compact_annotated_stat(
    value: dict[str, Any],
    /,
) -> dict[str, Any]:
    annotation = value["annotation"]
    return {
        "field": value["field"],
        "sourceText": value["sourceText"],
        "base": {
            key: value["base"][key]
            for key in ("value", "sourceText")
        },
        "annotation": {
            "prefixText": annotation["prefixText"],
            "suffixText": annotation["suffixText"],
            "fragments": [
                {
                    key: fragment[key]
                    for key in (
                        "ordinal",
                        "separator",
                        "text",
                        "semantics",
                    )
                }
                for fragment in annotation["fragments"]
            ],
        },
        "compileSupported": True,
        "runtimeSupported": False,
        "runtime": value["runtime"],
    }


def _compact_conditional_save(
    value: dict[str, Any],
    /,
) -> dict[str, Any]:
    return {
        key: value[key]
        for key in (
            "field",
            "sourceText",
            "baseSave",
            "conditionalClauses",
            "runtimeDeferrals",
            "registryStatus",
            "runtimeReady",
        )
    }


def _compact_immunities(
    value: dict[str, Any],
    /,
) -> dict[str, Any]:
    return {
        "field": value["field"],
        "fieldShape": value["fieldShape"],
        "tokens": [
            {
                key: token[key]
                for key in (
                    "sourceText",
                    "normalizedTerm",
                    "kind",
                    "support",
                    "deferredDependency",
                    "providerRuleIds",
                )
                if key in token
            }
            for token in value["tokens"]
        ],
        "runtime": value["runtime"],
    }


def _legacy_space(
    geometry: dict[str, Any] | None,
    /,
) -> dict[str, Any] | None:
    if geometry is None:
        return None
    footprint = geometry.get("footprint")
    reach = geometry.get("naturalReach")
    exact_footprint = (
        type(footprint) is dict
        and footprint.get("gridFootprintKind") == "exact"
        and footprint.get("spaceKind") == "exact"
    )
    canonical_minimum_footprint = (
        type(footprint) is dict
        and footprint.get("gridFootprintKind") == "canonical-minimum"
        and footprint.get("spaceKind") == "minimum"
    )
    if (
        type(footprint) is not dict
        or type(reach) is not dict
        or not (exact_footprint or canonical_minimum_footprint)
        or type(reach.get("resolvedFeet")) not in {int, float}
        or type(footprint.get("sizeRank")) is not int
        or type(footprint.get("widthSquares")) is not int
        or type(footprint.get("heightSquares")) is not int
        or type(footprint.get("spaceFeet")) not in {int, float}
        or type(geometry.get("size")) is not str
    ):
        return None
    selected_profile = reach.get("selectedProfile")
    reach_profile = (
        selected_profile
        if type(selected_profile) is str
        else geometry["size"].casefold()
    )
    result = {
        "sizeRank": footprint["sizeRank"],
        "reachProfile": reach_profile,
        "widthSquares": footprint["widthSquares"],
        "heightSquares": footprint["heightSquares"],
        "spaceFeet": footprint["spaceFeet"],
        "defaultReachFeet": reach["resolvedFeet"],
    }
    if canonical_minimum_footprint:
        result.update(
            {
                "spaceKind": "minimum",
                "gridFootprintKind": "canonical-minimum",
            }
        )
    return result


def _bind_compilation_api(
    *,
    validate_selection: Callable[..., Any],
    carrier_select: Callable[..., Any],
    toc_label: Callable[..., str],
    allowed_source_ids: property,
    resolve_rule: Callable[..., Any],
    bind_geometry_rules: Callable[..., Any],
    compile_geometry: Callable[..., Any],
    serialize_geometry: Callable[..., dict[str, Any]],
    bind_movement_rules: Callable[..., Any],
    bind_movement_inheritance: Callable[..., Any],
    compile_movement: Callable[..., Any],
    serialize_movement: Callable[..., dict[str, Any]],
    compile_vision: Callable[..., Any],
    compile_special_senses: Callable[..., Any],
    serialize_special_sense: Callable[..., dict[str, Any]],
    compile_annotated_stat: Callable[..., Any],
    serialize_annotated_stat: Callable[..., dict[str, Any]],
    conditional_requirements: Callable[..., Any],
    compile_conditional_save: Callable[..., Any],
    serialize_conditional_save: Callable[..., dict[str, Any]],
    compile_damage_defense_profile: Callable[..., Any],
    serialize_damage_defenses: Callable[..., dict[str, Any]],
    compile_damage_immunities: Callable[..., Any],
    serialize_damage_immunities: Callable[..., dict[str, Any]],
) -> tuple[Callable[..., Any], ...]:
    """Capture reviewed compiler entry points below rebindable module names."""

    @lru_cache(maxsize=8)
    def provider_context(
        authority: _SourceAuthorityAdapter,
    ) -> _ProviderContext:
        return _ProviderContext(
            geometry_rules=bind_geometry_rules(authority),
            movement_rules=bind_movement_rules(authority),
            vision_rules=tuple(
                resolve_rule(authority, requirement)
                for requirement in _VISION_RULE_REQUIREMENTS
            ),
            conditional_save_rules=tuple(
                resolve_rule(authority, requirement)
                for requirement in conditional_requirements()
            ),
        )

    def exact_fields(
        authority: _SourceAuthorityAdapter,
        creature_selection: _VerifiedSourceSelection,
    ) -> dict[str, _VerifiedSourceSelection]:
        verified = validate_selection(authority, creature_selection)
        block = verified.selected_value
        if (
            type(block) is not _RawSourceObject
            or block is not verified.carrier.raw_block
        ):
            raise _errors.EngineInputError(
                "stat compilation requires one exact creature block"
            )
        occurrences: dict[str, list[int]] = {}
        for ordinal, member in enumerate(block.members):
            if member.key in _PLAN_FIELDS:
                occurrences.setdefault(member.key, []).append(ordinal)
        duplicates = tuple(
            sorted(
                key
                for key, ordinals in occurrences.items()
                if len(ordinals) != 1
            )
        )
        if duplicates:
            raise _errors.EngineInputError(
                "source-backed stat field is duplicated: "
                + ", ".join(duplicates)
            )
        return {
            key: validate_selection(
                authority,
                carrier_select(
                    verified.carrier,
                    (_RawMemberStep(key, ordinals[0]),),
                ),
            )
            for key, ordinals in occurrences.items()
        }

    def compile_plan(
        authority: _SourceAuthorityAdapter,
        creature_selection: _VerifiedSourceSelection,
        /,
    ) -> CreatureStatCompilationPlan | None:
        if type(authority) is not _SourceAuthorityAdapter:
            raise TypeError(
                "stat compilation requires an exact "
                "SourceAuthorityAdapter"
            )
        if type(creature_selection) is not _VerifiedSourceSelection:
            raise TypeError(
                "stat compilation requires an exact verified selection"
            )
        fields = exact_fields(authority, creature_selection)
        name_selection = fields.get("Name")
        if (
            name_selection is None
            or type(name_selection.selected_value) is not str
            or not name_selection.selected_value
            or name_selection.selected_value
            != name_selection.selected_value.strip()
        ):
            raise _errors.EngineInputError(
                "source-backed creature Name is invalid"
            )
        address = creature_selection.address
        if (
            address.source_id != "core-mc1"
            or name_selection.selected_value
            != toc_label(authority, address.source_id, address.locator)
        ):
            raise _errors.EngineInputError(
                "creature name does not match its source target"
            )
        selected_scope = allowed_source_ids.__get__(authority)
        if not _REQUIRED_SOURCE_SCOPE.issubset(selected_scope):
            return None
        providers = provider_context(authority)

        families: dict[str, Any] = {
            "sizeSpaceReach": None,
            "movementSpeeds": None,
            "visionSenses": None,
            "specialSenses": [],
            "annotatedStats": {},
            "conditionalSaves": {},
            "damageDefenses": {},
            "damageImmunities": None,
        }
        base_values: dict[str, int] = {}
        deferrals: set[str] = set()

        size = fields.get("Size")
        speed = fields.get("Speed")
        if size is not None and speed is not None:
            try:
                geometry_patch = compile_geometry(
                    _CreatureGeometrySource(authority, size, speed),
                    providers.geometry_rules,
                    (),
                )
                if geometry_patch is not None:
                    geometry = _compact_geometry(
                        serialize_geometry(geometry_patch)
                    )
                    families["sizeSpaceReach"] = geometry
                    deferrals.update(
                        "size-space-reach:"
                        + str(item["id"])
                        for item in geometry["deferrals"]
                    )
                else:
                    geometry = None
                    deferrals.add(
                        "size-space-reach:compiler-no-match"
                    )
            except (TypeError, ValueError) as failure:
                raise _family_failure(
                    "size/space/reach",
                    failure,
                ) from failure
        else:
            geometry = None
            deferrals.add("size-space-reach:source-fields-missing")

        if speed is not None:
            try:
                movement_patch = compile_movement(
                    _MovementSpeedSource(
                        authority,
                        speed,
                        bind_movement_inheritance(
                            authority,
                            creature_selection,
                        ),
                    ),
                    providers.movement_rules,
                )
                if movement_patch is not None:
                    movement = _compact_movement(
                        serialize_movement(movement_patch)
                    )
                    families["movementSpeeds"] = movement
                    deferrals.update(
                        "movement-speeds:" + str(item)
                        for item in movement["deferredMechanics"]
                    )
                else:
                    deferrals.add(
                        "movement-speeds:compiler-no-match"
                    )
            except (TypeError, ValueError) as failure:
                raise _family_failure(
                    "movement-speed",
                    failure,
                ) from failure

        perception = fields.get("Perception")
        if perception is not None:
            try:
                vision = compile_vision(
                    authority,
                    creature_selection,
                    providers.vision_rules,
                )
                if vision is not None:
                    compact_vision = _compact_vision(vision)
                    families["visionSenses"] = compact_vision
                    deferrals.update(
                        "vision-senses:" + str(item)
                        for item in compact_vision["vision"][
                            "deferredMechanics"
                        ]
                    )
            except (TypeError, ValueError) as failure:
                raise _family_failure(
                    "vision-sense",
                    failure,
                ) from failure

            raw_perception = perception.selected_value
            raw_senses = (
                raw_perception.items[1]
                if type(raw_perception) is _RawSourceArray
                and len(raw_perception.items) == 2
                else None
            )
            if (
                type(raw_senses) is _RawSourceArray
                and raw_senses.items
                and any(
                    type(token) is str
                    and any(
                        marker in token.casefold()
                        for marker in _SPECIAL_SENSE_MARKERS
                    )
                    for token in raw_senses.items
                )
            ):
                try:
                    carrier = _SenseCreatureCarrier(
                        authority,
                        perception,
                    )
                    patches = compile_special_senses(
                        _SenseSource(carrier, 0),
                        _SPECIAL_SENSE_FRAGMENT.sense_compilers,
                    )
                    compact_senses = [
                        _compact_special_sense(
                            serialize_special_sense(patch)
                        )
                        for patch in patches
                    ]
                    families["specialSenses"] = compact_senses
                    for patch in compact_senses:
                        deferrals.update(
                            "special-senses:"
                            + str(patch["senseId"])
                            + ":"
                            + str(item)
                            for item in patch["deferredMechanics"]
                        )
                        if not patch["runtimeReady"]:
                            deferrals.add(
                                "special-senses:"
                                + str(patch["senseId"])
                                + ":runtime-not-registered"
                            )
                except (TypeError, ValueError) as failure:
                    raise _family_failure(
                        "special-sense",
                        failure,
                    ) from failure

        for field in _ANNOTATED_STAT_FIELDS:
            selection = fields.get(field)
            if selection is None:
                continue
            try:
                compiled = compile_annotated_stat(
                    authority,
                    selection.receipt,
                )
                if compiled is None:
                    continue
                serialized = _compact_annotated_stat(
                    serialize_annotated_stat(compiled)
                )
                families["annotatedStats"][field] = serialized
                base_values[field] = int(serialized["base"]["value"])
                deferrals.update(
                    "annotated-stats:"
                    + field
                    + ":"
                    + str(item["kind"])
                    for item in serialized["runtime"]["deferrals"]
                )
            except (TypeError, ValueError) as failure:
                raise _family_failure(
                    f"annotated {field}",
                    failure,
                ) from failure

        for field in _CONDITIONAL_SAVE_FIELDS:
            selection = fields.get(field)
            raw_value = (
                selection.selected_value
                if selection is not None
                else None
            )
            if (
                type(raw_value) is not str
                or _PLAIN_SIGNED_SAVE_RE.fullmatch(raw_value) is not None
            ):
                continue
            try:
                compiled = compile_conditional_save(
                    authority,
                    selection,
                    providers.conditional_save_rules,
                )
                serialized = _compact_conditional_save(
                    serialize_conditional_save(
                        compiled,
                        authority,
                    )
                )
                families["conditionalSaves"][field] = serialized
                base_values[field] = int(
                    serialized["baseSave"]["value"]
                )
                deferrals.update(
                    "conditional-saves:"
                    + field
                    + ":"
                    + str(item["id"])
                    for item in serialized["runtimeDeferrals"]
                )
            except (TypeError, ValueError) as failure:
                raise _family_failure(
                    f"conditional {field}",
                    failure,
                ) from failure

        try:
            compiled = compile_damage_defense_profile(
                authority,
                address.source_id,
                address.locator,
            )
            serialized = serialize_damage_defenses(
                authority,
                compiled,
            )
            families["damageDefenses"] = serialized
            source_fields = serialized.get("fields")
            if type(source_fields) is not list or len(source_fields) != 2:
                raise TypeError(
                    "damage-defense facade fields are invalid"
                )
            for source_field in source_fields:
                if type(source_field) is not dict:
                    raise TypeError(
                        "damage-defense facade field is invalid"
                    )
                field = source_field.get("field")
                entries = source_field.get("entries")
                if (
                    field not in _DAMAGE_DEFENSE_FIELDS
                    or type(entries) is not list
                ):
                    raise TypeError(
                        "damage-defense facade field projection is invalid"
                    )
                if source_field.get("shape") is not None:
                    deferrals.add(
                        "damage-defenses:"
                        + str(field)
                        + ":runtime-not-registered"
                    )
                for entry in entries:
                    if (
                        type(entry) is dict
                        and entry.get("support") == "deferred"
                        and type(entry.get("deferredDependency")) is str
                    ):
                        deferrals.add(
                            "damage-defenses:"
                            + str(field)
                            + ":"
                            + str(entry.get("ordinal"))
                            + ":"
                            + str(entry["deferredDependency"])
                        )
        except (TypeError, ValueError) as failure:
            raise _family_failure(
                "damage defense profile",
                failure,
            ) from failure

        immunities = fields.get("Immunities")
        if immunities is not None:
            try:
                compiled = compile_damage_immunities(
                    authority,
                    immunities,
                )
                serialized = _compact_immunities(
                    serialize_damage_immunities(compiled)
                )
                families["damageImmunities"] = serialized
                deferrals.add(
                    "damage-immunities:runtime-not-registered"
                )
                deferrals.update(
                    "damage-immunities:"
                    + str(token["normalizedTerm"])
                    + ":"
                    + str(token["deferredDependency"])
                    for token in serialized["tokens"]
                    if token.get("deferredDependency")
                )
            except (TypeError, ValueError) as failure:
                raise _family_failure(
                    "damage immunity",
                    failure,
                ) from failure

        projection = {
            "schema": 1,
            "status": "compiled",
            "runtimeReady": False,
            "families": families,
            "runtimeDeferredMechanics": sorted(deferrals),
        }
        legacy_space = _legacy_space(geometry)
        return CreatureStatCompilationPlan(
            source_id=address.source_id,
            locator=address.locator,
            block_sha256=creature_selection.block_sha256,
            projection_json=_canonical_json(projection),
            base_values=tuple(sorted(base_values.items())),
            legacy_space_json=(
                None
                if legacy_space is None
                else _canonical_json(legacy_space)
            ),
            runtime_deferrals=tuple(sorted(deferrals)),
        )

    def plan_base_value(
        plan: CreatureStatCompilationPlan | None,
        field: str,
        /,
    ) -> int | None:
        if plan is None:
            return None
        CreatureStatCompilationPlan.__post_init__(plan)
        if field not in {"HP", "AC", "Fort", "Will"}:
            raise ValueError("stat plan base field is invalid")
        return dict(plan.base_values).get(field)

    def plan_legacy_space(
        plan: CreatureStatCompilationPlan | None,
        /,
    ) -> dict[str, Any] | None:
        if plan is None:
            return None
        CreatureStatCompilationPlan.__post_init__(plan)
        return (
            None
            if plan.legacy_space_json is None
            else json.loads(plan.legacy_space_json)
        )

    def plan_projection(
        plan: CreatureStatCompilationPlan,
        /,
    ) -> dict[str, Any]:
        CreatureStatCompilationPlan.__post_init__(plan)
        return json.loads(plan.projection_json)

    def plan_speeds(
        plan: CreatureStatCompilationPlan | None,
        /,
    ) -> dict[str, int] | None:
        if plan is None:
            return None
        CreatureStatCompilationPlan.__post_init__(plan)
        projection = json.loads(plan.projection_json)
        families = projection.get("families")
        movement = (
            families.get("movementSpeeds")
            if type(families) is dict
            else None
        )
        modes = (
            movement.get("modes")
            if type(movement) is dict
            else None
        )
        if (
            type(movement) is not dict
            or movement.get("runtimeReady") is not False
            or type(movement.get("hasLandSpeed")) is not bool
            or type(modes) is not dict
            or not modes
            or any(mode not in _MOVEMENT_MODES for mode in modes)
            or movement["hasLandSpeed"] != ("land" in modes)
        ):
            raise _errors.EngineInputError(
                "movement-speed facade projection is invalid"
            )
        speeds: dict[str, int] = {}
        for mode, detail in modes.items():
            if (
                type(detail) is not dict
                or type(detail.get("feet")) is not int
                or detail["feet"] <= 0
                or detail["feet"] % 5
                or type(detail.get("sourceText")) is not str
                or type(detail.get("sourceToken")) is not int
                or detail["sourceToken"] < 0
                or type(detail.get("providerRuleId")) is not str
                or type(detail.get("rule")) is not dict
                or set(detail["rule"]) != {"sourceId", "locator"}
                or any(
                    type(detail["rule"].get(key)) is not str
                    or not detail["rule"][key]
                    for key in ("sourceId", "locator")
                )
                or (
                    detail.get("restriction") is not None
                    and type(detail["restriction"]) is not dict
                )
            ):
                raise _errors.EngineInputError(
                    "movement-speed facade mode is invalid"
                )
            speeds[mode] = detail["feet"]
        return speeds

    def plan_deferrals(
        plan: CreatureStatCompilationPlan | None,
        /,
    ) -> tuple[str, ...]:
        if plan is None:
            return ()
        CreatureStatCompilationPlan.__post_init__(plan)
        return plan.runtime_deferrals

    return (
        compile_plan,
        plan_base_value,
        plan_legacy_space,
        plan_projection,
        plan_speeds,
        plan_deferrals,
    )


def _bind_strike_compilation_api(
    *,
    compile_block: Callable[..., Any],
    project_bundle: Callable[..., Any],
    serialize_projection: Callable[..., dict[str, Any]],
) -> tuple[Callable[..., Any], ...]:
    """Capture the frozen Strike projection behind the facade seam."""

    def compile_plan(
        authority: _SourceAuthorityAdapter,
        creature_selection: _VerifiedSourceSelection,
        /,
    ) -> CreatureStrikeCompilationPlan:
        if type(authority) is not _SourceAuthorityAdapter:
            raise TypeError(
                "Strike compilation requires an exact "
                "SourceAuthorityAdapter"
            )
        if type(creature_selection) is not _VerifiedSourceSelection:
            raise TypeError(
                "Strike compilation requires an exact verified selection"
            )
        try:
            bundle = compile_block(authority, creature_selection)
            artifact = project_bundle(bundle)
            projection = serialize_projection(artifact)
            return CreatureStrikeCompilationPlan(
                source_id=creature_selection.address.source_id,
                locator=creature_selection.address.locator,
                block_sha256=creature_selection.block_sha256,
                projection_json=_canonical_json(projection),
            )
        except (TypeError, ValueError) as failure:
            raise _family_failure(
                "Strike",
                failure,
            ) from failure

    def plan_projection(
        plan: CreatureStrikeCompilationPlan,
        /,
    ) -> dict[str, Any]:
        CreatureStrikeCompilationPlan.__post_init__(plan)
        return json.loads(plan.projection_json)

    return compile_plan, plan_projection


def _bind_ability_compilation_api(
    *,
    compile_envelopes: Callable[..., Any],
    serialize_envelopes: Callable[..., dict[str, Any]],
) -> tuple[Callable[..., Any], ...]:
    """Capture the frozen action-envelope compiler behind the facade seam."""

    def compile_plan(
        authority: _SourceAuthorityAdapter,
        creature_selection: _VerifiedSourceSelection,
        /,
    ) -> CreatureAbilityCompilationPlan:
        if type(authority) is not _SourceAuthorityAdapter:
            raise TypeError(
                "ability compilation requires an exact "
                "SourceAuthorityAdapter"
            )
        if type(creature_selection) is not _VerifiedSourceSelection:
            raise TypeError(
                "ability compilation requires an exact verified selection"
            )
        try:
            compiled = compile_envelopes(
                authority,
                creature_selection,
            )
            projection = serialize_envelopes(compiled)
            return CreatureAbilityCompilationPlan(
                source_id=creature_selection.address.source_id,
                locator=creature_selection.address.locator,
                block_sha256=creature_selection.block_sha256,
                projection_json=_canonical_json(projection),
            )
        except (TypeError, ValueError) as failure:
            raise _family_failure(
                "ability action envelope",
                failure,
            ) from failure

    def plan_projection(
        plan: CreatureAbilityCompilationPlan,
        /,
    ) -> dict[str, Any]:
        CreatureAbilityCompilationPlan.__post_init__(plan)
        return json.loads(plan.projection_json)

    return compile_plan, plan_projection


def _public_receipt_source(
    value: object,
    /,
    *,
    source_id: str,
    locator: str,
) -> dict[str, str]:
    address = value.get("address") if type(value) is dict else None
    if (
        type(address) is not dict
        or address.get("sourceId") != source_id
        or address.get("locator") != locator
    ):
        raise TypeError("spellcasting source receipt is invalid")
    return {"sourceId": source_id, "locator": locator}


def _sanitize_spellcasting_projection(
    value: dict[str, Any],
    /,
) -> dict[str, Any]:
    if (
        type(value) is not dict
        or value.get("schema") != 1
        or value.get("supportState") != "partial-runtime"
        or value.get("compileSupported") is not True
    ):
        raise TypeError("spellcasting compiler projection is invalid")
    source_address = (
        value.get("source", {}).get("address")
        if type(value.get("source")) is dict
        else None
    )
    locator = (
        source_address.get("locator")
        if type(source_address) is dict
        else None
    )
    if locator not in _SPELLCASTING_CREATURE_LOCATORS:
        raise TypeError("spellcasting creature source is unsupported")
    prepared = locator in _PREPARED_SPELLCASTING_CREATURE_LOCATORS
    expected_kind = (
        "pf2er-prepared-spellcasting-compilation"
        if prepared
        else "pf2er-spontaneous-spellcasting-compilation"
    )
    expected_family_id = (
        _PREPARED_SPELLCASTING_FAMILY_ID
        if prepared
        else _SPELLCASTING_FAMILY_ID
    )
    expected_compiler_id = (
        _PREPARED_SPELLCASTING_COMPILER_ID
        if prepared
        else _SPELLCASTING_COMPILER_ID
    )
    if (
        value.get("kind") != expected_kind
        or value.get("familyId") != expected_family_id
        or value.get("compilerId") != expected_compiler_id
    ):
        raise TypeError("spellcasting compiler identity is invalid")
    creature_source = _public_receipt_source(
        value.get("source"),
        source_id="core-mc1",
        locator=locator,
    )
    casting = value.get("casting")
    if type(casting) is not dict:
        raise TypeError("spellcasting casting projection is invalid")
    public_casting = json.loads(_canonical_json(casting))
    attack_evidence = casting.get("attackEvidence")
    if (
        type(attack_evidence) is dict
        and attack_evidence.get("mode") == "derived"
    ):
        rule = attack_evidence.get("rule")
        if (
            type(rule) is not dict
            or rule.get("id") != "dc-from-modifier"
        ):
            raise TypeError(
                "spellcasting derived attack evidence is invalid"
            )
        public_casting["attackEvidence"]["rule"] = {
            "id": "dc-from-modifier",
            "provider": _public_receipt_source(
                rule.get("source"),
                source_id="core-pc1",
                locator="401.2",
            ),
        }
    if (
        public_casting.get("attackEvidence")
        != _SPELLCASTING_ATTACK_EVIDENCE[locator]
    ):
        raise TypeError("spellcasting attack evidence is invalid")
    spells = value.get("spells")
    if type(spells) is not list or not spells:
        raise TypeError("spellcasting spell projection is invalid")
    public_spells: list[dict[str, Any]] = []
    for spell in spells:
        spell_id = (
            spell.get("id")
            if type(spell) is dict
            else None
        )
        provider_locator = _SPELLCASTING_PROVIDER_BY_ID.get(spell_id)
        if provider_locator is None:
            raise TypeError("spellcasting spell identity is invalid")
        authorization = spell.get("repertoireAuthorization")
        if (
            type(authorization) is dict
            and authorization.get("mode")
            == "explicit-repertoire-grant"
        ):
            public_authorization = {
                "mode": "explicit-repertoire-grant",
                "tradition": authorization.get("tradition"),
                "providerTraditions": json.loads(
                    _canonical_json(
                        authorization.get("providerTraditions")
                    )
                ),
                "source": _public_receipt_source(
                    authorization.get("source"),
                    source_id="core-mc1",
                    locator=locator,
                ),
            }
        else:
            public_authorization = json.loads(
                _canonical_json(authorization)
            )
        public_spells.append(
            {
                key: json.loads(_canonical_json(spell.get(key)))
                for key in (
                    "id",
                    "name",
                    "rank",
                    "kind",
                    "actionCost",
                    "rawActionCost",
                    "actionVariants",
                    "traits",
                    "traditions",
                    "compiledEffect",
                    "execution",
                )
            }
            | {
                "repertoireAuthorization": public_authorization,
                "provider": _public_receipt_source(
                    spell.get("source"),
                    source_id="core-pc1",
                    locator=provider_locator,
                )
            }
        )
    rules = value.get("governingRules")
    expected_rules = _spellcasting_rules_for_locator(locator)
    if (
        type(rules) is not list
        or len(rules) != len(expected_rules)
    ):
        raise TypeError("spellcasting governing-rule projection is invalid")
    public_rules: list[dict[str, Any]] = []
    for rule, (rule_id, rule_locator) in zip(
        rules,
        expected_rules,
        strict=True,
    ):
        if type(rule) is not dict or rule.get("id") != rule_id:
            raise TypeError("spellcasting governing-rule identity is invalid")
        public_rules.append(
            {
                "id": rule_id,
                "provider": _public_receipt_source(
                    rule.get("source"),
                    source_id="core-pc1",
                    locator=rule_locator,
                ),
            }
        )
    return {
        "schema": 1,
        "kind": "pf2er-creature-spellcasting-plan",
        "familyId": expected_family_id,
        "compilerId": expected_compiler_id,
        "supportState": "partial-runtime",
        "compileSupported": True,
        "runtimeActivation": json.loads(
            _canonical_json(value["runtimeActivation"])
        ),
        "creatureSource": creature_source,
        "casting": public_casting,
        "spells": public_spells,
        "governingRules": public_rules,
    }


def _bind_spellcasting_compilation_api(
    *,
    validate_selection: Callable[..., Any],
    carrier_select: Callable[..., Any],
    compile_spellcasting: Callable[..., Any],
    serialize_spellcasting: Callable[..., dict[str, Any]],
    compile_prepared_spellcasting: Callable[..., Any],
    serialize_prepared_spellcasting: Callable[..., dict[str, Any]],
) -> tuple[Callable[..., Any], ...]:
    """Capture reviewed creature spell compilers behind an optional plan."""

    def compile_plan(
        authority: _SourceAuthorityAdapter,
        creature_selection: _VerifiedSourceSelection,
        /,
    ) -> CreatureSpellcastingCompilationPlan | None:
        if type(authority) is not _SourceAuthorityAdapter:
            raise TypeError(
                "spellcasting compilation requires an exact "
                "SourceAuthorityAdapter"
            )
        if type(creature_selection) is not _VerifiedSourceSelection:
            raise TypeError(
                "spellcasting compilation requires an exact verified "
                "selection"
            )
        verified = validate_selection(authority, creature_selection)
        block = verified.selected_value
        if (
            type(block) is not _RawSourceObject
            or block is not verified.carrier.raw_block
        ):
            raise _errors.EngineInputError(
                "spellcasting compilation requires one exact creature block"
            )
        if verified.address.source_id != "core-mc1" or (
            verified.address.locator
            not in _SPELLCASTING_CREATURE_LOCATORS
        ):
            return None
        try:
            spellcasting_ordinals = tuple(
                ordinal
                for ordinal, member in enumerate(block.members)
                if member.key.strip() == _SPELLCASTING_FIELD
            )
            if (
                len(spellcasting_ordinals) != 1
                or block.members[
                    spellcasting_ordinals[0]
                ].key != _SPELLCASTING_FIELD
            ):
                raise _errors.EngineInputError(
                    "reviewed caster requires one exact Spellcasting field"
                )
            consumer = validate_selection(
                authority,
                carrier_select(
                    verified.carrier,
                    (
                        _RawMemberStep(
                            _SPELLCASTING_FIELD,
                            spellcasting_ordinals[0],
                        ),
                    ),
                ),
            )
            prepared = (
                verified.address.locator
                in _PREPARED_SPELLCASTING_CREATURE_LOCATORS
            )
            artifact = (
                compile_prepared_spellcasting(consumer, authority)
                if prepared
                else compile_spellcasting(consumer, authority)
            )
            projection = _sanitize_spellcasting_projection(
                (
                    serialize_prepared_spellcasting(artifact)
                    if prepared
                    else serialize_spellcasting(artifact)
                )
            )
            return CreatureSpellcastingCompilationPlan(
                source_id=verified.address.source_id,
                locator=verified.address.locator,
                block_sha256=verified.block_sha256,
                projection_json=_canonical_json(projection),
            )
        except (TypeError, ValueError) as failure:
            raise _family_failure(
                "creature spellcasting",
                failure,
            ) from failure

    def plan_projection(
        plan: CreatureSpellcastingCompilationPlan | None,
        /,
    ) -> dict[str, Any] | None:
        if plan is None:
            return None
        CreatureSpellcastingCompilationPlan.__post_init__(plan)
        return json.loads(plan.projection_json)

    return compile_plan, plan_projection


(
    compile_creature_stat_plan,
    creature_stat_plan_base_value,
    creature_stat_plan_legacy_space,
    creature_stat_plan_projection,
    creature_stat_plan_speeds,
    creature_stat_plan_deferrals,
) = _bind_compilation_api(
    validate_selection=_SourceAuthorityAdapter.validate_selection,
    carrier_select=_VerifiedSourceCarrier.select,
    toc_label=_SourceAuthorityAdapter.toc_label,
    allowed_source_ids=_SourceAuthorityAdapter.allowed_source_ids,
    resolve_rule=_SourceAuthorityAdapter.resolve_rule,
    bind_geometry_rules=_bind_size_space_reach_rules,
    compile_geometry=_compile_size_space_reach,
    serialize_geometry=_SizeSpaceReachPatch.as_serialized,
    bind_movement_rules=_bind_movement_speed_rules,
    bind_movement_inheritance=_bind_movement_inheritance,
    compile_movement=_compile_movement_speeds,
    serialize_movement=_MovementSpeedPatch.as_serialized,
    compile_vision=_compile_and_link_vision_sense,
    compile_special_senses=_compile_sense_collection,
    serialize_special_sense=_SenseCompilerPatch.as_serialized,
    compile_annotated_stat=_compile_annotated_stat,
    serialize_annotated_stat=_CompiledAnnotatedStat.as_serialized,
    conditional_requirements=_conditional_save_requirements,
    compile_conditional_save=_compile_conditional_save,
    serialize_conditional_save=_CompiledConditionalSave.as_serialized,
    compile_damage_defense_profile=_compile_damage_defense_profile,
    serialize_damage_defenses=_serialize_damage_defenses,
    compile_damage_immunities=_compile_damage_immunities,
    serialize_damage_immunities=_DamageImmunityPatch.as_serialized,
)

(
    compile_creature_strike_plan,
    creature_strike_plan_projection,
) = _bind_strike_compilation_api(
    compile_block=_compile_strike_block,
    project_bundle=_project_strike_bundle,
    serialize_projection=_serialize_strike_projection,
)

(
    compile_creature_ability_plan,
    creature_ability_plan_projection,
) = _bind_ability_compilation_api(
    compile_envelopes=_compile_ability_envelopes,
    serialize_envelopes=(
        _CompiledCreatureAbilityEnvelopes.as_serialized
    ),
)

(
    compile_creature_spellcasting_plan,
    creature_spellcasting_plan_projection,
) = _bind_spellcasting_compilation_api(
    validate_selection=_SourceAuthorityAdapter.validate_selection,
    carrier_select=_VerifiedSourceCarrier.select,
    compile_spellcasting=_compile_spontaneous_spellcasting,
    serialize_spellcasting=(
        _CompiledSpontaneousSpellcasting.as_serialized
    ),
    compile_prepared_spellcasting=_compile_prepared_spellcasting,
    serialize_prepared_spellcasting=(
        _CompiledPreparedSpellcasting.as_serialized
    ),
)


__all__ = []

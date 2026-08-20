"""PF2ER semantic compiler composition owned by the TTRPG service.

This module is the production composition table between selected PF2ER books
and the source compiler fragments that TTRPG is allowed to run for them.  It
does not consult the process-global mechanics registry.  Selecting a book
therefore selects an exact, immutable compiler set, and separate compiler sets
can coexist in one process.

``grapples.FRAGMENT`` is carried by the foundation compiler package because
its Constrict grammar is shared by Monster Core and Monster Core 2 and embeds
Player Core basic-save and damage authority.  The actual creature carriers
remain in their respective Monster Core semantic packages.  All other current
families are assigned to the book containing their reviewed carrier grammar;
this table can be split further when a family gains reviewed carriers in more
books.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import MappingProxyType

from .pf2er_compiler.mechanics import (
    afflictions,
    amoeba_abilities,
    animated_construct_armor,
    battle_cry,
    cats_luck,
    conditional_damage,
    conditions,
    ferocity,
    flash_beetle,
    fungus_leshy,
    gaze,
    ghoul,
    giant_ant,
    gnome_bard,
    goblin_song,
    grabbed_strike_activities,
    grapples,
    kobold_tactics,
    plague_zombie_abilities,
    reactive_strike,
    river_drake,
    scarecrow,
    scuttle,
    shield_block,
    stench,
    stride_strike,
    strike_save_control,
    triggered_creature_reactions,
    warg,
    zombie_rot,
)
from .pf2er_compiler.mechanics.contracts import MechanicFamilyFragment
from .pf2er_compiler.mechanics.source_authority import SourceAuthorityAdapter
from .semantic_compiler import (
    SemanticCompilerIdentity,
    SemanticCompilerPackage,
    SemanticCompilerSet,
    build_semantic_compiler_set,
)
from .semantic_package_builder import (
    SemanticDefinitionProjector,
    SemanticPackageBuilderError,
    SourceCreatureTarget,
    build_creature_semantic_package,
)
from .semantic_evidence import SemanticEvidenceStore
from .semantic_packages import (
    CapabilityRequirement,
    ProviderCarrierRelationship,
    SemanticPackage,
    public_definition_acquisition_paths,
)


PF2ER_RULESET_ID = "paizo:pf2er"
PF2ER_SEMANTIC_COMPILER_ID = "ttrpg:pf2er-semantic-compiler"
PF2ER_SEMANTIC_COMPILER_VERSION = "1.0.0"
PF2ER_SEMANTIC_PACKAGE_VERSION = "1.0.0"
PF2ER_EVIDENCE_AUTHORITY_ID = "ttrpg:pf2er-semantic-evidence"
PF2ER_CREATURE_PROJECTION_ID = "ttrpg:pf2er-creature-definition"
PF2ER_CREATURE_PROJECTION_VERSION = "2.0.0"

PF2ER_XULGATH_WARRIOR_ENTITY_ID = "pf2er:xulgath-warrior"
PF2ER_XULGATH_WARRIOR_SOURCE_ID = "core-mc1:352.3"
PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID = (
    "ttrpg:xulgath-warrior-icon-x128"
)
PF2ER_STENCH_LIFECYCLE_CAPABILITY = CapabilityRequirement(
    "gladiator:pf2er-stench-lifecycle",
    "1.0.0",
)
PF2ER_XULGATH_STENCH_RELATIONSHIP = ProviderCarrierRelationship(
    "ttrpg:xulgath-warrior-stench-carrier",
    "pf2er.rule:xulgath-warrior-stench",
    PF2ER_XULGATH_WARRIOR_ENTITY_ID,
)

_PF2ER_SPACE_RULE_REF = "pf2er.rule:size-space-reach"
_PF2ER_STENCH_RULE_REFS = MappingProxyType(
    {
        "aura": "pf2er.rule:aura",
        "duration": "pf2er.rule:duration",
        "emanation": "pf2er.rule:emanation",
        "fortitude": "pf2er.rule:fortitude-save",
        "sickened": "pf2er.rule:sickened",
        "slowed": "pf2er.rule:slowed",
        "stench": "pf2er.rule:xulgath-warrior-stench",
        "traits": "pf2er.rule:traits",
        "turnStart": "pf2er.rule:turn-start",
    }
)
_PF2ER_XULGATH_ITEM_BY_STRIKE_ID = MappingProxyType(
    {
        "strike:club:melee": "pf2er:item.club",
        "strike:club:ranged": "pf2er:item.club",
        "strike:javelin:ranged": "pf2er:item.javelin",
    }
)
_PF2ER_XULGATH_NATURAL_STRIKE_IDS = frozenset(
    ("strike:jaws:melee", "strike:claw:melee")
)

PF2ER_GM_CORE_BOOK_ID = "paizo:gm-core"
PF2ER_PLAYER_CORE_ONE_BOOK_ID = "paizo:player-core-one"
PF2ER_MONSTER_CORE_ONE_BOOK_ID = "paizo:monster-core-one"
PF2ER_MONSTER_CORE_TWO_BOOK_ID = "paizo:monster-core-two"

PF2ER_FOUNDATION_PACKAGE_ID = "ttrpg:pf2er-core-foundation"
PF2ER_MONSTER_CORE_ONE_PACKAGE_ID = "ttrpg:pf2er-monster-core-one"
PF2ER_MONSTER_CORE_TWO_PACKAGE_ID = "ttrpg:pf2er-monster-core-two"

PF2ER_FOUNDATION_BOOK_IDS = (
    PF2ER_GM_CORE_BOOK_ID,
    PF2ER_PLAYER_CORE_ONE_BOOK_ID,
)
PF2ER_FOUNDATION_SOURCE_IDS = (
    "core-gmc",
    "core-pc1",
)


class PF2ERSemanticCompositionError(ValueError):
    """A PF2ER semantic compiler or package selection is invalid."""


# This is the one compiler family whose current reviewed carrier grammar spans
# both creature books.  It is mounted with the mandatory foundation so either
# book can use the same compiler without mounting the other creature book.
PF2ER_FOUNDATION_COMPILER_FRAGMENTS = (
    grapples.FRAGMENT,
)

# These families currently compile reviewed Monster Core 1 carrier shapes.
# Some also cite Player Core governing rules; that provenance does not move the
# carrier compiler out of the book package.
PF2ER_MONSTER_CORE_ONE_COMPILER_FRAGMENTS = (
    conditional_damage.FRAGMENT,
    ferocity.FRAGMENT,
    stride_strike.FRAGMENT,
    gaze.FRAGMENT,
    scuttle.FRAGMENT,
    reactive_strike.FRAGMENT,
    afflictions.FRAGMENT,
    goblin_song.FRAGMENT,
    battle_cry.FRAGMENT,
    fungus_leshy.FRAGMENT,
    river_drake.CAUSTIC_MUCUS_FRAGMENT,
    river_drake.DRACONIC_FRENZY_FRAGMENT,
    river_drake.SPEED_SURGE_FRAGMENT,
    grabbed_strike_activities.FRAGMENT,
    kobold_tactics.CONSTRUCT_TRAP_FRAGMENT,
    triggered_creature_reactions.TAIL_LASH_FRAGMENT,
    triggered_creature_reactions.BITING_SNAKES_FRAGMENT,
    cats_luck.FRAGMENT,
    shield_block.FRAGMENT,
    animated_construct_armor.FRAGMENT,
    gnome_bard.FRAGMENT,
    warg.FRAGMENT,
    giant_ant.FRAGMENT,
    flash_beetle.FRAGMENT,
    scarecrow.FRAGMENT,
    stench.FRAGMENT,
    ghoul.FRAGMENT,
    plague_zombie_abilities.FRAGMENT,
    strike_save_control.FRAGMENT,
    zombie_rot.FRAGMENT,
)

# These families currently compile reviewed Monster Core 2 carrier shapes.
# Shared Constrict compilation is intentionally in the foundation tuple above.
PF2ER_MONSTER_CORE_TWO_COMPILER_FRAGMENTS = (
    conditions.FRAGMENT,
    triggered_creature_reactions.GIANT_CRAB_SCUTTLE_FRAGMENT,
    amoeba_abilities.ENVELOP_FRAGMENT,
)

PF2ER_ALL_COMPILER_FRAGMENTS = (
    *PF2ER_FOUNDATION_COMPILER_FRAGMENTS,
    *PF2ER_MONSTER_CORE_ONE_COMPILER_FRAGMENTS,
    *PF2ER_MONSTER_CORE_TWO_COMPILER_FRAGMENTS,
)

_FOUNDATION_PACKAGE = SemanticCompilerPackage(
    package_id=PF2ER_FOUNDATION_PACKAGE_ID,
    version=PF2ER_SEMANTIC_PACKAGE_VERSION,
    book_ids=PF2ER_FOUNDATION_BOOK_IDS,
)
_MONSTER_CORE_ONE_PACKAGE = SemanticCompilerPackage(
    package_id=PF2ER_MONSTER_CORE_ONE_PACKAGE_ID,
    version=PF2ER_SEMANTIC_PACKAGE_VERSION,
    book_ids=(PF2ER_MONSTER_CORE_ONE_BOOK_ID,),
)
_MONSTER_CORE_TWO_PACKAGE = SemanticCompilerPackage(
    package_id=PF2ER_MONSTER_CORE_TWO_PACKAGE_ID,
    version=PF2ER_SEMANTIC_PACKAGE_VERSION,
    book_ids=(PF2ER_MONSTER_CORE_TWO_BOOK_ID,),
)

_BOOK_COMPILER_FRAGMENTS = MappingProxyType(
    {
        PF2ER_MONSTER_CORE_ONE_BOOK_ID:
            PF2ER_MONSTER_CORE_ONE_COMPILER_FRAGMENTS,
        PF2ER_MONSTER_CORE_TWO_BOOK_ID:
            PF2ER_MONSTER_CORE_TWO_COMPILER_FRAGMENTS,
    }
)
_BOOK_COMPILER_PACKAGES = MappingProxyType(
    {
        PF2ER_MONSTER_CORE_ONE_BOOK_ID: _MONSTER_CORE_ONE_PACKAGE,
        PF2ER_MONSTER_CORE_TWO_BOOK_ID: _MONSTER_CORE_TWO_PACKAGE,
    }
)
PF2ER_CREATURE_SOURCE_BY_BOOK = MappingProxyType(
    {
        PF2ER_MONSTER_CORE_ONE_BOOK_ID: "core-mc1",
        PF2ER_MONSTER_CORE_TWO_BOOK_ID: "core-mc2",
    }
)
PF2ER_CREATURE_BOOK_BY_SOURCE = MappingProxyType(
    {
        source_id: book_id
        for book_id, source_id in PF2ER_CREATURE_SOURCE_BY_BOOK.items()
    }
)

_KNOWN_BOOK_IDS = frozenset(
    (
        *PF2ER_FOUNDATION_BOOK_IDS,
        PF2ER_MONSTER_CORE_ONE_BOOK_ID,
        PF2ER_MONSTER_CORE_TWO_BOOK_ID,
    )
)
_OPTIONAL_BOOK_ORDER = (
    PF2ER_MONSTER_CORE_ONE_BOOK_ID,
    PF2ER_MONSTER_CORE_TWO_BOOK_ID,
)


def _object_with_allowed_keys(
    value: object,
    *,
    allowed: frozenset[str],
    label: str,
) -> dict[str, object]:
    if type(value) is not dict:
        raise SemanticPackageBuilderError(f"{label} must be an object")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SemanticPackageBuilderError(
            f"{label} has unreviewed fields: " + ", ".join(unknown)
        )
    return value


def _string_list(value: object, label: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise SemanticPackageBuilderError(f"{label} must be a string list")
    return list(value)


def _project_pf2er_space(value: object) -> tuple[dict[str, object], set[str]]:
    raw = _object_with_allowed_keys(
        value,
        allowed=frozenset(
            (
                "defaultReachFeet",
                "heightSquares",
                "reachProfile",
                "rule",
                "sizeRank",
                "spaceFeet",
                "widthSquares",
            )
        ),
        label="PF2ER creature space",
    )
    required = {"widthSquares", "heightSquares", "defaultReachFeet"}
    if not required.issubset(raw):
        raise SemanticPackageBuilderError(
            "PF2ER creature space omits required normalized geometry"
        )
    projected = {
        key: raw[key]
        for key in (
            "sizeRank",
            "reachProfile",
            "widthSquares",
            "heightSquares",
            "spaceFeet",
            "defaultReachFeet",
        )
        if key in raw
    }
    rule_refs: set[str] = set()
    if "rule" in raw:
        _object_with_allowed_keys(
            raw["rule"],
            allowed=frozenset(("sourceId", "locator")),
            label="PF2ER creature space rule evidence",
        )
        projected["ruleRef"] = _PF2ER_SPACE_RULE_REF
        rule_refs.add(_PF2ER_SPACE_RULE_REF)
    return projected, rule_refs


def _project_pf2er_damage(value: object, strike_id: str) -> dict[str, object]:
    raw = _object_with_allowed_keys(
        value,
        allowed=frozenset(
            (
                "components",
                "dice",
                "flatAmount",
                "modifier",
                "riderEffects",
                "sourceText",
                "type",
            )
        ),
        label=f"PF2ER {strike_id} damage",
    )
    required = {
        "components",
        "dice",
        "flatAmount",
        "modifier",
        "riderEffects",
        "type",
    }
    if not required.issubset(raw):
        raise SemanticPackageBuilderError(
            f"PF2ER {strike_id} damage omits normalized fields"
        )
    components = raw["components"]
    if type(components) is not list or not components:
        raise SemanticPackageBuilderError(
            f"PF2ER {strike_id} damage components must be nonempty"
        )
    projected_components = []
    for index, component_value in enumerate(components):
        component = _object_with_allowed_keys(
            component_value,
            allowed=frozenset(
                (
                    "dice",
                    "flatAmount",
                    "modifier",
                    "persistent",
                    "sourceAddressSha256",
                    "sourceSpan",
                    "sourceText",
                    "type",
                )
            ),
            label=f"PF2ER {strike_id} damage component {index}",
        )
        component_required = {
            "dice",
            "flatAmount",
            "modifier",
            "persistent",
            "type",
        }
        if not component_required.issubset(component):
            raise SemanticPackageBuilderError(
                f"PF2ER {strike_id} damage component {index} is incomplete"
            )
        projected_components.append(
            {
                key: component[key]
                for key in (
                    "dice",
                    "flatAmount",
                    "modifier",
                    "type",
                    "persistent",
                )
            }
        )
    rider_effects = raw["riderEffects"]
    if rider_effects != []:
        raise SemanticPackageBuilderError(
            f"PF2ER {strike_id} has unreviewed damage rider effects"
        )
    return {
        "dice": raw["dice"],
        "flatAmount": raw["flatAmount"],
        "modifier": raw["modifier"],
        "type": raw["type"],
        "components": projected_components,
        "riderEffects": [],
    }


def _project_pf2er_xulgath_strikes(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        raise SemanticPackageBuilderError("PF2ER creature strikes must be a list")
    expected_ids = set(_PF2ER_XULGATH_ITEM_BY_STRIKE_ID) | set(
        _PF2ER_XULGATH_NATURAL_STRIKE_IDS
    )
    if {
        strike.get("id")
        for strike in value
        if type(strike) is dict
    } != expected_ids or len(value) != len(expected_ids):
        raise SemanticPackageBuilderError(
            "Xulgath Warrior strikes do not match the reviewed five-strike set"
        )
    projected = []
    for strike_value in value:
        strike = _object_with_allowed_keys(
            strike_value,
            allowed=frozenset(
                (
                    "attackModifier",
                    "damage",
                    "followUps",
                    "id",
                    "kind",
                    "maximumRangeIncrements",
                    "name",
                    "rangeIncrementFeet",
                    "reachFeet",
                    "reloadActions",
                    "requiresDrawAfterUse",
                    "sourceAddressSha256",
                    "sourceDeferredDependencies",
                    "sourceOccurrenceId",
                    "traits",
                )
            ),
            label="PF2ER Xulgath Warrior strike",
        )
        strike_id = strike.get("id")
        if type(strike_id) is not str:
            raise SemanticPackageBuilderError(
                "PF2ER Xulgath Warrior strike ID is invalid"
            )
        required = {
            "attackModifier",
            "damage",
            "followUps",
            "id",
            "kind",
            "name",
            "traits",
        }
        if not required.issubset(strike):
            raise SemanticPackageBuilderError(
                f"PF2ER {strike_id} omits normalized strike fields"
            )
        if strike["followUps"] != []:
            raise SemanticPackageBuilderError(
                f"PF2ER {strike_id} has unreviewed follow-up activities"
            )
        item_entity_id = _PF2ER_XULGATH_ITEM_BY_STRIKE_ID.get(strike_id)
        attack_source = (
            {"kind": "item", "itemEntityId": item_entity_id}
            if item_entity_id is not None
            else {"kind": "natural"}
        )
        public_strike = {
            "id": strike_id,
            "name": strike["name"],
            "kind": strike["kind"],
            "attackSource": attack_source,
            "attackModifier": strike["attackModifier"],
            "traits": _string_list(
                strike["traits"], f"PF2ER {strike_id} traits"
            ),
            "damage": _project_pf2er_damage(strike["damage"], strike_id),
            "followUps": [],
        }
        for key in (
            "reachFeet",
            "rangeIncrementFeet",
            "maximumRangeIncrements",
            "reloadActions",
            "requiresDrawAfterUse",
        ):
            if key in strike:
                public_strike[key] = strike[key]
        projected.append(public_strike)
    return projected


def _project_pf2er_stench_duration(value: object) -> dict[str, object]:
    raw = _object_with_allowed_keys(
        value,
        allowed=frozenset(("sourceUnit", "sourceValue", "unit", "value")),
        label="PF2ER Stench duration",
    )
    if set(raw) != {"sourceUnit", "sourceValue", "unit", "value"}:
        raise SemanticPackageBuilderError("PF2ER Stench duration is incomplete")
    return {"unit": raw["unit"], "value": raw["value"]}


def _project_pf2er_stench_outcome(
    value: object,
    outcome: str,
) -> dict[str, object]:
    raw = _object_with_allowed_keys(
        value,
        allowed=frozenset(
            ("condition", "linkedCondition", "temporaryImmunity", "value")
        ),
        label=f"PF2ER Stench {outcome} outcome",
    )
    if "temporaryImmunity" in raw:
        immunity = _object_with_allowed_keys(
            raw["temporaryImmunity"],
            allowed=frozenset(("duration", "family")),
            label=f"PF2ER Stench {outcome} temporary immunity",
        )
        if set(immunity) != {"duration", "family"}:
            raise SemanticPackageBuilderError(
                f"PF2ER Stench {outcome} temporary immunity is incomplete"
            )
        return {
            "temporaryImmunity": {
                "family": immunity["family"],
                "duration": _project_pf2er_stench_duration(immunity["duration"]),
            }
        }
    projected = {
        key: raw[key]
        for key in ("condition", "value")
        if key in raw
    }
    if "linkedCondition" in raw:
        linked = _object_with_allowed_keys(
            raw["linkedCondition"],
            allowed=frozenset(("condition", "value", "while")),
            label=f"PF2ER Stench {outcome} linked condition",
        )
        if set(linked) != {"condition", "value", "while"}:
            raise SemanticPackageBuilderError(
                f"PF2ER Stench {outcome} linked condition is incomplete"
            )
        projected["linkedCondition"] = {
            "condition": linked["condition"],
            "value": linked["value"],
            "while": linked["while"],
        }
    return projected


def _project_pf2er_xulgath_abilities(
    value: object,
) -> tuple[list[dict[str, object]], set[str]]:
    if type(value) is not list or len(value) != 1:
        raise SemanticPackageBuilderError(
            "Xulgath Warrior requires the reviewed Stench ability"
        )
    ability = _object_with_allowed_keys(
        value[0],
        allowed=frozenset(
            (
                "actionCost",
                "deferredMechanics",
                "description",
                "id",
                "kind",
                "mechanic",
                "name",
                "rule",
                "supported",
                "traits",
            )
        ),
        label="PF2ER Xulgath Warrior Stench ability",
    )
    required = {
        "actionCost",
        "deferredMechanics",
        "id",
        "kind",
        "mechanic",
        "name",
        "supported",
        "traits",
    }
    if not required.issubset(ability) or ability.get("id") != "stench":
        raise SemanticPackageBuilderError(
            "Xulgath Warrior Stench ability shape is not reviewed"
        )
    if "rule" in ability:
        _object_with_allowed_keys(
            ability["rule"],
            allowed=frozenset(("sourceId", "locator")),
            label="PF2ER Xulgath Warrior Stench carrier evidence",
        )
    mechanic = _object_with_allowed_keys(
        ability["mechanic"],
        allowed=frozenset(
            (
                "family",
                "geometry",
                "outcomes",
                "rules",
                "savingThrow",
                "triggers",
                "type",
            )
        ),
        label="PF2ER Xulgath Warrior Stench mechanic",
    )
    if set(mechanic) != {
        "family",
        "geometry",
        "outcomes",
        "rules",
        "savingThrow",
        "triggers",
        "type",
    }:
        raise SemanticPackageBuilderError("PF2ER Stench mechanic is incomplete")
    geometry = _object_with_allowed_keys(
        mechanic["geometry"],
        allowed=frozenset(("boundary", "radiusFeet", "type")),
        label="PF2ER Stench geometry",
    )
    saving_throw = _object_with_allowed_keys(
        mechanic["savingThrow"],
        allowed=frozenset(("dc", "type")),
        label="PF2ER Stench saving throw",
    )
    outcomes = _object_with_allowed_keys(
        mechanic["outcomes"],
        allowed=frozenset(
            ("critical-failure", "critical-success", "failure", "success")
        ),
        label="PF2ER Stench outcomes",
    )
    if set(outcomes) != {
        "critical-failure",
        "critical-success",
        "failure",
        "success",
    }:
        raise SemanticPackageBuilderError("PF2ER Stench outcomes are incomplete")
    raw_rules = _object_with_allowed_keys(
        mechanic["rules"],
        allowed=frozenset(_PF2ER_STENCH_RULE_REFS),
        label="PF2ER Stench rule evidence",
    )
    if set(raw_rules) != set(_PF2ER_STENCH_RULE_REFS) or any(
        type(item) is not dict for item in raw_rules.values()
    ):
        raise SemanticPackageBuilderError("PF2ER Stench rule evidence is incomplete")
    rule_refs = set(_PF2ER_STENCH_RULE_REFS.values())
    public_ability = {
        "id": ability["id"],
        "name": ability["name"],
        "kind": ability["kind"],
        "actionCost": ability["actionCost"],
        "traits": _string_list(ability["traits"], "PF2ER Stench traits"),
        "supported": ability["supported"],
        "deferredMechanics": _string_list(
            ability["deferredMechanics"], "PF2ER Stench deferred mechanics"
        ),
        "ruleRef": _PF2ER_STENCH_RULE_REFS["stench"],
        "mechanic": {
            "type": mechanic["type"],
            "family": mechanic["family"],
            "geometry": {
                "type": geometry["type"],
                "radiusFeet": geometry["radiusFeet"],
                "boundary": geometry["boundary"],
            },
            "triggers": _string_list(
                mechanic["triggers"], "PF2ER Stench triggers"
            ),
            "savingThrow": {
                "type": saving_throw["type"],
                "dc": saving_throw["dc"],
            },
            "outcomes": {
                outcome: _project_pf2er_stench_outcome(
                    outcomes[outcome], outcome
                )
                for outcome in (
                    "critical-success",
                    "success",
                    "failure",
                    "critical-failure",
                )
            },
            "ruleRefs": dict(_PF2ER_STENCH_RULE_REFS),
        },
    }
    return [public_ability], rule_refs


def _project_pf2er_creature_definition(
    raw_definition: dict[str, object],
    entity_id: str,
) -> dict[str, object]:
    """Translate reviewed compiler schema 1 into public creature schema 2.

    Every public field is selected and reconstructed here.  Source addresses,
    compiler audit structures, raw prose, and extraction coordinates remain
    solely in the private evidence record and are never recursively scrubbed
    from a copied compiler object.
    """

    raw = _object_with_allowed_keys(
        raw_definition,
        allowed=frozenset(
            (
                "abilities",
                "attributes",
                "defenses",
                "deferredMechanics",
                "icon",
                "id",
                "inventory",
                "languages",
                "level",
                "name",
                "perception",
                "runtimeBlockers",
                "schema",
                "size",
                "skills",
                "source",
                "space",
                "speeds",
                "statCompilation",
                "strikes",
                "traits",
                "unsupportedMechanics",
            )
        ),
        label="PF2ER compiler creature definition",
    )
    if raw.get("schema") != 1:
        raise SemanticPackageBuilderError(
            "PF2ER creature projector requires compiler definition schema 1"
        )
    if "source" in raw:
        _object_with_allowed_keys(
            raw["source"],
            allowed=frozenset(("contentPath", "locator", "sectionId", "sourceId")),
            label="PF2ER creature source evidence",
        )
    if "statCompilation" in raw and type(raw["statCompilation"]) is not dict:
        raise SemanticPackageBuilderError(
            "PF2ER creature stat compilation evidence must be an object"
        )

    required = {
        "abilities",
        "defenses",
        "id",
        "inventory",
        "level",
        "name",
        "schema",
        "space",
    }
    if not required.issubset(raw):
        raise SemanticPackageBuilderError(
            "PF2ER compiler creature definition omits required normalized fields"
        )

    space, rule_refs = _project_pf2er_space(raw["space"])
    is_xulgath = (
        entity_id == PF2ER_XULGATH_WARRIOR_ENTITY_ID
        and raw.get("id") == PF2ER_XULGATH_WARRIOR_SOURCE_ID
        and raw.get("name") == "Xulgath Warrior"
    )
    inventory = raw["inventory"]
    strikes = raw.get("strikes", [])
    abilities = raw["abilities"]
    presentation: dict[str, object] | None = None
    if is_xulgath:
        if inventory != [
            {"name": "club", "quantity": 1, "sourceText": "club"},
            {"name": "javelin", "quantity": 3, "sourceText": "javelin (3)"},
        ]:
            raise SemanticPackageBuilderError(
                "Xulgath Warrior inventory does not match the reviewed item binding"
            )
        public_inventory = [
            {"itemEntityId": "pf2er:item.club", "quantity": 1},
            {"itemEntityId": "pf2er:item.javelin", "quantity": 3},
        ]
        public_strikes = _project_pf2er_xulgath_strikes(strikes)
        public_abilities, ability_rule_refs = (
            _project_pf2er_xulgath_abilities(abilities)
        )
        rule_refs.update(ability_rule_refs)
        if raw.get("icon") != "core/mc1/creatures/x128/Xulgath Warrior":
            raise SemanticPackageBuilderError(
                "Xulgath Warrior icon does not match the reviewed asset binding"
            )
        presentation = {
            "iconAssetId": PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID,
        }
        item_refs = ["pf2er:item.club", "pf2er:item.javelin"]
    else:
        if inventory != [] or strikes != [] or abilities != []:
            raise SemanticPackageBuilderError(
                "PF2ER creature has executable fields without a reviewed semantic projection"
            )
        if "icon" in raw:
            raise SemanticPackageBuilderError(
                "PF2ER creature icon lacks a reviewed opaque asset binding"
            )
        public_inventory = []
        public_strikes = []
        public_abilities = []
        item_refs = []

    defenses = _object_with_allowed_keys(
        raw["defenses"],
        allowed=frozenset(
            (
                "armorClass",
                "fortitude",
                "immunities",
                "maximumHitPoints",
                "reflex",
                "resistances",
                "weaknesses",
                "will",
            )
        ),
        label="PF2ER creature defenses",
    )
    if "maximumHitPoints" not in defenses:
        raise SemanticPackageBuilderError(
            "PF2ER creature defenses omit maximum hit points"
        )
    public_defenses = {
        key: defenses[key]
        for key in (
            "armorClass",
            "fortitude",
            "reflex",
            "will",
            "maximumHitPoints",
            "immunities",
            "weaknesses",
            "resistances",
        )
        if key in defenses
    }

    projected: dict[str, object] = {
        "schema": 2,
        "kind": "pf2er-creature",
        "id": entity_id,
        "name": raw["name"],
        "level": raw["level"],
        "space": space,
        "defenses": public_defenses,
        "inventory": public_inventory,
        "strikes": public_strikes,
        "abilities": public_abilities,
        "references": {
            "rules": sorted(rule_refs),
            "items": item_refs,
        },
    }
    for key in ("size",):
        if key in raw:
            projected[key] = raw[key]
    for key in (
        "traits",
        "languages",
        "deferredMechanics",
        "runtimeBlockers",
        "unsupportedMechanics",
    ):
        if key in raw:
            projected[key] = _string_list(raw[key], f"PF2ER creature {key}")
    if "attributes" in raw:
        attributes = _object_with_allowed_keys(
            raw["attributes"],
            allowed=frozenset(
                (
                    "charisma",
                    "constitution",
                    "dexterity",
                    "intelligence",
                    "strength",
                    "wisdom",
                )
            ),
            label="PF2ER creature attributes",
        )
        projected["attributes"] = {
            key: attributes[key]
            for key in (
                "strength",
                "dexterity",
                "constitution",
                "intelligence",
                "wisdom",
                "charisma",
            )
            if key in attributes
        }
    if "perception" in raw:
        perception = _object_with_allowed_keys(
            raw["perception"],
            allowed=frozenset(("modifier", "senses")),
            label="PF2ER creature perception",
        )
        projected["perception"] = {
            "modifier": perception["modifier"],
            "senses": _string_list(
                perception["senses"], "PF2ER creature senses"
            ),
        }
    if "skills" in raw:
        if type(raw["skills"]) is not list:
            raise SemanticPackageBuilderError("PF2ER creature skills must be a list")
        public_skills = []
        for skill_value in raw["skills"]:
            skill = _object_with_allowed_keys(
                skill_value,
                allowed=frozenset(("modifier", "name")),
                label="PF2ER creature skill",
            )
            if set(skill) != {"modifier", "name"}:
                raise SemanticPackageBuilderError("PF2ER creature skill is incomplete")
            public_skills.append(
                {"name": skill["name"], "modifier": skill["modifier"]}
            )
        projected["skills"] = public_skills
    if "speeds" in raw:
        speeds = _object_with_allowed_keys(
            raw["speeds"],
            allowed=frozenset(("land",)),
            label="PF2ER creature speeds",
        )
        projected["speeds"] = {
            "land": speeds["land"],
        }
    if presentation is not None:
        projected["presentation"] = presentation

    paths = public_definition_acquisition_paths(projected)
    if paths:
        raise SemanticPackageBuilderError(
            "PF2ER projector emitted acquisition-only fields: "
            + ", ".join(paths)
        )
    return projected


_BOOK_DEFINITION_PROJECTORS = MappingProxyType(
    {
        book_id: SemanticDefinitionProjector(
            package_id=package.package_id,
            package_version=package.version,
            projection_id=PF2ER_CREATURE_PROJECTION_ID,
            projection_version=PF2ER_CREATURE_PROJECTION_VERSION,
            definition_schema=2,
            project_creature=_project_pf2er_creature_definition,
        )
        for book_id, package in _BOOK_COMPILER_PACKAGES.items()
    }
)


def _selected_book_ids(book_ids: tuple[str, ...]) -> frozenset[str]:
    if not isinstance(book_ids, tuple) or any(
        type(book_id) is not str for book_id in book_ids
    ):
        raise PF2ERSemanticCompositionError(
            "PF2ER selected book IDs must be a tuple of strings"
        )
    if len(set(book_ids)) != len(book_ids):
        raise PF2ERSemanticCompositionError(
            "PF2ER selected book IDs contain duplicates"
        )
    unknown = sorted(set(book_ids) - _KNOWN_BOOK_IDS)
    if unknown:
        raise PF2ERSemanticCompositionError(
            "unsupported PF2ER book selection: " + ", ".join(unknown)
        )
    return frozenset((*PF2ER_FOUNDATION_BOOK_IDS, *book_ids))


def build_pf2er_semantic_compiler_set(
    *,
    book_ids: tuple[str, ...] = (),
) -> SemanticCompilerSet:
    """Build one compiler set from the mandatory foundation and selected books."""

    selected = _selected_book_ids(book_ids)
    packages = [_FOUNDATION_PACKAGE]
    fragments: list[MechanicFamilyFragment] = list(
        PF2ER_FOUNDATION_COMPILER_FRAGMENTS
    )
    for book_id in _OPTIONAL_BOOK_ORDER:
        if book_id not in selected:
            continue
        packages.append(_BOOK_COMPILER_PACKAGES[book_id])
        fragments.extend(_BOOK_COMPILER_FRAGMENTS[book_id])
    return build_semantic_compiler_set(
        identity=SemanticCompilerIdentity(
            compiler_id=PF2ER_SEMANTIC_COMPILER_ID,
            compiler_version=PF2ER_SEMANTIC_COMPILER_VERSION,
            ruleset_id=PF2ER_RULESET_ID,
            packages=tuple(packages),
        ),
        fragments=tuple(fragments),
    )


def build_pf2er_creature_compiler_set_for_source(
    *,
    source_id: str,
    selected_source_ids: tuple[str, ...],
) -> SemanticCompilerSet:
    """Bind one selected raw creature source to its exact book compiler set.

    This is the narrow hard-cut adapter for the existing source-addressed
    battleground API.  Even when both Monster Core sources are selected, each
    creature is compiled with only its own book plus the mandatory foundation;
    compiler families from the other creature book are never mixed into the
    call.
    """

    if type(source_id) is not str:
        raise PF2ERSemanticCompositionError(
            "PF2ER creature compiler source must be one exact source ID"
        )
    book_id = PF2ER_CREATURE_BOOK_BY_SOURCE.get(source_id)
    if book_id is None:
        raise PF2ERSemanticCompositionError(
            f"unsupported PF2ER creature compiler source: {source_id}"
        )
    if not isinstance(selected_source_ids, tuple) or any(
        type(selected) is not str for selected in selected_source_ids
    ):
        raise PF2ERSemanticCompositionError(
            "PF2ER selected source IDs must be a tuple of strings"
        )
    if len(set(selected_source_ids)) != len(selected_source_ids):
        raise PF2ERSemanticCompositionError(
            "PF2ER selected source IDs contain duplicates"
        )
    selected = frozenset(selected_source_ids)
    missing_foundation = sorted(
        set(PF2ER_FOUNDATION_SOURCE_IDS) - selected
    )
    if missing_foundation:
        raise PF2ERSemanticCompositionError(
            "PF2ER selected sources omit foundation sources: "
            + ", ".join(missing_foundation)
        )
    if source_id not in selected:
        raise PF2ERSemanticCompositionError(
            f"PF2ER creature compiler source is not selected: {source_id}"
        )
    return build_pf2er_semantic_compiler_set(book_ids=(book_id,))


def _require_exact_pf2er_compiler_set(
    compiler_set: SemanticCompilerSet,
) -> None:
    if type(compiler_set) is not SemanticCompilerSet:
        raise TypeError(
            "PF2ER creature package requires SemanticCompilerSet"
        )
    packages = compiler_set.identity.packages
    allowed_packages = {
        _FOUNDATION_PACKAGE,
        _MONSTER_CORE_ONE_PACKAGE,
        _MONSTER_CORE_TWO_PACKAGE,
    }
    if _FOUNDATION_PACKAGE not in packages or any(
        package not in allowed_packages for package in packages
    ):
        raise PF2ERSemanticCompositionError(
            "PF2ER compiler set is not an exact production composition"
        )
    selected_book_ids = tuple(
        book_id
        for book_id in _OPTIONAL_BOOK_ORDER
        if _BOOK_COMPILER_PACKAGES[book_id] in packages
    )
    expected = build_pf2er_semantic_compiler_set(
        book_ids=selected_book_ids
    )
    if (
        compiler_set.digest != expected.digest
        or compiler_set.canonical_manifest()
        != expected.canonical_manifest()
    ):
        raise PF2ERSemanticCompositionError(
            "PF2ER compiler set is not an exact production composition"
        )


def _require_xulgath_stench_capability_binding(
    creatures: Sequence[SourceCreatureTarget],
    relationships: Sequence[ProviderCarrierRelationship],
) -> None:
    """Require Xulgath's reviewed binding to the reusable Stench contract.

    The semantic builder never infers this requirement from the creature name
    or from the presence of a Stench-shaped ability.  Publication review must
    supply the exact capability and provider/carrier link explicitly.  The
    capability contract is reusable by later Stench carriers; only this
    provider/carrier relationship is specific to Xulgath Warrior.
    """

    xulgath_target = next(
        (
            target
            for target in creatures
            if target.entity_id == PF2ER_XULGATH_WARRIOR_ENTITY_ID
        ),
        None,
    )
    related_stench_links = tuple(
        relationship
        for relationship in relationships
        if (
            relationship.provider_entity_id
            == PF2ER_XULGATH_STENCH_RELATIONSHIP.provider_entity_id
            or relationship.carrier_entity_id
            == PF2ER_XULGATH_WARRIOR_ENTITY_ID
        )
    )
    if xulgath_target is None:
        if related_stench_links:
            raise PF2ERSemanticCompositionError(
                "the Xulgath Stench relationship requires its exact carrier"
            )
        return

    if xulgath_target.required_capabilities != (
        PF2ER_STENCH_LIFECYCLE_CAPABILITY,
    ):
        raise PF2ERSemanticCompositionError(
            "Xulgath Warrior requires exactly the reviewed Stench lifecycle "
            "capability"
        )
    if related_stench_links != (PF2ER_XULGATH_STENCH_RELATIONSHIP,):
        raise PF2ERSemanticCompositionError(
            "Xulgath Warrior requires exactly the reviewed Stench "
            "provider/carrier relationship"
        )


def build_pf2er_creature_semantic_package(
    *,
    authority: SourceAuthorityAdapter,
    compiler_set: SemanticCompilerSet,
    book_id: str,
    ruleset_digest: str,
    book_digest: str,
    semantic_generation: str,
    creatures: Sequence[SourceCreatureTarget],
    evidence_store: SemanticEvidenceStore,
    relationships: Sequence[ProviderCarrierRelationship] = (),
) -> SemanticPackage:
    """Compile and seal one selected PF2ER creature book package."""

    _require_exact_pf2er_compiler_set(compiler_set)
    package = _BOOK_COMPILER_PACKAGES.get(book_id)
    projector = _BOOK_DEFINITION_PROJECTORS.get(book_id)
    source_id = PF2ER_CREATURE_SOURCE_BY_BOOK.get(book_id)
    if package is None or projector is None or source_id is None:
        raise PF2ERSemanticCompositionError(
            "PF2ER creature package requires a supported creature book"
        )
    if not isinstance(creatures, (tuple, list)) or any(
        not isinstance(target, SourceCreatureTarget)
        for target in creatures
    ):
        raise PF2ERSemanticCompositionError(
            "PF2ER creature targets must be SourceCreatureTarget values"
        )
    wrong_sources = sorted(
        {
            target.source_id
            for target in creatures
            if target.source_id != source_id
        }
    )
    if wrong_sources:
        raise PF2ERSemanticCompositionError(
            f"{book_id} creature targets must use source {source_id}"
        )
    _require_xulgath_stench_capability_binding(creatures, relationships)
    return build_creature_semantic_package(
        authority=authority,
        compiler_set=compiler_set,
        package_id=package.package_id,
        version=package.version,
        ruleset_digest=ruleset_digest,
        book_id=book_id,
        book_digest=book_digest,
        semantic_generation=semantic_generation,
        creatures=creatures,
        projector=projector,
        evidence_authority_id=PF2ER_EVIDENCE_AUTHORITY_ID,
        evidence_store=evidence_store,
        relationships=relationships,
    )


__all__ = [
    "PF2ER_ALL_COMPILER_FRAGMENTS",
    "PF2ER_CREATURE_BOOK_BY_SOURCE",
    "PF2ER_CREATURE_SOURCE_BY_BOOK",
    "PF2ER_FOUNDATION_SOURCE_IDS",
    "PF2ER_EVIDENCE_AUTHORITY_ID",
    "PF2ER_CREATURE_PROJECTION_ID",
    "PF2ER_CREATURE_PROJECTION_VERSION",
    "PF2ER_FOUNDATION_BOOK_IDS",
    "PF2ER_FOUNDATION_COMPILER_FRAGMENTS",
    "PF2ER_FOUNDATION_PACKAGE_ID",
    "PF2ER_GM_CORE_BOOK_ID",
    "PF2ER_MONSTER_CORE_ONE_BOOK_ID",
    "PF2ER_MONSTER_CORE_ONE_COMPILER_FRAGMENTS",
    "PF2ER_MONSTER_CORE_ONE_PACKAGE_ID",
    "PF2ER_MONSTER_CORE_TWO_BOOK_ID",
    "PF2ER_MONSTER_CORE_TWO_COMPILER_FRAGMENTS",
    "PF2ER_MONSTER_CORE_TWO_PACKAGE_ID",
    "PF2ER_PLAYER_CORE_ONE_BOOK_ID",
    "PF2ER_RULESET_ID",
    "PF2ER_SEMANTIC_COMPILER_ID",
    "PF2ER_SEMANTIC_COMPILER_VERSION",
    "PF2ER_SEMANTIC_PACKAGE_VERSION",
    "PF2ER_STENCH_LIFECYCLE_CAPABILITY",
    "PF2ER_XULGATH_STENCH_RELATIONSHIP",
    "PF2ER_XULGATH_WARRIOR_ENTITY_ID",
    "PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID",
    "PF2ER_XULGATH_WARRIOR_SOURCE_ID",
    "PF2ERSemanticCompositionError",
    "build_pf2er_creature_compiler_set_for_source",
    "build_pf2er_creature_semantic_package",
    "build_pf2er_semantic_compiler_set",
]

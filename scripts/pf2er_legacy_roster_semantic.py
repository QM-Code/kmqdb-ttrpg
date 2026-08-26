"""Source-free persistence publication for Karmak's legacy PF2ER roster.

The roster is review authority for reconnecting the private source selections,
but it is not evidence that every executable mechanic has been reviewed for the
current Gladiator runtime.  This package therefore publishes only inert,
source-free creature identity and descriptive/statistical fields.  Every entity
is explicitly runtime-blocked and carries no inventory, strikes, or abilities.
Each entity carries exact generic source prose, one bounded opaque x128
thumbnail, and one opaque x512 viewer portrait for direct stable display.  It
is suitable for durable stable persistence and display, never for encounter
admission.

Hadrosaurid, Viper, and Xulgath Warrior are intentionally absent.  Their
existing reviewed semantic publication lanes own those identities.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac
from types import MappingProxyType
from typing import Any, Mapping

from subdomains.ttrpg.pf2er_compiler.mechanics.source_authority import (
    SourceAuthorityAdapter,
)
from subdomains.ttrpg.pf2er_compiler.source import source_creature_description
from subdomains.ttrpg.semantic_compiler import SemanticCompilerSet
from subdomains.ttrpg.semantic_evidence import (
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
    canonical_digest,
)
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    SemanticPackage,
    build_semantic_entity,
    build_semantic_package,
    public_definition_acquisition_paths,
    validate_public_semantic_definition,
)
from subdomains.ttrpg.pf2er_semantic import (
    PF2ER_MONSTER_CORE_ONE_BOOK_ID,
    PF2ER_RULESET_ID,
    build_pf2er_semantic_compiler_set,
)


PF2ER_LEGACY_ROSTER_PACKAGE_ID = (
    "ttrpg:pf2er-monster-core-one-legacy-roster"
)
PF2ER_LEGACY_ROSTER_PACKAGE_VERSION = "1.2.0"
PF2ER_LEGACY_ROSTER_SEMANTIC_GENERATION = (
    "ttrpg:pf2er-monster-core-one-legacy-roster-publication-3"
)
PF2ER_LEGACY_ROSTER_EVIDENCE_AUTHORITY_ID = (
    "ttrpg:pf2er-legacy-roster-semantic-evidence"
)
PF2ER_LEGACY_ROSTER_PROJECTION_ID = (
    "ttrpg:pf2er-legacy-roster-persistence-definition"
)
PF2ER_LEGACY_ROSTER_PROJECTION_VERSION = "3.0.0"
PF2ER_LEGACY_ROSTER_SOURCE_ID = "core-mc1"
PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER = "x128"
PF2ER_LEGACY_ROSTER_VIEWER_TIER = "x512"
PF2ER_LEGACY_ROSTER_AUTHORITY_DIGEST = (
    "686577b44c5a208e37dbb07a0fe1fca80aea283fd9fd9d67be640d43a93685ef"
)
PF2ER_LEGACY_ROSTER_RULESET_DIGEST = (
    "937849e4ebd85246f3524c9ffbdf110cafb0c34d9cc93f20ac27d6e24fd6b5e4"
)
PF2ER_LEGACY_ROSTER_BOOK_DIGEST = (
    "24c1e4ec306a523096a86416e35974558585bfec7abdfc3b4fc6a7a397b84abd"
)
PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER = (
    "semantic-publication:legacy-roster-executable-definition-unreviewed"
)

_EXPECTED_AUTHORITY_SCOPE = ("core-gmc", "core-mc1", "core-pc1")
_EXECUTABLE_MARKERS = MappingProxyType(
    {
        "inventory": "legacy-roster:inventory-semantics-unpublished",
        "strikes": "legacy-roster:strike-semantics-unpublished",
        "abilities": "legacy-roster:ability-semantics-unpublished",
    }
)
_DEFENSE_MARKERS = MappingProxyType(
    {
        "immunities": "legacy-roster:defense-immunities-unpublished",
        "weaknesses": "legacy-roster:defense-weaknesses-unpublished",
        "resistances": "legacy-roster:defense-resistances-unpublished",
    }
)
_PROJECTION_MANIFEST = {
    "schema": 1,
    "packageId": PF2ER_LEGACY_ROSTER_PACKAGE_ID,
    "packageVersion": PF2ER_LEGACY_ROSTER_PACKAGE_VERSION,
    "projectionId": PF2ER_LEGACY_ROSTER_PROJECTION_ID,
    "projectionVersion": PF2ER_LEGACY_ROSTER_PROJECTION_VERSION,
    "definitionSchema": 2,
    "entityKind": "ttrpg:creature",
    "executionPolicy": "persistence-only-runtime-blocked",
    "presentationPolicy": {
        "kind": "opaque-direct-use-thumbnail-and-viewer-portrait",
        "thumbnailTier": PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER,
        "viewerTier": PF2ER_LEGACY_ROSTER_VIEWER_TIER,
    },
    "descriptionPolicy": "exact-generic-source-prose",
}
PF2ER_LEGACY_ROSTER_PROJECTION_DIGEST = canonical_digest(
    _PROJECTION_MANIFEST,
    "PF2ER legacy roster projection manifest",
)


class PF2ERLegacyRosterSemanticError(ValueError):
    """The reviewed roster input, source reconnection, or projection drifted."""


@dataclass(frozen=True, order=True, slots=True)
class LegacyRosterTarget:
    """One approved legacy address reconnected to a current private target."""

    entity_id: str
    name: str
    legacy_locator: str
    current_locator: str

    @property
    def legacy_source_address(self) -> str:
        return f"{PF2ER_LEGACY_ROSTER_SOURCE_ID}:{self.legacy_locator}"

    @property
    def thumbnail_asset_id(self) -> str:
        return pf2er_roster_portrait_asset_id(
            self.entity_id,
            PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER,
        )

    @property
    def viewer_asset_id(self) -> str:
        return pf2er_roster_portrait_asset_id(
            self.entity_id,
            PF2ER_LEGACY_ROSTER_VIEWER_TIER,
        )


def pf2er_roster_portrait_asset_id(entity_id: str, tier: str) -> str:
    """Return the opaque direct-use roster portrait ID for one creature."""

    if type(entity_id) is not str or not entity_id.startswith("pf2er:"):
        raise PF2ERLegacyRosterSemanticError(
            "roster portrait entity ID must be in the pf2er namespace"
        )
    local_id = entity_id.removeprefix("pf2er:")
    if not local_id:
        raise PF2ERLegacyRosterSemanticError(
            "roster portrait entity ID must have a local component"
        )
    if tier not in {
        PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER,
        PF2ER_LEGACY_ROSTER_VIEWER_TIER,
    }:
        raise PF2ERLegacyRosterSemanticError(
            "roster portrait tier is not published"
        )
    return f"ttrpg:{local_id}-icon-{tier}"


PF2ER_LEGACY_ROSTER_TARGETS = (
    LegacyRosterTarget("pf2er:arbiter", "Arbiter", "8.4", "8.4"),
    LegacyRosterTarget("pf2er:axiomite", "Axiomite", "9.1", "9.1"),
    LegacyRosterTarget("pf2er:akhana", "Akhana", "9.3", "9.3"),
    LegacyRosterTarget("pf2er:animated-armor", "Animated Armor", "18.5", "18.5"),
    LegacyRosterTarget("pf2er:gorilla", "Gorilla", "23.3", "23.3"),
    LegacyRosterTarget("pf2er:megaprimatus", "Megaprimatus", "23.5", "23.5"),
    LegacyRosterTarget("pf2er:basilisk", "Basilisk", "39.1", "39.1"),
    LegacyRosterTarget("pf2er:cave-bear", "Cave Bear", "41.5", "41.5"),
    LegacyRosterTarget("pf2er:flash-beetle", "Flash Beetle", "42.4", "42.4"),
    LegacyRosterTarget("pf2er:giant-stag-beetle", "Giant Stag Beetle", "42.6", "42.6"),
    LegacyRosterTarget("pf2er:boar", "Boar", "43.3", "43.3"),
    LegacyRosterTarget("pf2er:daeodon", "Daeodon", "43.6", "43.6"),
    LegacyRosterTarget("pf2er:leopard", "Leopard", "50.3", "50.3"),
    LegacyRosterTarget("pf2er:lion", "Lion", "50.5", "50.5"),
    LegacyRosterTarget("pf2er:tiger", "Tiger", "51.2", "51.2"),
    LegacyRosterTarget("pf2er:smilodon", "Smilodon", "51.4", "51.4"),
    LegacyRosterTarget("pf2er:catfolk-pouncer", "Catfolk Pouncer", "52.2", "52.2"),
    LegacyRosterTarget("pf2er:chimera", "Chimera", "62.1", "62.1"),
    LegacyRosterTarget("pf2er:crawling-hand", "Crawling Hand", "68.2", "68.2"),
    LegacyRosterTarget("pf2er:cyclops", "Cyclops", "70.3", "70.3"),
    LegacyRosterTarget("pf2er:dero-magister", "Dero Magister", "85.3", "85.3"),
    LegacyRosterTarget("pf2er:velociraptor", "Velociraptor", "96.5", "96.5"),
    LegacyRosterTarget("pf2er:pachycephalosaurus", "Pachycephalosaurus", "97.4", "97.4"),
    LegacyRosterTarget("pf2er:ankylosaurus", "Ankylosaurus", "98.4", "98.4"),
    LegacyRosterTarget("pf2er:stegosaurus", "Stegosaurus", "99.3", "99.3"),
    LegacyRosterTarget("pf2er:triceratops", "Triceratops", "99.5", "99.5"),
    LegacyRosterTarget("pf2er:brontosaurus", "Brontosaurus", "100.3", "100.3"),
    LegacyRosterTarget("pf2er:tyrannosaurus", "Tyrannosaurus", "101.2", "101.2"),
    LegacyRosterTarget("pf2er:guard-dog", "Guard Dog", "102.2", "102.2"),
    LegacyRosterTarget("pf2er:riding-dog", "Riding Dog", "102.4", "102.4"),
    LegacyRosterTarget("pf2er:young-fortune-dragon", "Young Fortune Dragon", "117.2", "117.2"),
    LegacyRosterTarget("pf2er:young-mirage-dragon", "Young Mirage Dragon", "122.1", "122.1"),
    LegacyRosterTarget("pf2er:adult-mirage-dragon", "Adult Mirage Dragon", "122.2", "122.2"),
    LegacyRosterTarget("pf2er:ancient-mirage-dragon", "Ancient Mirage Dragon", "123.2", "123.2"),
    LegacyRosterTarget("pf2er:young-omen-dragon", "Young Omen Dragon", "124.1", "124.1"),
    LegacyRosterTarget("pf2er:adult-omen-dragon", "Adult Omen Dragon", "124.2", "124.2"),
    LegacyRosterTarget("pf2er:ancient-omen-dragon", "Ancient Omen Dragon", "125.2", "125.2"),
    LegacyRosterTarget("pf2er:river-drake", "River Drake", "129.1", "129.1"),
    LegacyRosterTarget("pf2er:dwarf-warrior", "Dwarf Warrior", "135.2", "135.2"),
    LegacyRosterTarget("pf2er:dwarf-stonecaster", "Dwarf Stonecaster", "135.4", "135.4"),
    LegacyRosterTarget("pf2er:zephyr-hawk", "Zephyr Hawk", "140.2", "140.2"),
    LegacyRosterTarget("pf2er:living-whirlwind", "Living Whirlwind", "140.4", "140.4"),
    LegacyRosterTarget("pf2er:air-scamp", "Air Scamp", "146.2", "146.2"),
    LegacyRosterTarget("pf2er:earth-scamp", "Earth Scamp", "146.4", "146.4"),
    LegacyRosterTarget("pf2er:fire-scamp", "Fire Scamp", "147.1", "147.1"),
    LegacyRosterTarget("pf2er:water-scamp", "Water Scamp", "147.3", "147.3"),
    LegacyRosterTarget("pf2er:brine-shark", "Brine Shark", "148.2", "148.2"),
    LegacyRosterTarget("pf2er:elemental-tsunami", "Elemental Tsunami", "149.2", "149.2"),
    LegacyRosterTarget("pf2er:aiuvarin-elementalist", "Aiuvarin Elementalist", "151.4", "151.4"),
    LegacyRosterTarget("pf2er:ghoul-stalker", "Ghoul Stalker", "163.1", "163.1"),
    LegacyRosterTarget("pf2er:ghoul-soldier", "Ghoul Soldier", "163.3", "163.3"),
    LegacyRosterTarget("pf2er:gnome-bard", "Gnome Bard", "172.2", "172.2"),
    LegacyRosterTarget("pf2er:umbral-gnome-warrior", "Umbral Gnome Warrior", "173.1", "173.1"),
    LegacyRosterTarget("pf2er:goblin-warrior", "Goblin Warrior", "174.2", "174.2"),
    LegacyRosterTarget("pf2er:goblin-commando", "Goblin Commando", "174.4", "174.4"),
    LegacyRosterTarget("pf2er:goblin-pyro", "Goblin Pyro", "175.1", "175.1"),
    LegacyRosterTarget("pf2er:goblin-war-chanter", "Goblin War Chanter", "175.3", "175.3"),
    LegacyRosterTarget("pf2er:goblin-dog", "Goblin Dog", "176.1", "176.1"),
    LegacyRosterTarget("pf2er:griffon", "Griffon", "182.1", "182.1"),
    LegacyRosterTarget("pf2er:harpy", "Harpy", "193.1", "193.1"),
    LegacyRosterTarget("pf2er:hell-hound", "Hell Hound", "194.2", "194.2"),
    LegacyRosterTarget("pf2er:hippogriff", "Hippogriff", "197.1", "197.1"),
    LegacyRosterTarget("pf2er:homunculus", "Homunculus", "200.1", "200.1"),
    LegacyRosterTarget("pf2er:hyena", "Hyena", "205.2", "205.2"),
    LegacyRosterTarget("pf2er:kobold-warrior", "Kobold Warrior", "210.2", "210.2"),
    LegacyRosterTarget("pf2er:kobold-scout", "Kobold Scout", "210.4", "210.4"),
    LegacyRosterTarget("pf2er:kobold-cavern-mage", "Kobold Cavern Mage", "211.2", "211.2"),
    LegacyRosterTarget("pf2er:gourd-leshy", "Gourd Leshy", "216.4", "216.4"),
    LegacyRosterTarget("pf2er:fungus-leshy", "Fungus Leshy", "217.2", "217.2"),
    LegacyRosterTarget("pf2er:manticore", "Manticore", "228.1", "228.1"),
    LegacyRosterTarget("pf2er:giant-mantis", "Giant Mantis", "229.2", "229.2"),
    LegacyRosterTarget("pf2er:giant-octopus", "Giant Octopus", "248.1", "248.1"),
    LegacyRosterTarget("pf2er:orc-scrapper", "Orc Scrapper", "258.2", "258.2"),
    LegacyRosterTarget("pf2er:orc-commander", "Orc Commander", "259.3", "259.3"),
    LegacyRosterTarget("pf2er:pegasus", "Pegasus", "261.1", "261.1"),
    LegacyRosterTarget("pf2er:pteranodon", "Pteranodon", "278.3", "278.3"),
    LegacyRosterTarget("pf2er:giant-rat", "Giant Rat", "288.2", "288.2"),
    LegacyRosterTarget("pf2er:reefclaw", "Reefclaw", "291.1", "291.1"),
    LegacyRosterTarget("pf2er:rhinoceros", "Rhinoceros", "293.2", "293.2"),
    LegacyRosterTarget("pf2er:scarecrow", "Scarecrow", "297.1", "297.1"),
    LegacyRosterTarget("pf2er:great-white-shark", "Great White Shark", "307.2", "307.2"),
    LegacyRosterTarget("pf2er:skeleton-guard", "Skeleton Guard", "312.2", "312.4"),
    LegacyRosterTarget("pf2er:skeletal-champion", "Skeletal Champion", "312.4", "312.6"),
    LegacyRosterTarget("pf2er:skeletal-horse", "Skeletal Horse", "313.1", "313.1"),
    LegacyRosterTarget("pf2er:skeletal-hulk", "Skeletal Hulk", "313.5", "313.6"),
    LegacyRosterTarget("pf2er:warg", "Warg", "341.2", "341.2"),
    LegacyRosterTarget("pf2er:wolf", "Wolf", "350.2", "350.2"),
    LegacyRosterTarget("pf2er:zombie-shambler", "Zombie Shambler", "356.4", "356.4"),
    LegacyRosterTarget("pf2er:plague-zombie", "Plague Zombie", "356.6", "356.6"),
    LegacyRosterTarget("pf2er:zombie-brute", "Zombie Brute", "357.2", "357.2"),
    LegacyRosterTarget("pf2er:zombie-hulk", "Zombie Hulk", "357.4", "357.4"),
)


def _object(value: object, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise PF2ERLegacyRosterSemanticError(f"{label} must be an object")
    return value


def _string_list(value: object, label: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise PF2ERLegacyRosterSemanticError(f"{label} must be a string list")
    return list(value)


def _selected_object(
    value: object,
    keys: tuple[str, ...],
    label: str,
) -> dict[str, object]:
    packet = _object(value, label)
    return {key: packet[key] for key in keys if key in packet}


def _project_persistence_definition(
    raw_definition: dict[str, object],
    target: LegacyRosterTarget,
    description: str,
) -> dict[str, object]:
    raw = _object(raw_definition, "legacy roster compiler definition")
    if raw.get("schema") != 1 or raw.get("name") != target.name:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster source reconnection drifted: {target.legacy_source_address}"
        )
    required = {"abilities", "defenses", "inventory", "level", "space", "strikes"}
    if not required.issubset(raw):
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster compiler definition is incomplete: {target.entity_id}"
        )
    if type(description) is not str or not description:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster creature description is empty: {target.entity_id}"
        )

    defenses = _object(raw["defenses"], "legacy roster creature defenses")
    unsupported = [
        marker
        for field, marker in _EXECUTABLE_MARKERS.items()
        if raw[field]
    ]
    unsupported.extend(
        marker
        for field, marker in _DEFENSE_MARKERS.items()
        if defenses.get(field)
    )
    if not unsupported:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster entity unexpectedly has no executable fields: {target.entity_id}"
        )

    projected: dict[str, object] = {
        "schema": 2,
        "kind": "pf2er-creature",
        "id": target.entity_id,
        "name": target.name,
        "description": description,
        "level": raw["level"],
        "space": _selected_object(
            raw["space"],
            (
                "widthSquares",
                "heightSquares",
                "defaultReachFeet",
                "spaceFeet",
                "sizeRank",
                "reachProfile",
            ),
            "legacy roster creature space",
        ),
        "defenses": {
            **_selected_object(
                defenses,
                (
                    "armorClass",
                    "fortitude",
                    "reflex",
                    "will",
                    "maximumHitPoints",
                ),
                "legacy roster creature defenses",
            ),
            "immunities": [],
            "weaknesses": [],
            "resistances": [],
        },
        "inventory": [],
        "strikes": [],
        "abilities": [],
        "references": {"rules": [], "items": []},
        "runtimeBlockers": [PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER],
        "unsupportedMechanics": sorted(unsupported),
        "deferredMechanics": [],
        "publication": {
            "purpose": "legacy-roster-persistence",
            "executableDefinition": "unpublished",
            "presentationAsset": "published",
        },
        "presentation": {
            "iconAssetId": target.thumbnail_asset_id,
            "viewerAssetId": target.viewer_asset_id,
        },
    }
    for key in ("size",):
        if key in raw:
            projected[key] = raw[key]
    for key in ("traits", "languages"):
        if key in raw:
            projected[key] = _string_list(raw[key], f"legacy roster creature {key}")
    if "attributes" in raw:
        projected["attributes"] = _selected_object(
            raw["attributes"],
            (
                "strength",
                "dexterity",
                "constitution",
                "intelligence",
                "wisdom",
                "charisma",
            ),
            "legacy roster creature attributes",
        )
    if "perception" in raw:
        perception = _object(raw["perception"], "legacy roster creature perception")
        projected["perception"] = {
            "modifier": perception["modifier"],
            "senses": _string_list(
                perception["senses"], "legacy roster creature senses"
            ),
        }
    if "skills" in raw:
        skills = raw["skills"]
        if type(skills) is not list:
            raise PF2ERLegacyRosterSemanticError(
                "legacy roster creature skills must be a list"
            )
        projected["skills"] = [
            _selected_object(item, ("name", "modifier"), "legacy roster skill")
            for item in skills
        ]
    if "speeds" in raw:
        projected["speeds"] = _selected_object(
            raw["speeds"],
            ("land", "burrow", "climb", "fly", "swim"),
            "legacy roster creature speeds",
        )

    acquisition_paths = public_definition_acquisition_paths(projected)
    if acquisition_paths:
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster projector emitted acquisition-only fields: "
            + ", ".join(acquisition_paths)
        )
    validate_public_semantic_definition(projected)
    return projected


def build_legacy_roster_semantic_package(
    *,
    authority: SourceAuthorityAdapter,
    compiler_set: SemanticCompilerSet,
    evidence_store: SemanticEvidenceStore,
    portrait_asset_refs: Mapping[str, tuple[AssetRef, AssetRef]],
) -> SemanticPackage:
    """Compile the exact 91-entity persistence-only roster package."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("legacy roster semantics require SourceAuthorityAdapter")
    if type(compiler_set) is not SemanticCompilerSet:
        raise TypeError("legacy roster semantics require SemanticCompilerSet")
    if type(evidence_store) is not SemanticEvidenceStore:
        raise TypeError("legacy roster semantics require SemanticEvidenceStore")
    if not isinstance(portrait_asset_refs, Mapping):
        raise TypeError("legacy roster semantics require portrait asset references")
    expected_portrait_ids = {
        target.entity_id for target in PF2ER_LEGACY_ROSTER_TARGETS
    }
    actual_portrait_ids = set(portrait_asset_refs)
    if actual_portrait_ids != expected_portrait_ids:
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster portrait reference census changed; "
            f"missing={sorted(expected_portrait_ids - actual_portrait_ids)}, "
            f"extra={sorted(actual_portrait_ids - expected_portrait_ids)}"
        )
    for target in PF2ER_LEGACY_ROSTER_TARGETS:
        portrait_refs = portrait_asset_refs[target.entity_id]
        if (
            type(portrait_refs) is not tuple
            or len(portrait_refs) != 2
            or not all(isinstance(item, AssetRef) for item in portrait_refs)
        ):
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster portrait references are invalid: {target.entity_id}"
            )
        expected_asset_ids = (
            target.thumbnail_asset_id,
            target.viewer_asset_id,
        )
        if tuple(item.asset_id for item in portrait_refs) != expected_asset_ids:
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster portrait asset IDs drifted: {target.entity_id}"
            )
    if authority.allowed_source_ids != _EXPECTED_AUTHORITY_SCOPE:
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster authority scope must be the exact Core compiler scope"
        )
    if not hmac.compare_digest(
        authority.snapshot.digest,
        PF2ER_LEGACY_ROSTER_AUTHORITY_DIGEST,
    ):
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster source authority drifted"
        )
    expected_compiler = build_pf2er_semantic_compiler_set(
        book_ids=(PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
    )
    if (
        compiler_set.digest != expected_compiler.digest
        or compiler_set.canonical_manifest()
        != expected_compiler.canonical_manifest()
    ):
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster compiler selection drifted"
        )

    entities = []
    evidence_records = []
    for target in PF2ER_LEGACY_ROSTER_TARGETS:
        address = authority.address(
            source_id=PF2ER_LEGACY_ROSTER_SOURCE_ID,
            locator=target.current_locator,
        )
        source_selection = authority.validate_selection(authority.resolve(address))
        raw_definition = compiler_set.compile_source_creature(
            authority,
            PF2ER_LEGACY_ROSTER_SOURCE_ID,
            target.current_locator,
        )
        description = source_creature_description(
            authority,
            PF2ER_LEGACY_ROSTER_SOURCE_ID,
            target.current_locator,
        )
        raw_definition_digest = canonical_digest(
            {
                "schema": 1,
                "compiledCreature": raw_definition,
                "genericDescription": description,
            },
            "legacy roster raw compiler definition",
        )
        definition = _project_persistence_definition(
            raw_definition,
            target,
            description,
        )
        definition_digest = canonical_digest(
            definition,
            "legacy roster projected definition",
        )
        record = SemanticEvidenceRecord.build(
            evidence_authority_id=PF2ER_LEGACY_ROSTER_EVIDENCE_AUTHORITY_ID,
            entity_id=target.entity_id,
            compiler_digest=compiler_set.digest,
            raw_definition_digest=raw_definition_digest,
            projected_definition_digest=definition_digest,
            projection_id=PF2ER_LEGACY_ROSTER_PROJECTION_ID,
            projection_version=PF2ER_LEGACY_ROSTER_PROJECTION_VERSION,
            projection_digest=PF2ER_LEGACY_ROSTER_PROJECTION_DIGEST,
            acquisition_receipt={
                "schema": 1,
                "kind": "pf2er-legacy-roster-source-reconnection",
                "authorityDigest": authority.snapshot.digest,
                "legacySourceAddress": target.legacy_source_address,
                "currentSelection": source_selection.receipt.as_serialized(),
            },
            compiler_receipt={
                "schema": 1,
                "manifest": compiler_set.manifest,
                "digest": compiler_set.digest,
                "projection": _PROJECTION_MANIFEST,
                "genericDescriptionDigest": canonical_digest(
                    description,
                    "legacy roster generic description",
                ),
                "executableFieldCounts": {
                    field: len(raw_definition[field])
                    for field in _EXECUTABLE_MARKERS
                },
            },
        )
        evidence_records.append(record)
        entities.append(
            build_semantic_entity(
                entity_id=target.entity_id,
                entity_kind="ttrpg:creature",
                definition=definition,
                evidence_authority_id=PF2ER_LEGACY_ROSTER_EVIDENCE_AUTHORITY_ID,
                evidence_record_digest=record.evidence_record_digest,
                compiler_digest=compiler_set.digest,
                raw_definition_digest=raw_definition_digest,
                projection_id=PF2ER_LEGACY_ROSTER_PROJECTION_ID,
                projection_version=PF2ER_LEGACY_ROSTER_PROJECTION_VERSION,
                projection_digest=PF2ER_LEGACY_ROSTER_PROJECTION_DIGEST,
                asset_refs=portrait_asset_refs[target.entity_id],
            )
        )

    generation_digest = canonical_digest(
        {
            "schema": 1,
            "semanticGeneration": PF2ER_LEGACY_ROSTER_SEMANTIC_GENERATION,
            "packageId": PF2ER_LEGACY_ROSTER_PACKAGE_ID,
            "packageVersion": PF2ER_LEGACY_ROSTER_PACKAGE_VERSION,
            "authorityDigest": authority.snapshot.digest,
            "compilerDigest": compiler_set.digest,
            "projectionDigest": PF2ER_LEGACY_ROSTER_PROJECTION_DIGEST,
            "entities": [
                {
                    "entityId": entity.entity_id,
                    "definitionDigest": entity.definition_digest,
                    "evidenceRecordDigest": entity.receipt.evidence_record_digest,
                    "assetRefs": [
                        asset_ref.to_dict() for asset_ref in entity.asset_refs
                    ],
                }
                for entity in entities
            ],
        },
        "legacy roster semantic generation",
    )
    package = build_semantic_package(
        package_id=PF2ER_LEGACY_ROSTER_PACKAGE_ID,
        version=PF2ER_LEGACY_ROSTER_PACKAGE_VERSION,
        ruleset_id=PF2ER_RULESET_ID,
        ruleset_digest=PF2ER_LEGACY_ROSTER_RULESET_DIGEST,
        book_id=PF2ER_MONSTER_CORE_ONE_BOOK_ID,
        book_digest=PF2ER_LEGACY_ROSTER_BOOK_DIGEST,
        semantic_generation=PF2ER_LEGACY_ROSTER_SEMANTIC_GENERATION,
        semantic_generation_digest=generation_digest,
        compiler_id=compiler_set.identity.compiler_id,
        compiler_version=compiler_set.identity.compiler_version,
        compiler_digest=compiler_set.digest,
        entities=tuple(entities),
    )
    evidence_store.provision_many(tuple(evidence_records))
    return package


__all__ = [
    "LegacyRosterTarget",
    "PF2ERLegacyRosterSemanticError",
    "PF2ER_LEGACY_ROSTER_AUTHORITY_DIGEST",
    "PF2ER_LEGACY_ROSTER_BOOK_DIGEST",
    "PF2ER_LEGACY_ROSTER_PACKAGE_ID",
    "PF2ER_LEGACY_ROSTER_PACKAGE_VERSION",
    "PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER",
    "PF2ER_LEGACY_ROSTER_VIEWER_TIER",
    "PF2ER_LEGACY_ROSTER_PROJECTION_DIGEST",
    "PF2ER_LEGACY_ROSTER_PROJECTION_ID",
    "PF2ER_LEGACY_ROSTER_PROJECTION_VERSION",
    "PF2ER_LEGACY_ROSTER_RULESET_DIGEST",
    "PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER",
    "PF2ER_LEGACY_ROSTER_SEMANTIC_GENERATION",
    "PF2ER_LEGACY_ROSTER_TARGETS",
    "build_legacy_roster_semantic_package",
    "pf2er_roster_portrait_asset_id",
]

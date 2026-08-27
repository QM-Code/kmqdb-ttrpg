"""Source-free executable publication for Karmak's legacy PF2ER roster.

The roster is review authority for reconnecting the private source selections.
Every imported creature therefore publishes the compiler's exact ordinary
combat baseline: identity, statistics, defenses, movement, and source-authored
strikes.  The four reviewed legacy spellcasters additionally publish the exact
source-free subset of their repertoire that the selected Gladiator runtime can
execute.  Advanced abilities, authored equipment, strike riders, unsupported
spells, and follow-up activities remain explicitly deferred until their
individual semantic/runtime contracts are selected.  A deferred advanced
mechanic does not invalidate the creature's already imported executable
definition.
Each entity carries exact generic source prose, one bounded opaque x128
thumbnail, one opaque x512 viewer portrait, and an exact content-addressed
offline closure of the existing source-node presentation packet.  It is
suitable for durable stable persistence, display, and baseline encounter
admission.

Hadrosaurid, Viper, and Xulgath Warrior are intentionally absent.  Their
existing reviewed semantic publication lanes own those identities.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hmac
from types import MappingProxyType
from typing import Any, Mapping

from scripts.pf2er_roster_source_presentation import RosterSourcePresentation
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
    CapabilityRequirement,
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
PF2ER_LEGACY_ROSTER_PACKAGE_VERSION = "1.5.0"
PF2ER_LEGACY_ROSTER_PRIOR_PACKAGE_VERSION = "1.4.0"
PF2ER_LEGACY_ROSTER_PRIOR_PACKAGE_DIGEST = (
    "cc4a7b0e184d8e860216e8cc93aef554c85db74dc56e29fe6a5dbda3a715078d"
)
PF2ER_LEGACY_ROSTER_SEMANTIC_GENERATION = (
    "ttrpg:pf2er-monster-core-one-legacy-roster-publication-6"
)
PF2ER_LEGACY_ROSTER_EVIDENCE_AUTHORITY_ID = (
    "ttrpg:pf2er-legacy-roster-semantic-evidence"
)
PF2ER_LEGACY_ROSTER_PROJECTION_ID = (
    "ttrpg:pf2er-legacy-roster-persistence-definition"
)
PF2ER_LEGACY_ROSTER_PROJECTION_VERSION = "6.0.0"
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
    "semantic-publication:plague-zombie-runtime-package-not-selected"
)
PF2ER_LEGACY_ROSTER_SUMMON_INSTRUMENT_CAPABILITY = CapabilityRequirement(
    "gladiator:pf2er-summon-instrument-lifecycle",
    "1.0.0",
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
_EXECUTABLE_SPELLCASTING_TARGETS = MappingProxyType(
    {
        "pf2er:gnome-bard": (
            "pf2er:gnome-bard-spellcasting-v1",
            ("courageous-anthem", "summon-instrument"),
        ),
        "pf2er:goblin-pyro": (
            "pf2er:goblin-pyro-spellcasting-v1",
            (
                "breathe-fire",
                "grease",
                "ignition",
                "light",
                "tangle-vine",
                "telekinetic-hand",
            ),
        ),
        "pf2er:goblin-war-chanter": (
            "pf2er:goblin-war-chanter-spellcasting-v1",
            (
                "bless",
                "soothe",
                "courageous-anthem",
                "telekinetic-hand",
                "telekinetic-projectile",
            ),
        ),
        "pf2er:kobold-cavern-mage": (
            "pf2er:kobold-cavern-mage-spellcasting-v1",
            (
                "fleet-step",
                "heal",
                "pummeling-rubble",
                "runic-weapon",
                "caustic-blast",
                "tangle-vine",
            ),
        ),
    }
)
_EXECUTABLE_SPELLCASTING_CAPABILITIES = MappingProxyType(
    {
        entity_id: (
            *(
                (PF2ER_LEGACY_ROSTER_SUMMON_INSTRUMENT_CAPABILITY,)
                if "summon-instrument" in spell_ids
                else ()
            ),
        )
        for entity_id, (_profile_id, spell_ids) in (
            _EXECUTABLE_SPELLCASTING_TARGETS.items()
        )
    }
)
_PROJECTION_MANIFEST = {
    "schema": 1,
    "packageId": PF2ER_LEGACY_ROSTER_PACKAGE_ID,
    "packageVersion": PF2ER_LEGACY_ROSTER_PACKAGE_VERSION,
    "projectionId": PF2ER_LEGACY_ROSTER_PROJECTION_ID,
    "projectionVersion": PF2ER_LEGACY_ROSTER_PROJECTION_VERSION,
    "definitionSchema": 3,
    "entityKind": "ttrpg:creature",
    "executionPolicy": (
        "baseline-strikes-reviewed-spellcasting-advanced-mechanics-deferred"
    ),
    "spellcastingPolicy": {
        "kind": "source-free-runtime-profile-v2",
        "selectedEntityIds": sorted(_EXECUTABLE_SPELLCASTING_TARGETS),
    },
    "presentationPolicy": {
        "kind": "opaque-portraits-and-exact-source-node-view",
        "thumbnailTier": PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER,
        "viewerTier": PF2ER_LEGACY_ROSTER_VIEWER_TIER,
        "sourceNodeView": "exact-packet-and-content-addressed-offline-closure-v1",
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


def legacy_roster_presentation_bindings(
    prior_package: SemanticPackage,
) -> tuple[
    dict[str, tuple[AssetRef, AssetRef]],
    dict[str, RosterSourcePresentation],
]:
    """Rebind the exact immutable presentation closure from publication 1.4."""

    if (
        not isinstance(prior_package, SemanticPackage)
        or prior_package.package_id != PF2ER_LEGACY_ROSTER_PACKAGE_ID
        or prior_package.version != PF2ER_LEGACY_ROSTER_PRIOR_PACKAGE_VERSION
        or not hmac.compare_digest(
            prior_package.package_digest,
            PF2ER_LEGACY_ROSTER_PRIOR_PACKAGE_DIGEST,
        )
        or len(prior_package.entities) != len(PF2ER_LEGACY_ROSTER_TARGETS)
        or {entity.entity_id for entity in prior_package.entities}
        != {target.entity_id for target in PF2ER_LEGACY_ROSTER_TARGETS}
    ):
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster prior presentation package is not exact"
        )

    portrait_refs: dict[str, tuple[AssetRef, AssetRef]] = {}
    source_presentations: dict[str, RosterSourcePresentation] = {}
    for target in PF2ER_LEGACY_ROSTER_TARGETS:
        entity = prior_package.entity(target.entity_id)
        presentation = entity.definition.get("presentation")
        if type(presentation) is not dict or set(presentation) != {
            "iconAssetId",
            "viewerAssetId",
            "sourceNodeView",
        }:
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster prior presentation is invalid: {target.entity_id}"
            )
        references = {reference.asset_id: reference for reference in entity.asset_refs}
        source_view = presentation["sourceNodeView"]
        if (
            len(references) != len(entity.asset_refs)
            or type(source_view) is not dict
            or set(source_view) != {
                "schema",
                "packetAssetId",
                "closureManifestAssetId",
            }
            or source_view.get("schema") != 1
        ):
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster prior source view is invalid: {target.entity_id}"
            )
        try:
            icon = references[presentation["iconAssetId"]]
            viewer = references[presentation["viewerAssetId"]]
            packet = references[source_view["packetAssetId"]]
            closure = references[source_view["closureManifestAssetId"]]
        except (KeyError, TypeError) as exc:
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster prior presentation closure is incomplete: {target.entity_id}"
            ) from exc
        portraits = (icon, viewer)
        if (
            icon.asset_id
            != pf2er_roster_portrait_asset_id(
                target.entity_id,
                PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER,
            )
            or viewer.asset_id
            != pf2er_roster_portrait_asset_id(
                target.entity_id,
                PF2ER_LEGACY_ROSTER_VIEWER_TIER,
            )
            or len({icon, viewer, packet, closure}) != 4
        ):
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster prior presentation identity drifted: {target.entity_id}"
            )
        portrait_refs[target.entity_id] = portraits
        source_presentations[target.entity_id] = RosterSourcePresentation(
            envelope=deepcopy(source_view),
            asset_refs=tuple(
                reference
                for reference in entity.asset_refs
                if reference not in portraits
            ),
            packet_ref=packet,
            closure_manifest_ref=closure,
        )
    return portrait_refs, source_presentations


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


def _project_damage_component(value: object, label: str) -> dict[str, object]:
    component = _object(value, label)
    projected = _selected_object(
        component,
        ("dice", "flatAmount", "modifier", "persistent", "type"),
        label,
    )
    dice = projected.get("dice")
    if dice is not None:
        projected["dice"] = _selected_object(
            dice,
            ("count", "sides"),
            f"{label} dice",
        )
    return projected


def _project_portable_compiled_effect(value: object) -> dict[str, object]:
    """Translate runtime effect data across Gladiator's acquisition fence."""

    effect = _object(value, "legacy roster spell compiled effect")

    def project(item: object, path: tuple[str, ...]) -> object:
        if type(item) is dict:
            result: dict[str, object] = {}
            for key, child in item.items():
                if type(key) is not str:
                    raise PF2ERLegacyRosterSemanticError(
                        "legacy roster spell effect has a non-string key"
                    )
                if key == "source":
                    if (
                        not path
                        or path[-1] != "duration"
                        or type(child) is not str
                        or not child
                        or "sourceUnit" in item
                    ):
                        raise PF2ERLegacyRosterSemanticError(
                            "legacy roster spell effect contains an "
                            "untranslatable source field"
                        )
                    result["sourceUnit"] = child
                    continue
                result[key] = project(child, (*path, key))
            return result
        if type(item) is list:
            return [project(child, path) for child in item]
        if type(item) in {str, int, bool, type(None)}:
            return item
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster spell effect is not strict JSON data"
        )

    return _object(project(effect, ()), "legacy roster portable spell effect")


def _project_baseline_strike(value: object) -> dict[str, object]:
    """Select one source-free ordinary Strike and omit advanced continuations."""

    strike = _object(value, "legacy roster strike")
    projected = _selected_object(
        strike,
        (
            "id",
            "name",
            "kind",
            "attackModifier",
            "traits",
            "reachFeet",
            "rangeIncrementFeet",
            "maximumRangeIncrements",
            "reloadActions",
            "requiresDrawAfterUse",
        ),
        "legacy roster strike",
    )
    if not {
        "id",
        "name",
        "kind",
        "attackModifier",
        "traits",
    }.issubset(projected):
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster strike omits its ordinary combat identity"
        )
    projected["traits"] = _string_list(
        projected["traits"], "legacy roster strike traits"
    )
    # The baseline has no separately persisted or item-backed equipment.
    # Source-authored Strikes are intrinsic creature attacks at the runtime
    # boundary; advanced equipment behavior remains explicitly deferred.
    projected["attackSource"] = {"kind": "natural"}
    damage = _object(strike.get("damage"), "legacy roster strike damage")
    public_damage = _selected_object(
        damage,
        ("dice", "flatAmount", "modifier", "type"),
        "legacy roster strike damage",
    )
    dice = public_damage.get("dice")
    if dice is not None:
        public_damage["dice"] = _selected_object(
            dice,
            ("count", "sides"),
            "legacy roster strike damage dice",
        )
    components = damage.get("components")
    if type(components) is not list or not components:
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster strike requires ordinary damage components"
        )
    public_damage["components"] = [
        _project_damage_component(
            component,
            f"legacy roster strike damage component {index}",
        )
        for index, component in enumerate(components)
    ]
    public_damage["riderEffects"] = []
    projected["damage"] = public_damage
    projected["followUps"] = []
    return projected


def _project_executable_spellcasting(
    value: object,
    target: LegacyRosterTarget,
) -> dict[str, object]:
    """Translate one private compiler plan into the public runtime profile."""

    plan = _object(value, "legacy roster spellcasting compilation")
    if plan.get("schema") != 1 or plan.get("kind") != "pf2er-creature-spellcasting-plan":
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster spellcasting plan is invalid: {target.entity_id}"
        )
    try:
        runtime_profile_id, expected_spell_ids = _EXECUTABLE_SPELLCASTING_TARGETS[
            target.entity_id
        ]
    except KeyError as exc:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster spellcasting target is not selected: {target.entity_id}"
        ) from exc
    activation = _object(
        plan.get("runtimeActivation"),
        "legacy roster spellcasting activation",
    )
    actual_spell_ids = tuple(
        _string_list(
            activation.get("executableSpellIds"),
            "legacy roster executable spell IDs",
        )
    )
    if actual_spell_ids != expected_spell_ids or len(set(actual_spell_ids)) != len(
        actual_spell_ids
    ):
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster executable spell census drifted: {target.entity_id}"
        )
    raw_spells = plan.get("spells")
    if type(raw_spells) is not list:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster spell repertoire is invalid: {target.entity_id}"
        )
    spells_by_id = {
        spell.get("id"): spell
        for spell in raw_spells
        if type(spell) is dict and type(spell.get("id")) is str
    }
    if len(spells_by_id) != len(raw_spells) or any(
        spell_id not in spells_by_id for spell_id in expected_spell_ids
    ):
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster spell repertoire drifted: {target.entity_id}"
        )
    public_spells = []
    spell_fields = (
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
    for spell_id in expected_spell_ids:
        raw_spell = _object(
            spells_by_id[spell_id],
            f"legacy roster spell {spell_id}",
        )
        spell = _selected_object(
            raw_spell,
            spell_fields,
            f"legacy roster spell {spell_id}",
        )
        if set(spell) != set(spell_fields) or spell.get("execution") != {
            "executable": True,
            "status": "active",
            "runtimeSupported": True,
            "runtimeDependencies": [],
        }:
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster spell is not exactly executable: {spell_id}"
            )
        spell["compiledEffect"] = _project_portable_compiled_effect(
            spell["compiledEffect"]
        )
        public_spells.append(spell)

    raw_casting = _object(plan.get("casting"), "legacy roster spellcasting record")
    casting = _selected_object(
        raw_casting,
        ("id", "mode", "tradition", "dc", "attack"),
        "legacy roster spellcasting record",
    )
    if set(casting) != {"id", "mode", "tradition", "dc", "attack"}:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster casting identity is incomplete: {target.entity_id}"
        )

    if raw_casting.get("mode") == "spontaneous":
        slots = raw_casting.get("slots", [])
        if type(slots) is not list:
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster spell slots are invalid: {target.entity_id}"
            )
        casting["slots"] = []
        for raw_slot in slots:
            slot = _object(raw_slot, "legacy roster spell slot")
            selected_ids = [
                spell_id
                for spell_id in _string_list(
                    slot.get("spellIds"), "legacy roster spell slot IDs"
                )
                if spell_id in expected_spell_ids
            ]
            if selected_ids:
                casting["slots"].append(
                    {
                        "rank": slot["rank"],
                        "maximum": slot["maximum"],
                        "spellIds": selected_ids,
                    }
                )
    elif raw_casting.get("mode") == "prepared":
        prepared = raw_casting.get("preparedSpells", [])
        if type(prepared) is not list:
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster prepared spells are invalid: {target.entity_id}"
            )
        casting["preparedSpells"] = [
            _selected_object(
                row,
                ("rank", "spellId", "maximum"),
                "legacy roster prepared spell",
            )
            for row in prepared
            if type(row) is dict and row.get("spellId") in expected_spell_ids
        ]
    else:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster casting mode is invalid: {target.entity_id}"
        )

    cantrips = raw_casting.get("cantrips")
    if type(cantrips) is dict:
        selected_cantrips = [
            spell_id
            for spell_id in _string_list(
                cantrips.get("spellIds"), "legacy roster cantrip IDs"
            )
            if spell_id in expected_spell_ids
        ]
        if selected_cantrips:
            casting["cantrips"] = {
                "rank": cantrips["rank"],
                "spellIds": selected_cantrips,
            }

    selected_casting_ids: set[str] = set()
    for slot in casting.get("slots", []):
        selected_casting_ids.update(slot["spellIds"])
    for row in casting.get("preparedSpells", []):
        selected_casting_ids.add(row["spellId"])
    selected_casting_ids.update(casting.get("cantrips", {}).get("spellIds", []))
    if selected_casting_ids != set(expected_spell_ids):
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster casting resources drifted: {target.entity_id}"
        )

    return {
        "schema": 2,
        "kind": "pf2er-creature-spellcasting-plan",
        "runtimeProfileId": runtime_profile_id,
        "supportState": "executable",
        "runtimeActivation": {
            "status": "active",
            "executableSpellIds": list(expected_spell_ids),
        },
        "casting": casting,
        "spells": public_spells,
    }


def _project_persistence_definition(
    raw_definition: dict[str, object],
    target: LegacyRosterTarget,
    description: str,
    source_presentation: RosterSourcePresentation,
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
    raw_blockers = _string_list(
        raw.get("runtimeBlockers", []),
        "legacy roster compiler runtime blockers",
    )
    if raw_blockers:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster compiler now blocks baseline execution: {target.entity_id}"
        )
    strikes = raw["strikes"]
    if type(strikes) is not list or not strikes:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster creature has no ordinary strike: {target.entity_id}"
        )
    abilities = raw["abilities"]
    inventory = raw["inventory"]
    if type(abilities) is not list or type(inventory) is not list:
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster compiler executable collections are invalid"
        )
    deferred = set(
        _string_list(
            raw.get("deferredMechanics", []),
            "legacy roster compiler deferred mechanics",
        )
    )
    deferred.update(
        f"advanced-ability-omitted:{ability.get('name')}"
        for ability in abilities
        if type(ability) is dict and type(ability.get("name")) is str
    )
    deferred.update(
        f"authored-inventory-omitted:{item.get('name')}"
        for item in inventory
        if type(item) is dict and type(item.get("name")) is str
    )
    deferred.update(
        f"strike-rider-omitted:{rider.get('name')}"
        for strike in strikes
        if type(strike) is dict
        for rider in (
            strike.get("damage", {}).get("riderEffects", [])
            if type(strike.get("damage")) is dict
            else []
        )
        if type(rider) is dict and type(rider.get("name")) is str
    )
    if abilities:
        deferred.add("semantic-publication:advanced-abilities-deferred")
    if inventory:
        deferred.add("semantic-publication:authored-inventory-deferred")

    runtime_blockers = (
        [PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER]
        if target.entity_id == "pf2er:plague-zombie"
        else []
    )
    executable_spellcasting = target.entity_id in _EXECUTABLE_SPELLCASTING_TARGETS
    raw_spellcasting = raw.get("spellcastingCompilation")
    if executable_spellcasting and raw_spellcasting is None:
        raise PF2ERLegacyRosterSemanticError(
            f"legacy roster selected spellcasting is absent: {target.entity_id}"
        )
    if raw_spellcasting is not None and not executable_spellcasting:
        deferred.add("semantic-publication:spellcasting-profile-deferred")

    projected: dict[str, object] = {
        "schema": 3,
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
            "immunities": _string_list(
                defenses.get("immunities", []),
                "legacy roster creature immunities",
            ),
            "weaknesses": [
                _selected_object(
                    item,
                    ("type", "value"),
                    "legacy roster creature weakness",
                )
                for item in defenses.get("weaknesses", [])
            ],
            "resistances": [
                _selected_object(
                    item,
                    ("type", "value"),
                    "legacy roster creature resistance",
                )
                for item in defenses.get("resistances", [])
            ],
        },
        "inventory": [],
        "strikes": [_project_baseline_strike(strike) for strike in strikes],
        "abilities": [],
        "references": {"rules": [], "items": []},
        "runtimeBlockers": runtime_blockers,
        "unsupportedMechanics": [],
        "deferredMechanics": sorted(deferred),
        "publication": {
            "purpose": "legacy-roster-executable-combat",
            "executableDefinition": (
                "blocked-pending-plague-zombie-runtime"
                if runtime_blockers
                else (
                    "baseline-strikes-and-reviewed-spellcasting"
                    if executable_spellcasting
                    else "baseline-strikes"
                )
            ),
            "advancedMechanics": "deferred",
            "authoredInventory": "deferred-to-owned-item-state",
            "presentationAsset": "published",
        },
        "presentation": {
            "iconAssetId": target.thumbnail_asset_id,
            "viewerAssetId": target.viewer_asset_id,
            "sourceNodeView": source_presentation.envelope,
        },
    }
    if executable_spellcasting:
        projected["spellcastingCompilation"] = _project_executable_spellcasting(
            raw_spellcasting,
            target,
        )
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
    source_presentations: Mapping[str, RosterSourcePresentation],
) -> SemanticPackage:
    """Compile the exact 91-entity baseline roster package."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("legacy roster semantics require SourceAuthorityAdapter")
    if type(compiler_set) is not SemanticCompilerSet:
        raise TypeError("legacy roster semantics require SemanticCompilerSet")
    if type(evidence_store) is not SemanticEvidenceStore:
        raise TypeError("legacy roster semantics require SemanticEvidenceStore")
    if not isinstance(portrait_asset_refs, Mapping):
        raise TypeError("legacy roster semantics require portrait asset references")
    if not isinstance(source_presentations, Mapping):
        raise TypeError("legacy roster semantics require source presentations")
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
    actual_presentation_ids = set(source_presentations)
    if actual_presentation_ids != expected_portrait_ids:
        raise PF2ERLegacyRosterSemanticError(
            "legacy roster source presentation census changed; "
            f"missing={sorted(expected_portrait_ids - actual_presentation_ids)}, "
            f"extra={sorted(actual_presentation_ids - expected_portrait_ids)}"
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
        presentation = source_presentations[target.entity_id]
        if not isinstance(presentation, RosterSourcePresentation):
            raise PF2ERLegacyRosterSemanticError(
                f"legacy roster source presentation is invalid: {target.entity_id}"
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
            source_presentations[target.entity_id],
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
                "sourceNodePacketAssetRef": (
                    source_presentations[target.entity_id].packet_ref.to_dict()
                ),
                "sourceNodeClosureManifestAssetRef": (
                    source_presentations[
                        target.entity_id
                    ].closure_manifest_ref.to_dict()
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
                required_capabilities=(
                    _EXECUTABLE_SPELLCASTING_CAPABILITIES.get(
                        target.entity_id,
                        (),
                    )
                ),
                asset_refs=tuple(
                    sorted(
                        {
                            *portrait_asset_refs[target.entity_id],
                            *source_presentations[target.entity_id].asset_refs,
                        }
                    )
                ),
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
    "PF2ER_LEGACY_ROSTER_PRIOR_PACKAGE_DIGEST",
    "PF2ER_LEGACY_ROSTER_PRIOR_PACKAGE_VERSION",
    "PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER",
    "PF2ER_LEGACY_ROSTER_VIEWER_TIER",
    "PF2ER_LEGACY_ROSTER_PROJECTION_DIGEST",
    "PF2ER_LEGACY_ROSTER_PROJECTION_ID",
    "PF2ER_LEGACY_ROSTER_PROJECTION_VERSION",
    "PF2ER_LEGACY_ROSTER_RULESET_DIGEST",
    "PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER",
    "PF2ER_LEGACY_ROSTER_SEMANTIC_GENERATION",
    "PF2ER_LEGACY_ROSTER_SUMMON_INSTRUMENT_CAPABILITY",
    "PF2ER_LEGACY_ROSTER_TARGETS",
    "build_legacy_roster_semantic_package",
    "legacy_roster_presentation_bindings",
    "pf2er_roster_portrait_asset_id",
]

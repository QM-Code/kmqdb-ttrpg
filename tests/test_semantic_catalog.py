from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import unittest

from subdomains.ttrpg import semantic_catalog as semantic_catalog_module
from subdomains.ttrpg.semantic_catalog import (
    SemanticCatalog,
    SemanticCatalogError,
    SemanticCatalogSnapshot,
)
from subdomains.ttrpg.semantic_packages import (
    CapabilityRequirement,
    SemanticPackage,
    SemanticPackageError,
    build_semantic_entity,
    build_semantic_package,
)


def _digest(character: str) -> str:
    return character * 64


def _evidence(character: str) -> dict[str, str]:
    return {
        "evidence_authority_id": "ttrpg:test-semantic-evidence",
        "evidence_record_digest": _digest(character),
        "compiler_digest": _digest("4"),
        "raw_definition_digest": _digest("5"),
        "projection_id": "ttrpg:test-source-free-projector",
        "projection_version": "1.0.0",
        "projection_digest": _digest("6"),
    }


def _entity(
    entity_id: str,
    name: str,
    capability_id: str,
):
    return build_semantic_entity(
        entity_id=entity_id,
        entity_kind="ttrpg:creature",
        definition={"name": name, "level": 1},
        **_evidence("a" if name == "Goblin" else "b"),
        required_capabilities=(CapabilityRequirement(capability_id, "1.0.0"),),
    )


def _package(
    package_id: str,
    book_id: str,
    digest_character: str,
    *entities: object,
) -> SemanticPackage:
    return build_semantic_package(
        package_id=package_id,
        version="1.0.0",
        ruleset_id="paizo:pf2er",
        ruleset_digest=_digest("1"),
        book_id=book_id,
        book_digest=_digest(digest_character),
        semantic_generation=f"ttrpg:{book_id.split(':', 1)[1]}-generation-1",
        semantic_generation_digest=_digest("3"),
        compiler_id="ttrpg:pf2er-creature-compiler",
        compiler_version="1.0.0",
        compiler_digest=_digest("4"),
        entities=entities,  # type: ignore[arg-type]
    )


class SemanticCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.goblin = _entity("pf2er:goblin-warrior", "Goblin", "gladiator:strike")
        self.leopard = _entity("pf2er:leopard", "Leopard", "gladiator:grab")
        self.core = _package(
            "ttrpg:pf2er-monster-core",
            "paizo:monster-core",
            "2",
            self.goblin,
        )
        self.bestial = _package(
            "ttrpg:pf2er-bestial-book",
            "paizo:bestial-book",
            "5",
            self.leopard,
        )

    def test_snapshot_has_exact_inventory_and_deterministic_manifest(self) -> None:
        first = SemanticCatalogSnapshot.from_selected_packages((self.bestial, self.core))
        second = SemanticCatalog.from_selected_packages((self.core, self.bestial)).snapshot

        self.assertEqual(first.catalog_digest, second.catalog_digest)
        self.assertEqual(first.canonical_manifest_json(), second.canonical_manifest_json())
        self.assertEqual(
            [item["packageId"] for item in first.manifest["packages"]],
            ["ttrpg:pf2er-bestial-book", "ttrpg:pf2er-monster-core"],
        )
        self.assertEqual(first.manifest["packages"][0]["bookId"], "paizo:bestial-book")
        self.assertEqual(first.manifest["packages"][1]["rulesetId"], "paizo:pf2er")
        self.assertRegex(first.catalog_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(json.loads(first.canonical_manifest_json()), first.manifest)

    def test_selections_coexist_without_entity_or_capability_leakage(self) -> None:
        core_only = SemanticCatalog.from_selected_packages((self.core,)).snapshot
        full = SemanticCatalog.from_selected_packages((self.core, self.bestial)).snapshot

        self.assertEqual(core_only.entity("pf2er:goblin-warrior").definition["name"], "Goblin")
        with self.assertRaises(KeyError):
            core_only.entity("pf2er:leopard")
        self.assertEqual(
            [item.capability_id for item in core_only.required_capabilities],
            ["gladiator:strike"],
        )
        self.assertEqual(
            [item.capability_id for item in full.required_capabilities],
            ["gladiator:grab", "gladiator:strike"],
        )

    def test_optional_book_omission_removes_its_entities(self) -> None:
        catalog = SemanticCatalog.from_selected_packages((self.core,))
        with catalog.open_snapshot() as snapshot:
            self.assertEqual([entity.entity_id for entity in snapshot.entities], ["pf2er:goblin-warrior"])
            self.assertEqual(snapshot.manifest["entities"][0]["entityId"], "pf2er:goblin-warrior")
            self.assertNotIn(
                "pf2er:leopard",
                [item["entityId"] for item in snapshot.manifest["entities"]],
            )

    def test_duplicate_entity_or_package_identity_fails_closed(self) -> None:
        duplicate_entity = _package(
            "ttrpg:pf2er-duplicate",
            "paizo:duplicate-book",
            "6",
            _entity("pf2er:goblin-warrior", "Other Goblin", "gladiator:strike"),
        )
        with self.assertRaisesRegex(SemanticCatalogError, "duplicate entity IDs"):
            SemanticCatalogSnapshot.from_selected_packages((self.core, duplicate_entity))
        with self.assertRaisesRegex(SemanticCatalogError, "duplicate package identities"):
            SemanticCatalogSnapshot.from_selected_packages((self.core, self.core))

    def test_tampered_package_is_rejected_during_catalog_load(self) -> None:
        packet = self.core.to_dict()
        packet["bookDigest"] = _digest("9")
        with self.assertRaisesRegex(SemanticPackageError, "package digest mismatch"):
            SemanticPackage.from_dict(packet)

        tampered = deepcopy(self.core)
        object.__setattr__(tampered, "book_digest", _digest("9"))
        with self.assertRaisesRegex(SemanticCatalogError, "not authenticated"):
            SemanticCatalogSnapshot.from_selected_packages((tampered,))

    def test_direct_construction_cannot_bypass_authenticated_selection(self) -> None:
        snapshot = SemanticCatalogSnapshot.from_selected_packages((self.core,))
        with self.assertRaisesRegex(TypeError, "sealed"):
            SemanticCatalogSnapshot(  # type: ignore[call-arg]
                (), (), (), (), "0" * 64
            )
        with self.assertRaisesRegex(TypeError, "sealed"):
            SemanticCatalog(snapshot)  # type: ignore[call-arg]

    def test_catalog_module_does_not_cross_source_or_game_boundaries(self) -> None:
        path = Path(semantic_catalog_module.__file__).resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden = {
            "sqlite3",
            "backend",
            "rules_engine",
            "gladiator",
            "source_authority_store",
            "source",
        }
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[-1] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[-1])
        self.assertFalse(imported & forbidden, imported & forbidden)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from subdomains.ttrpg import (
    semantic_package_builder as semantic_package_builder_module,
)
from subdomains.ttrpg.pf2er_compiler.mechanics import battle_cry
from subdomains.ttrpg.pf2er_compiler.mechanics.source_authority import (
    AuthoritySnapshot,
    authority_manifest_digest,
    text_sha256,
)
from subdomains.ttrpg.semantic_catalog import SemanticCatalog
from subdomains.ttrpg.semantic_compiler import (
    SemanticCompilerIdentity,
    SemanticCompilerPackage,
    SemanticCompilerSet,
    build_semantic_compiler_set,
)
from subdomains.ttrpg.semantic_package_builder import (
    SemanticDefinitionProjector,
    SemanticPackageBuilderError,
    SourceCreatureTarget,
    build_creature_semantic_package,
)
from subdomains.ttrpg.semantic_evidence import (
    SemanticEvidenceStore,
    canonical_digest,
)
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    CapabilityRequirement,
    ProviderCarrierRelationship,
    SemanticPackage,
    public_definition_acquisition_paths,
)


def _digest(character: str) -> str:
    return character * 64


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _authority():
    source_id = "core-mc1"
    source_payload = _json({"id": source_id, "name": "Monster Core"})
    content = _json({"privateRawSource": "must stay behind TTRPG"})
    section_id = "core-mc1:creatures"
    section_payload = _json(
        {"id": section_id, "source_id": source_id, "content": content}
    )
    source_toc = _json(
        [
            {
                "label": "Goblin Warrior",
                "locator": "1.1",
                "section_id": section_id,
                "content_path": [],
                "children": [],
            },
            {
                "label": "Leopard",
                "locator": "1.2",
                "section_id": section_id,
                "content_path": [],
                "children": [],
            },
        ]
    )
    body = {
        "schema": 1,
        "ruleset": "pf2er",
        "sources": [
            {
                "id": source_id,
                "payloadSha256": text_sha256(source_payload),
                "tocSha256": text_sha256(source_toc),
            }
        ],
        "sections": [
            {
                "id": section_id,
                "sourceId": source_id,
                "payloadSha256": text_sha256(section_payload),
                "contentSha256": text_sha256(content),
            }
        ],
    }
    manifest = {**body, "digest": authority_manifest_digest(body)}
    snapshot = AuthoritySnapshot.from_rows(
        manifest,
        source_payloads={source_id: source_payload},
        source_tocs={source_id: source_toc},
        section_payloads={section_id: section_payload},
        section_source_ids={section_id: source_id},
    )
    return snapshot.adapter((source_id,))


def _compiler_set(
    *,
    package_id: str = "ttrpg:pf2er-monster-core",
    book_id: str = "paizo:monster-core",
) -> SemanticCompilerSet:
    identity = SemanticCompilerIdentity(
        compiler_id="ttrpg:pf2er-semantic-compiler",
        compiler_version="1.0.0",
        ruleset_id="paizo:pf2er",
        packages=(
            SemanticCompilerPackage(package_id, "1.0.0", (book_id,)),
        ),
    )
    return build_semantic_compiler_set(
        identity=identity,
        fragments=(battle_cry.FRAGMENT,),
    )


def _target(entity_id: str, locator: str) -> SourceCreatureTarget:
    return SourceCreatureTarget(
        entity_id,
        "core-mc1",
        locator,
        required_capabilities=(
            CapabilityRequirement("gladiator:pf2er-strike", "1.0.0"),
        ),
        asset_refs=(AssetRef(f"ttrpg:{entity_id.split(':')[1]}-icon", _digest("a")),),
    )


def _project(raw: dict[str, object], entity_id: str) -> dict[str, object]:
    projected = {**raw, "id": entity_id}
    if entity_id == "pf2er:goblin-warrior":
        projected["abilities"] = [
            {"id": "darkvision", "ruleRef": "pf2er:darkvision"}
        ]
    return projected


PROJECTOR = SemanticDefinitionProjector(
    package_id="ttrpg:pf2er-monster-core",
    package_version="1.0.0",
    projection_id="ttrpg:test-source-free-creature",
    projection_version="1.0.0",
    definition_schema=1,
    project_creature=_project,
)


def _build(authority, compiler_set, creatures, evidence_store):
    return build_creature_semantic_package(
        authority=authority,
        compiler_set=compiler_set,
        package_id="ttrpg:pf2er-monster-core",
        version="1.0.0",
        ruleset_digest=_digest("1"),
        book_id="paizo:monster-core",
        book_digest=_digest("2"),
        semantic_generation="ttrpg:monster-core-generation-1",
        creatures=creatures,
        projector=PROJECTOR,
        evidence_authority_id="ttrpg:test-semantic-evidence",
        evidence_store=evidence_store,
        relationships=(
            ProviderCarrierRelationship(
                "ttrpg:darkvision-grant",
                "pf2er:darkvision",
                "pf2er:goblin-warrior",
            ),
        ),
    )


def _compiled(_set, _authority, source_id: str, locator: str):
    names = {"1.1": "Goblin Warrior", "1.2": "Leopard"}
    return {
        "schema": 1,
        "id": f"{source_id}:{locator}",
        "name": names[locator],
        "level": 1,
        "abilities": [],
    }


class SemanticPackageBuilderTests(unittest.TestCase):
    def test_selected_compiler_emits_deterministic_authenticated_package(self) -> None:
        authority = _authority()
        compiler_set = _compiler_set()
        goblin = _target("pf2er:goblin-warrior", "1.1")
        leopard = _target("pf2er:leopard", "1.2")

        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            autospec=True,
            side_effect=_compiled,
        ) as compile_creature:
            first_store = SemanticEvidenceStore()
            second_store = SemanticEvidenceStore()
            first = _build(
                authority, compiler_set, (leopard, goblin), first_store
            )
            second = _build(
                authority, compiler_set, (goblin, leopard), second_store
            )

        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.compiler_digest, compiler_set.digest)
        self.assertNotEqual(
            first.semantic_generation_digest, authority.snapshot.digest
        )
        self.assertEqual(
            [item.entity_id for item in first.entities],
            ["pf2er:goblin-warrior", "pf2er:leopard"],
        )
        self.assertEqual(
            first.entity("pf2er:goblin-warrior").definition["id"],
            "pf2er:goblin-warrior",
        )
        self.assertEqual(compile_creature.call_count, 4)
        receipt = first.entity("pf2er:goblin-warrior").receipt
        self.assertEqual(
            receipt.compiler_digest, compiler_set.digest
        )
        private = first_store.record(receipt.evidence_record_digest)
        self.assertEqual(
            private.acquisition_receipt["authorityDigest"], authority.snapshot.digest
        )
        self.assertEqual(
            private.raw_definition_digest,
            canonical_digest(_compiled(None, None, "core-mc1", "1.1")),
        )
        public = first.canonical_json().decode()
        self.assertNotIn('"sourceId"', public)
        self.assertNotIn('"locator"', public)
        self.assertNotIn(authority.snapshot.digest, public)
        self.assertIn(authority.snapshot.digest, private.canonical_json().decode())
        snapshot = first_store.snapshot()
        self.assertEqual(
            snapshot.record(receipt.evidence_record_digest).canonical_json(),
            private.canonical_json(),
        )

    def test_duplicate_or_unselected_targets_fail_before_compilation(self) -> None:
        authority = _authority()
        compiler_set = _compiler_set()
        duplicate = (
            _target("pf2er:goblin-warrior", "1.1"),
            _target("pf2er:goblin-warrior", "1.2"),
        )
        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            autospec=True,
        ) as compile_creature:
            with self.assertRaisesRegex(
                SemanticPackageBuilderError, "duplicate entity IDs"
            ):
                _build(
                    authority, compiler_set, duplicate, SemanticEvidenceStore()
                )
            compile_creature.assert_not_called()

        with self.assertRaisesRegex(
            SemanticPackageBuilderError, "not selected by the compiler set"
        ):
            _build(
                authority,
                _compiler_set(package_id="ttrpg:other-book"),
                duplicate[:1],
                SemanticEvidenceStore(),
            )

    def test_catalog_and_contract_decoder_consume_only_the_sealed_package(
        self,
    ) -> None:
        authority = _authority()
        compiler_set = _compiler_set()
        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            autospec=True,
            side_effect=_compiled,
        ):
            package = _build(
                authority,
                compiler_set,
                (_target("pf2er:goblin-warrior", "1.1"),),
                SemanticEvidenceStore(),
            )

        catalog = SemanticCatalog.from_selected_packages((package,)).snapshot
        self.assertEqual(
            catalog.entity("pf2er:goblin-warrior").definition["name"],
            "Goblin Warrior",
        )
        self.assertNotIn("privateRawSource", catalog.canonical_manifest_json().decode())

        package_bytes = package.canonical_json()
        stored = SemanticPackage.from_dict(json.loads(package_bytes))
        self.assertEqual(stored.canonical_json(), package_bytes)
        self.assertEqual(stored.package_digest, package.package_digest)
        self.assertEqual(
            stored.entity("pf2er:goblin-warrior").definition_digest,
            package.entity("pf2er:goblin-warrior").definition_digest,
        )
        self.assertEqual(
            stored.package_digest,
            canonical_digest(
                stored.to_dict(include_digest=False),
                "semantic package",
            ),
        )
        stored_catalog = SemanticCatalog.from_selected_packages((stored,)).snapshot
        self.assertEqual(
            stored_catalog.canonical_manifest_json(),
            catalog.canonical_manifest_json(),
        )
        self.assertEqual(
            tuple(item.package_digest for item in stored_catalog.inventory),
            (stored.package_digest,),
        )
        self.assertEqual(
            stored_catalog.required_capabilities,
            stored.entities[0].required_capabilities,
        )
        for entity in stored.entities:
            self.assertEqual(
                entity.definition_digest,
                canonical_digest(entity.definition, "semantic definition"),
            )
            self.assertEqual(
                entity.receipt.projected_definition_digest,
                entity.definition_digest,
            )
            self.assertEqual(
                entity.receipt.compiler_digest,
                stored.compiler_digest,
            )
            self.assertEqual(
                public_definition_acquisition_paths(entity.definition),
                (),
            )
        self.assertNotIn("sourceId", json.dumps(stored_catalog.manifest))

    def test_projector_fails_closed_without_storing_untranslated_evidence(self) -> None:
        authority = _authority()
        compiler_set = _compiler_set()
        evidence_store = SemanticEvidenceStore()
        compiler_shaped = {
            "schema": 1,
            "id": "core-mc1:1.1",
            "name": "Goblin Warrior",
            "source": {
                "sourceId": "core-mc1",
                "locator": "1.1",
                "sectionId": "core-mc1:creatures",
                "contentPath": ["Goblin Warrior"],
            },
            "icon": "core/mc1/creatures/x128/Goblin Warrior",
        }
        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            autospec=True,
            return_value=compiler_shaped,
        ):
            with self.assertRaisesRegex(
                SemanticPackageBuilderError,
                r"acquisition-only fields: .*?/icon.*?/source/contentPath",
            ):
                _build(
                    authority,
                    compiler_set,
                    (_target("pf2er:goblin-warrior", "1.1"),),
                    evidence_store,
                )
        self.assertEqual(evidence_store.inventory_projection()["records"], [])

    def test_builder_has_no_game_or_backend_import(self) -> None:
        path = Path(semantic_package_builder_module.__file__).resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        self.assertFalse(
            [name for name in imported if "gladiator" in name or "backend" in name],
            imported,
        )


if __name__ == "__main__":
    unittest.main()

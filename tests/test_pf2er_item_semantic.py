from __future__ import annotations

import ast
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from subdomains.ttrpg import pf2er_item_semantic
from subdomains.ttrpg.pf2er_item_semantic import (
    PF2ERItemSemanticError,
    PF2ER_CLUB_ENTITY_ID,
    PF2ER_HANDHELD_INSTRUMENT_ENTITY_ID,
    PF2ER_ITEM_COMPILER_DIGEST,
    PF2ER_ITEM_PROJECTION_DIGEST,
    PF2ER_ITEM_SOURCE_TARGETS,
    PF2ER_JAVELIN_ENTITY_ID,
    PF2ER_VIRTUOSO_HANDHELD_INSTRUMENT_ENTITY_ID,
    PF2ER_PLAYER_CORE_ONE_BOOK_ID,
    PF2ER_PLAYER_CORE_ONE_PACKAGE_ID,
    build_player_core_item_semantic_package,
)
from subdomains.ttrpg.pf2er_compiler.mechanics.source_authority import (
    SourceReceipt,
)
from subdomains.ttrpg.pf2er_compiler.source_authority_store import (
    SourceAuthorityStore,
)
from subdomains.ttrpg.semantic_evidence import (
    SemanticEvidenceError,
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
    canonical_digest,
)
from subdomains.ttrpg.semantic_packages import (
    SemanticPackage,
    SemanticPackageError,
)


TTRPG_ROOT = Path(__file__).resolve().parents[1]
CACHE_DB = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_CACHE_DB",
        TTRPG_ROOT / "cache" / "cache.db",
    )
).expanduser()


def _build(authority, authority_digest: str, evidence_store: SemanticEvidenceStore, **options):
    return build_player_core_item_semantic_package(
        authority=authority,
        expected_authority_digest=authority_digest,
        ruleset_digest="1" * 64,
        book_digest="2" * 64,
        semantic_generation="ttrpg:pf2er-player-core-one-generation-1",
        evidence_store=evidence_store,
        **options,
    )


def _rebuild_evidence(packet: dict, *, expected_digest: str) -> SemanticEvidenceRecord:
    return SemanticEvidenceRecord.build(
        evidence_authority_id=packet["evidenceAuthorityId"],
        entity_id=packet["entityId"],
        compiler_digest=packet["compilerDigest"],
        raw_definition_digest=packet["rawDefinitionDigest"],
        projected_definition_digest=packet["projectedDefinitionDigest"],
        projection_id=packet["projectionId"],
        projection_version=packet["projectionVersion"],
        projection_digest=packet["projectionDigest"],
        acquisition_receipt=packet["acquisitionReceipt"],
        compiler_receipt=packet["compilerReceipt"],
        expected_evidence_record_digest=expected_digest,
    )


def _nested_rule_refs(value: object) -> set[str]:
    refs: set[str] = set()
    if type(value) is dict:
        for key, child in value.items():
            if key == "ruleRef":
                refs.add(child)
            else:
                refs.update(_nested_rule_refs(child))
    elif type(value) is list:
        for child in value:
            refs.update(_nested_rule_refs(child))
    return refs


class PF2ERItemSemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CACHE_DB.is_file():
            raise unittest.SkipTest(
                "live TTRPG source cache is unavailable; "
                "set KMQDB_TTRPG_TEST_CACHE_DB"
            )
        uri = f"{CACHE_DB.resolve().as_uri()}?mode=ro&immutable=1"
        cls.connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        cls.connection.execute("PRAGMA query_only = ON")
        cls.authority_store = SourceAuthorityStore.from_connection(cls.connection)
        cls.authority = cls.authority_store.adapter_for(("core-pc1",))
        cls.evidence_store = SemanticEvidenceStore()
        cls.package = _build(
            cls.authority,
            cls.authority_store.digest,
            cls.evidence_store,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        connection = getattr(cls, "connection", None)
        if connection is not None:
            connection.close()

    def test_exact_current_mechanics_are_source_free_and_xulgath_ready(self) -> None:
        self.assertEqual(self.package.to_dict()["schema"], 2)
        self.assertEqual(self.package.package_id, PF2ER_PLAYER_CORE_ONE_PACKAGE_ID)
        self.assertEqual(self.package.book_id, PF2ER_PLAYER_CORE_ONE_BOOK_ID)
        self.assertEqual(
            [entity.entity_id for entity in self.package.entities],
            [
                PF2ER_CLUB_ENTITY_ID,
                PF2ER_JAVELIN_ENTITY_ID,
                PF2ER_HANDHELD_INSTRUMENT_ENTITY_ID,
                PF2ER_VIRTUOSO_HANDHELD_INSTRUMENT_ENTITY_ID,
            ],
        )
        self.assertEqual(
            self.package.entity(PF2ER_CLUB_ENTITY_ID).definition,
            {
                "schema": 1,
                "id": PF2ER_CLUB_ENTITY_ID,
                "name": "Club",
                "kind": "weapon",
                "level": 0,
                "rarity": "common",
                "weaponCategory": "simple",
                "mode": "melee",
                "price": "0",
                "damage": {
                    "dice": {"count": 1, "sides": 6},
                    "type": "bludgeoning",
                },
                "bulk": 1,
                "hands": {
                    "holding": 1,
                    "requiredToUse": 1,
                    "freeHandCompletesUse": False,
                },
                "group": "club",
                "traits": [
                    {
                        "name": "thrown",
                        "rangeIncrementFeet": 10,
                        "ruleRef": "pf2er.rule:weapon-traits",
                    }
                ],
                "references": {
                    "rules": [
                        "pf2er.rule:weapon-hands",
                        "pf2er.rule:weapon-statistics",
                        "pf2er.rule:weapon-traits",
                    ]
                },
                "presentation": {"name": "Club"},
                "rules": {
                    "statistics": {
                        "ruleRef": "pf2er.rule:weapon-statistics"
                    },
                    "hands": {"ruleRef": "pf2er.rule:weapon-hands"},
                    "traits": {"ruleRef": "pf2er.rule:weapon-traits"},
                },
            },
        )
        self.assertEqual(
            self.package.entity(PF2ER_JAVELIN_ENTITY_ID).definition,
            {
                "schema": 1,
                "id": PF2ER_JAVELIN_ENTITY_ID,
                "name": "Javelin",
                "kind": "weapon",
                "level": 0,
                "rarity": "common",
                "weaponCategory": "simple",
                "mode": "ranged",
                "price": "1 sp",
                "damage": {
                    "dice": {"count": 1, "sides": 6},
                    "type": "piercing",
                },
                "bulk": "light",
                "hands": {
                    "holding": 1,
                    "requiredToUse": 1,
                    "freeHandCompletesUse": False,
                },
                "group": "dart",
                "rangeIncrementFeet": 30,
                "maximumRangeIncrements": 6,
                "reloadActions": None,
                "requiresDrawAfterUse": True,
                "traits": [
                    {
                        "name": "thrown",
                        "ruleRef": "pf2er.rule:weapon-traits",
                    }
                ],
                "references": {
                    "rules": [
                        "pf2er.rule:weapon-hands",
                        "pf2er.rule:weapon-range",
                        "pf2er.rule:weapon-reload",
                        "pf2er.rule:weapon-statistics",
                        "pf2er.rule:weapon-traits",
                    ]
                },
                "presentation": {"name": "Javelin"},
                "rules": {
                    "statistics": {
                        "ruleRef": "pf2er.rule:weapon-statistics"
                    },
                    "hands": {"ruleRef": "pf2er.rule:weapon-hands"},
                    "traits": {"ruleRef": "pf2er.rule:weapon-traits"},
                    "range": {"ruleRef": "pf2er.rule:weapon-range"},
                    "reload": {"ruleRef": "pf2er.rule:weapon-reload"},
                },
            },
        )
        inventory = (
            (PF2ER_CLUB_ENTITY_ID, 1),
            (PF2ER_JAVELIN_ENTITY_ID, 3),
        )
        self.assertTrue(all(self.package.entity(item_id) for item_id, _ in inventory))
        for entity in self.package.entities:
            definition = entity.definition
            declared = definition["references"]["rules"]
            self.assertEqual(declared, sorted(set(declared)))
            self.assertEqual(set(declared), _nested_rule_refs(definition))
            self.assertTrue(
                all(rule_id.startswith("pf2er.rule:") for rule_id in declared)
            )

        public = self.package.canonical_json().decode("utf-8")
        for forbidden in (
            '"sourceId"',
            '"locator"',
            '"source"',
            "core-pc1",
            self.authority_store.digest,
        ):
            self.assertNotIn(forbidden, public)

    def test_exact_handheld_instrument_profiles_preserve_reviewed_deferrals(self) -> None:
        ordinary = self.package.entity(
            PF2ER_HANDHELD_INSTRUMENT_ENTITY_ID
        ).definition
        virtuoso = self.package.entity(
            PF2ER_VIRTUOSO_HANDHELD_INSTRUMENT_ENTITY_ID
        ).definition
        self.assertEqual(
            {
                key: ordinary[key]
                for key in ("level", "price", "bulk", "hands")
            },
            {
                "level": 0,
                "price": "8 sp",
                "bulk": 1,
                "hands": {"holding": 1, "requiredToUse": 2},
            },
        )
        self.assertEqual(
            {
                key: virtuoso[key]
                for key in ("level", "price", "bulk", "hands")
            },
            {
                "level": 3,
                "price": "50 gp",
                "bulk": 1,
                "hands": {"holding": 1, "requiredToUse": 2},
            },
        )
        self.assertIsNone(ordinary["performance"]["itemBonus"])
        self.assertEqual(virtuoso["performance"]["itemBonus"], 1)
        self.assertTrue(
            virtuoso["performance"]["appliesWhileUsingInstrument"]
        )
        for definition in (ordinary, virtuoso):
            self.assertIsNone(
                definition["telekineticProjectile"]["damageType"]
            )
            self.assertTrue(
                definition["telekineticProjectile"][
                    "requiresAdjudicatedPhysicalDamageType"
                ]
            )
            self.assertEqual(
                definition["reviewedDeferrals"],
                [
                    "especially-large-handheld-bulk-gm-ruling",
                    "perform-action-and-modality",
                    "physical-damage-type-gm-adjudication",
                ],
            )

    def test_package_and_private_evidence_round_trip_with_exact_digest_chain(self) -> None:
        decoded = json.loads(self.package.canonical_json().decode("utf-8"))
        round_trip = SemanticPackage.from_dict(decoded)
        self.assertEqual(round_trip.canonical_json(), self.package.canonical_json())

        snapshot = self.evidence_store.snapshot()
        self.assertEqual(len(snapshot.records), 4)
        for entity in self.package.entities:
            receipt = entity.receipt
            self.assertEqual(receipt.compiler_digest, PF2ER_ITEM_COMPILER_DIGEST)
            self.assertEqual(receipt.projection_digest, PF2ER_ITEM_PROJECTION_DIGEST)
            record = snapshot.record(receipt.evidence_record_digest)
            self.assertEqual(record.entity_id, entity.entity_id)
            self.assertEqual(record.projected_definition_digest, entity.definition_digest)
            self.assertEqual(record.compiler_digest, receipt.compiler_digest)
            self.assertEqual(record.projection_digest, receipt.projection_digest)
            self.assertEqual(
                canonical_digest(record.compiler_receipt["rawDefinition"]),
                record.raw_definition_digest,
            )
            packet = json.loads(record.canonical_json().decode("utf-8"))
            supplied_digest = packet.pop("evidenceRecordDigest")
            packet.pop("schema")
            rebuilt = _rebuild_evidence(packet, expected_digest=supplied_digest)
            self.assertEqual(rebuilt.canonical_json(), record.canonical_json())

            acquisition = record.acquisition_receipt
            self.assertEqual(acquisition["authorityDigest"], self.authority_store.digest)
            for source_receipt in acquisition["sourceSelections"].values():
                claim = SourceReceipt.from_serialized(source_receipt)
                verified = self.authority.reload(claim)
                self.assertEqual(verified.receipt.digest, claim.digest)

    def test_each_item_binds_its_exact_distinct_description_target(self) -> None:
        expected = {
            PF2ER_CLUB_ENTITY_ID: (
                "core-pc1",
                "284.13",
                "Club",
                ("Weapon Descriptions", "Club"),
                "core-pc1:item:club",
            ),
            PF2ER_JAVELIN_ENTITY_ID: (
                "core-pc1",
                "285.11",
                "Javelin",
                ("Weapon Descriptions", "Javelin"),
                "core-pc1:item:javelin",
            ),
        }
        self.assertEqual(set(PF2ER_ITEM_SOURCE_TARGETS), set(expected))
        item_receipt_digests: set[str] = set()
        shared_root_receipts: list[dict] = []
        for entity_id, values in expected.items():
            source_id, locator, label, content_path, source_item_id = values
            target = PF2ER_ITEM_SOURCE_TARGETS[entity_id]
            self.assertEqual(
                (target.source_id, target.locator, target.label, target.content_path),
                (source_id, locator, label, content_path),
            )
            self.assertEqual(self.authority.toc_label(source_id, locator), label)
            self.assertEqual(
                self.authority.toc_content_path(source_id, locator),
                content_path,
            )

            entity = self.package.entity(entity_id)
            record = self.evidence_store.record(
                entity.receipt.evidence_record_digest
            )
            acquisition = record.acquisition_receipt
            self.assertEqual(acquisition["selectedSourceItemId"], source_item_id)
            claim = SourceReceipt.from_serialized(acquisition["itemSelection"])
            self.assertEqual(claim.address.source_id, source_id)
            self.assertEqual(claim.address.locator, locator)
            verified = self.authority.reload(claim)
            self.assertEqual(verified.receipt.as_serialized(), claim.as_serialized())
            item_receipt_digests.add(claim.digest)
            shared_root_receipts.append(acquisition["sourceSelections"])

        self.assertEqual(len(item_receipt_digests), 2)
        self.assertEqual(shared_root_receipts[0], shared_root_receipts[1])

    def test_public_or_private_tampering_fails_closed(self) -> None:
        tampered_package = json.loads(self.package.canonical_json().decode("utf-8"))
        tampered_package["entities"][0]["definition"]["damage"]["dice"]["sides"] = 8
        with self.assertRaisesRegex(SemanticPackageError, "definition digest mismatch"):
            SemanticPackage.from_dict(tampered_package)

        record = self.evidence_store.snapshot().records[0]
        tampered_evidence = json.loads(record.canonical_json().decode("utf-8"))
        supplied_digest = tampered_evidence.pop("evidenceRecordDigest")
        tampered_evidence.pop("schema")
        tampered_evidence["compilerReceipt"]["rawDefinition"]["name"] = "Drifted"
        with self.assertRaisesRegex(
            SemanticEvidenceError,
            "semantic evidence record digest mismatch",
        ):
            _rebuild_evidence(tampered_evidence, expected_digest=supplied_digest)

    def test_selection_authority_and_compiler_drift_are_rejected_atomically(self) -> None:
        with patch(
            "subdomains.ttrpg.pf2er_item_semantic.equipment.compile_equipment_catalog"
        ) as compile_items:
            with self.assertRaisesRegex(PF2ERItemSemanticError, "missing=.*excess="):
                _build(
                    self.authority,
                    self.authority_store.digest,
                    SemanticEvidenceStore(),
                    selected_entity_ids=(
                        PF2ER_CLUB_ENTITY_ID,
                        "pf2er:item.sword",
                    ),
                )
            with self.assertRaisesRegex(PF2ERItemSemanticError, "duplicates"):
                _build(
                    self.authority,
                    self.authority_store.digest,
                    SemanticEvidenceStore(),
                    selected_entity_ids=(
                        PF2ER_CLUB_ENTITY_ID,
                        PF2ER_CLUB_ENTITY_ID,
                    ),
                )
            with self.assertRaisesRegex(PF2ERItemSemanticError, "authority drifted"):
                _build(self.authority, "0" * 64, SemanticEvidenceStore())
            compile_items.assert_not_called()

        raw_items = {
            record.acquisition_receipt["selectedSourceItemId"]: deepcopy(
                record.compiler_receipt["rawDefinition"]
            )
            for record in self.evidence_store.snapshot().records
            if "itemSelection" in record.acquisition_receipt
        }
        raw_items["core-pc1:item:club"]["damage"]["dice"]["sides"] = 8
        drifted_catalog = {
            "schema": 1,
            "sourceRoots": [
                {"sourceId": "core-pc1", "locator": "271.1"},
                {"sourceId": "core-pc1", "locator": "272.4"},
                {"sourceId": "core-pc1", "locator": "275.1"},
                {"sourceId": "core-pc1", "locator": "284.1"},
            ],
            "items": raw_items,
        }
        empty_store = SemanticEvidenceStore()
        with patch(
            "subdomains.ttrpg.pf2er_item_semantic.equipment.compile_equipment_catalog",
            return_value=drifted_catalog,
        ):
            with self.assertRaisesRegex(
                PF2ERItemSemanticError,
                "compiler output drifted",
            ):
                _build(
                    self.authority,
                    self.authority_store.digest,
                    empty_store,
                )
        self.assertEqual(empty_store.inventory_projection()["records"], [])

    def test_item_package_builder_has_no_cache_catalog_or_game_dependency(self) -> None:
        path = Path(pf2er_item_semantic.__file__).resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
        self.assertFalse(
            [
                name
                for name in imports
                if any(
                    forbidden in name
                    for forbidden in (
                        "backend",
                        "gladiator",
                        "item_catalog",
                        "sqlite",
                    )
                )
            ],
            imports,
        )


if __name__ == "__main__":
    unittest.main()

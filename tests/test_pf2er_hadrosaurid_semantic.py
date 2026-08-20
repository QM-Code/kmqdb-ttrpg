from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from subdomains.ttrpg import pf2er_hadrosaurid_semantic as hadrosaurid_semantic
from subdomains.ttrpg.pf2er_hadrosaurid_semantic import (
    PF2ER_HADROSAURID_AUTHORITY_DIGEST,
    PF2ER_HADROSAURID_COMPILER_DIGEST,
    PF2ER_HADROSAURID_ENTITY_ID,
    PF2ER_HADROSAURID_PACKAGE_ID,
    PF2ER_HADROSAURID_SPRINT_CAPABILITY,
    PF2ER_HADROSAURID_TRAMPLE_CAPABILITY,
    PF2ER_HADROSAURID_TRAMPLE_RELATIONSHIP,
    PF2ER_TRAMPLE_ENTITY_ID,
    PF2ERHadrosauridSemanticError,
    build_hadrosaurid_semantic_package,
)
from subdomains.ttrpg.pf2er_semantic import (
    PF2ER_MONSTER_CORE_ONE_BOOK_ID,
    build_pf2er_semantic_compiler_set,
)
from subdomains.ttrpg.pf2er_compiler.mechanics.source_authority import (
    SourceReceipt,
)
from subdomains.ttrpg.pf2er_compiler.source_authority_store import (
    SourceAuthorityStore,
)
from subdomains.ttrpg.semantic_compiler import SemanticCompilerSet
from subdomains.ttrpg.semantic_evidence import SemanticEvidenceStore
from subdomains.ttrpg.semantic_packages import (
    CapabilityRequirement,
    ProviderCarrierRelationship,
    SemanticPackage,
    SemanticPackageError,
    public_definition_acquisition_paths,
)


TTRPG_ROOT = Path(__file__).resolve().parents[1]
CACHE_DB = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_CACHE_DB",
        TTRPG_ROOT / "cache" / "cache.db",
    )
).expanduser()


class PF2ERHadrosauridSemanticTests(unittest.TestCase):
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
        cls.store = SourceAuthorityStore.from_connection(cls.connection)
        cls.authority = cls.store.adapter_for(
            ("core-gmc", "core-mc1", "core-pc1")
        )
        cls.compiler_set = build_pf2er_semantic_compiler_set(
            book_ids=(PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
        )
        cls.evidence = SemanticEvidenceStore()
        cls.common = {
            "authority": cls.authority,
            "expected_authority_digest": cls.store.digest,
            "compiler_set": cls.compiler_set,
            "ruleset_digest": "1" * 64,
            "book_digest": "2" * 64,
            "semantic_generation": "ttrpg:hadrosaurid-trample-generation-1",
            "sprint_required_capabilities": (
                PF2ER_HADROSAURID_SPRINT_CAPABILITY,
            ),
            "trample_required_capabilities": (
                PF2ER_HADROSAURID_TRAMPLE_CAPABILITY,
            ),
            "relationships": (
                PF2ER_HADROSAURID_TRAMPLE_RELATIONSHIP,
            ),
        }
        cls.package = build_hadrosaurid_semantic_package(
            **cls.common,
            evidence_store=cls.evidence,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def test_exact_source_and_private_evidence_are_distinct(self) -> None:
        self.assertEqual(self.store.digest, PF2ER_HADROSAURID_AUTHORITY_DIGEST)
        hadrosaurid = self.package.entity(PF2ER_HADROSAURID_ENTITY_ID)
        trample = self.package.entity(PF2ER_TRAMPLE_ENTITY_ID)
        self.assertNotEqual(
            hadrosaurid.receipt.evidence_record_digest,
            trample.receipt.evidence_record_digest,
        )
        self.assertNotEqual(
            hadrosaurid.receipt.raw_definition_digest,
            trample.receipt.raw_definition_digest,
        )

        carrier_record = self.evidence.record(
            hadrosaurid.receipt.evidence_record_digest
        )
        trample_record = self.evidence.record(
            trample.receipt.evidence_record_digest
        )
        carrier_claim = SourceReceipt.from_serialized(
            carrier_record.acquisition_receipt["carrierSelection"]
        )
        trample_claim = SourceReceipt.from_serialized(
            trample_record.acquisition_receipt["trampleSelection"]
        )
        self.assertEqual(carrier_claim.address.source_id, "core-mc1")
        self.assertEqual(carrier_claim.address.locator, "98.2")
        self.assertEqual(
            [step.as_serialized() for step in carrier_claim.address.carrier_path],
            [{"kind": "member", "rawKey": "^.creature", "memberOrdinal": 8}],
        )
        self.assertEqual(carrier_claim.address.selection_path, ())
        self.assertEqual(
            [step.as_serialized() for step in trample_claim.address.carrier_path],
            [{"kind": "member", "rawKey": "^.creature", "memberOrdinal": 8}],
        )
        self.assertEqual(
            [step.as_serialized() for step in trample_claim.address.selection_path],
            [{"kind": "member", "rawKey": "!.Trample", "memberOrdinal": 22}],
        )
        self.assertEqual(self.authority.reload(carrier_claim).receipt, carrier_claim)
        self.assertEqual(self.authority.reload(trample_claim).receipt, trample_claim)

        private_carrier = carrier_record.compiler_receipt["rawDefinition"]
        private_trample = trample_record.compiler_receipt["rawDefinition"]
        self.assertEqual(private_carrier["icon"], "core/mc1/creatures/x128/Hadrosaurid")
        self.assertEqual(
            private_trample["mechanic"]["source"]["receipt"]["address"]["locator"],
            "98.2",
        )
        self.assertEqual(
            len(
                trample_record.compiler_receipt["trampleEvidence"][
                    "providerRuleReceipts"
                ]
            ),
            17,
        )

    def test_package_has_two_typed_entities_and_exact_relationship(self) -> None:
        self.assertEqual(self.package.package_id, PF2ER_HADROSAURID_PACKAGE_ID)
        self.assertEqual(self.package.compiler_digest, PF2ER_HADROSAURID_COMPILER_DIGEST)
        self.assertEqual(
            [(entity.entity_id, entity.entity_kind) for entity in self.package.entities],
            [
                ("pf2er:hadrosaurid", "ttrpg:creature"),
                ("pf2er:trample", "ttrpg:creature-ability"),
            ],
        )
        hadrosaurid = self.package.entity(PF2ER_HADROSAURID_ENTITY_ID)
        trample = self.package.entity(PF2ER_TRAMPLE_ENTITY_ID)
        self.assertEqual(
            hadrosaurid.required_capabilities,
            (PF2ER_HADROSAURID_SPRINT_CAPABILITY,),
        )
        self.assertEqual(trample.required_capabilities, (PF2ER_HADROSAURID_TRAMPLE_CAPABILITY,))
        self.assertEqual(hadrosaurid.asset_refs, ())
        self.assertEqual(trample.asset_refs, ())
        self.assertEqual(
            tuple(item.to_dict() for item in self.package.relationships),
            (
                {
                    "relationshipId": "ttrpg:hadrosaurid-trample-carrier",
                    "providerEntityId": "pf2er:trample",
                    "carrierEntityId": "pf2er:hadrosaurid",
                },
            ),
        )

    def test_combat_fields_sprint_and_trample_are_exact(self) -> None:
        creature = self.package.entity(PF2ER_HADROSAURID_ENTITY_ID).definition
        self.assertEqual(creature["level"], 4)
        self.assertEqual(creature["size"], "huge")
        self.assertEqual(creature["defenses"]["maximumHitPoints"], 60)
        self.assertEqual(creature["space"]["widthSquares"], 3)
        self.assertEqual(creature["space"]["defaultReachFeet"], 10)
        self.assertEqual(creature["speeds"], {"land": 30})
        self.assertEqual(
            [(strike["id"], strike["attackModifier"], strike["reachFeet"])
             for strike in creature["strikes"]],
            [
                ("strike:tail:melee", 14, 15),
                ("strike:foot:melee", 12, 15),
            ],
        )
        sprint = creature["abilities"][0]
        self.assertEqual(sprint["id"], "sprint")
        self.assertEqual(sprint["actionCost"], 2)
        self.assertEqual(sprint["mechanic"]["strideCount"], 2)
        self.assertEqual(sprint["mechanic"]["speedIncreaseFeet"], 20)
        self.assertEqual(
            sprint["mechanic"]["frequency"],
            {
                "maximum": 1,
                "period": {"unit": "rounds", "value": 10},
                "decrementAt": "owner-start-turn",
            },
        )
        self.assertEqual(
            creature["abilities"][1],
            {
                "id": "trample",
                "name": "Trample",
                "kind": "activity",
                "providerEntityId": "pf2er:trample",
            },
        )

        ability = self.package.entity(PF2ER_TRAMPLE_ENTITY_ID).definition
        self.assertEqual(ability["kind"], "pf2er-creature-ability")
        self.assertEqual(ability["actionCost"], 3)
        mechanic = ability["mechanic"]
        self.assertEqual(mechanic["type"], "stride-through-basic-save-damage")
        self.assertEqual(mechanic["movement"]["speedMultiplier"], 2)
        self.assertEqual(mechanic["targeting"]["maximumSize"], "large")
        self.assertEqual(
            mechanic["savingThrow"],
            {"type": "reflex", "dc": 21, "basic": True},
        )
        self.assertTrue(mechanic["sharedDamageRoll"])
        self.assertEqual(
            mechanic["listedStrike"]["damage"]["components"],
            [{"dice": {"count": 2, "sides": 4}, "modifier": 8, "type": "bludgeoning"}],
        )
        self.assertFalse(mechanic["listedStrike"]["makesStrike"])
        self.assertEqual(mechanic["runtime"]["scope"], "clean-map-land")
        self.assertTrue(mechanic["runtime"]["completenessDeferrals"])

    def test_public_bytes_are_recursively_source_free_and_defer_assets(self) -> None:
        for entity in self.package.entities:
            self.assertEqual(public_definition_acquisition_paths(entity.definition), ())
        public = self.package.canonical_json().decode("utf-8")
        for forbidden in (
            '"sourceId"',
            '"locator"',
            '"authorityDigest"',
            '"sourceText"',
            '"sourceSpan"',
            "core-mc1",
            PF2ER_HADROSAURID_AUTHORITY_DIGEST,
            "core/mc1/creatures",
            "Large or smaller, foot, DC 21",
        ):
            self.assertNotIn(forbidden, public)
        presentation = self.package.entity(PF2ER_HADROSAURID_ENTITY_ID).definition[
            "presentation"
        ]
        self.assertEqual(
            presentation,
            {
                "status": "deferred",
                "assetRefs": [],
                "deferrals": ["presentation-asset-not-published"],
            },
        )

    def test_explicit_capability_relationship_and_authority_fences_fail_closed(self) -> None:
        bad_relationship = ProviderCarrierRelationship(
            "ttrpg:wrong-trample-carrier",
            "pf2er:trample",
            "pf2er:hadrosaurid",
        )
        cases = (
            (
                {"sprint_required_capabilities": ()},
                "exact Sprint runtime capability",
            ),
            (
                {"trample_required_capabilities": ()},
                "explicitly require the exact runtime capability",
            ),
            (
                {
                    "trample_required_capabilities": (
                        CapabilityRequirement("gladiator:wrong", "1.0.0"),
                    )
                },
                "explicitly require the exact runtime capability",
            ),
            (
                {"relationships": (bad_relationship,)},
                "exact Trample provider/carrier relationship",
            ),
            (
                {"expected_authority_digest": "0" * 64},
                "source authority drifted",
            ),
        )
        for changes, message in cases:
            with self.subTest(changes=changes):
                arguments = dict(self.common)
                arguments.update(changes)
                evidence = SemanticEvidenceStore()
                with self.assertRaisesRegex(PF2ERHadrosauridSemanticError, message):
                    build_hadrosaurid_semantic_package(
                        **arguments,
                        evidence_store=evidence,
                    )
                self.assertEqual(evidence.inventory_projection()["records"], [])

    def test_compiler_output_tamper_is_rejected_before_evidence_publication(self) -> None:
        carrier = self.package.entity(PF2ER_HADROSAURID_ENTITY_ID)
        record = self.evidence.record(carrier.receipt.evidence_record_digest)
        tampered = deepcopy(record.compiler_receipt["rawDefinition"])
        tampered["defenses"]["maximumHitPoints"] = 61
        evidence = SemanticEvidenceStore()
        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            autospec=True,
            return_value=tampered,
        ):
            with self.assertRaisesRegex(
                PF2ERHadrosauridSemanticError,
                "creature compiler output drifted",
            ):
                build_hadrosaurid_semantic_package(
                    **self.common,
                    evidence_store=evidence,
                )
        self.assertEqual(evidence.inventory_projection()["records"], [])

    def test_round_trip_needs_no_source_cache_or_compiler(self) -> None:
        encoded = self.package.canonical_json()
        with (
            patch.object(
                SourceAuthorityStore,
                "from_path",
                side_effect=AssertionError("offline package opened a cache"),
            ),
            patch.object(
                SourceAuthorityStore,
                "from_connection",
                side_effect=AssertionError("offline package opened a database"),
            ),
            patch.object(
                hadrosaurid_semantic,
                "compile_trample",
                side_effect=AssertionError("offline package compiled Trample"),
            ),
            patch.object(
                hadrosaurid_semantic,
                "link_trample_strike",
                side_effect=AssertionError("offline package linked Trample"),
            ),
            patch.object(
                SemanticCompilerSet,
                "compile_source_creature",
                side_effect=AssertionError("offline package compiled a creature"),
            ),
        ):
            rebuilt = SemanticPackage.from_dict(json.loads(encoded))
        self.assertEqual(rebuilt.canonical_json(), encoded)
        self.assertEqual(
            rebuilt.entity(PF2ER_HADROSAURID_ENTITY_ID).definition["name"],
            "Hadrosaurid",
        )

        tampered = json.loads(encoded)
        trample = next(
            entity
            for entity in tampered["entities"]
            if entity["entityId"] == PF2ER_TRAMPLE_ENTITY_ID
        )
        trample["definition"]["mechanic"]["savingThrow"]["dc"] = 22
        with self.assertRaisesRegex(SemanticPackageError, "definition digest mismatch"):
            SemanticPackage.from_dict(tampered)


if __name__ == "__main__":
    unittest.main()

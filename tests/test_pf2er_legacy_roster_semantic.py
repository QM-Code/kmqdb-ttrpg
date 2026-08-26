from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import pf2er_legacy_roster_semantic as roster_semantic
from subdomains.ttrpg.pf2er_compiler.source_authority_store import (
    SourceAuthorityStore,
)
from subdomains.ttrpg.pf2er_semantic import (
    PF2ER_MONSTER_CORE_ONE_BOOK_ID,
    build_pf2er_semantic_compiler_set,
)
from subdomains.ttrpg.semantic_evidence import SemanticEvidenceStore
from subdomains.ttrpg.semantic_packages import (
    SemanticPackage,
    public_definition_acquisition_paths,
)


TTRPG_ROOT = Path(__file__).resolve().parents[1]
CACHE_DB = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_CACHE_DB",
        TTRPG_ROOT / "cache" / "cache.db",
    )
).expanduser()
EXPECTED_PACKAGE_DIGEST = (
    "476b424e53ff0ab4cb5c7fb2684f480a9d15e99559bec1a41191e7f07368fcf9"
)


class PF2ERLegacyRosterTargetTests(unittest.TestCase):
    def test_exact_91_entity_census_is_unique_and_excludes_reviewed_lanes(self) -> None:
        targets = roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
        self.assertEqual(len(targets), 91)
        self.assertEqual(len({target.entity_id for target in targets}), 91)
        self.assertEqual(
            len({target.legacy_source_address for target in targets}),
            91,
        )
        self.assertTrue(
            all(
                target.legacy_source_address.startswith("core-mc1:")
                for target in targets
            )
        )
        self.assertTrue(
            {"pf2er:hadrosaurid", "pf2er:viper", "pf2er:xulgath-warrior"}
            .isdisjoint(target.entity_id for target in targets)
        )

    def test_only_three_private_locator_reconnections_are_declared(self) -> None:
        corrected = {
            target.legacy_source_address: (
                f"core-mc1:{target.current_locator}"
            )
            for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS
            if target.legacy_locator != target.current_locator
        }
        self.assertEqual(
            corrected,
            {
                "core-mc1:312.2": "core-mc1:312.4",
                "core-mc1:312.4": "core-mc1:312.6",
                "core-mc1:313.5": "core-mc1:313.6",
            },
        )


@unittest.skipUnless(
    CACHE_DB.is_file(),
    "live TTRPG source cache is unavailable; set KMQDB_TTRPG_TEST_CACHE_DB",
)
class PF2ERLegacyRosterPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = SourceAuthorityStore.from_path(CACHE_DB)
        cls.authority = cls.store.adapter_for(
            ("core-gmc", "core-mc1", "core-pc1")
        )
        cls.compiler = build_pf2er_semantic_compiler_set(
            book_ids=(PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
        )
        cls.evidence = SemanticEvidenceStore()
        cls.package = roster_semantic.build_legacy_roster_semantic_package(
            authority=cls.authority,
            compiler_set=cls.compiler,
            evidence_store=cls.evidence,
        )

    def test_package_is_exact_deterministic_and_round_trips(self) -> None:
        self.assertEqual(self.store.digest, roster_semantic.PF2ER_LEGACY_ROSTER_AUTHORITY_DIGEST)
        self.assertEqual(self.package.package_digest, EXPECTED_PACKAGE_DIGEST)
        self.assertEqual(len(self.package.entities), 91)
        parsed = SemanticPackage.from_dict(self.package.to_dict())
        self.assertEqual(parsed.canonical_json(), self.package.canonical_json())
        self.assertEqual(parsed.package_digest, EXPECTED_PACKAGE_DIGEST)

    def test_all_definitions_are_source_free_inert_and_runtime_blocked(self) -> None:
        for entity in self.package.entities:
            with self.subTest(entity=entity.entity_id):
                definition = entity.definition
                self.assertEqual(definition["id"], entity.entity_id)
                self.assertEqual(definition["kind"], "pf2er-creature")
                self.assertEqual(definition["inventory"], [])
                self.assertEqual(definition["strikes"], [])
                self.assertEqual(definition["abilities"], [])
                self.assertEqual(
                    definition["runtimeBlockers"],
                    [roster_semantic.PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER],
                )
                self.assertTrue(definition["unsupportedMechanics"])
                self.assertEqual(public_definition_acquisition_paths(definition), ())
                self.assertEqual(entity.required_capabilities, ())
                self.assertEqual(entity.asset_refs, ())

    def test_private_evidence_reconnects_every_target_without_public_leakage(self) -> None:
        for target in roster_semantic.PF2ER_LEGACY_ROSTER_TARGETS:
            entity = self.package.entity(target.entity_id)
            record = self.evidence.record(
                entity.receipt.evidence_record_digest
            )
            acquisition = record.acquisition_receipt
            self.assertEqual(
                acquisition["legacySourceAddress"],
                target.legacy_source_address,
            )
            self.assertEqual(
                acquisition["currentSelection"]["address"]["locator"],
                target.current_locator,
            )
            self.assertNotIn(
                target.legacy_source_address,
                entity.receipt.to_dict().values(),
            )
        self.assertEqual(len(self.evidence.snapshot().records), 91)

    def test_authority_and_compiler_drift_fail_before_publication(self) -> None:
        with patch.object(
            roster_semantic,
            "PF2ER_LEGACY_ROSTER_AUTHORITY_DIGEST",
            "0" * 64,
        ):
            with self.assertRaisesRegex(
                roster_semantic.PF2ERLegacyRosterSemanticError,
                "source authority drifted",
            ):
                roster_semantic.build_legacy_roster_semantic_package(
                    authority=self.authority,
                    compiler_set=self.compiler,
                    evidence_store=SemanticEvidenceStore(),
                )

        wrong = build_pf2er_semantic_compiler_set()
        with self.assertRaisesRegex(
            roster_semantic.PF2ERLegacyRosterSemanticError,
            "compiler selection drifted",
        ):
            roster_semantic.build_legacy_roster_semantic_package(
                authority=self.authority,
                compiler_set=wrong,
                evidence_store=SemanticEvidenceStore(),
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
from pathlib import Path
import unittest

from scripts.pf2er_portable_spell_reference_semantic import (
    PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_DIGEST,
    PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_ID,
    PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_DIGEST,
    PF2ER_PORTABLE_SPELL_REFERENCE_TARGETS,
    build_portable_spell_reference_semantic_package,
)
from subdomains.ttrpg.pf2er_compiler.mechanics.source_authority import (
    SourceReceipt,
)
from subdomains.ttrpg.pf2er_compiler.source_authority_store import (
    SourceAuthorityStore,
)
from subdomains.ttrpg.semantic_evidence import SemanticEvidenceStore
from subdomains.ttrpg.semantic_packages import SemanticPackage


TTRPG_ROOT = Path(__file__).resolve().parents[1]
CACHE_DB = Path(
    os.environ.get(
        "KMQDB_TTRPG_TEST_CACHE_DB",
        TTRPG_ROOT / "cache" / "cache.db",
    )
).expanduser()


@unittest.skipUnless(
    CACHE_DB.is_file(),
    "live TTRPG source cache is unavailable; set KMQDB_TTRPG_TEST_CACHE_DB",
)
class PF2ERPortableSpellReferenceSemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = SourceAuthorityStore.from_path(CACHE_DB)
        cls.authority = cls.store.adapter_for(
            ("core-gmc", "core-mc1", "core-pc1")
        )
        cls.evidence = SemanticEvidenceStore()
        cls.package = build_portable_spell_reference_semantic_package(
            authority=cls.authority,
            evidence_store=cls.evidence,
        )

    def test_exact_source_free_reference_closure_is_published(self) -> None:
        self.assertEqual(
            self.package.package_id,
            PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_ID,
        )
        self.assertEqual(len(self.package.entities), 16)
        self.assertEqual(
            {
                entity.definition["runtimeId"]: entity.entity_id
                for entity in self.package.entities
            },
            {
                runtime_id: target[0]
                for runtime_id, target in (
                    PF2ER_PORTABLE_SPELL_REFERENCE_TARGETS.items()
                )
            },
        )
        for entity in self.package.entities:
            self.assertEqual(entity.entity_kind, "ttrpg:spell")
            self.assertEqual(
                entity.receipt.compiler_digest,
                PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_DIGEST,
            )
            self.assertTrue(entity.definition["description"])
            self.assertEqual(
                entity.receipt.projection_digest,
                PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_DIGEST,
            )
        grease = self.package.entity("pf2er:spell-reference.grease")
        self.assertIn("\n\n- Area ", grease.definition["description"])
        public = self.package.canonical_json().decode("utf-8")
        for forbidden in (
            '"sourceId"',
            '"locator"',
            "core-pc1",
            self.store.digest,
        ):
            self.assertNotIn(forbidden, public)

    def test_private_receipts_reload_each_exact_source_selection(self) -> None:
        for entity in self.package.entities:
            with self.subTest(entity=entity.entity_id):
                record = self.evidence.record(
                    entity.receipt.evidence_record_digest
                )
                claim = SourceReceipt.from_serialized(
                    record.acquisition_receipt["sourceSelection"]
                )
                self.assertEqual(claim.address.source_id, "core-pc1")
                self.assertEqual(
                    self.authority.reload(claim).receipt.as_serialized(),
                    claim.as_serialized(),
                )

    def test_package_round_trips_under_closed_schema(self) -> None:
        rebuilt = SemanticPackage.from_dict(
            json.loads(self.package.canonical_json())
        )
        self.assertEqual(rebuilt.canonical_json(), self.package.canonical_json())


if __name__ == "__main__":
    unittest.main()

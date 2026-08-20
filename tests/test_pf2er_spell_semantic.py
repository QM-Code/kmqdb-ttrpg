from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import unittest

from subdomains.ttrpg.pf2er_spell_semantic import (
    PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_ID,
    PF2ER_SPELL_COMPILER_DIGEST,
    PF2ER_SUMMON_INSTRUMENT_ENTITY_ID,
    build_player_core_spell_semantic_package,
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


class PF2ERSpellSemanticTests(unittest.TestCase):
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
        cls.authority = cls.store.adapter_for(("core-pc1",))
        cls.evidence = SemanticEvidenceStore()
        cls.package = build_player_core_spell_semantic_package(
            authority=cls.authority,
            expected_authority_digest=cls.store.digest,
            ruleset_digest="1" * 64,
            book_digest="2" * 64,
            semantic_generation="ttrpg:pf2er-pc1-spell-generation-1",
            evidence_store=cls.evidence,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def test_source_free_summon_instrument_projection_is_exact(self) -> None:
        self.assertEqual(
            self.package.package_id,
            PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_ID,
        )
        entity = self.package.entity(PF2ER_SUMMON_INSTRUMENT_ENTITY_ID)
        self.assertEqual(entity.receipt.compiler_digest, PF2ER_SPELL_COMPILER_DIGEST)
        self.assertEqual(
            entity.definition,
            {
                "schema": 1,
                "id": "pf2er:summon-instrument",
                "name": "Summon Instrument",
                "kind": "cantrip",
                "rank": 1,
                "actionCost": 3,
                "traits": ["cantrip", "concentrate", "manipulate"],
                "traditions": ["arcane", "divine", "occult"],
                "duration": {"seconds": 3600},
                "effect": {
                    "type": "temporary-item-creation",
                    "mechanicType": "summon-instrument-item-creation",
                    "duration": {"seconds": 3600},
                    "createsInCasterGrasp": True,
                    "ordinaryItemEntityId": (
                        "pf2er:item.musical-instrument-handheld"
                    ),
                    "ownerOnlyMayPlay": True,
                    "recastRemovesPriorOwnedItem": True,
                    "expiryRemovesExactItem": True,
                    "heightened": {
                        "minimumCastRank": 5,
                        "itemEntityId": (
                            "pf2er:item.musical-instrument-handheld-virtuoso"
                        ),
                    },
                    "reviewedDeferrals": [
                        "especially-large-handheld-bulk-gm-ruling",
                        "perform-action-and-instrument-modality",
                        "physical-damage-type-gm-adjudication",
                    ],
                },
                "reviewedDeferrals": [
                    "especially-large-handheld-bulk-gm-ruling",
                    "perform-action-and-instrument-modality",
                    "physical-damage-type-gm-adjudication",
                ],
                "references": {
                    "rules": [
                        "pf2er.rule:duration",
                        "pf2er.rule:spellcasting",
                        "pf2er.rule:summon-instrument",
                    ]
                },
                "rules": {
                    "duration": {"ruleRef": "pf2er.rule:duration"},
                    "spellcasting": {"ruleRef": "pf2er.rule:spellcasting"},
                    "spell": {"ruleRef": "pf2er.rule:summon-instrument"},
                },
            },
        )
        self.assertEqual(
            [item.to_dict() for item in entity.required_capabilities],
            [
                {
                    "capabilityId": (
                        "gladiator:pf2er-summon-instrument-lifecycle"
                    ),
                    "contractVersion": "1.0.0",
                }
            ],
        )
        public = self.package.canonical_json().decode("utf-8")
        for forbidden in (
            '"sourceId"',
            '"locator"',
            "core-pc1",
            self.store.digest,
            "You materialize",
        ):
            self.assertNotIn(forbidden, public)

    def test_private_receipt_reloads_exact_source_selection(self) -> None:
        entity = self.package.entity(PF2ER_SUMMON_INSTRUMENT_ENTITY_ID)
        record = self.evidence.record(entity.receipt.evidence_record_digest)
        claim = SourceReceipt.from_serialized(
            record.acquisition_receipt["sourceSelection"]
        )
        self.assertEqual(claim.address.source_id, "core-pc1")
        self.assertEqual(claim.address.locator, "361.3")
        self.assertEqual(
            self.authority.reload(claim).receipt.as_serialized(),
            claim.as_serialized(),
        )
        self.assertIn("You materialize", json.dumps(record.to_dict()))

    def test_package_round_trips_under_closed_schema(self) -> None:
        rebuilt = SemanticPackage.from_dict(
            json.loads(self.package.canonical_json())
        )
        self.assertEqual(rebuilt.canonical_json(), self.package.canonical_json())


if __name__ == "__main__":
    unittest.main()

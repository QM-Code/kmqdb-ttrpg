from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from subdomains.ttrpg import pf2er_viper_semantic as viper_semantic
from subdomains.ttrpg.pf2er_compiler.mechanics import slink
from subdomains.ttrpg.pf2er_compiler.mechanics.source_authority import (
    RawMemberStep,
    SourceReceipt,
)
from subdomains.ttrpg.pf2er_compiler.source_authority_store import (
    SourceAuthorityStore,
)
from subdomains.ttrpg.semantic_compiler import SemanticCompilerSet
from subdomains.ttrpg.semantic_evidence import (
    SemanticEvidenceError,
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
    canonical_digest,
)
from subdomains.ttrpg.semantic_packages import (
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
CREATURE_RECEIPT_DIGEST = (
    "9e821d1de7fe12a04852001ac69d12992774a3ff15fa6563fe79ab8f5ad1572a"
)
SLINK_RECEIPT_DIGEST = (
    "a10ef449a63a4e09941cdc879941623dd2baf1e1d5dfe1ad3172138e90d92424"
)


def _build(
    authority,
    authority_digest: str,
    evidence_store: SemanticEvidenceStore,
):
    return viper_semantic.build_viper_semantic_package(
        authority=authority,
        expected_authority_digest=authority_digest,
        ruleset_digest="1" * 64,
        book_digest="2" * 64,
        semantic_generation="ttrpg:pf2er-monster-core-one-viper-generation-1",
        evidence_store=evidence_store,
        slink_required_capabilities=(
            viper_semantic.PF2ER_SLINK_CAPABILITY,
        ),
        relationships=(viper_semantic.PF2ER_VIPER_SLINK_RELATIONSHIP,),
    )


def _rebuild_evidence(
    packet: dict[str, object],
    *,
    expected_digest: str,
) -> SemanticEvidenceRecord:
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


@unittest.skipUnless(
    CACHE_DB.is_file(),
    "live TTRPG source cache is unavailable; set KMQDB_TTRPG_TEST_CACHE_DB",
)
class PF2ERViperSemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        uri = f"{CACHE_DB.resolve().as_uri()}?mode=ro&immutable=1"
        cls.connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        cls.connection.execute("PRAGMA query_only = ON")
        cls.authority_store = SourceAuthorityStore.from_connection(cls.connection)
        cls.authority = cls.authority_store.adapter_for(
            ("core-gmc", "core-mc1", "core-pc1")
        )
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

    def test_exact_viper_and_slink_source_receipts_remain_private(self) -> None:
        viper_entity = self.package.entity(
            viper_semantic.PF2ER_VIPER_ENTITY_ID
        )
        slink_entity = self.package.entity(
            viper_semantic.PF2ER_SLINK_ENTITY_ID
        )
        viper_record = self.evidence_store.record(
            viper_entity.receipt.evidence_record_digest
        )
        slink_record = self.evidence_store.record(
            slink_entity.receipt.evidence_record_digest
        )
        self.assertNotEqual(
            viper_record.evidence_record_digest,
            slink_record.evidence_record_digest,
        )
        self.assertNotEqual(
            viper_record.raw_definition_digest,
            slink_record.raw_definition_digest,
        )
        self.assertNotEqual(
            viper_record.projected_definition_digest,
            slink_record.projected_definition_digest,
        )
        self.assertEqual(viper_record.compiler_digest, slink_record.compiler_digest)
        self.assertEqual(
            viper_record.acquisition_receipt["authorityDigest"],
            self.authority_store.digest,
        )
        self.assertEqual(
            slink_record.acquisition_receipt["authorityDigest"],
            self.authority_store.digest,
        )
        common_viper_claim = SourceReceipt.from_serialized(
            viper_record.acquisition_receipt["sourceSelection"]
        )
        common_slink_claim = SourceReceipt.from_serialized(
            slink_record.acquisition_receipt["sourceSelection"]
        )
        self.assertEqual(
            common_viper_claim.as_serialized(),
            common_slink_claim.as_serialized(),
        )
        self.assertEqual(common_viper_claim.address.carrier_path, ())
        self.assertEqual(common_viper_claim.address.selection_path, ())

        creature_claim = SourceReceipt.from_serialized(
            viper_record.acquisition_receipt["creatureSelection"]
        )
        slink_claim = SourceReceipt.from_serialized(
            slink_record.acquisition_receipt["slinkSelection"]
        )
        self.assertEqual(creature_claim.digest, CREATURE_RECEIPT_DIGEST)
        self.assertEqual(slink_claim.digest, SLINK_RECEIPT_DIGEST)
        self.assertEqual(
            creature_claim.address.carrier_path,
            (RawMemberStep("^.creature", 1),),
        )
        self.assertEqual(slink_claim.address.carrier_path, creature_claim.address.carrier_path)
        self.assertEqual(slink_claim.address.selection_path[-1].raw_key, "!.Slink")
        for claim in (creature_claim, slink_claim):
            self.assertEqual(
                self.authority.reload(claim).receipt.as_serialized(),
                claim.as_serialized(),
            )

        viper_raw_definition = viper_record.compiler_receipt["rawDefinition"]
        slink_raw_definition = slink_record.compiler_receipt["rawDefinition"]
        self.assertEqual(
            canonical_digest(viper_raw_definition),
            viper_semantic.PF2ER_VIPER_RAW_DEFINITION_DIGEST,
        )
        self.assertEqual(
            canonical_digest(slink_raw_definition),
            viper_semantic.PF2ER_SLINK_RAW_DEFINITION_DIGEST,
        )
        self.assertEqual(
            viper_raw_definition["creature"]["source"]["locator"],
            "316.2",
        )
        self.assertEqual(
            slink_raw_definition["familyProjection"]["entityId"],
            slink.ENTITY_ID,
        )
        public = self.package.canonical_json().decode("utf-8")
        self.assertNotIn('"rawDefinition"', public)
        self.assertNotIn('"acquisitionReceipt"', public)

    def test_public_creature_is_source_free_schema_aware_and_combat_ready(self) -> None:
        self.assertEqual(self.package.to_dict()["schema"], 2)
        self.assertEqual(
            self.package.package_id,
            viper_semantic.PF2ER_VIPER_PACKAGE_ID,
        )
        self.assertEqual(
            self.package.book_id,
            viper_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
        )
        self.assertEqual(
            [(item.entity_id, item.entity_kind) for item in self.package.entities],
            [
                (viper_semantic.PF2ER_SLINK_ENTITY_ID, "ttrpg:creature-ability"),
                (viper_semantic.PF2ER_VIPER_ENTITY_ID, "ttrpg:creature"),
            ],
        )
        entity = self.package.entity(viper_semantic.PF2ER_VIPER_ENTITY_ID)
        definition = entity.definition
        self.assertEqual(entity.entity_kind, "ttrpg:creature")
        self.assertEqual(definition["schema"], 2)
        self.assertEqual(
            {
                "name": definition["name"],
                "level": definition["level"],
                "size": definition["size"],
                "space": definition["space"],
                "speeds": definition["speeds"],
                "defenses": definition["defenses"],
            },
            {
                "name": "Viper",
                "level": -1,
                "size": "tiny",
                "space": {
                    "sizeRank": 0,
                    "reachProfile": "tiny",
                    "widthSquares": 1,
                    "heightSquares": 1,
                    "spaceFeet": 2.5,
                    "defaultReachFeet": 0,
                },
                "speeds": {"land": 20, "climb": 20, "swim": 20},
                "defenses": {
                    "armorClass": 14,
                    "fortitude": 2,
                    "immunities": [],
                    "maximumHitPoints": 8,
                    "reflex": 7,
                    "resistances": [],
                    "weaknesses": [],
                    "will": 5,
                },
            },
        )
        strike = definition["strikes"][0]
        self.assertEqual(strike["id"], "strike:fangs:melee")
        self.assertEqual(strike["attackModifier"], 6)
        self.assertEqual(strike["damage"]["type"], "piercing")
        self.assertEqual(
            strike["damage"]["deferredRiders"],
            [
                {
                    "abilityId": "viper-venom",
                    "name": "Viper Venom",
                    "status": "deferred",
                }
            ],
        )
        self.assertEqual(public_definition_acquisition_paths(definition), ())
        encoded = self.package.canonical_json().decode("utf-8")
        for forbidden in (
            '"sourceId"',
            '"locator"',
            '"source"',
            '"carrierPath"',
            "core-mc1",
            self.authority_store.digest,
            "core/mc1/creatures/x128/Viper",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_carrier_binds_exact_family_semantics_capability_and_relationship(self) -> None:
        viper_entity = self.package.entity(
            viper_semantic.PF2ER_VIPER_ENTITY_ID
        )
        slink_entity = self.package.entity(
            viper_semantic.PF2ER_SLINK_ENTITY_ID
        )
        expected = slink.compile_slink(
            self.authority,
            slink.select_slink_source(self.authority),
        ).as_ability_update()
        ability = slink_entity.definition
        for key in ("supported", "ruleRef", "traits", "mechanic"):
            self.assertEqual(ability[key], expected[key])
        self.assertEqual(ability["id"], viper_semantic.PF2ER_SLINK_ENTITY_ID)
        self.assertEqual(ability["kind"], "pf2er-creature-ability")
        self.assertEqual(
            ability["mechanic"]["movement"]["triggersMovementReactions"],
            False,
        )
        self.assertEqual(
            slink_entity.required_capabilities,
            (viper_semantic.PF2ER_SLINK_CAPABILITY,),
        )
        self.assertEqual(viper_entity.required_capabilities, ())
        self.assertEqual(slink_entity.asset_refs, ())
        self.assertEqual(viper_entity.asset_refs, ())
        self.assertEqual(
            viper_entity.definition["abilities"],
            [
                {
                    "entityId": viper_semantic.PF2ER_SLINK_ENTITY_ID,
                    "kind": "creature-ability",
                }
            ],
        )
        self.assertEqual(
            self.package.relationships,
            (viper_semantic.PF2ER_VIPER_SLINK_RELATIONSHIP,),
        )
        self.assertEqual(
            self.package.relationships[0].provider_entity_id,
            viper_semantic.PF2ER_SLINK_ENTITY_ID,
        )
        self.assertEqual(
            [
                item["id"]
                for item in viper_entity.definition["runtime"]["deferrals"]
            ],
            [
                "climb-slink-runtime",
                "swim-slink-runtime",
                "tiny-shared-space-runtime",
                "viper-icon-semantic-asset",
                "viper-venom-semantic-runtime",
            ],
        )

        base = {
            "authority": self.authority,
            "expected_authority_digest": self.authority_store.digest,
            "ruleset_digest": "1" * 64,
            "book_digest": "2" * 64,
            "semantic_generation": (
                "ttrpg:pf2er-monster-core-one-viper-generation-1"
            ),
            "evidence_store": SemanticEvidenceStore(),
        }
        with self.assertRaisesRegex(
            viper_semantic.PF2ERViperSemanticError,
            "exactly the reviewed runtime capability",
        ):
            viper_semantic.build_viper_semantic_package(
                **base,
                slink_required_capabilities=(),
                relationships=(
                    viper_semantic.PF2ER_VIPER_SLINK_RELATIONSHIP,
                ),
            )
        with self.assertRaisesRegex(
            viper_semantic.PF2ERViperSemanticError,
            "exactly the reviewed Slink carrier relationship",
        ):
            viper_semantic.build_viper_semantic_package(
                **base,
                slink_required_capabilities=(
                    viper_semantic.PF2ER_SLINK_CAPABILITY,
                ),
                relationships=(),
            )

    def test_public_and_private_tampering_fail_closed(self) -> None:
        public = json.loads(self.package.canonical_json().decode("utf-8"))
        viper_packet = next(
            item
            for item in public["entities"]
            if item["entityId"] == viper_semantic.PF2ER_VIPER_ENTITY_ID
        )
        viper_packet["definition"]["speeds"]["land"] = 25
        with self.assertRaisesRegex(
            SemanticPackageError,
            "definition digest mismatch",
        ):
            SemanticPackage.from_dict(public)

        record = self.evidence_store.record(
            self.package.entity(
                viper_semantic.PF2ER_VIPER_ENTITY_ID
            ).receipt.evidence_record_digest
        )
        private = json.loads(record.canonical_json().decode("utf-8"))
        expected_digest = private.pop("evidenceRecordDigest")
        private.pop("schema")
        private["compilerReceipt"]["rawDefinition"]["creature"]["name"] = "Adder"
        with self.assertRaisesRegex(
            SemanticEvidenceError,
            "semantic evidence record digest mismatch",
        ):
            _rebuild_evidence(private, expected_digest=expected_digest)

    def test_source_and_compiler_drift_are_rejected_atomically(self) -> None:
        empty = SemanticEvidenceStore()
        with self.assertRaisesRegex(
            viper_semantic.PF2ERViperSemanticError,
            "source authority drifted",
        ):
            _build(self.authority, "0" * 64, empty)
        self.assertEqual(empty.inventory_projection()["records"], [])

        raw = deepcopy(
            self.evidence_store.record(
                self.package.entity(
                    viper_semantic.PF2ER_VIPER_ENTITY_ID
                ).receipt.evidence_record_digest
            ).compiler_receipt["rawDefinition"]["creature"]
        )
        raw["defenses"]["maximumHitPoints"] = 9
        empty = SemanticEvidenceStore()
        with patch.object(
            SemanticCompilerSet,
            "compile_source_creature",
            return_value=raw,
        ):
            with self.assertRaisesRegex(
                viper_semantic.PF2ERViperSemanticError,
                "compiler output drifted",
            ):
                _build(self.authority, self.authority_store.digest, empty)
        self.assertEqual(empty.inventory_projection()["records"], [])

    def test_projector_recursively_refuses_acquisition_fields(self) -> None:
        with self.assertRaisesRegex(
            viper_semantic.PF2ERViperSemanticError,
            "acquisition-only fields",
        ):
            viper_semantic._validate_projected_definition(
                {
                    "schema": 1,
                    "id": viper_semantic.PF2ER_SLINK_ENTITY_ID,
                    "mechanic": {"nested": {"sourceId": "core-mc1"}},
                },
                "Slink",
            )

    def test_built_definition_round_trips_with_source_services_offline(self) -> None:
        encoded = self.package.canonical_json()
        self.connection.close()
        self.connection = None
        with patch.object(
            SourceAuthorityStore,
            "from_path",
            side_effect=AssertionError("offline package opened source authority"),
        ), patch.object(
            slink,
            "select_slink_source",
            side_effect=AssertionError("offline package compiled Slink"),
        ):
            offline = SemanticPackage.from_dict(json.loads(encoded.decode("utf-8")))
            definition = offline.entity(
                viper_semantic.PF2ER_VIPER_ENTITY_ID
            ).definition
            ability = offline.entity(
                viper_semantic.PF2ER_SLINK_ENTITY_ID
            ).definition
            self.assertEqual(definition["speeds"]["land"], 20)
            self.assertEqual(
                ability["mechanic"]["runtime"]["readyDomains"],
                ["clean-map-land-stride"],
            )
            self.assertEqual(offline.canonical_json(), encoded)


if __name__ == "__main__":
    unittest.main()

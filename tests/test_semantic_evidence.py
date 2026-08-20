from __future__ import annotations

from copy import deepcopy
import json
import unittest

from subdomains.ttrpg.semantic_evidence import (
    SemanticEvidenceError,
    SemanticEvidenceRecord,
    SemanticEvidenceSnapshot,
    SemanticEvidenceStore,
)


def _digest(character: str) -> str:
    return character * 64


def _record(entity_id: str = "pf2er:goblin") -> SemanticEvidenceRecord:
    return SemanticEvidenceRecord.build(
        evidence_authority_id="ttrpg:pf2er-semantic-evidence",
        entity_id=entity_id,
        compiler_digest=_digest("1"),
        raw_definition_digest=_digest("2"),
        projected_definition_digest=_digest("3"),
        projection_id="ttrpg:pf2er-creature-definition",
        projection_version="1.0.0",
        projection_digest=_digest("4"),
        acquisition_receipt={
            "sourceId": "core-mc1",
            "locator": "1.1",
            "authorityDigest": _digest("5"),
        },
        compiler_receipt={"schema": 1, "digest": _digest("1")},
    )


class SemanticEvidenceTests(unittest.TestCase):
    def test_store_exposes_an_exact_private_publication_snapshot(self) -> None:
        store = SemanticEvidenceStore()
        goblin = _record()
        orc = _record("pf2er:orc")
        store.provision_many((orc, goblin))

        first = store.snapshot()
        second = SemanticEvidenceSnapshot.build((goblin, orc))
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(
            first.record(goblin.evidence_record_digest).acquisition_receipt[
                "sourceId"
            ],
            "core-mc1",
        )
        self.assertIn('"acquisitionReceipt"', first.canonical_json().decode())

    def test_evidence_tampering_fails_digest_verification(self) -> None:
        record = _record()
        with self.assertRaisesRegex(
            SemanticEvidenceError, "record digest mismatch"
        ):
            SemanticEvidenceRecord.build(
                evidence_authority_id=record.evidence_authority_id,
                entity_id=record.entity_id,
                compiler_digest=record.compiler_digest,
                raw_definition_digest=record.raw_definition_digest,
                projected_definition_digest=record.projected_definition_digest,
                projection_id=record.projection_id,
                projection_version=record.projection_version,
                projection_digest=record.projection_digest,
                acquisition_receipt={**record.acquisition_receipt, "locator": "1.2"},
                compiler_receipt=record.compiler_receipt,
                expected_evidence_record_digest=record.evidence_record_digest,
            )

        snapshot = SemanticEvidenceSnapshot.build((record,))
        with self.assertRaisesRegex(
            SemanticEvidenceError, "snapshot digest mismatch"
        ):
            SemanticEvidenceSnapshot.build(
                (_record("pf2er:orc"),),
                expected_snapshot_digest=snapshot.snapshot_digest,
            )


if __name__ == "__main__":
    unittest.main()

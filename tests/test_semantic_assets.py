from __future__ import annotations

import hashlib
import json
import unittest

from subdomains.ttrpg.semantic_assets import (
    SemanticAssetArtifact,
    SemanticAssetError,
    TtrpgSemanticAssetStore,
)
from subdomains.ttrpg.semantic_packages import AssetRef


def _artifact(asset_id: str, body: bytes) -> SemanticAssetArtifact:
    asset_ref = AssetRef(asset_id, hashlib.sha256(body).hexdigest())
    return SemanticAssetArtifact.from_bytes(asset_ref, "image/webp", body)


class SemanticAssetTests(unittest.TestCase):
    def test_artifact_binds_ref_media_type_size_digest_and_exact_bytes(self) -> None:
        body = b"synthetic-webp-body"
        artifact = _artifact("ttrpg:test-icon-x128", body)

        self.assertEqual(artifact.asset_bytes, body)
        self.assertEqual(artifact.size, len(body))
        self.assertEqual(artifact.sha256_digest, hashlib.sha256(body).hexdigest())
        self.assertEqual(artifact.asset_ref.asset_digest, artifact.sha256_digest)
        self.assertEqual(artifact.media_type, "image/webp")
        self.assertEqual(
            json.loads(artifact.canonical_manifest_json()),
            artifact.manifest_dict(),
        )
        serialized = json.dumps(artifact.manifest_dict(), sort_keys=True).lower()
        for forbidden in ("library", "cache", "s3", "path", "locator"):
            self.assertNotIn(forbidden, serialized)

    def test_artifact_rejects_every_byte_authentication_disagreement(self) -> None:
        body = b"one"
        asset_ref = AssetRef("ttrpg:test-icon-x128", hashlib.sha256(body).hexdigest())
        with self.assertRaisesRegex(SemanticAssetError, "size"):
            SemanticAssetArtifact(asset_ref, "image/webp", body, 99, asset_ref.asset_digest)
        with self.assertRaisesRegex(SemanticAssetError, "sha256"):
            SemanticAssetArtifact(asset_ref, "image/webp", body, len(body), "0" * 64)
        with self.assertRaisesRegex(SemanticAssetError, "AssetRef"):
            SemanticAssetArtifact(
                AssetRef("ttrpg:test-icon-x128", "1" * 64),
                "image/webp",
                body,
                len(body),
                hashlib.sha256(body).hexdigest(),
            )
        with self.assertRaisesRegex(SemanticAssetError, "mediaType"):
            SemanticAssetArtifact(
                asset_ref,
                "image/webp; source=/private/path",
                body,
                len(body),
                asset_ref.asset_digest,
            )

    def test_ttrpg_store_publishes_copy_on_write_exact_byte_snapshots(self) -> None:
        first = _artifact("ttrpg:first-icon", b"first")
        second = _artifact("ttrpg:second-icon", b"second")
        store = TtrpgSemanticAssetStore()

        refs = store.publish((second, first))
        snapshot = store.open_snapshot(refs)
        self.assertEqual(snapshot.asset_refs, tuple(sorted((first.asset_ref, second.asset_ref))))
        self.assertEqual(snapshot.artifact(first.asset_ref).asset_bytes, b"first")
        before = store.inventory_projection()

        replacement = _artifact("ttrpg:first-icon", b"replacement")
        with self.assertRaisesRegex(SemanticAssetError, "replacement"):
            store.publish((replacement,))
        self.assertEqual(store.inventory_projection(), before)
        self.assertEqual(snapshot.artifact(first.asset_ref).asset_bytes, b"first")

    def test_ttrpg_store_rejects_bad_batch_without_partial_publication(self) -> None:
        store = TtrpgSemanticAssetStore()
        first = _artifact("ttrpg:first-icon", b"first")
        duplicate_id = _artifact("ttrpg:first-icon", b"different")

        with self.assertRaisesRegex(SemanticAssetError, "duplicate asset IDs"):
            store.publish((first, duplicate_id))
        self.assertEqual(store.inventory_projection()["assets"], [])
        self.assertEqual(store.open_snapshot(()).asset_refs, ())


if __name__ == "__main__":
    unittest.main()

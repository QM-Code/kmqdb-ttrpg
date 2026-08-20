from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from subdomains.ttrpg.semantic_assets import (
    SemanticAssetArtifact,
    TtrpgSemanticAssetStore,
)
from subdomains.ttrpg.semantic_catalog import SemanticCatalogSnapshot
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    SemanticPackage,
    build_semantic_entity,
    build_semantic_package,
)
from subdomains.ttrpg.semantic_transport import (
    SEMANTIC_PACKAGE_MEDIA_TYPE,
    SemanticCatalogEnvelope,
    SemanticPackageArtifact,
    SemanticPackageRequest,
    SemanticTransportError,
    SnapshotSemanticAssetService,
    SnapshotSemanticPackageService,
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


def _asset_body(asset_id: str) -> bytes:
    return f"synthetic:{asset_id}".encode("utf-8")


def _package(
    package_id: str,
    entity_id: str,
    asset_id: str,
    digest_character: str,
) -> SemanticPackage:
    asset_body = _asset_body(asset_id)
    entity = build_semantic_entity(
        entity_id=entity_id,
        entity_kind="ttrpg:creature",
        definition={"name": entity_id.rsplit(":", 1)[1], "level": 1},
        **_evidence(digest_character),
        asset_refs=(AssetRef(asset_id, hashlib.sha256(asset_body).hexdigest()),),
    )
    return build_semantic_package(
        package_id=package_id,
        version="1.0.0",
        ruleset_id="paizo:pf2er",
        ruleset_digest=_digest("1"),
        book_id=f"paizo:{package_id.rsplit(':', 1)[1]}",
        book_digest=_digest(digest_character),
        semantic_generation="ttrpg:publication-generation-1",
        semantic_generation_digest=_digest("3"),
        compiler_id="ttrpg:pf2er-semantic-compiler",
        compiler_version="1.0.0",
        compiler_digest=_digest("4"),
        entities=(entity,),
    )


class SemanticTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = _package(
            "ttrpg:monster-core",
            "pf2er:goblin-warrior",
            "ttrpg:goblin-portrait",
            "2",
        )
        self.optional = _package(
            "ttrpg:optional-bestiary",
            "pf2er:leopard",
            "ttrpg:leopard-portrait",
            "5",
        )

    def test_catalog_envelope_round_trips_exact_refs_and_asset_refs(self) -> None:
        snapshot = SemanticCatalogSnapshot.from_selected_packages(
            (self.optional, self.core)
        )
        envelope = SemanticCatalogEnvelope.from_snapshot(snapshot)
        loaded = SemanticCatalogEnvelope.from_dict(
            json.loads(json.dumps(envelope.to_dict()))
        )

        self.assertEqual(loaded, envelope)
        self.assertEqual(loaded.catalog_digest, snapshot.catalog_digest)
        self.assertEqual(
            [item.package_id for item in loaded.package_requests],
            ["ttrpg:monster-core", "ttrpg:optional-bestiary"],
        )
        self.assertEqual(
            [item.asset_id for item in loaded.asset_refs],
            ["ttrpg:goblin-portrait", "ttrpg:leopard-portrait"],
        )
        serialized = json.dumps(loaded.to_dict(), sort_keys=True).lower()
        self.assertNotIn("locator", serialized)
        self.assertNotIn("sourcepath", serialized)
        self.assertNotIn("cache", serialized)

    def test_service_fetches_only_an_exact_package_identity(self) -> None:
        snapshot = SemanticCatalogSnapshot.from_selected_packages((self.core,))
        service = SnapshotSemanticPackageService(snapshot)
        request = SemanticPackageRequest.from_package(self.core)

        artifact = service.fetch_package(request)
        self.assertEqual(artifact.request, request)
        self.assertEqual(artifact.canonical_package_bytes, self.core.canonical_json())
        self.assertEqual(artifact.media_type, SEMANTIC_PACKAGE_MEDIA_TYPE)
        with self.assertRaisesRegex(SemanticTransportError, "unavailable"):
            service.fetch_package(
                SemanticPackageRequest(
                    request.package_id,
                    request.version,
                    _digest("9"),
                )
            )

    def test_asset_service_fetches_only_an_exact_public_asset_ref(self) -> None:
        asset_ref = self.core.entities[0].asset_refs[0]
        artifact = SemanticAssetArtifact.from_bytes(
            asset_ref,
            "image/webp",
            _asset_body(asset_ref.asset_id),
        )
        store = TtrpgSemanticAssetStore()
        store.publish((artifact,))
        service = SnapshotSemanticAssetService(store.open_snapshot((asset_ref,)))

        fetched = service.fetch_asset(asset_ref)
        self.assertEqual(fetched.asset_ref, asset_ref)
        self.assertEqual(fetched.asset_bytes, artifact.asset_bytes)
        with self.assertRaisesRegex(SemanticTransportError, "unavailable"):
            service.fetch_asset(AssetRef("ttrpg:missing-icon", _digest("9")))

    def test_package_artifact_rejects_noncanonical_or_mismatched_bytes(self) -> None:
        request = SemanticPackageRequest.from_package(self.core)
        with self.assertRaisesRegex(SemanticTransportError, "not canonical"):
            SemanticPackageArtifact(
                request,
                self.core.canonical_json() + b" ",
                tuple(self.core.entities[0].asset_refs),
            )

        packet = deepcopy(self.core.to_dict())
        packet["packageId"] = "ttrpg:other-package"
        with self.assertRaisesRegex(SemanticTransportError, "invalid"):
            SemanticPackageArtifact(
                request,
                json.dumps(packet, sort_keys=True, separators=(",", ":")).encode(),
                tuple(self.core.entities[0].asset_refs),
            )

        with self.assertRaisesRegex(SemanticTransportError, "asset inventory"):
            SemanticPackageArtifact(
                request,
                self.core.canonical_json(),
                (),
            )

    def test_catalog_envelope_is_sealed_and_strict(self) -> None:
        with self.assertRaisesRegex(TypeError, "sealed"):
            SemanticCatalogEnvelope(  # type: ignore[call-arg]
                _digest("0"), (), ()
            )
        packet = SemanticCatalogEnvelope.from_snapshot(
            SemanticCatalogSnapshot.from_selected_packages((self.core,))
        ).to_dict()
        packet["unexpected"] = True
        with self.assertRaisesRegex(SemanticTransportError, "exactly"):
            SemanticCatalogEnvelope.from_dict(packet)


if __name__ == "__main__":
    unittest.main()

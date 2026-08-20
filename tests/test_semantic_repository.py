from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from subdomains.ttrpg import semantic_repository as semantic_repository_module
from subdomains.ttrpg.semantic_assets import (
    SemanticAssetArtifact,
    TtrpgSemanticAssetSnapshot,
    TtrpgSemanticAssetStore,
)
from subdomains.ttrpg.semantic_catalog import SemanticCatalogSnapshot
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    SemanticPackage,
    build_semantic_entity,
    build_semantic_package,
)
from subdomains.ttrpg.semantic_repository import (
    SemanticRepositoryError,
    load_semantic_repository,
    write_semantic_repository,
)
from subdomains.ttrpg.semantic_transport import (
    SemanticPackageRequest,
    SemanticTransportError,
)


def _digest(character: str) -> str:
    return character * 64


def _asset(asset_id: str, body: bytes) -> SemanticAssetArtifact:
    reference = AssetRef(asset_id, hashlib.sha256(body).hexdigest())
    return SemanticAssetArtifact.from_bytes(reference, "image/webp", body)


def _package(
    package_id: str,
    entity_id: str,
    artifact: SemanticAssetArtifact | None,
    character: str,
) -> SemanticPackage:
    entity = build_semantic_entity(
        entity_id=entity_id,
        entity_kind="ttrpg:creature",
        definition={"level": 1, "name": entity_id.rsplit(":", 1)[1]},
        evidence_authority_id="ttrpg:test-semantic-evidence",
        evidence_record_digest=_digest(character),
        compiler_digest=_digest("4"),
        raw_definition_digest=_digest("5"),
        projection_id="ttrpg:test-source-free-projector",
        projection_version="1.0.0",
        projection_digest=_digest("6"),
        asset_refs=() if artifact is None else (artifact.asset_ref,),
    )
    return build_semantic_package(
        package_id=package_id,
        version="1.0.0",
        ruleset_id="paizo:pf2er",
        ruleset_digest=_digest("1"),
        book_id=f"paizo:{package_id.rsplit(':', 1)[1]}",
        book_digest=_digest(character),
        semantic_generation="ttrpg:publication-generation-1",
        semantic_generation_digest=_digest("3"),
        compiler_id="ttrpg:pf2er-semantic-compiler",
        compiler_version="1.0.0",
        compiler_digest=_digest("4"),
        entities=(entity,),
    )


def _snapshots() -> tuple[
    SemanticCatalogSnapshot,
    TtrpgSemanticAssetSnapshot,
    tuple[SemanticAssetArtifact, ...],
]:
    goblin = _asset("ttrpg:goblin-icon", b"synthetic-goblin-webp")
    leopard = _asset("ttrpg:leopard-icon", b"synthetic-leopard-webp")
    catalog = SemanticCatalogSnapshot.from_selected_packages(
        (
            _package(
                "ttrpg:optional-bestiary",
                "pf2er:leopard",
                leopard,
                "7",
            ),
            _package(
                "ttrpg:monster-core",
                "pf2er:goblin-warrior",
                goblin,
                "2",
            ),
        )
    )
    store = TtrpgSemanticAssetStore()
    artifacts = (leopard, goblin)
    store.publish(artifacts)
    assets = store.open_snapshot(tuple(item.asset_ref for item in artifacts))
    return catalog, assets, artifacts


def _tree_metadata(root: Path) -> dict[str, tuple[int, int, int, int]]:
    return {
        str(path.relative_to(root)): (
            path.lstat().st_ino,
            path.lstat().st_size,
            path.lstat().st_mtime_ns,
            stat.S_IMODE(path.lstat().st_mode),
        )
        for path in sorted(root.rglob("*"))
    }


class SemanticRepositoryTests(unittest.TestCase):
    def _publish(
        self,
        root: Path,
    ) -> tuple[Path, SemanticCatalogSnapshot, TtrpgSemanticAssetSnapshot]:
        catalog, assets, _ = _snapshots()
        destination = write_semantic_repository(
            root,
            catalog=catalog,
            assets=assets,
        )
        return destination, catalog, assets

    def test_publishes_digest_named_exact_tree_and_restarts_services(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination, catalog, assets = self._publish(Path(temporary))

            self.assertEqual(destination.name, catalog.catalog_digest)
            self.assertEqual(
                {path.name for path in destination.iterdir()},
                {"catalog-envelope.json", "catalog-index.json", "packages", "assets"},
            )
            self.assertEqual(
                {path.name for path in (destination / "packages").iterdir()},
                {f"{package.package_digest}.json" for package in catalog.packages},
            )
            self.assertEqual(
                {path.name for path in (destination / "assets" / "blobs").iterdir()},
                {reference.asset_digest for reference in assets.asset_refs},
            )
            for path in destination.rglob("*"):
                expected_mode = 0o755 if path.is_dir() else 0o644
                self.assertEqual(stat.S_IMODE(path.lstat().st_mode), expected_mode)

            repository = load_semantic_repository(destination)
            self.assertEqual(repository.catalog_snapshot.manifest, catalog.manifest)
            self.assertEqual(
                repository.asset_snapshot.inventory_projection(),
                assets.inventory_projection(),
            )
            for package in catalog.packages:
                request = SemanticPackageRequest.from_package(package)
                self.assertEqual(
                    repository.package_service.fetch_package(request).canonical_package_bytes,
                    package.canonical_json(),
                )
            for reference in assets.asset_refs:
                self.assertEqual(
                    repository.asset_service.fetch_asset(reference).asset_bytes,
                    assets.artifact(reference).asset_bytes,
                )
            with self.assertRaisesRegex(SemanticTransportError, "unavailable"):
                repository.package_service.fetch_package(
                    SemanticPackageRequest(
                        "ttrpg:monster-core",
                        "1.0.0",
                        _digest("9"),
                    )
                )

    def test_exact_republication_is_validation_only_and_preserves_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination, catalog, assets = self._publish(root)
            before = _tree_metadata(destination)

            reopened = write_semantic_repository(
                root,
                catalog=catalog,
                assets=assets,
            )

            self.assertEqual(reopened, destination)
            self.assertEqual(_tree_metadata(destination), before)
            self.assertFalse(any(path.name.endswith(".publish") for path in root.iterdir()))

    def test_requires_exact_catalog_asset_closure_before_writing(self) -> None:
        catalog, assets, artifacts = _snapshots()
        incomplete_store = TtrpgSemanticAssetStore()
        incomplete_store.publish((artifacts[0],))
        incomplete = incomplete_store.open_snapshot((artifacts[0].asset_ref,))
        extra = _asset("ttrpg:extra-icon", b"extra")
        extra_store = TtrpgSemanticAssetStore()
        extra_store.publish((*artifacts, extra))
        overfull = extra_store.open_snapshot(
            tuple(item.asset_ref for item in (*artifacts, extra))
        )

        for candidate in (incomplete, overfull):
            with self.subTest(asset_count=len(candidate.asset_refs)):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    with self.assertRaisesRegex(
                        SemanticRepositoryError,
                        "exactly close",
                    ):
                        write_semantic_repository(
                            root,
                            catalog=catalog,
                            assets=candidate,
                        )
                    self.assertEqual(list(root.iterdir()), [])
        self.assertEqual(len(assets.asset_refs), 2)

    def test_zero_asset_catalog_publishes_and_reopens_an_exact_empty_index(self) -> None:
        package = _package(
            "ttrpg:asset-free-book",
            "pf2er:asset-free-creature",
            None,
            "8",
        )
        catalog = SemanticCatalogSnapshot.from_selected_packages((package,))
        store = TtrpgSemanticAssetStore()
        assets = store.open_snapshot(())
        with tempfile.TemporaryDirectory() as temporary:
            destination = write_semantic_repository(
                temporary,
                catalog=catalog,
                assets=assets,
            )

            repository = load_semantic_repository(destination)
            self.assertEqual(repository.envelope.asset_refs, ())
            self.assertEqual(repository.asset_snapshot.asset_refs, ())
            self.assertEqual(
                list((destination / "assets" / "blobs").iterdir()),
                [],
            )

    def test_writer_rejects_a_symbolic_link_repository_root(self) -> None:
        catalog, assets, _ = _snapshots()
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            real_root = parent / "real"
            real_root.mkdir()
            linked_root = parent / "linked"
            linked_root.symlink_to(real_root, target_is_directory=True)

            with self.assertRaisesRegex(SemanticRepositoryError, "symbolic link"):
                write_semantic_repository(
                    linked_root,
                    catalog=catalog,
                    assets=assets,
                )
            self.assertEqual(list(real_root.iterdir()), [])

    def test_strict_loader_rejects_missing_extra_symlink_and_unsafe_modes(self) -> None:
        mutations = ("missing", "extra", "symlink", "mode")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                destination, catalog, _ = self._publish(Path(temporary))
                package_path = (
                    destination
                    / "packages"
                    / f"{catalog.packages[0].package_digest}.json"
                )
                if mutation == "missing":
                    package_path.unlink()
                elif mutation == "extra":
                    (destination / "unexpected").write_bytes(b"unexpected")
                    (destination / "unexpected").chmod(0o644)
                elif mutation == "symlink":
                    target = destination / "catalog-index.json"
                    package_path.unlink()
                    package_path.symlink_to(target)
                else:
                    package_path.chmod(0o600)

                with self.assertRaises(SemanticRepositoryError):
                    load_semantic_repository(destination)

    def test_strict_loader_authenticates_canonical_json_body_metadata_and_name(self) -> None:
        mutations = ("noncanonical", "package", "asset", "metadata", "name")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                destination, catalog, assets = self._publish(root)
                if mutation == "noncanonical":
                    path = destination / "catalog-envelope.json"
                    path.write_bytes(path.read_bytes() + b"\n")
                    path.chmod(0o644)
                elif mutation == "package":
                    path = (
                        destination
                        / "packages"
                        / f"{catalog.packages[0].package_digest}.json"
                    )
                    body = bytearray(path.read_bytes())
                    body[-2] ^= 1
                    path.write_bytes(bytes(body))
                    path.chmod(0o644)
                elif mutation == "asset":
                    reference = assets.asset_refs[0]
                    path = destination / "assets" / "blobs" / reference.asset_digest
                    path.write_bytes(b"tampered")
                    path.chmod(0o644)
                elif mutation == "metadata":
                    path = destination / "assets" / "index.json"
                    packet = json.loads(path.read_bytes())
                    packet["assets"][0]["mediaType"] = "image/png"
                    path.write_bytes(
                        json.dumps(
                            packet,
                            ensure_ascii=False,
                            allow_nan=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    )
                    path.chmod(0o644)
                else:
                    renamed = root / _digest("8")
                    destination.rename(renamed)
                    destination = renamed

                with self.assertRaises(SemanticRepositoryError):
                    load_semantic_repository(destination)

    def test_failed_final_rename_leaves_no_partial_publication(self) -> None:
        catalog, assets, _ = _snapshots()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch(
                "subdomains.ttrpg.semantic_repository.os.rename",
                side_effect=OSError("injected rename failure"),
            ):
                with self.assertRaisesRegex(
                    SemanticRepositoryError,
                    "atomically publish",
                ):
                    write_semantic_repository(
                        root,
                        catalog=catalog,
                        assets=assets,
                    )

            self.assertFalse((root / catalog.catalog_digest).exists())
            self.assertEqual(list(root.iterdir()), [])

    def test_existing_corrupt_destination_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination, catalog, assets = self._publish(root)
            envelope = destination / "catalog-envelope.json"
            envelope.write_bytes(b"{}")
            envelope.chmod(0o644)
            before = _tree_metadata(destination)

            with self.assertRaises(SemanticRepositoryError):
                write_semantic_repository(
                    root,
                    catalog=catalog,
                    assets=assets,
                )

            self.assertEqual(_tree_metadata(destination), before)
            self.assertEqual(envelope.read_bytes(), b"{}")

    def test_provider_repository_has_no_game_or_acquisition_imports(self) -> None:
        source_path = Path(semantic_repository_module.__file__).resolve()
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        source = source_path.read_text(encoding="utf-8").lower()

        self.assertFalse(any("gladiator" in name for name in imported))
        for forbidden in (
            "rules_engine",
            "backend",
            "source_authority",
            "semantic_compiler",
            "semantic_package_builder",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

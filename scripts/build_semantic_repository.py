#!/usr/bin/env python3
"""Seal reviewed semantic package and asset bundles for the TTRPG service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


TTRPG_ROOT = Path(__file__).resolve().parents[1]
if str(TTRPG_ROOT) not in sys.path:
    sys.path.insert(0, str(TTRPG_ROOT))

from subdomains.ttrpg.semantic_assets import (
    SemanticAssetArtifact,
    SemanticAssetError,
    TtrpgSemanticAssetStore,
)
from subdomains.ttrpg.semantic_catalog import (
    SemanticCatalogError,
    SemanticCatalogSnapshot,
)
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    SemanticPackage,
    SemanticPackageError,
)
from subdomains.ttrpg.semantic_repository import (
    SemanticRepository,
    SemanticRepositoryError,
    load_semantic_repository,
    write_semantic_repository,
)


class SemanticRepositoryBuildError(RuntimeError):
    """The selected input bundle is incomplete, unsafe, or unauthentic."""


def canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise SemanticRepositoryBuildError(
            "semantic bundle JSON is not canonicalizable"
        ) from exc


def decoded_canonical_json(path: Path, label: str) -> object:
    if path.is_symlink() or not path.is_file():
        raise SemanticRepositoryBuildError(f"{label} must be a regular file")
    try:
        body = path.read_bytes()
        value = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticRepositoryBuildError(f"{label} is invalid JSON") from exc
    if canonical_json(value) != body:
        raise SemanticRepositoryBuildError(f"{label} is not canonical JSON")
    return value


def _directory(path: Path, label: str) -> tuple[Path, ...]:
    if path.is_symlink() or not path.is_dir():
        raise SemanticRepositoryBuildError(f"{label} must be a regular directory")
    try:
        return tuple(sorted(path.iterdir(), key=lambda item: item.name))
    except OSError as exc:
        raise SemanticRepositoryBuildError(f"{label} could not be inspected") from exc


def load_packages(bundle: Path) -> tuple[SemanticPackage, ...]:
    package_directory = bundle / "semantic-packages"
    entries = _directory(package_directory, "semantic package directory")
    if not entries:
        raise SemanticRepositoryBuildError("semantic package directory is empty")
    packages = []
    for path in entries:
        if path.suffix != ".json" or len(path.stem) != 64:
            raise SemanticRepositoryBuildError("semantic package filename is invalid")
        packet = decoded_canonical_json(path, f"semantic package {path.name}")
        try:
            package = SemanticPackage.from_dict(packet)
        except SemanticPackageError as exc:
            raise SemanticRepositoryBuildError(
                f"semantic package failed authentication: {path.name}"
            ) from exc
        if package.package_digest != path.stem or package.canonical_json() != path.read_bytes():
            raise SemanticRepositoryBuildError(
                f"semantic package does not match its filename: {path.name}"
            )
        packages.append(package)
    return tuple(packages)


def load_assets(bundle: Path):
    asset_directory = bundle / "semantic-assets"
    entries = _directory(asset_directory, "semantic asset directory")
    if {path.name for path in entries} != {"blobs", "index.json"}:
        raise SemanticRepositoryBuildError(
            "semantic asset directory contains missing or extra content"
        )
    blobs = asset_directory / "blobs"
    blob_entries = _directory(blobs, "semantic asset blob directory")
    index = decoded_canonical_json(
        asset_directory / "index.json",
        "semantic asset index",
    )
    if type(index) is not dict or set(index) != {"schema", "snapshotDigest", "assets"}:
        raise SemanticRepositoryBuildError("semantic asset index shape is invalid")
    if index.get("schema") != 1 or type(index.get("assets")) is not list:
        raise SemanticRepositoryBuildError("semantic asset index schema is invalid")
    artifacts = []
    expected_blobs = set()
    for item in index["assets"]:
        if type(item) is not dict or set(item) != {
            "schema",
            "assetRef",
            "mediaType",
            "size",
            "sha256",
        }:
            raise SemanticRepositoryBuildError("semantic asset metadata is invalid")
        try:
            reference = AssetRef.from_dict(item["assetRef"])
            digest = str(item["sha256"])
            body_path = blobs / digest
            if body_path.is_symlink() or not body_path.is_file():
                raise SemanticRepositoryBuildError(
                    "semantic asset blob closure is incomplete"
                )
            artifact = SemanticAssetArtifact(
                asset_ref=reference,
                media_type=item["mediaType"],
                asset_bytes=body_path.read_bytes(),
                size=item["size"],
                sha256_digest=digest,
            )
        except (OSError, SemanticAssetError, SemanticPackageError) as exc:
            raise SemanticRepositoryBuildError(
                "semantic asset failed authentication"
            ) from exc
        if artifact.manifest_dict() != item:
            raise SemanticRepositoryBuildError("semantic asset metadata changed")
        artifacts.append(artifact)
        expected_blobs.add(digest)
    if {path.name for path in blob_entries} != expected_blobs:
        raise SemanticRepositoryBuildError(
            "semantic asset blob directory contains missing or extra content"
        )
    store = TtrpgSemanticAssetStore()
    if artifacts:
        store.publish(tuple(artifacts))
    snapshot = store.open_snapshot(tuple(item.asset_ref for item in artifacts))
    if snapshot.inventory_projection() != index:
        raise SemanticRepositoryBuildError("semantic asset index changed")
    return snapshot


def build_repository(bundle: str | Path, repository_root: str | Path) -> SemanticRepository:
    bundle_path = Path(bundle)
    if bundle_path.is_symlink() or not bundle_path.is_dir():
        raise SemanticRepositoryBuildError("semantic bundle must be a regular directory")
    packages = load_packages(bundle_path)
    assets = load_assets(bundle_path)
    try:
        catalog = SemanticCatalogSnapshot.from_selected_packages(packages)
        destination = write_semantic_repository(
            repository_root,
            catalog=catalog,
            assets=assets,
        )
        repository = load_semantic_repository(destination)
    except (SemanticCatalogError, SemanticRepositoryError) as exc:
        raise SemanticRepositoryBuildError(
            "semantic repository failed exact publication"
        ) from exc
    if repository.catalog_snapshot.catalog_digest != catalog.catalog_digest:
        raise SemanticRepositoryBuildError("semantic repository digest changed")
    return repository


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        repository = build_repository(
            arguments.bundle,
            arguments.repository_root,
        )
    except SemanticRepositoryBuildError as exc:
        print(f"semantic repository build failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "schema": 1,
                "kind": "ttrpg-semantic-repository-built",
                "catalogDigest": repository.catalog_snapshot.catalog_digest,
                "packages": len(repository.catalog_snapshot.packages),
                "assets": len(repository.asset_snapshot.asset_refs),
                "path": str(repository.path.resolve()),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

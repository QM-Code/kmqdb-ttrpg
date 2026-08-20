"""Immutable on-disk publication of the public TTRPG semantic catalog.

The repository is the restart boundary for the semantic HTTP service.  It is
closed over already-authenticated public semantic packages and assets and has
no dependency on source acquisition, compilation, or a game runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any

from .semantic_assets import (
    SemanticAssetArtifact,
    SemanticAssetError,
    TtrpgSemanticAssetSnapshot,
    TtrpgSemanticAssetStore,
)
from .semantic_catalog import SemanticCatalogError, SemanticCatalogSnapshot
from .semantic_packages import AssetRef, SemanticPackage, SemanticPackageError
from .semantic_transport import (
    SemanticCatalogEnvelope,
    SemanticPackageRequest,
    SemanticTransportError,
    SnapshotSemanticAssetService,
    SnapshotSemanticPackageService,
)


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CATALOG_ENVELOPE = "catalog-envelope.json"
_CATALOG_INDEX = "catalog-index.json"
_PACKAGES = "packages"
_ASSETS = "assets"
_ASSET_INDEX = "index.json"
_ASSET_BLOBS = "blobs"
_DIRECTORY_MODE = 0o755
_FILE_MODE = 0o644


class SemanticRepositoryError(ValueError):
    """The public semantic repository is incomplete, unsafe, or unauthentic."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SemanticRepositoryError("repository JSON is not canonicalizable") from exc


def _digest(value: object, label: str) -> str:
    if type(value) is not str or not _DIGEST_RE.fullmatch(value):
        raise SemanticRepositoryError(f"{label} must be a lowercase sha256 digest")
    return value


def _exact_dict(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise SemanticRepositoryError(f"{label} must have exactly {sorted(keys)}")
    return value


def _decode_canonical_json(value: bytes, label: str) -> object:
    try:
        decoded = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemanticRepositoryError(f"{label} is not valid UTF-8 JSON") from exc
    if not hmac.compare_digest(_canonical(decoded), value):
        raise SemanticRepositoryError(f"{label} is not canonical JSON")
    return decoded


def _mode(path: Path) -> tuple[int, int]:
    try:
        details = path.lstat()
    except OSError as exc:
        raise SemanticRepositoryError(f"could not inspect repository path: {path.name}") from exc
    return details.st_mode, stat.S_IMODE(details.st_mode)


def _require_directory(path: Path, label: str, *, exact_mode: bool = True) -> None:
    file_type, permissions = _mode(path)
    if not stat.S_ISDIR(file_type):
        raise SemanticRepositoryError(f"{label} must be a regular directory")
    if exact_mode and permissions != _DIRECTORY_MODE:
        raise SemanticRepositoryError(f"{label} must have mode 755")


def _directory_entries(path: Path, label: str) -> dict[str, Path]:
    _require_directory(path, label)
    try:
        return {item.name: item for item in path.iterdir()}
    except OSError as exc:
        raise SemanticRepositoryError(f"could not inspect {label}") from exc


def _read_exact_file(path: Path, label: str) -> bytes:
    file_type, permissions = _mode(path)
    if not stat.S_ISREG(file_type):
        raise SemanticRepositoryError(f"{label} must be a regular file")
    if permissions != _FILE_MODE:
        raise SemanticRepositoryError(f"{label} must have mode 644")
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise SemanticRepositoryError(f"{label} must be a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)
    except SemanticRepositoryError:
        raise
    except OSError as exc:
        raise SemanticRepositoryError(f"could not read {label}") from exc


def _write_exact_file(path: Path, value: bytes) -> None:
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path, flags, _FILE_MODE)
        try:
            os.fchmod(descriptor, _FILE_MODE)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(value)
                stream.flush()
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise SemanticRepositoryError(
            f"could not write semantic repository file: {path.name}"
        ) from exc


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise SemanticRepositoryError(
            f"could not synchronize repository directory: {path.name}"
        ) from exc


def _asset_refs(snapshot: SemanticCatalogSnapshot) -> tuple[AssetRef, ...]:
    return tuple(
        sorted(
            {
                asset_ref
                for package in snapshot.packages
                for entity in package.entities
                for asset_ref in entity.asset_refs
            }
        )
    )


def _verified_catalog(snapshot: SemanticCatalogSnapshot) -> SemanticCatalogSnapshot:
    if not isinstance(snapshot, SemanticCatalogSnapshot):
        raise SemanticRepositoryError("repository publication requires a catalog snapshot")
    try:
        verified = SemanticCatalogSnapshot.from_selected_packages(snapshot.packages)
    except (SemanticCatalogError, SemanticPackageError) as exc:
        raise SemanticRepositoryError("semantic catalog snapshot is not authenticated") from exc
    if verified.manifest != snapshot.manifest or not hmac.compare_digest(
        verified.canonical_manifest_json(),
        snapshot.canonical_manifest_json(),
    ):
        raise SemanticRepositoryError("semantic catalog snapshot changed during verification")
    return verified


def _verified_assets(
    snapshot: TtrpgSemanticAssetSnapshot,
) -> TtrpgSemanticAssetSnapshot:
    if not isinstance(snapshot, TtrpgSemanticAssetSnapshot):
        raise SemanticRepositoryError("repository publication requires an asset snapshot")
    store = TtrpgSemanticAssetStore()
    try:
        artifacts = tuple(snapshot.artifact(asset_ref) for asset_ref in snapshot.asset_refs)
        if artifacts:
            store.publish(artifacts)
        verified = store.open_snapshot(tuple(snapshot.asset_refs))
    except (SemanticAssetError, KeyError) as exc:
        raise SemanticRepositoryError("semantic asset snapshot is not authenticated") from exc
    if verified.inventory_projection() != snapshot.inventory_projection():
        raise SemanticRepositoryError("semantic asset snapshot changed during verification")
    return verified


@dataclass(frozen=True, slots=True)
class SemanticRepository:
    """One strictly loaded provider repository and its transport services."""

    path: Path
    catalog_snapshot: SemanticCatalogSnapshot
    asset_snapshot: TtrpgSemanticAssetSnapshot
    envelope: SemanticCatalogEnvelope
    package_service: SnapshotSemanticPackageService
    asset_service: SnapshotSemanticAssetService


def _load_asset_snapshot(
    assets_directory: Path,
    expected_refs: tuple[AssetRef, ...],
) -> TtrpgSemanticAssetSnapshot:
    entries = _directory_entries(assets_directory, "semantic assets directory")
    if set(entries) != {_ASSET_INDEX, _ASSET_BLOBS}:
        raise SemanticRepositoryError(
            "semantic assets directory contains missing or extra content"
        )
    blob_entries = _directory_entries(entries[_ASSET_BLOBS], "semantic asset blobs")
    index_bytes = _read_exact_file(entries[_ASSET_INDEX], "semantic asset index")
    index = _exact_dict(
        _decode_canonical_json(index_bytes, "semantic asset index"),
        {"schema", "snapshotDigest", "assets"},
        "semantic asset index",
    )
    if index["schema"] != 1 or type(index["assets"]) is not list:
        raise SemanticRepositoryError("semantic asset index schema or assets is invalid")

    artifacts: list[SemanticAssetArtifact] = []
    for item in index["assets"]:
        manifest = _exact_dict(
            item,
            {"schema", "assetRef", "mediaType", "size", "sha256"},
            "semantic asset metadata",
        )
        if manifest["schema"] != 1:
            raise SemanticRepositoryError("semantic asset metadata schema must be 1")
        try:
            asset_ref = AssetRef.from_dict(manifest["assetRef"])
        except SemanticPackageError as exc:
            raise SemanticRepositoryError("semantic asset reference is invalid") from exc
        body_name = _digest(manifest["sha256"], "semantic asset sha256")
        body_path = blob_entries.get(body_name)
        if body_path is None:
            raise SemanticRepositoryError("semantic asset blob closure is incomplete")
        body = _read_exact_file(body_path, f"semantic asset blob {body_name}")
        try:
            artifact = SemanticAssetArtifact(
                asset_ref=asset_ref,
                media_type=manifest["mediaType"],
                asset_bytes=body,
                size=manifest["size"],
                sha256_digest=body_name,
            )
        except SemanticAssetError as exc:
            raise SemanticRepositoryError("semantic asset failed authentication") from exc
        if artifact.manifest_dict() != manifest:
            raise SemanticRepositoryError("semantic asset metadata failed exact verification")
        artifacts.append(artifact)

    expected_blob_names = {artifact.sha256_digest for artifact in artifacts}
    if set(blob_entries) != expected_blob_names:
        raise SemanticRepositoryError("semantic asset blobs contain missing or extra content")
    store = TtrpgSemanticAssetStore()
    try:
        if artifacts:
            store.publish(tuple(artifacts))
        snapshot = store.open_snapshot(tuple(expected_refs))
    except SemanticAssetError as exc:
        raise SemanticRepositoryError("semantic asset closure is invalid") from exc
    if snapshot.inventory_projection() != index:
        raise SemanticRepositoryError("semantic asset index failed exact verification")
    return snapshot


def _load_semantic_repository(
    repository_directory: Path,
    *,
    expected_catalog_digest: str | None = None,
) -> SemanticRepository:
    _require_directory(repository_directory, "semantic repository")
    entries = _directory_entries(repository_directory, "semantic repository")
    if set(entries) != {
        _CATALOG_ENVELOPE,
        _CATALOG_INDEX,
        _PACKAGES,
        _ASSETS,
    }:
        raise SemanticRepositoryError(
            "semantic repository contains missing or extra content"
        )

    directory_digest = _digest(
        expected_catalog_digest or repository_directory.name,
        "semantic repository directory name",
    )
    envelope_bytes = _read_exact_file(
        entries[_CATALOG_ENVELOPE], "semantic catalog envelope"
    )
    index_bytes = _read_exact_file(entries[_CATALOG_INDEX], "semantic catalog index")
    try:
        envelope = SemanticCatalogEnvelope.from_dict(
            _decode_canonical_json(envelope_bytes, "semantic catalog envelope")
        )
    except SemanticTransportError as exc:
        raise SemanticRepositoryError("semantic catalog envelope is invalid") from exc
    if not hmac.compare_digest(directory_digest, envelope.catalog_digest):
        raise SemanticRepositoryError(
            "semantic repository directory does not match its catalog digest"
        )

    package_entries = _directory_entries(entries[_PACKAGES], "semantic packages")
    if len({request.package_digest for request in envelope.package_requests}) != len(
        envelope.package_requests
    ):
        raise SemanticRepositoryError("semantic package bodies must have unique digests")
    expected_package_names = {
        f"{request.package_digest}.json" for request in envelope.package_requests
    }
    if set(package_entries) != expected_package_names:
        raise SemanticRepositoryError(
            "semantic packages directory contains missing or extra content"
        )
    packages: list[SemanticPackage] = []
    for request in envelope.package_requests:
        filename = f"{request.package_digest}.json"
        package_bytes = _read_exact_file(
            package_entries[filename], f"semantic package {filename}"
        )
        packet = _decode_canonical_json(package_bytes, f"semantic package {filename}")
        try:
            package = SemanticPackage.from_dict(packet)
            actual_request = SemanticPackageRequest.from_package(package)
        except (SemanticPackageError, SemanticTransportError) as exc:
            raise SemanticRepositoryError("semantic package failed authentication") from exc
        if actual_request != request or not hmac.compare_digest(
            package.canonical_json(), package_bytes
        ):
            raise SemanticRepositoryError("semantic package does not match its index")
        packages.append(package)

    try:
        catalog_snapshot = SemanticCatalogSnapshot.from_selected_packages(tuple(packages))
    except SemanticCatalogError as exc:
        raise SemanticRepositoryError("semantic catalog package closure is invalid") from exc
    canonical_index = catalog_snapshot.canonical_manifest_json()
    _decode_canonical_json(index_bytes, "semantic catalog index")
    if not hmac.compare_digest(canonical_index, index_bytes):
        raise SemanticRepositoryError("semantic catalog index failed exact verification")
    expected_envelope = SemanticCatalogEnvelope.from_snapshot(catalog_snapshot)
    if expected_envelope != envelope or not hmac.compare_digest(
        _canonical(envelope.to_dict()), envelope_bytes
    ):
        raise SemanticRepositoryError("semantic catalog envelope failed exact verification")

    expected_asset_refs = _asset_refs(catalog_snapshot)
    if envelope.asset_refs != expected_asset_refs:
        raise SemanticRepositoryError("semantic catalog asset closure is invalid")
    asset_snapshot = _load_asset_snapshot(entries[_ASSETS], expected_asset_refs)
    return SemanticRepository(
        path=repository_directory,
        catalog_snapshot=catalog_snapshot,
        asset_snapshot=asset_snapshot,
        envelope=envelope,
        package_service=SnapshotSemanticPackageService(catalog_snapshot),
        asset_service=SnapshotSemanticAssetService(asset_snapshot),
    )


def load_semantic_repository(
    repository_directory: str | os.PathLike[str],
) -> SemanticRepository:
    """Strictly reopen one catalog-digest-named public repository."""

    return _load_semantic_repository(Path(repository_directory))


def _same_repository(
    repository: SemanticRepository,
    catalog: SemanticCatalogSnapshot,
    assets: TtrpgSemanticAssetSnapshot,
) -> bool:
    if not hmac.compare_digest(
        repository.catalog_snapshot.canonical_manifest_json(),
        catalog.canonical_manifest_json(),
    ) or repository.asset_snapshot.inventory_projection() != assets.inventory_projection():
        return False
    for package in catalog.packages:
        request = SemanticPackageRequest.from_package(package)
        if not hmac.compare_digest(
            repository.package_service.fetch_package(request).canonical_package_bytes,
            package.canonical_json(),
        ):
            return False
    for asset_ref in assets.asset_refs:
        if not hmac.compare_digest(
            repository.asset_service.fetch_asset(asset_ref).asset_bytes,
            assets.artifact(asset_ref).asset_bytes,
        ):
            return False
    return True


def _prepare_root(root: Path) -> None:
    if root.is_symlink():
        raise SemanticRepositoryError("semantic repository root must not be a symbolic link")
    try:
        if not root.exists():
            root.mkdir(parents=True, mode=_DIRECTORY_MODE)
            root.chmod(_DIRECTORY_MODE)
    except OSError as exc:
        raise SemanticRepositoryError("could not prepare semantic repository root") from exc
    _require_directory(root, "semantic repository root", exact_mode=False)
    _, permissions = _mode(root)
    if permissions & 0o022:
        raise SemanticRepositoryError(
            "semantic repository root must not be group- or world-writable"
        )


def write_semantic_repository(
    repository_root: str | os.PathLike[str],
    *,
    catalog: SemanticCatalogSnapshot,
    assets: TtrpgSemanticAssetSnapshot,
) -> Path:
    """Atomically publish one exact public catalog without replacing content.

    The destination is ``repository_root / catalog.catalog_digest``.  An
    already-present exact repository is validation-only and returned unchanged;
    any disagreement or unsafe boundary fails closed.
    """

    verified_catalog = _verified_catalog(catalog)
    verified_assets = _verified_assets(assets)
    required_assets = _asset_refs(verified_catalog)
    if verified_assets.asset_refs != required_assets:
        raise SemanticRepositoryError(
            "semantic assets must exactly close the catalog asset references"
        )
    envelope = SemanticCatalogEnvelope.from_snapshot(verified_catalog)
    envelope_bytes = _canonical(envelope.to_dict())
    catalog_index_bytes = verified_catalog.canonical_manifest_json()
    asset_index_bytes = _canonical(verified_assets.inventory_projection())

    root = Path(repository_root)
    _prepare_root(root)
    destination = root / verified_catalog.catalog_digest
    if destination.exists() or destination.is_symlink():
        existing = load_semantic_repository(destination)
        if _same_repository(existing, verified_catalog, verified_assets):
            return destination
        raise SemanticRepositoryError("semantic repository destination already exists")

    claim = root / f".{verified_catalog.catalog_digest}.publish"
    claim_descriptor: int | None = None
    stage: Path | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        claim_descriptor = os.open(claim, flags, 0o600)
        os.fsync(claim_descriptor)
        if destination.exists() or destination.is_symlink():
            existing = load_semantic_repository(destination)
            if _same_repository(existing, verified_catalog, verified_assets):
                return destination
            raise SemanticRepositoryError("semantic repository destination already exists")

        stage = Path(
            tempfile.mkdtemp(
                prefix=f".{verified_catalog.catalog_digest}.",
                dir=root,
            )
        )
        stage.chmod(_DIRECTORY_MODE)
        packages_directory = stage / _PACKAGES
        packages_directory.mkdir(mode=_DIRECTORY_MODE)
        packages_directory.chmod(_DIRECTORY_MODE)
        assets_directory = stage / _ASSETS
        assets_directory.mkdir(mode=_DIRECTORY_MODE)
        assets_directory.chmod(_DIRECTORY_MODE)
        blobs_directory = assets_directory / _ASSET_BLOBS
        blobs_directory.mkdir(mode=_DIRECTORY_MODE)
        blobs_directory.chmod(_DIRECTORY_MODE)

        _write_exact_file(stage / _CATALOG_ENVELOPE, envelope_bytes)
        _write_exact_file(stage / _CATALOG_INDEX, catalog_index_bytes)
        for package in verified_catalog.packages:
            _write_exact_file(
                packages_directory / f"{package.package_digest}.json",
                package.canonical_json(),
            )
        _write_exact_file(assets_directory / _ASSET_INDEX, asset_index_bytes)
        written_blobs: set[str] = set()
        for asset_ref in verified_assets.asset_refs:
            artifact = verified_assets.artifact(asset_ref)
            if artifact.sha256_digest in written_blobs:
                continue
            _write_exact_file(
                blobs_directory / artifact.sha256_digest,
                artifact.asset_bytes,
            )
            written_blobs.add(artifact.sha256_digest)

        for directory in (
            packages_directory,
            blobs_directory,
            assets_directory,
            stage,
        ):
            _fsync_directory(directory)
        staged = _load_semantic_repository(
            stage,
            expected_catalog_digest=verified_catalog.catalog_digest,
        )
        if not _same_repository(staged, verified_catalog, verified_assets):
            raise SemanticRepositoryError(
                "staged semantic repository changed during verification"
            )
        if destination.exists() or destination.is_symlink():
            raise SemanticRepositoryError("semantic repository destination already exists")
        os.rename(stage, destination)
        stage = None
        _fsync_directory(root)
        return destination
    except SemanticRepositoryError:
        raise
    except FileExistsError as exc:
        raise SemanticRepositoryError("semantic repository publication is already active") from exc
    except OSError as exc:
        raise SemanticRepositoryError(
            "could not atomically publish semantic repository"
        ) from exc
    finally:
        if claim_descriptor is not None:
            os.close(claim_descriptor)
        try:
            if claim.exists() or claim.is_symlink():
                claim.unlink()
                _fsync_directory(root)
        except (OSError, SemanticRepositoryError):
            pass
        if stage is not None:
            try:
                if stage.is_symlink():
                    stage.unlink()
                elif stage.exists():
                    shutil.rmtree(stage)
            except OSError:
                pass


__all__ = [
    "SemanticRepository",
    "SemanticRepositoryError",
    "load_semantic_repository",
    "write_semantic_repository",
]

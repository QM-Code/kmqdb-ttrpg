"""Transport-neutral publication contract for TTRPG semantics and assets.

The catalog envelope contains only exact semantic-package identities and
opaque asset references.  Package bodies are the canonical bytes already
sealed by :mod:`semantic_packages`; source acquisition and compilation are not
part of this service boundary.  Asset bodies are served only through an exact
public reference bound by :mod:`semantic_assets`.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import json
import re
from types import MappingProxyType
from typing import Protocol

from .semantic_assets import SemanticAssetArtifact, TtrpgSemanticAssetSnapshot
from .semantic_catalog import SemanticCatalogSnapshot
from .semantic_packages import AssetRef, SemanticPackage, SemanticPackageError


SEMANTIC_PACKAGE_MEDIA_TYPE = (
    "application/vnd.kmqdb.ttrpg-semantic-package+json;version=1"
)

_ID_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*:[a-z0-9]+"
    r"(?:[._-][a-z0-9]+)*$"
)
_VERSION_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SemanticTransportError(ValueError):
    """A semantic catalog transport value is invalid or unavailable."""


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or not _ID_RE.fullmatch(value):
        raise SemanticTransportError(f"{label} must be a normalized namespaced ID")
    return value


def _version(value: object) -> str:
    if type(value) is not str or not _VERSION_RE.fullmatch(value):
        raise SemanticTransportError("package version must be a normalized x.y.z version")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or not _DIGEST_RE.fullmatch(value):
        raise SemanticTransportError(f"{label} must be a lowercase sha256 digest")
    return value


def _exact_dict(value: object, keys: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise SemanticTransportError(f"{label} must have exactly {sorted(keys)}")
    return value


@dataclass(frozen=True, order=True)
class SemanticPackageRequest:
    """The complete immutable identity needed to fetch one package artifact."""

    package_id: str
    version: str
    package_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "package_id", _identifier(self.package_id, "packageId"))
        object.__setattr__(self, "version", _version(self.version))
        object.__setattr__(
            self,
            "package_digest",
            _digest(self.package_digest, "packageDigest"),
        )

    @classmethod
    def from_package(cls, package: SemanticPackage) -> SemanticPackageRequest:
        if not isinstance(package, SemanticPackage):
            raise SemanticTransportError("package request requires a SemanticPackage")
        return cls(package.package_id, package.version, package.package_digest)

    @classmethod
    def from_dict(cls, value: object) -> SemanticPackageRequest:
        packet = _exact_dict(
            value,
            {"packageId", "version", "packageDigest"},
            "semantic package request",
        )
        return cls(
            package_id=packet["packageId"],  # type: ignore[arg-type]
            version=packet["version"],  # type: ignore[arg-type]
            package_digest=packet["packageDigest"],  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "packageId": self.package_id,
            "version": self.version,
            "packageDigest": self.package_digest,
        }


def _package_asset_refs(package: SemanticPackage) -> tuple[AssetRef, ...]:
    return tuple(
        sorted(
            {
                asset
                for entity in package.entities
                for asset in entity.asset_refs
            }
        )
    )


@dataclass(frozen=True)
class SemanticPackageArtifact:
    """One exact canonical package response and its opaque asset inventory."""

    request: SemanticPackageRequest
    canonical_package_bytes: bytes
    asset_refs: tuple[AssetRef, ...]
    media_type: str = SEMANTIC_PACKAGE_MEDIA_TYPE

    def __post_init__(self) -> None:
        if not isinstance(self.request, SemanticPackageRequest):
            raise SemanticTransportError("package artifact requires an exact request")
        if type(self.canonical_package_bytes) is not bytes:
            raise SemanticTransportError("package artifact body must be bytes")
        if self.media_type != SEMANTIC_PACKAGE_MEDIA_TYPE:
            raise SemanticTransportError("semantic package media type is unsupported")
        if not all(isinstance(item, AssetRef) for item in self.asset_refs):
            raise SemanticTransportError("package artifact asset references are invalid")
        ordered_assets = tuple(sorted(set(self.asset_refs)))
        if len(ordered_assets) != len(self.asset_refs):
            raise SemanticTransportError("package artifact asset references contain duplicates")
        object.__setattr__(self, "asset_refs", ordered_assets)
        try:
            packet = json.loads(self.canonical_package_bytes.decode("utf-8"))
            package = SemanticPackage.from_dict(packet)
        except (UnicodeDecodeError, json.JSONDecodeError, SemanticPackageError) as exc:
            raise SemanticTransportError("package artifact body is invalid") from exc
        if SemanticPackageRequest.from_package(package) != self.request:
            raise SemanticTransportError("package artifact does not match its exact request")
        if not hmac.compare_digest(
            package.canonical_json(), self.canonical_package_bytes
        ):
            raise SemanticTransportError("package artifact body is not canonical")
        if _package_asset_refs(package) != self.asset_refs:
            raise SemanticTransportError("package artifact asset inventory does not match")

    @classmethod
    def from_package(cls, package: SemanticPackage) -> SemanticPackageArtifact:
        if not isinstance(package, SemanticPackage):
            raise SemanticTransportError("package artifact requires a SemanticPackage")
        return cls(
            request=SemanticPackageRequest.from_package(package),
            canonical_package_bytes=package.canonical_json(),
            asset_refs=_package_asset_refs(package),
        )


@dataclass(frozen=True, init=False)
class SemanticCatalogEnvelope:
    """Selected catalog identity sufficient for exact package provisioning."""

    catalog_digest: str
    package_requests: tuple[SemanticPackageRequest, ...]
    asset_refs: tuple[AssetRef, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("SemanticCatalogEnvelope is sealed; use a factory")

    @classmethod
    def _sealed(
        cls,
        *,
        catalog_digest: str,
        package_requests: tuple[SemanticPackageRequest, ...],
        asset_refs: tuple[AssetRef, ...],
    ) -> SemanticCatalogEnvelope:
        if not package_requests:
            raise SemanticTransportError("catalog envelope requires package requests")
        if len(set(package_requests)) != len(package_requests):
            raise SemanticTransportError("catalog envelope contains duplicate packages")
        if len(set(asset_refs)) != len(asset_refs):
            raise SemanticTransportError("catalog envelope contains duplicate assets")
        envelope = object.__new__(cls)
        object.__setattr__(envelope, "catalog_digest", _digest(catalog_digest, "catalogDigest"))
        object.__setattr__(envelope, "package_requests", tuple(sorted(package_requests)))
        object.__setattr__(envelope, "asset_refs", tuple(sorted(asset_refs)))
        return envelope

    @classmethod
    def from_snapshot(
        cls,
        snapshot: SemanticCatalogSnapshot,
    ) -> SemanticCatalogEnvelope:
        if not isinstance(snapshot, SemanticCatalogSnapshot):
            raise SemanticTransportError("catalog envelope requires an authenticated snapshot")
        packages = tuple(snapshot.packages)
        return cls._sealed(
            catalog_digest=snapshot.catalog_digest,
            package_requests=tuple(
                SemanticPackageRequest.from_package(package) for package in packages
            ),
            asset_refs=tuple(
                sorted(
                    {
                        asset
                        for package in packages
                        for asset in _package_asset_refs(package)
                    }
                )
            ),
        )

    @classmethod
    def from_dict(cls, value: object) -> SemanticCatalogEnvelope:
        packet = _exact_dict(
            value,
            {"schema", "catalogDigest", "packages", "assetRefs"},
            "semantic catalog envelope",
        )
        if packet["schema"] != 1:
            raise SemanticTransportError("semantic catalog envelope schema must be 1")
        packages = packet["packages"]
        assets = packet["assetRefs"]
        if type(packages) is not list or type(assets) is not list:
            raise SemanticTransportError("catalog packages and assets must be lists")
        return cls._sealed(
            catalog_digest=packet["catalogDigest"],  # type: ignore[arg-type]
            package_requests=tuple(
                SemanticPackageRequest.from_dict(item) for item in packages
            ),
            asset_refs=tuple(AssetRef.from_dict(item) for item in assets),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": 1,
            "catalogDigest": self.catalog_digest,
            "packages": [item.to_dict() for item in self.package_requests],
            "assetRefs": [item.to_dict() for item in self.asset_refs],
        }


class SemanticPackageService(Protocol):
    """TTRPG authority port implemented by local and future HTTP services."""

    def fetch_package(
        self,
        request: SemanticPackageRequest,
    ) -> SemanticPackageArtifact:
        """Return exactly the requested immutable semantic package."""


class SemanticAssetService(Protocol):
    """TTRPG authority port for exact source-free asset artifacts."""

    def fetch_asset(self, asset_ref: AssetRef) -> SemanticAssetArtifact:
        """Return exactly the requested immutable semantic asset."""


class SnapshotSemanticPackageService:
    """Minimal in-process service over one authenticated catalog snapshot."""

    __slots__ = ("_artifacts",)

    def __init__(self, snapshot: SemanticCatalogSnapshot) -> None:
        if not isinstance(snapshot, SemanticCatalogSnapshot):
            raise SemanticTransportError("semantic package service requires a snapshot")
        artifacts = {
            SemanticPackageRequest.from_package(package):
                SemanticPackageArtifact.from_package(package)
            for package in snapshot.packages
        }
        self._artifacts = MappingProxyType(artifacts)

    def fetch_package(
        self,
        request: SemanticPackageRequest,
    ) -> SemanticPackageArtifact:
        if not isinstance(request, SemanticPackageRequest):
            raise SemanticTransportError("package fetch requires an exact request")
        try:
            return self._artifacts[request]
        except KeyError as exc:
            raise SemanticTransportError("exact semantic package is unavailable") from exc


class SnapshotSemanticAssetService:
    """Minimal in-process service over one immutable TTRPG asset snapshot."""

    __slots__ = ("_artifacts",)

    def __init__(self, snapshot: TtrpgSemanticAssetSnapshot) -> None:
        if not isinstance(snapshot, TtrpgSemanticAssetSnapshot):
            raise SemanticTransportError("semantic asset service requires a snapshot")
        self._artifacts = MappingProxyType(
            {asset_ref: snapshot.artifact(asset_ref) for asset_ref in snapshot.asset_refs}
        )

    def fetch_asset(self, asset_ref: AssetRef) -> SemanticAssetArtifact:
        if not isinstance(asset_ref, AssetRef):
            raise SemanticTransportError("asset fetch requires an exact AssetRef")
        try:
            return self._artifacts[asset_ref]
        except KeyError as exc:
            raise SemanticTransportError("exact semantic asset is unavailable") from exc


__all__ = [
    "SEMANTIC_PACKAGE_MEDIA_TYPE",
    "SemanticAssetService",
    "SemanticCatalogEnvelope",
    "SemanticPackageArtifact",
    "SemanticPackageRequest",
    "SemanticPackageService",
    "SemanticTransportError",
    "SnapshotSemanticAssetService",
    "SnapshotSemanticPackageService",
]

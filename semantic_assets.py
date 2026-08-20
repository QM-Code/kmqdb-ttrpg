"""Source-free semantic asset artifacts and TTRPG-owned immutable storage.

Semantic packages refer to assets only through :class:`AssetRef`.  This
module binds those public references to exact bytes without exposing how the
TTRPG service acquired or stores the underlying Library asset.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from types import MappingProxyType
from typing import Mapping

from .semantic_packages import AssetRef


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE_RE = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$"
)


class SemanticAssetError(ValueError):
    """A public semantic asset artifact or TTRPG asset store is invalid."""


def _digest(value: object, label: str) -> str:
    if type(value) is not str or not _DIGEST_RE.fullmatch(value):
        raise SemanticAssetError(f"{label} must be a lowercase sha256 digest")
    return value


def _media_type(value: object) -> str:
    if type(value) is not str or not _MEDIA_TYPE_RE.fullmatch(value):
        raise SemanticAssetError("mediaType must be a normalized media type")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _projection_digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class SemanticAssetArtifact:
    """One exact source-free public asset response.

    ``sha256_digest`` is intentionally explicit on the transport artifact as
    well as inside ``asset_ref``.  The duplicated value makes the byte
    authentication contract unambiguous while construction rejects any
    disagreement between the reference, declared digest, size, and body.
    """

    asset_ref: AssetRef
    media_type: str
    asset_bytes: bytes
    size: int
    sha256_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.asset_ref, AssetRef):
            raise SemanticAssetError("semantic asset requires an exact AssetRef")
        object.__setattr__(self, "media_type", _media_type(self.media_type))
        if type(self.asset_bytes) is not bytes:
            raise SemanticAssetError("semantic asset body must be exact bytes")
        if type(self.size) is not int or self.size < 0:
            raise SemanticAssetError("semantic asset size must be a nonnegative integer")
        if self.size != len(self.asset_bytes):
            raise SemanticAssetError("semantic asset size does not match its body")
        declared_digest = _digest(self.sha256_digest, "sha256")
        actual_digest = hashlib.sha256(self.asset_bytes).hexdigest()
        if not hmac.compare_digest(declared_digest, actual_digest):
            raise SemanticAssetError("semantic asset sha256 does not match its body")
        if not hmac.compare_digest(self.asset_ref.asset_digest, declared_digest):
            raise SemanticAssetError("semantic asset digest does not match its AssetRef")

    @classmethod
    def from_bytes(
        cls,
        asset_ref: AssetRef,
        media_type: str,
        asset_bytes: bytes,
    ) -> SemanticAssetArtifact:
        if type(asset_bytes) is not bytes:
            raise SemanticAssetError("semantic asset body must be exact bytes")
        digest = hashlib.sha256(asset_bytes).hexdigest()
        return cls(
            asset_ref=asset_ref,
            media_type=media_type,
            asset_bytes=asset_bytes,
            size=len(asset_bytes),
            sha256_digest=digest,
        )

    def manifest_dict(self) -> dict[str, object]:
        """Return the source-free byte-authentication metadata."""

        return {
            "schema": 1,
            "assetRef": self.asset_ref.to_dict(),
            "mediaType": self.media_type,
            "size": self.size,
            "sha256": self.sha256_digest,
        }

    def canonical_manifest_json(self) -> bytes:
        """Return deterministic metadata bytes; the asset body stays opaque."""

        return _canonical(self.manifest_dict())


def _verified_copy(artifact: SemanticAssetArtifact) -> SemanticAssetArtifact:
    if not isinstance(artifact, SemanticAssetArtifact):
        raise SemanticAssetError("semantic asset store requires asset artifacts")
    return SemanticAssetArtifact(
        asset_ref=artifact.asset_ref,
        media_type=artifact.media_type,
        asset_bytes=artifact.asset_bytes,
        size=artifact.size,
        sha256_digest=artifact.sha256_digest,
    )


@dataclass(frozen=True, slots=True, init=False)
class TtrpgSemanticAssetSnapshot:
    """One immutable exact-byte view published by the TTRPG asset store."""

    asset_refs: tuple[AssetRef, ...]
    snapshot_digest: str
    _artifacts: Mapping[AssetRef, SemanticAssetArtifact]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("TtrpgSemanticAssetSnapshot instances must be opened by a store")

    def artifact(self, asset_ref: AssetRef) -> SemanticAssetArtifact:
        if not isinstance(asset_ref, AssetRef):
            raise SemanticAssetError("asset lookup requires an exact AssetRef")
        try:
            return self._artifacts[asset_ref]
        except KeyError as exc:
            raise KeyError(asset_ref) from exc

    def inventory_projection(self) -> dict[str, object]:
        return {
            "schema": 1,
            "snapshotDigest": self.snapshot_digest,
            "assets": [
                self._artifacts[asset_ref].manifest_dict()
                for asset_ref in self.asset_refs
            ],
        }


def _create_snapshot(
    asset_refs: tuple[AssetRef, ...],
    artifacts: Mapping[AssetRef, SemanticAssetArtifact],
) -> TtrpgSemanticAssetSnapshot:
    projection = {
        "schema": 1,
        "assets": [artifacts[asset_ref].manifest_dict() for asset_ref in asset_refs],
    }
    snapshot = object.__new__(TtrpgSemanticAssetSnapshot)
    object.__setattr__(snapshot, "asset_refs", asset_refs)
    object.__setattr__(snapshot, "snapshot_digest", _projection_digest(projection))
    object.__setattr__(snapshot, "_artifacts", MappingProxyType(dict(artifacts)))
    return snapshot


class TtrpgSemanticAssetStore:
    """TTRPG-owned copy-on-write storage for public semantic asset bytes."""

    __slots__ = ("__artifacts", "__ref_by_asset_id")

    def __init__(self) -> None:
        object.__setattr__(
            self,
            "_TtrpgSemanticAssetStore__artifacts",
            MappingProxyType({}),
        )
        object.__setattr__(
            self,
            "_TtrpgSemanticAssetStore__ref_by_asset_id",
            MappingProxyType({}),
        )

    def publish(
        self,
        artifacts: tuple[SemanticAssetArtifact, ...],
    ) -> tuple[AssetRef, ...]:
        """Atomically add an exact artifact batch without permitting replacement."""

        if not isinstance(artifacts, tuple):
            raise SemanticAssetError("asset publication must be an explicit tuple")
        if not artifacts:
            raise SemanticAssetError("asset publication must not be empty")
        verified = tuple(_verified_copy(artifact) for artifact in artifacts)
        refs = tuple(artifact.asset_ref for artifact in verified)
        if len(set(refs)) != len(refs):
            raise SemanticAssetError("asset publication contains duplicate references")
        asset_ids = tuple(ref.asset_id for ref in refs)
        if len(set(asset_ids)) != len(asset_ids):
            raise SemanticAssetError("asset publication contains duplicate asset IDs")

        next_artifacts = dict(self.__artifacts)
        next_refs = dict(self.__ref_by_asset_id)
        for artifact in verified:
            asset_ref = artifact.asset_ref
            prior_ref = next_refs.get(asset_ref.asset_id)
            if prior_ref is not None and prior_ref != asset_ref:
                raise SemanticAssetError("semantic asset replacement is not permitted")
            prior = next_artifacts.get(asset_ref)
            if prior is not None:
                if (
                    prior.media_type != artifact.media_type
                    or prior.size != artifact.size
                    or not hmac.compare_digest(prior.asset_bytes, artifact.asset_bytes)
                ):
                    raise SemanticAssetError("published semantic asset bytes do not match")
                continue
            next_artifacts[asset_ref] = artifact
            next_refs[asset_ref.asset_id] = asset_ref

        object.__setattr__(
            self,
            "_TtrpgSemanticAssetStore__artifacts",
            MappingProxyType(next_artifacts),
        )
        object.__setattr__(
            self,
            "_TtrpgSemanticAssetStore__ref_by_asset_id",
            MappingProxyType(next_refs),
        )
        return tuple(sorted(refs))

    def open_snapshot(
        self,
        asset_refs: tuple[AssetRef, ...],
    ) -> TtrpgSemanticAssetSnapshot:
        if not isinstance(asset_refs, tuple):
            raise SemanticAssetError("asset selection must be an explicit tuple")
        if not all(isinstance(asset_ref, AssetRef) for asset_ref in asset_refs):
            raise SemanticAssetError("asset selection contains an invalid reference")
        if len(set(asset_refs)) != len(asset_refs):
            raise SemanticAssetError("asset selection contains duplicate references")
        ordered_refs = tuple(sorted(asset_refs))
        selected: dict[AssetRef, SemanticAssetArtifact] = {}
        for asset_ref in ordered_refs:
            try:
                artifact = self.__artifacts[asset_ref]
            except KeyError as exc:
                raise SemanticAssetError(
                    f"semantic asset is not published: {asset_ref.asset_id}"
                ) from exc
            selected[asset_ref] = _verified_copy(artifact)
        return _create_snapshot(ordered_refs, selected)

    def inventory_projection(self) -> dict[str, object]:
        refs = tuple(sorted(self.__artifacts))
        projection = {
            "schema": 1,
            "assets": [self.__artifacts[ref].manifest_dict() for ref in refs],
        }
        return {**projection, "inventoryDigest": _projection_digest(projection)}


__all__ = [
    "SemanticAssetArtifact",
    "SemanticAssetError",
    "TtrpgSemanticAssetSnapshot",
    "TtrpgSemanticAssetStore",
]

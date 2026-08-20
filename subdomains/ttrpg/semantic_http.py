"""Versioned HTTP publication boundary for exact TTRPG semantic artifacts.

This WSGI application is deliberately only a transport adapter over the
authenticated catalog envelope and transport-neutral package and asset
services.  It has no source, compiler, cache, backend, or game-runtime
dependency.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import json
import re
from typing import Any
from urllib.parse import parse_qsl

from .semantic_assets import SemanticAssetArtifact, SemanticAssetError
from .semantic_packages import AssetRef, SemanticPackageError
from .semantic_transport import (
    SemanticAssetService,
    SemanticCatalogEnvelope,
    SemanticPackageArtifact,
    SemanticPackageRequest,
    SemanticPackageService,
    SemanticTransportError,
)


ENVELOPE_ROUTE = "/.api/catalog/v1/envelope"
PACKAGE_ROUTE = "/.api/catalog/v1/package"
ASSET_ROUTE = "/.api/catalog/v1/asset"
IMMUTABLE_CACHE_CONTROL = "public,max-age=31536000,immutable"
ERROR_MEDIA_TYPE = "application/json"
SEMANTIC_CATALOG_MEDIA_TYPE = (
    "application/vnd.kmqdb.ttrpg-semantic-catalog+json;version=1"
)

_ENVELOPE_QUERY_KEYS = frozenset({"catalogDigest"})
_PACKAGE_QUERY_KEYS = frozenset({"packageId", "version", "packageDigest"})
_ASSET_QUERY_KEYS = frozenset({"assetId", "assetDigest"})
_BAD_PERCENT_ESCAPE_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_STATUS_TEXT = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}

StartResponse = Callable[[str, list[tuple[str, str]]], Any]


class _MalformedRequest(ValueError):
    pass


class _InvalidServiceArtifact(RuntimeError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _start(
    start_response: StartResponse,
    status: int,
    headers: list[tuple[str, str]],
) -> None:
    start_response(f"{status} {_STATUS_TEXT[status]}", headers)


def _error_response(
    start_response: StartResponse,
    status: int,
    error: str,
    *,
    head: bool = False,
    extra_headers: tuple[tuple[str, str], ...] = (),
) -> list[bytes]:
    body = _canonical_json({"error": error})
    headers = [
        ("Content-Type", ERROR_MEDIA_TYPE),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        *extra_headers,
    ]
    _start(start_response, status, headers)
    return [] if head else [body]


def _success_response(
    start_response: StartResponse,
    body: bytes,
    media_type: str,
    digest: str,
    identity_headers: tuple[tuple[str, str], ...],
    *,
    head: bool,
) -> list[bytes]:
    headers = [
        ("Content-Type", media_type),
        ("Content-Length", str(len(body))),
        ("Cache-Control", IMMUTABLE_CACHE_CONTROL),
        ("ETag", f'"{digest}"'),
        *identity_headers,
        ("X-Content-Type-Options", "nosniff"),
    ]
    _start(start_response, 200, headers)
    return [] if head else [body]


def _exact_query(
    environ: Mapping[str, object],
    expected_keys: frozenset[str],
) -> dict[str, str]:
    raw_query = environ.get("QUERY_STRING", "")
    if type(raw_query) is not str or len(raw_query) > 4096:
        raise _MalformedRequest("query is invalid")
    if _BAD_PERCENT_ESCAPE_RE.search(raw_query):
        raise _MalformedRequest("query contains an invalid percent escape")
    try:
        pairs = parse_qsl(
            raw_query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=len(expected_keys) + 1,
            separator="&",
        )
    except (UnicodeError, ValueError) as exc:
        raise _MalformedRequest("query is malformed") from exc
    keys = [key for key, _ in pairs]
    if len(pairs) != len(expected_keys) or set(keys) != expected_keys:
        raise _MalformedRequest("query must contain each exact key once")
    return dict(pairs)


def _validated_package_artifact(
    service: SemanticPackageService,
    request: SemanticPackageRequest,
) -> SemanticPackageArtifact:
    artifact = service.fetch_package(request)
    if not isinstance(artifact, SemanticPackageArtifact):
        raise _InvalidServiceArtifact("package service returned an invalid artifact")
    try:
        validated = SemanticPackageArtifact(
            request=artifact.request,
            canonical_package_bytes=artifact.canonical_package_bytes,
            asset_refs=artifact.asset_refs,
            media_type=artifact.media_type,
        )
    except (SemanticTransportError, TypeError, ValueError) as exc:
        raise _InvalidServiceArtifact(
            "package service returned an invalid artifact"
        ) from exc
    if validated.request != request:
        raise _InvalidServiceArtifact("package service returned a different artifact")
    return validated


def _validated_asset_artifact(
    service: SemanticAssetService,
    asset_ref: AssetRef,
) -> SemanticAssetArtifact:
    artifact = service.fetch_asset(asset_ref)
    if not isinstance(artifact, SemanticAssetArtifact):
        raise _InvalidServiceArtifact("asset service returned an invalid artifact")
    try:
        validated = SemanticAssetArtifact(
            asset_ref=artifact.asset_ref,
            media_type=artifact.media_type,
            asset_bytes=artifact.asset_bytes,
            size=artifact.size,
            sha256_digest=artifact.sha256_digest,
        )
    except (SemanticAssetError, SemanticPackageError, TypeError, ValueError) as exc:
        raise _InvalidServiceArtifact(
            "asset service returned an invalid artifact"
        ) from exc
    if validated.asset_ref != asset_ref:
        raise _InvalidServiceArtifact("asset service returned a different artifact")
    return validated


def _validated_envelope(
    envelope: SemanticCatalogEnvelope,
) -> tuple[SemanticCatalogEnvelope, bytes]:
    if not isinstance(envelope, SemanticCatalogEnvelope):
        raise TypeError("envelope must be an authenticated SemanticCatalogEnvelope")
    try:
        canonical_bytes = _canonical_json(envelope.to_dict())
        decoded = json.loads(canonical_bytes.decode("utf-8"))
        validated = SemanticCatalogEnvelope.from_dict(decoded)
        validated_bytes = _canonical_json(validated.to_dict())
    except (UnicodeError, ValueError, TypeError, SemanticTransportError) as exc:
        raise TypeError(
            "envelope must be an authenticated SemanticCatalogEnvelope"
        ) from exc
    if validated != envelope or validated_bytes != canonical_bytes:
        raise TypeError("semantic catalog envelope is not canonical")
    return validated, validated_bytes


class SemanticCatalogHttpApplication:
    """Strict WSGI adapter for one immutable catalog closure."""

    __slots__ = (
        "_envelope",
        "_canonical_envelope_bytes",
        "_package_service",
        "_asset_service",
    )

    def __init__(
        self,
        envelope: SemanticCatalogEnvelope,
        package_service: SemanticPackageService,
        asset_service: SemanticAssetService,
    ) -> None:
        validated_envelope, canonical_envelope_bytes = _validated_envelope(envelope)
        if not callable(getattr(package_service, "fetch_package", None)):
            raise TypeError("package_service must implement fetch_package")
        if not callable(getattr(asset_service, "fetch_asset", None)):
            raise TypeError("asset_service must implement fetch_asset")
        self._envelope = validated_envelope
        self._canonical_envelope_bytes = canonical_envelope_bytes
        self._package_service = package_service
        self._asset_service = asset_service

    def __call__(
        self,
        environ: Mapping[str, object],
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        raw_method = environ.get("REQUEST_METHOD", "GET")
        method = raw_method.upper() if type(raw_method) is str else ""
        head = method == "HEAD"
        path = environ.get("PATH_INFO", "")
        if path not in (ENVELOPE_ROUTE, PACKAGE_ROUTE, ASSET_ROUTE):
            return _error_response(
                start_response,
                404,
                "route not found",
                head=head,
            )

        if method not in {"GET", "HEAD"}:
            return _error_response(
                start_response,
                405,
                "method not allowed",
                extra_headers=(("Allow", "GET, HEAD"),),
            )

        if path == ENVELOPE_ROUTE:
            try:
                query = _exact_query(environ, _ENVELOPE_QUERY_KEYS)
                requested_digest = query["catalogDigest"]
                if not _DIGEST_RE.fullmatch(requested_digest):
                    raise _MalformedRequest("catalogDigest is invalid")
            except _MalformedRequest:
                return _error_response(
                    start_response,
                    400,
                    "malformed request",
                    head=head,
                )
            if requested_digest != self._envelope.catalog_digest:
                return _error_response(
                    start_response,
                    404,
                    "exact artifact unavailable",
                    head=head,
                )
            return _success_response(
                start_response,
                self._canonical_envelope_bytes,
                SEMANTIC_CATALOG_MEDIA_TYPE,
                self._envelope.catalog_digest,
                (("X-KMQDB-Catalog-Digest", self._envelope.catalog_digest),),
                head=head,
            )

        if path == PACKAGE_ROUTE:
            try:
                query = _exact_query(environ, _PACKAGE_QUERY_KEYS)
                request = SemanticPackageRequest(
                    package_id=query["packageId"],
                    version=query["version"],
                    package_digest=query["packageDigest"],
                )
            except (_MalformedRequest, SemanticTransportError):
                return _error_response(
                    start_response,
                    400,
                    "malformed request",
                    head=head,
                )
            if request not in self._envelope.package_requests:
                return _error_response(
                    start_response,
                    404,
                    "exact artifact unavailable",
                    head=head,
                )
            try:
                artifact = _validated_package_artifact(
                    self._package_service,
                    request,
                )
            except SemanticTransportError:
                return _error_response(
                    start_response,
                    404,
                    "exact artifact unavailable",
                    head=head,
                )
            except Exception:
                return _error_response(
                    start_response,
                    500,
                    "semantic service failure",
                    head=head,
                )
            return _success_response(
                start_response,
                artifact.canonical_package_bytes,
                artifact.media_type,
                request.package_digest,
                (
                    ("X-KMQDB-Package-Id", request.package_id),
                    ("X-KMQDB-Package-Version", request.version),
                ),
                head=head,
            )

        try:
            query = _exact_query(environ, _ASSET_QUERY_KEYS)
            asset_ref = AssetRef(query["assetId"], query["assetDigest"])
        except (_MalformedRequest, SemanticPackageError):
            return _error_response(
                start_response,
                400,
                "malformed request",
                head=head,
            )
        if asset_ref not in self._envelope.asset_refs:
            return _error_response(
                start_response,
                404,
                "exact artifact unavailable",
                head=head,
            )
        try:
            asset = _validated_asset_artifact(self._asset_service, asset_ref)
        except SemanticTransportError:
            return _error_response(
                start_response,
                404,
                "exact artifact unavailable",
                head=head,
            )
        except Exception:
            return _error_response(
                start_response,
                500,
                "semantic service failure",
                head=head,
            )
        return _success_response(
            start_response,
            asset.asset_bytes,
            asset.media_type,
            asset.sha256_digest,
            (
                ("X-KMQDB-Asset-Id", asset_ref.asset_id),
                ("X-KMQDB-Asset-SHA256", asset.sha256_digest),
            ),
            head=head,
        )


def create_semantic_catalog_application(
    envelope: SemanticCatalogEnvelope,
    package_service: SemanticPackageService,
    asset_service: SemanticAssetService,
) -> SemanticCatalogHttpApplication:
    """Bind the exact semantic services to the version-1 WSGI boundary."""

    return SemanticCatalogHttpApplication(envelope, package_service, asset_service)


__all__ = [
    "ASSET_ROUTE",
    "ENVELOPE_ROUTE",
    "IMMUTABLE_CACHE_CONTROL",
    "PACKAGE_ROUTE",
    "SEMANTIC_CATALOG_MEDIA_TYPE",
    "SemanticCatalogHttpApplication",
    "create_semantic_catalog_application",
]

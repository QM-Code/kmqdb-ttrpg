from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import unittest
from urllib.parse import urlencode

from subdomains.ttrpg import semantic_http as semantic_http_module
from subdomains.ttrpg.semantic_assets import (
    SemanticAssetArtifact,
    TtrpgSemanticAssetStore,
)
from subdomains.ttrpg.semantic_catalog import SemanticCatalogSnapshot
from subdomains.ttrpg.semantic_http import (
    ASSET_ROUTE,
    ENVELOPE_ROUTE,
    IMMUTABLE_CACHE_CONTROL,
    PACKAGE_ROUTE,
    SEMANTIC_CATALOG_MEDIA_TYPE,
    SemanticCatalogHttpApplication,
)
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    build_semantic_entity,
    build_semantic_package,
)
from subdomains.ttrpg.semantic_transport import (
    SEMANTIC_PACKAGE_MEDIA_TYPE,
    SemanticCatalogEnvelope,
    SemanticPackageArtifact,
    SemanticPackageRequest,
    SnapshotSemanticAssetService,
    SnapshotSemanticPackageService,
)


def _digest(character: str) -> str:
    return character * 64


def _package():
    asset_bytes = b"synthetic goblin portrait"
    asset_ref = AssetRef(
        "ttrpg:goblin-portrait",
        hashlib.sha256(asset_bytes).hexdigest(),
    )
    entity = build_semantic_entity(
        entity_id="pf2er:goblin-warrior",
        entity_kind="ttrpg:creature",
        definition={"level": 1, "name": "Goblin Warrior"},
        evidence_authority_id="ttrpg:test-semantic-evidence",
        evidence_record_digest=_digest("2"),
        compiler_digest=_digest("3"),
        raw_definition_digest=_digest("4"),
        projection_id="ttrpg:test-source-free-projector",
        projection_version="1.0.0",
        projection_digest=_digest("5"),
        asset_refs=(asset_ref,),
    )
    package = build_semantic_package(
        package_id="ttrpg:monster-core",
        version="1.2.3",
        ruleset_id="paizo:pf2er",
        ruleset_digest=_digest("6"),
        book_id="paizo:monster-core",
        book_digest=_digest("7"),
        semantic_generation="ttrpg:publication-generation-1",
        semantic_generation_digest=_digest("8"),
        compiler_id="ttrpg:pf2er-semantic-compiler",
        compiler_version="1.0.0",
        compiler_digest=_digest("3"),
        entities=(entity,),
    )
    return package, asset_ref, asset_bytes


class _RecordingService:
    def __init__(self, delegate: object, method_name: str) -> None:
        self._delegate = delegate
        self._method_name = method_name
        self.calls: list[object] = []

    def fetch_package(self, request: object) -> object:
        self.calls.append(request)
        return getattr(self._delegate, self._method_name)(request)

    def fetch_asset(self, asset_ref: object) -> object:
        self.calls.append(asset_ref)
        return getattr(self._delegate, self._method_name)(asset_ref)


class _StaticPackageService:
    def __init__(self, artifact: object) -> None:
        self.artifact = artifact

    def fetch_package(self, request: object) -> object:
        return self.artifact


class SemanticHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package, self.asset_ref, self.asset_bytes = _package()
        catalog = SemanticCatalogSnapshot.from_selected_packages((self.package,))
        self.envelope = SemanticCatalogEnvelope.from_snapshot(catalog)
        package_delegate = SnapshotSemanticPackageService(catalog)
        asset_artifact = SemanticAssetArtifact.from_bytes(
            self.asset_ref,
            "image/webp",
            self.asset_bytes,
        )
        store = TtrpgSemanticAssetStore()
        store.publish((asset_artifact,))
        asset_delegate = SnapshotSemanticAssetService(
            store.open_snapshot((self.asset_ref,))
        )
        self.package_service = _RecordingService(
            package_delegate,
            "fetch_package",
        )
        self.asset_service = _RecordingService(asset_delegate, "fetch_asset")
        self.application = SemanticCatalogHttpApplication(
            self.envelope,
            self.package_service,
            self.asset_service,
        )

    @staticmethod
    def _request(
        application: object,
        path: str,
        query: str,
        *,
        method: str = "GET",
    ) -> tuple[str, dict[str, str], bytes]:
        response: dict[str, object] = {}

        def start_response(
            status: str,
            headers: list[tuple[str, str]],
        ) -> None:
            response["status"] = status
            response["headers"] = headers

        chunks = application(  # type: ignore[operator]
            {
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "REQUEST_METHOD": method,
            },
            start_response,
        )
        return (
            response["status"],  # type: ignore[return-value]
            dict(response["headers"]),  # type: ignore[arg-type]
            b"".join(chunks),
        )

    def _package_query(self, **changes: str) -> str:
        request = SemanticPackageRequest.from_package(self.package)
        values = {
            "packageId": request.package_id,
            "version": request.version,
            "packageDigest": request.package_digest,
            **changes,
        }
        return urlencode(values)

    def _asset_query(self, **changes: str) -> str:
        values = {
            "assetId": self.asset_ref.asset_id,
            "assetDigest": self.asset_ref.asset_digest,
            **changes,
        }
        return urlencode(values)

    def test_envelope_get_and_head_return_exact_canonical_closure(self) -> None:
        query = urlencode({"catalogDigest": self.envelope.catalog_digest})
        status, headers, body = self._request(
            self.application,
            ENVELOPE_ROUTE,
            query,
        )
        expected = json.dumps(
            self.envelope.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        self.assertEqual(status, "200 OK")
        self.assertEqual(body, expected)
        self.assertEqual(headers["Content-Type"], SEMANTIC_CATALOG_MEDIA_TYPE)
        self.assertEqual(headers["Content-Length"], str(len(expected)))
        self.assertEqual(headers["Cache-Control"], IMMUTABLE_CACHE_CONTROL)
        self.assertEqual(headers["ETag"], f'"{self.envelope.catalog_digest}"')
        self.assertEqual(
            headers["X-KMQDB-Catalog-Digest"],
            self.envelope.catalog_digest,
        )
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

        head_status, head_headers, head_body = self._request(
            self.application,
            ENVELOPE_ROUTE,
            query,
            method="HEAD",
        )
        self.assertEqual(head_status, status)
        self.assertEqual(head_headers, headers)
        self.assertEqual(head_body, b"")

    def test_envelope_digest_is_strict_and_exact(self) -> None:
        malformed = (
            "",
            urlencode(
                {
                    "catalogDigest": self.envelope.catalog_digest,
                    "extra": "forbidden",
                }
            ),
            "catalogDigest="
            + self.envelope.catalog_digest
            + "&catalogDigest="
            + _digest("9"),
            "catalogDigest=" + ("A" * 64),
            "catalogDigest=%ZZ",
        )
        for query in malformed:
            with self.subTest(query=query):
                status, headers, body = self._request(
                    self.application,
                    ENVELOPE_ROUTE,
                    query,
                )
                self.assertEqual(status, "400 Bad Request")
                self.assertEqual(body, b'{"error":"malformed request"}')
                self.assertEqual(headers["Cache-Control"], "no-store")

        status, headers, body = self._request(
            self.application,
            ENVELOPE_ROUTE,
            urlencode({"catalogDigest": _digest("9")}),
        )
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(body, b'{"error":"exact artifact unavailable"}')
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_application_revalidates_and_copies_its_envelope(self) -> None:
        malformed = SemanticCatalogEnvelope.from_dict(self.envelope.to_dict())
        object.__setattr__(
            malformed,
            "package_requests",
            list(malformed.package_requests),
        )
        with self.assertRaisesRegex(TypeError, "authenticated|canonical"):
            SemanticCatalogHttpApplication(
                malformed,
                self.package_service,
                self.asset_service,
            )

        original = SemanticCatalogEnvelope.from_dict(self.envelope.to_dict())
        application = SemanticCatalogHttpApplication(
            original,
            self.package_service,
            self.asset_service,
        )
        object.__setattr__(original, "catalog_digest", _digest("9"))
        status, _, _ = self._request(
            application,
            ENVELOPE_ROUTE,
            urlencode({"catalogDigest": self.envelope.catalog_digest}),
        )
        self.assertEqual(status, "200 OK")

    def test_package_get_returns_exact_canonical_artifact_and_headers(self) -> None:
        status, headers, body = self._request(
            self.application,
            PACKAGE_ROUTE,
            self._package_query(),
        )
        request = SemanticPackageRequest.from_package(self.package)

        self.assertEqual(status, "200 OK")
        self.assertEqual(body, self.package.canonical_json())
        self.assertEqual(headers["Content-Type"], SEMANTIC_PACKAGE_MEDIA_TYPE)
        self.assertEqual(headers["Content-Length"], str(len(body)))
        self.assertEqual(headers["Cache-Control"], IMMUTABLE_CACHE_CONTROL)
        self.assertEqual(headers["ETag"], f'"{request.package_digest}"')
        self.assertEqual(headers["X-KMQDB-Package-Id"], request.package_id)
        self.assertEqual(headers["X-KMQDB-Package-Version"], request.version)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.package_service.calls, [request])

    def test_package_head_returns_get_headers_without_a_body(self) -> None:
        get_status, get_headers, get_body = self._request(
            self.application,
            PACKAGE_ROUTE,
            self._package_query(),
        )
        head_status, head_headers, head_body = self._request(
            self.application,
            PACKAGE_ROUTE,
            self._package_query(),
            method="HEAD",
        )

        self.assertEqual(head_status, get_status)
        self.assertEqual(head_headers, get_headers)
        self.assertEqual(head_headers["Content-Length"], str(len(get_body)))
        self.assertEqual(head_body, b"")

    def test_asset_get_and_head_return_exact_opaque_bytes_and_headers(self) -> None:
        status, headers, body = self._request(
            self.application,
            ASSET_ROUTE,
            self._asset_query(),
        )

        self.assertEqual(status, "200 OK")
        self.assertEqual(body, self.asset_bytes)
        self.assertEqual(headers["Content-Type"], "image/webp")
        self.assertEqual(headers["Content-Length"], str(len(self.asset_bytes)))
        self.assertEqual(headers["Cache-Control"], IMMUTABLE_CACHE_CONTROL)
        self.assertEqual(headers["ETag"], f'"{self.asset_ref.asset_digest}"')
        self.assertEqual(headers["X-KMQDB-Asset-Id"], self.asset_ref.asset_id)
        self.assertEqual(
            headers["X-KMQDB-Asset-SHA256"],
            self.asset_ref.asset_digest,
        )
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

        head_status, head_headers, head_body = self._request(
            self.application,
            ASSET_ROUTE,
            self._asset_query(),
            method="HEAD",
        )
        self.assertEqual(head_status, status)
        self.assertEqual(head_headers, headers)
        self.assertEqual(head_body, b"")

    def test_queries_require_each_exact_single_strict_parameter(self) -> None:
        request = SemanticPackageRequest.from_package(self.package)
        malformed_queries = (
            "",
            urlencode(
                {
                    "packageId": request.package_id,
                    "version": request.version,
                }
            ),
            self._package_query(extra="forbidden"),
            self._package_query() + "&packageId=ttrpg%3Aduplicate",
            self._package_query(packageDigest="A" * 64),
            self._package_query() + "&",
            "packageId=ttrpg%ZZmonster&version=1.2.3&packageDigest=" + _digest("1"),
        )
        for query in malformed_queries:
            with self.subTest(query=query):
                status, headers, body = self._request(
                    self.application,
                    PACKAGE_ROUTE,
                    query,
                )
                self.assertEqual(status, "400 Bad Request")
                self.assertEqual(body, b'{"error":"malformed request"}')
                self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.package_service.calls, [])

    def test_unavailable_exact_artifacts_return_canonical_no_store_404(self) -> None:
        status, headers, body = self._request(
            self.application,
            PACKAGE_ROUTE,
            self._package_query(packageDigest=_digest("9")),
        )
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(body, b'{"error":"exact artifact unavailable"}')
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Content-Length"], str(len(body)))
        self.assertEqual(headers["Cache-Control"], "no-store")

        head_status, head_headers, head_body = self._request(
            self.application,
            ASSET_ROUTE,
            self._asset_query(assetDigest=_digest("9")),
            method="HEAD",
        )
        self.assertEqual(head_status, "404 Not Found")
        self.assertEqual(head_body, b"")
        self.assertEqual(
            head_headers["Content-Length"],
            str(len(b'{"error":"exact artifact unavailable"}')),
        )
        self.assertEqual(head_headers["Cache-Control"], "no-store")

    def test_paths_and_methods_fail_closed(self) -> None:
        status, headers, body = self._request(
            self.application,
            PACKAGE_ROUTE,
            self._package_query(),
            method="POST",
        )
        self.assertEqual(status, "405 Method Not Allowed")
        self.assertEqual(headers["Allow"], "GET, HEAD")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(body, b'{"error":"method not allowed"}')

        status, headers, body = self._request(
            self.application,
            "/.api/catalog/v1/packages",
            "",
            method="POST",
        )
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(body, b'{"error":"route not found"}')
        self.assertEqual(self.package_service.calls, [])

        head_status, head_headers, head_body = self._request(
            self.application,
            "/.api/catalog/v1/missing",
            "",
            method="HEAD",
        )
        self.assertEqual(head_status, "404 Not Found")
        self.assertEqual(head_body, b"")
        self.assertEqual(
            head_headers["Content-Length"],
            str(len(b'{"error":"route not found"}')),
        )

    def test_invalid_service_artifacts_and_exceptions_are_generic_500s(self) -> None:
        for service in (
            _StaticPackageService(object()),
            _StaticPackageService(
                SemanticPackageArtifact.from_package(
                    build_semantic_package(
                        package_id="ttrpg:other-package",
                        version="1.0.0",
                        ruleset_id="paizo:pf2er",
                        ruleset_digest=_digest("1"),
                        book_id="paizo:other-book",
                        book_digest=_digest("2"),
                        semantic_generation="ttrpg:publication-generation-1",
                        semantic_generation_digest=_digest("3"),
                        compiler_id="ttrpg:test-compiler",
                        compiler_version="1.0.0",
                        compiler_digest=_digest("3"),
                        entities=(self.package.entities[0],),
                    )
                )
            ),
        ):
            with self.subTest(service=service):
                application = SemanticCatalogHttpApplication(
                    self.envelope,
                    service,  # type: ignore[arg-type]
                    self.asset_service,
                )
                status, headers, body = self._request(
                    application,
                    PACKAGE_ROUTE,
                    self._package_query(),
                )
                self.assertEqual(status, "500 Internal Server Error")
                self.assertEqual(body, b'{"error":"semantic service failure"}')
                self.assertEqual(headers["Cache-Control"], "no-store")

    def test_provider_module_has_no_backend_source_compiler_or_game_dependency(self) -> None:
        path = Path(semantic_http_module.__file__).resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        forbidden = (
            "backend",
            "cache",
            "compiler",
            "gladiator",
            "rules_engine",
            "source_authority",
        )
        self.assertFalse(
            any(part in module for part in forbidden for module in imported),
            imported,
        )


if __name__ == "__main__":
    unittest.main()

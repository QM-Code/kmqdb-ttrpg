from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlencode

from subdomains.ttrpg import semantic_service as semantic_service_module
from subdomains.ttrpg.semantic_assets import (
    SemanticAssetArtifact,
    TtrpgSemanticAssetStore,
)
from subdomains.ttrpg.semantic_catalog import SemanticCatalogSnapshot
from subdomains.ttrpg.semantic_http import ASSET_ROUTE, ENVELOPE_ROUTE, PACKAGE_ROUTE
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    build_semantic_entity,
    build_semantic_package,
)
from subdomains.ttrpg.semantic_repository import write_semantic_repository
from subdomains.ttrpg.semantic_service import (
    SEMANTIC_REPOSITORY_ENVIRONMENT,
    SemanticServiceConfigurationError,
    _LazySemanticServiceApplication,
    application,
    create_semantic_service_application,
    load_configured_semantic_repository,
)
from subdomains.ttrpg.semantic_transport import SemanticPackageRequest


def _digest(character: str) -> str:
    return character * 64


def _repository(root: Path):
    asset_bytes = b"synthetic semantic service icon"
    asset_ref = AssetRef(
        "ttrpg:goblin-icon",
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
        version="1.0.0",
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
    catalog = SemanticCatalogSnapshot.from_selected_packages((package,))
    artifact = SemanticAssetArtifact.from_bytes(asset_ref, "image/webp", asset_bytes)
    store = TtrpgSemanticAssetStore()
    store.publish((artifact,))
    assets = store.open_snapshot((asset_ref,))
    destination = write_semantic_repository(root, catalog=catalog, assets=assets)
    return destination, catalog, package, artifact


def _request(application_value, path: str, query: str):
    response: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        response["status"] = status
        response["headers"] = headers

    body = b"".join(
        application_value(
            {
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "REQUEST_METHOD": "GET",
            },
            start_response,
        )
    )
    return response["status"], dict(response["headers"]), body


class SemanticServiceTests(unittest.TestCase):
    def test_missing_configuration_has_no_default_or_http_service(self) -> None:
        with mock.patch(
            "subdomains.ttrpg.semantic_service.create_semantic_catalog_application"
        ) as compose:
            with self.assertRaisesRegex(
                SemanticServiceConfigurationError,
                SEMANTIC_REPOSITORY_ENVIRONMENT,
            ):
                create_semantic_service_application({})
        compose.assert_not_called()
        self.assertTrue(callable(application))

    def test_malformed_missing_and_symbolic_link_roots_fail_before_composition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            missing = parent / _digest("9")
            malformed = parent / "not-a-catalog-digest"
            real_root = parent / "repositories"
            real_root.mkdir()
            real_root.chmod(0o755)
            destination, _, _, _ = _repository(real_root)
            link_parent = parent / "linked"
            link_parent.mkdir()
            linked = link_parent / destination.name
            linked.symlink_to(destination, target_is_directory=True)
            candidates = (
                "relative/repository",
                str(malformed),
                str(missing),
                str(linked),
            )
            with mock.patch(
                "subdomains.ttrpg.semantic_service.create_semantic_catalog_application"
            ) as compose:
                for candidate in candidates:
                    with self.subTest(candidate=candidate):
                        with self.assertRaises(SemanticServiceConfigurationError):
                            create_semantic_service_application(
                                {SEMANTIC_REPOSITORY_ENVIRONMENT: candidate}
                            )
            compose.assert_not_called()

    def test_tampered_repository_fails_closed_before_http_composition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination, _, _, _ = _repository(Path(temporary))
            envelope = destination / "catalog-envelope.json"
            envelope.write_bytes(envelope.read_bytes() + b"\n")
            envelope.chmod(0o644)
            environment = {SEMANTIC_REPOSITORY_ENVIRONMENT: str(destination)}

            with mock.patch(
                "subdomains.ttrpg.semantic_service.create_semantic_catalog_application"
            ) as compose:
                with self.assertRaisesRegex(
                    SemanticServiceConfigurationError,
                    "strict authentication",
                ):
                    create_semantic_service_application(environment)
            compose.assert_not_called()

    def test_exact_restart_reloads_the_same_immutable_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination, catalog, _, _ = _repository(Path(temporary))
            environment = {SEMANTIC_REPOSITORY_ENVIRONMENT: str(destination)}

            first = load_configured_semantic_repository(environment)
            second = load_configured_semantic_repository(environment)

            self.assertIsNot(first, second)
            self.assertEqual(first.envelope, second.envelope)
            self.assertEqual(first.catalog_snapshot.manifest, catalog.manifest)
            self.assertEqual(second.catalog_snapshot.manifest, catalog.manifest)

    def test_composed_application_serves_envelope_package_and_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination, catalog, package, artifact = _repository(Path(temporary))
            composed = create_semantic_service_application(
                {SEMANTIC_REPOSITORY_ENVIRONMENT: str(destination)}
            )
            envelope_status, envelope_headers, envelope_body = _request(
                composed,
                ENVELOPE_ROUTE,
                urlencode({"catalogDigest": catalog.catalog_digest}),
            )
            request = SemanticPackageRequest.from_package(package)
            package_status, _, package_body = _request(
                composed,
                PACKAGE_ROUTE,
                urlencode(request.to_dict()),
            )
            asset_status, asset_headers, asset_body = _request(
                composed,
                ASSET_ROUTE,
                urlencode(artifact.asset_ref.to_dict()),
            )

            self.assertEqual(envelope_status, "200 OK")
            self.assertEqual(json.loads(envelope_body), {
                "schema": 1,
                "catalogDigest": catalog.catalog_digest,
                "packages": [request.to_dict()],
                "assetRefs": [artifact.asset_ref.to_dict()],
            })
            self.assertEqual(
                envelope_headers["X-KMQDB-Catalog-Digest"],
                catalog.catalog_digest,
            )
            self.assertEqual(package_status, "200 OK")
            self.assertEqual(package_body, package.canonical_json())
            self.assertEqual(asset_status, "200 OK")
            self.assertEqual(asset_body, artifact.asset_bytes)
            self.assertEqual(asset_headers["Content-Type"], "image/webp")

    def test_lazy_application_loads_once_and_a_new_process_instance_reopens(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination, catalog, _, _ = _repository(Path(temporary))
            environment = {SEMANTIC_REPOSITORY_ENVIRONMENT: str(destination)}
            query = urlencode({"catalogDigest": catalog.catalog_digest})
            first_process = _LazySemanticServiceApplication()
            second_process = _LazySemanticServiceApplication()
            real_factory = create_semantic_service_application

            with mock.patch.dict(os.environ, environment, clear=True), mock.patch(
                "subdomains.ttrpg.semantic_service.create_semantic_service_application",
                wraps=real_factory,
            ) as factory:
                self.assertEqual(
                    _request(first_process, ENVELOPE_ROUTE, query)[0],
                    "200 OK",
                )
                self.assertEqual(
                    _request(first_process, ENVELOPE_ROUTE, query)[0],
                    "200 OK",
                )
                self.assertEqual(factory.call_count, 1)
                self.assertEqual(
                    _request(second_process, ENVELOPE_ROUTE, query)[0],
                    "200 OK",
                )
                self.assertEqual(factory.call_count, 2)

    def test_composition_leaf_has_no_auth_acquisition_or_game_import(self) -> None:
        source_path = Path(semantic_service_module.__file__).resolve()
        source = source_path.read_text(encoding="utf-8")
        imported = {
            alias.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }

        self.assertFalse(any("gladiator" in name for name in imported))
        for forbidden in (
            "backend",
            "cache",
            "compiler",
            "rules_engine",
            "source_authority",
            "ttrpg_auth",
        ):
            self.assertFalse(any(forbidden in name for name in imported))
        self.assertIn("authorization middleware", source)


if __name__ == "__main__":
    unittest.main()

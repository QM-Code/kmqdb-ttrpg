from __future__ import annotations

import base64
import csv
from email.parser import BytesParser
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
import venv
from zipfile import ZipFile


TTRPG_ROOT = Path(__file__).resolve().parents[1]
BUILD_BACKEND_PATH = (
    TTRPG_ROOT / "semantic_contract_distribution" / "build_backend.py"
)
BUILD_SCRIPT_PATH = TTRPG_ROOT / "scripts" / (
    "build_ttrpg_semantic_contract_wheel.py"
)

WHEEL_NAME = "kmqdb_ttrpg_semantic_contracts-1.0.0-py3-none-any.whl"
DIST_INFO = "kmqdb_ttrpg_semantic_contracts-1.0.0.dist-info"
MODULE_PATHS = {
    "subdomains/ttrpg/semantic_assets.py",
    "subdomains/ttrpg/semantic_catalog.py",
    "subdomains/ttrpg/semantic_packages.py",
    "subdomains/ttrpg/semantic_transport.py",
}

ASSET_BYTES = b"wire-contract-asset-v1\n"
PACKAGE_BYTES = (
    b'{"bookDigest":"92719fe0cf8cd51592af31ee8a5736d79f7273777fa3f7b70bfe993a4cd32180",'
    b'"bookId":"paizo:fixture","compilerDigest":"e996bb0ea465fae70d3e3c66b3b6e02d33d2f1eb76d5958720578b6cf359cc2e",'
    b'"compilerId":"kmqdb.compiler:fixture","compilerVersion":"1.0.0","entities":'
    b'[{"assetRefs":[{"assetDigest":"32fd71fdef3ae275a83c9bb8596c3ff644e30fae01c3647ee653ed2a95d277c4",'
    b'"assetId":"kmqdb.asset:wire-contract"}],"definition":{"displayName":"Wire Contract Fixture",'
    b'"kind":"creature","traits":["test"]},"definitionDigest":'
    b'"2e3506cb151704abae8e461a67af919bbaf91bc4f8b022f57a66a5917b6dd9d2",'
    b'"entityId":"kmqdb.entity:wire-contract","entityKind":"ttrpg:creature","receipt":'
    b'{"compilerDigest":"e996bb0ea465fae70d3e3c66b3b6e02d33d2f1eb76d5958720578b6cf359cc2e",'
    b'"evidenceAuthorityId":"kmqdb.evidence:wire-contract","evidenceRecordDigest":'
    b'"ee8250fb76e094b34b471f13a73dbbe51d1ae142e9df59d7c0d31ec20f0a0a8e",'
    b'"projectedDefinitionDigest":"2e3506cb151704abae8e461a67af919bbaf91bc4f8b022f57a66a5917b6dd9d2",'
    b'"projectionDigest":"1b250ea199bec73d392caad39d1167d6edc43c81f20edead86eea52c52b94fc1",'
    b'"projectionId":"kmqdb.projection:wire-contract","projectionVersion":"1.0.0",'
    b'"rawDefinitionDigest":"0d0e4766bdeeb514e784185d283858e9d958febdec485db4d842ae597eb0e4bc",'
    b'"schema":2,"semanticReceiptDigest":"aa05462dce70501e746b758d9e34d4791569c93432a6910db14d5f2c07bc5640"},'
    b'"requiredCapabilities":[{"capabilityId":"kmqdb.runtime:test","contractVersion":"1.0.0"}]}],'
    b'"packageDigest":"ab90b920029ada76079a2dd08b87f31a1ffea82dc931ee73300c63aa141c7d1a",'
    b'"packageId":"kmqdb.package:wire-contract","providerCarrierRelationships":[],'
    b'"rulesetDigest":"99c030754b69261444a37f5d6def839a9df98ec9df8a7666625ce8029c68f7cd",'
    b'"rulesetId":"paizo:pf2er","schema":2,"semanticGeneration":"kmqdb.semantic:wire-contract",'
    b'"semanticGenerationDigest":"e661f4c935e8a5a83349afb5e347695c2e972e967b50efcd618f93b0b7b4c24b",'
    b'"version":"1.0.0"}'
)
ENVELOPE_BYTES = (
    b'{"assetRefs":[{"assetDigest":"32fd71fdef3ae275a83c9bb8596c3ff644e30fae01c3647ee653ed2a95d277c4",'
    b'"assetId":"kmqdb.asset:wire-contract"}],"catalogDigest":'
    b'"6747f0a0acea7b5b0181e71330861642272668b39c0d6c0f2c31f4be988815e6",'
    b'"packages":[{"packageDigest":"ab90b920029ada76079a2dd08b87f31a1ffea82dc931ee73300c63aa141c7d1a",'
    b'"packageId":"kmqdb.package:wire-contract","version":"1.0.0"}],"schema":1}'
)
ASSET_MANIFEST_BYTES = (
    b'{"assetRef":{"assetDigest":"32fd71fdef3ae275a83c9bb8596c3ff644e30fae01c3647ee653ed2a95d277c4",'
    b'"assetId":"kmqdb.asset:wire-contract"},"mediaType":"image/png","schema":1,'
    b'"sha256":"32fd71fdef3ae275a83c9bb8596c3ff644e30fae01c3647ee653ed2a95d277c4",'
    b'"size":23}'
)


def load_build_backend() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_kmqdb_ttrpg_semantic_contract_build_backend",
        BUILD_BACKEND_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("semantic contract build backend is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def record_hash(payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b"=")
    return "sha256=" + digest.decode("ascii")


class TtrpgSemanticContractWheelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend = load_build_backend()

    def test_contract_closure_is_exact_and_source_free(self) -> None:
        sources = self.backend.contract_sources()
        self.assertEqual(set(sources), MODULE_PATHS)
        forbidden = (
            b"semantic_compiler",
            b"source_authority",
            b"source_content",
            b"item_catalog",
            b"backend",
            b"cache.db",
        )
        for path, payload in sources.items():
            for marker in forbidden:
                self.assertNotIn(marker, payload, f"{path} contains {marker!r}")

    def test_build_is_reproducible_and_never_clobbers(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path = self.backend.write_wheel(first)
            second_path = self.backend.write_wheel(second)
            self.assertEqual(first_path.name, WHEEL_NAME)
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())

            first_mtime = first_path.stat().st_mtime_ns
            self.assertEqual(self.backend.write_wheel(first), first_path)
            self.assertEqual(first_path.stat().st_mtime_ns, first_mtime)

        with tempfile.TemporaryDirectory() as conflicting:
            conflict_path = Path(conflicting) / WHEEL_NAME
            conflict_path.write_bytes(b"unrelated artifact")
            with self.assertRaises(FileExistsError):
                self.backend.write_wheel(conflicting)
            self.assertEqual(conflict_path.read_bytes(), b"unrelated artifact")

    def test_cli_reports_exact_artifact_digest(self) -> None:
        with tempfile.TemporaryDirectory() as output_directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT_PATH),
                    "--output-dir",
                    output_directory,
                ],
                cwd=output_directory,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(completed.stdout)
            wheel_path = Path(report["path"])
            self.assertEqual(report["distribution"], "kmqdb-ttrpg-semantic-contracts")
            self.assertEqual(report["version"], "1.0.0")
            self.assertEqual(report["filename"], WHEEL_NAME)
            self.assertEqual(report["sha256"], sha256(wheel_path.read_bytes()).hexdigest())
            self.assertEqual(report["size"], wheel_path.stat().st_size)

    def test_wheel_inventory_metadata_and_record_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as output_directory:
            wheel_path = self.backend.write_wheel(output_directory)
            with ZipFile(wheel_path) as archive:
                names = set(archive.namelist())
                expected = MODULE_PATHS | {
                    f"{DIST_INFO}/METADATA",
                    f"{DIST_INFO}/WHEEL",
                    f"{DIST_INFO}/top_level.txt",
                    f"{DIST_INFO}/RECORD",
                }
                self.assertEqual(names, expected)
                self.assertNotIn("subdomains/__init__.py", names)
                self.assertNotIn("subdomains/ttrpg/__init__.py", names)

                metadata = BytesParser().parsebytes(archive.read(f"{DIST_INFO}/METADATA"))
                self.assertEqual(metadata["Name"], "kmqdb-ttrpg-semantic-contracts")
                self.assertEqual(metadata["Version"], "1.0.0")
                self.assertEqual(metadata["Requires-Python"], ">=3.10")

                record_rows = list(
                    csv.reader(
                        archive.read(f"{DIST_INFO}/RECORD")
                        .decode("utf-8")
                        .splitlines()
                    )
                )
                self.assertEqual({row[0] for row in record_rows}, expected)
                for path, digest, size in record_rows:
                    if path == f"{DIST_INFO}/RECORD":
                        self.assertEqual((digest, size), ("", ""))
                        continue
                    payload = archive.read(path)
                    self.assertEqual(digest, record_hash(payload))
                    self.assertEqual(size, str(len(payload)))

    def test_fresh_venv_installs_and_round_trips_exact_wire_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            wheel_path = self.backend.write_wheel(temporary_root / "wheelhouse")
            environment_root = temporary_root / "environment"
            venv.EnvBuilder(with_pip=True).create(environment_root)
            environment_python = environment_root / "bin" / "python"
            if os.name == "nt":  # pragma: no cover - repository gates are POSIX
                environment_python = environment_root / "Scripts" / "python.exe"
            clean_environment = os.environ.copy()
            clean_environment.pop("PYTHONPATH", None)
            clean_environment["PYTHONDONTWRITEBYTECODE"] = "1"
            subprocess.run(
                [
                    str(environment_python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-index",
                    "--no-deps",
                    str(wheel_path),
                ],
                cwd=temporary_root,
                env=clean_environment,
                check=True,
                capture_output=True,
                text=True,
            )
            program = f"""
import importlib.metadata
import importlib.util
import json

from subdomains.ttrpg.semantic_assets import (
    SemanticAssetArtifact,
    TtrpgSemanticAssetStore,
)
from subdomains.ttrpg.semantic_catalog import SemanticCatalogSnapshot
from subdomains.ttrpg.semantic_packages import SemanticPackage
from subdomains.ttrpg.semantic_transport import (
    SemanticCatalogEnvelope,
    SemanticPackageArtifact,
    SnapshotSemanticAssetService,
    SnapshotSemanticPackageService,
)

package_bytes = {PACKAGE_BYTES!r}
asset_bytes = {ASSET_BYTES!r}
envelope_bytes = {ENVELOPE_BYTES!r}
asset_manifest_bytes = {ASSET_MANIFEST_BYTES!r}
canonical = lambda value: json.dumps(
    value,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(\",\", \":\"),
).encode(\"utf-8\")

assert importlib.metadata.version(\"kmqdb-ttrpg-semantic-contracts\") == \"1.0.0\"
package = SemanticPackage.from_dict(json.loads(package_bytes))
assert package.canonical_json() == package_bytes
snapshot = SemanticCatalogSnapshot.from_selected_packages((package,))
envelope = SemanticCatalogEnvelope.from_snapshot(snapshot)
assert canonical(envelope.to_dict()) == envelope_bytes
assert SemanticCatalogEnvelope.from_dict(json.loads(envelope_bytes)).to_dict() == envelope.to_dict()

asset_ref = envelope.asset_refs[0]
asset = SemanticAssetArtifact.from_bytes(asset_ref, \"image/png\", asset_bytes)
assert asset.canonical_manifest_json() == asset_manifest_bytes
asset_store = TtrpgSemanticAssetStore()
assert asset_store.publish((asset,)) == (asset_ref,)
asset_service = SnapshotSemanticAssetService(asset_store.open_snapshot((asset_ref,)))
assert asset_service.fetch_asset(asset_ref).asset_bytes == asset_bytes
package_service = SnapshotSemanticPackageService(snapshot)
package_artifact = package_service.fetch_package(envelope.package_requests[0])
assert isinstance(package_artifact, SemanticPackageArtifact)
assert package_artifact.canonical_package_bytes == package_bytes

for forbidden_module in (
    \"subdomains.ttrpg.backend\",
    \"subdomains.ttrpg.semantic_compiler\",
    \"subdomains.ttrpg.source_authority\",
    \"subdomains.ttrpg.source_content\",
    \"subdomains.ttrpg.item_catalog\",
):
    assert importlib.util.find_spec(forbidden_module) is None, forbidden_module
"""
            subprocess.run(
                [str(environment_python), "-I", "-c", program],
                cwd=temporary_root,
                env=clean_environment,
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()

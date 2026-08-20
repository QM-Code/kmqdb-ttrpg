from __future__ import annotations

from email.parser import BytesParser
from email.policy import compat32
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APPLICATION_BACKEND_PATH = (
    REPOSITORY_ROOT / "application_distribution" / "build_backend.py"
)
CONTRACT_BACKEND_PATH = (
    REPOSITORY_ROOT / "semantic_contract_distribution" / "build_backend.py"
)
EXPECTED_WHEEL_SHA256 = (
    "2a5ed3eee81bbdb3ab2587fb60c4fa7613eb6c5688292a70883244019496fc58"
)
EXPECTED_PAYLOAD_COUNT = 107
CONTRACT_PATHS = frozenset(
    {
        "subdomains/ttrpg/semantic_assets.py",
        "subdomains/ttrpg/semantic_catalog.py",
        "subdomains/ttrpg/semantic_packages.py",
        "subdomains/ttrpg/semantic_transport.py",
    }
)


def _load_backend(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"build backend is unavailable: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TtrpgApplicationWheelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temporary_directory.name)
        cls.application_backend = _load_backend(
            APPLICATION_BACKEND_PATH,
            "kmqdb_ttrpg_application_test_build_backend",
        )
        cls.contract_backend = _load_backend(
            CONTRACT_BACKEND_PATH,
            "kmqdb_ttrpg_contract_test_build_backend",
        )
        cls.first_wheel = cls.application_backend.write_wheel(
            cls.work / "first"
        )
        cls.second_wheel = cls.application_backend.write_wheel(
            cls.work / "second"
        )
        cls.contract_wheel = cls.contract_backend.write_wheel(
            cls.work / "contract"
        )
        cls.installed = cls.work / "installed"
        with ZipFile(cls.first_wheel) as archive:
            archive.extractall(cls.installed)
        with ZipFile(cls.contract_wheel) as archive:
            archive.extractall(cls.installed)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_two_builds_are_byte_identical_and_manifest_sealed(self) -> None:
        first = self.first_wheel.read_bytes()
        second = self.second_wheel.read_bytes()
        self.assertEqual(first, second)
        self.assertEqual(sha256(first).hexdigest(), EXPECTED_WHEEL_SHA256)
        manifest = json.loads(
            (
                REPOSITORY_ROOT
                / "application_distribution"
                / "source-manifest.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["wheelSha256"], EXPECTED_WHEEL_SHA256)
        self.assertEqual(len(manifest["files"]), EXPECTED_PAYLOAD_COUNT)

    def test_wheel_contains_exact_application_closure_without_contract_copies(
        self,
    ) -> None:
        expected = set(self.application_backend.source_paths())
        self.assertEqual(len(expected), EXPECTED_PAYLOAD_COUNT)
        with ZipFile(self.first_wheel) as archive:
            names = set(archive.namelist())
        payload = {
            name
            for name in names
            if not name.startswith(
                self.application_backend.DIST_INFO + "/"
            )
        }
        self.assertEqual(payload, expected)
        self.assertTrue(CONTRACT_PATHS.isdisjoint(payload))
        self.assertNotIn("subdomains/__init__.py", payload)
        self.assertNotIn("subdomains/ttrpg/__init__.py", payload)
        self.assertEqual(
            len(
                {
                    path
                    for path in payload
                    if path.startswith(
                        "subdomains/ttrpg/pf2er_compiler/"
                    )
                    and path.endswith(".py")
                }
            ),
            86,
        )

    def test_metadata_declares_only_exact_runtime_dependencies(self) -> None:
        with ZipFile(self.first_wheel) as archive:
            metadata_bytes = archive.read(
                self.application_backend.DIST_INFO + "/METADATA"
            )
        metadata = BytesParser(policy=compat32).parsebytes(metadata_bytes)
        self.assertEqual(metadata["Name"], "kmqdb-ttrpg")
        self.assertEqual(metadata["Version"], "0.1.0a1")
        self.assertEqual(
            metadata.get_all("Requires-Dist"),
            [
                "cryptography >=41.0.7",
                "kmqdb-ttrpg-semantic-contracts ==1.0.0",
            ],
        )
        for forbidden in ("kmqdbweb", "gladiator", "rules_engine"):
            self.assertNotIn(forbidden, metadata_bytes.decode("utf-8").lower())

    def test_manifest_sources_are_regular_mode_644_files(self) -> None:
        sources = self.application_backend.application_sources()
        self.assertEqual(len(sources), EXPECTED_PAYLOAD_COUNT)
        for relative, payload in sources.items():
            with self.subTest(path=relative):
                path = REPOSITORY_ROOT / relative
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(payload, path.read_bytes())

    def test_clean_installed_namespace_imports_without_core_or_game(self) -> None:
        script = r'''
import importlib
from pathlib import Path
import sys

installed = Path(sys.argv[1]).resolve()
repository = Path(sys.argv[2]).resolve()
sys.path[:] = [
    str(installed),
    *[
        entry
        for entry in sys.path
        if entry and not Path(entry).resolve().is_relative_to(repository)
    ],
]
modules = [
    importlib.import_module("kmqdb_ttrpg_wsgi"),
    importlib.import_module("subdomains.ttrpg.backend"),
    importlib.import_module("subdomains.ttrpg.item_catalog"),
    importlib.import_module("subdomains.ttrpg.pf2er_compiler"),
    *[
        importlib.import_module("subdomains.ttrpg." + name)
        for name in (
            "semantic_assets",
            "semantic_catalog",
            "semantic_packages",
            "semantic_transport",
        )
    ],
]
for module in modules:
    path = Path(module.__file__).resolve()
    assert path.is_relative_to(installed), (module.__name__, path)
assert callable(modules[0].application)
assert callable(modules[1].create_application)
assert not any(
    name == "kmqdbweb" or name.startswith("kmqdbweb.")
    for name in sys.modules
)
assert not any(
    name == "subdomains.ttrpg.rules_engine"
    or name.startswith("subdomains.ttrpg.rules_engine.")
    or name == "subdomains.ttrpg.gladiator"
    or name.startswith("subdomains.ttrpg.gladiator.")
    for name in sys.modules
)
print("clean installed import closure: OK")
'''
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                script,
                str(self.installed),
                str(REPOSITORY_ROOT),
            ],
            cwd=self.work,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )
        self.assertIn("clean installed import closure: OK", completed.stdout)

    def test_asset_stream_port_fails_closed_and_preserves_local_bodies(
        self,
    ) -> None:
        script = r'''
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import sys

installed = Path(sys.argv[1]).resolve()
repository = Path(sys.argv[2]).resolve()
sys.path[:] = [
    str(installed),
    *[
        entry
        for entry in sys.path
        if entry and not Path(entry).resolve().is_relative_to(repository)
    ],
]
from subdomains.ttrpg import backend

connection = sqlite3.connect(":memory:")
connection.row_factory = sqlite3.Row
connection.execute("""CREATE TABLE binary_assets (
    kind TEXT NOT NULL,
    asset_key TEXT NOT NULL,
    content_type TEXT NOT NULL,
    bucket TEXT NOT NULL,
    s3_key TEXT NOT NULL,
    body BLOB,
    size INTEGER NOT NULL,
    etag TEXT NOT NULL,
    last_modified TEXT NOT NULL
)""")
connection.executemany(
    "INSERT INTO binary_assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    [
        ("cover", "local", "image/webp", "assets", "local-key", b"local", 5, "", ""),
        ("cover", "remote", "image/webp", "assets", "remote-key", None, 6, "", ""),
    ],
)

@contextmanager
def cache_connection():
    yield connection

backend.cache_connection = cache_connection

def request(application, source_id):
    captured = {}
    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)
    body = b"".join(application(
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": f"/.api/sources/{source_id}/cover",
            "QUERY_STRING": "",
        },
        start_response,
    ))
    return captured, body

captured, body = request(backend.create_application(), "local")
assert (captured["status"], body) == ("200 OK", b"local")
captured, body = request(backend.create_application(), "remote")
assert captured["status"] == "503 Service Unavailable"
assert json.loads(body) == {"error": "external asset service is unavailable"}

calls = []
def streamer(key, environ, *, bucket, cache_control, extra_headers):
    calls.append((key, bucket, cache_control, extra_headers))
    return "200 OK", [("Content-Type", "image/webp")], [b"remote"]

captured, body = request(
    backend.create_application(asset_streamer=streamer),
    "remote",
)
assert (captured["status"], body) == ("200 OK", b"remote")
assert calls == [(
    "remote-key",
    "assets",
    "private, no-cache",
    (("Cross-Origin-Resource-Policy", "same-origin"),),
)]
assert not any(
    name == "kmqdbweb" or name.startswith("kmqdbweb.")
    for name in sys.modules
)
print("asset stream port: OK")
'''
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                script,
                str(self.installed),
                str(REPOSITORY_ROOT),
            ],
            cwd=self.work,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )
        self.assertIn("asset stream port: OK", completed.stdout)


if __name__ == "__main__":
    unittest.main()

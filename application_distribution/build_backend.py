"""Deterministic wheel builder for the standalone KMQDB TTRPG service.

The application and compiler share the PEP 420 ``subdomains.ttrpg``
namespace.  The four public semantic wire modules are deliberately absent:
they are supplied only by the exact semantic-contract distribution.
"""

from __future__ import annotations

import ast
import base64
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from zipfile import ZIP_STORED, ZipFile, ZipInfo


DISTRIBUTION_NAME = "kmqdb-ttrpg"
DISTRIBUTION_VERSION = "0.1.0a2"
WHEEL_NAME = "kmqdb_ttrpg-0.1.0a2-py3-none-any.whl"
DIST_INFO = "kmqdb_ttrpg-0.1.0a2.dist-info"
CRYPTOGRAPHY_DEPENDENCY = "cryptography >=41.0.7"
SEMANTIC_CONTRACT_DEPENDENCY = "kmqdb-ttrpg-semantic-contracts ==1.0.0"

ENTRYPOINT_PATHS = ("kmqdb_ttrpg_wsgi.py",)
APPLICATION_MODULE_PATHS = (
    "subdomains/ttrpg/backend.py",
    "subdomains/ttrpg/item_catalog.py",
    "subdomains/ttrpg/pf2er_hadrosaurid_semantic.py",
    "subdomains/ttrpg/pf2er_item_semantic.py",
    "subdomains/ttrpg/pf2er_semantic.py",
    "subdomains/ttrpg/pf2er_spell_semantic.py",
    "subdomains/ttrpg/pf2er_viper_semantic.py",
    "subdomains/ttrpg/semantic_compiler.py",
    "subdomains/ttrpg/semantic_evidence.py",
    "subdomains/ttrpg/semantic_http.py",
    "subdomains/ttrpg/semantic_package_builder.py",
    "subdomains/ttrpg/semantic_publication_review.py",
    "subdomains/ttrpg/semantic_repository.py",
    "subdomains/ttrpg/semantic_service.py",
    "subdomains/ttrpg/source_content.py",
    "subdomains/ttrpg/ttrpg_auth.py",
)
STATIC_PATHS = (
    "subdomains/ttrpg/@static/app.css",
    "subdomains/ttrpg/@static/app.js",
    "subdomains/ttrpg/@static/rules-menu.json",
    "subdomains/ttrpg/@static/rules-targets.json",
)
CONTRACT_MODULE_PATHS = frozenset(
    {
        "subdomains/ttrpg/semantic_assets.py",
        "subdomains/ttrpg/semantic_catalog.py",
        "subdomains/ttrpg/semantic_packages.py",
        "subdomains/ttrpg/semantic_transport.py",
    }
)

_DISTRIBUTION_ROOT = Path(__file__).resolve().parent
_TTRPG_ROOT = _DISTRIBUTION_ROOT.parent
_SOURCE_MANIFEST_PATH = _DISTRIBUTION_ROOT / "source-manifest.json"
_PACKAGE_ROOT = _TTRPG_ROOT / "subdomains" / "ttrpg"
_COMPILER_ROOT = _PACKAGE_ROOT / "pf2er_compiler"
_STATIC_ROOT = _PACKAGE_ROOT / "@static"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_EXTERNAL_IMPORTS = frozenset({"cryptography"})
_FORBIDDEN_IMPORT_PARTS = frozenset(
    {"gladiator", "kmqdbweb", "rules_engine"}
)


def _relative_files(root: Path, pattern: str) -> tuple[str, ...]:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"application source directory is unavailable: {root}")
    return tuple(
        sorted(
            path.relative_to(_TTRPG_ROOT).as_posix()
            for path in root.rglob(pattern)
            if path.is_file() and not path.is_symlink()
        )
    )


def source_paths() -> tuple[str, ...]:
    """Return the exact application, compiler, and static wheel closure."""

    compiler_paths = _relative_files(_COMPILER_ROOT, "*.py")
    if not compiler_paths:
        raise RuntimeError("the bundled PF2E Remaster compiler is unavailable")
    expected_python = tuple(sorted((*APPLICATION_MODULE_PATHS, *compiler_paths)))
    actual_python = _relative_files(_PACKAGE_ROOT, "*.py")
    if actual_python != expected_python:
        raise RuntimeError(
            "application Python closure contains an unlisted or missing module"
        )
    actual_static = _relative_files(_STATIC_ROOT, "*")
    if actual_static != tuple(sorted(STATIC_PATHS)):
        raise RuntimeError(
            "application static closure contains an unlisted or missing asset"
        )
    result = tuple(sorted((*ENTRYPOINT_PATHS, *expected_python, *STATIC_PATHS)))
    if CONTRACT_MODULE_PATHS.intersection(result):
        raise RuntimeError("application wheel duplicates semantic contract modules")
    return result


def _source_manifest() -> tuple[dict[str, str], str]:
    try:
        manifest = json.loads(_SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("application source manifest is unreadable") from exc
    if type(manifest) is not dict or set(manifest) != {
        "schema",
        "distribution",
        "version",
        "wheel",
        "wheelSha256",
        "files",
    }:
        raise RuntimeError("application source manifest has invalid fields")
    if manifest["schema"] != 1:
        raise RuntimeError("application source manifest schema must be 1")
    if manifest["distribution"] != DISTRIBUTION_NAME:
        raise RuntimeError("application source manifest distribution disagrees")
    if manifest["version"] != DISTRIBUTION_VERSION:
        raise RuntimeError("application source manifest version disagrees")
    if manifest["wheel"] != WHEEL_NAME:
        raise RuntimeError("application source manifest wheel disagrees")
    expected_wheel_digest = manifest["wheelSha256"]
    if (
        type(expected_wheel_digest) is not str
        or _SHA256_RE.fullmatch(expected_wheel_digest) is None
    ):
        raise RuntimeError("application source manifest wheel digest is invalid")
    entries = manifest["files"]
    if type(entries) is not list:
        raise RuntimeError("application source manifest files must be a list")
    allowed_paths = source_paths()
    expected: dict[str, str] = {}
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"path", "sha256"}:
            raise RuntimeError("application source manifest file is invalid")
        path = entry["path"]
        digest = entry["sha256"]
        if type(path) is not str or path not in allowed_paths:
            raise RuntimeError("application source manifest file is unknown")
        if path in expected:
            raise RuntimeError("application source manifest file is duplicated")
        if type(digest) is not str or _SHA256_RE.fullmatch(digest) is None:
            raise RuntimeError("application source manifest digest is invalid")
        expected[path] = digest
    if tuple(expected) != allowed_paths:
        raise RuntimeError("application source manifest file order disagrees")
    return expected, expected_wheel_digest


def _audit_python(relative: str, source: bytes) -> None:
    try:
        tree = ast.parse(source, filename=relative)
        compile(source, relative, "exec")
    except (SyntaxError, ValueError) as exc:
        raise RuntimeError(f"application module cannot be parsed: {relative}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = tuple(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported = ((node.module or ""),)
        else:
            continue
        for module in imported:
            parts = frozenset(part for part in module.split(".") if part)
            if parts.intersection(_FORBIDDEN_IMPORT_PARTS):
                raise RuntimeError(
                    f"application module imports a retired/external package: {relative}"
                )
            if isinstance(node, ast.ImportFrom) and node.level:
                continue
            root = module.partition(".")[0]
            if root in {"", "__future__", "subdomains"}:
                continue
            if root not in sys.stdlib_module_names and root not in _ALLOWED_EXTERNAL_IMPORTS:
                raise RuntimeError(
                    f"application module imports undeclared dependency {module}: {relative}"
                )


def application_sources() -> dict[str, bytes]:
    """Return exact manifest-authenticated wheel paths and source bytes."""

    expected_digests, _ = _source_manifest()
    result: dict[str, bytes] = {}
    for relative in source_paths():
        source_path = _TTRPG_ROOT / PurePosixPath(relative)
        if source_path.is_symlink() or not source_path.is_file():
            raise RuntimeError(f"application source must be a regular file: {relative}")
        if stat.S_IMODE(source_path.stat().st_mode) != 0o644:
            raise RuntimeError(f"application source must have mode 644: {relative}")
        source = source_path.read_bytes()
        if sha256(source).hexdigest() != expected_digests[relative]:
            raise RuntimeError(
                f"application source changed without a distribution release: {relative}"
            )
        if relative.endswith(".py"):
            _audit_python(relative, source)
        result[relative] = source
    return result


def _metadata() -> bytes:
    return (
        "Metadata-Version: 2.1\n"
        f"Name: {DISTRIBUTION_NAME}\n"
        f"Version: {DISTRIBUTION_VERSION}\n"
        "Summary: Standalone KMQDB TTRPG browser and semantic provider service\n"
        "Requires-Python: >=3.12\n"
        f"Requires-Dist: {CRYPTOGRAPHY_DEPENDENCY}\n"
        f"Requires-Dist: {SEMANTIC_CONTRACT_DEPENDENCY}\n"
        "\n"
    ).encode("utf-8")


def _wheel_metadata() -> bytes:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: kmqdb-ttrpg-application-builder 1\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
        "\n"
    ).encode("utf-8")


def _record_hash(payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b"=")
    return "sha256=" + digest.decode("ascii")


def _record(entries: dict[str, bytes]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for path in sorted(entries):
        payload = entries[path]
        writer.writerow((path, _record_hash(payload), str(len(payload))))
    writer.writerow((f"{DIST_INFO}/RECORD", "", ""))
    return output.getvalue().encode("utf-8")


def _wheel_entries() -> dict[str, bytes]:
    entries = application_sources()
    entries[f"{DIST_INFO}/METADATA"] = _metadata()
    entries[f"{DIST_INFO}/WHEEL"] = _wheel_metadata()
    entries[f"{DIST_INFO}/top_level.txt"] = b"kmqdb_ttrpg_wsgi\nsubdomains\n"
    entries[f"{DIST_INFO}/RECORD"] = _record(entries)
    return entries


def _zip_info(path: str) -> ZipInfo:
    info = ZipInfo(path, date_time=_ZIP_TIMESTAMP)
    info.compress_type = ZIP_STORED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def _unverified_wheel_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, mode="w") as archive:
        for path, payload in sorted(_wheel_entries().items()):
            archive.writestr(_zip_info(path), payload)
    return output.getvalue()


def wheel_bytes() -> bytes:
    """Return reproducible, source-manifest-bound wheel bytes."""

    payload = _unverified_wheel_bytes()
    _, expected_digest = _source_manifest()
    if sha256(payload).hexdigest() != expected_digest:
        raise RuntimeError("application wheel changed without a distribution release")
    return payload


def write_wheel(wheel_directory: str | Path) -> Path:
    output_directory = Path(wheel_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / WHEEL_NAME
    payload = wheel_bytes()
    if destination.exists():
        if destination.read_bytes() == payload:
            return destination
        raise FileExistsError(f"refusing to replace existing wheel: {destination}")
    destination.write_bytes(payload)
    destination.chmod(0o644)
    return destination


def get_requires_for_build_wheel(
    config_settings: dict[str, object] | None = None,
) -> list[str]:
    del config_settings
    return []


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, object] | None = None,
    metadata_directory: str | None = None,
) -> str:
    del config_settings, metadata_directory
    return write_wheel(wheel_directory).name


__all__ = [
    "APPLICATION_MODULE_PATHS",
    "CRYPTOGRAPHY_DEPENDENCY",
    "DISTRIBUTION_NAME",
    "DISTRIBUTION_VERSION",
    "ENTRYPOINT_PATHS",
    "SEMANTIC_CONTRACT_DEPENDENCY",
    "STATIC_PATHS",
    "WHEEL_NAME",
    "application_sources",
    "build_wheel",
    "get_requires_for_build_wheel",
    "source_paths",
    "wheel_bytes",
    "write_wheel",
]

"""Deterministic, dependency-free wheel builder for public TTRPG contracts.

The distribution deliberately installs four modules into the existing PEP 420
``subdomains.ttrpg`` namespace.  It does not install either namespace
``__init__.py`` and therefore coexists with independently installed TTRPG and
Gladiator distributions.
"""

from __future__ import annotations

import ast
import base64
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import re
import sys
from zipfile import ZIP_STORED, ZipFile, ZipInfo


DISTRIBUTION_NAME = "kmqdb-ttrpg-semantic-contracts"
DISTRIBUTION_VERSION = "1.0.0"
WHEEL_NAME = "kmqdb_ttrpg_semantic_contracts-1.0.0-py3-none-any.whl"
DIST_INFO = "kmqdb_ttrpg_semantic_contracts-1.0.0.dist-info"
IMPORT_NAMESPACE = "subdomains.ttrpg"
CONTRACT_MODULES = (
    "semantic_packages",
    "semantic_catalog",
    "semantic_assets",
    "semantic_transport",
)

_DISTRIBUTION_ROOT = Path(__file__).resolve().parent
_TTRPG_ROOT = _DISTRIBUTION_ROOT.parent
_SOURCE_MANIFEST_PATH = _DISTRIBUTION_ROOT / "source-manifest.json"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _source_path(module_name: str) -> Path:
    return _TTRPG_ROOT / f"{module_name}.py"


def _audit_imports(module_name: str, source: bytes) -> None:
    """Reject any dependency outside stdlib and the four contract modules."""

    try:
        tree = ast.parse(source, filename=str(_source_path(module_name)))
    except (SyntaxError, ValueError) as exc:
        raise RuntimeError(f"contract module {module_name} cannot be parsed") from exc
    allowed_stdlib = sys.stdlib_module_names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.partition(".")[0]
                if root not in allowed_stdlib:
                    raise RuntimeError(
                        f"contract module {module_name} imports non-stdlib {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                root = (node.module or "").partition(".")[0]
                if root not in allowed_stdlib:
                    raise RuntimeError(
                        f"contract module {module_name} imports non-stdlib {node.module}"
                    )
                continue
            if node.level != 1 or node.module not in CONTRACT_MODULES:
                raise RuntimeError(
                    f"contract module {module_name} imports outside the contract closure: "
                    f"level={node.level} module={node.module!r}"
                )


def _source_manifest() -> tuple[dict[str, str], str]:
    try:
        manifest = json.loads(_SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("semantic contract source manifest is unreadable") from exc
    if type(manifest) is not dict or set(manifest) != {
        "schema",
        "distribution",
        "version",
        "wheel",
        "wheelSha256",
        "modules",
    }:
        raise RuntimeError("semantic contract source manifest has invalid fields")
    if manifest["schema"] != 1:
        raise RuntimeError("semantic contract source manifest schema must be 1")
    if manifest["distribution"] != DISTRIBUTION_NAME:
        raise RuntimeError("semantic contract source manifest distribution disagrees")
    if manifest["version"] != DISTRIBUTION_VERSION:
        raise RuntimeError("semantic contract source manifest version disagrees")
    if manifest["wheel"] != WHEEL_NAME:
        raise RuntimeError("semantic contract source manifest wheel disagrees")
    expected_wheel_digest = manifest["wheelSha256"]
    if (
        type(expected_wheel_digest) is not str
        or not _SHA256_RE.fullmatch(expected_wheel_digest)
    ):
        raise RuntimeError("semantic contract source manifest wheel digest is invalid")
    modules = manifest["modules"]
    if type(modules) is not list:
        raise RuntimeError("semantic contract source manifest modules must be a list")
    expected: dict[str, str] = {}
    for entry in modules:
        if type(entry) is not dict or set(entry) != {"module", "sha256"}:
            raise RuntimeError("semantic contract source manifest module is invalid")
        module_name = entry["module"]
        digest = entry["sha256"]
        if type(module_name) is not str or module_name not in CONTRACT_MODULES:
            raise RuntimeError("semantic contract source manifest module is unknown")
        if module_name in expected:
            raise RuntimeError("semantic contract source manifest module is duplicated")
        if type(digest) is not str or not _SHA256_RE.fullmatch(digest):
            raise RuntimeError("semantic contract source manifest digest is invalid")
        expected[module_name] = digest
    if tuple(expected) != CONTRACT_MODULES:
        raise RuntimeError("semantic contract source manifest module order disagrees")
    return expected, expected_wheel_digest


def contract_sources() -> dict[str, bytes]:
    """Return the audited wheel paths and exact provider-owned source bytes."""

    expected_digests, _ = _source_manifest()
    result: dict[str, bytes] = {}
    for module_name in CONTRACT_MODULES:
        source_path = _source_path(module_name)
        source = source_path.read_bytes()
        if sha256(source).hexdigest() != expected_digests[module_name]:
            raise RuntimeError(
                f"contract module {module_name} changed without a distribution release"
            )
        _audit_imports(module_name, source)
        compile(source, str(source_path), "exec")
        result[f"subdomains/ttrpg/{module_name}.py"] = source
    return result


def _metadata() -> bytes:
    return (
        "Metadata-Version: 2.1\n"
        f"Name: {DISTRIBUTION_NAME}\n"
        f"Version: {DISTRIBUTION_VERSION}\n"
        "Summary: Provider-owned source-free TTRPG semantic wire contracts\n"
        "Requires-Python: >=3.10\n"
        "\n"
    ).encode("utf-8")


def _wheel_metadata() -> bytes:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: kmqdb-ttrpg-semantic-contract-builder 1\n"
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
    entries = contract_sources()
    entries[f"{DIST_INFO}/METADATA"] = _metadata()
    entries[f"{DIST_INFO}/WHEEL"] = _wheel_metadata()
    entries[f"{DIST_INFO}/top_level.txt"] = b"subdomains\n"
    entries[f"{DIST_INFO}/RECORD"] = _record(entries)
    return entries


def _zip_info(path: str) -> ZipInfo:
    info = ZipInfo(path, date_time=_ZIP_TIMESTAMP)
    info.compress_type = ZIP_STORED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def wheel_bytes() -> bytes:
    """Return reproducible wheel bytes without writing build state."""

    output = BytesIO()
    with ZipFile(output, mode="w") as archive:
        for path, payload in sorted(_wheel_entries().items()):
            archive.writestr(_zip_info(path), payload)
    payload = output.getvalue()
    _, expected_digest = _source_manifest()
    if sha256(payload).hexdigest() != expected_digest:
        raise RuntimeError(
            "semantic contract wheel changed without a distribution release"
        )
    return payload


def write_wheel(wheel_directory: str | Path) -> Path:
    """Publish into a caller-owned directory without replacing another file."""

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
    "CONTRACT_MODULES",
    "DISTRIBUTION_NAME",
    "DISTRIBUTION_VERSION",
    "IMPORT_NAMESPACE",
    "WHEEL_NAME",
    "build_wheel",
    "contract_sources",
    "get_requires_for_build_wheel",
    "wheel_bytes",
    "write_wheel",
]

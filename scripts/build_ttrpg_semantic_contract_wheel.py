#!/usr/bin/env python3
"""Build the provider-owned semantic contract wheel without dependencies."""

from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from types import ModuleType


_TTRPG_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_PATH = (
    _TTRPG_ROOT / "semantic_contract_distribution" / "build_backend.py"
)


def _backend() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kmqdb_ttrpg_semantic_contract_build_backend",
        _BACKEND_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("semantic contract build backend is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic TTRPG semantic contract wheel."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="caller-owned directory that will receive the exact wheel",
    )
    args = parser.parse_args()

    backend = _backend()
    wheel_path = backend.write_wheel(args.output_dir)
    payload = wheel_path.read_bytes()
    print(
        json.dumps(
            {
                "distribution": backend.DISTRIBUTION_NAME,
                "version": backend.DISTRIBUTION_VERSION,
                "filename": wheel_path.name,
                "path": str(wheel_path),
                "sha256": sha256(payload).hexdigest(),
                "size": len(payload),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

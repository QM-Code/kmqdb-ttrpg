#!/usr/bin/env python3
"""Run the exact retained standalone TTRPG product test inventory."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import sys
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TEST_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

APPLICATION_MODULES = (
    ("test_backend.py", 21),
    ("test_backend_semantic_catalog_mount.py", 2),
    ("test_ttrpg_auth.py", 10),
    ("test_sync_library_cache.py", 31),
    ("test_item_catalog.py", 10),
    ("test_ttrpg_game_ui_hardcut.py", 5),
    ("test_ttrpg_service_separation.py", 3),
    ("test_semantic_assets.py", 4),
    ("test_semantic_catalog.py", 7),
    ("test_semantic_packages.py", 9),
    ("test_semantic_transport.py", 5),
    ("test_semantic_repository.py", 10),
    ("test_semantic_http.py", 11),
    ("test_semantic_service.py", 7),
    ("test_semantic_compiler_selection.py", 5),
    ("test_semantic_evidence.py", 2),
    ("test_semantic_package_builder.py", 5),
    ("test_semantic_publication_review.py", 12),
    ("test_pf2er_semantic.py", 8),
    ("test_pf2er_item_semantic.py", 7),
    ("test_pf2er_spell_semantic.py", 3),
    ("test_pf2er_viper_semantic.py", 7),
    ("test_pf2er_hadrosaurid_semantic.py", 7),
)
CONTRACT_MODULES = (("test_ttrpg_semantic_contract_wheel.py", 5),)
INSTALLED_MODULES = tuple(
    item
    for item in APPLICATION_MODULES
    if item[0]
    not in {
        "test_sync_library_cache.py",
        "test_item_catalog.py",
        "test_ttrpg_service_separation.py",
    }
)

GATES = {
    "application": APPLICATION_MODULES,
    "installed": INSTALLED_MODULES,
    "semantic-contract": CONTRACT_MODULES,
    "all": APPLICATION_MODULES + CONTRACT_MODULES,
}

CACHE_ENVIRONMENT = "KMQDB_TTRPG_TEST_CACHE_DB"
PORTABLE_EXPECTATIONS = {
    "application": (174, 17),
    "installed": (130, 11),
    "semantic-contract": (5, 0),
    "all": (179, 17),
}


def _static_test_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


def _load_test_module(path: Path, index: int):
    module_name = f"_kmqdb_ttrpg_product_gate_{index}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def build_suite(gate: str) -> unittest.TestSuite:
    modules = GATES[gate]
    suite = unittest.TestSuite()
    for index, (filename, expected_count) in enumerate(modules):
        path = TEST_ROOT / filename
        if not path.is_file():
            raise RuntimeError(f"missing product test module: {path}")
        actual_count = _static_test_count(path)
        if actual_count != expected_count:
            raise RuntimeError(
                f"{filename}: expected {expected_count} test methods, found {actual_count}"
            )
        suite.addTests(
            unittest.defaultTestLoader.loadTestsFromModule(
                _load_test_module(path, index)
            )
        )
    loaded_count = suite.countTestCases()
    expected_total = sum(count for _, count in modules)
    if loaded_count != expected_total:
        raise RuntimeError(
            f"{gate}: expected {expected_total} loaded tests, found {loaded_count}"
        )
    return suite


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("gate", choices=tuple(GATES), nargs="?", default="all")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "--require-live-cache",
        action="store_true",
        help=(
            "require the exact cache named by KMQDB_TTRPG_TEST_CACHE_DB, "
            "or the target-local cache/cache.db, and reject every skip"
        ),
    )
    args = parser.parse_args()

    if args.require_live_cache:
        if args.gate == "semantic-contract":
            parser.error("the semantic-contract gate has no live-cache cases")
        cache_path = Path(
            os.environ.get(
                CACHE_ENVIRONMENT,
                str(REPO_ROOT / "cache" / "cache.db"),
            )
        ).expanduser()
        if not cache_path.is_file():
            parser.error(
                f"live cache is unavailable; set {CACHE_ENVIRONMENT}: {cache_path}"
            )
        os.environ[CACHE_ENVIRONMENT] = str(cache_path.resolve())
    elif args.gate != "semantic-contract":
        portable_cache = REPO_ROOT / "cache" / ".portable-gate-no-cache.db"
        if portable_cache.exists():
            raise RuntimeError(
                f"portable gate sentinel must not exist: {portable_cache}"
            )
        os.environ[CACHE_ENVIRONMENT] = str(portable_cache)

    result = unittest.TextTestRunner(verbosity=1 if args.quiet else 2).run(
        build_suite(args.gate)
    )
    if args.require_live_cache:
        expected_run = sum(count for _, count in GATES[args.gate])
        expected_skips = 0
    else:
        expected_run, expected_skips = PORTABLE_EXPECTATIONS[args.gate]
    skip_reasons = tuple(reason for _, reason in result.skipped)
    inventory_matches = (
        result.testsRun == expected_run
        and len(result.skipped) == expected_skips
        and (
            not skip_reasons
            or all(CACHE_ENVIRONMENT in reason for reason in skip_reasons)
        )
    )
    if not inventory_matches:
        print(
            f"gate inventory mismatch: expected run={expected_run}, "
            f"skips={expected_skips}; observed run={result.testsRun}, "
            f"skips={len(result.skipped)}",
            file=sys.stderr,
        )
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

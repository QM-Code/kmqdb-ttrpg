from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from subdomains.ttrpg.semantic_assets import TtrpgSemanticAssetStore
from subdomains.ttrpg.semantic_packages import (
    build_semantic_entity,
    build_semantic_package,
)
from subdomains.ttrpg.semantic_repository import load_semantic_repository


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "build_semantic_repository.py"
)
SPEC = importlib.util.spec_from_file_location(
    "kmqdb_ttrpg_semantic_repository_builder_test",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def digest(character: str) -> str:
    return character * 64


def package():
    entity = build_semantic_entity(
        entity_id="pf2er:test-creature",
        entity_kind="ttrpg:creature",
        definition={"level": 1, "name": "Test Creature"},
        evidence_authority_id="ttrpg:test-evidence",
        evidence_record_digest=digest("2"),
        compiler_digest=digest("3"),
        raw_definition_digest=digest("4"),
        projection_id="ttrpg:test-projector",
        projection_version="1.0.0",
        projection_digest=digest("5"),
        asset_refs=(),
    )
    return build_semantic_package(
        package_id="ttrpg:test-package",
        version="1.0.0",
        ruleset_id="paizo:pf2er",
        ruleset_digest=digest("6"),
        book_id="paizo:test-book",
        book_digest=digest("7"),
        semantic_generation="ttrpg:test-generation",
        semantic_generation_digest=digest("8"),
        compiler_id="ttrpg:test-compiler",
        compiler_version="1.0.0",
        compiler_digest=digest("3"),
        entities=(entity,),
    )


def write_bundle(root: Path) -> tuple[Path, object]:
    selected = package()
    bundle = root / "bundle"
    packages = bundle / "semantic-packages"
    blobs = bundle / "semantic-assets" / "blobs"
    packages.mkdir(parents=True)
    blobs.mkdir(parents=True)
    package_path = packages / f"{selected.package_digest}.json"
    package_path.write_bytes(selected.canonical_json())
    package_path.chmod(0o644)
    store = TtrpgSemanticAssetStore()
    snapshot = store.open_snapshot(())
    index = bundle / "semantic-assets" / "index.json"
    index.write_text(
        json.dumps(
            snapshot.inventory_projection(),
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    index.chmod(0o644)
    return bundle, selected


class BuildSemanticRepositoryTests(unittest.TestCase):
    def test_builds_and_reopens_exact_digest_named_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, selected = write_bundle(root)
            repository = builder.build_repository(bundle, root / "repositories")
            self.assertEqual(
                [item.package_digest for item in repository.catalog_snapshot.packages],
                [selected.package_digest],
            )
            self.assertEqual(repository.asset_snapshot.asset_refs, ())
            self.assertEqual(repository.path.name, repository.catalog_snapshot.catalog_digest)
            self.assertEqual(load_semantic_repository(repository.path).path, repository.path)
            self.assertEqual(
                {item.name for item in repository.path.iterdir()},
                {"assets", "catalog-envelope.json", "catalog-index.json", "packages"},
            )

    def test_rejects_package_filename_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, selected = write_bundle(root)
            package_path = (
                bundle
                / "semantic-packages"
                / f"{selected.package_digest}.json"
            )
            package_path.rename(package_path.with_name(digest("9") + ".json"))
            with self.assertRaisesRegex(
                builder.SemanticRepositoryBuildError,
                "filename",
            ):
                builder.build_repository(bundle, root / "repositories")


if __name__ == "__main__":
    unittest.main()

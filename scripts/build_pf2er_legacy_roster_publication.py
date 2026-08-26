#!/usr/bin/env python3
"""Build the canonical PF2ER legacy-roster semantic migration bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from subdomains.ttrpg import pf2er_semantic
from subdomains.ttrpg.pf2er_compiler.source_authority_store import (
    SourceAuthorityStore,
)
from scripts.pf2er_legacy_roster_semantic import (
    PF2ER_LEGACY_ROSTER_BOOK_DIGEST,
    PF2ER_LEGACY_ROSTER_RULESET_DIGEST,
    PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER,
    PF2ER_LEGACY_ROSTER_SOURCE_ID,
    PF2ER_LEGACY_ROSTER_TARGETS,
    build_legacy_roster_semantic_package,
)
from subdomains.ttrpg.semantic_assets import (
    SemanticAssetArtifact,
    TtrpgSemanticAssetStore,
)
from subdomains.ttrpg.semantic_catalog import SemanticCatalogSnapshot
from subdomains.ttrpg.semantic_evidence import SemanticEvidenceStore
from subdomains.ttrpg.semantic_package_builder import SourceCreatureTarget
from subdomains.ttrpg.semantic_packages import AssetRef, SemanticPackage


XULGATH_ICON_DIGEST = (
    "aa81ad330e38bf2f04521ce524ab07cc06add632bd9447edee529cb8a0a400f9"
)
EXPECTED_BASE_PACKAGE_IDS = frozenset(
    {
        "ttrpg:pf2er-monster-core-one-hadrosaurid-trample",
        "ttrpg:pf2er-monster-core-one-viper-slink",
        "ttrpg:pf2er-player-core-one",
        "ttrpg:pf2er-player-core-one-spells",
    }
)
REVIEWED_BINDINGS = {
    "core-mc1:98.2": (
        "pf2er:hadrosaurid",
        "ttrpg:pf2er-monster-core-one-hadrosaurid-trample",
    ),
    "core-mc1:316.2": (
        "pf2er:viper",
        "ttrpg:pf2er-monster-core-one-viper-slink",
    ),
    "core-mc1:352.3": (
        pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID,
        pf2er_semantic.PF2ER_MONSTER_CORE_ONE_PACKAGE_ID,
    ),
}


class LegacyRosterPublicationError(RuntimeError):
    """The roster publication inputs or deterministic outputs are invalid."""


def canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise LegacyRosterPublicationError(
            "publication artifact is not canonicalizable"
        ) from exc


def _load_base_packages(directory: Path) -> tuple[SemanticPackage, ...]:
    if directory.is_symlink() or not directory.is_dir():
        raise LegacyRosterPublicationError(
            "base package directory must be a regular directory"
        )
    packages = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.suffix != ".json" or path.is_symlink() or not path.is_file():
            continue
        body = path.read_bytes()
        try:
            packet = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise LegacyRosterPublicationError(
                f"base semantic package is invalid JSON: {path.name}"
            ) from exc
        if canonical_json(packet) != body:
            raise LegacyRosterPublicationError(
                f"base semantic package is not canonical JSON: {path.name}"
            )
        package = SemanticPackage.from_dict(packet)
        if path.stem != package.package_digest:
            raise LegacyRosterPublicationError(
                f"base semantic package filename is not its digest: {path.name}"
            )
        packages.append(package)
    actual = frozenset(package.package_id for package in packages)
    if actual != EXPECTED_BASE_PACKAGE_IDS:
        raise LegacyRosterPublicationError(
            "base semantic package selection changed; "
            f"expected={sorted(EXPECTED_BASE_PACKAGE_IDS)}, actual={sorted(actual)}"
        )
    return tuple(packages)


def _build_xulgath_package(authority, compiler_set, evidence_store):
    target = SourceCreatureTarget(
        pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID,
        "core-mc1",
        "352.3",
        required_capabilities=(
            pf2er_semantic.PF2ER_STENCH_LIFECYCLE_CAPABILITY,
        ),
        asset_refs=(
            AssetRef(
                pf2er_semantic.PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID,
                XULGATH_ICON_DIGEST,
            ),
        ),
    )
    return pf2er_semantic.build_pf2er_creature_semantic_package(
        authority=authority,
        compiler_set=compiler_set,
        book_id=pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,
        ruleset_digest=PF2ER_LEGACY_ROSTER_RULESET_DIGEST,
        book_digest=PF2ER_LEGACY_ROSTER_BOOK_DIGEST,
        semantic_generation=(
            "ttrpg:pf2er-monster-core-one-xulgath-publication-1"
        ),
        creatures=(target,),
        evidence_store=evidence_store,
        relationships=(pf2er_semantic.PF2ER_XULGATH_STENCH_RELATIONSHIP,),
    )


def _legacy_rows(path: Path) -> tuple[dict[str, str], ...]:
    if path.is_symlink() or not path.is_file():
        raise LegacyRosterPublicationError(
            "legacy world database must be a regular file"
        )
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            """
            SELECT
                gladiator_id,
                json_extract(definition_json, '$.sourceAddress') AS source_address,
                json_extract(definition_json, '$.sourceDigest') AS source_digest,
                json_extract(definition_json, '$.statBlock.name') AS creature_name
            FROM gladiators
            ORDER BY gladiator_id
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise LegacyRosterPublicationError(
            "could not read legacy roster database"
        ) from exc
    finally:
        if "connection" in locals():
            connection.close()
    if len(rows) != 163:
        raise LegacyRosterPublicationError(
            f"legacy roster count changed: expected=163, actual={len(rows)}"
        )
    result = tuple(
        {
            "gladiatorId": row["gladiator_id"],
            "legacySourceAddress": row["source_address"],
            "legacySourceDigest": row["source_digest"],
            "creatureName": row["creature_name"],
        }
        for row in rows
    )
    if any(
        type(value) is not str or not value
        for row in result
        for value in row.values()
    ):
        raise LegacyRosterPublicationError(
            "legacy roster contains an incomplete source identity"
        )
    if any(
        len(row["legacySourceDigest"]) != 64
        or any(character not in "0123456789abcdef" for character in row["legacySourceDigest"])
        for row in result
    ):
        raise LegacyRosterPublicationError(
            "legacy roster contains an invalid source digest"
        )
    return result


def _entity_pin(package: SemanticPackage, entity_id: str) -> dict[str, object]:
    entity = package.entity(entity_id)
    return {
        "package": {
            "packageId": package.package_id,
            "version": package.version,
            "packageDigest": package.package_digest,
        },
        "entityId": entity.entity_id,
        "definitionDigest": entity.definition_digest,
        "semanticReceiptDigest": entity.receipt.semantic_receipt_digest,
    }


def _binding_artifacts(
    rows: tuple[dict[str, str], ...],
    packages: tuple[SemanticPackage, ...],
) -> tuple[dict[str, object], dict[str, object]]:
    packages_by_id = {package.package_id: package for package in packages}
    legacy_package = next(
        package
        for package in packages
        if package.package_id
        == "ttrpg:pf2er-monster-core-one-legacy-roster"
    )
    legacy_by_address = {
        target.legacy_source_address: target
        for target in PF2ER_LEGACY_ROSTER_TARGETS
    }
    allowed_addresses = set(legacy_by_address) | set(REVIEWED_BINDINGS)
    actual_addresses = {row["legacySourceAddress"] for row in rows}
    if actual_addresses != allowed_addresses:
        raise LegacyRosterPublicationError(
            "legacy roster source-address census changed; "
            f"missing={sorted(allowed_addresses - actual_addresses)}, "
            f"extra={sorted(actual_addresses - allowed_addresses)}"
        )

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        key = (row["legacySourceAddress"], row["legacySourceDigest"])
        group = grouped.setdefault(
            key,
            {
                "legacySourceAddress": row["legacySourceAddress"],
                "legacySourceDigest": row["legacySourceDigest"],
                "creatureName": row["creatureName"],
                "gladiatorIds": [],
            },
        )
        if group["creatureName"] != row["creatureName"]:
            raise LegacyRosterPublicationError(
                "one legacy source identity has conflicting creature names"
            )
        group["gladiatorIds"].append(row["gladiatorId"])
    if len(grouped) != 160:
        raise LegacyRosterPublicationError(
            f"legacy identity-pair census changed: expected=160, actual={len(grouped)}"
        )

    bindings = []
    for key in sorted(grouped):
        group = grouped[key]
        address = group["legacySourceAddress"]
        if address in REVIEWED_BINDINGS:
            entity_id, package_id = REVIEWED_BINDINGS[address]
            package = packages_by_id[package_id]
            support = "reviewed-executable"
            current_address = address
            runtime_blockers: list[str] = []
        else:
            target = legacy_by_address[address]
            package = legacy_package
            entity_id = target.entity_id
            support = "persistence-only-runtime-blocked"
            current_address = (
                f"{PF2ER_LEGACY_ROSTER_SOURCE_ID}:{target.current_locator}"
            )
            runtime_blockers = [PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER]
        if package.entity(entity_id).definition.get("name") != group["creatureName"]:
            raise LegacyRosterPublicationError(
                "legacy source identity and semantic entity name disagree"
            )
        bindings.append(
            {
                **group,
                "gladiatorIds": sorted(group["gladiatorIds"]),
                "currentPrivateSourceAddress": current_address,
                "runtimeSupport": support,
                "runtimeBlockers": runtime_blockers,
                "entityPin": _entity_pin(package, entity_id),
            }
        )

    manifest = {
        "schema": 1,
        "kind": "pf2er-legacy-roster-semantic-binding-manifest",
        "legacyGladiatorCount": len(rows),
        "legacyIdentityPairCount": len(bindings),
        "legacySourceAddressCount": len(actual_addresses),
        "omissions": [],
        "bindings": bindings,
    }
    audit = {
        "schema": 1,
        "kind": "pf2er-legacy-roster-publication-audit",
        "legacyGladiatorCount": len(rows),
        "legacyIdentityPairCount": len(bindings),
        "legacySourceAddressCount": len(actual_addresses),
        "publishedEntityCount": sum(len(package.entities) for package in packages),
        "newPersistenceOnlyEntityCount": len(PF2ER_LEGACY_ROSTER_TARGETS),
        "reviewedRosterEntityCount": len(REVIEWED_BINDINGS),
        "privateSourceReconnections": [
            {
                "legacySourceAddress": target.legacy_source_address,
                "currentPrivateSourceAddress": (
                    f"{PF2ER_LEGACY_ROSTER_SOURCE_ID}:{target.current_locator}"
                ),
            }
            for target in PF2ER_LEGACY_ROSTER_TARGETS
            if target.legacy_locator != target.current_locator
        ],
        "omissions": [],
        "materializedAssetRefs": [
            {
                "assetId": pf2er_semantic.PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID,
                "assetDigest": XULGATH_ICON_DIGEST,
            }
        ],
        "packageDigests": [
            {
                "packageId": package.package_id,
                "version": package.version,
                "packageDigest": package.package_digest,
            }
            for package in sorted(
                packages, key=lambda item: (item.package_id, item.version)
            )
        ],
    }
    return manifest, audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic PF2ER legacy-roster publication."
    )
    parser.add_argument("--cache-db", type=Path, required=True)
    parser.add_argument("--legacy-world-db", type=Path, required=True)
    parser.add_argument("--base-package-dir", type=Path, required=True)
    parser.add_argument("--xulgath-icon", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise LegacyRosterPublicationError("output directory must be empty")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    bundle_directory = args.output_dir / "bundle"
    package_directory = bundle_directory / "semantic-packages"
    asset_directory = bundle_directory / "semantic-assets"
    blob_directory = asset_directory / "blobs"
    package_directory.mkdir(parents=True, mode=0o755)
    blob_directory.mkdir(parents=True, mode=0o755)

    base_packages = _load_base_packages(args.base_package_dir)
    store = SourceAuthorityStore.from_path(args.cache_db)
    authority = store.adapter_for(("core-gmc", "core-mc1", "core-pc1"))
    compiler_set = pf2er_semantic.build_pf2er_semantic_compiler_set(
        book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
    )
    evidence_store = SemanticEvidenceStore()
    legacy_package = build_legacy_roster_semantic_package(
        authority=authority,
        compiler_set=compiler_set,
        evidence_store=evidence_store,
    )
    xulgath_package = _build_xulgath_package(
        authority,
        compiler_set,
        evidence_store,
    )
    packages = (*base_packages, legacy_package, xulgath_package)
    catalog = SemanticCatalogSnapshot.from_selected_packages(packages)
    rows = _legacy_rows(args.legacy_world_db)
    bindings, audit = _binding_artifacts(rows, packages)

    if args.xulgath_icon.is_symlink() or not args.xulgath_icon.is_file():
        raise LegacyRosterPublicationError(
            "Xulgath icon must be one exact regular file"
        )
    icon_bytes = args.xulgath_icon.read_bytes()
    icon_ref = AssetRef(
        pf2er_semantic.PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID,
        XULGATH_ICON_DIGEST,
    )
    icon = SemanticAssetArtifact.from_bytes(
        icon_ref,
        "image/webp",
        icon_bytes,
    )
    asset_store = TtrpgSemanticAssetStore()
    asset_store.publish((icon,))
    asset_snapshot = asset_store.open_snapshot((icon_ref,))

    for package in packages:
        (package_directory / f"{package.package_digest}.json").write_bytes(
            package.canonical_json()
        )
    (asset_directory / "index.json").write_bytes(
        canonical_json(asset_snapshot.inventory_projection())
    )
    (blob_directory / XULGATH_ICON_DIGEST).write_bytes(icon_bytes)
    (args.output_dir / "catalog-manifest.json").write_bytes(
        catalog.canonical_manifest_json()
    )
    (args.output_dir / "private-evidence.json").write_bytes(
        evidence_store.snapshot().canonical_json()
    )
    (args.output_dir / "private-migration-bindings.json").write_bytes(
        canonical_json(bindings)
    )
    (args.output_dir / "publication-audit.json").write_bytes(
        canonical_json(audit)
    )

    outputs = []
    for path in sorted(args.output_dir.rglob("*")):
        if path.is_file():
            body = path.read_bytes()
            outputs.append(
                {
                    "path": str(path.relative_to(args.output_dir)),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "size": len(body),
                }
            )
    print(
        canonical_json(
            {
                "catalogDigest": catalog.catalog_digest,
                "packageCount": len(packages),
                "publishedEntityCount": len(catalog.entities),
                "legacyGladiatorCount": len(rows),
                "legacyIdentityPairCount": 160,
                "legacySourceAddressCount": 94,
                "omissionCount": 0,
                "outputs": outputs,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

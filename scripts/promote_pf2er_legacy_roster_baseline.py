#!/usr/bin/env python3
"""Promote the sealed legacy roster from display-only to baseline combat.

This operator consumes one exact prior roster publication, recompiles the
already imported creature targets from the pinned private authority, and emits
a new immutable publication.  Presentation assets are copied byte-for-byte;
only the legacy creature package, its evidence, catalog, and migration pins
change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import build_pf2er_legacy_roster_publication as publication
from scripts.pf2er_legacy_roster_semantic import (
    PF2ER_LEGACY_ROSTER_PACKAGE_ID,
    PF2ER_LEGACY_ROSTER_SOURCE_ID,
    PF2ER_LEGACY_ROSTER_TARGETS,
    build_legacy_roster_semantic_package,
    pf2er_roster_portrait_asset_id,
)
from scripts.pf2er_roster_source_presentation import RosterSourcePresentation
from subdomains.ttrpg import pf2er_semantic
from subdomains.ttrpg.pf2er_compiler.source_authority_store import (
    SourceAuthorityStore,
)
from subdomains.ttrpg.semantic_catalog import SemanticCatalogSnapshot
from subdomains.ttrpg.semantic_evidence import (
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
)
from subdomains.ttrpg.semantic_packages import AssetRef, SemanticPackage


class LegacyRosterBaselinePromotionError(RuntimeError):
    """The prior publication or its baseline promotion is invalid."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _json_file(path: Path, label: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise LegacyRosterBaselinePromotionError(f"{label} must be a regular file")
    body = path.read_bytes()
    try:
        packet = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyRosterBaselinePromotionError(f"{label} is invalid JSON") from exc
    if type(packet) is not dict or _canonical_json(packet) != body:
        raise LegacyRosterBaselinePromotionError(f"{label} is not canonical JSON")
    return packet


def _packages(directory: Path) -> tuple[SemanticPackage, ...]:
    if directory.is_symlink() or not directory.is_dir():
        raise LegacyRosterBaselinePromotionError(
            "prior semantic package directory is invalid"
        )
    packages = []
    for path in sorted(directory.glob("*.json")):
        package = SemanticPackage.from_dict(_json_file(path, "semantic package"))
        if path.stem != package.package_digest:
            raise LegacyRosterBaselinePromotionError(
                "semantic package filename is not its digest"
            )
        packages.append(package)
    if len(packages) != 6 or len({item.package_id for item in packages}) != 6:
        raise LegacyRosterBaselinePromotionError(
            "prior publication must contain the exact six-package roster selection"
        )
    return tuple(packages)


def _source_presentation(entity) -> RosterSourcePresentation:
    definition = entity.definition
    presentation = definition.get("presentation")
    if type(presentation) is not dict:
        raise LegacyRosterBaselinePromotionError(
            f"legacy entity presentation is missing: {entity.entity_id}"
        )
    envelope = presentation.get("sourceNodeView")
    if type(envelope) is not dict or set(envelope) != {
        "schema",
        "packetAssetId",
        "closureManifestAssetId",
    }:
        raise LegacyRosterBaselinePromotionError(
            f"legacy entity source view is invalid: {entity.entity_id}"
        )
    refs = {item.asset_id: item for item in entity.asset_refs}
    try:
        packet_ref = refs[envelope["packetAssetId"]]
        closure_ref = refs[envelope["closureManifestAssetId"]]
    except (KeyError, TypeError) as exc:
        raise LegacyRosterBaselinePromotionError(
            f"legacy entity source view closure is incomplete: {entity.entity_id}"
        ) from exc
    return RosterSourcePresentation(
        envelope=dict(envelope),
        asset_refs=entity.asset_refs,
        packet_ref=packet_ref,
        closure_manifest_ref=closure_ref,
    )


def _portrait_refs(entity) -> tuple[AssetRef, AssetRef]:
    refs = {item.asset_id: item for item in entity.asset_refs}
    expected = (
        pf2er_roster_portrait_asset_id(entity.entity_id, "x128"),
        pf2er_roster_portrait_asset_id(entity.entity_id, "x512"),
    )
    try:
        return refs[expected[0]], refs[expected[1]]
    except KeyError as exc:
        raise LegacyRosterBaselinePromotionError(
            f"legacy entity portrait closure is incomplete: {entity.entity_id}"
        ) from exc


def _evidence_record(packet: object) -> SemanticEvidenceRecord:
    if type(packet) is not dict:
        raise LegacyRosterBaselinePromotionError("private evidence record is invalid")
    return SemanticEvidenceRecord.build(
        evidence_authority_id=packet.get("evidenceAuthorityId"),
        entity_id=packet.get("entityId"),
        compiler_digest=packet.get("compilerDigest"),
        raw_definition_digest=packet.get("rawDefinitionDigest"),
        projected_definition_digest=packet.get("projectedDefinitionDigest"),
        projection_id=packet.get("projectionId"),
        projection_version=packet.get("projectionVersion"),
        projection_digest=packet.get("projectionDigest"),
        acquisition_receipt=packet.get("acquisitionReceipt"),
        compiler_receipt=packet.get("compilerReceipt"),
        expected_evidence_record_digest=packet.get("evidenceRecordDigest"),
    )


def promote(*, cache_db: Path, prior_root: Path, output_root: Path) -> dict[str, object]:
    if output_root.exists() and any(output_root.iterdir()):
        raise LegacyRosterBaselinePromotionError("output directory must be empty")
    prior_bundle = prior_root / "bundle"
    packages = _packages(prior_bundle / "semantic-packages")
    old_legacy = next(
        (
            package
            for package in packages
            if package.package_id == PF2ER_LEGACY_ROSTER_PACKAGE_ID
        ),
        None,
    )
    if old_legacy is None or len(old_legacy.entities) != 91:
        raise LegacyRosterBaselinePromotionError(
            "prior publication omits the exact legacy roster package"
        )
    old_by_id = {entity.entity_id: entity for entity in old_legacy.entities}
    expected_ids = {target.entity_id for target in PF2ER_LEGACY_ROSTER_TARGETS}
    if set(old_by_id) != expected_ids:
        raise LegacyRosterBaselinePromotionError(
            "prior legacy roster entity census changed"
        )

    store = SourceAuthorityStore.from_path(cache_db)
    authority = store.adapter_for(("core-gmc", "core-mc1", "core-pc1"))
    compiler = pf2er_semantic.build_pf2er_semantic_compiler_set(
        book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
    )
    evidence = SemanticEvidenceStore()
    new_legacy = build_legacy_roster_semantic_package(
        authority=authority,
        compiler_set=compiler,
        evidence_store=evidence,
        portrait_asset_refs={
            entity_id: _portrait_refs(old_by_id[entity_id])
            for entity_id in sorted(old_by_id)
        },
        source_presentations={
            entity_id: _source_presentation(old_by_id[entity_id])
            for entity_id in sorted(old_by_id)
        },
    )
    selected = tuple(
        sorted(
            [
                new_legacy
                if package.package_id == PF2ER_LEGACY_ROSTER_PACKAGE_ID
                else package
                for package in packages
            ],
            key=lambda item: (item.package_id, item.version),
        )
    )
    old_refs = {
        ref
        for package in packages
        for entity in package.entities
        for ref in entity.asset_refs
    }
    new_refs = {
        ref
        for package in selected
        for entity in package.entities
        for ref in entity.asset_refs
    }
    if new_refs != old_refs:
        raise LegacyRosterBaselinePromotionError(
            "baseline promotion changed the exact presentation asset closure"
        )

    prior_evidence = _json_file(
        prior_root / "private-evidence.json", "private evidence"
    )
    prior_records = prior_evidence.get("records")
    if type(prior_records) is not list:
        raise LegacyRosterBaselinePromotionError(
            "private evidence record inventory is invalid"
        )
    retained_records = tuple(
        _evidence_record(packet)
        for packet in prior_records
        if type(packet) is dict and packet.get("entityId") not in expected_ids
    )
    if retained_records:
        evidence.provision_many(retained_records)

    bindings = _json_file(
        prior_root / "private-migration-bindings.json", "migration bindings"
    )
    rows = bindings.get("bindings")
    if type(rows) is not list:
        raise LegacyRosterBaselinePromotionError("migration bindings are invalid")
    for row in rows:
        if type(row) is not dict:
            raise LegacyRosterBaselinePromotionError("migration binding row is invalid")
        entity_pin = row.get("entityPin")
        entity_id = entity_pin.get("entityId") if type(entity_pin) is dict else None
        if entity_id not in expected_ids:
            continue
        entity = new_legacy.entity(entity_id)
        blockers = list(entity.definition.get("runtimeBlockers", []))
        row["runtimeSupport"] = (
            "persistence-only-runtime-blocked"
            if blockers
            else "baseline-executable"
        )
        row["runtimeBlockers"] = blockers
        row["entityPin"] = {
            "package": {
                "packageId": new_legacy.package_id,
                "version": new_legacy.version,
                "packageDigest": new_legacy.package_digest,
            },
            "entityId": entity.entity_id,
            "definitionDigest": entity.definition_digest,
            "semanticReceiptDigest": entity.receipt.semantic_receipt_digest,
        }

    output_root.mkdir(parents=True, exist_ok=True)
    output_bundle = output_root / "bundle"
    package_directory = output_bundle / "semantic-packages"
    package_directory.mkdir(parents=True)
    for package in selected:
        (package_directory / f"{package.package_digest}.json").write_bytes(
            package.canonical_json()
        )
    shutil.copytree(
        prior_bundle / "semantic-assets",
        output_bundle / "semantic-assets",
        copy_function=shutil.copy2,
    )
    catalog = SemanticCatalogSnapshot.from_selected_packages(selected)
    (output_root / "catalog-manifest.json").write_bytes(
        catalog.canonical_manifest_json()
    )
    (output_root / "private-evidence.json").write_bytes(
        evidence.snapshot().canonical_json()
    )
    (output_root / "private-migration-bindings.json").write_bytes(
        _canonical_json(bindings)
    )

    audit = _json_file(prior_root / "publication-audit.json", "publication audit")
    audit.pop("newPersistenceOnlyEntityCount", None)
    audit["newBaselineExecutableEntityCount"] = sum(
        not entity.definition.get("runtimeBlockers")
        for entity in new_legacy.entities
    )
    audit["newRuntimeBlockedEntityCount"] = sum(
        bool(entity.definition.get("runtimeBlockers"))
        for entity in new_legacy.entities
    )
    audit["packageDigests"] = [
        {
            "packageId": package.package_id,
            "version": package.version,
            "packageDigest": package.package_digest,
        }
        for package in sorted(selected, key=lambda item: (item.package_id, item.version))
    ]
    (output_root / "publication-audit.json").write_bytes(_canonical_json(audit))
    for name in ("portrait-manifest.json", "source-presentation-audit.json"):
        shutil.copy2(prior_root / name, output_root / name)

    return {
        "schema": 1,
        "kind": "pf2er-legacy-roster-baseline-promotion",
        "priorLegacyPackageDigest": old_legacy.package_digest,
        "legacyPackageDigest": new_legacy.package_digest,
        "legacyPackageVersion": new_legacy.version,
        "catalogDigest": catalog.catalog_digest,
        "entityCount": len(new_legacy.entities),
        "runtimeBlockedEntityCount": sum(
            bool(entity.definition.get("runtimeBlockers"))
            for entity in new_legacy.entities
        ),
        "baselineStrikeCount": sum(
            len(entity.definition.get("strikes", []))
            for entity in new_legacy.entities
        ),
        "assetRefCount": len(new_refs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-db", type=Path, required=True)
    parser.add_argument("--prior-publication-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = promote(
        cache_db=args.cache_db,
        prior_root=args.prior_publication_root,
        output_root=args.output_root,
    )
    print(_canonical_json(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

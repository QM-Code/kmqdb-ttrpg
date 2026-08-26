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
from subdomains.ttrpg.pf2er_compiler.source import source_creature_description
from scripts.pf2er_legacy_roster_semantic import (
    PF2ER_LEGACY_ROSTER_BOOK_DIGEST,
    PF2ER_LEGACY_ROSTER_RULESET_DIGEST,
    PF2ER_LEGACY_ROSTER_RUNTIME_BLOCKER,
    PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER,
    PF2ER_LEGACY_ROSTER_VIEWER_TIER,
    PF2ER_LEGACY_ROSTER_SOURCE_ID,
    PF2ER_LEGACY_ROSTER_TARGETS,
    build_legacy_roster_semantic_package,
    pf2er_roster_portrait_asset_id,
)
from scripts.pf2er_roster_source_presentation import (
    RosterSourcePresentation,
    build_roster_source_presentations,
)
from subdomains.ttrpg.semantic_assets import (
    SemanticAssetArtifact,
    TtrpgSemanticAssetStore,
)
from subdomains.ttrpg.semantic_catalog import SemanticCatalogSnapshot
from subdomains.ttrpg.semantic_evidence import (
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
    canonical_digest,
)
from subdomains.ttrpg.semantic_package_builder import SourceCreatureTarget
from subdomains.ttrpg.semantic_packages import (
    AssetRef,
    SemanticPackage,
    build_semantic_entity,
    build_semantic_package,
)


XULGATH_ICON_DIGEST = (
    "aa81ad330e38bf2f04521ce524ab07cc06add632bd9447edee529cb8a0a400f9"
)
ROSTER_PORTRAIT_MANIFEST_DIGEST = (
    "6b32af1f7e7fcfdb3c197d351932c8be87ec8cdd62f78b1941db93fdc1e2cb5c"
)
REVIEWED_PRESENTATION_PROJECTION_ID = (
    "ttrpg:pf2er-reviewed-creature-roster-presentation"
)
REVIEWED_PRESENTATION_PROJECTION_VERSION = "3.0.0"
REVIEWED_PRESENTATION_EVIDENCE_AUTHORITY_ID = (
    "ttrpg:pf2er-reviewed-roster-presentation-evidence"
)
_REVIEWED_PRESENTATION_PROJECTION_MANIFEST = {
    "schema": 1,
    "projectionId": REVIEWED_PRESENTATION_PROJECTION_ID,
    "projectionVersion": REVIEWED_PRESENTATION_PROJECTION_VERSION,
    "kind": "reviewed-creature-description-and-presentation-augmentation",
    "presentationPolicy": {
        "kind": "opaque-portraits-and-exact-source-node-view",
        "thumbnailTier": PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER,
        "viewerTier": PF2ER_LEGACY_ROSTER_VIEWER_TIER,
        "sourceNodeView": "exact-packet-and-content-addressed-offline-closure-v1",
    },
    "descriptionPolicy": "exact-generic-source-prose",
    "mechanicsPolicy": "preserve-exactly",
}
REVIEWED_PRESENTATION_PROJECTION_DIGEST = canonical_digest(
    _REVIEWED_PRESENTATION_PROJECTION_MANIFEST,
    "reviewed roster presentation projection",
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
REVIEWED_PORTRAIT_NAMES = {
    "pf2er:hadrosaurid": "Hadrosaurid",
    "pf2er:viper": "Viper",
    pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID: "Xulgath Warrior",
}
REVIEWED_SOURCE_LOCATORS = {
    "pf2er:hadrosaurid": "98.2",
    "pf2er:viper": "316.2",
    pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID: "352.3",
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


def _portrait_inventory(
    directory: Path,
) -> tuple[
    dict[str, tuple[AssetRef, AssetRef]],
    tuple[SemanticAssetArtifact, ...],
    dict[str, object],
]:
    """Authenticate the exact complete x128/x512 roster asset closure."""

    if directory.is_symlink() or not directory.is_dir():
        raise LegacyRosterPublicationError(
            "portrait directory must be one regular directory"
        )
    names_by_entity = {
        target.entity_id: target.name for target in PF2ER_LEGACY_ROSTER_TARGETS
    }
    names_by_entity.update(REVIEWED_PORTRAIT_NAMES)
    if len(names_by_entity) != 94:
        raise LegacyRosterPublicationError(
            "roster portrait target census changed"
        )

    refs: dict[str, tuple[AssetRef, AssetRef]] = {}
    artifacts = []
    entries = []
    missing = []
    for entity_id, creature_name in sorted(names_by_entity.items()):
        entry: dict[str, object] = {
            "entityId": entity_id,
            "creatureName": creature_name,
        }
        entity_refs = []
        for role, tier in (
            ("thumbnail", PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER),
            ("viewer", PF2ER_LEGACY_ROSTER_VIEWER_TIER),
        ):
            path = directory / tier / f"{creature_name}.webp"
            if path.is_symlink() or not path.is_file():
                missing.append(f"{tier}/{creature_name}")
                continue
            body = path.read_bytes()
            if (
                len(body) < 16
                or body[:4] != b"RIFF"
                or body[8:12] != b"WEBP"
            ):
                raise LegacyRosterPublicationError(
                    f"roster portrait is not a WebP file: {tier}/{creature_name}"
                )
            asset_ref = AssetRef(
                pf2er_roster_portrait_asset_id(entity_id, tier),
                hashlib.sha256(body).hexdigest(),
            )
            entity_refs.append(asset_ref)
            artifacts.append(
                SemanticAssetArtifact.from_bytes(asset_ref, "image/webp", body)
            )
            entry[role] = {
                "assetId": asset_ref.asset_id,
                "assetDigest": asset_ref.asset_digest,
                "size": len(body),
            }
        if len(entity_refs) == 2:
            refs[entity_id] = (entity_refs[0], entity_refs[1])
            entries.append(entry)
    if missing:
        raise LegacyRosterPublicationError(
            "roster portraits are incomplete; missing=" + ", ".join(missing)
        )

    manifest = {
        "schema": 2,
        "mediaType": "image/webp",
        "tiers": {
            "thumbnail": PF2ER_LEGACY_ROSTER_THUMBNAIL_TIER,
            "viewer": PF2ER_LEGACY_ROSTER_VIEWER_TIER,
        },
        "portraits": entries,
    }
    actual_digest = canonical_digest(
        manifest,
        "legacy roster portrait source manifest",
    )
    if actual_digest != ROSTER_PORTRAIT_MANIFEST_DIGEST:
        raise LegacyRosterPublicationError(
            "roster portrait source manifest drifted; "
            f"expected={ROSTER_PORTRAIT_MANIFEST_DIGEST}, actual={actual_digest}"
        )
    return refs, tuple(artifacts), manifest


def _augment_reviewed_presentation(
    package: SemanticPackage,
    *,
    authority,
    entity_id: str,
    source_locator: str,
    description: str,
    source_languages: list[str],
    portrait_refs: tuple[AssetRef, AssetRef],
    source_presentation: RosterSourcePresentation,
    evidence_store: SemanticEvidenceStore,
) -> SemanticPackage:
    """Add only authenticated prose and portraits to a reviewed creature."""

    base_entity = package.entity(entity_id)
    if type(description) is not str or not description:
        raise LegacyRosterPublicationError(
            f"reviewed creature description is empty: {entity_id}"
        )
    if type(source_languages) is not list or any(
        type(item) is not str for item in source_languages
    ):
        raise LegacyRosterPublicationError(
            f"reviewed creature languages are invalid: {entity_id}"
        )
    if type(portrait_refs) is not tuple or len(portrait_refs) != 2:
        raise LegacyRosterPublicationError(
            f"reviewed creature portrait closure is invalid: {entity_id}"
        )
    if not isinstance(source_presentation, RosterSourcePresentation):
        raise LegacyRosterPublicationError(
            f"reviewed creature source presentation is invalid: {entity_id}"
        )
    source_selection = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=PF2ER_LEGACY_ROSTER_SOURCE_ID,
                locator=source_locator,
            )
        )
    )
    definition = base_entity.definition
    if "languages" in definition and definition["languages"] != source_languages:
        raise LegacyRosterPublicationError(
            f"reviewed creature languages drifted: {entity_id}"
        )
    definition["languages"] = source_languages
    definition["description"] = description
    definition["presentation"] = {
        "iconAssetId": portrait_refs[0].asset_id,
        "viewerAssetId": portrait_refs[1].asset_id,
        "sourceNodeView": source_presentation.envelope,
    }
    raw_definition_digest = canonical_digest(
        {
            "schema": 1,
            "baseDefinition": base_entity.definition,
            "genericDescription": description,
            "sourceLanguages": source_languages,
        },
        "reviewed creature presentation input",
    )
    projected_definition_digest = canonical_digest(
        definition,
        "reviewed creature presentation definition",
    )
    record = SemanticEvidenceRecord.build(
        evidence_authority_id=REVIEWED_PRESENTATION_EVIDENCE_AUTHORITY_ID,
        entity_id=entity_id,
        compiler_digest=package.compiler_digest,
        raw_definition_digest=raw_definition_digest,
        projected_definition_digest=projected_definition_digest,
        projection_id=REVIEWED_PRESENTATION_PROJECTION_ID,
        projection_version=REVIEWED_PRESENTATION_PROJECTION_VERSION,
        projection_digest=REVIEWED_PRESENTATION_PROJECTION_DIGEST,
        acquisition_receipt={
            "schema": 1,
            "kind": "reviewed-semantic-package-presentation-augmentation",
            "basePackageId": package.package_id,
            "basePackageVersion": package.version,
            "basePackageDigest": package.package_digest,
            "baseSemanticReceiptDigest": (
                base_entity.receipt.semantic_receipt_digest
            ),
            "currentSelection": source_selection.receipt.as_serialized(),
            "portraitAssetRefs": [item.to_dict() for item in portrait_refs],
            "sourceNodePacketAssetRef": source_presentation.packet_ref.to_dict(),
            "sourceNodeClosureManifestAssetRef": (
                source_presentation.closure_manifest_ref.to_dict()
            ),
        },
        compiler_receipt={
            "schema": 1,
            "projection": _REVIEWED_PRESENTATION_PROJECTION_MANIFEST,
            "mechanicsPreservedFromDefinitionDigest": (
                base_entity.definition_digest
            ),
            "genericDescriptionDigest": canonical_digest(
                description,
                "reviewed creature generic description",
            ),
            "sourceLanguages": source_languages,
        },
    )
    augmented_entity = build_semantic_entity(
        entity_id=entity_id,
        entity_kind=base_entity.entity_kind,
        definition=definition,
        evidence_authority_id=REVIEWED_PRESENTATION_EVIDENCE_AUTHORITY_ID,
        evidence_record_digest=record.evidence_record_digest,
        compiler_digest=package.compiler_digest,
        raw_definition_digest=raw_definition_digest,
        projection_id=REVIEWED_PRESENTATION_PROJECTION_ID,
        projection_version=REVIEWED_PRESENTATION_PROJECTION_VERSION,
        projection_digest=REVIEWED_PRESENTATION_PROJECTION_DIGEST,
        required_capabilities=base_entity.required_capabilities,
        asset_refs=tuple(
            sorted({*portrait_refs, *source_presentation.asset_refs})
        ),
    )
    entities = tuple(
        augmented_entity if entity.entity_id == entity_id else entity
        for entity in package.entities
    )
    semantic_generation = f"{package.semantic_generation}-roster-presentation-3"
    semantic_generation_digest = canonical_digest(
        {
            "schema": 1,
            "semanticGeneration": semantic_generation,
            "basePackageDigest": package.package_digest,
            "entityId": entity_id,
            "projectedDefinitionDigest": projected_definition_digest,
            "genericDescriptionDigest": canonical_digest(
                description,
                "reviewed creature generic description",
            ),
            "portraitAssetRefs": [item.to_dict() for item in portrait_refs],
            "sourceNodePacketAssetRef": source_presentation.packet_ref.to_dict(),
            "sourceNodeClosureManifestAssetRef": (
                source_presentation.closure_manifest_ref.to_dict()
            ),
        },
        "reviewed creature presentation semantic generation",
    )
    augmented_package = build_semantic_package(
        package_id=package.package_id,
        version="1.3.0",
        ruleset_id=package.ruleset_id,
        ruleset_digest=package.ruleset_digest,
        book_id=package.book_id,
        book_digest=package.book_digest,
        semantic_generation=semantic_generation,
        semantic_generation_digest=semantic_generation_digest,
        compiler_id=package.compiler_id,
        compiler_version=package.compiler_version,
        compiler_digest=package.compiler_digest,
        entities=entities,
        relationships=package.relationships,
    )
    evidence_store.provision_many((record,))
    return augmented_package


def _build_xulgath_package(
    authority,
    compiler_set,
    evidence_store,
    portrait_ref: AssetRef,
):
    if (
        portrait_ref.asset_id
        != pf2er_semantic.PF2ER_XULGATH_WARRIOR_ICON_ASSET_ID
        or portrait_ref.asset_digest != XULGATH_ICON_DIGEST
    ):
        raise LegacyRosterPublicationError(
            "reviewed Xulgath portrait binding drifted"
        )
    target = SourceCreatureTarget(
        pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID,
        "core-mc1",
        "352.3",
        required_capabilities=(
            pf2er_semantic.PF2ER_STENCH_LIFECYCLE_CAPABILITY,
        ),
        asset_refs=(portrait_ref,),
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
    portrait_manifest: dict[str, object],
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
        "rosterPortraitCount": len(portrait_manifest["portraits"]),
        "rosterPortraitTiers": portrait_manifest["tiers"],
        "rosterPortraitBytes": {
            role: sum(
                item[role]["size"]
                for item in portrait_manifest["portraits"]
            )
            for role in ("thumbnail", "viewer")
        },
        "rosterPortraitManifestDigest": ROSTER_PORTRAIT_MANIFEST_DIGEST,
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
                "assetId": item[role]["assetId"],
                "assetDigest": item[role]["assetDigest"],
                "size": item[role]["size"],
            }
            for item in portrait_manifest["portraits"]
            for role in ("thumbnail", "viewer")
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
    parser.add_argument("--presentation-cache-db", type=Path, required=True)
    parser.add_argument("--legacy-world-db", type=Path, required=True)
    parser.add_argument("--base-package-dir", type=Path, required=True)
    parser.add_argument("--portrait-root", type=Path, required=True)
    parser.add_argument("--library-asset-root", type=Path, required=True)
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
    portrait_refs, portrait_artifacts, portrait_manifest = (
        _portrait_inventory(args.portrait_root)
    )
    presentation_targets = [
        (target.entity_id, target.name, target.current_locator)
        for target in PF2ER_LEGACY_ROSTER_TARGETS
    ]
    presentation_targets.extend(
        (
            entity_id,
            REVIEWED_PORTRAIT_NAMES[entity_id],
            locator,
        )
        for entity_id, locator in sorted(REVIEWED_SOURCE_LOCATORS.items())
    )
    source_presentations, source_presentation_artifacts, source_presentation_audit = (
        build_roster_source_presentations(
            cache_path=args.presentation_cache_db,
            targets=presentation_targets,
            library_asset_root=args.library_asset_root,
        )
    )
    store = SourceAuthorityStore.from_path(args.cache_db)
    authority = store.adapter_for(("core-gmc", "core-mc1", "core-pc1"))
    compiler_set = pf2er_semantic.build_pf2er_semantic_compiler_set(
        book_ids=(pf2er_semantic.PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
    )
    evidence_store = SemanticEvidenceStore()
    reviewed_package_by_entity = {
        "pf2er:hadrosaurid": (
            "ttrpg:pf2er-monster-core-one-hadrosaurid-trample"
        ),
        "pf2er:viper": "ttrpg:pf2er-monster-core-one-viper-slink",
    }
    augmented_base_packages = []
    for package in base_packages:
        matching_entity_ids = [
            entity_id
            for entity_id, package_id in reviewed_package_by_entity.items()
            if package.package_id == package_id
        ]
        if len(matching_entity_ids) > 1:
            raise LegacyRosterPublicationError(
                "one reviewed package unexpectedly owns multiple portrait targets"
            )
        if matching_entity_ids:
            entity_id = matching_entity_ids[0]
            source_locator = REVIEWED_SOURCE_LOCATORS[entity_id]
            source_definition = compiler_set.compile_source_creature(
                authority,
                PF2ER_LEGACY_ROSTER_SOURCE_ID,
                source_locator,
            )
            package = _augment_reviewed_presentation(
                package,
                authority=authority,
                entity_id=entity_id,
                source_locator=source_locator,
                description=source_creature_description(
                    authority,
                    PF2ER_LEGACY_ROSTER_SOURCE_ID,
                    source_locator,
                ),
                source_languages=source_definition["languages"],
                portrait_refs=portrait_refs[entity_id],
                source_presentation=source_presentations[entity_id],
                evidence_store=evidence_store,
            )
        augmented_base_packages.append(package)
    base_packages = tuple(augmented_base_packages)
    legacy_package = build_legacy_roster_semantic_package(
        authority=authority,
        compiler_set=compiler_set,
        evidence_store=evidence_store,
        portrait_asset_refs={
            target.entity_id: portrait_refs[target.entity_id]
            for target in PF2ER_LEGACY_ROSTER_TARGETS
        },
        source_presentations={
            target.entity_id: source_presentations[target.entity_id]
            for target in PF2ER_LEGACY_ROSTER_TARGETS
        },
    )
    xulgath_entity_id = pf2er_semantic.PF2ER_XULGATH_WARRIOR_ENTITY_ID
    xulgath_source_definition = compiler_set.compile_source_creature(
        authority,
        PF2ER_LEGACY_ROSTER_SOURCE_ID,
        REVIEWED_SOURCE_LOCATORS[xulgath_entity_id],
    )
    xulgath_package = _build_xulgath_package(
        authority,
        compiler_set,
        evidence_store,
        portrait_refs[xulgath_entity_id][0],
    )
    xulgath_package = _augment_reviewed_presentation(
        xulgath_package,
        authority=authority,
        entity_id=xulgath_entity_id,
        source_locator=REVIEWED_SOURCE_LOCATORS[xulgath_entity_id],
        description=source_creature_description(
            authority,
            PF2ER_LEGACY_ROSTER_SOURCE_ID,
            REVIEWED_SOURCE_LOCATORS[xulgath_entity_id],
        ),
        source_languages=xulgath_source_definition["languages"],
        portrait_refs=portrait_refs[xulgath_entity_id],
        source_presentation=source_presentations[xulgath_entity_id],
        evidence_store=evidence_store,
    )
    packages = (*base_packages, legacy_package, xulgath_package)
    catalog = SemanticCatalogSnapshot.from_selected_packages(packages)
    rows = _legacy_rows(args.legacy_world_db)
    bindings, audit = _binding_artifacts(
        rows,
        packages,
        portrait_manifest,
    )
    audit["sourcePresentation"] = source_presentation_audit

    package_asset_refs = tuple(
        sorted(
            {
                asset_ref
                for package in packages
                for entity in package.entities
                for asset_ref in entity.asset_refs
            }
        )
    )
    all_artifacts = (*portrait_artifacts, *source_presentation_artifacts)
    expected_asset_refs = tuple(
        sorted({artifact.asset_ref for artifact in all_artifacts})
    )
    if package_asset_refs != expected_asset_refs:
        raise LegacyRosterPublicationError(
            "semantic packages do not have exact presentation asset closure"
        )
    asset_store = TtrpgSemanticAssetStore()
    asset_store.publish(tuple(all_artifacts))
    asset_snapshot = asset_store.open_snapshot(expected_asset_refs)

    for package in packages:
        (package_directory / f"{package.package_digest}.json").write_bytes(
            package.canonical_json()
        )
    (asset_directory / "index.json").write_bytes(
        canonical_json(asset_snapshot.inventory_projection())
    )
    for artifact in all_artifacts:
        (blob_directory / artifact.asset_ref.asset_digest).write_bytes(
            artifact.asset_bytes
        )
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
    (args.output_dir / "portrait-manifest.json").write_bytes(
        canonical_json(portrait_manifest)
    )
    (args.output_dir / "source-presentation-audit.json").write_bytes(
        canonical_json(source_presentation_audit)
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
                "portraitCount": len(portrait_artifacts),
                "portraitBytes": sum(
                    artifact.size for artifact in portrait_artifacts
                ),
                "portraitManifestDigest": ROSTER_PORTRAIT_MANIFEST_DIGEST,
                "assetSnapshotDigest": asset_snapshot.snapshot_digest,
                "sourcePresentationAssetCount": len(source_presentation_artifacts),
                "sourcePresentationBytes": sum(
                    artifact.size for artifact in source_presentation_artifacts
                ),
                "omissionCount": 0,
                "outputs": outputs,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

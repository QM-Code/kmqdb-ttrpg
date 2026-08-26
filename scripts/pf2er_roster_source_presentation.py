"""Exact offline Library presentation closure for PF2ER roster creatures.

This module does not translate source presentation into another stat schema.
It preserves the existing TTRPG ``source_node_packet`` byte structure and
binds every renderer/CSS/media dependency to one content-addressed semantic
asset.  Normalized executable creature semantics remain a separate concern.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterable

from subdomains.ttrpg.backend import source_node_packet
from subdomains.ttrpg.semantic_assets import SemanticAssetArtifact
from subdomains.ttrpg.semantic_packages import AssetRef


SOURCE_NODE_VIEW_SCHEMA = 1
SOURCE_NODE_CLOSURE_KIND = "kmqdb-source-node-view-closure"
_INTERFACE_MARKER = "KMQDB_SEALED_RENDERER_INTERFACE_V1"
_BUNDLE_MARKER = "KMQDB_SEALED_RENDERER_BUNDLE_V1"
_MEDIA_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*")


class RosterSourcePresentationError(ValueError):
    """The cached Library presentation cannot form one exact closure."""


@dataclass(frozen=True, slots=True)
class RosterSourcePresentation:
    """Public definition envelope and exact asset closure for one creature."""

    envelope: dict[str, object]
    asset_refs: tuple[AssetRef, ...]
    packet_ref: AssetRef
    closure_manifest_ref: AssetRef


class _Pairs(list[tuple[str, object]]):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _artifact(asset_id: str, media_type: str, body: bytes) -> SemanticAssetArtifact:
    digest = hashlib.sha256(body).hexdigest()
    ref = AssetRef(asset_id, digest)
    return SemanticAssetArtifact.from_bytes(ref, media_type.split(";", 1)[0], body)


def _content_asset_id(role: str, identity: str, body: bytes) -> str:
    identity_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    body_digest = hashlib.sha256(body).hexdigest()[:20]
    return f"ttrpg:pf2er-{role}-{identity_digest}-{body_digest}"


def _exact_metadata(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute(
        "SELECT key, value FROM metadata ORDER BY key"
    ).fetchall()
    result = {str(row[0]): str(row[1]) for row in rows}
    required = {
        "library_dataset": "karmak/games/ttrpg/pf2er",
        "ruleset": "pf2er",
    }
    if any(result.get(key) != value for key, value in required.items()):
        raise RosterSourcePresentationError(
            "source presentation cache identity is invalid"
        )
    generation = result.get("source_generation", "")
    if not re.fullmatch(r"[0-9a-f]{64}", generation):
        raise RosterSourcePresentationError(
            "source presentation cache generation is invalid"
        )
    return result


def _presentation_artifacts(
    connection: sqlite3.Connection,
) -> tuple[AssetRef, tuple[SemanticAssetArtifact, ...], dict[str, object]]:
    rows = connection.execute(
        "SELECT singleton, payload FROM presentation ORDER BY singleton"
    ).fetchall()
    if len(rows) != 1 or rows[0][0] != 1 or type(rows[0][1]) is not str:
        raise RosterSourcePresentationError("presentation manifest is not exact")
    manifest_body = rows[0][1].encode("utf-8")
    try:
        manifest = json.loads(rows[0][1])
    except json.JSONDecodeError as exc:
        raise RosterSourcePresentationError(
            "presentation manifest is not JSON"
        ) from exc
    if type(manifest) is not dict:
        raise RosterSourcePresentationError("presentation manifest must be an object")
    manifest_artifact = _artifact(
        _content_asset_id("source-presentation-manifest", "pf2er", manifest_body),
        "application/json",
        manifest_body,
    )

    asset_rows = connection.execute(
        "SELECT kind, asset_index, content_type, body "
        "FROM presentation_assets ORDER BY kind, asset_index"
    ).fetchall()
    expected = (("css", 0), ("css", 1), ("js", 0), ("js", 1))
    actual = tuple((str(row[0]), int(row[1])) for row in asset_rows)
    if actual != expected:
        raise RosterSourcePresentationError(
            f"presentation asset inventory changed: {actual!r}"
        )
    artifacts: list[SemanticAssetArtifact] = [manifest_artifact]
    entries: dict[str, list[dict[str, object]]] = {"css": [], "js": []}
    for kind, index, content_type, body_value in asset_rows:
        if type(body_value) is not bytes or not _MEDIA_TYPE_RE.match(str(content_type)):
            raise RosterSourcePresentationError("presentation asset row is invalid")
        body = body_value
        role = f"presentation-{kind}-{index}"
        artifact = _artifact(
            _content_asset_id(role, f"{kind}/{index}", body),
            str(content_type),
            body,
        )
        artifacts.append(artifact)
        entry: dict[str, object] = {
            "index": index,
            "path": f"/.api/presentation/{kind}/{index}",
            "assetRef": artifact.asset_ref.to_dict(),
        }
        if kind == "js":
            text = body.decode("utf-8")
            if index == 0:
                if _INTERFACE_MARKER not in text or _BUNDLE_MARKER in text:
                    raise RosterSourcePresentationError(
                        "presentation renderer interface is not sealed"
                    )
                entry["role"] = "renderer-interface"
            else:
                if _BUNDLE_MARKER not in text or _INTERFACE_MARKER in text:
                    raise RosterSourcePresentationError(
                        "presentation renderer bundle is not sealed"
                    )
                entry["role"] = "sealed-renderer-bundle"
        entries[kind].append(entry)
    projection = {
        "manifestAssetRef": manifest_artifact.asset_ref.to_dict(),
        "manifestSha256": hashlib.sha256(manifest_body).hexdigest(),
        "stylesheets": entries["css"],
        "scripts": entries["js"],
    }
    return manifest_artifact.asset_ref, tuple(artifacts), projection


def _pairs(value: list[tuple[str, object]]) -> _Pairs:
    return _Pairs(value)


def _field(value: _Pairs, key: str) -> object | None:
    matches = [item for name, item in value if name == key]
    if len(matches) > 1:
        raise RosterSourcePresentationError(
            f"selected creature has duplicate {key!r} fields"
        )
    return matches[0] if matches else None


def _creature_blocks(value: object) -> list[_Pairs]:
    result: list[_Pairs] = []
    if type(value) is _Pairs:
        for key, item in value:
            if key == "^.creature" and type(item) is _Pairs:
                result.append(item)
            result.extend(_creature_blocks(item))
    elif type(value) is list:
        for item in value:
            result.extend(_creature_blocks(item))
    return result


def _selected_media_references(
    packet: dict[str, object],
    creature_name: str,
) -> tuple[tuple[str, str, str], ...]:
    try:
        content = packet["content"]["section"]["content"]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise RosterSourcePresentationError(
            "source node packet has no selected section content"
        ) from exc
    if type(content) is not str:
        raise RosterSourcePresentationError("source section content is not exact text")
    try:
        raw = json.loads(content, object_pairs_hook=_pairs)
    except json.JSONDecodeError as exc:
        raise RosterSourcePresentationError("source section content is not JSON") from exc
    blocks = [
        block
        for block in _creature_blocks(raw)
        if _field(block, "Name") == creature_name
    ]
    if len(blocks) != 1:
        raise RosterSourcePresentationError(
            f"source packet has {len(blocks)} exact creature blocks for {creature_name}"
        )
    block = blocks[0]
    icon = _field(block, "Icon")
    if type(icon) is not str or not icon:
        raise RosterSourcePresentationError(
            f"source creature has no exact Icon: {creature_name}"
        )
    references: list[tuple[str, str, str]] = []
    icon_parts = icon.split("/")
    if len(icon_parts) < 3 or icon_parts[-2] != "x128":
        raise RosterSourcePresentationError(
            f"source creature Icon is not the x128 contract: {creature_name}"
        )
    for relative in (
        icon,
        "/".join((*icon_parts[:-2], "x256", icon_parts[-1])),
    ):
        references.append(("icon", relative, f"core/mc1/{relative}"))
    images = _field(block, "Image")
    if images is not None:
        image_values = images if type(images) is list else [images]
        for image in image_values:
            if type(image) is not str or not image:
                raise RosterSourcePresentationError(
                    f"source creature Image is invalid: {creature_name}"
                )
            parts = image.split("/")
            if len(parts) < 3:
                raise RosterSourcePresentationError(
                    f"source creature Image has no responsive tier: {creature_name}"
                )
            tiers = {
                "x1024": ("x256", "x512", "x1024"),
                "x1280x960": ("x320x240", "x640x480", "x1280x960"),
                "x960x1280": ("x240x320", "x480x640", "x960x1280"),
            }.get(parts[-3])
            if tiers is None:
                raise RosterSourcePresentationError(
                    f"source creature Image tier is unsupported: {creature_name}"
                )
            for tier in tiers:
                relative = "/".join((*parts[:-3], tier, *parts[-2:]))
                references.append(
                    ("image", relative, f"core/mc1/{relative}")
                )
    for action_icon in (
        "core/pc1/actions/Single Action",
        "core/pc1/actions/Two Actions",
        "core/pc1/actions/Three Actions",
        "core/pc1/actions/Reaction",
        "core/pc1/actions/Free Action",
    ):
        references.append(("icon", action_icon, action_icon))
    if len({(kind, resolved) for kind, _relative, resolved in references}) != len(
        references
    ):
        raise RosterSourcePresentationError(
            f"source creature media references are duplicated: {creature_name}"
        )
    return tuple(references)


def _media_artifact(
    connection: sqlite3.Connection,
    *,
    kind: str,
    resolved_reference: str,
    library_asset_root: Path | None,
) -> tuple[SemanticAssetArtifact, str]:
    row = connection.execute(
        "SELECT content_type, body, size FROM binary_assets "
        "WHERE kind = ? AND asset_key = ?",
        (kind, resolved_reference),
    ).fetchone()
    provenance = "ttrpg-cache"
    if row is not None and type(row[1]) is bytes:
        content_type, body, size = str(row[0]), row[1], int(row[2])
        if len(body) != size:
            raise RosterSourcePresentationError(
                f"cached media size disagrees: {resolved_reference}"
            )
    else:
        if library_asset_root is None:
            raise RosterSourcePresentationError(
                f"source media is absent from cache: {kind}/{resolved_reference}"
            )
        path = library_asset_root / ("icons" if kind == "icon" else "images")
        path = path.joinpath(*resolved_reference.split("/")).with_suffix(".webp")
        try:
            body = path.read_bytes()
        except OSError as exc:
            raise RosterSourcePresentationError(
                f"source media is unavailable: {kind}/{resolved_reference}"
            ) from exc
        content_type = "image/webp"
        provenance = "library-local-authoritative-assets"
    artifact = _artifact(
        _content_asset_id("source-media", f"{kind}/{resolved_reference}", body),
        content_type,
        body,
    )
    return artifact, provenance


def build_roster_source_presentations(
    *,
    cache_path: Path,
    targets: Iterable[tuple[str, str, str]],
    library_asset_root: Path | None,
) -> tuple[
    dict[str, RosterSourcePresentation],
    tuple[SemanticAssetArtifact, ...],
    dict[str, object],
]:
    """Build exact source-node packets and complete local presentation assets."""

    target_rows = tuple(targets)
    if len(target_rows) != 94 or len({row[0] for row in target_rows}) != 94:
        raise RosterSourcePresentationError("source presentation target census changed")
    uri = f"file:{cache_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        metadata = _exact_metadata(connection)
        _presentation_manifest_ref, shared_artifacts, presentation = (
            _presentation_artifacts(connection)
        )
        artifacts_by_ref = {
            artifact.asset_ref: artifact for artifact in shared_artifacts
        }
        publications: dict[str, RosterSourcePresentation] = {}
        media_provenance: dict[str, int] = {}
        for entity_id, creature_name, locator in target_rows:
            packet = source_node_packet(
                connection,
                "core-mc1",
                locator,
                locator,
            )
            packet_body = _canonical_json(packet)
            packet_artifact = _artifact(
                _content_asset_id("source-node-packet", entity_id, packet_body),
                "application/json",
                packet_body,
            )
            artifacts_by_ref.setdefault(packet_artifact.asset_ref, packet_artifact)
            media_bindings: list[dict[str, object]] = []
            media_refs: list[AssetRef] = []
            for kind, raw_reference, resolved_reference in _selected_media_references(
                packet, creature_name
            ):
                media_artifact, provenance = _media_artifact(
                    connection,
                    kind=kind,
                    resolved_reference=resolved_reference,
                    library_asset_root=library_asset_root,
                )
                artifacts_by_ref.setdefault(media_artifact.asset_ref, media_artifact)
                media_refs.append(media_artifact.asset_ref)
                media_provenance[provenance] = media_provenance.get(provenance, 0) + 1
                media_bindings.append(
                    {
                        "kind": kind,
                        "reference": resolved_reference,
                        "sourceRelativeReference": raw_reference,
                        "assetRef": media_artifact.asset_ref.to_dict(),
                    }
                )
            selected = packet["target"]["selected"]  # type: ignore[index]
            closure = {
                "schema": SOURCE_NODE_VIEW_SCHEMA,
                "kind": SOURCE_NODE_CLOSURE_KIND,
                "packet": packet_artifact.asset_ref.to_dict(),
                "source": {
                    "dataset": packet["dataset"],
                    "ruleset": "pf2er",
                    "sourceId": selected["source_id"],
                    "locator": selected["locator"],
                    "contentPath": selected["content_path"],
                    "sourceGeneration": metadata["source_generation"],
                },
                "presentation": presentation,
                "mediaBindings": media_bindings,
                "unavailableMediaReferences": [],
            }
            closure_body = _canonical_json(closure)
            closure_artifact = _artifact(
                _content_asset_id("source-node-closure", entity_id, closure_body),
                "application/json",
                closure_body,
            )
            artifacts_by_ref.setdefault(closure_artifact.asset_ref, closure_artifact)
            refs = tuple(
                sorted(
                    {
                        *(artifact.asset_ref for artifact in shared_artifacts),
                        packet_artifact.asset_ref,
                        closure_artifact.asset_ref,
                        *media_refs,
                    }
                )
            )
            publications[entity_id] = RosterSourcePresentation(
                envelope={
                    "schema": SOURCE_NODE_VIEW_SCHEMA,
                    "packetAssetId": packet_artifact.asset_ref.asset_id,
                    "closureManifestAssetId": closure_artifact.asset_ref.asset_id,
                },
                asset_refs=refs,
                packet_ref=packet_artifact.asset_ref,
                closure_manifest_ref=closure_artifact.asset_ref,
            )
    finally:
        connection.close()
    artifacts = tuple(sorted(artifacts_by_ref.values(), key=lambda item: item.asset_ref))
    audit = {
        "schema": 1,
        "kind": "pf2er-roster-source-presentation-audit",
        "sourceGeneration": metadata["source_generation"],
        "targetCount": len(publications),
        "packetCount": len(publications),
        "closureManifestCount": len(publications),
        "presentationAssetCount": len(shared_artifacts),
        "mediaAssetCount": len(artifacts) - len(shared_artifacts) - 2 * len(publications),
        "totalAssetCount": len(artifacts),
        "totalAssetBytes": sum(item.size for item in artifacts),
        "mediaReferenceProvenance": dict(sorted(media_provenance.items())),
        "unavailableMediaReferences": [],
    }
    return publications, artifacts, audit


__all__ = [
    "RosterSourcePresentation",
    "RosterSourcePresentationError",
    "SOURCE_NODE_CLOSURE_KIND",
    "SOURCE_NODE_VIEW_SCHEMA",
    "build_roster_source_presentations",
]

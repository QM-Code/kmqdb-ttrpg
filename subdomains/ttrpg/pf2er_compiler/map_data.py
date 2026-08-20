"""Canonical data-first tactical-map documents.

The source document is deliberately small and explicit.  Agents may use any
private conveniences they like while authoring a map, but persisted map data
contains only unit grid cells and unit grid edges.  This module validates and
normalizes that source into the immutable topology consumed by later engine
and presentation integrations.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from .errors import EngineInputError


MAP_DOCUMENT_KIND = "ttrpg-map"
MAP_DOCUMENT_SCHEMA = 1
MAP_TOPOLOGY_KIND = "ttrpg-map-topology"
MAP_TOPOLOGY_SCHEMA = 1
MAP_THEME_KIND = "ttrpg-map-theme"
MAP_THEME_SCHEMA = 1
RUNTIME_MAP_KIND = "ttrpg-runtime-map"
RUNTIME_MAP_SCHEMA = 1
MAX_GRID_AXIS = 200
MAX_FEATURES = 2_000
MAX_TEXT_LENGTH = 160
MAP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
FEATURE_CATEGORIES = frozenset({"barrier", "portal", "solid"})
FEATURE_RULE_PROFILES = frozenset(
    {
        "fixed-blocker",
        "fixed-barrier",
        "openable-barrier",
    }
)
FEATURE_CONTRACTS = frozenset(
    {
        ("solid", "fixed-blocker", "cell-set"),
        ("barrier", "fixed-barrier", "edge-set"),
        ("portal", "openable-barrier", "edge"),
    }
)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EngineInputError(f"{label} must be an object")
    return value


def _exact_fields(
    value: dict[str, Any],
    label: str,
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> None:
    required_fields = set(required)
    allowed_fields = required_fields | set(optional)
    missing = sorted(required_fields - set(value))
    extra = sorted(set(value) - allowed_fields)
    if missing:
        raise EngineInputError(
            f"{label} is missing required fields: {', '.join(missing)}"
        )
    if extra:
        raise EngineInputError(
            f"{label} contains unsupported fields: {', '.join(extra)}"
        )


def _integer(
    value: Any,
    label: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineInputError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise EngineInputError(
            f"{label} must be between {minimum} and {maximum}"
        )
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not MAP_ID_RE.fullmatch(value):
        raise EngineInputError(
            f"{label} must match {MAP_ID_RE.pattern}"
        )
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise EngineInputError(f"{label} must be text")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > MAX_TEXT_LENGTH:
        raise EngineInputError(
            f"{label} must contain 1 to {MAX_TEXT_LENGTH} characters"
        )
    return normalized


def _normalize_grid(value: Any) -> dict[str, Any]:
    grid = _object(value, "map.grid")
    _exact_fields(
        grid,
        "map.grid",
        required=("type", "width", "height", "cellSizeFeet"),
    )
    if grid["type"] != "square":
        raise EngineInputError("map.grid.type must be square")
    if grid["cellSizeFeet"] != 5:
        raise EngineInputError("map.grid.cellSizeFeet must be 5")
    return {
        "type": "square",
        "width": _integer(
            grid["width"],
            "map.grid.width",
            minimum=1,
            maximum=MAX_GRID_AXIS,
        ),
        "height": _integer(
            grid["height"],
            "map.grid.height",
            minimum=1,
            maximum=MAX_GRID_AXIS,
        ),
        "cellSizeFeet": 5,
    }


def _normalize_cell(
    value: Any,
    label: str,
    grid: dict[str, Any],
) -> dict[str, int]:
    cell = _object(value, label)
    _exact_fields(cell, label, required=("x", "y"))
    return {
        "x": _integer(
            cell["x"],
            f"{label}.x",
            minimum=0,
            maximum=grid["width"] - 1,
        ),
        "y": _integer(
            cell["y"],
            f"{label}.y",
            minimum=0,
            maximum=grid["height"] - 1,
        ),
    }


def _normalize_vertex(
    value: Any,
    label: str,
    grid: dict[str, Any],
) -> dict[str, int]:
    vertex = _object(value, label)
    _exact_fields(vertex, label, required=("x", "y"))
    return {
        "x": _integer(
            vertex["x"],
            f"{label}.x",
            minimum=0,
            maximum=grid["width"],
        ),
        "y": _integer(
            vertex["y"],
            f"{label}.y",
            minimum=0,
            maximum=grid["height"],
        ),
    }


def _vertex_key(vertex: dict[str, int]) -> tuple[int, int]:
    return vertex["x"], vertex["y"]


def _edge_key(edge: dict[str, Any]) -> tuple[int, int, int, int]:
    first = edge["from"]
    second = edge["to"]
    return first["x"], first["y"], second["x"], second["y"]


def _normalize_edge(
    value: Any,
    label: str,
    grid: dict[str, Any],
) -> dict[str, dict[str, int]]:
    edge = _object(value, label)
    _exact_fields(edge, label, required=("from", "to"))
    first = _normalize_vertex(edge["from"], f"{label}.from", grid)
    second = _normalize_vertex(edge["to"], f"{label}.to", grid)
    delta_x = abs(first["x"] - second["x"])
    delta_y = abs(first["y"] - second["y"])
    if delta_x + delta_y != 1:
        raise EngineInputError(
            f"{label} must connect two cardinally adjacent grid vertices"
        )
    if (_vertex_key(second)[1], _vertex_key(second)[0]) < (
        _vertex_key(first)[1],
        _vertex_key(first)[0],
    ):
        first, second = second, first
    return {"from": first, "to": second}


def _adjacent_edge_cells(
    edge: dict[str, dict[str, int]],
) -> tuple[tuple[int, int], tuple[int, int]]:
    first = edge["from"]
    second = edge["to"]
    if first["x"] == second["x"]:
        x = first["x"]
        y = min(first["y"], second["y"])
        return (x - 1, y), (x, y)
    x = min(first["x"], second["x"])
    y = first["y"]
    return (x, y - 1), (x, y)


def _normalize_solid_geometry(
    value: Any,
    label: str,
    grid: dict[str, Any],
) -> dict[str, Any]:
    geometry = _object(value, label)
    _exact_fields(geometry, label, required=("type", "cells"))
    if geometry["type"] != "cell-set":
        raise EngineInputError(f"{label}.type must be cell-set")
    raw_cells = geometry["cells"]
    if not isinstance(raw_cells, list) or not raw_cells:
        raise EngineInputError(f"{label}.cells must be a non-empty array")
    cells = [
        _normalize_cell(raw, f"{label}.cells[{index}]", grid)
        for index, raw in enumerate(raw_cells)
    ]
    keys = [(cell["x"], cell["y"]) for cell in cells]
    if len(keys) != len(set(keys)):
        raise EngineInputError(f"{label}.cells contains a duplicate cell")
    return {
        "type": "cell-set",
        "cells": sorted(cells, key=lambda item: (item["y"], item["x"])),
    }


def _normalize_barrier_geometry(
    value: Any,
    label: str,
    grid: dict[str, Any],
) -> dict[str, Any]:
    geometry = _object(value, label)
    _exact_fields(geometry, label, required=("type", "edges"))
    if geometry["type"] != "edge-set":
        raise EngineInputError(f"{label}.type must be edge-set")
    raw_edges = geometry["edges"]
    if not isinstance(raw_edges, list) or not raw_edges:
        raise EngineInputError(f"{label}.edges must be a non-empty array")
    edges = [
        _normalize_edge(raw, f"{label}.edges[{index}]", grid)
        for index, raw in enumerate(raw_edges)
    ]
    keys = [_edge_key(edge) for edge in edges]
    if len(keys) != len(set(keys)):
        raise EngineInputError(f"{label}.edges contains a duplicate edge")
    return {
        "type": "edge-set",
        "edges": sorted(edges, key=_edge_key),
    }


def _normalize_portal_geometry(
    value: Any,
    label: str,
    grid: dict[str, Any],
) -> dict[str, Any]:
    geometry = _object(value, label)
    _exact_fields(geometry, label, required=("type", "edge"))
    if geometry["type"] != "edge":
        raise EngineInputError(f"{label}.type must be edge")
    return {
        "type": "edge",
        "edge": _normalize_edge(geometry["edge"], f"{label}.edge", grid),
    }


def _normalize_feature_rules(value: Any, label: str) -> dict[str, str]:
    rules = _object(value, label)
    _exact_fields(rules, label, required=("profile",))
    profile = rules["profile"]
    if (
        not isinstance(profile, str)
        or profile not in FEATURE_RULE_PROFILES
    ):
        raise EngineInputError(
            f"{label}.profile must be one of: "
            + ", ".join(sorted(FEATURE_RULE_PROFILES))
        )
    return {"profile": profile}


def _normalize_feature_category(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or value not in FEATURE_CATEGORIES
    ):
        raise EngineInputError(
            f"{label} must be one of: "
            + ", ".join(sorted(FEATURE_CATEGORIES))
        )
    return value


def _normalize_initial_state(value: Any, label: str) -> dict[str, str]:
    state = _object(value, label)
    _exact_fields(state, label, required=("mode",))
    if state["mode"] not in {"open", "closed"}:
        raise EngineInputError(f"{label}.mode must be open or closed")
    return {"mode": state["mode"]}


def normalize_map_document(value: Any) -> dict[str, Any]:
    """Validate and deterministically normalize one authored map document."""

    document = _object(value, "map")
    _exact_fields(
        document,
        "map",
        required=(
            "schema",
            "kind",
            "id",
            "name",
            "grid",
            "features",
        ),
    )
    if document["schema"] != MAP_DOCUMENT_SCHEMA:
        raise EngineInputError(
            f"map.schema must be {MAP_DOCUMENT_SCHEMA}"
        )
    if document["kind"] != MAP_DOCUMENT_KIND:
        raise EngineInputError(f"map.kind must be {MAP_DOCUMENT_KIND}")
    grid = _normalize_grid(document["grid"])
    raw_features = document["features"]
    if (
        not isinstance(raw_features, list)
        or len(raw_features) > MAX_FEATURES
    ):
        raise EngineInputError(
            f"map.features must be an array with at most {MAX_FEATURES} entries"
        )

    features = []
    feature_ids: set[str] = set()
    claimed_cells: dict[tuple[int, int], str] = {}
    claimed_edges: dict[tuple[int, int, int, int], str] = {}
    for index, raw in enumerate(raw_features):
        label = f"map.features[{index}]"
        feature = _object(raw, label)
        _exact_fields(
            feature,
            label,
            required=("id", "category", "geometry", "rules"),
            optional=("initialState",),
        )
        feature_id = _identifier(feature["id"], f"{label}.id")
        if feature_id in feature_ids:
            raise EngineInputError(
                f"map feature id is duplicated: {feature_id}"
            )
        feature_ids.add(feature_id)
        category = _normalize_feature_category(
            feature["category"],
            f"{label}.category",
        )
        rules = _normalize_feature_rules(
            feature["rules"],
            f"{label}.rules",
        )
        profile = rules["profile"]
        raw_geometry = _object(feature["geometry"], f"{label}.geometry")
        geometry_type = raw_geometry.get("type")
        if (
            not isinstance(geometry_type, str)
            or (category, profile, geometry_type) not in FEATURE_CONTRACTS
        ):
            raise EngineInputError(
                f"{label} has unsupported category/profile/geometry: "
                f"{category}/{profile}/{geometry_type}"
            )
        if category == "portal" and "initialState" not in feature:
            raise EngineInputError(
                f"{label} is missing required fields: initialState"
            )
        if category != "portal" and "initialState" in feature:
            raise EngineInputError(
                f"{label}.initialState is only valid for portal features"
            )

        if category == "solid":
            geometry = _normalize_solid_geometry(
                feature["geometry"],
                f"{label}.geometry",
                grid,
            )
            for cell in geometry["cells"]:
                key = (cell["x"], cell["y"])
                if key in claimed_cells:
                    raise EngineInputError(
                        f"blocked cell {cell} is claimed by both "
                        f"{claimed_cells[key]} and {feature_id}"
                    )
                claimed_cells[key] = feature_id
            normalized = {
                "id": feature_id,
                "category": category,
                "geometry": geometry,
                "rules": rules,
            }
        elif category == "barrier":
            geometry = _normalize_barrier_geometry(
                feature["geometry"],
                f"{label}.geometry",
                grid,
            )
            normalized = {
                "id": feature_id,
                "category": category,
                "geometry": geometry,
                "rules": rules,
            }
        elif category == "portal":
            geometry = _normalize_portal_geometry(
                feature["geometry"],
                f"{label}.geometry",
                grid,
            )
            normalized = {
                "id": feature_id,
                "category": category,
                "geometry": geometry,
                "rules": rules,
                "initialState": _normalize_initial_state(
                    feature["initialState"],
                    f"{label}.initialState",
                ),
            }
        else:
            raise AssertionError("validated map feature category is unhandled")

        if category in {"barrier", "portal"}:
            edges = (
                normalized["geometry"]["edges"]
                if category == "barrier"
                else [normalized["geometry"]["edge"]]
            )
            for edge in edges:
                key = _edge_key(edge)
                if key in claimed_edges:
                    raise EngineInputError(
                        f"barrier edge {edge} is claimed by both "
                        f"{claimed_edges[key]} and {feature_id}"
                    )
                claimed_edges[key] = feature_id
        features.append(normalized)

    for feature in features:
        if feature["category"] != "portal":
            continue
        adjacent_cells = _adjacent_edge_cells(
            feature["geometry"]["edge"]
        )
        if any(
            x < 0
            or x >= grid["width"]
            or y < 0
            or y >= grid["height"]
            for x, y in adjacent_cells
        ):
            raise EngineInputError(
                f"portal {feature['id']} must separate two in-bounds cells"
            )
        for cell in adjacent_cells:
            if cell in claimed_cells:
                raise EngineInputError(
                    f"portal {feature['id']} borders solid cell "
                    f"{{'x': {cell[0]}, 'y': {cell[1]}}} claimed by "
                    f"{claimed_cells[cell]}"
                )

    return {
        "schema": MAP_DOCUMENT_SCHEMA,
        "kind": MAP_DOCUMENT_KIND,
        "id": _identifier(document["id"], "map.id"),
        "name": _text(document["name"], "map.name"),
        "grid": grid,
        "features": sorted(features, key=lambda item: item["id"]),
    }


def map_document_digest(value: Any) -> str:
    normalized = normalize_map_document(value)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compile_map_document(value: Any) -> dict[str, Any]:
    """Compile authored features into a stable topology projection."""

    normalized = normalize_map_document(value)
    solids = []
    barriers = []
    portals = []
    for feature in normalized["features"]:
        category = feature["category"]
        profile = feature["rules"]["profile"]
        if category == "solid":
            solids.append(
                {
                    "id": feature["id"],
                    "category": category,
                    "ruleProfile": profile,
                    "cells": feature["geometry"]["cells"],
                }
            )
        elif category == "barrier":
            barriers.append(
                {
                    "id": feature["id"],
                    "category": category,
                    "ruleProfile": profile,
                    "edges": feature["geometry"]["edges"],
                }
            )
        else:
            portals.append(
                {
                    "id": feature["id"],
                    "category": category,
                    "ruleProfile": profile,
                    "edge": feature["geometry"]["edge"],
                    "initialState": feature["initialState"],
                }
            )
    return {
        "schema": MAP_TOPOLOGY_SCHEMA,
        "kind": MAP_TOPOLOGY_KIND,
        "id": normalized["id"],
        "name": normalized["name"],
        "definitionDigest": map_document_digest(normalized),
        "grid": normalized["grid"],
        "solids": solids,
        "barriers": barriers,
        "portals": portals,
    }


def _color(value: Any, label: str) -> str:
    if not isinstance(value, str) or not COLOR_RE.fullmatch(value):
        raise EngineInputError(
            f"{label} must be a six- or eight-digit hexadecimal color"
        )
    return value.lower()


def normalize_map_theme(value: Any) -> dict[str, Any]:
    """Validate one reusable presentation theme independently of topology."""

    document = _object(value, "map theme")
    _exact_fields(
        document,
        "map theme",
        required=("schema", "kind", "id", "name", "tokens"),
    )
    if document["schema"] != MAP_THEME_SCHEMA:
        raise EngineInputError(
            f"map theme.schema must be {MAP_THEME_SCHEMA}"
        )
    if document["kind"] != MAP_THEME_KIND:
        raise EngineInputError(
            f"map theme.kind must be {MAP_THEME_KIND}"
        )
    tokens = _object(document["tokens"], "map theme.tokens")
    _exact_fields(
        tokens,
        "map theme.tokens",
        required=(
            "floorFill",
            "solidFill",
            "barrierStroke",
            "portalStroke",
            "gridStroke",
            "barrierWidthPercent",
            "portalWidthPercent",
        ),
    )
    return {
        "schema": MAP_THEME_SCHEMA,
        "kind": MAP_THEME_KIND,
        "id": _identifier(document["id"], "map theme.id"),
        "name": _text(document["name"], "map theme.name"),
        "tokens": {
            "floorFill": _color(
                tokens["floorFill"],
                "map theme.tokens.floorFill",
            ),
            "solidFill": _color(
                tokens["solidFill"],
                "map theme.tokens.solidFill",
            ),
            "barrierStroke": _color(
                tokens["barrierStroke"],
                "map theme.tokens.barrierStroke",
            ),
            "portalStroke": _color(
                tokens["portalStroke"],
                "map theme.tokens.portalStroke",
            ),
            "gridStroke": _color(
                tokens["gridStroke"],
                "map theme.tokens.gridStroke",
            ),
            "barrierWidthPercent": _integer(
                tokens["barrierWidthPercent"],
                "map theme.tokens.barrierWidthPercent",
                minimum=1,
                maximum=50,
            ),
            "portalWidthPercent": _integer(
                tokens["portalWidthPercent"],
                "map theme.tokens.portalWidthPercent",
                minimum=1,
                maximum=50,
            ),
        },
    }


def map_theme_digest(value: Any) -> str:
    normalized = normalize_map_theme(value)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
        raise EngineInputError(
            f"{label} must be a lowercase SHA-256 hexadecimal digest"
        )
    return value


def _topology_members(topology: Any) -> dict[str, list[Any]]:
    value = _object(topology, "map topology")
    members = {}
    for name in ("solids", "barriers", "portals"):
        member = value.get(name)
        if not isinstance(member, list):
            raise EngineInputError(f"map topology.{name} must be an array")
        members[name] = member
    return members


def _initial_portal_states(
    topology: Any,
) -> dict[str, str]:
    members = _topology_members(topology)
    result: dict[str, str] = {}
    for index, portal in enumerate(members["portals"]):
        label = f"map topology.portals[{index}]"
        item = _object(portal, label)
        portal_id = _identifier(item.get("id"), f"{label}.id")
        if portal_id in result:
            raise EngineInputError("map topology portal ids must be unique")
        initial_state = _normalize_initial_state(
            item.get("initialState"),
            f"{label}.initialState",
        )
        result[portal_id] = initial_state["mode"]
    return {portal_id: result[portal_id] for portal_id in sorted(result)}


def normalize_portal_states(
    value: Any,
    topology: Any,
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise EngineInputError("portal states must be an object")
    result: dict[str, str] = {}
    for raw_portal_id, mode in value.items():
        portal_id = _identifier(raw_portal_id, "portal state portalId")
        if mode not in {"open", "closed"}:
            raise EngineInputError(
                f"portal state {portal_id} must be open or closed"
            )
        result[portal_id] = mode
    expected_ids = set(_initial_portal_states(topology))
    if set(result) != expected_ids:
        raise EngineInputError(
            "portal states must contain exactly the topology portal ids"
        )
    return {portal_id: result[portal_id] for portal_id in sorted(result)}


def normalize_runtime_map(value: Any) -> dict[str, Any]:
    """Validate and normalize one composed map projected into runtime state."""

    runtime = _object(value, "runtime map")
    _exact_fields(
        runtime,
        "runtime map",
        required=(
            "schema",
            "kind",
            "id",
            "name",
            "grid",
            "topologyDefinitionDigest",
            "themeDigest",
            "topology",
            "portalStates",
            "theme",
        ),
    )
    if runtime["schema"] != RUNTIME_MAP_SCHEMA:
        raise EngineInputError(
            f"runtime map.schema must be {RUNTIME_MAP_SCHEMA}"
        )
    if runtime["kind"] != RUNTIME_MAP_KIND:
        raise EngineInputError(
            f"runtime map.kind must be {RUNTIME_MAP_KIND}"
        )

    topology = _object(runtime["topology"], "runtime map.topology")
    _exact_fields(
        topology,
        "runtime map.topology",
        required=("solids", "barriers", "portals"),
    )
    members = _topology_members(topology)
    features = []
    for index, raw_solid in enumerate(members["solids"]):
        label = f"runtime map.topology.solids[{index}]"
        solid = _object(raw_solid, label)
        _exact_fields(
            solid,
            label,
            required=("id", "category", "ruleProfile", "cells"),
        )
        features.append(
            {
                "id": solid["id"],
                "category": solid["category"],
                "geometry": {
                    "type": "cell-set",
                    "cells": solid["cells"],
                },
                "rules": {"profile": solid["ruleProfile"]},
            }
        )
    for index, raw_barrier in enumerate(members["barriers"]):
        label = f"runtime map.topology.barriers[{index}]"
        barrier = _object(raw_barrier, label)
        _exact_fields(
            barrier,
            label,
            required=("id", "category", "ruleProfile", "edges"),
        )
        features.append(
            {
                "id": barrier["id"],
                "category": barrier["category"],
                "geometry": {
                    "type": "edge-set",
                    "edges": barrier["edges"],
                },
                "rules": {"profile": barrier["ruleProfile"]},
            }
        )
    for index, raw_portal in enumerate(members["portals"]):
        label = f"runtime map.topology.portals[{index}]"
        portal = _object(raw_portal, label)
        _exact_fields(
            portal,
            label,
            required=(
                "id",
                "category",
                "ruleProfile",
                "edge",
                "initialState",
            ),
        )
        features.append(
            {
                "id": portal["id"],
                "category": portal["category"],
                "geometry": {
                    "type": "edge",
                    "edge": portal["edge"],
                },
                "rules": {"profile": portal["ruleProfile"]},
                "initialState": portal["initialState"],
            }
        )

    compiled = compile_map_document(
        {
            "schema": MAP_DOCUMENT_SCHEMA,
            "kind": MAP_DOCUMENT_KIND,
            "id": runtime["id"],
            "name": runtime["name"],
            "grid": runtime["grid"],
            "features": features,
        }
    )
    topology_digest = _digest(
        runtime["topologyDefinitionDigest"],
        "runtime map.topologyDefinitionDigest",
    )
    if topology_digest != compiled["definitionDigest"]:
        raise EngineInputError(
            "runtime map.topologyDefinitionDigest does not match topology"
        )

    theme = normalize_map_theme(runtime["theme"])
    expected_theme_digest = map_theme_digest(theme)
    theme_digest = _digest(
        runtime["themeDigest"],
        "runtime map.themeDigest",
    )
    if theme_digest != expected_theme_digest:
        raise EngineInputError(
            "runtime map.themeDigest does not match theme"
        )

    return {
        "schema": RUNTIME_MAP_SCHEMA,
        "kind": RUNTIME_MAP_KIND,
        "id": compiled["id"],
        "name": compiled["name"],
        "grid": compiled["grid"],
        "topologyDefinitionDigest": topology_digest,
        "themeDigest": theme_digest,
        "topology": {
            "solids": compiled["solids"],
            "barriers": compiled["barriers"],
            "portals": compiled["portals"],
        },
        "portalStates": normalize_portal_states(
            runtime["portalStates"],
            compiled,
        ),
        "theme": theme,
    }


def compose_runtime_map(value: Any) -> dict[str, Any]:
    """Compose one abstract definition and one independent presentation theme."""

    composition = _object(value, "map composition")
    _exact_fields(
        composition,
        "map composition",
        required=("definition", "theme"),
    )
    topology = compile_map_document(composition["definition"])
    theme = normalize_map_theme(composition["theme"])
    return normalize_runtime_map(
        {
            "schema": RUNTIME_MAP_SCHEMA,
            "kind": RUNTIME_MAP_KIND,
            "id": topology["id"],
            "name": topology["name"],
            "grid": topology["grid"],
            "topologyDefinitionDigest": topology["definitionDigest"],
            "themeDigest": map_theme_digest(theme),
            "topology": {
                "solids": topology["solids"],
                "barriers": topology["barriers"],
                "portals": topology["portals"],
            },
            "portalStates": _initial_portal_states(topology),
            "theme": theme,
        }
    )


def solid_cells(topology: Any) -> list[dict[str, int]]:
    """Return every non-occupiable cell in canonical coordinate order."""

    members = _topology_members(topology)
    cells = [
        cell
        for solid in members["solids"]
        for cell in solid.get("cells") or []
    ]
    return sorted(cells, key=lambda cell: (cell["y"], cell["x"]))


def active_barrier_edges(
    topology: Any,
    portal_states: Any | None = None,
) -> list[dict[str, dict[str, int]]]:
    """Return fixed barriers plus portal edges closed in the supplied state."""

    members = _topology_members(topology)
    states = (
        _initial_portal_states(topology)
        if portal_states is None
        else normalize_portal_states(portal_states, topology)
    )
    result = [
        edge
        for barrier in members["barriers"]
        for edge in barrier.get("edges") or []
    ]
    result.extend(
        portal["edge"]
        for portal in members["portals"]
        if states[portal["id"]] == "closed"
    )
    return sorted(result, key=_edge_key)

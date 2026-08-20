"""Minimal PF2ER square-grid battleground contracts."""

from __future__ import annotations

import hashlib
import json
import re
from itertools import combinations
from typing import Any, Callable, Mapping

from .errors import EngineInputError
from .geometry import (
    coordinate,
    coordinate_key,
    grid_distance_feet,
    square_is_inside,
    strict_integer,
)
from .equipment import (
    bind_creature_equipment,
    bind_semantic_creature_equipment,
    compile_semantic_equipment_catalog,
    initial_equipment_state,
    initial_item_instances,
    initial_semantic_equipment_state,
    initial_semantic_item_instances,
)
from .map_data import (
    active_barrier_edges,
    compose_runtime_map,
    normalize_portal_states,
    solid_cells,
)
from .mechanics import animated_construct_armor, stench


PARTICIPANT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
REQUIRED_CORE_SOURCES = frozenset({"core-gmc", "core-pc1", "core-mc1"})
MAX_GRID_AXIS = 200
MAX_PARTICIPANTS = 100
MAX_TINY_CREATURES_PER_SQUARE = 4


def square_is_within_reach(
    first: dict[str, int],
    second: dict[str, int],
    reach_feet: int,
) -> bool:
    """Apply the bounded Player Core reach exception to two grid squares."""

    delta_x = abs(first["x"] - second["x"])
    delta_y = abs(first["y"] - second["y"])
    return (
        grid_distance_feet(first, second) <= reach_feet
        or (reach_feet == 10 and delta_x == 2 and delta_y == 2)
    )


def occupied_squares(position: dict[str, int], definition: dict[str, Any]) -> list[dict[str, int]]:
    space = definition.get("space") if isinstance(definition.get("space"), dict) else {}
    width = strict_integer(space.get("widthSquares"), "creature space width", minimum=1)
    height = strict_integer(space.get("heightSquares"), "creature space height", minimum=1)
    return [
        {"x": position["x"] + offset_x, "y": position["y"] + offset_y}
        for offset_y in range(height)
        for offset_x in range(width)
    ]


def creature_tiny_flags_can_share_square(
    tiny_flags: list[bool],
) -> bool:
    """Apply the bounded Tiny-creature exception to one occupied square."""

    if (
        not isinstance(tiny_flags, list)
        or not tiny_flags
        or any(type(value) is not bool for value in tiny_flags)
    ):
        raise EngineInputError("shared-square Tiny flags are invalid")
    tiny_count = tiny_flags.count(True)
    larger_count = len(tiny_flags) - tiny_count
    return (
        tiny_count <= MAX_TINY_CREATURES_PER_SQUARE
        and larger_count <= 1
    )


def creature_is_tiny(definition: dict[str, Any]) -> bool:
    """Grant the sharing exception only to an explicitly Tiny definition."""

    if not isinstance(definition, dict):
        raise EngineInputError("creature definition is invalid")
    return definition.get("size") == "tiny"


def normalize_grid(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EngineInputError("map.grid must be an object")
    grid_type = str(value.get("type") or "square").strip().casefold()
    if grid_type != "square":
        raise EngineInputError("only a square grid is supported")
    cell_size = value.get("cellSizeFeet", 5)
    if cell_size != 5:
        raise EngineInputError("PF2ER square-grid cells must be 5 feet")
    return {
        "type": "square",
        "cellSizeFeet": 5,
        "width": strict_integer(value.get("width"), "map.grid.width", minimum=1, maximum=MAX_GRID_AXIS),
        "height": strict_integer(value.get("height"), "map.grid.height", minimum=1, maximum=MAX_GRID_AXIS),
        "origin": "northwest",
        "xAxis": "east",
        "yAxis": "south",
        "rule": {"sourceId": "core-pc1", "locator": "421.5"},
        "diagonalRule": {"sourceId": "core-pc1", "locator": "421.6", "costPatternFeet": [5, 10]},
    }


def normalize_blocked(value: Any, grid: dict[str, Any]) -> list[dict[str, int]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise EngineInputError("map.blockedSquares must be an array")
    result = []
    seen: set[tuple[int, int]] = set()
    for index, raw in enumerate(value):
        square = coordinate(raw, f"map.blockedSquares[{index}]")
        key = coordinate_key(square)
        if square["x"] >= grid["width"] or square["y"] >= grid["height"]:
            raise EngineInputError(f"blocked square is outside the map: {square}")
        if key in seen:
            raise EngineInputError(f"blocked square is duplicated: {square}")
        seen.add(key)
        result.append(square)
    return sorted(result, key=lambda item: (item["y"], item["x"]))


def normalize_visibility(
    value: Any,
    grid: dict[str, Any],
) -> dict[str, Any]:
    if value is None:
        return {"mode": "unobstructed"}
    if not isinstance(value, dict):
        raise EngineInputError("map.visibility must be an object")
    mode = str(value.get("mode") or "").casefold()
    if mode == "unobstructed":
        if set(value) != {"mode"}:
            raise EngineInputError(
                "unobstructed map.visibility contains unsupported fields"
            )
        return {"mode": "unobstructed"}
    if mode != "solid-barriers":
        raise EngineInputError(
            "map.visibility.mode must be unobstructed or solid-barriers"
        )
    if set(value) != {"mode", "opaqueSquares"}:
        raise EngineInputError(
            "solid-barriers map.visibility requires exactly mode and "
            "opaqueSquares"
        )
    raw_squares = value.get("opaqueSquares")
    if not isinstance(raw_squares, list):
        raise EngineInputError(
            "map.visibility.opaqueSquares must be an array"
        )
    opaque_squares = []
    seen: set[tuple[int, int]] = set()
    for index, raw in enumerate(raw_squares):
        square = coordinate(
            raw,
            f"map.visibility.opaqueSquares[{index}]",
        )
        key = coordinate_key(square)
        if square["x"] >= grid["width"] or square["y"] >= grid["height"]:
            raise EngineInputError(
                f"opaque square is outside the map: {square}"
            )
        if key in seen:
            raise EngineInputError(
                f"opaque square is duplicated: {square}"
            )
        seen.add(key)
        opaque_squares.append(square)
    return {
        "mode": "solid-barriers",
        "opaqueSquares": sorted(
            opaque_squares,
            key=lambda item: (item["y"], item["x"]),
        ),
        "rules": {
            "lineOfEffect": {
                "sourceId": "core-pc1",
                "locator": "426.6",
            },
            "lineOfSight": {
                "sourceId": "core-pc1",
                "locator": "427.2",
            },
        },
    }


def map_blocked_square_keys(
    map_state: Any,
) -> set[tuple[int, int]]:
    """Return non-occupiable cells from either engine map representation."""

    if not isinstance(map_state, dict):
        raise EngineInputError("encounter map must be an object")
    if map_state.get("kind") == "ttrpg-runtime-map":
        topology = map_state.get("topology")
        if not isinstance(topology, dict):
            raise EngineInputError("runtime map topology is invalid")
        try:
            return {
                (int(cell["x"]), int(cell["y"]))
                for cell in solid_cells(topology)
            }
        except (KeyError, TypeError, ValueError) as failure:
            raise EngineInputError(
                "runtime map solid cells are invalid"
            ) from failure
    if map_state.get("kind") is not None or any(
        field in map_state
        for field in (
            "topology",
            "topologyDefinitionDigest",
            "portalStates",
            "themeDigest",
            "theme",
        )
    ):
        raise EngineInputError("encounter runtime map identity is invalid")
    raw = map_state.get("blockedSquares") or []
    if not isinstance(raw, list):
        raise EngineInputError("encounter blocked squares are invalid")
    return {
        coordinate_key(square)
        for square in raw
        if isinstance(square, dict)
    }


def map_active_barrier_edge_keys(
    map_state: Any,
) -> set[tuple[int, int, int, int]]:
    """Return fixed barriers and currently closed portal edges."""

    if not isinstance(map_state, dict):
        raise EngineInputError("encounter map must be an object")
    if map_state.get("kind") != "ttrpg-runtime-map":
        if map_state.get("kind") is not None:
            raise EngineInputError("encounter runtime map identity is invalid")
        return set()
    topology = map_state.get("topology")
    portal_states = map_state.get("portalStates")
    if not isinstance(topology, dict) or not isinstance(portal_states, dict):
        raise EngineInputError("runtime map barrier state is invalid")
    result = set()
    for edge in active_barrier_edges(topology, portal_states):
        if not isinstance(edge, dict):
            raise EngineInputError("runtime map barrier edge is invalid")
        first = edge.get("from")
        second = edge.get("to")
        if not isinstance(first, dict) or not isinstance(second, dict):
            raise EngineInputError("runtime map barrier edge is invalid")
        result.add(
            (
                int(first["x"]),
                int(first["y"]),
                int(second["x"]),
                int(second["y"]),
            )
        )
    return result


def _cell_boundary_edge_key(
    first: dict[str, int],
    second: dict[str, int],
) -> tuple[int, int, int, int]:
    delta_x = int(second["x"]) - int(first["x"])
    delta_y = int(second["y"]) - int(first["y"])
    if abs(delta_x) + abs(delta_y) != 1:
        raise EngineInputError(
            "a barrier crossing check requires cardinally adjacent cells"
        )
    if delta_x:
        boundary_x = max(int(first["x"]), int(second["x"]))
        y = int(first["y"])
        return boundary_x, y, boundary_x, y + 1
    x = int(first["x"])
    boundary_y = max(int(first["y"]), int(second["y"]))
    return x, boundary_y, x + 1, boundary_y


def movement_step_crosses_active_barrier(
    map_state: Any,
    origin: dict[str, int],
    destination: dict[str, int],
    definition: dict[str, Any],
) -> bool:
    """Apply the conservative grid-edge rule to one footprint translation."""

    active_edges = map_active_barrier_edge_keys(map_state)
    if not active_edges:
        return False
    delta_x = int(destination["x"]) - int(origin["x"])
    delta_y = int(destination["y"]) - int(origin["y"])
    if max(abs(delta_x), abs(delta_y)) != 1:
        raise EngineInputError(
            "a barrier crossing check requires one adjacent movement step"
        )
    for square in occupied_squares(origin, definition):
        translated = {
            "x": int(square["x"]) + delta_x,
            "y": int(square["y"]) + delta_y,
        }
        if not delta_x or not delta_y:
            if _cell_boundary_edge_key(square, translated) in active_edges:
                return True
            continue

        horizontal = {
            "x": int(square["x"]) + delta_x,
            "y": int(square["y"]),
        }
        vertical = {
            "x": int(square["x"]),
            "y": int(square["y"]) + delta_y,
        }
        # A diagonal is clear only when both cardinal decompositions are
        # clear. This prevents squeezing around a barrier endpoint.
        if any(
            _cell_boundary_edge_key(first, second) in active_edges
            for first, second in (
                (square, horizontal),
                (horizontal, translated),
                (square, vertical),
                (vertical, translated),
            )
        ):
            return True
    return False


def footprint_straddles_active_barrier(
    map_state: Any,
    squares: list[dict[str, int]],
) -> bool:
    """Return whether one footprint occupies cells on both sides of a barrier."""

    active_edges = map_active_barrier_edge_keys(map_state)
    if not active_edges:
        return False
    occupied = {
        (int(square["x"]), int(square["y"]))
        for square in squares
    }
    for x, y in occupied:
        for neighbor in ((x + 1, y), (x, y + 1)):
            if neighbor not in occupied:
                continue
            if _cell_boundary_edge_key(
                {"x": x, "y": y},
                {"x": neighbor[0], "y": neighbor[1]},
            ) in active_edges:
                return True
    return False


def minimum_distance(first: list[dict[str, int]], second: list[dict[str, int]]) -> int:
    return min(grid_distance_feet(left, right) for left in first for right in second)


def occupied_squares_are_within_reach(
    first: list[dict[str, int]],
    second: list[dict[str, int]],
    reach_feet: int,
) -> bool:
    return any(
        square_is_within_reach(left, right, reach_feet)
        for left in first
        for right in second
    )


def map_relations(participants: list[dict[str, Any]], definitions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for first, second in combinations(participants, 2):
        distance = minimum_distance(first["occupiedSquares"], second["occupiedSquares"])
        first_definition = definitions[first["creatureId"]]
        second_definition = definitions[second["creatureId"]]
        first_reach = int(first_definition["space"]["defaultReachFeet"])
        second_reach = int(second_definition["space"]["defaultReachFeet"])
        result.append(
            {
                "participants": [first["id"], second["id"]],
                "distanceFeet": distance,
                "adjacent": distance == 5,
                "reach": {
                    first["id"]: occupied_squares_are_within_reach(
                        first["occupiedSquares"],
                        second["occupiedSquares"],
                        first_reach,
                    ),
                    second["id"]: occupied_squares_are_within_reach(
                        second["occupiedSquares"],
                        first["occupiedSquares"],
                        second_reach,
                    ),
                },
            }
        )
    return result


def selected_source_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        raise EngineInputError("rules must be an object")
    if str(payload.get("ruleset") or "") != "pf2er":
        raise EngineInputError("rules.ruleset must be pf2er")
    selected = payload.get("sources")
    if not isinstance(selected, list) or not selected or any(not isinstance(item, str) or not item for item in selected):
        raise EngineInputError("rules.sources must be a non-empty array of source ids")
    if len(selected) != len(set(selected)):
        raise EngineInputError("rules.sources contains duplicates")
    missing = sorted(REQUIRED_CORE_SOURCES - set(selected))
    if missing:
        raise EngineInputError(f"rules.sources is missing mandatory PF2ER sources: {', '.join(missing)}")
    return sorted(selected)


def validate_rules(payload: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    selected = selected_source_ids(payload)
    manifest_ids = [str(item.get("id") or "") for item in manifest.get("sources") or []]
    if selected != sorted(manifest_ids):
        raise EngineInputError("rules manifest does not match the selected sources")
    return manifest


def battleground_digest(payload: dict[str, Any]) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as failure:
        raise EngineInputError(
            "battleground is not canonical JSON"
        ) from failure
    return hashlib.sha256(encoded).hexdigest()


def _canonical_map_copy(value: Any, label: str) -> Any:
    try:
        return json.loads(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    except (TypeError, ValueError) as failure:
        raise EngineInputError(f"{label} is not canonical JSON") from failure


def immutable_map_definition(map_state: Any) -> dict[str, Any]:
    """Detach the immutable map definition from encounter portal state."""

    if not isinstance(map_state, dict):
        raise EngineInputError("encounter map must be an object")
    definition = {
        key: value
        for key, value in map_state.items()
        if key != "portalStates"
    }
    # The mechanics artifact owns this copy for its complete lifetime. Runtime
    # hydration subsequently shares it by reference.
    return _canonical_map_copy(definition, "map definition")


def mutable_map_state(map_state: Any) -> dict[str, Any]:
    """Return the only encounter-owned mutable portion of a map."""

    if not isinstance(map_state, dict):
        raise EngineInputError("encounter map must be an object")
    if map_state.get("kind") == "ttrpg-runtime-map":
        portal_states = normalize_portal_states(
            map_state.get("portalStates"),
            map_state.get("topology"),
        )
    else:
        portal_states = map_state.get("portalStates", {})
        if portal_states != {}:
            raise EngineInputError(
                "non-runtime map cannot have mutable portalStates"
            )
    return {
        "portalStates": _canonical_map_copy(
            portal_states,
            "map portalStates",
        )
    }


def hydrate_runtime_map(
    map_definition: Any,
    map_state: Any,
) -> dict[str, Any]:
    """Rebuild one runtime map without copying its immutable substructure."""

    if not isinstance(map_definition, dict):
        raise EngineInputError("mechanics mapDefinition is invalid")
    if (
        not isinstance(map_state, dict)
        or set(map_state) != {"portalStates"}
        or not isinstance(map_state.get("portalStates"), dict)
    ):
        raise EngineInputError("encounter mapState is invalid")
    if "portalStates" in map_definition:
        raise EngineInputError(
            "mechanics mapDefinition contains mutable portalStates"
        )
    result = dict(map_definition)
    if map_definition.get("kind") == "ttrpg-runtime-map":
        portal_states = normalize_portal_states(
            map_state["portalStates"],
            map_definition.get("topology"),
        )
        result["portalStates"] = _canonical_map_copy(
            portal_states,
            "map portalStates",
        )
    elif map_state["portalStates"]:
        raise EngineInputError(
            "non-runtime map cannot have mutable portalStates"
        )
    return result


OLFACTORY_AURA_ELIGIBILITY = stench.OLFACTORY_AURA_ELIGIBILITY


def normalize_olfactory_aura_adjudications(
    payload: Any,
    *,
    participants: list[dict[str, Any]],
    definitions: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, str]]] | None:
    """Transitional direct facade over the selected Stench algorithm."""

    return stench.normalize_adjudications(
        payload,
        participants=participants,
        definitions=definitions,
    )


def normalize_scarecrow_leer_adjudications(
    payload: Any,
    *,
    participants: list[dict[str, Any]],
    definitions: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, str]]] | None:
    """Validate the host's complete private Leer avian classification."""

    expected = []
    for source in participants:
        definition = definitions[source["creatureId"]]
        for ability in definition.get("abilities") or []:
            if (
                ability.get("supported") is not True
                or ability.get("mechanic", {}).get("type")
                != "scarecrow-leer"
            ):
                continue
            for target in participants:
                if target["id"] != source["id"]:
                    expected.append(
                        (
                            str(source["id"]),
                            str(ability["id"]),
                            str(target["id"]),
                        )
                    )
    if not expected and payload is None:
        return None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"scarecrowLeerTargets"}
        or not isinstance(payload.get("scarecrowLeerTargets"), list)
    ):
        raise EngineInputError(
            "Leer adjudications must contain exactly scarecrowLeerTargets"
        )
    leer_rows: dict[tuple[str, str, str], dict[str, str]] = {}
    for index, row in enumerate(payload["scarecrowLeerTargets"]):
        if (
            not isinstance(row, dict)
            or set(row) != {
                "sourceParticipantId", "abilityId",
                "targetParticipantId", "classification",
            }
            or any(
                type(row.get(field)) is not str or not row[field]
                for field in (
                    "sourceParticipantId", "abilityId",
                    "targetParticipantId",
                )
            )
            or row.get("classification") not in {"avian", "non-avian"}
        ):
            raise EngineInputError(
                f"adjudications.scarecrowLeerTargets[{index}] is invalid"
            )
        key = (
            row["sourceParticipantId"], row["abilityId"],
            row["targetParticipantId"],
        )
        if key in leer_rows:
            raise EngineInputError(
                "adjudications.scarecrowLeerTargets contains a duplicate row"
            )
        leer_rows[key] = {
            "sourceParticipantId": key[0], "abilityId": key[1],
            "targetParticipantId": key[2],
            "classification": row["classification"],
        }
    if set(leer_rows) != set(expected):
        raise EngineInputError(
            "adjudications.scarecrowLeerTargets must be the complete "
            "Leer source-by-target matrix"
        )
    return {"scarecrowLeerTargets": [leer_rows[key] for key in expected]}


def normalize_ghoul_corpse_adjudications(
    payload: Any,
    *,
    participants: list[dict[str, Any]],
    definitions: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, str]]] | None:
    """Validate whether each combatant's defeat is lethal or recoverable."""

    has_consumer = any(
        ability.get("supported") is True
        and ability.get("mechanic", {}).get("type")
        == "ghoul-consume-flesh"
        for participant in participants
        for ability in definitions[participant["creatureId"]].get(
            "abilities"
        ) or []
    )
    expected = [str(participant["id"]) for participant in participants]
    if not has_consumer and payload is None:
        return None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"ghoulCorpseTargets"}
        or not isinstance(payload.get("ghoulCorpseTargets"), list)
    ):
        raise EngineInputError(
            "Ghoul adjudications must contain exactly ghoulCorpseTargets"
        )
    rows: dict[str, dict[str, str]] = {}
    for index, row in enumerate(payload["ghoulCorpseTargets"]):
        if (
            not isinstance(row, dict)
            or set(row) != {"targetParticipantId", "defeatDisposition"}
            or type(row.get("targetParticipantId")) is not str
            or not row["targetParticipantId"]
            or row.get("defeatDisposition")
            not in {"corpse-on-defeat", "recoverable-on-defeat"}
        ):
            raise EngineInputError(
                f"adjudications.ghoulCorpseTargets[{index}] is invalid"
            )
        target_id = row["targetParticipantId"]
        if target_id in rows:
            raise EngineInputError(
                "adjudications.ghoulCorpseTargets contains a duplicate row"
            )
        rows[target_id] = {
            "targetParticipantId": target_id,
            "defeatDisposition": row["defeatDisposition"],
        }
    if set(rows) != set(expected):
        raise EngineInputError(
            "adjudications.ghoulCorpseTargets must classify every participant"
        )
    return {"ghoulCorpseTargets": [rows[target_id] for target_id in expected]}


def _assemble_battleground(
    payload: Any,
    *,
    rules: dict[str, Any],
    creature_reference_id: Callable[[dict[str, Any], str], str],
    creature_loader: Callable[[str], dict[str, Any]],
    equipment_loader: Callable[[set[str]], dict[str, Any]] | None = None,
    semantic_item_definitions: dict[str, dict[str, Any]] | None = None,
    rules_receipt: dict[str, Any] | None = None,
    adjudication_normalizers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    # Light production is encounter-owned rules state, not schema-1 map
    # topology. Import locally because illumination reuses this module's
    # canonical coordinate and distance validators.
    from .illumination import (
        normalize_light_production,
        refresh_state_illumination,
    )

    if not isinstance(payload, dict):
        raise EngineInputError("request body must be an object")
    map_input = payload.get("map")
    if not isinstance(map_input, dict):
        raise EngineInputError("map must be an object")
    canonical_map = "definition" in map_input or "theme" in map_input
    if canonical_map:
        if set(map_input) != {"definition", "theme"}:
            raise EngineInputError(
                "canonical map composition requires exactly definition and theme"
            )
        normalized_map = compose_runtime_map(map_input)
        grid = normalized_map["grid"]
    else:
        grid = normalize_grid(map_input.get("grid"))
        blocked = normalize_blocked(map_input.get("blockedSquares"), grid)
        visibility = normalize_visibility(
            map_input.get("visibility"),
            grid,
        )
        normalized_map = {
            "id": str(map_input.get("id") or "battleground").strip()
            or "battleground",
            "grid": grid,
            "blockedSquares": blocked,
            "visibility": visibility,
        }
    blocked_keys = map_blocked_square_keys(normalized_map)
    light_production = normalize_light_production(
        payload.get("lighting"),
        grid,
    )

    raw_participants = payload.get("participants")
    if not isinstance(raw_participants, list) or len(raw_participants) < 2:
        raise EngineInputError("participants must contain at least two entries")
    if len(raw_participants) > MAX_PARTICIPANTS:
        raise EngineInputError(f"participants must contain at most {MAX_PARTICIPANTS} entries")

    participants: list[dict[str, Any]] = []
    definitions: dict[str, dict[str, Any]] = {}
    participant_ids: set[str] = set()
    occupied: dict[tuple[int, int], list[str]] = {}
    participant_tiny_flags: dict[str, bool] = {}
    loadouts: dict[str, Any] = {}
    for index, raw in enumerate(raw_participants):
        if not isinstance(raw, dict):
            raise EngineInputError(f"participants[{index}] must be an object")
        participant_id = str(raw.get("id") or "").strip()
        if not PARTICIPANT_ID_RE.fullmatch(participant_id) or participant_id in participant_ids:
            raise EngineInputError(f"participant id is invalid or duplicated: {participant_id}")
        participant_ids.add(participant_id)
        loadouts[participant_id] = raw.get("loadout")
        side = str(raw.get("side") or "").strip()
        if not PARTICIPANT_ID_RE.fullmatch(side):
            raise EngineInputError(f"participant {participant_id} side is invalid")
        reference = raw.get("creature")
        if not isinstance(reference, dict):
            raise EngineInputError(f"participant {participant_id} requires a creature reference")
        creature_id = creature_reference_id(reference, participant_id)
        if creature_id not in definitions:
            definitions[creature_id] = creature_loader(creature_id)
        definition = definitions[creature_id]
        if definition.get("id") != creature_id:
            raise EngineInputError(f"participant {participant_id} creature identity is invalid")
        is_tiny = creature_is_tiny(definition)
        participant_tiny_flags[participant_id] = is_tiny
        runtime_blockers = definition.get("runtimeBlockers")
        if runtime_blockers is not None and (
            type(runtime_blockers) is not list
            or any(
                type(item) is not str or not item
                for item in runtime_blockers
            )
            or runtime_blockers != sorted(set(runtime_blockers))
        ):
            raise EngineInputError(
                f"participant {participant_id} creature runtime blockers are invalid"
            )
        if runtime_blockers:
            raise EngineInputError(
                f"participant {participant_id} creature is blocked from "
                "runtime admission: "
                + ", ".join(runtime_blockers)
            )

        position = coordinate(raw.get("position"), f"participant {participant_id} position")
        squares = occupied_squares(position, definition)
        if footprint_straddles_active_barrier(normalized_map, squares):
            raise EngineInputError(
                f"participant {participant_id} straddles an active map barrier"
            )
        for square in squares:
            key = coordinate_key(square)
            if not square_is_inside(square, grid):
                raise EngineInputError(f"participant {participant_id} does not fit inside the map")
            if key in blocked_keys:
                raise EngineInputError(f"participant {participant_id} occupies a blocked square: {square}")
            occupants = occupied.get(key, [])
            if occupants and not creature_tiny_flags_can_share_square(
                [
                    *(
                        participant_tiny_flags[occupant]
                        for occupant in occupants
                    ),
                    is_tiny,
                ]
            ):
                raise EngineInputError(
                    f"participants {', '.join(occupants)} and "
                    f"{participant_id} overlap at: {square}"
                )
            occupied.setdefault(key, []).append(participant_id)
        maximum_hp = int(definition["defenses"]["maximumHitPoints"])
        participant = {
            "id": participant_id,
            "side": side,
            "creatureId": creature_id,
            "position": position,
            "occupiedSquares": squares,
            "hitPoints": {"current": maximum_hp, "maximum": maximum_hp},
            "conditions": [],
        }
        try:
            construct_armor = (
                animated_construct_armor.initial_participant_state(
                    definition
                )
            )
        except animated_construct_armor.AnimatedConstructArmorError as failure:
            raise EngineInputError(
                "participant Animated Construct Armor definition is invalid: "
                f"{failure}"
            ) from failure
        if construct_armor is not None:
            participant["constructArmor"] = construct_armor
        participants.append(participant)

    semantic_equipment = semantic_item_definitions is not None
    if semantic_equipment:
        if equipment_loader is not None:
            raise EngineInputError(
                "semantic battleground cannot use a source equipment loader"
            )
        equipment_catalog = compile_semantic_equipment_catalog(
            semantic_item_definitions
        )
        referenced_item_ids: set[str] = set()
        for definition in definitions.values():
            references = definition.get("references")
            item_refs = (
                references.get("items")
                if type(references) is dict
                else []
            )
            if type(item_refs) is not list or any(
                type(item) is not str for item in item_refs
            ):
                raise EngineInputError(
                    "semantic creature item reference closure is invalid"
                )
            referenced_item_ids.update(item_refs)
        if not referenced_item_ids.issubset(
            set(equipment_catalog["items"])
        ):
            raise EngineInputError(
                "semantic equipment catalog is missing a carried item"
            )
        definitions = {
            creature_id: bind_semantic_creature_equipment(
                definition,
                equipment_catalog,
            )
            for creature_id, definition in definitions.items()
        }
    else:
        equipment_names = {
            str(item.get("name") or "")
            for definition in definitions.values()
            for item in definition.get("inventory") or []
        }
        if equipment_names:
            if equipment_loader is None:
                raise EngineInputError(
                    "creature equipment requires a canonical equipment loader"
                )
            equipment_catalog = equipment_loader(equipment_names)
            definitions = {
                creature_id: bind_creature_equipment(
                    definition,
                    equipment_catalog,
                )
                for creature_id, definition in definitions.items()
            }
        else:
            equipment_catalog = {"schema": 1, "sourceRoots": [], "items": {}}
    item_instances = []
    for participant in participants:
        equipment_state = (
            initial_semantic_equipment_state(
                definitions[participant["creatureId"]],
                equipment_catalog,
                loadouts[participant["id"]],
            )
            if semantic_equipment
            else initial_equipment_state(
                definitions[participant["creatureId"]],
                equipment_catalog,
                loadouts[participant["id"]],
            )
        )
        if equipment_state is not None:
            participant["equipment"] = equipment_state
        item_instances.extend(
            (
                initial_semantic_item_instances(
                    participant["id"],
                    equipment_state,
                    equipment_catalog,
                )
                if semantic_equipment
                else initial_item_instances(
                    participant["id"],
                    equipment_state,
                    equipment_catalog,
                )
            )
        )

    implemented_capabilities = [
        "square-grid",
        "placement",
        "footprints",
        "distance",
        "reach",
        "unobstructed-visibility",
        (
            "semantic-equipment"
            if semantic_equipment
            else "source-backed-equipment"
        ),
        "exact-match-item-identity",
        "exact-initial-item-custody",
    ]
    not_yet_implemented = [
        "initiative",
        "turns",
        "movement",
        "strikes",
        "damage",
        "conditions",
    ]
    if canonical_map:
        implemented_capabilities.extend(
            [
                "data-first-map-topology",
                "solid-cell-blockers",
                "fixed-edge-barriers",
                "portal-initial-state",
            ]
        )
        not_yet_implemented.append("portal-state-actions")
    result: dict[str, Any] = {
        "schema": 1,
        "kind": "pf2er-battleground",
        "rules": rules,
        "map": normalized_map,
        "lightProduction": light_production,
        "equipmentCatalog": equipment_catalog,
        "itemInstances": item_instances,
        "definitions": {key: definitions[key] for key in sorted(definitions)},
        "participants": participants,
        "spatialRelations": map_relations(participants, definitions),
        "capabilities": {
            "implemented": [
                *implemented_capabilities,
                "light-production",
                "no-source-ordinary-darkness",
                "ambient-illumination",
                "hard-blocked-point-light-sources",
                "wielded-burning-torch-light",
            ],
            "notYetImplemented": not_yet_implemented,
        },
        "ruleReferences": {
            "movement": {"sourceId": "core-pc1", "locator": "420.1"},
            "gridMovement": {"sourceId": "core-pc1", "locator": "421.5"},
            "diagonalMovement": {"sourceId": "core-pc1", "locator": "421.6"},
            "sizeSpaceReach": {"sourceId": "core-pc1", "locator": "421.8"},
            "rangeAndReach": {"sourceId": "core-pc1", "locator": "426.3"},
            "stride": {"sourceId": "core-pc1", "locator": "418.3"},
            "strike": {"sourceId": "core-pc1", "locator": "418.4"},
            "carryingItems": {"sourceId": "core-pc1", "locator": "267.7"},
            "wieldingItems": {"sourceId": "core-pc1", "locator": "267.8"},
            "armor": {"sourceId": "core-pc1", "locator": "271.1"},
            "weapons": {"sourceId": "core-pc1", "locator": "275.1"},
        },
    }
    raw_adjudications = payload.get("adjudications")
    if raw_adjudications is not None and not isinstance(raw_adjudications, dict):
        raise EngineInputError("adjudications must be an object")
    registered_adjudications: dict[str, Any] = {}
    if adjudication_normalizers is not None:
        for adjudication_key in sorted(adjudication_normalizers):
            registration = adjudication_normalizers[adjudication_key]
            if (
                getattr(registration, "adjudication_key", None)
                != adjudication_key
                or not callable(getattr(registration, "normalize", None))
            ):
                raise EngineInputError(
                    "selected battleground adjudication normalizer is invalid"
                )
            supplied = (
                {adjudication_key: raw_adjudications[adjudication_key]}
                if isinstance(raw_adjudications, dict)
                and adjudication_key in raw_adjudications
                else None
            )
            normalized = registration.normalize(
                supplied,
                participants=participants,
                definitions=definitions,
            )
            if normalized is None:
                continue
            if (
                not isinstance(normalized, dict)
                or set(normalized) != {adjudication_key}
            ):
                raise EngineInputError(
                    "selected battleground adjudication normalizer returned "
                    "an invalid result"
                )
            registered_adjudications.update(normalized)
        olfactory = None
    else:
        # Transitional source-addressed and direct-test facade. Configured
        # semantic play always supplies the selected registry above.
        olfactory = normalize_olfactory_aura_adjudications(
            (
                {"olfactoryAuras": raw_adjudications["olfactoryAuras"]}
                if isinstance(raw_adjudications, dict)
                and "olfactoryAuras" in raw_adjudications
                else None
            ),
            participants=participants,
            definitions=definitions,
        )
    leer = normalize_scarecrow_leer_adjudications(
        (
            {"scarecrowLeerTargets": raw_adjudications["scarecrowLeerTargets"]}
            if isinstance(raw_adjudications, dict)
            and "scarecrowLeerTargets" in raw_adjudications
            else None
        ),
        participants=participants,
        definitions=definitions,
    )
    ghoul_corpses = normalize_ghoul_corpse_adjudications(
        (
            {"ghoulCorpseTargets": raw_adjudications["ghoulCorpseTargets"]}
            if isinstance(raw_adjudications, dict)
            and "ghoulCorpseTargets" in raw_adjudications
            else None
        ),
        participants=participants,
        definitions=definitions,
    )
    adjudications = {
        **registered_adjudications,
        **(olfactory or {}),
        **(leer or {}),
        **(ghoul_corpses or {}),
    }
    if isinstance(raw_adjudications, dict) and set(raw_adjudications) != set(adjudications):
        raise EngineInputError("adjudications contains an inactive or unknown matrix")
    if adjudications:
        result["adjudications"] = adjudications
    if rules_receipt is not None:
        result["rulesReceipt"] = _canonical_map_copy(
            rules_receipt,
            "rules receipt",
        )
    refresh_state_illumination(result)
    result["stateDigest"] = battleground_digest(result)
    return result


def build_battleground(
    payload: Any,
    *,
    manifest: dict[str, Any],
    creature_loader: Callable[[str, str], dict[str, Any]],
    equipment_loader: Callable[[set[str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the source-addressed battleground used by the legacy catalog port."""

    if not isinstance(payload, dict):
        raise EngineInputError("request body must be an object")
    rules = validate_rules(payload.get("rules"), manifest)
    selected_sources = {str(item["id"]) for item in rules["sources"]}

    def reference_id(reference: dict[str, Any], participant_id: str) -> str:
        source_id = str(reference.get("sourceId") or "").strip()
        locator = str(reference.get("locator") or "").strip()
        if not source_id or not locator or source_id not in selected_sources:
            raise EngineInputError(
                f"participant {participant_id} creature is outside the selected sources"
            )
        return f"{source_id}:{locator}"

    def load(creature_id: str) -> dict[str, Any]:
        source_id, locator = creature_id.split(":", 1)
        return creature_loader(source_id, locator)

    return _assemble_battleground(
        payload,
        rules=rules,
        creature_reference_id=reference_id,
        creature_loader=load,
        equipment_loader=equipment_loader,
    )


def build_semantic_battleground(
    payload: Any,
    *,
    rules_identity: dict[str, Any],
    creature_loader: Callable[[str], dict[str, Any]],
    rules_receipt: dict[str, Any],
    semantic_item_definitions: dict[str, dict[str, Any]],
    adjudication_normalizers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a battleground from namespaced semantic creature identities.

    Selection and package verification belong to the Gladiator catalog port;
    this entry only adapts already-authenticated semantic definitions into the
    existing battleground assembly kernel.
    """

    if not isinstance(payload, dict):
        raise EngineInputError("request body must be an object")
    if payload.get("rules") != rules_identity:
        raise EngineInputError(
            "rules identity does not match the server-owned environment"
        )
    if type(semantic_item_definitions) is not dict:
        raise EngineInputError(
            "semantic battleground requires selected item definitions"
        )
    sealed_receipt = _canonical_map_copy(rules_receipt, "rules receipt")
    sealed_rules = {
        **_canonical_map_copy(rules_identity, "rules identity"),
        # The request selects only by identity. This server-added receipt then
        # travels with the immutable ``rules`` field into mechanics artifacts.
        "receipt": sealed_receipt,
    }

    def reference_id(reference: dict[str, Any], participant_id: str) -> str:
        if set(reference) != {"entityId"}:
            raise EngineInputError(
                f"participant {participant_id} creature must contain exactly entityId"
            )
        entity_id = reference.get("entityId")
        if type(entity_id) is not str or not entity_id:
            raise EngineInputError(
                f"participant {participant_id} creature entityId is invalid"
            )
        return entity_id

    return _assemble_battleground(
        payload,
        rules=sealed_rules,
        creature_reference_id=reference_id,
        creature_loader=creature_loader,
        semantic_item_definitions=semantic_item_definitions,
        rules_receipt=sealed_receipt,
        adjudication_normalizers=adjudication_normalizers,
    )

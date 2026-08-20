"""Exact hard-barrier and four-corner geometry for bounded PF2ER encounters.

This module implements the application's GM ruling for ranged cover and
provides the same exact solid-cell and active-edge geometry for line of effect
and line of sight. It does not define spell areas or visual abilities.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import combinations
import json
from math import gcd
from typing import Any, Iterable

from .errors import EngineInputError
from .map_data import (
    active_barrier_edges,
    normalize_runtime_map,
    solid_cells,
)


COVER_RULE = {"sourceId": "core-pc1", "locator": "424.2"}
LINE_OF_EFFECT_RULE = {"sourceId": "core-pc1", "locator": "426.6"}
RANGED_COVER_RULING = "four-target-corners-any-source-point-v1"
FIXED_POINT_LINE_OF_EFFECT_RULING = (
    "participant-footprint-to-fixed-point-hard-line-of-effect-v1"
)
FIXED_ORIGIN_AREA_COVER_RULING = (
    "fixed-origin-four-target-corners-area-cover-v1"
)
MAX_ARRANGEMENT_LINES = 128

_CORNER_NAMES = ("northwest", "northeast", "southeast", "southwest")
_EXPECTED_VISIBILITY_RULES = {
    "lineOfEffect": LINE_OF_EFFECT_RULE,
    "lineOfSight": {"sourceId": "core-pc1", "locator": "427.2"},
}

Point = tuple[Fraction, Fraction]
Line = tuple[int, int, int]
Rectangle = tuple[int, int, int, int]
Edge = tuple[int, int, int, int]


@dataclass(frozen=True)
class _SoftBlocker:
    participant_id: str
    rectangle: Rectangle


@dataclass(frozen=True)
class _HardTopology:
    squares: frozenset[tuple[int, int]]
    barrier_edges: tuple[Edge, ...]
    arrangement_vertices: tuple[tuple[int, int], ...]
    pinch_vertices: dict[tuple[int, int], tuple[tuple[int, int], ...]]


@lru_cache(maxsize=4096)
def _merged_collinear_barrier_edges(
    barrier_edges: tuple[Edge, ...],
) -> tuple[Edge, ...]:
    """Collapse unit barrier edges into the same maximal closed segments."""

    horizontal: dict[int, list[tuple[int, int]]] = {}
    vertical: dict[int, list[tuple[int, int]]] = {}
    for start_x, start_y, end_x, end_y in barrier_edges:
        if start_y == end_y:
            horizontal.setdefault(start_y, []).append(
                (min(start_x, end_x), max(start_x, end_x))
            )
        elif start_x == end_x:
            vertical.setdefault(start_x, []).append(
                (min(start_y, end_y), max(start_y, end_y))
            )
        else:
            raise EngineInputError("barrier edge must be cardinal")

    merged: list[Edge] = []
    for fixed, spans in sorted(horizontal.items()):
        start, end = sorted(spans)[0]
        for next_start, next_end in sorted(spans)[1:]:
            if next_start <= end:
                end = max(end, next_end)
                continue
            merged.append((start, fixed, end, fixed))
            start, end = next_start, next_end
        merged.append((start, fixed, end, fixed))
    for fixed, spans in sorted(vertical.items()):
        start, end = sorted(spans)[0]
        for next_start, next_end in sorted(spans)[1:]:
            if next_start <= end:
                end = max(end, next_end)
                continue
            merged.append((fixed, start, fixed, end))
            start, end = next_start, next_end
        merged.append((fixed, start, fixed, end))
    return tuple(sorted(merged))


def _fraction_payload(value: Fraction) -> dict[str, int]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
    }


def _point_payload(point: Point) -> dict[str, dict[str, int]]:
    return {
        "x": _fraction_payload(point[0]),
        "y": _fraction_payload(point[1]),
    }


def _rectangle_payload(rectangle: Rectangle) -> dict[str, int]:
    left, top, right, bottom = rectangle
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
    }


def _edge_payload(edge: Edge) -> dict[str, dict[str, int]]:
    start_x, start_y, end_x, end_y = edge
    return {
        "from": {"x": start_x, "y": start_y},
        "to": {"x": end_x, "y": end_y},
    }


def _participant_rectangle(participant: dict[str, Any]) -> Rectangle:
    raw_squares = participant.get("occupiedSquares")
    if not isinstance(raw_squares, list) or not raw_squares:
        raise EngineInputError(
            f"participant footprint is invalid: {participant.get('id')}"
        )
    squares: set[tuple[int, int]] = set()
    for raw in raw_squares:
        if (
            not isinstance(raw, dict)
            or isinstance(raw.get("x"), bool)
            or not isinstance(raw.get("x"), int)
            or isinstance(raw.get("y"), bool)
            or not isinstance(raw.get("y"), int)
        ):
            raise EngineInputError(
                f"participant footprint is invalid: {participant.get('id')}"
            )
        squares.add((raw["x"], raw["y"]))
    left = min(x for x, _y in squares)
    top = min(y for _x, y in squares)
    right = max(x for x, _y in squares) + 1
    bottom = max(y for _x, y in squares) + 1
    expected = {
        (x, y)
        for y in range(top, bottom)
        for x in range(left, right)
    }
    if squares != expected:
        raise EngineInputError(
            f"participant footprint must be rectangular: {participant.get('id')}"
        )
    return left, top, right, bottom


def _rectangle_corners(rectangle: Rectangle) -> tuple[Point, Point, Point, Point]:
    left, top, right, bottom = rectangle
    return (
        (Fraction(left), Fraction(top)),
        (Fraction(right), Fraction(top)),
        (Fraction(right), Fraction(bottom)),
        (Fraction(left), Fraction(bottom)),
    )


def _rectangle_center(rectangle: Rectangle) -> Point:
    left, top, right, bottom = rectangle
    return (
        Fraction(left + right, 2),
        Fraction(top + bottom, 2),
    )


def _point_in_rectangle(point: Point, rectangle: Rectangle) -> bool:
    left, top, right, bottom = rectangle
    return (
        Fraction(left) <= point[0] <= Fraction(right)
        and Fraction(top) <= point[1] <= Fraction(bottom)
    )


def _open_rectangles_overlap(first: Rectangle, second: Rectangle) -> bool:
    return (
        max(first[0], second[0]) < min(first[2], second[2])
        and max(first[1], second[1]) < min(first[3], second[3])
    )


def _normalized_line(first: Point, second: Point) -> Line | None:
    if first == second:
        return None
    delta_x = second[0] - first[0]
    delta_y = second[1] - first[1]
    if (
        delta_x.denominator != 1
        or delta_y.denominator != 1
        or first[0].denominator != 1
        or first[1].denominator != 1
    ):
        raise EngineInputError("critical cover line is not grid integral")
    a = int(delta_y)
    b = -int(delta_x)
    c = -(a * int(first[0]) + b * int(first[1]))
    common = gcd(gcd(abs(a), abs(b)), abs(c))
    if common:
        a //= common
        b //= common
        c //= common
    if a < 0 or (a == 0 and b < 0):
        a, b, c = -a, -b, -c
    return a, b, c


def _line_value(line: Line, point: Point) -> Fraction:
    a, b, c = line
    return a * point[0] + b * point[1] + c


def _line_crosses_rectangle(line: Line, rectangle: Rectangle) -> bool:
    values = [_line_value(line, point) for point in _rectangle_corners(rectangle)]
    return min(values) <= 0 <= max(values)


def _blocker_can_lie_between_source_and_target(
    target_endpoint: Point,
    blocker_point: Point,
    source_rectangle: Rectangle,
) -> bool:
    """Return whether the target-to-blocker ray reaches the source beyond it."""

    delta_x = blocker_point[0] - target_endpoint[0]
    delta_y = blocker_point[1] - target_endpoint[1]
    if delta_x == 0 and delta_y == 0:
        return False
    lower = Fraction(1)
    upper: Fraction | None = None
    for start, delta, minimum, maximum in (
        (target_endpoint[0], delta_x, source_rectangle[0], source_rectangle[2]),
        (target_endpoint[1], delta_y, source_rectangle[1], source_rectangle[3]),
    ):
        if delta == 0:
            if not Fraction(minimum) <= start <= Fraction(maximum):
                return False
            continue
        first = (Fraction(minimum) - start) / delta
        second = (Fraction(maximum) - start) / delta
        lower = max(lower, min(first, second))
        axis_upper = max(first, second)
        upper = axis_upper if upper is None else min(upper, axis_upper)
        if upper < lower:
            return False
    return upper is None or lower <= upper


def _line_intersection(first: Line, second: Line) -> Point | None:
    a1, b1, c1 = first
    a2, b2, c2 = second
    determinant = a1 * b2 - a2 * b1
    if determinant == 0:
        return None
    return (
        Fraction(b1 * c2 - b2 * c1, determinant),
        Fraction(c1 * a2 - c2 * a1, determinant),
    )


def _line_rectangle_intersections(
    line: Line,
    rectangle: Rectangle,
) -> set[Point]:
    left, top, right, bottom = rectangle
    a, b, c = line
    points: set[Point] = set()
    if b:
        for x in (Fraction(left), Fraction(right)):
            point = (x, Fraction(-(a * x + c), b))
            if _point_in_rectangle(point, rectangle):
                points.add(point)
    if a:
        for y in (Fraction(top), Fraction(bottom)):
            point = (Fraction(-(b * y + c), a), y)
            if _point_in_rectangle(point, rectangle):
                points.add(point)
    return points


def _projection_onto_line(point: Point, line: Line) -> Point:
    a, b, c = line
    scale = _line_value(line, point) / (a * a + b * b)
    return point[0] - a * scale, point[1] - b * scale


def _ordered_on_line(points: Iterable[Point], line: Line) -> list[Point]:
    _a, b, _c = line
    return sorted(
        set(points),
        key=lambda point: (
            (point[1], point[0])
            if b == 0
            else (point[0], point[1])
        ),
    )


def _midpoint(first: Point, second: Point) -> Point:
    return (
        (first[0] + second[0]) / 2,
        (first[1] + second[1]) / 2,
    )


def _local_epsilon(point: Point, lines: list[Line], rectangle: Rectangle) -> Fraction:
    candidates = [Fraction(1, 8)]
    left, top, right, bottom = rectangle
    for boundary in (
        point[0] - left,
        right - point[0],
        point[1] - top,
        bottom - point[1],
    ):
        if boundary > 0:
            candidates.append(boundary / 3)
    for line in lines:
        value = abs(_line_value(line, point))
        if value:
            a, b, _c = line
            candidates.append(value / (3 * (abs(a) + abs(b))))
    return min(candidates)


def _arrangement_candidates(
    source_rectangle: Rectangle,
    target_corners: tuple[Point, Point, Point, Point],
    blocker_points: Iterable[Point],
) -> set[Point]:
    source_center = _rectangle_center(source_rectangle)
    source_corners = _rectangle_corners(source_rectangle)
    critical_blocker_points = tuple(set(blocker_points))
    line_set = set()
    for target_corner in target_corners:
        for blocker_corner in critical_blocker_points:
            line = _normalized_line(target_corner, blocker_corner)
            if (
                line is None
                or not _line_crosses_rectangle(line, source_rectangle)
                or not _blocker_can_lie_between_source_and_target(
                    target_corner,
                    blocker_corner,
                    source_rectangle,
                )
            ):
                continue
            line_set.add(line)
            if len(line_set) > MAX_ARRANGEMENT_LINES:
                raise EngineInputError(
                    "ranged Strike cover arrangement is too complex"
                )
    lines = sorted(line_set)
    candidates: set[Point] = {
        source_center,
        *source_corners,
        *(
            _midpoint(source_corners[index], source_corners[(index + 1) % 4])
            for index in range(4)
        ),
    }
    line_points: dict[Line, set[Point]] = {
        line: _line_rectangle_intersections(line, source_rectangle)
        for line in lines
    }
    for line in lines:
        projection = _projection_onto_line(source_center, line)
        if _point_in_rectangle(projection, source_rectangle):
            candidates.add(projection)
    for first, second in combinations(lines, 2):
        point = _line_intersection(first, second)
        if point is None or not _point_in_rectangle(point, source_rectangle):
            continue
        line_points[first].add(point)
        line_points[second].add(point)
    arrangement_vertices = set(source_corners)
    for line, points in line_points.items():
        ordered = _ordered_on_line(points, line)
        arrangement_vertices.update(ordered)
        candidates.update(ordered)
        candidates.update(
            _midpoint(first, second)
            for first, second in zip(ordered, ordered[1:])
        )

    left, top, right, bottom = source_rectangle
    boundary_lines = (
        ((Fraction(left), Fraction(top)), (Fraction(right), Fraction(top))),
        ((Fraction(right), Fraction(top)), (Fraction(right), Fraction(bottom))),
        ((Fraction(right), Fraction(bottom)), (Fraction(left), Fraction(bottom))),
        ((Fraction(left), Fraction(bottom)), (Fraction(left), Fraction(top))),
    )
    for first, second in boundary_lines:
        points = {first, second}
        if first[1] == second[1]:
            points.update(
                point
                for point in arrangement_vertices
                if point[1] == first[1]
            )
            ordered = sorted(points, key=lambda point: point[0])
        else:
            points.update(
                point
                for point in arrangement_vertices
                if point[0] == first[0]
            )
            ordered = sorted(points, key=lambda point: point[1])
        candidates.update(
            _midpoint(left_point, right_point)
            for left_point, right_point in zip(ordered, ordered[1:])
        )

    # Interior representatives adjacent to every arrangement vertex ensure
    # Closed solid-union pinches do not make this a boundary-only search.
    for vertex in arrangement_vertices:
        incident = [line for line in lines if _line_value(line, vertex) == 0]
        epsilon = _local_epsilon(vertex, lines, source_rectangle)
        for direction in (-1, 1):
            x = vertex[0] + direction * epsilon
            if not Fraction(left) <= x <= Fraction(right):
                continue
            low = max(Fraction(top), vertex[1] - epsilon)
            high = min(Fraction(bottom), vertex[1] + epsilon)
            y_values = {low, high}
            for a, b, c in incident:
                if not b:
                    continue
                y = Fraction(-(a * x + c), b)
                if low <= y <= high:
                    y_values.add(y)
            ordered_y = sorted(y_values)
            candidates.update((x, y) for y in ordered_y)
            candidates.update(
                (x, (first_y + second_y) / 2)
                for first_y, second_y in zip(ordered_y, ordered_y[1:])
            )
    return {
        point
        for point in candidates
        if _point_in_rectangle(point, source_rectangle)
    }


def _open_segment_intersects_open_rectangle(
    origin: Point,
    endpoint: Point,
    rectangle: Rectangle,
) -> bool:
    lower = Fraction(0)
    upper = Fraction(1)
    for start, finish, minimum, maximum in (
        (origin[0], endpoint[0], rectangle[0], rectangle[2]),
        (origin[1], endpoint[1], rectangle[1], rectangle[3]),
    ):
        delta = finish - start
        if delta == 0:
            if not Fraction(minimum) < start < Fraction(maximum):
                return False
            continue
        first = (Fraction(minimum) - start) / delta
        second = (Fraction(maximum) - start) / delta
        lower = max(lower, min(first, second))
        upper = min(upper, max(first, second))
        if lower >= upper:
            return False
    return lower < upper


def _cross(origin: Point, endpoint: Point, point: Point) -> Fraction:
    return (
        (endpoint[0] - origin[0]) * (point[1] - origin[1])
        - (endpoint[1] - origin[1]) * (point[0] - origin[0])
    )


def _point_on_closed_segment(
    point: Point,
    first: Point,
    second: Point,
) -> bool:
    return (
        _cross(first, second, point) == 0
        and min(first[0], second[0]) <= point[0] <= max(first[0], second[0])
        and min(first[1], second[1]) <= point[1] <= max(first[1], second[1])
    )


def _closed_segments_intersect(
    first_start: Point,
    first_end: Point,
    second_start: Point,
    second_end: Point,
) -> bool:
    """Return exact closed-segment contact, including collinear overlap."""

    first_side_start = _cross(first_start, first_end, second_start)
    first_side_end = _cross(first_start, first_end, second_end)
    second_side_start = _cross(second_start, second_end, first_start)
    second_side_end = _cross(second_start, second_end, first_end)
    if (
        (first_side_start > 0 > first_side_end)
        or (first_side_start < 0 < first_side_end)
    ) and (
        (second_side_start > 0 > second_side_end)
        or (second_side_start < 0 < second_side_end)
    ):
        return True
    return (
        (
            first_side_start == 0
            and _point_on_closed_segment(
                second_start,
                first_start,
                first_end,
            )
        )
        or (
            first_side_end == 0
            and _point_on_closed_segment(
                second_end,
                first_start,
                first_end,
            )
        )
        or (
            second_side_start == 0
            and _point_on_closed_segment(
                first_start,
                second_start,
                second_end,
            )
        )
        or (
            second_side_end == 0
            and _point_on_closed_segment(
                first_end,
                second_start,
                second_end,
            )
        )
    )


def _segments_have_positive_collinear_overlap(
    first_start: Point,
    first_end: Point,
    second_start: Point,
    second_end: Point,
) -> bool:
    if (
        _cross(first_start, first_end, second_start) != 0
        or _cross(first_start, first_end, second_end) != 0
    ):
        return False
    axis = 0 if first_start[0] != first_end[0] else 1
    return max(
        min(first_start[axis], first_end[axis]),
        min(second_start[axis], second_end[axis]),
    ) < min(
        max(first_start[axis], first_end[axis]),
        max(second_start[axis], second_end[axis]),
    )


def _rectangles_straddle_edge(
    source_rectangle: Rectangle,
    target_rectangle: Rectangle,
    edge_start: Point,
    edge_end: Point,
) -> bool:
    source_side = _cross(
        edge_start,
        edge_end,
        _rectangle_center(source_rectangle),
    )
    target_side = _cross(
        edge_start,
        edge_end,
        _rectangle_center(target_rectangle),
    )
    return (
        (source_side > 0 > target_side)
        or (source_side < 0 < target_side)
    )


def _points_straddle_edge(
    first: Point,
    second: Point,
    edge_start: Point,
    edge_end: Point,
) -> bool:
    first_side = _cross(edge_start, edge_end, first)
    second_side = _cross(edge_start, edge_end, second)
    return (
        (first_side > 0 > second_side)
        or (first_side < 0 < second_side)
    )


def _barrier_edge_blocks_ray(
    origin: Point,
    endpoint: Point,
    edge: Edge,
    *,
    source_rectangle: Rectangle | None,
    target_rectangle: Rectangle | None,
) -> bool:
    edge_start = (Fraction(edge[0]), Fraction(edge[1]))
    edge_end = (Fraction(edge[2]), Fraction(edge[3]))
    if not _closed_segments_intersect(
        origin,
        endpoint,
        edge_start,
        edge_end,
    ):
        return False
    if _segments_have_positive_collinear_overlap(
        origin,
        endpoint,
        edge_start,
        edge_end,
    ):
        return True

    origin_contact = _point_on_closed_segment(
        origin,
        edge_start,
        edge_end,
    )
    endpoint_contact = _point_on_closed_segment(
        endpoint,
        edge_start,
        edge_end,
    )
    if not origin_contact and not endpoint_contact:
        # Proper crossings and contact with a barrier endpoint in the
        # interior of the ray are both hard under the bounded GM ruling.
        return True
    if target_rectangle is None:
        return True
    if endpoint_contact and not origin_contact:
        source_reference = (
            _rectangle_center(source_rectangle)
            if source_rectangle is not None
            else origin
        )
        if _cross(
            edge_start,
            edge_end,
            source_reference,
        ) == 0:
            return True
        return _points_straddle_edge(
            source_reference,
            _rectangle_center(target_rectangle),
            edge_start,
            edge_end,
        )
    if source_rectangle is None:
        return True
    return _rectangles_straddle_edge(
        source_rectangle,
        target_rectangle,
        edge_start,
        edge_end,
    )


def _fraction_floor(value: Fraction) -> int:
    return value.numerator // value.denominator


def _fraction_ceiling(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


def _open_segment_grid_squares(
    origin: Point,
    endpoint: Point,
) -> set[tuple[int, int]]:
    """Return only unit-square interiors crossed by an exact open segment."""

    if origin == endpoint:
        return set()
    delta_x = endpoint[0] - origin[0]
    delta_y = endpoint[1] - origin[1]
    breakpoints = {Fraction(0), Fraction(1)}
    for start, finish, delta in (
        (origin[0], endpoint[0], delta_x),
        (origin[1], endpoint[1], delta_y),
    ):
        if not delta:
            continue
        minimum = min(start, finish)
        maximum = max(start, finish)
        for grid_line in range(
            _fraction_floor(minimum) + 1,
            _fraction_ceiling(maximum),
        ):
            parameter = (Fraction(grid_line) - start) / delta
            if 0 < parameter < 1:
                breakpoints.add(parameter)
    ordered = sorted(breakpoints)
    result = set()
    for first, second in zip(ordered, ordered[1:]):
        parameter = (first + second) / 2
        x = origin[0] + delta_x * parameter
        y = origin[1] + delta_y * parameter
        # A segment lying on a grid line crosses no open square interior.
        if x.denominator == 1 or y.denominator == 1:
            continue
        result.add((_fraction_floor(x), _fraction_floor(y)))
    return result


def square_center_segment_square_keys(
    origin: object,
    endpoint: object,
) -> frozenset[tuple[int, int]]:
    """Return every grid-square interior crossed between two square centers."""

    normalized = []
    for value, label in (
        (origin, "object movement origin"),
        (endpoint, "object movement endpoint"),
    ):
        if (
            not isinstance(value, dict)
            or set(value) != {"x", "y"}
            or isinstance(value.get("x"), bool)
            or not isinstance(value.get("x"), int)
            or isinstance(value.get("y"), bool)
            or not isinstance(value.get("y"), int)
        ):
            raise EngineInputError(f"{label} is invalid")
        normalized.append((int(value["x"]), int(value["y"])))
    first, second = normalized
    first_center = (
        Fraction(first[0] * 2 + 1, 2),
        Fraction(first[1] * 2 + 1, 2),
    )
    second_center = (
        Fraction(second[0] * 2 + 1, 2),
        Fraction(second[1] * 2 + 1, 2),
    )
    return frozenset(
        {
            first,
            second,
            *_open_segment_grid_squares(
                first_center,
                second_center,
            ),
        }
    )


def _open_segment_grid_vertices(
    origin: Point,
    endpoint: Point,
) -> set[tuple[int, int]]:
    """Return integer grid vertices strictly inside an exact segment."""

    if origin == endpoint:
        return set()
    delta_x = endpoint[0] - origin[0]
    delta_y = endpoint[1] - origin[1]
    result = set()
    if delta_x:
        for x in range(
            _fraction_floor(min(origin[0], endpoint[0])) + 1,
            _fraction_ceiling(max(origin[0], endpoint[0])),
        ):
            parameter = (Fraction(x) - origin[0]) / delta_x
            y = origin[1] + delta_y * parameter
            if 0 < parameter < 1 and y.denominator == 1:
                result.add((x, int(y)))
    elif origin[0].denominator == 1:
        x = int(origin[0])
        for y in range(
            _fraction_floor(min(origin[1], endpoint[1])) + 1,
            _fraction_ceiling(max(origin[1], endpoint[1])),
        ):
            result.add((x, y))
    return result


def _hard_topology(
    squares: set[tuple[int, int]],
    barrier_edges: tuple[Edge, ...] = (),
) -> _HardTopology:
    vertices: set[tuple[int, int]] = set()
    for x, y in sorted(squares, key=lambda item: (item[1], item[0])):
        vertices.update(((x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)))
    arrangement_vertices = []
    pinch_vertices = {}
    for vertex in sorted(vertices, key=lambda item: (item[1], item[0])):
        incident = tuple(
            sorted(
                (
                    square
                    for square in (
                        (vertex[0] - 1, vertex[1] - 1),
                        (vertex[0], vertex[1] - 1),
                        (vertex[0] - 1, vertex[1]),
                        (vertex[0], vertex[1]),
                    )
                    if square in squares
                ),
                key=lambda item: (item[1], item[0]),
            )
        )
        diagonal_pinch = (
            len(incident) == 2
            and incident[0][0] != incident[1][0]
            and incident[0][1] != incident[1][1]
        )
        if len(incident) in {1, 3} or diagonal_pinch:
            arrangement_vertices.append(vertex)
        if diagonal_pinch:
            pinch_vertices[vertex] = incident
    arrangement_vertices.extend(
        (x, y)
        for edge in barrier_edges
        for x, y in ((edge[0], edge[1]), (edge[2], edge[3]))
    )
    return _HardTopology(
        squares=frozenset(squares),
        barrier_edges=barrier_edges,
        arrangement_vertices=tuple(
            sorted(
                set(arrangement_vertices),
                key=lambda item: (item[1], item[0]),
            )
        ),
        pinch_vertices=pinch_vertices,
    )


def _solid_blockers(
    origin: Point,
    endpoint: Point,
    topology: _HardTopology,
) -> list[tuple[int, int]]:
    if not topology.squares:
        return []
    blockers = set(
        topology.squares.intersection(
            _open_segment_grid_squares(origin, endpoint)
        )
    )
    if origin[0] == endpoint[0] and origin[0].denominator == 1:
        x = int(origin[0])
        minimum = min(origin[1], endpoint[1])
        maximum = max(origin[1], endpoint[1])
        for y in range(
            _fraction_floor(minimum),
            _fraction_ceiling(maximum),
        ):
            if max(minimum, Fraction(y)) >= min(maximum, Fraction(y + 1)):
                continue
            blockers.update(
                square
                for square in ((x - 1, y), (x, y))
                if square in topology.squares
            )
    elif origin[1] == endpoint[1] and origin[1].denominator == 1:
        y = int(origin[1])
        minimum = min(origin[0], endpoint[0])
        maximum = max(origin[0], endpoint[0])
        for x in range(
            _fraction_floor(minimum),
            _fraction_ceiling(maximum),
        ):
            if max(minimum, Fraction(x)) >= min(maximum, Fraction(x + 1)):
                continue
            blockers.update(
                square
                for square in ((x, y - 1), (x, y))
                if square in topology.squares
            )
    for vertex in _open_segment_grid_vertices(origin, endpoint):
        incident_squares = topology.pinch_vertices.get(vertex)
        if incident_squares is None:
            continue
        signs = set()
        for square in incident_squares:
            value = _cross(
                origin,
                endpoint,
                (
                    Fraction(2 * square[0] + 1, 2),
                    Fraction(2 * square[1] + 1, 2),
                ),
            )
            signs.add(1 if value > 0 else -1 if value < 0 else 0)
        if 1 in signs and -1 in signs:
            blockers.update(incident_squares)
    return sorted(blockers, key=lambda item: (item[1], item[0]))


def _barrier_edge_blockers(
    origin: Point,
    endpoint: Point,
    topology: _HardTopology,
    *,
    source_rectangle: Rectangle | None = None,
    target_rectangle: Rectangle | None = None,
) -> list[Edge]:
    """Return active unit edges contacted by one exact projectile segment."""

    if origin == endpoint:
        return []
    return [
        edge
        for edge in topology.barrier_edges
        if _barrier_edge_blocks_ray(
            origin,
            endpoint,
            edge,
            source_rectangle=source_rectangle,
            target_rectangle=target_rectangle,
        )
    ]


def _segment_has_hard_blocker(
    origin: Point,
    endpoint: Point,
    topology: _HardTopology,
    *,
    source_rectangle: Rectangle | None = None,
    target_rectangle: Rectangle | None = None,
) -> bool:
    return bool(
        _solid_blockers(origin, endpoint, topology)
        or _barrier_edge_blockers(
            origin,
            endpoint,
            topology,
            source_rectangle=source_rectangle,
            target_rectangle=target_rectangle,
        )
    )


@lru_cache(maxsize=4096)
def _cached_hard_topology(
    solid_squares: tuple[tuple[int, int], ...],
    barrier_edges: tuple[Edge, ...],
) -> _HardTopology:
    return _hard_topology(set(solid_squares), barrier_edges)


@lru_cache(maxsize=8192)
def _cached_squares_with_line_of_effect(
    origin: Point,
    squares: tuple[tuple[int, int], ...],
    solid_squares: tuple[tuple[int, int], ...],
    barrier_edges: tuple[Edge, ...],
) -> frozenset[tuple[int, int]]:
    topology = _cached_hard_topology(solid_squares, barrier_edges)
    solid = frozenset(solid_squares)
    reachable = set()
    for x, y in squares:
        if (x, y) in solid:
            continue
        target_rectangle = (x, y, x + 1, y + 1)
        target_corners = _rectangle_corners(target_rectangle)
        if any(
            endpoint != origin
            and not _segment_has_hard_blocker(
                origin,
                endpoint,
                topology,
                target_rectangle=target_rectangle,
            )
            for endpoint in target_corners
        ):
            reachable.add((x, y))
    return frozenset(reachable)


@lru_cache(maxsize=65536)
def _cached_participant_line_of_effect(
    source_rectangle: Rectangle,
    target_rectangle: Rectangle,
    source_square_keys: tuple[tuple[int, int], ...],
    target_square_keys: tuple[tuple[int, int], ...],
    solid_square_keys: tuple[tuple[int, int], ...],
    barrier_edges: tuple[Edge, ...],
    additional_blocked_squares: tuple[tuple[int, int], ...] = (),
) -> bool:
    solid_squares = set(solid_square_keys)
    solid_squares.update(additional_blocked_squares)
    solid_squares.difference_update(source_square_keys)
    solid_squares.difference_update(target_square_keys)
    topology = _cached_hard_topology(
        tuple(sorted(solid_squares)),
        _merged_collinear_barrier_edges(barrier_edges),
    )
    if not topology.squares and not topology.barrier_edges:
        return True
    target_corners = _rectangle_corners(target_rectangle)
    candidates = _arrangement_candidates(
        source_rectangle,
        target_corners,
        (
            (Fraction(x), Fraction(y))
            for x, y in topology.arrangement_vertices
        ),
    )
    return any(
        endpoint != origin
        and not _segment_has_hard_blocker(
            origin,
            endpoint,
            topology,
            source_rectangle=source_rectangle,
            target_rectangle=target_rectangle,
        )
        for origin in candidates
        for endpoint in target_corners
    )


@lru_cache(maxsize=256)
def _cached_runtime_hard_geometry(
    encoded_runtime_map: str,
) -> tuple[tuple[tuple[int, int], ...], tuple[Edge, ...]]:
    normalized = normalize_runtime_map(json.loads(encoded_runtime_map))
    topology = normalized["topology"]
    squares = tuple(
        (int(square["x"]), int(square["y"]))
        for square in solid_cells(topology)
    )
    edges = tuple(
        (
            int(edge["from"]["x"]),
            int(edge["from"]["y"]),
            int(edge["to"]["x"]),
            int(edge["to"]["y"]),
        )
        for edge in active_barrier_edges(
            topology,
            normalized["portalStates"],
        )
    )
    return squares, edges


def _visibility_hard_geometry(
    state: dict[str, Any],
) -> tuple[set[tuple[int, int]], tuple[Edge, ...]]:
    runtime_map = state.get("map", {})
    if not isinstance(runtime_map, dict):
        raise EngineInputError("encounter map contract is invalid")
    if runtime_map.get("kind") is not None:
        try:
            encoded = json.dumps(
                runtime_map,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as failure:
            raise EngineInputError(
                "encounter map contract is invalid"
            ) from failure
        squares, edges = _cached_runtime_hard_geometry(encoded)
        return set(squares), edges

    visibility = runtime_map.get(
        "visibility",
        {"mode": "unobstructed"},
    )
    mode = visibility.get("mode")
    if mode == "unobstructed":
        return set(), ()
    if (
        mode != "solid-barriers"
        or visibility.get("rules") != _EXPECTED_VISIBILITY_RULES
        or not isinstance(visibility.get("opaqueSquares"), list)
    ):
        raise EngineInputError("encounter visibility contract is invalid")
    return (
        {
            (int(square["x"]), int(square["y"]))
            for square in visibility["opaqueSquares"]
        },
        (),
    )


def squares_with_line_of_effect_from_point(
    state: dict[str, Any],
    origin: Point,
    squares: Iterable[tuple[int, int]],
) -> frozenset[tuple[int, int]]:
    """Return open target squares reachable from one fixed area origin."""

    if (
        type(origin) is not tuple
        or len(origin) != 2
        or any(
            isinstance(component, bool)
            or not isinstance(component, (int, Fraction))
            for component in origin
        )
    ):
        raise EngineInputError("area point of origin is invalid")
    exact_origin = (Fraction(origin[0]), Fraction(origin[1]))
    normalized = set()
    for square in squares:
        if (
            type(square) is not tuple
            or len(square) != 2
            or any(
                isinstance(component, bool)
                or not isinstance(component, int)
                for component in square
            )
        ):
            raise EngineInputError("area target square is invalid")
        normalized.add(square)

    solid_squares, barrier_edges = _visibility_hard_geometry(state)
    if not solid_squares and not barrier_edges:
        return frozenset(normalized)
    return _cached_squares_with_line_of_effect(
        exact_origin,
        tuple(sorted(normalized)),
        tuple(sorted(solid_squares)),
        barrier_edges,
    )


def participant_line_of_effect(
    state: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
) -> bool:
    """Return exact hard-barrier line of effect between two footprints."""

    source_id = str(source.get("id") or "")
    target_id = str(target.get("id") or "")
    if not source_id or not target_id or source_id == target_id:
        raise EngineInputError("line-of-effect participants are invalid")
    source_rectangle = _participant_rectangle(source)
    target_rectangle = _participant_rectangle(target)
    source_square_keys = {
        (int(square["x"]), int(square["y"]))
        for square in source["occupiedSquares"]
    }
    target_square_keys = {
        (int(square["x"]), int(square["y"]))
        for square in target["occupiedSquares"]
    }
    solid_squares, barrier_edges = _visibility_hard_geometry(state)
    return _cached_participant_line_of_effect(
        source_rectangle,
        target_rectangle,
        tuple(sorted(source_square_keys)),
        tuple(sorted(target_square_keys)),
        tuple(sorted(solid_squares)),
        barrier_edges,
    )


def participant_line_of_effect_around_squares(
    state: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    additional_blocked_squares: set[tuple[int, int]],
) -> bool:
    """Return whether one exact footprint ray can avoid extra square volumes."""

    if (
        not isinstance(additional_blocked_squares, set)
        or any(
            type(square) is not tuple
            or len(square) != 2
            or any(type(component) is not int for component in square)
            for square in additional_blocked_squares
        )
    ):
        raise EngineInputError(
            "additional line-of-effect squares are invalid"
        )
    source_id = str(source.get("id") or "")
    target_id = str(target.get("id") or "")
    if not source_id or not target_id or source_id == target_id:
        raise EngineInputError("line-of-effect participants are invalid")
    source_rectangle = _participant_rectangle(source)
    target_rectangle = _participant_rectangle(target)
    source_square_keys = {
        (int(square["x"]), int(square["y"]))
        for square in source["occupiedSquares"]
    }
    target_square_keys = {
        (int(square["x"]), int(square["y"]))
        for square in target["occupiedSquares"]
    }
    solid_squares, barrier_edges = _visibility_hard_geometry(state)
    return _cached_participant_line_of_effect(
        source_rectangle,
        target_rectangle,
        tuple(sorted(source_square_keys)),
        tuple(sorted(target_square_keys)),
        tuple(sorted(solid_squares)),
        barrier_edges,
        tuple(sorted(additional_blocked_squares)),
    )


def _fixed_point(value: object, label: str) -> Point:
    if (
        type(value) is not tuple
        or len(value) != 2
        or any(
            isinstance(component, bool)
            or not isinstance(component, (int, Fraction))
            for component in value
        )
    ):
        raise EngineInputError(f"{label} is invalid")
    point = (Fraction(value[0]), Fraction(value[1]))
    if point[0] < 0 or point[1] < 0:
        raise EngineInputError(f"{label} is invalid")
    return point


def participant_to_fixed_point_line_of_effect(
    state: dict[str, Any],
    source: dict[str, Any],
    target_point: Point,
) -> dict[str, Any]:
    """Return exact hard line-of-effect evidence to one fixed point.

    The source may originate the line from any point in its complete
    rectangular footprint. Creature blockers are intentionally excluded:
    line of effect is broken only by solid cells and active barrier edges.
    """

    source_id = str(source.get("id") or "")
    if not source_id:
        raise EngineInputError("line-of-effect source participant is invalid")
    endpoint = _fixed_point(target_point, "line-of-effect target point")
    source_rectangle = _participant_rectangle(source)
    source_square_keys = {
        (int(square["x"]), int(square["y"]))
        for square in source["occupiedSquares"]
    }
    solid_squares, barrier_edges = _visibility_hard_geometry(state)
    solid_squares.difference_update(source_square_keys)
    topology = _hard_topology(solid_squares, barrier_edges)
    candidates = _arrangement_candidates(
        source_rectangle,
        (endpoint, endpoint, endpoint, endpoint),
        (
            (Fraction(x), Fraction(y))
            for x, y in topology.arrangement_vertices
        ),
    )
    if _point_in_rectangle(endpoint, source_rectangle):
        candidates.add(endpoint)
    source_center = _rectangle_center(source_rectangle)
    evaluated = []
    for origin in candidates:
        hard_squares = _solid_blockers(origin, endpoint, topology)
        hard_edges = _barrier_edge_blockers(
            origin,
            endpoint,
            topology,
            source_rectangle=source_rectangle,
            target_rectangle=None,
        )
        evaluated.append(
            {
                "origin": origin,
                "hardSquares": hard_squares,
                "hardEdges": hard_edges,
            }
        )
    selected = min(
        evaluated,
        key=lambda item: (
            bool(item["hardSquares"] or item["hardEdges"]),
            len(item["hardSquares"]) + len(item["hardEdges"]),
            (
                (item["origin"][0] - source_center[0]) ** 2
                + (item["origin"][1] - source_center[1]) ** 2
            ),
            item["origin"][1],
            item["origin"][0],
        ),
    )
    line_of_effect = not bool(
        selected["hardSquares"] or selected["hardEdges"]
    )
    ray = {
        "endpoint": _point_payload(endpoint),
        "classification": "clear" if line_of_effect else "hard",
        "blockers": {
            "hard": [
                {
                    "kind": "solid-cell",
                    "square": {"x": x, "y": y},
                }
                for x, y in selected["hardSquares"]
            ] + [
                {
                    "kind": "barrier-edge",
                    "edge": _edge_payload(edge),
                }
                for edge in selected["hardEdges"]
            ],
            "soft": [],
        },
    }
    return {
        "schema": 1,
        "ruling": FIXED_POINT_LINE_OF_EFFECT_RULING,
        "sourceParticipantId": source_id,
        "sourceFootprint": _rectangle_payload(source_rectangle),
        "target": {
            "kind": "fixed-point",
            "point": _point_payload(endpoint),
        },
        "origin": _point_payload(selected["origin"]),
        "originSelection": {
            "region": "entire-source-footprint",
            "singleOriginForAllRays": True,
            "tieBreak": [
                "line-of-effect",
                "fewest-hard-blockers",
                "least-squared-distance-from-source-center",
                "lowest-y",
                "lowest-x",
            ],
        },
        "rays": [ray],
        "lineOfEffect": line_of_effect,
        "rules": {
            "lineOfEffect": dict(LINE_OF_EFFECT_RULE),
        },
    }


def _area_cover_record(
    *,
    hard_obstructed_rays: int,
    soft_obstructed_rays: int,
) -> dict[str, Any]:
    if hard_obstructed_rays >= 3:
        degree = "greater"
        reflex_bonus = 4
    elif hard_obstructed_rays == 2:
        degree = "standard"
        reflex_bonus = 2
    elif hard_obstructed_rays == 1 or soft_obstructed_rays:
        degree = "lesser"
        reflex_bonus = 0
    else:
        degree = "none"
        reflex_bonus = 0
    return {
        "degree": degree,
        "reflexSaveCircumstanceBonus": reflex_bonus,
        "obstructedRays": hard_obstructed_rays + soft_obstructed_rays,
        "hardObstructedRays": hard_obstructed_rays,
        "softObstructedRays": soft_obstructed_rays,
        "rule": dict(COVER_RULE),
    }


def fixed_origin_area_target_geometry(
    state: dict[str, Any],
    origin: Point,
    target: dict[str, Any],
) -> dict[str, Any]:
    """Return exact fixed-origin line-of-effect and area-cover evidence.

    Every cover degree is executable. Standard and greater cover carry their
    recorded +2 or +4 circumstance bonus to Reflex saves against the area;
    complete hard occlusion still fails line of effect.
    """

    exact_origin = _fixed_point(origin, "area point of origin")
    target_id = str(target.get("id") or "")
    if not target_id:
        raise EngineInputError("area target participant is invalid")
    target_rectangle = _participant_rectangle(target)
    target_square_keys = {
        (int(square["x"]), int(square["y"]))
        for square in target["occupiedSquares"]
    }
    solid_squares, barrier_edges = _visibility_hard_geometry(state)
    solid_squares.difference_update(target_square_keys)
    hard_topology = _hard_topology(solid_squares, barrier_edges)
    soft_blockers = tuple(
        _SoftBlocker(
            participant_id=str(participant["id"]),
            rectangle=_participant_rectangle(participant),
        )
        for participant in sorted(
            state.get("participants") or [],
            key=lambda item: str(item.get("id") or ""),
        )
        if str(participant.get("id") or "") != target_id
    )
    target_corners = _rectangle_corners(target_rectangle)
    rays = [
        _ray_evidence(
            exact_origin,
            endpoint,
            corner_name,
            hard_topology,
            soft_blockers,
            None,
            target_rectangle,
        )
        for corner_name, endpoint in zip(_CORNER_NAMES, target_corners)
    ]
    hard_obstructed = sum(
        ray["classification"] == "hard"
        for ray in rays
    )
    soft_obstructed = sum(
        ray["classification"] == "soft"
        for ray in rays
    )
    line_of_effect = any(
        ray["classification"] != "hard"
        for ray in rays
    )
    cover = _area_cover_record(
        hard_obstructed_rays=hard_obstructed,
        soft_obstructed_rays=soft_obstructed,
    )
    resolution_supported = line_of_effect
    unsupported_reason = (
        None
        if resolution_supported
        else "no-line-of-effect"
    )
    return {
        "schema": 1,
        "ruling": FIXED_ORIGIN_AREA_COVER_RULING,
        "source": {
            "kind": "fixed-area-origin",
            "point": _point_payload(exact_origin),
        },
        "targetParticipantId": target_id,
        "targetFootprint": _rectangle_payload(target_rectangle),
        "origin": _point_payload(exact_origin),
        "rays": rays,
        "cover": cover,
        "lineOfEffect": line_of_effect,
        "resolutionSupported": resolution_supported,
        "unsupportedReason": unsupported_reason,
        "rules": {
            "cover": dict(COVER_RULE),
            "lineOfEffect": dict(LINE_OF_EFFECT_RULE),
        },
    }


def _ray_evidence(
    origin: Point,
    endpoint: Point,
    corner_name: str,
    hard_topology: _HardTopology,
    soft_blockers: tuple[_SoftBlocker, ...],
    source_rectangle: Rectangle | None,
    target_rectangle: Rectangle,
) -> dict[str, Any]:
    hard_squares = _solid_blockers(origin, endpoint, hard_topology)
    hard_edges = _barrier_edge_blockers(
        origin,
        endpoint,
        hard_topology,
        source_rectangle=source_rectangle,
        target_rectangle=target_rectangle,
    )
    soft = [
        blocker.participant_id
        for blocker in soft_blockers
        if _open_segment_intersects_open_rectangle(
            origin,
            endpoint,
            blocker.rectangle,
        )
    ]
    classification = (
        "hard"
        if hard_squares or hard_edges
        else "soft"
        if soft
        else "clear"
    )
    return {
        "targetCorner": corner_name,
        "endpoint": _point_payload(endpoint),
        "classification": classification,
        "blockers": {
            "hard": [
                {
                    "kind": "solid-cell",
                    "square": {"x": x, "y": y},
                }
                for x, y in hard_squares
            ] + [
                {
                    "kind": "barrier-edge",
                    "edge": _edge_payload(edge),
                }
                for edge in hard_edges
            ],
            "soft": [
                {
                    "kind": "participant",
                    "participantId": participant_id,
                }
                for participant_id in soft
            ],
        },
    }


def _cover_record(obstructed_rays: int) -> dict[str, Any]:
    degrees = {
        0: ("none", 0),
        1: ("lesser", 1),
        2: ("standard", 2),
        3: ("greater", 4),
        4: ("greater", 4),
    }
    degree, bonus = degrees[obstructed_rays]
    return {
        "degree": degree,
        "armorClassBonus": bonus,
        "obstructedRays": obstructed_rays,
        "rule": dict(COVER_RULE),
    }


def _projectile_ray_index(
    origin: Point,
    target_center: Point,
    target_corners: tuple[Point, Point, Point, Point],
    rays: list[dict[str, Any]],
) -> int:
    center_vector = (
        target_center[0] - origin[0],
        target_center[1] - origin[1],
    )

    def key(index: int) -> tuple[int, Fraction, int]:
        corner = target_corners[index]
        corner_vector = (
            corner[0] - origin[0],
            corner[1] - origin[1],
        )
        cross = (
            center_vector[0] * corner_vector[1]
            - center_vector[1] * corner_vector[0]
        )
        length_squared = (
            corner_vector[0] * corner_vector[0]
            + corner_vector[1] * corner_vector[1]
        )
        return (
            0 if rays[index]["classification"] == "clear" else 1,
            cross * cross / length_squared,
            index,
        )

    eligible = [
        index
        for index, ray in enumerate(rays)
        if (
            ray["classification"] != "hard"
            and target_corners[index] != origin
        )
    ]
    if not eligible:
        raise EngineInputError("ranged Strike has no nondegenerate projectile ray")
    return min(eligible, key=key)


def _ranged_attack_geometry_uncached(
    state: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    solid_squares_override: tuple[tuple[int, int], ...] | None = None,
    barrier_edges_override: tuple[Edge, ...] | None = None,
) -> dict[str, Any]:
    """Return exact cover and projectile evidence for one ranged Strike."""

    source_id = str(source.get("id") or "")
    target_id = str(target.get("id") or "")
    if not source_id or not target_id or source_id == target_id:
        raise EngineInputError("ranged attack participants are invalid")
    source_rectangle = _participant_rectangle(source)
    target_rectangle = _participant_rectangle(target)
    source_square_keys = {
        (int(square["x"]), int(square["y"]))
        for square in source["occupiedSquares"]
    }
    target_square_keys = {
        (int(square["x"]), int(square["y"]))
        for square in target["occupiedSquares"]
    }
    if solid_squares_override is None or barrier_edges_override is None:
        state_squares, state_edges = _visibility_hard_geometry(state)
    else:
        state_squares, state_edges = set(), ()
    solid_squares = (
        state_squares
        if solid_squares_override is None
        else set(solid_squares_override)
    )
    solid_squares.difference_update(source_square_keys)
    solid_squares.difference_update(target_square_keys)
    barrier_edges = (
        state_edges
        if barrier_edges_override is None
        else barrier_edges_override
    )
    hard_topology = _hard_topology(solid_squares, barrier_edges)

    corridor = (
        min(source_rectangle[0], target_rectangle[0]),
        min(source_rectangle[1], target_rectangle[1]),
        max(source_rectangle[2], target_rectangle[2]),
        max(source_rectangle[3], target_rectangle[3]),
    )
    soft_blockers = tuple(
        _SoftBlocker(
            participant_id=str(participant["id"]),
            rectangle=_participant_rectangle(participant),
        )
        for participant in sorted(
            state.get("participants") or [],
            key=lambda item: str(item.get("id") or ""),
        )
        if str(participant.get("id") or "") not in {source_id, target_id}
        and _open_rectangles_overlap(
            _participant_rectangle(participant),
            corridor,
        )
    )
    target_corners = _rectangle_corners(target_rectangle)
    blocker_points = [
        (Fraction(x), Fraction(y))
        for x, y in hard_topology.arrangement_vertices
    ]
    blocker_points.extend(
        point
        for blocker in soft_blockers
        for point in _rectangle_corners(blocker.rectangle)
    )
    candidates = _arrangement_candidates(
        source_rectangle,
        target_corners,
        blocker_points,
    )
    evaluated = []
    for origin in candidates:
        rays = [
            _ray_evidence(
                origin,
                endpoint,
                corner_name,
                hard_topology,
                soft_blockers,
                source_rectangle,
                target_rectangle,
            )
            for corner_name, endpoint in zip(_CORNER_NAMES, target_corners)
        ]
        evaluated.append(
            {
                "origin": origin,
                "rays": rays,
                "obstructed": sum(
                    ray["classification"] != "clear"
                    for ray in rays
                ),
                "hasNonHardRay": any(
                    ray["classification"] != "hard"
                    and endpoint != origin
                    for ray, endpoint in zip(rays, target_corners)
                ),
            }
        )
    source_center = _rectangle_center(source_rectangle)

    def origin_key(item: dict[str, Any]) -> tuple[int, Fraction, Fraction, Fraction]:
        origin = item["origin"]
        return (
            int(item["obstructed"]),
            (
                (origin[0] - source_center[0]) ** 2
                + (origin[1] - source_center[1]) ** 2
            ),
            origin[1],
            origin[0],
        )

    legal_origins = [item for item in evaluated if item["hasNonHardRay"]]
    line_of_effect = bool(legal_origins)
    selected = min(legal_origins or evaluated, key=origin_key)
    origin = selected["origin"]
    rays = selected["rays"]
    cover = _cover_record(int(selected["obstructed"])) if line_of_effect else None
    projectile = None
    if line_of_effect:
        projectile_index = _projectile_ray_index(
            origin,
            _rectangle_center(target_rectangle),
            target_corners,
            rays,
        )
        projectile_ray = rays[projectile_index]
        projectile = {
            "origin": _point_payload(origin),
            "endpoint": dict(projectile_ray["endpoint"]),
            "targetCorner": projectile_ray["targetCorner"],
            "rayClassification": projectile_ray["classification"],
        }
    return {
        "schema": 1,
        "ruling": RANGED_COVER_RULING,
        "sourceParticipantId": source_id,
        "targetParticipantId": target_id,
        "sourceFootprint": _rectangle_payload(source_rectangle),
        "targetFootprint": _rectangle_payload(target_rectangle),
        "origin": _point_payload(origin),
        "originSelection": {
            "region": "entire-source-footprint",
            "singleOriginForAllRays": True,
            "tieBreak": [
                "least-cover",
                "least-squared-distance-from-source-center",
                "lowest-y",
                "lowest-x",
            ],
        },
        "rays": rays,
        "cover": cover,
        "lineOfEffect": line_of_effect,
        "projectile": projectile,
        "rules": {
            "cover": dict(COVER_RULE),
            "lineOfEffect": dict(LINE_OF_EFFECT_RULE),
        },
    }


def _rectangle_participant(
    participant_id: str,
    rectangle: Rectangle,
) -> dict[str, Any]:
    left, top, right, bottom = rectangle
    return {
        "id": participant_id,
        "occupiedSquares": [
            {"x": x, "y": y}
            for y in range(top, bottom)
            for x in range(left, right)
        ],
    }


@lru_cache(maxsize=2_048)
def _cached_ranged_attack_geometry(
    source_id: str,
    target_id: str,
    source_rectangle: Rectangle,
    target_rectangle: Rectangle,
    solid_squares: tuple[tuple[int, int], ...],
    barrier_edges: tuple[Edge, ...],
    participant_rectangles: tuple[tuple[str, Rectangle], ...],
    arrangement_limit: int,
) -> dict[str, Any]:
    # arrangement_limit is part of the cache identity so bounded tests and
    # deliberate runtime tuning cannot reuse a result from a different cap.
    del arrangement_limit
    return _ranged_attack_geometry_uncached(
        {
            "map": {},
            "participants": [
                _rectangle_participant(participant_id, rectangle)
                for participant_id, rectangle in participant_rectangles
            ],
        },
        _rectangle_participant(source_id, source_rectangle),
        _rectangle_participant(target_id, target_rectangle),
        solid_squares_override=solid_squares,
        barrier_edges_override=barrier_edges,
    )


def ranged_attack_geometry(
    state: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any]:
    """Return exact cover and projectile evidence for one ranged Strike."""

    source_id = str(source.get("id") or "")
    target_id = str(target.get("id") or "")
    if not source_id or not target_id or source_id == target_id:
        raise EngineInputError("ranged attack participants are invalid")
    source_rectangle = _participant_rectangle(source)
    target_rectangle = _participant_rectangle(target)
    hard_squares, barrier_edges = _visibility_hard_geometry(state)
    solid_squares = tuple(
        sorted(
            hard_squares,
            key=lambda item: (item[1], item[0]),
        )
    )
    participant_rectangles = tuple(
        sorted(
            (
                (
                    str(participant.get("id") or ""),
                    _participant_rectangle(participant),
                )
                for participant in state.get("participants") or []
            ),
            key=lambda item: item[0],
        )
    )
    return deepcopy(
        _cached_ranged_attack_geometry(
            source_id,
            target_id,
            source_rectangle,
            target_rectangle,
            solid_squares,
            barrier_edges,
            participant_rectangles,
            int(MAX_ARRANGEMENT_LINES),
        )
    )


__all__ = [
    "COVER_RULE",
    "FIXED_ORIGIN_AREA_COVER_RULING",
    "FIXED_POINT_LINE_OF_EFFECT_RULING",
    "LINE_OF_EFFECT_RULE",
    "RANGED_COVER_RULING",
    "fixed_origin_area_target_geometry",
    "participant_line_of_effect",
    "participant_line_of_effect_around_squares",
    "participant_to_fixed_point_line_of_effect",
    "ranged_attack_geometry",
    "squares_with_line_of_effect_from_point",
]

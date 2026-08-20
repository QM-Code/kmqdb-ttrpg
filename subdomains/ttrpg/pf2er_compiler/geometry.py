"""Foundation-only square-grid scalar and coordinate primitives."""

from __future__ import annotations

from typing import Any

from .errors import EngineInputError


def strict_integer(
    value: Any,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineInputError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise EngineInputError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise EngineInputError(f"{label} must be at most {maximum}")
    return value


def coordinate(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise EngineInputError(f"{label} must be an object")
    return {
        "x": strict_integer(value.get("x"), f"{label}.x", minimum=0),
        "y": strict_integer(value.get("y"), f"{label}.y", minimum=0),
    }


def coordinate_key(value: dict[str, int]) -> tuple[int, int]:
    return value["x"], value["y"]


def grid_distance_feet(
    first: dict[str, int],
    second: dict[str, int],
) -> int:
    """Measure square-grid distance with alternating 5/10-foot diagonals."""

    delta_x = abs(first["x"] - second["x"])
    delta_y = abs(first["y"] - second["y"])
    diagonals = min(delta_x, delta_y)
    straight = max(delta_x, delta_y) - diagonals
    return straight * 5 + (diagonals // 2) * 15 + (diagonals % 2) * 5


def square_is_inside(
    square: dict[str, int],
    grid: dict[str, Any],
) -> bool:
    return (
        0 <= square["x"] < grid["width"]
        and 0 <= square["y"] < grid["height"]
    )


__all__ = [
    "coordinate",
    "coordinate_key",
    "grid_distance_feet",
    "square_is_inside",
    "strict_integer",
]

"""Small fail-closed conversions for values captured from source text."""

from __future__ import annotations

import re
from typing import Any


MIN_SOURCE_INTEGER = -(1 << 63)
MAX_SOURCE_INTEGER = (1 << 63) - 1

_SIGNED_DECIMAL_RE = re.compile(
    r"^(?P<sign>[+-]?)(?P<digits>[0-9]+)$",
    re.ASCII,
)


def parse_decimal_integer(value: object) -> int | None:
    """Return one exact signed-64-bit ASCII decimal, or ``None``.

    Bounds are checked lexically before conversion.  The result therefore
    never depends on the interpreter's configurable decimal-digit limit.
    Leading zeros and an explicit sign are retained as accepted source forms,
    but callers never receive a value outside SQLite's signed integer range.
    """

    if not isinstance(value, str):
        return None
    match = _SIGNED_DECIMAL_RE.fullmatch(value)
    if match is None:
        return None

    sign = match.group("sign")
    digits = match.group("digits").lstrip("0") or "0"
    boundary = (
        str(abs(MIN_SOURCE_INTEGER))
        if sign == "-"
        else str(MAX_SOURCE_INTEGER)
    )
    if len(digits) > len(boundary) or (
        len(digits) == len(boundary) and digits > boundary
    ):
        return None

    magnitude = int(digits)
    return -magnitude if sign == "-" else magnitude


def reviewed_giant_ant_venom_source(source: Any, /) -> bool | None:
    """Return exactness for the one reviewed Giant Ant Venom source."""

    normalized_name = " ".join(
        str(getattr(source, "creature_name", "")).split()
    ).casefold()
    identity = (
        getattr(source, "source_id", None),
        getattr(source, "locator", None),
        normalized_name,
        str(getattr(source, "source_label", "")).casefold(),
    )
    if identity != (
        "core-mc1",
        "21.3",
        "giant ant",
        "giant ant venom",
    ):
        return None
    description = (
        "(poison) Saving Throw DC 18 Fortitude; Maximum Duration 4 rounds; "
        "Stage 1 1d8 poison and enfeebled 1 (1 round); Stage 2 1d10 poison "
        "and enfeebled 2 (1 round); Stage 3 1d12 poison and enfeebled 3 "
        "(1 round)"
    )
    raw_member = getattr(source, "raw_member", None)
    return (
        getattr(source, "kind", None) == "passive"
        and getattr(source, "action_cost", None) is None
        and getattr(source, "traits", None) == ()
        and not getattr(source, "trigger", None)
        and getattr(source, "description", None) == description
        and getattr(raw_member, "key", None) == "!.Giant Ant Venom"
        and getattr(raw_member, "value", None) == description
    )


__all__ = [
    "MAX_SOURCE_INTEGER",
    "MIN_SOURCE_INTEGER",
    "parse_decimal_integer",
]

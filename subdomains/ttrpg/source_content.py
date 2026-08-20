"""Pure, duplicate-preserving validation for cached source content.

This module intentionally does not import ``rules_engine``.  Both the cache
producer and the rules engine use it before treating exact library text as
source authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import TypeAlias, final


MAX_IDENTIFIER_BYTES = 4_096
MAX_MANIFEST_SOURCES = 4_096
MAX_MANIFEST_SECTIONS = 100_000
MAX_PATH_STEPS = 256
MAX_RAW_DEPTH = 128
MAX_RAW_NODES = 500_000
MAX_RAW_BYTES = 64 * 1024 * 1024
MAX_ROW_BYTES = 128 * 1024 * 1024


class SourceContentError(ValueError):
    """Exact cached source text is malformed or exceeds a hard bound."""


@final
@dataclass(frozen=True, slots=True)
class ValidatedSourceMember:
    key: str
    value: ValidatedSourceValue

    def __post_init__(self) -> None:
        if type(self) is not ValidatedSourceMember:
            raise TypeError(
                "ValidatedSourceMember subclasses are not supported"
            )
        if type(self.key) is not str:
            raise TypeError("validated source member key must be exact str")


@final
@dataclass(frozen=True, slots=True)
class ValidatedSourceArray:
    items: tuple[ValidatedSourceValue, ...]

    def __post_init__(self) -> None:
        if type(self) is not ValidatedSourceArray:
            raise TypeError(
                "ValidatedSourceArray subclasses are not supported"
            )
        if type(self.items) is not tuple:
            raise TypeError("validated source array items must be exact tuple")


@final
@dataclass(frozen=True, slots=True)
class ValidatedSourceObject:
    members: tuple[ValidatedSourceMember, ...]

    def __post_init__(self) -> None:
        if type(self) is not ValidatedSourceObject:
            raise TypeError(
                "ValidatedSourceObject subclasses are not supported"
            )
        if (
            type(self.members) is not tuple
            or any(
                type(member) is not ValidatedSourceMember
                for member in self.members
            )
        ):
            raise TypeError(
                "validated source object members must be exact members"
            )


ValidatedSourcePrimitive: TypeAlias = str | int | float | bool | None
ValidatedSourceValue: TypeAlias = (
    ValidatedSourcePrimitive
    | ValidatedSourceArray
    | ValidatedSourceObject
)


def _reject_constant(value: str) -> None:
    raise SourceContentError(
        f"non-finite source content number is invalid: {value}"
    )


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise SourceContentError(
            f"source content number overflows a finite float: {value}"
        )
    return result


def _object_pairs(
    pairs: list[tuple[str, object]],
) -> ValidatedSourceObject:
    if type(pairs) is not list:
        raise TypeError("source object pairs must be an exact list")
    return ValidatedSourceObject(
        tuple(
            ValidatedSourceMember(key, value)
            for key, value in pairs
        )
    )


def _freeze(
    value: object,
    *,
    depth: int = 0,
    counter: list[int] | None = None,
) -> ValidatedSourceValue:
    if counter is None:
        counter = [0]
    if depth > MAX_RAW_DEPTH:
        raise SourceContentError(
            "source content exceeds its depth bound"
        )
    counter[0] += 1
    if counter[0] > MAX_RAW_NODES:
        raise SourceContentError(
            "source content exceeds its node bound"
        )
    value_type = type(value)
    if value_type is ValidatedSourceObject:
        return ValidatedSourceObject(
            tuple(
                ValidatedSourceMember(
                    member.key,
                    _freeze(
                        member.value,
                        depth=depth + 1,
                        counter=counter,
                    ),
                )
                for member in value.members
            )
        )
    if value_type is list:
        return ValidatedSourceArray(
            tuple(
                _freeze(
                    item,
                    depth=depth + 1,
                    counter=counter,
                )
                for item in value
            )
        )
    if value is None or value_type in {bool, int, str}:
        return value
    if value_type is float:
        if not math.isfinite(value):
            raise SourceContentError(
                "source content numbers must be finite"
            )
        return value
    raise SourceContentError(
        "source content contains a subclassed or unsupported value: "
        f"{value_type.__name__}"
    )


class _Writer:
    __slots__ = ("body", "nodes")

    def __init__(self) -> None:
        self.body = bytearray()
        self.nodes = 0

    def append(self, value: str | bytes) -> None:
        if type(value) is str:
            try:
                encoded = str.encode(value, "utf-8")
            except UnicodeEncodeError as failure:
                raise SourceContentError(
                    "source content contains invalid UTF-8 text"
                ) from failure
        elif type(value) is bytes:
            encoded = value
        else:
            raise TypeError("source content writer requires exact str/bytes")
        if len(self.body) + len(encoded) > MAX_RAW_BYTES:
            raise SourceContentError(
                "canonical source content exceeds its byte bound"
            )
        self.body.extend(encoded)

    def node(self, depth: int) -> None:
        if depth > MAX_RAW_DEPTH:
            raise SourceContentError(
                "canonical source content exceeds its depth bound"
            )
        self.nodes += 1
        if self.nodes > MAX_RAW_NODES:
            raise SourceContentError(
                "canonical source content exceeds its node bound"
            )


def _write(
    value: ValidatedSourceValue,
    writer: _Writer,
    depth: int,
) -> None:
    writer.node(depth)
    value_type = type(value)
    if value_type is ValidatedSourceObject:
        writer.append(b"{")
        for index, member in enumerate(value.members):
            if type(member) is not ValidatedSourceMember:
                raise TypeError(
                    "canonical source content requires exact members"
                )
            if index:
                writer.append(b",")
            writer.append(
                json.dumps(
                    member.key,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            writer.append(b":")
            _write(member.value, writer, depth + 1)
        writer.append(b"}")
        return
    if value_type is ValidatedSourceArray:
        writer.append(b"[")
        for index, item in enumerate(value.items):
            if index:
                writer.append(b",")
            _write(item, writer, depth + 1)
        writer.append(b"]")
        return
    if value is None or value_type in {bool, int, float, str}:
        if value_type is float and not math.isfinite(value):
            raise SourceContentError(
                "canonical source content numbers must be finite"
            )
        try:
            writer.append(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
        except (TypeError, ValueError) as failure:
            raise SourceContentError(
                "canonical source content primitive is invalid"
            ) from failure
        return
    raise TypeError(
        "canonical source content value is invalid: "
        f"{value_type.__name__}"
    )


def canonical_source_content_bytes(
    value: ValidatedSourceObject,
    /,
) -> bytes:
    """Encode one validated root while preserving order and duplicates."""

    if type(value) is not ValidatedSourceObject:
        raise TypeError(
            "canonical source content requires ValidatedSourceObject"
        )
    writer = _Writer()
    _write(value, writer, 0)
    return bytes(writer.body)


def validate_source_content(
    value: str,
    /,
) -> ValidatedSourceObject | None:
    """Validate exact section content and return its immutable raw tree.

    The exact empty string returns ``None`` as the authenticated no-content
    sentinel.  Every nonempty input must be a JSON object.  Duplicate object
    members are retained in their original order.
    """

    if type(value) is not str:
        raise TypeError("source content must be exact stored text")
    if not value:
        return None
    try:
        encoded = str.encode(value, "utf-8")
    except UnicodeEncodeError as failure:
        raise SourceContentError(
            "source content contains invalid UTF-8 text"
        ) from failure
    if len(encoded) > MAX_RAW_BYTES:
        raise SourceContentError(
            "source content exceeds its byte bound"
        )
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except SourceContentError:
        raise
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
        RecursionError,
    ) as failure:
        raise SourceContentError(
            "source content is not strict duplicate-preserving JSON"
        ) from failure
    if type(parsed) is not ValidatedSourceObject:
        raise SourceContentError(
            "nonempty source content must be a JSON object"
        )
    frozen = _freeze(parsed)
    if type(frozen) is not ValidatedSourceObject:
        raise SourceContentError(
            "nonempty source content must freeze as an object"
        )
    canonical_source_content_bytes(frozen)
    return frozen


__all__ = [
    "MAX_IDENTIFIER_BYTES",
    "MAX_MANIFEST_SECTIONS",
    "MAX_MANIFEST_SOURCES",
    "MAX_PATH_STEPS",
    "MAX_RAW_BYTES",
    "MAX_RAW_DEPTH",
    "MAX_RAW_NODES",
    "MAX_ROW_BYTES",
    "SourceContentError",
    "ValidatedSourceArray",
    "ValidatedSourceMember",
    "ValidatedSourceObject",
    "ValidatedSourcePrimitive",
    "ValidatedSourceValue",
    "canonical_source_content_bytes",
    "validate_source_content",
]

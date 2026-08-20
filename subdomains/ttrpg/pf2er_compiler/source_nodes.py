"""Duplicate-preserving PF2ER source-node and source-field primitives."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from . import errors as _errors


SIGNED_INTEGER_RE = re.compile(r"^([+-]?\d+)$")


class OrderedObject:
    """JSON object represented as ordered, duplicate-preserving pairs."""

    def __init__(self, pairs: Iterable[tuple[str, Any]]):
        self.pairs = tuple((str(key), value) for key, value in pairs)

    def values(self, key: str) -> list[Any]:
        return [value for candidate, value in self.pairs if candidate == key]

    def unique(self, key: str, *, required: bool = True, default: Any = None) -> Any:
        matches = self.values(key)
        if len(matches) > 1:
            raise _errors.EngineInputError(f"source field is duplicated: {key}")
        if not matches:
            if required:
                raise _errors.EngineInputError(f"source field is missing: {key}")
            return default
        return matches[0]


def ordered_json(value: str, label: str) -> OrderedObject:
    try:
        result = json.loads(str(value), object_pairs_hook=OrderedObject)
    except (TypeError, json.JSONDecodeError) as failure:
        raise _errors.EngineInputError(f"{label} is not valid ordered JSON") from failure
    if not isinstance(result, OrderedObject):
        raise _errors.EngineInputError(f"{label} must be an object")
    return result


def semantic_key(raw_key: str) -> str:
    if raw_key.startswith("^."):
        parts = raw_key.split(".", 2)
        return parts[2] if len(parts) == 3 else raw_key
    if len(raw_key) > 2 and raw_key[1] == "." and raw_key[0] in "!%@#":
        return raw_key[2:]
    return raw_key


def object_child(node: OrderedObject, label: str) -> Any:
    exact = node.values(label)
    matches = exact or [value for key, value in node.pairs if semantic_key(key) == label]
    if len(matches) != 1:
        raise _errors.EngineInputError(f"source content path is not unique at: {label}")
    return matches[0]


def content_target(content: str, content_path: list[str]) -> OrderedObject:
    current: Any = ordered_json(content, "source content")
    for part in content_path:
        if not isinstance(current, OrderedObject):
            raise _errors.EngineInputError(
                f"source content path does not resolve through: {part}"
            )
        current = object_child(current, str(part))
    if not isinstance(current, OrderedObject):
        raise _errors.EngineInputError("source content target is not an object")
    return current


def plain_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, OrderedObject):
        raise _errors.EngineInputError(f"{label} must be an object")
    result: dict[str, Any] = {}
    for key, item in value.pairs:
        if key in result:
            raise _errors.EngineInputError(f"{label} field is duplicated: {key}")
        result[key] = plain_value(item, f"{label}.{key}")
    return result


def plain_value(value: Any, label: str) -> Any:
    if isinstance(value, OrderedObject):
        return plain_mapping(value, label)
    if isinstance(value, list):
        return [plain_value(item, f"{label}[]") for item in value]
    return value


def integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise _errors.EngineInputError(f"{label} must be an integer")
    if isinstance(value, int):
        return value
    match = SIGNED_INTEGER_RE.fullmatch(str(value).strip())
    if not match:
        raise _errors.EngineInputError(f"{label} must be an integer")
    return int(match.group(1))


def string_list(value: Any, label: str) -> list[str]:
    if value in (None, ""):
        return []
    values = value if isinstance(value, list) else [value]
    result = [str(item).strip() for item in values]
    if any(not item for item in result):
        raise _errors.EngineInputError(f"{label} contains an empty value")
    return result


def source_flow_text(value: Any, label: str) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, OrderedObject):
        raise _errors.EngineInputError(f"{label} must be text or paragraph flow")
    paragraphs = []
    for key, item in value.pairs:
        if key != "~.p" or not isinstance(item, str):
            raise _errors.EngineInputError(
                f"{label} contains unsupported source flow: {key}"
            )
        paragraphs.append(item.strip())
    if not paragraphs or any(not paragraph for paragraph in paragraphs):
        raise _errors.EngineInputError(f"{label} contains an empty paragraph")
    return "\n\n".join(paragraphs)


def action_cost(value: Any) -> int | str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().casefold()
    costs: dict[str, int | str] = {
        "single": 1,
        "one": 1,
        "double": 2,
        "two": 2,
        "triple": 3,
        "three": 3,
        "reaction": "reaction",
    }
    if normalized not in costs:
        raise _errors.EngineInputError(
            f"creature ability action cost is not understood: {value}"
        )
    return costs[normalized]


def ability_description(value: Any) -> tuple[int | str | None, str, list[str], str]:
    if isinstance(value, str):
        return None, value.strip(), [], ""
    if not isinstance(value, OrderedObject):
        raise _errors.EngineInputError("creature ability must be an object or string")
    fields: dict[str, Any] = {}
    for key, item in value.pairs:
        if key in fields:
            raise _errors.EngineInputError(
                f"creature ability field is duplicated: {key}"
            )
        fields[key] = item
    description_text = source_flow_text(
        fields.get("Description", ""),
        "creature ability Description",
    )
    traits = [
        trait.casefold()
        for trait in string_list(
            plain_value(fields.get("Traits"), "creature ability Traits"),
            "creature ability Traits",
        )
    ]
    trigger = str(fields.get("Trigger") or "").strip()
    return action_cost(fields.get("Action")), description_text, traits, trigger

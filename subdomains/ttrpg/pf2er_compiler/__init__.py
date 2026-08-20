"""TTRPG-owned PF2ER source and semantic compiler package.

The package deliberately excludes live encounters, mutable game state,
transitions, replay, and transcript rendering.  Public compiler exports
resolve lazily so importing a source contract or registry builder does not
initialize the complete PF2ER compiler composition.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "EngineInputError": ".errors",
    "EngineTransitionError": ".errors",
    "REQUIRED_CORE_SOURCES": ".battlemap",
    "build_battleground": ".battlemap",
    "build_semantic_battleground": ".battlemap",
    "compile_source_creature": ".source",
    "source_creature_description": ".source",
    "compile_equipment_catalog": ".equipment",
    "grid_distance_feet": ".battlemap",
    "selected_source_ids": ".battlemap",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()).union(__all__))

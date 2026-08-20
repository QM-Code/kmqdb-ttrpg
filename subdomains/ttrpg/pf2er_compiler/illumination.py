"""PF2ER light production and viewer-relative perception consequences.

Scenario-authored ambient light, fixed point sources, and admitted equipment
sources produce one complete resolved-illumination field. Mechanical light
levels and exact display RGB remain independent, while reachable source colors
mix deterministically in the engine. In the absence of any ambient light or
active source, an encounter is in ordinary `[0, 0, 0]` darkness. Resolved
illumination remains the consumer boundary used by perception, targeting,
movement, and public presentation.

The rules do not say how a creature whose footprint crosses more than one
light level is treated.  Mixed-footprint evaluation therefore fails closed
instead of silently selecting the best or worst occupied square.
"""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import re
from typing import Any, Callable

from .geometry import (
    coordinate,
    coordinate_key,
    grid_distance_feet,
    square_is_inside,
)
from .errors import EngineInputError
from .mechanics import flash_beetle as _flash_beetle
from .mechanics import scarecrow as _scarecrow
from .ranged_cover import squares_with_line_of_effect_from_point


ILLUMINATION_SCHEMA = 2
ILLUMINATION_KIND = "pf2er-resolved-illumination"
LIGHT_PRODUCTION_SCHEMA = 2
LIGHT_PRODUCTION_KIND = "pf2er-light-production"
LIGHT_LEVELS = ("bright", "dim", "darkness")
LIGHT_LEVEL_RULE = {"sourceId": "core-pc1", "locator": "432.2"}
BRIGHT_LIGHT_RULE = {"sourceId": "core-pc1", "locator": "432.3"}
DIM_LIGHT_RULE = {"sourceId": "core-pc1", "locator": "432.4"}
DARKNESS_RULE = {"sourceId": "core-pc1", "locator": "432.5"}
TORCH_RULE = {"sourceId": "core-pc1", "locator": "287.5"}
LIGHT_SPELL_RULE = {"sourceId": "core-pc1", "locator": "340.8"}
DARKVISION_RULE = {"sourceId": "core-pc1", "locator": "433.5"}
LOW_LIGHT_VISION_RULE = {"sourceId": "core-pc1", "locator": "433.7"}
OBSERVED_RULE = {"sourceId": "core-pc1", "locator": "434.2"}
HIDDEN_RULE = {"sourceId": "core-pc1", "locator": "434.3"}
UNDETECTED_RULE = {"sourceId": "core-pc1", "locator": "434.4"}
CONCEALED_RULE = {"sourceId": "core-pc1", "locator": "434.6"}
BLINDED_RULE = {"sourceId": "core-pc1", "locator": "442.6"}
DARKNESS_SPELL_RULE = {"sourceId": "core-pc1", "locator": "322.5"}

_RULES = {
    "lightLevels": LIGHT_LEVEL_RULE,
    "brightLight": BRIGHT_LIGHT_RULE,
    "dimLight": DIM_LIGHT_RULE,
    "darkness": DARKNESS_RULE,
}
_LIGHT_PRODUCTION_RULES = {
    **_RULES,
    "torch": TORCH_RULE,
    "lightSpell": LIGHT_SPELL_RULE,
}
_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ACTIVE_SOURCE_ID_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$"
)
_AWARENESS_STATES = {
    "observed",
    "hidden",
    "undetected",
    "unnoticed",
}
_DETECTION_RANK = {
    "observed": 0,
    "hidden": 1,
    "undetected": 2,
    "unnoticed": 3,
}


def _display_rgb(value: Any, label: str) -> list[int]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(
            isinstance(channel, bool)
            or not isinstance(channel, int)
            or not 0 <= channel <= 255
            for channel in value
        )
    ):
        raise EngineInputError(
            f"{label} must contain three integer channels from 0 to 255"
        )
    return [int(channel) for channel in value]


def _source_ids(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(
            not isinstance(source_id, str)
            or not _ACTIVE_SOURCE_ID_RE.fullmatch(source_id)
            for source_id in value
        )
        or value != sorted(set(value))
    ):
        raise EngineInputError(
            f"{label} must be a sorted array of unique light-source ids"
        )
    return [str(source_id) for source_id in value]


def _light_value(
    value: Any,
    label: str,
    *,
    resolved: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EngineInputError(f"{label} must be an object")
    level = value.get("rulesLevel")
    if level not in LIGHT_LEVELS:
        raise EngineInputError(
            f"{label}.rulesLevel must be bright, dim, or darkness"
        )
    expected = {"rulesLevel", "displayRgb"}
    if resolved:
        expected.add("sourceIds")
    if level != "darkness":
        if set(value) != expected:
            raise EngineInputError(
                f"{label} {level} light contains unsupported fields"
            )
        result = {
            "rulesLevel": str(level),
            "displayRgb": _display_rgb(
                value.get("displayRgb"),
                f"{label}.displayRgb",
            ),
        }
        if resolved:
            result["sourceIds"] = _source_ids(
                value.get("sourceIds"),
                f"{label}.sourceIds",
            )
        return result
    darkness = value.get("darkness")
    if not isinstance(darkness, dict):
        raise EngineInputError(
            f"{label}.darkness must describe ordinary or magical darkness"
        )
    darkness_kind = darkness.get("kind")
    if darkness_kind == "ordinary":
        if set(darkness) != {"kind"} or set(value) != {
            *expected,
            "darkness",
        }:
            raise EngineInputError(
                f"{label} ordinary darkness contains unsupported fields"
            )
        normalized_darkness = {"kind": "ordinary"}
    elif darkness_kind == "magical":
        rank = darkness.get("rank")
        profile = darkness.get("profile")
        if (
            set(darkness) != {"kind", "rank", "profile"}
            or isinstance(rank, bool)
            or not isinstance(rank, int)
            or not 1 <= rank <= 10
            or profile != "darkness-spell"
            or set(value) != {*expected, "darkness"}
        ):
            raise EngineInputError(
                f"{label} magical darkness is unsupported"
            )
        normalized_darkness = {
            "kind": "magical",
            "rank": int(rank),
            "profile": "darkness-spell",
        }
    else:
        raise EngineInputError(
            f"{label}.darkness.kind must be ordinary or magical"
        )
    result = {
        "rulesLevel": "darkness",
        "displayRgb": _display_rgb(
            value.get("displayRgb"),
            f"{label}.displayRgb",
        ),
        "darkness": normalized_darkness,
    }
    if resolved:
        result["sourceIds"] = _source_ids(
            value.get("sourceIds"),
            f"{label}.sourceIds",
        )
    return result


def default_resolved_illumination() -> dict[str, Any]:
    """Return the no-source ordinary-darkness result."""

    return {
        "schema": ILLUMINATION_SCHEMA,
        "kind": ILLUMINATION_KIND,
        "default": {
            "rulesLevel": "darkness",
            "displayRgb": [0, 0, 0],
            "sourceIds": [],
            "darkness": {"kind": "ordinary"},
        },
        "overrides": [],
        "rules": deepcopy(_RULES),
    }


def default_light_production() -> dict[str, Any]:
    """Return a normalized environment with no ambient light or sources."""

    return {
        "schema": LIGHT_PRODUCTION_SCHEMA,
        "kind": LIGHT_PRODUCTION_KIND,
        "ambient": {
            "rulesLevel": "darkness",
            "displayRgb": [0, 0, 0],
            "darkness": {"kind": "ordinary"},
        },
        "sources": [],
        "rules": deepcopy(_LIGHT_PRODUCTION_RULES),
    }


def _source_rule(value: Any, label: str) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"sourceId", "locator"}
        or not isinstance(value.get("sourceId"), str)
        or not value["sourceId"]
        or not isinstance(value.get("locator"), str)
        or not value["locator"]
    ):
        raise EngineInputError(
            f"{label} must contain exact sourceId and locator"
        )
    return {
        "sourceId": value["sourceId"],
        "locator": value["locator"],
    }


def _emission(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != {
        "brightRadiusFeet",
        "dimOuterRadiusFeet",
    }:
        raise EngineInputError(
            f"{label} requires brightRadiusFeet and dimOuterRadiusFeet"
        )
    bright = value.get("brightRadiusFeet")
    outer = value.get("dimOuterRadiusFeet")
    if (
        isinstance(bright, bool)
        or not isinstance(bright, int)
        or isinstance(outer, bool)
        or not isinstance(outer, int)
        or bright < 5
        or outer < bright
        or bright % 5
        or outer % 5
    ):
        raise EngineInputError(
            f"{label} radii must be 5-foot increments with the dim "
            "outer radius no smaller than the bright radius"
        )
    return {
        "brightRadiusFeet": int(bright),
        "dimOuterRadiusFeet": int(outer),
    }


def normalize_light_production(
    value: Any,
    grid: dict[str, Any],
) -> dict[str, Any]:
    """Validate scenario-authored ambient light and point sources."""

    if value is None:
        return default_light_production()
    if not isinstance(value, dict):
        raise EngineInputError("lighting must be an object")
    source_shape = {"ambient", "sources"}
    normalized_shape = {
        "schema",
        "kind",
        "ambient",
        "sources",
        "rules",
    }
    if frozenset(value) not in {
        frozenset(source_shape),
        frozenset(normalized_shape),
    }:
        raise EngineInputError("lighting fields are invalid")
    if "schema" in value and (
        value.get("schema") != LIGHT_PRODUCTION_SCHEMA
        or value.get("kind") != LIGHT_PRODUCTION_KIND
        or value.get("rules") != _LIGHT_PRODUCTION_RULES
    ):
        raise EngineInputError("lighting production identity is invalid")
    ambient = _light_value(value.get("ambient"), "lighting ambient")
    if ambient.get("darkness", {}).get("kind") == "magical":
        raise EngineInputError(
            "magical darkness must be supplied by a resolved spell effect"
        )
    raw_sources = value.get("sources")
    if not isinstance(raw_sources, list):
        raise EngineInputError("lighting sources must be an array")
    sources = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_sources):
        label = f"lighting sources[{index}]"
        if not isinstance(raw, dict) or set(raw) != {
            "id",
            "anchor",
            "emission",
            "displayRgb",
            "rule",
        }:
            raise EngineInputError(f"{label} fields are invalid")
        source_id = raw.get("id")
        if (
            not isinstance(source_id, str)
            or not _SOURCE_ID_RE.fullmatch(source_id)
            or source_id in seen
        ):
            raise EngineInputError(
                f"{label}.id is invalid or duplicated"
            )
        seen.add(source_id)
        anchor = raw.get("anchor")
        if not isinstance(anchor, dict):
            raise EngineInputError(f"{label}.anchor must be an object")
        anchor_kind = anchor.get("kind")
        if anchor_kind == "square":
            if set(anchor) != {"kind", "square"}:
                raise EngineInputError(
                    f"{label} square anchor fields are invalid"
                )
            square = coordinate(
                anchor.get("square"),
                f"{label}.anchor.square",
            )
            if not square_is_inside(square, grid):
                raise EngineInputError(
                    f"{label} anchor is outside the map"
                )
            normalized_anchor = {
                "kind": "square",
                "square": square,
            }
        elif anchor_kind == "participant":
            participant_id = anchor.get("participantId")
            if (
                set(anchor) != {"kind", "participantId"}
                or not isinstance(participant_id, str)
                or not participant_id
            ):
                raise EngineInputError(
                    f"{label} participant anchor fields are invalid"
                )
            normalized_anchor = {
                "kind": "participant",
                "participantId": participant_id,
            }
        else:
            raise EngineInputError(
                f"{label}.anchor.kind must be square or participant"
            )
        normalized_source = {
            "id": source_id,
            "anchor": normalized_anchor,
            "emission": _emission(
                raw.get("emission"),
                f"{label}.emission",
            ),
            "displayRgb": _display_rgb(
                raw.get("displayRgb"),
                f"{label}.displayRgb",
            ),
            "rule": _source_rule(
                raw.get("rule"),
                f"{label}.rule",
            ),
        }
        admitted_profile = (
            normalized_source["rule"]["sourceId"],
            normalized_source["rule"]["locator"],
            normalized_source["emission"]["brightRadiusFeet"],
            normalized_source["emission"]["dimOuterRadiusFeet"],
        )
        if admitted_profile not in {
            ("core-pc1", "287.5", 20, 40),
            ("core-pc1", "340.8", 20, 40),
            ("core-pc1", "340.8", 60, 120),
        }:
            raise EngineInputError(
                f"{label} emission does not match an admitted "
                "source-backed profile"
            )
        sources.append(normalized_source)
    sources.sort(key=lambda source: source["id"])
    return {
        "schema": LIGHT_PRODUCTION_SCHEMA,
        "kind": LIGHT_PRODUCTION_KIND,
        "ambient": ambient,
        "sources": sources,
        "rules": deepcopy(_LIGHT_PRODUCTION_RULES),
    }


def _participant_map_with_overrides(
    state: dict[str, Any],
    participant_overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    participants = state.get("participants")
    if not isinstance(participants, list):
        raise EngineInputError("light production participants are invalid")
    result = {
        str(participant.get("id") or ""): participant
        for participant in participants
        if isinstance(participant, dict)
    }
    if (
        len(result) != len(participants)
        or "" in result
        or (
            participant_overrides is not None
            and (
                not isinstance(participant_overrides, dict)
                or any(
                    participant_id not in result
                    or not isinstance(participant, dict)
                    for participant_id, participant
                    in participant_overrides.items()
                )
            )
        )
    ):
        raise EngineInputError("light production participants are invalid")
    if participant_overrides:
        result.update(participant_overrides)
    return result


def _burning_wielded_light_sources(
    state: dict[str, Any],
    participants: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    catalog = state.get("equipmentCatalog")
    definitions = state.get("definitions")
    if not isinstance(catalog, dict) or not isinstance(definitions, dict):
        raise EngineInputError("light-producing equipment state is invalid")
    catalog_items = catalog.get("items")
    if not isinstance(catalog_items, dict):
        raise EngineInputError("light-producing equipment catalog is invalid")
    result = []
    for participant_id, participant in participants.items():
        if int(participant.get("hitPoints", {}).get("current", 0)) <= 0:
            continue
        equipment = participant.get("equipment")
        if not isinstance(equipment, dict):
            continue
        item_id = str(equipment.get("wieldedItemId") or "")
        item = catalog_items.get(item_id)
        light_source = (
            item.get("lightSource")
            if isinstance(item, dict)
            else None
        )
        if light_source is None:
            continue
        if (
            not isinstance(light_source, dict)
            or set(light_source) != {
                "activeWhen",
                "emission",
                "displayRgb",
                "rule",
            }
            or light_source.get("activeWhen")
            != "wielded-burning-strike"
        ):
            raise EngineInputError(
                "equipment light-source contract is invalid"
            )
        definition = definitions.get(participant.get("creatureId"))
        if not isinstance(definition, dict):
            raise EngineInputError(
                "light-producing participant definition is missing"
            )
        strike_id = str(equipment.get("wieldedStrikeId") or "")
        strikes = [
            strike
            for strike in definition.get("strikes") or []
            if (
                isinstance(strike, dict)
                and strike.get("id") == strike_id
                and strike.get("itemId") == item_id
            )
        ]
        if len(strikes) != 1:
            raise EngineInputError(
                "wielded light-source Strike is missing or ambiguous"
            )
        components = strikes[0].get("damage", {}).get("components")
        if not isinstance(components, list) or not any(
            isinstance(component, dict)
            and component.get("type") == "fire"
            and component.get("persistent") is False
            for component in components
        ):
            raise EngineInputError(
                "wielded light source lacks a burning Strike"
            )
        result.append(
            {
                "id": f"equipment-{participant_id}-{item_id.rsplit(':', 1)[-1]}",
                "anchor": {
                    "kind": "participant",
                    "participantId": participant_id,
                },
                "emission": _emission(
                    light_source.get("emission"),
                    "equipment light-source emission",
                ),
                "displayRgb": _display_rgb(
                    light_source.get("displayRgb"),
                    "equipment light-source displayRgb",
                ),
                "rule": _source_rule(
                    light_source.get("rule"),
                    "equipment light-source rule",
                ),
                "origin": {
                    "kind": "equipment",
                    "participantId": participant_id,
                    "itemId": item_id,
                    "strikeId": strike_id,
                },
            }
        )
    return result


def _spell_light_sources(
    state: dict[str, Any],
    participants: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    effects = state.get("effects", [])
    if not isinstance(effects, list) or any(
        not isinstance(effect, dict)
        for effect in effects
    ):
        raise EngineInputError("encounter effects are invalid")
    result = []
    expected_fields = {
        "id",
        "kind",
        "sourceParticipantId",
        "sourceSpellId",
        "source",
        "traits",
        "rank",
        "displayRgb",
        "anchor",
        "emission",
        "duration",
        "creation",
        "rule",
    }
    for effect in effects:
        if effect.get("kind") != "spell-light-orb":
            continue
        source_id = effect.get("sourceParticipantId")
        rank = effect.get("rank")
        expected_emission = (
            {
                "brightRadiusFeet": 60,
                "dimOuterRadiusFeet": 120,
            }
            if isinstance(rank, int)
            and not isinstance(rank, bool)
            and rank >= 4
            else {
                "brightRadiusFeet": 20,
                "dimOuterRadiusFeet": 40,
            }
        )
        anchor = effect.get("anchor")
        if (
            set(effect) != expected_fields
            or effect.get("sourceSpellId") != "light"
            or effect.get("source") != LIGHT_SPELL_RULE
            or effect.get("rule") != LIGHT_SPELL_RULE
            or not isinstance(effect.get("id"), str)
            or not effect["id"]
            or not isinstance(source_id, str)
            or source_id not in participants
            or isinstance(rank, bool)
            or not isinstance(rank, int)
            or not 1 <= rank <= 10
            or effect.get("emission") != expected_emission
            or _display_rgb(
                effect.get("displayRgb"),
                "active Light spell displayRgb",
            )
            != effect.get("displayRgb")
            or not isinstance(anchor, dict)
        ):
            raise EngineInputError("active Light spell effect is invalid")
        if anchor.get("kind") == "square":
            if set(anchor) != {"kind", "square"}:
                raise EngineInputError(
                    "active Light spell square anchor is invalid"
                )
        elif anchor.get("kind") == "participant":
            if (
                set(anchor) != {"kind", "participantId"}
                or anchor.get("participantId") not in participants
            ):
                raise EngineInputError(
                    "active Light spell participant anchor is invalid"
                )
        else:
            raise EngineInputError("active Light spell anchor is invalid")
        result.append(
            {
                "id": str(effect["id"]),
                "anchor": deepcopy(anchor),
                "emission": deepcopy(expected_emission),
                "displayRgb": deepcopy(effect["displayRgb"]),
                "rule": deepcopy(LIGHT_SPELL_RULE),
                "origin": {
                    "kind": "spell",
                    "effectId": str(effect["id"]),
                    "participantId": source_id,
                    "spellId": "light",
                    "rank": int(rank),
                    "displayRgb": deepcopy(effect["displayRgb"]),
                },
            }
        )
    return result


def _flash_beetle_light_sources(
    state: dict[str, Any],
    participants: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project each active Luminescent Aura as an exact creature light."""

    definitions = state.get("definitions")
    if not isinstance(definitions, dict):
        raise EngineInputError("creature light-source definitions are invalid")
    result = []
    for participant_id, participant in participants.items():
        definition = definitions.get(participant.get("creatureId"))
        if not isinstance(definition, dict):
            raise EngineInputError(
                "creature light-source participant definition is missing"
            )
        try:
            pair = _flash_beetle.ability_pair(definition)
        except ValueError as failure:
            raise EngineInputError(str(failure)) from failure
        if pair is None:
            continue
        resource = participant.get("lightFlash")
        if resource is not None and (
            not isinstance(resource, dict)
            or resource.get("auraActive") is not True
        ):
            continue
        aura, _flash = pair
        result.append(
            {
                "id": (
                    f"creature-{participant_id}-"
                    f"{_flash_beetle.AURA_ABILITY_ID}"
                ),
                "anchor": {
                    "kind": "participant",
                    "participantId": participant_id,
                },
                "emission": deepcopy(
                    aura["mechanic"]["illumination"]["emission"]
                ),
                "displayRgb": deepcopy(
                    _display_rgb(
                        aura["mechanic"]["illumination"]["displayRgb"],
                        "creature light-source displayRgb",
                    )
                ),
                "rule": deepcopy(_flash_beetle.CREATURE_RULE),
                "origin": {
                    "kind": "creature-ability",
                    "participantId": participant_id,
                    "abilityId": _flash_beetle.AURA_ABILITY_ID,
                    "linkedAbilityId": _flash_beetle.FLASH_ABILITY_ID,
                },
            }
        )
    return result


def _scarecrow_light_sources(
    state: dict[str, Any],
    participants: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project each active Baleful Glow as a participant-anchored light."""

    definitions = state.get("definitions")
    effects = state.get("effects", [])
    if not isinstance(definitions, dict) or not isinstance(effects, list):
        raise EngineInputError("Scarecrow light-source state is invalid")
    result = []
    for effect in effects:
        if not isinstance(effect, dict):
            raise EngineInputError("encounter effects are invalid")
        if effect.get("kind") != "scarecrow-baleful-glow":
            continue
        source_id = effect.get("sourceParticipantId")
        participant = participants.get(str(source_id or ""))
        definition = (
            definitions.get(participant.get("creatureId"))
            if isinstance(participant, dict)
            else None
        )
        ability = None
        if isinstance(definition, dict):
            ability = next(
                (
                    item
                    for item in definition.get("abilities") or []
                    if isinstance(item, dict)
                    and item.get("id")
                    == _scarecrow.BALEFUL_GLOW_ABILITY_ID
                    and item.get("supported") is True
                    and item.get("mechanic", {}).get("type")
                    == _scarecrow.BALEFUL_GLOW_MECHANIC_TYPE
                ),
                None,
            )
        illumination = (
            ability.get("mechanic", {}).get("illumination")
            if isinstance(ability, dict)
            else None
        )
        expected_emission = (
            {
                "brightRadiusFeet": illumination["area"][
                    "brightRadiusFeet"
                ],
                "dimOuterRadiusFeet": illumination["area"][
                    "dimOuterRadiusFeet"
                ],
            }
            if isinstance(illumination, dict)
            and isinstance(illumination.get("area"), dict)
            else None
        )
        if (
            set(effect)
            != {
                "id",
                "kind",
                "sourceParticipantId",
                "sourceAbilityId",
                "displayRgb",
                "emission",
                "creation",
                "rule",
            }
            or participant is None
            or ability is None
            or not isinstance(illumination, dict)
            or effect.get("sourceAbilityId")
            != _scarecrow.BALEFUL_GLOW_ABILITY_ID
            or effect.get("rule") != _scarecrow.CREATURE_RULE
            or effect.get("emission") != expected_emission
            or _display_rgb(
                effect.get("displayRgb"),
                "Baleful Glow displayRgb",
            )
            != illumination.get("displayRgb")
        ):
            raise EngineInputError("active Baleful Glow effect is invalid")
        result.append(
            {
                "id": str(effect["id"]),
                "anchor": {
                    "kind": "participant",
                    "participantId": str(source_id),
                },
                "emission": deepcopy(expected_emission),
                "displayRgb": deepcopy(effect["displayRgb"]),
                "rule": deepcopy(_scarecrow.CREATURE_RULE),
                "origin": {
                    "kind": "creature-ability",
                    "participantId": str(source_id),
                    "abilityId": _scarecrow.BALEFUL_GLOW_ABILITY_ID,
                    "effectId": str(effect["id"]),
                },
            }
        )
    return result


def _active_light_sources(
    state: dict[str, Any],
    production: dict[str, Any],
    participants: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    active = [
        {
            **deepcopy(source),
            "origin": {"kind": "authored"},
        }
        for source in production["sources"]
    ]
    active.extend(
        _burning_wielded_light_sources(state, participants)
    )
    active.extend(_spell_light_sources(state, participants))
    active.extend(_flash_beetle_light_sources(state, participants))
    active.extend(_scarecrow_light_sources(state, participants))
    identifiers = [source["id"] for source in active]
    if len(identifiers) != len(set(identifiers)):
        raise EngineInputError("active light-source ids are duplicated")
    return sorted(active, key=lambda source: source["id"])


def _source_squares(
    source: dict[str, Any],
    participants: dict[str, dict[str, Any]],
) -> list[dict[str, int]]:
    anchor = source["anchor"]
    if anchor["kind"] == "square":
        return [deepcopy(anchor["square"])]
    participant = participants.get(anchor["participantId"])
    occupied = (
        participant.get("occupiedSquares")
        if isinstance(participant, dict)
        else None
    )
    if not isinstance(occupied, list) or not occupied:
        raise EngineInputError(
            f"light source participant is missing: "
            f"{anchor['participantId']}"
        )
    return [
        coordinate(square, "light-source participant occupied square")
        for square in occupied
    ]


def _source_rgb_at_level(
    display_rgb: list[int],
    rules_level: str,
) -> list[int]:
    """Return the deterministic visual contribution of one light source."""

    if rules_level == "bright":
        return deepcopy(display_rgb)
    if rules_level == "dim":
        # Dim light retains the source hue at two-fifths intensity.  Integer
        # half-up rounding makes the committed result platform-independent.
        return [(channel * 2 + 2) // 5 for channel in display_rgb]
    raise EngineInputError("light-source contribution level is invalid")


def _additive_rgb(first: list[int], second: list[int]) -> list[int]:
    """Add two display colors channel-wise and clamp to canonical sRGB."""

    return [
        min(255, int(first[index]) + int(second[index]))
        for index in range(3)
    ]


def resolve_light_production(
    state: dict[str, Any],
    *,
    participant_overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve ambient and active point sources through hard map blockers."""

    grid = state.get("map", {}).get("grid")
    if not isinstance(grid, dict):
        raise EngineInputError("light production map grid is invalid")
    production = normalize_light_production(
        state.get("lightProduction"),
        grid,
    )
    participants = _participant_map_with_overrides(
        state,
        participant_overrides,
    )
    active = _active_light_sources(
        state,
        production,
        participants,
    )
    ambient = {
        **deepcopy(production["ambient"]),
        "sourceIds": [],
    }
    levels: dict[tuple[int, int], dict[str, Any]] = {}
    all_squares = {
        (x, y)
        for y in range(int(grid["height"]))
        for x in range(int(grid["width"]))
    }
    for source in active:
        origins = _source_squares(source, participants)
        emission = source["emission"]
        outer = int(emission["dimOuterRadiusFeet"])
        candidates = {
            square
            for square in all_squares
            if min(
                grid_distance_feet(
                    origin,
                    {"x": square[0], "y": square[1]},
                )
                for origin in origins
            )
            <= outer
        }
        reachable: set[tuple[int, int]] = set()
        for origin in origins:
            reachable.update(
                squares_with_line_of_effect_from_point(
                    state,
                    (
                        Fraction(int(origin["x"]) * 2 + 1, 2),
                        Fraction(int(origin["y"]) * 2 + 1, 2),
                    ),
                    candidates,
                )
            )
        for x, y in reachable:
            distance = min(
                grid_distance_feet(
                    origin,
                    {"x": x, "y": y},
                )
                for origin in origins
            )
            produced_level = (
                "bright"
                if distance <= int(emission["brightRadiusFeet"])
                else "dim"
            )
            prior = deepcopy(levels.get((x, y), ambient))
            resolved_level = str(prior["rulesLevel"])
            if (
                resolved_level != "bright"
                and (
                    produced_level == "bright"
                    or resolved_level == "darkness"
                )
            ):
                resolved_level = produced_level
            resolved = {
                "rulesLevel": resolved_level,
                "displayRgb": _additive_rgb(
                    prior["displayRgb"],
                    _source_rgb_at_level(
                        source["displayRgb"],
                        produced_level,
                    ),
                ),
                "sourceIds": sorted(
                    [*prior["sourceIds"], str(source["id"])]
                ),
            }
            if resolved_level == "darkness":
                resolved["darkness"] = deepcopy(prior["darkness"])
            levels[(x, y)] = resolved
    overrides = [
        {
            "square": {"x": x, "y": y},
            "light": light,
        }
        for (x, y), light in sorted(
            levels.items(),
            key=lambda item: (item[0][1], item[0][0]),
        )
        if light != ambient
    ]
    return (
        normalize_resolved_illumination(
            {
                "schema": ILLUMINATION_SCHEMA,
                "kind": ILLUMINATION_KIND,
                "default": ambient,
                "overrides": overrides,
            },
            grid,
        ),
        active,
    )


def light_production_signature(state: dict[str, Any]) -> dict[str, Any]:
    """Return the small exact input surface that determines illumination."""

    grid = state.get("map", {}).get("grid")
    if not isinstance(grid, dict):
        raise EngineInputError("light production map grid is invalid")
    if (
        "lightProduction" not in state
        and state.get("illumination") is not None
    ):
        return {
            "legacyResolvedIllumination": deepcopy(state["illumination"]),
            "grid": deepcopy(grid),
        }
    production = normalize_light_production(
        state.get("lightProduction"),
        grid,
    )
    participants = _participant_map_with_overrides(state, None)
    sources = _active_light_sources(state, production, participants)
    runtime_map = state.get("map")
    if not isinstance(runtime_map, dict):
        raise EngineInputError("light production map is invalid")
    return {
        "map": {
            "id": runtime_map.get("id"),
            "grid": deepcopy(grid),
            "topologyDefinitionDigest": runtime_map.get(
                "topologyDefinitionDigest"
            ),
            "portalStates": deepcopy(runtime_map.get("portalStates", {})),
        },
        "production": production,
        "sources": [
            {
                "source": source,
                "squares": _source_squares(source, participants),
            }
            for source in sources
        ],
    }


def refresh_state_illumination(state: dict[str, Any]) -> None:
    """Regenerate producer-owned illumination or validate a resolved legacy field."""

    grid = state.get("map", {}).get("grid")
    if not isinstance(grid, dict):
        raise EngineInputError("encounter illumination grid is invalid")
    if (
        "lightProduction" not in state
        and state.get("illumination") is not None
    ):
        state["illumination"] = normalize_resolved_illumination(
            state.get("illumination"),
            grid,
        )
        state.pop("activeLightSources", None)
        return
    if "lightProduction" not in state:
        state["lightProduction"] = default_light_production()
    state["lightProduction"] = normalize_light_production(
        state.get("lightProduction"),
        grid,
    )
    illumination, sources = resolve_light_production(state)
    state["illumination"] = illumination
    state["activeLightSources"] = sources


def normalize_resolved_illumination(
    value: Any,
    grid: dict[str, Any],
) -> dict[str, Any]:
    """Validate one complete already-resolved illumination field."""

    if value is None:
        return default_resolved_illumination()
    if not isinstance(value, dict):
        raise EngineInputError("resolved illumination must be an object")
    source_shape = {"schema", "kind", "default", "overrides"}
    normalized_shape = {*source_shape, "rules"}
    if frozenset(value) not in {
        frozenset(source_shape),
        frozenset(normalized_shape),
    }:
        raise EngineInputError(
            "resolved illumination fields are invalid"
        )
    if (
        value.get("schema") != ILLUMINATION_SCHEMA
        or value.get("kind") != ILLUMINATION_KIND
    ):
        raise EngineInputError(
            "resolved illumination identity is invalid"
        )
    if "rules" in value and value.get("rules") != _RULES:
        raise EngineInputError(
            "resolved illumination rules are invalid"
        )
    default = _light_value(
        value.get("default"),
        "resolved illumination default",
        resolved=True,
    )
    raw_overrides = value.get("overrides")
    if not isinstance(raw_overrides, list):
        raise EngineInputError(
            "resolved illumination overrides must be an array"
        )
    overrides = []
    seen: set[tuple[int, int]] = set()
    for index, raw in enumerate(raw_overrides):
        if not isinstance(raw, dict) or set(raw) != {
            "square",
            "light",
        }:
            raise EngineInputError(
                f"resolved illumination overrides[{index}] is invalid"
            )
        square = coordinate(
            raw.get("square"),
            f"resolved illumination overrides[{index}].square",
        )
        if not square_is_inside(square, grid):
            raise EngineInputError(
                f"resolved illumination square is outside the map: {square}"
            )
        key = coordinate_key(square)
        if key in seen:
            raise EngineInputError(
                f"resolved illumination square is duplicated: {square}"
            )
        seen.add(key)
        overrides.append(
            {
                "square": square,
                "light": _light_value(
                    raw.get("light"),
                    f"resolved illumination overrides[{index}].light",
                    resolved=True,
                ),
            }
        )
    overrides.sort(
        key=lambda item: (
            int(item["square"]["y"]),
            int(item["square"]["x"]),
        )
    )
    return {
        "schema": ILLUMINATION_SCHEMA,
        "kind": ILLUMINATION_KIND,
        "default": default,
        "overrides": overrides,
        "rules": deepcopy(_RULES),
    }


def illumination_at_square(
    illumination: dict[str, Any],
    square: dict[str, Any],
) -> dict[str, Any]:
    """Return one normalized square's resolved light value."""

    key = coordinate_key(square)
    for override in illumination["overrides"]:
        if coordinate_key(override["square"]) == key:
            return deepcopy(override["light"])
    return deepcopy(illumination["default"])


def darkness_spell_squares(
    illumination: dict[str, Any],
    grid: dict[str, Any],
    *,
    minimum_rank: int = 1,
) -> set[tuple[int, int]]:
    """Return resolved squares occupied by an admitted Darkness profile."""

    if (
        isinstance(minimum_rank, bool)
        or not isinstance(minimum_rank, int)
        or not 1 <= minimum_rank <= 10
    ):
        raise EngineInputError(
            "Darkness spell minimum rank is invalid"
        )

    def matches(light: dict[str, Any]) -> bool:
        darkness = light.get("darkness", {})
        return bool(
            light.get("rulesLevel") == "darkness"
            and darkness.get("kind") == "magical"
            and darkness.get("profile") == "darkness-spell"
            and int(darkness["rank"]) >= minimum_rank
        )

    if matches(illumination["default"]):
        result = {
            (x, y)
            for y in range(int(grid["height"]))
            for x in range(int(grid["width"]))
        }
    else:
        result = set()
    for override in illumination["overrides"]:
        key = coordinate_key(override["square"])
        if matches(override["light"]):
            result.add(key)
        else:
            result.discard(key)
    return result


def participant_illumination(
    illumination: dict[str, Any],
    participant: dict[str, Any],
) -> dict[str, Any]:
    """Return one uniform footprint value or fail on the deferred exception."""

    occupied = participant.get("occupiedSquares")
    if not isinstance(occupied, list) or not occupied:
        raise EngineInputError(
            "participant occupied squares are invalid for illumination"
        )
    values = [
        illumination_at_square(illumination, square)
        for square in occupied
    ]
    first = values[0]
    first_rules = {
        key: deepcopy(first[key])
        for key in ("rulesLevel", "darkness")
        if key in first
    }
    if any(
        {
            key: deepcopy(value[key])
            for key in ("rulesLevel", "darkness")
            if key in value
        }
        != first_rules
        for value in values[1:]
    ):
        raise EngineInputError(
            "mixed-footprint illumination is unsupported pending an "
            "explicit Large-creature ruling"
        )
    return {
        **first_rules,
        "displayRgb": [
            (
                sum(value["displayRgb"][channel] for value in values)
                + len(values) // 2
            )
            // len(values)
            for channel in range(3)
        ],
        "sourceIds": sorted(
            {
                source_id
                for value in values
                for source_id in value["sourceIds"]
            }
        ),
    }


def _stat_families(definition: dict[str, Any]) -> dict[str, Any]:
    compilation = definition.get("statCompilation")
    families = (
        compilation.get("families")
        if isinstance(compilation, dict)
        else None
    )
    return families if isinstance(families, dict) else {}


def visual_sense_profile(
    definition: dict[str, Any],
) -> dict[str, Any]:
    """Project the reviewed visual grade, defaulting to average vision."""

    families = _stat_families(definition)
    compiled = families.get("visionSenses")
    vision = (
        compiled.get("vision")
        if isinstance(compiled, dict)
        else None
    )
    mechanic = (
        vision.get("mechanic")
        if isinstance(vision, dict)
        else None
    )
    grade = (
        mechanic.get("grade")
        if isinstance(mechanic, dict)
        else None
    )
    if grade not in {
        "low-light",
        "darkvision",
        "greater-darkvision",
    }:
        raw_senses = definition.get("perception", {}).get("senses", [])
        folded = {
            str(item).strip().casefold()
            for item in raw_senses
            if isinstance(item, str)
        }
        if "no vision" in folded:
            grade = "none"
        elif "greater darkvision" in folded:
            grade = "greater-darkvision"
        elif "darkvision" in folded:
            grade = "darkvision"
        elif "low-light vision" in folded:
            grade = "low-light"
        else:
            grade = "average"
    return {
        "channel": "vision",
        "acuity": "precise" if grade != "none" else "none",
        "grade": grade,
        "colorMode": (
            "black-and-white-in-dim-or-darkness"
            if grade in {"darkvision", "greater-darkvision"}
            else "normal"
        ),
        "rules": {
            "darkvision": deepcopy(DARKVISION_RULE),
            "lowLightVision": deepcopy(LOW_LIGHT_VISION_RULE),
        },
    }


def compiled_nonvisual_precise_senses(
    definition: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return compiler-ready precise senses without inventing eligibility."""

    families = _stat_families(definition)
    senses = families.get("specialSenses")
    if not isinstance(senses, list):
        return []
    result = []
    for sense in senses:
        precision = (
            sense.get("precision")
            if isinstance(sense, dict)
            else None
        )
        range_value = (
            sense.get("range")
            if isinstance(sense, dict)
            else None
        )
        feet = (
            range_value.get("feet")
            if isinstance(range_value, dict)
            else None
        )
        if (
            not isinstance(sense, dict)
            or sense.get("channel") == "vision"
            or not isinstance(precision, dict)
            or precision.get("effective") != "precise"
            or sense.get("compilerReady") is not True
            or isinstance(feet, bool)
            or not isinstance(feet, int)
            or feet <= 0
        ):
            continue
        result.append(
            {
                "senseId": str(sense.get("senseId") or ""),
                "family": str(sense.get("family") or ""),
                "channel": str(sense.get("channel") or ""),
                "acuity": "precise",
                "rangeFeet": int(feet),
                "eligibility": deepcopy(
                    sense.get("eligibility") or []
                ),
            }
        )
    return result


def _lighting_visual_result(
    *,
    grade: str,
    target_light: dict[str, Any],
) -> dict[str, Any]:
    level = target_light["rulesLevel"]
    if grade == "none":
        return {
            "usable": False,
            "concealed": False,
            "reason": "no-vision",
        }
    if level == "bright":
        return {
            "usable": True,
            "concealed": False,
            "reason": "bright-light",
        }
    if level == "dim":
        ignores = grade in {
            "low-light",
            "darkvision",
            "greater-darkvision",
        }
        return {
            "usable": True,
            "concealed": not ignores,
            "reason": (
                "dim-light-ignored"
                if ignores
                else "dim-light"
            ),
        }
    darkness = target_light["darkness"]
    if grade == "greater-darkvision":
        return {
            "usable": True,
            "concealed": False,
            "reason": "greater-darkvision",
        }
    if grade == "darkvision":
        magical_rank = (
            int(darkness["rank"])
            if darkness["kind"] == "magical"
            else 0
        )
        blocked = (
            darkness["kind"] == "magical"
            and darkness.get("profile") == "darkness-spell"
            and magical_rank >= 4
        )
        return {
            "usable": True,
            "concealed": blocked,
            "reason": (
                "rank-4-darkness-spell"
                if blocked
                else "darkvision"
            ),
        }
    return {
        "usable": False,
        "concealed": False,
        "reason": "darkness",
    }


def _worse_detection(
    first: str,
    second: str,
) -> str:
    return (
        first
        if _DETECTION_RANK[first] >= _DETECTION_RANK[second]
        else second
    )


def perception_relation(
    *,
    observer: dict[str, Any],
    observer_definition: dict[str, Any],
    target: dict[str, Any],
    target_definition: dict[str, Any],
    illumination: dict[str, Any],
    distance_feet: int,
    line_of_sight: bool,
    visual_path_concealed: bool = False,
    awareness_state: str = "observed",
    nonvisual_eligibility: Callable[
        [dict[str, Any], dict[str, Any], dict[str, Any]],
        bool,
    ]
    | None = None,
) -> dict[str, Any]:
    """Derive one observer-target relationship from resolved illumination."""

    if awareness_state not in _AWARENESS_STATES:
        raise EngineInputError("awareness state is invalid")
    if (
        isinstance(distance_feet, bool)
        or not isinstance(distance_feet, int)
        or distance_feet < 0
        or type(line_of_sight) is not bool
        or type(visual_path_concealed) is not bool
    ):
        raise EngineInputError("perception geometry is invalid")
    observer_light = participant_illumination(
        illumination,
        observer,
    )
    target_light = participant_illumination(
        illumination,
        target,
    )
    visual = visual_sense_profile(observer_definition)
    visual_result = _lighting_visual_result(
        grade=str(visual["grade"]),
        target_light=target_light,
    )
    visual_usable = bool(
        line_of_sight and visual_result["usable"]
    )
    selected_nonvisual = None
    for sense in compiled_nonvisual_precise_senses(
        observer_definition
    ):
        if distance_feet > int(sense["rangeFeet"]):
            continue
        if (
            nonvisual_eligibility is not None
            and nonvisual_eligibility(
                sense,
                observer_definition,
                target_definition,
            )
        ):
            selected_nonvisual = sense
            break

    if selected_nonvisual is not None:
        lighting_state = "observed"
        selected_sense = deepcopy(selected_nonvisual)
        concealed = False
    elif visual_usable:
        lighting_state = "observed"
        selected_sense = deepcopy(visual)
        concealed = bool(
            visual_result["concealed"]
            or visual_path_concealed
        )
    else:
        # Encounter participants begin aware of one another.  Hearing is the
        # default imprecise sense, so loss of precise vision caps that known
        # target at hidden.  An already-undetected or unnoticed target remains
        # worse through the awareness layer below.
        lighting_state = "hidden"
        selected_sense = {
            "channel": "hearing",
            "acuity": "imprecise",
            "grade": "average",
        }
        concealed = False

    detection = _worse_detection(
        awareness_state,
        lighting_state,
    )
    if detection != "observed":
        concealed = False
    observer_in_darkness = observer_light["rulesLevel"] == "darkness"
    lighting_blinded = bool(
        observer_in_darkness
        and visual["grade"]
        not in {"darkvision", "greater-darkvision"}
        and selected_nonvisual is None
    )
    flat_check_dc = (
        5
        if concealed
        else 11
        if detection in {"hidden", "undetected"}
        else None
    )
    return {
        "observerParticipantId": str(observer["id"]),
        "targetParticipantId": str(target["id"]),
        "observerLight": observer_light,
        "targetLight": target_light,
        "awarenessState": awareness_state,
        "detectionState": detection,
        "concealed": concealed,
        "targetingFlatCheckDC": flat_check_dc,
        "targetingFlatCheckSecret": detection == "undetected",
        "targetSquareMustBeGuessed": detection == "undetected",
        "offGuardToTarget": detection in {
            "hidden",
            "undetected",
            "unnoticed",
        },
        "selectedSense": selected_sense,
        "visualSense": visual,
        "visualLighting": visual_result,
        "visualPathConcealed": visual_path_concealed,
        "lightingBlinded": lighting_blinded,
        "rules": {
            "light": deepcopy(LIGHT_LEVEL_RULE),
            "brightLight": deepcopy(BRIGHT_LIGHT_RULE),
            "dimLight": deepcopy(DIM_LIGHT_RULE),
            "darkness": deepcopy(DARKNESS_RULE),
            "observed": deepcopy(OBSERVED_RULE),
            "hidden": deepcopy(HIDDEN_RULE),
            "undetected": deepcopy(UNDETECTED_RULE),
            "concealed": deepcopy(CONCEALED_RULE),
            "blinded": deepcopy(BLINDED_RULE),
            "darkvision": deepcopy(DARKVISION_RULE),
            "lowLightVision": deepcopy(LOW_LIGHT_VISION_RULE),
            **(
                {
                    "darknessSpell": deepcopy(
                        DARKNESS_SPELL_RULE
                    )
                }
                if target_light.get("darkness", {}).get("kind")
                == "magical"
                else {}
            ),
        },
    }


__all__ = [
    "BLINDED_RULE",
    "BRIGHT_LIGHT_RULE",
    "CONCEALED_RULE",
    "DARKNESS_RULE",
    "DARKNESS_SPELL_RULE",
    "DARKVISION_RULE",
    "DIM_LIGHT_RULE",
    "HIDDEN_RULE",
    "ILLUMINATION_KIND",
    "ILLUMINATION_SCHEMA",
    "LIGHT_PRODUCTION_KIND",
    "LIGHT_PRODUCTION_SCHEMA",
    "LIGHT_LEVEL_RULE",
    "LIGHT_LEVELS",
    "LIGHT_SPELL_RULE",
    "LOW_LIGHT_VISION_RULE",
    "OBSERVED_RULE",
    "TORCH_RULE",
    "UNDETECTED_RULE",
    "compiled_nonvisual_precise_senses",
    "default_light_production",
    "default_resolved_illumination",
    "darkness_spell_squares",
    "illumination_at_square",
    "normalize_light_production",
    "normalize_resolved_illumination",
    "participant_illumination",
    "perception_relation",
    "refresh_state_illumination",
    "resolve_light_production",
    "visual_sense_profile",
]

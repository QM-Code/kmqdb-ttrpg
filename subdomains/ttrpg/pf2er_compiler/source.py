"""Compile bounded PF2ER source nodes into mechanical definitions.

The library's ordered JSON may contain duplicate object members.  This module
therefore keeps object pairs intact while locating the selected semantic block;
it never round-trips a source document through a normal JSON mapping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import errors as _errors
from . import source_nodes as _source_nodes
from .mechanics import animated_construct_armor as _animated_construct_armor
from .mechanics import battle_cry as _mechanics_battle_cry
from .mechanics import contracts as _mechanics_contracts
from .mechanics import flash_beetle as _mechanics_flash_beetle
from .mechanics import forced_movement as _forced_movement
from .mechanics import fungus_leshy as _mechanics_fungus_leshy
from .mechanics import gaze as _mechanics_gaze
from .mechanics import ghoul as _mechanics_ghoul
from .mechanics import plague_zombie_abilities as _plague_zombie_abilities
from .mechanics import registry as _mechanics_registry
from .mechanics import source_authority as _source_authority
from .mechanics import stench as _mechanics_stench
from .mechanics import strike_save_control as _strike_save_control
from .mechanics import zombie_rot as _zombie_rot
from .mechanics import zombie_brute as _zombie_brute
from .mechanics import swallow_whole as _swallow_whole
from .mechanics import warg as _mechanics_warg
from .source_compilation_plan import (
    CreatureAbilityCompilationPlan as _CreatureAbilityCompilationPlan,
    CreatureSpellcastingCompilationPlan as _CreatureSpellcastingCompilationPlan,
    CreatureStatCompilationPlan as _CreatureStatCompilationPlan,
    CreatureStrikeCompilationPlan as _CreatureStrikeCompilationPlan,
    compile_creature_ability_plan as _compile_creature_ability_plan,
    compile_creature_spellcasting_plan as _compile_creature_spellcasting_plan,
    compile_creature_strike_plan as _compile_creature_strike_plan,
    compile_creature_stat_plan as _compile_creature_stat_plan,
    creature_ability_plan_projection as _creature_ability_plan_projection,
    creature_spellcasting_plan_projection as _creature_spellcasting_plan_projection,
    creature_strike_plan_projection as _creature_strike_plan_projection,
    creature_stat_plan_base_value as _creature_stat_plan_base_value,
    creature_stat_plan_deferrals as _creature_stat_plan_deferrals,
    creature_stat_plan_legacy_space as _creature_stat_plan_legacy_space,
    creature_stat_plan_projection as _creature_stat_plan_projection,
    creature_stat_plan_speeds as _creature_stat_plan_speeds,
)

DAMAGE_DEFENSE_RE = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z -]*?)\s+(?P<value>\d+)$",
    re.IGNORECASE,
)
DAMAGE_DEFENSE_EXCEPTION_RE = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z -]*?)\s+(?P<value>\d+)\s+"
    r"\(except (?P<exception>[A-Za-z][A-Za-z -]*?)\)$",
    re.IGNORECASE,
)
SOURCE_ONLY_SPEED_RE = re.compile(
    r"^(?:(?P<mode>[A-Za-z][A-Za-z -]*)\s+)?"
    r"(?P<feet>\d+)\s+feet$",
    re.IGNORECASE,
)
SKILL_RE = re.compile(r"^(?P<name>.+?)\s+(?P<modifier>[+-]\d+)(?:\s+\((?P<note>.+)\))?$")
INVENTORY_BUNDLE_RE = re.compile(
    r"^(?P<item>[^()]+?)\s+\((?P<quantity>\d+)\s+(?P<contents>[^()]+)\)$"
)
INVENTORY_QUANTITY_RE = re.compile(r"^(?P<item>[^()]+?)\s+\((?P<quantity>\d+)\)$")
MAX_INVENTORY_QUANTITY = (1 << 63) - 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
ICON_ASSET_EXTENSIONS = (".svg", ".png", ".webp", ".avif")
INVENTORY_BUNDLE_AMMUNITION = {
    "blowgun": "darts",
    "bow": "arrows",
    "crossbow": "bolts",
    "sling": "bullets",
}
SUPPORTED_DAMAGE_DEFENSE_TYPES = {
    "acid",
    "bludgeoning",
    "cold",
    "electricity",
    "fire",
    "force",
    "mental",
    "physical",
    "piercing",
    "poison",
    "slashing",
    "sonic",
    "spirit",
    "vitality",
    "void",
}
PHYSICAL_DAMAGE_TYPES = {"bludgeoning", "piercing", "slashing"}
CREATURE_ABILITY_GLOSSARIES = {
    "core-mc1": {
        "locator": "358.2",
        "followUpPages": {359},
        "constrictPages": {358},
    },
    "core-mc2": {
        "locator": "360.2",
        "followUpPages": {361},
        "constrictPages": {360},
    },
}
CREATURE_PRESENTATION_FIELDS = frozenset(("Description", "Image"))


def source_icon_asset_key(
    source_id: str,
    value: Any,
    *,
    label: str = "source Icon",
) -> str | None:
    """Compile one source-relative semantic icon into its logical asset key."""

    if value is None:
        return None
    if type(value) is not str:
        raise _errors.EngineInputError(
            f"{label} must be a string"
        )
    if (
        not value
        or value != value.strip()
        or len(value) > 500
        or "\r" in value
        or "\n" in value
    ):
        raise _errors.EngineInputError(
            f"{label} reference is invalid: {value}"
        )
    source_parts = source_id.split("-")
    if (
        not source_parts
        or any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._]*", part)
            for part in source_parts
        )
    ):
        raise _errors.EngineInputError(
            f"{label} source is invalid"
        )
    parts = value.split("/")
    if (
        len(parts) < 2
        or any(
            not part
            or part in {".", ".."}
            or "\\"
            in part
            or "\x00" in part
            or "<" in part
            or ">" in part
            for part in parts
        )
        or parts[-1].casefold().endswith(ICON_ASSET_EXTENSIONS)
    ):
        raise _errors.EngineInputError(
            f"{label} reference is invalid: {value}"
        )
    source_prefix = "/".join(source_parts)
    if value.startswith(f"{source_prefix}/"):
        raise _errors.EngineInputError(
            f"{label} must be book-relative"
        )
    return "/".join((*source_parts, *parts))


def creature_icon_asset_key(source_id: str, value: Any) -> str | None:
    """Compile one source-relative creature icon into its logical asset key."""

    return source_icon_asset_key(
        source_id,
        value,
        label="creature Icon",
    )


def parse_perception(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        if not value:
            raise _errors.EngineInputError("creature Perception is empty")
        modifier = _source_nodes.integer(value[0], "creature Perception")
        senses = _source_nodes.string_list(value[1], "creature senses") if len(value) > 1 else []
        if len(value) > 2:
            raise _errors.EngineInputError("creature Perception has unsupported fields")
        return {"modifier": modifier, "senses": senses}
    return {"modifier": _source_nodes.integer(value, "creature Perception"), "senses": []}


def parse_skills(value: Any) -> list[dict[str, Any]]:
    result = []
    for raw in _source_nodes.string_list(value, "creature Skills"):
        match = SKILL_RE.fullmatch(raw)
        if not match:
            raise _errors.EngineInputError(f"creature skill is not understood: {raw}")
        item = {
            "name": match.group("name"),
            "modifier": int(match.group("modifier")),
        }
        if match.group("note"):
            item["note"] = match.group("note")
        result.append(item)
    return result


def _source_only_numeric_speeds(value: Any) -> dict[str, int]:
    """Retain bounded source-only fixture support without provider claims."""

    result: dict[str, int] = {}
    for index, raw in enumerate(str(value or "").split(",")):
        text = raw.strip()
        match = SOURCE_ONLY_SPEED_RE.fullmatch(text)
        if not match:
            raise _errors.EngineInputError(
                f"creature Speed is not understood: {text}"
            )
        mode = str(
            match.group("mode")
            or ("land" if index == 0 else "")
        ).strip().casefold()
        if not mode or mode in result:
            raise _errors.EngineInputError(
                f"creature Speed mode is invalid: {text}"
            )
        result[mode] = int(match.group("feet"))
    if "land" not in result:
        raise _errors.EngineInputError("creature has no land Speed")
    return result


def inventory_bundle_is_supported(item: str, contents: str) -> bool:
    """Accept only one launcher paired with one homogeneous ammunition type."""

    normalized_item = re.sub(r"<[^>]+>", "", str(item or "")).strip().casefold()
    normalized_contents = " ".join(str(contents or "").split()).casefold()
    launcher_kind = next(
        (
            kind
            for kind in ("blowgun", "crossbow", "sling", "bow")
            if normalized_item.endswith(kind)
        ),
        None,
    )
    return (
        launcher_kind is not None
        and normalized_contents == INVENTORY_BUNDLE_AMMUNITION[launcher_kind]
    )


def require_inventory_quantity(value: str, source_text: str) -> int:
    quantity = int(value)
    if not 1 <= quantity <= MAX_INVENTORY_QUANTITY:
        raise _errors.EngineInputError(
            f"creature item quantity must be between 1 and "
            f"{MAX_INVENTORY_QUANTITY}: {source_text}"
        )
    return quantity


def parse_inventory(value: Any) -> list[dict[str, Any]]:
    result = []
    seen: set[str] = set()
    for source_text in _source_nodes.string_list(value, "creature Items"):
        bundle = INVENTORY_BUNDLE_RE.fullmatch(source_text)
        quantity = INVENTORY_QUANTITY_RE.fullmatch(source_text)
        if bundle and not inventory_bundle_is_supported(
            bundle.group("item"),
            bundle.group("contents"),
        ):
            raise _errors.EngineInputError(
                f"creature item bundle is not supported: {source_text}"
            )
        counted_quantity = (
            require_inventory_quantity(quantity.group("quantity"), source_text)
            if quantity
            else 1
        )
        entries = [
            {
                "name": str(
                    bundle.group("item")
                    if bundle
                    else quantity.group("item")
                    if quantity
                    else source_text
                ).strip().casefold(),
                "quantity": counted_quantity,
                "sourceText": source_text,
            }
        ]
        if bundle:
            entries.append(
                {
                    "name": bundle.group("contents").strip().casefold(),
                    "quantity": require_inventory_quantity(
                        bundle.group("quantity"),
                        source_text,
                    ),
                    "sourceText": source_text,
                    "supplies": bundle.group("item").strip().casefold(),
                }
            )
        for entry in entries:
            if not entry["name"] or entry["name"] in seen:
                raise _errors.EngineInputError(f"creature item is empty or duplicated: {source_text}")
            seen.add(entry["name"])
            result.append(entry)
    return result


def parse_damage_defenses(
    value: Any,
    *,
    label: str,
    rule_locator: str,
    source_id: str,
    source_locator: str,
) -> list[dict[str, Any]]:
    """Compile strict numeric damage defenses and one physical subtype exception."""

    result = []
    seen: set[str] = set()
    for source_text in _source_nodes.string_list(value, f"creature {label}"):
        match = DAMAGE_DEFENSE_RE.fullmatch(source_text)
        exception_match = (
            None if match is not None else DAMAGE_DEFENSE_EXCEPTION_RE.fullmatch(source_text)
        )
        match = match or exception_match
        damage_type = match.group("type").strip().casefold() if match else ""
        if match is None or damage_type not in SUPPORTED_DAMAGE_DEFENSE_TYPES:
            raise _errors.EngineInputError(
                f"creature {label} damage defense is not supported: {source_text}"
            )
        exception = (
            exception_match.group("exception").strip().casefold()
            if exception_match is not None
            else ""
        )
        if exception and (
            damage_type != "physical"
            or exception not in PHYSICAL_DAMAGE_TYPES
        ):
            raise _errors.EngineInputError(
                f"creature {label} damage defense is not supported: {source_text}"
            )
        if damage_type in seen:
            raise _errors.EngineInputError(f"creature {label} damage defense is duplicated: {damage_type}")
        seen.add(damage_type)
        amount = int(match.group("value"))
        if amount <= 0:
            raise _errors.EngineInputError(f"creature {label} damage defense must be positive")
        compiled = {
            "type": damage_type,
            "value": amount,
            "sourceText": source_text,
            "source": {
                "sourceId": source_id,
                "locator": source_locator,
            },
            "rule": {
                "sourceId": "core-pc1",
                "locator": rule_locator,
            },
        }
        if exception:
            compiled["exceptDamageTypes"] = [exception]
        result.append(compiled)
    return result


def _legacy_damage_defense_clause_is_runtime_safe(
    value: Any,
) -> bool:
    """Recognize only the already executable numeric defense grammar."""

    if (
        type(value) is not dict
        or value.get("support") != "supported"
        or type(value.get("ordinal")) is not int
        or type(value.get("sourceText")) is not str
        or type(value.get("value")) is not int
        or value["value"] <= 0
        or value.get("nonmagicalMultiplier") != 1
        or value.get("deferredDependency") is not None
        or type(value.get("providerRuleIds")) is not list
    ):
        return False
    predicate_kind = value.get("predicateKind")
    term = value.get("term")
    exceptions = value.get("exceptions")
    if (
        predicate_kind == "damage-type"
        and term in SUPPORTED_DAMAGE_DEFENSE_TYPES
        and exceptions == []
    ):
        return True
    if (
        predicate_kind != "physical-family"
        or term != "physical"
        or type(exceptions) is not list
    ):
        return False
    if not exceptions:
        return True
    return (
        len(exceptions) == 1
        and type(exceptions[0]) is list
        and len(exceptions[0]) == 1
        and type(exceptions[0][0]) is dict
        and exceptions[0][0].get("dimension") == "damage-type"
        and exceptions[0][0].get("term") in PHYSICAL_DAMAGE_TYPES
    )


def _damage_defense_runtime_projection(
    stat_plan: _CreatureStatCompilationPlan | None,
    fields: dict[str, Any],
    *,
    source_id: str,
    source_locator: str,
) -> tuple[dict[str, Any], list[str]]:
    """Project the legacy numeric subset or one atomic typed blocker."""

    if stat_plan is None:
        return (
            {
                "weaknesses": parse_damage_defenses(
                    fields.get("Weaknesses"),
                    label="Weaknesses",
                    rule_locator="408.6",
                    source_id=source_id,
                    source_locator=source_locator,
                ),
                "resistances": parse_damage_defenses(
                    fields.get("Resistances"),
                    label="Resistances",
                    rule_locator="408.7",
                    source_id=source_id,
                    source_locator=source_locator,
                ),
            },
            [],
        )

    stat_projection = _creature_stat_plan_projection(stat_plan)
    families = stat_projection.get("families")
    facade = (
        families.get("damageDefenses")
        if type(families) is dict
        else None
    )
    source_fields = (
        facade.get("fields")
        if type(facade) is dict
        else None
    )
    if (
        type(facade) is not dict
        or facade.get("registryStatus") != "unregistered"
        or facade.get("activationStatus") != "deferred"
        or facade.get("runtimeActivated") is not False
        or type(source_fields) is not list
        or any(type(item) is not dict for item in source_fields)
        or [item.get("field") for item in source_fields]
        != ["Weaknesses", "Resistances"]
    ):
        raise _errors.EngineInputError(
            "damage-defense facade projection is invalid"
        )

    blockers = []
    for source_field in source_fields:
        field = str(source_field["field"])
        entries = source_field.get("entries")
        if type(entries) is not list:
            raise _errors.EngineInputError(
                "damage-defense facade entries are invalid"
            )
        for entry in entries:
            if _legacy_damage_defense_clause_is_runtime_safe(entry):
                continue
            if type(entry) is not dict:
                raise _errors.EngineInputError(
                    "damage-defense facade clause is invalid"
                )
            dependency = entry.get("deferredDependency")
            blocker = (
                "dependency:" + dependency
                if type(dependency) is str and dependency
                else "predicate:" + str(entry.get("predicateKind"))
            )
            blockers.append(
                "damage-defenses:"
                + field
                + ":"
                + str(entry.get("ordinal"))
                + ":"
                + blocker
            )
        runtime_terms = [
            entry.get("term")
            for entry in entries
            if type(entry) is dict
            and _legacy_damage_defense_clause_is_runtime_safe(entry)
        ]
        for term in sorted(
            {
                item
                for item in runtime_terms
                if runtime_terms.count(item) > 1
            }
        ):
            blockers.append(
                "damage-defenses:"
                + field
                + ":duplicate-runtime-predicate:"
                + str(term)
            )

    blockers = sorted(set(blockers))
    if blockers:
        return (
            {
                field["field"].casefold(): {
                    "status": "blocked",
                    "sourceField": field["field"],
                    "shape": field.get("shape"),
                    "entries": field["entries"],
                }
                for field in source_fields
            },
            blockers,
        )

    runtime = {
        "weaknesses": parse_damage_defenses(
            fields.get("Weaknesses"),
            label="Weaknesses",
            rule_locator="408.6",
            source_id=source_id,
            source_locator=source_locator,
        ),
        "resistances": parse_damage_defenses(
            fields.get("Resistances"),
            label="Resistances",
            rule_locator="408.7",
            source_id=source_id,
            source_locator=source_locator,
        ),
    }
    for source_field in source_fields:
        runtime_field = source_field["field"].casefold()
        projected_entries = source_field["entries"]
        if [
            item["sourceText"] for item in runtime[runtime_field]
        ] != [
            item["sourceText"] for item in projected_entries
        ]:
            raise _errors.EngineInputError(
                "legacy damage-defense projection disagrees with facade"
            )
    return runtime, []


def _project_strike_riders(
    strike: dict[str, Any],
    *,
    source_id: str,
    strike_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    damage = strike.get("damage")
    carriers = (
        damage.get("carriers")
        if type(damage) is dict
        else None
    )
    if type(carriers) is not list:
        raise _errors.EngineInputError(
            "source-backed Strike projection has invalid damage carriers"
        )
    riders = []
    for carrier in carriers:
        terms = (
            carrier.get("terms")
            if type(carrier) is dict
            else None
        )
        if type(terms) is not list:
            raise _errors.EngineInputError(
                "source-backed Strike projection has invalid damage terms"
            )
        for term in terms:
            if (
                type(term) is not dict
                or term.get("riderOrdinal") is None
            ):
                continue
            source_text = term.get("rawText")
            source_address = term.get("riderAddressSha256")
            if (
                type(source_text) is not str
                or not source_text
                or type(source_address) is not str
                or SHA256_RE.fullmatch(source_address) is None
            ):
                raise _errors.EngineInputError(
                    "source-backed Strike rider projection is invalid"
                )
            name = re.sub(
                r"\s*\([^)]*\)\s*$",
                "",
                source_text,
            ).strip()
            if not name:
                raise _errors.EngineInputError(
                    "source-backed Strike rider name is empty"
                )
            riders.append(
                {
                    "name": name,
                    "sourceText": source_text,
                    "sourceAddressSha256": source_address,
                    "supported": False,
                }
            )

    follow_ups = []
    unresolved_riders = []
    rider_name_counts: dict[str, int] = {}
    for rider in riders:
        rider_name = rider["name"].casefold()
        rider_name_counts[rider_name] = (
            rider_name_counts.get(rider_name, 0) + 1
        )
    for rider in riders:
        follow_up_name = rider["name"].casefold()
        glossary = CREATURE_ABILITY_GLOSSARIES.get(source_id)
        page_match = re.fullmatch(
            r"(?:Grab|Knockdown) \(page (?P<page>\d+)\)",
            str(rider["sourceText"]),
            re.IGNORECASE,
        )
        if (
            follow_up_name in {"grab", "knockdown"}
            and rider_name_counts[follow_up_name] == 1
            and glossary is not None
            and page_match is not None
            and int(page_match.group("page"))
            in glossary["followUpPages"]
        ):
            follow_ups.append(
                {
                    "id": follow_up_name,
                    "name": (
                        "Grab"
                        if follow_up_name == "grab"
                        else "Knockdown"
                    ),
                    "trigger": "successful-strike",
                    "actionCost": 1,
                    "appendage": strike_id,
                    "supported": True,
                    "rule": {
                        "sourceId": source_id,
                        "locator": str(glossary["locator"]),
                    },
                    "sourceText": rider["sourceText"],
                }
            )
        else:
            unresolved_riders.append(
                {
                    "name": rider["name"],
                    "sourceText": rider["sourceText"],
                    "supported": False,
                }
            )
    return follow_ups, unresolved_riders


def _project_engine_strike(
    strike: dict[str, Any],
    *,
    default_reach_feet: int,
    source_id: str,
) -> dict[str, Any]:
    if type(strike) is not dict:
        raise _errors.EngineInputError(
            "source-backed Strike projection entry is invalid"
        )
    name = strike.get("sourceName")
    strike_id = strike.get("sourceActionId")
    occurrence_id = strike.get("id")
    mode = strike.get("mode")
    source_address = strike.get("sourceAddressSha256")
    if (
        type(name) is not str
        or not name
        or type(strike_id) is not str
        or strike_id != f"strike:{strike.get('normalizedLabel')}:{mode}"
        or type(occurrence_id) is not str
        or f"#{strike_id}:" not in occurrence_id
        or mode not in {"melee", "ranged"}
        or type(source_address) is not str
        or SHA256_RE.fullmatch(source_address) is None
    ):
        raise _errors.EngineInputError(
            "source-backed Strike identity projection is invalid"
        )
    if strike.get("mechanicallyComplete") is not True:
        blockers = strike.get("integrationBlockers")
        requirement = (
            blockers[0].get("requirementId")
            if type(blockers) is list
            and blockers
            and type(blockers[0]) is dict
            else "unknown"
        )
        raise _errors.EngineInputError(
            "source-backed Strike is not mechanically complete: "
            f"{strike_id} ({requirement})"
        )

    damage_projection = strike.get("damage")
    components = (
        damage_projection.get("components")
        if type(damage_projection) is dict
        else None
    )
    if (
        type(damage_projection) is not dict
        or damage_projection.get("status")
        != "exact-immediate-components"
        or damage_projection.get("immediateComplete") is not True
        or damage_projection.get("explicitNoDamage") is not False
        or type(components) is not list
        or not components
    ):
        raise _errors.EngineInputError(
            "source-backed Strike has no immediate damage components: "
            f"{strike_id}"
        )
    projected_components = []
    previous_span_end = -1
    for component_index, component in enumerate(components):
        if type(component) is not dict:
            raise _errors.EngineInputError(
                "source-backed Strike damage component is invalid: "
                f"{strike_id}[{component_index}]"
            )
        dice = component.get("dice")
        flat_amount = component.get("flatAmount")
        dice_is_valid = (
            type(dice) is dict
            and type(dice.get("count")) is int
            and dice["count"] >= 1
            and type(dice.get("sides")) is int
            and dice["sides"] >= 2
            and flat_amount is None
        )
        flat_is_valid = (
            dice is None
            and type(flat_amount) is int
            and flat_amount >= 0
        )
        source_text = component.get("sourceText")
        source_span = component.get("sourceSpan")
        component_address = component.get(
            "carrierAddressSha256"
        )
        if (
            not (dice_is_valid or flat_is_valid)
            or type(component.get("modifier")) is not int
            or type(component.get("damageType")) is not str
            or not component["damageType"]
            or component.get("persistent") is not False
            or component.get("componentOrdinal") != component_index
            or type(source_text) is not str
            or not source_text
            or type(source_span) is not dict
            or type(source_span.get("start")) is not int
            or type(source_span.get("end")) is not int
            or source_span["start"] < 0
            or source_span["end"] <= source_span["start"]
            or source_span["start"] < previous_span_end
            or type(component_address) is not str
            or SHA256_RE.fullmatch(component_address) is None
        ):
            raise _errors.EngineInputError(
                "source-backed Strike damage component cannot be "
                "represented exactly: "
                f"{strike_id}[{component_index}]"
            )
        previous_span_end = source_span["end"]
        projected_components.append(
            {
                "sourceText": source_text,
                "sourceAddressSha256": component_address,
                "sourceSpan": {
                    "start": source_span["start"],
                    "end": source_span["end"],
                },
                "dice": (
                    {
                        "count": dice["count"],
                        "sides": dice["sides"],
                    }
                    if dice_is_valid
                    else None
                ),
                "flatAmount": flat_amount,
                "modifier": component["modifier"],
                "type": component["damageType"],
                "persistent": False,
            }
        )
    component = projected_components[0]
    carriers = damage_projection.get("carriers")
    damage_carrier = next(
        (
            carrier
            for carrier in carriers
            if (
                type(carrier) is dict
                and carrier.get("sourceAddressSha256")
                == component["sourceAddressSha256"]
            )
        ),
        None,
    ) if type(carriers) is list else None
    if (
        type(damage_carrier) is not dict
        or type(damage_carrier.get("rawText")) is not str
        or not damage_carrier["rawText"]
    ):
        raise _errors.EngineInputError(
            "source-backed Strike damage carrier is invalid"
        )
    if any(
        component["sourceAddressSha256"]
        != damage_carrier["sourceAddressSha256"]
        for component in projected_components
    ):
        raise _errors.EngineInputError(
            "source-backed Strike damage components cross carriers"
        )

    follow_ups, rider_effects = _project_strike_riders(
        strike,
        source_id=source_id,
        strike_id=strike_id,
    )
    raw_traits = strike.get("traits")
    if type(raw_traits) is not list or any(
        type(trait) is not dict
        or type(trait.get("normalizedText")) is not str
        or not trait["normalizedText"]
        for trait in raw_traits
    ):
        raise _errors.EngineInputError(
            "source-backed Strike trait projection is invalid"
        )
    traits = [
        trait["normalizedText"]
        for trait in raw_traits
    ]
    compiled = {
        "id": strike_id,
        "sourceOccurrenceId": occurrence_id,
        "sourceAddressSha256": source_address,
        "sourceLabelKey": strike["normalizedLabel"],
        "name": name,
        "kind": mode,
        "attackModifier": strike.get("attackModifier"),
        "traits": traits,
        "damage": {
            "sourceText": damage_carrier["rawText"],
            "dice": component["dice"],
            "flatAmount": component["flatAmount"],
            "modifier": component["modifier"],
            "type": component["type"],
            "components": projected_components,
            "riderEffects": rider_effects,
        },
        "followUps": follow_ups,
        "sourceDeferredDependencies": list(
            strike.get("deferredDependencies") or []
        ),
    }
    if type(compiled["attackModifier"]) is not int:
        raise _errors.EngineInputError(
            "source-backed Strike attack modifier is invalid"
        )

    targeting = strike.get("targeting")
    if (
        type(targeting) is not dict
        or targeting.get("status") != "mechanically-complete"
    ):
        raise _errors.EngineInputError(
            "source-backed Strike targeting projection is invalid"
        )
    if mode == "melee":
        targeting_kind = targeting.get("kind")
        if targeting_kind == "creature-default-reach":
            reach_feet = default_reach_feet
        elif (
            targeting_kind == "explicit-reach"
            and type(targeting.get("reachFeet")) is int
            and targeting["reachFeet"] >= 0
        ):
            reach_feet = targeting["reachFeet"]
        else:
            raise _errors.EngineInputError(
                "source-backed melee Strike targeting cannot be represented "
                f"by the engine public shape: {strike_id}"
            )
        compiled["reachFeet"] = reach_feet
    else:
        targeting_kind = targeting.get("kind")
        if targeting_kind in {
            "range-increment",
            "thrown-range-increment",
        }:
            feet = targeting.get("feet")
            reload_actions = targeting.get("reloadActions")
            if (
                type(feet) is not int
                or feet < 1
                or (
                    reload_actions is not None
                    and (
                        type(reload_actions) is not int
                        or reload_actions < 0
                    )
                )
            ):
                raise _errors.EngineInputError(
                    "source-backed ranged Strike distance is invalid"
                )
            compiled.update(
                {
                    "rangeIncrementFeet": feet,
                    "maximumRangeIncrements": 6,
                    "reloadActions": reload_actions,
                    "requiresDrawAfterUse": (
                        targeting.get("resourcePolicy")
                        == "thrown-source"
                    ),
                }
            )
        elif targeting_kind == "absolute-maximum":
            maximum_range_feet = targeting.get("feet")
            if (
                type(maximum_range_feet) is not int
                or maximum_range_feet < 1
                or targeting.get("reloadActions") is not None
                or targeting.get("resourcePolicy") != "not-stated"
            ):
                raise _errors.EngineInputError(
                    "source-backed absolute-maximum ranged Strike "
                    "targeting is invalid"
                )
            compiled.update(
                {
                    "rangeKind": "absolute-maximum",
                    "maximumRangeFeet": maximum_range_feet,
                }
            )
        else:
            raise _errors.EngineInputError(
                "source-backed ranged Strike targeting cannot be represented "
                f"by the engine public shape: {strike_id}"
            )
    return compiled


def _project_engine_strikes(
    plan: _CreatureStrikeCompilationPlan,
    *,
    default_reach_feet: int,
    source_id: str,
) -> list[dict[str, Any]]:
    if (
        type(plan) is not _CreatureStrikeCompilationPlan
        or plan.source_id != source_id
        or type(default_reach_feet) is not int
        or default_reach_feet < 0
    ):
        raise _errors.EngineInputError(
            "source-backed Strike plan context is invalid"
        )
    projection = _creature_strike_plan_projection(plan)
    strikes = projection.get("strikes")
    if (
        projection.get("facadeReady") is not True
        or type(strikes) is not list
        or not strikes
    ):
        raise _errors.EngineInputError(
            "source-backed Strike projection is not facade-ready"
        )
    result = [
        _project_engine_strike(
            strike,
            default_reach_feet=default_reach_feet,
            source_id=source_id,
        )
        for strike in strikes
    ]
    strike_ids = tuple(strike["id"] for strike in result)
    occurrence_ids = tuple(
        strike["sourceOccurrenceId"]
        for strike in result
    )
    if (
        len(strike_ids) != len(set(strike_ids))
        or len(occurrence_ids) != len(set(occurrence_ids))
    ):
        raise _errors.EngineInputError(
            "source-backed Strike identities overlap"
        )
    return result


_ABILITY_STRIKE_MODES = {
    "double-stride-strike": "melee",
    "pre-roll-tail-strike-reaction": "melee",
    "triggered-melee-strike-reaction": "melee",
    "turn-end-adjacent-strike-reaction": "melee",
    "ally-attacked-jaws-strike-reaction": "melee",
}


def _link_ability_strike_ids(
    abilities: list[dict[str, Any]],
    strikes: list[dict[str, Any]],
) -> None:
    """Resolve source label references to canonical mode-qualified IDs."""

    by_label_and_mode: dict[
        tuple[str, str],
        list[dict[str, Any]],
    ] = {}
    for strike in strikes:
        key = (
            str(strike["sourceLabelKey"]),
            str(strike["kind"]),
        )
        by_label_and_mode.setdefault(key, []).append(strike)

    def linked_strike_id(
        ability: dict[str, Any],
        source_label_key: Any,
        expected_mode: str,
    ) -> str | None:
        if type(source_label_key) is not str or not source_label_key:
            raise _errors.EngineInputError(
                "supported ability Strike reference is invalid: "
                f"{ability.get('name')}"
            )
        matches = by_label_and_mode.get(
            (source_label_key, expected_mode),
            [],
        )
        if len(matches) != 1:
            ability["supported"] = False
            ability.pop("mechanic", None)
            ability.pop("rule", None)
            return None
        return str(matches[0]["id"])

    for ability in abilities:
        mechanic = ability.get("mechanic")
        if (
            not ability.get("supported")
            or type(mechanic) is not dict
        ):
            continue
        mechanic_type = mechanic.get("type")
        if mechanic_type == "draconic-frenzy":
            multiset = mechanic.get("strikeMultiset")
            if (
                type(multiset) is not list
                or not multiset
                or any(type(item) is not dict for item in multiset)
            ):
                raise _errors.EngineInputError(
                    "supported Draconic Frenzy Strike references are invalid"
                )
            linked_entries = []
            for entry in multiset:
                linked = linked_strike_id(
                    ability,
                    entry.get("strikeId"),
                    "melee",
                )
                if linked is None:
                    break
                linked_entries.append({**entry, "strikeId": linked})
            if ability.get("supported"):
                mechanic["strikeMultiset"] = linked_entries
            continue
        if mechanic_type == "grabbed-target-strikes":
            linked = linked_strike_id(
                ability,
                mechanic.get("strikeName"),
                "melee",
            )
            if linked is not None:
                mechanic["strikeId"] = linked
            continue
        if mechanic_type == "swallow-whole-containment":
            linked = linked_strike_id(
                ability,
                mechanic.get("feederStrikeId"),
                "melee",
            )
            if linked is not None:
                mechanic["feederStrikeId"] = linked
            continue
        if mechanic_type in {
            _strike_save_control.MECHANIC_TYPE,
            _mechanics_fungus_leshy.SPORES_MECHANIC_TYPE,
        }:
            strike_labels = mechanic.get("strikeLabels")
            if (
                not isinstance(strike_labels, list)
                or not strike_labels
                or any(
                    type(label) is not str or not label
                    for label in strike_labels
                )
                or len(strike_labels) != len(set(strike_labels))
            ):
                ability["supported"] = False
                ability.pop("mechanic", None)
                ability.pop("rule", None)
                continue
            linked_strikes = [
                strike
                for label in strike_labels
                for strike in strikes
                if strike.get("sourceLabelKey") == label
            ]
            linked_ids = [str(strike["id"]) for strike in linked_strikes]

            def rider_key(rider: dict[str, Any]) -> str:
                return re.sub(
                    r"[^a-z0-9]+",
                    "-",
                    str(rider.get("name") or "").casefold(),
                ).strip("-")

            if (
                len(linked_strikes) != len(strike_labels)
                or [
                    strike["sourceLabelKey"]
                    for strike in linked_strikes
                ]
                != strike_labels
                or any(
                    [
                        rider_key(rider)
                        for rider in strike["damage"].get(
                            "riderEffects"
                        ) or []
                    ].count(ability["id"])
                    != 1
                    for strike in linked_strikes
                )
                or any(
                    rider_key(rider) == ability["id"]
                    and strike["id"] not in linked_ids
                    for strike in strikes
                    for rider in strike["damage"].get(
                        "riderEffects"
                    ) or []
                )
            ):
                ability["supported"] = False
                ability.pop("mechanic", None)
                ability.pop("rule", None)
                continue
            mechanic["strikeIds"] = linked_ids
            continue
        if (
            mechanic_type == "triggered-melee-strike-reaction"
            and mechanic.get("strikeSelection") == "any-melee-strike"
        ):
            linked_ids = [
                str(strike["id"])
                for strike in strikes
                if strike.get("kind") == "melee"
            ]
            if not linked_ids:
                ability["supported"] = False
                ability.pop("mechanic", None)
                ability.pop("rule", None)
            else:
                mechanic["strikeIds"] = linked_ids
            continue
        if "strikeId" not in mechanic:
            continue
        expected_mode = _ABILITY_STRIKE_MODES.get(mechanic_type)
        if expected_mode is None:
            raise _errors.EngineInputError(
                "supported ability has an unreviewed Strike reference: "
                f"{ability.get('name')}"
            )
        linked = linked_strike_id(
            ability,
            mechanic.get("strikeId"),
            expected_mode,
        )
        if linked is not None:
            mechanic["strikeId"] = linked
    for strike in strikes:
        del strike["sourceLabelKey"]


def _raw_source_value(value: Any) -> _mechanics_contracts.RawSourceValue:
    """Freeze one decoded JSON value without discarding pair order."""

    if type(value) in {
        _mechanics_contracts.RawSourceArray,
        _mechanics_contracts.RawSourceObject,
    }:
        return value
    if isinstance(value, _source_nodes.OrderedObject):
        return _mechanics_contracts.RawSourceObject.from_pairs(
            tuple(
                (raw_key, _raw_source_value(raw_value))
                for raw_key, raw_value in value.pairs
            )
        )
    if isinstance(value, list):
        return _mechanics_contracts.RawSourceArray(
            tuple(_raw_source_value(item) for item in value)
        )
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise _errors.EngineInputError(
        "creature ability raw source contains a non-JSON value: "
        f"{type(value).__name__}"
    )


def _raw_object(value: Any, label: str) -> _mechanics_contracts.RawSourceObject:
    try:
        converted = _raw_source_value(value)
    except (TypeError, ValueError) as failure:
        raise _errors.EngineInputError(
            f"{label} is not valid duplicate-preserving source"
        ) from failure
    if type(converted) is not _mechanics_contracts.RawSourceObject:
        raise _errors.EngineInputError(f"{label} must be an object")
    if (
        type(converted.members) is not tuple
        or any(
            type(member) is not _mechanics_contracts.RawSourceMember
            for member in converted.members
        )
    ):
        raise _errors.EngineInputError(
            f"{label} has invalid source members"
        )
    return converted


def _raw_ability_member(
    raw_key: str,
    raw_value: Any,
) -> _mechanics_contracts.RawSourceMember:
    try:
        return _mechanics_contracts.RawSourceMember(
            key=raw_key,
            value=_raw_source_value(raw_value),
        )
    except (TypeError, ValueError) as failure:
        raise _errors.EngineInputError(
            f"creature ability raw source is invalid: {raw_key}"
        ) from failure


def _raw_plain_value(value: Any, label: str) -> Any:
    if type(value) is _mechanics_contracts.RawSourceObject:
        result: dict[str, Any] = {}
        for member in value.members:
            if member.key in result:
                raise _errors.EngineInputError(
                    f"{label} field is duplicated: {member.key}"
                )
            result[member.key] = _raw_plain_value(
                member.value,
                f"{label}.{member.key}",
            )
        return result
    if type(value) is _mechanics_contracts.RawSourceArray:
        return [
            _raw_plain_value(item, f"{label}[]")
            for item in value.items
        ]
    if value is None or type(value) in {bool, int, float, str}:
        return value
    raise _errors.EngineInputError(
        f"{label} contains an invalid raw source value"
    )


def _raw_unique(
    value: _mechanics_contracts.RawSourceObject,
    key: str,
    *,
    required: bool = True,
    default: Any = None,
) -> Any:
    matches = value.values(key)
    if len(matches) > 1:
        raise _errors.EngineInputError(
            f"source field is duplicated: {key}"
        )
    if not matches:
        if required:
            raise _errors.EngineInputError(
                f"source field is missing: {key}"
            )
        return default
    return matches[0]


def _raw_source_flow_text(
    value: Any,
    label: str,
    *,
    ignore_empty_paragraphs: bool = False,
) -> str:
    if type(value) is str:
        return value.strip()
    if type(value) is not _mechanics_contracts.RawSourceObject:
        raise _errors.EngineInputError(
            f"{label} must be text or paragraph flow"
        )
    paragraphs = []
    for member in value.members:
        if member.key != "~.p" or type(member.value) is not str:
            raise _errors.EngineInputError(
                f"{label} contains unsupported source flow: {member.key}"
            )
        paragraph = member.value.strip()
        if paragraph or not ignore_empty_paragraphs:
            paragraphs.append(paragraph)
    if (
        (not paragraphs and not ignore_empty_paragraphs)
        or any(not paragraph for paragraph in paragraphs)
    ):
        raise _errors.EngineInputError(
            f"{label} contains an empty paragraph"
        )
    return "\n\n".join(paragraphs)


def _creature_description_text(
    block: _mechanics_contracts.RawSourceObject,
    creature_name: str,
) -> str:
    """Read article prose without flattening it into creature stat fields."""

    description = _raw_unique(
        block,
        "Description",
        required=False,
    )
    if description is None:
        return ""
    label = f"creature Description for {creature_name}"
    if type(description) is str:
        return _raw_source_flow_text(
            description,
            label,
            ignore_empty_paragraphs=True,
        )
    if type(description) is not _mechanics_contracts.RawSourceObject:
        raise _errors.EngineInputError(
            f"{label} must be text or paragraph flow"
        )
    if description.members and all(
        member.key == "~.p"
        for member in description.members
    ):
        return _raw_source_flow_text(
            description,
            label,
            ignore_empty_paragraphs=True,
        )
    named = description.values(creature_name)
    if len(description.members) != 1 or len(named) != 1:
        raise _errors.EngineInputError(
            f"{label} must contain exactly one matching article"
        )
    return _raw_source_flow_text(
        named[0],
        label,
        ignore_empty_paragraphs=True,
    )


def _creature_generic_description(
    block: _mechanics_contracts.RawSourceObject,
    creature_name: str,
) -> str:
    return _creature_description_text(block, creature_name) or (
        "No creature-specific description prose is present in the "
        "authenticated source block."
    )


def _raw_ability_description(
    value: Any,
    *,
    compiled_action: dict[str, Any] | None = None,
) -> tuple[int | str | None, str, list[str], str]:
    if type(value) is str:
        if compiled_action is not None and (
            compiled_action.get("token"),
            compiled_action.get("actionCost"),
            compiled_action.get("kind"),
        ) != (None, None, "passive"):
            raise _errors.EngineInputError(
                "prose ability action envelope disagrees with source"
            )
        return None, value.strip(), [], ""
    if type(value) is not _mechanics_contracts.RawSourceObject:
        raise _errors.EngineInputError(
            "creature ability must be an object or string"
        )
    fields: dict[str, Any] = {}
    for member in value.members:
        if member.key in fields:
            raise _errors.EngineInputError(
                "creature ability field is duplicated: "
                f"{member.key}"
            )
        fields[member.key] = member.value
    description_text = _raw_source_flow_text(
        fields.get("Description", ""),
        "creature ability Description",
    )
    traits = [
        trait.casefold()
        for trait in _source_nodes.string_list(
            _raw_plain_value(
                fields.get("Traits"),
                "creature ability Traits",
            ),
            "creature ability Traits",
        )
    ]
    trigger = str(fields.get("Trigger") or "").strip()
    if compiled_action is None:
        action_cost = _source_nodes.action_cost(fields.get("Action"))
    else:
        token = compiled_action.get("token")
        action_cost = compiled_action.get("actionCost")
        kind = compiled_action.get("kind")
        if (
            fields.get("Action") != token
            or (token, action_cost, kind)
            not in {
                (None, None, "passive"),
                ("single", 1, "action"),
                ("two", 2, "activity"),
                ("three", 3, "activity"),
                ("reaction", "reaction", "reaction"),
                ("free", "free", "free-action"),
            }
        ):
            raise _errors.EngineInputError(
                "creature ability action envelope disagrees with source"
            )
    return (
        action_cost,
        description_text,
        traits,
        trigger,
    )


def compile_abilities(
    block: (
        _source_nodes.OrderedObject
        | _mechanics_contracts.RawSourceObject
    ),
    *,
    creature_name: str,
    source_id: str,
    locator: str,
    ability_plan: _CreatureAbilityCompilationPlan | None = None,
    allow_supported_mechanics: bool = True,
    authority_mechanics: dict[str, dict[str, Any]] | None = None,
    authority_compilations: dict[str, object] | None = None,
    compiler_registry: _mechanics_registry.MechanicRegistry | None = None,
) -> list[dict[str, Any]]:
    if type(allow_supported_mechanics) is not bool:
        raise TypeError("ability authority support flag must be boolean")
    if (
        compiler_registry is not None
        and not isinstance(
            compiler_registry,
            _mechanics_registry.MechanicRegistry,
        )
    ):
        raise TypeError(
            "ability compiler registry must be a MechanicRegistry"
        )
    authority_mechanics = dict(authority_mechanics or {})
    authority_compilations = dict(authority_compilations or {})
    if isinstance(block, _source_nodes.OrderedObject):
        source_members = tuple(
            (member_ordinal, raw_key, raw_value, None)
            for member_ordinal, (raw_key, raw_value)
            in enumerate(block.pairs)
        )
    elif type(block) is _mechanics_contracts.RawSourceObject:
        source_members = tuple(
            (member_ordinal, member.key, member.value, member)
            for member_ordinal, member in enumerate(block.members)
        )
    else:
        raise _errors.EngineInputError(
            "creature block must be an object"
        )
    ability_projection = (
        None
        if ability_plan is None
        else _creature_ability_plan_projection(ability_plan)
    )
    planned_abilities = (
        ()
        if ability_projection is None
        else tuple(ability_projection["abilities"])
    )
    if ability_projection is not None and (
        ability_plan.source_id != source_id
        or ability_plan.locator != locator
        or ability_projection.get("creatureName") != creature_name
    ):
        raise _errors.EngineInputError(
            "creature ability compilation plan belongs to another source"
        )
    planned_by_ordinal = {
        item["memberOrdinal"]: item
        for item in planned_abilities
    }
    candidates = []
    raw_keys: set[str] = set()
    ability_ids: set[str] = set()
    for member_ordinal, raw_key, raw_value, raw_member in source_members:
        if not raw_key.startswith("!."):
            continue
        name = raw_key[2:].strip()
        ability_id = re.sub(
            r"[^a-z0-9]+",
            "-",
            name.casefold(),
        ).strip("-")
        if (
            not ability_id
            or raw_key in raw_keys
            or ability_id in ability_ids
        ):
            raise _errors.EngineInputError(
                f"creature ability name is invalid or duplicated: {name}"
            )
        raw_keys.add(raw_key)
        ability_ids.add(ability_id)
        candidates.append(
            (
                member_ordinal,
                raw_key,
                raw_value,
                name,
                ability_id,
                raw_member,
            )
        )
    if ability_projection is not None and (
        len(candidates) != len(planned_abilities)
        or tuple(item[0] for item in candidates)
        != tuple(item["memberOrdinal"] for item in planned_abilities)
    ):
        raise _errors.EngineInputError(
            "creature ability compilation plan is incomplete"
        )

    lossless_candidates = []
    for (
        member_ordinal,
        raw_key,
        raw_value,
        name,
        ability_id,
        raw_member,
    ) in candidates:
        exact_member = (
            raw_member
            if raw_member is not None
            else _raw_ability_member(raw_key, raw_value)
        )
        planned_ability = planned_by_ordinal.get(member_ordinal)
        if planned_ability is not None and (
            planned_ability.get("abilityLabel") != name
            or planned_ability.get("rawAbilityMemberJson")
            != _source_authority.canonical_raw_bytes(
                _mechanics_contracts.RawSourceObject((exact_member,))
            ).decode("utf-8")
        ):
            raise _errors.EngineInputError(
                "creature ability compilation plan disagrees with source"
            )
        lossless_candidates.append(
            (
                member_ordinal,
                exact_member.value,
                name,
                ability_id,
                exact_member,
                planned_ability,
            )
        )

    result = []
    for (
        _member_ordinal,
        raw_value,
        name,
        ability_id,
        raw_member,
        planned_ability,
    ) in lossless_candidates:
        cost, description, traits, trigger = (
            _raw_ability_description(
                raw_value,
                compiled_action=(
                    None
                    if planned_ability is None
                    else planned_ability["action"]
                ),
            )
        )
        kind = (
            "reaction"
            if cost == "reaction"
            else "free-action"
            if cost == "free"
            else "activity"
            if isinstance(cost, int)
            else "passive"
        )
        ability = {
            "id": ability_id,
            "name": name,
            "kind": kind,
            "actionCost": (
                cost
                if isinstance(cost, int) or cost == "free"
                else None
            ),
            "traits": traits,
            "description": description,
            "supported": False,
            "deferredMechanics": [],
        }
        if planned_ability is not None:
            ability["actionEnvelope"] = planned_ability["action"]
        if trigger:
            ability["trigger"] = trigger

        if cost == "free":
            result.append(ability)
            continue
        source = _mechanics_contracts.AbilitySource(
            source_label=name,
            action_cost=cost,
            kind=kind,
            traits=tuple(traits),
            trigger=trigger,
            description=description,
            source_id=source_id,
            locator=locator,
            creature_name=creature_name,
            raw_member=raw_member,
        )
        matches = []
        if allow_supported_mechanics:
            registrations = (
                _mechanics_registry.ABILITY_COMPILERS
                if compiler_registry is None
                else compiler_registry.ability_compilers
            )
            for registration in registrations:
                patch = registration.match(source)
                if patch is None:
                    continue
                try:
                    patch = _mechanics_registry.bind_ability_authority(
                        patch,
                        authority_mechanics=authority_mechanics,
                        authority_compilations=authority_compilations,
                    )
                except (
                    _animated_construct_armor
                    .AnimatedConstructArmorError,
                    ValueError,
                ) as failure:
                    raise _errors.EngineInputError(
                        f"creature ability authority binding failed: "
                        f"{name}: {failure}"
                    ) from failure
                if patch is None:
                    continue
                matches.append((registration, patch))
        else:
            ability["deferredMechanics"].append(
                "source-authority:core-pc1"
            )
        if len(matches) > 1:
            matching_ids = ", ".join(
                registration.compiler_id
                for registration, _patch in matches
            )
            raise _errors.EngineInputError(
                f"creature ability has ambiguous source grammar: "
                f"{name} ({matching_ids})"
            )
        if matches:
            _registration, patch = matches[0]
            ability.update(patch.as_ability_update())
        result.append(ability)
    try:
        linked = _mechanics_gaze.link_gaze_abilities(result)
        return _mechanics_flash_beetle.link_flash_beetle_abilities(
            linked,
            source_id=source_id,
            locator=locator,
            creature_name=creature_name,
        )
    except ValueError as failure:
        raise _errors.EngineInputError(
            "creature linked ability validation failed: "
            f"{failure}"
        ) from failure


def _has_explicit_free_action(
    block: _mechanics_contracts.RawSourceObject,
    /,
) -> bool:
    """Select the bounded envelope integration lane from exact source."""

    if type(block) is not _mechanics_contracts.RawSourceObject:
        raise TypeError(
            "free-action envelope selection requires an exact source block"
        )
    return any(
        member.key.startswith("!.")
        and type(member.value) is _mechanics_contracts.RawSourceObject
        and any(
            field.key == "Action" and field.value == "free"
            for field in member.value.members
        )
        for member in block.members
    )


def creature_blocks(
    node: (
        _source_nodes.OrderedObject
        | _mechanics_contracts.RawSourceObject
    ),
    path: tuple[_source_authority.RawMemberStep, ...] = (),
) -> list[
    tuple[
        tuple[_source_authority.RawMemberStep, ...],
        _mechanics_contracts.RawSourceObject,
        _mechanics_contracts.RawSourceObject,
    ]
]:
    """Return exact creature paths, blocks, and immediate containers."""

    raw_node = _raw_object(node, "creature source target")
    result = []
    for ordinal, member in enumerate(raw_node.members):
        step = _source_authority.RawMemberStep(
            member.key,
            ordinal,
        )
        if member.key == "^.creature":
            if type(member.value) is not (
                _mechanics_contracts.RawSourceObject
            ):
                raise _errors.EngineInputError(
                    "^.creature source block must be an object"
                )
            result.append(
                ((*path, step), member.value, raw_node)
            )
        elif type(member.value) is (
            _mechanics_contracts.RawSourceObject
        ):
            result.extend(
                creature_blocks(
                    member.value,
                    (*path, step),
                )
            )
    return result


def creature_fields(
    block: (
        _source_nodes.OrderedObject
        | _mechanics_contracts.RawSourceObject
    ),
) -> dict[str, Any]:
    """Decode stat fields while leaving ordered ability source flow untouched."""

    raw_block = _raw_object(block, "creature block")
    result: dict[str, Any] = {}
    seen_fields: set[str] = set()
    for member in raw_block.members:
        key = member.key
        if key.startswith("!."):
            continue
        if key in seen_fields:
            raise _errors.EngineInputError(
                f"creature field is duplicated: {key}"
            )
        seen_fields.add(key)
        if key in CREATURE_PRESENTATION_FIELDS:
            continue
        result[key] = _raw_plain_value(
            member.value,
            f"creature.{key}",
        )
    return result


@dataclass(frozen=True)
class _CreatureSourceTarget:
    source_id: str
    locator: str
    section_id: str
    content_path: tuple[str, ...]


@dataclass(frozen=True)
class _ResolvedCreatureSource:
    target: _CreatureSourceTarget
    expected_name: str
    block: _mechanics_contracts.RawSourceObject
    creature_selection: _source_authority.VerifiedSourceSelection
    creature_container: _mechanics_contracts.RawSourceObject


def _semantic_member_path(
    path: tuple[_source_authority.RawPathStep, ...],
    label: str,
) -> tuple[str, ...]:
    result = []
    for step in path:
        if type(step) is not _source_authority.RawMemberStep:
            raise _errors.EngineInputError(
                f"{label} contains a non-object path step"
            )
        if step.raw_key.startswith("~."):
            continue
        result.append(_source_nodes.semantic_key(step.raw_key))
    return tuple(result)


def _resolve_source_creature(
    authority: _source_authority.SourceAuthorityAdapter,
    source_id: str,
    locator: str,
    /,
) -> _ResolvedCreatureSource:
    """Resolve one exact Monster Core creature without compiling mechanics."""

    if type(authority) is not (
        _source_authority.SourceAuthorityAdapter
    ):
        raise TypeError(
            "creature compiler requires an exact "
            "SourceAuthorityAdapter"
        )
    if (
        type(source_id) is not str
        or source_id not in CREATURE_ABILITY_GLOSSARIES
    ):
        raise _errors.EngineInputError(
            "creature source must be core-mc1 or core-mc2"
        )
    if (
        type(locator) is not str
        or not locator
        or locator != locator.strip()
    ):
        raise _errors.EngineInputError(
            "creature locator must be non-empty trimmed text"
        )
    expected_name = authority.toc_label(source_id, locator)

    root_address = authority.address(
        source_id=source_id,
        locator=locator,
    )
    root_selection = authority.validate_selection(
        authority.resolve(root_address)
    )
    if type(root_selection.selected_value) is not (
        _mechanics_contracts.RawSourceObject
    ):
        raise _errors.EngineInputError(
            "creature source target must be an object"
        )
    blocks = creature_blocks(root_selection.selected_value)
    if len(blocks) > 1:
        blocks = [
            candidate
            for candidate in blocks
            if (
                len(candidate[1].values("Name")) == 1
                and type(candidate[1].values("Name")[0]) is str
                and candidate[1].values("Name")[0].strip()
                == expected_name
            )
        ]
    if len(blocks) != 1:
        raise _errors.EngineInputError(
            "creature target must contain exactly one semantic "
            "^.creature block matching its authenticated ToC label"
        )
    creature_path, discovered_block, discovered_container = (
        blocks[0]
    )
    creature_address = authority.address(
        source_id=source_id,
        locator=locator,
        carrier_path=creature_path,
    )
    creature_selection = authority.validate_selection(
        authority.resolve(creature_address)
    )
    if (
        type(creature_selection.selected_value)
        is not _mechanics_contracts.RawSourceObject
        or creature_selection.selection_sha256
        != _source_authority.raw_source_sha256(discovered_block)
    ):
        raise _errors.EngineInputError(
            "creature source block disagrees with its exact target"
        )
    block = creature_selection.selected_value

    container_path = creature_path[:-1]
    if container_path:
        container_address = authority.address(
            source_id=source_id,
            locator=locator,
            carrier_path=container_path,
        )
        container_selection = authority.validate_selection(
            authority.resolve(container_address)
        )
    else:
        container_selection = root_selection
    if (
        type(container_selection.selected_value)
        is not _mechanics_contracts.RawSourceObject
        or _source_authority.raw_source_sha256(
            container_selection.selected_value
        )
        != _source_authority.raw_source_sha256(
            discovered_container
        )
    ):
        raise _errors.EngineInputError(
            "creature source container disagrees with its exact target"
        )

    content_path = authority.toc_content_path(source_id, locator)
    source_name = str(
        creature_fields(block).get("Name") or ""
    ).strip()
    if source_name != expected_name:
        raise _errors.EngineInputError(
            "creature name does not match its source target"
        )
    return _ResolvedCreatureSource(
        target=_CreatureSourceTarget(
            source_id=source_id,
            locator=locator,
            section_id=root_address.section_id,
            content_path=content_path,
        ),
        expected_name=expected_name,
        block=block,
        creature_selection=creature_selection,
        creature_container=container_selection.selected_value,
    )


def source_creature_icon_asset_key(
    authority: _source_authority.SourceAuthorityAdapter,
    source_id: str,
    locator: str,
    /,
) -> str | None:
    """Resolve only the current icon for one authenticated source creature."""

    resolved = _resolve_source_creature(
        authority,
        source_id,
        locator,
    )
    return creature_icon_asset_key(
        source_id,
        creature_fields(resolved.block).get("Icon"),
    )


def source_block_icon_asset_key(
    authority: _source_authority.SourceAuthorityAdapter,
    source_id: str,
    locator: str,
    /,
) -> str | None:
    """Resolve an icon declared directly by one authenticated source target."""

    if type(authority) is not (
        _source_authority.SourceAuthorityAdapter
    ):
        raise TypeError(
            "source icon resolver requires an exact "
            "SourceAuthorityAdapter"
        )
    if type(source_id) is not str or not source_id:
        raise _errors.EngineInputError(
            "source icon source must be non-empty text"
        )
    if (
        type(locator) is not str
        or not locator
        or locator != locator.strip()
    ):
        raise _errors.EngineInputError(
            "source icon locator must be non-empty trimmed text"
        )
    expected_name = authority.toc_label(source_id, locator)
    selection = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=source_id,
                locator=locator,
            )
        )
    )
    block = selection.selected_value
    if (
        type(block) is not _mechanics_contracts.RawSourceObject
        or selection.raw_member is not None
    ):
        raise _errors.EngineInputError(
            "source icon target must be an exact object"
        )
    names = block.values("Name")
    if (
        len(names) != 1
        or type(names[0]) is not str
        or names[0].strip() != expected_name
    ):
        raise _errors.EngineInputError(
            "source icon target name does not match its "
            "authenticated ToC label"
        )
    icons = block.values("Icon")
    if len(icons) > 1:
        raise _errors.EngineInputError(
            "source Icon is duplicated"
        )
    return source_icon_asset_key(
        source_id,
        icons[0] if icons else None,
    )


def _compile_source_creature(
    authority: _source_authority.SourceAuthorityAdapter,
    source_id: str,
    locator: str,
    /,
    *,
    compiler_registry: _mechanics_registry.MechanicRegistry | None,
) -> dict[str, Any]:
    """Compile one exact creature with a selected or legacy compiler table."""

    if (
        compiler_registry is not None
        and not isinstance(
            compiler_registry,
            _mechanics_registry.MechanicRegistry,
        )
    ):
        raise TypeError(
            "source creature compiler registry must be a MechanicRegistry"
        )

    resolved = _resolve_source_creature(
        authority,
        source_id,
        locator,
    )
    block = resolved.block
    stat_plan = (
        _compile_creature_stat_plan(
            authority,
            resolved.creature_selection,
        )
        if source_id == "core-mc1"
        else None
    )
    strike_plan = _compile_creature_strike_plan(
        authority,
        resolved.creature_selection,
    )
    ability_plan = (
        _compile_creature_ability_plan(
            authority,
            resolved.creature_selection,
        )
        if _has_explicit_free_action(block)
        else None
    )
    spellcasting_plan = _compile_creature_spellcasting_plan(
        authority,
        resolved.creature_selection,
    )
    authority_requirements = (
        _mechanics_registry.CREATURE_AUTHORITY_REQUIREMENTS.get(
            (source_id, locator),
            frozenset(),
        )
    )
    mechanics_authority_available = authority_requirements.issubset(
        authority.allowed_source_ids
    )
    if mechanics_authority_available:
        for rule_source_id, rule_locator in (
            _mechanics_registry
            .CREATURE_RULE_AUTHORITY_LOCATORS.get(
                (source_id, locator),
                (),
            )
        ):
            try:
                authority.validate_selection(
                    authority.resolve(
                        authority.address(
                            source_id=rule_source_id,
                            locator=rule_locator,
                        )
                    )
                )
            except _source_authority.SourceAuthorityError:
                mechanics_authority_available = False
                break
    improved_push_compilation = None
    if (
        source_id == _zombie_brute.SOURCE_ID
        and locator == _zombie_brute.LOCATOR
        and mechanics_authority_available
    ):
        requirement = next(
            (
                item
                for item in (
                    _forced_movement
                    .forced_movement_consumer_requirements()
                )
                if item.rule_id == _zombie_brute.CONSUMER_RULE_ID
            ),
            None,
        )
        if requirement is None:
            raise _errors.EngineInputError(
                "Zombie Brute Improved Push compiler dossier is missing"
            )
        try:
            compiled_improved_push = (
                _forced_movement.compile_forced_movement_rider(
                    authority,
                    authority.resolve_rule(requirement).receipt,
                )
            )
            _forced_movement.validate_compiled_forced_movement(
                authority,
                compiled_improved_push,
            )
            improved_push_compilation = (
                compiled_improved_push.as_serialized(authority)
            )
            _plague_zombie_abilities.verify_zombie_brute_source(
                authority
            )
        except (
            _forced_movement.ForcedMovementCompileError,
            _source_authority.SourceAuthorityError,
        ) as failure:
            raise _errors.EngineInputError(
                "Zombie Brute Improved Push authority link failed: "
                f"{failure}"
            ) from failure
    construct_armor = None
    if mechanics_authority_available:
        try:
            construct_armor = (
                _animated_construct_armor
                .compile_animated_construct_armor(
                    authority,
                    resolved.creature_selection,
                )
            )
        except (
            _animated_construct_armor.AnimatedConstructArmorError,
            _source_authority.SourceAuthorityError,
        ) as failure:
            raise _errors.EngineInputError(
                "Animated Armor Construct Armor authority link failed: "
                f"{failure}"
            ) from failure
    swallow_whole_compilation = None
    if (
        source_id == "core-mc1"
        and locator == "341.2"
        and mechanics_authority_available
    ):
        requirement = next(
            (
                item
                for item in (
                    _swallow_whole
                    .swallow_whole_consumer_requirements()
                )
                if item.rule_id == "swallow-whole:warg"
            ),
            None,
        )
        if requirement is None:
            raise _errors.EngineInputError(
                "Warg Swallow Whole compiler dossier is missing"
            )
        try:
            compiled_swallow = _swallow_whole.compile_swallow_whole(
                authority,
                authority.resolve_rule(requirement).receipt,
            )
            linked_swallow = _swallow_whole.link_swallow_whole(
                authority,
                compiled_swallow,
            )
            swallow_whole_compilation = {
                "familyId": "swallow-whole",
                "consumerRuleId": (
                    linked_swallow.compiled.consumer_rule.rule_id
                ),
                "feederRuleId": (
                    linked_swallow.selected_feeder_rule.rule_id
                ),
                "provider": {
                    "sourceId": "core-mc1",
                    "locator": "358.2",
                },
                "maximumTargetSize": (
                    linked_swallow.compiled.maximum_target_size
                ),
                "damage": [
                    {
                        "dice": {
                            "count": item.dice_count,
                            "sides": item.die_sides,
                        },
                        "modifier": item.modifier,
                        "type": item.damage_type,
                    }
                    for item in linked_swallow.compiled.internal_damage
                ],
                "escapeDC": linked_swallow.compiled.escape_dc,
                "ruptureThreshold": (
                    linked_swallow.compiled.rupture_threshold
                ),
                "genericRuntimeReady": (
                    linked_swallow.runtime_ready
                ),
                "runtimeActivation": (
                    "bounded-warg-containment"
                ),
            }
        except (
            _source_authority.SourceAuthorityError,
            _swallow_whole.SwallowWholeCompileError,
        ) as failure:
            raise _errors.EngineInputError(
                f"Warg Swallow Whole authority link failed: {failure}"
            ) from failure
    stench_compilation = None
    stench_members = [
        (ordinal, member)
        for ordinal, member in enumerate(block.members)
        if member.key == "!.Stench"
    ]
    if (
        source_id == "core-mc1"
        and locator in {"163.1", "163.3", "352.3"}
        and stench_members
        and mechanics_authority_available
    ):
        if len(stench_members) != 1:
            raise _errors.EngineInputError(
                "Stench source member is duplicated"
            )
        member_ordinal, stench_member = stench_members[0]
        try:
            consumer_address = authority.address(
                source_id=source_id,
                locator=locator,
                carrier_path=(
                    resolved.creature_selection.address.carrier_path
                ),
                selection_path=(
                    _source_authority.RawMemberStep(
                        "!.Stench",
                        member_ordinal,
                    ),
                ),
            )
            consumer = authority.validate_selection(
                authority.resolve(consumer_address)
            )
            cost, description, traits, trigger = (
                _raw_ability_description(stench_member.value)
            )
            if cost is not None:
                raise _errors.EngineInputError(
                    "Stench source action envelope is invalid"
                )
            providers = tuple(
                authority.resolve_rule(requirement)
                for requirement in (
                    _mechanics_stench
                    .stench_provider_requirements()
                )
            )
            stench_source = _mechanics_contracts.AbilitySource(
                source_label="Stench",
                action_cost=None,
                kind="passive",
                traits=tuple(traits),
                trigger=trigger,
                description=description,
                source_id=source_id,
                locator=locator,
                creature_name=resolved.expected_name,
                raw_member=stench_member,
            )
            stench_compilation = (
                _mechanics_stench.compile_stench_verified(
                    stench_source,
                    authority=authority,
                    consumer=consumer,
                    ordered_providers=providers,
                )
            )
            if stench_compilation is None:
                raise _errors.EngineInputError(
                    "Stench source and provider authority did not verify"
                )
        except _source_authority.SourceAuthorityError as failure:
            raise _errors.EngineInputError(
                f"Stench authority link failed: {failure}"
            ) from failure
    elif (
        source_id == "core-mc1"
        and locator in {"163.1", "163.3", "352.3"}
        and mechanics_authority_available
    ):
        raise _errors.EngineInputError(
            "reviewed Stench authority member is missing"
        )
    ghoul_authority_mechanics = (
        _mechanics_ghoul.verified_authority_mechanics(authority)
        if (
            source_id == _mechanics_ghoul.SOURCE_ID
            and locator in _mechanics_ghoul.CREATURE_LOCATORS
            and mechanics_authority_available
        )
        else {}
    )
    if (
        source_id == _plague_zombie_abilities.SOURCE_ID
        and locator == _plague_zombie_abilities.LOCATOR
        and mechanics_authority_available
    ):
        try:
            _plague_zombie_abilities.verify_current_source(authority)
        except _source_authority.SourceAuthorityError as failure:
            raise _errors.EngineInputError(
                f"Plague Zombie inherited authority link failed: {failure}"
            ) from failure
    if (
        source_id == _mechanics_battle_cry.SOURCE_ID
        and locator == _mechanics_battle_cry.LOCATOR
        and mechanics_authority_available
    ):
        try:
            _mechanics_battle_cry.verify_current_source(authority)
        except (
            _errors.EngineInputError,
            _source_authority.SourceAuthorityError,
        ) as failure:
            raise _errors.EngineInputError(
                f"Orc Commander Battle Cry authority link failed: {failure}"
            ) from failure
    if (
        source_id == _mechanics_fungus_leshy.SOURCE_ID
        and locator == _mechanics_fungus_leshy.LOCATOR
        and mechanics_authority_available
    ):
        try:
            _mechanics_fungus_leshy.verify_current_source(authority)
        except (
            _errors.EngineInputError,
            _source_authority.SourceAuthorityError,
        ) as failure:
            raise _errors.EngineInputError(
                f"Fungus Leshy spores authority link failed: {failure}"
            ) from failure
    authority_compilations: dict[str, object] = {}
    if swallow_whole_compilation is not None:
        authority_compilations[
            _mechanics_warg.SWALLOW_WHOLE_MECHANIC_TYPE
        ] = swallow_whole_compilation
    if stench_compilation is not None:
        authority_compilations[
            _mechanics_stench.STENCH_MECHANIC_TYPE
        ] = stench_compilation
    result = _compile_creature_raw(
        resolved.target,
        block,
        resolved.creature_container,
        expected_name=resolved.expected_name,
        stat_plan=stat_plan,
        strike_plan=strike_plan,
        ability_plan=ability_plan,
        spellcasting_plan=spellcasting_plan,
        swallow_whole_compilation=swallow_whole_compilation,
        allow_supported_mechanics=mechanics_authority_available,
        authority_mechanics={
            **ghoul_authority_mechanics,
            **(
                {}
                if construct_armor is None
                else {
                    _animated_construct_armor.MECHANIC_TYPE: (
                        construct_armor
                    )
                }
            ),
        },
        authority_compilations=authority_compilations,
        compiler_registry=compiler_registry,
    )
    if construct_armor is not None:
        try:
            _animated_construct_armor.activate_definition(
                result,
                construct_armor,
            )
        except _animated_construct_armor.AnimatedConstructArmorError as failure:
            raise _errors.EngineInputError(
                "Animated Armor Construct Armor definition link failed: "
                f"{failure}"
            ) from failure
    if (
        source_id == _plague_zombie_abilities.SOURCE_ID
        and locator == _plague_zombie_abilities.LOCATOR
        and mechanics_authority_available
    ):
        _plague_zombie_abilities.activate_plague_zombie_definition_links(
            result
        )
        _plague_zombie_abilities.validate_plague_zombie_definition_links(
            result
        )
    if (
        source_id == _mechanics_fungus_leshy.SOURCE_ID
        and locator == _mechanics_fungus_leshy.LOCATOR
        and mechanics_authority_available
    ):
        _mechanics_fungus_leshy.validate_definition_links(result)
    if improved_push_compilation is not None:
        _zombie_brute.activate_definition(
            result,
            improved_push_compilation,
        )
    return result


def compile_source_creature(
    authority: _source_authority.SourceAuthorityAdapter,
    source_id: str,
    locator: str,
    /,
) -> dict[str, Any]:
    """Compile through the temporary production-wide compiler facade."""

    return _compile_source_creature(
        authority,
        source_id,
        locator,
        compiler_registry=None,
    )


def compile_source_creature_with_registry(
    authority: _source_authority.SourceAuthorityAdapter,
    source_id: str,
    locator: str,
    /,
    *,
    registry: _mechanics_registry.MechanicRegistry,
) -> dict[str, Any]:
    """Compile through one explicitly selected semantic compiler registry."""

    if not isinstance(registry, _mechanics_registry.MechanicRegistry):
        raise TypeError(
            "source creature compiler registry must be a MechanicRegistry"
        )
    return _compile_source_creature(
        authority,
        source_id,
        locator,
        compiler_registry=registry,
    )


def source_creature_description(
    authority: _source_authority.SourceAuthorityAdapter,
    source_id: str,
    locator: str,
    /,
) -> str:
    """Return exact public article prose or the canonical absence statement."""

    resolved = _resolve_source_creature(authority, source_id, locator)
    fields = creature_fields(resolved.block)
    name = str(fields.get("Name") or "").strip()
    if not name:
        raise _errors.EngineInputError("creature Name is empty")
    if resolved.expected_name is not None and name != resolved.expected_name:
        raise _errors.EngineInputError(
            "creature name does not match its source target"
        )
    return _creature_generic_description(resolved.block, name)


def _compile_creature_raw(
    target: _CreatureSourceTarget,
    block: _mechanics_contracts.RawSourceObject,
    creature_container: _mechanics_contracts.RawSourceObject,
    *,
    expected_name: str | None,
    stat_plan: _CreatureStatCompilationPlan | None = None,
    strike_plan: _CreatureStrikeCompilationPlan,
    ability_plan: _CreatureAbilityCompilationPlan | None,
    spellcasting_plan: _CreatureSpellcastingCompilationPlan | None,
    swallow_whole_compilation: dict[str, Any] | None = None,
    allow_supported_mechanics: bool = True,
    authority_mechanics: dict[str, dict[str, Any]] | None = None,
    authority_compilations: dict[str, object] | None = None,
    compiler_registry: _mechanics_registry.MechanicRegistry | None = None,
) -> dict[str, Any]:
    """Compile one already authenticated exact raw creature block."""

    source_id = target.source_id
    locator = target.locator
    section_id = target.section_id
    content_path = target.content_path
    fields = creature_fields(block)
    name = str(fields.get("Name") or "").strip()
    if not name:
        raise _errors.EngineInputError("creature Name is empty")
    if expected_name is not None and name != expected_name:
        raise _errors.EngineInputError("creature name does not match its source target")
    size = str(fields.get("Size") or "").strip().casefold()
    planned_spatial_profile = _creature_stat_plan_legacy_space(
        stat_plan
    )
    if planned_spatial_profile is not None:
        spatial_profile = planned_spatial_profile
    elif size == "tiny":
        spatial_profile = {
            "sizeRank": 0,
            "reachProfile": "tiny",
            "widthSquares": 1,
            "heightSquares": 1,
            "spaceFeet": 2.5,
            "defaultReachFeet": 0,
        }
    elif size == "small":
        spatial_profile = {
            "sizeRank": 1,
            "reachProfile": "small",
            "widthSquares": 1,
            "heightSquares": 1,
            "spaceFeet": 5,
            "defaultReachFeet": 5,
        }
    elif size == "medium":
        spatial_profile = {
            "sizeRank": 2,
            "reachProfile": "medium",
            "widthSquares": 1,
            "heightSquares": 1,
            "spaceFeet": 5,
            "defaultReachFeet": 5,
        }
    elif size == "large":
        narrative = " ".join(
            (
                *(
                    str(item)
                    for item in creature_container.values("~.p")
                ),
                _creature_description_text(block, name),
            )
        )
        if not re.search(r"\b\d+\s+feet\s+long\b", narrative, re.IGNORECASE):
            raise _errors.EngineInputError("Large creature requires an explicit tall or long reach profile")
        spatial_profile = {
            "sizeRank": 3,
            "reachProfile": "long",
            "widthSquares": 2,
            "heightSquares": 2,
            "spaceFeet": 10,
            "defaultReachFeet": 5,
        }
    else:
        raise _errors.EngineInputError(f"creature size is not supported by this spike: {size}")

    default_reach_feet = int(spatial_profile["defaultReachFeet"])
    abilities = compile_abilities(
        block,
        creature_name=name,
        source_id=source_id,
        locator=locator,
        ability_plan=ability_plan,
        allow_supported_mechanics=allow_supported_mechanics,
        authority_mechanics=authority_mechanics,
        authority_compilations=authority_compilations,
        compiler_registry=compiler_registry,
    )
    strikes = _project_engine_strikes(
        strike_plan,
        default_reach_feet=default_reach_feet,
        source_id=source_id,
    )
    _link_ability_strike_ids(abilities, strikes)
    strikes_by_id = {
        str(strike["id"]): strike
        for strike in strikes
    }
    for ability in abilities:
        mechanic = ability.get("mechanic")
        reactive_strike_ids = (
            list(mechanic.get("strikeIds") or [])
            if isinstance(mechanic, dict)
            and mechanic.get("strikeSelection") == "any-melee-strike"
            else [str(mechanic.get("strikeId") or "")]
            if isinstance(mechanic, dict)
            else []
        )
        if (
            ability.get("supported")
            and isinstance(mechanic, dict)
            and mechanic.get("type") == "triggered-melee-strike-reaction"
            and (
                not reactive_strike_ids
                or len(reactive_strike_ids) != len(set(reactive_strike_ids))
                or any(
                    strikes_by_id.get(strike_id, {}).get("kind") != "melee"
                    for strike_id in reactive_strike_ids
                )
            )
        ):
            ability["supported"] = False
            ability.pop("mechanic", None)
            ability.pop("rule", None)
    abilities_by_id = {str(ability["id"]): ability for ability in abilities}
    for strike in strikes:
        rider_effects = strike["damage"]["riderEffects"]
        rider_name_counts: dict[str, int] = {}
        for rider in rider_effects:
            rider_key = re.sub(
                r"[^a-z0-9]+",
                "-",
                str(rider["name"]).casefold(),
            ).strip("-")
            rider_name_counts[rider_key] = (
                rider_name_counts.get(rider_key, 0) + 1
            )
        for rider in rider_effects:
            rider_key = re.sub(
                r"[^a-z0-9]+",
                "-",
                str(rider["name"]).casefold(),
            ).strip("-")
            if rider_name_counts[rider_key] != 1:
                continue
            ability = abilities_by_id.get(
                rider_key
            )
            if ability is None:
                continue
            rider.update(
                {
                    "name": ability["name"],
                    "abilityId": ability["id"],
                }
            )
            mechanic_type = ability.get("mechanic", {}).get("type")
            if ability.get("supported") and mechanic_type in {
                "affliction",
                "conditional-damage",
                _strike_save_control.MECHANIC_TYPE,
                _mechanics_fungus_leshy.SPORES_MECHANIC_TYPE,
                _zombie_rot.MECHANIC_TYPE,
            }:
                if (
                    mechanic_type in {
                        _strike_save_control.MECHANIC_TYPE,
                        _mechanics_fungus_leshy.SPORES_MECHANIC_TYPE,
                    }
                    and strike["id"]
                    not in ability["mechanic"].get("strikeIds", [])
                ):
                    continue
                rider.update(
                    {
                        "supported": True,
                        "effectType": mechanic_type,
                    }
                )
    for ability in abilities:
        mechanic = ability.get("mechanic")
        if (
            not ability.get("supported")
            or not isinstance(mechanic, dict)
            or mechanic.get("type") != "triggered-melee-strike-reaction"
        ):
            continue
        unrestricted = (
            mechanic.get("strikeSelection") == "any-melee-strike"
        )
        candidate_ids = (
            list(mechanic.get("strikeIds") or [])
            if unrestricted
            else [str(mechanic.get("strikeId") or "")]
        )
        valid_ids = [
            strike_id
            for strike_id in candidate_ids
            if not any(
                not rider.get("supported")
                for rider in strikes_by_id[strike_id]["damage"].get(
                    "riderEffects"
                ) or []
            )
        ]
        if unrestricted and valid_ids:
            mechanic["strikeIds"] = valid_ids
        elif len(valid_ids) != 1:
            ability["supported"] = False
            ability.pop("mechanic", None)
            ability.pop("rule", None)
    inventory = parse_inventory(fields.get("Items"))

    def planned_integer(field: str, label: str) -> int:
        planned = _creature_stat_plan_base_value(
            stat_plan,
            field,
        )
        return (
            planned
            if planned is not None
            else _source_nodes.integer(fields.get(field), label)
        )

    damage_defenses, runtime_blockers = (
        _damage_defense_runtime_projection(
            stat_plan,
            fields,
            source_id=source_id,
            source_locator=locator,
        )
    )
    speeds = _creature_stat_plan_speeds(stat_plan)
    if speeds is None:
        speeds = _source_only_numeric_speeds(
            fields.get("Speed")
        )
    result = {
        "schema": 1,
        "id": f"{source_id}:{locator}",
        "source": {
            "sourceId": source_id,
            "locator": locator,
            "sectionId": section_id,
            "contentPath": [str(part) for part in content_path],
        },
        "name": name,
        "level": _source_nodes.integer(fields.get("Level"), "creature Level"),
        "size": size,
        "space": {
            **spatial_profile,
            "rule": {"sourceId": "core-pc1", "locator": "421.8"},
        },
        "traits": [trait.casefold() for trait in _source_nodes.string_list(fields.get("Traits"), "creature Traits")],
        "languages": _source_nodes.string_list(
            fields.get("Languages"),
            "creature Languages",
        ),
        "perception": parse_perception(fields.get("Perception")),
        "skills": parse_skills(fields.get("Skills")),
        "attributes": {
            "strength": _source_nodes.integer(fields.get("Str"), "creature Str"),
            "dexterity": _source_nodes.integer(fields.get("Dex"), "creature Dex"),
            "constitution": _source_nodes.integer(fields.get("Con"), "creature Con"),
            "intelligence": _source_nodes.integer(fields.get("Int"), "creature Int"),
            "wisdom": _source_nodes.integer(fields.get("Wis"), "creature Wis"),
            "charisma": _source_nodes.integer(fields.get("Cha"), "creature Cha"),
        },
        "defenses": {
            "armorClass": planned_integer("AC", "creature AC"),
            "fortitude": planned_integer("Fort", "creature Fort"),
            "reflex": _source_nodes.integer(fields.get("Ref"), "creature Ref"),
            "will": planned_integer("Will", "creature Will"),
            "maximumHitPoints": planned_integer("HP", "creature HP"),
            "immunities": [
                item.casefold()
                for item in _source_nodes.string_list(fields.get("Immunities"), "creature Immunities")
            ],
            **damage_defenses,
        },
        "speeds": speeds,
        "inventory": inventory,
        "strikes": strikes,
        "abilities": abilities,
        "unsupportedMechanics": sorted(
            {
                item["name"]
                for item in abilities
                if not item["supported"]
            }
            | {
                rider["name"]
                for strike in strikes
                for rider in strike["damage"]["riderEffects"]
                if not rider["supported"]
            }
        ),
        "deferredMechanics": sorted(
            {
                f"{ability['name']}: {mechanic}"
                for ability in abilities
                for mechanic in ability.get("deferredMechanics") or []
            }
            | set(_creature_stat_plan_deferrals(stat_plan))
        ),
        "runtimeBlockers": runtime_blockers,
    }
    icon_asset_key = creature_icon_asset_key(
        source_id,
        fields.get("Icon"),
    )
    if icon_asset_key is not None:
        result["icon"] = icon_asset_key
    if stat_plan is not None:
        result["statCompilation"] = _creature_stat_plan_projection(
            stat_plan
        )
    if ability_plan is not None:
        result["abilityCompilation"] = (
            _creature_ability_plan_projection(ability_plan)
        )
    if spellcasting_plan is not None:
        result["spellcastingCompilation"] = (
            _creature_spellcasting_plan_projection(
                spellcasting_plan
            )
        )
    if swallow_whole_compilation is not None:
        result["swallowWholeCompilation"] = (
            swallow_whole_compilation
        )
    return result

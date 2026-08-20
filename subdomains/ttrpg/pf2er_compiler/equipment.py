"""Compile and bind the bounded Player Core equipment used by encounters."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from . import durability
from .errors import EngineInputError
from .mechanics.equipment_bindings import runtime_equipment_binding
from .source_nodes import (
    OrderedObject,
    content_target,
    integer,
    plain_value,
)


ARMOR_ROOT = {"sourceId": "core-pc1", "locator": "271.1"}
ARMOR_DESCRIPTIONS_ROOT = {
    "sourceId": "core-pc1",
    "locator": "272.4",
}
SHIELD_ROOT = {"sourceId": "core-pc1", "locator": "274.1"}
SHIELD_DESCRIPTIONS_ROOT = {
    "sourceId": "core-pc1",
    "locator": "274.7",
}
WEAPON_ROOT = {"sourceId": "core-pc1", "locator": "275.1"}
WEAPON_DESCRIPTIONS_ROOT = {
    "sourceId": "core-pc1",
    "locator": "284.1",
}
WEAPON_TRAITS_RULE = {"sourceId": "core-pc1", "locator": "282.1"}
AMMUNITION_RULE = {"sourceId": "core-pc1", "locator": "277.3"}
WIELDING_RULE = {"sourceId": "core-pc1", "locator": "267.8"}
CREATURE_REACH_RULE = {"sourceId": "core-pc1", "locator": "421.8"}

ARMOR_TABLE_TAIL = (
    "Price",
    "AC Bonus",
    "Dex Cap",
    "Check Penalty",
    "Speed Penalty",
    "Strength",
    "Bulk",
    "Group",
    "Armor Traits",
)
WEAPON_TABLE_CATEGORIES = frozenset(
    {
        "Simple Weapons",
        "Uncommon Simple Weapons",
        "Martial Weapons",
        "Advanced Weapons",
    }
)
MELEE_WEAPON_TABLE_TAIL = (
    "Price",
    "Damage",
    "Bulk",
    "Hands",
    "Group",
    "Weapon Traits",
)
RANGED_WEAPON_TABLE_TAIL = (
    "Price",
    "Damage",
    "Range",
    "Reload",
    "Bulk",
    "Hands",
    "Group",
    "Weapon Traits",
)

UNCOMMON_ITEM_IDS = frozenset(
    {
        "core-pc1:item:dogslicer",
        "core-pc1:item:halfling-sling-staff",
        "core-pc1:item:horsechopper",
        "core-pc1:item:orc-knuckle-dagger",
        "core-pc1:item:orc-necksplitter",
        "core-pc1:item:wakizashi",
    }
)

DAMAGE_TYPES = {
    "B": "bludgeoning",
    "P": "piercing",
    "S": "slashing",
}
DAMAGE_ROW_RE = re.compile(r"^(?P<count>\d+)d(?P<sides>\d+)\s+(?P<type>[BPS])$")
RANGE_RE = re.compile(r"^(?P<feet>\d+)\s+ft\.$")
DEADLY_RE = re.compile(r"^deadly\s+d(?P<sides>\d+)$", re.IGNORECASE)
VERSATILE_RE = re.compile(r"^versatile\s+(?P<type>[BPS])$", re.IGNORECASE)
DIE_TRAIT_RE = re.compile(
    r"^(?P<name>fatal|jousting|two-hand)\s+d(?P<sides>\d+)$",
    re.IGNORECASE,
)
DISTANCE_TRAIT_RE = re.compile(
    r"^(?P<name>thrown|volley)\s+(?P<feet>\d+)\s+ft\.$",
    re.IGNORECASE,
)
BUNDLE_RE = re.compile(r"^(?P<quantity>\d+)\s+(?P<name>.+)$")
WEAPON_BLOCK_PREFIX = "^.weapon."
ARMOR_BLOCK_PREFIX = "^.armor."
SHIELD_BLOCK_PREFIX = "^.shield."
AMMUNITION_PRESENTATION_NAMES = {
    "core-pc1:item:arrows": "Arrow",
    "core-pc1:item:bolts": "Bolt",
    "core-pc1:item:sling-bullets": "Sling Bullet",
}
ITEM_PRESENTATION_NAMES = {
    "core-pc1:item:half-plate": "Half Plate",
}

SEMANTIC_CREATURE_REACH_RULE_REF = "pf2er.rule:size-space-reach"
SEMANTIC_WIELDING_RULE_REF = "pf2er.rule:wielding-items"
_SEMANTIC_ACQUISITION_KEYS = frozenset(
    {
        "address",
        "carrierPath",
        "contentPath",
        "equipmentSource",
        "locator",
        "path",
        "receipt",
        "sectionId",
        "source",
        "sourceAddressSha256",
        "sourceId",
        "sourceOccurrenceId",
        "sourceSpan",
        "sourceText",
        "sourceToken",
    }
)


class EquipmentBindingBlocker(EngineInputError):
    """A reviewed deferral or unknown item stopped runtime binding."""

    def __init__(
        self,
        source_name: object,
        *,
        reason_kind: str | None = None,
        reason_message: str | None = None,
    ) -> None:
        self.source_name = source_name
        self.reason_kind = reason_kind
        self.reason_message = reason_message
        super().__init__(
            "creature item is not bound to canonical equipment: "
            f"{source_name}"
        )


class EquipmentStrikeBindingBlocker(EngineInputError):
    """An exact item binding disagrees with the authored creature Strike."""

    def __init__(
        self,
        message: str,
        *,
        reason_kind: str,
        creature_source_receipt: dict[str, Any],
        equipment_source_receipt: dict[str, Any],
        comparison: dict[str, Any],
    ) -> None:
        self.reason_kind = reason_kind
        self.creature_source_receipt = deepcopy(
            creature_source_receipt
        )
        self.equipment_source_receipt = deepcopy(
            equipment_source_receipt
        )
        self.source_receipts = {
            "creature": deepcopy(creature_source_receipt),
            "equipment": deepcopy(equipment_source_receipt),
        }
        self.comparison = deepcopy(comparison)
        super().__init__(message)


def normalized_source_name(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def thaw_binding(value: object) -> object:
    if isinstance(value, (dict, MappingProxyType)):
        return {
            str(key): thaw_binding(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [thaw_binding(item) for item in value]
    return value


def equipment_binding(source_name: object) -> dict[str, Any]:
    binding = runtime_equipment_binding(source_name)
    if binding is None:
        raise EquipmentBindingBlocker(source_name)
    if not binding["canonical"]:
        deferral = binding["deferral"]
        raise EquipmentBindingBlocker(
            source_name,
            reason_kind=str(deferral["kind"]),
            reason_message=str(deferral["message"]),
        )
    result = thaw_binding(binding)
    if not isinstance(result, dict):
        raise EngineInputError(
            "canonical equipment binding projection is invalid"
        )
    quality = next(
        (
            modifier["value"]
            for modifier in result["modifiers"]
            if modifier["kind"] == "quality-shoddy"
        ),
        None,
    )
    if quality is not None:
        result["quality"] = str(quality)
    return result


def packet_content(packet: dict[str, Any], *, locator: str) -> OrderedObject:
    target = packet.get("target", {}).get("selected")
    section = packet.get("content", {}).get("section")
    if not isinstance(target, dict) or not isinstance(section, dict):
        raise EngineInputError("equipment source packet is incomplete")
    if (
        str(target.get("source_id") or "") != "core-pc1"
        or str(target.get("locator") or "") != locator
        or str(section.get("id") or "") != str(target.get("section_id") or "")
        or str(section.get("source_id") or "") != "core-pc1"
        or not isinstance(target.get("content_path"), list)
    ):
        raise EngineInputError(f"equipment source packet does not match core-pc1/{locator}")
    return content_target(
        str(section.get("content") or ""),
        [str(part) for part in target["content_path"]],
    )


def table_records(value: Any) -> Iterable[tuple[list[str], list[Any]]]:
    if isinstance(value, OrderedObject):
        columns = value.unique("columns", required=False, default=None)
        rows = value.unique("rows", required=False, default=None)
        if isinstance(columns, list) and isinstance(rows, list):
            yield (
                [str(item) for item in plain_value(columns, "equipment table columns")],
                plain_value(rows, "equipment table rows"),
            )
        for _key, child in value.pairs:
            yield from table_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from table_records(child)


def _toc_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(value, dict):
        raise EngineInputError("equipment source ToC is invalid")
    yield value
    children = value.get("children")
    if not isinstance(children, list):
        raise EngineInputError("equipment source ToC children are invalid")
    for child in children:
        yield from _toc_nodes(child)


def source_presentation_index(
    packet: dict[str, Any],
    root: OrderedObject,
    *,
    description_root: dict[str, str],
    heading: str,
    block_prefix: str,
    kind: str,
) -> dict[str, dict[str, Any]]:
    """Compile exact Core PC1 item presentation targets from source."""

    toc = packet.get("toc")
    matches = [
        node
        for node in _toc_nodes(toc)
        if node.get("locator") == description_root["locator"]
    ]
    if len(matches) != 1:
        raise EngineInputError(
            f"Core PC1 {heading} ToC target is missing or ambiguous"
        )
    descriptions_node = matches[0]
    if (
        descriptions_node.get("label") != heading
        or descriptions_node.get("content_path") != [heading]
    ):
        raise EngineInputError(
            f"Core PC1 {heading} ToC target changed"
        )
    toc_children = descriptions_node.get("children")
    if not isinstance(toc_children, list):
        raise EngineInputError(
            f"Core PC1 {heading} ToC children are invalid"
        )
    toc_by_name: dict[str, dict[str, Any]] = {}
    for child in toc_children:
        if not isinstance(child, dict):
            raise EngineInputError(
                f"Core PC1 {kind} presentation target is invalid"
            )
        name = child.get("label")
        locator = child.get("locator")
        if (
            type(name) is not str
            or not name
            or name != name.strip()
            or type(locator) is not str
            or not locator
            or locator != locator.strip()
            or child.get("content_path") != [heading, name]
            or child.get("children") != []
            or name in toc_by_name
        ):
            raise EngineInputError(
                f"Core PC1 {kind} presentation target changed"
            )
        toc_by_name[name] = child

    descriptions = root.unique(heading)
    if not isinstance(descriptions, OrderedObject):
        raise EngineInputError(
            f"Core PC1 {heading} source target is invalid"
        )
    presentations: dict[str, dict[str, Any]] = {}
    block_names: set[str] = set()
    for key, block in descriptions.pairs:
        if not key.startswith(block_prefix):
            continue
        name = key[len(block_prefix):]
        if (
            not name
            or name in block_names
            or not isinstance(block, OrderedObject)
        ):
            raise EngineInputError(
                f"Core PC1 {kind} presentation block is invalid"
            )
        block_names.add(name)
        if block.unique("Name") != name:
            raise EngineInputError(
                f"Core PC1 {kind} presentation name changed: {name}"
            )
        description = block.unique("Description")
        if not isinstance(description, (str, OrderedObject)) or not description:
            raise EngineInputError(
                f"Core PC1 {kind} presentation description is invalid: {name}"
            )
        for field in ("Icon", "Image"):
            value = block.unique(field, required=False, default=None)
            if value is not None and (
                type(value) is not str
                or not value
                or value != value.strip()
            ):
                raise EngineInputError(
                    f"Core PC1 {kind} presentation {field} is invalid: {name}"
                )
        toc_target = toc_by_name.get(name)
        if toc_target is None:
            raise EngineInputError(
                f"Core PC1 {kind} presentation ToC target is missing: {name}"
            )
        normalized = normalized_source_name(name)
        if normalized in presentations:
            raise EngineInputError(
                f"Core PC1 {kind} presentation identity is ambiguous: {name}"
            )
        presentations[normalized] = {
            "name": name,
            "source": {
                "sourceId": description_root["sourceId"],
                "locator": toc_target["locator"],
            },
        }
    if block_names != set(toc_by_name):
        raise EngineInputError(
            f"Core PC1 {kind} presentation blocks and ToC disagree"
        )
    return presentations


def weapon_presentation_index(
    weapons_packet: dict[str, Any],
    weapons_root: OrderedObject,
) -> dict[str, dict[str, Any]]:
    return source_presentation_index(
        weapons_packet,
        weapons_root,
        description_root=WEAPON_DESCRIPTIONS_ROOT,
        heading="Weapon Descriptions",
        block_prefix=WEAPON_BLOCK_PREFIX,
        kind="weapon",
    )


def armor_presentation_index(
    armor_packet: dict[str, Any],
    armor_root: OrderedObject,
) -> dict[str, dict[str, Any]]:
    return source_presentation_index(
        armor_packet,
        armor_root,
        description_root=ARMOR_DESCRIPTIONS_ROOT,
        heading="Armor Descriptions",
        block_prefix=ARMOR_BLOCK_PREFIX,
        kind="armor",
    )


def shield_presentation_index(
    shield_packet: dict[str, Any],
    shield_root: OrderedObject,
) -> dict[str, dict[str, Any]]:
    return source_presentation_index(
        shield_packet,
        shield_root,
        description_root=SHIELD_DESCRIPTIONS_ROOT,
        heading="Shield Descriptions",
        block_prefix=SHIELD_BLOCK_PREFIX,
        kind="shield",
    )


def presentation_for_item(
    binding: dict[str, Any],
    presentations: dict[str, dict[str, Any]],
    *,
    kind: str = "weapon",
) -> dict[str, Any]:
    name = (
        AMMUNITION_PRESENTATION_NAMES.get(binding["itemId"])
        if binding["kind"] == "ammunition"
        else ITEM_PRESENTATION_NAMES.get(
            binding["itemId"],
            binding.get("rowName"),
        )
    )
    presentation = presentations.get(normalized_source_name(name))
    if presentation is None:
        raise EngineInputError(
            f"canonical equipment lacks an exact {kind} presentation: "
            f"{binding['itemId']}"
        )
    return deepcopy(presentation)


def row_mapping(columns: list[str], row: list[Any]) -> dict[str, str]:
    if len(row) != len(columns):
        raise EngineInputError("equipment table row does not match its columns")
    return {column: str(value) for column, value in zip(columns, row)}


def require_reviewed_rows(
    matches: list[tuple[list[str], list[Any]]],
    binding: dict[str, Any],
    label: str,
) -> None:
    expected = {
        str(value)
        for value in binding["source"]["rowSelectionSha256"]
    }
    actual = {
        hashlib.sha256(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        for _columns, row in matches
    }
    # The source repeats ammunition rows in several category tables. Exact
    # reviewed row content resolves those duplicates without making their
    # incidental multiplicity part of the runtime item identity.
    if not expected or not actual or actual != expected:
        raise EngineInputError(
            f"canonical {label} row is missing or ambiguous: "
            f"{binding['rowName']}"
        )


def dash_integer(value: object, label: str) -> int:
    normalized = str(value or "").strip().replace("−", "-").replace("–", "-")
    if normalized in {"", "—"}:
        return 0
    return integer(normalized.removesuffix(" ft."), label)


def bulk_value(value: object) -> int | str:
    normalized = str(value or "").strip()
    if normalized == "L":
        return "light"
    if normalized in {"", "—"}:
        return 0
    return integer(normalized, "equipment Bulk")


def damage_value(value: object, label: str) -> dict[str, Any]:
    match = DAMAGE_ROW_RE.fullmatch(str(value or "").strip())
    if match is None:
        raise EngineInputError(f"{label} damage row is not understood: {value}")
    return {
        "dice": {"count": int(match.group("count")), "sides": int(match.group("sides"))},
        "type": DAMAGE_TYPES[match.group("type")],
    }


def hands_value(value: object) -> dict[str, Any]:
    normalized = str(value or "").strip()
    if normalized == "1+":
        return {"holding": 1, "requiredToUse": 2, "freeHandCompletesUse": True}
    count = integer(normalized, "weapon Hands")
    if count not in {1, 2}:
        raise EngineInputError(f"weapon Hands is unsupported: {value}")
    return {"holding": count, "requiredToUse": count, "freeHandCompletesUse": False}


def weapon_trait(value: str) -> dict[str, Any]:
    normalized = value.strip().casefold()
    result: dict[str, Any] = {"name": normalized, "rule": deepcopy(WEAPON_TRAITS_RULE)}
    if not normalized:
        raise EngineInputError("weapon trait is empty")
    if normalized == "backstabber":
        result["precisionDamage"] = 1
        return result
    if normalized == "reach":
        result["reachFeet"] = 10
        return result
    deadly = DEADLY_RE.fullmatch(normalized)
    if deadly:
        return {
            "name": "deadly",
            "die": {"count": 1, "sides": int(deadly.group("sides"))},
            "rule": deepcopy(WEAPON_TRAITS_RULE),
        }
    versatile = VERSATILE_RE.fullmatch(normalized)
    if versatile:
        return {
            "name": "versatile",
            "damageType": DAMAGE_TYPES[versatile.group("type").upper()],
            "rule": deepcopy(WEAPON_TRAITS_RULE),
        }
    die_trait = DIE_TRAIT_RE.fullmatch(normalized)
    if die_trait:
        return {
            "name": die_trait.group("name").casefold(),
            "die": {
                "count": 1,
                "sides": int(die_trait.group("sides")),
            },
            "rule": deepcopy(WEAPON_TRAITS_RULE),
        }
    distance_trait = DISTANCE_TRAIT_RE.fullmatch(normalized)
    if distance_trait:
        trait_name = distance_trait.group("name").casefold()
        return {
            "name": trait_name,
            (
                "rangeIncrementFeet"
                if trait_name == "thrown"
                else "distanceFeet"
            ): int(distance_trait.group("feet")),
            "rule": deepcopy(WEAPON_TRAITS_RULE),
        }
    return result


def find_weapon(
    root: OrderedObject,
    binding: dict[str, Any],
    presentation: dict[str, Any],
) -> dict[str, Any]:
    matches: list[tuple[list[str], list[Any]]] = []
    for columns, rows in table_records(root):
        if not columns or "Weapons" not in columns[0]:
            continue
        for row in rows:
            if isinstance(row, list) and row and str(row[0]) == binding["rowName"]:
                matches.append((columns, row))
    require_reviewed_rows(matches, binding, "weapon")
    if len(matches) != 1:
        raise EngineInputError(
            f"canonical weapon row is missing or ambiguous: "
            f"{binding['rowName']}"
        )
    columns, row = matches[0]
    if (
        columns[0] not in WEAPON_TABLE_CATEGORIES
        or tuple(columns[1:])
        not in {
            MELEE_WEAPON_TABLE_TAIL,
            RANGED_WEAPON_TABLE_TAIL,
        }
    ):
        raise EngineInputError(
            "canonical weapon table columns changed: "
            f"{binding['rowName']}"
        )
    fields = row_mapping(columns, row)
    ranged = "Range" in fields
    raw_traits = [
        item.strip()
        for item in fields["Weapon Traits"].split(",")
        if item.strip() and item.strip() != "—"
    ]
    traits = [weapon_trait(item) for item in raw_traits]
    raw_category = columns[0].removesuffix(" Weapons")
    uncommon = (
        raw_category.startswith("Uncommon ")
        or binding["itemId"] in UNCOMMON_ITEM_IDS
    )
    weapon_category = raw_category.removeprefix(
        "Uncommon "
    ).casefold()
    result = {
        "schema": 1,
        "id": binding["itemId"],
        "name": presentation["name"],
        "kind": "weapon",
        "level": 0,
        "rarity": "uncommon" if uncommon else "common",
        "weaponCategory": weapon_category,
        "mode": "ranged" if ranged else "melee",
        "price": fields["Price"],
        "damage": damage_value(fields["Damage"], binding["rowName"]),
        "bulk": bulk_value(fields["Bulk"]),
        "hands": hands_value(fields["Hands"]),
        "group": fields["Group"].casefold(),
        "traits": traits,
        "source": {
            **deepcopy(WEAPON_ROOT),
            "row": binding["rowName"],
            "columns": columns,
            "bindingStatus": binding["bindingStatus"],
            "contract": deepcopy(binding["source"]),
        },
        "presentation": deepcopy(presentation),
        "rules": {
            "statistics": {"sourceId": "core-pc1", "locator": "276.1"},
            "hands": {"sourceId": "core-pc1", "locator": "276.7"},
            "traits": deepcopy(WEAPON_TRAITS_RULE),
        },
    }
    if ranged:
        range_match = RANGE_RE.fullmatch(fields["Range"])
        if range_match is None:
            raise EngineInputError(f"weapon Range is not understood: {fields['Range']}")
        reload_text = str(fields["Reload"]).strip()
        requires_draw = reload_text == "—"
        result.update(
            {
                "rangeIncrementFeet": int(range_match.group("feet")),
                "maximumRangeIncrements": 6,
                "reloadActions": None if requires_draw else integer(reload_text, "weapon Reload"),
                "requiresDrawAfterUse": requires_draw,
                "rules": {
                    **result["rules"],
                    "range": {"sourceId": "core-pc1", "locator": "276.4"},
                    "reload": {"sourceId": "core-pc1", "locator": "276.5"},
                },
            }
        )
    durability_profile = durability.reviewed_item_profile(
        result["id"]
    )
    if durability_profile is not None:
        result["durability"] = durability_profile
    return result


def find_armor(root: OrderedObject, binding: dict[str, Any]) -> dict[str, Any]:
    matches: list[tuple[list[str], list[Any], str]] = []
    for columns, rows in table_records(root):
        if (
            not columns
            or columns[0] not in {"Light Armor", "Medium Armor", "Heavy Armor"}
        ):
            continue
        for row in rows:
            if isinstance(row, list) and row and str(row[0]) == binding["rowName"]:
                matches.append((columns, row, columns[0]))
    require_reviewed_rows(
        [(columns, row) for columns, row, _category in matches],
        binding,
        "armor",
    )
    if len(matches) != 1:
        raise EngineInputError(
            f"canonical armor row is missing or ambiguous: "
            f"{binding['rowName']}"
        )
    columns, row, category = matches[0]
    if tuple(columns[1:]) != ARMOR_TABLE_TAIL:
        raise EngineInputError(
            "canonical armor table columns changed: "
            f"{binding['rowName']}"
        )
    fields = row_mapping(columns, row)
    traits = [] if fields["Armor Traits"] == "—" else [
        item.strip().casefold() for item in fields["Armor Traits"].split(",") if item.strip()
    ]
    result = {
        "schema": 1,
        "id": binding["itemId"],
        "name": binding["rowName"],
        "kind": "armor",
        "level": 0,
        "rarity": "common",
        "armorCategory": category.removesuffix(" Armor").casefold(),
        "price": fields["Price"],
        "armorClassBonus": dash_integer(fields["AC Bonus"], "armor AC Bonus"),
        "dexterityCap": dash_integer(fields["Dex Cap"], "armor Dex Cap"),
        "checkPenalty": dash_integer(fields["Check Penalty"], "armor Check Penalty"),
        "speedPenaltyFeet": dash_integer(fields["Speed Penalty"], "armor Speed Penalty"),
        "strengthThreshold": dash_integer(fields["Strength"], "armor Strength"),
        "bulk": bulk_value(fields["Bulk"]),
        "group": fields["Group"].casefold(),
        "traits": traits,
        "source": {
            **deepcopy(ARMOR_ROOT),
            "row": binding["rowName"],
            "columns": columns,
            "bindingStatus": binding["bindingStatus"],
            "contract": deepcopy(binding["source"]),
        },
        "rules": {
            "armorClass": {"sourceId": "core-pc1", "locator": "271.2"},
            "statistics": {"sourceId": "core-pc1", "locator": "271.4"},
        },
    }
    durability_profile = durability.reviewed_item_profile(
        result["id"]
    )
    if durability_profile is not None:
        result["durability"] = durability_profile
    return result


def find_ammunition(root: OrderedObject, binding: dict[str, Any]) -> dict[str, Any]:
    matches: list[tuple[list[str], list[Any]]] = []
    for columns, rows in table_records(root):
        if "Range" not in columns:
            continue
        for row in rows:
            if isinstance(row, list) and row and str(row[0]) == binding["rowName"]:
                matches.append((columns, row))
    require_reviewed_rows(matches, binding, "ammunition")
    if any(
        columns[0] not in WEAPON_TABLE_CATEGORIES
        or tuple(columns[1:]) != RANGED_WEAPON_TABLE_TAIL
        for columns, _row in matches
    ):
        raise EngineInputError(
            "canonical ammunition table columns changed: "
            f"{binding['rowName']}"
        )
    canonical = row_mapping(*matches[0])
    bundle_match = BUNDLE_RE.fullmatch(binding["rowName"])
    if bundle_match is None:
        raise EngineInputError(f"ammunition bundle name is invalid: {binding['rowName']}")
    return {
        "schema": 1,
        "id": binding["itemId"],
        "name": bundle_match.group("name").capitalize(),
        "kind": "ammunition",
        "level": 0,
        "rarity": "common",
        "bundleQuantity": int(bundle_match.group("quantity")),
        "pricePerBundle": canonical["Price"],
        "bulkPerBundle": bulk_value(canonical["Bulk"]),
        "consumedOnUse": True,
        "source": {
            **deepcopy(WEAPON_ROOT),
            "row": binding["rowName"],
            "columns": matches[0][0],
            "bindingStatus": binding["bindingStatus"],
            "contract": deepcopy(binding["source"]),
        },
        "rules": {"ammunition": deepcopy(AMMUNITION_RULE)},
    }


def find_noncombat_item(binding: dict[str, Any]) -> dict[str, Any]:
    """Project a source-contract item that needs no combat-stat row."""

    result = {
        "schema": 1,
        "id": binding["itemId"],
        "name": binding.get("rowName") or binding["sourceName"],
        "kind": binding["kind"],
        "source": {
            "sourceId": binding["source"]["sourceId"],
            "locator": binding["source"]["locator"],
            "contractId": binding["contractId"],
            "bindingStatus": binding["bindingStatus"],
            "contract": deepcopy(binding["source"]),
        },
    }
    hands_to_use = binding.get("handsToUse")
    if type(hands_to_use) is int:
        result["hands"] = hands_value(hands_to_use)
    elif hands_to_use == "1-or-2":
        result["hands"] = {
            "holding": 1,
            "requiredToUse": 1,
            "freeHandCompletesUse": False,
            "allowedHandsToUse": [1, 2],
        }
    elif hands_to_use is not None:
        raise EngineInputError(
            "canonical equipment hands-to-use is invalid: "
            f"{binding['sourceName']}"
        )
    shield_profiles = {
        "core-pc1:item:steel-shield": {
            "armorClassBonus": 2,
            "speedPenaltyFeet": 0,
            "bulk": 1,
            "hands": hands_value(1),
            "durability": {
                "hardness": 5,
                "maximumHitPoints": 20,
                "brokenThreshold": 10,
                "rule": {
                    "sourceId": "core-pc1",
                    "locator": "274.1",
                },
            },
        },
        "core-pc1:item:wooden-shield": {
            "armorClassBonus": 2,
            "speedPenaltyFeet": 0,
            "bulk": 1,
            "hands": hands_value(1),
            "durability": {
                "hardness": 3,
                "maximumHitPoints": 12,
                "brokenThreshold": 6,
                "rule": {
                    "sourceId": "core-pc1",
                    "locator": "274.1",
                },
            },
        },
    }
    shield_profile = shield_profiles.get(result["id"])
    if shield_profile is not None:
        if result["kind"] != "shield":
            raise EngineInputError(
                "canonical shield profile changed item kind"
            )
        result.update(deepcopy(shield_profile))
        result["rules"] = {
            "statistics": {
                "sourceId": "core-pc1",
                "locator": "274.1",
            },
            "wielding": {
                "sourceId": "core-pc1",
                "locator": "274.2",
            },
        }
    if binding["strikeNames"] and "hands" not in result:
        raise EngineInputError(
            "canonical struck-with equipment lacks hands: "
            f"{binding['sourceName']}"
        )
    if result["id"] == "core-pc1:item:torch":
        result["lightSource"] = {
            "activeWhen": "wielded-burning-strike",
            "emission": {
                "brightRadiusFeet": 20,
                "dimOuterRadiusFeet": 40,
            },
            "displayRgb": [255, 145, 55],
            "rule": {
                "sourceId": "core-pc1",
                "locator": "287.5",
            },
        }
    return result


def compile_equipment_catalog(
    source_names: Iterable[str],
    *,
    armor_packet: dict[str, Any],
    shield_packet: dict[str, Any] | None = None,
    weapons_packet: dict[str, Any],
) -> dict[str, Any]:
    """Compile only explicitly requested, scenario-bound equipment rows."""

    normalized_names = {normalized_source_name(name) for name in source_names}
    bindings = {name: equipment_binding(name) for name in sorted(normalized_names)}
    armor_root = packet_content(armor_packet, locator="271.1")
    weapons_root = packet_content(weapons_packet, locator="275.1")
    armor_presentations = armor_presentation_index(
        armor_packet,
        armor_root,
    )
    weapon_presentations = weapon_presentation_index(
        weapons_packet,
        weapons_root,
    )
    shield_bindings_present = any(
        binding["kind"] == "shield"
        for binding in bindings.values()
    )
    shield_presentations: dict[str, dict[str, Any]] = {}
    if shield_bindings_present:
        if shield_packet is None:
            raise EngineInputError(
                "canonical shields require the Core PC1 shield packet"
            )
        shield_root = packet_content(shield_packet, locator="274.1")
        shield_presentations = shield_presentation_index(
            shield_packet,
            shield_root,
        )
    items: dict[str, dict[str, Any]] = {}
    for binding in bindings.values():
        if binding["kind"] == "weapon":
            item = find_weapon(
                weapons_root,
                binding,
                presentation_for_item(binding, weapon_presentations),
            )
        elif binding["kind"] == "armor":
            item = find_armor(armor_root, binding)
            item["presentation"] = presentation_for_item(
                binding,
                armor_presentations,
                kind="armor",
            )
        elif binding["kind"] == "ammunition":
            item = find_ammunition(weapons_root, binding)
            item["presentation"] = presentation_for_item(
                binding,
                weapon_presentations,
            )
        elif binding["kind"] in {"gear", "shield", "source-item"}:
            item = find_noncombat_item(binding)
            if binding["kind"] == "shield":
                item["presentation"] = presentation_for_item(
                    binding,
                    shield_presentations,
                    kind="shield",
                )
        else:
            raise EngineInputError(f"equipment binding kind is invalid: {binding['kind']}")
        prior = items.get(item["id"])
        if prior is not None and prior != item:
            raise EngineInputError(
                "canonical equipment item has conflicting bindings: "
                f"{item['id']}"
            )
        items[item["id"]] = item
    for binding in bindings.values():
        ammunition_item_id = binding.get("ammunitionItemId")
        if ammunition_item_id is None:
            continue
        if binding["itemId"] not in items:
            raise EngineInputError(
                "canonical ammunition launcher is missing: "
                f"{binding['itemId']}"
            )
        if ammunition_item_id not in items:
            raise EngineInputError(
                f"{binding['sourceName']} inventory requires canonical "
                f"ammunition: {ammunition_item_id}"
            )
        items[binding["itemId"]][
            "ammunitionItemId"
        ] = ammunition_item_id
        items[binding["itemId"]][
            "ammunitionSource"
        ] = deepcopy(binding["ammunitionSource"])
    supplemental_roots = set()
    for binding in bindings.values():
        binding_sources = [
            binding["source"],
            *(
                modifier["source"]
                for modifier in binding.get("modifiers") or []
            ),
        ]
        if binding.get("ammunitionSource") is not None:
            binding_sources.append(binding["ammunitionSource"])
        for source in binding_sources:
            root = (source["sourceId"], source["locator"])
            if root not in {
                (ARMOR_ROOT["sourceId"], ARMOR_ROOT["locator"]),
                (WEAPON_ROOT["sourceId"], WEAPON_ROOT["locator"]),
            }:
                supplemental_roots.add(root)
    return {
        "schema": 1,
        "sourceRoots": [
            deepcopy(ARMOR_ROOT),
            deepcopy(ARMOR_DESCRIPTIONS_ROOT),
            deepcopy(WEAPON_ROOT),
            deepcopy(WEAPON_DESCRIPTIONS_ROOT),
            *(
                [deepcopy(SHIELD_DESCRIPTIONS_ROOT)]
                if shield_bindings_present
                else []
            ),
            *(
                {"sourceId": source_id, "locator": locator}
                for source_id, locator in sorted(supplemental_roots)
            ),
        ],
        "items": {item_id: items[item_id] for item_id in sorted(items)},
    }


def _semantic_json_digest(value: object, label: str) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EngineInputError(f"{label} is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _require_semantic_source_free(value: object, path: str) -> None:
    """Reject acquisition evidence at the semantic equipment runtime seam."""

    if type(value) is dict:
        forbidden = sorted(_SEMANTIC_ACQUISITION_KEYS.intersection(value))
        if forbidden:
            raise EngineInputError(
                f"{path} contains acquisition-only fields: "
                + ", ".join(forbidden)
            )
        for key, child in value.items():
            _require_semantic_source_free(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _require_semantic_source_free(child, f"{path}[{index}]")


def _semantic_positive_integer(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise EngineInputError(f"{label} must be a positive integer")
    return value


def _validate_semantic_rule_ref(value: object, label: str) -> None:
    if (
        type(value) is not dict
        or set(value) != {"ruleRef"}
        or type(value.get("ruleRef")) is not str
        or not value["ruleRef"].startswith("pf2er.rule:")
    ):
        raise EngineInputError(f"{label} must contain one PF2ER ruleRef")


def _semantic_rule_ref_census(value: object) -> set[str]:
    result: set[str] = set()
    if type(value) is dict:
        for key, child in value.items():
            if key == "ruleRef":
                if type(child) is not str or not child.startswith("pf2er.rule:"):
                    raise EngineInputError("semantic item ruleRef is invalid")
                result.add(child)
            else:
                result.update(_semantic_rule_ref_census(child))
    elif type(value) is list:
        for child in value:
            result.update(_semantic_rule_ref_census(child))
    return result


def _validate_semantic_weapon_definition(
    item_id: str,
    definition: dict[str, Any],
) -> None:
    common = {
        "schema",
        "id",
        "name",
        "kind",
        "level",
        "rarity",
        "weaponCategory",
        "mode",
        "price",
        "damage",
        "bulk",
        "hands",
        "group",
        "traits",
        "references",
        "presentation",
        "rules",
    }
    ranged = {
        "rangeIncrementFeet",
        "maximumRangeIncrements",
        "reloadActions",
        "requiresDrawAfterUse",
    }
    if not common.issubset(definition) or set(definition).difference(
        common | ranged
    ):
        raise EngineInputError(
            f"semantic equipment definition fields are invalid: {item_id}"
        )
    if (
        definition.get("schema") != 1
        or definition.get("id") != item_id
        or definition.get("kind") != "weapon"
        or definition.get("mode") not in {"melee", "ranged"}
        or type(definition.get("name")) is not str
        or not definition["name"]
        or type(definition.get("level")) is not int
        or type(definition.get("weaponCategory")) is not str
        or type(definition.get("group")) is not str
    ):
        raise EngineInputError(
            f"semantic weapon identity or statistics are invalid: {item_id}"
        )

    damage = definition.get("damage")
    dice = damage.get("dice") if type(damage) is dict else None
    if (
        type(damage) is not dict
        or set(damage) != {"dice", "type"}
        or type(dice) is not dict
        or set(dice) != {"count", "sides"}
        or type(dice.get("count")) is not int
        or dice["count"] <= 0
        or type(dice.get("sides")) is not int
        or dice["sides"] <= 0
        or damage.get("type") not in DAMAGE_TYPES.values()
    ):
        raise EngineInputError(
            f"semantic weapon damage is invalid: {item_id}"
        )

    hands = definition.get("hands")
    if (
        type(hands) is not dict
        or set(hands)
        != {"holding", "requiredToUse", "freeHandCompletesUse"}
        or type(hands.get("holding")) is not int
        or hands["holding"] not in {1, 2}
        or type(hands.get("requiredToUse")) is not int
        or hands["requiredToUse"] not in {1, 2}
        or type(hands.get("freeHandCompletesUse")) is not bool
    ):
        raise EngineInputError(
            f"semantic weapon Hands are invalid: {item_id}"
        )

    traits = definition.get("traits")
    if type(traits) is not list:
        raise EngineInputError(f"semantic weapon traits are invalid: {item_id}")
    trait_names: set[str] = set()
    allowed_trait_keys = {
        "name",
        "ruleRef",
        "rangeIncrementFeet",
        "distanceFeet",
        "damageType",
        "die",
        "precisionDamage",
        "reachFeet",
    }
    for index, trait in enumerate(traits):
        if (
            type(trait) is not dict
            or not {"name", "ruleRef"}.issubset(trait)
            or set(trait).difference(allowed_trait_keys)
            or type(trait.get("name")) is not str
            or not trait["name"]
            or trait["name"] in trait_names
            or type(trait.get("ruleRef")) is not str
            or not trait["ruleRef"].startswith("pf2er.rule:")
        ):
            raise EngineInputError(
                f"semantic weapon trait is invalid: {item_id}[{index}]"
            )
        trait_names.add(trait["name"])
        if "rangeIncrementFeet" in trait:
            _semantic_positive_integer(
                trait["rangeIncrementFeet"],
                f"semantic weapon trait range: {item_id}",
            )

    presentation = definition.get("presentation")
    if (
        type(presentation) is not dict
        or set(presentation) != {"name"}
        or presentation.get("name") != definition["name"]
    ):
        raise EngineInputError(
            f"semantic weapon presentation is invalid: {item_id}"
        )
    rules = definition.get("rules")
    if type(rules) is not dict or not {
        "statistics",
        "hands",
        "traits",
    }.issubset(rules):
        raise EngineInputError(f"semantic weapon rules are invalid: {item_id}")
    if set(rules).difference({"statistics", "hands", "traits", "range", "reload"}):
        raise EngineInputError(f"semantic weapon rules are invalid: {item_id}")
    for role, rule_ref in rules.items():
        _validate_semantic_rule_ref(
            rule_ref,
            f"semantic weapon {role} rule: {item_id}",
        )
    references = definition.get("references")
    referenced_rules = (
        references.get("rules")
        if type(references) is dict
        else None
    )
    if (
        type(references) is not dict
        or set(references) != {"rules"}
        or type(referenced_rules) is not list
        or any(type(rule_id) is not str for rule_id in referenced_rules)
        or referenced_rules != sorted(set(referenced_rules))
        or any(not rule_id.startswith("pf2er.rule:") for rule_id in referenced_rules)
    ):
        raise EngineInputError(
            f"semantic weapon rule references are invalid: {item_id}"
        )
    censused_rule_refs = _semantic_rule_ref_census(
        {
            key: value
            for key, value in definition.items()
            if key != "references"
        }
    )
    if set(referenced_rules) != censused_rule_refs:
        raise EngineInputError(
            f"semantic weapon rule reference closure is invalid: {item_id}"
        )

    if definition["mode"] == "ranged":
        if not ranged.issubset(definition):
            raise EngineInputError(
                f"semantic ranged weapon statistics are incomplete: {item_id}"
            )
        _semantic_positive_integer(
            definition["rangeIncrementFeet"],
            f"semantic weapon range: {item_id}",
        )
        _semantic_positive_integer(
            definition["maximumRangeIncrements"],
            f"semantic weapon maximum range increments: {item_id}",
        )
        if (
            definition["reloadActions"] is not None
            and (
                type(definition["reloadActions"]) is not int
                or definition["reloadActions"] < 0
            )
        ) or type(definition["requiresDrawAfterUse"]) is not bool:
            raise EngineInputError(
                f"semantic ranged weapon reload is invalid: {item_id}"
            )
    elif set(definition).intersection(ranged):
        raise EngineInputError(
            f"semantic melee weapon has ranged table fields: {item_id}"
        )


def _validate_semantic_instrument_definition(
    item_id: str,
    definition: dict[str, Any],
) -> None:
    profiles = {
        "pf2er:item.musical-instrument-handheld": {
            "name": "Handheld Musical Instrument",
            "level": 0,
            "price": "8 sp",
            "itemBonus": None,
        },
        "pf2er:item.musical-instrument-handheld-virtuoso": {
            "name": "Virtuoso Handheld Musical Instrument",
            "level": 3,
            "price": "50 gp",
            "itemBonus": 1,
        },
    }
    profile = profiles.get(item_id)
    expected_keys = {
        "schema",
        "id",
        "name",
        "kind",
        "level",
        "rarity",
        "price",
        "bulk",
        "hands",
        "profile",
        "performance",
        "telekineticProjectile",
        "reviewedDeferrals",
        "references",
        "rules",
    }
    if (
        profile is None
        or set(definition) != expected_keys
        or definition.get("schema") != 1
        or definition.get("id") != item_id
        or definition.get("name") != profile["name"]
        or definition.get("kind") != "adventuring-gear"
        or definition.get("level") != profile["level"]
        or definition.get("rarity") != "common"
        or definition.get("price") != profile["price"]
        or definition.get("bulk") != 1
        or definition.get("hands")
        != {"holding": 1, "requiredToUse": 2}
        or definition.get("profile") != "handheld-musical-instrument"
        or definition.get("performance")
        != {
            "itemBonus": profile["itemBonus"],
            "appliesWhileUsingInstrument": True,
            "runtimeStatus": "deferred",
            "ruleRef": "pf2er.rule:performance",
        }
        or definition.get("telekineticProjectile")
        != {
            "maximumBulkEligible": True,
            "damageType": None,
            "requiresAdjudicatedPhysicalDamageType": True,
            "ruleRef": "pf2er.rule:telekinetic-projectile",
        }
        or definition.get("reviewedDeferrals")
        != [
            "especially-large-handheld-bulk-gm-ruling",
            "perform-action-and-modality",
            "physical-damage-type-gm-adjudication",
        ]
        or definition.get("references")
        != {
            "rules": [
                "pf2er.rule:item-bulk",
                "pf2er.rule:item-hands",
                "pf2er.rule:musical-instrument",
                "pf2er.rule:performance",
                "pf2er.rule:telekinetic-projectile",
            ]
        }
        or definition.get("rules")
        != {
            "bulk": {"ruleRef": "pf2er.rule:item-bulk"},
            "hands": {"ruleRef": "pf2er.rule:item-hands"},
            "instrument": {
                "ruleRef": "pf2er.rule:musical-instrument"
            },
        }
    ):
        raise EngineInputError(
            f"semantic musical instrument profile is invalid: {item_id}"
        )


def compile_semantic_equipment_catalog(
    item_definitions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Compile verified semantic item entities into the engine catalog shape.

    This seam accepts no names, source packets, cache handles, or item-catalog
    access. Its keys are the selected semantic entity identities themselves.
    """

    if not isinstance(item_definitions, Mapping):
        raise EngineInputError("semantic item definitions must be a mapping")
    items: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    for item_id in sorted(item_definitions):
        definition = item_definitions[item_id]
        if (
            type(item_id) is not str
            or not item_id.startswith("pf2er:item.")
            or type(definition) is not dict
        ):
            raise EngineInputError("semantic item entity identity is invalid")
        _require_semantic_source_free(
            definition,
            f"semantic item {item_id}",
        )
        kind = definition.get("kind")
        if kind == "weapon":
            _validate_semantic_weapon_definition(item_id, definition)
        elif kind == "adventuring-gear":
            _validate_semantic_instrument_definition(item_id, definition)
        else:
            raise EngineInputError(
                f"semantic item kind is unsupported: {item_id}"
            )
        items[item_id] = deepcopy(definition)
        digests[item_id] = _semantic_json_digest(
            definition,
            f"semantic item {item_id}",
        )
    draft = {
        "schema": 2,
        "kind": "pf2er-semantic-equipment-catalog",
        "itemDefinitionDigests": digests,
        "items": items,
    }
    return {
        **draft,
        "catalogDigest": _semantic_json_digest(
            draft,
            "semantic equipment catalog",
        ),
    }


def catalog_item(catalog: dict[str, Any], item_id: str) -> dict[str, Any]:
    item = catalog.get("items", {}).get(item_id) if isinstance(catalog.get("items"), dict) else None
    if not isinstance(item, dict):
        raise EngineInputError(f"equipment catalog item is missing: {item_id}")
    return item


def trait_by_name(item: dict[str, Any], name: str) -> dict[str, Any] | None:
    matches = [trait for trait in item.get("traits") or [] if trait.get("name") == name]
    if len(matches) > 1:
        raise EngineInputError(f"equipment trait is ambiguous: {item.get('id')} {name}")
    return matches[0] if matches else None


def creature_trait_value(strike: dict[str, Any], prefix: str) -> str | None:
    matches = [trait for trait in strike.get("traits") or [] if str(trait).startswith(prefix)]
    if len(matches) > 1:
        raise EngineInputError(f"creature strike trait is ambiguous: {strike.get('id')} {prefix}")
    return str(matches[0]) if matches else None


def creature_default_reach(definition: dict[str, Any]) -> int:
    """Return the exact source-backed reach of the creature's unarmed body."""

    space = definition.get("space")
    if not isinstance(space, dict):
        raise EngineInputError(
            "bound creature definition lacks an exact space profile: "
            f"{definition.get('id')}"
        )
    default_reach = space.get("defaultReachFeet")
    if (
        not isinstance(default_reach, int)
        or isinstance(default_reach, bool)
        or default_reach < 0
        or default_reach % 5
    ):
        raise EngineInputError(
            "bound creature default reach is invalid: "
            f"{definition.get('id')}"
        )
    if space.get("rule") != CREATURE_REACH_RULE:
        raise EngineInputError(
            "bound creature default reach lacks exact rule provenance: "
            f"{definition.get('id')}"
        )
    return default_reach


def expected_melee_reach(
    definition: dict[str, Any],
    item: dict[str, Any],
) -> int:
    """Compose body reach with the canonical weapon's explicit Reach trait."""

    default_reach = creature_default_reach(definition)
    reach = trait_by_name(item, "reach")
    if reach is None:
        return default_reach
    weapon_reach = reach.get("reachFeet")
    if (
        not isinstance(weapon_reach, int)
        or isinstance(weapon_reach, bool)
        or weapon_reach < 5
        or weapon_reach % 5
    ):
        raise EngineInputError(
            "canonical weapon Reach trait is invalid: "
            f"{item.get('id')}"
        )
    # Player Core's explicit 10-foot Reach weapon statistic is 5 feet beyond
    # an ordinary wielder's 5-foot reach. Preserve that weapon-authored
    # extension while taking the creature's exact body reach from its public
    # source-backed space profile.
    return default_reach + weapon_reach - 5


def weapon_strike_modes(item: dict[str, Any]) -> tuple[str, ...]:
    primary_mode = str(item.get("mode") or "")
    modes = [primary_mode]
    thrown = trait_by_name(item, "thrown")
    if primary_mode == "melee" and thrown is not None:
        range_increment = thrown.get("rangeIncrementFeet")
        if (
            not isinstance(range_increment, int)
            or isinstance(range_increment, bool)
            or range_increment <= 0
        ):
            raise EngineInputError(
                "canonical melee thrown weapon range is invalid: "
                f"{item.get('id')}"
            )
        modes.append("ranged")
    return tuple(modes)


def ranged_weapon_statistics(
    item: dict[str, Any],
) -> tuple[int, int | None, bool]:
    if item.get("mode") == "ranged":
        return (
            int(item["rangeIncrementFeet"]),
            item.get("reloadActions"),
            bool(item.get("requiresDrawAfterUse")),
        )
    thrown = trait_by_name(item, "thrown")
    if thrown is None:
        raise EngineInputError(
            "canonical melee weapon has no ranged Strike mode: "
            f"{item.get('id')}"
        )
    return (
        int(thrown["rangeIncrementFeet"]),
        None,
        True,
    )


def selected_versatile_damage_types(
    strike: dict[str, Any],
    item: dict[str, Any],
) -> list[str]:
    """Return the canonical alternate to the Strike's selected damage mode."""

    item_damage = item.get("damage")
    if not isinstance(item_damage, dict):
        raise EngineInputError(
            "canonical weapon damage is invalid: "
            f"{item.get('id')}"
        )
    base_damage_type = item_damage.get("type")
    if base_damage_type not in DAMAGE_TYPES.values():
        raise EngineInputError(
            "canonical weapon damage type is invalid: "
            f"{item.get('id')}"
        )
    versatile = trait_by_name(item, "versatile")
    if versatile is None:
        return []
    versatile_damage_type = versatile.get("damageType")
    if (
        versatile_damage_type not in DAMAGE_TYPES.values()
        or versatile_damage_type == base_damage_type
    ):
        raise EngineInputError(
            "canonical weapon versatile trait is invalid: "
            f"{item.get('id')}"
        )
    selected_damage_type = strike.get("damage", {}).get("type")
    if selected_damage_type == base_damage_type:
        return [str(versatile_damage_type)]
    if selected_damage_type == versatile_damage_type:
        return [str(base_damage_type)]
    return []


def strike_binding_blocker(
    definition: dict[str, Any],
    strike: dict[str, Any],
    item: dict[str, Any],
    binding: dict[str, Any],
    *,
    reason_kind: str,
    message: str,
    field: str,
    creature_value: object,
    equipment_value: object,
) -> EquipmentStrikeBindingBlocker:
    creature_source = definition.get("source")
    equipment_source = item.get("source")
    if not isinstance(creature_source, dict):
        raise EngineInputError(
            "bound creature definition lacks source provenance: "
            f"{definition.get('id')}"
        )
    if not isinstance(equipment_source, dict):
        raise EngineInputError(
            "canonical equipment item lacks source provenance: "
            f"{item.get('id')}"
        )
    return EquipmentStrikeBindingBlocker(
        message,
        reason_kind=reason_kind,
        creature_source_receipt={
            "source": deepcopy(creature_source),
            "creatureId": str(definition.get("id") or ""),
            "creatureName": str(definition.get("name") or ""),
            "strikeId": str(strike.get("id") or ""),
            "strikeName": str(strike.get("name") or ""),
        },
        equipment_source_receipt={
            "source": deepcopy(equipment_source),
            "sourceName": str(binding.get("sourceName") or ""),
            "itemId": str(item.get("id") or ""),
            "contractId": str(binding.get("contractId") or ""),
            "bindingStatus": str(
                binding.get("bindingStatus") or ""
            ),
        },
        comparison={
            "field": field,
            "creatureValue": deepcopy(creature_value),
            "equipmentValue": deepcopy(equipment_value),
        },
    )


def validate_bound_strike(
    definition: dict[str, Any],
    strike: dict[str, Any],
    item: dict[str, Any],
    binding: dict[str, Any],
) -> None:
    allowed_modes = weapon_strike_modes(item)
    strike_mode = strike.get("kind")
    if strike_mode not in allowed_modes:
        raise strike_binding_blocker(
            definition,
            strike,
            item,
            binding,
            reason_kind="strike-mode-disagreement",
            message=(
                "creature strike mode disagrees with equipment: "
                f"{strike['name']}"
            ),
            field="mode",
            creature_value=strike_mode,
            equipment_value=(
                allowed_modes[0]
                if len(allowed_modes) == 1
                else list(allowed_modes)
            ),
        )
    # The exact creature stat block owns its Strike dice and flat damage
    # modifier.  Canonical equipment supplies item mechanics, not monster
    # competence or level-tuned damage.
    item_damage = item.get("damage")
    if not isinstance(item_damage, dict):
        raise EngineInputError(
            "canonical weapon damage is invalid: "
            f"{item.get('id')}"
        )
    base_damage_type = item_damage.get("type")
    versatile = trait_by_name(item, "versatile")
    canonical_versatile_damage_type = (
        None
        if versatile is None
        else versatile.get("damageType")
    )
    versatile_damage_types = selected_versatile_damage_types(
        strike,
        item,
    )
    selected_damage_type = strike.get("damage", {}).get("type")
    allowed_damage_types = {base_damage_type}
    if canonical_versatile_damage_type is not None:
        allowed_damage_types.add(canonical_versatile_damage_type)
    if selected_damage_type not in allowed_damage_types:
        raise strike_binding_blocker(
            definition,
            strike,
            item,
            binding,
            reason_kind="strike-damage-type-disagreement",
            message=(
                "creature strike type disagrees with equipment: "
                f"{strike['name']}"
            ),
            field="damage.type",
            creature_value=selected_damage_type,
            equipment_value=(
                base_damage_type
                if len(allowed_damage_types) == 1
                else sorted(allowed_damage_types)
            ),
        )
    for trait_name in ("agile", "backstabber", "finesse", "trip"):
        source_has_trait = trait_name in strike.get("traits", [])
        equipment_has_trait = bool(
            trait_by_name(item, trait_name)
        )
        # Finesse governs melee attack rolls. A source stat block can
        # therefore omit it from the ranged use of an otherwise finesse,
        # thrown weapon. Melee uses and weapons without canonical finesse
        # remain exact.
        if (
            trait_name == "finesse"
            and strike_mode == "ranged"
            and equipment_has_trait
        ):
            continue
        if source_has_trait != equipment_has_trait:
            raise strike_binding_blocker(
                definition,
                strike,
                item,
                binding,
                reason_kind="strike-trait-disagreement",
                message=(
                    f"creature strike {trait_name} trait disagrees "
                    f"with equipment: {strike['name']}"
                ),
                field=f"traits.{trait_name}",
                creature_value=source_has_trait,
                equipment_value=equipment_has_trait,
            )
    if strike_mode == "melee":
        expected_reach = expected_melee_reach(definition, item)
    if (
        strike_mode == "melee"
        and int(strike.get("reachFeet", -1)) != expected_reach
    ):
        raise strike_binding_blocker(
            definition,
            strike,
            item,
            binding,
            reason_kind="strike-reach-disagreement",
            message=(
                "creature strike reach disagrees with equipment: "
                f"{strike['name']}"
            ),
            field="reachFeet",
            creature_value=strike.get("reachFeet"),
            equipment_value=expected_reach,
        )
    deadly = trait_by_name(item, "deadly")
    raw_deadly = creature_trait_value(strike, "deadly d")
    if bool(deadly) != bool(raw_deadly):
        raise strike_binding_blocker(
            definition,
            strike,
            item,
            binding,
            reason_kind="strike-trait-disagreement",
            message=(
                "creature strike deadly trait disagrees with "
                f"equipment: {strike['name']}"
            ),
            field="traits.deadly",
            creature_value=raw_deadly,
            equipment_value=deepcopy(deadly),
        )
    if deadly and raw_deadly != f"deadly d{deadly['die']['sides']}":
        raise strike_binding_blocker(
            definition,
            strike,
            item,
            binding,
            reason_kind="strike-trait-disagreement",
            message=(
                "creature strike deadly die disagrees with "
                f"equipment: {strike['name']}"
            ),
            field="traits.deadly.die",
            creature_value=raw_deadly,
            equipment_value=f"deadly d{deadly['die']['sides']}",
        )
    raw_versatile = creature_trait_value(strike, "versatile ")
    expected_versatile = None
    if versatile_damage_types:
        expected_letter = next(
            key
            for key, value in DAMAGE_TYPES.items()
            if value == versatile_damage_types[0]
        )
        expected_versatile = f"versatile {expected_letter.casefold()}"
    if raw_versatile != expected_versatile:
        raise strike_binding_blocker(
            definition,
            strike,
            item,
            binding,
            reason_kind="strike-trait-disagreement",
            message=(
                "creature strike versatile trait disagrees with "
                f"equipment: {strike['name']}"
            ),
            field="traits.versatile",
            creature_value=raw_versatile,
            equipment_value=expected_versatile,
        )
    if strike_mode == "ranged":
        (
            expected_range_increment,
            expected_reload_actions,
            expected_requires_draw,
        ) = ranged_weapon_statistics(item)
        if (
            int(strike.get("rangeIncrementFeet", 0))
            != expected_range_increment
        ):
            raise strike_binding_blocker(
                definition,
                strike,
                item,
                binding,
                reason_kind="strike-range-disagreement",
                message=(
                    "creature strike range disagrees with equipment: "
                    f"{strike['name']}"
                ),
                field="rangeIncrementFeet",
                creature_value=strike.get("rangeIncrementFeet"),
                equipment_value=expected_range_increment,
            )
        source_reload_actions = strike.get("reloadActions")
        source_reload_trait = creature_trait_value(
            strike,
            "reload ",
        )
        defaulted_reload_zero = (
            expected_reload_actions == 0
            and source_reload_actions is None
        )
        if (
            source_reload_actions != expected_reload_actions
            and not defaulted_reload_zero
        ):
            raise strike_binding_blocker(
                definition,
                strike,
                item,
                binding,
                reason_kind="strike-reload-disagreement",
                message=(
                    "creature strike reload disagrees with equipment: "
                    f"{strike['name']}"
                ),
                field="reloadActions",
                creature_value=source_reload_actions,
                equipment_value=expected_reload_actions,
            )
        source_reload_is_valid = (
            source_reload_actions is None
            or (
                isinstance(source_reload_actions, int)
                and not isinstance(source_reload_actions, bool)
                and source_reload_actions >= 0
            )
        )
        expected_source_reload_trait = (
            None
            if source_reload_actions is None
            else f"reload {source_reload_actions}"
        )
        if (
            not source_reload_is_valid
            or source_reload_trait != expected_source_reload_trait
        ):
            raise strike_binding_blocker(
                definition,
                strike,
                item,
                binding,
                reason_kind="strike-reload-disagreement",
                message=(
                    "creature strike reload disagrees with equipment: "
                    f"{strike['name']}"
                ),
                field="traits.reload",
                creature_value=source_reload_trait,
                equipment_value=expected_source_reload_trait,
            )
        item_thrown = trait_by_name(item, "thrown")
        source_thrown = creature_trait_value(strike, "thrown ")
        expected_thrown = (
            f"thrown {expected_range_increment} feet"
            if item_thrown is not None
            else None
        )
        if source_thrown != expected_thrown:
            raise strike_binding_blocker(
                definition,
                strike,
                item,
                binding,
                reason_kind="strike-trait-disagreement",
                message=(
                    "creature strike thrown trait disagrees with "
                    f"equipment: {strike['name']}"
                ),
                field="traits.thrown",
                creature_value=source_thrown,
                equipment_value=expected_thrown,
            )
        if (
            bool(strike.get("requiresDrawAfterUse"))
            != expected_requires_draw
        ):
            raise strike_binding_blocker(
                definition,
                strike,
                item,
                binding,
                reason_kind="strike-draw-requirement-disagreement",
                message=(
                    "creature strike draw requirement disagrees "
                    f"with equipment: {strike['name']}"
                ),
                field="requiresDrawAfterUse",
                creature_value=bool(
                    strike.get("requiresDrawAfterUse")
                ),
                equipment_value=expected_requires_draw,
            )


def _semantic_creature_default_reach(definition: dict[str, Any]) -> int:
    space = definition.get("space")
    if (
        type(space) is not dict
        or space.get("ruleRef") != SEMANTIC_CREATURE_REACH_RULE_REF
    ):
        raise EngineInputError(
            "semantic creature default reach lacks its stable ruleRef: "
            f"{definition.get('id')}"
        )
    default_reach = space.get("defaultReachFeet")
    if (
        type(default_reach) is not int
        or default_reach < 0
        or default_reach % 5
    ):
        raise EngineInputError(
            "semantic creature default reach is invalid: "
            f"{definition.get('id')}"
        )
    return default_reach


def _validate_semantic_bound_strike(
    definition: dict[str, Any],
    strike: dict[str, Any],
    item: dict[str, Any],
) -> None:
    """Validate the item mechanics without consulting source-name bindings."""

    item_id = str(item.get("id") or "")
    strike_id = str(strike.get("id") or "")
    if item.get("kind") != "weapon":
        raise EngineInputError(
            f"semantic item-backed Strike is not a weapon: {strike_id}"
        )
    if strike.get("kind") not in weapon_strike_modes(item):
        raise EngineInputError(
            f"semantic Strike mode disagrees with its item: {strike_id}"
        )
    item_damage = item.get("damage")
    strike_damage = strike.get("damage")
    if (
        type(item_damage) is not dict
        or type(strike_damage) is not dict
        or strike_damage.get("type") != item_damage.get("type")
    ):
        raise EngineInputError(
            f"semantic Strike damage type disagrees with its item: {strike_id}"
        )

    for trait_name in ("agile", "backstabber", "finesse", "trip"):
        strike_has_trait = trait_name in (strike.get("traits") or [])
        item_has_trait = trait_by_name(item, trait_name) is not None
        if (
            trait_name == "finesse"
            and strike.get("kind") == "ranged"
            and item_has_trait
        ):
            continue
        if strike_has_trait != item_has_trait:
            raise EngineInputError(
                "semantic Strike trait disagrees with its item: "
                f"{strike_id} {trait_name}"
            )

    if strike.get("kind") == "melee":
        reach_trait = trait_by_name(item, "reach")
        expected_reach = _semantic_creature_default_reach(definition)
        if reach_trait is not None:
            expected_reach += int(reach_trait["reachFeet"]) - 5
        if strike.get("reachFeet") != expected_reach:
            raise EngineInputError(
                f"semantic Strike reach disagrees with its item: {strike_id}"
            )
        return

    (
        expected_range,
        expected_reload,
        expected_requires_draw,
    ) = ranged_weapon_statistics(item)
    if strike.get("rangeIncrementFeet") != expected_range:
        raise EngineInputError(
            f"semantic Strike range disagrees with its item: {strike_id}"
        )
    source_reload = strike.get("reloadActions")
    if source_reload != expected_reload and not (
        expected_reload == 0 and source_reload is None
    ):
        raise EngineInputError(
            f"semantic Strike reload disagrees with its item: {strike_id}"
        )
    expected_thrown = (
        f"thrown {expected_range} feet"
        if trait_by_name(item, "thrown") is not None
        else None
    )
    if creature_trait_value(strike, "thrown ") != expected_thrown:
        raise EngineInputError(
            f"semantic Strike thrown trait disagrees with its item: {strike_id}"
        )
    if bool(strike.get("requiresDrawAfterUse")) != expected_requires_draw:
        raise EngineInputError(
            "semantic Strike draw requirement disagrees with its item: "
            f"{strike_id}"
        )


def bind_semantic_creature_equipment(
    definition: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Bind semantic inventory and attackSource identities without names."""

    result = deepcopy(definition)
    _require_semantic_source_free(result, "semantic creature definition")
    inventory = result.get("inventory") or []
    strikes = result.get("strikes") or []
    if type(inventory) is not list or type(strikes) is not list:
        raise EngineInputError("semantic creature equipment fields are invalid")

    references = result.get("references")
    raw_item_refs = (
        references.get("items")
        if type(references) is dict
        else None
    )
    if raw_item_refs is None:
        raw_item_refs = []
    if (
        type(raw_item_refs) is not list
        or any(type(item) is not str for item in raw_item_refs)
        or raw_item_refs != sorted(set(raw_item_refs))
    ):
        raise EngineInputError(
            "semantic creature item references are invalid"
        )

    bound_inventory = []
    inventory_ids: set[str] = set()
    for index, entry in enumerate(inventory):
        if (
            type(entry) is not dict
            or set(entry) != {"itemEntityId", "quantity"}
            or type(entry.get("itemEntityId")) is not str
            or entry["itemEntityId"] in inventory_ids
            or type(entry.get("quantity")) is not int
            or not 1 <= entry["quantity"] <= 9_223_372_036_854_775_807
        ):
            raise EngineInputError(
                f"semantic creature inventory row is invalid: {index}"
            )
        item_id = entry["itemEntityId"]
        item = catalog_item(catalog, item_id)
        inventory_ids.add(item_id)
        bound_inventory.append(
            {
                "itemEntityId": item_id,
                "itemId": item_id,
                "quantity": entry["quantity"],
                "kind": item["kind"],
                "bindingStatus": "semantic-entity",
            }
        )

    strike_item_ids: set[str] = set()
    seen_strike_ids: set[str] = set()
    for strike in strikes:
        if type(strike) is not dict or type(strike.get("id")) is not str:
            raise EngineInputError("semantic creature Strike is invalid")
        strike_id = strike["id"]
        if strike_id in seen_strike_ids:
            raise EngineInputError("semantic creature Strike IDs are duplicated")
        seen_strike_ids.add(strike_id)
        if any(
            field in strike
            for field in (
                "equipmentContractId",
                "equipmentModifiers",
                "equipmentSource",
                "itemId",
            )
        ):
            raise EngineInputError(
                f"semantic Strike contains a prebound source item: {strike_id}"
            )
        attack_source = strike.get("attackSource")
        if attack_source == {"kind": "natural"}:
            continue
        if (
            type(attack_source) is not dict
            or set(attack_source) != {"kind", "itemEntityId"}
            or attack_source.get("kind") != "item"
            or type(attack_source.get("itemEntityId")) is not str
        ):
            raise EngineInputError(
                f"semantic Strike attackSource is invalid: {strike_id}"
            )
        item_id = attack_source["itemEntityId"]
        if item_id not in inventory_ids:
            raise EngineInputError(
                f"semantic Strike item is absent from inventory: {strike_id}"
            )
        item = catalog_item(catalog, item_id)
        _validate_semantic_bound_strike(result, strike, item)
        strike_item_ids.add(item_id)
        strike["itemId"] = item_id
        if strike.get("kind") == "ranged":
            (_range, reload_actions, _draw) = ranged_weapon_statistics(item)
            if reload_actions == 0 and strike.get("reloadActions") is None:
                strike["reloadActions"] = 0
        deadly = trait_by_name(item, "deadly")
        backstabber = trait_by_name(item, "backstabber")
        versatile = selected_versatile_damage_types(strike, item)
        if deadly is not None:
            strike["deadly"] = deepcopy(deadly["die"])
        if backstabber is not None:
            strike["backstabberPrecisionDamage"] = int(
                backstabber["precisionDamage"]
            )
        if versatile:
            strike["versatileDamageTypes"] = versatile
        if item.get("ammunitionItemId"):
            strike["ammunitionItemId"] = item["ammunitionItemId"]
        if (
            strike.get("kind") == "ranged"
            and trait_by_name(item, "thrown") is not None
        ):
            strike["thrownWeapon"] = True

    referenced_ids = set(raw_item_refs)
    if referenced_ids != inventory_ids | strike_item_ids:
        raise EngineInputError(
            "semantic creature item references do not match inventory and Strikes"
        )
    result["inventory"] = bound_inventory
    result["wornArmorItemId"] = None
    return result


def bind_creature_equipment(definition: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """Link Monster Core inventory and final Strikes to Player Core items."""

    result = deepcopy(definition)
    inventory = result.get("inventory") or []
    bound_inventory = []
    strike_item_by_name: dict[
        str,
        tuple[dict[str, Any], dict[str, Any]],
    ] = {}
    armor_ids = []
    for entry in inventory:
        binding = equipment_binding(entry.get("name"))
        item = catalog_item(catalog, binding["itemId"])
        bound = {
            **deepcopy(entry),
            "itemId": item["id"],
            "kind": item["kind"],
            "bindingStatus": binding["bindingStatus"],
            "equipmentContractId": binding["contractId"],
        }
        if binding.get("modifiers"):
            bound["modifiers"] = deepcopy(binding["modifiers"])
        if binding.get("quality"):
            bound["quality"] = str(binding["quality"])
        bound_inventory.append(bound)
        for strike_name in binding["strikeNames"]:
            normalized_strike_name = normalized_source_name(
                strike_name
            )
            prior = strike_item_by_name.get(normalized_strike_name)
            if (
                prior is not None
                and prior[0]["id"] != item["id"]
            ):
                raise EngineInputError(
                    "creature equipment has ambiguous Strike binding: "
                    f"{result['name']} {strike_name}"
                )
            strike_item_by_name[normalized_strike_name] = (
                item,
                binding,
            )
        if item["kind"] == "armor":
            armor_ids.append(item["id"])
    if len(armor_ids) > 1:
        raise EngineInputError(f"creature has ambiguous worn armor: {result['name']}")
    result["inventory"] = bound_inventory
    result["wornArmorItemId"] = armor_ids[0] if armor_ids else None
    if armor_ids:
        result["defenses"]["armorClassEquipmentItemId"] = armor_ids[0]

    for strike in result.get("strikes") or []:
        matched = strike_item_by_name.get(
            normalized_source_name(strike.get("name"))
        )
        if matched is None:
            continue
        item, binding = matched
        if item["kind"] == "weapon":
            validate_bound_strike(
                result,
                strike,
                item,
                binding,
            )
            if strike.get("kind") == "ranged":
                (
                    _range_increment,
                    canonical_reload_actions,
                    _requires_draw,
                ) = ranged_weapon_statistics(item)
                if (
                    canonical_reload_actions == 0
                    and strike.get("reloadActions") is None
                ):
                    strike["reloadActions"] = 0
        strike["itemId"] = item["id"]
        strike["equipmentSource"] = deepcopy(item["source"])
        if binding.get("modifiers"):
            strike["equipmentModifiers"] = deepcopy(
                binding["modifiers"]
            )
        if item["kind"] != "weapon":
            continue
        deadly = trait_by_name(item, "deadly")
        backstabber = trait_by_name(item, "backstabber")
        versatile_damage_types = selected_versatile_damage_types(
            strike,
            item,
        )
        if deadly:
            strike["deadly"] = deepcopy(deadly["die"])
        if backstabber:
            strike["backstabberPrecisionDamage"] = int(backstabber["precisionDamage"])
        if versatile_damage_types:
            strike["versatileDamageTypes"] = (
                versatile_damage_types
            )
        if item.get("ammunitionItemId"):
            strike["ammunitionItemId"] = item["ammunitionItemId"]
        if (
            strike.get("kind") == "ranged"
            and trait_by_name(item, "thrown")
        ):
            strike["thrownWeapon"] = True
    return result


def initial_semantic_equipment_state(
    definition: dict[str, Any],
    catalog: dict[str, Any],
    loadout: Any,
) -> dict[str, Any] | None:
    """Create the engine state from already-bound semantic item identities."""

    inventory = definition.get("inventory") or []
    if not inventory:
        if loadout not in (None, {}):
            raise EngineInputError(
                "creature without semantic equipment cannot have a loadout: "
                f"{definition['name']}"
            )
        return None
    if (
        type(loadout) is not dict
        or set(loadout)
        not in (
            {"wieldedStrikeId"},
            {"wieldedStrikeId", "heldShieldItemId"},
        )
        or type(loadout.get("wieldedStrikeId")) is not str
        or not loadout["wieldedStrikeId"]
    ):
        raise EngineInputError(
            "equipped semantic creature requires exactly one reviewed loadout: "
            f"{definition['name']}"
        )
    strike_id = loadout["wieldedStrikeId"]
    matches = [
        strike
        for strike in definition.get("strikes") or []
        if strike.get("id") == strike_id and type(strike.get("itemId")) is str
    ]
    if len(matches) != 1:
        raise EngineInputError(
            f"semantic loadout weapon Strike is invalid: "
            f"{definition['name']} {strike_id}"
        )
    strike = matches[0]
    wielded_item = catalog_item(catalog, strike["itemId"])

    held_shield_item_id = loadout.get("heldShieldItemId")
    if held_shield_item_id is not None and (
        type(held_shield_item_id) is not str or not held_shield_item_id
    ):
        raise EngineInputError("semantic loadout held shield identity is invalid")
    held_shield = None
    if held_shield_item_id is not None:
        shield_entries = [
            entry
            for entry in inventory
            if entry.get("itemId") == held_shield_item_id
        ]
        if len(shield_entries) != 1 or shield_entries[0]["quantity"] < 1:
            raise EngineInputError(
                "semantic loadout held shield is absent or ambiguous"
            )
        held_shield = catalog_item(catalog, held_shield_item_id)
        if held_shield.get("kind") != "shield":
            raise EngineInputError(
                "semantic loadout heldShieldItemId is not a shield"
            )

    hands = wielded_item.get("hands")
    if type(hands) is not dict:
        raise EngineInputError("semantic wielded weapon Hands are invalid")
    total_hands = 2
    weapon_holding = int(hands["holding"])
    required_to_use = int(hands["requiredToUse"])
    shield_holding = (
        int(held_shield["hands"]["holding"])
        if held_shield is not None
        else 0
    )
    holding = weapon_holding + shield_holding
    free = total_hands - holding
    if holding > total_hands or required_to_use > holding + free:
        raise EngineInputError(
            f"semantic loadout cannot wield its selected weapon: "
            f"{definition['name']}"
        )

    item_states = []
    for entry in inventory:
        item = catalog_item(catalog, entry["itemId"])
        carried = (
            "held"
            if item["id"] in {wielded_item["id"], held_shield_item_id}
            else "carried"
        )
        item_states.append(
            {
                "itemEntityId": item["id"],
                "itemId": item["id"],
                "quantity": int(entry["quantity"]),
                "carried": carried,
                "equipped": False,
            }
        )
    return {
        "items": item_states,
        "wornArmorItemId": None,
        "wieldedStrikeId": strike_id,
        "wieldedItemId": wielded_item["id"],
        "heldShieldItemId": held_shield_item_id,
        "hands": {
            "total": total_hands,
            "holding": holding,
            "free": free,
            "requiredToUse": required_to_use,
            "ready": required_to_use <= holding + free,
            "ruleRef": SEMANTIC_WIELDING_RULE_REF,
        },
    }


def initial_equipment_state(
    definition: dict[str, Any],
    catalog: dict[str, Any],
    loadout: Any,
) -> dict[str, Any] | None:
    inventory = definition.get("inventory") or []
    if not inventory:
        if loadout not in (None, {}):
            raise EngineInputError(f"creature without equipment cannot have a loadout: {definition['name']}")
        return None
    if (
        not isinstance(loadout, dict)
        or "wieldedStrikeId" not in loadout
    ):
        raise EngineInputError(
            "equipped creature requires exactly "
            "loadout.wieldedStrikeId: "
            f"{definition['name']}"
        )
    if set(loadout) not in (
        {"wieldedStrikeId"},
        {"wieldedStrikeId", "heldShieldItemId"},
    ):
        raise EngineInputError(
            "equipped creature loadout fields are invalid: "
            f"{definition['name']}"
        )
    strike_id = str(loadout.get("wieldedStrikeId") or "")
    selected_strikes = [
        strike
        for strike in definition.get("strikes") or []
        if strike.get("id") == strike_id
    ]
    matches = [
        strike
        for strike in selected_strikes
        if strike.get("itemId")
    ]
    if len(matches) != 1:
        unreviewed_weapon_bindings = []
        if len(selected_strikes) == 1:
            for entry in inventory:
                if entry.get("kind") != "weapon":
                    continue
                binding = equipment_binding(entry.get("name"))
                if binding["strikeNames"]:
                    continue
                unreviewed_weapon_bindings.append(
                    (
                        catalog_item(
                            catalog,
                            str(entry.get("itemId") or ""),
                        ),
                        binding,
                    )
                )
        if len(unreviewed_weapon_bindings) == 1:
            item, binding = unreviewed_weapon_bindings[0]
            raise strike_binding_blocker(
                definition,
                selected_strikes[0],
                item,
                binding,
                reason_kind="strike-unreviewed-loadout-name",
                message=(
                    "loadout weapon Strike is invalid: "
                    f"{definition['name']} {strike_id}"
                ),
                field="strikeNames",
                creature_value=selected_strikes[0].get("name"),
                equipment_value=deepcopy(binding["strikeNames"]),
            )
        raise EngineInputError(f"loadout weapon Strike is invalid: {definition['name']} {strike_id}")
    strike = matches[0]
    wielded_item = catalog_item(catalog, strike["itemId"])
    held_shield_item_id = str(
        loadout.get("heldShieldItemId") or ""
    )
    held_shield = None
    if held_shield_item_id:
        shield_entries = [
            entry
            for entry in inventory
            if entry.get("itemId") == held_shield_item_id
        ]
        if (
            len(shield_entries) != 1
            or int(shield_entries[0].get("quantity", 0)) < 1
        ):
            raise EngineInputError(
                "loadout held shield is absent or ambiguous: "
                f"{definition['name']}"
            )
        held_shield = catalog_item(
            catalog,
            held_shield_item_id,
        )
        if held_shield.get("kind") != "shield":
            raise EngineInputError(
                "loadout heldShieldItemId is not a shield"
            )
    hands = wielded_item["hands"]
    total_hands = 2
    weapon_holding = int(hands["holding"])
    required_to_use = int(hands["requiredToUse"])
    shield_holding = (
        int(held_shield["hands"]["holding"])
        if held_shield is not None
        else 0
    )
    holding = weapon_holding + shield_holding
    free = total_hands - holding
    if (
        holding > total_hands
        or required_to_use > weapon_holding + free
    ):
        raise EngineInputError(f"loadout cannot wield its selected weapon: {definition['name']}")
    item_states = []
    for entry in inventory:
        item = catalog_item(catalog, entry["itemId"])
        if item["id"] in {
            wielded_item["id"],
            held_shield_item_id,
        }:
            carried = "held"
        else:
            carried = "worn"
        item_state = {
            "itemId": item["id"],
            "quantity": int(entry["quantity"]),
            "carried": carried,
            "equipped": item["id"] == definition.get("wornArmorItemId"),
            "sourceText": entry["sourceText"],
        }
        if entry.get("quality"):
            item_state["quality"] = str(entry["quality"])
        item_states.append(item_state)
    return {
        "items": item_states,
        "wornArmorItemId": definition.get("wornArmorItemId"),
        "wieldedStrikeId": strike_id,
        "wieldedItemId": wielded_item["id"],
        "heldShieldItemId": (
            held_shield_item_id or None
        ),
        "hands": {
            "total": total_hands,
            "holding": holding,
            "free": free,
            "requiredToUse": required_to_use,
            "ready": required_to_use <= holding + free,
            "rule": deepcopy(WIELDING_RULE),
        },
    }


def initial_semantic_item_instances(
    participant_id: str,
    equipment: dict[str, Any] | None,
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expand semantic inventory without carrying source prose into play."""

    if equipment is None:
        return []
    instances: list[dict[str, Any]] = []
    wielded_item_id = str(equipment.get("wieldedItemId") or "")
    wielded_strike_id = str(equipment.get("wieldedStrikeId") or "")
    held_shield_item_id = str(equipment.get("heldShieldItemId") or "")
    wielded_created = False
    shield_created = False
    for occurrence, entry in enumerate(equipment.get("items") or []):
        item_id = str(entry.get("itemId") or "")
        item = catalog_item(catalog, item_id)
        quantity = int(entry.get("quantity", 0))
        if quantity <= 0:
            raise EngineInputError(
                f"initial semantic equipment quantity is invalid: {item_id}"
            )
        for physical_ordinal in range(quantity):
            material = (
                f"{participant_id}\0{occurrence}\0"
                f"{physical_ordinal}\0{item_id}"
            ).encode("utf-8")
            instance: dict[str, Any] = {
                "itemRef": (
                    "match-item-"
                    + hashlib.sha256(material).hexdigest()[:32]
                ),
                "itemEntityId": item_id,
                "itemId": item_id,
                "openingParticipantId": participant_id,
                "equipped": bool(entry.get("equipped")),
            }
            durability_profile = durability.durability_profile(item)
            if durability_profile is not None:
                instance["currentHitPoints"] = int(
                    durability_profile["maximumHitPoints"]
                )
            if item_id == wielded_item_id and not wielded_created:
                hands = item.get("hands")
                if type(hands) is not dict:
                    raise EngineInputError(
                        f"semantic wielded item Hands are invalid: {item_id}"
                    )
                holding = int(hands["holding"])
                instance["custody"] = {
                    "kind": "held",
                    "participantId": participant_id,
                    "hands": ["right"] if holding == 1 else ["left", "right"],
                    "wieldedStrikeId": wielded_strike_id,
                }
                wielded_created = True
            elif item_id == held_shield_item_id and not shield_created:
                instance["custody"] = {
                    "kind": "held",
                    "participantId": participant_id,
                    "hands": ["left"],
                }
                shield_created = True
            else:
                instance["custody"] = {
                    "kind": "carried",
                    "participantId": participant_id,
                }
            instances.append(instance)
    if wielded_item_id and not wielded_created:
        raise EngineInputError(
            f"semantic wielded item is absent from exact inventory: "
            f"{wielded_item_id}"
        )
    if held_shield_item_id and not shield_created:
        raise EngineInputError(
            "semantic held shield is absent from exact inventory"
        )
    return instances


def initial_item_instances(
    participant_id: str,
    equipment: dict[str, Any] | None,
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expand grouped creature inventory into exact match-local objects.

    These opaque references are deterministic only so the same battleground
    request compiles to the same digest. Persistent matches replace them with
    reservation-authored random references before observer admission.
    """

    if equipment is None:
        return []
    instances: list[dict[str, Any]] = []
    wielded_item_id = str(equipment.get("wieldedItemId") or "")
    wielded_strike_id = str(
        equipment.get("wieldedStrikeId") or ""
    )
    held_shield_item_id = str(
        equipment.get("heldShieldItemId") or ""
    )
    wielded_created = False
    shield_created = False
    for occurrence, entry in enumerate(equipment.get("items") or []):
        item_id = str(entry.get("itemId") or "")
        item = catalog_item(catalog, item_id)
        quantity = int(entry.get("quantity", 0))
        if quantity <= 0:
            raise EngineInputError(
                f"initial equipment quantity is invalid: {item_id}"
            )
        for physical_ordinal in range(quantity):
            material = (
                f"{participant_id}\0{occurrence}\0"
                f"{physical_ordinal}\0{item_id}"
            ).encode("utf-8")
            item_ref = (
                "match-item-"
                + hashlib.sha256(material).hexdigest()[:32]
            )
            instance = {
                "itemRef": item_ref,
                "itemId": item_id,
                "openingParticipantId": participant_id,
                "sourceText": str(entry.get("sourceText") or ""),
                "equipped": bool(entry.get("equipped")),
            }
            if entry.get("quality"):
                instance["quality"] = str(entry["quality"])
            durability_profile = durability.durability_profile(
                item,
                quality=instance.get("quality"),
            )
            if durability_profile is not None:
                instance["currentHitPoints"] = int(
                    durability_profile["maximumHitPoints"]
                )
            if item_id == wielded_item_id and not wielded_created:
                hands = item.get("hands")
                if not isinstance(hands, dict):
                    raise EngineInputError(
                        f"wielded item Hands are invalid: {item_id}"
                    )
                holding = int(hands["holding"])
                instance["custody"] = {
                    "kind": "held",
                    "participantId": participant_id,
                    "hands": (
                        ["right"]
                        if holding == 1
                        else ["left", "right"]
                    ),
                    "wieldedStrikeId": wielded_strike_id,
                }
                wielded_created = True
            elif (
                item_id == held_shield_item_id
                and not shield_created
            ):
                hands = item.get("hands")
                if (
                    not isinstance(hands, dict)
                    or int(hands.get("holding", 0)) != 1
                    or int(hands.get("requiredToUse", 0)) != 1
                ):
                    raise EngineInputError(
                        f"held shield Hands are invalid: {item_id}"
                    )
                instance["custody"] = {
                    "kind": "held",
                    "participantId": participant_id,
                    "hands": ["left"],
                }
                shield_created = True
            elif instance["equipped"]:
                instance["custody"] = {
                    "kind": "worn",
                    "participantId": participant_id,
                }
            else:
                instance["custody"] = {
                    "kind": "carried",
                    "participantId": participant_id,
                }
            instances.append(instance)
    if wielded_item_id and not wielded_created:
        raise EngineInputError(
            f"wielded item is absent from exact inventory: "
            f"{wielded_item_id}"
        )
    if held_shield_item_id and not shield_created:
        raise EngineInputError(
            "held shield is absent from exact inventory: "
            f"{held_shield_item_id}"
        )
    return instances

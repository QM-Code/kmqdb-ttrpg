#!/usr/bin/env python3
"""Build the deterministic PF2ER persistent-item catalog from cache only."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable


TTRPG_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TTRPG_ROOT
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from subdomains.ttrpg import backend, item_catalog
from subdomains.ttrpg.pf2er_compiler import durability as durability_rules
from subdomains.ttrpg.pf2er_compiler import equipment
from subdomains.ttrpg.pf2er_compiler.mechanics.equipment_bindings import (
    runtime_equipment_bindings,
)
from subdomains.ttrpg.pf2er_compiler.mechanics import healing_potion
from subdomains.ttrpg.pf2er_compiler.source_nodes import (
    OrderedObject,
    content_target,
)


COMPILER = {
    "id": "pf2er-persistent-item-catalog",
    "version": 2,
}
DEFAULT_SOURCE_CACHE = TTRPG_ROOT / "cache" / "cache.db"
DEFAULT_ITEM_CATALOG = item_catalog.DEFAULT_CATALOG_PATH

MONEY_RE = re.compile(
    r"^(?P<amount>(?:0|[1-9]\d{0,2}(?:,\d{3})*))"
    r"(?:\s+(?P<unit>cp|sp|gp|pp))?$"
)
LEVEL_RE = re.compile(r"\s+\(level\s+(?P<level>\d+)\)$", re.IGNORECASE)
HEALING_POTION_RE = re.compile(
    r"^The potion restores (?P<count>\d+)d(?P<sides>\d+)"
    r"(?:\+(?P<modifier>\d+))? Hit Points\.$"
)
SHIELD_HP_RE = re.compile(
    r"^(?P<hp>\d+)\s+\((?P<bt>\d+)\)$"
)
SHIELD_COLUMNS = (
    "Shield",
    "Price",
    "AC Bonus<sup>1</sup>",
    "Speed Penalty",
    "Bulk",
    "Hardness",
    "HP (BT)",
)
GEAR_COLUMNS = ("Item", "Price", "Bulk", "Hands")


class ItemCatalogBuildError(Exception):
    """The authenticated cache could not produce a safe item catalog."""


def _source_root(
    packet: dict[str, Any],
    *,
    source_id: str,
    locator: str,
) -> OrderedObject:
    target = packet.get("target", {}).get("selected")
    section = packet.get("content", {}).get("section")
    if not isinstance(target, dict) or not isinstance(section, dict):
        raise ItemCatalogBuildError(
            "item source packet is incomplete"
        )
    if (
        str(target.get("source_id") or "") != source_id
        or str(target.get("locator") or "") != locator
        or str(section.get("id") or "")
        != str(target.get("section_id") or "")
        or str(section.get("source_id") or "") != source_id
        or not isinstance(target.get("content_path"), list)
    ):
        raise ItemCatalogBuildError(
            "item source packet identity changed: "
            f"{source_id}:{locator}"
        )
    return content_target(
        str(section.get("content") or ""),
        [str(part) for part in target["content_path"]],
    )


def _row_digest(row: object) -> str:
    return hashlib.sha256(
        json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _reviewed_rows(
    root: object,
    binding: dict[str, Any],
) -> list[tuple[list[str], object]]:
    expected = {
        str(value)
        for value in binding["source"]["rowSelectionSha256"]
    }
    matches = [
        (columns, row)
        for columns, rows in equipment.table_records(root)
        for row in rows
        if _row_digest(row) in expected
    ]
    actual = {_row_digest(row) for _columns, row in matches}
    if not expected or actual != expected:
        raise ItemCatalogBuildError(
            "reviewed source rows changed for "
            f"{binding['sourceName']}"
        )
    return matches


def _compile_shield(
    root: object,
    binding: dict[str, Any],
    base_item: dict[str, Any],
) -> dict[str, Any]:
    matches = _reviewed_rows(root, binding)
    rows = [
        (columns, row)
        for columns, row in matches
        if isinstance(row, list)
    ]
    if len(rows) != 1 or tuple(rows[0][0]) != SHIELD_COLUMNS:
        raise ItemCatalogBuildError(
            "reviewed shield row is missing or ambiguous: "
            f"{binding['sourceName']}"
        )
    columns, row = rows[0]
    fields = equipment.row_mapping(columns, row)
    hp_match = SHIELD_HP_RE.fullmatch(fields["HP (BT)"])
    ac_text = fields["AC Bonus<sup>1</sup>"].strip()
    if hp_match is None or not ac_text.startswith("+") or not ac_text[1:].isdigit():
        raise ItemCatalogBuildError(
            "reviewed shield statistics are invalid: "
            f"{binding['sourceName']}"
        )
    result = deepcopy(base_item)
    result.update(
        {
            "level": 0,
            "rarity": "common",
            "price": fields["Price"],
            "armorClassBonus": int(ac_text[1:]),
            "speedPenaltyFeet": equipment.dash_integer(
                fields["Speed Penalty"],
                "shield Speed Penalty",
            ),
            "bulk": equipment.bulk_value(fields["Bulk"]),
            "hands": {
                "holding": 1,
                "requiredToUse": 1,
                "freeHandCompletesUse": False,
            },
            "durability": {
                "hardness": int(fields["Hardness"]),
                "maximumHitPoints": int(hp_match.group("hp")),
                "brokenThreshold": int(hp_match.group("bt")),
                "rule": {
                    "sourceId": "core-pc1",
                    "locator": "274.1",
                },
            },
            "rules": {
                "statistics": {
                    "sourceId": "core-pc1",
                    "locator": "274.1",
                },
                "wielding": {
                    "sourceId": "core-pc1",
                    "locator": "274.2",
                },
            },
        }
    )
    return result


def _compile_gear(
    root: object,
    binding: dict[str, Any],
    base_item: dict[str, Any],
) -> dict[str, Any]:
    expected = {
        str(value)
        for value in binding["source"]["rowSelectionSha256"]
    }
    rows: list[tuple[list[str], list[object]]] = []
    composite_parent: str | None = None
    for columns, table_rows in equipment.table_records(root):
        prior_header: str | None = None
        for row in table_rows:
            if isinstance(row, dict) and row.get("type") == "header":
                data = row.get("data")
                prior_header = (
                    str(data[0])
                    if isinstance(data, list) and data
                    else None
                )
                continue
            if isinstance(row, list) and _row_digest(row) in expected:
                rows.append((columns, row))
                composite_parent = prior_header
    if len(rows) != 1 or tuple(rows[0][0]) != GEAR_COLUMNS:
        raise ItemCatalogBuildError(
            "reviewed gear row is missing or ambiguous: "
            f"{binding['sourceName']}"
        )
    columns, row = rows[0]
    actual = {_row_digest(row)}
    if actual != expected:
        if (
            len(expected) != 2
            or composite_parent is None
            or len(row) != len(columns)
        ):
            raise ItemCatalogBuildError(
                "reviewed gear composite changed for "
                f"{binding['sourceName']}"
            )
        leaf_name = str(row[0])
        qualified_names = {
            equipment.normalized_source_name(
                f"{composite_parent} ({leaf_name})"
            ),
            equipment.normalized_source_name(
                f"{leaf_name} {composite_parent}"
            ),
        }
        if equipment.normalized_source_name(
            binding["rowName"]
        ) not in qualified_names:
            raise ItemCatalogBuildError(
                "reviewed gear parent qualification changed for "
                f"{binding['sourceName']}"
            )
    fields = equipment.row_mapping(columns, row)
    raw_name = fields["Item"]
    level_match = LEVEL_RE.search(raw_name)
    result = deepcopy(base_item)
    result.update(
        {
            "level": (
                int(level_match.group("level"))
                if level_match is not None
                else 0
            ),
            "rarity": "common",
            "price": fields["Price"],
            "bulk": equipment.bulk_value(fields["Bulk"]),
        }
    )
    source = result.get("source")
    if not isinstance(source, dict):
        raise ItemCatalogBuildError(
            "compiled gear lacks source provenance"
        )
    source["catalogRow"] = {
        "columns": columns,
        "rowSelectionSha256": sorted(
            binding["source"]["rowSelectionSha256"]
        ),
    }
    return result


def _compile_source_item(
    root: OrderedObject,
    binding: dict[str, Any],
    base_item: dict[str, Any],
) -> dict[str, Any]:
    name = str(root.unique("Name"))
    level = root.unique("Level")
    price = root.unique("Price")
    bulk = root.unique("Bulk")
    if equipment.normalized_source_name(name) != equipment.normalized_source_name(
        binding["sourceName"]
    ):
        raise ItemCatalogBuildError(
            "source item name disagrees with its reviewed binding: "
            f"{binding['sourceName']}"
        )
    if type(level) is not int or level < 0:
        raise ItemCatalogBuildError(
            f"source item level is invalid: {binding['sourceName']}"
        )
    traits = root.unique("Traits", required=False, default=[])
    if not isinstance(traits, list) or any(
        not isinstance(trait, str) or not trait.strip()
        for trait in traits
    ):
        raise ItemCatalogBuildError(
            f"source item traits are invalid: {binding['sourceName']}"
        )
    result = deepcopy(base_item)
    result.update(
        {
            "name": name,
            "level": level,
            "rarity": (
                "uncommon"
                if any(
                    trait.strip().casefold() == "uncommon"
                    for trait in traits
                )
                else "rare"
                if any(
                    trait.strip().casefold() == "rare"
                    for trait in traits
                )
                else "common"
            ),
            "price": str(price),
            "bulk": equipment.bulk_value(bulk),
            "traits": [
                trait.strip().casefold() for trait in traits
            ],
        }
    )
    return result


def _compile_healing_potion_definitions(
    root: OrderedObject,
) -> list[dict[str, Any]]:
    """Compile every exact GM Core Healing Potion variant."""

    activate = root.unique("Activate")
    variants = root.unique("Variants")
    if (
        root.unique("Name") != "Healing Potion"
        or root.unique("Level") != "1+"
        or root.unique("Traits")
        != ["Consumable", "Healing", "Magical", "Potion", "Vitality"]
        or root.unique("Usage") != "held in 1 hand"
        or root.unique("Bulk") != "L"
        or not isinstance(activate, OrderedObject)
        or activate.pairs
        != (("Actions", "single"), ("Traits", ["manipulate"]))
        or not isinstance(variants, list)
    ):
        raise ItemCatalogBuildError(
            "Healing Potion source contract changed"
        )
    compiled: dict[str, dict[str, Any]] = {}
    for value in variants:
        if not isinstance(value, OrderedObject):
            raise ItemCatalogBuildError(
                "Healing Potion variant is invalid"
            )
        variant = value.unique("Type")
        level = value.unique("Level")
        price = value.unique("Price")
        description = value.unique("Description")
        match = HEALING_POTION_RE.fullmatch(str(description))
        if (
            not isinstance(variant, str)
            or variant in compiled
            or type(level) is not int
            or not isinstance(price, str)
            or match is None
        ):
            raise ItemCatalogBuildError(
                "Healing Potion variant contract changed"
            )
        profile = {
            "level": level,
            "price": price,
            "healing": {
                "dice": {
                    "count": int(match.group("count")),
                    "sides": int(match.group("sides")),
                },
                "modifier": int(match.group("modifier") or 0),
            },
        }
        expected = healing_potion.VARIANTS.get(variant)
        if profile != expected:
            raise ItemCatalogBuildError(
                f"Healing Potion {variant} profile changed"
            )
        mechanics = healing_potion.mechanics(variant)
        item_id = healing_potion.item_id(variant)
        compiled[variant] = {
            "schema": 1,
            "kind": "pf2er-item-definition",
            "rulesetId": item_catalog.RULESET_ID,
            "definitionId": item_id,
            "itemId": item_id,
            "itemKind": "consumable",
            "name": healing_potion.definition_name(variant),
            "configuration": {
                "itemId": item_id,
                "quality": None,
                "modifiers": [],
            },
            "mechanics": mechanics,
            "sourceReceipts": [
                {
                    **deepcopy(healing_potion.SOURCE),
                    "field": "item-and-variant",
                    "variant": variant,
                },
                {
                    **deepcopy(
                        healing_potion.ACTIVATING_ITEMS_RULE
                    ),
                    "field": "activation",
                },
                {
                    **deepcopy(healing_potion.CONSUMABLE_RULE),
                    "field": "consumption",
                },
            ],
            "support": {
                "identity": {"status": "ready", "blockers": []},
                "price": {"status": "ready", "blockers": []},
                "durability": {
                    "status": "not-applicable",
                    "blockers": [],
                },
            },
            "price": {
                **_money(price),
                "unitQuantity": 1,
            },
        }
    if set(compiled) != set(healing_potion.VARIANTS):
        raise ItemCatalogBuildError(
            "Healing Potion variant census changed"
        )
    return [
        compiled[variant]
        for variant in healing_potion.VARIANTS
    ]


def _compile_modifier(
    modifier: dict[str, Any],
    source_roots: dict[tuple[str, str], OrderedObject],
) -> dict[str, Any]:
    source = modifier.get("source")
    if not isinstance(source, dict):
        raise ItemCatalogBuildError(
            "equipment modifier lacks source provenance"
        )
    selector = source.get("variantSelector")
    if not isinstance(selector, str) or not selector:
        return deepcopy(modifier)
    source_id = str(source.get("sourceId") or "")
    locator = str(source.get("locator") or "")
    root = source_roots.get((source_id, locator))
    if root is None:
        raise ItemCatalogBuildError(
            "equipment modifier source root is unavailable: "
            f"{source_id}:{locator}"
        )
    variants = root.unique("Variants")
    if not isinstance(variants, list):
        raise ItemCatalogBuildError(
            "equipment modifier variants are invalid"
        )
    matches = [
        variant
        for variant in variants
        if (
            isinstance(variant, OrderedObject)
            and str(variant.unique("Type") or "") == selector
        )
    ]
    if len(matches) != 1:
        raise ItemCatalogBuildError(
            "equipment modifier variant is missing or ambiguous: "
            f"{selector}"
        )
    variant = matches[0]
    level = variant.unique("Level")
    price = variant.unique("Price")
    if type(level) is not int or level < 0:
        raise ItemCatalogBuildError(
            f"equipment modifier level is invalid: {selector}"
        )
    result = deepcopy(modifier)
    result["level"] = level
    result["price"] = _money(price)
    return result


def _money(value: object) -> dict[str, Any]:
    text = str(value or "").strip()
    match = MONEY_RE.fullmatch(text)
    if match is None:
        raise ItemCatalogBuildError(
            f"equipment Price is unsupported: {value}"
        )
    unit = match.group("unit")
    amount = int(match.group("amount").replace(",", ""))
    multiplier = {
        None: 1,
        "cp": 1,
        "sp": 10,
        "gp": 100,
        "pp": 1000,
    }[unit]
    if unit is None and amount != 0:
        raise ItemCatalogBuildError(
            f"equipment Price lacks a denomination: {value}"
        )
    return {
        "amountCp": amount * multiplier,
        "currency": "cp",
        "sourceText": text,
    }


def _price_projection(
    item: dict[str, Any],
    binding: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    raw_price = (
        item.get("pricePerBundle")
        if item.get("kind") == "ammunition"
        else item.get("price")
    )
    if raw_price is None:
        return None, ["normalized-price-unavailable"]
    try:
        result = _money(raw_price)
    except ItemCatalogBuildError:
        return None, ["normalized-price-unavailable"]

    modifiers = list(binding.get("modifiers") or [])
    non_shoddy = [
        modifier
        for modifier in modifiers
        if modifier.get("kind") != "quality-shoddy"
    ]
    if non_shoddy:
        if any(
            modifier.get("kind") not in {"potency", "striking"}
            or not isinstance(modifier.get("price"), dict)
            or type(modifier["price"].get("amountCp")) is not int
            or modifier["price"]["amountCp"] < 0
            for modifier in non_shoddy
        ):
            return None, ["configuration-price-uncompiled"]
        result = {
            **result,
            "amountCp": result["amountCp"]
            + sum(
                int(modifier["price"]["amountCp"])
                for modifier in non_shoddy
            ),
            "adjustments": [
                {
                    "kind": str(modifier["kind"]),
                    "amountCp": int(
                        modifier["price"]["amountCp"]
                    ),
                    "sourceText": str(
                        modifier["price"]["sourceText"]
                    ),
                    "source": deepcopy(modifier["source"]),
                }
                for modifier in non_shoddy
            ],
            "compositionRule": {
                "sourceId": "core-gmc",
                "locator": "224.2",
            },
        }
    if modifiers and not non_shoddy:
        if (
            len(modifiers) != 1
            or modifiers[0].get("kind") != "quality-shoddy"
            or result["amountCp"] % 2
        ):
            return None, ["quality-price-uncompiled"]
        result = {
            **result,
            "amountCp": result["amountCp"] // 2,
            "adjustments": [
                {
                    "kind": "quality-shoddy",
                    "factor": {"numerator": 1, "denominator": 2},
                    "source": deepcopy(modifiers[0]["source"]),
                }
            ],
        }
    if item.get("kind") == "ammunition":
        result["unitQuantity"] = int(item["bundleQuantity"])
    else:
        result["unitQuantity"] = 1
    return result, []


def _configuration(binding: dict[str, Any]) -> dict[str, Any]:
    qualities = {
        str(modifier.get("value") or "")
        for modifier in binding.get("modifiers") or []
        if modifier.get("kind") == "quality-shoddy"
    }
    if len(qualities) > 1 or "" in qualities:
        raise ItemCatalogBuildError(
            "equipment quality configuration is invalid"
        )
    quality = (
        next(iter(qualities))
        if qualities
        else binding.get("quality")
    )
    return {
        "itemId": binding["itemId"],
        "quality": quality,
        "modifiers": deepcopy(binding.get("modifiers") or []),
    }


def _definition_id(binding: dict[str, Any]) -> str:
    configuration = _configuration(binding)
    if not configuration["quality"] and not configuration["modifiers"]:
        return str(binding["itemId"])
    digest = item_catalog.json_digest(configuration)
    return f"{binding['itemId']}@{digest[:16]}"


def _definition_payload(
    item: dict[str, Any],
    binding: dict[str, Any],
) -> dict[str, Any]:
    configured_item = deepcopy(item)
    if isinstance(configured_item.get("durability"), dict):
        configuration = _configuration(binding)
        configured_item["durability"] = (
            durability_rules.durability_profile(
                configured_item,
                quality=configuration["quality"],
            )
        )
    modifier_levels = [
        int(modifier["level"])
        for modifier in binding.get("modifiers") or []
        if type(modifier.get("level")) is int
    ]
    if modifier_levels:
        configured_item["level"] = max(
            int(configured_item.get("level") or 0),
            *modifier_levels,
        )
    price, price_blockers = _price_projection(
        configured_item,
        binding,
    )
    durability = item.get("durability")
    if isinstance(durability, dict):
        durability_support = {
            "status": "ready",
            "blockers": [],
        }
    elif item.get("kind") == "ammunition":
        durability_support = {
            "status": "not-applicable",
            "blockers": [],
        }
    else:
        durability_support = {
            "status": "blocked",
            "blockers": ["durability-profile-uncompiled"],
        }
    presentation = item.get("presentation")
    if presentation is not None and (
        not isinstance(presentation, dict)
        or type(presentation.get("name")) is not str
        or not presentation["name"]
        or not isinstance(presentation.get("source"), dict)
        or type(presentation["source"].get("sourceId")) is not str
        or type(presentation["source"].get("locator")) is not str
    ):
        raise ItemCatalogBuildError(
            "compiled item presentation is invalid"
        )
    receipts = [
        deepcopy(binding["source"]),
        *(
            [
                {
                    **deepcopy(presentation["source"]),
                    "field": "presentation",
                    "name": presentation["name"],
                }
            ]
            if isinstance(presentation, dict)
            else []
        ),
        *[
            deepcopy(modifier["source"])
            for modifier in binding.get("modifiers") or []
        ],
    ]
    if binding.get("ammunitionSource") is not None:
        receipts.append(deepcopy(binding["ammunitionSource"]))
    if isinstance(durability, dict):
        durability_rule = durability.get("rule")
        if not isinstance(durability_rule, dict):
            raise ItemCatalogBuildError(
                "compiled durability profile lacks source provenance"
            )
        receipts.append(
            {
                "sourceId": str(
                    durability_rule.get("sourceId") or ""
                ),
                "locator": str(
                    durability_rule.get("locator") or ""
                ),
                "field": "durability",
                **(
                    {
                        "material": str(
                            durability["material"]
                        ),
                        "exampleBasis": str(
                            durability["exampleBasis"]
                        ),
                    }
                    if (
                        durability.get("material")
                        and durability.get("exampleBasis")
                    )
                    else {}
                ),
            }
        )
    result = {
        "schema": 1,
        "kind": "pf2er-item-definition",
        "rulesetId": item_catalog.RULESET_ID,
        "definitionId": _definition_id(binding),
        "itemId": str(binding["itemId"]),
        "itemKind": str(item["kind"]),
        "name": str(item["name"]),
        "configuration": _configuration(binding),
        "mechanics": configured_item,
        "sourceReceipts": receipts,
        "support": {
            "identity": {"status": "ready", "blockers": []},
            "price": {
                "status": "ready" if price is not None else "blocked",
                "blockers": price_blockers,
            },
            "durability": durability_support,
        },
    }
    if isinstance(presentation, dict):
        result["presentation"] = deepcopy(presentation)
        result["source"] = deepcopy(presentation["source"])
    if price is not None:
        result["price"] = price
    return result


def _validated_bindings() -> list[dict[str, Any]]:
    bindings = [
        equipment.thaw_binding(binding)
        for binding in runtime_equipment_bindings()
    ]
    if any(not isinstance(binding, dict) for binding in bindings):
        raise ItemCatalogBuildError(
            "runtime equipment binding projection is invalid"
        )
    normalized = [
        binding
        for binding in bindings
        if isinstance(binding, dict)
    ]
    if len(normalized) != 73:
        raise ItemCatalogBuildError(
            "runtime equipment binding registry count changed"
        )
    return normalized


def compile_catalog_values(
    source_cache: Path,
) -> dict[str, Any]:
    """Compile a complete in-memory catalog from one validated cache."""

    connection = backend.open_cache_connection(source_cache.resolve())
    try:
        backend.begin_validated_cache_snapshot(connection)
        (
            source_generation,
            source_authority_digest,
            source_snapshot_digest,
        ) = backend.cache_authority_identity(connection)
        bindings = _validated_bindings()
        canonical_bindings = [
            binding for binding in bindings if binding["canonical"]
        ]
        armor_packet = backend.source_node_packet(
            connection,
            "core-pc1",
            "271.1",
            "271.1",
        )
        weapons_packet = backend.source_node_packet(
            connection,
            "core-pc1",
            "275.1",
            "275.1",
        )
        shield_packet = backend.source_node_packet(
            connection,
            "core-pc1",
            "274.1",
            "274.1",
        )
        shield_root = equipment.packet_content(
            shield_packet,
            locator="274.1",
        )
        gear_root = equipment.packet_content(
            backend.source_node_packet(
                connection,
                "core-pc1",
                "287.5",
                "287.5",
            ),
            locator="287.5",
        )
        supplemental_references = {
            (
                str(source["sourceId"]),
                str(source["locator"]),
            )
            for binding in canonical_bindings
            for source in (
                (
                    [binding["source"]]
                    if binding["kind"] == "source-item"
                    else []
                )
                + [
                    modifier["source"]
                    for modifier in binding.get("modifiers") or []
                    if modifier.get("source") is not None
                ]
            )
        }
        supplemental_roots = {
            reference: _source_root(
                backend.source_node_packet(
                    connection,
                    reference[0],
                    reference[1],
                    reference[1],
                ),
                source_id=reference[0],
                locator=reference[1],
            )
            for reference in sorted(supplemental_references)
        }
        healing_potion_root = _source_root(
            backend.source_node_packet(
                connection,
                healing_potion.SOURCE["sourceId"],
                healing_potion.SOURCE["locator"],
                healing_potion.SOURCE["locator"],
            ),
            source_id=healing_potion.SOURCE["sourceId"],
            locator=healing_potion.SOURCE["locator"],
        )
        compiled = equipment.compile_equipment_catalog(
            [
                str(binding["sourceName"])
                for binding in canonical_bindings
            ],
            armor_packet=armor_packet,
            shield_packet=shield_packet,
            weapons_packet=weapons_packet,
        )
    finally:
        backend.close_cache_connection(connection)

    definitions_by_id: dict[str, dict[str, Any]] = {}
    definition_digests: dict[str, str] = {}
    aliases = []
    for binding in bindings:
        source_name = str(binding["sourceName"])
        if not binding["canonical"]:
            deferral = binding["deferral"]
            aliases.append(
                {
                    "sourceName": source_name,
                    "status": "deferred",
                    "blocker": {
                        "kind": str(deferral["kind"]),
                        "message": str(deferral["message"]),
                    },
                }
            )
            continue

        resolved_binding = deepcopy(binding)
        resolved_binding["modifiers"] = [
            _compile_modifier(
                modifier,
                supplemental_roots,
            )
            for modifier in binding.get("modifiers") or []
        ]
        item_id = str(resolved_binding["itemId"])
        base_item = compiled.get("items", {}).get(item_id)
        if not isinstance(base_item, dict):
            raise ItemCatalogBuildError(
                f"compiled catalog item is missing: {item_id}"
            )
        item = deepcopy(base_item)
        if resolved_binding["kind"] == "shield":
            item = _compile_shield(
                shield_root,
                resolved_binding,
                item,
            )
        elif resolved_binding["kind"] == "gear":
            item = _compile_gear(
                gear_root,
                resolved_binding,
                item,
            )
        elif resolved_binding["kind"] == "source-item":
            reference = (
                str(resolved_binding["source"]["sourceId"]),
                str(resolved_binding["source"]["locator"]),
            )
            root = supplemental_roots.get(reference)
            if root is None:
                raise ItemCatalogBuildError(
                    "source item root is unavailable: "
                    f"{reference[0]}:{reference[1]}"
                )
            item = _compile_source_item(
                root,
                resolved_binding,
                item,
            )
        definition = _definition_payload(item, resolved_binding)
        definition_id = str(definition["definitionId"])
        definition_digest = item_catalog.json_digest(definition)
        prior = definitions_by_id.get(definition_id)
        if prior is not None and prior != definition:
            raise ItemCatalogBuildError(
                "item definition id has conflicting configurations: "
                f"{definition_id}"
            )
        definitions_by_id[definition_id] = definition
        definition_digests[definition_id] = definition_digest
        aliases.append(
            {
                "sourceName": source_name,
                "status": "canonical",
                "definitionDigest": definition_digest,
            }
        )

    potion_definitions = _compile_healing_potion_definitions(
        healing_potion_root
    )
    for definition in potion_definitions:
        definition_id = str(definition["definitionId"])
        definition_digest = item_catalog.json_digest(definition)
        if definition_id in definitions_by_id:
            raise ItemCatalogBuildError(
                "Healing Potion definition identity conflicts"
            )
        definitions_by_id[definition_id] = definition
        definition_digests[definition_id] = definition_digest
        aliases.append(
            {
                "sourceName": str(definition["name"]),
                "status": "canonical",
                "definitionDigest": definition_digest,
            }
        )

    definitions = [
        definitions_by_id[key]
        for key in sorted(definitions_by_id)
    ]
    price_statuses = Counter(
        definition["support"]["price"]["status"]
        for definition in definitions
    )
    durability_statuses = Counter(
        definition["support"]["durability"]["status"]
        for definition in definitions
    )
    return {
        "compiler": deepcopy(COMPILER),
        "source_generation": source_generation,
        "source_authority_digest": source_authority_digest,
        "source_snapshot_digest": source_snapshot_digest,
        "definitions": definitions,
        "aliases": aliases,
        "census": {
            "definitions": len(definitions),
            "aliases": len(aliases),
            "canonicalAliases": sum(
                alias["status"] == "canonical"
                for alias in aliases
            ),
            "deferredAliases": sum(
                alias["status"] == "deferred"
                for alias in aliases
            ),
            "priceSupport": dict(sorted(price_statuses.items())),
            "durabilitySupport": dict(
                sorted(durability_statuses.items())
            ),
            "healingPotionVariants": len(potion_definitions),
        },
    }


def configured_path(
    environment_name: str,
    default: Path,
) -> Path:
    configured = str(os.environ.get(environment_name) or "").strip()
    if not configured:
        return default
    path = Path(configured)
    return path if path.is_absolute() else TTRPG_ROOT / path


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the deterministic PF2ER persistent-item catalog "
            "from the validated local source cache."
        )
    )
    parser.add_argument(
        "--source-cache",
        type=Path,
        default=configured_path(
            "KMQDB_TTRPG_CACHE_DB",
            DEFAULT_SOURCE_CACHE,
        ),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=configured_path(
            "KMQDB_TTRPG_ITEM_CATALOG_DB",
            DEFAULT_ITEM_CATALOG,
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compile and report without replacing the catalog.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    values = compile_catalog_values(args.source_cache)
    if args.check:
        result = {
            "schema": 1,
            "kind": "pf2er-item-catalog-check",
            "sourceGeneration": values["source_generation"],
            "census": values["census"],
        }
    else:
        manifest = item_catalog.replace_item_catalog(
            args.catalog,
            compiler=values["compiler"],
            source_generation=values["source_generation"],
            source_authority_digest=values[
                "source_authority_digest"
            ],
            source_snapshot_digest=values[
                "source_snapshot_digest"
            ],
            definitions=values["definitions"],
            aliases=values["aliases"],
        )
        result = {
            "schema": 1,
            "kind": "pf2er-item-catalog-built",
            "path": str(args.catalog.resolve()),
            "manifest": manifest,
            "census": values["census"],
        }
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

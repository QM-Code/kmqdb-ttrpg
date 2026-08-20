"""Source-free PF2ER item semantics for the first Player Core closure.

This module publishes the reviewed Player Core item closure used by the first
semantic packages: Club, Javelin, and the ordinary and virtuoso handheld
musical-instrument profiles.  Source-shaped compiler definitions and authority
receipts remain in ``SemanticEvidenceStore``; the public schema-2 package
contains only portable item mechanics.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hmac
import json
import re
from types import MappingProxyType
from typing import Any

from .pf2er_compiler import equipment
from .pf2er_compiler.mechanics.source_authority import (
    SourceAuthorityAdapter,
    VerifiedSourceSelection,
    canonical_raw_bytes,
)
from .semantic_evidence import (
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
    canonical_digest,
)
from .semantic_packages import (
    SemanticPackage,
    build_semantic_entity,
    build_semantic_package,
    validate_public_semantic_definition,
)


PF2ER_RULESET_ID = "paizo:pf2er"
PF2ER_PLAYER_CORE_ONE_BOOK_ID = "paizo:player-core-one"
PF2ER_PLAYER_CORE_ONE_PACKAGE_ID = "ttrpg:pf2er-player-core-one"
PF2ER_PLAYER_CORE_ONE_PACKAGE_VERSION = "1.0.0"
PF2ER_ITEM_COMPILER_ID = "ttrpg:pf2er-item-semantic-compiler"
PF2ER_ITEM_COMPILER_VERSION = "1.0.0"
PF2ER_ITEM_PROJECTION_ID = "ttrpg:pf2er-item-definition"
PF2ER_ITEM_PROJECTION_VERSION = "2.0.0"
PF2ER_ITEM_EVIDENCE_AUTHORITY_ID = "ttrpg:pf2er-semantic-evidence"

PF2ER_CLUB_ENTITY_ID = "pf2er:item.club"
PF2ER_JAVELIN_ENTITY_ID = "pf2er:item.javelin"
PF2ER_HANDHELD_INSTRUMENT_ENTITY_ID = (
    "pf2er:item.musical-instrument-handheld"
)
PF2ER_VIRTUOSO_HANDHELD_INSTRUMENT_ENTITY_ID = (
    "pf2er:item.musical-instrument-handheld-virtuoso"
)
PF2ER_XULGATH_ITEM_ENTITY_IDS = (
    PF2ER_CLUB_ENTITY_ID,
    PF2ER_JAVELIN_ENTITY_ID,
)
PF2ER_PLAYER_CORE_ITEM_ENTITY_IDS = (
    *PF2ER_XULGATH_ITEM_ENTITY_IDS,
    PF2ER_HANDHELD_INSTRUMENT_ENTITY_ID,
    PF2ER_VIRTUOSO_HANDHELD_INSTRUMENT_ENTITY_ID,
)

_PLAYER_CORE_SOURCE_ID = "core-pc1"
_ARMOR_ROOT_LOCATOR = "271.1"
_ARMOR_DESCRIPTIONS_LOCATOR = "272.4"
_WEAPON_ROOT_LOCATOR = "275.1"
_WEAPON_DESCRIPTIONS_LOCATOR = "284.1"
_ADVENTURING_GEAR_LOCATOR = "287.5"
_MUSICAL_INSTRUMENT_LOCATOR = "290.1"
_REVIEWED_SOURCE_ROOTS = [
    {"sourceId": _PLAYER_CORE_SOURCE_ID, "locator": _ARMOR_ROOT_LOCATOR},
    {
        "sourceId": _PLAYER_CORE_SOURCE_ID,
        "locator": _ARMOR_DESCRIPTIONS_LOCATOR,
    },
    {"sourceId": _PLAYER_CORE_SOURCE_ID, "locator": _WEAPON_ROOT_LOCATOR},
    {
        "sourceId": _PLAYER_CORE_SOURCE_ID,
        "locator": _WEAPON_DESCRIPTIONS_LOCATOR,
    },
]

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class PF2ERItemSemanticError(ValueError):
    """The selected Player Core item closure is invalid or has drifted."""


@dataclass(frozen=True, slots=True)
class PF2ERItemSourceTarget:
    """One reviewed private source target for a public semantic item."""

    source_id: str
    locator: str
    label: str
    content_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ReviewedItem:
    entity_id: str
    source_name: str
    source_item_id: str
    raw_definition_digest: str
    compiler_family: str = "weapon"


_REVIEWED_ITEMS = (
    _ReviewedItem(
        entity_id=PF2ER_CLUB_ENTITY_ID,
        source_name="club",
        source_item_id="core-pc1:item:club",
        raw_definition_digest=(
            "e3700dede65d7d49938fa5a8268efeec2b38e35871f9a355b069150d32d79529"
        ),
    ),
    _ReviewedItem(
        entity_id=PF2ER_JAVELIN_ENTITY_ID,
        source_name="javelin",
        source_item_id="core-pc1:item:javelin",
        raw_definition_digest=(
            "e23fb8eb4737f3b6ba2557de2a5ed49a203d207a99a46426bc86e013809061a9"
        ),
    ),
    _ReviewedItem(
        entity_id=PF2ER_HANDHELD_INSTRUMENT_ENTITY_ID,
        source_name="Handheld",
        source_item_id="core-pc1:item:musical-instrument-handheld",
        raw_definition_digest=(
            "65476a2d4308734f2d1ff645d8010209fcaf3de36473a730cb6b151f75fac50f"
        ),
        compiler_family="musical-instrument",
    ),
    _ReviewedItem(
        entity_id=PF2ER_VIRTUOSO_HANDHELD_INSTRUMENT_ENTITY_ID,
        source_name="Virtuoso handheld (level 3)",
        source_item_id=(
            "core-pc1:item:musical-instrument-handheld-virtuoso"
        ),
        raw_definition_digest=(
            "d9f1d93799f6212f7d9712b0557a0db5705017ba1dd4bd3b2f6ec6df2ac9ad98"
        ),
        compiler_family="musical-instrument",
    ),
)

PF2ER_ITEM_SOURCE_TARGETS = MappingProxyType(
    {
        PF2ER_CLUB_ENTITY_ID: PF2ERItemSourceTarget(
            source_id=_PLAYER_CORE_SOURCE_ID,
            locator="284.13",
            label="Club",
            content_path=("Weapon Descriptions", "Club"),
        ),
        PF2ER_JAVELIN_ENTITY_ID: PF2ERItemSourceTarget(
            source_id=_PLAYER_CORE_SOURCE_ID,
            locator="285.11",
            label="Javelin",
            content_path=("Weapon Descriptions", "Javelin"),
        ),
    }
)

_PROJECTION_MANIFEST = {
    "schema": 1,
    "packageId": PF2ER_PLAYER_CORE_ONE_PACKAGE_ID,
    "packageVersion": PF2ER_PLAYER_CORE_ONE_PACKAGE_VERSION,
    "projectionId": PF2ER_ITEM_PROJECTION_ID,
    "projectionVersion": PF2ER_ITEM_PROJECTION_VERSION,
    "definitionSchema": 1,
    "entityKind": "ttrpg:item",
    "selectedEntityIds": list(PF2ER_PLAYER_CORE_ITEM_ENTITY_IDS),
}
PF2ER_ITEM_PROJECTION_DIGEST = canonical_digest(
    _PROJECTION_MANIFEST,
    "PF2ER item projection manifest",
)

_COMPILER_MANIFEST = {
    "schema": 1,
    "compilerId": PF2ER_ITEM_COMPILER_ID,
    "compilerVersion": PF2ER_ITEM_COMPILER_VERSION,
    "rulesetId": PF2ER_RULESET_ID,
    "bookId": PF2ER_PLAYER_CORE_ONE_BOOK_ID,
    "compilerSeam": "rules_engine.equipment.compile_equipment_catalog",
    "items": [
        {
            "entityId": item.entity_id,
            "sourceName": item.source_name,
            "sourceItemId": item.source_item_id,
            "reviewedRawDefinitionDigest": item.raw_definition_digest,
        }
        for item in _REVIEWED_ITEMS
    ],
}
PF2ER_ITEM_COMPILER_DIGEST = canonical_digest(
    _COMPILER_MANIFEST,
    "PF2ER item compiler manifest",
)


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise PF2ERItemSemanticError(
            f"{label} must be a lowercase sha256 digest"
        )
    return value


def _selected_items(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or any(type(item) is not str for item in value):
        raise PF2ERItemSemanticError(
            "selected item entity IDs must be an explicit tuple"
        )
    if len(set(value)) != len(value):
        raise PF2ERItemSemanticError(
            "selected item entity IDs contain duplicates"
        )
    expected = frozenset(PF2ER_PLAYER_CORE_ITEM_ENTITY_IDS)
    selected = frozenset(value)
    excess = sorted(selected - expected)
    missing = sorted(expected - selected)
    if excess or missing:
        raise PF2ERItemSemanticError(
            "selected items differ from the reviewed Player Core closure; "
            f"missing={missing}, excess={excess}"
        )
    return tuple(sorted(value))


def _one_target(
    targets: tuple[Any, ...],
    *,
    locator: str,
    label: str,
    content_path: tuple[str, ...],
) -> Any:
    matches = tuple(
        target
        for target in targets
        if target.source_id == _PLAYER_CORE_SOURCE_ID
        and target.locator == locator
        and target.label == label
        and target.content_path == content_path
    )
    if len(matches) != 1:
        raise PF2ERItemSemanticError(
            "Player Core item source target is missing or ambiguous: "
            f"{locator}"
        )
    return matches[0]


def _description_toc(
    targets: tuple[Any, ...],
    *,
    root_locator: str,
    root_label: str,
    description_locator: str,
    description_label: str,
) -> dict[str, object]:
    root = _one_target(
        targets,
        locator=root_locator,
        label=root_label,
        content_path=(),
    )
    description = _one_target(
        targets,
        locator=description_locator,
        label=description_label,
        content_path=(description_label,),
    )
    children = tuple(
        sorted(
            (
                target
                for target in targets
                if target.source_id == _PLAYER_CORE_SOURCE_ID
                and len(target.content_path) == 2
                and target.content_path[0] == description_label
                and target.label == target.content_path[1]
            ),
            key=lambda target: (target.label, target.locator),
        )
    )
    if not children:
        raise PF2ERItemSemanticError(
            f"Player Core {description_label} targets are missing"
        )
    if (
        len({item.label for item in children}) != len(children)
        or len({item.locator for item in children}) != len(children)
    ):
        raise PF2ERItemSemanticError(
            f"Player Core {description_label} targets are ambiguous"
        )
    return {
        "label": root.label,
        "locator": root.locator,
        "content_path": list(root.content_path),
        "children": [
            {
                "label": description.label,
                "locator": description.locator,
                "content_path": list(description.content_path),
                "children": [
                    {
                        "label": child.label,
                        "locator": child.locator,
                        "content_path": list(child.content_path),
                        "children": [],
                    }
                    for child in children
                ],
            }
        ],
    }


def _source_packet(
    authority: SourceAuthorityAdapter,
    *,
    targets: tuple[Any, ...],
    root_locator: str,
    root_label: str,
    description_locator: str,
    description_label: str,
) -> tuple[dict[str, object], VerifiedSourceSelection]:
    address = authority.address(
        source_id=_PLAYER_CORE_SOURCE_ID,
        locator=root_locator,
    )
    selection = authority.validate_selection(authority.resolve(address))
    content = canonical_raw_bytes(selection.selected_value).decode("utf-8")
    return (
        {
            "toc": _description_toc(
                targets,
                root_locator=root_locator,
                root_label=root_label,
                description_locator=description_locator,
                description_label=description_label,
            ),
            "target": {
                "selected": {
                    "source_id": _PLAYER_CORE_SOURCE_ID,
                    "locator": root_locator,
                    "section_id": address.section_id,
                    "content_path": [],
                }
            },
            "content": {
                "section": {
                    "id": address.section_id,
                    "source_id": _PLAYER_CORE_SOURCE_ID,
                    "content": content,
                }
            },
        },
        selection,
    )


def _item_source_selection(
    authority: SourceAuthorityAdapter,
    targets: tuple[Any, ...],
    reviewed: _ReviewedItem,
) -> VerifiedSourceSelection:
    target = PF2ER_ITEM_SOURCE_TARGETS[reviewed.entity_id]
    _one_target(
        targets,
        locator=target.locator,
        label=target.label,
        content_path=target.content_path,
    )
    address = authority.address(
        source_id=target.source_id,
        locator=target.locator,
    )
    return authority.validate_selection(authority.resolve(address))


def _rule_ref(rule_id: str) -> dict[str, str]:
    return {"ruleRef": rule_id}


def _raw_json(selection: VerifiedSourceSelection) -> dict[str, Any]:
    value = json.loads(canonical_raw_bytes(selection.selected_value))
    if type(value) is not dict:
        raise PF2ERItemSemanticError(
            "Player Core item source selection is not an object"
        )
    return value


def _compile_instrument_profiles(
    authority: SourceAuthorityAdapter,
    targets: tuple[Any, ...],
) -> tuple[
    dict[str, dict[str, object]],
    dict[str, dict[str, object]],
]:
    _one_target(
        targets,
        locator=_ADVENTURING_GEAR_LOCATOR,
        label="Adventuring Gear",
        content_path=("Adventuring Gear",),
    )
    _one_target(
        targets,
        locator=_MUSICAL_INSTRUMENT_LOCATOR,
        label="Musical Instrument",
        content_path=("Adventuring Gear", "Musical Instrument"),
    )
    table_selection = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=_PLAYER_CORE_SOURCE_ID,
                locator=_ADVENTURING_GEAR_LOCATOR,
            )
        )
    )
    description_selection = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=_PLAYER_CORE_SOURCE_ID,
                locator=_MUSICAL_INSTRUMENT_LOCATOR,
            )
        )
    )
    table_source = _raw_json(table_selection)
    description_source = _raw_json(description_selection)
    table = table_source.get("~.table")
    if (
        type(table) is not dict
        or table.get("title") != "Adventuring Gear"
        or table.get("columns") != ["Item", "Price", "Bulk", "Hands"]
        or type(table.get("rows")) is not list
    ):
        raise PF2ERItemSemanticError(
            "Player Core Adventuring Gear table shape drifted"
        )
    header_index = next(
        (
            index
            for index, row in enumerate(table["rows"])
            if row == {
                "type": "header",
                "data": ["Musical instrument", "", "", ""],
            }
        ),
        -1,
    )
    expected_rows = [
        ["Handheld", "8 sp", "1", "2"],
        ["Virtuoso handheld (level 3)", "50 gp", "1", "2"],
        ["Heavy", "2 gp", "16", "2"],
        ["Virtuoso heavy (level 3)", "100 gp", "16", "2"],
    ]
    if (
        header_index < 0
        or table["rows"][header_index + 1 : header_index + 5]
        != expected_rows
    ):
        raise PF2ERItemSemanticError(
            "Player Core musical-instrument rows drifted"
        )
    expected_description = {
        "Name": "Musical Instrument",
        "Icon": "gear/x128/Musical Instrument",
        "Image": "gear/x1280x960/musical-instrument",
        "Description": (
            "Handheld instruments include bagpipes, a small set of chimes, "
            "small drums, fiddles and viols, flutes and recorders, small "
            "harps, lutes, trumpets, and similarly sized instruments. The GM "
            "might rule that an especially large handheld instrument (like a "
            "tuba) has greater Bulk. Heavy instruments such as large drums, "
            "a full set of chimes, and keyboard instruments are less portable "
            "and generally need to be stationary while being played. A "
            "virtuoso instrument is more finely made and gives a +1 item "
            "bonus to Performance checks using that instrument."
        ),
    }
    if description_source != expected_description:
        raise PF2ERItemSemanticError(
            "Player Core musical-instrument description drifted"
        )

    definitions: dict[str, dict[str, object]] = {}
    for entity_id, source_item_id, row, level, bonus in (
        (
            PF2ER_HANDHELD_INSTRUMENT_ENTITY_ID,
            "core-pc1:item:musical-instrument-handheld",
            expected_rows[0],
            0,
            None,
        ),
        (
            PF2ER_VIRTUOSO_HANDHELD_INSTRUMENT_ENTITY_ID,
            "core-pc1:item:musical-instrument-handheld-virtuoso",
            expected_rows[1],
            3,
            1,
        ),
    ):
        definition: dict[str, object] = {
            "id": source_item_id,
            "name": (
                "Handheld Musical Instrument"
                if level == 0
                else "Virtuoso Handheld Musical Instrument"
            ),
            "kind": "adventuring-gear",
            "level": level,
            "rarity": "common",
            "price": row[1],
            "bulk": int(row[2]),
            "hands": {"holding": 1, "requiredToUse": int(row[3])},
            "profile": "handheld-musical-instrument",
            "performanceItemBonus": bonus,
            "reviewedDeferrals": [
                "especially-large-handheld-bulk-gm-ruling",
                "perform-action-and-modality",
                "physical-damage-type-gm-adjudication",
            ],
        }
        definitions[entity_id] = definition
    receipts = {
        entity_id: {
            "tableSelection": table_selection.receipt.as_serialized(),
            "descriptionSelection": (
                description_selection.receipt.as_serialized()
            ),
        }
        for entity_id in definitions
    }
    return definitions, receipts


def _project_club(raw: dict[str, Any]) -> dict[str, object]:
    # Values are copied one by one only after the reviewed raw digest matches.
    trait = raw["traits"][0]
    return {
        "schema": 1,
        "id": PF2ER_CLUB_ENTITY_ID,
        "name": raw["name"],
        "kind": raw["kind"],
        "level": raw["level"],
        "rarity": raw["rarity"],
        "weaponCategory": raw["weaponCategory"],
        "mode": raw["mode"],
        "price": raw["price"],
        "damage": deepcopy(raw["damage"]),
        "bulk": raw["bulk"],
        "hands": deepcopy(raw["hands"]),
        "group": raw["group"],
        "traits": [
            {
                "name": trait["name"],
                "rangeIncrementFeet": trait["rangeIncrementFeet"],
                "ruleRef": "pf2er.rule:weapon-traits",
            }
        ],
        "references": {
            "rules": [
                "pf2er.rule:weapon-hands",
                "pf2er.rule:weapon-statistics",
                "pf2er.rule:weapon-traits",
            ]
        },
        "presentation": {"name": raw["presentation"]["name"]},
        "rules": {
            "statistics": _rule_ref("pf2er.rule:weapon-statistics"),
            "hands": _rule_ref("pf2er.rule:weapon-hands"),
            "traits": _rule_ref("pf2er.rule:weapon-traits"),
        },
    }


def _project_javelin(raw: dict[str, Any]) -> dict[str, object]:
    trait = raw["traits"][0]
    return {
        "schema": 1,
        "id": PF2ER_JAVELIN_ENTITY_ID,
        "name": raw["name"],
        "kind": raw["kind"],
        "level": raw["level"],
        "rarity": raw["rarity"],
        "weaponCategory": raw["weaponCategory"],
        "mode": raw["mode"],
        "price": raw["price"],
        "damage": deepcopy(raw["damage"]),
        "bulk": raw["bulk"],
        "hands": deepcopy(raw["hands"]),
        "group": raw["group"],
        "rangeIncrementFeet": raw["rangeIncrementFeet"],
        "maximumRangeIncrements": raw["maximumRangeIncrements"],
        "reloadActions": raw["reloadActions"],
        "requiresDrawAfterUse": raw["requiresDrawAfterUse"],
        "traits": [
            {
                "name": trait["name"],
                "ruleRef": "pf2er.rule:weapon-traits",
            }
        ],
        "references": {
            "rules": [
                "pf2er.rule:weapon-hands",
                "pf2er.rule:weapon-range",
                "pf2er.rule:weapon-reload",
                "pf2er.rule:weapon-statistics",
                "pf2er.rule:weapon-traits",
            ]
        },
        "presentation": {"name": raw["presentation"]["name"]},
        "rules": {
            "statistics": _rule_ref("pf2er.rule:weapon-statistics"),
            "hands": _rule_ref("pf2er.rule:weapon-hands"),
            "traits": _rule_ref("pf2er.rule:weapon-traits"),
            "range": _rule_ref("pf2er.rule:weapon-range"),
            "reload": _rule_ref("pf2er.rule:weapon-reload"),
        },
    }


def _project_instrument(
    reviewed: _ReviewedItem,
    raw: dict[str, Any],
) -> dict[str, object]:
    projected: dict[str, object] = {
        "schema": 1,
        "id": reviewed.entity_id,
        "name": raw["name"],
        "kind": raw["kind"],
        "level": raw["level"],
        "rarity": raw["rarity"],
        "price": raw["price"],
        "bulk": raw["bulk"],
        "hands": deepcopy(raw["hands"]),
        "profile": raw["profile"],
        "performance": {
            "itemBonus": raw["performanceItemBonus"],
            "appliesWhileUsingInstrument": True,
            "runtimeStatus": "deferred",
            "ruleRef": "pf2er.rule:performance",
        },
        "telekineticProjectile": {
            "maximumBulkEligible": True,
            "damageType": None,
            "requiresAdjudicatedPhysicalDamageType": True,
            "ruleRef": "pf2er.rule:telekinetic-projectile",
        },
        "reviewedDeferrals": deepcopy(raw["reviewedDeferrals"]),
        "references": {
            "rules": [
                "pf2er.rule:item-bulk",
                "pf2er.rule:item-hands",
                "pf2er.rule:musical-instrument",
                "pf2er.rule:performance",
                "pf2er.rule:telekinetic-projectile",
            ]
        },
        "rules": {
            "bulk": _rule_ref("pf2er.rule:item-bulk"),
            "hands": _rule_ref("pf2er.rule:item-hands"),
            "instrument": _rule_ref("pf2er.rule:musical-instrument"),
        },
    }
    return projected


def _project_item(reviewed: _ReviewedItem, raw: dict[str, Any]) -> dict[str, object]:
    if type(raw) is not dict:
        raise PF2ERItemSemanticError(
            f"item compiler returned a non-object: {reviewed.entity_id}"
        )
    actual_digest = canonical_digest(raw, "raw PF2ER item definition")
    if not hmac.compare_digest(actual_digest, reviewed.raw_definition_digest):
        raise PF2ERItemSemanticError(
            f"reviewed item compiler output drifted: {reviewed.entity_id}"
        )
    if raw.get("id") != reviewed.source_item_id:
        raise PF2ERItemSemanticError(
            f"reviewed item compiler identity drifted: {reviewed.entity_id}"
        )
    if reviewed.entity_id == PF2ER_CLUB_ENTITY_ID:
        projected = _project_club(raw)
    elif reviewed.entity_id == PF2ER_JAVELIN_ENTITY_ID:
        projected = _project_javelin(raw)
    else:
        projected = _project_instrument(reviewed, raw)
    validate_public_semantic_definition(projected)
    return projected


def build_player_core_item_semantic_package(
    *,
    authority: SourceAuthorityAdapter,
    expected_authority_digest: str,
    ruleset_digest: str,
    book_digest: str,
    semantic_generation: str,
    evidence_store: SemanticEvidenceStore,
    selected_entity_ids: tuple[str, ...] = PF2ER_PLAYER_CORE_ITEM_ENTITY_IDS,
) -> SemanticPackage:
    """Compile and seal the reviewed Club/Javelin Player Core package.

    No catalog or SQLite path is accepted.  The caller supplies one retained
    source-authority adapter and the exact authority digest approved for the
    publication operation.
    """

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("PF2ER item semantics require SourceAuthorityAdapter")
    if type(evidence_store) is not SemanticEvidenceStore:
        raise TypeError("PF2ER item semantics require SemanticEvidenceStore")
    _selected_items(selected_entity_ids)
    expected_authority_digest = _digest(
        expected_authority_digest,
        "expectedAuthorityDigest",
    )
    if not hmac.compare_digest(authority.snapshot.digest, expected_authority_digest):
        raise PF2ERItemSemanticError("Player Core source authority drifted")
    if _PLAYER_CORE_SOURCE_ID not in authority.allowed_source_ids:
        raise PF2ERItemSemanticError("Player Core source is not selected")

    toc_targets = authority.iter_toc_targets()
    weapon_items = tuple(
        item for item in _REVIEWED_ITEMS if item.compiler_family == "weapon"
    )
    item_selections = {
        reviewed.entity_id: _item_source_selection(
            authority,
            toc_targets,
            reviewed,
        )
        for reviewed in weapon_items
    }
    instrument_definitions, instrument_receipts = _compile_instrument_profiles(
        authority,
        toc_targets,
    )
    armor_packet, armor_selection = _source_packet(
        authority,
        targets=toc_targets,
        root_locator=_ARMOR_ROOT_LOCATOR,
        root_label="Armor",
        description_locator=_ARMOR_DESCRIPTIONS_LOCATOR,
        description_label="Armor Descriptions",
    )
    weapons_packet, weapons_selection = _source_packet(
        authority,
        targets=toc_targets,
        root_locator=_WEAPON_ROOT_LOCATOR,
        root_label="Weapons",
        description_locator=_WEAPON_DESCRIPTIONS_LOCATOR,
        description_label="Weapon Descriptions",
    )
    catalog = equipment.compile_equipment_catalog(
        (item.source_name for item in weapon_items),
        armor_packet=armor_packet,
        weapons_packet=weapons_packet,
    )
    if (
        type(catalog) is not dict
        or set(catalog) != {"schema", "sourceRoots", "items"}
        or catalog.get("schema") != 1
        or catalog.get("sourceRoots") != _REVIEWED_SOURCE_ROOTS
        or type(catalog.get("items")) is not dict
        or set(catalog["items"])
        != {item.source_item_id for item in weapon_items}
    ):
        raise PF2ERItemSemanticError(
            "item compiler returned an unexpected selected catalog"
        )
    catalog_digest = canonical_digest(catalog, "raw PF2ER item catalog")

    entities = []
    records = []
    source_receipts = {
        "armor": armor_selection.receipt.as_serialized(),
        "weapons": weapons_selection.receipt.as_serialized(),
    }
    for reviewed in _REVIEWED_ITEMS:
        raw_definition = (
            catalog["items"][reviewed.source_item_id]
            if reviewed.compiler_family == "weapon"
            else instrument_definitions[reviewed.entity_id]
        )
        definition = _project_item(reviewed, raw_definition)
        raw_definition_digest = canonical_digest(
            raw_definition,
            "raw PF2ER item definition",
        )
        projected_definition_digest = canonical_digest(
            definition,
            "projected PF2ER item definition",
        )
        record = SemanticEvidenceRecord.build(
            evidence_authority_id=PF2ER_ITEM_EVIDENCE_AUTHORITY_ID,
            entity_id=reviewed.entity_id,
            compiler_digest=PF2ER_ITEM_COMPILER_DIGEST,
            raw_definition_digest=raw_definition_digest,
            projected_definition_digest=projected_definition_digest,
            projection_id=PF2ER_ITEM_PROJECTION_ID,
            projection_version=PF2ER_ITEM_PROJECTION_VERSION,
            projection_digest=PF2ER_ITEM_PROJECTION_DIGEST,
            acquisition_receipt={
                "schema": 1,
                "kind": "pf2er-item-acquisition",
                "authorityDigest": authority.snapshot.digest,
                "selectedSourceItemId": reviewed.source_item_id,
                "sourceSelections": (
                    deepcopy(source_receipts)
                    if reviewed.compiler_family == "weapon"
                    else deepcopy(instrument_receipts[reviewed.entity_id])
                ),
                **(
                    {
                        "itemSelection": item_selections[
                            reviewed.entity_id
                        ].receipt.as_serialized()
                    }
                    if reviewed.compiler_family == "weapon"
                    else {}
                ),
            },
            compiler_receipt={
                "schema": 1,
                "manifest": deepcopy(_COMPILER_MANIFEST),
                "digest": PF2ER_ITEM_COMPILER_DIGEST,
                "catalogDigest": catalog_digest,
                "rawDefinition": deepcopy(raw_definition),
                "projection": deepcopy(_PROJECTION_MANIFEST),
            },
        )
        records.append(record)
        entities.append(
            build_semantic_entity(
                entity_id=reviewed.entity_id,
                entity_kind="ttrpg:item",
                definition=definition,
                evidence_authority_id=PF2ER_ITEM_EVIDENCE_AUTHORITY_ID,
                evidence_record_digest=record.evidence_record_digest,
                compiler_digest=PF2ER_ITEM_COMPILER_DIGEST,
                raw_definition_digest=raw_definition_digest,
                projection_id=PF2ER_ITEM_PROJECTION_ID,
                projection_version=PF2ER_ITEM_PROJECTION_VERSION,
                projection_digest=PF2ER_ITEM_PROJECTION_DIGEST,
            )
        )

    package = build_semantic_package(
        package_id=PF2ER_PLAYER_CORE_ONE_PACKAGE_ID,
        version=PF2ER_PLAYER_CORE_ONE_PACKAGE_VERSION,
        ruleset_id=PF2ER_RULESET_ID,
        ruleset_digest=ruleset_digest,
        book_id=PF2ER_PLAYER_CORE_ONE_BOOK_ID,
        book_digest=book_digest,
        semantic_generation=semantic_generation,
        semantic_generation_digest=canonical_digest(
            {
                "schema": 1,
                "semanticGeneration": semantic_generation,
                "packageId": PF2ER_PLAYER_CORE_ONE_PACKAGE_ID,
                "packageVersion": PF2ER_PLAYER_CORE_ONE_PACKAGE_VERSION,
                "compilerDigest": PF2ER_ITEM_COMPILER_DIGEST,
                "projectionDigest": PF2ER_ITEM_PROJECTION_DIGEST,
                "entities": [
                    {
                        "entityId": entity.entity_id,
                        "definitionDigest": entity.definition_digest,
                        "evidenceRecordDigest": (
                            entity.receipt.evidence_record_digest
                        ),
                    }
                    for entity in entities
                ],
            },
            "PF2ER item semantic generation",
        ),
        compiler_id=PF2ER_ITEM_COMPILER_ID,
        compiler_version=PF2ER_ITEM_COMPILER_VERSION,
        compiler_digest=PF2ER_ITEM_COMPILER_DIGEST,
        entities=tuple(entities),
    )
    evidence_store.provision_many(tuple(records))
    return package


__all__ = [
    "PF2ERItemSemanticError",
    "PF2ER_CLUB_ENTITY_ID",
    "PF2ER_HANDHELD_INSTRUMENT_ENTITY_ID",
    "PF2ER_ITEM_COMPILER_DIGEST",
    "PF2ER_ITEM_EVIDENCE_AUTHORITY_ID",
    "PF2ER_ITEM_PROJECTION_DIGEST",
    "PF2ER_ITEM_SOURCE_TARGETS",
    "PF2ER_JAVELIN_ENTITY_ID",
    "PF2ER_PLAYER_CORE_ITEM_ENTITY_IDS",
    "PF2ERItemSourceTarget",
    "PF2ER_PLAYER_CORE_ONE_BOOK_ID",
    "PF2ER_PLAYER_CORE_ONE_PACKAGE_ID",
    "PF2ER_PLAYER_CORE_ONE_PACKAGE_VERSION",
    "PF2ER_XULGATH_ITEM_ENTITY_IDS",
    "PF2ER_VIRTUOSO_HANDHELD_INSTRUMENT_ENTITY_ID",
    "build_player_core_item_semantic_package",
]

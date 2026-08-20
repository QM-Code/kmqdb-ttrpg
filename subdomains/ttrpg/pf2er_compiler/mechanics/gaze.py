"""Compile source-authored petrifying gaze abilities."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RuleReference,
)
from .source_values import parse_decimal_integer


TURN_START_RANGE_RE = re.compile(
    r"\bA creature within (?P<range>\d+) feet that the "
    r"[A-Za-z][A-Za-z -]* can see starts its turn\b",
    re.IGNORECASE,
)
FORTITUDE_SAVE_RE = re.compile(
    r"\bDC (?P<dc>\d+) Fortitude save\b",
    re.IGNORECASE,
)
SLOWED_DURATION_RE = re.compile(
    r"\bit[’']s slowed (?P<value>\d+) for "
    r"(?P<duration>\d+) minute(?:s)?\b",
    re.IGNORECASE,
)
GAZE_RANGE_RE = re.compile(
    r"\bwithin (?P<range>\d+) feet\b",
    re.IGNORECASE,
)
GAZE_SLOWED_RE = re.compile(
    r"\bit becomes slowed (?P<value>\d+)\b",
    re.IGNORECASE,
)
BASILISK_BLOOD_RE = re.compile(
    r"\bfresh basilisk blood no more than "
    r"(?P<hours>\d+) hour(?:s)? old\b",
    re.IGNORECASE,
)
BASILISK_BLOOD_CAPACITY_RE = re.compile(
    r"\benough blood to coat (?P<count>\d+)d(?P<sides>\d+) "
    r"(?P<size>[A-Za-z]+) creatures\b",
    re.IGNORECASE,
)
MEDUSA_PETRIFYING_GAZE_RE = re.compile(
    r"^(?P<range>\d+) feet\. When a creature ends its turn in the aura, "
    r"it must attempt a DC (?P<dc>\d+) Fortitude save\. If the creature "
    r"fails, it becomes slowed (?P<value>\d+) for (?P<duration>\d+) "
    r"minute(?:s)?\. The medusa can deactivate or activate this aura by "
    r"using a single action, which has the concentrate trait\.$",
    re.IGNORECASE,
)
MEDUSA_FOCUS_GAZE_RE = re.compile(
    r"^The medusa fixes their glare at a creature they can see within "
    r"(?P<range>\d+) feet\. The target must immediately attempt a Fortitude "
    r"save against the medusa[’']s petrifying gaze\. If the creature was "
    r"already slowed by petrifying gaze before attempting its save, a failed "
    r"save causes it to be petrified permanently\. After attempting its save, "
    r"the creature is then temporarily immune until the start of the "
    r"medusa[’']s next turn\.$",
    re.IGNORECASE,
)


def compile_petrifying_glance(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the complete turn-start petrifying reaction grammar."""

    trigger_match = TURN_START_RANGE_RE.fullmatch(source.trigger)
    save_match = FORTITUDE_SAVE_RE.search(source.description)
    slowed_match = SLOWED_DURATION_RE.search(source.description)
    if trigger_match is None or save_match is None or slowed_match is None:
        return None
    range_feet = parse_decimal_integer(trigger_match.group("range"))
    save_dc = parse_decimal_integer(save_match.group("dc"))
    slowed_value = parse_decimal_integer(slowed_match.group("value"))
    duration_minutes = parse_decimal_integer(slowed_match.group("duration"))
    if (
        range_feet is None
        or save_dc is None
        or slowed_value is None
        or duration_minutes is None
    ):
        return None
    if (
        source.action_cost != "reaction"
        or source.kind != "reaction"
        or source.source_label.casefold() != "petrifying glance"
    ):
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": "turn-start-saving-throw-reaction",
            "rangeFeet": range_feet,
            "requiresVisibility": True,
            "requiresTargetToLook": True,
            "savingThrow": {
                "type": "fortitude",
                "dc": save_dc,
            },
            "failure": {
                "condition": "slowed",
                "value": slowed_value,
                "duration": {
                    "unit": "rounds",
                    "value": duration_minutes * 10,
                    "sourceUnit": "minutes",
                    "sourceValue": duration_minutes,
                },
                "sourceFamily": "basilisk-petrification",
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_petrifying_gaze(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the complete progressive petrification activity grammar."""

    save_match = FORTITUDE_SAVE_RE.search(source.description)
    range_match = GAZE_RANGE_RE.search(source.description)
    slowed_match = GAZE_SLOWED_RE.search(source.description)
    blood_match = BASILISK_BLOOD_RE.search(source.description)
    capacity_match = BASILISK_BLOOD_CAPACITY_RE.search(source.description)
    normalized = " ".join(source.description.split()).casefold()
    progression_is_explicit = (
        "has not already been slowed by petrifying glance or this ability"
        in normalized
        and "already slowed by this ability or petrifying glance" in normalized
        and "petrified permanently" in normalized
        and "instantly restored to flesh" in normalized
    )
    if (
        save_match is None
        or range_match is None
        or slowed_match is None
        or blood_match is None
        or capacity_match is None
        or not progression_is_explicit
    ):
        return None
    range_feet = parse_decimal_integer(range_match.group("range"))
    save_dc = parse_decimal_integer(save_match.group("dc"))
    slowed_value = parse_decimal_integer(slowed_match.group("value"))
    blood_hours = parse_decimal_integer(blood_match.group("hours"))
    capacity_count = parse_decimal_integer(capacity_match.group("count"))
    capacity_sides = parse_decimal_integer(capacity_match.group("sides"))
    if (
        range_feet is None
        or save_dc is None
        or slowed_value is None
        or blood_hours is None
        or capacity_count is None
        or capacity_sides is None
    ):
        return None
    if (
        source.action_cost != 2
        or source.kind != "activity"
        or source.source_label.casefold() != "petrifying gaze"
    ):
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": "progressive-saving-throw-activity",
            "rangeFeet": range_feet,
            "requiresVisibility": True,
            "requiresTargetToLook": True,
            "savingThrow": {
                "type": "fortitude",
                "dc": save_dc,
            },
            "progression": {
                "sourceFamily": "basilisk-petrification",
                "initialFailure": {
                    "condition": "slowed",
                    "value": slowed_value,
                    "duration": "persistent",
                },
                "repeatFailure": {
                    "condition": "petrified",
                    "duration": "permanent",
                },
            },
            "restoration": {
                "type": "fresh-basilisk-blood-coating",
                "application": "coated-not-splashed",
                "maximumBloodAgeSeconds": blood_hours * 3600,
                "capacity": {
                    "dice": {
                        "count": capacity_count,
                        "sides": capacity_sides,
                    },
                    "creatureSize": capacity_match.group("size").casefold(),
                },
            },
        },
        rule=RuleReference(source.source_id, source.locator),
        deferred_mechanics=("fresh-basilisk-blood-restoration-action",),
    )


def compile_medusa_petrifying_gaze(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the medusa's complete turn-end aura grammar."""

    match = MEDUSA_PETRIFYING_GAZE_RE.fullmatch(
        " ".join(source.description.split())
    )
    if match is None:
        return None
    range_feet = parse_decimal_integer(match.group("range"))
    save_dc = parse_decimal_integer(match.group("dc"))
    slowed_value = parse_decimal_integer(match.group("value"))
    duration_minutes = parse_decimal_integer(match.group("duration"))
    if (
        range_feet is None
        or save_dc is None
        or slowed_value is None
        or duration_minutes is None
    ):
        return None
    if (
        source.creature_name.casefold() != "medusa"
        or source.source_label.casefold() != "petrifying gaze"
        or source.action_cost is not None
        or source.kind != "passive"
        or set(source.traits) != {"arcane", "aura", "visual"}
    ):
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": "turn-end-saving-throw-aura",
            "rangeFeet": range_feet,
            "requiresVisibility": True,
            "requiresTargetToLook": True,
            "savingThrow": {
                "type": "fortitude",
                "dc": save_dc,
            },
            "failure": {
                "condition": "slowed",
                "value": slowed_value,
                "duration": {
                    "unit": "rounds",
                    "value": duration_minutes * 10,
                    "sourceUnit": "minutes",
                    "sourceValue": duration_minutes,
                },
                "sourceFamily": "medusa-petrification",
            },
            "activation": {
                "default": "active",
                "toggleActionCost": 1,
                "traits": ["concentrate"],
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def compile_medusa_focus_gaze(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile Focus Gaze while retaining its explicit aura dependency."""

    match = MEDUSA_FOCUS_GAZE_RE.fullmatch(
        " ".join(source.description.split())
    )
    if match is None:
        return None
    range_feet = parse_decimal_integer(match.group("range"))
    if range_feet is None:
        return None
    if (
        source.creature_name.casefold() != "medusa"
        or source.source_label.casefold() != "focus gaze"
        or source.action_cost != 1
        or source.kind != "activity"
        or set(source.traits)
        != {"arcane", "concentrate", "incapacitation", "visual"}
    ):
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": "linked-progressive-saving-throw-activity",
            "sourceAbilityId": "petrifying-gaze",
            "rangeFeet": range_feet,
            "requiresVisibility": True,
            "requiresTargetToLook": True,
            "repeatFailure": {
                "condition": "petrified",
                "duration": "permanent",
            },
            "temporaryImmunity": {
                "grant": "after-save",
                "scope": "source-participant-ability",
                "expires": "source-next-turn-start",
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


def link_gaze_abilities(
    abilities: list[dict[str, Any]],
    /,
) -> list[dict[str, Any]]:
    """Resolve source-authored gaze dependencies within one creature block."""

    linked = deepcopy(abilities)
    abilities_by_id: dict[str, dict[str, Any]] = {}
    for ability in linked:
        ability_id = str(ability.get("id") or "")
        if not ability_id or ability_id in abilities_by_id:
            raise ValueError("gaze ability identities are empty or duplicated")
        abilities_by_id[ability_id] = ability

    for ability in linked:
        mechanic = ability.get("mechanic")
        if (
            not ability.get("supported")
            or not isinstance(mechanic, dict)
            or mechanic.get("type")
            != "linked-progressive-saving-throw-activity"
        ):
            continue
        source_ability_id = str(mechanic.get("sourceAbilityId") or "")
        provider = abilities_by_id.get(source_ability_id)
        provider_mechanic = (
            provider.get("mechanic")
            if isinstance(provider, dict)
            else None
        )
        if (
            not isinstance(provider, dict)
            or provider.get("supported") is not True
            or not isinstance(provider_mechanic, dict)
            or provider_mechanic.get("type")
            != "turn-end-saving-throw-aura"
        ):
            raise ValueError(
                f"{ability['name']} requires one supported "
                f"{source_ability_id} aura"
            )
        if (
            int(mechanic["rangeFeet"])
            != int(provider_mechanic["rangeFeet"])
        ):
            raise ValueError(
                f"{ability['name']} range disagrees with "
                f"{provider['name']}"
            )
        failure = provider_mechanic.get("failure")
        saving_throw = provider_mechanic.get("savingThrow")
        repeat_failure = mechanic.get("repeatFailure")
        temporary_immunity = mechanic.get("temporaryImmunity")
        if (
            not isinstance(failure, dict)
            or not isinstance(saving_throw, dict)
            or not isinstance(repeat_failure, dict)
            or not isinstance(temporary_immunity, dict)
        ):
            raise ValueError(
                f"{ability['name']} gaze provider is incomplete"
            )
        ability["mechanic"] = {
            "type": "progressive-saving-throw-activity",
            "sourceAbilityId": source_ability_id,
            "rangeFeet": int(mechanic["rangeFeet"]),
            "requiresVisibility": bool(
                mechanic["requiresVisibility"]
            ),
            "requiresTargetToLook": bool(
                mechanic["requiresTargetToLook"]
            ),
            "savingThrow": deepcopy(saving_throw),
            "progression": {
                "sourceFamily": str(failure["sourceFamily"]),
                "initialFailure": {
                    "condition": str(failure["condition"]),
                    "value": int(failure["value"]),
                    "duration": deepcopy(failure["duration"]),
                },
                "repeatFailure": deepcopy(repeat_failure),
            },
            "temporaryImmunity": deepcopy(temporary_immunity),
        }
    return linked


FRAGMENT = MechanicFamilyFragment(
    family_id="gaze",
    mechanic_types=(
        "turn-start-saving-throw-reaction",
        "progressive-saving-throw-activity",
        "turn-end-saving-throw-aura",
        "linked-progressive-saving-throw-activity",
    ),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="petrifying-glance",
            mechanic_type="turn-start-saving-throw-reaction",
            compiler=compile_petrifying_glance,
        ),
        AbilityCompilerRegistration(
            compiler_id="petrifying-gaze",
            mechanic_type="progressive-saving-throw-activity",
            compiler=compile_petrifying_gaze,
        ),
        AbilityCompilerRegistration(
            compiler_id="medusa-petrifying-gaze",
            mechanic_type="turn-end-saving-throw-aura",
            compiler=compile_medusa_petrifying_gaze,
        ),
        AbilityCompilerRegistration(
            compiler_id="medusa-focus-gaze",
            mechanic_type="linked-progressive-saving-throw-activity",
            compiler=compile_medusa_focus_gaze,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "compile_medusa_focus_gaze",
    "compile_medusa_petrifying_gaze",
    "compile_petrifying_gaze",
    "compile_petrifying_glance",
    "link_gaze_abilities",
]

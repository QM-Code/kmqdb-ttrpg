"""Compile source-authored condition mechanics."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import re
from typing import Any

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RuleReference,
)


VULNERABLE_TO_PRONE_RE = re.compile(
    r"^If a creature critically succeeds at a check to Trip the "
    r"(?P<trip_target>[A-Za-z][A-Za-z '\u2019-]*), the "
    r"(?P<flipped_target>[A-Za-z][A-Za-z '\u2019-]*) is flipped over onto its back "
    r"in addition to the usual effects\. Until it Stands, a "
    r"(?P<defending_target>[A-Za-z][A-Za-z '\u2019-]*) that[’']s flipped onto its back "
    r"has a particularly hard time defending itself; instead of taking the normal "
    r"–(?P<ordinary_penalty>\d+) circumstance penalty to AC for being off-guard, "
    r"it takes a –(?P<vulnerable_penalty>\d+) circumstance penalty to AC\.$",
    re.IGNORECASE,
)
VULNERABLE_TO_PRONE_LABEL = "Vulnerable to Prone"
VULNERABLE_TO_PRONE_MECHANIC_TYPE = "critical-trip-prone-ac-penalty"
SICKENED_RULE_REF = "pf2er.rule:sickened"
FORTITUDE_SAVE_RULE_REF = "pf2er.rule:fortitude-save"
_SEMANTIC_RULE_REF_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*:"
    r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
)
_MECHANIC_TYPE_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def normalize_runtime_owner(value: Any) -> dict[str, str]:
    """Return one exact serialized kernel or selected-mechanic owner."""

    if not isinstance(value, Mapping):
        raise ValueError("condition runtime owner must be an object")
    if value.get("kind") == "kernel" and set(value) == {"kind"}:
        return {"kind": "kernel"}
    mechanic_type = value.get("mechanicType")
    if (
        value.get("kind") != "mechanic"
        or set(value) != {"kind", "mechanicType"}
        or type(mechanic_type) is not str
        or _MECHANIC_TYPE_RE.fullmatch(mechanic_type) is None
    ):
        raise ValueError("condition runtime owner is invalid")
    return {"kind": "mechanic", "mechanicType": mechanic_type}


def exact_semantic_rule_ref(value: Any, label: str) -> str:
    """Return one normalized, exactly namespaced semantic rule identity."""

    if type(value) is not str or _SEMANTIC_RULE_REF_RE.fullmatch(value) is None:
        raise ValueError(
            f"{label} must be an exact normalized semantic rule reference"
        )
    return value


def create_sickened_contribution(
    *,
    target_participant_id: str,
    source_participant_id: str,
    source_ability_id: str,
    source_family: str,
    value: int,
    recovery_dc: int,
    source_rule_ref: str,
    creation_event_sequence: int,
    creation_event_type: str,
    effect_ordinal: int,
    runtime_owner: Mapping[str, Any],
    linked_effect_ids: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Create one exact, independently recoverable Sickened contribution."""

    identifiers = {
        "target participant": target_participant_id,
        "source participant": source_participant_id,
        "source ability": source_ability_id,
        "source family": source_family,
        "creation event type": creation_event_type,
    }
    for label, identifier in identifiers.items():
        if type(identifier) is not str or not identifier:
            raise ValueError(f"Sickened {label} is invalid")
    integer_fields = {
        "value": value,
        "recovery DC": recovery_dc,
        "creation event sequence": creation_event_sequence,
        "effect ordinal": effect_ordinal,
    }
    for label, number in integer_fields.items():
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError(f"Sickened {label} must be a positive integer")
    if (
        not isinstance(linked_effect_ids, (list, tuple))
        or any(type(effect_id) is not str or not effect_id for effect_id in linked_effect_ids)
        or len(set(linked_effect_ids)) != len(linked_effect_ids)
    ):
        raise ValueError("Sickened linked effect IDs are invalid")
    effect_id = (
        f"condition:sickened:{creation_event_sequence}:"
        f"{target_participant_id}:{effect_ordinal}"
    )
    if effect_id in linked_effect_ids:
        raise ValueError("Sickened cannot link to its own contribution")
    return {
        "id": effect_id,
        "kind": "condition",
        "condition": "sickened",
        "targetParticipantId": target_participant_id,
        "sourceParticipantId": source_participant_id,
        "sourceAbilityId": source_ability_id,
        "sourceFamily": source_family,
        "runtimeOwner": normalize_runtime_owner(runtime_owner),
        "value": value,
        "initialValue": value,
        "recovery": {
            "actionType": "Retch",
            "check": "fortitude",
            "dc": recovery_dc,
        },
        "ruleRefs": {
            "source": exact_semantic_rule_ref(
                source_rule_ref,
                "Sickened source rule",
            ),
            "sickened": SICKENED_RULE_REF,
            "fortitude": FORTITUDE_SAVE_RULE_REF,
        },
        "creation": {
            "eventSequence": creation_event_sequence,
            "eventType": creation_event_type,
            "effectOrdinal": effect_ordinal,
        },
        "linkedEffectIds": list(linked_effect_ids),
    }


def validate_sickened_contribution(value: Any) -> dict[str, Any]:
    """Return one contribution after proving its complete normalized shape."""

    if not isinstance(value, dict):
        raise ValueError("Sickened contribution must be an object")
    expected_keys = {
        "id",
        "kind",
        "condition",
        "targetParticipantId",
        "sourceParticipantId",
        "sourceAbilityId",
        "sourceFamily",
        "runtimeOwner",
        "value",
        "initialValue",
        "recovery",
        "ruleRefs",
        "creation",
        "linkedEffectIds",
    }
    if set(value) != expected_keys:
        raise ValueError("Sickened contribution fields are invalid")
    creation = value.get("creation")
    recovery = value.get("recovery")
    if (
        not isinstance(creation, dict)
        or set(creation)
        != {"eventSequence", "eventType", "effectOrdinal"}
        or not isinstance(recovery, dict)
        or set(recovery) != {"actionType", "check", "dc"}
    ):
        raise ValueError("Sickened creation or recovery evidence is invalid")
    current_value = value.get("value")
    initial_value = value.get("initialValue")
    if (
        isinstance(current_value, bool)
        or not isinstance(current_value, int)
        or current_value < 1
        or isinstance(initial_value, bool)
        or not isinstance(initial_value, int)
        or initial_value < current_value
    ):
        raise ValueError("Sickened current and initial values are invalid")
    rebuilt = create_sickened_contribution(
        target_participant_id=value.get("targetParticipantId"),
        source_participant_id=value.get("sourceParticipantId"),
        source_ability_id=value.get("sourceAbilityId"),
        source_family=value.get("sourceFamily"),
        value=initial_value,
        recovery_dc=recovery.get("dc"),
        source_rule_ref=(
            value.get("ruleRefs", {}).get("source")
            if isinstance(value.get("ruleRefs"), dict)
            else None
        ),
        creation_event_sequence=creation.get("eventSequence"),
        creation_event_type=creation.get("eventType"),
        effect_ordinal=creation.get("effectOrdinal"),
        runtime_owner=value.get("runtimeOwner"),
        linked_effect_ids=value.get("linkedEffectIds"),
    )
    rebuilt["value"] = current_value
    if (
        recovery.get("actionType") != "Retch"
        or recovery.get("check") != "fortitude"
        or value.get("ruleRefs")
        != {
            "source": value.get("ruleRefs", {}).get("source"),
            "sickened": SICKENED_RULE_REF,
            "fortitude": FORTITUDE_SAVE_RULE_REF,
        }
        or value != rebuilt
    ):
        raise ValueError("Sickened contribution evidence is invalid")
    return value


def sickened_contribution_digest(value: Any) -> str:
    """Return the canonical integrity digest bound by the creation event."""

    contribution = deepcopy(validate_sickened_contribution(value))
    contribution["value"] = int(contribution["initialValue"])
    encoded = json.dumps(
        contribution,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def reduce_sickened_contribution(
    effects: list[dict[str, Any]],
    *,
    effect_id: str,
    reduction: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reduce one exact contribution and end only its explicit linked effects."""

    if (
        not isinstance(effects, list)
        or type(effect_id) is not str
        or not effect_id
        or isinstance(reduction, bool)
        or not isinstance(reduction, int)
        or reduction < 1
    ):
        raise ValueError("Sickened reduction request is invalid")
    matches = [
        effect
        for effect in effects
        if isinstance(effect, dict) and effect.get("id") == effect_id
    ]
    if len(matches) != 1:
        raise ValueError("Sickened reduction requires one exact contribution")
    contribution = validate_sickened_contribution(matches[0])
    linked_ids = list(contribution["linkedEffectIds"])
    linked_effects = [
        effect
        for effect in effects
        if isinstance(effect, dict) and effect.get("id") in linked_ids
    ]
    if (
        len(linked_effects) != len(linked_ids)
        or {effect["id"] for effect in linked_effects} != set(linked_ids)
        or any(
            effect.get("targetParticipantId")
            != contribution["targetParticipantId"]
            for effect in linked_effects
        )
    ):
        raise ValueError("Sickened linked-effect evidence is stale or forged")
    before = int(contribution["value"])
    after = max(0, before - reduction)
    updated = deepcopy(effects)
    updated_contribution = next(
        effect for effect in updated if effect.get("id") == effect_id
    )
    removed_ids: list[str] = []
    ended_linked_ids: list[str] = []
    if after:
        updated_contribution["value"] = after
    else:
        removed_ids = [effect_id, *linked_ids]
        ended_linked_ids = linked_ids
        updated = [
            effect
            for effect in updated
            if effect.get("id") not in set(removed_ids)
        ]
    return updated, {
        "effectId": effect_id,
        "beforeValue": before,
        "afterValue": after,
        "requestedReduction": reduction,
        "appliedReduction": before - after,
        "changedEffectIds": [effect_id],
        "removedEffectIds": removed_ids,
        "endedLinkedEffectIds": ended_linked_ids,
    }


def compile_vulnerable_to_prone(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile the stronger off-guard AC penalty from one critical Trip shape."""

    from .source_values import parse_decimal_integer

    match = VULNERABLE_TO_PRONE_RE.fullmatch(
        " ".join(source.description.split())
    )
    if match is None:
        return None

    canonical_name = " ".join(source.creature_name.split()).casefold()
    short_name = canonical_name.rsplit(" ", 1)[-1]
    if (
        match.group("trip_target").casefold() != canonical_name
        or match.group("flipped_target").casefold() != short_name
        or match.group("defending_target").casefold() != canonical_name
    ):
        return None

    ordinary_penalty = parse_decimal_integer(
        match.group("ordinary_penalty")
    )
    vulnerable_penalty = parse_decimal_integer(
        match.group("vulnerable_penalty")
    )
    if ordinary_penalty is None or vulnerable_penalty is None:
        return None
    if ordinary_penalty != 2 or vulnerable_penalty <= ordinary_penalty:
        return None
    if (
        source.source_label.casefold()
        != VULNERABLE_TO_PRONE_LABEL.casefold()
        or source.kind != "passive"
        or source.action_cost is not None
    ):
        return None

    return AbilityCompilerPatch(
        mechanic={
            "type": VULNERABLE_TO_PRONE_MECHANIC_TYPE,
            "trigger": {
                "check": "trip",
                "degree": "critical-success",
            },
            "condition": "prone",
            "duration": {"untilAction": "Stand"},
            "armorClassPenalty": {
                "type": "circumstance",
                "value": -vulnerable_penalty,
                "replaces": {
                    "condition": "off-guard",
                    "value": -ordinary_penalty,
                },
            },
            "rules": {
                "trip": {
                    "sourceId": "core-pc1",
                    "locator": "236.2",
                },
                "offGuard": {
                    "sourceId": "core-pc1",
                    "locator": "445.2",
                },
                "prone": {
                    "sourceId": "core-pc1",
                    "locator": "445.6",
                },
                "stand": {
                    "sourceId": "core-pc1",
                    "locator": "418.1",
                },
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="conditions",
    mechanic_types=(VULNERABLE_TO_PRONE_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="vulnerable-to-prone",
            mechanic_type=VULNERABLE_TO_PRONE_MECHANIC_TYPE,
            compiler=compile_vulnerable_to_prone,
        ),
    ),
)


__all__ = [
    "FORTITUDE_SAVE_RULE_REF",
    "FRAGMENT",
    "SICKENED_RULE_REF",
    "compile_vulnerable_to_prone",
    "create_sickened_contribution",
    "exact_semantic_rule_ref",
    "normalize_runtime_owner",
    "reduce_sickened_contribution",
    "sickened_contribution_digest",
    "validate_sickened_contribution",
]

"""Compile reviewed fixed-Strike and unrestricted Reactive Strike grammar."""

from __future__ import annotations

import re

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RuleReference,
)


REACTIVE_STRIKE_LABEL = "Reactive Strike"
REACTIVE_STRIKE_MECHANIC_TYPE = "triggered-melee-strike-reaction"
REACTIVE_STRIKE_RESTRICTION_RE = re.compile(
    r"^(?P<strike>[A-Za-z][A-Za-z '\u2019-]*) only "
    r"\(page 359\)\.$",
    re.IGNORECASE,
)
UNRESTRICTED_REACTIVE_STRIKE_REFERENCE = "(page 359)"


def _restricted_strike_id(source: AbilitySource) -> str | None:
    normalized_description = " ".join(source.description.split())
    restriction = REACTIVE_STRIKE_RESTRICTION_RE.fullmatch(
        normalized_description
    )
    if restriction is None:
        return None
    strike_id = re.sub(
        r"[^a-z0-9]+",
        "-",
        restriction.group("strike").casefold(),
    ).strip("-")
    return strike_id or None


def compile_reactive_strike(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only an exact reviewed Monster Core Reactive Strike reference."""

    normalized_description = " ".join(source.description.split())
    strike_id = _restricted_strike_id(source)
    unrestricted = (
        normalized_description == UNRESTRICTED_REACTIVE_STRIKE_REFERENCE
    )
    if strike_id is None and not unrestricted:
        return None
    if source.source_label.casefold() != REACTIVE_STRIKE_LABEL.casefold():
        return None
    if source.kind != "reaction" or source.action_cost != "reaction":
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": REACTIVE_STRIKE_MECHANIC_TYPE,
            **(
                {"strikeId": strike_id}
                if strike_id is not None
                else {"strikeSelection": "any-melee-strike"}
            ),
            "targetRelation": "creature-within-strike-reach",
            "triggers": [
                {
                    "id": "manipulate-action",
                    "actionTrait": "manipulate",
                    "timing": "before-effects",
                    "criticalHit": "disrupt-triggering-action",
                },
                {
                    "id": "move-action",
                    "actionTrait": "move",
                    "timing": "on-use",
                },
                {
                    "id": "ranged-attack",
                    "strikeKind": "ranged",
                    "timing": "before-attack",
                },
                {
                    "id": "leaves-square-during-move",
                    "timing": "before-leaving-square",
                },
            ],
            "ignoredTriggerActions": ["Step"],
            "multipleAttackPenalty": {
                "applies": False,
                "counts": False,
            },
            "rules": {
                "reactiveStrike": {
                    "sourceId": "core-mc1",
                    "locator": "358.2",
                },
                "triggeredActions": {
                    "sourceId": "core-pc1",
                    "locator": "414.6",
                },
                "disruption": {
                    "sourceId": "core-pc1",
                    "locator": "415.3",
                },
                "step": {
                    "sourceId": "core-pc1",
                    "locator": "418.2",
                },
                "multipleAttackPenalty": {
                    "sourceId": "core-pc1",
                    "locator": "402.1",
                },
            },
        },
        rule=RuleReference(source.source_id, source.locator),
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="reactive-strike",
    mechanic_types=(REACTIVE_STRIKE_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="reactive-strike",
            mechanic_type=REACTIVE_STRIKE_MECHANIC_TYPE,
            compiler=compile_reactive_strike,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "compile_reactive_strike",
]

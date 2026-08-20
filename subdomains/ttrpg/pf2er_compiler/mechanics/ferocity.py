"""Compile the reviewed Monster Core Ferocity glossary reference."""

from __future__ import annotations

import re

from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RuleReference,
)


FEROCITY_LABEL = "Ferocity"
FEROCITY_MECHANIC_TYPE = "zero-hit-points-reaction"
FEROCITY_SOURCE_ID = "core-mc1"
FEROCITY_RULE = RuleReference(
    source_id=FEROCITY_SOURCE_ID,
    locator="358.2",
)
GLOSSARY_REFERENCE_RE = re.compile(
    r"^\(page 359\)\.?$",
    re.IGNORECASE,
)


def _reviewed_rule_reference(
    source: AbilitySource,
) -> RuleReference | None:
    if source.source_id != FEROCITY_SOURCE_ID:
        return None
    if GLOSSARY_REFERENCE_RE.fullmatch(source.description) is None:
        return None
    return FEROCITY_RULE


def compile_ferocity(
    source: AbilitySource,
    /,
) -> AbilityCompilerPatch | None:
    """Compile only the exact reviewed core-mc1 Ferocity reference."""

    rule = _reviewed_rule_reference(source)
    if rule is None:
        return None
    if source.source_label.casefold() != FEROCITY_LABEL.casefold():
        return None
    if source.kind != "reaction" or source.action_cost != "reaction":
        return None
    return AbilityCompilerPatch(
        mechanic={
            "type": FEROCITY_MECHANIC_TYPE,
            "remainingHitPoints": 1,
            "increaseCondition": {
                "name": "wounded",
                "value": 1,
            },
            "disabledAtConditionValue": 3,
        },
        rule=rule,
    )


FRAGMENT = MechanicFamilyFragment(
    family_id="ferocity",
    mechanic_types=(FEROCITY_MECHANIC_TYPE,),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id="ferocity",
            mechanic_type=FEROCITY_MECHANIC_TYPE,
            compiler=compile_ferocity,
        ),
    ),
)


__all__ = [
    "FRAGMENT",
    "compile_ferocity",
]

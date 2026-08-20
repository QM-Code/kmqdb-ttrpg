"""Source-exact Fungus Leshy Spore Cloud and Spores contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..errors import EngineInputError
from .contracts import (
    AbilityCompilerPatch,
    AbilityCompilerRegistration,
    AbilitySource,
    MechanicFamilyFragment,
    RawSourceArray,
    RawSourceObject,
    RuleReference,
)
from .persistent_damage_foundation import (
    FixedFailedSavePersistentDamageBinding,
    PersistentDamageLinkedEffect,
    PersistentDamagePathStep,
    compile_fixed_failed_save_persistent_damage,
)
from .source_authority import (
    RawMemberStep,
    SourceAuthorityAdapter,
    raw_source_sha256,
)


SOURCE_ID = "core-mc1"
LOCATOR = "217.2"
SECTION_ID = "core-mc1:leshy"
CREATURE_NAME = "Fungus Leshy"
SPORE_CLOUD_ABILITY_ID = "spore-cloud"
SPORES_ABILITY_ID = "spores"
SPORE_POD_STRIKE_ID = "strike:spore-pod:ranged"
SPORE_CLOUD_MECHANIC_TYPE = "fungus-leshy-spore-cloud"
SPORES_MECHANIC_TYPE = "fungus-leshy-spores-strike-rider"

SPORE_CLOUD_TRAITS = ("poison",)
SPORE_CLOUD_DESCRIPTION = (
    "A fungus leshy can unleash a cloud of spores that irritates the eyes "
    "and throats of non-fungus creatures in a 15-foot emanation. Each "
    "creature must succeed at a DC 16 Fortitude save or take 1 persistent "
    "poison damage. A creature has its vision reduced as long as the "
    "persistent damage continues and can see only within 20 feet."
)
SPORES_DESCRIPTION = (
    "A creature that takes damage from a fungus leshy's spore pod Strike "
    "must attempt a saving throw with the same DC and effect as its Spore "
    "Cloud ability."
)

SOURCE_RULE = {"sourceId": SOURCE_ID, "locator": LOCATOR}
DUPLICATE_EFFECTS_RULE = {"sourceId": "core-pc1", "locator": "399.1"}
DEGREE_RULE = {"sourceId": "core-pc1", "locator": "401.4"}
SAVE_RULE = {"sourceId": "core-pc1", "locator": "404.1"}
IMMUNITY_RULE = {"sourceId": "core-pc1", "locator": "408.2"}
POISON_RULE = {"sourceId": "core-pc1", "locator": "409.6"}
RANGE_RULE = {"sourceId": "core-pc1", "locator": "426.3"}
LINE_OF_EFFECT_RULE = {"sourceId": "core-pc1", "locator": "426.6"}
VISION_RULE = {"sourceId": "core-pc1", "locator": "427.2"}
EMANATION_RULE = {"sourceId": "core-pc1", "locator": "428.4"}
PERSISTENT_DAMAGE_RULE = {"sourceId": "core-pc1", "locator": "445.4"}
TRAIT_RULE = {"sourceId": "core-pc1", "locator": "452.1"}

SOURCE_RECEIPTS = {
    "sporePod": {
        "selectionPath": (("Ranged", 23),),
        "selectionSha256": (
            "26ec08f50c6407322349c80d5bee8a29bb893cfa94bccffd483dddb92f5421af"
        ),
        "receiptDigest": (
            "5ea595dd3cd9db43d1242e6befb9bbd73683cd3c6f68d49ddc5de085249d8fff"
        ),
    },
    "sporeCloud": {
        "selectionPath": (("!.Spore Cloud", 26),),
        "selectionSha256": (
            "a694b242ba4f84e76d929a533c9163c323a6d6ad33841a6c43253811d10094fa"
        ),
        "receiptDigest": (
            "94dd7218e35ddac10470943e27f729b50e41b5e8995b413d44127c4497b2d399"
        ),
    },
    "spores": {
        "selectionPath": (("!.Spores", 27),),
        "selectionSha256": (
            "4fa0ce8079a64ff2451db24aa5c81543a68b7e0946b12e59a659e59bdbd17a11"
        ),
        "receiptDigest": (
            "2c691899b91c6369f0a5c630eda1daae551d9a855c895983b98ac67bae3a3e4a"
        ),
    },
}
TARGET_PATH = (("Leshy", 1),)
CARRIER_PATH = (("^.creature", 3),)
CARRIER_BLOCK_SHA256 = (
    "5a69ce6c6e32ab9c560a1784ab746f48aeb67ea97cb05266a37ddbb8524a4bc9"
)

_EXACT_SPORE_POD = RawSourceArray(
    (
        RawSourceObject.from_pairs(
            (
                ("Name", "spore pod"),
                ("Attack", "+10"),
                ("Traits", RawSourceArray(("range increment 30 feet",))),
                ("Damage", "1d6+2 bludgeoning plus spores"),
            )
        ),
    )
)
_EXACT_SPORE_CLOUD = RawSourceObject.from_pairs(
    (
        ("Action", "two"),
        ("Traits", RawSourceArray(SPORE_CLOUD_TRAITS)),
        ("Description", SPORE_CLOUD_DESCRIPTION),
    )
)
_EXACT_SPORES = SPORES_DESCRIPTION


def _persistent_damage_definition() -> dict[str, Any]:
    binding = FixedFailedSavePersistentDamageBinding(
        binding_id="persistent-producer:217.2:spore-cloud",
        name="Spore Cloud",
        source_text=SPORE_CLOUD_DESCRIPTION,
        source_text_sha256=(
            "fa44aa265404854d5cbe04d55e76dcfd5624f349fc9409d765dc542bbd0a3ee8"
        ),
        source_id=SOURCE_ID,
        locator=LOCATOR,
        section_id=SECTION_ID,
        content_path=("Leshy", CREATURE_NAME),
        ordered_path=(
            PersistentDamagePathStep(raw_key="^.creature", pair_index=3),
            PersistentDamagePathStep(raw_key="!.Spore Cloud", pair_index=26),
            PersistentDamagePathStep(raw_key="Description", pair_index=2),
        ),
        damage_expression="1",
        damage_type="poison",
        linked_effects=(
            PersistentDamageLinkedEffect(
                effect_id="spore-cloud-vision-limit",
                lifecycle="while-contribution-active",
                description=(
                    "Vision is limited to 20 feet while this poison continues."
                ),
            ),
        ),
        rules=(
            RuleReference("core-pc1", "406.2"),
            RuleReference("core-pc1", "407.1"),
            RuleReference("core-pc1", "400.1"),
            RuleReference("core-pc1", "436.3"),
            RuleReference("core-pc1", "445.4"),
            RuleReference("core-pc1", "409.6"),
        ),
        scale_rule=RuleReference(SOURCE_ID, LOCATOR),
    )
    compiled = compile_fixed_failed_save_persistent_damage(binding)
    if compiled is None:
        raise RuntimeError("canonical Spore Cloud persistent damage did not compile")
    return compiled


PERSISTENT_DAMAGE_DEFINITION = _persistent_damage_definition()


def _saving_throw() -> dict[str, Any]:
    return {"type": "fortitude", "dc": 16}


def _outcomes() -> dict[str, Any]:
    return {
        "criticalSuccess": {"persistentPoison": False},
        "success": {"persistentPoison": False},
        "failure": {"persistentPoison": True},
        "criticalFailure": {"persistentPoison": True},
    }


def _shared_effect() -> dict[str, Any]:
    return {
        "savingThrow": _saving_throw(),
        "outcomes": _outcomes(),
        "persistentDamage": deepcopy(PERSISTENT_DAMAGE_DEFINITION),
        "visionLimit": {
            "maximumDistanceFeet": 20,
            "sense": "vision",
            "lifecycle": "while-contribution-active",
        },
    }


def _spore_cloud_mechanic() -> dict[str, Any]:
    return {
        "type": SPORE_CLOUD_MECHANIC_TYPE,
        "targeting": {
            "selection": "automatic-at-use",
            "area": {"type": "emanation", "radiusFeet": 15},
            "recipients": "all-non-fungus-creatures",
            "requiresLineOfEffect": True,
        },
        **_shared_effect(),
        "rules": {
            "ability": deepcopy(SOURCE_RULE),
            "duplicateEffects": deepcopy(DUPLICATE_EFFECTS_RULE),
            "degrees": deepcopy(DEGREE_RULE),
            "savingThrows": deepcopy(SAVE_RULE),
            "immunity": deepcopy(IMMUNITY_RULE),
            "poison": deepcopy(POISON_RULE),
            "range": deepcopy(RANGE_RULE),
            "lineOfEffect": deepcopy(LINE_OF_EFFECT_RULE),
            "vision": deepcopy(VISION_RULE),
            "emanations": deepcopy(EMANATION_RULE),
            "persistentDamage": deepcopy(PERSISTENT_DAMAGE_RULE),
            "traits": deepcopy(TRAIT_RULE),
        },
    }


def _spores_mechanic() -> dict[str, Any]:
    return {
        "type": SPORES_MECHANIC_TYPE,
        "trigger": "strike-deals-positive-post-defense-damage",
        "strikeLabels": ["spore-pod"],
        "sharedEffectAbilityId": SPORE_CLOUD_ABILITY_ID,
        **_shared_effect(),
        "rules": deepcopy(_spore_cloud_mechanic()["rules"]),
    }


def compile_spore_cloud(source: AbilitySource, /) -> AbilityCompilerPatch | None:
    if (
        source.source_id != SOURCE_ID
        or source.locator != LOCATOR
        or source.creature_name != CREATURE_NAME
        or source.source_label != "Spore Cloud"
        or source.raw_member.key != "!.Spore Cloud"
        or source.kind != "activity"
        or source.action_cost != 2
        or source.traits != SPORE_CLOUD_TRAITS
        or source.trigger
        or source.description != SPORE_CLOUD_DESCRIPTION
        or source.raw_member.value != _EXACT_SPORE_CLOUD
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=_spore_cloud_mechanic(),
        rule=RuleReference(SOURCE_ID, LOCATOR),
        traits=SPORE_CLOUD_TRAITS,
    )


def compile_spores(source: AbilitySource, /) -> AbilityCompilerPatch | None:
    if (
        source.source_id != SOURCE_ID
        or source.locator != LOCATOR
        or source.creature_name != CREATURE_NAME
        or source.source_label != "Spores"
        or source.raw_member.key != "!.Spores"
        or source.kind != "passive"
        or source.action_cost is not None
        or source.traits
        or source.trigger
        or source.description != SPORES_DESCRIPTION
        or source.raw_member.value != _EXACT_SPORES
    ):
        return None
    return AbilityCompilerPatch(
        mechanic=_spores_mechanic(),
        rule=RuleReference(SOURCE_ID, LOCATOR),
    )


def spore_cloud_spec(value: object, /) -> dict[str, Any]:
    mechanic = value.get("mechanic") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("id") != SPORE_CLOUD_ABILITY_ID
        or value.get("name") != "Spore Cloud"
        or value.get("kind") != "activity"
        or value.get("actionCost") != 2
        or value.get("traits") != list(SPORE_CLOUD_TRAITS)
        or value.get("description") != SPORE_CLOUD_DESCRIPTION
        or value.get("supported") is not True
        or value.get("rule") != SOURCE_RULE
        or mechanic != _spore_cloud_mechanic()
    ):
        raise EngineInputError("Fungus Leshy Spore Cloud mechanic is invalid")
    return deepcopy(mechanic)


def spores_spec(value: object, /) -> dict[str, Any]:
    mechanic = value.get("mechanic") if isinstance(value, dict) else None
    expected = _spores_mechanic()
    expected["strikeIds"] = [SPORE_POD_STRIKE_ID]
    if (
        not isinstance(value, dict)
        or value.get("id") != SPORES_ABILITY_ID
        or value.get("name") != "Spores"
        or value.get("kind") != "passive"
        or value.get("actionCost") is not None
        or value.get("traits") != []
        or value.get("description") != SPORES_DESCRIPTION
        or value.get("supported") is not True
        or value.get("rule") != SOURCE_RULE
        or mechanic != expected
    ):
        raise EngineInputError("Fungus Leshy Spores mechanic is invalid")
    return deepcopy(mechanic)


def validate_definition_links(value: object, /) -> None:
    if not isinstance(value, dict):
        raise EngineInputError("Fungus Leshy definition is invalid")
    abilities = {
        ability.get("id"): ability
        for ability in value.get("abilities") or []
        if isinstance(ability, dict)
    }
    strikes = {
        strike.get("id"): strike
        for strike in value.get("strikes") or []
        if isinstance(strike, dict)
    }
    cloud = abilities.get(SPORE_CLOUD_ABILITY_ID)
    spores = abilities.get(SPORES_ABILITY_ID)
    strike = strikes.get(SPORE_POD_STRIKE_ID)
    spore_cloud_spec(cloud)
    mechanic = spores_spec(spores)
    riders = strike.get("damage", {}).get("riderEffects") if strike else None
    matches = [
        rider
        for rider in riders or []
        if isinstance(rider, dict)
        and rider.get("abilityId") == SPORES_ABILITY_ID
        and rider.get("effectType") == SPORES_MECHANIC_TYPE
        and rider.get("supported") is True
    ]
    if (
        strike is None
        or mechanic.get("sharedEffectAbilityId") != SPORE_CLOUD_ABILITY_ID
        or mechanic.get("strikeIds") != [SPORE_POD_STRIKE_ID]
        or len(matches) != 1
        or mechanic["savingThrow"] != cloud["mechanic"]["savingThrow"]
        or mechanic["outcomes"] != cloud["mechanic"]["outcomes"]
        or mechanic["persistentDamage"]
        != cloud["mechanic"]["persistentDamage"]
        or mechanic["visionLimit"] != cloud["mechanic"]["visionLimit"]
    ):
        raise EngineInputError("Fungus Leshy Spore Cloud/Spores link is invalid")


def verify_current_source(authority: SourceAuthorityAdapter, /) -> dict[str, Any]:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("Fungus Leshy source proof requires exact authority")
    proof: dict[str, Any] = {}
    expected_values = {
        "sporePod": _EXACT_SPORE_POD,
        "sporeCloud": _EXACT_SPORE_CLOUD,
        "spores": _EXACT_SPORES,
    }
    for name, receipt in SOURCE_RECEIPTS.items():
        selection_key, selection_ordinal = receipt["selectionPath"][0]
        selected = authority.resolve(
            authority.address(
                source_id=SOURCE_ID,
                locator=LOCATOR,
                carrier_path=(RawMemberStep("^.creature", 3),),
                selection_path=(
                    RawMemberStep(selection_key, selection_ordinal),
                ),
            )
        )
        address = selected.address
        if (
            address.section_id != SECTION_ID
            or tuple(
                (item.raw_key, item.member_ordinal)
                for item in address.target_path
            )
            != TARGET_PATH
            or tuple(
                (item.raw_key, item.member_ordinal)
                for item in address.carrier_path
            )
            != CARRIER_PATH
            or selected.receipt.block_sha256 != CARRIER_BLOCK_SHA256
            or selected.receipt.selection_sha256
            != receipt["selectionSha256"]
            or selected.receipt.digest != receipt["receiptDigest"]
            or raw_source_sha256(selected.raw_value)
            != receipt["selectionSha256"]
            or selected.raw_value != expected_values[name]
            or selected.carrier.raw_block.values("Name") != (CREATURE_NAME,)
            or selected.carrier.raw_block.values("Traits")
            != (RawSourceArray(("fungus", "leshy")),)
        ):
            raise EngineInputError(
                f"Fungus Leshy {name} source proof failed"
            )
        proof[name] = {
            "selectionPath": [list(item) for item in receipt["selectionPath"]],
            "selectionSha256": receipt["selectionSha256"],
            "receiptDigest": receipt["receiptDigest"],
        }
    return {
        "sourceId": SOURCE_ID,
        "locator": LOCATOR,
        "sectionId": SECTION_ID,
        "targetPath": [list(item) for item in TARGET_PATH],
        "carrierPath": [list(item) for item in CARRIER_PATH],
        "carrierBlockSha256": CARRIER_BLOCK_SHA256,
        "members": proof,
    }


FRAGMENT = MechanicFamilyFragment(
    family_id="fungus-leshy-spores",
    mechanic_types=(SPORE_CLOUD_MECHANIC_TYPE, SPORES_MECHANIC_TYPE),
    ability_compilers=(
        AbilityCompilerRegistration(
            compiler_id=SPORE_CLOUD_ABILITY_ID,
            mechanic_type=SPORE_CLOUD_MECHANIC_TYPE,
            compiler=compile_spore_cloud,
        ),
        AbilityCompilerRegistration(
            compiler_id=SPORES_ABILITY_ID,
            mechanic_type=SPORES_MECHANIC_TYPE,
            compiler=compile_spores,
        ),
    ),
)


__all__ = [
    "CREATURE_NAME",
    "FRAGMENT",
    "LOCATOR",
    "PERSISTENT_DAMAGE_DEFINITION",
    "SOURCE_ID",
    "SOURCE_RULE",
    "SPORE_CLOUD_ABILITY_ID",
    "SPORE_CLOUD_DESCRIPTION",
    "SPORE_CLOUD_MECHANIC_TYPE",
    "SPORE_CLOUD_TRAITS",
    "SPORE_POD_STRIKE_ID",
    "SPORES_ABILITY_ID",
    "SPORES_DESCRIPTION",
    "SPORES_MECHANIC_TYPE",
    "VISION_RULE",
    "compile_spore_cloud",
    "compile_spores",
    "spore_cloud_spec",
    "spores_spec",
    "validate_definition_links",
    "verify_current_source",
]

"""Compile reviewed creature spontaneous-spellcasting carriers.

This module accepts an exact, authority-issued ``Spellcasting`` selection
from Monster Core, resolves reviewed Player Core spell and governing-rule
providers from the same authority adapter, and emits immutable casting-entry
metadata.  Creature profiles own only their authored casting statistics,
resources, and repertoire.  Spell providers own reusable normalized effects.

This remains a strict reviewed compiler rather than an arbitrary prose
interpreter.  A spell effect is executable only when its provider has an
exact descriptor and the runtime has registered that descriptor family.
"""

from __future__ import annotations

import hashlib
import re
from types import MappingProxyType
from typing import Any, Callable, final
from weakref import WeakKeyDictionary

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
)
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceAuthorityError,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)
from .source_values import parse_decimal_integer


FAMILY_ID = "spontaneous-spellcasting"
COMPILER_ID = "creature-spontaneous-spellcasting"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"
GOBLIN_PYRO_LOCATOR = "175.1"
GOBLIN_WAR_CHANTER_LOCATOR = "175.3"
KOBOLD_CAVERN_MAGE_LOCATOR = "211.2"
GNOME_BARD_LOCATOR = "172.2"

_CARRIER_FIELD = "Spellcasting"
_SLOT_ENTRY_RE = re.compile(
    r"^(?P<rank>1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th) "
    r"\((?P<count>[1-9][0-9]*) "
    r"(?P<unit>slot|slots)\)$",
    re.ASCII,
)
_CANTRIP_ENTRY_RE = re.compile(
    r"^Cantrips "
    r"\((?P<rank>1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\)$",
    re.ASCII,
)
_ITALIC_SPELL_RE = re.compile(r"<i>(?P<name>[a-z]+(?: [a-z]+)*)</i>")
_CITATION_RE = re.compile(r" \(<i>Player Core</i> [1-9][0-9]*\)$")
_RANKS = {
    "1st": 1,
    "2nd": 2,
    "3rd": 3,
    "4th": 4,
    "5th": 5,
    "6th": 6,
    "7th": 7,
    "8th": 8,
    "9th": 9,
    "10th": 10,
}

_CARRIER_PROFILES = {
    GNOME_BARD_LOCATOR: {
        "label": "Gnome Bard",
        "selectionSha256": (
            "a1ca55541ff11ed7028a65bed93afbdf9ef67f4775b3467f199f970d6b616bf9"
        ),
        "header": "Occult Spontaneous Spells",
        "castingId": "occult-spontaneous-spells",
        "tradition": "occult",
        "dc": 19,
        "attack": 11,
        "slots": (
            (1, 4, ("charm", "command")),
        ),
        "cantrips": (
            1,
            (
                "courageous-anthem",
                "daze",
                "figment",
                "message",
                "prestidigitation",
                "summon-instrument",
            ),
        ),
        "active": ("courageous-anthem", "summon-instrument"),
        "explicitGrants": ("courageous-anthem",),
    },
    GOBLIN_PYRO_LOCATOR: {
        "label": "Goblin Pyro",
        "selectionSha256": (
            "d43b03e1631a00f01a0b367e89f20063584736cb4fdafd8c8081c98f804c36e2"
        ),
        "header": "Arcane Spontaneous Spells",
        "castingId": "arcane-spontaneous-spells",
        "tradition": "arcane",
        "dc": 16,
        "attack": 6,
        "slots": (
            (1, 3, ("breathe-fire", "grease")),
        ),
        "cantrips": (
            1,
            (
                "ignition",
                "light",
                "tangle-vine",
                "telekinetic-hand",
            ),
        ),
        "active": (
            "breathe-fire",
            "grease",
            "ignition",
            "light",
            "tangle-vine",
            "telekinetic-hand",
        ),
        "explicitGrants": (),
    },
    GOBLIN_WAR_CHANTER_LOCATOR: {
        "label": "Goblin War Chanter",
        "selectionSha256": (
            "2dfac328a5d2bc1e3ef299011f8b7d52806c2bb03207d0d0f931e530658d8959"
        ),
        "header": "Occult Spontaneous Spells",
        "castingId": "occult-spontaneous-spells",
        "tradition": "occult",
        "dc": 17,
        "attack": 7,
        "slots": (
            (1, 2, ("bless", "soothe")),
        ),
        "cantrips": (
            1,
            (
                "figment",
                "courageous-anthem",
                "message",
                "telekinetic-hand",
                "telekinetic-projectile",
            ),
        ),
        "active": (
            "bless",
            "soothe",
            "courageous-anthem",
            "telekinetic-hand",
            "telekinetic-projectile",
        ),
        "explicitGrants": ("courageous-anthem",),
    },
    KOBOLD_CAVERN_MAGE_LOCATOR: {
        "label": "Kobold Cavern Mage",
        "selectionSha256": (
            "f67059ccd8e58cba762e12e83e0a32b768529fae9a062e42b6ee038b899d8f08"
        ),
        "header": "Primal Spontaneous Spells",
        "castingId": "primal-spontaneous-spells",
        "tradition": "primal",
        "dc": 18,
        "attack": None,
        "slots": (
            (
                1,
                4,
                (
                    "fleet-step",
                    "heal",
                    "pummeling-rubble",
                    "runic-weapon",
                ),
            ),
        ),
        "cantrips": (
            1,
            (
                "caustic-blast",
                "detect-magic",
                "figment",
                "know-the-way",
                "tangle-vine",
            ),
        ),
        "active": (
            "fleet-step",
            "heal",
            "pummeling-rubble",
            "runic-weapon",
            "caustic-blast",
            "tangle-vine",
        ),
        "explicitGrants": ("figment",),
    },
}

_BREATHE_FIRE_PARAGRAPH = (
    "A gout of flame sprays from your mouth. You deal 2d6 fire damage "
    "to creatures in the area with a basic Reflex save."
)
_HEAL_DESCRIPTION = (
    "You channel vital energy to heal the living or damage the undead. If "
    "the target is a willing living creature, you restore 1d8 Hit Points. "
    "If the target is undead, you deal that amount of vitality damage to "
    "it, and it gets a basic Fortitude save. The number of actions you spend "
    "when Casting this Spell determines its targets, range, area, and other "
    "parameters. The spell has a range of touch. (concentrate) The spell has "
    "a range of 30 feet. If you’re healing a living creature, increase the "
    "Hit Points restored by 8. (concentrate) You disperse vital energy in a "
    "30-foot emanation. This targets all living and undead creatures in the "
    "burst."
)
_HEAL_HEIGHTENED = (
    "The amount of healing or damage increases by 1d8, and the extra healing "
    "for the 2-action version increases by 8."
)
_RUNIC_WEAPON_DESCRIPTION = (
    "The weapon glimmers with magic as temporary runes carve down its "
    "length. The target becomes a +1 striking weapon, gaining a +1 item "
    "bonus to attack rolls and increasing the number of weapon damage dice "
    "to two."
)
_RUNIC_WEAPON_HEIGHTENED_SIXTH = (
    "The weapon is +2 greater striking."
)
_RUNIC_WEAPON_HEIGHTENED_NINTH = (
    "The weapon is +3 major striking."
)
_GREASE_INTRODUCTION = "You conjure grease, choosing an area or target."
_GREASE_AREA_TEXT = (
    "Area All solid ground in the area is covered with grease. Each creature "
    "standing on the greasy surface must succeed at a Reflex save or an "
    "Acrobatics check against your spell DC or fall prone. Creatures using an "
    "action to move onto the greasy surface during the spell’s duration must "
    "attempt either a Reflex save or an Acrobatics check to Balance. A "
    "creature that Steps or Crawls doesn’t have to attempt a check or save."
)
_GREASE_TARGET_TEXT = (
    "Target If you Cast the Spell on an unattended object, anyone trying to "
    "pick up the object must succeed at an Acrobatics check or Reflex save "
    "against your spell DC to do so. If you target an attended object, the "
    "creature that has the object must attempt an Acrobatics check or Reflex "
    "save. On a failure, the holder or wielder takes a –2 circumstance penalty "
    "to all checks that involve using the object; on a critical failure, the "
    "holder or wielder releases the item. The object lands in an adjacent "
    "square of the GM’s choice. If you Cast this Spell on a worn object, the "
    "wearer gains a +2 circumstance bonus to Fortitude saves against attempts "
    "to grapple them."
)
_IGNITION_DESCRIPTION = (
    "You snap your fingers and point at a target, which begins to smolder. "
    "Make a spell attack roll against the target’s AC, dealing 2d4 fire damage "
    "on a hit. If the target is within your melee reach, you can choose to make "
    "a melee spell attack with the flame instead of a ranged spell attack, "
    "which increases all the spell’s damage dice to d6s."
)
_IGNITION_CRITICAL_SUCCESS = (
    "The target takes double damage and 1d4 persistent fire damage."
)
_IGNITION_SUCCESS = "The target takes full damage."
_IGNITION_HEIGHTENED = (
    "The initial damage increases by 1d4 and the persistent fire damage on a "
    "critical hit increases by 1d4."
)
_LIGHT_DESCRIPTION = (
    "You create an orb of light that sheds bright light in a 20- foot radius "
    "(and dim light for the next 20 feet) in a color you choose. If you "
    "create the light in the same space as a willing creature, you can attach "
    "the light to the creature, causing it to float near that creature as it "
    "moves. You can Sustain the spell to move the light up to 60 feet; you "
    "can attach or detach it from a creature as part of this movement. You "
    "can Dismiss the spell. If you Cast the Spell while you already have four "
    "light spells active, you must choose one of the existing spells to end."
)
_LIGHT_HEIGHTENED_FOURTH = (
    "The orb sheds light in a 60-foot radius (and dim light for the next 60 "
    "feet)."
)
_TANGLE_VINE_DESCRIPTION = (
    "A vine appears from thin air, flicking from your hand and lashing itself "
    "to the target. Attempt a spell attack roll against the target."
)
_TANGLE_VINE_CRITICAL_SUCCESS = (
    "The target gains the immobilized condition and takes a –10-foot "
    "circumstance penalty to its Speeds for 1 round. It can attempt to Escape "
    "against your spell DC to remove the penalty and the immobilized condition."
)
_TANGLE_VINE_SUCCESS = (
    "The target takes a –10-foot circumstance penalty to its Speeds for 1 "
    "round. It can attempt to Escape against your spell DC to remove the "
    "penalty."
)
_TANGLE_VINE_FAILURE = "The target is unaffected."
_TANGLE_VINE_HEIGHTENED_SECOND = "The effects last for 2 rounds."
_TANGLE_VINE_HEIGHTENED_FOURTH = "The effects last for 1 minute."
_TELEKINETIC_HAND_DESCRIPTION = (
    "You create a floating, magical hand, either invisible or ghostlike, that "
    "grasps the target object and levitates it slowly up to 20 feet in any "
    "direction. When you Sustain the spell, you can move the object an "
    "additional 20 feet. If the object is in the air when the spell ends, "
    "the object falls."
)
_TELEKINETIC_HAND_HEIGHTENED_THIRD = (
    "You can target an unattended object with a Bulk of 1 or less."
)
_TELEKINETIC_HAND_HEIGHTENED_FIFTH = (
    "The range increases to 60 feet, and you can target an unattended object "
    "with a Bulk of 1 or less."
)
_TELEKINETIC_HAND_HEIGHTENED_SEVENTH = (
    "The range increases to 60 feet, and you can target an unattended object "
    "with a Bulk of 2 or less."
)
_FLEET_STEP_DESCRIPTION = (
    "You gain a +30-foot status bonus to your Speed."
)
_PUMMELING_RUBBLE_DESCRIPTION = (
    "A spray of heavy rocks flies through the air in front of you. The rubble "
    "deals 2d4 bludgeoning damage to each creature in the area. Each creature "
    "must attempt a Reflex save."
)
_PUMMELING_RUBBLE_CRITICAL_SUCCESS = "The creature is unaffected."
_PUMMELING_RUBBLE_SUCCESS = "The creature takes half damage."
_PUMMELING_RUBBLE_FAILURE = (
    "The creature takes full damage and is pushed 5 feet away from you."
)
_PUMMELING_RUBBLE_CRITICAL_FAILURE = (
    "The creature takes double damage and is pushed 10 feet away from you."
)
_PUMMELING_RUBBLE_HEIGHTENED = "The damage increases by 2d4."
_CAUSTIC_BLAST_DESCRIPTION = (
    "You fling a large glob of acid that immediately detonates, spraying "
    "nearby creatures. Creatures in the area take 1d8 acid damage with a "
    "basic Reflex save; on a critical failure, the creature also takes 1 "
    "persistent acid damage."
)
_CAUSTIC_BLAST_HEIGHTENED = (
    "The initial damage increases by 1d8, and the persistent damage on a "
    "critical failure increases by 1."
)
_BLESS_DESCRIPTION = (
    "Blessings from beyond help your companions strike true. You and your "
    "allies gain a +1 status bonus to attack rolls while within the "
    "emanation. Once per round on subsequent turns, you can Sustain the spell "
    "to increase the emanation’s radius by 10 feet. Bless can counteract bane."
)
_SOOTHE_DESCRIPTION = (
    "You grace the target’s mind, boosting its mental defenses and healing "
    "its wounds. The target regains 1d10+4 Hit Points when you Cast the Spell "
    "and gains a +2 status bonus to saves against mental effects for the "
    "duration."
)
_SOOTHE_HEIGHTENED = "The amount of healing increases by 1d10+4."
_COURAGEOUS_ANTHEM_DESCRIPTION = (
    "You inspire yourself and your allies with words or tunes of "
    "encouragement. You and all allies in the area gain a +1 status bonus to "
    "attack rolls, damage rolls, and saves against fear effects."
)
_TELEKINETIC_PROJECTILE_DESCRIPTION = (
    "You hurl a loose, unattended object that is within range and that has 1 "
    "Bulk or less at the target. Make a spell attack roll against the target’s "
    "AC. If you hit, you deal 2d6 bludgeoning, piercing, or slashing damage—as "
    "appropriate for the object you hurled. No specific traits or magic "
    "properties of the hurled item affect the attack or the damage."
)
_TELEKINETIC_PROJECTILE_CRITICAL_SUCCESS = "You deal double damage."
_TELEKINETIC_PROJECTILE_SUCCESS = "You deal full damage."
_TELEKINETIC_PROJECTILE_HEIGHTENED = "The damage increases by 1d6."
_SUMMON_INSTRUMENT_DESCRIPTION = (
    "You materialize a handheld musical instrument in your grasp. The "
    "instrument is typical for its type, but it plays for only you. It "
    "vanishes when the spell ends. If you cast summon instrument again, "
    "any instrument you previously summoned disappears."
)
_SUMMON_INSTRUMENT_HEIGHTENED_FIFTH = (
    "The instrument is instead a virtuoso handheld instrument."
)


class SpontaneousSpellcastingSourceError(ValueError):
    """The authenticated carrier violates the reviewed source grammar."""


class SpontaneousSpellcastingLinkError(ValueError):
    """A reviewed Player Core dependency cannot be linked exactly."""


class SpontaneousSpellcastingArtifactError(ValueError):
    """A compiled artifact no longer agrees with its authority."""


def _provider_requirement(
    *,
    rule_id: str,
    locator: str,
    name_sha256: str,
) -> RuleRequirement:
    return RuleRequirement(
        rule_id=rule_id,
        source_id=PLAYER_CORE_SOURCE_ID,
        locator=locator,
        selection_path=(RawMemberStep("Name", 0),),
        expected_selection_sha256=name_sha256,
    )


_PROVIDER_SPECS = (
    {
        "id": "breathe-fire",
        "name": "Breathe Fire",
        "locator": "319.2",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": ("concentrate", "fire", "manipulate"),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (),
        "nameSha256": (
            "a56c31859f48c536f648a0135c5c7bf6d7459b2b1385936fbc3b889fb1615acc"
        ),
    },
    {
        "id": "grease",
        "name": "Grease",
        "locator": "333.8",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": ("concentrate", "manipulate"),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "terrain-effects",
            "balance-checks",
            "prone",
            "map-objects",
            "held-item-targeting",
        ),
        "nameSha256": (
            "487bfde9f15d7ee3bdeefe110f99c10050c9499f2b985fa30179818e6b2a6b7d"
        ),
    },
    {
        "id": "ignition",
        "name": "Ignition",
        "locator": "336.5",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": (
            "attack",
            "cantrip",
            "concentrate",
            "fire",
            "manipulate",
        ),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "spell-attack-map",
            "persistent-damage",
            "persistent-damage-recovery",
        ),
        "nameSha256": (
            "f840cd5c04dc7ca5bbea93b65c682a57fe8fa6be18341a1b31c40288aea31a25"
        ),
    },
    {
        "id": "light",
        "name": "Light",
        "locator": "340.8",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": ("cantrip", "concentrate", "light", "manipulate"),
        "traditions": ("arcane", "divine", "occult", "primal"),
        "runtimeDependencies": (
            "illumination",
            "visibility",
            "effect-attachment",
            "sustain-dismiss",
            "active-effect-limits",
        ),
        "nameSha256": (
            "0b46afa96380156b3a65feffe7bef3ce6c78f6e0db4d90d298b0092107217ee1"
        ),
    },
    {
        "id": "tangle-vine",
        "name": "Tangle Vine",
        "locator": "362.4",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": (
            "attack",
            "cantrip",
            "concentrate",
            "manipulate",
            "plant",
            "wood",
        ),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "spell-attack-map",
            "speed-modifiers",
            "immobilized",
            "escape",
            "duration-expiry",
        ),
        "nameSha256": (
            "fd9e2ed50cd12f4e6a8302de3028109ced352a22609d94f2af6c39cf051b2a1b"
        ),
    },
    {
        "id": "telekinetic-hand",
        "name": "Telekinetic Hand",
        "locator": "362.6",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": ("cantrip", "concentrate", "manipulate"),
        "traditions": ("arcane", "occult"),
        "runtimeDependencies": (
            "map-objects",
            "bulk",
            "object-movement",
            "falling",
            "sustain",
        ),
        "nameSha256": (
            "9abcb435d29003dfff68d4ab43282dcb31e7c0463567a18fc3ee08ce15d71e6b"
        ),
    },
    {
        "id": "charm",
        "name": "Charm",
        "locator": "320.1",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": (
            "concentrate",
            "emotion",
            "incapacitation",
            "manipulate",
            "mental",
            "subtle",
        ),
        "traditions": ("arcane", "occult", "primal"),
        "runtimeDependencies": (
            "attitude-state",
            "hostile-action-lifecycle",
            "social-memory",
        ),
        "nameSha256": (
            "569e495a4dd4b268874f8f81a6301b19960dd19b997571dedce9e9aa6136863b"
        ),
    },
    {
        "id": "command",
        "name": "Command",
        "locator": "321.1",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": (
            "auditory",
            "concentrate",
            "linguistic",
            "manipulate",
            "mental",
        ),
        "traditions": ("arcane", "divine", "occult"),
        "runtimeDependencies": (
            "command-choice",
            "forced-next-turn-action",
            "language-comprehension",
        ),
        "nameSha256": (
            "f400330b9c9c12e8e76f31da65f20827ad405b47242d806a24c241fea2345c2c"
        ),
    },
    {
        "id": "daze",
        "name": "Daze",
        "locator": "322.7",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": (
            "cantrip",
            "concentrate",
            "manipulate",
            "mental",
            "nonlethal",
        ),
        "traditions": ("arcane", "divine", "occult"),
        "runtimeDependencies": (
            "mental-basic-save-damage",
            "stunned",
            "nonlethal-damage",
        ),
        "nameSha256": (
            "30e65b7566eabf49578ad458027935d0ff0e7b28f9e95e1dfac1c5b5a01ac948"
        ),
    },
    {
        "id": "prestidigitation",
        "name": "Prestidigitation",
        "locator": "351.1",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": ("cantrip", "concentrate", "manipulate"),
        "traditions": ("arcane", "divine", "occult", "primal"),
        "runtimeDependencies": (
            "minor-magical-effects",
            "object-targeting",
            "sustain",
        ),
        "nameSha256": (
            "bc91a638735af783e5f5adaeea697f5f1aa4a8076e0c4f9d3169c0131a491ade"
        ),
    },
    {
        "id": "summon-instrument",
        "name": "Summon Instrument",
        "locator": "361.3",
        "rank": 1,
        "kind": "cantrip",
        "actions": "three",
        "traits": ("cantrip", "concentrate", "manipulate"),
        "traditions": ("arcane", "divine", "occult"),
        "runtimeDependencies": (
            "temporary-item-creation",
            "instrument-item-profile",
            "duration-expiry",
        ),
        "nameSha256": (
            "34c6db9b8833ed1e2db21458e2b9a3458c8d9e61e4441144c6e9c732d1d4c01b"
        ),
    },
    {
        "id": "bless",
        "name": "Bless",
        "locator": "318.3",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": ("concentrate", "manipulate", "mental"),
        "traditions": ("divine", "occult"),
        "runtimeDependencies": (),
        "nameSha256": (
            "e2c7bb88822cbcc012afde0b9842583a1401cd2d644bb42aba4de2de8f1e8c7b"
        ),
    },
    {
        "id": "soothe",
        "name": "Soothe",
        "locator": "357.6",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": (
            "concentrate",
            "emotion",
            "healing",
            "manipulate",
            "mental",
        ),
        "traditions": ("occult",),
        "runtimeDependencies": (),
        "nameSha256": (
            "922baa0dfc7fdf226b0b4816ceffd3bc44b803271871df8651d73f36bee642e7"
        ),
    },
    {
        "id": "figment",
        "name": "Figment",
        "locator": "331.6",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": ("cantrip", "concentrate", "illusion", "manipulate"),
        "traditions": ("arcane", "occult"),
        "runtimeDependencies": (
            "illusion-state",
            "create-a-diversion",
            "disbelief",
            "sustain",
        ),
        "nameSha256": (
            "5c8ca8a64538333fd9bfc09059563da53e8132f769a8a59b72afb70c1e09c32a"
        ),
    },
    {
        "id": "courageous-anthem",
        "name": "Courageous Anthem",
        "locator": "370.5",
        "rank": 1,
        "kind": "cantrip",
        "actions": "single",
        "traits": (
            "uncommon",
            "bard",
            "cantrip",
            "composition",
            "concentrate",
            "emotion",
            "mental",
        ),
        "traditions": (),
        "runtimeDependencies": (),
        "nameSha256": (
            "4f578f471a60152460e2557597b3ebd1a06c4170bac0226753d60f2da7e316f9"
        ),
    },
    {
        "id": "message",
        "name": "Message",
        "locator": "343.2",
        "rank": 1,
        "kind": "cantrip",
        "actions": "single",
        "traits": (
            "auditory",
            "cantrip",
            "concentrate",
            "illusion",
            "linguistic",
            "mental",
            "subtle",
        ),
        "traditions": ("arcane", "divine", "occult"),
        "runtimeDependencies": (
            "communication-intent",
            "target-reaction-response",
            "visibility",
        ),
        "nameSha256": (
            "be1af94c8c00110d748345ea5e25cfc3aca39055ab9101ab1d8d551928445819"
        ),
    },
    {
        "id": "telekinetic-projectile",
        "name": "Telekinetic Projectile",
        "locator": "363.2",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": ("attack", "cantrip", "concentrate", "manipulate"),
        "traditions": ("arcane", "occult"),
        "runtimeDependencies": (
            "movable-object-profile",
            "unattended-object-state",
            "object-bulk",
            "object-position-and-line-of-effect",
        ),
        "nameSha256": (
            "a0dd8ff669980ea35a25dabb6b22323363591221ede928b1b1950e5506fe4752"
        ),
    },
    {
        "id": "fleet-step",
        "name": "Fleet Step",
        "locator": "332.1",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": ("concentrate", "manipulate"),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "typed-movement-modifiers",
            "land-speed-status-bonus",
            "duration-expiry",
        ),
        "nameSha256": (
            "3745e730244d45157c563a7b177c561317321e11d87f4cccce8256d88aafe8ae"
        ),
    },
    {
        "id": "heal",
        "name": "Heal",
        "locator": "335.2",
        "rank": 1,
        "kind": "spell",
        "actions": "single-to-three",
        "traits": ("healing", "manipulate", "vitality"),
        "traditions": ("divine", "primal"),
        "runtimeDependencies": (
            "variable-action-spellcasting",
            "vitality-healing-and-damage",
            "living-and-undead-targeting",
            "emanation-targeting",
        ),
        "nameSha256": (
            "c03c41626b1b492ff6281b718cb697d25612099a5378793779d096c1e551040b"
        ),
    },
    {
        "id": "pummeling-rubble",
        "name": "Pummeling Rubble",
        "locator": "351.4",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": ("concentrate", "earth", "manipulate"),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "forced-movement",
            "cone-push",
        ),
        "nameSha256": (
            "c4737c410dde66c66cf92593a21513d2cd401eb8ce5b472dd95794fff16a6d98"
        ),
    },
    {
        "id": "runic-weapon",
        "name": "Runic Weapon",
        "locator": "354.3",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": ("concentrate", "manipulate"),
        "traditions": ("arcane", "divine", "occult", "primal"),
        "runtimeDependencies": (
            "temporary-equipment-effects",
            "temporary-weapon-runes",
        ),
        "nameSha256": (
            "14338e04a51c74fcf7e02582da43bb7cbecc4119bec9ba2b28db49ceb1a3e8d5"
        ),
    },
    {
        "id": "caustic-blast",
        "name": "Caustic Blast",
        "locator": "319.6",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": ("acid", "cantrip", "concentrate", "manipulate"),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "ranged-burst-geometry",
            "area-cover",
            "fixed-persistent-damage",
        ),
        "nameSha256": (
            "2bc03b85daacfd40169e011cfc6ad70854b1efd7ee76cb9b2541a926985cda30"
        ),
    },
    {
        "id": "detect-magic",
        "name": "Detect Magic",
        "locator": "323.2",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": ("cantrip", "concentrate", "detection", "manipulate"),
        "traditions": ("arcane", "divine", "occult", "primal"),
        "runtimeDependencies": (
            "magical-aura-state",
            "exploration-detection",
        ),
        "nameSha256": (
            "80962ed607dc404be19160c40ac8a420916a5f1a16bd19a2e77e21dfd8d5cff2"
        ),
    },
    {
        "id": "know-the-way",
        "name": "Know the Way",
        "locator": "340.5",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": ("cantrip", "concentrate", "detection", "manipulate"),
        "traditions": ("divine", "occult", "primal"),
        "runtimeDependencies": (
            "navigation-state",
            "location-memory",
            "campaign-time",
        ),
        "nameSha256": (
            "78bff3eaf945add8b7696d2534fbd6f0a7d1b5d73603e3f261d2daf8f6db2c1e"
        ),
    },
)

_PROVIDER_REQUIREMENTS = tuple(
    _provider_requirement(
        rule_id=f"spell-provider:{spec['id']}",
        locator=spec["locator"],
        name_sha256=spec["nameSha256"],
    )
    for spec in _PROVIDER_SPECS
)

_GOVERNING_REQUIREMENTS = (
    RuleRequirement(
        rule_id="spell-slots",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="297.3",
        selection_path=(RawMemberStep("~.p", 0),),
        expected_selection_sha256=(
            "8edeba1c0ac03565b5a86cfb88da9c062d496c6067c2eb8a2d89c3c830a55dd2"
        ),
    ),
    RuleRequirement(
        rule_id="spontaneous-spells",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="297.5",
        expected_block_sha256=(
            "c16191bcfbe5f6f14ebe6dc501aa0dfe02ced112d299fc971acd595bf11bcf43"
        ),
    ),
    RuleRequirement(
        rule_id="cantrips",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="298.1",
        expected_block_sha256=(
            "636a20b16e1981ef23673864f2eeb68471083cc01847580a193b80d9d9fecd20"
        ),
    ),
    RuleRequirement(
        rule_id="casting-spells",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="299.2",
        selection_path=(RawMemberStep("~.p", 2),),
        expected_selection_sha256=(
            "74d140deffffd2384d1ef61f1a99873e4188e603eeb4fbc2e6d897b1d283460b"
        ),
    ),
    RuleRequirement(
        rule_id="areas",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="300.7",
        expected_block_sha256=(
            "b994bfd4a73f123855157c234d88c7a0b1059347f4882e9c0d380adba2108012"
        ),
    ),
    RuleRequirement(
        rule_id="basic-saving-throws",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="302.8",
        expected_block_sha256=(
            "2515e9fe3148c83ebbcf92e8744e195e73c69ca9391c72e1536406de1d24bc48"
        ),
    ),
)

_DC_FROM_MODIFIER_REQUIREMENT = RuleRequirement(
    rule_id="dc-from-modifier",
    source_id=PLAYER_CORE_SOURCE_ID,
    locator="401.2",
    expected_block_sha256=(
        "9ff024bc6158c6efc6b6bdc906ee9a00261adfaae0e80f41e1a09bbd7daafd09"
    ),
)

_MOVEMENT_TYPE_REQUIREMENTS = (
    RuleRequirement(
        rule_id="movement-types",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="420.3",
        expected_block_sha256=(
            "db3d691feb3874b2df5f15c45c917bc1f4291b1c6b0c0d97c2139c91cfd11f02"
        ),
    ),
    RuleRequirement(
        rule_id="land-speed",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="420.4",
        expected_block_sha256=(
            "625d62f213cadf80d6dd6bff2a2b57ea558174462211db5b36f1d99891fa4433"
        ),
    ),
)

_DURATION_REQUIREMENT = RuleRequirement(
    rule_id="duration",
    source_id=PLAYER_CORE_SOURCE_ID,
    locator="426.2",
    expected_block_sha256=(
        "abae8acd3b37239c6a931639213e2a82dc7013498d3577007064f9cc1076bcc0"
    ),
)

_ACTION_VARIANTS = {
    "single": (1,),
    "two": (2,),
    "three": (3,),
    "single-to-three": (1, 2, 3),
}


def _unique_member(
    value: RawSourceObject,
    key: str,
    *,
    error_type: type[ValueError],
) -> RawSourceMember:
    if type(value) is not RawSourceObject or type(key) is not str:
        raise TypeError("exact raw member lookup requires exact types")
    matches = tuple(
        member
        for member in value.members
        if type(member) is RawSourceMember and member.key == key
    )
    if len(matches) != 1:
        raise error_type(
            f"source requires one exact {key!r} member; found {len(matches)}"
        )
    return matches[0]


def _exact_string_array(
    value: object,
    *,
    label: str,
    error_type: type[ValueError],
) -> tuple[str, ...]:
    if type(value) is not RawSourceArray:
        raise error_type(f"{label} must be an exact source array")
    if any(type(item) is not str for item in value.items):
        raise error_type(f"{label} must contain exact strings")
    return tuple(value.items)


def _parse_italic_list(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not str:
        raise SpontaneousSpellcastingSourceError(
            f"{label} must be exact marked-up text"
        )
    chunks = value.split(", ")
    names = []
    for chunk in chunks:
        citation_free = _CITATION_RE.sub("", chunk)
        match = _ITALIC_SPELL_RE.fullmatch(citation_free)
        if match is None:
            raise SpontaneousSpellcastingSourceError(
                f"{label} has wrong casing, spacing, citation, or italic "
                "markup"
            )
        names.append(match.group("name"))
    return tuple(names)


def _parse_carrier(
    consumer: VerifiedSourceSelection,
    authority: SourceAuthorityAdapter,
) -> dict[str, Any]:
    try:
        verified = authority.validate_selection(consumer)
    except SourceAuthorityError as failure:
        raise SpontaneousSpellcastingLinkError(
            "spellcasting carrier does not belong to this authority"
        ) from failure
    address = verified.address
    profile = _CARRIER_PROFILES.get(verified.carrier.locator)
    if (
        verified.carrier.source_id != MONSTER_CORE_SOURCE_ID
        or profile is None
        or authority.toc_label(
            MONSTER_CORE_SOURCE_ID,
            verified.carrier.locator,
        )
        != profile["label"]
        or not address.carrier_path
        or address.carrier_path[-1].raw_key != "^.creature"
        or len(address.selection_path) != 1
        or address.selection_path[0].raw_key != _CARRIER_FIELD
        or address.span is not None
        or verified.carrier.raw_block.values("Name")
        != (profile["label"],)
        or verified.raw_member is None
        or verified.raw_member.key != _CARRIER_FIELD
        or verified.selection_sha256 != profile["selectionSha256"]
    ):
        raise SpontaneousSpellcastingSourceError(
            "carrier is not a reviewed creature Spellcasting selection"
        )
    spellcasting = verified.selected_value
    if type(spellcasting) is not RawSourceObject:
        raise SpontaneousSpellcastingSourceError(
            "Spellcasting must be one exact source object"
        )
    if tuple(member.key for member in spellcasting.members) != (
        profile["header"],
    ):
        raise SpontaneousSpellcastingSourceError(
            "Spellcasting requires the exact reviewed casting header"
        )
    casting_member = _unique_member(
        spellcasting,
        profile["header"],
        error_type=SpontaneousSpellcastingSourceError,
    )
    casting = casting_member.value
    if type(casting) is not RawSourceObject:
        raise SpontaneousSpellcastingSourceError(
            "casting entry must be one exact source object"
        )
    expected_fields = (
        ("DC", "Attack", "Entries")
        if profile["attack"] is not None
        else ("DC", "Entries")
    )
    if tuple(member.key for member in casting.members) != expected_fields:
        raise SpontaneousSpellcastingSourceError(
            "casting entry fields or order differ from reviewed source"
        )
    dc = _unique_member(
        casting,
        "DC",
        error_type=SpontaneousSpellcastingSourceError,
    ).value
    attack = (
        _unique_member(
            casting,
            "Attack",
            error_type=SpontaneousSpellcastingSourceError,
        ).value
        if profile["attack"] is not None
        else None
    )
    entries = _unique_member(
        casting,
        "Entries",
        error_type=SpontaneousSpellcastingSourceError,
    ).value
    expected_dc = str(profile["dc"])
    if type(dc) is not str or dc != expected_dc:
        raise SpontaneousSpellcastingSourceError(
            "casting DC differs from exact authored text"
        )
    parsed_dc = parse_decimal_integer(dc)
    if parsed_dc != profile["dc"]:
        raise SpontaneousSpellcastingSourceError(
            "casting DC is not the authored positive integer"
        )
    expected_attack = profile["attack"]
    if expected_attack is not None and (
        type(attack) is not str
        or attack != f"{expected_attack:+d}"
    ):
        raise SpontaneousSpellcastingSourceError(
            "spell attack differs from exact authored text"
        )
    parsed_attack = (
        parse_decimal_integer(attack)
        if type(attack) is str
        else None
    )
    if parsed_attack != expected_attack:
        raise SpontaneousSpellcastingSourceError(
            "spell attack is not the authored signed integer"
        )
    if type(entries) is not RawSourceObject:
        raise SpontaneousSpellcastingSourceError(
            "casting Entries must be one exact source object"
        )
    expected_slot_count = len(profile["slots"])
    if len(entries.members) != expected_slot_count + 1:
        raise SpontaneousSpellcastingSourceError(
            "casting entries contain missing, duplicate, or unreviewed groups"
        )
    specs_by_id = {spec["id"]: spec for spec in _PROVIDER_SPECS}
    parsed_slots = []
    for slot_member, (rank, maximum, spell_ids) in zip(
        entries.members[:-1],
        profile["slots"],
        strict=True,
    ):
        slot_match = _SLOT_ENTRY_RE.fullmatch(slot_member.key)
        parsed_rank = (
            _RANKS.get(slot_match.group("rank"))
            if slot_match is not None
            else None
        )
        parsed_maximum = (
            parse_decimal_integer(slot_match.group("count"))
            if slot_match is not None
            else None
        )
        expected_unit = "slot" if maximum == 1 else "slots"
        if (
            slot_match is None
            or parsed_rank != rank
            or parsed_maximum != maximum
            or slot_match.group("unit") != expected_unit
        ):
            raise SpontaneousSpellcastingSourceError(
                "slot rank, maximum, or pluralization differs from source"
            )
        names = _parse_italic_list(
            slot_member.value,
            f"rank-{rank} spell list",
        )
        expected_names = tuple(
            str(specs_by_id[spell_id]["name"]).casefold()
            for spell_id in spell_ids
        )
        if names != expected_names:
            raise SpontaneousSpellcastingSourceError(
                "slot spell list contains missing, reordered, or "
                "unreviewed spells"
            )
        parsed_slots.append(
            {
                "rank": rank,
                "maximum": maximum,
                "spellIds": list(spell_ids),
            }
        )
    cantrip_member = entries.members[-1]
    cantrip_match = _CANTRIP_ENTRY_RE.fullmatch(cantrip_member.key)
    cantrip_rank, cantrip_ids = profile["cantrips"]
    if (
        cantrip_match is None
        or _RANKS.get(cantrip_match.group("rank")) != cantrip_rank
    ):
        raise SpontaneousSpellcastingSourceError(
            "cantrip rank entry has invalid grammar"
        )
    cantrip_names = _parse_italic_list(
        cantrip_member.value,
        "cantrip list",
    )
    expected_cantrip_names = tuple(
        str(specs_by_id[spell_id]["name"]).casefold()
        for spell_id in cantrip_ids
    )
    if cantrip_names != expected_cantrip_names:
        raise SpontaneousSpellcastingSourceError(
            "cantrip list contains missing, reordered, or unreviewed spells"
        )
    return {
        "consumer": verified,
        "profile": profile,
        "dc": parsed_dc,
        "attack": parsed_attack,
        "slots": parsed_slots,
        "cantrips": {
            "rank": cantrip_rank,
            "spellIds": list(cantrip_ids),
        },
    }


def _provider_block(
    authority: SourceAuthorityAdapter,
    requirement: RuleRequirement,
    spec: dict[str, Any],
    *,
    casting_tradition: str,
    explicit_repertoire_grant: bool,
) -> tuple[VerifiedSourceSelection, VerifiedRuleReceipt]:
    try:
        identity = authority.resolve_rule(requirement)
        provider = authority.resolve(
            authority.address(
                source_id=PLAYER_CORE_SOURCE_ID,
                locator=spec["locator"],
            )
        )
        authority.validate_rule(identity)
        authority.validate_selection(provider)
        label = authority.toc_label(
            PLAYER_CORE_SOURCE_ID,
            spec["locator"],
        )
    except SourceAuthorityError as failure:
        raise SpontaneousSpellcastingLinkError(
            f"spell provider cannot resolve exactly: {spec['id']}"
        ) from failure
    if label != spec["name"]:
        raise SpontaneousSpellcastingLinkError(
            f"spell provider ToC label mismatch: {spec['id']}"
        )
    value = provider.selected_value
    if type(value) is not RawSourceObject or provider.raw_member is not None:
        raise SpontaneousSpellcastingLinkError(
            f"spell provider must be one exact block: {spec['id']}"
        )
    keys = tuple(member.key for member in value.members)
    if len(keys) != len(set(keys)):
        raise SpontaneousSpellcastingLinkError(
            f"spell provider has duplicate root fields: {spec['id']}"
        )
    name = _unique_member(
        value,
        "Name",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    rank = _unique_member(
        value,
        "Rank",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    kind = _unique_member(
        value,
        "Kind",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    actions = _unique_member(
        value,
        "Actions",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    traits = _exact_string_array(
        _unique_member(
            value,
            "Traits",
            error_type=SpontaneousSpellcastingLinkError,
        ).value,
        label=f"{spec['id']} Traits",
        error_type=SpontaneousSpellcastingLinkError,
    )
    tradition_members = tuple(
        member for member in value.members if member.key == "Traditions"
    )
    if spec["traditions"]:
        if len(tradition_members) != 1:
            raise SpontaneousSpellcastingLinkError(
                f"{spec['id']} Traditions are missing or duplicated"
            )
        traditions = _exact_string_array(
            tradition_members[0].value,
            label=f"{spec['id']} Traditions",
            error_type=SpontaneousSpellcastingLinkError,
        )
    else:
        if tradition_members:
            raise SpontaneousSpellcastingLinkError(
                f"{spec['id']} unexpectedly declares Traditions"
            )
        traditions = ()
    if (
        type(name) is not str
        or name != spec["name"]
        or type(rank) is not int
        or rank != spec["rank"]
        or type(kind) is not str
        or kind != spec["kind"]
        or type(actions) is not str
        or actions != spec["actions"]
        or traits != spec["traits"]
        or traditions != spec["traditions"]
        or (
            casting_tradition not in traditions
            and not explicit_repertoire_grant
        )
    ):
        raise SpontaneousSpellcastingLinkError(
            f"spell provider semantic fields mismatch: {spec['id']}"
        )
    if (
        explicit_repertoire_grant
        and casting_tradition in traditions
    ):
        raise SpontaneousSpellcastingLinkError(
            f"spell provider does not require an explicit repertoire "
            f"grant: {spec['id']}"
        )
    if identity.selection.selected_value != name:
        raise SpontaneousSpellcastingLinkError(
            f"spell provider identity does not bind its Name: {spec['id']}"
        )
    return provider, identity


def _breathe_fire_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Breathe Fire provider is not an exact block"
        )
    area = _unique_member(
        value,
        "Area",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    defense = _unique_member(
        value,
        "Defense",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    description = _unique_member(
        value,
        "Description",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if area != "15-foot cone" or defense != "basic Reflex":
        raise SpontaneousSpellcastingLinkError(
            "Breathe Fire area or defense differs from reviewed source"
        )
    if (
        type(description) is not RawSourceObject
        or tuple(member.key for member in description.members) != ("~.p",)
        or description.members[0].value != _BREATHE_FIRE_PARAGRAPH
    ):
        raise SpontaneousSpellcastingLinkError(
            "Breathe Fire reviewed damage paragraph differs"
        )
    return {
        "type": "cone-basic-save-damage",
        "area": {
            "shape": "cone",
            "distanceFeet": 15,
            "origin": "caster",
        },
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dcSource": "casting",
        },
        "damage": {
            "dice": {"count": 2, "size": 6},
            "type": "fire",
        },
    }


def _grease_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    """Compile only the reviewed area mode and preserve the object deferral."""

    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Grease provider is not an exact block"
        )
    expected_scalars = {
        "Range": "30 feet",
        "Area": "4 contiguous 5-foot squares or",
        "Targets": "1 object of 1 Bulk or less",
        "Duration": "1 minute",
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Grease reviewed {key} differs"
            )
    description = _unique_member(
        value,
        "Description",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        type(description) is not RawSourceObject
        or tuple(member.key for member in description.members)
        != ("~.p", "~.ul")
        or description.members[0].value != _GREASE_INTRODUCTION
        or type(description.members[1].value) is not RawSourceArray
        or description.members[1].value.items
        != (_GREASE_AREA_TEXT, _GREASE_TARGET_TEXT)
    ):
        raise SpontaneousSpellcastingLinkError(
            "Grease reviewed effect text differs"
        )
    return {
        "type": "grease-area-control",
        "rangeFeet": 30,
        "area": {
            "shape": "contiguous-squares",
            "squareCount": 4,
            "squareSizeFeet": 5,
            "contiguity": "orthogonal",
            "surface": "solid-ground",
        },
        "initialCheck": {
            "methods": ["reflex", "acrobatics"],
            "dcSource": "casting",
            "failureEffect": "prone",
        },
        "entryCheck": {
            "trigger": "action-moves-onto-surface",
            "methods": ["reflex", "acrobatics"],
            "dcSource": "casting",
            "failureEffect": "prone",
            "runtimeSupportedActions": ["stride"],
            "exemptMovementActions": ["step", "crawl"],
            "deferredMovementActions": [
                "other-move-actions",
                "compound-move-activities",
            ],
        },
        "duration": {
            "rounds": 10,
            "source": "1 minute",
        },
        "deferredModes": ["object-target"],
    }


def _ignition_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    """Compile the reviewed rank-1 melee and ranged spell-attack modes."""

    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Ignition provider is not an exact block"
        )
    expected_scalars = {
        "Range": "30 feet",
        "Targets": "1 creature",
        "Defense": "AC",
        "Critical Success": _IGNITION_CRITICAL_SUCCESS,
        "Success": _IGNITION_SUCCESS,
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Ignition reviewed {key} differs"
            )
    description = _unique_member(
        value,
        "Description",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        type(description) is not RawSourceObject
        or tuple(member.key for member in description.members) != ("~.p",)
        or description.members[0].value != _IGNITION_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("+1",)
        or heightened.members[0].value != _IGNITION_HEIGHTENED
    ):
        raise SpontaneousSpellcastingLinkError(
            "Ignition reviewed effect text differs"
        )
    return {
        "type": "spell-attack-damage",
        "rangeFeet": 30,
        "target": "one-creature",
        "defense": "armor-class",
        "attackModes": [
            {
                "mode": "ranged",
                "damage": {
                    "dice": {"count": 2, "size": 4},
                    "type": "fire",
                },
            },
            {
                "mode": "melee",
                "requiresTargetWithinMeleeReach": True,
                "damage": {
                    "dice": {"count": 2, "size": 6},
                    "type": "fire",
                },
            },
        ],
        "outcomes": {
            "criticalSuccess": {
                "initialDamage": "double",
                "persistentDamage": {
                    "dice": {"count": 1, "size": 4},
                    "type": "fire",
                },
            },
            "success": {"initialDamage": "full"},
            "failure": {"initialDamage": "none"},
        },
        "heightened": {
            "everyRanks": 1,
            "initialDamageDice": {"count": 1, "size": 4},
            "criticalPersistentDamageDice": {"count": 1, "size": 4},
        },
    }


def _light_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    """Compile Light's persistent movable-orb lifecycle."""

    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Light provider is not an exact block"
        )
    expected_scalars = {
        "Range": "120 feet",
        "Duration": "until your next daily preparations",
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Light reviewed {key} differs"
            )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        _description_paragraph(provider, spell_name="Light")
        != _LIGHT_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("4th",)
        or heightened.members[0].value != _LIGHT_HEIGHTENED_FOURTH
    ):
        raise SpontaneousSpellcastingLinkError(
            "Light reviewed effect text differs"
        )
    return {
        "type": "movable-light-orb",
        "rangeFeet": 120,
        "emission": {
            "brightRadiusFeet": 20,
            "dimOuterRadiusFeet": 40,
        },
        "attachment": {
            "initial": "optional-willing-creature-in-origin-square",
            "followsCreature": True,
        },
        "sustain": {
            "actionCost": 1,
            "traits": ["concentrate"],
            "maximumMovementFeet": 60,
            "canAttachOrDetach": True,
        },
        "dismiss": {
            "actionCost": 1,
            "traits": ["concentrate"],
        },
        "duration": "until-next-daily-preparations",
        "activeLimit": 4,
        "heightened": {
            "4th": {
                "emission": {
                    "brightRadiusFeet": 60,
                    "dimOuterRadiusFeet": 120,
                }
            }
        },
    }


def _tangle_vine_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    """Compile the reviewed rank-1 spell-attack control outcomes."""

    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Tangle Vine provider is not an exact block"
        )
    expected_scalars = {
        "Range": "30 feet",
        "Targets": "1 creature",
        "Defense": "AC",
        "Critical Success": _TANGLE_VINE_CRITICAL_SUCCESS,
        "Success": _TANGLE_VINE_SUCCESS,
        "Failure": _TANGLE_VINE_FAILURE,
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Tangle Vine reviewed {key} differs"
            )
    description = _unique_member(
        value,
        "Description",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        type(description) is not RawSourceObject
        or tuple(member.key for member in description.members) != ("~.p",)
        or description.members[0].value != _TANGLE_VINE_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members)
        != ("2nd", "4th")
        or heightened.members[0].value != _TANGLE_VINE_HEIGHTENED_SECOND
        or heightened.members[1].value != _TANGLE_VINE_HEIGHTENED_FOURTH
    ):
        raise SpontaneousSpellcastingLinkError(
            "Tangle Vine reviewed effect text differs"
        )
    movement_modifiers = [{
        "statistic": "speed",
        "scope": {"kind": "all-speeds"},
        "type": "circumstance",
        "valueFeet": -10,
    }]
    duration = {"rounds": 1}
    escape = {
        "dcSource": "casting",
        "removes": ["speed-penalty", "immobilized"],
    }
    return {
        "type": "spell-attack-speed-control",
        "rangeFeet": 30,
        "target": "one-creature",
        "defense": "armor-class",
        "attackMode": "ranged",
        "outcomes": {
            "criticalSuccess": {
                "immobilized": True,
                "movementModifiers": movement_modifiers,
                "duration": duration,
                "escape": escape,
            },
            "success": {
                "immobilized": False,
                "movementModifiers": movement_modifiers,
                "duration": duration,
                "escape": {
                    "dcSource": "casting",
                    "removes": ["speed-penalty"],
                },
            },
            "failure": {"unaffected": True},
        },
        "heightened": {
            "2nd": {"rounds": 2},
            "4th": {"minutes": 1},
        },
    }


def _description_paragraph(
    provider: VerifiedSourceSelection,
    *,
    spell_name: str,
) -> str:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            f"{spell_name} provider is not an exact block"
        )
    description = _unique_member(
        value,
        "Description",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        type(description) is not RawSourceObject
        or tuple(member.key for member in description.members) != ("~.p",)
        or type(description.members[0].value) is not str
    ):
        raise SpontaneousSpellcastingLinkError(
            f"{spell_name} description is not one exact paragraph"
        )
    return description.members[0].value


def _fleet_step_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    """Compile Fleet Step as a typed land-Speed modifier."""

    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Fleet Step provider is not an exact block"
        )
    if (
        _unique_member(
            value,
            "Duration",
            error_type=SpontaneousSpellcastingLinkError,
        ).value
        != "1 minute"
        or _description_paragraph(provider, spell_name="Fleet Step")
        != _FLEET_STEP_DESCRIPTION
    ):
        raise SpontaneousSpellcastingLinkError(
            "Fleet Step reviewed duration or effect text differs"
        )
    return {
        "type": "self-movement-modifier",
        "target": "self",
        "movementModifiers": [
            {
                "statistic": "speed",
                "scope": {
                    "kind": "named-speed",
                    "movementMode": "land",
                },
                "type": "status",
                "valueFeet": 30,
            }
        ],
        "duration": {
            "rounds": 10,
            "source": "1 minute",
        },
    }


def _caustic_blast_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    """Compile the exact vertex-origin burst and acid-damage contract."""

    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Caustic Blast provider is not an exact block"
        )
    expected_scalars = {
        "Range": "30 feet",
        "Area": "5-foot burst",
        "Defense": "basic Reflex",
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Caustic Blast reviewed {key} differs"
            )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        _description_paragraph(provider, spell_name="Caustic Blast")
        != _CAUSTIC_BLAST_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("+2",)
        or heightened.members[0].value != _CAUSTIC_BLAST_HEIGHTENED
    ):
        raise SpontaneousSpellcastingLinkError(
            "Caustic Blast reviewed damage or heightening text differs"
        )
    return {
        "type": "ranged-burst-basic-save-damage",
        "rangeFeet": 30,
        "area": {
            "shape": "burst",
            "radiusFeet": 5,
            "origin": {"kind": "selected-grid-vertex"},
        },
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dcSource": "casting",
        },
        "damage": {
            "dice": {"count": 1, "size": 8},
            "type": "acid",
        },
        "outcomes": {
            "criticalFailure": {
                "persistentDamage": {
                    "flatAmount": 1,
                    "type": "acid",
                },
            },
        },
        "heightened": {
            "everyRanks": 2,
            "initialDamageDice": {"count": 1, "size": 8},
            "criticalPersistentDamageFlatAmount": 1,
        },
    }


def _pummeling_rubble_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    """Compile the reviewed cone damage and outcome-specific Push contract."""

    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Pummeling Rubble provider is not an exact block"
        )
    expected_scalars = {
        "Area": "15-foot cone",
        "Defense": "Reflex",
        "Critical Success": _PUMMELING_RUBBLE_CRITICAL_SUCCESS,
        "Success": _PUMMELING_RUBBLE_SUCCESS,
        "Failure": _PUMMELING_RUBBLE_FAILURE,
        "Critical Failure": _PUMMELING_RUBBLE_CRITICAL_FAILURE,
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Pummeling Rubble reviewed {key} differs"
            )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        _description_paragraph(
            provider,
            spell_name="Pummeling Rubble",
        )
        != _PUMMELING_RUBBLE_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("+1",)
        or heightened.members[0].value
        != _PUMMELING_RUBBLE_HEIGHTENED
    ):
        raise SpontaneousSpellcastingLinkError(
            "Pummeling Rubble reviewed damage or heightening text differs"
        )
    return {
        "type": "cone-basic-save-damage",
        "area": {
            "shape": "cone",
            "distanceFeet": 15,
            "origin": "caster",
        },
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dcSource": "casting",
        },
        "damage": {
            "dice": {"count": 2, "size": 4},
            "type": "bludgeoning",
        },
        "outcomes": {
            "failure": {"pushFeet": 5},
            "criticalFailure": {"pushFeet": 10},
        },
        "heightened": {
            "everyRanks": 1,
            "damageDice": {"count": 2, "size": 4},
        },
    }


def _bless_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Bless provider is not an exact block"
        )
    if (
        _unique_member(
            value,
            "Area",
            error_type=SpontaneousSpellcastingLinkError,
        ).value
        != "15-foot emanation"
        or _unique_member(
            value,
            "Duration",
            error_type=SpontaneousSpellcastingLinkError,
        ).value
        != "1 minute"
        or _description_paragraph(provider, spell_name="Bless")
        != _BLESS_DESCRIPTION
    ):
        raise SpontaneousSpellcastingLinkError(
            "Bless reviewed area, duration, or effect text differs"
        )
    return {
        "type": "emanation-status-aura",
        "area": {
            "shape": "emanation",
            "radiusFeet": 15,
            "origin": "caster",
        },
        "recipients": ["caster", "allies"],
        "bonuses": [
            {
                "type": "status",
                "value": 1,
                "appliesTo": "attack-rolls",
            }
        ],
        "duration": {"rounds": 10, "source": "1 minute"},
        "deferredModes": [
            "sustain-increase-radius",
            "counteract-bane",
        ],
    }


def _soothe_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Soothe provider is not an exact block"
        )
    expected_scalars = {
        "Range": "30 feet",
        "Targets": "1 willing creature",
        "Duration": "1 minute",
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Soothe reviewed {key} differs"
            )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        _description_paragraph(provider, spell_name="Soothe")
        != _SOOTHE_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("+1",)
        or heightened.members[0].value != _SOOTHE_HEIGHTENED
    ):
        raise SpontaneousSpellcastingLinkError(
            "Soothe reviewed effect or heightened text differs"
        )
    return {
        "type": "target-healing-and-save-bonus",
        "rangeFeet": 30,
        "target": "one-willing-creature",
        "healing": {
            "dice": {"count": 1, "size": 10},
            "modifier": 4,
        },
        "saveBonus": {
            "type": "status",
            "value": 2,
            "againstTraits": ["mental"],
        },
        "duration": {"rounds": 10, "source": "1 minute"},
        "heightened": {
            "everyRanks": 1,
            "healingDice": {"count": 1, "size": 10},
            "healingModifier": 4,
        },
    }


def _heal_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Heal provider is not an exact block"
        )
    if (
        _unique_member(
            value,
            "Range",
            error_type=SpontaneousSpellcastingLinkError,
        ).value
        != "varies"
        or _unique_member(
            value,
            "Targets",
            error_type=SpontaneousSpellcastingLinkError,
        ).value
        != "1 willing living creature or 1 undead creature"
        or _description_paragraph(provider, spell_name="Heal")
        != _HEAL_DESCRIPTION
    ):
        raise SpontaneousSpellcastingLinkError(
            "Heal reviewed targets, range, or effect text differs"
        )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("+1",)
        or heightened.members[0].value != _HEAL_HEIGHTENED
    ):
        raise SpontaneousSpellcastingLinkError(
            "Heal reviewed heightening text differs"
        )
    return {
        "type": "variable-vitality-healing-and-damage",
        "vitalityAmount": {
            "dice": {"count": 1, "size": 8},
        },
        "actionForms": {
            "1": {
                "actionCost": 1,
                "additionalTraits": [],
                "range": {
                    "kind": "touch",
                    "maximumDistanceFeet": 5,
                },
                "target": (
                    "one-willing-living-or-one-undead-creature"
                ),
            },
            "2": {
                "actionCost": 2,
                "additionalTraits": ["concentrate"],
                "range": {
                    "kind": "distance",
                    "maximumDistanceFeet": 30,
                },
                "target": (
                    "one-willing-living-or-one-undead-creature"
                ),
                "livingHealingModifier": 8,
            },
            "3": {
                "actionCost": 3,
                "additionalTraits": ["concentrate"],
                "area": {
                    "shape": "emanation",
                    "radiusFeet": 30,
                    "origin": "caster",
                },
                "targets": ["all-living", "all-undead"],
            },
        },
        "undeadSavingThrow": {
            "type": "fortitude",
            "basic": True,
            "dcSource": "casting",
        },
        "heightened": {
            "everyRanks": 1,
            "vitalityDice": {"count": 1, "size": 8},
            "twoActionLivingHealingModifier": 8,
        },
    }


def _runic_weapon_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Runic Weapon provider is not an exact block"
        )
    expected_scalars = {
        "Range": "touch",
        "Targets": (
            "1 weapon that is unattended or wielded by a willing creature"
        ),
        "Duration": "1 minute",
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Runic Weapon reviewed {key} differs"
            )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        _description_paragraph(
            provider,
            spell_name="Runic Weapon",
        )
        != _RUNIC_WEAPON_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members)
        != ("6th", "9th")
        or heightened.members[0].value
        != _RUNIC_WEAPON_HEIGHTENED_SIXTH
        or heightened.members[1].value
        != _RUNIC_WEAPON_HEIGHTENED_NINTH
    ):
        raise SpontaneousSpellcastingLinkError(
            "Runic Weapon reviewed effect or heightening text differs"
        )
    return {
        "type": "target-weapon-striking-runes",
        "range": {
            "kind": "touch",
            "maximumDistanceFeet": 5,
        },
        "target": (
            "one-weapon-unattended-or-wielded-by-willing-creature"
        ),
        "attackItemBonus": 1,
        "damageDiceCount": 2,
        "duration": {
            "rounds": 10,
            "source": "1 minute",
        },
        "heightened": {
            "6th": {
                "potencyBonus": 2,
                "strikingRune": "greater",
            },
            "9th": {
                "potencyBonus": 3,
                "strikingRune": "major",
            },
        },
    }


def _courageous_anthem_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Courageous Anthem provider is not an exact block"
        )
    if (
        _unique_member(
            value,
            "Area",
            error_type=SpontaneousSpellcastingLinkError,
        ).value
        != "60-foot emanation"
        or _unique_member(
            value,
            "Duration",
            error_type=SpontaneousSpellcastingLinkError,
        ).value
        != "1 round"
        or _description_paragraph(
            provider,
            spell_name="Courageous Anthem",
        )
        != _COURAGEOUS_ANTHEM_DESCRIPTION
    ):
        raise SpontaneousSpellcastingLinkError(
            "Courageous Anthem reviewed area, duration, or effect differs"
        )
    return {
        "type": "emanation-status-aura",
        "area": {
            "shape": "emanation",
            "radiusFeet": 60,
            "origin": "caster",
        },
        "recipients": ["caster", "allies"],
        "bonuses": [
            {
                "type": "status",
                "value": 1,
                "appliesTo": "attack-rolls",
            },
            {
                "type": "status",
                "value": 1,
                "appliesTo": "damage-rolls",
            },
            {
                "type": "status",
                "value": 1,
                "appliesTo": "saving-throws",
                "againstTraits": ["fear"],
            },
        ],
        "duration": {"rounds": 1, "source": "1 round"},
    }


def _telekinetic_hand_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Telekinetic Hand provider is not an exact block"
        )
    expected_scalars = {
        "Range": "30 feet",
        "Targets": "1 unattended object of light Bulk or less",
        "Duration": "sustained",
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Telekinetic Hand reviewed {key} differs"
            )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        _description_paragraph(
            provider,
            spell_name="Telekinetic Hand",
        )
        != _TELEKINETIC_HAND_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members)
        != ("3rd", "5th", "7th")
        or tuple(member.value for member in heightened.members)
        != (
            _TELEKINETIC_HAND_HEIGHTENED_THIRD,
            _TELEKINETIC_HAND_HEIGHTENED_FIFTH,
            _TELEKINETIC_HAND_HEIGHTENED_SEVENTH,
        )
    ):
        raise SpontaneousSpellcastingLinkError(
            "Telekinetic Hand reviewed effect or heightened text differs"
        )
    return {
        "type": "sustained-ground-object-movement",
        "rangeFeet": 30,
        "target": {
            "state": "loose-unattended",
            "maximumBulk": "light",
        },
        "movement": {
            "maximumFeet": 20,
            "intermediateSquares": "unoccupied",
            "destination": "unoccupied-ground-square",
        },
        "sustain": {
            "actionCost": 1,
            "traits": ["concentrate"],
            "maximumMovementFeet": 20,
            "oncePerTurn": True,
        },
        "duration": "sustained",
        "deferredModes": [
            "vertical-movement",
            "airborne-state-and-consequential-falling",
        ],
        "heightened": {
            "3rd": {"maximumBulk": 1},
            "5th": {"rangeFeet": 60, "maximumBulk": 1},
            "7th": {"rangeFeet": 60, "maximumBulk": 2},
        },
    }


def _telekinetic_projectile_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Telekinetic Projectile provider is not an exact block"
        )
    expected_scalars = {
        "Range": "30 feet",
        "Targets": "1 creature",
        "Defense": "AC",
        "Critical Success": _TELEKINETIC_PROJECTILE_CRITICAL_SUCCESS,
        "Success": _TELEKINETIC_PROJECTILE_SUCCESS,
    }
    for key, expected in expected_scalars.items():
        if (
            _unique_member(
                value,
                key,
                error_type=SpontaneousSpellcastingLinkError,
            ).value
            != expected
        ):
            raise SpontaneousSpellcastingLinkError(
                f"Telekinetic Projectile reviewed {key} differs"
            )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        _description_paragraph(
            provider,
            spell_name="Telekinetic Projectile",
        )
        != _TELEKINETIC_PROJECTILE_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("+1",)
        or heightened.members[0].value
        != _TELEKINETIC_PROJECTILE_HEIGHTENED
    ):
        raise SpontaneousSpellcastingLinkError(
            "Telekinetic Projectile reviewed effect or heightened text differs"
        )
    return {
        "type": "spell-attack-object-damage",
        "rangeFeet": 30,
        "target": "one-creature",
        "defense": "armor-class",
        "object": {
            "state": "loose-unattended",
            "maximumBulk": 1,
            "mustBeWithinRange": True,
        },
        "damage": {
            "dice": {"count": 2, "size": 6},
            "typeSource": "selected-object",
            "allowedTypes": [
                "bludgeoning",
                "piercing",
                "slashing",
            ],
        },
        "outcomes": {
            "criticalSuccess": {"initialDamage": "double"},
            "success": {"initialDamage": "full"},
            "failure": {"initialDamage": "none"},
        },
        "heightened": {
            "everyRanks": 1,
            "damageDice": {"count": 1, "size": 6},
        },
    }


def _summon_instrument_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    """Compile the exact source-free temporary-instrument contract."""

    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise SpontaneousSpellcastingLinkError(
            "Summon Instrument provider is not an exact block"
        )
    if (
        _unique_member(
            value,
            "Duration",
            error_type=SpontaneousSpellcastingLinkError,
        ).value
        != "1 hour"
        or _description_paragraph(
            provider,
            spell_name="Summon Instrument",
        )
        != _SUMMON_INSTRUMENT_DESCRIPTION
    ):
        raise SpontaneousSpellcastingLinkError(
            "Summon Instrument reviewed effect text differs"
        )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=SpontaneousSpellcastingLinkError,
    ).value
    if (
        type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("5th",)
        or heightened.members[0].value
        != _SUMMON_INSTRUMENT_HEIGHTENED_FIFTH
    ):
        raise SpontaneousSpellcastingLinkError(
            "Summon Instrument reviewed heightened text differs"
        )
    return {
        "type": "temporary-item-creation",
        "mechanicType": "summon-instrument-item-creation",
        "duration": {"seconds": 3600},
        "createsInCasterGrasp": True,
        "ordinaryItemEntityId": (
            "pf2er:item.musical-instrument-handheld"
        ),
        "ownerOnlyMayPlay": True,
        "recastRemovesPriorOwnedItem": True,
        "expiryRemovesExactItem": True,
        "heightened": {
            "minimumCastRank": 5,
            "itemEntityId": (
                "pf2er:item.musical-instrument-handheld-virtuoso"
            ),
        },
        "reviewedDeferrals": [
            "especially-large-handheld-bulk-gm-ruling",
            "perform-action-and-instrument-modality",
            "physical-damage-type-gm-adjudication",
        ],
    }


def _selection_digest(
    consumer: VerifiedSourceSelection,
    providers: tuple[VerifiedSourceSelection, ...],
    rules: tuple[VerifiedRuleReceipt, ...],
) -> str:
    value = {
        "consumer": consumer.receipt.digest,
        "providers": [provider.receipt.digest for provider in providers],
        "rules": [rule.receipt.digest for rule in rules],
    }
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _projection_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _freeze_json(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if type(value) is list:
        return tuple(_freeze_json(item) for item in value)
    if value is None or type(value) in (bool, int, str):
        return value
    raise TypeError(
        "normalized spontaneous-spellcasting output must be closed JSON"
    )


def _derive_projection(
    consumer: VerifiedSourceSelection,
    authority: SourceAuthorityAdapter,
    *,
    provider_specs: tuple[dict[str, Any], ...],
    provider_requirements: tuple[RuleRequirement, ...],
    governing_requirements: tuple[RuleRequirement, ...],
) -> dict[str, Any]:
    carrier = _parse_carrier(consumer, authority)
    profile = carrier["profile"]
    repertoire_ids = tuple(
        spell_id
        for _rank, _maximum, spell_ids in profile["slots"]
        for spell_id in spell_ids
    ) + tuple(profile["cantrips"][1])
    specs_by_id = {
        spec["id"]: spec
        for spec in provider_specs
    }
    requirements_by_id = {
        spec["id"]: requirement
        for spec, requirement in zip(
            provider_specs,
            provider_requirements,
            strict=True,
        )
    }
    selected_specs = tuple(
        specs_by_id[spell_id]
        for spell_id in repertoire_ids
    )
    providers: list[VerifiedSourceSelection] = []
    provider_rules: list[VerifiedRuleReceipt] = []
    authorization_modes: list[str] = []
    for spec in selected_specs:
        explicit_grant = spec["id"] in profile["explicitGrants"]
        provider, identity = _provider_block(
            authority,
            requirements_by_id[spec["id"]],
            spec,
            casting_tradition=profile["tradition"],
            explicit_repertoire_grant=explicit_grant,
        )
        providers.append(provider)
        provider_rules.append(identity)
        authorization_modes.append(
            "explicit-repertoire-grant"
            if explicit_grant
            else "tradition"
        )
    selected_governing_requirements = (
        governing_requirements
        + (
            (_DC_FROM_MODIFIER_REQUIREMENT,)
            if carrier["attack"] is None
            else ()
        )
        + (
            _MOVEMENT_TYPE_REQUIREMENTS
            if carrier["consumer"].carrier.locator
            == KOBOLD_CAVERN_MAGE_LOCATOR
            else ()
        )
        + (
            (_DURATION_REQUIREMENT,)
            if carrier["consumer"].carrier.locator
            == KOBOLD_CAVERN_MAGE_LOCATOR
            else ()
        )
    )
    try:
        governing_rules = tuple(
            authority.resolve_rule(requirement)
            for requirement in selected_governing_requirements
        )
        authority.require_shared_authority(
            carrier["consumer"],
            tuple(provider_rules) + governing_rules,
        )
    except SourceAuthorityError as failure:
        raise SpontaneousSpellcastingLinkError(
            "carrier, spells, and governing rules do not share authority"
        ) from failure

    spell_rows: list[dict[str, Any]] = []
    descriptor_compilers = {
        "breathe-fire": _breathe_fire_descriptor,
        "grease": _grease_descriptor,
        "ignition": _ignition_descriptor,
        "light": _light_descriptor,
        "tangle-vine": _tangle_vine_descriptor,
        "fleet-step": _fleet_step_descriptor,
        "heal": _heal_descriptor,
        "pummeling-rubble": _pummeling_rubble_descriptor,
        "caustic-blast": _caustic_blast_descriptor,
        "runic-weapon": _runic_weapon_descriptor,
        "bless": _bless_descriptor,
        "soothe": _soothe_descriptor,
        "courageous-anthem": _courageous_anthem_descriptor,
        "telekinetic-hand": _telekinetic_hand_descriptor,
        "telekinetic-projectile": _telekinetic_projectile_descriptor,
        "summon-instrument": _summon_instrument_descriptor,
    }
    active_ids = tuple(profile["active"])
    for spec, provider, authorization_mode in zip(
        selected_specs,
        providers,
        authorization_modes,
        strict=True,
    ):
        descriptor_compiler = descriptor_compilers.get(spec["id"])
        descriptor = (
            descriptor_compiler(provider)
            if descriptor_compiler is not None
            else None
        )
        active = spec["id"] in active_ids
        action_variants = _ACTION_VARIANTS.get(spec["actions"])
        if action_variants is None:
            raise SpontaneousSpellcastingLinkError(
                f"spell action cost is not reviewed: {spec['id']}"
            )
        action_cost = (
            action_variants[0]
            if len(action_variants) == 1
            else None
        )
        if (
            active
            and action_cost is None
            and not (
                spec["id"] == "heal"
                and action_variants == (1, 2, 3)
            )
        ):
            raise SpontaneousSpellcastingLinkError(
                f"active spell requires one exact action cost: {spec['id']}"
            )
        repertoire_authorization = (
            {
                "mode": "tradition",
                "tradition": profile["tradition"],
            }
            if authorization_mode == "tradition"
            else {
                "mode": "explicit-repertoire-grant",
                "tradition": profile["tradition"],
                "providerTraditions": list(spec["traditions"]),
                "source": carrier["consumer"].receipt.as_serialized(),
            }
        )
        spell_rows.append(
            {
                "id": spec["id"],
                "name": spec["name"],
                "rank": spec["rank"],
                "kind": spec["kind"],
                "actionCost": action_cost,
                "rawActionCost": spec["actions"],
                "actionVariants": list(action_variants),
                "traits": list(spec["traits"]),
                "traditions": list(spec["traditions"]),
                "repertoireAuthorization": repertoire_authorization,
                "source": provider.receipt.as_serialized(),
                "compiledEffect": descriptor,
                "execution": (
                    {
                        "executable": True,
                        "status": "active",
                        "runtimeSupported": True,
                        "runtimeDependencies": [],
                    }
                    if active
                    else {
                        "executable": False,
                        "status": "deferred",
                        "runtimeSupported": False,
                        "runtimeDependencies": list(
                            spec["runtimeDependencies"]
                        ),
                    }
                ),
            }
        )

    provider_tuple = tuple(providers)
    authority_digest = carrier["consumer"].carrier.authority_digest
    if carrier["attack"] is None:
        attack_rule = next(
            rule
            for rule in governing_rules
            if rule.rule_id == "dc-from-modifier"
        )
        attack_value = int(carrier["dc"]) - 10
        attack_evidence = {
            "mode": "derived",
            "authoredMemberPresent": False,
            "inputDc": int(carrier["dc"]),
            "formula": "DC - 10",
            "value": attack_value,
            "rule": {
                "id": attack_rule.rule_id,
                "source": attack_rule.receipt.as_serialized(),
            },
        }
    else:
        attack_value = int(carrier["attack"])
        attack_evidence = {
            "mode": "authored",
            "authoredMemberPresent": True,
            "value": attack_value,
        }
    body = {
        "schema": 1,
        "kind": "pf2er-spontaneous-spellcasting-compilation",
        "familyId": FAMILY_ID,
        "compilerId": COMPILER_ID,
        "supportState": "partial-runtime",
        "compileSupported": True,
        "runtimeActivation": {
            "status": "partial",
            "executableSpellIds": list(active_ids),
            "deferredSpellIds": [
                spell_id
                for spell_id in repertoire_ids
                if spell_id not in active_ids
            ],
        },
        "source": carrier["consumer"].receipt.as_serialized(),
        "casting": {
            "id": profile["castingId"],
            "mode": "spontaneous",
            "tradition": profile["tradition"],
            "dc": carrier["dc"],
            "attack": attack_value,
            "attackEvidence": attack_evidence,
            "slots": carrier["slots"],
            "cantrips": carrier["cantrips"],
        },
        "spells": spell_rows,
        "governingRules": [
            {
                "id": rule.rule_id,
                "source": rule.receipt.as_serialized(),
            }
            for rule in governing_rules
        ],
        "provenance": {
            "authorityDigest": authority_digest,
            "selectionDigest": _selection_digest(
                carrier["consumer"],
                provider_tuple,
                governing_rules,
            ),
        },
    }
    return {**body, "digest": _projection_digest(body)}


class _ImmutableArtifactType(type):
    def __setattr__(cls, _name: str, _value: object) -> None:
        raise TypeError(
            "spontaneous-spellcasting artifact class is immutable"
        )

    def __delattr__(cls, _name: str) -> None:
        raise TypeError(
            "spontaneous-spellcasting artifact class is immutable"
        )


@final
class CompiledSpontaneousSpellcasting(metaclass=_ImmutableArtifactType):
    """One immutable, authority-backed normalized repertoire artifact."""

    __slots__ = ("_projection_digest", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "CompiledSpontaneousSpellcasting can only be created by "
            "compile_spontaneous_spellcasting()"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError(
            "CompiledSpontaneousSpellcasting subclasses are unsupported"
        )

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("CompiledSpontaneousSpellcasting is immutable")

    def __delattr__(self, _name: str) -> None:
        raise TypeError("CompiledSpontaneousSpellcasting is immutable")

    def as_serialized(self) -> dict[str, Any]:
        """Return a fresh JSON projection after revalidating authority."""

        return _artifact_projection(self)

    @property
    def normalized(self) -> MappingProxyType[str, Any]:
        """Return a recursively immutable normalized projection."""

        frozen = _freeze_json(_artifact_projection(self))
        if type(frozen) is not MappingProxyType:
            raise SpontaneousSpellcastingArtifactError(
                "normalized projection lost its object root"
            )
        return frozen

    def __copy__(self) -> CompiledSpontaneousSpellcasting:
        raise TypeError("CompiledSpontaneousSpellcasting cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> CompiledSpontaneousSpellcasting:
        raise TypeError(
            "CompiledSpontaneousSpellcasting cannot be copied"
        )

    def __reduce__(self) -> object:
        raise TypeError(
            "CompiledSpontaneousSpellcasting cannot be pickled"
        )

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError(
            "CompiledSpontaneousSpellcasting cannot be pickled"
        )


_ARTIFACTS: WeakKeyDictionary[
    CompiledSpontaneousSpellcasting,
    tuple[SourceAuthorityAdapter, VerifiedSourceSelection, str],
] = WeakKeyDictionary()


def _bind_compiler() -> tuple[
    Callable[
        [VerifiedSourceSelection, SourceAuthorityAdapter],
        CompiledSpontaneousSpellcasting,
    ],
    Callable[[CompiledSpontaneousSpellcasting], dict[str, Any]],
]:
    provider_specs = tuple(dict(spec) for spec in _PROVIDER_SPECS)
    for spec in provider_specs:
        for key in ("traits", "traditions", "runtimeDependencies"):
            spec[key] = tuple(spec[key])
    provider_requirements = tuple(_PROVIDER_REQUIREMENTS)
    governing_requirements = tuple(_GOVERNING_REQUIREMENTS)
    registry = _ARTIFACTS

    def derive(
        consumer: VerifiedSourceSelection,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        return _derive_projection(
            consumer,
            authority,
            provider_specs=provider_specs,
            provider_requirements=provider_requirements,
            governing_requirements=governing_requirements,
        )

    def compile_spontaneous_spellcasting(
        consumer: VerifiedSourceSelection,
        authority: SourceAuthorityAdapter,
        /,
    ) -> CompiledSpontaneousSpellcasting:
        """Compile and link one reviewed spontaneous casting selection."""

        if type(consumer) is not VerifiedSourceSelection:
            raise TypeError(
                "consumer must be an exact VerifiedSourceSelection"
            )
        if type(authority) is not SourceAuthorityAdapter:
            raise TypeError(
                "authority must be an exact SourceAuthorityAdapter"
            )
        projection = derive(consumer, authority)
        projection_sha256 = _projection_digest(projection)
        result = object.__new__(CompiledSpontaneousSpellcasting)
        object.__setattr__(
            result,
            "_projection_digest",
            projection_sha256,
        )
        registry[result] = (authority, consumer, projection_sha256)
        return result

    def artifact_projection(
        value: CompiledSpontaneousSpellcasting,
    ) -> dict[str, Any]:
        if type(value) is not CompiledSpontaneousSpellcasting:
            raise TypeError(
                "artifact must be exact CompiledSpontaneousSpellcasting"
            )
        try:
            authority, consumer, expected = registry[value]
        except KeyError as failure:
            raise SpontaneousSpellcastingArtifactError(
                "artifact is not registered with this compiler"
            ) from failure
        stored = object.__getattribute__(value, "_projection_digest")
        if type(stored) is not str or stored != expected:
            raise SpontaneousSpellcastingArtifactError(
                "artifact projection digest changed"
            )
        try:
            projection = derive(consumer, authority)
        except (
            SourceAuthorityError,
            SpontaneousSpellcastingSourceError,
            SpontaneousSpellcastingLinkError,
            TypeError,
            ValueError,
        ) as failure:
            raise SpontaneousSpellcastingArtifactError(
                "artifact source authority no longer validates"
            ) from failure
        if _projection_digest(projection) != expected:
            raise SpontaneousSpellcastingArtifactError(
                "artifact normalized projection changed"
            )
        return projection

    return compile_spontaneous_spellcasting, artifact_projection


(
    compile_spontaneous_spellcasting,
    _artifact_projection,
) = _bind_compiler()


__all__ = [
    "COMPILER_ID",
    "CompiledSpontaneousSpellcasting",
    "FAMILY_ID",
    "GOBLIN_PYRO_LOCATOR",
    "GOBLIN_WAR_CHANTER_LOCATOR",
    "KOBOLD_CAVERN_MAGE_LOCATOR",
    "SpontaneousSpellcastingArtifactError",
    "SpontaneousSpellcastingLinkError",
    "SpontaneousSpellcastingSourceError",
    "compile_spontaneous_spellcasting",
]

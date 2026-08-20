"""Compile exact reviewed prepared-spellcasting creature carriers.

Each carrier owns its authored DC, optional authored attack modifier,
prepared spell instances, and cantrip repertoire. Player Core spell providers
own reusable normalized effects. Only providers with an independently
registered runtime effect are activated.
"""

from __future__ import annotations

import hashlib
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


FAMILY_ID = "prepared-spellcasting"
COMPILER_ID = "creature-prepared-spellcasting"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"
LIZARDFOLK_STARGAZER_LOCATOR = "227.2"
AIUVARIN_ELEMENTALIST_LOCATOR = "151.4"

_CARRIER_FIELD = "Spellcasting"
_STARGAZER_CARRIER_SELECTION_SHA256 = (
    "64c8e2a7e25bb6004789939f71bc3885ec0dab127013d495884e41b3b47d75f6"
)
_AIUVARIN_CARRIER_SELECTION_SHA256 = (
    "785f6a8fdf9e65264bb01a02c1cff02760528b81e1d021aaad005ac469c7bca0"
)
_STARGAZER_PREPARED_IDS = (
    "charm",
    "heal",
    "runic-body",
    "pest-form",
    "summon-animal",
)
_STARGAZER_CANTRIP_IDS = (
    "guidance",
    "ignition",
    "know-the-way",
    "light",
    "stabilize",
)
_STARGAZER_ACTIVE_IDS = ("heal", "runic-body")
_AIUVARIN_PREPARED_IDS = (
    "gentle-landing",
    "gust-of-wind",
    "illusory-disguise",
    "thunderstrike",
)
_AIUVARIN_CANTRIP_IDS = (
    "detect-magic",
    "electric-arc",
    "light",
    "message",
    "shield",
)
_AIUVARIN_ACTIVE_IDS = ("thunderstrike", "electric-arc")

_ACTION_VARIANTS = {
    "reaction": (),
    "single": (1,),
    "two": (2,),
    "three": (3,),
    "single-to-three": (1, 2, 3),
}

_RUNIC_BODY_DESCRIPTION = (
    "Glowing runes appear on the target’s body. All its unarmed attacks "
    "become +1 striking unarmed attacks, gaining a +1 item bonus to attack "
    "rolls and increasing the number of damage dice to two."
)
_RUNIC_BODY_HEIGHTENED_SIXTH = (
    "The unarmed attacks are +2 greater striking."
)
_RUNIC_BODY_HEIGHTENED_NINTH = (
    "The unarmed attacks are +3 major striking."
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
_ELECTRIC_ARC_DESCRIPTION = (
    "An arc of lightning leaps from one target to another. Each target takes "
    "2d4 electricity damage with a basic Reflex save."
)
_ELECTRIC_ARC_HEIGHTENED = "The damage increases by 1d4."
_THUNDERSTRIKE_DESCRIPTION = (
    "You call down a tendril of lightning that cracks with thunder, dealing "
    "1d12 electricity damage and 1d4 sonic damage to the target with a basic "
    "Reflex save. A target wearing metal armor or made of metal takes a –1 "
    "circumstance bonus to its save, and if damaged by the spell is clumsy 1 "
    "for 1 round."
)
_THUNDERSTRIKE_HEIGHTENED = (
    "The damage increases by 1d12 electricity and 1d4 sonic."
)


class PreparedSpellcastingSourceError(ValueError):
    """The authenticated carrier violates the reviewed prepared grammar."""


class PreparedSpellcastingLinkError(ValueError):
    """A reviewed Player Core dependency cannot be linked exactly."""


class PreparedSpellcastingArtifactError(ValueError):
    """A compiled artifact no longer agrees with its authority."""


_STARGAZER_PROVIDER_SPECS = (
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
            "hostile-actions",
            "incapacitation-saves",
            "dismiss",
        ),
        "nameSha256": (
            "569e495a4dd4b268874f8f81a6301b19960dd19b997571dedce9e9aa6136863b"
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
        "id": "runic-body",
        "name": "Runic Body",
        "locator": "354.2",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": ("concentrate", "manipulate"),
        "traditions": ("arcane", "divine", "occult", "primal"),
        "runtimeDependencies": (),
        "nameSha256": (
            "684380e20b9c7fffeafc71116d9421e3beeb0c39807fd7ded7126b0f14b87151"
        ),
    },
    {
        "id": "pest-form",
        "name": "Pest Form",
        "locator": "348.5",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": ("concentrate", "manipulate", "polymorph"),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "battle-form",
            "polymorph",
            "transformed-statistics",
        ),
        "nameSha256": (
            "8454a2ebffb89a690c919f73a84f9b5943f368f40737a29417f2168f036be79a"
        ),
    },
    {
        "id": "summon-animal",
        "name": "Summon Animal",
        "locator": "360.3",
        "rank": 1,
        "kind": "spell",
        "actions": "three",
        "traits": ("concentrate", "manipulate", "summon"),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "summoned-creatures",
            "minion-actions",
            "sustain",
        ),
        "nameSha256": (
            "421accca679c2a60e4bc1683f8ff6086d9a54604b32419cb8d71fbc228d8c7cc"
        ),
    },
    {
        "id": "guidance",
        "name": "Guidance",
        "locator": "334.2",
        "rank": 1,
        "kind": "cantrip",
        "actions": "single",
        "traits": ("cantrip", "concentrate"),
        "traditions": ("divine", "occult", "primal"),
        "runtimeDependencies": (
            "single-use-roll-bonus",
            "temporary-immunity",
        ),
        "nameSha256": (
            "fd4c2965c801d1ceb3381c4ab128578fb83b3bdf2e0b368a5bcde95ad2b554dd"
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
            "prepared-carrier-targeted-cantrip-provider",
        ),
        "nameSha256": (
            "f840cd5c04dc7ca5bbea93b65c682a57fe8fa6be18341a1b31c40288aea31a25"
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
            "prepared-carrier-light-provider",
        ),
        "nameSha256": (
            "0b46afa96380156b3a65feffe7bef3ce6c78f6e0db4d90d298b0092107217ee1"
        ),
    },
    {
        "id": "stabilize",
        "name": "Stabilize",
        "locator": "359.3",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": (
            "cantrip",
            "concentrate",
            "healing",
            "manipulate",
            "vitality",
        ),
        "traditions": ("divine", "primal"),
        "runtimeDependencies": (
            "dying-condition",
            "unconscious-at-zero-hit-points",
        ),
        "nameSha256": (
            "18bef51b6322ceeefd654b7fc900c2ced26401b7d98f27d713f125d7776c45fb"
        ),
    },
)

_AIUVARIN_PROVIDER_SPECS = (
    {
        "id": "gentle-landing",
        "name": "Gentle Landing",
        "locator": "333.3",
        "rank": 1,
        "kind": "spell",
        "actions": "reaction",
        "traits": ("air", "concentrate"),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "reaction-spellcasting",
            "falling-state",
            "falling-damage",
        ),
        "nameSha256": (
            "c2d2f383392e4994f8b00990d1339f50fb43e2a1d7da9cd3cc37bd166e75b8b0"
        ),
    },
    {
        "id": "gust-of-wind",
        "name": "Gust of Wind",
        "locator": "334.3",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": ("air", "concentrate", "manipulate"),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (
            "line-area",
            "persistent-area",
            "forced-movement",
            "flying-state",
            "environmental-effects",
        ),
        "nameSha256": (
            "8e11e41fa2cb6d825476f5ef179d95da0e13d7560411223551d02b177a68666e"
        ),
    },
    {
        "id": "illusory-disguise",
        "name": "Illusory Disguise",
        "locator": "337.1",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": (
            "concentrate",
            "illusion",
            "manipulate",
            "visual",
        ),
        "traditions": ("arcane", "occult"),
        "runtimeDependencies": (
            "disguise-state",
            "impersonate",
            "dismiss",
        ),
        "nameSha256": (
            "185156fe34fde8baeb3d012543751c67c2368ca1924b5d2b621d57524beeec7d"
        ),
    },
    {
        "id": "thunderstrike",
        "name": "Thunderstrike",
        "locator": "363.5",
        "rank": 1,
        "kind": "spell",
        "actions": "two",
        "traits": (
            "concentrate",
            "electricity",
            "manipulate",
            "sonic",
        ),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (),
        "nameSha256": (
            "79c8e2021338f67849004d97995497fe6a9cbc66d1b85f5eb79a1307c234bd5c"
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
            "magic-detection",
            "effect-rank-detection",
        ),
        "nameSha256": (
            "80962ed607dc404be19160c40ac8a420916a5f1a16bd19a2e77e21dfd8d5cff2"
        ),
    },
    {
        "id": "electric-arc",
        "name": "Electric Arc",
        "locator": "328.2",
        "rank": 1,
        "kind": "cantrip",
        "actions": "two",
        "traits": (
            "cantrip",
            "concentrate",
            "electricity",
            "manipulate",
        ),
        "traditions": ("arcane", "primal"),
        "runtimeDependencies": (),
        "nameSha256": (
            "e6069879c0417a0b81576237d169ba94fa09fa31ac79cf5d88268c853a720bad"
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
            "prepared-carrier-light-provider",
        ),
        "nameSha256": (
            "0b46afa96380156b3a65feffe7bef3ce6c78f6e0db4d90d298b0092107217ee1"
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
            "private-communication",
            "target-reply-timing",
        ),
        "nameSha256": (
            "be1af94c8c00110d748345ea5e25cfc3aca39055ab9101ab1d8d551928445819"
        ),
    },
    {
        "id": "shield",
        "name": "Shield",
        "locator": "356.7",
        "rank": 1,
        "kind": "cantrip",
        "actions": "single",
        "traits": ("cantrip", "concentrate", "force"),
        "traditions": ("arcane", "divine", "occult"),
        "runtimeDependencies": (
            "spell-shield",
            "magical-shield-block",
            "recast-lockout",
        ),
        "nameSha256": (
            "71486b7aa40e5861e11ada49a8bc8421387847760c8402b6c9423f101c6a778a"
        ),
    },
)

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


def _provider_requirements(
    specs: tuple[dict[str, Any], ...],
) -> tuple[RuleRequirement, ...]:
    return tuple(
        _provider_requirement(
            rule_id=f"spell-provider:{spec['id']}",
            locator=spec["locator"],
            name_sha256=spec["nameSha256"],
        )
        for spec in specs
    )


_STARGAZER_PROVIDER_REQUIREMENTS = _provider_requirements(
    _STARGAZER_PROVIDER_SPECS
)
_AIUVARIN_PROVIDER_REQUIREMENTS = _provider_requirements(
    _AIUVARIN_PROVIDER_SPECS
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
        rule_id="prepared-spells",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="297.4",
        expected_block_sha256=(
            "328a10d3a9fd4f33601c6983811957d2ac8f356cb80ce5f3daecae513df7fca3"
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
    RuleRequirement(
        rule_id="duration",
        source_id=PLAYER_CORE_SOURCE_ID,
        locator="426.2",
        expected_block_sha256=(
            "abae8acd3b37239c6a931639213e2a82dc7013498d3577007064f9cc1076bcc0"
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

_CARRIER_PROFILES = {
    LIZARDFOLK_STARGAZER_LOCATOR: {
        "locator": LIZARDFOLK_STARGAZER_LOCATOR,
        "name": "Lizardfolk Stargazer",
        "carrierMemberOrdinal": 3,
        "spellcastingMemberOrdinal": 24,
        "selectionSha256": _STARGAZER_CARRIER_SELECTION_SHA256,
        "castingHeader": "Primal Prepared Spells",
        "castingFields": ("DC", "Attack", "Entries"),
        "castingId": "primal-prepared-spells",
        "tradition": "primal",
        "dcText": "18",
        "attackText": "+10",
        "entryShape": "array",
        "preparedIds": _STARGAZER_PREPARED_IDS,
        "cantripIds": _STARGAZER_CANTRIP_IDS,
        "activeIds": _STARGAZER_ACTIVE_IDS,
        "providerSpecs": _STARGAZER_PROVIDER_SPECS,
        "providerRequirements": _STARGAZER_PROVIDER_REQUIREMENTS,
        "governingRequirements": _GOVERNING_REQUIREMENTS,
    },
    AIUVARIN_ELEMENTALIST_LOCATOR: {
        "locator": AIUVARIN_ELEMENTALIST_LOCATOR,
        "name": "Aiuvarin Elementalist",
        "carrierMemberOrdinal": 2,
        "spellcastingMemberOrdinal": 24,
        "selectionSha256": _AIUVARIN_CARRIER_SELECTION_SHA256,
        "castingHeader": "Arcane Prepared Spells",
        "castingFields": ("DC", "Entries"),
        "castingId": "arcane-prepared-spells",
        "tradition": "arcane",
        "dcText": "18",
        "attackText": None,
        "entryShape": "comma-separated-string",
        "preparedIds": _AIUVARIN_PREPARED_IDS,
        "cantripIds": _AIUVARIN_CANTRIP_IDS,
        "activeIds": _AIUVARIN_ACTIVE_IDS,
        "providerSpecs": _AIUVARIN_PROVIDER_SPECS,
        "providerRequirements": _AIUVARIN_PROVIDER_REQUIREMENTS,
        "governingRequirements": (
            *_GOVERNING_REQUIREMENTS,
            _DC_FROM_MODIFIER_REQUIREMENT,
        ),
    },
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
            f"source requires one exact {key!r} member; "
            f"found {len(matches)}"
        )
    return matches[0]


def _exact_string_array(
    value: object,
    *,
    label: str,
) -> tuple[str, ...]:
    if type(value) is not RawSourceArray or any(
        type(item) is not str for item in value.items
    ):
        raise PreparedSpellcastingLinkError(
            f"{label} must be an exact source string array"
        )
    return tuple(value.items)


def _provider_block(
    authority: SourceAuthorityAdapter,
    requirement: RuleRequirement,
    spec: dict[str, Any],
    *,
    tradition: str,
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
        raise PreparedSpellcastingLinkError(
            f"spell provider cannot resolve exactly: {spec['id']}"
        ) from failure
    if label != spec["name"]:
        raise PreparedSpellcastingLinkError(
            f"spell provider ToC label mismatch: {spec['id']}"
        )
    value = provider.selected_value
    if type(value) is not RawSourceObject or provider.raw_member is not None:
        raise PreparedSpellcastingLinkError(
            f"spell provider must be one exact block: {spec['id']}"
        )
    keys = tuple(member.key for member in value.members)
    if len(keys) != len(set(keys)):
        raise PreparedSpellcastingLinkError(
            f"spell provider has duplicate root fields: {spec['id']}"
        )
    name = _unique_member(
        value,
        "Name",
        error_type=PreparedSpellcastingLinkError,
    ).value
    rank = _unique_member(
        value,
        "Rank",
        error_type=PreparedSpellcastingLinkError,
    ).value
    kind = _unique_member(
        value,
        "Kind",
        error_type=PreparedSpellcastingLinkError,
    ).value
    actions = _unique_member(
        value,
        "Actions",
        error_type=PreparedSpellcastingLinkError,
    ).value
    traits = _exact_string_array(
        _unique_member(
            value,
            "Traits",
            error_type=PreparedSpellcastingLinkError,
        ).value,
        label=f"{spec['id']} Traits",
    )
    traditions = _exact_string_array(
        _unique_member(
            value,
            "Traditions",
            error_type=PreparedSpellcastingLinkError,
        ).value,
        label=f"{spec['id']} Traditions",
    )
    if (
        name != spec["name"]
        or rank != spec["rank"]
        or kind != spec["kind"]
        or actions != spec["actions"]
        or traits != spec["traits"]
        or traditions != spec["traditions"]
        or tradition not in traditions
        or identity.selection.selected_value != name
    ):
        raise PreparedSpellcastingLinkError(
            f"spell provider semantic fields mismatch: {spec['id']}"
        )
    return provider, identity


def _italic_spell_names(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not RawSourceArray or any(
        type(item) is not str for item in value.items
    ):
        raise PreparedSpellcastingSourceError(
            f"{label} must be an exact source string array"
        )
    names = []
    for item in value.items:
        if not item.startswith("<i>") or not item.endswith("</i>"):
            raise PreparedSpellcastingSourceError(
                f"{label} has unreviewed spell markup"
            )
        name = item[3:-4]
        if not name or name != name.casefold():
            raise PreparedSpellcastingSourceError(
                f"{label} has unreviewed spell casing"
            )
        names.append(name)
    return tuple(names)


def _comma_separated_italic_spell_names(
    value: object,
    label: str,
) -> tuple[str, ...]:
    if type(value) is not str or not value:
        raise PreparedSpellcastingSourceError(
            f"{label} must be one exact source string"
        )
    return _italic_spell_names(
        RawSourceArray(tuple(value.split(", "))),
        label,
    )


def _parse_carrier(
    consumer: VerifiedSourceSelection,
    authority: SourceAuthorityAdapter,
    *,
    profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    try:
        verified = authority.validate_selection(consumer)
    except SourceAuthorityError as failure:
        raise PreparedSpellcastingLinkError(
            "prepared carrier does not belong to this authority"
        ) from failure
    profile = profiles.get(verified.carrier.locator)
    if profile is None:
        raise PreparedSpellcastingSourceError(
            "carrier is not a reviewed prepared-spellcasting selection"
        )
    address = verified.address
    if (
        verified.carrier.source_id != MONSTER_CORE_SOURCE_ID
        or verified.carrier.locator != profile["locator"]
        or authority.toc_label(
            MONSTER_CORE_SOURCE_ID,
            profile["locator"],
        )
        != profile["name"]
        or len(address.carrier_path) != 1
        or address.carrier_path[0].raw_key != "^.creature"
        or address.carrier_path[0].member_ordinal
        != profile["carrierMemberOrdinal"]
        or len(address.selection_path) != 1
        or address.selection_path[0].raw_key != _CARRIER_FIELD
        or address.selection_path[0].member_ordinal
        != profile["spellcastingMemberOrdinal"]
        or address.span is not None
        or verified.carrier.raw_block.values("Name")
        != (profile["name"],)
        or verified.raw_member is None
        or verified.raw_member.key != _CARRIER_FIELD
        or verified.selection_sha256 != profile["selectionSha256"]
    ):
        raise PreparedSpellcastingSourceError(
            "carrier is not the exact reviewed prepared Spellcasting selection"
        )
    spellcasting = verified.selected_value
    if (
        type(spellcasting) is not RawSourceObject
        or tuple(member.key for member in spellcasting.members)
        != (profile["castingHeader"],)
    ):
        raise PreparedSpellcastingSourceError(
            "Spellcasting requires the exact prepared casting header"
        )
    casting = spellcasting.members[0].value
    if (
        type(casting) is not RawSourceObject
        or tuple(member.key for member in casting.members)
        != profile["castingFields"]
    ):
        raise PreparedSpellcastingSourceError(
            "prepared casting fields or order differ from source"
        )
    dc = _unique_member(
        casting,
        "DC",
        error_type=PreparedSpellcastingSourceError,
    ).value
    attack = (
        _unique_member(
            casting,
            "Attack",
            error_type=PreparedSpellcastingSourceError,
        ).value
        if profile["attackText"] is not None
        else None
    )
    entries = _unique_member(
        casting,
        "Entries",
        error_type=PreparedSpellcastingSourceError,
    ).value
    if (
        dc != profile["dcText"]
        or attack != profile["attackText"]
        or parse_decimal_integer(dc)
        != parse_decimal_integer(profile["dcText"])
        or (
            attack is not None
            and parse_decimal_integer(attack)
            != parse_decimal_integer(profile["attackText"])
        )
        or type(entries) is not RawSourceObject
        or tuple(member.key for member in entries.members)
        != ("1st", "Cantrips (1st)")
    ):
        raise PreparedSpellcastingSourceError(
            "prepared DC, attack, or entries differ from source"
        )
    name_parser = (
        _italic_spell_names
        if profile["entryShape"] == "array"
        else _comma_separated_italic_spell_names
    )
    prepared_names = name_parser(
        entries.members[0].value, "prepared spell list"
    )
    cantrip_names = name_parser(entries.members[1].value, "cantrip list")
    specs = {
        spec["id"]: spec
        for spec in profile["providerSpecs"]
    }
    if prepared_names != tuple(
        specs[spell_id]["name"].casefold()
        for spell_id in profile["preparedIds"]
    ) or cantrip_names != tuple(
        specs[spell_id]["name"].casefold()
        for spell_id in profile["cantripIds"]
    ):
        raise PreparedSpellcastingSourceError(
            "prepared repertoire contains missing, reordered, or unreviewed spells"
        )
    return {
        "consumer": verified,
        "profile": profile,
        "dc": parse_decimal_integer(dc),
        "attack": (
            parse_decimal_integer(attack)
            if attack is not None
            else None
        ),
        "preparedSpells": [
            {"rank": 1, "spellId": spell_id, "maximum": 1}
            for spell_id in profile["preparedIds"]
        ],
        "cantrips": {
            "rank": 1,
            "spellIds": list(profile["cantripIds"]),
        },
    }


def _description_paragraph(
    provider: VerifiedSourceSelection,
) -> str:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise PreparedSpellcastingLinkError(
            "Runic Body provider is not an exact block"
        )
    description = _unique_member(
        value,
        "Description",
        error_type=PreparedSpellcastingLinkError,
    ).value
    if (
        type(description) is not RawSourceObject
        or tuple(member.key for member in description.members) != ("~.p",)
        or type(description.members[0].value) is not str
    ):
        raise PreparedSpellcastingLinkError(
            "Runic Body description is not one exact paragraph"
        )
    return description.members[0].value


def _runic_body_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise PreparedSpellcastingLinkError(
            "Runic Body provider is not an exact block"
        )
    expected = {
        "Range": "touch",
        "Targets": "1 willing creature",
        "Duration": "1 minute",
    }
    for key, expected_value in expected.items():
        if _unique_member(
            value,
            key,
            error_type=PreparedSpellcastingLinkError,
        ).value != expected_value:
            raise PreparedSpellcastingLinkError(
                f"Runic Body reviewed {key} differs"
            )
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=PreparedSpellcastingLinkError,
    ).value
    if (
        _description_paragraph(provider) != _RUNIC_BODY_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members)
        != ("6th", "9th")
        or heightened.members[0].value
        != _RUNIC_BODY_HEIGHTENED_SIXTH
        or heightened.members[1].value
        != _RUNIC_BODY_HEIGHTENED_NINTH
    ):
        raise PreparedSpellcastingLinkError(
            "Runic Body reviewed effect or heightening text differs"
        )
    return {
        "type": "target-unarmed-striking-runes",
        "range": {
            "kind": "touch",
            "maximumDistanceFeet": 5,
        },
        "target": "one-willing-creature",
        "attackItemBonus": 1,
        "damageDiceCount": 2,
        "duration": {
            "rounds": 10,
            "source": "1 minute",
        },
        "heightened": {
            "6th": {"potencyBonus": 2, "strikingRune": "greater"},
            "9th": {"potencyBonus": 3, "strikingRune": "major"},
        },
    }


def _heal_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise PreparedSpellcastingLinkError(
            "Heal provider is not an exact block"
        )
    description = _unique_member(
        value,
        "Description",
        error_type=PreparedSpellcastingLinkError,
    ).value
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=PreparedSpellcastingLinkError,
    ).value
    if (
        _unique_member(
            value,
            "Range",
            error_type=PreparedSpellcastingLinkError,
        ).value
        != "varies"
        or _unique_member(
            value,
            "Targets",
            error_type=PreparedSpellcastingLinkError,
        ).value
        != "1 willing living creature or 1 undead creature"
        or type(description) is not RawSourceObject
        or tuple(member.key for member in description.members) != ("~.p",)
        or description.members[0].value != _HEAL_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("+1",)
        or heightened.members[0].value != _HEAL_HEIGHTENED
    ):
        raise PreparedSpellcastingLinkError(
            "Heal reviewed targets, range, effect, or heightening differs"
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


def _electric_arc_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise PreparedSpellcastingLinkError(
            "Electric Arc provider is not an exact block"
        )
    expected = {
        "Range": "30 feet",
        "Targets": "1 or 2 creatures",
        "Defense": "basic Reflex",
    }
    for key, expected_value in expected.items():
        if (
            _unique_member(
                value,
                key,
                error_type=PreparedSpellcastingLinkError,
            ).value
            != expected_value
        ):
            raise PreparedSpellcastingLinkError(
                f"Electric Arc reviewed {key} differs"
            )
    description = _unique_member(
        value,
        "Description",
        error_type=PreparedSpellcastingLinkError,
    ).value
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=PreparedSpellcastingLinkError,
    ).value
    if (
        type(description) is not RawSourceObject
        or tuple(member.key for member in description.members) != ("~.p",)
        or description.members[0].value != _ELECTRIC_ARC_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("+1",)
        or heightened.members[0].value != _ELECTRIC_ARC_HEIGHTENED
    ):
        raise PreparedSpellcastingLinkError(
            "Electric Arc reviewed effect or heightening text differs"
        )
    return {
        "type": "multi-target-basic-save-damage",
        "rangeFeet": 30,
        "targets": {
            "kind": "creature",
            "minimum": 1,
            "maximum": 2,
            "distinct": True,
        },
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dcSource": "casting",
        },
        "damage": {
            "dice": {"count": 2, "size": 4},
            "type": "electricity",
        },
        "heightened": {
            "everyRanks": 1,
            "damageDice": {"count": 1, "size": 4},
        },
    }


def _thunderstrike_descriptor(
    provider: VerifiedSourceSelection,
) -> dict[str, Any]:
    value = provider.selected_value
    if type(value) is not RawSourceObject:
        raise PreparedSpellcastingLinkError(
            "Thunderstrike provider is not an exact block"
        )
    expected = {
        "Range": "120 feet",
        "Targets": "1 creature",
        "Defense": "basic Reflex",
    }
    for key, expected_value in expected.items():
        if (
            _unique_member(
                value,
                key,
                error_type=PreparedSpellcastingLinkError,
            ).value
            != expected_value
        ):
            raise PreparedSpellcastingLinkError(
                f"Thunderstrike reviewed {key} differs"
            )
    description = _unique_member(
        value,
        "Description",
        error_type=PreparedSpellcastingLinkError,
    ).value
    heightened = _unique_member(
        value,
        "Heightened",
        error_type=PreparedSpellcastingLinkError,
    ).value
    if (
        type(description) is not RawSourceObject
        or tuple(member.key for member in description.members) != ("~.p",)
        or description.members[0].value != _THUNDERSTRIKE_DESCRIPTION
        or type(heightened) is not RawSourceObject
        or tuple(member.key for member in heightened.members) != ("+1",)
        or heightened.members[0].value != _THUNDERSTRIKE_HEIGHTENED
    ):
        raise PreparedSpellcastingLinkError(
            "Thunderstrike reviewed effect or heightening text differs"
        )
    return {
        "type": "single-target-basic-save-multi-damage-and-condition",
        "rangeFeet": 120,
        "target": "one-creature",
        "savingThrow": {
            "type": "reflex",
            "basic": True,
            "dcSource": "casting",
        },
        "damageComponents": [
            {
                "dice": {"count": 1, "size": 12},
                "type": "electricity",
            },
            {
                "dice": {"count": 1, "size": 4},
                "type": "sonic",
            },
        ],
        "conditionalTarget": {
            "predicate": "wearing-metal-armor-or-made-of-metal",
            "savingThrowModifier": {
                "type": "circumstance",
                "value": -1,
            },
            "ifDamaged": {
                "condition": {
                    "id": "clumsy",
                    "value": 1,
                    "duration": {"rounds": 1},
                },
            },
        },
        "heightened": {
            "everyRanks": 1,
            "damageComponents": [
                {
                    "dice": {"count": 1, "size": 12},
                    "type": "electricity",
                },
                {
                    "dice": {"count": 1, "size": 4},
                    "type": "sonic",
                },
            ],
        },
    }


def _projection_digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _derive_projection(
    consumer: VerifiedSourceSelection,
    authority: SourceAuthorityAdapter,
    *,
    profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    carrier = _parse_carrier(
        consumer,
        authority,
        profiles=profiles,
    )
    profile = carrier["profile"]
    provider_specs = profile["providerSpecs"]
    provider_requirements = profile["providerRequirements"]
    governing_requirements = profile["governingRequirements"]
    requirements = {
        spec["id"]: requirement
        for spec, requirement in zip(
            provider_specs,
            provider_requirements,
            strict=True,
        )
    }
    specs = {spec["id"]: spec for spec in provider_specs}
    repertoire_ids = profile["preparedIds"] + profile["cantripIds"]
    providers: list[VerifiedSourceSelection] = []
    identities: list[VerifiedRuleReceipt] = []
    for spell_id in repertoire_ids:
        spec = specs[spell_id]
        try:
            provider, identity = _provider_block(
                authority,
                requirements[spell_id],
                spec,
                tradition=profile["tradition"],
            )
        except ValueError as failure:
            raise PreparedSpellcastingLinkError(
                f"prepared spell provider cannot link: {spell_id}"
            ) from failure
        providers.append(provider)
        identities.append(identity)
    try:
        governing_rules = tuple(
            authority.resolve_rule(requirement)
            for requirement in governing_requirements
        )
        authority.require_shared_authority(
            carrier["consumer"],
            tuple(identities) + governing_rules,
        )
    except SourceAuthorityError as failure:
        raise PreparedSpellcastingLinkError(
            "carrier, spells, and governing rules do not share authority"
        ) from failure

    descriptor_compilers: dict[
        str,
        Callable[[VerifiedSourceSelection], dict[str, Any]],
    ] = {
        "electric-arc": _electric_arc_descriptor,
        "heal": _heal_descriptor,
        "runic-body": _runic_body_descriptor,
        "thunderstrike": _thunderstrike_descriptor,
    }
    spell_rows = []
    for spell_id, provider in zip(
        repertoire_ids,
        providers,
        strict=True,
    ):
        spec = specs[spell_id]
        descriptor_compiler = descriptor_compilers.get(spell_id)
        descriptor = (
            descriptor_compiler(provider)
            if descriptor_compiler is not None
            else None
        )
        active = spell_id in profile["activeIds"]
        variants = _ACTION_VARIANTS[spec["actions"]]
        action_cost = variants[0] if len(variants) == 1 else None
        spell_rows.append(
            {
                "id": spell_id,
                "name": spec["name"],
                "rank": 1,
                "kind": spec["kind"],
                "actionCost": action_cost,
                "rawActionCost": spec["actions"],
                "actionVariants": list(variants),
                "traits": list(spec["traits"]),
                "traditions": list(spec["traditions"]),
                "repertoireAuthorization": {
                    "mode": "tradition",
                    "tradition": profile["tradition"],
                },
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

    body = {
        "schema": 1,
        "kind": "pf2er-prepared-spellcasting-compilation",
        "familyId": FAMILY_ID,
        "compilerId": COMPILER_ID,
        "supportState": "partial-runtime",
        "compileSupported": True,
        "runtimeActivation": {
            "status": "partial",
            "executableSpellIds": list(profile["activeIds"]),
            "deferredSpellIds": [
                spell_id
                for spell_id in repertoire_ids
                if spell_id not in profile["activeIds"]
            ],
        },
        "source": carrier["consumer"].receipt.as_serialized(),
        "casting": {
            "id": profile["castingId"],
            "mode": "prepared",
            "tradition": profile["tradition"],
            "dc": carrier["dc"],
            "attack": (
                carrier["attack"]
                if carrier["attack"] is not None
                else carrier["dc"] - 10
            ),
            "attackEvidence": (
                {
                    "mode": "authored",
                    "authoredMemberPresent": True,
                    "value": carrier["attack"],
                }
                if carrier["attack"] is not None
                else {
                    "mode": "derived",
                    "authoredMemberPresent": False,
                    "inputDc": carrier["dc"],
                    "formula": "DC - 10",
                    "value": carrier["dc"] - 10,
                    "rule": {
                        "id": "dc-from-modifier",
                        "source": next(
                            rule
                            for rule in governing_rules
                            if rule.rule_id == "dc-from-modifier"
                        ).receipt.as_serialized(),
                    },
                }
            ),
            "preparedSpells": carrier["preparedSpells"],
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
            "authorityDigest": carrier[
                "consumer"
            ].carrier.authority_digest,
            "selectionDigest": _projection_digest(
                {
                    "consumer": carrier["consumer"].receipt.digest,
                    "providers": [
                        provider.receipt.digest
                        for provider in providers
                    ],
                    "rules": [
                        rule.receipt.digest
                        for rule in governing_rules
                    ],
                }
            ),
        },
    }
    return {**body, "digest": _projection_digest(body)}


class _ImmutableArtifactType(type):
    def __setattr__(cls, _name: str, _value: object) -> None:
        raise TypeError("prepared-spellcasting artifact class is immutable")

    def __delattr__(cls, _name: str) -> None:
        raise TypeError("prepared-spellcasting artifact class is immutable")


@final
class CompiledPreparedSpellcasting(metaclass=_ImmutableArtifactType):
    """One immutable, authority-backed prepared repertoire artifact."""

    __slots__ = ("_projection_digest", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "CompiledPreparedSpellcasting can only be created by "
            "compile_prepared_spellcasting()"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError(
            "CompiledPreparedSpellcasting subclasses are unsupported"
        )

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("CompiledPreparedSpellcasting is immutable")

    def __delattr__(self, _name: str) -> None:
        raise TypeError("CompiledPreparedSpellcasting is immutable")

    def as_serialized(self) -> dict[str, Any]:
        return _artifact_projection(self)

    @property
    def normalized(self) -> MappingProxyType[str, Any]:
        value = _artifact_projection(self)

        def freeze(item: Any) -> Any:
            if type(item) is dict:
                return MappingProxyType(
                    {key: freeze(child) for key, child in item.items()}
                )
            if type(item) is list:
                return tuple(freeze(child) for child in item)
            if item is None or type(item) in (bool, int, str):
                return item
            raise TypeError("prepared projection must be closed JSON")

        frozen = freeze(value)
        if type(frozen) is not MappingProxyType:
            raise PreparedSpellcastingArtifactError(
                "normalized prepared projection lost its object root"
            )
        return frozen


_ARTIFACTS: WeakKeyDictionary[
    CompiledPreparedSpellcasting,
    tuple[SourceAuthorityAdapter, VerifiedSourceSelection, str],
] = WeakKeyDictionary()


def _bind_compiler() -> tuple[
    Callable[
        [VerifiedSourceSelection, SourceAuthorityAdapter],
        CompiledPreparedSpellcasting,
    ],
    Callable[[CompiledPreparedSpellcasting], dict[str, Any]],
]:
    profiles = {
        locator: {
            **profile,
            "providerSpecs": tuple(
                dict(spec)
                for spec in profile["providerSpecs"]
            ),
            "providerRequirements": tuple(
                profile["providerRequirements"]
            ),
            "governingRequirements": tuple(
                profile["governingRequirements"]
            ),
        }
        for locator, profile in _CARRIER_PROFILES.items()
    }
    registry = _ARTIFACTS

    def derive(
        consumer: VerifiedSourceSelection,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        return _derive_projection(
            consumer,
            authority,
            profiles=profiles,
        )

    def compile_prepared_spellcasting(
        consumer: VerifiedSourceSelection,
        authority: SourceAuthorityAdapter,
        /,
    ) -> CompiledPreparedSpellcasting:
        if type(consumer) is not VerifiedSourceSelection:
            raise TypeError(
                "consumer must be an exact VerifiedSourceSelection"
            )
        if type(authority) is not SourceAuthorityAdapter:
            raise TypeError(
                "authority must be an exact SourceAuthorityAdapter"
            )
        projection = derive(consumer, authority)
        digest = _projection_digest(projection)
        result = object.__new__(CompiledPreparedSpellcasting)
        object.__setattr__(result, "_projection_digest", digest)
        registry[result] = (authority, consumer, digest)
        return result

    def artifact_projection(
        value: CompiledPreparedSpellcasting,
    ) -> dict[str, Any]:
        if type(value) is not CompiledPreparedSpellcasting:
            raise TypeError(
                "artifact must be exact CompiledPreparedSpellcasting"
            )
        try:
            authority, consumer, expected = registry[value]
        except KeyError as failure:
            raise PreparedSpellcastingArtifactError(
                "artifact is not registered with this compiler"
            ) from failure
        if object.__getattribute__(
            value,
            "_projection_digest",
        ) != expected:
            raise PreparedSpellcastingArtifactError(
                "artifact projection digest changed"
            )
        try:
            projection = derive(consumer, authority)
        except (SourceAuthorityError, TypeError, ValueError) as failure:
            raise PreparedSpellcastingArtifactError(
                "artifact source authority no longer validates"
            ) from failure
        if _projection_digest(projection) != expected:
            raise PreparedSpellcastingArtifactError(
                "artifact normalized projection changed"
            )
        return projection

    return compile_prepared_spellcasting, artifact_projection


(
    compile_prepared_spellcasting,
    _artifact_projection,
) = _bind_compiler()


__all__ = [
    "AIUVARIN_ELEMENTALIST_LOCATOR",
    "COMPILER_ID",
    "CompiledPreparedSpellcasting",
    "FAMILY_ID",
    "LIZARDFOLK_STARGAZER_LOCATOR",
    "PreparedSpellcastingArtifactError",
    "PreparedSpellcastingLinkError",
    "PreparedSpellcastingSourceError",
    "compile_prepared_spellcasting",
]

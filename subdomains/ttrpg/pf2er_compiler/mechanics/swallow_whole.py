"""Authority-backed compilation for the Core MC1 Swallow Whole family.

The Core MC1 corpus contains eighteen direct ``Swallow Whole`` productions.
This module compiles those exact productions from one server-owned
``SourceAuthorityAdapter`` and links each one to its exact local Grab or
Improved Grab melee carrier.  Callers cannot supply creature fields, strike
maps, glossary text, or provider mappings.

Compilation and linking deliberately stop before execution.  Target state,
capacity, checks, periodic damage, Escape, suffocation, Rupture, ejection,
and corpse extraction remain explicit typed deferrals.  There is no registry
fragment, activation hook, legacy source packet, or runtime resolver here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal, TypeAlias, final

from .contracts import RawSourceArray, RawSourceMember, RawSourceObject
from .source_authority import (
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)


FAMILY_ID = "swallow-whole"
COMPILER_ID = "swallow-whole-authority-v2"
MECHANIC_TYPE = "swallow-whole-source-family"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"
CONSUMER_REQUIREMENT_COUNT = 18
FEEDER_REQUIREMENT_COUNT = 19
RELATED_REQUIREMENT_COUNT = 16
PROVIDER_REQUIREMENT_COUNT = 27
MAX_DAMAGE_COMPONENTS = 2

ProviderPhase: TypeAlias = Literal[
    "compile-classification",
    "compile-link",
    "compile-semantics",
    "runtime-context",
]
TraitSource: TypeAlias = Literal["local", "monster-core-glossary"]
GrabKind: TypeAlias = Literal["grab", "improved-grab"]
RelatedKind: TypeAlias = Literal["variant", "near-miss"]
DeferralPhase: TypeAlias = Literal["source-link", "runtime"]

_SIZE_RANKS = {
    "Tiny": 0,
    "Small": 1,
    "Medium": 2,
    "Large": 3,
    "Huge": 4,
    "Gargantuan": 5,
}
_DAMAGE_RE = re.compile(
    r"(?P<count>[1-9][0-9]*)d(?P<sides>[1-9][0-9]*)"
    r"(?P<modifier>[+-](?:0|[1-9][0-9]*))? "
    r"(?P<damage_type>[a-z]+)",
    re.ASCII,
)
_DESCRIPTION_RE = re.compile(
    r"(?P<size>Tiny|Small|Medium|Large|Huge|Gargantuan), "
    r"(?P<damage>.+), Rupture (?P<rupture>[1-9][0-9]*) "
    r"\(page 360\)",
    re.ASCII,
)
_ATHLETICS_RE = re.compile(r"Athletics \+(?P<modifier>[0-9]+)", re.ASCII)
_ATTACK_RE = re.compile(r"\+(?P<modifier>[0-9]+)", re.ASCII)


@dataclass(frozen=True, slots=True)
class _ConsumerSpec:
    rule_id: str
    locator: str
    carrier_path: tuple[tuple[str, int], ...]
    creature_name: str
    creature_sha256: str
    ability_ordinal: int
    ability_member_sha256: str
    ability_value_sha256: str
    trait_source: TraitSource
    maximum_size: str
    damage_source_texts: tuple[str, ...]
    rupture: int
    armor_class: int
    athletics_source_text: str
    athletics_modifier: int


@dataclass(frozen=True, slots=True)
class _FeederSpec:
    rule_id: str
    creature_name: str
    melee_ordinal: int
    item_ordinal: int
    damage_ordinal: int
    strike_name: str
    attack_source_text: str
    damage_source_text: str
    grab_kind: GrabKind
    anatomy_eligible: bool
    block_sha256: str
    member_sha256: str
    value_sha256: str


@dataclass(frozen=True, slots=True)
class _RelatedSpec:
    rule_id: str
    kind: RelatedKind
    classification: str
    locator: str
    carrier_path: tuple[tuple[str, int], ...]
    creature_name: str
    raw_key: str
    member_ordinal: int
    block_sha256: str
    member_sha256: str
    value_sha256: str


@dataclass(frozen=True, slots=True)
class _ProviderSpec:
    rule_id: str
    source_id: str
    locator: str
    carrier_path: tuple[tuple[str, int], ...]
    block_sha256: str
    phase: ProviderPhase
    purpose: str


_CONSUMER_SPECS = (
    _ConsumerSpec(
        "swallow-whole:cave-worm", "54.2", (("^.creature", 1),),
        "Cave Worm",
        "21db440415be6758bb0e73a17c09cdfbc4954ab78ddb7dcfaf1df3b2e6247dfd",
        26,
        "e8b4daeabd989ce0f28f0e31be0cecf9438bb93a6652a5775ae6bf365aed1637",
        "b6c5bdc974d55ba7ddc8ef91f9a4d2fb4391ef2e1a8fa106fa916618ca1fe14f",
        "local", "Huge", ("3d6+9 bludgeoning",), 24, 32,
        "Athletics +30", 30,
    ),
    _ConsumerSpec(
        "swallow-whole:benthic-worm", "56.2", (("^.creature", 1),),
        "Benthic Worm",
        "38a18196a24ccfeacc170c5bfb572d9cdd5e5d823b60d8db090907b78b44ceca",
        24,
        "0588fa6688988219571d4d3144df5599ab40561ad06b28ccc3c2a656ccc76e54",
        "6a73587e13716e20e42c3ebe15f04a3d408280f156c0cd0816f7fb6bb00b32f8",
        "local", "Huge", ("3d8+10 bludgeoning",), 27, 35,
        "Athletics +33", 33,
    ),
    _ConsumerSpec(
        "swallow-whole:magma-worm", "57.2", (("^.creature", 2),),
        "Magma Worm",
        "e8940aaaccc4613ce509a6b6e81b8733290b5a5649ccfc56bce6b48bff3827c5",
        29,
        "d950379d9c7267cc3764aaec1a0d3ce4849ab9be5346dd1dc0774d806af4d2d7",
        "c25a3ed97922945cdc528e628b376bd191bb9d9fe0ea7fdb0a604c058ec14c1d",
        "local", "Huge",
        ("3d10+10 bludgeoning", "2d6 fire"), 36, 40,
        "Athletics +38", 38,
    ),
    _ConsumerSpec(
        "swallow-whole:deinosuchus", "69.6", (("^.creature", 1),),
        "Deinosuchus",
        "0360b496312745d9fbdce7d652c1be4b5d7ded6dfa68026542370471683e14a5",
        21,
        "5ba71c8ddebea8feabd79a43c89a0960f14426361a1571ad4b44ad5566039e2d",
        "39d573648044687b20a446bb7da2a927938119d1dcc6f633ddced80e68b10dbc",
        "local", "Large", ("2d8+7 bludgeoning",), 18, 26,
        "Athletics +20", 20,
    ),
    _ConsumerSpec(
        "swallow-whole:tyrannosaurus", "101.2", (("^.creature", 1),),
        "Tyrannosaurus",
        "c7ac4e2fa265dc76211a1d231f314edc3bb62de7018f517f761e328087d9db7b",
        21,
        "92fe49de208521a3c62bdfdcc57eba2a8fdc47f891dc4105001ee006964fa21e",
        "5dd4db600192bfa718fbd3551eecfcd659281104c58419865af39cedfd9e9df5",
        "local", "Medium", ("3d6+8 bludgeoning",), 26, 29,
        "Athletics +24", 24,
    ),
    _ConsumerSpec(
        "swallow-whole:young-adamantine-dragon", "108.5",
        (("^.creature", 0),), "Young Adamantine Dragon",
        "bcca5fd723f6d78876f227348d6928c4405d3a0c5bcb9a2cc24c90194271ac3d",
        32,
        "4acd2c5b3a0a8232d3a169eaaeeabfa7537bb005b5044b92c5ee3c1531336938",
        "22794aad2f5d0f365335eecd944614755613183ebf4b1e3073d0f67624c64c33",
        "monster-core-glossary", "Medium",
        ("2d12+4 bludgeoning",), 22, 27, "Athletics +21", 21,
    ),
    _ConsumerSpec(
        "swallow-whole:adult-adamantine-dragon", "109.2",
        (("^.creature", 0),), "Adult Adamantine Dragon",
        "66ec0887183736dd2e6f70bc54da3b88a2316099931a1720c48c7f83a0fdadae",
        32,
        "9a6b052e7f73308c1482c7150f11c8fa88e2f9c298a5b896ca2f9778b60b5a87",
        "15e90c078c2727c4855e3b9601f82086ded8b2728651af56311f041e01b3f392",
        "monster-core-glossary", "Large",
        ("3d12+7 bludgeoning",), 29, 33, "Athletics +27", 27,
    ),
    _ConsumerSpec(
        "swallow-whole:ancient-adamantine-dragon", "109.3",
        (("^.creature", 0),), "Ancient Adamantine Dragon",
        "02ad93ffa70bd7ceb63fcf1f966a94752b067247895d0e5ae5d3c0dcd65d3bf9",
        34,
        "869d613c639919bc9f53e00b42f77e1dcb7df4e5f58ecf6e838c7713bc80c017",
        "d9b71a8d857cca770c7189bf26b2957def19b35f5788d50db8976503e1b76d87",
        "monster-core-glossary", "Large",
        ("3d12+14 bludgeoning",), 35, 41, "Athletics +36", 36,
    ),
    _ConsumerSpec(
        "swallow-whole:giant-moray-eel", "138.4", (("^.creature", 1),),
        "Giant Moray Eel",
        "3f86d98b8cc66416d218b6d6d4b0079ea51b50a7237f3ff0e7e0d74cf0aad86b",
        22,
        "aed538946860adda348a4c1b6a2c48d81c32fcd39318b826b87549f4b689bc85",
        "e3b2ad68e5b307fbdaffec845712d0034b542f53912f4928990c9d2145e3ed86",
        "local", "Small", ("1d6+6 bludgeoning",), 12, 21,
        "Athletics +13", 13,
    ),
    _ConsumerSpec(
        "swallow-whole:snapping-flytrap", "154.2",
        (("^.creature", 1),), "Snapping Flytrap",
        "5dc029cf3898e92f111bf7884519076ba0bb75d6874d6afca5130214abd26620",
        25,
        "1966450381a70a53d2b808a4b5bb56ad37db438952ee9c1d4bf8431adfcb4341",
        "74922dcf16bab9fc72ac146fa96274c3c26715a8ef054c93e3f2c06e0c5d0862",
        "local", "Medium",
        ("1d8+1 bludgeoning", "1d6 acid"), 5, 18,
        "Athletics +11", 11,
    ),
    _ConsumerSpec(
        "swallow-whole:giant-flytrap", "154.4", (("^.creature", 1),),
        "Giant Flytrap",
        "121d35d2b6a73dd52a5202754da831d3ccda466c6383499371c69b3bcccb3bd6",
        25,
        "bbf3eef6ed18b93d3936aff68dec99fd6232911d01f76754fa3f50e9ca3b9dd7",
        "6ee617b0a0f36ef223734e2a7283f1f9e9f0e60b3d184654e8eeb792d1c48e23",
        "local", "Large",
        ("2d8+3 bludgeoning", "2d6 acid"), 17, 29,
        "Athletics +23", 23,
    ),
    _ConsumerSpec(
        "swallow-whole:ogre-glutton", "250.4", (("^.creature", 1),),
        "Ogre Glutton",
        "bd89d5c03efe695ffd007a3badd1ed1710cdeaaf0cc68deab67df6d60c1899b7",
        23,
        "129ec70227feda297a86e959609473e792f3b00d9e0058aa4d970292fa6aa315",
        "951eee7ba0d4a81fec3e9ef770def5f110e6629fbcf6056490e39dc9adbbfb26",
        "local", "Small", ("2d4+4 bludgeoning",), 14, 18,
        "Athletics +12", 12,
    ),
    _ConsumerSpec(
        "swallow-whole:island-oni", "254.3", (("^.creature", 2),),
        "Island Oni",
        "4265b04ec5af63995a3486494e6f6923b16f56031cdb3931717283b1c6723eeb",
        32,
        "c870bb31c861e56e9477accab48ab07fe85c1fbbdd52ca6579a714a0fc3c11fa",
        "4de5151cbcbd726ba9538dea66d6b45843dd088900872dd99ed03234630a6b00",
        "monster-core-glossary", "Medium",
        ("3d8+10 bludgeoning",), 30, 38, "Athletics +33", 33,
    ),
    _ConsumerSpec(
        "swallow-whole:raja-krodha", "287.1", (("^.creature", 2),),
        "Raja-Krodha",
        "f203d1b496cb14c5f47138afd19d3881448f44703f18d8a1d1bf2588bae803b0",
        29,
        "7745b91afa3d85710189eaac2bfa3cce033811805aefe358fae695d4b9be71ec",
        "f0f33555f52e8c31689cff58b2d16aca69c080d1c79df9427345271149c1dbbe",
        "local", "Medium", ("2d12+6 bludgeoning",), 15, 30,
        "Athletics +19", 19,
    ),
    _ConsumerSpec(
        "swallow-whole:sea-serpent", "299.1",
        (("Sea Serpent", 1), ("Sea Serpent", 0), ("^.creature", 2)),
        "Sea Serpent",
        "e6fb5e82cdb87e23b802db0f23d0d391ab09513e888a442c0866267ff504367a",
        25,
        "e7ff4008c5f458baf8bae8ca77baac3df7213893b4cf570ecffc69fe91c084d7",
        "ed73e4207ecbdabe0e5d97a8f0ca8eee869aeed770f98cc2901dca7ffe2d426f",
        "local", "Huge", ("2d10+6 bludgeoning",), 20, 35,
        "Athletics +26 (+28 to Swim)", 26,
    ),
    _ConsumerSpec(
        "swallow-whole:megalodon", "307.4", (("^.creature", 1),),
        "Megalodon",
        "1d324828ff4e18363beb48055b3f689c7f46ee11bf24a2e6ea17883331218a6f",
        22,
        "3cdfdab5c98baad6b3793f2cbc8c4eec7ba49386b12dde780b2c57452dabd8f9",
        "09984b20992619e5646d2807e9f6eb6f1ad9b1141e671f351724141d423af2ec",
        "local", "Huge", ("2d8+5 bludgeoning",), 20, 27,
        "Athletics +21", 21,
    ),
    _ConsumerSpec(
        "swallow-whole:giant-anaconda", "317.2", (("^.creature", 1),),
        "Giant Anaconda",
        "04515e3a5da19666f1756c51fdc9077a3732e3995643886094ba9f2e209ee8d3",
        22,
        "f5b9f58b6c58802986b946059485ca1efa63c033e29a72e2897c809604cb3a1f",
        "882a96fe1a05270ee7cf3f5474b796cc5035baab9c70d703c48273b9acde0720",
        "local", "Large", ("1d10+7 bludgeoning",), 21, 25,
        "Athletics +21", 21,
    ),
    _ConsumerSpec(
        "swallow-whole:warg", "341.2", (("^.creature", 1),), "Warg",
        "11d060a1dce5a397bb5f55886984dbdaa698b1ed7d7aa841bfa52fe733964ef1",
        24,
        "979cc40bf2470695ffdde9f0e8b0236940560c7ac1067bd04b98176eb67e55b2",
        "f02c95164d51f8c6bc9f2040740f258609ba86f9c24dbdd03af4bf987ea1e7c8",
        "local", "Small", ("1d6+2 bludgeoning",), 9, 17,
        "Athletics +8", 8,
    ),
)


_FEEDER_SPECS = (
    _FeederSpec(
        "swallow-feeder:cave-worm:jaws", "Cave Worm", 19, 0, 3,
        "jaws", "+28",
        "3d10+15 piercing plus Improved Grab (page 359)",
        "improved-grab", True,
        "cc5b735f7f6e7b01b2afe31a2cfccbb05f29324f3a0518ca2db1d8a5282a3a40",
        "e7268f8f72f30b89e8b85e721719d79d56750bd5524e039f36ca52306fcfb77f",
        "45448b6047f79dd84e1ba3a3266bca957e780974fe67ddd426e7f9545cf7239e",
    ),
    _FeederSpec(
        "swallow-feeder:benthic-worm:jaws", "Benthic Worm", 20, 0, 3,
        "jaws", "+31",
        "3d12+16 piercing plus Improved Grab (page 359)",
        "improved-grab", True,
        "dea08b2883afb0b5debdbb19460fa9bfd292c50f6f192515862b9b2bc64f1f52",
        "92f892a89e5ec0e552d0c1737b164607088ae91a058866b831055144d57ea631",
        "c17c118f4b261c7fab74630689d3eac346b9cf305779e67181acb114f3c6dc3c",
    ),
    _FeederSpec(
        "swallow-feeder:magma-worm:jaws", "Magma Worm", 24, 0, 3,
        "jaws", "+36",
        "3d10+18 piercing plus 2d6 fire and Improved Grab (page 359)",
        "improved-grab", True,
        "da6546351b291bdf1cbbb3d7af66f19eb374b129b9f29792978336e11531f812",
        "d5af9bfb1976d5605c5d64fdab901bc97fc2c54480a30f8f0078c88a5fe2f03a",
        "b44f8d852390d53d83dfec19ae15a913532a547ef479f248cde561400a23e9b7",
    ),
    _FeederSpec(
        "swallow-feeder:deinosuchus:jaws", "Deinosuchus", 19, 0, 3,
        "jaws", "+22", "2d10+13 piercing plus Grab (page 359)",
        "grab", True,
        "fd9389fb4d9c80b9ba175cb443c9c7a30cbfbfd19f4a2946a2f0bf7304b9677c",
        "ff00ad00899af247192d268ec02d4e9f68d3d425338b0116c008e4836bc2bd0d",
        "cbde465345e07fc709ece3a66d8699f57d88f5f6067664cb85beb7b242e0ea18",
    ),
    _FeederSpec(
        "swallow-feeder:tyrannosaurus:jaws", "Tyrannosaurus", 18, 0, 3,
        "jaws", "+22", "2d12+12 piercing plus Grab (page 359)",
        "grab", True,
        "e9d63b81048033d9d9f34ba2e85fb22b063b13b6dbecd2f9cc445b8be1f15650",
        "9b489d8cd5bf832a435878b15e8c8af7eb6449fa3e7a46497a1c574f794812a0",
        "1bdc110fa2363e0bef6b283c29fb414de0a1015ce1a49497c4a3a30d8c845ae7",
    ),
    _FeederSpec(
        "swallow-feeder:young-adamantine-dragon:jaws",
        "Young Adamantine Dragon", 21, 0, 3, "jaws", "+21",
        "2d12+9 piercing plus Grab (page 359)", "grab", True,
        "ed8c8b59604f1e7bde109c8e330b2d97258512cc5cbaddedf08462b6ec3a081c",
        "88eadcbf17e290a8975fe2c2505ebc032d100f37a93a9f847715c9791f7ac6df",
        "71ebaee108e3512dbf7eeb6c1bd8d6469447625dfe6cf5d194f1c15eba3da4e8",
    ),
    _FeederSpec(
        "swallow-feeder:adult-adamantine-dragon:jaws",
        "Adult Adamantine Dragon", 21, 0, 3, "jaws", "+27",
        "3d12+14 piercing plus Improved Grab (page 359)",
        "improved-grab", True,
        "474185dbabb6b2c50268f51778649ef287e74dd44142fde93fba2156164142d8",
        "af2e31e3164367d4e5ae93418c353edcbd880d48da7c1e71e1870b28b32749da",
        "6948c775c734d096db8c0eca052531d58ebaf5bbc55ec52a6cac289a726edc9b",
    ),
    _FeederSpec(
        "swallow-feeder:ancient-adamantine-dragon:jaws",
        "Ancient Adamantine Dragon", 22, 0, 3, "jaws", "+36",
        "3d12+18 piercing plus Improved Grab (page 359)",
        "improved-grab", True,
        "45d8993fe22ac3824b1448b89e165fd522a5e35168e9808470c70d3a9fa4a806",
        "9b3ea81dbe46286c2a8c003a0d8565f9b67ef5ca5e47da9c0c48a0193452a2eb",
        "43d84b2947cbd609f9528266c468c5147578b2fc729b60fc089c5b0783ebcaf7",
    ),
    _FeederSpec(
        "swallow-feeder:giant-moray-eel:jaws", "Giant Moray Eel",
        20, 0, 3, "jaws", "+15",
        "2d6+8 piercing plus Grab (page 359)", "grab", True,
        "000070786f06dea52fda7581cda8475eced1846db509f8c900bddc6e57478740",
        "e5ae339b9386bff188a32f2d6ef367ce11730d9966df12dfa0536bbce00c6c74",
        "b3ed95ac07a9accc0d6719c12aa8caa703a4002b26386f331c7d3aba42352f10",
    ),
    _FeederSpec(
        "swallow-feeder:snapping-flytrap:leaf", "Snapping Flytrap",
        22, 0, 3, "leaf", "+11",
        "1d8+2 piercing plus 1d6 acid and Improved Grab (page 359)",
        "improved-grab", True,
        "660036f86baa2fb29f782e4eb2d6c11cb7d319016e87e1747fb5b41d9f910f8b",
        "0aa0009282ed137434cba3130a79f7456480c561355575a59059c041f3eac0c2",
        "2e4a931cec5a8fff0d6eb14c62676adff7e655d8893835cf940a9b48d6937e71",
    ),
    _FeederSpec(
        "swallow-feeder:giant-flytrap:leaf", "Giant Flytrap",
        22, 0, 3, "leaf", "+23",
        "2d8+7 piercing plus 2d6 acid and Improved Grab (page 359)",
        "improved-grab", True,
        "fa05ab8670cf5c52ff393e87ceedca6802cca40f69d7e4ee33035457052e7ed4",
        "a1590977ac94a4105ce2d4aae90e60383783aca6dc89c00cd9f373839222124d",
        "0bc645f4a3201ba394b3339640c0c8d18cfe99e32603fb24e87997ccf5ef9697",
    ),
    _FeederSpec(
        "swallow-feeder:ogre-glutton:jaws", "Ogre Glutton",
        20, 1, 2, "jaws", "+14",
        "1d8+8 piercing plus Grab (page 359) and glutton's feast",
        "grab", True,
        "5d1a702d18559abe8421f180013c95eb0be809d78f9d0b709ce9e9fe70d67086",
        "97b78040e342853c92e38beee2acc4e1fccfe2b4927029dbfc77359736c284f0",
        "369b9b82cae3031cd3839bde7c56647ad5fd8111e98a721a0d781fe028704a72",
    ),
    _FeederSpec(
        "swallow-feeder:island-oni:jaws", "Island Oni",
        26, 1, 3, "jaws", "+33",
        "3d6+10 piercing plus 2d6 persistent electricity and "
        "Improved Grab (page 359)", "improved-grab", True,
        "bc1318eadf7db9b6b35c203fa40b4c6e51044b88297160bc4e674905ec7f1279",
        "3824a8213c9c4cdce0d7630d6a6d40c5c07a7df721c248e30fcf4ac84e278832",
        "4914f71d6ab9c22cf7b4c786a88e4a2d77b7e6a3b72f1c69422f7ee5768b2a54",
    ),
    _FeederSpec(
        "swallow-feeder:raja-krodha:fangs", "Raja-Krodha",
        24, 1, 3, "fangs", "+20",
        "2d6+12 piercing plus Grab (page 359)", "grab", True,
        "b8803e85799b0182ec731835074b37cea020305c8dc729a5381f907b7e7e1a44",
        "1872012723803848f5d0b50cb6c45bb9355adcc6f4894016ff38b5913a75d45a",
        "bb9d595ffaf80c83866a576ef686c9db661d1eaf7eb6723c24b72fe7f6624c9b",
    ),
    _FeederSpec(
        "swallow-feeder:sea-serpent:jaws", "Sea Serpent",
        19, 0, 3, "jaws", "+27",
        "3d10+14 piercing plus Grab (page 359)", "grab", True,
        "9b4143ec51a3ec905e33533949972fc854956c76a7bd5acf691f6e90e8383c52",
        "44cc7707500461c114b0e003c454e0e051b32f5144044a59953dedac1ea65944",
        "6f4ec997d3646c4824e7643f3b355f3a118651fe6e010175d319933057a30565",
    ),
    _FeederSpec(
        "swallow-feeder:sea-serpent:tail", "Sea Serpent",
        19, 1, 3, "tail", "+27",
        "2d10+14 bludgeoning plus Grab (page 359)", "grab", False,
        "508344cc6f894d611de7f8427e355486f2f35ac89643c673f339bfabb4d05323",
        "804a7d001dbcdff76f18c4be3d2367f6adb6c2bd1111cd173ce83ef438f83d33",
        "d084b8d1d85f956b2050fe7b40216f2e1d0b7d4c2468e756e1872bba0912dd95",
    ),
    _FeederSpec(
        "swallow-feeder:megalodon:jaws", "Megalodon",
        19, 0, 3, "jaws", "+22",
        "2d12+10 piercing plus Improved Grab (page 359)",
        "improved-grab", True,
        "96c75775eae36bb319fdf841e5717afab725b8c7dd562fffc27cff07e08bd07d",
        "e3457de243134be11494f43c52c114a9b5c7008f75ffe06430340212e6d18be5",
        "1e2cda49168b3c98b938474be4cb0babc889a3f8ddceed13aca4dd22228e00f1",
    ),
    _FeederSpec(
        "swallow-feeder:giant-anaconda:jaws", "Giant Anaconda",
        19, 0, 3, "jaws", "+19",
        "2d10+7 piercing plus Grab (page 359)", "grab", True,
        "f2d6f6cfce54634e6d66b378d140e0a8d54448b9804403f5d8ad9dcf50202f7b",
        "9575c920dfc0a90f78f42d6b9a630a2dfc3a894f604c76b0c63841817c74861c",
        "bc4a1be2f46f9bb45424cef6c4ad4e2e777f72432876a595456d808219f2e122",
    ),
    _FeederSpec(
        "swallow-feeder:warg:jaws", "Warg", 22, 0, 2,
        "jaws", "+11", "1d8+4 piercing plus Grab (page 359)",
        "grab", True,
        "4714135d9f53b813c1000a070ec2eb97c208cc90f051eefb0619e0a6df7cbd65",
        "9d7cc311876a2a35ffdc7fc165ecbee9b2faa16c6f96ea5eeb733bd0bc04d8d2",
        "33026141995e058eacd376c12480b5c757c9bf2902214663b2cc471e7b4eb375",
    ),
)


def _variant(
    rule_id: str,
    creature_name: str,
    raw_key: str,
    member_ordinal: int,
    member_sha256: str,
    value_sha256: str,
) -> _RelatedSpec:
    consumer = next(
        item for item in _CONSUMER_SPECS
        if item.creature_name == creature_name
    )
    return _RelatedSpec(
        rule_id, "variant", "local-swallow-extension",
        consumer.locator, consumer.carrier_path, creature_name, raw_key,
        member_ordinal, consumer.creature_sha256, member_sha256,
        value_sha256,
    )


_RELATED_SPECS = (
    _variant(
        "swallow-related:cave-worm:regurgitate", "Cave Worm",
        "!.Regurgitate", 22,
        "e2f5f4b999657bb092bc80752bcc7af82b61c77360458fdc94e48c168f724c5f",
        "1c135fe5a1139e5693b051f8807f554d44487b209e2e559e6e8cb72a855dff0a",
    ),
    _variant(
        "swallow-related:cave-worm:fast-swallow", "Cave Worm",
        "!.Fast Swallow", 25,
        "18a70fbb2d9f30f8e36f25d6b1ddff3fbd8346c58536c82058c2a533b91b26dd",
        "a728849ae6a18c281e1f0995f306609a54b96e2faa047acfb03d1b7a7c4149ad",
    ),
    _variant(
        "swallow-related:benthic-worm:breach", "Benthic Worm",
        "!.Breach", 22,
        "253c07cbae3eefe3fa1f1690d4179907423a8bca7fad1068ec164db857ccae5b",
        "76a00e81dd03e0ad901c9cca4adb098139b7ffe5747ac21b48f6d491615ef4c5",
    ),
    _variant(
        "swallow-related:benthic-worm:fast-swallow", "Benthic Worm",
        "!.Fast Swallow", 23,
        "3a87193ff083a085c7802500cbc6c9b3274c3e341fadcd423af35829c67becdc",
        "ed98af9fd15205529ea27308c8b1e3a0b9feef70728937a96d36c8406b99fe3f",
    ),
    _variant(
        "swallow-related:magma-worm:fast-swallow", "Magma Worm",
        "!.Fast Swallow", 25,
        "3a87193ff083a085c7802500cbc6c9b3274c3e341fadcd423af35829c67becdc",
        "ed98af9fd15205529ea27308c8b1e3a0b9feef70728937a96d36c8406b99fe3f",
    ),
    _variant(
        "swallow-related:tyrannosaurus:pin-prey", "Tyrannosaurus",
        "!.Pin Prey", 20,
        "23b53d7028dca02663fa5227399b3ab2231ff18e3bf780d100bcf9874e49ce81",
        "f1bab925097db71a31c19ec1735ed5b74dd6170ff5b8b31c6714282c685bb68e",
    ),
    _variant(
        "swallow-related:ancient-adamantine-dragon:fast-swallow",
        "Ancient Adamantine Dragon", "!.Fast Swallow", 30,
        "960f9102d9fdd1bfe598fc3a03cb9ccfcac63335fea303416dde97aaebc1b304",
        "021c0f49f69a7f3ef256ac1014983c1e268d9f25f71599aaf46c8592a47a7ec8",
    ),
    _variant(
        "swallow-related:giant-moray-eel:pharyngeal-jaws",
        "Giant Moray Eel", "!.Pharyngeal Jaws", 21,
        "ecaf7beba98ede2f315bd37338ef78412b42eb7dda2a8112aae9a8658eab889b",
        "6cca4612914ce3d2ec462f3fb3c7a299f5b408cd9460ba726ec6d59deb57b688",
    ),
    _variant(
        "swallow-related:snapping-flytrap:quick-capture",
        "Snapping Flytrap", "!.Quick Capture", 20,
        "ed26922516e49f9bc53ca664ce7c5f4e7980addc91bacc49d5651b0d94c3520a",
        "5c40da5043c975a22704f7a5c7404d71c1d4937d8da9f8d7a657da9999703ad7",
    ),
    _variant(
        "swallow-related:giant-flytrap:quick-capture",
        "Giant Flytrap", "!.Quick Capture", 20,
        "1a1b24a658fe99ac4ae2c6d1d1359efdda1949611f16d57b31c1b2ea684b148d",
        "1473e8e4bf645c17ced9f4c10dee90fa9b50f4ea915035e4ae67e9c520dc0709",
    ),
    _variant(
        "swallow-related:ogre-glutton:gluttons-feast", "Ogre Glutton",
        "!.Glutton's Feast", 21,
        "24852999491e0b04e4b37e6259410b8faa81fcb31560842d59af04f42aadc68a",
        "f9b9498b43cf38d4bcbb5400ab0e7511abbc30ef8ba4528cbfb95579343a9e92",
    ),
    _variant(
        "swallow-related:island-oni:electrifying-pierce", "Island Oni",
        "!.Electrifying Pierce", 31,
        "1b9f2440540adac0dc6019d0fc9ec78b6d022409c369cceba6fe1d2196574edd",
        "a29d38261d97971fcb67c6bdb10cd816e6dbb5e389dedecca3e0f93919182094",
    ),
    _variant(
        "swallow-related:megalodon:breach", "Megalodon", "!.Breach", 20,
        "b61658f0f717ac2275047d5bf6f8e6689902aa4e56305633ee4a88e73f867a7f",
        "65cd885ee311f2c6f3ae6e1d9ade2ac4416a85083d0d747db42855ad91601f47",
    ),
    _RelatedSpec(
        "swallow-near-miss:gylou:encage-in-tentacles", "near-miss",
        "derived-similar-effects-with-explicit-exceptions", "91.2",
        (("^.creature", 1),), "Gylou", "!.Encage in Tentacles", 26,
        "ae05f9b9d3c0819204cd912b99db4cf267749a33d616c5e2742b81014d4f3fbc",
        "7d8f4992b60c8212574e4e55c6b4e62226950150ab132c59b8361c3bb454c2f2",
        "2146079f5437a07634f5c1ac2cf711d79a73ff8a63bf52c57b49950fab15adfc",
    ),
    _RelatedSpec(
        "swallow-near-miss:living-tar:engulf", "near-miss",
        "different-glossary-family-and-entry-resolution", "257.3",
        (("^.creature", 1),), "Living Tar", "!.Engulf", 23,
        "5492d8fb21e21dc227fd6af2c7025f13aa78aa96f498c27840626ce8ea174152",
        "795c338340dfda05667342b5ca452b973b7d7af03e3e53fd3182763ed7cc6b43",
        "d1f0239e793480bf24460e9b091509b310fdb0db0fe40068819fdd1e8db7a2bb",
    ),
    _RelatedSpec(
        "swallow-near-miss:grothlut:disgusting-demise", "near-miss",
        "lexical-rupture-only", "152.2", (("^.creature", 2),),
        "Grothlut", "!.Disgusting Demise", 18,
        "6582728c6d8dce3e3d4396e8cfc8c7cd0ccffb5e8628e9e018eab2fcde11e2d5",
        "96fe007b00894fa90d79bafa6adb96d3ab96b8991be819033048599b97044074",
        "f9244312b93841b4e9ae51ca56546341a4d8fa8e8896db01dda7f5fc62060ae6",
    ),
)


_PROVIDER_SPECS = (
    _ProviderSpec(
        "monster-core-engulf", "core-mc1", "358.2",
        (("^.ability", 13),),
        "ae4a1111e749ffdecee3a27b729bda2fce88ba029d143e15532f46919d878911",
        "compile-classification",
        "Distinguishes the separate Engulf family from Swallow Whole.",
    ),
    _ProviderSpec(
        "monster-core-grab", "core-mc1", "358.2",
        (("^.ability", 17),),
        "b2a7e8bff611d3f650b228714ca7f43a7de3891b9d137d87fc35fb5d5a94b431",
        "compile-link", "Defines the local Grab feeder prerequisite.",
    ),
    _ProviderSpec(
        "monster-core-improved-grab", "core-mc1", "358.2",
        (("^.ability", 19),),
        "8c586381b4ec207e318e9af1f594cbe5ae3c39b3d340e550dd799275791908db",
        "compile-link",
        "Defines the local Improved Grab feeder prerequisite.",
    ),
    _ProviderSpec(
        "monster-core-swallow-whole", "core-mc1", "358.2",
        (("^.ability", 33),),
        "fd715b7177ac44edd0fec539d5cd62ad49cecb8c42fb1a76b299684416e116a1",
        "compile-semantics",
        "Defines every authored Swallow Whole effect and cross-reference.",
    ),
    _ProviderSpec(
        "player-core-bulk", "core-pc1", "269.1", (),
        "6448a7799bdc2bd8ead30b81d71599be8040bf688542b2b8849548755dd17f89",
        "runtime-context", "Defines the Light Bulk limit on internal attacks.",
    ),
    _ProviderSpec(
        "player-core-casting-spells", "core-pc1", "299.2", (),
        "e72af12260d392ccd01ddb21c5e0ac2d5c77b75b4cd55be9145c6cc1a36ad21b",
        "runtime-context",
        "Defines Cast a Spell activities used internally and for Rupture.",
    ),
    _ProviderSpec(
        "player-core-compare-check-to-dc", "core-pc1", "401.2", (),
        "9ff024bc6158c6efc6b6bdc906ee9a00261adfaae0e80f41e1a09bbd7daafd09",
        "runtime-context",
        "Defines Athletics check comparison against Reflex DC.",
    ),
    _ProviderSpec(
        "player-core-degrees-of-success", "core-pc1", "401.4", (),
        "05a8ea41e782723a63bed00663d4a4ffadfb446edf869af24b4f2f8a61d3c033",
        "runtime-context",
        "Defines success adjudication for the Athletics check.",
    ),
    _ProviderSpec(
        "player-core-attack-rolls-map", "core-pc1", "402.1", (),
        "9cee690b7622ad76a92678b16cacada0c963ba08172569a6bde16aaff0e5f42e",
        "runtime-context",
        "Defines the attack-trait multiple attack penalty.",
    ),
    _ProviderSpec(
        "player-core-defenses", "core-pc1", "404.1", (),
        "711bf9ea76187cd3bc4040c06867a23efe04f111779b6717a4ac375aa3759239",
        "runtime-context",
        "Defines AC and defense handling for internal attacks.",
    ),
    _ProviderSpec(
        "player-core-skill-checks", "core-pc1", "405.2", (),
        "a79c8fd08dccede98367c78bc73054d22f0dfe0826deb18a9eae02e763557c05",
        "runtime-context", "Defines the Athletics skill check.",
    ),
    _ProviderSpec(
        "player-core-damage-rolls", "core-pc1", "406.1", (),
        "c5324ca52f558006c5cb9c141a859291afc36c5fd5e3c389c178c40c02c899f4",
        "runtime-context", "Defines internal and periodic damage rolls.",
    ),
    _ProviderSpec(
        "player-core-apply-damage-defenses", "core-pc1", "407.3", (),
        "70d4b59f1e222320d84c65c73eee11d14210e6800d7ecdbd3ce000da6f13bc21",
        "runtime-context", "Defines post-defense damage used by Rupture.",
    ),
    _ProviderSpec(
        "player-core-damage-types", "core-pc1", "409.1", (),
        "b5e918eb06281d4b10f2a3f157110a16e86f31b85fa6efab2e9c9b6bfbf64200",
        "runtime-context",
        "Defines piercing and slashing Rupture eligibility.",
    ),
    _ProviderSpec(
        "player-core-death", "core-pc1", "411.5", (),
        "8e5345869b2c669d96672f75ddd62644b74a8cbb5aefe3a488fd549972c0c27d",
        "runtime-context",
        "Defines the death state that enables corpse extraction.",
    ),
    _ProviderSpec(
        "player-core-actions", "core-pc1", "414.1", (),
        "57b6ebdb98b389cefba4727fde8d79cb29065e0ba1a0590a0ce95cd1f99db111",
        "compile-semantics",
        "Defines the single-action grammar and action spending.",
    ),
    _ProviderSpec(
        "player-core-escape", "core-pc1", "416.6", (),
        "af85aa2310e998039ea5c6fd99b718ea3e3a10fdc2da76eff951d21a7871fad3",
        "runtime-context", "Defines Escape checks and exit handling.",
    ),
    _ProviderSpec(
        "player-core-strike", "core-pc1", "418.4", (),
        "4cea8c4d82ad0a9ea60102ae21613d1e401270c1b2e6d97ad7fc10041bda273a",
        "runtime-context",
        "Defines internal Strikes and attack restrictions.",
    ),
    _ProviderSpec(
        "player-core-size-space", "core-pc1", "421.8", (),
        "57f6c8bd51c2367bedfda5464ec295229a54363d5576a671fbda1fda3ab01fb6",
        "runtime-context", "Defines size categories used by capacity.",
    ),
    _ProviderSpec(
        "player-core-creature-space", "core-pc1", "422.3", (),
        "62ef4117bd8ca96e49011793c59b7325af76e8c57f60291aa0f0cd7e1b07a3e0",
        "runtime-context",
        "Defines creature spaces used for ejection placement.",
    ),
    _ProviderSpec(
        "player-core-end-turn", "core-pc1", "436.3", (),
        "6eb87a6eb2e19b10947a84a7f74c951a14abfe76831e37300709ede7fdb77140",
        "runtime-context", "Defines the end-of-turn damage cadence.",
    ),
    _ProviderSpec(
        "player-core-suffocation", "core-pc1", "437.8", (),
        "79f5413549b1bf2372ea937fd631a794ba90b613347e35a1de585b53c85a317f",
        "runtime-context", "Defines breath depletion and suffocation.",
    ),
    _ProviderSpec(
        "player-core-grabbed", "core-pc1", "444.5", (),
        "902cfc2c6b22dd6fe7aafd8e9c58aeccdf6f2c23db9877b9a86c81f830b6e1a9",
        "runtime-context",
        "Defines the swallowed grabbed state and prerequisite.",
    ),
    _ProviderSpec(
        "player-core-immobilized", "core-pc1", "444.9", (),
        "41ad939e731fef9bbe5bfef0ef381dd96edff7621c5102a25b87c187106655a1",
        "runtime-context",
        "Defines movement restriction inherited from Grab.",
    ),
    _ProviderSpec(
        "player-core-off-guard", "core-pc1", "445.2", (),
        "9de2e5a3c7821e4d541d8bf3d3a13e33fda3b36b76392fbf836df870985cdcf8",
        "runtime-context",
        "Defines the swallower being off-guard to internal attacks.",
    ),
    _ProviderSpec(
        "player-core-restrained", "core-pc1", "446.3", (),
        "73cf05f20dc1dd7f29afb7aff62c5ee3c1eb9036787b0786d0e295f15670381c",
        "runtime-context", "Defines the alternate restrained prerequisite.",
    ),
    _ProviderSpec(
        "player-core-slowed", "core-pc1", "446.5", (),
        "fe97d48614b792dc6cd10b3ea912550acb28445a43962574656b9ec265bf41fb",
        "runtime-context", "Defines slowed 1 while swallowed.",
    ),
)


_DEFERRAL_SPECS = (
    (
        "feeder-strike-link", "source-link",
        ("monster-core-grab", "monster-core-improved-grab"),
        "Select the one anatomy-eligible local Grab-bearing melee carrier.",
    ),
    (
        "target-prerequisite-and-capacity", "runtime",
        (
            "monster-core-swallow-whole", "monster-core-grab",
            "player-core-size-space", "player-core-grabbed",
            "player-core-restrained",
        ),
        "Bind target identity, feeder-held state, size, and remaining capacity.",
    ),
    (
        "athletics-versus-reflex", "runtime",
        (
            "monster-core-swallow-whole",
            "player-core-compare-check-to-dc",
            "player-core-degrees-of-success",
            "player-core-attack-rolls-map", "player-core-skill-checks",
        ),
        "Resolve the attack-trait Athletics check against target Reflex DC.",
    ),
    (
        "mouth-occupancy-and-attack-prohibition", "runtime",
        ("monster-core-swallow-whole", "monster-core-grab"),
        "Release the feeder mouth while forbidding attacks on swallowed targets.",
    ),
    (
        "immediate-and-end-turn-damage", "runtime",
        (
            "monster-core-swallow-whole", "player-core-damage-rolls",
            "player-core-end-turn",
        ),
        "Schedule source damage on swallow and at each victim end turn.",
    ),
    (
        "swallowed-condition-state", "runtime",
        (
            "monster-core-swallow-whole", "player-core-grabbed",
            "player-core-immobilized", "player-core-slowed",
        ),
        "Apply and maintain grabbed, immobilized, and slowed 1.",
    ),
    (
        "breath-and-suffocation", "runtime",
        ("monster-core-swallow-whole", "player-core-suffocation"),
        "Track held breath and suffocation while swallowed.",
    ),
    (
        "escape-ejection-and-mouth-release", "runtime",
        (
            "monster-core-swallow-whole", "player-core-escape",
            "player-core-creature-space",
        ),
        "Resolve Escape, mouth exit, breathing, and collateral mouth release.",
    ),
    (
        "internal-action-restrictions", "runtime",
        (
            "monster-core-swallow-whole", "player-core-bulk",
            "player-core-defenses", "player-core-strike",
            "player-core-casting-spells", "player-core-off-guard",
        ),
        "Limit internal attacks and spells and apply off-guard.",
    ),
    (
        "rupture-post-defense-single-event", "runtime",
        (
            "monster-core-swallow-whole", "player-core-casting-spells",
            "player-core-damage-rolls",
            "player-core-apply-damage-defenses", "player-core-damage-types",
        ),
        "Aggregate one attack or spell after defenses and eject on Rupture.",
    ),
    (
        "death-corpse-extraction", "runtime",
        (
            "monster-core-swallow-whole", "player-core-death",
            "player-core-actions", "player-core-strike",
            "player-core-damage-types",
        ),
        "Resolve adjacent combined three-action cutting extraction.",
    ),
    (
        "local-variant-runtime", "runtime",
        ("monster-core-swallow-whole",),
        "Implement each separately authenticated local extension ability.",
    ),
)


class SwallowWholeCompileError(ValueError):
    """Authenticated source differs from the reviewed Swallow Whole family."""


@final
@dataclass(frozen=True, slots=True, init=False)
class SwallowWholeDamage:
    source_text: str
    dice_count: int
    die_sides: int
    modifier: int
    damage_type: str


@final
@dataclass(frozen=True, slots=True, init=False)
class SwallowWholeFeederCandidate:
    rule_id: str
    strike_name: str
    attack_modifier: int
    attack_source_text: str
    damage_source_text: str
    grab_kind: GrabKind
    anatomy_eligible: bool
    status: Literal["candidate"]


@final
@dataclass(frozen=True, slots=True, init=False)
class SwallowWholeDeferral:
    mechanic_id: str
    phase: DeferralPhase
    provider_rule_ids: tuple[str, ...]
    blocking_reason: str
    status: Literal["deferred"]


@final
@dataclass(frozen=True, slots=True, init=False)
class SwallowWholeProviderDependency:
    rule_id: str
    source_id: str
    locator: str
    phase: ProviderPhase
    purpose: str


@final
@dataclass(frozen=True, slots=True, init=False)
class CompiledSwallowWhole:
    source_id: str
    locator: str
    creature_name: str
    action_cost: int
    traits: tuple[str, ...]
    trait_source: TraitSource
    maximum_target_size: str
    maximum_target_size_rank: int
    internal_damage: tuple[SwallowWholeDamage, ...]
    rupture_threshold: int
    rupture_damage_types: tuple[str, ...]
    armor_class: int
    athletics_modifier: int
    escape_dc: int
    feeder_candidates: tuple[SwallowWholeFeederCandidate, ...]
    consumer_rule: VerifiedRuleReceipt
    feeder_rules: tuple[VerifiedRuleReceipt, ...]
    related_rules: tuple[VerifiedRuleReceipt, ...]
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    deferrals: tuple[SwallowWholeDeferral, ...]
    runtime_ready: bool
    _authority: SourceAuthorityAdapter = field(repr=False, compare=False)

    def as_serialized(
        self,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        raise TypeError("compiled Swallow Whole contract is not bound")


@final
@dataclass(frozen=True, slots=True, init=False)
class LinkedSwallowWhole:
    compiled: CompiledSwallowWhole
    selected_feeder: SwallowWholeFeederCandidate
    selected_feeder_rule: VerifiedRuleReceipt
    rejected_feeders: tuple[SwallowWholeFeederCandidate, ...]
    deferrals: tuple[SwallowWholeDeferral, ...]
    runtime_ready: bool
    _authority: SourceAuthorityAdapter = field(repr=False, compare=False)

    def as_serialized(
        self,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        raise TypeError("linked Swallow Whole contract is not bound")


_OPAQUE_TYPES = (
    SwallowWholeDamage,
    SwallowWholeFeederCandidate,
    SwallowWholeDeferral,
    SwallowWholeProviderDependency,
    CompiledSwallowWhole,
    LinkedSwallowWhole,
)


def _deny_init(_self: object, *_args: object, **_kwargs: object) -> None:
    raise TypeError("Swallow Whole contracts are compiler-created")


def _deny_subclass(_cls: type, **_kwargs: object) -> None:
    raise TypeError("Swallow Whole contract subclasses are not supported")


def _deny_copy(_self: object) -> object:
    raise TypeError("Swallow Whole contracts cannot be copied")


def _deny_deepcopy(_self: object, _memo: dict[int, object]) -> object:
    raise TypeError("Swallow Whole contracts cannot be copied")


def _deny_reduce(_self: object, *_args: object) -> object:
    raise TypeError("Swallow Whole contracts cannot be pickled")


for _opaque_type in _OPAQUE_TYPES:
    _opaque_type.__init__ = _deny_init
    _opaque_type.__init_subclass__ = classmethod(_deny_subclass)
    _opaque_type.__copy__ = _deny_copy
    _opaque_type.__deepcopy__ = _deny_deepcopy
    _opaque_type.__reduce__ = _deny_reduce
    _opaque_type.__reduce_ex__ = _deny_reduce


def _new_value(value_type: type, values: tuple[object, ...]) -> Any:
    result = object.__new__(value_type)
    slots = tuple(
        item for item in value_type.__slots__
        if item not in {"__weakref__"}
    )
    if len(slots) != len(values):
        raise AssertionError("Swallow Whole contract construction drifted")
    for slot, value in zip(slots, values):
        object.__setattr__(result, slot, value)
    return result


def _member_steps(
    path: tuple[tuple[str, int], ...],
    _step_type: type[RawMemberStep] = RawMemberStep,
) -> tuple[RawMemberStep, ...]:
    return tuple(_step_type(key, ordinal) for key, ordinal in path)


def _consumer_requirement(
    spec: _ConsumerSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _step_type: type[RawMemberStep] = RawMemberStep,
    _member_steps_impl: Any = _member_steps,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec.rule_id,
        source_id="core-mc1",
        locator=spec.locator,
        carrier_path=_member_steps_impl(spec.carrier_path),
        selection_path=(
            _step_type("!.Swallow Whole", spec.ability_ordinal),
        ),
        expected_block_sha256=spec.creature_sha256,
        expected_member_sha256=spec.ability_member_sha256,
        expected_value_sha256=spec.ability_value_sha256,
        expected_selection_sha256=spec.ability_value_sha256,
    )


def _feeder_requirement(
    consumer: _ConsumerSpec,
    spec: _FeederSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _member_step_type: type[RawMemberStep] = RawMemberStep,
    _index_step_type: type[RawIndexStep] = RawIndexStep,
    _member_steps_impl: Any = _member_steps,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec.rule_id,
        source_id="core-mc1",
        locator=consumer.locator,
        carrier_path=(
            *_member_steps_impl(consumer.carrier_path),
            _member_step_type("Melee", spec.melee_ordinal),
            _index_step_type(spec.item_ordinal),
        ),
        selection_path=(
            _member_step_type("Damage", spec.damage_ordinal),
        ),
        expected_block_sha256=spec.block_sha256,
        expected_member_sha256=spec.member_sha256,
        expected_value_sha256=spec.value_sha256,
        expected_selection_sha256=spec.value_sha256,
    )


def _related_requirement(
    spec: _RelatedSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _step_type: type[RawMemberStep] = RawMemberStep,
    _member_steps_impl: Any = _member_steps,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec.rule_id,
        source_id="core-mc1",
        locator=spec.locator,
        carrier_path=_member_steps_impl(spec.carrier_path),
        selection_path=(
            _step_type(spec.raw_key, spec.member_ordinal),
        ),
        expected_block_sha256=spec.block_sha256,
        expected_member_sha256=spec.member_sha256,
        expected_value_sha256=spec.value_sha256,
        expected_selection_sha256=spec.value_sha256,
    )


def _provider_requirement(
    spec: _ProviderSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _member_steps_impl: Any = _member_steps,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec.rule_id,
        source_id=spec.source_id,
        locator=spec.locator,
        carrier_path=_member_steps_impl(spec.carrier_path),
        expected_block_sha256=spec.block_sha256,
        expected_value_sha256=spec.block_sha256,
        expected_selection_sha256=spec.block_sha256,
    )


def _same_requirement(
    left: object,
    right: RuleRequirement,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _canonical_bytes: Any = canonical_json_bytes,
    _serialize: Any = RuleRequirement.as_serialized,
) -> bool:
    if (
        type(left) is not _requirement_type
        or type(right) is not _requirement_type
    ):
        return False
    try:
        return _canonical_bytes(_serialize(left)) == _canonical_bytes(
            _serialize(right)
        )
    except (AttributeError, RecursionError, TypeError, ValueError):
        return False


def _same_receipt(
    left: object,
    right: object,
    _receipt_type: type[SourceReceipt] = SourceReceipt,
    _canonical_bytes: Any = canonical_json_bytes,
    _serialize: Any = SourceReceipt.as_serialized,
) -> bool:
    if type(left) is not _receipt_type or type(right) is not _receipt_type:
        return False
    try:
        return _canonical_bytes(_serialize(left)) == _canonical_bytes(
            _serialize(right)
        )
    except (AttributeError, RecursionError, TypeError, ValueError):
        return False


def _raw_member(
    value: RawSourceObject,
    ordinal: int,
    key: str,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> RawSourceMember:
    if (
        type(value) is not _object_type
        or type(value.members) is not tuple
        or type(ordinal) is not int
        or ordinal < 0
        or ordinal >= len(value.members)
    ):
        raise _error_type("raw source member address is invalid")
    member = value.members[ordinal]
    if type(member) is not _member_type or member.key != key:
        raise _error_type("raw source member differs from review")
    return member


def _unique_member(
    value: RawSourceObject,
    key: str,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> RawSourceMember:
    matches = tuple(
        member
        for member in value.members
        if type(member) is _member_type and member.key == key
    )
    if len(matches) != 1:
        raise _error_type(
            f"expected one exact raw source member: {key}"
        )
    return matches[0]


def _parse_damage(
    source_text: str,
    _damage_re: re.Pattern[str] = _DAMAGE_RE,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> tuple[int, int, int, str]:
    if type(source_text) is not str:
        raise _error_type("damage source text must be exact text")
    match = _damage_re.fullmatch(source_text)
    if match is None:
        raise _error_type("damage source text is not canonical")
    count = int(match.group("count"))
    sides = int(match.group("sides"))
    modifier = int(match.group("modifier") or "0")
    if any(type(item) is not int for item in (count, sides, modifier)):
        raise _error_type("damage integers must be exact")
    return count, sides, modifier, match.group("damage_type")


def _parse_consumer_source(
    selection: VerifiedSourceSelection,
    spec: _ConsumerSpec,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _array_type: type[RawSourceArray] = RawSourceArray,
    _unique_member_impl: Any = _unique_member,
    _raw_member_impl: Any = _raw_member,
    _description_re: re.Pattern[str] = _DESCRIPTION_RE,
    _athletics_re: re.Pattern[str] = _ATHLETICS_RE,
    _parse_damage_impl: Any = _parse_damage,
    _maximum_components: int = MAX_DAMAGE_COMPONENTS,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> tuple[tuple[tuple[object, ...], ...], int, int]:
    creature = selection.carrier.raw_block
    name = _unique_member_impl(creature, "Name").value
    ac = _unique_member_impl(creature, "AC").value
    skills = _unique_member_impl(creature, "Skills").value
    ability_member = _raw_member_impl(
        creature,
        spec.ability_ordinal,
        "!.Swallow Whole",
    )
    ability = ability_member.value
    if (
        type(name) is not str
        or name != spec.creature_name
        or type(ac) is not str
        or ac != str(spec.armor_class)
        or type(ability) is not _object_type
        or selection.raw_value != ability
        or selection.selected_value != ability
    ):
        raise _error_type(
            "Swallow Whole creature carrier differs from review"
        )
    expected_keys = (
        ("Action", "Traits", "Description")
        if spec.trait_source == "local"
        else ("Action", "Description")
    )
    if tuple(member.key for member in ability.members) != expected_keys:
        raise _error_type(
            "Swallow Whole local ability shape differs from review"
        )
    if _raw_member_impl(ability, 0, "Action").value != "single":
        raise _error_type(
            "Swallow Whole action cost differs from review"
        )
    description_ordinal = 2 if spec.trait_source == "local" else 1
    if spec.trait_source == "local":
        traits = _raw_member_impl(ability, 1, "Traits").value
        if (
            type(traits) is not _array_type
            or type(traits.items) is not tuple
            or traits.items != ("attack",)
        ):
            raise _error_type(
                "Swallow Whole local traits differ from review"
            )
    description = _raw_member_impl(
        ability, description_ordinal, "Description"
    ).value
    if type(description) is not str:
        raise _error_type(
            "Swallow Whole description must be exact text"
        )
    match = _description_re.fullmatch(description)
    if match is None:
        raise _error_type(
            "Swallow Whole description is not canonical"
        )
    damage_texts = tuple(match.group("damage").split(" plus "))
    if (
        match.group("size") != spec.maximum_size
        or damage_texts != spec.damage_source_texts
        or int(match.group("rupture")) != spec.rupture
        or not 1 <= len(damage_texts) <= _maximum_components
    ):
        raise _error_type(
            "Swallow Whole values differ from reviewed source"
        )
    parsed_damage = tuple(
        (source_text, *_parse_damage_impl(source_text))
        for source_text in damage_texts
    )
    skill_items: tuple[object, ...]
    if type(skills) is _array_type:
        skill_items = skills.items
    elif type(skills) is str:
        skill_items = (skills,)
    else:
        raise _error_type("creature Skills shape is invalid")
    athletics = tuple(
        item
        for item in skill_items
        if type(item) is str and item.startswith("Athletics ")
    )
    if athletics != (spec.athletics_source_text,):
        raise _error_type(
            "creature Athletics evidence differs from review"
        )
    athletics_match = _athletics_re.match(athletics[0])
    if (
        athletics_match is None
        or int(athletics_match.group("modifier"))
        != spec.athletics_modifier
    ):
        raise _error_type(
            "creature Athletics modifier differs from review"
        )
    return parsed_damage, spec.armor_class, spec.athletics_modifier


def _validate_feeder_source(
    selection: VerifiedSourceSelection,
    spec: _FeederSpec,
    _unique_member_impl: Any = _unique_member,
    _raw_member_impl: Any = _raw_member,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> None:
    strike = selection.carrier.raw_block
    name = _unique_member_impl(strike, "Name").value
    attack = _unique_member_impl(strike, "Attack").value
    damage = _raw_member_impl(
        strike, spec.damage_ordinal, "Damage"
    ).value
    if (
        type(name) is not str
        or name != spec.strike_name
        or type(attack) is not str
        or attack != spec.attack_source_text
        or type(damage) is not str
        or damage != spec.damage_source_text
        or selection.raw_value != damage
        or selection.selected_value != damage
        or (
            spec.grab_kind == "improved-grab"
            and "Improved Grab (page 359)" not in damage
        )
        or (
            spec.grab_kind == "grab"
            and "Grab (page 359)" not in damage
        )
    ):
        raise _error_type(
            "local Swallow Whole feeder differs from review"
        )


def _resolve_rule(
    authority: SourceAuthorityAdapter,
    requirement: RuleRequirement,
    _rule_type: type[VerifiedRuleReceipt] = VerifiedRuleReceipt,
    _same_requirement_impl: Any = _same_requirement,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> VerifiedRuleReceipt:
    rule = authority.validate_rule(authority.resolve_rule(requirement))
    authority.validate_selection(rule.selection)
    if (
        type(rule) is not _rule_type
        or rule.rule_id != requirement.rule_id
        or not _same_requirement_impl(rule.requirement, requirement)
    ):
        raise _error_type(
            f"verified rule differs from review: {requirement.rule_id}"
        )
    return rule


def _validate_exact_type_slots(
    value: object,
    exact_type: type,
    label: str,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> None:
    if type(value) is not exact_type:
        raise TypeError(f"{label} must use its exact contract type")
    try:
        for slot in exact_type.__slots__:
            if slot != "__weakref__":
                object.__getattribute__(value, slot)
    except (AttributeError, RecursionError) as failure:
        raise _error_type(
            f"{label} is incomplete or cyclic"
        ) from failure


def _damage_payload(
    value: SwallowWholeDamage,
    _damage_type: type[SwallowWholeDamage] = SwallowWholeDamage,
    _validate_slots_impl: Any = _validate_exact_type_slots,
    _parse_damage_impl: Any = _parse_damage,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> dict[str, Any]:
    _validate_slots_impl(value, _damage_type, "damage")
    if (
        type(value.source_text) is not str
        or type(value.dice_count) is not int
        or type(value.die_sides) is not int
        or type(value.modifier) is not int
        or type(value.damage_type) is not str
        or (
            value.dice_count,
            value.die_sides,
            value.modifier,
            value.damage_type,
        )
        != _parse_damage_impl(value.source_text)
    ):
        raise _error_type("compiled damage is invalid")
    return {
        "sourceText": value.source_text,
        "dice": {
            "count": value.dice_count,
            "sides": value.die_sides,
            "modifier": value.modifier,
        },
        "type": value.damage_type,
    }


def _candidate_payload(
    value: SwallowWholeFeederCandidate,
    _candidate_type: type[SwallowWholeFeederCandidate] = (
        SwallowWholeFeederCandidate
    ),
    _validate_slots_impl: Any = _validate_exact_type_slots,
    _attack_re: re.Pattern[str] = _ATTACK_RE,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> dict[str, Any]:
    _validate_slots_impl(
        value, _candidate_type, "feeder candidate"
    )
    if (
        type(value.rule_id) is not str
        or type(value.strike_name) is not str
        or type(value.attack_modifier) is not int
        or type(value.attack_source_text) is not str
        or type(value.damage_source_text) is not str
        or type(value.grab_kind) is not str
        or value.grab_kind not in ("grab", "improved-grab")
        or type(value.anatomy_eligible) is not bool
        or type(value.status) is not str
        or value.status != "candidate"
    ):
        raise _error_type("feeder candidate is invalid")
    attack_match = _attack_re.fullmatch(value.attack_source_text)
    if (
        attack_match is None
        or int(attack_match.group("modifier")) != value.attack_modifier
    ):
        raise _error_type(
            "feeder candidate attack modifier is invalid"
        )
    return {
        "ruleId": value.rule_id,
        "strikeName": value.strike_name,
        "attackModifier": value.attack_modifier,
        "attackSourceText": value.attack_source_text,
        "damageSourceText": value.damage_source_text,
        "grabKind": value.grab_kind,
        "anatomyEligible": value.anatomy_eligible,
        "status": value.status,
    }


def _deferral_payload(
    value: SwallowWholeDeferral,
    _deferral_type: type[SwallowWholeDeferral] = SwallowWholeDeferral,
    _validate_slots_impl: Any = _validate_exact_type_slots,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> dict[str, Any]:
    _validate_slots_impl(value, _deferral_type, "deferral")
    if (
        type(value.mechanic_id) is not str
        or type(value.phase) is not str
        or value.phase not in ("source-link", "runtime")
        or type(value.provider_rule_ids) is not tuple
        or any(type(item) is not str for item in value.provider_rule_ids)
        or type(value.blocking_reason) is not str
        or type(value.status) is not str
        or value.status != "deferred"
    ):
        raise _error_type("Swallow Whole deferral is invalid")
    return {
        "mechanicId": value.mechanic_id,
        "phase": value.phase,
        "providerRuleIds": list(value.provider_rule_ids),
        "blockingReason": value.blocking_reason,
        "status": "deferred",
        "blocks": "registry-activation",
    }


def _dependency_payload(
    value: SwallowWholeProviderDependency,
    _dependency_type: type[SwallowWholeProviderDependency] = (
        SwallowWholeProviderDependency
    ),
    _validate_slots_impl: Any = _validate_exact_type_slots,
    _error_type: type[SwallowWholeCompileError] = SwallowWholeCompileError,
) -> dict[str, Any]:
    _validate_slots_impl(
        value, _dependency_type, "provider dependency"
    )
    if (
        type(value.rule_id) is not str
        or type(value.source_id) is not str
        or type(value.locator) is not str
        or type(value.phase) is not str
        or value.phase not in (
            "compile-classification",
            "compile-link",
            "compile-semantics",
            "runtime-context",
        )
        or type(value.purpose) is not str
    ):
        raise _error_type(
            "Swallow Whole provider dependency is invalid"
        )
    return {
        "ruleId": value.rule_id,
        "sourceId": value.source_id,
        "locator": value.locator,
        "phase": value.phase,
        "purpose": value.purpose,
    }


def _new_damage(
    source_text: str,
    _parse_damage_impl: Any = _parse_damage,
    _new_value_impl: Any = _new_value,
    _damage_type: type[SwallowWholeDamage] = SwallowWholeDamage,
) -> SwallowWholeDamage:
    count, sides, modifier, damage_type = _parse_damage_impl(source_text)
    return _new_value_impl(
        _damage_type,
        (source_text, count, sides, modifier, damage_type),
    )


def _new_candidate(
    spec: _FeederSpec,
    _attack_re: re.Pattern[str] = _ATTACK_RE,
    _new_value_impl: Any = _new_value,
    _candidate_type: type[SwallowWholeFeederCandidate] = (
        SwallowWholeFeederCandidate
    ),
) -> SwallowWholeFeederCandidate:
    attack_match = _attack_re.fullmatch(spec.attack_source_text)
    if attack_match is None:
        raise AssertionError("reviewed feeder attack is invalid")
    return _new_value_impl(
        _candidate_type,
        (
            spec.rule_id,
            spec.strike_name,
            int(attack_match.group("modifier")),
            spec.attack_source_text,
            spec.damage_source_text,
            spec.grab_kind,
            spec.anatomy_eligible,
            "candidate",
        ),
    )


def _new_deferrals(
    specs: tuple[tuple[str, str, tuple[str, ...], str], ...],
    _new_value_impl: Any = _new_value,
    _deferral_type: type[SwallowWholeDeferral] = SwallowWholeDeferral,
) -> tuple[SwallowWholeDeferral, ...]:
    return tuple(
        _new_value_impl(
            _deferral_type,
            (mechanic_id, phase, providers, reason, "deferred"),
        )
        for mechanic_id, phase, providers, reason in specs
    )


def _new_dependency(
    spec: _ProviderSpec,
    _new_value_impl: Any = _new_value,
    _dependency_type: type[SwallowWholeProviderDependency] = (
        SwallowWholeProviderDependency
    ),
) -> SwallowWholeProviderDependency:
    return _new_value_impl(
        _dependency_type,
        (
            spec.rule_id,
            spec.source_id,
            spec.locator,
            spec.phase,
            spec.purpose,
        ),
    )


def _compiled_payload(
    value: CompiledSwallowWhole,
    provider_specs: tuple[_ProviderSpec, ...],
    _family_id: str = FAMILY_ID,
    _compiler_id: str = COMPILER_ID,
    _damage_payload_impl: Any = _damage_payload,
    _candidate_payload_impl: Any = _candidate_payload,
    _deferral_payload_impl: Any = _deferral_payload,
    _new_dependency_impl: Any = _new_dependency,
    _dependency_payload_impl: Any = _dependency_payload,
    _serialize_rule: Any = VerifiedRuleReceipt.as_serialized,
) -> dict[str, Any]:
    return {
        "familyId": _family_id,
        "compilerId": _compiler_id,
        "supportState": "compile-only",
        "runtimeReady": False,
        "source": {
            "sourceId": value.source_id,
            "locator": value.locator,
            "creatureName": value.creature_name,
        },
        "ability": {
            "actionCost": value.action_cost,
            "traits": list(value.traits),
            "traitSource": value.trait_source,
            "maximumTargetSize": {
                "name": value.maximum_target_size,
                "rank": value.maximum_target_size_rank,
            },
            "internalDamage": [
                _damage_payload_impl(item) for item in value.internal_damage
            ],
            "rupture": {
                "threshold": value.rupture_threshold,
                "eligibleDamageTypes": list(value.rupture_damage_types),
                "aggregation": "one-attack-or-spell-after-defenses",
            },
            "armorClassAgainstInternalAttacks": value.armor_class,
            "athleticsModifier": value.athletics_modifier,
            "escapeDc": value.escape_dc,
        },
        "feederLink": {
            "status": "deferred",
            "candidates": [
                _candidate_payload_impl(item)
                for item in value.feeder_candidates
            ],
            "rules": [
                _serialize_rule(item)
                for item in value.feeder_rules
            ],
        },
        "consumer": _serialize_rule(
            value.consumer_rule
        ),
        "relatedAbilities": [
            _serialize_rule(item)
            for item in value.related_rules
        ],
        "providers": [
            {
                **_dependency_payload_impl(_new_dependency_impl(spec)),
                "receipt": _serialize_rule(rule),
            }
            for spec, rule in zip(provider_specs, value.provider_rules)
        ],
        "deferredMechanics": [
            _deferral_payload_impl(item) for item in value.deferrals
        ],
    }


def _linked_payload(
    value: LinkedSwallowWhole,
    provider_specs: tuple[_ProviderSpec, ...],
    _family_id: str = FAMILY_ID,
    _compiler_id: str = COMPILER_ID,
    _compiled_payload_impl: Any = _compiled_payload,
    _candidate_payload_impl: Any = _candidate_payload,
    _deferral_payload_impl: Any = _deferral_payload,
    _serialize_rule: Any = VerifiedRuleReceipt.as_serialized,
) -> dict[str, Any]:
    return {
        "familyId": _family_id,
        "compilerId": _compiler_id,
        "supportState": "linked-non-executable",
        "runtimeReady": False,
        "compiled": _compiled_payload_impl(value.compiled, provider_specs),
        "feederLink": {
            "status": "linked",
            "selected": _candidate_payload_impl(value.selected_feeder),
            "selectedRule": _serialize_rule(
                value.selected_feeder_rule
            ),
            "rejectedCandidates": [
                _candidate_payload_impl(item)
                for item in value.rejected_feeders
            ],
        },
        "deferredMechanics": [
            _deferral_payload_impl(item) for item in value.deferrals
        ],
    }


def _bind_reviewed_api(
    consumer_specs: tuple[_ConsumerSpec, ...],
    feeder_specs: tuple[_FeederSpec, ...],
    related_specs: tuple[_RelatedSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    deferral_specs: tuple[tuple[str, str, tuple[str, ...], str], ...],
) -> tuple[Any, ...]:
    consumer_type = _ConsumerSpec
    feeder_type = _FeederSpec
    related_type = _RelatedSpec
    provider_type = _ProviderSpec
    reviewed_consumers = tuple(
        consumer_type(
            *(object.__getattribute__(item, slot)
              for slot in consumer_type.__slots__)
        )
        for item in consumer_specs
    )
    reviewed_feeders = tuple(
        feeder_type(
            *(object.__getattribute__(item, slot)
              for slot in feeder_type.__slots__)
        )
        for item in feeder_specs
    )
    reviewed_related = tuple(
        related_type(
            *(object.__getattribute__(item, slot)
              for slot in related_type.__slots__)
        )
        for item in related_specs
    )
    reviewed_providers = tuple(
        provider_type(
            *(object.__getattribute__(item, slot)
              for slot in provider_type.__slots__)
        )
        for item in provider_specs
    )
    reviewed_deferrals = tuple(
        (item[0], item[1], tuple(item[2]), item[3])
        for item in deferral_specs
    )
    authority_type = SourceAuthorityAdapter
    receipt_type = SourceReceipt
    compiled_type = CompiledSwallowWhole
    linked_type = LinkedSwallowWhole
    consumer_requirement_impl = _consumer_requirement
    feeder_requirement_impl = _feeder_requirement
    related_requirement_impl = _related_requirement
    provider_requirement_impl = _provider_requirement
    resolve_rule_impl = _resolve_rule
    same_requirement_impl = _same_requirement
    same_receipt_impl = _same_receipt
    parse_consumer_impl = _parse_consumer_source
    validate_feeder_impl = _validate_feeder_source
    new_value_impl = _new_value
    new_damage_impl = _new_damage
    new_candidate_impl = _new_candidate
    new_deferrals_impl = _new_deferrals
    new_dependency_impl = _new_dependency
    dependency_payload_impl = _dependency_payload
    damage_payload_impl = _damage_payload
    candidate_payload_impl = _candidate_payload
    deferral_payload_impl = _deferral_payload
    compiled_payload_impl = _compiled_payload
    linked_payload_impl = _linked_payload
    validate_slots_impl = _validate_exact_type_slots
    canonical_bytes = canonical_json_bytes
    error_type = SwallowWholeCompileError
    rule_receipt_type = VerifiedRuleReceipt
    size_ranks = dict(_SIZE_RANKS)
    consumer_count = CONSUMER_REQUIREMENT_COUNT

    if (
        len(reviewed_consumers) != CONSUMER_REQUIREMENT_COUNT
        or len(reviewed_feeders) != FEEDER_REQUIREMENT_COUNT
        or len(reviewed_related) != RELATED_REQUIREMENT_COUNT
        or len(reviewed_providers) != PROVIDER_REQUIREMENT_COUNT
        or len(reviewed_deferrals) != 12
        or len({item.rule_id for item in reviewed_consumers})
        != len(reviewed_consumers)
        or len({item.rule_id for item in reviewed_feeders})
        != len(reviewed_feeders)
        or len({item.rule_id for item in reviewed_related})
        != len(reviewed_related)
        or len({item.rule_id for item in reviewed_providers})
        != len(reviewed_providers)
    ):
        raise AssertionError("reviewed Swallow Whole dossier is incomplete")

    consumers_by_rule = {
        item.rule_id: item for item in reviewed_consumers
    }
    consumers_by_locator = {
        item.locator: item for item in reviewed_consumers
    }
    feeders_by_creature = {
        consumer.creature_name: tuple(
            item for item in reviewed_feeders
            if item.creature_name == consumer.creature_name
        )
        for consumer in reviewed_consumers
    }
    related_by_creature = {
        consumer.creature_name: tuple(
            item for item in reviewed_related
            if item.kind == "variant"
            and item.creature_name == consumer.creature_name
        )
        for consumer in reviewed_consumers
    }
    provider_by_rule = {
        item.rule_id: item for item in reviewed_providers
    }

    if (
        len(consumers_by_locator) != len(reviewed_consumers)
        or any(not feeders_by_creature[item.creature_name]
               for item in reviewed_consumers)
        or sum(len(items) for items in feeders_by_creature.values())
        != len(reviewed_feeders)
        or sum(len(items) for items in related_by_creature.values())
        != 13
    ):
        raise AssertionError("reviewed Swallow Whole relations are invalid")

    def swallow_whole_consumer_requirements(
    ) -> tuple[RuleRequirement, ...]:
        return tuple(
            consumer_requirement_impl(item)
            for item in reviewed_consumers
        )

    def swallow_whole_feeder_requirements(
    ) -> tuple[RuleRequirement, ...]:
        result = []
        for feeder in reviewed_feeders:
            consumer = next(
                item for item in reviewed_consumers
                if item.creature_name == feeder.creature_name
            )
            result.append(feeder_requirement_impl(consumer, feeder))
        return tuple(result)

    def swallow_whole_related_requirements(
    ) -> tuple[RuleRequirement, ...]:
        return tuple(
            related_requirement_impl(item) for item in reviewed_related
        )

    def swallow_whole_provider_requirements(
    ) -> tuple[RuleRequirement, ...]:
        return tuple(
            provider_requirement_impl(item)
            for item in reviewed_providers
        )

    def swallow_whole_provider_ledger(
    ) -> tuple[SwallowWholeProviderDependency, ...]:
        return tuple(
            new_dependency_impl(item) for item in reviewed_providers
        )

    def validate_rule_exact(
        authority: SourceAuthorityAdapter,
        rule: object,
        requirement: RuleRequirement,
    ) -> VerifiedRuleReceipt:
        verified = authority.validate_rule(rule)
        authority.validate_selection(verified.selection)
        if (
            type(verified) is not rule_receipt_type
            or verified.rule_id != requirement.rule_id
            or not same_requirement_impl(
                verified.requirement, requirement
            )
        ):
            raise error_type(
                f"retained rule differs from review: {requirement.rule_id}"
            )
        return verified

    def validate_compiled_swallow_whole(
        authority: SourceAuthorityAdapter,
        value: object,
        /,
    ) -> CompiledSwallowWhole:
        if type(authority) is not authority_type:
            raise TypeError(
                "Swallow Whole validation requires SourceAuthorityAdapter"
            )
        validate_slots_impl(value, compiled_type, "compiled Swallow Whole")
        assert type(value) is compiled_type
        if value._authority is not authority:
            raise error_type(
                "compiled Swallow Whole belongs to another authority"
            )
        consumer_rule = authority.validate_rule(value.consumer_rule)
        spec = consumers_by_rule.get(consumer_rule.rule_id)
        if spec is None:
            raise error_type(
                "compiled consumer is outside the reviewed corpus"
            )
        consumer_rule = validate_rule_exact(
            authority,
            consumer_rule,
            consumer_requirement_impl(spec),
        )
        consumer_selection = authority.validate_selection(
            consumer_rule.selection
        )
        parsed_damage, armor_class, athletics = parse_consumer_impl(
            consumer_selection, spec
        )
        if (
            type(value.source_id) is not str
            or value.source_id != "core-mc1"
            or type(value.locator) is not str
            or value.locator != spec.locator
            or type(value.creature_name) is not str
            or value.creature_name != spec.creature_name
            or type(value.action_cost) is not int
            or value.action_cost != 1
            or type(value.traits) is not tuple
            or value.traits != ("attack",)
            or type(value.trait_source) is not str
            or value.trait_source != spec.trait_source
            or type(value.maximum_target_size) is not str
            or value.maximum_target_size != spec.maximum_size
            or type(value.maximum_target_size_rank) is not int
            or value.maximum_target_size_rank
            != size_ranks[spec.maximum_size]
            or type(value.rupture_threshold) is not int
            or value.rupture_threshold != spec.rupture
            or type(value.rupture_damage_types) is not tuple
            or value.rupture_damage_types != ("piercing", "slashing")
            or type(value.armor_class) is not int
            or value.armor_class != armor_class
            or type(value.athletics_modifier) is not int
            or value.athletics_modifier != athletics
            or type(value.escape_dc) is not int
            or value.escape_dc != athletics + 10
            or value.runtime_ready is not False
        ):
            raise error_type(
                "compiled Swallow Whole scalar fields are noncanonical"
            )
        if (
            type(value.internal_damage) is not tuple
            or len(value.internal_damage) != len(parsed_damage)
        ):
            raise error_type(
                "compiled Swallow Whole damage census is invalid"
            )
        for damage, parsed in zip(value.internal_damage, parsed_damage):
            if (
                canonical_bytes(damage_payload_impl(damage))
                != canonical_bytes(
                    damage_payload_impl(new_damage_impl(parsed[0]))
                )
            ):
                raise error_type(
                    "compiled Swallow Whole damage differs from source"
                )

        expected_feeders = feeders_by_creature[spec.creature_name]
        if (
            type(value.feeder_candidates) is not tuple
            or type(value.feeder_rules) is not tuple
            or len(value.feeder_candidates) != len(expected_feeders)
            or len(value.feeder_rules) != len(expected_feeders)
        ):
            raise error_type(
                "compiled feeder evidence census is invalid"
            )
        verified_feeders = []
        for candidate, rule, feeder_spec in zip(
            value.feeder_candidates,
            value.feeder_rules,
            expected_feeders,
        ):
            if canonical_bytes(candidate_payload_impl(candidate)) != (
                canonical_bytes(
                    candidate_payload_impl(new_candidate_impl(feeder_spec))
                )
            ):
                raise error_type(
                    "compiled feeder candidate differs from review"
                )
            feeder_rule = validate_rule_exact(
                authority,
                rule,
                feeder_requirement_impl(spec, feeder_spec),
            )
            validate_feeder_impl(
                authority.validate_selection(feeder_rule.selection),
                feeder_spec,
            )
            verified_feeders.append(feeder_rule)

        expected_related = related_by_creature[spec.creature_name]
        if (
            type(value.related_rules) is not tuple
            or len(value.related_rules) != len(expected_related)
        ):
            raise error_type(
                "compiled related ability census is invalid"
            )
        verified_related = tuple(
            validate_rule_exact(
                authority,
                rule,
                related_requirement_impl(related_spec),
            )
            for rule, related_spec in zip(
                value.related_rules, expected_related
            )
        )

        if (
            type(value.provider_rules) is not tuple
            or tuple(item.rule_id for item in value.provider_rules)
            != tuple(item.rule_id for item in reviewed_providers)
        ):
            raise error_type(
                "compiled provider order or membership is invalid"
            )
        verified_providers = tuple(
            validate_rule_exact(
                authority,
                rule,
                provider_requirement_impl(
                    provider_by_rule[rule.rule_id]
                ),
            )
            for rule in value.provider_rules
        )
        if (
            type(value.deferrals) is not tuple
            or len(value.deferrals) != len(reviewed_deferrals)
        ):
            raise error_type(
                "compiled deferral census is invalid"
            )
        canonical_deferrals = new_deferrals_impl(reviewed_deferrals)
        for supplied, expected in zip(
            value.deferrals, canonical_deferrals
        ):
            if canonical_bytes(deferral_payload_impl(supplied)) != (
                canonical_bytes(deferral_payload_impl(expected))
            ):
                raise error_type(
                    "compiled deferral differs from review"
                )
        authority.require_shared_authority(
            consumer_selection,
            (
                consumer_rule,
                *tuple(verified_feeders),
                *verified_related,
                *verified_providers,
            ),
        )
        payload = compiled_payload_impl(value, reviewed_providers)
        canonical_bytes(payload)
        return value

    def compile_swallow_whole(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
        /,
    ) -> CompiledSwallowWhole:
        if type(authority) is not authority_type:
            raise TypeError(
                "Swallow Whole compilation requires SourceAuthorityAdapter"
            )
        if type(receipt) is not receipt_type:
            raise TypeError(
                "Swallow Whole compilation requires an exact SourceReceipt"
            )
        selection = authority.validate_selection(authority.reload(receipt))
        if selection.address.source_id != "core-mc1":
            raise error_type(
                "Swallow Whole consumer must come from Core MC1"
            )
        spec = consumers_by_locator.get(selection.address.locator)
        if spec is None:
            raise error_type(
                "consumer is outside the reviewed Swallow Whole corpus"
            )
        consumer_rule = resolve_rule_impl(
            authority, consumer_requirement_impl(spec)
        )
        if not same_receipt_impl(receipt, consumer_rule.receipt):
            raise error_type(
                "consumer is not the exact reviewed Swallow Whole ability"
            )
        parsed_damage, armor_class, athletics = parse_consumer_impl(
            selection, spec
        )
        local_feeders = feeders_by_creature[spec.creature_name]
        feeder_rules = tuple(
            resolve_rule_impl(
                authority, feeder_requirement_impl(spec, item)
            )
            for item in local_feeders
        )
        for rule, feeder_spec in zip(feeder_rules, local_feeders):
            validate_feeder_impl(
                authority.validate_selection(rule.selection),
                feeder_spec,
            )
        local_related = related_by_creature[spec.creature_name]
        related_rules = tuple(
            resolve_rule_impl(
                authority, related_requirement_impl(item)
            )
            for item in local_related
        )
        provider_rules = tuple(
            resolve_rule_impl(
                authority, provider_requirement_impl(item)
            )
            for item in reviewed_providers
        )
        result = new_value_impl(
            compiled_type,
            (
                "core-mc1",
                spec.locator,
                spec.creature_name,
                1,
                ("attack",),
                spec.trait_source,
                spec.maximum_size,
                size_ranks[spec.maximum_size],
                tuple(new_damage_impl(item[0]) for item in parsed_damage),
                spec.rupture,
                ("piercing", "slashing"),
                armor_class,
                athletics,
                athletics + 10,
                tuple(new_candidate_impl(item) for item in local_feeders),
                consumer_rule,
                feeder_rules,
                related_rules,
                provider_rules,
                new_deferrals_impl(reviewed_deferrals),
                False,
                authority,
            ),
        )
        return validate_compiled_swallow_whole(authority, result)

    def compile_swallow_whole_census(
        authority: SourceAuthorityAdapter,
        /,
    ) -> tuple[CompiledSwallowWhole, ...]:
        if type(authority) is not authority_type:
            raise TypeError(
                "Swallow Whole census requires SourceAuthorityAdapter"
            )
        result = tuple(
            compile_swallow_whole(
                authority,
                resolve_rule_impl(
                    authority, consumer_requirement_impl(spec)
                ).receipt,
            )
            for spec in reviewed_consumers
        )
        if len(result) != consumer_count:
            raise AssertionError("Swallow Whole census is incomplete")
        return result

    def validate_linked_swallow_whole(
        authority: SourceAuthorityAdapter,
        value: object,
        /,
    ) -> LinkedSwallowWhole:
        if type(authority) is not authority_type:
            raise TypeError(
                "linked Swallow Whole validation requires "
                "SourceAuthorityAdapter"
            )
        validate_slots_impl(value, linked_type, "linked Swallow Whole")
        assert type(value) is linked_type
        if value._authority is not authority:
            raise error_type(
                "linked Swallow Whole belongs to another authority"
            )
        compiled = validate_compiled_swallow_whole(
            authority, value.compiled
        )
        spec = consumers_by_rule[compiled.consumer_rule.rule_id]
        local_specs = feeders_by_creature[spec.creature_name]
        eligible = tuple(item for item in local_specs if item.anatomy_eligible)
        rejected = tuple(
            item for item in local_specs if not item.anatomy_eligible
        )
        if len(eligible) != 1:
            raise error_type(
                "reviewed feeder selection is not unique"
            )
        expected_candidate = new_candidate_impl(eligible[0])
        if (
            canonical_bytes(
                candidate_payload_impl(value.selected_feeder)
            )
            != canonical_bytes(
                candidate_payload_impl(expected_candidate)
            )
        ):
            raise error_type(
                "linked feeder selection differs from review"
            )
        selected_rule = validate_rule_exact(
            authority,
            value.selected_feeder_rule,
            feeder_requirement_impl(spec, eligible[0]),
        )
        validate_feeder_impl(
            authority.validate_selection(selected_rule.selection),
            eligible[0],
        )
        if (
            type(value.rejected_feeders) is not tuple
            or len(value.rejected_feeders) != len(rejected)
        ):
            raise error_type(
                "linked rejected-feeder census is invalid"
            )
        for supplied, rejected_spec in zip(
            value.rejected_feeders, rejected
        ):
            if canonical_bytes(candidate_payload_impl(supplied)) != (
                canonical_bytes(
                    candidate_payload_impl(
                        new_candidate_impl(rejected_spec)
                    )
                )
            ):
                raise error_type(
                    "linked rejected feeder differs from review"
                )
        expected_deferrals = tuple(
            item for item in reviewed_deferrals
            if item[0] != "feeder-strike-link"
        )
        if (
            type(value.deferrals) is not tuple
            or len(value.deferrals) != len(expected_deferrals)
            or value.runtime_ready is not False
        ):
            raise error_type(
                "linked runtime boundary is invalid"
            )
        for supplied, expected in zip(
            value.deferrals,
            new_deferrals_impl(expected_deferrals),
        ):
            if canonical_bytes(deferral_payload_impl(supplied)) != (
                canonical_bytes(deferral_payload_impl(expected))
            ):
                raise error_type(
                    "linked deferral differs from review"
                )
        authority.require_shared_authority(
            selected_rule.selection, (selected_rule,)
        )
        canonical_bytes(linked_payload_impl(value, reviewed_providers))
        return value

    def link_swallow_whole(
        authority: SourceAuthorityAdapter,
        compiled: CompiledSwallowWhole,
        /,
    ) -> LinkedSwallowWhole:
        compiled = validate_compiled_swallow_whole(authority, compiled)
        spec = consumers_by_rule[compiled.consumer_rule.rule_id]
        local_specs = feeders_by_creature[spec.creature_name]
        eligible_indexes = tuple(
            index for index, item in enumerate(local_specs)
            if item.anatomy_eligible
        )
        if len(eligible_indexes) != 1:
            raise error_type(
                "Swallow Whole feeder link is ambiguous"
            )
        selected_index = eligible_indexes[0]
        result = new_value_impl(
            linked_type,
            (
                compiled,
                compiled.feeder_candidates[selected_index],
                compiled.feeder_rules[selected_index],
                tuple(
                    candidate
                    for index, candidate
                    in enumerate(compiled.feeder_candidates)
                    if index != selected_index
                    and not local_specs[index].anatomy_eligible
                ),
                new_deferrals_impl(
                    tuple(
                        item for item in reviewed_deferrals
                        if item[0] != "feeder-strike-link"
                    )
                ),
                False,
                authority,
            ),
        )
        return validate_linked_swallow_whole(authority, result)

    def compiled_as_serialized(
        value: CompiledSwallowWhole,
        authority: SourceAuthorityAdapter,
        /,
    ) -> dict[str, Any]:
        validate_compiled_swallow_whole(authority, value)
        payload = compiled_payload_impl(value, reviewed_providers)
        canonical_bytes(payload)
        return payload

    def linked_as_serialized(
        value: LinkedSwallowWhole,
        authority: SourceAuthorityAdapter,
        /,
    ) -> dict[str, Any]:
        validate_linked_swallow_whole(authority, value)
        payload = linked_payload_impl(value, reviewed_providers)
        canonical_bytes(payload)
        return payload

    return (
        swallow_whole_consumer_requirements,
        swallow_whole_feeder_requirements,
        swallow_whole_related_requirements,
        swallow_whole_provider_requirements,
        swallow_whole_provider_ledger,
        compile_swallow_whole,
        compile_swallow_whole_census,
        validate_compiled_swallow_whole,
        link_swallow_whole,
        validate_linked_swallow_whole,
        compiled_as_serialized,
        linked_as_serialized,
    )


(
    swallow_whole_consumer_requirements,
    swallow_whole_feeder_requirements,
    swallow_whole_related_requirements,
    swallow_whole_provider_requirements,
    swallow_whole_provider_ledger,
    compile_swallow_whole,
    compile_swallow_whole_census,
    validate_compiled_swallow_whole,
    link_swallow_whole,
    validate_linked_swallow_whole,
    _compiled_as_serialized,
    _linked_as_serialized,
) = _bind_reviewed_api(
    _CONSUMER_SPECS,
    _FEEDER_SPECS,
    _RELATED_SPECS,
    _PROVIDER_SPECS,
    _DEFERRAL_SPECS,
)
CompiledSwallowWhole.as_serialized = _compiled_as_serialized
LinkedSwallowWhole.as_serialized = _linked_as_serialized


__all__ = [
    "COMPILER_ID",
    "CONSUMER_REQUIREMENT_COUNT",
    "CompiledSwallowWhole",
    "FAMILY_ID",
    "FEEDER_REQUIREMENT_COUNT",
    "LinkedSwallowWhole",
    "MAX_DAMAGE_COMPONENTS",
    "MECHANIC_TYPE",
    "PROVIDER_REQUIREMENT_COUNT",
    "RELATED_REQUIREMENT_COUNT",
    "SwallowWholeCompileError",
    "SwallowWholeDamage",
    "SwallowWholeDeferral",
    "SwallowWholeFeederCandidate",
    "SwallowWholeProviderDependency",
    "compile_swallow_whole",
    "compile_swallow_whole_census",
    "link_swallow_whole",
    "swallow_whole_consumer_requirements",
    "swallow_whole_feeder_requirements",
    "swallow_whole_provider_ledger",
    "swallow_whole_provider_requirements",
    "swallow_whole_related_requirements",
    "validate_compiled_swallow_whole",
    "validate_linked_swallow_whole",
]

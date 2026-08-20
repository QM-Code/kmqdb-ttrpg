"""Compile Monster Core Size, footprint, and reach into typed link facts.

This family is deliberately compile/link-only and unregistered.  It does not
change ``source.py``, construct participants, place footprints, or resolve
movement.  Its output preserves the exact duplicate-aware source selector and
keeps every unresolved whole-creature profile explicit.

The source contract has three authority layers:

* exact, lossless ``Size`` and ``Speed`` members in one authenticated creature
  block;
* the canonical Size/Space/Reach table;
* a server-owned reviewed tall/long catalog bound to the ordered statistical
  block projection (article-owned Icon, Image, and Description fields do not
  alter that review identity), with optional equally exact explicit review
  bindings.

Strike-local ``reach N feet`` never determines whole-creature shape.  A bare
``reach`` trait is retained as the canonical weapon operation "natural reach
+ 5 feet" and remains deferred until equipment linking.  Gargantuan space is
always represented as a 20-foot minimum, never an exact 20-foot claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any

from .contracts import (
    RawSourceArray,
    RawSourceMember,
    RawSourceObject,
    RawSourceValue,
    RuleReference,
    SerializedObject,
)
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)


FAMILY_ID = "size-space-reach"
COMPILER_ID = "size-space-reach"
MONSTER_CORE_SOURCE_ID = "core-mc1"

PROFILE_REVIEW_SCHEMA = 2
PROFILE_REVIEWER_ID = "kmqdb:core-mc1-first-gate-geometry"
PROFILE_REVIEW_MANIFEST_SHA256 = (
    "c17bcaeae11f702f34785e17607507af764302e8d30fd9f0bdd06d6ffd1b1c02"
)
PROFILE_REVIEW_RECORD_COUNT = 155

MAX_BLOCK_SOURCE_BYTES = 262_144
MAX_BLOCK_NODES = 8_192
MAX_BLOCK_DEPTH = 16
MAX_OBJECT_MEMBERS = 1_024
MAX_SOURCE_KEY_BYTES = 256
MAX_SOURCE_STRING_BYTES = 65_536
MAX_CONTENT_PATH_STEPS = 32
MAX_STRIKES_PER_FIELD = 128
MAX_TRAITS_PER_STRIKE = 64
MAX_TRAIT_SOURCE_BYTES = 256
MAX_IDENTIFIER_BYTES = 4_096
MAX_PROFILE_BINDINGS = 1_024
MAX_SPEED_SOURCE_BYTES = 512
MAX_STRIKE_NAME_BYTES = 256

SIZES = (
    "Tiny",
    "Small",
    "Medium",
    "Large",
    "Huge",
    "Gargantuan",
)
PROFILES = ("tall", "long")
PROFILE_EVIDENCE_KINDS = (
    "exact-creature-block-plus-reviewed-morphology",
    "whole-creature-prose",
    "authored-traits-plus-canonical-default",
)
STRIKE_REACH_KINDS = (
    "explicit-trait",
    "bare-weapon-trait",
    "natural-reach",
    "not-applicable-ranged",
)


def _bind_first_gate_profile_catalog():
    """Capture the exact reviewed Core MC1 geometry corpus."""

    rows = (
        ("10.2", "Pleroma", "Large", "5bf35a90175a8220b30d21ae391b2f286ca02668a66cee61d2f88f02044b3f05", "tall", 10),
        ("12.5", "Vidileth", "Large", "b5f8e062bd7af1a44c61eb56d318cb633611668d4803b0864d87effa7598f619", "long", 5),
        ("19.4", "Giant Animated Statue", "Huge", "cb31737c67e35bb428e5f05906630acd7c2fcbc36faaba321ba2dc7b70ae6dff", "tall", 15),
        ("20.3", "Ankhrav", "Large", "35dff795927d8bd3870a52bb7a386da2e838768b8a5e4e8defee6d6e0ffff787", "long", 5),
        ("20.5", "Ankhrav Hive Mother", "Huge", "e89639d4fe53c6c84ba8a95b73fb3fc97087d93b0fe0eb6aae7fc75d5547fe41", "long", 10),
        ("22.1", "Aolaz", "Gargantuan", "b32e535da0952392e6862968053c55cac3d0296b5a0c041a72693485cdc1b8bb", "long", 15),
        ("23.3", "Gorilla", "Large", "41fe3919aec1badd2f4f098eb589c002879380166e3d288e1e6971ccb9e15269", "tall", 10),
        ("23.5", "Megaprimatus", "Gargantuan", "69cadc1179fd07a2799a1f1000d12b0527469be8336ca36626e5fc581c1f6a6a", "tall", 20),
        ("36.1", "Bandersnatch", "Gargantuan", "9b2c84876e0a20158240e5e2d6ab41a38aff5ae5a0f1e0893ee096317692a9a2", "long", 15),
        ("40.5", "Giant Bat", "Large", "1e7bdab9f12501631d0e4c7ff162c0978ca53c9b462115444af6e99011a2b7c9", "long", 5),
        ("41.3", "Grizzly Bear", "Large", "8e1aa49c4ef956e4268e6397daf0417ba24911fd3936fd0b3e22fee5722960c9", "long", 5),
        ("41.5", "Cave Bear", "Large", "9a881453c2f17d09310b1fd7e9c5f71da8b54895839816912a523397305eb6cf", "long", 5),
        ("42.6", "Giant Stag Beetle", "Large", "fdf95ff1eb3e21038de2028ff3d8f5c85af1a4795b87a1897d6285d07ed12e18", "long", 5),
        ("50.5", "Lion", "Large", "f9adb992f8afe225d810fe0300fecaae1e3dd2e90921807f4abed8d0acc8ba01", "long", 5),
        ("51.2", "Tiger", "Large", "3e7fd1209d65bc42162a243d92f1c62889fafbc0e046fff84ce2e37586667ef3", "long", 5),
        ("51.4", "Smilodon", "Large", "f52b3131edc0eb25f83e9760ff6871e6cd188d8f7aacfac8061ec93eda14a557", "long", 5),
        ("54.2", "Cave Worm", "Gargantuan", "05ffc841ab08911f553dfa14d4944cb74a83390c34923c818e3fb090afe9603c", "long", 15),
        ("56.2", "Benthic Worm", "Gargantuan", "80e1ebe9a71023651920fa9dc8d043ac58cbed36770a0b46b3370e07ca741dfd", "long", 15),
        ("57.2", "Magma Worm", "Gargantuan", "3aea8d06e95fb088cee07836658cefcb547b5e99199fc1a0ee515e94cc6d7767", "long", 15),
        ("58.2", "Centaur Herbalist", "Large", "a57c83d0ac88136b7172bc3186bfdc2ae0df2c524fd9d1ea85471c9b3779c2dc", "long", 5),
        ("62.1", "Chimera", "Large", "9d8573b2e3429e37e309580fa2c5dfb89a7e1c2b8849a120bc3fc29454b4bc1f", "long", 5),
        ("67.1", "Con Rit", "Huge", "a155a2751dfbe3c5e87f9ef488eee74aa9a90cb6685e1969af01e7df555be79c", "long", 10),
        ("69.3", "Crocodile", "Large", "3091b2760de483b6316ad663bcc152e4191de6716b8abc8b7a4f6d397f26932c", "long", 5),
        ("69.6", "Deinosuchus", "Huge", "0ba1d60b718e56b68b4b79c0a44baea7d7be58c6cabd0cd4f7f938eb764c7970", "long", 10),
        ("70.3", "Cyclops", "Large", "6a0936fd30313b56cada0bed371e91b447256ba0f4acb62822a3bba720a33b32", "tall", 10),
        ("71.2", "Great Cyclops", "Huge", "180561e2e131daba2a7d82ae6777cd92ccd99070593bd6d999a2bece9040bf45", "tall", 15),
        ("97.4", "Pachycephalosaurus", "Large", "a9bc1d43d80bf86d02dd6da380d48df545b749cd865f9f40286f313e2ebbd6fb", "long", 5),
        ("98.2", "Hadrosaurid", "Huge", "b4e3d84a9041cc5e0640dfd59764662e54c20be75890172d9f2a88bb21e1240a", "long", 10),
        ("98.4", "Ankylosaurus", "Huge", "525f1606d823e1d56f2f0ceaf3ad4194badce75ef434b4779f335e077ac59652", "long", 10),
        ("99.3", "Stegosaurus", "Huge", "cb668ae0910ed64a20de7b914c3ef31ed3a9b790ce0ca65d3b51869fd3105b6b", "long", 10),
        ("99.5", "Triceratops", "Huge", "da2095c66180e3cad516263dced51bb998972c27172f60862acb16d013041a09", "long", 10),
        ("100.3", "Brontosaurus", "Gargantuan", "2e567522a37d8b4b994aa8dc4815523e6c40f72226f21d6ca085d4c06350af40", "long", 15),
        ("101.2", "Tyrannosaurus", "Gargantuan", "1c80e4b4d7d010b9996514e7a3de5fab0339ae61ef39f62e3c3e5a9c3c7c308a", "long", 15),
        ("103.4", "Orca", "Huge", "bdd9dd3dac091c033df2aa494a2d990fbbe52c17d8942b6a72d6835bb1a9e37c", "long", 10),
        ("108.5", "Young Adamantine Dragon", "Large", "f67092169cdfac2d1d1b0dd733876285d0aa9a8c8d424ccec5ddb2c545f06874", "long", 5),
        ("109.2", "Adult Adamantine Dragon", "Huge", "32713d6e38658ee86daaebebd699ad6f227926bf7a3eb82e095748686873cfaf", "long", 10),
        ("109.3", "Ancient Adamantine Dragon", "Gargantuan", "ca35f1d0f3e5602c4748bea66db042774920de66546ff81a550d7a4f0da3b96c", "long", 15),
        ("110.4", "Young Conspirator Dragon", "Large", "11e44d6761df055a06fc62b7dc274d4eff9d665836afe8f91a955eb522887d3e", "long", 5),
        ("111.2", "Adult Conspirator Dragon", "Large", "40bb8c8604e0bb7b2a29a2817eac4cd21a49f1919fb5f21fc84313a1e35f9176", "long", 5),
        ("112.1", "Ancient Conspirator Dragon", "Huge", "0bc08c85ef6d08d93c68d475ca2c2310c1f99bb9b2307ca3e00c5a027e3b13c3", "long", 10),
        ("117.2", "Young Fortune Dragon", "Large", "69970a7e4c78116ff72e3e00423458956c7c09f953c6363830be90bd5ef2606e", "long", 5),
        ("118.1", "Adult Fortune Dragon", "Huge", "07ae2d38e9ab421694e52e1e5a942b3684846df5897db0825ae6ce589565ff45", "long", 10),
        ("118.2", "Ancient Fortune Dragon", "Gargantuan", "46490aed569819d38450ee95f05424d8f03db7da1d1ee4bfe2d2cd64fd268476", "long", 15),
        ("119.3", "Young Horned Dragon", "Large", "a9ecd72b8c2f74a4f69adc79d086648ac4b9d6f1bb6735655ac393394100b746", "long", 5),
        ("120.1", "Adult Horned Dragon", "Huge", "b938aa98d7d6bec306f7ace48adc893dad2c9e51135b5d3d8bb5c2df38686dae", "long", 10),
        ("121.2", "Ancient Horned Dragon", "Gargantuan", "e46176caf6258b9838a0f8ab24384dacd8ea5cd02f941babed63877a3e9dc6e3", "long", 15),
        ("122.1", "Young Mirage Dragon", "Large", "e34cb1063069a686f830d0f0ae10c4e4178a594f8a9a7788507e4529ae20c3f4", "long", 5),
        ("122.2", "Adult Mirage Dragon", "Huge", "24cdc2b2769f56fe17588c49cb416491102978d60cacefa195fc012776910cae", "long", 10),
        ("123.2", "Ancient Mirage Dragon", "Huge", "97b960c14611aa30d1c2c8adc5156e20f465c5935e276068c771b8dc9bee76a7", "long", 10),
        ("124.1", "Young Omen Dragon", "Large", "159af5eedd3538d4433dfc4567898994705333e020eaad705d285d95c998c968", "long", 5),
        ("124.2", "Adult Omen Dragon", "Large", "37aa585af68acd249dd38e0bda4de4fc9d45ad3b66b2fb6f52f36c2fd8624451", "long", 5),
        ("125.2", "Ancient Omen Dragon", "Huge", "51f4d8de78e8620e658f637021f1fb97b2ed19dd000b46a95d88d28a0f134760", "long", 10),
        ("126.1", "Dragon Turtle", "Huge", "f3450391991ec2ee8e1b4ea753991779940a738a43a22bd214dc7103037eee54", "long", 10),
        ("129.3", "Flame Drake", "Large", "9e4384f5c7afbe2c6b89f4ecc75258aa96b57eae1910ee595703a47e7484f5ec", "long", 5),
        ("130.1", "Jungle Drake", "Large", "02db86642e4816e9d8f9da4dc04fda74931ace177b65bcf55c8a9a2368562e65", "long", 5),
        ("132.1", "Frost Drake", "Large", "35cdc44d799b8707537c8fab613a993ce88b6bd442610307b3db00004af303cc", "long", 5),
        ("133.1", "Desert Drake", "Large", "340e2bf47de27ba70af60348cc2af0623fa31032ff12e761f54f5400dd57578e", "long", 5),
        ("137.4", "Giant Eagle", "Large", "7c738389af46556f5050267606ef6feeebc852c98cb0e81b7485d73840132d42", "long", 5),
        ("138.4", "Giant Moray Eel", "Large", "a13eba21e98bc81d65ce0ea5325fbf4549f632ddad9b14255ac1b7e81bafcc09", "long", 5),
        ("141.2", "Elemental Hurricane", "Huge", "15f4d5f0a6ed7d9adac933e1229ee7b301262a84059e02f959f0bfa535396783", "tall", 15),
        ("142.6", "Stone Mauler", "Large", "cb2cc4980ea444a0a4bbe60093f6d44fcd1760947cb4754095102b672e6c999c", "tall", 10),
        ("143.2", "Elemental Avalanche", "Huge", "34f04fd7ca13cdc40dfb0292b04f48a35d6790afaa627c783d6b718da7aeeb22", "tall", 15),
        ("148.4", "Living Waterfall", "Large", "720b9c6d40ef7ded98900018f83e8ebc8f13c66cb62f0777f1c1f7ce847101b4", "tall", 10),
        ("149.2", "Elemental Tsunami", "Huge", "3590c73e97edf1d6a1bc36d1b17d419208290b4516f24fa16c5475d917b24988", "tall", 15),
        ("150.2", "Elephant", "Huge", "975ac309b29d4f1e4aaa40a9a5f9ddda2621f32cdbb5d0d43a2d6555e14e2ebe", "long", 10),
        ("150.4", "Mammoth", "Huge", "b121924c4379e25dbf3ad8e32fbb69ffb7a68ba3374e810275c1aeecc4ce7810", "long", 10),
        ("153.1", "Irnakurse", "Large", "6e0289b5267d88f3d5d9225a6c158e313757753de194218f33678d8a1e831e9e", "long", 5),
        ("154.2", "Snapping Flytrap", "Large", "a1112615ec0fd4df94727648e95acd74a7981c7c8f8dde2ed08644ad2135db17", "tall", 10),
        ("154.4", "Giant Flytrap", "Huge", "7cdb43880d0c43673e71177f0aee936cf7993eb2a4b468dd394ed964ffd9049e", "tall", 15),
        ("157.1", "Jaathoom", "Large", "0dfa756437fd2ad88c0c006bbbfd1b13fc88febbc8309e12c03e94d63801e2c2", "tall", 10),
        ("158.1", "Jabali", "Large", "e1eee813b5397e865b102c82ecb2cddf52c57468ce907c3096a01582ca615618", "tall", 10),
        ("158.3", "Faydhaan", "Large", "5d53c3de6d6c3a4b8553544a772814374c6a441d9a848df857d7ad27022627f3", "tall", 10),
        ("164.2", "Marsh Giant", "Large", "c3a99bc89828ee9d0023d87621490d226074b378bedb90fb2075e1af84e7804d", "tall", 10),
        ("164.4", "Stone Giant", "Large", "bcbab50fa80d2aaf3c9ae903c821bedb709dae0cfe0287171d1a2e1472d70583", "tall", 10),
        ("165.2", "Frost Giant", "Large", "25b27b0a4a56cef78f1cb3d828ad18f74eadc4f2be117b04b0730fbc7107e70e", "tall", 10),
        ("166.2", "Fire Giant", "Large", "f9144cffb46c536a8d83089122195bb690de1af63d9b4302bba090174895df64", "tall", 10),
        ("167.1", "Cloud Giant", "Huge", "fe498b936db6e58f51d3f376a929e8dffa4c4605c66c0b79d6e602b14342d2cd", "tall", 15),
        ("168.1", "Shadow Giant", "Large", "0e69cfc9da695e2290a2d8cbf9833a405e85f2c068fc392994781da4d94167d0", "tall", 10),
        ("168.3", "Rune Giant", "Gargantuan", "aa0fcaac7fc74bf96eaeaa47eb96aaba0d8703dbe39ad0369e9680fe36ce3426", "tall", 20),
        ("171.1", "Globster", "Large", "dbc5144cabb145aac7ca528ae40efd228b6bf2a2c2083ab74f9005434cc58e51", "long", 5),
        ("177.1", "Gogiteth", "Large", "26f85ee6eac43661a4c35495a6eefe92981f1fec102a0f277775499c093e667c", "long", 5),
        ("182.1", "Griffon", "Large", "8db6f99f85a43c90781b9d5ea9997fe2422ef314109e26c7819603d783e60a61", "long", 5),
        ("190.1", "Iron Hag", "Large", "6e12c296ab75db1134a60a39219182312e5fe439d0266ca854175c5e513954cc", "tall", 10),
        ("194.4", "Greater Hell Hound", "Large", "ff2752570cd5e6beffd9e77254d6f3e108d9950c7a6fe7ed24614bf569638ea4", "long", 5),
        ("196.2", "Hippocampus", "Large", "0dffdf2bca212eab3f280cae1f028b8bb413cc6070cb56fafb78d2b0fe17497a", "long", 5),
        ("196.4", "Giant Hippocampus", "Huge", "d0ad07782f129145c682a26a57e929518df0fcc3192384133c894f75c2ced9f1", "long", 10),
        ("197.1", "Hippogriff", "Large", "060f942f6360cb1e2df2494db77b9f0c87ffc45aeb4b9dc78da4b6b54eab9192", "long", 5),
        ("201.4", "Riding Horse", "Large", "ea57b8d4d5ee2243153ee1b38141020599b45d3a803ee3305a2fab2cf23d40ce", "long", 5),
        ("201.8", "War Horse", "Large", "7c852eb0f5feb7f139fd9587cbc3dbbb8c730d61a5a5b98950315e61d0d7f2fd", "long", 5),
        ("204.1", "Hydra", "Huge", "e2a7c252b47298ffd62322002a7573ae535ecf507c16ff08e2956d668197d6c2", "long", 10),
        ("205.4", "Hyaenodon", "Large", "4cb70dbd792a99a14cc2e24f96f248f5ad27c2fad7eb41ea31638620cf122a5c", "long", 5),
        ("212.1", "Kraken", "Gargantuan", "285a5bfe7576b30fde9b952324da5b6fe538513bb723ddfa0ed77887c3bbfb7d", "long", 15),
        ("213.1", "Krooth", "Large", "9744d08427259a34a9d48df06c79dccea1a9220f52cab711d4ff8bd92370585c", "long", 5),
        ("214.2", "Lamia", "Large", "aa68914db6db05af1f7b88485953e7bcb65fb0e4a1e8972c68f865b012e009c7", "long", 5),
        ("215.1", "Lamia Matriarch", "Large", "195fd7c3dc83745e8acd629d12dbe2cfa21238b22f0e158decb3a816185a96ae", "long", 5),
        ("220.2", "Crag Linnorm", "Gargantuan", "1f6e3d3c1b6d346a7a01002be250ee7388c4e5b9ae30e611273dfa0870364f09", "long", 15),
        ("221.1", "Ice Linnorm", "Gargantuan", "e9965081eb95f377cd25e257b5aec719a6ab7cf73ff516e4237727ff27d19f93", "long", 15),
        ("221.3", "Tarn Linnorm", "Gargantuan", "ab663d35f5309adb3e4d6ca49663dbdced02c9a5fcac4bd77007a40b7d7830c0", "long", 15),
        ("222.1", "Tor Linnorm", "Gargantuan", "ab2c60b415396007000115af906316d30e0e895097a911889cd48735f6054e19", "long", 15),
        ("225.2", "Giant Frilled Lizard", "Large", "9fb3cdb5b20d1aca589af4caf8aecfba98d3022ff1561e7b2985b3a30b3fb965", "long", 5),
        ("228.1", "Manticore", "Large", "995a522da0c5dfc8b8fe40ffc97bbfc61d80f627d57ff242fcbb85719e7d9647", "long", 5),
        ("229.2", "Giant Mantis", "Large", "3363ec1e10f3ac34184c1429e633ba9ce320b851fa9e8157d6d47a242150811b", "long", 5),
        ("229.4", "Deadly Mantis", "Gargantuan", "8e1b53f5957e406a1109cb2df85cf3f929e6470c330a9cb90561ab7629d7fc58", "long", 15),
        ("232.1", "Minotaur Hunter", "Large", "d5c81c0676d1a775fdac035738eb68042309242ff84c43f89068548f0cd582d2", "tall", 10),
        ("233.1", "Mukradi", "Gargantuan", "0a2703de5e3db0f92f48267460cb15910e4aac8a5317590daf67ca5abe7a452c", "long", 15),
        ("236.2", "Smaranava", "Large", "c98a165427db6dbfbcdb4b780161523be818dd7d0535bbbe2241edd7c5157658", "long", 5),
        ("237.1", "Vicharamuni", "Large", "4f5bd48e654479c2c1c32e2a302950ede5e5a39e46016ddd401787e57a871d39", "long", 5),
        ("238.2", "Nightmare", "Large", "11b0402d1737ed353b5c0ffa2bae22656b12a53be829961ecd67cf583357399d", "long", 5),
        ("238.3", "Greater Nightmare", "Huge", "dfe2652d1af3e1db1f8cf64db26a2c81ffc924e5904fb000fe2361056d28552e", "long", 10),
        ("240.1", "Norn", "Large", "e0877b9f7dfdeb87bd26bf8631a42bf5d1c33e16d0f41f74c4f87bcd08e41cf4", "tall", 10),
        ("243.1", "Nuckelavee", "Large", "92c689a1a66fb448e74bba6ccde2ee7d2e6302445665218af9ac6182f1948813", "long", 5),
        ("248.1", "Giant Octopus", "Huge", "066055ec7f687aec7a301164ea9d1fa871c2f2ebb2ebf030657b8b678367d8ce", "long", 10),
        ("249.4", "Ofalth", "Large", "6178b0439915fc2d18275f28de3967c7c2413e6636fcca89fce2bf446b530a3f", "tall", 10),
        ("250.2", "Ogre Warrior", "Large", "0790362a2819dd4890164dbb09eaa2c641724b0f9c0b2d1a03b9311360f3a836", "tall", 10),
        ("250.4", "Ogre Glutton", "Large", "1033a2cc58300fd489578724ab9064e3f4f8636598f55b480a3ac68986c55539", "tall", 10),
        ("251.2", "Ogre Boss", "Large", "48ef94c357adf9fbad0134f75f9abfa512d65ceab84c80c9276d2949ffd142a5", "tall", 10),
        ("256.4", "String Slime", "Large", "2b97051f8bdb0b76d54e48503ecc2dbf7c993cafa14d29f7a9ff9318b9f1686c", "long", 5),
        ("257.1", "Tomb Jelly", "Large", "23b87a9c510d0c8e4ffc79bda93f1a0776849ba82b04aab090f131c0ca222521", "long", 5),
        ("257.3", "Living Tar", "Huge", "7d07cf84ca99ab4bc8866e2fcc01602ba4812c232eee671cee048c2a405b5b1f", "long", 10),
        ("261.1", "Pegasus", "Large", "37353ba8e01d9a36206696e2c1ad476dedd0b4ff562b518b7c243310891f9f28", "long", 5),
        ("276.4", "Yamaraj", "Huge", "264842e6aba75fefee466ea3bd7d959566e6c0da6c754a40ea4722153421cfd8", "long", 10),
        ("278.3", "Pteranodon", "Large", "61c7a40369b307e909c23a0e06343e0c4df89213c128236746b8de5572aa60f5", "long", 5),
        ("278.5", "Quetzalcoatlus", "Huge", "1f44558e2da0eef21f225bd8925ac262200c184e46abfd442a2ed5c84902adfd", "long", 10),
        ("281.3", "Augnagar", "Huge", "4270b0b3ddf45b1d60595577583ab70b31535186d45fb56054b31b945616f5cb", "long", 10),
        ("283.1", "Thulgant", "Large", "2f6d4a96c6d3f5d80bbb1741774893fef8e7d49048322b326cbd00c89d386bae", "long", 5),
        ("284.1", "Quai Dau To", "Huge", "c7607491818a63014bfc978f023db64f99633c21affe648eef0ad3a42662fb57", "long", 10),
        ("285.1", "Quelaunt", "Large", "1c8a8370e0ddd6b5f101750db8789884410bef6795a7225efe45a3e1a308813f", "tall", 10),
        ("293.2", "Rhinoceros", "Large", "1e10c9e207310a06ce92503dcfa09d9248859ce77d84287f05cd55ccaf3626df", "long", 5),
        ("293.4", "Woolly Rhinoceros", "Large", "6c1450cf86017f570b17d2ced80c5672764dfad40b5fc202c0606bb705516765", "long", 5),
        ("294.1", "Roc", "Gargantuan", "27499fbc4c4a097e6387b6b50d7955f595445bdcef4ed6204e4a8f06555972db", "long", 15),
        ("295.2", "Sargassum Heap", "Large", "82c64492e784c54d928537b1de04378001c314cc30ceb552a7bfe7e6bcaa0935", "long", 5),
        ("295.3", "Doldrums Heap", "Huge", "e54568ca6fad22777056fa5f49c2336acb5739cffbf1934d131a6ca7f0d0b10b", "long", 10),
        ("299.1", "Sea Serpent", "Gargantuan", "aa79096ecc5d5e8ca7cc70781f7005e51273b855fcab19c0875998aec525073d", "long", 15),
        ("307.2", "Great White Shark", "Huge", "bae80aa20138e1e0d3955f8d27296bd2013f5e8f38152967b822e96932b74463", "long", 10),
        ("307.4", "Megalodon", "Huge", "395ae1958722de821d72d505cf9111ec204fa80e8921626c77b2b0cf145ebc4e", "long", 10),
        ("313.1", "Skeletal Horse", "Large", "05275fc5f6acf2c34b455876be298450b0d3088c1211613814f4b0ce2016d050", "long", 5),
        ("313.4", "Skeletal Giant", "Large", "af8f38b39dbf163573a31ca4a5330a19f2d8143bb12d055effa8a1e57de7f33c", "tall", 10),
        ("313.6", "Skeletal Hulk", "Huge", "34e811d1ba0a0c1a96518525add9a23d9dbb35963d197a1be41b2d7c576965a0", "tall", 15),
        ("314.1", "Skulltaker", "Huge", "9be5ab67387cb43922858b3ecfb14ef395d16a973bdb4a9604f1d1c7d3a1fe39", "tall", 15),
        ("317.2", "Giant Anaconda", "Gargantuan", "bf84fc14187d3e71b265814a37d3646991698412e338b1641569aeb28d1b3c63", "long", 15),
        ("319.1", "Sphinx", "Large", "311d81dacc404765339168ac45fee9e0b5b465404fc7bb43db8bb86913527901", "long", 5),
        ("321.1", "Giant Tarantula", "Large", "7de48ecd2adfac7a95b3608f09a8b7fec771b13bab2f386acdd104b206c65932", "long", 5),
        ("321.3", "Goliath Spider", "Gargantuan", "7a6d6f5bbd06d361a839aa329acc64d4da19e4060c813bd36258bfe20e8a0ba9", "long", 15),
        ("330.2", "Forest Troll", "Large", "b6ead532bb3ba6c8d2b3894c47f86ceabb40d5bc1439aedea44fff0b2968b151", "tall", 10),
        ("331.1", "Troll Warleader", "Large", "3411d9d66333011129eca142db1097f919f333d2262a4abb92f19e1871cb0e95", "tall", 10),
        ("333.1", "Unicorn", "Large", "e6006379104d72db917723d52026e4a4e4ab970157b0f74f249002a6d85f51b1", "long", 5),
        ("341.4", "Witchwarg", "Large", "7e0db92cd6b559427475510a2189225ac133b152de6f0b7879b8aabe00baf9a1", "long", 5),
        ("342.1", "Warsworn", "Gargantuan", "02a9d22e337556c338faa211843c94bec79f7b6c6ddf75d738c0109a541fb8cf", "long", 15),
        ("343.2", "Giant Wasp", "Large", "4ebd64d6ea597cf31f9f1fe10fbb69de934f2f1ccfe8d6da46176c3620944516", "long", 5),
        ("346.3", "Werebear", "Large", "ca676dd483108abbff1c647725f953e533f80f270199aa80acfa5a5fa7923a09", "tall", 10),
        ("347.1", "Weretiger", "Large", "83e287467f8206d2197a6a2a7dee02ea9c302297bffd95378afe098795cb7dd7", "tall", 10),
        ("350.4", "Dire Wolf", "Large", "e802399982ede46bbadaf01308429d0779cf90dcb2e1431d407c0a78ca07da03", "long", 5),
        ("354.1", "Yeti", "Large", "79a403b1a15c4e0158044c1cf2cdc2282a3ae20c08328c85c5ecccfd26dd4294", "tall", 10),
        ("357.2", "Zombie Brute", "Large", "a9d53d123b315bcac41bd79f4af237c563501dce00ab86129ef1a5bda81124f8", "tall", 10),
        ("357.4", "Zombie Hulk", "Huge", "8f8c3e76806ebaf0490f03b75fcc65d8a89730100d05c3cd9a627721076b205f", "tall", 15),
    )
    schema = 2
    reviewer = "kmqdb:core-mc1-first-gate-geometry"
    artifact = "core-mc1-first-gate-geometry-review"
    governing_rules = (
        (
            "core-gmc",
            "114.2",
            "0a94b193ad8541e980a07bb843f55450e3455c00ca0c4abe9e3f0c01a133c350",
        ),
        (
            "core-pc1",
            "421.8",
            "57f6c8bd51c2367bedfda5464ec295229a54363d5576a671fbda1fda3ab01fb6",
        ),
    )

    def record(row: tuple[object, ...]) -> dict[str, object]:
        locator, name, size, block_sha256, profile, reach = row
        return {
            "blockId": f"core-mc1:{locator}",
            "sourceId": "core-mc1",
            "locator": locator,
            "name": name,
            "authoredSize": size,
            "orderedBlockSha256": block_sha256,
            "profile": profile,
            "naturalReachFeet": reach,
        }

    manifest_json = json.dumps(
        {
            "artifact": artifact,
            "governingRules": [
                {
                    "sourceId": source_id,
                    "locator": locator,
                    "selectionSha256": selection_sha256,
                }
                for source_id, locator, selection_sha256
                in governing_rules
            ],
            "recordCount": len(rows),
            "records": [record(row) for row in rows],
            "reviewer": reviewer,
            "schema": schema,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    manifest_sha256 = hashlib.sha256(
        manifest_json.encode("utf-8")
    ).hexdigest()
    if (
        len(rows) != 155
        or len({row[0] for row in rows}) != len(rows)
        or manifest_sha256
        != "c17bcaeae11f702f34785e17607507af764302e8d30fd9f0bdd06d6ffd1b1c02"
    ):
        raise RuntimeError("reviewed geometry catalog invariants changed")

    def for_source(
        source: CreatureGeometrySource,
    ) -> tuple[object, ...] | None:
        identity = (
            source.locator,
            source.creature_name,
            source.size_source_text,
            source.reviewed_stat_block_sha256,
        )
        return next(
            (
                row
                for row in rows
                if row[:4] == identity
            ),
            None,
        )

    def for_block_id(block_id: str) -> tuple[object, ...] | None:
        if (
            type(block_id) is not str
            or not block_id.startswith("core-mc1:")
        ):
            return None
        locator = block_id.removeprefix("core-mc1:")
        return next(
            (row for row in rows if row[0] == locator),
            None,
        )

    return manifest_json, manifest_sha256, record, for_source, for_block_id


(
    PROFILE_REVIEW_MANIFEST_JSON,
    _profile_review_manifest_sha256,
    _profile_catalog_record,
    _profile_catalog_for_source,
    _profile_catalog_for_block_id,
) = _bind_first_gate_profile_catalog()
if _profile_review_manifest_sha256 != PROFILE_REVIEW_MANIFEST_SHA256:
    raise RuntimeError("public profile-review manifest hash disagrees")
del _bind_first_gate_profile_catalog
del _profile_review_manifest_sha256


@dataclass(frozen=True, slots=True)
class CreatureGeometrySource:
    """Authority-reloaded Size and Speed selections for one creature."""

    authority: SourceAuthorityAdapter
    size_selection: VerifiedSourceSelection
    speed_selection: VerifiedSourceSelection

    def __post_init__(self) -> None:
        # The closure-bound exact contract is installed below.  This method
        # must exist while @dataclass builds __init__ so construction invokes
        # the installed validator.
        raise RuntimeError("CreatureGeometrySource contract is not bound")


def _bind_creature_geometry_source_contract(
    source_type: type[CreatureGeometrySource],
    adapter_type: type[SourceAuthorityAdapter],
    selection_type: type[VerifiedSourceSelection],
    member_step_type: type[RawMemberStep],
    raw_member_type: type[RawSourceMember],
    raw_object_type: type[RawSourceObject],
    raw_array_type: type[RawSourceArray],
):
    """Capture exact Size+Speed source semantics below mutable globals."""

    maximum_block_bytes = 262_144
    maximum_nodes = 8_192
    maximum_depth = 16
    maximum_members = 1_024
    maximum_key_bytes = 256
    maximum_string_bytes = 65_536
    maximum_path_steps = 32
    maximum_identifier_bytes = 4_096
    maximum_size_bytes = 256
    maximum_speed_bytes = 512
    maximum_integer = (1 << 63) - 1
    size_rule = ("core-mc1", "361.3")
    article_owned_fields = frozenset(
        ("Description", "Icon", "Image")
    )
    json_dumps = json.dumps
    sha256 = hashlib.sha256
    isfinite = math.isfinite
    validate_selection = adapter_type.validate_selection
    invalid_payload = object()

    def require_text(value: object, label: str) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
        ):
            raise ValueError(
                f"{label} must be a non-empty trimmed string"
            )
        if len(value.encode("utf-8")) > maximum_identifier_bytes:
            raise ValueError(f"{label} exceeds its byte bound")
        return value

    def bounded_payload(
        value: RawSourceValue,
        *,
        depth: int,
        nodes: list[int],
    ) -> Any:
        if depth > maximum_depth:
            return invalid_payload
        nodes[0] += 1
        if nodes[0] > maximum_nodes:
            return invalid_payload
        if type(value) is raw_object_type:
            if len(value.members) > maximum_members:
                return invalid_payload
            members = []
            for member in value.members:
                if (
                    type(member) is not raw_member_type
                    or len(member.key.encode("utf-8"))
                    > maximum_key_bytes
                ):
                    return invalid_payload
                item = bounded_payload(
                    member.value,
                    depth=depth + 1,
                    nodes=nodes,
                )
                if item is invalid_payload:
                    return invalid_payload
                members.append([member.key, item])
            return {"$orderedObject": members}
        if type(value) is raw_array_type:
            items = []
            for raw_item in value.items:
                item = bounded_payload(
                    raw_item,
                    depth=depth + 1,
                    nodes=nodes,
                )
                if item is invalid_payload:
                    return invalid_payload
                items.append(item)
            return items
        if type(value) is str:
            if len(value.encode("utf-8")) > maximum_string_bytes:
                return invalid_payload
            return value
        if value is None or type(value) is bool:
            return value
        if type(value) is int:
            if value < -maximum_integer - 1 or value > maximum_integer:
                return invalid_payload
            return value
        if type(value) is float:
            return value if isfinite(value) else invalid_payload
        return invalid_payload

    def ordered_hash(value: RawSourceValue, /) -> str | None:
        payload = bounded_payload(value, depth=0, nodes=[0])
        if payload is invalid_payload:
            return None
        encoded = json_dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > maximum_block_bytes:
            return None
        return sha256(encoded).hexdigest()

    def validate(self: CreatureGeometrySource) -> None:
        authority = getattr(self, "authority", None)
        size_selection = getattr(self, "size_selection", None)
        speed_selection = getattr(self, "speed_selection", None)
        if type(self) is not source_type:
            raise TypeError("CreatureGeometrySource must be exact")
        if type(authority) is not adapter_type:
            raise TypeError(
                "CreatureGeometrySource.authority must be exact "
                "SourceAuthorityAdapter"
            )
        if (
            type(size_selection) is not selection_type
            or type(speed_selection) is not selection_type
        ):
            raise TypeError(
                "CreatureGeometrySource fields require verified selections"
            )
        size = validate_selection(authority, size_selection)
        speed = validate_selection(authority, speed_selection)
        object.__setattr__(self, "size_selection", size)
        object.__setattr__(self, "speed_selection", speed)

        size_address = size.address
        speed_address = speed.address
        if (
            (
                size_address.source_id,
                size_address.locator,
                size_address.section_id,
                size_address.target_path,
                size_address.carrier_path,
            )
            != (
                speed_address.source_id,
                speed_address.locator,
                speed_address.section_id,
                speed_address.target_path,
                speed_address.carrier_path,
            )
        ):
            raise ValueError(
                "Size and Speed selections must share one exact carrier"
            )
        if (
            size_address.span is not None
            or speed_address.span is not None
            or len(size_address.selection_path) != 1
            or len(speed_address.selection_path) != 1
            or type(size_address.selection_path[0])
            is not member_step_type
            or type(speed_address.selection_path[0])
            is not member_step_type
        ):
            raise ValueError(
                "Size and Speed must be exact whole-member selections"
            )
        carrier_path = size_address.carrier_path
        content_path = (
            size_address.target_path + carrier_path[:-1]
            if carrier_path
            else size_address.target_path
        )
        if (
            not content_path
            or len(content_path) > maximum_path_steps
            or any(
                type(step) is not member_step_type
                or len(step.raw_key.encode("utf-8"))
                > maximum_key_bytes
                for step in content_path
            )
        ):
            raise ValueError(
                "verified content path is outside family bounds"
            )
        if (
            not carrier_path
            or any(
                type(step) is not member_step_type
                for step in carrier_path
            )
            or carrier_path[-1].raw_key != "^.creature"
            or any(
                step.raw_key == "^.creature"
                for step in carrier_path[:-1]
            )
        ):
            raise ValueError(
                "verified carrier path must end at one ^.creature member"
            )
        if size.carrier.raw_block != speed.carrier.raw_block:
            raise ValueError(
                "Size and Speed verified carriers disagree"
            )
        block = size.carrier.raw_block
        if type(block) is not raw_object_type or ordered_hash(block) is None:
            raise ValueError(
                "verified creature block exceeds family bounds"
            )
        for label, selection, expected_key, byte_bound in (
            ("Size", size, "Size", maximum_size_bytes),
            ("Speed", speed, "Speed", maximum_speed_bytes),
        ):
            step = selection.address.selection_path[0]
            member = selection.raw_member
            if (
                type(member) is not raw_member_type
                or member.key != expected_key
                or step.raw_key != expected_key
                or step.member_ordinal >= len(block.members)
                or block.members[step.member_ordinal] != member
                or type(selection.selected_value) is not str
                or selection.selected_value != member.value
                or not selection.selected_value
                or selection.selected_value
                != selection.selected_value.strip()
                or len(selection.selected_value.encode("utf-8"))
                > byte_bound
            ):
                raise ValueError(
                    f"{label} selection is not one exact bounded string "
                    "member"
                )
            candidates = tuple(
                index
                for index, candidate in enumerate(block.members)
                if candidate.key.strip() == expected_key
            )
            if candidates != (step.member_ordinal,):
                raise ValueError(
                    f"verified creature requires one exact {expected_key} "
                    "member without key collisions"
                )
        name_indices = tuple(
            index
            for index, member in enumerate(block.members)
            if member.key.strip() == "Name"
        )
        if len(name_indices) != 1:
            raise ValueError(
                "verified creature requires one exact Name"
            )
        name_member = block.members[name_indices[0]]
        if (
            name_member.key != "Name"
            or type(name_member.value) is not str
        ):
            raise ValueError(
                "verified creature Name must be exact text"
            )
        require_text(
            name_member.value,
            "CreatureGeometrySource.creature_name",
        )

    def source_id(self: CreatureGeometrySource) -> str:
        return self.size_selection.address.source_id

    def locator(self: CreatureGeometrySource) -> str:
        return self.size_selection.address.locator

    def section_id(self: CreatureGeometrySource) -> str:
        return self.size_selection.address.section_id

    def receipt_digest_value(
        self: CreatureGeometrySource,
    ) -> str:
        encoded = json_dumps(
            {
                "authorityDigest": (
                    self.size_selection.receipt.authority_digest
                ),
                "sizeReceiptDigest": (
                    self.size_selection.receipt.digest
                ),
                "speedReceiptDigest": (
                    self.speed_selection.receipt.digest
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def creature_receipt_digest(
        self: CreatureGeometrySource,
    ) -> str:
        validate(self)
        return receipt_digest_value(self)

    def definition_id(self: CreatureGeometrySource) -> str:
        return (
            f"{source_id(self)}/verified#"
            f"{receipt_digest_value(self)}"
        )

    def creature_name(self: CreatureGeometrySource) -> str:
        names = raw_block(self).values("Name")
        if len(names) != 1 or type(names[0]) is not str:
            raise ValueError(
                "verified creature Name is no longer exact"
            )
        return names[0]

    def ordered_block_sha256(
        self: CreatureGeometrySource,
    ) -> str:
        value = ordered_hash(raw_block(self))
        if value is None:
            raise ValueError(
                "verified creature block exceeds family bounds"
            )
        return value

    def reviewed_stat_block_sha256(
        self: CreatureGeometrySource,
    ) -> str:
        """Hash the ordered fields that existed in the reviewed stat corpus."""

        block = raw_block(self)
        projected = raw_object_type(
            members=tuple(
                member
                for member in block.members
                if member.key not in article_owned_fields
            )
        )
        value = ordered_hash(projected)
        if value is None:
            raise ValueError(
                "reviewed creature stat projection exceeds family bounds"
            )
        return value

    def content_path(
        self: CreatureGeometrySource,
    ) -> tuple[RawMemberStep, ...]:
        address = self.size_selection.address
        return address.target_path + address.carrier_path[:-1]

    def block_member_ordinal(self: CreatureGeometrySource) -> int:
        return self.size_selection.address.carrier_path[-1].member_ordinal

    def size_member_ordinal(self: CreatureGeometrySource) -> int:
        return (
            self.size_selection.address.selection_path[0].member_ordinal
        )

    def speed_member_ordinal(self: CreatureGeometrySource) -> int:
        return (
            self.speed_selection.address.selection_path[0].member_ordinal
        )

    def raw_size_member(
        self: CreatureGeometrySource,
    ) -> RawSourceMember:
        member = self.size_selection.raw_member
        if type(member) is not raw_member_type:
            raise ValueError(
                "verified Size member is unavailable"
            )
        return member

    def raw_speed_member(
        self: CreatureGeometrySource,
    ) -> RawSourceMember:
        member = self.speed_selection.raw_member
        if type(member) is not raw_member_type:
            raise ValueError(
                "verified Speed member is unavailable"
            )
        return member

    def raw_block(self: CreatureGeometrySource) -> RawSourceObject:
        return self.size_selection.carrier.raw_block

    def size_source_text(self: CreatureGeometrySource) -> str:
        value = self.size_selection.selected_value
        if type(value) is not str:
            raise ValueError(
                "verified Size value is unavailable"
            )
        return value

    def speed_source_text(self: CreatureGeometrySource) -> str:
        value = self.speed_selection.selected_value
        if type(value) is not str:
            raise ValueError(
                "verified Speed value is unavailable"
            )
        return value

    def serialize(self: CreatureGeometrySource) -> SerializedObject:
        validate(self)
        size_hash = ordered_hash(size_source_text(self))
        speed_hash = ordered_hash(speed_source_text(self))
        if size_hash is None or speed_hash is None:
            raise ValueError(
                "verified source fields exceed family bounds"
            )
        return {
            "sourceId": source_id(self),
            "locator": locator(self),
            "sectionId": section_id(self),
            "definitionId": definition_id(self),
            "creatureReceiptDigest": receipt_digest_value(self),
            "creatureName": creature_name(self),
            "orderedBlockSha256": ordered_block_sha256(self),
            "authorityDigest": (
                self.size_selection.receipt.authority_digest
            ),
            "contentPath": [
                {
                    "rawKey": item.raw_key,
                    "memberOrdinal": item.member_ordinal,
                }
                for item in content_path(self)
            ],
            "blockMemberOrdinal": block_member_ordinal(self),
            "sizeField": {
                "rawKey": raw_size_member(self).key,
                "memberOrdinal": size_member_ordinal(self),
                "sourceText": size_source_text(self),
                "orderedValueSha256": size_hash,
                "fieldRule": {
                    "sourceId": size_rule[0],
                    "locator": size_rule[1],
                },
                "sourceReceipt": (
                    self.size_selection.receipt.as_serialized()
                ),
            },
            "speedField": {
                "rawKey": raw_speed_member(self).key,
                "memberOrdinal": speed_member_ordinal(self),
                "sourceText": speed_source_text(self),
                "orderedValueSha256": speed_hash,
                "targetFamily": "movement-speeds",
                "parseHere": False,
                "sourceReceipt": (
                    self.speed_selection.receipt.as_serialized()
                ),
            },
        }

    return (
        ordered_hash,
        validate,
        source_id,
        locator,
        section_id,
        creature_receipt_digest,
        definition_id,
        creature_name,
        ordered_block_sha256,
        reviewed_stat_block_sha256,
        content_path,
        block_member_ordinal,
        size_member_ordinal,
        speed_member_ordinal,
        raw_size_member,
        raw_speed_member,
        raw_block,
        size_source_text,
        speed_source_text,
        serialize,
    )


(
    ordered_source_sha256,
    CreatureGeometrySource._validate,
    _source_id,
    _source_locator,
    _source_section_id,
    _creature_receipt_digest,
    _source_definition_id,
    _source_creature_name,
    _source_ordered_block_sha256,
    _source_reviewed_stat_block_sha256,
    _source_content_path,
    _source_block_member_ordinal,
    _source_size_member_ordinal,
    _source_speed_member_ordinal,
    _source_raw_size_member,
    _source_raw_speed_member,
    _source_raw_block,
    _source_size_text,
    _source_speed_text,
    CreatureGeometrySource.as_source_identity,
) = _bind_creature_geometry_source_contract(
    CreatureGeometrySource,
    SourceAuthorityAdapter,
    VerifiedSourceSelection,
    RawMemberStep,
    RawSourceMember,
    RawSourceObject,
    RawSourceArray,
)
CreatureGeometrySource.__post_init__ = CreatureGeometrySource._validate
CreatureGeometrySource.source_id = property(_source_id)
CreatureGeometrySource.locator = property(_source_locator)
CreatureGeometrySource.section_id = property(_source_section_id)
CreatureGeometrySource.creature_receipt_digest = property(
    _creature_receipt_digest
)
CreatureGeometrySource.definition_id = property(_source_definition_id)
CreatureGeometrySource.creature_name = property(_source_creature_name)
CreatureGeometrySource.ordered_block_sha256 = property(
    _source_ordered_block_sha256
)
CreatureGeometrySource.reviewed_stat_block_sha256 = property(
    _source_reviewed_stat_block_sha256
)
CreatureGeometrySource.content_path = property(_source_content_path)
CreatureGeometrySource.block_member_ordinal = property(
    _source_block_member_ordinal
)
CreatureGeometrySource.size_member_ordinal = property(
    _source_size_member_ordinal
)
CreatureGeometrySource.speed_member_ordinal = property(
    _source_speed_member_ordinal
)
CreatureGeometrySource.raw_size_member = property(
    _source_raw_size_member
)
CreatureGeometrySource.raw_speed_member = property(
    _source_raw_speed_member
)
CreatureGeometrySource.raw_block = property(_source_raw_block)
CreatureGeometrySource.size_source_text = property(_source_size_text)
CreatureGeometrySource.speed_source_text = property(_source_speed_text)
del _bind_creature_geometry_source_contract
del _source_id
del _source_locator
del _source_section_id
del _creature_receipt_digest
del _source_definition_id
del _source_creature_name
del _source_ordered_block_sha256
del _source_reviewed_stat_block_sha256
del _source_content_path
del _source_block_member_ordinal
del _source_size_member_ordinal
del _source_speed_member_ordinal
del _source_raw_size_member
del _source_raw_speed_member
del _source_raw_block
del _source_size_text
del _source_speed_text


@dataclass(frozen=True, slots=True)
class SizeSpaceReachRuleBundle:
    """Eight exact provider rules resolved by one selected-source authority."""

    authority: SourceAuthorityAdapter
    receipts: tuple[VerifiedRuleReceipt, ...]

    def __post_init__(self) -> None:
        raise RuntimeError("SizeSpaceReachRuleBundle contract is not bound")


def _bind_provider_requirement_builder():
    """Capture the reviewed provider contract as private primitives."""

    requirement_type = RuleRequirement
    reviewed = (
        (
            "creature-size",
            "core-mc1",
            "361.3",
            "c77cba38080aa70810d2113dfd61f890c"
            "a3cce5f6f77dc7adfbeaad8d43bf2d0",
        ),
        (
            "creature-traits",
            "core-mc1",
            "361.4",
            "c1a6155ad2416ead9e24782a05684a229"
            "bef7195c499a5baec5c250a3eacf0fb",
        ),
        (
            "creature-construction-size-and-traits",
            "core-gmc",
            "114.2",
            "0a94b193ad8541e980a07bb843f55450"
            "e3455c00ca0c4abe9e3f0c01a133c350",
        ),
        (
            "size-space-reach",
            "core-pc1",
            "421.8",
            "57f6c8bd51c2367bedfda5464ec295229"
            "a54363d5576a671fbda1fda3ab01fb6",
        ),
        (
            "range-reach",
            "core-pc1",
            "426.3",
            "b9db9ee1c4a6c7297ab9128a8d019e6c"
            "b7b6d2416ea376f3f8dffbf4efdb04b4",
        ),
        (
            "weapon-reach",
            "core-pc1",
            "282.1",
            "585aad382e350310ec96d4a4bd10cd364"
            "490715b2eb958aff5fdbd1e97e3e1a0",
        ),
        (
            "creature-space",
            "core-pc1",
            "422.3",
            "62ef4117bd8ca96e49011793c59b7325a"
            "f76e8c57f60291aa0f0cd7e1b07a3e0",
        ),
        (
            "different-size-space",
            "core-pc1",
            "422.5",
            "a3e2e66282827229b902c96b25d9dce3"
            "47e1366868ca66750c316552cc74f270",
        ),
    )

    def reviewed_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(
            requirement_type(
                rule_id=rule_id,
                source_id=source_id,
                locator=locator,
                expected_selection_sha256=selection_sha256,
            )
            for (
                rule_id,
                source_id,
                locator,
                selection_sha256,
            ) in reviewed
        )

    return reviewed_requirements


provider_rule_requirements = _bind_provider_requirement_builder()
del _bind_provider_requirement_builder


def _bind_rule_bundle_contract(
    bundle_type: type[SizeSpaceReachRuleBundle],
    source_type: type[CreatureGeometrySource],
    adapter_type: type[SourceAuthorityAdapter],
    receipt_type: type[VerifiedRuleReceipt],
    requirements_builder: Any,
):
    validate_selection = adapter_type.validate_selection
    require_shared = adapter_type.require_shared_authority
    resolve_rule = adapter_type.resolve_rule
    source_validate = source_type._validate
    receipt_serialize = receipt_type.as_serialized
    requirement_serialize = RuleRequirement.as_serialized

    def validate_shape(value: object) -> tuple[VerifiedRuleReceipt, ...]:
        requirements = requirements_builder()
        authority = getattr(value, "authority", None)
        receipts = getattr(value, "receipts", None)
        if (
            type(value) is not bundle_type
            or type(authority) is not adapter_type
            or type(receipts) is not tuple
            or len(receipts) != len(requirements)
            or any(
                type(receipt) is not receipt_type
                or receipt.rule_id != requirement.rule_id
                or receipt.requirement != requirement
                for receipt, requirement in zip(
                    receipts,
                    requirements,
                    strict=True,
                )
            )
        ):
            raise TypeError(
                "provider rules do not match the reviewed requirement set"
            )
        return receipts

    def post_init(self: SizeSpaceReachRuleBundle) -> None:
        validate_shape(self)

    def require_source(
        self: SizeSpaceReachRuleBundle,
        source: CreatureGeometrySource,
    ) -> None:
        receipts = validate_shape(self)
        if (
            type(source) is not source_type
            or source.authority is not self.authority
        ):
            raise TypeError(
                "source and provider rules must share one exact authority"
            )
        source_validate(source)
        require_shared(
            self.authority,
            source.size_selection,
            receipts,
        )
        validate_selection(
            self.authority,
            source.speed_selection,
        )

    def serialize(
        self: SizeSpaceReachRuleBundle,
    ) -> SerializedObject:
        receipts = validate_shape(self)
        require_shared(
            self.authority,
            receipts[0].selection,
            receipts,
        )
        return {
            "authorityDigest": self.authority.snapshot.digest,
            "rules": [
                {
                    "ruleId": item.rule_id,
                    "requirement": requirement_serialize(
                        item.requirement
                    ),
                    "source": receipt_serialize(item),
                }
                for item in receipts
            ],
        }

    def bind(
        authority: SourceAuthorityAdapter,
        /,
    ) -> SizeSpaceReachRuleBundle:
        if type(authority) is not adapter_type:
            raise TypeError(
                "bind_size_space_reach_rules requires exact authority"
            )
        receipts = tuple(
            resolve_rule(authority, requirement)
            for requirement in requirements_builder()
        )
        result = bundle_type(
            authority=authority,
            receipts=receipts,
        )
        serialize(result)
        return result

    return post_init, require_source, serialize, bind


(
    SizeSpaceReachRuleBundle.__post_init__,
    SizeSpaceReachRuleBundle.require_source,
    SizeSpaceReachRuleBundle.as_serialized,
    bind_size_space_reach_rules,
) = _bind_rule_bundle_contract(
    SizeSpaceReachRuleBundle,
    CreatureGeometrySource,
    SourceAuthorityAdapter,
    VerifiedRuleReceipt,
    provider_rule_requirements,
)
SizeSpaceReachRuleBundle._as_serialized_validated = (
    SizeSpaceReachRuleBundle.as_serialized
)
del _bind_rule_bundle_contract


@dataclass(frozen=True, slots=True)
class NaturalReachProfileBinding:
    """Pinned review decision with separate source and provider proofs."""

    authority: SourceAuthorityAdapter
    review_manifest_json: str = field(repr=False)
    block_id: str
    definition_id: str
    ordered_block_sha256: str
    creature_receipt_digest: str
    creature_source: CreatureGeometrySource
    profile: str
    evidence_kind: str
    evidence_selection: VerifiedSourceSelection
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    review_record_sha256: str
    decision_digest: str

    def __post_init__(self) -> None:
        raise RuntimeError(
            "NaturalReachProfileBinding contract is not bound"
        )


class NaturalReachProfileAmbiguityError(ValueError):
    """More than one reviewed profile targets the same exact source block."""


@dataclass(frozen=True, slots=True)
class GeometryDeferral:
    deferral_id: str
    phase: str
    subject: str
    reason: str
    rule: RuleReference

    def __post_init__(self) -> None:
        raise RuntimeError("GeometryDeferral contract is not bound")


@dataclass(frozen=True, slots=True)
class CanonicalFootprint:
    size: str
    size_rank: int
    space_text: str
    space_kind: str
    space_feet: int | None
    width_squares: int
    height_squares: int
    grid_footprint_kind: str
    extent_deferral: GeometryDeferral | None

    def __post_init__(self) -> None:
        raise RuntimeError("CanonicalFootprint contract is not bound")


@dataclass(frozen=True, slots=True)
class NaturalReachResolution:
    status: str
    tall_feet: int
    long_feet: int
    selected_profile: str | None
    resolved_feet: int | None
    binding: NaturalReachProfileBinding | None
    profile_deferral: GeometryDeferral | None

    def __post_init__(self) -> None:
        raise RuntimeError("NaturalReachResolution contract is not bound")


@dataclass(frozen=True, slots=True)
class StrikeReachResolution:
    strike_kind: str
    strike_name: str
    strike_field_ordinal: int
    strike_ordinal: int
    traits_member_ordinal: int | None
    trait_ordinal: int | None
    source_text: str | None
    resolution_kind: str
    reach_feet: int | None
    candidate_feet: int | None
    deferral: GeometryDeferral | None

    def __post_init__(self) -> None:
        raise RuntimeError("StrikeReachResolution contract is not bound")


@dataclass(frozen=True, slots=True)
class SizeSpaceReachPatch:
    source: CreatureGeometrySource
    rules: SizeSpaceReachRuleBundle
    footprint: CanonicalFootprint
    natural_reach: NaturalReachResolution
    strike_reaches: tuple[StrikeReachResolution, ...]
    deferrals: tuple[GeometryDeferral, ...]

    def __post_init__(self) -> None:
        raise RuntimeError("SizeSpaceReachPatch contract is not bound")


@dataclass(frozen=True, slots=True)
class BattlegroundGeometryProjection:
    patch: SizeSpaceReachPatch
    gargantuan_minimum_accepted: bool
    geometry_link_ready: bool
    projection_deferrals: tuple[GeometryDeferral, ...]

    def __post_init__(self) -> None:
        raise RuntimeError(
            "BattlegroundGeometryProjection contract is not bound"
        )


def _bind_canonical_derivations(
    source_type: type[CreatureGeometrySource],
    binding_type: type[NaturalReachProfileBinding],
    footprint_type: type[CanonicalFootprint],
    natural_type: type[NaturalReachResolution],
    strike_type: type[StrikeReachResolution],
    deferral_type: type[GeometryDeferral],
    raw_object_type: type[RawSourceObject],
    raw_array_type: type[RawSourceArray],
    rule_type: type[RuleReference],
):
    """Capture PF2ER geometry semantics as private, fresh literals."""

    sizes = (
        "Tiny",
        "Small",
        "Medium",
        "Large",
        "Huge",
        "Gargantuan",
    )
    size_specs = (
        ("Tiny", (
            0,
            "Less than 5 feet",
            "less-than",
            None,
            1,
            1,
            "canonical-cell-proxy",
            0,
            0,
        )),
        ("Small", (
            1,
            "5 feet",
            "exact",
            5,
            1,
            1,
            "exact",
            5,
            5,
        )),
        ("Medium", (
            2,
            "5 feet",
            "exact",
            5,
            1,
            1,
            "exact",
            5,
            5,
        )),
        ("Large", (
            3,
            "10 feet",
            "exact",
            10,
            2,
            2,
            "exact",
            10,
            5,
        )),
        ("Huge", (
            4,
            "15 feet",
            "exact",
            15,
            3,
            3,
            "exact",
            15,
            10,
        )),
        ("Gargantuan", (
            5,
            "20 feet or more",
            "minimum",
            20,
            4,
            4,
            "canonical-minimum",
            20,
            15,
        )),
    )
    size_space_rule = ("core-pc1", "421.8")
    range_reach_rule = ("core-pc1", "426.3")
    weapon_reach_rule = ("core-pc1", "282.1")
    creature_space_rule = ("core-pc1", "422.3")
    numeric_reach = re.compile(
        r"^reach (?P<feet>[0-9]+) feet$",
        re.ASCII | re.IGNORECASE,
    )
    maximum_integer = (1 << 63) - 1
    maximum_strikes = 128
    maximum_traits = 64
    maximum_trait_bytes = 256
    maximum_strike_name_bytes = 256

    def new_rule(spec: tuple[str, str]) -> RuleReference:
        return rule_type(spec[0], spec[1])

    def rule_matches(value: object, spec: tuple[str, str]) -> bool:
        return (
            type(value) is rule_type
            and value.source_id == spec[0]
            and value.locator == spec[1]
        )

    def serialize_rule(spec: tuple[str, str]) -> SerializedObject:
        return {
            "sourceId": spec[0],
            "locator": spec[1],
        }

    def footprint_spec(
        size: str,
    ) -> tuple[object, ...]:
        if type(size) is not str or size not in sizes:
            raise ValueError("canonical Size is invalid")
        return next(
            spec
            for candidate, spec in size_specs
            if candidate == size
        )

    def extent_deferral(size: str) -> GeometryDeferral | None:
        if size != "Gargantuan":
            return None
        return deferral_type(
            deferral_id="gargantuan-exact-extent",
            phase="scenario",
            subject="footprint",
            reason=(
                "canonical Size supplies a 20-foot minimum, not an exact "
                "extent"
            ),
            rule=new_rule(size_space_rule),
        )

    def canonical_footprint(size: str) -> CanonicalFootprint:
        (
            rank,
            space_text,
            space_kind,
            space_feet,
            width,
            height,
            grid_kind,
            _tall,
            _long,
        ) = footprint_spec(size)
        return footprint_type(
            size=size,
            size_rank=rank,
            space_text=space_text,
            space_kind=space_kind,
            space_feet=space_feet,
            width_squares=width,
            height_squares=height,
            grid_footprint_kind=grid_kind,
            extent_deferral=extent_deferral(size),
        )

    def natural_reach(
        source: CreatureGeometrySource,
        size: str,
        binding: NaturalReachProfileBinding | None,
    ) -> NaturalReachResolution:
        if type(source) is not source_type:
            raise TypeError("natural reach source is invalid")
        spec = footprint_spec(size)
        tall = spec[7]
        long = spec[8]
        if tall == long:
            if binding is not None:
                raise ValueError(
                    "Size already makes tall/long natural reach invariant"
                )
            return natural_type(
                status="resolved-size-invariant",
                tall_feet=tall,
                long_feet=long,
                selected_profile=None,
                resolved_feet=tall,
                binding=None,
                profile_deferral=None,
            )
        if binding is not None:
            if type(binding) is not binding_type:
                raise TypeError("natural reach binding is invalid")
            return natural_type(
                status="resolved-reviewed-profile",
                tall_feet=tall,
                long_feet=long,
                selected_profile=binding.profile,
                resolved_feet=(
                    tall if binding.profile == "tall" else long
                ),
                binding=binding,
                profile_deferral=None,
            )
        return natural_type(
            status="deferred-profile",
            tall_feet=tall,
            long_feet=long,
            selected_profile=None,
            resolved_feet=None,
            binding=None,
            profile_deferral=deferral_type(
                deferral_id="natural-reach-profile",
                phase="link",
                subject=source.definition_id,
                reason=(
                    "Large-or-larger tall/long profile has no hash-bound "
                    "source-backed decision"
                ),
                rule=new_rule(size_space_rule),
            ),
        )

    def exact_member_indices(
        value: RawSourceObject,
        key: str,
    ) -> tuple[int, ...] | None:
        if type(value) is not raw_object_type or type(key) is not str:
            return None
        stripped = tuple(
            index
            for index, member in enumerate(value.members)
            if member.key.strip() == key
        )
        exact = tuple(
            index
            for index in stripped
            if value.members[index].key == key
        )
        if len(stripped) != len(exact):
            return None
        return exact

    def parse_integer(value: str) -> int | None:
        if (
            type(value) is not str
            or not value
            or any(character < "0" or character > "9" for character in value)
            or len(value) > len(str(maximum_integer))
            or (
                len(value) == len(str(maximum_integer))
                and value > str(maximum_integer)
            )
        ):
            return None
        return int(value)

    def strike_reach_facts(
        source: CreatureGeometrySource,
        natural: NaturalReachResolution,
    ) -> tuple[StrikeReachResolution, ...] | None:
        if (
            type(source) is not source_type
            or type(natural) is not natural_type
        ):
            return None
        result: list[StrikeReachResolution] = []
        for kind_key, kind in (
            ("Melee", "melee"),
            ("Ranged", "ranged"),
        ):
            member_indices = exact_member_indices(
                source.raw_block,
                kind_key,
            )
            if member_indices is None or len(member_indices) > 1:
                return None
            if not member_indices:
                continue
            field_ordinal = member_indices[0]
            field_value = source.raw_block.members[
                field_ordinal
            ].value
            if (
                type(field_value) is not raw_array_type
                or len(field_value.items) > maximum_strikes
            ):
                return None

            for strike_ordinal, strike in enumerate(field_value.items):
                if type(strike) is not raw_object_type:
                    return None
                name_indices = exact_member_indices(strike, "Name")
                if name_indices is None or len(name_indices) != 1:
                    return None
                strike_name = strike.members[name_indices[0]].value
                if (
                    type(strike_name) is not str
                    or not strike_name
                    or strike_name != strike_name.strip()
                    or len(strike_name.encode("utf-8"))
                    > maximum_strike_name_bytes
                ):
                    return None

                trait_indices = exact_member_indices(strike, "Traits")
                if trait_indices is None or len(trait_indices) > 1:
                    return None
                traits_member_ordinal: int | None = None
                traits: tuple[str, ...] = ()
                if trait_indices:
                    traits_member_ordinal = trait_indices[0]
                    raw_traits = strike.members[
                        traits_member_ordinal
                    ].value
                    if (
                        type(raw_traits) is not raw_array_type
                        or len(raw_traits.items) > maximum_traits
                        or any(
                            type(item) is not str
                            or not item
                            or item != item.strip()
                            or len(item.encode("utf-8"))
                            > maximum_trait_bytes
                            for item in raw_traits.items
                        )
                    ):
                        return None
                    traits = raw_traits.items

                reach_traits: list[
                    tuple[int, str, int | None, str]
                ] = []
                for trait_ordinal, trait in enumerate(traits):
                    numeric = numeric_reach.fullmatch(trait)
                    if numeric is not None:
                        feet = parse_integer(numeric.group("feet"))
                        if (
                            feet is None
                            or feet < 0
                            or feet % 5
                        ):
                            return None
                        reach_traits.append(
                            (
                                trait_ordinal,
                                trait,
                                feet,
                                "explicit-trait",
                            )
                        )
                    elif trait.casefold() == "reach":
                        reach_traits.append(
                            (
                                trait_ordinal,
                                trait,
                                None,
                                "bare-weapon-trait",
                            )
                        )
                    elif trait.casefold().startswith("reach"):
                        return None
                if len(reach_traits) > 1:
                    return None
                if kind == "ranged" and reach_traits:
                    return None

                if kind == "ranged":
                    result.append(
                        strike_type(
                            strike_kind=kind,
                            strike_name=strike_name,
                            strike_field_ordinal=field_ordinal,
                            strike_ordinal=strike_ordinal,
                            traits_member_ordinal=(
                                traits_member_ordinal
                            ),
                            trait_ordinal=None,
                            source_text=None,
                            resolution_kind="not-applicable-ranged",
                            reach_feet=None,
                            candidate_feet=None,
                            deferral=None,
                        )
                    )
                    continue

                if reach_traits:
                    (
                        trait_ordinal,
                        source_text,
                        feet,
                        reach_kind,
                    ) = reach_traits[0]
                    if reach_kind == "explicit-trait":
                        result.append(
                            strike_type(
                                strike_kind=kind,
                                strike_name=strike_name,
                                strike_field_ordinal=field_ordinal,
                                strike_ordinal=strike_ordinal,
                                traits_member_ordinal=(
                                    traits_member_ordinal
                                ),
                                trait_ordinal=trait_ordinal,
                                source_text=source_text,
                                resolution_kind=reach_kind,
                                reach_feet=feet,
                                candidate_feet=feet,
                                deferral=None,
                            )
                        )
                    else:
                        candidate = (
                            natural.resolved_feet + 5
                            if natural.resolved_feet is not None
                            else None
                        )
                        result.append(
                            strike_type(
                                strike_kind=kind,
                                strike_name=strike_name,
                                strike_field_ordinal=field_ordinal,
                                strike_ordinal=strike_ordinal,
                                traits_member_ordinal=(
                                    traits_member_ordinal
                                ),
                                trait_ordinal=trait_ordinal,
                                source_text=source_text,
                                resolution_kind=reach_kind,
                                reach_feet=None,
                                candidate_feet=candidate,
                                deferral=deferral_type(
                                    deferral_id=(
                                        "canonical-weapon-reach-binding"
                                    ),
                                    phase="link",
                                    subject=(
                                        f"{source.definition_id}:"
                                        f"{kind_key}:{strike_ordinal}"
                                    ),
                                    reason=(
                                        "bare reach must bind the canonical "
                                        "weapon trait before adding 5 feet"
                                    ),
                                    rule=new_rule(weapon_reach_rule),
                                ),
                            )
                        )
                    continue

                natural_deferral = (
                    deferral_type(
                        deferral_id="natural-reach-profile",
                        phase="link",
                        subject=(
                            f"{source.definition_id}:{kind_key}:"
                            f"{strike_ordinal}"
                        ),
                        reason=(
                            "implicit Melee reach depends on unresolved "
                            "whole-creature profile"
                        ),
                        rule=new_rule(size_space_rule),
                    )
                    if natural.resolved_feet is None
                    else None
                )
                result.append(
                    strike_type(
                        strike_kind=kind,
                        strike_name=strike_name,
                        strike_field_ordinal=field_ordinal,
                        strike_ordinal=strike_ordinal,
                        traits_member_ordinal=traits_member_ordinal,
                        trait_ordinal=None,
                        source_text=None,
                        resolution_kind="natural-reach",
                        reach_feet=natural.resolved_feet,
                        candidate_feet=natural.resolved_feet,
                        deferral=natural_deferral,
                    )
                )
        return tuple(result)

    def aggregate_deferrals(
        source: CreatureGeometrySource,
        footprint: CanonicalFootprint,
        natural: NaturalReachResolution,
        strike_reaches: tuple[StrikeReachResolution, ...],
    ) -> tuple[GeometryDeferral, ...]:
        result = [
            deferral_type(
                deferral_id="movement-speed-link",
                phase="link",
                subject=source.definition_id,
                reason=(
                    "exact Speed source is preserved for the "
                    "movement-speeds compiler and is not parsed by geometry"
                ),
                rule=new_rule(size_space_rule),
            ),
            deferral_type(
                deferral_id="spatial-runtime-integration",
                phase="runtime",
                subject="creature-geometry",
                reason=(
                    "compiled geometry is not activated in placement, "
                    "movement, adjacency, reactions, or encounter state"
                ),
                rule=new_rule(size_space_rule),
            ),
        ]
        if footprint.extent_deferral is not None:
            result.append(footprint.extent_deferral)
        if natural.profile_deferral is not None:
            result.append(natural.profile_deferral)
        result.extend(
            item.deferral
            for item in strike_reaches
            if (
                item.resolution_kind == "bare-weapon-trait"
                and item.deferral is not None
            )
        )
        return tuple(result)

    def projection_deferrals(
        patch: SizeSpaceReachPatch,
        accept_gargantuan_minimum: bool,
    ) -> tuple[GeometryDeferral, ...]:
        is_gargantuan = patch.footprint.size == "Gargantuan"
        result: list[GeometryDeferral | None] = []
        if patch.natural_reach.resolved_feet is None:
            result.append(patch.natural_reach.profile_deferral)
        if is_gargantuan and not accept_gargantuan_minimum:
            result.append(patch.footprint.extent_deferral)
        result.extend(
            (
                deferral_type(
                    deferral_id="placement-runtime",
                    phase="runtime",
                    subject="whole-footprint-placement",
                    reason=(
                        "map bounds, blocked squares, and occupancy need "
                        "current battleground state"
                    ),
                    rule=new_rule(size_space_rule),
                ),
                deferral_type(
                    deferral_id="transit-runtime",
                    phase="runtime",
                    subject="movement-transit-and-endpoint",
                    reason=(
                        "willing transit, size-rank transit, and endpoints "
                        "are separate current-state policies"
                    ),
                    rule=new_rule(creature_space_rule),
                ),
                deferral_type(
                    deferral_id="adjacency-runtime",
                    phase="runtime",
                    subject="minimum-footprint-separation",
                    reason=(
                        "adjacency and reach require current positions and "
                        "the 10-foot diagonal special case"
                    ),
                    rule=new_rule(range_reach_rule),
                ),
            )
        )
        return tuple(item for item in result if item is not None)

    return (
        sizes,
        footprint_spec,
        rule_matches,
        serialize_rule,
        extent_deferral,
        canonical_footprint,
        natural_reach,
        exact_member_indices,
        strike_reach_facts,
        aggregate_deferrals,
        projection_deferrals,
    )


(
    _CANONICAL_SIZES,
    _canonical_footprint_spec,
    _canonical_rule_matches,
    _canonical_rule_serialized,
    _extent_deferral,
    _canonical_footprint,
    _natural_reach,
    _exact_member_indices,
    _strike_reach_facts,
    _aggregate_deferrals,
    _projection_deferrals_bound,
) = _bind_canonical_derivations(
    CreatureGeometrySource,
    NaturalReachProfileBinding,
    CanonicalFootprint,
    NaturalReachResolution,
    StrikeReachResolution,
    GeometryDeferral,
    RawSourceObject,
    RawSourceArray,
    RuleReference,
)
del _bind_canonical_derivations


def _bind_profile_review_contract(
    binding_type: type[NaturalReachProfileBinding],
    source_type: type[CreatureGeometrySource],
    rules_type: type[SizeSpaceReachRuleBundle],
    selection_type: type[VerifiedSourceSelection],
    receipt_type: type[VerifiedRuleReceipt],
    adapter_type: type[SourceAuthorityAdapter],
    raw_array_type: type[RawSourceArray],
    raw_member_type: type[RawSourceMember],
    member_step_type: type[RawMemberStep],
    requirements_builder: Any,
    footprint_spec: Any,
    canonical_json: Any,
    catalog_manifest_json: str,
    catalog_manifest_sha256: str,
    catalog_record: Any,
    catalog_for_source: Any,
    catalog_for_block_id: Any,
):
    """Capture both exact reviewed morphology contracts."""

    schema = 1
    reviewer = "kmqdb:core-mc1-size-space-reach-foundation"
    manifest_sha256 = (
        "321b394378af8b3a4265916fc944271387f952bab3ee6c24ae804e3b6b7fe9b0"
    )
    artifact = "core-mc1-reviewed-profile-overlays"
    overlay_count = 46
    maximum_manifest_bytes = 262_144
    maximum_identifier_bytes = 4_096
    profiles = ("tall", "long")
    evidence_kinds = (
        "exact-creature-block-plus-reviewed-morphology",
        "whole-creature-prose",
        "authored-traits-plus-canonical-default",
    )
    catalog_schema = 2
    catalog_reviewer = "kmqdb:core-mc1-first-gate-geometry"
    catalog_artifact = "core-mc1-first-gate-geometry-review"
    catalog_record_count = 155
    catalog_evidence_kind = (
        "exact-creature-block-plus-reviewed-morphology"
    )
    sha256 = hashlib.sha256
    json_loads = json.loads
    source_validate = source_type._validate
    source_serialize = source_type.as_source_identity
    validate_selection = adapter_type.validate_selection
    validate_rule = adapter_type.validate_rule
    require_shared = adapter_type.require_shared_authority
    rules_serialize = rules_type.as_serialized
    receipt_serialize = receipt_type.as_serialized
    requirement_serialize = RuleRequirement.as_serialized

    def require_text(value: object, label: str) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or len(value.encode("utf-8")) > maximum_identifier_bytes
        ):
            raise ValueError(
                f"{label} must be a bounded non-empty trimmed string"
            )
        return value

    def require_sha(value: object, label: str) -> str:
        if (
            type(value) is not str
            or len(value) != 64
            or any(
                character not in "0123456789abcdef"
                for character in value
            )
        ):
            raise ValueError(f"{label} must be a lowercase SHA-256")
        return value

    def prose(record: dict[str, Any]) -> tuple[str, str]:
        if "paragraph" in record:
            paragraph = record.get("paragraph")
            section_id = record.get("sectionId")
        else:
            prior = record.get("priorReview")
            if type(prior) is not dict:
                raise ValueError("reviewed prose evidence is missing")
            paragraph = prior.get("text")
            section_id = prior.get("sectionId")
        if type(paragraph) is not str or type(section_id) is not str:
            raise ValueError(
                "reviewed prose evidence fields are invalid"
            )
        return paragraph, section_id

    def post_init(self: NaturalReachProfileBinding) -> None:
        authority = getattr(self, "authority", None)
        manifest = getattr(self, "review_manifest_json", None)
        creature = getattr(self, "creature_source", None)
        evidence = getattr(self, "evidence_selection", None)
        providers = getattr(self, "provider_rules", None)
        if (
            type(self) is not binding_type
            or type(authority) is not adapter_type
            or type(manifest) is not str
            or len(manifest.encode("utf-8"))
            > maximum_manifest_bytes
            or type(creature) is not source_type
            or type(evidence) is not selection_type
            or type(providers) is not tuple
            or not providers
            or any(type(item) is not receipt_type for item in providers)
        ):
            raise TypeError("profile-review claim fields are invalid")
        for field_name in ("block_id", "definition_id"):
            require_text(
                getattr(self, field_name, None),
                f"NaturalReachProfileBinding.{field_name}",
            )
        for field_name in (
            "ordered_block_sha256",
            "creature_receipt_digest",
            "review_record_sha256",
            "decision_digest",
        ):
            require_sha(
                getattr(self, field_name, None),
                f"NaturalReachProfileBinding.{field_name}",
            )
        if getattr(self, "profile", None) not in profiles:
            raise ValueError("profile review must be tall or long")
        if getattr(self, "evidence_kind", None) not in evidence_kinds:
            raise ValueError(
                "profile review evidence kind is invalid"
            )

    def catalog_providers(
        rules: SizeSpaceReachRuleBundle,
    ) -> tuple[VerifiedRuleReceipt, ...]:
        if type(rules) is not rules_type:
            raise TypeError(
                "profile review requires verified provider rules"
            )
        rules_serialize(rules)
        index = {item.rule_id: item for item in rules.receipts}
        expected = (
            "creature-construction-size-and-traits",
            "size-space-reach",
        )
        if (
            len(index) != len(rules.receipts)
            or any(rule_id not in index for rule_id in expected)
        ):
            raise ValueError(
                "profile provider-rule bundle is incomplete"
            )
        return tuple(index[rule_id] for rule_id in expected)

    def catalog_decision(
        source: CreatureGeometrySource,
        row: tuple[object, ...],
        evidence: VerifiedSourceSelection,
        providers: tuple[VerifiedRuleReceipt, ...],
    ) -> tuple[str, str]:
        overlay = catalog_record(row)
        record_sha256 = sha256(
            canonical_json(overlay)
        ).hexdigest()
        decision_payload = {
            "schema": catalog_schema,
            "reviewer": catalog_reviewer,
            "manifestSha256": catalog_manifest_sha256,
            "recordSha256": record_sha256,
            "blockId": overlay["blockId"],
            "creatureReceiptDigest": source.creature_receipt_digest,
            "profile": overlay["profile"],
            "evidenceReceiptDigest": evidence.receipt.digest,
            "providerRuleReceiptDigests": [
                item.receipt.digest for item in providers
            ],
        }
        return (
            record_sha256,
            sha256(canonical_json(decision_payload)).hexdigest(),
        )

    def validate_catalog(
        self: NaturalReachProfileBinding,
        source: CreatureGeometrySource | None,
    ) -> dict[str, Any]:
        if (
            self.review_manifest_json != catalog_manifest_json
            or sha256(
                self.review_manifest_json.encode("utf-8")
            ).hexdigest()
            != catalog_manifest_sha256
        ):
            raise ValueError(
                "profile review manifest is not the pinned artifact"
            )
        parsed = json_loads(self.review_manifest_json)
        if (
            type(parsed) is not dict
            or parsed.get("schema") != catalog_schema
            or parsed.get("reviewer") != catalog_reviewer
            or parsed.get("artifact") != catalog_artifact
            or parsed.get("recordCount") != catalog_record_count
            or type(parsed.get("records")) is not list
            or len(parsed["records"]) != catalog_record_count
        ):
            raise ValueError(
                "profile review manifest schema is invalid"
            )
        row = catalog_for_block_id(self.block_id)
        if row is None:
            raise ValueError("profile review record is not unique")
        overlay = catalog_record(row)
        if sum(
            type(item) is dict
            and item.get("blockId") == self.block_id
            for item in parsed["records"]
        ) != 1 or overlay not in parsed["records"]:
            raise ValueError("profile review record is not unique")

        creature = self.creature_source
        if (
            creature.authority is not self.authority
            or catalog_for_source(creature) != row
            or (
                source is not None
                and (
                    type(source) is not source_type
                    or source.authority is not self.authority
                    or source.size_selection.receipt.digest
                    != creature.size_selection.receipt.digest
                    or source.speed_selection.receipt.digest
                    != creature.speed_selection.receipt.digest
                )
            )
        ):
            raise TypeError(
                "profile review and creature must share exact authority"
            )
        source_validate(creature)
        if source is not None:
            source_validate(source)
        evidence = validate_selection(
            self.authority,
            self.evidence_selection,
        )
        require_shared(
            self.authority,
            evidence,
            self.provider_rules,
        )
        for receipt in self.provider_rules:
            validate_rule(self.authority, receipt)
        requirement_index = {
            item.rule_id: item for item in requirements_builder()
        }
        expected_requirements = tuple(
            requirement_index[rule_id]
            for rule_id in (
                "creature-construction-size-and-traits",
                "size-space-reach",
            )
        )
        if (
            self.definition_id != creature.definition_id
            or self.ordered_block_sha256
            != creature.ordered_block_sha256
            or self.creature_receipt_digest
            != creature.creature_receipt_digest
            or self.profile != overlay["profile"]
            or self.evidence_kind != catalog_evidence_kind
            or evidence.receipt.digest
            != creature.size_selection.receipt.digest
            or evidence.block_sha256
            != creature.size_selection.block_sha256
            or tuple(
                item.requirement for item in self.provider_rules
            )
            != expected_requirements
        ):
            raise ValueError(
                "profile review creature proof disagrees"
            )
        size_spec = footprint_spec(creature.size_source_text)
        expected_reach = (
            size_spec[7] if self.profile == "tall" else size_spec[8]
        )
        if overlay["naturalReachFeet"] != expected_reach:
            raise ValueError(
                "profile review reach decision disagrees"
            )
        record_sha256, decision_digest = catalog_decision(
            creature,
            row,
            evidence,
            self.provider_rules,
        )
        if (
            self.review_record_sha256 != record_sha256
            or self.decision_digest != decision_digest
        ):
            raise ValueError(
                "profile review decision digest disagrees"
            )
        return overlay

    def validate(
        self: NaturalReachProfileBinding,
        source: CreatureGeometrySource | None = None,
    ) -> dict[str, Any]:
        post_init(self)
        if self.evidence_kind == catalog_evidence_kind:
            return validate_catalog(self, source)
        encoded = self.review_manifest_json.encode("utf-8")
        if sha256(encoded).hexdigest() != manifest_sha256:
            raise ValueError(
                "profile review manifest is not the pinned artifact"
            )
        parsed = json_loads(self.review_manifest_json)
        if (
            type(parsed) is not dict
            or parsed.get("schema") != schema
            or parsed.get("artifact") != artifact
            or parsed.get("overlayCount") != overlay_count
            or type(parsed.get("overlays")) is not list
            or len(parsed["overlays"]) != overlay_count
        ):
            raise ValueError(
                "profile review manifest schema is invalid"
            )
        overlays = tuple(
            item
            for item in parsed["overlays"]
            if type(item) is dict
            and item.get("blockId") == self.block_id
        )
        if len(overlays) != 1:
            raise ValueError(
                "profile review record is not unique"
            )
        overlay = overlays[0]

        creature = self.creature_source
        if (
            creature.authority is not self.authority
            or (
                source is not None
                and (
                    type(source) is not source_type
                    or source.authority is not self.authority
                    or source.size_selection.receipt.digest
                    != creature.size_selection.receipt.digest
                    or source.speed_selection.receipt.digest
                    != creature.speed_selection.receipt.digest
                )
            )
        ):
            raise TypeError(
                "profile review and creature must share exact authority"
            )
        source_validate(creature)
        if source is not None:
            source_validate(source)
        evidence = validate_selection(
            self.authority,
            self.evidence_selection,
        )
        require_shared(
            self.authority,
            evidence,
            self.provider_rules,
        )
        if (
            self.definition_id != creature.definition_id
            or self.ordered_block_sha256
            != creature.ordered_block_sha256
            or self.creature_receipt_digest
            != creature.creature_receipt_digest
            or overlay.get("sourceId") != creature.source_id
            or overlay.get("locator") != creature.locator
            or overlay.get("name") != creature.creature_name
            or overlay.get("authoredSize")
            != creature.size_source_text
            or overlay.get("orderedBlockSha256")
            != creature.ordered_block_sha256
            or overlay.get("profile") != self.profile
        ):
            raise ValueError(
                "profile review creature proof disagrees"
            )
        size_spec = footprint_spec(creature.size_source_text)
        expected_reach = (
            size_spec[7] if self.profile == "tall" else size_spec[8]
        )
        if overlay.get("naturalReachFeet") != expected_reach:
            raise ValueError(
                "profile review reach decision disagrees"
            )

        evidence_record = overlay.get("evidence")
        if (
            type(evidence_record) is not dict
            or evidence_record.get("kind") != self.evidence_kind
        ):
            raise ValueError(
                "profile review evidence record is invalid"
            )
        requirement_index = {
            item.rule_id: item
            for item in requirements_builder()
        }
        if self.evidence_kind == "whole-creature-prose":
            paragraph, section_id = prose(evidence_record)
            expected_requirements = (
                requirement_index["size-space-reach"],
            )
            if (
                type(evidence.selected_value) is not str
                or evidence.selected_value != paragraph
                or evidence.address.source_id != creature.source_id
                or evidence.address.section_id != section_id
                or (
                    evidence_record.get("paragraphSha256") is not None
                    and evidence_record.get("paragraphSha256")
                    != evidence.selection_sha256
                )
            ):
                raise ValueError(
                    "profile prose receipt disagrees"
                )
        else:
            authored_traits = evidence_record.get("authoredTraits")
            expected_requirements = (
                requirement_index["creature-traits"],
                requirement_index["size-space-reach"],
            )
            if (
                type(authored_traits) is not list
                or any(type(item) is not str for item in authored_traits)
                or type(evidence.selected_value) is not raw_array_type
                or evidence.selected_value.items
                != tuple(authored_traits)
                or len(evidence.address.selection_path) != 1
                or type(evidence.address.selection_path[0])
                is not member_step_type
                or evidence.address.selection_path[0].raw_key
                != "Traits"
                or type(evidence.raw_member) is not raw_member_type
                or evidence.raw_member.key != "Traits"
                or evidence.block_sha256
                != creature.size_selection.block_sha256
                or evidence.address.target_path
                != creature.size_selection.address.target_path
                or evidence.address.carrier_path
                != creature.size_selection.address.carrier_path
            ):
                raise ValueError(
                    "profile trait receipt disagrees"
                )
        if tuple(
            item.requirement for item in self.provider_rules
        ) != expected_requirements:
            raise ValueError(
                "profile provider rules disagree with reviewed evidence"
            )

        record_sha256 = sha256(
            canonical_json(overlay)
        ).hexdigest()
        decision_payload = {
            "schema": schema,
            "reviewer": reviewer,
            "manifestSha256": manifest_sha256,
            "recordSha256": record_sha256,
            "blockId": self.block_id,
            "creatureReceiptDigest": creature.creature_receipt_digest,
            "profile": self.profile,
            "evidenceReceiptDigest": evidence.receipt.digest,
            "providerRuleReceiptDigests": [
                item.receipt.digest for item in self.provider_rules
            ],
        }
        decision_digest = sha256(
            canonical_json(decision_payload)
        ).hexdigest()
        if (
            self.review_record_sha256 != record_sha256
            or self.decision_digest != decision_digest
        ):
            raise ValueError(
                "profile review decision digest disagrees"
            )
        return overlay

    def catalog_binding(
        source: CreatureGeometrySource,
        rules: SizeSpaceReachRuleBundle,
    ) -> NaturalReachProfileBinding | None:
        if type(source) is not source_type:
            raise TypeError("profile review source is invalid")
        if type(rules) is not rules_type:
            raise TypeError(
                "profile review requires verified provider rules"
            )
        rules.require_source(source)
        row = catalog_for_source(source)
        if row is None:
            return None
        overlay = catalog_record(row)
        evidence = validate_selection(
            source.authority,
            source.size_selection,
        )
        providers = catalog_providers(rules)
        record_sha256, decision_digest = catalog_decision(
            source,
            row,
            evidence,
            providers,
        )
        result = binding_type(
            authority=source.authority,
            review_manifest_json=catalog_manifest_json,
            block_id=overlay["blockId"],
            definition_id=source.definition_id,
            ordered_block_sha256=source.ordered_block_sha256,
            creature_receipt_digest=source.creature_receipt_digest,
            creature_source=source,
            profile=overlay["profile"],
            evidence_kind=catalog_evidence_kind,
            evidence_selection=evidence,
            provider_rules=providers,
            review_record_sha256=record_sha256,
            decision_digest=decision_digest,
        )
        validate_catalog(result, source)
        return result

    def serialize(
        self: NaturalReachProfileBinding,
    ) -> SerializedObject:
        validate(self)
        is_catalog = self.evidence_kind == catalog_evidence_kind
        return {
            "creatureSource": source_serialize(self.creature_source),
            "definitionId": self.definition_id,
            "orderedBlockSha256": self.ordered_block_sha256,
            "profile": self.profile,
            "review": {
                "schema": catalog_schema if is_catalog else schema,
                "reviewer": (
                    catalog_reviewer if is_catalog else reviewer
                ),
                "manifestSha256": (
                    catalog_manifest_sha256
                    if is_catalog
                    else manifest_sha256
                ),
                "recordSha256": self.review_record_sha256,
                "decisionDigest": self.decision_digest,
                "blockId": self.block_id,
                "creatureReceiptDigest": (
                    self.creature_receipt_digest
                ),
            },
            "evidence": {
                "kind": self.evidence_kind,
                "sourceReceipt": (
                    self.evidence_selection.receipt.as_serialized()
                ),
            },
            "providerRules": [
                {
                    "ruleId": item.rule_id,
                    "requirement": requirement_serialize(
                        item.requirement
                    ),
                    "source": receipt_serialize(item),
                }
                for item in self.provider_rules
            ],
        }

    def load(
        exact_manifest_json: str,
        *,
        sources_by_block_id: dict[str, CreatureGeometrySource],
        evidence_by_block_id: dict[str, VerifiedSourceSelection],
        rules: SizeSpaceReachRuleBundle,
    ) -> tuple[NaturalReachProfileBinding, ...]:
        if type(exact_manifest_json) is not str:
            raise TypeError(
                "profile review manifest must be exact JSON text"
            )
        encoded = exact_manifest_json.encode("utf-8")
        if len(encoded) > maximum_manifest_bytes:
            raise ValueError(
                "profile review manifest exceeds its byte bound"
            )
        if exact_manifest_json == catalog_manifest_json:
            if sha256(encoded).hexdigest() != catalog_manifest_sha256:
                raise ValueError(
                    "profile review manifest is not the pinned artifact"
                )
            if type(sources_by_block_id) is not dict:
                raise TypeError(
                    "profile review sources must be an exact dict"
                )
            if type(evidence_by_block_id) is not dict:
                raise TypeError(
                    "profile review evidence must be an exact dict"
                )
            if type(rules) is not rules_type:
                raise TypeError(
                    "profile review requires verified provider rules"
                )
            rules_serialize(rules)
            parsed_catalog = json_loads(exact_manifest_json)
            records = (
                parsed_catalog.get("records")
                if type(parsed_catalog) is dict
                else None
            )
            block_ids = tuple(
                item.get("blockId")
                if type(item) is dict
                else None
                for item in (records if type(records) is list else ())
            )
            if (
                type(parsed_catalog) is not dict
                or parsed_catalog.get("schema") != catalog_schema
                or parsed_catalog.get("artifact") != catalog_artifact
                or parsed_catalog.get("reviewer") != catalog_reviewer
                or parsed_catalog.get("recordCount")
                != catalog_record_count
                or type(records) is not list
                or len(records) != catalog_record_count
                or any(type(item) is not str for item in block_ids)
                or len(set(block_ids)) != len(block_ids)
                or frozenset(sources_by_block_id)
                != frozenset(block_ids)
                or frozenset(evidence_by_block_id)
                != frozenset(block_ids)
            ):
                raise ValueError(
                    "profile review block bindings are incomplete"
                )
            result = []
            for block_id in block_ids:
                source = sources_by_block_id[block_id]
                evidence = evidence_by_block_id[block_id]
                if (
                    type(source) is not source_type
                    or type(evidence) is not selection_type
                ):
                    raise TypeError(
                        "profile review source or evidence is invalid"
                    )
                source_validate(source)
                validated_evidence = validate_selection(
                    source.authority,
                    evidence,
                )
                if (
                    validated_evidence.receipt.digest
                    != source.size_selection.receipt.digest
                ):
                    raise ValueError(
                        "profile review evidence disagrees with Size"
                    )
                binding = catalog_binding(source, rules)
                if binding is None or binding.block_id != block_id:
                    raise ValueError(
                        "profile review source catalog disagrees"
                    )
                result.append(binding)
            return tuple(result)
        if sha256(encoded).hexdigest() != manifest_sha256:
            raise ValueError(
                "profile review manifest is not the pinned artifact"
            )
        if type(sources_by_block_id) is not dict:
            raise TypeError(
                "profile review sources must be an exact dict"
            )
        if type(evidence_by_block_id) is not dict:
            raise TypeError(
                "profile review evidence must be an exact dict"
            )
        if type(rules) is not rules_type:
            raise TypeError(
                "profile review requires verified provider rules"
            )
        rules_serialize(rules)

        parsed = json_loads(exact_manifest_json)
        if (
            type(parsed) is not dict
            or parsed.get("schema") != schema
            or parsed.get("artifact") != artifact
            or parsed.get("overlayCount") != overlay_count
            or type(parsed.get("overlays")) is not list
            or len(parsed["overlays"]) != overlay_count
        ):
            raise ValueError(
                "profile review manifest schema is invalid"
            )
        overlays = parsed["overlays"]
        block_ids = tuple(
            item.get("blockId") if type(item) is dict else None
            for item in overlays
        )
        if (
            any(type(item) is not str for item in block_ids)
            or len(set(block_ids)) != len(block_ids)
            or frozenset(evidence_by_block_id)
            != frozenset(block_ids)
            or any(
                block_id not in sources_by_block_id
                for block_id in block_ids
            )
        ):
            raise ValueError(
                "profile review block bindings are incomplete"
            )

        requirements = requirements_builder()
        expected_by_location = {
            (item.source_id, item.locator): item
            for item in requirements
        }
        provider_index: dict[
            tuple[str, str],
            VerifiedRuleReceipt,
        ] = {}
        for receipt in rules.receipts:
            address = receipt.selection.address
            key = (address.source_id, address.locator)
            if key in provider_index:
                raise ValueError(
                    "provider-rule bundle contains duplicates"
                )
            provider_index[key] = receipt
        if frozenset(provider_index) != frozenset(
            expected_by_location
        ):
            raise ValueError(
                "provider-rule bundle is incomplete"
            )
        table_rule = provider_index[("core-pc1", "421.8")]
        traits_rule = provider_index[("core-mc1", "361.4")]

        result = []
        for overlay in overlays:
            block_id = overlay["blockId"]
            source = sources_by_block_id[block_id]
            evidence = evidence_by_block_id[block_id]
            if type(source) is not source_type:
                raise TypeError(
                    "profile review source is invalid"
                )
            source_validate(source)
            if type(evidence) is not selection_type:
                raise TypeError(
                    "profile review evidence must be verified"
                )
            record = overlay.get("evidence")
            if type(record) is not dict:
                raise ValueError(
                    "profile review evidence record is invalid"
                )
            evidence_kind = record.get("kind")
            if evidence_kind == "whole-creature-prose":
                provider_rules = (table_rule,)
            elif (
                evidence_kind
                == "authored-traits-plus-canonical-default"
            ):
                provider_rules = (traits_rule, table_rule)
            else:
                raise ValueError(
                    "profile review evidence kind is invalid"
                )
            record_sha256 = sha256(
                canonical_json(overlay)
            ).hexdigest()
            decision_payload = {
                "schema": schema,
                "reviewer": reviewer,
                "manifestSha256": manifest_sha256,
                "recordSha256": record_sha256,
                "blockId": block_id,
                "creatureReceiptDigest": (
                    source.creature_receipt_digest
                ),
                "profile": overlay.get("profile"),
                "evidenceReceiptDigest": evidence.receipt.digest,
                "providerRuleReceiptDigests": [
                    item.receipt.digest for item in provider_rules
                ],
            }
            decision_digest = sha256(
                canonical_json(decision_payload)
            ).hexdigest()
            binding = binding_type(
                authority=source.authority,
                review_manifest_json=exact_manifest_json,
                block_id=block_id,
                definition_id=source.definition_id,
                ordered_block_sha256=source.ordered_block_sha256,
                creature_receipt_digest=(
                    source.creature_receipt_digest
                ),
                creature_source=source,
                profile=overlay.get("profile"),
                evidence_kind=evidence_kind,
                evidence_selection=evidence,
                provider_rules=provider_rules,
                review_record_sha256=record_sha256,
                decision_digest=decision_digest,
            )
            validate(binding, source)
            result.append(binding)
        return tuple(result)

    return post_init, validate, serialize, load, catalog_binding


(
    NaturalReachProfileBinding.__post_init__,
    NaturalReachProfileBinding._validated_overlay,
    NaturalReachProfileBinding.as_serialized,
    load_reviewed_profile_bindings,
    _catalog_profile_binding,
) = _bind_profile_review_contract(
    NaturalReachProfileBinding,
    CreatureGeometrySource,
    SizeSpaceReachRuleBundle,
    VerifiedSourceSelection,
    VerifiedRuleReceipt,
    SourceAuthorityAdapter,
    RawSourceArray,
    RawSourceMember,
    RawMemberStep,
    provider_rule_requirements,
    _canonical_footprint_spec,
    canonical_json_bytes,
    PROFILE_REVIEW_MANIFEST_JSON,
    PROFILE_REVIEW_MANIFEST_SHA256,
    _profile_catalog_record,
    _profile_catalog_for_source,
    _profile_catalog_for_block_id,
)
NaturalReachProfileBinding._as_serialized_validated = (
    NaturalReachProfileBinding.as_serialized
)
del _bind_profile_review_contract
del _profile_catalog_record
del _profile_catalog_for_source
del _profile_catalog_for_block_id


def _bind_public_geometry_contract(
    source_type: type[CreatureGeometrySource],
    rule_bundle_type: type[SizeSpaceReachRuleBundle],
    binding_type: type[NaturalReachProfileBinding],
    deferral_type: type[GeometryDeferral],
    footprint_type: type[CanonicalFootprint],
    natural_type: type[NaturalReachResolution],
    strike_type: type[StrikeReachResolution],
    patch_type: type[SizeSpaceReachPatch],
    projection_type: type[BattlegroundGeometryProjection],
    rule_type: type[RuleReference],
    canonical_sizes: tuple[str, ...],
    footprint_spec: Any,
    rule_matches: Any,
    serialize_rule: Any,
    extent_deferral: Any,
    canonical_footprint: Any,
    natural_reach: Any,
    exact_member_indices: Any,
    strike_reach_facts: Any,
    aggregate_deferrals: Any,
    projection_deferrals: Any,
    catalog_profile_binding: Any,
):
    """Bind every public geometry projection to private canonical derivation."""

    size_space_rule = ("core-pc1", "421.8")
    range_reach_rule = ("core-pc1", "426.3")
    weapon_reach_rule = ("core-pc1", "282.1")
    creature_space_rule = ("core-pc1", "422.3")
    different_size_space_rule = ("core-pc1", "422.5")
    profiles = ("tall", "long")
    reach_kinds = (
        "explicit-trait",
        "bare-weapon-trait",
        "natural-reach",
        "not-applicable-ranged",
    )
    maximum_identifier_bytes = 4_096
    maximum_integer = (1 << 63) - 1
    maximum_profile_bindings = 1_024
    numeric_reach = re.compile(
        r"^reach (?P<feet>[0-9]+) feet$",
        re.ASCII | re.IGNORECASE,
    )
    source_validate = source_type._validate
    source_serialize = source_type.as_source_identity
    rules_require_source = rule_bundle_type.require_source
    rules_serialize = rule_bundle_type.as_serialized
    binding_validate = binding_type._validated_overlay
    binding_serialize = binding_type.as_serialized

    def require_text(value: object, label: str) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or len(value.encode("utf-8")) > maximum_identifier_bytes
        ):
            raise ValueError(
                f"{label} must be a bounded non-empty trimmed string"
            )
        return value

    def require_nonnegative(value: object, label: str) -> int:
        if (
            type(value) is not int
            or value < 0
            or value > maximum_integer
        ):
            raise ValueError(
                f"{label} must be a nonnegative signed-64-bit integer"
            )
        return value

    def parse_integer(value: str) -> int | None:
        if (
            type(value) is not str
            or not value
            or any(character < "0" or character > "9" for character in value)
            or len(value) > len(str(maximum_integer))
            or (
                len(value) == len(str(maximum_integer))
                and value > str(maximum_integer)
            )
        ):
            return None
        return int(value)

    def validate_deferral(self: GeometryDeferral) -> None:
        if type(self) is not deferral_type:
            raise TypeError("GeometryDeferral must be exact")
        for field_name in ("deferral_id", "subject", "reason"):
            require_text(
                getattr(self, field_name, None),
                f"GeometryDeferral.{field_name}",
            )
        if getattr(self, "phase", None) not in (
            "link",
            "scenario",
            "runtime",
        ):
            raise ValueError("GeometryDeferral.phase is invalid")
        if type(getattr(self, "rule", None)) is not rule_type:
            raise TypeError(
                "GeometryDeferral.rule must be a RuleReference"
            )
        require_text(
            self.rule.source_id,
            "GeometryDeferral.rule.source_id",
        )
        require_text(
            self.rule.locator,
            "GeometryDeferral.rule.locator",
        )

    def serialize_deferral(
        self: GeometryDeferral,
    ) -> SerializedObject:
        validate_deferral(self)
        return {
            "id": self.deferral_id,
            "phase": self.phase,
            "subject": self.subject,
            "reason": self.reason,
            "rule": {
                "sourceId": self.rule.source_id,
                "locator": self.rule.locator,
            },
        }

    def validate_footprint(self: CanonicalFootprint) -> None:
        if type(self) is not footprint_type:
            raise TypeError("CanonicalFootprint must be exact")
        if type(getattr(self, "size", None)) is not str:
            raise TypeError(
                "CanonicalFootprint fields require exact canonical types"
            )
        expected = footprint_spec(self.size)
        actual = (
            getattr(self, "size_rank", None),
            getattr(self, "space_text", None),
            getattr(self, "space_kind", None),
            getattr(self, "space_feet", None),
            getattr(self, "width_squares", None),
            getattr(self, "height_squares", None),
            getattr(self, "grid_footprint_kind", None),
        )
        canonical = expected[:7]
        if (
            type(self.size) is not str
            or type(self.size_rank) is not int
            or type(self.space_text) is not str
            or type(self.space_kind) is not str
            or (
                self.space_feet is not None
                and type(self.space_feet) is not int
            )
            or type(self.width_squares) is not int
            or type(self.height_squares) is not int
            or type(self.grid_footprint_kind) is not str
        ):
            raise TypeError(
                "CanonicalFootprint fields require exact canonical types"
            )
        if actual != canonical:
            raise ValueError(
                "CanonicalFootprint does not match the canonical size table"
            )
        expected_extent = extent_deferral(self.size)
        if self.extent_deferral != expected_extent:
            raise ValueError(
                "CanonicalFootprint extent deferral is not canonical"
            )
        if self.extent_deferral is not None:
            validate_deferral(self.extent_deferral)

    def occupied_square_count(self: CanonicalFootprint) -> int:
        validate_footprint(self)
        return self.width_squares * self.height_squares

    def serialize_footprint(
        self: CanonicalFootprint,
    ) -> SerializedObject:
        validate_footprint(self)
        return {
            "shape": "square",
            "size": self.size,
            "sizeRank": self.size_rank,
            "spaceText": self.space_text,
            "spaceKind": self.space_kind,
            "spaceFeet": self.space_feet,
            "widthSquares": self.width_squares,
            "heightSquares": self.height_squares,
            "occupiedSquareCount": occupied_square_count(self),
            "gridFootprintKind": self.grid_footprint_kind,
            "customSpace": None,
            "extentDeferral": (
                serialize_deferral(self.extent_deferral)
                if self.extent_deferral is not None
                else None
            ),
            "rule": serialize_rule(size_space_rule),
        }

    def validate_natural(self: NaturalReachResolution) -> None:
        if type(self) is not natural_type:
            raise TypeError("NaturalReachResolution must be exact")
        if getattr(self, "status", None) not in (
            "resolved-size-invariant",
            "resolved-reviewed-profile",
            "deferred-profile",
        ):
            raise ValueError(
                "NaturalReachResolution.status is invalid"
            )
        for field_name in ("tall_feet", "long_feet"):
            require_nonnegative(
                getattr(self, field_name, None),
                f"NaturalReachResolution.{field_name}",
            )
        if self.resolved_feet is not None:
            require_nonnegative(
                self.resolved_feet,
                "NaturalReachResolution.resolved_feet",
            )
        if (
            self.selected_profile is not None
            and (
                type(self.selected_profile) is not str
                or self.selected_profile not in profiles
            )
        ):
            raise ValueError(
                "NaturalReachResolution.selected_profile is invalid"
            )
        if (
            self.binding is not None
            and type(self.binding) is not binding_type
        ):
            raise TypeError(
                "NaturalReachResolution.binding is invalid"
            )
        if (
            self.profile_deferral is not None
            and type(self.profile_deferral) is not deferral_type
        ):
            raise TypeError(
                "NaturalReachResolution.profile_deferral is invalid"
            )
        if self.status == "resolved-size-invariant":
            if (
                self.tall_feet != self.long_feet
                or self.selected_profile is not None
                or self.resolved_feet != self.tall_feet
                or self.binding is not None
                or self.profile_deferral is not None
            ):
                raise ValueError(
                    "size-invariant natural reach is inconsistent"
                )
        elif self.status == "resolved-reviewed-profile":
            if (
                self.binding is None
                or self.binding.profile != self.selected_profile
                or self.resolved_feet
                != (
                    self.tall_feet
                    if self.selected_profile == "tall"
                    else self.long_feet
                )
                or self.profile_deferral is not None
            ):
                raise ValueError(
                    "reviewed natural reach is inconsistent"
                )
        else:
            deferral = self.profile_deferral
            if (
                self.selected_profile is not None
                or self.resolved_feet is not None
                or self.binding is not None
                or type(deferral) is not deferral_type
                or deferral.deferral_id != "natural-reach-profile"
                or deferral.phase != "link"
                or deferral.reason
                != (
                    "Large-or-larger tall/long profile has no hash-bound "
                    "source-backed decision"
                )
                or not rule_matches(deferral.rule, size_space_rule)
            ):
                raise ValueError(
                    "deferred natural reach is inconsistent"
                )
            validate_deferral(deferral)

    def serialize_natural(
        self: NaturalReachResolution,
    ) -> SerializedObject:
        validate_natural(self)
        binding = None
        if self.binding is not None:
            binding_validate(self.binding)
            binding = binding_serialize(self.binding)
        return {
            "status": self.status,
            "candidates": {
                "tallFeet": self.tall_feet,
                "longFeet": self.long_feet,
            },
            "selectedProfile": self.selected_profile,
            "resolvedFeet": self.resolved_feet,
            "binding": binding,
            "profileDeferral": (
                serialize_deferral(self.profile_deferral)
                if self.profile_deferral is not None
                else None
            ),
            "rule": serialize_rule(size_space_rule),
        }

    def validate_strike(self: StrikeReachResolution) -> None:
        if type(self) is not strike_type:
            raise TypeError("StrikeReachResolution must be exact")
        if getattr(self, "strike_kind", None) not in (
            "melee",
            "ranged",
        ):
            raise ValueError(
                "StrikeReachResolution.strike_kind is invalid"
            )
        require_text(
            getattr(self, "strike_name", None),
            "StrikeReachResolution.strike_name",
        )
        for field_name in ("strike_field_ordinal", "strike_ordinal"):
            require_nonnegative(
                getattr(self, field_name, None),
                f"StrikeReachResolution.{field_name}",
            )
        for field_name in ("traits_member_ordinal", "trait_ordinal"):
            value = getattr(self, field_name, None)
            if value is not None:
                require_nonnegative(
                    value,
                    f"StrikeReachResolution.{field_name}",
                )
        if self.source_text is not None:
            require_text(
                self.source_text,
                "StrikeReachResolution.source_text",
            )
        if getattr(self, "resolution_kind", None) not in reach_kinds:
            raise ValueError(
                "StrikeReachResolution.resolution_kind is invalid"
            )
        for field_name in ("reach_feet", "candidate_feet"):
            value = getattr(self, field_name, None)
            if value is not None:
                require_nonnegative(
                    value,
                    f"StrikeReachResolution.{field_name}",
                )

        if self.resolution_kind == "explicit-trait":
            match = (
                numeric_reach.fullmatch(self.source_text)
                if type(self.source_text) is str
                else None
            )
            parsed = (
                parse_integer(match.group("feet"))
                if match is not None
                else None
            )
            if (
                self.strike_kind != "melee"
                or self.reach_feet is None
                or self.candidate_feet != self.reach_feet
                or parsed != self.reach_feet
                or self.reach_feet % 5
                or self.deferral is not None
                or self.traits_member_ordinal is None
                or self.trait_ordinal is None
            ):
                raise ValueError(
                    "explicit Strike reach is inconsistent"
                )
        elif self.resolution_kind == "bare-weapon-trait":
            deferral = self.deferral
            if (
                self.strike_kind != "melee"
                or type(self.source_text) is not str
                or self.source_text.casefold() != "reach"
                or self.reach_feet is not None
                or type(deferral) is not deferral_type
                or deferral.deferral_id
                != "canonical-weapon-reach-binding"
                or deferral.phase != "link"
                or deferral.reason
                != (
                    "bare reach must bind the canonical weapon trait "
                    "before adding 5 feet"
                )
                or not rule_matches(deferral.rule, weapon_reach_rule)
            ):
                raise ValueError(
                    "bare weapon reach is inconsistent"
                )
            validate_deferral(deferral)
        elif self.resolution_kind == "natural-reach":
            deferral = self.deferral
            if (
                self.strike_kind != "melee"
                or self.source_text is not None
                or self.trait_ordinal is not None
                or self.reach_feet != self.candidate_feet
                or (
                    self.reach_feet is None
                    and (
                        type(deferral) is not deferral_type
                        or deferral.deferral_id
                        != "natural-reach-profile"
                        or deferral.phase != "link"
                        or deferral.reason
                        != (
                            "implicit Melee reach depends on unresolved "
                            "whole-creature profile"
                        )
                        or not rule_matches(
                            deferral.rule,
                            size_space_rule,
                        )
                    )
                )
                or (
                    self.reach_feet is not None
                    and deferral is not None
                )
            ):
                raise ValueError(
                    "implicit natural reach is inconsistent"
                )
            if deferral is not None:
                validate_deferral(deferral)
        elif (
            self.strike_kind != "ranged"
            or self.source_text is not None
            or self.reach_feet is not None
            or self.candidate_feet is not None
            or self.deferral is not None
        ):
            raise ValueError(
                "ranged reach projection is inconsistent"
            )

    def serialize_strike(
        self: StrikeReachResolution,
    ) -> SerializedObject:
        validate_strike(self)
        operation = {
            "explicit-trait": "fixed",
            "bare-weapon-trait": "natural-reach-plus-5-feet",
            "natural-reach": "natural-reach",
            "not-applicable-ranged": "not-applicable",
        }[self.resolution_kind]
        return {
            "strike": {
                "kind": self.strike_kind,
                "name": self.strike_name,
                "fieldMemberOrdinal": self.strike_field_ordinal,
                "strikeOrdinal": self.strike_ordinal,
                "traitsMemberOrdinal": self.traits_member_ordinal,
                "traitOrdinal": self.trait_ordinal,
            },
            "sourceText": self.source_text,
            "kind": self.resolution_kind,
            "operation": operation,
            "reachFeet": self.reach_feet,
            "candidateFeet": self.candidate_feet,
            "deferral": (
                serialize_deferral(self.deferral)
                if self.deferral is not None
                else None
            ),
            "rule": serialize_rule(
                weapon_reach_rule
                if self.resolution_kind == "bare-weapon-trait"
                else range_reach_rule
            ),
        }

    def match_profile(
        source: CreatureGeometrySource,
        bindings: list[NaturalReachProfileBinding]
        | tuple[NaturalReachProfileBinding, ...],
        /,
    ) -> NaturalReachProfileBinding | None:
        if type(source) is not source_type:
            raise TypeError(
                "match_natural_reach_profile source is invalid"
            )
        if type(bindings) not in (list, tuple):
            raise TypeError(
                "natural-reach profile bindings must be ordered"
            )
        if len(bindings) > maximum_profile_bindings:
            raise ValueError(
                "natural-reach profile bindings exceed their collection "
                "bound"
            )
        values = tuple(bindings)
        if any(type(item) is not binding_type for item in values):
            raise TypeError(
                "natural-reach profile bindings contain an invalid value"
            )
        source_validate(source)
        for binding in values:
            binding_validate(binding)
        targeted = tuple(
            item
            for item in values
            if item.creature_receipt_digest
            == source.creature_receipt_digest
        )
        if len(targeted) > 1:
            raise NaturalReachProfileAmbiguityError(
                "multiple natural-reach profile bindings match the source "
                "block"
            )
        if not targeted:
            return None
        binding = targeted[0]
        binding_validate(binding, source)
        return binding

    def validate_patch(self: SizeSpaceReachPatch) -> None:
        source = getattr(self, "source", None)
        rules = getattr(self, "rules", None)
        footprint = getattr(self, "footprint", None)
        natural = getattr(self, "natural_reach", None)
        if type(self) is not patch_type or type(source) is not source_type:
            raise TypeError("SizeSpaceReachPatch.source is invalid")
        if type(rules) is not rule_bundle_type:
            raise TypeError("SizeSpaceReachPatch.rules is invalid")
        rules_require_source(rules, source)
        if (
            source.source_id != "core-mc1"
            or source.size_source_text not in canonical_sizes
        ):
            raise ValueError(
                "SizeSpaceReachPatch source is outside the family contract"
            )
        for key in ("Space", "Reach"):
            indices = exact_member_indices(source.raw_block, key)
            if indices is None or indices:
                raise ValueError(
                    "SizeSpaceReachPatch source has authored or colliding "
                    f"{key}"
                )
        if type(footprint) is not footprint_type:
            raise TypeError("SizeSpaceReachPatch.footprint is invalid")
        if type(natural) is not natural_type:
            raise TypeError(
                "SizeSpaceReachPatch.natural_reach is invalid"
            )
        strikes = getattr(self, "strike_reaches", None)
        deferrals = getattr(self, "deferrals", None)
        if (
            type(strikes) is not tuple
            or any(type(item) is not strike_type for item in strikes)
        ):
            raise TypeError(
                "SizeSpaceReachPatch.strike_reaches is invalid"
            )
        if (
            type(deferrals) is not tuple
            or any(
                type(item) is not deferral_type
                for item in deferrals
            )
        ):
            raise TypeError(
                "SizeSpaceReachPatch.deferrals is invalid"
            )
        validate_footprint(footprint)
        validate_natural(natural)
        for item in strikes:
            validate_strike(item)
        for item in deferrals:
            validate_deferral(item)
        expected_footprint = canonical_footprint(
            source.size_source_text
        )
        if footprint != expected_footprint:
            raise ValueError(
                "SizeSpaceReachPatch footprint is not compiler-derived"
            )
        binding = natural.binding
        if binding is not None:
            binding_validate(binding, source)
        expected_natural = natural_reach(
            source,
            source.size_source_text,
            binding,
        )
        if natural != expected_natural:
            raise ValueError(
                "SizeSpaceReachPatch natural reach is not compiler-derived"
            )
        expected_strikes = strike_reach_facts(
            source,
            expected_natural,
        )
        if expected_strikes is None or strikes != expected_strikes:
            raise ValueError(
                "SizeSpaceReachPatch strike reach is not compiler-derived"
            )
        expected_deferrals = aggregate_deferrals(
            source,
            expected_footprint,
            expected_natural,
            expected_strikes,
        )
        if deferrals != expected_deferrals:
            raise ValueError(
                "SizeSpaceReachPatch deferrals are not compiler-derived"
            )

    def profile_link_ready(self: SizeSpaceReachPatch) -> bool:
        validate_patch(self)
        return self.natural_reach.resolved_feet is not None

    def serialize_patch(
        self: SizeSpaceReachPatch,
    ) -> SerializedObject:
        validate_patch(self)
        return {
            "source": source_serialize(self.source),
            "providerProofs": rules_serialize(self.rules),
            "size": self.source.size_source_text,
            "footprint": serialize_footprint(self.footprint),
            "naturalReach": serialize_natural(self.natural_reach),
            "strikeReach": [
                serialize_strike(item) for item in self.strike_reaches
            ],
            "profileLinkReady": (
                self.natural_reach.resolved_feet is not None
            ),
            "runtimeReady": False,
            "deferrals": [
                serialize_deferral(item) for item in self.deferrals
            ],
        }

    def compile_family(
        source: object,
        rules: object,
        bindings: list[NaturalReachProfileBinding]
        | tuple[NaturalReachProfileBinding, ...] = (),
        /,
    ) -> SizeSpaceReachPatch | None:
        if type(source) is not source_type:
            return None
        if type(rules) is not rule_bundle_type:
            return None
        source_validate(source)
        if source.source_id != "core-mc1":
            return None
        size = source.size_source_text
        if size not in canonical_sizes:
            return None
        for key in ("Space", "Reach"):
            indices = exact_member_indices(source.raw_block, key)
            if indices is None or indices:
                return None
        binding = match_profile(source, bindings)
        if binding is None:
            binding = catalog_profile_binding(source, rules)
        footprint = canonical_footprint(size)
        natural = natural_reach(source, size, binding)
        strikes = strike_reach_facts(source, natural)
        if strikes is None:
            return None
        return patch_type(
            source=source,
            rules=rules,
            footprint=footprint,
            natural_reach=natural,
            strike_reaches=strikes,
            deferrals=aggregate_deferrals(
                source,
                footprint,
                natural,
                strikes,
            ),
        )

    def validate_projection(
        self: BattlegroundGeometryProjection,
    ) -> None:
        patch = getattr(self, "patch", None)
        if type(self) is not projection_type or type(patch) is not patch_type:
            raise TypeError(
                "BattlegroundGeometryProjection.patch is invalid"
            )
        validate_patch(patch)
        accepted = getattr(
            self,
            "gargantuan_minimum_accepted",
            None,
        )
        ready = getattr(self, "geometry_link_ready", None)
        deferrals = getattr(self, "projection_deferrals", None)
        if type(accepted) is not bool:
            raise TypeError(
                "gargantuan_minimum_accepted must be boolean"
            )
        if type(ready) is not bool:
            raise TypeError(
                "geometry_link_ready must be boolean"
            )
        if (
            type(deferrals) is not tuple
            or any(
                type(item) is not deferral_type
                for item in deferrals
            )
        ):
            raise TypeError(
                "projection_deferrals contain an invalid value"
            )
        for item in deferrals:
            validate_deferral(item)
        is_gargantuan = patch.footprint.size == "Gargantuan"
        if accepted and not is_gargantuan:
            raise ValueError(
                "only Gargantuan can accept the canonical minimum"
            )
        expected_ready = (
            patch.natural_reach.resolved_feet is not None
            and (not is_gargantuan or accepted)
        )
        if ready != expected_ready:
            raise ValueError(
                "geometry link readiness is not projection-derived"
            )
        if deferrals != projection_deferrals(patch, accepted):
            raise ValueError(
                "projection deferrals are not projection-derived"
            )

    def serialize_projection(
        self: BattlegroundGeometryProjection,
    ) -> SerializedObject:
        validate_projection(self)
        footprint = self.patch.footprint
        size = footprint.size
        return {
            "source": source_serialize(self.patch.source),
            "providerProofs": rules_serialize(self.patch.rules),
            "compileOnly": True,
            "runtimeReady": False,
            "geometryLinkReady": self.geometry_link_ready,
            "placement": {
                "shape": "square",
                "widthSquares": footprint.width_squares,
                "heightSquares": footprint.height_squares,
                "occupiedSquareCount": occupied_square_count(footprint),
                "extentKind": footprint.space_kind,
                "gargantuanMinimumAccepted": (
                    self.gargantuan_minimum_accepted
                ),
                "sharingPolicy": (
                    "tiny-may-share-larger-space"
                    if size == "Tiny"
                    else "exclusive-endpoint-unless-rule-allows"
                ),
                "wholeFootprintBoundsCheck": "runtime-deferred",
                "wholeFootprintBlockedCheck": "runtime-deferred",
            },
            "transit": {
                "willingCreature": "runtime-deferred",
                "threeSizeRanks": "runtime-deferred",
                "endpointPolicySeparate": True,
                "rules": [
                    serialize_rule(creature_space_rule),
                    serialize_rule(different_size_space_rule),
                ],
            },
            "adjacency": {
                "measure": "minimum-footprint-separation",
                "tenFootTwoDiagonalSpecialCase": True,
                "movementDistanceIsNotReachDistance": True,
                "rule": serialize_rule(range_reach_rule),
            },
            "naturalReach": serialize_natural(
                self.patch.natural_reach
            ),
            "strikeReach": [
                serialize_strike(item)
                for item in self.patch.strike_reaches
            ],
            "deferrals": [
                serialize_deferral(item)
                for item in self.projection_deferrals
            ],
        }

    def project(
        patch: SizeSpaceReachPatch,
        /,
        *,
        accept_gargantuan_minimum: bool = False,
    ) -> BattlegroundGeometryProjection:
        if type(patch) is not patch_type:
            raise TypeError(
                "project_battleground_geometry patch is invalid"
            )
        if type(accept_gargantuan_minimum) is not bool:
            raise TypeError(
                "accept_gargantuan_minimum must be boolean"
            )
        validate_patch(patch)
        is_gargantuan = patch.footprint.size == "Gargantuan"
        if accept_gargantuan_minimum and not is_gargantuan:
            raise ValueError(
                "only Gargantuan has a canonical minimum extent choice"
            )
        return projection_type(
            patch=patch,
            gargantuan_minimum_accepted=(
                is_gargantuan and accept_gargantuan_minimum
            ),
            geometry_link_ready=(
                patch.natural_reach.resolved_feet is not None
                and (
                    not is_gargantuan
                    or accept_gargantuan_minimum
                )
            ),
            projection_deferrals=projection_deferrals(
                patch,
                accept_gargantuan_minimum,
            ),
        )

    return (
        validate_deferral,
        serialize_deferral,
        validate_footprint,
        occupied_square_count,
        serialize_footprint,
        validate_natural,
        serialize_natural,
        validate_strike,
        serialize_strike,
        match_profile,
        validate_patch,
        profile_link_ready,
        serialize_patch,
        compile_family,
        validate_projection,
        serialize_projection,
        project,
    )


(
    GeometryDeferral.__post_init__,
    GeometryDeferral.as_serialized,
    CanonicalFootprint.__post_init__,
    _occupied_square_count,
    CanonicalFootprint.as_serialized,
    NaturalReachResolution.__post_init__,
    NaturalReachResolution.as_serialized,
    StrikeReachResolution.__post_init__,
    StrikeReachResolution.as_serialized,
    match_natural_reach_profile,
    SizeSpaceReachPatch._validate,
    _profile_link_ready,
    SizeSpaceReachPatch.as_serialized,
    compile_size_space_reach,
    BattlegroundGeometryProjection._validate,
    BattlegroundGeometryProjection.as_serialized,
    project_battleground_geometry,
) = _bind_public_geometry_contract(
    CreatureGeometrySource,
    SizeSpaceReachRuleBundle,
    NaturalReachProfileBinding,
    GeometryDeferral,
    CanonicalFootprint,
    NaturalReachResolution,
    StrikeReachResolution,
    SizeSpaceReachPatch,
    BattlegroundGeometryProjection,
    RuleReference,
    _CANONICAL_SIZES,
    _canonical_footprint_spec,
    _canonical_rule_matches,
    _canonical_rule_serialized,
    _extent_deferral,
    _canonical_footprint,
    _natural_reach,
    _exact_member_indices,
    _strike_reach_facts,
    _aggregate_deferrals,
    _projection_deferrals_bound,
    _catalog_profile_binding,
)
CanonicalFootprint.occupied_square_count = property(
    _occupied_square_count
)
NaturalReachResolution._as_serialized_validated = (
    NaturalReachResolution.as_serialized
)
SizeSpaceReachPatch.__post_init__ = SizeSpaceReachPatch._validate
SizeSpaceReachPatch.profile_link_ready = property(
    _profile_link_ready
)
BattlegroundGeometryProjection.__post_init__ = (
    BattlegroundGeometryProjection._validate
)
_projection_deferrals = _projection_deferrals_bound
del _bind_public_geometry_contract
del _occupied_square_count
del _profile_link_ready
del _catalog_profile_binding


__all__ = [
    "BattlegroundGeometryProjection",
    "COMPILER_ID",
    "CanonicalFootprint",
    "CreatureGeometrySource",
    "FAMILY_ID",
    "GeometryDeferral",
    "MAX_BLOCK_DEPTH",
    "MAX_BLOCK_NODES",
    "MAX_BLOCK_SOURCE_BYTES",
    "MAX_CONTENT_PATH_STEPS",
    "MAX_IDENTIFIER_BYTES",
    "MAX_OBJECT_MEMBERS",
    "MAX_PROFILE_BINDINGS",
    "MAX_SOURCE_KEY_BYTES",
    "MAX_SOURCE_STRING_BYTES",
    "MAX_SPEED_SOURCE_BYTES",
    "MAX_STRIKES_PER_FIELD",
    "MAX_STRIKE_NAME_BYTES",
    "MAX_TRAITS_PER_STRIKE",
    "MAX_TRAIT_SOURCE_BYTES",
    "MONSTER_CORE_SOURCE_ID",
    "NaturalReachProfileAmbiguityError",
    "NaturalReachProfileBinding",
    "NaturalReachResolution",
    "PROFILE_EVIDENCE_KINDS",
    "PROFILE_REVIEW_MANIFEST_JSON",
    "PROFILE_REVIEWER_ID",
    "PROFILE_REVIEW_MANIFEST_SHA256",
    "PROFILE_REVIEW_RECORD_COUNT",
    "PROFILE_REVIEW_SCHEMA",
    "PROFILES",
    "SIZES",
    "STRIKE_REACH_KINDS",
    "SizeSpaceReachRuleBundle",
    "SizeSpaceReachPatch",
    "StrikeReachResolution",
    "bind_size_space_reach_rules",
    "compile_size_space_reach",
    "load_reviewed_profile_bindings",
    "match_natural_reach_profile",
    "ordered_source_sha256",
    "project_battleground_geometry",
    "provider_rule_requirements",
]

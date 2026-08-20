"""Compile the reviewed Monster Core disease family without runtime activation.

The browser-facing rules engine never accepts caller-built source blocks for
this family.  Every disease carrier, disease-like affliction near miss, and
general rule provider is selected from one server-owned
``SourceAuthorityAdapter``.  Compilation preserves the exact authored save,
onset, maximum duration, ordered stages, stage effects and intervals.  Linking
derives aliases, delivery sites, and disease-adjacent abilities from the same
authenticated creature blocks.

Diseases require campaign clocks, exposure identity, recurrence and recovery,
treatment, cures, stage effects, and terminal transformations that the
encounter runtime does not yet own.  The artifacts below are consequently
compile/link-only, immutable, and explicitly unregistered.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
import re
from typing import Any, Callable, Literal, TypeAlias, final

from .contracts import RawSourceArray, RawSourceObject
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
    raw_source_sha256,
)


FAMILY_ID = "diseases"
MECHANIC_TYPE = "disease"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"
OFFICIAL_CREATURE_CENSUS_COUNT = 445
DISEASE_CARRIER_COUNT = 20
DISEASE_DEFINITION_COUNT = 14
DISEASE_ALIAS_COUNT = 2
DISEASE_MECHANIC_COUNT = 4
DISEASE_RELATED_COUNT = 3
DISEASE_NEAR_MISS_COUNT = 50
DISEASE_DELIVERY_COUNT = 27
REGISTRY_STATUS = "unregistered"

MAX_DISEASE_STAGES = 64
MAX_DISEASE_TEXT_BYTES = 65_536
MAX_DISEASE_RECORDS = 128
MAX_DISEASE_LINK_DEPTH = 16
MAX_DISEASE_LINKS = 128
MAX_DISEASE_LINK_ID_BYTES = 256

DIRECT_CENSUS_SHA256 = (
    "23bf39f41e468ed3d23680837ff41124b298fffbbac5a246cd4ee87260e6bb05"
)
NEAR_MISS_CENSUS_SHA256 = (
    "42dd4c8940a3342b9f9f4195d98250c5446e271f157213e2265e54d25367d207"
)
CONSUMER_REQUIREMENTS_SHA256 = (
    "498c853760b0bf3eff831d821d685e1c2831a90c308e17acfbb9723929140712"
)
PROVIDER_REQUIREMENTS_SHA256 = (
    "bf9c5d7b716ad4b09d4ebeb27dbf0dce0512c79f28da4d1f6e79f1d0abbca745"
)
NEAR_MISS_REQUIREMENTS_SHA256 = (
    "1a68d96dc1c933f1496e913c06f03645ec2420f9e655e882d329cc51caceb2fe"
)
COMPILED_CENSUS_SHA256 = (
    "ac2afa447bbb517860c817d60812a9897e93db195c41e29fe3186759cccb405e"
)
NEAR_MISS_OUTPUT_SHA256 = (
    "a9b702cb8a1f1d16d4ad452acbfbb7a409a0cadf312b14f98e38871a0a87b902"
)
LINKED_CORPUS_SHA256 = (
    "2b5130f992562e04aa9036938a0fb51eccc9740dcb4e1f0408a2ad2c6f420230"
)

DiseaseClassification: TypeAlias = Literal[
    "affliction-definition",
    "affliction-alias",
    "disease-mechanic",
]
DiseaseNearMissClassification: TypeAlias = Literal[
    "poison-affliction",
    "curse-affliction",
]


class DiseaseCompileError(ValueError):
    """Authenticated source is outside the reviewed disease grammar."""


class DiseaseLinkError(ValueError):
    """Reviewed disease records cannot form one canonical linked corpus."""


# Direct spec:
# rule id, official creature sequence, creature, ability, locator,
# carrier path, selection path, expected block hash, expected selection hash,
# authored traits, source shape, classification.
_DirectSpec = tuple[object, ...]
_DIRECT_SPECS: tuple[_DirectSpec, ...] = (
    ('disease-consumer:001', 52, 'Bogwid', 'Bogwid Fever', '46.1', (('Bogwid', 1), ('Bogwid', 0), ('^.creature', 2)), (('!.Bogwid Fever', 22),), '0845658e41f0ffb3f825597759067b1a55faa0a9634648a93c709ba0d7518795', '0c215c32476972cfb7c617cab39ce747eb08fe774d690a4124f2530c5918805d', ('disease',), 'scalar', 'affliction-definition'),
    ('disease-consumer:002', 84, 'Cacodaemon', 'Cacodaemonia', '72.3', (('^.creature', 1),), (('!.Cacodaemonia', 23),), '341f10a4d24391e8b3b82dd339e2eb91ba03b39fb2fb9682989abdcd538633e2', '90ec666767229623560a4532030734f8958468e247cef40e67a0a8089c6e5a1e', ('disease',), 'scalar', 'affliction-definition'),
    ('disease-consumer:003', 86, 'Leukodaemon', 'Infectious Aura', '74.1', (('^.creature', 1),), (('!.Infectious Aura', 22),), '749a4b5c6233f3548dc808ad3001ecf724f329f3e9dc526f2f7479c42fe6bd49', '741afe3cd32853100ddac31e7ccbda841f215e26e4b7c91150cb72b8752f23b9', ('aura', 'disease'), 'scalar', 'disease-mechanic'),
    ('disease-consumer:004', 86, 'Leukodaemon', 'Daemonic Pestilence', '74.1', (('^.creature', 1),), (('!.Daemonic Pestilence', 27),), '749a4b5c6233f3548dc808ad3001ecf724f329f3e9dc526f2f7479c42fe6bd49', '1a66c279c3c453bbe08bd06bdf379b7c88943088bf265ff88fd9673effc0ee04', ('disease',), 'scalar', 'affliction-definition'),
    ('disease-consumer:005', 96, 'Dero Strangler', 'Ill Glow', '84.5', (('^.creature', 1),), (('!.Ill Glow', 20),), 'f798980dc96bdfb74cc733dd063a4a1941f367966dd78a30affdc98e100f8efd', 'eef00e2d155903e500e4840007c0c18ec12dd783fc012074001a24a4e5ca5993', ('disease', 'light'), 'scalar', 'disease-mechanic'),
    ('disease-consumer:006', 221, 'Goblin Dog', 'Goblin Pox', '176.1', (('Goblin Dog', 1), ('Goblin Dog', 0), ('^.creature', 4)), (('!.Goblin Pox', 22),), '641d6d7dd4acd7543991b357d16ae5f786da43c3d355f8676f58a44d1f3fc63f', '87554a229430386a1b27cc30c92200ba51183eb6d0d58bee80ce8dc4d8af1c4e', ('disease',), 'scalar', 'affliction-definition'),
    ('disease-consumer:007', 239, 'Harpy', 'Putrid Plague', '193.1', (('Harpy', 1), ('Harpy', 0), ('^.creature', 4)), (('!.Putrid Plague', 23),), 'afc96a53e279c971add0bbe55487aa72f4574776a1ab4ccd4ae8eebb247c94eb', 'c7253484ab44167c3205ede392683e85d12968132db259a847ea7a6e13795908', ('disease',), 'scalar', 'affliction-definition'),
    ('disease-consumer:008', 303, 'Nuckelavee', 'Blight Breath', '243.1', (('Nuckelavee', 1), ('Nuckelavee', 0), ('^.creature', 3)), (('!.Blight Breath', 27),), '4a3049064cb7903bc14a5f08502598ca4fa783f2a3d92edc3668e615669d9af6', 'ef7643d1a776bfea3ed3098e754f85b596781ab2f2576de758d886b9b3e72800', ('disease', 'poison', 'primal'), 'ordered-object', 'disease-mechanic'),
    ('disease-consumer:009', 303, 'Nuckelavee', 'Mortasheen', '243.1', (('Nuckelavee', 1), ('Nuckelavee', 0), ('^.creature', 3)), (('!.Mortasheen', 28),), '4a3049064cb7903bc14a5f08502598ca4fa783f2a3d92edc3668e615669d9af6', '8f387f409ae99eb66d20a0863ac4c3899944644003f57a5cb9e3ff86a2b92585', ('disease',), 'scalar', 'affliction-definition'),
    ('disease-consumer:010', 309, 'Larval Ofalth', 'Wretched Weeps', '249.2', (('^.creature', 1),), (('!.Wretched Weeps', 25),), '7ca4478d25cd3ac6195ae7f689fbb97313c0abeafe6f77302ac463d3407578a6', '7f5be19f49d228aa02308020a461c2ca48977c737e857385e44cb71d60f5d238', ('disease',), 'scalar', 'affliction-definition'),
    ('disease-consumer:011', 310, 'Ofalth', 'Wretched Weeps', '249.4', (('^.creature', 1),), (('!.Wretched Weeps', 25),), 'a91f5c13e47b5a3e9f3e5e2cdc3881f4de49db2d812be9692096ecdd83e57fdc', '39fd2acf4469eba87f5213d852bf15a6468e636125d98fe59bff640814878dad', ('disease',), 'scalar', 'affliction-alias'),
    ('disease-consumer:012', 347, 'Cythnigot', 'Tangle Spores', '280.2', (('^.creature', 1),), (('!.Tangle Spores', 25),), '610f48edd6c1a7d9defaeffafd9b666e5901804dd5099ada0940dfd457620315', '5e1401b1facf054ebf55ec63bd831872867cde84bca8b1b5c263f983a8d3c826', ('disease',), 'ordered-object', 'affliction-definition'),
    ('disease-consumer:013', 349, 'Augnagar', 'Rotting Curse', '281.3', (('^.creature', 2),), (('!.Rotting Curse', 26),), 'b0db0f8267b80516e45d0a94f4f281899e5a5c4676657e916135a12f5099e768', '9c8e24e8c47ae85bb90c2e9eeb7a0365e8aa7e1a3bc4857e4e0316ef8c05b731', ('curse', 'disease', 'occult'), 'scalar', 'affliction-definition'),
    ('disease-consumer:014', 355, 'Giant Rat', 'Putrid Plague', '288.2', (('^.creature', 2),), (('!.Putrid Plague', 19),), '103d6d9f1d5485d0b437900c1f45b1566308b55e58a052de88daa95b17bde96d', 'c89218f1db41e6ed9c624c01633608d8ef95cae75e70fb97a63406824b8ddb68', ('disease',), 'ordered-object', 'affliction-definition'),
    ('disease-consumer:015', 356, 'Rat Swarm', 'Putrid Plague', '288.4', (('^.creature', 1),), (('!.Putrid Plague', 21),), 'd4af057553ee6a93512f4da0553f8d62a40983ccaf3234f764c4839140b52692', 'e590777c97678b3fef50f86f47ea27d3f0e013b489bd2d20669a588edde67963', ('disease',), 'ordered-object', 'affliction-alias'),
    ('disease-consumer:016', 408, 'Terotricus', 'Spore Cloud', '326.1', (('Terotricus', 1), ('Terotricus', 0), ('^.creature', 1)), (('!.Spore Cloud', 22),), 'dd6f39f571070c275d77cb41ff7a5d13b1cf242629a1def89b6709d103caf146', 'f5e1305037815ce60a7da779d9c96d794c09ea90c9bfb2334c46447249be3a03', ('aura', 'disease'), 'ordered-object', 'disease-mechanic'),
    ('disease-consumer:017', 408, 'Terotricus', 'Spore Blight', '326.1', (('Terotricus', 1), ('Terotricus', 0), ('^.creature', 1)), (('!.Spore Blight', 27),), 'dd6f39f571070c275d77cb41ff7a5d13b1cf242629a1def89b6709d103caf146', '6b5ece89406ea9ff52e01b9f5e908de6c1e884da566eab80e1bebfa09aaff5c1', ('disease',), 'ordered-object', 'affliction-definition'),
    ('disease-consumer:018', 426, 'Giant Wasp', 'Wasp Larva', '343.2', (('^.creature', 1),), (('!.Wasp Larva', 21),), '0a7ae76c15f69a6dbe37a3e8b6e46f638b9e33569b8927b9a3127c85e1134dad', 'a27689334ad70729684e229160605d7c85d7cd88e0509ac7b776660f2a721599', ('disease',), 'ordered-object', 'affliction-definition'),
    ('disease-consumer:019', 441, 'Zecui', 'Zecui Larvae', '355.1', (('Zecui', 1), ('Zecui', 0), ('^.creature', 3)), (('!.Zecui Larvae', 27),), 'f0b389a926e9cf9de66d8b62ea97e168d6fc4f8d5c006bca0d12870d6b47cee0', '8649c4a7d602332fd4daa3212d04973d7eb4ad025c5239d261c1119ebf9b6ed4', ('disease',), 'ordered-object', 'affliction-definition'),
    ('disease-consumer:020', 443, 'Plague Zombie', 'Zombie Rot', '356.6', (('^.creature', 1),), (('!.Zombie Rot', 23),), '411dc3a799372a7aa0936837ed6e8e8befb8ae59a1078bc2176c26f5dc19be86', '155b958d21b310f60d647730dba6be2167a9c37a776572a2b3304eb5aeeab8c0', ('disease', 'divine', 'void'), 'ordered-object', 'affliction-definition'),
)


# Provider spec: rule id, source, locator, carrier path, selection path,
# expected block hash, expected selection hash.
_ProviderSpec = tuple[object, ...]
_PROVIDER_SPECS: tuple[_ProviderSpec, ...] = (
    ('disease-glossary', 'core-mc1', '358.2', (), (('^.ability', 12),), '2b112ab4886ed04c44004a3cbf876404265d7488c35fae66c9f9369accfc13ef', '0538c786d6af245ad98a8ecad29bd9edebd4e4ecfe10eb3d8f275a8613fd727a'),
    ('affliction-format', 'core-pc1', '430.3', (), (), 'f2006abbd55e7c0fcb8d771f2c3f109af2d2231de4d37f6dcec5ab39f998df97', 'f2006abbd55e7c0fcb8d771f2c3f109af2d2231de4d37f6dcec5ab39f998df97'),
    ('affliction-save', 'core-pc1', '430.4', (), (), '9dfb48b64be6588d59a030a6d3eeb9614d19a841e8b0392b2ecd297f6aedd044', '9dfb48b64be6588d59a030a6d3eeb9614d19a841e8b0392b2ecd297f6aedd044'),
    ('affliction-onset', 'core-pc1', '430.5', (), (), '1e9eeafc96f519ce9a6ba6c4243690b7858d34baf91130bfcc4876e9366bf3e1', '1e9eeafc96f519ce9a6ba6c4243690b7858d34baf91130bfcc4876e9366bf3e1'),
    ('affliction-maximum-duration', 'core-pc1', '430.6', (), (), '2452601fae54468f54d258389e14a179ac3d587bd61faf315bc1472c8c48213e', '2452601fae54468f54d258389e14a179ac3d587bd61faf315bc1472c8c48213e'),
    ('affliction-stage', 'core-pc1', '430.7', (), (), 'aa7c749eb46a4e98d1f7f5da4f9db6a14d484c11060e5845ed882dc526238a88', 'aa7c749eb46a4e98d1f7f5da4f9db6a14d484c11060e5845ed882dc526238a88'),
    ('affliction-effect', 'core-pc1', '430.8', (), (), '78309af53b456d8b41dee46aba6c327f1be13cd60fa4e54331108c3466ae78aa', '78309af53b456d8b41dee46aba6c327f1be13cd60fa4e54331108c3466ae78aa'),
    ('multiple-exposures', 'core-pc1', '430.9', (), (), '2ee5c0ad2df10f0a688c7fad95ebca466946b154b8425a30357d18ff345eff6e', '2ee5c0ad2df10f0a688c7fad95ebca466946b154b8425a30357d18ff345eff6e'),
    ('virulent', 'core-pc1', '431.1', (), (), 'aa9e03e06b4c4279230255d4640218c8c9999c6e2a8cb66b1437c576c7555178', 'aa9e03e06b4c4279230255d4640218c8c9999c6e2a8cb66b1437c576c7555178'),
    ('removing-afflictions', 'core-pc1', '431.3', (), (), '5cbf437b0171fc21fda86cac8a9659a9d2d68b7db78cd0b40fc9c5029f751d2a', '5cbf437b0171fc21fda86cac8a9659a9d2d68b7db78cd0b40fc9c5029f751d2a'),
    ('treat-disease', 'core-pc1', '242.2', (), (), 'c92b7c5bfa179be54753f7d5f65d11cea8abafbe3dcbb984b115e8416eccf3b5', 'c92b7c5bfa179be54753f7d5f65d11cea8abafbe3dcbb984b115e8416eccf3b5'),
    ('cleanse-affliction', 'core-pc1', '320.5', (), (), '78a7ae7d54af019a3f51e31af026aa8b1b07a8293ecce47fb6cc482984e96812', '78a7ae7d54af019a3f51e31af026aa8b1b07a8293ecce47fb6cc482984e96812'),
)


# Related spec: parent consumer rule id, creature, ability, path, exact hash,
# relationship, authored traits, source shape.
_RelatedSpec = tuple[object, ...]
_RELATED_SPECS: tuple[_RelatedSpec, ...] = (
    ('disease-consumer:004', 'Leukodaemon', 'Plaguesense', (('!.Plaguesense', 14),), 'd62753e7a744a430dd5d6300438b3967bfb476256ddde937f3ac2385333cc3fd', 'disease-observer', (), 'scalar'),
    ('disease-consumer:004', 'Leukodaemon', 'Quicken Pestilence', (('!.Quicken Pestilence', 29),), '224bc24004fa21cbfe49a714cc609e70442a824f9e6611e2877a88d6ad40bce5', 'stage-accelerator', ('divine', 'manipulate'), 'ordered-object'),
    ('disease-consumer:018', 'Giant Wasp', 'Implant Eggs', (('!.Implant Eggs', 19),), '723f657bd346ce2b64226f493f7e48ac107e8dd3b355723e4e245816838fba61', 'named-delivery', (), 'ordered-object'),
)


# Near-miss spec: rule id, official sequence, creature, ability, locator,
# carrier path, selection path, exact selection hash, traits, source shape,
# excluded family classification.
_NearMissSpec = tuple[object, ...]
_NEAR_MISS_SPECS: tuple[_NearMissSpec, ...] = (
    ('disease-near-miss:001', 17, 'Giant Ant', 'Giant Ant Venom', '21.3', (('^.creature', 1),), (('!.Giant Ant Venom', 19),), '0ed12e0c537e642046e0510a88f685de830ab26536e00b6191e6b13ca905273f', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:002', 64, 'Cave Worm', 'Cave Worm Venom', '54.2', (('^.creature', 1),), (('!.Cave Worm Venom', 21),), '3c69922134f7e436da3a903487830659b6d1b04577d385ba0b0d9e40f9baa876', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:003', 65, 'Benthic Worm', 'Benthic Worm Venom', '56.2', (('^.creature', 1),), (('!.Benthic Worm Venom', 21),), '4f0f8e2c8b55a3b034af4d473876b32487010b9f30442e24d14f8bab4121c7cf', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:004', 66, 'Magma Worm', 'Magma Worm Venom', '57.2', (('^.creature', 2),), (('!.Magma Worm Venom', 27),), '7b1b6abdafaece75ee6466ee1dfc193ba84e72390dd0109fbe9f672d4a61e50e', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:005', 68, 'Giant Centipede', 'Giant Centipede Venom', '59.3', (('^.creature', 1),), (('!.Giant Centipede Venom', 19),), 'ecc4842e1e8bbb1b134ee704c2639facd653764d465d273844310394dcee2d1e', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:006', 69, 'Centipede Swarm', 'Centipede Swarm Venom', '59.5', (('^.creature', 1),), (('!.Centipede Swarm Venom', 21),), '0a91a051dee3eb16882252676120e275b351bb5b4a870dd4f4ea2e8be19fbe0e', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:007', 75, 'Quetz Coatl', 'Quetz Coatl Venom', '65.1', (('Coatl', 1), ('Coatl', 0), ('^.creature', 2)), (('!.Quetz Coatl Venom', 22),), 'f8b4f3bd63917c3763a9279ca489973b13b88a1d1994518e1685bfe285272d37', ('holy', 'poison'), 'scalar', 'poison-affliction'),
    ('disease-near-miss:008', 77, 'Con Rit', 'Con Rit Venom', '67.1', (('Con Rit', 1), ('Con Rit', 0), ('^.creature', 3)), (('!.Con Rit Venom', 21),), '65ccd85e1a1207b8b0d497b4061674df21bb8393142235156ddbeb5bac873c59', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:009', 101, 'Sarglagon', 'Sarglagon Venom', '88.3', (('^.creature', 1),), (('!.Sarglagon Venom', 27),), '142a7126d08fbd5cf81c7794b6ac8da91e5ddbaf8e963f1f2db2139d404e368b', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:010', 104, 'Nessari', 'Nessari Venom', '92.2', (('^.creature', 5),), (('!.Nessari Venom', 31),), 'cd5c6457e61e4a8b520f770f20c31b991dc4d091f22be764907da793fd2e1a4c', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:011', 105, 'Dezullon', 'Amnesia Venom', '94.1', (('Dezullon', 1), ('Dezullon', 0), ('^.creature', 4)), (('!.Amnesia Venom', 22),), '8777dc9a7c008ab346a1c7847104d979ca3ffc9490d606b9ff491b05b618d6f8', ('mental', 'poison'), 'scalar', 'poison-affliction'),
    ('disease-near-miss:012', 107, 'Compsognathus', 'Compsognathus Venom', '96.3', (('^.creature', 2),), (('!.Compsognathus Venom', 19),), 'aad43bf9689494641e325e0992624163e4f0e73fe44d44c5f541052003b76e1d', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:013', 123, 'Jah-Tohl', 'Mind Snatcher Venom', '106.1', (('^.creature', 3),), (('!.Mind Snatcher Venom', 27),), '424a7060d03940fc3fe740e1f9444970ce9dabcccb8027f79e84a60f00478278', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:014', 153, 'Jungle Drake', 'Jungle Drake Venom', '130.1', (('^.creature', 1),), (('!.Jungle Drake Venom', 24),), 'cb78fc5b63cee222e40dbc75792060c6a53fd7e50ebe98c32a55a72cfecd5f00', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:015', 154, 'Wyvern', 'Wyvern Venom', '131.1', (('^.creature', 2),), (('!.Wyvern Venom', 25),), '60f227e1e0cdd6b4f29ac23e599f80f42432be9e01bf483a74418fce65e0c0a5', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:016', 249, 'Homunculus', 'Homunculus Poison', '200.1', (('Homunculus', 1), ('Homunculus', 0), ('^.creature', 4)), (('!.Homunculus Poison', 22),), '9212a58eb8fbe9280c862826e0d72c6a017587cb400c04ae18e94ce283d71bcb', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:017', 260, 'Imp', 'Imp Venom', '206.1', (('Imp', 1), ('Imp', 0), ('^.creature', 0)), (('!.Imp Venom', 26),), '50aa1b5ed8c4e3676a13ce1372378d2eb6aefdafa733a75410c6d4a330de6d54', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:018', 261, 'Iron Warden', 'Iron Warden Poison', '207.1', (('Iron Warden', 1), ('Iron Warden', 0), ('^.creature', 0)), (('!.Iron Warden Poison', 26),), '7f1c6da3fb1d1d61af98b2ab9e2bdb22cbd6e798abb7328bfd26b48408eb81e0', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:019', 268, 'Kraken', 'Kraken Ink', '212.1', (('Kraken', 1), ('Kraken', 0), ('^.creature', 1)), (('!.Kraken Ink', 29),), '437d47c7fae7fd134e9443f752adcf15809b3228284bcb2498bcc1993d43a299', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:020', 276, 'Crag Linnorm', 'Crag Linnorm Venom', '220.2', (('^.creature', 1),), (('!.Crag Linnorm Venom', 27),), 'a288ee3532f72607411476283c0459f77eaabc8cfae90b46ea99c5366f8bf0da', ('fire', 'poison'), 'scalar', 'poison-affliction'),
    ('disease-near-miss:021', 277, 'Ice Linnorm', 'Ice Linnorm Venom', '221.1', (('^.creature', 1),), (('!.Ice Linnorm Venom', 27),), 'e7e86bec938659c050811c788a6d568ebb78378e67f2c6e897f78beb550507ec', ('cold', 'poison'), 'scalar', 'poison-affliction'),
    ('disease-near-miss:022', 278, 'Tarn Linnorm', 'Tarn Linnorm Venom', '221.3', (('^.creature', 1),), (('!.Tarn Linnorm Venom', 30),), '9b97b244d207497871e720bc10b81d5cbc08637581bc6d6c65c3eb698e99a801', ('acid', 'poison'), 'scalar', 'poison-affliction'),
    ('disease-near-miss:023', 279, 'Tor Linnorm', 'Tor Linnorm Venom', '222.1', (('^.creature', 1),), (('!.Tor Linnorm Venom', 30),), 'ce6f63d34c7e423590a8ce4bd171cb9b92583557221862eddd9accd6ae39db7f', ('fire', 'poison'), 'scalar', 'poison-affliction'),
    ('disease-near-miss:024', 281, 'Giant Monitor Lizard', 'Monitor Lizard Venom', '224.4', (('^.creature', 2),), (('!.Monitor Lizard Venom', 21),), 'cf874c65fbe58171b66b9fc4f4d6eddd2d8f5fbc4a6276339f07c9fb7268700e', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:025', 284, 'Lizardfolk Scout', 'Giant Centipede Venom', '226.4', (('^.creature', 1),), (('!.Giant Centipede Venom', 23),), '087f80d478e2638b85a1ecb491f6276b15c52e3ce25e3bd59ed062813a662a35', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:026', 289, 'Medusa', 'Serpent Venom', '230.1', (('Medusa', 1), ('Medusa', 0), ('^.creature', 2)), (('!.Serpent Venom', 25),), '868f9f10388d45754b3d9c40fce0b3946fb22a9c208f8d96c3147b64e52c3b12', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:027', 296, 'Smaranava', 'Smaranava Venom', '236.2', (('^.creature', 2),), (('!.Smaranava Venom', 24),), 'e8733e11685fb11cd7381873ef0cc982431275e3b9423293bcfa719e8e703bc3', ('incapacitation', 'mental', 'poison'), 'scalar', 'poison-affliction'),
    ('disease-near-miss:028', 297, 'Vicharamuni', 'Vicharamuni Venom', '237.1', (('^.creature', 2),), (('!.Vicharamuni Venom', 26),), 'd603b07135f2f8bace13eb424c9fe84752671ffeee62020788657f2712b2f88e', ('divine', 'holy', 'mental', 'poison', 'spirit'), 'scalar', 'poison-affliction'),
    ('disease-near-miss:029', 308, 'Giant Octopus', 'Giant Octopus Venom', '248.1', (('Octopus', 1), ('Octopus', 0), ('^.creature', 2)), (('!.Giant Octopus Venom', 22),), 'ec3fc01cbde7d36fbd62b04314ff560950b75576a4de0d890904a5ce281107c8', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:030', 343, 'Yamaraj', 'Yamaraj Venom', '276.4', (('^.creature', 1),), (('!.Yamaraj Venom', 30),), '7f13da9ae525fd6d63a6ad54e97185722cacc67bb55b8d29abcecf2b397888f3', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:031', 346, 'Pukwudgie', 'Pukwudgie Poison', '279.1', (('Pukwudgie', 1), ('Pukwudgie', 0), ('^.creature', 5)), (('!.Pukwudgie Poison', 27),), 'b3a8b55a41df62f464b202b147fb1a57cb4d758480ba92725eb8345702c76971', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:032', 348, 'Gongorinan', 'Gongorinan Venom', '281.1', (('^.creature', 1),), (('!.Gongorinan Venom', 26),), 'eb055dc332b7d6ba345fc3b8382865403ed6fd18a7a03b07c4f62cc9ffb7c716', ('poison', 'polymorph'), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:033', 350, 'Thulgant', 'Thulgant Venom', '283.1', (('^.creature', 1),), (('!.Thulgant Venom', 28),), 'eea28d87d65bfedaf85e4b91f63a20e440cf0ab133a2418dbf2da8bd1d5e9ebf', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:034', 353, 'Raktavarna', 'Raktavarna Venom', '286.2', (('^.creature', 1),), (('!.Raktavarna Venom', 27),), '4f7a82bbe608c725b6741cb9b57c8926042ce3df38ff19d846e8ffddf7e077a6', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:035', 359, 'Reefclaw', 'Reefclaw Venom', '291.1', (('Reefclaw', 1), ('Reefclaw', 0), ('^.creature', 4)), (('!.Reefclaw Venom', 22),), '6fdf0c678e8ae301078ca30fb2ab362dd377763189a84a40324ab8d518b822e9', ('poison',), 'scalar', 'poison-affliction'),
    ('disease-near-miss:036', 368, 'Giant Scorpion', 'Giant Scorpion Venom', '298.2', (('^.creature', 2),), (('!.Giant Scorpion Venom', 21),), '37ff84ec35f949996e62149bc06e8262af7df8ec19c236921e9ca118abd22ba3', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:037', 369, 'Scorpion Swarm', 'Scorpion Venom', '298.4', (('^.creature', 1),), (('!.Scorpion Venom', 21),), 'd97caaf07c9763b7f207eb1107ac413e25ba54a869a351458c77513535589f59', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:038', 370, 'Sea Serpent', 'Sea Serpent Algae', '299.1', (('Sea Serpent', 1), ('Sea Serpent', 0), ('^.creature', 2)), (('!.Sea Serpent Algae', 23),), 'd31c1c43a66e1cc02904e43de9928072e7dd7db8f2a64f9b41a1fb6b1e7209a4', ('incapacitation', 'poison'), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:039', 374, 'Zyss Serpentfolk', 'Serpentfolk Venom', '302.2', (('^.creature', 1),), (('!.Serpentfolk Venom', 26),), '244aa19a5c9be946b7eed4db049e8b08056841a498671a09bdcf0ba2ef337f30', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:040', 384, 'Shuln', 'Shuln Saliva', '309.1', (('Shuln', 1), ('Shuln', 0), ('^.creature', 1)), (('!.Shuln Saliva', 22),), 'd11c5a22d8a8f3170ef1abed9a24eb67f6630efc12f9a166861996cddb50ec9b', ('incapacitation', 'poison'), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:041', 393, 'Viper', 'Viper Venom', '316.2', (('^.creature', 1),), (('!.Viper Venom', 20),), '4784ec487963c3dfe15ccb1ed2a7547792076322dc508d27e17505ee059ed64e', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:042', 395, 'Giant Viper', 'Giant Viper Venom', '316.6', (('^.creature', 1),), (('!.Giant Viper Venom', 21),), 'b3b0d0350f9aaf6a4ac9e983febe5bcbf6a8d506f6e6889df793682bdf820481', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:043', 399, 'Spider Swarm', 'Spider Swarm Venom', '320.2', (('^.creature', 1),), (('!.Spider Swarm Venom', 23),), 'dbe26860a8a0024fbcc5c4da2ce4c967fef83b22af6d1ef6372c40dc64aef6bc', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:044', 400, 'Hunting Spider', 'Hunting Spider Venom', '320.4', (('^.creature', 1),), (('!.Hunting Spider Venom', 23),), '0009822bfed705086503ef93c8ed61a8be91ee980af457aa9a8db846164a4597', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:045', 401, 'Giant Tarantula', 'Giant Tarantula Venom', '321.1', (('^.creature', 1),), (('!.Giant Tarantula Venom', 19),), 'aba38d8951b9c40d2e4e78df545ee3a7308266376dfa9a2f74a67ba1af69ac21', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:046', 402, 'Goliath Spider', 'Goliath Spider Venom', '321.3', (('^.creature', 1),), (('!.Goliath Spider Venom', 23),), 'aa5980e0b7eba35b56e1bcd3184aead15e14405b2b4e892e9f0d37dca47c4c12', ('incapacitation', 'poison'), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:047', 426, 'Giant Wasp', 'Giant Wasp Venom', '343.2', (('^.creature', 1),), (('!.Giant Wasp Venom', 20),), 'eaa351b893db58fa290751fd43845079cd84f785eb5d4d9a28a976f15ddcea00', ('incapacitation', 'poison'), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:048', 427, 'Wasp Swarm', 'Wasp Venom', '343.4', (('^.creature', 1),), (('!.Wasp Venom', 22),), 'd3dd5598b9ad980eca8d043315c645fb5b18a5faa1dbf3ab8dca4d7e91c12170', ('poison',), 'ordered-object', 'poison-affliction'),
    ('disease-near-miss:049', 432, 'Wight', 'Corrupting Spite', '348.1', (('Wight', 1), ('Wight', 0), ('^.creature', 3)), (('!.Corrupting Spite', 26),), '8fc40d0ac55c896333ceaa277dbf55953f95b83eab5a4ab5491cb1d9ad3f0652', ('curse', 'divine', 'void'), 'ordered-object', 'curse-affliction'),
    ('disease-near-miss:050', 436, 'Wraith', "Void's Embrace", '351.1', (('Wraith', 1), ('Wraith', 0), ('^.creature', 3)), (("!.Void's Embrace", 25),), '0876c1a5cb33b5f8ffa24b0ea28fe2ea03a564a81152b0650984ac02939fcd07', ('curse', 'death', 'divine', 'void'), 'ordered-object', 'curse-affliction'),
)


_TRAIT_PREFIX_RE = re.compile(r"^\s*\((?P<traits>[^)]+)\)", re.DOTALL)
_TAG_RE = re.compile(r"</?[^>]+>", re.ASCII)
_SAVE_DC_FIRST_RE = re.compile(
    r"\b(?:Saving Throw\s+)?DC\s+(?P<dc>[0-9]+)\s+"
    r"(?:(?P<basic>basic)\s+)?"
    r"(?P<save>Fortitude|Reflex|Will)\b",
    re.IGNORECASE | re.ASCII,
)
_SAVE_TYPE_FIRST_RE = re.compile(
    r"\bSaving Throw\s+(?:(?P<basic>basic)\s+)?"
    r"(?P<save>Fortitude|Reflex|Will)\s+"
    r"DC\s+(?P<dc>[0-9]+)\b",
    re.IGNORECASE | re.ASCII,
)
_DURATION_RE = re.compile(
    r"(?P<amount>[0-9]+(?:d[0-9]+(?:[+-][0-9]+)?)?)\s+"
    r"(?P<unit>rounds?|minutes?|hours?|days?|weeks?)\b",
    re.IGNORECASE | re.ASCII,
)
_ONSET_RE = re.compile(
    r"\bOnset\s+(?P<duration>"
    r"[0-9]+(?:d[0-9]+(?:[+-][0-9]+)?)?\s+"
    r"(?:rounds?|minutes?|hours?|days?|weeks?))\b",
    re.IGNORECASE | re.ASCII,
)
_MAX_DURATION_RE = re.compile(
    r"\bMaximum Duration\s+(?P<duration>"
    r"[0-9]+(?:d[0-9]+(?:[+-][0-9]+)?)?\s+"
    r"(?:rounds?|minutes?|hours?|days?|weeks?))\b",
    re.IGNORECASE | re.ASCII,
)
_STAGE_HEADER_RE = re.compile(
    r"(?:^|[;,])\s*Stage\s+(?P<number>[0-9]+)\b",
    re.IGNORECASE | re.ASCII,
)
_ALIAS_RE = re.compile(
    r"\b(?:Saving Throw\s+)?As\s+(?P<target>[^,.]+?)"
    r"(?:,\s*but DC\s+(?P<dc>[0-9]+))?\.",
    re.IGNORECASE | re.ASCII,
)
_DICE_RE = re.compile(
    r"(?P<count>[0-9]+)d(?P<sides>[0-9]+)"
    r"(?P<modifier>[+-][0-9]+)?",
    re.ASCII,
)
_NORMALIZE_RE = re.compile(r"[^a-z0-9]+", re.ASCII)


class _SealedType(type):
    def __new__(
        metaclass: type,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        **kwargs: object,
    ) -> type:
        if any(
            base.__dict__.get("_disease_type_sealed", False)
            for base in bases
        ):
            raise TypeError("sealed disease artifacts cannot be subclassed")
        return super().__new__(
            metaclass,
            name,
            bases,
            namespace,
            **kwargs,
        )

    def __setattr__(cls, name: str, value: object) -> None:
        if cls.__dict__.get("_disease_type_sealed", False):
            raise TypeError(f"{cls.__name__} is sealed")
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if cls.__dict__.get("_disease_type_sealed", False):
            raise TypeError(f"{cls.__name__} is sealed")
        super().__delattr__(name)


def _seal_type(value: type) -> None:
    type.__setattr__(value, "_disease_type_sealed", True)


class _NoTransfer(metaclass=_SealedType):
    __slots__ = ()

    def __copy__(self) -> object:
        raise TypeError(f"{type(self).__name__} cannot be copied")

    def __deepcopy__(self, _memo: dict[int, object]) -> object:
        raise TypeError(f"{type(self).__name__} cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError(f"{type(self).__name__} cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError(f"{type(self).__name__} cannot be pickled")


@final
@dataclass(frozen=True, slots=True, init=False)
class DiseaseDuration(_NoTransfer):
    source_text: str
    amount_kind: str
    fixed_amount: int | None
    dice_count: int | None
    dice_sides: int | None
    dice_modifier: int | None
    unit: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("DiseaseDuration is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class DiseaseSave(_NoTransfer):
    dc: int
    save_type: str
    basic: bool
    source_text: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("DiseaseSave is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class DiseaseStage(_NoTransfer):
    number: int
    source_text: str
    effect_text: str
    duration: DiseaseDuration | None
    terminal: bool

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("DiseaseStage is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class DiseaseDependency(_NoTransfer):
    dependency_id: str
    phase: str
    required_contract: str
    provider_rule_id: str | None

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("DiseaseDependency is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class CompiledDisease(_NoTransfer):
    record_id: str
    sequence: int
    creature_name: str
    ability_name: str
    locator: str
    classification: DiseaseClassification
    source_shape: str
    traits: tuple[str, ...]
    action_cost: int | str | None
    source_text: str
    source_text_sha256: str
    saving_throw: DiseaseSave | None
    onset: DiseaseDuration | None
    maximum_duration: DiseaseDuration | None
    stages: tuple[DiseaseStage, ...]
    alias_target_name: str | None
    alias_dc_override: int | None
    consumer_rule: VerifiedRuleReceipt
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    dependencies: tuple[DiseaseDependency, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("CompiledDisease is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class DiseaseNearMiss(_NoTransfer):
    record_id: str
    sequence: int
    creature_name: str
    ability_name: str
    locator: str
    classification: DiseaseNearMissClassification
    source_shape: str
    traits: tuple[str, ...]
    source_text: str
    source_text_sha256: str
    saving_throw: DiseaseSave
    onset: DiseaseDuration | None
    maximum_duration: DiseaseDuration | None
    stages: tuple[DiseaseStage, ...]
    consumer_rule: VerifiedRuleReceipt

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("DiseaseNearMiss is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class DiseaseAliasLink(_NoTransfer):
    alias_record_id: str
    definition_record_id: str
    resolved_dc: int

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("DiseaseAliasLink is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class DiseaseDelivery(_NoTransfer):
    delivery_id: str
    creature_name: str
    source_name: str
    delivery_kind: str
    delivery_mode: str
    declared_record_id: str | None
    resolved_definition_id: str | None
    source_path: tuple[str, ...]
    source_sha256: str
    parent_consumer_rule_id: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("DiseaseDelivery is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class RelatedDiseaseUse(_NoTransfer):
    related_id: str
    creature_name: str
    ability_name: str
    relationship: str
    source_shape: str
    traits: tuple[str, ...]
    source_text: str
    source_sha256: str
    source_path: tuple[str, ...]
    parent_consumer_rule_id: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("RelatedDiseaseUse is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class DiseaseLinkEdge(_NoTransfer):
    consumer_id: str
    producer_id: str

    def __init__(self, consumer_id: str, producer_id: str) -> None:
        if type(self) is not DiseaseLinkEdge:
            raise TypeError("DiseaseLinkEdge must be exact")
        max_id_bytes = 256
        if (
            type(consumer_id) is not str
            or not consumer_id
            or consumer_id != consumer_id.strip()
            or len(consumer_id.encode("utf-8")) > max_id_bytes
            or type(producer_id) is not str
            or not producer_id
            or producer_id != producer_id.strip()
            or len(producer_id.encode("utf-8")) > max_id_bytes
        ):
            raise ValueError(
                "disease link IDs must be bounded trimmed text"
            )
        object.__setattr__(self, "consumer_id", consumer_id)
        object.__setattr__(self, "producer_id", producer_id)


@final
@dataclass(frozen=True, slots=True, init=False)
class LinkedDiseaseCorpus(_NoTransfer):
    records: tuple[CompiledDisease, ...]
    near_misses: tuple[DiseaseNearMiss, ...]
    alias_links: tuple[DiseaseAliasLink, ...]
    deliveries: tuple[DiseaseDelivery, ...]
    related_uses: tuple[RelatedDiseaseUse, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("LinkedDiseaseCorpus is linker-created")


def _new_artifact(
    artifact_type: type,
    field_names: tuple[str, ...],
    values: tuple[object, ...],
) -> object:
    if len(field_names) != len(values):
        raise AssertionError("disease artifact construction is malformed")
    result = object.__new__(artifact_type)
    for field_name, value in zip(field_names, values, strict=True):
        object.__setattr__(result, field_name, value)
    return result


def _path_from_spec(
    value: tuple[tuple[str, int], ...],
) -> tuple[RawMemberStep, ...]:
    if type(value) is not tuple:
        raise AssertionError("reviewed disease path must be an exact tuple")
    result: list[RawMemberStep] = []
    for item in value:
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
        ):
            raise AssertionError("reviewed disease path is malformed")
        result.append(RawMemberStep(item[0], item[1]))
    return tuple(result)


def _direct_requirement(
    spec: _DirectSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _source_id: str = MONSTER_CORE_SOURCE_ID,
    _path_impl: Callable[
        [tuple[tuple[str, int], ...]],
        tuple[RawMemberStep, ...],
    ] = _path_from_spec,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec[0],
        source_id=_source_id,
        locator=spec[4],
        carrier_path=_path_impl(spec[5]),
        selection_path=_path_impl(spec[6]),
        expected_block_sha256=spec[7],
        expected_selection_sha256=spec[8],
    )


def _provider_requirement(
    spec: _ProviderSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _path_impl: Callable[
        [tuple[tuple[str, int], ...]],
        tuple[RawMemberStep, ...],
    ] = _path_from_spec,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec[0],
        source_id=spec[1],
        locator=spec[2],
        carrier_path=_path_impl(spec[3]),
        selection_path=_path_impl(spec[4]),
        expected_block_sha256=spec[5],
        expected_selection_sha256=spec[6],
    )


def _near_miss_requirement(
    spec: _NearMissSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _source_id: str = MONSTER_CORE_SOURCE_ID,
    _path_impl: Callable[
        [tuple[tuple[str, int], ...]],
        tuple[RawMemberStep, ...],
    ] = _path_from_spec,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec[0],
        source_id=_source_id,
        locator=spec[4],
        carrier_path=_path_impl(spec[5]),
        selection_path=_path_impl(spec[6]),
        expected_selection_sha256=spec[7],
    )


def _same_requirement(
    left: RuleRequirement,
    right: RuleRequirement,
    _canonical_json_impl: Callable[[object], bytes] = (
        canonical_json_bytes
    ),
    _requirement_type: type[RuleRequirement] = RuleRequirement,
) -> bool:
    return _canonical_json_impl(
        _requirement_type.as_serialized(left)
    ) == _canonical_json_impl(_requirement_type.as_serialized(right))


def _same_receipt(
    left: SourceReceipt,
    right: SourceReceipt,
    _canonical_json_impl: Callable[[object], bytes] = (
        canonical_json_bytes
    ),
    _receipt_type: type[SourceReceipt] = SourceReceipt,
) -> bool:
    return _canonical_json_impl(
        _receipt_type.as_serialized(left)
    ) == _canonical_json_impl(_receipt_type.as_serialized(right))


def _unique_member(
    value: RawSourceObject,
    key: str,
    _raw_object_type: type[RawSourceObject] = RawSourceObject,
) -> object | None:
    if type(value) is not _raw_object_type:
        raise DiseaseCompileError("ability source must be an exact object")
    matches = tuple(
        member.value for member in value.members if member.key == key
    )
    if len(matches) > 1:
        raise DiseaseCompileError(f"disease source duplicates {key!r}")
    return matches[0] if matches else None


def _flow_text(
    value: object,
    label: str,
    _raw_object_type: type[RawSourceObject] = RawSourceObject,
    _max_text_bytes: int = MAX_DISEASE_TEXT_BYTES,
) -> str:
    if type(value) is str:
        result = value
    elif type(value) is _raw_object_type:
        paragraphs = []
        for member in value.members:
            if member.key != "~.p" or type(member.value) is not str:
                raise DiseaseCompileError(
                    f"{label} has unsupported ordered content"
                )
            paragraphs.append(member.value)
        if not paragraphs:
            raise DiseaseCompileError(f"{label} is empty")
        result = "\n\n".join(paragraphs)
    else:
        raise DiseaseCompileError(f"{label} must be authored text")
    if (
        not result
        or len(result.encode("utf-8")) > _max_text_bytes
        or "\x00" in result
    ):
        raise DiseaseCompileError(f"{label} is outside its text bound")
    return result


def _plain_text(
    value: str,
    _tag_re: re.Pattern[str] = _TAG_RE,
    _html_unescape: Callable[[str], str] = html.unescape,
) -> str:
    if type(value) is not str:
        raise TypeError("disease source text must be exact text")
    return " ".join(
        _html_unescape(_tag_re.sub(" ", value)).replace("’", "'").split()
    )


def _normalized(
    value: str,
    _normalize_re: re.Pattern[str] = _NORMALIZE_RE,
) -> str:
    return " ".join(_normalize_re.sub(" ", value.casefold()).split())


def _ability_parts_value(
    raw: object,
    _trait_prefix_re: re.Pattern[str] = _TRAIT_PREFIX_RE,
    _plain_text_impl: Callable[[str], str] = _plain_text,
    _raw_object_type: type[RawSourceObject] = RawSourceObject,
    _raw_array_type: type[RawSourceArray] = RawSourceArray,
    _unique_member_impl: Callable[
        [RawSourceObject, str],
        object | None,
    ] = _unique_member,
    _flow_text_impl: Callable[[object, str], str] = _flow_text,
) -> tuple[
    str,
    tuple[str, ...],
    int | str | None,
    str,
    str,
]:
    if type(raw) is str:
        match = _trait_prefix_re.match(raw)
        traits = (
            ()
            if match is None
            else tuple(
                item.strip().casefold()
                for item in match.group("traits").split(",")
                if item.strip()
            )
        )
        return "scalar", traits, None, raw, _plain_text_impl(raw)
    if type(raw) is not _raw_object_type:
        raise DiseaseCompileError(
            "reviewed disease ability must be text or an ordered object"
        )
    traits_value = _unique_member_impl(raw, "Traits")
    if type(traits_value) is _raw_array_type:
        if any(type(item) is not str for item in traits_value.items):
            raise DiseaseCompileError("disease Traits must be text")
        traits = tuple(item.casefold() for item in traits_value.items)
    elif type(traits_value) is str:
        traits = tuple(
            item.strip().casefold()
            for item in traits_value.split(",")
            if item.strip()
        )
    elif traits_value is None:
        traits = ()
    else:
        raise DiseaseCompileError("disease Traits have an invalid shape")
    action_value = _unique_member_impl(raw, "Action")
    if action_value in {"single", "one"}:
        action: int | str | None = 1
    elif action_value == "two":
        action = 2
    elif action_value == "three":
        action = 3
    elif action_value in {"free", "reaction"}:
        action = action_value
    elif action_value is None:
        action = None
    else:
        raise DiseaseCompileError("disease Action is unsupported")
    description_value = _unique_member_impl(raw, "Description")
    source_text = _flow_text_impl(
        description_value,
        "disease Description",
    )
    components = []
    for key in ("Saving Throw", "Onset", "Maximum Duration"):
        field_value = _unique_member_impl(raw, key)
        if field_value is not None:
            if type(field_value) is not str:
                raise DiseaseCompileError(
                    f"disease {key} must be text"
                )
            components.append(f"{key} {field_value}")
    components.append(source_text)
    return (
        "ordered-object",
        traits,
        action,
        source_text,
        _plain_text_impl("; ".join(components)),
    )


def _ability_parts(
    selection: VerifiedSourceSelection,
    _value_impl: Callable[
        [object],
        tuple[
            str,
            tuple[str, ...],
            int | str | None,
            str,
            str,
        ],
    ] = _ability_parts_value,
) -> tuple[
    str,
    tuple[str, ...],
    int | str | None,
    str,
    str,
]:
    return _value_impl(selection.selected_value)


def _duration(
    source_text: str,
    duration_type: type[DiseaseDuration],
    new_artifact: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    _duration_re: re.Pattern[str] = _DURATION_RE,
    _dice_re: re.Pattern[str] = _DICE_RE,
) -> DiseaseDuration:
    match = _duration_re.fullmatch(source_text.strip())
    if match is None:
        raise DiseaseCompileError(
            f"unsupported disease duration: {source_text!r}"
        )
    amount_text = match.group("amount")
    dice = _dice_re.fullmatch(amount_text)
    if dice is None:
        amount_kind = "fixed"
        fixed_amount = int(amount_text)
        dice_count = dice_sides = dice_modifier = None
    else:
        amount_kind = "dice"
        fixed_amount = None
        dice_count = int(dice.group("count"))
        dice_sides = int(dice.group("sides"))
        dice_modifier = int(dice.group("modifier") or "0")
    if (
        (fixed_amount is not None and fixed_amount <= 0)
        or (dice_count is not None and dice_count <= 0)
        or (dice_sides is not None and dice_sides <= 0)
    ):
        raise DiseaseCompileError("disease duration must be positive")
    return new_artifact(
        duration_type,
        (
            "source_text",
            "amount_kind",
            "fixed_amount",
            "dice_count",
            "dice_sides",
            "dice_modifier",
            "unit",
        ),
        (
            match.group(0),
            amount_kind,
            fixed_amount,
            dice_count,
            dice_sides,
            dice_modifier,
            match.group("unit").casefold().removesuffix("s"),
        ),
    )  # type: ignore[return-value]


def _save(
    plain: str,
    save_type: type[DiseaseSave],
    new_artifact: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    _dc_first_re: re.Pattern[str] = _SAVE_DC_FIRST_RE,
    _type_first_re: re.Pattern[str] = _SAVE_TYPE_FIRST_RE,
) -> DiseaseSave | None:
    match = _dc_first_re.search(plain)
    if match is None:
        match = _type_first_re.search(plain)
    if match is None:
        return None
    return new_artifact(
        save_type,
        ("dc", "save_type", "basic", "source_text"),
        (
            int(match.group("dc")),
            match.group("save").casefold(),
            match.group("basic") is not None,
            match.group(0),
        ),
    )  # type: ignore[return-value]


def _optional_duration(
    pattern: re.Pattern[str],
    plain: str,
    duration_type: type[DiseaseDuration],
    new_artifact: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    _duration_impl: Callable[..., DiseaseDuration] = _duration,
) -> DiseaseDuration | None:
    match = pattern.search(plain)
    if match is None:
        return None
    return _duration_impl(
        match.group("duration"),
        duration_type,
        new_artifact,
    )


def _stages(
    plain: str,
    stage_type: type[DiseaseStage],
    duration_type: type[DiseaseDuration],
    new_artifact: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    _stage_header_re: re.Pattern[str] = _STAGE_HEADER_RE,
    _duration_re: re.Pattern[str] = _DURATION_RE,
    _duration_impl: Callable[..., DiseaseDuration] = _duration,
    _max_stages: int = MAX_DISEASE_STAGES,
) -> tuple[DiseaseStage, ...]:
    matches = tuple(_stage_header_re.finditer(plain))
    if len(matches) > _max_stages:
        raise DiseaseCompileError("disease stage count exceeds its bound")
    result = []
    for index, match in enumerate(matches):
        number = int(match.group("number"))
        expected = index + 1
        if number != expected:
            raise DiseaseCompileError(
                "disease stages must be contiguous and one-based"
            )
        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(plain)
        )
        source_text = plain[start:end].strip(" ,;.")
        if not source_text:
            raise DiseaseCompileError("disease stage effect is empty")
        duration_matches = tuple(_duration_re.finditer(source_text))
        duration = None
        effect_text = source_text
        if duration_matches:
            candidate = duration_matches[-1]
            tail = source_text[candidate.end():].strip()
            if tail in {"", ")"}:
                duration = _duration_impl(
                    candidate.group(0),
                    duration_type,
                    new_artifact,
                )
                before = source_text[:candidate.start()].rstrip(" ;")
                after = source_text[candidate.end():]
                effect_text = f"{before}{after}".strip()
                effect_text = effect_text.replace("; )", ")")
                if effect_text.endswith("()"):
                    effect_text = effect_text[:-2].rstrip()
        terminal = duration is None or bool(
            re.search(
                r"\b(dead|dies?|emerges?|transforms?|rising)\b",
                effect_text,
                re.IGNORECASE | re.ASCII,
            )
        )
        result.append(
            new_artifact(
                stage_type,
                (
                    "number",
                    "source_text",
                    "effect_text",
                    "duration",
                    "terminal",
                ),
                (
                    number,
                    source_text,
                    effect_text,
                    duration,
                    terminal,
                ),
            )
        )
    return tuple(result)  # type: ignore[return-value]


def _raw_at_path(
    value: object,
    path: tuple[RawMemberStep, ...],
    _member_step_type: type[RawMemberStep] = RawMemberStep,
    _raw_object_type: type[RawSourceObject] = RawSourceObject,
) -> object:
    current = value
    if type(path) is not tuple or len(path) > 16:
        raise DiseaseCompileError("disease source path exceeds its bound")
    for step in path:
        if type(step) is not _member_step_type:
            raise DiseaseCompileError("disease source path is invalid")
        if type(current) is not _raw_object_type:
            raise DiseaseCompileError(
                "disease source path requires an ordered object"
            )
        if step.member_ordinal >= len(current.members):
            raise DiseaseCompileError("disease source path is out of range")
        member = current.members[step.member_ordinal]
        if member.key != step.raw_key:
            raise DiseaseCompileError("disease source path key disagrees")
        current = member.value
    return current


def _raw_ability_parts(
    raw: object,
    _value_impl: Callable[
        [object],
        tuple[
            str,
            tuple[str, ...],
            int | str | None,
            str,
            str,
        ],
    ] = _ability_parts_value,
) -> tuple[str, tuple[str, ...], int | str | None, str, str]:
    return _value_impl(raw)


_SOURCE_DEPENDENCY_PURPOSES = (
    ("disease-glossary", "Monster Core disease defaults and exposure identity"),
    ("affliction-format", "affliction field grammar"),
    ("affliction-save", "initial save and stage movement outcomes"),
    ("affliction-onset", "onset clock semantics"),
    ("affliction-maximum-duration", "maximum-duration termination"),
    ("affliction-stage", "ordered stage intervals and progression"),
    ("affliction-effect", "stage effect replacement"),
    ("multiple-exposures", "same-affliction exposure policy"),
    ("virulent", "two-save virulent resolution"),
    ("removing-afflictions", "recovery and recurrence"),
    ("treat-disease", "Medicine treatment"),
    ("cleanse-affliction", "magical cure and counteract"),
)

_RUNTIME_DEPENDENCY_SPECS = (
    ("campaign-clock", "campaign-time", "round/hour/day/week campaign clock"),
    ("exposure-identity", "affliction-state", "same-disease exposure identity"),
    ("initial-save", "affliction-state", "initial save and onset entry"),
    ("ordered-stage-progression", "affliction-state", "ordered stage transitions"),
    ("stage-effect-ownership", "effect-state", "replacement stage effects"),
    ("recovery-save", "affliction-state", "end-of-stage recovery save"),
    ("recovery-and-recurrence", "affliction-state", "recovery, recurrence, and cure state"),
    ("maximum-duration", "campaign-time", "maximum duration expiry"),
    ("treatment-and-cure", "affliction-state", "treatment bonuses and cure counteracts"),
    ("delivery-exposure", "exposure-state", "strike, ability, and relay exposure"),
    ("terminal-transition", "effect-state", "death, emergence, or transformation"),
)


def _bind_reviewed_api(
    *,
    direct_specs: tuple[_DirectSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    related_specs: tuple[_RelatedSpec, ...],
    near_specs: tuple[_NearMissSpec, ...],
    source_purposes: tuple[tuple[str, str], ...],
    runtime_specs: tuple[tuple[str, str, str], ...],
    adapter_type: type[SourceAuthorityAdapter],
    verified_rule_type: type[VerifiedRuleReceipt],
    raw_object_type: type[RawSourceObject],
    raw_array_type: type[RawSourceArray],
    duration_type: type[DiseaseDuration],
    save_type: type[DiseaseSave],
    stage_type: type[DiseaseStage],
    dependency_type: type[DiseaseDependency],
    compiled_type: type[CompiledDisease],
    near_type: type[DiseaseNearMiss],
    alias_link_type: type[DiseaseAliasLink],
    delivery_type: type[DiseaseDelivery],
    related_type: type[RelatedDiseaseUse],
    edge_type: type[DiseaseLinkEdge],
    corpus_type: type[LinkedDiseaseCorpus],
    direct_requirement_impl: Callable[[_DirectSpec], RuleRequirement],
    provider_requirement_impl: Callable[[_ProviderSpec], RuleRequirement],
    near_requirement_impl: Callable[[_NearMissSpec], RuleRequirement],
    same_requirement_impl: Callable[[RuleRequirement, RuleRequirement], bool],
    same_receipt_impl: Callable[[SourceReceipt, SourceReceipt], bool],
    ability_parts_impl: Callable[
        [VerifiedSourceSelection],
        tuple[str, tuple[str, ...], int | str | None, str, str],
    ],
    raw_ability_parts_impl: Callable[
        [object],
        tuple[str, tuple[str, ...], int | str | None, str, str],
    ],
    duration_impl: Callable[..., DiseaseDuration],
    save_impl: Callable[..., DiseaseSave | None],
    optional_duration_impl: Callable[..., DiseaseDuration | None],
    stages_impl: Callable[..., tuple[DiseaseStage, ...]],
    raw_at_path_impl: Callable[[object, tuple[RawMemberStep, ...]], object],
    path_impl: Callable[
        [tuple[tuple[str, int], ...]],
        tuple[RawMemberStep, ...],
    ],
    unique_member_impl: Callable[[RawSourceObject, str], object | None],
    normalized_impl: Callable[[str], str],
    plain_text_impl: Callable[[str], str],
    new_artifact_impl: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    canonical_json_impl: Callable[[object], bytes],
    raw_hash_impl: Callable[[object], str],
    sha256_impl: Callable[[bytes], Any],
) -> tuple[Callable[..., object], ...]:
    adapter_validate_selection = adapter_type.validate_selection
    adapter_resolve_rule = adapter_type.resolve_rule
    adapter_validate_rule = adapter_type.validate_rule
    adapter_reload = adapter_type.reload
    adapter_require_shared = adapter_type.require_shared_authority
    source_purpose_map = tuple(source_purposes)
    provider_ids = tuple(spec[0] for spec in provider_specs)
    affliction_provider_ids = provider_ids
    mechanic_provider_ids = ("disease-glossary",)
    monster_source_id = MONSTER_CORE_SOURCE_ID
    official_creature_count = OFFICIAL_CREATURE_CENSUS_COUNT
    max_stages = MAX_DISEASE_STAGES
    max_records = MAX_DISEASE_RECORDS
    max_links = MAX_DISEASE_LINKS
    max_link_depth = MAX_DISEASE_LINK_DEPTH
    max_link_id_bytes = MAX_DISEASE_LINK_ID_BYTES
    onset_pattern = _ONSET_RE
    maximum_duration_pattern = _MAX_DURATION_RE
    alias_pattern = _ALIAS_RE

    def _require_authority(value: object) -> SourceAuthorityAdapter:
        if type(value) is not adapter_type:
            raise TypeError(
                "diseases require an exact SourceAuthorityAdapter"
            )
        value.allowed_source_ids
        return value

    def _provider_spec(rule_id: str) -> _ProviderSpec:
        matches = tuple(
            spec for spec in provider_specs if spec[0] == rule_id
        )
        if len(matches) != 1:
            raise DiseaseCompileError(
                f"unknown reviewed disease provider: {rule_id}"
            )
        return matches[0]

    def _resolve_provider(
        authority: SourceAuthorityAdapter,
        rule_id: str,
    ) -> VerifiedRuleReceipt:
        return adapter_validate_rule(
            authority,
            adapter_resolve_rule(
                authority,
                provider_requirement_impl(_provider_spec(rule_id)),
            ),
        )

    def _validated_rule(
        authority: SourceAuthorityAdapter,
        value: object,
        label: str,
    ) -> VerifiedRuleReceipt:
        if type(value) is not verified_rule_type:
            raise TypeError(f"{label} must be an exact VerifiedRuleReceipt")
        try:
            for field_name in (
                "rule_id",
                "requirement",
                "selection",
                "receipt",
                "_capability",
            ):
                object.__getattribute__(value, field_name)
        except AttributeError as failure:
            raise DiseaseCompileError(f"{label} is uninitialized") from failure
        return adapter_validate_rule(authority, value)

    def _direct_rule_and_spec(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
    ) -> tuple[VerifiedRuleReceipt, _DirectSpec]:
        _require_authority(authority)
        consumer = adapter_validate_selection(
            authority,
            adapter_reload(authority, receipt),
        )
        candidates = tuple(
            spec
            for spec in direct_specs
            if spec[4] == consumer.address.locator
            and consumer.address.source_id == monster_source_id
        )
        matches = []
        for spec in candidates:
            rule = adapter_validate_rule(
                authority,
                adapter_resolve_rule(
                    authority,
                    direct_requirement_impl(spec),
                ),
            )
            if same_receipt_impl(rule.receipt, consumer.receipt):
                matches.append((rule, spec))
        if len(matches) != 1:
            raise DiseaseCompileError(
                "source is not one exact reviewed disease carrier"
            )
        rule, spec = matches[0]
        adapter_require_shared(authority, consumer, (rule,))
        return rule, spec

    def _near_rule_and_spec(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
    ) -> tuple[VerifiedRuleReceipt, _NearMissSpec]:
        _require_authority(authority)
        consumer = adapter_validate_selection(
            authority,
            adapter_reload(authority, receipt),
        )
        candidates = tuple(
            spec
            for spec in near_specs
            if spec[4] == consumer.address.locator
            and consumer.address.source_id == monster_source_id
        )
        matches = []
        for spec in candidates:
            rule = adapter_validate_rule(
                authority,
                adapter_resolve_rule(
                    authority,
                    near_requirement_impl(spec),
                ),
            )
            if same_receipt_impl(rule.receipt, consumer.receipt):
                matches.append((rule, spec))
        if len(matches) != 1:
            raise DiseaseCompileError(
                "source is not one exact reviewed disease near miss"
            )
        rule, spec = matches[0]
        adapter_require_shared(authority, consumer, (rule,))
        return rule, spec

    def _dependency(
        values: tuple[str, str, str, str | None],
    ) -> DiseaseDependency:
        return new_artifact_impl(
            dependency_type,
            (
                "dependency_id",
                "phase",
                "required_contract",
                "provider_rule_id",
            ),
            values,
        )  # type: ignore[return-value]

    def _dependencies(
        classification: str,
        providers: tuple[VerifiedRuleReceipt, ...],
        plain: str,
    ) -> tuple[DiseaseDependency, ...]:
        purpose = dict(source_purpose_map)
        result = [
            _dependency(
                (
                    f"source:{provider.rule_id}",
                    "source-link",
                    purpose[provider.rule_id],
                    provider.rule_id,
                )
            )
            for provider in providers
        ]
        if classification == "disease-mechanic":
            result.extend(
                _dependency(spec)
                for spec in (
                    (
                        "delivery-exposure",
                        "runtime",
                        "disease-tagged ability exposure",
                        None,
                    ),
                    (
                        "disease-state-integration",
                        "runtime",
                        "shared disease state and immunity resolution",
                        None,
                    ),
                )
            )
            return tuple(result)
        result.extend(
            _dependency((item[0], "runtime", item[2], None))
            for item in runtime_specs
        )
        if classification == "affliction-alias":
            result.append(
                _dependency(
                    (
                        "exact-alias-resolution",
                        "source-link",
                        "exact authored disease definition target",
                        None,
                    )
                )
            )
        if "virulent" in plain.casefold():
            result.append(
                _dependency(
                    (
                        "conditional-virulence",
                        "runtime",
                        "target-sensitive virulent save count",
                        "virulent",
                    )
                )
            )
        return tuple(result)

    def _provider_rules(
        authority: SourceAuthorityAdapter,
        consumer: VerifiedRuleReceipt,
        classification: str,
    ) -> tuple[VerifiedRuleReceipt, ...]:
        expected = (
            mechanic_provider_ids
            if classification == "disease-mechanic"
            else affliction_provider_ids
        )
        providers = tuple(
            _resolve_provider(authority, rule_id) for rule_id in expected
        )
        adapter_require_shared(
            authority,
            consumer.selection,
            (consumer, *providers),
        )
        return providers

    def _canonical_compiled(
        authority: SourceAuthorityAdapter,
        rule: VerifiedRuleReceipt,
        spec: _DirectSpec,
        providers: tuple[VerifiedRuleReceipt, ...],
    ) -> CompiledDisease:
        selection = adapter_validate_selection(authority, rule.selection)
        source_shape, traits, action, source_text, plain = (
            ability_parts_impl(selection)
        )
        if (
            source_shape != spec[10]
            or traits != spec[9]
            or "disease" not in traits
        ):
            raise DiseaseCompileError(
                "disease carrier shape or traits differ from review"
            )
        classification = spec[11]
        saving_throw = save_impl(
            plain,
            save_type,
            new_artifact_impl,
        )
        onset = optional_duration_impl(
            onset_pattern,
            plain,
            duration_type,
            new_artifact_impl,
        )
        maximum_duration = optional_duration_impl(
            maximum_duration_pattern,
            plain,
            duration_type,
            new_artifact_impl,
        )
        parsed_stages = stages_impl(
            plain,
            stage_type,
            duration_type,
            new_artifact_impl,
        )
        alias_target = None
        alias_dc = None
        alias_match = alias_pattern.search(plain)
        if classification == "affliction-definition":
            if saving_throw is None or not parsed_stages:
                raise DiseaseCompileError(
                    "disease definition lacks its save or ordered stages"
                )
            if alias_match is not None:
                raise DiseaseCompileError(
                    "disease definition unexpectedly contains an alias"
                )
        elif classification == "affliction-alias":
            if alias_match is None or parsed_stages or saving_throw is not None:
                raise DiseaseCompileError("disease alias grammar is invalid")
            alias_target = alias_match.group("target").strip().casefold()
            alias_dc = (
                None
                if alias_match.group("dc") is None
                else int(alias_match.group("dc"))
            )
        elif classification == "disease-mechanic":
            if parsed_stages or alias_match is not None:
                raise DiseaseCompileError(
                    "non-affliction disease mechanic has affliction grammar"
                )
        else:
            raise DiseaseCompileError("unknown disease classification")
        expected_ids = (
            mechanic_provider_ids
            if classification == "disease-mechanic"
            else affliction_provider_ids
        )
        if tuple(item.rule_id for item in providers) != expected_ids:
            raise DiseaseCompileError("disease provider order is invalid")
        return new_artifact_impl(
            compiled_type,
            (
                "record_id",
                "sequence",
                "creature_name",
                "ability_name",
                "locator",
                "classification",
                "source_shape",
                "traits",
                "action_cost",
                "source_text",
                "source_text_sha256",
                "saving_throw",
                "onset",
                "maximum_duration",
                "stages",
                "alias_target_name",
                "alias_dc_override",
                "consumer_rule",
                "provider_rules",
                "dependencies",
            ),
            (
                f"disease:{rule.rule_id}",
                spec[1],
                spec[2],
                spec[3],
                spec[4],
                classification,
                source_shape,
                traits,
                action,
                source_text,
                sha256_impl(source_text.encode("utf-8")).hexdigest(),
                saving_throw,
                onset,
                maximum_duration,
                parsed_stages,
                alias_target,
                alias_dc,
                rule,
                providers,
                _dependencies(classification, providers, plain),
            ),
        )  # type: ignore[return-value]

    def _duration_payload(value: DiseaseDuration) -> dict[str, object]:
        if type(value) is not duration_type:
            raise TypeError("disease duration must be exact")
        if (
            type(value.source_text) is not str
            or type(value.amount_kind) is not str
            or value.amount_kind not in {"fixed", "dice"}
            or type(value.unit) is not str
            or value.unit
            not in {"round", "minute", "hour", "day", "week"}
        ):
            raise DiseaseCompileError("stored disease duration is invalid")
        if value.amount_kind == "fixed":
            if (
                type(value.fixed_amount) is not int
                or value.fixed_amount <= 0
                or value.dice_count is not None
                or value.dice_sides is not None
                or value.dice_modifier is not None
            ):
                raise DiseaseCompileError(
                    "stored fixed disease duration is invalid"
                )
            amount: object = {
                "kind": "fixed",
                "value": value.fixed_amount,
            }
        else:
            if (
                type(value.dice_count) is not int
                or value.dice_count <= 0
                or type(value.dice_sides) is not int
                or value.dice_sides <= 0
                or type(value.dice_modifier) is not int
                or value.fixed_amount is not None
            ):
                raise DiseaseCompileError(
                    "stored dice disease duration is invalid"
                )
            amount = {
                "kind": "dice",
                "count": value.dice_count,
                "sides": value.dice_sides,
                "modifier": value.dice_modifier,
            }
        return {
            "sourceText": value.source_text,
            "amount": amount,
            "unit": value.unit,
        }

    def _save_payload(value: DiseaseSave) -> dict[str, object]:
        if (
            type(value) is not save_type
            or type(value.dc) is not int
            or value.dc <= 0
            or type(value.save_type) is not str
            or value.save_type not in {"fortitude", "reflex", "will"}
            or type(value.basic) is not bool
            or type(value.source_text) is not str
            or not value.source_text
        ):
            raise DiseaseCompileError("stored disease save is invalid")
        return {
            "dc": value.dc,
            "type": value.save_type,
            "basic": value.basic,
            "sourceText": value.source_text,
        }

    def _stage_payload(value: DiseaseStage) -> dict[str, object]:
        if (
            type(value) is not stage_type
            or type(value.number) is not int
            or value.number <= 0
            or type(value.source_text) is not str
            or not value.source_text
            or type(value.effect_text) is not str
            or not value.effect_text
            or type(value.terminal) is not bool
        ):
            raise DiseaseCompileError("stored disease stage is invalid")
        return {
            "number": value.number,
            "sourceText": value.source_text,
            "effectText": value.effect_text,
            "duration": (
                None
                if value.duration is None
                else _duration_payload(value.duration)
            ),
            "terminal": value.terminal,
        }

    def _dependency_payload(
        value: DiseaseDependency,
    ) -> dict[str, object]:
        if (
            type(value) is not dependency_type
            or type(value.dependency_id) is not str
            or not value.dependency_id
            or type(value.phase) is not str
            or value.phase not in {"source-link", "runtime"}
            or type(value.required_contract) is not str
            or not value.required_contract
            or (
                value.provider_rule_id is not None
                and type(value.provider_rule_id) is not str
            )
        ):
            raise DiseaseCompileError(
                "stored disease dependency is invalid"
            )
        return {
            "id": value.dependency_id,
            "phase": value.phase,
            "requiredContract": value.required_contract,
            "providerRuleId": value.provider_rule_id,
            "status": "deferred",
            "blocks": "registry-activation",
        }

    def _compiled_payload(value: CompiledDisease) -> dict[str, object]:
        if type(value) is not compiled_type:
            raise TypeError("compiled disease must be exact")
        if (
            type(value.traits) is not tuple
            or any(type(item) is not str for item in value.traits)
            or type(value.stages) is not tuple
            or len(value.stages) > max_stages
            or type(value.provider_rules) is not tuple
            or type(value.dependencies) is not tuple
        ):
            raise DiseaseCompileError(
                "compiled disease tuple fields are invalid"
            )
        if (
            type(value.record_id) is not str
            or not value.record_id
            or type(value.sequence) is not int
            or not 1 <= value.sequence <= official_creature_count
            or type(value.creature_name) is not str
            or not value.creature_name
            or type(value.ability_name) is not str
            or not value.ability_name
            or type(value.locator) is not str
            or not value.locator
            or type(value.source_text) is not str
            or not value.source_text
            or type(value.source_text_sha256) is not str
            or len(value.source_text_sha256) != 64
        ):
            raise DiseaseCompileError(
                "compiled disease scalar fields are invalid"
            )
        if tuple(
            stage.number for stage in value.stages
            if type(stage) is stage_type
        ) != tuple(range(1, len(value.stages) + 1)):
            raise DiseaseCompileError(
                "compiled disease stages are not canonical"
            )
        consumer = _validated_rule(
            value.consumer_rule._capability.adapter,
            value.consumer_rule,
            "disease consumer",
        )
        return {
            "family": "diseases",
            "mechanicType": "disease",
            "recordId": value.record_id,
            "sequence": value.sequence,
            "creature": value.creature_name,
            "ability": value.ability_name,
            "locator": value.locator,
            "classification": value.classification,
            "sourceShape": value.source_shape,
            "traits": list(value.traits),
            "actionCost": value.action_cost,
            "sourceText": value.source_text,
            "sourceTextSha256": value.source_text_sha256,
            "savingThrow": (
                None
                if value.saving_throw is None
                else _save_payload(value.saving_throw)
            ),
            "onset": (
                None
                if value.onset is None
                else _duration_payload(value.onset)
            ),
            "maximumDuration": (
                None
                if value.maximum_duration is None
                else _duration_payload(value.maximum_duration)
            ),
            "stages": [
                _stage_payload(stage) for stage in value.stages
            ],
            "alias": (
                None
                if value.alias_target_name is None
                else {
                    "targetCreature": value.alias_target_name,
                    "dcOverride": value.alias_dc_override,
                }
            ),
            "source": consumer.as_serialized(),
            "providerRules": [
                _validated_rule(
                    provider._capability.adapter,
                    provider,
                    "disease provider",
                ).as_serialized()
                for provider in value.provider_rules
            ],
            "deferredMechanics": [
                _dependency_payload(item) for item in value.dependencies
            ],
            "runtimeSupported": False,
            "registryStatus": "unregistered",
            "activationStatus": "deferred",
        }

    def _validate_compiled(
        authority: SourceAuthorityAdapter,
        value: CompiledDisease,
    ) -> dict[str, object]:
        _require_authority(authority)
        if type(value) is not compiled_type:
            raise TypeError("compiled disease must be exact")
        consumer = _validated_rule(
            authority,
            value.consumer_rule,
            "disease consumer",
        )
        matches = tuple(
            spec for spec in direct_specs if spec[0] == consumer.rule_id
        )
        if len(matches) != 1:
            raise DiseaseCompileError(
                "compiled disease consumer is outside the census"
            )
        spec = matches[0]
        if not same_requirement_impl(
            consumer.requirement,
            direct_requirement_impl(spec),
        ):
            raise DiseaseCompileError(
                "compiled disease retained the wrong consumer requirement"
            )
        adapter_validate_selection(authority, consumer.selection)
        expected_ids = (
            mechanic_provider_ids
            if spec[11] == "disease-mechanic"
            else affliction_provider_ids
        )
        if (
            type(value.provider_rules) is not tuple
            or len(value.provider_rules) != len(expected_ids)
        ):
            raise DiseaseCompileError(
                "compiled disease provider count is invalid"
            )
        providers = []
        for expected_id, provider in zip(
            expected_ids,
            value.provider_rules,
            strict=True,
        ):
            verified = _validated_rule(
                authority,
                provider,
                "disease provider",
            )
            if (
                verified.rule_id != expected_id
                or not same_requirement_impl(
                    verified.requirement,
                    provider_requirement_impl(
                        _provider_spec(expected_id)
                    ),
                )
            ):
                raise DiseaseCompileError(
                    "compiled disease retained the wrong provider"
                )
            providers.append(verified)
        adapter_require_shared(
            authority,
            consumer.selection,
            (consumer, *providers),
        )
        canonical = _canonical_compiled(
            authority,
            consumer,
            spec,
            tuple(providers),
        )
        supplied_payload = _compiled_payload(value)
        canonical_payload = _compiled_payload(canonical)
        if canonical_json_impl(supplied_payload) != canonical_json_impl(
            canonical_payload
        ):
            raise DiseaseCompileError(
                "compiled disease differs from current authority"
            )
        return supplied_payload

    def _canonical_near(
        authority: SourceAuthorityAdapter,
        rule: VerifiedRuleReceipt,
        spec: _NearMissSpec,
    ) -> DiseaseNearMiss:
        selection = adapter_validate_selection(authority, rule.selection)
        source_shape, traits, _action, source_text, plain = (
            ability_parts_impl(selection)
        )
        if (
            source_shape != spec[9]
            or traits != spec[8]
            or "disease" in traits
            or spec[10]
            not in {"poison-affliction", "curse-affliction"}
        ):
            raise DiseaseCompileError(
                "disease near-miss shape or traits differ from review"
            )
        saving_throw = save_impl(
            plain,
            save_type,
            new_artifact_impl,
        )
        parsed_stages = stages_impl(
            plain,
            stage_type,
            duration_type,
            new_artifact_impl,
        )
        if saving_throw is None or not parsed_stages:
            raise DiseaseCompileError(
                "disease near miss lacks affliction grammar"
            )
        return new_artifact_impl(
            near_type,
            (
                "record_id",
                "sequence",
                "creature_name",
                "ability_name",
                "locator",
                "classification",
                "source_shape",
                "traits",
                "source_text",
                "source_text_sha256",
                "saving_throw",
                "onset",
                "maximum_duration",
                "stages",
                "consumer_rule",
            ),
            (
                f"near-miss:{rule.rule_id}",
                spec[1],
                spec[2],
                spec[3],
                spec[4],
                spec[10],
                source_shape,
                traits,
                source_text,
                sha256_impl(source_text.encode("utf-8")).hexdigest(),
                saving_throw,
                optional_duration_impl(
                    onset_pattern,
                    plain,
                    duration_type,
                    new_artifact_impl,
                ),
                optional_duration_impl(
                    maximum_duration_pattern,
                    plain,
                    duration_type,
                    new_artifact_impl,
                ),
                parsed_stages,
                rule,
            ),
        )  # type: ignore[return-value]

    def _near_payload(value: DiseaseNearMiss) -> dict[str, object]:
        if (
            type(value) is not near_type
            or type(value.traits) is not tuple
            or any(type(item) is not str for item in value.traits)
            or type(value.stages) is not tuple
            or not value.stages
            or len(value.stages) > max_stages
            or type(value.record_id) is not str
            or type(value.sequence) is not int
            or type(value.creature_name) is not str
            or type(value.ability_name) is not str
            or type(value.locator) is not str
            or type(value.source_text) is not str
            or type(value.source_text_sha256) is not str
        ):
            raise DiseaseCompileError("stored disease near miss is invalid")
        return {
            "family": "diseases",
            "relationship": "excluded-affliction-near-miss",
            "recordId": value.record_id,
            "sequence": value.sequence,
            "creature": value.creature_name,
            "ability": value.ability_name,
            "locator": value.locator,
            "classification": value.classification,
            "sourceShape": value.source_shape,
            "traits": list(value.traits),
            "sourceText": value.source_text,
            "sourceTextSha256": value.source_text_sha256,
            "savingThrow": _save_payload(value.saving_throw),
            "onset": (
                None
                if value.onset is None
                else _duration_payload(value.onset)
            ),
            "maximumDuration": (
                None
                if value.maximum_duration is None
                else _duration_payload(value.maximum_duration)
            ),
            "stages": [
                _stage_payload(stage) for stage in value.stages
            ],
            "source": value.consumer_rule.as_serialized(),
            "providerRules": [],
            "runtimeSupported": False,
            "registryStatus": "unregistered",
            "activationStatus": "excluded-other-family",
        }

    def _validate_near(
        authority: SourceAuthorityAdapter,
        value: DiseaseNearMiss,
    ) -> dict[str, object]:
        _require_authority(authority)
        if type(value) is not near_type:
            raise TypeError("disease near miss must be exact")
        consumer = _validated_rule(
            authority,
            value.consumer_rule,
            "disease near-miss consumer",
        )
        matches = tuple(
            spec for spec in near_specs if spec[0] == consumer.rule_id
        )
        if len(matches) != 1:
            raise DiseaseCompileError(
                "disease near miss is outside the reviewed census"
            )
        spec = matches[0]
        if not same_requirement_impl(
            consumer.requirement,
            near_requirement_impl(spec),
        ):
            raise DiseaseCompileError(
                "disease near miss retained the wrong requirement"
            )
        adapter_require_shared(
            authority,
            consumer.selection,
            (consumer,),
        )
        canonical = _canonical_near(authority, consumer, spec)
        supplied_payload = _near_payload(value)
        if canonical_json_impl(supplied_payload) != canonical_json_impl(
            _near_payload(canonical)
        ):
            raise DiseaseCompileError(
                "disease near miss differs from current authority"
            )
        return supplied_payload

    def _alias_links(
        records: tuple[CompiledDisease, ...],
    ) -> tuple[DiseaseAliasLink, ...]:
        definitions = tuple(
            item
            for item in records
            if item.classification == "affliction-definition"
        )
        result = []
        for alias in records:
            if alias.classification != "affliction-alias":
                continue
            matches = tuple(
                item
                for item in definitions
                if item.creature_name.casefold()
                == alias.alias_target_name
                and item.ability_name == alias.ability_name
            )
            if len(matches) != 1:
                raise DiseaseLinkError(
                    "disease alias target is missing or ambiguous"
                )
            definition = matches[0]
            if definition.saving_throw is None:
                raise DiseaseLinkError(
                    "disease alias target lacks a saving throw"
                )
            result.append(
                new_artifact_impl(
                    alias_link_type,
                    (
                        "alias_record_id",
                        "definition_record_id",
                        "resolved_dc",
                    ),
                    (
                        alias.record_id,
                        definition.record_id,
                        (
                            alias.alias_dc_override
                            if alias.alias_dc_override is not None
                            else definition.saving_throw.dc
                        ),
                    ),
                )
            )
        return tuple(result)  # type: ignore[return-value]

    def _resolved_definition_id(
        record: CompiledDisease,
        alias_links: tuple[DiseaseAliasLink, ...],
    ) -> str:
        if record.classification == "affliction-definition":
            return record.record_id
        if record.classification != "affliction-alias":
            raise DiseaseLinkError(
                "disease delivery refers to a non-affliction mechanic"
            )
        matches = tuple(
            item
            for item in alias_links
            if item.alias_record_id == record.record_id
        )
        if len(matches) != 1:
            raise DiseaseLinkError("disease alias link is missing")
        return matches[0].definition_record_id

    def _delivery_mode(text: str, source_name: str) -> str:
        lowered = text.casefold()
        if (
            "entering the aura" in lowered
            and "starting its turn" in lowered
        ):
            return "enter-or-start-turn-aura-exposure"
        if "basic reflex" in lowered:
            return "failed-basic-reflex-save-exposure"
        if "paralyzed or unconscious" in lowered:
            return "single-action-adjacent-incapacitated-target-exposure"
        if "end of each of its turns" in lowered:
            return "end-of-each-turn-while-immobilized-exposure"
        if "touches" in lowered or "contact" in lowered:
            return "touch-or-contact-exposure"
        if "adjacent" in lowered and "expos" in lowered:
            return "adjacent-area-exposure"
        if "strike" in lowered:
            return "single-action-restricted-strike-exposure"
        if source_name == "Scratch":
            return "adjacent-area-exposure"
        return "named-ability-exposure"

    def _deliveries(
        records: tuple[CompiledDisease, ...],
        alias_links: tuple[DiseaseAliasLink, ...],
    ) -> tuple[DiseaseDelivery, ...]:
        by_block: dict[
            tuple[str, str, str], list[CompiledDisease]
        ] = {}
        for record in records:
            if record.classification == "disease-mechanic":
                continue
            receipt = record.consumer_rule.receipt
            key = (
                receipt.address.locator,
                receipt.block_sha256,
                record.creature_name,
            )
            by_block.setdefault(key, []).append(record)
        result = []
        seen: set[tuple[str, tuple[str, ...], str | None]] = set()
        delivery_sequence = 0
        for block_records in by_block.values():
            parent = block_records[0]
            raw_block = parent.consumer_rule.selection.carrier.raw_block
            if type(raw_block) is not raw_object_type:
                raise DiseaseLinkError(
                    "disease delivery carrier must be an object"
                )
            direct_keys = {
                item.consumer_rule.selection.raw_member.key
                for item in block_records
                if item.consumer_rule.selection.raw_member is not None
            }
            for member_ordinal, member in enumerate(raw_block.members):
                if member.key in {"Melee", "Ranged"}:
                    if type(member.value) is not raw_array_type:
                        raise DiseaseLinkError(
                            "disease Strike source must be an array"
                        )
                    for item_ordinal, raw_strike in enumerate(
                        member.value.items
                    ):
                        if type(raw_strike) is not raw_object_type:
                            raise DiseaseLinkError(
                                "disease Strike must be an object"
                            )
                        name = unique_member_impl(raw_strike, "Name")
                        damage = unique_member_impl(raw_strike, "Damage")
                        if type(name) is not str or type(damage) is not str:
                            continue
                        effects = unique_member_impl(
                            raw_strike,
                            "Effects",
                        )
                        if effects is None:
                            effects_text = ""
                        elif type(effects) is str:
                            effects_text = effects
                        elif type(effects) is raw_array_type and all(
                            type(item) is str for item in effects.items
                        ):
                            effects_text = " ".join(effects.items)
                        else:
                            raise DiseaseLinkError(
                                "disease Strike Effects are malformed"
                            )
                        normalized_damage = normalized_impl(
                            plain_text_impl(
                                f"{damage} {effects_text}".strip()
                            )
                        )
                        matches = tuple(
                            record
                            for record in block_records
                            if normalized_impl(record.ability_name)
                            in normalized_damage
                        )
                        if len(matches) > 1:
                            raise DiseaseLinkError(
                                "Strike disease rider is ambiguous"
                            )
                        if not matches:
                            continue
                        declared = matches[0]
                        path = (
                            f"{member.key}@{member_ordinal}",
                            f"#{item_ordinal}",
                        )
                        identity = (
                            parent.creature_name,
                            path,
                            declared.record_id,
                        )
                        if identity in seen:
                            raise DiseaseLinkError(
                                "duplicate disease delivery source"
                            )
                        seen.add(identity)
                        delivery_sequence += 1
                        result.append(
                            new_artifact_impl(
                                delivery_type,
                                (
                                    "delivery_id",
                                    "creature_name",
                                    "source_name",
                                    "delivery_kind",
                                    "delivery_mode",
                                    "declared_record_id",
                                    "resolved_definition_id",
                                    "source_path",
                                    "source_sha256",
                                    "parent_consumer_rule_id",
                                ),
                                (
                                    f"disease-delivery:{delivery_sequence:03d}",
                                    parent.creature_name,
                                    name,
                                    "strike-rider",
                                    "strike-hit-exposure",
                                    declared.record_id,
                                    _resolved_definition_id(
                                        declared,
                                        alias_links,
                                    ),
                                    path,
                                    raw_hash_impl(raw_strike),
                                    parent.consumer_rule.rule_id,
                                ),
                            )
                        )
                if not member.key.startswith("!."):
                    continue
                source_name = member.key[2:]
                try:
                    (
                        _shape,
                        member_traits,
                        _action,
                        source_text,
                        plain,
                    ) = raw_ability_parts_impl(member.value)
                except DiseaseCompileError:
                    if type(member.value) is not raw_object_type:
                        continue
                    effect = unique_member_impl(
                        member.value,
                        "Effect",
                    )
                    if type(effect) is not str:
                        continue
                    source_text = effect
                    plain = plain_text_impl(effect)
                    traits_value = unique_member_impl(
                        member.value,
                        "Traits",
                    )
                    if type(traits_value) is raw_array_type and all(
                        type(item) is str
                        for item in traits_value.items
                    ):
                        member_traits = tuple(
                            item.casefold()
                            for item in traits_value.items
                        )
                    else:
                        member_traits = ()
                normalized_text = normalized_impl(plain)
                generic_relay = (
                    "aura" in member_traits
                    and "disease" in member_traits
                    and (
                        "all adjacent creatures are exposed to the same disease"
                        in plain.casefold()
                    )
                )
                if generic_relay:
                    path = (f"{member.key}@{member_ordinal}",)
                    identity = (parent.creature_name, path, None)
                    if identity not in seen:
                        seen.add(identity)
                        delivery_sequence += 1
                        result.append(
                            new_artifact_impl(
                                delivery_type,
                                (
                                    "delivery_id",
                                    "creature_name",
                                    "source_name",
                                    "delivery_kind",
                                    "delivery_mode",
                                    "declared_record_id",
                                    "resolved_definition_id",
                                    "source_path",
                                    "source_sha256",
                                    "parent_consumer_rule_id",
                                ),
                                (
                                    f"disease-delivery:{delivery_sequence:03d}",
                                    parent.creature_name,
                                    source_name,
                                    "generic-disease-relay",
                                    "adjacent-creatures-same-disease-same-dc",
                                    None,
                                    None,
                                    path,
                                    raw_hash_impl(member.value),
                                    parent.consumer_rule.rule_id,
                                ),
                            )
                        )
                    continue
                if "expos" not in plain.casefold():
                    continue
                matches = tuple(
                    record
                    for record in block_records
                    if normalized_impl(record.ability_name)
                    in normalized_text
                    and member.key not in direct_keys
                )
                # Spore Cloud is itself a disease-tagged direct mechanic but
                # delivers the separately named Spore Blight affliction.
                if not matches:
                    matches = tuple(
                        record
                        for record in block_records
                        if normalized_impl(record.ability_name)
                        in normalized_text
                        and normalized_impl(record.ability_name)
                        != normalized_impl(source_name)
                    )
                if len(matches) > 1:
                    raise DiseaseLinkError(
                        "named disease delivery is ambiguous"
                    )
                if not matches:
                    continue
                declared = matches[0]
                path = (f"{member.key}@{member_ordinal}",)
                identity = (
                    parent.creature_name,
                    path,
                    declared.record_id,
                )
                if identity in seen:
                    continue
                seen.add(identity)
                delivery_sequence += 1
                result.append(
                    new_artifact_impl(
                        delivery_type,
                        (
                            "delivery_id",
                            "creature_name",
                            "source_name",
                            "delivery_kind",
                            "delivery_mode",
                            "declared_record_id",
                            "resolved_definition_id",
                            "source_path",
                            "source_sha256",
                            "parent_consumer_rule_id",
                        ),
                        (
                            f"disease-delivery:{delivery_sequence:03d}",
                            parent.creature_name,
                            source_name,
                            "named-ability-exposure",
                            _delivery_mode(plain, source_name),
                            declared.record_id,
                            _resolved_definition_id(
                                declared,
                                alias_links,
                            ),
                            path,
                            raw_hash_impl(member.value),
                            parent.consumer_rule.rule_id,
                        ),
                    )
                )
        return tuple(result)  # type: ignore[return-value]

    def _related_uses(
        records: tuple[CompiledDisease, ...],
    ) -> tuple[RelatedDiseaseUse, ...]:
        by_rule = {
            item.consumer_rule.rule_id: item for item in records
        }
        result = []
        for index, spec in enumerate(related_specs, start=1):
            try:
                parent = by_rule[spec[0]]
            except KeyError as failure:
                raise DiseaseLinkError(
                    "related disease parent is missing"
                ) from failure
            raw = raw_at_path_impl(
                parent.consumer_rule.selection.carrier.raw_block,
                path_impl(spec[3]),
            )
            if raw_hash_impl(raw) != spec[4]:
                raise DiseaseLinkError(
                    "related disease source differs from review"
                )
            shape, traits, _action, source_text, _plain = (
                raw_ability_parts_impl(raw)
            )
            if shape != spec[7] or traits != spec[6]:
                raise DiseaseLinkError(
                    "related disease source shape differs from review"
                )
            path = tuple(
                f"{step.raw_key}@{step.member_ordinal}"
                for step in path_impl(spec[3])
            )
            result.append(
                new_artifact_impl(
                    related_type,
                    (
                        "related_id",
                        "creature_name",
                        "ability_name",
                        "relationship",
                        "source_shape",
                        "traits",
                        "source_text",
                        "source_sha256",
                        "source_path",
                        "parent_consumer_rule_id",
                    ),
                    (
                        f"disease-related:{index:03d}",
                        spec[1],
                        spec[2],
                        spec[5],
                        shape,
                        traits,
                        source_text,
                        spec[4],
                        path,
                        spec[0],
                    ),
                )
            )
        return tuple(result)  # type: ignore[return-value]

    def _alias_payload(value: DiseaseAliasLink) -> dict[str, object]:
        if (
            type(value) is not alias_link_type
            or type(value.alias_record_id) is not str
            or not value.alias_record_id
            or type(value.definition_record_id) is not str
            or not value.definition_record_id
            or type(value.resolved_dc) is not int
            or value.resolved_dc <= 0
        ):
            raise DiseaseLinkError("stored disease alias link is invalid")
        return {
            "aliasRecordId": value.alias_record_id,
            "definitionRecordId": value.definition_record_id,
            "resolvedDc": value.resolved_dc,
        }

    def _delivery_payload(value: DiseaseDelivery) -> dict[str, object]:
        if (
            type(value) is not delivery_type
            or type(value.delivery_id) is not str
            or not value.delivery_id
            or type(value.creature_name) is not str
            or type(value.source_name) is not str
            or type(value.delivery_kind) is not str
            or value.delivery_kind
            not in {
                "strike-rider",
                "named-ability-exposure",
                "generic-disease-relay",
            }
            or type(value.delivery_mode) is not str
            or type(value.source_path) is not tuple
            or not value.source_path
            or any(type(item) is not str for item in value.source_path)
            or type(value.source_sha256) is not str
            or len(value.source_sha256) != 64
            or type(value.parent_consumer_rule_id) is not str
        ):
            raise DiseaseLinkError("stored disease delivery is invalid")
        if value.delivery_kind == "generic-disease-relay":
            if (
                value.declared_record_id is not None
                or value.resolved_definition_id is not None
            ):
                raise DiseaseLinkError(
                    "generic disease relay cannot bind one disease"
                )
        elif (
            type(value.declared_record_id) is not str
            or type(value.resolved_definition_id) is not str
        ):
            raise DiseaseLinkError(
                "specific disease delivery lacks its definition binding"
            )
        return {
            "deliveryId": value.delivery_id,
            "creature": value.creature_name,
            "sourceName": value.source_name,
            "kind": value.delivery_kind,
            "mode": value.delivery_mode,
            "declaredRecordId": value.declared_record_id,
            "resolvedDefinitionId": value.resolved_definition_id,
            "sourcePath": list(value.source_path),
            "sourceSha256": value.source_sha256,
            "parentConsumerRuleId": value.parent_consumer_rule_id,
            "deferredMechanic": {
                "id": "delivery-exposure",
                "status": "deferred",
                "sameDiseaseExposurePolicy": (
                    "new-exposure-has-no-effect"
                ),
                "notPoisonProgression": True,
            },
            "runtimeSupported": False,
        }

    def _related_payload(value: RelatedDiseaseUse) -> dict[str, object]:
        if (
            type(value) is not related_type
            or type(value.related_id) is not str
            or type(value.creature_name) is not str
            or type(value.ability_name) is not str
            or type(value.relationship) is not str
            or value.relationship
            not in {
                "disease-observer",
                "stage-accelerator",
                "named-delivery",
            }
            or type(value.source_shape) is not str
            or type(value.traits) is not tuple
            or any(type(item) is not str for item in value.traits)
            or type(value.source_text) is not str
            or type(value.source_sha256) is not str
            or len(value.source_sha256) != 64
            or type(value.source_path) is not tuple
            or any(type(item) is not str for item in value.source_path)
            or type(value.parent_consumer_rule_id) is not str
        ):
            raise DiseaseLinkError(
                "stored related disease use is invalid"
            )
        return {
            "relatedId": value.related_id,
            "creature": value.creature_name,
            "ability": value.ability_name,
            "relationship": value.relationship,
            "sourceShape": value.source_shape,
            "traits": list(value.traits),
            "sourceText": value.source_text,
            "sourceSha256": value.source_sha256,
            "sourcePath": list(value.source_path),
            "parentConsumerRuleId": value.parent_consumer_rule_id,
            "runtimeSupported": False,
            "registryStatus": "unregistered",
        }

    def _corpus_payload(value: LinkedDiseaseCorpus) -> dict[str, object]:
        if (
            type(value) is not corpus_type
            or type(value.records) is not tuple
            or len(value.records) > max_records
            or type(value.near_misses) is not tuple
            or len(value.near_misses) > max_records
            or type(value.alias_links) is not tuple
            or len(value.alias_links) > max_links
            or type(value.deliveries) is not tuple
            or len(value.deliveries) > max_links
            or type(value.related_uses) is not tuple
            or len(value.related_uses) > max_links
        ):
            raise DiseaseLinkError("stored disease corpus is invalid")
        return {
            "family": "diseases",
            "officialCreatureCensus": official_creature_count,
            "records": [
                _compiled_payload(item) for item in value.records
            ],
            "nearMisses": [
                _near_payload(item) for item in value.near_misses
            ],
            "aliasLinks": [
                _alias_payload(item) for item in value.alias_links
            ],
            "deliveries": [
                _delivery_payload(item) for item in value.deliveries
            ],
            "relatedUses": [
                _related_payload(item) for item in value.related_uses
            ],
            "migrationSeam": {
                "campaignClock": "deferred",
                "sameDiseaseExposure": (
                    "new-exposure-has-no-effect"
                ),
                "recoveryAndRecurrence": "deferred",
                "treatmentAndCure": "deferred",
                "notPoisonProgression": True,
            },
            "runtimeSupported": False,
            "registryStatus": "unregistered",
            "activationStatus": "deferred",
        }

    def _canonical_corpus(
        records: tuple[CompiledDisease, ...],
        near_misses: tuple[DiseaseNearMiss, ...],
    ) -> LinkedDiseaseCorpus:
        aliases = _alias_links(records)
        return new_artifact_impl(
            corpus_type,
            (
                "records",
                "near_misses",
                "alias_links",
                "deliveries",
                "related_uses",
            ),
            (
                records,
                near_misses,
                aliases,
                _deliveries(records, aliases),
                _related_uses(records),
            ),
        )  # type: ignore[return-value]

    def _validate_corpus(
        authority: SourceAuthorityAdapter,
        value: LinkedDiseaseCorpus,
    ) -> dict[str, object]:
        _require_authority(authority)
        if type(value) is not corpus_type:
            raise TypeError("linked disease corpus must be exact")
        if (
            type(value.records) is not tuple
            or len(value.records) != len(direct_specs)
            or type(value.near_misses) is not tuple
            or len(value.near_misses) != len(near_specs)
        ):
            raise DiseaseLinkError(
                "linked disease corpus has an incomplete census"
            )
        for record in value.records:
            _validate_compiled(authority, record)
        for near in value.near_misses:
            _validate_near(authority, near)
        if tuple(
            item.consumer_rule.rule_id for item in value.records
        ) != tuple(spec[0] for spec in direct_specs):
            raise DiseaseLinkError(
                "linked disease record order differs from review"
            )
        if tuple(
            item.consumer_rule.rule_id for item in value.near_misses
        ) != tuple(spec[0] for spec in near_specs):
            raise DiseaseLinkError(
                "linked near-miss order differs from review"
            )
        canonical = _canonical_corpus(
            value.records,
            value.near_misses,
        )
        supplied_payload = _corpus_payload(value)
        if canonical_json_impl(supplied_payload) != canonical_json_impl(
            _corpus_payload(canonical)
        ):
            raise DiseaseLinkError(
                "linked disease corpus differs from current authority"
            )
        return supplied_payload

    def disease_consumer_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(direct_requirement_impl(spec) for spec in direct_specs)

    def disease_provider_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(
            provider_requirement_impl(spec) for spec in provider_specs
        )

    def disease_near_miss_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(near_requirement_impl(spec) for spec in near_specs)

    def compile_disease(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
    ) -> CompiledDisease:
        rule, spec = _direct_rule_and_spec(authority, receipt)
        providers = _provider_rules(authority, rule, spec[11])
        return _canonical_compiled(
            authority,
            rule,
            spec,
            providers,
        )

    def compile_disease_census(
        authority: SourceAuthorityAdapter,
    ) -> tuple[CompiledDisease, ...]:
        _require_authority(authority)
        return tuple(
            compile_disease(
                authority,
                adapter_resolve_rule(
                    authority,
                    direct_requirement_impl(spec),
                ).receipt,
            )
            for spec in direct_specs
        )

    def compile_disease_near_miss(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
    ) -> DiseaseNearMiss:
        rule, spec = _near_rule_and_spec(authority, receipt)
        return _canonical_near(authority, rule, spec)

    def compile_disease_near_miss_census(
        authority: SourceAuthorityAdapter,
    ) -> tuple[DiseaseNearMiss, ...]:
        _require_authority(authority)
        return tuple(
            compile_disease_near_miss(
                authority,
                adapter_resolve_rule(
                    authority,
                    near_requirement_impl(spec),
                ).receipt,
            )
            for spec in near_specs
        )

    def validate_compiled_disease(
        authority: SourceAuthorityAdapter,
        value: CompiledDisease,
    ) -> CompiledDisease:
        _validate_compiled(authority, value)
        return value

    def validate_disease_near_miss(
        authority: SourceAuthorityAdapter,
        value: DiseaseNearMiss,
    ) -> DiseaseNearMiss:
        _validate_near(authority, value)
        return value

    def link_disease_corpus(
        authority: SourceAuthorityAdapter,
        records: tuple[CompiledDisease, ...],
        near_misses: tuple[DiseaseNearMiss, ...],
    ) -> LinkedDiseaseCorpus:
        _require_authority(authority)
        if (
            type(records) is not tuple
            or type(near_misses) is not tuple
        ):
            raise TypeError("disease linker inputs must be exact tuples")
        if (
            len(records) != len(direct_specs)
            or len(near_misses) != len(near_specs)
        ):
            raise DiseaseLinkError(
                "disease linker inputs must contain the full census"
            )
        for record in records:
            _validate_compiled(authority, record)
        for near in near_misses:
            _validate_near(authority, near)
        if tuple(
            item.consumer_rule.rule_id for item in records
        ) != tuple(spec[0] for spec in direct_specs):
            raise DiseaseLinkError(
                "disease records are not in reviewed order"
            )
        if tuple(
            item.consumer_rule.rule_id for item in near_misses
        ) != tuple(spec[0] for spec in near_specs):
            raise DiseaseLinkError(
                "disease near misses are not in reviewed order"
            )
        return _canonical_corpus(records, near_misses)

    def validate_linked_disease_corpus(
        authority: SourceAuthorityAdapter,
        value: LinkedDiseaseCorpus,
    ) -> LinkedDiseaseCorpus:
        _validate_corpus(authority, value)
        return value

    def validate_disease_link_graph(
        edges: tuple[DiseaseLinkEdge, ...],
    ) -> None:
        if type(edges) is not tuple:
            raise TypeError("disease link graph must be an exact tuple")
        if len(edges) > max_links:
            raise TypeError("disease link graph exceeds its width bound")
        mapping: dict[str, str] = {}
        for edge in edges:
            if type(edge) is not edge_type:
                raise TypeError("disease link edge must be exact")
            if (
                type(edge.consumer_id) is not str
                or not edge.consumer_id
                or edge.consumer_id != edge.consumer_id.strip()
                or len(edge.consumer_id.encode("utf-8"))
                > max_link_id_bytes
                or type(edge.producer_id) is not str
                or not edge.producer_id
                or edge.producer_id != edge.producer_id.strip()
                or len(edge.producer_id.encode("utf-8"))
                > max_link_id_bytes
            ):
                raise DiseaseLinkError(
                    "disease link graph contains an invalid endpoint"
                )
            if edge.consumer_id in mapping:
                raise DiseaseLinkError(
                    "disease link graph has an ambiguous consumer"
                )
            mapping[edge.consumer_id] = edge.producer_id
        for origin in mapping:
            seen = set()
            current = origin
            depth = 0
            while current in mapping:
                if current in seen:
                    raise DiseaseLinkError(
                        "disease link graph contains a cycle"
                    )
                seen.add(current)
                depth += 1
                if depth > max_link_depth:
                    raise DiseaseLinkError(
                        "disease link graph exceeds its depth bound"
                    )
                current = mapping[current]

    def compiled_as_serialized(
        self: CompiledDisease,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, object]:
        return _validate_compiled(authority, self)

    def near_as_serialized(
        self: DiseaseNearMiss,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, object]:
        return _validate_near(authority, self)

    def corpus_as_serialized(
        self: LinkedDiseaseCorpus,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, object]:
        return _validate_corpus(authority, self)

    return (
        disease_consumer_requirements,
        disease_provider_requirements,
        disease_near_miss_requirements,
        compile_disease,
        compile_disease_census,
        compile_disease_near_miss,
        compile_disease_near_miss_census,
        validate_compiled_disease,
        validate_disease_near_miss,
        link_disease_corpus,
        validate_linked_disease_corpus,
        validate_disease_link_graph,
        compiled_as_serialized,
        near_as_serialized,
        corpus_as_serialized,
    )


(
    disease_consumer_requirements,
    disease_provider_requirements,
    disease_near_miss_requirements,
    compile_disease,
    compile_disease_census,
    compile_disease_near_miss,
    compile_disease_near_miss_census,
    validate_compiled_disease,
    validate_disease_near_miss,
    link_disease_corpus,
    validate_linked_disease_corpus,
    validate_disease_link_graph,
    _compiled_as_serialized,
    _near_as_serialized,
    _corpus_as_serialized,
) = _bind_reviewed_api(
    direct_specs=_DIRECT_SPECS,
    provider_specs=_PROVIDER_SPECS,
    related_specs=_RELATED_SPECS,
    near_specs=_NEAR_MISS_SPECS,
    source_purposes=_SOURCE_DEPENDENCY_PURPOSES,
    runtime_specs=_RUNTIME_DEPENDENCY_SPECS,
    adapter_type=SourceAuthorityAdapter,
    verified_rule_type=VerifiedRuleReceipt,
    raw_object_type=RawSourceObject,
    raw_array_type=RawSourceArray,
    duration_type=DiseaseDuration,
    save_type=DiseaseSave,
    stage_type=DiseaseStage,
    dependency_type=DiseaseDependency,
    compiled_type=CompiledDisease,
    near_type=DiseaseNearMiss,
    alias_link_type=DiseaseAliasLink,
    delivery_type=DiseaseDelivery,
    related_type=RelatedDiseaseUse,
    edge_type=DiseaseLinkEdge,
    corpus_type=LinkedDiseaseCorpus,
    direct_requirement_impl=_direct_requirement,
    provider_requirement_impl=_provider_requirement,
    near_requirement_impl=_near_miss_requirement,
    same_requirement_impl=_same_requirement,
    same_receipt_impl=_same_receipt,
    ability_parts_impl=_ability_parts,
    raw_ability_parts_impl=_raw_ability_parts,
    duration_impl=_duration,
    save_impl=_save,
    optional_duration_impl=_optional_duration,
    stages_impl=_stages,
    raw_at_path_impl=_raw_at_path,
    path_impl=_path_from_spec,
    unique_member_impl=_unique_member,
    normalized_impl=_normalized,
    plain_text_impl=_plain_text,
    new_artifact_impl=_new_artifact,
    canonical_json_impl=canonical_json_bytes,
    raw_hash_impl=raw_source_sha256,
    sha256_impl=hashlib.sha256,
)

type.__setattr__(
    CompiledDisease,
    "as_serialized",
    _compiled_as_serialized,
)
type.__setattr__(
    DiseaseNearMiss,
    "as_serialized",
    _near_as_serialized,
)
type.__setattr__(
    LinkedDiseaseCorpus,
    "as_serialized",
    _corpus_as_serialized,
)

for _artifact_type in (
    _NoTransfer,
    DiseaseDuration,
    DiseaseSave,
    DiseaseStage,
    DiseaseDependency,
    CompiledDisease,
    DiseaseNearMiss,
    DiseaseAliasLink,
    DiseaseDelivery,
    RelatedDiseaseUse,
    DiseaseLinkEdge,
    LinkedDiseaseCorpus,
):
    _seal_type(_artifact_type)


__all__ = [
    "COMPILED_CENSUS_SHA256",
    "CONSUMER_REQUIREMENTS_SHA256",
    "DISEASE_ALIAS_COUNT",
    "DISEASE_CARRIER_COUNT",
    "DISEASE_DEFINITION_COUNT",
    "DISEASE_DELIVERY_COUNT",
    "DISEASE_MECHANIC_COUNT",
    "DISEASE_NEAR_MISS_COUNT",
    "DISEASE_RELATED_COUNT",
    "DIRECT_CENSUS_SHA256",
    "DiseaseAliasLink",
    "DiseaseCompileError",
    "DiseaseDelivery",
    "DiseaseDependency",
    "DiseaseDuration",
    "DiseaseLinkEdge",
    "DiseaseLinkError",
    "DiseaseNearMiss",
    "DiseaseSave",
    "DiseaseStage",
    "FAMILY_ID",
    "LINKED_CORPUS_SHA256",
    "LinkedDiseaseCorpus",
    "MAX_DISEASE_LINK_ID_BYTES",
    "MAX_DISEASE_LINKS",
    "MAX_DISEASE_STAGES",
    "MECHANIC_TYPE",
    "NEAR_MISS_CENSUS_SHA256",
    "NEAR_MISS_OUTPUT_SHA256",
    "NEAR_MISS_REQUIREMENTS_SHA256",
    "OFFICIAL_CREATURE_CENSUS_COUNT",
    "PROVIDER_REQUIREMENTS_SHA256",
    "REGISTRY_STATUS",
    "RelatedDiseaseUse",
    "CompiledDisease",
    "compile_disease",
    "compile_disease_census",
    "compile_disease_near_miss",
    "compile_disease_near_miss_census",
    "disease_consumer_requirements",
    "disease_near_miss_requirements",
    "disease_provider_requirements",
    "link_disease_corpus",
    "validate_compiled_disease",
    "validate_disease_link_graph",
    "validate_disease_near_miss",
    "validate_linked_disease_corpus",
]

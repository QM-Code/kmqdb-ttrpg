"""Compile and link the complete Core MC1 poison-affliction corpus.

This family consumes only exact selections issued by one retained
``SourceAuthorityAdapter`` derived from the server's schema-2 authority
store.  The reviewed census contains 48 definitions and four source-authored
aliases.  Compilation preserves each save, onset, maximum duration, ordered
stage, stage interval, effect duration, special clause, and source blocker.
Linking derives every exact Strike or named-ability delivery from the same
authenticated creature blocks and binds the Player Core affliction,
multiple-exposure, recovery, treatment, and removal rules.

The existing staged-poison encounter implementation is intentionally
untouched.  These artifacts are compile/link-only, immutable, non-transferable
authority projections with explicit typed runtime deferrals.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import re
from typing import Any, Callable, Literal, NamedTuple, TypeAlias, final

from .contracts import (
    RawSourceArray,
    RawSourceObject,
)
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


FAMILY_ID = "poison-afflictions"
MECHANIC_TYPE = "poison-affliction"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"
SOURCE_SCOPE = ("core-mc1", "core-pc1")
REGISTRY_STATUS = "unregistered"

OFFICIAL_CREATURE_CENSUS_COUNT = 445
POISON_CARRIER_COUNT = 52
POISON_DEFINITION_COUNT = 48
POISON_ALIAS_COUNT = 4
POISON_STAGE_COUNT = 123
POISON_DELIVERY_COUNT = 63
POISON_RELATED_USE_COUNT = 3
POISON_SPECIAL_CLAUSE_COUNT = 5
POISON_PROVIDER_COUNT = 13
POISON_SOURCE_BLOCKER_COUNT = 1

MAX_POISON_TEXT_BYTES = 65_536
MAX_POISON_STAGES = 32
MAX_POISON_RECORDS = 128
MAX_POISON_DELIVERIES = 256
MAX_POISON_RELATED_USES = 64
MAX_POISON_SPECIAL_CLAUSES = 16
MAX_POISON_SOURCE_MEMBERS = 512
MAX_POISON_STRIKES = 64
MAX_POISON_SCAN_NODES = 8_192
MAX_POISON_SCAN_DEPTH = 16
MAX_POISON_IDENTIFIER_BYTES = 256

CARRIER_CENSUS_SHA256 = (
    "579e90bced1201ef06b1f676ecb801e69518b6b953ad07159f61089c0e7f0ec4"
)
CONSUMER_REQUIREMENTS_SHA256 = (
    "d1e8aadb16634ed51eb9aac8ea909c56bdfc72475599dc7610b8024fe78fddd7"
)
PROVIDER_REQUIREMENTS_SHA256 = (
    "9844339d05c0c9cf6b5fd82a856bd67af0f053aaf1501e6cd2a76de78ede9808"
)
COMPILED_CENSUS_SHA256 = (
    "236d963a600b7ded14c693de7dc768f3874750c2d6490b32e33946c8ca9dabf5"
)
LINKED_CORPUS_SHA256 = (
    "7a80b062e7264b56b4e31fc28293d62d53e995b451ac6560a9081dd0fbcce167"
)


PoisonClassification: TypeAlias = Literal[
    "affliction-definition",
    "affliction-alias",
]
PoisonDefinitionStatus: TypeAlias = Literal[
    "complete",
    "source-incomplete",
    "alias",
]
PoisonDeliveryKind: TypeAlias = Literal[
    "strike-rider",
    "named-ability-exposure",
]


class _PoisonSpec(NamedTuple):
    rule_id: str
    sequence: int
    creature_name: str
    ability_name: str
    locator: str
    carrier_path: tuple[tuple[str, int], ...]
    selection_path: tuple[tuple[str, int], ...]
    block_sha256: str
    selection_sha256: str
    traits: tuple[str, ...]
    source_shape: str
    classification: PoisonClassification
    definition_status: PoisonDefinitionStatus


class _ProviderSpec(NamedTuple):
    rule_id: str
    source_id: str
    locator: str
    selection_path: tuple[tuple[str, int], ...]
    block_sha256: str
    selection_sha256: str


_POISON_SPECS: tuple[_PoisonSpec, ...] = (
    _PoisonSpec('poison-consumer:001', 17, 'Giant Ant', 'Giant Ant Venom', '21.3', (('^.creature', 1),), (('!.Giant Ant Venom', 19),), 'c826aa4a8f80a3768f7e7657b2b5caa15da8e31a0fd9c690252b3615adba36e0', '0ed12e0c537e642046e0510a88f685de830ab26536e00b6191e6b13ca905273f', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:002', 64, 'Cave Worm', 'Cave Worm Venom', '54.2', (('^.creature', 1),), (('!.Cave Worm Venom', 21),), '21db440415be6758bb0e73a17c09cdfbc4954ab78ddb7dcfaf1df3b2e6247dfd', '3c69922134f7e436da3a903487830659b6d1b04577d385ba0b0d9e40f9baa876', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:003', 65, 'Benthic Worm', 'Benthic Worm Venom', '56.2', (('^.creature', 1),), (('!.Benthic Worm Venom', 21),), '38a18196a24ccfeacc170c5bfb572d9cdd5e5d823b60d8db090907b78b44ceca', '4f0f8e2c8b55a3b034af4d473876b32487010b9f30442e24d14f8bab4121c7cf', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:004', 66, 'Magma Worm', 'Magma Worm Venom', '57.2', (('^.creature', 2),), (('!.Magma Worm Venom', 27),), 'e8940aaaccc4613ce509a6b6e81b8733290b5a5649ccfc56bce6b48bff3827c5', '7b1b6abdafaece75ee6466ee1dfc193ba84e72390dd0109fbe9f672d4a61e50e', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:005', 68, 'Giant Centipede', 'Giant Centipede Venom', '59.3', (('^.creature', 1),), (('!.Giant Centipede Venom', 19),), 'dc98c5f4b46a4734aca09122ab6f3adb97cc7b54f5517b40beefd84ac7051c7c', 'ecc4842e1e8bbb1b134ee704c2639facd653764d465d273844310394dcee2d1e', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:006', 69, 'Centipede Swarm', 'Centipede Swarm Venom', '59.5', (('^.creature', 1),), (('!.Centipede Swarm Venom', 21),), '7093d3c4fe87ae8b7bf8b7c25e995fc2c0feaf9a9219a9c2d1d54aa4be761b7e', '0a91a051dee3eb16882252676120e275b351bb5b4a870dd4f4ea2e8be19fbe0e', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:007', 75, 'Quetz Coatl', 'Quetz Coatl Venom', '65.1', (('Coatl', 1), ('Coatl', 0), ('^.creature', 2)), (('!.Quetz Coatl Venom', 22),), 'f0425486f7271dfebe4d6084a4bf20042216b795b5e87a5ef1cd60d90ff63400', 'f8b4f3bd63917c3763a9279ca489973b13b88a1d1994518e1685bfe285272d37', ('holy', 'poison'), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:008', 77, 'Con Rit', 'Con Rit Venom', '67.1', (('Con Rit', 1), ('Con Rit', 0), ('^.creature', 3)), (('!.Con Rit Venom', 21),), '54d137e8b660848e503a383bf4c947925fb270f42c5591905d16a30207bbde45', '65ccd85e1a1207b8b0d497b4061674df21bb8393142235156ddbeb5bac873c59', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:009', 101, 'Sarglagon', 'Sarglagon Venom', '88.3', (('^.creature', 1),), (('!.Sarglagon Venom', 27),), '4cc0a04b107af3ef3a68d0cb9fa0df920e5f8976f5c725c42a25bc0f21701114', '142a7126d08fbd5cf81c7794b6ac8da91e5ddbaf8e963f1f2db2139d404e368b', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:010', 104, 'Nessari', 'Nessari Venom', '92.2', (('^.creature', 5),), (('!.Nessari Venom', 31),), '02aef8e9de00832deb749267530b62e2cb2fb299f0d83e0404ee920243cb7f54', 'cd5c6457e61e4a8b520f770f20c31b991dc4d091f22be764907da793fd2e1a4c', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:011', 105, 'Dezullon', 'Amnesia Venom', '94.1', (('Dezullon', 1), ('Dezullon', 0), ('^.creature', 4)), (('!.Amnesia Venom', 22),), 'e2e92265b16c6d37c4d912857208847343aad0fac45de833c9731d2293786a68', '8777dc9a7c008ab346a1c7847104d979ca3ffc9490d606b9ff491b05b618d6f8', ('mental', 'poison'), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:012', 107, 'Compsognathus', 'Compsognathus Venom', '96.3', (('^.creature', 2),), (('!.Compsognathus Venom', 19),), '189c3c7b5e5a1bb7aa4bc894d683342f30b9177225559e6f84a1a5c66e183098', 'aad43bf9689494641e325e0992624163e4f0e73fe44d44c5f541052003b76e1d', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:013', 123, 'Jah-Tohl', 'Mind Snatcher Venom', '106.1', (('^.creature', 3),), (('!.Mind Snatcher Venom', 27),), 'f3656ab939d7bfb87f677acd2ed41e184b0251dedd2f13356e397d80c1bac7cb', '424a7060d03940fc3fe740e1f9444970ce9dabcccb8027f79e84a60f00478278', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:014', 153, 'Jungle Drake', 'Jungle Drake Venom', '130.1', (('^.creature', 1),), (('!.Jungle Drake Venom', 24),), 'a258d0018cc2ac1298e2c0b730e9251d64388add86d00023f36d038939b08653', 'cb78fc5b63cee222e40dbc75792060c6a53fd7e50ebe98c32a55a72cfecd5f00', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:015', 154, 'Wyvern', 'Wyvern Venom', '131.1', (('^.creature', 2),), (('!.Wyvern Venom', 25),), 'e1df50bde287eac1d982337df07eeac842ca4dc984d792c38e85e8b1c022a423', '60f227e1e0cdd6b4f29ac23e599f80f42432be9e01bf483a74418fce65e0c0a5', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:016', 249, 'Homunculus', 'Homunculus Poison', '200.1', (('Homunculus', 1), ('Homunculus', 0), ('^.creature', 4)), (('!.Homunculus Poison', 22),), 'aeddc66c45d55d61d3665d651fa1d44e522b1145576cca7471797b431bd21458', '9212a58eb8fbe9280c862826e0d72c6a017587cb400c04ae18e94ce283d71bcb', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:017', 260, 'Imp', 'Imp Venom', '206.1', (('Imp', 1), ('Imp', 0), ('^.creature', 0)), (('!.Imp Venom', 26),), '0222d55840e76ab94bf6daf5f5007a52711687640b32c02c4457c2ac02972a52', '50aa1b5ed8c4e3676a13ce1372378d2eb6aefdafa733a75410c6d4a330de6d54', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:018', 261, 'Iron Warden', 'Iron Warden Poison', '207.1', (('Iron Warden', 1), ('Iron Warden', 0), ('^.creature', 0)), (('!.Iron Warden Poison', 26),), '42578237970eb204ff6a1322c26ebbb2be44a14e4ac44a1ca76bf7a9ae0a73e6', '7f1c6da3fb1d1d61af98b2ab9e2bdb22cbd6e798abb7328bfd26b48408eb81e0', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:019', 268, 'Kraken', 'Kraken Ink', '212.1', (('Kraken', 1), ('Kraken', 0), ('^.creature', 1)), (('!.Kraken Ink', 29),), 'b8502c80360df3f9cdad4cdb099087552d834fbb262c4b916fd47bff45003d2d', '437d47c7fae7fd134e9443f752adcf15809b3228284bcb2498bcc1993d43a299', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:020', 276, 'Crag Linnorm', 'Crag Linnorm Venom', '220.2', (('^.creature', 1),), (('!.Crag Linnorm Venom', 27),), '3049b93fefbc7f3a8da35f1b8f5b8e7c89aa0e3ba1aa3a4ca1a59d4fef6144a3', 'a288ee3532f72607411476283c0459f77eaabc8cfae90b46ea99c5366f8bf0da', ('fire', 'poison'), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:021', 277, 'Ice Linnorm', 'Ice Linnorm Venom', '221.1', (('^.creature', 1),), (('!.Ice Linnorm Venom', 27),), 'c6bbc26ae0e714a65b1e19f9e4beb68b25250375c644bfcf2f39095643736723', 'e7e86bec938659c050811c788a6d568ebb78378e67f2c6e897f78beb550507ec', ('cold', 'poison'), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:022', 278, 'Tarn Linnorm', 'Tarn Linnorm Venom', '221.3', (('^.creature', 1),), (('!.Tarn Linnorm Venom', 30),), 'c01519b94251e03f5c674081fc6143eb0debe7515f5bc8da4228dd9daf7315e7', '9b97b244d207497871e720bc10b81d5cbc08637581bc6d6c65c3eb698e99a801', ('acid', 'poison'), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:023', 279, 'Tor Linnorm', 'Tor Linnorm Venom', '222.1', (('^.creature', 1),), (('!.Tor Linnorm Venom', 30),), '1779d972c4c697efa21707476a335d5df978c857cef0398af80578a5c5b132d5', 'ce6f63d34c7e423590a8ce4bd171cb9b92583557221862eddd9accd6ae39db7f', ('fire', 'poison'), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:024', 281, 'Giant Monitor Lizard', 'Monitor Lizard Venom', '224.4', (('^.creature', 2),), (('!.Monitor Lizard Venom', 21),), '1d8ab3e9cb75f610837ade1006c996d81768d9e4165059c615981bee6c5362a0', 'cf874c65fbe58171b66b9fc4f4d6eddd2d8f5fbc4a6276339f07c9fb7268700e', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:025', 284, 'Lizardfolk Scout', 'Giant Centipede Venom', '226.4', (('^.creature', 1),), (('!.Giant Centipede Venom', 23),), '496fcb13ea6ecb116cb25f627815e3a691febd7028fca01c38feda5bd7b40ce1', '087f80d478e2638b85a1ecb491f6276b15c52e3ce25e3bd59ed062813a662a35', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:026', 289, 'Medusa', 'Serpent Venom', '230.1', (('Medusa', 1), ('Medusa', 0), ('^.creature', 2)), (('!.Serpent Venom', 25),), 'ce5dbac4e9c712802328a33026834a5190ddaaf770b4c49031c90d499c29f578', '868f9f10388d45754b3d9c40fce0b3946fb22a9c208f8d96c3147b64e52c3b12', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:027', 296, 'Smaranava', 'Smaranava Venom', '236.2', (('^.creature', 2),), (('!.Smaranava Venom', 24),), 'a17b89893008d71915d521c79a1392c7f0bfdf3e416976d69422da7467c61418', 'e8733e11685fb11cd7381873ef0cc982431275e3b9423293bcfa719e8e703bc3', ('incapacitation', 'mental', 'poison'), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:028', 297, 'Vicharamuni', 'Vicharamuni Venom', '237.1', (('^.creature', 2),), (('!.Vicharamuni Venom', 26),), 'c3b0cc546f0ba4553229fcf6f8cb8ff52fb67c304660bd4bf0ab314ed18594ea', 'd603b07135f2f8bace13eb424c9fe84752671ffeee62020788657f2712b2f88e', ('divine', 'holy', 'mental', 'poison', 'spirit'), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:029', 308, 'Giant Octopus', 'Giant Octopus Venom', '248.1', (('Octopus', 1), ('Octopus', 0), ('^.creature', 2)), (('!.Giant Octopus Venom', 22),), '4739dfe0c46caca766e894c1c25fe1a458e17206f7f383ba1a7ec4e9343cd9ab', 'ec3fc01cbde7d36fbd62b04314ff560950b75576a4de0d890904a5ce281107c8', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:030', 343, 'Yamaraj', 'Yamaraj Venom', '276.4', (('^.creature', 1),), (('!.Yamaraj Venom', 30),), '1904f72cc3ddfd5363297b75cfba880f3dc6982236bd133057f1efb660f1fe38', '7f13da9ae525fd6d63a6ad54e97185722cacc67bb55b8d29abcecf2b397888f3', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:031', 346, 'Pukwudgie', 'Pukwudgie Poison', '279.1', (('Pukwudgie', 1), ('Pukwudgie', 0), ('^.creature', 5)), (('!.Pukwudgie Poison', 27),), '057a6b2632ec989e6150b4e8769b5422cb3b5e5c2835053fe9a8e0c7f710a70f', 'b3a8b55a41df62f464b202b147fb1a57cb4d758480ba92725eb8345702c76971', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:032', 348, 'Gongorinan', 'Gongorinan Venom', '281.1', (('^.creature', 1),), (('!.Gongorinan Venom', 26),), '193bc2ba5ba87d5519f6ef7d74a0aac329bd640a2bfcb864f3e73c3a01c67cf6', 'eb055dc332b7d6ba345fc3b8382865403ed6fd18a7a03b07c4f62cc9ffb7c716', ('poison', 'polymorph'), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:033', 350, 'Thulgant', 'Thulgant Venom', '283.1', (('^.creature', 1),), (('!.Thulgant Venom', 28),), 'a267829c367b12a2efa90737ab73df1f7661c12b7202517dc18890d2d58a7949', 'eea28d87d65bfedaf85e4b91f63a20e440cf0ab133a2418dbf2da8bd1d5e9ebf', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:034', 353, 'Raktavarna', 'Raktavarna Venom', '286.2', (('^.creature', 1),), (('!.Raktavarna Venom', 27),), 'b0474a952b58d43c467c4af621706a5b2e893fe4d17b19048bafb8a0e29c6db9', '4f7a82bbe608c725b6741cb9b57c8926042ce3df38ff19d846e8ffddf7e077a6', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:035', 359, 'Reefclaw', 'Reefclaw Venom', '291.1', (('Reefclaw', 1), ('Reefclaw', 0), ('^.creature', 4)), (('!.Reefclaw Venom', 22),), 'ad68f4ccbabb984327176f2b603483112ebc55396ca2a96e14e5147b9ccda5af', '6fdf0c678e8ae301078ca30fb2ab362dd377763189a84a40324ab8d518b822e9', ('poison',), 'scalar', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:036', 368, 'Giant Scorpion', 'Giant Scorpion Venom', '298.2', (('^.creature', 2),), (('!.Giant Scorpion Venom', 21),), '3a4add8175461313d6854cd2f09b5a0e13a5031d5b97d48770112ea83d684f53', '37ff84ec35f949996e62149bc06e8262af7df8ec19c236921e9ca118abd22ba3', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:037', 369, 'Scorpion Swarm', 'Scorpion Venom', '298.4', (('^.creature', 1),), (('!.Scorpion Venom', 21),), 'd86fc438a500d51615d7ab8124787d13e9e9044639e7ca96c4b22f235b1e983f', 'd97caaf07c9763b7f207eb1107ac413e25ba54a869a351458c77513535589f59', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:038', 370, 'Sea Serpent', 'Sea Serpent Algae', '299.1', (('Sea Serpent', 1), ('Sea Serpent', 0), ('^.creature', 2)), (('!.Sea Serpent Algae', 23),), 'e6fb5e82cdb87e23b802db0f23d0d391ab09513e888a442c0866267ff504367a', 'd31c1c43a66e1cc02904e43de9928072e7dd7db8f2a64f9b41a1fb6b1e7209a4', ('incapacitation', 'poison'), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:039', 374, 'Zyss Serpentfolk', 'Serpentfolk Venom', '302.2', (('^.creature', 1),), (('!.Serpentfolk Venom', 26),), 'bb1d947dc9e9b6aae157309d160a8559815cc7900286730582d4b8f2bd36fb1f', '244aa19a5c9be946b7eed4db049e8b08056841a498671a09bdcf0ba2ef337f30', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:040', 375, 'Aapoph Serpentfolk', 'Serpentfolk Venom', '303.2', (('^.creature', 2),), (('!.Serpentfolk Venom', 23),), 'eda129a1419f91dc8c243cd127eb85a765ce87620fabfb8346e3b756f4daf240', '29ba6d825744e45fdd3898ab7db61ff5d8f27809696a2d798dc623b28b0fe56c', ('poison',), 'ordered-object', 'affliction-alias', 'alias'),
    _PoisonSpec('poison-consumer:041', 376, 'Coil Spy', 'Serpentfolk Venom', '304.1', (('^.creature', 1),), (('!.Serpentfolk Venom', 28),), '0ad917f641a02609cfb5af3e28047d7ed933e3958662923e8fc71805b84200d9', 'e821bc6a612a2ff575a639ca58c5c3cfd498c063ef102ef8b54f07dec6517534', ('poison',), 'ordered-object', 'affliction-alias', 'alias'),
    _PoisonSpec('poison-consumer:042', 377, 'Aapoph Granitescale', 'Serpentfolk Venom', '304.3', (('^.creature', 1),), (('!.Serpentfolk Venom', 26),), '14f4d0ea734bc6ac833cb2c904723783655389c9ff777a9a19d25f94e8bf2a0c', '7d9cc3ad000d8381161fd50a5799f6b6f13e4b78302be40de770d7b0f456e3a9', ('poison',), 'ordered-object', 'affliction-alias', 'alias'),
    _PoisonSpec('poison-consumer:043', 378, 'Bone Prophet', 'Serpentfolk Venom', '305.1', (('^.creature', 1),), (('!.Serpentfolk Venom', 26),), 'b337bbbfd60839c8c6e3f3e0975992ffde22243bc9264abfaef4506132c39f0d', '0a858f280bb1ab59c229c0fa4cd46aaa07c4ee39f29dddd4de6566554383ae78', ('poison',), 'ordered-object', 'affliction-alias', 'alias'),
    _PoisonSpec('poison-consumer:044', 384, 'Shuln', 'Shuln Saliva', '309.1', (('Shuln', 1), ('Shuln', 0), ('^.creature', 1)), (('!.Shuln Saliva', 22),), 'd2375836248729de161b1d954b7a1152146086469c517f93c575bb73815c12a5', 'd11c5a22d8a8f3170ef1abed9a24eb67f6630efc12f9a166861996cddb50ec9b', ('incapacitation', 'poison'), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:045', 393, 'Viper', 'Viper Venom', '316.2', (('^.creature', 1),), (('!.Viper Venom', 20),), '23368dfae10953d3168c47b12f8786389ab2128b577faa99fcf3a3a465524672', '4784ec487963c3dfe15ccb1ed2a7547792076322dc508d27e17505ee059ed64e', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:046', 395, 'Giant Viper', 'Giant Viper Venom', '316.6', (('^.creature', 1),), (('!.Giant Viper Venom', 21),), 'a239d7ecee6f23fbaaf90fa57036cbcf4d2695439d83617aec8d4e84c7e5e602', 'b3b0d0350f9aaf6a4ac9e983febe5bcbf6a8d506f6e6889df793682bdf820481', ('poison',), 'ordered-object', 'affliction-definition', 'source-incomplete'),
    _PoisonSpec('poison-consumer:047', 399, 'Spider Swarm', 'Spider Swarm Venom', '320.2', (('^.creature', 1),), (('!.Spider Swarm Venom', 23),), '56cb2471bb374b2cfe9406c72c456fe539ea8f085b298d2c2126013098f0162a', 'dbe26860a8a0024fbcc5c4da2ce4c967fef83b22af6d1ef6372c40dc64aef6bc', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:048', 400, 'Hunting Spider', 'Hunting Spider Venom', '320.4', (('^.creature', 1),), (('!.Hunting Spider Venom', 23),), 'a37e3882f3a7a6f185125392475a55c3ccbd40bcc9cc38261282d8fb7146ee34', '0009822bfed705086503ef93c8ed61a8be91ee980af457aa9a8db846164a4597', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:049', 401, 'Giant Tarantula', 'Giant Tarantula Venom', '321.1', (('^.creature', 1),), (('!.Giant Tarantula Venom', 19),), '74384a544832761638f122d66e3af2d1ad015144c401bd4146f2a3f673d84646', 'aba38d8951b9c40d2e4e78df545ee3a7308266376dfa9a2f74a67ba1af69ac21', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:050', 402, 'Goliath Spider', 'Goliath Spider Venom', '321.3', (('^.creature', 1),), (('!.Goliath Spider Venom', 23),), '159b2cb74377f43754e5bbf32fdb3cc10c2231ae2bf86f09d01606e1bc437af5', 'aa5980e0b7eba35b56e1bcd3184aead15e14405b2b4e892e9f0d37dca47c4c12', ('incapacitation', 'poison'), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:051', 426, 'Giant Wasp', 'Giant Wasp Venom', '343.2', (('^.creature', 1),), (('!.Giant Wasp Venom', 20),), '0a7ae76c15f69a6dbe37a3e8b6e46f638b9e33569b8927b9a3127c85e1134dad', 'eaa351b893db58fa290751fd43845079cd84f785eb5d4d9a28a976f15ddcea00', ('incapacitation', 'poison'), 'ordered-object', 'affliction-definition', 'complete'),
    _PoisonSpec('poison-consumer:052', 427, 'Wasp Swarm', 'Wasp Venom', '343.4', (('^.creature', 1),), (('!.Wasp Venom', 22),), 'd252c8e6304e1b609530511d0a0b2a2f0dc0c51887b7e52bfb3e78c2aa01bf5c', 'd3dd5598b9ad980eca8d043315c645fb5b18a5faa1dbf3ab8dca4d7e91c12170', ('poison',), 'ordered-object', 'affliction-definition', 'complete'),
)


_PROVIDER_SPECS: tuple[_ProviderSpec, ...] = (
    _ProviderSpec('poison-trait', 'core-pc1', '452.1', (('!.poison (trait)', 434),), '3b1e174896f4057efb317bf53ecabb5db4aa66e1160d1c47371c6947afda5449', '6040e77a6e52017f6c0b377d382ccdda345d3013183122600346ab0f69c4685d'),
    _ProviderSpec('strike', 'core-pc1', '418.4', (), '4cea8c4d82ad0a9ea60102ae21613d1e401270c1b2e6d97ad7fc10041bda273a', '4cea8c4d82ad0a9ea60102ae21613d1e401270c1b2e6d97ad7fc10041bda273a'),
    _ProviderSpec('affliction-format', 'core-pc1', '430.3', (), 'f2006abbd55e7c0fcb8d771f2c3f109af2d2231de4d37f6dcec5ab39f998df97', 'f2006abbd55e7c0fcb8d771f2c3f109af2d2231de4d37f6dcec5ab39f998df97'),
    _ProviderSpec('affliction-save', 'core-pc1', '430.4', (), '9dfb48b64be6588d59a030a6d3eeb9614d19a841e8b0392b2ecd297f6aedd044', '9dfb48b64be6588d59a030a6d3eeb9614d19a841e8b0392b2ecd297f6aedd044'),
    _ProviderSpec('affliction-onset', 'core-pc1', '430.5', (), '1e9eeafc96f519ce9a6ba6c4243690b7858d34baf91130bfcc4876e9366bf3e1', '1e9eeafc96f519ce9a6ba6c4243690b7858d34baf91130bfcc4876e9366bf3e1'),
    _ProviderSpec('affliction-maximum-duration', 'core-pc1', '430.6', (), '2452601fae54468f54d258389e14a179ac3d587bd61faf315bc1472c8c48213e', '2452601fae54468f54d258389e14a179ac3d587bd61faf315bc1472c8c48213e'),
    _ProviderSpec('affliction-stage', 'core-pc1', '430.7', (), 'aa7c749eb46a4e98d1f7f5da4f9db6a14d484c11060e5845ed882dc526238a88', 'aa7c749eb46a4e98d1f7f5da4f9db6a14d484c11060e5845ed882dc526238a88'),
    _ProviderSpec('affliction-effect', 'core-pc1', '430.8', (), '78309af53b456d8b41dee46aba6c327f1be13cd60fa4e54331108c3466ae78aa', '78309af53b456d8b41dee46aba6c327f1be13cd60fa4e54331108c3466ae78aa'),
    _ProviderSpec('multiple-exposures', 'core-pc1', '430.9', (), '2ee5c0ad2df10f0a688c7fad95ebca466946b154b8425a30357d18ff345eff6e', '2ee5c0ad2df10f0a688c7fad95ebca466946b154b8425a30357d18ff345eff6e'),
    _ProviderSpec('virulent', 'core-pc1', '431.1', (), 'aa9e03e06b4c4279230255d4640218c8c9999c6e2a8cb66b1437c576c7555178', 'aa9e03e06b4c4279230255d4640218c8c9999c6e2a8cb66b1437c576c7555178'),
    _ProviderSpec('removing-afflictions', 'core-pc1', '431.3', (), '5cbf437b0171fc21fda86cac8a9659a9d2d68b7db78cd0b40fc9c5029f751d2a', '5cbf437b0171fc21fda86cac8a9659a9d2d68b7db78cd0b40fc9c5029f751d2a'),
    _ProviderSpec('treat-poison', 'core-pc1', '242.3', (), '314467f57d88bba6487f9190592b74c08fe268613fc590ad20b71c0bfe7f582d', '314467f57d88bba6487f9190592b74c08fe268613fc590ad20b71c0bfe7f582d'),
    _ProviderSpec('cleanse-affliction', 'core-pc1', '320.5', (), '78a7ae7d54af019a3f51e31af026aa8b1b07a8293ecce47fb6cc482984e96812', '78a7ae7d54af019a3f51e31af026aa8b1b07a8293ecce47fb6cc482984e96812'),
)


_ALIAS_LINK_SPECS = (
    ("poison-consumer:040", "poison-consumer:039", 20),
    ("poison-consumer:041", "poison-consumer:039", 19),
    ("poison-consumer:042", "poison-consumer:039", 22),
    ("poison-consumer:043", "poison-consumer:039", 26),
)

_TERMINAL_STAGE_SPECS = (
    ("poison-consumer:032", 5, "explicit-affliction-end"),
    ("poison-consumer:044", 3, "reviewed-condition-duration-terminal"),
    ("poison-consumer:050", 3, "reviewed-condition-duration-terminal"),
)

_SPECIAL_CLAUSE_SPECS = (
    (
        "poison-consumer:007",
        "conditional-curse-and-spirit-variant",
        "To unholy creatures, this is a curse instead of a poison and deals spirit damage instead of poison damage",
        "target-trait-variant",
    ),
    (
        "poison-consumer:016",
        "finite-dose-and-refill",
        "A homunculus has one dose of poison in a reservoir in its head. It can refill this poison from its reserves with an Interact action",
        "resource-and-interact-state",
    ),
    (
        "poison-consumer:019",
        "self-immunity",
        "Krakens are immune to this poison",
        "source-creature-immunity",
    ),
    (
        "poison-consumer:027",
        "holy-success-auto-cure",
        "When a holy creature succeeds at a saving throw against this poison, it is immediately cured",
        "target-trait-recovery",
    ),
    (
        "poison-consumer:030",
        "clumsy-doomed-mirror",
        "While a creature is clumsy from this poison, it is doomed with the same value",
        "derived-condition-state",
    ),
)

_STATIC_RELATED_USE_SPECS = (
    (
        "poison-consumer:028",
        "Spiritual Venom",
        (("!.Spiritual Venom", 25),),
        "5b86d7a62ebe44ea44ea1064d56df3b77ca71a9458af8e344aa52ab16580a270",
        "damage-suppression-and-spell-targeting",
    ),
)

_RUNTIME_DEPENDENCY_SPECS = (
    ("poison-state-identity", "affliction-state", "same-poison identity"),
    ("onset-clock", "campaign-time", "onset scheduling"),
    ("maximum-duration-clock", "campaign-time", "absolute maximum duration"),
    ("ordered-stage-progression", "affliction-state", "ordered poison stages"),
    ("stage-effect-application", "effect-state", "authored stage effects"),
    ("repeated-exposure", "affliction-state", "same-poison re-exposure"),
    ("interval-save-recovery", "affliction-state", "interval save recovery"),
    ("virulent-save-history", "affliction-state", "consecutive success history"),
    ("treat-poison", "affliction-state", "Medicine treatment modifiers"),
    ("cleanse-affliction", "counteract-state", "counteract removal"),
    ("delivery-trigger", "effect-state", "Strike and ability exposure"),
    ("terminal-stage-effects", "effect-state", "terminal authored effects"),
    ("special-clause-effects", "effect-state", "source-specific clauses"),
)


_TRAIT_PREFIX_RE = re.compile(r"^\s*\((?P<traits>[^)]+)\)", re.DOTALL)
_TAG_RE = re.compile(r"</?[^>]+>", re.ASCII)
_NORMALIZE_RE = re.compile(r"[^a-z0-9]+", re.ASCII)
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
_TRAILING_INTERVAL_RE = re.compile(
    r"\s*\((?P<duration>"
    r"[0-9]+(?:d[0-9]+(?:[+-][0-9]+)?)?\s+"
    r"(?:rounds?|minutes?|hours?|days?|weeks?))\)\s*$",
    re.IGNORECASE | re.ASCII,
)
_EFFECT_DURATION_RE = re.compile(
    r"\bfor\s+(?P<duration>"
    r"[0-9]+(?:d[0-9]+(?:[+-][0-9]+)?)?\s+"
    r"(?:rounds?|minutes?|hours?|days?|weeks?))\b",
    re.IGNORECASE | re.ASCII,
)
_ALIAS_RE = re.compile(
    r"^As\s+(?P<target>[^,]+),\s*but\s+DC\s+(?P<dc>[0-9]+)\.$",
    re.IGNORECASE | re.ASCII,
)
_DICE_RE = re.compile(
    r"(?P<count>[0-9]+)d(?P<sides>[0-9]+)"
    r"(?P<modifier>[+-][0-9]+)?",
    re.ASCII,
)


class PoisonCompileError(ValueError):
    """A reviewed poison source failed its closed compiler contract."""


class PoisonLinkError(ValueError):
    """The poison corpus cannot be linked without ambiguity or drift."""


class _SealedType(type):
    def __new__(
        metaclass: type,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        **kwargs: object,
    ) -> type:
        if any(
            base.__dict__.get("_poison_type_sealed", False)
            for base in bases
        ):
            raise TypeError("sealed poison artifacts cannot be subclassed")
        return super().__new__(
            metaclass,
            name,
            bases,
            namespace,
            **kwargs,
        )

    def __setattr__(cls, name: str, value: object) -> None:
        if cls.__dict__.get("_poison_type_sealed", False):
            raise TypeError("sealed poison artifact types are immutable")
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if cls.__dict__.get("_poison_type_sealed", False):
            raise TypeError("sealed poison artifact types are immutable")
        super().__delattr__(name)


def _seal_type(value: type) -> None:
    type.__setattr__(value, "_poison_type_sealed", True)


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
class PoisonDuration(_NoTransfer):
    source_text: str
    amount_kind: str
    fixed_amount: int | None
    dice_count: int | None
    dice_sides: int | None
    dice_modifier: int | None
    unit: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonDuration is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonSave(_NoTransfer):
    dc: int
    save_type: str
    basic: bool
    source_text: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonSave is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonStage(_NoTransfer):
    number: int
    source_text: str
    effect_text: str
    interval: PoisonDuration | None
    effect_durations: tuple[PoisonDuration, ...]
    permanent_effect: bool
    terminal: bool
    terminal_reason: str | None
    source_complete: bool

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonStage is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonSpecialClause(_NoTransfer):
    clause_id: str
    kind: str
    source_text: str
    required_contract: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonSpecialClause is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonDependency(_NoTransfer):
    dependency_id: str
    phase: str
    required_contract: str
    provider_rule_id: str | None

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonDependency is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class CompiledPoisonAffliction(_NoTransfer):
    record_id: str
    sequence: int
    creature_name: str
    ability_name: str
    locator: str
    classification: PoisonClassification
    definition_status: PoisonDefinitionStatus
    source_shape: str
    traits: tuple[str, ...]
    action_cost: int | str | None
    source_text: str
    source_text_sha256: str
    saving_throw: PoisonSave | None
    onset: PoisonDuration | None
    maximum_duration: PoisonDuration | None
    stages: tuple[PoisonStage, ...]
    alias_target_creature: str | None
    alias_dc_override: int | None
    special_clauses: tuple[PoisonSpecialClause, ...]
    dependencies: tuple[PoisonDependency, ...]
    consumer_rule: VerifiedRuleReceipt

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("CompiledPoisonAffliction is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonAliasLink(_NoTransfer):
    alias_record_id: str
    definition_record_id: str
    resolved_dc: int

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonAliasLink is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonDelivery(_NoTransfer):
    delivery_id: str
    record_id: str
    creature_name: str
    source_name: str
    delivery_kind: PoisonDeliveryKind
    delivery_mode: str
    traits: tuple[str, ...]
    source_text: str
    source_selection: VerifiedSourceSelection

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonDelivery is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonRelatedUse(_NoTransfer):
    related_id: str
    record_id: str
    creature_name: str
    source_name: str
    relationship: str
    source_text: str
    source_selection: VerifiedSourceSelection

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonRelatedUse is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonProgressionRules(_NoTransfer):
    initial_success_unaffected: bool
    initial_failure_stage: int
    initial_critical_failure_stage: int
    interval_critical_success_delta: int
    interval_success_delta: int
    interval_failure_delta: int
    interval_critical_failure_delta: int
    repeat_highest_stage: bool
    below_stage_one_ends: bool
    apply_effect_on_stage_entry: bool
    provider_rule_ids: tuple[str, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonProgressionRules is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonExposureRules(_NoTransfer):
    successful_exposure_unchanged: bool
    failure_stage_delta: int
    critical_failure_stage_delta: int
    preserves_maximum_duration: bool
    preserves_onset_length: bool
    immediate_effect_after_onset: bool
    provider_rule_ids: tuple[str, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonExposureRules is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class PoisonRecoveryRules(_NoTransfer):
    ordinary_successes_required: int
    virulent_consecutive_successes_required: int
    virulent_critical_success_delta: int
    treat_poison_critical_success_bonus: int
    treat_poison_success_bonus: int
    treat_poison_critical_failure_penalty: int
    provider_rule_ids: tuple[str, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PoisonRecoveryRules is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class LinkedPoisonCorpus(_NoTransfer):
    records: tuple[CompiledPoisonAffliction, ...]
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    alias_links: tuple[PoisonAliasLink, ...]
    deliveries: tuple[PoisonDelivery, ...]
    related_uses: tuple[PoisonRelatedUse, ...]
    progression_rules: PoisonProgressionRules
    exposure_rules: PoisonExposureRules
    recovery_rules: PoisonRecoveryRules
    dependencies: tuple[PoisonDependency, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("LinkedPoisonCorpus is linker-created")


def _new_artifact(
    artifact_type: type,
    field_names: tuple[str, ...],
    values: tuple[object, ...],
) -> object:
    if len(field_names) != len(values):
        raise AssertionError("poison artifact construction is malformed")
    result = object.__new__(artifact_type)
    for field_name, value in zip(field_names, values, strict=True):
        object.__setattr__(result, field_name, value)
    return result


def _path_from_spec(
    value: tuple[tuple[str, int], ...],
) -> tuple[RawMemberStep, ...]:
    if type(value) is not tuple:
        raise AssertionError("reviewed poison path must be an exact tuple")
    result: list[RawMemberStep] = []
    for item in value:
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
        ):
            raise AssertionError("reviewed poison path is malformed")
        result.append(RawMemberStep(item[0], item[1]))
    return tuple(result)


def _consumer_requirement(
    spec: _PoisonSpec,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
    _source_id: str = MONSTER_CORE_SOURCE_ID,
    _path_impl: Callable[
        [tuple[tuple[str, int], ...]],
        tuple[RawMemberStep, ...],
    ] = _path_from_spec,
) -> RuleRequirement:
    return _requirement_type(
        rule_id=spec.rule_id,
        source_id=_source_id,
        locator=spec.locator,
        carrier_path=_path_impl(spec.carrier_path),
        selection_path=_path_impl(spec.selection_path),
        expected_block_sha256=spec.block_sha256,
        expected_selection_sha256=spec.selection_sha256,
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
        rule_id=spec.rule_id,
        source_id=spec.source_id,
        locator=spec.locator,
        selection_path=_path_impl(spec.selection_path),
        expected_block_sha256=spec.block_sha256,
        expected_selection_sha256=spec.selection_sha256,
    )


def _same_requirement(
    left: RuleRequirement,
    right: RuleRequirement,
    _canonical_json_impl: Callable[[object], bytes] = canonical_json_bytes,
    _requirement_type: type[RuleRequirement] = RuleRequirement,
) -> bool:
    return _canonical_json_impl(
        _requirement_type.as_serialized(left)
    ) == _canonical_json_impl(_requirement_type.as_serialized(right))


def _same_receipt(
    left: SourceReceipt,
    right: SourceReceipt,
    _canonical_json_impl: Callable[[object], bytes] = canonical_json_bytes,
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
        raise PoisonCompileError("poison source must be an exact object")
    matches = tuple(
        member.value for member in value.members if member.key == key
    )
    if len(matches) > 1:
        raise PoisonCompileError(f"poison source duplicates {key!r}")
    return matches[0] if matches else None


def _flow_text(
    value: object,
    label: str,
    _raw_object_type: type[RawSourceObject] = RawSourceObject,
    _max_text_bytes: int = MAX_POISON_TEXT_BYTES,
) -> str:
    if type(value) is str:
        result = value
    elif type(value) is _raw_object_type:
        paragraphs: list[str] = []
        for member in value.members:
            if member.key != "~.p" or type(member.value) is not str:
                raise PoisonCompileError(
                    f"{label} has unsupported ordered content"
                )
            paragraphs.append(member.value)
        if not paragraphs:
            raise PoisonCompileError(f"{label} is empty")
        result = "\n\n".join(paragraphs)
    else:
        raise PoisonCompileError(f"{label} must be authored text")
    if (
        not result
        or len(result.encode("utf-8")) > _max_text_bytes
        or "\x00" in result
    ):
        raise PoisonCompileError(f"{label} is outside its text bound")
    return result


def _plain_text(
    value: str,
    _tag_re: re.Pattern[str] = _TAG_RE,
    _html_unescape: Callable[[str], str] = html.unescape,
) -> str:
    if type(value) is not str:
        raise TypeError("poison source text must be exact text")
    return " ".join(
        _html_unescape(_tag_re.sub(" ", value)).replace("’", "'").split()
    )


def _normalized(
    value: str,
    _normalize_re: re.Pattern[str] = _NORMALIZE_RE,
) -> str:
    if type(value) is not str:
        raise TypeError("poison normalization requires exact text")
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
        raise PoisonCompileError(
            "reviewed poison ability must be text or an ordered object"
        )
    traits_value = _unique_member_impl(raw, "Traits")
    if type(traits_value) is _raw_array_type:
        if any(type(item) is not str for item in traits_value.items):
            raise PoisonCompileError("poison Traits must be exact text")
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
        raise PoisonCompileError("poison Traits have an invalid shape")
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
        raise PoisonCompileError("poison Action is unsupported")
    description_value = _unique_member_impl(raw, "Description")
    source_text = _flow_text_impl(
        description_value,
        "poison Description",
    )
    grammar_components: list[str] = []
    for key in ("Saving Throw", "Onset", "Maximum Duration"):
        field_value = _unique_member_impl(raw, key)
        if field_value is not None:
            if type(field_value) is not str:
                raise PoisonCompileError(f"poison {key} must be text")
            grammar_components.append(f"{key} {field_value}")
    grammar_components.append(source_text)
    return (
        "ordered-object",
        traits,
        action,
        source_text,
        _plain_text_impl("; ".join(grammar_components)),
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
    duration_type: type[PoisonDuration],
    new_artifact: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    _duration_re: re.Pattern[str] = _DURATION_RE,
    _dice_re: re.Pattern[str] = _DICE_RE,
) -> PoisonDuration:
    match = _duration_re.fullmatch(source_text.strip())
    if match is None:
        raise PoisonCompileError(
            f"unsupported poison duration: {source_text!r}"
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
        raise PoisonCompileError("poison duration must be positive")
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
    save_type: type[PoisonSave],
    new_artifact: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    _dc_first_re: re.Pattern[str] = _SAVE_DC_FIRST_RE,
    _type_first_re: re.Pattern[str] = _SAVE_TYPE_FIRST_RE,
) -> PoisonSave | None:
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
    duration_type: type[PoisonDuration],
    new_artifact: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    _duration_impl: Callable[..., PoisonDuration] = _duration,
) -> PoisonDuration | None:
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
    record_id: str,
    definition_status: PoisonDefinitionStatus,
    stage_type: type[PoisonStage],
    duration_type: type[PoisonDuration],
    new_artifact: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    _stage_header_re: re.Pattern[str] = _STAGE_HEADER_RE,
    _trailing_interval_re: re.Pattern[str] = _TRAILING_INTERVAL_RE,
    _effect_duration_re: re.Pattern[str] = _EFFECT_DURATION_RE,
    _duration_impl: Callable[..., PoisonDuration] = _duration,
    _search_impl: Callable[..., re.Match[str] | None] = re.search,
    _terminal_specs: tuple[tuple[str, int, str], ...] = (
        _TERMINAL_STAGE_SPECS
    ),
    _max_stages: int = MAX_POISON_STAGES,
) -> tuple[PoisonStage, ...]:
    matches = tuple(_stage_header_re.finditer(plain))
    if len(matches) > _max_stages:
        raise PoisonCompileError("poison stage count exceeds its bound")
    terminal_map = {
        (item[0], item[1]): item[2] for item in _terminal_specs
    }
    result: list[PoisonStage] = []
    for index, match in enumerate(matches):
        number = int(match.group("number"))
        if number != index + 1:
            raise PoisonCompileError(
                "poison stages must be contiguous and one-based"
            )
        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(plain)
        )
        source_text = plain[start:end].strip(" ,;.")
        if not source_text:
            raise PoisonCompileError("poison stage effect is empty")
        interval_match = _trailing_interval_re.search(source_text)
        interval = None
        effect_text = source_text
        if interval_match is not None:
            interval = _duration_impl(
                interval_match.group("duration"),
                duration_type,
                new_artifact,
            )
            effect_text = source_text[:interval_match.start()].rstrip(
                " ,;"
            )
        terminal_reason = terminal_map.get((record_id, number))
        source_complete = not (
            definition_status == "source-incomplete"
            and record_id == "poison-consumer:046"
            and number == 2
        )
        if interval is None and terminal_reason is None and source_complete:
            raise PoisonCompileError(
                "reviewed poison stage lacks an interval or terminal review"
            )
        effect_durations = tuple(
            _duration_impl(
                duration_match.group("duration"),
                duration_type,
                new_artifact,
            )
            for duration_match in _effect_duration_re.finditer(effect_text)
        )
        result.append(
            new_artifact(
                stage_type,
                (
                    "number",
                    "source_text",
                    "effect_text",
                    "interval",
                    "effect_durations",
                    "permanent_effect",
                    "terminal",
                    "terminal_reason",
                    "source_complete",
                ),
                (
                    number,
                    source_text,
                    effect_text,
                    interval,
                    effect_durations,
                    bool(
                        _search_impl(
                            r"\bpermanent(?:ly)?\b",
                            effect_text,
                            re.IGNORECASE | re.ASCII,
                        )
                    ),
                    terminal_reason is not None,
                    terminal_reason,
                    source_complete,
                ),
            )
        )
    return tuple(result)  # type: ignore[return-value]


def _raw_texts(
    value: object,
    *,
    _raw_object_type: type[RawSourceObject] = RawSourceObject,
    _raw_array_type: type[RawSourceArray] = RawSourceArray,
    _max_depth: int = MAX_POISON_SCAN_DEPTH,
    _max_nodes: int = MAX_POISON_SCAN_NODES,
) -> tuple[str, ...]:
    result: list[str] = []
    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        if depth > _max_depth:
            raise PoisonLinkError(
                "poison source scan exceeds its depth bound"
            )
        nodes += 1
        if nodes > _max_nodes:
            raise PoisonLinkError(
                "poison source scan exceeds its node bound"
            )
        if type(current) is str:
            result.append(current)
        elif type(current) is _raw_object_type:
            stack.extend(
                (member.value, depth + 1)
                for member in reversed(current.members)
            )
        elif type(current) is _raw_array_type:
            stack.extend(
                (item, depth + 1)
                for item in reversed(current.items)
            )
        elif current is not None and type(current) not in {
            bool,
            int,
            float,
        }:
            raise PoisonLinkError(
                "poison source scan found an invalid raw value"
            )
    return tuple(result)


def _traits_from_object(
    value: RawSourceObject,
    _unique_member_impl: Callable[
        [RawSourceObject, str],
        object | None,
    ] = _unique_member,
    _raw_array_type: type[RawSourceArray] = RawSourceArray,
) -> tuple[str, ...]:
    traits = _unique_member_impl(value, "Traits")
    if traits is None:
        return ()
    if type(traits) is _raw_array_type:
        if any(type(item) is not str for item in traits.items):
            raise PoisonLinkError("delivery Traits must be exact text")
        return tuple(item.casefold() for item in traits.items)
    if type(traits) is str:
        return tuple(
            item.strip().casefold()
            for item in traits.split(",")
            if item.strip()
        )
    raise PoisonLinkError("delivery Traits have an invalid shape")


def _bind_reviewed_api(
    *,
    poison_specs: tuple[_PoisonSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    alias_specs: tuple[tuple[str, str, int], ...],
    special_specs: tuple[tuple[str, str, str, str], ...],
    static_related_specs: tuple[
        tuple[
            str,
            str,
            tuple[tuple[str, int], ...],
            str,
            str,
        ],
        ...,
    ],
    runtime_specs: tuple[tuple[str, str, str], ...],
    adapter_type: type[SourceAuthorityAdapter],
    receipt_type: type[SourceReceipt],
    verified_rule_type: type[VerifiedRuleReceipt],
    verified_selection_type: type[VerifiedSourceSelection],
    raw_object_type: type[RawSourceObject],
    raw_array_type: type[RawSourceArray],
    member_step_type: type[RawMemberStep],
    index_step_type: type[RawIndexStep],
    duration_type: type[PoisonDuration],
    save_type: type[PoisonSave],
    stage_type: type[PoisonStage],
    special_type: type[PoisonSpecialClause],
    dependency_type: type[PoisonDependency],
    compiled_type: type[CompiledPoisonAffliction],
    alias_link_type: type[PoisonAliasLink],
    delivery_type: type[PoisonDelivery],
    related_type: type[PoisonRelatedUse],
    progression_type: type[PoisonProgressionRules],
    exposure_type: type[PoisonExposureRules],
    recovery_type: type[PoisonRecoveryRules],
    corpus_type: type[LinkedPoisonCorpus],
    compile_error_type: type[PoisonCompileError],
    link_error_type: type[PoisonLinkError],
    consumer_requirement_impl: Callable[[_PoisonSpec], RuleRequirement],
    provider_requirement_impl: Callable[[_ProviderSpec], RuleRequirement],
    same_requirement_impl: Callable[
        [RuleRequirement, RuleRequirement],
        bool,
    ],
    same_receipt_impl: Callable[[SourceReceipt, SourceReceipt], bool],
    ability_parts_impl: Callable[
        [VerifiedSourceSelection],
        tuple[str, tuple[str, ...], int | str | None, str, str],
    ],
    save_impl: Callable[..., PoisonSave | None],
    optional_duration_impl: Callable[..., PoisonDuration | None],
    stages_impl: Callable[..., tuple[PoisonStage, ...]],
    path_impl: Callable[
        [tuple[tuple[str, int], ...]],
        tuple[RawMemberStep, ...],
    ],
    unique_member_impl: Callable[[RawSourceObject, str], object | None],
    flow_text_impl: Callable[[object, str], str],
    normalized_impl: Callable[[str], str],
    raw_texts_impl: Callable[..., tuple[str, ...]],
    traits_impl: Callable[[RawSourceObject], tuple[str, ...]],
    new_artifact_impl: Callable[
        [type, tuple[str, ...], tuple[object, ...]],
        object,
    ],
    canonical_json_impl: Callable[[object], bytes],
    sha256_impl: Callable[[bytes], Any],
    onset_re: re.Pattern[str],
    maximum_duration_re: re.Pattern[str],
    alias_re: re.Pattern[str],
    source_scope: tuple[str, ...],
    family_id: str,
    mechanic_type: str,
    registry_status: str,
    official_creature_count: int,
    carrier_count: int,
    definition_count: int,
    alias_count: int,
    stage_count: int,
    delivery_count: int,
    related_count: int,
    special_count: int,
    provider_count: int,
    source_blocker_count: int,
    max_records: int,
    max_text_bytes: int,
    max_stages: int,
    max_deliveries: int,
    max_related: int,
    max_special: int,
    max_members: int,
    max_strikes: int,
    max_identifier_bytes: int,
) -> tuple[Callable[..., Any], ...]:
    spec_by_id = {spec.rule_id: spec for spec in poison_specs}
    if (
        len(poison_specs) != carrier_count
        or len(spec_by_id) != carrier_count
        or len(provider_specs) != provider_count
        or len(alias_specs) != alias_count
        or sum(
            spec.classification == "affliction-definition"
            for spec in poison_specs
        )
        != definition_count
        or sum(
            spec.definition_status == "source-incomplete"
            for spec in poison_specs
        )
        != source_blocker_count
    ):
        raise AssertionError("reviewed poison census constants disagree")
    reviewed_requirements = tuple(
        consumer_requirement_impl(spec) for spec in poison_specs
    )
    reviewed_requirement_by_id = {
        requirement.rule_id: requirement
        for requirement in reviewed_requirements
    }
    reviewed_provider_requirements = tuple(
        provider_requirement_impl(spec) for spec in provider_specs
    )
    provider_id_set = frozenset(
        requirement.rule_id
        for requirement in reviewed_provider_requirements
    )
    static_related_by_record = {
        spec[0]: spec for spec in static_related_specs
    }
    runtime_provider_map = {
        "poison-state-identity": "multiple-exposures",
        "onset-clock": "affliction-onset",
        "maximum-duration-clock": "affliction-maximum-duration",
        "ordered-stage-progression": "affliction-stage",
        "stage-effect-application": "affliction-effect",
        "repeated-exposure": "multiple-exposures",
        "interval-save-recovery": "affliction-save",
        "virulent-save-history": "virulent",
        "treat-poison": "treat-poison",
        "cleanse-affliction": "cleanse-affliction",
        "delivery-trigger": "strike",
        "terminal-stage-effects": "affliction-effect",
        "special-clause-effects": "poison-trait",
    }
    if any(
        runtime_provider_map.get(spec[0]) not in provider_id_set
        for spec in runtime_specs
    ):
        raise AssertionError("poison runtime dependency provider is absent")

    def _require_authority(
        authority: SourceAuthorityAdapter,
    ) -> SourceAuthorityAdapter:
        if type(authority) is not adapter_type:
            raise TypeError("poison authority must be an exact adapter")
        if authority.allowed_source_ids != source_scope:
            raise compile_error_type(
                "poison authority must use the reviewed source scope"
            )
        return authority

    def _consumer_rule_and_spec(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
    ) -> tuple[VerifiedRuleReceipt, _PoisonSpec]:
        _require_authority(authority)
        if type(receipt) is not receipt_type:
            raise TypeError("poison compiler requires an exact receipt")
        selection = authority.reload(receipt)
        address = selection.address
        candidates = tuple(
            spec
            for spec, requirement in zip(
                poison_specs,
                reviewed_requirements,
                strict=True,
            )
            if address.source_id == requirement.source_id
            and address.locator == requirement.locator
            and address.carrier_path == requirement.carrier_path
            and address.selection_path == requirement.selection_path
            and address.span == requirement.span
        )
        if len(candidates) != 1:
            raise compile_error_type(
                "source receipt is not a reviewed poison carrier"
            )
        spec = candidates[0]
        # Use the immutable ID map rather than allowing receipt metadata to
        # select or construct a requirement.
        requirement = reviewed_requirement_by_id[spec.rule_id]
        rule = authority.resolve_rule(requirement)
        if not same_receipt_impl(rule.receipt, selection.receipt):
            raise compile_error_type(
                "source receipt differs from the reviewed poison rule"
            )
        return rule, spec

    def _validated_consumer_rule(
        authority: SourceAuthorityAdapter,
        rule: VerifiedRuleReceipt,
    ) -> tuple[VerifiedRuleReceipt, _PoisonSpec]:
        _require_authority(authority)
        if type(rule) is not verified_rule_type:
            raise TypeError("compiled poison consumer rule must be exact")
        authority.validate_rule(rule)
        spec = spec_by_id.get(rule.rule_id)
        if spec is None:
            raise compile_error_type(
                "compiled poison uses an unreviewed consumer rule"
            )
        requirement = reviewed_requirement_by_id[spec.rule_id]
        if not same_requirement_impl(rule.requirement, requirement):
            raise compile_error_type(
                "compiled poison requirement differs from review"
            )
        fresh = authority.resolve_rule(requirement)
        if not same_receipt_impl(rule.receipt, fresh.receipt):
            raise compile_error_type(
                "compiled poison receipt differs from current authority"
            )
        return fresh, spec

    def _provider_rules(
        authority: SourceAuthorityAdapter,
    ) -> tuple[VerifiedRuleReceipt, ...]:
        _require_authority(authority)
        return tuple(
            authority.resolve_rule(requirement)
            for requirement in reviewed_provider_requirements
        )

    def _special_clauses(
        spec: _PoisonSpec,
        plain: str,
    ) -> tuple[PoisonSpecialClause, ...]:
        result: list[PoisonSpecialClause] = []
        for record_id, kind, source_text, contract in special_specs:
            if record_id != spec.rule_id:
                continue
            if normalized_impl(source_text) not in normalized_impl(plain):
                raise compile_error_type(
                    "reviewed poison special clause is absent from source"
                )
            result.append(
                new_artifact_impl(
                    special_type,
                    (
                        "clause_id",
                        "kind",
                        "source_text",
                        "required_contract",
                    ),
                    (
                        f"{record_id}:{kind}",
                        kind,
                        source_text,
                        contract,
                    ),
                )
            )
        if len(result) > max_special:
            raise compile_error_type(
                "poison special-clause count exceeds its bound"
            )
        return tuple(result)

    def _record_dependencies(
        spec: _PoisonSpec,
    ) -> tuple[PoisonDependency, ...]:
        if spec.definition_status != "source-incomplete":
            return ()
        return (
            new_artifact_impl(
                dependency_type,
                (
                    "dependency_id",
                    "phase",
                    "required_contract",
                    "provider_rule_id",
                ),
                (
                    f"{spec.rule_id}:source-completion",
                    "source-completeness",
                    (
                        "authoritative Giant Viper stage 2 interval or "
                        "terminal disposition"
                    ),
                    None,
                ),
            ),
        )  # type: ignore[return-value]

    def _canonical_compiled(
        authority: SourceAuthorityAdapter,
        rule: VerifiedRuleReceipt,
        spec: _PoisonSpec,
    ) -> CompiledPoisonAffliction:
        authority.validate_rule(rule)
        selection = authority.validate_selection(rule.selection)
        source_shape, traits, action, source_text, plain = (
            ability_parts_impl(selection)
        )
        if (
            source_shape != spec.source_shape
            or traits != spec.traits
            or "poison" not in traits
        ):
            raise compile_error_type(
                "poison carrier shape or traits differ from review"
            )
        creature_name = unique_member_impl(
            selection.carrier.raw_block,
            "Name",
        )
        if creature_name != spec.creature_name:
            raise compile_error_type(
                "poison carrier creature name differs from review"
            )
        if spec.classification == "affliction-alias":
            alias_match = alias_re.fullmatch(plain)
            if alias_match is None:
                raise compile_error_type(
                    "reviewed poison alias grammar differs from source"
                )
            saving_throw = None
            onset = None
            maximum_duration = None
            stages: tuple[PoisonStage, ...] = ()
            alias_target = alias_match.group("target")
            alias_dc = int(alias_match.group("dc"))
        else:
            saving_throw = save_impl(
                plain,
                save_type,
                new_artifact_impl,
            )
            if saving_throw is None:
                raise compile_error_type(
                    "poison definition lacks a saving throw"
                )
            onset = optional_duration_impl(
                onset_re,
                plain,
                duration_type,
                new_artifact_impl,
            )
            maximum_duration = optional_duration_impl(
                maximum_duration_re,
                plain,
                duration_type,
                new_artifact_impl,
            )
            stages = stages_impl(
                plain,
                spec.rule_id,
                spec.definition_status,
                stage_type,
                duration_type,
                new_artifact_impl,
            )
            if not stages:
                raise compile_error_type(
                    "poison definition lacks ordered stages"
                )
            alias_target = None
            alias_dc = None
        return new_artifact_impl(
            compiled_type,
            (
                "record_id",
                "sequence",
                "creature_name",
                "ability_name",
                "locator",
                "classification",
                "definition_status",
                "source_shape",
                "traits",
                "action_cost",
                "source_text",
                "source_text_sha256",
                "saving_throw",
                "onset",
                "maximum_duration",
                "stages",
                "alias_target_creature",
                "alias_dc_override",
                "special_clauses",
                "dependencies",
                "consumer_rule",
            ),
            (
                spec.rule_id,
                spec.sequence,
                spec.creature_name,
                spec.ability_name,
                spec.locator,
                spec.classification,
                spec.definition_status,
                source_shape,
                traits,
                action,
                source_text,
                sha256_impl(source_text.encode("utf-8")).hexdigest(),
                saving_throw,
                onset,
                maximum_duration,
                stages,
                alias_target,
                alias_dc,
                _special_clauses(spec, plain),
                _record_dependencies(spec),
                rule,
            ),
        )  # type: ignore[return-value]

    def _selected_source_text(
        value: RawSourceObject,
        ability_name: str,
    ) -> str:
        ability_normalized = normalized_impl(ability_name)
        result: list[str] = []
        for key in ("Damage", "Effects", "Effect", "Description"):
            field = unique_member_impl(value, key)
            if field is None:
                continue
            text = flow_text_impl(field, f"poison delivery {key}")
            if ability_normalized in normalized_impl(text):
                result.append(text)
        if not result:
            raise link_error_type(
                "poison delivery lacks exact authored exposure text"
            )
        source_text = "; ".join(result)
        if len(source_text.encode("utf-8")) > max_text_bytes:
            raise link_error_type(
                "poison delivery source text exceeds its bound"
            )
        return source_text

    def _deliveries_and_related(
        authority: SourceAuthorityAdapter,
        records: tuple[CompiledPoisonAffliction, ...],
    ) -> tuple[
        tuple[PoisonDelivery, ...],
        tuple[PoisonRelatedUse, ...],
    ]:
        deliveries: list[PoisonDelivery] = []
        related: list[PoisonRelatedUse] = []
        for record in records:
            carrier = record.consumer_rule.selection.carrier
            root = carrier.raw_block
            if (
                type(root) is not raw_object_type
                or len(root.members) > max_members
            ):
                raise link_error_type(
                    "poison carrier exceeds its member bound"
                )
            ability_normalized = normalized_impl(record.ability_name)
            definition_ordinal = (
                record.consumer_rule.selection.address
                .selection_path[0].member_ordinal
            )
            for ordinal, member in enumerate(root.members):
                if ordinal == definition_ordinal:
                    continue
                member_path = (member_step_type(member.key, ordinal),)
                if member.key in {"Melee", "Ranged"}:
                    if type(member.value) is not raw_array_type:
                        raise link_error_type(
                            "poison Strike collection must be an array"
                        )
                    if len(member.value.items) > max_strikes:
                        raise link_error_type(
                            "poison Strike collection exceeds its bound"
                        )
                    for item_ordinal, strike in enumerate(
                        member.value.items
                    ):
                        if type(strike) is not raw_object_type:
                            raise link_error_type(
                                "poison Strike must be an exact object"
                            )
                        searchable = " ".join(raw_texts_impl(strike))
                        if ability_normalized not in normalized_impl(
                            searchable
                        ):
                            continue
                        source_name = unique_member_impl(strike, "Name")
                        if (
                            type(source_name) is not str
                            or not source_name
                        ):
                            raise link_error_type(
                                "poison Strike lacks an exact name"
                            )
                        source_text = _selected_source_text(
                            strike,
                            record.ability_name,
                        )
                        source_selection = carrier.select(
                            (
                                member_path[0],
                                index_step_type(item_ordinal),
                            )
                        )
                        authority.validate_selection(source_selection)
                        deliveries.append(
                            new_artifact_impl(
                                delivery_type,
                                (
                                    "delivery_id",
                                    "record_id",
                                    "creature_name",
                                    "source_name",
                                    "delivery_kind",
                                    "delivery_mode",
                                    "traits",
                                    "source_text",
                                    "source_selection",
                                ),
                                (
                                    (
                                        "poison-delivery:"
                                        f"{len(deliveries) + 1:03d}"
                                    ),
                                    record.record_id,
                                    record.creature_name,
                                    source_name,
                                    "strike-rider",
                                    (
                                        "strike-rider-choice"
                                        if " or " in source_text.casefold()
                                        else "successful-strike-rider"
                                    ),
                                    traits_impl(strike),
                                    source_text,
                                    source_selection,
                                ),
                            )
                        )
                    continue
                if member.key == "Items":
                    searchable = " ".join(raw_texts_impl(member.value))
                    if ability_normalized not in normalized_impl(searchable):
                        continue
                    if type(member.value) is not raw_array_type:
                        raise link_error_type(
                            "poison-bearing Items must be an array"
                        )
                    source_text = "; ".join(
                        item
                        for item in member.value.items
                        if type(item) is str
                        and ability_normalized
                        in normalized_impl(item)
                    )
                    if not source_text:
                        raise link_error_type(
                            "poison-bearing Items lack authored text"
                        )
                    source_selection = carrier.select(member_path)
                    authority.validate_selection(source_selection)
                    related.append(
                        new_artifact_impl(
                            related_type,
                            (
                                "related_id",
                                "record_id",
                                "creature_name",
                                "source_name",
                                "relationship",
                                "source_text",
                                "source_selection",
                            ),
                            (
                                (
                                    "poison-related:"
                                    f"{len(related) + 1:03d}"
                                ),
                                record.record_id,
                                record.creature_name,
                                "Items",
                                "coated-ammunition-inventory",
                                source_text,
                                source_selection,
                            ),
                        )
                    )
                    continue
                if (
                    not member.key.startswith("!.")
                    or type(member.value) is not raw_object_type
                ):
                    continue
                searchable = " ".join(raw_texts_impl(member.value))
                if ability_normalized not in normalized_impl(searchable):
                    continue
                description = flow_text_impl(
                    unique_member_impl(member.value, "Description"),
                    f"{member.key} Description",
                )
                description_normalized = normalized_impl(description)
                source_name = member.key.removeprefix("!.")
                if (
                    f"exposed to {ability_normalized}"
                    in description_normalized
                    or f"plus {ability_normalized}"
                    in description_normalized
                ):
                    source_selection = carrier.select(member_path)
                    authority.validate_selection(source_selection)
                    deliveries.append(
                        new_artifact_impl(
                            delivery_type,
                            (
                                "delivery_id",
                                "record_id",
                                "creature_name",
                                "source_name",
                                "delivery_kind",
                                "delivery_mode",
                                "traits",
                                "source_text",
                                "source_selection",
                            ),
                            (
                                (
                                    "poison-delivery:"
                                    f"{len(deliveries) + 1:03d}"
                                ),
                                record.record_id,
                                record.creature_name,
                                source_name,
                                "named-ability-exposure",
                                "authored-exposure",
                                traits_impl(member.value),
                                description,
                                source_selection,
                            ),
                        )
                    )
                    continue
                relationship_by_name = {
                    "Mind-Rending Sting": (
                        "conditional-virulent-promotion"
                    ),
                    "Spiritual Venom": (
                        "damage-suppression-and-spell-targeting"
                    ),
                }
                relationship = relationship_by_name.get(source_name)
                if relationship is None:
                    raise link_error_type(
                        "unreviewed poison-related ability was discovered"
                    )
                source_selection = carrier.select(member_path)
                authority.validate_selection(source_selection)
                static_spec = static_related_by_record.get(
                    record.record_id
                )
                if static_spec is not None:
                    if (
                        source_name != static_spec[1]
                        or member_path != path_impl(static_spec[2])
                        or source_selection.selection_sha256
                        != static_spec[3]
                        or relationship != static_spec[4]
                    ):
                        raise link_error_type(
                            "reviewed poison-related ability drifted"
                        )
                related.append(
                    new_artifact_impl(
                        related_type,
                        (
                            "related_id",
                            "record_id",
                            "creature_name",
                            "source_name",
                            "relationship",
                            "source_text",
                            "source_selection",
                        ),
                        (
                            (
                                "poison-related:"
                                f"{len(related) + 1:03d}"
                            ),
                            record.record_id,
                            record.creature_name,
                            source_name,
                            relationship,
                            description,
                            source_selection,
                        ),
                    )
                )
            static_spec = static_related_by_record.get(record.record_id)
            if (
                static_spec is not None
                and not any(
                    item.record_id == record.record_id
                    and item.source_name == static_spec[1]
                    for item in related
                )
            ):
                source_selection = carrier.select(
                    path_impl(static_spec[2])
                )
                authority.validate_selection(source_selection)
                if source_selection.selection_sha256 != static_spec[3]:
                    raise link_error_type(
                        "reviewed poison-related ability drifted"
                    )
                if type(source_selection.selected_value) is str:
                    description = flow_text_impl(
                        source_selection.selected_value,
                        f"{static_spec[1]} Description",
                    )
                elif (
                    type(source_selection.selected_value)
                    is raw_object_type
                ):
                    description = flow_text_impl(
                        unique_member_impl(
                            source_selection.selected_value,
                            "Description",
                        ),
                        f"{static_spec[1]} Description",
                    )
                else:
                    raise link_error_type(
                        "reviewed poison-related ability has invalid source"
                    )
                related.append(
                    new_artifact_impl(
                        related_type,
                        (
                            "related_id",
                            "record_id",
                            "creature_name",
                            "source_name",
                            "relationship",
                            "source_text",
                            "source_selection",
                        ),
                        (
                            (
                                "poison-related:"
                                f"{len(related) + 1:03d}"
                            ),
                            record.record_id,
                            record.creature_name,
                            static_spec[1],
                            static_spec[4],
                            description,
                            source_selection,
                        ),
                    )
                )
        if (
            len(deliveries) != delivery_count
            or len(related) != related_count
        ):
            raise link_error_type(
                "derived poison delivery census differs from review: "
                f"deliveries={len(deliveries)}, related={len(related)}"
            )
        return tuple(deliveries), tuple(related)

    def _alias_links(
        records: tuple[CompiledPoisonAffliction, ...],
    ) -> tuple[PoisonAliasLink, ...]:
        records_by_id = {record.record_id: record for record in records}
        result: list[PoisonAliasLink] = []
        for alias_id, definition_id, dc in alias_specs:
            alias = records_by_id.get(alias_id)
            definition = records_by_id.get(definition_id)
            if (
                alias is None
                or definition is None
                or alias.classification != "affliction-alias"
                or definition.classification != "affliction-definition"
                or alias.alias_dc_override != dc
                or alias.alias_target_creature is None
                or normalized_impl(alias.alias_target_creature)
                != normalized_impl(definition.creature_name)
            ):
                raise link_error_type(
                    "reviewed poison alias cannot be resolved exactly"
                )
            result.append(
                new_artifact_impl(
                    alias_link_type,
                    (
                        "alias_record_id",
                        "definition_record_id",
                        "resolved_dc",
                    ),
                    (alias_id, definition_id, dc),
                )
            )
        return tuple(result)

    def _progression_rules() -> PoisonProgressionRules:
        return new_artifact_impl(
            progression_type,
            (
                "initial_success_unaffected",
                "initial_failure_stage",
                "initial_critical_failure_stage",
                "interval_critical_success_delta",
                "interval_success_delta",
                "interval_failure_delta",
                "interval_critical_failure_delta",
                "repeat_highest_stage",
                "below_stage_one_ends",
                "apply_effect_on_stage_entry",
                "provider_rule_ids",
            ),
            (
                True,
                1,
                2,
                -2,
                -1,
                1,
                2,
                True,
                True,
                True,
                (
                    "affliction-save",
                    "affliction-stage",
                    "affliction-effect",
                ),
            ),
        )  # type: ignore[return-value]

    def _exposure_rules() -> PoisonExposureRules:
        return new_artifact_impl(
            exposure_type,
            (
                "successful_exposure_unchanged",
                "failure_stage_delta",
                "critical_failure_stage_delta",
                "preserves_maximum_duration",
                "preserves_onset_length",
                "immediate_effect_after_onset",
                "provider_rule_ids",
            ),
            (
                True,
                1,
                2,
                True,
                True,
                True,
                ("multiple-exposures",),
            ),
        )  # type: ignore[return-value]

    def _recovery_rules() -> PoisonRecoveryRules:
        return new_artifact_impl(
            recovery_type,
            (
                "ordinary_successes_required",
                "virulent_consecutive_successes_required",
                "virulent_critical_success_delta",
                "treat_poison_critical_success_bonus",
                "treat_poison_success_bonus",
                "treat_poison_critical_failure_penalty",
                "provider_rule_ids",
            ),
            (
                1,
                2,
                -1,
                4,
                2,
                -2,
                (
                    "virulent",
                    "removing-afflictions",
                    "treat-poison",
                    "cleanse-affliction",
                ),
            ),
        )  # type: ignore[return-value]

    def _runtime_dependencies() -> tuple[PoisonDependency, ...]:
        return tuple(
            new_artifact_impl(
                dependency_type,
                (
                    "dependency_id",
                    "phase",
                    "required_contract",
                    "provider_rule_id",
                ),
                (
                    dependency_id,
                    phase,
                    contract,
                    runtime_provider_map[dependency_id],
                ),
            )
            for dependency_id, phase, contract in runtime_specs
        )  # type: ignore[return-value]

    def _canonical_corpus(
        authority: SourceAuthorityAdapter,
        records: tuple[CompiledPoisonAffliction, ...],
        provider_rules: tuple[VerifiedRuleReceipt, ...],
    ) -> LinkedPoisonCorpus:
        for record in records:
            authority.require_shared_authority(
                record.consumer_rule.selection,
                provider_rules,
            )
        deliveries, related = _deliveries_and_related(
            authority,
            records,
        )
        return new_artifact_impl(
            corpus_type,
            (
                "records",
                "provider_rules",
                "alias_links",
                "deliveries",
                "related_uses",
                "progression_rules",
                "exposure_rules",
                "recovery_rules",
                "dependencies",
            ),
            (
                records,
                provider_rules,
                _alias_links(records),
                deliveries,
                related,
                _progression_rules(),
                _exposure_rules(),
                _recovery_rules(),
                _runtime_dependencies(),
            ),
        )  # type: ignore[return-value]

    def _bounded_text(value: object, label: str) -> str:
        if (
            type(value) is not str
            or not value
            or "\x00" in value
            or len(value.encode("utf-8")) > max_text_bytes
        ):
            raise link_error_type(f"{label} is outside its text bound")
        return value

    def _identifier(value: object, label: str) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or "\x00" in value
            or len(value.encode("utf-8")) > max_identifier_bytes
        ):
            raise link_error_type(f"{label} is not an exact identifier")
        return value

    def _duration_payload(
        value: PoisonDuration | None,
    ) -> dict[str, object] | None:
        if value is None:
            return None
        if (
            type(value) is not duration_type
            or type(value.source_text) is not str
            or value.amount_kind not in {"fixed", "dice"}
            or value.unit
            not in {"round", "minute", "hour", "day", "week"}
        ):
            raise link_error_type("stored poison duration is invalid")
        if value.amount_kind == "fixed":
            if (
                type(value.fixed_amount) is not int
                or value.fixed_amount <= 0
                or value.dice_count is not None
                or value.dice_sides is not None
                or value.dice_modifier is not None
            ):
                raise link_error_type(
                    "stored fixed poison duration is invalid"
                )
        elif (
            value.fixed_amount is not None
            or type(value.dice_count) is not int
            or value.dice_count <= 0
            or type(value.dice_sides) is not int
            or value.dice_sides <= 0
            or type(value.dice_modifier) is not int
        ):
            raise link_error_type(
                "stored dice poison duration is invalid"
            )
        return {
            "sourceText": value.source_text,
            "amountKind": value.amount_kind,
            "fixedAmount": value.fixed_amount,
            "diceCount": value.dice_count,
            "diceSides": value.dice_sides,
            "diceModifier": value.dice_modifier,
            "unit": value.unit,
        }

    def _save_payload(
        value: PoisonSave | None,
    ) -> dict[str, object] | None:
        if value is None:
            return None
        if (
            type(value) is not save_type
            or type(value.dc) is not int
            or value.dc <= 0
            or value.save_type not in {"fortitude", "reflex", "will"}
            or type(value.basic) is not bool
            or type(value.source_text) is not str
            or not value.source_text
        ):
            raise link_error_type("stored poison save is invalid")
        return {
            "dc": value.dc,
            "saveType": value.save_type,
            "basic": value.basic,
            "sourceText": value.source_text,
        }

    def _stage_payload(value: PoisonStage) -> dict[str, object]:
        if (
            type(value) is not stage_type
            or type(value.number) is not int
            or value.number <= 0
            or type(value.source_text) is not str
            or not value.source_text
            or type(value.effect_text) is not str
            or not value.effect_text
            or type(value.effect_durations) is not tuple
            or len(value.effect_durations) > max_special
            or type(value.permanent_effect) is not bool
            or type(value.terminal) is not bool
            or (
                value.terminal_reason is not None
                and type(value.terminal_reason) is not str
            )
            or type(value.source_complete) is not bool
        ):
            raise link_error_type("stored poison stage is invalid")
        return {
            "number": value.number,
            "sourceText": value.source_text,
            "effectText": value.effect_text,
            "interval": _duration_payload(value.interval),
            "effectDurations": [
                _duration_payload(item)
                for item in value.effect_durations
            ],
            "permanentEffect": value.permanent_effect,
            "terminal": value.terminal,
            "terminalReason": value.terminal_reason,
            "sourceComplete": value.source_complete,
        }

    def _special_payload(
        value: PoisonSpecialClause,
    ) -> dict[str, object]:
        if type(value) is not special_type:
            raise link_error_type(
                "stored poison special clause is invalid"
            )
        return {
            "clauseId": _identifier(value.clause_id, "clause id"),
            "kind": _identifier(value.kind, "clause kind"),
            "sourceText": _bounded_text(
                value.source_text,
                "clause source text",
            ),
            "requiredContract": _identifier(
                value.required_contract,
                "clause contract",
            ),
        }

    def _dependency_payload(
        value: PoisonDependency,
    ) -> dict[str, object]:
        if type(value) is not dependency_type:
            raise link_error_type("stored poison dependency is invalid")
        provider_rule_id = value.provider_rule_id
        if provider_rule_id is not None:
            _identifier(provider_rule_id, "dependency provider rule")
        return {
            "dependencyId": _identifier(
                value.dependency_id,
                "dependency id",
            ),
            "phase": _identifier(value.phase, "dependency phase"),
            "requiredContract": _bounded_text(
                value.required_contract,
                "dependency contract",
            ),
            "providerRuleId": provider_rule_id,
            "status": "deferred",
        }

    def _compiled_payload(
        value: CompiledPoisonAffliction,
    ) -> dict[str, object]:
        if (
            type(value) is not compiled_type
            or type(value.sequence) is not int
            or value.sequence < 0
            or value.classification
            not in {"affliction-definition", "affliction-alias"}
            or value.definition_status
            not in {"complete", "source-incomplete", "alias"}
            or value.source_shape not in {"scalar", "ordered-object"}
            or type(value.traits) is not tuple
            or any(type(item) is not str for item in value.traits)
            or value.action_cost
            not in {None, 1, 2, 3, "free", "reaction"}
            or type(value.source_text_sha256) is not str
            or len(value.source_text_sha256) != 64
            or type(value.stages) is not tuple
            or len(value.stages) > max_stages
            or type(value.special_clauses) is not tuple
            or len(value.special_clauses) > max_special
            or type(value.dependencies) is not tuple
            or len(value.dependencies) > max_special
            or type(value.consumer_rule) is not verified_rule_type
        ):
            raise link_error_type("stored compiled poison is invalid")
        source_text = _bounded_text(
            value.source_text,
            "compiled poison source text",
        )
        if (
            sha256_impl(source_text.encode("utf-8")).hexdigest()
            != value.source_text_sha256
        ):
            raise link_error_type(
                "compiled poison source text hash disagrees"
            )
        return {
            "family": family_id,
            "mechanicType": mechanic_type,
            "recordId": _identifier(value.record_id, "poison record id"),
            "sequence": value.sequence,
            "creature": _identifier(
                value.creature_name,
                "poison creature name",
            ),
            "ability": _identifier(
                value.ability_name,
                "poison ability name",
            ),
            "locator": _identifier(value.locator, "poison locator"),
            "classification": value.classification,
            "definitionStatus": value.definition_status,
            "sourceShape": value.source_shape,
            "traits": list(value.traits),
            "actionCost": value.action_cost,
            "sourceText": source_text,
            "sourceTextSha256": value.source_text_sha256,
            "savingThrow": _save_payload(value.saving_throw),
            "onset": _duration_payload(value.onset),
            "maximumDuration": _duration_payload(
                value.maximum_duration
            ),
            "stages": [
                _stage_payload(item) for item in value.stages
            ],
            "aliasTargetCreature": value.alias_target_creature,
            "aliasDcOverride": value.alias_dc_override,
            "specialClauses": [
                _special_payload(item)
                for item in value.special_clauses
            ],
            "dependencies": [
                _dependency_payload(item)
                for item in value.dependencies
            ],
            "consumerRule": verified_rule_type.as_serialized(
                value.consumer_rule
            ),
            "runtimeSupported": False,
            "registryStatus": registry_status,
            "activationStatus": "deferred",
        }

    def _alias_payload(value: PoisonAliasLink) -> dict[str, object]:
        if (
            type(value) is not alias_link_type
            or type(value.resolved_dc) is not int
            or value.resolved_dc <= 0
        ):
            raise link_error_type("stored poison alias link is invalid")
        return {
            "aliasRecordId": _identifier(
                value.alias_record_id,
                "alias record id",
            ),
            "definitionRecordId": _identifier(
                value.definition_record_id,
                "alias definition id",
            ),
            "resolvedDc": value.resolved_dc,
        }

    def _delivery_payload(value: PoisonDelivery) -> dict[str, object]:
        if (
            type(value) is not delivery_type
            or value.delivery_kind
            not in {"strike-rider", "named-ability-exposure"}
            or type(value.traits) is not tuple
            or any(type(item) is not str for item in value.traits)
            or type(value.source_selection) is not verified_selection_type
        ):
            raise link_error_type("stored poison delivery is invalid")
        return {
            "deliveryId": _identifier(
                value.delivery_id,
                "poison delivery id",
            ),
            "recordId": _identifier(
                value.record_id,
                "poison delivery record id",
            ),
            "creature": _identifier(
                value.creature_name,
                "poison delivery creature",
            ),
            "sourceName": _identifier(
                value.source_name,
                "poison delivery source name",
            ),
            "kind": value.delivery_kind,
            "mode": _identifier(
                value.delivery_mode,
                "poison delivery mode",
            ),
            "traits": list(value.traits),
            "sourceText": _bounded_text(
                value.source_text,
                "poison delivery source text",
            ),
            "source": receipt_type.as_serialized(
                value.source_selection.receipt
            ),
            "runtimeSupported": False,
        }

    def _related_payload(value: PoisonRelatedUse) -> dict[str, object]:
        if (
            type(value) is not related_type
            or type(value.source_selection) is not verified_selection_type
        ):
            raise link_error_type("stored poison related use is invalid")
        return {
            "relatedId": _identifier(
                value.related_id,
                "poison related id",
            ),
            "recordId": _identifier(
                value.record_id,
                "poison related record id",
            ),
            "creature": _identifier(
                value.creature_name,
                "poison related creature",
            ),
            "sourceName": _identifier(
                value.source_name,
                "poison related source name",
            ),
            "relationship": _identifier(
                value.relationship,
                "poison relationship",
            ),
            "sourceText": _bounded_text(
                value.source_text,
                "poison related source text",
            ),
            "source": receipt_type.as_serialized(
                value.source_selection.receipt
            ),
            "runtimeSupported": False,
        }

    def _progression_payload(
        value: PoisonProgressionRules,
    ) -> dict[str, object]:
        if (
            type(value) is not progression_type
            or type(value.provider_rule_ids) is not tuple
            or any(
                type(item) is not str
                for item in value.provider_rule_ids
            )
        ):
            raise link_error_type(
                "stored poison progression rules are invalid"
            )
        return {
            "initialSuccessUnaffected": value.initial_success_unaffected,
            "initialFailureStage": value.initial_failure_stage,
            "initialCriticalFailureStage": (
                value.initial_critical_failure_stage
            ),
            "intervalCriticalSuccessDelta": (
                value.interval_critical_success_delta
            ),
            "intervalSuccessDelta": value.interval_success_delta,
            "intervalFailureDelta": value.interval_failure_delta,
            "intervalCriticalFailureDelta": (
                value.interval_critical_failure_delta
            ),
            "repeatHighestStage": value.repeat_highest_stage,
            "belowStageOneEnds": value.below_stage_one_ends,
            "applyEffectOnStageEntry": (
                value.apply_effect_on_stage_entry
            ),
            "providerRuleIds": list(value.provider_rule_ids),
        }

    def _exposure_payload(
        value: PoisonExposureRules,
    ) -> dict[str, object]:
        if (
            type(value) is not exposure_type
            or type(value.provider_rule_ids) is not tuple
            or any(
                type(item) is not str
                for item in value.provider_rule_ids
            )
        ):
            raise link_error_type(
                "stored poison exposure rules are invalid"
            )
        return {
            "successfulExposureUnchanged": (
                value.successful_exposure_unchanged
            ),
            "failureStageDelta": value.failure_stage_delta,
            "criticalFailureStageDelta": (
                value.critical_failure_stage_delta
            ),
            "preservesMaximumDuration": (
                value.preserves_maximum_duration
            ),
            "preservesOnsetLength": value.preserves_onset_length,
            "immediateEffectAfterOnset": (
                value.immediate_effect_after_onset
            ),
            "providerRuleIds": list(value.provider_rule_ids),
        }

    def _recovery_payload(
        value: PoisonRecoveryRules,
    ) -> dict[str, object]:
        if (
            type(value) is not recovery_type
            or type(value.provider_rule_ids) is not tuple
            or any(
                type(item) is not str
                for item in value.provider_rule_ids
            )
        ):
            raise link_error_type(
                "stored poison recovery rules are invalid"
            )
        return {
            "ordinarySuccessesRequired": (
                value.ordinary_successes_required
            ),
            "virulentConsecutiveSuccessesRequired": (
                value.virulent_consecutive_successes_required
            ),
            "virulentCriticalSuccessDelta": (
                value.virulent_critical_success_delta
            ),
            "treatPoisonCriticalSuccessBonus": (
                value.treat_poison_critical_success_bonus
            ),
            "treatPoisonSuccessBonus": (
                value.treat_poison_success_bonus
            ),
            "treatPoisonCriticalFailurePenalty": (
                value.treat_poison_critical_failure_penalty
            ),
            "providerRuleIds": list(value.provider_rule_ids),
        }

    def _corpus_payload(value: LinkedPoisonCorpus) -> dict[str, object]:
        if (
            type(value) is not corpus_type
            or type(value.records) is not tuple
            or len(value.records) > max_records
            or type(value.provider_rules) is not tuple
            or len(value.provider_rules) > provider_count
            or type(value.alias_links) is not tuple
            or len(value.alias_links) > max_records
            or type(value.deliveries) is not tuple
            or len(value.deliveries) > max_deliveries
            or type(value.related_uses) is not tuple
            or len(value.related_uses) > max_related
            or type(value.dependencies) is not tuple
            or len(value.dependencies) > max_special
        ):
            raise link_error_type("stored poison corpus is invalid")
        return {
            "family": family_id,
            "mechanicType": mechanic_type,
            "officialCreatureCensus": official_creature_count,
            "reviewedCounts": {
                "carriers": carrier_count,
                "definitions": definition_count,
                "aliases": alias_count,
                "stages": stage_count,
                "deliveries": delivery_count,
                "relatedUses": related_count,
                "specialClauses": special_count,
                "sourceBlockers": source_blocker_count,
            },
            "records": [
                _compiled_payload(item) for item in value.records
            ],
            "providerRules": [
                verified_rule_type.as_serialized(item)
                for item in value.provider_rules
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
            "progressionRules": _progression_payload(
                value.progression_rules
            ),
            "exposureRules": _exposure_payload(value.exposure_rules),
            "recoveryRules": _recovery_payload(value.recovery_rules),
            "dependencies": [
                _dependency_payload(item)
                for item in value.dependencies
            ],
            "runtimeSupported": False,
            "registryStatus": registry_status,
            "activationStatus": "deferred",
        }

    def _validated_records(
        authority: SourceAuthorityAdapter,
        records: tuple[CompiledPoisonAffliction, ...],
    ) -> tuple[CompiledPoisonAffliction, ...]:
        if type(records) is not tuple:
            raise TypeError("poison records must be an exact tuple")
        if len(records) != carrier_count:
            raise link_error_type(
                "poison records must contain the complete reviewed census"
            )
        if any(type(item) is not compiled_type for item in records):
            raise TypeError("poison records must contain exact artifacts")
        if tuple(item.record_id for item in records) != tuple(
            spec.rule_id for spec in poison_specs
        ):
            raise link_error_type(
                "poison records are not in reviewed source order"
            )
        for record in records:
            _validate_compiled(authority, record)
        if (
            sum(len(record.stages) for record in records) != stage_count
            or sum(
                len(record.special_clauses) for record in records
            )
            != special_count
        ):
            raise link_error_type(
                "compiled poison stage or special-clause census drifted"
            )
        return records

    def _validated_provider_rules(
        authority: SourceAuthorityAdapter,
        rules: tuple[VerifiedRuleReceipt, ...],
    ) -> tuple[VerifiedRuleReceipt, ...]:
        if type(rules) is not tuple or len(rules) != provider_count:
            raise link_error_type(
                "poison provider rules must contain the reviewed set"
            )
        fresh = _provider_rules(authority)
        for supplied, canonical, requirement in zip(
            rules,
            fresh,
            reviewed_provider_requirements,
            strict=True,
        ):
            if type(supplied) is not verified_rule_type:
                raise TypeError("poison provider rules must be exact")
            authority.validate_rule(supplied)
            if (
                not same_requirement_impl(
                    supplied.requirement,
                    requirement,
                )
                or not same_receipt_impl(
                    supplied.receipt,
                    canonical.receipt,
                )
            ):
                raise link_error_type(
                    "poison provider rule differs from review"
                )
        return fresh

    def _validate_compiled(
        authority: SourceAuthorityAdapter,
        value: CompiledPoisonAffliction,
    ) -> dict[str, object]:
        _require_authority(authority)
        if type(value) is not compiled_type:
            raise TypeError("compiled poison artifact must be exact")
        fresh_rule, spec = _validated_consumer_rule(
            authority,
            value.consumer_rule,
        )
        canonical = _canonical_compiled(
            authority,
            fresh_rule,
            spec,
        )
        supplied_payload = _compiled_payload(value)
        canonical_payload = _compiled_payload(canonical)
        if canonical_json_impl(
            supplied_payload
        ) != canonical_json_impl(canonical_payload):
            raise compile_error_type(
                "compiled poison differs from current source authority"
            )
        return supplied_payload

    def _validate_corpus(
        authority: SourceAuthorityAdapter,
        value: LinkedPoisonCorpus,
    ) -> dict[str, object]:
        _require_authority(authority)
        if type(value) is not corpus_type:
            raise TypeError("linked poison corpus must be exact")
        records = _validated_records(authority, value.records)
        providers = _validated_provider_rules(
            authority,
            value.provider_rules,
        )
        for delivery in value.deliveries:
            if type(delivery) is not delivery_type:
                raise TypeError("poison delivery must be exact")
            authority.validate_selection(delivery.source_selection)
        for related in value.related_uses:
            if type(related) is not related_type:
                raise TypeError("poison related use must be exact")
            authority.validate_selection(related.source_selection)
        canonical = _canonical_corpus(authority, records, providers)
        supplied_payload = _corpus_payload(value)
        canonical_payload = _corpus_payload(canonical)
        if canonical_json_impl(
            supplied_payload
        ) != canonical_json_impl(canonical_payload):
            raise link_error_type(
                "linked poison corpus differs from current authority"
            )
        return supplied_payload

    def poison_consumer_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(
            consumer_requirement_impl(spec) for spec in poison_specs
        )

    def poison_provider_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(
            provider_requirement_impl(spec) for spec in provider_specs
        )

    def compile_poison(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
    ) -> CompiledPoisonAffliction:
        rule, spec = _consumer_rule_and_spec(authority, receipt)
        return _canonical_compiled(authority, rule, spec)

    def compile_poison_census(
        authority: SourceAuthorityAdapter,
    ) -> tuple[CompiledPoisonAffliction, ...]:
        _require_authority(authority)
        return tuple(
            _canonical_compiled(
                authority,
                authority.resolve_rule(requirement),
                spec,
            )
            for spec, requirement in zip(
                poison_specs,
                reviewed_requirements,
                strict=True,
            )
        )

    def validate_compiled_poison(
        authority: SourceAuthorityAdapter,
        value: CompiledPoisonAffliction,
    ) -> CompiledPoisonAffliction:
        _validate_compiled(authority, value)
        return value

    def link_poison_corpus(
        authority: SourceAuthorityAdapter,
        records: tuple[CompiledPoisonAffliction, ...],
    ) -> LinkedPoisonCorpus:
        _require_authority(authority)
        records = _validated_records(authority, records)
        providers = _provider_rules(authority)
        return _canonical_corpus(authority, records, providers)

    def validate_linked_poison_corpus(
        authority: SourceAuthorityAdapter,
        value: LinkedPoisonCorpus,
    ) -> LinkedPoisonCorpus:
        _validate_corpus(authority, value)
        return value

    def compiled_as_serialized(
        self: CompiledPoisonAffliction,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, object]:
        return _validate_compiled(authority, self)

    def corpus_as_serialized(
        self: LinkedPoisonCorpus,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, object]:
        return _validate_corpus(authority, self)

    return (
        poison_consumer_requirements,
        poison_provider_requirements,
        compile_poison,
        compile_poison_census,
        validate_compiled_poison,
        link_poison_corpus,
        validate_linked_poison_corpus,
        compiled_as_serialized,
        corpus_as_serialized,
    )


(
    poison_consumer_requirements,
    poison_provider_requirements,
    compile_poison,
    compile_poison_census,
    validate_compiled_poison,
    link_poison_corpus,
    validate_linked_poison_corpus,
    _compiled_as_serialized,
    _corpus_as_serialized,
) = _bind_reviewed_api(
    poison_specs=_POISON_SPECS,
    provider_specs=_PROVIDER_SPECS,
    alias_specs=_ALIAS_LINK_SPECS,
    special_specs=_SPECIAL_CLAUSE_SPECS,
    static_related_specs=_STATIC_RELATED_USE_SPECS,
    runtime_specs=_RUNTIME_DEPENDENCY_SPECS,
    adapter_type=SourceAuthorityAdapter,
    receipt_type=SourceReceipt,
    verified_rule_type=VerifiedRuleReceipt,
    verified_selection_type=VerifiedSourceSelection,
    raw_object_type=RawSourceObject,
    raw_array_type=RawSourceArray,
    member_step_type=RawMemberStep,
    index_step_type=RawIndexStep,
    duration_type=PoisonDuration,
    save_type=PoisonSave,
    stage_type=PoisonStage,
    special_type=PoisonSpecialClause,
    dependency_type=PoisonDependency,
    compiled_type=CompiledPoisonAffliction,
    alias_link_type=PoisonAliasLink,
    delivery_type=PoisonDelivery,
    related_type=PoisonRelatedUse,
    progression_type=PoisonProgressionRules,
    exposure_type=PoisonExposureRules,
    recovery_type=PoisonRecoveryRules,
    corpus_type=LinkedPoisonCorpus,
    compile_error_type=PoisonCompileError,
    link_error_type=PoisonLinkError,
    consumer_requirement_impl=_consumer_requirement,
    provider_requirement_impl=_provider_requirement,
    same_requirement_impl=_same_requirement,
    same_receipt_impl=_same_receipt,
    ability_parts_impl=_ability_parts,
    save_impl=_save,
    optional_duration_impl=_optional_duration,
    stages_impl=_stages,
    path_impl=_path_from_spec,
    unique_member_impl=_unique_member,
    flow_text_impl=_flow_text,
    normalized_impl=_normalized,
    raw_texts_impl=_raw_texts,
    traits_impl=_traits_from_object,
    new_artifact_impl=_new_artifact,
    canonical_json_impl=canonical_json_bytes,
    sha256_impl=hashlib.sha256,
    onset_re=_ONSET_RE,
    maximum_duration_re=_MAX_DURATION_RE,
    alias_re=_ALIAS_RE,
    source_scope=SOURCE_SCOPE,
    family_id=FAMILY_ID,
    mechanic_type=MECHANIC_TYPE,
    registry_status=REGISTRY_STATUS,
    official_creature_count=OFFICIAL_CREATURE_CENSUS_COUNT,
    carrier_count=POISON_CARRIER_COUNT,
    definition_count=POISON_DEFINITION_COUNT,
    alias_count=POISON_ALIAS_COUNT,
    stage_count=POISON_STAGE_COUNT,
    delivery_count=POISON_DELIVERY_COUNT,
    related_count=POISON_RELATED_USE_COUNT,
    special_count=POISON_SPECIAL_CLAUSE_COUNT,
    provider_count=POISON_PROVIDER_COUNT,
    source_blocker_count=POISON_SOURCE_BLOCKER_COUNT,
    max_records=MAX_POISON_RECORDS,
    max_text_bytes=MAX_POISON_TEXT_BYTES,
    max_stages=MAX_POISON_STAGES,
    max_deliveries=MAX_POISON_DELIVERIES,
    max_related=MAX_POISON_RELATED_USES,
    max_special=MAX_POISON_SPECIAL_CLAUSES,
    max_members=MAX_POISON_SOURCE_MEMBERS,
    max_strikes=MAX_POISON_STRIKES,
    max_identifier_bytes=MAX_POISON_IDENTIFIER_BYTES,
)

type.__setattr__(
    CompiledPoisonAffliction,
    "as_serialized",
    _compiled_as_serialized,
)
type.__setattr__(
    LinkedPoisonCorpus,
    "as_serialized",
    _corpus_as_serialized,
)

for _artifact_type in (
    _NoTransfer,
    PoisonDuration,
    PoisonSave,
    PoisonStage,
    PoisonSpecialClause,
    PoisonDependency,
    CompiledPoisonAffliction,
    PoisonAliasLink,
    PoisonDelivery,
    PoisonRelatedUse,
    PoisonProgressionRules,
    PoisonExposureRules,
    PoisonRecoveryRules,
    LinkedPoisonCorpus,
):
    _seal_type(_artifact_type)


__all__ = [
    "CARRIER_CENSUS_SHA256",
    "COMPILED_CENSUS_SHA256",
    "CONSUMER_REQUIREMENTS_SHA256",
    "CompiledPoisonAffliction",
    "FAMILY_ID",
    "LINKED_CORPUS_SHA256",
    "LinkedPoisonCorpus",
    "MAX_POISON_DELIVERIES",
    "MAX_POISON_RECORDS",
    "MAX_POISON_RELATED_USES",
    "MAX_POISON_STAGES",
    "MECHANIC_TYPE",
    "OFFICIAL_CREATURE_CENSUS_COUNT",
    "POISON_ALIAS_COUNT",
    "POISON_CARRIER_COUNT",
    "POISON_DEFINITION_COUNT",
    "POISON_DELIVERY_COUNT",
    "POISON_PROVIDER_COUNT",
    "POISON_RELATED_USE_COUNT",
    "POISON_SOURCE_BLOCKER_COUNT",
    "POISON_SPECIAL_CLAUSE_COUNT",
    "POISON_STAGE_COUNT",
    "PROVIDER_REQUIREMENTS_SHA256",
    "PoisonAliasLink",
    "PoisonCompileError",
    "PoisonDelivery",
    "PoisonDependency",
    "PoisonDuration",
    "PoisonExposureRules",
    "PoisonLinkError",
    "PoisonProgressionRules",
    "PoisonRecoveryRules",
    "PoisonRelatedUse",
    "PoisonSave",
    "PoisonSpecialClause",
    "PoisonStage",
    "REGISTRY_STATUS",
    "compile_poison",
    "compile_poison_census",
    "link_poison_corpus",
    "poison_consumer_requirements",
    "poison_provider_requirements",
    "validate_compiled_poison",
    "validate_linked_poison_corpus",
]

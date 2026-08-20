"""Compile and link the reviewed Core MC1 Engulf source family.

Engulf remains deliberately non-executable.  Compilation authenticates and
normalizes the exact local creature ability.  Linking attaches the generic
Monster Core rule and every directly consumed Player Core rule.  Movement,
save, damage, containment, Escape, and Rupture behavior remains represented by
typed runtime deferrals until the ordinary engine can resolve those mechanics.

The browser, registry, and runtime are not involved here.  Every public entry
point accepts one exact :class:`SourceAuthorityAdapter`; no caller-built
packets, source maps, or compatibility inputs are accepted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Any, Literal, TypeAlias, final

from .contracts import RawSourceMember, RawSourceObject
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)


FAMILY_ID = "engulf"
COMPILER_ID = "engulf"
MECHANIC_TYPE = "stride-through-save-containment"
CONSUMER_REQUIREMENT_COUNT = 1
RELATED_REQUIREMENT_COUNT = 11
PROVIDER_REQUIREMENT_COUNT = 35
COMPILE_DEFERRAL_COUNT = 1
RUNTIME_DEFERRAL_COUNT = 9

_SIZE_RANKS = MappingProxyType(
    {
        "Tiny": 0,
        "Small": 1,
        "Medium": 2,
        "Large": 3,
        "Huge": 4,
        "Gargantuan": 5,
    }
)
_ACTION_COSTS = MappingProxyType(
    {"single": 1, "two": 2, "three": 3}
)
_DAMAGE_RE = re.compile(
    r"^(?P<count>[1-9][0-9]*)d(?P<sides>[1-9][0-9]*)"
    r"(?P<modifier>[+-][0-9]+)? "
    r"(?P<damage_type>[A-Za-z][A-Za-z -]*)$",
    re.ASCII,
)
_LOCAL_DESCRIPTION_RE = re.compile(
    r"^DC (?P<save_dc>[1-9][0-9]*), "
    r"(?P<damage>[1-9][0-9]*d[1-9][0-9]*(?:[+-][0-9]+)? "
    r"[A-Za-z][A-Za-z -]*), "
    r"Escape DC (?P<escape_dc>[1-9][0-9]*), "
    r"Rupture (?P<rupture>[1-9][0-9]*) "
    r"\(page (?P<page>[1-9][0-9]*)\)$",
    re.ASCII,
)
_LAND_SPEED_RE = re.compile(
    r"^(?P<land>[1-9][0-9]*) feet(?:, .+)?$",
    re.ASCII,
)

_ENGULF_PARAGRAPHS = (
    "The monster Strides up to double its Speed and can move through the "
    "spaces of any creatures in its path. Any creature of the monster's "
    "size or smaller whose space the monster moves through can attempt a "
    "Reflex save with the listed DC to avoid being engulfed. A creature "
    "unable to act automatically critically fails this save. If a creature "
    "succeeds at its save, it can choose to be either pushed aside (out of "
    "the monster's path) or pushed in front of the monster to the end of "
    "the monster's movement. The monster can attempt to Engulf the same "
    "creature only once in a single use of Engulf. The monster can contain "
    "as many creatures as can fit in its space.",
    "A creature that fails its save is pulled into the monster's body. It "
    "is grabbed, slowed 1, and has to hold its breath or start suffocating. "
    "The creature takes the listed amount of damage when first engulfed and "
    "at the end of each of its turns while it's engulfed. An engulfed "
    "creature can get free by Escaping against the listed Escape DC. An "
    "engulfed creature can attack the monster engulfing it, but only with "
    "unarmed attacks or with weapons of light Bulk or less. The engulfing "
    "creature is off-guard against the attack. If the monster takes piercing "
    "or slashing damage equaling or exceeding the listed Rupture value from "
    "a single attack or spell, the engulfed creature cuts itself free. A "
    "creature that gets free by either method can immediately breathe and "
    "exits the engulfing monster's space.",
    "If the monster dies, all creatures it has engulfed are automatically "
    "released as the monster's form loses cohesion.",
)

ProviderPhase: TypeAlias = Literal[
    "compile-classification",
    "source-link",
    "runtime-context",
]
DeferralPhase: TypeAlias = Literal["source-link", "runtime"]
RelatedKind: TypeAlias = Literal["near-miss"]
ActionCostRelation: TypeAlias = Literal["local-override"]


@dataclass(frozen=True, slots=True)
class _ConsumerSpec:
    rule_id: str
    locator: str
    carrier_path: tuple[tuple[str, int], ...]
    creature_name: str
    ability_ordinal: int
    creature_sha256: str
    member_sha256: str
    value_sha256: str


@dataclass(frozen=True, slots=True)
class _RelatedSpec:
    rule_id: str
    kind: RelatedKind
    reason: str
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
        "engulf-consumer:living-tar",
        "257.3",
        (("^.creature", 1),),
        "Living Tar",
        23,
        "5492d8fb21e21dc227fd6af2c7025f13aa78aa96f498c27840626ce8ea174152",
        "795c338340dfda05667342b5ca452b973b7d7af03e3e53fd3182763ed7cc6b43",
        "d1f0239e793480bf24460e9b091509b310fdb0db0fe40068819fdd1e8db7a2bb",
    ),
)

# The related dossier has two exact boundaries: abilities where the acting
# creature itself enters or crosses occupied creature spaces, and abilities
# that move or retain a target inside the actor.  Adjacency/area path traces
# (for example Flaming Gallop or Spine Rake) and independently moving proxies
# (for example Propel Sphere) do not satisfy either boundary.
_RELATED_SPECS = (
    _RelatedSpec(
        "engulf-near-miss:clay-effigy:heavy-stride",
        "near-miss",
        "move-through Reflex activity that knocks targets prone",
        "64.1",
        (
            ("Clay Effigy", 1),
            ("Clay Effigy", 0),
            ("^.creature", 3),
        ),
        "Clay Effigy",
        "!.Heavy Stride",
        25,
        "587a3c90b86ee3f9c67b0614dd64b3d537ab849ddc934d7902bdce36c059ccd0",
        "df4147ab98ad09234afed055be1bc37cc8b863134c62d516c7a8a52a86801b0a",
        "abde5a2235b0d6fe798d8b0294a948ad1fed8587ccc396cd46eb43dcf43604a4",
    ),
    _RelatedSpec(
        "engulf-near-miss:quetz-coatl:wrap-in-coils",
        "near-miss",
        "moves grabbed prey into coils with space-based capacity",
        "65.1",
        (("Coatl", 1), ("Coatl", 0), ("^.creature", 2)),
        "Quetz Coatl",
        "!.Wrap in Coils",
        25,
        "f0425486f7271dfebe4d6084a4bf20042216b795b5e87a5ef1cd60d90ff63400",
        "2cef5805503211535621763a80c77d2cffe0caa8dc052b8a3b298f789f893d15",
        "49bb2fd1984eecbb67816d5fd51734c0329f276e877fa366d6a0e4ec63ee6432",
    ),
    _RelatedSpec(
        "engulf-near-miss:gylou:encage-in-tentacles",
        "near-miss",
        "explicit Swallow Whole variant with containment exceptions",
        "91.2",
        (("^.creature", 1),),
        "Gylou",
        "!.Encage in Tentacles",
        26,
        "ae05f9b9d3c0819204cd912b99db4cf267749a33d616c5e2742b81014d4f3fbc",
        "7d8f4992b60c8212574e4e55c6b4e62226950150ab132c59b8361c3bb454c2f2",
        "2146079f5437a07634f5c1ac2cf711d79a73ff8a63bf52c57b49950fab15adfc",
    ),
    _RelatedSpec(
        "engulf-near-miss:young-fortune-dragon:treasure-dive",
        "near-miss",
        "path Reflex activity that pushes creatures without containment",
        "117.2",
        (("^.creature", 0),),
        "Young Fortune Dragon",
        "!.Treasure Dive",
        27,
        "f117fb39663f4ab57856203a1571c1a8d96944bca61d09993c116687b91719d7",
        "adf26366585dcb4a02236bdd3cb4ab5ece09c29b22e3270e1a56a28991a0d56d",
        "77da32ce24227ff05dcbd268383d18fc6fc8e2e11b796d4b09951de6d5a27bbf",
    ),
    _RelatedSpec(
        "engulf-near-miss:caldera-oni:ash-form",
        "near-miss",
        "movement through occupied spaces without Engulf consequences",
        "254.1",
        (("^.creature", 1),),
        "Caldera Oni",
        "!.Ash Form",
        28,
        "6fc15b861a27b04e609cde6a23975dbf0dbb0731b18748466a09bec3c868c08a",
        "800274f07e9f7cdb5942dae2ae96ac48fab3a8e41e6cb7fa8d0cdd8a8af80707",
        "0be002db805ba923761d91069ce74ad21132d71f78dcfdd78bd7b37e63a0abe2",
    ),
    _RelatedSpec(
        "engulf-near-miss:doldrums-heap:draw-in",
        "near-miss",
        "repositions grabbed prey into its own space and damages them",
        "295.3",
        (("^.creature", 1),),
        "Doldrums Heap",
        "!.Draw In",
        24,
        "050fb489ea283deae453555bf4231daf95ed686b189b5786d400f9d6eb33b9e4",
        "80a78456008d75f3290b837e6e93daeee2ffe1314a4335463e5a9b8fad930e7a",
        "2ca4d4b0a604f2e660aefc0f968d5b96f864a2b0f184a984b09c8402bfd4ac15",
    ),
    _RelatedSpec(
        "engulf-near-miss:python:wrap-in-coils",
        "near-miss",
        "moves grabbed prey into a one-creature coil capacity",
        "316.4",
        (("^.creature", 1),),
        "Python",
        "!.Wrap in Coils",
        21,
        "f8ecffd064f4521e543c4eb649426c6941eec277ddea80298741245e6c38d2ff",
        "053d7ab6c7544490067c73a3d12d95c1c6da4eed8d2f03337e95060cdc27ebfd",
        "fab43ac70d9993f1737cea25d17dda0dd157c5adaad6df17d43198ca65bbbbd8",
    ),
    _RelatedSpec(
        "engulf-near-miss:giant-anaconda:wrap-in-coils",
        "near-miss",
        "moves grabbed prey into coils with space-based capacity",
        "317.2",
        (("^.creature", 1),),
        "Giant Anaconda",
        "!.Wrap in Coils",
        23,
        "04515e3a5da19666f1756c51fdc9077a3732e3995643886094ba9f2e209ee8d3",
        "233702e8f95823f570b16df456e49982e1ddee1230a999c8a1cd1ff0f1cbdbaf",
        "54eded13680b74922eef8f75766f18edc08a1bcc0f21309540b6503d54c029fc",
    ),
    _RelatedSpec(
        "engulf-near-miss:stone-bulwark:inexorable-march",
        "near-miss",
        "occupied-space Stride that pushes or damages creatures barring it",
        "324.1",
        (
            ("Stone Bulwark", 1),
            ("Stone Bulwark", 0),
            ("^.creature", 1),
        ),
        "Stone Bulwark",
        "!.Inexorable March",
        25,
        "5db57b59dede72911ef64ea82cacfbc36980cce87b9afb1e309c9c0aaa984941",
        "7b171b97dc223c246880e53a5cc0c2487d823bad5c719ebbf8130826c0360608",
        "1e0350f640f00b2d5f217e58a120c19853d17de7deaa81ef223ca1ab62c03a18",
    ),
    _RelatedSpec(
        "engulf-near-miss:vescavor-swarm:devour-all",
        "near-miss",
        "move-through Reflex activity that alters terrain and knocks prone",
        "338.2",
        (("^.creature", 1),),
        "Vescavor Swarm",
        "!.Devour All",
        22,
        "3f6d18aca483649fad2cb4bb1ff8311d686e32a6cb49ad47ae1d7e2dfa462281",
        "bb5a0d85cac298a25eee4d7d2e90b91848918325833a20d9d68910568717e8dc",
        "c797f3e1792b3e4648c5956531c303fd77fcace6f8470556babd1efc3f03631d",
    ),
    _RelatedSpec(
        "engulf-near-miss:warsworn:absorb",
        "near-miss",
        "occupied-space reaction that absorbs one dying creature permanently",
        "342.1",
        (
            ("Warsworn", 1),
            ("Warsworn", 0),
            ("^.creature", 1),
        ),
        "Warsworn",
        "!.Absorb",
        26,
        "8e82a5d33259b0948c586764b703b221630baf80162eb1558c2beeebe9724f88",
        "7770dae9bef889374ca773a71eacf839b5b914a0d6de185a7e191f932635bb4a",
        "954d02f8840be5d7668ebca273bfa689a41b2e4079afefafb8f8630c5925e0e0",
    ),
)

_PROVIDER_SPECS = (
    _ProviderSpec(
        "monster-core-engulf",
        "core-mc1",
        "358.2",
        (("^.ability", 13),),
        "ae4a1111e749ffdecee3a27b729bda2fce88ba029d143e15532f46919d878911",
        "source-link",
        "Defines the generic Engulf activity and all authored outcomes.",
    ),
    _ProviderSpec(
        "monster-core-swallow-whole",
        "core-mc1",
        "358.2",
        (("^.ability", 33),),
        "fd715b7177ac44edd0fec539d5cd62ad49cecb8c42fb1a76b299684416e116a1",
        "compile-classification",
        "Distinguishes the prerequisite-driven Swallow Whole family.",
    ),
    _ProviderSpec(
        "monster-core-trample",
        "core-mc1",
        "358.2",
        (("^.ability", 37),),
        "02c0549ccadd9b8ae8f927e701f363ade8391727cc4fa223a90b937f705f397b",
        "compile-classification",
        "Distinguishes move-through basic-save Trample damage.",
    ),
    _ProviderSpec(
        "player-core-bulk",
        "core-pc1",
        "269.1",
        (),
        "6448a7799bdc2bd8ead30b81d71599be8040bf688542b2b8849548755dd17f89",
        "runtime-context",
        "Defines the light Bulk ceiling on attacks from inside.",
    ),
    _ProviderSpec(
        "player-core-casting-spells",
        "core-pc1",
        "299.2",
        (),
        "e72af12260d392ccd01ddb21c5e0ac2d5c77b75b4cd55be9145c6cc1a36ad21b",
        "runtime-context",
        "Defines Cast a Spell activities used internally and for Rupture.",
    ),
    _ProviderSpec(
        "player-core-compare-check-to-dc",
        "core-pc1",
        "401.2",
        (),
        "9ff024bc6158c6efc6b6bdc906ee9a00261adfaae0e80f41e1a09bbd7daafd09",
        "runtime-context",
        "Defines comparison of the Reflex save to the listed DC.",
    ),
    _ProviderSpec(
        "player-core-degrees-of-success",
        "core-pc1",
        "401.4",
        (),
        "05a8ea41e782723a63bed00663d4a4ffadfb446edf869af24b4f2f8a61d3c033",
        "runtime-context",
        "Defines save degrees and critical-failure handling.",
    ),
    _ProviderSpec(
        "player-core-defenses",
        "core-pc1",
        "404.1",
        (),
        "711bf9ea76187cd3bc4040c06867a23efe04f111779b6717a4ac375aa3759239",
        "runtime-context",
        "Defines Reflex saving throws and defense resolution.",
    ),
    _ProviderSpec(
        "player-core-damage-rolls",
        "core-pc1",
        "406.1",
        (),
        "c5324ca52f558006c5cb9c141a859291afc36c5fd5e3c389c178c40c02c899f4",
        "runtime-context",
        "Defines initial, periodic, and internal damage rolls.",
    ),
    _ProviderSpec(
        "player-core-apply-damage-defenses",
        "core-pc1",
        "407.3",
        (),
        "70d4b59f1e222320d84c65c73eee11d14210e6800d7ecdbd3ce000da6f13bc21",
        "runtime-context",
        "Defines post-defense damage used by Rupture.",
    ),
    _ProviderSpec(
        "player-core-damage-types",
        "core-pc1",
        "409.1",
        (),
        "b5e918eb06281d4b10f2a3f157110a16e86f31b85fa6efab2e9c9b6bfbf64200",
        "runtime-context",
        "Defines acid damage and piercing or slashing Rupture eligibility.",
    ),
    _ProviderSpec(
        "player-core-death",
        "core-pc1",
        "411.5",
        (),
        "8e5345869b2c669d96672f75ddd62644b74a8cbb5aefe3a488fd549972c0c27d",
        "runtime-context",
        "Defines the engulfing creature death state that releases victims.",
    ),
    _ProviderSpec(
        "player-core-actions",
        "core-pc1",
        "414.1",
        (),
        "57b6ebdb98b389cefba4727fde8d79cb29065e0ba1a0590a0ce95cd1f99db111",
        "runtime-context",
        "Defines exact local action spending.",
    ),
    _ProviderSpec(
        "player-core-activities",
        "core-pc1",
        "414.4",
        (),
        "6cca42e564d687b1b3fd6ce074ad87b1a8e055f7f0dd8fe0383bad3a81e4fa1d",
        "runtime-context",
        "Defines activities and their subordinate Stride.",
    ),
    _ProviderSpec(
        "player-core-actions-with-triggers",
        "core-pc1",
        "414.6",
        (),
        "aca6a47fc0d1e9269f4477375a80c4176bca46c7d361dd1ea4922102651299bf",
        "runtime-context",
        "Defines reaction windows during the subordinate movement.",
    ),
    _ProviderSpec(
        "player-core-gaining-losing-actions",
        "core-pc1",
        "415.2",
        (),
        "c0d99a4b3fcbf74fb36cbf34078f736851804d5bfcc9ae9233b672666ebd4896",
        "runtime-context",
        "Defines action availability and inability to act.",
    ),
    _ProviderSpec(
        "player-core-disruption",
        "core-pc1",
        "415.3",
        (),
        "e4cbbde8bdd6b5e20a99f8e66687e3b98620ba4eb4be67b169de239b0de6bcc9",
        "runtime-context",
        "Defines interruption of the Engulf activity.",
    ),
    _ProviderSpec(
        "player-core-escape",
        "core-pc1",
        "416.6",
        (),
        "af85aa2310e998039ea5c6fd99b718ea3e3a10fdc2da76eff951d21a7871fad3",
        "runtime-context",
        "Defines Escape checks against the listed Escape DC.",
    ),
    _ProviderSpec(
        "player-core-stride",
        "core-pc1",
        "418.3",
        (),
        "a15ba248a6375c3a4f8a4c300b16b4fd2c0f433cb0d6b582e1bbfc49fce9193f",
        "runtime-context",
        "Defines the subordinate Stride and its land-Speed basis.",
    ),
    _ProviderSpec(
        "player-core-strike",
        "core-pc1",
        "418.4",
        (),
        "4cea8c4d82ad0a9ea60102ae21613d1e401270c1b2e6d97ad7fc10041bda273a",
        "runtime-context",
        "Defines attacks from inside and single-attack Rupture.",
    ),
    _ProviderSpec(
        "player-core-movement",
        "core-pc1",
        "420.1",
        (),
        "8057ab6ad13dab84b0fed6a4c6fa0fd595989a68a5d8946b9bdfce3de5a63cf0",
        "runtime-context",
        "Defines path selection and movement timing.",
    ),
    _ProviderSpec(
        "player-core-land-speed",
        "core-pc1",
        "420.4",
        (),
        "625d62f213cadf80d6dd6bff2a2b57ea558174462211db5b36f1d99891fa4433",
        "runtime-context",
        "Defines the land Speed used by Stride.",
    ),
    _ProviderSpec(
        "player-core-grid-movement",
        "core-pc1",
        "421.5",
        (),
        "1610c62fb122a577e3f69ec6b2e3f1273f6cb7e535ee9d5529291637a3b9ce67",
        "runtime-context",
        "Defines square-by-square path traversal.",
    ),
    _ProviderSpec(
        "player-core-diagonal-movement",
        "core-pc1",
        "421.6",
        (),
        "8932a0244b193fd5fb2dc7ebb8a0623cbf9304d52daa9d03845578a5259ed210",
        "runtime-context",
        "Defines diagonal path costs.",
    ),
    _ProviderSpec(
        "player-core-size-space",
        "core-pc1",
        "421.8",
        (),
        "57f6c8bd51c2367bedfda5464ec295229a54363d5576a671fbda1fda3ab01fb6",
        "runtime-context",
        "Defines target size ranks and the engulfing footprint.",
    ),
    _ProviderSpec(
        "player-core-creature-space",
        "core-pc1",
        "422.3",
        (),
        "62ef4117bd8ca96e49011793c59b7325af76e8c57f60291aa0f0cd7e1b07a3e0",
        "runtime-context",
        "Defines occupied-space transit, containment, and exits.",
    ),
    _ProviderSpec(
        "player-core-forced-movement",
        "core-pc1",
        "422.7",
        (),
        "9c89056aba0eec571c99b1518c574c8ab6e6815b75003d96f5731e4393362c42",
        "runtime-context",
        "Defines successful targets being pushed aside or ahead.",
    ),
    _ProviderSpec(
        "player-core-difficult-terrain",
        "core-pc1",
        "423.4",
        (),
        "f9fd32133b57ac1fd215780b357c66f5cafd1e9707f11b19d8e0e9ac8e431663",
        "runtime-context",
        "Defines difficult-terrain path costs.",
    ),
    _ProviderSpec(
        "player-core-hazardous-terrain",
        "core-pc1",
        "423.6",
        (),
        "2db44c3550d4dc17042f03a119dd8e750f262c221b6f55686bfed6ec4ee8b172",
        "runtime-context",
        "Defines hazardous-terrain effects during movement.",
    ),
    _ProviderSpec(
        "player-core-end-turn",
        "core-pc1",
        "436.3",
        (),
        "6eb87a6eb2e19b10947a84a7f74c951a14abfe76831e37300709ede7fdb77140",
        "runtime-context",
        "Defines the victim end-turn damage cadence.",
    ),
    _ProviderSpec(
        "player-core-suffocation",
        "core-pc1",
        "437.8",
        (),
        "79f5413549b1bf2372ea937fd631a794ba90b613347e35a1de585b53c85a317f",
        "runtime-context",
        "Defines breath depletion and suffocation.",
    ),
    _ProviderSpec(
        "player-core-grabbed",
        "core-pc1",
        "444.5",
        (),
        "902cfc2c6b22dd6fe7aafd8e9c58aeccdf6f2c23db9877b9a86c81f830b6e1a9",
        "runtime-context",
        "Defines the engulfed grabbed state.",
    ),
    _ProviderSpec(
        "player-core-immobilized",
        "core-pc1",
        "444.9",
        (),
        "41ad939e731fef9bbe5bfef0ef381dd96edff7621c5102a25b87c187106655a1",
        "runtime-context",
        "Defines movement restriction inherited from grabbed.",
    ),
    _ProviderSpec(
        "player-core-off-guard",
        "core-pc1",
        "445.2",
        (),
        "9de2e5a3c7821e4d541d8bf3d3a13e33fda3b36b76392fbf836df870985cdcf8",
        "runtime-context",
        "Defines the victim's Grabbed-derived state and the engulfing "
        "creature's defense against internal attacks.",
    ),
    _ProviderSpec(
        "player-core-slowed",
        "core-pc1",
        "446.5",
        (),
        "fe97d48614b792dc6cd10b3ea912550acb28445a43962574656b9ec265bf41fb",
        "runtime-context",
        "Defines slowed 1 while engulfed.",
    ),
)

_DEFERRAL_SPECS = (
    (
        "generic-engulf-provider-link",
        "source-link",
        (
            "monster-core-engulf",
            "monster-core-swallow-whole",
            "monster-core-trample",
        ),
        "Attach and classify the exact generic Engulf rule.",
    ),
    (
        "action-economy-and-subordinate-stride",
        "runtime",
        (
            "monster-core-engulf",
            "player-core-actions",
            "player-core-activities",
            "player-core-gaining-losing-actions",
            "player-core-disruption",
            "player-core-stride",
        ),
        "Spend the local three-action override and resolve its Stride.",
    ),
    (
        "movement-path-reactions-and-terrain",
        "runtime",
        (
            "monster-core-engulf",
            "player-core-activities",
            "player-core-actions-with-triggers",
            "player-core-disruption",
            "player-core-stride",
            "player-core-movement",
            "player-core-land-speed",
            "player-core-grid-movement",
            "player-core-diagonal-movement",
            "player-core-difficult-terrain",
            "player-core-hazardous-terrain",
        ),
        "Resolve a legal doubled-Speed path and its reaction windows.",
    ),
    (
        "path-targeting-once-and-capacity",
        "runtime",
        (
            "monster-core-engulf",
            "player-core-size-space",
            "player-core-creature-space",
        ),
        "Track eligible occupied spaces, once-per-use targeting, and capacity.",
    ),
    (
        "reflex-save-and-success-displacement",
        "runtime",
        (
            "monster-core-engulf",
            "player-core-compare-check-to-dc",
            "player-core-degrees-of-success",
            "player-core-defenses",
            "player-core-gaining-losing-actions",
            "player-core-creature-space",
            "player-core-forced-movement",
        ),
        "Resolve Reflex saves, automatic critical failure, and success push.",
    ),
    (
        "failure-entry-and-condition-state",
        "runtime",
        (
            "monster-core-engulf",
            "player-core-size-space",
            "player-core-creature-space",
            "player-core-grabbed",
            "player-core-immobilized",
            "player-core-off-guard",
            "player-core-slowed",
        ),
        "Move failed targets inside and maintain grabbed, off-guard, and slowed 1.",
    ),
    (
        "immediate-and-end-turn-damage",
        "runtime",
        (
            "monster-core-engulf",
            "player-core-damage-rolls",
            "player-core-apply-damage-defenses",
            "player-core-damage-types",
            "player-core-end-turn",
        ),
        "Apply local damage on entry and each engulfed victim end turn.",
    ),
    (
        "breath-suffocation-escape-and-release",
        "runtime",
        (
            "monster-core-engulf",
            "player-core-death",
            "player-core-escape",
            "player-core-casting-spells",
            "player-core-strike",
            "player-core-creature-space",
            "player-core-suffocation",
        ),
        "Track breath and release victims through Escape or engulfing death.",
    ),
    (
        "internal-action-restrictions",
        "runtime",
        (
            "monster-core-engulf",
            "player-core-bulk",
            "player-core-casting-spells",
            "player-core-strike",
            "player-core-grabbed",
            "player-core-off-guard",
        ),
        "Limit internal attacks, including grabbed manipulate restrictions, "
        "while applying the engulfing off-guard state.",
    ),
    (
        "rupture-post-defense-single-event",
        "runtime",
        (
            "monster-core-engulf",
            "player-core-casting-spells",
            "player-core-strike",
            "player-core-damage-rolls",
            "player-core-apply-damage-defenses",
            "player-core-damage-types",
            "player-core-creature-space",
        ),
        "Aggregate one internal attack or spell and release on Rupture.",
    ),
)


class EngulfCompileError(ValueError):
    """Authenticated source differs from the reviewed Engulf family."""


@final
@dataclass(frozen=True, slots=True, init=False)
class EngulfDamage:
    source_text: str
    dice_count: int
    die_sides: int
    modifier: int
    damage_type: str


@final
@dataclass(frozen=True, slots=True, init=False)
class EngulfDeferral:
    mechanic_id: str
    phase: DeferralPhase
    provider_rule_ids: tuple[str, ...]
    blocking_reason: str
    status: Literal["deferred"]


@final
@dataclass(frozen=True, slots=True, init=False)
class EngulfProviderDependency:
    rule_id: str
    source_id: str
    locator: str
    phase: ProviderPhase
    purpose: str


@final
@dataclass(frozen=True, slots=True, init=False)
class CompiledEngulf:
    source_id: str
    locator: str
    creature_name: str
    creature_size: str
    creature_size_rank: int
    action_cost: int
    action_source_text: str
    speed_source_text: str
    land_speed_feet: int
    save_type: str
    save_dc: int
    damage: EngulfDamage
    escape_dc: int
    rupture_threshold: int
    source_page: int
    consumer_rule: VerifiedRuleReceipt
    related_rules: tuple[VerifiedRuleReceipt, ...]
    deferrals: tuple[EngulfDeferral, ...]
    runtime_ready: bool
    _authority: SourceAuthorityAdapter = field(repr=False, compare=False)

    def as_serialized(
        self,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        raise TypeError("compiled Engulf contract is not bound")


@final
@dataclass(frozen=True, slots=True, init=False)
class LinkedEngulf:
    compiled: CompiledEngulf
    glossary_action_cost: int
    action_cost_relation: ActionCostRelation
    movement_action: str
    movement_multiplier: int
    maximum_path_distance_feet: int
    transit_creature_scope: str
    maximum_target_size: str
    maximum_target_size_rank: int
    save_success_choices: tuple[str, ...]
    save_success_choice_owner: str
    save_avoid_degrees: tuple[str, ...]
    save_engulf_degrees: tuple[str, ...]
    unable_to_act_result: str
    repeated_target_limit_per_use: int
    capacity_mode: str
    failure_location: str
    failure_conditions: tuple[str, ...]
    damage_timings: tuple[str, ...]
    internal_attack_sources: tuple[str, ...]
    internal_attack_target: str
    internal_defense_state: str
    rupture_damage_types: tuple[str, ...]
    rupture_event_sources: tuple[str, ...]
    rupture_release_binding: str
    release_methods: tuple[str, ...]
    escape_or_rupture_consequences: tuple[str, ...]
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    deferrals: tuple[EngulfDeferral, ...]
    runtime_ready: bool
    _authority: SourceAuthorityAdapter = field(repr=False, compare=False)

    def as_serialized(
        self,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        raise TypeError("linked Engulf contract is not bound")


_OPAQUE_TYPES = (
    EngulfDamage,
    EngulfDeferral,
    EngulfProviderDependency,
    CompiledEngulf,
    LinkedEngulf,
)


def _deny_init(_self: object, *_args: object, **_kwargs: object) -> None:
    raise TypeError("Engulf contracts are compiler-created")


def _deny_subclass(_cls: type, **_kwargs: object) -> None:
    raise TypeError("Engulf contract subclasses are not supported")


def _deny_copy(_self: object) -> object:
    raise TypeError("Engulf contracts cannot be copied")


def _deny_deepcopy(_self: object, _memo: dict[int, object]) -> object:
    raise TypeError("Engulf contracts cannot be copied")


def _deny_reduce(_self: object, *_args: object) -> object:
    raise TypeError("Engulf contracts cannot be pickled")


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
        slot for slot in value_type.__slots__ if slot != "__weakref__"
    )
    if len(slots) != len(values):
        raise AssertionError("Engulf contract construction drifted")
    for slot, value in zip(slots, values):
        object.__setattr__(result, slot, value)
    return result


def _validate_exact_type_slots(
    value: object,
    exact_type: type,
    label: str,
    _error_type: type[EngulfCompileError] = EngulfCompileError,
) -> None:
    if type(value) is not exact_type:
        raise TypeError(f"{label} must use its exact contract type")
    try:
        for slot in exact_type.__slots__:
            if slot != "__weakref__":
                object.__getattribute__(value, slot)
    except (AttributeError, RecursionError) as failure:
        raise _error_type(f"{label} is incomplete or cyclic") from failure


def _member_steps(
    values: tuple[tuple[str, int], ...],
    _step_type: type[RawMemberStep] = RawMemberStep,
) -> tuple[RawMemberStep, ...]:
    result = []
    for raw_key, member_ordinal in values:
        if (
            type(raw_key) is not str
            or type(member_ordinal) is not int
            or member_ordinal < 0
        ):
            raise AssertionError("invalid reviewed Engulf member path")
        result.append(_step_type(raw_key, member_ordinal))
    return tuple(result)


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
            _step_type("!.Engulf", spec.ability_ordinal),
        ),
        expected_block_sha256=spec.creature_sha256,
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


def _resolve_rule(
    authority: SourceAuthorityAdapter,
    requirement: RuleRequirement,
    _rule_type: type[VerifiedRuleReceipt] = VerifiedRuleReceipt,
    _same_requirement_impl: Any = _same_requirement,
    _error_type: type[EngulfCompileError] = EngulfCompileError,
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


def _raw_member(
    value: RawSourceObject,
    ordinal: int,
    key: str,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _error_type: type[EngulfCompileError] = EngulfCompileError,
) -> RawSourceMember:
    if (
        type(value) is not _object_type
        or type(value.members) is not tuple
        or type(ordinal) is not int
        or ordinal < 0
        or ordinal >= len(value.members)
    ):
        raise _error_type(f"missing exact {key!r} member")
    member = value.members[ordinal]
    if (
        type(member) is not _member_type
        or type(member.key) is not str
        or member.key != key
    ):
        raise _error_type(f"expected {key!r} at ordinal {ordinal}")
    return member


def _parse_damage(
    source_text: str,
    _damage_re: re.Pattern[str] = _DAMAGE_RE,
    _error_type: type[EngulfCompileError] = EngulfCompileError,
) -> tuple[int, int, int, str]:
    if type(source_text) is not str:
        raise _error_type("Engulf damage must be exact text")
    match = _damage_re.fullmatch(source_text)
    if match is None:
        raise _error_type("Engulf damage differs from reviewed grammar")
    count = int(match.group("count"))
    sides = int(match.group("sides"))
    modifier = int(match.group("modifier") or "0")
    damage_type = match.group("damage_type")
    if count <= 0 or sides <= 0:
        raise _error_type("Engulf damage dice must be positive")
    return count, sides, modifier, damage_type


def _new_damage(
    source_text: str,
    _parse_damage_impl: Any = _parse_damage,
    _new_value_impl: Any = _new_value,
    _damage_type: type[EngulfDamage] = EngulfDamage,
) -> EngulfDamage:
    count, sides, modifier, damage_type = _parse_damage_impl(source_text)
    return _new_value_impl(
        _damage_type,
        (source_text, count, sides, modifier, damage_type),
    )


def _damage_payload(
    value: EngulfDamage,
    _damage_type: type[EngulfDamage] = EngulfDamage,
    _validate_slots_impl: Any = _validate_exact_type_slots,
    _parse_damage_impl: Any = _parse_damage,
    _error_type: type[EngulfCompileError] = EngulfCompileError,
) -> dict[str, Any]:
    _validate_slots_impl(value, _damage_type, "Engulf damage")
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
        raise _error_type("compiled Engulf damage is invalid")
    return {
        "sourceText": value.source_text,
        "dice": {
            "count": value.dice_count,
            "sides": value.die_sides,
            "modifier": value.modifier,
        },
        "type": value.damage_type,
    }


def _parse_consumer_source(
    selection: VerifiedSourceSelection,
    spec: _ConsumerSpec,
    _selection_type: type[VerifiedSourceSelection] = VerifiedSourceSelection,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _raw_member_impl: Any = _raw_member,
    _description_re: re.Pattern[str] = _LOCAL_DESCRIPTION_RE,
    _speed_re: re.Pattern[str] = _LAND_SPEED_RE,
    _action_costs: dict[str, int] = dict(_ACTION_COSTS),
    _size_ranks: dict[str, int] = dict(_SIZE_RANKS),
    _parse_damage_impl: Any = _parse_damage,
    _error_type: type[EngulfCompileError] = EngulfCompileError,
) -> tuple[
    str, str, int, str, int, str, int, str, int, int, int, int
]:
    if type(selection) is not _selection_type:
        raise TypeError("Engulf source selection must be exact")
    block = selection.carrier.raw_block
    if type(block) is not _object_type:
        raise _error_type("Engulf carrier must be an exact object")
    name = _raw_member_impl(block, 0, "Name").value
    size = _raw_member_impl(block, 2, "Size").value
    speed_text = _raw_member_impl(block, 20, "Speed").value
    ability_member = _raw_member_impl(
        block, spec.ability_ordinal, "!.Engulf"
    )
    if (
        type(name) is not str
        or name != spec.creature_name
        or type(size) is not str
        or size not in _size_ranks
        or type(speed_text) is not str
        or type(ability_member.value) is not _object_type
        or type(selection.raw_member) is not _member_type
        or selection.raw_member.key != "!.Engulf"
        or type(selection.raw_value) is not _object_type
    ):
        raise _error_type("Engulf carrier identity or shape is invalid")
    ability = ability_member.value
    if len(ability.members) != 2:
        raise _error_type("local Engulf ability shape drifted")
    action_text = _raw_member_impl(ability, 0, "Action").value
    description = _raw_member_impl(ability, 1, "Description").value
    if (
        type(action_text) is not str
        or action_text not in _action_costs
        or type(description) is not str
    ):
        raise _error_type("local Engulf action or description is invalid")
    speed_match = _speed_re.fullmatch(speed_text)
    description_match = _description_re.fullmatch(description)
    if speed_match is None or description_match is None:
        raise _error_type("local Engulf source text differs from review")
    damage_text = description_match.group("damage")
    _parse_damage_impl(damage_text)
    return (
        name,
        size,
        _size_ranks[size],
        action_text,
        _action_costs[action_text],
        speed_text,
        int(speed_match.group("land")),
        damage_text,
        int(description_match.group("save_dc")),
        int(description_match.group("escape_dc")),
        int(description_match.group("rupture")),
        int(description_match.group("page")),
    )


def _validate_related_source(
    selection: VerifiedSourceSelection,
    spec: _RelatedSpec,
    _selection_type: type[VerifiedSourceSelection] = VerifiedSourceSelection,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _member_type: type[RawSourceMember] = RawSourceMember,
    _raw_member_impl: Any = _raw_member,
    _error_type: type[EngulfCompileError] = EngulfCompileError,
) -> None:
    if type(selection) is not _selection_type:
        raise TypeError("Engulf related selection must be exact")
    block = selection.carrier.raw_block
    if type(block) is not _object_type:
        raise _error_type("Engulf near-miss carrier must be an object")
    name = _raw_member_impl(block, 0, "Name").value
    selected = _raw_member_impl(
        block, spec.member_ordinal, spec.raw_key
    )
    if (
        type(name) is not str
        or name != spec.creature_name
        or type(selected.value) is not _object_type
        or type(selection.raw_member) is not _member_type
        or selection.raw_member.key != spec.raw_key
        or type(selection.raw_value) is not _object_type
    ):
        raise _error_type("Engulf near-miss evidence differs from review")


def _parse_glossary_source(
    selection: VerifiedSourceSelection,
    _paragraphs: tuple[str, ...] = _ENGULF_PARAGRAPHS,
    _selection_type: type[VerifiedSourceSelection] = VerifiedSourceSelection,
    _object_type: type[RawSourceObject] = RawSourceObject,
    _raw_member_impl: Any = _raw_member,
    _action_costs: dict[str, int] = dict(_ACTION_COSTS),
    _error_type: type[EngulfCompileError] = EngulfCompileError,
) -> int:
    if type(selection) is not _selection_type:
        raise TypeError("Engulf glossary selection must be exact")
    ability = selection.selected_value
    if type(ability) is not _object_type or len(ability.members) != 3:
        raise _error_type("Engulf glossary ability shape drifted")
    name = _raw_member_impl(ability, 0, "Name").value
    action_text = _raw_member_impl(ability, 1, "Action").value
    description = _raw_member_impl(ability, 2, "Description").value
    if (
        type(name) is not str
        or name != "Engulf"
        or type(action_text) is not str
        or action_text != "two"
        or type(description) is not _object_type
        or len(description.members) != len(_paragraphs)
    ):
        raise _error_type("Engulf glossary identity or action drifted")
    actual_paragraphs = []
    for ordinal, expected in enumerate(_paragraphs):
        value = _raw_member_impl(description, ordinal, "~.p").value
        if type(value) is not str or value != expected:
            raise _error_type("Engulf glossary semantics drifted")
        actual_paragraphs.append(value)
    if tuple(actual_paragraphs) != _paragraphs:
        raise _error_type("Engulf glossary paragraph order drifted")
    return _action_costs[action_text]


def _new_deferrals(
    specs: tuple[tuple[str, str, tuple[str, ...], str], ...],
    _new_value_impl: Any = _new_value,
    _deferral_type: type[EngulfDeferral] = EngulfDeferral,
) -> tuple[EngulfDeferral, ...]:
    return tuple(
        _new_value_impl(
            _deferral_type,
            (mechanic_id, phase, providers, reason, "deferred"),
        )
        for mechanic_id, phase, providers, reason in specs
    )


def _deferral_payload(
    value: EngulfDeferral,
    _deferral_type: type[EngulfDeferral] = EngulfDeferral,
    _validate_slots_impl: Any = _validate_exact_type_slots,
    _error_type: type[EngulfCompileError] = EngulfCompileError,
) -> dict[str, Any]:
    _validate_slots_impl(value, _deferral_type, "Engulf deferral")
    if (
        type(value.mechanic_id) is not str
        or type(value.phase) is not str
        or value.phase not in ("source-link", "runtime")
        or type(value.provider_rule_ids) is not tuple
        or any(type(item) is not str for item in value.provider_rule_ids)
        or not value.provider_rule_ids
        or len(set(value.provider_rule_ids)) != len(value.provider_rule_ids)
        or type(value.blocking_reason) is not str
        or type(value.status) is not str
        or value.status != "deferred"
    ):
        raise _error_type("Engulf deferral is invalid")
    return {
        "mechanicId": value.mechanic_id,
        "phase": value.phase,
        "providerRuleIds": list(value.provider_rule_ids),
        "blockingReason": value.blocking_reason,
        "status": value.status,
        "blocks": "registry-activation",
    }


def _new_dependency(
    spec: _ProviderSpec,
    _new_value_impl: Any = _new_value,
    _dependency_type: type[EngulfProviderDependency] = (
        EngulfProviderDependency
    ),
) -> EngulfProviderDependency:
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


def _dependency_payload(
    value: EngulfProviderDependency,
    _dependency_type: type[EngulfProviderDependency] = (
        EngulfProviderDependency
    ),
    _validate_slots_impl: Any = _validate_exact_type_slots,
    _error_type: type[EngulfCompileError] = EngulfCompileError,
) -> dict[str, Any]:
    _validate_slots_impl(value, _dependency_type, "Engulf dependency")
    if (
        type(value.rule_id) is not str
        or type(value.source_id) is not str
        or type(value.locator) is not str
        or type(value.phase) is not str
        or value.phase not in (
            "compile-classification",
            "source-link",
            "runtime-context",
        )
        or type(value.purpose) is not str
        or not value.purpose.endswith(".")
    ):
        raise _error_type("Engulf provider dependency is invalid")
    return {
        "ruleId": value.rule_id,
        "sourceId": value.source_id,
        "locator": value.locator,
        "phase": value.phase,
        "purpose": value.purpose,
    }


def _compiled_payload(
    value: CompiledEngulf,
    related_specs: tuple[_RelatedSpec, ...],
    _family_id: str = FAMILY_ID,
    _compiler_id: str = COMPILER_ID,
    _damage_payload_impl: Any = _damage_payload,
    _deferral_payload_impl: Any = _deferral_payload,
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
        "activity": {
            "creatureSize": {
                "name": value.creature_size,
                "rank": value.creature_size_rank,
            },
            "actionCost": value.action_cost,
            "actionSourceText": value.action_source_text,
            "speedSourceText": value.speed_source_text,
            "landSpeedFeet": value.land_speed_feet,
            "save": {"type": value.save_type, "dc": value.save_dc},
            "damage": _damage_payload_impl(value.damage),
            "escapeDc": value.escape_dc,
            "ruptureThreshold": value.rupture_threshold,
            "sourcePage": value.source_page,
        },
        "consumer": _serialize_rule(value.consumer_rule),
        "classificationEvidence": [
            {
                "kind": spec.kind,
                "reason": spec.reason,
                "receipt": _serialize_rule(rule),
            }
            for spec, rule in zip(related_specs, value.related_rules)
        ],
        "deferredMechanics": [
            _deferral_payload_impl(item) for item in value.deferrals
        ],
    }


def _linked_payload(
    value: LinkedEngulf,
    related_specs: tuple[_RelatedSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    _family_id: str = FAMILY_ID,
    _compiler_id: str = COMPILER_ID,
    _compiled_payload_impl: Any = _compiled_payload,
    _deferral_payload_impl: Any = _deferral_payload,
    _new_dependency_impl: Any = _new_dependency,
    _dependency_payload_impl: Any = _dependency_payload,
    _serialize_rule: Any = VerifiedRuleReceipt.as_serialized,
) -> dict[str, Any]:
    return {
        "familyId": _family_id,
        "compilerId": _compiler_id,
        "supportState": "linked-non-executable",
        "runtimeReady": False,
        "compiled": _compiled_payload_impl(value.compiled, related_specs),
        "genericRule": {
            "glossaryActionCost": value.glossary_action_cost,
            "actionCostRelation": value.action_cost_relation,
            "movementAction": value.movement_action,
            "movementMultiplier": value.movement_multiplier,
            "maximumPathDistanceFeet": value.maximum_path_distance_feet,
            "transitCreatureScope": value.transit_creature_scope,
            "maximumTargetSize": {
                "name": value.maximum_target_size,
                "rank": value.maximum_target_size_rank,
            },
            "saveSuccessChoices": list(value.save_success_choices),
            "saveSuccessChoiceOwner": value.save_success_choice_owner,
            "saveAvoidDegrees": list(value.save_avoid_degrees),
            "saveEngulfDegrees": list(value.save_engulf_degrees),
            "unableToActResult": value.unable_to_act_result,
            "repeatedTargetLimitPerUse": (
                value.repeated_target_limit_per_use
            ),
            "capacityMode": value.capacity_mode,
            "failureLocation": value.failure_location,
            "failureConditions": list(value.failure_conditions),
            "damageTimings": list(value.damage_timings),
            "internalAttackSources": list(value.internal_attack_sources),
            "internalAttackTarget": value.internal_attack_target,
            "internalDefenseState": value.internal_defense_state,
            "ruptureDamageTypes": list(value.rupture_damage_types),
            "ruptureEventSources": list(value.rupture_event_sources),
            "ruptureReleaseBinding": value.rupture_release_binding,
            "releaseMethods": list(value.release_methods),
            "escapeOrRuptureConsequences": list(
                value.escape_or_rupture_consequences
            ),
        },
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


def _bind_reviewed_api(
    consumer_specs: tuple[_ConsumerSpec, ...],
    related_specs: tuple[_RelatedSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    deferral_specs: tuple[
        tuple[str, str, tuple[str, ...], str], ...
    ],
) -> tuple[Any, ...]:
    consumer_type = _ConsumerSpec
    related_type = _RelatedSpec
    provider_type = _ProviderSpec
    reviewed_consumers = tuple(
        consumer_type(
            *(object.__getattribute__(item, slot)
              for slot in consumer_type.__slots__)
        )
        for item in consumer_specs
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
    rule_receipt_type = VerifiedRuleReceipt
    compiled_type = CompiledEngulf
    linked_type = LinkedEngulf
    error_type = EngulfCompileError
    consumer_requirement_impl = _consumer_requirement
    related_requirement_impl = _related_requirement
    provider_requirement_impl = _provider_requirement
    resolve_rule_impl = _resolve_rule
    same_requirement_impl = _same_requirement
    same_receipt_impl = _same_receipt
    parse_consumer_impl = _parse_consumer_source
    validate_related_impl = _validate_related_source
    parse_glossary_impl = _parse_glossary_source
    new_value_impl = _new_value
    new_damage_impl = _new_damage
    new_deferrals_impl = _new_deferrals
    new_dependency_impl = _new_dependency
    damage_payload_impl = _damage_payload
    deferral_payload_impl = _deferral_payload
    compiled_payload_impl = _compiled_payload
    linked_payload_impl = _linked_payload
    validate_slots_impl = _validate_exact_type_slots
    canonical_bytes = canonical_json_bytes
    size_ranks = dict(_SIZE_RANKS)
    consumer_count = CONSUMER_REQUIREMENT_COUNT
    compile_deferral_count = COMPILE_DEFERRAL_COUNT
    runtime_deferral_count = RUNTIME_DEFERRAL_COUNT

    if (
        len(reviewed_consumers) != CONSUMER_REQUIREMENT_COUNT
        or len(reviewed_related) != RELATED_REQUIREMENT_COUNT
        or len(reviewed_providers) != PROVIDER_REQUIREMENT_COUNT
        or len(reviewed_deferrals)
        != COMPILE_DEFERRAL_COUNT + RUNTIME_DEFERRAL_COUNT
        or len({item.rule_id for item in reviewed_consumers})
        != len(reviewed_consumers)
        or len({item.rule_id for item in reviewed_related})
        != len(reviewed_related)
        or len({item.rule_id for item in reviewed_providers})
        != len(reviewed_providers)
        or len({item.locator for item in reviewed_consumers})
        != len(reviewed_consumers)
        or any(item.kind != "near-miss" for item in reviewed_related)
    ):
        raise AssertionError("reviewed Engulf dossier is incomplete")
    provider_ids = frozenset(
        item.rule_id for item in reviewed_providers
    )
    if (
        reviewed_deferrals[0][1] != "source-link"
        or any(item[1] != "runtime" for item in reviewed_deferrals[1:])
        or any(
            provider_id not in provider_ids
            for item in reviewed_deferrals
            for provider_id in item[2]
        )
    ):
        raise AssertionError("reviewed Engulf deferrals are invalid")

    consumers_by_locator = {
        item.locator: item for item in reviewed_consumers
    }
    consumers_by_rule = {
        item.rule_id: item for item in reviewed_consumers
    }
    providers_by_rule = {
        item.rule_id: item for item in reviewed_providers
    }
    compile_deferrals = reviewed_deferrals[:compile_deferral_count]
    runtime_deferrals = reviewed_deferrals[compile_deferral_count:]

    def engulf_consumer_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(
            consumer_requirement_impl(item)
            for item in reviewed_consumers
        )

    def engulf_related_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(
            related_requirement_impl(item) for item in reviewed_related
        )

    def engulf_provider_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(
            provider_requirement_impl(item)
            for item in reviewed_providers
        )

    def engulf_provider_ledger(
    ) -> tuple[EngulfProviderDependency, ...]:
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
                f"retained rule differs from review: "
                f"{requirement.rule_id}"
            )
        return verified

    def validate_compiled_engulf(
        authority: SourceAuthorityAdapter,
        value: object,
        /,
    ) -> CompiledEngulf:
        if type(authority) is not authority_type:
            raise TypeError(
                "Engulf validation requires SourceAuthorityAdapter"
            )
        validate_slots_impl(value, compiled_type, "compiled Engulf")
        assert type(value) is compiled_type
        if value._authority is not authority:
            raise error_type(
                "compiled Engulf belongs to another authority"
            )
        consumer_rule = authority.validate_rule(value.consumer_rule)
        spec = consumers_by_rule.get(consumer_rule.rule_id)
        if spec is None:
            raise error_type(
                "compiled Engulf consumer is outside the reviewed corpus"
            )
        consumer_rule = validate_rule_exact(
            authority,
            consumer_rule,
            consumer_requirement_impl(spec),
        )
        selection = authority.validate_selection(
            consumer_rule.selection
        )
        (
            creature_name,
            creature_size,
            creature_size_rank,
            action_text,
            action_cost,
            speed_text,
            land_speed,
            damage_text,
            save_dc,
            escape_dc,
            rupture,
            source_page,
        ) = parse_consumer_impl(selection, spec)
        if (
            type(value.source_id) is not str
            or value.source_id != "core-mc1"
            or type(value.locator) is not str
            or value.locator != spec.locator
            or type(value.creature_name) is not str
            or value.creature_name != creature_name
            or type(value.creature_size) is not str
            or value.creature_size != creature_size
            or type(value.creature_size_rank) is not int
            or value.creature_size_rank != creature_size_rank
            or type(value.action_cost) is not int
            or value.action_cost != action_cost
            or type(value.action_source_text) is not str
            or value.action_source_text != action_text
            or type(value.speed_source_text) is not str
            or value.speed_source_text != speed_text
            or type(value.land_speed_feet) is not int
            or value.land_speed_feet != land_speed
            or type(value.save_type) is not str
            or value.save_type != "Reflex"
            or type(value.save_dc) is not int
            or value.save_dc != save_dc
            or type(value.escape_dc) is not int
            or value.escape_dc != escape_dc
            or type(value.rupture_threshold) is not int
            or value.rupture_threshold != rupture
            or type(value.source_page) is not int
            or value.source_page != source_page
            or value.runtime_ready is not False
        ):
            raise error_type(
                "compiled Engulf scalar fields are noncanonical"
            )
        if canonical_bytes(damage_payload_impl(value.damage)) != (
            canonical_bytes(
                damage_payload_impl(new_damage_impl(damage_text))
            )
        ):
            raise error_type("compiled Engulf damage differs from source")
        if (
            type(value.related_rules) is not tuple
            or len(value.related_rules) != len(reviewed_related)
        ):
            raise error_type(
                "compiled Engulf near-miss census is invalid"
            )
        verified_related = []
        for rule, related_spec in zip(
            value.related_rules, reviewed_related
        ):
            related_rule = validate_rule_exact(
                authority,
                rule,
                related_requirement_impl(related_spec),
            )
            validate_related_impl(
                authority.validate_selection(related_rule.selection),
                related_spec,
            )
            verified_related.append(related_rule)
        if (
            type(value.deferrals) is not tuple
            or len(value.deferrals) != compile_deferral_count
        ):
            raise error_type("compiled Engulf source-link boundary drifted")
        for supplied, expected in zip(
            value.deferrals,
            new_deferrals_impl(compile_deferrals),
        ):
            if canonical_bytes(deferral_payload_impl(supplied)) != (
                canonical_bytes(deferral_payload_impl(expected))
            ):
                raise error_type(
                    "compiled Engulf deferral differs from review"
                )
        authority.require_shared_authority(
            selection,
            (consumer_rule, *tuple(verified_related)),
        )
        canonical_bytes(
            compiled_payload_impl(value, reviewed_related)
        )
        return value

    def compile_engulf(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
        /,
    ) -> CompiledEngulf:
        if type(authority) is not authority_type:
            raise TypeError(
                "Engulf compilation requires SourceAuthorityAdapter"
            )
        if type(receipt) is not receipt_type:
            raise TypeError(
                "Engulf compilation requires an exact SourceReceipt"
            )
        supplied_selection = authority.validate_selection(
            authority.reload(receipt)
        )
        if supplied_selection.address.source_id != "core-mc1":
            raise error_type("Engulf consumer must come from Core MC1")
        spec = consumers_by_locator.get(
            supplied_selection.address.locator
        )
        if spec is None:
            raise error_type(
                "consumer is outside the reviewed Engulf corpus"
            )
        consumer_rule = resolve_rule_impl(
            authority, consumer_requirement_impl(spec)
        )
        if not same_receipt_impl(receipt, consumer_rule.receipt):
            raise error_type(
                "consumer is not the exact reviewed Engulf ability"
            )
        selection = authority.validate_selection(
            consumer_rule.selection
        )
        (
            creature_name,
            creature_size,
            creature_size_rank,
            action_text,
            action_cost,
            speed_text,
            land_speed,
            damage_text,
            save_dc,
            escape_dc,
            rupture,
            source_page,
        ) = parse_consumer_impl(selection, spec)
        related_rules = tuple(
            resolve_rule_impl(
                authority, related_requirement_impl(item)
            )
            for item in reviewed_related
        )
        for rule, related_spec in zip(
            related_rules, reviewed_related
        ):
            validate_related_impl(
                authority.validate_selection(rule.selection),
                related_spec,
            )
        result = new_value_impl(
            compiled_type,
            (
                "core-mc1",
                spec.locator,
                creature_name,
                creature_size,
                creature_size_rank,
                action_cost,
                action_text,
                speed_text,
                land_speed,
                "Reflex",
                save_dc,
                new_damage_impl(damage_text),
                escape_dc,
                rupture,
                source_page,
                consumer_rule,
                related_rules,
                new_deferrals_impl(compile_deferrals),
                False,
                authority,
            ),
        )
        return validate_compiled_engulf(authority, result)

    def compile_engulf_census(
        authority: SourceAuthorityAdapter,
        /,
    ) -> tuple[CompiledEngulf, ...]:
        if type(authority) is not authority_type:
            raise TypeError(
                "Engulf census requires SourceAuthorityAdapter"
            )
        result = tuple(
            compile_engulf(
                authority,
                resolve_rule_impl(
                    authority, consumer_requirement_impl(spec)
                ).receipt,
            )
            for spec in reviewed_consumers
        )
        if len(result) != consumer_count:
            raise AssertionError("reviewed Engulf census is incomplete")
        return result

    def validate_linked_engulf(
        authority: SourceAuthorityAdapter,
        value: object,
        /,
    ) -> LinkedEngulf:
        if type(authority) is not authority_type:
            raise TypeError(
                "linked Engulf validation requires SourceAuthorityAdapter"
            )
        validate_slots_impl(value, linked_type, "linked Engulf")
        assert type(value) is linked_type
        if value._authority is not authority:
            raise error_type(
                "linked Engulf belongs to another authority"
            )
        compiled = validate_compiled_engulf(
            authority, value.compiled
        )
        if (
            type(value.provider_rules) is not tuple
            or len(value.provider_rules) != len(reviewed_providers)
            or tuple(item.rule_id for item in value.provider_rules)
            != tuple(item.rule_id for item in reviewed_providers)
        ):
            raise error_type(
                "linked Engulf provider order or membership is invalid"
            )
        verified_providers = []
        for rule, provider_spec in zip(
            value.provider_rules, reviewed_providers
        ):
            provider_rule = validate_rule_exact(
                authority,
                rule,
                provider_requirement_impl(provider_spec),
            )
            verified_providers.append(provider_rule)
        glossary_rule = next(
            item for item in verified_providers
            if item.rule_id == "monster-core-engulf"
        )
        glossary_action_cost = parse_glossary_impl(
            authority.validate_selection(glossary_rule.selection)
        )

        expected_string_tuples = (
            (
                value.save_success_choices,
                ("push-aside-out-of-path", "push-ahead-to-movement-end"),
            ),
            (
                value.save_avoid_degrees,
                ("critical-success", "success"),
            ),
            (
                value.save_engulf_degrees,
                ("failure", "critical-failure"),
            ),
            (
                value.failure_conditions,
                (
                    "grabbed",
                    "immobilized",
                    "off-guard",
                    "slowed-1",
                    "breath-required",
                ),
            ),
            (
                value.damage_timings,
                ("on-engulf", "engulfed-victim-end-turn"),
            ),
            (
                value.internal_attack_sources,
                ("unarmed-attack", "weapon-light-bulk-or-less"),
            ),
            (
                value.rupture_damage_types,
                ("piercing", "slashing"),
            ),
            (
                value.rupture_event_sources,
                ("single-attack", "single-spell"),
            ),
            (
                value.release_methods,
                (
                    "escape-single-victim",
                    "rupture-single-victim",
                    "engulfing-creature-death-automatically-releases-all-victims",
                ),
            ),
            (
                value.escape_or_rupture_consequences,
                (
                    "immediate-breathing",
                    "exit-engulfing-creature-space",
                ),
            ),
        )
        if (
            type(value.glossary_action_cost) is not int
            or value.glossary_action_cost != glossary_action_cost
            or type(value.action_cost_relation) is not str
            or value.action_cost_relation != "local-override"
            or compiled.action_cost == glossary_action_cost
            or type(value.movement_action) is not str
            or value.movement_action != "Stride"
            or type(value.movement_multiplier) is not int
            or value.movement_multiplier != 2
            or type(value.maximum_path_distance_feet) is not int
            or value.maximum_path_distance_feet
            != compiled.land_speed_feet * 2
            or type(value.transit_creature_scope) is not str
            or value.transit_creature_scope != "all-creature-spaces"
            or type(value.maximum_target_size) is not str
            or value.maximum_target_size != compiled.creature_size
            or type(value.maximum_target_size_rank) is not int
            or value.maximum_target_size_rank
            != size_ranks[compiled.creature_size]
            or type(value.save_success_choice_owner) is not str
            or value.save_success_choice_owner != "saving-creature"
            or type(value.unable_to_act_result) is not str
            or value.unable_to_act_result != "automatic-critical-failure"
            or type(value.repeated_target_limit_per_use) is not int
            or value.repeated_target_limit_per_use != 1
            or type(value.capacity_mode) is not str
            or value.capacity_mode != "creatures-that-fit-in-own-space"
            or type(value.failure_location) is not str
            or value.failure_location != "inside-engulfing-creature"
            or type(value.internal_attack_target) is not str
            or value.internal_attack_target != "engulfing-creature"
            or type(value.internal_defense_state) is not str
            or value.internal_defense_state != "off-guard"
            or type(value.rupture_release_binding) is not str
            or value.rupture_release_binding
            != "victim-whose-event-met-threshold"
            or any(
                type(supplied) is not tuple
                or any(type(item) is not str for item in supplied)
                or supplied != expected
                for supplied, expected in expected_string_tuples
            )
            or value.runtime_ready is not False
        ):
            raise error_type(
                "linked Engulf semantics are noncanonical"
            )
        if (
            type(value.deferrals) is not tuple
            or len(value.deferrals) != runtime_deferral_count
        ):
            raise error_type("linked Engulf runtime boundary drifted")
        for supplied, expected in zip(
            value.deferrals,
            new_deferrals_impl(runtime_deferrals),
        ):
            if canonical_bytes(deferral_payload_impl(supplied)) != (
                canonical_bytes(deferral_payload_impl(expected))
            ):
                raise error_type(
                    "linked Engulf deferral differs from review"
                )
        authority.require_shared_authority(
            compiled.consumer_rule.selection,
            (
                compiled.consumer_rule,
                *compiled.related_rules,
                *tuple(verified_providers),
            ),
        )
        canonical_bytes(
            linked_payload_impl(
                value, reviewed_related, reviewed_providers
            )
        )
        return value

    def link_engulf(
        authority: SourceAuthorityAdapter,
        compiled: CompiledEngulf,
        /,
    ) -> LinkedEngulf:
        compiled = validate_compiled_engulf(authority, compiled)
        provider_rules = tuple(
            resolve_rule_impl(
                authority, provider_requirement_impl(item)
            )
            for item in reviewed_providers
        )
        glossary_rule = next(
            item for item in provider_rules
            if item.rule_id == "monster-core-engulf"
        )
        glossary_action_cost = parse_glossary_impl(
            authority.validate_selection(glossary_rule.selection)
        )
        if compiled.action_cost == glossary_action_cost:
            raise error_type(
                "reviewed local Engulf action-cost variant disappeared"
            )
        result = new_value_impl(
            linked_type,
            (
                compiled,
                glossary_action_cost,
                "local-override",
                "Stride",
                2,
                compiled.land_speed_feet * 2,
                "all-creature-spaces",
                compiled.creature_size,
                size_ranks[compiled.creature_size],
                ("push-aside-out-of-path", "push-ahead-to-movement-end"),
                "saving-creature",
                ("critical-success", "success"),
                ("failure", "critical-failure"),
                "automatic-critical-failure",
                1,
                "creatures-that-fit-in-own-space",
                "inside-engulfing-creature",
                (
                    "grabbed",
                    "immobilized",
                    "off-guard",
                    "slowed-1",
                    "breath-required",
                ),
                ("on-engulf", "engulfed-victim-end-turn"),
                ("unarmed-attack", "weapon-light-bulk-or-less"),
                "engulfing-creature",
                "off-guard",
                ("piercing", "slashing"),
                ("single-attack", "single-spell"),
                "victim-whose-event-met-threshold",
                (
                    "escape-single-victim",
                    "rupture-single-victim",
                    "engulfing-creature-death-automatically-releases-all-victims",
                ),
                (
                    "immediate-breathing",
                    "exit-engulfing-creature-space",
                ),
                provider_rules,
                new_deferrals_impl(runtime_deferrals),
                False,
                authority,
            ),
        )
        return validate_linked_engulf(authority, result)

    def compiled_as_serialized(
        value: CompiledEngulf,
        authority: SourceAuthorityAdapter,
        /,
    ) -> dict[str, Any]:
        validate_compiled_engulf(authority, value)
        payload = compiled_payload_impl(value, reviewed_related)
        canonical_bytes(payload)
        return payload

    def linked_as_serialized(
        value: LinkedEngulf,
        authority: SourceAuthorityAdapter,
        /,
    ) -> dict[str, Any]:
        validate_linked_engulf(authority, value)
        payload = linked_payload_impl(
            value, reviewed_related, reviewed_providers
        )
        canonical_bytes(payload)
        return payload

    return (
        engulf_consumer_requirements,
        engulf_related_requirements,
        engulf_provider_requirements,
        engulf_provider_ledger,
        compile_engulf,
        compile_engulf_census,
        validate_compiled_engulf,
        link_engulf,
        validate_linked_engulf,
        compiled_as_serialized,
        linked_as_serialized,
    )


(
    engulf_consumer_requirements,
    engulf_related_requirements,
    engulf_provider_requirements,
    engulf_provider_ledger,
    compile_engulf,
    compile_engulf_census,
    validate_compiled_engulf,
    link_engulf,
    validate_linked_engulf,
    _compiled_as_serialized,
    _linked_as_serialized,
) = _bind_reviewed_api(
    _CONSUMER_SPECS,
    _RELATED_SPECS,
    _PROVIDER_SPECS,
    _DEFERRAL_SPECS,
)
CompiledEngulf.as_serialized = _compiled_as_serialized
LinkedEngulf.as_serialized = _linked_as_serialized


__all__ = [
    "COMPILE_DEFERRAL_COUNT",
    "COMPILER_ID",
    "CONSUMER_REQUIREMENT_COUNT",
    "CompiledEngulf",
    "EngulfCompileError",
    "EngulfDamage",
    "EngulfDeferral",
    "EngulfProviderDependency",
    "FAMILY_ID",
    "LinkedEngulf",
    "MECHANIC_TYPE",
    "PROVIDER_REQUIREMENT_COUNT",
    "RELATED_REQUIREMENT_COUNT",
    "RUNTIME_DEFERRAL_COUNT",
    "compile_engulf",
    "compile_engulf_census",
    "engulf_consumer_requirements",
    "engulf_provider_ledger",
    "engulf_provider_requirements",
    "engulf_related_requirements",
    "link_engulf",
    "validate_compiled_engulf",
    "validate_linked_engulf",
]

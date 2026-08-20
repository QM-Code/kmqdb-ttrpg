"""Compile the complete reviewed Core MC1 Push and Pull rider census.

This module is deliberately compile-only.  A forced-movement rider is stored
inside a Strike's exact ``Damage`` member rather than as a standalone creature
ability.  The compiler therefore begins with one untrusted source receipt,
reloads it through an explicit :class:`SourceAuthorityAdapter`, matches it to
one of thirteen hash-pinned consumer requirements, and resolves every rule
provider through the same adapter.

The result preserves the complete Damage text, the selected rider text, its
Strike identity, the ordered consumer and provider receipts, and every
dependency that still blocks runtime activation.  Qarna's unnumbered Push
uses Shove's reviewed default 5-foot success distance.  Jabali, Guthallath,
and Terotricus retain their coupled source grammar and remain explicitly
deferred; no partial source choice is made executable.

There is no registry fragment, activation hook, encounter transition, or
caller-supplied provider path in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Literal, TypeAlias, final

from .contracts import RawSourceMember, RawSourceObject
from .source_authority import (
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    TextSpan,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)
from .source_values import parse_decimal_integer


FAMILY_ID = "forced-movement"
MECHANIC_TYPE = "strike-forced-movement-follow-up"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"
MONSTER_CORE_GLOSSARY_LOCATOR = "358.2"
CONSUMER_CENSUS_COUNT = 13
MAX_FORCED_MOVEMENT_FEET = 10_000
MAX_SOURCE_TEXT_BYTES = 512

MovementModeId: TypeAlias = Literal["push", "pull"]
SourceVariant: TypeAlias = Literal[
    "improved-push",
    "push",
    "push-or-pull",
]
SourceCoupling: TypeAlias = Literal[
    "direct",
    "improved-grab-choice",
    "stone-clutch-conjunction",
]
WindowKind: TypeAlias = Literal[
    "immediately-next-action",
    "triggered-on-hit",
]
ModeSelection: TypeAlias = Literal["choose-exactly-one", "fixed"]
DependencyPhase: TypeAlias = Literal["source-link", "runtime"]
DeferredMechanic: TypeAlias = Literal[
    "athletics-check-resolution",
    "counter-reposition",
    "forced-path-resolution",
    "hazard-and-falling-resolution",
    "immediate-follow-up-window",
    "improved-grab-choice-coupling",
    "movement-trigger-suppression",
    "post-push-stride",
    "stone-clutch-coupling",
    "strike-rider-linker",
    "triggered-free-action-window",
]

_LOCATOR_RE = re.compile(r"^[0-9]+\.[0-9]+$", re.ASCII)
_PUSH_RE = re.compile(
    r"^Push(?: (?P<distance>[1-9][0-9]*) feet)? \(page 359\)$",
    re.ASCII,
)
_PUSH_OR_PULL_RE = re.compile(
    r"^Push or Pull (?P<distance>[1-9][0-9]*) feet \(page 359\)$",
    re.ASCII,
)
_IMPROVED_PUSH_RE = re.compile(
    r"^Improved Push (?P<distance>[1-9][0-9]*) feet \(page 359\)$",
    re.ASCII,
)

# A path descriptor is deliberately a tuple of exact immutable primitives.
# ``("m", raw_key, absolute_member_ordinal)`` selects an object pair and
# ``("i", absolute_item_ordinal)`` selects an array item.
_PathSpec = tuple[tuple[object, ...], ...]

# Consumer spec fields:
# rule id, locator, strike id, complete Damage text, selected rider text,
# variant, listed distance, source coupling, carrier path, Damage ordinal,
# span start, span end, block/member/value/selection hashes.
_ConsumerSpec = tuple[object, ...]
_CONSUMER_SPECS: tuple[_ConsumerSpec, ...] = (
    (
        "forced-movement-consumer:qarna-horn",
        "27.2",
        "horn",
        "1d8+9 piercing plus Push (page 359)",
        "Push (page 359)",
        "push",
        None,
        "direct",
        (("m", "^.creature", 1), ("m", "Melee", 23), ("i", 0)),
        3,
        20,
        35,
        "b5adb50c10ec75ebf0c55eccd907238472a8f0f07529a7d973b1af976c3e0a5d",
        "862dda52edbe83bf8953d969857252d194ba6542f458650b30c81348818e536c",
        "feb6bc2ebef97eccb63712e2919bb42015ba5d3555058dbd8e42c52234dc706c",
        "31e4f1932cf8c3535189f23fe6143c1e218729631f261242bb2af47c6fc8d502",
    ),
    (
        "forced-movement-consumer:desert-drake-tail",
        "133.1",
        "tail",
        "2d8+10 bludgeoning plus Push 5 feet (page 359)",
        "Push 5 feet (page 359)",
        "push",
        5,
        "direct",
        (("m", "^.creature", 3), ("m", "Melee", 23), ("i", 1)),
        3,
        24,
        46,
        "2f6cf0aaef4f14fd8fcb574037b1c32d8ae55864e0c9fb475a9168ea9acb00d7",
        "11b8932e5f20b8ff9c5890d124a65c9e5cca8f5dc1ae11a733f0018bc816b4f8",
        "6b3d4d6a72c3359623046959b8421d0d9dbbd1536fa063810344226126987206",
        "b0e0c21e24fb6e694994a7eed43aacdc0d0d6b97481ef055370993985ba5ffcc",
    ),
    (
        "forced-movement-consumer:elemental-hurricane-gust",
        "141.2",
        "gust",
        "2d10+12 bludgeoning plus Push 10 feet (page 359)",
        "Push 10 feet (page 359)",
        "push",
        10,
        "direct",
        (("m", "^.creature", 1), ("m", "Melee", 22), ("i", 0)),
        3,
        25,
        48,
        "2cbfdaf74d083e63f5e8b8aa7f4945c0c3fd4ca202bf0f1125d712fb4a6f6af1",
        "29448eefdd441b46a6561f137cb2a728a7b1e9cf665c4a02b89f392e0c1231e6",
        "a39d00b8a5b5498ac8e8d3abf1432dbfbbec50be51008e52ebb06293a4e7e8d5",
        "78d7c8bfa31e8db3e4e6808e4d9630e400d76f3c1943ddb5e8b3877d8b84b51a",
    ),
    (
        "forced-movement-consumer:stone-mauler-fist",
        "142.6",
        "fist",
        "2d10+10 bludgeoning plus Push 10 feet (page 359)",
        "Push 10 feet (page 359)",
        "push",
        10,
        "direct",
        (("m", "^.creature", 1), ("m", "Melee", 23), ("i", 0)),
        3,
        25,
        48,
        "39804886ff69508e6419e616eddc78ffe0f451ed92ee01f3236dc0e04b2749db",
        "d0e48efcfe1232fd36c6f0f67cbb112b121a1d88ba2cc074b147171a597881c1",
        "dae44cfd10dd836385092971f34d6895786f7eb2988c4f45821abd55c2f21b3c",
        "78d7c8bfa31e8db3e4e6808e4d9630e400d76f3c1943ddb5e8b3877d8b84b51a",
    ),
    (
        "forced-movement-consumer:living-waterfall-wave",
        "148.4",
        "wave",
        "2d8+7 bludgeoning plus Push or Pull 5 feet (page 359)",
        "Push or Pull 5 feet (page 359)",
        "push-or-pull",
        5,
        "direct",
        (("m", "^.creature", 1), ("m", "Melee", 23), ("i", 0)),
        3,
        23,
        53,
        "85b7bd9ba2c3266f5577fed4522e38331cfb63d9237da3a18bdd3b34b7c1f391",
        "d3b9d098af7f6279a45ba764b1016c53c2f32ca2b46bfee62ea42333d4c799df",
        "2c08ed33ced93ee967ec6e03951a51552b44c4c7d831d9fedf7e9e95786abaea",
        "12f29ed1356a44813eb940bb358ce9dfd65fb1c01421e37ab02922e992840b3e",
    ),
    (
        "forced-movement-consumer:elemental-tsunami-wave",
        "149.2",
        "wave",
        "2d12+12 bludgeoning plus Push or Pull 10 feet (page 359)",
        "Push or Pull 10 feet (page 359)",
        "push-or-pull",
        10,
        "direct",
        (("m", "^.creature", 1), ("m", "Melee", 23), ("i", 0)),
        3,
        25,
        56,
        "c31c334392859cf2a3b74b3085e97b965378d884001ca3b4eb65efe7dbfc7700",
        "f056b6f48168af44450ebd484717c16cb263a37c326a90e1a31e9f554d20dd1a",
        "aa1ae14e29f9456e15acb5500fe85a77c11931a9294e651b4b6db04744aef90a",
        "defc7c88d3e27c4cb8b699f34182cb1212aac146710b9761fa797aad250eba4d",
    ),
    (
        "forced-movement-consumer:jabali-fist",
        "158.1",
        "fist",
        "1d4+12 bludgeoning plus Push 10 feet (page 359) and stone clutch",
        "Push 10 feet (page 359)",
        "push",
        10,
        "stone-clutch-conjunction",
        (("m", "^.creature", 1), ("m", "Melee", 20), ("i", 1)),
        3,
        24,
        47,
        "466d615bce62eed0aec7d067fd197657afdb51d596de047112844aa48bacfccf",
        "f94965ec0f033ba62d307c8252b0682f019c4b2e977f800a88e89600e5e09614",
        "7bbf71f7d783cf4be6544cfb7943df2b114cf7a320a78ebbf50c23b27e757149",
        "78d7c8bfa31e8db3e4e6808e4d9630e400d76f3c1943ddb5e8b3877d8b84b51a",
    ),
    (
        "forced-movement-consumer:guthallath-fist",
        "187.1",
        "fist",
        "4d12+18 bludgeoning plus Improved Grab (page 359) or "
        "Improved Push 20 feet (page 359)",
        "Improved Push 20 feet (page 359)",
        "improved-push",
        20,
        "improved-grab-choice",
        (
            ("m", "Guthallath", 1),
            ("m", "Guthallath", 0),
            ("m", "^.creature", 2),
            ("m", "Melee", 23),
            ("i", 0),
        ),
        3,
        53,
        85,
        "0ac72eb34511ca18a23a9dab1ded60eea8712292e4268bec5d8c8081d0c102d5",
        "92593b37c22c3a8239c59de4a7e2708af8ca3c3b137749e77c9a638f793687ad",
        "acb2baed7996664c2f0eb952c9e2f3307cfb58d374f51a3a127cae4b98d2d4c2",
        "3e0124c8237f9e58824599954f5031835dff99c2487928be8f854c8af91e245c",
    ),
    (
        "forced-movement-consumer:roc-wing",
        "294.1",
        "wing",
        "2d6+10 bludgeoning plus Improved Push 10 feet (page 359)",
        "Improved Push 10 feet (page 359)",
        "improved-push",
        10,
        "direct",
        (
            ("m", "Roc", 1),
            ("m", "Roc", 0),
            ("m", "^.creature", 3),
            ("m", "Melee", 20),
            ("i", 2),
        ),
        3,
        24,
        56,
        "9a18152c6aa9c60e11488e558125fa1177dc9d8866903eac561d37c5d194be03",
        "cb2002f20c966b2e25b10cea866a8d59ee2e7f41f78e6583229326e91de5324a",
        "86ebb0c400b7e4321d25fdb73207aee8ae742f83b85b313d5bc75d75ecaa2cb9",
        "493eec970ddd73abf75ba72cd98b1dc88ef935ec00b121c4f927f9b3d1f77c16",
    ),
    (
        "forced-movement-consumer:megalodon-tail",
        "307.4",
        "tail",
        "2d8+10 piercing plus Push 15 feet (page 359)",
        "Push 15 feet (page 359)",
        "push",
        15,
        "direct",
        (("m", "^.creature", 1), ("m", "Melee", 19), ("i", 1)),
        3,
        21,
        44,
        "137d0fd9439f3656474cd912c4e073723f7d74a16369ea94eb25592dbb10685a",
        "011f86dbe1247b5e9c036de892eda3d9c2e8a581dba8188ebc8ba2a3d49ed4c0",
        "ea683992598e553d93368acdf98ff09efd3a71e17cc7a1f56b586463c08a201c",
        "eafab6c9705d038614132d1592cd1e7078a5efb93159b91ccd5166872e5b2958",
    ),
    (
        "forced-movement-consumer:giant-anaconda-tail",
        "317.2",
        "tail",
        "2d8+7 bludgeoning plus Push 10 feet (page 359)",
        "Push 10 feet (page 359)",
        "push",
        10,
        "direct",
        (("m", "^.creature", 1), ("m", "Melee", 19), ("i", 1)),
        3,
        23,
        46,
        "f08a9b26608a791bc0ea3d7612607bc49ea5c3dda1c4903a0aa1f991c6af9219",
        "f88ee184d4aae154d07287eec40504f81bf6f681a0053eea7f5257bcb5020899",
        "f15c8cc24390aa0ec47020daf2ae903374b5040231a7d2638a4befd590cb9c62",
        "78d7c8bfa31e8db3e4e6808e4d9630e400d76f3c1943ddb5e8b3877d8b84b51a",
    ),
    (
        "forced-movement-consumer:terotricus-tentacle",
        "326.1",
        "tentacle",
        "4d10+18 bludgeoning plus 2d6 spirit and Improved Grab (page 359) "
        "or Improved Push 20 feet (page 359)",
        "Improved Push 20 feet (page 359)",
        "improved-push",
        20,
        "improved-grab-choice",
        (
            ("m", "Terotricus", 1),
            ("m", "Terotricus", 0),
            ("m", "^.creature", 1),
            ("m", "Melee", 24),
            ("i", 0),
        ),
        3,
        68,
        100,
        "b6aa09c04a1752db4b1b1083cd8fa3117bc36ad2d846a030e38b494421bd5375",
        "7d5cf7d4f3d4375ee4726b4176af175801aa0003227de9f1f48c2bb1bff2cfd7",
        "8844d393441dcd8158fe3c6f52448a7a23b0637839c586a94e2816f5253a481c",
        "3e0124c8237f9e58824599954f5031835dff99c2487928be8f854c8af91e245c",
    ),
    (
        "forced-movement-consumer:zombie-brute-fist",
        "357.2",
        "fist",
        "1d12+5 bludgeoning plus Improved Push 5 feet (page 359)",
        "Improved Push 5 feet (page 359)",
        "improved-push",
        5,
        "direct",
        (("m", "^.creature", 6), ("m", "Melee", 24), ("i", 0)),
        3,
        24,
        55,
        "90bed40ed8c62ff1538fcf6d8eedbb17a7fb67e78125341d2b85878b17bfbddb",
        "76b79f4160a88093097bb3e31f483b47db4f78ba3650cec1700e40f9f9721cb5",
        "9aef7486e18b5126de8a5dc3c3f16979ae02f16c2aaca341266c45b2dd47959e",
        "6a9adb3e0b801b75573e4b66b71f44f512e4c9a766983892cd82ab239f4911f5",
    ),
)

# Provider spec fields: rule id, source id, locator, carrier path, selected
# block hash.  Every provider selects its complete reviewed block.
_ProviderSpec = tuple[object, ...]
_PROVIDER_SPECS: tuple[_ProviderSpec, ...] = (
    (
        "monster-core-improved-push",
        "core-mc1",
        "358.2",
        (("m", "^.ability", 19),),
        "8c586381b4ec207e318e9af1f594cbe5ae3c39b3d340e550dd799275791908db",
    ),
    (
        "monster-core-pull",
        "core-mc1",
        "358.2",
        (("m", "^.ability", 25),),
        "33f72436a64177c039033a9f95c24b94ffad5f9b8082ed26e4e0316cf782b6a2",
    ),
    (
        "monster-core-push",
        "core-mc1",
        "358.2",
        (("m", "^.ability", 26),),
        "7435490b1a16e13b9bdab44f6b6de36e258fe445f3d1b254c409f04762230883",
    ),
    (
        "player-core-reposition",
        "core-pc1",
        "235.4",
        (),
        "35b61a1b7723ac05a7003cbd01846e630eee748ed5d224f8f2f289c9a2031ea2",
    ),
    (
        "player-core-shove",
        "core-pc1",
        "235.6",
        (),
        "d33cc9af845d0a612e5da4b336a8e309706d0d563cc103ce49d650637c1a2a9d",
    ),
    (
        "player-core-compare-to-dc",
        "core-pc1",
        "401.2",
        (),
        "9ff024bc6158c6efc6b6bdc906ee9a00261adfaae0e80f41e1a09bbd7daafd09",
    ),
    (
        "player-core-degree-of-success",
        "core-pc1",
        "401.4",
        (),
        "05a8ea41e782723a63bed00663d4a4ffadfb446edf869af24b4f2f8a61d3c033",
    ),
    (
        "player-core-subordinate-actions",
        "core-pc1",
        "414.4",
        (),
        "6cca42e564d687b1b3fd6ce074ad87b1a8e055f7f0dd8fe0383bad3a81e4fa1d",
    ),
    (
        "player-core-actions-with-triggers",
        "core-pc1",
        "414.6",
        (),
        "aca6a47fc0d1e9269f4477375a80c4176bca46c7d361dd1ea4922102651299bf",
    ),
    (
        "player-core-stride",
        "core-pc1",
        "418.3",
        (),
        "a15ba248a6375c3a4f8a4c300b16b4fd2c0f433cb0d6b582e1bbfc49fce9193f",
    ),
    (
        "player-core-falling",
        "core-pc1",
        "421.1",
        (),
        "186b99c5b65a376d256d1ed5e7e280efbdb9efe2c6f0821dc798452b30390b6b",
    ),
    (
        "player-core-grid-movement",
        "core-pc1",
        "421.5",
        (),
        "1610c62fb122a577e3f69ec6b2e3f1273f6cb7e535ee9d5529291637a3b9ce67",
    ),
    (
        "player-core-diagonal-movement",
        "core-pc1",
        "421.6",
        (),
        "8932a0244b193fd5fb2dc7ebb8a0623cbf9304d52daa9d03845578a5259ed210",
    ),
    (
        "player-core-size-space-reach",
        "core-pc1",
        "421.8",
        (),
        "57f6c8bd51c2367bedfda5464ec295229a54363d5576a671fbda1fda3ab01fb6",
    ),
    (
        "player-core-creature-space-transit",
        "core-pc1",
        "422.3",
        (),
        "62ef4117bd8ca96e49011793c59b7325af76e8c57f60291aa0f0cd7e1b07a3e0",
    ),
    (
        "player-core-forced-movement",
        "core-pc1",
        "422.7",
        (),
        "9c89056aba0eec571c99b1518c574c8ab6e6815b75003d96f5731e4393362c42",
    ),
    (
        "player-core-hazardous-terrain",
        "core-pc1",
        "423.6",
        (),
        "2db44c3550d4dc17042f03a119dd8e750f262c221b6f55686bfed6ec4ee8b172",
    ),
)


class ForcedMovementCompileError(ValueError):
    """Verified source is outside the complete reviewed family contract."""


def _path_from_spec(value: _PathSpec) -> tuple[RawMemberStep | RawIndexStep, ...]:
    result: list[RawMemberStep | RawIndexStep] = []
    for item in value:
        if (
            type(item) is tuple
            and len(item) == 3
            and item[0] == "m"
            and type(item[1]) is str
            and type(item[2]) is int
        ):
            result.append(
                RawMemberStep(
                    raw_key=item[1],
                    member_ordinal=item[2],
                )
            )
        elif (
            type(item) is tuple
            and len(item) == 2
            and item[0] == "i"
            and type(item[1]) is int
        ):
            result.append(RawIndexStep(item_ordinal=item[1]))
        else:
            raise AssertionError("invalid reviewed forced-movement path")
    return tuple(result)


def _consumer_requirement(
    spec: _ConsumerSpec,
    _source_id: str = "core-mc1",
) -> RuleRequirement:
    return RuleRequirement(
        rule_id=spec[0],
        source_id=_source_id,
        locator=spec[1],
        carrier_path=_path_from_spec(spec[8]),
        selection_path=(
            RawMemberStep(
                raw_key="Damage",
                member_ordinal=spec[9],
            ),
        ),
        span=TextSpan(start=spec[10], end=spec[11]),
        expected_block_sha256=spec[12],
        expected_member_sha256=spec[13],
        expected_value_sha256=spec[14],
        expected_selection_sha256=spec[15],
    )


def _provider_requirement(spec: _ProviderSpec) -> RuleRequirement:
    return RuleRequirement(
        rule_id=spec[0],
        source_id=spec[1],
        locator=spec[2],
        carrier_path=_path_from_spec(spec[3]),
        expected_block_sha256=spec[4],
        expected_value_sha256=spec[4],
        expected_selection_sha256=spec[4],
    )


def _forced_movement_consumer_requirements(
    specs: tuple[_ConsumerSpec, ...],
) -> tuple[RuleRequirement, ...]:
    return tuple(_consumer_requirement(spec) for spec in specs)


def _forced_movement_provider_requirements(
    specs: tuple[_ProviderSpec, ...],
) -> tuple[RuleRequirement, ...]:
    return tuple(_provider_requirement(spec) for spec in specs)


def _require_exact_text(
    value: object,
    label: str,
    *,
    maximum_bytes: int = MAX_SOURCE_TEXT_BYTES,
) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be an exact string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    if len(value.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{label} exceeds its byte bound")
    return value


def _valid_locator(
    value: object,
    _pattern: re.Pattern[str] = _LOCATOR_RE,
) -> bool:
    return type(value) is str and _pattern.fullmatch(value) is not None


@final
@dataclass(frozen=True, slots=True)
class ForcedMovementMode:
    """One fully normalized Push or Pull subordinate-action branch."""

    mode_id: MovementModeId
    subordinate_action: Literal["Reposition", "Shove"]
    success_maximum_feet: int
    critical_success_maximum_feet: int
    critical_failure: Literal[
        "source-falls-prone",
        "target-may-counter-reposition-source-5-feet",
    ]
    path_constraint: Literal[
        "monotonically-closer-and-within-source-reach",
        "straight-away-from-source",
    ]
    allows_source_follow_stride: bool

    def __post_init__(self) -> None:
        if type(self) is not ForcedMovementMode:
            raise TypeError("ForcedMovementMode subclasses are unsupported")
        _require_initialized_slots(
            self,
            tuple(
                field_name for field_name in ForcedMovementMode.__slots__
            ),
            "forced-movement mode",
        )
        if type(self.mode_id) is not str or self.mode_id not in ("push", "pull"):
            raise ValueError("ForcedMovementMode.mode_id is invalid")
        expected = (
            (
                "Shove",
                "source-falls-prone",
                "straight-away-from-source",
                True,
            )
            if self.mode_id == "push"
            else (
                "Reposition",
                "target-may-counter-reposition-source-5-feet",
                "monotonically-closer-and-within-source-reach",
                False,
            )
        )
        if (
            type(self.subordinate_action) is not str
            or type(self.critical_failure) is not str
            or type(self.path_constraint) is not str
            or type(self.allows_source_follow_stride) is not bool
            or (
                self.subordinate_action,
                self.critical_failure,
                self.path_constraint,
                self.allows_source_follow_stride,
            )
            != expected
        ):
            raise ValueError("ForcedMovementMode semantics are inconsistent")
        for field_name in (
            "success_maximum_feet",
            "critical_success_maximum_feet",
        ):
            distance = getattr(self, field_name)
            if (
                type(distance) is not int
                or distance <= 0
                or distance > 10_000
                or distance % 5
            ):
                raise ValueError(
                    f"ForcedMovementMode.{field_name} is invalid"
                )
        if self.critical_success_maximum_feet != 10:
            raise ValueError(
                "ForcedMovementMode critical success must retain 10 feet"
            )

    def as_serialized(self) -> dict[str, Any]:
        ForcedMovementMode.__post_init__(self)
        return {
            "id": self.mode_id,
            "subordinateAction": self.subordinate_action,
            "check": "Athletics",
            "targetDC": "Fortitude",
            "success": {
                "maximumFeet": self.success_maximum_feet,
                "voluntaryShortening": True,
                "obstructionCanShorten": True,
            },
            "criticalSuccess": {
                "maximumFeet": self.critical_success_maximum_feet,
                "voluntaryShortening": True,
                "obstructionCanShorten": True,
            },
            "criticalFailure": self.critical_failure,
            "pathConstraint": self.path_constraint,
            "allowsHazardousTerrain": True,
            "allowsLedge": True,
            "allowsSourceFollowStride": self.allows_source_follow_stride,
        }


@final
@dataclass(frozen=True, slots=True)
class DeferredForcedMovementDependency:
    """One typed missing contract that blocks runtime activation."""

    dependency_id: str
    phase: DependencyPhase
    mechanic: DeferredMechanic
    required_contract: str

    def __post_init__(self) -> None:
        if type(self) is not DeferredForcedMovementDependency:
            raise TypeError(
                "DeferredForcedMovementDependency subclasses are unsupported"
            )
        _require_initialized_slots(
            self,
            tuple(
                field_name
                for field_name in DeferredForcedMovementDependency.__slots__
            ),
            "deferred forced-movement dependency",
        )
        _require_exact_text(
            self.dependency_id,
            "DeferredForcedMovementDependency.dependency_id",
        )
        if (
            type(self.phase) is not str
            or self.phase not in ("source-link", "runtime")
        ):
            raise ValueError(
                "DeferredForcedMovementDependency.phase is invalid"
            )
        if (
            type(self.mechanic) is not str
            or self.mechanic
            not in (
                "athletics-check-resolution",
                "counter-reposition",
                "forced-path-resolution",
                "hazard-and-falling-resolution",
                "immediate-follow-up-window",
                "improved-grab-choice-coupling",
                "movement-trigger-suppression",
                "post-push-stride",
                "stone-clutch-coupling",
                "strike-rider-linker",
                "triggered-free-action-window",
            )
        ):
            raise ValueError(
                "DeferredForcedMovementDependency.mechanic is invalid"
            )
        _require_exact_text(
            self.required_contract,
            "DeferredForcedMovementDependency.required_contract",
        )

    def as_serialized(self) -> dict[str, str]:
        DeferredForcedMovementDependency.__post_init__(self)
        return {
            "id": self.dependency_id,
            "phase": self.phase,
            "mechanic": self.mechanic,
            "requiredContract": self.required_contract,
            "status": "deferred",
            "blocks": "registry-activation",
        }


def _dependency_specs(
    variant: SourceVariant,
    coupling: SourceCoupling,
) -> tuple[tuple[str, DependencyPhase, DeferredMechanic, str], ...]:
    window = (
        (
            "triggered-free-action-window",
            "runtime",
            "triggered-free-action-window",
            "successful Strike hit opens one optional free-action window",
        )
        if variant == "improved-push"
        else (
            "immediate-follow-up-window",
            "runtime",
            "immediate-follow-up-window",
            "the rider must be the creature's immediately next action",
        )
    )
    result: list[
        tuple[str, DependencyPhase, DeferredMechanic, str]
    ] = [
        (
            "shared-strike-rider-linker",
            "source-link",
            "strike-rider-linker",
            "lossless Strike compilation must mount this exact Damage rider",
        ),
        window,
        (
            "athletics-subordinate-action-resolution",
            "runtime",
            "athletics-check-resolution",
            "resolve the subordinate Athletics attack against Fortitude DC "
            "without applying or advancing MAP",
        ),
        (
            "forced-path-and-footprint-resolution",
            "runtime",
            "forced-path-resolution",
            "validate every occupied square, obstruction, shortening, reach, "
            "and mode-specific path constraint",
        ),
        (
            "forced-versus-voluntary-reaction-policy",
            "runtime",
            "movement-trigger-suppression",
            "suppress movement reactions only for the forced target path",
        ),
        (
            "hazard-ledge-and-falling-resolution",
            "runtime",
            "hazard-and-falling-resolution",
            "resolve hazardous terrain, ledges, falling, and nested reactions",
        ),
    ]
    if variant in ("push", "improved-push", "push-or-pull"):
        result.append(
            (
                "optional-post-push-stride",
                "runtime",
                "post-push-stride",
                "resolve the source's same-distance, same-direction voluntary "
                "Stride with ordinary movement reactions",
            )
        )
    if variant == "push-or-pull":
        result.append(
            (
                "pull-critical-failure-counter-reposition",
                "runtime",
                "counter-reposition",
                "the original target chooses the safe counter-Reposition path",
            )
        )
    if coupling == "stone-clutch-conjunction":
        result.append(
            (
                "jabali-stone-clutch-coupling",
                "source-link",
                "stone-clutch-coupling",
                "preserve and resolve stone clutch with the same Damage rider",
            )
        )
    elif coupling == "improved-grab-choice":
        result.append(
            (
                "improved-grab-or-push-exclusive-choice",
                "source-link",
                "improved-grab-choice-coupling",
                "preserve one exclusive Improved Grab or Improved Push choice",
            )
        )
    return tuple(result)


def _dependencies(
    variant: SourceVariant,
    coupling: SourceCoupling,
) -> tuple[DeferredForcedMovementDependency, ...]:
    return tuple(
        DeferredForcedMovementDependency(
            dependency_id=dependency_id,
            phase=phase,
            mechanic=mechanic,
            required_contract=required_contract,
        )
        for dependency_id, phase, mechanic, required_contract
        in _dependency_specs(variant, coupling)
    )


def _mode(mode_id: MovementModeId, success_feet: int) -> ForcedMovementMode:
    if mode_id == "push":
        return ForcedMovementMode(
            mode_id="push",
            subordinate_action="Shove",
            success_maximum_feet=success_feet,
            critical_success_maximum_feet=10,
            critical_failure="source-falls-prone",
            path_constraint="straight-away-from-source",
            allows_source_follow_stride=True,
        )
    if mode_id == "pull":
        return ForcedMovementMode(
            mode_id="pull",
            subordinate_action="Reposition",
            success_maximum_feet=success_feet,
            critical_success_maximum_feet=10,
            critical_failure="target-may-counter-reposition-source-5-feet",
            path_constraint="monotonically-closer-and-within-source-reach",
            allows_source_follow_stride=False,
        )
    raise AssertionError("invalid reviewed forced-movement mode")


def _expected_provider_ids(variant: SourceVariant) -> tuple[str, ...]:
    leading: tuple[str, ...]
    if variant == "improved-push":
        leading = (
            "monster-core-improved-push",
            "monster-core-push",
            "player-core-subordinate-actions",
            "player-core-shove",
            "player-core-actions-with-triggers",
        )
    elif variant == "push-or-pull":
        leading = (
            "monster-core-push",
            "monster-core-pull",
            "player-core-subordinate-actions",
            "player-core-shove",
            "player-core-reposition",
        )
    elif variant == "push":
        leading = (
            "monster-core-push",
            "player-core-subordinate-actions",
            "player-core-shove",
        )
    else:
        raise AssertionError("invalid reviewed forced-movement variant")
    return (
        *leading,
        "player-core-compare-to-dc",
        "player-core-degree-of-success",
        "player-core-grid-movement",
        "player-core-diagonal-movement",
        "player-core-size-space-reach",
        "player-core-creature-space-transit",
        "player-core-forced-movement",
        "player-core-hazardous-terrain",
        "player-core-falling",
        "player-core-stride",
    )


@final
@dataclass(frozen=True, slots=True)
class CompiledForcedMovementRider:
    """One canonical compile-only rider and its authenticated evidence."""

    source_id: str
    locator: str
    strike_id: str
    damage_source_text: str
    source_text: str
    variant: SourceVariant
    source_coupling: SourceCoupling
    listed_success_distance_feet: int | None
    success_distance_feet: int
    window: WindowKind
    action_cost: int
    modes: tuple[ForcedMovementMode, ...]
    mode_selection: ModeSelection
    consumer_rule: VerifiedRuleReceipt
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    dependencies: tuple[DeferredForcedMovementDependency, ...]

    def __post_init__(self) -> None:
        if type(self) is not CompiledForcedMovementRider:
            raise TypeError(
                "CompiledForcedMovementRider subclasses are unsupported"
            )
        _require_initialized_slots(
            self,
            tuple(
                field_name
                for field_name in CompiledForcedMovementRider.__slots__
            ),
            "compiled forced movement",
        )
        if (
            type(self.source_id) is not str
            or self.source_id != "core-mc1"
        ):
            raise ValueError(
                "CompiledForcedMovementRider.source_id is invalid"
            )
        if (
            not _valid_locator(self.locator)
        ):
            raise ValueError("CompiledForcedMovementRider.locator is invalid")
        _require_exact_text(
            self.strike_id,
            "CompiledForcedMovementRider.strike_id",
        )
        _require_exact_text(
            self.damage_source_text,
            "CompiledForcedMovementRider.damage_source_text",
        )
        _require_exact_text(
            self.source_text,
            "CompiledForcedMovementRider.source_text",
        )
        if (
            type(self.variant) is not str
            or self.variant
            not in ("improved-push", "push", "push-or-pull")
        ):
            raise ValueError("CompiledForcedMovementRider.variant is invalid")
        if (
            type(self.source_coupling) is not str
            or self.source_coupling
            not in (
                "direct",
                "improved-grab-choice",
                "stone-clutch-conjunction",
            )
        ):
            raise ValueError(
                "CompiledForcedMovementRider.source_coupling is invalid"
            )
        if self.listed_success_distance_feet is not None and (
            type(self.listed_success_distance_feet) is not int
            or self.listed_success_distance_feet <= 0
            or self.listed_success_distance_feet > 10_000
            or self.listed_success_distance_feet % 5
        ):
            raise ValueError(
                "CompiledForcedMovementRider listed distance is invalid"
            )
        if (
            type(self.success_distance_feet) is not int
            or self.success_distance_feet <= 0
            or self.success_distance_feet > 10_000
            or self.success_distance_feet % 5
        ):
            raise ValueError(
                "CompiledForcedMovementRider success distance is invalid"
            )
        if (
            type(self.window) is not str
            or self.window
            not in ("immediately-next-action", "triggered-on-hit")
        ):
            raise ValueError("CompiledForcedMovementRider.window is invalid")
        if type(self.action_cost) is not int or self.action_cost not in (0, 1):
            raise ValueError(
                "CompiledForcedMovementRider.action_cost is invalid"
            )
        if (
            type(self.modes) is not tuple
            or not self.modes
            or len(self.modes) > 2
            or any(type(item) is not ForcedMovementMode for item in self.modes)
        ):
            raise TypeError("CompiledForcedMovementRider.modes is invalid")
        if (
            type(self.mode_selection) is not str
            or self.mode_selection not in ("choose-exactly-one", "fixed")
        ):
            raise ValueError(
                "CompiledForcedMovementRider.mode_selection is invalid"
            )
        if type(self.consumer_rule) is not VerifiedRuleReceipt:
            raise TypeError(
                "CompiledForcedMovementRider.consumer_rule is invalid"
            )
        if (
            type(self.provider_rules) is not tuple
            or not self.provider_rules
            or any(
                type(item) is not VerifiedRuleReceipt
                for item in self.provider_rules
            )
        ):
            raise TypeError(
                "CompiledForcedMovementRider.provider_rules is invalid"
            )
        if (
            type(self.dependencies) is not tuple
            or not self.dependencies
            or any(
                type(item) is not DeferredForcedMovementDependency
                for item in self.dependencies
            )
        ):
            raise TypeError(
                "CompiledForcedMovementRider.dependencies is invalid"
            )

    def as_serialized(
        self,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        raise TypeError("compiled forced-movement contract is not bound")


def _spec_variant(spec: _ConsumerSpec) -> SourceVariant:
    return spec[5]  # type: ignore[return-value]


def _spec_coupling(spec: _ConsumerSpec) -> SourceCoupling:
    return spec[7]  # type: ignore[return-value]


def _provider_spec_map(
    specs: tuple[_ProviderSpec, ...],
) -> dict[str, _ProviderSpec]:
    result: dict[str, _ProviderSpec] = {}
    for spec in specs:
        rule_id = spec[0]
        if type(rule_id) is not str or rule_id in result:
            raise AssertionError("invalid reviewed provider inventory")
        result[rule_id] = spec
    return result


def _same_requirement(
    left: RuleRequirement,
    right: RuleRequirement,
) -> bool:
    return canonical_json_bytes(
        RuleRequirement.as_serialized(left)
    ) == canonical_json_bytes(
        RuleRequirement.as_serialized(right)
    )


def _same_receipt(left: SourceReceipt, right: SourceReceipt) -> bool:
    return canonical_json_bytes(
        SourceReceipt.as_serialized(left)
    ) == canonical_json_bytes(
        SourceReceipt.as_serialized(right)
    )


def _consumer_and_spec(
    authority: SourceAuthorityAdapter,
    consumer_receipt: SourceReceipt,
    consumer_specs: tuple[_ConsumerSpec, ...],
) -> tuple[
    VerifiedSourceSelection,
    VerifiedRuleReceipt,
    _ConsumerSpec,
]:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "forced-movement compilation requires SourceAuthorityAdapter"
        )
    if type(consumer_receipt) is not SourceReceipt:
        raise TypeError(
            "forced-movement compilation requires an exact SourceReceipt"
        )
    consumer = authority.validate_selection(
        authority.reload(consumer_receipt)
    )
    candidates = tuple(
        spec
        for spec in consumer_specs
        if spec[1] == consumer.address.locator
        and consumer.address.source_id == "core-mc1"
    )
    matches: list[tuple[VerifiedRuleReceipt, _ConsumerSpec]] = []
    for spec in candidates:
        rule = authority.validate_rule(
            authority.resolve_rule(_consumer_requirement(spec))
        )
        if _same_receipt(rule.receipt, consumer.receipt):
            matches.append((rule, spec))
    if len(matches) != 1:
        raise ForcedMovementCompileError(
            "consumer is not one exact reviewed forced-movement rider"
        )
    consumer_rule, spec = matches[0]
    authority.require_shared_authority(consumer, (consumer_rule,))
    return consumer, consumer_rule, spec


def _source_shape(
    consumer: VerifiedSourceSelection,
    spec: _ConsumerSpec,
    _push_re: re.Pattern[str] = _PUSH_RE,
    _push_or_pull_re: re.Pattern[str] = _PUSH_OR_PULL_RE,
    _improved_push_re: re.Pattern[str] = _IMPROVED_PUSH_RE,
    _parse_decimal_integer: Any = parse_decimal_integer,
    _maximum_feet: int = 10_000,
) -> None:
    block = consumer.carrier.raw_block
    if (
        type(block) is not RawSourceObject
        or type(block.members) is not tuple
        or len(block.members) != 4
        or any(type(item) is not RawSourceMember for item in block.members)
        or tuple(item.key for item in block.members)
        != ("Name", "Attack", "Traits", "Damage")
        or type(block.members[0].value) is not str
        or block.members[0].value != spec[2]
        or type(block.members[3].value) is not str
        or block.members[3].value != spec[3]
        or type(consumer.raw_value) is not str
        or consumer.raw_value != spec[3]
        or type(consumer.selected_value) is not str
        or consumer.selected_value != spec[4]
    ):
        raise ForcedMovementCompileError(
            "verified Strike carrier differs from its reviewed source shape"
        )

    source_text = consumer.selected_value
    variant = _spec_variant(spec)
    if variant == "improved-push":
        match = _improved_push_re.fullmatch(source_text)
    elif variant == "push-or-pull":
        match = _push_or_pull_re.fullmatch(source_text)
    else:
        match = _push_re.fullmatch(source_text)
    if match is None:
        raise ForcedMovementCompileError(
            "verified rider text differs from its reviewed grammar"
        )
    distance_text = match.groupdict().get("distance")
    distance = (
        None
        if distance_text is None
        else _parse_decimal_integer(distance_text)
    )
    if (
        distance != spec[6]
        or (
            distance is not None
            and (
                distance <= 0
                or distance > _maximum_feet
                or distance % 5
            )
        )
    ):
        raise ForcedMovementCompileError(
            "verified rider distance differs from its reviewed value"
        )


def _resolve_providers(
    authority: SourceAuthorityAdapter,
    consumer: VerifiedSourceSelection,
    consumer_rule: VerifiedRuleReceipt,
    variant: SourceVariant,
    provider_specs: tuple[_ProviderSpec, ...],
) -> tuple[VerifiedRuleReceipt, ...]:
    by_id = _provider_spec_map(provider_specs)
    rules: list[VerifiedRuleReceipt] = []
    for rule_id in _expected_provider_ids(variant):
        try:
            spec = by_id[rule_id]
        except KeyError as failure:
            raise AssertionError(
                f"missing reviewed forced-movement provider: {rule_id}"
            ) from failure
        expected = _provider_requirement(spec)
        rule = authority.validate_rule(authority.resolve_rule(expected))
        if (
            rule.rule_id != rule_id
            or type(rule.requirement) is not RuleRequirement
            or not _same_requirement(rule.requirement, expected)
        ):
            raise ForcedMovementCompileError(
                f"verified provider differs from reviewed rule: {rule_id}"
            )
        rules.append(rule)
    result = tuple(rules)
    authority.require_shared_authority(
        consumer,
        (consumer_rule, *result),
    )
    return result


def _canonical_compiled(
    spec: _ConsumerSpec,
    consumer_rule: VerifiedRuleReceipt,
    provider_rules: tuple[VerifiedRuleReceipt, ...],
) -> CompiledForcedMovementRider:
    variant = _spec_variant(spec)
    coupling = _spec_coupling(spec)
    listed_distance = spec[6]
    success_distance = 5 if listed_distance is None else listed_distance
    mode_ids: tuple[MovementModeId, ...] = (
        ("push", "pull")
        if variant == "push-or-pull"
        else ("push",)
    )
    return CompiledForcedMovementRider(
        source_id="core-mc1",
        locator=spec[1],
        strike_id=spec[2],
        damage_source_text=spec[3],
        source_text=spec[4],
        variant=variant,
        source_coupling=coupling,
        listed_success_distance_feet=listed_distance,
        success_distance_feet=success_distance,
        window=(
            "triggered-on-hit"
            if variant == "improved-push"
            else "immediately-next-action"
        ),
        action_cost=0 if variant == "improved-push" else 1,
        modes=tuple(_mode(item, success_distance) for item in mode_ids),
        mode_selection=(
            "choose-exactly-one"
            if variant == "push-or-pull"
            else "fixed"
        ),
        consumer_rule=consumer_rule,
        provider_rules=provider_rules,
        dependencies=_dependencies(variant, coupling),
    )


def _compile_forced_movement_rider(
    authority: SourceAuthorityAdapter,
    consumer_receipt: SourceReceipt,
    consumer_specs: tuple[_ConsumerSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    payload_impl: Callable[
        [CompiledForcedMovementRider],
        dict[str, Any],
    ],
) -> CompiledForcedMovementRider:
    consumer, consumer_rule, spec = _consumer_and_spec(
        authority,
        consumer_receipt,
        consumer_specs,
    )
    _source_shape(consumer, spec)
    provider_rules = _resolve_providers(
        authority,
        consumer,
        consumer_rule,
        _spec_variant(spec),
        provider_specs,
    )
    result = _canonical_compiled(spec, consumer_rule, provider_rules)
    _validate_compiled_forced_movement(
        authority,
        result,
        consumer_specs,
        provider_specs,
        payload_impl,
    )
    return result


def _compile_forced_movement_census(
    authority: SourceAuthorityAdapter,
    consumer_specs: tuple[_ConsumerSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    payload_impl: Callable[
        [CompiledForcedMovementRider],
        dict[str, Any],
    ],
) -> tuple[CompiledForcedMovementRider, ...]:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "forced-movement census requires SourceAuthorityAdapter"
        )
    result: list[CompiledForcedMovementRider] = []
    for spec in consumer_specs:
        consumer_rule = authority.validate_rule(
            authority.resolve_rule(_consumer_requirement(spec))
        )
        consumer = authority.validate_selection(consumer_rule.selection)
        _source_shape(consumer, spec)
        providers = _resolve_providers(
            authority,
            consumer,
            consumer_rule,
            _spec_variant(spec),
            provider_specs,
        )
        result.append(_canonical_compiled(spec, consumer_rule, providers))
    compiled = tuple(result)
    if len(compiled) != 13:
        raise AssertionError("reviewed forced-movement census is incomplete")
    for item in compiled:
        _validate_compiled_shape(
            authority,
            item,
            consumer_specs,
            provider_specs,
            payload_impl,
        )
    return compiled


def _compiled_payload(value: CompiledForcedMovementRider) -> dict[str, Any]:
    return {
        "family": "forced-movement",
        "mechanicType": "strike-forced-movement-follow-up",
        "sourceId": value.source_id,
        "locator": value.locator,
        "strikeId": value.strike_id,
        "damageSourceText": value.damage_source_text,
        "sourceText": value.source_text,
        "sourceVariant": value.variant,
        "sourceCoupling": value.source_coupling,
        "listedSuccessDistanceFeet": value.listed_success_distance_feet,
        "successDistanceFeet": value.success_distance_feet,
        "trigger": "successful-listed-strike-hit",
        "window": value.window,
        "actionCost": value.action_cost,
        "traits": ["attack"],
        "multipleAttackPenalty": {"applies": False, "counts": False},
        "maximumTargetSizeDelta": 1,
        "modes": [item.as_serialized() for item in value.modes],
        "modeSelection": value.mode_selection,
        "consumerRule": value.consumer_rule.as_serialized(),
        "providerRules": [
            item.as_serialized() for item in value.provider_rules
        ],
        "deferredMechanics": [
            item.as_serialized() for item in value.dependencies
        ],
        "activationStatus": "deferred",
    }


def _require_initialized_slots(
    value: object,
    field_names: tuple[str, ...],
    label: str,
) -> None:
    try:
        for field_name in field_names:
            object.__getattribute__(value, field_name)
    except AttributeError as failure:
        raise ForcedMovementCompileError(
            f"{label} is uninitialized"
        ) from failure


def _require_rule_surface(
    value: object,
    label: str,
) -> VerifiedRuleReceipt:
    if type(value) is not VerifiedRuleReceipt:
        raise TypeError(f"{label} must be an exact VerifiedRuleReceipt")
    _require_initialized_slots(
        value,
        (
            "rule_id",
            "requirement",
            "selection",
            "receipt",
            "_capability",
        ),
        label,
    )
    if (
        type(value.rule_id) is not str
        or type(value.requirement) is not RuleRequirement
        or type(value.selection) is not VerifiedSourceSelection
        or type(value.receipt) is not SourceReceipt
    ):
        raise ForcedMovementCompileError(
            f"{label} has invalid structural fields"
        )
    return value


def _validate_compiled_shape(
    authority: SourceAuthorityAdapter,
    value: CompiledForcedMovementRider,
    consumer_specs: tuple[_ConsumerSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    payload_impl: Callable[
        [CompiledForcedMovementRider],
        dict[str, Any],
    ],
) -> tuple[_ConsumerSpec, dict[str, Any]]:
    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError(
            "compiled forced movement requires SourceAuthorityAdapter"
        )
    if type(value) is not CompiledForcedMovementRider:
        raise TypeError(
            "compiled forced movement must be CompiledForcedMovementRider"
        )
    _require_initialized_slots(
        value,
        tuple(
            field_name
            for field_name in CompiledForcedMovementRider.__slots__
        ),
        "compiled forced movement",
    )
    CompiledForcedMovementRider.__post_init__(value)
    for mode in value.modes:
        _require_initialized_slots(
            mode,
            tuple(
                field_name for field_name in ForcedMovementMode.__slots__
            ),
            "compiled forced-movement mode",
        )
        ForcedMovementMode.__post_init__(mode)
    for dependency in value.dependencies:
        _require_initialized_slots(
            dependency,
            tuple(
                field_name
                for field_name in DeferredForcedMovementDependency.__slots__
            ),
            "compiled forced-movement dependency",
        )
        DeferredForcedMovementDependency.__post_init__(dependency)

    consumer_rule = authority.validate_rule(
        _require_rule_surface(
            value.consumer_rule,
            "compiled forced-movement consumer",
        )
    )
    candidates = tuple(
        spec
        for spec in consumer_specs
        if spec[0] == consumer_rule.rule_id
    )
    if len(candidates) != 1:
        raise ForcedMovementCompileError(
            "compiled consumer rule is outside the reviewed census"
        )
    spec = candidates[0]
    expected_consumer = _consumer_requirement(spec)
    if not _same_requirement(consumer_rule.requirement, expected_consumer):
        raise ForcedMovementCompileError(
            "compiled consumer retained the wrong reviewed requirement"
        )
    consumer = authority.validate_selection(consumer_rule.selection)
    _source_shape(consumer, spec)

    expected_provider_ids = _expected_provider_ids(_spec_variant(spec))
    for provider in value.provider_rules:
        _require_rule_surface(
            provider,
            "compiled forced-movement provider",
        )
    if (
        type(value.provider_rules) is not tuple
        or tuple(item.rule_id for item in value.provider_rules)
        != expected_provider_ids
    ):
        raise ForcedMovementCompileError(
            "compiled provider order or membership is invalid"
        )
    provider_by_id = _provider_spec_map(provider_specs)
    verified_providers: list[VerifiedRuleReceipt] = []
    for provider in value.provider_rules:
        verified = authority.validate_rule(provider)
        expected_provider = _provider_requirement(
            provider_by_id[verified.rule_id]
        )
        if not _same_requirement(
            verified.requirement,
            expected_provider,
        ):
            raise ForcedMovementCompileError(
                "compiled provider retained the wrong reviewed requirement"
            )
        verified_providers.append(verified)
    authority.require_shared_authority(
        consumer,
        (consumer_rule, *tuple(verified_providers)),
    )
    payload = payload_impl(value)
    canonical_json_bytes(payload)
    return spec, payload


def _validate_compiled_forced_movement(
    authority: SourceAuthorityAdapter,
    value: CompiledForcedMovementRider,
    consumer_specs: tuple[_ConsumerSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    payload_impl: Callable[
        [CompiledForcedMovementRider],
        dict[str, Any],
    ],
) -> CompiledForcedMovementRider:
    spec, supplied_payload = _validate_compiled_shape(
        authority,
        value,
        consumer_specs,
        provider_specs,
        payload_impl,
    )
    canonical = _canonical_compiled(
        spec,
        value.consumer_rule,
        value.provider_rules,
    )
    _canonical_spec, canonical_payload = _validate_compiled_shape(
        authority,
        canonical,
        consumer_specs,
        provider_specs,
        payload_impl,
    )
    if canonical_json_bytes(supplied_payload) != canonical_json_bytes(
        canonical_payload
    ):
        raise ForcedMovementCompileError(
            "compiled forced movement differs from canonical source derivation"
        )
    return value


def _bind_reviewed_api(
    consumer_specs: tuple[_ConsumerSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
) -> tuple[Any, Any, Any, Any, Any, Any]:
    """Close the public API over the immutable reviewed source inventory."""

    consumer_requirements_impl = _forced_movement_consumer_requirements
    provider_requirements_impl = _forced_movement_provider_requirements
    compile_rider_impl = _compile_forced_movement_rider
    compile_census_impl = _compile_forced_movement_census
    validate_compiled_impl = _validate_compiled_forced_movement
    compiled_payload_impl = _compiled_payload

    def forced_movement_consumer_requirements(
    ) -> tuple[RuleRequirement, ...]:
        """Return fresh copies of all thirteen reviewed requirements."""

        return consumer_requirements_impl(consumer_specs)

    def forced_movement_provider_requirements(
    ) -> tuple[RuleRequirement, ...]:
        """Return fresh copies of the complete reviewed provider inventory."""

        return provider_requirements_impl(provider_specs)

    def compile_forced_movement_rider(
        authority: SourceAuthorityAdapter,
        consumer_receipt: SourceReceipt,
    ) -> CompiledForcedMovementRider:
        """Compile one exact reviewed Core MC1 forced-movement rider."""

        return compile_rider_impl(
            authority,
            consumer_receipt,
            consumer_specs,
            provider_specs,
            compiled_payload_impl,
        )

    def compile_forced_movement_census(
        authority: SourceAuthorityAdapter,
    ) -> tuple[CompiledForcedMovementRider, ...]:
        """Compile the complete reviewed thirteen-carrier census."""

        return compile_census_impl(
            authority,
            consumer_specs,
            provider_specs,
            compiled_payload_impl,
        )

    def validate_compiled_forced_movement(
        authority: SourceAuthorityAdapter,
        value: CompiledForcedMovementRider,
    ) -> CompiledForcedMovementRider:
        """Authenticate and canonically rederive every compiled field."""

        return validate_compiled_impl(
            authority,
            value,
            consumer_specs,
            provider_specs,
            compiled_payload_impl,
        )

    def compiled_as_serialized(
        value: CompiledForcedMovementRider,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        validate_compiled_impl(
            authority,
            value,
            consumer_specs,
            provider_specs,
            compiled_payload_impl,
        )
        return compiled_payload_impl(value)

    return (
        forced_movement_consumer_requirements,
        forced_movement_provider_requirements,
        compile_forced_movement_rider,
        compile_forced_movement_census,
        validate_compiled_forced_movement,
        compiled_as_serialized,
    )


(
    forced_movement_consumer_requirements,
    forced_movement_provider_requirements,
    compile_forced_movement_rider,
    compile_forced_movement_census,
    validate_compiled_forced_movement,
    _compiled_as_serialized,
) = _bind_reviewed_api(_CONSUMER_SPECS, _PROVIDER_SPECS)
CompiledForcedMovementRider.as_serialized = _compiled_as_serialized


__all__ = [
    "CONSUMER_CENSUS_COUNT",
    "CompiledForcedMovementRider",
    "DeferredForcedMovementDependency",
    "FAMILY_ID",
    "ForcedMovementCompileError",
    "ForcedMovementMode",
    "MAX_FORCED_MOVEMENT_FEET",
    "MECHANIC_TYPE",
    "MONSTER_CORE_GLOSSARY_LOCATOR",
    "MONSTER_CORE_SOURCE_ID",
    "PLAYER_CORE_SOURCE_ID",
    "compile_forced_movement_census",
    "compile_forced_movement_rider",
    "forced_movement_consumer_requirements",
    "forced_movement_provider_requirements",
    "validate_compiled_forced_movement",
]

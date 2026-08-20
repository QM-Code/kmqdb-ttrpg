"""Compile the definitive Core MC1 equipment binding census.

This family is compile/link-only.  Its public entry point accepts only the
exact server-owned :class:`SourceAuthorityAdapter`, the ordered 445 stable
Monster Core creature selections, and the reviewed provider rules issued by
that same adapter.  It derives every Items carrier and occurrence from those
authenticated source blocks and links only to hash-pinned source contracts.

The definitive 445-creature result remains compile/link-only: it does not
mutate creature definitions, select a loadout, register a mechanics family,
or overclaim its historical gate count.  A separate closed projection exposes
the exact bindings reviewed for the facade-visible equipment slice to
``equipment.py``.  Noncanonical entries in that slice remain typed deferrals,
and structural Strike disagreements still fail closed after item binding.
"""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
from enum import Enum
import hashlib
import html
import json
import math
import re
from types import MappingProxyType
from typing import Any, Callable, final
import zlib

from ...source_content import MAX_RAW_BYTES, MAX_RAW_DEPTH, MAX_RAW_NODES
from .contracts import RawSourceArray, RawSourceMember, RawSourceObject
from .source_authority import (
    AUTHORITY_RULESET,
    RawIndexStep,
    RawMemberStep,
    RuleRequirement,
    SourceAddress,
    SourceAuthorityAdapter,
    SourceReceipt,
    TextSpan,
    VerifiedRuleReceipt,
    VerifiedSourceCarrier,
    VerifiedSourceSelection,
)


FAMILY_ID = "equipment-bindings"
COMPILER_ID = "core-mc1-equipment-authority-beta"
REGISTRY_STATUS = "compile-link-only"
MONSTER_CORE_SOURCE_ID = "core-mc1"
MAX_SOURCE_QUANTITY = (1 << 63) - 1

EXPECTED_CACHE_SHA256 = (
    "a10da28907027b1e8099d0b3b5bf2f6bf4fa5a24c0377648040a62c5618f5e3f"
)
EXPECTED_AUTHORITY_DIGEST = (
    "5a14dc342c4a09230a7af07e4ab81e0bdbf8e7864e322e4e3450203aef132dc8"
)
EXPECTED_PRIVATE_REVIEW_SHA256 = (
    "176a13a4960f8b2c9db5eda84d6337b78e1b82a4c13171ba4bdf5d3e6afe275b"
)
EXPECTED_REVIEWED_PACKET_SHA256 = (
    "5acd9547638209cca00ef5879456ca746fd4e5baf195b122520f8d38d0d9ca8e"
)
EXPECTED_REVIEW_DIGEST = (
    "081930d001360eb997c1e9c37829411de5e7c08f3f41fca5938b73977a8ca809"
)
EXPECTED_COMPILED_CORPUS_SHA256 = (
    "5a2f5731a59a61f92738b0d3155a1578c7ea1bdce068004f4cbacbb0ceb5db8c"
)
EXPECTED_RUNTIME_BINDING_SHA256 = (
    "8b978eb2f37f5e342c31408bc3db76b2f0d360e8576464872b71006eee158ec0"
)

EXPECTED_COUNTS = MappingProxyType(
    {
        "stableCreatures": 445,
        "equipmentCarriers": 148,
        "occurrences": 318,
        "components": 363,
        "modifiers": 85,
        "canonicalOccurrences": 284,
        "deferredOccurrences": 34,
        "equipmentTitleMismatches": 19,
        "sourceContracts": 140,
        "providerTargets": 28,
        "gateBlockers": 19,
        "gatesUnlocked": 0,
        "groupedTargets": 1,
    }
)
EXPECTED_RUNTIME_BINDING_COUNTS = MappingProxyType(
    {
        "entries": 73,
        "canonicalEntries": 68,
        "deferredEntries": 5,
    }
)
EXPECTED_SOURCE_SCOPE = tuple(
    sorted(("core-gmc", "core-mc1", "core-pc1"))
)
EXPECTED_FIELD_SHAPES = MappingProxyType({"list": 118, "string": 30})
EXPECTED_DEFERRAL_COUNTS = MappingProxyType(
    {
        "ambiguous-runtime-selection": 1,
        "catalog-bundle-unit-mismatch": 1,
        "compound-component-unbound": 1,
        "dynamic-contents-not-catalogued": 2,
        "missing-material-grade": 1,
        "missing-required-variant": 2,
        "near-miss-not-bound": 7,
        "source-local-no-canonical-catalog": 14,
        "unbound": 4,
        "unsupported-modifier": 1,
    }
)

# This is the exact facade-visible integration slice reviewed against the
# definitive corpus.  Names are the normalized inventory entry names emitted
# by source.py, not fallback aliases.  Each canonical tuple contains:
#
#   source name, contract id, binding status, exact matching Strike names,
#   modifiers, and an optional supplying-ammunition contract.
#
# The five deferred names are kept in the same closed registry so the runtime
# can surface their reviewed reason kind instead of accidentally treating a
# near miss as a catalog row.
_RUNTIME_CANONICAL_ENTRY_SPECS = (
    (
        "+1 <i>striking warhammer</i>",
        "core-pc1:weapon:warhammer",
        "resolved-exact",
        ("warhammer",),
        (
            (
                "potency",
                1,
                "core-gmc:rune:weapon-potency",
                "+1 weapon potency",
            ),
            (
                "striking",
                "standard",
                "core-gmc:rune:striking",
                "striking",
            ),
        ),
        None,
    ),
    (
        "+1 composite shortbow",
        "core-pc1:weapon:composite-shortbow",
        "resolved-exact",
        ("composite shortbow",),
        (
            (
                "potency",
                1,
                "core-gmc:rune:weapon-potency",
                "+1 weapon potency",
            ),
        ),
        "core-pc1:ammunition:10-arrows",
    ),
    (
        "+1 glaive",
        "core-pc1:weapon:glaive",
        "resolved-exact",
        ("glaive",),
        (
            (
                "potency",
                1,
                "core-gmc:rune:weapon-potency",
                "+1 weapon potency",
            ),
        ),
        None,
    ),
    (
        "+1 scythe",
        "core-pc1:weapon:scythe",
        "resolved-exact",
        ("scythe",),
        (
            (
                "potency",
                1,
                "core-gmc:rune:weapon-potency",
                "+1 weapon potency",
            ),
        ),
        None,
    ),
    (
        "+1 striking battle axe",
        "core-pc1:weapon:battle-axe",
        "resolved-exact",
        ("battle axe",),
        (
            (
                "potency",
                1,
                "core-gmc:rune:weapon-potency",
                "+1 weapon potency",
            ),
            (
                "striking",
                "standard",
                "core-gmc:rune:striking",
                "striking",
            ),
        ),
        None,
    ),
    (
        "+1 striking greatclub",
        "core-pc1:weapon:greatclub",
        "resolved-exact",
        ("greatclub",),
        (
            (
                "potency",
                1,
                "core-gmc:rune:weapon-potency",
                "+1 weapon potency",
            ),
            (
                "striking",
                "standard",
                "core-gmc:rune:striking",
                "striking",
            ),
        ),
        None,
    ),
    (
        "+1 striking ranseur",
        "core-pc1:weapon:ranseur",
        "resolved-exact",
        ("ranseur",),
        (
            (
                "potency",
                1,
                "core-gmc:rune:weapon-potency",
                "+1 weapon potency",
            ),
            (
                "striking",
                "standard",
                "core-gmc:rune:striking",
                "striking",
            ),
        ),
        None,
    ),
    (
        "+1 striking scimitar",
        "core-pc1:weapon:scimitar",
        "resolved-exact",
        ("scimitar",),
        (
            (
                "potency",
                1,
                "core-gmc:rune:weapon-potency",
                "+1 weapon potency",
            ),
            (
                "striking",
                "standard",
                "core-gmc:rune:striking",
                "striking",
            ),
        ),
        None,
    ),
    (
        "+1 striking staff",
        "core-pc1:weapon:staff",
        "resolved-exact",
        ("staff",),
        (
            (
                "potency",
                1,
                "core-gmc:rune:weapon-potency",
                "+1 weapon potency",
            ),
            (
                "striking",
                "standard",
                "core-gmc:rune:striking",
                "striking",
            ),
        ),
        None,
    ),
    (
        "+2 striking bo staff",
        "core-pc1:weapon:bo-staff",
        "resolved-exact",
        ("bo staff",),
        (
            (
                "potency",
                2,
                "core-gmc:rune:weapon-potency",
                "+2 weapon potency",
            ),
            (
                "striking",
                "standard",
                "core-gmc:rune:striking",
                "striking",
            ),
        ),
        None,
    ),
    (
        "arrows",
        "core-pc1:ammunition:10-arrows",
        "resolved-reviewed-alias",
        (),
        (),
        None,
    ),
    (
        "bastard sword",
        "core-pc1:weapon:bastard-sword",
        "resolved-exact",
        ("bastard sword",),
        (),
        None,
    ),
    (
        "bolts",
        "core-pc1:ammunition:10-bolts",
        "resolved-reviewed-alias",
        (),
        (),
        None,
    ),
    (
        "breastplate",
        "core-pc1:armor:breastplate",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "bullets",
        "core-pc1:ammunition:10-sling-bullets",
        "resolved-reviewed-alias",
        (),
        (),
        None,
    ),
    (
        "chain mail",
        "core-pc1:armor:chain-mail",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "club",
        "core-pc1:weapon:club",
        "resolved-exact",
        ("club",),
        (),
        None,
    ),
    (
        "composite longbow",
        "core-pc1:weapon:composite-longbow",
        "resolved-exact",
        ("composite longbow",),
        (),
        "core-pc1:ammunition:10-arrows",
    ),
    (
        "composite shortbow",
        "core-pc1:weapon:composite-shortbow",
        "resolved-exact",
        ("composite shortbow",),
        (),
        "core-pc1:ammunition:10-arrows",
    ),
    (
        "crossbow",
        "core-pc1:weapon:crossbow",
        "resolved-exact",
        ("crossbow",),
        (),
        "core-pc1:ammunition:10-bolts",
    ),
    (
        "cytillesh toolkit (see sidebar on page 84)",
        "core-pc1:gear:healer-s-toolkit",
        "resolved-source-composite",
        (),
        (),
        None,
    ),
    (
        "dagger",
        "core-pc1:weapon:dagger",
        "resolved-exact",
        ("dagger",),
        (),
        None,
    ),
    (
        "dogslicer",
        "core-pc1:weapon:dogslicer",
        "resolved-exact",
        ("dogslicer",),
        (),
        None,
    ),
    (
        "falchion",
        "core-pc1:weapon:falchion",
        "resolved-exact",
        ("falchion",),
        (),
        None,
    ),
    (
        "flail",
        "core-pc1:weapon:flail",
        "resolved-exact",
        ("flail",),
        (),
        None,
    ),
    (
        "glaive",
        "core-pc1:weapon:glaive",
        "resolved-exact",
        ("glaive",),
        (),
        None,
    ),
    (
        "greataxe",
        "core-pc1:weapon:greataxe",
        "resolved-exact",
        ("greataxe",),
        (),
        None,
    ),
    (
        "greatclub",
        "core-pc1:weapon:greatclub",
        "resolved-exact",
        ("greatclub",),
        (),
        None,
    ),
    (
        "greatsword",
        "core-pc1:weapon:greatsword",
        "resolved-exact",
        ("greatsword",),
        (),
        None,
    ),
    (
        "half plate",
        "core-pc1:armor:half-plate-level-1",
        "resolved-reviewed-alias",
        (),
        (),
        None,
    ),
    (
        "halfling sling staff",
        "core-pc1:weapon:halfling-sling-staff",
        "resolved-exact",
        ("halfling sling staff",),
        (),
        None,
    ),
    (
        "hatchet",
        "core-pc1:weapon:hatchet",
        "resolved-exact",
        ("hatchet",),
        (),
        None,
    ),
    (
        "hand crossbow",
        "core-pc1:weapon:hand-crossbow",
        "resolved-exact",
        ("hand crossbow",),
        (),
        "core-pc1:ammunition:10-bolts",
    ),
    (
        "heavy crossbow",
        "core-pc1:weapon:heavy-crossbow",
        "resolved-exact",
        ("heavy crossbow",),
        (),
        "core-pc1:ammunition:10-bolts",
    ),
    (
        "hide armor",
        "core-pc1:armor:hide",
        "resolved-reviewed-alias",
        (),
        (),
        None,
    ),
    (
        "horsechopper",
        "core-pc1:weapon:horsechopper",
        "resolved-exact",
        ("horsechopper",),
        (),
        None,
    ),
    (
        "invisibility potion",
        "core-gmc:item:invisibility-potion",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "javelin",
        "core-pc1:weapon:javelin",
        "resolved-exact",
        ("javelin",),
        (),
        None,
    ),
    (
        "lance",
        "core-pc1:weapon:lance",
        "resolved-exact",
        ("lance",),
        (),
        None,
    ),
    (
        "leather armor",
        "core-pc1:armor:leather",
        "resolved-reviewed-alias",
        (),
        (),
        None,
    ),
    (
        "light hammer",
        "core-pc1:weapon:light-hammer",
        "resolved-exact",
        ("light hammer",),
        (),
        None,
    ),
    (
        "light pick",
        "core-pc1:weapon:light-pick",
        "resolved-exact",
        ("light pick",),
        (),
        None,
    ),
    (
        "longsword",
        "core-pc1:weapon:longsword",
        "resolved-exact",
        ("longsword",),
        (),
        None,
    ),
    (
        "musical instrument (handheld)",
        "core-pc1:gear:musical-instrument-handheld",
        "resolved-reviewed-variant",
        (),
        (),
        None,
    ),
    (
        "orc knuckle dagger",
        "core-pc1:weapon:orc-knuckle-dagger",
        "resolved-exact",
        ("orc knuckle dagger",),
        (),
        None,
    ),
    (
        "orc necksplitter",
        "core-pc1:weapon:orc-necksplitter",
        "resolved-exact",
        ("orc necksplitter",),
        (),
        None,
    ),
    (
        "pick",
        "core-pc1:weapon:pick",
        "resolved-exact",
        ("pick",),
        (),
        None,
    ),
    (
        "scale mail",
        "core-pc1:armor:scale-mail",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "scimitar",
        "core-pc1:weapon:scimitar",
        "resolved-exact",
        ("scimitar",),
        (),
        None,
    ),
    (
        "scythe",
        "core-pc1:weapon:scythe",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "shoddy breastplate",
        "core-pc1:armor:breastplate",
        "resolved-exact",
        (),
        (
            (
                "quality-shoddy",
                "shoddy",
                "core-pc1:rule:shoddy",
                None,
            ),
        ),
        None,
    ),
    (
        "shortbow",
        "core-pc1:weapon:shortbow",
        "resolved-exact",
        ("shortbow",),
        (),
        "core-pc1:ammunition:10-arrows",
    ),
    (
        "shortsword",
        "core-pc1:weapon:shortsword",
        "resolved-exact",
        ("shortsword",),
        (),
        None,
    ),
    (
        "sickle",
        "core-pc1:weapon:sickle",
        "resolved-exact",
        ("sickle",),
        (),
        None,
    ),
    (
        "sling",
        "core-pc1:weapon:sling",
        "resolved-exact",
        ("sling",),
        (),
        "core-pc1:ammunition:10-sling-bullets",
    ),
    (
        "spear",
        "core-pc1:weapon:spear",
        "resolved-exact",
        ("spear",),
        (),
        None,
    ),
    (
        "spider venom",
        "core-gmc:item:spider-venom",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "staff",
        "core-pc1:weapon:staff",
        "resolved-exact",
        ("staff",),
        (),
        None,
    ),
    (
        "steel shield (hardness 5, hp 20, bt 10)",
        "core-pc1:shield:steel-shield",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "sterling artisan’s toolkit",
        "core-pc1:gear:sterling-artisan-s-toolkit",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "studded leather armor",
        "core-pc1:armor:studded-leather",
        "resolved-reviewed-alias",
        (),
        (),
        None,
    ),
    (
        "thieves' toolkit",
        "core-pc1:gear:thieves-toolkit",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "torch",
        "core-pc1:gear:torch",
        "resolved-exact",
        ("torch",),
        (),
        None,
    ),
    (
        "trident",
        "core-pc1:weapon:trident",
        "resolved-exact",
        ("trident",),
        (),
        None,
    ),
    (
        "wakizashi",
        "core-pc1:weapon:wakizashi",
        "resolved-exact",
        ("wakizashi",),
        (),
        None,
    ),
    (
        "warhammer",
        "core-pc1:weapon:warhammer",
        "resolved-exact",
        ("warhammer",),
        (),
        None,
    ),
    (
        "wooden religious symbol",
        "core-pc1:gear:wooden-religious-symbol",
        "resolved-exact",
        (),
        (),
        None,
    ),
    (
        "wooden shield (hardness 3, hp 12, bt 6)",
        "core-pc1:shield:wooden-shield",
        "resolved-exact",
        (),
        (),
        None,
    ),
)
_RUNTIME_DEFERRED_ENTRY_SPECS = (
    (
        "defiled religious symbol of pharasma",
        "near-miss-not-bound",
        "near-miss-not-bound",
        (
            "deity/defilement qualifier does not select the printed wooden "
            "or silver variant"
        ),
    ),
    (
        "frying pan",
        "near-miss-not-bound",
        "near-miss-not-bound",
        "Player Core has Cookware, not an exact frying-pan row",
    ),
    (
        "religious symbol",
        "near-miss-not-bound",
        "near-miss-not-bound",
        "source omits the printed wooden/silver material variant",
    ),
    (
        "religious symbol of ydersius",
        "near-miss-not-bound",
        "near-miss-not-bound",
        (
            "deity qualifier does not select the printed wooden or silver "
            "variant"
        ),
    ),
    (
        "tengu feather fan (worth 0 gp)",
        "unbound",
        "unbound",
        "worth annotation is not a canonical item definition",
    ),
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BLOCK_ID_RE = re.compile(
    r"^core-mc1/(?P<section>[a-z0-9-]+)#creature-(?P<ordinal>\d{3})$"
)
_OCCURRENCE_ID_RE = re.compile(
    r"^(?P<block>core-mc1/[a-z0-9-]+#creature-\d{3})"
    r"#items-(?P<ordinal>\d{3})$"
)
_LOCATOR_RE = re.compile(r"^(?P<page>\d+)\.(?P<ordinal>\d+)$")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")

_RESOLVED_BINDING_STATUSES = frozenset(
    {
        "resolved-exact",
        "resolved-reviewed-alias",
        "resolved-reviewed-variant",
        "resolved-source-composite",
        "resolved-source-declared-alias",
    }
)
_SOURCE_LOCAL_BINDING_STATUSES = frozenset(
    {
        "source-local-authoritative-no-canonical-catalog",
        "source-local-statblock-only",
    }
)


class EquipmentBindingCompileError(ValueError):
    """The source-backed equipment corpus is malformed or incomplete."""


class EquipmentBindingAddressabilityError(EquipmentBindingCompileError):
    """A source selection differs from the reviewed stable address."""


class UnresolvedEquipmentReasonKind(str, Enum):
    """Finite reasons that keep an occurrence out of runtime."""

    AMBIGUOUS_RUNTIME_SELECTION = "ambiguous-runtime-selection"
    CATALOG_BUNDLE_UNIT_MISMATCH = "catalog-bundle-unit-mismatch"
    COMPOUND_COMPONENT_UNBOUND = "compound-component-unbound"
    DYNAMIC_CONTENTS_NOT_CATALOGUED = "dynamic-contents-not-catalogued"
    MISSING_MATERIAL_GRADE = "missing-material-grade"
    MISSING_REQUIRED_VARIANT = "missing-required-variant"
    NEAR_MISS_NOT_BOUND = "near-miss-not-bound"
    SOURCE_LOCAL_NO_CANONICAL_CATALOG = (
        "source-local-no-canonical-catalog"
    )
    UNBOUND = "unbound"
    UNSUPPORTED_MODIFIER = "unsupported-modifier"


@final
@dataclass(frozen=True, slots=True, init=False, eq=False)
class CompiledEquipmentBindingCorpus:
    """Opaque immutable projection of one exact authority-backed compile."""

    _authority: SourceAuthorityAdapter
    _anchor: VerifiedSourceSelection
    _payload: bytes
    _digest: str
    _project: Callable[[object, str], object]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "CompiledEquipmentBindingCorpus can only be constructed by "
            "compile_equipment_bindings"
        )

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError(
            "CompiledEquipmentBindingCorpus subclasses are not supported"
        )

    @property
    def digest(self) -> str:
        return self._project(self, "digest")  # type: ignore[return-value]

    @property
    def review_digest(self) -> str:
        return self._project(  # type: ignore[return-value]
            self,
            "review-digest",
        )

    @property
    def private_review_digest(self) -> str:
        return self._project(  # type: ignore[return-value]
            self,
            "private-review-digest",
        )

    @property
    def authority_digest(self) -> str:
        return self._project(  # type: ignore[return-value]
            self,
            "authority-digest",
        )

    @property
    def counts(self) -> MappingProxyType:
        return self._project(self, "counts")  # type: ignore[return-value]

    @property
    def creatures(self) -> tuple[MappingProxyType, ...]:
        return self._project(self, "creatures")  # type: ignore[return-value]

    @property
    def occurrences(self) -> tuple[MappingProxyType, ...]:
        return self._project(self, "occurrences")  # type: ignore[return-value]

    @property
    def occurrence_by_id(self) -> MappingProxyType:
        return self._project(  # type: ignore[return-value]
            self,
            "occurrence-by-id",
        )

    @property
    def canonical_occurrences(self) -> tuple[MappingProxyType, ...]:
        return self._project(  # type: ignore[return-value]
            self,
            "canonical-occurrences",
        )

    @property
    def unresolved_occurrences(self) -> tuple[MappingProxyType, ...]:
        return self._project(  # type: ignore[return-value]
            self,
            "unresolved-occurrences",
        )

    @property
    def source_contracts(self) -> MappingProxyType:
        return self._project(  # type: ignore[return-value]
            self,
            "source-contracts",
        )

    @property
    def gate_blockers(self) -> tuple[MappingProxyType, ...]:
        return self._project(  # type: ignore[return-value]
            self,
            "gate-blockers",
        )

    @property
    def gates_unlocked(self) -> int:
        return 0

    @property
    def runtime_ready(self) -> bool:
        return False

    @property
    def creature_sources(self) -> tuple[VerifiedSourceSelection, ...]:
        return self._project(  # type: ignore[return-value]
            self,
            "creature-sources",
        )

    @property
    def provider_rules(self) -> tuple[VerifiedRuleReceipt, ...]:
        return self._project(  # type: ignore[return-value]
            self,
            "provider-rules",
        )

    def as_serialized(self) -> dict[str, Any]:
        return self._project(self, "serialized")  # type: ignore[return-value]

    def __copy__(self) -> CompiledEquipmentBindingCorpus:
        raise TypeError("CompiledEquipmentBindingCorpus cannot be copied")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> CompiledEquipmentBindingCorpus:
        raise TypeError(
            "CompiledEquipmentBindingCorpus cannot be deep-copied"
        )

    def __reduce__(self) -> object:
        raise TypeError("CompiledEquipmentBindingCorpus cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CompiledEquipmentBindingCorpus cannot be pickled")


_PRIVATE_REVIEW_B85 = b"""c-ri}>vChuaW42Om_9!&9Shrazw|^*gtcW`K9+2awro#?LlcpenMFbk0z3fNt+qoa<~8Q^=1C?CH-c<}WPu=?V7Efi8w4tAtySyGYh`8r*E_gcoKI(?#pieL|LYwBp7T%VV0?J@{vBvVU{Y35nOHO@l{2Ygi!asGP^zoo!8lYl#^9223W7l&bgG_hefNuZ^9fwe&!>xDjm~(!kU2eQM`)cv2Pzw@AVO7<9h9V56)H7xOu?}=hUH)9l~ESBYHJ8nn{#?KL;eY;m;CPif4sx#jE83zD8DQ}UZCE5yp)fB{EPenv)PDezh~sp<@LRo8lBc$oVK2o3qfmTpk(ygn-Gl$6|B|HdW~{*T_TlYV@XvN%$k;$nJi|2i@Ds%e{KKzN0Qk$_w|0X;EVTXBbY3P$dkqBl8J{Oc{06_3C>|c^FK`gbuP~`xf+ju@vaST6RiIFFq*W<R?j?azX{QJim;f@+9SC9gOzV)(@*~l7uz}H&)>n~yxr9wmw)}lW5&g3I@!G3_WgYMB~u%^q1=4;1;P5~<$c_EKDqh=W@o(k{ndE&3;)ln(dC6a>TvbL`|VO}ZucY1+Iq<S{nuaq@{9WyZpN_S*>JvqT8Gm*tfLtpVc}x_!5?Sg<i)QqcEJ~gXEN*R!@taEG=cHE_fe*TPyfWiWAFZL^XTol+ih(}>FrI+zx?NSfBEA*uj3uE0guHA1G2%0+AApJTu~M|S<O1L<%-sLrII(+`x0&R+CjyT?YpPH%=Hp>yv)($<7hrAqp`@F;pMbF&=Fpx&p(6{;(_(;b}ZYN7w0ldTe8voI7_B}(5JLytK02ZvI{sH;c$+#>3DpE^$O;sAhy2Uj`f;fj!2~JvDA{hFn?P3db}jNX!>Xb<M;E?_@k`ZCx*)ord)mARpIJ~bV@3Gb-O!j_3nIhc0N3t0r6n9CWG~w$ZwaA)RF#CI@0Xbk-NIl`Aih63LL$Uq{&*B$Q7rYEnG|0)ld;*wS)@jvIWQru!w~jxKfqt$_x7RGLNJl^++~ngF%x|zW5p=C=FF(4mP8SsYXkILIz#L@P=lh%k!I@pvW31D(#WPgqje{=w+TuKkB)R)ggh3Sb(ig2DK}wl%qmQ7x^g^@j=8dKq#>|Cyqrmfy7#`&JyCgzud#AGlBE_l@4h3<6<;ljBtK9r;1p$r=<lRZ*0%5Cj1^|7t>iY%y@#I4__w}PHLUjx4SFR{#p-~YcbfY#aCi`rGgHa!G>B3x>5j*7uIlDX>qi($Sf;vYrqr|a<F8g5jWK;TXU+!jqU&1JomFaj@89)Mx}$eEXmkdMMTN7c(1Yn6DlhcL4HsHVv;A-kwp#|5-Fx*4vO^hS?qH^%i}Z*#;lAH<&i|wFxwKMyd!Ubvj<lxnV?)1Iqh-~)xz3>yfY{6R}k+@hX=%#u;PqGK92;iPhvxNT5RZUvEkbJA6zfSSHdoMv3rcy*(25vl&@&2wpBh0fVI{(dqFmNt;iyvii)eeY^$|XvATxc3;5IYSs&$b(AA|lU4+rZHqa?nfopW~n-$)4E%0V)u|>Nms+JP?;vkEG5lqU(*0K~S&-f6JlZ#-)PD8KJiGcv#dL?#2u$Yppzt<JLCuFJ!PD6t1Tyix)uC^Knt~|_t^Tli=H*$73``Oddg7!--xM9ETT6`t$6YZvRjv<hZC8JKdcocc7i>pS=K`m^jn;mZqhe+O{b+Kth%q;dlUUT2`J;~#k4@3!4_9kOQ%R0KsHgjT8-nK>-t)g0>TLo)GZItMdP*s(REPxlLT$%CD^$d^WJ%<I8xK~w-aa$~~644=EhGuKT3z5%NiOjQsNbX+8#2Qmfs>oP*HuEs=tz43)+oATf6rlZ50g4^ET8yu4h_bwDk+a2R@skCWz*tSP&Id7rD0*8{^*IGolrN$aD~Bv!Sn*n${}$GU=yN~J<Kzhi;U%${xhA6GieVB5RFf9rqM{WYNS-W-HWX9ZsvKew4h4nUph^kWmgsXo%;Q9gt?gz5nJkWTL}sTG)*>#m0qrA3Yh#lCdn->P?~1TS<HW93N@hs(2zH!aP3UQ=F#ixwi4j+~`>^ADfqE4_En~nB@aH3JOo`zC!F<KFT5X>`YOUJSZ*KQ-Yt<fe{Ju=bFqD55-K({vAHv1O)nv5ZJla8-GRNA~c$kCr4hR2w_IYv!vn2!flMUoHW^I#P#7OrX|Mw5rY_zKxKZeq{9n$~phhNHj82qxmhx@l0y+UVEWDIBrTFW{+L~(1Q<`!8MGo>04pjpfnCBif2<VEeX5s5_E1^w>HDBHZ+9+ctd#b`X{`T1}$osK_@4n<oVF}#@4sE(FvdJVYbz7F1g#k1*SUbotz`CmW4d_>$!_Ty#|2Y*;C;`{-u2s}vOBC1EBFDRZSiP;)rvv5I~P%x7tQNG5+5;IkCD#;e3ZQHUo@N}%K-%1Zu2xcF6A{y?{4c2R<+yID6Uk4yR!gzEx8NCojezjS>!S7b9cRxa6s$dgGt4h`?sg{GIjK!7<l(gZ9lmb&W;zW2Y-ntJZo2<q15)a<u(-E?MEj<XSFnI=zW!2Zg$KNi_;R0q?y>GgQ&K|C%><umT_b_>kk}Ap(m+W+lz-Coc%(?`^Vx1L%q@ppVaF!7YQDjqe;$|n6JhOP@u{<4CR&~SboM%PgF>h&ihhj_SpI==-8S@Qn`L88=WNF~4+mKn44Su~`k<ond%$AV3fwA9Afd)UV-ogXYOF2hk)3_Go^(OeBL{jNcM3EJ2v8W=7PIR71CY7QxaxsWWiI3*AKZ5k~{nBg3G(@;OmRd9UE6J_jGquO)lv<CcI$UPyo0hd)a`0oj=Dk?5f{TbX7?D~gWX@=G7SLF3`$*LS7PQ5RLiFAi-}GOL4q}EJz#KzlZQf)LnC7tfJR5!*O?WPgay(3huY;+d+T-*>>d{2*Scv-R^Z27E!he@#e<(4OL>4&(NN7WfHrci}f;#&I-d7P!6?5ALNv@I;*~Qv<h>0*%`A;|os=^~tbt$8-ZKL;E4PhoP`Ti7*Ytm)tWlOPM(0$Q?=x+k-omPV_?GDcVqwm%HuOAjm-P@_I=2vA&_m~*wBh=Z>%*!YGVp9KQEb(nVX#7?lG=D1(s=o~C@6!eEL~k-H3fXcAo-`YVKwdNE<b26U7Ofa%z8bHvI-+Df=b#FhK(QTJc_ULCCmMYDc*)-c@<zxWBKgaB`swUyG9;KSx)i`|!UOccdWykjir1tL)U)u^<5?=1D%JxO>oHo0)@Y}4V4q0Wq}xVQRzQm6zc~e0lNcAS8YNbTiCj++iPLc>0@nnGAa70j<`HLKp}KmO2MyoKgQjoA05OjjmKs27W*1rfDRJCQDaoc7D+XVJNKf4)XpJ!;niPTzBM>=RYD?s$cCg}&OmT8je?D#-Kt*nY`=tME!UMFxa*DzA6mQ@D(63N<nEofV$F#Jn5e_4xh25;?<TMx)#lotP*l{wPlF_JIniYe#DFq!80tK&v!_-n%o;<}Vux&d4@V?9#=8MZQEV#>5yFs>L)i&cTF4ecV^p`gXyBIW|p31Y2M=hDeO4$;`O>j0Oji&ABd!kw#rFJ%gwF;=COH8CGXK_@WR#deQXulTZbT{Pi97dDj1&qc$h`T}60k|I<-C#}k*74S1Vv)B|iT#mMHC!NSF+L1&DyT!YRK2SuVG&cLIOjcjQ!oZWUeSow;i=(mem<Hl`T@5g>qgv$@D)K$ePt0>66AJtI1+%P+A@T*7Q46|K}ksM>=!Bd5wR!*)fEdO|EiC<WSz4*9mw&YFURuDY&aj{c)B=$DC_qY^zJ6_fZ*S)C;0#VpZ|A0*qNdWjOj2i9@mz$)tZ=H#w@;(hmut`*@tRlirEyO+TL!!8VgrU!N*jKvYs5HB1fkKnJO0^F72Y>m_PD(XnGKHP2C5SzZbf}l5X&`<z)xv=dVj>nXjxTbIfAao6Oc0`3k5)j0#e<47o<VJf9eRFqs_4r&wK5semb_iie+02Z84>t~U^<dk}a{-G{(m3*Aiw>TdyoJu*<cR5bYLy%Gt?jzn)}R9IZLNenfs6=yH-WGkYtWl$w&vcW1I137a-2yAJyJ(ydK??Ky&;;s7u>hb8Z1r!=Uu<XF53<(5n#PYM%;$Bvr723?IDCfi{)lf`HC0G_KE>w3q=o+)!-f}%34X|sH4vhU~OZ3)l{|+H0CcLdVQccRH1l3#4n7j|7T$_6t3~ODYXw(u-AuPF8AO$+d7;DO>1GC9=xIxLIakfL#0knUf4mQJHhhg6#cEnVQ#@d|3O3GN3mG>_uR)%6-OvYDTvT;C6rj=qUA*-N*BhQF21bsSqxCD}?=*Pq@x(;0YZb^9<Hcn6qb)YU_@YSafYAIP@CJN8k1kr+1u~Y><*~B)4#Kwi%G#ny0aU@YWQ{w5MZjLbK?jY+8st&~c)absIAZv%#D`H%U(#zr;#stVEXDW(3xkw<=PU$Mvl_sMLChL_YRoPq5K?zLhgtXrLay*i$8UzmU9(Tw)k+&pVLhqaMA3KB|qtaSz_iD4o>U3@O4YkkO7wZdDt91mIT|i}uQ;KR8-!a?h#Uvv>AyqqHTrG9x0ha!kq&*;95f8@SjOE{x%M*f_bEvZchfIlz_Xd;LD57COD-B}#<>YLrR-8?nWRN%6%Kucrd=l_GW0<{%F`o0qXucTE_neh~r-#$oGO)Yv5XPNTtXH~S<R%bPyjdRj-Io5Z=7VecE--rYT;4&)PLWvs-jiX1T3Kwd;FVbYJ~?VzLb{YzUp7VWDm$^u3?W)y8?;i<F?_9{#QJ@7VCI~~aGD(sm^<hnkCqkjYlMpHu(3Qv2dSdTU`3h~h1F~FD7L!>G3l#rHE*jHHD|0qDWC@rv2xT|Wi}^+m5ZzSXnE*wGGENDma{gjob#A&!N%;x%l&ga9y;rJ2G{cpezuwD=dTAx!5xwx_l)=BJABpPi~*mk3!#;7w#!W?iz4kx@Rm~H?2xjiATUpqD&*`<V6cvzZE0+}vIWc(imKWBP%CN6$RWnoJcim4ms~~08X^j&R8v$gtc+{*BV0Tg*0`LFE?NPA&lhES+u_ywBP_S59uNN&<zP$sO5h&d<Kd+ug&cHf!B>%t94N`F4_UB7-d1MOvRIS}V2dD2m*~YK4K0%yYGQRV*qBW(dFa(p9%=DtIeCld@yKX|gP(adXq2x=5~iNiFfE39@~whA7}1%bs;FZ`P{ml|ybe@@!cfo$@=Ol33zk!i8d{Fn$v|Tc_~FsgVm<irP*@YZ7690u9cL94Xw%9DWp90A@!68rAe`?4sZ6C-S0F;Ns&#?@1hXvP93n-FrvrdX9*@g(+JS-{iVi63P`wsB#E!FzXcTD(jJ0agtyT-=qO-VOs<yov_9+&T4y{b4*dqZV+MFY|!lk~3)4{`nXUk(KFk6h~Fge^YyLYAz;H;+^tfzU6&RUO6n*|%y<>ZY{<XlrJDpymTNrkk?5@UVKKfq*MDp@%f$>q$hI`;K+G|S?A#2@)!^n6MFc*v}2|LXMtC5MiDfgGZ!9uD5O0+_m~qZm9X`4bD~Y{hR$Xj2Pr>zc%hH8qPRYhy4FPRBfz*NEqjRzI839dKAvyb=s()srwTvcV;zkWF%8k){N`+NiYhSuv{^utfli_^O61Ap|6CfQ<IBYB-%R;HT-7cru*vcyu<JUd?+w+5Pm72g+)W!FG<<=iP?a70ihp7L?1un?zP+RY{{bhuIcRg5(6^JC(LI9HV2MYh~bA$%t%oF^F!g7L?qd=iExb>naX-%m7$Q4%wR)?p#)3XVjjn*yl9@i^dew-D%LSg?BigL@;O7Y3zJT^n`W=QGM0Q-`yKc>XDVd+vvF{_c6UMSNLJvx50T$vMD6Doa)xjrn`Myb4%4F1i~xGFiQ%>Q;BS?sVRq)tui$di;9S)H3CbZ0zeiEvj*pMa<vu8CD)qUh${J7`;M+--*F8G@e+7E+`iC`P463YJ;3;>kq)*)Uk5rmVq9oMVCtw;2^exQI+vQcSaESP2cjq-K`Nl4)*RU@qs2K9mnArhSm1=vv6y~pTZG-{xJB24jz2Wg*M^P`!?R@|C)b35$JA<p<&wQX#Ze9}DZ;2s0u4%lAqJ-rTeS63!lFgM5Y-bx$J%u4hsSNg9(?@!%GP{k0O{CtR;*n#NUBxD2J1vVINkcYvCra+Xx+A%ZPbpV#*oBm0aLx9A|I(JeG&j^LCg0Gxs%K3?C}1HHrTJ)KB{w#Hn-ceMjv@J9!~4<ayI%1Pw2E|L-?xw<hz%ur$Fth&C@2usU;zl=|$-(QTqkynq9Z8!|$sP^tW5;L8Jcf-$J=s)pO3(dht3dBoz!6ldTC3wTel%)B$T-^Et2q5X3E2K0!4hVkFZx1#>=yk~bR&w%YhSU-Xqn-qLh|?wah)gRMh-HX}N=nn?r!qlpx1DDoc^3yT57S2Hc2Pc!IT*`$P3V40$Tk1|<%LSQQ}U$kcN^H0-Rmwk1cum^U(T+t3Tw0+n!Z~6?7NG$`tu<|NsXkGmx$Aplo$|bhL7`ev8Es-?IFc#dA%ACZ?*D+*sQrKH8#yoteq23q3+o9@1T_YT<2;V&9I>a4|AZtM-jj@`jtjIbC0<B_oYerw20AzNS#fJ=Nw9Swmr<ffngRz_v<W?o14=6m{3$`uQo3HZNA>72@^lVhjUc5~7AkL@F>~cY0ENM)|rq)n6S~lL1H<eY!k}zV{A`MRoY15%7xmx=wOmAtrur?iR$lknI>xiL>Ti~OyWmyjgJ?6+x>^Vg>SXH6*qhr=8SCueX&7qz1<|M{n%ScxKq`)?Y&Qj*k4YDQ4n|BjB!muF95ilusH79gl{7!|s<P_vP5*cSxGNMKEvifRNQREx9xSRME)%a5~)o={0^}^X%->%+GvL3koD3pUOWgqI)n~sE35n?VmEY^6zTE$kX(EI4B%c4&!y9hD3N*2M?+WL)Er)**GTp&~@g}STK2e+%zjk6`mYXaEUHqv6iQUX<{Tkdqrw9i%RpagTZmGuQgXGCcRZL(|j8U!ojTgolx=uS$kO)oB|^HD1)H=Uf7>8CEV-9g+1y$$`~n*PnJ*N!7Vky`=aV2s1oH#q44DP_yLXhq(&?Ea#X(j1{$K_WOLhJxayDwjh(NgU44r?bVuK-{4|42e4vym=^wo^ntS$ynt|iasV?ebC^Nu^}e%ti3h477S4|vGdhuP)pm-g`kWJa7s{|P3QAo0AAB{!S0&u%?C+(O1cKI=ENVR#D+qsSW6^tv;(Rb$%2SH(~gr@Z#b%=tt-_P?Zux>KA%!JuHU0L$eH-nYxE<&cGTB_PR*=yw%VFRx|Pf}r$XL)3q^pJO{j`6K_#{=9g!SxVJfOQxF-d(zS{ch@qG}RExrXg)?vSu=&Q~K1y5+(-h84Ms9<Yqt-yr>ifkx4Q}No1_AIIGIT(edb*Z6K0@(CyJ|1DGDBB_Gg4zz<Yl`>k=V+|dQ?oOBF~~5bDwy)ssj9J6knmpH;u0_z@d{8ZIVUz+N<|q(skoptic~wLzzBVU*+-rX<v*Rfr(aNZA#X)I*b?`_&%QQscU1TVqnwDb8dNT+w1eniD0%YYu~rK{%D7Mq>#S2uXrfUprX1$P)JiR$5d3)DAcR)}hG7{)Usd$Gh<iZzca46qq#tbP-@F*?NnWxpa(3dVg5XRAHp#TqxZK+GB4$%fwy06DQlgpJ8|Mn<7>a8xZ%!$ES6j;Es`cXITajGT^q}tVugTv09&1lqI0r!tyBe*y3}Uu{<(jN<HQSssKrmJp0w1!7$94uV#1<6EuGpx24yOdRQOnS6#q8>I_Mr=Mw<)`Tw<2D)N?Mb@d1==XED=*LlGY%Q^GWPD2t{Ncr6h9CRNxA&cbrxk9D_K!M8+tC!GOp<WI8DT_T>bx$M=D4{!&fhj%s^RRgRrkKDi3M<OnJy)jkl{mdqv=R@5~_XEJ9pO)fbtPG+^WU_7O*f;#Rjn!X|E!om1}TIr{#>Ut{DwbN0&?4*@#EV>rRQHAQja7M!1`cQ_PD5NaTr3qPJh|1Lxi_a>a5XR2nYO)w}m$ccT=|S2*T$8=|;B1FlW241&bVw$-Ld1rYD@t6(+}f^-0S~!|eb3e>0~8fFtC%%dMWO17rvx^UH6Ob?$Sp+|&^APGUZ!;vywU=xVy$Ow+bIJ1mrL|5KTRvr-pG#tD!0ZqN&ajnNR{PQq(H<V$9hUIn@lfwSjQv$Z~@qdw=YP$fY+!8yVP$!YSvR8yJDi&e*{HEYP4Fngd^LwrlRJO0MMgIJa0lt&Jv5TQ!yEGrqrBI4}s^?=?A9aIb2-yZ5P~4-jBr941?_qZ{C~i2xn-KY1S}hBd(%%Tr+y5lvmjYwghZY1y`(g$+K0FvVc-4YMCIe)^ti}oG~mqHxG7bx^Q<*_U4suM^cd!-AYa*U9L&H8kwyTS?6^uF_5NQRnZAt>q^efRhtqKc=Q4^?;xBS*m|>hcZs^;hKJ<!o*>>jioCVrK^Tfgm6XX<%sv5@sYI^C>U~n8T7!mW+bNr~(q0#<Oj1sXE9>m3;q7vSAG-0jChEr9n(ocxEp_0{vp5x$ASqRAEC8A?$p5goTEL47>&PgrZ1u&J>`V^E=61}~Lr^D&x9%hKH>kQ1_stxh&mEAfjL_01TX)t{feL0UoWY^DF0clj9clJOTnAqwtHKdEv_ie;$|>cvon4LQFuUlp->zx8;C4;+_K(eX>^f+ZZH^+VVug^hc5J+j3B5R{(Q<-dB32g@>n7}y%P|H;CUUS;;FR{B&S5O;*d^VrNqVsM>n+vWhgwgVB!p~C@hUlIz426a^*R*8sTPNstN|BEl&jAIFOhM@#~78es+~>srv<gTY)vp<{o8wpeh+;o2$xd~=Bs}XI$ZBwTi4d3?zoDr7BP@(endqKs6?P86epsc%0fY>M~GVMM5w*b1PL7$!gg}O7dR<EPH1?@v6$P0eGr_`0KcIFG99}X?aWnc9al<9WVH_%HAd3dYKefr5~x}wVvudp<SiH-1g>07iyN!c(z^>h@7svICh5c5hU)F>-JTjEt>cS_npyO!uL?z&1<zvXS?eMc&#}c+7$7PieM&*ZAR8`_A{RO-z02_N^I>xCHf0y^8u2$J={iDo-XI01#K+(o#j}l;#Ffo8HIFtrC2no2aif!bPfGle7+ngjqP+1&my?oo)7hNye0q7=w=H&yt_ylMN#FcNnCr^x&6IL=&`OGf;EDx#THKA+Ad3jC5$%iBxWLtwTE+jxmH_1e$l@s_)cpxQvY7cjn7bzFf!qJsQoVT**AcQKMIz%kXkBZI6&oi)O*<{Z&1#!XrIx8#Ks(RLipL?s(8g>zN8r;sHuC{4x~g=o$M<0DpH?JqUX=AT^<(F$X2^n}s)$iX&qW7c^AdR#eXLgeR~F|X1r;>uT#X{}6-1bolLFWRCY=ylQ}lssP4wnr*0Gyk*(FdV)mD!tI<3V*b7*Ywf+eiJ7#mGchA^^ttxQ!gs9S+TYh<)OF__JIQ8qgOWZy*TH{H|ux>OFq0vXpN7)EQ10tOV!wUYRmwSoY;wJk-X1YTIR(O6Y-xwuop*g1Uo0JA<}c1_cTv}>|AFVK2?&mw-ME@Ee8q71sY45C6Qp)<?M&|DPjVm)z+g-BIQt`w(G1Rcdwitv88`Y;=HA#F|21+z8Ho5xs3ib%G_xe~JvwTSH%wHAAy#oa_3bhR-hAH?lUA-Nc#f+wG<Puz+lCHAKz(8e(7%R1i>^kD2aYnrzo!|iI*Yc*AI0oY`3txc_I9*CiqN{zurZbuzlOaXHg57e7T1{oq7BUYL@r6AgPbauWtAh-M$T^HmU>FdlUe;(v@MA1x4V&(&i0u_bnTdXXrkfVsYENIg%Bvsov_!?_v0V!G~>NL0(UrRop9P)Zk*4&`#N8Lf^Y1Er8$bd+mWxa~E4mh;dvbMFOH>Dj+RpK339jVnQH%g2(&KA(L)6ta`=aVWPxB^damhTO!e#m_*dA_<M!e+Fp9#gcf(nn2Jfnd<PR5-d8Q%jMl1j@Er%R$-TLqUhSq5>su>?vWczfAOD#i4)m?UaO0JqlF}wP>R#(ikB7>U~f-c@?~OCRUe=t}c3I47!wE)&{(54P=rQxZ#N*ZGOppfwo<uUbJoK-n=&LsrgVDj0mo*bo7F=pi*>E#GJFP)f4ft1O+0@RDq({q+Dup#VAv15dC{<c<VjEuuIg9w{PYAg6`NwV4~<uiejj>HXfOL&YX;gY>JCi!KREMnqa-Mlyz0wdXTXwC`{&*insOp3I})zzx_u1gC1Kg$6}eV2$;nF^2Lj)M1)G@q4<O*2SpCE)!v{bO-Z$6%Ou*f74bbOfQ=@@Gq}R@PMqzM^}%hI^6ksDj?IK(HF=R%#-sp6bBVb^RH83+;HX$sDODS6&<1^o+Hg%iIZdGDFIP_rc30y*yj_jEfp+yxROiwiu0hbmvE&fs0~SVWF>5N(Csn*?N3r0@XdSatN?G5|VHt{6`RogslRAubF`Z3DVnB87!rvt8!rKkXH?K}R>@}M~b8g8)@<C@sU=+p#R2;jIszMuLs6e)g4Hp=r6&HcYX(Qe%o>Eb`$<+kU;louA<aTI!@b=HwWN&`Av?EorkjO4mRI-kgXB~<Q+PV-aLJ-HHV1<@^lt}wTz?s<@aa*IZHlseJ?S$zJhaV<a_+iWkw4J<@x(9&&GQ+`of<v27o??;lo@)2OS900b;#AS9gsjAqAgChVbYvBxh&f>S-nM*R?-hk4nmNbdq5?QEEKV3d%rD2I#iAdHw`hBDc#Hha7mw>Won;|f_8?|lvS2AC$et7$vHL2Q%wqBdfP&f+aY>o1^VtNl1p?=MO4_$~o9loLuHSttTU#9}*JW>-NXuU7V6&KY8d6b3)sU#=k0X=E7{Rc!#Uw^DPJ9a=y$UIwQn+LWlQ~~?Nw;f~9-RGtOZE1<)%R2r;fg9F*K8Fzz+AZKhOeA*E~PaaPazbey-g^7hK~j*LpI*FGc$BjP`ey)C(_mweL!0iy?vZ@B#{G>_ckgn@*#`PRN^$m96*dX46&(5bcV4;4Ou>b(y<g5jaYix=u>KwHHWUO-qr9Pg#85HL`H8<r5a||Y_nlg!HG?#i?-BSy*Lu#W>w|ZP!ij3v0AHJ{kN6{Qkb+d)|?c)F8knh*$uDDZ$f%?nEVi{)=4>ElrBl3%c->e_aL68qk_mGiKVZ7O=y)20F|uISw6bVj!z0+pBB^U;(R!V(x)xIpzH(Pig>Uge)Aq@M|x$f=-bhF6bDmWOpT$nnAC++>(0=64;d;3RnY-k3|RXNs7cov5WPR8Q+{(CU5q-n7<Op7Aa_mn_Jv&s+MKdRR}kaOi*{tRoGP_L@gm9$CrjBEkHrU{j47f{ON|tCVhtr?_9un5&x^i&`YlBt($++8A7>qDZb9^8tue$_`dL5)As4U>SHU_>@~gO*$$_>UYfv>uodk<Y6Z`B>>KNAie8giK7MP!Rf$aua7vh$bgEi&bhh0Z5Qr4l`=t_!SS;5`1c%^3tCd8y&h%tn$a&|$fm@$Y1)JV}HM-J*FVK<%64}sl^>=4+kDBnKpI`-^U6g#cB6419}@=^Q)(%RSv*2>pfDQA)|G5U;!to3c%D#WZHC>>8K$8wFI`Q_*X9|F8B;Q`Rw(!PE0btJ-pxC@{_kq*IfAS*s;QXv~sTEL~Ew`?OR+cHW#$JmZ@X{&q$lt1iAfp0onbRL%3q3MI%mh8<Rm+9H17nvrmsdM74wk97M1Z_4K<`glRRK13(v?$rA1cb4Qw;_&$3~z}eOn7Q&>psA6gQ^>G-^>vP(~*c-6-Tk`LP?oh-doA+Ych_rl8>!+C8`Xe^{Ny>CoV3S*0eJDTmg(ZEeUru6D2q4L)@084{uwtH(!R_^nfimrE>~_SjV<)Rls|~6iNs#pc1E{cvqE)#*u2#I<26R2WwQQClw(XwRE&DsBI{^fVLre^J%^vR$CNwl~_y$n?#{%t+?2b#d?d;T31TUZSMh`7Uh{lmlhDW0<CF!G{PxmUM^c6bfIib&;_zJ&6_WT+GVU2Em&eB(n>p%#Y<(I64qAjv_;}_^FKw<p%EyGvmmZ%6xY=vRTI={xdy!ln-4kE{L{B`pt-|1D`NDAR=63tLPhaCsfv$~Vmp@=jM!^|3B1U+m|_y!tQ8H(z}9*nK!uaS*r;{N#dGK@?tF``4{?ojupxc>c_AH^8s=pJNG_x~N6f)G+v?XB?-MF(5{ld-EKX&Ejv`uHYk<tI#wt4X^pJN3SChrKuX)FpqzB+{hx*OSzK&ep))>oZk$S;`Qn~nSDjVgU3kpN>zH-WnIH~9`6x1bop#TwuTvR=!BMaS4vkvK!_0vIZvDDi(;$p0xqxMb!6UF`X>~(9@5d(0}HpWOPd5a~a;!!I@&9HO9H8opLs$)kx4*Fp-s@w^*Em0@fwsdbl+}0u0Sg|+_uD1T+H5r8^IpbPrt!B?QAOvwDoHhni(k%vTd`jZRihXC2I;jwE3%3ptCVhz8rRsuQBOI&=-#q4QhmgxTipB(&1!%>P!fMExtig)cAZDI(R7JsxdB;&z?>HKU<h(|4YD+jJAty_8Ip$&a#=<SS9^Cz5Nji9qn+wn5MRe8jjg&pLehO8iPf&yPt&zRgCXu+Pm{`PIEhc~tUh9-&PLZqSNT5%tj>uv*BAKiUbX$@xyltu8zL3*Bd#9O=a~?{D;B%{ZpG9#-DABVx35AL+TEtw=OfKh;4Oe5ccOv16IVE@D6MPu`C(O^gPRr~P^}y}lcj(@}Z0o5O-P+R^O-0*SYYj@YrZS3MDFUqQvKV<b8)I^=F0_Uo){+Hs+E%N5JSo7<hII_1aUbBWiTVIH8*J#_zJxP9Cr-&yGOc-OMp2OBNSGEG(a~BoDPudm#VSYgMiDc_rbAmr!WgjBa$11vuZq7*)Cst6ryjoTu-?QbGq!b&G1WDZh2U#N5pTs5FwDW5=z{zUPz)lqJj^U!YC$v@+(`lMeAIO~a6P^YW-F4nk1*GhUg?2|ZE2^jk{8d^aZBn=&XR!1wnn;D83Yt*SAwmra4+U;GHR{!Ycks8PH=j)`s*FSWI7okjQ<7kYBu8u%JRQA$+bZjf)!p4v_ZI$xUvkP8$;V7Zg1d6n9W8!n>YI;?R@`-(PGTM9nCM6&A{iYQW<Bk;9m+3KdcDW-^~AYviy#gFa2yby}D%j!}7W2OSoK2X;fDiN&Xk_rZ;Y;752NFO+Sj`G20TgB(v2*{<!9><qgX8^CjMXoG~n}W^Dp7%l~rw&IJ6p9<gSSUtXOR7Ulmt!OD1vJz1L3WVHMK-r2&`b~szv1twEV4xDU-EI@IJ#b>nKs)vgp3Zz^8N(>>^B#SIya?L}pVq3^nf6MbZoV5#Y?qkq!JQ&Rflj&km<Ym%eF&%8*<zTz;@7wthK?QBS{`H){XPAp1c>nHdvZNnwiHBR_cPpW?e(2j1T}u!bf3WYq#Oj4$bt%qnF5a(rHXZyH&PMaazNG_FU=_8Tg&3`qMNFz%a83kw)VjzYoGk`YV#gZDs+LHtN1d$*CfXw{9e!Sn#v+c+WyEy+VYC?hY|cEG3%H8B{pn<IDRU2!`}tGWwd*R^i=KSfqKnB<2mjvKbGm2Ivk^;8`QRABvcU&KI}j-F%+XUp-;UaQBom=3OCbZca?;tLyp!zJkrw?N#&vKx77l#MqTZP0deOA?KbYQC`)MIk5Me)D6SkxW7sW|8;;qNz6cweEp{$Tftfi2AU}r)rebI*b<Z6)hRmB8zq?OxjwH>@@n+a~NmwWtr{ljE>!GmAIQa;?VP=S)tK*>6ct&V+8#bz<h<ddLI3zM6eY!0dt1Q*CgG&MWSw5%wdk0laCwKm1@6k)iXVrQ|U=>gZjUX+>K*J{mv5{<mr!<RW#qf&)vh#QJ(61QsEl){O5t0-#LE^x-mRkWH2PZmv6e2F>=z+V5N^&o6o#-qvLcb{j|yH~3g6->k+PCyO5RT0Egg0_ULY~X-O1|$u#aG8B}F4TxloK=&RqoYYNc{n_O%35tE*j=fWE%(Tk`n5>FmJBK4YsS0~+22gBJrc|muack(nFLd$QHz&ueGE*|+aNrdg9#-R(Gjkas9&9mQ{q2~p&K0@Y1QiNbGze9m^@|aZp^Z?ez}W1e?2W{E3p0TZ2!WMwbh7ftkFgBFb#?MVHAn0kh3tXPd=DbGpAImRYs&<m4$7EX<UvuAInlH)A18ob3MWCa^)_#ZI|mGc)}vs_5e-%bSj=(G$<!DR9dCa_MI^TCTQn&(F^{ffGZW_bO>Cm3z)>mhjgU%`fEKn8^h@1lWdILNp7xNhhg?l=hN|Y@Jq2UJ}_VIgPA<P70zt+8JrQzSEQD&XdosL^vuQv`2#UqR$>ho7D=ZI3f|DRV$sLa0Tsr0KAJv_JFn;1i9x6?u&oyDCl>z>CVSK-dgp8*6EueuvMXXhge(G%bJpa%hE{JemVjCoiA2uDY+dW5?x2~x$MPYX6FrylgPjwIhx-b5&31DcJFxeg(SM4mR>kQUv@Do2_|JX#^CCRO2@77lEY+Gd$0TY~3Cm_niM;U!L*$4tiFS3Sa1FK;-HJ#Pf_}Xgt}(GkE3~?~|Hk48ES1Y0D<vpnL6tXTxjNC97Rd&vWUytWCJ>3{TMIjJ_&H?lMcRo|&|0RjQ+PBJS4ifIC%aKMr`cIGpL(pewrW34FD_t0dtH8Ajo52G8C}sSCL$wBQwgRti?R$!d<8>d`eJiG*?TYn#dH((;ft?FTDP-Cg5#_5lvUfEWOvQ_m=ivgnb<KrYi|4HY{c_@4ubQx^|+?6#G2Dy7*O2wP*O6jo1M4?F_3%@qG83xLshe{C1%hf7U}icAmT6gFz3ICGC1F}Ml7zZa!Q1fEg|u8gMe9s66qukX6u7R<P&o>vM9o@BE@PD_dKa27(1Tbv8^uj6uV<P$;~i+$6Eb?CudiKpC$|+?p(1|`1vTV(DF)E=){T^6Jj#>*(cFm=L0o3yL?jQ?2DOiEQmE-{?h+-H9nJx2ESq0E2IigH6ney3Z+yr8mMR#OO~<;*^A|hT%1^A%?-CITCp{>r~+}JyceD5PeZs{Z}$uLKW?{7Hs4)OKZL7=m?fjd=i!V$j<^{oH^TG(@n7$X5Q|h3dt=e=VaD_6_#^M!t<aPfdcSeqzX6_3{@Z4$hDtR*eRqH2dgkS(#-q>kA98ws&slx3Ef!bv-Dl!I%RLCzuJ808m)lHjW8;5biLjEDTJ3=GYOViO@YXh?<QBH;zp-3yUyA?n;&Lnt)&RQR$!U8pv|QOAMbnOGwZ!MG-pX_~6xw$8LILCH*+1QSsO8Sg^2M~%;O(MqRd+A@$F{RFnk<-p-S!@vtJ4;vy?wd=zx#8$o6+JoQ=sY9V!NI7?)_qR#n<~>|JYax#_M74-itdh=j9XOhu^Q~`nBBgkL#yt{R#g4oG1V1dcFSc&&W*kf0^)>_EW10(;mFt`OcHK3$J#&*0{O%*;bodZCh|>J9YcIb~c^<<Bz+jegLNbtxYpu19tU7|G<A<T*nWpO}1ie@suK-NK8Hkor@t(E^6mnPj?y0TFjoBMS1z?vGv(=(doL{Vm%U1=>vF59I)B@78!4$rXkE0qd825^Wl0c;~oyXk7mtrXRBkDg4XsBzu&UmhIX)~{j2%ln)aF5@S#gTnk^eUHnwc+`2}09pZsp7yv2y?B!G9i&9<}v?qjw47^04rCgyc^%5$-Weuyo6Nx_+9wJ(&xp%HJhU<^)qVUe`jC2d7|L+g^;0^*vJ@J@}Qk=f+0%@%hg2OW?Kba&#<^8)<Stt-8Znz;eFx20t|nd)YO!$Vj*yTJFes|l|GH@uvRO^l!KLCH23WVLongHIfa75!jC|CcQocV^tO>5^nQ)A&kOK<_Zy1GhPEYqP4*&~t-Zvg`ZWooV;RcD`TVUc1tS+MeWJ4iZuNZV_cr!!pXF$g143$yBLYml9oN!$Ma>^Aezh3c*xNy5)Xo&PItaQ%@36<FoVWc)U2jI+9Ji+iv@Sj@)<m-+o>}HNJJFml0IgSABDW3dgXDCht7qakT&4Xnn{A;7o0cmW|i0g+~J?%#l?|Nn<f!TZGvf8;o!DURznsVlh{pO+@YabubvrE~d>wz9M-i!|^Isai3Xyd*GVamh;>?xVjuVxE}i4rte+X>#}#hV7JXv?KO07^V61*{;~e{YP=X-j`@)+)vo`y?Q+k@68dN?u}9~SO(?i$uOP}N_By2MK&xE6LQy^#V+6~=MG7^rHBlHywH|dol=L)~n4Ix=_ioJ-LNM25`TOhr-&x)NnW2C4LN640*<AGP1zvWZ?C~1ryD9uqrtlY>{%{lvQ~>e2#s3yRJh~LPkZT*pEc!Uw=qNZUF0qQvP%KKE`k;|GWaZ$fa>;)8*PmN9ot#8^F!Uwb`19bvz}L$NCetsN%r)nmHz}CxLxQQefH8q_SeyyLC~jTiO52x<n3B;c1U9vZO@-MMRoLa?V>HTG9ksnnFs&{#Z2M*7?T(l5+cFRAE&(+w@)5>Q@g(k>XS3ML;`qBS?Z%C^Z<jYWoKD6KDp!-uOWp1qidjEczTm-jQ*uc%m|tBA^YMHDgS9vrOoVg(X2nFm7?i8UU@{%d_-fwH)9mb8E;lu=cT$h#`?r%lg90<TwcW?=5`JF@z3o)(*Hy29TSm>J<>B&F+i1SN@^7!^i(m3aEIvvM-oJ0P+xTVPPA3fZxF|Qkdo^Fv--C<m?cE!rCexkm<n^j8Puy*Gv0nx{hlL;R;+uyAhX{lS=smFuDv~Who9L?olZ#Q2lWooaT2<&63sb@5qhhK_{ui|OcL|Qmwr8~0j5&go_#V*vZpl1ZI((t(uNB2`!*M%e;%d@3d^%g~{=6$0gt=FzEO%IYc~`@=JtHrM#h4fmHh{jx>G$o3Y!P|aP2Q>F4!fPrQRDS*!zIO+X3gr$Yn!J1{g;D9)4m{3@UgbC;R+qKqLUTb8${5CiUpIB{GCcLr5ZvNqO<4{IuvWiq18`vwq|&KwB6BdGV`$EbCt`yM^@c6bid5{ahoN5J^FcN7w);@%S4L4y!stt?XOQEX7r24MAR=Xu2v?&d##3Y<#x7zFLJiOZ{p}%>g9U0EH$P-%wRIF)7iz=?rAbXtd|w_VEBIw*2^jO%7jFC$kzj{2HV-M!MFSEm!R8RaR}oP%<n><-bJ5LU%>Ci1Ka@NjmthUF28#bc@6WcizYLFYK!uqDf|$6))wK9x7qG5_x*NHkp2$dJ8utlwEe3uh2BHvV_l}GYqk!GZijtca^4cBR2+p=vrR5UU{q+m{7gvgs6=9wv4pCQE2GW9`&Ly}ZMe)39gg`UkC*vHdpPZS>>ayScQ9HTzdEAb`0MYl|N7bTQUmkz8+^5Az#%MlfPlZg*>7RrtB&Q<U|I)%63=yn{EV#hU~IV^Z)48cL#yor(O9B(j;6L_G(<^(cELN(Av0)UAOKewTr4?aAUrNBJt4R}23d}K+_Ck~_qbx~5zp*~?Of$6xnSlk1d~_m_<e`#RR)s3<m-pTkO-Vs5JlCP*`xSZtrb%iz24HioNu+SnY4DyHDIi{mG^0t#tKH2shFcgk{9Q20kdNzec^06pWp9xU5~iO+qxd~%ud$L3%!tUwYliYiK)kVRD!GbO90ArlVLl8_wMcx@J+wt&OL@35WYKR{E)-5EF<?=ho_w-+Z-C~Lc~tAX!ilW+!5Hj0Ean0hk7{Iz+Xo4mhGnwh~)LYtfy=SY^?CX+Mm7_#e;Kbhuj7ijOVbNM6_iC#h4eoyAiOQc(6h5!QubAgyw_i5124hPPrK0YS337NY%ipS)Agbi6LsBaMo6<;zP=eTrs!4kh+lZPck}>E9I{dbN^1jo<3-|b^_L;USKC+=SnY_+Ph(`Qxx@25g<>=WxSWc_5`ufh6oB{HYj`p%GwZgVbgp(*9uuFjn0>l9D+(jt<GFhI){*3_4N807;K%|E7y^ES5=_*W;5=L*`LtcMh(`Zo;#uO)}`Kd8gD=R&5_`5_T;u#V`4F!l7rCnNUoWLB{C6+dhv|jM#Z90N~$(nMM<Ypqs>usq&pLN*XO?XVE#X0_JJ3p$76nHYi%>{-P>uaZU5VwYJan9GCWfn2+p9$70-IZ6|1*>1H!AX4z%j-fgZux89&BY+pO~L&gy2}Z)~O>xZH=?PIsZ^A=?Q9LKK_Gu*=LkS_95i8<>GP1PI(33lOx{D#17tvDVhKT^qKV>eB*t-7vq`c3Qu^y>fl~`+lqGSDPWvE6{28GB0B<T|@hAWvAc8vQIIO?&YC9=20u+Q-OmAQ$mc%ryRuD5a%L+0xnD`sg|nftgV?XyH-xmA)+lVE9_4{Iuhfo>H)}0yT=$>{rb=u|JA5FcWC7fuEsFixRz~b+d}%?7(VlC@S|L9@KgKlXa46aQCQ((G`<liT`$JQ{cn!_@T0uTtNF&G9j<nI_h(9Oc7)qjuzbd4j@x>Bcv=Tl-0H!n^O5}3MsL&NR=hYLw7i^^58j;Q_OwSb?N$r-RcjIGm(ZAxe}y|WYi|6oqPbX?rT-#?@f<JsFcb4$5wgd`42;%9ZwzzF1<`5kDH#mbiWI?=TB*%s#p|*fNUNHaHW7T=Gi$?+t%jeFDAamg3?GhG-yXJKDL1SR@TKC`=XYG~WmNRdE1#&Q?#~I@#Dw?YWb^Yu89__p{Ru&vxo_kH?Z&8IE*<Eg$oR=;1Knn}P3OX+WiZ?&+8%O=vJ+=Ng0Y2EEmgdGtr7;0RotOyea>EIat@u-%CHx?Y(NLhNxQ0?c@47o`$6^-j({D;75YeA@fuIFAJ;;;?vL8tK=rP6sn3i5#f|H{j3u%IxVIH8IE=H*DJK3L%>R2l6zf%qEH5ImfufYHNRF}s<-v$PEX66&kx_dWY>rm6WRBSaX5~{vbx4q70Y~Ea8C;I;(|_CF_w)PjH$$G6-DkU(`F^PCutQZNc`dWSdMOV`z1RdRE=Kbfz8bC<gNEB9MQ1ah-B875<gEd_L5gks>+^iDzQcB$a(Xcm7iB#CH2lS2lMW{zr?bKN=<Iwo&(7(mwWPRzli(&}Y*y~ywrvGP5MIx{zL%X|lb`ndvc0{#eqQz|yh|2tmgN0v{BU==o8i5Omix}&-qDx!i_>GvNxw*D+<d!DWn6vnfZV+$(H_iWbU7MSPP6gZSOreLaK)-Zmf0DF*1C!{lko{uVYFhDRnyASMs@ej<Ah<hT<YV9-5n`(aW!9^1)j`BIJ6qmgP%2x+oaR-c);eJ?F?wgiwE<ovooH{`)Y5Fro1Yv&1=y!{ybPonPuc|H*UN$PwPhd`SM1>_4YxBGTU&qJ$D=-{c$u~TutZGK^<Q$Uh#fruOPf@#U46RdN<9r*n7Tr{l5=3x3ek4F1$FRK@}!nMTDmxdD70-uFJJA@Ax^7s~&hiUq#~Vaq}XVq&TBdMl&)giWbNxUtDrgJiQo{jZ`B9Os)TXFj>cFQzji9mM6M-H}BSbKT`j_M&{w(-tK}fTK3c%Jm1m7{12YqQq?C6+CZ#cSIV_yiq#sfm2-?vlL{>M21IRgf#O4kT-jD;?^D*tFgMH-%#B?eV{I31HOyMAZ0wQ2YV&b$&hYW`V5`t?%=MC%#5v3^U#}r?KPNrfmUz6?@Z`7mm&0SD`<P~r#$=Uqw#j%X8IywIB0|cMeMCYPi6K+5WFax3F-lPhCfQPys_4Q|HRktndf&_6KS5)@>Y94rk3!zT?+>Z;uUYuMOwZ2biH?)G|KJ|x{=LgPvIN$H2g@-nLEtxA>K)Vno-NL2satU4uD*qxP8mIsyPB`7HIG*;u@GzH>Ud=g?t<ZiY0+G$X0I)(O2(QJtg-=|7Y&cqihb-eLv>19QfM$3t4oyMeAJpPzXG;dtM!{pyoYyg4%)BUe|z(NJ*#rR_~KeGquzI~`{oq<6Bte(hvD{E(WMyUeFdv9hzF|LK?L-c99K%#)S6YIoK!XJlx-*a8Ni~+<g`jjzaEC$Eb6{goAuB46v`jpZ+jdmuV&{eFH|CbdBtxguW|Xf!y;_N_vJU<9(GWk<8qS0dXoM5jyHzg&U?K5<CF6rbyxo5jq83p8IVs9$mTc#+3aiTmy6gqIVi}g0{av+Czn7c3YtuDVh(X}o>}ap3g}`Gfi1GwWN)fJvOs=H<;qoW?|oHMR=?g;F=aL2nX9E-U*v@<rL+sa!LC@#W&9I-WZ|S2aU~wy!$&ked8*MdQc1;Gwv?-`F<a)0NJa}sMR1uD`;ZeB&&nHYMF;_34<lVK>mFXZ9<ZOC{>OIAp&Vr&#ZiB{ah;c8s?9ZDA78Czep$BC$6>2|hc2tnV8|C8y;CSIgNqsqa!x>$G~`lIQL*BiLp9lGB|rI$(F&7Q{R-IX=t=r_nTa>k=dS}^U*_@m<@i5K0PN1Y{Wf~n9l~MeI2^Xe0(3++8YZiB2)Sf&!Yxozo)cjVsis5(04~%_9&L@DOl!*`Y$hyt>=@WnI@m3s*83Q1_47S0`Fg~2A9cCD$_u&V%PYRUmUZiee17Zi!ITQ^gE1<2C#GBsP8*9x7xKo1=&FJQP+i8<c8s0F9IZG{9Ad1Iol;NQ9WGaAg<*E2xK@GYq|)$#tg73?_A}KlS0e{6lU-HrxZ2Aw+084zIcB@Pu<I7;JGSs~nC}iSKf?7YPSsq%MNDLirRYVIQ5F>y3fiDFfz2|kIKT=4<<HReK&^0LeLc+g-SzrLU9Tr`mp%@6y+#l0INbF;wcyQqR8L|Ya~#GouQ0jb%lkb%bb;qEnhfXXquD)&sc#P2TUX%6Hf*pN_RP`tFRt~bS>d|e+z3C6`8iFphl^`~&Xy7dE<uaaqjC}rQL+tW#0(4aC9CQ+cp?WOLD1G?^jO(gvC>`v_P>`K{N~FIK9ZI6aaidE%MN}WR$4FS{s7(P_j@9An<0m?l6hQ+Zuc@T6r<ZB?M*p0eVk;D!%6!LvewGYG8Zq7zt~x#jbdc$YgPt8i@AovN40PTNJu&;6RfM$ilRFzPvRu`VRSa>DCH@>)iSpQ#(%qR3i0{JEpx4V?A<r_od@-IPfm``&KJWAxVQb)?wBu_@(!n{z+yTX)T_x7mGc422g^AI>p6BjqusB+Waf4KNManr?8rXS@+Mz6G`N^f-eO2_wUCc0&ii<K^Da0)SV18(D(}4!c12)FPP8P%P@G0j3SupkDkxv0bvBxmk*RpGG&7-5^rEc&-QN6eZ$5#O^l>=p1<lRgo@#g8cdyxb-9n366|9zgIlP>X=F`cZR$3c`AF+wn12J`)&iPB8THowod$Z5qL~H%%U$N1`H`xU1E|fob&QC*BH7D|gwL&rsF62mF3|kwtcJjN)jvatk5Ga}AY7W{lw7^R~vYz`MSNX2zzG54PdpYQ|^qV<#{T9AK{Wh0HTWs?^zU#P0ap=R%#jQ;VJtRw_wUjVujEcbI6k0x_jjq%hGFZx}Y^u3xRaK%Cl<__v+m|!nH=Mt3I6utu$5mqwmZSNao6ARHlFhEb^@8r-8Q2|j&+fqPuxH*OxP7S?+9kMwzBjc~@My*|$6>5}2O?QJg_%;M$hGy3_rgz1nw-tLW=ql45(9`=Rg_lAwVv};Ln;U%Jdv>$bvpj=h9ZgfyNC64w%g9y@9<|nVpRT1Y(8YkRqu!tpyJk!+lW>Q+L@4yvjI(N9VMI#DJn0fTUDB>ld-K3a;lsFUJoyAmvb*S?TpyZPycW|=y_unXE!hOGCZ}5xwqA;yO*u>aoB2a@m}w>!c@^)s||qFiM=Wru~JP%*%|`oQdJcz(N<eX+$ACL!TCf_D)xl}OSqaHr6uJ#!<c8o`EW6nB^ce4TzJRG2U=CGDE?|bxTbjKhH`gb@T;|Ze5c!NOC#sd@W%OcTDR3Ij;2TM0MLV{t5gx#iVhLfYY1{1Ik=*YcrpP!5^J(HXNaO(n1hU}Rm`~T$T=gpKT6E*>A=5^*@?$oS_N>xb6)HT*j-mNdD*bt-QaHbJJ{au^T+INJpJ(_cl)9J)?;`2IGn2Y<ze_30XbU+(iN8VV^pHhP7!<ODvP(|R8Za<B5FrQM45?)B^;h=p;w@qzSsBqUf=6`eXsBJz4|(wKHgL^#}UA<u%1`bN@wlZ)!Fw0d*Am@_Le|_PxI@1@LyaPr#Oy#aW@8Eb0Og4vCS(wXQ98Jvv}#6cn9#6J{n)`&9*5NT0K1NU9>)+(W)}qs2M=JioyH9Tr(vW9h5>zU~<GL3|5lOuZyp~*BAPx>I)sjQs!tZWnN#YA^eQv>E-<UrpotCm8Y}U&T_6AJZ(F6AI%uN1FjEQf?suW<*4knT-4!C8}$8~D>ujOXSHA7d`~a1r}E|HUWV<yMC2(lUw^o(Ovm?yxi&u^6y91A?+<Hj=Drcm+I;!KVXU32emg;|Lj|%vjzHeyLg*rPOi-D!@!~8*#ld2!k$^H5qn)?e)f596XzsZN04~7+8EQYj0)e~=XPuAe9#d!i>mveLZRB+n>(?u~9T~m);)UW@*EjPm1g{R|5OW+3*;m&<ITcKa;GK@yv#T~(F;dL3lPl!}mf8r6#c-)?SsQJIiBKGIqmON}=qGvv_cwCb9rA!rfG^R~;q2CxUeGJp)7;_2-GX%mx7~F;UoFwB>C9*J4fMl}lT{?L!aB)Oix8KRn8mmDF)OUO7STzdRgFs5oDw;wS{4d<7j!+k>#e`5qHk9fJ&8^9ao9w^K7B;M7t_g+j;1Wh=JK?|)*1U=C;G0T_cR;Yj2>K%e&$+;d#?CGZHT_O`W?aIzkZt@wOo1n=^mGQ`};vY^@@7GQ@x%2hF87)_Q`Iw?{TYdT=v`XtJ^-pMhM+v!9TSfhVM<dUt<&QJ2c5d_Ms~_6vu^A0<i;a@F_ZHRdCUguTe}!(gmVbVj@<|>=herg4Pymh)+{|x9`?HVWSgA7o&SS3Ga-!XS?%y&@&&#ym_G)(P^i4a_qsBXoRczVuS<1)^vFSVI{RbO|O=q8EhB%ySVyl;_A`&xp`~%v)+bvcLwj?%Fg$FlJg5u^pN0$90S;hu^N$~##QZ#u1H3KOHO;^bt0`?K`)L%^?-~uMipD#BW2Um1m|peq#d{KEl9t$7NqAwar}MjFCh7vn~(PK&*RJ5u8&IL=f!9|=K1;d?BCwXwqN5=;XMu-uTeezJP=fjCM<O4Jm*#w_x4Ql`>Nn>9fxCyfX$M=p|gqy@S{EgKkkWu5dtOSj2QP-EPG)$ZMZ7O+8OpWWs{ZGzKA=J;wl;6_-Me`9H3ZyCHkzb=3^2_ZVkI9f8@sNdG_>?JFfOZ*(0}M_-&k(db7zR=6mwU!$GcY0c?&SfcI>PXBUf!B2NpcS}Kd*pb`cz!WcrdK4-5pIfu?^B_cT{Yd{CgNjs6#=4%Sz=ESX!H!aR#cJ_H+VaMAg9iJRqxvOI1<|Ym+*tmM<cb@ZpwyKN=AkiKHiFR)%BvnEP#`{XCco2^ji((yJP1XTGiIxeMWu|H*adX=t>SVLcxqN-sc4<`4rk6bQYFL@?F{p2idcc@&qX$3pYS4!N{C+9Dj;I{TE@)T&+9t1gS%AAE0NmXTa4P~eF^b_@HAD;Ih(;qKRp-K*bRi4@6Z+(;e4R9rZGmsEK}-+G^_T$H-+j;TzURx=$+_)kT*|NVO=~~+Y%!q+la-iCiK10f;S9ATsNg~%7gco{T#W(A6t=baRz^2t_Tqg~^%-qWkY0{2zx$xyebDbd==TE*Pp`spxFFU?5X5_efl50^Rr%nf823usY@j%=s)%4QjRG>{0+6E)Rs2yKD6(zc>MLi*%6v^h{8GNCf1|$W6A)>RfXF@35sL%_7`<5O-nmqA5lbC1`Y7f=%7&7%R#lT~s}EyXIWWaU?HD}-|Funn?>_0P^GTlobbAD#+f(;V@6X3tF6MBxnEP|GZjQPqFKhSRJbN{Y|DU~g-EkdB(ga_Hs6SPO$w2x2lKrbQd%J6AtFVR28Z;J*`eE*FenNE=Qmmvn*{6X9<~8Q^=1JCEcPT_MBvA~7g8AcQh&0kkr+wyT=5~2KSVu)E_BimqvScp6n`!}XHNK!MJkvruu8dDvSTHD@(8|dWrDKZ65IyH0(U<@l65}E$o|PzG(#+b#o9KN(y)US9Ur@W%%wF;IM{@dzzS2@(Y3Yr<Us|nIR*xEfdnJ_;3GQJ#S)GAyGMzmS%LCLqz;=lCb3E4o`e}#kx-bf_#=7gw&1J1vI+$qMN{IdA;JL*mW1pWIvzlXJ;%KAKXfvr}OeX8NaZyBCO<WG7)>#b@dB}k?pM^%u$q2|S1orOSzg#rt(^$**%d_=M#=kEJuFLAbZU*UQ!C3LueXSSgK!~>ip_&B*0SOU|TZR#^#8yWiWcKv`$gJ}KK5_^qgoIq70}%xT!dP%xI&E$RLYoP#LD7bw9!P&%(_9xzvz>9efzxWt9#JQHsA~~b<D$+%1Rnx75+Z3?5|U;qx#Tqq+5{l2ODAuD3?6B6jsVW4s8sN@&Se3uBI*K5hE#*n?s$4Mn{t<^9$A0hp}Q`+o?eaB4Z^m^y*rfcPU^2G_f`5B*_5XUf<}*q45XHFCz+SZD8>W#ib)Yvib>}zNF-P$At*07CM$(-f|WcAA*~DSGC}YNPtSwN9rfeneLv23>KwSN*VD3p@Bo800m>+@GoaBRg0a?V=Z)u*kmY~@229Q|<%3p|G+2~m9D46mj8PKE*umVSXPA@;zbcC6UiIlS4u@ep{(5X1Y(vuEN8ctr7W}g!E1^Gs8Nzp*R6o<0)i3K4zY9Ycef@nEV2af^`~%~T{=1x?jU$~noL>B4G@h;cfW2UGVQ+e+{S~2vI4pXCt>TSVt-VUX(O_CZH6M2Kfd5o2nv<38VdYr08mR($-1P^T?`TwI2Wg2cy3-WtA?a&wF4^iI*2+HMX0G4W$<HtF?!N)e2m8mp@%wMu#-;BgcpAhboU+?A?!6i0JUjcC^r~wxht~U2Jq(i|;iZ@|!YaiWod+F~Fz85zp;1PYX>EkbOfxO!aV<)#+ffJlJ&w<{$8nA(Alkvw4R(@9^s4X(qjpLwXS&<Nd;{TOh~IEH-@~l|)`s?NH7*N%HK#Aj|G#d2{cb)~C4Rqy${K=>YG7_2_7l~>{E9f5*HoL*P15SX1nG)mZC8)w>2cPc)_sU~o78SvlLVsoq;_YO!3vp@B5Y+^r&LOg0jDKPX*3>zBl7?%ASfHWjV8rg0NXkxW47!AT$_wB+ih%oFb!k2)lB%B2^h0;nik(zX|RT+t5NT56=?k4d|F4v0k7-R8OfNI5|c%Y!m*4}C#^9%Ar1E|OA$2bxFLE$%e2p)L*O>~kkBS`L*ihYA?g}+Zu3m7Nchth)pdo!aBrkuEWE#15T8mch`I{%+C{?!*sOU@J_nyHi2}?Sy|wcK+Ng2_%Y_dRwDI6cbYw)Wo#z*cg<oNkTWWOz!@Q%9^JB`wiuR2)=ZSu!kN<J=YpHJY-|y)e2MM~WNxvTbll1l-Rckw!*olnNC!DmWc)#M%CapX1D6I0HsVpNZmm_AL0IjshU9hBd3$Bo5pOw-jVm1oRax$C_VT5<b)AX?j=O3ptBor-v9P=6NP^~ibR=>AhM?_eyPh8uB^lGq^*4tMoSl_Cg{bl}Rk4fLW1eZ5}!E`zDpI@f4pKyhpHvy%6IPf;$P@{E9mzg0;R2mg|3_@`(P{mXV(Uo$MF*#96B9*Qt5@O_~O>cmdlSsnY`0j96h5D`MvOeB#i{wbq-xk%CBmeeB>L~ngo9XVZJMS6j5^bQXMtMsnl^s=+L^M8IN7kINoJ$!*DK2Iih~zAb7!6A)X|nWqWG;YLWd9k}D!R@OBOlT|9*;q5L+}Q5ZArZ867;9_)mxU|`dCML+0IjaKGm${D1=wM*I2I@L&{!r8A;a?QiRe>%Yf3+v6v+pKiVT?Rr)!yNN^&g1WV^M;Rz+aJ5u^RywBPZ{zMe<Hc)hfX-hcFeOO!{7I*Px`1El+nYCFvf1femBOI=K5Ur=Nel6Ni99fPwL|0ysb_eQcQQG3QzWLl8G@lcF^SQ>FXs1eAez~NrQC9>AClp!1EIZQWRph)lqv(j>#*n@e0w~NTFqu3<DXa~N3o;APDB)9!l9u=CO0TY*uC823N8z`uqkO^90Nd)1wQiEztgjrTeM?8(X;(T-tQ)fHp1QqW)9W>#uiwZa^sPdx&uUe9L}0%bf{m?UxkWB?Kr4|2W&v~#jHL(~xeP(L2nnQTi7U?q!ziPUJ_-f`A>~^U*|*aQmfvhE*d2bmGl%EpDC2FQthTgrW?YIuc*;Te$V@aYL=!m+T&O5w3R<KfIDktkTXasT0NkqJO>(WGjQ1$(QFb26CNM28T>V;RqQhmZxi-`-0qlY@9Q1*RrN&39=WbEd1MFWnMArpa-W{kLfUO6;yK1>x(>cf1=PJ7K8c0pB*UBjEO9{Ang>3Ik^4Uv(5KF}>20$t-oeD~&lwFKY3Xx=V+9-yCwF-OL*R$&DS)Gjd#S*&pe)k6WAKv<y(=s!K?6e15U$%L!?K^Eh*w*po<CT#{2`1?`CkZCmD43EFJaMhi=b)rjiD5Fy>X1n9fTU7XrRF~<Cxn-!v8N3gmEkr8=G*mzs=iX|r^qk9z8<b_xkhU%eBT?oy`lU6UgkOKm*w|bmQ|A<E@fZ_Q21;UI%}0P7?MI~G-mE?S*VRlK{;eriDUx<6%CIGjc4kjG^;O<<CnJT-v%h98Ph{UI`ckRy`cJOL0NT^)*KFu){V&89r^C$*8arCArwdWKj7DCdrHA8K5mSnk0L0ReE?;nOEQp7pndSkdosjBl!o!L$3$d7LCjzx{WQ_>EJeor?x^dP;SZz?pN|3F1_pR{it(~a-@FLk11#G^(MSD;HCQN1^d<YPwKv&cSk?@^^N8i>{IMR!qv7}ZDw1>NUl;kS=9g5fz4r>LCAU^1`s9CDeElD)@G`4L<7$F0(-I3%t>r>hzRaSd)FNb{9aMekI#uP%!Az9}6MuYFdo`WUgV`JER32xmSK8^`fxquJg<afdG~O&Gs~VQC3RqsBH+z5I`x_RoWL$IAG_D;fEz-$=(Mk<6Ku}RykMvt)pM&Jqvq<I#Br-cVLqHQrFUkrpGc5L>_5#D=OSwxNzJz)WXPcznp!l~fs_UvZU-m}oNE)w4y}wP!r9|GE*GUPi>-Q!;gsf^b$3le6U3MHTvk+`ff+bUGys4B72NF$IBq@yuRw$*IiQ1wvCXf&d3|o~|qBqAr#ookRn!ta|KUEw=8nQKi#4DD%=}n3@0I<DSFX!~gTD_oXSgIF99jw%wfjV5M%b<6?PM?6Rez)RA7V5@!uURA%%s8#H%~oYDlq)$^IXG#9ky3=Hvek@v3_5^Ct!y$;@EkqAtcSp>r<E7VsfMkJ9hwGN)y*cwm;IqSlvj1z6Zavp^03VC4|}iL+ZMMkvKr%_tl~CCP^AqTNg&RPbrDg-<f8(?17qMEGZ`7Az%{qr1s5Plh=~rqyU6P6!hYhqu;<FBGgYejY@9Ei7M1F*5Qbfk`q~0d+<_LVlu97Xla<6>45esij){e=t&<{JugK2w+A6KkamKBSE@~f6Z`IZc)EAA~XcasX<h3~4)ShiYbue9*p5SE&lWLW>OQf&5vz24N)4yMA24r{|48I>~%2qO8AHET%y-ZiT6c3BE-{!t-B`=u%j`OXGWv=izS9$Oat6v`n^s7*>cQ+Q;o>nxgTm87o+qM+7wwSmZZ?m?$kgq?>%P5RrMm5dw3dg}<M4x!wh3pY%l1JleHQN3z5Ph4PgzMGK(of%iJ~rw4O_N@Hxu>RKFC^a1TrUotmu20841P=dx(1{yKHp|Da6a>N=wbZ{9yZ_ja2va}@bpjB`3!Sb(byw0zNTobkvc~aqjV}o?=l)duQ0PfmH_u;q$&@NCr$RKmcmKkG9)Ji3d0QORyDf|B72K)#+M_3y&HmhGxV=(n(Nx2lbvz8F+f*i-mCSw^?tp{dHW`3W6FV+E{mKc$S4xWSi*UeSEZgcW@AMltrLwfQDJFK<b;i2EhNQa2uiiP^{)Hvtk02Z^GpY6MSi3;`#O^3J&nUR%Mp5(!EkUq>GaS8Zm!!r+0MPTpKbfZWwJy!$r9%nVumDK5K;h-iWDBNv%(N02B%BKd@r;_$e_`BQh~g(AaexHQM|h>S*0({+4Et+o<};6?@%2{W7_8StEV!(9;~BuraesGrS@}z;OaLDZ$t&sP5w8Gm_5@xa?*Z`QOu#XKKdAVRw^TSr$D;I0#hIiSTNB8WUrj%$l4WKrr#*+Hws$}ZCK6hym8|*!cAIk;&ibkHgZ8+U2M%~5+~IO;_KBV8!@&#b($12&DCR*woLlO3<)ijcm(8vD`C9^9gz&WB)N{#8OG2i%ae(jyXeTKGZ&_bwJ60ljC#D!?2@FR&+L+_gFdrcBXuLeb`aeQuwL)FF}=$)255N_O(Ah>IG2ot04xeF(U>3v=f-AKrPK>1XE6xCvQKJr@j>ORjDL5DwQxO62?(Rv!xIdK&EXDP#BYmtSX@w*3(C&tFIztkM?BO~bQJQi^}L@gKKoQjCGI=!!8GlODV7j`6PPnI9*~i4Vi^Zf^4x_(5f~j!0=Xh3#cJaam31y>(qfX4m*Ky3ktA0A(ozNGM<`pLlks$VwBG$bS-tvFmhx(g^13R_<AKq-QDb&T{-8A_PA_dA#>3f>%J!?%XBD=eUtC|;es%Aivi7Tk-Bz{V9`zFywO`a!*vH)Ibw+ySwln4S;BwJqlMBuuC$uKW;JC{gjdGkrEU_IVO@s<UGfCFDLDGCPcqx3&4g(i1`^!=gM&l>!n>Y5|kS=fDSoprZgu_>SdDDH7+Cb4fRQBm*Ixmee7?BWqc`EU7WdT?QV%7lb_(ctYwabgE&BfL4R#!Jzgi9gY5-49k$a{yaiVH$4Pr?On0~d9j_7W`@oEgitQYoVbYqQKYfHW>fbV(ZUR)Rs#ga@CQ%PB@~nGG)Dt*kDKd8~JtEKeWVU>_b=8d~yfY>m><mimgpK8Hy(f8B>b5W-`o(LUK(Cer*S)$%6wrqT}CzR9$IvSZU}XWY-&>GTcaSF|C1Yur~_M-k>_K<Hm^NuyR62@qO@Qj=VAG)Zc~f+h{caI3UHx+v&CTE2%?#qR}0i-v<QkF$s8!Ldx99hxIsZiTE`l3jVvZGWhaHr+PE-krj~JEhlE`kSksYG#$wSsMk?Vn`whW=ZFdN*kWDRz}FcNu|Low2gwW2Z>`gIRPqhE9mN#n_ju;m789<d7E-`vIypFh+zH!6r2kRJv}0P`~H@_xqZ4Ln{$P<!`-<<!*#Shw>$I)4K?cb=lcD*w@cyIa63J4_7q9nSaQ#nVh=V*rClhVK2*#EW|H;7C~2J!Mg&wGtTo;l8H=VICBxDk%O`y+lDHwRvpJ^omrmk2yN~6pi{t#@7Ufw$;%xw_Mx}9C#OS37+#44?1C&-8a7sBTrA^XFu7dHICvY|eLYq~_am{loxoYnYr0HY%6hBU9h{K1)k0W^6rCRNcuYPaAst{J|6IVvp>%mR}*(-3ZZ&l9zGXJs1qi@_CTD$=arpuB4{4$;Wge%;=31_XNL9~H}8V{y)nbr|RX;kDfh*EM0RZM{;P7ug3IT4lO4v7Y0<QxG4q+Faa#>RI?!!iJO_L4|CJq+nykH^9kUK7400C#awwY+E<KUqR?cTemAYX4kU;kSpL_A><Ho&_%12DoHRbZbh|3QUr5V|?)QA`8hejV?uNTy`!c08l2Ah8AVEItdY2@J<7L!&bp{K`p;QI#N+#dG;-J`-pOboj)$F+cKyZ2fC`uw|<z<0F7=u`i;dcBO|Lt1PfYm>ouw@jWj0GvXjV`@eX7v6lCZK3>jrfUz0M17zs$6y*nV5M$GY@vc^5KzjU!X*7?5JeeQ^L<A`l65a}Wk4oq|gz315m<-JtaC$jXDl}!2^omE2EoQwjEJd2=mib?Wh!M{6l<^gcT8c(IV-1nz29v%VE9$7<>+k(7WlV2HE2S&T$+Ka7lwrGR1MV&p4I$4*MwT21CN)ssJauvxiCsxkf$KZpuf*DXTGHoGCA*AJu%k25-rB6>|XHvxGK1&$>^RhwU_n+4szKG@DM6eI>$0;eG!$nWE!E`o=)A`+3w)-;<hd+M9!SG?6ALxUAgZRBn{^5}LMF1!ezdtN)`<wm7Yby@jFLnAfn3l?^4@=3r3FkamY;$q*igdNF)nHmdn3hP<JQ+XD%P$T_-{|*v^1Y(}O}@7k5?bD?TEEwY)in1er2Vp*^>8^_NwfAtY|3UH`Bs~vnWulEc8na^WaQZ3qx1nhFd4WM2}=yNP8m}9*BU95f#^7j0FH2r8jO}s2kWK8a4R}pAEnVpY4lMVg%A5EjpqHq6O<>_hVWH2@fk%m^5_i%&oZEPhNDvsxJ!m7G66_w!k{#wkRn4=)<i9tbHZzpFWVIy2YUOq(#ytQXfET?46`kgBS~gkR9DV3+Z(B)RI~M{_m^$9J)xv&&z8|9?KrDmb8C~gN<t9MaxNj3(v|cNmr=!>2tcIEc!|!C#uJ%!%AnIiXcerqi3JU0f4@Jt7XI7DO_7r}Ltbry{OQ2v$Dg|1^!Rj}9cO@rw*r<L2UWz7veyL;Ini1ZjAW7)9~~WwS=y{=or0{$XiqGPXoTd!(m72CLy0%D60Ik*UiI5h9I*yAL{~Nlb_eRnCfMS*{YB`%-KSkZBaeSQVi2s)pJfRwuC6x$)_330{ntmkRr+^^{X}VJr;A+CipUjp#nX6cw#z&x6<>q(L3rU(c3D^zwNcK+BsdEy8_%@NnlrG-WKNPto!S+-7bM8gTuw1Qj-Q{8X(@YDM<TO#39lTN{d%yDqO!LKzPs{|`_p=TbD%LDO$rgRjVQDXISK{9!C?@j`x^tnDP7#10Sth&%mAr8B1aVz>ZoJj?+>@$9Jt@ur?c?FTfxhRun2f>5%d;8ZxLK6N$8VW1m{Uz(TdcqF$x3-CzNHtvLj(y8p@UcZ#p8lF_}RKpfH=jWbzE9ur?$v$~J*f!nbS`h;t)_X5&eGtcTX>bVFp&itM`bc6*c#B7v6UwI2|)zVDSZ?8Y27X#?4)Arprh@4+h;QF5ugBGsD|ZXKd772vq_m@HtlN@=14bV=J_+vQ!^?`HM8Ss!LMOMa}~EZLi{z4`iXyIJyM*{-s;U3=TLw_W?)tPi}KC2x8+YXaZ!>!?&-YAK3fe%X{>`JuFeIVyk;k=9G%pI6k?hWff9Io6EWiERFO5_xH6_aeD>C!Q*jmz|{YWIUZ!hhVojv)i|{9ec7y05%zwIWvixG+qUP3tft+C@mAZQl!YZ>?IkK#Z$wg)O0$<#HBJ0nUBF_b|XT2VOeIHzlY}`6iGa9;wI|BxS@TUomuFsIemfPzixgl`?HDN4sJCB9hsk-hy6tT+gd{%|9Cy!-rSyto@GE%ZQZ@$tq-`lZu4Y2_u788?GvZ9=xLH-HP(J|!jv*NUSMe&B4h{&QexRA?I4KkvsXa}L_=o3P9D4qW!uCgfAOA4>#Aqp1N;*8QhW&QvO8%e+S4Iw3_sv#od{?IgDe^7Y*2%WoFFJzj7Hhg2^Lh=;0S}kSwU#@xzq=D^0E?C6MSkhi3ujNV;!>QXOH#An#?Z28GB=UtjVn7=2(;24Q}r&?tFe{ti>!A$4T3&_-mGIQo~(Izm~vNWLjGmLsV#$EqkIiMieoU^39dc2wa=UAj+IoHkmHV0@dw6Xlp``d#sxmuV1#wI`CR|zIg3%-@Ub-I}KpG9e~woh*>(BqebpQh&)=St>HchGIeQrQrcT^M2b8@&OXSXt&S2?R95kfEd#6%X6!eF`VFBIypN{$J~nzEw~^L~TGN<up}fze;j5S}TE@}KoC4!Pg{VOW=F2`j3E&d*m=XzJFS(T>8JT?)N!*y!?bVuItvLr|yd98z4An;TAnQTa2FR|yd^LtMzb~=|PoyNlGfvvF%;Wdj<B>Yh>+?rYwIaDPqPB<W-N<LTk-s92s^vtshoQqf*;qANCTFq`VChwaBRVUkFr~>2j|_bh(FGoY5#C_%n6>lKC=qSuQGmMwj(Crw9!EEZBYxvJ8l~^U@vm*IMtvKpPt`^$3>LvC%lVwqSAjTe6;lWJvvJ?$3caL8^oH}Q!H0qL2*X^8PM(0HE!O&ZJpTGCOy-R@R>hzHGKB9qseYyrsz;bsE1Dmw(RfzDsG0+!%9HP<;^{LTnC$v}*H8RF7d(XV%P6%Kh%_IwqA@Qo5WP55gPN^@E~yc{^SrAswXD!ekDv1!3P&HB%}uT7Lua?kM4$ID|LaWD9Aw5O(D2|*vM4M>#yk%SnB{^ol^EGQ!U)ajP&N)xmUbYh3>~1gNpb+CF50X-13gCz7cFnMEE>G{#PtP?4pSc~WORswu3pfne$b8z8`a?Ez6u<jC@L;+3LXb(jaN`AQvAR%?uB;RD`r><ITA)mJ#^MP6w2zTtf!@pw8R{lvn*)^M)|<>Er7Jo7roz@-3!qpT0)Pwz4XyT4}5{UA`ga<SnFZ>KnOU}^y(E|{j&D23)27nKmXUXS`uG(Nn1YKZ+C|4W-;3v`tIzq*YDSgId+hVn-oh11TX1Q<N|CI#wbfx7HO0^djZVTx)g=*XtQ<TxpO&1?-Z1-bl%+t>iRY7j`K`TfC_I3DmPf)faU=I1KW$a{_^E$ot@SBV{z9@k}Fr(*&e2=(Chh-cNiSHdarg?n*$u#wAdKMbp|x09+k1yY3GgSlJVex0R~LYF*1d8>4xPAGPK5&<f0g5P@cteTz@A6XGda=6OO704hLTb<Cp2Cf#KQ_n2^5GA81AgLwqXT#fZa)^ZBdN7^ia&(t;W0Eyq@oe9Jr2(lQ+oXeQOBeOU)C!o}mJS1(qLbM==;n85T2uIoI!#9?@dk+0wtZ2Qap*STxeF`(5fRY;l{^R!55?vSC1lGHh4yv4w>%F$@d38PP3%zGh;80c(@Ni!7kvfPHpacHv<ODIsAtrBZ%7OY*Oef4g=X#KQ9cHNaLyc+AS6}6Hpw+_f^yK>uMmTEL@BCQ`R+UPTxFF|o8lXcuU(#=ZMlpM0~Rs+ORK9Mt@g+{`K5s+C3>?T04)Y!JCx6ZuTBB|Hg{<Qs_t_pzR-bmeOZ<|r?PJufEV!SPg)vYr=F^?L{_EXN08FY~r85W%5F$j=Gh9HGBLVIp<uvQ02c;sH#$Ti*)#QG$kKFO!A`qn4;v?6##TY~on3%|7{c&CpAsy{9)riaC^dYtW(t$Mnzes2Ks?+X)bedfAy_}2rYog|E3VPk!(a`u<`k3Bi|=2+133NV;1NB;B6boLXjWb>P3amxycYzr4PjnyRq!w~07<+11=Jg694f($5vB}0HAciIKuC`z@Al0ra7LlPl#ZCvZPxL_ACPR7&e@hXTLiX+7jH$+#idAK`JHwwvm&<`5ya=Jbe#=~Ph)>o&`(njVN*DE8dd++EXtApKEJKP@i^JpU55NkhQ>#zW8jOTUS^5{8oBdsFKj+784=%<#7C&sKxA+YQe3T{i!^{jy`Mjn81lajp&k-P9UPH7;zF${*sQcbpKYCVm=6sl@Tb?uCky`k>f&v*_3cv}dl^MYg{Y!K+20u#`4pM8?X`jj9BqcLh}8Ah*y%hF4h9CsmG=`BZ_@RpR0J|DQx2R<8UqAj3_+e;2U_{5@(V&~0{$Ah$QDR(~Y${88!hU~}+cs+dYpzLd)e;Tvk5c<9hVek#FYaBF|b5NXwwa@{rL>8C@&^a)cBAEbOh9F#o1k$s_mFI$#BpG$|Q7{k)Dc_RBUQTFzec;vkBej87Bv-Brygf`e5_rRH_my&VKD5p(X}*}~^J|(fu0OY^`S}8%#x@cqURE;hRh9xHHyV_+8M2pwVIV_Db8d~4IddIV^a2et!ZK%3JK#4V02bbX5;VNi>VO|lTRf%JL80HYI{4$}*RqoV|NW~Z#{&c%MWJsV_EUHq&Xxe8t;My@9O6+}<vk;8MN}?FEJ^dU*3K;?3tS1VkY%5h(vX9TLbIF<r$ZRwB5X~*kG{a9ofyCP2!r{~-my~PyF|5~x1S4HwIaK+)$?ks&*FO<mWuV&6T}u3%mW<Nq+WX9UM80e2E)O5=3OGI-%FE36v5CzVt>s+r=-9*FkI?rb<9{ARve6TT@3R;EDys6c$pFC2XtzoP+boR{ia{P>9@sJKhF8D?B>CI$8Rg(VTV6=OySj+u4mzg(Rd@-AC|M;XoJhsHs+u@Yj^HtwC2$57kC{WQ9A)=<{BI|$UpV|tT;PV?9=bh)~%2SGgV%hcBdlvhuW|D_rrpt<}RD`my*-6x>dDg!p+h>uah$xS5HVf(EKLD@AJ+%L!6cCUZ&+6Rm&S!D+ryP19MC_sIfeiCi~I2sH89|1rS{Lti3ZnJ8d9^<ctfUw54(~+2VVO7(8fXNk<-TKs#Oq{})zzn6pxS^#3-^k?{WwS6)5-e}AZs5&(8^cei_TZ&tuXJ0PnuK?9N+4Kb-4$l8>OyR1=I7n#rmy6CgWRtYT<N8}Q%iXN3^Rs>CEs%jZz=WKj`L74mqCC&V4Fr7V2A7<n6@ay1+C3={63A!(fVtd4}<;nlLM&A0O-%hK|Mc0L3{g@{$$pwoC167yr`leXazm5OLbgq$<yUn@j+_2N-ThZ*6j%*`HMZo+DlSk4N+Dvdhz+O%EsPLLuOV+1hGV8>BNYNEvOX=PUi40I}UE&}k>I9Za!J^4BBw?8KJl_BumXT1imqZfkp|PmOYr^`Ns0C>?JW@5I)u51r<K4A~<|1hDcA!z$GC{fs(x7HQ%LAb1#$^R1?NYPId5G3pkXQ=Pm~2oAi$xVn7_<ovZvYxgb!;=A^|=aLB=ySJzi&}pIY(h{q;6EP9mcyaP3$6|iFSZiw<};$DXvjGpr*6}(i)BBT*@E>aAO&W<SdJ{C=t4nc0%&VN;gF1ST=2|Wa7eIf#cD*J2VY@0-Z$T#{Hr0dcAob#IM&>xEkY2nBd7qqXA>eyo8k4QZyQpa8_y=E%#C+rW{I7=19&$m4$_jeUI5Gb_2}5Tvg^%S<C0kv-NAqUls({W$x$AAl<AWEB?B##p4aA;q9QNMi+AtrHm#zgPyDo8<h7_S)YuI$x0@Dj*iTBVRJI7glc6GR8BETf*bgA>M)%QmecAmtvr-ZgW2>zJ)S=-i}4Vj;e^<r+j>g}9{fgYE4^mTD^ylG_gno}ds<XuY=t%{0vAT2k^~XPRHS9ZC`{h)kU{|AnV~;fNIAG{g3>8@>4Oi!xQiB+uaD#5xFz3lfZ1$_5AYwyswZvJ)GskV&B>|-*_DeY?GM$>a<et;{WSyGp3;B7B1*dLLQStZw=qDtg!@GxD}<CbL+Tl=L=Ykn@K9S)=W=#F(?X>L*)E`iC(TZ?WSL_^A%AzA^~GoJ*1EX>GQ17Q++ZErHkYQp;8I_3sn2KX^O;%|yrK=kTVoTHmgz!S1}r<0rz&#JOeovgq??$`fUE+AWC}2uJS#gGHYBnk=%7);r&a~;CG9DS_j<tyb&V-D6h~T8Y>2Mhieh)5j+#)c2ED&7N}K7NW9w?le{*w99RUR-ra31iKWSFXXHs9HvQ{OFDF#epz8jb_FVz)%V%F&_!3oaZ9Z<`}pg}rfT`$kRB?*WqH#+|x7uRhi{VWc2mE^O2m`~AX;v`J)HZW1A-803E2xRIiZoNj8rIE%&QHtr9<Q<g$en!MnaU^8Y=egig#t@^lw}6RxJk_#T-`er{uy%YNukLr?f`+)Ndf#v-W&bX8?Y16Y#V_f^c@hXj8z89Bv@i%us{v?U_9Ox=AkKi(GPzRGk|~>lNJ@gwEF=UjJ$K0n4hAg<)2@lz7y0OmeDp?fZxr8Rk&l&e90yN>8BDIH%inaRk5)u>ugl+a!v1MM;cWorBPjS6=r-%AJW?uiO>xA1zahGIoy?tqI&$A{@!Or{B3+I$(FV$DEC|Lk<5C1#cybUvG82sp(L~My7b=RFf)->(Z~&K7wxxQf3c#%j-lU5Pfqxy7A(;A&<$hzi20Qbf+vP={u}z)rHQO~hVBd2qxfPVG7Ng~i)~!U#(?^z})hD^`8niV^M+?w=#1FdqoNgx1U-uypi11huhJCWLjOO`Gs^v}UZRZ`beG_{BWXDDHcgFoZrt~TDm$xE+Yit3nqX>?pW%MuUAsV&9NPy5Hc!^qaG)Zc~g2v<wDJNPWT@-YX!h5(K`TLAVErI3fBl34iab@|tHA+YFcg14&rTw3RAkhkfYV>@UMT}mWz`b$NGeBucgCSksNhxiTPI48DFNN`(O(Cdcm2q72oV@a?T?F;re)_^+eYc;!+s{Yn_H#gb-Eym+c7$#3ROvedwWQqhn~u|OQ#I*(0`)zCI_L>>3}QFf5a{*eic3rUHI<dwqiQPi*HLkq;p@S=EcJJ<C1&CfHiiCLu5EUJcbjxSbS@hXAeA%8npA53WrjQ%GQY`|cBpL9vXq{Q484hwo6-|c3lNcceF@Zt@HBvyJXQaIZ#Wzr$$i)m)Z^>FuW8POmUt7i{;@MoH>g^Td3%6b-1%HQZO!G<3pguPdfI~2YaVU1rj!-njpK}TL<2@kZ9xkWJdhD3TyR)2iD>aM4x%oBuJpIG!elN3=eL5W-uL^te7|P_>E5~_9f5m|IY_E%hLp1t%%PSh@zNDmAO<T0i2?Ki$^uIYE7Bq>v~p1)OD;vnwY9Cno%eBHecac1J3nWI8h;GD|M1qwoR&E`9x!s~0oRvpo@@I~+Yh#NeEE1~q)`GgxKENx%}(7QrDB-1&FH0e=u8$NWCKBJ#+`~BO%$Ag;v9w7K5Eq7dk~3xd6`_o>Erjds^pJHUm8@AZIUC#^A^>WE$6+FIx?HrquyO=^Uj3QO`pf@?U%gf)yC*LX)Lg4y@)w_U{aQXVJJjaS;dT*@u+k#1TkPPCC0pPjC*6e^(Zb%iJ&j{cnPqIsGDPEF#0x_4#I#w+V>)tcd7y`TZ*iB`>J5sevoSYAQ#rr+k1od3+g?>s6`gs|EP^gIW7rrO-xypW+w=l#fa7hXLTaWGK!>_<>)gRqNPt@QBRH4%sK6nJ}BFtVN#}`4Yq@n=3B8a{O4tho9{obIdK_fzFu~RwCu*ocsP70-+VBg4dQfu_oaj<+z*F8&geruk0-M-=SR5u3BC;C!{UC8?7V#Ac}c?(H@Fm#>0whua?`u&uj`7G^P5)_7=5h<(+a|rrl87`@zcEKA+a<49#6hk^uNjXmOwIpuWJ2X9}gV|%S|?ZfKBbmBj0GN0OiS_=Bz!#dbrlrW#!;v7Ez!N!ezq@<Jwrs5G0o-Fay9%0OwH)WjWc5$Vx2?(%FDJeiIAEmvRrB6qM%tFwPH|zQg-08Oukh=8sa1bG3YwJ6JSC3tU)N=12>!k^q@O8?QtpB|kW$j1a~pS|%Vn&ur$=CSp8J+KN<B3$21=HeASs|49~39uL2^WEJG$(faYL(?_Zt4ZA2CpND5ujK8eD(QxUsyD#^|Y9cpI%4JSkyUzZ@Y}%xb6-zs&lsMWFdup}8%$-)rC1fBGM5!GdOQRI6v{z(>J7X<NPM|^WZVFj9vXLhHjkJz8(k_7*Zw+EKDwN5(IHq*qRx1{{V5BF-5D7hGZIFWHLyjy38I6D}yx@#ZX&<dbZSsvQUem|&ZB|8*7QY&6C#}g=n%3&~R>z@5(W3R4PD&*0jCK<AUbp^T-Kw1ZW&UH2ao<=iY4Hj$m@Y^D^UHMh6RxoMChT1cBBC{j)aZ9Idv0P9Qh5xd=JB9na0xP?2-at0NQ;sSz)`5k=YdmnG$au+nIl(Ng)Z2QqA`B`@^WMq+7KM6Y`><ta#{PGaXPALzZ~<^q<}78_#wgMXy(Ko*?Achi<?yQn;glc*d}|GQL%UO;>?PZ`gCuPdT*H(#5*uQm;N^X`Spyw(VbDeM-P#%96V#fhi^C<Kegb_5XZ&G{J|HW;+0pUJW;iNqH6U-x9-*0NWbn(vgX}S<{?=hqE}L8rAp5U$VLmaN(7xscO>Us@bs5rhJ%BUK!;FFwrH=QFJ4lTr}(*!^=e(5J`$9%q_}ot*3Bp#g=5S|yu(PWRUN$fe0G4R#xP-05QShyE1AF=#f6N5hoprvR%J%;fvkLV;Jj5TdMmZaXspc^6=UWSJUwB0nYI<x*q83?OLz9AJDasl)0gf%uXN{be%c7WVwGX^WqOZ+bw}2j146rLjRC<kPtpnDqhu*$Z;jMt<Fr(I;Pew@az#@^G%=c>(PWlMS5`6y3pcaI^of;yVrA<B;_WW>W6<NbmvH%nlNPtH=mR92$A#1YZ$nUzy1%VyuA2uo+Zm@DysgH(x9zK~_iDvZI>eTZUWcrCa@s^EOpqX=<k=V$GJ8zMSxt0Y&O6U)nM}+OtwtA=5}^2HG1mv4_X7WWf-hf=r7W+{*MsO^RwUP5w$k=6-9TtL<lQY-oA<gFf*SpHMsb}14I!nZ96RkiseY32;D7-JOwKXogD!48j}jI0-l-U)49c^35rPJz@eE!jEv-cJD7B*vnztzGVf1esq7I_!x^B(99`x>V7PhAIvCK?ss5-=@O|Y`4HD}S~sHNlrKyrtg1s`Kh*##zPor*pbb1Ed6Wk|*YU80TBE?rcd{^{lE>3d7dQlAXeCj;fdbT;o8w)KX6#^TLoEWU<)laLZlOPfMeC^R#mlSc0`d#;d+pgjiCta*l<cwkyc0V0>MOF9k_jXWfzmYbg>m0<V)%WM?F-ZwlftVRU3OV<Cod+bZ1^~c(Iz;bl{P!HqL@cZHXlak3W|FG3+h-!XGwenzAP%TADH6qOXVF8~Xs_-(aM&oLNFVo^tt=3|@D&M6d2o08w*S7pg1kP#4zNGn(uSDKLD12a<S273Yi4KMOhpqQ)$gnxaU4P#Xc34o2#+wEGVLAOfSvK7;;90uSE95n%a;6|lM;;?(3fvfoO1k7jFc8YlX0({-Zw*qHP9xE98ARX_l}GFIMKN=um-rQj@C~sggChWa;YoUE@I3F69f_Y?P*&aepTmLCI*O&+8Tsza`u&N09FOx^O`?0<sUzK~Ml>`!Pm<KiA_ir3wDcpJAXx^IY7AvoQdlh$Cy9sPB>hd=6SEAYDeitBE|F$qvUl5Qjnud5`|ve;H}Ua>Eh-W?Ut9BkykfM*HU1qN^R<DB7V@$VpyPS?LSLd<#+(cx;IP1CleqP^WUdpzVou5Gn)Yd3t=30;D;9YRSghG+mQ2KgJ>xvLHsx%D(m_R*NWZ4PytG)dBuNLS-@*k3&cu*(=7eI|iiv+IChP9;2~GSBM|FwR9X`G@L%$KN_iN^h7Q{|nJ#o!_&QS-!z*ru&N3BDa3RtoGnJ_wLi`qHmqUWk~vL<aoYHpnfDYmHs^zAMB_7;b?2~Ri3PrwMj<({E!V5Hx5?|0o#g%fW9PW<+E-1i?=oW0}(y2*6*JX~x$)H#%Qi1wGBjW>CR?8?66S7Y`5mX;Qh##AvDOU75U(Py+dC{8+-b=){wGy<&{Ib`9j28cXlQoei^8ZoC*xPyi8?wo&Hb#P2y2j`9*CZcH>@j83wOVXt%<vWs90Z|whGUrxAB;_o`sG0UkF_pY^GBA#UEAL#0a1DovXu)A3dWT8xFu6^K$q)M?`lEVKK70;gy|k?J^BA2}Rw6o6N?gX6gk@H0CX|qw{wBND%7|V%BT;8XN{Zl&3-7rnmTW~@js_QdmtWuF6UxdN&ZaM6+--8ya?E>_lZ)Ccn-^?TM1EYE*@w8iPl(IDjB9jHl0;7cLRrk&TN%({RxB_8l_N7ovn1Kvo1%FP5Mxw41#7v<I^adg;d{?|fl>LDSbhZcHs$(!y-E3htw^rxLHW8pOgF-JIpn>T^Vz)Ktwr34)5Ve4;9cCIIBIrs0a}%;5Vlm^%n@WT21zzaWZ=Bwnv1~DC~K^CR!1SCmf#i0lH9=GSseA=-4Es6eY^ZPvmfJp2F}-J7JJCoR%Yl~2BZQWt;=xe0XNreo^0n{+t0Rrq8$lR<Jsdz*c3?^NFG2Np*aR)Nxd<V(>Wcij~)V#DUgDLHU?iR#ygNeY7M3qC5Y@3GW&$gi}joBd7VAJ(D#{y@o?5FJf|x>n+7*;R(xJvvJqd)Q>RET*`)vYk}m)($eaQfLM9hOPNeAAVvdmj<IXC<geQ}YrKE()R-tEtd$b{4CcP%HolJvX|M?L5&obeA%hNxJ)z^|EGsNngnk8>wkVRj*$8k#EkAKc3L(nIjcT(J3vSXF3j;=L|#et)U+~e{lL~4vlx-4aO5(Rfr`pB#SQZa%`+B(Nw;5Ir!ECCVA?x5h2^b46ZNcYZ&?7Po=^6oPigZzYD_&R9aVDp*wphb6jSWf6eQ+cn0wDo}dzh8f=YnRR&*A3axmij^N>=AixM1LJ3Yc_gOS;sSAl!=xw86f3SEyNHcnF1%2uz)#<lINNn3Q$U_fYJ#qGJt6jk-S$wKcV_L!uWMsus2%>o}D7L?ZjQ~vDr<BU0x1}+tUA3um9b`YI82i_~j_8i^sGmZSi|VCXI;60HCl;awwTHnklE1LBNFE3P99WNW+pvqH)&W2+E3jw>P&(6u~{p<7(jkC%fuOG(J3FcPik{;P=;bw@pln%P}eHdOfAUq(DQq7c*9+pq+)7$z+Q>qV{Bh#h@~iDogHt63H8#vZVhZyA@2{TGIg0Hx2ms3!%Imbh6If$Q6q|IZKOM=8BfOm?b8j=H<;jDW56_Yrq>G7-vqg06udlen(@lMbKRkkM%r=U+dwvJX;U6zbpu@yU0Cn2I&S|^8xR#3fg#B!r7MaTD{{nOtr?~As11~XreRded$D~yqC)QWMoWMGU;<H+h@X(d8UA%mIbX}DJIF21^>?2>C1H8iD%<vNbt)c!Edlg*X5A-f-w1UGJeJf%^ou1k^VD#R7-?>S;S2c>y+pG>ze%wb@e;VszUzz<3L!(5wrw_GV(bfD9g^lChyBvd{ZCyzm5OL6z4kV`E6-WWo~gfbJuld2V)&ZPX-DHD?vMLg+R@HK%RI=kvQE&?Np}2j;AC&YNk2RLPtu|ZRkqN39a)}FU}q*Cc7ZGZXR^l4AN2Q*fQX~nII=aM_vw{8Z!fYB+EhiQl`{rhSHL0Z=9tiz<?83Y70gFv&cwCGC^ov%F-CjCPuAAi_no57Nv>9m(Wm^W=YaemS#!SL0y`ykvc3)GavO{+g5DP>y|J78g@uy5Fg9T(pp1mlvAmcdkVoJqOsa~7PHR*k_XPRWn|Gimr9KRuTs*=@XX9RgR8eg?rVqjbZGF)p>g~6i0o_F^t-8DEjHqEM2YSy*}N4|&qEl&<Y5}=qqP)Gw{GqGQ1TuYoqcOSc8IhdZa=Sk25+dZtLnv?5xarl>(LK@@xOfp-S3CD=q&5@_CIp=KqHUmxidAKvp&DlU)ERGC^5@&?$cQ*nXtIJXfw;{tisDE4Y8ub6=&7@?i=RYK6;L-!*_NN*(>(jd4U}!+!^*lZD)HB`V7;Tr&1E)moh0UCaKkgnz(0KhT`Xa*!|bBb8qPozQNvOc{XgXlX0!|YqAe=W)d|=sUUEnol;I|nULf$*$Xav>6Ed6kwvNLbc%^fWgIdegURg1MD}W4>y3pqLA`kX<C^BW8|#ld<8&j6w;1oPw4w7s##;ngjirG?I-wl1E^&j5IYwrAL}dWDwIM1_K#Lks3#)?^Npk|9i8djbA0gig$od-PcWa-Yj~~$@e#Gt7Ew6j%^K$}_J}@1jdp^YBc=ou+<gLNdVd6L7YIWgnr`77hg0BB#dH8?-&;PYKv4gcbijI(X;JH5o{^$jBzPdWdo12Ii7nmsNrOp6)<G6_6P0Y4Lcrgo!G(;gX1n-ngS_CbO^ad?+IUIBsKf|QV()Hmr-=UvA<8T-j<yY%MEVoD+_U5-qj~QbtvI4Qc4B<O19Y52U)i3K4zYFxHUw>Z(m|`^!|G>DTU@j-=VOdJAykL3phtYVpDx&v-slMFf%KTf>&h5WJsiZd_cJqM$R4wXT66yR{wHk?*I$RgzTa@yvN=MoyEa*;Cq=%$Wy18WaMOtbmyfxSF8j`>-2uV1A<AbFa-}t>ZH5SwN5j+jz5zg4Hu=w5#(W-{sn6p7Tfrn&5La9?SU}d&a_{e;A#yacCW`!7v;i`Z;(iKecO(rifIsxHUG=x>4_?(OC1=#ZRk?`;(#dW=k)2&fD3JPDr>%Ib4-?I9P7Ex5AXLD_YU`DIr!Z(Tw83hlt$d^9ZnSlcWj*kwUw@O8Cr4|{Dwb_=$L~{)kT@cL_C*$e#xZ8e1al~7{A-b}Yes`dbeDkY8KWH?@=^pt~v1)oW%58SGKYo63y*qw&?;UUa>fpuBcz%jAetXnU<cr@xY`$^YZa#Od3~MsGP{<sWm0Zi@3`Qi0nw-E$LRYZFyhtRLGk76YY3J>&Md=|YNLfW4ZcOlQP3`euxaK^!f7>SOARMmyJhxpwysv<`bKu5Xgj<cZ031uxPc(u-mJD<@s6j;zDG3&%QI>O4%G_yiWF`b>g$ml|sF`&#-U{57(Qz=$5A#wT4@3Nh!v}tB`)ft}#)vthujcggh`G(L-_3`r`0w|2&JGfE6;Zby{Zn}C&%l;w5nFZrS$GsydCydq5tYjkGf#k4TI4QR;7V|XEc>jKh8$cekeid?bO<ku0h)e~kK<?Jq_*tv_<i<xB=mHB{)i>MBDu0DzCBDww)kSmd#!c5dA(aJZF|LbOf?8<jxx`Tpbp#vBUM!@9YhvUp>#TA;Yg8HDrb{|l}RV3Oq5AUEs`WrAaeVlzbFanp~3&QMR6<{s+xA<g$ug_b(IuV)%oJYM^7SOPv@@~s$VDY{7mmZ?TcLBWLJ+G_&1l*<vueHR?;U0ZnZOHYFn40i7av9SuCcwiQGtrTEygoNLoqDRZ#LWi~Hs4uP^D#0Pid4jrT!sUCXMi$t>k!mTuh7q^}%=QWN-v1B?Nj=PdHfc}yZ^D<u}QAGyv_C>yN|Sz+lxCPA5OMD&`_&yu<&@UK7o@rqJSn;gGvh^}m?><-jnEvb*3chI5;IKjVm99%WdH4O}%jm9OzQf4v$hsd3ZIti_9AniXJ7OnTfpwHT4N-01HMraEtF9Fy8Hyk{ZNO^3@{6C(~-I&S!a~Db6o#$`Yq;7xkm2^3cr0K_HoH4!m{I3$(0&#eko`5^h{|`dGv9%2?{3#@EMTjW4Rp0~3AjOl63><0tj?@B0Hh_vY3IPEznxvHX-mrYp2EYWqP9I?kZ<kS!(tLXrhX1_mP5u4n^`}}!Zy&w+-+yRwa}J&cvttduwkTf7y93(>L<xl(s{AsVBY#@KwA#AKwtsYe@HJ;GqvI0BAxv7{Em%Ecx6P+lgWjP4g`(4CD6Wzpc3!lXnl~pk56X!~v&kY!KNFlc8m-M*2$GzZ6gtissvMYQOfiO%D+5+>FGS!dY%s_$y33^IERTm@FEyIxA>uG3jrnOXojpt+W@EbR;E3<!FmXfJ`1+#XPOHsD*Hr}T$9%Uy>fi8kxA{ilx$)G?w<^KMUx<%kUZG_rWFAXA@^%1QD^Wa$SgjEnUNdW@A)7~Loj9oz(Utwok|_(xIM5~e4`f80z%nUVG+Blu46~l+8-T{znK+^m8zU$8$&NV|w?ESL-HWeB>&nTv$BZ9weea_w&ns>4Iio3C6VALH;au0yL)joK2okp}hm28k=AzLt8!%RC?=|;i+(o506G)O;3g9Ms$5m!Z+<<UiM0!nUFNv`G(3pY!n(z&=UdxNBR~gyA?4H<5G}%AbQLxv+r~M3ZU#)>ov;(@DI53rxv;vc4+!!Cc$XP;iOruND8ke0*383t(_@txERwptSSny5*ec6jZhbh8yYYNdY;IT;N4Z$%bXhm~v^=EsWt`wien0FTmvi0RB;}K~V<GDpODBTg;vo>DyYLl^{1lbcFd0<H>j@fyXXlzOZBxXfc%4SYRw+c}52BeUZTbZKZN|KF!(AZdd+U9AV53qDI661WsYeB63F8eTALuTh8%hCCRJ&Z@g@Aa9{b9k*2S*!Ua)k@o`pju+08qsI}!-4~TAVqUljmFgkU#3O-s@4LhD&MA}FF#l+Y3<;4&0y0mq5BH43qHPK$Ts>5-j3OWY1zj(Y?F(<Lp2(2mZMcd_N#2{>oehb+Vm0OQ<rH?!^Y$zGUizToR=#KN&<Jna8x1F5-vQg_`!1oQm=zkQi0Q?dIxK6M)>?VAMVG=T%CCS&Eb!`!s<Z@wDY8g`Jkmf4f8zy=Tk+)Mj$?HKldvsap;ZDGcmhD<{M`I611)imTKvZ*ubZHglWO#6Gl?C%T0#gtMY}1IKyqEE{ZN3u7@C6!Dn6DWD8275GrLtosI!Bmr9bI8%Z1YiF5&Pe9jI<(Z^GA=zJ)ey3z8&{EJrg?j>i`+qkRqM}nGGBv%e;+8(B(fTlHU?k%A4Y?WKKf~uMx6{Jfi6H{<pD_YVF>C!A?l$Mq_;3`L>wLv6P)**AwnczTpONOqH!O4r-c}-#VebN%BmOb5TLA5?#52}Azkz5y4X?vJ%K(%Rje_x>5OyyZY!bgzwnl+njSEIPjfJTD|##*NxtwvljPJm&gO=5D6DIc_wG8em6G4Gv<G0LDkI~aL0LYO=}4W`p}@Uz8EPcPGjzCD`KBtH>(^}FI?D{MB;d|eruTLeXguhJNco-nI$$u6WOEI4DkJlJoi)#`44ctrU2y;}A6+Cta*?dBDq!uW-Fxuvd?FnS(5<EbX+f?sx^wK&wi&e*`Y2NlIb^R-b151rjs|JweL=UQe*kX6^tq7-k=A$n;_7K@L9K!nC{RzPJ+wVs@GjHT|rw>%n|(K<s=w51W5x|JoW4`}}k0quPu{l1X?soTw`>M^1XX<K7v3lL5y%YbEPNn?qeGZT=G2yRSf5CSO7CNP;iLn*8ci3>vqjS@b!;Rd@{>TbMX^IJXqIvC;f>vpf88+3+kJ>&=WhMl9?+>r}RwgJr=Tb+<bz%xO6vNM1wlay18Yr`DaOn;OxJu)d2Dlb5lqFP2}013_znlDQ2onj({J$`RX7kb8{QTfZ$N3@_N#g$c{tx-DCf950JYY_da0?Fzn+p*OTv1Vf%`z&IyC<6D!MNbyGw9-In6C<UxNjk|@Fus)daW;jZl2yiW&2#d~tG2Ope%1X@Z1vfyI#gY>;ttV%%+#i|#}3(*t9!f}>%Oa6b&P=K(l)V_wv9G=GM95uoD@3iIH5tr5Uk4~3vV?*<RJ&nd=?rpCnF%U5ZEms;8s=>(XS?5wnRD^O1vc~)p)2vwnppdJa>u9()`h89uw(lMiPPq5`q#7(x8)>TjdQ%i9SV%7A3Q7L+OGVQ8d#DM@Q0zHU#x>`rDf3x=YAxXPk}_9hYO?xr(;+nxClZ%0VzSs**9<?5*WUMpntK7H9>N0NUnajA6DaClv$eY;_Jg1xq(eJ}aqdb-fJzlV|!&Ev8BJ8>ydpBXt#S-~NVb4Wqutw(9$VtKS0Zw}3w17Le?>fZo0ZbfN_2?MdLevR5cDMhzf^@?K;XBLH#}Br_?<Qe!R|MW&7>D~DU;HfPPG7g~~86x<ag@I{5MFR2Lgw&E`BmcQN^sH+0l%R%o>(OIKwGp#ci46m)`G&|#XW?YI8g2<t?cQetr5KZJPaG|1zDQJ;`-~cYEY|%NT0&uH>H|ZK66Md<LzSKfrYN0Q+a9zdcaDw+z|7o|2Rh^(~EUNd8Wfocz&c*e%+zS~boIHHP(fH|AG|YY+%$0UQ$`e$pC%7;`ckj{Lk7v1<KY4rn$?KX_FqF|s^v-!?+7W|th_ZB+k126ugiQ*a;So>-4ncYCr1Ydw&{g5Kl!vW}J?<rG?y>gEHdzOrlJ0w~?Q-FL>gs1BPqc@;x}H#3I+^3V0aS=QTBohyrJ({kWx3Mcf+JES<mK#x4BF}_F-2t+&v+xqn->q9Jr3|2zM*j7Yr=-2fy)bi+gZiHngKs@xxkCTAlm~&T`D2>Ok)WXW`>SrXEX7<2f-yW6_gX)Inat(7ikGX<2)gO=mP4TwY&lt<oV0cKj0e<=fSu&FxU{(FF^l&O>-{8>o+m{KX%6HX6adtd2i7rE2M4abU3CXEeC8JX4l58W<rxPw8TWK(F1ebp(BNl$4D!Vq<^G}s7t9@5XplMgu@I>D`AvDaa$1E%xf*kwn^$?_NOhX>#i)ry^*?s+71KWS1GFV(Z<_DTV3LzG!{xj4-s=Dv`J|U4=6-dS;dT*@u+ktA@>Bulo<2EG474=*5hT(|7xCDoon|GM&Ab0K^V}N{9XcY7QUfY&HpzRgxY$LYW*M|#S5@*4S3CEKs7A`AUQpT!a%B&V7XLpP|-`$r??J4%$l4`N<@%3I0jxhS}s!X#Lj?9+jDZw&*H}&oqC*bR80uwUk2lsX*K=+6vo5tT=Rs5Cy1ej^U2$!C@=GpOZv{ri@Uttcv4LV#G{jL6U_JDq8jJw|4H<{2QN3Abbf@1uaI!w%Gdm_c16Bw6#0%bNtU}+puLfhy<*7#&xY9opc2zptawqvkgU-uCc}iYAqF)0D&a=z0$1AcZm-R)UVrJN&ujNhUh6u%-plUx8&)aNHz;|R1|^M>sV*<Ov{f*iN2e@lo<4a`qK9Xf0xj~$g#;-imtei~L1FURXC_JmYf+k(9Fk1%6b4^j#xHei{$MnHhF?c-4}M(F_4>{a^f_jOCw!Q$@pG`C=`LAW5*Cayk3ugC$zZW~EV6^?{9rU+LH^G&YgI0QX-OK<<*UIH&T#TH7?oXPdV(1(_k+>xuJ79s{LQQTu}}2(t<CmhA9AzWxAgtaQ=<>@X_F33%XrL5GiC!2=t9wwJyTA|@-G-;71?$wDeV+M7Mev6wiG31iY&p)qV~ViEX~HFwxWvrn6}Rx)3${D_N=xZy?=;dZ#t%}WrX!{`+eMgU%IJ}+iy?!@|J`z@2-r~CBpao`WEpK2BU|k5~W?=v3i@Pwz|d7g{oRoUAcMn{!pKxw#5*LcUL<&?M7}M;;2UbL-1sy(SR{!j$8&?O1VH1&Ppw#<z9+J%05b;Ld;nxf&mJKp0s?$ZUF+TozmsZ*6ormPaoMKT~b_mcXVr%j&?@pBi`Mv=$U}xEdi>o-5jk8+2-g7Pf9thqmEogmsPT~lvuKlQG+16S>`0XRi!Zxik#4S49eaTpw=^bJoKP3#Pm;FR2_sKbRJ;3!+LjVH=hbJ(Gtk&+Fba=JZco0tDMPbMi;$B7M$ZT2#`jGAcZtSdv0>DRtFh<=3dyyHQoZqrjO;5{5YK<4j&djj_pG2P_5kVtKZw3QAAj+Ph5LX>eXN;0q%A6&DE{S*<a>A_IUNp&8*5Bz+k!@`Oh!Y*-yB_-<$Au1ysnEP*D?GDqSw-3ra(l48cHgE>Oi3SmMO{CE`Jp^c#mn1Cgv91PG959ZJI3*fuIIh<f`nghk=o8a%Ae*DpH%wj#MM2EJ?$)6H_T9P;iIy7g2((yUCcY8N#Ik&+Q42{$$=W|`8Ze33+JnD9|EQ|u#SP-o$VcG5V{6Kd(uDO3s2yIa80!Zq*+!~8I>Ao(!FZ?uZ=qs>g0v~Oz~T<EJgeR073ar5hU^PwvK`~5zshX^|A8N7Me&){x22~4~tFxA*ZiAQ0T_e^COQMnwkl#E3y=Se{pxGF{v%brXo4LP_dG|S0wI&@)IvMI^P8Md^=F@fj7vASRD^YzQpUsoj8U6v->!*sJOEr+~26KMGIG#Jgp7@uMCwY<yvMcY}QUUO*E>V(=#6Mf{$f>bdSg-=5Wgci_=jtL<9NTKuI2yVEL5|YZEK?3cAX%|r9G8e<qEyE4LarZ(O8-~N3ak_IY^xK8^vt4NV?ZU?G!Y!O#p}xgy@zuCTqJkl{UZ|jjS1d~lMwUP*CmGA&!6qZJ7eN_gOO3^pEt(V=YM!MEHzRHPssVk~fO8SXTR|AVy%GU49DRA|L!kN)s9vY(OP5|vrwIsOx8t6O$KdPWKVkYfXic?wEy<cRn`@LUeHpFN+%6ZkYu4P{^gvn!F~{t&g3)L^n{(1SjJ{fn{;EtwMYB9uGE7S~RLbjAncn6RCsl?U&U<(>10KwSSk3<?=V9|jHu()_eu%TQj3dlmqhxSxvI;6{#<YsoLfH@tD6L3da%UB0txVA`QpPB>kBONWRAOK`AiEVMWAoi=*OP6MdNt$Ux2UeGXZ*T1Qa6gm4ujv90)PH;BHBQhsOv*O3re)wF>uPr1k$=7=@2a`(i&P_vUQx67aK#)fjeIs$a!mx&ekS8eK{GAXO9mV29xh?FDj#PHAevHSj&!<OMw4jyPf8h)|H}OOs<?HzZ&F{MP+k~R@RU6=lnc<sfK$R+ike4O@LyCD#L`#hNt8_=$tv15s1TW4pwRBVla*|;|<xafd`CQrpv6=3E~9)6EE)kyC@nwB+&)`f$vl0<fqN(U6eNY&H8OG(xWyH{W^#A66O8ihi!CCLW0DEFg|JpTtSQ^e^UU`ZV+5FnG=h~EK)+Jg_l~V<aGk?BWiw`PBR$~hb@Jg2AIu;_^_DQx(e6ZH1%4|Pjj+r!&ld<(i`@N>PD~G8us4m%I(Z(ZL0Qtv{<`?It{NyKx15$N)|8~R9skxPAFPEF-NWvPfU|g%HYXHLklihP3xugqHMs}qyppl-33-3RP~92s?HQoCwMjL0d<41Ro~$0nLb84kQy$$Xh%Xp)&y?=(UQ2D(-a*2X?^up;K=$|M`+o3s!x>k*mA_wA--!`cp`>WYW>Sd%rB$}MlxwY>F7v5mNskc5wc=jCKg3BLh@kgoVJ{!#2dg#AB6aMgAh*v62G&C!$;v>vn-lyc~l}RjnNt{lp_2KaK?g`(Kz9`FXw{FIR%-uR7nPIBGaht;Rwm2uE+xqDOzwtjweJ9lke4Z@MVOvikSLK*;aWf6{E)UqFXPs`6kQUA+{*ORcc0+%9HfxpK&_H(HETjc3S;)er>^NOVI<HN4oKPUu`)kul6<CS_Vb4{iU@FCY1_!S_W@RX=V@L=#OBN1PyAwHfm-$sgpwJ<h7vxl1f@#6gm7WPH^?CE$xN%P4xOEdVLeUzKPxmRfzU6H@Dxf5^7v4?{2x5UYkO?H|+1-u)h>cyhSka+cW&Hpz-uE{Cy06n+OywBJc(q0M<S99qm=~ey{qSg76OP2F<_Jls-VU6`R*;phzu8H))j$4Koq66A6;ZCE{B`h+rg^eBxkpc0N0UO7P+)3tl*@S+dMAp^)Dg4A(RL(42L1khUI{KOg#tSFVLwH)J<3JurNqozoX6{xsP+ElP6Uq9m^|X;ewY5jvoi$O5wfItRuQ3HMULH3%0Wf%GhK<+)%OWz^9}!9XCSd@GWC;UAdJUJ}9iq0vw9n(z(&g5^ckE5E@nyC?Rl=<T2D$d7RFX+LXZ&AA8^Eh4bSq){nJD=<mMjq#)@<t!mNrqQKnjmyrZ1OUoppU9TURwp3>3*Ko+=_)3TxUhQo^l>nmHI)xv5jE5gUy*fDKzw_w&){?WQqC@b@>m`eXI+^Xjk}8;xR=Q#gTZico_UwZocGcs5k)Yj<k4l#L8qj^I51r5NXC9fLF<;f6<DmQP;O?rt`6mf;z%XR4bhcrQSJ`ZQ8midp!Zr}{9L^87V%c22wK#dv*>cvQgQ(xxkF8>OpG~Y7nsb(L?1HC7?R8~B;$cD(MD;P*p1<BGrhI@_$z{AJNPS_bHV1`xOcxjPFK73i!tvl?c+kEi58Joqwoc5gI6YUo@~h30Sa!N3c?$QE*K|4SQ|@M3?7s>CS{pI@uqP{6c^Qi`gQQ-an{oIQGzdDj@el2^YsAxmler%7qhfIOgHda4tcLzMVr@aM@xLgmW_$Cit7w$G>|T6t<$AJG$$J>IADMQlXFb@P->`Uj}jI0-l-U)Burh_IQl<chF{30ZV5(l_!5qoN{h2c9Lx)XD_cjKK{|3GmjUk;Jj>bq2YkcfyuWR$7S|!}Y|LngLOY$ZRTxunK}nRU)cLnwB9aQ21W$%rP##GuH2(i@?`oRkxQ*y9G7AlK1Kl~Qa&na~x%<%gl9-|-hNM&}SLMIwVY!sEOD#1^)0SdOI*2MXci!~$$9q@|psmUX5*thE{tac*uTDLYP`?_S&Z!?i**rI`(x$Zf=fQRUn9O>(=AV@JJtw#5WpeA}>jPpQyHqN|p-~K6s8#Sg_1={nnyQ6fQ_IoUDF75OB(_cokUZ&ybBq4J2_Jtad|xB2J~{OFZdG4idQdxsS!zwnVkyTYA+Oo-Axz1$R*0tHYkjMAClggkDaM#{il+9$>Gb@W@`?|+y?c1y`PAZ{1EZ5O<*yFRe&^LckFNC>n<@X}c-xn^lWx#8p_OKHlv$ZV>P0DQi>=n8v!bCCac@*-rC>A47_+ZV6KW0LKr(!vAOAi-{+qLmUM9=F!Kv|=&9ZMq9r1T{^wnp@&&sd(GWm64Lfpzo#RC*j0H13ebZ*2F68U<yLISIR-udW*O7ykDG^QMS8L-h}zbU_d8STU6pY(l-`2Br~ua<1LyF16P)T?py5(WNqeR=m{yzy}ae|f8J;?S&XS?5R-Bcs|(qf_T(Gz}b*XDtv=nQEY*9ID$S*R{kukKI0Acw!&njeqQxuKoS;^|)ODM))nLFt!}f7$YuHWpr2WIi&(dI;d)NZj`7{b*Q;1J&o)WDKBg4=KALS$ICu$_Rs9?r!*Y@zTQ3PS1XJEXVaqG$a@jMx82^aA*NM7T4S2i3_lKT7%`L<^la<gCJIgA;V{^pxr)%;Z9M^%c(IO0y!mi-@8yNzdO`T%&Tn3iyT5(f=i<Ti-oFQXVC?GA3A96MtQmD{Ok>DcjYO<rdg7UTs4b49s`zo(Y(`w-bPrZ}TF><nTHcP9&qgZ*e@^@fiqudji>6lc+IrWc3Nb#mLr;V%o-3G6M4e9T8c54DIz*ec`!+qtx6L9WbS+7poW+92TJy+h(iHD;AP%T_E3x6mBoR!sW`qbSqWdvg-j4Qs-wsQm#-hbR7o}@0m9(!dwMuuNAeO-u0nL3ncaQ5VP_?QOgp<Z}gw`&~R<!q~=b_C(z<WcPWp+Z|G*e$&_j9)z4GlR~>6zPFIGplCY$&6kc$}%MEkqB|a=6fqX!oY)p|yl0M}pNFXG}fjp`Hq_vj`Gkd+oTD+RKyyk7^S^j%Dd3b{%21Beb?TZuh2V)&vll(dRnj2`S#$*5P~5?!>?}R-QFWB~qH}mA8t_tGR$1841Eck7|O13)+ZwZ+aeDpD}XuUeOM^7ld&v=o4m>BMPzd3fS0(cdsq8ja55zeV^27N^FnN%67DJHd+$03?!`Ucna{xQH<jl@FUo!wi;AQ3Z<{J-KEv4rAa}#1ys~FK0<33c`Mp`)AP`3jy)>=R>;iSH9>Q(Vm1-C>)V5YE*f2A)!^))!;Gg8R7b7oWb-J?a@-uZd($&(0v`1c28G}`*A__N2(^rc2<`#(KU!v_7%E!~G#l>9rg=z15^CR=kI?4rXrJNRZn5CW(%NYo@tS!CTACfrSMpeE0$5m3y9P7-+nh@aIia{EZ9@*x7TX-Rd(-pK!fi=?Z3x~Q2oi!ft@u<j=fM@sMuVg&rL2hwwBR@heSyH%z`Z;lq789NO;}rbKbRh)#n=;QQ=F_zsx>a!G-MI!GV07ZL(MU`OELxOoWSv#7e>cL{6@uCJnm%{Hlwxh4746YD!U^(pdUl)5rhjYAu@>RSjtk6f31WJu8MTixsF7I)3u|MF^wa%c{|$t478TkMw=oiNTAYG7R?1MA1Jj6tqd+$XCj1HhjsH7d!G1(%tSfPd6Z>ovuo3HJX;#T25ZQ*(Q8&8NGFh5CT}W{4Dvx&Gpj@J<kxpM;uHOCZQ4um(6cGpMcfE>Z+aeDRQ}!-1S}K&0n^GvC<iq`yp*hcqT$ZeK*m}r$hANzMEJL?0wVb^YFW2>c5ite*2ykVXUG`Pfx#ZcW=CC85<GPZ=(!2e35I}%23Hd5E1>~5Yodh@`<QITD$l`6RB9&iLThyvkT!`!=lX8DtqxWNxt|0S4Ee7K3=PE$Hv;)-F72>(DR0HPw>%ST5Fj;&T4}u*Dpb#z5l@L4q9fLT%2vV{>!t?kYlmEO3y?ibtsm8b61GI_nhSa`Jw|)|B-#+9<kY!1q|0ihd4#1OQJ$c!OKBjWNV8dmTh1sA4xhsN=y2>^;}Kfg;@W$(^jY6NjTU`Li36i!HIBR8QC2?~wUq{PTXV&uuiRH}OVaD22NB5_Of7(%AED*#X!#jvz0Lw1GX?|zbW8V+XaHCsZd5{8dMz_(Z`3>rNG@8gjgqZ&$TB+OwMDk0m1m$uNvZ_l0DZfPs0Nd4bCo9=Q7DHsc_U`kz`r2J!4o4uqWOlkFXfTe)v|@n?9lE_&qIs;G;(9EJrvX~6x2GGBxk@B=v~Mhj~UpgpfnVdR99q-lx${CM?Ea3Ey{eMeK0)_Z7j(Vua;VEmeI1%6nag0ZEOG<%aAsB^2C-DOt+31MsM&q2)GCu+Y#ElH4+|7Ka2L~`;WLCYnJUAvA0{@(%y`>zMJU1yS%#^KV9DLW?Ns~&vWlz$KTHr`qk?<@2{@z-hAfpum_WOugBHnubNJcri0O&_U8S&$19Ca4#%g54?q0wjlcDqCy@W*cYgZf$D{Gd(Su8OA8(%k-j7H5aP;Hl)k#>7Mh`yu?d3ZA?!(Q=d%nK%cYgE3ZM!@~u*v8E$iJ>Gudm;KZk^caGv|K(&wl}JL^*E"""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _decode_private_review() -> dict[str, Any]:
    try:
        raw = zlib.decompress(base64.b85decode(_PRIVATE_REVIEW_B85))
        value = json.loads(raw)
    except (
        ValueError,
        TypeError,
        zlib.error,
        json.JSONDecodeError,
    ) as failure:
        raise RuntimeError(
            "embedded equipment review cannot be decoded"
        ) from failure
    if type(value) is not dict:
        raise RuntimeError("embedded equipment review must be an object")
    supplied = value.pop("privateReviewDigest", None)
    actual = hashlib.sha256(_canonical_bytes(value)).hexdigest()
    if (
        supplied != EXPECTED_PRIVATE_REVIEW_SHA256
        or actual != EXPECTED_PRIVATE_REVIEW_SHA256
    ):
        raise RuntimeError("embedded equipment review digest disagrees")
    value["privateReviewDigest"] = supplied
    return value


def _public_rule_requirements(
    review: dict[str, Any],
) -> tuple[RuleRequirement, ...]:
    return tuple(
        RuleRequirement(
            rule_id=record["ruleId"],
            source_id=record["sourceId"],
            locator=record["locator"],
            expected_block_sha256=record["expectedBlockSha256"],
        )
        for record in review["providerRequirements"]
    )


def _build_runtime_binding_entrypoints(
    review: dict[str, Any],
) -> tuple[
    Callable[[object], MappingProxyType | None],
    Callable[[], tuple[MappingProxyType, ...]],
]:
    """Close the reviewed facade-entry slice over exact source contracts."""

    contracts = {
        record["contractId"]: record
        for record in review["contracts"]
    }
    requirements = {
        record["ruleId"]: record
        for record in review["providerRequirements"]
    }
    resolved_statuses = _RESOLVED_BINDING_STATUSES
    expected_counts = dict(EXPECTED_RUNTIME_BINDING_COUNTS)
    expected_digest = EXPECTED_RUNTIME_BINDING_SHA256
    enum_values = {
        member.value for member in UnresolvedEquipmentReasonKind
    }
    mapping_proxy_type = MappingProxyType
    json_dumps = json.dumps
    json_loads = json.loads
    sha256 = hashlib.sha256

    def canonical_runtime_bytes(value: object) -> bytes:
        return json_dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def exact_contract(
        contract_id: object,
        label: str,
    ) -> dict[str, Any]:
        if type(contract_id) is not str or contract_id not in contracts:
            raise RuntimeError(f"{label} contract is absent")
        record = contracts[contract_id]
        if type(record) is not dict:
            raise RuntimeError(f"{label} contract is invalid")
        requirement = requirements.get(record.get("targetRuleId"))
        if type(requirement) is not dict:
            raise RuntimeError(f"{label} provider is absent")
        return record

    def contract_source(
        record: dict[str, Any],
        *,
        variant_selector: object = None,
    ) -> dict[str, Any]:
        requirement = requirements[record["targetRuleId"]]
        result = {
            "contractId": record["contractId"],
            "sourceId": record["sourceId"],
            "locator": record["locator"],
            "targetRuleId": record["targetRuleId"],
            "expectedBlockSha256": requirement[
                "expectedBlockSha256"
            ],
            "rowSelectionSha256": list(
                record["rowSelectionSha256"]
            ),
        }
        if variant_selector is not None:
            variants = record["variants"]
            if (
                type(variant_selector) is not str
                or variant_selector not in variants
            ):
                raise RuntimeError(
                    "runtime equipment modifier variant is absent"
                )
            result["variantSelector"] = variant_selector
            result["variantSelectionSha256"] = variants[
                variant_selector
            ]["selectionSha256"]
        return result

    entries: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for spec in _RUNTIME_CANONICAL_ENTRY_SPECS:
        if type(spec) is not tuple or len(spec) != 6:
            raise RuntimeError(
                "runtime canonical equipment entry is invalid"
            )
        (
            source_name,
            contract_id,
            binding_status,
            strike_names,
            modifier_specs,
            ammunition_contract_id,
        ) = spec
        if (
            type(source_name) is not str
            or not source_name
            or source_name
            != " ".join(source_name.strip().casefold().split())
            or source_name in seen_names
            or binding_status not in resolved_statuses
            or type(strike_names) is not tuple
            or any(
                type(name) is not str
                or not name
                or name
                != " ".join(name.strip().casefold().split())
                for name in strike_names
            )
            or len(set(strike_names)) != len(strike_names)
            or type(modifier_specs) is not tuple
        ):
            raise RuntimeError(
                "runtime canonical equipment entry changed"
            )
        seen_names.add(source_name)
        contract = exact_contract(
            contract_id,
            f"runtime equipment {source_name}",
        )
        kind = contract.get("kind")
        item_id = contract.get("itemId")
        if item_id is None and kind == "source-item":
            item_id = contract_id
        if (
            type(kind) is not str
            or kind not in {
                "ammunition",
                "armor",
                "gear",
                "shield",
                "source-item",
                "weapon",
            }
            or type(item_id) is not str
            or not item_id
        ):
            raise RuntimeError(
                f"runtime equipment target is incomplete: {source_name}"
            )
        modifiers: list[dict[str, Any]] = []
        for modifier_spec in modifier_specs:
            if (
                type(modifier_spec) is not tuple
                or len(modifier_spec) != 4
            ):
                raise RuntimeError(
                    "runtime equipment modifier is invalid"
                )
            (
                modifier_kind,
                modifier_value,
                modifier_contract_id,
                variant_selector,
            ) = modifier_spec
            if (
                type(modifier_kind) is not str
                or type(modifier_value) not in (int, str)
                or type(modifier_value) is bool
            ):
                raise RuntimeError(
                    "runtime equipment modifier changed"
                )
            modifier_contract = exact_contract(
                modifier_contract_id,
                f"runtime equipment {source_name} modifier",
            )
            modifiers.append(
                {
                    "kind": modifier_kind,
                    "value": modifier_value,
                    "contractId": modifier_contract_id,
                    "variantSelector": variant_selector,
                    "source": contract_source(
                        modifier_contract,
                        variant_selector=variant_selector,
                    ),
                }
            )
        ammunition_item_id = None
        ammunition_source = None
        if ammunition_contract_id is not None:
            ammunition_contract = exact_contract(
                ammunition_contract_id,
                f"runtime equipment {source_name} ammunition",
            )
            if (
                ammunition_contract.get("kind") != "ammunition"
                or type(ammunition_contract.get("itemId")) is not str
            ):
                raise RuntimeError(
                    "runtime equipment ammunition target changed"
                )
            ammunition_item_id = ammunition_contract["itemId"]
            ammunition_source = contract_source(
                ammunition_contract
            )
        entries.append(
            {
                "sourceName": source_name,
                "canonical": True,
                "bindingStatus": binding_status,
                "contractId": contract_id,
                "itemId": item_id,
                "kind": kind,
                "rowName": contract.get("rowName"),
                "handsToUse": contract.get("handsToUse"),
                "strikeNames": list(strike_names),
                "modifiers": modifiers,
                "ammunitionItemId": ammunition_item_id,
                "ammunitionSource": ammunition_source,
                "source": contract_source(contract),
            }
        )

    for spec in _RUNTIME_DEFERRED_ENTRY_SPECS:
        if type(spec) is not tuple or len(spec) != 4:
            raise RuntimeError(
                "runtime deferred equipment entry is invalid"
            )
        source_name, binding_status, reason_kind, message = spec
        if (
            type(source_name) is not str
            or not source_name
            or source_name
            != " ".join(source_name.strip().casefold().split())
            or source_name in seen_names
            or binding_status in resolved_statuses
            or reason_kind not in enum_values
            or type(message) is not str
            or not message
            or message != message.strip()
        ):
            raise RuntimeError(
                "runtime deferred equipment entry changed"
            )
        seen_names.add(source_name)
        entries.append(
            {
                "sourceName": source_name,
                "canonical": False,
                "bindingStatus": binding_status,
                "deferral": {
                    "kind": reason_kind,
                    "message": message,
                },
            }
        )

    entries.sort(key=lambda item: item["sourceName"])
    counts = {
        "entries": len(entries),
        "canonicalEntries": sum(
            item["canonical"] for item in entries
        ),
        "deferredEntries": sum(
            not item["canonical"] for item in entries
        ),
    }
    if counts != expected_counts:
        raise RuntimeError("runtime equipment binding counts changed")
    payload = {
        "schema": 1,
        "kind": "pf2er-runtime-equipment-bindings",
        "compiledCorpusSha256": EXPECTED_COMPILED_CORPUS_SHA256,
        "counts": counts,
        "entries": entries,
    }
    payload_bytes = canonical_runtime_bytes(payload)
    digest = sha256(payload_bytes).hexdigest()
    if (
        expected_digest != "__RUNTIME_BINDING_SHA256__"
        and digest != expected_digest
    ):
        raise RuntimeError("runtime equipment binding digest changed")

    def deep_freeze(value: object) -> object:
        value_type = type(value)
        if value_type is dict:
            return mapping_proxy_type(
                {
                    key: deep_freeze(item)
                    for key, item in value.items()
                }
            )
        if value_type is list:
            return tuple(deep_freeze(item) for item in value)
        if value is None or value_type in (bool, int, str):
            return value
        raise TypeError(
            "runtime equipment binding is not closed JSON"
        )

    def exact_payload() -> dict[str, Any]:
        if sha256(payload_bytes).hexdigest() != digest:
            raise RuntimeError(
                "runtime equipment binding identity changed"
            )
        value = json_loads(payload_bytes)
        if (
            type(value) is not dict
            or canonical_runtime_bytes(value) != payload_bytes
        ):
            raise RuntimeError(
                "runtime equipment binding payload changed"
            )
        return value

    def binding_for(source_name: object) -> MappingProxyType | None:
        if type(source_name) is not str:
            return None
        normalized = " ".join(
            source_name.strip().casefold().split()
        )
        value = exact_payload()
        match = next(
            (
                item
                for item in value["entries"]
                if item["sourceName"] == normalized
            ),
            None,
        )
        return (
            deep_freeze(match)  # type: ignore[return-value]
            if match is not None
            else None
        )

    def all_bindings() -> tuple[MappingProxyType, ...]:
        value = exact_payload()
        return tuple(
            deep_freeze(item)  # type: ignore[arg-type]
            for item in value["entries"]
        )

    return binding_for, all_bindings


def _build_equipment_entrypoints(
    raw_review: dict[str, Any],
) -> tuple[
    Callable[
        [object, object, object],
        CompiledEquipmentBindingCorpus,
    ],
    Callable[[], tuple[RuleRequirement, ...]],
]:
    """Bind all trust-bearing types, methods, hashes, and review data."""

    adapter_type = SourceAuthorityAdapter
    selection_type = VerifiedSourceSelection
    carrier_type = VerifiedSourceCarrier
    rule_type = VerifiedRuleReceipt
    requirement_type = RuleRequirement
    receipt_type = SourceReceipt
    address_type = SourceAddress
    member_step_type = RawMemberStep
    index_step_type = RawIndexStep
    span_type = TextSpan
    raw_object_type = RawSourceObject
    raw_array_type = RawSourceArray
    raw_member_type = RawSourceMember
    patch_type = CompiledEquipmentBindingCorpus
    mapping_proxy_type = MappingProxyType
    compile_error_type = EquipmentBindingCompileError
    addressability_error_type = EquipmentBindingAddressabilityError
    enum_type = UnresolvedEquipmentReasonKind

    validate_selection = SourceAuthorityAdapter.validate_selection
    validate_rule = SourceAuthorityAdapter.validate_rule
    require_shared = SourceAuthorityAdapter.require_shared_authority
    reload_selection = SourceAuthorityAdapter.reload
    resolve_selection = SourceAuthorityAdapter.resolve
    make_address = SourceAuthorityAdapter.address
    resolve_rule = SourceAuthorityAdapter.resolve_rule
    adapter_scope_get = SourceAuthorityAdapter.allowed_source_ids.fget
    adapter_snapshot_get = SourceAuthorityAdapter.snapshot.fget
    selection_receipt_get = VerifiedSourceSelection.receipt.fget
    selection_block_get = VerifiedSourceSelection.block_sha256.fget
    receipt_serialize = SourceReceipt.as_serialized
    receipt_parse = SourceReceipt.from_serialized
    requirement_serialize = RuleRequirement.as_serialized

    json_loads = json.loads
    json_dumps = json.dumps
    json_decode_error = json.JSONDecodeError
    sha256 = hashlib.sha256
    isfinite = math.isfinite
    counter_type = Counter
    block_id_fullmatch = _BLOCK_ID_RE.fullmatch
    html_unescape = html.unescape
    tag_sub = _TAG_RE.sub
    space_sub = _SPACE_RE.sub

    authority_ruleset = AUTHORITY_RULESET
    source_id = MONSTER_CORE_SOURCE_ID
    source_scope = EXPECTED_SOURCE_SCOPE
    authority_digest = EXPECTED_AUTHORITY_DIGEST
    expected_review_digest = EXPECTED_REVIEW_DIGEST
    expected_private_review_digest = EXPECTED_PRIVATE_REVIEW_SHA256
    expected_compiled_digest = EXPECTED_COMPILED_CORPUS_SHA256
    expected_counts = dict(EXPECTED_COUNTS)
    expected_shapes = dict(EXPECTED_FIELD_SHAPES)
    expected_deferrals = dict(EXPECTED_DEFERRAL_COUNTS)
    resolved_statuses = _RESOLVED_BINDING_STATUSES
    source_local_statuses = _SOURCE_LOCAL_BINDING_STATUSES
    maximum_integer = MAX_SOURCE_QUANTITY
    max_raw_depth = MAX_RAW_DEPTH
    max_raw_nodes = MAX_RAW_NODES
    max_raw_bytes = MAX_RAW_BYTES

    def canonical_bytes(value: object) -> bytes:
        return json_dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def canonical_digest(value: object) -> str:
        return sha256(canonical_bytes(value)).hexdigest()

    def exact_sha(value: object, label: str) -> str:
        if (
            type(value) is not str
            or _SHA256_RE.fullmatch(value) is None
        ):
            raise RuntimeError(f"{label} must be a lowercase SHA-256")
        return value

    def exact_text(value: object, label: str) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or "\x00" in value
        ):
            raise RuntimeError(f"{label} must be non-empty trimmed text")
        return value

    def exact_nonnegative(
        value: object,
        label: str,
    ) -> int:
        if (
            type(value) is not int
            or value < 0
            or value > maximum_integer
        ):
            raise RuntimeError(
                f"{label} must be a nonnegative signed-64-bit integer"
            )
        return value

    def exact_positive(value: object, label: str) -> int:
        result = exact_nonnegative(value, label)
        if result == 0:
            raise RuntimeError(
                f"{label} must be a positive signed-64-bit integer"
            )
        return result

    def review_path(
        value: object,
        label: str,
    ) -> tuple[RawMemberStep | RawIndexStep, ...]:
        if type(value) is not list:
            raise RuntimeError(f"{label} must be an array")
        result: list[RawMemberStep | RawIndexStep] = []
        for index, raw_step in enumerate(value):
            if type(raw_step) is not dict:
                raise RuntimeError(
                    f"{label}[{index}] must be an object"
                )
            kind = raw_step.get("kind")
            if kind == "member":
                result.append(member_step_type.from_serialized(raw_step))
            elif kind == "index":
                result.append(index_step_type.from_serialized(raw_step))
            else:
                raise RuntimeError(
                    f"{label}[{index}] kind is unsupported"
                )
        return tuple(result)

    def freeze_review(value: object) -> object:
        value_type = type(value)
        if value_type is dict:
            return mapping_proxy_type(
                {
                    key: freeze_review(item)
                    for key, item in value.items()
                }
            )
        if value_type is list:
            return tuple(freeze_review(item) for item in value)
        if value is None or value_type in (bool, int, str):
            return value
        if value_type is float and isfinite(value):
            return value
        raise RuntimeError("equipment review is not exact closed JSON")

    def thaw(value: object) -> object:
        if type(value) is mapping_proxy_type:
            return {
                key: thaw(item)
                for key, item in value.items()
            }
        if type(value) is tuple:
            return [thaw(item) for item in value]
        return value

    def validate_review(review: dict[str, Any]) -> None:
        if (
            type(review) is not dict
            or review.get("schema") != 2
            or review.get("kind")
            != "core-mc1-equipment-authority-review"
            or review.get("ruleset") != "pf2er"
            or review.get("privateReviewDigest")
            != expected_private_review_digest
        ):
            raise RuntimeError("embedded equipment review identity changed")
        authority = review.get("authority")
        if (
            type(authority) is not dict
            or authority.get("cacheSha256") != EXPECTED_CACHE_SHA256
            or authority.get("snapshotDigest") != authority_digest
            or authority.get("sourceScope") != list(source_scope)
        ):
            raise RuntimeError("embedded equipment authority changed")
        if review.get("counts") != expected_counts:
            raise RuntimeError("embedded equipment counts changed")

        requirements = review.get("providerRequirements")
        if type(requirements) is not list or len(requirements) != 28:
            raise RuntimeError("equipment provider requirements changed")
        requirement_ids: set[str] = set()
        requirement_pairs: set[tuple[str, str]] = set()
        prior_pair: tuple[str, str] | None = None
        for record in requirements:
            if type(record) is not dict:
                raise RuntimeError(
                    "equipment provider requirement must be an object"
                )
            rule_id = exact_text(record.get("ruleId"), "provider rule id")
            provider_source = exact_text(
                record.get("sourceId"),
                "provider source id",
            )
            locator = exact_text(
                record.get("locator"),
                "provider locator",
            )
            exact_sha(
                record.get("expectedBlockSha256"),
                "provider block hash",
            )
            match = _LOCATOR_RE.fullmatch(locator)
            if match is None:
                raise RuntimeError("provider locator syntax changed")
            pair_order = (provider_source, locator)
            if (
                rule_id in requirement_ids
                or (provider_source, locator) in requirement_pairs
                or (prior_pair is not None and pair_order <= prior_pair)
            ):
                raise RuntimeError(
                    "equipment provider requirements are not unique/sorted"
                )
            requirement_ids.add(rule_id)
            requirement_pairs.add((provider_source, locator))
            prior_pair = pair_order

        contracts = review.get("contracts")
        if type(contracts) is not list or len(contracts) != 140:
            raise RuntimeError("equipment source contract count changed")
        contract_ids: set[str] = set()
        for contract in contracts:
            if type(contract) is not dict:
                raise RuntimeError(
                    "equipment source contract is not an object"
                )
            contract_id = exact_text(
                contract.get("contractId"),
                "source contract id",
            )
            if contract_id in contract_ids:
                raise RuntimeError("equipment source contract duplicates")
            contract_ids.add(contract_id)
            if contract.get("targetRuleId") not in requirement_ids:
                raise RuntimeError(
                    f"source contract target is absent: {contract_id}"
                )
            row_paths = contract.get("rowPaths")
            row_hashes = contract.get("rowSelectionSha256")
            if (
                type(row_paths) is not list
                or type(row_hashes) is not list
                or len(row_paths) != len(row_hashes)
            ):
                raise RuntimeError(
                    f"source contract row receipts changed: {contract_id}"
                )
            for index, (path, row_hash) in enumerate(
                zip(row_paths, row_hashes, strict=True)
            ):
                review_path(path, f"contract {contract_id} row {index}")
                exact_sha(row_hash, f"contract {contract_id} row hash")
            selected_path = contract.get("selectedPath")
            selected_hash = contract.get("selectedSelectionSha256")
            if (selected_path is None) != (selected_hash is None):
                raise RuntimeError(
                    f"source contract selected receipt changed: {contract_id}"
                )
            if selected_path is not None:
                review_path(
                    selected_path,
                    f"contract {contract_id} selected path",
                )
                exact_sha(
                    selected_hash,
                    f"contract {contract_id} selected hash",
                )
            variants = contract.get("variants")
            if type(variants) is not dict:
                raise RuntimeError(
                    f"source contract variants changed: {contract_id}"
                )
            for selector, variant in variants.items():
                exact_text(selector, f"contract {contract_id} variant")
                if type(variant) is not dict:
                    raise RuntimeError(
                        f"contract {contract_id} variant is invalid"
                    )
                review_path(
                    variant.get("path"),
                    f"contract {contract_id} variant path",
                )
                exact_sha(
                    variant.get("selectionSha256"),
                    f"contract {contract_id} variant hash",
                )

        occurrences = review.get("occurrences")
        if type(occurrences) is not list or len(occurrences) != 318:
            raise RuntimeError("equipment occurrence count changed")
        occurrence_ids: set[str] = set()
        component_count = 0
        modifier_count = 0
        canonical_count = 0
        deferral_counts: Counter[str] = counter_type()
        carrier_ids: set[str] = set()
        indexes_by_block: dict[str, list[int]] = {}
        for occurrence in occurrences:
            if type(occurrence) is not dict:
                raise RuntimeError("equipment occurrence is not an object")
            occurrence_id = exact_text(
                occurrence.get("occurrenceId"),
                "equipment occurrence id",
            )
            match = _OCCURRENCE_ID_RE.fullmatch(occurrence_id)
            block_id = exact_text(
                occurrence.get("blockId"),
                "equipment occurrence block id",
            )
            item_index = exact_nonnegative(
                occurrence.get("itemIndex"),
                "equipment occurrence item index",
            )
            if (
                match is None
                or match.group("block") != block_id
                or int(match.group("ordinal")) != item_index
                or occurrence_id in occurrence_ids
            ):
                raise RuntimeError(
                    f"equipment occurrence identity changed: {occurrence_id}"
                )
            exact_sha(
                occurrence.get("sourceTextSha256"),
                "equipment source text hash",
            )
            occurrence_ids.add(occurrence_id)
            carrier_ids.add(block_id)
            indexes_by_block.setdefault(block_id, []).append(item_index)
            components = occurrence.get("components")
            modifiers = occurrence.get("modifiers")
            if (
                type(components) is not list
                or not components
                or type(modifiers) is not list
            ):
                raise RuntimeError(
                    "equipment occurrence collections changed: "
                    f"{occurrence_id}"
                )
            component_count += len(components)
            modifier_count += len(modifiers)
            for index, component in enumerate(components):
                if (
                    type(component) is not dict
                    or exact_nonnegative(
                        component.get("componentIndex"),
                        "equipment component index",
                    )
                    != index
                ):
                    raise RuntimeError(
                        f"equipment component order changed: {occurrence_id}"
                    )
                exact_text(
                    component.get("sourceName"),
                    "equipment component source name",
                )
                exact_positive(
                    component.get("quantity"),
                    "equipment component quantity",
                )
                binding = component.get("binding")
                if type(binding) is not dict:
                    raise RuntimeError("equipment component binding changed")
            for modifier in modifiers:
                if type(modifier) is not dict:
                    raise RuntimeError("equipment modifier changed")
                value = modifier.get("value")
                if type(value) not in (int, str) or type(value) is bool:
                    raise RuntimeError(
                        "equipment modifier bool/int grammar changed"
                    )
                binding = modifier.get("binding")
                if type(binding) is not dict:
                    raise RuntimeError("equipment modifier binding changed")
            binding_statuses: list[str] = []
            for item in (*components, *modifiers):
                binding = item["binding"]
                status = exact_text(
                    binding.get("status"),
                    "equipment binding status",
                )
                binding_statuses.append(status)
                contract_id = binding.get("contractId")
                if contract_id is not None and (
                    contract_id not in contract_ids
                    and not (
                        status == "source-local-statblock-only"
                        and contract_id == block_id
                    )
                ):
                    raise RuntimeError(
                        f"equipment binding contract is absent: {contract_id}"
                    )
                additional = binding.get(
                    "additionalAuthorityContractIds",
                    [],
                )
                if type(additional) is not list or any(
                    type(item_id) is not str
                    or (
                        item_id not in contract_ids
                        and item_id != block_id
                    )
                    for item_id in additional
                ):
                    raise RuntimeError(
                        "equipment supporting contract list changed"
                    )
            state = occurrence.get("bindingState")
            deferral = occurrence.get("deferral")
            if state == "resolved-canonical":
                canonical_count += 1
                if (
                    deferral is not None
                    or any(
                        status not in resolved_statuses
                        for status in binding_statuses
                    )
                ):
                    raise RuntimeError(
                        "canonical equipment occurrence is not fully linked"
                    )
            else:
                if (
                    type(deferral) is not dict
                    or deferral.get("kind")
                    not in {item.value for item in enum_type}
                ):
                    raise RuntimeError(
                        f"equipment deferral is invalid: {occurrence_id}"
                    )
                exact_text(
                    deferral.get("message"),
                    "equipment deferral message",
                )
                statuses = deferral.get("bindingStatuses")
                if (
                    type(statuses) is not list
                    or statuses != binding_statuses
                    or all(
                        status in resolved_statuses
                        for status in binding_statuses
                    )
                ):
                    raise RuntimeError(
                        "equipment deferral statuses changed"
                    )
                deferral_counts[deferral["kind"]] += 1
        if any(
            indexes != list(range(len(indexes)))
            for indexes in indexes_by_block.values()
        ):
            raise RuntimeError("equipment item indexes are not consecutive")
        if (
            len(carrier_ids) != 148
            or component_count != 363
            or modifier_count != 85
            or canonical_count != 284
            or dict(sorted(deferral_counts.items()))
            != expected_deferrals
        ):
            raise RuntimeError("embedded equipment occurrence totals changed")
        blockers = review.get("gateBlockers")
        if (
            type(blockers) is not list
            or len(blockers) != 19
            or not any(
                row.get("sourceId") == "core-mc1"
                and row.get("locator") == "325.1"
                and row.get("creatureName") == "Tengu Sneak"
                and row.get("itemName") == "tengu feather fan"
                for row in blockers
                if type(row) is dict
            )
        ):
            raise RuntimeError("equipment gate blocker baseline changed")
        exact_sha(
            review.get("carrierReceiptDigest"),
            "equipment carrier receipt digest",
        )
        mismatch_ids = review.get("titleMismatchBlockIds")
        if (
            type(mismatch_ids) is not list
            or len(mismatch_ids) != 19
            or len(set(mismatch_ids)) != 19
            or any(
                type(block_id) is not str or block_id not in carrier_ids
                for block_id in mismatch_ids
            )
        ):
            raise RuntimeError("equipment title mismatch review changed")

    validate_review(raw_review)
    review = freeze_review(raw_review)
    review_counts = review["counts"]
    review_occurrences = review["occurrences"]
    review_contracts = review["contracts"]
    review_blockers = review["gateBlockers"]
    expected_carrier_receipt_digest = review["carrierReceiptDigest"]
    expected_title_mismatches = tuple(review["titleMismatchBlockIds"])

    private_requirements = tuple(
        requirement_type(
            rule_id=record["ruleId"],
            source_id=record["sourceId"],
            locator=record["locator"],
            expected_block_sha256=record["expectedBlockSha256"],
        )
        for record in review["providerRequirements"]
    )
    private_requirement_serialized = tuple(
        requirement_serialize(requirement)
        for requirement in private_requirements
    )
    requirement_index = {
        requirement.rule_id: index
        for index, requirement in enumerate(private_requirements)
    }
    contract_index = {
        record["contractId"]: record for record in review_contracts
    }
    occurrence_index = {
        record["occurrenceId"]: record
        for record in review_occurrences
    }

    def clone_requirement(
        requirement: RuleRequirement,
    ) -> RuleRequirement:
        return requirement_type(
            rule_id=requirement.rule_id,
            source_id=requirement.source_id,
            locator=requirement.locator,
            carrier_path=tuple(
                member_step_type(step.raw_key, step.member_ordinal)
                if type(step) is member_step_type
                else index_step_type(step.item_ordinal)
                for step in requirement.carrier_path
            ),
            selection_path=tuple(
                member_step_type(step.raw_key, step.member_ordinal)
                if type(step) is member_step_type
                else index_step_type(step.item_ordinal)
                for step in requirement.selection_path
            ),
            span=(
                None
                if requirement.span is None
                else span_type(
                    requirement.span.start,
                    requirement.span.end,
                )
            ),
            expected_block_sha256=requirement.expected_block_sha256,
            expected_member_sha256=requirement.expected_member_sha256,
            expected_value_sha256=requirement.expected_value_sha256,
            expected_selection_sha256=(
                requirement.expected_selection_sha256
            ),
        )

    def reviewed_requirements() -> tuple[RuleRequirement, ...]:
        return tuple(
            clone_requirement(requirement)
            for requirement in private_requirements
        )

    def reject_raw_cycles_and_bounds(value: object) -> None:
        active: set[int] = set()
        nodes = 0
        source_bytes = 0

        def walk(item: object, depth: int) -> None:
            nonlocal nodes, source_bytes
            if depth > max_raw_depth:
                raise compile_error_type(
                    "equipment source exceeds its depth bound"
                )
            nodes += 1
            if nodes > max_raw_nodes:
                raise compile_error_type(
                    "equipment source exceeds its node bound"
                )
            item_type = type(item)
            if item_type is raw_object_type:
                identity = id(item)
                if identity in active:
                    raise compile_error_type(
                        "equipment source contains a cycle"
                    )
                active.add(identity)
                try:
                    if type(item.members) is not tuple:
                        raise TypeError(
                            "equipment source members must be an exact tuple"
                        )
                    for member in item.members:
                        if (
                            type(member) is not raw_member_type
                            or type(member.key) is not str
                        ):
                            raise TypeError(
                                "equipment source member must be exact"
                            )
                        source_bytes += len(member.key.encode("utf-8"))
                        if source_bytes > max_raw_bytes:
                            raise compile_error_type(
                                "equipment source exceeds its byte bound"
                            )
                        walk(member.value, depth + 1)
                finally:
                    active.remove(identity)
                return
            if item_type is raw_array_type:
                identity = id(item)
                if identity in active:
                    raise compile_error_type(
                        "equipment source contains a cycle"
                    )
                active.add(identity)
                try:
                    if type(item.items) is not tuple:
                        raise TypeError(
                            "equipment source array must be an exact tuple"
                        )
                    for child in item.items:
                        walk(child, depth + 1)
                finally:
                    active.remove(identity)
                return
            if item is None or item_type is bool:
                return
            if item_type is int:
                if item < -maximum_integer or item > maximum_integer:
                    raise compile_error_type(
                        "equipment source integer exceeds signed-64-bit bounds"
                    )
                return
            if item_type is float:
                if not isfinite(item):
                    raise compile_error_type(
                        "equipment source number must be finite"
                    )
                return
            if item_type is str:
                source_bytes += len(item.encode("utf-8"))
                if source_bytes > max_raw_bytes:
                    raise compile_error_type(
                        "equipment source exceeds its byte bound"
                    )
                return
            raise TypeError(
                "equipment source contains a non-exact value: "
                f"{item_type.__name__}"
            )

        walk(value, 0)

    def require_authority(value: object) -> SourceAuthorityAdapter:
        if type(value) is not adapter_type:
            raise TypeError(
                "equipment compilation requires an exact "
                "SourceAuthorityAdapter"
            )
        scope = adapter_scope_get(value)
        snapshot = adapter_snapshot_get(value)
        if (
            scope != source_scope
            or snapshot.ruleset != authority_ruleset
            or snapshot.digest != authority_digest
        ):
            raise addressability_error_type(
                "equipment authority scope or snapshot is not reviewed"
            )
        return value

    def require_selection_shell(
        value: object,
    ) -> VerifiedSourceSelection:
        if type(value) is not selection_type:
            raise TypeError(
                "equipment creature sources must be exact "
                "VerifiedSourceSelection values"
            )
        if (
            type(value.carrier) is not carrier_type
            or type(value.address) is not address_type
            or type(value.carrier.raw_block) is not raw_object_type
            or (
                value.raw_member is not None
                and type(value.raw_member) is not raw_member_type
            )
        ):
            raise addressability_error_type(
                "equipment source selection fields are not exact contracts"
            )
        reject_raw_cycles_and_bounds(value.carrier.raw_block)
        reject_raw_cycles_and_bounds(value.raw_value)
        reject_raw_cycles_and_bounds(value.selected_value)
        if value.raw_member is not None:
            reject_raw_cycles_and_bounds(value.raw_member.value)
        return value

    def normalized_name(value: object) -> str:
        rendered = html_unescape(tag_sub("", str(value or "")))
        rendered = rendered.replace("’", "'").replace("‘", "'")
        return space_sub(" ", rendered).strip().casefold()

    def clean_title_key(value: str) -> bool:
        return not value.startswith(
            ("^.", "!.", "~.", "$.", "%.", "&.", ".")
        )

    def source_title(
        selection: VerifiedSourceSelection,
        creature_name: str,
    ) -> str:
        target_titles = tuple(
            step.raw_key
            for step in selection.address.target_path
            if type(step) is member_step_type
            and clean_title_key(step.raw_key)
        )
        if target_titles:
            return target_titles[-1]
        carrier_titles = tuple(
            step.raw_key
            for step in selection.address.carrier_path
            if type(step) is member_step_type
            and clean_title_key(step.raw_key)
        )
        return carrier_titles[0] if carrier_titles else creature_name

    def exact_creature(
        authority: SourceAuthorityAdapter,
        value: object,
    ) -> tuple[
        VerifiedSourceSelection,
        str,
        RawSourceObject,
        tuple[tuple[int, RawSourceMember], ...],
    ]:
        source = require_selection_shell(value)
        validate_selection(authority, source)
        fresh = reload_selection(
            authority,
            selection_receipt_get(source),
        )
        address = fresh.address
        carrier = fresh.carrier
        block = carrier.raw_block
        if (
            carrier.ruleset != authority_ruleset
            or carrier.source_id != source_id
            or address.source_id != source_id
            or type(address.target_path) is not tuple
            or type(address.carrier_path) is not tuple
            or not address.carrier_path
            or type(address.carrier_path[-1]) is not member_step_type
            or address.carrier_path[-1].raw_key != "^.creature"
            or type(address.selection_path) is not tuple
            or address.selection_path
            or address.span is not None
            or type(block) is not raw_object_type
            or fresh.raw_value is not block
            or fresh.selected_value is not block
            or fresh.raw_member is not None
        ):
            raise addressability_error_type(
                "equipment source must select one whole Monster Core "
                "creature block"
            )
        names = tuple(
            member.value
            for member in block.members
            if member.key == "Name"
        )
        if (
            len(names) != 1
            or type(names[0]) is not str
            or not names[0]
            or names[0] != names[0].strip()
        ):
            raise compile_error_type(
                "equipment creature requires one exact Name member"
            )
        if address.locator == "5.3" or names[0] == "Creature Name":
            raise addressability_error_type(
                "the introduction creature example is not stable corpus data"
            )
        items = tuple(
            (ordinal, member)
            for ordinal, member in enumerate(block.members)
            if member.key == "Items"
        )
        if len(items) > 1:
            raise compile_error_type(
                f"equipment creature has duplicate Items: {names[0]}"
            )
        return (
            fresh,
            names[0],
            block,
            items,
        )

    def validate_providers(
        authority: SourceAuthorityAdapter,
        anchor: VerifiedSourceSelection,
        providers: object,
    ) -> tuple[VerifiedRuleReceipt, ...]:
        if type(providers) is not tuple:
            raise TypeError(
                "equipment provider rules must be an exact ordered tuple"
            )
        if len(providers) != len(private_requirements):
            raise addressability_error_type(
                "equipment provider rule count changed"
            )
        if any(type(provider) is not rule_type for provider in providers):
            raise TypeError(
                "equipment providers must contain exact VerifiedRuleReceipt "
                "values"
            )
        for provider in providers:
            require_selection_shell(provider.selection)
        require_shared(authority, anchor, providers)
        fresh: list[VerifiedRuleReceipt] = []
        provider_rows = zip(
            providers,
            private_requirements,
            private_requirement_serialized,
            strict=True,
        )
        for index, (
            provider,
            requirement,
            serialized_requirement,
        ) in enumerate(
            provider_rows
        ):
            validate_rule(authority, provider)
            if (
                provider.rule_id != requirement.rule_id
                or type(provider.requirement) is not requirement_type
                or requirement_serialize(provider.requirement)
                != serialized_requirement
                or type(provider.receipt) is not receipt_type
                or receipt_serialize(provider.receipt)
                != receipt_serialize(
                    selection_receipt_get(provider.selection)
                )
            ):
                raise addressability_error_type(
                    "equipment provider order or reviewed identity changed "
                    f"at {index}"
                )
            fresh.append(resolve_rule(authority, requirement))
        return tuple(fresh)

    def receipt_json(
        selection: VerifiedSourceSelection,
    ) -> dict[str, Any]:
        return receipt_serialize(selection_receipt_get(selection))

    def provider_json(
        provider: VerifiedRuleReceipt,
    ) -> dict[str, Any]:
        return {
            "ruleId": provider.rule_id,
            "requirement": requirement_serialize(provider.requirement),
            "source": receipt_serialize(provider.receipt),
        }

    def selection_at(
        authority: SourceAuthorityAdapter,
        *,
        provider: VerifiedRuleReceipt,
        path: object,
        expected_sha: object,
        label: str,
    ) -> VerifiedSourceSelection:
        selection_path = tuple(
            member_step_type(step.raw_key, step.member_ordinal)
            if type(step) is member_step_type
            else index_step_type(step.item_ordinal)
            for step in review_path(thaw(path), label)
        )
        selection = resolve_selection(
            authority,
            make_address(
                authority,
                source_id=provider.requirement.source_id,
                locator=provider.requirement.locator,
                selection_path=selection_path,
            ),
        )
        if selection.selection_sha256 != expected_sha:
            raise addressability_error_type(
                f"{label} no longer matches its reviewed hash"
            )
        validate_selection(authority, selection)
        return selection

    def compile_contracts(
        authority: SourceAuthorityAdapter,
        providers: tuple[VerifiedRuleReceipt, ...],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        provider_by_id = {
            provider.rule_id: provider for provider in providers
        }
        serialized_contracts: dict[str, dict[str, Any]] = {}
        runtime: dict[str, Any] = {}
        for record in review_contracts:
            contract_id = record["contractId"]
            provider = provider_by_id[record["targetRuleId"]]
            rows = tuple(
                selection_at(
                    authority,
                    provider=provider,
                    path=path,
                    expected_sha=row_hash,
                    label=f"equipment contract {contract_id} row {index}",
                )
                for index, (path, row_hash) in enumerate(
                    zip(
                        record["rowPaths"],
                        record["rowSelectionSha256"],
                        strict=True,
                    )
                )
            )
            selected = None
            if record["selectedPath"] is not None:
                selected = selection_at(
                    authority,
                    provider=provider,
                    path=record["selectedPath"],
                    expected_sha=record["selectedSelectionSha256"],
                    label=f"equipment contract {contract_id} selection",
                )
            variants: dict[str, VerifiedSourceSelection] = {}
            for selector, variant in record["variants"].items():
                variants[selector] = selection_at(
                    authority,
                    provider=provider,
                    path=variant["path"],
                    expected_sha=variant["selectionSha256"],
                    label=(
                        f"equipment contract {contract_id} variant "
                        f"{selector}"
                    ),
                )
            serialized = {
                "contractId": contract_id,
                "kind": record["kind"],
                "itemId": record["itemId"],
                "rowName": record["rowName"],
                "handsToUse": record["handsToUse"],
                "targetRule": provider_json(provider),
                "rowSources": [receipt_json(row) for row in rows],
                "selectedSource": (
                    receipt_json(selected)
                    if selected is not None
                    else None
                ),
                "variantSources": {
                    selector: receipt_json(selection)
                    for selector, selection in variants.items()
                },
            }
            serialized_contracts[contract_id] = serialized
            runtime[contract_id] = (
                record,
                provider,
                rows,
                selected,
                variants,
                serialized,
            )
        return serialized_contracts, runtime

    def source_link(
        *,
        role: str,
        binding: MappingProxyType,
        block_id: str,
        component_index: int | None,
        modifier_index: int | None,
        creature_source: VerifiedSourceSelection,
        occurrence_source: VerifiedSourceSelection,
        contracts: dict[str, Any],
    ) -> dict[str, Any] | None:
        status = binding["status"]
        contract_id = binding.get("contractId")
        if contract_id is None:
            if status in resolved_statuses:
                raise compile_error_type(
                    f"resolved {role} binding omits its contract"
                )
            return None
        if contract_id in contracts:
            (
                record,
                provider,
                rows,
                selected,
                variants,
                _serialized,
            ) = contracts[contract_id]
            for field_name in ("kind", "itemId"):
                if (
                    binding.get(field_name) is not None
                    and binding[field_name] != record[field_name]
                ):
                    raise compile_error_type(
                        f"{role} binding {field_name} disagrees: "
                        f"{contract_id}"
                    )
            binding_row = (
                binding.get("rowName")
                or binding.get("logicalRowName")
            )
            if (
                binding_row is not None
                and binding_row != record["rowName"]
            ):
                raise compile_error_type(
                    f"{role} binding row disagrees: {contract_id}"
                )
            selector = binding.get("variantSelector")
            variant = None
            if selector is not None:
                variant = variants.get(selector)
                if variant is None:
                    raise compile_error_type(
                        f"{role} binding variant is absent: {contract_id}"
                    )
            elif status in resolved_statuses and variants:
                raise compile_error_type(
                    f"resolved {role} binding omits its variant: "
                    f"{contract_id}"
                )
            supporting = []
            for supporting_id in binding.get(
                "additionalAuthorityContractIds",
                (),
            ):
                if supporting_id == block_id:
                    supporting.append(
                        {
                            "kind": "creature-local-statblock",
                            "contractId": supporting_id,
                            "source": receipt_json(creature_source),
                        }
                    )
                else:
                    supporting_record = contracts[supporting_id]
                    supporting.append(
                        {
                            "kind": "reviewed-rule",
                            "contractId": supporting_id,
                            "rule": provider_json(supporting_record[1]),
                        }
                    )
            target_rule = provider_json(provider)
            row_sources = [receipt_json(row) for row in rows]
            selected_source = (
                receipt_json(selected) if selected is not None else None
            )
            variant_source = (
                receipt_json(variant) if variant is not None else None
            )
            source_kind = "reviewed-source-contract"
        elif (
            status == "source-local-statblock-only"
            and contract_id == block_id
        ):
            target_rule = None
            row_sources = []
            selected_source = receipt_json(creature_source)
            variant_source = None
            supporting = []
            source_kind = "creature-local-statblock"
        else:
            raise compile_error_type(
                f"{role} binding contract is absent: {contract_id}"
            )
        result: dict[str, Any] = {
            "role": role,
            "bindingStatus": status,
            "contractId": contract_id,
            "canonical": status in resolved_statuses,
            "sourceKind": source_kind,
            "occurrenceSource": receipt_json(occurrence_source),
            "targetRule": target_rule,
            "rowSources": row_sources,
            "selectedSource": selected_source,
            "variantSource": variant_source,
            "supportingRules": supporting,
        }
        if component_index is not None:
            result["componentIndex"] = component_index
        if modifier_index is not None:
            result["modifierIndex"] = modifier_index
        return result

    def occurrence_source(
        authority: SourceAuthorityAdapter,
        creature: VerifiedSourceSelection,
        *,
        item_member_ordinal: int,
        item_index: int,
        shape: str,
    ) -> VerifiedSourceSelection:
        path: tuple[RawMemberStep | RawIndexStep, ...] = (
            member_step_type("Items", item_member_ordinal),
        )
        if shape == "list":
            path = (*path, index_step_type(item_index))
        return resolve_selection(
            authority,
            make_address(
                authority,
                source_id=creature.address.source_id,
                locator=creature.address.locator,
                carrier_path=creature.address.carrier_path,
                selection_path=path,
            ),
        )

    def compile_occurrence(
        authority: SourceAuthorityAdapter,
        *,
        spec: MappingProxyType,
        creature_record: dict[str, Any],
        creature_source: VerifiedSourceSelection,
        item_member_ordinal: int,
        shape: str,
        contracts: dict[str, Any],
    ) -> dict[str, Any]:
        item_index = spec["itemIndex"]
        selected = occurrence_source(
            authority,
            creature_source,
            item_member_ordinal=item_member_ordinal,
            item_index=item_index,
            shape=shape,
        )
        validate_selection(authority, selected)
        if (
            type(selected.raw_value) is not str
            or type(selected.selected_value) is not str
            or selected.raw_value != selected.selected_value
        ):
            raise compile_error_type(
                f"equipment Items entry is not exact text: "
                f"{spec['occurrenceId']}"
            )
        source_text = selected.selected_value
        if (
            sha256(source_text.encode("utf-8")).hexdigest()
            != spec["sourceTextSha256"]
        ):
            raise addressability_error_type(
                f"equipment Items text changed: {spec['occurrenceId']}"
            )
        components = thaw(spec["components"])
        modifiers = thaw(spec["modifiers"])
        links: list[dict[str, Any]] = []
        for index, raw_component in enumerate(spec["components"]):
            link = source_link(
                role="component",
                binding=raw_component["binding"],
                block_id=spec["blockId"],
                component_index=index,
                modifier_index=None,
                creature_source=creature_source,
                occurrence_source=selected,
                contracts=contracts,
            )
            if link is not None:
                links.append(link)
        for index, raw_modifier in enumerate(spec["modifiers"]):
            link = source_link(
                role="modifier",
                binding=raw_modifier["binding"],
                block_id=spec["blockId"],
                component_index=None,
                modifier_index=index,
                creature_source=creature_source,
                occurrence_source=selected,
                contracts=contracts,
            )
            if link is not None:
                links.append(link)
        canonical = spec["bindingState"] == "resolved-canonical"
        if canonical and (
            not links or any(not link["canonical"] for link in links)
        ):
            raise compile_error_type(
                f"canonical equipment links changed: {spec['occurrenceId']}"
            )
        deferral = thaw(spec["deferral"])
        if deferral is not None:
            deferral["source"] = receipt_json(selected)
            deferral["kind"] = enum_type(deferral["kind"]).value
        return {
            "occurrenceId": spec["occurrenceId"],
            "blockId": spec["blockId"],
            "sourceId": creature_record["sourceId"],
            "locator": creature_record["locator"],
            "creatureName": creature_record["creatureName"],
            "sourceTitle": creature_record["sourceTitle"],
            "itemIndex": item_index,
            "sourceText": source_text,
            "sourceTextSha256": spec["sourceTextSha256"],
            "bindingState": spec["bindingState"],
            "canonical": canonical,
            "source": receipt_json(selected),
            "creatureSource": receipt_json(creature_source),
            "creatureStrikeNames": list(spec["creatureStrikeNames"]),
            "components": components,
            "modifiers": modifiers,
            "sourceLinks": links,
            "deferral": deferral,
        }

    def deep_freeze_projection(value: object) -> object:
        value_type = type(value)
        if value_type is dict:
            return mapping_proxy_type(
                {
                    key: deep_freeze_projection(item)
                    for key, item in value.items()
                }
            )
        if value_type is list:
            return tuple(deep_freeze_projection(item) for item in value)
        if value is None or value_type in (bool, int, str):
            return value
        if value_type is float and isfinite(value):
            return value
        raise TypeError("equipment public projection is not closed JSON")

    def parse_payload(patch: object) -> dict[str, Any]:
        if type(patch) is not patch_type:
            raise TypeError(
                "equipment projection requires exact "
                "CompiledEquipmentBindingCorpus"
            )
        authority = require_authority(patch._authority)
        anchor = require_selection_shell(patch._anchor)
        validate_selection(authority, anchor)
        if (
            type(patch._payload) is not bytes
            or type(patch._digest) is not str
            or sha256(patch._payload).hexdigest() != patch._digest
        ):
            raise addressability_error_type(
                "compiled equipment payload identity changed"
            )
        try:
            value = json_loads(patch._payload)
        except (TypeError, json_decode_error) as failure:
            raise compile_error_type(
                "compiled equipment payload is invalid"
            ) from failure
        if (
            type(value) is not dict
            or canonical_bytes(value) != patch._payload
            or value.get("authority", {}).get("digest")
            != authority_digest
            or value.get("reviewDigest") != expected_review_digest
            or value.get("privateReviewDigest")
            != expected_private_review_digest
        ):
            raise addressability_error_type(
                "compiled equipment payload contract changed"
            )
        if (
            expected_compiled_digest != "__COMPILED_DIGEST__"
            and patch._digest != expected_compiled_digest
        ):
            raise addressability_error_type(
                "compiled equipment digest is not the frozen corpus"
            )
        return value

    def project(patch: object, mode: str) -> object:
        value = parse_payload(patch)
        if mode == "digest":
            return patch._digest
        if mode == "review-digest":
            return value["reviewDigest"]
        if mode == "private-review-digest":
            return value["privateReviewDigest"]
        if mode == "authority-digest":
            return value["authority"]["digest"]
        if mode == "counts":
            return deep_freeze_projection(value["counts"])
        if mode == "creatures":
            return tuple(
                deep_freeze_projection(item)
                for item in value["creatures"]
            )
        if mode == "occurrences":
            return tuple(
                deep_freeze_projection(item)
                for item in value["occurrences"]
            )
        if mode == "occurrence-by-id":
            return mapping_proxy_type(
                {
                    item["occurrenceId"]: deep_freeze_projection(item)
                    for item in value["occurrences"]
                }
            )
        if mode == "canonical-occurrences":
            return tuple(
                deep_freeze_projection(item)
                for item in value["occurrences"]
                if item["canonical"]
            )
        if mode == "unresolved-occurrences":
            return tuple(
                deep_freeze_projection(item)
                for item in value["occurrences"]
                if item["deferral"] is not None
            )
        if mode == "source-contracts":
            return deep_freeze_projection(value["sourceContracts"])
        if mode == "gate-blockers":
            return tuple(
                deep_freeze_projection(item)
                for item in value["gateBlockers"]
            )
        if mode == "creature-sources":
            return tuple(
                reload_selection(
                    patch._authority,
                    receipt_parse(item["source"]),
                )
                for item in value["creatures"]
            )
        if mode == "provider-rules":
            return tuple(
                resolve_rule(patch._authority, requirement)
                for requirement in private_requirements
            )
        if mode != "serialized":
            raise ValueError("unknown equipment corpus projection")
        return {**value, "digest": patch._digest}

    def new_patch(
        authority: SourceAuthorityAdapter,
        anchor: VerifiedSourceSelection,
        payload: dict[str, Any],
    ) -> CompiledEquipmentBindingCorpus:
        payload_bytes = canonical_bytes(payload)
        digest_value = sha256(payload_bytes).hexdigest()
        result = object.__new__(patch_type)
        object.__setattr__(result, "_authority", authority)
        object.__setattr__(result, "_anchor", anchor)
        object.__setattr__(result, "_payload", payload_bytes)
        object.__setattr__(result, "_digest", digest_value)
        object.__setattr__(result, "_project", project)
        return result

    def compile_entry(
        authority: object,
        creature_sources: object,
        provider_rules: object,
        /,
    ) -> CompiledEquipmentBindingCorpus:
        verified_authority = require_authority(authority)
        if type(creature_sources) is not tuple:
            raise TypeError(
                "equipment creature sources must be an exact ordered tuple"
            )
        if len(creature_sources) != 445:
            raise addressability_error_type(
                "equipment corpus requires exactly 445 stable creatures"
            )
        if any(
            type(source) is not selection_type
            for source in creature_sources
        ):
            raise TypeError(
                "equipment creature sources must contain exact "
                "VerifiedSourceSelection values"
            )
        if type(provider_rules) is not tuple:
            raise TypeError(
                "equipment provider rules must be an exact ordered tuple"
            )
        if len(provider_rules) != len(private_requirements):
            raise addressability_error_type(
                "equipment provider rule count changed"
            )
        if any(
            type(provider) is not rule_type
            for provider in provider_rules
        ):
            raise TypeError(
                "equipment providers must contain exact "
                "VerifiedRuleReceipt values"
            )

        first_creature = exact_creature(
            verified_authority,
            creature_sources[0],
        )
        providers = validate_providers(
            verified_authority,
            first_creature[0],
            provider_rules,
        )
        reviewed_creatures = (
            first_creature,
            *(
                exact_creature(verified_authority, source)
                for source in creature_sources[1:]
            ),
        )
        fresh_sources = tuple(item[0] for item in reviewed_creatures)
        receipt_values = [
            receipt_json(source) for source in fresh_sources
        ]
        if (
            canonical_digest(receipt_values)
            != expected_carrier_receipt_digest
        ):
            raise addressability_error_type(
                "equipment creature carrier corpus changed"
            )
        if len({source.block_sha256 for source in fresh_sources}) != 445:
            raise addressability_error_type(
                "equipment creature carriers are duplicated"
            )

        serialized_contracts, runtime_contracts = compile_contracts(
            verified_authority,
            providers,
        )

        section_ordinals: Counter[str] = counter_type()
        creature_records: list[dict[str, Any]] = []
        compiled_occurrences: list[dict[str, Any]] = []
        shape_counts: Counter[str] = counter_type()
        mismatch_ids: list[str] = []
        carrier_count = 0
        grouped_count = 0
        for corpus_index, (
            source,
            creature_name,
            _block,
            items,
        ) in enumerate(reviewed_creatures):
            section_id = source.address.section_id
            if (
                type(section_id) is not str
                or not section_id.startswith("core-mc1:")
            ):
                raise addressability_error_type(
                    "equipment creature section identity changed"
                )
            section_slug = section_id.removeprefix("core-mc1:")
            ordinal = section_ordinals[section_slug]
            section_ordinals[section_slug] += 1
            block_id = (
                f"core-mc1/{section_slug}#creature-{ordinal:03d}"
            )
            if block_id_fullmatch(block_id) is None:
                raise addressability_error_type(
                    f"equipment creature block identity is invalid: {block_id}"
                )
            title = source_title(source, creature_name)
            grouped = (
                block_id == "core-mc1/grim-reaper#creature-000"
                and source.address.locator == "184.1"
                and tuple(
                    (step.raw_key, step.member_ordinal)
                    for step in source.address.carrier_path
                    if type(step) is member_step_type
                )
                == (
                    ("Grim Reaper", 1),
                    ("Grim Reaper", 2),
                    ("^.creature", 3),
                )
            )
            if block_id == "core-mc1/grim-reaper#creature-000" and not grouped:
                raise addressability_error_type(
                    "the grouped Grim Reaper carrier path changed"
                )
            grouped_count += grouped
            record: dict[str, Any] = {
                "corpusIndex": corpus_index,
                "blockId": block_id,
                "sourceId": source.address.source_id,
                "locator": source.address.locator,
                "sectionId": section_id,
                "creatureName": creature_name,
                "sourceTitle": title,
                "titleMatchesName": title == creature_name,
                "groupedTarget": grouped,
                "hasItems": bool(items),
                "itemCount": 0,
                "source": receipt_json(source),
            }
            if items:
                carrier_count += 1
                item_ordinal, item_member = items[0]
                value = item_member.value
                if type(value) is str:
                    shape = "string"
                    item_values = (value,)
                elif type(value) is raw_array_type:
                    if any(type(item) is not str for item in value.items):
                        raise compile_error_type(
                            f"equipment Items array is not textual: {block_id}"
                        )
                    shape = "list"
                    item_values = value.items
                else:
                    raise compile_error_type(
                        f"equipment Items shape is unsupported: {block_id}"
                    )
                if not item_values:
                    raise compile_error_type(
                        f"equipment Items is empty: {block_id}"
                    )
                shape_counts[shape] += 1
                record["itemCount"] = len(item_values)
                if title != creature_name:
                    mismatch_ids.append(block_id)
                for item_index, source_text in enumerate(item_values):
                    occurrence_id = (
                        f"{block_id}#items-{item_index:03d}"
                    )
                    spec = occurrence_index.get(occurrence_id)
                    if spec is None or spec["blockId"] != block_id:
                        raise addressability_error_type(
                            "equipment occurrence review is absent: "
                            f"{occurrence_id}"
                        )
                    compiled_occurrences.append(
                        compile_occurrence(
                            verified_authority,
                            spec=spec,
                            creature_record=record,
                            creature_source=source,
                            item_member_ordinal=item_ordinal,
                            shape=shape,
                            contracts=runtime_contracts,
                        )
                    )
            creature_records.append(record)

        if (
            grouped_count != 1
            or carrier_count != 148
            or dict(shape_counts) != expected_shapes
            or tuple(mismatch_ids) != expected_title_mismatches
            or len(compiled_occurrences) != 318
            or {
                item["occurrenceId"] for item in compiled_occurrences
            }
            != set(occurrence_index)
        ):
            raise addressability_error_type(
                "equipment carrier/occurrence census changed"
            )
        deferral_counts = counter_type(
            item["deferral"]["kind"]
            for item in compiled_occurrences
            if item["deferral"] is not None
        )
        counts = {
            "stableCreatures": len(creature_records),
            "equipmentCarriers": carrier_count,
            "occurrences": len(compiled_occurrences),
            "components": sum(
                len(item["components"])
                for item in compiled_occurrences
            ),
            "modifiers": sum(
                len(item["modifiers"])
                for item in compiled_occurrences
            ),
            "canonicalOccurrences": sum(
                item["canonical"] for item in compiled_occurrences
            ),
            "deferredOccurrences": sum(
                item["deferral"] is not None
                for item in compiled_occurrences
            ),
            "equipmentTitleMismatches": len(mismatch_ids),
            "sourceContracts": len(serialized_contracts),
            "providerTargets": len(providers),
            "gateBlockers": len(review_blockers),
            "gatesUnlocked": 0,
            "groupedTargets": grouped_count,
        }
        if (
            counts != expected_counts
            or dict(sorted(deferral_counts.items()))
            != expected_deferrals
        ):
            raise compile_error_type(
                "compiled equipment corpus totals changed"
            )
        payload = {
            "schema": 2,
            "kind": "pf2er-equipment-binding-corpus",
            "status": "compile-link-only",
            "runtimeSupported": False,
            "authority": {
                "ruleset": authority_ruleset,
                "digest": authority_digest,
                "sourceScope": list(source_scope),
            },
            "reviewDigest": expected_review_digest,
            "privateReviewDigest": expected_private_review_digest,
            "counts": counts,
            "providerRules": [
                provider_json(provider) for provider in providers
            ],
            "sourceContracts": serialized_contracts,
            "creatures": creature_records,
            "occurrences": compiled_occurrences,
            "gateBlockers": thaw(review_blockers),
            "gatesUnlocked": 0,
        }
        patch = new_patch(
            verified_authority,
            fresh_sources[0],
            payload,
        )
        if (
            expected_compiled_digest != "__COMPILED_DIGEST__"
            and patch.digest != expected_compiled_digest
        ):
            raise addressability_error_type(
                "compiled equipment corpus digest changed"
            )
        return patch

    return compile_entry, reviewed_requirements


_RAW_PRIVATE_REVIEW = _decode_private_review()
EQUIPMENT_RULE_REQUIREMENTS = _public_rule_requirements(
    _RAW_PRIVATE_REVIEW
)
(
    runtime_equipment_binding,
    runtime_equipment_bindings,
) = _build_runtime_binding_entrypoints(_RAW_PRIVATE_REVIEW)
(
    compile_equipment_bindings,
    equipment_rule_requirements,
) = _build_equipment_entrypoints(_RAW_PRIVATE_REVIEW)
del _RAW_PRIVATE_REVIEW


__all__ = [
    "COMPILER_ID",
    "CompiledEquipmentBindingCorpus",
    "EQUIPMENT_RULE_REQUIREMENTS",
    "EXPECTED_AUTHORITY_DIGEST",
    "EXPECTED_CACHE_SHA256",
    "EXPECTED_COMPILED_CORPUS_SHA256",
    "EXPECTED_COUNTS",
    "EXPECTED_PRIVATE_REVIEW_SHA256",
    "EXPECTED_REVIEW_DIGEST",
    "EXPECTED_REVIEWED_PACKET_SHA256",
    "EXPECTED_RUNTIME_BINDING_COUNTS",
    "EXPECTED_RUNTIME_BINDING_SHA256",
    "FAMILY_ID",
    "MAX_SOURCE_QUANTITY",
    "MONSTER_CORE_SOURCE_ID",
    "REGISTRY_STATUS",
    "EquipmentBindingAddressabilityError",
    "EquipmentBindingCompileError",
    "UnresolvedEquipmentReasonKind",
    "compile_equipment_bindings",
    "equipment_rule_requirements",
    "runtime_equipment_binding",
    "runtime_equipment_bindings",
]

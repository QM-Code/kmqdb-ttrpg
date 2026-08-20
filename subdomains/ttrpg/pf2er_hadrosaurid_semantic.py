"""Authenticated, source-free Hadrosaurid carrier semantics.

This module owns the bounded Monster Core 1 carrier leaf used by the first
Trample pilot.  The existing PF2ER creature compiler and the separately
authenticated Trample compiler/linker run only while constructing the leaf.
Their source-shaped outputs are retained in TTRPG-private evidence; the
public package is rebuilt field by field and contains no Library or cache
coordinate.
"""

from __future__ import annotations

from copy import deepcopy
import hmac
import re

from .pf2er_semantic import (
    PF2ER_MONSTER_CORE_ONE_BOOK_ID,
    PF2ER_RULESET_ID,
    build_pf2er_semantic_compiler_set,
)
from .pf2er_compiler.mechanics.source_authority import (
    RawMemberStep,
    SourceAuthorityAdapter,
)
from .pf2er_compiler.mechanics.trample import (
    COMPILER_ID as TRAMPLE_COMPILER_ID,
    FAMILY_ID as TRAMPLE_FAMILY_ID,
    MECHANIC_TYPE as TRAMPLE_MECHANIC_TYPE,
    TRAMPLE_RULE_REQUIREMENTS,
    TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS,
    compile_trample,
    link_trample_strike,
)
from .semantic_compiler import SemanticCompilerSet
from .semantic_evidence import (
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
    canonical_digest,
)
from .semantic_package_builder import SourceCreatureTarget
from .semantic_packages import (
    CapabilityRequirement,
    ProviderCarrierRelationship,
    SemanticPackage,
    build_semantic_entity,
    build_semantic_package,
    public_definition_acquisition_paths,
    validate_public_semantic_definition,
)


PF2ER_HADROSAURID_ENTITY_ID = "pf2er:hadrosaurid"
PF2ER_HADROSAURID_SOURCE_ID = "core-mc1"
PF2ER_HADROSAURID_LOCATOR = "98.2"
PF2ER_HADROSAURID_CARRIER_MEMBER_ORDINAL = 8
PF2ER_HADROSAURID_TRAMPLE_MEMBER_ORDINAL = 22

PF2ER_HADROSAURID_PACKAGE_ID = (
    "ttrpg:pf2er-monster-core-one-hadrosaurid-trample"
)
PF2ER_HADROSAURID_PACKAGE_VERSION = "1.0.0"
PF2ER_HADROSAURID_COMPILER_ID = (
    "ttrpg:pf2er-hadrosaurid-semantic-compiler"
)
PF2ER_HADROSAURID_COMPILER_VERSION = "1.0.0"
PF2ER_HADROSAURID_PROJECTION_ID = (
    "ttrpg:pf2er-hadrosaurid-definition"
)
PF2ER_HADROSAURID_PROJECTION_VERSION = "1.0.0"
PF2ER_TRAMPLE_PROJECTION_ID = "ttrpg:pf2er-trample-ability-definition"
PF2ER_TRAMPLE_PROJECTION_VERSION = "1.0.0"
PF2ER_HADROSAURID_EVIDENCE_AUTHORITY_ID = (
    "ttrpg:pf2er-semantic-evidence"
)

PF2ER_TRAMPLE_ENTITY_ID = "pf2er:trample"
PF2ER_TRAMPLE_CAPABILITY = CapabilityRequirement(
    "gladiator:pf2er-trample-activity",
    "1.0.0",
)
# Retain the carrier-qualified spelling as a descriptive import for the
# composition layer; the requirement itself belongs to the Trample entity.
PF2ER_HADROSAURID_TRAMPLE_CAPABILITY = PF2ER_TRAMPLE_CAPABILITY
PF2ER_HADROSAURID_SPRINT_CAPABILITY = CapabilityRequirement(
    "gladiator:pf2er-hadrosaurid-sprint-activity",
    "1.0.0",
)
PF2ER_HADROSAURID_TRAMPLE_RELATIONSHIP = ProviderCarrierRelationship(
    "ttrpg:hadrosaurid-trample-carrier",
    PF2ER_TRAMPLE_ENTITY_ID,
    PF2ER_HADROSAURID_ENTITY_ID,
)
PF2ER_HADROSAURID_TARGET = SourceCreatureTarget(
    PF2ER_HADROSAURID_ENTITY_ID,
    PF2ER_HADROSAURID_SOURCE_ID,
    PF2ER_HADROSAURID_LOCATOR,
)

PF2ER_HADROSAURID_PRESENTATION_DEFERRALS = (
    "presentation-asset-not-published",
)
PF2ER_HADROSAURID_RUNTIME_DEFERRALS = (
    "scent-observer-relative-detection",
    "mixed-footprint-light-level-ruling",
    "other-effect-created-sight-obscurers",
)
PF2ER_HADROSAURID_COMPLETENESS_DEFERRALS = tuple(
    TRAMPLE_RUNTIME_COMPLETENESS_DEFERRALS
)

# These are the current production outputs of the authenticated compilers.
# A source, provider-rule, compiler-selection, or link change is a review
# event, not an implicit republish of the carrier.
PF2ER_HADROSAURID_AUTHORITY_DIGEST = (
    "686577b44c5a208e37dbb07a0fe1fca80aea283fd9fd9d67be640d43a93685ef"
)
PF2ER_HADROSAURID_UPSTREAM_COMPILER_DIGEST = (
    "766ab7b26f4d463ed17c7bd62a3328f02faf6e3c947d89847401d96d3372f340"
)
PF2ER_HADROSAURID_RAW_CREATURE_DIGEST = (
    "fec8a26ec538ce128c6022eea549ec6328ca9ea7653c9e0b01427cdd8f0dbb1f"
)
PF2ER_HADROSAURID_LINKED_TRAMPLE_DIGEST = (
    "28376d1aae515310be93692d41abf5544094d2dd8dcc9b3b5df6f8bb5bace258"
)
PF2ER_HADROSAURID_RAW_DEFINITION_DIGEST = (
    "01b1721c134e5c1da7f8e65ab6f840867d719af76f9c2b8441cfffb44ef4ca45"
)
_TRAMPLE_CONTRACT_PROOF_DIGEST = (
    "7fd5ab4ff752d1fce8ba0bb59dbf18bb07086a178d93d641c58cad75bf0037c3"
)

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_AUTHORITY_SCOPE = (
    "core-gmc",
    "core-mc1",
    "core-pc1",
)

_HADROSAURID_PROJECTION_MANIFEST = {
    "schema": 1,
    "packageId": PF2ER_HADROSAURID_PACKAGE_ID,
    "packageVersion": PF2ER_HADROSAURID_PACKAGE_VERSION,
    "projectionId": PF2ER_HADROSAURID_PROJECTION_ID,
    "projectionVersion": PF2ER_HADROSAURID_PROJECTION_VERSION,
    "definitionSchema": 2,
    "entityKind": "ttrpg:creature",
    "selectedEntityIds": [PF2ER_HADROSAURID_ENTITY_ID],
    "assetPolicy": "zero-references-with-explicit-deferral",
}
PF2ER_HADROSAURID_PROJECTION_DIGEST = canonical_digest(
    _HADROSAURID_PROJECTION_MANIFEST,
    "Hadrosaurid projection manifest",
)
_TRAMPLE_PROJECTION_MANIFEST = {
    "schema": 1,
    "packageId": PF2ER_HADROSAURID_PACKAGE_ID,
    "packageVersion": PF2ER_HADROSAURID_PACKAGE_VERSION,
    "projectionId": PF2ER_TRAMPLE_PROJECTION_ID,
    "projectionVersion": PF2ER_TRAMPLE_PROJECTION_VERSION,
    "definitionSchema": 1,
    "entityKind": "ttrpg:creature-ability",
    "selectedEntityIds": [PF2ER_TRAMPLE_ENTITY_ID],
}
PF2ER_TRAMPLE_PROJECTION_DIGEST = canonical_digest(
    _TRAMPLE_PROJECTION_MANIFEST,
    "Trample ability projection manifest",
)

_COMPILER_MANIFEST = {
    "schema": 1,
    "compilerId": PF2ER_HADROSAURID_COMPILER_ID,
    "compilerVersion": PF2ER_HADROSAURID_COMPILER_VERSION,
    "rulesetId": PF2ER_RULESET_ID,
    "bookId": PF2ER_MONSTER_CORE_ONE_BOOK_ID,
    "selectedEntityIds": [
        PF2ER_HADROSAURID_ENTITY_ID,
        PF2ER_TRAMPLE_ENTITY_ID,
    ],
    "carrier": {
        "sourceId": PF2ER_HADROSAURID_SOURCE_ID,
        "locator": PF2ER_HADROSAURID_LOCATOR,
        "rawKey": "^.creature",
        "memberOrdinal": PF2ER_HADROSAURID_CARRIER_MEMBER_ORDINAL,
        "trampleMemberOrdinal": PF2ER_HADROSAURID_TRAMPLE_MEMBER_ORDINAL,
    },
    "creatureCompiler": {
        "digest": PF2ER_HADROSAURID_UPSTREAM_COMPILER_DIGEST,
    },
    "trampleCompiler": {
        "compilerId": TRAMPLE_COMPILER_ID,
        "familyId": TRAMPLE_FAMILY_ID,
        "mechanicType": TRAMPLE_MECHANIC_TYPE,
        "contractProofDigest": _TRAMPLE_CONTRACT_PROOF_DIGEST,
    },
    "reviewedOutputs": {
        "rawCreatureDigest": PF2ER_HADROSAURID_RAW_CREATURE_DIGEST,
        "linkedTrampleDigest": PF2ER_HADROSAURID_LINKED_TRAMPLE_DIGEST,
        "rawDefinitionDigest": PF2ER_HADROSAURID_RAW_DEFINITION_DIGEST,
    },
}
PF2ER_HADROSAURID_COMPILER_DIGEST = canonical_digest(
    _COMPILER_MANIFEST,
    "Hadrosaurid compiler manifest",
)


class PF2ERHadrosauridSemanticError(ValueError):
    """The selected Hadrosaurid carrier leaf is invalid or has drifted."""


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise PF2ERHadrosauridSemanticError(
            f"{label} must be a lowercase sha256 digest"
        )
    return value


def _object(
    value: object,
    *,
    allowed: frozenset[str],
    required: frozenset[str] | None = None,
    label: str,
) -> dict[str, object]:
    if type(value) is not dict:
        raise PF2ERHadrosauridSemanticError(f"{label} must be an object")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise PF2ERHadrosauridSemanticError(
            f"{label} has unreviewed fields: " + ", ".join(unknown)
        )
    if required is not None:
        missing = sorted(required - set(value))
        if missing:
            raise PF2ERHadrosauridSemanticError(
                f"{label} omits reviewed fields: " + ", ".join(missing)
            )
    return value


def _string_list(value: object, label: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise PF2ERHadrosauridSemanticError(f"{label} must be a string list")
    return list(value)


def _require_equal(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise PF2ERHadrosauridSemanticError(f"{label} drifted")


def _project_damage(value: object, strike_id: str) -> dict[str, object]:
    damage = _object(
        value,
        allowed=frozenset(
            {
                "components",
                "dice",
                "flatAmount",
                "modifier",
                "riderEffects",
                "sourceText",
                "type",
            }
        ),
        required=frozenset(
            {
                "components",
                "dice",
                "flatAmount",
                "modifier",
                "riderEffects",
                "type",
            }
        ),
        label=f"Hadrosaurid {strike_id} damage",
    )
    if damage["riderEffects"] != []:
        raise PF2ERHadrosauridSemanticError(
            f"Hadrosaurid {strike_id} has unreviewed damage riders"
        )
    components = damage["components"]
    if type(components) is not list or len(components) != 1:
        raise PF2ERHadrosauridSemanticError(
            f"Hadrosaurid {strike_id} requires one damage component"
        )
    component = _object(
        components[0],
        allowed=frozenset(
            {
                "dice",
                "flatAmount",
                "modifier",
                "persistent",
                "sourceAddressSha256",
                "sourceSpan",
                "sourceText",
                "type",
            }
        ),
        required=frozenset(
            {"dice", "flatAmount", "modifier", "persistent", "type"}
        ),
        label=f"Hadrosaurid {strike_id} damage component",
    )
    public_component = {
        "dice": deepcopy(component["dice"]),
        "flatAmount": component["flatAmount"],
        "modifier": component["modifier"],
        "persistent": component["persistent"],
        "type": component["type"],
    }
    expected_component = {
        "strike:tail:melee": {
            "dice": {"count": 2, "sides": 6},
            "flatAmount": None,
            "modifier": 8,
            "persistent": False,
            "type": "bludgeoning",
        },
        "strike:foot:melee": {
            "dice": {"count": 2, "sides": 4},
            "flatAmount": None,
            "modifier": 8,
            "persistent": False,
            "type": "bludgeoning",
        },
    }[strike_id]
    _require_equal(
        public_component,
        expected_component,
        f"Hadrosaurid {strike_id} damage component",
    )
    projected = {
        "dice": deepcopy(damage["dice"]),
        "flatAmount": damage["flatAmount"],
        "modifier": damage["modifier"],
        "type": damage["type"],
        "components": [public_component],
        "riderEffects": [],
    }
    _require_equal(
        {
            key: projected[key]
            for key in ("dice", "flatAmount", "modifier", "type")
        },
        {
            key: expected_component[key]
            for key in ("dice", "flatAmount", "modifier", "type")
        },
        f"Hadrosaurid {strike_id} damage summary",
    )
    return projected


def _project_strikes(value: object) -> list[dict[str, object]]:
    if type(value) is not list or len(value) != 2:
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid requires the reviewed tail and foot Strikes"
        )
    expected = {
        "strike:tail:melee": ("tail", 14),
        "strike:foot:melee": ("foot", 12),
    }
    projected: list[dict[str, object]] = []
    for strike_value in value:
        strike = _object(
            strike_value,
            allowed=frozenset(
                {
                    "attackModifier",
                    "damage",
                    "followUps",
                    "id",
                    "kind",
                    "name",
                    "reachFeet",
                    "sourceAddressSha256",
                    "sourceDeferredDependencies",
                    "sourceOccurrenceId",
                    "traits",
                }
            ),
            required=frozenset(
                {
                    "attackModifier",
                    "damage",
                    "followUps",
                    "id",
                    "kind",
                    "name",
                    "reachFeet",
                    "traits",
                }
            ),
            label="Hadrosaurid Strike",
        )
        strike_id = strike["id"]
        if type(strike_id) is not str or strike_id not in expected:
            raise PF2ERHadrosauridSemanticError(
                "Hadrosaurid Strike identity drifted"
            )
        name, attack_modifier = expected[strike_id]
        if (
            strike["name"] != name
            or strike["kind"] != "melee"
            or strike["attackModifier"] != attack_modifier
            or strike["reachFeet"] != 15
            or strike["traits"] != ["reach 15 feet"]
            or strike["followUps"] != []
        ):
            raise PF2ERHadrosauridSemanticError(
                f"Hadrosaurid {strike_id} normalized shape drifted"
            )
        projected.append(
            {
                "id": strike_id,
                "name": name,
                "kind": "melee",
                "attackSource": {"kind": "natural"},
                "attackModifier": attack_modifier,
                "reachFeet": 15,
                "traits": ["reach 15 feet"],
                "damage": _project_damage(strike["damage"], strike_id),
                "followUps": [],
            }
        )
    if [item["id"] for item in projected] != list(expected):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid Strike order drifted"
        )
    return projected


def _project_sprint(value: object) -> dict[str, object]:
    ability = _object(
        value,
        allowed=frozenset(
            {
                "actionCost",
                "deferredMechanics",
                "description",
                "id",
                "kind",
                "mechanic",
                "name",
                "rule",
                "supported",
                "traits",
            }
        ),
        required=frozenset(
            {
                "actionCost",
                "deferredMechanics",
                "id",
                "kind",
                "mechanic",
                "name",
                "supported",
                "traits",
            }
        ),
        label="Hadrosaurid Sprint",
    )
    if (
        ability["id"] != "sprint"
        or ability["name"] != "Sprint"
        or ability["kind"] != "activity"
        or ability["actionCost"] != 2
        or ability["supported"] is not True
        or ability["traits"] != []
        or ability["deferredMechanics"] != []
    ):
        raise PF2ERHadrosauridSemanticError("Hadrosaurid Sprint drifted")
    mechanic = _object(
        ability["mechanic"],
        allowed=frozenset(
            {
                "frequency",
                "movementMode",
                "rules",
                "speedBonusType",
                "speedIncreaseFeet",
                "strideCount",
                "type",
            }
        ),
        required=frozenset(
            {
                "frequency",
                "movementMode",
                "rules",
                "speedBonusType",
                "speedIncreaseFeet",
                "strideCount",
                "type",
            }
        ),
        label="Hadrosaurid Sprint mechanic",
    )
    expected_rules = {
        "circumstanceBonus": {"sourceId": "core-pc1", "locator": "400.2"},
        "duration": {"sourceId": "core-pc1", "locator": "426.2"},
        "speed": {"sourceId": "core-pc1", "locator": "420.3"},
        "stride": {"sourceId": "core-pc1", "locator": "418.3"},
        "subordinateActions": {"sourceId": "core-pc1", "locator": "414.4"},
    }
    _require_equal(mechanic["rules"], expected_rules, "Sprint rule evidence")
    expected_frequency = {
        "decrementAt": "owner-start-turn",
        "maximum": 1,
        "period": {
            "source": "1 minute",
            "unit": "rounds",
            "value": 10,
        },
    }
    _require_equal(mechanic["frequency"], expected_frequency, "Sprint frequency")
    public = {
        "id": "sprint",
        "name": "Sprint",
        "kind": "activity",
        "actionCost": 2,
        "traits": [],
        "supported": True,
        "ruleRef": "pf2er.rule:hadrosaurid-sprint",
        "mechanic": {
            "type": mechanic["type"],
            "movementMode": mechanic["movementMode"],
            "strideCount": mechanic["strideCount"],
            "speedIncreaseFeet": mechanic["speedIncreaseFeet"],
            "speedBonusType": mechanic["speedBonusType"],
            "frequency": {
                "maximum": 1,
                "period": {"unit": "rounds", "value": 10},
                "decrementAt": "owner-start-turn",
            },
            "ruleRefs": {
                key: f"pf2er.rule:{key.replace('Actions', '-actions').replace('Bonus', '-bonus').casefold()}"
                for key in sorted(expected_rules)
            },
        },
    }
    _require_equal(
        {
            key: public["mechanic"][key]
            for key in (
                "type",
                "movementMode",
                "strideCount",
                "speedIncreaseFeet",
                "speedBonusType",
            )
        },
        {
            "type": "double-stride-speed-boost",
            "movementMode": "land",
            "strideCount": 2,
            "speedIncreaseFeet": 20,
            "speedBonusType": "circumstance",
        },
        "Sprint public mechanic",
    )
    return public


def _project_trample(value: object) -> dict[str, object]:
    ability = _object(
        value,
        allowed=frozenset({"mechanic", "rule", "supported", "traits"}),
        required=frozenset({"mechanic", "rule", "supported", "traits"}),
        label="linked Hadrosaurid Trample",
    )
    if ability["supported"] is not True or ability["traits"] != []:
        raise PF2ERHadrosauridSemanticError(
            "linked Hadrosaurid Trample support drifted"
        )
    _require_equal(
        ability["rule"],
        {"sourceId": "core-mc1", "locator": "358.2"},
        "linked Hadrosaurid Trample rule",
    )
    mechanic = _object(
        ability["mechanic"],
        allowed=frozenset(
            {
                "actionCost",
                "contractProof",
                "listedStrike",
                "listedStrikeId",
                "listedStrikeResolution",
                "listedStrikeSourceName",
                "movement",
                "multipleAttackPenalty",
                "rules",
                "runtime",
                "savingThrow",
                "sharedDamageRoll",
                "source",
                "sourceRecords",
                "targeting",
                "type",
            }
        ),
        required=frozenset(
            {
                "actionCost",
                "contractProof",
                "listedStrike",
                "listedStrikeId",
                "listedStrikeResolution",
                "movement",
                "multipleAttackPenalty",
                "rules",
                "runtime",
                "savingThrow",
                "sharedDamageRoll",
                "source",
                "sourceRecords",
                "targeting",
                "type",
            }
        ),
        label="linked Hadrosaurid Trample mechanic",
    )
    _require_equal(
        mechanic["contractProof"],
        {
            "schema": 1,
            "providerCount": 17,
            "deferralCount": 5,
            "sha256": _TRAMPLE_CONTRACT_PROOF_DIGEST,
        },
        "Trample contract proof",
    )
    expected_movement = {
        "legalEndpoint": "ordinary-occupiable-nonoverlapping-space",
        "movementMode": "land",
        "speedMultiplier": 2,
        "subordinateAction": "Stride",
        "targetTransit": "listed-size-or-smaller",
    }
    expected_targeting = {
        "identity": "participantId",
        "includesAllies": True,
        "maximumSize": "large",
        "maximumSizeRank": 3,
        "sameTargetLimit": 1,
        "selection": "first-space-entry",
    }
    expected_save = {"type": "reflex", "dc": 21, "basic": True}
    _require_equal(mechanic["type"], TRAMPLE_MECHANIC_TYPE, "Trample mechanic type")
    _require_equal(mechanic["actionCost"], 3, "Trample action cost")
    _require_equal(mechanic["movement"], expected_movement, "Trample movement")
    _require_equal(mechanic["targeting"], expected_targeting, "Trample targeting")
    _require_equal(mechanic["savingThrow"], expected_save, "Trample saving throw")
    _require_equal(mechanic["sharedDamageRoll"], True, "Trample shared roll")
    _require_equal(
        mechanic["multipleAttackPenalty"],
        {"changes": False, "reads": False},
        "Trample multiple attack penalty",
    )
    if (
        mechanic["listedStrikeId"] != "foot"
        or mechanic["listedStrikeResolution"]
        != "verified-complete-local-melee-index"
    ):
        raise PF2ERHadrosauridSemanticError("Trample listed Strike drifted")
    listed = _object(
        mechanic["listedStrike"],
        allowed=frozenset(
            {
                "damageCarrierSource",
                "damageComponents",
                "damageQualifiers",
                "damageSourceText",
                "excludedNonDamageTail",
                "id",
                "kind",
                "makesStrike",
                "name",
                "strikeSource",
            }
        ),
        required=frozenset(
            {
                "damageComponents",
                "damageQualifiers",
                "excludedNonDamageTail",
                "id",
                "kind",
                "makesStrike",
                "name",
            }
        ),
        label="Trample linked Strike",
    )
    components = listed["damageComponents"]
    if type(components) is not list or len(components) != 1:
        raise PF2ERHadrosauridSemanticError(
            "Trample linked Strike damage components drifted"
        )
    component = _object(
        components[0],
        allowed=frozenset({"dice", "modifier", "source", "sourceText", "type"}),
        required=frozenset({"dice", "modifier", "source", "sourceText", "type"}),
        label="Trample linked Strike damage component",
    )
    public_component = {
        "dice": deepcopy(component["dice"]),
        "modifier": component["modifier"],
        "type": component["type"],
    }
    _require_equal(
        public_component,
        {
            "dice": {"count": 2, "sides": 4},
            "modifier": 8,
            "type": "bludgeoning",
        },
        "Trample linked Strike damage",
    )
    if (
        listed["id"] != "foot"
        or listed["name"] != "foot"
        or listed["kind"] != "melee"
        or listed["makesStrike"] is not False
        or listed["damageQualifiers"] != []
        or listed["excludedNonDamageTail"] is not None
    ):
        raise PF2ERHadrosauridSemanticError(
            "Trample linked Strike normalized shape drifted"
        )
    definition = {
        "schema": 1,
        "id": PF2ER_TRAMPLE_ENTITY_ID,
        "name": "Trample",
        "kind": "pf2er-creature-ability",
        "activityKind": "activity",
        "actionCost": 3,
        "traits": [],
        "supported": True,
        "references": {
            "rules": sorted(
                f"pf2er.rule:{rule_id}"
                for rule_id in TRAMPLE_RULE_REQUIREMENTS
            ),
            "carriers": [PF2ER_HADROSAURID_ENTITY_ID],
        },
        "mechanic": {
            "type": TRAMPLE_MECHANIC_TYPE,
            "movement": deepcopy(expected_movement),
            "targeting": deepcopy(expected_targeting),
            "savingThrow": deepcopy(expected_save),
            "sharedDamageRoll": True,
            "multipleAttackPenalty": {"changes": False, "reads": False},
            "listedStrike": {
                "strikeId": "strike:foot:melee",
                "name": "foot",
                "kind": "melee",
                "makesStrike": False,
                "damage": {"components": [public_component]},
            },
            "runtime": {
                "status": "runtime-ready",
                "scope": "clean-map-land",
                "completenessDeferrals": list(
                    PF2ER_HADROSAURID_COMPLETENESS_DEFERRALS
                ),
            },
        },
    }
    validate_public_semantic_definition(definition)
    if public_definition_acquisition_paths(definition):
        raise PF2ERHadrosauridSemanticError(
            "Trample ability projection emitted acquisition fields"
        )
    return definition


def _project_hadrosaurid_definition(
    raw_definition: dict[str, object],
) -> dict[str, object]:
    raw = _object(
        raw_definition,
        allowed=frozenset(
            {
                "abilities",
                "attributes",
                "defenses",
                "deferredMechanics",
                "icon",
                "id",
                "inventory",
                "languages",
                "level",
                "name",
                "perception",
                "runtimeBlockers",
                "schema",
                "size",
                "skills",
                "source",
                "space",
                "speeds",
                "statCompilation",
                "strikes",
                "traits",
                "unsupportedMechanics",
            }
        ),
        required=frozenset(
            {
                "abilities",
                "attributes",
                "defenses",
                "icon",
                "id",
                "inventory",
                "level",
                "name",
                "schema",
                "size",
                "space",
                "speeds",
                "strikes",
                "traits",
            }
        ),
        label="Hadrosaurid creature compiler output",
    )
    if (
        raw["schema"] != 1
        or raw["id"] != f"{PF2ER_HADROSAURID_SOURCE_ID}:{PF2ER_HADROSAURID_LOCATOR}"
        or raw["name"] != "Hadrosaurid"
        or raw["level"] != 4
        or raw["size"] != "huge"
        or raw["traits"] != ["animal", "dinosaur"]
        or raw["inventory"] != []
        or raw["languages"] != []
        or raw["runtimeBlockers"] != []
        or raw["unsupportedMechanics"] != ["Trample"]
        or raw["icon"] != "core/mc1/creatures/x128/Hadrosaurid"
    ):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid reviewed compiler identity or profile drifted"
        )
    _require_equal(
        raw["source"],
        {
            "sourceId": "core-mc1",
            "locator": "98.2",
            "sectionId": "core-mc1:dinosaur",
            "contentPath": ["Dinosaur", "Hadrosaurid"],
        },
        "Hadrosaurid source evidence",
    )
    attributes = {
        "strength": 6,
        "dexterity": 2,
        "constitution": 3,
        "intelligence": -4,
        "wisdom": 1,
        "charisma": 0,
    }
    defenses = {
        "armorClass": 21,
        "fortitude": 12,
        "reflex": 10,
        "will": 11,
        "maximumHitPoints": 60,
        "immunities": [],
        "weaknesses": [],
        "resistances": [],
    }
    perception = {
        "modifier": 13,
        "senses": ["low-light vision", "scent (imprecise) 30 feet"],
    }
    skills = [
        {"name": "Athletics", "modifier": 12},
        {"name": "Stealth", "modifier": 10},
    ]
    _require_equal(raw["attributes"], attributes, "Hadrosaurid attributes")
    _require_equal(raw["defenses"], defenses, "Hadrosaurid defenses")
    _require_equal(raw["perception"], perception, "Hadrosaurid perception")
    _require_equal(raw["skills"], skills, "Hadrosaurid skills")
    space = _object(
        raw["space"],
        allowed=frozenset(
            {
                "defaultReachFeet",
                "heightSquares",
                "reachProfile",
                "rule",
                "sizeRank",
                "spaceFeet",
                "widthSquares",
            }
        ),
        required=frozenset(
            {
                "defaultReachFeet",
                "heightSquares",
                "reachProfile",
                "rule",
                "sizeRank",
                "spaceFeet",
                "widthSquares",
            }
        ),
        label="Hadrosaurid space",
    )
    _require_equal(
        space,
        {
            "sizeRank": 4,
            "reachProfile": "long",
            "widthSquares": 3,
            "heightSquares": 3,
            "spaceFeet": 15,
            "defaultReachFeet": 10,
            "rule": {"sourceId": "core-pc1", "locator": "421.8"},
        },
        "Hadrosaurid space",
    )
    _require_equal(raw["speeds"], {"land": 30}, "Hadrosaurid speeds")
    abilities = raw["abilities"]
    if type(abilities) is not list or len(abilities) != 2:
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid compiler abilities drifted"
        )
    sprint = _project_sprint(abilities[0])
    placeholder = abilities[1]
    _require_equal(
        placeholder,
        {
            "id": "trample",
            "name": "Trample",
            "kind": "activity",
            "actionCost": 3,
            "traits": [],
            "supported": False,
            "deferredMechanics": [],
            "description": "Large or smaller, foot, DC 21 (page 360)",
        },
        "Hadrosaurid compiler Trample placeholder",
    )
    rule_refs = {
        "pf2er.rule:circumstance-bonus",
        "pf2er.rule:duration",
        "pf2er.rule:hadrosaurid-sprint",
        "pf2er.rule:size-space-reach",
        "pf2er.rule:speed",
        "pf2er.rule:stride",
        "pf2er.rule:subordinate-actions",
    }
    definition: dict[str, object] = {
        "schema": 2,
        "kind": "pf2er-creature",
        "id": PF2ER_HADROSAURID_ENTITY_ID,
        "name": "Hadrosaurid",
        "level": 4,
        "size": "huge",
        "traits": ["animal", "dinosaur"],
        "attributes": attributes,
        "perception": perception,
        "skills": skills,
        "defenses": defenses,
        "space": {
            "sizeRank": 4,
            "reachProfile": "long",
            "widthSquares": 3,
            "heightSquares": 3,
            "spaceFeet": 15,
            "defaultReachFeet": 10,
            "ruleRef": "pf2er.rule:size-space-reach",
        },
        "speeds": {"land": 30},
        "inventory": [],
        "strikes": _project_strikes(raw["strikes"]),
        "abilities": [
            sprint,
            {
                "id": "trample",
                "name": "Trample",
                "kind": "activity",
                "providerEntityId": PF2ER_TRAMPLE_ENTITY_ID,
            },
        ],
        "references": {
            "rules": sorted(rule_refs),
            "items": [],
            "abilityProviders": [PF2ER_TRAMPLE_ENTITY_ID],
        },
        "runtime": {
            "status": "runtime-ready",
            "scope": "clean-map-land",
            "deferrals": list(PF2ER_HADROSAURID_RUNTIME_DEFERRALS),
            "completenessDeferrals": list(
                PF2ER_HADROSAURID_COMPLETENESS_DEFERRALS
            ),
        },
        "presentation": {
            "status": "deferred",
            "assetRefs": [],
            "deferrals": list(PF2ER_HADROSAURID_PRESENTATION_DEFERRALS),
        },
    }
    validate_public_semantic_definition(definition)
    paths = public_definition_acquisition_paths(definition)
    if paths:
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid projection emitted acquisition fields: "
            + ", ".join(paths)
        )
    return definition


def _require_exact_compiler_set(compiler_set: object) -> SemanticCompilerSet:
    if type(compiler_set) is not SemanticCompilerSet:
        raise TypeError("Hadrosaurid semantics require SemanticCompilerSet")
    expected = build_pf2er_semantic_compiler_set(
        book_ids=(PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
    )
    if (
        compiler_set.digest != PF2ER_HADROSAURID_UPSTREAM_COMPILER_DIGEST
        or compiler_set.digest != expected.digest
        or compiler_set.canonical_manifest() != expected.canonical_manifest()
    ):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid creature compiler selection drifted"
        )
    return compiler_set


def build_hadrosaurid_semantic_package(
    *,
    authority: SourceAuthorityAdapter,
    expected_authority_digest: str,
    compiler_set: SemanticCompilerSet,
    ruleset_digest: str,
    book_digest: str,
    semantic_generation: str,
    evidence_store: SemanticEvidenceStore,
    sprint_required_capabilities: tuple[CapabilityRequirement, ...],
    trample_required_capabilities: tuple[CapabilityRequirement, ...],
    relationships: tuple[ProviderCarrierRelationship, ...],
) -> SemanticPackage:
    """Compile and seal the exact Hadrosaurid/Trample carrier leaf.

    The ability capability and provider/carrier relationship are caller-owned
    publication choices.  This function verifies that the supplied values are
    exactly the reviewed leaf instead of inferring them from a creature name.
    """

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("Hadrosaurid semantics require SourceAuthorityAdapter")
    if type(evidence_store) is not SemanticEvidenceStore:
        raise TypeError("Hadrosaurid semantics require SemanticEvidenceStore")
    compiler_set = _require_exact_compiler_set(compiler_set)
    expected_authority_digest = _digest(
        expected_authority_digest,
        "expectedAuthorityDigest",
    )
    if (
        not hmac.compare_digest(authority.snapshot.digest, expected_authority_digest)
        or not hmac.compare_digest(
            expected_authority_digest,
            PF2ER_HADROSAURID_AUTHORITY_DIGEST,
        )
    ):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid source authority drifted"
        )
    if authority.allowed_source_ids != _EXPECTED_AUTHORITY_SCOPE:
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid authority scope must be the exact Core compiler scope"
        )
    if trample_required_capabilities != (
        PF2ER_HADROSAURID_TRAMPLE_CAPABILITY,
    ):
        raise PF2ERHadrosauridSemanticError(
            "Trample entity must explicitly require the exact runtime capability"
        )
    if sprint_required_capabilities != (
        PF2ER_HADROSAURID_SPRINT_CAPABILITY,
    ):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid must explicitly require the exact Sprint runtime capability"
        )
    if relationships != (PF2ER_HADROSAURID_TRAMPLE_RELATIONSHIP,):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid requires the exact Trample provider/carrier relationship"
        )
    if (
        authority.toc_label(
            PF2ER_HADROSAURID_SOURCE_ID,
            PF2ER_HADROSAURID_LOCATOR,
        )
        != "Hadrosaurid"
        or authority.toc_content_path(
            PF2ER_HADROSAURID_SOURCE_ID,
            PF2ER_HADROSAURID_LOCATOR,
        )
        != ("Dinosaur", "Hadrosaurid")
    ):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid source target drifted"
        )

    carrier = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=PF2ER_HADROSAURID_SOURCE_ID,
                locator=PF2ER_HADROSAURID_LOCATOR,
                carrier_path=(
                    RawMemberStep(
                        "^.creature",
                        PF2ER_HADROSAURID_CARRIER_MEMBER_ORDINAL,
                    ),
                ),
            )
        )
    )
    if carrier.carrier.raw_block.values("Name") != ("Hadrosaurid",):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid exact creature carrier drifted"
        )
    trample_selection = authority.validate_selection(
        carrier.carrier.select(
            (
                RawMemberStep(
                    "!.Trample",
                    PF2ER_HADROSAURID_TRAMPLE_MEMBER_ORDINAL,
                ),
            )
        )
    )
    rule_receipts = {
        rule_id: authority.resolve_rule(requirement)
        for rule_id, requirement in TRAMPLE_RULE_REQUIREMENTS.items()
    }
    compiled_trample = compile_trample(
        authority,
        trample_selection,
        rule_receipts,
    )
    if compiled_trample is None:
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid Trample did not compile"
        )
    linked_trample = link_trample_strike(compiled_trample)
    linked_output = linked_trample.as_ability_update()
    raw_creature = compiler_set.compile_source_creature(
        authority,
        PF2ER_HADROSAURID_SOURCE_ID,
        PF2ER_HADROSAURID_LOCATOR,
    )
    if not hmac.compare_digest(
        canonical_digest(raw_creature, "Hadrosaurid raw creature"),
        PF2ER_HADROSAURID_RAW_CREATURE_DIGEST,
    ):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid creature compiler output drifted"
        )
    if not hmac.compare_digest(
        canonical_digest(linked_output, "Hadrosaurid linked Trample"),
        PF2ER_HADROSAURID_LINKED_TRAMPLE_DIGEST,
    ):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid Trample compiler/link output drifted"
        )
    raw_definition = {
        "schema": 1,
        "creatureCompilerOutput": raw_creature,
        "trampleLinkedOutput": linked_output,
    }
    raw_digest = canonical_digest(
        raw_definition,
        "Hadrosaurid private compiler definition",
    )
    if not hmac.compare_digest(
        raw_digest,
        PF2ER_HADROSAURID_RAW_DEFINITION_DIGEST,
    ):
        raise PF2ERHadrosauridSemanticError(
            "Hadrosaurid private compiler definition drifted"
        )
    hadrosaurid_definition = _project_hadrosaurid_definition(raw_creature)
    trample_definition = _project_trample(linked_output)
    hadrosaurid_projected_digest = canonical_digest(
        hadrosaurid_definition,
        "Hadrosaurid public definition",
    )
    trample_projected_digest = canonical_digest(
        trample_definition,
        "Trample public definition",
    )
    hadrosaurid_record = SemanticEvidenceRecord.build(
        evidence_authority_id=PF2ER_HADROSAURID_EVIDENCE_AUTHORITY_ID,
        entity_id=PF2ER_HADROSAURID_ENTITY_ID,
        compiler_digest=PF2ER_HADROSAURID_COMPILER_DIGEST,
        raw_definition_digest=PF2ER_HADROSAURID_RAW_CREATURE_DIGEST,
        projected_definition_digest=hadrosaurid_projected_digest,
        projection_id=PF2ER_HADROSAURID_PROJECTION_ID,
        projection_version=PF2ER_HADROSAURID_PROJECTION_VERSION,
        projection_digest=PF2ER_HADROSAURID_PROJECTION_DIGEST,
        acquisition_receipt={
            "schema": 1,
            "kind": "pf2er-creature-carrier-acquisition",
            "authorityDigest": authority.snapshot.digest,
            "carrierSelection": carrier.receipt.as_serialized(),
        },
        compiler_receipt={
            "schema": 1,
            "manifest": deepcopy(_COMPILER_MANIFEST),
            "digest": PF2ER_HADROSAURID_COMPILER_DIGEST,
            "upstreamCreatureCompiler": {
                "manifest": compiler_set.manifest,
                "digest": compiler_set.digest,
            },
            "rawDefinition": deepcopy(raw_creature),
            "projection": deepcopy(_HADROSAURID_PROJECTION_MANIFEST),
        },
    )
    trample_record = SemanticEvidenceRecord.build(
        evidence_authority_id=PF2ER_HADROSAURID_EVIDENCE_AUTHORITY_ID,
        entity_id=PF2ER_TRAMPLE_ENTITY_ID,
        compiler_digest=PF2ER_HADROSAURID_COMPILER_DIGEST,
        raw_definition_digest=PF2ER_HADROSAURID_LINKED_TRAMPLE_DIGEST,
        projected_definition_digest=trample_projected_digest,
        projection_id=PF2ER_TRAMPLE_PROJECTION_ID,
        projection_version=PF2ER_TRAMPLE_PROJECTION_VERSION,
        projection_digest=PF2ER_TRAMPLE_PROJECTION_DIGEST,
        acquisition_receipt={
            "schema": 1,
            "kind": "pf2er-creature-ability-acquisition",
            "authorityDigest": authority.snapshot.digest,
            "trampleSelection": trample_selection.receipt.as_serialized(),
        },
        compiler_receipt={
            "schema": 1,
            "manifest": deepcopy(_COMPILER_MANIFEST),
            "digest": PF2ER_HADROSAURID_COMPILER_DIGEST,
            "rawDefinition": deepcopy(linked_output),
            "trampleEvidence": {
                "sourceReceipt": compiled_trample.source_receipt.as_serialized(),
                "strikeReceipt": linked_trample.strike_receipt.as_serialized(),
                "damageReceipt": linked_trample.damage_receipt.as_serialized(),
                "providerRuleReceipts": {
                    rule_id: receipt.as_serialized()
                    for rule_id, receipt in sorted(rule_receipts.items())
                },
            },
            "projection": deepcopy(_TRAMPLE_PROJECTION_MANIFEST),
        },
    )
    hadrosaurid_entity = build_semantic_entity(
        entity_id=PF2ER_HADROSAURID_ENTITY_ID,
        entity_kind="ttrpg:creature",
        definition=hadrosaurid_definition,
        evidence_authority_id=PF2ER_HADROSAURID_EVIDENCE_AUTHORITY_ID,
        evidence_record_digest=hadrosaurid_record.evidence_record_digest,
        compiler_digest=PF2ER_HADROSAURID_COMPILER_DIGEST,
        raw_definition_digest=PF2ER_HADROSAURID_RAW_CREATURE_DIGEST,
        projection_id=PF2ER_HADROSAURID_PROJECTION_ID,
        projection_version=PF2ER_HADROSAURID_PROJECTION_VERSION,
        projection_digest=PF2ER_HADROSAURID_PROJECTION_DIGEST,
        required_capabilities=sprint_required_capabilities,
        asset_refs=(),
    )
    trample_entity = build_semantic_entity(
        entity_id=PF2ER_TRAMPLE_ENTITY_ID,
        entity_kind="ttrpg:creature-ability",
        definition=trample_definition,
        evidence_authority_id=PF2ER_HADROSAURID_EVIDENCE_AUTHORITY_ID,
        evidence_record_digest=trample_record.evidence_record_digest,
        compiler_digest=PF2ER_HADROSAURID_COMPILER_DIGEST,
        raw_definition_digest=PF2ER_HADROSAURID_LINKED_TRAMPLE_DIGEST,
        projection_id=PF2ER_TRAMPLE_PROJECTION_ID,
        projection_version=PF2ER_TRAMPLE_PROJECTION_VERSION,
        projection_digest=PF2ER_TRAMPLE_PROJECTION_DIGEST,
        required_capabilities=trample_required_capabilities,
        asset_refs=(),
    )
    package = build_semantic_package(
        package_id=PF2ER_HADROSAURID_PACKAGE_ID,
        version=PF2ER_HADROSAURID_PACKAGE_VERSION,
        ruleset_id=PF2ER_RULESET_ID,
        ruleset_digest=ruleset_digest,
        book_id=PF2ER_MONSTER_CORE_ONE_BOOK_ID,
        book_digest=book_digest,
        semantic_generation=semantic_generation,
        semantic_generation_digest=canonical_digest(
            {
                "schema": 1,
                "semanticGeneration": semantic_generation,
                "packageId": PF2ER_HADROSAURID_PACKAGE_ID,
                "packageVersion": PF2ER_HADROSAURID_PACKAGE_VERSION,
                "compilerDigest": PF2ER_HADROSAURID_COMPILER_DIGEST,
                "entities": [
                    {
                        "entityId": entity.entity_id,
                        "projectionDigest": entity.receipt.projection_digest,
                        "semanticReceiptDigest": (
                            entity.receipt.semantic_receipt_digest
                        ),
                    }
                    for entity in sorted(
                        (hadrosaurid_entity, trample_entity),
                        key=lambda item: item.entity_id,
                    )
                ],
                "relationships": [
                    relationship.to_dict()
                    for relationship in relationships
                ],
            },
            "Hadrosaurid semantic generation",
        ),
        compiler_id=PF2ER_HADROSAURID_COMPILER_ID,
        compiler_version=PF2ER_HADROSAURID_COMPILER_VERSION,
        compiler_digest=PF2ER_HADROSAURID_COMPILER_DIGEST,
        entities=(hadrosaurid_entity, trample_entity),
        relationships=relationships,
    )
    evidence_store.provision_many((hadrosaurid_record, trample_record))
    return package


__all__ = [
    "PF2ER_HADROSAURID_AUTHORITY_DIGEST",
    "PF2ER_HADROSAURID_CARRIER_MEMBER_ORDINAL",
    "PF2ER_HADROSAURID_COMPILER_DIGEST",
    "PF2ER_HADROSAURID_COMPLETENESS_DEFERRALS",
    "PF2ER_HADROSAURID_ENTITY_ID",
    "PF2ER_HADROSAURID_LOCATOR",
    "PF2ER_HADROSAURID_PACKAGE_ID",
    "PF2ER_HADROSAURID_PACKAGE_VERSION",
    "PF2ER_HADROSAURID_PRESENTATION_DEFERRALS",
    "PF2ER_HADROSAURID_PROJECTION_DIGEST",
    "PF2ER_HADROSAURID_RUNTIME_DEFERRALS",
    "PF2ER_HADROSAURID_SPRINT_CAPABILITY",
    "PF2ER_HADROSAURID_SOURCE_ID",
    "PF2ER_HADROSAURID_TARGET",
    "PF2ER_HADROSAURID_TRAMPLE_CAPABILITY",
    "PF2ER_HADROSAURID_TRAMPLE_RELATIONSHIP",
    "PF2ER_TRAMPLE_CAPABILITY",
    "PF2ER_TRAMPLE_ENTITY_ID",
    "PF2ER_TRAMPLE_PROJECTION_DIGEST",
    "PF2ERHadrosauridSemanticError",
    "build_hadrosaurid_semantic_package",
]

"""Source-free Viper carrier semantics for the bounded Slink pilot.

The production source compiler and the family-local Slink compiler run only
while TTRPG owns an authenticated source-authority adapter.  Their complete
output and source receipts are retained in ``SemanticEvidenceStore``.  The
public schema-2 package contains distinct Slink ability and Viper carrier
entities, their exact capability requirement and relationship, and no
acquisition coordinates or invented presentation asset.
"""

from __future__ import annotations

from copy import deepcopy
import hmac
import json
import re
from types import MappingProxyType
from typing import Any

from . import pf2er_semantic
from .pf2er_compiler.mechanics import slink
from .pf2er_compiler.mechanics.contracts import RawSourceObject
from .pf2er_compiler.mechanics.source_authority import (
    RawMemberStep,
    SourceAuthorityAdapter,
    canonical_raw_bytes,
)
from .semantic_evidence import (
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
    canonical_digest,
)
from .semantic_packages import (
    CapabilityRequirement,
    ProviderCarrierRelationship,
    SemanticPackage,
    build_semantic_entity,
    build_semantic_package,
    public_definition_acquisition_paths,
    validate_public_semantic_definition,
)


PF2ER_RULESET_ID = "paizo:pf2er"
PF2ER_MONSTER_CORE_ONE_BOOK_ID = "paizo:monster-core-one"
PF2ER_VIPER_PACKAGE_ID = "ttrpg:pf2er-monster-core-one-viper-slink"
PF2ER_VIPER_PACKAGE_VERSION = "1.0.0"
PF2ER_VIPER_COMPILER_ID = "ttrpg:pf2er-viper-semantic-compiler"
PF2ER_VIPER_COMPILER_VERSION = "1.0.0"
PF2ER_VIPER_PROJECTION_ID = "ttrpg:pf2er-viper-creature-definition"
PF2ER_VIPER_PROJECTION_VERSION = "1.0.0"
PF2ER_SLINK_PROJECTION_ID = "ttrpg:pf2er-slink-ability-definition"
PF2ER_SLINK_PROJECTION_VERSION = "1.0.0"
PF2ER_VIPER_EVIDENCE_AUTHORITY_ID = "ttrpg:pf2er-semantic-evidence"

PF2ER_VIPER_ENTITY_ID = "pf2er:viper"
PF2ER_SLINK_ENTITY_ID = slink.ENTITY_ID
PF2ER_VIPER_SOURCE_ID = slink.SOURCE_ID
PF2ER_VIPER_SOURCE_LOCATOR = slink.SOURCE_LOCATOR
PF2ER_VIPER_SOURCE_CARRIER_KEY = "^.creature"
PF2ER_VIPER_SOURCE_CARRIER_ORDINAL = 1
PF2ER_SLINK_CAPABILITY = CapabilityRequirement(
    "gladiator:pf2er-slink-reaction",
    "1.0.0",
)
PF2ER_VIPER_SLINK_RELATIONSHIP = ProviderCarrierRelationship(
    "ttrpg:viper-slink-carrier",
    PF2ER_SLINK_ENTITY_ID,
    PF2ER_VIPER_ENTITY_ID,
)

# These are publication statements, not fallbacks.  A later package must
# replace each one with reviewed semantics before broadening the ready domain.
PF2ER_VIPER_DEFERRALS = (
    MappingProxyType(
        {
            "domain": "movement-mode",
            "id": "climb-slink-runtime",
            "reason": "the bounded Slink carrier executes only land Stride",
        }
    ),
    MappingProxyType(
        {
            "domain": "movement-mode",
            "id": "swim-slink-runtime",
            "reason": "the bounded Slink carrier executes only land Stride",
        }
    ),
    MappingProxyType(
        {
            "domain": "geometry",
            "id": "tiny-shared-space-runtime",
            "reason": "Tiny conscious-creature shared-space movement is not selected",
        }
    ),
    MappingProxyType(
        {
            "domain": "presentation",
            "id": "viper-icon-semantic-asset",
            "reason": "no reviewed opaque Viper asset is published by this package",
        }
    ),
    MappingProxyType(
        {
            "domain": "strike-rider",
            "id": "viper-venom-semantic-runtime",
            "reason": "Viper Venom is outside the selected Slink capability lane",
        }
    ),
)

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class PF2ERViperSemanticError(ValueError):
    """The reviewed Viper carrier source or semantic projection drifted."""


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise PF2ERViperSemanticError(
            f"{label} must be a lowercase sha256 digest"
        )
    return value


def _exact_object(
    value: object,
    keys: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        actual = sorted(value) if type(value) is dict else type(value).__name__
        raise PF2ERViperSemanticError(
            f"{label} shape drifted; expected={sorted(keys)}, actual={actual}"
        )
    return value


def _string_list(value: object, label: str) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise PF2ERViperSemanticError(f"{label} must be a string list")
    return list(value)


_VIPER_PROJECTION_MANIFEST = {
    "schema": 1,
    "packageId": PF2ER_VIPER_PACKAGE_ID,
    "packageVersion": PF2ER_VIPER_PACKAGE_VERSION,
    "projectionId": PF2ER_VIPER_PROJECTION_ID,
    "projectionVersion": PF2ER_VIPER_PROJECTION_VERSION,
    "definitionSchema": 2,
    "entityKind": "ttrpg:creature",
    "selectedEntityIds": [PF2ER_VIPER_ENTITY_ID],
}
PF2ER_VIPER_PROJECTION_DIGEST = canonical_digest(
    _VIPER_PROJECTION_MANIFEST,
    "PF2ER Viper projection manifest",
)

_SLINK_PROJECTION_MANIFEST = {
    "schema": 1,
    "packageId": PF2ER_VIPER_PACKAGE_ID,
    "packageVersion": PF2ER_VIPER_PACKAGE_VERSION,
    "projectionId": PF2ER_SLINK_PROJECTION_ID,
    "projectionVersion": PF2ER_SLINK_PROJECTION_VERSION,
    "definitionSchema": 1,
    "entityKind": "ttrpg:creature-ability",
    "selectedEntityIds": [PF2ER_SLINK_ENTITY_ID],
}
PF2ER_SLINK_PROJECTION_DIGEST = canonical_digest(
    _SLINK_PROJECTION_MANIFEST,
    "PF2ER Slink projection manifest",
)

_BASE_COMPILER_SET = pf2er_semantic.build_pf2er_semantic_compiler_set(
    book_ids=(PF2ER_MONSTER_CORE_ONE_BOOK_ID,)
)
_COMPILER_MANIFEST = {
    "schema": 1,
    "compilerId": PF2ER_VIPER_COMPILER_ID,
    "compilerVersion": PF2ER_VIPER_COMPILER_VERSION,
    "rulesetId": PF2ER_RULESET_ID,
    "bookId": PF2ER_MONSTER_CORE_ONE_BOOK_ID,
    "entityIds": [PF2ER_SLINK_ENTITY_ID, PF2ER_VIPER_ENTITY_ID],
    "sourceTarget": {
        "sourceId": PF2ER_VIPER_SOURCE_ID,
        "locator": PF2ER_VIPER_SOURCE_LOCATOR,
        "carrierMember": PF2ER_VIPER_SOURCE_CARRIER_KEY,
        "carrierOrdinal": PF2ER_VIPER_SOURCE_CARRIER_ORDINAL,
    },
    "baseCreatureCompilerDigest": _BASE_COMPILER_SET.digest,
    "familyCompiler": {
        "familyId": slink.FAMILY_ID,
        "entityId": slink.ENTITY_ID,
        "providerRuleId": slink.PROVIDER_RULE_ID,
        "mechanicType": slink.MECHANIC_TYPE,
        "selectionSha256": slink.SOURCE_SELECTION_SHA256,
    },
}
PF2ER_VIPER_COMPILER_DIGEST = canonical_digest(
    _COMPILER_MANIFEST,
    "PF2ER Viper compiler manifest",
)

# The digest is filled from the reviewed production compiler output.  It is a
# code-and-source drift fence in addition to the authority snapshot fence.
PF2ER_SLINK_RAW_DEFINITION_DIGEST = (
    "6430044e90eeaa8d43134448a2085d475a7a4c589f7637aa259b640b639761d2"
)
PF2ER_VIPER_RAW_DEFINITION_DIGEST = (
    "0c3a09e073c9a15605762f5782e3f2d44ad870ead4a60dc6c78f7a3b57f42251"
)


def _compile_private_definition(
    authority: SourceAuthorityAdapter,
) -> tuple[dict[str, Any], dict[str, Any], object, object, object]:
    if (
        authority.toc_label(PF2ER_VIPER_SOURCE_ID, PF2ER_VIPER_SOURCE_LOCATOR)
        != "Viper"
        or authority.toc_content_path(
            PF2ER_VIPER_SOURCE_ID,
            PF2ER_VIPER_SOURCE_LOCATOR,
        )
        != ("Snake", "Viper")
    ):
        raise PF2ERViperSemanticError("Viper source target drifted")

    source_target = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=PF2ER_VIPER_SOURCE_ID,
                locator=PF2ER_VIPER_SOURCE_LOCATOR,
            )
        )
    )
    carrier = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=PF2ER_VIPER_SOURCE_ID,
                locator=PF2ER_VIPER_SOURCE_LOCATOR,
                carrier_path=(
                    RawMemberStep(
                        PF2ER_VIPER_SOURCE_CARRIER_KEY,
                        PF2ER_VIPER_SOURCE_CARRIER_ORDINAL,
                    ),
                ),
            )
        )
    )
    if (
        type(carrier.selected_value) is not RawSourceObject
        or carrier.selected_value.values("Name") != ("Viper",)
        or carrier.address.carrier_path
        != (
            RawMemberStep(
                PF2ER_VIPER_SOURCE_CARRIER_KEY,
                PF2ER_VIPER_SOURCE_CARRIER_ORDINAL,
            ),
        )
    ):
        raise PF2ERViperSemanticError("Viper carrier refinement drifted")

    source = slink.select_slink_source(authority)
    compiled = slink.compile_slink(authority, source)
    if compiled is None:
        raise PF2ERViperSemanticError("Viper Slink source no longer compiles")
    if source.address.carrier_path != carrier.address.carrier_path:
        raise PF2ERViperSemanticError(
            "Viper and Slink source refinements disagree"
        )

    creature = _BASE_COMPILER_SET.compile_source_creature(
        authority,
        PF2ER_VIPER_SOURCE_ID,
        PF2ER_VIPER_SOURCE_LOCATOR,
    )
    viper_raw_definition = {
        "schema": 1,
        "creature": creature,
    }
    slink_raw_definition = {
        "schema": 1,
        "sourceMember": json.loads(
            canonical_raw_bytes(source.selected_value).decode("utf-8")
        ),
        "familyProjection": compiled.as_ability_update(),
    }
    return (
        viper_raw_definition,
        slink_raw_definition,
        source_target,
        carrier,
        source,
    )


def _project_damage(value: object) -> dict[str, Any]:
    raw = _exact_object(
        value,
        frozenset(
            (
                "components",
                "dice",
                "flatAmount",
                "modifier",
                "riderEffects",
                "sourceText",
                "type",
            )
        ),
        "Viper fangs damage",
    )
    components = raw["components"]
    if type(components) is not list or len(components) != 1:
        raise PF2ERViperSemanticError("Viper fangs damage component drifted")
    component = _exact_object(
        components[0],
        frozenset(
            (
                "dice",
                "flatAmount",
                "modifier",
                "persistent",
                "sourceAddressSha256",
                "sourceSpan",
                "sourceText",
                "type",
            )
        ),
        "Viper fangs damage component",
    )
    riders = raw["riderEffects"]
    if (
        type(riders) is not list
        or len(riders) != 1
        or type(riders[0]) is not dict
        or riders[0].get("abilityId") != "viper-venom"
        or riders[0].get("name") != "Viper Venom"
    ):
        raise PF2ERViperSemanticError("Viper Venom rider drifted")
    return {
        "dice": deepcopy(raw["dice"]),
        "flatAmount": raw["flatAmount"],
        "modifier": raw["modifier"],
        "type": raw["type"],
        "components": [
            {
                key: deepcopy(component[key])
                for key in (
                    "dice",
                    "flatAmount",
                    "modifier",
                    "persistent",
                    "type",
                )
            }
        ],
        "deferredRiders": [
            {
                "abilityId": "viper-venom",
                "name": "Viper Venom",
                "status": "deferred",
            }
        ],
    }


def _project_strike(value: object) -> dict[str, Any]:
    raw = _exact_object(
        value,
        frozenset(
            (
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
            )
        ),
        "Viper fangs strike",
    )
    if (
        raw["id"] != "strike:fangs:melee"
        or raw["name"] != "fangs"
        or raw["kind"] != "melee"
        or raw["followUps"] != []
    ):
        raise PF2ERViperSemanticError("Viper fangs strike identity drifted")
    return {
        "id": raw["id"],
        "name": raw["name"],
        "kind": raw["kind"],
        "attackSource": {"kind": "natural"},
        "attackModifier": raw["attackModifier"],
        "traits": _string_list(raw["traits"], "Viper fangs traits"),
        "reachFeet": raw["reachFeet"],
        "damage": _project_damage(raw["damage"]),
        "followUps": [],
    }


def _validate_projected_definition(
    projected: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    paths = public_definition_acquisition_paths(projected)
    if paths:
        raise PF2ERViperSemanticError(
            f"{label} projector emitted acquisition-only fields: "
            + ", ".join(paths)
        )
    validate_public_semantic_definition(projected)
    return projected


def _project_slink_definition(
    raw_definition: dict[str, Any],
) -> dict[str, Any]:
    raw = _exact_object(
        raw_definition,
        frozenset(("schema", "sourceMember", "familyProjection")),
        "Slink private compiler definition",
    )
    if raw["schema"] != 1:
        raise PF2ERViperSemanticError("Slink compiler schema drifted")
    source_member = _exact_object(
        raw["sourceMember"],
        frozenset(("Action", "Description", "Trigger")),
        "Slink private source member",
    )
    if source_member != {
        "Action": "reaction",
        "Trigger": slink.SOURCE_TRIGGER,
        "Description": slink.SOURCE_DESCRIPTION,
    }:
        raise PF2ERViperSemanticError("Slink private source member drifted")
    family = _exact_object(
        raw["familyProjection"],
        frozenset(("entityId", "mechanic", "ruleRef", "supported", "traits")),
        "Slink family projection",
    )
    if (
        family["supported"] is not True
        or family["entityId"] != PF2ER_SLINK_ENTITY_ID
        or family["ruleRef"] != slink.PROVIDER_RULE_ID
        or family["traits"] != []
    ):
        raise PF2ERViperSemanticError("Slink family projection drifted")
    projected = {
        "schema": 1,
        "kind": "pf2er-creature-ability",
        "id": PF2ER_SLINK_ENTITY_ID,
        "name": "Slink",
        "actionCost": "reaction",
        "supported": True,
        "traits": deepcopy(family["traits"]),
        "ruleRef": family["ruleRef"],
        "mechanic": deepcopy(family["mechanic"]),
        "references": {"rules": [slink.PROVIDER_RULE_ID]},
    }
    return _validate_projected_definition(projected, "Slink")


def _project_viper_definition(
    raw_definition: dict[str, Any],
) -> dict[str, Any]:
    raw = _exact_object(
        raw_definition,
        frozenset(("schema", "creature")),
        "Viper private compiler definition",
    )
    if raw["schema"] != 1:
        raise PF2ERViperSemanticError("Viper compiler schema drifted")
    creature = _exact_object(
        raw["creature"],
        frozenset(
            (
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
            )
        ),
        "Viper creature compiler definition",
    )
    if (
        creature["schema"] != 1
        or creature["id"] != "core-mc1:316.2"
        or creature["name"] != "Viper"
        or creature["level"] != -1
        or creature["size"] != "tiny"
        or creature["inventory"] != []
        or creature["languages"] != []
        or creature["runtimeBlockers"] != []
        or creature["traits"] != ["animal"]
    ):
        raise PF2ERViperSemanticError("Viper creature identity or stats drifted")

    abilities = creature["abilities"]
    if (
        type(abilities) is not list
        or len(abilities) != 2
        or abilities[0].get("id") != "slink"
        or abilities[0].get("supported") is not False
        or abilities[1].get("id") != "viper-venom"
    ):
        raise PF2ERViperSemanticError("Viper source ability census drifted")
    attributes = _exact_object(
        creature["attributes"],
        frozenset(
            (
                "charisma",
                "constitution",
                "dexterity",
                "intelligence",
                "strength",
                "wisdom",
            )
        ),
        "Viper attributes",
    )
    defenses = _exact_object(
        creature["defenses"],
        frozenset(
            (
                "armorClass",
                "fortitude",
                "immunities",
                "maximumHitPoints",
                "reflex",
                "resistances",
                "weaknesses",
                "will",
            )
        ),
        "Viper defenses",
    )
    perception = _exact_object(
        creature["perception"],
        frozenset(("modifier", "senses")),
        "Viper perception",
    )
    space = _exact_object(
        creature["space"],
        frozenset(
            (
                "defaultReachFeet",
                "heightSquares",
                "reachProfile",
                "rule",
                "sizeRank",
                "spaceFeet",
                "widthSquares",
            )
        ),
        "Viper space",
    )
    speeds = _exact_object(
        creature["speeds"],
        frozenset(("climb", "land", "swim")),
        "Viper speeds",
    )
    if speeds != {"land": 20, "climb": 20, "swim": 20}:
        raise PF2ERViperSemanticError("Viper speed profile drifted")
    strikes = creature["strikes"]
    if type(strikes) is not list or len(strikes) != 1:
        raise PF2ERViperSemanticError("Viper strike census drifted")

    skills = creature["skills"]
    if type(skills) is not list or any(type(item) is not dict for item in skills):
        raise PF2ERViperSemanticError("Viper skills drifted")
    public_skills = []
    for index, value in enumerate(skills):
        unknown = set(value) - {"modifier", "name", "note"}
        if unknown or set(value) not in (
            {"modifier", "name"},
            {"modifier", "name", "note"},
        ):
            raise PF2ERViperSemanticError(
                f"Viper skill {index} shape drifted"
            )
        public_skills.append(deepcopy(value))

    projected = {
        "schema": 2,
        "kind": "pf2er-creature",
        "id": PF2ER_VIPER_ENTITY_ID,
        "name": "Viper",
        "level": -1,
        "size": "tiny",
        "traits": ["animal"],
        "attributes": deepcopy(attributes),
        "perception": {
            "modifier": perception["modifier"],
            "senses": _string_list(perception["senses"], "Viper senses"),
        },
        "skills": public_skills,
        "space": {
            key: space[key]
            for key in (
                "sizeRank",
                "reachProfile",
                "widthSquares",
                "heightSquares",
                "spaceFeet",
                "defaultReachFeet",
            )
        },
        "speeds": deepcopy(speeds),
        "defenses": deepcopy(defenses),
        "inventory": [],
        "strikes": [_project_strike(strikes[0])],
        "abilities": [
            {
                "entityId": PF2ER_SLINK_ENTITY_ID,
                "kind": "creature-ability",
            }
        ],
        "references": {
            "rules": [],
            "items": [],
            "abilities": [PF2ER_SLINK_ENTITY_ID],
        },
        "runtime": {
            "readyDomains": ["clean-map-land-slink-carrier"],
            "algorithmicallyComplete": False,
            "deferrals": [dict(item) for item in PF2ER_VIPER_DEFERRALS],
        },
    }
    return _validate_projected_definition(projected, "Viper")


def build_viper_semantic_package(
    *,
    authority: SourceAuthorityAdapter,
    expected_authority_digest: str,
    ruleset_digest: str,
    book_digest: str,
    semantic_generation: str,
    evidence_store: SemanticEvidenceStore,
    slink_required_capabilities: tuple[CapabilityRequirement, ...],
    relationships: tuple[ProviderCarrierRelationship, ...],
) -> SemanticPackage:
    """Compile and seal the exact Slink provider and Viper carrier package."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("Viper semantics require SourceAuthorityAdapter")
    if type(evidence_store) is not SemanticEvidenceStore:
        raise TypeError("Viper semantics require SemanticEvidenceStore")
    if slink_required_capabilities != (PF2ER_SLINK_CAPABILITY,):
        raise PF2ERViperSemanticError(
            "Slink requires exactly the reviewed runtime capability"
        )
    if relationships != (PF2ER_VIPER_SLINK_RELATIONSHIP,):
        raise PF2ERViperSemanticError(
            "Viper requires exactly the reviewed Slink carrier relationship"
        )
    expected_authority_digest = _digest(
        expected_authority_digest,
        "expectedAuthorityDigest",
    )
    if not hmac.compare_digest(
        authority.snapshot.digest,
        expected_authority_digest,
    ):
        raise PF2ERViperSemanticError("Viper source authority drifted")
    if PF2ER_VIPER_SOURCE_ID not in authority.allowed_source_ids:
        raise PF2ERViperSemanticError("Monster Core source is not selected")
    ruleset_digest = _digest(ruleset_digest, "rulesetDigest")
    book_digest = _digest(book_digest, "bookDigest")

    (
        viper_raw_definition,
        slink_raw_definition,
        source_target,
        carrier,
        slink_source,
    ) = _compile_private_definition(authority)
    viper_raw_definition_digest = canonical_digest(
        viper_raw_definition,
        "raw Viper compiler definition",
    )
    if not hmac.compare_digest(
        viper_raw_definition_digest,
        PF2ER_VIPER_RAW_DEFINITION_DIGEST,
    ):
        raise PF2ERViperSemanticError("Viper compiler output drifted")
    slink_raw_definition_digest = canonical_digest(
        slink_raw_definition,
        "raw Slink compiler definition",
    )
    if not hmac.compare_digest(
        slink_raw_definition_digest,
        PF2ER_SLINK_RAW_DEFINITION_DIGEST,
    ):
        raise PF2ERViperSemanticError("Slink compiler output drifted")

    viper_definition = _project_viper_definition(viper_raw_definition)
    slink_definition = _project_slink_definition(slink_raw_definition)
    viper_projected_definition_digest = canonical_digest(
        viper_definition,
        "projected Viper definition",
    )
    slink_projected_definition_digest = canonical_digest(
        slink_definition,
        "projected Slink definition",
    )
    viper_record = SemanticEvidenceRecord.build(
        evidence_authority_id=PF2ER_VIPER_EVIDENCE_AUTHORITY_ID,
        entity_id=PF2ER_VIPER_ENTITY_ID,
        compiler_digest=PF2ER_VIPER_COMPILER_DIGEST,
        raw_definition_digest=viper_raw_definition_digest,
        projected_definition_digest=viper_projected_definition_digest,
        projection_id=PF2ER_VIPER_PROJECTION_ID,
        projection_version=PF2ER_VIPER_PROJECTION_VERSION,
        projection_digest=PF2ER_VIPER_PROJECTION_DIGEST,
        acquisition_receipt={
            "schema": 1,
            "kind": "pf2er-viper-acquisition",
            "authorityDigest": authority.snapshot.digest,
            "sourceSelection": source_target.receipt.as_serialized(),
            "creatureSelection": carrier.receipt.as_serialized(),
        },
        compiler_receipt={
            "schema": 1,
            "manifest": deepcopy(_COMPILER_MANIFEST),
            "digest": PF2ER_VIPER_COMPILER_DIGEST,
            "rawDefinition": deepcopy(viper_raw_definition),
            "projection": deepcopy(_VIPER_PROJECTION_MANIFEST),
        },
    )
    slink_record = SemanticEvidenceRecord.build(
        evidence_authority_id=PF2ER_VIPER_EVIDENCE_AUTHORITY_ID,
        entity_id=PF2ER_SLINK_ENTITY_ID,
        compiler_digest=PF2ER_VIPER_COMPILER_DIGEST,
        raw_definition_digest=slink_raw_definition_digest,
        projected_definition_digest=slink_projected_definition_digest,
        projection_id=PF2ER_SLINK_PROJECTION_ID,
        projection_version=PF2ER_SLINK_PROJECTION_VERSION,
        projection_digest=PF2ER_SLINK_PROJECTION_DIGEST,
        acquisition_receipt={
            "schema": 1,
            "kind": "pf2er-slink-acquisition",
            "authorityDigest": authority.snapshot.digest,
            "sourceSelection": source_target.receipt.as_serialized(),
            "slinkSelection": slink_source.receipt.as_serialized(),
        },
        compiler_receipt={
            "schema": 1,
            "manifest": deepcopy(_COMPILER_MANIFEST),
            "digest": PF2ER_VIPER_COMPILER_DIGEST,
            "rawDefinition": deepcopy(slink_raw_definition),
            "projection": deepcopy(_SLINK_PROJECTION_MANIFEST),
        },
    )
    viper_entity = build_semantic_entity(
        entity_id=PF2ER_VIPER_ENTITY_ID,
        entity_kind="ttrpg:creature",
        definition=viper_definition,
        evidence_authority_id=PF2ER_VIPER_EVIDENCE_AUTHORITY_ID,
        evidence_record_digest=viper_record.evidence_record_digest,
        compiler_digest=PF2ER_VIPER_COMPILER_DIGEST,
        raw_definition_digest=viper_raw_definition_digest,
        projection_id=PF2ER_VIPER_PROJECTION_ID,
        projection_version=PF2ER_VIPER_PROJECTION_VERSION,
        projection_digest=PF2ER_VIPER_PROJECTION_DIGEST,
        required_capabilities=(),
        asset_refs=(),
    )
    slink_entity = build_semantic_entity(
        entity_id=PF2ER_SLINK_ENTITY_ID,
        entity_kind="ttrpg:creature-ability",
        definition=slink_definition,
        evidence_authority_id=PF2ER_VIPER_EVIDENCE_AUTHORITY_ID,
        evidence_record_digest=slink_record.evidence_record_digest,
        compiler_digest=PF2ER_VIPER_COMPILER_DIGEST,
        raw_definition_digest=slink_raw_definition_digest,
        projection_id=PF2ER_SLINK_PROJECTION_ID,
        projection_version=PF2ER_SLINK_PROJECTION_VERSION,
        projection_digest=PF2ER_SLINK_PROJECTION_DIGEST,
        required_capabilities=slink_required_capabilities,
        asset_refs=(),
    )
    entities = (slink_entity, viper_entity)
    package = build_semantic_package(
        package_id=PF2ER_VIPER_PACKAGE_ID,
        version=PF2ER_VIPER_PACKAGE_VERSION,
        ruleset_id=PF2ER_RULESET_ID,
        ruleset_digest=ruleset_digest,
        book_id=PF2ER_MONSTER_CORE_ONE_BOOK_ID,
        book_digest=book_digest,
        semantic_generation=semantic_generation,
        semantic_generation_digest=canonical_digest(
            {
                "schema": 1,
                "semanticGeneration": semantic_generation,
                "packageId": PF2ER_VIPER_PACKAGE_ID,
                "packageVersion": PF2ER_VIPER_PACKAGE_VERSION,
                "compilerDigest": PF2ER_VIPER_COMPILER_DIGEST,
                "projectionDigests": [
                    PF2ER_SLINK_PROJECTION_DIGEST,
                    PF2ER_VIPER_PROJECTION_DIGEST,
                ],
                "entities": [
                    {
                        "entityId": entity.entity_id,
                        "semanticReceiptDigest": (
                            entity.receipt.semantic_receipt_digest
                        ),
                    }
                    for entity in entities
                ],
            },
            "PF2ER Viper and Slink semantic generation",
        ),
        compiler_id=PF2ER_VIPER_COMPILER_ID,
        compiler_version=PF2ER_VIPER_COMPILER_VERSION,
        compiler_digest=PF2ER_VIPER_COMPILER_DIGEST,
        entities=entities,
        relationships=relationships,
    )
    evidence_store.provision_many((slink_record, viper_record))
    return package


__all__ = [
    "PF2ER_MONSTER_CORE_ONE_BOOK_ID",
    "PF2ER_SLINK_ENTITY_ID",
    "PF2ER_SLINK_PROJECTION_DIGEST",
    "PF2ER_SLINK_RAW_DEFINITION_DIGEST",
    "PF2ER_VIPER_COMPILER_DIGEST",
    "PF2ER_VIPER_DEFERRALS",
    "PF2ER_VIPER_ENTITY_ID",
    "PF2ER_VIPER_PACKAGE_ID",
    "PF2ER_VIPER_PACKAGE_VERSION",
    "PF2ER_VIPER_PROJECTION_DIGEST",
    "PF2ER_VIPER_RAW_DEFINITION_DIGEST",
    "PF2ER_SLINK_CAPABILITY",
    "PF2ER_VIPER_SLINK_RELATIONSHIP",
    "PF2ER_VIPER_SOURCE_CARRIER_KEY",
    "PF2ER_VIPER_SOURCE_CARRIER_ORDINAL",
    "PF2ER_VIPER_SOURCE_ID",
    "PF2ER_VIPER_SOURCE_LOCATOR",
    "PF2ERViperSemanticError",
    "build_viper_semantic_package",
]

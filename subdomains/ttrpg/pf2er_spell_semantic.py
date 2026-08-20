"""Source-authenticated, source-free PF2ER spell semantics.

The first closure contains Summon Instrument only.  Acquisition locators,
source-shaped values, and receipts remain in the private evidence store; the
public package contains semantic rule references and executable intent.
"""

from __future__ import annotations

from copy import deepcopy
import hmac
import json
import re

from .pf2er_compiler.mechanics.source_authority import (
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
    SemanticPackage,
    build_semantic_entity,
    build_semantic_package,
    validate_public_semantic_definition,
)


PF2ER_RULESET_ID = "paizo:pf2er"
PF2ER_PLAYER_CORE_ONE_BOOK_ID = "paizo:player-core-one"
PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_ID = (
    "ttrpg:pf2er-player-core-one-spells"
)
PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_VERSION = "1.0.0"
PF2ER_SPELL_COMPILER_ID = "ttrpg:pf2er-spell-semantic-compiler"
PF2ER_SPELL_COMPILER_VERSION = "1.0.0"
PF2ER_SPELL_PROJECTION_ID = "ttrpg:pf2er-spell-definition"
PF2ER_SPELL_PROJECTION_VERSION = "1.0.0"
PF2ER_SPELL_EVIDENCE_AUTHORITY_ID = "ttrpg:pf2er-semantic-evidence"

PF2ER_SUMMON_INSTRUMENT_ENTITY_ID = "pf2er:summon-instrument"
PF2ER_SUMMON_INSTRUMENT_CAPABILITY = CapabilityRequirement(
    "gladiator:pf2er-summon-instrument-lifecycle",
    "1.0.0",
)
PF2ER_SUMMON_INSTRUMENT_MECHANIC = "summon-instrument-item-creation"
PF2ER_SUMMON_INSTRUMENT_SOURCE_ID = "core-pc1"
PF2ER_SUMMON_INSTRUMENT_LOCATOR = "361.3"
PF2ER_SUMMON_INSTRUMENT_RAW_DIGEST = (
    "bbe7f839aa2c59ada010a67249b70309e997d483ab4bbd341155dc732ff834ca"
)

_ORDINARY_ITEM_ID = "pf2er:item.musical-instrument-handheld"
_VIRTUOSO_ITEM_ID = (
    "pf2er:item.musical-instrument-handheld-virtuoso"
)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

_REVIEWED_SOURCE = {
    "Name": "Summon Instrument",
    "Icon": "spells/summon-instrument",
    "Rank": 1,
    "Kind": "cantrip",
    "Actions": "three",
    "Traits": ["cantrip", "concentrate", "manipulate"],
    "Traditions": ["arcane", "divine", "occult"],
    "Duration": "1 hour",
    "Description": {
        "~.p": (
            "You materialize a handheld musical instrument in your grasp. "
            "The instrument is typical for its type, but it plays for only "
            "you. It vanishes when the spell ends. If you cast summon "
            "instrument again, any instrument you previously summoned "
            "disappears."
        )
    },
    "Heightened": {
        "5th": "The instrument is instead a virtuoso handheld instrument."
    },
}

_PROJECTION_MANIFEST = {
    "schema": 1,
    "packageId": PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_ID,
    "packageVersion": PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_VERSION,
    "projectionId": PF2ER_SPELL_PROJECTION_ID,
    "projectionVersion": PF2ER_SPELL_PROJECTION_VERSION,
    "definitionSchema": 1,
    "entityKind": "ttrpg:spell",
    "selectedEntityIds": [PF2ER_SUMMON_INSTRUMENT_ENTITY_ID],
}
PF2ER_SPELL_PROJECTION_DIGEST = canonical_digest(
    _PROJECTION_MANIFEST,
    "PF2ER spell projection manifest",
)

_COMPILER_MANIFEST = {
    "schema": 1,
    "compilerId": PF2ER_SPELL_COMPILER_ID,
    "compilerVersion": PF2ER_SPELL_COMPILER_VERSION,
    "rulesetId": PF2ER_RULESET_ID,
    "bookId": PF2ER_PLAYER_CORE_ONE_BOOK_ID,
    "selectedEntityIds": [PF2ER_SUMMON_INSTRUMENT_ENTITY_ID],
    "reviewedRawDefinitionDigest": PF2ER_SUMMON_INSTRUMENT_RAW_DIGEST,
}
PF2ER_SPELL_COMPILER_DIGEST = canonical_digest(
    _COMPILER_MANIFEST,
    "PF2ER spell compiler manifest",
)


class PF2ERSpellSemanticError(ValueError):
    """The selected Player Core spell closure is invalid or has drifted."""


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise PF2ERSpellSemanticError(
            f"{label} must be a lowercase sha256 digest"
        )
    return value


def _project_summon_instrument() -> dict[str, object]:
    rules = [
        "pf2er.rule:duration",
        "pf2er.rule:spellcasting",
        "pf2er.rule:summon-instrument",
    ]
    definition: dict[str, object] = {
        "schema": 1,
        "id": PF2ER_SUMMON_INSTRUMENT_ENTITY_ID,
        "name": "Summon Instrument",
        "kind": "cantrip",
        "rank": 1,
        "actionCost": 3,
        "traits": ["cantrip", "concentrate", "manipulate"],
        "traditions": ["arcane", "divine", "occult"],
        "duration": {"seconds": 3600},
        "effect": {
            "type": "temporary-item-creation",
            "mechanicType": PF2ER_SUMMON_INSTRUMENT_MECHANIC,
            "duration": {"seconds": 3600},
            "createsInCasterGrasp": True,
            "ordinaryItemEntityId": _ORDINARY_ITEM_ID,
            "ownerOnlyMayPlay": True,
            "recastRemovesPriorOwnedItem": True,
            "expiryRemovesExactItem": True,
            "heightened": {
                "minimumCastRank": 5,
                "itemEntityId": _VIRTUOSO_ITEM_ID,
            },
            "reviewedDeferrals": [
                "especially-large-handheld-bulk-gm-ruling",
                "perform-action-and-instrument-modality",
                "physical-damage-type-gm-adjudication",
            ],
        },
        "reviewedDeferrals": [
            "especially-large-handheld-bulk-gm-ruling",
            "perform-action-and-instrument-modality",
            "physical-damage-type-gm-adjudication",
        ],
        "references": {"rules": rules},
        "rules": {
            "duration": {"ruleRef": "pf2er.rule:duration"},
            "spellcasting": {"ruleRef": "pf2er.rule:spellcasting"},
            "spell": {"ruleRef": "pf2er.rule:summon-instrument"},
        },
    }
    validate_public_semantic_definition(definition)
    return definition


def build_player_core_spell_semantic_package(
    *,
    authority: SourceAuthorityAdapter,
    expected_authority_digest: str,
    ruleset_digest: str,
    book_digest: str,
    semantic_generation: str,
    evidence_store: SemanticEvidenceStore,
) -> SemanticPackage:
    """Compile and seal the one-spell Summon Instrument package."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("PF2ER spell semantics require SourceAuthorityAdapter")
    if type(evidence_store) is not SemanticEvidenceStore:
        raise TypeError("PF2ER spell semantics require SemanticEvidenceStore")
    expected_authority_digest = _digest(
        expected_authority_digest,
        "expectedAuthorityDigest",
    )
    if not hmac.compare_digest(
        authority.snapshot.digest,
        expected_authority_digest,
    ):
        raise PF2ERSpellSemanticError("Player Core source authority drifted")
    if PF2ER_SUMMON_INSTRUMENT_SOURCE_ID not in authority.allowed_source_ids:
        raise PF2ERSpellSemanticError("Player Core source is not selected")
    if (
        authority.toc_label(
            PF2ER_SUMMON_INSTRUMENT_SOURCE_ID,
            PF2ER_SUMMON_INSTRUMENT_LOCATOR,
        )
        != "Summon Instrument"
        or authority.toc_content_path(
            PF2ER_SUMMON_INSTRUMENT_SOURCE_ID,
            PF2ER_SUMMON_INSTRUMENT_LOCATOR,
        )
        != ("Summon Instrument",)
    ):
        raise PF2ERSpellSemanticError(
            "Summon Instrument source target drifted"
        )
    selection = authority.validate_selection(
        authority.resolve(
            authority.address(
                source_id=PF2ER_SUMMON_INSTRUMENT_SOURCE_ID,
                locator=PF2ER_SUMMON_INSTRUMENT_LOCATOR,
            )
        )
    )
    raw_definition = json.loads(canonical_raw_bytes(selection.selected_value))
    if raw_definition != _REVIEWED_SOURCE:
        raise PF2ERSpellSemanticError("Summon Instrument source text drifted")
    raw_digest = canonical_digest(
        raw_definition,
        "raw PF2ER spell definition",
    )
    if not hmac.compare_digest(raw_digest, PF2ER_SUMMON_INSTRUMENT_RAW_DIGEST):
        raise PF2ERSpellSemanticError(
            "Summon Instrument raw definition digest drifted"
        )
    definition = _project_summon_instrument()
    projected_digest = canonical_digest(
        definition,
        "projected PF2ER spell definition",
    )
    record = SemanticEvidenceRecord.build(
        evidence_authority_id=PF2ER_SPELL_EVIDENCE_AUTHORITY_ID,
        entity_id=PF2ER_SUMMON_INSTRUMENT_ENTITY_ID,
        compiler_digest=PF2ER_SPELL_COMPILER_DIGEST,
        raw_definition_digest=raw_digest,
        projected_definition_digest=projected_digest,
        projection_id=PF2ER_SPELL_PROJECTION_ID,
        projection_version=PF2ER_SPELL_PROJECTION_VERSION,
        projection_digest=PF2ER_SPELL_PROJECTION_DIGEST,
        acquisition_receipt={
            "schema": 1,
            "kind": "pf2er-spell-acquisition",
            "authorityDigest": authority.snapshot.digest,
            "sourceSelection": selection.receipt.as_serialized(),
        },
        compiler_receipt={
            "schema": 1,
            "manifest": deepcopy(_COMPILER_MANIFEST),
            "digest": PF2ER_SPELL_COMPILER_DIGEST,
            "rawDefinition": deepcopy(raw_definition),
            "projection": deepcopy(_PROJECTION_MANIFEST),
        },
    )
    entity = build_semantic_entity(
        entity_id=PF2ER_SUMMON_INSTRUMENT_ENTITY_ID,
        entity_kind="ttrpg:spell",
        definition=definition,
        evidence_authority_id=PF2ER_SPELL_EVIDENCE_AUTHORITY_ID,
        evidence_record_digest=record.evidence_record_digest,
        compiler_digest=PF2ER_SPELL_COMPILER_DIGEST,
        raw_definition_digest=raw_digest,
        projection_id=PF2ER_SPELL_PROJECTION_ID,
        projection_version=PF2ER_SPELL_PROJECTION_VERSION,
        projection_digest=PF2ER_SPELL_PROJECTION_DIGEST,
        required_capabilities=(PF2ER_SUMMON_INSTRUMENT_CAPABILITY,),
    )
    package = build_semantic_package(
        package_id=PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_ID,
        version=PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_VERSION,
        ruleset_id=PF2ER_RULESET_ID,
        ruleset_digest=ruleset_digest,
        book_id=PF2ER_PLAYER_CORE_ONE_BOOK_ID,
        book_digest=book_digest,
        semantic_generation=semantic_generation,
        semantic_generation_digest=canonical_digest(
            {
                "schema": 1,
                "semanticGeneration": semantic_generation,
                "packageId": PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_ID,
                "packageVersion": PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_VERSION,
                "compilerDigest": PF2ER_SPELL_COMPILER_DIGEST,
                "projectionDigest": PF2ER_SPELL_PROJECTION_DIGEST,
                "entity": {
                    "entityId": entity.entity_id,
                    "semanticReceiptDigest": (
                        entity.receipt.semantic_receipt_digest
                    ),
                },
            },
            "PF2ER spell semantic generation",
        ),
        compiler_id=PF2ER_SPELL_COMPILER_ID,
        compiler_version=PF2ER_SPELL_COMPILER_VERSION,
        compiler_digest=PF2ER_SPELL_COMPILER_DIGEST,
        entities=(entity,),
    )
    evidence_store.provision_many((record,))
    return package


__all__ = [
    "PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_ID",
    "PF2ER_PLAYER_CORE_ONE_SPELL_PACKAGE_VERSION",
    "PF2ER_SPELL_COMPILER_DIGEST",
    "PF2ER_SPELL_PROJECTION_DIGEST",
    "PF2ER_SUMMON_INSTRUMENT_CAPABILITY",
    "PF2ER_SUMMON_INSTRUMENT_ENTITY_ID",
    "PF2ER_SUMMON_INSTRUMENT_LOCATOR",
    "PF2ER_SUMMON_INSTRUMENT_MECHANIC",
    "PF2ERSpellSemanticError",
    "build_player_core_spell_semantic_package",
]

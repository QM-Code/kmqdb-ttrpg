"""Publish source-authenticated references for portable creature spells.

The Gladiator runtime identifies spells with compact runtime IDs such as
``breathe-fire``.  Those IDs are intentionally not semantic entity IDs.  This
operator-only compiler publishes one source-free ``ttrpg:spell`` entity for
each executable portable spell and binds the runtime ID explicitly in the
public definition.  Acquisition addresses and raw source records remain in
the private evidence store.
"""

from __future__ import annotations

from copy import deepcopy
import hmac
import json
from types import MappingProxyType

from scripts.pf2er_legacy_roster_semantic import (
    PF2ER_LEGACY_ROSTER_AUTHORITY_DIGEST,
    PF2ER_LEGACY_ROSTER_RULESET_DIGEST,
)
from subdomains.ttrpg.pf2er_compiler.mechanics.source_authority import (
    SourceAuthorityAdapter,
    canonical_raw_bytes,
)
from subdomains.ttrpg.semantic_evidence import (
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
    canonical_digest,
)
from subdomains.ttrpg.semantic_packages import (
    SemanticPackage,
    build_semantic_entity,
    build_semantic_package,
    validate_public_semantic_definition,
)
from subdomains.ttrpg.pf2er_semantic import (
    PF2ER_PLAYER_CORE_ONE_BOOK_ID,
    PF2ER_RULESET_ID,
)


PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_ID = (
    "ttrpg:pf2er-player-core-one-portable-spell-references"
)
PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_VERSION = "1.0.0"
PF2ER_PORTABLE_SPELL_REFERENCE_SEMANTIC_GENERATION = (
    "ttrpg:pf2er-player-core-one-portable-spell-references-publication-1"
)
PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_ID = (
    "ttrpg:pf2er-portable-spell-reference-compiler"
)
PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_VERSION = "1.0.0"
PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_ID = (
    "ttrpg:pf2er-portable-spell-reference-definition"
)
PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_VERSION = "1.0.0"
PF2ER_PORTABLE_SPELL_REFERENCE_EVIDENCE_AUTHORITY_ID = (
    "ttrpg:pf2er-portable-spell-reference-evidence"
)
PF2ER_PORTABLE_SPELL_REFERENCE_SOURCE_ID = "core-pc1"
PF2ER_PORTABLE_SPELL_REFERENCE_BOOK_DIGEST = (
    "5839c0004e279d1d23c3ca2db52f80eb0d07c74f479406712e1959c96d7d13de"
)

# runtime ID: (semantic entity ID, exact source name, private source locator)
PF2ER_PORTABLE_SPELL_REFERENCE_TARGETS = MappingProxyType(
    {
        "bless": ("pf2er:spell-reference.bless", "Bless", "318.3"),
        "breathe-fire": (
            "pf2er:spell-reference.breathe-fire",
            "Breathe Fire",
            "319.2",
        ),
        "caustic-blast": (
            "pf2er:spell-reference.caustic-blast",
            "Caustic Blast",
            "319.6",
        ),
        "courageous-anthem": (
            "pf2er:spell-reference.courageous-anthem",
            "Courageous Anthem",
            "370.5",
        ),
        "fleet-step": (
            "pf2er:spell-reference.fleet-step",
            "Fleet Step",
            "332.1",
        ),
        "grease": ("pf2er:spell-reference.grease", "Grease", "333.8"),
        "heal": ("pf2er:spell-reference.heal", "Heal", "335.2"),
        "ignition": (
            "pf2er:spell-reference.ignition",
            "Ignition",
            "336.5",
        ),
        "light": ("pf2er:spell-reference.light", "Light", "340.8"),
        "pummeling-rubble": (
            "pf2er:spell-reference.pummeling-rubble",
            "Pummeling Rubble",
            "351.4",
        ),
        "runic-weapon": (
            "pf2er:spell-reference.runic-weapon",
            "Runic Weapon",
            "354.3",
        ),
        "soothe": ("pf2er:spell-reference.soothe", "Soothe", "357.6"),
        "summon-instrument": (
            "pf2er:spell-reference.summon-instrument",
            "Summon Instrument",
            "361.3",
        ),
        "tangle-vine": (
            "pf2er:spell-reference.tangle-vine",
            "Tangle Vine",
            "362.4",
        ),
        "telekinetic-hand": (
            "pf2er:spell-reference.telekinetic-hand",
            "Telekinetic Hand",
            "362.6",
        ),
        "telekinetic-projectile": (
            "pf2er:spell-reference.telekinetic-projectile",
            "Telekinetic Projectile",
            "363.2",
        ),
    }
)

_PROJECTION_MANIFEST = {
    "schema": 1,
    "packageId": PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_ID,
    "packageVersion": PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_VERSION,
    "projectionId": PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_ID,
    "projectionVersion": PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_VERSION,
    "definitionSchema": 1,
    "entityKind": "ttrpg:spell",
    "selectedEntityIds": sorted(
        target[0] for target in PF2ER_PORTABLE_SPELL_REFERENCE_TARGETS.values()
    ),
    "runtimeIds": sorted(PF2ER_PORTABLE_SPELL_REFERENCE_TARGETS),
    "descriptionPolicy": "normalized-source-prose",
}
PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_DIGEST = canonical_digest(
    _PROJECTION_MANIFEST,
    "PF2ER portable spell reference projection manifest",
)

_COMPILER_MANIFEST = {
    "schema": 1,
    "compilerId": PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_ID,
    "compilerVersion": PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_VERSION,
    "rulesetId": PF2ER_RULESET_ID,
    "bookId": PF2ER_PLAYER_CORE_ONE_BOOK_ID,
    "targets": [
        {
            "runtimeId": runtime_id,
            "entityId": target[0],
            "sourceId": PF2ER_PORTABLE_SPELL_REFERENCE_SOURCE_ID,
            "locator": target[2],
        }
        for runtime_id, target in sorted(
            PF2ER_PORTABLE_SPELL_REFERENCE_TARGETS.items()
        )
    ],
}
PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_DIGEST = canonical_digest(
    _COMPILER_MANIFEST,
    "PF2ER portable spell reference compiler manifest",
)


class PF2ERPortableSpellReferenceError(ValueError):
    """The selected Player Core spell-reference closure is invalid."""


def _description_text(value: object, *, runtime_id: str) -> str:
    if type(value) is not dict or not set(value).issubset({"~.p", "~.ul"}):
        raise PF2ERPortableSpellReferenceError(
            f"portable spell description is invalid: {runtime_id}"
        )
    paragraph = value.get("~.p")
    bullets = value.get("~.ul", [])
    if (
        type(paragraph) is not str
        or not paragraph
        or paragraph != paragraph.strip()
        or type(bullets) is not list
        or any(
            type(item) is not str or not item or item != item.strip()
            for item in bullets
        )
    ):
        raise PF2ERPortableSpellReferenceError(
            f"portable spell description is invalid: {runtime_id}"
        )
    description = paragraph
    if bullets:
        description += "\n\n" + "\n".join(f"- {item}" for item in bullets)
    if len(description) > 16 * 1024:
        raise PF2ERPortableSpellReferenceError(
            f"portable spell description exceeds its bound: {runtime_id}"
        )
    return description


def build_portable_spell_reference_semantic_package(
    *,
    authority: SourceAuthorityAdapter,
    evidence_store: SemanticEvidenceStore,
) -> SemanticPackage:
    """Compile and seal the exact portable-spell prose reference closure."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("portable spell references require SourceAuthorityAdapter")
    if type(evidence_store) is not SemanticEvidenceStore:
        raise TypeError("portable spell references require SemanticEvidenceStore")
    if not hmac.compare_digest(
        authority.snapshot.digest,
        PF2ER_LEGACY_ROSTER_AUTHORITY_DIGEST,
    ):
        raise PF2ERPortableSpellReferenceError(
            "Player Core source authority drifted"
        )
    if PF2ER_PORTABLE_SPELL_REFERENCE_SOURCE_ID not in authority.allowed_source_ids:
        raise PF2ERPortableSpellReferenceError("Player Core source is not selected")

    entities = []
    evidence_records = []
    for runtime_id, (entity_id, name, locator) in sorted(
        PF2ER_PORTABLE_SPELL_REFERENCE_TARGETS.items()
    ):
        content_path = authority.toc_content_path(
            PF2ER_PORTABLE_SPELL_REFERENCE_SOURCE_ID,
            locator,
        )
        if (
            authority.toc_label(PF2ER_PORTABLE_SPELL_REFERENCE_SOURCE_ID, locator)
            != name
            or not content_path
            or content_path[-1] != name
        ):
            raise PF2ERPortableSpellReferenceError(
                f"portable spell source target drifted: {runtime_id}"
            )
        selection = authority.validate_selection(
            authority.resolve(
                authority.address(
                    source_id=PF2ER_PORTABLE_SPELL_REFERENCE_SOURCE_ID,
                    locator=locator,
                )
            )
        )
        raw_definition = json.loads(canonical_raw_bytes(selection.selected_value))
        if type(raw_definition) is not dict or raw_definition.get("Name") != name:
            raise PF2ERPortableSpellReferenceError(
                f"portable spell source definition drifted: {runtime_id}"
            )
        definition = {
            "schema": 1,
            "id": entity_id,
            "runtimeId": runtime_id,
            "name": name,
            "description": _description_text(
                raw_definition.get("Description"),
                runtime_id=runtime_id,
            ),
        }
        validate_public_semantic_definition(definition)
        raw_digest = canonical_digest(
            raw_definition,
            "raw PF2ER portable spell reference definition",
        )
        projected_digest = canonical_digest(
            definition,
            "projected PF2ER portable spell reference definition",
        )
        record = SemanticEvidenceRecord.build(
            evidence_authority_id=(
                PF2ER_PORTABLE_SPELL_REFERENCE_EVIDENCE_AUTHORITY_ID
            ),
            entity_id=entity_id,
            compiler_digest=PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_DIGEST,
            raw_definition_digest=raw_digest,
            projected_definition_digest=projected_digest,
            projection_id=PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_ID,
            projection_version=(
                PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_VERSION
            ),
            projection_digest=PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_DIGEST,
            acquisition_receipt={
                "schema": 1,
                "kind": "pf2er-portable-spell-reference-acquisition",
                "authorityDigest": authority.snapshot.digest,
                "sourceSelection": selection.receipt.as_serialized(),
            },
            compiler_receipt={
                "schema": 1,
                "manifest": deepcopy(_COMPILER_MANIFEST),
                "digest": PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_DIGEST,
                "rawDefinition": deepcopy(raw_definition),
                "projection": deepcopy(_PROJECTION_MANIFEST),
            },
        )
        evidence_records.append(record)
        entities.append(
            build_semantic_entity(
                entity_id=entity_id,
                entity_kind="ttrpg:spell",
                definition=definition,
                evidence_authority_id=(
                    PF2ER_PORTABLE_SPELL_REFERENCE_EVIDENCE_AUTHORITY_ID
                ),
                evidence_record_digest=record.evidence_record_digest,
                compiler_digest=PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_DIGEST,
                raw_definition_digest=raw_digest,
                projection_id=PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_ID,
                projection_version=(
                    PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_VERSION
                ),
                projection_digest=(
                    PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_DIGEST
                ),
            )
        )

    generation_digest = canonical_digest(
        {
            "schema": 1,
            "semanticGeneration": (
                PF2ER_PORTABLE_SPELL_REFERENCE_SEMANTIC_GENERATION
            ),
            "packageId": PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_ID,
            "packageVersion": PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_VERSION,
            "authorityDigest": authority.snapshot.digest,
            "compilerDigest": PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_DIGEST,
            "projectionDigest": PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_DIGEST,
            "entities": [
                {
                    "entityId": entity.entity_id,
                    "definitionDigest": entity.definition_digest,
                    "semanticReceiptDigest": (
                        entity.receipt.semantic_receipt_digest
                    ),
                }
                for entity in entities
            ],
        },
        "PF2ER portable spell reference semantic generation",
    )
    package = build_semantic_package(
        package_id=PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_ID,
        version=PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_VERSION,
        ruleset_id=PF2ER_RULESET_ID,
        ruleset_digest=PF2ER_LEGACY_ROSTER_RULESET_DIGEST,
        book_id=PF2ER_PLAYER_CORE_ONE_BOOK_ID,
        book_digest=PF2ER_PORTABLE_SPELL_REFERENCE_BOOK_DIGEST,
        semantic_generation=(
            PF2ER_PORTABLE_SPELL_REFERENCE_SEMANTIC_GENERATION
        ),
        semantic_generation_digest=generation_digest,
        compiler_id=PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_ID,
        compiler_version=PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_VERSION,
        compiler_digest=PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_DIGEST,
        entities=tuple(entities),
    )
    evidence_store.provision_many(tuple(evidence_records))
    return package


__all__ = [
    "PF2ER_PORTABLE_SPELL_REFERENCE_COMPILER_DIGEST",
    "PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_ID",
    "PF2ER_PORTABLE_SPELL_REFERENCE_PACKAGE_VERSION",
    "PF2ER_PORTABLE_SPELL_REFERENCE_PROJECTION_DIGEST",
    "PF2ER_PORTABLE_SPELL_REFERENCE_TARGETS",
    "PF2ERPortableSpellReferenceError",
    "build_portable_spell_reference_semantic_package",
]

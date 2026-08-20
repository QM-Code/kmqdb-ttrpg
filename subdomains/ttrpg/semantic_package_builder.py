"""Build authenticated TTRPG creature packages through an explicit compiler set."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Callable, Sequence

from .pf2er_compiler.mechanics.source_authority import SourceAuthorityAdapter
from .semantic_compiler import SemanticCompilerPackage, SemanticCompilerSet
from .semantic_evidence import (
    SemanticEvidenceRecord,
    SemanticEvidenceStore,
    canonical_digest,
    canonical_json,
)
from .semantic_packages import (
    AssetRef,
    CapabilityRequirement,
    ProviderCarrierRelationship,
    SemanticPackage,
    SemanticPackageError,
    build_semantic_entity,
    build_semantic_package,
    validate_public_semantic_definition,
)


_ID_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*:"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)
_VERSION_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)


class SemanticPackageBuilderError(ValueError):
    """A requested package is outside its authority or compiler selection."""


def _id(value: object, label: str) -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        raise SemanticPackageBuilderError(
            f"{label} must be a normalized namespaced ID"
        )
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SemanticPackageBuilderError(f"{label} must be non-empty trimmed text")
    return value


def _version(value: object, label: str) -> str:
    if type(value) is not str or _VERSION_RE.fullmatch(value) is None:
        raise SemanticPackageBuilderError(
            f"{label} must be a normalized x.y.z version"
        )
    return value


def _sorted_unique(values: Sequence[object], label: str) -> tuple[object, ...]:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise SemanticPackageBuilderError(f"{label} contains duplicates")
    return tuple(sorted(items))


@dataclass(frozen=True, order=True, slots=True)
class SourceCreatureTarget:
    """One stable semantic identity bound to one authenticated source target."""

    entity_id: str
    source_id: str
    locator: str
    required_capabilities: tuple[CapabilityRequirement, ...] = ()
    asset_refs: tuple[AssetRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_id", _id(self.entity_id, "entityId"))
        object.__setattr__(self, "source_id", _text(self.source_id, "sourceId"))
        object.__setattr__(self, "locator", _text(self.locator, "locator"))
        if not isinstance(self.required_capabilities, tuple) or any(
            not isinstance(item, CapabilityRequirement)
            for item in self.required_capabilities
        ):
            raise SemanticPackageBuilderError(
                "required capabilities must be a tuple of CapabilityRequirement values"
            )
        if not isinstance(self.asset_refs, tuple) or any(
            not isinstance(item, AssetRef) for item in self.asset_refs
        ):
            raise SemanticPackageBuilderError(
                "asset references must be a tuple of AssetRef values"
            )
        object.__setattr__(
            self,
            "required_capabilities",
            _sorted_unique(self.required_capabilities, "required capabilities"),
        )
        object.__setattr__(
            self,
            "asset_refs",
            _sorted_unique(self.asset_refs, "asset references"),
        )


@dataclass(frozen=True, slots=True)
class SemanticDefinitionProjector:
    """One package-selected, schema-aware public-definition projector."""

    package_id: str
    package_version: str
    projection_id: str
    projection_version: str
    definition_schema: int
    project_creature: Callable[[dict[str, object], str], dict[str, object]] = field(
        compare=False,
        repr=False,
    )
    projection_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "package_id", _id(self.package_id, "packageId"))
        object.__setattr__(
            self, "package_version", _version(self.package_version, "packageVersion")
        )
        object.__setattr__(
            self, "projection_id", _id(self.projection_id, "projectionId")
        )
        object.__setattr__(
            self,
            "projection_version",
            _version(self.projection_version, "projectionVersion"),
        )
        if type(self.definition_schema) is not int or self.definition_schema < 1:
            raise SemanticPackageBuilderError(
                "definitionSchema must be a positive integer"
            )
        if not callable(self.project_creature):
            raise SemanticPackageBuilderError("projectCreature must be callable")
        object.__setattr__(
            self,
            "projection_digest",
            canonical_digest(self.manifest, "semantic projection manifest"),
        )

    @property
    def manifest(self) -> dict[str, object]:
        return {
            "schema": 1,
            "packageId": self.package_id,
            "packageVersion": self.package_version,
            "projectionId": self.projection_id,
            "projectionVersion": self.projection_version,
            "definitionSchema": self.definition_schema,
        }

    def project(
        self,
        raw_definition: dict[str, object],
        entity_id: str,
    ) -> dict[str, object]:
        if type(raw_definition) is not dict:
            raise SemanticPackageBuilderError(
                "semantic compiler returned a non-object creature definition"
            )
        entity_id = _id(entity_id, "entityId")
        # Projectors receive a strict detached copy and cannot mutate the
        # private raw compiler result retained by the evidence digest.
        detached = json.loads(
            canonical_json(raw_definition, "raw compiler definition").decode("utf-8")
        )
        projected = self.project_creature(detached, entity_id)
        if type(projected) is not dict:
            raise SemanticPackageBuilderError(
                "semantic definition projector returned a non-object"
            )
        if projected.get("schema") != self.definition_schema:
            raise SemanticPackageBuilderError(
                "semantic definition projector returned the wrong definition schema"
            )
        if projected.get("id") != entity_id:
            raise SemanticPackageBuilderError(
                "semantic definition projector returned the wrong entity identity"
            )
        try:
            validate_public_semantic_definition(projected)
        except SemanticPackageError as exc:
            raise SemanticPackageBuilderError(str(exc)) from exc
        return json.loads(
            canonical_json(projected, "projected semantic definition").decode("utf-8")
        )


def _selected_package(
    compiler_set: SemanticCompilerSet,
    package_id: str,
    version: str,
    book_id: str,
) -> SemanticCompilerPackage:
    matches = tuple(
        item
        for item in compiler_set.identity.packages
        if item.package_id == package_id and item.version == version
    )
    if len(matches) != 1:
        raise SemanticPackageBuilderError(
            "semantic package is not selected by the compiler set"
        )
    selected = matches[0]
    if book_id not in selected.book_ids:
        raise SemanticPackageBuilderError(
            "semantic package book is not selected by the compiler set"
        )
    return selected


def build_creature_semantic_package(
    *,
    authority: SourceAuthorityAdapter,
    compiler_set: SemanticCompilerSet,
    package_id: str,
    version: str,
    ruleset_digest: str,
    book_id: str,
    book_digest: str,
    semantic_generation: str,
    creatures: Sequence[SourceCreatureTarget],
    projector: SemanticDefinitionProjector,
    evidence_authority_id: str,
    evidence_store: SemanticEvidenceStore,
    relationships: Sequence[ProviderCarrierRelationship] = (),
) -> SemanticPackage:
    """Compile and seal one selected book's exact source creature package."""

    if type(authority) is not SourceAuthorityAdapter:
        raise TypeError("semantic package builder requires SourceAuthorityAdapter")
    if type(compiler_set) is not SemanticCompilerSet:
        raise TypeError("semantic package builder requires SemanticCompilerSet")
    package_id = _id(package_id, "packageId")
    book_id = _id(book_id, "bookId")
    semantic_generation = _id(semantic_generation, "semanticGeneration")
    selected_package = _selected_package(
        compiler_set, package_id, version, book_id
    )
    if not isinstance(projector, SemanticDefinitionProjector):
        raise TypeError(
            "semantic package builder requires SemanticDefinitionProjector"
        )
    if (
        projector.package_id != selected_package.package_id
        or projector.package_version != selected_package.version
    ):
        raise SemanticPackageBuilderError(
            "semantic definition projector is not selected by the compiler package"
        )
    evidence_authority_id = _id(
        evidence_authority_id, "evidenceAuthorityId"
    )
    if type(evidence_store) is not SemanticEvidenceStore:
        raise TypeError("semantic package builder requires SemanticEvidenceStore")
    if not isinstance(creatures, (tuple, list)) or not creatures:
        raise SemanticPackageBuilderError("creatures must be a non-empty sequence")
    if any(not isinstance(item, SourceCreatureTarget) for item in creatures):
        raise SemanticPackageBuilderError("creatures contain an invalid target")
    ordered = tuple(sorted(creatures))
    if len({item.entity_id for item in ordered}) != len(ordered):
        raise SemanticPackageBuilderError("creatures contain duplicate entity IDs")
    source_targets = tuple((item.source_id, item.locator) for item in ordered)
    if len(set(source_targets)) != len(source_targets):
        raise SemanticPackageBuilderError("creatures contain duplicate source targets")
    if not isinstance(relationships, (tuple, list)) or any(
        not isinstance(item, ProviderCarrierRelationship) for item in relationships
    ):
        raise SemanticPackageBuilderError(
            "relationships contain an invalid provider/carrier link"
        )

    entities = []
    evidence_records = []
    for target in ordered:
        address = authority.address(
            source_id=target.source_id,
            locator=target.locator,
        )
        source_selection = authority.validate_selection(authority.resolve(address))
        raw_definition = compiler_set.compile_source_creature(
            authority,
            target.source_id,
            target.locator,
        )
        if type(raw_definition) is not dict:
            raise SemanticPackageBuilderError(
                "semantic compiler returned a non-object creature definition"
            )
        raw_definition_digest = canonical_digest(
            raw_definition, "raw compiler definition"
        )
        definition = projector.project(raw_definition, target.entity_id)
        projected_definition_digest = canonical_digest(
            definition, "projected semantic definition"
        )
        compiler_receipt = {
            "schema": 1,
            "manifest": compiler_set.manifest,
            "digest": compiler_set.digest,
            "selectedPackage": selected_package.to_dict(),
            "projection": projector.manifest,
        }
        evidence_record = SemanticEvidenceRecord.build(
            evidence_authority_id=evidence_authority_id,
            entity_id=target.entity_id,
            compiler_digest=compiler_set.digest,
            raw_definition_digest=raw_definition_digest,
            projected_definition_digest=projected_definition_digest,
            projection_id=projector.projection_id,
            projection_version=projector.projection_version,
            projection_digest=projector.projection_digest,
            acquisition_receipt=source_selection.receipt.as_serialized(),
            compiler_receipt=compiler_receipt,
        )
        evidence_records.append(evidence_record)
        entities.append(
            build_semantic_entity(
                entity_id=target.entity_id,
                entity_kind="ttrpg:creature",
                definition=definition,
                evidence_authority_id=evidence_authority_id,
                evidence_record_digest=evidence_record.evidence_record_digest,
                compiler_digest=compiler_set.digest,
                raw_definition_digest=raw_definition_digest,
                projection_id=projector.projection_id,
                projection_version=projector.projection_version,
                projection_digest=projector.projection_digest,
                required_capabilities=target.required_capabilities,
                asset_refs=target.asset_refs,
            )
        )

    package = build_semantic_package(
        package_id=package_id,
        version=version,
        ruleset_id=compiler_set.identity.ruleset_id,
        ruleset_digest=ruleset_digest,
        book_id=book_id,
        book_digest=book_digest,
        semantic_generation=semantic_generation,
        semantic_generation_digest=canonical_digest(
            {
                "schema": 1,
                "semanticGeneration": semantic_generation,
                "packageId": package_id,
                "packageVersion": version,
                "compilerDigest": compiler_set.digest,
                "projectionDigest": projector.projection_digest,
                "entities": [
                    {
                        "entityId": entity.entity_id,
                        "definitionDigest": entity.definition_digest,
                        "evidenceRecordDigest": (
                            entity.receipt.evidence_record_digest
                        ),
                    }
                    for entity in entities
                ],
            },
            "semantic generation",
        ),
        compiler_id=compiler_set.identity.compiler_id,
        compiler_version=compiler_set.identity.compiler_version,
        compiler_digest=compiler_set.digest,
        entities=tuple(entities),
        relationships=tuple(relationships),
    )
    evidence_store.provision_many(tuple(evidence_records))
    return package


__all__ = [
    "SemanticPackageBuilderError",
    "SemanticDefinitionProjector",
    "SourceCreatureTarget",
    "build_creature_semantic_package",
]

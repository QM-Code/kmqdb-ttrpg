"""TTRPG-owned, transport-neutral semantic package artifacts.

Compiled definitions and provenance stay opaque; this is not a rule language.
"""

from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable, Sequence


_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*:[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_VERSION_RE = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

# Acquisition evidence belongs exclusively to TTRPG's private evidence store.
# This is a validator, not a scrubber: a projector must explicitly translate a
# compiler output before this module will seal it as a public definition.
_FORBIDDEN_PUBLIC_DEFINITION_KEYS = frozenset(
    {
        "address",
        "assetPath",
        "authorityDigest",
        "blockSha256",
        "cachePath",
        "carrierPath",
        "contentPath",
        "icon",
        "iconPath",
        "imagePath",
        "libraryPath",
        "locator",
        "memberSha256",
        "rawIconPath",
        "sectionId",
        "selectionPath",
        "selectionSha256",
        "sourceAddress",
        "sourceAddressSha256",
        "sourceDeferredDependencies",
        "sourceId",
        "sourceOccurrenceId",
        "sourcePath",
        "sourceProvenance",
        "sourceProvenanceDigest",
        "sourceSpan",
        "sourceTextSha256",
        "sourceToken",
        "sourceTokenIndex",
        "statCompilation",
        "targetPath",
        "valueSha256",
    }
)


class SemanticPackageError(ValueError):
    """A semantic package value is malformed or fails its digest fence."""


class _FactoryOnly:
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("semantic contracts must be created through their builders")


def _id(value: object, label: str) -> str:
    if type(value) is not str or not _ID_RE.fullmatch(value):
        raise SemanticPackageError(f"{label} must be a normalized namespaced ID")
    return value

def _version(value: object, label: str) -> str:
    if type(value) is not str or not _VERSION_RE.fullmatch(value):
        raise SemanticPackageError(f"{label} must be a normalized x.y.z version")
    return value

def _digest(value: object, label: str) -> str:
    if type(value) is not str or not _DIGEST_RE.fullmatch(value):
        raise SemanticPackageError(f"{label} must be a lowercase sha256 digest")
    return value

def _exact_keys(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise SemanticPackageError(f"{label} must have exactly {sorted(keys)}")
    return value

def _strict_json(value: object, label: str) -> None:
    """Reject Python extensions that json.dumps would silently coerce."""
    if value is None or type(value) in {bool, str, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise SemanticPackageError(f"{label} contains a non-finite number")
        return
    if type(value) is list:
        for item in value:
            _strict_json(item, label)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise SemanticPackageError(f"{label} contains a non-string object key")
            _strict_json(item, label)
        return
    raise SemanticPackageError(f"{label} is not strict JSON-compatible data")

def _canonical(value: object, label: str = "value") -> bytes:
    _strict_json(value, label)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:  # defensive after _strict_json
        raise SemanticPackageError(f"{label} is not JSON-compatible") from exc

def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def _decoded(value: bytes) -> Any:
    return json.loads(value.decode("utf-8"))

def _sorted_unique(values: Iterable[Any], label: str) -> tuple[Any, ...]:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise SemanticPackageError(f"{label} contains duplicates")
    return tuple(sorted(items))


def _create(contract: type[Any], **values: object) -> Any:
    instance = object.__new__(contract)
    for name, value in values.items():
        object.__setattr__(instance, name, value)
    return instance


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def public_definition_acquisition_paths(value: object) -> tuple[str, ...]:
    """Return every acquisition-only field in one prospective definition.

    This deliberately does not rewrite values.  It is the final closed
    boundary after a ruleset-specific projector has translated the compiler
    output into its public semantic schema.
    """

    paths: list[str] = []

    def walk(item: object, path: str) -> None:
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    continue
                child_path = f"{path}/{_pointer_token(key)}"
                if key in _FORBIDDEN_PUBLIC_DEFINITION_KEYS:
                    paths.append(child_path)
                walk(child, child_path)
        elif type(item) is list:
            for index, child in enumerate(item):
                walk(child, f"{path}/{index}")

    walk(value, "")
    return tuple(sorted(set(paths)))


def validate_public_semantic_definition(value: object) -> None:
    if type(value) is not dict:
        raise SemanticPackageError("compiled definition must be a JSON object")
    _strict_json(value, "compiled definition")
    paths = public_definition_acquisition_paths(value)
    if paths:
        preview = ", ".join(paths[:8])
        if len(paths) > 8:
            preview += f", ... ({len(paths)} fields)"
        raise SemanticPackageError(
            "public semantic definition contains acquisition-only fields: "
            + preview
        )


@dataclass(frozen=True, order=True)
class CapabilityRequirement:
    capability_id: str
    contract_version: str
    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_id", _id(self.capability_id, "capabilityId"))
        object.__setattr__(
            self, "contract_version", _version(self.contract_version, "capability contractVersion")
        )
    def to_dict(self) -> dict[str, str]:
        return {"capabilityId": self.capability_id, "contractVersion": self.contract_version}
    @classmethod
    def from_dict(cls, value: object) -> CapabilityRequirement:
        packet = _exact_keys(value, {"capabilityId", "contractVersion"}, "capability requirement")
        return cls(packet["capabilityId"], packet["contractVersion"])

@dataclass(frozen=True, order=True)
class AssetRef:
    asset_id: str
    asset_digest: str
    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _id(self.asset_id, "assetId"))
        object.__setattr__(self, "asset_digest", _digest(self.asset_digest, "assetDigest"))
    def to_dict(self) -> dict[str, str]:
        return {"assetId": self.asset_id, "assetDigest": self.asset_digest}
    @classmethod
    def from_dict(cls, value: object) -> AssetRef:
        packet = _exact_keys(value, {"assetId", "assetDigest"}, "asset reference")
        return cls(packet["assetId"], packet["assetDigest"])

@dataclass(frozen=True, order=True)
class ProviderCarrierRelationship:
    relationship_id: str
    provider_entity_id: str
    carrier_entity_id: str
    def __post_init__(self) -> None:
        object.__setattr__(self, "relationship_id", _id(self.relationship_id, "relationshipId"))
        object.__setattr__(
            self, "provider_entity_id", _id(self.provider_entity_id, "providerEntityId")
        )
        object.__setattr__(
            self, "carrier_entity_id", _id(self.carrier_entity_id, "carrierEntityId")
        )
        if self.provider_entity_id == self.carrier_entity_id:
            raise SemanticPackageError("provider and carrier must be distinct entities")
    def to_dict(self) -> dict[str, str]:
        return {
            "relationshipId": self.relationship_id,
            "providerEntityId": self.provider_entity_id,
            "carrierEntityId": self.carrier_entity_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> ProviderCarrierRelationship:
        packet = _exact_keys(
            value,
            {"relationshipId", "providerEntityId", "carrierEntityId"},
            "provider/carrier relationship",
        )
        return cls(packet["relationshipId"], packet["providerEntityId"], packet["carrierEntityId"])

@dataclass(frozen=True, init=False)
class SemanticReceipt(_FactoryOnly):
    """Public digest chain to TTRPG-private acquisition evidence."""

    evidence_authority_id: str
    evidence_record_digest: str
    compiler_digest: str
    raw_definition_digest: str
    projected_definition_digest: str
    projection_id: str
    projection_version: str
    projection_digest: str
    semantic_receipt_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": 2,
            "evidenceAuthorityId": self.evidence_authority_id,
            "evidenceRecordDigest": self.evidence_record_digest,
            "compilerDigest": self.compiler_digest,
            "rawDefinitionDigest": self.raw_definition_digest,
            "projectedDefinitionDigest": self.projected_definition_digest,
            "projectionId": self.projection_id,
            "projectionVersion": self.projection_version,
            "projectionDigest": self.projection_digest,
            "semanticReceiptDigest": self.semantic_receipt_digest,
        }

    @classmethod
    def build(
        cls,
        *,
        entity_id: str,
        evidence_authority_id: str,
        evidence_record_digest: str,
        compiler_digest: str,
        raw_definition_digest: str,
        projected_definition_digest: str,
        projection_id: str,
        projection_version: str,
        projection_digest: str,
        expected_semantic_receipt_digest: str | None = None,
    ) -> SemanticReceipt:
        entity_id = _id(entity_id, "entityId")
        values = {
            "evidence_authority_id": _id(
                evidence_authority_id, "evidenceAuthorityId"
            ),
            "evidence_record_digest": _digest(
                evidence_record_digest, "evidenceRecordDigest"
            ),
            "compiler_digest": _digest(compiler_digest, "compilerDigest"),
            "raw_definition_digest": _digest(
                raw_definition_digest, "rawDefinitionDigest"
            ),
            "projected_definition_digest": _digest(
                projected_definition_digest, "projectedDefinitionDigest"
            ),
            "projection_id": _id(projection_id, "projectionId"),
            "projection_version": _version(
                projection_version, "projectionVersion"
            ),
            "projection_digest": _digest(
                projection_digest, "projectionDigest"
            ),
        }
        receipt_packet = {
            "schema": 2,
            "entityId": entity_id,
            "evidenceAuthorityId": values["evidence_authority_id"],
            "evidenceRecordDigest": values["evidence_record_digest"],
            "compilerDigest": values["compiler_digest"],
            "rawDefinitionDigest": values["raw_definition_digest"],
            "projectedDefinitionDigest": values[
                "projected_definition_digest"
            ],
            "projectionId": values["projection_id"],
            "projectionVersion": values["projection_version"],
            "projectionDigest": values["projection_digest"],
        }
        receipt_digest = _sha(_canonical(receipt_packet, "semantic receipt"))
        if (
            expected_semantic_receipt_digest is not None
            and _digest(expected_semantic_receipt_digest, "semanticReceiptDigest")
            != receipt_digest
        ):
            raise SemanticPackageError("semantic receipt digest mismatch")
        return _create(
            cls,
            **values,
            semantic_receipt_digest=receipt_digest,
        )

@dataclass(frozen=True, init=False)
class SemanticEntity(_FactoryOnly):
    entity_id: str
    entity_kind: str
    _definition_json: bytes
    definition_digest: str
    receipt: SemanticReceipt
    required_capabilities: tuple[CapabilityRequirement, ...]
    asset_refs: tuple[AssetRef, ...]
    @property
    def definition(self) -> dict[str, Any]:
        return _decoded(self._definition_json)
    def to_dict(self) -> dict[str, object]:
        return {
            "entityId": self.entity_id,
            "entityKind": self.entity_kind,
            "definition": self.definition,
            "definitionDigest": self.definition_digest,
            "receipt": self.receipt.to_dict(),
            "requiredCapabilities": [item.to_dict() for item in self.required_capabilities],
            "assetRefs": [item.to_dict() for item in self.asset_refs],
        }

    @classmethod
    def from_dict(cls, value: object) -> SemanticEntity:
        packet = _exact_keys(
            value,
            {
                "entityId", "entityKind", "definition", "definitionDigest",
                "receipt", "requiredCapabilities", "assetRefs",
            },
            "semantic entity",
        )
        receipt = _exact_keys(
            packet["receipt"],
            {
                "schema", "evidenceAuthorityId", "evidenceRecordDigest",
                "compilerDigest", "rawDefinitionDigest",
                "projectedDefinitionDigest", "projectionId",
                "projectionVersion", "projectionDigest",
                "semanticReceiptDigest",
            },
            "semantic receipt",
        )
        if receipt["schema"] != 2:
            raise SemanticPackageError("semantic receipt schema must be 2")
        if receipt["projectedDefinitionDigest"] != packet["definitionDigest"]:
            raise SemanticPackageError("entity and receipt definition digests disagree")
        capabilities = packet["requiredCapabilities"]
        assets = packet["assetRefs"]
        if type(capabilities) is not list or type(assets) is not list:
            raise SemanticPackageError("entity capability and asset references must be lists")
        return build_semantic_entity(
            entity_id=packet["entityId"],
            entity_kind=packet["entityKind"],
            definition=packet["definition"],
            evidence_authority_id=receipt["evidenceAuthorityId"],
            evidence_record_digest=receipt["evidenceRecordDigest"],
            compiler_digest=receipt["compilerDigest"],
            raw_definition_digest=receipt["rawDefinitionDigest"],
            projection_id=receipt["projectionId"],
            projection_version=receipt["projectionVersion"],
            projection_digest=receipt["projectionDigest"],
            required_capabilities=tuple(
                CapabilityRequirement.from_dict(item) for item in capabilities
            ),
            asset_refs=tuple(AssetRef.from_dict(item) for item in assets),
            expected_definition_digest=packet["definitionDigest"],
            expected_semantic_receipt_digest=receipt["semanticReceiptDigest"],
        )

@dataclass(frozen=True, init=False)
class SemanticPackage(_FactoryOnly):
    package_id: str
    version: str
    ruleset_id: str
    ruleset_digest: str
    book_id: str
    book_digest: str
    semantic_generation: str
    semantic_generation_digest: str
    compiler_id: str
    compiler_version: str
    compiler_digest: str
    entities: tuple[SemanticEntity, ...]
    relationships: tuple[ProviderCarrierRelationship, ...]
    package_digest: str
    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "schema": 2,
            "packageId": self.package_id,
            "version": self.version,
            "rulesetId": self.ruleset_id,
            "rulesetDigest": self.ruleset_digest,
            "bookId": self.book_id,
            "bookDigest": self.book_digest,
            "semanticGeneration": self.semantic_generation,
            "semanticGenerationDigest": self.semantic_generation_digest,
            "compilerId": self.compiler_id,
            "compilerVersion": self.compiler_version,
            "compilerDigest": self.compiler_digest,
            "entities": [item.to_dict() for item in self.entities],
            "providerCarrierRelationships": [
                item.to_dict() for item in self.relationships
            ],
        }
        if include_digest:
            result["packageDigest"] = self.package_digest
        return result

    def canonical_json(self) -> bytes:
        return _canonical(self.to_dict(), "semantic package")
    def entity(self, entity_id: str) -> SemanticEntity:
        entity_id = _id(entity_id, "entityId")
        for entity in self.entities:
            if entity.entity_id == entity_id:
                return entity
        raise KeyError(entity_id)

    @classmethod
    def from_dict(cls, value: object) -> SemanticPackage:
        keys = {
            "schema", "packageId", "version", "rulesetId", "rulesetDigest",
            "bookId", "bookDigest", "semanticGeneration", "semanticGenerationDigest",
            "compilerId", "compilerVersion", "compilerDigest", "entities",
            "providerCarrierRelationships", "packageDigest",
        }
        packet = _exact_keys(value, keys, "semantic package")
        if packet["schema"] != 2:
            raise SemanticPackageError("semantic package schema must be 2")
        entities = packet["entities"]
        relationships = packet["providerCarrierRelationships"]
        if type(entities) is not list or type(relationships) is not list:
            raise SemanticPackageError("package entities and relationships must be lists")
        return build_semantic_package(
            package_id=packet["packageId"],
            version=packet["version"],
            ruleset_id=packet["rulesetId"],
            ruleset_digest=packet["rulesetDigest"],
            book_id=packet["bookId"],
            book_digest=packet["bookDigest"],
            semantic_generation=packet["semanticGeneration"],
            semantic_generation_digest=packet["semanticGenerationDigest"],
            compiler_id=packet["compilerId"],
            compiler_version=packet["compilerVersion"],
            compiler_digest=packet["compilerDigest"],
            entities=tuple(SemanticEntity.from_dict(item) for item in entities),
            relationships=tuple(
                ProviderCarrierRelationship.from_dict(item) for item in relationships
            ),
            expected_package_digest=packet["packageDigest"],
        )

def build_semantic_entity(
    *,
    entity_id: str,
    entity_kind: str,
    definition: dict[str, Any],
    evidence_authority_id: str,
    evidence_record_digest: str,
    compiler_digest: str,
    raw_definition_digest: str,
    projection_id: str,
    projection_version: str,
    projection_digest: str,
    required_capabilities: Sequence[CapabilityRequirement] = (),
    asset_refs: Sequence[AssetRef] = (),
    expected_definition_digest: str | None = None,
    expected_semantic_receipt_digest: str | None = None,
) -> SemanticEntity:
    """Seal one already-projected, source-free public definition."""
    entity_id = _id(entity_id, "entityId")
    entity_kind = _id(entity_kind, "entityKind")
    validate_public_semantic_definition(definition)
    definition_json = _canonical(definition, "compiled definition")
    definition_digest = _sha(definition_json)
    if (
        expected_definition_digest is not None
        and _digest(expected_definition_digest, "definitionDigest") != definition_digest
    ):
        raise SemanticPackageError("definition digest mismatch")
    if not all(isinstance(item, CapabilityRequirement) for item in required_capabilities):
        raise SemanticPackageError("required capabilities are invalid")
    if not all(isinstance(item, AssetRef) for item in asset_refs):
        raise SemanticPackageError("asset references are invalid")
    receipt = SemanticReceipt.build(
        entity_id=entity_id,
        evidence_authority_id=evidence_authority_id,
        evidence_record_digest=evidence_record_digest,
        compiler_digest=compiler_digest,
        raw_definition_digest=raw_definition_digest,
        projected_definition_digest=definition_digest,
        projection_id=projection_id,
        projection_version=projection_version,
        projection_digest=projection_digest,
        expected_semantic_receipt_digest=expected_semantic_receipt_digest,
    )
    return _create(
        SemanticEntity,
        entity_id=entity_id,
        entity_kind=entity_kind,
        _definition_json=definition_json,
        definition_digest=definition_digest,
        receipt=receipt,
        required_capabilities=_sorted_unique(
            required_capabilities, "required capabilities"
        ),
        asset_refs=_sorted_unique(asset_refs, "asset references"),
    )

def build_semantic_package(
    *,
    package_id: str,
    version: str,
    ruleset_id: str,
    ruleset_digest: str,
    book_id: str,
    book_digest: str,
    semantic_generation: str,
    semantic_generation_digest: str,
    compiler_id: str,
    compiler_version: str,
    compiler_digest: str,
    entities: Sequence[SemanticEntity],
    relationships: Sequence[ProviderCarrierRelationship] = (),
    expected_package_digest: str | None = None,
) -> SemanticPackage:
    """Seal a deterministic, lookup-ready semantic package."""
    values = {
        "package_id": _id(package_id, "packageId"),
        "version": _version(version, "package version"),
        "ruleset_id": _id(ruleset_id, "rulesetId"),
        "ruleset_digest": _digest(ruleset_digest, "rulesetDigest"),
        "book_id": _id(book_id, "bookId"),
        "book_digest": _digest(book_digest, "bookDigest"),
        "semantic_generation": _id(semantic_generation, "semanticGeneration"),
        "semantic_generation_digest": _digest(
            semantic_generation_digest, "semanticGenerationDigest"
        ),
        "compiler_id": _id(compiler_id, "compilerId"),
        "compiler_version": _version(compiler_version, "compiler version"),
        "compiler_digest": _digest(compiler_digest, "compilerDigest"),
    }
    if not entities or not all(isinstance(item, SemanticEntity) for item in entities):
        raise SemanticPackageError("semantic package requires entities")
    if not all(isinstance(item, ProviderCarrierRelationship) for item in relationships):
        raise SemanticPackageError("provider/carrier relationships are invalid")
    ordered_entities = tuple(sorted(entities, key=lambda item: item.entity_id))
    if len({item.entity_id for item in ordered_entities}) != len(ordered_entities):
        raise SemanticPackageError("semantic package contains duplicate entity IDs")
    if any(
        item.receipt.compiler_digest != values["compiler_digest"]
        for item in ordered_entities
    ):
        raise SemanticPackageError(
            "semantic entity compiler digest disagrees with its package"
        )
    ordered_relationships = _sorted_unique(relationships, "provider/carrier relationships")
    entity_by_id = {item.entity_id: item for item in ordered_entities}
    creature_entities = tuple(
        item for item in ordered_entities if item.entity_kind == "ttrpg:creature"
    )

    def ability_provider_claims(entity: SemanticEntity, provider_id: str) -> int:
        abilities = entity.definition.get("abilities")
        if type(abilities) is not list:
            return 0
        return sum(
            1
            for ability in abilities
            if type(ability) is dict
            and (
                ability.get("entityId") == provider_id
                or ability.get("providerEntityId") == provider_id
            )
        )

    def ability_rule_claimed(entity: SemanticEntity, provider_id: str) -> bool:
        abilities = entity.definition.get("abilities")

        def contains_rule_ref(value: object) -> bool:
            if type(value) is dict:
                return any(
                    (key in {"ruleRef", "ruleRefs"} and (
                        child == provider_id
                        or (
                            type(child) is dict
                            and provider_id in child.values()
                        )
                    ))
                    or contains_rule_ref(child)
                    for key, child in value.items()
                )
            if type(value) is list:
                return any(contains_rule_ref(child) for child in value)
            return False

        return type(abilities) is list and contains_rule_ref(abilities)

    for relationship in ordered_relationships:
        carrier = entity_by_id.get(relationship.carrier_entity_id)
        if carrier is None or carrier.entity_kind != "ttrpg:creature":
            raise SemanticPackageError(
                "provider/carrier relationship carrier must be an exact "
                "creature entity in its package"
            )
        provider = entity_by_id.get(relationship.provider_entity_id)
        if provider is not None:
            if provider.entity_kind == "ttrpg:creature":
                raise SemanticPackageError(
                    "provider/carrier relationship provider must be a "
                    "non-creature semantic entity"
                )
            claims = {
                entity.entity_id: ability_provider_claims(
                    entity, relationship.provider_entity_id
                )
                for entity in creature_entities
            }
            if claims.get(carrier.entity_id) != 1 or any(
                count
                for entity_id, count in claims.items()
                if entity_id != carrier.entity_id
            ):
                raise SemanticPackageError(
                    "semantic entity provider must be declared exactly once "
                    "by only its relationship carrier"
                )
        else:
            claimants = tuple(
                entity.entity_id
                for entity in creature_entities
                if ability_rule_claimed(
                    entity, relationship.provider_entity_id
                )
            )
            if claimants != (carrier.entity_id,):
                raise SemanticPackageError(
                    "carrier-local semantic rule provider must be declared "
                    "by only its relationship carrier"
                )
    draft = _create(
        SemanticPackage,
        **values,
        entities=ordered_entities,
        relationships=ordered_relationships,
        package_digest="0" * 64,
    )
    package_digest = _sha(_canonical(draft.to_dict(include_digest=False), "semantic package"))
    if (
        expected_package_digest is not None
        and _digest(expected_package_digest, "packageDigest") != package_digest
    ):
        raise SemanticPackageError("semantic package digest mismatch")
    return _create(
        SemanticPackage,
        **values,
        entities=ordered_entities,
        relationships=ordered_relationships,
        package_digest=package_digest,
    )

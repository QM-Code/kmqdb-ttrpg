"""Private PF2ER authority for accepting one semantic publication record.

These records are operator inputs to TTRPG provisioning.  They bind an exact
source lifecycle record to the private evidence and public semantic identities
that were reviewed.  They are not public package content, an authentication
mechanism, or a generalized approval workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import hmac
import json
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


REVIEW_SCHEMA = 2
REVIEW_KIND = "pf2er-semantic-publication-review"
REVIEW_DECISION = "accepted"
REVIEW_CENSUS_KIND = "pf2er-semantic-publication-review-census"
PF2ER_RULESET_ID = "paizo:pf2er"

_REVIEWED_ENTITY_KINDS = frozenset(
    {
        "ttrpg:creature",
        "ttrpg:creature-ability",
        "ttrpg:item",
        "ttrpg:spell",
    }
)

_REVIEW_DIGEST_DOMAIN = b"pf2er-semantic-publication-review-v2\0"
_CENSUS_DIGEST_DOMAIN = b"pf2er-semantic-publication-review-census-v2\0"
_ID_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*:"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)
_VERSION_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SemanticPublicationReviewError(ValueError):
    """A private publication review or accepted census is invalid."""


def _exact(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise SemanticPublicationReviewError(
            f"{label} must have exactly {sorted(keys)}"
        )
    return value


def _array(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise SemanticPublicationReviewError(f"{label} must be an array")
    return value


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        raise SemanticPublicationReviewError(
            f"{label} must be a normalized namespaced ID"
        )
    return value


def _version(value: object, label: str) -> str:
    if type(value) is not str or _VERSION_RE.fullmatch(value) is None:
        raise SemanticPublicationReviewError(
            f"{label} must be a normalized x.y.z version"
        )
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise SemanticPublicationReviewError(
            f"{label} must be a lowercase sha256 digest"
        )
    return value


def _text(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
    ):
        raise SemanticPublicationReviewError(
            f"{label} must be nonempty trimmed text"
        )
    return value


def _review_date(value: object) -> str:
    text = _text(value, "reviewedOn")
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise SemanticPublicationReviewError(
            "reviewedOn must be an ISO 8601 calendar date"
        ) from exc
    if parsed.isoformat() != text:
        raise SemanticPublicationReviewError(
            "reviewedOn must be an ISO 8601 calendar date"
        )
    return text


def _lifecycle_path(value: object) -> str:
    text = _text(value, "lifecycleRecord.path")
    if "\\" in text:
        raise SemanticPublicationReviewError(
            "lifecycleRecord.path must be a repo-relative POSIX path"
        )
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or str(path) != text
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parts[:2] != ("subdomains", "ttrpg")
    ):
        raise SemanticPublicationReviewError(
            "lifecycleRecord.path must be a normalized TTRPG repo-relative path"
        )
    return text


def _canonical(value: object, label: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SemanticPublicationReviewError(
            f"{label} is not canonical JSON data"
        ) from exc


def _document_digest(domain: bytes, value: object, label: str) -> str:
    return hashlib.sha256(domain + _canonical(value, label)).hexdigest()


def _sorted_unique(values: Iterable[Any], label: str) -> tuple[Any, ...]:
    result = tuple(sorted(values))
    if len(result) != len(set(result)):
        raise SemanticPublicationReviewError(f"{label} contains duplicates")
    return result


def _duplicate_rejecting_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SemanticPublicationReviewError(
                f"publication review contains duplicate key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise SemanticPublicationReviewError(
        f"publication review contains non-finite number: {value}"
    )


@dataclass(frozen=True, order=True, slots=True)
class ReviewedCapability:
    capability_id: str
    contract_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capability_id",
            _identifier(self.capability_id, "capabilityId"),
        )
        object.__setattr__(
            self,
            "contract_version",
            _version(self.contract_version, "capability contractVersion"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "capabilityId": self.capability_id,
            "contractVersion": self.contract_version,
        }

    @classmethod
    def from_dict(cls, value: object) -> ReviewedCapability:
        packet = _exact(
            value,
            {"capabilityId", "contractVersion"},
            "reviewed capability",
        )
        return cls(packet["capabilityId"], packet["contractVersion"])


@dataclass(frozen=True, order=True, slots=True)
class ReviewedSourceEvidence:
    source_id: str
    locator: str
    source_receipt_digest: str
    refined_source_receipt_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text(self.source_id, "sourceId"))
        object.__setattr__(self, "locator", _text(self.locator, "locator"))
        object.__setattr__(
            self,
            "source_receipt_digest",
            _digest(self.source_receipt_digest, "sourceReceiptDigest"),
        )
        refinements = self.refined_source_receipt_digests
        if refinements == ():
            refinements = (self.source_receipt_digest,)
        if type(refinements) is not tuple:
            raise SemanticPublicationReviewError(
                "refinedSourceReceiptDigests must be a tuple"
            )
        normalized = tuple(
            sorted(
                _digest(item, "refinedSourceReceiptDigest")
                for item in refinements
            )
        )
        if not normalized:
            raise SemanticPublicationReviewError(
                "refinedSourceReceiptDigests must not be empty"
            )
        if len(normalized) != len(set(normalized)):
            raise SemanticPublicationReviewError(
                "refinedSourceReceiptDigests contains duplicates"
            )
        object.__setattr__(
            self,
            "refined_source_receipt_digests",
            normalized,
        )

    def to_dict(self) -> dict[str, object]:
        packet: dict[str, object] = {
            "sourceId": self.source_id,
            "locator": self.locator,
            "sourceReceiptDigest": self.source_receipt_digest,
        }
        # Retain byte-exact schema-2 decoding for the accepted root-only
        # authorities.  A refined closure is explicit whenever it differs
        # from the authenticated root selection.
        if self.refined_source_receipt_digests != (
            self.source_receipt_digest,
        ):
            packet["refinedSourceReceiptDigests"] = list(
                self.refined_source_receipt_digests
            )
        return packet

    @classmethod
    def from_dict(cls, value: object) -> ReviewedSourceEvidence:
        if type(value) is not dict:
            raise SemanticPublicationReviewError(
                "reviewed source evidence must be an object"
            )
        keys = frozenset(value)
        root_only = {"sourceId", "locator", "sourceReceiptDigest"}
        refined = root_only | {"refinedSourceReceiptDigests"}
        if keys not in {frozenset(root_only), frozenset(refined)}:
            raise SemanticPublicationReviewError(
                "reviewed source evidence must have exactly root receipt "
                "fields and an optional refined receipt closure"
            )
        packet = value
        return cls(
            packet["sourceId"],
            packet["locator"],
            packet["sourceReceiptDigest"],
            (
                ()
                if "refinedSourceReceiptDigests" not in packet
                else tuple(
                    _array(
                        packet["refinedSourceReceiptDigests"],
                        "refinedSourceReceiptDigests",
                    )
                )
            ),
        )


@dataclass(frozen=True, order=True, slots=True)
class ItemReviewRef:
    entity_id: str
    review_id: str
    review_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_id", _identifier(self.entity_id, "item entityId"))
        object.__setattr__(self, "review_id", _identifier(self.review_id, "item reviewId"))
        object.__setattr__(self, "review_digest", _digest(self.review_digest, "item reviewDigest"))

    def to_dict(self) -> dict[str, str]:
        return {
            "entityId": self.entity_id,
            "reviewId": self.review_id,
            "reviewDigest": self.review_digest,
        }

    @classmethod
    def from_dict(cls, value: object) -> ItemReviewRef:
        packet = _exact(
            value,
            {"entityId", "reviewId", "reviewDigest"},
            "item review reference",
        )
        return cls(
            packet["entityId"],
            packet["reviewId"],
            packet["reviewDigest"],
        )


@dataclass(frozen=True, order=True, slots=True)
class ReviewedOpaqueAsset:
    asset_id: str
    asset_digest: str
    private_acquisition_binding_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _identifier(self.asset_id, "assetId"))
        object.__setattr__(self, "asset_digest", _digest(self.asset_digest, "assetDigest"))
        object.__setattr__(
            self,
            "private_acquisition_binding_digest",
            _digest(
                self.private_acquisition_binding_digest,
                "privateAcquisitionBindingDigest",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "assetId": self.asset_id,
            "assetDigest": self.asset_digest,
            "privateAcquisitionBindingDigest": (
                self.private_acquisition_binding_digest
            ),
        }

    @classmethod
    def from_dict(cls, value: object) -> ReviewedOpaqueAsset:
        packet = _exact(
            value,
            {
                "assetId",
                "assetDigest",
                "privateAcquisitionBindingDigest",
            },
            "reviewed opaque asset",
        )
        return cls(
            packet["assetId"],
            packet["assetDigest"],
            packet["privateAcquisitionBindingDigest"],
        )


@dataclass(frozen=True, order=True, slots=True)
class ReviewedProviderCarrierRelationship:
    relationship_id: str
    provider_entity_id: str
    carrier_entity_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "relationship_id",
            _identifier(self.relationship_id, "relationshipId"),
        )
        object.__setattr__(
            self,
            "provider_entity_id",
            _identifier(self.provider_entity_id, "providerEntityId"),
        )
        object.__setattr__(
            self,
            "carrier_entity_id",
            _identifier(self.carrier_entity_id, "carrierEntityId"),
        )
        if self.provider_entity_id == self.carrier_entity_id:
            raise SemanticPublicationReviewError(
                "provider and carrier entity identities must differ"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "relationshipId": self.relationship_id,
            "providerEntityId": self.provider_entity_id,
            "carrierEntityId": self.carrier_entity_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> ReviewedProviderCarrierRelationship:
        packet = _exact(
            value,
            {"relationshipId", "providerEntityId", "carrierEntityId"},
            "reviewed provider/carrier relationship",
        )
        return cls(
            packet["relationshipId"],
            packet["providerEntityId"],
            packet["carrierEntityId"],
        )


@dataclass(frozen=True, slots=True, init=False)
class SemanticPublicationReview:
    """One accepted, digest-sealed PF2ER semantic publication review."""

    review_id: str
    lifecycle_record_path: str | None
    lifecycle_record_digest: str | None
    ruleset_digest: str
    entity_id: str
    entity_kind: str
    book_id: str
    book_digest: str
    source_id: str
    source_evidence: tuple[ReviewedSourceEvidence, ...]
    source_generation: str
    authority_digest: str
    package_id: str
    package_version: str
    semantic_generation: str
    semantic_generation_digest: str
    compiler_id: str
    compiler_version: str
    compiler_digest: str
    projection_id: str
    projection_version: str
    projection_digest: str
    raw_definition_digest: str
    projected_definition_digest: str
    evidence_authority_id: str
    evidence_record_digest: str
    semantic_receipt_digest: str
    required_capabilities: tuple[ReviewedCapability, ...]
    item_review_refs: tuple[ItemReviewRef, ...]
    opaque_assets: tuple[ReviewedOpaqueAsset, ...]
    provider_carrier_relationships: tuple[
        ReviewedProviderCarrierRelationship, ...
    ]
    accepted_deferrals: tuple[str, ...]
    reviewer_role: str
    reviewed_on: str
    review_scope: str
    review_digest: str

    def __init__(self, *unused: object, **unused_named: object) -> None:
        raise TypeError(
            "SemanticPublicationReview values must be built through build()"
        )

    @classmethod
    def build(
        cls,
        *,
        review_id: str,
        lifecycle_record_path: str | None,
        lifecycle_record_digest: str | None,
        ruleset_digest: str,
        entity_id: str,
        entity_kind: str,
        book_id: str,
        book_digest: str,
        source_id: str,
        source_evidence: Sequence[ReviewedSourceEvidence],
        source_generation: str,
        authority_digest: str,
        package_id: str,
        package_version: str,
        semantic_generation: str,
        semantic_generation_digest: str,
        compiler_id: str,
        compiler_version: str,
        compiler_digest: str,
        projection_id: str,
        projection_version: str,
        projection_digest: str,
        raw_definition_digest: str,
        projected_definition_digest: str,
        evidence_authority_id: str,
        evidence_record_digest: str,
        semantic_receipt_digest: str,
        required_capabilities: Sequence[ReviewedCapability] = (),
        item_review_refs: Sequence[ItemReviewRef] = (),
        opaque_assets: Sequence[ReviewedOpaqueAsset] = (),
        provider_carrier_relationships: Sequence[
            ReviewedProviderCarrierRelationship
        ] = (),
        accepted_deferrals: Sequence[str] = (),
        reviewer_role: str,
        reviewed_on: str,
        review_scope: str,
        expected_review_digest: str | None = None,
    ) -> SemanticPublicationReview:
        normalized_entity_kind = _identifier(entity_kind, "entityKind")
        if normalized_entity_kind not in _REVIEWED_ENTITY_KINDS:
            raise SemanticPublicationReviewError(
                "entityKind must be ttrpg:creature, ttrpg:creature-ability, "
                "ttrpg:item, or ttrpg:spell"
            )
        if (lifecycle_record_path is None) != (
            lifecycle_record_digest is None
        ):
            raise SemanticPublicationReviewError(
                "lifecycle record path and digest must be supplied together"
            )
        if lifecycle_record_path is None:
            if normalized_entity_kind == "ttrpg:creature":
                raise SemanticPublicationReviewError(
                    "creature review requires a lifecycle record"
                )
            normalized_lifecycle_path = None
            normalized_lifecycle_digest = None
        else:
            if normalized_entity_kind != "ttrpg:creature":
                raise SemanticPublicationReviewError(
                    "non-creature review lifecycleRecord must be null"
                )
            normalized_lifecycle_path = _lifecycle_path(lifecycle_record_path)
            normalized_lifecycle_digest = _digest(
                lifecycle_record_digest, "lifecycleRecord.sha256"
            )

        normalized_source_id = _text(source_id, "sourceId")
        if not isinstance(source_evidence, (tuple, list)) or any(
            type(item) is not ReviewedSourceEvidence for item in source_evidence
        ):
            raise SemanticPublicationReviewError(
                "sourceEvidence contains an invalid value"
            )
        normalized_source_evidence = _sorted_unique(
            source_evidence, "sourceEvidence"
        )
        if not normalized_source_evidence:
            raise SemanticPublicationReviewError("sourceEvidence must not be empty")
        if any(
            item.source_id != normalized_source_id
            for item in normalized_source_evidence
        ):
            raise SemanticPublicationReviewError(
                "sourceEvidence must use the reviewed publication source"
            )

        values: dict[str, object] = {
            "review_id": _identifier(review_id, "reviewId"),
            "lifecycle_record_path": normalized_lifecycle_path,
            "lifecycle_record_digest": normalized_lifecycle_digest,
            "ruleset_digest": _digest(ruleset_digest, "rulesetDigest"),
            "entity_id": _identifier(entity_id, "entityId"),
            "entity_kind": normalized_entity_kind,
            "book_id": _identifier(book_id, "bookId"),
            "book_digest": _digest(book_digest, "bookDigest"),
            "source_id": normalized_source_id,
            "source_generation": _digest(source_generation, "sourceGeneration"),
            "authority_digest": _digest(authority_digest, "authorityDigest"),
            "package_id": _identifier(package_id, "packageId"),
            "package_version": _version(package_version, "packageVersion"),
            "semantic_generation": _identifier(
                semantic_generation, "semanticGeneration"
            ),
            "semantic_generation_digest": _digest(
                semantic_generation_digest, "semanticGenerationDigest"
            ),
            "compiler_id": _identifier(compiler_id, "compilerId"),
            "compiler_version": _version(compiler_version, "compilerVersion"),
            "compiler_digest": _digest(compiler_digest, "compilerDigest"),
            "projection_id": _identifier(projection_id, "projectionId"),
            "projection_version": _version(
                projection_version, "projectionVersion"
            ),
            "projection_digest": _digest(projection_digest, "projectionDigest"),
            "raw_definition_digest": _digest(
                raw_definition_digest, "rawDefinitionDigest"
            ),
            "projected_definition_digest": _digest(
                projected_definition_digest, "projectedDefinitionDigest"
            ),
            "evidence_authority_id": _identifier(
                evidence_authority_id, "evidenceAuthorityId"
            ),
            "evidence_record_digest": _digest(
                evidence_record_digest, "evidenceRecordDigest"
            ),
            "semantic_receipt_digest": _digest(
                semantic_receipt_digest, "semanticReceiptDigest"
            ),
            "reviewer_role": _identifier(reviewer_role, "reviewer.role"),
            "reviewed_on": _review_date(reviewed_on),
            "review_scope": _identifier(review_scope, "reviewer.scope"),
        }
        for sequence, expected_type, label in (
            (required_capabilities, ReviewedCapability, "requiredCapabilities"),
            (item_review_refs, ItemReviewRef, "itemReviewRefs"),
            (opaque_assets, ReviewedOpaqueAsset, "opaqueAssets"),
            (
                provider_carrier_relationships,
                ReviewedProviderCarrierRelationship,
                "providerCarrierRelationships",
            ),
        ):
            if not isinstance(sequence, (tuple, list)) or any(
                type(item) is not expected_type for item in sequence
            ):
                raise SemanticPublicationReviewError(
                    f"{label} contains an invalid value"
                )
        capabilities = _sorted_unique(
            required_capabilities, "requiredCapabilities"
        )
        item_refs = _sorted_unique(item_review_refs, "itemReviewRefs")
        assets = _sorted_unique(opaque_assets, "opaqueAssets")
        relationships = _sorted_unique(
            provider_carrier_relationships,
            "providerCarrierRelationships",
        )
        if not isinstance(accepted_deferrals, (tuple, list)):
            raise SemanticPublicationReviewError(
                "acceptedDeferrals contains an invalid value"
            )
        deferrals = _sorted_unique(
            (_text(item, "accepted deferral") for item in accepted_deferrals),
            "acceptedDeferrals",
        )
        if len({item.entity_id for item in item_refs}) != len(item_refs):
            raise SemanticPublicationReviewError(
                "itemReviewRefs contains duplicate item entity IDs"
            )
        if any(item.entity_id == values["entity_id"] for item in item_refs):
            raise SemanticPublicationReviewError(
                "an entity cannot cite its own item review"
            )
        if len({item.asset_id for item in assets}) != len(assets):
            raise SemanticPublicationReviewError(
                "opaqueAssets contains duplicate asset IDs"
            )
        if (
            len({item.relationship_id for item in relationships})
            != len(relationships)
            or len(
                {
                    (item.provider_entity_id, item.carrier_entity_id)
                    for item in relationships
                }
            )
            != len(relationships)
        ):
            raise SemanticPublicationReviewError(
                "providerCarrierRelationships contains duplicate identities"
            )

        instance = object.__new__(cls)
        for name, value in values.items():
            object.__setattr__(instance, name, value)
        object.__setattr__(
            instance, "source_evidence", normalized_source_evidence
        )
        object.__setattr__(instance, "required_capabilities", capabilities)
        object.__setattr__(instance, "item_review_refs", item_refs)
        object.__setattr__(instance, "opaque_assets", assets)
        object.__setattr__(
            instance, "provider_carrier_relationships", relationships
        )
        object.__setattr__(instance, "accepted_deferrals", deferrals)
        object.__setattr__(instance, "review_digest", "0" * 64)
        actual = _document_digest(
            _REVIEW_DIGEST_DOMAIN,
            instance.to_dict(include_digest=False),
            "semantic publication review",
        )
        if expected_review_digest is not None and not hmac.compare_digest(
            _digest(expected_review_digest, "reviewDigest"), actual
        ):
            raise SemanticPublicationReviewError(
                "semantic publication review digest mismatch"
            )
        object.__setattr__(instance, "review_digest", actual)
        return instance

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        packet: dict[str, object] = {
            "schema": REVIEW_SCHEMA,
            "kind": REVIEW_KIND,
            "decision": REVIEW_DECISION,
            "reviewId": self.review_id,
            "lifecycleRecord": (
                None
                if self.lifecycle_record_path is None
                else {
                    "path": self.lifecycle_record_path,
                    "sha256": self.lifecycle_record_digest,
                }
            ),
            "ruleset": {
                "rulesetId": PF2ER_RULESET_ID,
                "rulesetDigest": self.ruleset_digest,
            },
            "publication": {
                "bookId": self.book_id,
                "bookDigest": self.book_digest,
                "sourceId": self.source_id,
                "sourceGeneration": self.source_generation,
                "authorityDigest": self.authority_digest,
                "packageId": self.package_id,
                "packageVersion": self.package_version,
                "semanticGeneration": self.semantic_generation,
                "semanticGenerationDigest": self.semantic_generation_digest,
            },
            "entity": {
                "entityId": self.entity_id,
                "entityKind": self.entity_kind,
                "sourceEvidence": [
                    item.to_dict() for item in self.source_evidence
                ],
                "rawDefinitionDigest": self.raw_definition_digest,
                "projectedDefinitionDigest": self.projected_definition_digest,
                "evidenceAuthorityId": self.evidence_authority_id,
                "evidenceRecordDigest": self.evidence_record_digest,
                "semanticReceiptDigest": self.semantic_receipt_digest,
            },
            "compiler": {
                "compilerId": self.compiler_id,
                "compilerVersion": self.compiler_version,
                "compilerDigest": self.compiler_digest,
            },
            "projection": {
                "projectionId": self.projection_id,
                "projectionVersion": self.projection_version,
                "projectionDigest": self.projection_digest,
            },
            "requiredCapabilities": [
                item.to_dict() for item in self.required_capabilities
            ],
            "itemReviewRefs": [item.to_dict() for item in self.item_review_refs],
            "opaqueAssets": [item.to_dict() for item in self.opaque_assets],
            "providerCarrierRelationships": [
                item.to_dict() for item in self.provider_carrier_relationships
            ],
            "acceptedDeferrals": list(self.accepted_deferrals),
            "reviewer": {
                "role": self.reviewer_role,
                "reviewedOn": self.reviewed_on,
                "scope": self.review_scope,
            },
        }
        if include_digest:
            packet["reviewDigest"] = self.review_digest
        return packet

    def canonical_json(self) -> bytes:
        return _canonical(self.to_dict(), "semantic publication review")

    @classmethod
    def from_dict(cls, value: object) -> SemanticPublicationReview:
        packet = _exact(
            value,
            {
                "schema",
                "kind",
                "decision",
                "reviewId",
                "lifecycleRecord",
                "ruleset",
                "publication",
                "entity",
                "compiler",
                "projection",
                "requiredCapabilities",
                "itemReviewRefs",
                "opaqueAssets",
                "providerCarrierRelationships",
                "acceptedDeferrals",
                "reviewer",
                "reviewDigest",
            },
            "semantic publication review",
        )
        if (
            type(packet["schema"]) is not int
            or packet["schema"] != REVIEW_SCHEMA
            or packet["kind"] != REVIEW_KIND
            or packet["decision"] != REVIEW_DECISION
        ):
            raise SemanticPublicationReviewError(
                "semantic publication review identity is unsupported"
            )
        if packet["lifecycleRecord"] is None:
            lifecycle: dict[str, Any] | None = None
        else:
            lifecycle = _exact(
                packet["lifecycleRecord"],
                {"path", "sha256"},
                "lifecycleRecord",
            )
        ruleset = _exact(
            packet["ruleset"],
            {"rulesetId", "rulesetDigest"},
            "ruleset",
        )
        if ruleset["rulesetId"] != PF2ER_RULESET_ID:
            raise SemanticPublicationReviewError(
                "semantic publication review is not PF2ER"
            )
        publication = _exact(
            packet["publication"],
            {
                "bookId",
                "bookDigest",
                "sourceId",
                "sourceGeneration",
                "authorityDigest",
                "packageId",
                "packageVersion",
                "semanticGeneration",
                "semanticGenerationDigest",
            },
            "publication",
        )
        entity = _exact(
            packet["entity"],
            {
                "entityId",
                "entityKind",
                "sourceEvidence",
                "rawDefinitionDigest",
                "projectedDefinitionDigest",
                "evidenceAuthorityId",
                "evidenceRecordDigest",
                "semanticReceiptDigest",
            },
            "entity",
        )
        compiler = _exact(
            packet["compiler"],
            {"compilerId", "compilerVersion", "compilerDigest"},
            "compiler",
        )
        projection = _exact(
            packet["projection"],
            {"projectionId", "projectionVersion", "projectionDigest"},
            "projection",
        )
        reviewer = _exact(
            packet["reviewer"],
            {"role", "reviewedOn", "scope"},
            "reviewer",
        )
        return cls.build(
            review_id=packet["reviewId"],
            lifecycle_record_path=(None if lifecycle is None else lifecycle["path"]),
            lifecycle_record_digest=(
                None if lifecycle is None else lifecycle["sha256"]
            ),
            ruleset_digest=ruleset["rulesetDigest"],
            entity_id=entity["entityId"],
            entity_kind=entity["entityKind"],
            book_id=publication["bookId"],
            book_digest=publication["bookDigest"],
            source_id=publication["sourceId"],
            source_evidence=tuple(
                ReviewedSourceEvidence.from_dict(item)
                for item in _array(entity["sourceEvidence"], "sourceEvidence")
            ),
            source_generation=publication["sourceGeneration"],
            authority_digest=publication["authorityDigest"],
            package_id=publication["packageId"],
            package_version=publication["packageVersion"],
            semantic_generation=publication["semanticGeneration"],
            semantic_generation_digest=publication["semanticGenerationDigest"],
            compiler_id=compiler["compilerId"],
            compiler_version=compiler["compilerVersion"],
            compiler_digest=compiler["compilerDigest"],
            projection_id=projection["projectionId"],
            projection_version=projection["projectionVersion"],
            projection_digest=projection["projectionDigest"],
            raw_definition_digest=entity["rawDefinitionDigest"],
            projected_definition_digest=entity["projectedDefinitionDigest"],
            evidence_authority_id=entity["evidenceAuthorityId"],
            evidence_record_digest=entity["evidenceRecordDigest"],
            semantic_receipt_digest=entity["semanticReceiptDigest"],
            required_capabilities=tuple(
                ReviewedCapability.from_dict(item)
                for item in _array(
                    packet["requiredCapabilities"], "requiredCapabilities"
                )
            ),
            item_review_refs=tuple(
                ItemReviewRef.from_dict(item)
                for item in _array(packet["itemReviewRefs"], "itemReviewRefs")
            ),
            opaque_assets=tuple(
                ReviewedOpaqueAsset.from_dict(item)
                for item in _array(packet["opaqueAssets"], "opaqueAssets")
            ),
            provider_carrier_relationships=tuple(
                ReviewedProviderCarrierRelationship.from_dict(item)
                for item in _array(
                    packet["providerCarrierRelationships"],
                    "providerCarrierRelationships",
                )
            ),
            accepted_deferrals=tuple(
                _array(packet["acceptedDeferrals"], "acceptedDeferrals")
            ),
            reviewer_role=reviewer["role"],
            reviewed_on=reviewer["reviewedOn"],
            review_scope=reviewer["scope"],
            expected_review_digest=packet["reviewDigest"],
        )

    @classmethod
    def from_json(cls, value: bytes | str) -> SemanticPublicationReview:
        if type(value) is bytes:
            try:
                text = value.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SemanticPublicationReviewError(
                    "semantic publication review must be UTF-8 JSON"
                ) from exc
        elif type(value) is str:
            text = value
        else:
            raise TypeError("semantic publication review JSON must be bytes or str")
        try:
            decoded = json.loads(
                text,
                object_pairs_hook=_duplicate_rejecting_object,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SemanticPublicationReviewError(
                "semantic publication review is not valid JSON"
            ) from exc
        return cls.from_dict(decoded)


@dataclass(frozen=True, slots=True, init=False)
class AcceptedSemanticPublicationReviewCensus:
    """Deterministic, conflict-free accepted reviews for one provision run."""

    reviews: tuple[SemanticPublicationReview, ...]
    assets: tuple[ReviewedOpaqueAsset, ...]
    relationships: tuple[ReviewedProviderCarrierRelationship, ...]
    census_digest: str
    _by_entity: Mapping[str, SemanticPublicationReview]
    _by_review_id: Mapping[str, SemanticPublicationReview]

    def __init__(self, *unused: object, **unused_named: object) -> None:
        raise TypeError(
            "AcceptedSemanticPublicationReviewCensus values must be built "
            "through build()"
        )

    @classmethod
    def build(
        cls,
        reviews: Sequence[SemanticPublicationReview],
        *,
        expected_census_digest: str | None = None,
    ) -> AcceptedSemanticPublicationReviewCensus:
        if not isinstance(reviews, (tuple, list)) or not reviews:
            raise SemanticPublicationReviewError(
                "accepted review census requires reviews"
            )
        if any(type(item) is not SemanticPublicationReview for item in reviews):
            raise SemanticPublicationReviewError(
                "accepted review census contains an invalid record"
            )
        ordered = tuple(sorted(reviews, key=lambda item: item.entity_id))
        for values, label in (
            ((item.review_digest for item in ordered), "review digests"),
            ((item.review_id for item in ordered), "review IDs"),
            ((item.entity_id for item in ordered), "entity IDs"),
            (
                (
                    item.lifecycle_record_path
                    for item in ordered
                    if item.lifecycle_record_path is not None
                ),
                "lifecycle record paths",
            ),
            (
                (
                    item.evidence_record_digest for item in ordered
                ),
                "evidence record digests",
            ),
            (
                (
                    item.semantic_receipt_digest for item in ordered
                ),
                "semantic receipt digests",
            ),
        ):
            sequence = tuple(values)
            if len(sequence) != len(set(sequence)):
                raise SemanticPublicationReviewError(
                    f"accepted review census contains duplicate {label}"
                )

        authority_fences = {
            (
                item.ruleset_digest,
                item.source_generation,
                item.authority_digest,
            )
            for item in ordered
        }
        if len(authority_fences) != 1:
            raise SemanticPublicationReviewError(
                "accepted reviews conflict on the ruleset/source authority fence"
            )

        source_target_fences: dict[tuple[str, str], str] = {}
        for review in ordered:
            for evidence in review.source_evidence:
                source_target = (evidence.source_id, evidence.locator)
                prior_receipt = source_target_fences.setdefault(
                    source_target, evidence.source_receipt_digest
                )
                if not hmac.compare_digest(
                    prior_receipt, evidence.source_receipt_digest
                ):
                    raise SemanticPublicationReviewError(
                        "accepted reviews conflict on an authenticated source target fence"
                    )

        by_entity = {item.entity_id: item for item in ordered}
        by_review_id = {item.review_id: item for item in ordered}
        for review in ordered:
            for reference in review.item_review_refs:
                target = by_entity.get(reference.entity_id)
                if target is None:
                    raise SemanticPublicationReviewError(
                        "item review reference is absent from the accepted census"
                    )
                if (
                    target.entity_kind != "ttrpg:item"
                    or target.review_id != reference.review_id
                    or not hmac.compare_digest(
                        target.review_digest, reference.review_digest
                    )
                ):
                    raise SemanticPublicationReviewError(
                        "item review reference conflicts with its accepted record"
                    )

        book_fences: dict[str, tuple[object, ...]] = {}
        package_fences: dict[tuple[str, str], tuple[object, ...]] = {}
        asset_by_id: dict[str, ReviewedOpaqueAsset] = {}
        relationship_by_id: dict[
            str, ReviewedProviderCarrierRelationship
        ] = {}
        for review in ordered:
            book_fence = (
                review.book_digest,
                review.source_id,
                review.source_generation,
                review.authority_digest,
                review.ruleset_digest,
            )
            prior_book = book_fences.setdefault(review.book_id, book_fence)
            if prior_book != book_fence:
                raise SemanticPublicationReviewError(
                    "accepted reviews conflict on a book/source authority fence"
                )
            package_key = (review.package_id, review.package_version)
            package_fence = (
                review.book_id,
                review.book_digest,
                review.source_id,
                review.source_generation,
                review.authority_digest,
                review.semantic_generation,
                review.semantic_generation_digest,
                review.compiler_id,
                review.compiler_version,
                review.compiler_digest,
                review.ruleset_digest,
            )
            prior_package = package_fences.setdefault(package_key, package_fence)
            if prior_package != package_fence:
                raise SemanticPublicationReviewError(
                    "accepted reviews conflict on a semantic package fence"
                )
            for asset in review.opaque_assets:
                prior_asset = asset_by_id.setdefault(asset.asset_id, asset)
                if prior_asset != asset:
                    raise SemanticPublicationReviewError(
                        "accepted reviews conflict on an opaque asset binding"
                    )
            for relationship in review.provider_carrier_relationships:
                prior_relationship = relationship_by_id.setdefault(
                    relationship.relationship_id, relationship
                )
                if prior_relationship != relationship:
                    raise SemanticPublicationReviewError(
                        "accepted reviews conflict on a provider/carrier relationship"
                    )

        assets = tuple(sorted(asset_by_id.values()))
        relationships = tuple(sorted(relationship_by_id.values()))
        instance = object.__new__(cls)
        object.__setattr__(instance, "reviews", ordered)
        object.__setattr__(instance, "assets", assets)
        object.__setattr__(instance, "relationships", relationships)
        object.__setattr__(instance, "census_digest", "0" * 64)
        object.__setattr__(
            instance, "_by_entity", MappingProxyType(by_entity)
        )
        object.__setattr__(
            instance, "_by_review_id", MappingProxyType(by_review_id)
        )
        actual = _document_digest(
            _CENSUS_DIGEST_DOMAIN,
            instance.to_dict(include_digest=False),
            "accepted semantic publication review census",
        )
        if expected_census_digest is not None and not hmac.compare_digest(
            _digest(expected_census_digest, "censusDigest"), actual
        ):
            raise SemanticPublicationReviewError(
                "accepted semantic publication review census digest mismatch"
            )
        object.__setattr__(instance, "census_digest", actual)
        return instance

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return tuple(item.entity_id for item in self.reviews)

    def review(self, entity_id: str) -> SemanticPublicationReview:
        key = _identifier(entity_id, "entityId")
        try:
            return self._by_entity[key]
        except KeyError as exc:
            raise KeyError(key) from exc

    def review_id(self, review_id: str) -> SemanticPublicationReview:
        key = _identifier(review_id, "reviewId")
        try:
            return self._by_review_id[key]
        except KeyError as exc:
            raise KeyError(key) from exc

    def review_by_id(self, review_id: str) -> SemanticPublicationReview:
        """Return one accepted record by its review identity."""

        return self.review_id(review_id)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        packet: dict[str, object] = {
            "schema": REVIEW_SCHEMA,
            "kind": REVIEW_CENSUS_KIND,
            "reviews": [item.to_dict() for item in self.reviews],
        }
        if include_digest:
            packet["censusDigest"] = self.census_digest
        return packet

    def canonical_json(self) -> bytes:
        return _canonical(
            self.to_dict(), "accepted semantic publication review census"
        )

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> AcceptedSemanticPublicationReviewCensus:
        packet = _exact(
            value,
            {"schema", "kind", "reviews", "censusDigest"},
            "accepted semantic publication review census",
        )
        if (
            type(packet["schema"]) is not int
            or packet["schema"] != REVIEW_SCHEMA
            or packet["kind"] != REVIEW_CENSUS_KIND
        ):
            raise SemanticPublicationReviewError(
                "accepted semantic publication review census identity is "
                "unsupported"
            )
        return cls.build(
            tuple(
                SemanticPublicationReview.from_dict(item)
                for item in _array(packet["reviews"], "reviews")
            ),
            expected_census_digest=packet["censusDigest"],
        )

    @classmethod
    def from_json(
        cls,
        value: bytes | str,
    ) -> AcceptedSemanticPublicationReviewCensus:
        if type(value) is bytes:
            try:
                text = value.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SemanticPublicationReviewError(
                    "accepted review census must be UTF-8 JSON"
                ) from exc
        elif type(value) is str:
            text = value
        else:
            raise TypeError("accepted review census JSON must be bytes or str")
        try:
            decoded = json.loads(
                text,
                object_pairs_hook=_duplicate_rejecting_object,
                parse_constant=_reject_constant,
            )
        except json.JSONDecodeError as exc:
            raise SemanticPublicationReviewError(
                "accepted review census is not valid JSON"
            ) from exc
        return cls.from_dict(decoded)


def build_semantic_publication_review(
    **values: object,
) -> SemanticPublicationReview:
    """Named factory kept small for operator/provisioner composition."""

    return SemanticPublicationReview.build(**values)  # type: ignore[arg-type]


def collect_accepted_semantic_publication_reviews(
    reviews: Sequence[SemanticPublicationReview],
    *,
    expected_census_digest: str | None = None,
) -> AcceptedSemanticPublicationReviewCensus:
    """Collect one deterministic, complete accepted-review census."""

    return AcceptedSemanticPublicationReviewCensus.build(
        reviews,
        expected_census_digest=expected_census_digest,
    )


__all__ = [
    "AcceptedSemanticPublicationReviewCensus",
    "ItemReviewRef",
    "PF2ER_RULESET_ID",
    "REVIEW_CENSUS_KIND",
    "REVIEW_DECISION",
    "REVIEW_KIND",
    "REVIEW_SCHEMA",
    "ReviewedCapability",
    "ReviewedOpaqueAsset",
    "ReviewedProviderCarrierRelationship",
    "ReviewedSourceEvidence",
    "SemanticPublicationReview",
    "SemanticPublicationReviewError",
    "build_semantic_publication_review",
    "collect_accepted_semantic_publication_reviews",
]

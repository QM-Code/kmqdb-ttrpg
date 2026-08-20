"""Private TTRPG evidence retained behind the semantic-package boundary.

The public semantic package carries only the digest of one of these records.
Acquisition addresses and exact authority receipts never enter public package
bytes or the Gladiator package store.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
from types import MappingProxyType
from typing import Any, Sequence


_ID_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*:"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)
_VERSION_RE = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SemanticEvidenceError(ValueError):
    """A private semantic evidence record or store operation is invalid."""


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        raise SemanticEvidenceError(f"{label} must be a normalized namespaced ID")
    return value


def _version(value: object, label: str) -> str:
    if type(value) is not str or _VERSION_RE.fullmatch(value) is None:
        raise SemanticEvidenceError(f"{label} must be a normalized x.y.z version")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise SemanticEvidenceError(f"{label} must be a lowercase sha256 digest")
    return value


def _strict_json(value: object, label: str) -> None:
    if value is None or type(value) in {bool, str, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise SemanticEvidenceError(f"{label} contains a non-finite number")
        return
    if type(value) is list:
        for item in value:
            _strict_json(item, label)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise SemanticEvidenceError(f"{label} contains a non-string object key")
            _strict_json(item, label)
        return
    raise SemanticEvidenceError(f"{label} is not strict JSON-compatible data")


def canonical_json(value: object, label: str = "evidence value") -> bytes:
    _strict_json(value, label)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_digest(value: object, label: str = "evidence value") -> str:
    return hashlib.sha256(canonical_json(value, label)).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class SemanticEvidenceRecord:
    """Exact private evidence for one projected semantic definition."""

    evidence_authority_id: str
    entity_id: str
    compiler_digest: str
    raw_definition_digest: str
    projected_definition_digest: str
    projection_id: str
    projection_version: str
    projection_digest: str
    _acquisition_receipt_json: bytes
    _compiler_receipt_json: bytes
    evidence_record_digest: str

    def __init__(self, *unused: object, **unused_named: object) -> None:
        raise TypeError("SemanticEvidenceRecord values must be built through build()")

    @property
    def acquisition_receipt(self) -> dict[str, Any]:
        return json.loads(self._acquisition_receipt_json.decode("utf-8"))

    @property
    def compiler_receipt(self) -> dict[str, Any]:
        return json.loads(self._compiler_receipt_json.decode("utf-8"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        packet: dict[str, object] = {
            "schema": 1,
            "evidenceAuthorityId": self.evidence_authority_id,
            "entityId": self.entity_id,
            "compilerDigest": self.compiler_digest,
            "rawDefinitionDigest": self.raw_definition_digest,
            "projectedDefinitionDigest": self.projected_definition_digest,
            "projectionId": self.projection_id,
            "projectionVersion": self.projection_version,
            "projectionDigest": self.projection_digest,
            "acquisitionReceipt": self.acquisition_receipt,
            "compilerReceipt": self.compiler_receipt,
        }
        if include_digest:
            packet["evidenceRecordDigest"] = self.evidence_record_digest
        return packet

    def canonical_json(self) -> bytes:
        return canonical_json(self.to_dict(), "semantic evidence record")

    @classmethod
    def build(
        cls,
        *,
        evidence_authority_id: str,
        entity_id: str,
        compiler_digest: str,
        raw_definition_digest: str,
        projected_definition_digest: str,
        projection_id: str,
        projection_version: str,
        projection_digest: str,
        acquisition_receipt: dict[str, Any],
        compiler_receipt: dict[str, Any],
        expected_evidence_record_digest: str | None = None,
    ) -> SemanticEvidenceRecord:
        values = {
            "evidence_authority_id": _identifier(
                evidence_authority_id, "evidenceAuthorityId"
            ),
            "entity_id": _identifier(entity_id, "entityId"),
            "compiler_digest": _digest(compiler_digest, "compilerDigest"),
            "raw_definition_digest": _digest(
                raw_definition_digest, "rawDefinitionDigest"
            ),
            "projected_definition_digest": _digest(
                projected_definition_digest, "projectedDefinitionDigest"
            ),
            "projection_id": _identifier(projection_id, "projectionId"),
            "projection_version": _version(
                projection_version, "projectionVersion"
            ),
            "projection_digest": _digest(projection_digest, "projectionDigest"),
        }
        if type(acquisition_receipt) is not dict:
            raise SemanticEvidenceError("acquisitionReceipt must be a JSON object")
        if type(compiler_receipt) is not dict:
            raise SemanticEvidenceError("compilerReceipt must be a JSON object")
        acquisition_json = canonical_json(
            acquisition_receipt, "acquisition receipt"
        )
        compiler_json = canonical_json(compiler_receipt, "compiler receipt")
        draft = {
            "schema": 1,
            "evidenceAuthorityId": values["evidence_authority_id"],
            "entityId": values["entity_id"],
            "compilerDigest": values["compiler_digest"],
            "rawDefinitionDigest": values["raw_definition_digest"],
            "projectedDefinitionDigest": values["projected_definition_digest"],
            "projectionId": values["projection_id"],
            "projectionVersion": values["projection_version"],
            "projectionDigest": values["projection_digest"],
            "acquisitionReceipt": json.loads(acquisition_json.decode("utf-8")),
            "compilerReceipt": json.loads(compiler_json.decode("utf-8")),
        }
        actual = canonical_digest(draft, "semantic evidence record")
        if expected_evidence_record_digest is not None and not hmac.compare_digest(
            _digest(expected_evidence_record_digest, "evidenceRecordDigest"),
            actual,
        ):
            raise SemanticEvidenceError("semantic evidence record digest mismatch")
        instance = object.__new__(cls)
        for name, value in values.items():
            object.__setattr__(instance, name, value)
        object.__setattr__(instance, "_acquisition_receipt_json", acquisition_json)
        object.__setattr__(instance, "_compiler_receipt_json", compiler_json)
        object.__setattr__(instance, "evidence_record_digest", actual)
        return instance


@dataclass(frozen=True, slots=True, init=False)
class SemanticEvidenceSnapshot:
    """Exact operator-publication artifact for private TTRPG evidence.

    This artifact must be written to TTRPG-owned durable storage before the
    corresponding public package is published.  It is never included in a
    Gladiator rules bundle.
    """

    records: tuple[SemanticEvidenceRecord, ...]
    snapshot_digest: str

    def __init__(self, *unused: object, **unused_named: object) -> None:
        raise TypeError("SemanticEvidenceSnapshot values must be built through build()")

    @classmethod
    def build(
        cls,
        records: Sequence[SemanticEvidenceRecord],
        *,
        expected_snapshot_digest: str | None = None,
    ) -> SemanticEvidenceSnapshot:
        if not isinstance(records, (tuple, list)) or not records:
            raise SemanticEvidenceError("evidence snapshot requires records")
        if any(type(item) is not SemanticEvidenceRecord for item in records):
            raise SemanticEvidenceError("evidence snapshot contains an invalid record")
        ordered = tuple(sorted(records, key=lambda item: item.evidence_record_digest))
        if len({item.evidence_record_digest for item in ordered}) != len(ordered):
            raise SemanticEvidenceError("evidence snapshot contains duplicate records")
        packet = {
            "schema": 1,
            "records": [item.to_dict() for item in ordered],
        }
        actual = canonical_digest(packet, "semantic evidence snapshot")
        if expected_snapshot_digest is not None and not hmac.compare_digest(
            _digest(expected_snapshot_digest, "snapshotDigest"), actual
        ):
            raise SemanticEvidenceError("semantic evidence snapshot digest mismatch")
        instance = object.__new__(cls)
        object.__setattr__(instance, "records", ordered)
        object.__setattr__(instance, "snapshot_digest", actual)
        return instance

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": 1,
            "records": [item.to_dict() for item in self.records],
            "snapshotDigest": self.snapshot_digest,
        }

    def canonical_json(self) -> bytes:
        return canonical_json(self.to_dict(), "semantic evidence snapshot")

    def record(self, evidence_record_digest: str) -> SemanticEvidenceRecord:
        digest = _digest(evidence_record_digest, "evidenceRecordDigest")
        for record in self.records:
            if record.evidence_record_digest == digest:
                return record
        raise KeyError(digest)


class SemanticEvidenceStore:
    """Instance-bound immutable private evidence records, published atomically."""

    __slots__ = ("__records",)

    def __init__(self) -> None:
        object.__setattr__(self, "_SemanticEvidenceStore__records", MappingProxyType({}))

    def provision_many(
        self,
        records: Sequence[SemanticEvidenceRecord],
    ) -> tuple[str, ...]:
        if not isinstance(records, (tuple, list)) or not records:
            raise SemanticEvidenceError("evidence provisioning requires records")
        if any(type(item) is not SemanticEvidenceRecord for item in records):
            raise SemanticEvidenceError("evidence provisioning contains an invalid record")
        digests = tuple(item.evidence_record_digest for item in records)
        if len(set(digests)) != len(digests):
            raise SemanticEvidenceError("evidence provisioning contains duplicate records")
        next_records = dict(self.__records)
        for record in records:
            prior = next_records.get(record.evidence_record_digest)
            if prior is not None and not hmac.compare_digest(
                prior.canonical_json(), record.canonical_json()
            ):
                raise SemanticEvidenceError("evidence digest collision")
            next_records[record.evidence_record_digest] = record
        object.__setattr__(
            self,
            "_SemanticEvidenceStore__records",
            MappingProxyType(next_records),
        )
        return tuple(sorted(digests))

    def record(self, evidence_record_digest: str) -> SemanticEvidenceRecord:
        digest = _digest(evidence_record_digest, "evidenceRecordDigest")
        try:
            return self.__records[digest]
        except KeyError as exc:
            raise KeyError(digest) from exc

    def inventory_projection(self) -> dict[str, object]:
        return {
            "schema": 1,
            "records": sorted(self.__records),
        }

    def snapshot(self) -> SemanticEvidenceSnapshot:
        return SemanticEvidenceSnapshot.build(tuple(self.__records.values()))


__all__ = [
    "SemanticEvidenceError",
    "SemanticEvidenceRecord",
    "SemanticEvidenceSnapshot",
    "SemanticEvidenceStore",
    "canonical_digest",
    "canonical_json",
]

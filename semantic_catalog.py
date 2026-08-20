"""Selected, immutable TTRPG semantic-package catalog snapshots.

This is the TTRPG-side handoff boundary for already authenticated semantic
packages.  It does not compile source material or choose runtime behavior.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterator, Sequence

from .semantic_packages import (
    CapabilityRequirement,
    SemanticEntity,
    SemanticPackage,
    SemanticPackageError,
)


_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*:[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class SemanticCatalogError(ValueError):
    """A selected semantic package set is malformed or ambiguous."""


def _entity_id(value: object) -> str:
    if type(value) is not str or not _ID_RE.fullmatch(value):
        raise SemanticCatalogError("entityId must be a normalized namespaced ID")
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SemanticCatalogError("catalog projection is not JSON-compatible") from exc


@dataclass(frozen=True, order=True)
class SemanticPackageInventory:
    """Exact selected-package identity, without source-layout information."""

    package_id: str
    version: str
    package_digest: str
    ruleset_id: str
    ruleset_digest: str
    book_id: str
    book_digest: str
    semantic_generation: str
    semantic_generation_digest: str
    compiler_id: str
    compiler_version: str
    compiler_digest: str

    @classmethod
    def from_package(cls, package: SemanticPackage) -> SemanticPackageInventory:
        return cls(
            package_id=package.package_id,
            version=package.version,
            package_digest=package.package_digest,
            ruleset_id=package.ruleset_id,
            ruleset_digest=package.ruleset_digest,
            book_id=package.book_id,
            book_digest=package.book_digest,
            semantic_generation=package.semantic_generation,
            semantic_generation_digest=package.semantic_generation_digest,
            compiler_id=package.compiler_id,
            compiler_version=package.compiler_version,
            compiler_digest=package.compiler_digest,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "packageId": self.package_id,
            "version": self.version,
            "packageDigest": self.package_digest,
            "rulesetId": self.ruleset_id,
            "rulesetDigest": self.ruleset_digest,
            "bookId": self.book_id,
            "bookDigest": self.book_digest,
            "semanticGeneration": self.semantic_generation,
            "semanticGenerationDigest": self.semantic_generation_digest,
            "compilerId": self.compiler_id,
            "compilerVersion": self.compiler_version,
            "compilerDigest": self.compiler_digest,
        }


@dataclass(frozen=True, init=False)
class SemanticCatalogSnapshot:
    """One self-contained selected semantic package set.

    The package objects have been independently decoded and digest-verified on
    construction, rather than retaining caller-owned values.
    """

    packages: tuple[SemanticPackage, ...]
    inventory: tuple[SemanticPackageInventory, ...]
    required_capabilities: tuple[CapabilityRequirement, ...]
    _entities: tuple[SemanticEntity, ...]
    catalog_digest: str

    def __init__(self, *unused: object, **unused_named: object) -> None:
        raise TypeError(
            "SemanticCatalogSnapshot is sealed; use from_selected_packages()"
        )

    @classmethod
    def _sealed(
        cls,
        *,
        packages: tuple[SemanticPackage, ...],
        inventory: tuple[SemanticPackageInventory, ...],
        required_capabilities: tuple[CapabilityRequirement, ...],
        entities: tuple[SemanticEntity, ...],
        catalog_digest: str,
    ) -> SemanticCatalogSnapshot:
        snapshot = object.__new__(cls)
        object.__setattr__(snapshot, "packages", packages)
        object.__setattr__(snapshot, "inventory", inventory)
        object.__setattr__(snapshot, "required_capabilities", required_capabilities)
        object.__setattr__(snapshot, "_entities", entities)
        object.__setattr__(snapshot, "catalog_digest", catalog_digest)
        return snapshot

    @classmethod
    def from_selected_packages(
        cls,
        selected_packages: Sequence[SemanticPackage],
    ) -> SemanticCatalogSnapshot:
        if not selected_packages:
            raise SemanticCatalogError("semantic catalog requires selected packages")
        if not all(isinstance(item, SemanticPackage) for item in selected_packages):
            raise SemanticCatalogError("selected packages must be SemanticPackage values")

        # Re-decode every packet so a caller cannot bypass a package digest
        # fence through a mutated frozen instance.
        try:
            packages = tuple(
                SemanticPackage.from_dict(json.loads(item.canonical_json()))
                for item in selected_packages
            )
        except (SemanticPackageError, json.JSONDecodeError) as exc:
            raise SemanticCatalogError("selected semantic package is not authenticated") from exc
        packages = tuple(sorted(packages, key=lambda item: (item.package_id, item.version)))
        package_keys = tuple((item.package_id, item.version) for item in packages)
        if len(set(package_keys)) != len(package_keys):
            raise SemanticCatalogError("selected packages contain duplicate package identities")

        entities = tuple(
            entity for package in packages for entity in package.entities
        )
        entity_ids = tuple(entity.entity_id for entity in entities)
        if len(set(entity_ids)) != len(entity_ids):
            raise SemanticCatalogError("selected packages contain duplicate entity IDs")
        entities = tuple(sorted(entities, key=lambda item: item.entity_id))
        capabilities = tuple(
            sorted(
                {
                    capability
                    for entity in entities
                    for capability in entity.required_capabilities
                }
            )
        )
        inventory = tuple(SemanticPackageInventory.from_package(item) for item in packages)
        projection = {
            "schema": 1,
            "packages": [item.to_dict() for item in inventory],
            "requiredCapabilities": [item.to_dict() for item in capabilities],
            "entities": [
                {
                    "entityId": entity.entity_id,
                    "entityKind": entity.entity_kind,
                    "definitionDigest": entity.definition_digest,
                    "semanticReceiptDigest": entity.receipt.semantic_receipt_digest,
                }
                for entity in entities
            ],
        }
        return cls._sealed(
            packages=packages,
            inventory=inventory,
            required_capabilities=capabilities,
            entities=entities,
            catalog_digest=hashlib.sha256(_canonical(projection)).hexdigest(),
        )

    def entity(self, entity_id: str) -> SemanticEntity:
        entity_id = _entity_id(entity_id)
        for entity in self._entities:
            if entity.entity_id == entity_id:
                return entity
        raise KeyError(entity_id)

    @property
    def entities(self) -> tuple[SemanticEntity, ...]:
        return self._entities

    @property
    def manifest(self) -> dict[str, object]:
        """Return a fresh callable-free transport projection of this snapshot."""

        return {
            "schema": 1,
            "catalogDigest": self.catalog_digest,
            "packages": [item.to_dict() for item in self.inventory],
            "requiredCapabilities": [item.to_dict() for item in self.required_capabilities],
            "entities": [
                {
                    "entityId": entity.entity_id,
                    "entityKind": entity.entity_kind,
                    "definitionDigest": entity.definition_digest,
                    "semanticReceiptDigest": entity.receipt.semantic_receipt_digest,
                }
                for entity in self._entities
            ],
        }

    def canonical_manifest_json(self) -> bytes:
        return _canonical(self.manifest)


class _SnapshotContext(AbstractContextManager[SemanticCatalogSnapshot]):
    def __init__(self, snapshot: SemanticCatalogSnapshot) -> None:
        self._snapshot = snapshot

    def __enter__(self) -> SemanticCatalogSnapshot:
        return self._snapshot

    def __exit__(self, *unused: object) -> None:
        return None


@dataclass(frozen=True, init=False)
class SemanticCatalog:
    """TTRPG semantic catalog service backed by one explicit selection."""

    _snapshot: SemanticCatalogSnapshot

    def __init__(self, *unused: object, **unused_named: object) -> None:
        raise TypeError("SemanticCatalog is sealed; use from_selected_packages()")

    @classmethod
    def from_selected_packages(
        cls,
        selected_packages: Sequence[SemanticPackage],
    ) -> SemanticCatalog:
        catalog = object.__new__(cls)
        object.__setattr__(
            catalog,
            "_snapshot",
            SemanticCatalogSnapshot.from_selected_packages(selected_packages),
        )
        return catalog

    @property
    def snapshot(self) -> SemanticCatalogSnapshot:
        return self._snapshot

    def open_snapshot(self) -> AbstractContextManager[SemanticCatalogSnapshot]:
        return _SnapshotContext(self._snapshot)

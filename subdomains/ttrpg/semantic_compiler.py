"""Explicit, package-selected semantic compiler composition.

This TTRPG-owned seam selects source compilers.  It deliberately does not
contain Gladiator runtime handlers or a runtime RulesEnvironment.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .pf2er_compiler.mechanics.contracts import MechanicFamilyFragment
from .pf2er_compiler.mechanics.runtime_registry import (
    MechanicRegistry,
    build_registry,
)
from .pf2er_compiler.mechanics.source_authority import SourceAuthorityAdapter


_ID_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*:"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)
_VERSION_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)$"
)


class SemanticCompilerError(ValueError):
    """A semantic compiler selection or identity is malformed."""


def _id(value: object, label: str) -> str:
    if type(value) is not str or not _ID_RE.fullmatch(value):
        raise SemanticCompilerError(
            f"{label} must be a normalized namespaced ID"
        )
    return value


def _version(value: object, label: str) -> str:
    if type(value) is not str or not _VERSION_RE.fullmatch(value):
        raise SemanticCompilerError(
            f"{label} must be a normalized x.y.z version"
        )
    return value


def _sorted_unique(
    values: Iterable[str],
    *,
    label: str,
) -> tuple[str, ...]:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise SemanticCompilerError(f"{label} contains duplicates")
    return tuple(sorted(items))


@dataclass(frozen=True, order=True, slots=True)
class SemanticCompilerPackage:
    """One selected semantic package and its owning source books."""

    package_id: str
    version: str
    book_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "package_id",
            _id(self.package_id, "semantic package ID"),
        )
        object.__setattr__(
            self,
            "version",
            _version(self.version, "semantic package version"),
        )
        if not isinstance(self.book_ids, tuple) or not self.book_ids:
            raise SemanticCompilerError(
                "semantic package book IDs must be a non-empty tuple"
            )
        object.__setattr__(
            self,
            "book_ids",
            _sorted_unique(
                (
                    _id(book_id, "semantic package book ID")
                    for book_id in self.book_ids
                ),
                label="semantic package book IDs",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "packageId": self.package_id,
            "version": self.version,
            "bookIds": list(self.book_ids),
        }


@dataclass(frozen=True, slots=True)
class SemanticCompilerIdentity:
    """Ruleset, package, book, and compiler release identity."""

    compiler_id: str
    compiler_version: str
    ruleset_id: str
    packages: tuple[SemanticCompilerPackage, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "compiler_id",
            _id(self.compiler_id, "semantic compiler ID"),
        )
        object.__setattr__(
            self,
            "compiler_version",
            _version(
                self.compiler_version,
                "semantic compiler version",
            ),
        )
        object.__setattr__(
            self,
            "ruleset_id",
            _id(self.ruleset_id, "ruleset ID"),
        )
        if not isinstance(self.packages, tuple) or not self.packages:
            raise SemanticCompilerError(
                "semantic compiler packages must be a non-empty tuple"
            )
        if any(
            not isinstance(item, SemanticCompilerPackage)
            for item in self.packages
        ):
            raise SemanticCompilerError(
                "semantic compiler packages must contain package identities"
            )
        packages = tuple(sorted(self.packages))
        if len({item.package_id for item in packages}) != len(packages):
            raise SemanticCompilerError(
                "semantic compiler package IDs contain duplicates"
            )
        book_ids = [
            book_id
            for package in packages
            for book_id in package.book_ids
        ]
        if len(set(book_ids)) != len(book_ids):
            raise SemanticCompilerError(
                "semantic compiler book IDs belong to multiple packages"
            )
        object.__setattr__(self, "packages", packages)

    def to_dict(self) -> dict[str, object]:
        return {
            "compilerId": self.compiler_id,
            "compilerVersion": self.compiler_version,
            "rulesetId": self.ruleset_id,
            "packages": [item.to_dict() for item in self.packages],
        }


@dataclass(frozen=True, slots=True, init=False)
class SemanticCompilerSet:
    """One immutable semantic compiler table and callable-free manifest."""

    identity: SemanticCompilerIdentity
    registry: MechanicRegistry
    _manifest_json: bytes
    digest: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "SemanticCompilerSet must be created with "
            "build_semantic_compiler_set()"
        )

    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(self._manifest_json.decode("utf-8"))

    def canonical_manifest(self) -> str:
        return self._manifest_json.decode("utf-8")

    def compile_source_creature(
        self,
        authority: SourceAuthorityAdapter,
        source_id: str,
        locator: str,
        /,
    ) -> dict[str, Any]:
        """Compile one source creature without consulting global compilers."""

        from .pf2er_compiler import source as source_compiler

        return source_compiler.compile_source_creature_with_registry(
            authority,
            source_id,
            locator,
            registry=self.registry,
        )

    def compile_abilities(
        self,
        block: object,
        *,
        creature_name: str,
        source_id: str,
        locator: str,
        **options: object,
    ) -> list[dict[str, Any]]:
        """Compile an exact ability carrier through only this set."""

        from .pf2er_compiler import source as source_compiler

        if "compiler_registry" in options:
            raise TypeError("compiler_registry is owned by SemanticCompilerSet")
        return source_compiler.compile_abilities(
            block,  # type: ignore[arg-type]
            creature_name=creature_name,
            source_id=source_id,
            locator=locator,
            compiler_registry=self.registry,
            **options,  # type: ignore[arg-type]
        )


def _compiler_fragment(
    fragment: MechanicFamilyFragment,
) -> MechanicFamilyFragment:
    if not isinstance(fragment, MechanicFamilyFragment):
        raise SemanticCompilerError(
            "semantic compiler fragments must be MechanicFamilyFragment values"
        )
    if not fragment.ability_compilers:
        raise SemanticCompilerError(
            f"semantic compiler family has no ability compilers: "
            f"{fragment.family_id!r}"
        )
    mechanic_types = tuple(
        dict.fromkeys(
            registration.mechanic_type
            for registration in fragment.ability_compilers
        )
    )
    return MechanicFamilyFragment(
        family_id=fragment.family_id,
        mechanic_types=mechanic_types,
        ability_compilers=fragment.ability_compilers,
    )


def build_semantic_compiler_set(
    *,
    identity: SemanticCompilerIdentity,
    fragments: tuple[MechanicFamilyFragment, ...],
) -> SemanticCompilerSet:
    """Build an explicit compiler set from package-selected family fragments."""

    if not isinstance(identity, SemanticCompilerIdentity):
        raise SemanticCompilerError(
            "semantic compiler identity is required"
        )
    if not isinstance(fragments, tuple) or not fragments:
        raise SemanticCompilerError(
            "semantic compiler fragments must be a non-empty tuple"
        )
    compiler_fragments = tuple(_compiler_fragment(item) for item in fragments)
    registry = build_registry(compiler_fragments)
    manifest = {
        "schema": 1,
        "identity": identity.to_dict(),
        "families": [
            {
                "familyId": fragment.family_id,
                "mechanicTypes": list(fragment.mechanic_types),
                "abilityCompilers": [
                    {
                        "compilerId": registration.compiler_id,
                        "mechanicType": registration.mechanic_type,
                    }
                    for registration in fragment.ability_compilers
                ],
            }
            for fragment in compiler_fragments
        ],
    }
    manifest_json = json.dumps(
        manifest,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    instance = object.__new__(SemanticCompilerSet)
    object.__setattr__(instance, "identity", identity)
    object.__setattr__(instance, "registry", registry)
    object.__setattr__(instance, "_manifest_json", manifest_json)
    object.__setattr__(
        instance,
        "digest",
        hashlib.sha256(manifest_json).hexdigest(),
    )
    return instance


__all__ = [
    "SemanticCompilerError",
    "SemanticCompilerIdentity",
    "SemanticCompilerPackage",
    "SemanticCompilerSet",
    "build_semantic_compiler_set",
]

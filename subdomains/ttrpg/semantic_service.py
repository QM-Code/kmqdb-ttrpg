"""Production composition for the persisted TTRPG semantic HTTP service.

``KMQDB_TTRPG_SEMANTIC_REPOSITORY`` must name one exact catalog-digest
repository directory.  Importing this module performs no filesystem access;
the module-level WSGI application loads and seals its delegate on first use.
A successful process never switches repositories until it is restarted.

The artifact transport is intentionally authentication-neutral.  A deployed
host must wrap this application in authorization middleware appropriate for
the service; this module neither accepts credentials nor grants access.
"""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import re
from threading import Lock
from typing import Any, Iterable

from .semantic_http import (
    SemanticCatalogHttpApplication,
    create_semantic_catalog_application,
)
from .semantic_repository import (
    SemanticRepository,
    SemanticRepositoryError,
    load_semantic_repository,
)


SEMANTIC_REPOSITORY_ENVIRONMENT = "KMQDB_TTRPG_SEMANTIC_REPOSITORY"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SemanticServiceConfigurationError(RuntimeError):
    """The production semantic repository is absent or failed authentication."""


def _configured_repository_path(environment: Mapping[str, str]) -> Path:
    if not isinstance(environment, Mapping):
        raise SemanticServiceConfigurationError(
            "semantic service environment must be a string mapping"
        )
    value = environment.get(SEMANTIC_REPOSITORY_ENVIRONMENT)
    if type(value) is not str or not value or "\x00" in value:
        raise SemanticServiceConfigurationError(
            f"{SEMANTIC_REPOSITORY_ENVIRONMENT} must name an exact repository"
        )
    path = Path(value)
    if not path.is_absolute() or not _DIGEST_RE.fullmatch(path.name):
        raise SemanticServiceConfigurationError(
            f"{SEMANTIC_REPOSITORY_ENVIRONMENT} must be an absolute catalog-digest directory"
        )
    if any(candidate.is_symlink() for candidate in (path, *path.parents)):
        raise SemanticServiceConfigurationError(
            "configured semantic repository path must not traverse a symbolic link"
        )
    return path


def load_configured_semantic_repository(
    environment: Mapping[str, str] | None = None,
) -> SemanticRepository:
    """Strictly load the one repository selected for this service process."""

    selected_environment = os.environ if environment is None else environment
    path = _configured_repository_path(selected_environment)
    try:
        return load_semantic_repository(path)
    except SemanticRepositoryError as exc:
        raise SemanticServiceConfigurationError(
            "configured semantic repository failed strict authentication"
        ) from exc


def create_semantic_service_application(
    environment: Mapping[str, str] | None = None,
) -> SemanticCatalogHttpApplication:
    """Load one exact repository and bind its public HTTP transport.

    Authorization remains the responsibility of the host middleware wrapping
    the returned WSGI application.
    """

    repository = load_configured_semantic_repository(environment)
    return create_semantic_catalog_application(
        repository.envelope,
        repository.package_service,
        repository.asset_service,
    )


class _LazySemanticServiceApplication:
    """Load one production delegate on first request and retain it until restart."""

    __slots__ = ("_delegate", "_lock")

    def __init__(self) -> None:
        self._delegate: SemanticCatalogHttpApplication | None = None
        self._lock = Lock()

    def _application(self) -> SemanticCatalogHttpApplication:
        delegate = self._delegate
        if delegate is not None:
            return delegate
        with self._lock:
            delegate = self._delegate
            if delegate is None:
                delegate = create_semantic_service_application()
                self._delegate = delegate
            return delegate

    def __call__(
        self,
        environ: Mapping[str, object],
        start_response: Any,
    ) -> Iterable[bytes]:
        return self._application()(environ, start_response)


application = _LazySemanticServiceApplication()


__all__ = [
    "SEMANTIC_REPOSITORY_ENVIRONMENT",
    "SemanticServiceConfigurationError",
    "application",
    "create_semantic_service_application",
    "load_configured_semantic_repository",
]

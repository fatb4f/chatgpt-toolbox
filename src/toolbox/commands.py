from __future__ import annotations

from pathlib import Path

from toolbox.model import BundleResult, RepositoryPlan
from toolbox.operations import (
    build_repository,
    clean_cache as clean_shared_cache,
    clean_repository,
    inspect_repository,
)


def inspect(
    repository: str,
    target: str | None = None,
    toolbox_root: Path = Path("."),
) -> RepositoryPlan:
    """Resolve and validate a repository release plan without executing it."""
    return inspect_repository(repository, target, toolbox_root=toolbox_root)


def build(
    repository: str,
    target: str | None = None,
    toolbox_root: Path = Path("."),
    pool_root: Path | None = None,
) -> BundleResult:
    """Build qualified component archives and one installable aggregate release."""
    return build_repository(
        repository,
        target,
        toolbox_root=toolbox_root,
        pool_root=pool_root,
    )


def clean(
    repository: str,
    target: str | None = None,
    toolbox_root: Path = Path("."),
) -> None:
    """Remove disposable repository composition state while preserving the pool."""
    clean_repository(repository, target, toolbox_root=toolbox_root)


def clean_cache(toolbox_root: Path = Path(".")) -> None:
    """Explicitly remove the shared acquisition, projection, and component pool."""
    clean_shared_cache(toolbox_root=toolbox_root)

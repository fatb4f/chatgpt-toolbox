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
    """Resolve and validate a repository bundle plan without executing it.

    Args:
        repository: Closed repository registry key.
        target: Optional target triple; must match registered tool descriptors.
        toolbox_root: Toolbox checkout containing repository descriptors.
    """
    return inspect_repository(repository, target, toolbox_root=toolbox_root)


def build(
    repository: str,
    target: str | None = None,
    toolbox_root: Path = Path("."),
    pool_root: Path | None = None,
) -> BundleResult:
    """Acquire, pool, build, compose, and package one repository bundle.

    Args:
        repository: Closed repository registry key.
        target: Optional target triple; must match registered tool descriptors.
        toolbox_root: Toolbox checkout containing repository descriptors.
        pool_root: Optional shared acquisition and projection cache root.
    """
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
    """Remove one repository's disposable composition workspace.

    Shared acquisitions and built projections are deliberately preserved.
    """
    clean_repository(repository, target, toolbox_root=toolbox_root)


def clean_cache(toolbox_root: Path = Path(".")) -> None:
    """Remove the shared acquisition and built-projection pool."""
    clean_shared_cache(toolbox_root=toolbox_root)

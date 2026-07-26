from __future__ import annotations

from pathlib import Path

from toolbox.model import BundleResult, RepositoryPlan
from toolbox.operations import build_repository, clean_repository, inspect_repository


def inspect(repository: str, target: str | None = None, toolbox_root: Path = Path(".")) -> RepositoryPlan:
    """Resolve and validate a repository bundle plan without executing it.

    Args:
        repository: Closed repository registry key.
        target: Optional target triple; must match registered tool descriptors.
        toolbox_root: Toolbox checkout containing repos and local program sources.
    """
    return inspect_repository(repository, target, toolbox_root=toolbox_root)


def build(repository: str, target: str | None = None, toolbox_root: Path = Path(".")) -> BundleResult:
    """Acquire, verify, build, stage, and package one repository bundle.

    Args:
        repository: Closed repository registry key.
        target: Optional target triple; must match registered tool descriptors.
        toolbox_root: Toolbox checkout containing repos and local program sources.
    """
    return build_repository(repository, target, toolbox_root=toolbox_root)


def clean(repository: str, target: str | None = None, toolbox_root: Path = Path(".")) -> None:
    """Remove intermediate state for one registered repository bundle."""
    clean_repository(repository, target, toolbox_root=toolbox_root)

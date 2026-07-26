from __future__ import annotations

from graphlib import TopologicalSorter, CycleError
from types import MappingProxyType
from typing import Mapping

from toolbox.model import DescriptorError, RepositorySpec, ToolSpec
from toolbox.repositories.dotfiles import SPEC as DOTFILES
from toolbox.tools.cue import SPEC as CUE
from toolbox.tools.context_git_hydrator import SPEC as CONTEXT_GIT_HYDRATOR
from toolbox.tools.go import SPEC as GO
from toolbox.tools.go_git import SPEC as GO_GIT
from toolbox.tools.goimports import SPEC as GOIMPORTS
from toolbox.tools.gopls import SPEC as GOPLS
from toolbox.tools.lua import SPEC as LUA
from toolbox.tools.luals import SPEC as LUALS
from toolbox.tools.python import SPEC as PYTHON
from toolbox.tools.uv import SPEC as UV


def _closed_registry(items: tuple[ToolSpec, ...]) -> Mapping[str, ToolSpec]:
    registry: dict[str, ToolSpec] = {}
    for item in items:
        if item.name in registry:
            raise DescriptorError(f"duplicate tool descriptor: {item.name}")
        registry[item.name] = item
    return MappingProxyType(registry)


TOOLS: Mapping[str, ToolSpec] = _closed_registry(
    (PYTHON, GO, CUE, GOPLS, GOIMPORTS, UV, LUA, LUALS, GO_GIT, CONTEXT_GIT_HYDRATOR)
)
REPOSITORIES: Mapping[str, RepositorySpec] = MappingProxyType({DOTFILES.name: DOTFILES})


def get_repository(name: str) -> RepositorySpec:
    try:
        return REPOSITORIES[name]
    except KeyError as error:
        raise DescriptorError(
            f"unknown repository {name!r}; expected one of {tuple(REPOSITORIES)}"
        ) from error


def selected_tools(
    repository: RepositorySpec, *, target: str | None = None
) -> Mapping[str, ToolSpec]:
    resolved_target = target or repository.target
    selected: dict[str, ToolSpec] = {}
    for name in repository.tools:
        try:
            tool = TOOLS[name]
        except KeyError as error:
            raise DescriptorError(
                f"repository {repository.name} selects unknown tool {name!r}"
            ) from error
        if tool.target != resolved_target:
            raise DescriptorError(
                f"tool {name} targets {tool.target}, but repository {repository.name} targets {resolved_target}"
            )
        selected[name] = tool

    missing: dict[str, tuple[str, ...]] = {}
    for name, tool in selected.items():
        unresolved = tuple(
            dependency for dependency in tool.requires if dependency not in selected
        )
        if unresolved:
            missing[name] = unresolved
    if missing:
        raise DescriptorError(
            f"repository {repository.name} has unresolved dependencies: {missing}"
        )
    return MappingProxyType(selected)


def topological_tools(
    repository: RepositorySpec, *, target: str | None = None
) -> tuple[ToolSpec, ...]:
    selected = selected_tools(repository, target=target)
    graph = {name: set(tool.requires) for name, tool in selected.items()}
    try:
        order = tuple(TopologicalSorter(graph).static_order())
    except CycleError as error:
        raise DescriptorError(
            f"repository {repository.name} tool graph is cyclic: {error.args[1]}"
        ) from error
    return tuple(selected[name] for name in order)

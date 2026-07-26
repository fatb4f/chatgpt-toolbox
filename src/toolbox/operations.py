from __future__ import annotations

from pathlib import Path
from typing import Mapping
import re
import shutil

from toolbox.acquisition import AcquiredArtifact, SubprocessRunner, acquire_tool
from toolbox.builders import build_and_stage_tool
from toolbox.model import AcquisitionKind, BundleResult, PlanNode, RepositoryPlan, ToolRole, ToolSpec, to_primitive
from toolbox.packaging import create_deterministic_archive, write_native_lock
from toolbox.registry import get_repository, selected_tools, topological_tools
from toolbox.staging import write_activation


class OperationError(RuntimeError):
    pass


def _verify_go_module_edges(
    tool: ToolSpec,
    artifact: AcquiredArtifact,
    selected: Mapping[str, ToolSpec],
) -> None:
    if artifact.path is None:
        return
    module_dependencies = [
        selected[name]
        for name in tool.requires
        if selected[name].acquisition.kind is AcquisitionKind.GO_MODULE
    ]
    if not module_dependencies:
        return
    go_mod = artifact.path / tool.build.source_subdir / "go.mod"
    if not go_mod.is_file():
        raise OperationError(f"{tool.name} requires Go modules but has no go.mod at {go_mod}")
    content = go_mod.read_text(encoding="utf-8")
    for dependency in module_dependencies:
        module = dependency.acquisition.module or ""
        version = dependency.acquisition.version or ""
        pattern = rf"(?m)^\s*(?:require\s+)?{re.escape(module)}\s+{re.escape(version)}(?:\s+//\s*indirect)?\s*$"
        if re.search(pattern, content) is None:
            raise OperationError(
                f"{tool.name} go.mod does not require declared module {module}@{version}"
            )


def inspect_repository(repository: str, target: str | None = None, *, toolbox_root: Path = Path(".")) -> RepositoryPlan:
    descriptor = get_repository(repository)
    resolved_target = target or descriptor.target
    tools = topological_tools(descriptor, target=resolved_target)
    nodes = tuple(
        PlanNode(
            name=tool.name,
            kind="program" if ToolRole.PROGRAM in tool.roles else "tool",
            version=tool.version,
            requires=tool.requires,
            roles=tuple(sorted(role.value for role in tool.roles)),
            acquisition=tool.acquisition,
            build=tool.build,
        )
        for tool in tools
    )
    defects_list = [defect for tool in tools for defect in tool.lock_defects]
    for tool in tools:
        if tool.acquisition.kind is AcquisitionKind.LOCAL_SOURCE:
            source = toolbox_root / (tool.acquisition.path or "")
            if not source.exists():
                defects_list.append(f"{tool.name}: local source path does not exist: {source.as_posix()}")
    defects = tuple(defects_list)
    output = toolbox_root / descriptor.dist_dir / f"{descriptor.name}-{resolved_target}.tar.gz"
    return RepositoryPlan(
        repository=descriptor.name,
        target=resolved_target,
        python_group=descriptor.python_group,
        output=output.as_posix(),
        nodes=nodes,
        lock_defects=defects,
    )


def build_repository(
    repository: str,
    target: str | None = None,
    *,
    toolbox_root: Path = Path("."),
    work_root: Path | None = None,
) -> BundleResult:
    plan = inspect_repository(repository, target, toolbox_root=toolbox_root)
    if not plan.admissible:
        formatted = "\n".join(f"- {defect}" for defect in plan.lock_defects)
        raise OperationError(f"bundle plan has unresolved lock authority:\n{formatted}")

    descriptor = get_repository(repository)
    tools = topological_tools(descriptor, target=plan.target)
    selected = selected_tools(descriptor, target=plan.target)
    workspace = work_root or toolbox_root / ".toolbox-work" / f"{descriptor.name}-{plan.target}"
    downloads = workspace / "downloads"
    sources = workspace / "sources"
    builds = workspace / "build"
    prefix = workspace / "prefix"
    shutil.rmtree(prefix, ignore_errors=True)
    prefix.mkdir(parents=True)
    runner = SubprocessRunner()
    lock_tools: list[dict[str, object]] = []

    for tool in tools:
        artifact = acquire_tool(
            tool,
            downloads=downloads,
            sources=sources,
            toolbox_root=toolbox_root,
            runner=runner,
        )
        _verify_go_module_edges(tool, artifact, selected)
        build_and_stage_tool(tool, artifact, prefix=prefix, build_root=builds, runner=runner)
        lock_tools.append(
            {
                "name": tool.name,
                "version": tool.version,
                "identity": artifact.identity,
                "acquisition": to_primitive(tool.acquisition),
                "build": to_primitive(tool.build),
            }
        )

    write_activation(prefix)
    lockfile = write_native_lock(
        prefix / "native-lock.json",
        {
            "schema": "toolbox.native-lock.v0",
            "repository": descriptor.name,
            "target": plan.target,
            "tools": lock_tools,
        },
    )
    root_name = f"{descriptor.name}-{plan.target}"
    archive = toolbox_root / descriptor.dist_dir / f"{root_name}.tar.gz"
    create_deterministic_archive(prefix, archive, root_name)
    return BundleResult(
        repository=descriptor.name,
        target=plan.target,
        prefix=prefix.as_posix(),
        archive=archive.as_posix(),
        lockfile=lockfile.as_posix(),
    )


def clean_repository(repository: str, target: str | None = None, *, toolbox_root: Path = Path(".")) -> None:
    descriptor = get_repository(repository)
    resolved_target = target or descriptor.target
    shutil.rmtree(toolbox_root / ".toolbox-work" / f"{descriptor.name}-{resolved_target}", ignore_errors=True)

from __future__ import annotations

from pathlib import Path
from typing import Mapping
import os
import re
import shutil
import subprocess

from toolbox.acquisition import (
    AcquiredArtifact,
    Runner,
    SubprocessRunner,
    acquire,
    acquire_tool,
)
from toolbox.model import (
    AcquisitionKind,
    BundleResult,
    PlanNode,
    RepositoryPlan,
    ToolRole,
    ToolSpec,
)
from toolbox.pool import ToolProjection, ensure_tool_projection
from toolbox.registry import get_repository, selected_tools, topological_tools
from toolbox.release import build_components, publish_release
from toolbox.source import (
    SourceProjectionError,
    patch_identity,
    prepare_repository_source,
)
from toolbox.staging import stage_projection


class OperationError(RuntimeError):
    pass


def _verify_tool_probes(
    tools: tuple[ToolSpec, ...],
    prefix: Path,
    runner: Runner,
) -> None:
    resolved = prefix.resolve()
    environment = {
        **os.environ,
        "PATH": os.pathsep.join((str(resolved / "bin"), os.environ.get("PATH", ""))),
        "GOROOT": str(resolved / "libexec" / "go"),
        "GOTOOLCHAIN": "local",
        "GOBIN": str(resolved / "bin"),
    }
    for tool in tools:
        for probe in tool.probes:
            try:
                runner.run(probe, env=environment, capture_output=True)
            except subprocess.CalledProcessError as error:
                raise OperationError(
                    f"runtime probe failed for {tool.name}: {' '.join(probe)}"
                ) from error


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
        raise OperationError(
            f"{tool.name} requires Go modules but has no go.mod at {go_mod}"
        )
    content = go_mod.read_text(encoding="utf-8")
    for dependency in module_dependencies:
        module = dependency.acquisition.module or ""
        version = dependency.acquisition.version or ""
        pattern = (
            rf"(?m)^\s*(?:require\s+)?{re.escape(module)}\s+"
            rf"{re.escape(version)}(?:\s+//\s*indirect)?\s*$"
        )
        if re.search(pattern, content) is None:
            raise OperationError(
                f"{tool.name} go.mod does not require declared module "
                f"{module}@{version}"
            )


def inspect_repository(
    repository: str,
    target: str | None = None,
    *,
    toolbox_root: Path = Path("."),
) -> RepositoryPlan:
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
    if descriptor.source is not None:
        defects_list.extend(
            f"repository source: {defect}" for defect in descriptor.source.lock_defects
        )
    try:
        patch_identity(descriptor, toolbox_root)
    except SourceProjectionError as error:
        defects_list.append(str(error))
    for tool in tools:
        if tool.acquisition.kind is AcquisitionKind.LOCAL_SOURCE:
            source = toolbox_root / (tool.acquisition.path or "")
            if not source.exists():
                defects_list.append(
                    f"{tool.name}: local source path does not exist: "
                    f"{source.as_posix()}"
                )
    defects = tuple(defects_list)
    output = (
        toolbox_root
        / descriptor.dist_dir
        / "release"
        / f"{descriptor.name}-tools-linux-amd64.tar.zst"
    )
    return RepositoryPlan(
        repository=descriptor.name,
        target=resolved_target,
        python_group=descriptor.python_group,
        output=output.as_posix(),
        nodes=nodes,
        components=descriptor.components,
        lock_defects=defects,
    )


def build_repository(
    repository: str,
    target: str | None = None,
    *,
    toolbox_root: Path = Path("."),
    work_root: Path | None = None,
    pool_root: Path | None = None,
) -> BundleResult:
    plan = inspect_repository(repository, target, toolbox_root=toolbox_root)
    if not plan.admissible:
        formatted = "\n".join(f"- {defect}" for defect in plan.lock_defects)
        raise OperationError(
            f"bundle plan has unresolved lock authority:\n{formatted}"
        )

    descriptor = get_repository(repository)
    tools = topological_tools(descriptor, target=plan.target)
    selected = selected_tools(descriptor, target=plan.target)
    workspace = work_root or (
        toolbox_root / ".toolbox-work" / f"{descriptor.name}-{plan.target}"
    )
    pool = pool_root or toolbox_root / ".toolbox-cache"
    downloads = pool / "downloads"
    sources = pool / "sources"
    builds = pool / "builds" / plan.target
    projections_root = pool / "projections" / plan.target
    components_root = pool / "components" / plan.target
    composed_prefix = workspace / "composition"
    aggregate_root = workspace / "aggregate"
    release_dir = toolbox_root / descriptor.dist_dir / "release"
    shutil.rmtree(composed_prefix, ignore_errors=True)
    composed_prefix.mkdir(parents=True)
    runner = SubprocessRunner()
    artifacts: dict[str, AcquiredArtifact] = {}
    projections: dict[str, ToolProjection] = {}

    for tool in tools:
        artifact = acquire_tool(
            tool,
            downloads=downloads,
            sources=sources,
            toolbox_root=toolbox_root,
            runner=runner,
        )
        _verify_go_module_edges(tool, artifact, selected)
        dependency_keys = {
            dependency: projections[dependency].key for dependency in tool.requires
        }
        projection = ensure_tool_projection(
            tool,
            artifact,
            dependency_keys=dependency_keys,
            projections_root=projections_root,
            builds_root=builds,
            toolchain_prefix=composed_prefix,
            runner=runner,
        )
        stage_projection(projection.root, composed_prefix)
        artifacts[tool.name] = artifact
        projections[tool.name] = projection

    _verify_tool_probes(tools, composed_prefix, runner)
    if descriptor.source is None:
        raise OperationError("repository source authority is missing")
    repository_artifact = acquire(
        f"repository-{descriptor.name}",
        descriptor.source,
        downloads=downloads,
        sources=sources,
        toolbox_root=toolbox_root,
        runner=runner,
    )
    repository_artifact = prepare_repository_source(
        descriptor,
        repository_artifact,
        toolbox_root=toolbox_root,
        destination=workspace / "repository-source-projection",
        runner=runner,
    )
    components = build_components(
        repository=descriptor,
        tools=tools,
        projections=projections,
        artifacts=artifacts,
        repository_artifact=repository_artifact,
        composed_prefix=composed_prefix,
        components_root=components_root,
        work_root=workspace,
        runner=runner,
    )
    archive, manifest, lockfile, component_paths = publish_release(
        repository=descriptor,
        tools=tools,
        artifacts=artifacts,
        projections=projections,
        repository_artifact=repository_artifact,
        components=components,
        release_dir=release_dir,
        aggregate_root=aggregate_root,
    )
    return BundleResult(
        repository=descriptor.name,
        target=plan.target,
        release_dir=release_dir.as_posix(),
        archive=archive.as_posix(),
        manifest=manifest.as_posix(),
        lockfile=lockfile.as_posix(),
        components=tuple(path.as_posix() for path in component_paths),
        prefix=aggregate_root.as_posix(),
    )


def clean_repository(
    repository: str,
    target: str | None = None,
    *,
    toolbox_root: Path = Path("."),
) -> None:
    descriptor = get_repository(repository)
    resolved_target = target or descriptor.target
    shutil.rmtree(
        toolbox_root / ".toolbox-work" / f"{descriptor.name}-{resolved_target}",
        ignore_errors=True,
    )


def clean_cache(*, toolbox_root: Path = Path(".")) -> None:
    shutil.rmtree(toolbox_root / ".toolbox-cache", ignore_errors=True)

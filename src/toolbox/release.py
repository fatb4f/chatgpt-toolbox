from __future__ import annotations

from dataclasses import dataclass
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Callable, Mapping
import hashlib
import json
import os
import shutil

from toolbox.acquisition import AcquiredArtifact, Runner, sha256_file, sha256_tree
from toolbox.model import (
    ComponentKind,
    ComponentSpec,
    PythonProjectSpec,
    RepositorySpec,
    ToolRole,
    ToolSpec,
    to_primitive,
)
from toolbox.packaging import (
    archive_record,
    canonical_json_bytes,
    create_deterministic_tar_zst,
    finalize_component_stage,
    verify_deterministic_tar_zst,
    verify_release_directory,
    write_bundle_support,
    write_json,
    write_outer_installer,
    write_release_checksums,
)
from toolbox.pool import (
    CachedComponent,
    ToolProjection,
    component_cache_key,
    valid_cached_component,
)
from toolbox.qualification import (
    materialize_python_closure,
    qualify_cue_repository_source,
    qualify_context_git_hydrator,
    write_qualification_report,
)
from toolbox.staging import stage_projection


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ComponentRecord:
    specification: ComponentSpec
    key: str
    root: Path
    archive: Path
    archive_record: Mapping[str, object]
    qualification: Mapping[str, object]
    reused: bool


def target_document(target: str) -> dict[str, object]:
    if target != "x86_64-unknown-linux-gnu":
        raise ReleaseError(f"unsupported release target: {target}")
    return {
        "os": "linux",
        "arch": "amd64",
        "abi": {"libc": "glibc", "minVersion": "2.17"},
        "triple": target,
    }


def component_order(components: tuple[ComponentSpec, ...]) -> tuple[ComponentSpec, ...]:
    by_name = {component.name: component for component in components}
    graph = {component.name: set(component.requires) for component in components}
    return tuple(by_name[name] for name in TopologicalSorter(graph).static_order())


def _write_component_marker(
    entry: Path,
    *,
    key: str,
    root: Path,
    archive: Path,
    manifest: Mapping[str, object],
) -> None:
    write_json(
        entry / "complete.json",
        {
            "schema": "toolbox.component-cache.v1",
            "key": key,
            "treeSha256": sha256_tree(root),
            "archiveSha256": sha256_file(archive),
            "manifest": manifest,
        },
    )


def ensure_component(
    *,
    specification: ComponentSpec,
    key_payload: Mapping[str, object],
    components_root: Path,
    archive_name: str,
    manifest: Mapping[str, object],
    build_stage: Callable[[Path], Mapping[str, object]],
) -> ComponentRecord:
    key = component_cache_key(
        {
            "schema": "toolbox.component-key.v1",
            "component": specification,
            "inputs": key_payload,
        }
    )
    entry = components_root / key
    root = entry / "root"
    archive = entry / archive_name
    if valid_cached_component(entry, key, archive_name):
        verify_deterministic_tar_zst(archive, root)
        marker = json.loads((entry / "complete.json").read_text(encoding="utf-8"))
        qualification = marker.get("manifest", {}).get("qualification", {})
        return ComponentRecord(
            specification=specification,
            key=key,
            root=root,
            archive=archive,
            archive_record=archive_record(archive),
            qualification=qualification,
            reused=True,
        )

    components_root.mkdir(parents=True, exist_ok=True)
    temporary = components_root / f".{key}.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary_root = temporary / "root"
    temporary_root.mkdir(parents=True)
    qualification = dict(build_stage(temporary_root))
    resolved_manifest = dict(manifest)
    resolved_manifest["qualification"] = qualification
    finalize_component_stage(temporary_root, specification.name, resolved_manifest)
    temporary_archive = temporary / archive_name
    create_deterministic_tar_zst(temporary_root, temporary_archive)
    verify_deterministic_tar_zst(temporary_archive, temporary_root)
    _write_component_marker(
        temporary,
        key=key,
        root=temporary_root,
        archive=temporary_archive,
        manifest=resolved_manifest,
    )
    shutil.rmtree(entry, ignore_errors=True)
    os.replace(temporary, entry)
    return ComponentRecord(
        specification=specification,
        key=key,
        root=root,
        archive=archive,
        archive_record=archive_record(archive),
        qualification=qualification,
        reused=False,
    )


def _copy_tracked_source(source: Path, destination: Path, runner: Runner) -> None:
    completed = runner.run(
        ["git", "ls-files", "-z"], cwd=source, capture_output=True
    )
    destination.mkdir(parents=True, exist_ok=True)
    for relative in filter(None, completed.stdout.split("\0")):
        source_path = source / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_symlink():
            os.symlink(os.readlink(source_path), target)
        elif source_path.is_file():
            shutil.copy2(source_path, target)
        else:
            raise ReleaseError(f"tracked source path is not materializable: {relative}")


def _wrapper_environment_path(project: PythonProjectSpec) -> tuple[str, ...]:
    return (project.environment_path,)


def build_components(
    *,
    repository: RepositorySpec,
    tools: tuple[ToolSpec, ...],
    projections: Mapping[str, ToolProjection],
    artifacts: Mapping[str, AcquiredArtifact],
    repository_artifact: AcquiredArtifact,
    composed_prefix: Path,
    components_root: Path,
    work_root: Path,
    runner: Runner,
) -> tuple[ComponentRecord, ...]:
    if repository_artifact.path is None:
        raise ReleaseError("repository source acquisition did not produce a checkout")
    source = repository_artifact.path
    by_name = {component.name: component for component in repository.components}
    tool_by_name = {tool.name: tool for tool in tools}
    program_names = set(repository.programs)

    native_names = tuple(
        tool.name
        for tool in tools
        if tool.name not in program_names and ToolRole.MODULE not in tool.roles
    )
    program_projection_names = tuple(
        name for name in repository.programs if name in projections
    )

    records: dict[str, ComponentRecord] = {}
    for specification in component_order(repository.components):
        base_manifest = {
            "schema": "toolbox.component-manifest.v1",
            "name": specification.name,
            "kind": specification.kind.value,
            "target": target_document(repository.target),
            "requires": list(specification.requires),
        }
        archive_name = (
            f"{repository.name}-{specification.name}-linux-amd64.tar.zst"
        )

        if specification.kind is ComponentKind.NATIVE_BASE:
            key_payload = {
                "projections": {
                    name: projections[name].key for name in native_names
                }
            }

            def build_native(stage: Path) -> Mapping[str, object]:
                for name in native_names:
                    stage_projection(projections[name].root, stage)
                return {
                    "schema": "toolbox.component-qualification.v1",
                    "status": "passed",
                    "probes": list(native_names),
                }

            record = ensure_component(
                specification=specification,
                key_payload=key_payload,
                components_root=components_root,
                archive_name=archive_name,
                manifest={
                    **base_manifest,
                    "tools": {
                        name: {
                            "projectionKey": projections[name].key,
                            "version": tool_by_name[name].version,
                        }
                        for name in native_names
                    },
                },
                build_stage=build_native,
            )

        elif specification.kind is ComponentKind.GO_PROGRAMS:
            key_payload = {
                "projections": {
                    name: projections[name].key for name in program_projection_names
                },
                "qualificationContract": "toolbox.go-programs-qualification.v1",
            }

            def build_programs(stage: Path) -> Mapping[str, object]:
                program_qualifications: dict[str, Mapping[str, object]] = {}
                for name in program_projection_names:
                    resolved = projections[name].resolved_build
                    if name == "context-git-hydrator":
                        if resolved.source_digest is None:
                            raise ReleaseError(
                                "context-git-hydrator projection has no source digest"
                            )
                        program_qualifications[name] = qualify_context_git_hydrator(
                            prefix=composed_prefix,
                            work_root=work_root / "qualification" / name,
                            runner=runner,
                            expected_digest=resolved.source_digest,
                        )
                    stage_projection(projections[name].root, stage)
                    report = program_qualifications.get(name)
                    if report:
                        write_qualification_report(
                            stage
                            / "share"
                            / "toolbox"
                            / "qualification"
                            / f"{name}.json",
                            report,
                        )
                return {
                    "schema": "toolbox.component-qualification.v1",
                    "status": "passed",
                    "programs": program_qualifications,
                }

            record = ensure_component(
                specification=specification,
                key_payload=key_payload,
                components_root=components_root,
                archive_name=archive_name,
                manifest={
                    **base_manifest,
                    "programs": {
                        name: {
                            "projectionKey": projections[name].key,
                            "sourceIdentity": artifacts[name].identity,
                            "sourceDigest": projections[name].resolved_build.source_digest,
                        }
                        for name in program_projection_names
                    },
                },
                build_stage=build_programs,
            )

        elif specification.kind is ComponentKind.REPOSITORY_SOURCE:
            key_payload = {
                "sourceIdentity": repository_artifact.identity,
                "qualificationContract": "toolbox.cue-contract-suite.v1",
            }

            def build_source(stage: Path) -> Mapping[str, object]:
                qualification = qualify_cue_repository_source(
                    source=source,
                    prefix=composed_prefix,
                    work_root=work_root / "qualification" / "repository-source",
                    runner=runner,
                )
                source_root = stage / "share" / repository.name / "source"
                _copy_tracked_source(source, source_root, runner)
                write_qualification_report(
                    stage
                    / "share"
                    / "toolbox"
                    / "qualification"
                    / "repository-source.json",
                    qualification,
                )
                return qualification

            record = ensure_component(
                specification=specification,
                key_payload=key_payload,
                components_root=components_root,
                archive_name=archive_name,
                manifest={
                    **base_manifest,
                    "repository": {
                        "name": repository.name,
                        "sourceIdentity": repository_artifact.identity,
                        "acquisition": to_primitive(repository.source),
                        "patches": to_primitive(repository.patches),
                    },
                },
                build_stage=build_source,
            )

        elif specification.kind is ComponentKind.PYTHON_PROJECTS:
            project = repository.python_project
            if project is None:
                raise ReleaseError("repository has no Python project descriptor")
            project_root = source / project.project_path
            pyproject = project_root / "pyproject.toml"
            lock = project_root / project.lock_path
            key_payload = {
                "sourceIdentity": repository_artifact.identity,
                "pythonProject": to_primitive(project),
                "pyprojectSha256": sha256_file(pyproject),
                "lockSha256": sha256_file(lock),
                "nativeBaseKey": records["native-base"].key,
            }

            def build_python(stage: Path) -> Mapping[str, object]:
                report = materialize_python_closure(
                    source=source,
                    project=project,
                    prefix=composed_prefix,
                    stage=stage,
                    work_root=work_root / "qualification" / "python-projects",
                    runner=runner,
                )
                write_qualification_report(
                    stage
                    / "share"
                    / "toolbox"
                    / "qualification"
                    / "python-projects.json",
                    report,
                )
                return report

            record = ensure_component(
                specification=specification,
                key_payload=key_payload,
                components_root=components_root,
                archive_name=archive_name,
                manifest={
                    **base_manifest,
                    "pythonProject": to_primitive(project),
                    "sourceIdentity": repository_artifact.identity,
                },
                build_stage=build_python,
            )
        else:
            raise AssertionError(f"unhandled component kind: {specification.kind}")
        records[specification.name] = record

    return tuple(records[component.name] for component in component_order(repository.components))


def publish_release(
    *,
    repository: RepositorySpec,
    tools: tuple[ToolSpec, ...],
    artifacts: Mapping[str, AcquiredArtifact],
    projections: Mapping[str, ToolProjection],
    repository_artifact: AcquiredArtifact,
    components: tuple[ComponentRecord, ...],
    release_dir: Path,
    aggregate_root: Path,
) -> tuple[Path, Path, Path, tuple[Path, ...]]:
    shutil.rmtree(release_dir, ignore_errors=True)
    release_dir.mkdir(parents=True)
    shutil.rmtree(aggregate_root, ignore_errors=True)
    aggregate_root.mkdir(parents=True)

    component_documents: dict[str, object] = {}
    component_paths: list[Path] = []
    for component in components:
        stage_projection(component.root, aggregate_root)
        destination = release_dir / component.archive_record["name"]
        shutil.copy2(component.archive, destination)
        verify_deterministic_tar_zst(destination, component.root)
        checksum = release_dir / f"{destination.name}.sha256"
        checksum.write_text(
            f"{sha256_file(destination)}  {destination.name}\n", encoding="utf-8"
        )
        component_paths.append(destination)
        component_documents[component.specification.name] = {
            "kind": component.specification.kind.value,
            "requires": list(component.specification.requires),
            "key": component.key,
            "archive": archive_record(destination),
            "qualification": component.qualification,
        }

    lock_document = {
        "schema": "toolbox.repository-release-lock.v1",
        "repository": {
            "name": repository.name,
            "sourceIdentity": repository_artifact.identity,
            "acquisition": to_primitive(repository.source),
            "patches": to_primitive(repository.patches),
        },
        "target": target_document(repository.target),
        "toolGraph": {
            tool.name: {
                "version": tool.version,
                "requires": list(tool.requires),
                "roles": sorted(role.value for role in tool.roles),
                "acquisition": to_primitive(tool.acquisition),
                "identity": artifacts[tool.name].identity,
                "projectionKey": projections[tool.name].key,
                "resolvedBuild": to_primitive(projections[tool.name].resolved_build),
            }
            for tool in tools
        },
        "componentGraph": component_documents,
        "pythonProject": to_primitive(repository.python_project),
    }
    lock_path = write_json(
        release_dir / "release-lock.json", lock_document, canonical=True
    )
    lock_digest = hashlib.sha256(canonical_json_bytes(lock_document)).hexdigest()

    project = repository.python_project
    python_project_manifest: dict[str, object] | None = None
    mutable_paths: tuple[str, ...] = ()
    if project is not None:
        python_project_manifest = {
            "sourceRoot": f"share/{repository.name}/source",
            "projectPath": project.project_path,
            "lockPath": project.lock_path,
            "groups": list(project.groups),
            "environmentPath": project.environment_path,
            "cachePath": project.cache_path,
        }
        mutable_paths = _wrapper_environment_path(project)

    embedded_manifest: dict[str, object] = {
        "schema": "toolbox.combined-repository-bundle-manifest.v1",
        "lockDigest": lock_digest,
        "repository": {
            "name": repository.name,
            "sourceIdentity": repository_artifact.identity,
        },
        "target": target_document(repository.target),
        "components": component_documents,
    }
    if python_project_manifest is not None:
        embedded_manifest["pythonProject"] = python_project_manifest
    write_json(
        aggregate_root / "share" / "toolbox" / "release-lock.json",
        lock_document,
        canonical=True,
    )
    write_bundle_support(
        aggregate_root,
        repository=repository.name,
        manifest=embedded_manifest,
        mutable_paths=mutable_paths,
    )

    aggregate_name = f"{repository.name}-tools-linux-amd64.tar.zst"
    aggregate = create_deterministic_tar_zst(
        aggregate_root, release_dir / aggregate_name
    )
    verify_deterministic_tar_zst(aggregate, aggregate_root)
    manifest_document = {
        "schema": "toolbox.repository-release-manifest.v1",
        "lockDigest": lock_digest,
        "releaseTag": f"{repository.name}-tools-{lock_digest}",
        "repository": {
            "name": repository.name,
            "sourceIdentity": repository_artifact.identity,
        },
        "target": target_document(repository.target),
        "components": component_documents,
        "archive": archive_record(aggregate),
        "releaseLock": archive_record(lock_path),
        "hostRequirements": {
            "install": ["bash", "sha256sum", "tar", "zstd"],
            "build": ["git", "make", "cc", "jq", "zstd"],
        },
    }
    manifest = write_json(release_dir / "manifest.json", manifest_document)
    installer = write_outer_installer(
        release_dir / "install.sh",
        repository=repository.name,
        archive_name=aggregate.name,
    )
    write_release_checksums(
        release_dir,
        (aggregate.name, manifest.name, lock_path.name, installer.name),
    )
    verify_release_directory(release_dir)
    return aggregate, manifest, lock_path, tuple(component_paths)

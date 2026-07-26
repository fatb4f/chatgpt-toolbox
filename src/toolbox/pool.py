from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import hashlib
import json
import os
import shutil

from toolbox.acquisition import AcquiredArtifact, Runner, sha256_file, sha256_tree
from toolbox.builders import ResolvedBuild, build_and_stage_tool, resolve_build
from toolbox.model import ToolSpec, to_primitive


@dataclass(frozen=True, slots=True)
class ToolProjection:
    key: str
    root: Path
    resolved_build: ResolvedBuild
    reused: bool


@dataclass(frozen=True, slots=True)
class CachedComponent:
    key: str
    root: Path
    archive: Path
    archive_sha256: str
    reused: bool


def projection_cache_key(
    tool: ToolSpec,
    artifact: AcquiredArtifact,
    dependency_keys: Mapping[str, str],
    resolved_build: ResolvedBuild,
) -> str:
    payload = {
        "schema": "toolbox.tool-projection-key.v1",
        "tool": to_primitive(tool),
        "sourceIdentity": artifact.identity,
        "resolvedBuild": to_primitive(resolved_build),
        "dependencies": dict(sorted(dependency_keys.items())),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _valid_projection(entry: Path, key: str) -> bool:
    root = entry / "root"
    marker = entry / "complete.json"
    if not root.is_dir() or not marker.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("key") == key and payload.get("treeSha256") == sha256_tree(root)


def ensure_tool_projection(
    tool: ToolSpec,
    artifact: AcquiredArtifact,
    *,
    dependency_keys: Mapping[str, str],
    projections_root: Path,
    builds_root: Path,
    toolchain_prefix: Path,
    runner: Runner,
) -> ToolProjection:
    resolved = resolve_build(tool, artifact)
    key = projection_cache_key(tool, artifact, dependency_keys, resolved)
    entry = projections_root / key
    root = entry / "root"
    if _valid_projection(entry, key):
        return ToolProjection(
            key=key, root=root, resolved_build=resolved, reused=True
        )

    projections_root.mkdir(parents=True, exist_ok=True)
    temporary = projections_root / f".{key}.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary_root = temporary / "root"
    temporary_root.mkdir(parents=True)

    build_and_stage_tool(
        tool,
        artifact,
        prefix=temporary_root,
        build_root=builds_root / "tools" / key,
        runner=runner,
        toolchain_prefix=toolchain_prefix,
        go_cache_root=builds_root / "go-cache",
        resolved_build=resolved,
    )
    (temporary / "complete.json").write_text(
        json.dumps(
            {
                "schema": "toolbox.tool-projection.v1",
                "key": key,
                "tool": tool.name,
                "version": tool.version,
                "sourceIdentity": artifact.identity,
                "resolvedBuild": to_primitive(resolved),
                "dependencies": dict(sorted(dependency_keys.items())),
                "treeSha256": sha256_tree(temporary_root),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(entry, ignore_errors=True)
    os.replace(temporary, entry)
    return ToolProjection(key=key, root=root, resolved_build=resolved, reused=False)


def component_cache_key(payload: object) -> str:
    encoded = json.dumps(
        to_primitive(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def valid_cached_component(entry: Path, key: str, archive_name: str) -> bool:
    marker = entry / "complete.json"
    root = entry / "root"
    archive = entry / archive_name
    if not marker.is_file() or not root.is_dir() or not archive.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        payload.get("key") == key
        and payload.get("treeSha256") == sha256_tree(root)
        and payload.get("archiveSha256") == sha256_file(archive)
    )

from __future__ import annotations

from pathlib import Path
import shutil

from toolbox.acquisition import (
    AcquiredArtifact,
    Runner,
    canonical_digest,
    sha256_file,
)
from toolbox.model import RepositorySpec, to_primitive


class SourceProjectionError(RuntimeError):
    pass


def patch_identity(repository: RepositorySpec, toolbox_root: Path) -> tuple[dict[str, str], ...]:
    records: list[dict[str, str]] = []
    for patch in repository.patches:
        path = toolbox_root / patch.path
        if not path.is_file():
            raise SourceProjectionError(f"source patch does not exist: {path}")
        actual = sha256_file(path)
        if actual != patch.sha256:
            raise SourceProjectionError(
                f"source patch SHA-256 mismatch for {patch.path}: "
                f"expected {patch.sha256}, got {actual}"
            )
        records.append({"path": patch.path, "sha256": actual})
    return tuple(records)


def prepare_repository_source(
    repository: RepositorySpec,
    artifact: AcquiredArtifact,
    *,
    toolbox_root: Path,
    destination: Path,
    runner: Runner,
) -> AcquiredArtifact:
    if artifact.path is None:
        raise SourceProjectionError("repository source acquisition has no checkout")
    if not repository.patches:
        return artifact

    patches = patch_identity(repository, toolbox_root)
    shutil.rmtree(destination, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    runner.run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-hardlinks",
            str(artifact.path.resolve()),
            str(destination.resolve()),
        ]
    )
    revision = repository.source.revision if repository.source is not None else None
    if revision:
        runner.run(
            ["git", "checkout", "--quiet", "--detach", revision], cwd=destination
        )
    for record in patches:
        patch_path = (toolbox_root / record["path"]).resolve()
        runner.run(["git", "apply", "--check", str(patch_path)], cwd=destination)
        runner.run(["git", "apply", str(patch_path)], cwd=destination)
    runner.run(["git", "diff", "--check"], cwd=destination)

    projection_key = canonical_digest(
        {
            "schema": "toolbox.repository-source-projection.v1",
            "baseIdentity": artifact.identity,
            "patches": patches,
        }
    )
    return AcquiredArtifact(
        name=artifact.name,
        path=destination,
        identity=f"{artifact.identity}#source-projection:{projection_key}",
        cache_key=projection_key,
    )

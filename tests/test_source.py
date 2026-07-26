from pathlib import Path
import hashlib
import subprocess

import pytest

from toolbox.acquisition import AcquiredArtifact, SubprocessRunner
from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    PythonProjectSpec,
    RepositorySpec,
    SourcePatchSpec,
)
from toolbox.source import SourceProjectionError, prepare_repository_source

TARGET = "x86_64-unknown-linux-gnu"


def _repository(tmp_path: Path, patch_digest: str) -> RepositorySpec:
    return RepositorySpec(
        name="sample",
        root=Path("repos/sample"),
        target=TARGET,
        python_group="sample",
        tools=("tool",),
        source=AcquisitionSpec(
            kind=AcquisitionKind.GIT_CHECKOUT,
            repository="https://example.invalid/sample.git",
            revision="a" * 40,
        ),
        python_project=PythonProjectSpec(),
        patches=(SourcePatchSpec("patches/change.patch", patch_digest),),
    )


def test_repository_source_patch_is_sha_bound_and_does_not_mutate_pool(
    tmp_path: Path,
) -> None:
    source = tmp_path / "pooled"
    source.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True
    )
    (source / "file.txt").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=source, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "--no-gpg-sign", "-m", "fixture"],
        cwd=source,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()

    patch = tmp_path / "patches/change.patch"
    patch.parent.mkdir()
    patch.write_text(
        "diff --git a/file.txt b/file.txt\n"
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -1 +1 @@\n"
        "-before\n"
        "+after\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    repository = _repository(tmp_path, digest)
    object.__setattr__(
        repository,
        "source",
        AcquisitionSpec(
            kind=AcquisitionKind.GIT_CHECKOUT,
            repository="https://example.invalid/sample.git",
            revision=revision,
        ),
    )

    derived = prepare_repository_source(
        repository,
        AcquiredArtifact("repository-sample", source, f"source@{revision}", "base"),
        toolbox_root=tmp_path,
        destination=tmp_path / "derived",
        runner=SubprocessRunner(),
    )

    assert (source / "file.txt").read_text() == "before\n"
    assert (derived.path / "file.txt").read_text() == "after\n"  # type: ignore[union-attr]
    assert "source-projection" in derived.identity


def test_repository_source_patch_rejects_digest_mismatch(tmp_path: Path) -> None:
    patch = tmp_path / "patches/change.patch"
    patch.parent.mkdir()
    patch.write_text("fixture", encoding="utf-8")
    repository = _repository(tmp_path, "0" * 64)
    with pytest.raises(SourceProjectionError, match="SHA-256 mismatch"):
        prepare_repository_source(
            repository,
            AcquiredArtifact("repository-sample", tmp_path, "source", "base"),
            toolbox_root=tmp_path,
            destination=tmp_path / "derived",
            runner=SubprocessRunner(),
        )

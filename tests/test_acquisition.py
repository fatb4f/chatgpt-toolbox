from __future__ import annotations

from pathlib import Path
import hashlib

from toolbox.acquisition import (
    SubprocessRunner,
    acquire_tool,
    acquisition_cache_key,
)
from toolbox.model import AcquisitionKind, AcquisitionSpec, ToolSpec

TARGET = "x86_64-unknown-linux-gnu"


def test_acquisition_key_is_independent_of_tool_name() -> None:
    acquisition = AcquisitionSpec(
        kind=AcquisitionKind.HTTP_ARCHIVE,
        url="https://example.invalid/tool.tar.gz",
        sha256="a" * 64,
    )
    assert acquisition_cache_key(acquisition) == acquisition_cache_key(acquisition)


def test_http_archive_reuses_verified_pool_entry(tmp_path: Path) -> None:
    payload = b"archive"
    acquisition = AcquisitionSpec(
        kind=AcquisitionKind.HTTP_ARCHIVE,
        url="https://example.invalid/tool.tar.gz",
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    key = acquisition_cache_key(acquisition)
    cached = tmp_path / "downloads" / key / "tool.tar.gz"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(payload)
    tool = ToolSpec("example", "1", TARGET, acquisition)

    artifact = acquire_tool(
        tool,
        downloads=tmp_path / "downloads",
        sources=tmp_path / "sources",
        toolbox_root=tmp_path,
        runner=SubprocessRunner(),
    )

    assert artifact.path == cached
    assert artifact.cache_key == key
    assert artifact.identity.endswith(acquisition.sha256 or "")


def test_local_source_identity_hashes_tree_content(tmp_path: Path) -> None:
    source = tmp_path / "program"
    source.mkdir()
    (source / "main.go").write_text("package main\n", encoding="utf-8")
    tool = ToolSpec(
        name="program",
        version="repository",
        target=TARGET,
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.LOCAL_SOURCE, path="program"
        ),
    )
    first = acquire_tool(
        tool,
        downloads=tmp_path / "downloads",
        sources=tmp_path / "sources",
        toolbox_root=tmp_path,
        runner=SubprocessRunner(),
    )
    (source / "main.go").write_text(
        "package main\n// changed\n", encoding="utf-8"
    )
    second = acquire_tool(
        tool,
        downloads=tmp_path / "downloads",
        sources=tmp_path / "sources",
        toolbox_root=tmp_path,
        runner=SubprocessRunner(),
    )
    assert first.identity != second.identity


def test_pooled_git_checkout_rejects_untracked_contamination(tmp_path: Path) -> None:
    import subprocess

    from toolbox.acquisition import _valid_git_checkout

    repository = tmp_path / "checkout"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repository,
        check=True,
    )
    (repository / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "--no-gpg-sign", "-m", "fixture"],
        cwd=repository,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert _valid_git_checkout(repository, revision, SubprocessRunner())

    (repository / "untracked.txt").write_text("contamination\n", encoding="utf-8")
    assert not _valid_git_checkout(repository, revision, SubprocessRunner())

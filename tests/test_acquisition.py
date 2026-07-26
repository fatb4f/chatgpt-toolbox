from __future__ import annotations

from pathlib import Path
import hashlib
import json
import subprocess

import pytest

from toolbox.acquisition import AcquisitionError, acquire_tool
from toolbox.model import AcquisitionKind, AcquisitionSpec, ToolSpec

TARGET = "x86_64-unknown-linux-gnu"


class FakeRunner:
    def __init__(self, payload: bytes, assets: list[str]) -> None:
        self.payload = payload
        self.assets = assets
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd=None, env=None, capture_output=False):
        command = tuple(argv)
        self.calls.append(command)
        if command[:3] == ("gh", "release", "view"):
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps({"assets": [{"name": name} for name in self.assets]}),
                "",
            )
        if command[:3] == ("gh", "release", "download"):
            output = Path(command[command.index("--dir") + 1])
            asset = command[command.index("--pattern") + 1]
            (output / asset).write_bytes(self.payload)
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)


class GitRunner:
    def __init__(self, revision: str) -> None:
        self.revision = revision
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd=None, env=None, capture_output=False):
        command = tuple(argv)
        self.calls.append(command)
        if command == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(command, 0, self.revision + "\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")


def release_tool(payload: bytes) -> ToolSpec:
    return ToolSpec(
        name="example",
        version="1.0.0",
        target=TARGET,
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.GITHUB_RELEASE,
            repository="owner/repository",
            release="v1.0.0",
            asset="example.tar.gz",
            sha256=hashlib.sha256(payload).hexdigest(),
        ),
    )


def test_github_release_resolves_metadata_before_download(tmp_path: Path) -> None:
    runner = FakeRunner(b"archive", ["example.tar.gz"])
    artifact = acquire_tool(
        release_tool(b"archive"),
        downloads=tmp_path / "downloads",
        sources=tmp_path / "sources",
        toolbox_root=tmp_path,
        runner=runner,
    )
    assert artifact.path and artifact.path.read_bytes() == b"archive"
    assert runner.calls[0][:3] == ("gh", "release", "view")
    assert runner.calls[1][:3] == ("gh", "release", "download")


def test_github_release_rejects_missing_exact_asset(tmp_path: Path) -> None:
    runner = FakeRunner(b"archive", ["other.tar.gz"])
    with pytest.raises(AcquisitionError, match="does not contain exactly one"):
        acquire_tool(
            release_tool(b"archive"),
            downloads=tmp_path / "downloads",
            sources=tmp_path / "sources",
            toolbox_root=tmp_path,
            runner=runner,
        )
    assert len(runner.calls) == 1


def test_equal_git_acquisitions_share_one_checkout(tmp_path: Path) -> None:
    revision = "a" * 40
    acquisition = AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository="https://example.invalid/tools.git",
        revision=revision,
    )
    first_tool = ToolSpec(
        name="first", version="1", target=TARGET, acquisition=acquisition
    )
    second_tool = ToolSpec(
        name="second", version="1", target=TARGET, acquisition=acquisition
    )
    runner = GitRunner(revision)

    first = acquire_tool(
        first_tool,
        downloads=tmp_path / "downloads",
        sources=tmp_path / "sources",
        toolbox_root=tmp_path,
        runner=runner,
    )
    second = acquire_tool(
        second_tool,
        downloads=tmp_path / "downloads",
        sources=tmp_path / "sources",
        toolbox_root=tmp_path,
        runner=runner,
    )

    assert first.path == second.path
    assert first.cache_key == second.cache_key
    assert sum(call[:2] == ("git", "fetch") for call in runner.calls) == 1


def test_local_source_identity_hashes_tree_content(tmp_path: Path) -> None:
    from toolbox.acquisition import SubprocessRunner

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

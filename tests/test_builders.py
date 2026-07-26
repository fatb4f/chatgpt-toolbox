from __future__ import annotations

from pathlib import Path
import subprocess

from toolbox.acquisition import AcquiredArtifact
from toolbox.builders import build_and_stage_tool, staged_go_environment
from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    ToolSpec,
)

TARGET = "x86_64-unknown-linux-gnu"


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Path | None, dict[str, str] | None]] = []

    def run(self, argv, *, cwd=None, env=None, capture_output=False):
        command = tuple(argv)
        self.calls.append((command, cwd, dict(env) if env is not None else None))
        if command[:2] == ("go", "build"):
            output = Path(command[command.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("binary", encoding="utf-8")
            output.chmod(0o755)
        return subprocess.CompletedProcess(command, 0, "", "")


def test_staged_go_environment_forces_pooled_compiler_and_external_cache(
    tmp_path: Path,
) -> None:
    toolchain = tmp_path / "toolchain"
    output = tmp_path / "projection"
    cache = tmp_path / "workspace" / "go-cache"
    environment = staged_go_environment(toolchain, output, cache)
    assert environment["GOROOT"] == str(toolchain / "libexec" / "go")
    assert environment["GOTOOLCHAIN"] == "local"
    assert environment["GOBIN"] == str(output / "bin")
    assert environment["PATH"].split(":")[:3] == [
        str(toolchain / "libexec" / "go" / "bin"),
        str(toolchain / "bin"),
        str(output / "bin"),
    ]
    assert environment["GOPATH"] == str(cache / "gopath")
    assert environment["GOMODCACHE"] == str(cache / "gopath" / "pkg" / "mod")
    assert environment["GOCACHE"] == str(cache / "build")
    assert not Path(environment["GOCACHE"]).is_relative_to(output)


def test_go_source_build_matches_cuestrap_flags(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "projection"
    runner = RecordingRunner()
    tool = ToolSpec(
        name="cue",
        version="0.18.0",
        target=TARGET,
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.GIT_CHECKOUT,
            repository="https://example.invalid/cue.git",
            revision="a" * 40,
        ),
        build=BuildSpec(
            kind=BuildKind.GO_COMMAND,
            requires=("go",),
            package="./cmd/cue",
            output="bin/cue",
            build_vcs=True,
            ldflags=("-s", "-w"),
        ),
    )
    build_and_stage_tool(
        tool,
        AcquiredArtifact("cue", source, "source", "source-key"),
        prefix=output,
        build_root=tmp_path / "build",
        toolchain_prefix=tmp_path / "toolchain",
        runner=runner,
    )
    command, cwd, _ = runner.calls[0]
    assert command == (
        "go",
        "build",
        "-trimpath",
        "-buildvcs=true",
        "-ldflags=-s -w",
        "-o",
        str((output / "bin/cue").resolve()),
        "./cmd/cue",
    )
    assert cwd == source

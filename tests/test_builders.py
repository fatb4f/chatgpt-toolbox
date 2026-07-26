from pathlib import Path
import hashlib
import subprocess
import tarfile

from toolbox.acquisition import AcquiredArtifact
from toolbox.builders import build_and_stage_tool, resolve_build, staged_go_environment
from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    LinkerVariableSpec,
    SourceDigestSpec,
    ToolSpec,
)

TARGET = "x86_64-unknown-linux-gnu"


class RecordingRunner:
    def __init__(self) -> None:
        self.calls = []

    def run(self, argv, *, cwd=None, env=None, capture_output=False):
        command = tuple(argv)
        self.calls.append((command, cwd, dict(env or {})))
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
    assert environment["GOROOT"] == str((toolchain / "libexec/go").resolve())
    assert environment["GOTOOLCHAIN"] == "local"
    assert environment["GOBIN"] == str((output / "bin").resolve())
    assert environment["PATH"].split(":")[:3] == [
        str((toolchain / "libexec/go/bin").resolve()),
        str((toolchain / "bin").resolve()),
        str((output / "bin").resolve()),
    ]
    assert environment["GOCACHE"] == str((cache / "build").resolve())


def test_make_build_uses_declared_install_prefix_variable(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(source, arcname="source")
    tool = ToolSpec(
        name="example",
        version="1",
        target=TARGET,
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.LOCAL_SOURCE,
            path="source",
        ),
        build=BuildSpec(
            kind=BuildKind.MAKE_COMMAND,
            make_target="all",
            install_target="install",
            install_prefix_variable="PREFIX",
        ),
    )
    artifact = AcquiredArtifact("example", archive, "source", "source-key")
    runner = RecordingRunner()
    build_and_stage_tool(
        tool,
        artifact,
        prefix=tmp_path / "projection",
        build_root=tmp_path / "build",
        runner=runner,
    )
    assert runner.calls[1][0][-1] == f"PREFIX={(tmp_path / 'projection').resolve()}"


def test_source_digest_and_linker_projection_match_hydrator_contract(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "go.mod").write_text("module example.invalid/program\n", encoding="utf-8")
    (source / "main.go").write_text("package main\n", encoding="utf-8")
    (source / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    symbol = "example.invalid/program/internal.BuildDigest"
    tool = ToolSpec(
        name="program",
        version="1",
        target=TARGET,
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.GIT_CHECKOUT,
            repository="https://example.invalid/program.git",
            revision="a" * 40,
        ),
        build=BuildSpec(
            kind=BuildKind.GO_COMMAND,
            package=".",
            output="bin/program",
            build_vcs=True,
            ldflags=("-s", "-w"),
            source_digest=SourceDigestSpec(),
            linker_variables=(LinkerVariableSpec(symbol),),
        ),
    )
    artifact = AcquiredArtifact("program", source, "source", "source-key")
    expected = hashlib.sha256()
    for name in ("go.mod", "main.go"):
        expected.update(name.encode())
        expected.update(b"\0")
        expected.update((source / name).read_bytes())
        expected.update(b"\0")
    digest = "sha256:" + expected.hexdigest()
    resolved = resolve_build(tool, artifact)
    assert resolved.source_digest == digest
    assert resolved.ldflags == ("-s", "-w", "-X", f"{symbol}={digest}")

    runner = RecordingRunner()
    build_and_stage_tool(
        tool,
        artifact,
        prefix=tmp_path / "projection",
        build_root=tmp_path / "build",
        toolchain_prefix=tmp_path / "toolchain",
        runner=runner,
        resolved_build=resolved,
    )
    command = runner.calls[0][0]
    assert command[:4] == ("go", "build", "-trimpath", "-buildvcs=true")
    assert f"-ldflags=-s -w -X {symbol}={digest}" in command

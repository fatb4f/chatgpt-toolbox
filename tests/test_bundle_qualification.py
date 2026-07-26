from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import subprocess

import pytest

from toolbox.acquisition import AcquiredArtifact, SubprocessRunner
from toolbox.builders import build_and_stage_tool, go_source_digest
from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    DescriptorError,
    ToolSpec,
)
from toolbox.qualification import qualify_context_git_hydrator
from toolbox.staging import write_activation

TARGET = "x86_64-unknown-linux-gnu"
DIGEST_SYMBOL = "example.invalid/module/internal/build.SourceDigest"


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd=None, env=None, capture_output=False):
        command = tuple(argv)
        self.calls.append(command)
        if command[:2] == ("go", "build"):
            output = Path(command[command.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("binary", encoding="utf-8")
            output.chmod(0o755)
        return subprocess.CompletedProcess(command, 0, "", "")


def _manual_source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (
            path
            for path in source.rglob("*")
            if path.is_file()
            and (path.suffix == ".go" or path.name in {"go.mod", "go.sum"})
        ),
        key=lambda path: path.relative_to(source).as_posix(),
    ):
        digest.update(path.relative_to(source).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def test_source_digest_matches_hydrator_release_algorithm(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "cmd").mkdir(parents=True)
    (source / "go.mod").write_text("module example.invalid/module\n", encoding="utf-8")
    (source / "go.sum").write_text("dependency checksum\n", encoding="utf-8")
    (source / "cmd/main.go").write_text("package main\n", encoding="utf-8")
    (source / "ignored.md").write_text("ignored\n", encoding="utf-8")

    assert go_source_digest(source) == _manual_source_digest(source)


def test_source_digest_is_injected_into_go_linker_flags(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "go.mod").write_text("module example.invalid/module\n", encoding="utf-8")
    (source / "main.go").write_text("package main\n", encoding="utf-8")
    output = tmp_path / "projection"
    runner = RecordingRunner()
    tool = ToolSpec(
        name="program",
        version="1.0.0",
        target=TARGET,
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.GIT_CHECKOUT,
            repository="https://example.invalid/module.git",
            revision="a" * 40,
        ),
        build=BuildSpec(
            kind=BuildKind.GO_COMMAND,
            package=".",
            output="bin/program",
            build_vcs=True,
            ldflags=("-s", "-w"),
            source_digest_symbol=DIGEST_SYMBOL,
        ),
    )

    build_and_stage_tool(
        tool,
        AcquiredArtifact("program", source, "source", "source-key"),
        prefix=output,
        build_root=tmp_path / "build",
        toolchain_prefix=tmp_path / "toolchain",
        runner=runner,
    )

    expected = go_source_digest(source)
    command = runner.calls[0]
    assert f"-ldflags=-s -w -X {DIGEST_SYMBOL}={expected}" in command


def test_source_digest_requires_source_acquisition() -> None:
    with pytest.raises(DescriptorError, match="requires a Git checkout or local source"):
        ToolSpec(
            name="program",
            version="1.0.0",
            target=TARGET,
            acquisition=AcquisitionSpec(
                kind=AcquisitionKind.GO_MODULE,
                module="example.invalid/module",
                version="v1.0.0",
            ),
            build=BuildSpec(
                kind=BuildKind.GO_COMMAND,
                package="example.invalid/module/cmd/program",
                output="bin/program",
                source_digest_symbol=DIGEST_SYMBOL,
            ),
        )


@pytest.mark.parametrize("shell", ["bash", "dash", "zsh"])
def test_activation_resolves_its_sourced_path(tmp_path: Path, shell: str) -> None:
    executable = shutil.which(shell)
    if executable is None:
        pytest.skip(f"{shell} is unavailable")
    prefix = tmp_path / "relocated bundle"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "libexec/go").mkdir(parents=True)
    activation = write_activation(prefix)
    completed = subprocess.run(
        [
            executable,
            "-c",
            '. "$1"; printf "%s\\n%s\\n%s\\n" "$TOOLBOX_ROOT" "${PATH%%:*}" "$GOROOT"',
            shell,
            str(activation),
        ],
        check=True,
        text=True,
        capture_output=True,
        cwd=tmp_path,
    )
    assert completed.stdout.splitlines() == [
        str(prefix.resolve()),
        str((prefix / "bin").resolve()),
        str((prefix / "libexec/go").resolve()),
    ]


def test_committed_hydrator_qualification_executes_fixture(tmp_path: Path) -> None:
    expected_digest = "sha256:" + "1" * 64
    prefix = tmp_path / "prefix"
    binary = prefix / "bin/context-git-hydrator"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import json, subprocess, sys\n"
        "request = json.load(open(sys.argv[sys.argv.index('--request') + 1], encoding='utf-8'))\n"
        "revision = subprocess.run(['git', '-C', request['path'], 'rev-parse', request['revision']], check=True, text=True, capture_output=True).stdout.strip()\n"
        f"digest = {expected_digest!r}\n"
        "json.dump({'schema':'kernel.git-committed-snapshot-observation.v0','repositoryID':request['repositoryID'],'requestedRevision':revision,'resolvedRevision':{'format':'sha1','hex':revision},'rootTree':{'format':'sha1','hex':'0'*40},'occurrences':[{'path':'fixture.txt','mode':'100644','kind':'blob','objectID':{'format':'sha1','hex':'1'*40},'size':10}],'hydrator':{'identity':'context-git-hydrator','digest':digest}}, sys.stdout, separators=(',', ':'))\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)

    qualify_context_git_hydrator(
        prefix=prefix,
        work_root=tmp_path / "qualification",
        runner=SubprocessRunner(),
        expected_digest=expected_digest,
    )

from pathlib import Path

import pytest

from toolbox.operations import OperationError, inspect_repository


def test_inspect_projects_fully_pinned_dotfiles_plan() -> None:
    plan = inspect_repository("dotfiles")
    assert plan.admissible
    assert plan.lock_defects == ()
    assert plan.output == (
        "repos/dotfiles/dist/dotfiles-x86_64-unknown-linux-gnu.tar.gz"
    )
    nodes = {node.name: node for node in plan.nodes}
    assert nodes["cue"].acquisition.revision == (
        "806821e40fae070318600a264d311517e596353b"
    )
    assert nodes["cue"].build.build_vcs
    assert nodes["cue"].build.ldflags == ("-s", "-w")
    assert (
        nodes["gopls"].acquisition.repository
        == nodes["goimports"].acquisition.repository
    )
    assert (
        nodes["gopls"].acquisition.revision
        == nodes["goimports"].acquisition.revision
    )


def test_local_go_program_must_match_declared_module_pin(tmp_path: Path) -> None:
    from types import MappingProxyType

    from toolbox.acquisition import AcquiredArtifact
    from toolbox.model import (
        AcquisitionKind,
        AcquisitionSpec,
        BuildKind,
        BuildSpec,
        ToolRole,
        ToolSpec,
    )
    from toolbox.operations import _verify_go_module_edges

    module = ToolSpec(
        name="dependency",
        version="1.2.3",
        target="x86_64-unknown-linux-gnu",
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.GO_MODULE,
            module="example.invalid/dependency",
            version="v1.2.3",
        ),
        roles=frozenset({ToolRole.MODULE}),
    )
    program = ToolSpec(
        name="program",
        version="repository",
        target="x86_64-unknown-linux-gnu",
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.LOCAL_SOURCE, path="program"
        ),
        build=BuildSpec(
            kind=BuildKind.GO_COMMAND,
            requires=("dependency",),
            package=".",
            output="bin/program",
        ),
        roles=frozenset({ToolRole.PROGRAM}),
    )
    source = tmp_path / "program"
    source.mkdir()
    (source / "go.mod").write_text(
        "module example.invalid/program\n\n"
        "require example.invalid/dependency v1.2.2\n",
        encoding="utf-8",
    )
    artifact = AcquiredArtifact("program", source, "local:program")
    selected = MappingProxyType({"dependency": module, "program": program})

    with pytest.raises(OperationError, match="does not require declared module"):
        _verify_go_module_edges(program, artifact, selected)

    (source / "go.mod").write_text(
        "module example.invalid/program\n\n"
        "require example.invalid/dependency v1.2.3\n",
        encoding="utf-8",
    )
    _verify_go_module_edges(program, artifact, selected)


def test_clean_repository_preserves_shared_cache(tmp_path: Path) -> None:
    from toolbox.operations import clean_repository

    work = tmp_path / ".toolbox-work/dotfiles-x86_64-unknown-linux-gnu"
    cache = tmp_path / ".toolbox-cache/projections/example"
    work.mkdir(parents=True)
    cache.mkdir(parents=True)

    clean_repository("dotfiles", toolbox_root=tmp_path)

    assert not work.exists()
    assert cache.exists()


def test_clean_cache_is_explicit(tmp_path: Path) -> None:
    from toolbox.operations import clean_cache

    cache = tmp_path / ".toolbox-cache/projections/example"
    cache.mkdir(parents=True)
    clean_cache(toolbox_root=tmp_path)
    assert not (tmp_path / ".toolbox-cache").exists()


def test_runtime_probes_use_composed_prefix(tmp_path: Path) -> None:
    import subprocess

    from toolbox.model import AcquisitionKind, AcquisitionSpec, ToolSpec
    from toolbox.operations import _verify_tool_probes

    class Runner:
        def __init__(self) -> None:
            self.calls = []

        def run(self, argv, *, cwd=None, env=None, capture_output=False):
            self.calls.append((tuple(argv), dict(env or {}), capture_output))
            return subprocess.CompletedProcess(tuple(argv), 0, "", "")

    tool = ToolSpec(
        name="example",
        version="1",
        target="x86_64-unknown-linux-gnu",
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.GO_MODULE,
            module="example.invalid/tool",
            version="v1.0.0",
        ),
        probes=(("example", "version"),),
    )
    runner = Runner()
    _verify_tool_probes((tool,), tmp_path / "prefix", runner)
    command, environment, capture = runner.calls[0]
    assert command == ("example", "version")
    assert environment["PATH"].split(":")[0] == str(
        (tmp_path / "prefix/bin").resolve()
    )
    assert environment["GOROOT"] == str(
        (tmp_path / "prefix/libexec/go").resolve()
    )
    assert capture


def test_warm_and_cold_repository_builds_are_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path
    from types import MappingProxyType
    import hashlib
    import io
    import tarfile

    from toolbox.acquisition import acquisition_cache_key, sha256_file
    from toolbox.model import (
        AcquisitionKind,
        AcquisitionSpec,
        InstallEntry,
        RepositorySpec,
        ToolSpec,
    )
    import toolbox.operations as operations

    payload = b"#!/bin/sh\necho ok\n"
    archive = tmp_path / "fixture.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo("tool")
        info.mode = 0o755
        info.size = len(payload)
        stream.addfile(info, io.BytesIO(payload))

    acquisition = AcquisitionSpec(
        kind=AcquisitionKind.HTTP_ARCHIVE,
        url="https://example.invalid/tool.tar.gz",
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    tool = ToolSpec(
        name="example",
        version="1.0.0",
        target="x86_64-unknown-linux-gnu",
        acquisition=acquisition,
        install=(InstallEntry("tool", "bin/tool"),),
    )
    repository = RepositorySpec(
        name="sample",
        root=Path("repos/sample"),
        target=tool.target,
        python_group="sample",
        tools=(tool.name,),
    )
    selected = MappingProxyType({tool.name: tool})
    monkeypatch.setattr(operations, "get_repository", lambda name: repository)
    monkeypatch.setattr(
        operations,
        "topological_tools",
        lambda descriptor, target=None: (tool,),
    )
    monkeypatch.setattr(
        operations,
        "selected_tools",
        lambda descriptor, target=None: selected,
    )

    pool = tmp_path / "pool"
    cached = (
        pool
        / "downloads"
        / acquisition_cache_key(acquisition)
        / "tool.tar.gz"
    )
    cached.parent.mkdir(parents=True)
    cached.write_bytes(archive.read_bytes())

    first = operations.build_repository(
        "sample", toolbox_root=tmp_path, pool_root=pool
    )
    first_digest = sha256_file(Path(first.archive))
    first_lock = Path(first.lockfile).read_text(encoding="utf-8")

    second = operations.build_repository(
        "sample", toolbox_root=tmp_path, pool_root=pool
    )
    second_digest = sha256_file(Path(second.archive))
    second_lock = Path(second.lockfile).read_text(encoding="utf-8")

    assert first_digest == second_digest
    assert first_lock == second_lock
    assert "projectionReused" not in second_lock
    assert len(list((pool / "projections" / tool.target).iterdir())) == 1

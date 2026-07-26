from pathlib import Path

import pytest

from toolbox.operations import OperationError, build_repository, inspect_repository


def test_inspect_projects_lock_defects_without_executing() -> None:
    plan = inspect_repository("dotfiles")
    assert not plan.admissible
    assert "python: missing sha256" not in plan.lock_defects
    assert "goimports: git revision is not a full 40-character commit" not in plan.lock_defects
    assert "cue: missing sha256" in plan.lock_defects
    assert "go-git: missing Go module version" in plan.lock_defects
    assert plan.output == "repos/dotfiles/dist/dotfiles-x86_64-unknown-linux-gnu.tar.gz"


def test_build_refuses_before_transport_when_lock_is_incomplete(tmp_path: Path) -> None:
    with pytest.raises(OperationError, match="unresolved lock authority"):
        build_repository("dotfiles", toolbox_root=tmp_path)
    assert not (tmp_path / ".toolbox-work").exists()


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
        acquisition=AcquisitionSpec(kind=AcquisitionKind.LOCAL_SOURCE, path="program"),
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
        "module example.invalid/program\n\nrequire example.invalid/dependency v1.2.2\n",
        encoding="utf-8",
    )
    artifact = AcquiredArtifact("program", source, "local:program")
    selected = MappingProxyType({"dependency": module, "program": program})

    with pytest.raises(OperationError, match="does not require declared module"):
        _verify_go_module_edges(program, artifact, selected)

    (source / "go.mod").write_text(
        "module example.invalid/program\n\nrequire example.invalid/dependency v1.2.3\n",
        encoding="utf-8",
    )
    _verify_go_module_edges(program, artifact, selected)

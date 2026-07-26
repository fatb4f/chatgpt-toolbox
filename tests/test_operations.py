from pathlib import Path

import pytest

from toolbox.operations import OperationError, inspect_repository


def test_inspect_projects_fully_pinned_layered_release() -> None:
    plan = inspect_repository("dotfiles")
    assert plan.admissible
    assert plan.lock_defects == ()
    assert plan.output == (
        "repos/dotfiles/dist/release/dotfiles-tools-linux-amd64.tar.zst"
    )
    assert [component.name for component in plan.components] == [
        "native-base",
        "go-programs",
        "python-projects",
        "repository-source",
    ]
    nodes = {node.name: node for node in plan.nodes}
    assert "context-git-hydrator" not in nodes
    assert nodes["cue"].acquisition.revision == (
        "806821e40fae070318600a264d311517e596353b"
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
    artifact = AcquiredArtifact("program", source, "local:program", "key")
    selected = MappingProxyType({"dependency": module, "program": program})

    with pytest.raises(OperationError, match="does not require declared module"):
        _verify_go_module_edges(program, artifact, selected)

    (source / "go.mod").write_text(
        "module example.invalid/program\n\n"
        "require example.invalid/dependency v1.2.3\n",
        encoding="utf-8",
    )
    _verify_go_module_edges(program, artifact, selected)


def test_clean_repository_preserves_shared_pool(tmp_path: Path) -> None:
    from toolbox.operations import clean_repository

    work = tmp_path / ".toolbox-work/dotfiles-x86_64-unknown-linux-gnu"
    cache = tmp_path / ".toolbox-cache/components/example"
    work.mkdir(parents=True)
    cache.mkdir(parents=True)
    clean_repository("dotfiles", toolbox_root=tmp_path)
    assert not work.exists()
    assert cache.exists()


def test_clean_cache_is_explicit(tmp_path: Path) -> None:
    from toolbox.operations import clean_cache

    cache = tmp_path / ".toolbox-cache/components/example"
    cache.mkdir(parents=True)
    clean_cache(toolbox_root=tmp_path)
    assert not (tmp_path / ".toolbox-cache").exists()

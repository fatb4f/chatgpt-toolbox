from pathlib import Path

import pytest

from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    DescriptorError,
    InstallEntry,
    LinkerVariableSpec,
    PythonProjectSpec,
    RepositorySpec,
    SourceDigestSpec,
    ToolSpec,
)

TARGET = "x86_64-unknown-linux-gnu"
SOURCE = AcquisitionSpec(
    kind=AcquisitionKind.GIT_CHECKOUT,
    repository="https://example.invalid/repo.git",
    revision="a" * 40,
)


def test_digest_must_be_sha256() -> None:
    with pytest.raises(DescriptorError, match="64 lowercase"):
        AcquisitionSpec(
            kind=AcquisitionKind.HTTP_ARCHIVE,
            url="https://example.invalid/tool.tar.gz",
            sha256="abc",
        )


def test_git_checkout_requires_full_commit_for_lock_admission() -> None:
    acquisition = AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository="https://example.invalid/tools.git",
        revision="014f87f",
    )
    assert acquisition.lock_defects == (
        "git revision is not a full 40-character commit",
    )


def test_no_build_spec_rejects_build_fields() -> None:
    with pytest.raises(DescriptorError, match="no-build"):
        BuildSpec(kind=BuildKind.NONE, output="bin/tool")


def test_linker_variable_requires_source_digest() -> None:
    with pytest.raises(DescriptorError, match="source digest"):
        BuildSpec(
            kind=BuildKind.GO_COMMAND,
            package=".",
            output="bin/tool",
            linker_variables=(LinkerVariableSpec("example.invalid/x.Value"),),
        )


def test_paths_cannot_escape_bundle() -> None:
    with pytest.raises(DescriptorError, match="normalized relative"):
        InstallEntry("tool", "../bin/tool")


def test_go_module_cannot_directly_install_archive_entries() -> None:
    with pytest.raises(DescriptorError, match="do not directly install"):
        ToolSpec(
            name="example",
            version="1.0.0",
            target=TARGET,
            acquisition=AcquisitionSpec(
                kind=AcquisitionKind.GO_MODULE,
                module="example.invalid/tool",
                version="v1.0.0",
            ),
            install=(InstallEntry("tool", "bin/tool"),),
        )


def test_repository_requires_source_and_python_authority() -> None:
    with pytest.raises(DescriptorError, match="source authority"):
        RepositorySpec(
            name="repo",
            root=Path("repos/repo"),
            target=TARGET,
            python_group="repo-test",
            tools=("example",),
            python_project=PythonProjectSpec(),
        )


def test_repository_root_is_relative() -> None:
    with pytest.raises(DescriptorError, match="root must be relative"):
        RepositorySpec(
            name="repo",
            root=Path("/tmp/repo"),
            target=TARGET,
            python_group="repo-test",
            tools=("example",),
            source=SOURCE,
            python_project=PythonProjectSpec(),
        )

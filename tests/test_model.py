from pathlib import Path

import pytest

from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    DescriptorError,
    InstallEntry,
    RepositorySpec,
    ToolSpec,
)

TARGET = "x86_64-unknown-linux-gnu"


def test_github_release_requires_exact_repository_shape() -> None:
    with pytest.raises(DescriptorError, match="owner/repository"):
        AcquisitionSpec(
            kind=AcquisitionKind.GITHUB_RELEASE,
            repository="astral-sh",
            release="1",
            asset="tool.tar.gz",
        )


def test_digest_must_be_sha256() -> None:
    with pytest.raises(DescriptorError, match="64 lowercase"):
        AcquisitionSpec(
            kind=AcquisitionKind.HTTP_ARCHIVE,
            url="https://example.invalid/tool.tar.gz",
            sha256="abc",
        )


def test_archive_without_digest_is_inspectable_but_not_locked() -> None:
    acquisition = AcquisitionSpec(
        kind=AcquisitionKind.HTTP_ARCHIVE,
        url="https://example.invalid/tool.tar.gz",
    )
    assert acquisition.lock_defects == ("missing sha256",)


def test_git_checkout_requires_full_commit_for_lock_admission() -> None:
    acquisition = AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository="https://example.invalid/tools.git",
        revision="014f87f",
    )
    assert acquisition.lock_defects == ("git revision is not a full 40-character commit",)


def test_go_module_requires_immutable_version_for_lock_admission() -> None:
    acquisition = AcquisitionSpec(
        kind=AcquisitionKind.GO_MODULE,
        module="example.invalid/module",
    )
    assert acquisition.lock_defects == ("missing Go module version",)


def test_no_build_spec_rejects_build_fields() -> None:
    with pytest.raises(DescriptorError, match="no-build"):
        BuildSpec(kind=BuildKind.NONE, output="bin/tool")


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


def test_repository_root_is_relative() -> None:
    with pytest.raises(DescriptorError, match="root must be relative"):
        RepositorySpec(
            name="repo",
            root=Path("/tmp/repo"),
            target=TARGET,
            python_group="repo-test",
            tools=("example",),
        )

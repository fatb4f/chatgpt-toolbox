from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

from toolbox.acquisition import sha256_file
from toolbox.packaging import (
    archive_record,
    canonical_json_bytes,
    create_deterministic_tar_zst,
    extract_tar_zst,
    write_bundle_support,
    write_json,
    write_outer_installer,
    write_release_checksums,
)

TARGET = {
    "os": "linux",
    "arch": "amd64",
    "abi": {"libc": "glibc", "minVersion": "2.17"},
    "triple": "x86_64-unknown-linux-gnu",
}


def test_tar_zst_is_byte_deterministic_and_epoch_normalized(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "bin").mkdir(parents=True)
    tool = root / "bin/tool"
    tool.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    tool.chmod(0o755)
    first = create_deterministic_tar_zst(root, tmp_path / "first.tar.zst")
    second = create_deterministic_tar_zst(root, tmp_path / "second.tar.zst")
    assert sha256_file(first) == sha256_file(second)

    extracted = extract_tar_zst(first, tmp_path / "extracted")
    assert (extracted / "bin/tool").read_text() == tool.read_text()
    listing = subprocess.run(
        ["tar", "--zstd", "-tvf", str(first)],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert "1970-01-01 00:00" in listing
    assert " 0/0 " in listing


def _python_wrapper(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        f"#!/bin/sh\nexec {sys.executable} \"$@\"\n", encoding="utf-8"
    )
    path.chmod(0o755)


def test_stable_prefix_installer_does_not_require_sourcing(tmp_path: Path) -> None:
    root = tmp_path / "aggregate"
    _python_wrapper(root / "bin/python3")
    tool = root / "bin/tool"
    tool.write_text("#!/bin/sh\necho installed\n", encoding="utf-8")
    tool.chmod(0o755)
    lock_digest = "a" * 64
    write_bundle_support(
        root,
        repository="sample",
        manifest={
            "schema": "toolbox.combined-repository-bundle-manifest.v1",
            "lockDigest": lock_digest,
            "repository": {"name": "sample", "sourceIdentity": "fixture"},
            "target": TARGET,
            "components": {},
        },
    )

    prefix = tmp_path / "installed"
    subprocess.run(
        ["bash", str(root / "install.sh"), "--prefix", str(prefix)],
        check=True,
        text=True,
        capture_output=True,
    )

    current = prefix / "current"
    assert current.is_symlink()
    assert os.readlink(current) == f"versions/{lock_digest}"
    completed = subprocess.run(
        [str(current / "bin/tool")], check=True, text=True, capture_output=True
    )
    assert completed.stdout.strip() == "installed"


def test_outer_release_installer_verifies_and_activates_aggregate(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    root = tmp_path / "aggregate"
    _python_wrapper(root / "bin/python3")
    (root / "bin/tool").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    (root / "bin/tool").chmod(0o755)
    lock = {"schema": "fixture", "value": 1}
    lock_path = write_json(release / "release-lock.json", lock, canonical=True)
    lock_digest = hashlib.sha256(canonical_json_bytes(lock)).hexdigest()
    embedded = {
        "schema": "toolbox.combined-repository-bundle-manifest.v1",
        "lockDigest": lock_digest,
        "repository": {"name": "sample", "sourceIdentity": "fixture"},
        "target": TARGET,
        "components": {},
    }
    write_bundle_support(root, repository="sample", manifest=embedded)
    archive = create_deterministic_tar_zst(
        root, release / "sample-tools-linux-amd64.tar.zst"
    )
    manifest = {
        "schema": "toolbox.repository-release-manifest.v1",
        "lockDigest": lock_digest,
        "repository": embedded["repository"],
        "target": TARGET,
        "components": {},
        "archive": archive_record(archive),
        "releaseLock": archive_record(lock_path),
    }
    write_json(release / "manifest.json", manifest)
    write_outer_installer(
        release / "install.sh",
        repository="sample",
        archive_name=archive.name,
    )
    write_release_checksums(
        release,
        (archive.name, "manifest.json", "release-lock.json", "install.sh"),
    )

    prefix = tmp_path / "prefix"
    subprocess.run(
        ["bash", str(release / "install.sh"), "--prefix", str(prefix)],
        check=True,
        text=True,
        capture_output=True,
    )
    assert (prefix / "current/bin/tool").is_file()


def test_release_verifier_rejects_component_sidecar_tampering(tmp_path: Path) -> None:
    from toolbox.packaging import PackagingError, verify_release_directory
    import pytest

    # Reuse the complete release constructed by the outer-installer test shape.
    release = tmp_path / "release"
    release.mkdir()
    root = tmp_path / "aggregate"
    _python_wrapper(root / "bin/python3")
    write_bundle_support(
        root,
        repository="sample",
        manifest={
            "schema": "toolbox.combined-repository-bundle-manifest.v1",
            "lockDigest": "0" * 64,
            "repository": {"name": "sample", "sourceIdentity": "fixture"},
            "target": TARGET,
            "components": {},
        },
    )
    lock = {"schema": "fixture"}
    lock_path = write_json(release / "release-lock.json", lock, canonical=True)
    lock_digest = hashlib.sha256(canonical_json_bytes(lock)).hexdigest()
    embedded = json.loads((root / "share/toolbox/manifest.json").read_text())
    embedded["lockDigest"] = lock_digest
    write_bundle_support(root, repository="sample", manifest=embedded)
    aggregate = create_deterministic_tar_zst(
        root, release / "sample-tools-linux-amd64.tar.zst"
    )
    component_root = tmp_path / "component"
    component_root.mkdir()
    (component_root / "tool").write_text("tool", encoding="utf-8")
    component = create_deterministic_tar_zst(
        component_root, release / "sample-native-base-linux-amd64.tar.zst"
    )
    (release / f"{component.name}.sha256").write_text(
        f"{'f' * 64}  {component.name}\n", encoding="utf-8"
    )
    manifest = {
        "schema": "toolbox.repository-release-manifest.v1",
        "lockDigest": lock_digest,
        "repository": {"name": "sample", "sourceIdentity": "fixture"},
        "target": TARGET,
        "components": {
            "native-base": {"archive": archive_record(component)}
        },
        "archive": archive_record(aggregate),
        "releaseLock": archive_record(lock_path),
    }
    write_json(release / "manifest.json", manifest)
    write_outer_installer(
        release / "install.sh", repository="sample", archive_name=aggregate.name
    )
    write_release_checksums(
        release, (aggregate.name, "manifest.json", "release-lock.json", "install.sh")
    )

    with pytest.raises(PackagingError, match="sidecar"):
        verify_release_directory(release)

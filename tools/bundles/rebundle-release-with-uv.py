#!/usr/bin/env python3
"""Rebuild an existing CUEstrap release with the pinned UV component.

This is a release migration utility. The canonical network-enabled builder remains
``build-linux-amd64.sh``; this utility permits a previously qualified release to
be rebundled without rebuilding the unchanged native tool components.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import zipfile

UV_VERSION = "0.11.32"
UV_REVISION = "2cf57f594cacc1643947dfc89ae49fce5e66e29f"
UV_TARGET = "x86_64-unknown-linux-gnu"
UV_SOURCE = (
    "https://github.com/astral-sh/uv/releases/download/0.11.32/"
    "uv-x86_64-unknown-linux-gnu.tar.gz"
)
UV_ARCHIVE_SHA256 = "0a48426481cac4927441f6875f7c7b07cfcc72cb96803d6e0103c55b8e3040cf"
UV_CI_ARTIFACT_SHA256 = "c7b212ba37296ec8d4e9dc22922fc3035cd02dbca5f5f8fbcfe3f0ad06728885"
UV_CI_RUN_ID = 30049327818
UV_CI_ARTIFACT_ID = 8580700036

COMPONENTS = ("python", "uv", "go", "cue", "gopls", "gopy")


def run(*command: str, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(document: dict[str, object]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def file_digest(path: Path) -> str:
    payload = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
    return hashlib.sha256(payload).hexdigest()


def read_checksum_projection(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line:
            continue
        digest, relative = line.split(maxsplit=1)
        entries[relative.lstrip("* ")] = digest
    return entries


def write_checksum_projection(path: Path, entries: dict[str, str]) -> None:
    path.write_text(
        "".join(f"{entries[relative]}  {relative}\n" for relative in sorted(entries))
    )


def update_projection_checksums(stage: Path, changed: set[str]) -> None:
    installed_path = stage / "share" / "cuestrap" / "installed-files.sha256"
    archive_path = stage / "archive-files.sha256"
    installed = read_checksum_projection(installed_path)
    archive = read_checksum_projection(archive_path)

    for relative in changed:
        path = stage / relative
        if not (path.is_file() or path.is_symlink()):
            raise ValueError(f"changed projection path is unavailable: {relative}")
        digest = file_digest(path)
        if relative not in {
            "install.sh",
            "archive-files.sha256",
            "share/cuestrap/installed-files.sha256",
        }:
            installed[relative] = digest
        if relative != "archive-files.sha256":
            archive[relative] = digest

    write_checksum_projection(installed_path, installed)
    archive["share/cuestrap/installed-files.sha256"] = file_digest(installed_path)
    write_checksum_projection(archive_path, archive)


def write_projection_checksums(stage: Path) -> None:
    installed_path = stage / "share" / "cuestrap" / "installed-files.sha256"
    archive_path = stage / "archive-files.sha256"
    installed: dict[str, str] = {}
    archive: dict[str, str] = {}
    for path in sorted(stage.rglob("*")):
        if not (path.is_file() or path.is_symlink()):
            continue
        relative = path.relative_to(stage).as_posix()
        if relative == "archive-files.sha256":
            continue
        digest = file_digest(path)
        archive[relative] = digest
        if relative not in {"install.sh", "share/cuestrap/installed-files.sha256"}:
            installed[relative] = digest
    write_checksum_projection(installed_path, installed)
    archive["share/cuestrap/installed-files.sha256"] = file_digest(installed_path)
    write_checksum_projection(archive_path, archive)


def extract_tar_zstd(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    run("tar", "--zstd", "-xf", str(archive), "-C", str(destination))


def compress_stage(stage: Path, archive: Path, level: int, threads: int) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    command = (
        "set -o pipefail; "
        "tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner "
        f"-cf - -C {shlex.quote(str(stage))} . | "
        f"zstd -{level} -T{threads} --force --no-progress "
        f"-o {shlex.quote(str(archive))}"
    )
    subprocess.run(["bash", "-c", command], check=True)


def verify_sidecar(archive: Path) -> None:
    sidecar = archive.with_name(archive.name + ".sha256")
    expected, filename = sidecar.read_text().strip().split(maxsplit=1)
    filename = filename.lstrip("* ")
    if filename != archive.name or expected != sha256(archive):
        raise ValueError(f"invalid component sidecar: {sidecar}")


def extract_uv(artifact_zip: Path, work: Path) -> tuple[Path, Path]:
    if sha256(artifact_zip) != UV_CI_ARTIFACT_SHA256:
        raise ValueError("UV CI artifact ZIP digest mismatch")
    artifact_root = work / "uv-artifact"
    artifact_root.mkdir()
    with zipfile.ZipFile(artifact_zip) as archive:
        archive.extractall(artifact_root)
    upstream = artifact_root / f"uv-{UV_TARGET}.tar.gz"
    sidecar = upstream.with_name(upstream.name + ".sha256")
    expected, filename = sidecar.read_text().strip().split(maxsplit=1)
    if filename.lstrip("* ") != upstream.name:
        raise ValueError("UV upstream checksum names an unexpected archive")
    if expected != UV_ARCHIVE_SHA256 or sha256(upstream) != UV_ARCHIVE_SHA256:
        raise ValueError("UV upstream archive digest mismatch")
    extracted = work / "uv-upstream"
    extracted.mkdir()
    run("tar", "-xzf", str(upstream), "-C", str(extracted))
    candidates = [path for path in extracted.rglob("uv") if path.is_file() and os.access(path, os.X_OK)]
    if len(candidates) != 1:
        raise ValueError(f"expected one UV executable, found {len(candidates)}")
    version = subprocess.run(
        [str(candidates[0]), "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if version != f"uv {UV_VERSION} ({UV_TARGET})":
        raise ValueError(f"unexpected UV identity: {version}")
    return candidates[0], upstream


def uv_tool() -> dict[str, object]:
    return {
        "version": UV_VERSION,
        "revision": UV_REVISION,
        "target": UV_TARGET,
        "source": UV_SOURCE,
        "sha256": UV_ARCHIVE_SHA256,
    }


def component_manifest(
    lock_digest: str,
    target: dict[str, object],
    host_requirements: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": "cuestrap.tool-bundle-manifest/v2",
        "lockDigest": lock_digest,
        "target": target,
        "hostRequirements": host_requirements,
        "tool": {
            "name": "uv",
            "version": UV_VERSION,
            "revision": UV_REVISION,
            "upstreamArchiveSha256": UV_ARCHIVE_SHA256,
        },
        "archive": {"checksumFile": "archive-files.sha256"},
        "installation": {
            "checksumFile": "share/cuestrap/installed-files.sha256",
            "omittedFiles": ["archive-files.sha256", "install.sh"],
            "mutablePaths": [],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--uv-artifact-zip", type=Path, required=True)
    parser.add_argument("--bundle-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    release_dir = args.release_dir.resolve()
    bundle_source = args.bundle_source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for path in output.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    run("sha256sum", "--check", "--strict", "SHA256SUMS", cwd=release_dir)
    for name in ("python", "go", "cue", "gopls", "gopy"):
        verify_sidecar(release_dir / f"cuestrap-{name}-linux-amd64.tar.zst")

    with tempfile.TemporaryDirectory(prefix="cuestrap-uv-rebundle-") as temporary:
        work = Path(temporary)
        uv_binary, _ = extract_uv(args.uv_artifact_zip.resolve(), work)

        combined_stage = work / "stage" / "tools"
        extract_tar_zstd(
            release_dir / "cuestrap-tools-linux-amd64.tar.zst", combined_stage
        )
        combined_manifest_path = combined_stage / "share" / "cuestrap" / "manifest.json"
        combined = json.loads(combined_manifest_path.read_text())

        lock: dict[str, object] = {
            "target": combined["target"],
            "hostRequirements": combined["hostRequirements"],
            "archive": combined["archivePolicy"],
            "pythonEnvironment": combined["pythonEnvironment"],
            "tools": {**combined["tools"], "uv": uv_tool()},
        }
        lock_digest = canonical_digest(lock)
        compression = lock["archive"]["compression"]  # type: ignore[index]
        level = int(compression["level"])
        threads = int(compression["threads"])

        component_stages: dict[str, Path] = {}
        for name in ("python", "go", "cue", "gopls", "gopy"):
            stage = work / "stage" / name
            extract_tar_zstd(
                release_dir / f"cuestrap-{name}-linux-amd64.tar.zst", stage
            )
            manifest_path = stage / "share" / "cuestrap" / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["lockDigest"] = lock_digest
            write_json(manifest_path, manifest)
            shutil.copy2(bundle_source / "install.sh", stage / "install.sh")
            shutil.copy2(
                bundle_source / "verify_bundle.py",
                stage / "share" / "cuestrap" / "verify_bundle.py",
            )
            os.chmod(stage / "install.sh", 0o755)
            os.chmod(stage / "share" / "cuestrap" / "verify_bundle.py", 0o755)
            update_projection_checksums(
                stage,
                {
                    "install.sh",
                    "share/cuestrap/verify_bundle.py",
                    "share/cuestrap/manifest.json",
                },
            )
            component_stages[name] = stage

        uv_stage = work / "stage" / "uv"
        (uv_stage / "bin").mkdir(parents=True)
        (uv_stage / "share" / "cuestrap").mkdir(parents=True)
        shutil.copy2(uv_binary, uv_stage / "bin" / "uv")
        shutil.copy2(bundle_source / "install.sh", uv_stage / "install.sh")
        shutil.copy2(
            bundle_source / "verify_bundle.py",
            uv_stage / "share" / "cuestrap" / "verify_bundle.py",
        )
        os.chmod(uv_stage / "bin" / "uv", 0o755)
        os.chmod(uv_stage / "install.sh", 0o755)
        os.chmod(uv_stage / "share" / "cuestrap" / "verify_bundle.py", 0o755)
        write_json(
            uv_stage / "share" / "cuestrap" / "manifest.json",
            component_manifest(
                lock_digest,
                combined["target"],
                combined["hostRequirements"],
            ),
        )
        write_projection_checksums(uv_stage)
        component_stages["uv"] = uv_stage

        shutil.copy2(uv_binary, combined_stage / "bin" / "uv")
        os.chmod(combined_stage / "bin" / "uv", 0o755)
        shutil.copy2(bundle_source / "install.sh", combined_stage / "install.sh")
        shutil.copy2(
            bundle_source / "verify_bundle.py",
            combined_stage / "share" / "cuestrap" / "verify_bundle.py",
        )
        shutil.copy2(
            bundle_source / "cuestrap_doctor.py",
            combined_stage / "share" / "cuestrap" / "cuestrap_doctor.py",
        )
        for executable in (
            combined_stage / "install.sh",
            combined_stage / "share" / "cuestrap" / "verify_bundle.py",
            combined_stage / "share" / "cuestrap" / "cuestrap_doctor.py",
        ):
            os.chmod(executable, 0o755)
        combined["lockDigest"] = lock_digest
        combined["tools"] = lock["tools"]
        write_json(combined_manifest_path, combined)
        update_projection_checksums(
            combined_stage,
            {
                "bin/uv",
                "install.sh",
                "share/cuestrap/verify_bundle.py",
                "share/cuestrap/cuestrap_doctor.py",
                "share/cuestrap/manifest.json",
            },
        )

        for name in COMPONENTS:
            archive = output / f"cuestrap-{name}-linux-amd64.tar.zst"
            compress_stage(component_stages[name], archive, level, threads)
            archive.with_name(archive.name + ".sha256").write_text(
                f"{sha256(archive)}  {archive.name}\n"
            )

        combined_archive = output / "cuestrap-tools-linux-amd64.tar.zst"
        compress_stage(combined_stage, combined_archive, level, threads)

        shutil.copy2(bundle_source / "install-release.sh", output / "install.sh")
        os.chmod(output / "install.sh", 0o755)
        release = json.loads((release_dir / "manifest.json").read_text())
        release["lockDigest"] = lock_digest
        release["releaseTag"] = f"cuestrap-tools-{lock_digest}"
        release["tools"] = lock["tools"]
        release["archive"] = {
            "name": combined_archive.name,
            "sha256": sha256(combined_archive),
            "size": combined_archive.stat().st_size,
        }
        write_json(output / "manifest.json", release)
        (output / "SHA256SUMS").write_text(
            "".join(
                f"{sha256(output / name)}  {name}\n"
                for name in (
                    "cuestrap-tools-linux-amd64.tar.zst",
                    "manifest.json",
                    "install.sh",
                )
            )
        )

        for name in COMPONENTS:
            verify_sidecar(output / f"cuestrap-{name}-linux-amd64.tar.zst")
        run("sha256sum", "--check", "--strict", "SHA256SUMS", cwd=output)
        provenance = {
            "schema": "cuestrap.rebundle-provenance/v1",
            "baseLockDigest": json.loads((release_dir / "manifest.json").read_text())[
                "lockDigest"
            ],
            "lockDigest": lock_digest,
            "uv": {
                **uv_tool(),
                "executableSha256": sha256(uv_binary),
                "ciArtifact": {
                    "workflowRunID": UV_CI_RUN_ID,
                    "artifactID": UV_CI_ARTIFACT_ID,
                    "zipSha256": UV_CI_ARTIFACT_SHA256,
                },
            },
        }
        write_json(output / "rebundle-provenance.json", provenance)

        print(f"lock-digest={lock_digest}")
        print(f"archive-sha256={release['archive']['sha256']}")
        print(f"uv-executable-sha256={sha256(uv_binary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify CUEstrap archive and installed projections."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys


def fail(message: str) -> None:
    raise ValueError(message)


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not value or "\x00" in value:
        fail(f"unsafe manifest path: {value!r}")
    if any(part in {"", ".", ".."} for part in path.parts):
        fail(f"unsafe manifest path: {value!r}")
    return path


def checksum_entries(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            digest, relative = line.split("  ", 1)
        except ValueError:
            fail(f"invalid checksum line {number} in {path}")
        safe_relative(relative)
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            fail(f"invalid SHA-256 on line {number} in {path}")
        if relative in entries:
            fail(f"duplicate checksum path: {relative}")
        entries[relative] = digest
    return entries


def projection_files(root: Path) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_file() or path.is_symlink():
            files.add(path.relative_to(root).as_posix())
        if path.is_symlink():
            target = (path.parent / os.readlink(path)).resolve(strict=False)
            try:
                target.relative_to(root.resolve())
            except ValueError:
                fail(f"symlink escapes projection: {path.relative_to(root)}")
    return files


def verify_projection(root: Path, kind: str) -> dict[str, object]:
    root = root.resolve()
    manifest_path = root / "share" / "cuestrap" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if kind == "archive":
        checksum_relative = manifest["archive"]["checksumFile"]
    else:
        checksum_relative = manifest["installation"]["checksumFile"]
    checksum_path = root / safe_relative(checksum_relative)
    entries = checksum_entries(checksum_path)

    for relative, expected in entries.items():
        path = root / relative
        if not path.exists():
            fail(f"missing {kind} file: {relative}")
        payload = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            fail(f"changed {kind} file: {relative}")

    expected_files = set(entries) | {checksum_relative}
    actual_files = projection_files(root)
    missing = sorted(expected_files - actual_files)
    unexpected = sorted(actual_files - expected_files)
    if missing:
        fail(f"missing {kind} files: {', '.join(missing)}")
    if unexpected:
        fail(f"unexpected {kind} files: {', '.join(unexpected)}")

    target = manifest["target"]
    if target["os"] != "linux" or target["arch"] != "amd64":
        fail(f"unsupported embedded target: {target!r}")
    return manifest


def verify_release(
    root: Path, release_manifest_path: Path, archive_path: Path
) -> None:
    embedded = json.loads(
        (root / "share" / "cuestrap" / "manifest.json").read_text()
    )
    release = json.loads(release_manifest_path.read_text())
    if embedded.get("lockDigest") != release.get("lockDigest"):
        fail("release and embedded lock digests differ")
    if embedded.get("target") != release.get("target"):
        fail("release and embedded targets differ")
    archive = release.get("archive", {})
    if archive.get("name") != "cuestrap-tools-linux-amd64.tar.zst":
        fail("release manifest names an unexpected archive")
    payload = archive_path.read_bytes()
    if archive.get("size") != len(payload):
        fail("release manifest archive size differs")
    if archive.get("sha256") != hashlib.sha256(payload).hexdigest():
        fail("release manifest archive digest differs")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("archive", "installed", "release"))
    parser.add_argument("root", type=Path)
    parser.add_argument("release_manifest", type=Path, nargs="?")
    parser.add_argument("archive", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        if args.kind == "release":
            if args.release_manifest is None or args.archive is None:
                parser.error(
                    "release verification requires a release manifest and archive"
                )
            verify_release(
                args.root.resolve(),
                args.release_manifest.resolve(),
                args.archive.resolve(),
            )
        else:
            verify_projection(args.root, args.kind)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"bundle verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

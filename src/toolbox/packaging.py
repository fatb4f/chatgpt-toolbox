from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile

from toolbox.acquisition import sha256_file, sha256_tree


class PackagingError(RuntimeError):
    pass


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_json(path: Path, payload: object, *, canonical: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if canonical:
        path.write_bytes(canonical_json_bytes(payload) + b"\n")
    else:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return path


def _file_payload(path: Path) -> bytes:
    return os.readlink(path).encode("utf-8") if path.is_symlink() else path.read_bytes()


def _under(relative: str, roots: Iterable[str]) -> bool:
    path = PurePosixPath(relative)
    for value in roots:
        root = PurePosixPath(value)
        if path == root or root in path.parents:
            return True
    return False


def checksum_entries(
    root: Path,
    *,
    excluded: Iterable[str] = (),
    excluded_roots: Iterable[str] = (),
) -> tuple[tuple[str, str], ...]:
    excluded_set = set(excluded)
    entries: list[tuple[str, str]] = []
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        if not (path.is_file() or path.is_symlink()):
            continue
        relative = path.relative_to(root).as_posix()
        if relative in excluded_set or _under(relative, excluded_roots):
            continue
        entries.append((relative, hashlib.sha256(_file_payload(path)).hexdigest()))
    return tuple(entries)


def write_checksum_file(
    path: Path,
    root: Path,
    *,
    excluded: Iterable[str] = (),
    excluded_roots: Iterable[str] = (),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = checksum_entries(
        root, excluded=excluded, excluded_roots=excluded_roots
    )
    path.write_text(
        "".join(f"{digest}  {relative}\n" for relative, digest in entries),
        encoding="utf-8",
    )
    return path


def _normalized_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.pax_headers = {}
    if info.isdir():
        info.mode = 0o755
    elif info.isfile() and info.mode & 0o111:
        info.mode = 0o755
    elif info.isfile():
        info.mode = 0o644
    elif info.issym():
        info.mode = 0o777
    return info


def create_deterministic_tar_zst(
    root: Path,
    archive: Path,
    *,
    compression_level: int = 19,
) -> Path:
    if not root.is_dir():
        raise PackagingError(f"archive root does not exist: {root}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary_tar = archive.with_suffix(".tar.tmp")
    temporary_archive = archive.with_suffix(archive.suffix + ".tmp")
    temporary_tar.unlink(missing_ok=True)
    temporary_archive.unlink(missing_ok=True)
    with tarfile.open(temporary_tar, mode="w", format=tarfile.GNU_FORMAT) as stream:
        root_info = tarfile.TarInfo(".")
        root_info.type = tarfile.DIRTYPE
        root_info.mode = 0o755
        stream.addfile(_normalized_tar_info(root_info))
        for path in sorted(
            root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
        ):
            relative = path.relative_to(root).as_posix()
            stream.add(
                path,
                arcname=f"./{relative}",
                recursive=False,
                filter=_normalized_tar_info,
            )
    try:
        subprocess.run(
            [
                "zstd",
                f"-{compression_level}",
                "-T1",
                "--force",
                "--no-progress",
                str(temporary_tar),
                "-o",
                str(temporary_archive),
            ],
            check=True,
        )
        os.replace(temporary_archive, archive)
    finally:
        temporary_tar.unlink(missing_ok=True)
        temporary_archive.unlink(missing_ok=True)
    return archive


def extract_tar_zst(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    decompressor = subprocess.Popen(
        ["zstd", "-dc", str(archive)], stdout=subprocess.PIPE
    )
    if decompressor.stdout is None:
        raise PackagingError("zstd did not expose archive output")
    try:
        with tarfile.open(fileobj=decompressor.stdout, mode="r|") as stream:
            for member in stream:
                target = (destination / member.name).resolve()
                resolved = destination.resolve()
                if target != resolved and resolved not in target.parents:
                    raise PackagingError(
                        f"archive member escapes destination: {member.name}"
                    )
                if member.issym() or member.islnk():
                    link = (Path(member.name).parent / member.linkname).as_posix()
                    linked = (destination / link).resolve()
                    if linked != resolved and resolved not in linked.parents:
                        raise PackagingError(
                            f"archive link escapes destination: {member.name}"
                        )
                stream.extract(member, destination, filter="data")
    finally:
        decompressor.stdout.close()
    if decompressor.wait() != 0:
        raise PackagingError(f"zstd failed to decompress {archive}")
    return destination


def verify_deterministic_tar_zst(archive: Path, expected_root: Path) -> None:
    """Reopen a component/archive and prove deterministic metadata and content."""
    if not archive.is_file():
        raise PackagingError(f"archive does not exist: {archive}")
    decompressor = subprocess.Popen(
        ["zstd", "-dc", str(archive)], stdout=subprocess.PIPE
    )
    if decompressor.stdout is None:
        raise PackagingError("zstd did not expose archive output")
    try:
        with tarfile.open(fileobj=decompressor.stdout, mode="r|") as stream:
            for member in stream:
                if member.uid != 0 or member.gid != 0:
                    raise PackagingError(
                        f"archive member has nonzero ownership: {member.name}"
                    )
                if member.mtime != 0:
                    raise PackagingError(
                        f"archive member has non-epoch timestamp: {member.name}"
                    )
                if member.uname not in {"", None} or member.gname not in {"", None}:
                    raise PackagingError(
                        f"archive member has named ownership: {member.name}"
                    )
                name = PurePosixPath(member.name)
                if member.name not in {".", "./"} and (
                    name.is_absolute() or ".." in name.parts
                ):
                    raise PackagingError(
                        f"archive member has unsafe path: {member.name}"
                    )
    finally:
        decompressor.stdout.close()
    if decompressor.wait() != 0:
        raise PackagingError(f"zstd failed to inspect {archive}")

    with tempfile.TemporaryDirectory(prefix="toolbox-archive-verify-") as directory:
        extracted = extract_tar_zst(archive, Path(directory))
        expected = sha256_tree(expected_root)
        actual = sha256_tree(extracted)
        if actual != expected:
            raise PackagingError(
                f"archive projection differs from source tree: expected {expected}, got {actual}"
            )


def _read_checksum_file(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as error:
            raise PackagingError(
                f"invalid checksum line {number} in {path}"
            ) from error
        candidate = PurePosixPath(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in entries:
            raise PackagingError(f"invalid checksum path in {path}: {relative!r}")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise PackagingError(f"invalid checksum digest in {path}: {digest!r}")
        entries[relative] = digest
    return entries


def verify_release_directory(release_dir: Path) -> None:
    """Verify the outer release authority and every admitted component archive."""
    manifest_path = release_dir / "manifest.json"
    lock_path = release_dir / "release-lock.json"
    checksums_path = release_dir / "SHA256SUMS"
    installer_path = release_dir / "install.sh"
    for path in (manifest_path, lock_path, checksums_path, installer_path):
        if not path.is_file():
            raise PackagingError(f"release metadata is missing: {path.name}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PackagingError("release metadata is not valid JSON") from error

    lock_digest = hashlib.sha256(lock_path.read_bytes().rstrip(b"\n")).hexdigest()
    if manifest.get("lockDigest") != lock_digest:
        raise PackagingError("release manifest lock digest is not bound to release-lock.json")

    checksums = _read_checksum_file(checksums_path)
    expected_outer = {
        manifest.get("archive", {}).get("name"),
        "manifest.json",
        "release-lock.json",
        "install.sh",
    }
    if (release_dir / "zstd").is_file():
        expected_outer.add("zstd")
    if None in expected_outer or set(checksums) != expected_outer:
        raise PackagingError("SHA256SUMS does not cover the exact outer release authority")
    for relative, expected in checksums.items():
        path = release_dir / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise PackagingError(f"release checksum mismatch: {relative}")

    def verify_record(record: Mapping[str, object], label: str) -> Path:
        name = record.get("name")
        if not isinstance(name, str):
            raise PackagingError(f"{label} has no archive name")
        path = release_dir / name
        if not path.is_file():
            raise PackagingError(f"{label} archive is missing: {name}")
        if record.get("size") != path.stat().st_size:
            raise PackagingError(f"{label} archive size differs: {name}")
        if record.get("sha256") != sha256_file(path):
            raise PackagingError(f"{label} archive digest differs: {name}")
        return path

    verify_record(manifest.get("archive", {}), "aggregate")
    verify_record(manifest.get("releaseLock", {}), "release lock")
    for name, component in manifest.get("components", {}).items():
        if not isinstance(component, dict):
            raise PackagingError(f"component record is invalid: {name}")
        archive = verify_record(component.get("archive", {}), f"component {name}")
        sidecar = release_dir / f"{archive.name}.sha256"
        sidecar_entries = _read_checksum_file(sidecar)
        if sidecar_entries != {archive.name: sha256_file(archive)}:
            raise PackagingError(f"component checksum sidecar differs: {archive.name}")


def component_manifest_path(root: Path, name: str) -> Path:
    return root / "share" / "toolbox" / "components" / f"{name}.json"


def component_checksum_path(root: Path, name: str) -> Path:
    return root / "share" / "toolbox" / "components" / f"{name}-files.sha256"


def finalize_component_stage(root: Path, name: str, manifest: Mapping[str, object]) -> None:
    manifest_path = component_manifest_path(root, name)
    checksum_path = component_checksum_path(root, name)
    write_json(manifest_path, manifest)
    write_checksum_file(
        checksum_path,
        root,
        excluded=(checksum_path.relative_to(root).as_posix(),),
    )


def _verifier_script() -> str:
    return r'''#!/usr/bin/env python3
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


def under(relative: str, roots: list[str]) -> bool:
    path = PurePosixPath(relative)
    return any(path == PurePosixPath(root) or PurePosixPath(root) in path.parents for root in roots)


def projection_files(root: Path, mutable: list[str], omitted: list[str]) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if relative in omitted or under(relative, mutable):
            continue
        if path.is_file() or path.is_symlink():
            files.add(relative)
        if path.is_symlink():
            target = (path.parent / os.readlink(path)).resolve(strict=False)
            try:
                target.relative_to(root.resolve())
            except ValueError:
                fail(f"symlink escapes projection: {relative}")
    return files


def verify_projection(root: Path, kind: str) -> dict[str, object]:
    root = root.resolve()
    manifest = json.loads((root / "share/toolbox/manifest.json").read_text())
    section = manifest["archive"] if kind == "archive" else manifest["installation"]
    checksum_relative = section["checksumFile"]
    mutable = list(manifest.get("installation", {}).get("mutablePaths", [])) if kind == "installed" else []
    omitted = list(manifest.get("installation", {}).get("omittedFiles", [])) if kind == "installed" else []
    checksum_path = root / safe_relative(checksum_relative)
    entries = checksum_entries(checksum_path)
    for relative, expected in entries.items():
        path = root / relative
        if not path.exists() and not path.is_symlink():
            fail(f"missing {kind} file: {relative}")
        payload = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected:
            fail(f"changed {kind} file: {relative}")
    expected_files = set(entries) | {checksum_relative}
    actual_files = projection_files(root, mutable, omitted)
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


def verify_release(root: Path, release_manifest_path: Path, archive_path: Path, lock_path: Path) -> None:
    embedded = json.loads((root / "share/toolbox/manifest.json").read_text())
    release = json.loads(release_manifest_path.read_text())
    lock = lock_path.read_bytes()
    lock_digest = hashlib.sha256(lock.rstrip(b"\n")).hexdigest()
    if release.get("lockDigest") != lock_digest:
        fail("release lock digest differs from release-lock.json")
    if embedded.get("lockDigest") != release.get("lockDigest"):
        fail("release and embedded lock digests differ")
    if embedded.get("target") != release.get("target"):
        fail("release and embedded targets differ")
    if embedded.get("repository") != release.get("repository"):
        fail("release and embedded repository identities differ")
    archive = release.get("archive", {})
    payload = archive_path.read_bytes()
    if archive.get("name") != archive_path.name:
        fail("release manifest names an unexpected archive")
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
    parser.add_argument("release_lock", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        if args.kind == "release":
            if args.release_manifest is None or args.archive is None or args.release_lock is None:
                parser.error("release verification requires manifest, archive, and lock")
            verify_release(args.root.resolve(), args.release_manifest.resolve(), args.archive.resolve(), args.release_lock.resolve())
        else:
            verify_projection(args.root, args.kind)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"bundle verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _internal_installer_script(default_prefix: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

prefix=${{TOOLBOX_PREFIX:-"${{HOME}}/.local/{default_prefix}"}}
force=false
verify_only=false

usage() {{
    cat <<'EOF'
Usage: install.sh [--prefix DIR] [--verify-only] [--force]

Verifies an extracted toolbox bundle and atomically activates it under
DIR/current, backed by DIR/versions/<lock-digest>.
EOF
}}

while (($#)); do
    case "$1" in
        --prefix) [[ $# -ge 2 ]] || {{ echo "--prefix requires a value" >&2; exit 2; }}; prefix=$2; shift 2 ;;
        --verify-only) verify_only=true; shift ;;
        --force) force=true; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

root=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
manifest="$root/share/toolbox/manifest.json"
archive_checksums="$root/archive-files.sha256"
for required in "$manifest" "$archive_checksums"; do
    [[ -f "$required" ]] || {{ echo "missing bundle metadata: $required" >&2; exit 1; }}
done
"$root/bin/python3" "$root/share/toolbox/verify_bundle.py" archive "$root"
lock_digest=$("$root/bin/python3" - "$manifest" <<'PY'
import json, pathlib, sys
value=json.loads(pathlib.Path(sys.argv[1]).read_text())["lockDigest"]
if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
    raise SystemExit("invalid lock digest")
print(value)
PY
)
if $verify_only; then printf 'verified lock digest %s\n' "$lock_digest"; exit 0; fi

if [[ -L "$prefix" ]]; then echo "installation root must not be a symlink: $prefix" >&2; exit 1; fi
mkdir -p "$prefix"
prefix=$(CDPATH='' cd -- "$prefix" && pwd)
if [[ "$prefix" == / || "$prefix" == "$HOME" ]]; then echo "refusing broad installation root: $prefix" >&2; exit 1; fi
versions="$prefix/versions"
target="$versions/$lock_digest"
mkdir -p "$versions"

verify_installed() {{
    "$1/bin/python3" "$1/share/toolbox/verify_bundle.py" installed "$1"
}}
activate() {{
    local activation="$prefix/.current.$$.tmp"
    ln -s "versions/$lock_digest" "$activation"
    mv -Tf "$activation" "$prefix/current"
}}
if [[ -d "$target" ]] && ! $force; then
    verify_installed "$target" || {{ echo "existing version is invalid; rerun with --force" >&2; exit 1; }}
    activate
    echo "activated existing version $lock_digest"
    echo "export PATH=$prefix/current/bin:\\$PATH"
    exit 0
fi
candidate=$(mktemp -d "$versions/.install.${{lock_digest}}.XXXXXX")
cleanup() {{ [[ -z "${{candidate:-}}" || ! -d "$candidate" ]] || rm -rf -- "$candidate"; }}
trap cleanup EXIT
cp -a "$root/." "$candidate/"
rm -f "$candidate/install.sh" "$candidate/archive-files.sha256"

"$candidate/bin/python3" - "$candidate" "$manifest" <<'PY'
import json, os, pathlib, subprocess, sys
candidate=pathlib.Path(sys.argv[1])
manifest=json.loads(pathlib.Path(sys.argv[2]).read_text())
project=manifest.get("pythonProject")
if project:
    source=candidate / project["sourceRoot"] / project.get("projectPath", ".")
    environment=candidate / project["environmentPath"]
    cache=candidate / project["cachePath"]
    argv=[str(candidate / "bin/uv"), "sync", "--offline", "--frozen", "--project", str(source)]
    for group in project.get("groups", []):
        argv.extend(("--group", group))
    env={{**os.environ, "UV_CACHE_DIR": str(cache), "UV_PROJECT_ENVIRONMENT": str(environment), "UV_PYTHON": str(candidate / "bin/python3"), "UV_NO_PROGRESS": "1"}}
    subprocess.run(argv, check=True, env=env)
PY

verify_installed "$candidate"
if [[ -e "$target" ]]; then
    mv --help | grep -q -- '--exchange' || {{ echo "--force replacement requires mv --exchange" >&2; exit 1; }}
    mv --exchange -T "$candidate" "$target"
else
    mv -T "$candidate" "$target"
    candidate=
fi
activate
if [[ -n "${{candidate:-}}" && -d "$candidate" ]]; then rm -rf -- "$candidate"; candidate=; fi
echo "installed version $lock_digest into $target"
echo "export PATH=$prefix/current/bin:\\$PATH"
'''


def _outer_installer_script(
    repository: str, archive_name: str, zstd_name: str | None
) -> str:
    upper = repository.upper().replace("-", "_")
    bundled_zstd = zstd_name or ""
    zstd_asset = f' "{zstd_name}"' if zstd_name else ""
    return f'''#!/usr/bin/env bash
set -euo pipefail

archive_name={archive_name}
zstd_name={bundled_zstd}
prefix=${{{upper}_PREFIX:-"${{HOME}}/.local/{repository}"}}
base_url=${{{upper}_RELEASE_URL:-}}
source_dir=
force=false
verify_only=false
print_manifest=false
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [[ -f "$script_dir/$archive_name" && -f "$script_dir/SHA256SUMS" && -f "$script_dir/manifest.json" && -f "$script_dir/release-lock.json" ]]; then source_dir=$script_dir; fi
usage() {{
cat <<'EOF'
Usage: install.sh [OPTIONS]
  --prefix DIR
  --source-dir DIR
  --base-url URL
  --verify-only
  --print-manifest
  --force
EOF
}}
while (($#)); do
case "$1" in
  --prefix) [[ $# -ge 2 ]] || exit 2; prefix=$2; shift 2 ;;
  --source-dir) [[ $# -ge 2 ]] || exit 2; source_dir=$2; shift 2 ;;
  --base-url) [[ $# -ge 2 ]] || exit 2; base_url=${{2%/}}; source_dir=; shift 2 ;;
  --verify-only) verify_only=true; shift ;;
  --print-manifest) print_manifest=true; shift ;;
  --force) force=true; shift ;;
  --help|-h) usage; exit 0 ;;
  *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
esac
done
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || {{ echo "this bundle requires Linux x86_64" >&2; exit 1; }}
for command_name in sha256sum tar; do command -v "$command_name" >/dev/null || {{ echo "required command unavailable: $command_name" >&2; exit 1; }}; done
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
assets=("$archive_name" SHA256SUMS manifest.json release-lock.json install.sh{zstd_asset})
if [[ -n "$source_dir" ]]; then
  for asset in "${{assets[@]}}"; do [[ -f "$source_dir/$asset" ]] || {{ echo "offline asset is missing: $source_dir/$asset" >&2; exit 1; }}; cp "$source_dir/$asset" "$work/$asset"; done
else
  [[ -n "$base_url" ]] || {{ echo "--base-url is required when release assets are not adjacent" >&2; exit 1; }}
  command -v curl >/dev/null || {{ echo "required command unavailable: curl" >&2; exit 1; }}
  for asset in "${{assets[@]}}"; do curl --fail --location --proto '=https' --tlsv1.2 "$base_url/$asset" -o "$work/$asset"; done
fi
(cd "$work" && sha256sum --check --strict SHA256SUMS)
if [[ -n "$zstd_name" ]]; then
  chmod 0755 "$work/$zstd_name"
  zstd_command="$work/$zstd_name"
else
  command -v zstd >/dev/null || {{ echo "required command unavailable: zstd" >&2; exit 1; }}
  zstd_command=zstd
fi
path_is_safe() {{
 local value=$1 depth=0 part
 [[ -n "$value" && "$value" != /* && "$value" != *$'\n'* && "$value" != *$'\r'* && "$value" != *$'\t'* ]] || return 1
 IFS='/' read -r -a parts <<< "$value"
 for part in "${{parts[@]}}"; do case "$part" in ''|.) ;; ..) ((depth > 0)) || return 1; ((depth -= 1)) ;; *) ((depth += 1)) ;; esac; done
}}
while IFS= read -r member; do path_is_safe "$member" || {{ echo "unsafe archive member: $member" >&2; exit 1; }}; done < <("$zstd_command" -dc "$work/$archive_name" | tar -tf -)
mkdir -p "$work/extracted"
"$zstd_command" -dc "$work/$archive_name" | tar -xf - -C "$work/extracted"
"$work/extracted/bin/python3" "$work/extracted/share/toolbox/verify_bundle.py" archive "$work/extracted"
"$work/extracted/bin/python3" "$work/extracted/share/toolbox/verify_bundle.py" release "$work/extracted" "$work/manifest.json" "$work/$archive_name" "$work/release-lock.json"
if $print_manifest; then cat "$work/manifest.json"; exit 0; fi
if $verify_only; then echo "release verification passed"; exit 0; fi
arguments=(--prefix "$prefix"); $force && arguments+=(--force)
bash "$work/extracted/install.sh" "${{arguments[@]}}"
'''


def write_bundle_support(
    root: Path,
    *,
    repository: str,
    manifest: Mapping[str, object],
    mutable_paths: tuple[str, ...] = (),
) -> None:
    support = root / "share" / "toolbox"
    support.mkdir(parents=True, exist_ok=True)
    archive_checksum = "archive-files.sha256"
    installed_checksum = "share/toolbox/installed-files.sha256"
    enriched = dict(manifest)
    enriched["archive"] = {"checksumFile": archive_checksum}
    enriched["installation"] = {
        "checksumFile": installed_checksum,
        "omittedFiles": [archive_checksum, "install.sh"],
        "mutablePaths": list(mutable_paths),
    }
    write_json(support / "manifest.json", enriched)
    verifier = support / "verify_bundle.py"
    verifier.write_text(_verifier_script(), encoding="utf-8")
    verifier.chmod(0o755)
    installer = root / "install.sh"
    installer.write_text(_internal_installer_script(repository), encoding="utf-8")
    installer.chmod(0o755)
    write_checksum_file(
        root / installed_checksum,
        root,
        excluded=(archive_checksum, "install.sh", installed_checksum),
        excluded_roots=mutable_paths,
    )
    write_checksum_file(
        root / archive_checksum,
        root,
        excluded=(archive_checksum,),
    )


def write_outer_installer(
    path: Path,
    *,
    repository: str,
    archive_name: str,
    zstd_name: str | None = None,
) -> Path:
    path.write_text(
        _outer_installer_script(repository, archive_name, zstd_name),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def archive_record(path: Path) -> dict[str, object]:
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def write_release_checksums(release_dir: Path, names: Iterable[str]) -> Path:
    path = release_dir / "SHA256SUMS"
    path.write_text(
        "".join(
            f"{sha256_file(release_dir / name)}  {name}\n" for name in names
        ),
        encoding="utf-8",
    )
    return path


def component_stage_digest(root: Path) -> str:
    return sha256_tree(root)

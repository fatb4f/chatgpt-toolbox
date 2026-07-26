from __future__ import annotations

from pathlib import Path
import filecmp
import os
import shutil
import tarfile
import zipfile

from toolbox.model import InstallEntry, InstallEntryKind, LinkSpec


class StagingError(RuntimeError):
    pass


def _safe_destination(root: Path, member: str) -> Path:
    destination = (root / member).resolve()
    if destination != root.resolve() and root.resolve() not in destination.parents:
        raise StagingError(f"archive member escapes extraction root: {member!r}")
    return destination


def extract_archive(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as stream:
            for member in stream.getmembers():
                _safe_destination(destination, member.name)
                if member.issym() or member.islnk():
                    link_target = Path(member.name).parent / member.linkname
                    _safe_destination(destination, link_target.as_posix())
            stream.extractall(destination, filter="data")
        return destination
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as stream:
            for member in stream.infolist():
                _safe_destination(destination, member.filename)
            stream.extractall(destination)
        return destination
    raise StagingError(f"unsupported archive format: {archive}")


def _copy_entry(source: Path, destination: Path, kind: InstallEntryKind) -> None:
    resolved_kind = kind
    if kind is InstallEntryKind.AUTO:
        resolved_kind = (
            InstallEntryKind.TREE if source.is_dir() else InstallEntryKind.FILE
        )
    if resolved_kind is InstallEntryKind.TREE:
        if not source.is_dir():
            raise StagingError(f"expected install tree: {source}")
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True)
    else:
        if not source.is_file():
            raise StagingError(f"expected install file: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def stage_entries(
    source_root: Path, prefix: Path, entries: tuple[InstallEntry, ...]
) -> None:
    for entry in entries:
        source = source_root / entry.source
        destination = prefix / entry.destination
        _copy_entry(source, destination, entry.kind)


def stage_links(prefix: Path, links: tuple[LinkSpec, ...]) -> None:
    for link in links:
        destination = prefix / link.destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)
        os.symlink(link.target, destination)


def _same_projection_entry(source: Path, destination: Path) -> bool:
    if source.is_symlink() or destination.is_symlink():
        return (
            source.is_symlink()
            and destination.is_symlink()
            and os.readlink(source) == os.readlink(destination)
        )
    return (
        source.is_file()
        and destination.is_file()
        and (source.stat().st_mode & 0o7777) == (destination.stat().st_mode & 0o7777)
        and filecmp.cmp(source, destination, shallow=False)
    )


def stage_projection(source_root: Path, prefix: Path) -> None:
    """Merge one immutable pooled projection into a repository bundle prefix."""
    prefix.mkdir(parents=True, exist_ok=True)
    for source in sorted(
        source_root.rglob("*"), key=lambda item: item.relative_to(source_root).as_posix()
    ):
        relative = source.relative_to(source_root)
        destination = prefix / relative
        if source.is_dir() and not source.is_symlink():
            if destination.exists() and not destination.is_dir():
                raise StagingError(
                    f"tool projections conflict at {relative.as_posix()}"
                )
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            if _same_projection_entry(source, destination):
                continue
            raise StagingError(f"tool projections conflict at {relative.as_posix()}")
        if source.is_symlink():
            os.symlink(os.readlink(source), destination)
            continue
        shutil.copy2(source, destination)


def write_activation(prefix: Path) -> Path:
    activation = prefix / "activate"
    activation.write_text(
        "#!/bin/sh\n"
        'TOOLBOX_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        "export TOOLBOX_ROOT\n"
        'export PATH="$TOOLBOX_ROOT/bin:$PATH"\n'
        'export GOROOT="$TOOLBOX_ROOT/libexec/go"\n'
        "export GOTOOLCHAIN=local\n"
        'export GOBIN="$TOOLBOX_ROOT/bin"\n',
        encoding="utf-8",
    )
    activation.chmod(0o755)
    return activation

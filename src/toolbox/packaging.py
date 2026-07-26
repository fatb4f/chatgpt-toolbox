from __future__ import annotations

from pathlib import Path
import gzip
import json
import os
import tarfile


def write_native_lock(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    if info.isdir():
        info.mode = 0o755
    elif info.isfile() and info.mode & 0o111:
        info.mode = 0o755
    elif info.isfile():
        info.mode = 0o644
    return info


def create_deterministic_archive(prefix: Path, archive: Path, root_name: str) -> Path:
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as stream:
                root_info = tarfile.TarInfo(root_name)
                root_info.type = tarfile.DIRTYPE
                root_info.mode = 0o755
                stream.addfile(_tar_filter(root_info))
                for path in sorted(prefix.rglob("*"), key=lambda item: item.relative_to(prefix).as_posix()):
                    relative = path.relative_to(prefix)
                    arcname = (Path(root_name) / relative).as_posix()
                    stream.add(path, arcname=arcname, recursive=False, filter=_tar_filter)
    os.replace(temporary, archive)
    return archive

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request

from toolbox.model import AcquisitionKind, AcquisitionSpec, ToolSpec, to_primitive


class AcquisitionError(RuntimeError):
    pass


class Runner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]: ...


class SubprocessRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            check=True,
            text=True,
            capture_output=capture_output,
        )


@dataclass(frozen=True, slots=True)
class AcquiredArtifact:
    name: str
    path: Path | None
    identity: str
    cache_key: str


def canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        to_primitive(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def acquisition_cache_key(acquisition: AcquisitionSpec) -> str:
    return canonical_digest(
        {
            "schema": "toolbox.acquisition-key.v1",
            "acquisition": acquisition,
        }
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_symlink():
            digest.update(
                b"L\0"
                + relative
                + b"\0"
                + os.readlink(path).encode("utf-8")
                + b"\0"
            )
        elif path.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str | None) -> None:
    if expected is None:
        raise AcquisitionError(f"no pinned SHA-256 for {path.name}")
    actual = sha256_file(path)
    if actual != expected:
        raise AcquisitionError(
            f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}"
        )


def _github_asset_url(acquisition: AcquisitionSpec) -> str:
    repository = acquisition.repository or ""
    release = acquisition.release or ""
    asset = acquisition.asset or ""
    return f"https://github.com/{repository}/releases/download/{release}/{asset}"


def _download_verified(url: str, destination: Path, expected: str | None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        try:
            verify_sha256(destination, expected)
            return
        except AcquisitionError:
            destination.unlink()
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with urllib.request.urlopen(url) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    verify_sha256(temporary, expected)
    os.replace(temporary, destination)


def _valid_git_checkout(
    destination: Path, revision: str, runner: Runner
) -> bool:
    if not (destination / ".git").is_dir():
        return False
    try:
        head = runner.run(
            ["git", "rev-parse", "HEAD"], cwd=destination, capture_output=True
        ).stdout.strip()
        status = runner.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=destination,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError:
        return False
    return head == revision and status == ""


def acquire(
    name: str,
    acquisition: AcquisitionSpec,
    *,
    downloads: Path,
    sources: Path,
    toolbox_root: Path,
    runner: Runner,
) -> AcquiredArtifact:
    downloads.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    key = acquisition_cache_key(acquisition)

    match acquisition.kind:
        case AcquisitionKind.GITHUB_RELEASE:
            url = _github_asset_url(acquisition)
            path = downloads / key / (acquisition.asset or "asset")
            _download_verified(url, path, acquisition.sha256)
            identity = (
                f"{acquisition.repository}@{acquisition.release}:"
                f"{acquisition.asset}#sha256:{acquisition.sha256}"
            )
            return AcquiredArtifact(name, path, identity, key)

        case AcquisitionKind.HTTP_ARCHIVE:
            filename = Path(acquisition.url or "archive").name or "archive"
            path = downloads / key / filename
            _download_verified(acquisition.url or "", path, acquisition.sha256)
            identity = f"{acquisition.url}#sha256:{acquisition.sha256}"
            return AcquiredArtifact(name, path, identity, key)

        case AcquisitionKind.GIT_CHECKOUT:
            revision = acquisition.revision or ""
            destination = sources / key
            if not _valid_git_checkout(destination, revision, runner):
                temporary = sources / f".{key}.tmp"
                shutil.rmtree(temporary, ignore_errors=True)
                temporary.mkdir(parents=True)
                runner.run(["git", "init", "--quiet"], cwd=temporary)
                runner.run(
                    ["git", "remote", "add", "origin", acquisition.repository or ""],
                    cwd=temporary,
                )
                runner.run(
                    [
                        "git",
                        "fetch",
                        "--quiet",
                        "--depth",
                        "1",
                        "origin",
                        revision,
                    ],
                    cwd=temporary,
                )
                runner.run(
                    ["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"],
                    cwd=temporary,
                )
                completed = runner.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=temporary,
                    capture_output=True,
                )
                actual = completed.stdout.strip()
                if actual != revision:
                    raise AcquisitionError(
                        f"resolved git revision {actual}, expected {revision}"
                    )
                shutil.rmtree(destination, ignore_errors=True)
                os.replace(temporary, destination)
            return AcquiredArtifact(
                name,
                destination,
                f"{acquisition.repository}@{revision}",
                key,
            )

        case AcquisitionKind.GO_MODULE:
            version = acquisition.version or ""
            return AcquiredArtifact(
                name, None, f"{acquisition.module}@{version}", key
            )

        case AcquisitionKind.LOCAL_SOURCE:
            path = toolbox_root / (acquisition.path or "")
            if not path.exists():
                raise AcquisitionError(f"local source for {name} does not exist: {path}")
            digest = sha256_tree(path)
            return AcquiredArtifact(
                name,
                path,
                f"local:{acquisition.path}#sha256:{digest}",
                key,
            )

    raise AssertionError(f"unhandled acquisition kind: {acquisition.kind}")


def acquire_tool(
    tool: ToolSpec,
    *,
    downloads: Path,
    sources: Path,
    toolbox_root: Path,
    runner: Runner,
) -> AcquiredArtifact:
    return acquire(
        tool.name,
        tool.acquisition,
        downloads=downloads,
        sources=sources,
        toolbox_root=toolbox_root,
        runner=runner,
    )

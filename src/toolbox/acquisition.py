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
    tool: str
    path: Path | None
    identity: str
    cache_key: str = ""


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
        mode = f"{path.lstat().st_mode & 0o7777:o}".encode("ascii")
        if path.is_symlink():
            digest.update(
                b"L\0"
                + relative
                + b"\0"
                + mode
                + b"\0"
                + path.readlink().as_posix().encode("utf-8")
                + b"\0"
            )
        elif path.is_dir():
            digest.update(b"D\0" + relative + b"\0" + mode + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0" + mode + b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
    return digest.hexdigest()


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        to_primitive(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def acquisition_cache_key(acquisition: AcquisitionSpec) -> str:
    return f"{acquisition.kind.value}-{_canonical_digest(acquisition)}"


def verify_sha256(path: Path, expected: str | None) -> None:
    if expected is None:
        raise AcquisitionError(f"no pinned SHA-256 for {path.name}")
    actual = sha256_file(path)
    if actual != expected:
        raise AcquisitionError(
            f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}"
        )


def _resolve_github_asset(tool: ToolSpec, runner: Runner) -> None:
    acquisition = tool.acquisition
    completed = runner.run(
        [
            "gh",
            "release",
            "view",
            acquisition.release or "",
            "--repo",
            acquisition.repository or "",
            "--json",
            "assets",
        ],
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    names = [asset["name"] for asset in payload.get("assets", [])]
    if names.count(acquisition.asset) != 1:
        raise AcquisitionError(
            f"release {acquisition.repository}@{acquisition.release} does not "
            f"contain exactly one asset named {acquisition.asset!r}"
        )


def _cached_git_revision(destination: Path, runner: Runner) -> str | None:
    if not destination.is_dir():
        return None
    try:
        completed = runner.run(
            ["git", "rev-parse", "HEAD"], cwd=destination, capture_output=True
        )
        status = runner.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=destination,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    if status.stdout.strip():
        return None
    return completed.stdout.strip()


def acquire_tool(
    tool: ToolSpec,
    *,
    downloads: Path,
    sources: Path,
    toolbox_root: Path,
    runner: Runner,
) -> AcquiredArtifact:
    downloads.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    acquisition = tool.acquisition
    cache_key = acquisition_cache_key(acquisition)

    match acquisition.kind:
        case AcquisitionKind.GITHUB_RELEASE:
            output_dir = downloads / cache_key
            path = output_dir / (acquisition.asset or "")
            if path.is_file():
                verify_sha256(path, acquisition.sha256)
                return AcquiredArtifact(
                    tool.name,
                    path,
                    f"{acquisition.repository}@{acquisition.release}:{acquisition.asset}",
                    cache_key,
                )

            _resolve_github_asset(tool, runner)
            temporary = downloads / f".{cache_key}.tmp"
            shutil.rmtree(temporary, ignore_errors=True)
            temporary.mkdir(parents=True)
            runner.run(
                [
                    "gh",
                    "release",
                    "download",
                    acquisition.release or "",
                    "--repo",
                    acquisition.repository or "",
                    "--pattern",
                    acquisition.asset or "",
                    "--dir",
                    str(temporary),
                ]
            )
            temporary_path = temporary / (acquisition.asset or "")
            if not temporary_path.is_file():
                raise AcquisitionError(
                    f"GitHub release download did not produce {temporary_path}"
                )
            verify_sha256(temporary_path, acquisition.sha256)
            shutil.rmtree(output_dir, ignore_errors=True)
            os.replace(temporary, output_dir)
            return AcquiredArtifact(
                tool.name,
                path,
                f"{acquisition.repository}@{acquisition.release}:{acquisition.asset}",
                cache_key,
            )

        case AcquisitionKind.HTTP_ARCHIVE:
            filename = Path(acquisition.url or "").name
            output_dir = downloads / cache_key
            path = output_dir / filename
            if not path.exists():
                output_dir.mkdir(parents=True, exist_ok=True)
                temporary = output_dir / f".{filename}.tmp"
                temporary.unlink(missing_ok=True)
                with urllib.request.urlopen(acquisition.url or "") as response:
                    with temporary.open("wb") as output:
                        shutil.copyfileobj(response, output)
                verify_sha256(temporary, acquisition.sha256)
                os.replace(temporary, path)
            verify_sha256(path, acquisition.sha256)
            return AcquiredArtifact(
                tool.name, path, acquisition.url or "", cache_key
            )

        case AcquisitionKind.GIT_CHECKOUT:
            destination = sources / cache_key
            expected = acquisition.revision or ""
            if _cached_git_revision(destination, runner) == expected:
                return AcquiredArtifact(
                    tool.name,
                    destination,
                    f"{acquisition.repository}@{expected}",
                    cache_key,
                )

            temporary = sources / f".{cache_key}.tmp"
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
                    expected,
                ],
                cwd=temporary,
            )
            runner.run(
                ["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"],
                cwd=temporary,
            )
            actual = _cached_git_revision(temporary, runner)
            if actual != expected:
                raise AcquisitionError(
                    f"resolved git revision {actual}, expected {expected}"
                )
            shutil.rmtree(destination, ignore_errors=True)
            os.replace(temporary, destination)
            return AcquiredArtifact(
                tool.name,
                destination,
                f"{acquisition.repository}@{actual}",
                cache_key,
            )

        case AcquisitionKind.GO_MODULE:
            version = acquisition.version or ""
            return AcquiredArtifact(
                tool.name,
                None,
                f"{acquisition.module}@{version}",
                cache_key,
            )

        case AcquisitionKind.LOCAL_SOURCE:
            path = toolbox_root / (acquisition.path or "")
            if not path.exists():
                raise AcquisitionError(
                    f"local source for {tool.name} does not exist: {path}"
                )
            identity = f"local:{acquisition.path}#sha256:{sha256_tree(path)}"
            return AcquiredArtifact(
                tool.name,
                path,
                identity,
                f"local-source-{hashlib.sha256(identity.encode()).hexdigest()}",
            )

    raise AssertionError(f"unhandled acquisition kind: {acquisition.kind}")

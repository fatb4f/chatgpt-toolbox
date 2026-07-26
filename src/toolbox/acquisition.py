from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence
import hashlib
import json
import shutil
import subprocess
import urllib.request

from toolbox.model import AcquisitionKind, ToolSpec


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()



def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + path.readlink().as_posix().encode("utf-8") + b"\0")
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
        raise AcquisitionError(f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}")


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
            f"release {acquisition.repository}@{acquisition.release} does not contain exactly one "
            f"asset named {acquisition.asset!r}"
        )


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

    match acquisition.kind:
        case AcquisitionKind.GITHUB_RELEASE:
            _resolve_github_asset(tool, runner)
            output_dir = downloads / tool.name
            shutil.rmtree(output_dir, ignore_errors=True)
            output_dir.mkdir(parents=True)
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
                    str(output_dir),
                ]
            )
            path = output_dir / (acquisition.asset or "")
            if not path.is_file():
                raise AcquisitionError(f"GitHub release download did not produce {path}")
            verify_sha256(path, acquisition.sha256)
            return AcquiredArtifact(tool.name, path, f"{acquisition.repository}@{acquisition.release}:{acquisition.asset}")

        case AcquisitionKind.HTTP_ARCHIVE:
            filename = Path(acquisition.url or "").name
            path = downloads / tool.name / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                with urllib.request.urlopen(acquisition.url or "") as response, path.open("wb") as output:
                    shutil.copyfileobj(response, output)
            verify_sha256(path, acquisition.sha256)
            return AcquiredArtifact(tool.name, path, acquisition.url or "")

        case AcquisitionKind.GIT_CHECKOUT:
            destination = sources / tool.name
            shutil.rmtree(destination, ignore_errors=True)
            destination.mkdir(parents=True)
            runner.run(["git", "init", "--quiet"], cwd=destination)
            runner.run(["git", "remote", "add", "origin", acquisition.repository or ""], cwd=destination)
            runner.run(["git", "fetch", "--quiet", "--depth", "1", "origin", acquisition.revision or ""], cwd=destination)
            runner.run(["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], cwd=destination)
            completed = runner.run(["git", "rev-parse", "HEAD"], cwd=destination, capture_output=True)
            actual = completed.stdout.strip()
            if actual != acquisition.revision:
                raise AcquisitionError(f"resolved git revision {actual}, expected {acquisition.revision}")
            return AcquiredArtifact(tool.name, destination, f"{acquisition.repository}@{actual}")

        case AcquisitionKind.GO_MODULE:
            version = acquisition.version or ""
            return AcquiredArtifact(tool.name, None, f"{acquisition.module}@{version}")

        case AcquisitionKind.LOCAL_SOURCE:
            path = toolbox_root / (acquisition.path or "")
            if not path.exists():
                raise AcquisitionError(f"local source for {tool.name} does not exist: {path}")
            return AcquiredArtifact(tool.name, path, f"local:{acquisition.path}#sha256:{sha256_tree(path)}")

    raise AssertionError(f"unhandled acquisition kind: {acquisition.kind}")

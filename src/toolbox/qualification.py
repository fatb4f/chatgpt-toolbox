from __future__ import annotations

from pathlib import Path
from typing import Mapping
import hashlib
import json
import os
import re
import shutil

from toolbox.acquisition import Runner, sha256_file
from toolbox.model import PythonProjectSpec
from toolbox.packaging import write_json

_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class QualificationError(RuntimeError):
    pass


def program_environment(prefix: Path) -> dict[str, str]:
    resolved = prefix.resolve()
    return {
        **os.environ,
        "PATH": os.pathsep.join((str(resolved / "bin"), os.environ.get("PATH", ""))),
        "GOROOT": str(resolved / "libexec" / "go"),
        "GOTOOLCHAIN": "local",
        "GOBIN": str(resolved / "bin"),
    }


def qualify_context_git_hydrator(
    *,
    prefix: Path,
    work_root: Path,
    runner: Runner,
    expected_digest: str,
) -> dict[str, object]:
    if not _SHA256_DIGEST_RE.fullmatch(expected_digest):
        raise QualificationError("context-git-hydrator expected digest is invalid")

    shutil.rmtree(work_root, ignore_errors=True)
    repository = work_root / "repository"
    repository.mkdir(parents=True)
    runner.run(["git", "init", "--quiet"], cwd=repository)
    runner.run(["git", "config", "commit.gpgsign", "false"], cwd=repository)
    runner.run(["git", "config", "tag.gpgsign", "false"], cwd=repository)
    runner.run(["git", "config", "user.name", "Toolbox Qualification"], cwd=repository)
    runner.run(
        ["git", "config", "user.email", "toolbox-qualification@example.invalid"],
        cwd=repository,
    )
    (repository / "fixture.txt").write_text("qualified\n", encoding="utf-8")
    runner.run(["git", "add", "fixture.txt"], cwd=repository)
    environment = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
    }
    runner.run(
        ["git", "commit", "--quiet", "--no-gpg-sign", "-m", "qualification fixture"],
        cwd=repository,
        env=environment,
    )
    completed = runner.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, capture_output=True
    )
    revision = completed.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
        raise QualificationError("qualification fixture produced an invalid revision")

    request = work_root / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema": "kernel.git-committed-snapshot-request.v0",
                "repositoryID": "repo.toolbox-qualification",
                "path": str(repository.resolve()),
                "revision": revision,
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    completed = runner.run(
        [
            str((prefix / "bin/context-git-hydrator").resolve()),
            "committed",
            "--request",
            str(request.resolve()),
        ],
        env=program_environment(prefix),
        capture_output=True,
    )
    try:
        observation = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise QualificationError(
            "context-git-hydrator emitted invalid committed observation JSON"
        ) from error

    if observation.get("schema") != "kernel.git-committed-snapshot-observation.v0":
        raise QualificationError("context-git-hydrator emitted the wrong schema")
    if observation.get("repositoryID") != "repo.toolbox-qualification":
        raise QualificationError("context-git-hydrator changed repository identity")
    if observation.get("requestedRevision") != revision:
        raise QualificationError(
            "context-git-hydrator did not canonicalize the fixture revision"
        )
    if observation.get("resolvedRevision", {}).get("hex") != revision:
        raise QualificationError(
            "context-git-hydrator resolved the wrong fixture revision"
        )
    if observation.get("hydrator", {}).get("digest") != expected_digest:
        raise QualificationError(
            "context-git-hydrator provenance digest is not build-bound"
        )
    if not any(
        occurrence.get("path") == "fixture.txt"
        and occurrence.get("kind") == "blob"
        for occurrence in observation.get("occurrences", [])
    ):
        raise QualificationError("context-git-hydrator omitted the committed fixture")

    report = {
        "schema": "toolbox.program-qualification.v1",
        "program": "context-git-hydrator",
        "status": "passed",
        "sourceDigest": expected_digest,
        "fixtureRevision": revision,
        "observationSha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
    }
    return report


def qualify_cue_repository_source(
    *,
    source: Path,
    prefix: Path,
    work_root: Path,
    runner: Runner,
) -> dict[str, object]:
    script = source / ".github" / "scripts" / "cue-contract-test.sh"
    if not script.is_file():
        raise QualificationError(f"repository CUE qualification is missing: {script}")
    shutil.rmtree(work_root, ignore_errors=True)
    work_root.mkdir(parents=True)
    environment = {
        **program_environment(prefix),
        "RUNNER_TEMP": str((work_root / "runner-temp").resolve()),
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
    }
    runner.run(["bash", str(script.resolve())], cwd=source, env=environment)
    report = {
        "schema": "toolbox.repository-source-qualification.v1",
        "kind": "cue-contract-suite",
        "status": "passed",
        "script": ".github/scripts/cue-contract-test.sh",
    }
    return report


def materialize_python_closure(
    *,
    source: Path,
    project: PythonProjectSpec,
    prefix: Path,
    stage: Path,
    work_root: Path,
    runner: Runner,
) -> dict[str, object]:
    project_root = source / project.project_path
    lock_path = project_root / project.lock_path
    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file() or not lock_path.is_file():
        raise QualificationError(
            f"Python project authority is incomplete under {project_root}"
        )
    cache = stage / project.cache_path
    metadata = stage / "share" / "dotfiles" / "python" / "project"
    metadata.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pyproject, metadata / "pyproject.toml")
    shutil.copy2(lock_path, metadata / "uv.lock")

    shutil.rmtree(work_root, ignore_errors=True)
    work_root.mkdir(parents=True)
    environment_path = work_root / "venv"
    environment = {
        **program_environment(prefix),
        "UV_CACHE_DIR": str(cache.resolve()),
        "UV_PROJECT_ENVIRONMENT": str(environment_path.resolve()),
        "UV_PYTHON": str((prefix / "bin/python3").resolve()),
        "UV_NO_PROGRESS": "1",
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
    }
    argv = [
        str((prefix / "bin/uv").resolve()),
        "sync",
        "--frozen",
        "--project",
        str(project_root.resolve()),
    ]
    for group in project.groups:
        argv.extend(("--group", group))
    runner.run(argv, env=environment)
    if not environment_path.is_dir():
        raise QualificationError("uv sync did not create a qualification environment")

    scripts: dict[str, str] = {}
    try:
        import tomllib

        document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        scripts = dict(document.get("project", {}).get("scripts", {}))
    except (OSError, ValueError, TypeError) as error:
        raise QualificationError("failed to read Python project scripts") from error

    bin_dir = stage / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(scripts):
        wrapper = bin_dir / name
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'root=$(CDPATH=\'\' cd -- "$(dirname -- "$0")/.." && pwd)\n'
            f'exec "$root/{project.environment_path}/bin/{name}" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)

    report = {
        "schema": "toolbox.python-project-qualification.v1",
        "status": "passed",
        "project": project.project_path,
        "pyprojectSha256": sha256_file(pyproject),
        "lockSha256": sha256_file(lock_path),
        "groups": list(project.groups),
        "scripts": sorted(scripts),
    }
    return report


def write_qualification_report(path: Path, report: Mapping[str, object]) -> Path:
    return write_json(path, report)

from __future__ import annotations

from pathlib import Path
from typing import Mapping
import json
import os
import re
import shutil

from toolbox.acquisition import Runner

_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class QualificationError(RuntimeError):
    pass


def _program_environment(prefix: Path) -> dict[str, str]:
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
) -> None:
    if not _SHA256_DIGEST_RE.fullmatch(expected_digest):
        raise QualificationError("context-git-hydrator expected digest is invalid")

    shutil.rmtree(work_root, ignore_errors=True)
    repository = work_root / "repository"
    repository.mkdir(parents=True)
    runner.run(["git", "init", "--quiet"], cwd=repository)
    runner.run(["git", "config", "user.name", "Toolbox Qualification"], cwd=repository)
    runner.run(
        ["git", "config", "user.email", "toolbox-qualification@example.invalid"],
        cwd=repository,
    )
    (repository / "fixture.txt").write_text("qualified\n", encoding="utf-8")
    runner.run(["git", "add", "fixture.txt"], cwd=repository)
    runner.run(["git", "commit", "--quiet", "-m", "qualification fixture"], cwd=repository)
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
        env=_program_environment(prefix),
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
        raise QualificationError("context-git-hydrator did not canonicalize the fixture revision")
    if observation.get("resolvedRevision", {}).get("hex") != revision:
        raise QualificationError("context-git-hydrator resolved the wrong fixture revision")
    if observation.get("hydrator", {}).get("digest") != expected_digest:
        raise QualificationError("context-git-hydrator provenance digest is not build-bound")
    if not any(
        occurrence.get("path") == "fixture.txt"
        and occurrence.get("kind") == "blob"
        for occurrence in observation.get("occurrences", [])
    ):
        raise QualificationError("context-git-hydrator omitted the committed fixture")


def qualify_programs(
    programs: tuple[str, ...],
    *,
    prefix: Path,
    work_root: Path,
    runner: Runner,
    source_digests: Mapping[str, str],
) -> None:
    for program in programs:
        if program == "context-git-hydrator":
            try:
                expected_digest = source_digests[program]
            except KeyError as error:
                raise QualificationError(
                    "context-git-hydrator has no resolved source digest"
                ) from error
            qualify_context_git_hydrator(
                prefix=prefix,
                work_root=work_root / program,
                runner=runner,
                expected_digest=expected_digest,
            )

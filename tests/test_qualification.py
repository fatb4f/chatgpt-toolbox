from pathlib import Path
import json
import subprocess

from toolbox.qualification import qualify_context_git_hydrator


class FakeRunner:
    def __init__(self, digest: str) -> None:
        self.digest = digest
        self.calls = []

    def run(self, argv, *, cwd=None, env=None, capture_output=False):
        command = tuple(argv)
        self.calls.append(command)
        if command[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(command, 0, "a" * 40 + "\n", "")
        if command and command[0].endswith("context-git-hydrator"):
            payload = {
                "schema": "kernel.git-committed-snapshot-observation.v0",
                "repositoryID": "repo.toolbox-qualification",
                "requestedRevision": "a" * 40,
                "resolvedRevision": {"format": "sha1", "hex": "a" * 40},
                "rootTree": {"format": "sha1", "hex": "b" * 40},
                "occurrences": [
                    {
                        "path": "fixture.txt",
                        "mode": "100644",
                        "kind": "blob",
                        "objectID": {"format": "sha1", "hex": "c" * 40},
                        "size": 10,
                    }
                ],
                "hydrator": {
                    "identity": "context-git-hydrator",
                    "digest": self.digest,
                },
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_hydrator_qualification_executes_real_committed_surface(tmp_path: Path) -> None:
    digest = "sha256:" + "d" * 64
    binary = tmp_path / "prefix/bin/context-git-hydrator"
    binary.parent.mkdir(parents=True)
    binary.write_text("fixture", encoding="utf-8")
    runner = FakeRunner(digest)

    report = qualify_context_git_hydrator(
        prefix=tmp_path / "prefix",
        work_root=tmp_path / "work",
        runner=runner,
        expected_digest=digest,
    )

    assert report["status"] == "passed"
    assert report["sourceDigest"] == digest
    commit_call = next(call for call in runner.calls if call[:2] == ("git", "commit"))
    assert "--no-gpg-sign" in commit_call
    hydrator_call = next(
        call for call in runner.calls if call and call[0].endswith("context-git-hydrator")
    )
    assert hydrator_call[1] == "committed"

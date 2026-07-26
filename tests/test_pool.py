from __future__ import annotations

from pathlib import Path
import io
import subprocess
import tarfile

from toolbox.acquisition import AcquiredArtifact
from toolbox.model import AcquisitionKind, AcquisitionSpec, InstallEntry, ToolSpec
from toolbox.pool import ensure_tool_projection, projection_cache_key

TARGET = "x86_64-unknown-linux-gnu"


class NoopRunner:
    def run(self, argv, *, cwd=None, env=None, capture_output=False):
        return subprocess.CompletedProcess(tuple(argv), 0, "", "")


def archive_tool(tmp_path: Path) -> tuple[ToolSpec, AcquiredArtifact]:
    archive = tmp_path / "tool.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        payload = b"tool\n"
        info = tarfile.TarInfo("tool")
        info.mode = 0o755
        info.size = len(payload)
        stream.addfile(info, io.BytesIO(payload))
    tool = ToolSpec(
        name="example",
        version="1.0.0",
        target=TARGET,
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.HTTP_ARCHIVE,
            url="https://example.invalid/tool.tar.gz",
            sha256="a" * 64,
        ),
        install=(InstallEntry("tool", "bin/tool"),),
    )
    return tool, AcquiredArtifact("example", archive, "archive", "archive-key")


def test_projection_is_built_once_and_reused(tmp_path: Path) -> None:
    tool, artifact = archive_tool(tmp_path)
    arguments = dict(
        dependency_keys={},
        projections_root=tmp_path / "projections",
        builds_root=tmp_path / "builds",
        toolchain_prefix=tmp_path / "toolchain",
        runner=NoopRunner(),
    )
    first = ensure_tool_projection(tool, artifact, **arguments)
    second = ensure_tool_projection(tool, artifact, **arguments)

    assert not first.reused
    assert second.reused
    assert first.key == second.key
    assert (second.root / "bin/tool").read_text() == "tool\n"


def test_projection_key_includes_dependency_projections(tmp_path: Path) -> None:
    tool, artifact = archive_tool(tmp_path)
    first = projection_cache_key(tool, artifact, {"go": "one"})
    second = projection_cache_key(tool, artifact, {"go": "two"})
    assert first != second

from pathlib import Path
import io
import tarfile

import pytest

from toolbox.staging import StagingError, extract_archive, stage_projection


def test_tar_extraction_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo("../escape")
        payload = b"bad"
        info.size = len(payload)
        stream.addfile(info, io.BytesIO(payload))
    with pytest.raises(StagingError, match="escapes extraction root"):
        extract_archive(archive, tmp_path / "out")


def test_projection_files_are_copied_into_isolated_composition(tmp_path: Path) -> None:
    projection = tmp_path / "projection"
    prefix = tmp_path / "prefix"
    source = projection / "bin/tool"
    source.parent.mkdir(parents=True)
    source.write_text("tool\n", encoding="utf-8")
    source.chmod(0o755)

    stage_projection(projection, prefix)

    destination = prefix / "bin/tool"
    destination.write_text("changed\n", encoding="utf-8")
    assert source.read_text(encoding="utf-8") == "tool\n"


def test_projection_conflicts_are_rejected(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    prefix = tmp_path / "prefix"
    (first / "bin").mkdir(parents=True)
    (second / "bin").mkdir(parents=True)
    (first / "bin/tool").write_text("one", encoding="utf-8")
    (second / "bin/tool").write_text("two", encoding="utf-8")
    stage_projection(first, prefix)
    with pytest.raises(StagingError, match="conflict"):
        stage_projection(second, prefix)

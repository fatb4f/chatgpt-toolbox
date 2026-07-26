from pathlib import Path
import io
import tarfile

import pytest

from toolbox.staging import StagingError, extract_archive, write_activation


def test_activation_enforces_staged_go_toolchain(tmp_path: Path) -> None:
    activation = write_activation(tmp_path)
    content = activation.read_text(encoding="utf-8")
    assert 'export GOROOT="$TOOLBOX_ROOT/libexec/go"' in content
    assert "export GOTOOLCHAIN=local" in content
    assert 'export GOBIN="$TOOLBOX_ROOT/bin"' in content


def test_tar_extraction_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo("../escape")
        payload = b"bad"
        info.size = len(payload)
        stream.addfile(info, io.BytesIO(payload))
    with pytest.raises(StagingError, match="escapes extraction root"):
        extract_archive(archive, tmp_path / "out")

from pathlib import Path

from toolbox.acquisition import sha256_file
from toolbox.packaging import create_deterministic_archive
from toolbox.staging import write_activation


def test_archive_is_byte_deterministic(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    executable = prefix / "bin" / "tool"
    executable.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    executable.chmod(0o755)
    (prefix / "share").mkdir()
    (prefix / "share" / "data.txt").write_text("payload\n", encoding="utf-8")
    write_activation(prefix)

    first = create_deterministic_archive(prefix, tmp_path / "first.tar.gz", "bundle")
    second = create_deterministic_archive(prefix, tmp_path / "second.tar.gz", "bundle")
    assert sha256_file(first) == sha256_file(second)

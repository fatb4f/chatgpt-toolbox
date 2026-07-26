from pathlib import Path

from toolbox.builders import staged_go_environment


def test_staged_go_environment_forces_bundle_compiler_and_external_cache(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    cache = tmp_path / "workspace" / "go-cache"
    environment = staged_go_environment(prefix, cache)
    assert environment["GOROOT"] == str(prefix / "libexec" / "go")
    assert environment["GOTOOLCHAIN"] == "local"
    assert environment["GOBIN"] == str(prefix / "bin")
    assert environment["PATH"].split(":")[:2] == [
        str(prefix / "libexec" / "go" / "bin"),
        str(prefix / "bin"),
    ]
    assert environment["GOPATH"] == str(cache / "gopath")
    assert environment["GOMODCACHE"] == str(cache / "gopath" / "pkg" / "mod")
    assert environment["GOCACHE"] == str(cache / "build")
    assert not Path(environment["GOCACHE"]).is_relative_to(prefix)

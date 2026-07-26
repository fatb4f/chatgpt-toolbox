from __future__ import annotations

from pathlib import Path
from typing import Mapping
import hashlib
import os
import shutil

from toolbox.acquisition import AcquiredArtifact, Runner
from toolbox.model import AcquisitionKind, BuildKind, BuildSpec, ToolSpec
from toolbox.staging import extract_archive, stage_entries, stage_links


class BuildError(RuntimeError):
    pass


def staged_go_environment(
    toolchain_prefix: Path,
    output_prefix: Path,
    cache_root: Path | None = None,
) -> dict[str, str]:
    """Build with the pooled Go toolchain while emitting into one projection.

    The two-argument form retains the original behavior, where the toolchain and
    output prefixes are the same path.
    """
    if cache_root is None:
        cache_root = output_prefix
        output_prefix = toolchain_prefix
    toolchain_prefix = toolchain_prefix.resolve()
    output_prefix = output_prefix.resolve()
    cache_root = cache_root.resolve()
    goroot = toolchain_prefix / "libexec" / "go"
    path = os.pathsep.join(
        (
            str(goroot / "bin"),
            str(toolchain_prefix / "bin"),
            str(output_prefix / "bin"),
            os.environ.get("PATH", ""),
        )
    )
    gopath = cache_root / "gopath"
    return {
        **os.environ,
        "GOROOT": str(goroot),
        "GOTOOLCHAIN": "local",
        "GOBIN": str(output_prefix / "bin"),
        "PATH": path,
        "CGO_ENABLED": "0",
        "GOPATH": str(gopath),
        "GOMODCACHE": str(gopath / "pkg" / "mod"),
        "GOCACHE": str(cache_root / "build"),
    }


def _merged_environment(
    base: Mapping[str, str], overlay: Mapping[str, str]
) -> dict[str, str]:
    result = dict(base)
    result.update(overlay)
    return result


def go_source_digest(source_root: Path) -> str:
    """Hash the Go source authority exactly as the hydrator qualification does."""
    paths = sorted(
        (
            path
            for path in source_root.rglob("*")
            if path.is_file()
            and (path.suffix == ".go" or path.name in {"go.mod", "go.sum"})
        ),
        key=lambda path: path.relative_to(source_root).as_posix(),
    )
    if not paths:
        raise BuildError(f"Go source digest has no admitted files under {source_root}")
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(source_root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def go_build_arguments(
    build: BuildSpec, *, source_root: Path | None = None
) -> list[str]:
    arguments: list[str] = []
    if build.trimpath:
        arguments.append("-trimpath")
    arguments.append(f"-buildvcs={'true' if build.build_vcs else 'false'}")
    ldflags = list(build.ldflags)
    if build.source_digest_symbol is not None:
        if source_root is None:
            raise BuildError("source digest injection requires a Go source root")
        ldflags.append(
            f"-X {build.source_digest_symbol}={go_source_digest(source_root)}"
        )
    if ldflags:
        arguments.append(f"-ldflags={' '.join(ldflags)}")
    return arguments


def build_and_stage_tool(
    tool: ToolSpec,
    artifact: AcquiredArtifact,
    *,
    prefix: Path,
    build_root: Path,
    runner: Runner,
    toolchain_prefix: Path | None = None,
    go_cache_root: Path | None = None,
) -> None:
    build_root.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)
    toolchain = toolchain_prefix or prefix
    shared_go_cache = go_cache_root or build_root / "go-cache"

    match tool.build.kind:
        case BuildKind.NONE:
            if artifact.path is None:
                return
            extracted = build_root / "extracted"
            shutil.rmtree(extracted, ignore_errors=True)
            extract_archive(artifact.path, extracted)
            stage_entries(extracted, prefix, tool.install)
            stage_links(prefix, tool.links)

        case BuildKind.GO_COMMAND:
            environment = _merged_environment(
                staged_go_environment(toolchain, prefix, shared_go_cache),
                tool.build.environment,
            )
            output = prefix / (tool.build.output or "")
            output.parent.mkdir(parents=True, exist_ok=True)
            if tool.acquisition.kind is AcquisitionKind.GO_MODULE:
                flags = go_build_arguments(tool.build)
                module = tool.acquisition.module or ""
                version = tool.acquisition.version or ""
                package = tool.build.package or module
                if package == module:
                    install_target = f"{module}@{version}"
                elif package.startswith(module + "/"):
                    install_target = f"{package}@{version}"
                else:
                    raise BuildError(
                        f"Go package {package!r} is outside module {module!r}"
                    )
                runner.run(["go", "install", *flags, install_target], env=environment)
                produced = prefix / "bin" / Path(package).name
                if produced != output:
                    if not produced.exists():
                        raise BuildError(f"go install did not produce {produced}")
                    shutil.move(produced, output)
            else:
                if artifact.path is None:
                    raise BuildError(f"Go source path missing for {tool.name}")
                source = artifact.path / tool.build.source_subdir
                flags = go_build_arguments(tool.build, source_root=source)
                runner.run(
                    [
                        "go",
                        "build",
                        *flags,
                        "-o",
                        str(output.resolve()),
                        tool.build.package or ".",
                    ],
                    cwd=source,
                    env=environment,
                )
            stage_links(prefix, tool.links)

        case BuildKind.MAKE_COMMAND:
            if artifact.path is None:
                raise BuildError(f"make source archive missing for {tool.name}")
            source = build_root / "source"
            shutil.rmtree(source, ignore_errors=True)
            extract_archive(artifact.path, source)
            children = [path for path in source.iterdir() if path.is_dir()]
            working = children[0] if len(children) == 1 else source
            environment = _merged_environment(os.environ, tool.build.environment)
            install_prefix = prefix.resolve()
            runner.run(
                ["make", tool.build.make_target or ""], cwd=working, env=environment
            )
            runner.run(
                [
                    "make",
                    tool.build.install_target or "",
                    f"INSTALL_TOP={install_prefix}",
                ],
                cwd=working,
                env=environment,
            )
            stage_links(prefix, tool.links)

        case _:
            raise AssertionError(f"unhandled build kind: {tool.build.kind}")

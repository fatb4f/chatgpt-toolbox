from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping
import re

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_TARGET_RE = re.compile(r"^[A-Za-z0-9_.+-]+(?:-[A-Za-z0-9_.+-]+)+$")


class DescriptorError(ValueError):
    pass


class AcquisitionKind(StrEnum):
    GITHUB_RELEASE = "github-release"
    HTTP_ARCHIVE = "http-archive"
    GIT_CHECKOUT = "git-checkout"
    GO_MODULE = "go-module"
    LOCAL_SOURCE = "local-source"


class BuildKind(StrEnum):
    NONE = "none"
    GO_COMMAND = "go-command"
    MAKE_COMMAND = "make-command"


class InstallEntryKind(StrEnum):
    AUTO = "auto"
    FILE = "file"
    TREE = "tree"


class ToolRole(StrEnum):
    BUILD = "build"
    RUNTIME = "runtime"
    MODULE = "module"
    PROGRAM = "program"


def _require_nonempty(label: str, value: str | None) -> str:
    if value is None or not value.strip():
        raise DescriptorError(f"{label} must be non-empty")
    return value


def _validate_relative_posix(label: str, value: str, *, allow_dot: bool = True) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise DescriptorError(f"{label} must be a normalized relative path: {value!r}")
    if not allow_dot and value in {"", "."}:
        raise DescriptorError(f"{label} must not be the current directory")


@dataclass(frozen=True, slots=True)
class AcquisitionSpec:
    kind: AcquisitionKind
    repository: str | None = None
    release: str | None = None
    asset: str | None = None
    sha256: str | None = None
    url: str | None = None
    revision: str | None = None
    module: str | None = None
    version: str | None = None
    path: str | None = None

    def __post_init__(self) -> None:
        if self.sha256 is not None and not _SHA256_RE.fullmatch(self.sha256):
            raise DescriptorError("sha256 must contain exactly 64 lowercase hexadecimal characters")

        match self.kind:
            case AcquisitionKind.GITHUB_RELEASE:
                repository = _require_nonempty("repository", self.repository)
                if repository.count("/") != 1:
                    raise DescriptorError("GitHub repository must use owner/repository form")
                _require_nonempty("release", self.release)
                _require_nonempty("asset", self.asset)
            case AcquisitionKind.HTTP_ARCHIVE:
                url = _require_nonempty("url", self.url)
                if not url.startswith("https://"):
                    raise DescriptorError("HTTP archive URL must use HTTPS")
            case AcquisitionKind.GIT_CHECKOUT:
                repository = _require_nonempty("repository", self.repository)
                if not (repository.startswith("https://") or repository.startswith("ssh://")):
                    raise DescriptorError("Git checkout repository must use HTTPS or SSH")
                _require_nonempty("revision", self.revision)
            case AcquisitionKind.GO_MODULE:
                _require_nonempty("module", self.module)
            case AcquisitionKind.LOCAL_SOURCE:
                path = _require_nonempty("path", self.path)
                _validate_relative_posix("local source path", path)

    @property
    def lock_defects(self) -> tuple[str, ...]:
        defects: list[str] = []
        if self.kind in {AcquisitionKind.GITHUB_RELEASE, AcquisitionKind.HTTP_ARCHIVE}:
            if self.sha256 is None:
                defects.append("missing sha256")
        elif self.kind is AcquisitionKind.GIT_CHECKOUT:
            revision = self.revision or ""
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                defects.append("git revision is not a full 40-character commit")
        elif self.kind is AcquisitionKind.GO_MODULE:
            if self.version is None:
                defects.append("missing Go module version")
            elif self.version in {"latest", "master", "main"}:
                defects.append("Go module version is mutable")
        return tuple(defects)


@dataclass(frozen=True, slots=True)
class BuildSpec:
    kind: BuildKind = BuildKind.NONE
    requires: tuple[str, ...] = ()
    package: str | None = None
    output: str | None = None
    source_subdir: str = "."
    make_target: str | None = None
    install_target: str | None = None
    environment: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        for dependency in self.requires:
            if not _NAME_RE.fullmatch(dependency):
                raise DescriptorError(f"invalid build dependency name: {dependency!r}")
        _validate_relative_posix("source_subdir", self.source_subdir)

        match self.kind:
            case BuildKind.NONE:
                if self.package or self.output or self.make_target or self.install_target:
                    raise DescriptorError("no-build specifications cannot declare build commands")
            case BuildKind.GO_COMMAND:
                _require_nonempty("Go package", self.package)
                output = _require_nonempty("Go output", self.output)
                _validate_relative_posix("Go output", output, allow_dot=False)
            case BuildKind.MAKE_COMMAND:
                _require_nonempty("make target", self.make_target)
                _require_nonempty("make install target", self.install_target)


@dataclass(frozen=True, slots=True)
class InstallEntry:
    source: str
    destination: str
    kind: InstallEntryKind = InstallEntryKind.AUTO

    def __post_init__(self) -> None:
        _validate_relative_posix("install source", self.source)
        _validate_relative_posix("install destination", self.destination)


@dataclass(frozen=True, slots=True)
class LinkSpec:
    destination: str
    target: str

    def __post_init__(self) -> None:
        _validate_relative_posix("link destination", self.destination, allow_dot=False)
        if PurePosixPath(self.target).is_absolute():
            raise DescriptorError("link target must remain relative to the bundle")


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    version: str
    target: str
    acquisition: AcquisitionSpec
    build: BuildSpec = field(default_factory=BuildSpec)
    install: tuple[InstallEntry, ...] = ()
    links: tuple[LinkSpec, ...] = ()
    roles: frozenset[ToolRole] = frozenset({ToolRole.RUNTIME})
    dependencies: tuple[str, ...] = ()
    probes: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        if not _NAME_RE.fullmatch(self.name):
            raise DescriptorError(f"invalid tool name: {self.name!r}")
        _require_nonempty("version", self.version)
        if not _TARGET_RE.fullmatch(self.target):
            raise DescriptorError(f"invalid target triple: {self.target!r}")
        for dependency in self.dependencies:
            if not _NAME_RE.fullmatch(dependency):
                raise DescriptorError(f"invalid dependency name: {dependency!r}")
        if self.acquisition.kind is AcquisitionKind.GO_MODULE and self.install:
            raise DescriptorError("go-module descriptors do not directly install archive entries")
        for probe in self.probes:
            if not probe or any(not part for part in probe):
                raise DescriptorError("version probes must be non-empty argv tuples")

    @property
    def requires(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.dependencies, *self.build.requires)))

    @property
    def lock_defects(self) -> tuple[str, ...]:
        return tuple(f"{self.name}: {defect}" for defect in self.acquisition.lock_defects)


@dataclass(frozen=True, slots=True)
class RepositorySpec:
    name: str
    root: Path
    target: str
    python_group: str
    tools: tuple[str, ...]
    programs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _NAME_RE.fullmatch(self.name):
            raise DescriptorError(f"invalid repository name: {self.name!r}")
        if self.root.is_absolute():
            raise DescriptorError("repository root must be relative to the toolbox root")
        if not _TARGET_RE.fullmatch(self.target):
            raise DescriptorError(f"invalid target triple: {self.target!r}")
        _require_nonempty("python_group", self.python_group)
        if not self.tools:
            raise DescriptorError("repository must select at least one tool")
        for name in (*self.tools, *self.programs):
            if not _NAME_RE.fullmatch(name):
                raise DescriptorError(f"invalid selected tool/program name: {name!r}")

    @property
    def dist_dir(self) -> Path:
        return self.root / "dist"


@dataclass(frozen=True, slots=True)
class PlanNode:
    name: str
    kind: str
    version: str
    requires: tuple[str, ...]
    roles: tuple[str, ...]
    acquisition: AcquisitionSpec
    build: BuildSpec


@dataclass(frozen=True, slots=True)
class RepositoryPlan:
    repository: str
    target: str
    python_group: str
    output: str
    nodes: tuple[PlanNode, ...]
    lock_defects: tuple[str, ...]

    @property
    def admissible(self) -> bool:
        return not self.lock_defects


@dataclass(frozen=True, slots=True)
class BundleResult:
    repository: str
    target: str
    prefix: str
    archive: str
    lockfile: str


def to_primitive(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset, set)):
        return [to_primitive(item) for item in value]
    if is_dataclass(value):
        return {descriptor.name: to_primitive(getattr(value, descriptor.name)) for descriptor in fields(value)}
    return value

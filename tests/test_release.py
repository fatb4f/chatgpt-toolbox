from pathlib import Path
import json
import shutil

from toolbox.acquisition import AcquiredArtifact, sha256_file
from toolbox.builders import ResolvedBuild
from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    PythonProjectSpec,
    RepositorySpec,
    ToolSpec,
)
from toolbox.pool import ToolProjection
from toolbox.release import ComponentRecord, publish_release

TARGET = "x86_64-unknown-linux-gnu"


def test_publish_release_emits_components_aggregate_and_manifest(tmp_path: Path) -> None:
    source_spec = AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository="https://example.invalid/repo.git",
        revision="a" * 40,
    )
    repository = RepositorySpec(
        name="sample",
        root=Path("repos/sample"),
        target=TARGET,
        python_group="sample",
        tools=("tool",),
        source=source_spec,
        python_project=PythonProjectSpec(),
    )
    tool = ToolSpec(
        name="tool",
        version="1",
        target=TARGET,
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.GO_MODULE,
            module="example.invalid/tool",
            version="v1.0.0",
        ),
        build=BuildSpec(),
    )
    artifact = AcquiredArtifact("tool", None, "module", "artifact-key")
    projection_root = tmp_path / "projection"
    projection_root.mkdir()
    projection = ToolProjection(
        key="projection-key",
        root=projection_root,
        resolved_build=ResolvedBuild(None, ()),
        reused=False,
    )
    component_root = tmp_path / "component"
    (component_root / "bin").mkdir(parents=True)
    (component_root / "bin/tool").write_text("tool\n", encoding="utf-8")
    component_archive = tmp_path / "component.tar.zst"
    from toolbox.packaging import create_deterministic_tar_zst

    create_deterministic_tar_zst(component_root, component_archive)
    specification = repository.components[0]
    component = ComponentRecord(
        specification=specification,
        key="component-key",
        root=component_root,
        archive=component_archive,
        archive_record={
            "name": "sample-native-base-linux-amd64.tar.zst",
            "size": component_archive.stat().st_size,
            "sha256": sha256_file(component_archive),
        },
        qualification={"status": "passed"},
        reused=False,
    )

    aggregate, manifest, lock, components = publish_release(
        repository=repository,
        tools=(tool,),
        artifacts={"tool": artifact},
        projections={"tool": projection},
        repository_artifact=AcquiredArtifact(
            "repository-sample", tmp_path, "source", "source-key"
        ),
        components=(component,),
        release_dir=tmp_path / "release",
        aggregate_root=tmp_path / "aggregate",
    )

    assert aggregate.name == "sample-tools-linux-amd64.tar.zst"
    assert manifest.is_file() and lock.is_file()
    assert len(components) == 1
    document = json.loads(manifest.read_text())
    assert document["components"]["native-base"]["key"] == "component-key"
    assert (manifest.parent / "install.sh").is_file()
    assert (manifest.parent / "SHA256SUMS").is_file()


def test_component_cache_reuses_qualified_archive(tmp_path: Path) -> None:
    from toolbox.model import ComponentKind, ComponentSpec
    from toolbox.release import ensure_component

    builds = 0

    def build(stage: Path):
        nonlocal builds
        builds += 1
        (stage / "bin").mkdir(parents=True)
        (stage / "bin/tool").write_text("tool\n", encoding="utf-8")
        return {"schema": "fixture", "status": "passed"}

    specification = ComponentSpec("native-base", ComponentKind.NATIVE_BASE)
    first = ensure_component(
        specification=specification,
        key_payload={"projection": "a"},
        components_root=tmp_path / "components",
        archive_name="sample-native-base-linux-amd64.tar.zst",
        manifest={"schema": "fixture", "name": "native-base"},
        build_stage=build,
    )
    second = ensure_component(
        specification=specification,
        key_payload={"projection": "a"},
        components_root=tmp_path / "components",
        archive_name="sample-native-base-linux-amd64.tar.zst",
        manifest={"schema": "fixture", "name": "native-base"},
        build_stage=build,
    )

    assert builds == 1
    assert not first.reused
    assert second.reused
    assert first.key == second.key
    assert sha256_file(first.archive) == sha256_file(second.archive)


def test_cold_and_warm_layered_publications_are_byte_identical(tmp_path: Path) -> None:
    source_spec = AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository="https://example.invalid/repo.git",
        revision="b" * 40,
    )
    repository = RepositorySpec(
        name="sample",
        root=Path("repos/sample"),
        target=TARGET,
        python_group="sample",
        tools=("tool",),
        source=source_spec,
        python_project=PythonProjectSpec(),
    )
    tool = ToolSpec(
        name="tool",
        version="1",
        target=TARGET,
        acquisition=AcquisitionSpec(
            kind=AcquisitionKind.GO_MODULE,
            module="example.invalid/tool",
            version="v1.0.0",
        ),
    )
    projection_root = tmp_path / "projection"
    projection_root.mkdir()
    projection = ToolProjection(
        key="projection-key",
        root=projection_root,
        resolved_build=ResolvedBuild(None, ()),
        reused=False,
    )
    component_root = tmp_path / "component"
    (component_root / "bin").mkdir(parents=True)
    (component_root / "bin/tool").write_text("tool\n", encoding="utf-8")
    from toolbox.packaging import create_deterministic_tar_zst

    component_archive = create_deterministic_tar_zst(
        component_root, tmp_path / "component.tar.zst"
    )
    component = ComponentRecord(
        specification=repository.components[0],
        key="component-key",
        root=component_root,
        archive=component_archive,
        archive_record={
            "name": "sample-native-base-linux-amd64.tar.zst",
            "size": component_archive.stat().st_size,
            "sha256": sha256_file(component_archive),
        },
        qualification={"status": "passed"},
        reused=False,
    )
    artifacts = {"tool": AcquiredArtifact("tool", None, "module", "artifact-key")}
    projections = {"tool": projection}
    source = AcquiredArtifact("repository-sample", tmp_path, "source", "source-key")

    digests = []
    for name in ("cold", "warm"):
        publish_release(
            repository=repository,
            tools=(tool,),
            artifacts=artifacts,
            projections=projections,
            repository_artifact=source,
            components=(component,),
            release_dir=tmp_path / name / "release",
            aggregate_root=tmp_path / name / "aggregate",
        )
        release = tmp_path / name / "release"
        digests.append(
            {
                path.relative_to(release).as_posix(): sha256_file(path)
                for path in sorted(release.iterdir())
                if path.is_file()
            }
        )
    assert digests[0] == digests[1]

from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    ToolRole,
    ToolSpec,
)

TOOLS_REVISION = "014f87ff5c01915bc90f4f11a6bb8aea3e0edbd7"
TOOLS_REPOSITORY = "https://github.com/golang/tools.git"

SPEC = ToolSpec(
    name="goimports",
    version="0.39.0+cuestrap.014f87f",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository=TOOLS_REPOSITORY,
        revision=TOOLS_REVISION,
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go",),
        package="./cmd/goimports",
        output="bin/goimports",
        build_vcs=True,
        ldflags=("-s", "-w"),
    ),
    roles=frozenset({ToolRole.RUNTIME}),
    probes=(("goimports", "-h"),),
)

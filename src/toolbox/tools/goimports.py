from toolbox.model import AcquisitionKind, AcquisitionSpec, BuildKind, BuildSpec, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="goimports",
    version="014f87f",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository="https://go.googlesource.com/tools",
        revision="014f87ff5c01915bc90f4f11a6bb8aea3e0edbd7",
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go",),
        package="./cmd/goimports",
        output="bin/goimports",
    ),
    roles=frozenset({ToolRole.RUNTIME}),
    probes=(("goimports", "-h"),),
)

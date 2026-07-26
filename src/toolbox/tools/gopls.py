from toolbox.model import AcquisitionKind, AcquisitionSpec, BuildKind, BuildSpec, ToolRole, ToolSpec

TOOLS_REVISION = "014f87ff5c01915bc90f4f11a6bb8aea3e0edbd7"
TOOLS_SOURCE = "https://github.com/golang/tools.git"

SPEC = ToolSpec(
    name="gopls",
    version="0.23.0",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository=TOOLS_SOURCE,
        revision=TOOLS_REVISION,
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go",),
        source_subdir="gopls",
        package=".",
        output="bin/gopls",
        build_vcs=True,
        ldflags=("-s", "-w"),
    ),
    roles=frozenset({ToolRole.RUNTIME}),
    probes=(("gopls", "version"),),
)

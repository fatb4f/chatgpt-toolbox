from toolbox.model import AcquisitionKind, AcquisitionSpec, BuildKind, BuildSpec, ToolRole, ToolSpec
from toolbox.tools.gopls import TOOLS_REVISION, TOOLS_SOURCE

SPEC = ToolSpec(
    name="goimports",
    version="0.39.0+cuestrap.014f87f",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository=TOOLS_SOURCE,
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
    probes=(),
)

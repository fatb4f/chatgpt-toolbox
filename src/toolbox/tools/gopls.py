from toolbox.model import AcquisitionKind, AcquisitionSpec, BuildKind, BuildSpec, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="gopls",
    version="0.23.0",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GO_MODULE,
        module="golang.org/x/tools/gopls",
        version="v0.23.0",
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go",),
        package="golang.org/x/tools/gopls",
        output="bin/gopls",
    ),
    roles=frozenset({ToolRole.RUNTIME}),
    probes=(("gopls", "version"),),
)

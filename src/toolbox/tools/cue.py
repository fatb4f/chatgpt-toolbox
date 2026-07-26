from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    ToolRole,
    ToolSpec,
)

SPEC = ToolSpec(
    name="cue",
    version="0.18.0",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GO_MODULE,
        module="cuelang.org/go",
        version="v0.18.0",
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go",),
        package="cuelang.org/go/cmd/cue",
        output="bin/cue",
    ),
    roles=frozenset({ToolRole.RUNTIME}),
    probes=(("cue", "version"),),
)

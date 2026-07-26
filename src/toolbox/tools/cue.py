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
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository="https://github.com/cue-lang/cue.git",
        revision="806821e40fae070318600a264d311517e596353b",
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go",),
        package="./cmd/cue",
        output="bin/cue",
        build_vcs=True,
        ldflags=("-s", "-w"),
    ),
    roles=frozenset({ToolRole.RUNTIME}),
    probes=(("cue", "version"),),
)

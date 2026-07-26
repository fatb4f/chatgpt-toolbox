from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    ToolRole,
    ToolSpec,
)

SPEC = ToolSpec(
    name="context-git-hydrator",
    version="repository",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.LOCAL_SOURCE,
        path="/home/_404/src/dotfiles/.codex/context-hydrators/git",
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go", "go-git"),
        package=".",
        output="bin/context-git-hydrator",
    ),
    roles=frozenset({ToolRole.PROGRAM, ToolRole.RUNTIME}),
    probes=(("gitfacts", "--version"),),
)

from toolbox.model import AcquisitionKind, AcquisitionSpec, BuildKind, BuildSpec, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="gitfacts",
    version="repository",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.LOCAL_SOURCE,
        path="repos/dotfiles/programs/gitfacts",
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go", "go-git"),
        package=".",
        output="bin/gitfacts",
    ),
    roles=frozenset({ToolRole.PROGRAM, ToolRole.RUNTIME}),
    probes=(("gitfacts", "--version"),),
)

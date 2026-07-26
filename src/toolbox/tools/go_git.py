from toolbox.model import AcquisitionKind, AcquisitionSpec, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="go-git",
    version="v5.19.1",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GO_MODULE,
        module="github.com/go-git/go-git/v5",
        version="v5.19.1",
    ),
    roles=frozenset({ToolRole.MODULE}),
)

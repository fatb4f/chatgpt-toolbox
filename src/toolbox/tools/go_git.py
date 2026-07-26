from toolbox.model import AcquisitionKind, AcquisitionSpec, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="go-git",
    version="unresolved",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GO_MODULE,
        module="github.com/go-git/go-git/v5",
        version=None,
    ),
    roles=frozenset({ToolRole.MODULE}),
)

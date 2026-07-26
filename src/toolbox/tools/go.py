from toolbox.model import AcquisitionKind, AcquisitionSpec, InstallEntry, InstallEntryKind, LinkSpec, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="go",
    version="1.26.5",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.HTTP_ARCHIVE,
        url="https://go.dev/dl/go1.26.5.linux-amd64.tar.gz",
        sha256="5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053",
    ),
    install=(InstallEntry("go", "libexec/go", InstallEntryKind.TREE),),
    links=(
        LinkSpec("bin/go", "../libexec/go/bin/go"),
        LinkSpec("bin/gofmt", "../libexec/go/bin/gofmt"),
    ),
    roles=frozenset({ToolRole.BUILD, ToolRole.RUNTIME}),
    probes=(("go", "version"),),
)

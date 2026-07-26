from toolbox.model import AcquisitionKind, AcquisitionSpec, InstallEntry, InstallEntryKind, LinkSpec, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="luals",
    version="3.18.2",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GITHUB_RELEASE,
        repository="LuaLS/lua-language-server",
        release="3.18.2",
        asset="lua-language-server-3.18.2-linux-x64.tar.gz",
        sha256="ca71415dd19f19e30aaa35a4915aefca9fdb5fec31b98331cc3d77f778d539c5",
    ),
    install=(InstallEntry(".", "libexec/lua-language-server", InstallEntryKind.TREE),),
    links=(LinkSpec("bin/lua-language-server", "../libexec/lua-language-server/bin/lua-language-server"),),
    roles=frozenset({ToolRole.RUNTIME}),
    dependencies=("lua",),
    probes=(("lua-language-server", "--version"),),
)

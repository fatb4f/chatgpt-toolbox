from toolbox.model import AcquisitionKind, AcquisitionSpec, BuildKind, BuildSpec, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="lua",
    version="5.5.0",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.HTTP_ARCHIVE,
        url="https://www.lua.org/ftp/lua-5.5.0.tar.gz",
        sha256="57ccc32bbbd005cab75bcc52444052535af691789dba2b9016d5c50640d68b3d",
    ),
    build=BuildSpec(
        kind=BuildKind.MAKE_COMMAND,
        make_target="linux",
        install_target="install",
    ),
    roles=frozenset({ToolRole.BUILD, ToolRole.RUNTIME}),
    probes=(("lua", "-v"),),
)

from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    ToolRole,
    ToolSpec,
)

SPEC = ToolSpec(
    name="zstd",
    version="1.5.7",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.HTTP_ARCHIVE,
        url="https://github.com/facebook/zstd/releases/download/v1.5.7/zstd-1.5.7.tar.gz",
        sha256="eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3",
    ),
    build=BuildSpec(
        kind=BuildKind.MAKE_COMMAND,
        make_target="zstd-release",
        install_target="install",
        install_prefix_variable="PREFIX",
        environment={
            "HAVE_ZLIB": "0",
            "HAVE_LZMA": "0",
            "HAVE_LZ4": "0",
        },
    ),
    roles=frozenset({ToolRole.BUILD, ToolRole.RUNTIME}),
    probes=(("zstd", "--version"),),
)

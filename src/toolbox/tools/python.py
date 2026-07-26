from toolbox.model import AcquisitionKind, AcquisitionSpec, InstallEntry, InstallEntryKind, ToolRole, ToolSpec

TARGET = "x86_64-unknown-linux-gnu"

SPEC = ToolSpec(
    name="python",
    version="3.14.3",
    target=TARGET,
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.HTTP_ARCHIVE,
        url=(
            "https://github.com/astral-sh/python-build-standalone/releases/download/"
            "20260203/cpython-3.14.3%2B20260203-x86_64-unknown-linux-gnu-"
            "install_only_stripped.tar.gz"
        ),
        sha256="d2a2c12cc62b9de249ed9f7c66c6382c76788b464297aaed165853e18643f9e7",
    ),
    install=(InstallEntry("python", ".", InstallEntryKind.TREE),),
    roles=frozenset({ToolRole.BUILD, ToolRole.RUNTIME}),
    probes=(("python", "--version"),),
)

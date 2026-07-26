from toolbox.model import AcquisitionKind, AcquisitionSpec, InstallEntry, InstallEntryKind, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="uv",
    version="0.11.32",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.HTTP_ARCHIVE,
        url=(
            "https://github.com/astral-sh/uv/releases/download/0.11.32/"
            "uv-x86_64-unknown-linux-gnu.tar.gz"
        ),
        sha256="aab924fd522efd06f1c5f3b93a243864fc453132c94b2dc49f1371b528a4b967",
    ),
    install=(
        InstallEntry("uv-x86_64-unknown-linux-gnu/uv", "bin/uv", InstallEntryKind.FILE),
        InstallEntry("uv-x86_64-unknown-linux-gnu/uvx", "bin/uvx", InstallEntryKind.FILE),
    ),
    roles=frozenset({ToolRole.RUNTIME}),
    probes=(("uv", "--version"),),
)

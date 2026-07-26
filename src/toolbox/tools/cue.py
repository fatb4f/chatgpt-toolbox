from toolbox.model import AcquisitionKind, AcquisitionSpec, InstallEntry, InstallEntryKind, ToolRole, ToolSpec

SPEC = ToolSpec(
    name="cue",
    version="0.18.0",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GITHUB_RELEASE,
        repository="cue-lang/cue",
        release="v0.18.0",
        asset="cue_v0.18.0_linux_amd64.tar.gz",
        sha256=None,
    ),
    install=(InstallEntry("cue", "bin/cue", InstallEntryKind.FILE),),
    roles=frozenset({ToolRole.RUNTIME}),
    probes=(("cue", "version"),),
)

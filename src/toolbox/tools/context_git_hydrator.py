from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    ToolRole,
    ToolSpec,
)

DOTFILES_REVISION = "de858a831d219cae1abcd721ea11cc4779ab6a9a"
HYDRATOR_DIGEST_SYMBOL = (
    "github.com/fatb4f/dotfiles/.codex/context-hydrators/git/"
    "internal/hydrator.BuildHydratorDigest"
)

SPEC = ToolSpec(
    name="context-git-hydrator",
    version=f"0.0.0+{DOTFILES_REVISION[:7]}",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository="https://github.com/fatb4f/dotfiles.git",
        revision=DOTFILES_REVISION,
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go", "go-git"),
        source_subdir=".codex/context-hydrators/git",
        package="./cmd/context-git-hydrator",
        output="bin/context-git-hydrator",
        build_vcs=True,
        ldflags=("-s", "-w"),
        source_digest_symbol=HYDRATOR_DIGEST_SYMBOL,
    ),
    roles=frozenset({ToolRole.RUNTIME, ToolRole.PROGRAM}),
    probes=(),
)

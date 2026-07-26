from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    BuildKind,
    BuildSpec,
    ToolRole,
    ToolSpec,
)

SPEC = ToolSpec(
    name="context-git-hydrator",
    version="<pinned revision identity>",
    target="x86_64-unknown-linux-gnu",
    acquisition=AcquisitionSpec(
        kind=AcquisitionKind.GO_MODULE,
        module=("github.com/fatb4f/dotfiles/.codex/context-hydrators/git"),
        version="<immutable revision>",
    ),
    build=BuildSpec(
        kind=BuildKind.GO_COMMAND,
        requires=("go",),
        package=(
            "github.com/fatb4f/dotfiles/"
            ".codex/context-hydrators/git/"
            "cmd/context-git-hydrator"
        ),
        output="bin/context-git-hydrator",
    ),
    roles=frozenset({ToolRole.RUNTIME, ToolRole.PROGRAM}),
    probes=(),
)

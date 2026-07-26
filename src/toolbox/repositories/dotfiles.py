from pathlib import Path

from toolbox.model import (
    AcquisitionKind,
    AcquisitionSpec,
    PythonProjectSpec,
    RepositorySpec,
    SourcePatchSpec,
)
from toolbox.tools.context_git_hydrator import DOTFILES_REVISION, DOTFILES_SOURCE

SPEC = RepositorySpec(
    name="dotfiles",
    root=Path("repos/dotfiles"),
    target="x86_64-unknown-linux-gnu",
    python_group="repo-dotfiles",
    tools=(
        "python",
        "go",
        "cue",
        "gopls",
        "goimports",
        "uv",
        "lua",
        "luals",
        "go-git",
        "context-git-hydrator",
    ),
    programs=("context-git-hydrator",),
    source=AcquisitionSpec(
        kind=AcquisitionKind.GIT_CHECKOUT,
        repository=DOTFILES_SOURCE,
        revision=DOTFILES_REVISION,
    ),
    python_project=PythonProjectSpec(groups=("test",)),
    patches=(
        SourcePatchSpec(
            path="patches/dotfiles-context-selection-cue-0.18.patch",
            sha256="163f69dfd3474c61a60f6f6c973ed99d06f89793264dcddd96293f0269876969",
        ),
    ),
)

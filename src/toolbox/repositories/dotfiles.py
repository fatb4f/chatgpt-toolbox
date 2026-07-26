from pathlib import Path

from toolbox.model import RepositorySpec

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
        "gitfacts",
    ),
    programs=("gitfacts",),
)

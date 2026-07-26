set shell := ["bash", "-euo", "pipefail", "-c"]

inspect repository="dotfiles":
    uv run toolbox inspect --repository {{repository}}

bundle repository="dotfiles":
    uv run --group repo-dotfiles toolbox build --repository {{repository}}

bundle-dotfiles:
    uv run --group repo-dotfiles toolbox build --repository dotfiles

clean repository="dotfiles":
    uv run toolbox clean --repository {{repository}}

clean-cache:
    uv run toolbox clean-cache

test:
    uv run --group dev pytest

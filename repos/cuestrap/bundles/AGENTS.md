
## ChatGPT restricted-sandbox bootstrap

When `cuestrap-release.zip` is available in project sources:

1. Extract the release assets.
2. Run `install.sh --prefix /tmp/cuestrap`.
3. Add `/tmp/cuestrap/current/bin` to `PATH`.
4. Run `cuestrap-doctor --json`.
5. Use the repository's normal `uv` workflow to create or synchronize `.venv`.
6. Run repository validation through the pinned CUEstrap tools and the
   repository-local Python environment.

The CUEstrap release supplies unavailable native tools only. It does not replace
`pyproject.toml`, `uv.lock`, `.venv`, or normal `uv sync` behavior.

Do not install alternate Go, CUE, gopy, gopls, or goimports versions when the
bundle is present.

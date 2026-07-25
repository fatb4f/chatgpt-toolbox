
## ChatGPT restricted-sandbox bootstrap

When `cuestrap-release.zip` is available in project sources:

1. Extract the release assets.
2. Run `install.sh --prefix /tmp/cuestrap`.
3. Add `/tmp/cuestrap/current/bin` to `PATH`.
4. Run `cuestrap-doctor --json`.
5. Bind UV to the bundled interpreter with `export UV_PYTHON=/tmp/cuestrap/current/bin/python3`.
6. Run `uv sync --frozen --no-python-downloads` to create or synchronize `.venv`.
7. Run repository validation through the pinned CUEstrap tools and the
   repository-local Python environment.

The CUEstrap release supplies unavailable native tools only. It does not replace
`pyproject.toml`, `uv.lock`, `.venv`, or normal `uv sync` behavior.

Do not install alternate UV, Go, CUE, gopy, gopls, or goimports versions when the
bundle is present.

## Bundle lock extension

The native UV pin is declared in `toolchain-uv.cue` beside the builder.
`build-linux-amd64.sh` must export that file together with
`environment/toolchain.cue` before reading `tools.uv` or computing the lock
digest. Keep source-file references relative to the builder directory so a
qualified bundle copy can be exercised under `tools/bundles-uv` without
falling back to stale files under `tools/bundles`.

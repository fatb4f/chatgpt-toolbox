# ChatGPT Toolbox

A Python-authoritative builder for repository-specific, self-contained native tool bundles.

```text
Just recipe
    ↓
root UV project + dependency group
    ↓
jsonargparse command façade
    ↓
frozen repository/tool descriptors
    ↓
validated acyclic build graph
    ↓
acquire → verify → build → stage → package
    ↓
repos/<repository>/dist/
```

## Authority boundary

The MVP uses:

- frozen dataclasses for descriptor types;
- immutable, closed repository and tool registries;
- constructor and graph invariants;
- typed operations exposed through `jsonargparse`;
- SHA-256 and immutable-revision admission before build execution.

CUE projection, Pydantic generation, and Hypothesis mutation testing remain deferred extensions.

## Commands

```bash
just inspect dotfiles
just bundle-dotfiles
just clean dotfiles
just test
```

Equivalent direct commands:

```bash
uv run toolbox inspect --repository dotfiles
uv run --group repo-dotfiles toolbox build --repository dotfiles
uv run toolbox clean --repository dotfiles
```

`inspect` is non-mutating. It emits the resolved build order and all lock defects. `build` refuses to perform transport while any digest, source revision, module version, or required local source is unresolved.

## Dotfiles bundle

The registered closure is:

```text
Python 3.14.3
Go 1.26.5
CUE 0.18.0
gopls 0.23.0
goimports @ pinned golang/tools revision
UV 0.11.32
Lua 5.5.0
LuaLS 3.18.2
go-git @ pinned module version
gitfacts from repository-owned source
```

The graph enforces:

```text
go ─────┬─→ gopls
        ├─→ goimports
        └─→ gitfacts ←─ go-git

lua ───────→ luals
```

The build prefix is the packaged runtime prefix. Go builds run with:

```bash
GOROOT="$PREFIX/libexec/go"
GOTOOLCHAIN=local
GOBIN="$PREFIX/bin"
PATH="$GOROOT/bin:$PREFIX/bin:$PATH"
```

## Lock completion

The uploaded design did not include every literal pin. The descriptors intentionally retain explicit unresolved defects for:

- the CUE SHA-256 value;
- the pinned `go-git` module version;
- the repository-owned `gitfacts` source path.

Python 3.14.3, Go 1.26.5, UV 0.11.32, Lua 5.5.0, and LuaLS 3.18.2 include their published SHA-256 values. `goimports` is pinned to its complete commit. No placeholder digest is accepted as authority.

CUE 0.18.0 remains deliberately unresolved: the requested `v0.18.0` GitHub release asset is not presently available, while the supplied cuestrap manifest identifies CUE 0.18.0 as a source build from commit `806821e40fae070318600a264d311517e596353b`. The toolbox does not silently change the requested acquisition class.

## Constructor host

The current generic adapters require these host-side constructors:

```text
uv
gh
git
make
C compiler toolchain (for Lua)
```

The resulting bundle still carries its own pinned Python, Go, and UV runtimes. Host tools are transport/build constructors and are not treated as bundle authority.

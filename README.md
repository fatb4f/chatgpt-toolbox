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
content-addressed acquisition pool
    ↓
content-addressed tool projection pool
    ↓
compose one repository prefix
    ↓
package one release archive
```

## Authority boundary

The builder uses:

- frozen dataclasses for descriptor types;
- immutable, closed repository and tool registries;
- constructor and graph invariants;
- typed operations exposed through `jsonargparse`;
- SHA-256 and immutable Git/module revisions before transport;
- deterministic build projections keyed by source, build contract, and dependency projections.

CUE projection, Pydantic generation, and Hypothesis mutation testing remain deferred extensions.

## Commands

```bash
just inspect dotfiles
just bundle-dotfiles
just clean dotfiles
just clean-cache
just test
```

Equivalent direct commands:

```bash
uv run toolbox inspect --repository dotfiles
uv run --group repo-dotfiles toolbox build --repository dotfiles
uv run toolbox clean --repository dotfiles
uv run toolbox clean-cache
```

`inspect` is non-mutating. `build` refuses transport while any digest, source revision, or module version is unresolved.

`clean` removes only the repository composition workspace. It deliberately preserves `.toolbox-cache`, allowing immutable downloads, source checkouts, and built tool projections to be reused. `clean-cache` is the explicit eviction operation.

## Dotfiles bundle

The registered closure is:

```text
Python 3.14.3
Go 1.26.5
CUE 0.18.0 @ 806821e
 gopls 0.23.0 ┐
                  ├─ shared golang/tools checkout @ 014f87f
 goimports        ┘
UV 0.11.32
Lua 5.5.0
LuaLS 3.18.2
go-git v5.19.1
context-git-hydrator @ pinned dotfiles revision
```

The graph enforces:

```text
go ─────┬─→ cue
        ├─→ gopls
        ├─→ goimports
        └─→ context-git-hydrator ←─ go-git

lua ───────→ luals
```

CUE, gopls, goimports, and the context hydrator follow the known-good CUEstrap source workflow:

```bash
git fetch --depth=1 <exact-commit>
git checkout --detach FETCH_HEAD
go build -trimpath -buildvcs=true '-ldflags=-s -w' ...
```

CUE 0.18.0 is therefore acquired from commit `806821e40fae070318600a264d311517e596353b`; the nonexistent module query `cuelang.org/go/cmd/cue@v0.18.0` is never used.

## Pooling model

Pool keys do not contain repository names.

```text
Acquisition key
    = hash(AcquisitionSpec)

Projection key
    = hash(ToolSpec + acquired identity + dependency projection keys)
```

Consequences:

- gopls and goimports share one `golang/tools` checkout;
- repeated builds do not redownload immutable archives;
- compiled tools are reused across repository bundles when their full build closure is unchanged;
- repository bundles remain independent compositions;
- only the combined repository archive is published—pooled projections are internal cache entries, not release artifacts.

The final lock records deterministic acquisition and projection keys. It does not record whether a cache happened to be warm, so cold and warm builds remain byte-equivalent.

## Build layout

```text
.toolbox-cache/
├── downloads/                 # shared immutable archives
├── sources/                   # shared immutable Git checkouts
├── builds/<target>/           # external compiler/module caches
└── projections/<target>/      # verified immutable tool projections

.toolbox-work/
└── dotfiles-<target>/
    └── prefix/                 # disposable composed bundle

repos/dotfiles/dist/
└── dotfiles-<target>.tar.gz    # sole published artifact
```

Go source builds use the pooled Go toolchain while writing only into the tool's projection:

```bash
GOROOT="$COMPOSED_PREFIX/libexec/go"
GOTOOLCHAIN=local
GOBIN="$PROJECTION_PREFIX/bin"
PATH="$GOROOT/bin:$COMPOSED_PREFIX/bin:$PROJECTION_PREFIX/bin:$PATH"
```

## Constructor host

The generic adapters require these host-side constructors:

```text
uv
git
make
C compiler toolchain (for Lua)
```

Public release assets use pinned HTTPS URLs and SHA-256 verification, so the dotfiles closure no longer requires `gh` for transport.

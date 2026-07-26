# ChatGPT Toolbox

A Python-authoritative builder for repository-specific, offline tool releases.

```text
frozen repository/tool/component descriptors
    ↓
validated acyclic build graph
    ↓
content-addressed acquisition pool
    ↓
content-addressed build projections
    ↓
qualified deterministic component archives
    ↓
manifest-bound aggregate tar.zst
    ↓
stable-prefix installer
```

## Authority boundary

The builder uses:

- frozen dataclasses and closed registries;
- immutable Git revisions, module versions, and SHA-256 pins;
- typed build projections, including source-derived Go linker variables;
- qualification gates before component admission;
- deterministic `tar.zst` archives with epoch timestamps and numeric ownership;
- release and component manifests that encode the admitted DAG.

CUE may later generate or validate descriptor values, but Python remains the execution adapter for acquisition, pooling, building, qualification, and publication.

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

`inspect` is non-mutating. `clean` removes only the repository workspace. `clean-cache` explicitly evicts the shared content-addressed pool.

## Pool and release separation

The pool is an internal build accelerator:

```text
.toolbox-cache/
├── downloads/                  verified immutable archives
├── sources/                    clean immutable Git checkouts
├── builds/<target>/            compiler and module caches
├── projections/<target>/       checksum-bound tool projections
└── components/<target>/        checksum-bound component archives
```

Repository names are excluded from cache keys when the underlying artifact is reusable. Cache hit state never enters release authority, so cold and warm builds remain byte-identical.

The published release is layered:

```text
repos/dotfiles/dist/release/
├── install.sh
├── manifest.json
├── release-lock.json
├── SHA256SUMS
├── dotfiles-native-base-linux-amd64.tar.zst
├── dotfiles-native-base-linux-amd64.tar.zst.sha256
├── dotfiles-go-programs-linux-amd64.tar.zst
├── dotfiles-go-programs-linux-amd64.tar.zst.sha256
├── dotfiles-python-projects-linux-amd64.tar.zst
├── dotfiles-python-projects-linux-amd64.tar.zst.sha256
├── dotfiles-repository-source-linux-amd64.tar.zst
├── dotfiles-repository-source-linux-amd64.tar.zst.sha256
└── dotfiles-tools-linux-amd64.tar.zst
```

Only the aggregate is required for installation; component archives remain independently inspectable and reusable release surfaces.

## Dotfiles release graph

```text
native-base
├── Python 3.14.3
├── uv 0.11.32
├── Go 1.26.5
├── CUE 0.18.0 @ pinned source revision
├── Lua 5.5.0
├── gopls / goimports @ shared x/tools revision
└── LuaLS 3.18.2

go-programs ──requires──> native-base
└── context-git-hydrator
    ├── deterministic source digest
    ├── BuildHydratorDigest linker injection
    └── committed-snapshot fixture qualification

repository-source ──requires──> native-base
└── exact dotfiles checkout admitted only after the pinned CUE suite passes

python-projects ──requires──> native-base + repository-source
└── pyproject.toml + uv.lock + offline uv closure
```

CUE, gopls, goimports, and the Git hydrator follow the known-good CUEstrap source-build pattern:

```bash
git fetch --depth=1 <exact-commit>
git checkout --detach FETCH_HEAD
go build -trimpath -buildvcs=true '-ldflags=-s -w ...' ...
```

## Installation

```bash
bash repos/dotfiles/dist/release/install.sh --prefix /tmp/dotfiles
export PATH=/tmp/dotfiles/current/bin:$PATH
export GOROOT=/tmp/dotfiles/current/libexec/go
export GOTOOLCHAIN=local
```

The installer verifies the outer checksums and aggregate manifest, installs into `versions/<lock-digest>`, materializes the Python project from the bundled offline uv cache, verifies the installed projection, and atomically updates `current`.

No sourced activation script must infer its own pathname.

# Toolbox architecture

## Descriptor graph

```text
RepositorySpec
├── selected target
├── Python dependency group
├── ToolSpec references
└── Program references

ToolSpec
├── identity/version/target
├── AcquisitionSpec
├── BuildSpec
├── install projection
├── bundle links
├── roles
└── dependency edges
```

The registry is closed through immutable mappings. Graph resolution rejects unknown nodes, target mismatches, missing dependencies, and cycles.

## Acquisition matrix

| Descriptor kind | Adapter |
| --- | --- |
| `github-release` | exact GitHub asset metadata plus SHA-256 |
| `http-archive` | HTTPS download plus SHA-256 verification |
| `git-checkout` | detached checkout of a full commit |
| `go-module` | immutable module identity consumed by Go build logic |
| `local-source` | toolbox-owned relative source path |

Acquisitions are pooled by the canonical `AcquisitionSpec`, not by tool or repository name. Two tools with the same immutable source resolve to the same cached path.

## Build matrix

| Build kind | Behavior |
| --- | --- |
| `none` | extract and stage declared entries |
| `go-command` | use the pooled Go compiler and emit one isolated projection |
| `make-command` | build source and install into one isolated projection |

Go build controls are typed:

```text
trimpath
build_vcs
ldflags
```

The dotfiles source-built commands use the CUEstrap flags:

```text
-trimpath
-buildvcs=true
-ldflags=-s -w
```

## Two-level pool

```text
immutable acquisition
        ↓
AcquisitionSpec hash
        ↓
shared archive or checkout
        ↓
ToolSpec + source identity + dependency projection keys
        ↓
verified immutable tool projection
        ↓
repository composition prefix
```

Projection markers contain a tree SHA-256. A missing, malformed, or changed projection is rebuilt rather than trusted.

The dependency projection keys are part of the build key. Changing the pooled Go compiler or a declared module edge therefore invalidates dependent binaries without invalidating unrelated tools.

## Composition

Tool projections are merged into a fresh repository prefix in topological order. Files are copied from the immutable pool so the disposable composition cannot mutate cached projections. Conflicting paths are rejected unless they are byte-identical (or identical symlinks).

The composition prefix receives only repository-level metadata after projection merge:

```text
activate
native-lock.json
```

Cache hit/miss state is intentionally excluded from `native-lock.json`; a warm build and cold build have the same release authority.

## Bundle invariants

```text
one repository build → one published archive

all network archives have pinned SHA-256
all Git checkouts use full commit IDs
all Go modules have immutable versions
all dependency edges resolve inside the selected closure
the selected graph is acyclic
repository-owned Go programs require declared module pins in go.mod
Go compiler and module caches remain outside packaged projections
archive paths cannot escape extraction/staging roots
pooled projections are checksum-verified before reuse
projection conflicts are rejected
archive metadata is normalized
```

## Workspace ownership

```text
.toolbox-cache/                persistent, shared, explicitly evicted
.toolbox-work/<repo-target>/   disposable repository composition
repos/<repo>/dist/             published combined archive
```

`toolbox clean` removes only the disposable repository workspace. `toolbox clean-cache` removes the shared pool.

## Constructor boundary

The package does not bootstrap every host primitive. `uv` runs the Python control plane, `git` materializes immutable source revisions, and `make` plus a native C toolchain build Lua. Public binary archives are downloaded directly over HTTPS and admitted by SHA-256.

The resulting bundle carries its own pinned Python, Go, and UV runtimes. Host tools remain constructors, not bundle authority.

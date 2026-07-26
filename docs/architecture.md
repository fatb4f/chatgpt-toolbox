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
| `github-release` | `gh release view` then `gh release download` |
| `http-archive` | HTTPS download plus SHA-256 verification |
| `git-checkout` | detached checkout of a full commit |
| `go-module` | immutable module identity consumed by Go build logic |
| `local-source` | repository-owned source path |

## Build matrix

| Build kind | Behavior |
| --- | --- |
| `none` | extract and stage declared entries |
| `go-command` | force the staged Go compiler and emit into the prefix |
| `make-command` | build source and install directly into the prefix |

## Bundle invariants

```text
build prefix == packaged runtime prefix

all network archives have pinned SHA-256
all Git checkouts use full commit IDs
all Go modules have immutable versions
all dependency edges resolve inside the selected closure
the selected graph is acyclic
repository-owned Go programs require the declared module pins in go.mod
Go build caches remain outside the packaged prefix
archive paths cannot escape extraction/staging roots
archive metadata is normalized
```

## Constructor boundary

The package does not bootstrap every host primitive. `uv` runs the Python control plane, `gh` transports GitHub release assets, `git` materializes immutable source revisions, and `make` plus a native C toolchain build Lua. These constructors are distinct from the bundle-owned Python, Go, and UV installations staged into the final prefix.

A root `uv.lock` should be generated in a networked environment after the dependency groups are accepted. The implementation does not fabricate a lockfile when dependency metadata is unavailable.

## Output

```text
repos/dotfiles/dist/
└── dotfiles-x86_64-unknown-linux-gnu.tar.gz
```

Archive root:

```text
dotfiles-x86_64-unknown-linux-gnu/
├── bin/
├── lib/
├── libexec/go/
├── share/
├── activate
└── native-lock.json
```

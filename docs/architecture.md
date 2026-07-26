# Toolbox architecture

## Graphs

The toolbox models separate build and release graphs.

```text
Build graph
source authority → acquisition → projection → qualification

Release graph
qualified projection → component archive → aggregate → installation
```

`RepositorySpec` selects tools and programs, declares repository-source and Python-lock authority, and defines the component DAG. `ToolSpec` declares acquisition, build, install, probe, role, and dependency contracts.

## Acquisition pool

| Kind | Admission |
| --- | --- |
| `github-release` | exact asset identity plus SHA-256 |
| `http-archive` | HTTPS plus SHA-256 |
| `git-checkout` | detached full commit with no tracked or untracked changes |
| `go-module` | immutable module version |
| `local-source` | toolbox-relative source tree digest |

```text
acquisition key = SHA-256(canonical AcquisitionSpec)
```

Equivalent immutable acquisitions share one cache entry independently of tool and repository names.

## Build projections

```text
projection key = SHA-256(
    ToolSpec
    + acquired identity
    + resolved source digest/linker values
    + dependency projection keys
)
```

Go builds use the pooled Go toolchain, isolated output prefixes, and an external target-scoped module/build cache. Typed controls include `trimpath`, `build_vcs`, linker flags, source digest projections, and source-derived linker variables.

A cached projection is reusable only when its marker and tree checksum agree.

## Component DAG

| Component | Contents | Admission gate |
| --- | --- | --- |
| `native-base` | reusable runtimes and language tooling | runtime probes |
| `go-programs` | repository-specific Go commands | program-specific runtime qualification |
| `repository-source` | exact tracked source projection | repository CUE qualification suite |
| `python-projects` | lock authority, offline uv closure, command wrappers | frozen uv synchronization |

Component keys contain their complete immutable inputs and dependency authority. Qualification runs only when a component must be created; a checksum-valid cached component reuses its stored report.

Each component archive is reopened after creation and checked for:

- numeric owner/group `0/0`;
- epoch timestamps;
- safe paths and links;
- byte-equivalence with its admitted staging tree.

## Aggregate release

```text
release/
├── install.sh
├── manifest.json
├── release-lock.json
├── SHA256SUMS
├── <component>.tar.zst
├── <component>.tar.zst.sha256
└── <repository>-tools-linux-amd64.tar.zst
```

`release-lock.json` records tool and component DAG authority. Its canonical SHA-256 is the release lock digest. `manifest.json` binds that digest, target constraints, component records, aggregate name/size/digest, and installer host requirements.

The aggregate archive is a deterministic merge of admitted components. Conflicting paths are rejected unless they are identical.

## Installation

The outer installer verifies the release authority and safely extracts the aggregate. The embedded installer then:

1. verifies the archive projection;
2. selects `versions/<lock-digest>`;
3. materializes any Python project with bundled uv and offline cache;
4. verifies the installed projection while excluding declared mutable paths;
5. atomically updates `current`.

```text
<prefix>/
├── versions/<lock-digest>/
└── current -> versions/<lock-digest>
```

## Invariants

```text
all transport sources are immutable and admitted
all dependency graphs are closed and acyclic
pooled checkouts are clean
projection/component markers match tree and archive digests
qualification precedes component publication
cache hit/miss state is absent from release authority
cold and warm releases are byte-identical
archive paths cannot escape extraction roots
component and aggregate tar metadata is deterministic
one repository release installs through a stable current symlink
```

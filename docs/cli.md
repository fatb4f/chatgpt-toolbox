# CLI contract

## Surface

```python
def inspect(
    repository: str,
    target: str | None = None,
    toolbox_root: Path = Path("."),
) -> RepositoryPlan: ...


def build(
    repository: str,
    target: str | None = None,
    toolbox_root: Path = Path("."),
    pool_root: Path | None = None,
) -> BundleResult: ...


def clean(
    repository: str,
    target: str | None = None,
    toolbox_root: Path = Path("."),
) -> None: ...


def clean_cache(toolbox_root: Path = Path(".")) -> None: ...
```

`jsonargparse.auto_cli` exposes only these typed functions. Repository names, tool names, versions, sources, checksums, and build flags are not user-overridable CLI parameters.

## Control flow

```text
CLI arguments
    ↓
closed repository lookup
    ↓
target compatibility validation
    ↓
dependency closure validation
    ↓
topological ordering
    ↓
lock admission
    ↓
shared acquisition lookup/build
    ↓
shared projection lookup/build
    ↓
repository composition
    ↓
package one archive
```

## Inspect

`inspect` resolves the complete graph without transport or filesystem mutation. The result includes:

- repository and target;
- root UV dependency group;
- deterministic output path;
- topologically ordered nodes;
- acquisition and build descriptors;
- unresolved lock defects.

A plan is admissible exactly when `lock_defects` is empty.

## Build

`build` has a fail-closed precondition:

```text
plan.lock_defects == ()
```

Only then may it:

1. resolve an immutable acquisition identity;
2. reuse or acquire the shared archive/checkout;
3. verify SHA-256 or exact Git revision;
4. derive a projection key from the complete build closure;
5. reuse or build the isolated tool projection;
6. checksum the projection before reuse;
7. merge projections into one fresh repository prefix;
8. write `native-lock.json` without cache-hit state;
9. create one normalized deterministic `tar.gz` archive.

`pool_root` defaults to `.toolbox-cache`. It may be redirected when several toolbox checkouts should share a cache.

## Clean

`clean` removes only:

```text
.toolbox-work/<repository>-<target>
```

It does not remove immutable acquisitions or projections.

`clean-cache` is the explicit destructive operation for:

```text
.toolbox-cache/
```

## Transport adapters

Public dotfiles bundle assets use exact HTTPS URLs plus SHA-256. The generic GitHub release adapter remains available for descriptors that require release metadata validation, but it is not selected by the current dotfiles closure.

Git checkout sources are admitted only by a full 40-character commit and are reused only while both conditions remain true:

```text
HEAD == requested revision
tracked working tree is clean
```

## Deferred authority projection

A later CUE layer can validate or generate the Python descriptors and command façade. It should not duplicate execution behavior. Python remains the adapter for acquisition, pooling, building, composition, and packaging.

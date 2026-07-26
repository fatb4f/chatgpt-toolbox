# CLI contract

## Surface

```python
def inspect(repository: str, target: str | None = None, toolbox_root: Path = Path(".")) -> RepositoryPlan: ...

def build(
    repository: str,
    target: str | None = None,
    toolbox_root: Path = Path("."),
    pool_root: Path | None = None,
) -> BundleResult: ...

def clean(repository: str, target: str | None = None, toolbox_root: Path = Path(".")) -> None: ...

def clean_cache(toolbox_root: Path = Path(".")) -> None: ...
```

Repository names, versions, sources, checksums, build flags, qualification commands, and component edges are closed descriptor authority rather than user-overridable CLI inputs.

## Inspect

`inspect` resolves without transport or mutation and returns:

- repository and target;
- Python dependency group;
- deterministic aggregate output path;
- topologically ordered tool nodes;
- component DAG;
- unresolved lock defects.

## Build

`build` requires `plan.lock_defects == ()`, then executes:

```text
shared acquisition lookup/admission
    ↓
shared projection lookup/build
    ↓
program and repository qualification
    ↓
shared component lookup/build
    ↓
component archive verification
    ↓
aggregate composition and verification
    ↓
manifest / release lock / checksums / installer
```

The result identifies the release directory, aggregate, manifest, release lock, component archives, and aggregate staging root.

## Clean

`clean` removes only `.toolbox-work/<repository>-<target>`. It preserves downloads, source checkouts, build caches, projections, and component archives.

`clean-cache` removes `.toolbox-cache` explicitly.

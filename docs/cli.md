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
) -> BundleResult: ...


def clean(
    repository: str,
    target: str | None = None,
    toolbox_root: Path = Path("."),
) -> None: ...
```

`jsonargparse.auto_cli` exposes only these typed functions. Repository names, tool names, versions, sources, and checksums are not user-overridable CLI parameters.

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
operation execution
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

1. resolve a GitHub release asset against release metadata;
2. download through `gh release download`;
3. verify the descriptor SHA-256;
4. acquire HTTP archives or immutable Git revisions;
5. build with the staged toolchain;
6. stage into one prefix;
7. write `native-lock.json`;
8. create a normalized deterministic `tar.gz` archive.

## GitHub release adapter

The adapter first requests release metadata:

```bash
gh release view "$TAG" \
  --repo "$REPOSITORY" \
  --json assets
```

It requires exactly one asset with the descriptor's exact name before running:

```bash
gh release download "$TAG" \
  --repo "$REPOSITORY" \
  --pattern "$ASSET" \
  --dir "$DOWNLOAD_DIR"
```

Transport identity and content identity remain separate gates:

```text
release metadata exact-name match
    ∧
local SHA-256 equals descriptor SHA-256
```

## Deferred authority projection

A later CUE layer can validate or generate the Python descriptors and command façade. It should not duplicate execution behavior. The Python operations remain adapters for acquisition, building, staging, and packaging.

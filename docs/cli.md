```text
CUE logical kernel
├── domain types
├── operation signatures
├── admissible graph
├── properties
├── effects
└── command declarations
        ↓ code generation
Generated Pydantic models
Generated Protocols
Generated command façade
        ↓ introspection
jsonargparse
        ↓
CLI arguments
config files
environment variables
subcommands
object instantiation
        ↓
typed handlers
```

Verification remains:

```text
CUE         graph and policy admission
ty          static Python conformance
Pydantic    runtime value conformance
Hypothesis  behavioral property testing
Ruff        source policy and defect detection
pytest      examples and integration
```

## Important authority constraint

By default, `jsonargparse` treats Python signatures as the CLI description:

```python
def profile(
    root: Path,
    timezone: str = "UTC",
    strict: bool = False,
) -> DailyProfile:
    ...
```

Instead:

```text
CUE
  ↓ generates
Python command façade
  ↓ inspected by
jsonargparse
```

For example:

```python
# Generated from CUE. Do not edit.

from pathlib import Path

from codex_profile.application import execute_profile
from codex_profile.generated.models import DailyProfile


def profile(
    roots: list[Path],
    timezone: str = "UTC",
    strict: bool = False,
) -> DailyProfile:
    """Generate a daily Codex usage profile.

    Args:
        roots: Session files or directories to scan.
        timezone: Timezone used for daily aggregation.
        strict: Reject malformed events instead of recording diagnostics.
    """
    return execute_profile(
        roots=roots,
        timezone=timezone,
        strict=strict,
    )
```

Then the entire CLI can be:

```python
from jsonargparse import auto_cli

from codex_profile.generated.commands import profile


def main() -> None:
    result = auto_cli({"profile": profile})

    if result is not None:
        print(result.model_dump_json(indent=2))
```

No generated Typer syntax is required.

## Argument linking

Its argument-linking facility is especially relevant. It can propagate one parsed value into another target:

```python
parser.link_arguments(
    "scan.timezone",
    "aggregate.timezone",
    apply_on="parse",
)
```

It can also link instantiated objects, automatically deriving an instantiation order. The linked instantiation graph must be a DAG.

This overlaps with part of the CUE kernel, but the boundary matters:

```text
jsonargparse argument links
    configuration propagation
    object-instantiation ordering

CUE operation graph
    type compatibility
    admissible operation composition
    effects and policy
    behavioral declarations
```

`link_arguments` should therefore be treated as an **execution adapter feature**, not the authoritative logical graph.

CUE can generate the link declarations:

```cue
command: {
	name: "profile"

	links: [
		{
			source:  "scan.timezone"
			target:  "aggregate.timezone"
			applyOn: "parse"
		},
	]
}
```

Projected Python:

```python
parser.link_arguments(
    "scan.timezone",
    "aggregate.timezone",
    apply_on="parse",
)
```

## Pydantic integration

The repository explicitly tests Pydantic models, constrained fields, nested models, dataclasses, defaults, and discriminated unions. For example, a discriminated union can be selected through CLI dot syntax and instantiated as the appropriate Pydantic subtype.

That permits CUE-generated operation unions such as:

```cue
#Source:
	#FilesystemSource |
	#StdinSource
```

to project into:

```python
class FilesystemSource(BaseModel):
    kind: Literal["filesystem"]
    roots: list[Path]


class StdinSource(BaseModel):
    kind: Literal["stdin"]


Source = Annotated[
    FilesystemSource | StdinSource,
    Field(discriminator="kind"),
]
```

`jsonargparse` can then expose the generated union through the CLI/config surface.

## JSON Schema support

The library can validate an individual JSON or YAML argument against JSON Schema, including schema defaults. Its documented implementation currently uses Draft 7.

That may be useful for opaque external payloads:

```python
parser.add_argument(
    "--event",
    action=ActionJsonSchema(schema=event_schema),
)
```

But for the main internal domain:

```text
CUE → Pydantic → jsonargparse
```

is preferable to:

```text
CUE → JSON Schema → jsonargparse → untyped dictionary
```

The Pydantic path preserves Python static types and works better with `ty`.

## Alpha architecture revision

```text
kernel/
├── domain.cue
├── operations.cue
├── pipelines.cue
├── properties.cue
└── commands.cue

generated/
├── models.py
├── protocols.py
├── commands.py
└── plan.json

codex_profile/
├── handlers/
├── application.py
├── runtime.py
├── registry.py
└── cli.py
```

`cli.py` becomes minimal:

```python
from jsonargparse import auto_cli

from codex_profile.generated.commands import COMMANDS


def main() -> None:
    auto_cli(COMMANDS)
```

## Updated recommendation

For the alpha:

* use **CUE** as contract and graph authority;
* generate **Pydantic models**, typed protocols, and a thin command façade;
* use **jsonargparse instead of Typer**;
* keep the runtime registry closed;
* use `ty`, Ruff, Pydantic, Hypothesis, and pytest as previously defined;
* defer a custom CLI generator unless `jsonargparse` exposes an actual blocking limitation.

This substantially reduces prototype infrastructure while preserving the schema-first control model.

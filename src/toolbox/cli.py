from __future__ import annotations

import json
from typing import Any

from toolbox.commands import build, clean, inspect
from toolbox.model import to_primitive

COMMANDS = {"inspect": inspect, "build": build, "clean": clean}


def main() -> None:
    try:
        from jsonargparse import auto_cli
    except ImportError as error:
        raise SystemExit("jsonargparse is required; run the CLI through the root UV project") from error

    result: Any = auto_cli(COMMANDS, as_positional=False)
    if result is not None:
        print(json.dumps(to_primitive(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

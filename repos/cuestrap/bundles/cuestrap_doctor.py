#!/usr/bin/env python3
"""Machine-readable CUEstrap bundle admission checks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        **kwargs,
    )


def probe(command: list[str], expected: str = "") -> tuple[bool, str]:
    result = run(command)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0 and expected in output, output


def gopy_smoke(prefix: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="cuestrap-doctor-") as temporary:
        root = Path(temporary)
        module = root / "smoke"
        output = module / "out"
        module.mkdir()
        (module / "go.mod").write_text("module smoke\n\ngo 1.22.0\n")
        (module / "smoke.go").write_text(
            "package smoke\n\nfunc Add(a, b int) int { return a + b }\n"
        )
        build_environment = os.environ.copy()
        build_environment["GOCACHE"] = str(root / "go-build-cache")
        build_environment["GOMODCACHE"] = str(root / "go-module-cache")
        build = run(
            [
                str(prefix / "bin" / "gopy"),
                "build",
                "-vm",
                str(prefix / "bin" / "python3"),
                "-output",
                str(output),
                ".",
            ],
            cwd=module,
            env=build_environment,
        )
        if build.returncode:
            return False, (build.stdout + build.stderr)[-4000:]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(module)
        imported = run(
            [
                str(prefix / "bin" / "python3"),
                "-c",
                "from out import smoke; assert smoke.Add(20, 22) == 42",
            ],
            env=environment,
        )
        return imported.returncode == 0, (imported.stdout + imported.stderr)[-4000:]


def status(ok: bool, **identity: str) -> dict[str, str]:
    return {"status": "pass" if ok else "fail", **identity}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", required=True)
    args = parser.parse_args()
    del args

    prefix = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (prefix / "share" / "cuestrap" / "manifest.json").read_text()
    )
    tools = manifest["tools"]

    python_ok, _ = probe(
        [
            str(prefix / "bin" / "python3"),
            "-c",
            (
                "import cffi, platform, pybindgen, setuptools, ssl, sqlite3, wheel; "
                "print(platform.python_version())"
            ),
        ],
        tools["python"]["version"],
    )
    pip_ok, _ = probe([str(prefix / "bin" / "pip"), "--version"], "pip")
    go_ok, _ = probe([str(prefix / "bin" / "go"), "version"], tools["go"]["version"])
    cue_ok, _ = probe([str(prefix / "bin" / "cue"), "version"], tools["cue"]["version"])
    gopls_ok, _ = probe(
        [str(prefix / "bin" / "gopls"), "version"],
        tools["gopls"]["revision"][:12],
    )
    gofmt_result = run(
        [str(prefix / "bin" / "gofmt")], input="package smoke\n"
    )
    gofmt_ok = gofmt_result.returncode == 0
    goimports_result = run(
        [str(prefix / "bin" / "goimports")], input="package smoke\n"
    )
    goimports_ok = goimports_result.returncode == 0
    gopy_help = run([str(prefix / "bin" / "gopy"), "-h"])
    gopy_help_ok = gopy_help.returncode == 2 and "Usage of gopy:" in (
        gopy_help.stdout + gopy_help.stderr
    )
    gopy_build_ok, gopy_diagnostic = gopy_smoke(prefix)

    required_commands = manifest["hostRequirements"]["commands"]
    capabilities = {name: shutil.which(name) is not None for name in required_commands}
    libc_name, libc_version = platform.libc_ver()
    target = manifest["target"]
    platform_ok = (
        sys.platform == "linux"
        and platform.machine() == "x86_64"
        and libc_name == target["abi"]["libc"]
        and tuple(map(int, libc_version.split(".")))
        >= tuple(map(int, target["abi"]["minVersion"].split(".")))
    )

    document = {
        "schema": "cuestrap.doctor/v1",
        "lockDigest": manifest["lockDigest"],
        "platform": {
            "status": "pass" if platform_ok else "fail",
            "os": "linux" if sys.platform == "linux" else sys.platform,
            "arch": "amd64" if platform.machine() == "x86_64" else platform.machine(),
            "libc": libc_name,
            "libcVersion": libc_version,
        },
        "tools": {
            "python": status(python_ok and pip_ok, version=tools["python"]["version"]),
            "go": status(go_ok, version=tools["go"]["version"]),
            "gofmt": status(gofmt_ok, version=tools["go"]["version"]),
            "goimports": status(goimports_ok, revision=tools["goimports"]["revision"]),
            "cue": status(cue_ok, revision=tools["cue"]["revision"]),
            "gopls": status(gopls_ok, revision=tools["gopls"]["revision"]),
            "gopy": status(
                gopy_help_ok and gopy_build_ok,
                revision=tools["gopy"]["revision"],
                buildSmoke="pass" if gopy_build_ok else "fail",
            ),
        },
        "hostCapabilities": capabilities,
    }
    if not gopy_build_ok:
        document["diagnostics"] = {"gopy": gopy_diagnostic}
    print(json.dumps(document, indent=2, sort_keys=True))

    okay = (
        platform_ok
        and all(capabilities.values())
        and all(item["status"] == "pass" for item in document["tools"].values())
    )
    return 0 if okay else 1


if __name__ == "__main__":
    raise SystemExit(main())

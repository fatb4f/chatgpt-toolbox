# Linux AMD64 tool bundles

`environment/toolchain.cue` owns the base tool versions and source revisions.
`toolchain-uv.cue`, colocated with the builder, contributes the pinned native UV extension;
the builder unifies both CUE inputs before computing the canonical lock digest.
The primary distribution is the combined archive:

```text
cuestrap-tools-linux-amd64.tar.zst
```

The builder also produces six independently installable archives for caching
and maintenance:

```text
cuestrap-python-linux-amd64.tar.zst
cuestrap-uv-linux-amd64.tar.zst
cuestrap-go-linux-amd64.tar.zst
cuestrap-cue-linux-amd64.tar.zst
cuestrap-gopls-linux-amd64.tar.zst
cuestrap-gopy-linux-amd64.tar.zst
```

Build them from the repository root:

```bash
bash tools/bundles-uv/build-linux-amd64.sh
```

The network-enabled build-authority environment must provide CUE so the builder
can export the canonical lock. The resulting archives do not require CUE for
installation; the CUE executable is itself one of the payloads.

Each archive contains `install.sh`, `archive-files.sha256`, and a distinct
installed-state checksum projection. The Go archive contains the complete
relocatable GOROOT plus `gofmt` and the pinned `goimports`. The gopy archive
contains the patched generator CLI and an exact, file-backed proxy for its
`gopyh` module; generated extension modules remain project-specific.

The UV archive contains the pinned Linux AMD64 GNU executable. The combined
bundle uses it for normal `uv sync --frozen` and `uv run` workflows without
depending on a host-installed UV.

The Python archive contains the pinned CPython 3.14 standalone runtime and the
complete Python dependency closure from the hash-locked `uv.lock`, plus locked
`setuptools` and `wheel` build support. Installation performs no compilation,
package resolution, or network access.

The release publishes `manifest.json`, `SHA256SUMS`, `install.sh`, the provenance
attestation, and a coherent `cuestrap-tools-linux-amd64-offline.zip`. The release
installer verifies every required release asset, validates archive paths before
extraction, and verifies both archive and installed projections. Install from
GitHub's latest release:

```bash
curl --fail --location --proto '=https' --tlsv1.2 \
  https://github.com/fatb4f/cuestrap/releases/latest/download/install.sh \
  -o install.sh
bash install.sh
```

For blocked-egress or controlled environments, download or pre-stage the
release assets and install without network access:

```bash
# Upload into the same sandbox directory:
# Either upload cuestrap-tools-linux-amd64-offline.zip and extract it, or upload:
#   install.sh, SHA256SUMS, manifest.json,
#   cuestrap-tools-linux-amd64.tar.zst, attestation.jsonl
bash install.sh
```

`--source-dir /path/to/release-assets` is also supported when the files are not
beside the installer. `--verify-only` checks a staged upload without mutating the
environment, and `--print-manifest` prints its verified metadata. Installation
uses `versions/<lock-digest>` and atomically switches `current`; add
`<prefix>/current/bin` to `PATH`. `--doctor` runs the active installation's JSON
admission probe, including a complete offline gopy build and extension import.

The canonical lock digest is SHA-256 over the sorted, compact JSON export of
the CUE lock. Releases use `cuestrap-tools-<lock-digest>` as their tag.

## UV lock surface

The bundle carries this UV extension in `toolchain-uv.cue`:

```cue
tools: uv: {
    version:  "0.11.32"
    revision: "2cf57f594cacc1643947dfc89ae49fce5e66e29f"
    target:   "x86_64-unknown-linux-gnu"
    source:   "https://github.com/astral-sh/uv/releases/download/0.11.32/uv-x86_64-unknown-linux-gnu.tar.gz"
    sha256:   "0a48426481cac4927441f6875f7c7b07cfcc72cb96803d6e0103c55b8e3040cf"
}
```

The extension is unified with `environment/toolchain.cue`. If the base lock later
defines `tools.uv`, CUE requires the values to agree. The build downloads and
verifies UV before hydrating the locked Python environment, so UV is no longer
a host build prerequisite.

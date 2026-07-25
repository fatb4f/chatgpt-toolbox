# Linux AMD64 tool bundles

`environment/toolchain.cue` owns the tool versions and source revisions. The
primary distribution is the combined archive:

```text
cuestrap-tools-linux-amd64.tar.zst
```

The builder also produces five independently installable archives for caching
and maintenance:

```text
cuestrap-python-linux-amd64.tar.zst
cuestrap-go-linux-amd64.tar.zst
cuestrap-cue-linux-amd64.tar.zst
cuestrap-gopls-linux-amd64.tar.zst
cuestrap-gopy-linux-amd64.tar.zst
```

Build them from the repository root:

```bash
bash tools/bundles/build-linux-amd64.sh
```

The network-enabled build-authority environment must provide CUE so the builder
can export the canonical lock. The resulting archives do not require CUE for
installation; the CUE executable is itself one of the payloads.

Each archive contains `install.sh`, `archive-files.sha256`, and a distinct
installed-state checksum projection. The Go archive contains the complete
relocatable GOROOT plus `gofmt` and the pinned `goimports`. The gopy archive
contains the patched generator CLI and an exact, file-backed proxy for its
`gopyh` module; generated extension modules remain project-specific.

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

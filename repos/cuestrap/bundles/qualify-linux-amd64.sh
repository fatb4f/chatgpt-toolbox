#!/usr/bin/env bash
set -euo pipefail

release_dir=${1:?usage: qualify-linux-amd64.sh RELEASE_DIR WORK_DIR}
qualification_root=${2:?usage: qualify-linux-amd64.sh RELEASE_DIR WORK_DIR}
release_dir=$(CDPATH='' cd -- "$release_dir" && pwd)
mkdir -p "$qualification_root"
qualification_root=$(CDPATH='' cd -- "$qualification_root" && pwd)

for command_name in cc make sha256sum tar timeout zstd; do
	command -v "$command_name" >/dev/null 2>&1 || {
		echo "required qualification command unavailable: $command_name" >&2
		exit 1
	}
done

(
	cd "$release_dir"
	sha256sum --check --strict SHA256SUMS
)
bash "$release_dir/install.sh" --source-dir "$release_dir" --verify-only
bash "$release_dir/install.sh" --source-dir "$release_dir" --print-manifest >/dev/null

install_root="$qualification_root/install"
mkdir -p "$install_root/versions/previous/bin"
printf 'stale\n' > "$install_root/versions/previous/bin/stale-tool"
ln -s versions/previous "$install_root/current"
bash "$release_dir/install.sh" --source-dir "$release_dir" --prefix "$install_root"
prefix="$install_root/current"
[[ -L "$install_root/current" ]]
[[ ! -e "$prefix/bin/stale-tool" ]]

"$prefix/bin/python3" --version
"$prefix/bin/python3" -c 'import cffi, pybindgen, setuptools, ssl, sqlite3, wheel'
"$prefix/bin/pip" --version
"$prefix/bin/python3-config" --embed --ldflags | grep -F -- '/libexec/python/lib'
"$prefix/bin/go" version
printf 'package smoke\n' | "$prefix/bin/gofmt" >/dev/null
printf 'package smoke\n' | "$prefix/bin/goimports" >/dev/null
printf 'package smoke\nvalue: 2 + 2\n' | "$prefix/bin/cue" eval -e value -
"$prefix/bin/gopls" version
if timeout 5 "$prefix/bin/gopls" -mode=stdio </dev/null; then
	gopls_start_status=0
else
	gopls_start_status=$?
fi
[[ "$gopls_start_status" -eq 0 || "$gopls_start_status" -eq 124 ]]

gopy_help=
if gopy_help=$("$prefix/bin/gopy" -h 2>&1); then
	gopy_status=0
else
	gopy_status=$?
fi
[[ "$gopy_status" -eq 2 ]]
grep -q '^Usage of gopy:' <<< "$gopy_help"

go_smoke="$qualification_root/go-smoke"
mkdir -p "$go_smoke"
cat > "$go_smoke/go.mod" <<'EOF'
module qualification

go 1.22.0
EOF
cat > "$go_smoke/main.go" <<'EOF'
package main

func main() {}
EOF
mkdir -p "$go_smoke/cache"
(cd "$go_smoke" && GOCACHE="$go_smoke/cache" "$prefix/bin/go" build .)

"$prefix/bin/python3" "$prefix/share/cuestrap/verify_bundle.py" \
	installed "$prefix"
doctor_json="$qualification_root/doctor.json"
bash "$release_dir/install.sh" --prefix "$install_root" --doctor > "$doctor_json"
"$prefix/bin/python3" - "$doctor_json" <<'PY'
import json
import pathlib
import sys

document = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert document["schema"] == "cuestrap.doctor/v1"
assert document["platform"]["status"] == "pass"
assert document["tools"]["gopy"]["buildSmoke"] == "pass"
assert all(item["status"] == "pass" for item in document["tools"].values())
assert all(document["hostCapabilities"].values())
PY

expect_failure() {
	if "$@" >/dev/null 2>&1; then
		echo "command unexpectedly succeeded: $*" >&2
		exit 1
	fi
}

missing_checksums="$qualification_root/missing-checksums"
mkdir -p "$missing_checksums"
cp "$release_dir/install.sh" "$release_dir/manifest.json" \
	"$release_dir/cuestrap-tools-linux-amd64.tar.zst" "$missing_checksums/"
expect_failure bash "$missing_checksums/install.sh" --source-dir "$missing_checksums" \
	--verify-only

corrupted="$qualification_root/corrupted"
mkdir -p "$corrupted"
cp "$release_dir/install.sh" "$release_dir/manifest.json" "$release_dir/SHA256SUMS" \
	"$release_dir/cuestrap-tools-linux-amd64.tar.zst" "$corrupted/"
printf 'corruption\n' >> "$corrupted/cuestrap-tools-linux-amd64.tar.zst"
expect_failure bash "$corrupted/install.sh" --source-dir "$corrupted" --verify-only

wrong_target="$qualification_root/wrong-target"
mkdir -p "$wrong_target"
cp "$release_dir/install.sh" "$release_dir/manifest.json" \
	"$release_dir/cuestrap-tools-linux-amd64.tar.zst" "$wrong_target/"
"$prefix/bin/python3" - "$wrong_target/manifest.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
document = json.loads(path.read_text())
document["target"]["arch"] = "arm64"
path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
PY
(
	cd "$wrong_target"
	sha256sum cuestrap-tools-linux-amd64.tar.zst manifest.json install.sh > SHA256SUMS
)
expect_failure bash "$wrong_target/install.sh" --source-dir "$wrong_target" --verify-only

unsafe="$qualification_root/unsafe"
unsafe_stage="$qualification_root/unsafe-stage"
mkdir -p "$unsafe" "$unsafe_stage"
printf 'unsafe\n' > "$unsafe_stage/payload"
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
	--transform='s|^|../|' -cf - -C "$unsafe_stage" payload |
	zstd -10 -T2 --no-progress -o "$unsafe/cuestrap-tools-linux-amd64.tar.zst"
cp "$release_dir/install.sh" "$release_dir/manifest.json" "$unsafe/"
"$prefix/bin/python3" - "$unsafe/manifest.json" \
	"$unsafe/cuestrap-tools-linux-amd64.tar.zst" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest = pathlib.Path(sys.argv[1])
archive = pathlib.Path(sys.argv[2])
payload = archive.read_bytes()
document = json.loads(manifest.read_text())
document["archive"]["sha256"] = hashlib.sha256(payload).hexdigest()
document["archive"]["size"] = len(payload)
manifest.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
PY
(
	cd "$unsafe"
	sha256sum cuestrap-tools-linux-amd64.tar.zst manifest.json install.sh > SHA256SUMS
)
expect_failure bash "$unsafe/install.sh" --source-dir "$unsafe" --verify-only

printf 'gopy-smoke=pass\n'
printf 'promotion=not-promoted\n'

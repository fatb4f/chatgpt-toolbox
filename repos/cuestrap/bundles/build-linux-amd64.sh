#!/usr/bin/env bash
set -euo pipefail

repository_root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
output=${1:-"$repository_root/dist/bundles"}
work=$(mktemp -d)
cleanup() {
	chmod -R u+w -- "$work" 2>/dev/null || true
	rm -rf -- "$work"
}
trap cleanup EXIT

require() {
	command -v "$1" >/dev/null 2>&1 || {
		echo "required command unavailable: $1" >&2
		exit 1
	}
}

for command_name in bash cue curl git python3 sha256sum tar uv zstd; do
	require "$command_name"
done

mkdir -p "$output" "$work/download" "$work/source" "$work/stage"

lock_json="$work/toolchain-lock.json"
cue export "$repository_root/environment/toolchain.cue" -e bundle --out json > "$lock_json"
lock_digest=$(python3 - "$lock_json" <<'PY'
import hashlib
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
document = json.loads(path.read_text())
canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
path.write_bytes(canonical + b"\n")
print(hashlib.sha256(canonical).hexdigest())
PY
)

lock_value() {
	python3 - "$lock_json" "$@" <<'PY'
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text())
for key in sys.argv[2:]:
    value = value[key]
print(value)
PY
}

python_version=$(lock_value tools python version)
python_revision=$(lock_value tools python revision)
python_release=${python_revision##*/}
python_source=$(lock_value tools python source)
python_archive_sha256=$(lock_value tools python sha256)
go_version=$(lock_value tools go version)
go_revision=$(lock_value tools go revision)
go_source=$(lock_value tools go source)
go_archive_sha256=$(lock_value tools go sha256)
cue_version=$(lock_value tools cue version)
cue_revision=$(lock_value tools cue revision)
cue_source=$(lock_value tools cue source)
gopls_version=$(lock_value tools gopls version)
gopls_revision=$(lock_value tools gopls revision)
gopls_source=$(lock_value tools gopls source)
goimports_version=$(lock_value tools goimports version)
goimports_revision=$(lock_value tools goimports revision)
gopy_version=$(lock_value tools gopy version)
gopy_revision=$(lock_value tools gopy revision)
gopy_source=$(lock_value tools gopy source)
gopy_patch_path=$(lock_value tools gopy patch path)
gopy_patch_sha256=$(lock_value tools gopy patch sha256)
gopy_module_version=$(lock_value tools gopy offlineModule version)
uv_lock_path=$(lock_value pythonEnvironment lockPath)
uv_lock_sha256=$(lock_value pythonEnvironment sha256)
compression_level=$(lock_value archive compression level)
compression_threads=$(lock_value archive compression threads)

printf '%s  %s\n' "$uv_lock_sha256" "$repository_root/$uv_lock_path" |
	sha256sum --check --status
printf '%s  %s\n' "$gopy_patch_sha256" "$repository_root/$gopy_patch_path" |
	sha256sum --check --status

download_verified() {
	local source=$1 digest=$2 destination=$3
	curl --fail --location --proto '=https' --tlsv1.2 "$source" -o "$destination"
	printf '%s  %s\n' "$digest" "$destination" | sha256sum --check --status
}

python_archive="$work/download/cpython-${python_version}+${python_release}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
download_verified "$python_source" "$python_archive_sha256" "$python_archive"
mkdir -p "$work/python-standalone"
tar -xzf "$python_archive" -C "$work/python-standalone"

go_archive="$work/download/go${go_version}.linux-amd64.tar.gz"
download_verified "$go_source" "$go_archive_sha256" "$go_archive"
tar -xzf "$go_archive" -C "$work"

export GOROOT="$work/go"
export GOPATH="$work/gopath"
export GOMODCACHE="$work/gomodcache"
export PATH="$GOROOT/bin:$PATH"
export CGO_ENABLED=0
export GOOS=linux
export GOARCH=amd64
export GOTOOLCHAIN=local

checkout() {
	local url=$1 revision=$2 destination=$3
	git init --quiet "$destination"
	git -C "$destination" remote add origin "$url"
	git -C "$destination" fetch --quiet --depth=1 origin "$revision"
	git -C "$destination" checkout --quiet --detach FETCH_HEAD
	[[ $(git -C "$destination" rev-parse HEAD) == "$revision" ]]
}

checkout "$cue_source" "$cue_revision" "$work/source/cue"
checkout "$gopls_source" "$gopls_revision" "$work/source/tools"
checkout "$gopy_source" "$gopy_revision" "$work/source/gopy"
git -C "$work/source/gopy" apply --check --unidiff-zero \
	"$repository_root/$gopy_patch_path"
git -C "$work/source/gopy" apply --unidiff-zero \
	"$repository_root/$gopy_patch_path"

mkdir -p "$work/bin"
go_build_flags=(-trimpath -buildvcs=true '-ldflags=-s -w')
(cd "$work/source/cue" && go build "${go_build_flags[@]}" -o "$work/bin/cue" ./cmd/cue)
(cd "$work/source/tools/gopls" && go build "${go_build_flags[@]}" -o "$work/bin/gopls" .)
(cd "$work/source/tools" && go build "${go_build_flags[@]}" -o "$work/bin/goimports" ./cmd/goimports)
(cd "$work/source/gopy" && go build "${go_build_flags[@]}" -o "$work/bin/gopy" .)

make_stage() {
	local name=$1
	local stage="$work/stage/$name"
	mkdir -p "$stage/bin" "$stage/share/cuestrap"
	cp "$repository_root/tools/bundles/install.sh" "$stage/install.sh"
	cp "$repository_root/tools/bundles/verify_bundle.py" \
		"$stage/share/cuestrap/verify_bundle.py"
	chmod 0755 "$stage/install.sh" "$stage/share/cuestrap/verify_bundle.py"
	printf '%s\n' "$stage"
}

emit_component_manifest() {
	local stage=$1 name=$2 version=$3 revision=$4 upstream_digest=${5:-}
	python3 - "$stage" "$lock_json" "$lock_digest" "$name" "$version" \
		"$revision" "$upstream_digest" <<'PY'
import json
import pathlib
import sys

stage = pathlib.Path(sys.argv[1])
lock = json.loads(pathlib.Path(sys.argv[2]).read_text())
document = {
    "schema": "cuestrap.tool-bundle-manifest/v2",
    "lockDigest": sys.argv[3],
    "target": lock["target"],
    "hostRequirements": lock["hostRequirements"],
    "tool": {"name": sys.argv[4], "version": sys.argv[5], "revision": sys.argv[6]},
    "archive": {"checksumFile": "archive-files.sha256"},
    "installation": {
        "checksumFile": "share/cuestrap/installed-files.sha256",
        "omittedFiles": ["archive-files.sha256", "install.sh"],
        "mutablePaths": [],
    },
}
if sys.argv[7]:
    document["tool"]["upstreamArchiveSha256"] = sys.argv[7]
manifest = stage / "share" / "cuestrap" / "manifest.json"
manifest.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
PY
}

emit_combined_manifest() {
	local stage=$1
	python3 - "$stage" "$lock_json" "$lock_digest" <<'PY'
import json
import pathlib
import sys

stage = pathlib.Path(sys.argv[1])
lock = json.loads(pathlib.Path(sys.argv[2]).read_text())
document = {
    "schema": "cuestrap.combined-tool-bundle-manifest/v2",
    "lockDigest": sys.argv[3],
    "target": lock["target"],
    "hostRequirements": lock["hostRequirements"],
    "archivePolicy": lock["archive"],
    "pythonEnvironment": lock["pythonEnvironment"],
    "tools": lock["tools"],
    "archive": {"checksumFile": "archive-files.sha256"},
    "installation": {
        "checksumFile": "share/cuestrap/installed-files.sha256",
        "omittedFiles": ["archive-files.sha256", "install.sh"],
        "mutablePaths": [],
    },
}
manifest = stage / "share" / "cuestrap" / "manifest.json"
manifest.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
PY
}

write_projection_checksums() {
	local stage=$1
	python3 - "$stage" <<'PY'
import hashlib
import os
import pathlib
import sys

stage = pathlib.Path(sys.argv[1])
installed = stage / "share" / "cuestrap" / "installed-files.sha256"
archive = stage / "archive-files.sha256"

def files(excluded):
    for path in sorted(stage.rglob("*")):
        relative = path.relative_to(stage).as_posix()
        if relative in excluded:
            continue
        if path.is_file() or path.is_symlink():
            payload = (
                os.readlink(path).encode()
                if path.is_symlink()
                else path.read_bytes()
            )
            yield relative, hashlib.sha256(payload).hexdigest()

installed.parent.mkdir(parents=True, exist_ok=True)
installed.write_text("".join(
    f"{digest}  {relative}\n"
    for relative, digest in files({
        "install.sh",
        "archive-files.sha256",
        "share/cuestrap/installed-files.sha256",
    })
))
archive.write_text("".join(
    f"{digest}  {relative}\n"
    for relative, digest in files({"archive-files.sha256"})
))
PY
}

compress_stage() {
	local stage=$1 archive=$2
	tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
		-cf - -C "$stage" . |
		zstd "-$compression_level" "-T$compression_threads" --force --no-progress \
			-o "$archive"
}

go_stage=$(make_stage go)
mkdir -p "$go_stage/libexec"
cp -a "$GOROOT" "$go_stage/libexec/go"
cat > "$go_stage/bin/go" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
export GOTOOLCHAIN=local
exec "$prefix/libexec/go/bin/go" "$@"
EOF
cat > "$go_stage/bin/gofmt" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
exec "$prefix/libexec/go/bin/gofmt" "$@"
EOF
cp "$work/bin/goimports" "$go_stage/bin/goimports"
chmod 0755 "$go_stage/bin/go" "$go_stage/bin/gofmt" "$go_stage/bin/goimports"
emit_component_manifest "$go_stage" go "$go_version" "$go_revision" "$go_archive_sha256"
write_projection_checksums "$go_stage"

python_stage=$(make_stage python)
mkdir -p "$python_stage/libexec/python"
cp -a "$work/python-standalone/python/." "$python_stage/libexec/python/"
requirements="$work/cuestrap-requirements.txt"
uv export --project "$repository_root" --locked --no-dev --no-emit-project \
	--format requirements.txt --output-file "$requirements"
uv pip install --python "$python_stage/libexec/python/bin/python3" \
	--requirements "$requirements" --no-cache --no-build --strict

while IFS=$'\t' read -r package_name package_source package_sha256; do
	wheel_path="$work/download/${package_source##*/}"
	download_verified "$package_source" "$package_sha256" "$wheel_path"
done < <(python3 - "$lock_json" <<'PY'
import json
import pathlib
import sys

lock = json.loads(pathlib.Path(sys.argv[1]).read_text())
for name, wheel in sorted(lock["pythonEnvironment"]["additionalWheels"].items()):
    print(name, wheel["source"], wheel["sha256"], sep="\t")
PY
)
additional_requirements="$work/additional-requirements.txt"
python3 - "$lock_json" "$additional_requirements" <<'PY'
import json
import pathlib
import sys

lock = json.loads(pathlib.Path(sys.argv[1]).read_text())
lines = []
for name, wheel in sorted(lock["pythonEnvironment"]["additionalWheels"].items()):
    lines.append(f'{name}=={wheel["version"]} --hash=sha256:{wheel["sha256"]}\n')
pathlib.Path(sys.argv[2]).write_text("".join(lines))
PY
uv pip install --python "$python_stage/libexec/python/bin/python3" \
	--requirements "$additional_requirements" --no-index \
	--find-links "$work/download" --no-cache --no-build --strict

for executable in python python3; do
	cat > "$python_stage/bin/$executable" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
exec "$prefix/libexec/python/bin/python3" "$@"
EOF
	chmod 0755 "$python_stage/bin/$executable"
done
cat > "$python_stage/bin/python3-config" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
exec "$prefix/libexec/python/bin/python3-config" "$@"
EOF
cat > "$python_stage/bin/pip" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
exec "$prefix/libexec/python/bin/python3" -m pip "$@"
EOF
chmod 0755 "$python_stage/bin/python3-config" "$python_stage/bin/pip"
emit_component_manifest "$python_stage" python "$python_version" "$python_revision" "$python_archive_sha256"
write_projection_checksums "$python_stage"

for name in cue gopls; do
	stage=$(make_stage "$name")
	cp "$work/bin/$name" "$stage/bin/$name"
	chmod 0755 "$stage/bin/$name"
	case "$name" in
		cue) emit_component_manifest "$stage" cue "$cue_version" "$cue_revision" ;;
		gopls) emit_component_manifest "$stage" gopls "$gopls_version" "$gopls_revision" ;;
	esac
	write_projection_checksums "$stage"
done

gopy_stage=$(make_stage gopy)
mkdir -p "$gopy_stage/libexec/gopy" "$gopy_stage/share/cuestrap/goproxy/github.com/go-python/gopy/@v"
cp "$work/bin/gopy" "$gopy_stage/libexec/gopy/gopy"
chmod 0755 "$gopy_stage/libexec/gopy/gopy"
for artifact in info mod zip; do
	artifact_source=$(lock_value tools gopy offlineModule artifacts "$artifact" source)
	artifact_sha256=$(lock_value tools gopy offlineModule artifacts "$artifact" sha256)
	destination="$gopy_stage/share/cuestrap/goproxy/github.com/go-python/gopy/@v/${gopy_module_version}.${artifact}"
	download_verified "$artifact_source" "$artifact_sha256" "$destination"
done
printf '%s\n' "$gopy_module_version" > \
	"$gopy_stage/share/cuestrap/goproxy/github.com/go-python/gopy/@v/list"
cat > "$gopy_stage/bin/gopy" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
export PATH="$prefix/bin:$PATH"
export GOPROXY="file://$prefix/share/cuestrap/goproxy"
export GOSUMDB=off
export GONOPROXY=none
export GOPRIVATE=
export GOTOOLCHAIN=local
exec "$prefix/libexec/gopy/gopy" "$@"
EOF
chmod 0755 "$gopy_stage/bin/gopy"
emit_component_manifest "$gopy_stage" gopy "$gopy_version" "$gopy_revision"
write_projection_checksums "$gopy_stage"

for name in python go cue gopls gopy; do
	archive="$output/cuestrap-${name}-linux-amd64.tar.zst"
	compress_stage "$work/stage/$name" "$archive"
	(cd "$output" && sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256")
done

combined_stage=$(make_stage tools)
for name in python go cue gopls gopy; do
	cp -a "$work/stage/$name/bin/." "$combined_stage/bin/"
	if [[ -d "$work/stage/$name/libexec" ]]; then
		mkdir -p "$combined_stage/libexec"
		cp -a "$work/stage/$name/libexec/." "$combined_stage/libexec/"
	fi
done
mkdir -p "$combined_stage/share/cuestrap/goproxy"
cp -a "$gopy_stage/share/cuestrap/goproxy/." \
	"$combined_stage/share/cuestrap/goproxy/"
cp "$repository_root/tools/bundles/cuestrap_doctor.py" \
	"$combined_stage/share/cuestrap/cuestrap_doctor.py"
chmod 0755 "$combined_stage/share/cuestrap/cuestrap_doctor.py"
cat > "$combined_stage/bin/cuestrap-doctor" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
exec "$prefix/libexec/python/bin/python3" \
	"$prefix/share/cuestrap/cuestrap_doctor.py" "$@"
EOF
chmod 0755 "$combined_stage/bin/cuestrap-doctor"
emit_combined_manifest "$combined_stage"
write_projection_checksums "$combined_stage"

combined_archive="$output/cuestrap-tools-linux-amd64.tar.zst"
compress_stage "$combined_stage" "$combined_archive"

cp "$repository_root/tools/bundles/install-release.sh" "$output/install.sh"
chmod 0755 "$output/install.sh"
python3 - "$lock_json" "$combined_archive" "$lock_digest" "$output/manifest.json" <<'PY'
import hashlib
import json
import pathlib
import sys

lock = json.loads(pathlib.Path(sys.argv[1]).read_text())
archive = pathlib.Path(sys.argv[2])
payload = archive.read_bytes()
document = {
    "schema": "cuestrap.tool-release-manifest/v2",
    "lockDigest": sys.argv[3],
    "releaseTag": f"cuestrap-tools-{sys.argv[3]}",
    "target": lock["target"],
    "hostRequirements": lock["hostRequirements"],
    "tools": lock["tools"],
    "archive": {
        "name": archive.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    },
}
pathlib.Path(sys.argv[4]).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
PY

(
	cd "$output"
	sha256sum --check --strict ./*.tar.zst.sha256
	sha256sum cuestrap-tools-linux-amd64.tar.zst manifest.json install.sh > SHA256SUMS
)

archive_sha256=$(sha256sum "$combined_archive" | awk '{print $1}')
compressed_size=$(wc -c < "$combined_archive")
installed_size=$(du -sb "$combined_stage" | awk '{print $1}')
file_count=$(wc -l < "$combined_stage/share/cuestrap/installed-files.sha256")
printf 'lock-digest=%s\n' "$lock_digest"
printf 'release-tag=cuestrap-tools-%s\n' "$lock_digest"
printf 'archive-sha256=%s\n' "$archive_sha256"
printf 'compressed-size=%s\n' "$compressed_size"
printf 'installed-size=%s\n' "$installed_size"
printf 'file-count=%s\n' "$file_count"
printf 'tool-identities=cue:%s,gopls:%s,goimports:%s,gopy:%s\n' \
	"$cue_revision" "$gopls_revision" "$goimports_revision" "$gopy_revision"
printf 'gopy-smoke=not-run\n'
printf 'promotion=not-promoted\n'

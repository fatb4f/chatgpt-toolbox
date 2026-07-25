#!/usr/bin/env bash
set -euo pipefail

prefix="${HOME}/.local/cuestrap"
force=false
verify_only=false

usage() {
	cat <<'EOF'
Usage: install.sh [--prefix DIR] [--verify-only] [--force]

Verifies an extracted CUEstrap bundle and atomically activates it under
DIR/current, backed by DIR/versions/<lock-digest>.
EOF
}

while (($#)); do
	case "$1" in
		--prefix)
			[[ $# -ge 2 ]] || { echo "--prefix requires a value" >&2; exit 2; }
			prefix=$2
			shift 2
			;;
		--verify-only)
			verify_only=true
			shift
			;;
		--force)
			force=true
			shift
			;;
		--help|-h)
			usage
			exit 0
			;;
		*)
			echo "unknown argument: $1" >&2
			usage >&2
			exit 2
			;;
	esac
done

root=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
manifest="$root/share/cuestrap/manifest.json"
archive_checksums="$root/archive-files.sha256"

for required in "$manifest" "$archive_checksums"; do
	[[ -f "$required" ]] || { echo "missing bundle metadata: $required" >&2; exit 1; }
done
command -v sha256sum >/dev/null 2>&1 || {
	echo "required command unavailable: sha256sum" >&2
	exit 1
}
if [[ -x "$root/bin/python3" ]]; then
	"$root/bin/python3" "$root/share/cuestrap/verify_bundle.py" archive "$root"
else
	(cd "$root" && sha256sum --check --strict archive-files.sha256 >/dev/null)
fi

lock_digest=$(sed -n 's/^[[:space:]]*"lockDigest": "\([0-9a-f]*\)",*$/\1/p' "$manifest")
[[ "$lock_digest" =~ ^[0-9a-f]{64}$ ]] || {
	echo "embedded manifest has an invalid lock digest" >&2
	exit 1
}

if $verify_only; then
	printf 'verified lock digest %s\n' "$lock_digest"
	exit 0
fi

if [[ -L "$prefix" ]]; then
	echo "installation root must not be a symlink: $prefix" >&2
	exit 1
fi
mkdir -p "$prefix"
prefix=$(CDPATH='' cd -- "$prefix" && pwd)
if [[ "$prefix" == / || "$prefix" == "$HOME" ]]; then
	echo "refusing broad installation root: $prefix" >&2
	exit 1
fi
versions="$prefix/versions"
target="$versions/$lock_digest"
mkdir -p "$versions"

verify_installed() {
	local candidate=$1
	if [[ -x "$candidate/bin/python3" ]]; then
		"$candidate/bin/python3" \
			"$candidate/share/cuestrap/verify_bundle.py" installed "$candidate"
	else
		(
			cd "$candidate"
			sha256sum --check --strict share/cuestrap/installed-files.sha256 >/dev/null
		)
	fi
}

activate() {
	local activation="$prefix/.current.$$.tmp"
	ln -s "versions/$lock_digest" "$activation"
	mv -Tf "$activation" "$prefix/current"
}

if [[ -d "$target" ]] && ! $force; then
	verify_installed "$target" || {
		echo "existing version is invalid; rerun with --force to replace it" >&2
		exit 1
	}
	activate
	echo "activated existing version $lock_digest"
	echo "export PATH=$prefix/current/bin:\$PATH"
	exit 0
fi

candidate=$(mktemp -d "$versions/.install.${lock_digest}.XXXXXX")
cleanup() {
	if [[ -n "$candidate" && -d "$candidate" ]]; then
		rm -rf -- "$candidate"
	fi
}
trap cleanup EXIT

mkdir -p "$candidate/bin" "$candidate/share/cuestrap"
cp -a "$root/bin/." "$candidate/bin/"
cp -a "$root/share/cuestrap/." "$candidate/share/cuestrap/"
if [[ -d "$root/libexec" ]]; then
	mkdir -p "$candidate/libexec"
	cp -a "$root/libexec/." "$candidate/libexec/"
fi

verify_installed "$candidate"
if [[ -x "$candidate/bin/cuestrap-doctor" ]]; then
	"$candidate/bin/cuestrap-doctor" --json >/dev/null
fi

if [[ -e "$target" ]]; then
	mv --help | grep -q -- '--exchange' || {
		echo "--force replacement requires mv --exchange" >&2
		exit 1
	}
	mv --exchange -T "$candidate" "$target"
else
	mv -T "$candidate" "$target"
	candidate=
fi
activate

if [[ -n "$candidate" && -d "$candidate" ]]; then
	rm -rf -- "$candidate"
	candidate=
fi

echo "installed version $lock_digest into $target"
echo "export PATH=$prefix/current/bin:\$PATH"

#!/usr/bin/env bash
set -euo pipefail

archive_name=cuestrap-tools-linux-amd64.tar.zst
prefix=${CUESTRAP_PREFIX:-"${HOME}/.local/cuestrap"}
base_url=${CUESTRAP_RELEASE_URL:-https://github.com/fatb4f/cuestrap/releases/latest/download}
source_dir=
force=false
verify_only=false
print_manifest=false
doctor=false
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

if [[ -f "$script_dir/$archive_name" && -f "$script_dir/SHA256SUMS" && \
	-f "$script_dir/manifest.json" ]]; then
	source_dir=$script_dir
fi

usage() {
	cat <<'EOF'
Usage: install.sh [OPTIONS]

Options:
  --prefix DIR       Installation root (default: ~/.local/cuestrap)
  --source-dir DIR   Read a coherent offline asset set from DIR
  --base-url URL     Download release assets from URL
  --verify-only      Verify the release without changing the installation
  --print-manifest   Verify and print the release manifest
  --doctor           Run the active installation's machine-readable doctor
  --force            Replace an invalid version with the same lock digest
  --help             Show this help
EOF
}

while (($#)); do
	case "$1" in
		--prefix)
			[[ $# -ge 2 ]] || { echo "--prefix requires a value" >&2; exit 2; }
			prefix=$2
			shift 2
			;;
		--base-url)
			[[ $# -ge 2 ]] || { echo "--base-url requires a value" >&2; exit 2; }
			base_url=${2%/}
			source_dir=
			shift 2
			;;
		--source-dir)
			[[ $# -ge 2 ]] || { echo "--source-dir requires a value" >&2; exit 2; }
			source_dir=$2
			shift 2
			;;
		--verify-only)
			verify_only=true
			shift
			;;
		--print-manifest)
			print_manifest=true
			shift
			;;
		--doctor)
			doctor=true
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

if $doctor; then
	[[ -x "$prefix/current/bin/cuestrap-doctor" ]] || {
		echo "no active CUEstrap installation under $prefix" >&2
		exit 1
	}
	exec "$prefix/current/bin/cuestrap-doctor" --json
fi

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
	echo "this bundle requires Linux on x86_64" >&2
	exit 1
fi

for command_name in sha256sum tar zstd; do
	command -v "$command_name" >/dev/null 2>&1 || {
		echo "required command unavailable: $command_name" >&2
		exit 1
	}
done

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT

if [[ -n "$source_dir" ]]; then
	for asset in "$archive_name" SHA256SUMS manifest.json install.sh; do
		[[ -f "$source_dir/$asset" ]] || {
			echo "offline asset is missing: $source_dir/$asset" >&2
			exit 1
		}
		cp "$source_dir/$asset" "$work/$asset"
	done
else
	command -v curl >/dev/null 2>&1 || {
		echo "required command unavailable: curl" >&2
		exit 1
	}
	for asset in "$archive_name" SHA256SUMS manifest.json install.sh; do
		curl --fail --location --proto '=https' --tlsv1.2 \
			"$base_url/$asset" -o "$work/$asset"
	done
fi

(
	cd "$work"
	sha256sum --check --strict SHA256SUMS
)

path_is_safe() {
	local value=$1 depth=0 part
	[[ -n "$value" && "$value" != /* && "$value" != *$'\n'* && \
		"$value" != *$'\r'* && "$value" != *$'\t'* ]] || return 1
	IFS='/' read -r -a parts <<< "$value"
	for part in "${parts[@]}"; do
		case "$part" in
			''|.) ;;
			..)
				((depth > 0)) || return 1
				((depth -= 1))
				;;
			*) ((depth += 1)) ;;
		esac
	done
	return 0
}

validate_archive_paths() {
	local archive=$1 member mode owner size date time description target joined
	while IFS= read -r member; do
		path_is_safe "$member" || {
			echo "unsafe archive member: $member" >&2
			return 1
		}
	done < <(tar --zstd -tf "$archive")

	while read -r mode owner size date time description; do
		case "$mode" in
			l*)
				[[ "$description" == *' -> '* ]] || return 1
				member=${description%% -> *}
				target=${description#* -> }
				joined="${member%/*}/$target"
				path_is_safe "$joined" || {
					echo "unsafe symlink target: $member -> $target" >&2
					return 1
				}
				;;
			h*)
				[[ "$description" == *' link to '* ]] || return 1
				member=${description%% link to *}
				target=${description#* link to }
				path_is_safe "$target" || {
					echo "unsafe hardlink target: $member -> $target" >&2
					return 1
				}
				;;
		esac
	done < <(tar --zstd -tvf "$archive")
}

validate_archive_paths "$work/$archive_name"
mkdir -p "$work/extracted"
tar --zstd -xf "$work/$archive_name" -C "$work/extracted"
"$work/extracted/bin/python3" \
	"$work/extracted/share/cuestrap/verify_bundle.py" archive "$work/extracted"
"$work/extracted/bin/python3" \
	"$work/extracted/share/cuestrap/verify_bundle.py" release \
	"$work/extracted" "$work/manifest.json" "$work/$archive_name"

if $print_manifest; then
	cat "$work/manifest.json"
	exit 0
fi
if $verify_only; then
	echo "release verification passed"
	exit 0
fi

install_arguments=(--prefix "$prefix")
if $force; then
	install_arguments+=(--force)
fi
bash "$work/extracted/install.sh" "${install_arguments[@]}"

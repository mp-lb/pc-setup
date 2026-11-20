#!/bin/bash
set -euo pipefail

kernel=$(uname -s)
case "$kernel" in
  Darwin)
    platform=macos
    detected=macOS
    ;;
  Linux)
    if [ -r /etc/os-release ]; then
      . /etc/os-release
    fi
    if [ "${ID:-}" != ubuntu ]; then
      printf 'Unsupported operating system: %s\n' "${PRETTY_NAME:-Linux}" >&2
      exit 1
    fi
    platform=ubuntu
    detected="${PRETTY_NAME:-Ubuntu}"
    ;;
  *)
    printf 'Unsupported operating system: %s\n' "$kernel" >&2
    exit 1
    ;;
esac

printf 'Detected %s. Proceed with PC setup? [y/N] ' "$detected"
if ! read -r reply || [[ "$reply" != [Yy] && "$reply" != [Yy][Ee][Ss] ]]; then
  printf 'Setup cancelled.\n'
  exit 0
fi

if [ "$EUID" -eq 0 ]; then
  printf 'Run setup as your normal user with access to sudo.\n' >&2
  exit 1
fi

export PC_SETUP_REPO_SLUG=mp-lb/pc-setup
recipe="os/$platform/setup.sh"
script_file="${BASH_SOURCE[0]:-}"
if [[ -f "$script_file" && "$script_file" != /dev/fd/* ]]; then
  script_dir=$(cd "$(dirname "$script_file")" && pwd)
  if [ -f "$script_dir/$recipe" ]; then
    if [ -z "${PC_SETUP_REPO_PATH:-}" ] && [ -z "${PC_SETUP_WORKSPACE:-}" ]; then
      export PC_SETUP_REPO_PATH="$script_dir"
    fi
    exec /bin/bash "$script_dir/$recipe"
  fi
fi

recipe_source=$(curl -fsSL "https://raw.githubusercontent.com/$PC_SETUP_REPO_SLUG/main/$recipe")
exec /bin/bash -c "$recipe_source"

#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/paths.sh"

source "$PC_SETUP_REPO_PATH/lib/runtime-path.sh"

if command -v mise >/dev/null 2>&1; then
  PATH="$(mise exec -- printenv PATH)"
  export PATH
fi

print_version() {
  local label="$1"
  local command_name="$2"
  shift 2

  if command -v "$command_name" >/dev/null 2>&1; then
    printf "%-18s %s\n" "$label" "$("$command_name" "$@" 2>&1 | awk 'NF { print; exit }')"
  else
    printf "%-18s missing\n" "$label"
  fi
}

echo "pc-setup inventory"
echo
print_version "gh" gh --version
print_version "mise" mise --version
print_version "node" node --version
print_version "npm" npm --version
print_version "pnpm" pnpm --version
print_version "claude" claude --version
print_version "fm" fm --version
print_version "berth" berth --version
print_version "zap" zap --version
print_version "clerk" clerk --version
print_version "aws" aws --version
print_version "gcloud" gcloud --version
print_version "tree" tree --version
print_version "task" task --version
print_version "overmind" overmind --version
print_version "docker" docker --version

echo
echo "mise tools"
if command -v mise >/dev/null 2>&1; then
  mise list || true
else
  echo "mise missing"
fi

echo
if [[ "$OSTYPE" == darwin* ]]; then
  source "$SCRIPT_DIR/os/macos/inventory.sh"
else
  source "$SCRIPT_DIR/os/ubuntu/inventory.sh"
fi

echo
echo "global agent skills"
if command -v npm >/dev/null 2>&1; then
  npx --yes skills list --global || true
else
  echo "npm missing"
fi

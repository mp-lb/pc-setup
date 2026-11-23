#!/bin/bash
set -euo pipefail

# This is optional: public setup must work without access to this private repo.
repo=felixsebastian/ubuntu-fonts
if [ "$(gh api "repos/$repo" --jq .private 2>/dev/null)" != true ]; then
  exit 0
fi

workspace="${PC_SETUP_WORKSPACE:-$HOME/Work}"
checkout="$workspace/ubuntu-fonts"
mkdir -p "$workspace"
if [ ! -e "$checkout" ]; then
  gh repo clone "$repo" "$checkout"
else
  origin="$(git -C "$checkout" remote get-url origin)"
  case "$origin" in
    "https://github.com/$repo"|"https://github.com/$repo.git"|"git@github.com:$repo.git"|"ssh://git@github.com/$repo.git") ;;
    *) echo "Unexpected repository at $checkout; leaving it untouched." >&2; exit 1 ;;
  esac
  if [ -n "$(git -C "$checkout" status --porcelain)" ]; then
    echo "Uncommitted changes at $checkout; leaving them untouched." >&2
    exit 1
  fi
  git -C "$checkout" pull --ff-only
fi
bash "$checkout/install.sh"

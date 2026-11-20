#!/bin/bash
set -euo pipefail

export PC_SETUP_WORKSPACE="${PC_SETUP_WORKSPACE:-${PC_SETUP_REPO_PATH:+$(dirname "$PC_SETUP_REPO_PATH")}}"
export PC_SETUP_WORKSPACE="${PC_SETUP_WORKSPACE:-$HOME/Work}"
export PC_SETUP_REPO_PATH="${PC_SETUP_REPO_PATH:-$PC_SETUP_WORKSPACE/pc-setup}"

sudo apt-get update
if ! command -v gh >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
  sudo apt-get install -y ca-certificates curl git gh
fi

gh auth status --hostname github.com >/dev/null 2>&1 || gh auth login --hostname github.com
gh auth setup-git --hostname github.com
mkdir -p "$PC_SETUP_WORKSPACE"
if [ ! -f "$PC_SETUP_REPO_PATH/start.sh" ] && [ ! -e "$PC_SETUP_REPO_PATH/.git" ]; then
  gh repo clone "$PC_SETUP_REPO_SLUG" "$PC_SETUP_REPO_PATH"
fi

mapfile -t packages < "$PC_SETUP_REPO_PATH/os/ubuntu/apt-packages.txt"
sudo apt-get install -y "${packages[@]}"

export PATH="$HOME/.local/bin:$PATH"
command -v mise >/dev/null 2>&1 || curl -fsSL https://mise.run | sh
command -v claude >/dev/null 2>&1 || curl -fsSL https://claude.ai/install.sh | bash

mise use --global overmind@2.5.1

source "$PC_SETUP_REPO_PATH/lib/setup-user.sh"
setup_user

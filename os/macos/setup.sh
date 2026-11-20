#!/bin/bash
set -euo pipefail

export PC_SETUP_WORKSPACE="${PC_SETUP_WORKSPACE:-${PC_SETUP_REPO_PATH:+$(dirname "$PC_SETUP_REPO_PATH")}}"
export PC_SETUP_WORKSPACE="${PC_SETUP_WORKSPACE:-$HOME/Work}"
export PC_SETUP_REPO_PATH="${PC_SETUP_REPO_PATH:-$PC_SETUP_WORKSPACE/pc-setup}"

if ! command -v brew >/dev/null 2>&1 && [ ! -x /opt/homebrew/bin/brew ] && [ ! -x /usr/local/bin/brew ]; then
  installer=$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)
  /bin/bash -c "$installer"
fi
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi
command -v gh >/dev/null 2>&1 || brew install gh

gh auth status --hostname github.com >/dev/null 2>&1 || gh auth login --hostname github.com
gh auth setup-git --hostname github.com
mkdir -p "$PC_SETUP_WORKSPACE"
if [ ! -f "$PC_SETUP_REPO_PATH/start.sh" ] && [ ! -e "$PC_SETUP_REPO_PATH/.git" ]; then
  gh repo clone "$PC_SETUP_REPO_SLUG" "$PC_SETUP_REPO_PATH"
fi

brew bundle --file "$PC_SETUP_REPO_PATH/os/macos/Brewfile"

source "$PC_SETUP_REPO_PATH/lib/shell-profile.sh"
if [ "$shell_profile" = zsh ] && [ ! -d "$HOME/.oh-my-zsh" ]; then
  installer=$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)
  KEEP_ZSHRC=yes sh -c "$installer" "" --unattended
fi

source "$PC_SETUP_REPO_PATH/lib/setup-user.sh"
setup_user

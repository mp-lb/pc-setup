# Sourced by Bash scripts and shell startup files, including non-interactive zsh.
if [[ "$OSTYPE" == darwin* ]]; then
  source "$PC_SETUP_REPO_PATH/os/macos/path.sh"
fi
export PATH="$HOME/.local/bin:$HOME/.local/share/npm-global/bin:$PATH"

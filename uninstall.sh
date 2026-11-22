#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/output.sh"
source "$SCRIPT_DIR/lib/paths.sh"

log "Removing legacy pc-setup-managed runtimes."

if [ -f "$HOME/.nvm/nvm.sh" ]; then
  source "$HOME/.nvm/nvm.sh"
  npm uninstall -g pnpm pm2 zapper-cli @mp-lb/zapper clerk 2>/dev/null || true
fi

rm -rf "$HOME/.nvm"
rm -rf "$HOME/.pyenv"
rm -rf "$HOME/.rbenv"
rm -rf "$HOME/google-cloud-sdk"
if [[ "$OSTYPE" == darwin* ]]; then
  source "$SCRIPT_DIR/os/macos/uninstall-legacy.sh"
fi
rm -rf "$HOME/.config/pypoetry"

if [ "${1:-}" = "--all" ]; then
  log "Removing current mise-managed runtime state."
  rm -rf "$HOME/.local/share/mise"
  rm -rf "$HOME/.config/mise"
fi

for rc_file in "$HOME"/.{bashrc,bash_profile,bash_login,profile} "${ZDOTDIR:-$HOME}"/.{zshenv,zshrc}; do
  if grep -Fxq '# >>> pc-setup >>>' "$rc_file" 2>/dev/null &&
     grep -Fxq '# <<< pc-setup <<<' "$rc_file"; then
    updated_rc=$(mktemp)
    awk '
      $0 == "# >>> pc-setup >>>" { in_block = 1; next }
      $0 == "# <<< pc-setup <<<" { in_block = 0; next }
      !in_block
      END { if (in_block) exit 1 }
    ' "$rc_file" > "$updated_rc" && cat "$updated_rc" > "$rc_file"
    rm -f "$updated_rc"
  elif grep -Fq 'PC_SETUP_REPO_PATH/env/zshrc' "$rc_file" 2>/dev/null; then
    note "Remove the legacy pc-setup lines from $rc_file if desired."
  fi
done

success "Legacy pc-setup-managed runtime cleanup complete."
note "Homebrew, gh auth, git config, $PC_SETUP_WORKSPACE, and project files were intentionally left in place."

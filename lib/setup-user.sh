#!/bin/bash

setup_user() {
  local installer login_shell mise_trusted_paths
  local git_name git_email

  . "$PC_SETUP_REPO_PATH/lib/output.sh"
  . "$PC_SETUP_REPO_PATH/lib/runtime-path.sh"

  if ! git config --global user.name >/dev/null; then
    read -r -p 'Enter your full name for git commits: ' git_name
    git config --global user.name "$git_name"
  fi
  if ! git config --global user.email >/dev/null; then
    read -r -p 'Enter your email for git commits: ' git_email
    git config --global user.email "$git_email"
  fi

  mise_trusted_paths=$(
    unset MISE_TRUSTED_CONFIG_PATHS
    mise settings get trusted_config_paths
  )
  case "$mise_trusted_paths" in
    *'"~/Work"'*|*"\"$HOME/Work\""*) ;;
    *)
      log "Trusting mise configs under $HOME/Work."
      mise settings add trusted_config_paths '~/Work'
      ;;
  esac

  log "Installing default mise tools."
  mise use --global node@lts pnpm@latest aqua:go-task/task@latest
  "$PC_SETUP_REPO_PATH/bin/install-host-clis"

  if ! fm auth status | grep -Fxq 'Authenticated'; then
    fm auth login
  fi
  "$PC_SETUP_REPO_PATH/bin/install-global-instructions"
  "$PC_SETUP_REPO_PATH/bin/install-skills"

  "$PC_SETUP_REPO_PATH/bin/install-shell"

  if [ ! -f "$HOME/.oh-my-zsh/oh-my-zsh.sh" ]; then
    log "Installing Oh My Zsh."
    installer=$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)
    ZSH="$HOME/.oh-my-zsh" KEEP_ZSHRC=yes sh -c "$installer" "" --unattended
  fi

  mkdir -p "$HOME/.aws"
  if [ ! -e "$HOME/.aws/config" ] && [ ! -L "$HOME/.aws/config" ]; then
    install -m 600 "$PC_SETUP_REPO_PATH/env/aws-config" "$HOME/.aws/config"
  elif ! cmp -s "$PC_SETUP_REPO_PATH/env/aws-config" "$HOME/.aws/config"; then
    note "Kept your existing AWS config. MAP Lab profiles are in $PC_SETUP_REPO_PATH/env/aws-config."
  fi

  login_shell=$(get_login_shell)
  if [[ "$login_shell" != */zsh ]]; then
    log "Setting zsh as the login shell."
    sudo chsh -s /bin/zsh "$(id -un)"
  fi

  success "PC setup finished. Open a new terminal and run $PC_SETUP_REPO_PATH/doctor.sh."
}

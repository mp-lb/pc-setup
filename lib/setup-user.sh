#!/bin/bash

setup_user() {
  local shell_profile rc_file
  local git_name git_email

  . "$PC_SETUP_REPO_PATH/lib/shell-profile.sh"
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

  log "Installing default mise tools."
  mise use --global node@lts pnpm@latest aqua:go-task/task@latest
  mise exec -- npm install -g @mp-lb/forum-cli @mp-lb/berth @mp-lb/zapper pm2 clerk

  "$PC_SETUP_REPO_PATH/bin/install-skills"

  if ! grep -Fq '# >>> pc-setup >>>' "$rc_file" 2>/dev/null &&
     ! grep -Fq 'PC_SETUP_REPO_PATH/env/zshrc' "$rc_file" 2>/dev/null; then
    log "Adding the shell bridge to $rc_file."
    {
      printf '\n# >>> pc-setup >>>\n'
      printf 'export PC_SETUP_WORKSPACE=%q\n' "$PC_SETUP_WORKSPACE"
      printf 'export PC_SETUP_REPO_PATH=%q\n' "$PC_SETUP_REPO_PATH"
      printf 'source "$PC_SETUP_REPO_PATH/env/%src"\n' "$shell_profile"
      printf '# <<< pc-setup <<<\n'
    } >> "$rc_file"
  fi

  mkdir -p "$HOME/.aws"
  if [ ! -e "$HOME/.aws/config" ] && [ ! -L "$HOME/.aws/config" ]; then
    install -m 600 "$PC_SETUP_REPO_PATH/env/aws-config" "$HOME/.aws/config"
  elif ! cmp -s "$PC_SETUP_REPO_PATH/env/aws-config" "$HOME/.aws/config"; then
    note "Kept your existing AWS config. MAP Lab profiles are in $PC_SETUP_REPO_PATH/env/aws-config."
  fi

  success "PC setup finished. Open a new terminal and run $PC_SETUP_REPO_PATH/doctor.sh."
}

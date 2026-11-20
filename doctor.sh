#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/output.sh"
source "$SCRIPT_DIR/lib/paths.sh"

failures=0

check_command() {
  local name="$1"
  local command_name="$2"
  shift 2

  if command -v "$command_name" >/dev/null 2>&1; then
    if [ "$#" -gt 0 ] && ! "$command_name" "$@" >/dev/null 2>&1; then
      error "$name: command exists but health check failed"
      failures=$((failures + 1))
      return
    fi

    success "$name: $(command -v "$command_name")"
  else
    error "$name: missing command '$command_name'"
    failures=$((failures + 1))
  fi
}

check_absent_dir() {
  local label="$1"
  local dir="$2"

  if [ -d "$dir" ]; then
    error "$label: legacy directory still exists at $dir"
    failures=$((failures + 1))
  else
    success "$label: absent"
  fi
}

check_recommended_command() {
  local name="$1"
  local command_name="$2"
  shift 2

  if command -v "$command_name" >/dev/null 2>&1; then
    if [ "$#" -gt 0 ] && ! "$command_name" "$@" >/dev/null 2>&1; then
      note "$name: optional command '$command_name' is installed but unhealthy"
      return
    fi

    success "$name: $(command -v "$command_name")"
  else
    note "$name: optional command '$command_name' is not installed"
  fi
}

source "$PC_SETUP_REPO_PATH/lib/runtime-path.sh"

if command -v mise >/dev/null 2>&1; then
  PATH="$(mise exec -- printenv PATH)"
  export PATH
fi

log "Checking host tools."
check_command "GitHub CLI" gh
check_command "mise" mise
check_command "Node" node --version
check_command "pnpm" pnpm --version
check_command "Claude Code" claude --version
check_command "Forum" fm --version
check_command "Berth" berth --version
check_command "Zapper" zap --version
check_command "Clerk CLI" clerk --version
check_command "AWS CLI" aws --version
check_command "Overmind" overmind --version
check_command "Go Task" task --version
check_command "lsof" lsof
check_command "tree" tree --version
if [[ "$OSTYPE" == darwin* ]]; then
  source "$SCRIPT_DIR/os/macos/doctor.sh"
else
  source "$SCRIPT_DIR/os/ubuntu/doctor.sh"
fi

log "Checking GitHub Git credentials."
if git config --global --get-all credential.https://github.com.helper | grep -Eq 'gh[[:space:]]+auth[[:space:]]+git-credential'; then
  success "GitHub: Git uses the gh credential helper"
else
  error "GitHub: run gh auth setup-git --hostname github.com"
  failures=$((failures + 1))
fi

log "Checking legacy runtime cleanup."
check_absent_dir "nvm" "$HOME/.nvm"
check_absent_dir "pyenv" "$HOME/.pyenv"
check_absent_dir "rbenv" "$HOME/.rbenv"
check_absent_dir "old gcloud installer" "$HOME/google-cloud-sdk"

# shellcheck source=lib/shell-profile.sh
source "$PC_SETUP_REPO_PATH/lib/shell-profile.sh"
if grep -Fq "PC_SETUP_REPO_PATH/env/${shell_profile}rc" "$rc_file" 2>/dev/null; then
  success "Shell bridge: $rc_file sources pc-setup"
else
  error "Shell bridge: $rc_file does not source pc-setup"
  failures=$((failures + 1))
fi

if [ -f "$HOME/.aws/config" ] && cmp -s "$SCRIPT_DIR/env/aws-config" "$HOME/.aws/config"; then
  success "AWS config: ~/.aws/config matches pc-setup"
elif [ -f "$HOME/.aws/config" ]; then
  note "AWS config: existing file differs from the MAP Lab template"
else
  error "AWS config: ~/.aws/config is missing"
  failures=$((failures + 1))
fi

if [ "$failures" -eq 0 ]; then
  success "Doctor passed."
else
  error "Doctor found $failures issue(s)."
  exit 1
fi

#!/bin/bash

if [ -n "${ZSH_VERSION:-}" ]; then
  _PC_SETUP_PATHS_SOURCE="${(%):-%x}"
elif [ -n "${BASH_SOURCE:-}" ]; then
  _PC_SETUP_PATHS_SOURCE="${BASH_SOURCE[0]}"
else
  _PC_SETUP_PATHS_SOURCE="$0"
fi

case "$_PC_SETUP_PATHS_SOURCE" in
  /dev/fd/*|/proc/*|/private/dev/fd/*)
    _PC_SETUP_DEFAULT_WORKSPACE="$HOME/Work"
    _PC_SETUP_DEFAULT_REPO_PATH="$_PC_SETUP_DEFAULT_WORKSPACE/pc-setup"
    ;;
  *)
    _PC_SETUP_PATHS_DIR="$(cd "$(dirname "$_PC_SETUP_PATHS_SOURCE")" && pwd)"
    _PC_SETUP_DEFAULT_REPO_PATH="$(cd "$_PC_SETUP_PATHS_DIR/.." && pwd)"
    _PC_SETUP_DEFAULT_WORKSPACE="$(dirname "$_PC_SETUP_DEFAULT_REPO_PATH")"
    ;;
esac

if [ -n "${PC_SETUP_REPO_PATH:-}" ] && [ -z "${PC_SETUP_WORKSPACE:-}" ]; then
  export PC_SETUP_WORKSPACE="$(dirname "$PC_SETUP_REPO_PATH")"
else
  export PC_SETUP_WORKSPACE="${PC_SETUP_WORKSPACE:-$_PC_SETUP_DEFAULT_WORKSPACE}"
fi

export PC_SETUP_REPO_PATH="${PC_SETUP_REPO_PATH:-$PC_SETUP_WORKSPACE/pc-setup}"

unset _PC_SETUP_PATHS_SOURCE
unset _PC_SETUP_PATHS_DIR
unset _PC_SETUP_DEFAULT_WORKSPACE
unset _PC_SETUP_DEFAULT_REPO_PATH

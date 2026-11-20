case "${SHELL:-}" in
  */zsh)
    shell_profile=zsh
    rc_file="$HOME/.zshrc"
    ;;
  *)
    shell_profile=bash
    rc_file="$HOME/.bashrc"
    if [[ "$OSTYPE" == darwin* ]]; then
      source "$PC_SETUP_REPO_PATH/os/macos/bash-profile.sh"
    fi
    ;;
esac

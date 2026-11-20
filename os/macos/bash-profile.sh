# macOS Terminal starts Bash as a login shell.
rc_file="$HOME/.bash_profile"
if [ ! -e "$rc_file" ]; then
  if [ -e "$HOME/.bash_login" ]; then
    rc_file="$HOME/.bash_login"
  elif [ -e "$HOME/.profile" ]; then
    rc_file="$HOME/.profile"
  fi
fi

# Apple Silicon and Intel Homebrew paths.
if [ -x /opt/homebrew/bin/brew ]; then
  export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
elif [ -x /usr/local/bin/brew ]; then
  export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
fi

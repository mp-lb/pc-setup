print_version "brew" brew --version
echo "Homebrew bundle"
if command -v brew >/dev/null 2>&1; then
  brew bundle check --file "$PC_SETUP_REPO_PATH/os/macos/Brewfile" || true
fi

#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -eq 0 ]; then
  echo "Run as your regular desktop user." >&2
  exit 1
fi
command -v fc-cache >/dev/null || { echo "Missing command: fc-cache (fontconfig)" >&2; exit 1; }

# Berkeley Mono is supplied by the user, never bundled in this repository.
if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ ! -f "$1/BerkeleyMono-Regular.otf" ]; }; then
  echo "Usage: $0 [directory-containing-BerkeleyMono-Regular.otf]" >&2
  exit 1
fi

font_dir="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/pc-setup"
mkdir -p "$font_dir"
install -m 644 "$SCRIPT_DIR"/desktop/fonts/*.ttf "$font_dir/"
install -m 644 "$SCRIPT_DIR/desktop/fonts/COPYRIGHT" "$font_dir/IBM-Plex-COPYRIGHT"
fc-cache -f "$font_dir"
echo "Installed IBM Plex Sans for the current user."

if [ "$#" -eq 1 ]; then
  berkeley_dir="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/berkeley-mono"
  mkdir -p "$berkeley_dir"
  install -m 644 "$1"/BerkeleyMono-*.otf "$berkeley_dir/"
  fc-cache -f "$berkeley_dir"
  echo "Installed Berkeley Mono for the current user."
  echo "Restart terminal apps to discover new fonts; ptyxis --standalone opens a fresh instance without closing sessions."
fi

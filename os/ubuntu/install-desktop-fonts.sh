#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -eq 0 ]; then
  echo "Run as your regular desktop user." >&2
  exit 1
fi
command -v fc-cache >/dev/null || { echo "Missing command: fc-cache (fontconfig)" >&2; exit 1; }

font_dir="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/pc-setup"
mkdir -p "$font_dir"
install -m 644 "$SCRIPT_DIR"/desktop/fonts/*.ttf "$font_dir/"
install -m 644 "$SCRIPT_DIR/desktop/fonts/COPYRIGHT" "$font_dir/IBM-Plex-COPYRIGHT"
fc-cache -f "$font_dir"
echo "Installed IBM Plex Sans and Mono for the current user."

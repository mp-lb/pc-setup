#!/bin/bash
# Optional desktop app; deliberately excluded from the base bootstrap.
set -euo pipefail

[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || {
  echo 'This installer requires x86_64 Linux.' >&2; exit 1;
}
[[ $EUID != 0 ]] || { echo 'Run as your regular desktop user.' >&2; exit 1; }
[[ $# -le 1 ]] || { echo "Usage: $0 [T3-Code-x86_64.AppImage]" >&2; exit 2; }
downloads=$(xdg-user-dir DOWNLOAD 2>/dev/null || true)
[[ "$downloads" == /* && "$downloads" != "$HOME" ]] || downloads="$HOME/Downloads"
source_image=${1:-"$downloads/T3-Code-x86_64.AppImage"}
[[ -f "$source_image" ]] || { echo "AppImage not found: $source_image" >&2; exit 1; }
command -v python3 >/dev/null

app_dir="$HOME/.local/opt/t3-code"
data_dir=${XDG_DATA_HOME:-"$HOME/.local/share"}
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
install -m 755 -- "$source_image" "$stage/T3-Code.AppImage"
(
  cd "$stage"
  ./T3-Code.AppImage --appimage-extract t3code.desktop >/dev/null
  ./T3-Code.AppImage --appimage-extract 'usr/share/icons/hicolor/*/apps/t3code.png' >/dev/null
)
python3 - "$stage/squashfs-root/t3code.desktop" "$app_dir/T3-Code.AppImage" "$stage/t3code.desktop" <<'PY'
import pathlib
import sys

source, executable, destination = sys.argv[1:]
text = pathlib.Path(source).read_text()
if 'Name=T3 Code' not in text or 'Type=Application' not in text:
    raise SystemExit('The supplied AppImage does not identify itself as T3 Code.')
# Escape the desktop entry string layer and the Exec quoted-argument layer.
quoted = executable.replace('%', '%%')
for char in ('\\', '"', '`', '$'):
    quoted = quoted.replace(char, '\\' + char)
quoted = quoted.replace('\\', '\\\\')
lines = [f'Exec="{quoted}" %U' if line.startswith('Exec=') else line
         for line in text.splitlines()]
pathlib.Path(destination).write_text('\n'.join(lines) + '\n')
PY
if command -v desktop-file-validate >/dev/null; then
  desktop-file-validate "$stage/t3code.desktop"
fi
mkdir -p "$app_dir" "$HOME/.local/bin" "$data_dir/applications"
install -m 755 "$stage/T3-Code.AppImage" "$app_dir/T3-Code.AppImage.new"
mv -f -- "$app_dir/T3-Code.AppImage.new" "$app_dir/T3-Code.AppImage"
ln -sfn "$app_dir/T3-Code.AppImage" "$HOME/.local/bin/t3-code"
for icon in "$stage"/squashfs-root/usr/share/icons/hicolor/*/apps/t3code.png; do
  size=$(basename "$(dirname "$(dirname "$icon")")")
  install -Dm 644 "$icon" "$data_dir/icons/hicolor/$size/apps/t3code.png"
done
install -m 644 "$stage/t3code.desktop" "$data_dir/applications/t3code.desktop"
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$data_dir/applications"
fi
if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache --force --ignore-theme-index "$data_dir/icons/hicolor" >/dev/null
fi
printf 'Installed T3 Code: %s\nLaunch from the app menu or run t3-code.\n' "$app_dir/T3-Code.AppImage"

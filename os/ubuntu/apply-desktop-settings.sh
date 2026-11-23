#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -eq 0 ] || [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  echo "Run as your regular user from a logged-in GNOME desktop session." >&2
  exit 1
fi
for command in dconf gsettings python3; do
  command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done

# Check the full profile before writing any preferences. Do not silently store
# unsupported keys that would have no effect on another GNOME version.
python3 - "$SCRIPT_DIR/desktop/settings.ini" <<'PYTHON'
import configparser
import subprocess
import sys

profile = configparser.ConfigParser(interpolation=None)
profile.read(sys.argv[1])
for section in profile.sections():
    schema = 'org.gnome.' + section.replace('/', '.')
    keys = subprocess.check_output(['gsettings', 'list-keys', schema], text=True).splitlines()
    for key in profile[section]:
        if key not in keys:
            sys.exit(f'Unsupported setting: {schema} {key}')
PYTHON

bash "$SCRIPT_DIR/install-desktop-fonts.sh"

wallpaper_dir="${XDG_DATA_HOME:-$HOME/.local/share}/backgrounds/pc-setup"
mkdir -p "$wallpaper_dir"
install -m 644 "$SCRIPT_DIR/desktop/wallpaper.jpg" "$wallpaper_dir/wallpaper.jpg"
wallpaper_uri="$(python3 - "$wallpaper_dir/wallpaper.jpg" <<'PYTHON'
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve().as_uri())
PYTHON
)"

# dconf load merges only these keys; never reset the surrounding settings tree.
dconf load /org/gnome/ < "$SCRIPT_DIR/desktop/settings.ini"
# Keep the existing monospace preference unless the user's licensed font exists.
if [ "$(fc-match -f '%{family}' 'Berkeley Mono')" = 'Berkeley Mono' ]; then
  gsettings set org.gnome.desktop.interface monospace-font-name 'Berkeley Mono 11'
else
  echo "Berkeley Mono is not installed; keeping the current monospace font."
fi
gsettings set org.gnome.desktop.background picture-uri "$wallpaper_uri"
gsettings set org.gnome.desktop.background picture-uri-dark "$wallpaper_uri"
gsettings set org.gnome.desktop.screensaver picture-uri "$wallpaper_uri"
echo "Applied portable Ubuntu desktop preferences."

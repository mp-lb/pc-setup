#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$(id -u)" -eq 0 ] || [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  echo "Run as your regular user from a logged-in GNOME desktop session." >&2
  exit 1
fi
python3 - "$SCRIPT_DIR" "${1:-apply}" <<'PYTHON'
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

source = Path(sys.argv[1]) / 'desktop/pc_setup_sidebar.py'
mode = sys.argv[2]
config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'pc-setup/files'
extension = data / 'nautilus-python/extensions/pc_setup_sidebar.py'
bookmarks = config / 'gtk-3.0/bookmarks'
backup = state / 'original.json'
setting = ['org.gnome.nautilus.preferences', 'default-folder-viewer']

if mode == '--remove':
    extension.unlink(missing_ok=True)
    if backup.exists():
        original = json.loads(backup.read_text())
        if original['bookmarks'] is None:
            bookmarks.unlink(missing_ok=True)
        else:
            bookmarks.parent.mkdir(parents=True, exist_ok=True)
            bookmarks.write_text(original['bookmarks'])
        subprocess.run(['gsettings', 'set', *setting, original['view']], check=True)
        backup.unlink()
    print('Removed Files customization and restored saved bookmarks/default view. Restart Files.')
    sys.exit(0)
if mode != 'apply':
    sys.exit('Usage: apply-files-settings.sh [--remove]')

version = subprocess.check_output(['nautilus', '--version'], text=True).strip()
if not version.startswith('GNOME nautilus 50.'):
    sys.exit(f'Sidebar customization needs review for this version: {version}')
import gi
gi.require_version('Nautilus', '4.1')
from gi.repository import GLib
if not subprocess.run(['dpkg-query', '-W', '-f=${Status}', 'python3-nautilus'],
                      capture_output=True, text=True).stdout.endswith('install ok installed'):
    sys.exit('Install python3-nautilus first: sudo apt-get install python3-nautilus')

state.mkdir(parents=True, exist_ok=True)
if not backup.exists():
    backup.write_text(json.dumps({
        'bookmarks': bookmarks.read_text() if bookmarks.exists() else None,
        'view': subprocess.check_output(['gsettings', 'get', *setting], text=True).strip(),
    }))
downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
folders = [(Path(downloads or Path.home() / 'Downloads'), 'Downloads'),
           (Path.home() / 'Work', 'Work')]
for folder, _ in folders:
    folder.mkdir(parents=True, exist_ok=True)
bookmarks.parent.mkdir(parents=True, exist_ok=True)
bookmarks.write_text(''.join(f'{folder.as_uri()} {label}\n' for folder, label in folders))
extension.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(source, extension)
subprocess.run(['gsettings', 'set', *setting, 'list-view'], check=True)
print('Applied Files sidebar and default list view. Restart Files to load the extension.')
PYTHON

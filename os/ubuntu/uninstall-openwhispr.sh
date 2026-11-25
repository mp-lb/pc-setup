#!/bin/bash
# Optional cleanup for the Ubuntu deb install. Run as the desktop user.
set -euo pipefail

user_only=false
remove_uinput=false
for arg in "$@"; do
  case "$arg" in
    --user-data-only) user_only=true ;;
    --remove-uinput-rule) remove_uinput=true ;;
    *) echo "Usage: $0 [--user-data-only] [--remove-uinput-rule]" >&2; exit 2 ;;
  esac
done
[[ $(uname -s) == Linux && $EUID != 0 ]] || {
  echo 'Run as the regular desktop user on Ubuntu.' >&2; exit 1;
}

/usr/bin/python3 - <<'PY'
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

home = Path.home()
config = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
cache = home / '.cache' / 'openwhispr'
data = config / 'open-whispr'
try:
    downloads = Path(subprocess.check_output(['xdg-user-dir', 'DOWNLOAD'], text=True).strip())
except (FileNotFoundError, subprocess.CalledProcessError):
    downloads = home / 'Downloads'
if not downloads.is_absolute() or downloads == home:
    downloads = home / 'Downloads'

# Match executables, never command-line text belonging to another process.
def processes():
    found = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            exe = os.readlink(proc / 'exe')
            if proc.stat().st_uid == os.getuid() and (
                exe.startswith('/opt/OpenWhispr/') or exe.startswith(str(data / 'bin') + '/')
            ):
                found.append(int(proc.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    return found

for pid in processes():
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
for _ in range(150):
    if not processes():
        break
    time.sleep(0.1)
if processes():
    raise SystemExit('OpenWhispr is still running; no data has been removed.')

def manifest(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise SystemExit(f'Refusing model cache containing a symlink: {path}')
        if path.is_file():
            with path.open('rb') as stream:
                result[str(path.relative_to(root))] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result

# Preserve the entire cache, including all model companion files. Verify before
# removing the original, even when Downloads is on a different filesystem.
if cache.is_symlink():
    raise SystemExit('Refusing a symlinked model cache; inspect it manually.')
if cache.exists():
    before = manifest(cache)
    downloads.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='OpenWhispr-models-', dir=downloads))
    shutil.copytree(cache, backup, dirs_exist_ok=True)
    if manifest(backup) != before:
        raise SystemExit(f'Backup verification failed; originals retained. Backup: {backup}')
    (backup / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in before.items()))
    (backup / 'RESTORE.txt').write_text(
        'Models preserved from ~/.cache/openwhispr.\n'
        'For a compatible OpenWhispr reinstall, quit the app and copy models/ and\n'
        'parakeet-models/ back into ~/.cache/openwhispr/.\n'
        'Keep each Parakeet folder intact, including tokens.txt and all ONNX files.\n'
        'Verify files here with: sha256sum -c SHA256SUMS\n'
    )
    shutil.rmtree(cache)
    print(f'Preserved and verified {len(before)} files: {backup}', flush=True)

# Delete only this app's keyring records, without reading secret values.
import dbus
bus = dbus.SessionBus()
service = dbus.Interface(bus.get_object('org.freedesktop.secrets', '/org/freedesktop/secrets'),
                         'org.freedesktop.Secret.Service')
items = set()
for attrs in ({'service': 'OpenWhispr'}, {'application': 'open-whispr'}):
    unlocked, locked = service.SearchItems(dbus.Dictionary(attrs, signature='ss'))
    if locked:
        raise SystemExit('OpenWhispr keyring items are locked; unlock the login keyring and retry.')
    items.update(unlocked)
for item in items:
    prompt = dbus.Interface(bus.get_object('org.freedesktop.secrets', item),
                            'org.freedesktop.Secret.Item').Delete()
    if prompt != '/':
        raise SystemExit('Keyring deletion requires an interactive prompt; retry from the desktop.')
print(f'Removed {len(items)} OpenWhispr keyring entries.')

for path in (data, config / 'autostart/open-whispr.desktop',
             home / '.local/share/applications/open-whispr.desktop'):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
for installer in downloads.glob('OpenWhispr-*.deb'):
    package = subprocess.run(['dpkg-deb', '-f', str(installer), 'Package'],
                             capture_output=True, text=True)
    if package.returncode == 0 and package.stdout.strip() == 'open-whispr':
        installer.unlink()
print('Removed OpenWhispr user data, autostart entry, and downloaded deb installers.')
PY

if $user_only; then
  echo 'User cleanup complete. System package removal remains: sudo apt-get purge open-whispr'
  exit 0
fi
sudo apt-get purge -y open-whispr

# Opt in only after confirming the app created this otherwise shared rule.
if $remove_uinput; then
  rule=/etc/udev/rules.d/70-uinput.rules
  expected='KERNEL=="uinput", GROUP="input", MODE="0660", TAG+="uaccess"'
  if [[ -f "$rule" ]]; then
    [[ $(cat "$rule") == "$expected" ]] || {
      echo 'uinput rule has other content; leaving it in place.' >&2; exit 1;
    }
    sudo rm -- "$rule"
    sudo udevadm control --reload-rules
    sudo udevadm trigger /dev/uinput
  fi
fi
echo 'OpenWhispr package and user data removed; preserved models remain in Downloads.'

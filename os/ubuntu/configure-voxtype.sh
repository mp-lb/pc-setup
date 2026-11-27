#!/bin/bash
# Optional local GPU dictation setup after install-voxtype.sh.
set -euo pipefail
[[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]] || {
  echo 'This shortcut setup requires GNOME.' >&2; exit 1;
}
command -v voxtype >/dev/null
model=${VOXTYPE_MODEL:-parakeet-ultra-Q8_0.gguf}
shortcut=${VOXTYPE_SHORTCUT:-'<Super>slash'}
config_root=${XDG_CONFIG_HOME:-$HOME/.config}
config="$config_root/voxtype/config.toml"
mkdir -p "$(dirname "$config")"
if [[ -f "$config" ]]; then
  cp -p -- "$config" "$config.backup-$(date +%s%N)"
else
  cp -- /etc/voxtype/config.toml "$config"
fi

# The packaged wrapper supports selecting Vulkan per process, without replacing
# system binaries. The drop-in below applies the same selection to the daemon.
[[ -x /usr/lib/voxtype/voxtype-vulkan && -x /usr/lib/voxtype/voxtype-gguf-worker-vulkan ]]
export VOXTYPE_GPU=1
voxtype --config "$config" setup --download --model "$model" --no-post-install
voxtype --config "$config" config select-model parakeet "$model"
voxtype --config "$config" config set parakeet.gguf_backend vulkan
voxtype --config "$config" config set parakeet.threads "$(lscpu -p=CORE,SOCKET | sed '/^#/d' | sort -u | wc -l)"
voxtype --config "$config" config set text.language en
# Allow long dictations. Parakeet splits audio past parakeet.max_window_secs
# (240s by default) into overlapping passes, which keeps VRAM near 2.3GB.
voxtype --config "$config" config set audio.max_duration_secs 600
voxtype --config "$config" config set hotkey.enabled false
voxtype --config "$config" config set output.shift_enter_newlines true
# GNOME does not implement the Layer Shell protocol used by the waveform OSD.
# The Voxtype bubble extension installed below shows recording state instead.
voxtype --config "$config" config set osd.enabled false
voxtype --config "$config" config set output.notification.on_recording_start false
voxtype --config "$config" config set output.notification.on_recording_stop false
voxtype --config "$config" config validate-selection

# Preserve unrelated custom shortcuts. GNOME treats both Super keys alike.
/usr/bin/python3 - "$shortcut" <<'PY'
import sys
from gi.repository import Gio
shortcut = sys.argv[1]
root = Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys')
paths = list(root.get_strv('custom-keybindings'))
path = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voxtype/'
schema = 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'
for existing in paths:
    item = Gio.Settings.new_with_path(schema, existing)
    if existing != path and item.get_string('binding') == shortcut:
        raise SystemExit('Shortcut already assigned; set VOXTYPE_SHORTCUT and retry.')
item = Gio.Settings.new_with_path(schema, path)
item.set_string('name', 'Voxtype dictation')
item.set_string('command', '/usr/bin/voxtype record toggle')
item.set_string('binding', shortcut)
if path not in paths:
    paths.append(path)
root.set_strv('custom-keybindings', paths)
Gio.Settings.sync()
PY

# Recording bubble with a level meter and stop button, drawn by GNOME Shell.
extension=voxtype-bubble@mp-lb.dev
extension_source="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/artifacts/gnome-shell/$extension"
extension_target="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$extension"
mkdir -p "$extension_target"
cp -- "$extension_source"/{metadata.json,extension.js,stylesheet.css} "$extension_target/"
/usr/bin/python3 - "$extension" <<'PY'
import sys
from gi.repository import Gio
settings = Gio.Settings.new('org.gnome.shell')
enabled = list(settings.get_strv('enabled-extensions'))
if sys.argv[1] not in enabled:
    settings.set_strv('enabled-extensions', enabled + [sys.argv[1]])
Gio.Settings.sync()
PY
gnome-extensions enable "$extension" 2>/dev/null ||
  echo 'Log out and back in to load the Voxtype bubble extension.'

mkdir -p "$config_root/systemd/user/voxtype.service.d"
cat > "$config_root/systemd/user/voxtype.service.d/pc-setup-gpu.conf" <<'UNIT'
[Service]
Environment=VOXTYPE_GPU=1
UNIT
systemctl --user daemon-reload
systemctl --user enable voxtype.service
systemctl --user restart voxtype.service
printf 'Voxtype enabled with %s and shortcut %s\n' "$model" "$shortcut"

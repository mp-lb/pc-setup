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
voxtype --config "$config" config set hotkey.enabled false
voxtype --config "$config" config set output.shift_enter_newlines true
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

mkdir -p "$config_root/systemd/user/voxtype.service.d"
cat > "$config_root/systemd/user/voxtype.service.d/pc-setup-gpu.conf" <<'UNIT'
[Service]
Environment=VOXTYPE_GPU=1
UNIT
systemctl --user daemon-reload
systemctl --user enable voxtype.service
systemctl --user restart voxtype.service
printf 'Voxtype enabled with %s and shortcut %s\n' "$model" "$shortcut"

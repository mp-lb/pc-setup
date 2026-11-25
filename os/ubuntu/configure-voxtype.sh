#!/bin/bash
# Optional local GPU dictation setup after install-voxtype.sh.
set -euo pipefail
command -v voxtype >/dev/null
model=${VOXTYPE_MODEL:-parakeet-ultra-Q8_0.gguf}
hotkey=${VOXTYPE_HOTKEY:-RIGHTCTRL}
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
voxtype --config "$config" config set hotkey.enabled true
voxtype --config "$config" config set hotkey.key "$hotkey"
voxtype --config "$config" config set hotkey.mode toggle
voxtype --config "$config" config set output.shift_enter_newlines true
voxtype --config "$config" config validate-selection

mkdir -p "$config_root/systemd/user/voxtype.service.d"
cat > "$config_root/systemd/user/voxtype.service.d/pc-setup-gpu.conf" <<'UNIT'
[Service]
Environment=VOXTYPE_GPU=1
UNIT
systemctl --user daemon-reload
systemctl --user enable voxtype.service
systemctl --user restart voxtype.service
printf 'Voxtype enabled with %s and shortcut %s\n' "$model" "$hotkey"
if ! id -nG | tr ' ' '\n' | grep -qx input; then
  echo 'Right Ctrl needs keyboard access. In a normal terminal run:'
  echo '  sudo usermod -aG input "$USER"'
  echo 'Then log out and back in to activate group membership.'
fi

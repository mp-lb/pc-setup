#!/bin/bash
# Lets systemd-oomd kill the biggest swap user in the desktop session once swap
# is nearly full, instead of letting the machine thrash until it freezes.
set -euo pipefail

dropin_dir=/etc/systemd/system/user@.service.d
dropin="$dropin_dir/90-oomd-swap.conf"
content='[Service]
ManagedOOMSwap=kill
'

if ! systemctl list-unit-files systemd-oomd.service >/dev/null 2>&1; then
  echo "systemd-oomd is not available; memory watchdog skipped."
  exit 0
fi

if [ "$(cat "$dropin" 2>/dev/null)" != "$(printf '%s' "$content")" ]; then
  sudo mkdir -p "$dropin_dir"
  printf '%s' "$content" | sudo tee "$dropin" >/dev/null
  sudo systemctl daemon-reload
fi

sudo systemctl enable --now systemd-oomd.service >/dev/null
echo "Memory watchdog: oomd kills the largest swap user in the session at its swap limit."

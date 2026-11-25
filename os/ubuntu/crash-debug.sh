#!/usr/bin/env bash
# Optional per-user recorder; never enabled by the default bootstrap.
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/crash-debug"
root="$HOME/Work/crash-debug"
unit="$HOME/.config/systemd/user/crash-debug.service"
case "${1:-}" in
  install)
    [[ $(uname -s) == Linux && -d /proc/pressure ]]
    [[ ! -e "$unit" ]] || { echo "Service already exists; uninstall it before reinstalling." >&2; exit 1; }
    mkdir -p "$root/bin" "$root/logs" "$(dirname "$unit")"
    chmod 700 "$root" "$root/logs"
    cp "$source_dir/recorder.py" "$root/bin/recorder.py"
    cp "${BASH_SOURCE[0]}" "$root/control.sh"
    cp "$source_dir/../../../docs/crash-debug.md" "$root/README.md"
    cat > "$unit" <<'UNIT'
[Unit]
Description=Removable crash diagnostic recorder

[Service]
ExecStart=/usr/bin/python3 "%h/Work/crash-debug/bin/recorder.py" "%h/Work/crash-debug/logs"
Restart=on-failure
RestartSec=10
UMask=0077
MemoryMax=96M
CPUQuota=5%
Nice=10
StandardOutput=null
StandardError=journal

[Install]
WantedBy=default.target
UNIT
    systemctl --user daemon-reload
    systemctl --user enable --now crash-debug.service
    ;;
  uninstall)
    systemctl --user disable --now crash-debug.service
    rm -f "$unit"
    systemctl --user daemon-reload
    systemctl --user reset-failed crash-debug.service 2>/dev/null || true
    if [[ ${2:-} == --purge ]]; then
      rm -rf -- "$root"
    else
      rm -rf -- "$root/bin"
      echo "Recorder removed; retained data and control.sh in $root. Use uninstall --purge to delete them."
    fi
    ;;
  status) systemctl --user status crash-debug.service --no-pager ;;
  *) echo "Usage: $0 {install|status|uninstall [--purge]}"; exit 1 ;;
esac

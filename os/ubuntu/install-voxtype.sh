#!/bin/bash
# Optional desktop app; deliberately excluded from the base bootstrap.
set -euo pipefail

download_only=false
case "${1:-}" in
  '') ;;
  --download-only) download_only=true ;;
  *) echo "Usage: $0 [--download-only]" >&2; exit 2 ;;
esac
[[ $(uname -s) == Linux && $(dpkg --print-architecture) == amd64 ]] || {
  echo 'This package requires amd64 Ubuntu or Debian.' >&2; exit 1;
}
[[ $EUID != 0 ]] || { echo 'Run as your regular user; apt will use sudo.' >&2; exit 1; }

version=1.3.1
filename="voxtype_${version}-1_amd64.deb"
sha256=d84a1c1f0c55fe0068830b3c4a6ac3dc5d63cc43e60bdae8dcc7e52b2162da53
downloads=$(xdg-user-dir DOWNLOAD 2>/dev/null || true)
[[ "$downloads" == /* && "$downloads" != "$HOME" ]] || downloads="$HOME/Downloads"
mkdir -p "$downloads"
package="$downloads/$filename"
if [[ ! -f "$package" ]]; then
  curl --fail --location --retry 3 --connect-timeout 20 \
    --speed-limit 1024 --speed-time 60 --continue-at - \
    "https://github.com/peteonrails/voxtype/releases/download/v$version/$filename" \
    --output "$package.part"
  printf '%s  %s\n' "$sha256" "$package.part" | sha256sum --check -
  mv -- "$package.part" "$package"
fi
printf '%s  %s\n' "$sha256" "$package" | sha256sum --check -
[[ $(dpkg-deb -f "$package" Package) == voxtype ]]
[[ $(dpkg-deb -f "$package" Architecture) == amd64 ]]
[[ $(dpkg-deb -f "$package" Version) == "$version-1" ]]
if $download_only; then
  printf 'Verified installer ready: %s\n' "$package"
  exit 0
fi
sudo apt-get install --no-remove -y "$package"
voxtype --version
echo 'Package installed. Configure a model and hotkey before enabling the user service.'

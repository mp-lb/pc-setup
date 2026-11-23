#!/bin/bash
set -euo pipefail

# Also runnable on an existing machine without repeating the full bootstrap.
source /etc/os-release
if [ "$ID" != ubuntu ]; then
  printf 'This installer requires Ubuntu.\n' >&2
  exit 1
fi
docker_user="${SUDO_USER:-$(id -un)}"

sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod 644 /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo chmod 644 /etc/apt/sources.list.d/docker.sources

sudo apt-get update
# Refuse to silently remove an existing container runtime when migrating hosts.
sudo apt-get install --no-remove -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo groupadd --force docker
sudo usermod -aG docker "$docker_user"
sudo systemctl enable --now containerd.service docker.service
sudo systemctl is-enabled --quiet containerd.service
sudo systemctl is-enabled --quiet docker.service
sudo systemctl is-active --quiet containerd.service
sudo systemctl is-active --quiet docker.service

# sudo initializes the user's updated groups; the calling shell still has its old groups.
sudo -H -u "$docker_user" docker --host unix:///var/run/docker.sock info >/dev/null
sudo -H -u "$docker_user" docker compose version
printf 'Docker is running and enabled at boot.\n'
printf 'Sign out and back in to activate Docker group access in all apps, or run newgrp docker for this terminal.\n'

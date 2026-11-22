#!/bin/bash
set -euo pipefail

# Also runnable on an existing machine without repeating the full bootstrap.
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg |
  gpg --batch --yes --dearmor |
  sudo tee /usr/share/keyrings/cloud.google.gpg >/dev/null
sudo chmod 644 /usr/share/keyrings/cloud.google.gpg
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main' |
  sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null
sudo chmod 644 /etc/apt/sources.list.d/google-cloud-sdk.list

sudo apt-get update
sudo apt-get install -y google-cloud-cli

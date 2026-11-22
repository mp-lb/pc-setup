# PC setup

PC setup bootstraps MAP Lab development machines on macOS and Ubuntu. It
installs host tools, mise-managed runtimes, Claude Code, the Forum, Berth and
Zapper CLIs, and global agent skills. It also configures GitHub credentials,
a shell profile bridge and MAP Lab AWS SSO profiles.

## Install

From an existing checkout, run:

```bash
./start.sh
```

For a new checkout, run this from a terminal with Bash and curl:

```bash
installer=$(curl -fsSL https://raw.githubusercontent.com/mp-lb/pc-setup/main/start.sh) &&
  /bin/bash -c "$installer"
```

Run as your regular user. Setup prints the detected OS and asks before
installing anything. Ubuntu uses sudo for apt and has been targeted at Ubuntu
26.04 LTS. The installer may prompt for GitHub login and Git author details.

The remote installer clones into `~/Work/pc-setup` by default. A local run
uses the current checkout and its parent as the workspace. Set
`PC_SETUP_WORKSPACE` to choose a different Work folder and optionally
`PC_SETUP_REPO_PATH` to choose the checkout path.

Setup adds `~/Work` to mise's global trusted paths. Mise loads configs from
current and future checkouts under `~/Work` without prompting for trust.

Forum, Berth, Zapper, PM2 and Clerk are installed as global mise `npm:` tools.
Their installs are separate from Node's global npm packages, so they stay on
PATH when a project selects a different Node version. They still run with the
active Node version, which must meet the CLI's runtime requirements. See the
[mise npm backend](https://mise.jdx.dev/dev-tools/backends/npm).
The installer explicitly approves our Berth and Zapper packages for mise's
new-package and low-download checks; dependency checks remain enabled.

To repair an existing machine that installed these CLIs with `npm install -g`,
run this from the pc-setup checkout:

```bash
./bin/install-host-clis
mise exec node@lts -- npm uninstall -g @mp-lb/forum-cli @mp-lb/berth @mp-lb/zapper pm2 clerk
mise reshim
```

This also updates the CLIs and removes the old copies from the default LTS
Node installation so they cannot shadow mise's separate installs. If you
installed copies under other Node versions, remove those copies there too.
Open a new terminal, then run `fm --version` and
`~/Work/pc-setup/doctor.sh` from a project with its own `.node-version` to check
that the tools work with the project's Node version.

Setup installs Oh My Zsh, adds its bridge to `~/.zshrc`, and sets zsh as your
login shell. Sign out and back in after installation to pick up the shell change. If you already have an AWS config,
copy the MAP Lab profiles you need from `env/aws-config` into it.

## Repository layout

- `start.sh` detects the OS and dispatches to the selected recipe.
- `os/macos/` contains the macOS recipe and Homebrew manifests.
- `os/ubuntu/` contains the Ubuntu recipe and apt package list.
- `lib/`, `env/`, `config/` and `bin/` contain shared user setup, configuration
  and commands.

## Verify

```bash
./doctor.sh
./inventory.sh
```

## Optional apps and containers

On macOS, install OrbStack separately:

```bash
brew bundle --file os/macos/Brewfile.apps
```

On Ubuntu, install [Docker Engine and the Compose plugin](https://docs.docker.com/engine/install/ubuntu/)
if you need containers. Use `docker info` and `docker compose version` to verify
that your normal account can use them. Ubuntu desktop apps are outside the
base install.

Install the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk)
separately on Ubuntu if needed. The macOS bundle includes it.

## Agent skills

Global skills for Codex and Claude Code are listed in
`config/global-skills.txt`. To install them again, run `./bin/install-skills`.

## Uninstall legacy runtime state

`./uninstall.sh` removes legacy runtime directories and the managed shell
bridge. `./uninstall.sh --all` also clears mise runtime state. Existing package
managers, system packages, Git config and workspace files remain in place.

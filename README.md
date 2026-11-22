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

Setup configures npm's user-level global prefix as
`~/.local/share/npm-global` and adds its `bin` directory to the shell PATH.
Forum, Berth, Zapper, PM2 and Clerk are installed there with npm. Global
packages and `npm link` links share this location across all mise Node versions.
Project dependencies remain in each project's `node_modules`.

To configure the prefix and install or update host CLIs, run:

```bash
./bin/install-host-clis
```

The installer preserves existing `npm link` symlinks. To use a local CLI,
build it as required by its repository and run `npm link` from the package
directory that declares its `bin`. The command then uses that checkout across
projects. To return to a published version, run `npm unlink --global <package>`
and `npm install --global <package>`.

CLIs still run with the active Node version, which must meet their runtime
requirements. Native dependencies may need rebuilding after a Node change.
Open a new terminal after setup and run `~/Work/pc-setup/doctor.sh` from a
project with its own `.node-version` to verify the prefix and command paths.

When migrating from separate mise `npm:` installs, first run the installer
above, then remove the superseded global registrations and installations:

```bash
mise unuse --global --no-prune npm:@mp-lb/forum-cli npm:@mp-lb/berth npm:@mp-lb/zapper npm:pm2 npm:clerk
mise uninstall --all npm:@mp-lb/forum-cli npm:@mp-lb/berth npm:@mp-lb/zapper npm:pm2 npm:clerk
mise reshim
```

For old npm globals inside a Node installation, use an explicit old prefix
when uninstalling (for example, `npm uninstall --global --prefix /path/to/node
<package>`). Relink local checkouts into the shared prefix before removing old
links. Doctor reports host commands that are still shadowed by another install.

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

## Google Cloud CLI and Overmind

Setup installs the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk)
on both platforms: through Homebrew on macOS and Google's signed apt repository
on Ubuntu. Doctor requires it on both platforms.

To add or update it on an existing Ubuntu machine without rerunning setup:

```bash
bash os/ubuntu/install-gcloud.sh
```

Overmind uses Homebrew's current version on macOS and `overmind@latest` through
mise on Ubuntu. Setup does not pin an Overmind release. To update an existing
Ubuntu installation and remove the old version pin, run:

```bash
mise use --global --fuzzy overmind@latest
```

## Agent skills

Global skills for Codex and Claude Code are listed in
`config/global-skills.txt`. To install them again, run `./bin/install-skills`.

## Uninstall legacy runtime state

`./uninstall.sh` removes legacy runtime directories and the managed shell
bridge. `./uninstall.sh --all` also clears mise runtime state. Existing package
managers, system packages, Git config and workspace files remain in place.

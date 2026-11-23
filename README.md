# PC setup

PC setup bootstraps MAP Lab development machines on macOS and Ubuntu. It
installs host tools, mise-managed runtimes, Claude Code, the Forum, Berth and
Zapper CLIs, and global agent skills. It also configures GitHub credentials,
a shell profile bridge and MAP Lab AWS SSO profiles. On Ubuntu GNOME it also
applies portable desktop appearance preferences and the bundled wallpaper.

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

Setup installs Oh My Zsh, adds bridges to `~/.zshenv` and `~/.zshrc`, and sets
zsh as your login shell. With `ZDOTDIR` set, the bridges go there instead.
Sign out and back in after installation to pick up the shell change. If you already have an AWS config,
copy the MAP Lab profiles you need from `env/aws-config` into it.

### Non-interactive shells

Zsh reads `.zshenv` for ordinary interactive and non-interactive invocations
on both macOS and Ubuntu. PC setup uses it for host CLI paths, helper commands
and mise shims. `.zshrc` keeps Oh My Zsh, aliases, custom interactive settings
and full mise activation. The shims select tools for the current project even
when an agent or script starts with a minimal PATH.

To add the bridges on an existing machine without rerunning the full setup:

```bash
./bin/install-shell
mise reshim
./doctor.sh
```

The installer preserves existing shell configuration and skips installed
bridges. New zsh processes pick up the change immediately. Existing terminals
can run `exec zsh` to reload it. Shells started with `zsh -f` deliberately skip
user startup files; Bash and processes that do not launch zsh are not covered.
Shims load mise environment variables for the tool they launch, not the parent
shell. Use `mise exec -- <command>` when a whole command needs the project
environment. See [mise's shim documentation](https://mise.jdx.dev/dev-tools/shims.html).

## Desktop preferences

PC setup owns intentional preferences that should carry across machines, while
environment-specific configuration and incidental state remain local. Ubuntu's
curated appearance profile includes dark mode, the blue accent, wallpaper, dock
layout, IBM Plex Sans for the interface, optional Berkeley Mono for monospace
text, and desktop special-icon visibility. See [desktop settings](docs/desktop-settings.md)
for the scope, exclusions, and how to apply it independently of the bootstrap.

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

## Containers and optional apps

On macOS, install OrbStack separately:

```bash
brew bundle --file os/macos/Brewfile.apps
```

On Ubuntu, setup installs [Docker Engine](https://docs.docker.com/engine/install/ubuntu/),
the Docker CLI, Buildx and Compose from Docker's signed apt repository. It starts
Docker and containerd immediately and enables both systemd services at boot.
Systemd manages daemon restarts using the packaged service restart policies.
Setup adds your account to the `docker` group so Zapper can use the local daemon.
Sign out and back in to activate that group in all apps, or run `newgrp docker`
for access in the current terminal.

To install Docker or restore daemon startup on an existing Ubuntu machine:

```bash
bash ~/Work/pc-setup/os/ubuntu/install-docker.sh
```

The installer refuses package changes that would remove an existing container
runtime. If apt reports conflicting distro packages, follow Docker's migration
instructions linked above before rerunning it. Doctor requires the local daemon,
Compose and Buildx, and checks that Docker and containerd are running and enabled
at boot. Ubuntu desktop apps remain outside the base install.

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

# PC setup

This repository bootstraps MAP Lab development machines. The scripts support macOS and Ubuntu.

## Boundary

PC setup owns the host substrate and portable desktop preferences:

- OS package managers and host CLI tools
- mise installation and global default tools
- Claude Code installation
- the Forum, production Berth, and Zapper CLI installs
- GitHub authentication and Git credential helper setup
- the shell bridge that activates mise and adds MAP Lab helper scripts to PATH
- doctor/inventory scripts for checking local machine state
- intentional desktop preferences and their assets that should follow the user
  across machines

PC setup does not directly install language runtimes with `nvm`, `pyenv`, or
`rbenv`. Runtime versions belong to mise. Project services, ports, env files,
and tasks belong to Zapper.

Capture reusable intent, not a snapshot of the current machine. Keep settings
that remain meaningful when hardware, location, accounts, or session state
change. Leave environment-specific configuration, secrets, generated state, and
unrequested defaults local. Use a reviewed allowlist of settings; never commit
an entire desktop configuration dump. Store required assets in the repo and
resolve installation paths for the current user. See [desktop settings](docs/desktop-settings.md).

## Structure

- `os/macos/` holds the macOS recipe and Homebrew manifests.
- `os/ubuntu/` holds the Ubuntu recipe and apt package list.
- Keep OS-specific install steps in their OS directory.
- `start.sh` is the bootstrap entrypoint and must remain runnable from the
  GitHub raw URL.
- `uninstall.sh` removes legacy pc-setup-managed runtime state only; it must
  never delete `~/Work`, project files, git config, or Homebrew.
- `doctor.sh` checks whether the required host substrate is healthy.
- `inventory.sh` prints what is installed.
- `env/` contains shell configuration.
- `bin/` contains small MAP Lab helper commands.

## Editing Rules

Keep the repo boring. Prefer deleting stale setup code over preserving historical
layers.

When adding a tool:

1. Put required host CLI tools in the OS package list or recipe.
2. Keep optional heavy apps outside the default bootstrap.
3. Use mise for language and runtime versions.
4. Add or update doctor and inventory checks when useful.

Before finishing, run:

```bash
for file in *.sh bin/* lib/*.sh os/*/*.sh env/bashrc tests/*.sh; do
  bash -n "$file" || exit
done
for file in env/zshenv env/zshrc env/home-zshrc env/zsh-theme.sh; do
  zsh -n "$file" || exit
done
bash tests/shell-startup.sh
./doctor.sh
```

Check the Homebrew bundle on macOS with `brew bundle check --file os/macos/Brewfile`.

## Documentation

Keep PC setup-specific documents under `docs/` when needed. This repository has no dedicated Forum store or sync configuration.

Read shared standards with `fm read <file>.md --store mp-lb/dev` (list them with `fm ls --store mp-lb/dev`). Read shared extensions with `fm read extensions/<extension>/README.md --store mp-lb/fssstack` (list them with `fm ls extensions --store mp-lb/fssstack`).

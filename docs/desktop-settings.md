# Desktop settings

PC setup owns intentional preferences that should follow the user to another
machine, together with the assets needed to reproduce them. The test is whether
a setting expresses a lasting preference independently of the current hardware,
location, account, or session. Preserve that intent, not a machine snapshot.

Use a reviewed allowlist. Do not export whole configuration trees, capture
untouched categories just because they exist, or save user-specific paths.
Keep environment-specific configuration, credentials, identifiers, and generated
or temporary state on the machine. Application/project configuration retains its
own owner.

Personal fonts and other private assets belong in a separate personal setup
repository. The public appearance profile does not manage font preferences.
After the normal Ubuntu setup and GitHub authentication, an optional step checks
access to the private `felixsebastian/ubuntu-fonts` repository. If inaccessible,
it silently skips without changing fonts or requiring another login. If
accessible and private, it clones or fast-forwards the checkout at
`$PC_SETUP_WORKSPACE/ubuntu-fonts` (default `~/Work/ubuntu-fonts`) and runs its
installer. Font files and personal font preferences live entirely in that
private repo. Existing local changes or a different origin are never overwritten.

The private installer supports installing font files in headless sessions and
applying its preferences when run from GNOME. To retry just the optional step
after GitHub authentication:

```bash
bash os/ubuntu/install-optional-fonts.sh
```

The shared appearance command below does not run this optional step.

## Ubuntu appearance

`os/ubuntu/desktop/settings.ini` is a curated dconf profile relative to
`/org/gnome/`. It records dark mode, the blue accent and matching Yaru themes,
wallpaper rendering, and the customized dock: a full-width opaque bottom panel,
centered icons and app-grid button, 24-pixel icons, always visible, on all
monitors, with no trash icon. Showing the dock on every monitor is a portable
policy; selecting a particular monitor is not.

Desktop Icons NG hides its home, trash, mounted-volume, and network-volume icons.
It remains enabled, so files placed on the desktop can still appear. Its runtime
compatibility flag is deliberately excluded.

`os/ubuntu/desktop/wallpaper.jpg` is the existing Mojave desert wallpaper copied
from the user's local background image. The installer copies it into
`${XDG_DATA_HOME:-$HOME/.local/share}/backgrounds/pc-setup/` and derives the desktop,
dark-mode, and lock-screen image URIs at runtime. No original home-directory path
is saved in the profile.

Excluded: display resolution, scaling and layout, monitor identities, Wi-Fi and
other network configuration, audio devices and levels, and room/desk-specific
choices. Search and notifications are not managed because they were not requested
or customized as part of this profile.

## Apply

From a logged-in Ubuntu GNOME session, as your regular user:

```bash
bash os/ubuntu/apply-desktop-settings.sh
```

The Ubuntu bootstrap runs this automatically when invoked in a GNOME session.
Headless installs skip it and print the command to run later. It targets the
Ubuntu 26.04 desktop with Ubuntu Dock, Desktop Icons NG, and Yaru installed, and
requires `dconf`, `gsettings`, and `python3`. Unsupported profile keys fail before
preferences are written.

Applying the profile overwrites only its listed preferences and the three
wallpaper URIs. Other settings are preserved. Running it again is safe. Changes
made later in Settings stay local until deliberately added to the profile;
reapplying restores the managed preferences.

## Files sidebar and list view

The desktop installer also runs `os/ubuntu/apply-files-settings.sh`. It sets
Nautilus's default to list view and replaces its bookmarks with Downloads and
Work (`~/Work`). A small user extension filters and orders the
native sidebar rows: Home, Downloads, Work, Network, Trash. The actual
folders and normal navigation/context menus are preserved. Other sidebar entries,
including mounted devices, are hidden; devices remain accessible through Network
or their filesystem paths. Recent-file tracking is unchanged.

This customization requires Ubuntu's `python3-nautilus` package and Nautilus 50.
It uses internal sidebar widgets because Nautilus exposes no sidebar settings;
review it when upgrading Nautilus. New windows and rebuilt rows are handled.
The extension lives under `${XDG_DATA_HOME:-~/.local/share}/nautilus-python/extensions/`.
The first apply saves the original bookmarks and default view under
`${XDG_STATE_HOME:-~/.local/state}/pc-setup/files/`; reapplying preserves that backup.
Folder-specific view overrides can still override the default list view.

Apply just this preference, then close/reopen Files:

```bash
bash os/ubuntu/apply-files-settings.sh
nautilus --quit
nautilus --new-window "$HOME"
```

To remove the extension and restore the saved bookmarks/default view (this
replaces any bookmark edits made since installation):

```bash
bash os/ubuntu/apply-files-settings.sh --remove
nautilus --quit
```

Reapplying desktop settings installs the customization again. No folders or
folder contents are deleted when applying or removing it.

## Optional Gnome MacLike dashboard

The [Gnome MacLike dashboard](../os/ubuntu/command/README.md), previously Ubuntu
Command, provides optional keyboard layers, a local wallpaper gallery, a bottom
panel preset, and restore/uninstall controls. It uses a pinned Xremap binary for
manually started macOS-style shortcuts on Ubuntu 26.04 / GNOME 50 Wayland.
It runs quietly in transient background services and is not part of the default
bootstrap. It changes no packages, persistent services, device permissions, or
group memberships. Starting/stopping an active session requires administrator
authorization; the emergency stop chord does not. Its README
lists the exact user files and extension settings it owns, the appearance recovery
journal, and the current shortcut limitations. Open `os/ubuntu/command/gui.py`
with Python for first installation; the application launcher opens the GUI after
that. Keyboard changes take effect only when applied, and appearance controls
save original values before modifying the allowlisted settings.

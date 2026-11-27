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
monitors, with no trash icon. Clicking a dock icon focuses the app, minimizes it
if it is already focused, and spreads its windows when it has several. Showing
the dock on every monitor is a portable policy; selecting a particular monitor
is not.

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

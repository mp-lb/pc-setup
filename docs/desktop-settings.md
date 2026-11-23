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

## Ubuntu appearance

`os/ubuntu/desktop/settings.ini` is a curated dconf profile relative to
`/org/gnome/`. It records dark mode, the blue accent and matching Yaru themes,
IBM Plex Sans for interface text and bold window titles (11 points), wallpaper
rendering, and the customized dock: a full-width opaque bottom panel, centered
icons and app-grid button, 24-pixel icons, always visible, on all monitors, with
no trash icon. Showing the dock on every monitor is a portable policy; selecting
a particular monitor is not.

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

The bundled IBM Plex Sans fonts include all eight weights and italics,
with their license and package provenance in `os/ubuntu/desktop/fonts/`. The
installer copies them to `${XDG_DATA_HOME:-$HOME/.local/share}/fonts/pc-setup/`
and refreshes the font cache without requiring administrator access. Apps with
their own font preferences may need separate configuration or a restart.

Document fonts retain their existing setting. Monospace text uses Berkeley Mono
at 11 points when it is installed; otherwise the existing monospace preference is
preserved. Fontconfig's generic family aliases and fallback lists are unchanged.

Berkeley Mono is a user-supplied font and is not committed to this repository.
Install a licensed copy from its extracted font directory before applying the
profile:

```bash
bash os/ubuntu/install-desktop-fonts.sh /path/to/berkeley-font-directory
```

This copies `BerkeleyMono-*.otf` into the current user's font directory and
refreshes the cache. The regular face must be present. Terminals that follow
GNOME's monospace preference then use Berkeley Mono; apps with an explicit font
override retain that override.

After installing new font files, fully restart running terminal applications
once existing sessions can be closed. A new tab or window can reuse the old
Ptyxis process and its font cache. To check a fresh process without closing
existing sessions, use `ptyxis --standalone`. Confirm the font in that terminal;
a fontconfig match in a separate process does not verify a running terminal.

## Apply

From a logged-in Ubuntu GNOME session, as your regular user:

```bash
bash os/ubuntu/apply-desktop-settings.sh
```

The Ubuntu bootstrap runs this automatically when invoked in a GNOME session.
Headless installs skip it and print the command to run later. It targets the
Ubuntu 26.04 desktop with Ubuntu Dock, Desktop Icons NG, and Yaru installed, and
requires `dconf`, `gsettings`, `python3`, and `fc-cache` (fontconfig). Unsupported
profile keys fail before preferences are written.

Applying the profile overwrites its listed preferences, the three wallpaper
URIs, and the monospace preference when Berkeley Mono is available. Other settings are preserved. Running it again is safe. Changes
made later in Settings stay local until deliberately added to the profile;
reapplying restores the managed preferences.

# Ubuntu Command

An optional, deliberately small keyboard experiment for Ubuntu 26.04, GNOME 50,
Wayland, and 64-bit x86/ARM machines. Inspired by Toshy's context-sensitive
Command-key approach. This is independent code, not a Toshy distribution.

## Shortcuts

On a PC keyboard the **left Alt key becomes Command**, and the left Windows/Super
key becomes Option (Alt). On an Apple keyboard use `start --apple`: the left
Command and Option keys stay in their existing positions. Right-side modifiers,
including AltGr, are unchanged.

- Command+Tab / Shift+Command+Tab: GNOME application switching.
- Command+C/V: copy/paste. Known terminal apps receive Ctrl+Shift+C/V; other apps
  receive Ctrl+Insert/Shift+Insert, which also work in many embedded terminals.
- Control+C remains Control+C, including terminal interrupt.
- Command+W: close tab/document. Shift+Command+W: close window where the app
  supports its conventional shortcut. Terminal variants use terminal bindings.
- Command+Q: GNOME requests a normal application quit, allowing save dialogs.
- Other Command shortcuts become Control shortcuts, such as A, X, Z, T and F.
- **Physical Ctrl+Alt+Esc** stops remapping. Closing the session terminal also stops it.

This first version does not promise complete macOS emulation. Command+click,
right-side Command, keyboard LED feedback, hot-plugging, and per-app exceptions
beyond the small terminal list are not implemented. Restart after plugging in a
keyboard. Combined keyboard/mouse/touchpad event devices are excluded so pointers
are not grabbed. Non-US layouts and application-specific close/quit behavior
need testing. Grabbing a keyboard can affect the touchpad's disable-while-typing
feature; no libinput workaround is installed. Locking the session or losing the
extension stops the process rather than guessing terminal context.

## Install and start

Run as your normal user, from this directory:

```sh
python3 -B control.py install
python3 -B control.py start
```

On GNOME Wayland, a logout/login may be needed after first installation before
the local extension can be enabled. Installation does **not** start remapping or
turn on automatic startup. Start runs in the foreground and asks for sudo only
to open the keyboard devices and create the session's virtual keyboard.

Before reading keyboard events, the process permanently drops to your normal
user and sets `no_new_privs`. Only that process keeps the open device handles.
No device ACLs, group memberships, udev rules, kernel boot configuration, system
services, shell configuration, package-manager state, or application settings are
changed. The kernel releases device grabs and destroys the virtual keyboard when
the process exits, including after a crash or SIGKILL. There is no keystroke log,
network service, downloaded dependency, or startup service.

The standard Ubuntu `gdbus`, `gsettings`, `dconf`, `gnome-extensions`, and Python
commands, plus an existing `/dev/uinput`, are required. Missing prerequisites
cause a refusal; the tool never installs packages or loads kernel modules.

## Uninstall and verification

```sh
python3 -B control.py stop
python3 -B control.py uninstall
python3 -B control.py status
```

Uninstall itself stops a running session, so the separate `stop` is optional.
It removes the extension UUID from the enabled/disabled extension lists and
restores their exact original raw values when no unrelated changes were made.
Other extension changes made during the trial are preserved. It then removes
its files and any empty parent directories it created. Run uninstall from this
source checkout, which is not an installed artifact and is kept for development.

The complete persistent footprint is:

- `${XDG_DATA_HOME:-~/.local/share}/ubuntu-command/` (three Python files and an empty session lock).
- `${XDG_DATA_HOME:-~/.local/share}/gnome-shell/extensions/ubuntu-command@mp-lb.dev/` (two files).
- `${XDG_DATA_HOME:-~/.local/share}/applications/ubuntu-command.desktop`.
- `${XDG_STATE_HOME:-~/.local/state}/ubuntu-command/` (recovery manifest, operation lock, temporary staging).
- Only membership of this extension UUID in GNOME's two extension lists, changed when starting/stopping the extension.

Existing paths and existing entries with the same UUID are never adopted or
overwritten. The journal is saved before publishing files. Removal is retryable
following partial installs or removals. Modified installed files, substituted
symlinks, and unexpected files cause removal to stop with a precise explanation;
move/save those changes and retry. The journal is retained until cleanup succeeds.
It never announces successful removal after a conflict or command failure.

The system journal or sudo audit log may retain the fact that a process ran.
Those shared audit records are not application leftovers and are never erased.
GNOME may keep a disabled extension in memory until logout; its files and enabled
settings are removed. No claim of byte-for-byte restoration of unrelated OS
caches, timestamps, or audit history is made.

Tests: `python3 -B -m unittest discover -s os/ubuntu/command/tests -v` from the
pc-setup repository. Tests exercise installation/removal against temporary real
files and a private D-Bus/dconf session; synthetic keyboard sequences test mapping
and cleanup. Real device and GNOME Shell activation testing must be reported
separately from these tests.

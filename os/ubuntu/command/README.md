# Ubuntu Command

An optional macOS-style shortcut setup for Ubuntu 26.04, GNOME 50 and Wayland.
**Xremap handles all keyboard input.** Our code installs a pinned upstream binary,
manages its lifetime, and supplies a small GNOME adapter for application context
and normal application quit. There is no custom keyboard driver or mapping engine.

## Install and use

Run as your normal user from this directory:

```sh
python3 -B control.py install
python3 -B control.py start
python3 -B control.py stop
python3 -B control.py uninstall
```

First installation may require logging out and back in so GNOME recognizes the
extension. Launch **Ubuntu Command** from the applications menu after that.
There is no terminal to keep open. Its launcher also has Stop and Uninstall actions.
Use `start --apple` for an Apple keyboard; the default is a PC keyboard.
Installation is inactive, and startup is manual on every login.

Starting requests administrator authorization through the desktop's normal
Polkit prompt. Stopping or uninstalling an active session also requests it.
**Physical Ctrl+Alt+Esc** exits Xremap directly, without an authentication prompt.
Once Xremap has exited, uninstall requires no administrator access.

The supplied upstream binary is **Xremap 0.15.19, socket variant**, for x86_64 or
ARM64. Its release archive SHA-256 is pinned in `control.py` and checked before
extracting the single binary. `install --archive /path/to/release.zip` uses a
local copy with the same verification. The MIT license is included. This checks
integrity against our pinned upstream release; it is not an independent security
certification. Updating Xremap requires an intentional version/checksum update.

## Shortcuts

PC keyboards: left Alt becomes Command, left Super becomes Option/Alt. Apple
keyboards with `--apple`: existing left Command and Option positions are retained.
AltGr and right Super are unchanged. Physical right Control sends left Control
so it remains separate from the right-Control signal reserved for Command.

- Command behaves as Control by default, including Command-click, copy/paste,
  select all, undo, find, save, new tabs, and app-specific Control shortcuts.
- Command+Tab / Shift+Command+Tab: native GNOME application switching. Keep
  Command held and tap Tab to cycle; release Command to select.
- Command+C/V: Ctrl+Shift+C/V in recognized standalone terminals.
- Physical Control+C remains Control+C, including terminal interrupt.
- Command+W / Shift+Command+W: the application's Control+W / Control+Shift+W;
  recognized terminals use Ctrl+Shift+W / Ctrl+Shift+Q.
- Command+T/N: Ctrl+Shift+T/N in recognized terminals.
- Command+H: minimize the focused window (GNOME’s default Super+H binding).
  This minimizes one window; macOS Hide can hide all windows of an app.
- Command+Q: GNOME requests normal application quit, allowing save dialogs.
- Control+Command+Q: lock the screen through GNOME's screen-lock service.
  On a PC keyboard this is physical Control+left Alt+Q.
- Physical Ctrl+Alt+Esc: emergency stop (Ctrl+Super+Esc also works).

The JSON files use upstream Xremap's press/release actions and modes. Pressing
Command holds a real Control modifier, so mouse clicks need no interception and
ordinary shortcuts need no individual entries. While Command is held, terminal
exceptions add Shift. Command+Tab releases that Control and holds Super for the
native switcher until Command is released. Physical Control remains independent.
The lock shortcut calls GNOME's `org.gnome.ScreenSaver.Lock` D-Bus method through
the user bridge. Minimize temporarily releases Command's Control signal and
emits GNOME's Super+H binding. No GNOME keybindings are changed.

Embedded terminals inside editors/browsers follow their host application's
Control shortcuts; they are not detected separately. Some terminals use different
bindings and some apps do not support GNOME's quit request. Repeated quit requests
within one second are collapsed to avoid quitting successive apps during ordinary
key repeat; unusually slow repeat settings still need care. Non-US layouts,
unusual keyboards and application-specific behavior require a live trial.
Xremap watches for newly connected keyboards. Grabbing input can affect touchpad
"disable while typing"; no libinput workaround is installed.

If GNOME context disappears or the desktop locks, terminal and quit exceptions
are disabled. The base Command-to-Control mapping remains until Xremap stops.
Consequently Command+C can interrupt a terminal if its context is unavailable.

### Try a changed configuration or roll back

Stop, uninstall, then install the chosen source revision and start again. Do not
edit installed JSON files directly: their recorded hashes protect uninstall from
deleting modifications. A full reinstall records the chosen configuration in the
same recovery manifest and retains the normal uninstall guarantees. There is no
configuration auto-reload while keys are held.

## Background operation and privilege boundary

Start creates two **transient** systemd units:

- System `ubuntu-command-<uid>.service`: upstream Xremap, running as root to read
  input devices and create a virtual keyboard. It is sandboxed with read-only
  filesystem access, hidden home directories except our installed files/runtime
  socket, Unix sockets only, and input/uinput device access. It is tied to the
  graphical login session and stops on logout. It is not enabled at boot.
- User `ubuntu-command-bridge.service`: a small Python socket adapter. It obtains
  the focused app through our GNOME extension and accepts exactly two launch
  requests, `ubuntu-command-quit` and `ubuntu-command-lock`. The latter calls
  a fixed GNOME D-Bus method. It never executes supplied commands, reads
  keyboard events, or sends window titles. It exits after observing Xremap stop.

The socket-mode Xremap client delegates launch requests to this adapter; it does
not run them as root. No session D-Bus policy is modified. The adapter supplies
no app context while locked. Losing the adapter does not itself stop the root
engine: use the emergency chord or Stop if that happens.

No packages, accounts, groups, udev rules, device ACLs, kernel modules, boot
settings, shell configuration, or persistent system/user services are installed.
The existing `/dev/uinput`, Python, GNOME tools, systemd and Polkit are required.
Missing prerequisites cause a refusal. The remapper has keyboard access while
running, as other system-wide remappers do. It does not log keystrokes; window
logging is disabled and the adapter supplies no titles.

## Uninstall boundary

The persistent footprint is:

- `${XDG_DATA_HOME:-~/.local/share}/ubuntu-command/`: controller, runtime manager,
  desktop adapter, three JSON configs, Xremap binary/license and empty session lock.
- `${XDG_DATA_HOME}/gnome-shell/extensions/ubuntu-command@mp-lb.dev/`: JS and metadata.
- `${XDG_DATA_HOME}/applications/ubuntu-command.desktop`.
- `${XDG_STATE_HOME:-~/.local/state}/ubuntu-command/`: recovery manifest and
  operation lock, plus staging files during installation.
- Only our UUID membership in GNOME's enabled/disabled extension lists.

While running, systemd additionally owns the two transient unit definitions and
`/run/user/<uid>/ubuntu-command/desktop.sock`. Service stop/collection removes
these. The kernel releases keyboard grabs and destroys the virtual device when
Xremap exits. Uninstall checks service identity and waits for both units and the
runtime directory to disappear **before removing installed files**. A denied
stop, unresponsive service, or cleanup failure leaves the installation and
recovery record available for retry.

Existing paths and extension UUID entries are never adopted or overwritten.
Files are hashed and the recovery record is written before publication. Modified
files or unexpected files are preserved and reported. Partial installation or
removal is retryable. Original raw extension-list settings are restored when
possible; unrelated changes made during the trial are preserved. Previously
absent parent directories are removed only when empty. The old prototype's
manifest and files can also be uninstalled by this controller.

The source checkout and downloaded reference archives are development material,
not installed application state. Shared system/audit logs are not erased. GNOME
may retain the disabled extension in memory until logout. We do not claim exact
restoration of unrelated caches, timestamps, or OS history.

## Verification

From the pc-setup repository:

```sh
python3 -B -m unittest discover -s os/ubuntu/command/tests -v
```

Set `XREMAP_TEST_BINARY` to a verified upstream binary to additionally validate
both keyboard profiles with its real parser. Set `XREMAP_TEST_SYSTEMD=1` to test
real transient user-service stop and runtime-directory cleanup using a harmless
sleep process. The suite tests filesystem/settings restoration, partial failures,
modified-file preservation, rejected authorization, service identity checks,
real socket protocol/cleanup, private D-Bus/dconf restoration, and the extension
in GJS with mocked GNOME Shell objects.

These checks do not establish real keyboard behavior or prove the privileged
service sandbox works on this host. A fresh login and actual keyboard trial are
still required, followed by uninstall of that active trial. Inactive
install/uninstall results must be reported separately from that trial.

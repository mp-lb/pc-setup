# Gnome MacLike

An optional native GTK/libadwaita dashboard for Ubuntu 26.04, GNOME 50 and Wayland:
keyboard layers, a local wallpaper gallery, a bottom-panel dock preset, and explicit
restore/uninstall controls. This is a first local version, not a new distribution.
**Xremap handles all keyboard input.** Our code installs a pinned upstream binary,
manages its lifetime, and supplies a small GNOME adapter for application context
and normal application quit. There is no custom keyboard driver or mapping engine.

## Install and use

Open the GUI as your normal user from this directory:

```sh
python3 -B gui.py
```

Choose **Check setup**, then **Install** (or **Update installation** for the previous trial), then
**Apply and start** on the Keyboard page. Ubuntu's normal authentication dialog
handles starting/stopping the privileged remapper. Updates fetch and verify the
new binary before removing the old installation, then restore old managed
settings and install inactive; saved layer choices reset. No terminal is needed
after installation: open **Gnome MacLike** from the applications menu.

For an existing Ubuntu Command trial, `python3 -B control.py refresh-launcher`
renames the owned launcher and opens this source checkout's GUI for upgrading.
It does not stop the current remapper or need administrator access. It updates
the launcher's recorded checksum with a retryable staging journal; run the same
command again if interrupted. The normal GUI installation then points the
launcher at the installed GUI, independent of the source checkout.

For GUI-only development changes, run `python3 -B refresh_gui.py` from the source
checkout, then close and reopen the window. This preserves the running keyboard
session, saved choices and restoration records. It refuses changes to other app
modules and records the new GUI checksum for uninstall. Retry the same command
if interrupted. The GUI does not hot-reload; restarting it does not reset settings.
Use `python3 -B refresh_gui.py --dashboard` for compatible dashboard/backend
changes as well. It updates only an explicit set of modules, leaves the remapper,
mapping configuration and adapter unchanged, and journals each publication so an
interrupted update can be retried. Saved settings and restoration baselines stay.

The host must already provide Python GObject, GTK 4 and libadwaita 1.5+. No packages
are installed. Keyboard remapping runs independently of the window: closing the
dashboard does not stop it. **Stop** restores the original keyboard behavior.
Nothing starts automatically at login. GUI controls and generated configurations
do not overwrite any GNOME keybinding settings.

The backend CLI remains available for recovery and automation:

```sh
python3 -B control.py install
python3 -B control.py start
python3 -B control.py stop
python3 -B control.py uninstall
```

First installation may require logging out and back in so GNOME recognizes the
extension. Its launcher also has Stop and Uninstall actions.
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

## Dashboard layers and appearance

Five switches control the Command-position mapping, separate physical Control,
terminal shortcuts, desktop shortcuts, and text navigation. Disabling Command
disables all dependent mappings. Disabling terminal shortcuts does not remove the
physical-Control safety exception for standalone terminals. Application exclusions
(including a Chrome/Chromium convenience switch) disable optional shortcuts in
those apps while keeping the base modifier mapping and emergency stop. This is
not widget detection and adds no browser-specific remapping rules.

Text navigation translates Command+Left/Right to Home/End, Command+Up/Down to
Control+Home/End, and Option+Left/Right to Control+Left/Right. Shift variants select
text. These are generic mappings, including outside text fields; Option arrows
replace normal Linux browser back/forward navigation. Specialized editors and
terminal programs can interpret these keys differently. Turn the layer off or
exclude an app rather than adding an open-ended collection of exceptions.

Setup is checked only on request or after an explicit operation, never on startup
or a polling timer. File reads and image decoding run off the GTK event loop.
The image-only gallery reads local JPEG/PNG/WebP images, filters for at least
5120×2880 landscape images, and shows names and resolution in the preview. A folder can show
up to 200 candidate files. Images stay at their original paths: do not move or
delete an active wallpaper. Choosing a folder alone never changes the wallpaper.
Images are not copied, uploaded, bundled, or assigned new licenses. Filenames
are display labels, not independently verified author credits. Scaled previews
are cached only in memory; there is no thumbnail cache to remove at uninstall.

The dock preset changes only position, full-width layout, centered icons and
fixed visibility in the existing Ubuntu Dock / Dash to Dock extension. Plain
GNOME without that extension reports the missing capability instead of installing
another extension. Wallpapers set only the light/dark background URI and zoom.

Before the first appearance change, the app records each original raw dconf value,
including whether the key was unset. Restore returns those values, not factory
defaults. Newer external edits are preserved and reported. The write-ahead journal
survives partial failures. Restore and uninstall keep it until restoration succeeds.

## Audit and uninstall guarantees

The Restore page exposes the recovery record and a separate timestamped JSON Lines
history. The history is stored with the owned state as `audit.jsonl` (mode 0600).
Intent is flushed to disk before each managed setting, choices/recovery-record,
installed-file, extension or requested service change; an observed result or
failure follows it. Missing results mean interruption or an unknown outcome.
Repeated wallpaper/dock changes remain in the history, while the recovery record
continues to retain the original value. External settings preserved during restore
are recorded too. The log does not contain keystrokes or image contents.

History begins when this version is installed or upgraded. Previous versions'
saved baselines can be carried forward; their missing history cannot be recreated.
The log is local and user-writable, not a tamper-proof forensic record. Service
exits outside the app (logout, emergency stop, crash) are observed by systemd, not
continuously monitored by this optional dashboard.

Export a copy from Restore, or choose **Save history and uninstall** to include
the final uninstall result. Exports must use a new filename. A normal uninstall
removes the internal history with the rest of the app; an explicitly exported
copy is yours to keep. The CLI equivalent is
`python3 -B control.py uninstall --audit-export /path/to/new-history.jsonl`.

The guarantee is restoration of the app's recorded before-state, with newer
external changes preserved—not a reset of Ubuntu to factory defaults. The app
owns its files, recovery state, extension and transient services. Shared system
journals, desktop caches and unrelated personal files are outside its ownership;
it must not erase those to claim the machine has never run it. Source checkouts
and explicitly exported history are also intentionally retained.

## Shortcuts

PC keyboards: left Alt becomes Command, left Super becomes Option/Alt. Apple
keyboards with `--apple`: existing left Command and Option positions are retained.
AltGr and right Super are unchanged. Both physical Control keys send Super in
ordinary applications, and Control in recognized standalone terminals. This
removes duplicate Control shortcuts in ordinary apps. Command uses a separate
Control signal so terminal interrupts and Command shortcuts remain distinct.

- Command behaves as Control by default, including Command-click, copy/paste,
  select all, undo, find, save, new tabs, and app-specific Control shortcuts.
- Command+Tab / Shift+Command+Tab: native GNOME application switching. Keep
  Command held and tap Tab to cycle; release Command to select.
- Command+C/V: Ctrl+Shift+C/V in recognized standalone terminals.
- Physical Control+C interrupts processes in recognized terminals. Outside
  terminals, physical Control is Super: Control+A/T are no longer app shortcuts.
  This does not reproduce macOS Control-based text editing.
- Command+W / Shift+Command+W: the application's Control+W / Control+Shift+W;
  recognized terminals use Ctrl+Shift+W / Ctrl+Shift+Q.
- Command+T/N: Ctrl+Shift+T/N in recognized terminals.
- Command+arrows / Option+Left/Right: text navigation, with Shift selection.
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
native switcher until Command is released. Physical Control remains independent;
its terminal/ordinary-app mapping is selected when the key is pressed. Xremap
retains that choice through key release, even if focus changes.
The lock shortcut calls GNOME's `org.gnome.ScreenSaver.Lock` D-Bus method through
the user bridge. Minimize temporarily releases Command's Control signal and
emits GNOME's Super+H binding. No GNOME keybindings are changed.

Embedded terminals inside editors/browsers follow their host application's
mapping; they are not detected separately. Physical Control will be Super there,
so use the Command key for the terminal's underlying Control shortcuts. This is
a deliberate limit: we maintain one standalone-terminal rule, not per-app or
per-widget exceptions. Some terminals use different
bindings and some apps do not support GNOME's quit request. Repeated quit requests
within one second are collapsed to avoid quitting successive apps during ordinary
key repeat; unusually slow repeat settings still need care. Non-US layouts,
unusual keyboards and application-specific behavior require a live trial.
Xremap watches for newly connected keyboards. Grabbing input can affect touchpad
"disable while typing"; no libinput workaround is installed.

If GNOME context disappears or the desktop locks, terminal and quit exceptions
are disabled, and physical Control falls back to Control. The base
Command-to-Control mapping remains until Xremap stops.
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
  operation lock, mutable `preferences.json` for layer/gallery choices, and
  `appearance.json` for original/applied allowlisted desktop settings. Atomic
  writes may leave recoverable staging files during an interruption.
- Only our UUID membership in GNOME's enabled/disabled extension lists.

While running, systemd additionally owns the two transient unit definitions and
`/run/user/<uid>/ubuntu-command/desktop.sock`, generated `active.json` and a copy of
the active preferences. Service stop/collection removes
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

The dashboard tests additionally cover every layer/hardware combination with the
real parser, appearance restoration against private dconf, external-edit
preservation, rejected preferences, interrupted writes, and uninstall with saved
choices. For a non-mutating visual check of the actual GTK pages:

```sh
GSK_RENDERER=cairo python3 -B os/ubuntu/command/tests/gui_smoke.py /tmp/gnome-mac-preview
```

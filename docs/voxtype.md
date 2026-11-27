# Voxtype on Ubuntu

Voxtype is an optional local dictation app. Install the upstream amd64 deb:

```bash
bash os/ubuntu/install-voxtype.sh
```

The installer pins release 1.3.1 and its upstream SHA-256, validates the Debian
package identity, and uses apt to resolve dependencies without removing other
packages. It keeps the installer in Downloads. Use `--download-only` to prepare
and verify it when administrator access is unavailable, then rerun the command
in a normal terminal to install. This utility does not change macOS or the base
bootstrap. Upstream does not currently publish an AppImage.

After installation, inspect `voxtype info variants`, `voxtype info models`, and
`voxtype doctor`. Use `voxtype configure` for interactive setup, or consult
`voxtype config --help` and `voxtype setup --help` for CLI setup. Select and
download a supported local model before starting the daemon. Saved models from
other applications must match Voxtype's model format; preserve the originals
when testing compatibility.

On GNOME Wayland, bind a desktop shortcut to `voxtype record toggle` and set
`hotkey.enabled` to `false` with `voxtype config set`. This avoids requiring
access to all keyboard input devices. Choose a typing backend that works on
GNOME; `wtype` requires a protocol GNOME does not implement. An existing working
`ydotool` user service can be used. Keep the user's existing shortcut bindings
when adding a Voxtype shortcut.

Once configured:

```bash
voxtype config validate-selection
systemctl --user enable --now voxtype.service
voxtype doctor
```

Verify one dictated sentence in an editor and inspect `voxtype info accel` to
confirm the model's runtime backend. Avoid putting personal configuration,
recordings, model weights, or history in this repository.

For an initial English dictation setup on GNOME with a working Vulkan GPU:

```bash
bash os/ubuntu/configure-voxtype.sh
```

This downloads and selects Parakeet Ultra Q8, selects the packaged Vulkan worker
through the wrapper's `VOXTYPE_GPU=1` environment setting, adds a user service
drop-in, and enables the service. Super+/ toggles recording through GNOME,
with Voxtype's built-in keyboard listener disabled. Both left and right Super
work because GNOME does not distinguish modifier sides. Existing config is backed up before
changing the managed settings. It sets English cleanup and Shift+Enter for
newlines, leaving auto-submit off. Recordings may run up to 10 minutes instead
of the upstream 60-second default. Parakeet's encoder memory grows with the square
of the audio length (about 2.3GB of VRAM for one 4-minute pass, about 5.5GB for 6
minutes), so keep the default 240-second `parakeet.max_window_secs` on 8GB GPUs. `VOXTYPE_MODEL` can select another supported
Parakeet GGUF and `VOXTYPE_SHORTCUT` can change the GNOME accelerator. This is an
explicit setup utility, never part of bootstrap.

GNOME does not implement the Layer Shell protocol used by the waveform OSD.
The utility disables that overlay and the recording desktop notifications, and
installs the `voxtype-bubble@mp-lb.dev` GNOME Shell extension from
`artifacts/gnome-shell/` instead. While Voxtype records or transcribes, it shows
a bubble at the bottom centre of the current monitor with a live level meter
and a stop button (`voxtype record stop`). It reads only Voxtype's public
runtime files, `$XDG_RUNTIME_DIR/voxtype/state` and `audio.sock`. GNOME on
Wayland loads a newly installed extension after the next login. The extension
declares only the GNOME Shell version it was tested on; check it after a GNOME
upgrade.

This setup does not require the `input` group. If that group was added solely
for a previous built-in hotkey setup, remove it with
`sudo gpasswd -d "$USER" input`. Log out and back in if the current session had
already acquired that membership.

To undo automatic startup, run `systemctl --user disable --now voxtype`. Remove
`~/.config/systemd/user/voxtype.service.d/pc-setup-gpu.conf`, then restore the
saved config if one existed. Remove the Voxtype shortcut in GNOME Settings. Disable the bubble with
`gnome-extensions disable voxtype-bubble@mp-lb.dev` and delete its folder under
`~/.local/share/gnome-shell/extensions/`.
Model files remain available for reuse.

References: [release](https://github.com/peteonrails/voxtype/releases/tag/v1.3.1),
[installation](https://github.com/peteonrails/voxtype/blob/v1.3.1/docs/INSTALL.md),
[user manual](https://github.com/peteonrails/voxtype/blob/v1.3.1/docs/USER_MANUAL.md).

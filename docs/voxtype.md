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

References: [release](https://github.com/peteonrails/voxtype/releases/tag/v1.3.1),
[installation](https://github.com/peteonrails/voxtype/blob/v1.3.1/docs/INSTALL.md),
[user manual](https://github.com/peteonrails/voxtype/blob/v1.3.1/docs/USER_MANUAL.md).

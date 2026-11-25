# T3 Code on Ubuntu

Install a trusted, already downloaded x86_64 T3 Code AppImage:

```bash
bash os/ubuntu/install-t3-code.sh
# Or provide a different download path:
bash os/ubuntu/install-t3-code.sh /path/to/T3-Code-x86_64.AppImage
```

The default source is `T3-Code-x86_64.AppImage` in the user's Downloads folder.
The installer keeps that download, copies the executable to
`~/.local/opt/t3-code/T3-Code.AppImage`, adds the `~/.local/bin/t3-code` command,
and installs the bundled launcher and icons under the user's XDG data directory.
It checks the bundled application identity but does not authenticate the download;
only supply an AppImage you trust. No application binaries are stored in this repo.

Launch **T3 Code (Beta)** from the app menu or run `t3-code` from a desktop terminal.
Rerun the installer with a newer download to update the managed copy. The app
uses its upstream AppImage runtime and requires working FUSE support in the
desktop session. A confined agent process may fail to mount it even when desktop
launching works; verify through the user's desktop session in that case.

This optional installer does not change macOS or the base bootstrap. It leaves
application preferences and projects alone.

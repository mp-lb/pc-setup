# Remove OpenWhispr on Ubuntu

The optional utility targets OpenWhispr's Ubuntu deb installation. It is never
run by bootstrap and does not change macOS setup.

Run as the regular desktop user with an unlocked login keyring:

```bash
bash os/ubuntu/uninstall-openwhispr.sh
```

It stops executables belonging to OpenWhispr, copies the complete model cache to
a unique `OpenWhispr-models-*` directory in Downloads, verifies every file with
SHA-256, and only then removes the original cache. The backup contains restore
instructions and checksums. Models and personal state are never committed here.

It deletes OpenWhispr settings, recordings, local history, keyring records,
autostart and local launcher entries, and verified OpenWhispr deb installers in
Downloads. It then purges the `open-whispr` system package using sudo. Shared
dependencies are not automatically removed.

Use `--user-data-only` when administrator access is unavailable. Afterwards,
rerun without that flag in a desktop terminal to finish package removal.
Existing model backups are preserved on subsequent runs.

Some versions create `/etc/udev/rules.d/70-uinput.rules` outside package tracking.
If installation timestamps and contents confirm OpenWhispr created that rule,
and no other application needs it, add `--remove-uinput-rule`. The utility only
removes the exact rule shipped by OpenWhispr. Inspect any `ydotoold` service or
`input` group changes separately because other apps may share them.

Verify that `dpkg-query -W open-whispr` no longer finds the package, no executables
under `/opt/OpenWhispr` remain running, and the app's configuration/cache and
autostart entry are absent. In the backup folder, `sha256sum -c SHA256SUMS`
verifies the preserved files.

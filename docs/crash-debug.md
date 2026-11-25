# Crash debugging on Ubuntu

Opt-in, removable logging for desktop freezes. Not part of the default setup; macOS is unaffected. Requires existing Python 3 and systemd user services; installs no packages and changes no kernel, swap, journal or desktop settings.

Run `bash os/ubuntu/crash-debug.sh install`. The recorder starts immediately and at subsequent user logins. It uses `~/Work/crash-debug`, plus one unit at `~/.config/systemd/user/crash-debug.service` and systemd's enablement symlink. No root or lingering is required.

Every five seconds it records system memory and swap counters, CPU and disk counters, memory/CPU/I/O pressure, available thermal readings, and process IDs, parent IDs, names, resident memory, swap, state and cumulative CPU ticks. Process start ticks distinguish reused PIDs. RSS can double-count shared pages; values are diagnostic estimates, not additive application totals. Command arguments and environment variables are excluded. Logs remain local and private to the user. Rotation retains 16 files of roughly 16 MiB each (about 256 MiB total); retention duration depends on process count. Each sample is flushed and fsynced, though sudden hardware failure can still lose recent data. A fully hung kernel cannot write further samples. The recorder has a 96 MiB memory cap and 5% CPU quota.

Check `bash ~/Work/crash-debug/control.sh status`. After another freeze and restart, retain the samples and inspect the previous boot with `journalctl -b -1`; boot IDs and UTC sample timestamps let you correlate the sources. Rotation may split a boot across files, and the final JSON line may be incomplete after a power cut.

Remove the watcher while retaining evidence:

```sh
bash ~/Work/crash-debug/control.sh uninstall
```

Remove the watcher and **all collected data**, scripts and local reports:

```sh
bash ~/Work/crash-debug/control.sh uninstall --purge
```

Uninstall stops and disables the service, removes its unit and enablement symlink, reloads systemd, and optionally deletes the entire dedicated directory. Normal system journal entries about service startup/shutdown remain under the machine's existing journal retention; no separate journal watcher is installed. The reusable source remains in pc-setup history.

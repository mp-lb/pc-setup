# Memory watchdog on Ubuntu

Ubuntu's `systemd-oomd` ships watching only memory pressure in the desktop session (`user@.service`, 50% for 20s). In practice a machine can thrash on full swap well below that threshold and freeze until a forced power-off, while the kernel OOM killer never fires.

`os/ubuntu/configure-memory-watchdog.sh` (run by Ubuntu setup) adds one drop-in, `/etc/systemd/system/user@.service.d/90-oomd-swap.conf`, setting `ManagedOOMSwap=kill`. When system swap use passes oomd's `SwapUsedLimit` (default 90%), oomd kills the session cgroup using the most swap — usually a runaway build or app — rather than letting the desktop hang. It also ensures `systemd-oomd` is enabled.

Swap size is machine-specific and is not managed here. Check the result with `oomctl`, which should list `user@1000.service` under "Swap Monitored CGroups". Remove the drop-in and run `sudo systemctl daemon-reload` to undo. macOS is unaffected.

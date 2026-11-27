# Agent browser

`bin/agent-browser` gives each coding agent its own Chromium. Each browser runs
on its own invisible screen, so agents never share tabs and nothing opens,
takes focus or sends notifications on the desktop.

```sh
agent-browser start                    # prints the browser ID (a UUID) and debug port
agent-browser status <id>
agent-browser list [--json]                 # with approximate memory per browser
agent-browser stop <id>                # or: stop --all
```

Agents connect over the Chrome DevTools Protocol on the printed debug port.
`start --visible` opens a normal desktop window instead, for when you want to
see it directly.

## How it works

- `Xvnc` (apt `tigervnc-standalone-server`) provides the invisible screen. Its
  VNC stream is only available on a private Unix socket in
  `$XDG_RUNTIME_DIR/agent-browser/`, never on a network port.
- Each browser gets a fresh profile in
  `~/snap/chromium/common/agent-browser/<name>/`, which the Chromium snap can
  write to. `stop` deletes it.
- The screen and Chromium run in one process group, so they always stop
  together, including when Chromium crashes.
- Every `start` and `list` removes leftovers of dead browsers and stops
  browsers older than `AGENT_BROWSER_MAX_AGE_HOURS` (default 12).

## Watching

The cpanel project's Browsers tab lists the running browsers with their memory. It can watch a
browser's screen live, take control of it, and stop browsers one at a time, in bulk or all at once.

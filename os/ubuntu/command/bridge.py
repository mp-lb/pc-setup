"""Xremap's desktop socket protocol, restricted to context and normal app quit.

Runs as the logged-in user. Never opens input devices, executes supplied commands,
or sends window titles. Root Xremap delegates its one launch action here.
"""
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import time
from runtime import Runtime, context


def respond(request, get_context=context):
    current = get_context()
    if request == 'ActiveWindow':
        return {'wm_class': '' if current['locked'] else current['wm_class'], 'title': ''}
    if request == {'Run': ['ubuntu-command-quit']}:
        if current['locked']:
            return {'Error': 'Desktop is locked'}
        get_context('Quit')
        return 'Ok'
    return {'Error': 'Unsupported request'}


class QuitGuard:
    """Collapse Xremap's repeated launch requests while Command+Q is held."""
    def __init__(self):
        self.last = float('-inf')

    def allow(self, now):
        allowed = now - self.last >= 1.0
        self.last = now
        return allowed


def main():
    runtime = Runtime(Path(__file__).resolve().parent)
    path = runtime.directory / 'desktop.sock'
    # The transient user service owns this runtime directory. Never adopt a socket.
    with (runtime.app / 'run.lock').open('r+') as lock, socket.socket(socket.AF_UNIX) as server:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        server.bind(str(path))
        os.chmod(path, 0o600)
        server.listen(4)
        server.settimeout(0.5)
        stopping = False
        def stop(*_):
            nonlocal stopping
            stopping = True
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, stop)
        started = time.monotonic()
        observed_engine = False
        next_check = 0
        quit_guard = QuitGuard()
        try:
            while not stopping:
                now = time.monotonic()
                if now >= next_check:
                    active = runtime.state()['LoadState'] != 'not-found'
                    observed_engine |= active
                    if not active and (observed_engine or now - started > 120):
                        break
                    next_check = now + 1
                try:
                    client, _ = server.accept()
                except socket.timeout:
                    continue
                with client:
                    client.settimeout(0.5)
                    # The protocol is local and bounded; a stalled peer cannot hang GNOME.
                    try:
                        data = b''
                        while b'\n' not in data and len(data) <= 1024:
                            chunk = client.recv(1025 - len(data))
                            if not chunk:
                                break
                            data += chunk
                        if len(data) > 1024 or not data.endswith(b'\n'):
                            raise ValueError('Invalid request')
                        request = json.loads(data)
                        if request == {'Run': ['ubuntu-command-quit']} and not quit_guard.allow(time.monotonic()):
                            reply = 'Ok'
                        else:
                            reply = respond(request)
                    except Exception:
                        # Missing extension/context disables app-sensitive actions.
                        reply = {'Error': 'Desktop context unavailable'}
                    try:
                        client.sendall(json.dumps(reply).encode() + b'\n')
                    except OSError:
                        pass
        finally:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()

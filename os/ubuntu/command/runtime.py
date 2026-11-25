"""Manage transient services. Keyboard handling belongs entirely to Xremap."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15, **kwargs).stdout.strip()


def context(method='Context'):
    try:
        output = run(['/usr/bin/gdbus', 'call', '--session', '--dest', 'org.gnome.Shell',
                      '--object-path', '/dev/mplb/UbuntuCommand', '--method', 'dev.mplb.UbuntuCommand.' + method])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('GNOME adapter unavailable. After first installation, log out and back in before starting.') from exc
    if method == 'Context':
        value = json.loads(ast.literal_eval(output)[0])
        if not isinstance(value.get('locked'), bool) or not isinstance(value.get('wm_class'), str):
            raise RuntimeError('Invalid GNOME context response.')
        return value
    return output


class Runtime:
    def __init__(self, app):
        self.app = Path(app)
        self.uid = os.getuid()
        self.unit = f'ubuntu-command-{self.uid}.service'
        self.bridge_unit = 'ubuntu-command-bridge.service'
        self.directory = Path(f'/run/user/{self.uid}/ubuntu-command')
        self.description = 'Ubuntu Command ' + hashlib.sha256(os.fsencode(self.app)).hexdigest()[:16]

    context = staticmethod(context)

    def state(self, user=False):
        args = ['/usr/bin/systemctl'] + (['--user'] if user else [])
        output = run(args + ['show', self.bridge_unit if user else self.unit,
                             '--property=LoadState,ActiveState,Description,Transient'])
        state = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
        if 'LoadState' not in state:
            raise RuntimeError('Could not determine background service state.')
        if state['LoadState'] != 'not-found' and (state.get('Description') != self.description or state.get('Transient') != 'yes'):
            raise RuntimeError('An unrelated service uses our name; refusing to change it.')
        return state

    def running(self):
        return any(self.state(user)['LoadState'] != 'not-found' for user in (False, True))

    def ensure_absent(self):
        if self.running() or os.path.lexists(self.directory):
            raise RuntimeError('A session or its runtime directory already exists. Stop it before continuing.')

    def wait_absent(self, user):
        for _ in range(50):
            if self.state(user)['LoadState'] == 'not-found':
                return
            time.sleep(0.1)
        raise RuntimeError('Service has not finished stopping; installation preserved.')

    def stop(self):
        if self.state()['LoadState'] != 'not-found':
            # Polkit shows a normal desktop authentication prompt. No shell or sudo rule.
            subprocess.run(['/usr/bin/pkexec', '/usr/bin/systemctl', 'stop', self.unit], check=True)
            self.wait_absent(False)
        if self.state(True)['LoadState'] != 'not-found':
            run(['/usr/bin/systemctl', '--user', 'stop', self.bridge_unit])
            self.wait_absent(True)
        if os.path.lexists(self.directory):
            raise RuntimeError(f'Runtime directory remains; refusing to delete unknown contents: {self.directory}')

    def session_scope(self):
        session = run(['/usr/bin/loginctl', 'show-user', str(self.uid), '--property=Display', '--value'])
        if not re.fullmatch('[a-zA-Z0-9_]+', session):
            raise RuntimeError('Cannot identify the graphical login session.')
        values = dict(line.split('=', 1) for line in run([
            '/usr/bin/loginctl', 'show-session', session, '-p', 'User', '-p', 'Type', '-p', 'Active']).splitlines())
        if values != {'User': str(self.uid), 'Type': 'wayland', 'Active': 'yes'}:
            raise RuntimeError('Start from your active Wayland login session.')
        return f'session-{session}.scope'

    def engine_command(self, apple, scope, generated=False):
        # systemd-run quotes ExecStart arguments. Property values have a separate syntax.
        def bind(path):
            return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
        return [
            '/usr/bin/pkexec', '/usr/bin/systemd-run', '--quiet', '--collect', '--service-type=exec',
            '--expand-environment=no', '--unit=' + self.unit, '--description=' + self.description,
            '--property=BindsTo=' + scope, '--property=After=' + scope,
            '--property=NoNewPrivileges=yes', '--property=CapabilityBoundingSet=CAP_DAC_OVERRIDE',
            '--property=ProtectSystem=strict', '--property=ProtectHome=tmpfs',
            '--property=BindReadOnlyPaths=' + bind(self.app) + ' ' + bind(self.directory),
            '--property=PrivateTmp=yes', '--property=ProtectKernelTunables=yes',
            '--property=ProtectKernelModules=yes', '--property=ProtectControlGroups=yes',
            '--property=RestrictAddressFamilies=AF_UNIX', '--property=RestrictSUIDSGID=yes',
            '--property=DevicePolicy=closed', '--property=DeviceAllow=char-input r',
            '--property=DeviceAllow=/dev/uinput rw', '--property=TimeoutStopSec=5s',
            '--setenv=XREMAP_SOCKET=/run/user/{uid}/ubuntu-command/desktop.sock', '--setenv=RUST_LOG=error',
            str(self.app / 'xremap'), '--desktop=socket', '--no-window-logging', '--allow-launch=true',
            '--watch=device', '--output-device-name=Ubuntu Command (Xremap)',
        ] + ([str(self.directory / 'active.json')] if generated else [
            str(self.app / 'config.json'), str(self.app / ('apple.json' if apple else 'pc.json'))])

    def start(self, apple=False, preferences=None):
        self.ensure_absent()
        current = self.context()
        if current['locked']:
            raise RuntimeError('Unlock the desktop before starting.')
        scope = self.session_scope()
        engine = self.engine_command(apple, scope, generated=preferences is not None)
        # Validate with the actual upstream parser, without touching any input devices.
        compiled = None
        if preferences is not None:
            from profiles import compile_profile
            compiled = json.dumps(compile_profile(self.app, preferences), indent=2)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as validation:
                validation.write(compiled)
                validation.flush()
                run([str(self.app / 'xremap'), '--validate-config', validation.name])
        else:
            run([str(self.app / 'xremap'), '--validate-config',
                 str(self.app / 'config.json'), str(self.app / ('apple.json' if apple else 'pc.json'))])
        run(['/usr/bin/systemd-run', '--user', '--quiet', '--collect', '--service-type=exec',
             '--expand-environment=no', '--unit=' + self.bridge_unit, '--description=' + self.description,
             '--property=PartOf=graphical-session.target', '--property=RuntimeDirectory=ubuntu-command',
             '--property=RuntimeDirectoryMode=0700', '--property=NoNewPrivileges=yes',
             '--property=UMask=0077', '--property=TimeoutStopSec=5s',
             '--setenv=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/' + str(self.uid) + '/bus',
             '/usr/bin/python3', '-B', str(self.app / 'bridge.py')])
        try:
            for _ in range(50):
                if (self.directory / 'desktop.sock').exists():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError('Desktop bridge did not start.')
            if compiled is not None:
                with (self.directory / 'active.json').open('x') as stream:
                    stream.write(compiled)
                with (self.directory / 'preferences.json').open('x') as stream:
                    json.dump(preferences, stream)
            subprocess.run(engine, check=True)
            time.sleep(0.4)
            if self.state().get('ActiveState') != 'active':
                raise RuntimeError('Xremap exited during startup. See journalctl -u ' + self.unit)
            if self.state(True).get('ActiveState') != 'active' or not (self.directory / 'desktop.sock').exists():
                raise RuntimeError('Desktop bridge exited before Xremap was ready. Please start again.')
        except BaseException:
            # A rejected authentication must not leave an orphaned user bridge.
            self.stop()
            raise

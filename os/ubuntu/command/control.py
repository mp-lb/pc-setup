#!/usr/bin/python3
"""Install/remove a closed set of new user files; never replace existing files."""
import argparse
import ast
import contextlib
import ctypes
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

# Direct invocation must be as clean as the launcher: importing our runtime
# must not create unrecorded files that would prevent a safe uninstall.
sys.dont_write_bytecode = True

UUID = 'ubuntu-command@mp-lb.dev'
SCHEMA = 'org.gnome.shell'
KEYS = ('enabled-extensions', 'disabled-extensions')
VERSION = '0.15.19'
ARCHIVES = {
    'x86_64': '61db029d4ee19b9431120ab740574b9b0d2740d9b5b98bbc3375601fdf2687d3',
    'aarch64': 'a0f1cf1428c8a60d95009519cffc2971bbcf695564ea1fcd5e95aa3719dd69b0',
}
APP_FILES = ('control.py', 'runtime.py', 'bridge.py', 'profiles.py', 'preferences.py', 'dashboard.py', 'gui.py',
             'config.json', 'pc.json', 'apple.json', 'xremap', 'XREMAP-LICENSE')


def engine_payload(archive=None):
    arch = platform.machine()
    if arch not in ARCHIVES:
        raise RuntimeError('No pinned Xremap binary for this architecture.')
    if archive is None:
        url = f'https://github.com/xremap/xremap/releases/download/v{VERSION}/xremap-linux-{arch}-socket.zip'
        with urllib.request.urlopen(url, timeout=60) as response:
            blob = response.read(32 * 1024 * 1024 + 1)
    else:
        blob = Path(archive).read_bytes()
    if hashlib.sha256(blob).hexdigest() != ARCHIVES[arch]:
        raise RuntimeError('Xremap archive checksum mismatch; nothing installed.')
    # Read the one expected file, never extract archive paths onto the filesystem.
    with zipfile.ZipFile(io.BytesIO(blob)) as bundle:
        if bundle.namelist() != ['xremap'] or bundle.getinfo('xremap').file_size > 64 * 1024 * 1024:
            raise RuntimeError('Unexpected Xremap archive contents.')
        return bundle.read('xremap')


def command(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def publish(source, target):
    """Atomic publication without replacing a concurrently-created destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(target))


def variants(value):
    return ast.literal_eval(value.removeprefix('@as '))


class Desktop:
    def read(self, key):
        return {
            'raw': command(['dconf', 'read', '/org/gnome/shell/' + key]) or None,
            'value': variants(command(['gsettings', 'get', SCHEMA, key])),
        }

    def restore(self, key, before):
        current = self.read(key)
        cleaned = [item for item in current['value'] if item != UUID]
        if cleaned == before['value']:
            path = '/org/gnome/shell/' + key
            if before['raw'] is None:
                command(['dconf', 'reset', path])
            else:
                command(['dconf', 'write', path, before['raw']])
        elif cleaned != current['value']:
            command(['gsettings', 'set', SCHEMA, key, repr(cleaned)])
        if UUID in self.read(key)['value']:
            raise RuntimeError('Extension entry remains in ' + key)

    def enable(self):
        command(['gnome-extensions', 'enable', UUID])

    def disable(self):
        # Direct list restoration below also works if GNOME has not loaded it yet.
        subprocess.run(['gnome-extensions', 'disable', UUID], capture_output=True)


class Install:
    def __init__(self, data=None, state=None, desktop=None, source=None, engine=None, runtime=None):
        self.data = Path(data or os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share').absolute()
        self.state = Path(state or os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state').absolute()
        self.app = self.data / 'ubuntu-command'
        self.ext = self.data / 'gnome-shell/extensions' / UUID
        self.launcher = self.data / 'applications/ubuntu-command.desktop'
        self.record_dir = self.state / 'ubuntu-command'
        self.record = self.record_dir / 'manifest.json'
        self.desktop = desktop or Desktop()
        self.source = Path(source).resolve() if source else Path(__file__).resolve().parent
        self.roots = {'app': self.app, 'extension': self.ext, 'launcher': self.launcher}
        from runtime import Runtime
        self.runtime = runtime or Runtime(self.app)
        self.engine = engine

    def files(self):
        payload = {}
        for name in APP_FILES:
            payload['app/' + name] = (self.engine if self.engine is not None else engine_payload()) if name == 'xremap' else (self.source / name).read_bytes()
        for name in ('metadata.json', 'extension.js'):
            payload['extension/' + name] = (self.source / 'extension' / name).read_bytes()
        payload['app/run.lock'] = b''
        payload['launcher'] = self.launcher_payload()
        return payload

    def launcher_payload(self, gui_path=None):
        executable = str(self.app / 'control.py').replace('\\', '\\\\').replace('"', '\\"')
        gui = str(gui_path or self.app / 'gui.py').replace('\\', '\\\\').replace('"', '\\"')
        return ('[Desktop Entry]\nType=Application\nName=Gnome MacLike\n'
                              'Comment=Familiar shortcuts, wallpapers and dock, with restore controls\n'
                              f'Exec=/usr/bin/python3 -B "{gui}"\n'
                              'Icon=preferences-desktop-keyboard-shortcuts\nStartupWMClass=dev.mplb.GnomeMacLike\n'
                              'Terminal=false\nCategories=Settings;Utility;\nActions=Stop;Uninstall;\n\n'
                              '[Desktop Action Stop]\nName=Stop shortcuts\n'
                              f'Exec=/usr/bin/python3 -B "{executable}" stop --notify\n\n'
                              '[Desktop Action Uninstall]\nName=Uninstall Gnome MacLike\n'
                              f'Exec=/usr/bin/python3 -B "{executable}" uninstall --notify\n').encode()

    def refresh_launcher(self):
        """Expose the GUI without restarting the remapper or losing file ownership."""
        from preferences import write_json
        with self.operation():
            info = self.load()
            for root in (self.app, self.record_dir, self.launcher):
                if root.is_symlink():
                    raise RuntimeError(f'Replaced installation path: {root}')
            stage = self.record_dir / 'staging'
            pending = stage / 'launcher-update.json'
            current = hashlib.sha256(self.launcher.read_bytes()).hexdigest()
            if os.path.lexists(stage):
                if stage.is_symlink() or not pending.is_file() or pending.is_symlink():
                    raise RuntimeError('An unfinished installation exists; use its uninstall recovery first.')
                if {p.name for p in stage.iterdir()} - {'launcher-update.json', 'launcher'}:
                    raise RuntimeError('Unexpected staging files preserved.')
                plan = json.loads(pending.read_text())
                if set(plan) != {'before', 'after', 'content'} or not isinstance(plan['content'], str):
                    raise ValueError('Invalid launcher recovery record.')
                if hashlib.sha256(plan['content'].encode()).hexdigest() != plan['after']:
                    raise ValueError('Launcher recovery checksum mismatch.')
                if current not in (plan['before'], plan['after']) or info['files']['launcher'] not in (plan['before'], plan['after']):
                    raise RuntimeError('Launcher changed outside this update; preserved for review.')
            else:
                if current != info['files']['launcher']:
                    raise RuntimeError('Modified launcher preserved; refusing to overwrite it.')
                gui = self.app / 'gui.py'
                if not gui.is_file():
                    gui = self.source / 'gui.py'  # Legacy installation: open the upgrade dashboard.
                if not gui.is_file():
                    raise RuntimeError('GUI source is missing; nothing changed.')
                content = self.launcher_payload(gui)
                if hashlib.sha256(content).hexdigest() == current:
                    print('Launcher is already current.')
                    return
                plan = {'before': current, 'after': hashlib.sha256(content).hexdigest(), 'content': content.decode()}
                stage.mkdir(mode=0o700)
                write_json(pending, plan)
            if current != plan['after']:
                staged = stage / 'launcher'
                if staged.is_symlink():
                    raise RuntimeError('Replaced staged launcher; preserved for review.')
                with staged.open('wb') as stream:
                    stream.write(plan['content'].encode())
                    stream.flush()
                    os.fsync(stream.fileno())
                info['files']['launcher'] = plan['after']
                self.save(info)
                os.replace(staged, self.launcher)
            elif info['files']['launcher'] != plan['after']:
                info['files']['launcher'] = plan['after']
                self.save(info)
            pending.unlink()
            stage.rmdir()
        print('Gnome MacLike launcher updated. The keyboard session was not changed.')

    def path_for(self, label):
        # Never use arbitrary paths from a writable manifest for cleanup.
        if label == 'launcher':
            return self.launcher
        allowed = {'app/' + name for name in (*APP_FILES, 'run.lock', 'driver.py', 'mapping.py')} | {
                   'extension/metadata.json', 'extension/extension.js'}
        if label not in allowed:
            raise ValueError('Unknown installation file: ' + label)
        root, name = label.split('/')
        return self.roots[root] / name

    def allowed_dirs(self):
        result = set()
        for leaf in (self.app, self.ext, self.launcher.parent, self.record_dir):
            # Ancestors are only removed if recorded as absent before installation
            # and still empty. This covers initially missing XDG parent folders.
            cursor = leaf
            while cursor != cursor.parent:
                result.add(str(cursor))
                cursor = cursor.parent
        return result

    def load(self):
        info = json.loads(self.record.read_text())
        if info.get('version') not in (1, 2) or set(info) != {'version', 'files', 'dirs', 'desktop'}:
            raise ValueError('Invalid installation manifest; refusing destructive cleanup.')
        if not isinstance(info['files'], dict) or set(info['desktop']) != set(KEYS):
            raise ValueError('Invalid installation manifest contents.')
        for label, digest in info['files'].items():
            self.path_for(label)
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError('Invalid file digest.')
        if not set(info['dirs']) <= self.allowed_dirs():
            raise ValueError('Invalid created-directory record.')
        for setting in info['desktop'].values():
            if set(setting) != {'raw', 'value'} or not isinstance(setting['value'], list):
                raise ValueError('Invalid desktop baseline.')
        return info

    def save(self, info):
        fd, temp = tempfile.mkstemp(dir=self.record_dir, prefix='.manifest-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(info, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.record)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def install(self):
        for path in (*self.roots.values(), self.record_dir):
            if os.path.lexists(path):
                raise RuntimeError(f'Refusing to overwrite existing path: {path}')
        self.runtime.ensure_absent()
        baseline = {key: self.desktop.read(key) for key in KEYS}
        if any(UUID in item['value'] for item in baseline.values()):
            raise RuntimeError('A pre-existing extension setting uses our UUID; nothing changed.')
        payload = self.files()  # Read all sources before changing the filesystem.
        new_dirs = sorted((p for p in self.allowed_dirs() if not os.path.lexists(p)),
                          key=lambda p: len(Path(p).parts))
        info = {'version': 2, 'files': {k: hashlib.sha256(v).hexdigest() for k, v in payload.items()},
                'dirs': new_dirs, 'desktop': baseline}
        # Create the journal first. No desktop preferences change during install.
        self.record_dir.mkdir(parents=True, mode=0o700)
        try:
            self.save(info)
            staging = self.record_dir / 'staging'
            staging.mkdir()
            for label, content in payload.items():
                staged = staging / label
                staged.parent.mkdir(parents=True, exist_ok=True)
                with staged.open('xb') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if label == 'app/xremap':
                    staged.chmod(0o755)
            for directory in new_dirs:
                if Path(directory) not in (self.app, self.ext):
                    Path(directory).mkdir(exist_ok=True, mode=0o700)
            # Cross-filesystem XDG state/data directories need staging on the data
            # filesystem. Reject them before publishing rather than partially copy.
            for label, target in self.roots.items():
                if os.path.lexists(target):
                    raise RuntimeError(f'Path appeared during installation: {target}')
                publish(staging / label, target)
            staging.rmdir()
        except BaseException:
            if not self.record.exists():
                for temporary in self.record_dir.glob('.manifest-*'):
                    temporary.unlink()
                for directory in sorted(new_dirs, key=lambda p: len(Path(p).parts), reverse=True):
                    try:
                        Path(directory).rmdir()
                    except OSError:
                        pass
            # Keep the journal for retryable removal of a partial installation.
            print(f'Incomplete install: run {self.source / "control.py"} uninstall', file=sys.stderr)
            raise
        print('Installed, inactive. No device permissions or system settings changed.')
        print('On Wayland a logout/login may be needed before GNOME recognizes the extension.')

    @contextlib.contextmanager
    def operation(self):
        # Existing state only: status/uninstall on an absent installation creates nothing.
        if not self.record_dir.is_dir():
            yield
            return
        with (self.record_dir / 'operation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def sessions(self):
        target = os.fsencode(self.app / 'driver.py')
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                if proc.stat().st_uid == os.getuid() and target in (proc / 'cmdline').read_bytes().split(b'\0'):
                    yield int(proc.name)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue

    def stop(self):
        self.runtime.stop()
        # Discover live processes rather than trusting a crash-prone PID file.
        # pidfds ensure a recycled PID can never receive our signal.
        import select
        target = os.fsencode(self.app / 'driver.py')
        for pid in list(self.sessions()):
            try:
                pidfd = os.pidfd_open(pid)
            except ProcessLookupError:
                continue
            try:
                proc = Path('/proc') / str(pid)
                if proc.stat().st_uid != os.getuid() or target not in (proc / 'cmdline').read_bytes().split(b'\0'):
                    continue
                signal.pidfd_send_signal(pidfd, signal.SIGTERM)
                if not select.select([pidfd], [], [], 5)[0]:
                    raise RuntimeError('Session did not stop; installation preserved. Use Ctrl+Alt+Esc or close its terminal.')
            except (FileNotFoundError, ProcessLookupError):
                pass
            finally:
                os.close(pidfd)
        if list(self.sessions()):
            raise RuntimeError('A session is still running; installation preserved.')

    def uninstall(self):
        from preferences import FILES, Appearance, validate_state
        if not self.record.exists():
            if any(os.path.lexists(path) for path in (*self.roots.values(), self.record_dir)):
                raise RuntimeError('Owned-looking files exist without a manifest; refusing to guess.')
            print('Already uninstalled.')
            return
        info = self.load()
        for root in (self.app, self.ext, self.record_dir):
            if root.is_symlink():
                raise RuntimeError(f'Replaced installation directory: {root}')
        with self.operation():
            self.stop()
            # Hold the same lock the remapper needs before it can grab devices.
            lock = (self.app / 'run.lock').open('a') if self.app.is_dir() else None
            try:
                if lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                expected = {self.path_for(label) for label in info['files']}
                runtime = {self.app / 'run.lock'}
                for root in (self.app, self.ext):
                    if root.is_symlink():
                        raise RuntimeError(f'Replaced installation directory: {root}')
                    if root.exists():
                        unexpected = set(root.rglob('*')) - expected - runtime
                        if unexpected:
                            raise RuntimeError(f'Unexpected local files preserved: {sorted(map(str, unexpected))}')
                for label, digest in info['files'].items():
                    path = self.path_for(label)
                    if os.path.lexists(path) and (path.is_symlink() or not path.is_file() or
                            hashlib.sha256(path.read_bytes()).hexdigest() != digest):
                        raise RuntimeError(f'Modified file preserved; restore or move it before retrying: {path}')
                for child in self.record_dir.iterdir():
                    if child.name not in ('manifest.json', 'operation.lock', 'staging', *FILES) and not child.name.startswith(('.manifest-', '.settings-')):
                        raise RuntimeError(f'Unexpected recovery file preserved: {child}')
                validate_state(self.record_dir)
                preserved = Appearance(self.record_dir).restore()
                if preserved:
                    print('Preserved newer external desktop changes: ' + ', '.join(preserved))
                self.desktop.disable()
                for key in KEYS:
                    self.desktop.restore(key, info['desktop'][key])
                for path in expected | runtime:
                    path.unlink(missing_ok=True)
                for root in (self.app, self.ext):
                    if root.exists():
                        root.rmdir()
                # Keep the manifest until all potentially failing removal steps finish.
                staging = self.record_dir / 'staging'
                if staging.is_symlink():
                    staging.unlink()
                elif staging.exists():
                    shutil.rmtree(staging)
                for temporary in self.record_dir.glob('.manifest-*'):
                    temporary.unlink()
                for temporary in self.record_dir.glob('.settings-*'):
                    temporary.unlink()
                for name in FILES:
                    (self.record_dir / name).unlink(missing_ok=True)
                self.record.unlink()
                (self.record_dir / 'operation.lock').unlink(missing_ok=True)
                self.record_dir.rmdir()
                for directory in sorted(info['dirs'], key=lambda p: len(Path(p).parts), reverse=True):
                    path = Path(directory)
                    if path.exists():
                        try:
                            path.rmdir()  # Never remove unrelated contents in a shared parent.
                        except OSError:
                            pass
            finally:
                if lock:
                    lock.close()
        print('Uninstalled. Session stopped, extension/settings restored, owned files removed.')

    def start(self, apple=False):
        from preferences import read_preferences
        with self.operation():
            info = self.load()
            if info['version'] != 2:
                raise RuntimeError('Uninstall the old prototype before installing Xremap.')
            for label, digest in info['files'].items():
                path = self.path_for(label)
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise RuntimeError(f'Installed file differs from the recorded version: {path}')
            self.runtime.ensure_absent()
            self.desktop.enable()
            # Fail before requesting administrator access if GNOME hasn't loaded us.
            self.runtime.context()
            preferences = read_preferences(self.record_dir)
            if apple:
                preferences['keyboard'] = 'apple'
            self.runtime.start(preferences['keyboard'] == 'apple', preferences=preferences)
        print('Xremap is running in the background. Physical Ctrl+Alt+Esc stops it.')


def preflight():
    try:
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Adw
        if Adw.get_major_version() == 1 and Adw.get_minor_version() < 5:
            raise RuntimeError('The dashboard requires libadwaita 1.5 or newer.')
    except (ImportError, ValueError) as exc:
        raise RuntimeError('The dashboard requires Python GObject, GTK 4 and libadwaita. No packages were installed.') from exc
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or platform.machine() not in ('x86_64', 'aarch64'):
        raise RuntimeError('This version supports 64-bit Ubuntu only.')
    if os.environ.get('XDG_SESSION_TYPE') != 'wayland' or 'GNOME' not in os.environ.get('XDG_CURRENT_DESKTOP', ''):
        raise RuntimeError('This version supports the Ubuntu GNOME Wayland session only.')
    if not command(['gnome-shell', '--version']).split()[-1].startswith('50.'):
        raise RuntimeError('This first version targets GNOME 50; other releases need explicit testing.')
    for name in ('gdbus', 'busctl', 'gsettings', 'dconf', 'pkexec', 'systemd-run', 'systemctl', 'loginctl', 'gnome-extensions'):
        if not shutil.which(name):
            raise RuntimeError(f'Missing prerequisite: {name}. No packages will be installed automatically.')
    if not Path('/dev/uinput').exists():
        raise RuntimeError('/dev/uinput is unavailable. No module or boot settings were changed.')


def main():
    parser = argparse.ArgumentParser(description='Optional, session-only Mac-style keyboard shortcuts on Ubuntu.')
    parser.add_argument('action', choices=('install', 'start', 'stop', 'uninstall', 'status', 'refresh-launcher'))
    parser.add_argument('--notify', action='store_true', help='Show desktop feedback when launched without a terminal.')
    parser.add_argument('--archive', type=Path, help='Use a locally downloaded, checksum-verified Xremap release zip.')
    parser.add_argument('--apple', action='store_true', help='Use the physical Command key on an Apple keyboard.')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError('Run control.py as your normal user. Start/stop request administrator authorization for the transient service.')
    if args.action in ('install', 'start'):
        preflight()
    install = Install(engine=engine_payload(args.archive) if args.action == 'install' else None)
    if args.action == 'install':
        install.install()
    elif args.action == 'start':
        install.start(args.apple)
    elif args.action == 'stop':
        with install.operation():
            install.stop()
        print('Session stopped.')
    elif args.action == 'uninstall':
        install.uninstall()
    elif args.action == 'refresh-launcher':
        install.refresh_launcher()
    else:
        print('Installed' if install.record.exists() else 'Not installed')
        print('Session running' if install.runtime.running() or list(install.sessions()) else 'No running session')
    if args.notify:
        notify({'start': 'Shortcuts are running. Ctrl+Alt+Esc stops them.',
                'stop': 'Shortcuts stopped.', 'uninstall': 'Gnome MacLike removed.'}.get(args.action, 'Done.'))
    return 0


def notify(message):
    if shutil.which('notify-send'):
        subprocess.run(['notify-send', 'Gnome MacLike', message], check=False)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Gnome MacLike: {exc}', file=sys.stderr)
        if '--notify' in sys.argv:
            notify(str(exc))
        sys.exit(1)

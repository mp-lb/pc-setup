"""Dashboard operations, kept separate from GTK and serialized by the installer."""
import hashlib
import json

from control import APP_FILES, Install, engine_payload, preflight
from preferences import Appearance, read_preferences, save_preferences
from profiles import validate


class Dashboard:
    def __init__(self, install=None, archive=None):
        self.install = install or Install()
        self.archive = archive

    def status(self):
        install = self.install
        present = install.record.exists()
        info = install.load() if present else None
        update = present and any(
            info['files'].get('app/' + name) != hashlib.sha256((install.source / name).read_bytes()).hexdigest()
            for name in APP_FILES if name != 'xremap')
        state = install.runtime.state()
        bridge = install.runtime.state(True)
        return {'installed': present, 'update': bool(update),
                'running': state.get('ActiveState') == 'active',
                'bridge': bridge.get('ActiveState') == 'active',
                'preferences': read_preferences(install.record_dir),
                'appearance': Appearance(install.record_dir).load()}

    def install_current(self):
        preflight()
        # Fetch/verify before removing anything. Failure leaves the old install intact.
        source = self.install.source
        if source == self.install.app:
            raise RuntimeError('Updates must be launched from the new source checkout.')
        payload = engine_payload(self.archive)
        if self.install.record.exists():
            self.install.uninstall()
        self.install.engine = payload
        self.install.install()
        return 'Installed. Choose your layers, then Apply and start. A first installation may need a logout/login.'

    def apply_keyboard(self, preferences):
        preferences = validate(preferences)
        preflight()
        if not self.install.record.exists():
            raise RuntimeError('Install Gnome MacLike first.')
        with self.install.operation():
            self.install.stop()
            save_preferences(self.install.record_dir, preferences)
        self.install.start()
        return 'Keyboard layers are running. Stop returns the keyboard to its original behavior.'

    def stop(self):
        with self.install.operation():
            self.install.stop()
        return 'Keyboard remapping stopped. Native key behavior is restored.'

    def appearance(self, action, value=None):
        if not self.install.record.exists():
            raise RuntimeError('Install Gnome MacLike first so changes have a recovery record.')
        with self.install.operation():
            appearance = Appearance(self.install.record_dir)
            if action == 'dock':
                appearance.dock()
            elif action == 'wallpaper':
                appearance.wallpaper(value)
            elif action in ('restore-dock', 'restore-wallpaper'):
                skipped = appearance.restore(action.removeprefix('restore-'))
                if skipped:
                    return 'Restored our changes; preserved newer changes made outside Gnome MacLike.'
            else:
                raise ValueError('Unknown appearance action.')
        return 'Desktop setting updated. Its original value is saved for restoration.'

    def save_folder(self, folder):
        # Browsing the source preview must not add files to a legacy installation.
        if self.install.record.exists() and not self.status()['update']:
            with self.install.operation():
                prefs = read_preferences(self.install.record_dir)
                prefs['wallpaper_folder'] = str(folder)
                save_preferences(self.install.record_dir, prefs)

    def restore(self):
        with self.install.operation():
            self.install.stop()
            skipped = Appearance(self.install.record_dir).restore()
        return ('Keyboard stopped and managed appearance restored.' +
                (' Newer external changes were preserved.' if skipped else ''))

    def uninstall(self):
        self.install.uninstall()
        return 'Uninstalled. Keyboard stopped, managed desktop changes restored, owned files removed.'

    def details(self):
        install = self.install
        if not install.record.exists():
            return 'Not installed. No desktop settings have been changed by this dashboard.'
        info = install.load()
        lines = ['Installed files', *[str(install.path_for(label)) for label in sorted(info['files'])],
                 '', 'Recovery and choices', str(install.record),
                 str(install.record_dir / 'preferences.json'), str(install.record_dir / 'appearance.json'),
                 '', 'Original GNOME extension settings', json.dumps(info['desktop'], indent=2),
                 '', 'Appearance changes (before → applied)', json.dumps(Appearance(install.record_dir).load(), indent=2),
                 '', 'Runtime only', install.runtime.unit, install.runtime.bridge_unit, str(install.runtime.directory)]
        return '\n'.join(lines)

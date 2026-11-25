"""Mutable user choices and a narrowly scoped, write-ahead appearance journal."""
import copy
import json
import os
from pathlib import Path
import tempfile

from profiles import DEFAULTS, validate
from runtime import run

FILES = ('preferences.json', 'appearance.json')
DOCK = '/org/gnome/shell/extensions/dash-to-dock/'
BACKGROUND = '/org/gnome/desktop/background/'
DOCK_PRESET = {'dock-position': "'BOTTOM'", 'extend-height': 'true',
               'always-center-icons': 'true', 'dock-fixed': 'true'}
ALLOWED = {DOCK + key: 'dock' for key in DOCK_PRESET} | {
    BACKGROUND + key: 'wallpaper' for key in ('picture-uri', 'picture-uri-dark', 'picture-options')}


def read_json(path, default):
    path = Path(path)
    if path.is_symlink():
        raise RuntimeError('Refusing a replaced settings file: ' + str(path))
    return json.loads(path.read_text()) if path.exists() else copy.deepcopy(default)


def write_json(path, value):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink():
        raise RuntimeError('Refusing replaced settings paths.')
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.settings-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_preferences(directory):
    return validate(read_json(Path(directory) / 'preferences.json', DEFAULTS))


def save_preferences(directory, value):
    write_json(Path(directory) / 'preferences.json', validate(value))


class Dconf:
    def read(self, path):
        return run(['dconf', 'read', path]) or None

    def write(self, path, value):
        run(['dconf', 'reset', path] if value is None else ['dconf', 'write', path, value])
        if self.read(path) != value:
            raise RuntimeError('Desktop did not retain the requested setting: ' + path)


class Appearance:
    def __init__(self, directory, desktop=None):
        self.path = Path(directory) / 'appearance.json'
        self.desktop = desktop or Dconf()

    def load(self):
        value = read_json(self.path, {})
        if not isinstance(value, dict) or not set(value) <= set(ALLOWED):
            raise ValueError('Unknown desktop settings in recovery journal; preserved for review.')
        for entry in value.values():
            if not isinstance(entry, dict) or set(entry) != {'before', 'after'}:
                raise ValueError('Invalid desktop recovery journal.')
            if any(v is not None and (not isinstance(v, str) or len(v) > 32768) for v in entry.values()):
                raise ValueError('Invalid desktop recovery values.')
        return value

    def apply(self, changes):
        if not set(changes) <= set(ALLOWED):
            raise ValueError('Setting outside our managed scope.')
        journal = self.load()
        # Refuse to overwrite a newer external edit without explicit restoration.
        for path in changes:
            if path in journal and self.desktop.read(path) not in (journal[path]['before'], journal[path]['after']):
                raise RuntimeError('This setting changed outside Gnome MacLike. Restore this section first: ' + path)
        for path, after in changes.items():
            before = journal[path]['before'] if path in journal else self.desktop.read(path)
            journal[path] = {'before': before, 'after': after}
            write_json(self.path, journal)  # Recoverable even if the following write fails.
            self.desktop.write(path, after)

    def dock(self):
        # Plain GNOME without Ubuntu Dock is supported without installing extensions.
        schemas = run(['gsettings', 'list-schemas']).splitlines()
        if 'org.gnome.shell.extensions.dash-to-dock' not in schemas:
            raise RuntimeError('Ubuntu Dock / Dash to Dock is not installed. No extension was added.')
        self.apply({DOCK + key: value for key, value in DOCK_PRESET.items()})

    def wallpaper(self, filename):
        path = Path(filename).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError('Choose an image file.')
        # URI encoding makes a safe single-quoted GVariant string, including quotes.
        value = "'" + path.as_uri().replace("'", '%27') + "'"
        self.apply({BACKGROUND + 'picture-uri': value, BACKGROUND + 'picture-uri-dark': value,
                    BACKGROUND + 'picture-options': "'zoom'"})

    def restore(self, group=None):
        journal = self.load()
        preserved = []
        for path, entry in list(journal.items()):
            if group is not None and ALLOWED[path] != group:
                continue
            current = self.desktop.read(path)
            if current == entry['after']:
                self.desktop.write(path, entry['before'])
            elif current != entry['before']:
                preserved.append(path)  # Leave newer external edits alone.
            del journal[path]
            write_json(self.path, journal)
        if not journal:
            self.path.unlink(missing_ok=True)
        return preserved


def validate_state(directory):
    read_preferences(directory)
    Appearance(directory).load()

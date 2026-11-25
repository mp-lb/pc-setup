#!/usr/bin/python3
"""Development-only GUI refresh; no session or desktop changes.

Run from the source checkout, then restart the window. An interrupted publication
must be retried with this command before start/uninstall can verify ownership.
"""
import hashlib
import json
import os
import sys
sys.dont_write_bytecode = True
from control import Install, APP_FILES
from preferences import write_json


def refresh(install=None):
    install = install or Install()
    with install.operation():
        info = install.load()
        target = install.app / 'gui.py'
        for path in (install.app, install.record_dir, target):
            if path.is_symlink():
                raise RuntimeError(f'Replaced installation path preserved: {path}')
        # This shortcut is deliberately limited to a compatible GUI-only update.
        for name in APP_FILES:
            if name in ('gui.py', 'xremap'):
                continue
            expected = info['files'].get('app/' + name)
            if any(hashlib.sha256(path.read_bytes()).hexdigest() != expected
                   for path in (install.source / name, install.app / name)):
                raise RuntimeError(f'{name} also changed; use the full installer.')
        stage = install.record_dir / 'staging'
        pending = stage / 'gui-update.json'
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        if os.path.lexists(stage):
            if stage.is_symlink() or not pending.is_file() or pending.is_symlink():
                raise RuntimeError('Unfinished installation preserved; recover it first.')
            if {p.name for p in stage.iterdir()} - {'gui-update.json', 'gui.py'}:
                raise RuntimeError('Unexpected staging files preserved.')
            plan = json.loads(pending.read_text())
            if set(plan) != {'before', 'after', 'content'} or not isinstance(plan['content'], str):
                raise ValueError('Invalid GUI recovery record.')
            if hashlib.sha256(plan['content'].encode()).hexdigest() != plan['after']:
                raise ValueError('GUI recovery checksum mismatch.')
            if current not in (plan['before'], plan['after']) or info['files']['app/gui.py'] not in (plan['before'], plan['after']):
                raise RuntimeError('GUI changed outside this update; preserved for review.')
        else:
            if current != info['files']['app/gui.py']:
                raise RuntimeError('Modified GUI preserved; refusing to overwrite it.')
            content = (install.source / 'gui.py').read_text()
            after = hashlib.sha256(content.encode()).hexdigest()
            if current == after:
                return
            plan = {'before': current, 'after': after, 'content': content}
            stage.mkdir(mode=0o700)
            write_json(pending, plan)
        if current != plan['after']:
            staged = stage / 'gui.py'
            if staged.is_symlink():
                raise RuntimeError('Replaced staged GUI preserved.')
            with staged.open('wb') as stream:
                stream.write(plan['content'].encode())
                stream.flush()
                os.fsync(stream.fileno())
            info['files']['app/gui.py'] = plan['after']
            install.save(info)
            os.replace(staged, target)
        elif info['files']['app/gui.py'] != plan['after']:
            info['files']['app/gui.py'] = plan['after']
            install.save(info)
        pending.unlink()
        stage.rmdir()
    print('GUI updated. Restart the window; keyboard and desktop settings were preserved.')


if __name__ == '__main__':
    refresh()

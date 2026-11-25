#!/usr/bin/python3
"""Development-only GUI refresh; no session or desktop changes.

Run from the source checkout, then restart the window. An interrupted publication
must be retried with this command before start/uninstall can verify ownership.
"""
import argparse
import hashlib
import json
import os
import sys
sys.dont_write_bytecode = True
from control import Install, APP_FILES
from preferences import write_json

DASHBOARD_FILES = {'gui.py', 'dashboard.py', 'preferences.py', 'control.py', 'audit.py'}


def refresh(install=None, dashboard=False):
    if dashboard:
        return refresh_dashboard(install or Install())
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


def refresh_dashboard(install):
    """Publish only dashboard modules; engine, mapping and adapter stay unchanged."""
    with install.operation():
        info = install.load()
        for root in (install.app, install.record_dir, install.record):
            if root.is_symlink():
                raise RuntimeError(f'Replaced installation path preserved: {root}')
        for name in set(APP_FILES) - DASHBOARD_FILES - {'xremap'}:
            expected = info['files'].get('app/' + name)
            for path in (install.source / name, install.app / name):
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise RuntimeError(f'{name} also changed; use the full installer.')
        stage = install.record_dir / 'staging'
        pending = stage / 'dashboard-update.json'
        if os.path.lexists(stage):
            if stage.is_symlink() or pending.is_symlink() or not pending.is_file():
                raise RuntimeError('Unfinished installation preserved; recover it first.')
            if {p.name for p in stage.iterdir()} - ({pending.name} | DASHBOARD_FILES):
                raise RuntimeError('Unexpected staging files preserved.')
            plan = json.loads(pending.read_text())
            if not isinstance(plan, dict) or not set(plan) <= DASHBOARD_FILES:
                raise ValueError('Invalid dashboard recovery record.')
        else:
            plan = {}
            for name in sorted(DASHBOARD_FILES):
                target = install.app / name
                if target.is_symlink():
                    raise RuntimeError(f'Modified file preserved: {target}')
                before = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
                if before != info['files'].get('app/' + name):
                    raise RuntimeError(f'Modified file preserved: {target}')
                content = (install.source / name).read_text()
                after = hashlib.sha256(content.encode()).hexdigest()
                if before != after:
                    plan[name] = dict(before=before, after=after, content=content)
            if not plan:
                print('Dashboard is already current.')
                return
            install.audit.append('history boundary',
                note='History begins here if upgrading from a version without an audit log. Earlier activity cannot be reconstructed.',
                recovery_record=info,
                saved_state={name: json.loads((install.record_dir / name).read_text())
                             for name in ('preferences.json', 'appearance.json') if (install.record_dir / name).exists()})
            stage.mkdir(mode=0o700)
            write_json(pending, plan)
        # Validate the whole plan and all targets before publishing any part.
        for name, entry in plan.items():
            if not isinstance(entry, dict) or set(entry) != {'before', 'after', 'content'} or not isinstance(entry['content'], str):
                raise ValueError('Invalid dashboard recovery entry.')
            if hashlib.sha256(entry['content'].encode()).hexdigest() != entry['after']:
                raise ValueError('Dashboard recovery checksum mismatch.')
            target = install.app / name
            if target.is_symlink():
                raise RuntimeError(f'Modified file preserved: {target}')
            current = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            if current not in (entry['before'], entry['after']) or info['files'].get('app/' + name) not in (entry['before'], entry['after']):
                raise RuntimeError(f'Dashboard file changed outside this update: {target}')
        # Publish the controller last so its new imports are already available.
        for name in sorted(plan, key=lambda n: (n == 'control.py', n)):
            entry = plan[name]
            target = install.app / name
            def publish_module():
                staged = stage / name
                if staged.is_symlink():
                    raise RuntimeError('Replaced staged dashboard file preserved.')
                with staged.open('wb') as stream:
                    stream.write(entry['content'].encode())
                    stream.flush()
                    os.fsync(stream.fileno())
                info['files']['app/' + name] = entry['after']
                install.save(info)
                os.replace(staged, target)
            install.audit.change('update dashboard module', target, lambda: install.file_state(target),
                                 {'sha256': entry['after']}, publish_module)
        pending.unlink()
        stage.rmdir()
    print('Dashboard updated. Restart the window; session, choices and original restoration values are unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dashboard', action='store_true', help='Also refresh dashboard backend and audit modules; never remapper code/configuration.')
    refresh(dashboard=parser.parse_args().dashboard)

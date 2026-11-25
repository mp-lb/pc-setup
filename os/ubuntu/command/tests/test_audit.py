import copy
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit import Audit
from preferences import Appearance, DOCK, save_preferences
from profiles import DEFAULTS
from control import Install
from refresh_gui import refresh_dashboard
from test_command import FakeDesktop, FakeRuntime, SOURCE, snapshot
from test_dashboard import MemoryDconf


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audit = Audit(self.root)

    def entries(self, audit=None):
        return [json.loads(line) for line in (audit or self.audit).text().splitlines()]

    def test_every_setting_change_keeps_immediate_before_and_after(self):
        desktop = MemoryDconf()
        appearance = Appearance(self.root, desktop)
        key = DOCK + 'dock-position'
        appearance.apply({key: "'BOTTOM'"})
        appearance.apply({key: "'TOP'"})
        appearance.restore()
        history = [e for e in self.entries() if e['event'] == 'completed' and e['action'] == 'desktop setting']
        self.assertEqual([(e['before'], e['after']) for e in history],
                         [("'LEFT'", "'BOTTOM'"), ("'BOTTOM'", "'TOP'"), ("'TOP'", "'LEFT'")])

    def test_failure_is_recorded_and_original_stays_recoverable(self):
        desktop = MemoryDconf()
        key = desktop.fail = DOCK + 'dock-position'
        appearance = Appearance(self.root, desktop)
        with self.assertRaises(RuntimeError):
            appearance.apply({key: "'BOTTOM'"})
        failure = self.entries()[-1]
        self.assertEqual(failure['event'], 'failed')
        self.assertEqual(failure['before'], failure['after'])
        self.assertEqual(appearance.load()[key]['before'], "'LEFT'")

    def test_no_mutation_when_durable_intent_cannot_be_written(self):
        value = []
        with patch.object(self.audit, 'append', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.audit.change('test', 'value', lambda: list(value), [1], lambda: value.append(1))
        self.assertEqual(value, [])

    def test_external_change_preservation_is_in_history(self):
        desktop = MemoryDconf()
        appearance = Appearance(self.root, desktop)
        key = DOCK + 'dock-position'
        appearance.apply({key: "'BOTTOM'"})
        desktop.values[key] = "'RIGHT'"
        appearance.restore()
        preserved = next(e for e in self.entries() if e['event'] == 'preserved external change')
        self.assertEqual(preserved['before'], "'RIGHT'")
        self.assertEqual(preserved['after'], "'RIGHT'")

    def test_torn_or_symlinked_logs_are_not_appended_to(self):
        self.audit.path.write_text('{"schema":1')
        with self.assertRaises(RuntimeError):
            self.audit.append('test')
        self.assertEqual(self.audit.path.read_text(), '{"schema":1')
        self.audit.path.unlink()
        other = self.root / 'personal'
        other.write_text('keep')
        self.audit.path.symlink_to(other)
        with self.assertRaises(OSError):
            self.audit.append('test')
        self.assertEqual(other.read_text(), 'keep')

    def make_install(self):
        install = Install(self.root/'data', self.root/'state', FakeDesktop(), SOURCE, b'engine', FakeRuntime())
        install.install()
        return install

    def test_uninstall_export_includes_result_and_only_export_survives(self):
        install = self.make_install()
        save_preferences(install.record_dir, DEFAULTS)
        target = self.root / 'history.jsonl'
        install.uninstall(audit_export=target)
        self.assertEqual(set(snapshot(self.root)), {'history.jsonl'})
        entries = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(entries[-1]['event'], 'uninstall completed')
        self.assertTrue(any(e.get('action') == 'remove installed file' for e in entries))
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_export_never_overwrites_a_personal_file(self):
        install = self.make_install()
        target = self.root / 'personal'
        target.write_text('keep')
        before = snapshot(self.root)
        with self.assertRaises(FileExistsError):
            install.uninstall(audit_export=target)
        self.assertEqual(snapshot(self.root), before)

    def test_dashboard_update_preserves_choices_and_recovers_each_publication_failure(self):
        for failed_name in ('audit.py', 'dashboard.py', 'gui.py', 'preferences.py', 'control.py'):
            with self.subTest(file=failed_name):
                install = self.make_install()
                prefs = copy.deepcopy(DEFAULTS)
                prefs['layers']['navigation'] = False
                save_preferences(install.record_dir, prefs)
                before = (install.record_dir/'preferences.json').read_bytes()
                info = install.load()
                import hashlib
                for name in ('audit.py', 'dashboard.py', 'gui.py', 'preferences.py', 'control.py'):
                    path = install.app / name
                    if name == 'audit.py':
                        path.unlink()
                        del info['files']['app/' + name]
                    else:
                        path.write_text('# prior version\n')
                        info['files']['app/' + name] = hashlib.sha256(path.read_bytes()).hexdigest()
                install.save(info)
                replace = os.replace
                def fail(source, target):
                    if Path(target) == install.app / failed_name:
                        raise OSError('publication failed')
                    return replace(source, target)
                with patch('refresh_gui.os.replace', side_effect=fail):
                    with self.assertRaisesRegex(OSError, 'publication failed'):
                        refresh_dashboard(install)
                refresh_dashboard(install)
                self.assertEqual((install.record_dir/'preferences.json').read_bytes(), before)
                for name in ('audit.py', 'dashboard.py', 'gui.py', 'preferences.py', 'control.py'):
                    self.assertEqual((install.app/name).read_bytes(), (SOURCE/name).read_bytes())
                install.uninstall()
                self.assertEqual(snapshot(self.root), {})

    def test_dashboard_update_rejects_modified_engine_code(self):
        install = self.make_install()
        (install.app/'runtime.py').write_text('personal edit')
        before = snapshot(self.root)
        with self.assertRaisesRegex(RuntimeError, 'runtime.py'):
            refresh_dashboard(install)
        # operation.lock may be newly created, but no managed files are changed.
        after = snapshot(self.root)
        for name, value in before.items():
            self.assertEqual(after[name], value)

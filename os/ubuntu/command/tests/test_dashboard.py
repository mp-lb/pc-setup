import copy
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from profiles import DEFAULTS, LAYERS, compile_profile, validate
from preferences import Appearance, DOCK, DOCK_PRESET, BACKGROUND, read_preferences, save_preferences
from control import Install
from runtime import Runtime
from dashboard import Dashboard
from test_command import FakeDesktop, FakeRuntime, snapshot


class MemoryDconf:
    def __init__(self):
        self.values = {DOCK + 'dock-position': "'LEFT'", BACKGROUND + 'picture-uri': "'file:///original.jpg'"}
        self.fail = None

    def read(self, path):
        return self.values.get(path)

    def write(self, path, value):
        if path == self.fail:
            raise RuntimeError('Simulated write failure')
        if value is None:
            self.values.pop(path, None)
        else:
            self.values[path] = value


class ProfileTests(unittest.TestCase):
    def test_every_layer_combination_and_hardware_profile_passes_upstream_parser(self):
        binary = os.environ.get('XREMAP_TEST_BINARY')
        if not binary:
            self.skipTest('Set XREMAP_TEST_BINARY to validate generated profiles')
        prefs = copy.deepcopy(DEFAULTS)
        prefs['excluded_apps'] = ['chromium', 'org.example.Editor']
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'active.json'
            for hardware in ('pc', 'apple'):
                prefs['keyboard'] = hardware
                for flags in itertools.product((False, True), repeat=len(LAYERS)):
                    prefs['layers'] = dict(zip(LAYERS, flags))
                    path.write_text(json.dumps(compile_profile(SOURCE, prefs)))
                    result = subprocess.run([binary, '--validate-config', str(path)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, f'{hardware} {flags}: {result.stderr}')

    def test_navigation_releases_command_for_line_edges_but_keeps_it_for_document_edges(self):
        profile = compile_profile(SOURCE, DEFAULTS)
        command = next(k['remap'] for k in profile['keymap'] if k['name'] == 'Command text navigation')
        self.assertEqual(command['Left'], [{'release': 'Ctrl_R'}, 'Home', {'press': 'Ctrl_R'}])
        self.assertEqual(command['Shift-Right'], [{'release': 'Ctrl_R'}, 'Shift-End', {'press': 'Ctrl_R'}])
        self.assertEqual(command['Up'], 'Home')
        self.assertEqual(command['Shift-Down'], 'Shift-End')
        option = next(k for k in profile['keymap'] if k['name'] == 'Option word navigation')
        self.assertEqual(option['mode'], 'default')
        self.assertEqual(option['remap']['Alt_L-Shift-Right'], 'Ctrl_L-Shift-Right')

    def test_exclusions_only_disable_optional_shortcuts(self):
        prefs = copy.deepcopy(DEFAULTS)
        prefs['excluded_apps'] = ['chromium']
        compiled = compile_profile(SOURCE, prefs)
        for mapping in compiled['keymap']:
            if mapping['name'].startswith('Emergency'):
                self.assertNotIn('application', mapping)
            else:
                self.assertEqual(mapping['application']['not'], ['chromium'])
        self.assertTrue(all('not' not in m.get('application', {}) for m in compiled['modmap']))
        prefs['layers']['command'] = False
        compiled = compile_profile(SOURCE, prefs)
        self.assertNotIn('modmap', compiled)
        self.assertEqual(len(compiled['keymap']), 1)

    def test_invalid_preferences_and_regexes_are_rejected(self):
        prefs = copy.deepcopy(DEFAULTS)
        prefs['excluded_apps'] = ['/.* /']
        with self.assertRaises(ValueError):
            validate(prefs)
        prefs = copy.deepcopy(DEFAULTS)
        prefs['layers']['navigation'] = 'true'
        with self.assertRaises(ValueError):
            validate(prefs)


class RestorationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.desktop = MemoryDconf()
        self.appearance = Appearance(self.root, self.desktop)
        self.before = dict(self.desktop.values)

    def test_repeated_changes_restore_original_raw_values_and_absent_keys(self):
        self.appearance.apply({DOCK + 'dock-position': "'BOTTOM'", DOCK + 'extend-height': 'true'})
        self.appearance.apply({DOCK + 'dock-position': "'TOP'"})
        self.appearance.restore('dock')
        self.assertEqual(self.desktop.values, self.before)
        self.assertFalse(self.appearance.path.exists())

    def test_interrupted_apply_is_recoverable_and_other_groups_remain(self):
        self.desktop.fail = DOCK + 'extend-height'
        with self.assertRaisesRegex(RuntimeError, 'write failure'):
            self.appearance.apply({DOCK + 'dock-position': "'BOTTOM'", DOCK + 'extend-height': 'true'})
        self.assertTrue(self.appearance.path.exists())
        self.desktop.fail = None
        self.appearance.apply({BACKGROUND + 'picture-uri': "'file:///new.jpg'"})
        self.appearance.restore('dock')
        self.assertEqual(self.desktop.read(DOCK + 'dock-position'), "'LEFT'")
        self.assertEqual(self.desktop.read(BACKGROUND + 'picture-uri'), "'file:///new.jpg'")
        self.appearance.restore()
        self.assertEqual(self.desktop.values, self.before)

    def test_newer_external_changes_are_preserved(self):
        key = DOCK + 'dock-position'
        self.appearance.apply({key: "'BOTTOM'"})
        self.desktop.values[key] = "'RIGHT'"
        with self.assertRaisesRegex(RuntimeError, 'outside'):
            self.appearance.apply({key: "'TOP'"})
        self.assertEqual(self.appearance.restore(), [key])
        self.assertEqual(self.desktop.read(key), "'RIGHT'")

    def test_failed_restore_retains_recovery_record_for_retry(self):
        key = DOCK + 'dock-position'
        self.appearance.apply({key: "'BOTTOM'"})
        self.desktop.fail = key
        with self.assertRaises(RuntimeError):
            self.appearance.restore()
        self.assertIn(key, self.appearance.load())
        self.desktop.fail = None
        self.appearance.restore()
        self.assertEqual(self.desktop.values, self.before)

    def test_wallpapers_are_referenced_not_copied_or_deleted(self):
        image = self.root / "user's image.jpg"
        image.write_bytes(b'original user file')
        self.appearance.wallpaper(image)
        self.assertIn('%27', self.desktop.read(BACKGROUND + 'picture-uri'))
        self.appearance.restore()
        self.assertEqual(image.read_bytes(), b'original user file')
        self.assertEqual(self.desktop.values, self.before)

    def test_forged_or_symlinked_recovery_is_not_followed(self):
        self.appearance.path.write_text(json.dumps({'/unrelated/path': {'before': None, 'after': 'true'}}))
        with self.assertRaises(ValueError):
            self.appearance.restore()
        self.appearance.path.unlink()
        target = self.root / 'unrelated'
        target.write_text('{}')
        self.appearance.path.symlink_to(target)
        with self.assertRaises(RuntimeError):
            self.appearance.restore()
        self.assertEqual(target.read_text(), '{}')

    def test_real_installer_removes_preferences_and_restores_appearance(self):
        install = Install(self.root/'data', self.root/'state', FakeDesktop(), SOURCE, b'engine', FakeRuntime())
        install.install()
        save_preferences(install.record_dir, DEFAULTS)
        appearance = Appearance(install.record_dir, self.desktop)
        appearance.apply({DOCK + 'dock-position': "'BOTTOM'"})
        with patch('preferences.Dconf', return_value=self.desktop):
            install.uninstall()
        self.assertEqual(snapshot(self.root), {})
        self.assertEqual(self.desktop.values, self.before)

    def test_invalid_preferences_block_removal_without_losing_files(self):
        install = Install(self.root/'data', self.root/'state', FakeDesktop(), SOURCE, b'engine', FakeRuntime())
        install.install()
        (install.record_dir/'preferences.json').write_text('{"unexpected":true}')
        before = snapshot(self.root)
        with self.assertRaises(ValueError):
            install.uninstall()
        # operation.lock is an intentional lock created by operations, not lost data.
        after = snapshot(self.root)
        for name, content in before.items():
            if not name.endswith('/audit.jsonl'):
                self.assertEqual(after[name], content)
        self.assertIn('uninstall failed', (install.record_dir / 'audit.jsonl').read_text())

    def test_browsing_gallery_does_not_change_legacy_installation(self):
        runtime = FakeRuntime()
        runtime.state = lambda user=False: {'LoadState':'not-found', 'ActiveState':'inactive'}
        install = Install(self.root/'data', self.root/'state', FakeDesktop(), SOURCE, b'engine', runtime)
        install.install()
        # An older installation has no GUI file. Its old uninstaller would not
        # recognize mutable dashboard choices, so preview must remain read-only.
        info = install.load()
        del info['files']['app/gui.py']
        (install.app/'gui.py').unlink()
        install.save(info)
        before = snapshot(self.root)
        Dashboard(install).save_folder('/tmp/wallpapers')
        self.assertEqual(snapshot(self.root), before)

    def test_failed_restart_keeps_saved_choices_and_installation(self):
        install = Install(self.root/'data', self.root/'state', FakeDesktop(), SOURCE, b'engine', FakeRuntime())
        install.install()
        prefs = copy.deepcopy(DEFAULTS)
        prefs['layers']['navigation'] = False
        manifest = install.record.read_bytes()
        with patch('dashboard.preflight'), patch.object(install, 'start', side_effect=RuntimeError('Authentication cancelled')):
            with self.assertRaisesRegex(RuntimeError, 'Authentication cancelled'):
                Dashboard(install).apply_keyboard(prefs)
        self.assertEqual(install.record.read_bytes(), manifest)
        self.assertTrue((install.app/'control.py').exists())
        self.assertEqual(read_preferences(install.record_dir), prefs)


class RuntimeProfileTests(unittest.TestCase):
    def test_generated_session_config_is_written_without_changing_installed_templates(self):
        import shutil
        binary = os.environ.get('XREMAP_TEST_BINARY')
        if not binary:
            self.skipTest('Set XREMAP_TEST_BINARY')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = root/'app'
            app.mkdir()
            for name in ('config.json', 'pc.json', 'apple.json'):
                shutil.copyfile(SOURCE/name, app/name)
            (app/'xremap').symlink_to(binary)
            before = {name:(app/name).read_bytes() for name in ('config.json','pc.json','apple.json')}
            runtime = Runtime(app)
            runtime.directory = root/'run'
            actual_run = __import__('runtime').run
            real_subprocess_run = subprocess.run
            def run(args, **kwargs):
                if '--validate-config' in args:
                    return actual_run(args, **kwargs)
                runtime.directory.mkdir()
                (runtime.directory/'desktop.sock').touch()
                return ''
            with patch.object(runtime, 'ensure_absent'), patch.object(runtime, 'context', return_value={'locked':False}), \
                 patch.object(runtime, 'session_scope', return_value='session-2.scope'), \
                 patch.object(runtime, 'state', return_value={'ActiveState':'active'}), \
                 patch('runtime.run', side_effect=run), patch('runtime.subprocess.run') as spawn, \
                 patch('runtime.time.sleep'):
                spawn.side_effect = lambda args, **kw: real_subprocess_run(args, **kw) if '--validate-config' in args else None
                runtime.start(preferences=DEFAULTS)
            self.assertEqual(json.loads((runtime.directory/'active.json').read_text()), compile_profile(SOURCE, DEFAULTS))
            self.assertEqual(json.loads((runtime.directory/'preferences.json').read_text()), DEFAULTS)
            self.assertEqual(before, {name:(app/name).read_bytes() for name in before})

    def test_generated_config_only_lives_in_systemd_runtime_directory(self):
        runtime = Runtime(SOURCE)
        args = runtime.engine_command(False, 'session-2.scope', generated=True)
        self.assertEqual(args[-1], str(runtime.directory/'active.json'))
        self.assertNotIn(str(SOURCE/'config.json'), args)
        self.assertNotIn('--watch=config', args)

    def test_private_dconf_appearance_roundtrip(self):
        script = '''
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from preferences import Appearance, Dconf, DOCK, BACKGROUND
store=Path(sys.argv[2]); d=Dconf(); a=Appearance(store,d)
keys=[DOCK+'dock-position', DOCK+'extend-height', BACKGROUND+'picture-uri',BACKGROUND+'picture-uri-dark',BACKGROUND+'picture-options']
d.write(keys[0],"'LEFT'")
before={k:d.read(k) for k in keys}
a.apply({keys[0]:"'BOTTOM'", keys[1]:'true'})
image=store/'a wallpaper.jpg'; image.write_bytes(b'keep')
a.wallpaper(image)
a.restore()
assert {k:d.read(k) for k in keys}==before
assert image.read_bytes()==b'keep'
assert not a.path.exists()
'''
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, XDG_CONFIG_HOME=temp+'/dconf')
            env.pop('DBUS_SESSION_BUS_ADDRESS', None)
            env.pop('DCONF_PROFILE', None)
            result = subprocess.run(['dbus-run-session', '--', sys.executable, '-B', '-c', script, str(SOURCE), temp],
                                    env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

import ast
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from control import Install, Desktop, UUID, KEYS, publish
from mapping import Mapper, ALT, SUPER, CTRL, SHIFT, C, V, W, Q, TAB, INSERT, RALT
import driver


class FakeDesktop:
    def __init__(self):
        self.values = {key: {'raw': None, 'value': []} for key in KEYS}
        self.fail = False

    def read(self, key):
        return json.loads(json.dumps(self.values[key]))

    def enable(self):
        self.values['enabled-extensions'] = {'raw': repr([UUID]), 'value': [UUID]}

    def disable(self):
        pass

    def restore(self, key, before):
        if self.fail:
            raise RuntimeError('D-Bus failed')
        cleaned = [x for x in self.values[key]['value'] if x != UUID]
        self.values[key] = before if cleaned == before['value'] else {'raw': repr(cleaned), 'value': cleaned}


def snapshot(root):
    return {str(p.relative_to(root)): ('dir' if p.is_dir() else p.read_bytes())
            for p in root.rglob('*')}


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.desktop = FakeDesktop()
        self.install = Install(self.root / 'nested/data', self.root / 'nested/state', self.desktop, SOURCE)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def test_complete_filesystem_and_settings_roundtrip(self):
        keep = self.root / 'unrelated'
        keep.write_text('keep')
        before = snapshot(self.root)
        self.desktop.values['enabled-extensions'] = {'raw': "['existing']", 'value': ['existing']}
        baseline = json.loads(json.dumps(self.desktop.values))
        self.install.install()
        self.desktop.values['enabled-extensions']['value'].append(UUID)
        self.desktop.values['disabled-extensions']['value'].append(UUID)
        (self.install.app / 'run.lock').touch()
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(self.desktop.values, baseline)
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), before)

    def test_existing_paths_are_untouched(self):
        for target in self.install.roots.values():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target == self.install.launcher:
                target.write_text('unrelated')
            else:
                target.mkdir()
            before = snapshot(self.root)
            with self.assertRaises(RuntimeError):
                self.install.install()
            self.assertEqual(snapshot(self.root), before)
            if target.is_dir():
                target.rmdir()
            else:
                target.unlink()

    def test_no_adoption_of_existing_extension_setting(self):
        self.desktop.values['disabled-extensions']['value'].append(UUID)
        with self.assertRaises(RuntimeError):
            self.install.install()
        self.assertEqual(snapshot(self.root), {})

    def test_failure_during_each_publish_is_recoverable(self):
        actual_rename = publish
        for fail_at in range(1, 4):
            calls = 0
            def rename(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == fail_at:
                    raise OSError('simulated interrupted publication')
                return actual_rename(*args, **kwargs)
            before = snapshot(self.root)
            with patch('control.publish', side_effect=rename):
                with self.assertRaises(OSError):
                    self.install.install()
            self.assertTrue(self.install.record.exists())
            self.install.uninstall()
            self.assertEqual(snapshot(self.root), before)

    def test_partial_staging_file_is_removed(self):
        actual_fsync = os.fsync
        calls = 0
        def fail(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('disk full during payload write')
            return actual_fsync(fd)
        with patch('control.os.fsync', side_effect=fail):
            with self.assertRaises(OSError):
                self.install.install()
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), {})

    def test_changed_managed_file_blocks_deletion_and_retains_journal(self):
        self.install.install()
        path = self.install.app / 'mapping.py'
        original = path.read_bytes()
        path.write_text('custom code')
        with self.assertRaisesRegex(RuntimeError, 'Modified file'):
            self.install.uninstall()
        self.assertEqual(path.read_text(), 'custom code')
        self.assertTrue(self.install.record.exists())
        path.write_bytes(original)
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), {})

    def test_unexpected_runtime_file_is_preserved(self):
        self.install.install()
        extra = self.install.app / 'notes.txt'
        extra.write_text('keep my notes')
        with self.assertRaisesRegex(RuntimeError, 'Unexpected local'):
            self.install.uninstall()
        self.assertEqual(extra.read_text(), 'keep my notes')
        extra.unlink()
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), {})

    def test_desktop_failure_leaves_files_and_retryable_journal(self):
        self.install.install()
        self.desktop.fail = True
        with self.assertRaises(RuntimeError):
            self.install.uninstall()
        self.assertTrue(self.install.record.exists())
        self.assertTrue(self.install.app.exists())
        self.desktop.fail = False
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), {})

    def test_unrelated_extension_changes_are_preserved(self):
        self.install.install()
        self.desktop.values['enabled-extensions'] = {'raw': repr([UUID, 'new']), 'value': [UUID, 'new']}
        self.install.uninstall()
        self.assertEqual(self.desktop.values['enabled-extensions']['value'], ['new'])

    def test_replaced_root_symlink_is_not_followed(self):
        self.install.install()
        original = self.root / 'moved-app'
        self.install.app.rename(original)
        external = self.root / 'external'
        external.mkdir()
        self.install.app.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'Replaced'):
            self.install.uninstall()
        self.assertEqual(list(external.iterdir()), [])
        self.install.app.unlink()
        original.rename(self.install.app)
        self.install.uninstall()

    def test_forged_manifest_path_is_rejected(self):
        self.install.install()
        data = self.install.load()
        data['files']['app/../../../important'] = '0' * 64
        self.install.save(data)
        with self.assertRaises(ValueError):
            self.install.uninstall()
        self.assertTrue(self.install.app.exists())

    def test_busy_session_prevents_deletion(self):
        self.install.install()
        with (self.install.app / 'run.lock').open('a') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.install.uninstall()
        self.assertTrue(self.install.record.exists())
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), {})

    def test_partial_removal_is_retryable(self):
        self.install.install()
        (self.install.app / 'mapping.py').unlink()
        (self.install.ext / 'metadata.json').unlink()
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), {})

    def test_python_bytecode_not_in_installed_payload(self):
        self.install.install()
        self.assertEqual({p.name for p in self.install.app.iterdir()}, {'mapping.py', 'driver.py', 'control.py', 'run.lock'})
        self.install.uninstall()

    def test_failed_initial_manifest_write_leaves_nothing(self):
        with patch.object(self.install, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.install.install()
        self.assertEqual(snapshot(self.root), {})

    def test_atomic_publish_never_replaces_an_existing_file(self):
        source = self.root / 'source'
        target = self.root / 'target'
        source.write_text('ours')
        target.write_text('theirs')
        with self.assertRaises(FileExistsError):
            publish(source, target)
        self.assertEqual(target.read_text(), 'theirs')
        self.assertEqual(source.read_text(), 'ours')

    def test_removal_failure_keeps_journal_and_can_be_retried(self):
        self.install.install()
        original = Path.unlink
        def unlink(path, *args, **kwargs):
            if path == self.install.launcher:
                raise PermissionError('simulated removal failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', unlink):
            with self.assertRaises(PermissionError):
                self.install.uninstall()
        self.assertTrue(self.install.record.exists())
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), {})

    def test_real_process_stop_and_kernel_lock_release_on_exit(self):
        import select
        self.install.install()
        code = """import fcntl,sys,time
from pathlib import Path
lock=(Path(sys.argv[1]).parent/'run.lock').open('r+')
fcntl.flock(lock,fcntl.LOCK_EX)
print('ready',flush=True)
time.sleep(60)
"""
        with subprocess.Popen([sys.executable, '-B', '-c', code, str(self.install.app / 'driver.py')],
                              stdout=subprocess.PIPE, text=True) as child:
            self.assertTrue(select.select([child.stdout], [], [], 5)[0])
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            self.assertIn(child.pid, list(self.install.sessions()))
            self.install.uninstall()
            self.assertEqual(child.wait(timeout=5), -15)
        self.assertEqual(snapshot(self.root), {})



class MappingTests(unittest.TestCase):
    def make(self, terminal=False):
        self.quits = 0
        def quit_app():
            self.quits += 1
        return Mapper(lambda: {'wm_class': 'gnome-terminal-server' if terminal else 'firefox'}, quit_app)

    def key(self, mapper, code, value=1, device=1):
        return mapper.event(device, code, value)

    def test_terminal_command_copy_keeps_control_interrupt_separate(self):
        m = self.make(True)
        self.assertEqual(self.key(m, ALT), [])
        self.assertEqual(self.key(m, C), [(CTRL, 1), (SHIFT, 1), (C, 1)])
        self.key(m, C, 0)
        self.assertEqual(self.key(m, ALT, 0), [(CTRL, 0), (SHIFT, 0)])
        self.assertEqual(self.key(m, CTRL), [(CTRL, 1)])
        self.assertEqual(self.key(m, C), [(C, 1)])

    def test_command_tab_keeps_super_until_command_release(self):
        m = self.make()
        self.key(m, ALT)
        self.assertEqual(self.key(m, TAB), [(SUPER, 1), (TAB, 1)])
        self.assertEqual(self.key(m, TAB, 0), [(TAB, 0)])
        self.assertEqual(self.key(m, ALT, 0), [(SUPER, 0)])

    def test_option_swap_and_altgr_passthrough(self):
        m = self.make()
        self.assertEqual(self.key(m, SUPER), [(ALT, 1)])
        self.assertEqual(self.key(m, SUPER, 0), [(ALT, 0)])
        self.assertEqual(self.key(m, RALT), [(RALT, 1)])
        self.assertEqual(self.key(m, RALT, 0), [(RALT, 0)])

    def test_gui_copy_uses_insert_not_sigint(self):
        m = self.make()
        self.key(m, ALT)
        self.assertEqual(self.key(m, C), [(CTRL, 1), (INSERT, 1)])
        self.assertEqual(self.key(m, C, 0), [(INSERT, 0)])
        self.key(m, ALT, 0)
        self.key(m, ALT)
        self.assertEqual(self.key(m, V), [(SHIFT, 1), (INSERT, 1)])

    def test_key_release_uses_original_mapping_after_context_change(self):
        m = self.make()
        self.key(m, ALT)
        self.key(m, C)
        m.context = lambda: {'wm_class': 'gnome-terminal-server'}
        self.assertEqual(self.key(m, C, 2), [(INSERT, 2)])
        self.assertEqual(self.key(m, C, 0), [(INSERT, 0)])

    def test_shutdown_releases_all_output_keys(self):
        m = self.make(True)
        self.key(m, ALT)
        self.key(m, C)
        self.assertEqual(set(m.release_all()), {(C, 0), (CTRL, 0), (SHIFT, 0)})
        self.assertEqual(m.release_all(), [])

    def test_quit_requests_app_quit_once_not_a_key_or_repeat(self):
        m = self.make()
        self.key(m, ALT)
        self.assertEqual(self.key(m, Q), [])
        self.assertEqual(self.key(m, Q, 2), [])
        self.assertEqual(self.key(m, Q, 0), [])
        self.assertEqual(self.quits, 1)

    def test_terminal_tab_and_window_close(self):
        m = self.make(True)
        self.key(m, ALT)
        self.assertEqual(self.key(m, W)[-1], (W, 1))
        self.key(m, W, 0)
        self.key(m, SHIFT)
        self.assertEqual(self.key(m, W)[-1], (Q, 1))

    def test_multiple_keyboards_do_not_release_other_keyboard_modifier(self):
        m = self.make()
        self.key(m, CTRL, device=1)
        self.assertEqual(self.key(m, CTRL, device=2), [])
        self.assertEqual(self.key(m, CTRL, 0, device=1), [])
        self.assertEqual(self.key(m, CTRL, 0, device=2), [(CTRL, 0)])

    def test_apple_command_position(self):
        m = Mapper(lambda: {'wm_class': 'firefox'}, lambda: None, apple=True)
        self.assertEqual(self.key(m, SUPER), [])
        self.assertEqual(self.key(m, C)[-1], (INSERT, 1))

    def test_overlapping_chord_cannot_turn_terminal_copy_repeat_into_interrupt(self):
        m = self.make(True)
        self.key(m, ALT)
        self.key(m, C)
        # A second chord must not drop the synthetic Shift needed by held C.
        events = self.key(m, 30)  # Command+A before C has been released
        self.assertNotIn((SHIFT, 0), events)
        self.assertIn(SHIFT, m.output_mods)
        self.assertEqual(self.key(m, C, 2), [(C, 2)])
        self.key(m, ALT, 0)
        self.assertEqual(self.key(m, C, 2), [])

    def test_two_keyboards_holding_same_key_produce_one_press_and_release(self):
        m = self.make()
        self.assertEqual(self.key(m, C, device=1), [(C, 1)])
        self.assertEqual(self.key(m, C, device=2), [])
        self.assertEqual(self.key(m, C, 0, device=1), [])
        self.assertEqual(self.key(m, C, 0, device=2), [(C, 0)])


class DriverTests(unittest.TestCase):
    def test_privilege_drop_before_mapping_loop_and_fds_closed_on_crash(self):
        order = []
        with patch.object(sys, 'argv', ['driver.py']), patch.dict(os.environ, SUDO_UID='1000'), \
             patch('driver.os.geteuid', return_value=0), \
             patch('driver.os.open', return_value=12), patch('driver.fcntl.flock'), \
             patch('driver.open_keyboards', side_effect=lambda: order.append('open') or [(10, 'path', 'name', bytes(96))]), \
             patch('driver.create_output', side_effect=lambda d: order.append('output') or 11), \
             patch('driver.drop_privileges', side_effect=lambda uid: order.append('drop')), \
             patch('driver.run_session', side_effect=lambda *a: (_ for _ in ()).throw(RuntimeError('crash'))), \
             patch('driver.os.close', side_effect=lambda fd: order.append(('close', fd))):
            with self.assertRaises(RuntimeError):
                driver.main()
        self.assertEqual(order, ['open', 'output', 'drop', ('close', 11), ('close', 10), ('close', 12)])

    def test_output_creation_failure_closes_open_keyboards(self):
        with patch.object(sys, 'argv', ['driver.py']), patch.dict(os.environ, SUDO_UID='1000'), \
             patch('driver.os.geteuid', return_value=0), \
             patch('driver.os.open', return_value=12), patch('driver.fcntl.flock'), \
             patch('driver.open_keyboards', return_value=[(10, 'p', 'n', b'')]), \
             patch('driver.create_output', side_effect=OSError('denied')), \
             patch('driver.os.close') as close:
            with self.assertRaises(OSError):
                driver.main()
        self.assertEqual([x.args for x in close.call_args_list], [(10,), (12,)])

    def test_kernel_ioctl_constants_match_local_headers(self):
        if not shutil.which('cc'):
            self.skipTest('C compiler unavailable')
        code = '''#include <stdio.h>
#include <linux/input.h>
#include <linux/uinput.h>
int main(void) {printf("%lu %lu %lu %lu %lu %zu", (unsigned long)EVIOCGRAB,
(unsigned long)UI_DEV_CREATE,(unsigned long)UI_DEV_SETUP,(unsigned long)UI_SET_EVBIT,
(unsigned long)UI_SET_KEYBIT,sizeof(struct input_event));}'''
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / 'abi'
            subprocess.run(['cc', '-x', 'c', '-', '-o', str(binary)], input=code, text=True, check=True)
            values = list(map(int, subprocess.check_output([str(binary)], text=True).split()))
        self.assertEqual(values, [driver.GRAB, driver.CREATE, driver.SETUP, driver.SET_EVBIT, driver.SET_KEYBIT, driver.EVENT.size])


class RealDesktopTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('dbus-run-session') and shutil.which('dconf'), 'needs D-Bus/dconf')
    def test_real_private_dconf_install_enable_uninstall_exact_roundtrip(self):
        script = '''
import os,sys,json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from control import Install, Desktop, UUID, KEYS, publish, command
root=Path(sys.argv[2])
desktop=Desktop()
before={k:desktop.read(k) for k in KEYS}
install=Install(root/'data',root/'state',desktop,Path(sys.argv[1]))
install.install()
command(['gsettings','set','org.gnome.shell','enabled-extensions',repr(['another-extension',UUID])])
command(['gsettings','set','org.gnome.shell','disabled-extensions',repr([UUID])])
install.uninstall()
assert desktop.read('enabled-extensions')['value'] == ['another-extension']
assert desktop.read('disabled-extensions') == before['disabled-extensions']
# Second cycle with existing explicit settings restores exact raw values.
before={k:desktop.read(k) for k in KEYS}
install.install()
command(['gsettings','set','org.gnome.shell','enabled-extensions',repr(['another-extension',UUID])])
install.uninstall()
assert {k:desktop.read(k) for k in KEYS} == before
assert not (root/'data').exists() and not (root/'state').exists()
'''
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = dict(os.environ, XDG_CONFIG_HOME=str(root / 'private-dconf'))
            env.pop('DBUS_SESSION_BUS_ADDRESS', None)
            env.pop('DCONF_PROFILE', None)
            result = subprocess.run(['dbus-run-session', '--', sys.executable, '-B', '-c', script,
                                     str(SOURCE), str(root)], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ExtensionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('gjs') and shutil.which('dbus-run-session'), 'needs GJS and D-Bus')
    def test_context_quit_lock_and_export_lifecycle_in_gjs(self):
        source = (SOURCE / 'extension/extension.js').read_text()
        source = source.replace("import Shell from 'gi://Shell';", """
let quitCount = 0;
const app = {get_id: () => 'org.gnome.Terminal.desktop', request_quit: () => {quitCount++; return true;}};
const Shell = {WindowTracker: {get_default: () => ({get_window_app: () => app})}};
const global = {display: {focus_window: {get_wm_class: () => 'gnome-terminal-server'}}};
""")
        source = source.replace("import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';", 'class Extension {}')
        source = source.replace("import * as Main from 'resource:///org/gnome/shell/ui/main.js';",
                                'const Main = {sessionMode: {isLocked: false, isGreeter: false}};')
        source += """
const extension = new UbuntuCommand();
extension.enable();
let context = JSON.parse(extension.Context());
if (context.app_id !== 'org.gnome.Terminal' || context.wm_class !== 'gnome-terminal-server') throw Error('context');
if (!extension.Quit() || quitCount !== 1) throw Error('quit');
Main.sessionMode.isLocked = true;
context = JSON.parse(extension.Context());
if (!context.locked || context.app_id !== '' || extension.Quit() || quitCount !== 1) throw Error('lock');
extension.disable();
extension.disable();
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'extension-test.mjs'
            path.write_text(source)
            result = subprocess.run(['dbus-run-session', '--', 'gjs', '-m', str(path)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()

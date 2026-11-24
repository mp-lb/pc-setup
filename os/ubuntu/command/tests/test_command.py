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
from control import Install, Desktop, UUID, KEYS, publish, APP_FILES, engine_payload
from runtime import Runtime
from bridge import respond


class FakeRuntime:
    def ensure_absent(self):
        pass
    def stop(self):
        pass


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
        self.install = Install(self.root / 'nested/data', self.root / 'nested/state', self.desktop, SOURCE, engine=b"fake-engine", runtime=FakeRuntime())
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
        path = self.install.app / 'config.json'
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
        (self.install.app / 'config.json').unlink()
        (self.install.ext / 'metadata.json').unlink()
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), {})

    def test_python_bytecode_not_in_installed_payload(self):
        self.install.install()
        # Exercise runtime import in a fresh Python process without -B, as the
        # old desktop launcher did. The controller must suppress cache writes.
        env = dict(os.environ)
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        env.pop('PYTHONPYCACHEPREFIX', None)
        subprocess.run([sys.executable, '-c',
                        'import runpy,sys; sys.path.insert(0,sys.argv[1]); '
                        'runpy.run_path(sys.argv[1]+"/control.py")["Install"]()',
                        str(self.install.app)], env=env, check=True, timeout=10)
        entries = [line for line in self.install.launcher.read_text().splitlines() if line.startswith('Exec=')]
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(line.startswith('Exec=/usr/bin/python3 -B ') for line in entries))
        self.assertEqual({p.name for p in self.install.app.iterdir()}, set(APP_FILES) | {'run.lock'})
        self.install.uninstall()
        self.assertEqual(snapshot(self.root), {})

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



class RealDesktopTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('dbus-run-session') and shutil.which('dconf'), 'needs D-Bus/dconf')
    def test_real_private_dconf_install_enable_uninstall_exact_roundtrip(self):
        script = '''
import os,sys,json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from control import Install, Desktop, UUID, KEYS, publish, APP_FILES, engine_payload, command
root=Path(sys.argv[2])
desktop=Desktop()
before={k:desktop.read(k) for k in KEYS}
# This test isolates real dconf, not the host's running keyboard service.
class IsolatedRuntime:
    def ensure_absent(self): pass
    def stop(self): pass
install=Install(root/'data',root/'state',desktop,Path(sys.argv[1]),engine=b'fake-engine',runtime=IsolatedRuntime())
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

class XremapTests(unittest.TestCase):
    def test_bad_archive_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'release.zip'
            path.write_bytes(b'untrusted download')
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                engine_payload(path)

    def test_configuration_with_upstream_parser(self):
        binary = os.environ.get('XREMAP_TEST_BINARY')
        if not binary:
            self.skipTest('Set XREMAP_TEST_BINARY to a checksum-verified upstream binary')
        for keyboard in ('pc.json', 'apple.json'):
            result = subprocess.run([binary, '--validate-config', str(SOURCE/'config.json'), str(SOURCE/keyboard)],
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_terminal_copy_and_interrupt_are_separate(self):
        config = json.loads((SOURCE/'config.json').read_text())
        terminal = next(item for item in config['keymap'] if item['name'].startswith('Terminal'))
        self.assertEqual(terminal['mode'], 'command')
        self.assertEqual(terminal['remap']['c'], 'Shift-c')
        self.assertEqual(terminal['remap']['v'], 'Shift-v')
        self.assertFalse(any('Ctrl-c' in item['remap'] for item in config['keymap']))
        for profile, command_key in (('pc', 'Alt_L'), ('apple', 'Super_L')):
            remap = json.loads((SOURCE/(profile+'.json')).read_text())['modmap'][0]['remap']
            command = remap[command_key]
            self.assertIn({'press': 'Ctrl_R'}, command['press'])
            self.assertIn({'release': 'Ctrl_R'}, command['release'])
            self.assertIn({'release': 'Super_L'}, command['release'])
            self.assertIn({'set_mode': 'default'}, command['release'])
            self.assertEqual(remap['Ctrl_R'], 'Ctrl_L')
            self.assertNotIn('Ctrl_L', remap)
            self.assertNotIn('Alt_R', remap)
        # App switching must hold Super across repeated Tabs, not emit a tap
        # that selects immediately. Command release above is the cleanup.
        switcher = next(item for item in config['keymap'] if item.get('mode') == 'command' and 'Tab' in item['remap'])
        actions = switcher['remap']['Tab']
        self.assertLess(actions.index({'release': 'Ctrl_R'}), actions.index({'press': 'Super_L'}))
        self.assertNotIn({'release': 'Super_L'}, actions)

    def test_lock_chord_is_distinct_from_quit(self):
        keymaps = json.loads((SOURCE/'config.json').read_text())['keymap']
        lock = next(item for item in keymaps if 'Ctrl-q' in item['remap'])
        quit_app = next(item for item in keymaps if 'q' in item['remap'])
        self.assertEqual(lock['mode'], 'command')
        self.assertTrue(lock['exact_match'])
        self.assertNotIn('application', lock)  # Also works with no focused window.
        self.assertLess(keymaps.index(lock), keymaps.index(quit_app))
        self.assertEqual(lock['remap']['Ctrl-q'], {'launch': ['ubuntu-command-lock']})
        self.assertEqual(quit_app['remap']['q'], {'launch': ['ubuntu-command-quit']})

    def test_bridge_never_executes_arbitrary_launches_and_hides_locked_context(self):
        calls = []
        def context(method='Context'):
            calls.append(method)
            return {'locked': False, 'wm_class': 'kitty'}
        self.assertEqual(respond('ActiveWindow', context), {'wm_class': 'kitty', 'title': ''})
        self.assertEqual(respond({'Run': ['ubuntu-command-quit']}, context), 'Ok')
        self.assertEqual(calls.count('Quit'), 1)
        self.assertIn('Error', respond({'Run': ['/bin/sh', '-c', 'anything']}, context))
        self.assertEqual(calls.count('Quit'), 1)
        locked = lambda *args: {'locked': True, 'wm_class': 'private'}
        self.assertEqual(respond('ActiveWindow', locked)['wm_class'], '')
        self.assertIn('Error', respond({'Run': ['ubuntu-command-quit']}, locked))

    def test_lock_uses_fixed_user_session_call_even_without_extension(self):
        def unavailable(*args):
            raise RuntimeError('GNOME extension unavailable')
        with patch('bridge.run', return_value='()') as run:
            self.assertEqual(respond({'Run': ['ubuntu-command-lock']}, unavailable), 'Ok')
        run.assert_called_once_with([
            '/usr/bin/busctl', '--user', '--expect-reply=no', 'call',
            'org.gnome.ScreenSaver', '/org/gnome/ScreenSaver', 'org.gnome.ScreenSaver', 'Lock'])
        with patch('bridge.run', side_effect=RuntimeError('D-Bus failed')):
            with self.assertRaisesRegex(RuntimeError, 'D-Bus failed'):
                respond({'Run': ['ubuntu-command-lock']}, unavailable)

    def test_system_service_is_transient_sandboxed_and_tied_to_login(self):
        runtime = Runtime(Path('/tmp/app with spaces'))
        args = runtime.engine_command(False, 'session-2.scope')
        self.assertIn('--collect', args)
        self.assertIn('--property=BindsTo=session-2.scope', args)
        self.assertIn('--property=ProtectHome=tmpfs', args)
        self.assertIn('--property=RestrictAddressFamilies=AF_UNIX', args)
        self.assertIn('--desktop=socket', args)  # Launches delegate to the user's restricted bridge.
        self.assertIn('--property=BindReadOnlyPaths="/tmp/app with spaces" "' + str(runtime.directory) + '"', args)
        self.assertNotIn('--user', args)

    def test_unrelated_service_is_never_stopped(self):
        runtime = Runtime(Path('/tmp/app'))
        with patch('runtime.run', return_value='LoadState=loaded\nDescription=Someone else\nTransient=yes\nActiveState=active'), \
             patch('runtime.subprocess.run') as execute:
            with self.assertRaisesRegex(RuntimeError, 'unrelated'):
                runtime.stop()
            execute.assert_not_called()

    def test_denied_stop_preserves_installed_files_and_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = FakeRuntime()
            install = Install(root/'data', root/'state', FakeDesktop(), SOURCE, b'engine', runtime)
            install.install()
            before = {name:path.read_bytes() for name in install.load()['files'] for path in [install.path_for(name)]}
            with patch.object(runtime, 'stop', side_effect=PermissionError('authentication cancelled')):
                with self.assertRaises(PermissionError):
                    install.uninstall()
            self.assertTrue(install.record.exists())
            self.assertEqual(before, {name:install.path_for(name).read_bytes() for name in before})
            install.uninstall()

    def test_rejected_start_cleans_user_bridge(self):
        runtime = Runtime(Path('/tmp/app'))
        with patch.object(runtime, 'ensure_absent'), \
             patch.object(runtime, 'context', return_value={'locked':False}), \
             patch.object(runtime, 'session_scope', return_value='session-2.scope'), \
             patch('runtime.run', return_value=''), patch('runtime.Path.exists', return_value=True), \
             patch('runtime.subprocess.run', side_effect=subprocess.CalledProcessError(126, ['pkexec'])), \
             patch.object(runtime, 'stop') as stop:
            with self.assertRaises(subprocess.CalledProcessError):
                runtime.start()
            stop.assert_called_once()

    def test_failed_engine_start_stops_both_services(self):
        runtime = Runtime(Path('/tmp/app'))
        with patch.object(runtime, 'ensure_absent'), \
             patch.object(runtime, 'context', return_value={'locked':False}), \
             patch.object(runtime, 'session_scope', return_value='session-2.scope'), \
             patch('runtime.run', return_value=''), patch('runtime.Path.exists', return_value=True), \
             patch('runtime.subprocess.run'), patch('runtime.time.sleep'), \
             patch.object(runtime, 'state', return_value={'ActiveState':'failed'}), \
             patch.object(runtime, 'stop') as stop:
            with self.assertRaisesRegex(RuntimeError, 'exited'):
                runtime.start()
            stop.assert_called_once()

    def test_real_socket_bridge_and_cleanup(self):
        import select
        import socket
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'run.lock').touch()
            script='''import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import bridge
class LocalRuntime:
    app=Path(sys.argv[2])
    directory=app
    def __init__(self,*a): pass
    def state(self): return {'LoadState':'loaded'}
bridge.Runtime=LocalRuntime
original=bridge.respond
bridge.respond=lambda request:original(request,lambda *a:{'locked':False,'wm_class':'kitty'},lambda:(LocalRuntime.app/'locked').touch())
bridge.main()
'''
            process = subprocess.Popen([sys.executable,'-B','-c',script,str(SOURCE),str(root)], stderr=subprocess.PIPE)
            try:
                import time
                path=root/'desktop.sock'
                for _ in range(50):
                    if path.exists(): break
                    time.sleep(.05)
                self.assertTrue(path.exists())
                # A client that stalls must not kill the bridge.
                with socket.socket(socket.AF_UNIX) as client:
                    client.connect(str(path)); time.sleep(.7)
                for request in ['ActiveWindow', {'Run':['ubuntu-command-lock']}, {'Run':['/bin/sh']}]:
                    with socket.socket(socket.AF_UNIX) as client:
                        client.settimeout(3); client.connect(str(path))
                        client.sendall(json.dumps(request).encode()+b'\n')
                        response=json.loads(client.recv(4096))
                    if request=='ActiveWindow': self.assertEqual(response['wm_class'],'kitty')
                    elif request=={'Run':['ubuntu-command-lock']}:
                        self.assertEqual(response,'Ok')
                        self.assertTrue((root/'locked').exists())
                    else: self.assertIn('Error',response)
                with (root/'run.lock').open() as lock:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:
                process.terminate()
                _,err=process.communicate(timeout=5)
            self.assertEqual(process.returncode,0,err)
            self.assertFalse(path.exists())
            with (root/'run.lock').open() as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)

class ServiceLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('XREMAP_TEST_SYSTEMD') == '1', 'opt in to transient user-service test')
    def test_real_user_service_stop_removes_unit_and_runtime_directory(self):
        import uuid
        token = 'ubuntu-command-test-' + uuid.uuid4().hex
        runtime = Runtime(Path('/tmp') / token)
        runtime.unit = token + '.service'
        runtime.bridge_unit = token + '.service'
        runtime.directory = Path('/run/user') / str(os.getuid()) / token
        runtime.ensure_absent()
        try:
            subprocess.run(['systemd-run','--user','--quiet','--collect','--service-type=exec',
                            '--unit='+runtime.bridge_unit, '--description='+runtime.description,
                            '--property=RuntimeDirectory='+token,'--property=RuntimeDirectoryMode=0700',
                            '/usr/bin/sleep','60'],check=True,capture_output=True)
            self.assertTrue(runtime.directory.is_dir())
            self.assertEqual(runtime.state(True)['ActiveState'],'active')
            runtime.stop()
            self.assertFalse(runtime.directory.exists())
            self.assertEqual(runtime.state(True)['LoadState'],'not-found')
        finally:
            subprocess.run(['systemctl','--user','stop',runtime.bridge_unit],capture_output=True)


class QuitRepeatTests(unittest.TestCase):
    def test_repeated_quit_requests_do_not_follow_focus_to_other_apps(self):
        from bridge import QuitGuard
        guard=QuitGuard()
        self.assertTrue(guard.allow(0))
        for moment in (.5,.55,.6,1,1.5,2):
            self.assertFalse(guard.allow(moment))
        self.assertTrue(guard.allow(3.1))


if __name__ == '__main__':
    unittest.main()

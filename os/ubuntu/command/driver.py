#!/usr/bin/python3
"""Session-only evdev/uinput driver for 64-bit Ubuntu; standard library only.

Open device handles as administrator, then permanently drop privileges before
reading keys, querying GNOME, or loading mapping code. Never alter device ACLs,
groups, udev rules, system files, or package state. Closing FDs releases grabs
and destroys the virtual keyboard, including on SIGKILL/process crashes.
"""
import argparse
import ast
import ctypes
import fcntl
import glob
import json
import os
from pathlib import Path
import pwd
import selectors
import signal
import stat
import struct
import subprocess
import sys
import time

EVENT = struct.Struct('llHHi')
EV_KEY, EV_REL, EV_ABS = 1, 2, 3
GRAB = 0x40044590
CREATE = 0x5501
SETUP = 0x405c5503
SET_EVBIT, SET_KEYBIT = 0x40045564, 0x40045565
NAME = b'Ubuntu Command (session keyboard)'


def read_ioctl(fd, number, size):
    data = bytearray(size)
    fcntl.ioctl(fd, (2 << 30) | (size << 16) | (ord('E') << 8) | number, data)
    return data


def bit(data, code):
    return bool(data[code // 8] & (1 << (code % 8)))


def open_char(path, flags):
    fd = os.open(path, flags | os.O_CLOEXEC | os.O_NOFOLLOW)
    if not stat.S_ISCHR(os.fstat(fd).st_mode):
        os.close(fd)
        raise RuntimeError('Not a character device: ' + path)
    return fd


def open_keyboards():
    devices = []
    try:
        for path in sorted(glob.glob('/dev/input/event*')):
            fd = open_char(path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                types = read_ioctl(fd, 0x20, 8)
                keys = read_ioctl(fd, 0x21, 96)
                name = bytes(read_ioctl(fd, 0x06, 256)).split(b'\0')[0]
                if (name != NAME and bit(types, EV_KEY) and not bit(types, EV_REL)
                        and not bit(types, EV_ABS) and all(bit(keys, k) for k in (30, 44, 28, 57))):
                    devices.append((fd, path, name.decode(errors='replace'), keys))
                    fd = None
            finally:
                if fd is not None:
                    os.close(fd)
        if not devices:
            raise RuntimeError('No supported keyboard found (combined mouse/touchpad devices are excluded).')
        return devices
    except BaseException:
        for fd, *_ in devices:
            os.close(fd)
        raise


def create_output(devices):
    fd = open_char('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
    try:
        fcntl.ioctl(fd, SET_EVBIT, EV_KEY)
        for code in range(768):
            if code in (29, 42, 56, 97, 100, 110, 125, 126) or any(bit(d[3], code) for d in devices):
                fcntl.ioctl(fd, SET_KEYBIT, code)
        # struct input_id + name[80] + ff_effects_max; from linux/uinput.h.
        fcntl.ioctl(fd, SETUP, struct.pack('HHHH80sI', 0x03, 0x1, 0x1, 1, NAME, 0))
        fcntl.ioctl(fd, CREATE)
        return fd
    except BaseException:
        os.close(fd)
        raise


def drop_privileges(uid):
    user = pwd.getpwuid(uid)
    os.initgroups(user.pw_name, user.pw_gid)
    os.setgid(user.pw_gid)
    os.setuid(uid)
    # No later exec may regain privileges (e.g. through a setuid binary).
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), 'prctl failed')
    if os.getuid() == 0 or os.geteuid() == 0:
        raise RuntimeError('Privilege drop failed')
    os.environ.clear()
    os.environ.update(PATH='/usr/bin:/bin', HOME=user.pw_dir, USER=user.pw_name,
                      XDG_RUNTIME_DIR=f'/run/user/{uid}',
                      DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{uid}/bus')


def dbus_call(method):
    result = subprocess.run([
        '/usr/bin/gdbus', 'call', '--session', '--dest', 'org.gnome.Shell',
        '--object-path', '/dev/mplb/UbuntuCommand', '--method', 'dev.mplb.UbuntuCommand.' + method,
    ], capture_output=True, text=True, check=True, timeout=1)
    if method == 'Context':
        data = json.loads(ast.literal_eval(result.stdout.strip())[0])
        if data.get('locked'):
            raise RuntimeError('Desktop is locked or focused application is unavailable; stopping.')
        return data
    if result.stdout.strip() != '(true,)':
        raise RuntimeError('GNOME could not request application quit')


def emit(fd, events):
    for code, value in events:
        payload = EVENT.pack(0, 0, EV_KEY, code, value) + EVENT.pack(0, 0, 0, 0, 0)
        if os.write(fd, payload) != len(payload):
            raise OSError('Short write to virtual keyboard')


def idle_grab(devices):
    deadline = time.monotonic() + 10
    while True:
        if time.monotonic() > deadline:
            raise RuntimeError('Release all keyboard keys and try again.')
        if any(any(read_ioctl(fd, 0x18, 96)) for fd, *_ in devices):
            time.sleep(0.05)
            continue
        acquired = []
        try:
            for fd, *_ in devices:
                fcntl.ioctl(fd, GRAB, 1)
                acquired.append(fd)
            if not any(any(read_ioctl(fd, 0x18, 96)) for fd, *_ in devices):
                for fd in acquired:
                    try:
                        while os.read(fd, EVENT.size * 64):
                            pass
                    except BlockingIOError:
                        pass
                return
        except BaseException:
            for fd in acquired:
                fcntl.ioctl(fd, GRAB, 0)
            raise
        for fd in acquired:
            fcntl.ioctl(fd, GRAB, 0)
        time.sleep(0.05)


def run_session(devices, output, app, apple):
    # Imports of user-owned Python code happen only after permanently dropping root.
    sys.path.insert(0, str(app))
    from mapping import Mapper, CTRL, RCTRL, ALT, RALT, ESC
    mapper = Mapper(lambda: dbus_call('Context'), lambda: dbus_call('Quit'), apple)
    dbus_call('Context')  # Fail before grabbing a keyboard if the extension isn't ready.
    selector = selectors.DefaultSelector()
    running = True
    def stop(*_):
        nonlocal running
        running = False
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    try:
        time.sleep(1)  # Let the compositor discover the virtual keyboard.
        idle_grab(devices)
        for fd, *_ in devices:
            selector.register(fd, selectors.EVENT_READ)
        print('Ubuntu Command is active. Physical Ctrl+Alt+Esc stops it.', flush=True)
        last_check = time.monotonic()
        while running:
            for key, _ in selector.select(timeout=0.25):
                data = os.read(key.fd, EVENT.size * 64)
                if not data or len(data) % EVENT.size:
                    raise RuntimeError('Keyboard disconnected or invalid event stream; stopping.')
                for _, _, kind, code, value in EVENT.iter_unpack(data):
                    if kind == 0 and code == 3:  # SYN_DROPPED: never guess lost key state
                        raise RuntimeError('Keyboard event overflow; stopping safely.')
                    if kind != EV_KEY:
                        continue
                    held = mapper._physical()
                    if value == 1 and code == ESC and held & {CTRL, RCTRL} and held & {ALT, RALT}:
                        running = False
                        break
                    emit(output, mapper.event(key.fd, code, value))
            if time.monotonic() - last_check > 0.5:
                # Stop even without keypresses when the shell locks/disables the extension.
                dbus_call('Context')
                last_check = time.monotonic()
    finally:
        try:
            emit(output, mapper.release_all())
        finally:
            for fd, *_ in devices:
                try:
                    fcntl.ioctl(fd, GRAB, 0)
                except OSError:
                    pass
            selector.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apple', action='store_true')
    args = parser.parse_args()
    uid = int(os.environ.get('SUDO_UID', '0'))
    if os.geteuid() != 0 or uid <= 0 or EVENT.size != 24:
        raise RuntimeError('Start using the control.py start command on 64-bit Ubuntu.')
    app = Path(__file__).resolve().parent
    devices, output = [], None
    lock_fd = os.open(app / 'run.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        devices = open_keyboards()
        output = create_output(devices)
        drop_privileges(uid)
        run_session(devices, output, app, args.apple)
    finally:
        if output is not None:
            os.close(output)
        for fd, *_ in devices:
            os.close(fd)
        os.close(lock_fd)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Ubuntu Command stopped: {exc}', file=sys.stderr)
        sys.exit(1)

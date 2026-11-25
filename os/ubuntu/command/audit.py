"""Durable configuration history, separate from the restoration baseline.

Intent is fsynced before a mutation. A missing result means interrupted/unknown,
never success. This is a local audit trail, not a tamper-proof security log.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import stat
import uuid

NAME = 'audit.jsonl'


class Audit:
    def __init__(self, directory):
        self.path = Path(directory) / NAME

    def text(self):
        if self.path.is_symlink():
            raise RuntimeError('Replaced audit log preserved.')
        text = self.path.read_text() if self.path.exists() else ''
        if text and not text.endswith('\n'):
            raise RuntimeError('Incomplete audit entry; preserve/export the log before repairing it.')
        for line in text.splitlines():
            entry = json.loads(line)
            if not isinstance(entry, dict) or entry.get('schema') != 1 or 'event' not in entry:
                raise ValueError('Invalid audit history; preserved for review.')
        return text

    def append(self, event, **fields):
        if self.path.parent.is_symlink():
            raise RuntimeError('Replaced audit directory preserved.')
        # Legacy no-install stop is a no-op; do not create unowned directories.
        if not self.path.parent.exists():
            return
        entry = dict(schema=1, time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     event=event, **fields)
        payload = (json.dumps(entry, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'ab', buffering=0) as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise RuntimeError('Audit destination is not a regular file.')
            self.text()  # Refuse to bury a truncated/corrupt entry with new events.
            remaining = memoryview(payload)
            while remaining:
                written = stream.write(remaining)
                if not written:
                    raise OSError('Audit write did not complete.')
                remaining = remaining[written:]
            os.fsync(stream.fileno())

    def change(self, action, target, read, requested, write):
        before = read()
        operation = uuid.uuid4().hex
        self.append('intent', operation=operation, action=action, target=str(target),
                    before=before, requested=requested)
        try:
            result = write()
            after = read()
        except BaseException as exc:
            try:
                after = read()
            except Exception as read_error:
                after = {'unavailable': str(read_error)}
            self.append('failed', operation=operation, action=action, target=str(target),
                        before=before, after=after, error=str(exc))
            raise
        self.append('completed', operation=operation, action=action, target=str(target),
                    before=before, after=after)
        return result

    def export(self, target):
        target = Path(target)
        # An explicitly chosen export is user-owned and must survive uninstall.
        # Require a new path, rather than overwrite any existing personal file.
        text = self.text()
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())

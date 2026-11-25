#!/usr/bin/python3
"""Small bounded Linux flight recorder. No command lines or environments recorded."""
import argparse
import datetime
import json
import os
from pathlib import Path
import time

LIMIT = 16 * 1024 * 1024
BACKUPS = 15


def read(path):
    try:
        return Path(path).read_text()
    except (OSError, UnicodeError):
        return ''


def sample():
    processes = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = dict(line.split(':', 1) for line in read(entry / 'status').splitlines() if ':' in line)
            stat = read(entry / 'stat').rsplit(')', 1)[1].split()
            processes.append(dict(pid=int(entry.name), name=status.get('Name', '').strip(),
                                  ppid=int(stat[1]), state=stat[0],
                                  rss_kib=int(status.get('VmRSS', '0').split()[0]),
                                  swap_kib=int(status.get('VmSwap', '0').split()[0]),
                                  cpu_ticks=int(stat[11]) + int(stat[12]), start_ticks=int(stat[19])))
        except (OSError, ValueError, IndexError):
            continue  # Process exited during the snapshot.
    processes.sort(key=lambda p: p['rss_kib'], reverse=True)
    return dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                boot_id=read('/proc/sys/kernel/random/boot_id').strip(),
                uptime=read('/proc/uptime').strip(), loadavg=read('/proc/loadavg').strip(),
                meminfo=read('/proc/meminfo'), vmstat=read('/proc/vmstat'),
                cpu=read('/proc/stat'), diskstats=read('/proc/diskstats'),
                pressure={k: read('/proc/pressure/' + k) for k in ('memory', 'cpu', 'io')},
                temperatures={str(p): read(p).strip() for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')},
                processes=processes)


def append(path, data):
    if path.exists() and path.stat().st_size >= LIMIT:
        path.with_name(path.name + '.' + str(BACKUPS)).unlink(missing_ok=True)
        for n in range(BACKUPS - 1, 0, -1):
            old = path.with_name(path.name + '.' + str(n))
            if old.exists():
                old.rename(path.with_name(path.name + '.' + str(n + 1)))
        path.rename(path.with_name(path.name + '.1'))
    with path.open('a') as stream:
        stream.write(json.dumps(data, separators=(',', ':')) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    args.directory.mkdir(parents=True, exist_ok=True)
    while True:
        start = time.monotonic()
        append(args.directory / 'samples.jsonl', sample())
        if args.once:
            return
        time.sleep(max(0, 5 - (time.monotonic() - start)))


if __name__ == '__main__':
    main()

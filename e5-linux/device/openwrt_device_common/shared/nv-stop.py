#!/usr/bin/python3
"""Stop the vendor writer between NV transactions, then flush/detach its loops."""
import argparse
import os
from pathlib import Path
import runpy
import signal
import subprocess
import time


def writing(pid):
    try:
        for fd in (Path('/proc') / str(pid) / 'fd').iterdir():
            try:
                if '/dev/loop' in os.readlink(fd):
                    return True
            except FileNotFoundError:
                pass
    except FileNotFoundError:
        pass
    return False


def freeze_idle(pid):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if not writing(pid):
            try:
                os.kill(pid, signal.SIGSTOP)
                # SIGSTOP is asynchronous. Check the stopped task, not a running
                # task which might open its next NV fd after our first check.
                for _ in range(50):
                    status = (Path('/proc') / str(pid) / 'status').read_text()
                    if any(line.startswith('State:') and line.split()[1] in ('T', 't')
                           for line in status.splitlines()):
                        if not writing(pid):
                            print('T551M: NV writer quiesced between transactions')
                            return
                        break
                    time.sleep(.02)
                os.kill(pid, signal.SIGCONT)
            except (ProcessLookupError, FileNotFoundError):
                return
        time.sleep(.1)
    raise RuntimeError('NV writer did not become idle; redundant copies require verification')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('quiesce', 'detach'))
    args = ap.parse_args()
    nv = runpy.run_path('/opt/e5/t551m-nv-prepare')
    nv['READY'].unlink(missing_ok=True)
    if args.action == 'quiesce':
        for pid, name in nv['vendor_pids']().items():
            if name == 'cp_diskserver':
                freeze_idle(pid)
        # rc.common now removes the procd instances. Its bounded SIGKILL timeout
        # terminates the frozen writer without letting it start another write.
        return
    deadline = time.monotonic() + 15
    while nv['vendor_pids']():
        if time.monotonic() >= deadline:
            raise RuntimeError('Vendor processes remain; refusing to detach NV')
        time.sleep(.1)
    for backing, dev in nv['attached_loops']().items():
        with dev.open('rb') as stream:
            os.fsync(stream.fileno())
        subprocess.run(['losetup', '-d', str(dev)], check=True)
        with backing.open('rb') as stream:
            os.fsync(stream.fileno())
    print('T551M: NV loops flushed and detached')


if __name__ == '__main__':
    main()

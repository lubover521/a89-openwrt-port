#!/usr/bin/env python3
"""Upload a new M8 trial image without replacing an existing installation."""
import argparse
import hashlib
from pathlib import Path
import subprocess


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', required=True)
    p.add_argument('--backup', type=Path, required=True)
    p.add_argument('--rootfs', type=Path, required=True)
    p.add_argument('--device-files', type=Path, required=True)
    a = p.parse_args()
    adb = ['adb', '-s', a.serial]
    def shell(cmd):
        return subprocess.check_output(adb + ['exec-out', 'su', '-c',
            'stty -onlcr 2>/dev/null; ' + cmd], timeout=180).decode().strip()
    if shell('getprop ro.product.model') != 'VIPME M8' or shell('getprop ro.boot.slot_suffix') != '_a':
        raise ValueError('Expected rooted M8 Android A')
    if shell('cat /sys/block/mmcblk0/device/cid') != (a.backup / 'cid.txt').read_text().strip():
        raise ValueError('Different device')
    targets = [('openwrt-m8.ext4', a.rootfs), ('device-files.tar', a.device_files)]
    for name, source in targets:
        remote = '/data/e5linux/' + name
        sha = digest(source)
        old = shell('if [ -e ' + remote + ' ]; then sha256sum ' + remote + '; fi')
        if old and old.split()[0] != sha:
            raise ValueError('Refusing to replace existing ' + remote)
        if old:
            print('Already verified:', name)
            continue
        subprocess.run(adb + ['push', str(source), '/data/local/tmp/m8-' + name], check=True)
        temp = '/data/local/tmp/m8-' + name
        if shell('sha256sum ' + temp).split()[0] != sha:
            raise ValueError('Upload hash mismatch: ' + name)
        shell('mkdir -p /data/e5linux && chmod 600 ' + temp + ' && mv ' + temp + ' ' + remote + ' && sync')
        if shell('sha256sum ' + remote).split()[0] != sha:
            raise ValueError('Installed hash mismatch: ' + name)
        print('Installed and verified:', name, flush=True)


if __name__ == '__main__':
    main()

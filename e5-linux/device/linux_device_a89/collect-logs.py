#!/usr/bin/env python3
"""Read A89 probe evidence after returning to rooted Android.

Identity: enforced against the identity.json recorded by collect.py from the
SAME unit (model + eMMC CID), because the persist log area offset is device
specific.
"""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True,
                        help='Directory created by collect.py (must contain identity.json)')
    args = parser.parse_args()
    identity = json.loads((args.backup / 'identity.json').read_text())
    cid = (args.backup / 'cid.txt').read_text().strip()
    adb = ['adb', '-s', args.serial, 'exec-out', 'su', '-c']

    def read(command):
        return subprocess.check_output(adb + ['stty -onlcr 2>/dev/null; ' + command], timeout=90)

    if read('getprop ro.product.model').strip().decode() != identity['model']:
        raise SystemExit('Not the recorded unit; refusing to collect another device')
    if read('cat /sys/block/mmcblk0/device/cid').strip().decode() != cid:
        raise SystemExit('Different physical unit; refusing')
    args.out.mkdir(parents=True, exist_ok=False)
    for name, command in {
        'identity.txt': 'getprop ro.product.model; getprop ro.boot.slot_suffix; cat /proc/uptime',
        'pstore-list.txt': 'ls -l /sys/fs/pstore',
        'console.txt': 'cat /sys/fs/pstore/console-ramoops-0',
        'pmsg.txt': 'cat /sys/fs/pstore/pmsg-ramoops-0',
        'persist.bin': 'dd if=/dev/block/by-name/boot_b bs=4096 skip=14336 count=1024 2>/dev/null',
        'uboot.bin': 'cat /dev/block/by-name/uboot_log',
    }.items():
        data = read(command)
        (args.out / name).write_bytes(data)
        if name == 'persist.bin':
            (args.out / 'persist.txt').write_bytes(data.split(b'\0', 1)[0])
        print(json.dumps({'file': name, 'bytes': len(data)}), flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Collect Baihe A89 bring-up evidence and boot recovery images, read-only.

Identity model: unlike the M8 port, this port does not hardcode the model or
board strings, because the A89's exact getprop values have not been confirmed
on a real unit yet. Instead this script RECORDS the unit's own identity into
identity.json inside --out. Every downstream tool (make-probe.py,
flash-probe.py, make-trial.py) refuses to run unless identity.json is present
and the connected phone matches it exactly, plus the eMMC CID. That keeps the
M8-level "refuse another device" guarantee without guessing strings now.

After the first run, verify by hand that identity.json matches YOUR A89 unit
(see PORTING-CHECKLIST.md) and fill the real values into README.md.

This script only reads. It never reads or writes raw NV/calibration
partitions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    adb = ['adb', '-s', args.serial, 'exec-out', 'su', '-c']

    def read(command):
        # This factory Magisk allocates a PTY even for adb exec-out. Disable
        # ONLCR before binary reads; never repair CRLF after reading binary data.
        return subprocess.check_output(adb + ['stty -onlcr 2>/dev/null; ' + command], timeout=180)

    model = read('getprop ro.product.model').strip()
    device = read('getprop ro.product.device').strip()
    brand = read('getprop ro.product.brand').strip()
    platform = read('getprop ro.board.platform').strip()
    if not model or not device:
        raise SystemExit('Could not read device identity')
    if b'uid=0(' not in read('id'):
        raise SystemExit('Root access required')
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {}

    def save(name, command):
        data = read(command)
        (args.out / name).write_bytes(data)
        manifest[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(name, len(data), flush=True)

    for name, command in {
        'properties.txt': 'getprop',
        'uname.txt': 'uname -a',
        'cid.txt': 'cat /sys/block/mmcblk0/device/cid',
        'cmdline.txt': 'cat /proc/cmdline',
        'modules.txt': 'cat /proc/modules',
        'inputs.txt': 'cat /proc/bus/input/devices',
        'partitions.txt': 'ls -l /dev/block/by-name; cat /proc/partitions',
        'mounts.txt': 'cat /proc/mounts; df -h /data',
        'dmesg.txt': 'dmesg',
        'live.dtb': 'cat /sys/firmware/fdt',
        'config.gz': 'cat /proc/config.gz',
        'i2c.txt': 'for d in /sys/bus/i2c/devices/*; do echo "$d"; cat "$d/name" 2>/dev/null; readlink "$d/driver"; done; true',
        'power.txt': 'for d in /sys/class/power_supply/*; do echo "$d"; cat "$d/uevent"; done',
        'modules-load.txt': 'cat /vendor/lib/modules/modules.load* 2>/dev/null; true',
    }.items():
        save(name, command)
    # Boot recovery only. Never read or write raw NV/calibration partitions.
    for part in ('boot_a', 'boot_b', 'vendor_boot_a', 'vendor_boot_b',
                 'init_boot_a', 'init_boot_b', 'dtb_a', 'dtb_b',
                 'dtbo_a', 'dtbo_b', 'vbmeta_a', 'vbmeta_b', 'misc', 'uboot_log'):
        path = '/dev/block/by-name/' + part
        if read('test -e ' + path + ' && echo present || true').strip() != b'present':
            continue
        save(part + '.img', 'cat ' + path)
        if read('sha256sum ' + path).decode().split()[0] != manifest[part + '.img']['sha256']:
            raise SystemExit('Boot recovery hash mismatch: ' + part)
    (args.out / 'misc-head.bin').write_bytes((args.out / 'misc.img').read_bytes()[:4096])
    identity = {
        'model': model.decode(),
        'device': device.decode(),
        'brand': brand.decode(),
        'platform': platform.decode(),
        'cid': (args.out / 'cid.txt').read_text().strip(),
    }
    (args.out / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    print('=' * 60)
    print('Recorded unit identity (verify these match YOUR A89):')
    print(json.dumps(identity, indent=2))
    print('=' * 60)
    print('If any value looks wrong (not a Baihe A89), delete the directory')
    print('and investigate before proceeding. Downstream tools will refuse')
    print('any phone that does not match identity.json exactly.')


if __name__ == '__main__':
    main()

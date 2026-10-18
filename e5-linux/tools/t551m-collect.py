#!/usr/bin/env python3
"""Read-only T551M hardware inventory and recovery backup (binary-safe on Windows)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--serial', required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    adb = ['adb', '-s', args.serial]

    def read(command):
        return subprocess.check_output(adb + ['exec-out', 'su', '-c', command])

    if read('getprop ro.product.model').strip() != b'T551M':
        raise SystemExit('This collector expects a T551M')
    if b'uid=0(' not in read('id'):
        raise SystemExit('Root access is required')
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {}

    def save(name, command):
        data = read(command)
        (args.out / name).write_bytes(data)
        manifest[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        print(name, len(data), flush=True)

    for name, cmd in {
        'properties.txt': 'getprop',
        'uname.txt': 'uname -a',
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
        'modules-load.txt': 'find /vendor/lib/modules /vendor_dlkm/lib/modules -name "modules.load*" -exec cat {} \\; 2>/dev/null; true',
    }.items():
        save(name, cmd)
    # Preserve the original bytes; no partition writes or reboot in this tool.
    for part in ('boot_a', 'boot_b', 'init_boot_a', 'init_boot_b',
                 'vendor_boot_a', 'vendor_boot_b', 'dtb_a', 'dtb_b',
                 'dtbo_a', 'dtbo_b', 'vbmeta_a', 'vbmeta_b', 'misc', 'uboot_log'):
        save(part + '.img', 'cat /dev/block/by-name/' + part)
        remote = read('sha256sum /dev/block/by-name/' + part).decode().split()[0]
        if remote != manifest[part + '.img']['sha256']:
            raise SystemExit('Backup hash mismatch: ' + part)
    (args.out / 'misc-head.bin').write_bytes((args.out / 'misc.img').read_bytes()[:4096])
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()

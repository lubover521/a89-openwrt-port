#!/usr/bin/env python3
"""Verified slot-B trial from rooted T551M Android, keeping slot A recoverable."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_bc(data):
    if len(data) != 32 or data[4:8] != b'BCAB':
        raise ValueError('Invalid boot control block')
    if zlib.crc32(data[:28]) != struct.unpack_from('<I', data, 28)[0]:
        raise ValueError('Invalid boot control CRC')
    if data[9] & 7 != 2 or not data[12] & 0x80:
        raise ValueError('Requires two slots and a successful Android A slot')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--serial', required=True)
    ap.add_argument('--backup', type=Path, required=True)
    ap.add_argument('--image', type=Path, required=True)
    ap.add_argument('--reboot', action='store_true')
    a = ap.parse_args()
    adb = ['adb', '-s', a.serial]

    def su(cmd):
        return subprocess.check_output(adb + ['exec-out', 'su', '-c', cmd])

    def push(path, remote):
        subprocess.run(adb + ['push', str(path), remote], check=True)
        if su('sha256sum ' + remote).decode().split()[0] != digest(path):
            raise ValueError('ADB transfer checksum mismatch')

    if su('getprop ro.product.model').strip() != b'T551M':
        raise SystemExit('Expected T551M')
    if su('getprop ro.boot.slot_suffix').strip() != b'_a':
        raise SystemExit('Run this from Android slot A')
    if su('getprop ro.boot.verifiedbootstate').strip() != b'orange':
        raise SystemExit('Bootloader must be unlocked')
    saved = json.loads((a.backup / 'manifest.json').read_text())
    for name in ('boot_a.img', 'boot_b.img', 'misc.img'):
        if digest(a.backup / name) != saved[name]['sha256']:
            raise SystemExit('Original backup checksum mismatch: ' + name)
    # B's DTB/DTBO/vendor ramdisk are retained and must match the inspected unit.
    for part in ('boot_a', 'dtb_b', 'dtbo_b', 'vendor_boot_b'):
        if su('sha256sum /dev/block/by-name/' + part).decode().split()[0] != saved[part + '.img']['sha256']:
            raise SystemExit('Device differs from original backup: ' + part)
    meta = json.loads(a.image.with_suffix('.json').read_text())
    if digest(a.image) != meta['sha256']:
        raise SystemExit('Trial image checksum mismatch')
    if a.image.stat().st_size != saved['boot_b.img']['bytes']:
        raise SystemExit('Trial image must fill exactly boot_b')
    live = su('dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null')
    validate_bc(live)
    if live.hex() != meta['misc_slot_a_hex']:
        raise SystemExit('Boot control changed; rebuild the image using current misc')
    bc = a.image.with_suffix('.misc-slot-b-trial.bin')
    trial = bc.read_bytes()
    validate_bc(trial)
    if trial.hex() != meta['misc_slot_b_trial_hex'] or trial[14] != 0x2f:
        raise SystemExit('Expected bounded, unsuccessful slot B trial with two tries')
    image_remote = '/data/local/tmp/t551m-trial.img'
    bc_remote = '/data/local/tmp/t551m-trial-bc.bin'
    push(a.image, image_remote)
    push(bc, bc_remote)
    # Recheck after transfers; do not arm a partial or corrupt boot partition.
    if su('dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null') != live:
        raise SystemExit('Boot control changed during transfer')
    su('dd if=' + image_remote + ' of=/dev/block/by-name/boot_b bs=4M && sync')
    if su('sha256sum /dev/block/by-name/boot_b').decode().split()[0] != meta['sha256']:
        raise SystemExit('boot_b write failed verification; Android A still selected')
    su('dd if=' + bc_remote + ' of=/dev/block/by-name/misc bs=1 seek=2048 conv=notrunc && sync')
    if su('dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null') != trial:
        raise SystemExit('Boot control write verification failed')
    print('Verified boot_b and armed the trial; Android boot_a is unchanged.')
    if a.reboot:
        subprocess.run(adb + ['reboot'], check=True)


if __name__ == '__main__':
    main()

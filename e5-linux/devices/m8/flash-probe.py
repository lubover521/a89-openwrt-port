#!/usr/bin/env python3
"""Flash a verified M8 probe to B, verify it, and arm a bounded Android rollback."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import zlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--previous-image', type=Path,
                        help='Previously verified probe whose first 56 MiB must match Boot B')
    args = parser.parse_args()
    adb = ['adb', '-s', args.serial]
    def read(command):
        return subprocess.check_output(adb + ['exec-out', 'su', '-c',
            'stty -onlcr 2>/dev/null; ' + command], timeout=180)
    def value(command):
        return read(command).decode().strip()
    if value('getprop ro.product.model') != 'VIPME M8' or value('getprop ro.product.device') != 'ums9157_2h10':
        raise SystemExit('M8 identity mismatch')
    manifest = json.loads(args.image.with_suffix('.json').read_text())
    backup = json.loads((args.backup / 'manifest.json').read_text())
    cid = (args.backup / 'cid.txt').read_bytes()
    if hashlib.sha256(cid).hexdigest() != backup['cid.txt']['sha256']:
        raise SystemExit('Backup CID integrity failure')
    if value('cat /sys/block/mmcblk0/device/cid') != cid.decode().strip():
        raise SystemExit('Different physical M8; refusing to flash')
    if value('getprop ro.boot.slot_suffix') != '_a' or value('getprop ro.boot.verifiedbootstate') != 'orange':
        raise SystemExit('Expected unlocked Android A')
    if (int(value('cat /sys/class/power_supply/battery/capacity')) < 5 or
            int(value('cat /sys/class/power_supply/battery/voltage_now')) < 3500000 or
            value('cat /sys/class/power_supply/battery/status') not in ('Charging', 'Full')):
        raise SystemExit('Keep charging: probe requires >=5%, >=3.5 V and external power')
    data = args.image.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest['sha256'] or len(data) != int(value('blockdev --getsize64 /dev/block/by-name/boot_b')):
        raise SystemExit('Invalid image size or checksum')
    if args.previous_image:
        previous = json.loads(args.previous_image.with_suffix('.json').read_text())
        if hashlib.sha256(args.previous_image.read_bytes()).hexdigest() != previous['sha256']:
            raise SystemExit('Previous probe integrity failure')
        digest_before = value('dd if=/dev/block/by-name/boot_b bs=1M count=56 2>/dev/null | sha256sum').split()[0]
        if digest_before != previous['sha256_head56m']:
            raise SystemExit('Boot B is not the expected previous probe')
    elif value('sha256sum /dev/block/by-name/boot_b').split()[0] != backup['boot_b.img']['sha256']:
        raise SystemExit('Boot B differs from backup; preserve and review before replacing it')
    boot_control = read('dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null')
    misc = (args.backup / 'misc.img').read_bytes()
    if hashlib.sha256(misc).hexdigest() != backup['misc.img']['sha256']:
        raise SystemExit('Backup misc integrity failure')
    if args.previous_image:
        if (len(boot_control) != 32 or boot_control[:9] != b'_a\0\0BCAB\x01' or
                (boot_control[9] & 7) != 2 or
                zlib.crc32(boot_control[:28]) != struct.unpack('<I', boot_control[28:])[0] or
                not boot_control[12] & 128 or
                (boot_control[12] & 15) < (boot_control[14] & 15)):
            raise SystemExit('Expected valid successful Android A boot control')
    elif boot_control != misc[2048:2080]:
        raise SystemExit('Unexpected live boot control; Android remains selected')
    restore = args.image.with_suffix('.misc-original.bin')
    restore.write_bytes(boot_control)
    trial = args.image.with_suffix('.misc-slot-b-trial.bin')
    if trial.read_bytes().hex() != manifest['misc_slot_b_trial_hex']:
        raise SystemExit('Invalid trial boot control')
    for source, remote in ((args.image, '/data/local/tmp/m8-probe.img'),
                           (trial, '/data/local/tmp/m8-probe-bc.bin'),
                           (restore, '/data/local/tmp/m8-probe-bc-restore.bin')):
        subprocess.run(adb + ['push', str(source), remote], check=True)
        if value('sha256sum ' + remote).split()[0] != hashlib.sha256(source.read_bytes()).hexdigest():
            raise SystemExit('Upload verification failed')
    read('dd if=/data/local/tmp/m8-probe.img of=/dev/block/by-name/boot_b bs=4M && sync')
    if value('sha256sum /dev/block/by-name/boot_b').split()[0] != digest:
        raise SystemExit('Boot B verification failed; Android A is still selected')
    read('dd if=/data/local/tmp/m8-probe-bc.bin of=/dev/block/by-name/misc bs=1 seek=2048 conv=notrunc && sync')
    if read('dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null') != trial.read_bytes():
        read('dd if=/data/local/tmp/m8-probe-bc-restore.bin of=/dev/block/by-name/misc bs=1 seek=2048 conv=notrunc && sync')
        if read('dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null') != boot_control:
            raise SystemExit('Boot control rollback verification failed; do not reboot')
        raise SystemExit('Trial boot control verification failed; Android A control restored')
    print('Verified M8 probe installed; rebooting with Android A rollback', flush=True)
    subprocess.run(adb + ['reboot'], check=True)


if __name__ == '__main__':
    main()

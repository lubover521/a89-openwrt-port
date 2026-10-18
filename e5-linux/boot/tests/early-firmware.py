#!/usr/bin/env python3
"""Run init's firmware discovery with fake mounts/devices under BusyBox ash.

No real block device, mount, firmware or partition is accessed. Run on Linux.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[2]
INIT = (TOP / 'boot/init').read_text()
FUNCTIONS = INIT[INIT.index('early_card_firmware() {'):INIT.index('\nloaded=0\n')]


class Discovery(unittest.TestCase):
    def run_boot(self, *, explicit=False, card=False, delayed=False,
                 bundle='good', existing=False, mount_fail=False):
        with tempfile.TemporaryDirectory(prefix='e5-firmware-test-') as directory:
            root = Path(directory)
            def write(name, value):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)
                return path
            write('sys/class/block/mmcblk0p70/uevent', 'PARTNAME=userdata\n')
            write('dev/mmcblk0p70', '')
            write('proc/cmdline', 'console=tty0' + (
                ' e5.openwrt=openwrt-t551m.ext4' if explicit else ''))
            for name in ('run', 'tmp', 'data', 'lib/firmware'):
                (root / name).mkdir(parents=True, exist_ok=True)
            if bundle != 'missing':
                payload = write('payload/lib/firmware/wcnmodem.bin', 'userdata')
                target = root / 'userdata/e5linux/device-files.tar'
                target.parent.mkdir(parents=True)
                if bundle == 'corrupt':
                    target.write_text('not a tar archive')
                else:
                    with tarfile.open(target, 'w') as archive:
                        archive.add(payload.parent.parent, arcname='lib')
            if card or delayed:
                write('card/etc/e5/sd-root', '')
                write('card/sbin/init', '#!/bin/sh\n').chmod(0o755)
                write('card/lib/firmware/wcnmodem.bin', 'card')
            if card:
                (root / 'sys/class/block/mmcblk1').mkdir()
                write('dev/mmcblk1p1', '')
            if existing:
                write('lib/firmware/wcnmodem.bin', 'embedded')
            # Redirect absolute paths and model block nodes as ordinary files.
            functions = re.sub(r'(?<![\w./-])/(?:proc/cmdline|sys/class/block|dev|tmp|data|lib/firmware|run)\b',
                               lambda m: directory + m[0], FUNCTIONS)
            functions = functions.replace('[ -b ', '[ -e ')
            harness = r'''
log() { echo "log $*"; }
f2fs_last_cp() { :; }
mdev() { echo scan; }
umount() { echo "unmount $*"; }
mount() {
    for destination; do :; done
    case "$*" in
        *'-t f2fs -o ro,norecovery '*)
            echo userdata-mount
            [ "$MOUNT_FAIL" = 1 ] && return 1
            [ -d "$ROOT/userdata" ] && cp -a "$ROOT/userdata/." "$destination/"
            return 0 ;;
        *'-t ext4 -o ro,noload,noatime'*)
            echo card-mount
            cp -a "$ROOT/card/." "$destination/" ;;
        *) echo "Unexpected mount: $*" >&2; exit 20 ;;
    esac
}
waits=0
sleep() {
    echo "wait $1"
    waits=$((waits + 1))
    if [ "$DELAYED" = 1 ] && [ "$waits" = 3 ]; then
        mkdir -p "$ROOT/sys/class/block/mmcblk1"
        : > "$ROOT/dev/mmcblk1p1"
    fi
}
early_device_firmware
'''
            script = functions + harness
            env = dict(os.environ, ROOT=directory, DELAYED=str(int(delayed)),
                       MOUNT_FAIL=str(int(mount_fail)))
            result = subprocess.run([shutil.which('busybox'), 'sh', '-c', script],
                                    env=env, capture_output=True, text=True, timeout=10)
            errors = '\n'.join(p.read_text() for p in (root / 'run').glob('*.err'))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr + errors)
            firmware = root / 'lib/firmware/wcnmodem.bin'
            return firmware.read_text() if firmware.exists() else None, result.stdout

    def test_explicit_internal_image_has_no_card_wait(self):
        value, trace = self.run_boot(explicit=True, card=True)
        self.assertEqual(value, 'userdata')
        self.assertNotIn('wait ', trace)
        self.assertNotIn('card-mount', trace)

    def test_normal_tf_boot_keeps_card_priority(self):
        value, trace = self.run_boot(card=True)
        self.assertEqual(value, 'card')
        self.assertNotIn('userdata-mount', trace)

    def test_late_tf_card_is_still_detected(self):
        value, trace = self.run_boot(delayed=True)
        self.assertEqual(value, 'card')
        self.assertEqual(trace.count('wait 1\n'), 3)

    def test_normal_boot_without_card_keeps_full_discovery_window(self):
        value, trace = self.run_boot()
        self.assertEqual(value, 'userdata')
        self.assertEqual(trace.count('wait 1\n'), 10)

    def test_missing_or_corrupt_internal_bundle_falls_back_to_tf(self):
        for bundle in ('missing', 'corrupt'):
            with self.subTest(bundle=bundle):
                value, trace = self.run_boot(explicit=True, bundle=bundle, card=True)
                self.assertEqual(value, 'card')
                self.assertLess(trace.index('userdata-mount'), trace.index('card-mount'))

    def test_embedded_firmware_needs_no_storage(self):
        value, trace = self.run_boot(existing=True)
        self.assertEqual(value, 'embedded')
        self.assertEqual(trace, '')

    def test_unmountable_userdata_falls_back_to_tf(self):
        value, trace = self.run_boot(explicit=True, mount_fail=True, card=True)
        self.assertEqual(value, 'card')
        self.assertIn('mount-fail', trace)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Device filtering tests; optional real APK test in a disposable container."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[2]


class BlockProbe(unittest.TestCase):
    def test_types_before_open(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / 'guard')
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror',
                            str(TOP / 'openwrt/tests/block-probe-guard.c'), '-o', binary], check=True)
            subprocess.run([binary], check=True)

    def test_patch_and_common_image_integration(self):
        patch = (TOP / 'openwrt/patches/fstools-probe-device-types.patch').read_text()
        self.assertIn('+\tif (!block_probe_allowed(path))', patch)
        guard = (TOP / 'openwrt/block-probe-guard.h').read_text()
        self.assertNotIn('open(', guard)
        builder = (TOP / 'openwrt/build-rootfs.sh').read_text()
        self.assertIn('sh "$HERE/build-block-mount.sh" "$BLOCK_APK"', builder)
        self.assertIn('apk add --allow-untrusted /in/block-mount-guarded.apk', builder)
        self.assertIn('$R/etc/e5/block-mount.build-id', builder)

    @unittest.skipUnless(os.environ.get('E5_TEST_BLOCK_APK'), 'set E5_TEST_BLOCK_APK for APK integration')
    def test_real_apk_does_not_hang_on_fifo_or_probe_character_channels(self):
        apk = Path(os.environ['E5_TEST_BLOCK_APK']).resolve()
        with tempfile.TemporaryDirectory() as directory:
            disk = Path(directory) / 'disk.ext4'
            with disk.open('wb') as stream:
                stream.truncate(16 << 20)
            subprocess.run(['mkfs.ext4', '-q', '-F', '-L', 'probe-fixture', str(disk)], check=True)
            command = r'''
set -eu
mkdir -p /var/lock /var/run
apk update >/dev/null
apk add --allow-untrusted /test/block.apk coreutils-timeout
test -x /sbin/block
test -s /lib/libblkid-tiny.so
test -s /etc/init.d/fstab
cp /test/disk.ext4 /dev/sd-fixture
mkfifo /dev/sd-fifo
ln -s /dev/sd-fifo /dev/sd-fifo-link
ln -s /dev/zero /dev/sdiag
ln -s /dev/null /dev/sdiom
timeout 5 /sbin/block info > /tmp/info
cat /tmp/info
grep -q 'LABEL="probe-fixture"' /tmp/info
if grep -E 'sdiag|sdiom|sd-fifo' /tmp/info; then exit 1; fi
timeout 5 /sbin/block detect > /tmp/detect
uuid=$(sed -n 's/.* UUID="\([^"]*\)".*/\1/p' /tmp/info | head -1)
test -n "$uuid"
grep -F "$uuid" /tmp/detect
timeout 5 /sbin/block info /dev/sdiag > /tmp/specific
test ! -s /tmp/specific
echo 'APK install, ext4 discovery, FIFO and character-device filtering: passed'
'''
            subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/arm64',
                            '-v', f'{apk}:/test/block.apk:ro', '-v', f'{disk}:/test/disk.ext4:ro',
                            os.environ.get('E5_TEST_IMAGE', 'e5-openwrt-base:25.12.5'),
                            '/bin/sh', '-ec', command], check=True, timeout=180)


if __name__ == '__main__':
    unittest.main()

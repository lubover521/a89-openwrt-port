"""The deployment guard must reject mismatched devices before any write."""
import hashlib
import json
from pathlib import Path
import runpy
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

HERE = Path(__file__).resolve().parent


class FlashGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / 'probe.img'
        self.image.write_bytes(b'verified test image')
        cid = b'0123456789abcdef0123456789abcdef\n'
        (self.root / 'cid.txt').write_bytes(cid)
        bc = bytearray(32)
        bc[:10] = b'_a\0\0BCAB\x01\x02'
        bc[12], bc[14] = 0x9f, 0x0f
        bc[28:] = struct.pack('<I', zlib.crc32(bc[:28]))
        self.bc = bytes(bc)
        misc = bytes(2048) + self.bc + bytes(2016)
        (self.root / 'misc.img').write_bytes(misc)
        (self.root / 'manifest.json').write_text(json.dumps({
            'cid.txt': {'sha256': hashlib.sha256(cid).hexdigest()},
            'misc.img': {'sha256': hashlib.sha256(misc).hexdigest()},
            'boot_b.img': {'sha256': 'stock-boot-hash'},
        }))
        self.image.with_suffix('.json').write_text(json.dumps({
            'sha256': hashlib.sha256(self.image.read_bytes()).hexdigest(),
            'sha256_head56m': 'previous-head-hash',
            'misc_slot_b_trial_hex': self.bc.hex(),
        }))
        self.image.with_suffix('.misc-slot-b-trial.bin').write_bytes(self.bc)
        self.values = {
            'getprop ro.product.model': b'VIPME M8\n',
            'getprop ro.product.device': b'ums9157_2h10\n',
            'cat /sys/block/mmcblk0/device/cid': cid,
            'getprop ro.boot.slot_suffix': b'_a\n',
            'getprop ro.boot.verifiedbootstate': b'orange\n',
            'cat /sys/class/power_supply/battery/capacity': b'60\n',
            'cat /sys/class/power_supply/battery/voltage_now': b'3900000\n',
            'cat /sys/class/power_supply/battery/status': b'Charging\n',
            'blockdev --getsize64 /dev/block/by-name/boot_b': str(self.image.stat().st_size).encode(),
            'sha256sum /dev/block/by-name/boot_b': b'stock-boot-hash  boot_b\n',
            'dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null': self.bc,
            'dd if=/dev/block/by-name/boot_b bs=1M count=56 2>/dev/null | sha256sum': b'previous-head-hash  -\n',
        }

    def reject(self, message, previous=False):
        calls = []
        def read(argv, **kwargs):
            command = argv[-1].removeprefix('stty -onlcr 2>/dev/null; ')
            calls.append(command)
            return self.values[command]
        argv = ['flash-probe.py', '--serial', 'test', '--backup', str(self.root), '--image', str(self.image)]
        if previous:
            argv += ['--previous-image', str(self.image)]
        with patch.object(sys, 'argv', argv), patch('subprocess.check_output', side_effect=read), patch('subprocess.run') as mutation:
            with self.assertRaisesRegex(SystemExit, message):
                runpy.run_path(str(HERE / 'flash-probe.py'), run_name='__main__')
            mutation.assert_not_called()
        self.assertFalse(any('of=/dev/' in command or 'reboot' in command for command in calls))

    def test_other_model(self):
        self.values['getprop ro.product.model'] = b'E5'
        self.reject('identity mismatch')

    def test_other_physical_unit(self):
        self.values['cat /sys/block/mmcblk0/device/cid'] = b'0' * 32
        self.reject('Different physical M8')

    def test_corrupt_image(self):
        self.image.write_bytes(b'corrupt')
        self.reject('Invalid image')

    def test_unknown_boot_b(self):
        self.values['sha256sum /dev/block/by-name/boot_b'] = b'unknown-boot-image'
        self.reject('Boot B differs')

    def test_low_voltage(self):
        self.values['cat /sys/class/power_supply/battery/voltage_now'] = b'3300000'
        self.reject('Keep charging')

    def test_corrupt_boot_control_after_probe(self):
        self.values['dd if=/dev/block/by-name/misc bs=1 skip=2048 count=32 2>/dev/null'] = self.bc[:-1] + bytes([self.bc[-1] ^ 1])
        self.reject('valid successful Android A', previous=True)

    def test_previous_image_mismatch(self):
        self.values['dd if=/dev/block/by-name/boot_b bs=1M count=56 2>/dev/null | sha256sum'] = b'not-previous-probe'
        self.reject('expected previous probe', previous=True)


if __name__ == '__main__':
    unittest.main()

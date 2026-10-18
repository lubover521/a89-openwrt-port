#!/usr/bin/env python3
"""Exercise installer failures without adb, a device or card writes."""
import contextlib
import gzip
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
import struct
import zlib
import json
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('flash', Path(__file__).resolve().parents[3] / 'openwrt/bundle/flash.py')
flash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flash)


class Diagnostics(unittest.TestCase):
    def test_wrong_profile_is_rejected_before_partition_commands(self):
        for profile, model, wrong in (('e5', 'E5', 'T551M'),
                                     ('t551m', 'T551M', 'VIPME M8'),
                                     ('m8', 'VIPME M8', 'E5')):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                Path(directory, 'device-profile.json').write_text(json.dumps({
                    'profile': profile, 'android_models': [model]}))
                def shell(command):
                    if command.endswith(' -c id'):
                        return 'uid=0(root)'
                    self.assertEqual(command, 'getprop ro.product.model')
                    return wrong
                with patch.object(flash, 'F', directory), patch.object(flash, 'SU', None), \
                     patch.object(flash, 'adb', return_value='List of devices attached\nunit\tdevice\n'), \
                     patch.object(flash, 'sh', shell), patch.object(flash, 'su') as su, \
                     contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        flash.android_checks()
                    su.assert_not_called()

    def control(self, a=0x9f, b=0x1e):
        data = bytearray(32)
        data[:10] = b'_a\0\0BCAB\x01\x02'
        data[12], data[14] = a, b
        data[16:28] = b'preserve-me!'
        data[28:] = struct.pack('<I', zlib.crc32(data[:28]))
        return bytes(data)

    def test_live_boot_control_accepts_device_reserved_data(self):
        data = self.control()
        self.assertEqual(flash.validate_boot_control(data), data)
        for bad in (data[:-1], data[:28] + bytes(4), self.control(a=0x1f), self.control(a=0x9e, b=0x1f)):
            with self.assertRaises(ValueError):
                flash.validate_boot_control(bad)

    def test_arm_only_changes_live_32_bytes_and_backs_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            misc = root / 'misc'
            before = b'A' * 2048 + self.control() + b'Z' * 2016
            misc.write_bytes(before)
            def push(local, remote, label):
                (root / 'e5-bc-b.bin').write_bytes(Path(local).read_bytes())
            def execute(stage, command, timeout=600):
                command = command.replace('/dev/block/by-name/misc', str(misc))
                command = command.replace('/data/adb/e5-boot-control', str(root / 'backups'))
                command = command.replace('/data/local/tmp', str(root))
                result = subprocess.run(['sh', '-ec', command], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout
            with patch.object(flash, 'od_hex', return_value=self.control().hex()), \
                 patch.object(flash, 'push', push), patch.object(flash, 'su_checked', execute):
                flash.arm_slot_b()
            after = misc.read_bytes()
            self.assertEqual(after[:2048], before[:2048])
            self.assertEqual(after[2080:], before[2080:])
            block = after[2048:2080]
            self.assertEqual(block[:4], b'_b\0\0')
            self.assertEqual((block[12], block[14]), (0x9e, 0x2f))
            self.assertEqual(block[16:28], self.control()[16:28])
            self.assertEqual(struct.unpack('<I', block[28:])[0], zlib.crc32(block[:28]))
            self.assertEqual(next((root / 'backups').iterdir()).read_bytes(), self.control())

    def failure(self, stage, response, context='EXT4-fs: unsupported feature'):
        def remote(command, timeout=600):
            if command.startswith('dmesg'):
                if isinstance(context, Exception):
                    raise context
                return context
            return response
        error = io.StringIO()
        with patch.object(flash, 'su', remote), contextlib.redirect_stderr(error):
            with self.assertRaises(SystemExit):
                flash.su_checked(stage, 'mount /dev/card /mnt/card')
        return error.getvalue()

    def test_mount_failure_reports_stage_status_and_kernel(self):
        error = self.failure('mounting card', 'mount: Invalid argument\n__E5_STAGE_STATUS__=32\n')
        for text in ('mounting card', 'exit 32', 'Invalid argument', 'unsupported feature'):
            self.assertIn(text, error)

    def test_disconnect_not_reported_as_missing_image(self):
        error = self.failure('writing image', 'adb: device offline\n')
        self.assertIn('no completion status', error)
        self.assertIn('device offline', error)

    def test_diagnostic_timeout_does_not_hide_original_error(self):
        error = self.failure('writing image', 'dd: I/O error\n__E5_STAGE_STATUS__=1\n',
                             subprocess.TimeoutExpired('diagnostics', 20))
        self.assertIn('dd: I/O error', error)
        self.assertIn('diagnostics unavailable', error)

    def test_sequence_stops_before_later_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / 'must-not-exist'
            def shell(command, timeout=600):
                if command.startswith('dmesg'):
                    return ''
                return subprocess.run(['sh', '-c', command], capture_output=True, text=True).stdout
            with patch.object(flash, 'su', shell), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    flash.su_checked('sequence', f'false; touch "{sentinel}"')
            self.assertFalse(sentinel.exists())

    def test_vold_unmounts_only_sd_not_internal_storage(self):
        calls = []
        def checked(stage, command, timeout=600):
            calls.append(command)
            if 'list-volumes' in command:
                return 'public:179,1 mounted card\nprivate:253,0 mounted data\n'
            return ''
        with patch.object(flash, 'sd_device_numbers', return_value={'179:0', '179:1'}), \
             patch.object(flash, 'su_checked', checked):
            flash.unmount_android_sd('/dev/card')
        self.assertIn('sm unmount public:179,1', calls)
        self.assertNotIn('sm unmount private:253,0', calls)

    def test_still_mounted_aborts_before_gpt(self):
        def checked(stage, command, timeout=600):
            return '1 2 179:1 / /mnt/media_rw/card rw - vfat /dev/cardp1 rw\n' if 'mountinfo' in command else ''
        with patch.object(flash, 'sd_device_numbers', return_value={'179:1'}), \
             patch.object(flash, 'su_checked', checked), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                flash.unmount_android_sd('/dev/card')

    def test_gzip_checks_crc_and_real_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.gz'
            path.write_bytes(gzip.compress(b'x' * 10000))
            self.assertEqual(flash.gz_usize(path), 10000)
            data = bytearray(path.read_bytes()); data[-8] ^= 1; path.write_bytes(data)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                flash.gz_usize(path)

    def simulate_install(self, failure=None):
        calls = []
        def record(kind, text=''):
            calls.append((kind, text))
            if failure and failure in text:
                raise SystemExit('injected failure')
        def checked(stage, command, timeout=600):
            record('command', command)
            return '0' if '/ro' in command else ''
        def firmware(*args):
            record('firmware', 'firmware')
            return 1024
        args = SimpleNamespace(apn='', ssid='test', wifi_key='12345678', y=True)
        with contextlib.ExitStack() as stack:
            mocks = {
                'find_adb': lambda: None, 'android_checks': lambda: None,
                'install_preflight': lambda: record('preflight'),
                'boot_json': lambda: {'sha256': 'abc'},
                'device_sd': lambda: '/dev/block/mmcblk1',
                'device_size': lambda dev: (5 << 20) if dev.endswith('p1') else (16 << 30),
                'gz_usize': lambda path: 4 << 20,
                'su_checked': checked, 'pull_device_files': firmware,
                'push': lambda local, remote, label: record('push', label),
                'unmount_android_sd': lambda sd: record('release', sd),
                'bootchain': lambda mode: record('chain', mode),
                'arm_slot_b': lambda: record('arm'),
                'adb': lambda *args, **kwargs: record('adb', args[0]),
                'su': lambda cmd, **kwargs: 'abc' if cmd.startswith('sha256sum') else 'ok',
            }
            for name, value in mocks.items():
                stack.enter_context(patch.object(flash, name, value))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            if failure:
                with self.assertRaises(SystemExit):
                    flash.install_sd(args)
            else:
                flash.install_sd(args)
        return calls

    def test_install_order_and_no_automatic_reboot(self):
        calls = self.simulate_install()
        index = lambda kind, text='': next(i for i, (k, t) in enumerate(calls) if k == kind and text in t)
        self.assertLess(index('firmware'), index('command', '--zap-all'))
        self.assertLess(index('push', 'boot.img'), index('command', '--zap-all'))
        self.assertLess(index('release'), index('chain', 'sync'))
        self.assertLess(index('chain', 'sync'), index('command', '--zap-all'))
        self.assertLess(index('command', 'ro,noload'), index('command', 'of=/dev/block/by-name/boot_b'))
        self.assertLess(index('command', 'echo sd'), index('arm'))
        self.assertNotIn(('adb', 'reboot'), calls)

    def test_firmware_failure_preserves_card_and_chain(self):
        calls = self.simulate_install('firmware')
        self.assertFalse(any('--zap-all' in text or kind in ('chain', 'arm') for kind, text in calls))

    def test_readonly_remount_failure_never_writes_boot_or_arms_slot(self):
        calls = self.simulate_install('ro,noload')
        self.assertFalse(any('of=/dev/block/by-name/boot_b' in text or kind == 'arm' for kind, text in calls))


if __name__ == '__main__':
    unittest.main()

"""Bounded, reversible-in-RAM call gain tuning; no audio hardware required."""
import importlib.util
from pathlib import Path
import stat
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'overlay/opt/e5/e5_call_profiles.py'
spec = importlib.util.spec_from_file_location('profiles', SOURCE)
profiles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiles)


def fixture():
    blob = bytearray(struct.pack('<16sII', b'audio_profile', 67, 730) + b'\x55' * (67 * 730))
    for mode in profiles.LOCAL_MODES:
        struct.pack_into('<7H', blob, 24 + mode * 730 + 0x244, 130, 183, 258, 365, 649, 1029, 1029)
    return bytes(blob)


class ProfilesTest(unittest.TestCase):
    def test_only_local_downlink_steps_change(self):
        original = fixture()
        new = profiles.quieter_low_steps(original, 30)
        allowed = set()
        for mode in profiles.LOCAL_MODES:
            offset = 24 + mode * 730 + 0x244
            allowed.update(range(offset, offset + 12))
            gains = struct.unpack_from('<7H', new, offset)
            self.assertEqual(gains[0], 4)
            self.assertEqual(gains[-1], 1029)
            self.assertEqual(list(gains), sorted(gains))
        self.assertEqual(len(new), len(original))
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(original, new)) if a != b))

    def test_reject_unknown_layout_and_invalid_range(self):
        for data, db in [(fixture()[:-1], 30), (b'bad', 30), (fixture(), -1), (fixture(), 37)]:
            with self.assertRaises(ValueError):
                profiles.quieter_low_steps(data, db)

    def test_ram_write_readback_and_restart_idempotence(self):
        original = fixture()
        desired = profiles.quieter_low_steps(original, 30)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, firmware, device = root/'config', root/'firmware', root/'device'
            config.write_text('30\n'); firmware.write_bytes(original)
            for current, expect_write in [(original, True), (desired, False)]:
                with patch.object(Path, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
                     patch.object(profiles.os, 'open', return_value=99), \
                     patch.object(profiles.os, 'close'), \
                     patch.object(profiles.os, 'read', side_effect=[current, desired]), \
                     patch.object(profiles.os, 'write', return_value=len(desired)) as write:
                    self.assertEqual(profiles.prepare(config, firmware, device), desired)
                    self.assertEqual(write.call_count, int(expect_write))
                    if expect_write: write.assert_called_once_with(99, desired)
            self.assertEqual(firmware.read_bytes(), original)
            with patch.object(Path, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
                 patch.object(profiles.os, 'open', return_value=99), \
                 patch.object(profiles.os, 'close'), \
                 patch.object(profiles.os, 'read', return_value=b'foreign profile'), \
                 patch.object(profiles.os, 'write') as write:
                with self.assertRaises(ValueError): profiles.prepare(config, firmware, device)
                write.assert_not_called()

    def test_existing_boards_do_not_access_tuning_device(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(profiles.os, 'open') as opened:
            self.assertIsNone(profiles.prepare(config=Path(directory)/'missing'))
            opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()

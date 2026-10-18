import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('bt_address', Path(__file__).with_name('bluetooth-address.py'))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)


class AddressRecovery(unittest.TestCase):
    def test_only_adapter_address_is_recovered_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / 'etc/e5/device-profile'
            firmware = root / 'lib/firmware/sprd/marlin3lite_pskey.bin'
            config = root / 'mnt/e5-data/misc/bluedroid/bt_config.conf'
            for path in (profile, firmware, config):
                path.parent.mkdir(parents=True, exist_ok=True)
            profile.write_text('m8\n')
            original = bytes(range(20)) + bytes(6) + bytes(range(150))
            firmware.write_bytes(original)
            config.write_text('[Adapter]\nAddress = 40:45:da:12:34:56\n'
                              '[11:22:33:44:55:66]\nLinkKey = must-not-copy\n')
            self.assertTrue(bt.prepare(root))
            result = firmware.read_bytes()
            self.assertEqual(result[:20], original[:20])
            self.assertEqual(result[20:26], bytes.fromhex('563412da4540'))
            self.assertEqual(result[26:], original[26:])
            config.unlink()
            self.assertFalse(bt.prepare(root))
            self.assertEqual(result, firmware.read_bytes())

    def test_placeholder_and_multicast_addresses_rejected(self):
        for value in ('', '00:00:00:00:00:00', 'ff:ff:ff:ff:ff:ff',
                      '41:45:da:12:34:56', '40:45:da:12:34:zz'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bt.parse_address(value)


if __name__ == '__main__':
    unittest.main()

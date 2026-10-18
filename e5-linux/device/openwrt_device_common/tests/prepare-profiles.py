"""Clean assembly for each board: real stagers, no modem, credentials or package install."""
import os
from pathlib import Path
import runpy
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

TOP = Path(__file__).resolve().parents[3]
real_run = runpy.run_path
prepare = real_run(str(TOP / 'device/openwrt_device_common/shared/prepare-root.py'))['prepare']


class Profiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / 'base'; self.base.mkdir()
        for source in (TOP / 'ci/infoscreen/root', TOP / 'device/openwrt_device_common/overlay'):
            shutil.copytree(source, self.base, dirs_exist_ok=True)
        shutil.copytree(TOP / 'device/linux_device_common/overlay/opt/e5', self.base / 'opt/e5', dirs_exist_ok=True)
        (self.base / 'etc/openwrt_release').write_text("DISTRIB_RELEASE='25.12.5'\n")
        (self.base / 'etc/shadow').write_text('root:synthetic-donor-hash:0:0:99999:7:::\n')
        for name in ('opt/e5/android', 'etc/dropbear', 'etc/ssh', 'root', 'tmp'):
            (self.base / name).mkdir(parents=True, exist_ok=True)
        self.defaults = self.root / 'defaults.tar'
        with tarfile.open(self.defaults, 'w') as archive:
            archive.add(self.base / 'etc/config', arcname='etc/config')

    def staged(self, path):
        result = real_run(str(path))
        if Path(path).name == 'ui.py':
            # Validate real file staging without downloading optional themes.
            result['stage'].__globals__['PACKAGES'] = {}
        return result

    def test_clean_roots_keep_board_boundaries_and_strip_donor_identity(self):
        with patch.object(runpy, 'run_path', side_effect=self.staged), \
                patch.dict(os.environ, E5_UI_CACHE=str(self.root / 'cache')):
            for profile in ('e5', 't551m', 'm8'):
                with self.subTest(profile=profile):
                    root = self.root / profile
                    prepare(self.base, root, self.defaults, profile=profile)
                    self.assertEqual((root / 'etc/e5/device-profile').read_text().strip(), profile)
                    self.assertTrue((root / 'etc/shadow').read_text().startswith('root::'))
                    self.assertEqual((root / 'etc/machine-id').read_text(), '')
                    self.assertFalse(any((root / 'opt/e5/android').iterdir()))
                    self.assertFalse((root / 'etc/e5/install.conf').exists())
                    self.assertFalse((root / 'etc/e5/sd-root').exists())
                    for name in ('etc/init.d/e5-infoscreen', 'usr/libexec/e5-infoscreen/plugin',
                                 'usr/libexec/unisoc-modem/apn', 'usr/libexec/e5-mm-report-ports'):
                        self.assertTrue((root / name).stat().st_mode & 0o111, name)
                    self.assertEqual((root / 'etc/config/unisoc_apn').stat().st_mode & 0o777, 0o600)
                    config = (root / 'etc/config/unisoc_modem').read_text()
                    self.assertEqual('auto_work_mode' in config, profile == 't551m')
                    if profile == 'e5':
                        self.assertFalse((root / 'etc/e5/t551m-persistent').exists())
                        self.assertIn('aw87xxx', (root / 'opt/e5/e5-audio-dsp').read_text())
                    if profile == 'm8':
                        self.assertEqual((root / 'etc/e5/receiver-volume-ceiling').read_text().strip(), '5')

    def test_private_vendor_source_is_rejected_before_copy(self):
        (self.base / 'opt/e5/android/private-fixture').write_text('synthetic')
        target = self.root / 'rejected'
        with self.assertRaisesRegex(ValueError, 'vendor'):
            prepare(self.base, target, self.defaults, profile='e5')
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()

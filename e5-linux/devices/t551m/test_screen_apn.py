"""Screen APN packaging and bridge contract checks, without modem commands."""
from pathlib import Path
import runpy
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
screen=runpy.run_path(str(HERE/'infoscreen/stage.py'))


class ScreenAPN(unittest.TestCase):
    def test_shared_screen_stage_carries_editor_and_rpc_for_all_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            for profile in ('e5','t551m','m8'):
                with self.subTest(profile=profile):
                    root=Path(tmp)/profile
                    marker=root/'etc/e5/device-profile'
                    marker.parent.mkdir(parents=True);marker.write_text(profile+'\n')
                    screen['stage'](root)
                    base=root/'usr/share/e5-infoscreen'
                    self.assertIn('function stAPNRender', (base/'www/app.js').read_text(encoding='utf-8'))
                    self.assertIn("ubus_call('mu300dash','apn_set'",(base/'api.uc').read_text(encoding='utf-8'))
                    self.assertIn('.apn-editor',(base/'www/mobile.css').read_text(encoding='utf-8'))
                    self.assertIn("category:'apn'",(base/'settings.uc').read_text(encoding='utf-8'))
                    self.assertNotIn('function apn_options',(base/'settings.uc').read_text(encoding='utf-8'))
                    self.assertNotIn("c.set('network','wan','apn'",(base/'settings.uc').read_text(encoding='utf-8'))

    def test_bridge_allows_only_public_operations_and_serializes_payload(self):
        api=screen['sources']()['api.uc']
        bridge=api.split("if (path == '/apn')",1)[1].split("if (!post && path == '/network-job')",1)[0]
        self.assertIn("['save','delete','apply','auto']",bridge)
        self.assertIn("payload:sprintf('%J',b.payload)",bridge)
        self.assertNotIn('resolve',bridge)
        self.assertNotIn('system(',bridge)
        self.assertNotIn('sh(',bridge)


if __name__=='__main__': unittest.main()

"""Check the T551M engineering layout and SMS adapter without sending messages."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import runpy
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2] / 'openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem'
loader = importlib.machinery.SourceFileLoader('sms', str(ROOT / 't551m-sms'))
spec = importlib.util.spec_from_loader(loader.name, loader)
sms = importlib.util.module_from_spec(spec)
loader.exec_module(sms)


class AdaptationTest(unittest.TestCase):
    def test_lte_identity_matches_registration(self):
        script = (ROOT / 'cell').read_text()
        fragment = script[script.index('sp_fragment()'):script.index('\nnr_neighbours()')]
        fields = ['0'] * 64
        for i, value in {0:'8', 1:'3740', 2:'161', 3:'+8924', 4:'+926',
                         7:'3', 10:'94067', 11:'19', 27:'61908'}.items():
            fields[i] = value
        result = json.loads(subprocess.check_output(
            ['sh', '-c', fragment + '\nsp_fragment lte "$1"', 'test', '-'.join(fields)], text=True))
        self.assertEqual(result['enb'] * 256 + result['cid'], int('016F7313', 16))
        self.assertEqual(int(result['tac'], 16), int('F1D4', 16))
        self.assertEqual((result['band'], result['pci'], result['rsrp']), (8, 161, -89.2))
        self.assertIsNone(result['dl_bler'])
        self.assertIsNone(result['ul_bler'])

    def test_local_delete_does_not_access_sim(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sms, 'HIDDEN', Path(directory)/'hidden.json'), patch.object(sms, 'run') as run:
            self.assertEqual(sms.main('delete', {'id': '1000000001', 'sim': 0}), {'ok': 1})
            run.assert_not_called()
            self.assertEqual(sms.hidden(), {1000000001})

    def test_bulk_sim_delete_refused(self):
        with patch.object(sms, 'messages', return_value=[{'id': 1000000001}]), patch.object(sms, 'run') as run:
            with self.assertRaises(ValueError):
                sms.main('delete', {'id':'all', 'sim':1})
            run.assert_not_called()

    def test_sms_body_is_file_not_shell_code(self):
        body = '中文 "quoted" $(do-not-execute); line\nnext'
        def sent(argv, timeout):
            self.assertEqual(argv[:3], [sms.TOOL, 'send', '+123456789'])
            self.assertEqual(Path(argv[3]).read_text(), body)
            return {'ok': True}
        with patch.object(sms, 'run', side_effect=sent):
            self.assertEqual(sms.main('send', {'num': '+123456789', 'text': body})['ok'], 1)

    def test_explicit_send_card_is_preserved(self):
        with patch.object(sms, 'run', return_value={'ok': True}) as run:
            sms.main('send', {'num': '+123456789', 'text':'test', 'card':'1'})
            self.assertEqual(run.call_args.args[0][-1], '1')
        with patch.object(sms, 'run') as run:
            with self.assertRaises(ValueError):
                sms.main('send', {'num': '+123456789', 'text':'test', 'card':'2'})
            run.assert_not_called()

    def test_cleanup_preserves_shared_services_and_private_settings(self):
        cleanup = runpy.run_path(str(Path(__file__).with_name('ui-cleanup.py')))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kept = ['etc/config/e5-notify', 'etc/e5-sms/inbox.json',
                    'etc/init.d/e5-sms-notify', 'etc/init.d/e5-infoscreen',
                    'etc/init.d/unisoc-sms-forward', 'usr/libexec/unisoc-modem/sms-forward',
                    'etc/unisoc-modem/forward/config.json']
            for relative in [*kept, *cleanup['OBSOLETE']]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('preserved')
            menu = root / 'usr/share/luci/menu.d/luci-mod-status.json'
            menu.write_text(json.dumps({'admin/status/overview': {'title':'Overview'},
                                        'admin/status/logs': {'title':'Logs'}}))
            acl = root / 'usr/share/rpcd/acl.d/luci-app-e5-infoscreen.json'
            acl.parent.mkdir(parents=True)
            acl.write_text(json.dumps({'luci-app-e5-infoscreen': {'read': {}, 'write': {'uci': ['e5-infoscreen']}}}))
            cleanup['cleanup'](root)
            cleanup['cleanup'](root)
            self.assertTrue(all((root / name).read_text() == 'preserved' for name in kept))
            self.assertTrue(all(not (root / name).exists() for name in cleanup['OBSOLETE']))
            result = json.loads(menu.read_text())
            self.assertNotIn('title', result['admin/status/overview'])
            self.assertEqual(result['admin/status/logs']['title'], 'Logs')
            self.assertEqual(json.loads(acl.read_text())['luci-app-e5-infoscreen']['read']['uci'], ['e5-infoscreen'])


if __name__ == '__main__':
    unittest.main()

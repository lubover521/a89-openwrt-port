"""Native forwarding migration, replay barriers, multipart and source SIMs."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[3] / 'device/openwrt_device_common/luci-app-t551m/root/usr/libexec/unisoc-modem/forward-native'
loader = importlib.machinery.SourceFileLoader('forward_native', str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec); loader.exec_module(m)


class NativeForwardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = patch.object(m, 'BASE', self.root / 'forward'); self.base.start(); self.addCleanup(self.base.stop)
        self.inbox = patch.object(m, 'INBOX', self.root / 'inbox.json'); self.inbox.start(); self.addCleanup(self.inbox.stop)
        self.old = {'forward': {'enabled':'1','mode':'per_sim','url':'https://example.com/secret',
                               'body':'{"text":"{text}"}', 'header':['X-Test: one','Authorization: secret']},
                    'forward_sim1': {'enabled':'0','url':'https://example.com/one'},
                    'forward_sim2': {'enabled':'1','url':'https://example.com/two'}}
        with patch.object(m.time, 'time', return_value=100): m.migrate(self.old)
        self.items = [dict(id=1000000000+i,card=i,number='12345',text='验证码\n$(reboot)',
                           time='2026-10-10T10:00:00+08:00',direction='in',state='received',
                           historical=False,first_seen=101) for i in range(2)]
        self.save()

    def save(self): m.INBOX.write_text(json.dumps({'version':1,'messages':self.items}))

    def test_migration_retains_both_disabled_and_enabled_targets_and_is_idempotent(self):
        c=json.loads((m.BASE/'config.json').read_text())
        self.assertEqual(c['webhook_url'],self.old['forward']['url'])
        self.assertEqual(c['webhook_body'],self.old['forward']['body'])
        self.assertEqual(c['webhook_headers'],'X-Test: one\nAuthorization: secret')
        self.assertEqual((m.BASE/'mode').read_text().strip(),'per_sim')
        self.assertEqual(json.loads((m.BASE/'config.sim0.json').read_text())['enabled'],0)
        self.assertEqual(json.loads((m.BASE/'config.sim1.json').read_text())['enabled'],1)
        (m.BASE/'config.json').write_text('{"enabled":0}')
        m.migrate(self.old)
        self.assertEqual((m.BASE/'config.json').read_text(),'{"enabled":0}')
        self.assertEqual((m.BASE/'legacy-e5-notify.json').stat().st_mode & 0o777,0o600)

    def test_complete_messages_on_both_slots_claim_once_without_modifying_inbox(self):
        before=m.INBOX.read_bytes()
        for i,item in enumerate(self.items):
            result=m.claim(str(item['id']),100)
            self.assertEqual(result['card'],i); self.assertEqual(result['text'],item['text'])
            with self.assertRaises(ValueError): m.claim(str(item['id']),100)
        self.assertEqual(before,m.INBOX.read_bytes())
        self.assertNotIn('验证码',(m.BASE/'claimed-ids').read_text())

    def test_incomplete_old_deleted_outgoing_or_baseline_never_claim(self):
        for change in [{'state':'receiving'},{'historical':True},{'deleted':True},
                       {'direction':'out'},{'first_seen':99},{'card':2}]:
            with self.subTest(change=change):
                original=self.items[0].copy();self.items[0].update(change);self.save()
                with self.assertRaises(ValueError):m.claim('1000000000',100)
                self.assertFalse((m.BASE/'claimed-ids').exists())
                self.items[0]=original

    def test_late_multipart_completion_can_follow_a_newer_id(self):
        self.items[0]['state']='receiving';self.save()
        m.claim('1000000001',100)
        self.items[0]['state']='received';self.save()
        self.assertEqual(m.claim('1000000000',100)['id'],1000000000)

    def test_new_config_barrier_does_not_replay_old_events(self):
        with self.assertRaises(ValueError):m.claim('1000000000',102)

    def test_sms_delivery_uses_origin_slot_and_private_file(self):
        def submit(argv,**kwargs):
            self.assertEqual(argv[-1],'1')
            self.assertEqual(Path(argv[-2]).read_text(),'test body')
            self.assertNotIn('test body',' '.join(argv))
            self.assertEqual(Path(argv[-2]).stat().st_mode & 0o777,0o600)
            return type('Result',(),dict(returncode=0,stdout='{"ok":true}'))()
        with patch.dict(m.os.environ,{'MU300_SIM_SLOT':'1'}),patch.object(m.subprocess,'run',side_effect=submit):
            m.send('+861234567890','test body')


if __name__ == '__main__': unittest.main()

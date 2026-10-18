#!/usr/bin/env python3
"""Exercise untrusted uploads, retained settings and quiet audio paths offline."""
import base64
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sounds', ROOT / 'overlay/usr/lib/e5/e5_sounds.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
WAV = (ROOT / 'overlay/usr/share/e5/ding.wav').read_bytes()


class Sounds(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.settings = {t: {'enabled': False, 'tone': s.TONES[t][0]} for t in s.SECONDS}
        for name, value in [('STORE', root/'sounds'), ('RUN', root/'run'), ('CONFIG', root/'config')]:
            p = patch.object(s, name, value); p.start(); self.addCleanup(p.stop)
            value.mkdir()
        for name, func in [('setting', lambda target: dict(self.settings[target])),
                           ('configure', self.configure)]:
            p = patch.object(s, name, side_effect=func); p.start(); self.addCleanup(p.stop)

    def configure(self, target, enabled, tone):
        self.settings[target] = dict(enabled=enabled, tone=tone)

    def upload(self, data=WAV, target='sms'):
        token = ''
        for offset in range(0, len(data), s.CHUNK):
            reply = s.dispatch('upload', dict(target=target, token=token, offset=str(offset),
                              data=base64.b64encode(data[offset:offset+s.CHUNK]).decode()))
            token = reply['token']
            self.assertEqual(reply['next'], min(offset+s.CHUNK, len(data)))
        return token

    def test_upload_reset_and_independent_targets(self):
        for target in ['sms', 'ring']:
            token = self.upload(target=target)
            s.dispatch('finish', dict(target=target, token=token, name='My sound\n.wav'))
            self.assertEqual(s.resolve(target).read_bytes(), WAV)
            self.assertFalse(self.settings[target]['enabled'])
            self.assertEqual(s.custom(target)['name'], 'My sound.wav')
        s.dispatch('reset', dict(target='sms'))
        self.assertIsNone(s.custom('sms'))
        self.assertIsNotNone(s.custom('ring'))
        self.assertFalse(self.settings['sms']['enabled'])

    def test_validation_and_transaction_failure(self):
        s.dispatch('finish', dict(target='sms', token=self.upload(), name='Original'))
        original = s.resolve('sms')
        for data in [WAV[:-2], b'not audio', WAV[:24]+b'xxxx'+WAV[28:], WAV*8]:
            with self.assertRaises(ValueError): s.validate_wav(data, 'sms')
        changed = WAV[:100] + bytes([WAV[100] ^ 1]) + WAV[101:]
        token = self.upload(changed)
        with patch.object(s, 'configure', side_effect=RuntimeError('write failed')):
            with self.assertRaises(RuntimeError):
                s.dispatch('finish', dict(target='sms', token=token, name='Replacement'))
        self.assertEqual(s.resolve('sms'), original)
        self.assertEqual(s.custom('sms')['name'], 'Original')

    def test_upload_bounds_and_paths(self):
        token = self.upload()
        with self.assertRaises(ValueError): s.upload_path('sms', '../escape')
        with self.assertRaises(ValueError):
            s.dispatch('upload', dict(target='sms', token=token, offset='0', data='AAAA'))
        with self.assertRaises(ValueError):
            s.dispatch('upload', dict(target='sms', token='', offset='0', data='A'*(s.CHUNK*2)))
        self.upload()
        self.assertEqual(len(list(s.RUN.glob('upload-sms-*'))), 1)

    def test_corrupt_custom_falls_back(self):
        s.dispatch('finish', dict(target='sms', token=self.upload(), name='Test'))
        s.resolve('sms').write_bytes(b'corrupt')
        self.assertEqual(s.resolve('sms'), s.BUILTIN/'ding.wav')

    def test_silent_paths_never_start_audio(self):
        with patch.object(s, 'call_busy', return_value=True), patch.object(s.subprocess, 'Popen') as spawn:
            s.play('sms'); s.play('ring'); s.play('ring', preview=True)
            spawn.assert_not_called()
        with patch.object(s, 'call_busy', return_value=False), patch.object(s.subprocess, 'Popen') as spawn:
            s.play('sms'); s.play('ring')  # independently disabled
            self.settings['sms']['enabled'] = True
            with patch.object(s, 'cfg', return_value='0'): s.play('sms')
            spawn.assert_not_called()

    def test_incoming_call_stops_sms_but_allows_ring(self):
        with patch.object(s, 'json_read', return_value={'calls':[{'state':'ringing-in'}]}):
            self.assertTrue(s.call_busy('sms'))
            self.assertFalse(s.call_busy('ring'))
        with patch.object(s, 'json_read', return_value={'active':True}):
            self.assertTrue(s.call_busy('ring'))


if __name__ == '__main__': unittest.main()

"""Regression: CRLF inside PCM samples must not shift the audio byte stream."""
from pathlib import Path
import io
import runpy
import tempfile
import unittest
import wave

TOP = Path(__file__).resolve().parents[2]
source_bytes = runpy.run_path(str(TOP / 'device/linux_device_common/staging.py'))['source_bytes']
copy = runpy.run_path(str(TOP / 'device/openwrt_device_e5/stage.py'))['copy']


class StagingTest(unittest.TestCase):
    def test_builtin_audio_survives_shared_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('call.wav', 'beep.wav', 'ding.wav'):
                with self.subTest(name=name):
                    src = TOP / 'device/openwrt_device_common/overlay/usr/share/e5' / name
                    original = src.read_bytes()
                    if name != 'ding.wav':
                        self.assertIn(b'\r\n', original)
                    self.assertEqual(source_bytes(src), original)
                    copy(root, src, name, mode=0o644)
                    actual = (root / name).read_bytes()
                    self.assertEqual(actual, original)
                    with wave.open(io.BytesIO(actual)) as wav:
                        self.assertEqual(len(wav.readframes(wav.getnframes())),
                                         wav.getnframes() * wav.getnchannels() * wav.getsampwidth())

    def test_text_normalization_and_unknown_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'extensionless'
            for data, expected in [
                (b'#!/bin/sh\r\necho OK\r\n', b'#!/bin/sh\necho OK\n'),
                (b'\0PCM\r\n', b'\0PCM\r\n'),
                (b'\xff\r\n', b'\xff\r\n'),
            ]:
                path.write_bytes(data)
                self.assertEqual(source_bytes(path), expected)


if __name__ == '__main__':
    unittest.main()

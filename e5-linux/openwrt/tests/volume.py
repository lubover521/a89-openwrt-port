"""Check media volume routing without opening hardware or playing sound."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'overlay/usr/libexec/e5-volume'


class VolumeTest(unittest.TestCase):
    def apply(self, level, sinks, operation='apply', profile='t551m', sink='speaker'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in {
                'pidof': 'exit 0',
                'pactl': '''if [ "$1" = list ]; then printf '%s\n' "$TEST_SINKS"; elif [ "$1" = get-default-sink ]; then echo "$TEST_DEFAULT_SINK"; else printf 'pulse %s\n' "$*" >> "$TEST_LOG"; fi''',
                'amixer': '''printf 'mixer %s\n' "$*" >> "$TEST_LOG"''',
                'paplay': '''cat >/dev/null; printf 'preroll %s\n' "$*" >> "$TEST_LOG"''',
                'cat': '''if [ "$1" = /etc/e5/device-profile ]; then printf '%s\n' "$TEST_PROFILE"; else exec /bin/cat "$@"; fi''',
            }.items():
                p = root / name
                p.write_text('#!/bin/sh\n' + body + '\n')
                p.chmod(0o755)
            source = SOURCE.read_text().split('case "${1:-}" in')[0]
            script = source + '\ncard() { echo 0; }\n'+operation+' "$1"\n'
            env = dict(os.environ, PATH=str(root)+':'+os.environ['PATH'], TEST_LOG=str(root/'log'), TEST_SINKS=sinks, TEST_PROFILE=profile, TEST_DEFAULT_SINK=sink)
            subprocess.run(['sh', '-c', script, 'volume-test', str(level)], env=env, check=True)
            return (root/'log').read_text().splitlines()

    def test_speaker_and_bluetooth_share_level(self):
        lines = self.apply(5, '0\tspeaker\tmodule-alsa-sink\n1\tbluez_sink.TEST\tmodule-bluez5-device')
        self.assertIn('pulse set-sink-volume speaker 33%', lines)
        self.assertIn('pulse set-sink-volume bluez_sink.TEST 33%', lines)
        self.assertTrue(lines[-1].endswith('name=VBC DAC0 DG Set 39,39'))
        self.assertTrue(lines[0].startswith('pulse '))

    def test_mute_silences_both_pcm_and_hardware(self):
        lines = self.apply(0, '0\tspeaker\tmodule-alsa-sink')
        self.assertEqual(lines[0], 'pulse set-sink-volume speaker 0%')
        self.assertTrue(lines[-1].endswith('name=VBC DAC0 DG Set 0,0'))

    def test_direct_alsa_retains_hardware_curve(self):
        lines = self.apply(5, '')
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith('name=VBC DAC0 DG Set 19,19'))

    def test_cold_playback_resumes_before_restoring_gain(self):
        lines = self.apply(5, '0\tspeaker\tmodule-alsa-sink', 'prepare')
        self.assertEqual(lines[0], 'pulse suspend-sink speaker 0')
        self.assertEqual(lines[1], 'pulse set-sink-volume speaker 33%')
        self.assertTrue(lines[-1].endswith('name=VBC DAC0 DG Set 39,39'))

    def test_setting_volume_does_not_wake_idle_audio(self):
        lines = self.apply(5, '0\tspeaker\tmodule-alsa-sink')
        self.assertFalse(any('suspend-sink' in line for line in lines))

    def test_suspended_speaker_is_primed_silently_before_gain(self):
        for profile in ['t551m', 'e5', 'm8', 'future-board', '']:
            with self.subTest(profile=profile):
                lines = self.apply(5, '0\tspeaker\tmodule-alsa-sink\ts16le 2ch 48000Hz\tSUSPENDED', 'prepare', profile)
                self.assertEqual(lines[0], 'pulse suspend-sink speaker 0')
                self.assertTrue(lines[1].startswith('preroll --device=speaker --raw '))
                self.assertEqual(lines[2], 'pulse set-sink-volume speaker 33%')
                self.assertTrue(lines[-1].endswith('name=VBC DAC0 DG Set 39,39'))

    def test_warm_speaker_has_no_preroll(self):
        for profile in ['t551m', 'e5', 'm8', 'future-board', '']:
            with self.subTest(profile=profile):
                lines = self.apply(5, '0\tspeaker\tmodule-alsa-sink\ts16le 2ch 48000Hz\tIDLE', 'prepare', profile)
                self.assertFalse(any(line.startswith('preroll') for line in lines))

    def test_bluetooth_playback_does_not_prime_speaker(self):
        sinks = ('0\tspeaker\tmodule-alsa-sink\ts16le 2ch 48000Hz\tSUSPENDED\n'
                 '1\tbluez_sink.TEST\tmodule-bluez5-device\ts16le 2ch 48000Hz\tSUSPENDED')
        lines = self.apply(5, sinks, 'prepare', 'future-board', 'bluez_sink.TEST')
        self.assertEqual(lines[0], 'pulse suspend-sink bluez_sink.TEST 0')
        self.assertFalse(any(line.startswith('preroll') for line in lines))
        self.assertNotIn('pulse suspend-sink speaker 0', lines)

    def test_e5_retains_default_volume_curve_without_boost(self):
        sinks='0\tspeaker\tmodule-alsa-sink\n1\tbluez_sink.TEST\tmodule-bluez5-device'
        for level, percent in [(0,0),(5,33),(13,86),(14,93),(15,100)]:
            with self.subTest(level=level):
                lines=self.apply(level,sinks,profile='e5')
                gain=39 if level else 0
                self.assertTrue(lines[-1].endswith(f'name=VBC DAC0 DG Set {gain},{gain}'))
                self.assertIn(f'pulse set-sink-volume speaker {percent}%',lines)
                self.assertFalse(any('AO Gain' in line for line in lines))
                self.assertIn(f'pulse set-sink-volume bluez_sink.TEST {level*100//15}%',lines)
        for profile in ['t551m','unknown','']:
            lines=self.apply(15,sinks,profile=profile)
            self.assertTrue(lines[-1].endswith('name=VBC DAC0 DG Set 39,39'))
            self.assertIn('pulse set-sink-volume speaker 100%',lines)
            self.assertFalse(any('AO Gain' in line for line in lines))

    def test_e5_direct_alsa_ceiling_and_mute(self):
        for level,gain in [(0,0),(5,19),(13,35),(14,37),(15,39)]:
            with self.subTest(level=level):
                self.assertTrue(self.apply(level,'',profile='e5')[-1].endswith(f'name=VBC DAC0 DG Set {gain},{gain}'))

    def test_media_apply_never_overwrites_voice_codec_gain(self):
        lines=self.apply(15,'0\tspeaker\tmodule-alsa-sink',profile='e5')
        self.assertFalse(any('AO Gain' in line for line in lines))


if __name__ == '__main__':
    unittest.main()

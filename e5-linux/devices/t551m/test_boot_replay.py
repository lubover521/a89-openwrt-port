"""Exercise startup ordering and early-only replay without a modem."""
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[2]
BOOT = TOP / 'openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/boot-replay'
patch_root = runpy.run_path(str(Path(__file__).with_name('network-startup.py')))['patch_root']

class BootReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.trace = self.root / 'trace'
        self.state = self.root / 'state';self.state.mkdir()
        (self.state/'mode').write_text('4g')
        self.env = dict(os.environ, TEST_STATE=str(self.state), TRACE=str(self.trace),
                        UNISOC_REPLAY_MARKER=str(self.root/'done'), PATH=str(self.root)+':'+os.environ['PATH'])
        self.script('uci', 'case "$*" in *state_dir) echo "$TEST_STATE";; *replay_timeout) echo 2;; esac')
        self.script('logger', 'echo "$*" >> "$TRACE"')
        self.script('at', 'echo AT >> "$TRACE"; echo OK')
        self.script('mmcli', 'echo "modem.generic.state : connected"')
        self.script('lock', 'echo "lock:$*" >> "$TRACE"; [ "$1" != replay ] || touch "$UNISOC_REPLAY_MARKER"; echo \'{"ok":1}\'')
        self.env.update(UNISOC_AT_BIN=str(self.root/'at'), UNISOC_LOCK_BIN=str(self.root/'lock'))

    def script(self, name, body):
        path=self.root/name;path.write_text('#!/bin/sh\n'+body+'\n');path.chmod(0o755)

    def run_boot(self, stage):
        return subprocess.run(['sh',str(BOOT),stage],env=self.env,capture_output=True,text=True,timeout=8)

    def test_early_before_verification_and_once_per_boot(self):
        self.assertEqual(self.run_boot('early').returncode,0)
        self.assertEqual(self.run_boot('early').returncode,0)
        self.assertEqual(self.run_boot('verify').returncode,0)
        trace=self.trace.read_text()
        self.assertEqual(trace.count('lock:replay early'),1)
        self.assertIn('lock:verify',trace)
        self.assertNotIn('replay late',trace)

    def test_disabled_switch_generates_no_at_traffic(self):
        (self.state/'auto_apply').write_text('off')
        self.assertEqual(self.run_boot('early').returncode,0)
        self.assertFalse(self.trace.exists())

    def test_only_secondary_saved_settings_still_replay_early(self):
        (self.state/'mode').unlink()
        (self.state/'sim1').mkdir();(self.state/'sim1/mode').write_text('4g')
        self.assertEqual(self.run_boot('early').returncode,0)
        self.assertIn('lock:replay early',self.trace.read_text())

    def test_empty_unlock_is_still_a_saved_setting(self):
        (self.state/'mode').unlink()
        (self.state/'sim1').mkdir()
        (self.state/'sim1/nr').write_text('')
        self.assertEqual(self.run_boot('early').returncode,0)
        self.assertIn('lock:replay early',self.trace.read_text())

    def test_voice_only_saved_setting_starts_pre_dial_replay(self):
        (self.state/'mode').unlink()
        (self.state/'sim1').mkdir()
        for kind in ('volte', 'vonr'):
            with self.subTest(kind=kind):
                path = self.state/'sim1'/kind;path.write_text('off')
                attempt = Path(self.env['UNISOC_REPLAY_MARKER']+'-attempted')
                if attempt.exists(): attempt.rmdir()
                Path(self.env['UNISOC_REPLAY_MARKER']).unlink(missing_ok=True)
                self.trace.unlink(missing_ok=True)
                self.assertEqual(self.run_boot('early').returncode,0)
                self.assertIn('lock:replay early',self.trace.read_text())
                path.unlink()

    def test_removed_ims_alone_never_starts_replay(self):
        (self.state/'mode').unlink()
        (self.state/'ims').write_text('off')
        (self.state/'sim1').mkdir()
        (self.state/'sim1/ims').write_text('on')
        self.assertEqual(self.run_boot('early').returncode, 0)
        self.assertFalse(self.trace.exists())

    def test_migrated_legacy_settings_do_not_override_disabled_slots(self):
        (self.state/'.per-sim-migrated').touch()
        for slot in ('sim0','sim1'):
            (self.state/slot).mkdir()
            (self.state/slot/'mode').write_text('4g')
            (self.state/slot/'auto_apply').write_text('off')
        self.assertEqual(self.run_boot('early').returncode,0)
        self.assertEqual(self.run_boot('verify').returncode,0)
        self.assertFalse(self.trace.exists())

    def test_failed_early_replay_is_not_retried_late(self):
        self.script('lock', 'echo "lock:$*" >> "$TRACE"; exit 1')
        self.assertEqual(self.run_boot('early').returncode,1)
        self.assertEqual(self.run_boot('early').returncode,0)
        self.assertEqual(self.run_boot('verify').returncode,1)
        self.assertEqual(self.trace.read_text().count('lock:replay early'),1)

    def test_wrapper_hook_precedes_modem_process_and_is_idempotent(self):
        path=self.root/'usr/sbin/ModemManager-wrapper';path.parent.mkdir(parents=True)
        path.write_text('#!/bin/sh\nmain() {\n\t/usr/sbin/ModemManager "$@" 1>/dev/null 2>/dev/null &\n\tmm_report_events_from_cache\n}\nmain "$@"\n')
        patch_root(self.root);text=path.read_text();patch_root(self.root)
        self.assertEqual(path.read_text(),text)
        self.assertLess(text.index('boot-replay early'),text.index('/usr/sbin/ModemManager "$@"'))
        subprocess.run(['sh','-n',str(path)],check=True)

if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Exercise the real initramfs handoff barrier with a delayed mock radio."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

INIT = (Path(__file__).resolve().parents[1] / 'init').read_text()
FUNCTION = INIT[INIT.index('early_wcn_ready() {'):INIT.index('\nloaded=0\n')]


class Handoff(unittest.TestCase):
    def boot(self, *, modules=True, ready_after=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if modules:
                for name in ['wcn_bsp', 'sprd_wlan_combo']:
                    (root / 'sys/module' / name).mkdir(parents=True)
            if ready_after == 0:
                (root / 'sys/class/ieee80211/phy0').mkdir(parents=True)
            script = FUNCTION.replace('/sys/', directory + '/sys/') + '''
log() { echo "$*"; }
ticks=0
sleep() {
    ticks=$((ticks + 1))
    [ "$ticks" != "$READY_AFTER" ] || mkdir -p "$ROOT/sys/class/ieee80211/phy0"
    return 0
}
early_wcn_ready
echo "switch-root ticks=$ticks"
'''
            return subprocess.check_output([shutil.which('busybox'), 'sh', '-c', script],
                env=dict(os.environ, ROOT=directory, READY_AFTER=str(ready_after)),
                text=True, timeout=5)

    def test_download_finishes_before_switch_root(self):
        trace = self.boot(ready_after=3)
        self.assertIn('stage=wcn-handoff-ready waited=3s\nswitch-root ticks=3', trace)

    def test_already_ready_has_no_delay(self):
        self.assertIn('stage=wcn-handoff-ready waited=0s\nswitch-root ticks=0', self.boot())

    def test_no_wcn_modules_has_no_delay(self):
        self.assertEqual(self.boot(modules=False, ready_after=-1), 'switch-root ticks=0\n')

    def test_broken_radio_cannot_block_boot_forever(self):
        self.assertIn('stage=wcn-handoff-timeout waited=15s\nswitch-root ticks=15', self.boot(ready_after=-1))

    def test_deadline_readiness_is_accepted(self):
        self.assertIn('stage=wcn-handoff-ready waited=15s', self.boot(ready_after=15))

    def test_barrier_precedes_process_cleanup_and_switch(self):
        call = INIT.index('\n    early_wcn_ready\n')
        kill = INIT.index('    kill $persist_job $timer_job', call)
        switch = INIT.index('    exec switch_root /newroot $init', kill)
        self.assertLess(call, kill)
        self.assertLess(kill, switch)


if __name__ == '__main__':
    unittest.main()

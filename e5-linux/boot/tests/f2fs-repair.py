#!/usr/bin/env python3
"""Exercise the actual init shell policy with fake block devices and fsck.

No real device, partition or mount is modified. Requires BusyBox on Linux.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

BOOT = Path(__file__).resolve().parents[1]
INIT = (BOOT/'init').read_text()
REPAIR = (BOOT/'f2fs-repair.sh').read_text()
MOUNT = INIT[INIT.index('mount_userdata_root() {'):INIT.index('\nrootdir= data_mounted= on_card=')]

class Recovery(unittest.TestCase):
    def run_case(self, mode='repair', mounted=False, part='userdata', holder=False, repeat=False, verify_fail=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def write(name, text, executable=False):
                p=root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text)
                if executable:p.chmod(0o755)
            write('dev/mmcblk0p70','')
            write('sys/class/block/mmcblk0p70/uevent','PARTNAME='+part+'\n')
            write('sys/class/block/mmcblk0p70/dev','179:70\n')
            (root/'sys/class/block/mmcblk0p70/holders').mkdir()
            if holder:write('sys/class/block/mmcblk0p70/holders/loop0','')
            write('proc/self/mountinfo','1 0 179:70 / /elsewhere rw - f2fs /dev/alias rw\n' if mounted else '')
            (root/'run').mkdir()
            write('repair/sbin/fsck.f2fs','#!/bin/sh\n',True)
            write('repair/lib/ld-musl-aarch64.so.1', '''#!/bin/sh
echo "fsck $*" >> "$ROOT/trace"
n=$(cat "$ROOT/count" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$ROOT/count"
if [ "$MODE" = orphan ] || [ "$MODE" = extra-prompt ]; then
    # The real tool's optional lost_found export ignores -f, -y and dry-run.
    read -r answer || { echo '[ASSERT] scanf EOF'; exit 255; }
    echo "export-answer:$answer" >> "$ROOT/trace"
    [ "$answer" = n ] || { echo 'unexpected orphan export'; exit 8; }
    if [ "$MODE" = extra-prompt ]; then
        read -r answer || { echo '[ASSERT] unexpected second prompt'; exit 255; }
    fi
fi
case "$MODE:$n" in clean:1) exit 0;; operation:1) exit 8;; verify:3) echo '[Fail]'; exit 4;; esac
case "$n" in 1|2) exit 1;; *) exit 0;; esac
''',True)
            def redirect(code):
                return re.sub(r'(?<![\w./-])/(dev|sys|proc|run|repair|etc)(?=/)',
                              lambda m: folder+m[0],code).replace('[ -b ', '[ -e ')
            write('etc/f2fs-repair.sh',redirect(REPAIR))
            harness = '''
log() { echo "$*" >> "$ROOT/trace"; }
blockdev() { [ "$1" != --getro ] || echo 0; echo "$*" >> "$ROOT/trace"; }
od() { echo f2f52010; }
mount() { echo mount >> "$ROOT/trace"; [ "$MODE" = mounted-ok ]; }
write_misc_bc() { echo rearm >> "$ROOT/trace"; }
sync() { :; }
persist() { :; }
reboot() { echo reboot >> "$ROOT/trace"; exit 0; }
data="$ROOT/dev/mmcblk0p70"
'''+redirect(MOUNT)+'\nmount_userdata_root\n'
            if repeat:harness+='mount_userdata_root\n'
            subprocess.run([shutil.which('busybox'),'sh','-c',harness],
                           env=dict(os.environ,ROOT=folder,MODE='verify' if verify_fail else mode),timeout=5)
            return (root/'trace').read_text()

    def test_healthy_mount_has_no_fsck_or_reboot(self):
        self.assertEqual(self.run_case('mounted-ok'),'mount\n')
    def test_orphan_export_prompt_has_an_answer_in_all_three_passes(self):
        trace=self.run_case('orphan')
        self.assertEqual(trace.count('export-answer:n'),3)
        self.assertTrue(trace.endswith('rearm\nreboot\n'))
    def test_unexpected_additional_prompt_still_aborts_without_repair(self):
        trace=self.run_case('extra-prompt',repeat=True)
        self.assertEqual(trace.count('fsck '),1)
        self.assertIn('stage=f2fs-check-result rc=255',trace)
        self.assertNotIn('stage=f2fs-repair dev=',trace)
        self.assertNotIn('reboot',trace)
    def test_repair_checks_then_verifies_before_reboot(self):
        trace=self.run_case()
        calls=[s for s in trace.splitlines() if s.startswith('fsck ')]
        self.assertEqual(len(calls),3)
        self.assertIn('--dry-run',calls[0]);self.assertNotIn('--dry-run',calls[1]);self.assertIn('--dry-run',calls[2])
        self.assertTrue(trace.endswith('rearm\nreboot\n'))
    def test_mounted_alias_wrong_partition_and_holders_never_repaired(self):
        for opts in [dict(mounted=True),dict(part='nr_fixnv1'),dict(holder=True)]:
            self.assertNotIn('fsck ',self.run_case(**opts))
    def test_clean_or_operational_error_does_not_write(self):
        for mode in ['clean','operation']:
            trace=self.run_case(mode,repeat=True)
            self.assertEqual(trace.count('fsck '),1)
            self.assertNotIn('reboot',trace)
    def test_bad_verification_cannot_reboot_or_mount_again(self):
        trace=self.run_case(verify_fail=True,repeat=True)
        self.assertEqual(trace.count('fsck '),3)
        self.assertNotIn('reboot',trace)
    def test_tf_and_early_probes_cannot_call_repair(self):
        # The only call site is the userdata branch after the TF branch.
        self.assertEqual(INIT.count('&& mount_userdata_root; then'),1)
        before, after=INIT.split('&& mount_userdata_root; then')
        self.assertIn('log "stage=card-system userdata read-only"',before)
        early=INIT[INIT.index('early_userdata_firmware()'):INIT.index('\nloaded=0')]
        self.assertNotIn('f2fs_repair',early)
        self.assertIn('[ -z "$SDMETA" ] && [ -z "$SDMETA_INVALID" ]',before[-130:])

if __name__=='__main__':unittest.main()

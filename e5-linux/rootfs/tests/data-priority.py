#!/usr/bin/env python3
"""Offline policy, build-hook and all-board staging regressions. Run in Linux/WSL."""
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

TOP = Path(__file__).resolve().parents[2]
WORKER = TOP / 'rootfs/overlay/opt/e5/e5-data-priority'


class Policy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='e5-policy-')
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.worker = self.bin / 'worker'
        self.worker.write_bytes(WORKER.read_bytes())
        self.worker.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        E5_DATA_PRIORITY_DIR=str(self.root / 'state'),
                        E5_DATA_PRIORITY_CLIENT=str(self.bin / 'client'), TEST_ROOT=str(self.root))
        self.stub('logger', 'printf "%s\\n" "$*" >> "$TEST_ROOT/log"')
        self.stub('sleep', 'echo "$*" >> "$TEST_ROOT/sleeps"')
        self.stub('client', r'''
cmd=$3
printf '%s|%s|%s\n' "$cmd" "$T551M_AT_CHANNEL" "$2" >> "$TEST_ROOT/commands"
case "$cmd" in *CEUS=1)
    if [ "${HOLD:-0}" = 1 ]; then
        touch "$TEST_ROOT/started"
        n=0
        while [ ! -e "$TEST_ROOT/release" ] && [ "$n" -lt 100 ]; do
            /bin/sleep 0.05; n=$((n+1))
        done
    fi ;;
esac
fail=0
case "$cmd" in *"${FAIL_CMD:-never-match}"*) fail=1 ;; esac
[ "${FAIL_CMD:-}" != all ] || fail=1
count=$(grep -Fc "$cmd|" "$TEST_ROOT/commands")
if [ -n "${FAIL_FIRST:-}" ] && [ "$count" -gt "$FAIL_FIRST" ]; then fail=0; fi
echo finished >> "$TEST_ROOT/finished"
if [ "$fail" = 1 ]; then
    case "$FAIL_MODE" in
        error) echo ERROR ;;
        cme) echo '+CME ERROR: 3' ;;
        mixed) printf 'OK\n+CMS ERROR: 500\n' ;;
        stale) printf 'OK\npartial\n' ;;
        empty) : ;;
        transport) echo OK; exit 1 ;;
    esac
else printf '\r\nOK\r\n'; fi
''')

    def tearDown(self):
        self.temp.cleanup()

    def stub(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)

    def run_worker(self, mode='run', slot='0', shell='dash', **env):
        return subprocess.run([shell, str(self.worker), mode, slot], env=dict(self.env, **env),
                              capture_output=True, text=True, timeout=10)

    def reset(self):
        for name in ('commands', 'log', 'sleeps'):
            (self.root / name).write_text('')

    def commands(self):
        return (self.root / 'commands').read_text().splitlines()

    def wait(self, predicate):
        end = time.monotonic() + 4
        while time.monotonic() < end:
            if predicate(): return
            time.sleep(0.02)
        self.fail('worker did not reach expected state')

    def test_ok_stops_retries_and_routes_each_card_on_secondary_owner(self):
        for shell in ('dash', 'bash'):
            for slot in ('0', '1'):
                for failures in range(4):
                    self.reset()
                    r = self.run_worker(slot=slot, shell=shell, FAIL_CMD='all',
                                        FAIL_MODE='error', FAIL_FIRST=str(failures))
                    self.assertEqual(r.returncode, 0, r.stderr)
                    expected = []
                    for cmd in ('+CEUS=1', '+CEMODE=2'):
                        expected += [f'AT+SPACTCARD={slot};{cmd}|2|3'] * (failures + 1)
                    self.assertEqual(self.commands(), expected)
                    self.assertIn('both confirmed OK', (self.root / 'log').read_text())
                    self.assertEqual(len((self.root / 'sleeps').read_text().splitlines()), failures * 2)

    def test_failure_exhaustion_does_not_skip_next_command_or_claim_success(self):
        for shell in ('dash', 'bash'):
            for mode in ('error', 'cme', 'mixed', 'stale', 'empty', 'transport'):
                for cmd in ('CEUS=1', 'CEMODE=2', 'all'):
                    self.reset()
                    r = self.run_worker(shell=shell, FAIL_CMD=cmd, FAIL_MODE=mode)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    expected = []
                    for at in ('CEUS=1', 'CEMODE=2'):
                        expected += [at] * (4 if cmd in (at, 'all') else 1)
                    self.assertEqual([s.split(';+')[1].split('|')[0] for s in self.commands()], expected)
                    log = (self.root / 'log').read_text()
                    self.assertIn('exhausted 3 retries', log)
                    self.assertNotIn('both confirmed OK', log)

    def test_async_and_nonblocking_singleton_then_reapply(self):
        self.reset()
        try:
            r = self.run_worker('queue', HOLD='1', FAIL_CMD='all', FAIL_MODE='transport')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.wait(lambda: (self.root / 'started').exists())
            self.assertFalse((self.root / 'finished').exists())
            self.assertEqual(self.run_worker().returncode, 0)
            self.assertEqual(len(self.commands()), 1)  # no parallel duplicate worker
        finally:
            (self.root / 'release').touch()
            self.wait(lambda: 'continuing without blocking dialing' in (self.root / 'log').read_text()
                      and len(self.commands()) == 8)
            # Wait for the final log + flock release, without arbitrary fixed sleep.
            lock = self.root / 'state/slot0.lock'
            self.wait(lambda: subprocess.run(['flock', '-n', str(lock), 'true']).returncode == 0)
        self.assertEqual(self.run_worker().returncode, 0)
        self.assertEqual(len(self.commands()), 10)  # no permanent boot-done marker

    def test_spawn_failure_and_invalid_slot(self):
        self.stub('setsid', 'exit 1')
        self.assertEqual(self.run_worker('queue').returncode, 0)
        self.assertEqual(self.run_worker(slot='2').returncode, 2)

    def test_daemon_absence_never_opens_tty(self):
        self.reset()
        r = self.run_worker(E5_DATA_PRIORITY_CLIENT=str(self.root / 'nonexistent'))
        self.assertEqual(r.returncode, 0)
        self.assertNotIn('both confirmed OK', (self.root / 'log').read_text())
        source = WORKER.read_text()
        self.assertNotIn('/dev/stty', source)
        self.assertNotIn('SFUN=', source)


class Integration(unittest.TestCase):
    def test_all_modem_patches_apply_and_actual_callbacks_compile(self):
        with tempfile.TemporaryDirectory(prefix='e5-mm-policy-') as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            for patchfile in sorted((TOP / 'rootfs/deb-patches').glob('modemmanager-*.patch')):
                result = subprocess.run(['git', 'apply', '--include=src/plugins/unisoc/mm-broadband-modem-unisoc.c',
                                         str(patchfile)], cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, str(patchfile) + ': ' + result.stderr)
            subprocess.run(['python3', str(TOP / 'openwrt/tests/data-priority-hook.py'),
                            str(root / 'src')], check=True)

    def test_supported_profiles_stage_the_executable_worker(self):
        stage = runpy.run_path(str(TOP / 'devices/t551m/ui.py'))['stage']
        stage.__globals__['PACKAGES'] = {}  # no package downloads in isolated tests
        original_run = runpy.run_path

        def isolated_run(path):
            path = Path(path)
            if path.name == 'build-at-client.py': return {'build': lambda: Path('/bin/true')}
            if path.name == 'ui-cleanup.py': return {'cleanup': lambda root: None}
            if path.parent.name == 'infoscreen': return {'stage': lambda root: None}
            return original_run(str(path))

        with tempfile.TemporaryDirectory(prefix='e5-policy-stage-') as directory:
            for profile in ('e5', 't551m'):
                root = Path(directory) / profile
                root.mkdir()
                with patch.dict(os.environ, E5_UI_CACHE=str(Path(directory) / 'cache')), \
                     patch('runpy.run_path', side_effect=isolated_run):
                    stage(root, profile)
                worker = root / 'opt/e5/e5-data-priority'
                self.assertEqual(worker.read_bytes(), WORKER.read_bytes())
                self.assertEqual(worker.stat().st_mode & 0o777, 0o755)
        self.assertIn('profile=\'e5\'', (TOP / 'devices/e5/stage.py').read_text())

    def test_base_images_include_worker_and_reject_stale_mm_package(self):
        build = (TOP / 'openwrt/build-rootfs.sh').read_text()
        self.assertIn('e5-at e5-data-priority e5-audio-dsp', build)
        self.assertIn('openwrt-package-state.py" check "$VER"', build)
        self.assertIn('"$HERE/overlay"/*', (TOP / 'rootfs/configure-rootfs.sh').read_text())
        self.assertIn('/opt/e5/e5-data-priority queue 0',
                      (TOP / 'rootfs/overlay/opt/e5/mobile-data').read_text())


if __name__ == '__main__':
    unittest.main()

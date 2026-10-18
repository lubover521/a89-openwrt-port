#!/usr/bin/env python3
"""Exercise the actual shared installer lock with BusyBox ash (Linux, root)."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def block(name):
    text = (ROOT / 'openwrt' / name).read_text()
    return text.split('# BEGIN e5-upgrade-lock\n')[1].split('# END e5-upgrade-lock')[0]


class UpgradeLock(unittest.TestCase):
    def test_lock_lifetime_and_unsafe_paths(self):
        code = block('device-install-image.sh')
        self.assertEqual(code, block('device-install.sh'))
        with tempfile.TemporaryDirectory() as temp:
            lockdir = Path(temp) / 'lockdir'
            code = 'set -eu\n' + code.replace('/run/e5-upgrade', str(lockdir))
            def run(extra='echo entered'):
                return subprocess.run(['busybox', 'sh', '-c', code + extra], text=True, capture_output=True)
            # A holder survives until its process exits, including on SIGKILL.
            holder = subprocess.Popen(['busybox', 'sh', '-c', code + 'echo ready\nread -r done'],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(holder.stdout.readline().strip(), 'ready')
                other = run()
                self.assertNotEqual(other.returncode, 0)
                self.assertIn('another system upgrade', other.stderr)
                self.assertNotIn('entered', other.stdout)
            finally:
                holder.kill()
                holder.wait()
                holder.stdin.close()
                holder.stdout.close()
            self.assertEqual(run().stdout.strip(), 'entered')
            inode = (lockdir / 'lock').stat().st_ino
            self.assertEqual(run().returncode, 0)
            self.assertEqual((lockdir / 'lock').stat().st_ino, inode)
            # Refuse symlinks and world-writable runtime dirs before writes.
            (lockdir / 'lock').unlink()
            target = Path(temp) / 'target'
            target.write_text('unchanged')
            (lockdir / 'lock').symlink_to(target)
            self.assertIn('unsafe upgrade lock file', run().stderr)
            self.assertEqual(target.read_text(), 'unchanged')
            (lockdir / 'lock').unlink()
            lockdir.chmod(0o777)
            self.assertIn('unsafe upgrade lock directory', run().stderr)
            lockdir.rmdir()
            lockdir.symlink_to(temp)
            self.assertIn('unsafe upgrade lock directory', run().stderr)
            lockdir.unlink()
            # Missing flock fails closed, without starting an upgrade.
            fail = subprocess.run(['busybox', 'sh', '-c',
                'command() { return 1; }\n' + code], text=True, capture_output=True)
            self.assertNotEqual(fail.returncode, 0)
            self.assertIn('flock is required', fail.stderr)


if __name__ == '__main__':
    if os.geteuid() != 0:
        raise SystemExit('Run as root in an isolated Linux test environment')
    unittest.main()

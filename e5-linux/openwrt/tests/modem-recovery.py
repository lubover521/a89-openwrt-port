#!/usr/bin/env python3
"""Real C daemon + private abstract sockets; never opens a modem/AT/NV node."""
import contextlib
import os
from pathlib import Path
import runpy
import select
import socket
import subprocess
import tempfile
import time
import unittest
import uuid

TOP = Path(__file__).resolve().parents[2]
ACK = b'SLOGMODEM DUMP COMPLETE\0'
ALERTS = (b'Modem Assert', b'Modem State: Assert', b'Modem Blocked', b'Modem State: Blocked')


@unittest.skipUnless(os.name == 'posix', 'Run the Linux abstract-socket fixture in WSL')
class Daemon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='modem-recovery-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.binary = Path(cls.temp.name) / 'modemd'
        cls.name = 'e5-recovery-test-' + uuid.uuid4().hex
        subprocess.run(['cc', '-std=gnu99', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-DSOCKET_NAME="' + cls.name + '"',
                        str(TOP / 'openwrt/src/e5-modemd.c'), '-o', str(cls.binary)], check=True)

    @contextlib.contextmanager
    def client(self, *args):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind('\0' + self.name); server.listen(1); server.settimeout(3)
            process = subprocess.Popen([str(self.binary), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(2)
                    yield process, connection
            finally:
                if process.poll() is None: process.terminate()
                process.communicate(timeout=3)

    def receive(self, connection, count=1):
        data = b''
        while len(data) < len(ACK) * count:
            part = connection.recv(4096)
            self.assertTrue(part, 'Client disconnected before acknowledgement')
            data += part
        self.assertEqual(data, ACK * count)

    def test_normal_startup_is_passive_and_idle(self):
        with self.client() as (process, connection):
            connection.sendall(b'Modem Alive\0CH Alive\0Modem Reset\0Modem State: Ready\0Modem State: Alive\0Modem State: Reset\0Assert policy disabled\0')
            self.assertFalse(select.select([connection], [], [], .15)[0], 'Healthy boot sent a command')
            self.assertIsNone(process.poll())

    def test_complete_assert_and_late_assert_snapshot(self):
        for event in ALERTS:
            with self.subTest(event=event), self.client() as (_, connection):
                connection.sendall(event + b': reason\0')
                self.receive(connection)

    def test_every_split_of_all_alert_prefixes(self):
        with self.client() as (_, connection):
            for event in ALERTS:
                for split in range(1, len(event)):
                    with self.subTest(event=event, split=split):
                        connection.sendall(event[:split])
                        self.assertFalse(select.select([connection], [], [], .01)[0])
                        connection.sendall(event[split:] + b'\0')
                        self.receive(connection)

    def test_coalesced_and_unterminated_vendor_messages(self):
        with self.client() as (_, connection):
            connection.sendall(b'Modem Alive\0Modem Assert: RF path failed\0Modem Reset\0Modem Blocked\0')
            self.receive(connection, 2)
            # Existing vendors need not wait for a NUL to start recovery.
            connection.sendall(b'Modem State: As')
            time.sleep(.01)
            connection.sendall(b'sert')
            self.receive(connection)

    def test_large_reason_and_subsequent_assert_are_bounded(self):
        with self.client() as (_, connection):
            connection.sendall(b'Modem Assert: ' + b'x' * 65536 + b'\0Modem State: Assert\0')
            self.receive(connection, 2)

    def test_recovery_never_triggers_the_manual_blocked_command(self):
        with self.client('blocked') as (process, connection):
            data = connection.recv(4096)
            self.assertEqual(data, b'Modem Blocked\0')
            self.assertEqual(process.wait(timeout=2), 0)

    def test_socket_close_exits_for_procd_respawn_and_new_connection_works(self):
        with self.client() as (process, connection):
            connection.shutdown(socket.SHUT_RDWR)
            self.assertEqual(process.wait(timeout=2), 1)
        with self.client() as (_, connection):
            connection.sendall(b'Modem State: Assert\0')
            self.receive(connection)

    def test_server_can_appear_after_the_helper(self):
        process = subprocess.Popen([str(self.binary)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(.05)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind('\0' + self.name); server.listen(1); server.settimeout(3)
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(2); connection.sendall(b'Modem Assert\0')
                    self.receive(connection)
        finally:
            if process.poll() is None: process.terminate()
            process.communicate(timeout=3)


@unittest.skipUnless(os.name == 'posix', 'Offline root symlinks run in WSL')
class Staging(unittest.TestCase):
    def test_common_stage_is_idempotent_and_preserves_radio_inputs(self):
        stage = runpy.run_path(str(TOP / 'devices/modem-recovery.py'))['stage']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protected = {'etc/config/e5-sim': b'keep SIM selection',
                         'usr/libexec/unisoc-modem/boot-replay': b'keep replay sequence',
                         'opt/e5/android/vendor/bin/modem_control': b'keep vendor runtime',
                         'etc/unisoc-modem/lock-state.d/mode': b'keep user mode'}
            for name, data in protected.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            for _ in range(2):
                stage(root)
                for name, data in protected.items(): self.assertEqual((root / name).read_bytes(), data)
                for name in ('S22e5-modemd', 'K09e5-modemd'):
                    link = root / 'etc/rc.d' / name
                    self.assertEqual(os.readlink(link), '../init.d/e5-modemd')
                    self.assertTrue(link.is_file())
                self.assertTrue((root / 'etc/init.d/e5-modemd').stat().st_mode & 0o111)

    def test_foreign_service_link_is_rejected_without_overwriting(self):
        stage = runpy.run_path(str(TOP / 'devices/modem-recovery.py'))['stage']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'etc/rc.d').mkdir(parents=True)
            link = root / 'etc/rc.d/S22e5-modemd'; link.symlink_to('../init.d/foreign')
            with self.assertRaises(ValueError): stage(root)
            self.assertEqual(os.readlink(link), '../init.d/foreign')
            self.assertFalse((root / 'etc/init.d/e5-modemd').exists())


if __name__ == '__main__': unittest.main()

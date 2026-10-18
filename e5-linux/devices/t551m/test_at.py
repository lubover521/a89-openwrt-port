"""Real PTY tests for framing, late replies and timeout quarantine (no modem)."""
import importlib.util
import os
from pathlib import Path
import pty
import select
import threading
import time
import tty
import unittest

spec = importlib.util.spec_from_file_location('atd', Path(__file__).with_name('atd.py'))
atd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atd)


class TransportTest(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = pty.openpty()
        tty.setraw(self.slave)
        self.channel = atd.Channel(self.slave, gap=0)

    def tearDown(self):
        os.close(self.master)
        os.close(self.slave)

    def modem(self, response):
        def reply():
            request = os.read(self.master, 1024)
            self.assertTrue(request.endswith(b'\r'))
            for part in response:
                os.write(self.master, part)
                time.sleep(0.01)
        thread = threading.Thread(target=reply)
        thread.start()
        return thread

    def test_fragmented_registration_and_final(self):
        thread = self.modem([b'\r\n+CERE', b'G: 2,1,"1234","5678",7\r\nO', b'K\r\n'])
        answer = self.channel.command('AT+CEREG?', 1)
        thread.join()
        self.assertIn('+CEREG: 2,1', answer)
        self.assertTrue(answer.endswith('OK\n'))

    def test_error_is_complete_response(self):
        thread = self.modem([b'\r\n+CME ERROR: 10\r\n'])
        self.assertIn('ERROR: 10', self.channel.command('AT+CPIN?', 1))
        thread.join()
        self.assertTrue(self.channel.synchronized)

    def test_late_reply_never_becomes_next_reply(self):
        with self.assertRaises(TimeoutError):
            self.channel.command('AT+SLOW?', 0.03)
        os.read(self.master, 1024)
        with self.assertRaises(TimeoutError):
            self.channel.command('AT+NEXT?', 0.03)
        self.assertFalse(select.select([self.master], [], [], 0)[0])
        os.write(self.master, b'+SLOW: old\r\nOK\r\n')
        thread = self.modem([b'+NEXT: new\r\nOK\r\n'])
        answer = self.channel.command('AT+NEXT?', 1)
        thread.join()
        self.assertNotIn('old', answer)
        self.assertIn('new', answer)

    def test_success_has_no_one_second_drain_tax(self):
        thread = self.modem([b'OK\r\n'])
        start = time.monotonic()
        self.channel.command('AT', 1)
        thread.join()
        self.assertLess(time.monotonic() - start, 0.5)

    def test_recovery_requires_two_named_replies_and_never_retries_write(self):
        self.channel.synchronized = False
        self.channel.failed_at = time.monotonic() - 3
        sent = []
        def responder():
            sent.append(os.read(self.master, 1024))
            os.write(self.master, b'OK\r\n+OLD: late\r\n+CFUN: 1\r\nOK\r\n')
            sent.append(os.read(self.master, 1024))
            os.write(self.master, b'OK\r\n+CSQ: 20,99\r\nOK\r\n')
        thread = threading.Thread(target=responder);thread.start()
        self.channel.recover();thread.join()
        self.assertTrue(self.channel.synchronized)
        self.assertEqual(sent, [b'AT+CFUN?\r', b'AT+CSQ\r'])

    def test_recovery_does_not_probe_a_recent_pending_command(self):
        self.channel.synchronized = False
        self.channel.failed_at = time.monotonic()
        with self.assertRaises(TimeoutError): self.channel.recover()
        self.assertFalse(select.select([self.master], [], [], 0)[0])

    def test_recovery_bare_ok_does_not_unlock_channel(self):
        self.channel.synchronized = False
        self.channel.failed_at = time.monotonic() - 3
        thread = self.modem([b'OK\r\n'])
        with self.assertRaises(TimeoutError): self.channel.recover()
        thread.join()
        self.assertFalse(self.channel.synchronized)

    def test_control_characters_and_expired_writes_rejected(self):
        for command, deadline in [('AT\rAT+CFUN=0', time.monotonic() + 5),
                                  ('AT+CFUN=0', time.monotonic() - 1)]:
            with self.assertRaises(ValueError):
                atd.validate(dict(command=command, deadline=deadline))

    def test_card_is_explicit_per_command(self):
        self.assertEqual(atd.address_card('AT+CEREG?', 1), 'AT+SPACTCARD=1;+CEREG?')
        self.assertEqual(atd.address_card('AT+SPACTCARD=0;+CIMI', 1), 'AT+SPACTCARD=0;+CIMI')

    def test_channel_directories_are_independent_and_reserved_rings_rejected(self):
        self.assertEqual(len({atd.runtime(n) for n in (2, 6, 7)}), 3)
        for n in (0, 1, 3, 31):
            with self.assertRaises(ValueError):
                atd.runtime(n)

    def test_slow_collector_does_not_block_another_channel(self):
        master, slave = pty.openpty()
        tty.setraw(slave)
        slow = atd.Channel(slave, gap=0)
        errors = []
        def waiting():
            try:
                slow.command('AT+SLOW?', 0.5)
            except TimeoutError:
                errors.append('timeout')
        thread = threading.Thread(target=waiting)
        thread.start()
        try:
            self.assertTrue(select.select([master], [], [], 1)[0])
            self.assertEqual(os.read(master, 1024), b'AT+SLOW?\r')
            responder = self.modem([b'+CFUN: 1\r\nOK\r\n'])
            answer = self.channel.command('AT+CFUN?', 1)
            responder.join()
            self.assertIn('+CFUN: 1', answer)
            self.assertTrue(thread.is_alive(), 'independent query waited for slow collector')
            thread.join()
            self.assertEqual(errors, ['timeout'])
        finally:
            thread.join()
            os.close(master)
            os.close(slave)


if __name__ == '__main__':
    unittest.main()

"""Exercise the native client's real socket framing against a fake owner."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest


class ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='at-client-')
        cls.root = Path(cls.directory.name)
        cls.binary = cls.root / 'client'
        subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            f'-DAT_SOCKET_PREFIX="{cls.root}/at"', str((Path(__file__).resolve().parent / '../shared/at-client.c')),
            '-o', str(cls.binary)], check=True)
        (cls.root / 'at2').mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def exchange(self, arguments, parts):
        endpoint = self.root / 'at2/cmd.sock'
        endpoint.unlink(missing_ok=True)
        captured = []
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(endpoint))
            server.listen(1)
            server.settimeout(3)
            def answer():
                client, _ = server.accept()
                with client:
                    data = b''
                    while b'\n' not in data:
                        data += client.recv(4096)
                    captured.append(json.loads(data))
                    for part in parts:
                        client.sendall(part)
                        time.sleep(.005)
            worker = threading.Thread(target=answer)
            worker.start()
            result = subprocess.run([str(self.binary), *arguments],capture_output=True,timeout=5)
            worker.join()
        endpoint.unlink()
        return result, captured[0]

    def test_fragmented_response_and_escaped_command(self):
        command = 'AT+EXAMPLE="quoted\\text"'
        result, request = self.exchange(['-t', '3', command], [b'0', b'\n+RESULT: ', '中文'.encode(), b'\r\nO', b'K\r\n'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '+RESULT: 中文\r\nOK\r\n'.encode())
        self.assertEqual(request['command'], command)
        self.assertEqual(request['timeout'], 3)
        self.assertIs(request['plain'], True)
        self.assertGreater(request['deadline'], time.monotonic())

    def test_transport_error_is_failure(self):
        result, _ = self.exchange(['AT'], [b'1\nPrevious command is still pending'])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertIn(b'pending', result.stderr)

    def test_truncated_reply_is_not_success(self):
        result, _ = self.exchange(['AT'], [b'0\n+CFUN: 1\nO'])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')

    def test_modem_error_is_complete_transport(self):
        result, _ = self.exchange(['AT'], [b'0\n+CME ERROR: 10\n'])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'+CME ERROR: 10\n')

    def test_invalid_request_never_connects(self):
        for arguments in [['--channel','1','AT'], ['-t','0','AT'], ['AT\rAT'], ['AT'+'x'*1024]]:
            result = subprocess.run([str(self.binary), *arguments], capture_output=True, timeout=2)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b'')


if __name__ == '__main__':
    unittest.main()

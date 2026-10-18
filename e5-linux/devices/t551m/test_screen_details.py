"""Details collector regressions: read-only channel use and honest failures."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('details', Path(__file__).parent / 'infoscreen/details-radio.py')
details = importlib.util.module_from_spec(spec)
spec.loader.exec_module(details)


class DetailsTests(unittest.TestCase):
    def test_success_ignores_echo_and_unsolicited_lines(self):
        result = subprocess.CompletedProcess([], 0, 'AT+SPLBAND=0\r\n+IMSREG: 1\r\n+SPLBAND: 0,0,0,0,0\r\nOK\r\n', '')
        with patch.object(details.subprocess, 'run', return_value=result) as run:
            data = details.collect(6, [('lte', details.QUERIES['lte'])], 1)
        self.assertEqual(data, {'lte': '+SPLBAND: 0,0,0,0,0'})
        self.assertEqual(run.call_args.args[0], ['/opt/e5/t551m-at', '--channel', '6', '-t', '2', 'AT+SPACTCARD=1;+SPLBAND=0'])

    def test_error_and_missing_payload_are_unknown(self):
        for output in ['ERROR\r\n', '+CME ERROR: 3\r\n', 'OK\r\n', '+SPLBAND: 1,2,3\r\nERROR\r\n']:
            with self.subTest(output=output), patch.object(details.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                self.assertIsNone(details.collect(7, [('nr', details.QUERIES['nr'])])['nr'])

    def test_timeout_is_unknown_and_other_fields_still_collected(self):
        result = subprocess.CompletedProcess([], 0, '+SP5GRAN: 1\nOK\n', '')
        with patch.object(details.subprocess, 'run', side_effect=[subprocess.TimeoutExpired('AT', 4), result]):
            self.assertEqual(details.collect(7, [('nr', details.QUERIES['nr']), ('sa', details.QUERIES['sa'])]), {'nr': None, 'sa': '+SP5GRAN: 1'})


if __name__ == '__main__':
    unittest.main()

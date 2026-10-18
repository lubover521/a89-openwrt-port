"""Selected-SIM adapter must preserve payload and cannot override its scope."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[2]/'openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/at'

class Scope(unittest.TestCase):
    def test_adapter_scopes_commands_without_data_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,text in {'uci':'case "$*" in *at_backend) echo custom;; *at_command) echo "$TEST_ADAPTER";; esac',
                              'adapter':'printf "%s\\n" "$2"'}.items():
                path=root/name;path.write_text('#!/bin/sh\n'+text+'\n');path.chmod(0o755)
            env={**os.environ,'PATH':str(root)+':'+os.environ['PATH'],'TEST_ADAPTER':str(root/'adapter')}
            for slot in ['0','1']:
                for command in ['AT+COPS?','AT+SPACTCARD?','at+cesq','AT+CGDCONT=1,"IP","MixedCaseAPN"']:
                    result=subprocess.check_output(['sh',str(SOURCE),command],env={**env,'MU300_SIM_SLOT':slot},text=True)
                    self.assertEqual(result.strip(),'AT+SPACTCARD='+slot+';'+command[2:])
                for command in ['AT+SPACTCARD=0','at+spswdata=1','AT+COPS?;+SpAcTcArD=0']:
                    result=subprocess.run(['sh',str(SOURCE),command],env={**env,'MU300_SIM_SLOT':slot},capture_output=True)
                    self.assertNotEqual(result.returncode,0)
            self.assertEqual(subprocess.check_output(['sh',str(SOURCE),'AT+COPS?'],env=env,text=True).strip(),'AT+COPS?')

if __name__=='__main__':unittest.main()

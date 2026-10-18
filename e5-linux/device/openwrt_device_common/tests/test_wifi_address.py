"""Validate one-time AP address migration without radio or UCI access (Linux)."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

SOURCE=(Path(__file__).resolve().parent / '../shared/wifi-address-defaults').read_text()


class AddressMigration(unittest.TestCase):
    def check(self, configured='', driver='40:45:da:01:02:03', phy='00:00:00:00:00:00'):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'profile').write_text('t551m\n')
            radio=root/'sys/wlan0/phy80211'
            radio.mkdir(parents=True)
            if phy is not None:(radio/'macaddress').write_text(phy+'\n')
            (radio.parent/'address').write_text(driver+'\n')
            functions='''
config_load() { :; }
config_foreach() { "$1" default_radio0; }
config_get() {
    case "$3" in
        mode) mode=ap ;;
        macaddr) mac=$MAC ;;
        ifname) ifname=wlan0 ;;
    esac
}
uci() { echo "uci $*"; }
logger() { :; }
'''
            script=SOURCE.replace('/etc/e5/device-profile',directory+'/profile').replace('/sys/class/net/',directory+'/sys/').replace('. /lib/functions.sh',functions)
            return subprocess.run([shutil.which('busybox'),'sh','-c',script],env=dict(os.environ,MAC=configured),capture_output=True,text=True,timeout=5)

    def test_zero_phy_uses_valid_interface_address(self):
        result=self.check()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'uci set wireless.default_radio0.macaddr=40:45:da:01:02:03\nuci commit wireless\n')

    def test_explicit_mac_is_never_replaced(self):
        self.assertEqual(self.check(configured='02:aa:bb:cc:dd:ee').stdout,'')

    def test_valid_phy_needs_no_override(self):
        self.assertEqual(self.check(phy='40:45:da:11:22:33').stdout,'')

    def test_invalid_or_multicast_address_is_not_committed(self):
        for driver in ['00:00:00:00:00:00','ff:ff:ff:ff:ff:ff','41:45:da:01:02:03','broken']:
            result=self.check(driver=driver)
            self.assertEqual(result.returncode,1)
            self.assertEqual(result.stdout,'')

    def test_absent_phy_retries_on_later_boot(self):
        result=self.check(phy=None)
        self.assertEqual(result.returncode,1)
        self.assertEqual(result.stdout,'')

    def test_zero_configured_address_is_repaired(self):
        self.assertIn('uci set ',self.check(configured='00:00:00:00:00:00').stdout)


if __name__=='__main__':unittest.main()

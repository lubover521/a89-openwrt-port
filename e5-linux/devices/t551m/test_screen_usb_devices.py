"""Exercise the screen USB scanner with a real sysfs-shaped directory tree.

Run where ucode is installed: python3 test_screen_usb_devices.py API_UC
Only temporary files are read/written; no hardware or networking is changed.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    api = Path(sys.argv[1]).read_text()
    scanner = api[api.index('function usb_devices() {'):api.index('function usb_status() {')]
    with tempfile.TemporaryDirectory(prefix='screen-usb-test-') as tmp:
        root = Path(tmp)
        bus = root / 'bus'
        bus.mkdir()

        def device(key, name, cls='00'):
            node = root / 'devices' / key
            node.mkdir(parents=True)
            for attr, value in {'idVendor':'0bda', 'idProduct':'8153',
                                'bDeviceClass':cls, 'product':name}.items():
                if value is not None:
                    (node / attr).write_text(value + '\n')
            (bus / key).symlink_to(node, target_is_directory=True)
            return node

        def interface(key, dev, wireless=False):
            node = root / 'interfaces' / (key + ':1.0')
            net = node / 'net' / dev
            net.mkdir(parents=True)
            (net / 'type').write_text('1\n')
            (net / 'carrier').write_text('0\n')  # No cable/DHCP required.
            if wireless:
                (net / 'phy80211').mkdir()
            (bus / node.name).symlink_to(node, target_is_directory=True)

        device('usb2', 'Root hub', '09')
        device('2-1', 'Dock hub', '09')
        device('2-1.3', 'Nested hub', '09')
        device('2-1.3.4', 'USB Audio')  # Sorts before the NIC.
        nic = device('2-1.4', 'USB 10/100/1000 LAN', 'ff')
        interface('2-1.4', 'eth0')
        device('2-1.2', 'USB Wi-Fi')
        interface('2-1.2', 'wlan1', wireless=True)
        vanished = device('2-1.5', 'Unplugging')
        (vanished / 'idProduct').unlink()
        script = root / 'scan.uc'
        script.write_text("import { glob, readfile, stat } from 'fs';\n"
                          "function read_trim(p) { let v=readfile(p); return v==null ? null : trim(v); }\n"
                          + scanner.replace('/sys/bus/usb/devices', str(bus))
                          + "print(sprintf('%J', usb_devices()));\n")

        def scan():
            return json.loads(subprocess.check_output(['ucode', str(script)]))

        devices = scan()
        assert [d['id'] for d in devices] == ['2-1.2', '2-1.3.4', '2-1.4'], devices
        assert devices[-1]['kind'] == 'ethernet' and devices[-1]['interfaces'] == ['eth0'], devices
        assert devices[0]['kind'] == 'device', 'USB Wi-Fi mislabeled as Ethernet'
        (nic / 'product').unlink()
        assert scan()[-1]['kind'] == 'ethernet' and scan()[-1]['name'] == 'USB'
        # The driver may register after USB enumeration. The next ordinary
        # status request must discover it, without a sticky device cache.
        net = root / 'interfaces/2-1.4:1.0/net'
        shutil.rmtree(net)
        assert scan()[-1]['kind'] == 'device'
        (net / 'eth1').mkdir(parents=True)
        (net / 'eth1/type').write_text('1\n')
        assert scan()[-1]['interfaces'] == ['eth1']
        (bus / '2-1.4').unlink()
        assert len(scan()) == 2, 'Removed NIC left a stale indication'
    print('PASS: dock topology, Ethernet without carrier/product, late driver, Wi-Fi, disconnect')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Add temporary rollback/logging to an offline M8 bring-up root."""
import argparse
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--backup', type=Path, required=True)
    a = p.parse_args()
    root = a.root.resolve()
    if root == Path('/') or (root / 'etc/e5/device-profile').read_text().strip() != 'm8':
        raise ValueError('Offline M8 root required')
    cid = (a.backup / 'cid.txt').read_text().strip()
    mac = '02:51:' + ':'.join(cid[-8:][i:i+2] for i in range(0, 8, 2))
    defaults = root / 'etc/uci-defaults/zz-m8-trial'
    defaults.write_text('''#!/bin/sh
# Suppress IPv4 gateway/DNS only for the development PC. Do not disable LAN
# IPv6: phones need odhcpd RA/SLAAC. Disable router discovery on the PC's test
# adapter separately when it must not use this trial device for internet.
uci -q batch <<'UCI'
delete network.lan.ipaddr
add_list network.lan.ipaddr='192.168.9.1/24'
set dhcp.usb_host.mac='HOST_MAC'
set dhcp.usbhost=tag
add_list dhcp.usbhost.dhcp_option='3'
add_list dhcp.usbhost.dhcp_option='6'
set dhcp.lan.ra='server'
set dhcp.lan.dhcpv6='server'
commit network
commit dhcp
UCI
exit 0
'''.replace('HOST_MAC', mac))
    defaults.chmod(0o755)
    service = root / 'etc/init.d/m8-trial'
    service.write_text('''#!/bin/sh /etc/rc.common
START=99
USE_PROCD=1
start_service() {
    procd_open_instance
    procd_set_param command /usr/libexec/m8-trial
    procd_close_instance
}
''')
    service.chmod(0o755)
    script = root / 'usr/libexec/m8-trial'
    script.write_text('''#!/bin/sh
save() {
    p=/mnt/e5-data/e5linux/m8-trial-logs
    mkdir -p "$p" || return
    dmesg > "$p/dmesg.txt"
    logread > "$p/logread.txt"
    ubus call system board > "$p/system.json"
    cat /proc/mounts > "$p/mounts.txt"
    sync
}
t=0
while [ "$t" -lt 480 ]; do
    sleep 30; t=$((t+30)); save
done
[ -e /run/m8-keep-running ] && exit 0
logger -t m8-trial 'Bounded trial finished; returning to Android A'
save
/sbin/reboot
''')
    script.chmod(0o755)
    link = root / 'etc/rc.d/S99m8-trial'
    if not link.exists():
        link.symlink_to('../init.d/m8-trial')
    (root / 'etc/e5linux/default-boot').write_text('android\n')


if __name__ == '__main__':
    main()

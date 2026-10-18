#!/usr/bin/env python3
"""Build identity-guarded M8 OpenWrt; optionally permit persistent boot."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

TOP = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backup', type=Path, required=True)
    p.add_argument('--kernel', type=Path, required=True)
    p.add_argument('--busybox', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--persistent', action='store_true',
                   help='Honor the root filesystem default-boot setting instead of forcing Android')
    a = p.parse_args()
    manifest = json.loads((a.backup / 'manifest.json').read_text())
    for name in ('boot_b.img', 'misc.img', 'cid.txt', 'properties.txt'):
        if hashlib.sha256((a.backup / name).read_bytes()).hexdigest() != manifest[name]['sha256']:
            raise ValueError('Invalid stock backup: ' + name)
    if '[ro.product.model]: [VIPME M8]' not in (a.backup / 'properties.txt').read_text():
        raise ValueError('Not an M8 backup')
    cid = (a.backup / 'cid.txt').read_text().strip()
    if len(cid) != 32 or any(c not in '0123456789abcdef' for c in cid):
        raise ValueError('Invalid CID')
    init = (TOP / 'boot/init').read_text()
    anchor = 'log "stage=devfs-ready"'
    guard = '''
# Unit-scoped first boot: check identity before any partition writes/mounts.
i=0
while [ ! -r /sys/block/mmcblk0/device/cid ] && [ "$i" -lt 10 ]; do
    sleep 1; i=$((i+1))
done
if [ "$(cat /sys/block/mmcblk0/device/cid 2>/dev/null)" != "EXPECTED_CID" ]; then
    log "M8 identity mismatch; aborting without partition writes"
    reboot -f; while :; do sleep 60; done
fi
'''.replace('EXPECTED_CID', cid)
    if init.count(anchor) != 1:
        raise ValueError('Missing init identity anchor')
    init = init.replace(anchor, anchor + guard)
    anchor = 'find_partitions 6 || true'
    restore = '''find_partitions 6 || { reboot -f; exit 1; }
dd if=/etc/misc-bc-slot-a.bin of="$misc" bs=1 seek=2048 conv=notrunc
dd if="$misc" of=/run/m8-bc.bin bs=1 skip=2048 count=32
cmp /run/m8-bc.bin /etc/misc-bc-slot-a.bin || { reboot -f; exit 1; }
sync
log "stage=m8-android-a-verified"
'''
    if init.count(anchor) != 1:
        raise ValueError('Missing fallback anchor')
    init = init.replace(anchor, restore)
    # The diagnostic kernel forces its command line, so select the trial
    # explicitly in init, including the early own-firmware lookup.
    lines = init.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('w=$(echo ') and 'e5\\.openwrt' in line:
            lines[i] = 'w=openwrt-m8.ext4'
        if line.lstrip().startswith('image=$(echo ') and 'e5\\.openwrt' in line:
            lines[i] = '    image=openwrt-m8.ext4'
    init = '\n'.join(lines) + '\n'
    if a.persistent:
        # Keep explicit M8 root selection and early Android fallback. Only stop
        # overwriting the user's boot preference: e5-boot-ok re-arms B after a
        # successful boot, while a failed boot still falls back to Android A.
        reset = '''    [ -n "$e5_trial" ] && mkdir -p /newroot/etc/e5linux && echo android > /newroot/etc/e5linux/default-boot &&
        log "stage=trial-image default-boot=android"'''
        if init.count(reset) != 1:
            raise ValueError('Missing trial preference reset anchor')
        init = init.replace(reset, '    # Persistent M8: honor the saved default-boot preference.')
    if 'w=openwrt-m8.ext4' not in init or 'image=openwrt-m8.ext4' not in init:
        raise ValueError('Missing trial image selectors')
    mac = ':'.join(cid[-8:][i:i+2] for i in range(0, 8, 2))
    init = init.replace('E5LINUX', 'M8LINUX' + cid[-8:])
    init = init.replace('02:50:00:00:e5:01', '02:50:' + mac)
    init = init.replace('02:50:00:00:e5:02', '02:51:' + mac)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    init_path = a.out.with_suffix('.init')
    init_path.write_text(init)
    subprocess.run([sys.executable, str(TOP / 'boot/build-boot-image.py'),
        '--stock-boot', str(a.backup / 'boot_b.img'),
        '--misc-head', str(a.backup / 'misc-head.bin'),
        '--kernel', str(a.kernel / 'Image.lk'),
        '--modules', str(a.kernel / 'modules'),
        '--module-order', str(a.kernel / 'module-order.txt'),
        '--busybox', str(a.busybox), '--init', str(init_path),
        '--cmdline', '', '--out', str(a.out)], check=True)


if __name__ == '__main__':
    main()

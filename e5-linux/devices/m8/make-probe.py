#!/usr/bin/env python3
"""Build a bounded M8 initramfs probe using this unit's verified boot backup."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--kernel', required=True, type=Path)
    parser.add_argument('--busybox', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--modules', type=Path)
    parser.add_argument('--module-order', type=Path)
    parser.add_argument('--stay', type=int, default=45)
    parser.add_argument('--display-test', type=Path)
    args = parser.parse_args()
    if not 15 <= args.stay <= 300:
        raise SystemExit('Probe stay must be 15..300 seconds')
    if bool(args.modules) != bool(args.module_order):
        raise SystemExit('Provide both --modules and --module-order')
    top = Path(__file__).resolve().parents[2]
    manifest = json.loads((args.backup / 'manifest.json').read_text())
    for name in ('boot_b.img', 'misc.img', 'cid.txt', 'properties.txt'):
        if hashlib.sha256((args.backup / name).read_bytes()).hexdigest() != manifest[name]['sha256']:
            raise SystemExit('Backup verification failed: ' + name)
    if '[ro.product.model]: [VIPME M8]' not in (args.backup / 'properties.txt').read_text():
        raise SystemExit('Not an M8 backup')
    cid = (args.backup / 'cid.txt').read_text().strip()
    if len(cid) != 32 or any(c not in '0123456789abcdef' for c in cid):
        raise SystemExit('Invalid eMMC identity')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    init = args.out.with_suffix('.init')
    text = (top / 'upstream/init-bringup').read_text()
    anchor = 'log "userspace up: $(uname -a)"'
    if text.count(anchor) != 1:
        raise SystemExit('Unexpected shared init')
    restore = '''
# Return to this unit's Android A before starting the bounded hardware test.
i=0
while [ ! -r /sys/block/mmcblk0/device/cid ] && [ "$i" -lt 10 ]; do
    sleep 1; i=$((i + 1))
done
actual=$(cat /sys/block/mmcblk0/device/cid 2>/dev/null)
if [ "$actual" != "EXPECTED_CID" ]; then
    log "M8 identity mismatch; refusing partition writes"
    sleep 5; reboot -f
    while :; do sleep 60; done
fi
misc=
for u in /sys/class/block/mmcblk0p*/uevent; do
    if grep -qx PARTNAME=misc "$u"; then
        misc=/dev/$(basename "$(dirname "$u")")
    fi
done
if [ ! -b "$misc" ]; then
    log "No misc; aborting probe"
    reboot -f
    while :; do sleep 60; done
fi
dd if=/etc/misc-bc-slot-a.bin of="$misc" bs=1 seek=2048 conv=notrunc
dd if="$misc" of=/tmp/bc.bin bs=1 skip=2048 count=32
if ! cmp /tmp/bc.bin /etc/misc-bc-slot-a.bin; then
    log "Android fallback verification FAILED"
    reboot -f
    while :; do sleep 60; done
fi
sync
log "Android slot A fallback restored and verified"
(sleep WATCHDOG_SECONDS; persist; sync; reboot -f) &
echo 1 > /proc/sys/kernel/panic_on_oops
echo 1 > /proc/sys/kernel/softlockup_panic
persist
if [ -f /etc/module-order ]; then
    while read -r module; do
        [ -n "$module" ] || continue
        log "loading $module"
        insmod "/linux-modules/$module"
        log "loaded $module rc=$?"
        persist
    done < /etc/module-order
fi
log "power supplies: $(ls /sys/class/power_supply)"
for p in /sys/class/power_supply/*; do
    log "${p##*/}: $(tr '\\n' ' ' < "$p/uevent")"
done
log "input: $(cat /proc/bus/input/devices)"
log "drm: $(ls /sys/class/drm)"
[ ! -x /e5-overlay/bin/m8-display-test ] || /e5-overlay/bin/m8-display-test > /tmp/display-test.log 2>&1 &
for p in /sys/class/backlight/*; do
    log "backlight ${p##*/}: $(cat "$p/brightness" "$p/max_brightness")"
done
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    log "cpufreq ${p##*/}: $(cat "$p/scaling_available_frequencies" "$p/scaling_governor")"
done
'''.replace('EXPECTED_CID', cid)
    restore = restore.replace('WATCHDOG_SECONDS', str(args.stay + 180))
    text = text.replace(anchor, anchor + restore)
    text = text.replace('stay=${E5_STAY:-180}', 'stay=' + str(args.stay))
    text = text.replace('E5LINUX', 'M8PROBE' + cid[-8:])
    text = text.replace('E5 Linux USB Ethernet (mainline bring-up)', 'M8 OpenWrt hardware probe')
    mac = ':'.join(cid[-8:][i:i+2] for i in range(0, 8, 2))
    text = text.replace('02:50:00:00:e5:01', '02:50:' + mac)
    text = text.replace('02:50:00:00:e5:02', '02:51:' + mac)
    init.write_text(text)
    order = args.out.with_suffix('.modules')
    order.write_text(args.module_order.read_text() if args.module_order else '')
    command = [
        sys.executable, str(top / 'boot/build-boot-image.py'),
        '--stock-boot', str(args.backup / 'boot_b.img'),
        '--misc-head', str(args.backup / 'misc-head.bin'),
        '--kernel', str(args.kernel / 'Image.lk'), '--module-order', str(order),
        '--init', str(init), '--busybox', str(args.busybox), '--cmdline', '',
        '--out', str(args.out),
    ]
    if args.modules:
        command.extend(['--modules', str(args.modules)])
    if args.display_test:
        overlay = args.out.with_suffix('.overlay')
        target = overlay / 'bin/m8-display-test'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(args.display_test.read_bytes())
        target.chmod(0o755)
        command.extend(['--overlay', str(overlay)])
    subprocess.run(command, check=True)


if __name__ == '__main__':
    main()

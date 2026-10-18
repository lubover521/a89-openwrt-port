#!/usr/bin/env python3
"""Build a T551M probe, trial or persistent image from its own boot and misc."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--backup', type=Path, required=True)
    ap.add_argument('--kernel', type=Path, required=True)
    ap.add_argument('--busybox', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--probe', action='store_true')
    ap.add_argument('--persistent', action='store_true', help='Allow the installed root to select Linux as default')
    a = ap.parse_args()
    if a.probe and a.persistent:
        ap.error('--probe and --persistent are mutually exclusive')
    top = Path(__file__).resolve().parents[2]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    init = top / 'boot/init'
    order = a.kernel / 'module-order.txt'
    if a.persistent:
        init = a.out.with_suffix('.init')
        text = (top / 'boot/init').read_text()
        old = '[ -n "$e5_trial" ] && mkdir -p /newroot/etc/e5linux'
        new = ('[ -n "$e5_trial" ] && [ ! -f /newroot/etc/e5/t551m-persistent ] && '
               'mkdir -p /newroot/etc/e5linux')
        if text.count(old) != 1:
            raise SystemExit('Unexpected init default-boot logic')
        init.write_text(text.replace(old, new))
    if a.probe:
        init = a.out.with_suffix('.init')
        text = (top / 'upstream/init-bringup').read_text()
        marker = 'log "userspace up: $(uname -a)"'
        text = text.replace(marker, marker + '''
# Restore Android before loading any board modules. This is a bounded probe.
for u in /sys/class/block/mmcblk0p*/uevent; do
    if grep -qx PARTNAME=misc "$u"; then
        m=/dev/$(basename "$(dirname "$u")")
        dd if=/etc/misc-bc-slot-a.bin of="$m" bs=1 seek=2048 conv=notrunc
        dd if="$m" of=/tmp/bc.bin bs=1 skip=2048 count=32
        cmp /tmp/bc.bin /etc/misc-bc-slot-a.bin || { log "MISC VERIFY FAILED"; reboot -f; }
        sync
        log "Android slot A restored"
    fi
done
(sleep 120; persist; sync; echo b > /proc/sysrq-trigger) &
while read -r module; do
    insmod "/linux-modules/$module"
    log "module $module rc=$?"
done < /etc/module-order
for p in /sys/class/power_supply/*; do
    log "power $(cat "$p/uevent" | tr '\\n' ' ')"
done
''')
        text = text.replace('stay=${E5_STAY:-180}', 'stay=${E5_STAY:-60}')
        init.write_text(text)
        order = a.out.with_suffix('.modules')
        order.write_text('sprd_battery_info.ko\nsprd-charger-manager.ko\nump96xx_fuel_gauge.ko\nbq2560x-charger.ko\n')
    subprocess.run([
        sys.executable, str(top / 'boot/build-boot-image.py'),
        '--stock-boot', str(a.backup / 'boot_b.img'),
        '--misc-head', str(a.backup / 'misc-head.bin'),
        '--kernel', str(a.kernel / 'Image.lk'), '--modules', str(a.kernel / 'modules'),
        '--module-order', str(order), '--init', str(init),
        '--busybox', str(a.busybox), '--cmdline', '', '--out', str(a.out),
    ], check=True)


if __name__ == '__main__':
    main()

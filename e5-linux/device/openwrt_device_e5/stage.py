#!/usr/bin/env python3
"""Install the shared dashboard/mobile features into an offline E5 root.

Keep E5 firmware, calibration, amplifier, backlight, credentials and boot
selection. Internal t551m-* service/RPC names remain stable compatibility APIs.
"""
import argparse
import json
import os
from pathlib import Path
import runpy

TOP = Path(__file__).resolve().parents[2]
SHARED = TOP / 'device/openwrt_device_common/shared'
source_bytes = runpy.run_path(str(TOP / 'device/linux_device_common/staging.py'))['source_bytes']


_shared=runpy.run_path(str(TOP/"device/openwrt_device_common/shared/staging.py"))
copy,link,stage_nv=(_shared[name] for name in ("copy","link","stage_nv"))


def stage(root):
    root = Path(root).resolve()
    if root == Path('/') or os.name == 'nt':
        raise ValueError('Run in Linux/WSL against an offline root, never the running system')
    marker = root / 'etc/e5/device-profile'
    if marker.exists() and marker.read_text().strip() != 'e5':
        raise ValueError('Refusing to convert another board image into E5')
    if (root / 'etc/e5/t551m-persistent').exists():
        raise ValueError('T551M boot policy found in E5 root')
    # The shell, compositor, RPC registration and fonts belong to the base E5
    # screen package. A partial archive must not claim to be a complete image.
    for name in ('etc/init.d/e5-vendor', 'etc/init.d/e5-sipc-wwan',
                 'usr/libexec/e5-infoscreen/session',
                 'usr/share/rpcd/ucode/e5-infoscreen.uc'):
        if not (root / name).is_file():
            raise ValueError('Missing E5 base component: ' + name)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text('e5\n')
    runpy.run_path(str(TOP / 'device/linux_device_common/wifi-common.py'))['stage'](root)
    runpy.run_path(str(TOP / 'device/openwrt_device_common/shared/modem-recovery.py'))['stage'](root)
    for name in ('vendor-start.sh', 'android-import-perms.sh', 'android-run', 'e5-modem-coldboot', 'e5-at',
                 'e5-next-boot', 'e5-os', 'e5-sd-registry', 'e5-call-audio.py'):
        copy(root, TOP / 'device/linux_device_common/overlay/opt/e5' / name, 'opt/e5/' + name)
    for name in ('usr/libexec/e5-sms', 'usr/libexec/e5-sms-receive',
                 'usr/lib/e5/sms_pdu.py', 'usr/libexec/e5-container-setup',
                 'usr/libexec/e5-dockerd'):
        copy(root, TOP / 'device/openwrt_device_common/overlay' / name, name)
    copy(root, TOP / 'device/openwrt_device_common/overlay/etc/config/e5-audio',
         'etc/config/e5-audio', 0o644, preserve=True)
    runpy.run_path(str(SHARED / 'ui.py'))['stage'](root, profile='e5')
    stage_nv(root)
    for source, target in (
        ('charge-mode.py', 'usr/libexec/e5-charge-mode'),
        ('charge-screen.py', 'usr/libexec/e5-charge-screen'),
        ('charge-art.zip', 'usr/share/e5-charge/art.zip'),
        ('charge-mode-service', 'etc/init.d/e5-charge-mode'),
        ('usb-service', 'etc/init.d/t551m-usb'),
        ('usb-host-storage.modules', 'etc/modules.d/usb-host-storage'),
        ('usb-host-network.modules', 'etc/modules.d/usb-host-network'),
    ):
        copy(root, SHARED / source, target,
             0o644 if source.endswith(('.zip', '.modules')) else 0o755)
    link(root, 'S14e5-charge-mode', 'e5-charge-mode')
    link(root, 'S25t551m-usb', 't551m-usb')
    # Make an unadapted upstream UI update fail the existing compatibility gate.
    (root / 'usr/share/e5-infoscreen/ADAPTATION').write_text('e5-device-ui-v1\n')
    manifest = {'profile': 'e5', 'schema': 1,
                'hardware': 'native E5 DT, charger, backlight, touchscreen and AW87xxx',
                'features': ['aurora', 'dashboard', 'dual-sim', 'traffic', 'sms',
                             'at-workers', 'pre-dial-replay', 'mobile-screen',
                             'phone-hfp', 'cpu-controls', 'usb-controls',
                             'charger-boot', 'isolated-nv'],
                'hardware_validation': 'required on target before deployment'}
    (root / 'etc/e5/feature-port.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    stage(parser.parse_args().root)

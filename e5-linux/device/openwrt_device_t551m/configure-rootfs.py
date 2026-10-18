#!/usr/bin/env python3
"""Customize a mounted copy of the E5 OpenWrt root image for a T551M trial.

Run as root on Linux after extracting the device's private device-files.tar.
The image must not be a live system root. Credentials stay in ignored output.
"""
import argparse
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import runpy
import sys
from types import SimpleNamespace


def stage(root, persistent=True):
    """Stage T551M programs without firmware, credentials or kernel changes."""
    root = Path(root).resolve()
    if root == Path('/'):
        raise ValueError('Expected an offline root')
    top = Path(__file__).resolve().parents[2]
    runpy.run_path(str(top / 'device/linux_device_common/wifi-common.py'))['stage'](root)
    runpy.run_path(str(top / 'device/openwrt_device_common/shared/modem-recovery.py'))['stage'](root)
    a = SimpleNamespace(persistent=persistent)
    base_profile = (root / 'etc/e5/device-profile').read_text().strip() if (root / 'etc/e5/device-profile').exists() else ''
    if base_profile == 'e5':
        shutil.copy2(Path(__file__).with_name('overlay') / 'etc/config/unisoc_modem', root / 'etc/config/unisoc_modem')
    for name in ('vendor-start.sh', 'android-import-perms.sh', 'android-run', 'e5-modem-coldboot'):
        dst = root / 'opt/e5' / name
        shutil.copy2(top / 'device/linux_device_common/overlay/opt/e5' / name, dst)
        dst.chmod(0o755)
    nv = root / 'opt/e5/t551m-nv-prepare'
    shutil.copy2((Path(__file__).resolve().parent / '../openwrt_device_common/shared/nv-prepare.py'), nv)
    nv.chmod(0o755)
    nv_verify = root / 'opt/e5/t551m-nv-verify'
    shutil.copy2((Path(__file__).resolve().parent / '../openwrt_device_common/shared/nv-verify.py'), nv_verify)
    nv_verify.chmod(0o755)
    nv_stop = root / 'opt/e5/t551m-nv-stop'
    shutil.copy2((Path(__file__).resolve().parent / '../openwrt_device_common/shared/nv-stop.py'), nv_stop)
    nv_stop.chmod(0o755)
    # Prepare and protect NV before procd starts any of the parallel daemons.
    service = root / 'etc/init.d/e5-vendor'
    service_text = (top / 'device/openwrt_device_common/overlay/etc/init.d/e5-vendor').read_text()
    service_text = service_text.replace('START=20', 'START=20\nSTOP=10')
    service_text = service_text.replace('procd_set_param respawn 3600 5 0',
        'procd_set_param respawn 3600 5 0\n\tprocd_set_param term_timeout 2')
    service_text = service_text.replace('start_service() {',
        'start_service() {\n\t/opt/e5/t551m-nv-prepare || return 1')
    service.write_text(service_text + '''
stop_service() {
    /opt/e5/t551m-nv-stop quiesce
}

service_stopped() {
    /opt/e5/t551m-nv-stop detach
}
''')
    shutdown = root / 'etc/rc.d/K10e5-vendor'
    if not shutdown.is_symlink():
        shutdown.symlink_to('../init.d/e5-vendor')
    vendor = root / 'opt/e5/vendor-start.sh'
    text = vendor.read_text()
    text = text.replace('  ln -sfn "/dev/$d"',
        '  case "$n" in nr_fixnv*|nr_runtimenv*|nr_deltanv*|calinv) continue ;; esac\n  ln -sfn "/dev/$d"', 1)
    text = text.replace('for p in nr_modem nr_phy nr_deltanv nr_fixnv1 nr_fixnv2;',
                        'for p in nr_modem nr_phy;')
    vendor.write_text(text)
    audio = root / 'opt/e5/e5-audio-dsp'
    audio_text = (top / 'device/linux_device_common/overlay/opt/e5/e5-audio-dsp').read_text()
    audio_text = audio_text.replace(' snd-soc-sprd-pa-aw87xxx', '')
    # T551M's GPIO amplifier retains legacy hook state across unbind. E5's
    # forced rebind can race successful registration and call a freed hook.
    # Probe missing consumers, then let deferred probing settle naturally.
    start = audio_text.index('bind_card() {')
    end = audio_text.index('\n}\n', start) + 3
    audio_text = audio_text[:start] + '''bind_card() {
    bind_pd_consumers || :
    for attempt in $(seq 1 20); do
        grep -q sprdphone /proc/asound/cards 2>/dev/null && return 0
        sleep 1
    done
    echo "T551M: card unavailable; skipping unsafe legacy unbind" >&2
    return 1
}
''' + audio_text[end:]
    audio.write_text(audio_text)
    (root / 'etc/e5linux').mkdir(exist_ok=True)
    (root / 'etc/e5linux/default-boot').write_text('linux\n' if a.persistent else 'android\n')
    marker = root / 'etc/e5/t551m-persistent'
    if a.persistent:
        marker.touch()
    else:
        marker.unlink(missing_ok=True)
    next_boot = (top / 'device/linux_device_common/overlay/opt/e5/e5-next-boot').read_text()
    next_boot = next_boot.replace('trial() { case',
        'trial() { [ -f /etc/e5/t551m-persistent ] && '
        '[ "$(cat /etc/e5/device-profile 2>/dev/null)" = t551m ] && return 1; case')
    (root / 'opt/e5/e5-next-boot').write_text(next_boot)
    (root / 'opt/e5/e5-next-boot').chmod(0o755)
    (root / 'etc/e5/device-profile').write_text('t551m\n')
    for source, target in [('charge-mode.py', 'usr/libexec/e5-charge-mode'),
                           ('charge-screen.py', 'usr/libexec/e5-charge-screen'),
                           ('charge-art.zip', 'usr/share/e5-charge/art.zip'),
                           ('charge-mode-service', 'etc/init.d/e5-charge-mode')]:
        destination = root / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = (top / 'device/openwrt_device_common/shared' / source).read_bytes()
        destination.write_bytes(data if source.endswith('.zip') else data.replace(b'\r\n', b'\n'))
        destination.chmod(0o644 if source.endswith('.zip') else 0o755)
    link = root / 'etc/rc.d/S14e5-charge-mode'
    if not link.is_symlink():
        link.symlink_to('../init.d/e5-charge-mode')
    runpy.run_path(str((Path(__file__).resolve().parent / '../openwrt_device_common/shared/ui.py')))['stage'](root)
    service = root / 'etc/init.d/t551m-trial'
    shutil.copy2(Path(__file__).with_name('trial-service'), service)
    service.chmod(0o755)
    link = root / 'etc/rc.d/S15t551m-trial'
    if a.persistent:
        link.unlink(missing_ok=True)
    elif not link.is_symlink():
        link.symlink_to('../init.d/t551m-trial')
    service = root / 'etc/init.d/t551m-usb'
    shutil.copy2((Path(__file__).resolve().parent / '../openwrt_device_common/shared/usb-service'), service)
    service.chmod(0o755)
    link = root / 'etc/rc.d/S25t551m-usb'
    if not link.is_symlink():
        link.symlink_to('../init.d/t551m-usb')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('root', type=Path)
    ap.add_argument('--kernel', type=Path, required=True)
    ap.add_argument('--credentials', type=Path, required=True)
    ap.add_argument('--persistent', action='store_true', help='Use with the --persistent boot image')
    a = ap.parse_args()
    root = a.root.resolve()
    if root == Path('/') or not (root / 'etc/openwrt_release').is_file():
        raise SystemExit('Expected a mounted offline OpenWrt image')
    if not (root / 'opt/e5/android/apex/com.android.runtime/bin/linker').is_file():
        raise SystemExit('Extract T551M device-files.tar into this image first')
    top = Path(__file__).resolve().parents[2]
    base_profile = (root / 'etc/e5/device-profile').read_text().strip() if (root / 'etc/e5/device-profile').exists() else ''
    if base_profile == 'e5':
        # This explicit offline conversion replaces only the base board's radio defaults.
        shutil.copy2(Path(__file__).with_name('overlay') / 'etc/config/unisoc_modem', root / 'etc/config/unisoc_modem')
    release = (a.kernel / 'kernel.release').read_text().strip()
    if '-t551m' not in release:
        raise SystemExit('Expected the T551M kernel build')
    # Include on-demand virtualization/networking modules and their indexes,
    # alongside the existing audio/modem aliases used by board services.
    subprocess.run([sys.executable, str(top / 'upstream/stage-root-modules.py'),
                    str(a.kernel), '--root', str(root)], check=True)
    # OpenWrt has no generic modalias loader in this image. Load the host
    # storage drivers once so later OTG attachments can bind automatically.
    modules_d = root / 'etc/modules.d'
    modules_d.mkdir(parents=True, exist_ok=True)
    storage_modules = modules_d / '55-usb-host-storage'
    shutil.copyfile((Path(__file__).resolve().parent / '../openwrt_device_common/shared/usb-host-storage.modules'), storage_modules)
    storage_modules.chmod(0o644)
    network_modules = modules_d / '56-usb-host-network'
    shutil.copyfile((Path(__file__).resolve().parent / '../openwrt_device_common/shared/usb-host-network.modules'), network_modules)
    network_modules.chmod(0o644)
    stage(root, a.persistent)
    if a.credentials.exists():
        credentials = json.loads(a.credentials.read_text())
    else:
        credentials = {'username': 'root', 'password': secrets.token_urlsafe(16),
                       'ssid': 'OpenWrt', 'wifi_key': secrets.token_urlsafe(12)}
        a.credentials.parent.mkdir(parents=True, exist_ok=True)
        a.credentials.write_text(json.dumps(credentials, indent=2) + '\n')
        a.credentials.chmod(0o600)
    hashed = subprocess.check_output(['openssl', 'passwd', '-6', '-stdin'],
                                    input=credentials['password'].encode()).decode().strip()
    shadow = root / 'etc/shadow'
    lines = shadow.read_text().splitlines()
    shadow.write_text('\n'.join(':'.join([f[0], hashed, *f[2:]]) if f[0] == 'root' else ':'.join(f)
                                for f in (l.split(':') for l in lines)) + '\n')
    shadow.chmod(0o600)
    install = root / 'etc/e5/install.conf'
    install.write_text("E5_DEFAULT_BOOT=" + ('linux' if a.persistent else 'android') + "\nE5_WIFI_SSID='" + credentials['ssid']
                       + "'\nE5_WIFI_KEY='" + credentials['wifi_key'] + "'\n")
    install.chmod(0o600)
    defaults = root / 'etc/uci-defaults/99-t551m'
    defaults.write_text("#!/bin/sh\nuci set system.@system[0].hostname='OpenWrt'\n"
                        "uci set system.@system[0].zonename='Asia/Singapore'\n"
                        "uci set system.@system[0].timezone='SGT-8'\nuci commit system\n")
    defaults.chmod(0o755)
    print('Prepared T551M ' + ('persistent' if a.persistent else 'trial') + ' root, kernel ' + release)


if __name__ == '__main__':
    main()

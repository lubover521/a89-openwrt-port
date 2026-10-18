"""Shared offline userspace staging, service links and isolated NV setup."""
from pathlib import Path
import os, runpy
TOP=Path(__file__).resolve().parents[3]
SHARED=Path(__file__).resolve().parent
source_bytes=runpy.run_path(str(TOP/"device/linux_device_common/staging.py"))["source_bytes"]


def stage_runtime(root):
    """Install common audio/SMS dependencies independently of the screen package."""
    root = Path(root)
    base = TOP / 'device/openwrt_device_common/overlay'
    names = ('usr/libexec/e5-voice-audio', 'usr/libexec/e5-hfp', 'usr/libexec/e5-volume',
             'usr/libexec/e5-call-volume', 'usr/lib/e5/e5_call_volume.py',
             'usr/lib/e5/e5_call_events.py', 'usr/lib/e5/e5_screen_rpc.py', 'usr/lib/e5/e5_power_events.py', 'usr/lib/e5/e5_sounds.py',
             'usr/libexec/e5-notification-sound', 'usr/libexec/e5-sms-notify',
             'etc/init.d/e5-hfp', 'etc/sysctl.d/10-e5-printk.conf')
    for name in names:
        copy(root, base / name, name, 0o644 if name.startswith('etc/sysctl.d/') else 0o755)
    for name in ('e5-call-audio.py', 'e5_call_profiles.py'):
        copy(root, TOP / 'device/linux_device_common/overlay/opt/e5' / name, 'opt/e5/' + name)
    for name in ('ding.wav', 'call.wav', 'beep.wav'):
        copy(root, base / 'usr/share/e5' / name, 'usr/share/e5/' + name, 0o644)
    for source in (base / 'usr/lib/e5/vendor').iterdir():
        copy(root, source, 'usr/lib/e5/vendor/' + source.name, 0o644)
    for name in ('S98e5-hfp', 'K08e5-hfp'):
        link(root, name, 'e5-hfp')


def stage_phone(root):
    """Stage the separately versioned Phone plugin from its own repository."""
    plugin = Path(os.environ.get('E5_INFOSCREEN_PLUGINS', str(TOP / 'ci/infoscreen-plugins'))) / 'plugins/phone'
    if not (plugin / 'manifest.json').is_file():
        raise ValueError('Missing infoscreen-plugins Phone package')
    for source in plugin.iterdir():
        if source.is_file():
            copy(root, source, 'etc/e5-infoscreen/plugins/phone/' + source.name, 0o644)
            web = Path(root) / 'usr/share/e5-infoscreen/www/plugins/phone'
            if not web.is_symlink():
                copy(root, source, 'usr/share/e5-infoscreen/www/plugins/phone/' + source.name, 0o644)

def copy(root, source, target, mode=0o755, preserve=False):
    dest = root / target
    if preserve and dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(source_bytes(source))
    dest.chmod(mode)

def link(root, name, service):
    path = root / 'etc/rc.d' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        if os.readlink(path) != '../init.d/' + service:
            raise ValueError('Unexpected service link: ' + str(path))
    elif path.exists():
        raise ValueError('Service link occupied: ' + str(path))
    else:
        path.symlink_to('../init.d/' + service)

def stage_nv(root):
    # Each unit creates isolated loop-backed copies from its OWN partitions
    # before either vendor writer starts. No donor NV data is staged here.
    for name in ('prepare', 'verify', 'stop'):
        copy(root, SHARED / ('nv-' + name + '.py'), 'opt/e5/t551m-nv-' + name)
    service = (TOP / 'device/openwrt_device_common/overlay/etc/init.d/e5-vendor').read_text()
    service = service.replace('START=20', 'START=20\nSTOP=10')
    service = service.replace('procd_set_param respawn 3600 5 0',
                              'procd_set_param respawn 3600 5 0\n\tprocd_set_param term_timeout 2')
    service = service.replace('start_service() {',
                              'start_service() {\n\trm -f /run/e5-vendor-prepared\n\t/opt/e5/t551m-nv-prepare || return 1')
    service = service.replace('instance cp_diskserver /opt/e5/android-run cp_diskserver',
        "instance cp_diskserver /bin/sh -c 'i=0; until [ -e /run/e5-vendor-prepared ]; do "
        "i=$((i + 1)); [ $i -lt 120 ] || exit 1; /opt/e5/bin/busybox sleep 0.1; done; exec /opt/e5/android-run cp_diskserver'")
    service += '\nstop_service() {\n\t/opt/e5/t551m-nv-stop quiesce\n}\n\nservice_stopped() {\n\t/opt/e5/t551m-nv-stop detach\n}\n'
    (root / 'etc/init.d/e5-vendor').write_text(service)
    (root / 'etc/init.d/e5-vendor').chmod(0o755)
    vendor = root / 'opt/e5/vendor-start.sh'
    text = vendor.read_text()
    anchor = '  [ -n "$n" ] && ln -sfn "/dev/$d" "/dev/block/by-name/$n"'
    if text.count(anchor) != 1:
        raise ValueError('Unexpected vendor partition setup')
    text = text.replace(anchor,
        '  case "$n" in nr_fixnv*|nr_runtimenv*|nr_deltanv*|calinv) continue ;; esac\n' + anchor)
    text = text.replace('for p in nr_modem nr_phy nr_deltanv nr_fixnv1 nr_fixnv2;',
                        'for p in nr_modem nr_phy;')
    # E5's 64-bit loader parses bootconfig AFTER cmdline. Keep each isolated
    # NV alias bound to its own loop, and select the intended firmware/NV slot
    # consistently in both inputs instead of loading slot B's stale calibration.
    anchor = 'mountpoint -q "$A/proc/cmdline" || mount --bind /run/e5-cmdline.android "$A/proc/cmdline"'
    if text.count(anchor) != 1:
        raise ValueError('Unexpected vendor cmdline mount')
    text = text.replace(anchor, anchor + '''
if [ "$modem_slot" = "a" ] && [ -r /proc/bootconfig ]; then
  sed 's/\\(androidboot.slot_suffix *= *"\\)_b"/\\1_a"/' /proc/bootconfig > /run/e5-bootconfig.android
  mountpoint -q "$A/proc/bootconfig" || mount --bind /run/e5-bootconfig.android "$A/proc/bootconfig"
fi
''')
    text = text.replace('echo "stage=exec"', 'touch /run/e5-vendor-prepared\necho "stage=exec"', 1)
    vendor.write_text(text)
    link(root, 'K10e5-vendor', 'e5-vendor')

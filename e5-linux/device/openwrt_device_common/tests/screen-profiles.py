"""Shared screen transport must ship on both supported phones."""
from pathlib import Path
import runpy
import tempfile

repo = Path(__file__).resolve().parents[3]
screen = runpy.run_path(str(repo/'ci/infoscreen/tools/stage.py'))['stage']
shared = runpy.run_path(str(repo/'device/openwrt_device_common/shared/staging.py'))
with tempfile.TemporaryDirectory() as tmp:
    for profile in ('t551m', 'e5', 'm8'):
        root = Path(tmp)/profile
        (root/'etc/e5').mkdir(parents=True)
        (root/'etc/e5/device-profile').write_text(profile+'\n')
        (root/'etc/rc.d').mkdir()
        (root/'etc/uci-defaults').mkdir()
        screen(root)
        shared['stage_runtime'](root)
        shared['stage_phone'](root)
        index = (root/'usr/share/e5-infoscreen/www/index.html').read_text()
        assert index.count('src="transport.js"') == 1
        assert index.index('transport.js') < index.index('calls.js')
        for name in ('e5_call_events.py', 'e5_screen_rpc.py', 'e5_power_events.py'):
            assert (root/'usr/lib/e5'/name).read_bytes() == (repo/'device/openwrt_device_common/overlay/usr/lib/e5'/name).read_bytes().replace(b'\r\n',b'\n')
        for name in ('calls.js', 'transport.js'):
            assert (root/'usr/share/e5-infoscreen/www'/name).read_bytes() == (repo/'ci/infoscreen/root/usr/share/e5-infoscreen/www'/name).read_bytes().replace(b'\r\n',b'\n')
        assert b'T551MTransport' in (root/'usr/share/e5-infoscreen/www/sdk/e5.js').read_bytes()
        assert b'T551MCalls.subscribe' in (root/'etc/e5-infoscreen/plugins/phone/phone.js').read_bytes()
        assert (root/'etc/e5/device-profile').read_text().strip() == profile
print('E5/T551M shared event/read transport PASS')

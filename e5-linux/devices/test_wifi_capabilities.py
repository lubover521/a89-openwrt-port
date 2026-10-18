#!/usr/bin/env python3
"""Test the real ucode policy in an OpenWrt chroot (Linux root + binfmt).

Usage: test_wifi_capabilities.py /path/to/staged-openwrt-root
"""
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

ROOT = Path(sys.argv[1]).resolve()
module = runpy.run_path(str(Path(__file__).with_name('t551m') / 'network-startup.py'))
with tempfile.TemporaryDirectory(prefix='wifi-cap-test-', dir=ROOT / 'tmp') as temp:
    temp = Path(temp)
    target = temp / 'usr/share/ucode/wifi/hostapd.uc'
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / 'usr/share/ucode/wifi/hostapd.uc').read_bytes())
    module['patch_wifi_capabilities'](temp)
    first = target.read_bytes()
    module['patch_wifi_capabilities'](temp)
    assert first == target.read_bytes(), 'not idempotent'
    legacy = '''// unisoc-driver-dfs-capabilities: previous policy.
function device_no_dfs(config) { config.htmode = 'HT20'; }

'''
    target.write_text(target.read_text().replace(module['NO_DFS'], legacy))
    module['patch_wifi_capabilities'](temp)
    assert first == target.read_bytes(), 'existing roots did not migrate'
    script = temp / 'test.uc'
    script.write_text('let phy_features = {}, phy_capabilities = {};\nfunction log(s) {}\n' + module['NO_DFS'] + '''
function check(value, message) { if (!value) die(message); }
function channels(list) { return map(list, (c) => ({freq:5000+5*c})); }
function run(channel, mode, freqs, radar, band) {
    radar ??= false;
    band ??= '5g';
    phy_features={radar_detect:radar};
    phy_capabilities={freqs:[...freqs,{freq:5260,radar:true}]};
    let c={band:band,channel:channel,htmode:mode};
    device_no_dfs(c);
    return c;
}
let c=run(52,'VHT80',channels([36,40,44,48]));
check(c.channel==36 && c.htmode=='VHT80','80 MHz fallback');
for (let mode in ['NOHT','HT20','HT40','VHT80','HE80','HE160','EHT80']) {
    c=run(52,mode,channels([149,153,157,161]));
    check(c.channel==36 && c.htmode==mode,'fixed 36, preserve '+mode);
    c=run(52,mode,[]);
    check(c.channel==36 && c.htmode==mode,'no fallback search with partial frequency data');
}
c=run(0,'VHT80',channels([36]));
check(c.channel==0 && c.acs_exclude_dfs,'ACS filtering');
c=run(52,'VHT80',channels([36]),true);
check(c.channel==52 && c.htmode=='VHT80','radar-capable driver unchanged');
c=run(6,'HT40',[],false,'2g');
check(c.channel==6 && c.htmode=='HT40','2.4 GHz unchanged');
c=run(36,'VHT80',channels([36,40,44,48]));
check(c.channel==36 && c.htmode=='VHT80','non-DFS selection unchanged');
let restricted={freq:5180,no_ir:true,disabled:true};
c=run(52,'VHT80',[restricted]);
check(c.channel==36 && c.htmode=='VHT80' && restricted.no_ir && restricted.disabled,
      'policy must not modify regulatory flags used by hostapd/nl80211');
print('PASS: fixed channel 36, unchanged bandwidth, DFS/ACS scope and regulatory flags\\n');
''')
    def inside(path):
        return '/' + str(path.relative_to(ROOT))
    subprocess.run(['chroot', str(ROOT), '/usr/bin/ucode', inside(script)], check=True)
    wrapper = temp / 'compile.uc'
    wrapper.write_text("import * as hostapd from '" + inside(target) + "';\n")
    subprocess.run(['chroot', str(ROOT), '/usr/bin/ucode', '-c', '-o', inside(temp / 'hostapd.ucb'), inside(wrapper)], check=True)
print('PASS: installed hostapd generator compiles and patch is idempotent')

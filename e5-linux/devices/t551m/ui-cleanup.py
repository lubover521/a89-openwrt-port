#!/usr/bin/env python3
"""Remove superseded web pages; retain the native-event forwarding service."""
import argparse
import json
from pathlib import Path

OBSOLETE = (
    'usr/share/e5-infoscreen/www/plugins/calculator/index.html',
    'usr/share/e5-infoscreen/www/plugins/calculator/manifest.json',
    'usr/share/luci/menu.d/luci-app-e5-sms.json',
    'www/luci-static/resources/view/e5-sms/sms.js',
    'www/luci-static/resources/view/e5-sms/sms.css',
)


def cleanup(root):
    root = Path(root).resolve()
    # Exact file names only; keep inboxes, forwarding configuration, e5-sms
    # services/RPCs, the physical display, Bluetooth and network diagnostics.
    for relative in OBSOLETE:
        path = root / relative
        if path.is_file() or path.is_symlink():
            path.unlink()
    menu = root / 'usr/share/luci/menu.d/luci-mod-status.json'
    if menu.exists():
        data = json.loads(menu.read_text())
        # No title: no duplicate menu, while existing bookmarks still work.
        data['admin/status/overview'] = {'action': {'type': 'alias', 'path': 'admin/home'}}
        menu.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    # The retained display settings page loads this UCI config, but the E5
    # image shipped only its write ACL. Grant the matching read permission.
    acl = root / 'usr/share/rpcd/acl.d/luci-app-e5-infoscreen.json'
    if acl.exists():
        data = json.loads(acl.read_text())
        read = data['luci-app-e5-infoscreen'].setdefault('read', {})
        configs = read.setdefault('uci', [])
        if 'e5-infoscreen' not in configs:
            configs.append('e5-infoscreen')
        acl.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/'))
    cleanup(parser.parse_args().root)

#!/usr/bin/env python3
"""Stage passive CP dump acknowledgements, without AT or radio/NV changes."""
from pathlib import Path
import os
import runpy

TOP = Path(__file__).resolve().parents[1]
source_bytes = runpy.run_path(str(TOP / 'devices/staging.py'))['source_bytes']


def stage(root):
    root = Path(root).resolve()
    if root == Path('/'):
        raise ValueError('Expected an offline root')
    service = root / 'etc/init.d/e5-modemd'
    links = [('S22e5-modemd', '../init.d/e5-modemd'), ('K09e5-modemd', '../init.d/e5-modemd')]
    # Refuse foreign entries before making any changes.
    for name, target in links:
        link = root / 'etc/rc.d' / name
        if link.is_symlink():
            if os.readlink(link) != target:
                raise ValueError('Unexpected CP recovery service link: ' + str(link))
        elif link.exists():
            raise ValueError('CP recovery service link occupied: ' + str(link))
    if service.is_symlink():
        raise ValueError('CP recovery service must not be a symlink')
    service.parent.mkdir(parents=True, exist_ok=True)
    service.write_bytes(source_bytes(TOP / 'openwrt/overlay/etc/init.d/e5-modemd'))
    service.chmod(0o755)
    for name, target in links:
        link = root / 'etc/rc.d' / name
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.is_symlink(): link.symlink_to(target)

#!/usr/bin/env python3
"""Prepare clean M8 userspace using the shared device image assembler."""
import argparse
from pathlib import Path
import runpy
TOP = Path(__file__).resolve().parents[2]
prepare = runpy.run_path(str(TOP / 'device/openwrt_device_common/shared/prepare-root.py'))['prepare']
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base','root','defaults'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    prepare(a.base, a.root, a.defaults, profile='m8')

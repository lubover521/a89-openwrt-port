#!/usr/bin/env python3
"""Collect A89-owned firmware and Android userspace; does not flash or read NV.

Identity: enforced against the identity.json recorded by collect.py from the
SAME unit (model, device, eMMC CID). Never use firmware from another device.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--backup', required=True, type=Path,
                        help='Directory created by collect.py (must contain identity.json)')
    args = parser.parse_args()
    identity = json.loads((args.backup / 'identity.json').read_text())
    cid = (args.backup / 'cid.txt').read_text().strip()
    os.environ['ANDROID_SERIAL'] = args.serial

    def prop(name):
        return subprocess.check_output(['adb', '-s', args.serial, 'shell', 'getprop', name]).strip()

    if prop('ro.product.model').decode() != identity['model'] or prop('ro.product.device').decode() != identity['device']:
        raise SystemExit('Identity mismatch: expected %s / %s' % (identity['model'], identity['device']))
    if subprocess.check_output(['adb', '-s', args.serial, 'shell',
                                'su', '-c', 'cat /sys/block/mmcblk0/device/cid']).strip().decode() != cid:
        raise SystemExit('Different physical unit; refusing to collect')
    top = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('flash', top / 'openwrt/bundle/flash.py')
    flash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(flash)
    flash.SCRIPTS = str(top)
    flash.F = str(top / 'openwrt/bundle')
    flash.ADB = shutil.which('adb')
    flash.SU = 'su'
    args.out.mkdir(parents=True, exist_ok=False)
    remote = '/data/local/tmp/a89-device-files.tar'
    flash.pull_device_files(str(args.out), remote)
    subprocess.run(['adb', '-s', args.serial, 'pull', remote, str(args.out / 'device-files.tar')], check=True)


if __name__ == '__main__':
    main()

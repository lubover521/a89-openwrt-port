#!/usr/bin/env python3
"""Collect M8-owned firmware and Android userspace; does not flash or read NV."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    os.environ['ANDROID_SERIAL'] = args.serial
    def prop(name):
        return subprocess.check_output(['adb', '-s', args.serial, 'shell', 'getprop', name]).strip()
    if prop('ro.product.model') != b'VIPME M8' or prop('ro.product.device') != b'ums9157_2h10':
        raise SystemExit('Expected VIPME M8 / ums9157_2h10')
    top = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('flash', top / 'openwrt/bundle/flash.py')
    flash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(flash)
    flash.SCRIPTS = str(top)
    flash.F = str(top / 'openwrt/bundle')
    flash.ADB = shutil.which('adb')
    flash.SU = 'su'
    args.out.mkdir(parents=True, exist_ok=False)
    remote = '/data/local/tmp/m8-device-files.tar'
    flash.pull_device_files(str(args.out), remote)
    subprocess.run(['adb', '-s', args.serial, 'pull', remote, str(args.out / 'device-files.tar')], check=True)


if __name__ == '__main__':
    main()

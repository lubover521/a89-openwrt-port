#!/usr/bin/env python3
"""Collect this unit's private firmware and Android runtime without flashing."""
import argparse
import importlib.util
import os
import shutil
from pathlib import Path
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--serial', required=True)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    os.environ['ANDROID_SERIAL'] = a.serial
    model = subprocess.check_output(['adb', 'shell', 'getprop', 'ro.product.model']).strip()
    if model != b'T551M':
        raise SystemExit('Expected a T551M')
    top = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('flash', top / 'openwrt/bundle/flash.py')
    flash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(flash)
    flash.SCRIPTS = str(top)
    flash.F = str(top / 'openwrt/bundle')
    flash.ADB = shutil.which('adb')
    flash.SU = 'su'
    a.out.mkdir(parents=True, exist_ok=False)
    remote = '/data/local/tmp/t551m-device-files.tar'
    flash.pull_device_files(str(a.out), remote)
    subprocess.run(['adb', 'pull', remote, str(a.out / 'device-files.tar')], check=True)


if __name__ == '__main__':
    main()

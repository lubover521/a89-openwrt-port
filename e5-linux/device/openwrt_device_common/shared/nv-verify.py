#!/usr/bin/python3
"""Read-only verification after the modem has booted and written runtime NV."""
import json
from pathlib import Path
import runpy
import stat

nv = runpy.run_path('/opt/e5/t551m-nv-prepare')
store = nv['STORE']
if not nv['READY'].exists():
    raise SystemExit('NV preparation did not complete')
expected = json.loads(nv['BOOT_SOURCE'].read_text())
checked = set()
for entry in Path('/sys/class/block').glob('mmcblk0p*/uevent'):
    props = dict(line.split('=', 1) for line in entry.read_text().splitlines() if '=' in line)
    name = props.get('PARTNAME')
    if name not in nv['NAMES']:
        continue
    physical = Path('/dev') / props['DEVNAME']
    if nv['digest'](physical) != expected[name] or (entry.parent / 'ro').read_text().strip() != '1':
        raise SystemExit('Factory NV changed or writable: ' + name)
    logical = Path('/dev/block/by-name') / name
    dev = logical.resolve()
    if not stat.S_ISBLK(dev.stat().st_mode) or not dev.name.startswith('loop'):
        raise SystemExit('NV is not isolated on a loop device: ' + name)
    backing = Path('/sys/class/block') / dev.name / 'loop/backing_file'
    if backing.read_text().strip() != str(store / name):
        raise SystemExit('Wrong NV backing file: ' + name)
    if name.startswith(('nr_fixnv', 'nr_runtimenv')):
        nv['validate_nv'](store / name)
    checked.add(name)
    print(name + ': original unchanged since preparation and read-only; working device verified')
if checked != set(nv['NAMES']):
    raise SystemExit('Incomplete NV verification')
print('PASS: all nine factory partitions and all working devices verified')

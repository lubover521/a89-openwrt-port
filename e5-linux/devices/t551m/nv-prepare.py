#!/usr/bin/python3
"""Give vendor daemons NV loop devices, never writable factory partitions."""
import array
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

NAMES = ('nr_fixnv1_a', 'nr_fixnv2_a', 'nr_fixnv1_b', 'nr_fixnv2_b',
         'nr_runtimenv1', 'nr_runtimenv2', 'nr_deltanv_a', 'nr_deltanv_b', 'calinv')
STORE = Path('/opt/e5/nv')
READY = Path('/run/t551m-nv-ready')
BOOT_SOURCE = Path('/run/t551m-nv-source-sha256.json')
PAIRS = (('nr_fixnv1_a', 'nr_fixnv2_a'), ('nr_fixnv1_b', 'nr_fixnv2_b'),
         ('nr_runtimenv1', 'nr_runtimenv2'))


def vendor_pids():
    result = {}
    for comm in Path('/proc').glob('[0-9]*/comm'):
        try:
            name = comm.read_text().strip()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if name in ('modem_control', 'cp_diskserver'):
            result[int(comm.parent.name)] = name
    return result


def attached_loops():
    result = {}
    for backing in Path('/sys/class/block').glob('loop*/loop/backing_file'):
        name = backing.read_text().strip()
        if name.startswith(str(STORE) + '/'):
            result[Path(name)] = Path('/dev') / backing.parents[1].name
    return result


def atomic_copy(source, target):
    temporary = target.with_name(target.name + '.tmp')
    with source.open('rb') as src, temporary.open('wb') as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if digest(temporary) != digest(source):
        raise RuntimeError('Working NV copy mismatch: ' + target.name)
    validate_nv(temporary)
    temporary.chmod(0o660)
    os.chown(temporary, target.stat().st_uid, target.stat().st_gid)
    temporary.replace(target)
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def reconcile_pair(primary, backup, attached=()):
    """The vendor reads primary, then applies identical sector deltas to both."""
    errors = {}
    for path in (primary, backup):
        try:
            validate_nv(path)
        except (RuntimeError, ValueError, struct.error, OSError) as error:
            errors[path] = str(error)
    if len(errors) == 2:
        raise RuntimeError('Both working NV copies invalid: ' + '; '.join(errors.values()))
    source = backup if primary in errors else primary
    target = primary if source == backup else backup
    if target not in errors and digest(source) == digest(target):
        return False
    if source in attached or target in attached:
        raise RuntimeError('Detach NV loops before reconciling: ' + target.name)
    atomic_copy(source, target)
    print('Reconciled isolated ' + target.name + ' from validated ' + source.name,
          '(' + errors.get(target, 'different valid contents') + ')')
    return True


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def validate_nv(path):
    with path.open('rb') as stream:
        magic, size, expected, version = struct.unpack('<4I', stream.read(16))
        # An erased runtime store is initialized by cp_diskserver on first boot.
        # Only the isolated copy may be initialized; fixed calibration must pass.
        if path.name.startswith('nr_runtimenv') and (magic, size, expected, version) == (0, 0, 0, 0):
            if any(any(block) for block in iter(lambda: stream.read(1024 * 1024), b'')):
                raise RuntimeError('Partially erased runtime NV: ' + path.name)
            return
        if magic != 0x4e56 or not 0 < size <= path.stat().st_size - 512 or size % 2:
            raise RuntimeError('Invalid NV header: ' + path.name)
        stream.seek(512)
        words = array.array('H', stream.read(size))
    # Factory 32-bit and 64-bit implementations differ on accumulator overflow.
    total = sum(words)
    checksums = []
    for value in (total, total & 0xffffffff):
        while value >> 16:
            value = (value & 0xffff) + (value >> 16)
        checksums.append(value ^ 0xffff)
    if expected not in checksums:
        raise RuntimeError('NV checksum failed: ' + path.name)


def loop_for(target):
    def find():
        for backing in Path('/sys/class/block').glob('loop*/loop/backing_file'):
            if backing.read_text().strip() == str(target):
                return Path('/dev') / backing.parents[1].name
        return None
    dev = find()
    if dev is None:
        subprocess.run(['losetup', '-f', str(target)], check=True)
        dev = find()
    if dev is None:
        raise RuntimeError('Cannot find NV loop device: ' + target.name)
    dev.chmod(0o660)
    os.chown(dev, 1000, 1000)
    return dev


def keep_working_copy(name, target, changed, refresh):
    """External OS updates do not invalidate an already isolated, valid store.

    Keep the recorded origin fingerprint: do not pretend to import new source
    data. Unchecksummed calibration/delta changes still require review, and
    missing or corrupt working copies never silently fall back to the source.
    """
    if not changed or refresh:
        return False
    if not name.startswith(('nr_fixnv', 'nr_runtimenv')) or not target.is_file():
        raise RuntimeError('Factory NV changed; explicitly refresh the working copy: ' + name)
    validate_nv(target)
    print('Source changed; retaining validated isolated working copy: ' + name)
    return True


def recover_existing_pairs(store, original, attached, refresh=False):
    """Recover interrupted isolated writes before per-file origin validation.

    Both files must already be tracked. Never adopt an unknown file or use a
    newly changed Android partition as a recovery source. Explicit refresh
    keeps its existing import path.
    """
    if refresh:
        return
    for primary, backup in PAIRS:
        if (primary in original and backup in original and
                (store / primary).is_file() and (store / backup).is_file()):
            reconcile_pair(store / primary, store / backup, attached)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Refresh working copies changed by Android; requires stopped vendor daemons and no NV loops')
    args = parser.parse_args()
    if vendor_pids():
        raise RuntimeError('Stop vendor daemons before preparing NV')
    if args.refresh:
        if attached_loops():
            raise RuntimeError('Detach NV working loops before refreshing')
    READY.unlink(missing_ok=True)
    BOOT_SOURCE.unlink(missing_ok=True)
    devices = {}
    for entry in Path('/sys/class/block').glob('mmcblk0p*/uevent'):
        props = dict(line.split('=', 1) for line in entry.read_text().splitlines() if '=' in line)
        if props.get('PARTNAME') in NAMES:
            devices[props['PARTNAME']] = Path('/dev') / props['DEVNAME']
    if set(devices) != set(NAMES):
        raise RuntimeError('Incomplete T551M NV partition map')
    # Kernel-level write protection also covers alternate block-device aliases.
    for dev in devices.values():
        with dev.open('rb') as stream:
            fcntl.ioctl(stream, 0x125d, struct.pack('i', 1))  # BLKROSET
            state = bytearray(4)
            fcntl.ioctl(stream, 0x125e, state, True)  # BLKROGET
            if struct.unpack('i', state)[0] != 1:
                raise RuntimeError('Cannot protect ' + str(dev))
    STORE.mkdir(mode=0o700, exist_ok=True)
    manifest = STORE / 'factory-sha256.json'
    original = json.loads(manifest.read_text()) if manifest.exists() else {}
    recover_existing_pairs(STORE, original, attached_loops(), args.refresh)
    boot_source = {}
    for name, dev in devices.items():
        current = digest(dev)
        boot_source[name] = current
        changed = name in original and original[name] != current
        target = STORE / name
        retained = keep_working_copy(name, target, changed, args.refresh)
        if target.exists() and name not in original and digest(target) != current:
            raise RuntimeError('Untracked NV working copy differs: ' + name)
        if not target.exists() or changed and not retained:
            temporary = STORE / (name + '.tmp')
            with dev.open('rb') as src, temporary.open('wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
            if digest(temporary) != current:
                raise RuntimeError('NV working copy mismatch: ' + name)
            if name.startswith(('nr_fixnv', 'nr_runtimenv')):
                validate_nv(temporary)
            temporary.replace(target)
        target.chmod(0o660)
        os.chown(target, 1000, 1000)
        if not retained:
            original[name] = current
    attached = attached_loops()
    for primary, backup in PAIRS:
        reconcile_pair(STORE / primary, STORE / backup, attached)
    manifest.write_text(json.dumps(original, indent=2) + '\n')
    manifest.chmod(0o600)
    Path('/dev/block/by-name').mkdir(parents=True, exist_ok=True)
    # cp_diskserver opens NV with O_TRUNC and writes only the used records.
    # A block device must retain its capacity and unwritten tail, unlike a file.
    for name in NAMES:
        link = Path('/dev/block/by-name') / name
        link.unlink(missing_ok=True)
        link.symlink_to(loop_for(STORE / name))
    # Verify physical partitions against this boot's read-only baseline, while
    # the persistent manifest continues to identify the working copies' origin.
    BOOT_SOURCE.write_text(json.dumps(boot_source, indent=2) + '\n')
    BOOT_SOURCE.chmod(0o600)
    READY.touch()
    print('T551M: factory NV read-only; validated writable working copies ready')


if __name__ == '__main__':
    main()

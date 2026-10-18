#!/usr/bin/env python3
"""Stage all matching modules plus aliases used by the existing board services."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('container_support', HERE / 'check-container-support.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


def root_owned(entry):
    entry.uid = entry.gid = 0
    entry.uname = entry.gname = 'root'
    entry.mode = 0o777 if entry.issym() else (0o755 if entry.isdir() else 0o644)
    return entry


def stage(out, root):
    release = support.check(out)
    if root.resolve() == Path('/'):
        raise ValueError('Use an offline root or a temporary staging directory')
    dest = root / 'lib/modules' / release
    if dest.exists():
        manifest = dest / 'container-support.json'
        if not manifest.is_file() or manifest.read_bytes() != (out / 'container-support.json').read_bytes():
            raise ValueError('Refusing to mix different builds of release: ' + release)
    dest.mkdir(parents=True, exist_ok=True)
    # OpenWrt kmodloader only scans the release directory's *.ko, unlike
    # libkmod's recursive module tree. Keep every dependency directly visible.
    for source in (out / 'modules').glob('*.ko'):
        shutil.copy2(source, dest / source.name)
        (dest / source.name).chmod(0o644)
    for name in ['modules.builtin', 'modules.builtin.modinfo']:
        shutil.copy2(out / name, dest / name)
        (dest / name).chmod(0o644)
    (dest / 'modules.order').write_text(''.join(p.name + '\n' for p in sorted(dest.glob('*.ko'))))
    by_name = {p.name: p for p in dest.glob('*.ko')}
    for line in (HERE / 'root-modules.txt').read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        source = by_name.get(Path(line).name)
        if source is None:
            if Path(line).name == 'snd-soc-sprd-pa-aw87xxx.ko' and 'CONFIG_SND_SOC_UNISOC_PA_AW87XXX=m' not in (out / 'config').read_text():
                continue
            raise ValueError('Required board module missing: ' + line)
        target = dest / line
        if source != target:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                target.unlink()
            target.symlink_to(os.path.relpath(source, target.parent))
    if shutil.which('depmod'):
        subprocess.run(['depmod', '-b', str(root), release], check=True)
    else:
        # macOS builders already use this image for the mainline build.
        subprocess.run(['docker', 'run', '--rm', '-v', str(root.resolve()) + ':/rootfs',
                        os.environ.get('E5_TOOLS_BUILD_IMAGE', 'e5-mainline-build'),
                        'depmod', '-b', '/rootfs', release], check=True)
    # Keep the accepted build manifest with the rootfs for deployment audits.
    shutil.copy2(out / 'container-support.json', dest / 'container-support.json')
    (dest / 'container-support.json').chmod(0o644)
    return release


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output', type=Path)
    ap.add_argument('--root', type=Path)
    args = ap.parse_args()
    if args.root:
        stage(args.output, args.root)
    else:
        with tempfile.TemporaryDirectory(prefix='root-modules-') as tmp:
            root = Path(tmp)
            release = stage(args.output, root)
            with tarfile.open(args.output / 'root-modules.tar', 'w') as tar:
                tar.add(root / 'lib', arcname='lib', filter=root_owned)
            print('Packaged complete module tree:', release)

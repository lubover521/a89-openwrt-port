#!/usr/bin/env python3
"""Apply suspend correctness fixes without changing when the system sleeps."""
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PATCHES = tuple(sorted((HERE / 'power').glob('*.patch')))


def apply(kernel):
    kernel = Path(kernel).resolve()
    paths = {line[6:].split('\t', 1)[0] for patch in PATCHES for line in patch.read_text().splitlines()
             if line.startswith('+++ b/')}
    with tempfile.TemporaryDirectory(prefix='e5-power-') as directory:
        stage = Path(directory)
        for name in paths:
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = kernel / name
            if source.exists():
                target.write_bytes(source.read_bytes())
        args = ['git', 'apply', '--whitespace=nowarn']
        for patch in reversed(PATCHES):
            if subprocess.run(args + ['--reverse', '--check', str(patch)],
                              cwd=stage, capture_output=True).returncode == 0:
                subprocess.run(args + ['--reverse', str(patch)], cwd=stage, check=True)
        for patch in PATCHES:
            result = subprocess.run(args + ['--check', str(patch)], cwd=stage,
                                    capture_output=True, text=True)
            if result.returncode:
                raise ValueError('Unsupported power source: ' + result.stderr.strip())
            subprocess.run(args + [str(patch)], cwd=stage, check=True)
        for name in paths:
            target = kernel / name
            content = (stage / name).read_bytes()
            if not target.exists() or target.read_bytes() != content:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    apply(parser.parse_args().kernel)

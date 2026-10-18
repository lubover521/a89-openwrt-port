#!/usr/bin/env python3
"""Exercise Docker on the router using its static BusyBox, without a registry.

Leaves the engine running but removes only this test's container and image.
"""
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time
import urllib.request
import uuid


def command(*args, **kwargs):
    return subprocess.check_output(args, text=True, timeout=60, **kwargs).strip()


def main():
    name = 'e5-smoke-' + uuid.uuid4().hex[:10]
    image = name + ':local'
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as tar:
        for path in ('bin', 'tmp', 'www', 'etc', 'proc', 'sys', 'dev'):
            entry = tarfile.TarInfo(path)
            entry.type = tarfile.DIRTYPE
            entry.mode = 0o1777 if path == 'tmp' else 0o755
            tar.addfile(entry)
        busybox = next((p for p in (Path('/usr/local/bin/busybox'), Path('/opt/e5/bin/busybox'))
                        if p.is_file()), None)
        if busybox is None:
            raise RuntimeError('The full static BusyBox from this image is required')
        tar.add(busybox, arcname='bin/busybox')
        for app in ('sh', 'httpd', 'wget', 'cat', 'sleep', 'nslookup'):
            entry = tarfile.TarInfo('bin/' + app)
            entry.type = tarfile.SYMTYPE
            entry.linkname = 'busybox'
            entry.mode = 0o755
            tar.addfile(entry)
        data = (name + '\n').encode()
        entry = tarfile.TarInfo('www/index.html')
        entry.size = len(data)
        entry.mode = 0o644
        tar.addfile(entry, io.BytesIO(data))
    try:
        subprocess.run(['docker', 'import', '-', image], input=archive.getvalue(),
                       check=True, timeout=60, stdout=subprocess.DEVNULL)
        command('docker', 'run', '-d', '--name', name, '--memory', '64m',
                '--memory-swap', '64m', '--cpus', '0.5', '--pids-limit', '32',
                '-p', '127.0.0.1::80', image, '/bin/httpd', '-f', '-h', '/www')
        report = command('docker', 'exec', name, '/bin/sh', '-ec',
                         'cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max '
                         '/sys/fs/cgroup/pids.max; cat /proc/self/status')
        limits = report.splitlines()
        assert limits[:3] == ['67108864', '50000 100000', '32'], report
        assert any(line.split() == ['Seccomp:', '2'] for line in limits), report
        print('PASS: memory 64 MiB, CPU 50%, pids 32 and seccomp enforced')
        swap = command('docker', 'exec', name, '/bin/cat', '/sys/fs/cgroup/memory.swap.max')
        assert swap == '0', swap
        print('PASS: per-container swap limit')
        info = json.loads(command('docker', 'inspect', name))[0]
        port = info['NetworkSettings']['Ports']['80/tcp'][0]['HostPort']
        url = 'http://127.0.0.1:' + port + '/'
        for attempt in range(20):
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    assert response.read().decode().strip() == name
                break
            except OSError:
                if attempt == 19:
                    raise
                time.sleep(0.2)
        print('PASS: bridge networking and published HTTP port')
        command('/etc/init.d/firewall', 'reload')
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.read().decode().strip() == name
        print('PASS: published port survives fw4 reload')
        command('docker', 'exec', name, '/bin/sh', '-ec',
                'wget -q -T 15 -O /tmp/network-test '
                'http://downloads.openwrt.org/releases/25.12.5/targets/armsr/armv8/sha256sums; '
                'test -s /tmp/network-test; echo persisted > /tmp/overlay-test')
        command('docker', 'restart', '-t', '1', name)
        assert command('docker', 'exec', name, '/bin/cat', '/tmp/overlay-test') == 'persisted'
        print('PASS: outbound DNS/NAT and overlay writes across restart')
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=30)
        subprocess.run(['docker', 'image', 'rm', image], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=30)


if __name__ == '__main__':
    main()

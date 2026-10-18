#!/usr/bin/env python3
"""Exercise the shipped CGCONTRDP parser and verify the patched MM hooks."""
from pathlib import Path
import os
import signal
import subprocess
import sys
import tempfile
import time

source = Path(sys.argv[1]) if len(sys.argv) > 1 else None
helper = (Path(sys.argv[2]) if len(sys.argv) > 2 else
          Path(__file__).resolve().parents[1] / 'files/modemmanager-unisoc-renew')

if source:
    base = (source / 'mm-base-bearer.c').read_text()
    modem = (source / 'mm-broadband-modem.c').read_text()
    header = (source / 'mm-broadband-modem.h').read_text()
    parser = (source / 'mm-modem-helpers.c').read_text()
    unisoc = (source / 'plugins/unisoc/mm-broadband-modem-unisoc.c').read_text()

    assert 'BEARER_UNISOC_DEFERRED_UNREGISTRATION_TIMEOUT 45' in base
    assert 'mm_base_modem_get_plugin' in base
    assert '->cgev_received (self, str)' in modem
    assert 'void (* cgev_received)' in header
    assert r'(?:,\\s*([0-9]+))?' in parser
    assert 'UNISOC_BEARER_EVENT_FIFO' in unisoc
    assert 'sppcodata_received' in unisoc

fixture = """response: '+CGCONTRDP: 1,6,3gnet,10.208.154.13.255.0.0.0,,58.20.127.238,58.20.159.152,,,,,0
+CGCONTRDP: 1,6,3gnet,0.0.0.0.0.0.0.0.0.0.0.0.35.152.165.225.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0,,36.8.128.1.32.0.0.3.0.0.0.0.0.0.255.255,36.8.128.1.32.0.0.3.0.0.0.0.0.0.238.238'\n"""

with tempfile.TemporaryDirectory(prefix='e5-mobility-') as directory:
    root = Path(directory)
    (root / 'lib/netifd').mkdir(parents=True)
    (root / 'lib/functions.sh').write_text('# test stub\n')
    (root / 'lib/netifd/netifd-proto.sh').write_text('# test stub\n')
    bindir = root / 'bin'
    bindir.mkdir()
    mmcli = bindir / 'mmcli'
    mmcli.write_text("#!/bin/sh\ncat <<'EOF'\n" + fixture + "EOF\n")
    mmcli.chmod(0o755)
    env = os.environ.copy()
    env.update({
        'PATH': str(bindir) + os.pathsep + env['PATH'],
        'MODEMMANAGER_UNISOC_LIB_ROOT': str(root),
        'MODEMMANAGER_UNISOC_TEST_PARSE': '1',
    })
    result = subprocess.run(
        ['sh', str(helper), 'wan', 'unisoc-sipc', '/bearer/1', 'sipa_eth0',
         '1', '10.0.0.1', '8', '', '1.1.1.1', '2.2.2.2', '10'],
        check=True, text=True, capture_output=True, env=env)
    assert result.stdout.strip() == '10.208.154.13|8||58.20.127.238|58.20.159.152'

    # Exercise the complete event path as well as the parser.  This catches
    # shell, FIFO and route-update regressions without touching a real bearer.
    trace = root / 'trace'
    (root / 'lib/netifd/netifd-proto.sh').write_text(
        'proto_init_update() { echo "proto init $*" >>"$TRACE"; }\n'
        'proto_set_keep() { echo "proto keep $*" >>"$TRACE"; }\n'
        'proto_add_ipv4_address() { echo "proto address $*" >>"$TRACE"; }\n'
        'proto_add_ipv4_route() { echo "proto route $*" >>"$TRACE"; }\n'
        'proto_add_dns_server() { echo "proto dns $*" >>"$TRACE"; }\n'
        'json_add_int() { echo "proto int $*" >>"$TRACE"; }\n'
        'proto_send_update() { echo "proto update $*" >>"$TRACE"; }\n')
    mmcli.write_text(
        '#!/bin/sh\n'
        '[ "$CGACT_MODE" != error ] || exit 1\n'
        'case "$*" in\n'
        '  *CGACT*) printf "+CGACT:1,%s\\r\\n+CGACT:11,1\\n" "${CGACT_MODE:-1}" ;;\n'
        '  *CGCONTRDP*) cat <<\'EOF\'\n' + fixture + 'EOF\n  ;;\n'
        'esac\n')
    ip = bindir / 'ip'
    ip.write_text('#!/bin/sh\necho "ip $*" >>"$TRACE"\n')
    ip.chmod(0o755)
    logger = bindir / 'logger'
    logger.write_text('#!/bin/sh\necho "logger $*" >>"$TRACE"\n')
    logger.chmod(0o755)
    env.pop('MODEMMANAGER_UNISOC_TEST_PARSE')
    env['TRACE'] = str(trace)
    fifo = root / 'events'
    env['MODEMMANAGER_UNISOC_EVENT_FIFO'] = str(fifo)
    daemon = subprocess.Popen(
        ['sh', str(helper), 'wan', 'unisoc-sipc', '/bearer/1', 'sipa_eth0',
         '1', '10.0.0.1', '8', '', '1.1.1.1', '2.2.2.2', '10'], env=env)
    try:
        for _ in range(50):
            if fifo.exists():
                break
            time.sleep(0.02)
        assert fifo.exists(), 'mobility event FIFO was not created'
        with fifo.open('w') as stream:
            stream.write('cgev NW MODIFY 1,8\n')
        for _ in range(100):
            if trace.exists() and 'proto update wan' in trace.read_text():
                break
            time.sleep(0.03)
        output = trace.read_text()
        assert 'ip -4 addr add 10.208.154.13/8 dev sipa_eth0' in output
        assert 'proto route 0.0.0.0 0  10.208.154.13' in output
        assert 'ip -4 route' not in output, 'netifd must retain ownership of routing policy'
        assert 'proto address 10.208.154.13 255.0.0.0' in output
        assert 'proto keep 0' in output, 'old IP/DNS must be replaced, not accumulated'
        assert 'proto update wan' in output
        assert output.index('ip -4 addr add') < output.index('proto update wan')
        for _ in range(50):
            if 'ip -4 addr del' in trace.read_text():
                break
            time.sleep(0.02)
        output = trace.read_text()
        assert output.index('proto update wan') < output.index('ip -4 addr del 10.0.0.1/8')
    finally:
        daemon.send_signal(signal.SIGTERM)
        daemon.wait(timeout=5)
    assert not fifo.exists(), 'FIFO survived teardown'

    for mode in ('error', '0'):
        env['CGACT_MODE'] = mode
        daemon = subprocess.Popen(
            ['sh', str(helper), 'wan', 'unisoc-sipc', '/bearer/1', 'sipa_eth0',
             '1', '10.0.0.1', '8', '', '1.1.1.1', '2.2.2.2', '10'], env=env)
        try:
            for _ in range(50):
                if fifo.exists():
                    break
                time.sleep(0.02)
            with fifo.open('w') as stream:
                stream.write('cgev NW PDN DEACT 1\n')
            if mode == 'error':
                time.sleep(1.5)
                assert daemon.poll() is None, 'AT failure incorrectly disconnected WAN'
            else:
                assert daemon.wait(timeout=10) == 2, 'inactive context lost its reconnect exit status'
        finally:
            if daemon.poll() is None:
                daemon.send_signal(signal.SIGTERM)
                daemon.wait(timeout=5)
        assert not fifo.exists(), 'FIFO survived teardown'

print('PASS: mobility address renewal, AT-failure isolation, inactive-context recovery and cleanup'
      + ('; compiled source hooks verified' if source else ''))

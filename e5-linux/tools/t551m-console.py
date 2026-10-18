#!/usr/bin/env python3
"""Send diagnostic commands over the T551M Linux USB ACM console (pyserial)."""
import argparse
from pathlib import Path
import sys
import time
import serial
from serial.tools import list_ports


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--port')
    ap.add_argument('--timeout', type=float, default=15)
    a = ap.parse_args()
    ports = [p.device for p in list_ports.comports() if p.vid == 0x0525 and p.pid in (0xa4a1, 0xa4a2, 0xa4a3)]
    if not a.port and len(ports) != 1:
        raise SystemExit('Expected one Linux ACM console; use --port')
    with serial.Serial(a.port or ports[0], 115200, timeout=.2) as s:
        s.reset_input_buffer()
        s.write(b'\n')
        time.sleep(.5)
        s.write((a.command + '; echo __T551M_""DONE__\n').encode())
        end = time.monotonic() + a.timeout
        data = b''
        while time.monotonic() < end:
            data += s.read(65536)
            if b'\n__T551M_DONE__' in data:
                break
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_bytes(data)
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(data.decode(errors='replace').replace('\r', ''))
    if b'\n__T551M_DONE__' not in data:
        raise SystemExit('Console command timed out')


if __name__ == '__main__':
    main()

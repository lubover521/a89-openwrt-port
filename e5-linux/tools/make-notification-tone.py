#!/usr/bin/env python3
"""Generate an original, gently decaying notification ding (no sampled audio)."""
from pathlib import Path
import math
import struct

def make():
    rate, duration = 32000, .8
    frames = int(rate * duration)
    samples = []
    for i in range(frames):
        t = i / rate
        attack = min(1, t / .005)
        tail = min(1, (duration - t) / .04)
        value = (.28 * math.sin(2 * math.pi * 1318.51 * t) * math.exp(-t * 7)
                 + .10 * math.sin(2 * math.pi * 1977.77 * t) * math.exp(-t * 11)
                 + .045 * math.sin(2 * math.pi * 2638.1 * t) * math.exp(-t * 17))
        samples.append(round(32767 * value * attack * tail))
    pcm = struct.pack('<' + 'h' * frames, *samples)
    return b'RIFF' + struct.pack('<I', len(pcm) + 36) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) + b'data' + struct.pack('<I', len(pcm)) + pcm

if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1] / 'openwrt/overlay/usr/share/e5/ding.wav'
    output.write_bytes(make())
    print(output)

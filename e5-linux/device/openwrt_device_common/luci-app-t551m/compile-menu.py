#!/usr/bin/env python3
"""Compile this app's simple, non-plural menu PO catalogs to LuCI LMO.

Format/hash follows OpenWrt luci-base src/po2lmo.c and src/lib/lmo.c.
Fail on unsupported PO constructs rather than silently dropping translations.
"""
import ast
from pathlib import Path
import struct


def sfh(value):
    data = value.encode('utf-8')
    h, pos = len(data), 0
    mask = 0xffffffff
    for pos in range(0, len(data) - len(data) % 4, 4):
        h = (h + int.from_bytes(data[pos:pos+2], 'little')) & mask
        tmp = (int.from_bytes(data[pos+2:pos+4], 'little') << 11) ^ h
        h = ((h << 16) ^ tmp) & mask
        h = (h + (h >> 11)) & mask
    pos = len(data) - len(data) % 4
    rem = len(data) % 4
    signed = lambda b: b if b < 128 else b - 256
    if rem == 3:
        h = (h + int.from_bytes(data[pos:pos+2], 'little')) & mask
        h = (h ^ (h << 16)) & mask
        h = (h ^ (signed(data[pos+2]) << 18)) & mask
        h = (h + (h >> 11)) & mask
    elif rem == 2:
        h = (h + int.from_bytes(data[pos:pos+2], 'little')) & mask
        h = (h ^ (h << 11)) & mask
        h = (h + (h >> 17)) & mask
    elif rem == 1:
        h = (h + signed(data[pos])) & mask
        h = (h ^ (h << 10)) & mask
        h = (h + (h >> 1)) & mask
    for left, right in ((3, 5), (4, 17), (25, 6)):
        h = (h ^ (h << left)) & mask
        h = (h + (h >> right)) & mask
    return h if data else 0


def compile_po(path):
    entries, current, field = [], {}, None
    for line in path.read_text(encoding='utf-8').splitlines() + ['msgid ""']:
        if line.startswith('msgid '):
            if current.get('id'):
                if not current.get('str'):
                    raise ValueError('Missing menu translation')
                entries.append((current['id'], current['str']))
            current, field = {}, 'id'
            current[field] = ast.literal_eval(line[6:])
        elif line.startswith('msgstr '):
            field = 'str'
            current[field] = ast.literal_eval(line[7:])
        elif line.startswith('"'):
            if not field:
                raise ValueError('Invalid PO continuation')
            current[field] += ast.literal_eval(line)
        elif line and not line.startswith('#'):
            raise ValueError('Unsupported PO syntax: ' + line)
    payload, index = bytearray(), []
    for key, value in entries:
        data = value.encode('utf-8')
        if sfh(key) == sfh(value):
            continue
        index.append((sfh(key), 1, len(payload), len(data)))
        payload.extend(data + b'\0' * (-len(data) % 4))
    offset = len(payload)
    for entry in sorted(index):
        payload.extend(struct.pack('!IIII', *entry))
    payload.extend(struct.pack('!I', offset))
    return bytes(payload)


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    for language in ('en', 'tr'):
        target = root / 'lmo' / ('mu300.' + language + '.lmo')
        target.write_bytes(compile_po(root / 'po' / language / 'mu300.po'))
        print('Compiled', target.name)

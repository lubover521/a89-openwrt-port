#!/usr/bin/python3
"""Read each SIM through existing AT owners; never change the data SIM or RF.

Separate card snapshots avoid ModemManager's shared access-technology/signal
cache mixing a standby NR card into the data card's LTE display.
"""
import csv
import json
from pathlib import Path
import re
import signal
import socket
import threading
import time

RUN = Path('/run/t551m-sims.json')
CARD = Path('/sys/module/sipc_wwan/parameters/card')


def query(card, command):
    # The card selection and read are one AT transaction on an existing owner.
    request = {'command': f'AT+SPACTCARD={card};{command}', 'timeout': 2,
               'deadline': time.monotonic() + 5}
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(6)
        client.connect(f'/run/t551m-at{6 + card}/cmd.sock')
        client.sendall((json.dumps(request) + '\n').encode())
        data = b''
        while not data.endswith(b'\n'):
            block = client.recv(4096)
            if not block: raise RuntimeError('AT owner disconnected')
            data += block
            if len(data) > 131072: raise RuntimeError('AT response too large')
    result = json.loads(data)
    if not result.get('ok'): raise RuntimeError(result.get('error', 'AT unavailable'))
    return result['response']


def field(reply, prefix):
    for line in reply.splitlines():
        if line.startswith(prefix + ':'):
            return next(csv.reader([line.split(':', 1)[1].strip()], skipinitialspace=True))
    return []


def registration(reply, prefix):
    parts = field(reply, prefix)
    # Query replies start with reporting mode, then registration state.
    return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None


def operator_name(reply):
    parts = field(reply, '+COPS')
    if len(parts) < 3 or not parts[2]: return None
    name = parts[2]
    # Read the charset and name in one AT transaction. Do not change CSCS:
    # other users of the modem (including SMS) may require UCS2.
    charset = field(reply, '+CSCS')
    if parts[1] in ('0', '1') and charset and charset[0].upper() == 'UCS2' and re.fullmatch(r'(?:[0-9a-fA-F]{4})+', name):
        try:
            decoded = bytes.fromhex(name).decode('utf-16-be')
            if not any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in decoded):
                return decoded
        except UnicodeDecodeError:
            pass  # Preserve malformed input; never lose the rest of this SIM snapshot.
    return name


def radio(act, lte, nr):
    # Serving NR measurements distinguish NSA from an LTE-only connection.
    if nr.get('rsrp') is not None:
        return '5gnr', '5G NSA' if lte.get('rsrp') is not None else '5G SA'
    if act == 13: return '5gnr', '5G NSA'
    if act in (11, 18, 19): return '5gnr', '5G'
    if act in (7, 10): return 'lte', '4G'
    if act in (2, 3, 4, 5, 6): return 'umts', '3G'
    if act in (0, 1): return 'gsm', '2G'
    return None, None


def lte_sinr(reply):
    # Same LTE PHY field and centi-dB scale as the dashboard's cell collector.
    # Unisoc uses '-' separators, '--' for a negative scalar, and '+abs' on
    # some firmware. Ignore echoes/errors and reject unavailable/outlier values.
    for line in reply.splitlines():
        line = line.strip().replace(' ', '').replace(',-', ',+').replace('--', '-+')
        if line.startswith('-'): line = '+' + line[1:]
        fields = line.split('-')
        if len(fields) < 7 or not all(re.fullmatch(r'\+?\d+', x) for x in fields[:2]):
            continue
        value = fields[2].split(',')[0]
        if not re.fullmatch(r'\+?\d+', value): return None
        value = -int(value[1:]) if value.startswith('+') else int(value)
        return round(value / 100, 1) if -2000 <= value <= 4000 else None
    return None


def collect(card, read=query):
    row = {'slot': card, 'updated': time.monotonic(), 'present': None,
           'registration': 'unknown', 'operator': None, 'tech': None,
           'radio_label': None, 'signal': {}, 'error': None}
    try:
        pin_reply = read(card, '+CPIN?')
        pin = field(pin_reply, '+CPIN')
        if field(pin_reply, '+CME ERROR') == ['10'] or (pin and pin[0] in ('NOT INSERTED', 'SIM NOT INSERTED')):
            row.update(present=False, registration='absent');return row
        if not pin: raise RuntimeError('SIM status unavailable')
        row['present'] = True
        if pin[0] != 'READY':
            row.update(registration='locked', pin=pin[0]);return row
        power = field(read(card, '+CFUN?'), '+CFUN')
        if power and power[0] != '1':
            row['registration'] = 'disabled';return row
        operator_reply = read(card, '+CSCS?;+COPS?')
        cops = field(operator_reply, '+COPS')
        row['operator'] = operator_name(operator_reply)
        act = int(cops[3]) if len(cops) >= 4 and cops[3].isdigit() else None
        row['act'] = act
        reg = registration(read(card, '+CEREG?'), '+CEREG')
        reg5 = registration(read(card, '+C5GREG?'), '+C5GREG')
        row.update(reg=reg, reg5g=reg5)
        values = field(read(card, '+CESQ'), '+CESQ')
        v = [int(n) for n in values] + [255] * 9
        lte = {'rsrp': v[5]-141 if 0 <= v[5] <= 97 else None,
               'rsrq': v[4]*.5-20 if 0 <= v[4] <= 34 else None}
        nr = {'rsrp': v[7]-157 if 0 <= v[7] <= 126 else None,
              'rsrq': v[6]*.5-43 if 0 <= v[6] <= 127 else None,
              'snr': v[8]*.5-23 if 0 <= v[8] <= 127 else None}
        row['tech'], row['radio_label'] = radio(act, lte, nr)
        row['signal'] = nr if row['tech'] == '5gnr' else lte
        if row['tech'] == 'lte' and lte['rsrp'] is not None:
            # CESQ has no LTE SINR. Keep it fresh even when LuCI is closed,
            # within the existing per-card background round (never HTTP).
            try:
                lte['snr'] = lte_sinr(read(card, '+SPENGMD=0,0,6'))
            except (OSError, ValueError, RuntimeError):
                lte['snr'] = None  # An optional PHY failure must not hide registration/RSRP.
        state = reg5 if reg5 in (1, 5) else reg
        row['registration'] = {0:'idle', 1:'home', 2:'searching', 3:'denied', 4:'unknown', 5:'roaming', 8:'emergency'}.get(state, 'unknown')
        if state is None and row['operator'] and row['signal'].get('rsrp') is not None:
            row['registration'] = 'camped'  # Evidence of camping, not a fabricated registration reply.
    except (OSError, ValueError, RuntimeError) as error:
        row.update(error=str(error), registration='unknown', tech=None, radio_label=None, signal={})
    return row


def main():
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):signal.signal(sig, lambda *_:stop.set())
    while not stop.is_set():
        started = time.monotonic()
        try:
            active = int(CARD.read_text().strip())
            rows = [collect(0), collect(1)]
            if int(CARD.read_text().strip()) != active:continue
            data = {'updated': time.monotonic(), 'active': active, 'sims': rows}
            tmp = RUN.with_suffix('.part');tmp.write_text(json.dumps(data));tmp.replace(RUN)
        except (OSError, ValueError):pass
        stop.wait(max(.1, 5 - (time.monotonic() - started)))


if __name__ == '__main__':main()

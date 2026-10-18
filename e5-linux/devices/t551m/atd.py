#!/usr/bin/python3
"""T551M secondary AT owner; MU300's persistent-channel/serialized-reply design.

Keep nr2 (interactive) and nr6/nr7 (collector pool) open once, independently.
nr0/nr1/nr3 remain owned by sipc_wwan/ModemManager for network/SMS/URCs.
Use a root-only socket instead of polling reply files. Never retry a write or
reopen on a timeout. Missing finals require late completion or named read-only
recovery probes before another user command can run.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import select
import socket
import sys
import termios
import time
import tty

CHANNELS = (2, 6, 7)
FINAL = re.compile(rb'^(?:OK|ERROR|\+CM[ES] ERROR(?::.*)?|CONNECT(?: .*)?|NO CARRIER|BUSY|NO ANSWER)$')


class Channel:
    def __init__(self, fd, gap=0.1):
        self.fd, self.gap = fd, gap
        self.pending = b''
        self.synchronized = True
        self.last_write = 0.0
        self.failed_at = None

    def lines(self, wait):
        if not select.select([self.fd], [], [], max(0, wait))[0]:
            return []
        data = os.read(self.fd, 4096)
        if not data:
            raise OSError('AT channel disconnected')
        self.pending += data
        if len(self.pending) > 131072:
            raise OSError('AT response exceeds limit')
        parts = self.pending.split(b'\n')
        self.pending = parts.pop()
        return [line.strip(b'\r') for line in parts if line.strip(b'\r')]

    def idle(self, wait=0):
        for line in self.lines(wait):
            if FINAL.fullmatch(line):
                self.synchronized = True

    def command(self, command, timeout):
        # A late terminal can restore sync here; otherwise serve() must finish
        # recover() first. Silence alone never proves a command has finished.
        self.idle()
        if not self.synchronized:
            raise TimeoutError('Previous AT command has not finished; channel quarantined')
        time.sleep(max(0, self.last_write + self.gap - time.monotonic()))
        payload = command.encode('ascii') + b'\r'
        self.synchronized = False
        if os.write(self.fd, payload) != len(payload):
            raise OSError('Short AT write; command will not be retried')
        self.last_write = time.monotonic()
        end, lines, size = self.last_write + timeout, [], 0
        while time.monotonic() < end:
            batch = self.lines(end - time.monotonic())
            for line in batch:
                lines.append(line.decode('utf-8', errors='replace'))
                size += len(line)
                if size > 131072:
                    raise OSError('AT response exceeds limit')
                if FINAL.fullmatch(line):
                    self.synchronized = True
                    self.failed_at = None
                    return '\n'.join(lines) + '\n'
        self.failed_at = time.monotonic()
        raise TimeoutError('Modem returned no final response; awaiting late reply')

    def recover(self):
        """Re-establish framing with two named read replies; never retry a write.

        Some firmware setters omit their terminal response. Silence alone is
        not a boundary: ignore old terminals until each probe's payload arrives.
        Keep the same descriptor, including when recovery fails.
        """
        self.idle()
        if self.synchronized:
            return
        if self.failed_at is not None and time.monotonic() - self.failed_at < 2:
            raise TimeoutError('Previous AT command is still pending')
        for command, pattern in [
                (b'AT+CFUN?\r', re.compile(rb'^\+CFUN:\s*[0-9]+\s*$')),
                (b'AT+CSQ\r', re.compile(rb'^\+CSQ:\s*[0-9]+\s*,\s*[0-9]+\s*$'))]:
            self.idle()
            self.synchronized = False
            time.sleep(max(0, self.last_write + self.gap - time.monotonic()))
            self.last_write = time.monotonic()
            if os.write(self.fd, command) != len(command):
                raise OSError('Short recovery probe write')
            deadline, payload, complete = time.monotonic() + 3, False, False
            while time.monotonic() < deadline and not complete:
                for line in self.lines(deadline - time.monotonic()):
                    if pattern.fullmatch(line):
                        payload = True
                    elif payload and line == b'OK':
                        complete = True
                    elif payload and FINAL.fullmatch(line):
                        raise TimeoutError('Read-only AT recovery probe rejected')
            if not complete:
                self.failed_at = time.monotonic()
                raise TimeoutError('AT recovery did not receive a complete named reply')
        self.synchronized = True
        self.failed_at = None


def validate(request):
    if not isinstance(request, dict):
        raise ValueError('Expected a request object')
    command, timeout = request.get('command'), request.get('timeout', 8)
    deadline = request.get('deadline')
    if (not isinstance(command, str) or not command.upper().startswith('AT')
            or len(command) > 1024 or any(ord(c) < 32 or ord(c) > 126 for c in command)):
        raise ValueError('Expected one ASCII AT command without control characters')
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 60:
        raise ValueError('Timeout must be 1..60 seconds')
    if not isinstance(deadline, (int, float)) or not time.monotonic() < deadline <= time.monotonic() + 90:
        raise ValueError('Request expired before execution')
    return command, timeout


def address_card(command, card):
    if command.upper().startswith('AT+') and not command.upper().startswith('AT+SPACTCARD'):
        return f'AT+SPACTCARD={card};' + command[2:]
    return command


def runtime(number):
    if number not in CHANNELS:
        raise ValueError('Only dedicated channels nr2, nr6 and nr7 are allowed')
    return Path(f'/run/t551m-at{number}')


def serve(number):
    os.umask(0o077)
    directory = runtime(number)
    directory.mkdir(mode=0o700, exist_ok=True)
    # flock is atomic, released by the kernel on exit, and acquired BEFORE open.
    # Keep its inode forever: unlinking a lock allows two independent owners.
    owner = (directory / 'owner.lock').open('a')
    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
    wwan = Path('/sys/class/wwan/wwan0at0')
    until = time.monotonic() + 120
    while not wwan.exists() and time.monotonic() < until:
        time.sleep(1)
    generation = wwan.stat().st_ino
    params = Path('/sys/module/sipc_wwan/parameters')
    owned = [int((params / p).read_text().strip()) for p in ('cmd_ring', 'urc_ring')]
    owned += [int(n) for n in (params / 'drain_rings').read_text().strip().split(',') if n]
    if number in owned:
        raise RuntimeError(f'nr{number} is already owned by sipc_wwan')
    fd = os.open(f'/dev/stty_nr{number}', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        tty.setraw(fd, termios.TCSANOW)
    except termios.error:
        pass  # spipe character devices have no termios
    channel = Channel(fd)
    # Only initial attach drains for one quiet second. Successful commands do
    # not pay that delay again. No URC rings are opened by this service.
    end = time.monotonic() + 3
    while time.monotonic() < end and select.select([fd], [], [], 1)[0]:
        channel.idle()
    endpoint = directory / 'cmd.sock'
    endpoint.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(endpoint))
    server.listen(8)
    print(f't551m-atd: nr{number} open; independent queue, {channel.gap * 1000:.0f}ms pacing', flush=True)
    while True:
        # sipc_wwan removes/recreates this sysfs port on an actual CP reset.
        # This is evidence to reattach, unlike silence or a missing URC log.
        if wwan.stat().st_ino != generation:
            raise OSError('CP channel generation changed')
        readable = select.select([server, fd], [], [], 1)[0]
        if fd in readable:
            channel.idle()
        if server not in readable:
            continue
        client, _ = server.accept()
        with client:
            client.settimeout(1)
            data = b''
            request_data = {}
            try:
                while b'\n' not in data:
                    block = client.recv(2048)
                    if not block:
                        raise ValueError('Client disconnected before request')
                    data += block
                    if len(data) > 4096:
                        raise ValueError('Request too large')
                request_data = json.loads(data.split(b'\n', 1)[0])
                command, timeout = validate(request_data)
                # A client killed while waiting must not leave a queued write.
                if select.select([client], [], [], 0)[0] and not client.recv(1, socket.MSG_PEEK):
                    continue
                if not channel.synchronized:
                    channel.recover()
                    # Recovery may have consumed the queued request's budget.
                    command, timeout = validate(request_data)
                card = int((params / 'card').read_text())
                if card not in (0, 1):
                    raise ValueError('Unknown active SIM card')
                reply = channel.command(address_card(command, card), timeout)
                result = {'ok': True, 'response': reply}
            except (ConnectionResetError, BrokenPipeError):
                continue
            except (ValueError, TimeoutError, UnicodeError) as error:
                result = {'ok': False, 'error': str(error)}
            # Device I/O errors deliberately terminate the owner: procd may
            # reattach after a real disconnect. Timeouts never reopen a ring.
            try:
                # Small native clients need no JSON parser. Still send only
                # complete responses, with an explicit transport status.
                if isinstance(request_data, dict) and request_data.get('plain') is True:
                    payload = ('0\n' + result['response'] if result['ok'] else '1\n' + result['error'])
                    client.sendall(payload.encode('utf-8'))
                else:
                    client.sendall(json.dumps(result).encode() + b'\n')
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                pass


def request(command, timeout, number=2):
    # Bounded queue wait plus the command's own deadline, no shell/fifo polling.
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(timeout + 13)
        client.connect(str(runtime(number) / 'cmd.sock'))
        client.sendall(json.dumps({'command': command, 'timeout': timeout,
                                  'deadline': time.monotonic() + 12}).encode() + b'\n')
        data = b''
        while b'\n' not in data:
            block = client.recv(16384)
            if not block:
                raise OSError('AT daemon disconnected')
            data += block
            if len(data) > 262144:
                raise ValueError('AT response too large')
        result = json.loads(data)
        if not result['ok']:
            raise RuntimeError(result['error'])
        print(result['response'], end='')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--channel', type=int, choices=CHANNELS,
                        default=int(os.environ.get('T551M_AT_CHANNEL', '2')))
    parser.add_argument('-t', type=int, default=8)
    parser.add_argument('command', nargs='?')
    args = parser.parse_args()
    try:
        if args.serve:
            serve(args.channel)
        elif args.command:
            request(args.command, args.t, args.channel)
        else:
            parser.error('AT command required')
    except (OSError, RuntimeError, ValueError) as error:
        print('t551m-at: ' + str(error), file=sys.stderr)
        sys.exit(1)

"""Bounded loopback GET transport for the local screen, over one WebSocket.

The caller validates Host/Origin before entering. No shell, remote destination,
POST replay, background polling, or state cache is involved.
"""
import base64
import hashlib
import http.client
import json
import select
import socket
import struct
import threading
from concurrent.futures import ThreadPoolExecutor


def serve(handler, owner):
    headers = handler.headers
    try:
        key = headers.get('Sec-WebSocket-Key', '')
        assert len(base64.b64decode(key, validate=True)) == 16
        assert headers.get('Upgrade', '').lower() == 'websocket'
        assert 'upgrade' in [v.strip().lower() for v in headers.get('Connection', '').split(',')]
        assert headers.get('Sec-WebSocket-Version') == '13'
    except (ValueError, AssertionError):
        handler.send_error(400)
        return
    sock = handler.connection
    accept = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
    handler.send_response(101)
    handler.send_header('Upgrade', 'websocket')
    handler.send_header('Connection', 'Upgrade')
    handler.send_header('Sec-WebSocket-Accept', accept)
    handler.end_headers()
    handler.wfile.flush()
    handler.close_connection = True
    write_lock = threading.Lock()
    work_lock = threading.Lock()
    pending = set()
    stopped = threading.Event()
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='screen-get')
    power = None
    with owner.condition:
        if owner.closed:
            executor.shutdown(wait=False)
            return
        owner.rpc_sockets.add(sock)

    def send(opcode, data):
        with write_lock:
            if stopped.is_set():
                return
            length = len(data)
            header = bytes([0x80 | opcode])
            header += bytes([length]) if length < 126 else b'\x7e' + struct.pack('!H', length) if length < 65536 else b'\x7f' + struct.pack('!Q', length)
            sock.sendall(header + data)

    def reply(value):
        send(1, json.dumps(value, separators=(',', ':')).encode())

    def request(request_id, path):
        connection = http.client.HTTPConnection('127.0.0.1', 8088, timeout=8)
        try:
            connection.request('GET', path, headers={'Accept': 'application/json', 'Cache-Control': 'no-cache'})
            response = connection.getresponse()
            content_type = response.getheader('Content-Type', '')
            if 'application/json' not in content_type.lower():
                raise ValueError('Not a JSON endpoint')
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise ValueError('Response too large')
            reply({'id': request_id, 'status': response.status, 'type': content_type,
                   'body': body.decode('utf-8')})
        except (OSError, ValueError, http.client.HTTPException):
            try:
                reply({'id': request_id, 'fallback': True})
            except OSError:
                stopped.set()
        finally:
            connection.close()
            with work_lock:
                pending.discard(request_id)

    def read(length):
        result = bytearray()
        while len(result) < length:
            chunk = handler.rfile.read(length - len(result))
            if not chunk:
                raise EOFError
            result.extend(chunk)
        return bytes(result)

    try:
        try:
            from e5_power_events import PowerEvents
            power = PowerEvents()
        except (OSError, AttributeError):
            pass  # Non-Linux/test hosts: existing status polling still works.
        fragments = bytearray()
        fragmented = False
        while not owner.closed and not stopped.is_set():
            # No periodic wake when idle. The service's close() shuts the socket.
            ready = select.select([sock, power.socket] if power else [sock], [], [], None)[0]
            if power and power.socket in ready:
                try:
                    if power.receive():
                        reply({'event': 'power-supply-change'})
                except OSError:
                    power.close()
                    power = None  # Preserve RPC and the status-based fallback.
            if sock not in ready:
                continue
            first, second = read(2)
            final, opcode, length = bool(first & 128), first & 15, second & 127
            if first & 112 or not second & 128:
                break
            if length == 126:
                length = struct.unpack('!H', read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', read(8))[0]
            if length > 8192 or (opcode >= 8 and (not final or length > 125)):
                break
            mask = read(4)
            data = bytes(value ^ mask[i % 4] for i, value in enumerate(read(length)))
            if opcode == 8:
                send(8, data)
                break
            if opcode == 9:
                send(10, data)
                continue
            if opcode == 10:
                continue
            if opcode == 1 and not fragmented:
                fragments = bytearray(data)
            elif opcode == 0 and fragmented:
                fragments.extend(data)
            else:
                break
            if len(fragments) > 8192:
                break
            fragmented = not final
            if fragmented:
                continue
            message = json.loads(fragments.decode('utf-8'))
            fragments.clear()
            request_id, path = message.get('id'), message.get('path')
            if (type(request_id) is not int or not 0 < request_id < 2**53
                    or not isinstance(path, str) or not path.startswith('/api/')
                    or len(path) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in path)
                    or '#' in path or '\\' in path or '/..' in path):
                break
            with work_lock:
                if request_id in pending:
                    break
                busy = len(pending) >= 8
                if not busy:
                    pending.add(request_id)
            if busy:
                reply({'id': request_id, 'fallback': True})
            else:
                executor.submit(request, request_id, path)
    except (OSError, EOFError, ValueError, AttributeError):
        pass
    finally:
        if power:
            power.close()
        stopped.set()
        with owner.condition:
            owner.rpc_sockets.discard(sock)
        executor.shutdown(wait=False, cancel_futures=True)

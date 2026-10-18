"""Local, bounded call-state stream; no modem queries or periodic UI polling."""
import json
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ORIGIN = 'http://127.0.0.1:8088'


def stable(value):
    # Freshness timestamps change on every observer tick, not call state.
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k != 'updated'}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


class CallEvents:
    def __init__(self, port=8089):
        self.condition = threading.Condition()
        self.closed = False
        self.revision = 0
        self.payload = b'{"error":"Call observer is starting","calls":[]}'
        self.slots = threading.BoundedSemaphore(6)
        self.rpc_sockets = set()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            rbufsize = 0  # WebSocket select must not miss frames buffered by rfile.

            def log_message(self, *args):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def do_GET(self):
                if (self.path not in ('/events', '/rpc') or self.headers.get('Origin') != ORIGIN
                        or self.headers.get('Host') != '127.0.0.1:' + str(owner.port)):
                    self.send_error(403)
                    return
                if self.path == '/rpc':
                    from e5_screen_rpc import serve
                    return serve(self, owner)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Access-Control-Allow-Origin', ORIGIN)
                self.send_header('Vary', 'Origin')
                self.send_header('Connection', 'close')
                self.end_headers()
                revision = -1
                try:
                    while True:
                        with owner.condition:
                            owner.condition.wait_for(
                                lambda: owner.closed or owner.revision != revision, timeout=30)
                            if owner.closed:
                                break
                            changed = owner.revision != revision
                            revision, payload = owner.revision, owner.payload
                        # No queue per client: a slow/disconnected reader cannot
                        # retain an unbounded history. Initial state is immediate.
                        self.wfile.write(b'data: ' + payload + b'\n\n' if changed else b': alive\n\n')
                        self.wfile.flush()
                except (OSError, TimeoutError):
                    pass
                self.close_connection = True

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            block_on_close = False

            def process_request(self, request, address):
                if not owner.slots.acquire(blocking=False):
                    self.shutdown_request(request)
                    return
                try:
                    super().process_request(request, address)
                except Exception:
                    owner.slots.release()
                    raise

            def process_request_thread(self, request, address):
                try:
                    super().process_request_thread(request, address)
                finally:
                    owner.slots.release()

        self.server = Server(('127.0.0.1', port), Handler)
        self.port = self.server.server_address[1]
        self.wake_read, self.wake_write = socket.socketpair()
        self.thread = threading.Thread(target=self.serve, daemon=True, name='call-events')
        self.thread.start()

    def serve(self):
        # Block indefinitely when idle; shutdown has a dedicated wake FD.
        while not self.closed:
            ready, _, _ = select.select([self.server, self.wake_read], [], [])
            if self.wake_read in ready:
                break
            if self.server in ready:
                self.server._handle_request_noblock()

    def publish(self, state, wake=True):
        value = {'calls': state.get('calls', []), 'audio': state, 'wake': bool(wake),
                 'error': None if state.get('available') and 'calls' in state
                 else state.get('error') or 'Call observer unavailable'}
        payload = json.dumps(stable(value), separators=(',', ':'), ensure_ascii=True).encode()
        if len(payload) > 65536:
            return  # Never allocate a growing per-client backlog.
        with self.condition:
            if self.closed or payload == self.payload:
                return
            self.payload = payload
            self.revision += 1
            self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
            for sock in self.rpc_sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self.wake_write.send(b'x')
        self.thread.join(timeout=3)
        self.server.server_close()
        self.wake_read.close()
        self.wake_write.close()

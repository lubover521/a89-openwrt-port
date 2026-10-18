"""Real browser/HTTP/WebSocket checks; never talks to a modem or device."""
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'openwrt/overlay/usr/lib/e5'))
from e5_call_events import CallEvents
import e5_power_events


class TestPowerEvents:
    """Inject a supply event without real hardware or a periodic timer."""
    instances = []

    def __init__(self):
        self.socket, self.writer = socket.socketpair()
        self.instances.append(self)

    def receive(self):
        return self.socket.recv(1) == b'1'

    def close(self):
        self.socket.close()
        self.writer.close()


e5_power_events.PowerEvents = TestPowerEvents

reads, actions = [], []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, kind='application/json', status=200):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionError):
            pass

    def do_GET(self):
        if self.path == '/':
            return self.reply(b'<script src="/transport.js"></script>', 'text/html')
        if self.path == '/transport.js':
            return self.reply((repo / 'devices/t551m/infoscreen/transport.js').read_bytes(), 'text/javascript')
        reads.append((self.path, bool(self.headers.get('User-Agent'))))
        if self.path == '/api/slow':
            time.sleep(.8)
        self.reply(json.dumps({'path': self.path}).encode(), status=403 if self.path == '/api/denied' else 200)

    def do_POST(self):
        actions.append(self.path)
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.reply(b'{"ok":true}')


server = ThreadingHTTPServer(('127.0.0.1', 8088), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
events = CallEvents()
try:
    with sync_playwright() as pw:
        exe = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        browser = pw.chromium.launch(executable_path=str(exe) if exe.exists() else None, headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('http://127.0.0.1:8088/')
        for _ in range(30):
            if events.rpc_sockets:
                break
            page.wait_for_timeout(50)
        assert events.rpc_sockets
        page.wait_for_timeout(100)
        page.evaluate("window.powerChanges=0;window.addEventListener('e5-power-supply-change',()=>window.powerChanges++)")
        TestPowerEvents.instances[-1].writer.send(b'1')
        page.wait_for_function('window.powerChanges===1')
        TestPowerEvents.instances[-1].writer.send(b'0')
        page.wait_for_timeout(100)
        assert page.evaluate('window.powerChanges') == 1
        reads.clear()
        assert page.evaluate('''async()=>{
            for(let i=0;i<200;i++){
                const r=await fetch('/api/check?i='+i,{cache:'no-store'});
                if((await r.json()).path!=='/api/check?i='+i)return false;
            }return true;
        }''')
        assert len(reads) == 200 and not any(native for _, native in reads), reads[:5]
        assert page.evaluate("async()=>{return (await (await fetch('/api/custom',{headers:{'X-Test':'keep-native'}})).json()).path}") == '/api/custom'
        assert reads[-1] == ('/api/custom', True), reads[-1]
        order = page.evaluate('''async()=>{
            let order=[];await Promise.all(['/api/slow','/api/fast'].map(async p=>{
                await (await fetch(p)).json();order.push(p);
            }));return order;
        }''')
        assert order == ['/api/fast', '/api/slow'], order
        assert page.evaluate("async()=>{let r=await fetch('/api/denied');return [r.status,r.ok,(await r.json()).path]}") == [403, False, '/api/denied']
        assert page.evaluate("async()=>{await fetch('/api/action',{method:'POST',body:'{}'});return true}")
        assert actions == ['/api/action']
        before = len(reads)
        assert page.evaluate('''async()=>{
            let c=new AbortController();setTimeout(()=>c.abort(),100);
            try{await fetch('/api/slow',{signal:c.signal});return 'no abort';}
            catch(e){return e.name;}
        }''') == 'AbortError'
        page.wait_for_timeout(900)
        assert len(reads) == before + 1, 'aborted GET was replayed'
        started = time.monotonic()
        events.close()
        assert time.monotonic() - started < 1
        page.wait_for_timeout(100)
        assert page.evaluate("async()=> (await (await fetch('/api/fallback')).json()).path") == '/api/fallback'
        assert reads[-1] == ('/api/fallback', True)
        assert not errors, errors
        browser.close()
    print('200 persistent reads, concurrent completion, HTTP error, POST once, abort without replay, disconnect fallback and shutdown PASS')
finally:
    if not events.closed:
        events.close()
    server.shutdown()

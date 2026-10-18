"""Lock gestures with deterministic timing; mocked HTTP, no device writes."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--webroot', type=Path, required=True)
    ap.add_argument('--fixtures', type=Path, required=True)
    args = ap.parse_args()
    fixtures = json.loads(args.fixtures.read_text(encoding='utf-8'))
    fixtures['/api/status']['screen'].update(idle=0, lock_enabled=True)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            path = urlsplit(self.path).path
            if not path.startswith('/api/'): return super().do_GET()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps(fixtures.get(path, {})).encode())
        def do_POST(self):
            assert self.path == '/api/backlight', 'Unexpected device action: ' + self.path
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}')

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(args.webroot)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Samples are (milliseconds after wake, x, y). End can include a release wobble.
    cases = [
        dict(name='middle-origin', points=[(500,160,220),(580,160,170),(680,160,110)], unlocked=True),
        dict(name='fast-flick-under-70ms', points=[(500,160,425),(520,160,385),(545,160,345)], unlocked=True),
        dict(name='moderate-100px', points=[(500,160,425),(650,160,375),(800,160,325)], unlocked=True),
        dict(name='thumb-arc', points=[(500,110,410),(600,150,340),(700,195,260)], unlocked=True),
        dict(name='release-wobble', points=[(500,160,425),(580,160,355),(650,160,275),(670,160,287)], unlocked=True),
        dict(name='slow-held-long-swipe', points=[(500,160,425),(800,160,295),(3400,160,295)], unlocked=True),
        dict(name='start-during-wake-guard', points=[(60,160,425),(140,160,370),(250,160,305)], unlocked=True),
        dict(name='wake-burst', points=[(10,160,425),(25,160,350),(45,160,270)], unlocked=False),
        dict(name='tap', points=[(500,160,425),(600,160,425)], unlocked=False),
        dict(name='short-fast', points=[(500,160,425),(520,160,405),(545,160,381)], unlocked=False),
        dict(name='held-short', points=[(500,160,425),(540,160,385),(580,160,345),(760,160,345)], unlocked=False),
        dict(name='sideways', points=[(500,160,425),(550,240,405),(620,290,375)], unlocked=False),
        dict(name='downward', points=[(500,160,350),(550,160,390),(620,160,425)], unlocked=False),
        dict(name='top-edge', points=[(500,160,80),(550,160,40),(620,160,0)], unlocked=False),
        dict(name='pull-back', points=[(500,160,425),(570,160,340),(640,160,270),(680,160,300)], unlocked=False),
        dict(name='pull-back-and-hold', points=[(500,160,425),(570,160,270),(640,160,300),(1000,160,300)], unlocked=False),
        dict(name='second-finger', points=[(500,160,425),(580,160,370),(650,160,270)], multi=True, unlocked=False),
        dict(name='cancelled', points=[(500,160,425),(580,160,350),(650,160,270)], cancel=True, unlocked=False),
        dict(name='long-mode-short', points=[(500,160,425),(700,160,375),(900,160,320)], mode='long', unlocked=False),
        dict(name='long-mode-distance', points=[(500,160,425),(700,160,345),(900,160,265)], mode='long', unlocked=True),
        dict(name='long-mode-flick', points=[(500,160,425),(540,160,385),(580,160,345)], mode='long', unlocked=True),
        dict(name='dark-screen', points=[(500,160,425),(600,160,350),(700,160,270)], dark=True, unlocked=False),
        dict(name='touch-disabled', points=[(500,160,425),(600,160,350),(700,160,270)], disabled=True, unlocked=False),
    ]
    with sync_playwright() as p:
        chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        browser = p.chromium.launch(**({'executable_path': str(chrome)} if chrome.exists() else {}))
        page = browser.new_page(viewport={'width':320, 'height':480}, has_touch=True)
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}/')
        page.wait_for_function("typeof last !== 'undefined' && last !== null")
        page.evaluate('''() => {
            window.gestureClock = performance.now() + 10000;
            Object.defineProperty(performance, 'now', {configurable:true, value:()=>gestureClock});
        }''')
        failures = []
        for source in ['touch', 'mouse']:
            for case in cases:
                if source == 'mouse' and case.get('multi'): continue
                page.evaluate('''({test,source}) => {
                    gestureClock += 10000; const base = gestureClock;
                    Object.assign(last.screen, {ui_motion:false, unlock_distance:test.mode || 'standard', touch:!test.disabled});
                    T551M.status(last); T551M.power(true); if (!test.dark) T551M.power(false);
                    const target = document.querySelector('#mobile-lockscreen');
                    function send(type, sample, multi=false) {
                        const [t,x,y] = sample; gestureClock = base + t;
                        const ending = type === 'end' || type === 'cancel';
                        if (source === 'mouse') {
                            target.dispatchEvent(new PointerEvent({start:'pointerdown',move:'pointermove',end:'pointerup',cancel:'pointercancel'}[type],
                                {bubbles:true,cancelable:true,pointerId:1,pointerType:'mouse',buttons:ending?0:1,clientX:x,clientY:y}));
                        } else {
                            const finger = new Touch({identifier:1,target,clientX:x,clientY:y});
                            const touches = ending ? [] : [finger];
                            if (multi) touches.push(new Touch({identifier:2,target,clientX:x+20,clientY:y}));
                            target.dispatchEvent(new TouchEvent('touch'+type, {bubbles:true,cancelable:true,touches,targetTouches:touches,changedTouches:[finger]}));
                        }
                    }
                    send('start',test.points[0]);
                    for (let i=1;i<test.points.length-1;i++) send('move',test.points[i],test.multi && i===1);
                    send(test.cancel?'cancel':'end',test.points[test.points.length-1]);
                }''', {'test':case, 'source':source})
                page.wait_for_timeout(35)
                unlocked = page.evaluate('!T551M.isLocked()')
                if unlocked != case['unlocked']: failures.append(f"{source}/{case['name']}: unlocked={unlocked}")
                assert page.evaluate('page===0'), 'Lock gesture leaked into navigation'
        assert not errors, errors
        browser.close(); server.shutdown()
        assert not failures, '\n'.join(failures)
    print('PASS: 45 touch/mouse cases covering wake, origin, speed, thumb arc, release wobble, holding, long mode, cancellation and accidental input')


if __name__ == '__main__': main()

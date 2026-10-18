"""Run charger wake transitions through the real browser status/power paths."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--fixtures',type=Path,required=True)
    ap.add_argument('--webroot',type=Path,required=True)
    args=ap.parse_args()
    fixtures=json.loads(args.fixtures.read_text())
    state=fixtures['/api/status']; state['screen']['idle']=0
    state['battery']['online']=False; state['screen']['touch']=True
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(args.webroot)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
            browser=p.chromium.launch(**({'executable_path':str(chrome)} if chrome.exists() else {}))
            page=browser.new_page(viewport={'width':320,'height':480},has_touch=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def api(route):
                path=route.request.url.split(server.server_address[0]+':'+str(server.server_port))[-1].split('?')[0]
                if route.request.method=='POST':
                    if path=='/api/backlight':
                        state['screen']['awake']=route.request.post_data_json.get('level',0)>0
                    value={'ok':True}
                else:value=fixtures.get(path,{})
                route.fulfill(json=value)
            page.route('**/api/**',api)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function('typeof last!=="undefined" && last!==null')
            page.wait_for_timeout(300)
            def poll():page.evaluate('poll()');page.wait_for_timeout(250)
            def dark():page.evaluate('setBlank(true)');page.wait_for_timeout(200)
            # A focused plugin has its own event tree. Exercise both capture
            # paths, including call, number, navigation and volume keys.
            page.evaluate('''()=>{
                const frame=document.createElement('iframe');frame.id='wake-test-frame';
                frame.hidden=true;document.body.append(frame);
                T551MPower.attach(frame.contentWindow);T551M.attachKeys(frame.contentWindow);
            }''')
            for frame in [False,True]:
                dark()
                for key in ['F13','F1','Enter','ArrowUp','ArrowDown','ArrowLeft','ArrowRight',
                            'ContextMenu','Backspace','1','*','AudioVolumeUp','AudioVolumeDown','Unidentified']:
                    page.evaluate('''([key,frame])=>{
                        const target=frame?document.querySelector('#wake-test-frame').contentWindow:window;
                        for(const type of ['keydown','keyup'])target.dispatchEvent(new KeyboardEvent(type,{key,bubbles:true,cancelable:true}));
                    }''',[key,frame])
                    assert page.evaluate('blank && T551M.isLocked()'),(key,frame)
                page.touchscreen.tap(160,250)
                assert page.evaluate('blank && T551M.isLocked()')
                page.evaluate('''frame=>{
                    const target=frame?document.querySelector('#wake-test-frame').contentWindow:window;
                    for(const type of ['keydown','keyup'])target.dispatchEvent(new KeyboardEvent(type,{key:'Power',bubbles:true,cancelable:true}));
                }''',frame)
                page.wait_for_timeout(200)
                assert page.evaluate('!blank && T551M.isLocked()')
            page.evaluate("document.querySelector('#wake-test-frame').remove()")
            # A quick unplug/replug leaves the next status sample unchanged.
            # Both kernel transitions must wake without waiting for that poll.
            for _ in range(2):
                dark()
                page.evaluate("window.dispatchEvent(new Event('e5-power-supply-change'))")
                page.wait_for_timeout(200)
                assert page.evaluate('!blank && T551M.isLocked()')
                assert state['screen']['awake']
            for online in [True,False,True,False]:
                dark();state['battery']['online']=online;poll()
                assert page.evaluate('!blank && T551M.isLocked()')
                assert state['screen']['awake']
            dark()
            for status in ['Charging','Full','Not charging']:
                state['battery']['status']=status;poll()
                assert page.evaluate('blank')
            state['screen']['touch']=False;state['battery']['online']=True;poll()
            assert page.evaluate('!blank && T551M.isLocked() && touchOff()')
            # No initial-state wake: a page refresh creates a new baseline.
            page.reload();page.wait_for_function('typeof last!=="undefined" && last!==null')
            page.wait_for_timeout(250);dark();poll()
            assert page.evaluate('blank')
            assert not errors,errors
            browser.close()
            print('PASS: only power wakes from shell/plugin key or touch input; attach/detach still wakes lock; explicit touch-off retained')
    finally:server.shutdown()

if __name__=='__main__':main()

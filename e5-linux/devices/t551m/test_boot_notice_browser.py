"""Real staged screen, mock RPC only; no device changes."""
from pathlib import Path
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
import argparse,json,threading
from playwright.sync_api import sync_playwright

ap=argparse.ArgumentParser();ap.add_argument('--webroot',type=Path,required=True);ap.add_argument('--fixtures',type=Path,required=True);args=ap.parse_args()
fixtures=json.loads(args.fixtures.read_text(encoding='utf-8'))
fixtures['/api/status']['screen'].update(idle=0,lock_enabled=False)
fixtures['/api/status']['boot']={'default':'android','temporary':True,'can_set_default':True}
posts=[];failure=False
class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        path=urlsplit(self.path).path
        if not path.startswith('/api/'):return super().do_GET()
        self.send_response(200);self.end_headers();self.wfile.write(json.dumps(fixtures.get(path,{})).encode())
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))));posts.append((self.path,body))
        if self.path=='/api/settings/system' and not failure:
            fixtures['/api/status']['boot'].update(default='linux',temporary=False)
        self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'ok':not failure}).encode())
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(args.webroot)))
threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe')
    page=browser.new_page(viewport={'width':320,'height':480});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{server.server_port}/')
    page.wait_for_selector('#home-boot:not([hidden])');page.wait_for_timeout(800)
    button=page.locator('#home-boot-default')
    assert button.evaluate("e=>e.classList.contains('btn') && getComputedStyle(e).display==='flex'")
    assert button.evaluate("e=>getComputedStyle(e).alignItems==='center' && getComputedStyle(e).justifyContent==='center'")
    assert button.bounding_box()['height']>=38
    assert not [item for item in posts if item[0]=='/api/settings/system']
    page.locator('#home-boot-default').click();assert not [item for item in posts if item[0]=='/api/settings/system']
    page.locator('#home-boot-default').click()
    page.wait_for_selector('#home-boot[hidden]',state='attached')
    assert [item for item in posts if item[0]=='/api/settings/system']==[('/api/settings/system',{'id':'default_boot','value':'linux'})]
    fixtures['/api/status']['boot'].update(default='android',temporary=True,can_set_default=False)
    page.evaluate("last.boot={default:'android',temporary:true,can_set_default:false};T551M.status(last)")
    assert page.locator('#home-boot-default').is_disabled()
    failure=True;fixtures['/api/status']['boot']['can_set_default']=True
    page.evaluate("last.boot.can_set_default=true;T551M.status(last)")
    page.locator('#home-boot-default').click();page.locator('#home-boot-default').click()
    page.wait_for_function("document.querySelector('#home-boot-default').disabled===false")
    assert page.locator('#home-boot').is_visible()
    page.evaluate("last.boot={default:'unknown',temporary:null,can_set_default:false};T551M.status(last)")
    assert page.locator('#home-boot').is_hidden()
    assert not errors,errors
    browser.close()
server.shutdown();print('PASS: temporary/default/unknown, trial restriction, double confirmation, failed save, no reboot')

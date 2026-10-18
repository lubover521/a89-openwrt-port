"""Real screen shell: unread projection, cross-client updates and bulk-read ACKs."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import json
import threading

from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--webroot',type=Path,required=True)
parser.add_argument('--fixtures',type=Path,required=True)
args=parser.parse_args()
fixtures=json.loads(args.fixtures.read_text(encoding='utf-8'))
status=fixtures['/api/status']
status['screen'].update(idle=0,lock_enabled=False,ui_theme='dark')
status['sms'].update(unread=[],screen=False)
fixtures['/api/sms']={'messages':[]}
posts=[]
fail_read=False
read_gate=threading.Event();read_gate.set()

class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*_):pass
    def reply(self,data):
        body=json.dumps(data).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=urlsplit(self.path).path
        if not path.startswith('/api/'):return super().do_GET()
        self.reply(fixtures.get(path,{}))
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
        posts.append((self.path,body))
        if self.path=='/api/sms-read':
            read_gate.wait(10)
            if fail_read:return self.reply({'ok':False})
            status['sms']['unread']=[]
            for message in fixtures['/api/sms']['messages']:message['unread']=False
        self.reply({'ok':True})

def arrival(*ids):
    status['sms']['unread']=list(ids)
    fixtures['/api/sms']['messages']=[
        {'id':identifier,'card':index%2,'sim':f'SIM{index%2+1}','number':'10010','text':'Fixture',
         'state':'received','direction':'in','unread':True,'time':'2026-10-14T16:00:00+08:00'}
        for index,identifier in enumerate(ids)]

def read_posts():return [p for p in posts if p[0]=='/api/sms-read']

server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(args.webroot)))
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with sync_playwright() as pw:
        exe=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        browser=pw.chromium.launch(executable_path=str(exe) if exe.exists() else None)
        page=browser.new_page(viewport={'width':320,'height':480})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}/')
        page.wait_for_function('last!=null && !T551M.isLocked()')
        icon=page.locator('#bar-sms')
        assert icon.is_hidden()
        arrival(1000000000,1000000001)
        page.wait_for_function("document.querySelector('#bar-sms').getAttribute('aria-label')==='未读短信 (2)'")
        assert icon.is_visible() and icon.locator('svg rect').count()==1
        assert read_posts()==[]
        for theme in ('dark','light'):
            status['screen']['ui_theme']=theme
            page.wait_for_function('(theme)=>document.body.dataset.theme===theme',arg=theme)
            assert page.evaluate('''()=>{
                const icon=document.querySelector('#bar-sms');
                const signal=document.querySelector('#bar-dual').hidden
                    ? document.querySelector('#bar-bars') : document.querySelector('#bar-dual');
                const a=icon.getBoundingClientRect(),b=signal.getBoundingClientRect();
                const center=r=>r.top+r.height/2;
                const envelope=icon.querySelector('rect').getBoundingClientRect();
                const bar=document.querySelector('#bar').getBoundingClientRect();
                const battery=document.querySelector('#bar-bat').getBoundingClientRect();
                return a.width>=14 && a.height>=14 && a.right<=b.left && b.left-a.right<=6
                    && Math.abs(center(a)-center(bar))<0.5
                    && Math.abs(center(a)-center(battery))<0.5
                    && Math.abs(center(a)-center(b))<0.5
                    && Math.abs(center(envelope)-center(a)-1)<0.5
                    && getComputedStyle(icon).color===getComputedStyle(signal).color;
            }''')
        # Another client reads one card, then the other; the next existing poll reflects it.
        status['sms']['unread']=[1000000001]
        page.wait_for_function("document.querySelector('#bar-sms').getAttribute('aria-label')==='未读短信 (1)'")
        status['sms']['unread']=[]
        page.wait_for_function("document.querySelector('#bar-sms').hidden")
        assert read_posts()==[]

        arrival(1000000002,1000000003)
        page.wait_for_function("!document.querySelector('#bar-sms').hidden")
        fail_read=True
        page.locator('#mobile-nav [data-page="'+str(page.evaluate('P.sms'))+'"]').click()
        page.wait_for_function('!smsReading')
        assert len(read_posts())==1 and read_posts()[0][1]=={}
        assert icon.is_visible(), 'Failed persistence must not clear the icon'
        # Keep the original entry-to-list = all-read behavior, after backend success.
        fail_read=False;read_gate.clear()
        page.locator('#mobile-nav [data-page="0"]').click()
        page.locator('#mobile-nav [data-page="'+str(page.evaluate('P.sms'))+'"]').click()
        page.wait_for_function('smsReading')
        assert icon.is_visible(), 'Pending acknowledgement cleared the icon early'
        read_gate.set()
        page.wait_for_function("document.querySelector('#bar-sms').hidden && !smsReading")
        assert status['sms']['unread']==[]

        page.locator('#mobile-nav [data-page="0"]').click()
        page.locator('#mobile-lock').click()
        page.wait_for_function('T551M.isLocked()')
        before=len(read_posts())
        status['sms']['screen']=True
        arrival(1000000004)
        page.wait_for_function("!document.querySelector('#bar-sms').hidden")
        page.wait_for_timeout(2500)
        assert len(read_posts())==before, 'Notification behind lock marked messages read'
        assert icon.is_visible()
        page.evaluate("lang='en';applyLang();renderSmsIndicator(last.sms.unread)")
        assert icon.get_attribute('aria-label')=='Unread messages (1)'
        assert not errors,errors
        browser.close()
    print('PASS: theme/placement, both SIMs, web read sync, existing screen bulk read, failed/pending ACK, locked notifications')
finally:
    read_gate.set();server.shutdown();server.server_close()

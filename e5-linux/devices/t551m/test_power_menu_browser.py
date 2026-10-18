"""Real-screen keyboard regressions; local fixtures only, no device operations."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import runpy
import tempfile
import threading

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures',type=Path,required=True)
    args = parser.parse_args()
    fixtures = json.loads(args.fixtures.read_text(encoding='utf-8'))
    state = fixtures['/api/status'];state['screen']['idle'] = 0
    posts = [];response = {'ok':False};errors = []
    with tempfile.TemporaryDirectory(prefix='screen-power-nav-') as directory:
        root = Path(directory)
        sources = runpy.run_path(str(Path(__file__).with_name('infoscreen')/'stage.py'))['sources']()
        for name,text in sources.items():
            if not name.startswith('www/'):continue
            target=root/name[4:];target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(text,encoding='utf-8')
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(root)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
                browser=p.chromium.launch(**({'executable_path':str(chrome)} if chrome.exists() else {}))
                page=browser.new_page(viewport={'width':320,'height':480},has_touch=True)
                page.on('pageerror',lambda error:errors.append(str(error)))
                def api(route):
                    path=route.request.url.split(server.server_address[0]+':'+str(server.server_port))[-1].split('?')[0]
                    if route.request.method=='POST':
                        body=route.request.post_data_json;posts.append((path,body))
                        if path=='/api/backlight':state['screen']['awake']=body.get('level',0)>0
                        route.fulfill(json=response if path=='/api/settings/system' else {'ok':True})
                    else:route.fulfill(json=fixtures.get(path,{}))
                page.route('**/api/**',api)
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                page.wait_for_function('typeof last!=="undefined" && last!==null')
                page.wait_for_timeout(500)

                def focus():
                    return page.evaluate('''()=>{const b=document.activeElement;return b?.dataset.power || (b?.hasAttribute('data-confirm')?'confirm':b?.hasAttribute('data-cancel')?'cancel':b?.tagName);}''')
                def hold():
                    page.evaluate("window.dispatchEvent(new KeyboardEvent('keydown',{key:'Power',bubbles:true,cancelable:true}))")
                    page.wait_for_timeout(1250)
                    page.evaluate("window.dispatchEvent(new KeyboardEvent('keyup',{key:'Power',bubbles:true,cancelable:true}))")
                    assert page.locator('#power-menu').is_visible()
                    assert focus()=='cancel'
                def unlock():
                    state['screen'].update(lock_enabled=False,touch=True)
                    page.evaluate('T551M.status({...last,screen:{...last.screen,lock_enabled:false,touch:true}})')
                    page.wait_for_timeout(300)
                def lock(touch):
                    state['screen'].update(lock_enabled=True,touch=touch)
                    page.evaluate('''touch=>{T551M.status({...last,screen:{...last.screen,lock_enabled:true,touch}});setBlank(true);setBlank(false);}''',touch)
                    page.wait_for_timeout(500)
                    assert page.evaluate('T551M.isLocked()')
                def dismiss():
                    page.evaluate('T551MPower.close()')
                    assert page.locator('#power-menu').is_hidden()
                def frame():
                    page.evaluate('''()=>{let f=document.getElementById('power-focus-test');if(!f){f=document.createElement('iframe');f.id='power-focus-test';document.body.append(f);T551MPower.attach(f.contentWindow);}f.contentWindow.focus();}''')
                def frame_key(key,repeat=False):
                    page.evaluate('''([key,repeat])=>{const w=document.getElementById('power-focus-test').contentWindow;for(const type of ['keydown','keyup'])w.dispatchEvent(new KeyboardEvent(type,{key,repeat,bubbles:true,cancelable:true}));}''',[key,repeat])

                # Both locked states must be operable without a touchscreen.
                for touch in (True,False):
                    lock(touch);hold()
                    page.keyboard.press('ArrowUp');assert focus()=='android_once'
                    page.keyboard.press('Enter')
                    assert page.locator('[data-confirm]').is_visible(),('hardware OK blocked',touch)
                    assert focus()=='cancel'
                    page.keyboard.press('ArrowUp');assert focus()=='confirm'
                    assert not [p for p in posts if p[0]=='/api/settings/system']
                    if not touch:
                        page.keyboard.press('Enter')
                        page.wait_for_function("!document.querySelector('[data-confirm]').disabled")
                        assert focus()=='confirm'
                        assert len([p for p in posts if p[0]=='/api/settings/system'])==1
                        posts.clear()
                    page.keyboard.press('Escape');page.wait_for_timeout(170)
                    assert page.locator('[data-power=reboot]').is_visible()
                    dismiss()

                # Frame onload/background repaint may steal DOM focus. The
                # logical menu selection must survive, including direct OK.
                unlock();hold();page.keyboard.press('ArrowUp');assert focus()=='android_once'
                frame();frame_key('ArrowUp');assert focus()=='reboot'
                frame();frame_key('Enter');assert page.locator('[data-confirm]').is_visible()
                assert '重启' in page.locator('#power-title').inner_text()
                # The hardware can report both BrowserBack and Backspace for
                # one press. It must return to choices without dismissing them.
                frame_key('BrowserBack');frame_key('Backspace')
                assert page.locator('#power-menu').is_visible()
                assert page.locator('[data-power=reboot]').is_visible()
                dismiss()

                # Confirm-repeat must never turn selecting an action into an
                # accidental system operation. Arrow repeat remains usable.
                hold();page.keyboard.press('ArrowUp');page.keyboard.press('Enter')
                page.keyboard.press('ArrowUp');assert focus()=='confirm'
                frame_key('Enter',repeat=True)
                assert not [p for p in posts if p[0]=='/api/settings/system']
                page.keyboard.press('Enter')
                page.wait_for_function("!document.querySelector('[data-confirm]').disabled")
                assert len([p for p in posts if p[0]=='/api/settings/system'])==1
                assert focus()=='confirm','failed request lost keyboard selection'
                page.keyboard.press('ArrowDown');assert focus()=='cancel'
                page.keyboard.press('Enter');assert page.locator('[data-power=reboot]').is_visible()
                page.keyboard.press('ArrowUp');assert focus()=='android_once'
                page.wait_for_timeout(130);frame_key('ArrowUp',repeat=True)
                assert focus()=='reboot'
                page.keyboard.press('Tab');assert focus()=='android_once'
                page.keyboard.press('Shift+Tab');assert focus()=='reboot'
                dismiss()
                # Focus scrolling stays inside a short sheet, without moving
                # the background's horizontally arranged page viewport.
                page.set_viewport_size({'width':320,'height':240});hold()
                for key in ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown']*2:
                    page.keyboard.press(key)
                    box=page.evaluate('''()=>{const b=document.activeElement.getBoundingClientRect();return {top:b.top,bottom:b.bottom,scroll:document.body.scrollLeft+document.documentElement.scrollLeft};}''')
                    assert box['top']>=0 and box['bottom']<=240 and box['scroll']==0,box
                dismiss()
                # A successful action accepts one explicit confirmation and
                # remains disabled until the operating system exits.
                response['ok']=True;hold()
                page.keyboard.press('ArrowUp');page.keyboard.press('Enter');page.keyboard.press('ArrowUp')
                before=len([p for p in posts if p[0]=='/api/settings/system'])
                page.keyboard.press('Enter')
                page.wait_for_timeout(100)
                page.keyboard.press('Enter');page.keyboard.press('Escape')
                assert page.locator('[data-confirm]').is_disabled()
                assert len([p for p in posts if p[0]=='/api/settings/system'])==before+1
                assert not errors,errors
                browser.close()
                print(json.dumps({'locked_touch_on':'PASS','locked_touch_off':'PASS','iframe_focus':'PASS',
                                  'duplicate_back':'PASS','failed_action_focus':'PASS','repeat_and_tab':'PASS',
                                  'small_sheet_scroll':'PASS','successful_action_guard':'PASS','js_errors':errors}))
        finally:server.shutdown()


if __name__=='__main__':main()

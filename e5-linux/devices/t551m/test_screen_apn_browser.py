"""Real staged screen/APN UI against mock RPC, without a connected device."""
from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import runpy
import tempfile
import threading
import time
import unittest

TOP = Path(__file__).resolve().parents[2]


class ScreenAPN(unittest.TestCase):
    def test_shared_crud_sim_binding_themes_and_failure(self):
        from playwright.sync_api import sync_playwright
        sources = runpy.run_path(str(TOP / 'devices/t551m/infoscreen/stage.py'))['sources']()
        status = dict(sims=[], time=int(time.time()), tz_offset=0, clock='',
                      modem={'sim_card':0}, wan={}, traffic={'rx_rate':0,'tx_rate':0,'rx_total':0,'tx_total':0},
                      wifi={}, clients=[], battery={}, usb={}, system={}, sms={'unread':[]}, notifications=[],
                      screen={'idle':0,'awake':True,'touch':True,'lang':'zh','lock_enabled':False,'ui_theme':'dark'})
        current = {'apn':'3gnet','pdptype':'IPV4V6','auth':'none'}
        base = dict(ok=1, data_sim=0, current=current, identity_ready=True, auth_supported=True, remembered=True,
                    profiles=[dict(id='automatic', name='SIM default', apn='', pdptype='IPV4V6', auth='none', current=False),
                              dict(id='private', name='Private', apn='private.example', pdptype='IP',auth='chap',username='user',has_password=True,current=True)])
        calls=[];posts=[]
        state=deepcopy(base)
        fail_next=[False]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name, text in sources.items():
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
            class Handler(SimpleHTTPRequestHandler):
                def log_message(self,*args): pass
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(root/'www')))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(channel=os.environ.get('MU300_BROWSER_CHANNEL','msedge'),headless=True)
                    page=browser.new_page(viewport={'width':320,'height':480},has_touch=True)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    def route(request):
                        path=request.request.url.split('/api/',1)[1].split('?',1)[0]
                        if request.request.method=='POST': posts.append(path)
                        if path=='status': data=status
                        elif path=='settings': data={'categories':[{'id':'network','label':{'zh':'网络','en':'Network'}},{'id':'apn','parent':'network','view':'apn','label':{'zh':'接入点 APN','en':'Access points (APN)'}}]}
                        elif path=='settings/network': data={'items':[{'id':'apn','type':'category','category':'apn','label':'APN'}]}
                        elif path=='apn' and request.request.method=='POST':
                            payload=request.request.post_data_json;calls.append(payload)
                            if fail_next[0]: fail_next[0]=False;data={'ok':0,'error':'apn_storage'}
                            elif payload['action']=='save':
                                p=deepcopy(payload['payload']);p['id']=p.get('id') or 'new'
                                old=next((x for x in state['profiles'] if x['id']==p['id']),{})
                                p['has_password']=bool(p['password']) if 'password' in p else old.get('has_password',False)
                                p.pop('password',None)
                                state['profiles']=[p if x['id']==p['id'] else x for x in state['profiles']]
                                if not any(x['id']==p['id'] for x in state['profiles']):state['profiles'].append(p)
                                data={'ok':1}
                            elif payload['action']=='delete':
                                state['profiles']=[p for p in state['profiles'] if p['id']!=payload['payload']['id']];data={'ok':1}
                            else:
                                for p in state['profiles']:p['current']=p['id']==payload['payload'].get('id')
                                data={'ok':1}
                        elif path=='apn': data=state
                        elif path=='plugins': data={'plugins':[]}
                        else: data={}
                        request.fulfill(status=200,content_type='application/json',body=json.dumps(data))
                    page.route('**/api/**',route)
                    page.goto(f'http://127.0.0.1:{server.server_port}/')
                    page.wait_for_function('last !== null')
                    page.wait_for_timeout(700)  # Let the initial unlock transition finish.
                    page.evaluate('showPage(P.settings)')
                    page.locator('[data-st="cat:0"]').click()
                    page.wait_for_function("stTop()?.view === 'cat' && stTop().items !== null",timeout=5000)
                    self.assertFalse(errors,errors)
                    page.locator('[data-st="item:apn"]').click()
                    page.locator('[data-st="apn:edit:1"]').wait_for()
                    self.assertEqual(page.locator('.apn-summary strong').inner_text(),'SIM 1')
                    # The real edit view never retrieves or prefills saved passwords.
                    page.locator('[data-st="apn:edit:1"]').click()
                    self.assertEqual(page.locator('[data-apn-field="password"]').input_value(),'')
                    page.locator('[data-apn-field="name"]').fill('Private renamed')
                    page.locator('[data-st="apn:save"]').click()
                    page.locator('[data-st="apn:edit:1"]').wait_for()
                    self.assertNotIn('password',calls[-1]['payload'])
                    page.locator('[data-st="apn:edit:1"]').click()
                    page.locator('[data-apn-field="clear_password"]').check()
                    page.locator('[data-st="apn:save"]').click()
                    page.locator('[data-st="apn:edit:1"]').wait_for()
                    self.assertEqual(calls[-1]['payload']['password'],'')
                    # Add, failed save retains the draft, then successful save.
                    page.locator('[data-st="apn:add"]').click()
                    page.locator('[data-apn-field="name"]').fill('Test APN')
                    page.locator('[data-apn-field="apn"]').fill('test.example')
                    page.locator('[data-st="apnfield:auth:pap"]').click()
                    page.locator('[data-apn-field="username"]').fill('test')
                    page.locator('[data-apn-field="password"]').fill('secret')
                    fail_next[0]=True
                    page.locator('[data-st="apn:save"]').click()
                    page.wait_for_function('stTop().parent.saving === false')
                    self.assertEqual(page.locator('[data-apn-field="name"]').input_value(),'Test APN')
                    page.locator('[data-st="apn:save"]').click()
                    page.locator('[data-st="apn:use:2"]').wait_for()
                    self.assertEqual(calls[-1]['payload']['auth'],'pap')
                    # First press only arms. Second applies through the shared RPC,
                    # always remembering the current data SIM, not the view SIM.
                    before=len(calls)
                    page.locator('[data-st="apn:use:2"]').click()
                    self.assertEqual(len(calls),before)
                    page.locator('[data-st="apn:use:2"]').click()
                    page.wait_for_function('stTop().saving === false && !stTop().loading')
                    self.assertEqual(calls[-1],{'action':'apply','payload':{'id':'new','remember':True,'data_sim':0}})
                    # A status event for a changed data SIM refreshes the APN view.
                    state['data_sim']=1
                    status['modem']['sim_card']=1
                    page.evaluate('stAPNSync({modem:{sim_card:1}})')
                    page.wait_for_function('stTop().apn.data_sim === 1')
                    before=len(calls)
                    page.locator('[data-st="apn:auto"]').click()
                    self.assertEqual(len(calls),before)
                    page.locator('[data-st="apn:auto"]').click()
                    page.wait_for_function('stTop().saving === false')
                    self.assertEqual(calls[-1],{'action':'auto','payload':{'remember':True,'data_sim':1}})
                    for lang in ('zh','en','tr'):
                        for theme in ('light','dark'):
                            page.evaluate('([language,theme])=>{lang=language;document.body.dataset.theme=theme;stRender()}',[lang,theme])
                            self.assertTrue(page.locator('[data-st="apn:auto"]').is_visible())
                            self.assertFalse(page.evaluate("$('st-view').scrollWidth > $('st-view').clientWidth"))
                            if os.environ.get('SCREEN_APN_SCREENSHOTS'):
                                dest=Path(os.environ['SCREEN_APN_SCREENSHOTS']);dest.mkdir(parents=True,exist_ok=True)
                                page.screenshot(path=str(dest/f'apn-{lang}-{theme}.png'))
                    # Unsupported authentication is clearly blocked, while editing remains available.
                    state['auth_supported']=False
                    page.locator('[data-st="apn:refresh"]').click()
                    page.wait_for_function('stTop().apn.auth_supported === false')
                    self.assertTrue(page.locator('[data-st="apn:use:2"]').is_disabled())
                    state['auth_supported']=True
                    state['profiles'][2]['current']=False
                    page.locator('[data-st="apn:refresh"]').click()
                    page.wait_for_function('stTop().apn.auth_supported === true')
                    before=len(calls)
                    page.locator('[data-st="apn:delete:2"]').click()
                    self.assertEqual(len(calls),before)
                    page.locator('[data-st="apn:delete:2"]').click()
                    page.locator('[data-st="apn:delete:2"]').wait_for(state='detached')
                    self.assertEqual(calls[-1],{'action':'delete','payload':{'id':'new'}})
                    self.assertNotIn('settings/network',posts)
                    self.assertNotIn('at',posts)
                    self.assertFalse(errors,errors)
                    browser.close()
            finally: server.shutdown();server.server_close()


if __name__=='__main__': unittest.main()

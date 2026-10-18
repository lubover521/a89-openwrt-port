"""Real screen scripts with isolated RPC fixtures; never changes a device setting."""
import argparse,json,threading
from pathlib import Path
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ap=argparse.ArgumentParser();ap.add_argument('--webroot',type=Path,required=True);ap.add_argument('--fixtures',type=Path,required=True);args=ap.parse_args()
fixtures=json.loads(args.fixtures.read_text(encoding='utf-8'))
fixtures['/api/status']['screen'].update(idle=0,lock_enabled=False)
class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        path=urlsplit(self.path).path
        if not path.startswith('/api/'):return super().do_GET()
        self.send_response(200);self.end_headers();self.wfile.write(json.dumps(fixtures.get(path,{})).encode())
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length',0)))
        self.send_response(200);self.end_headers();self.wfile.write(b'{"ok":true}')
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(args.webroot)))
threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe')
    page=browser.new_page(viewport={'width':320,'height':480});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{server.server_port}/');page.wait_for_function("typeof last!=='undefined'&&last!==null")
    page.wait_for_timeout(700)  # Respect the real screen's startup touch guard.
    page.evaluate('''()=>{
        showPage(P.settings);window.writes=[];window.jobState='running';window.failed=false;
        const native=fetch;window.items=[{id:'net_mode',type:'choice',value:'auto',slot:'1',label:'网络模式',options:[{value:'auto',label:'自动'},{value:'4g',label:'仅4G'}]}];
        window.fetch=async(url,options)=>{
            if (url==='/api/settings/network'&&options?.method==='POST') {writes.push(JSON.parse(options.body));return new Response(JSON.stringify({ok:true,pending:true,job:'a'.repeat(32),slot:'1'}));}
            if (String(url).startsWith('/api/network-job')) {window.jobURL=url;return new Response(JSON.stringify({state:jobState,ok:jobState==='done',error:jobState==='error'?'readback mismatch':null,...window.jobReceipt}));}
            if(url==='/api/settings/network') {
                if(window.bandReadFailure)throw new Error('test read failure');
                if(window.holdBandRead)return new Promise(resolve=>{window.releaseBandRead=()=>resolve(new Response(JSON.stringify({items})));});
                return new Response(JSON.stringify({items}));
            }
            if(url==='/api/at'){writes.push(JSON.parse(options.body));return new Response(' {"ok":true,"reply":"OK"}');}
            return native(url,options);
        };
        st=[{view:'cat',cat:{id:'network',label:'网络'},items}];stRender();
    }''')
    page.locator('[data-st="item:net_mode"]').click()
    page.locator('[data-st="opt:1"]').click()
    page.wait_for_function('writes.length===1');page.wait_for_selector('#mobile-toolbar > .screen-loading:not([hidden])')
    page.locator('[data-st="opt:1"]').click();assert page.evaluate('writes.length')==1
    page.wait_for_function("window.jobURL?.includes('slot=1')")
    assert page.evaluate("writes[0].slot==='1'&&stTop().view==='edit'")
    page.evaluate("jobState='error'");page.wait_for_function('!stTop().parent.saving')
    assert page.evaluate("stTop().view==='edit'")
    page.evaluate("jobState='done'");page.locator('[data-st="opt:1"]').click();page.wait_for_function("stTop().view==='cat'")
    page.evaluate('''async()=>{
        const nativeToast=toast;const messages=[];toast=message=>messages.push(message);
        try {
            for (const language of ['zh','en']) {
                lang=language;
                for (const receipt of [{reconnect:'deferred'}, {reconnect:'failed'}, {refresh_error:'offline'}]) {
                    window.jobReceipt=receipt;
                    const result=await stPost(stTop(),{id:'net_mode',value:'4g'});
                    if(!result.ok)throw new Error('Accepted job became a screen failure');
                    const expected=t(receipt.reconnect==='deferred'?'network_deferred':
                        receipt.reconnect==='failed'?'network_reconnect_failed':'network_refresh_pending');
                    if(messages.at(-1)!==expected)throw new Error('Screen lost reconnect outcome: '+messages.at(-1));
                }
            }
        } finally {toast=nativeToast;lang='zh';delete window.jobReceipt;}
    }''')
    # Simulate a category left open while the web changes the selected SIM's
    # lock snapshot. Opening the editor must use the newly read candidates.
    page.evaluate('''()=>{
        const old={id:'nr_bands',type:'multi',slot:'0',label:'NR',value:[78],options:[{value:78,label:'n78'}]};
        items=[{...old,slot:'1',value:[41],options:[{value:1,label:'n1'},{value:41,label:'n41'}],display_value:{zh:'已锁 1 个：n41',en:'Locked 1: n41'}}];
        st=[{view:'cat',cat:{id:'network',label:'Network'},items:[old]}];stRender();
    }''')
    page.locator('[data-st="item:nr_bands"]').click();page.wait_for_function("stTop().view==='edit'")
    assert page.evaluate("stTop().item.slot==='1'&&stTop().draft.join(',')==='41'")
    assert page.locator('[data-st^="chk:"]').all_text_contents()==['n1','n41']
    page.evaluate("st.pop();bandReadFailure=true;stRender()")
    page.locator('[data-st="item:nr_bands"]').click();page.wait_for_function('!stTop().saving')
    assert page.evaluate("stTop().view==='cat'"),'Failed refresh opened a stale editor'
    page.evaluate("bandReadFailure=false;holdBandRead=true;delete window.releaseBandRead")
    page.locator('[data-st="item:nr_bands"]').click();page.wait_for_function("typeof releaseBandRead==='function'")
    page.locator('[data-st="item:nr_bands"]').click()
    assert page.evaluate("stTop().view==='cat'&&stTop().saving")
    page.evaluate("st=[];releaseBandRead();holdBandRead=false")
    page.wait_for_timeout(100)
    assert page.evaluate('st.length===0'),'Late response reopened a page after navigation'
    page.evaluate("st=[{view:'at',presets:[{cmd:'AT+CSQ',label:'Signal'}],slot:'0'}];stRender()")
    page.locator('[data-st="atslot:"]').click();page.locator('[data-st="atp:0"]').click()
    page.wait_for_function("writes.at(-1).cmd==='AT+CSQ'");assert page.evaluate('writes.at(-1).slot')=='1'
    for language,label,value in [('zh','充电设置','充电启动阈值必须低于停止阈值'),('en','Charging','Charge start must be lower than stop')]:
        page.evaluate('language=>{lang=language;st=[{view:"cat",cat:{id:"charge",label:{zh:"充电设置",en:"Charging"}},items:[{id:"error",type:"info",label:{zh:"充电设置",en:"Charging"},value:"Charge start must be lower than stop"}]}];stRender();}',language)
        assert label in page.locator('#st-view').inner_text()
        assert value in page.locator('#st-view').inner_text()
    assert not errors,errors
    browser.close()
server.shutdown()
print('PASS: network jobs, duplicate prevention, immutable SIM, stale band editor refresh, failed and late reads, AT SIM selector')

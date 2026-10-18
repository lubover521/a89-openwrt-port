"""CPU web controls and nested screen navigation, with hardware-free fixtures."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[3]
SOURCE=(ROOT/'device/openwrt_device_common/luci-app-t551m/htdocs/luci-static/resources/view/mu300/cpu.js').read_text(encoding='utf-8')
COMMON=(ROOT/'device/openwrt_device_common/luci-app-t551m/htdocs/luci-static/resources/mu300/common.js').read_text(encoding='utf-8')
STATE={'ok':True,'available':True,'persistent':False,'voltage_min':-50000,'voltage_max':25000,'voltage_step':3125,'policies':[
    {'id':f'policy{cpu}','cpus':cpus,'current':600000,'min':600000,'max':1800000,
     'governor':'schedutil','governors':['schedutil','powersave','performance'],
     'frequencies':[600000,900000,1200000,1800000],'voltages':[{'khz':600000,'uv':650000}],
     'voltage_boot_writable':True,'voltage_offset':0,'voltage_next':0,'voltage_actual':650000}
    for cpu,cpus in [(0,'0 1 2 3 4 5'),(6,'6'),(7,'7')]],
    'zones':[{'id':'thermal_zone23','name':'soc-thmzone','temp':48000,'trips':[
        {'id':0,'type':'passive','temp':70000,'hysteresis':1000,'writable':True},
        {'id':1,'type':'passive','temp':85000,'hysteresis':1000,'writable':True},
        {'id':2,'type':'critical','temp':110000,'hysteresis':2000,'writable':False}]}]}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--webroot',type=Path,required=True)
    ap.add_argument('--fixtures',type=Path,required=True)
    args=ap.parse_args()
    snapshots=ROOT/'logs/t551m';snapshots.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        browser=p.chromium.launch(**({'executable_path':str(chrome)} if chrome.exists() else {}))
        page=browser.new_page(viewport={'width':390,'height':844})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.set_content('<html lang="zh"><style>*{box-sizing:border-box}body{margin:14px}.mud-card{border:1px solid #ddd;border-radius:16px}.mud-btn{padding:10px;border:1px solid #ddd;border-radius:8px}h3{font-size:16px}</style></html>')
        page.evaluate('s=>{window.fixture=s;window.calls=[];window.fail=false;}',STATE)
        page.evaluate('''([source,common])=>{
            const rpc={declare:spec=>(...args)=>{
                calls.push({method:spec.method,args});
                if(fail&&spec.method==='apply')return Promise.resolve({ok:false,error:'Test failure'});
                if(spec.method==='apply') {
                    args[0].policies.forEach(v=>Object.assign(fixture.policies.find(p=>p.id===v.id),v));
                    fixture.persistent=args[1];
                }
                return Promise.resolve(JSON.parse(JSON.stringify(fixture)));
            }};
            const poll={add:f=>window.tick=f};
            window.L={env:{lang:'zh'}};
            const M=new Function('rpc','baseclass',common)(rpc,{extend:x=>x});
            M.localizeMenu=()=>{};
            window.cpuView=new Function('view','rpc','poll','M',source)({extend:x=>x},rpc,poll,M);
            document.body.append(cpuView.render(fixture));
        }''',[SOURCE,COMMON])
        assert page.locator('[data-setting$="_governor"]').count()==3
        assert page.locator('.cpu-thermal input').count()==2
        assert page.locator('[data-setting$="_voltage_next"]').count()==3
        # Firmware tables use the shared themed dialog without expanding cards.
        table_button = page.locator('.mud-cpu-table button').first
        before_height = page.locator('.mud-cpu').bounding_box()['height']
        page.evaluate('()=>{fixture.policies[0].voltages=Array.from({length:31},(_,i)=>({khz:600000+i*10000,uv:650000+i*3125}));return tick();}')
        table_button.click()
        assert page.get_by_role('dialog').count()==1
        assert page.locator('.mud-cpu-voltage-table tbody tr').count()==31
        assert page.locator('.mud-cpu-voltage-table tbody tr').first.inner_text()=='600\t650'
        assert page.locator('.mud-cpu').bounding_box()['height']==before_height
        assert page.locator('.mud-cpu-voltage-scroll').evaluate('(el)=>el.scrollHeight>el.clientHeight')
        page.evaluate("document.querySelector('.mud-cpu-table button').click()")
        assert page.get_by_role('dialog').count()==1
        page.keyboard.press('Escape')
        page.wait_for_function('!cpuView.tableOpen')
        assert table_button.evaluate('(el)=>document.activeElement===el')
        table_button.click()
        page.get_by_role('dialog').get_by_role('button',name='确定',exact=True).click()
        page.wait_for_function('!cpuView.tableOpen')
        assert page.get_by_role('dialog').count()==0
        page.locator('[data-setting="policy0_voltage_next"]').select_option('-3125')
        page.locator('[data-setting="policy0_max"]').select_option('1200000')
        page.evaluate('()=>{fixture.policies[0].current=900000;return tick();}')
        assert page.locator('[data-setting="policy0_max"]').input_value()=='1200000'
        assert page.locator('[data-current="policy0"]').inner_text()=='900'
        page.locator('.cpu-persist input').check()
        page.get_by_role('button',name='应用设置').click()
        page.wait_for_function('calls.some(c=>c.method==="apply")&&!cpuView.busy')
        assert page.evaluate('fixture.persistent')
        assert page.evaluate('fixture.policies[0].max')==1200000
        assert page.evaluate('fixture.policies[0].voltage_next')==-3125
        assert page.evaluate('fixture.policies[0].voltage_offset')==0
        page.locator('[data-setting="policy0_min"]').select_option('1800000')
        count=page.evaluate('calls.filter(c=>c.method==="apply").length')
        page.get_by_role('button',name='应用设置').click()
        assert page.evaluate('calls.filter(c=>c.method==="apply").length')==count
        assert '最低频率' in page.locator('.cpu-message').inner_text()
        page.locator('[data-setting="policy0_min"]').select_option('600000')
        page.evaluate('fail=true')
        page.get_by_role('button',name='应用设置').click()
        page.wait_for_function('!cpuView.busy')
        assert 'Test failure' in page.locator('.cpu-message').inner_text()
        assert page.locator('[data-setting="policy0_max"]').is_enabled()
        for language,title,error in [('en','CPU settings','Governor unavailable'),('tr','CPU ayarları','Seçilen frekans yöneticisi kullanılamıyor')]:
            page.evaluate('language=>{L.env.lang=language;document.documentElement.lang=language;cpuView.paint(fixture);cpuView.message("Governor unavailable",true);}',language)
            assert page.locator('h2').inner_text()==title
            assert page.locator('.cpu-message').inner_text()==error
            assert not page.evaluate(r'/[\u3400-\u9fff]/.test(document.body.innerText)'), language
        page.evaluate("L.env.lang='zh';document.documentElement.lang='zh';cpuView.paint(fixture)")
        for width in [390,1280]:
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(snapshots/f'cpu-web-{width}.png'),full_page=True)
        fixtures=json.loads(args.fixtures.read_text(encoding='utf-8'))
        fixtures['/api/status']['screen'].update(idle=0,lock_enabled=False)
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if not self.path.startswith('/api/'):
                    return super().do_GET()
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps(fixtures.get(self.path,{})).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(args.webroot)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        page=browser.new_page(viewport={'width':320,'height':480},has_touch=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}')
        page.wait_for_function("typeof last!=='undefined'&&last!==null")
        page.wait_for_timeout(700)
        page.evaluate('''()=>{
            stCats=[{id:'system',label:{zh:'系统',en:'System'}},{id:'cpu',parent:'system',label:{zh:'CPU 设置',en:'CPU settings'}}];
            pageRead=async()=>({items:[{id:'policy0_min',type:'choice',label:{zh:'最低频率',en:'Minimum frequency'},value:'600000',options:[{value:'600000',label:'600 MHz'}]}]});
            showPage(P.settings);st=[{view:'menu'},{view:'cat',cat:stCats[0],items:[{id:'cpu',type:'category',category:'cpu',label:stCats[1].label}]}];stRender();
        }''')
        page.locator('[data-st="item:cpu"]').click()
        page.wait_for_function("stTop().cat.id==='cpu'&&stTop().items!==null")
        assert '系统 › CPU 设置' in page.locator('#st-path').inner_text()
        page.locator('[data-st="item:policy0_min"]').click()
        assert page.locator('[data-st="opt:0"]').is_visible()
        page.screenshot(path=str(snapshots/'cpu-screen.png'))
        page.locator('#mobile-back').click()
        page.locator('#mobile-back').click()
        assert page.evaluate("stTop().cat.id==='system'")
        page.evaluate("st=[{view:'menu'}];stRender()")
        assert page.locator('[data-st="cat:1"]').count()==0,'CPU leaked into top-level settings'
        assert not errors,errors
        browser.close();server.shutdown()
    print('PASS: CPU web apply/readback, validation, error, poll preserves drafts, responsive layout; nested screen navigation')


if __name__=='__main__':main()

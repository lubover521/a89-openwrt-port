"""Real LuCI dashboard/common scripts with delayed RPC responses, no device access."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[3] / 'device/openwrt_device_common/luci-app-t551m/htdocs/luci-static/resources'
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe')
    page = browser.new_page(viewport={'width':1280, 'height':900})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.set_content('<html lang="zh"><body></body></html>')
    page.evaluate('''() => {
        window.calls=[];window.inflight={};window.peak={};window.rateDelay=20;
        window.rpc={declare: spec => (...args) => {
            const method=spec.method;calls.push({method,args,time:performance.now(),nobatch:spec.nobatch});
            inflight[method]=(inflight[method]||0)+1;peak[method]=Math.max(peak[method]||0,inflight[method]);
            return new Promise(resolve=>setTimeout(()=>{
                inflight[method]--;
                const ts=performance.now()/1000;
                resolve(method==='rates' ? {card:0,device:'sipa_eth0',ifindex:1,ts,net:{rx:ts*1000000,tx:ts*100000}}
                    : method==='status' ? {info:{ts:100,uptime:100,host:'TEST',modem:{alive:1},wan:{}}} : {});
            },method==='rates' ? rateDelay : method==='status' ? 2400 : 1));
        }};
        window.L={resolveDefault:(promise,value)=>Promise.resolve(promise).catch(()=>value),env:{}};
        window.uci={load:()=>Promise.resolve(),get:()=>0.5};
    }''')
    # The common module accesses sessionStorage; use its existing accessor with
    # a tiny in-memory object on this isolated document.
    page.evaluate("Object.defineProperty(window,'sessionStorage',{value:{getItem:()=>null,setItem:()=>{}}})")
    page.evaluate('(source)=>{window.M=new Function("rpc","baseclass",source)(rpc,{extend:x=>x})}', (root/'mu300/common.js').read_text(encoding='utf-8'))
    page.evaluate('(source)=>{window.dashboard=new Function("view","uci","M",source)({extend:x=>x},uci,M);document.body.append(dashboard.render())}', (root/'view/mu300/home.js').read_text(encoding='utf-8'))
    values=page.evaluate('(source)=>new Function(source.split("return view.extend({")[0]+"return [0.5,1.5,2,5,60,61,null].map(pollSeconds);")()', (root/'view/mu300/home.js').read_text(encoding='utf-8'))
    assert values==[2,2,2,5,60,2,2],values
    page.wait_for_timeout(2150)
    assert page.locator('#mud-dl').text_content() not in ('--',''), 'Rates waited for slow status'
    rates = page.evaluate("calls.filter(c=>c.method==='rates')")
    assert len(rates) == 3, rates
    assert all(r['nobatch'] and r['args']==['0'] for r in rates)
    gaps = [b['time']-a['time'] for a,b in zip(rates,rates[1:])]
    assert all(850 < g < 1300 for g in gaps), gaps
    page.evaluate('rateDelay=2600')
    page.wait_for_timeout(5600)
    assert page.evaluate("peak.rates===1 && peak.status===1"), 'Overlapping requests'
    page.evaluate('dashboard.unload()')
    count = page.evaluate("calls.filter(c=>['rates','status'].includes(c.method)).length")
    page.wait_for_timeout(3000)
    assert page.evaluate("calls.filter(c=>['rates','status'].includes(c.method)).length") == count, 'Polling restarted after unload'
    result = page.evaluate('''() => {
        const sample=(ts,rx,tx,card=0,ifindex=1)=>({ts,card,device:card?'sipa_eth8':'sipa_eth0',ifindex,net:{rx,tx}});
        dashboard.lastNet=null;
        dashboard.updateRates(sample(10,1000,100));
        dashboard.updateRates(sample(10.5,501000,50100));
        const dl=M.v('dl').textContent,ul=M.v('ul').textContent;
        dashboard.updateRates(sample(11,10,10));
        const reset=M.v('dl').textContent==='--';
        dashboard.updateRates(sample(11.5,500010,50010,1));
        const switched=M.v('dl').textContent==='--';
        dashboard.updateRates({ts:12,net:null});
        return {dl,ul,reset,switched,missing:M.v('dl').textContent==='--'};
    }''')
    assert result == {'dl':'977 KB/s','ul':'97.7 KB/s','reset':True,'switched':True,'missing':True},result
    assert not errors, errors
    browser.close()
print('PASS: status minimum 2s (including old configs), independent 1s rates, no overlap/unload leaks, rate/SIM/reset guards')

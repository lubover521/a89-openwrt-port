"""Real shared LuCI module against a batching RPC harness (no device writes)."""
from pathlib import Path
from playwright.sync_api import sync_playwright

source = (Path(__file__).resolve().parents[2] / 'openwrt/luci-app-t551m/htdocs/luci-static/resources/mu300/common.js').read_text(encoding='utf-8')
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe')
    page = browser.new_page()
    page.set_content('<html><body></body></html>')
    page.evaluate('''() => {
        let values={};
        Object.defineProperty(window,'sessionStorage',{value:{getItem:k=>values[k],setItem:(k,v)=>values[k]=v}});
        window.records=[]; window.atDone=false;
        let queued=[], scheduled=false;
        const flush=()=>{const batch=queued;queued=[];scheduled=false;
            setTimeout(()=>batch.forEach(c=>{if(c.method==='at')atDone=true;c.resolve({ok:true})}),
                       batch.some(c=>c.method==='at')?600:1);};
        window.rpc={declare:s=> (...args)=>new Promise(resolve=>{
            records.push({method:s.method,args,nobatch:s.nobatch});
            if(s.nobatch) setTimeout(()=>{if(s.method==='at')atDone=true;resolve({ok:true})},s.method==='at'?600:1);
            else {queued.push({method:s.method,resolve});if(!scheduled){scheduled=true;setTimeout(flush,0);}}
        })};
    }''')
    page.evaluate('(s)=>{window.M=new Function("rpc","baseclass",s)(rpc,{extend:x=>x})}', source)
    result = page.evaluate('''async()=>{
        const slow=M.callAt('AT+TEST');
        const reads=[M.callStatus(),M.callRates(),M.callSysinfo(),M.callSignal(),M.callCells()];
        sessionStorage.setItem('modem-view-slot','1');
        reads.push(M.callStatus());
        await Promise.all(reads);
        const independent=!atDone;
        await slow;
        return {independent,records};
    }''')
    assert result['independent'], result
    assert all(r['nobatch'] for r in result['records']), result
    statuses = [r['args'] for r in result['records'] if r['method'] == 'status']
    assert statuses == [['0'], ['1']], statuses
    assert sum(r['method'] == 'at' for r in result['records']) == 1, 'AT command repeated'
    browser.close()
print('PASS: slow AT batch cannot hold status/rates/sysinfo, slot captured at dispatch, no mutation retry')

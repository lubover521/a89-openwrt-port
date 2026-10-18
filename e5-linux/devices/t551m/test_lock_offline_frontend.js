// Execute the shipped LuCI view with isolated RPC, including offline receipts.
const fs = require('fs'), assert = require('assert');
const source = fs.readFileSync('openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/locks.js','utf8');
const M = {busy() {}, waitLockJob: async () => ({ok:1,state:'done'})};
const view = new Function('view','M',source)({extend: x => x},M);
(async () => {
    let messages=[], paints=0;
    const page={...view,note:(message,type)=>messages.push({message,type}),
        paint:()=>paints++,paintServing(){},paintNeighbors(){},paintVoiceSwitches(){},refresh(){}};
    async function run(receipt, status, rejected=false) {
        messages=[];page._applying=true;
        M.waitLockJob=async()=>receipt;
        M.callLockGet=async()=>{if (rejected)throw new Error('offline');return status;};
        await page.readback({id:'job',op:'mode'},{});
        assert.strictEqual(page._applying,false);
        assert.strictEqual(messages.length,1);
        return messages[0];
    }
    let message=await run({ok:1,reconnect:'deferred'}, {error:'no SIM'});
    assert.equal(message.type,'info');assert(message.message.includes('跳过重连'));
    message=await run({ok:1,reconnect:'failed',reconnect_error:'WrongState'},null,true);
    assert.equal(message.type,'error');assert(message.message.includes('WrongState'));
    assert(!message.message.includes('应用失败'));
    message=await run({ok:1,refresh_error:'snapshot timeout'},null,true);
    assert.equal(message.type,'info');assert(message.message.includes('设置已应用'));
    message=await run({ok:1,reconnect:'done'},{mode:{label:'4g'}});
    assert.equal(message.type,'success');assert.equal(page.lastLock.mode.label,'4g');
    assert.equal(paints,1);
    M.waitLockJob=async()=>{throw new Error('AT rejected');};messages=[];
    await page.readback({id:'job'},{});
    assert.equal(messages[0].type,'error');assert(messages[0].message.includes('应用失败'));
    assert.strictEqual(page._applying,false);
    const common=fs.readFileSync('openwrt/luci-app-t551m/htdocs/luci-static/resources/mu300/common.js','utf8');
    const L={env:{lang:'zh'}};
    const catalog=new Function('rpc','baseclass','L',common)(
        {declare:()=>()=>Promise.resolve({})},{extend:x=>x},L);
    for (const language of ['en','tr']) {
        L.env.lang=language;
        for (const label of ['设置已保存；当前模组未就绪或射频已关闭，已跳过重连',
                             '设置已应用；状态刷新暂不可用，请稍后刷新',
                             '设置已接受，但重连失败：WrongState'])
            assert(!/[\u3400-\u9fff]/.test(catalog.translate(label)),language+': '+label);
    }
    console.log('PASS: deferred/rejected reconnect, status-refresh failure, accepted settings and actual AT rejection');
})().catch(e=>{console.error(e);process.exitCode=1;});

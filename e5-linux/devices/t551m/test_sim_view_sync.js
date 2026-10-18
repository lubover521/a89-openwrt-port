// Real shared module: observe data SIM changes without stealing manual views.
const fs = require('fs'), assert = require('assert');
const source = fs.readFileSync('openwrt/luci-app-t551m/htdocs/luci-static/resources/mu300/common.js', 'utf8');
const memory = new Map([['modem-view-slot', '0']]);
const storage = {getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, value)};
let reloads = 0, hasSelector = false, actual = 1, fail = false, deferred;
const rpc = {declare: spec => () => {
    if (spec.method === 'sim_get') {
        if (fail) return Promise.reject(new Error('offline'));
        if (deferred) return new Promise(resolve => { deferred = resolve; });
        return Promise.resolve({ok:true, data_sim:actual});
    }
    return Promise.resolve(spec.method === 'status' ? {info:{modem:{data_sim:actual}}} : {});
}};
const M = new Function('rpc', 'baseclass', 'sessionStorage', 'document', 'window', source)(
    rpc, {extend:x=>x}, storage, {querySelector:()=>hasSelector}, {location:{reload:()=>reloads++}});
(async()=>{
    await M.callSimGet();
    assert.equal(M.simSlot(), '1', 'First visit must follow actual SIM 2');
    storage.setItem('modem-view-slot', '0');
    await M.callSimGet(); await M.callStatus();
    assert.equal(M.simSlot(), '0', 'Stable data SIM must preserve a manual secondary view');
    M.followDataSim('1', true);
    assert.equal(M.simSlot(), '1', 'Verified success follows even if actual card was observed earlier');
    hasSelector = true; actual = 0;
    await M.callStatus();
    assert.equal(M.simSlot(), '0'); assert.equal(reloads, 1, 'Screen/other-tab switch must invalidate page caches');
    await M.callStatus();
    assert.equal(reloads, 1, 'Stable state must not cause a reload loop');
    for (const value of [null, undefined, '', 2, false, 'bad']) M.followDataSim(value, true);
    assert.equal(M.simSlot(), '0');
    fail = true; await assert.rejects(M.callSimGet()); fail = false;
    assert.equal(M.simSlot(), '0', 'Failed reads cannot guess a slot');
    deferred = true;
    const old = M.callSimGet();
    M.followDataSim('1', true);
    deferred({ok:true, data_sim:0}); deferred = null;
    await old;
    assert.equal(M.simSlot(), '1', 'Late pre-switch snapshot reverted the completed switch');
    console.log('PASS: first visit, manual secondary view, actual/verified switch, one reload, unknown/offline and late snapshots');
})().catch(error=>{console.error(error);process.exitCode=1;});

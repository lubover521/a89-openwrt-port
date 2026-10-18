// Verify current feature strings and shared backend errors in every UI language.
const fs=require('fs'),assert=require('assert');
const base='openwrt/luci-app-t551m/htdocs/luci-static/resources/';
const common=fs.readFileSync(base+'mu300/common.js','utf8');
const L={env:{lang:'zh'}};
const M=new Function('rpc','baseclass','L',common)({declare:()=>()=>Promise.resolve({})},{extend:x=>x},L);
const cpu=fs.readFileSync(base+'view/mu300/cpu.js','utf8');
const labels=[...cpu.matchAll(/text\('([^']*)','([^']*)'\)/g)].map(x=>x[1]);
labels.push('SIM 卡管理','切换上网卡','开机使用','清空当前卡记录','需要确认清空','与屏幕共用系统双卡短信池');
labels.push('状态暂不可读，请选择开启或关闭','本次已应用',
    '关闭后只停止下次开机回放，已保存的网络、IMS、VoLTE 和 VoNR 设置不会被删除。',
    'IMS 为总开关，VoLTE 用于 4G 通话，VoNR 用于 5G SA 通话。设置按当前查看的 SIM 保存，并跟随“开机自动应用”。',
    '关闭 IMS 不等于屏蔽全部来电和短信，传统网络业务仍可能到达。');
labels.push('切换上网卡后，看板、锁定和 AT 的查看卡槽会同步；仍可手动查看另一张卡。');
for(const lang of ['en','tr']) {
    L.env.lang=lang;
    for(const label of labels) assert(!/[\u3400-\u9fff]/.test(M.translate(label)),lang+': '+label);
}
const start=common.indexOf('/* BEGIN SHARED PLATFORM MESSAGES:');
const end=common.indexOf('/* END SHARED PLATFORM MESSAGES */',start);
const catalog=new Function(common.slice(start,end)+';return {errorText,PLATFORM_ERRORS};')();
for(const row of catalog.PLATFORM_ERRORS) {
    for(const [i,lang] of ['en','zh','tr'].entries()) assert.equal(catalog.errorText(row[0],lang),row[i]);
}
assert.equal(catalog.errorText('traffic_unavailable','zh'),'流量统计服务暂不可用');
assert.equal(catalog.errorText('Kernel did not accept scaling_min_freq','zh'),'内核未接受设置：scaling_min_freq');
assert.equal(catalog.errorText('AT+CSQ: 12,99','tr'),'AT+CSQ: 12,99','Raw diagnostics must be preserved');
L.env.lang='zh';assert.equal(M.translate('A data SIM switch is already running'),'正在切换上网卡，请稍后再试');
console.log('PASS: CPU/SIM/traffic labels in English and Turkish; '+catalog.PLATFORM_ERRORS.length+' backend messages in Chinese/English/Turkish; structured errors and technical details');

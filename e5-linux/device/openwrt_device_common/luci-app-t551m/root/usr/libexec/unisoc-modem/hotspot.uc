// Shared hotspot configuration and switch for the physical screen and LuCI.
import { stat } from 'fs';
export function config(c) {
    let ap = null;
    c.foreach('wireless','wifi-iface',s=>{if (!ap && s.mode == 'ap') ap=s;});
    if (!ap) return {available:false,enabled:false};
    let radio=ap.device, encryption=ap.encryption;
    return {available:true,iface:ap['.name'],radio,ssid:ap.ssid,key:ap.key,encryption,
        secured:encryption != null && encryption != 'none',hidden:ap.hidden == '1',
        enabled:ap.disabled != '1' && c.get('wireless',radio,'disabled') != '1',
        channel:c.get('wireless',radio,'channel'),band:c.get('wireless',radio,'band'),
        qr_revision:stat('/etc/config/wireless')?.mtime ?? 0};
};
export function set(c,on,run) {
	run ??= system;
    if (type(on) != 'bool') return {ok:false,error:'Invalid hotspot state'};
    let ap=config(c);
    if (!ap.available) return {ok:false,error:'No hotspot configured'};
    c.set('wireless',ap.radio,'disabled',on?'0':'1');
    c.set('wireless',ap.iface,'disabled',on?'0':'1');
    if (!c.commit('wireless')) return {ok:false,error:'Cannot save hotspot setting'};
    return {ok:run('(wifi reload) >/dev/null 2>&1 &') == 0};
};

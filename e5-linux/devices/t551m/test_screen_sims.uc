// Pure projection test: no modem access or real cache writes.
import { readfile } from 'fs';
let build = loadstring('return function(readfile,sim_card,time) {\n' + readfile(ARGV[0]) + '\nreturn {sim_status,card_modem};\n};', {raw_mode:true})();
let active=0, now=100;
let data={sims:[
    {slot:0,present:true,updated:99,operator:'CHN-UNICOM',tech:'lte',radio_label:'4G',signal:{rsrp:-91},registration:'camped'},
    {slot:1,present:true,updated:99,operator:'46011',tech:'5gnr',radio_label:'5G SA',signal:{rsrp:-104},registration:'home'}]};
let cache={card:0,ts:99,lte:{band:8,pci:143,earfcn:3740,rsrp:-90,rsrq:-12,sinr:3,bw:'10M'},reg:{stat:1}};
let api=build(path=>path=='/proc/uptime' ? `${now} 0` : sprintf('%J',path=='/run/t551m-sims.json' ? data : cache),()=>active,()=>now);
function check(ok,msg) { if (!ok) die(msg); }
let mm={tech:'5gnr',operator:'wrong card',signal:{rsrp:-104},cell:{type:'5gnr',band:'n78'}};
let cards=api.sim_status(),m=api.card_modem(mm,cards);
check(m.tech=='lte' && m.operator=='CHN-UNICOM' && m.signal.rsrp==-90, 'Standby 5G leaked into data SIM');
check(m.cell.band=='B8' && m.signal.snr==3, 'Dashboard serving-cell data not aligned');
check(cards[0].registration=='camped' && m.registration=='unknown', 'Shared registration state leaked into SIM');
cache.nr={band:78,rsrp:-100,rsrq:-10,sinr:5};
m=api.card_modem(mm,api.sim_status());
check(m.tech=='5gnr' && m.radio_label=='5G NSA' && m.cell.band=='n78', 'Dashboard NSA decision differs');
cache.nr=null;
active=1;cards=api.sim_status();m=api.card_modem(mm,cards);
check(m.tech=='5gnr' && m.signal.rsrp==-104 && m.operator=='46011', 'Data card change not reflected');
check(m.cell.band=='n78', 'Other SIM cached LTE cell leaked into NR');
now=130;cards=api.sim_status();m=api.card_modem(mm,cards);
check(cards[0].stale && cards[1].stale && m.tech==null && m.signal.rsrp==null, 'Stale data presented as live');
now=100;active=0;
data.sims[0].signal.snr=4;
mm.cell={type:'lte',band:'B8',sinr:33};
cache.ts=50;
m=api.card_modem(mm,api.sim_status());
check(m.signal.snr==4, 'Closed dashboard must keep per-card SINR, not shared MM SINR');
cache.ts=99;cache.lte.sinr=null;
m=api.card_modem(mm,api.sim_status());
check(m.signal.snr==4, 'Optional dashboard PHY failure erased per-card SINR');
cache.lte.sinr=0;
m=api.card_modem(mm,api.sim_status());
check(m.signal.snr==0, 'Valid zero SINR was treated as unavailable');
cache.card=1;
m=api.card_modem(mm,api.sim_status());
check(m.signal.snr==4, 'Other slot SINR leaked into data card');
data.sims[0].signal.snr=null;
m=api.card_modem(mm,api.sim_status());
check(m.signal.snr==null, 'Shared MM cell must not fabricate per-card SINR');
data.sims[0]={slot:0,present:false,updated:99,registration:'absent',signal:{}};
cache.card=0;
m=api.card_modem({...mm,sim:true},api.sim_status());
check(m.sim===false && m.operator==null && m.cell==null && m.tech==null,
      'No SIM reused operator/cell from MM or dashboard');
print('Per-SIM projection, data SIM selection, dashboard cache isolation and expiry: PASS\n');

// Mock configuration: prove shared hotspot and setting failures without hardware writes.
'use strict';
function check(ok,why){if(!ok)die(why);}
import * as hotspot from '/usr/libexec/unisoc-modem/hotspot.uc';
let store={radio1:{disabled:'0',channel:'6'},guest:{'.name':'guest',mode:'ap',device:'radio1',disabled:'1',ssid:'test'},station:{'.name':'station',mode:'sta',device:'radio0',disabled:'1'}};
let fail=false,runs=[];
let c={foreach:(pkg,kind,fn)=>{fn(store.station);fn(store.guest);},get:(pkg,s,k)=>store[s]?.[k],
    set:(pkg,s,k,v)=>{store[s][k]=v;return true;},commit:()=>!fail};
check(!hotspot.config(c).enabled,'Disabled AP was reported enabled');
check(hotspot.set(c,true,cmd=>{push(runs,cmd);return 0;}).ok,'Enable failed');
check(store.radio1.disabled=='0'&&store.guest.disabled=='0'&&store.station.disabled=='1','Wrong radio/interface toggled');
fail=true;let count=length(runs);
check(!hotspot.set(c,false,cmd=>{push(runs,cmd);return 0;}).ok&&length(runs)==count,'Failed save still applied Wi-Fi');
let config={'e5-charge':{start:'70',stop:'80'}}, writes=0,failed=false;
let ctx={run:()=>1,sh_json:()=>({}),uci:()=>({get:(p,s,k)=>config[p]?.[k],set:()=>{writes++;return !failed;},commit:()=>true})};
let categories=loadfile(ARGV[1],{raw_mode:true})()(ctx), charge=filter(categories,c=>c.id=='charge')[0],screen=filter(categories,c=>c.id=='screen')[0];
check(charge.set('start',85)!=null&&writes==0,'Inverted charge thresholds accepted');
failed=true;check(screen.set('idle','60')!=null,'Failed UCI save reported success');
let raw=loadfile(ARGV[2],{raw_mode:true})()({read_trim:p=>p=='/usr/share/e5-infoscreen/ADAPTATION'?'e5-device-ui-v1':p=='/usr/share/e5-infoscreen/VERSION'?'1.6.7':index(p,'latest.json')>=0?'{"version":"99.0"}':null,uci:()=>({get:()=>null})});
check(raw.state().incompatible&&!raw.state().available&&raw.start('apply')!=null,'Generic upstream update may overwrite integration');
print('PASS: shared hotspot target/switch/save failure, charge thresholds, failed setting writes and incompatible update rejection\n');

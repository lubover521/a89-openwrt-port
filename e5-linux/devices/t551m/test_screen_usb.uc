// Pure settings integration: all commands and hardware are mocked.
'use strict';
let calls = [];
let state = {ok:1,role:'device',policy:'auto',host_supported:1,role_auto:0,
    net_current:'ncm',net_mode:'rndis',net_scope:'once',net_auto:1,
    net_available:1,net_supported:['ncm','ecm','rndis'],lan_auto:1};
let ctx = {run:()=>1,uci:()=>({get:()=>null}),network_check_status:()=>null,
    usb_status:()=>({reset:{},state:'configured'}),
    sh_json:cmd=>{push(calls,cmd);return cmd == '/usr/libexec/unisoc-modem/device-usb get' ? state : {ok:1};}};
let categories = loadfile(ARGV[0], {raw_mode:true})()(ctx);
let usb = filter(categories,c=>c.id == 'usb')[0];
function check(value,why) { if (!value) die(why); }
function item(id) { return filter(usb.items(),i=>i.id==id)[0]; }
check(item('usb_role_state').value.en=='Device mode','Policy mistaken for actual role');
check(item('usb_net_current').value=='NCM','Saved mode mistaken for active protocol');
check(length(item('usb_net_mode').options)==3,'Missing USB protocols');
for (let pair in [['usb_role','host'],['usb_net_mode','ecm'],['usb_net_scope','permanent'],['usb_host_boot',true],['usb_net_auto',false]])
    check(usb.set(pair[0],pair[1])==null,'Valid USB setting rejected');
check(index(calls,'/usr/libexec/unisoc-modem/device-usb set-role host 0')>=0,'Role switch backend differs');
check(index(calls,'/usr/libexec/unisoc-modem/device-usb set-role host 1')>=0,'Persistent host setting lost');
check(index(calls,'/usr/libexec/unisoc-modem/device-usb set-net ecm once 1')>=0,'Protocol setting lost');
check(index(calls,'/usr/libexec/unisoc-modem/device-usb set-net rndis once 0')>=0,'Disable protocol ignored');
state.net_auto=0;calls=[];
usb.set('usb_net_mode','ecm');usb.set('usb_net_scope','permanent');
check(index(calls,'/usr/libexec/unisoc-modem/device-usb set-net ecm once 0')>=0,'Changing mode unexpectedly re-enabled auto apply');
check(index(calls,'/usr/libexec/unisoc-modem/device-usb set-net rndis permanent 0')>=0,'Changing scope unexpectedly re-enabled auto apply');
for (let pair in [['usb_role','host; reboot'],['usb_net_mode','rndis; reboot'],['usb_net_scope','forever'],['usb_host_boot','1']]) {
    calls=[];check(usb.set(pair[0],pair[1])!=null,'Invalid input accepted');
    check(length(calls)==1,'Invalid input reached mutation command');
}
print('PASS: shared USB settings backend, actual vs selected state, one-boot scope and input validation\n');

'use strict';
let calls = [], fail = false;
let ctx = {run:()=>1,uci:()=>({get:()=>null}),sh_json:()=>({}),ubus:(object,method,args)=>{
    push(calls,{object,method,args});return fail ? {ok:0,error:'storage_failed'} : {ok:1};
}};
let categories = loadfile(ARGV[0],{raw_mode:true})()(ctx);
function check(value,why) {if(!value) die(why);}
let c = filter(categories,c=>c.id=='traffic_clear')[0];
check(c.parent=='system','Clear history must be a nested page');
let items=c.items();
check(length(items)==3,'Missing per-SIM/all scopes');
for(let i in items) check(i.confirm && i.type=='action','Destructive action missing confirmation');
for(let scope in ['0','1','all']) {
    check(c.set('clear_'+scope)==null,'Clear failed');
    let call=calls[length(calls)-1];
    check(call.object=='unisoc.traffic' && call.method=='clear' && call.args.slot==scope && call.args.confirm===true,'Screen bypassed shared ledger or selected wrong scope');
}
let count=length(calls);
check(c.set('clear_2')=='invalid_slot' && length(calls)==count,'Invalid scope reached backend');
fail=true;check(c.set('clear_0')=='storage_failed','Failure incorrectly acknowledged');
print('PASS: screen scopes, confirmation, common service and failure propagation\n');

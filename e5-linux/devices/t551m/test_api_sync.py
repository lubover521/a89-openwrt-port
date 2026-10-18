"""Execute screen/SMS functions with ucode mocks on OpenWrt; no real mutations."""
from pathlib import Path
import subprocess,sys,tempfile

root=Path(sys.argv[1]);api=(root/'usr/share/e5-infoscreen/api.uc').read_text()
sms=(root/'usr/libexec/e5-sms').read_text()
def part(source,start,end):return source[source.index(start):source.index(end,source.index(start))]
code='''let calls=[],hidden='[1000000001]',currentSlot=0,changeSlot=false,saved=[];
function check(v,why){if(!v)die(why);}
function readfile(path){return hidden;}
function sim_card(){return currentSlot;}
function state_get(){return null;}
function state_put(key,value){push(saved,{key,value});}
function at(cmd,timeout,slot){check(slot==currentSlot,'QoS query lost its slot');if(changeSlot)currentSlot=1;return [1,9,0,0,0,0,100,20];}
function payload_ints(v){return v;}
function at_warning(cmd){return false;}
function ubus_call(object,method,args){push(calls,{object,method,args});return {ok:true,reply:'OK'};}
'''
code+=part(sms,'function visible(messages)','function sms_list()')
code+=part(api,'function sms_delete(id)','// e5-linux\'s /usr/libexec/e5-sms:')
code+=part(api,'function at_console(cmd','// Internal queries')
code+=part(api,'function qos_status(m)','function status()')
code+='''
check(qos_status({present:true,tech:'lte'}).dl_kbps==100 && saved[0].key=='qos-0','QoS not scoped');
saved=[];changeSlot=true;
check(qos_status({present:true,tech:'lte'})==null && length(saved)==0,'Card change contaminated QoS cache');
currentSlot=0;
check(length(visible([{id:1000000001},{id:1000000002}]))==1,'Local deletion not shared');
check(at_console('AT+CSQ',8,'1').ok,'AT rejected');
check(calls[0].object=='mu300dash'&&calls[0].method=='at'&&calls[0].args.slot=='1','AT bypassed common SIM owner/history');
let count=length(calls);check(!at_console('AT',8,'3').ok&&length(calls)==count,'Invalid AT scope sent');
check(sms_delete(1000000002),'SMS delete failed');
check(calls[1].method=='sms_delete'&&calls[1].args.sim=='0','Screen deleted SIM storage implicitly');
check(!sms_delete('1;reboot')&&length(calls)==2,'Invalid SMS ID reached backend');
print('PASS: shared local SMS visibility/deletion, captured AT scope/history and invalid input rejection\\n');
'''
with tempfile.NamedTemporaryFile(suffix='.uc',mode='w') as f:
    f.write(code);f.flush();subprocess.run(['ucode',f.name],check=True)

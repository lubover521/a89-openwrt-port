'use strict';
let commands = [];
let state = {ok:true,available:true,persistent:false,voltage_min:-50000,voltage_max:25000,voltage_step:3125,policies:[
    {id:'policy0',cpus:'0 1 2 3 4 5',current:600000,min:600000,max:1200000,governor:'schedutil',
     governors:['schedutil','powersave'],frequencies:[600000,900000,1200000],voltages:[{khz:600000,uv:600000}],voltage_boot_writable:true,voltage_offset:0,voltage_next:-3125},
    {id:'policy6',cpus:'6',current:900000,min:900000,max:1500000,governor:'schedutil',
     governors:['schedutil','powersave'],frequencies:[900000,1500000],voltages:[{khz:900000,uv:700000}]}
],zones:[{id:'thermal_zone7',name:'soc-thmzone',temp:45000,trips:[
    {id:0,type:'passive',temp:70000,hysteresis:1000,writable:true},
    {id:1,type:'critical',temp:110000,hysteresis:2000,writable:false}]}]};
let ctx = {run:()=>1,uci:()=>({get:()=>null}),sh_json:cmd=>{push(commands,cmd);return state;}};
let categories = loadfile(ARGV[0],{raw_mode:true})()(ctx);
function check(value,message) {if(!value) die(message);}
function cat(id) {return filter(categories,c=>c.id==id)[0];}
check(cat('cpu').parent=='system','CPU must be inside System');
check(cat('cpu_policy0').parent=='cpu','Domain not nested');
check(cat('cpu_policy0').items()[0].value=='600 MHz','Wrong closure for policy0');
check(cat('cpu_policy6').items()[0].value=='900 MHz','Wrong closure for policy6');
let voltage=filter(cat('cpu_policy0').items(),x=>x.id=='policy0_voltage_next')[0];
check(voltage.type=='choice'&&voltage.value=='-3125'&&length(voltage.options)==25,'Voltage selector range or units');
let thermal=cat('cpu_thermal').items();
check(thermal[1].type=='number'&&thermal[1].max==100,'Passive range');
check(thermal[2].type=='info','Critical shutdown must be read-only');
check(cat('cpu_policy0').set('policy0_max',900000)==null,'Shared setter failed');
check(match(commands[length(commands)-1],/cpu-control set/),'Screen bypassed shared backend');
print('PASS: nested CPU categories, independent domain closures, voltage readout and protected trips\n');

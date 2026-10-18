/* A late HTTP fallback must not undo a more recent pushed call state. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const hooks={},received=[];
let source,complete,requests=0;
const context={
    console,Set,WeakSet,performance,AbortController,setTimeout,clearTimeout,
    blank:false,last:{screen:{touch:true}},location:{hostname:'127.0.0.1'},
    addEventListener:(name,handler)=>{hooks[name]=handler;},
    EventSource:class {constructor(){source=this;}close(){this.closed=true;}},
    fetch:()=>{requests++;return new Promise(resolve=>{complete=resolve;});}
};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname+'/infoscreen/calls.js','utf8'),context);
const calls=context.T551MCalls;
const emit=data=>source.onmessage({data:JSON.stringify(data)});
(async()=>{
    const unsubscribe=calls.subscribe(data=>received.push(data));
    calls.boot();emit({calls:[]});assert.equal(requests,0);
    source.onerror();assert.equal(requests,1);
    emit({calls:[{id:'test',state:'active'}]});
    complete({ok:true,json:async()=>({calls:[]})});
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(received.at(-1).calls[0].id,'test');
    const count=received.length;unsubscribe();emit({calls:[]});
    assert.equal(received.length,count);
    hooks.pagehide();assert.equal(source.closed,true);
    console.log('Push recovery rejects stale fallback; subscriber and page cleanup PASS');
})().catch(error=>{hooks.pagehide();console.error(error);process.exitCode=1;});

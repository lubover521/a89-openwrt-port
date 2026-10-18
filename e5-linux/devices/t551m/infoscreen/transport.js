/* Keep local JSON reads on one connection; never replay a control action. */
'use strict';
window.T551MTransport = (() => {
    const nativeFetch=window.fetch.bind(window), pending=new Map();
    let socket=null, nextId=0, retryAfter=0, stopped=false;
    const unavailable=()=>new Error('Local read transport unavailable');
    function fail(error=unavailable()) {
        retryAfter=performance.now()+3000;
        for(const item of [...pending.values()])item.finish(error);
    }
    function connect() {
        if(stopped || typeof WebSocket!=='function' || location.origin!=='http://127.0.0.1:8088')return;
        if(socket && socket.readyState<=1)return;
        if(performance.now()<retryAfter)return;
        const current=new WebSocket('ws://127.0.0.1:8089/rpc');socket=current;
        current.onmessage=event=>{
            if(socket!==current)return;
            try {
                const value=JSON.parse(event.data);
                if(value.event==='power-supply-change') {
                    window.dispatchEvent(new Event('e5-power-supply-change'));
                    return;
                }
                const item=pending.get(value.id);
                if(!item)return;
                if(value.fallback || !Number.isInteger(value.status) || value.status<200 || value.status>599 || typeof value.body!=='string')
                    item.finish(unavailable());
                else item.finish(null,new Response(value.status===204||value.status===205||value.status===304?null:value.body,
                    {status:value.status,headers:{'Content-Type':value.type||'application/json','Cache-Control':'no-store'}}));
            } catch(_) {current.close();fail();}
        };
        current.onclose=()=>{if(socket===current)fail();};
        current.onerror=()=>{if(socket===current)fail();};
    }
    function request(path, signal) {
        return new Promise((resolve,reject)=>{
            const id=++nextId;
            const abort=()=>finish(new DOMException('The operation was aborted.','AbortError'));
            const timer=setTimeout(()=>finish(unavailable()),10000);
            function finish(error,response) {
                if(!pending.delete(id))return;
                clearTimeout(timer);signal?.removeEventListener('abort',abort);
                error?reject(error):resolve(response);
            }
            pending.set(id,{finish});
            signal?.addEventListener('abort',abort,{once:true});
            if(signal?.aborted){abort();return;}
            try{socket.send(JSON.stringify({id,path}));}catch(_){finish(unavailable());}
        });
    }
    async function fetch(input, options={}) {
        // Only string GET URLs are intercepted. Uploads, POSTs, arbitrary
        // Request objects and non-local URLs retain native fetch semantics.
        if(typeof input!=='string' || (options.method||'GET').toUpperCase()!=='GET' ||
            Object.keys(options).some(key=>!['method','cache','signal'].includes(key)))return nativeFetch(input,options);
        let url;try{url=new URL(input,location.href);}catch(_){return nativeFetch(input,options);}
        if(url.origin!==location.origin || !url.pathname.startsWith('/api/'))return nativeFetch(input,options);
        connect();
        if(socket?.readyState===1 && pending.size<8) {
            try{return await request(url.pathname+url.search,options.signal);}
            catch(error){if(error.name==='AbortError' || options.signal?.aborted)throw error;}
        }
        return nativeFetch(input,options);
    }
    window.addEventListener('pagehide',()=>{stopped=true;socket?.close();fail(new DOMException('Page closed.','AbortError'));});
    window.addEventListener('pageshow',event=>{if(event.persisted){stopped=false;retryAfter=0;connect();}});
    connect();
    window.fetch=fetch;
    return {fetch};
})();

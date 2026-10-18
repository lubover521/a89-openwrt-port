'use strict';
'require view';
'require rpc';
'require ui';

var getWallpaper = rpc.declare({object:'t551m-screen',method:'wallpaper_get',params:['target'],expect:{}});
var readWallpaper = rpc.declare({object:'t551m-screen',method:'wallpaper_read',params:['target','offset','revision'],expect:{}});
var uploadWallpaper = rpc.declare({object:'t551m-screen',method:'wallpaper_upload',params:['target','token','offset','png'],expect:{}});
var finishWallpaper = rpc.declare({object:'t551m-screen',method:'wallpaper_finish',params:['target','token'],expect:{}});
var resetWallpaper = rpc.declare({object:'t551m-screen',method:'wallpaper_reset',params:['target'],expect:{}});

async function loadWallpaper(target) {
    var data=await getWallpaper(target);
    if(!data.ok)throw new Error(data.error||'读取壁纸失败');
    if(!data.custom || data.png)return data;
    var offset=0, parts=[];
    while(offset<data.bytes) {
        var r=await readWallpaper(target,String(offset),data.revision);
        if(!r.ok || !r.png || r.next<=offset)throw new Error(r.error||'读取壁纸失败，请刷新重试');
        parts.push(r.png);offset=r.next;
    }
    data.png=parts.join('');return data;
}

async function saveWallpaper(target,png,progress) {
    var token='', offset=0;
    for(var start=0;start<png.length;start+=16384) {
        var part=png.slice(start,start+16384);
        var r=await uploadWallpaper(target,token,String(offset),part);
        if(!r.ok)throw new Error(r.error||'上传失败');
        token=r.token;offset=r.next;
        progress(Math.min(100,Math.round((start+part.length)/png.length*100)));
    }
    return finishWallpaper(target,token);
}

function makeImage(file) {
    if (!file || !/^image\/(png|jpeg|webp)$/.test(file.type) || file.size>12*1024*1024)
        return Promise.reject(new Error('请选择 12 MB 以内的 JPG、PNG 或 WebP 图片。'));
    return new Promise(function(resolve,reject) {
        var image = new Image(), url = URL.createObjectURL(file);
        image.onload = function() {
            try {
                var canvas = document.createElement('canvas'); canvas.width=320; canvas.height=480;
                var ctx=canvas.getContext('2d'), scale=Math.max(320/image.naturalWidth,480/image.naturalHeight);
                ctx.fillStyle='#0c121b'; ctx.fillRect(0,0,320,480);
                ctx.drawImage(image,(320-image.naturalWidth*scale)/2,(480-image.naturalHeight*scale)/2,
                    image.naturalWidth*scale,image.naturalHeight*scale);
                resolve(canvas.toDataURL('image/png'));
            } catch(e) {reject(e);} finally {URL.revokeObjectURL(url);}
        };
        image.onerror=function() {URL.revokeObjectURL(url);reject(new Error('无法读取这张图片。'));};
        image.src=url;
    });
}

return view.extend({
    load:function() {return Promise.all([loadWallpaper('lock'),loadWallpaper('desktop')]);},
    render:function(data) {
        var cards=['lock','desktop'].map(function(target,index) {
            var title=index?'桌面壁纸':'锁屏壁纸', pending=null;
            var saved=data[index] || {}, preview=E('div',{'class':'t551m-wallpaper-preview'});
            function paint(png) {preview.style.backgroundImage=png?'linear-gradient(#0b142026,#0b142050),url("'+png+'")':'';}
            if(saved.png)paint('data:image/png;base64,'+saved.png);
            preview.appendChild(E('div',{'class':'t551m-wallpaper-overlay'},index ? [
                E('span','随身网络'),E('strong','桌面预览'),E('div',{'class':'t551m-wallpaper-card'},'清晰的卡片 · 你的壁纸')
            ] : [E('span','锁屏预览'),E('strong','09:41'),E('div',{'class':'t551m-wallpaper-card'},'今日流量　 ·　 本月流量')]));
            var status=E('p',{'class':'description'},saved.custom?'已设置自定义壁纸':'正在使用默认背景');
            var input=E('input',{type:'file',accept:'image/jpeg,image/png,image/webp',style:'display:none'});
            var apply=E('button',{type:'button','class':'cbi-button cbi-button-apply',disabled:true},'应用到'+(index?'桌面':'锁屏'));
            var choose=E('button',{type:'button','class':'cbi-button'},'选择图片');
            var reset=E('button',{type:'button','class':'cbi-button'},'恢复默认');
            choose.onclick=function() {input.click();};
            input.onchange=function() {
                makeImage(input.files[0]).then(function(png) {pending=png;paint(png);apply.disabled=false;status.textContent='预览已就绪，点击应用后生效';})
                .catch(function(e) {ui.addNotification(null,E('p',e.message),'error');});
            };
            function busy(on) {choose.disabled=reset.disabled=on;apply.disabled=on || !pending;}
            apply.onclick=function() {
                if(!pending)return;
                busy(true);
                return saveWallpaper(target,pending.split(',')[1],function(percent) {status.textContent='正在上传 '+percent+'%';}).then(function(r) {
                    if(!r.ok)throw new Error(r.error||'保存失败');
                    pending=null;status.textContent='已保存，设备屏幕会自动更新';
                }).catch(function(e) {status.textContent='保存失败，可点击应用重试';ui.addNotification(null,E('p',e.message),'error');}).finally(function() {busy(false);});
            };
            reset.onclick=function() {
                busy(true);
                return resetWallpaper(target).then(function(r) {
                    if(!r.ok)throw new Error(r.error||'恢复失败');
                    pending=null;input.value='';paint(null);status.textContent='已恢复默认背景';
                }).catch(function(e) {ui.addNotification(null,E('p',e.message),'error');}).finally(function() {busy(false);});
            };
            return E('section',{'class':'t551m-wallpaper-section'},[E('h3',title),preview,status,input,
                E('div',{'class':'t551m-wallpaper-actions'},[choose,apply,reset])]);
        });
        return E('div',{},[E('style',{},`
            .t551m-wallpapers{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}
            .t551m-wallpaper-section{min-width:0;padding:20px;border:1px solid var(--border,#ddd);border-radius:16px}
            .t551m-wallpaper-preview{position:relative;width:200px;max-width:100%;aspect-ratio:2/3;border-radius:18px;overflow:hidden;background:radial-gradient(ellipse at 12% 10%,#224844,#152530 40%,#0c1420 78%);background-position:center;background-size:cover;color:#eef6f8;margin:18px auto}
            .t551m-wallpaper-overlay{display:flex;flex-direction:column;align-items:center;padding:28px 12px;gap:20px;font-size:11px}.t551m-wallpaper-overlay strong{font-size:32px;color:#eef6f8}.t551m-wallpaper-card{padding:18px 8px;background:#0c142090;border-radius:12px}
            .t551m-wallpaper-actions{display:flex;gap:8px;flex-wrap:wrap}.t551m-wallpaper-actions button{white-space:nowrap}
            @media(max-width:650px){.t551m-wallpapers{grid-template-columns:minmax(0,1fr)}}
        `),E('h2','设备屏幕壁纸'),E('p',{'class':'description'},'分别设置锁屏和桌面背景。图片在浏览器中居中裁剪为 320 × 480，预览确认后保存。壁纸保存在本机，重启后保留。'),
        E('div',{'class':'t551m-wallpapers'},cards)]);
    },
    handleSaveApply:null,handleSave:null,handleReset:null
});

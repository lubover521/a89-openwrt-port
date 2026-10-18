'use strict';
'require view';
'require rpc';
'require ui';
'require mu300.common as M';

const words = {
 '铃声与通知':['Ringtones & notifications','Zil sesleri ve bildirimler'],
 '让提醒听起来更合心意':['Make every alert sound right','Bildirim seslerinizi kişiselleştirin'],
 '来电铃声':['Incoming calls','Gelen aramalar'], '短信提示音':['SMS alerts','SMS bildirimleri'],
 '来电时循环播放，接听或挂断后立即停止。':['Repeats until you answer or the call ends.','Yanıtlayana veya arama bitene kadar yinelenir.'],
 '收到新短信时播放一次；通话中保持安静。':['Plays once for new messages; silent during calls.','Yeni mesajda bir kez çalar; arama sırasında sessizdir.'],
 '开启声音':['Enable sound','Sesi etkinleştir'], '当前声音':['Selected sound','Seçili ses'],
 '电话铃（默认）':['Phone ring (default)','Telefon zili (varsayılan)'],
 '清脆叮声（默认）':['Soft ding (default)','Yumuşak ding (varsayılan)'],
 '短提示音':['Short beep','Kısa bip'], '自定义音频':['Custom audio','Özel ses'],
 '上传音频':['Upload audio','Ses yükle'], '设备试听':['Play on device','Cihazda dinle'],
 '停止试听':['Stop preview','Önizlemeyi durdur'], '恢复默认':['Restore default','Varsayılana dön'],
 '恢复默认声音？':['Restore the default sound?','Varsayılan sese dönülsün mü?'],
 '会移除已上传的音频，声音开关保持不变。':['Removes your uploaded audio without changing the sound switch.','Yüklenen sesi kaldırır; ses anahtarı değişmez.'],
 '取消':['Cancel','İptal'], '确认':['Confirm','Onayla'],
 '已保存':['Saved','Kaydedildi'], '正在处理音频…':['Processing audio…','Ses işleniyor…'],
 '正在上传…':['Uploading…','Yükleniyor…'], '正在设备上试听（最多 8 秒）':['Playing on device (up to 8 seconds)','Cihazda çalınıyor (en fazla 8 saniye)'],
 '试听已停止':['Preview stopped','Önizleme durduruldu'], '操作失败':['Operation failed','İşlem başarısız'],
 '请选择 12 MB 以内的音频文件。':['Choose an audio file under 12 MB.','12 MB altında bir ses dosyası seçin.'],
 '浏览器无法解码此音频，请换用 MP3 或 WAV。':['Your browser cannot decode this audio. Try MP3 or WAV.','Tarayıcı bu sesi çözemiyor. MP3 veya WAV deneyin.'],
 '音频太短或无效。':['Audio is too short or invalid.','Ses çok kısa veya geçersiz.'],
 '支持浏览器可解码的 MP3、WAV、M4A、OGG，最大 12 MB。':['MP3, WAV, M4A or OGG supported by your browser; up to 12 MB.','Tarayıcınızın desteklediği MP3, WAV, M4A veya OGG; en fazla 12 MB.'],
 '来电铃声保留前 30 秒，短信提示音保留前 5 秒。':['Keeps the first 30 seconds for calls and 5 seconds for SMS.','Aramalar için ilk 30, SMS için ilk 5 saniye saklanır.'],
 '沿用设备媒体音量；音量为 0 时静音。试听会在设备上播放。':['Uses device media volume; 0 is mute. Previews play on the device.','Cihazın medya sesini kullanır; 0 sessizdir. Önizleme cihazda çalar.'],
 'Preview unavailable during calls':['通话时无法试听','Arama sırasında önizleme kullanılamaz'],
 'Device volume is muted':['设备音量为 0，请先调高音量','Cihaz sessizde; önce sesi açın'],
 'Upload a sound first':['请先上传音频','Önce bir ses yükleyin']
};
function t(s) {
 const lang = M.uiLanguage(), value = words[s];
 if (!value) return s;
 if (/^[A-Za-z]/.test(s)) return lang === 'zh' ? value[0] : lang === 'tr' ? value[1] : s;
 return lang === 'zh' ? s : value[lang === 'tr' ? 1 : 0];
}
function txt(s) { return document.createTextNode(String(s == null ? '' : s)); }
const get = rpc.declare({object:'e5-sounds',method:'status',expect:{}});
const configure = rpc.declare({object:'e5-sounds',method:'configure',params:['target','enabled','tone'],expect:{}});
const upload = rpc.declare({object:'e5-sounds',method:'upload',params:['target','token','offset','data'],expect:{}});
const finish = rpc.declare({object:'e5-sounds',method:'finish',params:['target','token','name'],expect:{}});
const reset = rpc.declare({object:'e5-sounds',method:'reset',params:['target'],expect:{}});
const preview = rpc.declare({object:'e5-sounds',method:'preview',params:['target'],expect:{}});
const stop = rpc.declare({object:'e5-sounds',method:'stop',expect:{}});
function checked(r) { if (!r || r.ok !== true) throw new Error(t(r && r.error || '操作失败')); return r; }

function encodeWav(samples, rate) {
 const buffer = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buffer);
 const text = (offset, value) => { for (let i=0;i<value.length;i++) v.setUint8(offset+i,value.charCodeAt(i)); };
 text(0,'RIFF');v.setUint32(4,buffer.byteLength-8,true);text(8,'WAVEfmt ');
 v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,rate,true);
 v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);text(36,'data');v.setUint32(40,samples.length*2,true);
 let peak=0;
 for (const value of samples) peak=Math.max(peak,Math.abs(value));
 // Only attenuate. Never boost a quiet recording to an unexpected loud level.
 const gain=peak>.65?.65/peak:1, fade=Math.min(Math.floor(rate*.008),samples.length/2);
 for(let i=0;i<samples.length;i++) {
  const envelope=Math.min(1,i/fade,(samples.length-1-i)/fade);
  const value=Math.max(-1,Math.min(1,samples[i]*gain*envelope));
  v.setInt16(44+i*2,Math.round(value*32767),true);
 }
 return new Uint8Array(buffer);
}

async function convert(file, target) {
 if (!file || file.size > 12*1024*1024 || !file.size) throw new Error(t('请选择 12 MB 以内的音频文件。'));
 const Context=window.AudioContext || window.webkitAudioContext;
 const Offline=window.OfflineAudioContext || window.webkitOfflineAudioContext;
 if (!Context || !Offline) throw new Error(t('浏览器无法解码此音频，请换用 MP3 或 WAV。'));
 const context=new Context();let decoded;
 try { decoded=await context.decodeAudioData(await file.arrayBuffer()); }
 catch(e) { throw new Error(t('浏览器无法解码此音频，请换用 MP3 或 WAV。')); }
 finally { await context.close(); }
 if (!Number.isFinite(decoded.duration) || decoded.duration < .05) throw new Error(t('音频太短或无效。'));
 const rate=32000, duration=Math.min(decoded.duration,target==='ring'?30:5);
 const offline=new Offline(1,Math.floor(duration*rate),rate), source=offline.createBufferSource();
 source.buffer=decoded;source.connect(offline.destination);source.start();
 return encodeWav((await offline.startRendering()).getChannelData(0),rate);
}

const css=`
.sound-page{max-width:1100px;margin:auto;color:var(--text,inherit)}
.sound-page .sound-intro{line-height:1.8;color:var(--text-muted,#858c99);margin:8px 0 24px}
.sound-page .sound-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
.sound-page .sound-card{padding:24px;border:1px solid var(--hairline,rgba(128,128,128,.22));border-radius:18px;background:var(--surface,transparent);min-width:0}
.sound-page .sound-top{display:flex;align-items:center;gap:14px;margin-bottom:16px}
.sound-page .sound-symbol{display:grid;place-items:center;width:44px;height:44px;border-radius:14px;background:rgba(80,150,160,.12);color:var(--primary,#59aeb7);flex:none}
.sound-page h3{margin:0;font-size:1.12rem}.sound-page .sound-desc{min-height:3em;line-height:1.6;color:var(--text-muted,#858c99)}
.sound-page .sound-toggle{display:flex;align-items:center;gap:10px;margin:22px 0;font-weight:600}.sound-page input[type=checkbox]{margin:0!important;width:18px;height:18px;accent-color:var(--primary,#59aeb7)}
.sound-page .sound-label{display:block;font-size:.85rem;margin-bottom:9px}.sound-page select{width:100%;max-width:100%;padding:10px 12px!important;border-radius:10px;background:var(--input-bg,var(--surface,transparent));color:inherit}
.sound-page .sound-file{overflow-wrap:anywhere;min-height:1.6em;font-size:.85rem;line-height:1.6;margin:10px 0 18px;color:var(--text-muted,#858c99)}
.sound-page .sound-actions{display:flex;gap:10px;flex-wrap:wrap}.sound-page .sound-actions button{min-height:36px;margin:0!important;border-radius:9px!important}
.sound-page .sound-feedback{line-height:1.7;margin:14px 0 0;min-height:1.7em;overflow-wrap:anywhere}.sound-page .sound-feedback.error{color:var(--danger,#df6c6c)}
.sound-page .sound-foot{margin-top:24px;font-size:.86rem;line-height:1.9;color:var(--text-muted,#858c99)}
@media(max-width:750px){.sound-page .sound-grid{grid-template-columns:1fr}.sound-page .sound-card{padding:20px}.sound-page .sound-desc{min-height:0}}
`;
function icon(kind) {
 const path=kind==='ring'?'M5 3h4l2 5-3 2a16 16 0 0 0 6 6l2-3 5 2v4a2 2 0 0 1-2 2C9.6 21 3 14.4 3 5a2 2 0 0 1 2-2Z':'M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2Zm2 5h10M7 13h7';
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width','23');svg.setAttribute('height','23');svg.setAttribute('aria-hidden','true');
 const p=document.createElementNS(svg.namespaceURI,'path');for(const [key,value] of Object.entries({d:path,fill:'none',stroke:'currentColor','stroke-width':'1.7','stroke-linecap':'round','stroke-linejoin':'round'}))p.setAttribute(key,value);svg.appendChild(p);return svg;
}

return view.extend({
 load:async function(){return checked(await get());},
 render:function(initial){
  let state=initial;const cards=[];
  const refresh=async()=>{state=checked(await get());cards.forEach(card=>card.paint());};
  const make=target=>{
   const enabled=E('input',{type:'checkbox'}),select=E('select'),name=E('p',{class:'sound-file'}),feedback=E('p',{class:'sound-feedback',role:'status','aria-live':'polite'});
   const file=E('input',{type:'file',accept:'audio/*,.mp3,.wav,.m4a,.ogg',style:'display:none'});
   let busy=false;const controls=[];
   const paint=()=>{
    const s=state.targets[target];enabled.checked=s.enabled;
    select.replaceChildren();
    const choices=target==='ring'?[['call','电话铃（默认）'],['beep','短提示音']]:[['ding','清脆叮声（默认）']];
    if(s.custom)choices.push(['custom','自定义音频']);
    choices.forEach(([value,label])=>select.appendChild(E('option',{value},txt(t(label)))));select.value=s.tone;
    name.textContent=s.custom?s.name+' · '+s.duration.toFixed(1)+' s':'';
    [...controls,enabled,select].forEach(node=>{node.disabled=busy;});
   };
   const action=async(fn,message)=>{
    if(busy)return;busy=true;[...controls,enabled,select].forEach(node=>{node.disabled=true;});feedback.classList.remove('error');feedback.textContent='';
    try{await fn();await refresh();feedback.textContent=message||t('已保存');}
    catch(e){feedback.classList.add('error');feedback.textContent=e.message||t('操作失败');}
    finally{busy=false;paint();}
   };
   enabled.addEventListener('change',()=>{const value=enabled.checked;action(async()=>checked(await configure(target,value,select.value)));});
   select.addEventListener('change',()=>{const value=select.value;action(async()=>checked(await configure(target,enabled.checked,value)));});
   const button=(label,fn,primary=false)=>{const b=E('button',{class:'cbi-button '+(primary?'cbi-button-action':''),click:fn},txt(t(label)));controls.push(b);return b;};
   file.addEventListener('change',()=>{const selected=file.files[0];if(!selected)return;
    action(async()=>{
     feedback.textContent=t('正在处理音频…');const data=await convert(selected,target);let token='',offset=0;
     while(offset<data.length){const chunk=data.subarray(offset,Math.min(offset+12288,data.length));let bytes='';for(const b of chunk)bytes+=String.fromCharCode(b);
      const r=checked(await upload(target,token,String(offset),btoa(bytes)));if(r.next!==offset+chunk.length)throw new Error(t('操作失败'));token=r.token;offset=r.next;
      feedback.textContent=t('正在上传…')+' '+Math.round(offset/data.length*100)+'%';}
     checked(await finish(target,token,selected.name));file.value='';
    });
   });
   const panel=E('section',{class:'sound-card'},[
    E('div',{class:'sound-top'},[E('div',{class:'sound-symbol'},[icon(target)]),E('h3',{},txt(t(target==='ring'?'来电铃声':'短信提示音')))]),
    E('p',{class:'sound-desc'},txt(t(target==='ring'?'来电时循环播放，接听或挂断后立即停止。':'收到新短信时播放一次；通话中保持安静。'))),
    E('label',{class:'sound-toggle'},[enabled,txt(t('开启声音'))]),E('label',{class:'sound-label',for:'sound-'+target},txt(t('当前声音'))),select,name,file,
    E('div',{class:'sound-actions'},[
     button('上传音频',()=>file.click(),true),
     button('设备试听',()=>action(async()=>checked(await preview(target)),t('正在设备上试听（最多 8 秒）'))),
     button('停止试听',()=>action(async()=>checked(await stop()),t('试听已停止'))),
     button('恢复默认',()=>ui.showModal(t('恢复默认声音？'),[
      E('p',{},txt(t('会移除已上传的音频，声音开关保持不变。'))),
      E('div',{class:'right'},[E('button',{class:'cbi-button',click:ui.hideModal},txt(t('取消'))),
       E('button',{class:'cbi-button cbi-button-action',style:'margin-left:12px',click:()=>{ui.hideModal();action(async()=>checked(await reset(target)));}},txt(t('确认')))])]))
    ]),feedback]);select.id='sound-'+target;
   cards.push({paint});paint();return panel;
  };
  return E('div',{class:'sound-page'},[E('style',{},css),E('h2',{},txt(t('铃声与通知'))),
   E('p',{class:'sound-intro'},txt(t('让提醒听起来更合心意'))),E('div',{class:'sound-grid'},[make('ring'),make('sms')]),
   E('div',{class:'sound-foot'},[E('div',{},txt(t('支持浏览器可解码的 MP3、WAV、M4A、OGG，最大 12 MB。'))),E('div',{},txt(t('来电铃声保留前 30 秒，短信提示音保留前 5 秒。'))),E('div',{},txt(t('沿用设备媒体音量；音量为 0 时静音。试听会在设备上播放。')))])]);
 },handleSaveApply:null,handleSave:null,handleReset:null
});

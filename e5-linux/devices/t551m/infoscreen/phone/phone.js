'use strict';
const callOnly = new URLSearchParams(location.search).get('callonly') === '1';
document.body.classList.toggle('call-only', callOnly);
const $ = id => document.getElementById(id);
const words = {
 phone:['电话','Phone'], enterNumber:['输入电话号码','Enter a number'], dial:['拨号','Call'],
 keypad:['键盘','Keypad'], hideKeypad:['收起键盘','Hide keypad'],
 toneFailed:['按键音发送失败，请确认通话状态后重试','Tone failed; check the call before trying again'],
 contacts:['通讯录','Contacts'], newContact:['新建联系人','New contact'], contactName:['姓名（可选）','Name (optional)'],
 contactNumber:['电话号码','Phone number'], save:['保存','Save'], cancel:['取消','Cancel'],
 answer:['接听','Answer'], hangup:['挂断','End call'], delete:['删除','Delete'], deleteContact:['删除联系人？','Delete contact?'],
 speaker:['扬声器','Speaker'], mute:['静音','Mute mic'], audioWait:['通话音频尚未启动','Call audio has not started'],
 audioOutput:['通话音频','Call audio'], receiver:['手机','Phone'], bluetooth:['蓝牙耳机','Bluetooth'],
 btDisconnected:['未连接通话耳机','No call headset connected'], done:['完成','Done'],
 connectingAudio:['连接蓝牙…','Connecting…'],
 noContacts:['暂无联系人 · 输入号码后按 ＋ 保存','No contacts · enter a number and press +'],
 idle:['待机','Ready'], offline:['服务不可用','Unavailable'], dialing:['正在拨出…','Calling…'],
 'ringing-out':['等待对方接听','Ringing…'], 'ringing-in':['来电','Incoming call'], waiting:['来电等待','Call waiting'],
 active:['通话中','In call'], held:['通话保持','On hold'],
 invalid:['请输入至少 3 位有效号码','Enter a valid number (at least 3 digits)'],
 timedOut:['请求超时，通话结果尚未确认。请查看通话状态，不要重复拨号。','Request timed out; call result is unknown. Check its state before dialing again.'],
 noState:['拨号请求已发送，暂未收到通话状态。','Call requested; waiting for modem state.'],
 settling:['请稍候…','Please wait…'],
 saved:['联系人已保存','Contact saved'], saveNumber:['保存联系人','Save contact'], backspace:['退格','Delete digit'],
 confirm:['请先用方向键选择按钮，再按确认。','Choose a button with the arrows, then confirm.']
};
const t = key => { const w=words[key]; return w ? e5.t({zh:w[0],en:w[1]}) : key; };
const LIVE = new Set(['dialing','ringing-out','ringing-in','active','held','waiting']);
let number='', contacts=[], calls=[], pending=null, reading=false, feedback=null;
let contactsSignature='', deleteNumber=null, activeId=null, activeSince=null, zeroTimer=null, zeroHeld=false;
let awaitingId=null, awaitingSince=0;
let dialAfter=0;
let selectedCard=0, simPicked=false, selectedCall=null;
let audio={available:false,active:false,speaker:false,muted:false}, audioFeedback=false;
let dtmfOpen=false, toneCall=null, toneDigits='', tones=[], sendingTone=false;
let liveRevision=0;
function toggleKeypad(on) {
 dtmfOpen=!!on && current()?.state==='active';
 $('dtmf-panel').hidden=!dtmfOpen;
 $('dtmf-toggle').setAttribute('aria-expanded',String(dtmfOpen));
 $('dtmf-toggle').textContent=t(dtmfOpen?'hideKeypad':'keypad');
 $('call-card').classList.toggle('dtmf-open',dtmfOpen);
}
async function sendTone(tone) {
 const c=current();
 if(c?.state!=='active'||pending||!/^[0-9*#]$/.test(tone)||tones.length>=32)return;
 tones.push({id:c.id,tone});
 if(sendingTone)return;
 sendingTone=true;
 try {
  while(tones.length){
   const next=tones.shift();
   if(current()?.id!==next.id||current()?.state!=='active') {tones=[];break;}
   try {
    await request('/dtmf',next);
    if(current()?.id!==next.id||current()?.state!=='active'){tones=[];break;}
    toneDigits=(toneDigits+next.tone).slice(-32);$('dtmf-digits').textContent=toneDigits;
    await new Promise(resolve=>setTimeout(resolve,60));
   } catch(e){tones=[];showFeedback(t('toneFailed')+': '+e.message);break;}
  }
 } finally {sendingTone=false;}
}
function translate() {
 document.querySelectorAll('[data-text]').forEach(el=>el.textContent=t(el.dataset.text));
 $('save-number').setAttribute('aria-label',t('saveNumber'));
 $('backspace').setAttribute('aria-label',t('backspace'));
 contactsSignature=''; render();
}
function showFeedback(text, info=false) { feedback=text ? {text,info} : null; renderFeedback(); }
function renderFeedback() {
 $('feedback').hidden=!feedback;
 $('feedback').textContent=feedback?.text || '';
 $('feedback').className='feedback'+(feedback?.info?' info':'');
}
function setNumber(value) {
 number=String(value || '').slice(0,32);
 $('number').textContent=number;
 $('number').style.fontSize=number.length>16?'19px':number.length>12?'23px':'28px';
 $('number-label').hidden=!!number;
 $('number').scrollLeft=$('number').scrollWidth;
 if (!pending) showFeedback(null);
}
function current() { return calls.find(c=>c.id===selectedCall) || calls.find(c=>c.state==='ringing-in'||c.state==='waiting') || calls[0] || null; }
function incoming(c) { return c?.state==='ringing-in'||c?.state==='waiting'; }
function renderContacts() {
 const signature=JSON.stringify(contacts);
 if(signature===contactsSignature) return;
 contactsSignature=signature;
 const box=$('contacts'), oldFocus=document.activeElement?.dataset?.contact;
 box.textContent=''; $('contact-count').textContent=String(contacts.length);
 if(!contacts.length){const empty=document.createElement('div');empty.className='empty';empty.textContent=t('noContacts');box.append(empty);return;}
 for(const c of contacts){
  const row=document.createElement('div');row.className='contact';
  const pick=document.createElement('button');pick.className='contact-pick';pick.dataset.contact=c.number;
  const avatar=document.createElement('span');avatar.className='avatar';avatar.textContent=(c.name||c.number).slice(0,1);
  const text=document.createElement('span');text.className='contact-text';
  const name=document.createElement('strong');name.textContent=c.name||c.number;text.append(name);
  if(c.name){const small=document.createElement('small');small.textContent=c.number;text.append(small);}
  pick.append(avatar,text);pick.addEventListener('click',()=>{setNumber(c.number);$('dial').focus();});
  const remove=document.createElement('button');remove.className='contact-remove';remove.setAttribute('aria-label',t('delete')+' '+(c.name||c.number));
  remove.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M9 3h6m-8 4 1 13h8l1-13M10 10v7m4-7v7"/></svg>';
  remove.addEventListener('click',()=>{deleteNumber=c.number;$('delete-name').textContent=c.name?c.name+' · '+c.number:c.number;$('delete-sheet').hidden=false;$('delete-cancel').focus();});
  row.append(pick,remove);box.append(row);
 }
 if(oldFocus){const match=[...box.querySelectorAll('[data-contact]')].find(el=>el.dataset.contact===oldFocus);match?.focus();}
}
function render() {
 const c=current();
 if(toneCall!==c?.id){toneCall=c?.id;toneDigits='';tones=[];$('dtmf-digits').textContent='';dtmfOpen=false;}
 if(c?.state!=='active'){tones=[];dtmfOpen=false;}
 $('dtmf-toggle').hidden=c?.state!=='active';
 toggleKeypad(dtmfOpen);
 const choices=$('call-choices');choices.textContent='';choices.hidden=calls.length<2;
 for(const candidate of calls){const button=document.createElement('button');button.textContent=[candidate.sim,t(candidate.state)].filter(Boolean).join(' · ');button.setAttribute('aria-pressed',String(candidate.id===c?.id));button.addEventListener('click',()=>{selectedCall=candidate.id;render();});choices.append(button);}
 $('call-card').hidden=!c; $('dialer').hidden=!!c;
 $('contacts-panel').hidden=!!c;
 $('connection').textContent=c?t(c.state):pending?t('dialing'):t('idle');
 if(c){
  $('call-state').textContent=t(c.state);
  $('call-sim').textContent=c.sim || '';
  const contact=contacts.find(x=>x.number===c.number);
  $('call-name').textContent=contact?.name||c.number||t('phone');
  $('call-number').textContent=contact?.name?c.number:'';
  $('accept').hidden=!incoming(c);
  if(c.state==='active'){
   if(activeId!==c.id){activeId=c.id;activeSince=Date.now();}
  }else{activeId=null;activeSince=null;}
 }else{activeId=null;activeSince=null;}
 $('call-duration').textContent=activeSince?duration(Date.now()-activeSince):'';
 document.querySelectorAll('[data-sim]').forEach(button=>{button.setAttribute('aria-pressed',String(+button.dataset.sim===selectedCard));button.disabled=!!pending;});
 $('dial').disabled=!!pending||Date.now()<dialAfter||!!awaitingId;
 $('dial').querySelector('span').textContent=pending==='call'?t('dialing'):(Date.now()<dialAfter||awaitingId)?t('settling'):t('dial');
 $('hangup').disabled=!!pending; $('accept').disabled=!!pending;
 const differentAudio=audio.active && audio.sim && c?.sim && audio.sim!==c.sim;
 $('speaker').disabled=!!pending||!audio.available||differentAudio; $('mute').disabled=!!pending||!audio.available||differentAudio;
 $('speaker').setAttribute('aria-pressed',String(!!audio.speaker));
 const route=audio.route || (audio.speaker?'speaker':'receiver');
 $('speaker').textContent=t(audio.route_pending?'connectingAudio':route);
 $('speaker').setAttribute('aria-label',t('audioOutput')+' · '+t(route));
 $('bluetooth-name').textContent=audio.bluetooth?.connected?(audio.bluetooth.device||t('bluetooth')):t('btDisconnected');
 document.querySelectorAll('[data-route]').forEach(button=>{
  button.setAttribute('aria-pressed',String(button.dataset.route===route));
  button.disabled=!!pending||!audio.available||differentAudio||(button.dataset.route==='bluetooth'&&!audio.bluetooth?.connected);
 });
 if(!c)closeAudio();
 $('mute').setAttribute('aria-pressed',String(!!audio.muted));
 $('editor-save').disabled=!!pending; $('delete-confirm').disabled=!!pending;
 e5.keepAwake(!!c||!!pending);
 // Capture the lock key only while a call exists. At idle it keeps its normal
 // screen/lock behavior; input-device mappings are never changed here.
 e5.capturePower(!!c);
 renderFeedback(); renderContacts();
}
function duration(ms){const s=Math.floor(ms/1000);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
async function request(path,body){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
 try{
  const response=await fetch('/api/plugins/phone'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal,cache:'no-store'});
  const r=await response.json();
  if(!response.ok||r.ok!==true) throw new Error((r.stage?r.stage+': ':'')+(r.error||'HTTP '+response.status));
  return r;
 }catch(e){if(e.name==='AbortError')throw new Error(t('timedOut'));throw e;}finally{clearTimeout(timer);}
}
function applyLive(r){
  if(!r.error && Array.isArray(r.calls)) calls=r.calls.filter(c=>LIVE.has(c.state));
  if(r.audio){
   audio=r.audio;
   if(current()?.state==='active'&&(!audio.active||audio.error)){
    if(!feedback||audioFeedback){showFeedback(audio.error||t('audioWait'));audioFeedback=true;}
   }else if(audioFeedback){showFeedback(null);audioFeedback=false;}
  }
  if(r.error){if(!feedback)showFeedback(r.error);}
  if(awaitingId){
   if(calls.some(c=>c.id===awaitingId)){awaitingId=null;showFeedback(null);}
   else if(Date.now()-awaitingSince>6000){awaitingId=null;if(!feedback)showFeedback(t('noState'),true);}
  }
  render();
  if(r.error)$('connection').textContent=t('offline');
}
async function read(){
 if(reading)return;
 reading=true;
 const revision=liveRevision;
 try{
  const r=await e5.api('/status');
  if(!simPicked && (r.sim?.card===0 || r.sim?.card===1))selectedCard=r.sim.card;
  contacts=Array.isArray(r.contacts)?r.contacts:[];
  if(revision===liveRevision)applyLive(r);else render();
 }catch(e){if(!feedback)showFeedback(e.message);$('connection').textContent=t('offline');}
 finally{reading=false;}
}
async function perform(action,body){
 if(pending)return;
 if(action==='call'&&(Date.now()<dialAfter||awaitingId))return;
 if(action==='hangup')tones=[];
 pending=action;showFeedback(null);render();
 try{
  const r=await request('/'+action,body);
  if(action==='call'){awaitingId=String(r.id);awaitingSince=Date.now();}
  await read();
 }catch(e){showFeedback(e.message);}
 finally{if(action==='call'||action==='hangup')dialAfter=Date.now()+2000;pending=null;render();}
}
function dial(){
 if(pending||current()||Date.now()<dialAfter||awaitingId)return;
 if(!/^\+?[0-9*#]{3,32}$/.test(number)){showFeedback(t('invalid'));return;}
 perform('call',{number,card:selectedCard});
}
function openEditor(){
 if(!number){showFeedback(t('invalid'));return;}
 $('contact-name').value='';$('contact-number').value=number;$('editor').hidden=false;$('contact-name').focus();
}
function closeEditor(){$('editor').hidden=true;$('save-number').focus();}
async function saveContacts(next){
 if(pending)return false;
 pending='contacts';showFeedback(null);render();
 try{const r=await request('/contacts',{contacts:next});contacts=r.contacts;contactsSignature='';showFeedback(t('saved'),true);return true;}
 catch(e){showFeedback(e.message);return false;}
 finally{pending=null;render();}
}
$('contact-form').addEventListener('submit',async e=>{
 e.preventDefault();const n=$('contact-number').value.trim(),name=$('contact-name').value.trim();
 if(!/^\+?[0-9*#]{3,32}$/.test(n)){showFeedback(t('invalid'));return;}
 const next=[{name,number:n},...contacts.filter(c=>c.number!==n)];
 if(await saveContacts(next))closeEditor();
});
$('delete-cancel').addEventListener('click',()=>{$('delete-sheet').hidden=true;deleteNumber=null;});
$('delete-confirm').addEventListener('click',async()=>{
 if(await saveContacts(contacts.filter(c=>c.number!==deleteNumber))){$('delete-sheet').hidden=true;deleteNumber=null;}
});
function moveFocus(direction){
 const root=!$('audio-sheet').hidden?$('audio-sheet'):!$('editor').hidden?$('editor'):!$('delete-sheet').hidden?$('delete-sheet'):document.body;
 const items=[...root.querySelectorAll('button,input')].filter(el=>el.offsetParent!==null&&!el.disabled);
 if(!items.length)return;
 const current=document.activeElement;
 let next;
 if(!items.includes(current))next=items[0];
 else{
  const from=current.getBoundingClientRect(),horizontal=direction==='left'||direction==='right';
  const sign=direction==='left'||direction==='up'?-1:1;
  const cx=(from.left+from.right)/2,cy=(from.top+from.bottom)/2;
  let best=Infinity;
  for(const el of items){
   if(el===current)continue;
   const r=el.getBoundingClientRect(),dx=(r.left+r.right)/2-cx,dy=(r.top+r.bottom)/2-cy;
   const forward=(horizontal?dx:dy)*sign;
   // Stay in the same visible row/column; do not wrap to another keypad row.
   const aligned=horizontal?r.top<from.bottom-1&&r.bottom>from.top+1:r.left<from.right-1&&r.right>from.left+1;
   const distance=dx*dx+dy*dy;
   if(forward>1&&aligned&&distance<best){next=el;best=distance;}
  }
 }
 if(next){next.focus();next.scrollIntoView({block:'nearest'});}
}
function eraseInput(el){const a=el.selectionStart??el.value.length,b=el.selectionEnd??a;el.value=el.value.slice(0,Math.max(0,a-(a===b?1:0)))+el.value.slice(b);}
function insertInput(el,key){const a=el.selectionStart??el.value.length,b=el.selectionEnd??a;el.value=el.value.slice(0,a)+key+el.value.slice(b);el.setSelectionRange(a+key.length,a+key.length);}
function key(k){
 if(k.repeat&&k.kind!=='digit')return true;
 if(!$('audio-sheet').hidden){
  if(k.kind==='back'){closeAudio();return true;}
  if(k.kind==='ok'){if(document.activeElement?.tagName==='BUTTON')e5.press(document.activeElement);return true;}
  if(['up','down','left','right'].includes(k.kind)){moveFocus(k.kind);return true;}
  if(k.key!=='HangupPhone'&&k.kind!=='power')return true;
 }
 if(!$('editor').hidden&&document.activeElement?.tagName==='INPUT'){
  if(k.kind==='digit'){insertInput(document.activeElement,k.key);return true;}
  if(k.kind==='back'){if(document.activeElement.value)eraseInput(document.activeElement);else closeEditor();return true;}
 }
 if(!$('editor').hidden||!$('delete-sheet').hidden){
  if(k.kind==='back'){closeEditor();$('delete-sheet').hidden=true;return true;}
 }else{
  if(k.kind==='digit'){if(current()?.state==='active'){if(!k.repeat)sendTone(k.key);}else if(!current()&&!pending&&!callOnly)setNumber(number+k.key);return true;}
  if(k.kind==='call'||k.key==='Phone'||k.key==='PickupPhone'){
   const c=current();if(incoming(c))perform('answer',{id:c.id});else if(!c)dial();return true;
  }
  if(k.key==='HangupPhone'||k.kind==='power'){
   const c=current();if(c)perform('hangup',{id:c.id});return !!c;
  }
  if(k.kind==='back'&&dtmfOpen){toggleKeypad(false);return true;}
  if(k.kind==='back'&&callOnly)return true;
  if(k.kind==='back'&&number){setNumber(number.slice(0,-1));return true;}
 }
 if(k.kind==='ok'){
  const el=document.activeElement;if(el?.tagName==='BUTTON')e5.press(el);else moveFocus('down');return true;
 }
 if(['up','down','left','right'].includes(k.kind)){moveFocus(k.kind);return true;}
 return false;
}
document.querySelectorAll('[data-key]').forEach(b=>{
 b.addEventListener('click',()=>{if(b.dataset.key==='0'&&zeroHeld){zeroHeld=false;return;}if(!pending)setNumber(number+b.dataset.key);});
 if(b.dataset.key==='0'){
  b.addEventListener('pointerdown',()=>{zeroHeld=false;zeroTimer=setTimeout(()=>{if(!pending&&!number){setNumber('+');zeroHeld=true;}zeroTimer=null;},700);});
  b.addEventListener('pointerup',()=>{if(zeroTimer)clearTimeout(zeroTimer);});
  b.addEventListener('pointercancel',()=>clearTimeout(zeroTimer));
 }
});
document.querySelectorAll('[data-sim]').forEach(button=>button.addEventListener('click',()=>{if(!pending){selectedCard=+button.dataset.sim;simPicked=true;render();}}));
$('dial').addEventListener('click',dial);
$('accept').addEventListener('click',()=>{const c=current();if(incoming(c))perform('answer',{id:c.id});});
$('hangup').addEventListener('click',()=>{const c=current();if(c)perform('hangup',{id:c.id});});
function closeAudio(){
 if($('audio-sheet').hidden)return;
 $('audio-sheet').hidden=true;$('speaker').setAttribute('aria-expanded','false');$('speaker').focus();
}
$('speaker').addEventListener('click',()=>{
 if(!current())return;
 $('audio-sheet').hidden=false;$('speaker').setAttribute('aria-expanded','true');
 $('audio-sheet').querySelector('[data-route][aria-pressed="true"]')?.focus();
});
$('audio-close').addEventListener('click',closeAudio);
$('audio-sheet').addEventListener('click',e=>{if(e.target===$('audio-sheet'))closeAudio();});
document.querySelectorAll('[data-route]').forEach(button=>button.addEventListener('click',()=>{
 const route=button.dataset.route;closeAudio();if(current())perform('audio',{route});
}));
$('mute').addEventListener('click',()=>{if(current())perform('audio',{muted:!audio.muted});});
$('dtmf-toggle').addEventListener('click',()=>toggleKeypad(!dtmfOpen));
document.querySelectorAll('[data-tone]').forEach(button=>button.addEventListener('click',()=>sendTone(button.dataset.tone)));
$('save-number').addEventListener('click',openEditor);
$('backspace').addEventListener('click',()=>{if(!pending)setNumber(number.slice(0,-1));});
$('editor-close').addEventListener('click',closeEditor);
e5.onKey(key);
e5.onBack(()=>{if(!$('audio-sheet').hidden){closeAudio();return true;}if(number){setNumber(number.slice(0,-1));return true;}return false;});
e5.onLang(translate);
translate();read();
let unsubscribe=null, fallbackTimer=null;
if(window.parent!==window && window.parent.T551MCalls?.subscribe)
 unsubscribe=window.parent.T551MCalls.subscribe(data=>{liveRevision++;applyLive(data);});
else fallbackTimer=setInterval(read,350);
const clockTimer=setInterval(()=>{
 if(activeSince)$('call-duration').textContent=duration(Date.now()-activeSince);
 if(awaitingId && Date.now()-awaitingSince>6000){awaitingId=null;if(!feedback)showFeedback(t('noState'),true);render();}
 if(dialAfter && Date.now()>=dialAfter){dialAfter=0;render();}
},1000);
window.addEventListener('pagehide',()=>{unsubscribe?.();clearInterval(fallbackTimer);clearInterval(clockTimer);});

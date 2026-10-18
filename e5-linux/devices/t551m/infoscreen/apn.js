/* APN management uses the same public RPC as LuCI. No AT or password reads. */
const APN_TEXT = {
    title:['接入点 APN','Access points (APN)','Erişim noktaları (APN)'],
    add:['添加接入点','Add access point','Erişim noktası ekle'], edit:['编辑','Edit','Düzenle'],
    remove:['删除','Delete','Sil'], use:['切换','Use','Kullan'], active:['当前使用','Current','Etkin'],
    automatic:['自动匹配当前 SIM','Match current SIM automatically','Mevcut SIM için otomatik eşleştir'],
    refresh:['刷新','Refresh','Yenile'], name:['名称','Name','Ad'], protocol:['IP 协议','IP protocol','IP protokolü'],
    auth:['鉴权方式','Authentication','Kimlik doğrulama'], none:['无鉴权','None','Yok'],
    user:['用户名','Username','Kullanıcı adı'], password:['密码','Password','Parola'],
    keep:['留空保留原密码','Leave blank to keep saved password','Kayıtlı parolayı korumak için boş bırakın'],
    clear:['清除已保存密码','Clear saved password','Kayıtlı parolayı sil'],
    save:['保存','Save','Kaydet'], cancel:['取消','Cancel','İptal'], default:['SIM 默认','SIM default','SIM varsayılanı'],
    current:['当前配置','Current configuration','Mevcut yapılandırma'], empty:['暂无接入点，请添加','No access points; add one','Erişim noktası yok; bir tane ekleyin'],
    scope:['应用于当前上网卡，不切换 SIM。切换 APN 会短暂中断蜂窝连接。','Applies to the data SIM without switching SIMs. Changing APN briefly interrupts cellular data.','SIM değiştirmeden veri SIM’ine uygulanır. APN değişimi mobil bağlantıyı kısa süre keser.'],
    remembered:['已按当前 SIM 保存选择','Selection saved for this SIM','Seçim bu SIM için kaydedildi'],
    global:['正在使用全局接口配置','Using global interface configuration','Genel arayüz yapılandırması kullanılıyor'],
    save_note:['保存只更新列表；切换后才会应用。','Saving only updates the list; choose Use to apply.','Kaydetmek yalnızca listeyi günceller; uygulamak için Kullan’ı seçin.'],
    auto_note:['按运营商匹配公网 APN，未知运营商使用 SIM 默认。专网或物联卡请手动设置。','Matches public APNs by operator; unknown operators use SIM defaults. Configure private APNs manually.','Operatöre göre genel APN eşleştirilir; bilinmeyen operatörlerde SIM varsayılanı kullanılır. Özel APN’leri elle ayarlayın.'],
    auth_note:['当前固件暂不支持 APN 鉴权；可以保存配置，但不能应用需要鉴权的接入点。','This firmware cannot apply authenticated APNs yet. Such profiles can still be saved.','Bu yazılım henüz kimlik doğrulamalı APN’leri uygulayamıyor. Profiller yine de kaydedilebilir.'],
    apn_invalid:['接入点参数无效','Invalid access point settings','Geçersiz erişim noktası ayarları'],
    apn_missing:['接入点已不存在，请刷新','Access point no longer exists; refresh','Erişim noktası artık yok; yenileyin'],
    apn_identity:['无法读取当前 SIM 身份，请稍后刷新','Current SIM identity unavailable; refresh later','Mevcut SIM kimliği okunamıyor; daha sonra yenileyin'],
    apn_sim_changed:['上网卡已改变，请刷新后重新确认','Data SIM changed; refresh and confirm again','Veri SIM’i değişti; yenileyip yeniden onaylayın'],
    apn_unavailable:['APN 服务暂不可用，请重试','APN service unavailable; retry','APN hizmeti kullanılamıyor; tekrar deneyin'],
    apn_storage:['接入点保存失败','Could not save access point','Erişim noktası kaydedilemedi'],
    apn_auth_unsupported:['此固件暂不支持 APN 鉴权','APN authentication is unsupported by this firmware','Bu yazılım APN kimlik doğrulamasını desteklemiyor'],
    apn_reload:['配置已保存，但应用失败，请刷新后重试','Configuration saved, but applying failed; refresh and retry','Ayarlar kaydedildi ancak uygulanamadı; yenileyip tekrar deneyin'],
    apn_busy:['另一项网络操作仍在执行，请稍后重试','Another network operation is running; retry later','Başka bir ağ işlemi sürüyor; daha sonra tekrar deneyin'],
    apn_bound:['此接入点仍被 SIM 使用，不能删除','A SIM still uses this access point; cannot delete','Bir SIM bu erişim noktasını kullanıyor; silinemez'],
    apn_current:['请先切换，再删除当前接入点','Switch before deleting the current access point','Etkin erişim noktasını silmeden önce değiştirin'],
    apn_duplicate:['相同配置的接入点已存在','An access point with these settings already exists','Bu ayarlara sahip erişim noktası zaten var'],
    apn_limit:['最多保存 32 个接入点','Up to 32 access points can be saved','En fazla 32 erişim noktası kaydedilebilir'],
    apn_unsaved:['网络配置有未应用更改，请先保存或撤销','Save or discard pending network changes first','Önce bekleyen ağ değişikliklerini kaydedin veya iptal edin'],
    apn_scope:['当前 SIM 已保存选择，请按卡应用','This SIM has a saved selection; apply per SIM','Bu SIM’in kayıtlı seçimi var; SIM’e göre uygulayın'],
    apn_unsupported:['当前蜂窝接口不支持 APN 管理','Cellular interface does not support APN management','Mobil arayüz APN yönetimini desteklemiyor']
};
function apnText(key) { return (APN_TEXT[key] ?? APN_TEXT.apn_unavailable)[lang == 'en' ? 1 : lang == 'tr' ? 2 : 0]; }
function apnName(p) { return p.id == 'automatic' && p.name == 'SIM default' ? apnText('default') : p.name; }
function apnButton(action, label, disabled=false, active=false) {
    return `<button type="button" class="btn apn-button${active ? ' active' : ''}" data-st="${esc(action)}"${disabled ? ' disabled' : ''}>${esc(label)}</button>`;
}
function stAPNRender(v) {
    if (v.view == 'apnedit') {
        const p=v.draft, busy=!!v.parent.saving;
        const field=(key,label,type='text',max=64) => `<label class="apn-field"><span>${esc(label)}</span><input data-apn-field="${key}" type="${type}" maxlength="${max}" value="${esc(p[key] ?? '')}" autocomplete="${type=='password'?'new-password':'off'}" spellcheck="false"${key=='name'?' required':''}${key=='password' && v.has_password ? ` placeholder="${esc(apnText('keep'))}"` : ''}></label>`;
        const choices=(key,values) => `<div class="apn-field"><span>${esc(apnText(key=='pdptype'?'protocol':'auth'))}</span><div class="apn-choices" role="group">${values.map(([value,label])=>apnButton(`apnfield:${key}:${value}`,label,busy,p[key]==value)).join('')}</div></div>`;
        return `<form id="screen-apn-form" class="card apn-editor" onsubmit="return false"><fieldset${busy?' disabled':''}>`+
            field('name',apnText('name'))+field('apn','APN','text',100)+
            choices('pdptype',[['IPV4V6','IPv4 / IPv6'],['IP','IPv4']])+
            choices('auth',[['none',apnText('none')],['pap','PAP'],['chap','CHAP'],['papchap','PAP / CHAP']])+
            field('username',apnText('user'))+field('password',apnText('password'),'password')+
            (v.has_password ? `<label class="apn-clear"><input type="checkbox" data-apn-field="clear_password"${p.clear_password?' checked':''}><span>${esc(apnText('clear'))}</span></label>` : '')+
            `<p class="stnote">${esc(apnText('save_note'))}</p><div class="apn-actions">`+
            apnButton('apn:save',apnText('save'),busy)+apnButton('apn:cancel',apnText('cancel'),busy)+`</div></fieldset></form>`;
    }
    const data=v.apn, busy=!!v.saving || !!v.loading;
    let html=`<div class="apn-actions">${apnButton('apn:refresh',apnText('refresh'),busy)}${apnButton('apn:add',apnText('add'),busy || !data?.ok)}</div>`;
    if (v.error) html+=`<p class="stnote apn-error" role="alert">${esc(apnText(v.error))}</p>`;
    if (!data?.ok) return html;
    const ready=data.identity_ready && [0,1].includes(data.data_sim);
    html+=`<div class="card apn-summary"><strong>SIM ${data.data_sim==null?'—':data.data_sim+1}</strong><span>${esc(apnText('current'))}</span><b>${esc(data.current?.apn || apnText('default'))}</b><span>${esc(data.current?.pdptype=='IP'?'IPv4':'IPv4 / IPv6')}</span><p class="stnote">${esc(apnText(data.remembered?'remembered':'global'))}</p></div>`+
        apnButton('apn:auto',apnText('automatic'),busy || !ready)+`<p class="stnote">${esc(apnText('scope'))}</p>`;
    if (!ready) html+=`<p class="stnote">${esc(apnText('apn_identity'))}</p>`;
    if (!data.auth_supported) html+=`<p class="stnote">${esc(apnText('auth_note'))}</p>`;
    if (!data.profiles?.length) html+=`<p class="stnote">${esc(apnText('empty'))}</p>`;
    for (const [i,p] of (data.profiles ?? []).entries()) {
        const unsupported=!data.auth_supported && p.auth && p.auth!='none';
        html+=`<article class="card apn-profile${p.current?' current':''}"><div class="apn-profile-head"><strong>${esc(apnName(p))}</strong>${p.current?`<span class="apn-badge">${esc(apnText('active'))}</span>`:''}</div><div class="apn-value">${esc(p.apn || apnText('default'))}</div><div class="sub">${p.pdptype=='IP'?'IPv4':'IPv4 / IPv6'} · ${esc(p.auth && p.auth!='none'?p.auth.toUpperCase():apnText('none'))}</div><div class="apn-actions">`+
            apnButton(`apn:use:${i}`,apnText('use'),busy || !ready || unsupported)+
            apnButton(`apn:edit:${i}`,apnText('edit'),busy)+
            apnButton(`apn:delete:${i}`,apnText('remove'),busy || p.current)+`</div></article>`;
    }
    return html;
}
function stAPNBind(v) {
    $('screen-apn-form')?.addEventListener('input', e => {
        const key=e.target.dataset.apnField;
        if (key) v.draft[key]=e.target.type=='checkbox'?e.target.checked:e.target.value;
    });
}
async function stAPNLoad(v) {
    if (v.loading || v.saving) return;
    v.loading=true;
    if (stTop()===v) stRender();
    try {
        const data=await pageRead('/api/apn',P.settings);
        if (data?.ok) {v.apn=data;v.error=null;v.observedSlot ??= data.data_sim;}
        else v.error=data?.error || 'apn_unavailable';
    } catch(e) {v.error='apn_unavailable';}
    finally {v.loading=false;if (stTop()===v) stRender();}
}
function stAPNSync(status) {
    const v=stTop(), raw=status?.modem?.sim_card;
    if (raw==null || raw==='') return;
    const slot=Number(raw);
    if (page===P.settings && !blank && v?.view=='apn' && v.apn &&
        [0,1].includes(slot) && v.observedSlot!==slot && !v.saving && !v.loading) {
        v.observedSlot=slot;stAPNLoad(v);
    }
}
async function stAPNChange(v,action,payload) {
    if (v.saving || v.loading) return null;
    v.saving=true;stDisarm();stRender();
    const done=beginPageLoad(P.settings);
    let r;
    try {
        r=await fetch('/api/apn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,payload})}).then(r=>r.json());
        toast(r?.ok ? t('saved') : apnText(r?.error || 'apn_unavailable'));
    } catch(e) {r={ok:false,error:'apn_unavailable'};toast(apnText(r.error));}
    finally {v.saving=false;done(!r?.ok);}
    if (r?.ok || r?.saved || r?.error=='apn_sim_changed') await stAPNLoad(v);
    return r;
}
async function stAPNClick(v,key,el) {
    const [kind,action,index]=key.split(':');
    if (v.saving || v.parent?.saving || v.loading) return;
    if (kind=='apnfield' && v.view=='apnedit') {
        if (action=='pdptype' && ['IP','IPV4V6'].includes(index) || action=='auth' && ['none','pap','chap','papchap'].includes(index)) {
            v.draft[action]=index;stRender();
        }
        return;
    }
    if (kind!='apn') return;
    if (action=='cancel') {stDisarm();st.pop();stRender();return;}
    if (action=='refresh') {stDisarm();await stAPNLoad(v);return;}
    if (action=='save' && v.view=='apnedit') {
        if (!$('screen-apn-form')?.reportValidity() || !v.draft.name.trim()) return;
        const p=v.draft, payload={id:p.id,name:p.name.trim(),apn:p.apn.trim(),pdptype:p.pdptype,auth:p.auth,username:p.username,roaming:p.pdptype,attach:'0'};
        if (p.clear_password || p.password || !v.has_password) payload.password=p.clear_password?'':p.password;
        const r=await stAPNChange(v.parent,'save',payload);
        if (r?.ok && stTop()===v) st.pop();
        stRender();return;
    }
    if (v.view!='apn') return;
    const p=v.apn?.profiles?.[+index];
    if (action=='add' || action=='edit') {
        if (!v.apn?.ok || action=='edit' && !p) return;
        stDisarm();
        st.push({view:'apnedit',item:{label:apnText(action=='add'?'add':'edit')},parent:v,has_password:!!p?.has_password,
            draft:{id:p?.id || '',name:p?.name || '',apn:p?.apn || '',pdptype:p?.pdptype || 'IPV4V6',auth:p?.auth || 'none',username:p?.username || '',password:'',clear_password:false}});
        stRender();return;
    }
    if (!['auto','use','delete'].includes(action) || action!='auto' && !p) return;
    if (!stConfirm(key,el)) return;
    if (action=='delete') {await stAPNChange(v,'delete',{id:p.id});}
    else {
        if (!v.apn.identity_ready || ![0,1].includes(v.apn.data_sim)) {toast(apnText('apn_identity'));return;}
        await stAPNChange(v,action=='auto'?'auto':'apply',{...(p?{id:p.id}:{}),remember:true,data_sim:v.apn.data_sim});
    }
    if (stTop()===v) stRender();
}

import {orderStats,recordedIncidents,target,telemetryState} from '../domain.mjs';
import {badge,clock,date,empty,esc,icon,number,duration} from '../lib/ui.mjs';

const orderLink=id=>`<button class="row-link" data-action="order-detail" data-id="${esc(id)}">${esc(id)}</button>`;

function cameraStatus(state){
 const labels={
  demo:['Örnek çalışma','gray'],disabled:['Kamera takibi kapalı','gray'],
  disconnected:['MQTT bağlantısı yok','amber'],unreported:['Kamera verisi bekleniyor','amber'],
  fresh:['Kamera verisi güncel','teal'],stale:['Kamera verisi güncel değil','amber'],
 };
 return labels[telemetryState(state.meta,state.meta.telemetry?.lastVisionAt)];
}

function incidentList(state,open,canOperate){
 return open.map(alert=>{
  const station=state.stations.find(s=>s.id===alert.station);
  const knownOrder=state.orders.some(o=>o.id===alert.orderId);
  const tone=alert.kind==='fault'?'red':'amber';
  return `<article class="alert-item">
   <span class="alert-symbol">${icon(alert.kind==='material'?'box':'alert')}</span>
   <div><strong>${esc(alert.title)}</strong><p>${esc(alert.reason||'Açıklama kaydı yok')}</p>
   <small>${esc(station?.name||alert.station||'Hat geneli')} · ${clock(alert.at)}</small>
   <div class="inline-actions">${knownOrder?orderLink(alert.orderId):'<small>İş emri bağlantısı yok</small>'}
    ${badge('Açık · '+duration(state.meta.serverNow-alert.at),tone)}
    ${canOperate&&alert.kind==='material'?`<button class="text-link" data-action="restock" data-color="${esc(alert.color)}">Malzeme geldi ${icon('check')}</button>`:''}
   </div></div></article>`;
 }).join('')||empty('Açık bildirim yok','Yeni istasyon ve malzeme bildirimleri burada görünür.');
}

function priorities(state,canOperate){
 const current=state.instruction;
 const pending=state.orders.filter(o=>!o.closedAt&&o.id!==state.activeOrder&&orderStats(state,o.id).prepared<target(o));
 const queue=state.orders.filter(o=>!o.closedAt);
 return `<section class="card"><div class="card-heading"><div><h2>İş emri önceliği</h2>
 <p>Aktif bantlama emri <strong>${esc(state.activeOrder||'Yok')}</strong></p></div>${icon('orders')}</div>
 <div class="card-body">${current?`<div class="instruction-status">
  ${badge(current.acknowledgedAt?'Onaylandı · geçiş bekleniyor':'Operatör onayı bekleniyor','amber')}
  <h3>${orderLink(current.orderId)}</h3><p>${current.mode==='immediate'?'Eldeki kutudan sonra geç':'Mevcut iş emrini bitir, sonra geç'}</p>
  ${canOperate?'<button class="button" data-action="cancel-instruction">Talimatı iptal et</button>':''}</div>`
 :canOperate?`<form id="priority-form"><label>Geçilecek iş emri<select name="orderId" required>
  ${pending.map(o=>`<option value="${esc(o.id)}">${esc(o.id)} · ${esc(o.customer)}${o.priority==='urgent'?' · Acil':''}</option>`).join('')}</select></label>
  <label>Geçiş zamanı<select name="mode"><option value="immediate">Hemen — eldeki kutudan sonra</option><option value="after-order">Mevcut iş emri bitince</option></select></label>
  <p class="form-hint">Konveyör çalışmaya devam eder. Operatörden “Tamam” onayı alınır.</p>
  <button class="button primary full" ${pending.length?'':'disabled'}>Talimatı operatöre gönder</button></form>`
 :'<p class="muted">Bekleyen geçiş talimatı yok.</p>'}</div>
 <div class="subsection"><h3>Açık iş emirleri</h3>
  ${queue.map((o,i)=>`<div class="history-line">${orderLink(o.id)}<span>${esc(o.customer)}</span>
   ${o.priority==='urgent'?badge('Acil','amber'):''}${canOperate&&i>0?`<button class="button" data-action="order-up" data-id="${esc(o.id)}" aria-label="${esc(o.id)} emrini sırada öne al">Öne al</button>`:''}</div>`).join('')||'<p class="muted">Açık emir yok.</p>'}
 </div>
 <div class="subsection"><h3>Son talimatlar</h3>
 ${state.instructionHistory.slice(0,3).map(entry=>`<div class="history-line">${orderLink(entry.orderId)}
 ${badge(entry.cancelledAt?'İptal edildi':'Uygulandı',entry.cancelledAt?'gray':'green')}<small>${clock(entry.appliedAt||entry.cancelledAt)}</small></div>`).join('')||'<p class="muted">Henüz geçmiş talimat yok.</p>'}
 </div></section>`;
}

function productionPlanning(planning,canOperate){
 if(!planning)return '';
 const today=planning.days[planning.today]||{};
 const rows=(orders,pending)=>orders.map(row=>`<tr>
 <td>${orderLink(row.id)}</td><td>${row.day?date(Date.parse(row.day+'T12:00:00+03:00')):'Planlanmadı'}</td>
 <td>${number(row.remaining)} kutu</td>
 ${canOperate?`<td><button class="button" data-action="plan-order" data-id="${esc(row.id)}">${pending?'Güne planla':'Günü değiştir'}</button></td>`:''}
 </tr>`).join('')||`<tr><td colspan="${canOperate?4:3}">İş emri yok.</td></tr>`;
 const table=(orders,pending)=>`<div class="table-wrap"><table><thead><tr><th>İş emri</th><th>${pending?'Son planlanan gün':'Planlanan gün'}</th><th>Kalan sağlam kutu</th>${canOperate?'<th>İşlem</th>':''}</tr></thead><tbody>${rows(orders,pending)}</tbody></table></div>`;
 return `<section class="card section-gap"><div class="card-heading"><div><h2>Günlük üretim planı</h2>
 <p>Bugünün otomatik hedefi ${today.automatic==null?'—':number(today.automatic)+' kutu'} · Mühendis hedefi ${today.manual==null?'—':number(today.manual)+' kutu'}</p></div>
 ${canOperate?'<div class="heading-actions"><button class="button" data-action="daily-target-manual">Hedef gir</button><button class="button" data-action="daily-target-auto">Otomatik hesaba dön</button></div>':''}</div>
 <div class="subsection"><h3>Planlama bekliyor</h3><p class="form-hint">Günü geçip kalan kutular ve henüz gün atanmayan emirler.</p>${table(planning.pending,true)}</div>
 <div class="subsection"><h3>Planlanan açık iş emirleri</h3>${table(planning.planned,false)}</div>
 </section>`;
}

export function render({state}){
 const canOperate=state.meta.workspace==='engineer'&&!state.meta.readOnly;
 const open=recordedIncidents(state.alerts);
 const deviations=state.activities.filter(a=>a.minutes>a.expected);
 const [camera,tone]=cameraStatus(state);
 const visionAt=state.meta.telemetry?.lastVisionAt;
 return `<div class="page-heading"><div><div class="eyebrow">ÖNCELİKLER VE MÜDAHALELER</div><h1>Mühendis paneli</h1>
 <p>Açık arızalar, etkilenen iş emirleri ve operatör açıklamaları.</p></div>
 ${canOperate?badge('Mühendis çalışma alanı','teal'):badge('Yalnız görüntüleme','blue')}</div>
 ${!canOperate?`<div class="observer-notice">${icon('info')}<div><strong>Salt okunur izleme</strong><span>Talimat, öncelik ve malzeme işlemleri mühendis hesabıyla /muhendis adresinde yapılır.</span></div></div>`:''}
 <div class="engineer-metrics">
  <div class="compact-metric">${icon('alert')}<div><strong>${open.filter(a=>a.kind==='fault').length}</strong><span>Açık arıza bildirimi</span></div></div>
  <div class="compact-metric">${icon('time')}<div><strong>${duration(state.meta.performance.stopped)}</strong><span>Vardiyada kaydedilen hat duruşu</span></div></div>
  <div class="compact-metric">${icon('bell')}<div><strong>${open.length}</strong><span>Açık bildirim</span></div></div>
 </div>
 <div class="two-col"><section class="card"><div class="card-heading"><div><h2>Müdahale listesi</h2>
 <p>Açık kalma süresi her bildirimin kendi kaydına göre gösterilir.</p></div><span class="count-pill">${open.length}</span></div>
 <div class="alert-list">${incidentList(state,open,canOperate)}</div>
 <div class="subsection"><h3>Kamera bağlantısı</h3>${badge(camera,tone)}
 <p class="form-hint">${visionAt?`Son veri ${clock(visionAt)} · `:''}Bağlantı durumu ayrı izlenir ve hat duruşu süresine eklenmez.</p></div></section>
 ${priorities(state,canOperate)}</div>
 ${productionPlanning(state.meta.planning,canOperate)}
 <section class="card section-gap"><div class="card-heading"><div><h2>Faaliyet süre aşımı geçmişi</h2>
 <p>Standart süreyi aşan faaliyetler ve operatör açıklamaları.</p></div>${icon('chart')}</div>
 <div class="table-wrap"><table><thead><tr><th>Faaliyet</th><th>Standart</th><th>Gerçekleşen</th><th>Fark</th><th>Operatör açıklaması</th></tr></thead>
 <tbody>${deviations.map(a=>`<tr><td><strong>${esc(a.name)}</strong><small>${date(a.startedAt)}</small></td>
 <td>${number(a.expected)} dk</td><td>${number(a.minutes)} dk</td><td>${badge('+'+number(a.minutes-a.expected)+' dk','amber')}</td>
 <td class="wrap-cell">${esc(a.reason||'Açıklama kaydı yok')}</td></tr>`).join('')||'<tr><td colspan="5">Süre aşımı kaydı yok.</td></tr>'}</tbody></table></div></section>`;
}

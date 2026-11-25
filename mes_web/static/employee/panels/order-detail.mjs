import {elapsedBetween,orderStats,orderTimeline} from '../domain.mjs';
import {clock,colorLabel,date,esc,duration} from '../lib/ui.mjs';

const timestamp=at=>Number.isFinite(at)?`${date(at)} · ${clock(at)}`:'Kayıt yok';
const elapsed=ms=>ms===null?'—':duration(ms);
const stages={transit:'Konveyörde',exited:'Çıkışı doğrulandı',packed:'Paketlendi',scrap:'Hurda',rework:'Yeniden işlem'};

export function renderOrderDetail(state,order){
 const stats=orderStats(state,order.id);
 const timeline=orderTimeline(state,order);
 const metrics=[
  ['Hedef',stats.target],['Sağlam çıkış',stats.good],['Konveyörde',stats.transit],
  ['Paketlenen',stats.packed],['Yeniden işlem',stats.rework],['Hurda',stats.scrap],
 ];
 return `<p>${esc(order.customer)}</p>
 <div class="detail-field-grid">${metrics.map(([label,value])=>`<div class="detail-field"><span>${label}</span><strong>${esc(value)}</strong></div>`).join('')}</div>
 <section class="timeline-section">
 <h3>İş emri zaman çizelgesi</h3>
 <p>${order.closedAt?'Emrin gelişinden kapanışına':'Emrin gelişinden şu ana'} kadar geçen süre <strong>${elapsed(timeline.total)}</strong></p>
 <ol class="order-timeline">${timeline.milestones.map(step=>`<li><div><strong>${step.label}</strong><span>${timestamp(step.at)}</span></div><span class="mono">${elapsed(step.elapsed)}</span></li>`).join('')}</ol>
 <p class="form-hint">Sağdaki süre iki ardışık kayıt arasındaki farkı gösterir. Kutu bazındaki taşıma ve bekleme süreleri aşağıdadır.</p>
 </section>
 <section class="timeline-section">
 <h3>Beklemeler ve bildirimler</h3>
 ${timeline.waits.length?`<ul class="order-timeline">${timeline.waits.map(wait=>`<li><div><strong>${esc(wait.label)}</strong><span>${timestamp(wait.at)} · ${wait.end?'Sonlandı':'Açık'}</span><span>${esc(wait.reason||'Açıklama kaydı yok')}</span>${wait.resolvedBy?`<span>Çözen: ${esc(wait.resolvedBy)}</span>`:''}</div><span class="mono">${elapsed(wait.elapsed)}</span></li>`).join('')}</ul>`:'<p class="muted">Bu iş emrine bağlı bekleme veya bildirim kaydı yok.</p>'}
 </section>
 <details class="timeline-section"><summary>Kutu bazında aşamalar ve süreler (${timeline.boxes.length})</summary>
 <div class="table-wrap"><table><thead><tr><th>Kutu</th><th>Aşama</th><th>Bantlama çalışanı</th><th>Bantlama başlangıcı</th><th>Konveyöre teslim</th><th>Doğrulanan çıkış</th><th>Paketleme çalışanı</th><th>Paketlendi</th><th>Konveyör süresi</th><th>Paketleme beklemesi</th></tr></thead>
 <tbody>${timeline.boxes.map(box=>`<tr><td>${esc(box.id)} ${colorLabel(box.color)}</td><td>${stages[box.stage]||'Bantlamada'}</td><td>${esc(box.operator||'—')}</td><td>${timestamp(box.startedAt)}</td><td>${timestamp(box.deliveredAt)}</td><td>${timestamp(box.exitedAt)}</td><td>${esc(box.packedBy||'—')}</td><td>${timestamp(box.packedAt)}</td><td>${elapsed(elapsedBetween(box.deliveredAt,box.exitedAt))}</td><td>${elapsed(elapsedBetween(box.exitedAt,box.packedAt))}</td></tr>`).join('')||'<tr><td colspan="10">Henüz kutu kaydı yok.</td></tr>'}</tbody></table></div>
 </details>`;
}

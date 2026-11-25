import {taping} from './shared-stations.mjs';
import {badge, esc} from '../lib/ui.mjs';
import {stationShift} from './station-shift.mjs';

export function render(context){
 const {state,ui}=context;
 const showAdvance=state.meta.workspace==='taping'&&!state.meta.readOnly&&!context.readOnly;
 const notice=state.activeBox?.handoverRequired?'<div class="observer-notice"><div><strong>Bu kutu operatör devrini bekliyor</strong><span>Kutu ve tamamlanan adımlar korunur.</span></div><button class="button primary" data-action="claim-box">Bu kutuyu devral</button></div>':'';
 return `<div class="page-heading"><div><div class="eyebrow">BNT-01 · OPERATÖR ÇALIŞMA ALANI</div><h1>Bantlama istasyonu</h1><p>${esc(state.stations.find(station=>station.id==='BNT-01')?.device||'')}</p></div></div>
 ${stationShift(context,'taping','Bantlama',notice+renderHandoff(state)+taping(state,ui,showAdvance))}`;
}

function renderHandoff(state) {
 const handoff = state.handoff;
 if (!handoff || state.mode === 'demo') return '';
 const labels = {
  waiting_entry: ['Giriş bekleniyor', 'Fiziksel hattın girişinde kutunun algılanması bekleniyor.'],
  confirm_entry: ['Onay bekleniyor', 'Eşleştirmeyi kaydetmeden önce konveyöre verdiğin fiziksel kutuyu algılanan kutuyla karşılaştır.'],
  needs_review: ['İnceleme gerekiyor', 'Algılama güvenle eşleştirilemedi. Kutu ve ölçüm kaydını kontrol et.'],
 };
 const label = labels[handoff.status];
 if (!label) return '';
 const candidate = handoff.candidate;
 return `<section class="card section-gap employee-handoff" aria-label="Fiziksel kutu eşleştirmesi"><div class="card-heading">
  <h2>Fiziksel kutu eşleştirmesi</h2>${badge(label[0], 'amber')}</div>
  <div class="card-body"><p>${label[1]}</p>
  ${candidate?.item_id ? `<p><strong>Algılanan kutu:</strong> ${esc(candidate.item_id)}</p>` : ''}
  <div class="inline-actions">${handoff.status === 'confirm_entry' && candidate?.item_id && candidate?.measure_id
   ? `<button class="button primary" data-action="handoff-confirm" data-id="${esc(handoff.id)}" data-item-id="${esc(candidate.item_id)}" data-measure-id="${esc(candidate.measure_id)}">Aynı kutu, eşleştir</button>` : ''}
  <button class="button" data-action="handoff-close" data-id="${esc(handoff.id)}">Doğrulamadan kapat</button></div></div></section>`;
}

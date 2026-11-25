import {badge,clock,esc} from '../lib/ui.mjs';

export function stationShift({state,readOnly},workspace,label,content){
 const shift=(workspace==='taping'?state.shift:state.meta.stationShift??state.stationShifts?.[workspace])||{};
 const canOperate=state.meta.workspace===workspace&&!state.meta.readOnly&&!readOnly;
 const named=shift.active&&shift.operatorAccountId;
 const busy=workspace==='taping'&&Boolean(state.activeBox||state.activity);
 const canTransfer=busy&&state.meta.actor?.pairedTablet&&state.activeBox?.handoverRequired&&!state.activity;
 const startDisabled=busy&&!canTransfer;
 const status=shift.active&&shift.operator?`Çalışan: ${esc(shift.operator)}${Number.isFinite(shift.startedAt)?` · Başlangıç: ${clock(shift.startedAt)}`:''}`:'Vardiya başlatılmadı';
 const blocked=canOperate&&!named&&!busy;
 return `<section class="card taping-shift" aria-label="${esc(label)} vardiyası">
  <div>${badge(shift.active?'Vardiya açık':'Vardiya kapalı',shift.active?'teal':'gray')}<p>${status}</p>${canOperate&&busy&&!canTransfer?'<p class="muted">Vardiya değişiminden önce açık kutuyu veya faaliyeti bitir.</p>':''}</div>
  ${canOperate&&!named?`<form id="station-shift-form"><label>Ad soyad<input name="operator" type="text" maxlength="80" autocomplete="name" required ${startDisabled?'disabled':''}></label><button class="button primary" ${startDisabled?'disabled':''}>Vardiyayı başlat</button></form>`:''}
  ${canOperate&&shift.active?`<button class="button" data-action="end-station-shift" ${busy?'disabled':''}>Vardiyayı bitir</button>`:''}
 </section><fieldset class="station-work" ${blocked?'disabled':''}>${content}</fieldset>`;
}

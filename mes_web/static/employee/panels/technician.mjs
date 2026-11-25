import {esc,badge,clock,empty} from '../lib/ui.mjs';
import {stationShift} from './station-shift.mjs';

export const render=context=>stationShift(context,'technician','Tekniker',renderFaults(context));
function renderFaults({state:s}){const rows=s.alerts.filter(a=>a.kind==='fault');return `<div class="page-heading"><div><div class="eyebrow">BAKIM VE ARIZA</div><h1>Tekniker paneli</h1><p>İstasyondan gelen açıklamalar ve devam eden duruşlar.</p></div></div><section class="card"><div class="card-heading"><h2>Arıza kayıtları</h2></div><div class="card-body">${rows.map(a=>`<article class="alert-item"><div><strong>${esc(a.station||'Hat')} · ${esc(a.title)}</strong><p>${esc(a.reason)}</p><small>${clock(a.at)}</small>${badge(a.resolved?'Çözüldü':'Açık',a.resolved?'green':'red')}${a.resolved?'':`<button class="button" data-action="resolve" data-id="${esc(a.id)}">Çözüldü</button>`}</div></article>`).join('')||empty('Açık arıza yok','Operatör bildirimleri burada listelenir.')}</div></section>`;}

export const COLORS={yellow:'Sarı',blue:'Mavi',red:'Kırmızı'};
export const STEPS=['Kutuyu al','Tezgâha yerleştir','Üstünü bantla','Etrafını tek seferde bantla','Kontrol et'];
const sum=values=>values.reduce((a,b)=>a+b,0);
export const target=o=>sum(Object.values(o.requirements));

export function newOrderAction(fields){
 const id=fields.id.trim();
 const customer=fields.customer.trim();
 if(!/^[A-Za-z0-9_-]{1,40}$/.test(id))throw Error('İş emri kodunu boşluksuz yaz. Örnek DENEME-1.');
 if(!customer)throw Error('Müşteri adını yaz.');
 const requirements=Object.fromEntries(Object.keys(COLORS).map(color=>[color,Number(fields[color])]));
 const quantities=Object.values(requirements);
 if(quantities.some(value=>!Number.isInteger(value)||value<0||value>10000))throw Error('Kutu adetlerini 0 ile 10.000 arasında tam sayı olarak gir.');
 if(!quantities.some(value=>value>0))throw Error('En az bir renk için 1 veya daha fazla kutu gir.');
 return {type:'order-create',id,customer,priority:fields.priority,requirements};
}
export function orderStats(s,id){
 const o=s.orders.find(o=>o.id===id);if(!o)throw new Error('İş emri bulunamadı.');
 const items=s.items.filter(i=>i.orderId===id);
 const byColor=Object.fromEntries(Object.keys(COLORS).map(color=>{const rows=items.filter(i=>i.color===color);return [color,{target:o.requirements[color]||0,good:rows.filter(i=>i.quality==='good'&&['exited','packed'].includes(i.stage)).length,prepared:rows.filter(i=>i.quality==='good').length,packed:rows.filter(i=>i.stage==='packed').length,transit:rows.filter(i=>i.stage==='transit').length,reserved:rows.filter(i=>i.quality==='good').length+(s.activeBox?.orderId===id&&s.activeBox.color===color?1:0)}];}));
 return {target:target(o),good:sum(Object.values(byColor).map(v=>v.good)),prepared:sum(Object.values(byColor).map(v=>v.prepared)),packed:sum(Object.values(byColor).map(v=>v.packed)),transit:sum(Object.values(byColor).map(v=>v.transit)),scrap:items.filter(i=>i.quality==='scrap').length,rework:items.filter(i=>i.quality==='rework').length,byColor};
}
export function remaining(s,id,color){const row=orderStats(s,id).byColor[color];if(!row)throw new Error('Bant rengi geçersiz.');return Math.max(0,row.target-row.reserved);}
export function orderStatus(s,id){
 const o=s.orders.find(o=>o.id===id),v=orderStats(s,id);
 if(o.closedAt)return {label:'Tamamlandı',tone:'green'};
 if(Object.keys(COLORS).some(c=>remaining(s,id,c)>0&&s.tape[c]==='empty'))return {label:'Malzeme bekliyor',tone:'amber'};
 if(v.packed===v.target)return {label:'Koli onayı bekliyor',tone:'teal'};
 if(v.prepared>=v.target)return {label:'Paketleniyor',tone:'teal'};
 if(s.activeOrder===id)return {label:'Üretimde',tone:'blue'};
 return {label:v.prepared?'Devam bekliyor':'Sırada',tone:'gray'};
}

export const elapsedBetween=(start,end)=>Number.isFinite(start)&&Number.isFinite(end)&&end>=start?end-start:null;

export function telemetryState(meta,lastAt){
 if(meta.mode==='demo')return 'demo';
 if(!meta.connection?.enabled)return 'disabled';
 if(!meta.brokerConnected)return 'disconnected';
 const age=elapsedBetween(lastAt,meta.serverNow);
 return age===null?'unreported':age<20000?'fresh':'stale';
}

export function recordedIncidents(alerts){
 const priority=alert=>alert.kind==='fault'?0:alert.kind==='material'?(alert.level==='empty'?1:2):3;
 return alerts.filter(alert=>!alert.resolved).sort((a,b)=>priority(a)-priority(b)
  ||(a.at??Infinity)-(b.at??Infinity));
}

export function orderTimeline(state,order){
 const items=state.items.filter(item=>item.orderId===order.id);
 const active=state.activeBox?.orderId===order.id?state.activeBox:null;
 const boxes=active?[...items,active]:items;
 const first=key=>boxes.reduce((at,box)=>Number.isFinite(box[key])&&(at===undefined||box[key]<at)?box[key]:at,undefined);
 const stages=[
  ['Emir geldi',order.createdAt],['İlk bantlama başladı',first('startedAt')],
  ['İlk konveyöre teslim',first('deliveredAt')],['İlk doğrulanan hat çıkışı',first('exitedAt')],
  ['İlk kutu paketlendi',first('packedAt')],['Koli kapandı',order.closedAt],
 ];
 const now=state.meta.serverNow;
 const waits=state.alerts.filter(alert=>alert.orderId===order.id).map(alert=>({
  label:alert.title,at:alert.at,end:alert.resolvedAt,reason:alert.reason,resolvedBy:alert.resolvedBy,
 }));
 for(const box of boxes){
  for(const pause of box.pauseHistory||[])waits.push({...pause,label:'Kutu duraklaması · '+box.id});
 }
 if(active?.paused&&!active.pauseHistory?.length)waits.push({
  label:'Kutu duraklaması',at:active.since,reason:active.pauseReason,
 });
 for(const pause of order.parkHistory||[])waits.push({...pause,label:'Ayrılan koli'});
 if(order.parkedAt)waits.push({label:'Ayrılan koli',at:order.parkedAt,reason:order.parkReason});
 return {
  boxes,
  milestones:stages.map(([label,at],index)=>({label,at,elapsed:elapsedBetween(stages[index-1]?.[1],at)})),
  total:elapsedBetween(order.createdAt,order.closedAt??now),
  waits:waits.sort((a,b)=>a.at-b.at).map(wait=>({...wait,elapsed:elapsedBetween(wait.at,wait.end??now)})),
 };
}

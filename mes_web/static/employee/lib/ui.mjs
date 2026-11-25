export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const number=n=>new Intl.NumberFormat('tr-TR',{maximumFractionDigits:1}).format(n||0);
export const clock=t=>t===null||t===undefined?'—':new Date(t).toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit',second:'2-digit',timeZone:'Europe/Istanbul'});
export const shortClock=t=>t===null||t===undefined?'—':new Date(t).toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/Istanbul'});
export const date=t=>new Date(t).toLocaleDateString('tr-TR',{day:'2-digit',month:'long',year:'numeric',timeZone:'Europe/Istanbul'});
export const dateKey=t=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'Europe/Istanbul'}).format(new Date(t));
export const duration=ms=>{const s=Math.floor(Math.max(0,ms)/1000);return [Math.floor(s/3600),Math.floor(s/60)%60,s%60].map(n=>String(n).padStart(2,'0')).join(':');};
const paths={grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',orders:'M8 4h12v17H4V4h4M9 2h6v4H9zM8 11h8M8 15h5',engineer:'m14 6 4-4 4 4-4 4M16 8l-5 5M10 14l-5 7-3-3 7-5M3 3l5 1 2 4-2 2-4-2z',box:'m12 3 9 5v9l-9 5-9-5V8zM3 8l9 5 9-5M12 13v9M7 5.8l9 5',packing:'M3 8h18v13H3zM2 3h20v5H2zM12 8v13M9 13h6',activity:'M3 12h4l3-8 4 16 3-8h4',camera:'M3 7h5l2-3h4l2 3h5v13H3zM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0',settings:'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',bell:'M6 9a6 6 0 0 1 12 0v6l2 3H4l2-3zM10 21h4',chevron:'m9 5 7 7-7 7',down:'m6 9 6 6 6-6',arrow:'M4 12h16M14 6l6 6-6 6',download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',plus:'M12 5v14M5 12h14',check:'m5 12 4 4L19 6',close:'m6 6 12 12M18 6 6 18',search:'M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',alert:'m12 3 10 18H2zM12 9v5M12 17v1',time:'M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',play:'m8 4 12 8-12 8z',pause:'M8 4v16M16 4v16',refresh:'M20 7V2l-3 3M4 17v5l3-3M20 7a9 9 0 0 0-16 0M4 17a9 9 0 0 0 16 0',users:'M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3M13 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0M18 3a4 4 0 0 1 0 8M22 21v-3a4 4 0 0 0-3-4',link:'m9 15 6-6M7 17l-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M17 7l2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0',logout:'M9 3H3v18h6M10 12h12m-5-5 5 5-5 5',factory:'M3 21V8l6 4V7l6 4V3h5v18zM6 16v2M11 16v2M16 16v2',chart:'M4 3v18h18M8 15l4-5 4 3 5-8',calendar:'M3 5h18v16H3zM7 2v6M17 2v6M3 10h18',info:'M12 10v7M12 6v1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0'};
export const icon=(name,cls='')=>`<svg class="icon ${cls}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.box}"/></svg>`;
export const badge=(text,tone='gray')=>`<span class="badge ${tone}"><span class="badge-dot"></span>${esc(text)}</span>`;
export const colorClass=c=>['red','blue','yellow'].includes(c)?c:'unknown';
export const colorLabel=(c,label)=>`<span class="color-label"><i class="swatch ${colorClass(c)}" aria-hidden="true"></i>${esc(label??({red:'Kırmızı',blue:'Mavi',yellow:'Sarı'}[colorClass(c)]||'Okunamadı'))}</span>`;
export const progress=(value,max,cls='')=>{
 const limit=Number.isFinite(max)&&max>0?max:1;
 const count=Number.isFinite(value)?Math.max(0,Math.min(value,limit)):0;
 return `<div class="progress ${esc(cls)}" role="progressbar" aria-valuenow="${count}" aria-valuemin="0" aria-valuemax="${limit}" aria-label="Tamamlanma"><i style="width:${count/limit*100}%"></i></div>`;
};
export const button=(text,action,cls='button',attrs='')=>`<button class="${cls}" data-action="${action}" ${attrs}>${text}</button>`;
export function empty(title,text){return `<div class="empty-state">${icon('box')}<h3>${esc(title)}</h3><p>${esc(text)}</p></div>`;}
export function csvDownload(name,rows){const cell=v=>{let t=String(v??'');if(/^[=+@\-\t\r\n]/.test(t))t="'"+t;return '"'+t.replaceAll('"','""')+'"';};const url=URL.createObjectURL(new Blob(['\ufeff'+rows.map(row=>row.map(cell).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function inPeriod(at,selected,period='day'){
 const d=dateKey(at),end=new Date(selected+'T23:59:59+03:00');if(period==='day')return d===selected;const start=new Date(end);start.setDate(start.getDate()-(period==='week'?6:29));return at>=start.getTime()-86399000&&at<=end.getTime();
}

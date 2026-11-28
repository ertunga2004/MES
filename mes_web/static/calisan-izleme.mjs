import { esc } from './atolye-onizleme-core.js?v=5';

const stations = {
  bantlama: { name: 'Bantlama', count: 'Bantlanan kutu', unit: 'kutu', chart: 'Saatlik bantlama', output: 'Üretim ve kalite' },
  paketleme: { name: 'Paketleme', count: 'Koliye alınan kutu', unit: 'kutu', chart: 'Saatlik koliye alınan kutu', output: 'Paketleme kayıtları' },
  tekniker: { name: 'Tekniker', count: 'Tamamlanan teknik işlem', unit: 'işlem', chart: 'Saatlik tamamlanan teknik işlem', output: 'Teknik işlemler' },
  giyotin: { name: 'Giyotin', count: 'Kesilen bant', unit: 'bant', chart: 'Saatlik kesim adedi', output: 'Kesim ve kalite' },
};
const statusLabel = {
  running: 'Çalışıyor', stopped: 'Durdu', paused: 'Duraklatıldı', idle: 'Boşta', maintenance: 'Bakımda',
  unmeasured: 'Vardiya açık · çalışma ölçümü yok',
};
const number = new Intl.NumberFormat('tr-TR');
const percent = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1 });
const clock = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', hour: '2-digit', minute: '2-digit' });
const date = new Intl.DateTimeFormat('tr-TR', { timeZone: 'UTC', day: 'numeric', month: 'long', year: 'numeric' });
const unavailable = 'Veri yok';
const amount = value => value == null ? unavailable : number.format(value);
const rate = (value, total) => value == null || !total ? unavailable : percent.format(value / total);

function duration(ms) {
  if (ms == null) return unavailable;
  if (ms > 0 && ms < 60_000) return '<1 dk';
  const minutes = Math.floor(ms / 60_000);
  return `${Math.floor(minutes / 60)} sa ${String(minutes % 60).padStart(2, '0')} dk`;
}

function led(status) {
  return `<span class="watch-status" data-state="${status}"><i aria-hidden="true"></i>${statusLabel[status]}</span>`;
}

function control(id, expanded = false) {
  const label = `${stations[id].name} ayrıntısını ${expanded ? 'küçült' : 'büyüt'}`;
  return `<button type="button" class="watch-expand" data-open="${expanded ? '' : id}" aria-label="${label}" title="${label}" aria-expanded="${expanded}"><i aria-hidden="true"></i></button>`;
}

function metrics(rows) {
  return `<dl class="watch-metrics">${rows.map(([label, value, tone]) => `<div><dt>${esc(label)}</dt><dd${tone ? ` class="watch-${tone}"` : ''}>${esc(value)}</dd></div>`).join('')}</dl>`;
}

function section(title, content, wide = false) {
  return `<section class="watch-section${wide ? ' watch-wide' : ''}"><h3>${esc(title)}</h3>${content}</section>`;
}

function employees(rows, unit) {
  if (!rows.length) return '<p>Bugün için vardiya kaydı yok.</p>';
  const headings = ['Çalışan', 'Vardiya başlangıcı', 'Vardiya bitişi', 'Aktif süre', `Kayıtlı ${unit}`, 'Durum'];
  return `<div class="watch-table-wrap" role="region" aria-label="Çalışan vardiyaları" tabindex="0"><table>
    <thead><tr>${headings.map(label => `<th scope="col">${esc(label)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(row => `<tr${row.end == null ? ' class="watch-current"' : ''}>
      <th scope="row">${esc(row.operator)}</th><td>${clock.format(row.start)}</td><td>${row.end == null ? '—' : clock.format(row.end)}</td>
      <td>${esc(duration(row.activeMs))}</td><td>${amount(row.count)}</td><td>${row.end == null ? 'Görevde' : 'Vardiya bitti'}</td>
    </tr>`).join('')}</tbody></table></div>`;
}

function tasks(rows) {
  if (!rows.length) return '<p>Bugün için teknik işlem kaydı yok.</p>';
  return `<ul class="watch-tasks">${rows.map(row => {
    const state = row.status === 'resolved' ? 'Tamamlandı' : row.active ? 'Müdahalede' : row.status === 'accepted' ? 'Bekliyor' : 'Açık';
    return `<li><div><strong>${esc(row.station)} · ${esc(row.text)}</strong><span>${esc(row.id)} · ${row.kind === 'fault' ? 'Arıza' : 'Yardım'}</span></div><div><strong>${state}</strong><span>${esc(duration(row.activeMs))}</span></div></li>`;
  }).join('')}</ul>`;
}

function chart(hourly, hour, unit) {
  if (!hourly.some(Boolean)) return '<p>Bugün için grafiğe alınacak işlem kaydı yok.</p>';
  const max = Math.max(...hourly);
  const description = hourly.flatMap((value, index) => value ? [`${index}:00, ${value} ${unit}`] : []).join(' · ');
  return `<div class="watch-chart" role="img" aria-label="${esc(description)}"><div class="watch-bars" aria-hidden="true">${hourly.map((value, index) => {
    const time = `${String(index).padStart(2, '0')}:00`;
    return `<span class="watch-bar${index > hour ? ' watch-future' : ''}" title="${time} · ${value} ${unit}"><i style="--bar: ${value / max * 100}%"></i></span>`;
  }).join('')}</div><div class="watch-chart-axis" aria-hidden="true"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span></div></div>`;
}

function detailBody(id, data, hour) {
  const station = stations[id];
  const { activeMs, stoppedMs, idleMs, maintenanceMs, stopCount, reasons } = data.work;
  const { total, quality } = data;
  const output = [[station.count, amount(total)]];
  if (id === 'tekniker') {
    output.push(['Başlatılan müdahale', amount(data.interventions)], ['Devam eden görev', amount(data.ongoing)]);
  } else {
    output.push(['Günlük hedef', unavailable], ['Hedef gerçekleşmesi', unavailable]);
  }
  if (id === 'bantlama' || id === 'giyotin') {
    output.push(['Sağlam', amount(quality.good), 'good'], ['Hurda', amount(quality.scrap), 'scrap'], ['Hurda oranı', rate(quality.scrap, total), 'scrap']);
  }
  if (id === 'bantlama') output.push(['Yeniden işlem', amount(quality.rework), 'rework'], ['Yeniden işlem oranı', rate(quality.rework, total), 'rework']);
  if (quality.allowed) output.push(['İzinli geçiş', amount(quality.allowed)]);
  if (id === 'paketleme') output.push(['Hatalı paket', unavailable]);

  const performance = id === 'giyotin'
    ? [['OEE', unavailable], ['Kullanılabilirlik', unavailable], ['Performans', unavailable], ['Kalite oranı', rate(quality.good, total)]]
    : id === 'bantlama' ? [['Kalite oranı', rate(quality.good, total)]] : [];
  const reasonList = reasons.length ? `<div class="watch-reasons"><h4>Duruş ve bakım nedenleri</h4><ul>${reasons.map(reason => `<li>${esc(reason)}</li>`).join('')}</ul></div>` : '';

  return `<div class="watch-detail-grid">
    ${performance.length ? section('Performans', metrics(performance), id === 'giyotin') : ''}
    ${section('Çalışma ve duruş', metrics([['Çalışma', duration(activeMs)], ['Duruş', duration(stoppedMs)],
      ['Boşta', duration(idleMs)], ['Bakım', duration(maintenanceMs)], ['Planlanan süre', unavailable], ['Duruş sayısı', amount(stopCount)]]) + reasonList)}
    ${section(station.output, metrics(output), id === 'bantlama')}
    ${section('Çalışanlar', employees(data.workers, station.unit), true)}
    ${id === 'tekniker' ? section('Teknik müdahaleler', tasks(data.tasks), true) : ''}
    ${section(station.chart, chart(data.hourly, hour, station.unit), true)}
  </div>`;
}

const grid = document.querySelector('[data-watch-grid]');
const detail = document.querySelector('[data-watch-detail]');
const notice = document.querySelector('[data-watch-notice]');
const dateLabel = document.querySelector('[data-watch-date]');
const designer = document.querySelector('[data-watch-designer]');
let current = new URLSearchParams(location.search).get('istasyon');
current = Object.hasOwn(stations, current) ? current : null;
let snapshot;
let fetching = false;
let lastDetailContent;

grid.innerHTML = Object.entries(stations).map(([id, station]) => `<article class="watch-card" aria-labelledby="watch-title-${id}" data-station-card="${id}">
  <header><h2 id="watch-title-${id}">${station.name}</h2><div class="watch-actions"><span data-led></span>${control(id)}</div></header>
  <div data-summary></div></article>`).join('');
grid.hidden = true;

function render() {
  if (!snapshot) return;
  dateLabel.textContent = date.format(new Date(`${snapshot.date}T00:00:00Z`));
  designer.hidden = !['admin', 'engineer'].includes(snapshot.role);
  grid.hidden = Boolean(current);
  detail.hidden = !current;
  if (!current) {
    for (const [id, station] of Object.entries(stations)) {
      const data = snapshot.stations[id];
      const card = grid.querySelector(`[data-station-card="${id}"]`);
      card.querySelector('[data-led]').innerHTML = led(data.status);
      card.querySelector('[data-summary]').innerHTML = metrics([[station.count, amount(data.total)], ['Toplam çalışma', duration(data.work.activeMs)]]);
    }
    return;
  }

  if (detail.dataset.station !== current) {
    detail.dataset.station = current;
    detail.innerHTML = `<header><h2 id="watch-detail-title">${stations[current].name}</h2><div class="watch-actions"><span data-led></span>${control(current, true)}</div></header><div data-detail-body></div>`;
    lastDetailContent = undefined;
  }
  const data = snapshot.stations[current];
  detail.querySelector('[data-led]').innerHTML = led(data.status);
  const content = detailBody(current, data, snapshot.hour);
  if (content !== lastDetailContent) {
    const body = detail.querySelector('[data-detail-body]');
    const table = body.querySelector('.watch-table-wrap');
    const scroll = table?.scrollLeft;
    const focused = document.activeElement === table;
    body.innerHTML = content;
    const nextTable = body.querySelector('.watch-table-wrap');
    if (nextTable && scroll) nextTable.scrollLeft = scroll;
    if (focused) nextTable?.focus({ preventScroll: true });
    lastDetailContent = content;
  }
}

function selectStation(id) {
  const previous = current;
  current = id || null;
  const url = new URL(location.href);
  if (current) url.searchParams.set('istasyon', current);
  else url.searchParams.delete('istasyon');
  history.replaceState(null, '', url);
  render();
  const target = current ? detail.querySelector('button') : grid.querySelector(`[data-open="${previous}"]`);
  target?.focus();
  if (current) window.scrollTo({ top: 0, behavior: 'instant' });
}

document.querySelector('.watch-shell').addEventListener('click', event => {
  const button = event.target.closest('button[data-open]');
  if (button) selectStation(button.dataset.open);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && current && snapshot) selectStation(null);
});

async function refresh() {
  if (fetching) return;
  fetching = true;
  try {
    const response = await fetch('/api/workspace/monitoring/dashboard', { cache: 'no-store', signal: AbortSignal.timeout(9000) });
    if (response.status === 401) return location.replace('/mes-oturum');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    snapshot = await response.json();
    notice.hidden = true;
    render();
  } catch {
    notice.hidden = false;
    notice.textContent = snapshot ? 'Bağlantı kesildi. Son alınan istasyon kayıtları gösteriliyor.' : 'İstasyon kayıtlarına ulaşılamıyor.';
  } finally {
    fetching = false;
  }
}

setInterval(refresh, 3000);
void refresh();

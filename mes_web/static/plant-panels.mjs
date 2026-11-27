import { esc } from './atolye-onizleme-core.js?v=5';

const unknown = 'Veri yok';
const trNumber = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const trDay = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: '2-digit', month: 'short', year: 'numeric' });
const trTime = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const tokens = { online: 'Bağlı', offline: 'Bağlantı kesik', reconnecting: 'Yeniden bağlanıyor', degraded: 'Kısıtlı',
  idle: 'Boşta', run: 'Çalışıyor', running: 'Çalışıyor', moving: 'Hareket ediyor', stopped: 'Durdu', stop: 'Durdu',
  active: 'Aktif', pending_approval: 'Onay bekliyor', completed: 'Tamamlandı', busy: 'İşlemde',
  on: 'Çalışıyor', off: 'Kapalı', ready: 'Hazır', fault: 'Arıza', error: 'Hata', unknown, red: 'Kırmızı', yellow: 'Sarı', blue: 'Mavi',
  GOOD: 'Sağlam', REWORK: 'Yeniden işlem', SCRAP: 'Hurda', info: 'Bilgi', warn: 'Uyarı' };
const results = { success: ['Başarılı', 'ok'], failed: ['Başarısız', 'error'], uncertain: ['Doğrulanamadı', 'warn'] };
const element = id => document.getElementById(id);
const value = input => input == null || input === '' ? unknown : input;
const label = input => tokens[input] ?? value(input);
const number = input => Number.isFinite(input) ? trNumber.format(input) : unknown;
const percent = input => Number.isFinite(input) ? `%${number(input)}` : unknown;
const seconds = ms => Number.isFinite(ms) ? `${number(ms / 1000)} sn` : unknown;
const day = stamp => validDate(stamp) ? trDay.format(new Date(stamp)) : '—';
const time = stamp => validDate(stamp) ? trTime.format(new Date(stamp)) : '—';
const timestamp = stamp => validDate(stamp) ? `${day(stamp)} · ${time(stamp)}` : unknown;
const fresh = (stamp, maxSeconds) => validDate(stamp) && Date.now() - Date.parse(stamp) <= maxSeconds * 1000;

function validDate(stamp) {
  return typeof stamp === 'string' && Number.isFinite(Date.parse(stamp));
}

function badge(text, tone) {
  return `<span class="plant-led" data-tone="${tone}">${esc(text)}</span>`;
}

function metrics(rows) {
  return rows.map(([title, metric, note]) => `<article class="plant-kpi"><span>${esc(title)}</span><strong>${esc(metric)}</strong>${note ? `<small>${esc(note)}</small>` : ''}</article>`).join('');
}

function fields(rows) {
  return rows.map(([title, result]) => `<div class="status-row"><span>${esc(title)}</span><strong>${esc(result)}</strong></div>`).join('');
}

function table(caption, headings, rows, empty) {
  return `<div class="plant-table-wrap" tabindex="0" role="region" aria-label="${esc(caption)}"><table class="plant-table">
    <thead><tr>${headings.map(heading => `<th scope="col">${esc(heading)}</th>`).join('')}</tr></thead>
    <tbody>${rows.length ? rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${headings.length}" class="empty-state">${esc(empty)}</td></tr>`}</tbody></table></div>`;
}

function flowCard({ name, status, tone, item, complete, waiting, cycle, standard, handoff }) {
  return `<li class="plant-stage"><div><h3>${esc(name)}</h3>${badge(status, tone)}</div><dl>${[
    ['İşlenen ürün', item], ['Tamamlanan', complete], ['Bekleyen', waiting],
    ['Son çevrim', cycle], ['Standart çevrim', standard], ['Aktarım', handoff],
  ].map(([key, entry]) => `<div><dt>${key}</dt><dd>${esc(value(entry))}</dd></div>`).join('')}</dl></li>`;
}

function readProduction(snapshot) {
  if (!snapshot) return;
  const plant = snapshot.plant || {};
  const orders = snapshot.work_orders || {};
  const order = orders.active_order;
  const oee = snapshot.oee;
  const system = snapshot.system_status;
  const heartbeat = snapshot.connection.mega_heartbeat;
  const live = heartbeat.state === 'online' && fresh(snapshot.timestamps.last_status_at, heartbeat.timeout_sec);
  const dayMatches = plant.local_day && day(`${plant.local_day}T12:00:00+03:00`) === trDay.format(new Date());
  const done = dayMatches ? plant.daily_completed : null;
  const product = order?.stock_name || order?.product_code || order?.stock_code || unknown;
  const standard = order?.cycle_time_ms > 0 ? order.cycle_time_ms : null;
  const waiting = live ? system.queue_depth : null;
  const median = live && fresh(plant.cycle_at, 600) ? plant.cycle_median_ms : null;
  const lastCycle = live && fresh(plant.cycle_at, 600) ? plant.last_cycle_ms : null;
  const fault = oee.fault.active ? oee.fault.reason || 'Açık arıza kaydı' : null;
  const slowRobot = waiting > 0 && standard != null && median != null && median > standard;
  const eta = order?.status === 'active' && live && !fault && plant.rate_order_id === order.order_id && plant.rate_ms > 0 && fresh(plant.cycle_at, 600)
    ? new Date(Date.now() + order.remaining_qty * plant.rate_ms).toISOString() : null;
  const shiftShortfall = oee.shift.active && oee.targets.expected_qty > oee.production.total;
  const rateGap = standard != null && median != null ? median - standard : null;
  const operational = code => live ? label(code) : unknown;
  const machineTone = code => !live ? 'idle' : ['fault', 'error', 'alarm'].includes(code) ? 'error' :
    ['run', 'running', 'moving', 'busy', 'on', 'active'].includes(code) ? 'ok' : 'idle';

  element('production-day').textContent = trDay.format(new Date());
  element('production-summary').innerHTML = metrics([
    ['Aktif iş emri', order?.order_id || 'Açık emir yok'], ['Üretimdeki ürün', product],
    ['Günlük hedef', unknown, oee.shift.active && oee.targets.target_qty > 0 ? `Vardiya hedefi ${number(oee.targets.target_qty)}` : null],
    ['Bugünkü üretim', number(done), 'Kayıtlı hat çıkışı'], ['Kalan üretim', number(order?.remaining_qty), 'Aktif iş emri'],
    ['Günlük hedef gerçekleşmesi', unknown, order ? `İş emri ${percent(order.progress_pct)}` : null],
  ]);

  const coating = orders.manual_coating;
  const cut = coating?.cutting;
  const handoff = orders.conveyor_handoff;
  const stages = [];
  if (cut) stages.push({ name: 'Giyotin', status: cut.order_open ? 'İş emri açık' : 'Beklemede', tone: 'idle', item: product,
    complete: `${number(cut.cut_tapes)} / ${number(cut.target_tapes)} bant`, handoff: `${number(cut.available_boxes)} kutuluk bant hazır` });
  if (coating?.unit_supported) stages.push({ name: 'Manuel kaplama', status: coating.can_record ? 'Kayıt açık' : 'Beklemede', tone: 'idle',
    item: product, complete: `${number(coating.completed_qty)} / ${number(coating.target_qty)} kutu`,
    waiting: cut ? number(cut.available_boxes) : null, handoff: handoff ? `${number(handoff.ready_qty)} kutu teslime hazır` : null });
  stages.push(
    { name: 'Konveyör', status: fault ? 'Arıza kaydı açık' : operational(system.conveyor_state), tone: fault ? 'error' : machineTone(system.conveyor_state),
      item: live ? plant.queue_item : null, handoff: live && system.stop_request ? 'Durma talebi var' : live ? 'Renk kontrolü' : null },
    { name: 'Renk sensörü', status: operational(system.last_color), tone: live && system.last_color !== 'unknown' ? 'ok' : 'idle',
      complete: dayMatches ? number(plant.measured_today) : unknown, handoff: waiting == null ? null : `${number(waiting)} kutu hat kuyruğunda` },
    { name: 'Robot kol', status: operational(system.robot_state), tone: machineTone(system.robot_state),
      item: live ? plant.robot_item : null, waiting: number(waiting), cycle: seconds(lastCycle),
      standard: standard ? `${seconds(standard)} · hat planı` : unknown, handoff: plant.robot_item && live ? 'Çıkış işlemi bekleniyor' : null },
    { name: 'Hat çıkışı', status: live ? 'Hat bağlantısı açık' : unknown, tone: live ? 'ok' : 'idle',
      item: dayMatches ? plant.last_completed : null, complete: number(done) },
  );
  const flow = element('production-flow');
  flow.innerHTML = `<ol class="plant-flow" tabindex="0" aria-label="Konveyör istasyon sırası" style="--stages:${stages.length}">${stages.map(flowCard).join('')}</ol>`;

  element('production-losses').innerHTML = fields([
    ['Darboğaz adayı', slowRobot ? 'Robot kol · kuyruk + çevrim sapması' : 'Yeterli ölçüm yok'], ['Hat kuyruğu', number(waiting)],
    ['Medyan robot çevrimi', seconds(median)], ['Hat planına sapma', seconds(rateGap)],
    ['Vardiya üretim gecikmesi', oee.shift.active ? `${number(Math.max(0, (oee.targets.expected_qty || 0) - oee.production.total))} kutu` : unknown],
    ['Plansız duruş', oee.shift.active ? `${number(orders.performance_panel?.unplanned_stop_min)} dk` : unknown],
  ]);
  const alerts = [];
  if (fault) alerts.push(['error', fault]);
  if (slowRobot) alerts.push(['warn', `Robot kolun medyan çevrimi hat planını ${seconds(rateGap)} aştı. Kuyrukta ${number(waiting)} kutu var.`]);
  if (live && system.stop_request && waiting > 0) alerts.push(['warn', 'Durma talebi sırasında hat kuyruğunda kutu var.']);
  if (shiftShortfall) alerts.push(['warn', 'Vardiya üretimi bu saate ait hedefin gerisinde.']);
  if (order && (order.scrap_qty > 0 || order.rework_qty > 0)) alerts.push(['warn', `Aktif emirde ${number(order.scrap_qty)} hurda, ${number(order.rework_qty)} yeniden işlem kaydı var.`]);
  if (order?.acceptance_pending) alerts.push(['ok', `${order.order_id} tamamlandı. Operatör onayı bekleniyor.`]);
  const completed = [...(orders.completed || [])].sort((a, b) => Date.parse(b.completed_at) - Date.parse(a.completed_at));
  if (completed[0] && fresh(completed[0].completed_at, 300)) alerts.push(['ok', `${completed[0].order_id} tamamlandı.`]);
  element('production-alerts').innerHTML = alerts.length ? `<ul class="plant-alerts">${alerts.map(([tone, message]) => `<li>${badge(tone === 'error' ? 'Arıza' : tone === 'warn' ? 'Uyarı' : 'Bilgi', tone)}<span>${esc(message)}</span></li>`).join('')}</ul>`
    : '<p class="empty-state">Kayıtlı operasyonel uyarı yok.</p>';
  const rows = [order, ...completed].filter(Boolean).map(row => [
    row.order_id, row.stock_name || row.product_code || row.stock_code, number(row.qty), number(row.completed_qty),
    number(row.remaining_qty), timestamp(row.started_at), timestamp(row === order ? eta || row.auto_completed_at : row.completed_at),
    percent(row.progress_pct), label(row.status),
  ].map(cell => esc(value(cell))));
  element('production-orders').innerHTML = table('İş emri takibi', ['İş emri', 'Ürün', 'Plan', 'Tamamlanan', 'Kalan', 'Başlangıç', 'Tahmin / bitiş', 'İlerleme', 'Durum'], rows, 'Aktif veya tamamlanan iş emri yok.');
}

function readSystem(data, runtime) {
  const mqtt = data.connection.mqtt;
  const incidents = data.devices.filter(device => device.tone === 'error');
  const alarms = new Set(incidents.map(incident => incident.name));
  if (data.database !== 'online' || data.journal_error) alarms.add('Kayıt deposu');
  if (!mqtt.connected && mqtt.last_changed_at) alarms.add('MQTT broker');
  const totalMinutes = Math.floor(data.uptime_seconds / 60);
  element('diagnostic-summary').innerHTML = metrics([
    ['MES veri akışı', runtime === 'live' ? 'Bağlı' : 'Bağlantı bekleniyor'], ['Sunucu', label(data.server)],
    ['Veri tabanı', data.database === 'online' ? 'Kayıt deposu erişilebilir' : 'Erişim hatası', data.journal_error ? 'Kayıt yazma hatası görüldü' : null],
    ['Haberleşme', label(mqtt.state), 'MQTT broker'], ['Son veri', timestamp(mqtt.last_message_at)],
    ['Aktif hata', number(alarms.size), [...alarms].join(' · ')], ['Çalışma süresi', `${Math.floor(totalMinutes / 60)} sa ${totalMinutes % 60} dk`],
  ]);
  const deviceRows = data.devices.map(device => {
    const state = device.tone === 'maintenance' ? 'Bakımda' : device.status ? label(device.status)
      : device.tone === 'error' ? 'Kesinti / arıza' : device.tone === 'warn' ? 'Uyarı' : unknown;
    return [`<strong>${esc(device.name)}</strong>`, esc(value(device.connection)), badge(state, device.tone),
      esc(timestamp(device.at)), esc(value(device.detail)), esc(value(device.code))];
  });
  element('diagnostic-devices').innerHTML = table('Donanım durumu', ['Donanım', 'Bağlantı', 'Durum', 'Son haberleşme', 'Hata / uyarı', 'Kod'], deviceRows, 'Donanım kaydı bulunamadı.');
  const eventRows = data.events.map(event => [esc(day(event.at)), esc(time(event.at)), esc(event.device), esc(event.kind),
    esc(event.message), esc(event.code || '—'), badge(label(event.level), event.level === 'info' ? 'idle' : event.level)]);
  element('diagnostic-events').innerHTML = table('Sistem olayları', ['Tarih', 'Saat', 'Donanım', 'Olay', 'Açıklama', 'Kod', 'Seviye'], eventRows, 'Henüz sistem olayı kaydedilmedi.');
}

function readCamera(data) {
  const good = data.today.success || 0;
  const failed = data.today.failed || 0;
  const uncertain = data.today.uncertain || 0;
  const total = good + failed + uncertain;
  element('camera-source').textContent = data.ingest_enabled ? 'Bugünkü okumalar · Türkiye saati' : 'Kamera alımı kapalı · Kayıt geçmişi';
  element('camera-summary').innerHTML = metrics([
    ['Bugünkü okumalar', number(total), uncertain ? `${number(uncertain)} doğrulanamadı` : null],
    ['Başarılı', number(good)], ['Başarısız', number(failed)], ['Başarı oranı', percent(total ? good / total * 100 : null)],
    ['Son okuma', timestamp(data.last_at)],
  ]);
  const rows = data.items.map(row => {
    const [title, tone] = results[row.result];
    return [`<button type="button" class="plant-record" data-record="${esc(row.id)}" aria-label="${esc(row.id.slice(0, 12))} numaralı okumanın ayrıntısı">${esc(row.id.slice(0, 12))}</button>`,
      esc(day(row.at)), esc(time(row.at)), esc(value(row.camera)), esc(value(row.item_id)), esc(value(row.code)),
      esc(value([row.product_code, row.description].filter(Boolean).join(' · '))), esc(value(row.order_id)), badge(title, tone),
      esc(label(row.quality)), row.duration_ms == null ? '—' : `${esc(number(row.duration_ms))} ms`, esc(row.error || '—'), row.image_url ? 'Var' : '—'];
  });
  const container = element('camera-table');
  const focused = document.activeElement?.dataset.record;
  const horizontal = container.querySelector('.plant-table-wrap')?.scrollLeft;
  container.innerHTML = table('Kamera kayıtları', ['Kayıt no', 'Tarih', 'Saat', 'Kamera', 'Ürün ID', 'Barkod / QR', 'Tespit', 'İş emri', 'Sonuç', 'Kalite', 'Okuma süresi', 'Hata', 'Görüntü'], rows, data.count ? 'Bu sayfada kayıt yok.' : 'Bu filtrelerle eşleşen okuma kaydı yok.');
  if (horizontal) container.querySelector('.plant-table-wrap').scrollLeft = horizontal;
  if (focused) container.querySelector(`[data-record="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
  const pages = Math.max(1, Math.ceil(data.count / data.limit));
  element('camera-page-label').textContent = `${number(data.count)} kayıt · ${data.page} / ${pages}`;
  element('camera-prev').disabled = data.page <= 1;
  element('camera-next').disabled = data.page >= pages;
}

export function bindPlantPanels({ moduleId, getSnapshot, getRuntime }) {
  const base = `/api/modules/${encodeURIComponent(moduleId)}`;
  const form = element('camera-filters');
  const modal = element('camera-detail');
  const body = element('camera-detail-body');
  const exportLink = element('camera-export');
  let tab;
  let page = 1;
  let filters = new URLSearchParams();
  let request;
  let detailRequest;
  let activeRecord;
  let lastCameraResponse;

  function updateExport() {
    exportLink.href = `${base}/camera-records/export?${filters}`;
  }
  updateExport();

  async function get(url, signal) {
    const response = await fetch(url, { cache: 'no-store', signal: AbortSignal.any([signal, AbortSignal.timeout(8000)]) });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Veri bağlantısı kurulamadı.');
    }
    return response.json();
  }

  async function refresh(replace = false) {
    if (replace) request?.abort();
    if (request && !replace) return;
    if (tab === 'operations') return readProduction(getSnapshot());
    if (tab !== 'system-status' && tab !== 'camera-records') return;
    const controller = new AbortController();
    request = controller;
    const currentTab = tab;
    const camera = currentTab === 'camera-records';
    const feedback = element(camera ? 'camera-feedback' : 'diagnostic-feedback');
    try {
      const params = new URLSearchParams(filters);
      params.set('page', page);
      const data = await get(`${base}/${camera ? `camera-records?${params}` : 'system-status'}`, controller.signal);
      if (tab !== currentTab || controller.signal.aborted) return;
      feedback.textContent = '';
      if (camera) {
        page = data.page;
        const representation = JSON.stringify(data);
        if (lastCameraResponse !== representation) readCamera(data);
        lastCameraResponse = representation;
      } else {
        readSystem(data, getRuntime());
      }
    } catch (error) {
      if (!controller.signal.aborted && tab === currentTab) feedback.textContent = error.message;
    } finally {
      if (request === controller) request = null;
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    filters = new URLSearchParams([...new FormData(form)].map(([key, input]) => [key, input.trim()]).filter(([, input]) => input));
    page = 1;
    updateExport();
    void refresh(true);
  });
  form.addEventListener('reset', () => {
    filters = new URLSearchParams();
    page = 1;
    updateExport();
    void refresh(true);
  });
  for (const [id, direction] of [['camera-prev', -1], ['camera-next', 1]]) {
    element(id).addEventListener('click', () => {
      page += direction;
      void refresh(true);
    });
  }
  element('camera-table').addEventListener('click', async event => {
    const button = event.target.closest('button[data-record]');
    if (!button) return;
    activeRecord = button.dataset.record;
    detailRequest?.abort();
    detailRequest = new AbortController();
    const signal = detailRequest.signal;
    body.textContent = 'Okuma yükleniyor…';
    modal.showModal();
    try {
      const row = await get(`${base}/camera-records/${encodeURIComponent(activeRecord)}`, signal);
      if (signal.aborted) return;
      body.innerHTML = `<div class="status-grid">${fields([
        ['Kayıt', row.id], ['Kamera', value(row.camera)], ['Okuma zamanı', timestamp(row.at)], ['Sonuç', results[row.result][0]],
        ['Ürün ID', value(row.item_id)], ['Ürün kodu', value(row.product_code)], ['Tespit', value(row.description)],
        ['Barkod / QR', value(row.code)], ['İş emri', value(row.order_id)], ['Kalite', label(row.quality)],
        ['Takip', value(row.track_id)], ['Eşleşme', label(row.correlation)], ['Hata', value(row.error)],
        ['Görüntü', row.image_url ? 'Kayıtlı' : 'Görüntü kaydı yok'],
      ])}</div><h3>Ham kamera verisi</h3><pre>${esc(row.raw)}</pre>`;
    } catch (error) {
      if (!signal.aborted) body.textContent = error.message;
    }
  });
  modal.addEventListener('close', () => {
    detailRequest?.abort();
    if (activeRecord) element('camera-table').querySelector(`[data-record="${CSS.escape(activeRecord)}"]`)?.focus({ preventScroll: true });
    activeRecord = null;
  });

  setInterval(() => { if (!document.hidden) void refresh(); }, 3000);
  return {
    activate(next) {
      tab = next;
      if (tab !== 'camera-records' && modal.open) modal.close();
      void refresh(true);
    },
    snapshot() { if (tab === 'operations') readProduction(getSnapshot()); },
  };
}

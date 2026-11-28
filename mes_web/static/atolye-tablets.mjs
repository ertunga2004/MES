import { esc, duration } from './atolye-onizleme-core.js';
import { SAMPLE_MONITOR_DATA } from './atolye-onizleme-data.js';
import {
  COLORS, OUTCOMES, TAPING_STEPS, FAULT_STATUS, elapsedTaping, packedTotal, readyPairs, readyToPack,
} from './atolye-tablet-state.mjs';

const colorEntries = Object.entries(COLORS);
const outcomes = Object.entries(OUTCOMES);
const orderLabel = order => `${order.id} · ${order.customer}`;
const goodOrReject = [['good', 'Uygun'], ['scrap', 'Red']];

function options(rows, placeholder = 'Seçin') {
  return `<option value="">${esc(placeholder)}</option>${rows.map(([value, label]) =>
    `<option value="${esc(value)}">${esc(label)}</option>`).join('')}`;
}

function panel(title, content, wide = false) {
  return `<section class="panel card${wide ? ' panel-span-12' : ''}"><div class="panel-head"><h3>${esc(title)}</h3></div>${content}</section>`;
}

function stats(rows) {
  return `<div class="tablet-stats">${rows.map(([label, value]) =>
    `<div class="connection-card"><p>${esc(label)}</p><strong>${esc(value)}</strong></div>`).join('')}</div>`;
}

function button(label, { primary = false, disabled = false } = {}) {
  return `<button type="submit" class="preset-button tablet-button${primary ? '' : ' tablet-button-secondary'}"${disabled ? ' disabled' : ''}>${esc(label)}</button>`;
}

function blank(text) {
  return `<p class="tablet-muted tablet-empty">${esc(text)}</p>`;
}

function pill(label, tone = '') {
  return `<span class="runtime-badge tablet-pill${tone ? ` tablet-pill-${tone}` : ''}">${esc(label)}</span>`;
}

function colorMark(color) {
  return `<span class="tablet-color"><span class="tablet-dot tablet-dot-${color}" aria-hidden="true"></span>${COLORS[color]}</span>`;
}

function actionForm(action, fields, label, settings = {}) {
  return `<form class="tablet-form" data-task="${action}">${fields}<div class="tablet-actions">${button(label, settings)}</div></form>`;
}

function boxOptions(boxes) {
  return options(boxes.map(box => [box.id, `${box.id} · ${COLORS[box.color]}${box.measurement ? ` · ${box.measurement}` : ''}`]), 'Kutu seçin');
}

function field(label, name, type = 'text', extra = '') {
  return `<label>${label}<input name="${name}" type="${type}"${extra ? ` ${extra}` : ''} required></label>`;
}

function checkField(label, name) {
  return `<label class="tablet-inline-check"><input name="${name}" type="checkbox" required>${label}</label>`;
}

function workRef(state) {
  const order = state.orders[0];
  return `<div class="tablet-order"><span class="tablet-muted">Aktif örnek iş emri</span><strong>${esc(orderLabel(order))}</strong></div>`;
}

function taping(state) {
  const box = state.activeBox;
  const ready = colorEntries.map(([color, label]) => [label, readyPairs(state, color)]);
  const pending = state.boxes.filter(row => row.stage === 'handoff').length;
  const processed = Object.values(state.used).reduce((total, count) => total + count, 0) / 2 - Number(Boolean(box));
  const current = !box ? actionForm('start', `
    <div class="tablet-fields">
      <label>Bant rengi<select name="color" required>${options(colorEntries.filter(([color]) => readyPairs(state, color) > 0))}</select></label>
      <label>Kutu kodu<input name="box" maxlength="60" required></label>
    </div>`, 'Kutuyu başlat', { primary: true, disabled: !ready.some(([, count]) => count > 0) }) : `
    <div class="tablet-row tablet-active-box"><div><strong>${esc(box.id)}</strong> ${colorMark(box.color)}</div>${pill(box.paused ? 'Duraklatıldı' : 'İşlemde', box.paused ? 'amber' : 'green')}</div>
    <fieldset class="tablet-checklist"${box.paused ? ' disabled' : ''}>
      <legend>İşlem adımları</legend>
      ${TAPING_STEPS.map((step, index) => `<label><input type="checkbox" data-taping-step="${index}"${box.steps[index] ? ' checked' : ''}><span>${esc(step)}</span></label>`).join('')}
    </fieldset>
    ${actionForm('finish', `<div class="tablet-fields">
      <label>Kontrol sonucu<select name="outcome"${box.paused ? ' disabled' : ''}>${outcomes.filter(([name]) => name !== 'allowed').map(([name, title]) => `<option value="${name}">${title}</option>`).join('')}</select></label>
      <label data-outcome-length>Bant uzunluğu (mm)<input name="length" type="number" min="0.01" step="any"${box.paused ? ' disabled' : ''} required></label>
      <label data-outcome-reason hidden>Kalite gerekçesi<input name="reason" maxlength="240" disabled></label>
    </div>`, 'Sonucu kaydet', { primary: true, disabled: box.paused || !box.steps.every(Boolean) })}`;
  const timeControls = !box ? blank('Kutu başladığında süre sayacı çalışır.') : `
    <p class="tablet-time" data-taping-clock>${duration(elapsedTaping(box, Date.now()))}</p>
    ${box.paused ? `<p class="tablet-muted">${esc(box.pauseReason)}</p>${actionForm('resume', '', 'Bantlamaya devam et')}` :
      actionForm('pause', '<label>Duraklatma nedeni<input name="reason" maxlength="240" required></label>', 'Duraklat')}`;
  return `${workRef(state)}
    <div class="content-grid tablet-grid">
      ${panel('Kutu bantlama', current)}
      ${panel('İş süresi', timeControls)}
      ${panel('Bantlama ilerlemesi', `${stats([['İşlenen kutu', `${processed} / ${state.orders[0].qty}`], ['Konveyör teslimi bekliyor', pending]])}<p class="tablet-muted">Renge göre hazır kutu</p>${stats(ready)}`)}
      ${panel('WIP bekleme alanları', stats(state.wip.map(area => [area.name, `${area.occupied} / ${area.capacity}`])))}
    </div>`;
}

function cutting(state) {
  if (state.protocol4) return protocolCutting(state.protocol4);
  const rows = colorEntries.map(([color]) => {
    const remaining = state.cut[color] - state.used[color];
    return `<tr><th scope="row">${colorMark(color)}</th><td>${state.cut[color]} / ${state.goals[color] * 2}</td><td>${readyPairs(state, color)}</td><td>${remaining % 2}</td></tr>`;
  }).join('');
  const log = state.cutLog.slice(0, 12).map(row => `<div class="tablet-row"><div><strong>${esc(row.lot)}</strong>${colorMark(row.color)}</div><span>${row.count} bant${row.length ? ` · ${row.length} mm` : ''}</span>${pill(row.result === 'good' ? 'Uygun' : 'Red', row.result === 'good' ? 'green' : 'amber')}</div>`).join('');
  return `${workRef(state)}<div class="content-grid tablet-grid">
    ${panel('Kesim kaydı', `<p class="tablet-muted">Her iki kesilmiş bant aynı renkte bir kutuya yeter.</p>${actionForm('cut', `<div class="tablet-fields">
      <label>Bant rengi<select name="color" required>${options(colorEntries)}</select></label>
      <label>Kesilen bant adedi<input name="count" type="number" inputmode="numeric" min="1" max="10000" required></label>
      <label>Kesim partisi<input name="lot" maxlength="60" required></label>
      ${field('Ölçülen uzunluk (mm)', 'length', 'number', 'min="0.01" step="any"')}
      <label>Kalite sonucu<select name="result" required>${options(goodOrReject)}</select></label>
      </div>${checkField('Koruyucu kalkan kontrol edildi', 'shield')}`, 'Kesimi kaydet', { primary: true })}`)}
    ${panel('Kesim ve bantlama durumu', `<div class="tablet-table-wrap"><table class="tablet-table"><thead><tr><th scope="col">Renk</th><th scope="col">Kesilen / Hedef</th><th scope="col">Hazır kutu</th><th scope="col">Tek bant</th></tr></thead><tbody>${rows}</tbody></table></div>`)}
    ${panel('Son kesim kayıtları', `<div class="tablet-list">${log}</div>`, true)}
  </div>`;
}

const giyotinModes = {
  offline: 'Cihaz bağlantısı bekleniyor',
  not_ready: 'Nano hazır değil',
  ready: 'Yeni çevrim için hazır',
  awaiting_permit: 'İzin bekleniyor',
  permitted: 'İzin verildi',
  running: 'Çevrim sürüyor',
  awaiting_event: 'Çevrim kaydı veya cihaz durumu bekleniyor',
  revoking: 'İzin kaldırma onayı bekleniyor',
  review: 'Çevrim uzlaştırması gerekli',
};
const giyotinReasons = {
  paused: 'Üretim duraklatıldı.',
  stopped: 'Üretim durduruldu.',
  order_or_shift_ended: 'İş emri değişti veya vardiya kapandı.',
  target_reached: 'İş emri hedefi tamamlandı.',
  permit_expired: 'İzin süresi doldu. Yeni çevrim için yeniden başlatın.',
  permit_unconfirmed: 'İzin cihaz tarafından doğrulanamadı.',
  cycle_uncertain: 'Nano çevrim sonucunu doğrulayamadı.',
  cycle_unconfirmed: 'Çevrim sonucu alınamadı.',
  backend_restart: 'MES yeniden başlatıldığında açık çevrim kaydı bulundu.',
  nano_reset: 'Nano yeniden başladı.',
  telemetry_loss: 'Köprü yayın kaybı bildirdi. Cihaz ve MES kayıtlarını karşılaştırın.',
  connection_lost: 'Cihaz bağlantısı kesildi.',
  command_rejected: 'Cihaz komutu reddetti.',
  publish_failed: 'MQTT yayını doğrulanamadı.',
  unmatched_event: 'Çevrim olayı kayıtlı izinle eşleştirilemedi.',
  unknown_permit: 'MES kaydı olmayan izin kapatılıyor.',
};
const giyotinNanoStates = {
  SESSION_REQUIRED: 'Oturum bekleniyor', CONFIG_REQUIRED: 'Ayar gerekli', PERMIT_REQUIRED: 'İzin gerekli',
  WAIT_RELEASE: 'Butonlar bırakılmalı', WAIT_SECOND_BUTTON: 'İkinci buton bekleniyor', READY: 'Hazır',
  CYCLE_RUNNING: 'Çevrim sürüyor', EVENT_PENDING: 'Olay onayı bekleniyor', CYCLE_UNCERTAIN: 'Çevrim belirsiz',
};
const hiddenField = (name, value) => `<input type="hidden" name="${name}" value="${esc(value)}">`;

function protocolCutting(device) {
  const { order, events, review } = device;
  const text = giyotinReasons[review?.reason ?? device.reason];
  const direction = device.mode === 'permitted' ?
    (device.nanoState === 'WAIT_RELEASE' ? 'İki fiziksel butonu bırakın.' : 'Çevrim için iki fiziksel butonu kullanın.') : '';
  const startFields = order ? hiddenField('orderId', order.id) + hiddenField('orderKey', order.key) : '';
  const startLabel = device.reason === 'paused' ? 'Devam et' : 'Başlat';
  const orderTitle = order?.stationOrderId ? `Ana emir ${order.id} · İstasyon emri ${order.stationOrderId}` : order?.id;
  const buttonState = value => value === true ? 'Basılı' : value === false ? 'Bırakıldı' : '—';
  const records = events.filter(row => row.count).map(row => `<div class="tablet-row">
    <div><strong>${esc(row.stationOrderId || row.orderId)}</strong><span>${esc(row.operator ?? '')}</span></div>
    <span>${esc(new Date(row.recordedAt).toLocaleString('tr-TR'))}</span>
    ${pill(row.resolution ? 'Uzlaştırıldı' : 'Nano çevrimi', 'green')}</div>`).join('');
  const resolve = review ? panel('Çevrim uzlaştırması', `<p class="tablet-muted">Fiziksel sonucu ve MES kaydını karşılaştırın.</p>${actionForm(
    'giyotin-reconcile', hiddenField('reviewId', review.id) + `<label>Çevrim sonucu<select name="outcome" required>${options([
      ...(review.canCredit ? [['completed', 'Tamamlandığı doğrulandı · Bir çevrim kaydet']] : []),
      ['no_credit', 'Kayıtlar doğrulandı · Sayaç değişmesin'],
    ])}</select></label>` + checkField('Fiziksel sonucu ve MES kaydını kontrol ettim', 'confirmed'), 'Uzlaştırmayı kaydet')}`, true) : '';
  return `<div class="content-grid tablet-grid">
    ${panel('Çevrim kontrolü', `
      ${text || direction ? `<p class="tablet-muted">${esc([text, direction].filter(Boolean).join(' '))}</p>` : ''}
      ${device.rejection ? `<p class="tablet-muted">${esc(device.rejection)}</p>` : ''}
      ${stats([['Cihaz', device.online ? 'Çevrimiçi' : 'Çevrimdışı'], ['Nano', giyotinNanoStates[device.nanoState] ?? '—'],
        ['D2', buttonState(device.buttons[0])], ['D3', buttonState(device.buttons[1])]])}
      <div class="tablet-actions tablet-giyotin-actions">
        ${actionForm('giyotin-start', startFields, startLabel, { primary: true, disabled: !device.canStart })}
        ${actionForm('giyotin-pause', '', 'Duraklat', { disabled: !device.canStop })}
        ${actionForm('giyotin-stop', '', 'Durdur', { disabled: !device.canStop })}
      </div>`)}
    ${panel('İş emri ve üretim', order ? `<p>${esc([orderTitle, order.name].filter(Boolean).join(' · '))}</p>
      ${stats([['Tamamlanan çevrim', `${order.completed} / ${order.target}`]])}
      <progress class="tablet-progress" aria-label="Tamamlanan çevrim" max="${order.target}" value="${order.completed}"></progress>`
      : blank('MES’te aktif iş emri bekleniyor.'))}
    ${resolve}
    ${panel('Son çevrim kayıtları', records ? `<div class="tablet-list">${records}</div>` : blank('Tamamlanmış cihaz çevrimi bekleniyor.'), true)}
  </div>`;
}

function coating(state) {
  const data = state.coating;
  const rows = data.records.slice(0, 12).map(row => `<div class="tablet-row"><div><strong>${esc(row.batch)}</strong><span>Tank ${esc(row.tank)} · Kimyasal lotu ${esc(row.chemical)}</span></div><span>${row.quantity} adet · ${row.drying} dk</span>${pill(row.outcome === 'good' ? 'Uygun' : 'Red')}</div>`).join('');
  return `${workRef(state)}<div class="content-grid tablet-grid">
    ${panel('Kaplama ve kurutma kontrolü', actionForm('coat', `<div class="tablet-fields">
      ${field('Kaplama partisi', 'batch')}${field('Tank kodu', 'tank')}${field('Kimyasal lotu', 'chemical')}
      ${field('Ölçülen konsantrasyon', 'concentration', 'number', 'min="0" step="any"')}
      ${field('Ölçülen kalınlık', 'thickness', 'number', 'min="0" step="any"')}
      ${field('Kurutma süresi (dk)', 'drying', 'number', 'min="0" step="any"')}
      ${field('Parça adedi', 'quantity', 'number', 'min="1" step="1"')}
      <label>Görsel kontrol<select name="outcome" required>${options(goodOrReject)}</select></label>
      </div>`, 'Kaplama kontrolünü kaydet', { primary: true }))}
    ${panel('Kaplama ilerlemesi', `${stats([['Uygun parça', `${data.total} / ${data.target}`]])}<progress class="tablet-progress" aria-label="Kaplama ilerlemesi" max="${data.target}" value="${data.total}"></progress>${rows ? `<div class="tablet-list">${rows}</div>` : blank('Henüz parti kaydı yok.')}`)}
  </div>`;
}

function conveyor(state) {
  const handoff = state.boxes.filter(box => box.stage === 'handoff');
  const transit = state.boxes.filter(box => box.stage === 'transit');
  const exits = state.boxes.filter(box => ['exited', 'packed'].includes(box.stage));
  const log = exits.map(box => `<div class="tablet-row"><div><strong>${esc(box.id)}</strong>${colorMark(box.color)}</div><span>${esc(box.measurement)}</span>${pill('Çıkış doğrulandı', 'green')}</div>`).join('');
  return `${workRef(state)}<div class="content-grid tablet-grid">
    ${panel('Hat kuyruğu', stats([['Teslim bekliyor', handoff.length], ['Hat üzerinde', transit.length], ['Doğrulanan çıkış', exits.length]]), true)}
    ${panel('Kutu ve ölçüm eşleştirme', handoff.length ? actionForm('match', `<div class="tablet-fields">
      <label>Teslim edilen kutu<select name="box" required>${boxOptions(handoff)}</select></label>
      <label>Hat ölçüm kimliği<input name="measurement" maxlength="60" required></label></div>`, 'Hat girişini eşleştir', { primary: true }) : blank('Eşleşecek kutu bekleniyor.'))}
    ${panel('Hat çıkışını doğrula', transit.length ? actionForm('exit', `<label>Hat üzerindeki kutu<select name="box" required>${boxOptions(transit)}</select></label>`, 'Çıkışı doğrula', { primary: true }) : blank('Hat üzerinde kutu yok.'))}
    ${panel('Hız ve sensör kontrolü', `${state.conveyorCheck ? stats([['Son gözlenen hız', state.conveyorCheck.speed], ['Sensör', 'Kontrol edildi'], ['Acil durdurma', 'Kontrol edildi']]) : ''}${actionForm('check',
      `${field('Gözlenen hız', 'speed', 'number', 'min="0" step="any"')}${checkField('Sensör temizliği kontrol edildi', 'sensor')}${checkField('Acil durdurma kontrolü tamamlandı', 'stop')}`, 'Kontrolü kaydet')}`)}
    ${panel('Son doğrulamalar', log ? `<div class="tablet-list">${log}</div>` : blank('Doğrulanan çıkış bekleniyor.'), true)}
  </div>`;
}

function packing(state) {
  const order = state.orders[0];
  const boxes = readyToPack(state);
  const packed = packedTotal(state);
  const stage = state.carton.stage;
  const stageLabel = { open: 'Açık', parked: 'Ayrıldı', sealed: 'Kapatıldı' }[stage];
  const cartonRows = colorEntries.map(([color, label]) => [label, `${state.packed[color]} / ${state.goals[color]}`]);
  const cartonActions = stage === 'parked' ? `<p class="tablet-muted">${esc(state.carton.reason)}</p>${actionForm('resume', '', 'Paketlemeye devam et', { primary: true })}` :
    stage === 'sealed' ? blank('Müşteri kolisi tamamlandı.') : `<div class="tablet-actions">${actionForm('seal', '', 'Koliyi tamamla', { primary: true, disabled: packed !== order.qty })}</div>
      ${packed < order.qty ? actionForm('park', '<label>Eksik koli nedeni<input name="reason" maxlength="240" required></label>', 'Eksik koliyi ayır') : ''}`;
  return `${workRef(state)}<div class="content-grid tablet-grid">
    ${panel('Müşteri kolisi', `<div class="tablet-row"><div><strong>${esc(order.customer)}</strong><span class="tablet-muted">${packed} / ${order.qty} kutu</span></div>${pill(stageLabel, stage === 'sealed' ? 'green' : 'amber')}</div>
      <progress class="tablet-progress" aria-label="Koli ilerlemesi" max="${order.qty}" value="${packed}"></progress>${stats(cartonRows)}${cartonActions}`)}
    ${panel('Paketlemeye hazır kutular', `<p class="tablet-muted">Çıkışı doğrulanan sağlam kutular.</p>${boxes.length && stage === 'open' ?
      actionForm('pack', `<div class="tablet-fields"><label>Koliye eklenecek kutu<select name="box" required>${boxOptions(boxes)}</select></label>
      ${field('Kutu boyutu', 'size')}${field('Sayılan kutu', 'count', 'number', 'min="1" max="1" value="1"')}
      ${field('Etiket kodu', 'label')}${field('Tartılan ağırlık (g)', 'weight', 'number', 'min="0.01" step="any"')}
      </div>${checkField('Koruyucu malzeme yerleştirildi', 'protected')}`, 'Kutuyu koliye ekle', { primary: true }) :
      blank(stage === 'open' ? 'Yeni kutu bekleniyor.' : 'Koliye ekleme için açık koli gerekiyor.')}`)}
  </div>`;
}

function technician(state) {
  const rows = state.faults.map(fault => {
    const idField = `<input type="hidden" name="fault" value="${esc(fault.id)}">`;
    let controls = '';
    if (fault.status === 'open') controls = actionForm('accept', idField, 'Arızayı kabul et', { primary: true });
    if (fault.status === 'accepted') controls = `<div class="tablet-fields tablet-fault-actions">${actionForm('reply', `${idField}<label>Teknik yanıt<textarea name="reply" rows="2" maxlength="240" required></textarea></label>`, 'Yanıtı kaydet', { primary: true })}${actionForm('resolve', `${idField}<div class="tablet-fields">
      ${field('Arıza türü', 'category')}${field('Yedek parça durumu', 'parts')}${field('Duruş süresi (dk)', 'downtime', 'number', 'min="0" step="1"')}
      <label>Sonuç<select name="outcome" required>${options([['repaired','Onarıldı'],['waiting','Bekliyor']])}</select></label></div>
      <label>Müdahale<textarea name="intervention" rows="2" maxlength="240" required></textarea></label>
      <label class="tablet-inline-check"><input name="tested" type="checkbox">Test tamamlandı</label>`, 'Müdahaleyi kaydet')}</div>`;
    return `<article class="tablet-record"><div class="tablet-row"><div><strong>${esc(fault.id)}</strong><span class="tablet-muted">${esc(fault.station)}</span></div>${pill(FAULT_STATUS[fault.status], fault.status === 'resolved' ? 'green' : 'amber')}</div>
      <p><strong>${fault.kind === 'help' ? 'Yardım çağrısı' : 'Arıza'}</strong> · ${esc(fault.text)}</p>${fault.reply ? `<p class="tablet-muted">Teknik yanıt · ${esc(fault.reply)}</p>` : ''}${fault.result ? `<p>${esc(fault.result.category)} · ${fault.result.downtime} dk · ${fault.result.outcome === 'repaired' ? 'Onarıldı' : 'Bekliyor'} · ${esc(fault.result.intervention)}</p>` : ''}${controls}</article>`;
  }).join('');
  return `<div class="content-grid tablet-grid">${panel('Arıza kayıtları', `<div class="tablet-list">${rows}</div>`, true)}</div>`;
}

function materialRequests(state) {
  return state.requests.map(row => `<div class="tablet-row"><div><strong>${esc(row.id)} · ${COLORS[row.color]} · ${row.quantity} adet</strong><span class="tablet-muted">${esc(row.reason)}</span></div>${pill(row.received ? 'Teslim alındı' : 'Bekliyor', row.received ? 'green' : 'amber')}</div>`).join('');
}

function quality(state) {
  const boxes = state.boxes.filter(box => box.stage === 'exited');
  const log = state.qualityLog.map(row => `<div class="tablet-row"><div><strong>${esc(row.box)}</strong><span class="tablet-muted">${esc(row.reason)}</span></div><span>${OUTCOMES[row.previous]} → ${OUTCOMES[row.outcome]}</span></div>`).join('');
  return `${workRef(state)}<div class="content-grid tablet-grid">
    ${panel('Çıkışı doğrulanan kutular', boxes.length ? `<div class="tablet-list">${boxes.map(box => `<div class="tablet-row"><div><strong>${esc(box.id)}</strong>${colorMark(box.color)}</div>${pill(OUTCOMES[box.outcome], box.outcome === 'good' ? 'green' : 'amber')}</div>`).join('')}</div>` : blank('Kontrol edilecek kutu bekleniyor.'))}
    ${panel('Kalite sınıfı düzeltme', boxes.length ? actionForm('classify', `<div class="tablet-fields">
      <label>İncelenen kutu<select name="box" required>${boxOptions(boxes)}</select></label>
      <label>Kalite kararı<select name="outcome" required>${options([['good','Uygun'],['scrap','Red'],['allowed','İzinli']])}</select></label>
      ${field('Ölçüm aleti', 'instrument')}${field('Ölçüm', 'measured', 'number', 'min="0" step="any"')}${field('Tolerans', 'tolerance')}
      <label>Görsel kontrol<select name="visual" required>${options(goodOrReject)}</select></label></div>
      <label>Düzeltme gerekçesi<textarea name="reason" rows="2" maxlength="240" required></textarea></label>`, 'Kalite sonucunu güncelle', { primary: true }) : blank('Yeni kutu bekleniyor.'))}
    ${panel('Düzeltme geçmişi', log ? `<div class="tablet-list">${log}</div>` : blank('Henüz kalite düzeltmesi yok.'), true)}
  </div>`;
}

function materials(state) {
  const rows = state.dispatches.slice(0, 12).map(row => `<div class="tablet-row"><strong>${esc(row.barcode)}</strong><span>${esc(row.location)} · ${row.quantity} kit</span></div>`).join('');
  const shipped = state.dispatches.reduce((total, row) => total + row.quantity, 0);
  return `<div class="content-grid tablet-grid">
    ${panel('Hazır bant stoku', stats(colorEntries.map(([color, label]) => [label, `${state.materials[color]} adet`])))}
    ${panel('Malzeme talebi', actionForm('request', `<div class="tablet-fields">
      <label>Talep edilen renk<select name="color" required>${options(colorEntries)}</select></label>
      <label>Talep adedi<input name="quantity" type="number" inputmode="numeric" min="1" max="10000" required></label></div>
      <label>Talep nedeni<textarea name="reason" rows="2" maxlength="240" required></textarea></label>`, 'Talep oluştur', { primary: true }))}
    ${panel('Stok ve sevk kaydı', actionForm('dispatch', `<div class="tablet-fields">
      ${field('Barkod', 'barcode')}${field('Lokasyon', 'location')}
      <label>Bant rengi<select name="color" required>${options(colorEntries)}</select></label>${field('Kit miktarı', 'quantity', 'number', 'min="1" step="1"')}
      </div>${checkField('Malzeme sevke uygun', 'condition')}`, 'Sevki kaydet', { primary: true }))}
    ${panel('Son sevkler', `${stats([['Sevk edilen kit', shipped]])}${rows ? `<div class="tablet-list">${rows}</div>` : blank('Henüz sevk kaydı yok.')}`)}
    ${panel('Malzeme talepleri', `<div class="tablet-list">${materialRequests(state)}</div>`, true)}
  </div>`;
}

const areas = {
  bantlama: { title: 'Bantlama', subtitle: 'Kutu hazırlığı, bantlama adımları ve konveyöre teslim', render: taping },
  paketleme: { title: 'Paketleme', subtitle: 'Doğrulanmış kutular, renk hedefleri ve müşteri kolisi', render: packing },
  giyotin: { title: 'Giyotin', subtitle: 'Renge göre kesim kaydı ve bantlamaya hazır çiftler', render: cutting },
  kaplama: { title: 'Kaplama', subtitle: 'Kimyasal lotu, tank, ölçümler ve kurutma kontrolü', render: coating },
  konveyor: { title: 'Konveyör Operatörü', subtitle: 'Teslim edilen kutuyu hat ölçümüyle eşleştir ve çıkışı doğrula', render: conveyor },
  tekniker: { title: 'Tekniker', subtitle: 'İstasyon arızalarını kabul et, yanıtla ve tamamla', render: technician },
  kalite: { title: 'Kalite Kontrol', subtitle: 'Çıkışı doğrulanmış kutuların kalite sınıfları ve düzeltmeler', render: quality },
  malzeme: { title: 'Malzeme', subtitle: 'Bant stoku ve istasyondan gelen malzeme talepleri', render: materials },
};

function publishedTemplate(state) {
  const template = state.template;
  if (!template) return '';
  const { design, version } = template;
  const values = state.templateRecord?.version === version ? state.templateRecord.values : [];
  const fields = design.steps.map((step, index) => {
    const name = `step-${index}`;
    const value = values[index];
    const required = step.required ? ' required' : '';
    if (step.kind === 'check') return `<label class="tablet-inline-check"><input type="checkbox" name="${name}"${value ? ' checked' : ''}${required}>${esc(step.label)}</label>`;
    const control = step.kind === 'choice'
      ? `<select name="${name}"${required}><option value="">Seçin</option>${step.options.map(option => `<option${option === value ? ' selected' : ''}>${esc(option)}</option>`).join('')}</select>`
      : `<input name="${name}" type="${step.kind === 'number' ? 'number' : 'text'}" ${step.kind === 'number' ? 'step="any" min="0"' : 'maxlength="240"'} value="${esc(value ?? '')}"${required}>`;
    return `<label>${esc(step.label)}${control}</label>`;
  }).join('');
  const result = state.templateRecord?.version === version ? state.templateRecord.result : '';
  const results = design.result_options.length ? `<label>Şablon sonucu<select name="result" required><option value="">Seçin</option>${design.result_options.map(option =>
    `<option${option === result ? ' selected' : ''}>${esc(option)}</option>`).join('')}</select></label>` : '';
  const checkForm = actionForm('template-record', `<input type="hidden" name="version" value="${version}">${fields}${results}`, 'Kontrol listesini kaydet');
  const defaults = { instructions: 'Operatör talimatı', steps: 'Kontrol listesi', order: 'İş emri', wip: 'WIP', status: 'Vardiya durumu',
    material: 'Malzeme', progress: 'İlerleme', extra: 'Ek bilgi', before: 'İşe başlamadan önce', after: 'İş bitiminde' };
  const detail = {
    instructions: design.instructions, before: design.before, after: design.after,
    order: state.protocol4 ? (state.protocol4.order?.id ?? 'Aktif iş emri bekleniyor') : orderLabel(state.orders[0]), status: state.shift?.operator ?? 'Vardiya kapalı',
    wip: state.wip?.map(area => `${area.name} ${area.occupied} / ${area.capacity}`).join(' · '),
    material: state.materials && colorEntries.map(([id, name]) => `${name} ${state.materials[id]}`).join(' · '),
    timer: design.features.timer ? (state.shift ? `Vardiya başlangıcı ${new Date(state.shift.startedAt).toLocaleTimeString('tr-TR')}` : 'Vardiya kapalı') : '',
    result: result || 'Sonuç bekleniyor', actions: 'İşlemler vardiya açıkken kullanılabilir.',
    downtime: state.faults ? `${state.faults.filter(item => item.status !== 'resolved').length} açık bildirim` : '',
    progress: state.protocol4 ? (state.protocol4.order ? `${state.protocol4.order.completed} / ${state.protocol4.order.target} çevrim` : '') :
      state.coating ? `${state.coating.total} / ${state.coating.target} parça` :
      state.packed ? `${packedTotal(state)} / ${state.orders[0].qty} kutu` : `İş emri hedefi ${state.orders[0].qty} adet`,
    extra: design.sections.map(item => `${item.title} · ${item.body}`).join('\n'),
  };
  const cards = design.cards.filter(card => card.visible);
  const hasSteps = cards.some(card => card.kind === 'steps');
  return `<section class="panel station-template"><div class="panel-head"><h3>${esc(design.title)}</h3>${pill(`Şablon sürümü ${version}`)}</div>
    ${design.instructions && !cards.some(card => card.kind === 'instructions') ? `<p>${esc(design.instructions)}</p>` : ''}
    <div class="station-template-grid layout-${design.layout}">${cards.map(card => `<section class="tablet-record size-${card.size}"><h4>${esc(card.title || defaults[card.kind] || card.kind)}</h4>
      ${card.body ? `<p>${esc(card.body)}</p>` : ''}${card.kind === 'steps' ? checkForm : detail[card.kind] ? `<p>${esc(detail[card.kind])}</p>` : ''}</section>`).join('')}
    ${hasSteps ? '' : `<section class="tablet-record size-full"><h4>Kontrol listesi</h4>${checkForm}</section>`}</div></section>`;
}

function shiftControls(state) {
  if (!state.shift) return panel('Vardiya', actionForm('shift-start', field('Operatör adı', 'operator', 'text', 'maxlength="80"'), 'Vardiyayı başlat', { primary: true }), true);
  return panel('Vardiya', `<div class="tablet-row"><strong>${esc(state.shift.operator)}</strong>${pill('Vardiya açık', 'green')}
    ${actionForm('shift-end', '', 'Vardiyayı bitir', { disabled: Boolean(state.activeBox) })}</div>`, true);
}

function assistance() {
  return `<div class="content-grid tablet-grid">
    ${panel('Arıza bildirimi', actionForm('fault', '<label>Arıza açıklaması<textarea name="description" rows="2" maxlength="240" required></textarea></label>', 'Arızayı bildir'))}
    ${panel('Yardım çağrısı', actionForm('help', '<label>Yardım nedeni<textarea name="description" rows="2" maxlength="240" required></textarea></label>', 'Yardım çağır'))}
  </div>`;
}

function renderTabletStation(station, { readOnly, state }) {
  const area = areas[station];
  return `<section class="tablet-station" data-current-station="${station}" aria-labelledby="tablet-station-title">
    <header class="tablet-station-heading"><h2 id="tablet-station-title">${area.title}</h2><p class="subtitle">${state.protocol4 ? 'İş emri ve Nano çevrim kontrolü' : area.subtitle}</p></header>
    <fieldset class="station-controls"${readOnly ? ' disabled' : ''}>${shiftControls(state)}</fieldset>
    ${state.protocol4 ? `<p class="tablet-giyotin-status" data-giyotin-status role="status" aria-atomic="true">${giyotinModes[state.protocol4.mode]}</p>
      <fieldset class="station-controls" data-giyotin-panel${readOnly ? ' disabled' : ''}>${area.render(state)}</fieldset>` : ''}
    <fieldset class="station-controls station-work"${readOnly || !state.shift ? ' disabled' : ''}>
      ${state.protocol4 ? '' : area.render(state)}${publishedTemplate(state)}${assistance()}
    </fieldset>
  </section>`;
}

function monitoringSummary(data) {
  const { kpis } = SAMPLE_MONITOR_DATA.lineStatus;
  const actual = packedTotal(data) + data.boxes.filter(box => box.stage === 'exited' && box.outcome === 'good').length;
  const activeFaults = data.faults.filter(fault => fault.status !== 'resolved' && fault.kind === 'fault');
  return panel('Hat özeti', `${stats([['Örnek OEE', `%${kpis.oee}`], ['Üretim hedefi', data.orders[0].qty], ['Doğrulanan sağlam', actual], ['Aktif arıza', activeFaults.length]])}
    ${activeFaults.length ? `<ul class="monitor-faults">${activeFaults.slice(0, 5).map(item => `<li>${esc(item.station)} · ${esc(item.text)}</li>`).join('')}</ul>` : ''}`, true);
}

function monitoringRecords(data) {
  const recent = data.boxes.filter(box => ['exited', 'packed', 'rejected'].includes(box.stage))
    .sort((a, b) => (b.completedAt ?? 0) - (a.completedAt ?? 0)).slice(0, 5);
  const rows = recent.map(box => `<div class="tablet-row"><strong>${esc(box.id)}</strong>${colorMark(box.color)}${pill(OUTCOMES[box.outcome], box.outcome === 'good' ? 'green' : 'amber')}</div>`).join('');
  const queue = data.orders.map(order => `<div class="tablet-row"><strong>${esc(orderLabel(order))}</strong><span>${order.qty} kutu</span>${pill(order.status === 'active' ? 'Aktif' : 'Sırada')}</div>`).join('');
  return `<div class="content-grid tablet-grid">${panel('Son 5 ürün · Kalite', `<div class="tablet-list">${rows}</div>`)}
    ${panel('İş emri kuyruğu', `<div class="tablet-list">${queue}</div>`)}</div>`;
}

async function requestData(path, body) {
  const options = { cache: 'no-store' };
  if (body) Object.assign(options, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw Object.assign(new Error(typeof result.detail === 'string' ? result.detail : 'İşlem alanlarını kontrol edin.'), { status: response.status });
  return result;
}

function mountWorkspace(root, readOnly, lockedStation) {
  const initialStation = new URLSearchParams(location.search).get('istasyon');
  let current = readOnly ? (Object.hasOwn(areas, initialStation) ? initialStation : 'bantlama') : lockedStation;
  let data;
  let pending = 0;
  let reading = false;
  let dirty = false;
  let queue = Promise.resolve();
  const path = readOnly ? '/api/workspace/monitoring' : `/api/workspace/tablet/${lockedStation}`;

  root.innerHTML = `${readOnly ? `<div class="monitor-page-nav"><a class="tab-button" href="/">MES Kontrol Paneli</a><a class="tab-button" data-designer-link href="/atolye-onizleme" hidden>Kiosk Tasarımcı</a></div><div id="monitor-summary"></div>` : ''}
    <div class="station-toolbar">${readOnly ? `<label class="station-picker" for="station-select">İstasyon
      <select id="station-select">${Object.entries(areas).map(([id, area]) => `<option value="${id}"${id === current ? ' selected' : ''}>${area.title}</option>`).join('')}</select></label>
      <span class="badge gray">Salt okunur izleme</span>` : ''}<p class="station-sample-note">Örnek veri</p></div>
    <p class="tablet-feedback" role="status" aria-live="polite" tabindex="-1"></p>
    <div id="tablet-container"><p class="station-loading" role="status">İstasyon verisi yükleniyor…</p></div>${readOnly ? '<div id="monitor-records"></div>' : ''}`;
  const outlet = root.querySelector('#tablet-container');
  const feedback = root.querySelector('.tablet-feedback');
  const picker = root.querySelector('#station-select');
  const stationState = () => readOnly ? data?.stations[current] : data;

  function paint() {
    const board = stationState();
    if (!board) return;
    const sampleNote = root.querySelector('.station-sample-note');
    sampleNote.hidden = Boolean(board.protocol4) && !readOnly;
    outlet.innerHTML = renderTabletStation(current, { readOnly, state: board });
    if (readOnly) {
      root.querySelector('#monitor-summary').innerHTML = monitoringSummary(data);
      root.querySelector('#monitor-records').innerHTML = monitoringRecords(data);
      root.querySelector('[data-designer-link]').hidden = !['admin', 'engineer'].includes(data.role);
    }
  }

  function notify(message, tone) {
    feedback.dataset.tone = tone;
    feedback.textContent = message;
  }

  async function refresh() {
    if (reading || pending || (dirty && !stationState()?.protocol4)) return;
    reading = true;
    try {
      const next = await requestData(path);
      const nextBoard = readOnly ? next.stations[current] : next;
      const protocol = nextBoard?.protocol4;
      const deviceChanged = protocol && JSON.stringify(protocol) !== JSON.stringify(stationState()?.protocol4);
      if (!pending && !dirty && (!data || next.revision > data.revision)) {
        data = next;
        paint();
      } else if (!pending && deviceChanged) {
        const status = outlet.querySelector('[data-giyotin-status]');
        const panel = outlet.querySelector('[data-giyotin-panel]');
        if (status.textContent !== giyotinModes[protocol.mode]) status.textContent = giyotinModes[protocol.mode];
        const focused = panel.contains(document.activeElement) ? document.activeElement : null;
        const task = focused?.closest('form')?.dataset.task;
        if (task === 'giyotin-reconcile' && protocol.review?.id === focused.form.elements.reviewId.value) return;
        if (readOnly) data.stations[current].protocol4 = protocol;
        else data.protocol4 = protocol;
        panel.innerHTML = protocolCutting(protocol);
        if (task) panel.querySelector(`[data-task="${task}"] button:enabled`)?.focus({ preventScroll: true });
      }
    } catch (error) {
      if (error.status === 401) location.replace(readOnly ? '/mes-oturum' : '/tablet-eslestir');
      else if (!data) notify(error.message, 'error');
    } finally {
      reading = false;
    }
  }

  picker?.addEventListener('change', () => {
    current = picker.value;
    const url = new URL(location.href);
    url.searchParams.set('istasyon', current);
    history.replaceState(null, '', url);
    paint();
  });

  function updateTapingControls() {
    const form = outlet.querySelector('[data-task="finish"]');
    const box = stationState()?.activeBox;
    if (!form || !box || box.paused) return;
    const good = form.elements.outcome.value === 'good';
    form.querySelector('[data-outcome-reason]').hidden = good;
    form.elements.reason.disabled = good;
    form.elements.reason.required = !good;
    form.querySelector('[data-outcome-length]').hidden = !good;
    form.elements.length.disabled = !good;
    form.querySelector('button').disabled = good && !box.steps.every(Boolean);
  }

  function submit(action, fields, form) {
    const button = form?.querySelector('button');
    if (button?.disabled) return;
    if (button) button.disabled = true;
    pending += 1;
    queue = queue.then(async () => {
      try {
        const next = await requestData(`${path}/actions`, { action, fields });
        data = next.board;
        if (action === 'step') updateTapingControls();
        else {
          dirty = false;
          paint();
          notify(next.message, 'success');
        }
      } catch (error) {
        notify(error.message, 'error');
        if (action === 'step') { dirty = false; paint(); }
        if (button?.isConnected) button.disabled = false;
      } finally {
        pending -= 1;
      }
    });
  }

  if (!readOnly) {
    outlet.addEventListener('input', () => { dirty = true; });
    outlet.addEventListener('change', event => {
      const input = event.target;
      if (input.matches('[name="outcome"]') && current === 'bantlama') updateTapingControls();
      if (input.matches('[data-taping-step]')) submit('step', { index: Number(input.dataset.tapingStep), checked: input.checked, activeBoxId: stationState().activeBox.id });
    });
    outlet.addEventListener('submit', event => {
      const form = event.target.closest('form[data-task]');
      if (!form) return;
      event.preventDefault();
      const fields = Object.fromEntries(new FormData(form));
      if (current === 'bantlama' && stationState()?.activeBox) fields.activeBoxId = stationState().activeBox.id;
      submit(form.dataset.task, fields, form);
    });
  } else {
    outlet.addEventListener('submit', event => event.preventDefault());
  }

  setInterval(() => {
    const clock = outlet.querySelector('[data-taping-clock]');
    const box = stationState()?.activeBox;
    if (clock && box) clock.textContent = duration(elapsedTaping(box, Date.now()));
  }, 500);
  setInterval(refresh, 3000);
  void refresh();
}

const stationRoot = document.getElementById('station-workspace');
if (stationRoot) mountWorkspace(stationRoot, document.body.dataset.mode === 'monitor', document.body.dataset.station);

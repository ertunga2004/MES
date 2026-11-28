/**
 * Atölye Önizleme - Paylaşılan Çekirdek Render Modülü
 * Kaynak: mes-modular/mes/web/lib/kiosk-view.mjs + kiosk-layout.mjs
 * Bu modül canlı veri kullanmaz, MQTT veya fiziksel cihaz komutu göndermez.
 */

// ============================================================
// Yardımcı fonksiyonlar (kiosk-view.mjs'den uyarlanmış)
// ============================================================

export function esc(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function duration(ms) {
  if (!ms || ms < 0) return '00:00';
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

export function timerValues(timer, now) {
  const { activeMs = 0, waitingMs = 0, since, paused } = timer || {};
  const elapsed = since != null ? Math.max(0, now - since) : 0;
  return {
    activeMs: activeMs + (paused ? 0 : elapsed),
    waitingMs: waitingMs + (paused ? elapsed : 0)
  };
}

export const stepTypes = {
  check: 'Onay kutusu',
  text: 'Metin girişi',
  number: 'Sayı girişi',
  choice: 'Listeden seçim'
};

// ============================================================
// kiosk-layout.mjs sabitleri
// ============================================================

export const layouts = {
  single: 'Tek sütun',
  double: 'İki sütun',
  sidebar: 'Ana panel + yan panel'
};

export const sizes = {
  small: 'Küçük',
  medium: 'Orta',
  large: 'Büyük',
  full: 'Tam genişlik'
};

export const sources = {
  fixed: 'Sabit içerik',
  station: 'Bağlı istasyon',
  order: 'Seçili iş emri'
};

export const cardTypes = {
  order: ['İş emri', 1, ['order']],
  instructions: ['Operatör talimatı', 0, ['fixed', 'order']],
  steps: ['Akış / kontrol adımları', 2, ['fixed']],
  timer: ['Süre sayacı', 0, ['fixed']],
  progress: ['Üretim sayacı', 0, ['fixed', 'order']],
  result: ['İşin sonucu', 1, ['fixed']],
  status: ['İstasyon durumu', 0, ['station']],
  wip: ['WIP bekleme alanları', 2, ['station']],
  downtime: ['Duruş / hata bildirimi', 1, ['fixed']],
  actions: ['İşlem butonları', 2, ['fixed']],
  material: ['Malzeme listesi', 1, ['station', 'fixed']],
  before: ['İşe başlamadan önce', 0, ['fixed']],
  after: ['İş bitiminde', 0, ['fixed']],
  extra: ['Ek bölümler', 1, ['fixed']]
};

export const templates = {
  process: { title: 'İşlem Takip', hint: 'Kesme, bantlama veya montaj', cards: ['order', 'instructions', 'steps', 'timer', 'wip'], layout: 'sidebar', features: { timer: true, progress: null, result: null } },
  quality: { title: 'Kalite Kontrol', hint: 'Kontrol listesi, ölçüm ve sonuç', cards: ['order', 'steps', 'result', 'instructions', 'wip'], layout: 'double', features: { timer: false, progress: null, result: ['Uygun', 'Yeniden işlem', 'Uygunsuz'] } },
  packing: { title: 'Paketleme', hint: 'Hedef, gerçekleşen ve paket sonucu', cards: ['order', 'progress', 'steps', 'result', 'wip'], layout: 'sidebar', features: { timer: false, progress: { target: 1, unit: 'adet' }, result: ['Tamamlandı', 'Eksik'] } },
  material: { title: 'Malzeme', hint: 'İhtiyaç, mevcut miktar ve bildirim', cards: ['order', 'material', 'steps', 'instructions', 'wip'], layout: 'double', features: { timer: false, progress: null, result: null } },
  status: { title: 'İstasyon Durumu', hint: 'Çalışma, bekleme ve duruş kaydı', cards: ['status', 'order', 'timer', 'downtime', 'steps', 'wip'], layout: 'single', features: { timer: true, progress: null, result: null } }
};

// ============================================================
// Kart yardımcıları
// ============================================================

export function makeCard(kind) {
  const [title, min, available] = cardTypes[kind];
  return { kind, size: Object.keys(sizes)[Math.max(min, 1)], source: available[0], visible: true, title, body: '' };
}

export function applyTemplate(design, key) {
  const template = templates[key];
  const cards = [...template.cards, 'before', 'after', 'extra', 'actions'].map(makeCard);
  const progress = cards.find(card => card.kind === 'progress');
  if (progress) progress.source = 'order';
  return { ...design, template: key, layout: template.layout, cards, features: structuredClone(template.features) };
}

// ============================================================
// Render fonksiyonları (kiosk-view.mjs'den uyarlanmış)
// ============================================================

function note(title, body) {
  return body ? `<section class="kiosk-note"><h2>${esc(title)}</h2><p>${esc(body)}</p></section>` : '';
}

function text(value) {
  return value ? `<p class="kiosk-card-copy">${esc(value)}</p>` : '';
}

export function kioskHeading(design) {
  return `<header class="kiosk-heading"><h1>${esc(design.title || 'İstasyon adı')}</h1>${design.instructions && !design.cards?.length ? `<p>${esc(design.instructions)}</p>` : ''}</header>`;
}

export function kioskSteps(steps, values = []) {
  if (!steps.length) return '<p class="muted">Henüz adım eklenmedi.</p>';
  return `<ol class="kiosk-steps">${steps.map((step, index) => {
    const name = `step-${index}`, value = values[index], label = esc(step.label || 'Adım adı');
    const required = step.required ? ' <small>Zorunlu</small>' : '';
    if (step.kind === 'check') return `<li><label class="kiosk-check"><input type="checkbox" name="${name}" ${value ? 'checked' : ''} disabled><span>${label}${required}</span></label></li>`;
    const field = step.kind === 'choice'
      ? `<select name="${name}" disabled><option value="">Seçiniz</option>${step.options.map(option => `<option value="${esc(option)}" ${option === value ? 'selected' : ''}>${esc(option)}</option>`).join('')}</select>`
      : `<input name="${name}" type="${step.kind === 'number' ? 'number' : 'text'}" ${step.kind === 'number' ? 'step="any"' : 'maxlength="500"'} value="${esc(value ?? '')}" disabled>`;
    return `<li><label><span>${label}${required}</span>${field}</label></li>`;
  }).join('')}</ol>`;
}

export function kioskWork(design, run, controls = false, board = {}) {
  const { timer, progress, result } = design.features;
  const quantity = run?.quantity ?? 0;
  const time = timerValues(run?.timer, run?.timer?.since ?? 0);
  const elapsed = timer ? `<div class="kiosk-clock-values"><span>Aktif süre <strong data-kiosk-active>${duration(time.activeMs)}</strong></span><span>Bekleme süresi <strong data-kiosk-waiting>${duration(time.waitingMs)}</strong></span></div>` : '';
  const counter = progress ? `<p data-kiosk-quantity>${quantity} / ${progress.target ?? '—'} ${esc(progress.unit || 'adet')}</p><progress aria-label="İşin ilerlemesi" max="${progress.target || 1}" value="${quantity}"></progress>` : '';
  const outcome = result ? `<label>Sonucu seç <small>Zorunlu</small><select name="result" disabled><option value="">Seçiniz</option>${result.map(option => `<option value="${esc(option)}" ${run?.result === option ? 'selected' : ''}>${esc(option)}</option>`).join('')}</select></label>` : '';
  const order = board.orders?.find(item => item.id === run?.orderRef);
  const assigned = board.orders?.length ? `<ul>${board.orders.map(item => `<li>${esc(item.id)} · ${esc(item.customer)} · ${item.target} adet</li>`).join('')}</ul>` : text('Atanmış iş emri bulunmuyor.');
  const renderers = {
    before: () => text(design.before),
    after: () => text(design.after),
    instructions: () => text(design.instructions),
    steps: () => kioskSteps(design.steps, run?.values),
    timer: () => elapsed,
    progress: () => counter,
    result: () => outcome,
    extra: () => design.sections.map(section => note(section.title, section.body)).join(''),
    order: () => order ? text(`${order.id} · ${order.customer} · Hedef ${order.target} adet`) : assigned,
    status: () => text(`${board.station?.name || design.station || 'İstasyon'} · ${run ? (run.timer?.paused ? 'Duraklatıldı' : 'Çalışıyor') : board.occupied ? 'İstasyon meşgul' : board.shift ? 'Hazır' : 'Vardiya kapalı'}`),
    wip: () => board.wipAreas?.length ? `<ul>${board.wipAreas.map(area => `<li>${esc(area.title)} · ${area.occupied} / ${area.capacity}</li>`).join('')}</ul>` : text('Seçili WIP bekleme alanı yok.'),
    material: () => '',
    downtime: () => '',
    actions: () => '<div class="kiosk-actions"><button class="button" value="save" disabled>İlerlemeyi kaydet</button><button class="button primary" value="finish" disabled>İşi tamamla</button></div>'
  };
  const defaults = [['before', 'İşe başlamadan önce'], ['timer', 'Süre sayacı'], ['progress', 'Hedef ve ilerleme'], ['steps', 'Akış adımları'], ['after', 'İş bitiminde'], ['extra', 'Ek bölümler'], ['result', 'İşin sonucu']];
  const configured = design.cards?.length;
  const cards = configured ? design.cards : defaults.map(([kind, title]) => ({ kind, title, visible: true, size: 'full' }));
  return `<div class="kiosk-card-grid layout-${esc(design.layout || 'single')}">${cards.filter(card => card.visible).map(card => {
    const content = (renderers[card.kind] ? renderers[card.kind](card) : '') + text(card.body);
    if (!content && (!configured || ['before', 'after', 'extra', 'instructions', 'timer', 'progress', 'result'].includes(card.kind))) return '';
    return `<section class="kiosk-feature-output kiosk-card size-${esc(card.size)}"><h2>${esc(card.title || defaults.find(row => row[0] === card.kind)?.[1] || 'Bilgi')}</h2>${content || text('Bu kart için veri yok.')}</section>`;
  }).join('')}</div>`;
}

export function readKioskValues(form, steps, previous = []) {
  return steps.map((step, index) => {
    const input = form.elements[`step-${index}`];
    if (!input) return previous[index];
    if (step.kind === 'check') return input.checked;
    if (step.kind === 'number') return input.value === '' ? null : input.valueAsNumber;
    return input.value;
  });
}

// ============================================================
// KioskRenderer sınıfı (kolay erişim için)
// ============================================================

export class KioskRenderer {
  static esc = esc;
  static duration = duration;
  static timerValues = timerValues;
  static stepTypes = stepTypes;
  static layouts = layouts;
  static sizes = sizes;
  static sources = sources;
  static cardTypes = cardTypes;
  static templates = templates;
  static makeCard = makeCard;
  static applyTemplate = applyTemplate;
  static heading = kioskHeading;
  static steps = kioskSteps;
  static work = kioskWork;
  static readValues = readKioskValues;
}
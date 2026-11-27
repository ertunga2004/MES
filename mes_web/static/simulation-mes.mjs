import { card, depot, request, stage, stateLabels } from './anylogic-panel.mjs?v=4';
import { esc } from './atolye-onizleme-core.js?v=5';

const api = '/api/workspace/anylogic';
const format = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const percentage = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1 });
const clock = new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' });
const amount = value => Number.isFinite(value) ? format.format(value) : '—';
const unit = (value, suffix) => Number.isFinite(value) ? `${amount(value)} ${suffix}` : '—';
const colors = ['red', 'blue', 'yellow'];
const colorNames = { red: 'Kırmızı', blue: 'Mavi', yellow: 'Sarı', kirmizi: 'Kırmızı', mavi: 'Mavi', sari: 'Sarı' };
const speedSuffix = speed => Number.isFinite(speed) ? ` · ${amount(speed)}×` : '';
const controls = '<div class="mes-sim-links"><button type="button" class="tab-button" data-sim-tab="anylogic">AnyLogic kontrollerine git</button><button type="button" class="tab-button" data-sim-tab="digital-twin">Dijital İkizi izle</button></div>';

function cards(...values) {
  return `<div class="plant-kpis">${values.map(([label, value]) => card(label, value)).join('')}</div>`;
}

function panel(title, content, { full = true, status = '' } = {}) {
  const heading = status ? `<h2>${title}</h2>` : `<h3>${title}</h3>`;
  return `<section class="panel${full ? ' panel-span-12' : ''}"><div class="panel-head">${heading}${status}</div>${content}</section>`;
}

function recentOutput(events) {
  const rows = events.flatMap(event => {
    const [kind, box, color] = String(event.message || '').split(';');
    if (kind !== 'DEPOLANDI') return [];
    return [`<tr><td>${esc(unit(event.at, 'sn'))}</td><td>${esc(box || '—')}</td><td>${esc(colorNames[color] || '—')}</td></tr>`];
  }).reverse();
  return `<div class="plant-table-wrap"><table class="plant-table" aria-label="Son depolama hareketleri">
    <thead><tr><th scope="col">Model saati</th><th scope="col">Kutu</th><th scope="col">Renk</th></tr></thead>
    <tbody>${rows.join('') || '<tr><td colspan="3" class="empty-state">Depolama hareketi bekleniyor.</td></tr>'}</tbody>
    </table></div>`;
}

export function renderSimulationSummary(snapshot, tab) {
  const { run, state, speed, target, verdict, metrics = {}, modelTime } = snapshot;
  const { counters = {}, inventory = {}, robot, stations, conveyor, camera } = metrics;
  const { entered, completed, buffer, onConveyor, shipped } = counters;
  const [label, tone] = stateLabels[state] || ['Motor sorgulanıyor', 'idle'];
  const mode = run ? (run.mode === 'TEST' ? 'Excel testi' : 'Sürekli akış') : '—';
  const runLabel = run ? `${mode} ${run.scenario} · ${run.id.slice(0, 8)}${speedSuffix(speed)}` :
    snapshot.detail || 'AnyLogic koşusu bekleniyor.';
  const status = `<span class="plant-led" data-tone="${tone}">${label}</span>`;
  const identity = `<p class="panel-note" data-sim-run>${esc(runLabel)}</p>`;
  const belt = typeof conveyor?.running === 'boolean' ? (conveyor.running ? 'Bant çalışıyor' : 'Bant duruyor') : '—';
  const deposits = `<div class="anylogic-stock">${colors.map(color => depot(color, inventory)).join('')}</div>`;
  const counts = cards(['Model saati', unit(modelTime, 'sn')], ['Hat girişi', unit(entered, 'kutu')],
    ['Depolanan', unit(completed, 'kutu')], ['Ara depo', unit(buffer, 'kutu')],
    ['Konveyör / robot', unit(onConveyor, 'kutu')], ['Sevk edilen', unit(shipped, 'kutu')]);

  if (tab === 'operations') {
    const flow = [stage('Kesme', unit(stations?.cutting, 'kutu')), stage('Kaplama', unit(stations?.coating, 'kutu')),
      stage('Ara depo', unit(buffer, 'kutu')), stage('Konveyör / kamera', camera?.busy ? 'Renk okunuyor' : belt),
      stage('Robot kol', robot?.state === 'IDLE' ? 'Boşta' : robot?.state?.replaceAll('_', ' ') || '—'),
      stage('Renk depoları', unit(completed, 'kutu'))];
    return [
      panel('Anlık üretim özeti', identity + counts, { status }),
      panel('Üretim akışı', `<ol class="plant-flow" style="--stages: 6" aria-label="Simülasyon istasyon sırası" tabindex="0">${flow.join('')}</ol>`),
      panel('Darboğaz ve kayıplar', cards(['Ara depo bekleyen', unit(buffer, 'kutu')],
        ['Bant durumu', belt], ['Robot boşta', unit(robot?.idleSeconds, 'sn')]), { full: false }),
      panel('Operasyonel uyarılar', `<p class="panel-note">${state === 'error' || state === 'unavailable' ? 'AnyLogic verisi alınamadı.' : '—'}</p>`, { full: false }),
      panel('İş emri takibi', cards(['Simülasyon senaryosu', run?.scenario ?? '—'], ['Beklenen', unit(target, 'kutu')],
        ['Depolanan', unit(completed, 'kutu')], ['Model sonucu', verdict || '—'])),
      panel('Renk sayaçları', deposits),
      panel('Komut paneli', controls),
    ].join('');
  }

  if (tab === 'oee') {
    const startedAt = Date.parse(run?.startedAt);
    const rate = modelTime > 0 && Number.isFinite(completed) ? completed * 3600 / modelTime : null;
    const idle = robot?.idleSeconds;
    const utilisation = modelTime > 0 && Number.isFinite(idle) ? Math.max(0, Math.min(1, 1 - idle / modelTime)) : null;
    return [
      panel('OEE özeti', identity + cards(['OEE', '—'], ['Kullanılabilirlik', '—'], ['Performans', '—'], ['Kalite', '—']) +
        '<p class="panel-note">OEE için ideal çevrim süresi, planlı üretim süresi ve kalite sayımı gerekir.</p>', { status }),
      panel('Vardiya bilgileri', cards(['Vardiya', '—'], ['Koşu başlangıcı', Number.isFinite(startedAt) ? clock.format(startedAt) : '—'],
        ['Planlı üretim', '—'], ['İdeal çevrim', '—'], ['Senaryo hedefi', unit(target, 'kutu')])),
      panel('Üretim özeti', counts),
      panel('Ekipman performansı', cards(['Ortalama üretim hızı', unit(rate, 'kutu / model saati')],
        ['Robot boşta', unit(idle, 'sn')], ['Robot çalışma oranı', utilisation === null ? '—' : percentage.format(utilisation)])),
      panel('Arıza ve duruşlar', cards(['Arıza kaydı', '—'], ['Duruş süresi', '—'], ['Bant durumu', belt]), { full: false }),
      panel('Kalite kayıtları', cards(['Sağlam', '—'], ['Yeniden işlem', '—'], ['Hurda', '—']), { full: false }),
      panel('Renk performansı', deposits),
      panel('Son üretim hareketleri', recentOutput(metrics.events || [])),
      panel('Simülasyon kontrolleri', controls),
    ].join('');
  }

  const header = `<div class="panel-head"><h2>Simülasyon senaryosu</h2>${status}</div>`;
  if (!run) return header + identity + controls;
  const progress = target > 0 && Number.isFinite(completed) ? `<progress max="${target}" value="${completed}" aria-label="Senaryo ilerlemesi"></progress>` : '';
  const result = verdict ? `<p class="panel-note">Model sonucu · ${esc(verdict)}</p>` : '';
  return header + identity + cards(['Senaryo', run.scenario], ['Mod', mode], ['Beklenen', unit(target, 'kutu')],
    ['Depolanan', unit(completed, 'kutu')]) + progress + result + controls;
}

function twinSummary({ run, state, speed, frame, detail }) {
  const [label, tone] = stateLabels[state] || ['Motor sorgulanıyor', 'idle'];
  const model = frame ? `<dl class="digital-twin-metrics">
    <div><dt>Model saati</dt><dd>${unit(frame.simTime, 'sn')}</dd></div>
    <div><dt>Depolanan</dt><dd>${unit(frame.counters?.completed, 'kutu')}</dd></div>
    <div><dt>Konveyör</dt><dd>${frame.conveyor?.running ? 'Çalışıyor' : 'Duruyor'}</dd></div>
    <div><dt>Kamera</dt><dd>${frame.camera?.busy ? 'Okuyor' : 'Bekliyor'}</dd></div>
    </dl>` : `<p class="panel-note">${esc(detail || (run ? 'Modelin ilk karesi bekleniyor.' : 'Bir AnyLogic koşusu başlat.'))}</p>`;
  return `<span class="plant-led" data-tone="${tone}">${label}</span>
    ${run ? `<p class="panel-note" data-sim-run>${esc(run.scenario)} · ${esc(run.id.slice(0, 8) + speedSuffix(speed))}</p>` : ''}${model}`;
}

export function bindSimulationMes({ moduleId, selectTab }) {
  const picker = document.getElementById('mes-source');
  const views = new Map([...document.querySelectorAll('[data-sim-view]')].map(view => [view.dataset.simView, view]));
  let tab, twin;
  let active = new URLSearchParams(window.location.search).get('source') === 'anylogic';
  let snapshot = {}, packet = {}, frameKey, generation = 0;
  const rendered = new WeakMap();

  function render() {
    if (!active || !views.has(tab)) return;
    const view = views.get(tab);
    const motorError = !packet.run && ['unavailable', 'error'].includes(snapshot.state);
    const next = tab === 'digital-twin' ? twinSummary(motorError ? snapshot : packet) : renderSimulationSummary(snapshot, tab);
    if (rendered.get(view) === next) return;
    const focus = view.contains(document.activeElement) ? document.activeElement : null;
    const flow = view.querySelector('.plant-flow');
    const scroll = flow?.scrollLeft;
    view.innerHTML = next;
    rendered.set(view, next);
    if (flow) view.querySelector('.plant-flow')?.scrollTo(scroll, 0);
    if (focus?.dataset.simTab) view.querySelector(`[data-sim-tab="${focus.dataset.simTab}"]`)?.focus({ preventScroll: true });
    else if (flow && focus === flow) view.querySelector('.plant-flow')?.focus({ preventScroll: true });
  }

  async function poll(path, interval, receive) {
    const stamp = generation;
    while (generation === stamp) {
      if (!document.hidden) {
        let result;
        try {
          result = await request(path);
        } catch (error) {
          result = { state: 'unavailable', detail: error.message };
        }
        if (generation === stamp) receive(result);
      }
      await new Promise(resolve => setTimeout(resolve, interval));
    }
  }

  function refresh() {
    generation += 1;
    twin?.setAnyLogicMode(active);
    render();
    if (!active || !views.has(tab)) return;
    void poll(api, 1200, result => {
      snapshot = result;
      render();
    });
    if (tab === 'digital-twin') {
      void poll(`${api}/frame`, 150, result => {
        const key = [result.run?.id, result.state, result.speed, result.frame?.seq, result.detail].join('|');
        if (key === frameKey) return;
        frameKey = key;
        packet = result;
        twin?.acceptAnyLogicFrame(result);
        render();
      });
    }
  }

  function setSource(anylogic) {
    active = anylogic;
    picker.value = anylogic ? 'anylogic' : 'physical';
    document.body.dataset.mesSource = picker.value;
    const url = new URL(window.location.href);
    if (anylogic) url.searchParams.set('source', 'anylogic');
    else url.searchParams.delete('source');
    window.history.replaceState({}, '', url);
    refresh();
  }

  for (const link of document.querySelectorAll('[data-sim-link]')) {
    link.href = `/?${new URLSearchParams({ module: moduleId, tab: link.dataset.simLink, source: 'anylogic' })}`;
  }
  picker.addEventListener('change', () => setSource(picker.value === 'anylogic'));
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-sim-tab]');
    if (!button) return;
    if (!active) setSource(true);
    selectTab(button.dataset.simTab);
    document.querySelector(`.tab-button[data-tab="${button.dataset.simTab}"]`)?.focus();
  });
  setSource(active);
  return {
    start() { if (!active) setSource(true); },
    activate(next) { tab = next; refresh(); },
    attachTwin(module) {
      twin = module;
      twin.setAnyLogicMode(active);
      if (active) twin.acceptAnyLogicFrame(packet);
    },
  };
}

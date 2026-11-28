import { esc } from './atolye-onizleme-core.js?v=5';

const api = '/api/workspace/anylogic';
const cases = [
  ['T01', 'Tek kırmızı'], ['T02', 'Tek mavi'], ['T03', 'Tek sarı'],
  ['T04', 'Ardışık kırmızı'], ['T05', 'Ardışık mavi'], ['T06', 'Ardışık sarı'],
  ['T07', 'Karışık sıra'], ['T08', 'Altı kutulu karışık sıra'],
  ['T09', 'Üç kırmızı · depo testi'], ['T10', 'Üç mavi · depo testi'], ['T11', 'Üç sarı · depo testi'],
  ['T12', 'Kamera süresi'], ['T13', 'Konum ve robot'], ['T14', 'Hızlı karışık geliş'],
];
export const stateLabels = {
  ready: ['Motor hazır', 'ok'], running: ['Simülasyon çalışıyor', 'ok'], paused: ['Duraklatıldı', 'warn'],
  stopped: ['Simülasyon durduruldu', 'idle'],
  completed: ['Koşu tamamlandı', 'ok'], unavailable: ['Motor kullanılamıyor', 'idle'], error: ['Motor hatası', 'error'],
};
const colors = { red: 'Kırmızı', blue: 'Mavi', yellow: 'Sarı', kirmizi: 'Kırmızı', mavi: 'Mavi', sari: 'Sarı' };
const number = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const amount = value => Number.isFinite(value) ? number.format(value) : '—';
const seconds = value => Number.isFinite(value) ? `${amount(value)} sn` : '—';
const running = value => typeof value === 'boolean' ? (value ? 'Çalışıyor' : 'Bekliyor') : '—';

export function card(label, value) {
  return `<article class="plant-kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong></article>`;
}

export function stage(label, value) {
  return `<li class="plant-stage"><h3>${esc(label)}</h3><p class="panel-note">${esc(value)}</p></li>`;
}

export function depot(color, inventory) {
  const data = inventory[color];
  const name = colors[color];
  const recorded = Number.isFinite(data?.count) && data?.capacity > 0;
  return `<article data-color="${color}"><div><span>${name} deposu</span><strong>${recorded ? `${amount(data.count)} / ${amount(data.capacity)}` : '—'}</strong></div>
    ${recorded ? `<progress max="${data.capacity}" value="${data.count}" aria-label="${name} deposunun doluluğu"></progress>` : ''}</article>`;
}

function eventRows(events) {
  if (!events.length) return '<tr><td colspan="5" class="empty-state">Model olayı bekleniyor.</td></tr>';
  return [...events].reverse().map(event => {
    const [kind, box, color, ...detail] = String(event.message || '').split(';');
    return `<tr>${[seconds(event.at), kind.replaceAll('_', ' '), box, colors[color] || color, detail.join(';')]
      .map(value => `<td>${esc(value || '—')}</td>`).join('')}</tr>`;
  }).join('');
}

export async function request(path, data) {
  const init = { cache: 'no-store', signal: AbortSignal.timeout(data ? 42_000 : 12_000) };
  if (data) Object.assign(init, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const response = await fetch(path, init);
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'AnyLogic isteği tamamlanamadı.');
  return result;
}

export function bindAnyLogic(panel, onStart) {
  const query = selector => panel.querySelector(selector);
  const engine = query('#anylogic-engine');
  const mode = query('#anylogic-mode');
  const scenario = query('#anylogic-scenario');
  const speedButtons = [...panel.querySelectorAll('[data-sim-speed]')];
  const speedNote = query('#anylogic-speed-note');
  const speedDetail = query('#anylogic-speed-detail');
  const speedPreview = query('#anylogic-speed-preview');
  const feedback = query('#anylogic-feedback');
  const report = query('#anylogic-report');
  const verdict = query('#anylogic-verdict');
  const buttons = [...panel.querySelectorAll('[data-sim-action]')];
  scenario.innerHTML = cases.map(([id, name]) => `<option value="${id}">${id} · ${name}</option>`).join('');
  scenario.value = 'T07';
  let visible = false;
  let loading = false;
  let commandPending = false;
  let revision = 0;
  let lastReport;
  let selectedSpeed = 1;
  let snapshot = {};
  const onMainPreview = ['127.0.0.1', 'localhost'].includes(location.hostname) && location.port === '18780';

  if (onMainPreview) {
    const url = new URL(location.href);
    url.port = '18880';
    url.searchParams.set('tab', 'anylogic');
    url.searchParams.set('source', 'anylogic');
    speedPreview.href = url;
  }

  function liveRun(state) {
    return state.state === 'running' || state.state === 'paused';
  }

  function acceptState(state) {
    snapshot = state;
    if (liveRun(state) && state.speed != null) selectedSpeed = state.speed;
  }

  function controls() {
    const run = snapshot.run;
    if (run && snapshot.state !== 'stopped' && run.mode && run.scenario !== '—') {
      mode.value = run.mode;
      scenario.value = run.scenario;
    }
    const unlocked = snapshot.available && snapshot.can_control && !commandPending;
    mode.disabled = scenario.disabled = !unlocked || Boolean(run && snapshot.state !== 'stopped');
    const hasSpeed = Object.hasOwn(snapshot, 'speed') && (!liveRun(snapshot) || snapshot.speed != null);
    const speedAvailable = snapshot.available && snapshot.can_control && hasSpeed;
    for (const button of speedButtons) {
      button.disabled = !speedAvailable;
      button.setAttribute('aria-disabled', String(!speedAvailable || commandPending));
      button.setAttribute('aria-pressed', String(Number(button.dataset.simSpeed) === selectedSpeed));
    }
    const speedUnavailable = snapshot.available && !hasSpeed;
    const nextRunSpeed = snapshot.state === 'completed' && hasSpeed && snapshot.can_control;
    speedNote.hidden = !speedUnavailable && !nextRunSpeed;
    speedDetail.textContent = speedUnavailable ? 'Bu önizlemede hız ayarı kullanılamıyor.' :
      nextRunSpeed ? 'Seçtiğin hız bir sonraki koşuda uygulanır.' : '';
    speedPreview.hidden = !speedUnavailable || !onMainPreview;
    for (const button of buttons) {
      const action = button.dataset.simAction;
      const allowed = { start: !run || snapshot.state === 'stopped', pause: snapshot.state === 'running',
        resume: snapshot.state === 'paused', stop: liveRun(snapshot), reset: Boolean(run) };
      button.disabled = !unlocked || !allowed[action];
    }
    query('#anylogic-scenario-note').textContent = mode.value === 'SUREKLI'
      ? 'Seçili Excel testi renk ve kamera süresini sağlar. Model sentetik giriş üretir.'
      : 'Seçili Excel testinin renkleri, giriş zamanları ve kamera süreleri kullanılır.';
  }

  function render() {
    controls();
    const [title, tone] = stateLabels[snapshot.state] || ['Motor sorgulanıyor', 'idle'];
    engine.textContent = title;
    engine.dataset.tone = tone;
    const run = snapshot.run;
    const metrics = snapshot.metrics || {};
    const counts = metrics.counters || {};
    const inventory = metrics.inventory || {};
    const simulated = run?.mode === 'SUREKLI';
    const runSpeed = snapshot.speed == null ? '' : ` · ${snapshot.speed}×`;
    query('#anylogic-run').textContent = run ? `${simulated ? 'Sentetik akış' : `Excel testi ${run.scenario}`} · ${run.id.slice(0, 8)}${runSpeed}` : 'Koşu bekleniyor';
    query('#anylogic-kpis').innerHTML = [card('Model saati', seconds(snapshot.modelTime)), card('Giren kutu', amount(counts.entered)),
      card('Depolanan kutu', amount(counts.completed)), card('Ara depo', amount(counts.buffer)), card('Konveyör / robot bölgesi', amount(counts.onConveyor)),
      simulated ? card('Sevk edilen kutu', amount(counts.shipped)) : card('Testte beklenen kutu', amount(snapshot.target))].join('');
    verdict.hidden = !snapshot.verdict;
    verdict.dataset.tone = snapshot.verdict?.startsWith('TAMAMLANDI') ? 'ok' : 'error';
    verdict.textContent = snapshot.verdict ? `Model sonucu · ${snapshot.verdict}` : '';
    query('#anylogic-flow').innerHTML = [stage('Kesme', `${amount(metrics.stations?.cutting)} kutu`),
      stage('Kaplama', `${amount(metrics.stations?.coating)} kutu`), stage('Ara depo', `${amount(counts.buffer)} kutu`),
      stage('Konveyör / kamera', metrics.camera?.busy ? `Okuyor · ${metrics.camera.productId || 'Kutu'}` : running(metrics.conveyor?.running)),
      stage('Robot kol', metrics.robot?.state === 'IDLE' ? 'Boşta' : metrics.robot?.state?.replaceAll('_', ' ') || '—'),
      stage('Renk depoları', `${amount(counts.completed)} depolanan`)].join('');
    query('#anylogic-stock').innerHTML = ['red', 'blue', 'yellow'].map(color => depot(color, inventory)).join('');
    query('#anylogic-events').innerHTML = eventRows(metrics.events || []);
    if (run && snapshot.has_report) lastReport = run.id;
    else if (snapshot.lastReport) lastReport = snapshot.lastReport;
    report.hidden = !lastReport;
    if (lastReport) {
      report.href = `${api}/${lastReport}/report`;
      report.textContent = run?.id === lastReport ? 'Olay CSV’si' : 'Son koşunun CSV’si';
    }
  }

  function message(text, tone = '') {
    feedback.textContent = text || '';
    feedback.dataset.tone = tone;
  }

  async function refresh() {
    if (!visible || loading || commandPending) return;
    loading = true;
    const before = revision;
    try {
      const state = await request(api);
      if (before !== revision) return;
      acceptState(state);
      render();
      if (state.detail) message(state.detail, state.state === 'error' ? 'error' : '');
      else if (!state.can_control) message('Koşuyu izleme erişiminiz var. Kontroller mühendis ve yöneticiye açık.');
      else if (!feedback.textContent || previousError) message('');
      previousError = state.state === 'error';
    } catch (error) {
      if (before !== revision) return;
      snapshot = { ...snapshot, available: false, state: 'unavailable' };
      render();
      message(error.message, 'error');
      previousError = true;
    } finally {
      loading = false;
    }
  }

  let previousError = false;
  mode.addEventListener('change', controls);
  async function send(action, speed = selectedSpeed) {
    if (commandPending) return;
    commandPending = true;
    revision += 1;
    controls();
    message(action === 'speed' ? 'Hız değiştiriliyor…' : 'Motor yanıtı bekleniyor…');
    try {
      const state = await request(`${api}/command`, { action, run_id: snapshot.run?.id || null, ...selection(), speed });
      acceptState(state);
      if (action === 'speed' && state.speed != null) selectedSpeed = state.speed;
      if (action === 'start') onStart();
      message(action === 'speed' ? `Simülasyon hızı ${snapshot.speed}×.` : '');
      previousError = false;
    } catch (error) {
      message(error.message, 'error');
    } finally {
      commandPending = false;
      render();
    }
  }
  panel.addEventListener('click', event => {
    const speedButton = event.target.closest('button[data-sim-speed]');
    if (speedButton && !speedButton.disabled && !commandPending) {
      const speed = Number(speedButton.dataset.simSpeed);
      if (liveRun(snapshot)) {
        if (speed !== selectedSpeed) void send('speed', speed);
      } else {
        selectedSpeed = speed;
        controls();
      }
      return;
    }
    const button = event.target.closest('button[data-sim-action]');
    if (button) void send(button.dataset.simAction);
  });
  setInterval(() => { if (!document.hidden) void refresh(); }, 1200);
  function selection() {
    return { mode: mode.value || 'TEST', scenario: scenario.value || 'T07', speed: selectedSpeed };
  }
  render();
  return { selection, activate(active) { visible = active; if (visible) void refresh(); } };
}

import {badge, clock, duration, esc, icon} from './lib/ui.mjs';
import {FormDrafts} from './lib/drafts.mjs';
import {makeReadOnly} from './lib/read-only.mjs';
import {render as renderTaping} from './panels/taping.mjs';
import {render as renderPacking} from './panels/packing.mjs';
import {render as renderTechnician} from './panels/technician.mjs';
import {render as renderEngineer} from './panels/engineer.mjs';
import {renderOrderDetail} from './panels/order-detail.mjs';

const employeePages = {
  taping: ['Bantlama istasyonu', renderTaping],
  packing: ['Paketleme istasyonu', renderPacking],
  technician: ['Tekniker paneli', renderTechnician],
  engineer: ['Mühendis paneli', renderEngineer],
};
const routeNames = { bantlama: 'taping', paketleme: 'packing', tekniker: 'technician', teknisyen: 'technician',
  muhendis: 'engineer', mühendis: 'engineer' };
const path = decodeURIComponent(location.pathname).split('/').filter(Boolean);
const observed = path[0] === 'calisan' && path[1] === 'izle';
const workspace = observed ? path[2] : routeNames[path[0]];
const page = Object.hasOwn(employeePages, workspace) ? employeePages[workspace] : null;
const root = document.querySelector('#content');
const modal = document.querySelector('#modal');
const toastBox = document.querySelector('#toast');
const retry = document.querySelector('#retry-action');
const ui = {color: 'blue', quality: 'good', packOrder: null};
const drafts = new FormDrafts();
let state, signature, pending, busy = false, refreshing = false, lastRead = 0, toastTimer;
const reasonField = '<label>Kısa açıklama<textarea name="reason" required maxlength="500" rows="3"></textarea></label>';
const colorField = '<label>Bant rengi<select name="color"><option value="yellow">Sarı</option><option value="blue">Mavi</option><option value="red">Kırmızı</option></select></label>';

function toast(message) {
  toastBox.textContent = message;
  toastBox.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastBox.classList.remove('visible'), 6000);
}

function setConnected(connected) {
  const status = document.querySelector('#connection-status');
  if (status.dataset.connected !== String(connected)) {
    status.dataset.connected = connected;
    status.innerHTML = badge(connected ? 'Sunucu bağlı' : 'Yeniden bağlanıyor', connected ? 'teal' : 'amber');
  }
  retry.hidden = observed || !pending;
}

function draftKey(id, box = state?.activeBox?.id) {
  return id === 'finish-form' ? id + ':' + (box || '') : id;
}

function applySnapshot(data, force = false) {
  const previousBox = state?.activeBox?.id;
  state = data.state || data;
  if (state.activeBox?.id !== previousBox) {
    if (previousBox) drafts.delete(draftKey('finish-form', previousBox));
    ui.quality = 'good';
  }
  const meta = state.meta || {};
  const {serverNow, ...stableMeta} = meta;
  const nextSignature = JSON.stringify({...state, meta: stableMeta});
  if (force || signature !== nextSignature) {
    signature = nextSignature;
    render();
  }
  document.querySelector('#server-time').textContent = clock(serverNow);
  setConnected(true);
}

function render() {
  if (!state) return;
  const focus = document.activeElement;
  const elementId = focus?.id;
  const formId = focus?.form?.id;
  const name = focus?.name;
  const selection = [focus?.selectionStart, focus?.selectionEnd];
  const readOnly = observed || state.meta.readOnly === true;
  const context = { state: {...state, meta: {...state.meta, mode: state.mode, workspace, readOnly}}, ui, readOnly };
  const isDemo = (state.mode || state.meta.mode) === 'demo';
  document.querySelector('#source-mode').innerHTML = badge(isDemo ? 'ÖRNEK VERİ' : 'FİZİKSEL HAT', isDemo ? 'amber' : 'blue');
  document.querySelector('#mode-banner').innerHTML = isDemo
    ? '<div class="source-banner">Örnek çalışma alanı · Üretim işlemleri deneme kaydıdır. Fiziksel cihazlara otomatik komut gönderilmez.</div>' : '';
  const shift = workspace === 'taping' ? state.shift : state.meta.stationShift ?? state.stationShifts?.[workspace];
  const identity = document.querySelector('#employee-identity');
  const currentOperator = shift?.active ? shift.operator : '';
  identity.hidden = !currentOperator;
  identity.textContent = currentOperator || '';
  root.classList.toggle('employee-observer', readOnly);
  root.innerHTML = page[1](context);
  for (const form of root.querySelectorAll('form')) drafts.restore(draftKey(form.id), form.elements);
  if (state.activeBox?.handoverRequired) {
    root.querySelectorAll('[data-step], #finish-form button, [data-action="pause-dialog"], [data-action="resume"]')
      .forEach(control => { control.disabled = true; });
  }
  if (readOnly) makeReadOnly(root);
  else delete root.dataset.readOnly;
  if (elementId || (name && formId)) {
    const next = (elementId && document.getElementById(elementId)) || document.getElementById(formId)?.elements.namedItem(name);
    if (next && !next.disabled) {
      next.focus({preventScroll: true});
      if (selection[0] !== null && selection[0] !== undefined) next.setSelectionRange?.(...selection);
    }
  }
}

async function request(url, method = 'GET', body) {
  const params = {method, credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(10000)};
  if (body !== undefined) {
    params.headers = {'Content-Type': 'application/json'};
    params.body = JSON.stringify(body);
  }
  const response = await fetch(url, params);
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) {
    const detail = data?.detail;
    const fallback = response.status === 401 ? 'Bu ekran için mühendis girişi gerekiyor.'
      : response.status === 403 ? 'Bu istasyona erişim yetkin yok.' : 'İstasyon isteği tamamlanamadı.';
    const error = new Error(typeof detail === 'string' ? detail : detail?.message || fallback);
    error.status = response.status;
    throw error;
  }
  return data;
}

function statePath() {
  return `/api/${observed ? 'employee-observer' : 'employee-stations'}/${workspace}`;
}

async function refresh() {
  if (!page || refreshing || busy) return;
  refreshing = true;
  const read = ++lastRead;
  try {
    const data = await request(statePath());
    if (read === lastRead) applySnapshot(data);
  } catch (error) {
    if (read === lastRead) {
      setConnected(false);
      if (!state) root.textContent = error.message || 'Sunucuya ulaşılamadı.';
    }
  } finally {
    refreshing = false;
  }
}

function requestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
}

async function sendPending() {
  if (!pending || busy || observed || state?.meta.readOnly) return;
  busy = true;
  lastRead += 1;
  let refreshAfter = false;
  try {
    const data = await request(`/api/employee-stations/${workspace}/actions`, 'POST', pending.payload);
    if (pending.formId) drafts.delete(pending.formId);
    pending = null;
    applySnapshot(data, true);
  } catch (error) {
    if (error.status && error.status < 500) {
      pending = null;
      refreshAfter = error.status === 409;
    } else {
      setConnected(false);
      throw Error('Son kayıt doğrulanamadı. Üst çubuktan aynı isteği yeniden dene.');
    }
    throw error;
  } finally {
    busy = false;
    retry.hidden = !pending;
    if (refreshAfter) refresh();
  }
}

async function dispatch(action, formId) {
  if (!state || observed || state.meta.readOnly || busy) return;
  if (pending) throw Error('Önce üst çubuktan son isteğin sonucunu doğrula.');
  const revision = state.revision ?? state.meta.revision;
  if (!Number.isInteger(revision)) throw Error('İstasyon durumu güncellenemedi.');
  pending = {payload: {id: requestId(), revision, action}, formId: formId && draftKey(formId)};
  await sendPending();
}

function dialog(title, fields, submit) {
  modal.setAttribute('aria-labelledby', 'dialog-title');
  modal.classList.toggle('detail-dialog', !submit);
  const actions = submit
    ? '<button type="button" class="button" data-close>Vazgeç</button><button class="button primary">Kaydet</button>'
    : '<button type="button" class="button" data-close>Kapat</button>';
  const content = `<div class="dialog-header"><h2 id="dialog-title">${esc(title)}</h2>
    <button type="button" class="icon-button" data-close aria-label="Kapat">${icon('close')}</button></div>
    <div class="dialog-body">${fields}<p class="dialog-error" role="alert" hidden></p><div class="dialog-actions">${actions}</div></div>`;
  modal.innerHTML = submit ? `<form>${content}</form>` : content;
  modal.querySelectorAll('[data-close]').forEach(button => { button.onclick = () => modal.close(); });
  if (submit) modal.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
      await submit(Object.fromEntries(new FormData(event.target)));
      modal.close();
    } catch (error) {
      const message = modal.querySelector('.dialog-error');
      message.textContent = error.message;
      message.hidden = false;
    } finally { button.disabled = false; }
  };
  if (!modal.open) modal.showModal();
}

function planOrder(id) {
  const planning = state.meta.planning;
  const order = planning?.planned.find(entry => entry.id === id) || planning?.pending.find(entry => entry.id === id);
  if (!order) return;
  const day = order.day >= planning.today ? order.day : planning.today;
  dialog(id + ' · Üretim günü', `<label>Üretim günü<input name="day" type="date" required min="${esc(planning.today)}" value="${esc(day)}"></label>`,
    fields => dispatch({type: 'order-plan', orderId: id, day: fields.day}));
}

function dailyTarget(automatic) {
  const today = state.meta.planning?.today;
  if (!today) return;
  dialog(automatic ? 'Otomatik hesaba dön' : 'Günlük hedefi gir',
    `<label>Üretim günü<input name="day" type="date" required min="${esc(today)}" value="${esc(today)}"></label>`
    + (automatic ? '' : '<label>Sağlam kutu hedefi<input name="quantity" type="number" required min="0" max="1000000"></label>'),
    fields => dispatch({type: 'daily-target', day: fields.day, quantity: automatic ? null : Number(fields.quantity)}));
}

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled || !state || busy) return;
  const {action, id, color, itemId, measureId} = button.dataset;
  if (action === 'order-detail') {
    const order = state.orders.find(entry => entry.id === id);
    if (order) dialog('İş emri ' + id, renderOrderDetail(state, order));
    return;
  }
  if (observed || state.meta.readOnly) return;
  try {
    switch (action) {
      case 'retry-request': await sendPending(); toast('Son istek doğrulandı.'); break;
      case 'choose-color': ui.color = color; render(); break;
      case 'start': await dispatch({type: 'start-box', color: ui.color}); break;
      case 'complete-next-step': {
        const index = Number(button.dataset.stepIndex), box = state.activeBox;
        if (box && !box.paused && !box.handoverRequired && box.steps.findIndex(done => !done) === index) {
          await dispatch({type: 'step', index});
          document.getElementById('complete-next-step')?.focus({preventScroll: true});
        }
        break;
      }
      case 'end-station-shift': await dispatch({type: 'shift', operation: 'end'}); break;
      case 'claim-box': case 'ack': case 'activity-start': case 'cancel-instruction': await dispatch({type: action}); break;
      case 'resume': await dispatch({type: 'resume-box'}); break;
      case 'pause-dialog': dialog('Duraklama nedeni', reasonField, fields => dispatch({type: 'pause-box', ...fields})); break;
      case 'activity-end': dialog('Faaliyeti tamamla', reasonField.replace(' required', ''), fields => dispatch({type: 'activity-end', ...fields})); break;
      case 'material-dialog': dialog('Bant bildirimi', colorField + '<label>Durum<select name="level"><option value="low">Azalıyor</option><option value="empty">Bitti</option></select></label>' + reasonField, fields => dispatch({type: 'material', ...fields})); break;
      case 'fault-dialog': dialog('Arıza bildir', reasonField, fields => dispatch({type: 'fault', orderId: id, ...fields})); break;
      case 'restock': await dispatch({type: 'restock', color}); break;
      case 'resolve': await dispatch({type: 'resolve', id}); break;
      case 'pack': await dispatch({type: 'pack', itemId: id}); break;
      case 'seal': case 'unpark': await dispatch({type: action, orderId: id}); break;
      case 'park-dialog': dialog('Eksik koliyi ayır', reasonField, fields => dispatch({type: 'park', orderId: id, ...fields})); break;
      case 'plan-order': planOrder(id); break;
      case 'daily-target-manual': case 'daily-target-auto': dailyTarget(action.endsWith('-auto')); break;
      case 'order-up': {
        const ids = state.orders.filter(order => !order.closedAt).map(order => order.id);
        const index = ids.indexOf(id);
        if (index > 0) {
          [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]];
          await dispatch({type: 'reorder', ids});
        }
        break;
      }
      case 'handoff-confirm':
        dialog('Gerçek kutuyu doğrula', `<p>Konveyöre verdiğin fiziksel kutu, <strong>${esc(itemId)}</strong> kodlu algılanan kutuyla aynıysa kaydet.</p>`,
          () => dispatch({type: 'handoff-confirm', id, itemId, measureId}));
        break;
      case 'handoff-close':
        dialog('Eşleştirmeyi kapat', '<p>Kutuyu doğrulamadan bu teslim kaydını kapatmak için kaydet.</p>',
          () => dispatch({type: 'handoff-close', id}));
        break;
    }
  } catch (error) { toast(error.message); }
});

root.addEventListener('input', event => {
  if (event.target.form?.id && !observed) drafts.edit(draftKey(event.target.form.id), event.target);
});
root.addEventListener('change', async event => {
  const field = event.target;
  if (field.id === 'packing-order') { ui.packOrder = field.value; render(); return; }
  if (observed || state?.meta.readOnly || !state || busy || field.disabled) return;
  try {
    if (field.matches('[data-step]')) await dispatch({type: 'step', index: Number(field.dataset.step)});
    else if (field.id === 'quality-select') { ui.quality = field.value; render(); }
  } catch (error) {
    if (field.matches('[data-step]')) render();
    toast(error.message);
  }
});

root.addEventListener('submit', async event => {
  event.preventDefault();
  if (observed || state?.meta.readOnly || !state || busy) return;
  const form = event.target;
  const fields = Object.fromEntries(new FormData(form));
  try {
    if (form.id === 'station-shift-form') {
      if (!fields.operator?.trim()) throw Error('Adını ve soyadını yaz.');
      await dispatch({type: 'shift', operation: 'start', operator: fields.operator.trim()}, form.id);
    } else if (form.id === 'priority-form') await dispatch({type: 'instruction', ...fields}, form.id);
    else if (form.id === 'finish-form') {
      await dispatch({type: 'finish-box', ...fields}, form.id);
      ui.quality = 'good';
      render();
    }
  } catch (error) { toast(error.message); }
});

if (page) {
  document.title = page[0] + ' · Atölye MES';
  if (observed) document.body.classList.add('embedded-employee');
  document.querySelector('#employee-brand').innerHTML = icon('factory') + '<span>ATÖLYE <b>MES</b><small>ÜRETİM ÇALIŞMA ALANI</small></span>';
  setConnected(false);
  refresh();
  setInterval(refresh, 1500);
  setInterval(() => {
    if (!state) return;
    const box = state.activeBox, now = Date.now();
    const timers = {box: box ? box.activeMs + (!box.paused ? now - box.since : 0) : 0,
      pause: box ? box.pausedMs + (box.paused ? now - box.since : 0) : 0,
      activity: state.activity ? now - state.activity.startedAt : 0};
    for (const [name, value] of Object.entries(timers)) {
      const timer = root.querySelector(`[data-timer="${name}"]`);
      if (timer) timer.textContent = duration(value);
    }
  }, 1000);
} else root.textContent = 'İstasyon bulunamadı.';

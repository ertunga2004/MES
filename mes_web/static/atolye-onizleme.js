/**
 * Atölye Önizleme - Ana Uygulama Modülü
 * Kiosk Tasarla düzenleyicisini yönetir.
 * Bu modül canlı veri kullanmaz, MQTT veya fiziksel cihaz komutu göndermez.
 */

import { KioskRenderer } from './atolye-onizleme-core.js?v=5';
import {
  SAMPLE_KIOSK_DESIGN,
  TEMPLATES
} from './atolye-onizleme-data.js';
import { STATIONS_LIST } from './atolye-tablet-state.mjs?v=4';

// ============================================================
// Yardımcı fonksiyonlar
// ============================================================

function esc(str) {
  return KioskRenderer.esc(str);
}

// ============================================================
// Durum yönetimi
// ============================================================

const state = {
  // Designer sekmesi
  designer: {
    currentKiosk: null,
    templates: {},
    busy: false,
    editDesign: { ...SAMPLE_KIOSK_DESIGN },
    selectedTemplate: null
  }
};

// ============================================================
// Sekme 1: Kiosk Tasarla Editörü
// ============================================================

async function workspaceRequest(path, method = 'GET', body) {
  const options = { method, cache: 'no-store' };
  if (body) Object.assign(options, { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const response = await fetch(`/api/workspace/${path}`, options);
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Şablon alanlarını kontrol edin.');
  return value;
}

function feedback(message) {
  document.getElementById('designer-feedback').textContent = message;
}

async function initDesignerTab() {
  renderTemplateSelector();
  try {
    const [templates, user] = await Promise.all([workspaceRequest('templates'), workspaceRequest('identity')]);
    state.designer.templates = templates;
    loadKiosk('bantlama');
    if (user.role === 'admin') bindPairForm();
  } catch (error) {
    feedback(error.message);
  }
}

function renderCatalog() {
  const catalog = document.getElementById('kiosk-catalog');
  if (!catalog) return;

  const kiosks = STATIONS_LIST.map(({ id, name }) => ({ slug: id, title: name, published: state.designer.templates[id]?.published }));

  catalog.innerHTML = kiosks.map(k => `
    <button type="button" class="kiosk-catalog-item" data-kiosk-slug="${esc(k.slug)}" aria-pressed="${k.slug === state.designer.currentKiosk?.slug}">
      <strong>${esc(k.title)}</strong>
      <span>${k.published ? `Yayında · Sürüm ${k.published.version}` : 'Taslak'}</span>
    </button>
  `).join('');

  // Click handlers
  catalog.querySelectorAll('[data-kiosk-slug]').forEach(btn => {
    btn.addEventListener('click', () => loadKiosk(btn.dataset.kioskSlug));
  });
}

function loadKiosk(slug) {
  if (state.designer.busy) return;
  const station = STATIONS_LIST.find(item => item.id === slug);
  if (!station) return;
  const row = state.designer.templates[slug];
  state.designer.currentKiosk = { slug, revision: row?.revision ?? 0, published: row?.published };
  const base = structuredClone(SAMPLE_KIOSK_DESIGN);
  if (slug !== 'bantlama') {
    Object.assign(base, { title: `${station.name} kontrol listesi`, instructions: '', before: '', after: '', steps: [], sections: [], cards: [] });
    base.features = { timer: false, progress: null, result: null };
  } else {
    base.cards = base.cards.map(card => card.kind === 'steps' ? KioskRenderer.makeCard('stepper') : card);
    base.steps = [];
  }
  loadDesign({ ...base, ...structuredClone(row?.draft ?? {}), station: slug, slug });
  hideTemplateSelector();
  renderCatalog();
  feedback('');
}

function renderTemplateSelector() {
  const grid = document.getElementById('template-grid');
  if (!grid) return;

  grid.innerHTML = Object.entries(TEMPLATES).map(([key, tpl]) => `
    <button type="button" class="template-card" data-template="${key}">
      <strong>${esc(tpl.title)}</strong>
      <span>${esc(tpl.hint)}</span>
    </button>
  `).join('');

  grid.querySelectorAll('.template-card').forEach(card => {
    card.addEventListener('click', () => selectTemplate(card.dataset.template));
  });
}

function selectTemplate(key) {
  state.designer.selectedTemplate = key;
  const design = KioskRenderer.applyTemplate(structuredClone(state.designer.editDesign), key);
  loadDesign(design);
  hideTemplateSelector();
}

function hideTemplateSelector() {
  const selector = document.getElementById('template-selector');
  const form = document.getElementById('kiosk-design-form');
  if (selector) selector.classList.add('hidden');
  if (form) form.classList.remove('hidden');
}

function showTemplateSelector() {
  const selector = document.getElementById('template-selector');
  const form = document.getElementById('kiosk-design-form');
  if (selector) selector.classList.remove('hidden');
  if (form) form.classList.add('hidden');
}

function loadDesign(design) {
  state.designer.editDesign = { ...design };
  renderEditor(design);
  renderPreview(design);
  updateEditorTitle(design);
}

function updateEditorTitle(design) {
  const titleEl = document.getElementById('editor-title');
  const statusEl = document.getElementById('editor-status');
  if (titleEl) titleEl.textContent = design.title || 'Yeni kiosk';
  if (statusEl) {
    statusEl.textContent = state.designer.currentKiosk?.published ? `Yayında · Sürüm ${state.designer.currentKiosk.published.version}` : 'Taslak';
    statusEl.className = 'badge ' + (state.designer.currentKiosk?.published ? 'teal' : 'gray');
  }
}

function renderEditor(design) {
  const form = document.getElementById('kiosk-design-form');
  if (!form) return;

  form.dataset.template = design.template || '';

  const progress = design.features?.progress;
  const timer = design.features?.timer;
  const result = design.features?.result;

  form.innerHTML = `
    <section class="kiosk-editor-block">
      <h3>İstasyon Bilgileri</h3>
      <div class="kiosk-design-details">
        <label>Kiosk adı<input name="title" value="${esc(design.title)}" placeholder="Örn. Bantlama" required maxlength="60"></label>
        <label>Web adresi <small>Örn. /bantlama</small>
          <div class="kiosk-slug"><span aria-hidden="true">/</span><input name="slug" readonly value="${esc(design.slug)}"></div>
        </label>
      </div>
      <label>Operatör talimatı<textarea name="instructions" rows="3" maxlength="1500">${esc(design.instructions)}</textarea></label>
    </section>

    <section class="kiosk-editor-block">
      <h3>Özellikler</h3>
      <div class="kiosk-feature-question">
        <label><input type="checkbox" name="feature-timer" ${timer ? 'checked' : ''}> Süre sayacı</label>
      </div>
      <div class="kiosk-feature-question">
        <label><input type="checkbox" name="feature-progress" ${progress ? 'checked' : ''}> Üretim sayacı</label>
        ${progress ? `
        <div class="kiosk-feature-settings">
          <label>Hedef adet<input name="progress-target" type="number" min="1" value="${esc(progress.target)}"></label>
          <label>Birim<input name="progress-unit" value="${esc(progress.unit)}" placeholder="adet"></label>
        </div>` : ''}
      </div>
      <div class="kiosk-feature-question">
        <label><input type="checkbox" name="feature-result" ${result ? 'checked' : ''}> İş sonucu</label>
        ${result ? `
        <div class="kiosk-feature-settings">
          <label>Sonuç seçenekleri<textarea name="result-options" rows="3">${esc(result.join('\n'))}</textarea></label>
        </div>` : ''}
      </div>
    </section>

    <section class="kiosk-editor-block">
      <h3>Yerleşim ve Kartlar</h3>
      <div class="kiosk-design-details">
        <label>Ekran yerleşimi
          <select name="layout">
            ${Object.entries(KioskRenderer.layouts).map(([k, v]) => `<option value="${k}" ${k === design.layout ? 'selected' : ''}>${esc(v)}</option>`).join('')}
          </select>
        </label>
        <label>Vardiya konumu
          <select name="shiftPosition">
            <option value="top" ${design.shiftPosition === 'top' ? 'selected' : ''}>Üstte geniş</option>
            <option value="compact" ${design.shiftPosition === 'compact' ? 'selected' : ''}>Sağ üstte kompakt</option>
          </select>
        </label>
        <label>İstasyon
          <select name="station" disabled>
            <option value="">İstasyon seçin</option>
            ${STATIONS_LIST.map(s => `<option value="${s.id}" ${s.id === design.station ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}
          </select>
        </label>
      </div>

      <h4>Kartlar</h4>
      <div id="cards-container">
        ${design.cards.map((card, idx) => renderCardEditor(card, idx)).join('')}
      </div>
      <div class="kiosk-design-details">
        <label>Kart ekle
          <select name="new-card-kind">
            ${Object.entries(KioskRenderer.cardTypes)
              .filter(([kind]) => (kind !== 'stepper' || design.station === 'bantlama') && !design.cards.some(card => card.kind === kind))
              .map(([kind, [title]]) => `<option value="${kind}">${esc(title)}</option>`).join('')}
          </select>
        </label>
        <button type="button" class="button" data-action="add-card">Kart ekle</button>
      </div>
    </section>

    <label>İşe başlamadan önce<textarea name="before" rows="2" maxlength="1500" placeholder="Operatör başlamadan önce neyi kontrol etsin?">${esc(design.before)}</textarea></label>

    <div class="kiosk-section-title">
      <h3>Akış Adımları</h3>
      <button type="button" class="button" data-action="add-step">${KioskRenderer.stepTypes.check} Adım ekle</button>
    </div>
    <div id="steps-container">
      ${design.steps.map((step, idx) => renderStepEditor(step, idx)).join('')}
    </div>

    <label>İş bitiminde<textarea name="after" rows="2" maxlength="1500" placeholder="İş tamamlanınca operatör ne yapsın?">${esc(design.after)}</textarea></label>

    <div class="kiosk-section-title">
      <h3>Ek Bölümler</h3>
      <button type="button" class="button" data-action="add-section">+ Bölüm ekle</button>
    </div>
    <div id="sections-container">
      ${design.sections.map((sec, idx) => renderSectionEditor(sec, idx)).join('')}
    </div>

    <div class="kiosk-actions" style="margin-top: 20px; display: flex; gap: 8px; flex-wrap: wrap;">
      <button type="button" class="button" data-action="save-draft">Taslağı Kaydet</button>
      <button type="button" class="button primary" data-action="publish">Yayınla</button>
      <button type="button" class="button" data-action="show-templates">Şablon Seç</button>
    </div>
  `;

  // Form event listeners
  attachEditorListeners(form);
  renderPreview(design);
}

function renderCardEditor(card, idx) {
  const [, min, allowed] = KioskRenderer.cardTypes[card.kind];
  return `
    <fieldset class="kiosk-step-editor" data-card-index="${idx}" data-card-kind="${card.kind}">
      <legend>${esc(card.title)}</legend>
      <div class="kiosk-design-details">
        <label>Kart başlığı<input name="card-title" value="${esc(card.title)}" maxlength="80"></label>
        <label>Boyut
          <select name="card-size">
            ${Object.entries(KioskRenderer.sizes).slice(min).map(([k, v]) => `<option value="${k}" ${k === card.size ? 'selected' : ''}>${esc(v)}</option>`).join('')}
          </select>
        </label>
        <label>Kaynak
          <select name="card-source">
            ${allowed.map(key => `<option value="${key}" ${key === card.source ? 'selected' : ''}>${esc(KioskRenderer.sources[key])}</option>`).join('')}
          </select>
        </label>
      </div>
      <label>Açıklama<textarea name="card-body" rows="2" maxlength="1500">${esc(card.body)}</textarea></label>
      <div class="kiosk-actions">
        <label class="check-label"><input type="checkbox" name="card-visible" ${card.visible ? 'checked' : ''}> Görünür</label>
        <button type="button" class="button" data-action="card-up" ${idx === 0 ? 'disabled' : ''}>↑</button>
        <button type="button" class="button" data-action="card-down" ${idx === card.parentLength - 1 ? 'disabled' : ''}>↓</button>
        <button type="button" class="button" data-action="card-remove">Kaldır</button>
      </div>
    </fieldset>
  `;
}

function renderStepEditor(step, idx) {
  return `
    <fieldset class="kiosk-step-editor" data-step-index="${idx}">
      <legend>Adım ${idx + 1}</legend>
      <label>Adım adı<input name="step-label" value="${esc(step.label)}" required maxlength="100"></label>
      <label>Tür
        <select name="step-kind">
          ${Object.entries(KioskRenderer.stepTypes).map(([k, v]) => `<option value="${k}" ${k === step.kind ? 'selected' : ''}>${esc(v)}</option>`).join('')}
        </select>
      </label>
      <div class="kiosk-step-options" data-for="choice">
        <label>Seçenekler (her satır bir seçenek)<textarea name="step-options" rows="3" maxlength="740">${esc(step.options?.join('\n') || '')}</textarea></label>
      </div>
      <div class="kiosk-step-actions">
        <label class="check-label"><input type="checkbox" name="step-required" ${step.required ? 'checked' : ''}> Zorunlu</label>
        <div class="kiosk-actions">
          <button type="button" class="button" data-action="step-up" ${idx === 0 ? 'disabled' : ''}>↑</button>
          <button type="button" class="button" data-action="step-down" ${idx === step.parentLength - 1 ? 'disabled' : ''}>↓</button>
          <button type="button" class="button" data-action="step-remove">Sil</button>
        </div>
      </div>
      <label class="check-label"><input type="checkbox" name="step-interruptible" ${step.interruptible ? 'checked' : ''}> Bu adımda iş WIP alanına alınabilir</label>
    </fieldset>
  `;
}

function renderSectionEditor(sec, idx) {
  return `
    <fieldset class="kiosk-step-editor" data-section-index="${idx}">
      <legend>Ek Bölüm ${idx + 1}</legend>
      <label>Başlık<input name="section-title" value="${esc(sec.title)}" required maxlength="80"></label>
      <label>İçerik<textarea name="section-body" rows="3" maxlength="1500" required>${esc(sec.body)}</textarea></label>
      <div class="kiosk-actions">
        <button type="button" class="button" data-action="section-remove">Sil</button>
      </div>
    </fieldset>
  `;
}

function attachEditorListeners(form) {
  // Input changes -> update preview
  form.oninput = () => {
    updateDesignFromForm();
    renderPreview(state.designer.editDesign);
  };

  form.onchange = (e) => {
    // Toggle choice options visibility
    if (e.target.name === 'step-kind') {
      const fieldset = e.target.closest('.kiosk-step-editor');
      const optionsDiv = fieldset.querySelector('.kiosk-step-options');
      if (optionsDiv) optionsDiv.hidden = e.target.value !== 'choice';
    }
    // Feature settings visibility
    if (e.target.name.startsWith('feature-')) {
      const settings = e.target.closest('.kiosk-feature-question').querySelector('.kiosk-feature-settings');
      if (settings) settings.hidden = settings.disabled = !e.target.checked;
    }
    updateDesignFromForm();
    renderPreview(state.designer.editDesign);
  };

  form.onclick = (e) => {
    const action = e.target.dataset.action;
    if (!action) return;

    switch (action) {
      case 'add-step':
        state.designer.editDesign.steps.push({ label: '', kind: 'check', required: true, options: [], interruptible: false });
        renderEditor(state.designer.editDesign);
        break;
      case 'add-section':
        state.designer.editDesign.sections.push({ title: '', body: '' });
        renderEditor(state.designer.editDesign);
        break;
      case 'add-card':
        const kind = form.elements['new-card-kind'].value;
        if (kind) {
          state.designer.editDesign.cards.push(KioskRenderer.makeCard(kind));
          renderEditor(state.designer.editDesign);
        }
        break;
      case 'show-templates':
        showTemplateSelector();
        break;
      case 'save-draft':
        void saveDesign(false);
        break;
      case 'publish':
        void saveDesign(true);
        break;
      // Card actions
      case 'card-up':
      case 'card-down':
      case 'card-remove':
        handleCardAction(action, e.target.closest('[data-card-index]'));
        break;
      // Step actions
      case 'step-up':
      case 'step-down':
      case 'step-remove':
        handleStepAction(action, e.target.closest('[data-step-index]'));
        break;
      // Section actions
      case 'section-remove':
        handleSectionAction(e.target.closest('[data-section-index]'));
        break;
    }
  };
}

function updateDesignFromForm() {
  const form = document.getElementById('kiosk-design-form');
  if (!form) return;

  const design = state.designer.editDesign;
  design.title = form.elements.title?.value || '';
  design.slug = form.elements.slug?.value || '';
  design.instructions = form.elements.instructions?.value || '';
  design.layout = form.elements.layout?.value || 'sidebar';
  design.shiftPosition = form.elements.shiftPosition?.value || 'top';
  design.station = form.elements.station?.value || '';
  design.before = form.elements.before?.value || '';
  design.after = form.elements.after?.value || '';

  design.features.timer = form.elements['feature-timer']?.checked || false;
  design.features.progress = form.elements['feature-progress']?.checked ? {
    target: parseInt(form.elements['progress-target']?.value) || 50,
    unit: form.elements['progress-unit']?.value || 'adet'
  } : null;
  design.features.result = form.elements['feature-result']?.checked ?
    (form.elements['result-options']?.value || '').split('\n').filter(Boolean) : null;

  // Steps
  design.steps = [...form.querySelectorAll('[data-step-index]')].map(fs => ({
    label: fs.elements['step-label']?.value || '',
    kind: fs.elements['step-kind']?.value || 'check',
    required: fs.elements['step-required']?.checked || false,
    options: fs.elements['step-kind']?.value === 'choice' ?
      (fs.elements['step-options']?.value || '').split('\n').filter(Boolean) : [],
    interruptible: fs.elements['step-interruptible']?.checked || false
  }));

  // Sections
  design.sections = [...form.querySelectorAll('[data-section-index]')].map(fs => ({
    title: fs.elements['section-title']?.value || '',
    body: fs.elements['section-body']?.value || ''
  }));

  // Cards
  design.cards = [...form.querySelectorAll('[data-card-index]')].map(fs => ({
    kind: fs.dataset.cardKind,
    title: fs.elements['card-title']?.value || '',
    size: fs.elements['card-size']?.value || 'full',
    source: fs.elements['card-source']?.value || 'fixed',
    visible: fs.elements['card-visible']?.checked || false,
    body: fs.elements['card-body']?.value || ''
  }));
}

function handleCardAction(action, fieldset) {
  const idx = parseInt(fieldset.dataset.cardIndex);
  const cards = state.designer.editDesign.cards;
  if (action === 'card-up' && idx > 0) {
    [cards[idx - 1], cards[idx]] = [cards[idx], cards[idx - 1]];
  } else if (action === 'card-down' && idx < cards.length - 1) {
    [cards[idx], cards[idx + 1]] = [cards[idx + 1], cards[idx]];
  } else if (action === 'card-remove') {
    cards.splice(idx, 1);
  }
  renderEditor(state.designer.editDesign);
}

function handleStepAction(action, fieldset) {
  const idx = parseInt(fieldset.dataset.stepIndex);
  const steps = state.designer.editDesign.steps;
  if (action === 'step-up' && idx > 0) {
    [steps[idx - 1], steps[idx]] = [steps[idx], steps[idx - 1]];
  } else if (action === 'step-down' && idx < steps.length - 1) {
    [steps[idx], steps[idx + 1]] = [steps[idx + 1], steps[idx]];
  } else if (action === 'step-remove') {
    steps.splice(idx, 1);
  }
  renderEditor(state.designer.editDesign);
}

function handleSectionAction(fieldset) {
  const idx = parseInt(fieldset.dataset.sectionIndex);
  state.designer.editDesign.sections.splice(idx, 1);
  renderEditor(state.designer.editDesign);
}

async function saveDesign(publish) {
  const current = state.designer.currentKiosk;
  if (!current || state.designer.busy || !document.getElementById('kiosk-design-form').reportValidity()) return;
  updateDesignFromForm();
  state.designer.busy = true;
  const path = `templates/${current.slug}`;
  try {
    const retain = row => {
      state.designer.templates[current.slug] = row;
      Object.assign(current, { revision: row.revision, published: row.published });
    };
    retain(await workspaceRequest(path, 'PUT', { revision: current.revision, design: state.designer.editDesign }));
    if (publish) retain(await workspaceRequest(`${path}/publish`, 'POST', { revision: current.revision }));
    feedback(publish ? 'Şablon istasyon tabletinde yayınlandı.' : 'Taslak kaydedildi.');
  } catch (error) {
    feedback(error.message);
  } finally {
    state.designer.busy = false;
    renderCatalog();
    updateEditorTitle(state.designer.editDesign);
  }
}

function bindPairForm() {
  const panel = document.getElementById('tablet-pair-panel');
  const form = document.getElementById('tablet-pair-code-form');
  const output = document.getElementById('tablet-pair-code');
  panel.hidden = false;
  form.elements.station.innerHTML = STATIONS_LIST.map(({ id, name }) => `<option value="${id}">${name}</option>`).join('');
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const invitation = await workspaceRequest(`pair-codes/${form.elements.station.value}`, 'POST', {});
      output.textContent = `Port ${invitation.station_port}${invitation.pair_path} · Kod ${invitation.code}`;
    } catch (error) {
      output.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
}

function renderPreview(design) {
  const preview = document.getElementById('kiosk-preview');
  if (!preview) return;

  // Tablet boyutunda önizleme (380px genişlik)
  preview.innerHTML = `
    <div class="kiosk-preview-screen" style="width: 100%; max-width: 380px; margin: 0 auto;">
      ${KioskRenderer.heading(design)}
      <div class="kiosk-board-status">
        <span class="badge teal">Önizleme</span>
      </div>
      ${KioskRenderer.work(design, {
        timer: { activeMs: 125000, waitingMs: 10000, since: Date.now() - 125000, paused: false },
        quantity: 12,
        values: [true, 'KUTU-001', 450, 'Geçti'],
        result: null
      }, false, {
        station: { name: design.station || 'İstasyon' },
        shift: { operator: 'Önizleme Operatörü' },
        orders: [],
        wipAreas: [],
        reasons: {}
      })}
    </div>
  `;
}

document.addEventListener('DOMContentLoaded', initDesignerTab);

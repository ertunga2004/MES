import { kioskRequest } from "./kiosk-request.js";
import { cardTypes, layouts, makeCard, presets, sizes, sources, stations, templateCards } from "./kiosk-presets.js?v=2";
import { option, renderCards } from "./kiosk-cards.js?v=2";

const form = document.getElementById("design-form");
const fields = form.elements;
const steps = document.getElementById("steps");
const sections = document.getElementById("sections");
const catalog = document.getElementById("catalog");
const presetList = document.getElementById("preset-list");
const clearPreset = document.getElementById("clear-preset");
const feedback = document.getElementById("feedback");
const cards = document.getElementById("cards");
const cardControls = document.getElementById("card-controls");
const newCardKind = document.getElementById("new-card-kind");
const preview = document.getElementById("tablet-preview");
const endpoint = "/api/kiosk-designs";
const optionLines = value => value.split("\n").map(line => line.trim()).filter(Boolean);

let items = [];
let current = null;
let busy = false;
let selectedTemplate = "plain";
let featureOptionsEdited = false;
let draggedCard = null;

fields.station.append(option("İstasyon seçin", ""), ...Object.entries(stations).map(([key, label]) => option(label, key)));
fields.layout.append(...Object.entries(layouts).map(([key, label]) => option(label, key)));

function drawPreview() {
  const design = readDesign();
  if (design.cards === null) {
    design.cards = ["order", "instructions", "before", "steps", "timer", "result", "after", "extra", "actions"].map(makeCard);
  }
  const title = document.createElement("h3");
  title.textContent = design.title || "İstasyon adı";
  const shift = document.createElement("p");
  shift.className = "preview-shift";
  shift.textContent = "Operatör adı ve soyadı";
  preview.dataset.shiftPosition = design.shift_position;
  preview.replaceChildren(title, shift, renderCards(design, {}, { preview: true }));
}

function updateCardOrder() {
  const rows = [...cards.children];
  rows.forEach((row, index) => {
    row.querySelector('[data-card-action="up"]').disabled = index === 0;
    row.querySelector('[data-card-action="down"]').disabled = index === rows.length - 1;
  });
  const used = new Set(rows.map(row => row.dataset.kind));
  const remaining = Object.entries(cardTypes).filter(([kind]) => !used.has(kind));
  const previouslySelected = newCardKind.value;
  newCardKind.replaceChildren(...remaining.map(([kind, [label]]) => option(label, kind)));
  if (remaining.some(([kind]) => kind === previouslySelected)) newCardKind.value = previouslySelected;
  document.getElementById("card-add-controls").hidden = !remaining.length;
  document.getElementById("fixed-target").hidden = !fields.show_target.checked || !rows.some(row =>
    row.dataset.kind === "progress" && row.querySelector('[name="card_source"]').value === "fixed");
}

function addCard(value) {
  const row = document.getElementById("card-template").content.firstElementChild.cloneNode(true);
  const [title, minimum, allowedSources] = cardTypes[value.kind];
  row.dataset.kind = value.kind;
  row.querySelector("legend").textContent = title;
  row.querySelector('[name="card_title"]').value = value.title;
  row.querySelector('[name="card_body"]').value = value.body;
  row.querySelector('[name="card_visible"]').checked = value.visible;
  const size = row.querySelector('[name="card_size"]');
  size.append(...Object.entries(sizes).filter(([key], index) => index >= minimum || key === value.size)
    .map(([key, label]) => option(label, key)));
  size.value = value.size;
  const source = row.querySelector('[name="card_source"]');
  source.append(...allowedSources.map(key => option(sources[key], key)));
  source.value = value.source;
  cards.append(row);
}

function showCards(values) {
  cardControls.hidden = values === null;
  document.getElementById("configure-cards").hidden = values !== null;
  cards.replaceChildren();
  values?.forEach(addCard);
  updateCardOrder();
}

function configureFromPreset(preset) {
  const edited = new Map((readDesign().cards || []).map(card => [card.kind, card]));
  fields.layout.value = preset.layout;
  showCards(templateCards(preset).map(card => edited.get(card.kind) || card));
}

function applyPresetOptions(preset) {
  fields.timer.checked = Boolean(preset?.timer);
  fields.show_target.checked = Boolean(preset?.target);
  fields.record_result.checked = Boolean(preset?.results.length);
  fields.result_options.value = (preset?.results || []).join("\n");
  syncResult();
}

function renderPresetSelection() {
  for (const choice of presetList.children) {
    choice.setAttribute("aria-pressed", String(choice.value === selectedTemplate));
  }
  clearPreset.setAttribute("aria-pressed", String(selectedTemplate === "plain"));
}

for (const [key, preset] of Object.entries(presets)) {
  const choice = document.createElement("button");
  choice.type = "button";
  choice.value = key;
  choice.className = "preset-choice";
  const title = document.createElement("strong");
  const description = document.createElement("span");
  title.textContent = preset.title;
  description.textContent = preset.description;
  choice.append(title, description);
  choice.onclick = () => {
    if (selectedTemplate === key && !cardControls.hidden) return;
    selectedTemplate = key;
    if (!current && !featureOptionsEdited) applyPresetOptions(preset);
    configureFromPreset(preset);
    renderPresetSelection();
    drawPreview();
  };
  presetList.append(choice);
}

clearPreset.onclick = () => {
  selectedTemplate = "plain";
  if (!current && !featureOptionsEdited) applyPresetOptions(null);
  if (!cardControls.hidden) fields.layout.value = "single";
  renderPresetSelection();
  drawPreview();
};

function updateStepOrder() {
  [...steps.children].forEach((row, index) => {
    row.querySelector("legend").textContent = `Adım ${index + 1}`;
    row.querySelector('[data-action="up"]').disabled = index === 0;
    row.querySelector('[data-action="down"]').disabled = index === steps.children.length - 1;
  });
}

function addStep(value = {}) {
  if (steps.children.length >= 30) return;
  const row = document.getElementById("step-template").content.firstElementChild.cloneNode(true);
  const kind = row.querySelector('[name="step_kind"]');
  const options = row.querySelector('[name="step_options"]');
  row.querySelector('[name="step_label"]').value = value.label || "";
  row.querySelector('[name="step_required"]').checked = value.required ?? true;
  row.querySelector('[name="step_interruptible"]').checked = Boolean(value.interruptible);
  kind.value = value.kind || "check";
  options.value = (value.options || []).join("\n");
  function syncOptions() {
    const visible = kind.value === "choice";
    row.querySelector("[data-options]").hidden = !visible;
    options.required = visible;
  }
  kind.addEventListener("change", syncOptions);
  syncOptions();
  row.querySelector('[data-action="up"]').onclick = () => {
    row.previousElementSibling?.before(row);
    updateStepOrder();
    drawPreview();
  };
  row.querySelector('[data-action="down"]').onclick = () => {
    row.nextElementSibling?.after(row);
    updateStepOrder();
    drawPreview();
  };
  row.querySelector('[data-action="remove"]').onclick = () => { row.remove(); updateStepOrder(); drawPreview(); };
  steps.append(row);
  updateStepOrder();
}

function addSection(value = {}) {
  if (sections.children.length >= 20) return;
  const row = document.getElementById("section-template").content.firstElementChild.cloneNode(true);
  row.querySelector('[name="section_title"]').value = value.title || "";
  row.querySelector('[name="section_body"]').value = value.body || "";
  row.querySelector("button").onclick = () => { row.remove(); drawPreview(); };
  sections.append(row);
}

function syncResult() {
  const visible = fields.record_result.checked;
  document.getElementById("result-options").hidden = !visible;
  fields.result_options.required = visible;
}

function renderCatalog() {
  catalog.replaceChildren();
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-button station-option";
    button.textContent = `${item.draft.title} · ${item.published ? `Sürüm ${item.published}` : "Taslak"}`;
    button.setAttribute("aria-current", String(item.slug === current?.slug));
    button.onclick = () => { if (!busy) { feedback.textContent = ""; show(item); } };
    catalog.append(button);
  }
}

function show(item) {
  current = item;
  featureOptionsEdited = false;
  const draft = item?.draft || {};
  selectedTemplate = draft.template || "plain";
  renderPresetSelection();
  fields.slug.value = item?.slug || "";
  fields.slug.readOnly = Boolean(item);
  fields.title.value = draft.title || "";
  fields.instructions.value = draft.instructions || "";
  fields.before.value = draft.before || "";
  fields.after.value = draft.after || "";
  fields.layout.value = draft.layout || "single";
  fields.station.value = draft.station || "";
  fields.shift_position.value = draft.shift_position || "top";
  fields.target_quantity.value = draft.target_quantity ?? "";
  fields.target_unit.value = draft.target_unit || "";
  fields.waiting_areas.value = (draft.waiting_areas || []).join("\n");
  fields.timer.checked = Boolean(draft.timer);
  fields.show_target.checked = Boolean(draft.show_target);
  fields.record_result.checked = Boolean(draft.result_options?.length);
  fields.result_options.value = (draft.result_options || []).join("\n");
  syncResult();
  steps.replaceChildren();
  (draft.steps || [{}]).forEach(addStep);
  sections.replaceChildren();
  (draft.sections || []).forEach(addSection);
  showCards(draft.cards ?? null);
  document.getElementById("design-heading").textContent = item ? "Kiosku düzenle" : "Yeni kiosk";
  document.getElementById("design-status").textContent = item?.published
    ? `Yayında · Sürüm ${item.published}${item.revision !== item.published_revision ? " · Yayınlanmamış taslak var" : ""}` : "Taslak";
  document.getElementById("published-info").hidden = !item?.published;
  if (item?.published) document.getElementById("operator-link").href = item.path;
  document.getElementById("active-info").textContent = item?.active
    ? `Açık iş: ${item.active.operator} · ${item.active.order.id} · Sürüm ${item.active.version}` : "Açık iş yok";
  const finishedInfo = document.getElementById("finished-info");
  const last = item?.last_completed;
  finishedInfo.hidden = !last;
  if (last) finishedInfo.textContent = `Son tamamlanan iş: ${last.order.id} · ${last.operator}${last.result ? ` · ${last.result}` : ""}`;
  renderCatalog();
  drawPreview();
}

function readDesign() {
  return {
    title: fields.title.value,
    template: selectedTemplate,
    instructions: fields.instructions.value,
    before: fields.before.value,
    after: fields.after.value,
    layout: cardControls.hidden ? null : fields.layout.value,
    station: fields.station.value,
    shift_position: fields.shift_position.value,
    target_quantity: fields.target_quantity.valueAsNumber || null,
    target_unit: fields.target_unit.value,
    waiting_areas: optionLines(fields.waiting_areas.value),
    cards: cardControls.hidden ? null : [...cards.children].map(row => ({
      kind: row.dataset.kind,
      title: row.querySelector('[name="card_title"]').value,
      size: row.querySelector('[name="card_size"]').value,
      source: row.querySelector('[name="card_source"]').value,
      visible: row.querySelector('[name="card_visible"]').checked,
      body: row.querySelector('[name="card_body"]').value,
    })),
    timer: fields.timer.checked,
    show_target: fields.show_target.checked,
    result_options: fields.record_result.checked ? optionLines(fields.result_options.value) : [],
    steps: [...steps.children].map(row => ({
      label: row.querySelector('[name="step_label"]').value,
      kind: row.querySelector('[name="step_kind"]').value,
      required: row.querySelector('[name="step_required"]').checked,
      interruptible: row.querySelector('[name="step_interruptible"]').checked,
      options: optionLines(row.querySelector('[name="step_options"]').value),
    })),
    sections: [...sections.children].map(row => ({
      title: row.querySelector('[name="section_title"]').value,
      body: row.querySelector('[name="section_body"]').value,
    })),
  };
}

function remember(item) {
  items = [...items.filter(entry => entry.slug !== item.slug), item].sort((a, b) => a.slug.localeCompare(b.slug));
  show(item);
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  form.inert = true;
  const buttons = [...form.querySelectorAll('button[type="submit"]')];
  buttons.forEach(button => { button.disabled = true; });
  feedback.textContent = "Kaydediliyor…";
  const publish = event.submitter?.value === "publish";
  try {
    const slug = fields.slug.value.trim();
    let saved = await kioskRequest(`${endpoint}/${encodeURIComponent(slug)}`, "PUT", {
      revision: current?.revision || 0, design: readDesign(),
    });
    remember(saved);
    if (publish) {
      saved = await kioskRequest(`${endpoint}/${encodeURIComponent(slug)}/publish`, "POST", { revision: saved.revision });
      remember(saved);
    }
    feedback.textContent = publish ? `Yayınlandı. Operatör adresi ${saved.path}` : "Taslak kaydedildi.";
  } catch (error) {
    feedback.textContent = error.message;
  } finally {
    busy = false;
    form.inert = false;
    buttons.forEach(button => { button.disabled = false; });
  }
});

document.getElementById("new-kiosk").onclick = () => { if (!busy) { show(null); feedback.textContent = ""; fields.title.focus(); } };
document.getElementById("add-step").onclick = () => { addStep(); drawPreview(); };
document.getElementById("add-section").onclick = () => { addSection(); drawPreview(); };
document.getElementById("configure-cards").onclick = () => {
  const preset = presets[selectedTemplate];
  if (preset) configureFromPreset(preset);
  else showCards(["order", "instructions", "steps", "timer", "progress", "result", "before", "after", "extra", "actions"].map(makeCard));
  drawPreview();
};
document.getElementById("add-card").onclick = () => {
  addCard(makeCard(newCardKind.value));
  updateCardOrder();
  drawPreview();
};
cards.addEventListener("click", event => {
  const control = event.target.closest("[data-card-action]");
  if (!control) return;
  const row = control.closest("[data-kind]");
  if (control.dataset.cardAction === "up") row.previousElementSibling?.before(row);
  if (control.dataset.cardAction === "down") row.nextElementSibling?.after(row);
  if (control.dataset.cardAction === "remove") row.remove();
  updateCardOrder();
  drawPreview();
});
cards.addEventListener("dragstart", event => {
  if (!event.target.matches(".card-drag")) return;
  draggedCard = event.target.closest("[data-kind]");
  event.dataTransfer.setData("text/plain", draggedCard.dataset.kind);
});
cards.addEventListener("dragover", event => {
  if (draggedCard && event.target.closest("[data-kind]")) event.preventDefault();
});
cards.addEventListener("drop", event => {
  const target = event.target.closest("[data-kind]");
  if (!target || !draggedCard) return;
  event.preventDefault();
  if (target.compareDocumentPosition(draggedCard) & Node.DOCUMENT_POSITION_PRECEDING) target.after(draggedCard);
  else target.before(draggedCard);
  draggedCard = null;
  updateCardOrder();
  drawPreview();
});
cards.addEventListener("dragend", () => { draggedCard = null; });
fields.record_result.onchange = syncResult;
for (const field of [fields.timer, fields.show_target, fields.record_result, fields.result_options]) {
  field.addEventListener("input", () => { featureOptionsEdited = true; });
}
const optionalCards = { timer: "timer", show_target: "progress", record_result: "result" };
form.addEventListener("input", event => {
  const kind = optionalCards[event.target.name];
  if (kind && event.target.checked && !cardControls.hidden && !cards.querySelector(`[data-kind="${kind}"]`)) {
    addCard(makeCard(kind));
  }
  updateCardOrder();
  drawPreview();
});
show(null);
try {
  items = await kioskRequest(endpoint);
  renderCatalog();
} catch (error) {
  feedback.textContent = error.message;
}

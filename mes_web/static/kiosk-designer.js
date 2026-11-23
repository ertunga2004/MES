import { kioskRequest } from "./kiosk-request.js";

const form = document.getElementById("design-form");
const fields = form.elements;
const steps = document.getElementById("steps");
const sections = document.getElementById("sections");
const catalog = document.getElementById("catalog");
const feedback = document.getElementById("feedback");
const endpoint = "/api/kiosk-designs";
const optionLines = value => value.split("\n").map(line => line.trim()).filter(Boolean);

let items = [];
let current = null;
let busy = false;

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
  };
  row.querySelector('[data-action="down"]').onclick = () => {
    row.nextElementSibling?.after(row);
    updateStepOrder();
  };
  row.querySelector('[data-action="remove"]').onclick = () => { row.remove(); updateStepOrder(); };
  steps.append(row);
  updateStepOrder();
}

function addSection(value = {}) {
  if (sections.children.length >= 20) return;
  const row = document.getElementById("section-template").content.firstElementChild.cloneNode(true);
  row.querySelector('[name="section_title"]').value = value.title || "";
  row.querySelector('[name="section_body"]').value = value.body || "";
  row.querySelector("button").onclick = () => row.remove();
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
  const draft = item?.draft || {};
  fields.slug.value = item?.slug || "";
  fields.slug.readOnly = Boolean(item);
  fields.title.value = draft.title || "";
  fields.instructions.value = draft.instructions || "";
  fields.timer.checked = Boolean(draft.timer);
  fields.show_target.checked = Boolean(draft.show_target);
  fields.record_result.checked = Boolean(draft.result_options?.length);
  fields.result_options.value = (draft.result_options || []).join("\n");
  syncResult();
  steps.replaceChildren();
  (draft.steps || [{}]).forEach(addStep);
  sections.replaceChildren();
  (draft.sections || []).forEach(addSection);
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
}

function readDesign() {
  return {
    title: fields.title.value,
    instructions: fields.instructions.value,
    timer: fields.timer.checked,
    show_target: fields.show_target.checked,
    result_options: fields.record_result.checked ? optionLines(fields.result_options.value) : [],
    steps: [...steps.children].map(row => ({
      label: row.querySelector('[name="step_label"]').value,
      kind: row.querySelector('[name="step_kind"]').value,
      required: row.querySelector('[name="step_required"]').checked,
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
document.getElementById("add-step").onclick = () => addStep();
document.getElementById("add-section").onclick = () => addSection();
fields.record_result.onchange = syncResult;
show(null);
try {
  items = await kioskRequest(endpoint);
  renderCatalog();
} catch (error) {
  feedback.textContent = error.message;
}

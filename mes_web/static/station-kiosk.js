import { kioskRequest } from "./kiosk-request.js";
import { option, renderCards, renderParked, renderStep, updateClocks } from "./kiosk-cards.js?v=2";

const slug = window.location.pathname.split("/").pop();
const url = `/api/station-kiosks/${encodeURIComponent(slug)}`;
const start = document.getElementById("start");
const work = document.getElementById("work");
const steps = document.getElementById("work-steps");
const feedback = document.getElementById("feedback");
const timer = document.getElementById("timer");
const shell = document.getElementById("operator-shell");
const support = document.getElementById("operator-support");
const idleCards = document.getElementById("station-cards-idle");
const workCards = document.getElementById("station-cards-work");
const parkedFallback = document.getElementById("parked-fallback");
const finishButton = work.querySelector('button[type="submit"]');
const legacyResult = document.getElementById("work-result");
let board;
let identity;
let busy = false;
let refreshing = false;
let writeGeneration = 0;

function updateTimer() {
  updateClocks(workCards, board?.active);
  if (timer.hidden || !board?.active) return;
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(board.active.started_at)) / 1000));
  timer.textContent = [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
    .map(value => String(value).padStart(2, "0")).join(":");
}

function draftKey(runId) {
  return `mes-station:${slug}:${runId}`;
}

function enteredWork() {
  const values = [...work.querySelectorAll("[data-step-index]")].map(input => {
    if (input.type === "checkbox") return input.checked;
    if (input.type === "number") return input.value === "" ? null : input.valueAsNumber;
    return input.value || null;
  });
  const quantity = work.elements.namedItem("quantity");
  const result = work.querySelector('select[name="result"]:enabled');
  return { values, result: result?.value || "", quantity: quantity?.valueAsNumber || (quantity?.value === "0" ? 0 : null) };
}

function restoreWork(active) {
  let saved = active;
  try {
    const draft = JSON.parse(sessionStorage.getItem(draftKey(active.run_id)) || "null");
    if (draft && (draft.revision ?? 0) === (active.revision ?? 0)) saved = draft;
  } catch { /* The active server record still opens if browser storage is unavailable. */ }
  [...work.querySelectorAll("[data-step-index]")].forEach((input, index) => {
    if (input.type === "checkbox") input.checked = saved.values?.[index] === true;
    else input.value = saved.values?.[index] ?? "";
  });
  const result = work.querySelector('select[name="result"]:enabled');
  if (result) result.value = saved.result || "";
  const quantity = work.elements.namedItem("quantity");
  if (quantity) quantity.value = saved.quantity ?? "";
  quantity?.dispatchEvent(new Event("input"));
}

function render(next) {
  const sameWork = next.active && next.active.run_id === board?.active?.run_id &&
    next.active.revision === board.active.revision;
  board = next;
  const active = board.active;
  const design = board.design;
  const nextIdentity = JSON.stringify([board.version, active?.run_id, active?.revision, board.order, board.waiting, board.line_shift_active, board.parked]);
  if (identity === nextIdentity) return;
  identity = nextIdentity;
  const pendingInputs = sameWork
    ? ["incident_note", "material_name", "material_amount", "park_area", "park_step", "park_item", "park_note"]
      .flatMap(name => {
        const field = work.elements.namedItem(name);
        return field ? [[name, field.value]] : [];
      })
    : [];
  const focused = sameWork && work.contains(document.activeElement) ? document.activeElement : null;
  shell.dataset.template = design.template || "plain";
  document.title = `${design.title} · MES`;
  document.getElementById("station-title").textContent = design.title;
  document.getElementById("version").textContent = `Sürüm ${board.version}`;
  const configured = Array.isArray(design.cards);
  shell.classList.toggle("has-custom-cards", configured);
  shell.dataset.shiftPosition = design.shift_position;
  document.querySelector(".operator-order").hidden = configured;
  idleCards.hidden = !configured || Boolean(active);
  workCards.hidden = !configured || !active;
  document.getElementById("order").textContent = board.order?.id || "Aktif iş emri bekleniyor";
  const stationState = document.getElementById("station-state");
  stationState.hidden = design.template !== "status";
  stationState.textContent = active ? "Durum: Açık iş var" : board.order ? "Durum: İşe hazır" : "Durum: İş emri bekleniyor";
  const target = document.getElementById("target");
  target.hidden = !(design.show_target && board.order);
  target.textContent = board.order ? `İş emri hedefi ${board.order.quantity} ${board.order.unit}` : "";
  const instructions = document.getElementById("instructions");
  instructions.hidden = !design.instructions;
  instructions.textContent = design.instructions;
  document.getElementById("extra-sections").replaceChildren(...design.sections.map(section => {
    const card = document.createElement("section");
    card.className = "station-block station-stack";
    const title = document.createElement("h3");
    const body = document.createElement("p");
    title.textContent = section.title;
    body.textContent = section.body;
    body.className = "preserve-lines";
    card.append(title, body);
    return card;
  }));
  timer.hidden = !(design.timer && active);
  for (const kind of ["before", "after"]) {
    const note = document.getElementById(kind);
    note.hidden = !design[kind];
    note.textContent = design[kind];
  }
  support.hidden = configured || (!design.instructions && !design.sections.length && timer.hidden && !design.before && !design.after);
  shell.classList.toggle("has-support", !support.hidden);
  updateTimer();
  start.hidden = Boolean(active) || !board.order;
  work.hidden = !active;
  document.getElementById("worker").textContent = active ? `Operatör ${active.operator}` : "";
  steps.hidden = configured;
  steps.replaceChildren(...(active && !configured ? design.steps.map(renderStep) : []));
  legacyResult.hidden = configured || !design.result_options.length;
  const legacySelect = legacyResult.querySelector("select");
  legacySelect.disabled = configured || !design.result_options.length;
  legacySelect.required = !legacySelect.disabled;
  legacySelect.replaceChildren(option("Seç", ""), ...design.result_options.map(value => option(value)));
  for (const target of [idleCards, workCards]) {
    target.replaceChildren(...(target.hidden ? [] : [renderCards(design, board)]));
  }
  parkedFallback.hidden = Boolean(active || !board.parked?.length || idleCards.querySelector('[data-card="wip"]'));
  parkedFallback.replaceChildren(...(parkedFallback.hidden ? [] : renderParked(board.parked, null)));
  finishButton.hidden = Boolean(workCards.querySelector('[data-run-action="finish"]'));
  if (active) restoreWork(active);
  for (const [name, value] of pendingInputs) {
    const field = work.elements.namedItem(name);
    if (!field) continue;
    field.value = value;
  }
  if (focused?.dataset.stepIndex != null) {
    work.querySelector(`[data-step-index="${focused.dataset.stepIndex}"]`)?.focus({ preventScroll: true });
  } else if (focused?.name) {
    work.elements.namedItem(focused.name)?.focus?.({ preventScroll: true });
  }
  updateTimer();
}

async function refresh() {
  if (busy || refreshing) return;
  refreshing = true;
  const generation = writeGeneration;
  try {
    const next = await kioskRequest(url);
    if (generation === writeGeneration) render(next);
  } catch (error) {
    if (generation === writeGeneration) feedback.textContent = error.message;
  } finally { refreshing = false; }
}

async function write(form, action, payload, message) {
  busy = true;
  writeGeneration += 1;
  form.inert = true;
  try {
    render(await kioskRequest(`${url}/${action}`, "POST", payload));
    if (action === "finish" || payload.operation === "park") {
      try { sessionStorage.removeItem(draftKey(payload.run_id)); } catch { /* Browser storage is optional. */ }
    }
    feedback.textContent = message;
  } catch (error) {
    feedback.textContent = error.message;
  } finally {
    busy = false;
    form.inert = false;
  }
}

start.addEventListener("submit", event => {
  event.preventDefault();
  if (busy || !board?.order || board.active) return;
  write(start, "start", { run_id: crypto.randomUUID(), operator: start.elements.operator.value,
    order_id: board.order.id, order_key: board.order.key, version: board.version }, "İş başlatıldı.");
});

work.addEventListener("submit", event => {
  event.preventDefault();
  if (busy || !board?.active) return;
  write(work, "finish", { run_id: board.active.run_id, revision: board.active.revision ?? 0, ...enteredWork() }, "İş tamamlandı.");
});

work.addEventListener("click", event => {
  const operation = event.target.closest('button[type="button"][data-run-action]')?.dataset.runAction;
  if (!operation || busy || !board?.active) return;
  const { run_id, revision = 0 } = board.active;
  const payload = { run_id, revision, operation, ...enteredWork() };
  const messages = {
    save: "İlerleme kaydedildi.", pause: "Sayaç duraklatıldı.", resume: "Sayaç devam ediyor.",
    incident: "Duruş bildirimi kaydedildi.", "material-request": "Malzeme talebi kaydedildi.", park: "İş bekleme alanına alındı.",
  };
  if (operation === "incident") payload.note = work.elements.incident_note.value;
  if (operation === "material-request") {
    payload.note = work.elements.material_name.value;
    payload.amount = work.elements.material_amount.valueAsNumber || null;
  }
  if (operation === "park") {
    payload.area = work.elements.park_area.value;
    payload.item = work.elements.park_item.value;
    payload.note = work.elements.park_note.value;
    payload.step_index = work.elements.park_step.value === "" ? null : Number(work.elements.park_step.value);
  }
  write(work, "update", payload, messages[operation]);
});

document.getElementById("operator-shell").addEventListener("click", event => {
  const control = event.target.closest('[data-run-action="pickup"]');
  if (!control || busy || board?.active) return;
  const row = control.closest(".station-block");
  write(row, "pickup", { run_id: control.dataset.runId, operator: row.querySelector("input").value }, "Bekleyen iş açıldı.");
});

work.addEventListener("input", () => {
  if (!board?.active) return;
  try { sessionStorage.setItem(draftKey(board.active.run_id), JSON.stringify({ ...enteredWork(), revision: board.active.revision ?? 0 })); }
  catch { /* Work can still be completed without a local draft. */ }
});

refresh();
setInterval(refresh, 3000);
setInterval(updateTimer, 1000);

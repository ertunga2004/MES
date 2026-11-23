import { kioskRequest } from "./kiosk-request.js";

const slug = window.location.pathname.split("/").pop();
const url = `/api/station-kiosks/${encodeURIComponent(slug)}`;
const start = document.getElementById("start");
const work = document.getElementById("work");
const steps = document.getElementById("work-steps");
const feedback = document.getElementById("feedback");
const timer = document.getElementById("timer");
let board;
let identity;
let busy = false;
let refreshing = false;
let writeGeneration = 0;

function option(label, value = label) {
  const entry = document.createElement("option");
  entry.textContent = label;
  entry.value = value;
  return entry;
}

function renderStep(step) {
  const label = document.createElement("label");
  const caption = document.createElement("span");
  caption.textContent = step.label;
  const input = document.createElement(step.kind === "choice" ? "select" : "input");
  if (step.kind === "choice") input.append(option("Seç", ""), ...step.options.map(value => option(value)));
  else if (step.kind === "check") { input.type = "checkbox"; label.className = "station-check"; }
  else if (step.kind === "number") { input.type = "number"; input.step = "any"; }
  else { input.type = "text"; input.maxLength = 500; }
  input.required = step.required;
  if (step.kind === "check") label.append(input, caption);
  else label.append(caption, input);
  return label;
}

function updateTimer() {
  if (timer.hidden || !board?.active) return;
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(board.active.started_at)) / 1000));
  timer.textContent = [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
    .map(value => String(value).padStart(2, "0")).join(":");
}

function draftKey(runId) {
  return `mes-station:${slug}:${runId}`;
}

function enteredWork() {
  const values = [...steps.querySelectorAll("input, select")].map(input => {
    if (input.type === "checkbox") return input.checked;
    if (input.type === "number") return input.value === "" ? null : input.valueAsNumber;
    return input.value || null;
  });
  return { values, result: work.elements.result.value };
}

function restoreWork(runId) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(draftKey(runId)) || "null");
    if (!saved) return;
    [...steps.querySelectorAll("input, select")].forEach((input, index) => {
      if (input.type === "checkbox") input.checked = saved.values[index] === true;
      else input.value = saved.values[index] ?? "";
    });
    work.elements.result.value = saved.result;
  } catch { /* The active server record still opens if browser storage is unavailable. */ }
}

function render(next) {
  board = next;
  const active = board.active;
  const design = board.design;
  const nextIdentity = JSON.stringify([board.version, active?.run_id, board.order?.id, board.order?.key, board.order?.quantity, board.order?.unit]);
  if (identity === nextIdentity) return;
  identity = nextIdentity;
  document.title = `${design.title} · MES`;
  document.getElementById("station-title").textContent = design.title;
  document.getElementById("version").textContent = `Sürüm ${board.version}`;
  document.getElementById("order").textContent = board.order?.id || "Aktif iş emri bekleniyor";
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
  updateTimer();
  start.hidden = Boolean(active) || !board.order;
  work.hidden = !active;
  document.getElementById("worker").textContent = active ? `Operatör ${active.operator}` : "";
  steps.replaceChildren(...(active ? design.steps.map(renderStep) : []));
  document.getElementById("work-result").hidden = !design.result_options.length;
  work.elements.result.required = Boolean(design.result_options.length);
  work.elements.result.replaceChildren(option("Seç", ""), ...design.result_options.map(value => option(value)));
  if (active) restoreWork(active.run_id);
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

async function write(form, action, payload) {
  busy = true;
  writeGeneration += 1;
  form.inert = true;
  const submit = form.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    render(await kioskRequest(`${url}/${action}`, "POST", payload));
    if (action === "finish") {
      try { sessionStorage.removeItem(draftKey(payload.run_id)); } catch { /* Browser storage is optional. */ }
    }
    feedback.textContent = action === "start" ? "İş başlatıldı." : "İş tamamlandı.";
  } catch (error) {
    feedback.textContent = error.message;
  } finally {
    busy = false;
    form.inert = false;
    submit.disabled = false;
  }
}

start.addEventListener("submit", event => {
  event.preventDefault();
  if (busy || !board?.order || board.active) return;
  write(start, "start", { run_id: crypto.randomUUID(), operator: start.elements.operator.value,
    order_id: board.order.id, order_key: board.order.key, version: board.version });
});

work.addEventListener("submit", event => {
  event.preventDefault();
  if (busy || !board?.active) return;
  write(work, "finish", { run_id: board.active.run_id, ...enteredWork() });
});

work.addEventListener("input", () => {
  if (!board?.active) return;
  try { sessionStorage.setItem(draftKey(board.active.run_id), JSON.stringify(enteredWork())); }
  catch { /* Work can still be completed without a local draft. */ }
});

refresh();
setInterval(refresh, 3000);
setInterval(updateTimer, 1000);

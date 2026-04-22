const state = {
  moduleId: "",
  deviceId: "",
  snapshot: null,
  socket: null,
  busy: false,
};

const els = {
  screenTitle: document.getElementById("screenTitle"),
  technicianNameInput: document.getElementById("technicianNameInput"),
  connectionState: document.getElementById("connectionState"),
  alarmBand: document.getElementById("alarmBand"),
  alarmTitle: document.getElementById("alarmTitle"),
  alarmMeta: document.getElementById("alarmMeta"),
  openCount: document.getElementById("openCount"),
  ackCount: document.getElementById("ackCount"),
  resolvedTodayCount: document.getElementById("resolvedTodayCount"),
  activeRequestsList: document.getElementById("activeRequestsList"),
  resolvedTodayList: document.getElementById("resolvedTodayList"),
  recentRequestsList: document.getElementById("recentRequestsList"),
};

function storageKey(suffix) {
  return `mes_technician_${state.deviceId}_${suffix}`;
}

function readTechnicianName() {
  return window.localStorage.getItem(storageKey("name")) || "Teknisyen";
}

function writeTechnicianName(value) {
  window.localStorage.setItem(storageKey("name"), String(value || "").trim() || "Teknisyen");
}

function technicianName() {
  return String(els.technicianNameInput.value || "").trim() || "Teknisyen";
}

function setConnectionState(text) {
  els.connectionState.textContent = text;
}

function safeText(value, fallback = "-") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function statusLabel(status) {
  const map = {
    open: "Acik",
    acknowledged: "Kabul edildi",
    resolved: "Cozuldu",
  };
  return map[String(status || "").trim()] || safeText(status, "-");
}

function shortDateTime(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function durationText(durationMs) {
  const totalSeconds = Math.max(0, Math.floor(Number(durationMs || 0) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function durationSince(value) {
  const parsed = new Date(value || "");
  if (Number.isNaN(parsed.getTime())) {
    return 0;
  }
  return Math.max(0, Date.now() - parsed.getTime());
}

function liveDurations(row) {
  const status = String((row || {}).status || "");
  if (status === "open") {
    const elapsed = durationSince(row.created_at);
    return {
      response: elapsed,
      repair: 0,
      total: elapsed,
    };
  }
  if (status === "acknowledged") {
    return {
      response: Number(row.response_duration_ms || durationSince(row.created_at) - durationSince(row.acknowledged_at) || 0),
      repair: durationSince(row.acknowledged_at),
      total: durationSince(row.created_at),
    };
  }
  return {
    response: Number(row.response_duration_ms || 0),
    repair: Number(row.repair_duration_ms || 0),
    total: Number(row.total_duration_ms || 0),
  };
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof body === "object" && body !== null ? body.detail : body;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    const error = new Error(message);
    error.detail = detail;
    error.status = response.status;
    throw error;
  }
  return body;
}

async function resolveModuleId() {
  const url = new URL(window.location.href);
  const queryModuleId = (url.searchParams.get("module_id") || "").trim();
  if (queryModuleId) {
    return queryModuleId;
  }
  const modules = await fetchJson("/api/modules");
  if (!Array.isArray(modules) || modules.length === 0) {
    throw new Error("MODULE_NOT_FOUND");
  }
  return String(modules[0].module_id || "").trim();
}

async function loadBootstrap() {
  const query = new URLSearchParams({
    device_id: state.deviceId,
    technician_name: technicianName(),
  });
  state.snapshot = await fetchJson(`/api/modules/${state.moduleId}/technician/bootstrap?${query.toString()}`);
  render();
}

function currentActorPayload() {
  return {
    device_id: state.deviceId,
    device_name: safeText((state.snapshot || {}).device?.device_name, state.deviceId),
    technician_name: technicianName(),
  };
}

async function performAction(callback) {
  if (state.busy) {
    return;
  }
  state.busy = true;
  render();
  try {
    await callback();
  } catch (error) {
    window.alert(String(error.message || error));
  } finally {
    state.busy = false;
    await loadBootstrap();
  }
}

function createStatusPill(status) {
  const pill = document.createElement("div");
  pill.className = `status-pill status-${safeText(status, "open")}`;
  pill.textContent = statusLabel(status);
  return pill;
}

function createDetailBox(label, value) {
  const box = document.createElement("div");
  box.className = "detail-box";
  const labelEl = document.createElement("span");
  labelEl.textContent = label;
  const valueEl = document.createElement("strong");
  valueEl.textContent = safeText(value);
  box.appendChild(labelEl);
  box.appendChild(valueEl);
  return box;
}

function createTimerBox(label, value) {
  const box = document.createElement("div");
  box.className = "timer-box";
  const labelEl = document.createElement("span");
  labelEl.textContent = label;
  const valueEl = document.createElement("strong");
  valueEl.textContent = durationText(value);
  box.appendChild(labelEl);
  box.appendChild(valueEl);
  return box;
}

function requestTitle(row) {
  return `${safeText(row.line_id || row.station_id, "Hat")} / ${safeText(row.station_name, "Istasyon")}`;
}

function createRequestCard(row) {
  const card = document.createElement("div");
  card.className = `request-card ${safeText(row.status, "open")}`;

  const top = document.createElement("div");
  top.className = "request-top";
  const title = document.createElement("div");
  title.className = "request-title";
  const heading = document.createElement("h3");
  heading.textContent = requestTitle(row);
  const meta = document.createElement("p");
  meta.className = "muted";
  meta.textContent = `${safeText(row.operator_code || row.operator_id, "Operator")} - ${safeText(row.operator_name, "Isim yok")} | Cagri ${shortDateTime(row.created_at)}`;
  title.appendChild(heading);
  title.appendChild(meta);
  top.appendChild(title);
  top.appendChild(createStatusPill(row.status));

  const reason = document.createElement("p");
  reason.className = "reason-text";
  reason.textContent = safeText(row.reason || row.fault_code, "Sebep belirtilmedi");

  const details = document.createElement("div");
  details.className = "detail-grid";
  details.appendChild(createDetailBox("Kiosk", row.device_name || row.device_id));
  details.appendChild(createDetailBox("Tekrar", row.repeat_count || 1));
  details.appendChild(createDetailBox("Ariza", row.is_active_fault ? "Aktif" : "Kapali"));

  const timers = document.createElement("div");
  timers.className = "timer-grid";
  const live = liveDurations(row);
  timers.appendChild(createTimerBox("Cevap", live.response));
  timers.appendChild(createTimerBox("Giderme", live.repair));
  timers.appendChild(createTimerBox("Toplam", live.total));

  const actions = document.createElement("div");
  actions.className = "request-actions";
  const ackButton = document.createElement("button");
  ackButton.type = "button";
  ackButton.className = "primary-button";
  ackButton.textContent = "Cevapla";
  ackButton.disabled = state.busy || row.status !== "open";
  ackButton.addEventListener("click", () => handleAcknowledge(row.request_id));

  const resolveButton = document.createElement("button");
  resolveButton.type = "button";
  resolveButton.className = "resolve-button";
  resolveButton.textContent = "Tamamla";
  resolveButton.disabled = state.busy || row.status !== "acknowledged";
  resolveButton.addEventListener("click", () => handleResolve(row.request_id));

  actions.appendChild(ackButton);
  actions.appendChild(resolveButton);

  card.appendChild(top);
  card.appendChild(reason);
  card.appendChild(details);
  card.appendChild(timers);
  card.appendChild(actions);
  return card;
}

function createHistoryRow(row) {
  const wrapper = document.createElement("div");
  wrapper.className = "history-row";
  const top = document.createElement("div");
  top.className = "history-top";
  const title = document.createElement("strong");
  title.textContent = requestTitle(row);
  top.appendChild(title);
  top.appendChild(createStatusPill(row.status));

  const reason = document.createElement("p");
  reason.textContent = safeText(row.reason || row.fault_code, "Sebep belirtilmedi");
  const meta = document.createElement("p");
  meta.className = "muted";
  const live = liveDurations(row);
  meta.textContent = `${safeText(row.operator_name || row.operator_code, "Operator")} | ${shortDateTime(row.resolved_at || row.last_requested_at || row.created_at)} | Toplam ${durationText(live.total)}`;

  wrapper.appendChild(top);
  wrapper.appendChild(reason);
  wrapper.appendChild(meta);
  return wrapper;
}

function renderList(container, rows, emptyText, createRow) {
  container.innerHTML = "";
  if (!Array.isArray(rows) || rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  for (const row of rows) {
    container.appendChild(createRow(row));
  }
}

function renderAlarm() {
  const snapshot = state.snapshot || {};
  const summary = snapshot.summary || {};
  const active = Array.isArray(snapshot.active_requests) ? snapshot.active_requests : [];
  const openCount = Number(summary.open_count || 0);
  const ackCount = Number(summary.acknowledged_count || 0);
  els.openCount.textContent = String(openCount);
  els.ackCount.textContent = String(ackCount);
  els.resolvedTodayCount.textContent = String(summary.resolved_today_count || 0);
  els.alarmBand.classList.toggle("alarm", openCount > 0);
  if (active.length > 0) {
    const first = active[0];
    const live = liveDurations(first);
    els.alarmTitle.textContent = `${openCount + ackCount} aktif cagri`;
    els.alarmMeta.textContent = `${requestTitle(first)} | ${safeText(first.reason || first.fault_code, "Sebep yok")} | Bekleme ${durationText(live.total)}`;
  } else {
    els.alarmTitle.textContent = "Aktif cagri yok";
    els.alarmMeta.textContent = "Cozulen cagrilar gecmis panelinde gorunur.";
  }
}

function render() {
  const snapshot = state.snapshot || {};
  const device = snapshot.device || {};
  const module = snapshot.module || {};
  els.screenTitle.textContent = `${safeText(module.title, "MES")} / ${safeText(device.device_name, state.deviceId)}`;
  renderAlarm();
  renderList(
    els.activeRequestsList,
    snapshot.active_requests || [],
    "Aktif teknisyen cagrisi yok",
    createRequestCard,
  );
  renderList(
    els.resolvedTodayList,
    snapshot.resolved_today || [],
    "Bugun cozulen cagri yok",
    createHistoryRow,
  );
  renderList(
    els.recentRequestsList,
    snapshot.recent_requests || [],
    "Gecmis cagri yok",
    createHistoryRow,
  );
}

async function handleAcknowledge(requestId) {
  await performAction(async () => {
    await fetchJson(`/api/modules/${state.moduleId}/technician/requests/${encodeURIComponent(requestId)}/acknowledge`, {
      method: "POST",
      body: JSON.stringify(currentActorPayload()),
    });
  });
}

async function handleResolve(requestId) {
  await performAction(async () => {
    await fetchJson(`/api/modules/${state.moduleId}/technician/requests/${encodeURIComponent(requestId)}/resolve`, {
      method: "POST",
      body: JSON.stringify(currentActorPayload()),
    });
  });
}

function connectSocket() {
  if (state.socket) {
    state.socket.onclose = null;
    state.socket.close();
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const query = new URLSearchParams({ technician_name: technicianName() });
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/modules/${encodeURIComponent(state.moduleId)}/technician/${encodeURIComponent(state.deviceId)}?${query.toString()}`);
  state.socket = socket;
  socket.addEventListener("open", () => {
    setConnectionState("Canli");
  });
  socket.addEventListener("close", () => {
    if (state.socket !== socket) {
      return;
    }
    setConnectionState("Baglanti koptu");
    window.setTimeout(connectSocket, 2000);
  });
  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type !== "technician_snapshot") {
      return;
    }
    state.snapshot = payload.data || null;
    render();
  });
}

async function handleTechnicianNameChange() {
  writeTechnicianName(technicianName());
  await loadBootstrap();
  connectSocket();
}

async function init() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  state.deviceId = decodeURIComponent(parts[parts.length - 1] || "");
  if (!state.deviceId) {
    window.alert("DEVICE_ID_REQUIRED");
    return;
  }
  els.technicianNameInput.value = readTechnicianName();
  try {
    setConnectionState("Hazirlaniyor");
    state.moduleId = await resolveModuleId();
    await loadBootstrap();
    connectSocket();
    window.setInterval(render, 1000);
  } catch (error) {
    setConnectionState("Hata");
    window.alert(String(error.message || error));
  }
}

els.technicianNameInput.addEventListener("change", handleTechnicianNameChange);
window.addEventListener("load", init);

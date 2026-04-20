const state = {
  moduleId: "",
  deviceId: "",
  snapshot: null,
  socket: null,
  busy: false,
  drafts: {
    faultReasonText: "",
    qualityReasonByItem: {},
  },
};

const els = {
  screenTitle: document.getElementById("screenTitle"),
  operatorSelect: document.getElementById("operatorSelect"),
  connectionState: document.getElementById("connectionState"),
  lineStateText: document.getElementById("lineStateText"),
  deviceMetaText: document.getElementById("deviceMetaText"),
  metricOee: document.getElementById("metricOee"),
  metricAvailability: document.getElementById("metricAvailability"),
  metricPerformance: document.getElementById("metricPerformance"),
  metricQuality: document.getElementById("metricQuality"),
  activeOrderTitle: document.getElementById("activeOrderTitle"),
  activeOrderMeta: document.getElementById("activeOrderMeta"),
  activeOrderContents: document.getElementById("activeOrderContents"),
  maintenancePanel: document.getElementById("maintenancePanel"),
  maintenanceTitle: document.getElementById("maintenanceTitle"),
  maintenanceProgress: document.getElementById("maintenanceProgress"),
  maintenanceChecklist: document.getElementById("maintenanceChecklist"),
  maintenanceNote: document.getElementById("maintenanceNote"),
  bigActionButton: document.getElementById("bigActionButton"),
  systemStartButton: document.getElementById("systemStartButton"),
  secondaryShiftStopButton: document.getElementById("secondaryShiftStopButton"),
  faultStateText: document.getElementById("faultStateText"),
  helpButton: document.getElementById("helpButton"),
  faultClearButton: document.getElementById("faultClearButton"),
  helpStateText: document.getElementById("helpStateText"),
  faultSelect: document.getElementById("faultSelect"),
  faultReasonButton: document.getElementById("faultReasonButton"),
  faultReasonPreview: document.getElementById("faultReasonPreview"),
  faultStartButton: document.getElementById("faultStartButton"),
  workOrderList: document.getElementById("workOrderList"),
  recentItemsList: document.getElementById("recentItemsList"),
};

function deviceStorageKey(suffix) {
  return `mes_kiosk_${state.deviceId}_${suffix}`;
}

function checklistStorageKey(sessionId) {
  return `mes_kiosk_checklist_${sessionId}`;
}

function readStoredOperatorId() {
  return window.localStorage.getItem(deviceStorageKey("operator_id")) || "";
}

function writeStoredOperatorId(value) {
  window.localStorage.setItem(deviceStorageKey("operator_id"), value || "");
}

function readStoredStationId() {
  return window.localStorage.getItem(deviceStorageKey("station_id")) || "";
}

function writeStoredStationId(value) {
  window.localStorage.setItem(deviceStorageKey("station_id"), value || "");
}

function readStoredDeviceName() {
  return window.localStorage.getItem(deviceStorageKey("device_name")) || "";
}

function writeStoredDeviceName(value) {
  window.localStorage.setItem(deviceStorageKey("device_name"), value || "");
}

function setConnectionState(text) {
  els.connectionState.textContent = text;
}

function pct(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return `${Number(value).toFixed(1)}%`;
}

function safeText(value, fallback = "-") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function cleanReasonText(value) {
  return String(value ?? "").trim();
}

function faultReasonText() {
  return cleanReasonText(state.drafts.faultReasonText);
}

function setFaultReasonText(value) {
  state.drafts.faultReasonText = cleanReasonText(value);
}

function qualityReasonText(item) {
  const itemId = String((item || {}).item_id || "").trim();
  const draft = itemId ? state.drafts.qualityReasonByItem[itemId] : "";
  if (cleanReasonText(draft)) {
    return cleanReasonText(draft);
  }
  return cleanReasonText((item || {}).override_reason_text);
}

function setQualityReasonText(itemId, value) {
  const normalizedItemId = String(itemId || "").trim();
  if (!normalizedItemId) {
    return;
  }
  const cleaned = cleanReasonText(value);
  if (cleaned) {
    state.drafts.qualityReasonByItem[normalizedItemId] = cleaned;
  } else {
    delete state.drafts.qualityReasonByItem[normalizedItemId];
  }
}

function promptReason(message, initialValue = "") {
  const result = window.prompt(message, initialValue);
  if (result === null) {
    return null;
  }
  return cleanReasonText(result);
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

function statusLabel(status) {
  const map = {
    active: "Aktif",
    pending_approval: "Onay Bekliyor",
    queued: "Sirada",
    completed: "Tamamlandi",
  };
  return map[status] || safeText(status, "-");
}

function operationalLabel(status) {
  const map = {
    idle_ready: "Vardiya hazir",
    opening_checklist: "Acilis bakimi bekleniyor",
    shift_active_running: "Hat calisiyor",
    manual_fault_active: "Manuel ariza aktif",
    closing_checklist: "Kapanis bakimi bekleniyor",
  };
  return map[status] || "Veri bekleniyor";
}

function colorLabel(colorCode) {
  const map = {
    red: "Kirmizi",
    blue: "Mavi",
    yellow: "Sari",
  };
  return map[String(colorCode || "").trim().toLowerCase()] || "Bilinmeyen";
}

function currentActorPayload() {
  const snapshot = state.snapshot || {};
  const device = snapshot.device || {};
  const selectedOperatorId = els.operatorSelect.value || readStoredOperatorId() || device.last_operator_id || "";
  const boundStationId = readStoredStationId() || device.bound_station_id || "";
  const deviceName = readStoredDeviceName() || device.device_name || state.deviceId;
  return {
    device_id: state.deviceId,
    device_name: deviceName,
    bound_station_id: boundStationId,
    operator_id: selectedOperatorId,
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
  const bootstrap = await fetchJson(`/api/modules/${state.moduleId}/kiosk/bootstrap?device_id=${encodeURIComponent(state.deviceId)}`);
  state.snapshot = bootstrap;
  const visibleItemIds = new Set(((bootstrap.recent_items || []).map((item) => String((item || {}).item_id || "").trim())).filter(Boolean));
  for (const itemId of Object.keys(state.drafts.qualityReasonByItem)) {
    if (!visibleItemIds.has(itemId)) {
      delete state.drafts.qualityReasonByItem[itemId];
    }
  }
  const device = bootstrap.device || {};
  if (!readStoredDeviceName()) {
    writeStoredDeviceName(device.device_name || state.deviceId);
  }
  if (!readStoredStationId() && device.bound_station_id) {
    writeStoredStationId(device.bound_station_id);
  }
  if (!readStoredOperatorId()) {
    const bootstrapOperatorId = (bootstrap.operator || {}).operator_id || device.last_operator_id || ((bootstrap.operators || [])[0] || {}).operator_id || "";
    if (bootstrapOperatorId) {
      writeStoredOperatorId(bootstrapOperatorId);
    }
  }
  render();
}

async function registerDevice() {
  await fetchJson(`/api/modules/${state.moduleId}/kiosk/register`, {
    method: "POST",
    body: JSON.stringify(currentActorPayload()),
  });
}

function getActiveChecklistSession() {
  const maintenance = (state.snapshot || {}).maintenance || {};
  const operationalState = (state.snapshot || {}).operational_state || "";
  if (operationalState === "opening_checklist") {
    return maintenance.opening_session || null;
  }
  if (operationalState === "closing_checklist") {
    return maintenance.closing_session || null;
  }
  return null;
}

function getChecklistLocalState(sessionId) {
  if (!sessionId) {
    return { steps: {}, note: "" };
  }
  try {
    return JSON.parse(window.sessionStorage.getItem(checklistStorageKey(sessionId)) || "{\"steps\":{},\"note\":\"\"}");
  } catch {
    return { steps: {}, note: "" };
  }
}

function setChecklistLocalState(sessionId, payload) {
  if (!sessionId) {
    return;
  }
  window.sessionStorage.setItem(checklistStorageKey(sessionId), JSON.stringify(payload));
}

function clearChecklistLocalState(sessionId) {
  if (!sessionId) {
    return;
  }
  window.sessionStorage.removeItem(checklistStorageKey(sessionId));
}

function mergedChecklist(session) {
  if (!session) {
    return { steps: [], note: "" };
  }
  const local = getChecklistLocalState(session.sessionId);
  const mergedSteps = (session.steps || []).map((step) => {
    const localEntry = local.steps[String(step.stepCode || "")] || {};
    return {
      ...step,
      completed: Boolean(localEntry.completed ?? step.completed),
    };
  });
  return {
    steps: mergedSteps,
    note: local.note || session.note || "",
  };
}

function checklistProgress(steps) {
  const total = steps.length;
  const done = steps.filter((step) => step.completed).length;
  const ready = steps.every((step) => !step.required || step.completed);
  return { total, done, ready };
}

function renderOperatorSelect() {
  const snapshot = state.snapshot || {};
  const operators = Array.isArray(snapshot.operators) ? snapshot.operators : [];
  const currentValue = readStoredOperatorId() || (snapshot.operator || {}).operator_id || (snapshot.device || {}).last_operator_id || "";
  els.operatorSelect.innerHTML = "";
  for (const operator of operators) {
    const option = document.createElement("option");
    option.value = String(operator.operator_id || "");
    option.textContent = `${safeText(operator.operator_code, "-")} - ${safeText(operator.operator_name, "-")}`;
    if (option.value === currentValue) {
      option.selected = true;
    }
    els.operatorSelect.appendChild(option);
  }
  if (!els.operatorSelect.value && operators.length > 0) {
    els.operatorSelect.value = String(operators[0].operator_id || "");
    writeStoredOperatorId(els.operatorSelect.value);
  }
}

function renderFaultOptions() {
  const snapshot = state.snapshot || {};
  const options = Array.isArray(snapshot.fault_options) ? snapshot.fault_options : [];
  const currentValue = els.faultSelect.value;
  els.faultSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Sebep sec";
  els.faultSelect.appendChild(placeholder);
  for (const row of options) {
    const option = document.createElement("option");
    option.value = String(row.fault_type_code || row.fault_type_id || "");
    option.textContent = safeText(row.fault_reason_tr || row.fault_type_code, "Ariza");
    if (option.value === currentValue) {
      option.selected = true;
    }
    els.faultSelect.appendChild(option);
  }
}

function renderLineStatus() {
  const snapshot = state.snapshot || {};
  const lineStatus = snapshot.line_status || {};
  const device = snapshot.device || {};
  const header = lineStatus.header || {};
  const kpis = lineStatus.kpis || {};
  els.screenTitle.textContent = `${safeText(device.device_name, state.deviceId)} / ${safeText((snapshot.operator || {}).operator_name, "Operator sec")}`;
  els.lineStateText.textContent = safeText(header.state_summary, operationalLabel(snapshot.operational_state));
  els.deviceMetaText.textContent = `${operationalLabel(snapshot.operational_state)} | Istasyon ${safeText(device.bound_station_id, "-")}`;
  els.metricOee.textContent = pct(kpis.oee);
  els.metricAvailability.textContent = pct(kpis.availability);
  els.metricPerformance.textContent = pct(kpis.performance);
  els.metricQuality.textContent = pct(kpis.quality);
}

function createContentBadges(contentCounts) {
  const wrapper = document.createDocumentFragment();
  for (const colorCode of ["red", "blue", "yellow"]) {
    const badge = document.createElement("div");
    badge.className = `content-badge color-${colorCode}`;
    badge.textContent = `${colorLabel(colorCode)} ${Number((contentCounts || {})[colorCode] || 0)}`;
    wrapper.appendChild(badge);
  }
  return wrapper;
}

function renderActiveOrderContents(order) {
  els.activeOrderContents.innerHTML = "";
  if (!order) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "Icerik bilgisi bekleniyor";
    els.activeOrderContents.appendChild(empty);
    return;
  }
  els.activeOrderContents.appendChild(createContentBadges(order.content_counts || {}));
}

function renderPrimaryPanel() {
  const snapshot = state.snapshot || {};
  const workOrders = snapshot.work_orders || {};
  const activeOrder = workOrders.active_order || null;
  const queue = Array.isArray(workOrders.queue) ? workOrders.queue : [];
  const displayOrder = activeOrder || queue[0] || null;
  const bigAction = snapshot.big_action || {};
  const systemStart = snapshot.system_start || {};
  const maintenanceSession = getActiveChecklistSession();

  if (activeOrder) {
    els.activeOrderTitle.textContent = `${safeText(activeOrder.order_id)} / ${safeText(activeOrder.stock_name, activeOrder.stock_code)}`;
    els.activeOrderMeta.textContent = `${statusLabel(activeOrder.status)} | ${activeOrder.completed_qty || 0} / ${activeOrder.qty || 0} | Kalan ${activeOrder.remaining_qty || 0}`;
  } else if (queue.length > 0) {
    els.activeOrderTitle.textContent = `${safeText(queue[0].order_id)} hazir bekliyor`;
    els.activeOrderMeta.textContent = `${safeText(queue[0].stock_name, queue[0].stock_code)} | Siradaki is emri`;
  } else {
    els.activeOrderTitle.textContent = "Is emri bekleniyor";
    els.activeOrderMeta.textContent = "Ana ekran sirasi burada gorunur";
  }

  renderActiveOrderContents(displayOrder);
  els.bigActionButton.textContent = safeText(bigAction.label, "Hazirlaniyor");
  els.bigActionButton.disabled = state.busy || !Boolean(bigAction.enabled);
  els.systemStartButton.textContent = safeText(systemStart.label, "Sistem Start");
  els.systemStartButton.disabled = state.busy || !Boolean(systemStart.enabled);

  const showShiftStop = snapshot.operational_state === "shift_active_running";
  els.secondaryShiftStopButton.hidden = !showShiftStop;
  els.secondaryShiftStopButton.disabled = state.busy || !showShiftStop;

  if (!maintenanceSession) {
    els.maintenancePanel.classList.add("hidden");
    els.maintenanceChecklist.innerHTML = "";
    els.maintenanceNote.value = "";
    return;
  }

  const merged = mergedChecklist(maintenanceSession);
  const progress = checklistProgress(merged.steps);
  els.bigActionButton.disabled = state.busy || progress.total === 0 || !progress.ready;
  els.maintenancePanel.classList.remove("hidden");
  els.maintenanceTitle.textContent = maintenanceSession.phase === "closing" ? "Kapanis Bakimi" : "Acilis Bakimi";
  els.maintenanceProgress.textContent = `${progress.done} / ${progress.total}`;
  els.maintenanceNote.value = merged.note;
  els.maintenanceChecklist.innerHTML = "";
  for (const step of merged.steps) {
    const wrapper = document.createElement("label");
    wrapper.className = "checklist-item";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = Boolean(step.completed);
    checkbox.dataset.stepCode = String(step.stepCode || "");
    checkbox.addEventListener("change", handleChecklistChange);
    const text = document.createElement("span");
    text.textContent = step.required ? `${safeText(step.stepLabel)} *` : safeText(step.stepLabel);
    wrapper.appendChild(checkbox);
    wrapper.appendChild(text);
    els.maintenanceChecklist.appendChild(wrapper);
  }
}

function renderFaultPanel() {
  const snapshot = state.snapshot || {};
  const activeFault = snapshot.active_fault || null;
  const helpRequest = snapshot.help_request || null;
  if (activeFault) {
    els.faultStateText.textContent = `${safeText(activeFault.reason, "Ariza")} / ${shortDateTime(activeFault.startedAt)}`;
  } else {
    els.faultStateText.textContent = "Aktif ariza yok";
  }
  if (helpRequest) {
    els.helpStateText.textContent = `Yardim istegi ${safeText(helpRequest.status, "open")} / tekrar ${helpRequest.repeatCount || 1}`;
  } else {
    els.helpStateText.textContent = "Teknisyen cagrisi yok";
  }
  els.faultReasonPreview.textContent = faultReasonText() || "Harici sebep yok";
  els.faultReasonButton.textContent = faultReasonText() ? "Sebebi Duzenle" : "Sebep Yaz";
  const helpEnabled = ["shift_active_running", "manual_fault_active"].includes(snapshot.operational_state);
  els.helpButton.disabled = state.busy || !helpEnabled;
  els.faultReasonButton.disabled = state.busy || Boolean(activeFault);
  els.faultStartButton.disabled = state.busy || Boolean(activeFault);
  els.faultClearButton.disabled = state.busy || !Boolean(activeFault);
}

function createQueuedOrderButton(row) {
  const snapshot = state.snapshot || {};
  const hasActiveOrder = Boolean((snapshot.work_orders || {}).active_order);
  const button = document.createElement("button");
  button.type = "button";
  button.className = `row-action-button${row.is_top_queue ? " top-queue" : ""}`;
  button.textContent = row.is_top_queue ? "Siradakini Baslat" : "Bu Isi Baslat";
  button.disabled = state.busy || snapshot.operational_state !== "shift_active_running" || hasActiveOrder;
  button.addEventListener("click", () => handleQueuedWorkOrderStart(row.order_id));
  return button;
}

function renderWorkOrders() {
  const rows = ((state.snapshot || {}).work_orders || {}).ordered || [];
  els.workOrderList.innerHTML = "";
  if (rows.length === 0) {
    els.workOrderList.innerHTML = '<div class="empty-state">Goruntulenecek is emri yok</div>';
    return;
  }
  rows.forEach((row, index) => {
    const wrapper = document.createElement("div");
    wrapper.className = "work-order-row";

    const indexBox = document.createElement("div");
    indexBox.className = "order-index";
    indexBox.textContent = String(index + 1);

    const main = document.createElement("div");
    main.className = "work-order-main";

    const header = document.createElement("div");
    header.className = "work-order-header";
    const titleBlock = document.createElement("div");
    titleBlock.innerHTML = `
      <strong>${safeText(row.order_id)}</strong>
      <p class="muted">${safeText(row.stock_name, row.stock_code)} | ${row.completed_qty || 0} / ${row.qty || 0}</p>
    `;
    const status = document.createElement("div");
    status.className = `status-pill status-${safeText(row.status, "queued")}`;
    status.textContent = statusLabel(row.status);
    header.appendChild(titleBlock);
    header.appendChild(status);

    const contentRow = document.createElement("div");
    contentRow.className = "order-content-row";
    contentRow.appendChild(createContentBadges(row.content_counts || {}));

    main.appendChild(header);
    main.appendChild(contentRow);

    const actions = document.createElement("div");
    actions.className = "order-row-actions";
    if (row.status === "queued") {
      actions.appendChild(createQueuedOrderButton(row));
    }

    wrapper.appendChild(indexBox);
    wrapper.appendChild(main);
    wrapper.appendChild(actions);
    els.workOrderList.appendChild(wrapper);
  });
}

function createQualityButton(item, label, value) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  if (String(item.classification || "").toUpperCase() === value) {
    button.classList.add("active");
  }
  button.disabled = state.busy || !item.can_override;
  button.addEventListener("click", () => handleQualityOverride(item.item_id, value));
  return button;
}

function createColorChip(item) {
  const chip = document.createElement("div");
  const colorCode = String(item.display_color || "").trim().toLowerCase();
  chip.className = `color-chip${colorCode ? ` color-${colorCode}` : ""}`;
  chip.textContent = safeText(item.color_label || colorLabel(colorCode), "Bilinmeyen");
  return chip;
}

function renderRecentItems() {
  const items = (state.snapshot || {}).recent_items || [];
  els.recentItemsList.innerHTML = "";
  if (items.length === 0) {
    els.recentItemsList.innerHTML = '<div class="empty-state">Kalite duzeltilecek urun yok</div>';
    return;
  }
  for (const item of items) {
    const wrapper = document.createElement("div");
    wrapper.className = "recent-item-row";

    const top = document.createElement("div");
    top.className = "recent-item-top";

    const left = document.createElement("div");
    left.className = "recent-item-meta";
    left.innerHTML = `
      <strong>#${safeText(item.item_id)}</strong>
      <p class="muted">${shortDateTime(item.completed_at)} | ${safeText(item.classification, "-")}</p>
    `;
    left.appendChild(createColorChip(item));

    const right = document.createElement("div");
    right.className = `status-pill ${item.can_override ? "status-active" : "status-completed"}`;
    right.textContent = item.can_override ? "Duzenlenebilir" : "Kilitli";

    top.appendChild(left);
    top.appendChild(right);

    const actions = document.createElement("div");
    actions.className = "quality-actions";
    actions.appendChild(createQualityButton(item, "Saglam", "GOOD"));
    actions.appendChild(createQualityButton(item, "Rework", "REWORK"));
    actions.appendChild(createQualityButton(item, "Hurda", "SCRAP"));

    const reasonTools = document.createElement("div");
    reasonTools.className = "reason-tools";

    const reasonButton = document.createElement("button");
    reasonButton.type = "button";
    reasonButton.className = "secondary-button note-button";
    reasonButton.textContent = qualityReasonText(item) ? "Sebebi Duzenle" : "Sebep Yaz";
    reasonButton.disabled = state.busy || !item.can_override;
    reasonButton.addEventListener("click", () => handleQualityReasonEdit(item.item_id));

    const reasonPreview = document.createElement("p");
    reasonPreview.className = "reason-preview";
    reasonPreview.textContent = qualityReasonText(item) || "Sebep yok";

    reasonTools.appendChild(reasonButton);
    reasonTools.appendChild(reasonPreview);

    wrapper.appendChild(top);
    wrapper.appendChild(actions);
    wrapper.appendChild(reasonTools);
    els.recentItemsList.appendChild(wrapper);
  }
}

function render() {
  renderOperatorSelect();
  renderFaultOptions();
  renderLineStatus();
  renderPrimaryPanel();
  renderFaultPanel();
  renderWorkOrders();
  renderRecentItems();
}

function handleChecklistChange() {
  const session = getActiveChecklistSession();
  if (!session) {
    return;
  }
  const steps = {};
  els.maintenanceChecklist.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    steps[String(checkbox.dataset.stepCode || "")] = { completed: checkbox.checked };
  });
  setChecklistLocalState(session.sessionId, {
    steps,
    note: els.maintenanceNote.value || "",
  });
  renderPrimaryPanel();
}

els.maintenanceNote.addEventListener("input", () => {
  const session = getActiveChecklistSession();
  if (!session) {
    return;
  }
  const local = getChecklistLocalState(session.sessionId);
  setChecklistLocalState(session.sessionId, {
    ...local,
    note: els.maintenanceNote.value || "",
  });
});

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
    render();
  }
}

async function requestWorkOrderStart(orderId = "", transitionReason = "") {
  try {
    await fetchJson(`/api/modules/${state.moduleId}/kiosk/work-orders/start`, {
      method: "POST",
      body: JSON.stringify({
        ...currentActorPayload(),
        ...(orderId ? { order_id: orderId } : {}),
        ...(transitionReason ? { transition_reason: transitionReason } : {}),
      }),
    });
  } catch (error) {
    const detail = error.detail;
    const code = detail && typeof detail === "object" ? String(detail.code || "") : "";
    if (code === "KIOSK_QUEUE_REASON_REQUIRED" || code === "WORK_ORDER_REASON_REQUIRED") {
      const fallbackOrderId = orderId || String(detail.order_id || detail.requested_order_id || "");
      const reason = window.prompt(
        code === "KIOSK_QUEUE_REASON_REQUIRED"
          ? `Siradaki ilk is emri ${safeText(detail.priority_order_id)} beklerken ${safeText(detail.requested_order_id || fallbackOrderId)} baslatiliyor. Sebep yazin.`
          : `Is emri gecis sebebi zorunlu. Sebep yazin.`,
        transitionReason || "",
      );
      if (!reason || !reason.trim()) {
        return false;
      }
      return requestWorkOrderStart(fallbackOrderId, reason.trim());
    }
    throw error;
  }
  return true;
}

async function handleBigAction() {
  const snapshot = state.snapshot || {};
  const action = (snapshot.big_action || {}).action || "";
  await performAction(async () => {
    if (action === "shift_start") {
      await fetchJson(`/api/modules/${state.moduleId}/kiosk/shift/start`, {
        method: "POST",
        body: JSON.stringify(currentActorPayload()),
      });
    } else if (action === "maintenance_complete") {
      const session = getActiveChecklistSession();
      if (!session) {
        return;
      }
      const merged = mergedChecklist(session);
      const completedSteps = merged.steps.filter((step) => step.completed).map((step) => ({ step_code: step.stepCode, completed: true }));
      await fetchJson(`/api/modules/${state.moduleId}/kiosk/maintenance/complete`, {
        method: "POST",
        body: JSON.stringify({
          ...currentActorPayload(),
          phase: session.phase,
          completed_steps: completedSteps,
          note: merged.note || "",
        }),
      });
      clearChecklistLocalState(session.sessionId);
    } else if (action === "work_order_start_next") {
      await requestWorkOrderStart("");
    } else if (action === "work_order_accept") {
      await fetchJson(`/api/modules/${state.moduleId}/kiosk/work-orders/accept-active`, {
        method: "POST",
        body: JSON.stringify({}),
      });
    }
    await loadBootstrap();
  });
}

async function handleSystemStart() {
  await performAction(async () => {
    await fetchJson(`/api/modules/${state.moduleId}/kiosk/system/start`, {
      method: "POST",
      body: JSON.stringify(currentActorPayload()),
    });
    await loadBootstrap();
  });
}

async function handleShiftStop() {
  await performAction(async () => {
    await fetchJson(`/api/modules/${state.moduleId}/kiosk/shift/stop`, {
      method: "POST",
      body: JSON.stringify(currentActorPayload()),
    });
    await loadBootstrap();
  });
}

async function handleHelpRequest() {
  await performAction(async () => {
    await fetchJson(`/api/modules/${state.moduleId}/kiosk/help/request`, {
      method: "POST",
      body: JSON.stringify(currentActorPayload()),
    });
    await loadBootstrap();
  });
}

function handleFaultReasonEdit() {
  const reason = promptReason("Harici ariza sebebini yazin.", faultReasonText());
  if (reason === null) {
    return;
  }
  setFaultReasonText(reason);
  renderFaultPanel();
}

async function handleFaultStart() {
  await performAction(async () => {
    let reasonText = faultReasonText();
    if (!els.faultSelect.value && !reasonText) {
      const prompted = promptReason("Hazir sebep secmediyseniz ariza sebebini yazin.", "");
      if (prompted === null || !prompted) {
        return;
      }
      setFaultReasonText(prompted);
      reasonText = prompted;
    }
    await fetchJson(`/api/modules/${state.moduleId}/kiosk/fault/start`, {
      method: "POST",
      body: JSON.stringify({
        ...currentActorPayload(),
        reason_code: els.faultSelect.value || "",
        reason_text: reasonText,
      }),
    });
    setFaultReasonText("");
    await loadBootstrap();
  });
}

async function handleFaultClear() {
  await performAction(async () => {
    await fetchJson(`/api/modules/${state.moduleId}/kiosk/fault/clear`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    await loadBootstrap();
  });
}

async function handleQueuedWorkOrderStart(orderId) {
  await performAction(async () => {
    await requestWorkOrderStart(orderId);
    await loadBootstrap();
  });
}

function handleQualityReasonEdit(itemId) {
  const normalizedItemId = String(itemId || "").trim();
  if (!normalizedItemId) {
    return;
  }
  const currentItem = ((state.snapshot || {}).recent_items || []).find((item) => String((item || {}).item_id || "").trim() === normalizedItemId) || {};
  const reason = promptReason(`Urun #${normalizedItemId} icin opsiyonel sebep girin.`, qualityReasonText(currentItem));
  if (reason === null) {
    return;
  }
  setQualityReasonText(normalizedItemId, reason);
  renderRecentItems();
}

async function handleQualityOverride(itemId, classification) {
  await performAction(async () => {
    const normalizedItemId = String(itemId || "").trim();
    const reasonText = cleanReasonText(state.drafts.qualityReasonByItem[normalizedItemId] || "");
    await fetchJson(`/api/modules/${state.moduleId}/kiosk/quality/override`, {
      method: "POST",
      body: JSON.stringify({
        item_id: itemId,
        classification,
        reason_text: reasonText,
      }),
    });
    delete state.drafts.qualityReasonByItem[normalizedItemId];
    await loadBootstrap();
  });
}

async function handleOperatorChange() {
  writeStoredOperatorId(els.operatorSelect.value || "");
  await performAction(async () => {
    await registerDevice();
    await loadBootstrap();
  });
}

function connectSocket() {
  if (state.socket) {
    state.socket.close();
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  state.socket = new WebSocket(`${protocol}://${window.location.host}/ws/modules/${encodeURIComponent(state.moduleId)}/kiosk/${encodeURIComponent(state.deviceId)}`);
  state.socket.addEventListener("open", () => {
    setConnectionState("Canli");
  });
  state.socket.addEventListener("close", () => {
    setConnectionState("Baglanti koptu");
    window.setTimeout(connectSocket, 2000);
  });
  state.socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type !== "kiosk_snapshot") {
      return;
    }
    state.snapshot = payload.data || null;
    render();
  });
}

async function init() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  state.deviceId = decodeURIComponent(parts[parts.length - 1] || "");
  if (!state.deviceId) {
    window.alert("DEVICE_ID_REQUIRED");
    return;
  }
  try {
    setConnectionState("Hazirlaniyor");
    state.moduleId = await resolveModuleId();
    await loadBootstrap();
    await registerDevice();
    await loadBootstrap();
    connectSocket();
  } catch (error) {
    setConnectionState("Hata");
    window.alert(String(error.message || error));
  }
}

els.bigActionButton.addEventListener("click", handleBigAction);
els.systemStartButton.addEventListener("click", handleSystemStart);
els.secondaryShiftStopButton.addEventListener("click", handleShiftStop);
els.helpButton.addEventListener("click", handleHelpRequest);
els.faultReasonButton.addEventListener("click", handleFaultReasonEdit);
els.faultClearButton.addEventListener("click", handleFaultClear);
els.faultStartButton.addEventListener("click", handleFaultStart);
els.operatorSelect.addEventListener("change", handleOperatorChange);

window.addEventListener("load", init);

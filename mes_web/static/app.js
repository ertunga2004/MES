const DEFAULT_MODULE_ID = "konveyor_main";
const RECONNECT_DELAYS = [1000, 2000, 5000, 10000, 15000];

const PRESET_LABELS = {
  start: "Baslat",
  stop: "Durdur",
  rev: "Ters Yon",
  status: "Durum",
  q: "Q Test",
  pickplace: "Pick Place",
  "__reset_counts__": "Sayac Sifirla",
  "cal x": "Cal Bos",
  "cal k": "Cal Kirmizi",
  "cal s": "Cal Sari",
  "cal m": "Cal Mavi",
};

const TOKEN_LABELS = {
  auto: "Otomatik",
  manual: "Manuel",
  run: "Calisiyor",
  running: "Calisiyor",
  stopped: "Durusta",
  stop: "Durdu",
  wait_arm: "Robot Bekliyor",
  idle: "Beklemede",
  unknown: "-",
  forward: "Ileri",
  fwd: "Ileri",
  reverse: "Ters",
  rev: "Ters",
  online: "Online",
  offline: "Offline",
  degraded: "Degrede",
  red: "Kirmizi",
  yellow: "Sari",
  blue: "Mavi",
  alarm: "Alarm",
  normal: "Normal",
  good: "Iyi",
  warn: "Uyari",
  bad: "Kritik",
  neutral: "Normal",
  full_live: "Tam Canli",
  preset_live: "Preset Canli",
  read_only: "Sadece Izleme",
  live_ops: "Canli Operasyon",
  target: "Hedef Bazli",
  ideal_cycle: "Ideal Cycle",
  runtime_state: "Runtime State",
  tablet_log: "Tablet Log",
  ready: "Hazir",
  bootstrapping: "Bootstrapping",
  live: "Canli",
  reconnecting: "Reconnect",
};

const state = {
  moduleId: new URLSearchParams(window.location.search).get("module") || DEFAULT_MODULE_ID,
  activeTab: new URLSearchParams(window.location.search).get("tab") || "operations",
  runtime: "bootstrapping",
  snapshot: null,
  ws: null,
  reconnectAttempt: 0,
  reconnectTimer: null,
  oeeControlBusy: false,
};

const els = {
  moduleTitle: document.getElementById("module-title"),
  moduleSubtitle: document.getElementById("module-subtitle"),
  runtimeBadge: document.getElementById("runtime-badge"),
  snapshotAt: document.getElementById("snapshot-at"),
  connectionBanner: document.getElementById("connection-banner"),
  tabButtons: Array.from(document.querySelectorAll(".tab-button")),
  operationsTab: document.getElementById("tab-operations"),
  oeeTab: document.getElementById("tab-oee"),
  overviewMeta: document.getElementById("overview-meta"),
  connectionCards: document.getElementById("connection-cards"),
  systemGrid: document.getElementById("system-grid"),
  hardwareGrid: document.getElementById("hardware-grid"),
  visionPanel: document.getElementById("vision-panel"),
  visionGrid: document.getElementById("vision-grid"),
  countCards: document.getElementById("count-cards"),
  commandMode: document.getElementById("command-mode"),
  presetButtons: document.getElementById("preset-buttons"),
  manualCommandForm: document.getElementById("manual-command-form"),
  manualCommandInput: document.getElementById("manual-command-input"),
  manualCommandSubmit: document.getElementById("manual-command-submit"),
  commandFeedback: document.getElementById("command-feedback"),
  logList: document.getElementById("log-list"),
  oeeUpdatedAt: document.getElementById("oee-updated-at"),
  oeeSource: document.getElementById("oee-source"),
  oeeControlSummary: document.getElementById("oee-control-summary"),
  oeeShiftOptions: document.getElementById("oee-shift-options"),
  oeeModeOptions: document.getElementById("oee-mode-options"),
  oeeSelectedWindow: document.getElementById("oee-selected-window"),
  oeeShiftStart: document.getElementById("oee-shift-start"),
  oeeShiftStop: document.getElementById("oee-shift-stop"),
  oeeControlStats: document.getElementById("oee-control-stats"),
  oeeTargetQty: document.getElementById("oee-target-qty"),
  oeeTargetApply: document.getElementById("oee-target-apply"),
  oeeIdealCycle: document.getElementById("oee-ideal-cycle"),
  oeeIdealCycleApply: document.getElementById("oee-ideal-cycle-apply"),
  oeePlannedStop: document.getElementById("oee-planned-stop"),
  oeePlannedStopApply: document.getElementById("oee-planned-stop-apply"),
  oeeControlCurrent: document.getElementById("oee-control-current"),
  oeeControlFeedback: document.getElementById("oee-control-feedback"),
  oeeSummary: document.getElementById("oee-summary"),
  oeeKpiGrid: document.getElementById("oee-kpi-grid"),
  oeeProductionGrid: document.getElementById("oee-production-grid"),
  oeeFaultGrid: document.getElementById("oee-fault-grid"),
  oeeColorGrid: document.getElementById("oee-color-grid"),
  oeeTrendList: document.getElementById("oee-trend-list"),
};

function formatToken(value) {
  const key = String(value ?? "").trim().toLowerCase();
  if (!key) return "-";
  return TOKEN_LABELS[key] || key.replaceAll("_", " ").toUpperCase();
}

function formatBool(value, truthy = "Aktif", falsy = "Pasif") {
  if (value === null || value === undefined) return "-";
  return value ? truthy : falsy;
}

function formatNumber(value) {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return `${numeric.toFixed(1)}%`;
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("tr-TR", { hour12: false });
}

function runtimeBannerText() {
  if (state.runtime === "reconnecting") {
    return "Canli baglanti koptu, son bilinen veri gosteriliyor";
  }
  if (state.runtime === "bootstrapping") {
    return "Ilk snapshot yukleniyor";
  }
  return "";
}

function toneClassForPercent(value, warn = 60, good = 75) {
  if (value === null || value === undefined || value === "") return "neutral";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "neutral";
  if (numeric >= good) return "good";
  if (numeric >= warn) return "warn";
  return "bad";
}

function setFeedback(message, tone = "neutral") {
  els.commandFeedback.textContent = message;
  els.commandFeedback.dataset.tone = tone;
}

function setOeeFeedback(message, tone = "neutral") {
  els.oeeControlFeedback.textContent = message;
  els.oeeControlFeedback.dataset.tone = tone;
}

function syncInputValue(input, value) {
  if (document.activeElement === input) return;
  input.value = value === null || value === undefined || value === "" ? "" : String(value);
}

function setRuntime(nextRuntime) {
  state.runtime = nextRuntime;
  els.runtimeBadge.textContent = formatToken(nextRuntime);
  els.runtimeBadge.className = `runtime-badge runtime-${nextRuntime}`;

  const bannerText = runtimeBannerText();
  if (bannerText) {
    els.connectionBanner.textContent = bannerText;
    els.connectionBanner.classList.remove("hidden");
  } else {
    els.connectionBanner.classList.add("hidden");
  }
}

function setActiveTab(tabName) {
  state.activeTab = tabName === "oee" ? "oee" : "operations";
  els.tabButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tab === state.activeTab);
  });
  els.operationsTab.classList.toggle("hidden", state.activeTab !== "operations");
  els.oeeTab.classList.toggle("hidden", state.activeTab !== "oee");

  const params = new URLSearchParams(window.location.search);
  params.set("module", state.moduleId);
  params.set("tab", state.activeTab);
  window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
}

function renderOverview(snapshot) {
  const meta = snapshot.module_meta;
  const timestamps = snapshot.timestamps;
  els.moduleTitle.textContent = meta.title;
  els.moduleSubtitle.textContent = `${meta.module_id} | Canli operator paneli`;
  els.snapshotAt.textContent = `Son snapshot: ${formatTime(timestamps.snapshot_at)}`;

  const cards = [
    ["Broker", snapshot.connection.mqtt.state, "mqtt"],
    ["ESP32", snapshot.connection.mega_heartbeat.state, "heartbeat"],
    ["Bridge", snapshot.connection.bridge.state, "bridge"],
  ];

  els.overviewMeta.innerHTML = `
    <div class="overview-pill">
      <span class="overview-label">Module</span>
      <strong>${meta.module_id}</strong>
    </div>
    <div class="overview-pill">
      <span class="overview-label">Faz</span>
      <strong>${formatToken(meta.ui_phase)}</strong>
    </div>
    <div class="overview-pill">
      <span class="overview-label">Komut Modu</span>
      <strong>${formatToken(snapshot.command_permissions.mode)}</strong>
    </div>
    <div class="overview-pill">
      <span class="overview-label">Vision Ingest</span>
      <strong>${snapshot.vision_ingest.enabled ? "Acik" : "Kapali"}</strong>
    </div>
    <div class="overview-pill">
      <span class="overview-label">OEE Tab</span>
      <strong>${snapshot.oee.enabled ? "Acik" : "Kapali"}</strong>
    </div>
  `;

  els.connectionCards.innerHTML = cards
    .map(
      ([label, value, tone]) => `
        <article class="connection-card tone-${tone}">
          <p>${label}</p>
          <strong>${formatToken(value)}</strong>
        </article>
      `
    )
    .join("");
}

function renderFieldGrid(container, rows) {
  container.innerHTML = rows
    .map(
      ([label, value]) => `
        <div class="status-row">
          <span>${label}</span>
          <strong>${value}</strong>
        </div>
      `
    )
    .join("");
}

function renderCounts(snapshot) {
  const counts = snapshot.counts;
  const cards = [
    ["Kirmizi", counts.red, "red"],
    ["Sari", counts.yellow, "yellow"],
    ["Mavi", counts.blue, "blue"],
    ["Toplam", counts.total, "total"],
  ];
  els.countCards.innerHTML = cards
    .map(
      ([label, value, tone]) => `
        <article class="count-card count-${tone}">
          <p>${label}</p>
          <strong>${formatNumber(value)}</strong>
        </article>
      `
    )
    .join("");
}

function renderVision(snapshot) {
  const vision = snapshot.vision_ingest;
  if (!vision.enabled || !vision.ui_visible) {
    els.visionPanel.classList.add("hidden");
    return;
  }

  const cards = [
    ["Vision State", formatToken(vision.status.state)],
    ["FPS", formatNumber(vision.status.fps)],
    ["Active Tracks", formatNumber(vision.tracks.active_tracks)],
    ["Crossings", formatNumber(vision.tracks.total_crossings)],
    ["Sari Diff", formatNumber(vision.compare.diff.yellow)],
    ["Alarm", formatToken(vision.compare.yellow_alarm)],
    ["Vizyon K", formatNumber(vision.compare.vision.red)],
    ["Mega K", formatNumber(vision.compare.mega.red)],
    ["Vizyon S", formatNumber(vision.compare.vision.yellow)],
    ["Mega S", formatNumber(vision.compare.mega.yellow)],
    ["Vizyon M", formatNumber(vision.compare.vision.blue)],
    ["Mega M", formatNumber(vision.compare.mega.blue)],
  ];

  els.visionPanel.classList.remove("hidden");
  els.visionGrid.innerHTML = cards
    .map(
      ([label, value]) => `
        <article class="vision-card">
          <span>${label}</span>
          <strong>${value}</strong>
        </article>
      `
    )
    .join("");
}

function renderCommands(snapshot) {
  const permissions = snapshot.command_permissions;
  const presetDisabled = !permissions.publish_enabled;
  const manualDisabled = !permissions.publish_enabled || !permissions.manual_command_enabled;

  els.commandMode.textContent = `Mod: ${formatToken(permissions.mode)} | Topic: ${permissions.transport_topic}`;
  els.presetButtons.innerHTML = permissions.allowed_presets
    .map((command) => {
      const label = PRESET_LABELS[command] || command;
      return `
        <button class="preset-button" data-command="${command}" ${presetDisabled ? "disabled" : ""}>
          ${label}
        </button>
      `;
    })
    .join("");

  els.manualCommandInput.disabled = manualDisabled;
  els.manualCommandSubmit.disabled = manualDisabled;

  if (permissions.publish_enabled && permissions.manual_command_enabled && els.commandFeedback.dataset.tone !== "success") {
    setFeedback("Komutlar aktif.", "neutral");
  } else if (!permissions.publish_enabled) {
    setFeedback("Komut publish kapali.", "neutral");
  } else if (!permissions.manual_command_enabled) {
    setFeedback("Serbest komut kapali, preset komutlar acik.", "neutral");
  }
}

function renderLogs(snapshot) {
  if (!snapshot.recent_logs.length) {
    els.logList.innerHTML = `<p class="empty-state">Henuz log gelmedi.</p>`;
    return;
  }
  els.logList.innerHTML = snapshot.recent_logs
    .map(
      (entry) => `
        <article class="log-entry">
          <div class="log-meta">
            <span>${entry.source}</span>
            <span>${formatTime(entry.received_at)}</span>
          </div>
          <pre>${entry.message}</pre>
        </article>
      `
    )
    .join("");
}

function findShiftOption(controls, code) {
  return (controls.shift_options || []).find((option) => option.code === code) || null;
}

function selectedShiftWindowText(controls) {
  const selected = findShiftOption(controls, controls.selected_shift);
  return selected ? `${selected.name} | ${selected.window}` : "-";
}

function renderOeeControls(oee) {
  const controls = oee.controls || {};
  const selectedShift = controls.selected_shift || "SHIFT-A";
  const performanceMode = controls.performance_mode || "TARGET";

  els.oeeControlSummary.textContent = oee.last_event_summary || "OEE kontrol paneli hazir.";
  els.oeeSelectedWindow.textContent = selectedShiftWindowText(controls);

  els.oeeShiftOptions.innerHTML = (controls.shift_options || [])
    .map(
      (option) => `
        <button
          class="oee-choice-button ${option.code === selectedShift ? "is-active" : ""}"
          data-shift-code="${option.code}"
          type="button"
          ${state.oeeControlBusy ? "disabled" : ""}
        >
          ${option.code}
        </button>
      `
    )
    .join("");

  const modes = [
    ["TARGET", "Hedef Bazli"],
    ["IDEAL_CYCLE", "Ideal Cycle"],
  ];
  els.oeeModeOptions.innerHTML = modes
    .map(
      ([mode, label]) => `
        <button
          class="oee-choice-button ${mode === performanceMode ? "is-active" : ""}"
          data-performance-mode="${mode}"
          type="button"
          ${state.oeeControlBusy ? "disabled" : ""}
        >
          ${label}
        </button>
      `
    )
    .join("");

  els.oeeShiftStart.disabled = state.oeeControlBusy || !controls.can_start;
  els.oeeShiftStop.disabled = state.oeeControlBusy || !controls.can_stop;

  syncInputValue(els.oeeTargetQty, controls.target_qty);
  syncInputValue(els.oeeIdealCycle, controls.ideal_cycle_sec);
  syncInputValue(els.oeePlannedStop, controls.planned_stop_min);
  els.oeeTargetQty.disabled = state.oeeControlBusy;
  els.oeeIdealCycle.disabled = state.oeeControlBusy;
  els.oeePlannedStop.disabled = state.oeeControlBusy;
  els.oeeTargetApply.disabled = state.oeeControlBusy;
  els.oeeIdealCycleApply.disabled = state.oeeControlBusy;
  els.oeePlannedStopApply.disabled = state.oeeControlBusy;

  els.oeeControlStats.innerHTML = `
    <article class="oee-mini-stat">
      <span>Aktif Vardiya</span>
      <strong>${oee.shift.active ? (oee.shift.code || selectedShift) : "Hazir"}</strong>
    </article>
    <article class="oee-mini-stat">
      <span>Baslangic</span>
      <strong>${formatTime(oee.shift.started_at)}</strong>
    </article>
    <article class="oee-mini-stat">
      <span>Plan Penceresi</span>
      <strong>${oee.shift.active ? `${formatTime(oee.shift.plan_start)} - ${formatTime(oee.shift.plan_end)}` : selectedShiftWindowText(controls)}</strong>
    </article>
  `;

  renderFieldGrid(els.oeeControlCurrent, [
    ["Secim", selectedShift],
    ["Aktif Shift", oee.shift.code || "-"],
    ["Mod", formatToken(performanceMode)],
    ["Target", `${formatNumber(controls.target_qty)} adet`],
    ["Cycle", `${formatNumber(controls.ideal_cycle_sec)} sn`],
    ["Planli Durus", `${formatNumber(controls.planned_stop_min)} dk`],
  ]);
}

function renderOee(snapshot) {
  const oee = snapshot.oee;
  renderOeeControls(oee);
  els.oeeUpdatedAt.textContent = `Son guncelleme: ${formatTime(oee.updated_at)}`;
  els.oeeSource.textContent = `Kaynak: ${formatToken(oee.state_source)}`;
  const targetValue = oee.targets.performance_mode === "IDEAL_CYCLE"
    ? `${formatNumber(oee.targets.ideal_cycle_sec)} sn`
    : `${formatNumber(oee.targets.target_qty)} adet`;

  els.oeeSummary.innerHTML = `
    <article class="oee-summary-card tone-${oee.header.tone}">
      <span>Hat Durumu</span>
      <strong>${formatToken(oee.header.line_state)}</strong>
      <small>${oee.header.state_summary}</small>
    </article>
    <article class="oee-summary-card">
      <span>Vardiya</span>
      <strong>${oee.shift.code || "-"}</strong>
      <small>${oee.shift.name || "Aktif vardiya bilgisi yok"}</small>
    </article>
    <article class="oee-summary-card">
      <span>Hedef Ayari</span>
      <strong>${targetValue}</strong>
      <small>Planli durus ${formatNumber(oee.targets.planned_stop_min)} dk</small>
    </article>
    <article class="oee-summary-card">
      <span>Ozet</span>
      <strong>${oee.last_event_summary || "-"}</strong>
      <small>${oee.last_tablet_line ? "Tablet satiri alindi" : "Runtime state yedegi"}</small>
    </article>
  `;

  const kpis = [
    ["Kullanilabilirlik", oee.kpis.availability],
    ["Performans", oee.kpis.performance],
    ["Kalite", oee.kpis.quality],
    ["OEE", oee.kpis.oee],
  ];
  els.oeeKpiGrid.innerHTML = kpis
    .map(
      ([label, value]) => `
        <article class="oee-kpi-card tone-${toneClassForPercent(value, 75, 90)}">
          <span>${label}</span>
          <strong>${formatPercent(value)}</strong>
        </article>
      `
    )
    .join("");

  renderFieldGrid(els.oeeProductionGrid, [
    ["Toplam Urun", formatNumber(oee.production.total)],
    ["Saglam", formatNumber(oee.production.good)],
    ["Rework", formatNumber(oee.production.rework)],
    ["Hurda", formatNumber(oee.production.scrap)],
    ["Mavi Total", formatNumber(oee.colors.blue.total)],
    ["Sari Total", formatNumber(oee.colors.yellow.total)],
    ["Kirmizi Total", formatNumber(oee.colors.red.total)],
    ["Perf Modu", formatToken(oee.targets.performance_mode)],
  ]);

  renderFieldGrid(els.oeeFaultGrid, [
    ["Fault Active", formatBool(oee.fault.active, "Evet", "Hayir")],
    ["Reason", oee.fault.reason || "-"],
    ["Status", oee.fault.status || "-"],
    ["Baslangic", formatTime(oee.fault.started_at)],
    ["Bitis", formatTime(oee.fault.ended_at)],
    ["Sure DK", formatNumber(oee.fault.duration_min)],
    ["Shift Start", formatTime(oee.shift.started_at)],
    ["Plan", `${formatTime(oee.shift.plan_start)} - ${formatTime(oee.shift.plan_end)}`],
  ]);

  const colorCards = [
    ["red", "Kirmizi", oee.colors.red],
    ["yellow", "Sari", oee.colors.yellow],
    ["blue", "Mavi", oee.colors.blue],
  ];
  els.oeeColorGrid.innerHTML = colorCards
    .map(
      ([tone, label, row]) => `
        <article class="oee-color-card color-${tone}">
          <div class="oee-color-head">
            <h3>${label}</h3>
            <strong>${formatNumber(row.total)}</strong>
          </div>
          <div class="oee-chip-grid">
            <div class="oee-chip-item">
              <span>Saglam</span>
              <strong>${formatNumber(row.good)}</strong>
            </div>
            <div class="oee-chip-item">
              <span>Rework</span>
              <strong>${formatNumber(row.rework)}</strong>
            </div>
            <div class="oee-chip-item">
              <span>Hurda</span>
              <strong>${formatNumber(row.scrap)}</strong>
            </div>
          </div>
        </article>
      `
    )
    .join("");

  if (!oee.trend.length) {
    els.oeeTrendList.innerHTML = `<p class="empty-state">Henuz OEE trend kaydi yok.</p>`;
    return;
  }
  els.oeeTrendList.innerHTML = oee.trend
    .slice()
    .reverse()
    .map(
      (row) => `
        <article class="oee-trend-row">
          <span>${formatTime(row.time)}</span>
          <strong>OEE ${formatPercent(row.oee)}</strong>
          <span>Kalite ${formatPercent(row.quality)}</span>
          <span>Perf ${formatPercent(row.performance)}</span>
          <span>Kull ${formatPercent(row.availability)}</span>
          <span>Loss ${formatPercent(row.loss)}</span>
        </article>
      `
    )
    .join("");
}

function render(snapshot) {
  renderOverview(snapshot);

  renderFieldGrid(els.systemGrid, [
    ["Mod", formatToken(snapshot.system_status.mode)],
    ["Sistem", formatToken(snapshot.system_status.system_state)],
    ["Konveyor", formatToken(snapshot.system_status.conveyor_state)],
    ["Robot", formatToken(snapshot.system_status.robot_state)],
    ["Son Renk", formatToken(snapshot.system_status.last_color)],
    ["Step", formatBool(snapshot.system_status.step_enabled, "Calisiyor", "Durdu")],
    ["Kuyruk", formatNumber(snapshot.system_status.queue_depth)],
    ["Stop Talep", formatBool(snapshot.system_status.stop_request, "Var", "Yok")],
  ]);

  renderFieldGrid(els.hardwareGrid, [
    ["Yon", formatToken(snapshot.hardware_status.direction)],
    ["PWM", formatNumber(snapshot.hardware_status.pwm)],
    ["Travel MS", formatNumber(snapshot.hardware_status.travel_ms)],
    ["Limit 22", formatBool(snapshot.hardware_status.limit_22_pressed, "Basili", "Acik")],
    ["Limit 23", formatBool(snapshot.hardware_status.limit_23_pressed, "Basili", "Acik")],
    ["Step Hold", formatBool(snapshot.hardware_status.step_hold)],
    ["Step US", formatNumber(snapshot.hardware_status.step_us)],
    ["ESP32", formatToken(snapshot.hardware_status.esp32_state)],
  ]);

  renderCounts(snapshot);
  renderVision(snapshot);
  renderCommands(snapshot);
  renderLogs(snapshot);
  renderOee(snapshot);
}

async function fetchDashboard() {
  const response = await fetch(`/api/modules/${state.moduleId}/dashboard`);
  if (!response.ok) {
    throw new Error(`Dashboard fetch failed: ${response.status}`);
  }
  return response.json();
}

function applySnapshot(snapshot) {
  state.snapshot = snapshot;
  render(snapshot);
}

function socketUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/modules/${state.moduleId}`;
}

function scheduleReconnect() {
  const delay = RECONNECT_DELAYS[Math.min(state.reconnectAttempt, RECONNECT_DELAYS.length - 1)];
  state.reconnectAttempt += 1;
  window.clearTimeout(state.reconnectTimer);
  state.reconnectTimer = window.setTimeout(() => connectSocket(), delay);
}

function connectSocket() {
  if (state.ws) {
    state.ws.onclose = null;
    state.ws.close();
  }

  const ws = new WebSocket(socketUrl());
  state.ws = ws;

  ws.onopen = () => {
    state.reconnectAttempt = 0;
    setRuntime("live");
  };

  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "dashboard_snapshot" && payload.data) {
      applySnapshot(payload.data);
      setRuntime("live");
    }
  };

  ws.onclose = () => {
    state.ws = null;
    setRuntime("reconnecting");
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws.close();
  };
}

async function sendCommand(kind, value) {
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/commands`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, value }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    setFeedback(`Komut gonderildi: ${value}`, "success");
  } catch (error) {
    setFeedback(`Komut hatasi: ${error.message}`, "error");
  }
}

async function sendOeeControl(action, value = null) {
  state.oeeControlBusy = true;
  setOeeFeedback("OEE ayari gonderiliyor...", "neutral");
  if (state.snapshot) {
    renderOee(state.snapshot);
  }
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/oee/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, value }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    setOeeFeedback(payload.summary || `OEE aksiyonu gonderildi: ${action}`, "success");
  } catch (error) {
    setOeeFeedback(`OEE kontrol hatasi: ${error.message}`, "error");
  } finally {
    state.oeeControlBusy = false;
    if (state.snapshot) {
      renderOee(state.snapshot);
    }
  }
}

els.tabButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveTab(button.dataset.tab));
});

els.presetButtons.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-command]");
  if (!button) return;
  sendCommand("preset", button.dataset.command);
});

els.manualCommandForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = els.manualCommandInput.value.trim();
  if (!value) return;
  sendCommand("manual", value);
  els.manualCommandInput.value = "";
});

els.oeeShiftOptions.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-shift-code]");
  if (!button || button.disabled) return;
  sendOeeControl("select_shift", button.dataset.shiftCode);
});

els.oeeModeOptions.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-performance-mode]");
  if (!button || button.disabled) return;
  sendOeeControl("set_performance_mode", button.dataset.performanceMode);
});

els.oeeShiftStart.addEventListener("click", () => sendOeeControl("shift_start"));
els.oeeShiftStop.addEventListener("click", () => sendOeeControl("shift_stop"));

els.oeeTargetApply.addEventListener("click", () => {
  sendOeeControl("set_target_qty", els.oeeTargetQty.value.trim());
});

els.oeeIdealCycleApply.addEventListener("click", () => {
  sendOeeControl("set_ideal_cycle_sec", els.oeeIdealCycle.value.trim());
});

els.oeePlannedStopApply.addEventListener("click", () => {
  sendOeeControl("set_planned_stop_min", els.oeePlannedStop.value.trim());
});

async function bootstrap() {
  setActiveTab(state.activeTab);
  setRuntime("bootstrapping");
  setFeedback("Komutlar beklemede.");
  setOeeFeedback("OEE ayarlari beklemede.");
  try {
    const snapshot = await fetchDashboard();
    applySnapshot(snapshot);
    connectSocket();
  } catch (error) {
    setFeedback(`Bootstrap hatasi: ${error.message}`, "error");
    setRuntime("reconnecting");
    scheduleReconnect();
  }
}

bootstrap();

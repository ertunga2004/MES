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
  queued: "Kuyrukta",
  started: "Basladi",
  completed: "Kapatildi",
  consumed_for_work_order: "Depodan Kullanildi",
  off_order_completion: "Depoya Alindi",
  rollback_to_inventory: "Depoya Geri Alindi",
  manual_inventory_removed: "Elle Silindi",
  rolled_back: "Geri Alindi",
};

const OEE_TREND_METRICS = [
  { key: "availability", label: "Kullanilabilirlik", shortLabel: "KULL", color: "#58a6ff", glow: "rgba(88, 166, 255, 0.28)" },
  { key: "performance", label: "Performans", shortLabel: "PERF", color: "#ff8a3d", glow: "rgba(255, 138, 61, 0.28)" },
  { key: "quality", label: "Kalite", shortLabel: "KLT", color: "#24c78d", glow: "rgba(36, 199, 141, 0.28)" },
  { key: "oee", label: "OEE", shortLabel: "OEE", color: "#f8bf4f", glow: "rgba(248, 191, 79, 0.28)" },
];

const OEE_TREND_CHART = {
  width: 640,
  height: 220,
  padding: { top: 18, right: 18, bottom: 24, left: 18 },
  gridValues: [100, 75, 50, 25, 0],
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
  workOrderBusy: false,
  oeeDrafts: {
    selectedShift: null,
    performanceMode: null,
    targetQty: { value: "", dirty: false },
    idealCycleSec: { value: "", dirty: false },
    plannedStopMin: { value: "", dirty: false },
    qualityOverrides: {},
  },
  workOrderDrafts: {
    operatorCode: "",
    operatorName: "",
    toleranceMinutes: { value: "", dirty: false },
    pendingReason: "",
    pendingStart: null,
    pendingRollback: null,
    rollbackConfirmTimer: null,
    pendingReset: null,
    resetConfirmTimer: null,
    pendingInventoryRemove: null,
    inventoryRemoveConfirmTimer: null,
  },
};

const els = {
  moduleTitle: document.getElementById("module-title"),
  moduleSubtitle: document.getElementById("module-subtitle"),
  runtimeBadge: document.getElementById("runtime-badge"),
  snapshotAt: document.getElementById("snapshot-at"),
  connectionBanner: document.getElementById("connection-banner"),
  tabButtons: Array.from(document.querySelectorAll(".tab-button")),
  operationsTab: document.getElementById("tab-operations"),
  workOrdersTab: document.getElementById("tab-work-orders"),
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
  oeeQualityOverrideList: document.getElementById("oee-quality-override-list"),
  oeeTrendList: document.getElementById("oee-trend-list"),
  workOrderSummary: document.getElementById("work-order-summary"),
  workOrderOperatorCode: document.getElementById("work-order-operator-code"),
  workOrderOperatorName: document.getElementById("work-order-operator-name"),
  workOrderTolerance: document.getElementById("work-order-tolerance"),
  workOrderToleranceApply: document.getElementById("work-order-tolerance-apply"),
  workOrderReasonPanel: document.getElementById("work-order-reason-panel"),
  workOrderReasonContext: document.getElementById("work-order-reason-context"),
  workOrderReasonInput: document.getElementById("work-order-reason-input"),
  workOrderReasonSubmit: document.getElementById("work-order-reason-submit"),
  workOrderFeedback: document.getElementById("work-order-feedback"),
  workOrderActive: document.getElementById("work-order-active"),
  workOrderSource: document.getElementById("work-order-source"),
  workOrderReloadSubmit: document.getElementById("work-order-reload-submit"),
  workOrderResetSubmit: document.getElementById("work-order-reset-submit"),
  workOrderQueueList: document.getElementById("work-order-queue-list"),
  workOrderInventory: document.getElementById("work-order-inventory"),
  workOrderPerformance: document.getElementById("work-order-performance"),
  workOrderTransitionLog: document.getElementById("work-order-transition-log"),
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
  const text = String(value);
  const dateText = date.toLocaleDateString("tr-TR");
  const timeOptions = {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  };
  if (/\.\d{1,6}(?:Z|[+-]\d\d:\d\d)?$/.test(text)) {
    timeOptions.fractionalSecondDigits = 3;
  }
  return `${dateText} ${date.toLocaleTimeString("tr-TR", timeOptions)}`;
}

function formatTrendTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString("tr-TR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function clampPercent(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  return Math.max(0, Math.min(100, numeric));
}

function formatTrendIndex(index, total) {
  const offset = total - index - 1;
  return offset <= 0 ? "N" : `N-${offset}`;
}

function formatTrendDelta(current, previous) {
  if (current === null || previous === null) {
    return { text: "Ilk veri", tone: "flat" };
  }

  const delta = current - previous;
  if (Math.abs(delta) < 0.05) {
    return { text: "Degisim yok", tone: "flat" };
  }

  const prefix = delta > 0 ? "+" : "";
  return {
    text: `${prefix}${delta.toFixed(1)} puan`,
    tone: delta > 0 ? "up" : "down",
  };
}

function buildTrendChartGeometry(values) {
  const { width, height, padding } = OEE_TREND_CHART;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  return values.map((value, index) => {
    const x = values.length === 1
      ? padding.left + plotWidth / 2
      : padding.left + (index / (values.length - 1)) * plotWidth;
    const y = value === null ? null : padding.top + ((100 - value) / 100) * plotHeight;
    return { index, x, y, value };
  });
}

function buildSvgPath(points) {
  let path = "";
  let started = false;

  points.forEach((point) => {
    if (point.value === null || point.y === null) {
      started = false;
      return;
    }
    path += `${started ? " L" : "M"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
    started = true;
  });

  return path.trim();
}

function buildSvgArea(points) {
  const finitePoints = points.filter((point) => point.value !== null && point.y !== null);
  if (!finitePoints.length) return "";

  const baseline = OEE_TREND_CHART.height - OEE_TREND_CHART.padding.bottom;
  const linePath = buildSvgPath(finitePoints);
  return `${linePath} L ${finitePoints[finitePoints.length - 1].x.toFixed(2)} ${baseline.toFixed(2)} L ${finitePoints[0].x.toFixed(2)} ${baseline.toFixed(2)} Z`;
}

function renderTrendMetricCard(metric, rows) {
  const values = rows.map((row) => clampPercent(row[metric.key]));
  const points = buildTrendChartGeometry(values);
  const linePath = buildSvgPath(points);
  const areaPath = buildSvgArea(points);
  const validValues = values.filter((value) => value !== null);
  const latest = validValues.length ? validValues[validValues.length - 1] : null;
  const previous = validValues.length > 1 ? validValues[validValues.length - 2] : null;
  const delta = formatTrendDelta(latest, previous);
  const low = validValues.length ? Math.min(...validValues).toFixed(1) : "-";
  const high = validValues.length ? Math.max(...validValues).toFixed(1) : "-";
  const rangeText = validValues.length ? `${low}% - ${high}%` : "-";
  const gradientId = `oee-trend-gradient-${metric.key}`;

  const gridLines = OEE_TREND_CHART.gridValues
    .map((gridValue) => {
      const y = OEE_TREND_CHART.padding.top
        + ((100 - gridValue) / 100) * (OEE_TREND_CHART.height - OEE_TREND_CHART.padding.top - OEE_TREND_CHART.padding.bottom);
      const className = gridValue === 0 ? "oee-trend-svg-baseline" : "oee-trend-svg-grid";
      return `
        <g>
          <line class="${className}" x1="${OEE_TREND_CHART.padding.left}" y1="${y.toFixed(2)}" x2="${(OEE_TREND_CHART.width - OEE_TREND_CHART.padding.right).toFixed(2)}" y2="${y.toFixed(2)}"></line>
          <text class="oee-trend-svg-label" x="${(OEE_TREND_CHART.width - OEE_TREND_CHART.padding.right - 4).toFixed(2)}" y="${(y - 6).toFixed(2)}" text-anchor="end">${gridValue}%</text>
        </g>
      `;
    })
    .join("");

  const circles = points
    .filter((point) => point.value !== null && point.y !== null)
    .map((point, index, visiblePoints) => {
      const isLatest = index === visiblePoints.length - 1;
      return `
        ${isLatest ? `<circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="11" fill="${metric.color}" opacity="0.14"></circle>` : ""}
        <circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="${isLatest ? "5.5" : "3.5"}" fill="${metric.color}" stroke="#08131f" stroke-width="${isLatest ? "4" : "2"}">
          <title>${metric.label} | ${formatTrendTime(rows[point.index].time)} | ${formatPercent(point.value)}</title>
        </circle>
      `;
    })
    .join("");

  return `
    <article class="oee-trend-card" style="--metric-color: ${metric.color}; --metric-glow: ${metric.glow};">
      <div class="oee-trend-card-head">
        <div class="oee-trend-card-title">
          <span>${metric.shortLabel}</span>
          <strong>${metric.label}</strong>
        </div>
        <div class="oee-trend-card-stats">
          <strong>${formatPercent(latest)}</strong>
          <span class="oee-trend-delta" data-tone="${delta.tone}">${delta.text}</span>
        </div>
      </div>

      <svg class="oee-trend-chart" viewBox="0 0 ${OEE_TREND_CHART.width} ${OEE_TREND_CHART.height}" role="img" aria-label="${metric.label} icin son 10 kayitlik cizgi grafigi">
        <defs>
          <linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${metric.color}" stop-opacity="0.28"></stop>
            <stop offset="100%" stop-color="${metric.color}" stop-opacity="0.02"></stop>
          </linearGradient>
        </defs>
        ${gridLines}
        ${areaPath ? `<path d="${areaPath}" fill="url(#${gradientId})"></path>` : ""}
        ${linePath ? `<path d="${linePath}" fill="none" stroke="${metric.color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>` : ""}
        ${circles}
      </svg>

      <div class="oee-trend-card-foot">
        <span>Aralik ${rangeText}</span>
        <span>${rows.length} kayit</span>
      </div>
    </article>
  `;
}

function renderOeeTrend(trendRows) {
  const rows = (trendRows || []).slice(-10);
  if (!rows.length) {
    els.oeeTrendList.innerHTML = `<p class="empty-state">Henuz OEE trend kaydi yok.</p>`;
    return;
  }

  const firstTime = formatTrendTime(rows[0].time);
  const lastTime = formatTrendTime(rows[rows.length - 1].time);
  const tickColumns = Math.max(rows.length, 1);
  const tickStyle = `--trend-axis-columns: ${tickColumns};`;

  els.oeeTrendList.innerHTML = `
    <div class="oee-trend-band">
      <div class="oee-trend-band-copy">
        <strong>Canli kayan trend</strong>
        <span>Her yeni veri sagdan eklenir, pencere son 10 kayitla sinirli kalir.</span>
      </div>
      <div class="oee-trend-band-meta">
        <strong>${rows.length}/10</strong>
        <span>${firstTime} -> ${lastTime}</span>
      </div>
    </div>

    <div class="oee-trend-grid">
      ${OEE_TREND_METRICS.map((metric) => renderTrendMetricCard(metric, rows)).join("")}
    </div>

    <div class="oee-trend-axis" style="${tickStyle}">
      ${rows
        .map(
          (row, index) => `
            <article class="oee-trend-tick">
              <strong>${formatTrendIndex(index, rows.length)}</strong>
              <span>${formatTrendTime(row.time)}</span>
            </article>
          `
        )
        .join("")}
    </div>
  `;
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

function setWorkOrderFeedback(message, tone = "neutral") {
  els.workOrderFeedback.textContent = message;
  els.workOrderFeedback.dataset.tone = tone;
}

function syncInputValue(input, value) {
  if (document.activeElement === input) return;
  input.value = value === null || value === undefined || value === "" ? "" : String(value);
}

function normalizeComparableValue(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function comparableValuesMatch(left, right) {
  const leftText = normalizeComparableValue(left).replace(",", ".");
  const rightText = normalizeComparableValue(right).replace(",", ".");
  if (!leftText || !rightText) return leftText === rightText;

  const leftNumber = Number(leftText);
  const rightNumber = Number(rightText);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    return Math.abs(leftNumber - rightNumber) < 0.000001;
  }
  return leftText === rightText;
}

function getOeeDraftField(key) {
  return state.oeeDrafts[key];
}

function setOeeInputDraft(key, value) {
  const draft = getOeeDraftField(key);
  draft.value = String(value ?? "");
  draft.dirty = true;
}

function clearOeeInputDraft(key) {
  const draft = getOeeDraftField(key);
  draft.value = "";
  draft.dirty = false;
}

function effectiveOeeInputValue(key, serverValue) {
  const draft = getOeeDraftField(key);
  if (draft && draft.dirty) return draft.value;
  return serverValue === null || serverValue === undefined || serverValue === "" ? "" : String(serverValue);
}

function syncOeeInputValue(input, draftKey, serverValue) {
  const nextValue = effectiveOeeInputValue(draftKey, serverValue);
  if (document.activeElement === input) return;
  if (input.value !== nextValue) {
    input.value = nextValue;
  }
}

function resolveOeeInputDraft(draftKey, serverValue) {
  const draft = getOeeDraftField(draftKey);
  if (draft && draft.dirty && comparableValuesMatch(draft.value, serverValue)) {
    clearOeeInputDraft(draftKey);
  }
}

function setOeeChoiceDraft(key, value) {
  state.oeeDrafts[key] = value ? String(value) : null;
}

function clearOeeChoiceDraft(key) {
  state.oeeDrafts[key] = null;
}

function effectiveOeeChoiceValue(key, serverValue, fallbackValue = "") {
  return state.oeeDrafts[key] || serverValue || fallbackValue;
}

function resolveOeeChoiceDraft(key, serverValue) {
  const draftValue = state.oeeDrafts[key];
  if (draftValue && comparableValuesMatch(draftValue, serverValue)) {
    clearOeeChoiceDraft(key);
  }
}

function setOeeQualityDraft(itemId, value) {
  if (!itemId) return;
  state.oeeDrafts.qualityOverrides[String(itemId)] = String(value ?? "");
}

function resolveOeeQualityDrafts(snapshot) {
  const recentItems = snapshot?.oee?.recent_items || [];
  const knownItems = new Map(recentItems.map((item) => [String(item.item_id), item]));
  Object.keys(state.oeeDrafts.qualityOverrides).forEach((itemId) => {
    const item = knownItems.get(itemId);
    if (!item) {
      delete state.oeeDrafts.qualityOverrides[itemId];
      return;
    }
    if (comparableValuesMatch(state.oeeDrafts.qualityOverrides[itemId], item.classification)) {
      delete state.oeeDrafts.qualityOverrides[itemId];
    }
  });
}

function resolveOeeDrafts(snapshot) {
  const controls = snapshot?.oee?.controls || {};
  resolveOeeChoiceDraft("selectedShift", controls.selected_shift || "SHIFT-A");
  resolveOeeChoiceDraft("performanceMode", controls.performance_mode || "TARGET");
  resolveOeeInputDraft("targetQty", controls.target_qty);
  resolveOeeInputDraft("idealCycleSec", controls.ideal_cycle_sec);
  resolveOeeInputDraft("plannedStopMin", controls.planned_stop_min);
  resolveOeeQualityDrafts(snapshot);
}

function setWorkOrderToleranceDraft(value) {
  state.workOrderDrafts.toleranceMinutes.value = String(value ?? "");
  state.workOrderDrafts.toleranceMinutes.dirty = true;
}

function clearWorkOrderToleranceDraft() {
  state.workOrderDrafts.toleranceMinutes.value = "";
  state.workOrderDrafts.toleranceMinutes.dirty = false;
}

function effectiveWorkOrderToleranceValue(serverValue) {
  const draft = state.workOrderDrafts.toleranceMinutes;
  if (draft.dirty) return draft.value;
  return serverValue === null || serverValue === undefined || serverValue === "" ? "" : String(serverValue);
}

function resolveWorkOrderDrafts(snapshot) {
  const controls = snapshot?.work_orders?.controls || {};
  if (state.workOrderDrafts.toleranceMinutes.dirty && comparableValuesMatch(state.workOrderDrafts.toleranceMinutes.value, controls.tolerance_minutes)) {
    clearWorkOrderToleranceDraft();
  }
  const activeOrderId = String(snapshot?.work_orders?.active_order?.order_id || "");
  const pendingRollback = state.workOrderDrafts.pendingRollback;
  if (pendingRollback && pendingRollback.orderId !== activeOrderId) {
    clearWorkOrderRollbackDraft();
  }
  const summary = snapshot?.work_orders?.summary || {};
  if (state.workOrderDrafts.pendingReset && Number(summary.queued_count || 0) === 0 && Number(summary.active_count || 0) === 0 && Number(summary.inventory_total || 0) === 0) {
    clearWorkOrderResetDraft();
  }
  const inventoryRows = snapshot?.work_orders?.inventory || [];
  const pendingInventoryRemove = state.workOrderDrafts.pendingInventoryRemove;
  if (pendingInventoryRemove) {
    const currentRow = inventoryRows.find((row) => String(row.match_key || "") === pendingInventoryRemove.matchKey);
    if (!currentRow || Number(currentRow.quantity || 0) !== pendingInventoryRemove.quantity) {
      clearWorkOrderInventoryRemoveDraft();
    }
  }
}

function clearWorkOrderRollbackDraft() {
  if (state.workOrderDrafts.rollbackConfirmTimer) {
    window.clearTimeout(state.workOrderDrafts.rollbackConfirmTimer);
  }
  state.workOrderDrafts.pendingRollback = null;
  state.workOrderDrafts.rollbackConfirmTimer = null;
}

function armWorkOrderRollback(orderId) {
  clearWorkOrderRollbackDraft();
  if (!orderId) return;
  state.workOrderDrafts.pendingRollback = { orderId: String(orderId) };
  state.workOrderDrafts.rollbackConfirmTimer = window.setTimeout(() => {
    clearWorkOrderRollbackDraft();
    if (state.snapshot) renderWorkOrders(state.snapshot);
  }, 5000);
}

function clearWorkOrderResetDraft() {
  if (state.workOrderDrafts.resetConfirmTimer) {
    window.clearTimeout(state.workOrderDrafts.resetConfirmTimer);
  }
  state.workOrderDrafts.pendingReset = null;
  state.workOrderDrafts.resetConfirmTimer = null;
}

function armWorkOrderReset() {
  clearWorkOrderResetDraft();
  state.workOrderDrafts.pendingReset = { armed: true };
  state.workOrderDrafts.resetConfirmTimer = window.setTimeout(() => {
    clearWorkOrderResetDraft();
    if (state.snapshot) renderWorkOrders(state.snapshot);
  }, 5000);
}

function clearWorkOrderInventoryRemoveDraft() {
  if (state.workOrderDrafts.inventoryRemoveConfirmTimer) {
    window.clearTimeout(state.workOrderDrafts.inventoryRemoveConfirmTimer);
  }
  state.workOrderDrafts.pendingInventoryRemove = null;
  state.workOrderDrafts.inventoryRemoveConfirmTimer = null;
}

function armWorkOrderInventoryRemove(matchKey, quantity) {
  clearWorkOrderInventoryRemoveDraft();
  if (!matchKey) return;
  state.workOrderDrafts.pendingInventoryRemove = {
    matchKey: String(matchKey),
    quantity: Number(quantity || 0),
  };
  state.workOrderDrafts.inventoryRemoveConfirmTimer = window.setTimeout(() => {
    clearWorkOrderInventoryRemoveDraft();
    if (state.snapshot) renderWorkOrders(state.snapshot);
  }, 5000);
}

function syncButtonCollection(container, entries, { datasetKey, activeValue = null, disabled = false, baseClass }) {
  const existing = new Map(
    Array.from(container.querySelectorAll("button")).map((button) => [button.dataset[datasetKey], button])
  );

  entries.forEach((entry, index) => {
    const value = String(entry.value);
    let button = existing.get(value);
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.dataset[datasetKey] = value;
    }
    button.textContent = entry.label;
    button.className = activeValue !== null && comparableValuesMatch(activeValue, value)
      ? `${baseClass} is-active`
      : baseClass;
    button.disabled = disabled;

    const currentChild = container.children[index];
    if (currentChild !== button) {
      container.insertBefore(button, currentChild || null);
    }
    existing.delete(value);
  });

  existing.forEach((button) => button.remove());
}

function createQualityOverrideRow(itemId) {
  const row = document.createElement("article");
  row.className = "status-row";
  row.dataset.itemId = String(itemId);

  const label = document.createElement("span");
  label.className = "oee-override-label";

  const controls = document.createElement("div");
  controls.className = "oee-override-actions";

  row.append(label, controls);
  return row;
}

function renderQualityOverrideRows(recentItems, overrideOptions, disabled) {
  if (!recentItems.length) {
    els.oeeQualityOverrideList.innerHTML = `<p class="empty-state">Override icin tamamlanan urun yok.</p>`;
    return;
  }

  Array.from(els.oeeQualityOverrideList.querySelectorAll(".empty-state")).forEach((node) => node.remove());

  const existing = new Map(
    Array.from(els.oeeQualityOverrideList.querySelectorAll("article[data-item-id]")).map((row) => [row.dataset.itemId, row])
  );

  recentItems.forEach((item, index) => {
    const itemId = String(item.item_id);
    let row = existing.get(itemId);
    if (!row) {
      row = createQualityOverrideRow(itemId);
    }

    const label = row.querySelector(".oee-override-label");
    const controls = row.querySelector(".oee-override-actions");
    label.textContent = `#${item.item_id} | ${formatToken(item.color)} | ${formatTime(item.completed_at)}`;

    const draftValue = state.oeeDrafts.qualityOverrides[itemId];
    const selectedValue = draftValue || item.classification || "GOOD";
    syncButtonCollection(
      controls,
      overrideOptions.map((value) => ({ value, label: formatToken(value) })),
      {
        datasetKey: "oeeQualityValue",
        activeValue: selectedValue,
        disabled,
        baseClass: "oee-choice-button oee-override-button",
      }
    );
    controls.querySelectorAll("button[data-oee-quality-value]").forEach((button) => {
      button.dataset.itemId = itemId;
      button.dataset.oeeOverrideItem = itemId;
      button.dataset.qualityValue = button.dataset.oeeQualityValue;
      button.classList.toggle("quality-good", button.dataset.oeeQualityValue === "GOOD");
      button.classList.toggle("quality-rework", button.dataset.oeeQualityValue === "REWORK");
      button.classList.toggle("quality-scrap", button.dataset.oeeQualityValue === "SCRAP");
    });

    const currentChild = els.oeeQualityOverrideList.children[index];
    if (currentChild !== row) {
      els.oeeQualityOverrideList.insertBefore(row, currentChild || null);
    }
    existing.delete(itemId);
  });

  existing.forEach((row) => row.remove());
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
  if (tabName === "oee") {
    state.activeTab = "oee";
  } else if (tabName === "work-orders") {
    state.activeTab = "work-orders";
  } else {
    state.activeTab = "operations";
  }
  els.tabButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tab === state.activeTab);
  });
  els.operationsTab.classList.toggle("hidden", state.activeTab !== "operations");
  els.workOrdersTab.classList.toggle("hidden", state.activeTab !== "work-orders");
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
  const runtime = vision.runtime || {};
  const lastItem = runtime.last_item || null;
  const lastItemSummary = lastItem
    ? `#${lastItem.item_id} | ${formatToken(lastItem.sensor_color)} / ${formatToken(lastItem.vision_color)} / ${formatToken(lastItem.final_color)}`
    : "-";
  const lastCorrelation = lastItem ? formatToken(lastItem.correlation_status) : "-";

  const cards = [
    ["Vision State", formatToken(vision.status.state)],
    ["Health", formatToken(runtime.health_state)],
    ["FPS", formatNumber(vision.status.fps)],
    ["Active Tracks", formatNumber(vision.tracks.active_tracks)],
    ["Crossings", formatNumber(vision.tracks.total_crossings)],
    ["Mismatch", formatNumber(runtime.mismatch_count)],
    ["Early OK", formatNumber(runtime.early_accepted_count)],
    ["Early Rej", formatNumber(runtime.early_rejected_count)],
    ["Son Reject", formatToken(runtime.last_reject_reason)],
    ["Son Corr", lastCorrelation],
    ["Son Item", lastItemSummary],
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
  syncButtonCollection(
    els.presetButtons,
    permissions.allowed_presets.map((command) => ({ value: command, label: PRESET_LABELS[command] || command })),
    { datasetKey: "command", disabled: presetDisabled, baseClass: "preset-button" }
  );

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
  const selectedShift = effectiveOeeChoiceValue("selectedShift", controls.selected_shift, "SHIFT-A");
  const performanceMode = effectiveOeeChoiceValue("performanceMode", controls.performance_mode, "TARGET");
  const targetQtyValue = effectiveOeeInputValue("targetQty", controls.target_qty);
  const idealCycleValue = effectiveOeeInputValue("idealCycleSec", controls.ideal_cycle_sec);
  const plannedStopValue = effectiveOeeInputValue("plannedStopMin", controls.planned_stop_min);
  const selectedShiftControls = {
    ...controls,
    selected_shift: selectedShift,
  };

  els.oeeControlSummary.textContent = oee.last_event_summary || "OEE kontrol paneli hazir.";
  els.oeeSelectedWindow.textContent = selectedShiftWindowText(selectedShiftControls);

  syncButtonCollection(
    els.oeeShiftOptions,
    (controls.shift_options || []).map((option) => ({ value: option.code, label: option.code })),
    { datasetKey: "shiftCode", activeValue: selectedShift, disabled: state.oeeControlBusy, baseClass: "oee-choice-button" }
  );

  const modes = [
    ["TARGET", "Hedef Bazli"],
    ["IDEAL_CYCLE", "Ideal Cycle"],
  ];
  syncButtonCollection(
    els.oeeModeOptions,
    modes.map(([value, label]) => ({ value, label })),
    { datasetKey: "performanceMode", activeValue: performanceMode, disabled: state.oeeControlBusy, baseClass: "oee-choice-button" }
  );

  els.oeeShiftStart.disabled = state.oeeControlBusy || !controls.can_start;
  els.oeeShiftStop.disabled = state.oeeControlBusy || !controls.can_stop;

  syncOeeInputValue(els.oeeTargetQty, "targetQty", targetQtyValue);
  syncOeeInputValue(els.oeeIdealCycle, "idealCycleSec", idealCycleValue);
  syncOeeInputValue(els.oeePlannedStop, "plannedStopMin", plannedStopValue);
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
    ["Target", `${formatNumber(targetQtyValue)} adet`],
    ["Cycle", `${formatNumber(idealCycleValue)} sn`],
    ["Planli Durus", `${formatNumber(plannedStopValue)} dk`],
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

  const overrideOptions = oee.controls.quality_override_options || ["GOOD", "REWORK", "SCRAP"];
  const recentItems = oee.recent_items || [];
  renderQualityOverrideRows(recentItems, overrideOptions, state.oeeControlBusy);

  renderOeeTrend(oee.trend);
}

function formatMinutes(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return `${numeric.toFixed(1)} dk`;
}

function workOrderTitle(order) {
  if (!order) return "-";
  const stockCode = String(order.stock_code || "").trim();
  const stockName = String(order.stock_name || "").trim();
  if (stockCode && stockName) return `${stockCode} | ${stockName}`;
  return stockCode || stockName || String(order.order_id || "-");
}

function workOrderRequirementLabel(requirement) {
  if (!requirement) return "-";
  const color = String(requirement.color || "").trim();
  if (color) return formatToken(color);
  return String(requirement.stock_code || requirement.product_code || requirement.line_id || "-");
}

function renderWorkOrderRequirements(order, compact = false) {
  const requirements = Array.isArray(order?.requirements) ? order.requirements : [];
  if (!requirements.length) return "";
  return `
    <div class="work-order-requirement-list${compact ? " compact" : ""}">
      ${requirements.map((requirement) => `
        <div class="work-order-requirement-chip">
          <span>${workOrderRequirementLabel(requirement)}</span>
          <strong>${formatNumber(requirement.completed_qty)}/${formatNumber(requirement.qty)}</strong>
          <small>Uretim ${formatNumber(requirement.production_qty)} | Depo ${formatNumber(requirement.inventory_consumed_qty)} | Kalan ${formatNumber(requirement.remaining_qty)}</small>
        </div>
      `).join("")}
    </div>
  `;
}

function workOrderProgressBar(order) {
  const progress = Number(order?.progress_pct || 0);
  const safeProgress = Math.max(0, Math.min(100, progress));
  return `
    <div class="work-order-progress">
      <div class="work-order-progress-bar">
        <span style="width:${safeProgress.toFixed(1)}%"></span>
      </div>
      <strong>${safeProgress.toFixed(1)}%</strong>
    </div>
  `;
}

function renderWorkOrderReasonPanel() {
  const pending = state.workOrderDrafts.pendingStart;
  if (!pending) {
    els.workOrderReasonPanel.classList.add("hidden");
    els.workOrderReasonContext.textContent = "-";
    if (document.activeElement !== els.workOrderReasonInput) {
      els.workOrderReasonInput.value = "";
    }
    return;
  }
  els.workOrderReasonPanel.classList.remove("hidden");
  els.workOrderReasonContext.textContent = `${pending.previousOrderId} -> ${pending.orderId} | ${pending.elapsedMinutes.toFixed(1)} dk gecikme | limit ${pending.toleranceMinutes.toFixed(1)} dk`;
  if (document.activeElement !== els.workOrderReasonInput) {
    els.workOrderReasonInput.value = state.workOrderDrafts.pendingReason;
  }
}

function renderWorkOrders(snapshot) {
  const workOrders = snapshot.work_orders || {};
  const summary = workOrders.summary || {};
  const controls = workOrders.controls || {};
  const activeOrder = workOrders.active_order;
  const queue = workOrders.queue || [];
  const inventory = workOrders.inventory || [];
  const transitionLog = workOrders.transition_log || [];
  const completionLog = workOrders.completion_log || [];
  const perf = workOrders.performance_panel || {};
  const source = workOrders.source || {};
  const rollbackArmed = activeOrder && state.workOrderDrafts.pendingRollback?.orderId === activeOrder.order_id;
  const resetArmed = Boolean(state.workOrderDrafts.pendingReset);

  syncInputValue(els.workOrderTolerance, effectiveWorkOrderToleranceValue(controls.tolerance_minutes));
  els.workOrderTolerance.disabled = state.workOrderBusy;
  els.workOrderToleranceApply.disabled = state.workOrderBusy;
  els.workOrderReasonSubmit.disabled = state.workOrderBusy;
  els.workOrderReloadSubmit.disabled = state.workOrderBusy;
  els.workOrderResetSubmit.disabled = state.workOrderBusy;
  els.workOrderResetSubmit.textContent = resetArmed ? "Tekrar tikla: Is Emirlerini + Depoyu Sifirla" : "Is Emirlerini + Depoyu Sifirla";
  els.workOrderResetSubmit.className = resetArmed ? "oee-danger-button is-active" : "oee-danger-button";

  els.workOrderSummary.innerHTML = `
    <article class="work-order-metric-card">
      <span>Bekleyen</span>
      <strong>${formatNumber(summary.queued_count)}</strong>
    </article>
    <article class="work-order-metric-card">
      <span>Aktif</span>
      <strong>${formatNumber(summary.active_count)}</strong>
    </article>
    <article class="work-order-metric-card">
      <span>Kapanan</span>
      <strong>${formatNumber(summary.completed_count)}</strong>
    </article>
    <article class="work-order-metric-card">
      <span>Depo Stogu</span>
      <strong>${formatNumber(summary.inventory_total)}</strong>
    </article>
    <article class="work-order-metric-card">
      <span>Tolerans</span>
      <strong>${formatMinutes(controls.tolerance_minutes)}</strong>
    </article>
    <article class="work-order-metric-card">
      <span>Son Kapanis</span>
      <strong>${summary.last_completed_order_id || "-"}</strong>
      <small>${formatTime(summary.last_completed_at)}</small>
    </article>
  `;

  if (!activeOrder) {
    els.workOrderActive.innerHTML = `<p class="empty-state">Aktif is emri yok. Operator kuyruktaki siradaki emri secebilir.</p>`;
  } else {
    els.workOrderActive.innerHTML = `
      <article class="work-order-active-card">
        <div class="work-order-active-head">
          <div>
            <span class="work-order-badge">${activeOrder.order_id}</span>
            <h3>${workOrderTitle(activeOrder)}</h3>
          </div>
          <strong>${formatToken(activeOrder.status)}</strong>
        </div>
        <div class="work-order-active-actions">
          <button
            class="${rollbackArmed ? "oee-danger-button" : "oee-choice-button"}"
            type="button"
            data-work-order-rollback="${activeOrder.order_id}"
            ${state.workOrderBusy || controls.can_rollback === false ? "disabled" : ""}
          >${rollbackArmed ? "Tekrar tikla: geri al" : "Aktif Is Emrini Geri Al"}</button>
          <span>${rollbackArmed ? "5 sn icinde ayni tusa tekrar tikla. Tamamlanan kutular depoya geri gider." : "Yanlis baslatma durumunda is emrini kuyruga geri alir."}</span>
        </div>
        ${workOrderProgressBar(activeOrder)}
        ${renderWorkOrderRequirements(activeOrder)}
        <div class="work-order-kpi-grid">
          <div class="work-order-kpi-chip">
            <span>Plan</span>
            <strong>${formatNumber(activeOrder.qty)} ${activeOrder.unit || "adet"}</strong>
          </div>
          <div class="work-order-kpi-chip">
            <span>Uretimden</span>
            <strong>${formatNumber(activeOrder.production_qty)}</strong>
          </div>
          <div class="work-order-kpi-chip">
            <span>Depodan</span>
            <strong>${formatNumber(activeOrder.inventory_consumed_qty)}</strong>
          </div>
          <div class="work-order-kpi-chip">
            <span>Kalan</span>
            <strong>${formatNumber(activeOrder.remaining_qty)}</strong>
          </div>
          <div class="work-order-kpi-chip">
            <span>WO OEE</span>
            <strong>${formatPercent(activeOrder.oee)}</strong>
          </div>
          <div class="work-order-kpi-chip">
            <span>WO Kull</span>
            <strong>${formatPercent(activeOrder.availability)}</strong>
          </div>
          <div class="work-order-kpi-chip">
            <span>WO Perf</span>
            <strong>${formatPercent(activeOrder.performance)}</strong>
          </div>
          <div class="work-order-kpi-chip">
            <span>WO Kalite</span>
            <strong>${formatPercent(activeOrder.quality)}</strong>
          </div>
        </div>
        <div class="work-order-meta-grid">
          <div class="status-row"><span>Operator</span><strong>${activeOrder.started_by_name || activeOrder.started_by || "-"}</strong></div>
          <div class="status-row"><span>Baslangic</span><strong>${formatTime(activeOrder.started_at)}</strong></div>
          <div class="status-row"><span>Proje</span><strong>${activeOrder.project_code || "-"}</strong></div>
          <div class="status-row"><span>Vardiya</span><strong>${activeOrder.shift_code || "-"}</strong></div>
          <div class="status-row"><span>Is Merkezi</span><strong>${activeOrder.work_center_code || "-"}</strong></div>
          <div class="status-row"><span>Aciklama</span><strong>${activeOrder.description || "-"}</strong></div>
          <div class="status-row"><span>Ideal Cycle</span><strong>${formatNumber(activeOrder.ideal_cycle_sec)} sn</strong></div>
          <div class="status-row"><span>Plan Sure</span><strong>${formatMinutes(activeOrder.planned_duration_min)}</strong></div>
        </div>
      </article>
    `;
  }

  renderFieldGrid(els.workOrderSource, [
    ["Klasor", source.folder || "-"],
    ["Kaynak Dosya", source.file || "-"],
    ["Yuklenme", formatTime(source.loaded_at)],
    ["Kaynak Mod", "ERP klasor cache"],
  ]);

  if (!queue.length) {
    els.workOrderQueueList.innerHTML = `<p class="empty-state">Bekleyen is emri yok.</p>`;
  } else {
    els.workOrderQueueList.innerHTML = queue
      .map((order, index) => `
        <article class="work-order-row">
          <div class="work-order-row-main">
            <div class="work-order-row-head">
              <span class="work-order-badge">${order.order_id}</span>
              <strong>${workOrderTitle(order)}</strong>
            </div>
            <div class="work-order-row-meta">
              <span>Plan ${formatNumber(order.qty)} ${order.unit || "adet"}</span>
              <span>Siralama ${formatNumber(order.sequence_no)}</span>
              <span>Renk ${formatToken(order.product_color)}</span>
              <span>Proje ${order.project_code || "-"}</span>
            </div>
            ${renderWorkOrderRequirements(order, true)}
          </div>
          <div class="work-order-row-actions">
            <button class="oee-choice-button" type="button" data-work-order-move="${order.order_id}" data-direction="up" ${state.workOrderBusy || index === 0 ? "disabled" : ""}>Yukari</button>
            <button class="oee-choice-button" type="button" data-work-order-move="${order.order_id}" data-direction="down" ${state.workOrderBusy || index === queue.length - 1 ? "disabled" : ""}>Asagi</button>
            <button class="oee-primary-button" type="button" data-work-order-start="${order.order_id}" ${state.workOrderBusy || !controls.can_start ? "disabled" : ""}>Baslat</button>
          </div>
        </article>
      `)
      .join("");
  }

  if (!inventory.length) {
    els.workOrderInventory.innerHTML = `<p class="empty-state">Depoya alinmis ara urun yok.</p>`;
  } else {
    els.workOrderInventory.innerHTML = inventory
      .map((row) => `
        <article class="status-row work-order-inventory-row">
          <div class="work-order-inventory-meta">
            <span>${row.stock_code || row.match_key}</span>
            <small>${formatToken(row.color)} | Kaynak ${formatToken(row.last_source)} | Son ${formatTime(row.last_updated_at)}</small>
          </div>
          <div class="work-order-inventory-actions">
            <strong>${formatNumber(row.quantity)}</strong>
            <button
              class="${state.workOrderDrafts.pendingInventoryRemove?.matchKey === String(row.match_key || "") && Number(state.workOrderDrafts.pendingInventoryRemove?.quantity || 0) === Number(row.quantity || 0) ? "oee-danger-button" : "oee-choice-button"}"
              type="button"
              data-inventory-remove="${row.match_key}"
              data-inventory-quantity="${row.quantity}"
              ${state.workOrderBusy ? "disabled" : ""}
            >${state.workOrderDrafts.pendingInventoryRemove?.matchKey === String(row.match_key || "") && Number(state.workOrderDrafts.pendingInventoryRemove?.quantity || 0) === Number(row.quantity || 0) ? "Tekrar: 1 Adet Sil" : "1 Adet Sil"}</button>
          </div>
        </article>
      `)
      .join("");
  }

  renderFieldGrid(els.workOrderPerformance, [
    ["OEE", formatPercent(perf.oee)],
    ["Kullanilabilirlik", formatPercent(perf.availability)],
    ["Performans", formatPercent(perf.performance)],
    ["Kalite", formatPercent(perf.quality)],
    ["Planli Durus", formatMinutes(perf.planned_stop_min)],
    ["Plansiz Durus", formatMinutes(perf.unplanned_stop_min)],
    ["Runtime", formatMinutes(perf.runtime_min)],
    ["Kalan Sure", formatMinutes(perf.remaining_min)],
    ["Fault", formatBool(perf.active_fault, "Aktif", "Yok")],
    ["Fault Neden", perf.fault_reason || "-"],
  ]);

  const mergedLog = [
    ...transitionLog.map((row) => ({ ...row, logType: "transition" })),
    ...completionLog.map((row) => ({ ...row, logType: "completion" })),
  ]
    .sort((left, right) => String(right.time || "").localeCompare(String(left.time || "")))
    .slice(0, 10);

  if (!mergedLog.length) {
    els.workOrderTransitionLog.innerHTML = `<p class="empty-state">Henuz is emri gecis kaydi yok.</p>`;
  } else {
    els.workOrderTransitionLog.innerHTML = mergedLog
      .map((row) => `
        <article class="work-order-log-card">
          <div class="work-order-log-head">
            <strong>${row.orderId || "-"}</strong>
            <span>${formatToken(row.eventType || row.logType)}</span>
          </div>
          <div class="work-order-log-body">
            <span>${row.stockCode || row.stockName || "-"}</span>
            <strong>${formatTime(row.time)}</strong>
          </div>
          <p>${row.note || "-"}</p>
        </article>
      `)
      .join("");
  }

  renderWorkOrderReasonPanel();
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
  renderWorkOrders(snapshot);
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
  resolveOeeDrafts(snapshot);
  resolveWorkOrderDrafts(snapshot);
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

async function sendOeeControl(action, value = null, options = {}) {
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
    if (typeof options.onError === "function") {
      options.onError();
    }
    setOeeFeedback(`OEE kontrol hatasi: ${error.message}`, "error");
  } finally {
    state.oeeControlBusy = false;
    if (state.snapshot) {
      renderOee(state.snapshot);
    }
  }
}

async function sendQualityOverride(itemId, classification, options = {}) {
  state.oeeControlBusy = true;
  setOeeFeedback("Kalite override gonderiliyor...", "neutral");
  if (state.snapshot) renderOee(state.snapshot);
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/oee/quality-override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_id: itemId, classification }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    setOeeFeedback(payload.summary || `Kalite guncellendi: ${itemId}`, "success");
  } catch (error) {
    if (typeof options.onError === "function") {
      options.onError();
    }
    setOeeFeedback(`Kalite override hatasi: ${error.message}`, "error");
  } finally {
    state.oeeControlBusy = false;
    if (state.snapshot) renderOee(state.snapshot);
  }
}

async function sendWorkOrderTolerance() {
  state.workOrderBusy = true;
  setWorkOrderFeedback("Is emri toleransi gonderiliyor...", "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/work-orders/tolerance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ minutes: effectiveWorkOrderToleranceValue(els.workOrderTolerance.value).trim() }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    setWorkOrderFeedback(payload.summary || "Tolerans guncellendi.", "success");
  } catch (error) {
    setWorkOrderFeedback(`Is emri tolerans hatasi: ${error.message}`, "error");
  } finally {
    state.workOrderBusy = false;
    if (state.snapshot) renderWorkOrders(state.snapshot);
  }
}

async function sendWorkOrderReload() {
  clearWorkOrderRollbackDraft();
  clearWorkOrderResetDraft();
  clearWorkOrderInventoryRemoveDraft();
  state.workOrderBusy = true;
  setWorkOrderFeedback("Is emri kaynagi klasorden yenileniyor...", "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/work-orders/reload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    setWorkOrderFeedback(payload.summary || "Is emri kaynagi yenilendi.", "success");
  } catch (error) {
    setWorkOrderFeedback(`Is emri kaynak hatasi: ${error.message}`, "error");
  } finally {
    state.workOrderBusy = false;
    if (state.snapshot) renderWorkOrders(state.snapshot);
  }
}

async function sendWorkOrderReorder(orderId, direction) {
  if (!state.snapshot?.work_orders?.queue?.length) return;
  clearWorkOrderRollbackDraft();
  clearWorkOrderResetDraft();
  clearWorkOrderInventoryRemoveDraft();
  const queue = [...state.snapshot.work_orders.queue];
  const index = queue.findIndex((order) => order.order_id === orderId);
  if (index < 0) return;
  const targetIndex = direction === "up" ? index - 1 : index + 1;
  if (targetIndex < 0 || targetIndex >= queue.length) return;
  [queue[index], queue[targetIndex]] = [queue[targetIndex], queue[index]];

  state.workOrderBusy = true;
  setWorkOrderFeedback("Is emri sirasi guncelleniyor...", "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/work-orders/reorder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order_ids: queue.map((order) => order.order_id) }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    setWorkOrderFeedback(payload.summary || "Is emri sirasi guncellendi.", "success");
  } catch (error) {
    setWorkOrderFeedback(`Is emri sira hatasi: ${error.message}`, "error");
  } finally {
    state.workOrderBusy = false;
    if (state.snapshot) renderWorkOrders(state.snapshot);
  }
}

async function sendWorkOrderStart(orderId, transitionReason = "") {
  clearWorkOrderRollbackDraft();
  clearWorkOrderResetDraft();
  clearWorkOrderInventoryRemoveDraft();
  state.workOrderBusy = true;
  setWorkOrderFeedback(`${orderId} baslatiliyor...`, "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/work-orders/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        order_id: orderId,
        operator_code: els.workOrderOperatorCode.value.trim(),
        operator_name: els.workOrderOperatorName.value.trim(),
        transition_reason: transitionReason,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 409 && payload.detail?.code === "WORK_ORDER_REASON_REQUIRED") {
        state.workOrderDrafts.pendingStart = {
          orderId: payload.detail.order_id,
          previousOrderId: payload.detail.previous_order_id,
          elapsedMinutes: Number(payload.detail.elapsed_minutes || 0),
          toleranceMinutes: Number(payload.detail.tolerance_minutes || 0),
        };
        renderWorkOrderReasonPanel();
        throw new Error("Gecis toleransi asildi. Neden girilmesi gerekiyor.");
      }
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    state.workOrderDrafts.pendingStart = null;
    state.workOrderDrafts.pendingReason = "";
    els.workOrderReasonInput.value = "";
    setWorkOrderFeedback(payload.summary || `${orderId} baslatildi.`, "success");
  } catch (error) {
    setWorkOrderFeedback(`Is emri baslatma hatasi: ${error.message}`, "error");
  } finally {
    state.workOrderBusy = false;
    if (state.snapshot) renderWorkOrders(state.snapshot);
  }
}

async function sendWorkOrderRollback(orderId) {
  clearWorkOrderRollbackDraft();
  clearWorkOrderResetDraft();
  clearWorkOrderInventoryRemoveDraft();
  state.workOrderBusy = true;
  setWorkOrderFeedback(`${orderId} geri aliniyor...`, "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/work-orders/rollback-active`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    setWorkOrderFeedback(payload.summary || `${orderId} geri alindi.`, "success");
  } catch (error) {
    setWorkOrderFeedback(`Is emri geri alma hatasi: ${error.message}`, "error");
  } finally {
    state.workOrderBusy = false;
    if (state.snapshot) renderWorkOrders(state.snapshot);
  }
}

async function sendWorkOrderReset() {
  clearWorkOrderRollbackDraft();
  clearWorkOrderResetDraft();
  clearWorkOrderInventoryRemoveDraft();
  state.workOrderBusy = true;
  setWorkOrderFeedback("Is emirleri ve depo sifirlaniyor...", "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/work-orders/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    setWorkOrderFeedback(payload.summary || "Is emirleri sifirlandi.", "success");
  } catch (error) {
    setWorkOrderFeedback(`Is emri reset hatasi: ${error.message}`, "error");
  } finally {
    state.workOrderBusy = false;
    if (state.snapshot) renderWorkOrders(state.snapshot);
  }
}

async function sendWorkOrderInventoryRemove(matchKey) {
  clearWorkOrderRollbackDraft();
  clearWorkOrderResetDraft();
  clearWorkOrderInventoryRemoveDraft();
  state.workOrderBusy = true;
  setWorkOrderFeedback(`${matchKey} icin depodan 1 adet siliniyor...`, "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
  try {
    const response = await fetch(`/api/modules/${state.moduleId}/work-orders/inventory/remove`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_key: matchKey, quantity: 1 }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    setWorkOrderFeedback(payload.summary || `${matchKey} deposundan 1 adet silindi.`, "success");
  } catch (error) {
    setWorkOrderFeedback(`Depo silme hatasi: ${error.message}`, "error");
  } finally {
    state.workOrderBusy = false;
    if (state.snapshot) renderWorkOrders(state.snapshot);
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
  setOeeChoiceDraft("selectedShift", button.dataset.shiftCode);
  if (state.snapshot) renderOee(state.snapshot);
  sendOeeControl("select_shift", button.dataset.shiftCode, {
    onError: () => {
      clearOeeChoiceDraft("selectedShift");
    },
  });
});

els.oeeModeOptions.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-performance-mode]");
  if (!button || button.disabled) return;
  setOeeChoiceDraft("performanceMode", button.dataset.performanceMode);
  if (state.snapshot) renderOee(state.snapshot);
  sendOeeControl("set_performance_mode", button.dataset.performanceMode, {
    onError: () => {
      clearOeeChoiceDraft("performanceMode");
    },
  });
});

els.oeeShiftStart.addEventListener("click", () => sendOeeControl("shift_start"));
els.oeeShiftStop.addEventListener("click", () => sendOeeControl("shift_stop"));

els.oeeTargetApply.addEventListener("click", () => {
  sendOeeControl("set_target_qty", effectiveOeeInputValue("targetQty", els.oeeTargetQty.value).trim());
});

els.oeeIdealCycleApply.addEventListener("click", () => {
  sendOeeControl("set_ideal_cycle_sec", effectiveOeeInputValue("idealCycleSec", els.oeeIdealCycle.value).trim());
});

els.oeePlannedStopApply.addEventListener("click", () => {
  sendOeeControl("set_planned_stop_min", effectiveOeeInputValue("plannedStopMin", els.oeePlannedStop.value).trim());
});

els.oeeTargetQty.addEventListener("input", () => setOeeInputDraft("targetQty", els.oeeTargetQty.value));
els.oeeIdealCycle.addEventListener("input", () => setOeeInputDraft("idealCycleSec", els.oeeIdealCycle.value));
els.oeePlannedStop.addEventListener("input", () => setOeeInputDraft("plannedStopMin", els.oeePlannedStop.value));

els.oeeTargetQty.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  els.oeeTargetApply.click();
});

els.oeeIdealCycle.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  els.oeeIdealCycleApply.click();
});

els.oeePlannedStop.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  els.oeePlannedStopApply.click();
});

els.oeeQualityOverrideList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-oee-override-item][data-quality-value]");
  if (!button || button.disabled) return;
  const itemId = button.dataset.oeeOverrideItem;
  const classification = button.dataset.qualityValue;
  const currentSnapshotItem = (state.snapshot?.oee?.recent_items || []).find((item) => String(item.item_id) === itemId);
  const currentValue = state.oeeDrafts.qualityOverrides[itemId] || currentSnapshotItem?.classification || "";
  if (comparableValuesMatch(currentValue, classification)) return;
  setOeeQualityDraft(itemId, classification);
  if (state.snapshot) renderOee(state.snapshot);
  sendQualityOverride(itemId, classification, {
    onError: () => {
      delete state.oeeDrafts.qualityOverrides[itemId];
    },
  });
});

els.workOrderTolerance.addEventListener("input", () => setWorkOrderToleranceDraft(els.workOrderTolerance.value));
els.workOrderToleranceApply.addEventListener("click", () => sendWorkOrderTolerance());
els.workOrderTolerance.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  els.workOrderToleranceApply.click();
});

els.workOrderReloadSubmit.addEventListener("click", () => sendWorkOrderReload());
els.workOrderResetSubmit.addEventListener("click", () => {
  if (state.workOrderDrafts.pendingReset) {
    sendWorkOrderReset();
    return;
  }
  armWorkOrderReset();
  setWorkOrderFeedback("Tum is emirlerini ve depo kayitlarini sifirlamak icin ayni tusa tekrar tikla.", "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
});

els.workOrderReasonInput.addEventListener("input", () => {
  state.workOrderDrafts.pendingReason = els.workOrderReasonInput.value;
});
els.workOrderReasonSubmit.addEventListener("click", () => {
  const pending = state.workOrderDrafts.pendingStart;
  if (!pending) return;
  const reason = els.workOrderReasonInput.value.trim();
  if (!reason) {
    setWorkOrderFeedback("Gecikme nedeni bos birakilamaz.", "error");
    return;
  }
  sendWorkOrderStart(pending.orderId, reason);
});

els.workOrderQueueList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-work-order-start]");
  if (button && !button.disabled) {
    sendWorkOrderStart(button.dataset.workOrderStart);
    return;
  }
  const moveButton = event.target.closest("button[data-work-order-move][data-direction]");
  if (moveButton && !moveButton.disabled) {
    sendWorkOrderReorder(moveButton.dataset.workOrderMove, moveButton.dataset.direction);
  }
});

els.workOrderActive.addEventListener("click", (event) => {
  const rollbackButton = event.target.closest("button[data-work-order-rollback]");
  if (!rollbackButton || rollbackButton.disabled) return;
  const orderId = String(rollbackButton.dataset.workOrderRollback || "");
  const pendingRollback = state.workOrderDrafts.pendingRollback;
  if (pendingRollback && pendingRollback.orderId === orderId) {
    sendWorkOrderRollback(orderId);
    return;
  }
  armWorkOrderRollback(orderId);
  setWorkOrderFeedback(`${orderId} geri alma icin ayni tusa tekrar tikla.`, "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
});

els.workOrderInventory.addEventListener("click", (event) => {
  const removeButton = event.target.closest("button[data-inventory-remove]");
  if (!removeButton || removeButton.disabled) return;
  const matchKey = String(removeButton.dataset.inventoryRemove || "");
  const quantity = Number(removeButton.dataset.inventoryQuantity || 0);
  const pendingInventoryRemove = state.workOrderDrafts.pendingInventoryRemove;
  if (
    pendingInventoryRemove
    && pendingInventoryRemove.matchKey === matchKey
    && Number(pendingInventoryRemove.quantity || 0) === quantity
  ) {
    sendWorkOrderInventoryRemove(matchKey);
    return;
  }
  armWorkOrderInventoryRemove(matchKey, quantity);
  setWorkOrderFeedback(`${matchKey} icin depodan 1 adet silmek icin ayni tusa tekrar tikla.`, "neutral");
  if (state.snapshot) renderWorkOrders(state.snapshot);
});

async function bootstrap() {
  setActiveTab(state.activeTab);
  setRuntime("bootstrapping");
  setFeedback("Komutlar beklemede.");
  setOeeFeedback("OEE ayarlari beklemede.");
  setWorkOrderFeedback("Is emri kontrolleri beklemede.");
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

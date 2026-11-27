import { analyze, liveKpis, physicalLog, WINDOW_MS } from "./digital-twin/analytics.mjs?v=1";
import { createAnalysisView, elapsedLabel } from "./digital-twin/analysis-view.mjs?v=1";

const scenarioLabels = {
  normal_run: "Normal",
  planned_pause: "Planlı Duruş",
  recovery: "Toparlanma",
  temperature_warning: "Sıcaklık Uyarısı",
  restart: "Yeniden Başlatma",
};

const panel = document.getElementById("tab-digital-twin");
const response = await fetch(new URL("./digital-twin/test-telemetry.json", import.meta.url));
if (!response.ok) {
  throw new Error(`Sample telemetry request returned ${response.status}`);
}

const { sourceBasis, scenarios, samples } = await response.json();
const normalRun = scenarios.find((scenario) => scenario.id === "normal_run");
const number = new Intl.NumberFormat("tr-TR");
const percent = new Intl.NumberFormat("tr-TR", { style: "percent" });
const metrics = panel.querySelectorAll("[data-twin-value]");
const telemetryStatus = panel.querySelector("[data-twin-status]");
const selector = panel.querySelector("#digital-twin-scenario");
const source = panel.querySelector("#digital-twin-source");
source.value = "demo";
const initialScenario = normalRun ?? scenarios[0];
const updateAnalysis = createAnalysisView(panel);
let dashboard, dashboardReceivedAt, live, model;
const sampleStride = 2000;

panel.querySelector("[data-twin-line]").textContent = sourceBasis.line;
selector.replaceChildren(...scenarios.map(({ id }) => new Option(scenarioLabels[id] ?? id, id)));
selector.value = initialScenario.id;

let displayedSample;
function showSample(sample) {
  if (sample === displayedSample) return;
  displayedSample = sample;
  telemetryStatus.textContent = sample?.running ? "Örnek hatta üretim sürüyor" : "Örnek hat duruyor";

  for (const metric of metrics) {
    const field = metric.dataset.twinValue;
    const value = sample?.[field];
    if (!Number.isFinite(value)) {
      metric.textContent = "—";
    } else if (field === "fillLevel") {
      metric.textContent = percent.format(value / 100);
    } else {
      metric.textContent = number.format(value) + (field === "temperature" ? " °C" : "");
    }
  }
}

export function acceptDashboardSnapshot(snapshot) {
  dashboard = snapshot;
  dashboardReceivedAt = Date.now();
  if (source.value === "live" && !panel.classList.contains("hidden")) updateLive();
}

function updateLive() {
  const now = Date.now();
  const stamp = Date.parse(dashboard?.timestamps?.snapshot_at);
  const connected = dashboard?.connection?.mqtt?.connected && now - dashboardReceivedAt <= 15000;
  if (Number.isFinite(stamp) && connected && live.lastStamp !== stamp) {
    const reconnected = live.connected === false && live.lastStamp != null;
    if (reconnected) live.events.push({at:live.lastStamp, kind:"gap"});
    const since = Math.max(live.start, Date.parse(dashboard.connection.mqtt.last_online_at) || 0, stamp - WINDOW_MS);
    const logs = [...(dashboard.recent_logs ?? [])].reverse();
    const additions = [];
    for (const log of logs) {
      const logAt = Date.parse(log.received_at);
      if (!log.id || live.seen.has(log.id) || !Number.isFinite(logAt) || logAt < since || logAt > stamp) continue;
      live.seen.set(log.id, logAt);
      for (const event of physicalLog(log)) {
        if (event.kind !== "energy") additions.push(event);
        else if (!live.meter || event.at >= live.meter.at) live.meter = event;
      }
    }
    live.events.push(...additions);
    live.events = live.events.filter(event => event.at >= stamp - WINDOW_MS - 15000).sort((a,b) => a.at - b.at);
    model?.applyLive(additions, stamp - live.start);
    for (const [id, at] of live.seen) if (at < stamp - WINDOW_MS) live.seen.delete(id);
    live.kpis = liveKpis(dashboard);
    const values = { at:stamp, ...live.kpis };
    for (const event of additions) if (event.kind === "released") live.released.add(event.id);
    if (Number.isFinite(live.kpis.oee)) values.count = dashboard.oee.production?.total;
    else if (live.released.size) values.count = live.released.size;
    if (stamp - (live.history.at(-1)?.at ?? -Infinity) < sampleStride) live.history.pop();
    live.history.push(values);
    live.history = live.history.filter(row => row.at >= stamp - WINDOW_MS);
    live.lastStamp = stamp;
  }
  live.connected = Boolean(connected);
  const end = live.lastStamp ?? live.start;
  const start = Math.max(live.start, end - WINDOW_MS);
  const data = analyze(live.events, start, end);
  const heartbeat = dashboard?.connection?.mega_heartbeat?.state === "online";
  const beltStatus = dashboard?.system_status?.conveyor_state;
  telemetryStatus.textContent = connected ? heartbeat ? `Cihaz bağlı · ${beltStatus === "run" ? "Konveyör çalışıyor" : beltStatus === "stop" ? "Konveyör duruyor" : "Bant durumu bekleniyor"}`
    : "Broker bağlı · cihaz verisi bekleniyor" : "Fiziksel hat bağlantısı bekleniyor";
  for (const metric of metrics) {
    const value = dashboard?.counts?.total;
    metric.textContent = connected && heartbeat && metric.dataset.twinValue === "count" && Number.isFinite(value)
      ? number.format(value) : "—";
  }
  updateAnalysis({...data, ...live.kpis, energyKwh:live.meter?.value}, live.history, {
    demo:false, start, end, stale:!connected || !heartbeat, energyAt:live.meter?.at,
    source:connected ? "MES telemetrisi · vardiya OEE’si, ekipman olayları ve varsa enerji sayacı"
      : "Fiziksel hat için MES’in MQTT üzerinden cihaz verisi alması gerekiyor.",
  });
}

async function mountModel() {
  const canvas = panel.querySelector("#digital-twin-canvas");
  const diagram = panel.querySelector("[data-twin-diagram]");
  const sceneStatus = panel.querySelector("[data-twin-scene-status]");
  const {
    Engine, PointerEventTypes, createFactory, FactoryController, Replay, createTelemetryScenario,
  } = await import("./digital-twin/engine/model.js?v=1");
  const recording = createTelemetryScenario({ samples });

  let engine;
  let factory;
  try {
    canvas.hidden = false;
    engine = new Engine(canvas, true, { stencil: true });
    factory = createFactory(engine, canvas);
  } catch (error) {
    engine?.dispose();
    canvas.hidden = true;
    throw error;
  }

  const controller = new FactoryController(factory);
  controller.pauses = recording.pauses;
  controller.conveyorPauses = recording.conveyorPauses;
  const replay = new Replay(recording.events, controller);
  const playback = panel.querySelector(".digital-twin-playback");
  const play = panel.querySelector("[data-twin-play]");
  const pause = panel.querySelector("[data-twin-pause]");
  const restart = panel.querySelector("[data-twin-restart]");
  const timeline = panel.querySelector("#digital-twin-timeline");
  const speed = panel.querySelector("#digital-twin-speed");
  const playbackStatus = panel.querySelector("[data-twin-playback-status]");
  const time = panel.querySelector("[data-twin-time]");
  const views = panel.querySelector(".digital-twin-views");
  const viewButtons = views.querySelectorAll("[data-twin-view]");
  const cameraHint = "Sürükle: döndür · sağ tuş: kaydır · tekerlek: yakınlaş";
  let rangeStart;
  let rangeEnd;
  let scenario;
  let history = [];
  let lastAnalysisAt = -Infinity;
  let livePosition = 0;
  let rendering = false;
  let firstView = true;

  function setPlayback(playing, status) {
    replay.playing = playing;
    play.disabled = playing;
    pause.disabled = !playing;
    playbackStatus.textContent = status;
  }

  function updateTime() {
    const next = `${elapsedLabel(replay.position - rangeStart)} / ${elapsedLabel(rangeEnd - rangeStart)}`;
    if (time.textContent !== next) time.textContent = next;
    timeline.value = Math.round(replay.position - rangeStart);
  }

  function drawDemo(force = false) {
    const at = replay.position;
    if (!force && performance.now() - lastAnalysisAt < 140) return;
    lastAnalysisAt = performance.now();
    const planned = scenario.id === "planned_pause";
    const options = {demo:true, planned, idealCycleMs:8000};
    const values = analyze(controller.events, rangeStart, at, options);
    for (let sample = (history.at(-1)?.at ?? rangeStart - sampleStride) + sampleStride; sample <= at; sample += sampleStride) {
      history.push({at:sample, ...analyze(controller.events, rangeStart, sample, options)});
    }
    const points = history.at(-1)?.at === at ? history : [...history, {at, ...values}];
    updateAnalysis(values, points, {
      demo:true, start:rangeStart, end:at, planned,
      source:"Örnek simülasyon · her 8. ürün ilk geçişte başarısız kabul edilir. Enerji, ekipman durumuna bağlı tahmindir.",
    });
  }

  function seek(position, status) {
    setPlayback(false, status);
    replay.seek(position);
    displayedSample = undefined;
    showSample(controller.lineSample);
    updateTime();
    history = [];
    drawDemo(true);
  }

  function selectScenario(next) {
    scenario = next;
    rangeStart = Date.parse(samples[scenario.from].timestamp) - replay.start;
    rangeEnd = Date.parse(samples[scenario.to].timestamp) - replay.start;
    timeline.max = rangeEnd - rangeStart;
    controller.pauses = recording.pauses;
    controller.conveyorPauses = recording.conveyorPauses;
    seek(rangeStart, "Hazır");
  }

  function draw() {
    if (replay.playing) {
      const delta = Math.min(engine.getDeltaTime(), 100) * Number(speed.value);
      const step = Math.min(delta, rangeEnd - replay.position);
      replay.advance(step);
      controller.update(replay.position, step / 1000);
      showSample(controller.lineSample);
      updateTime();
      const finished = replay.position >= rangeEnd;
      if (finished) setPlayback(false, "Senaryo tamamlandı");
      drawDemo(finished);
    } else if (source.value === "live") {
      controller.update(livePosition, engine.getDeltaTime() / 1000);
    }
    factory.scene.render();
  }

  function syncRendering() {
    const visible = !document.hidden && canvas.clientWidth > 0 && canvas.clientHeight > 0;
    if (visible) engine.resize();
    if (visible === rendering) return;
    rendering = visible;
    if (visible) {
      if (firstView) {
        factory.view("overview");
        firstView = false;
      }
      engine.runRenderLoop(draw);
      if (source.value === "demo") drawDemo(true);
    } else {
      engine.stopRenderLoop(draw);
      if (replay.playing) setPlayback(false, "Duraklatıldı");
    }
  }

  const selected = () => scenarios.find(({ id }) => id === selector.value) ?? initialScenario;
  selector.addEventListener("change", () => selectScenario(selected()));
  play.addEventListener("click", () => {
    if (replay.position >= rangeEnd) selectScenario(selected());
    setPlayback(true, "Oynatılıyor");
  });
  pause.addEventListener("click", () => { setPlayback(false, "Duraklatıldı"); drawDemo(true); });
  restart.addEventListener("click", () => seek(rangeStart, "Hazır"));
  timeline.addEventListener("input", () => seek(rangeStart + Number(timeline.value), "Duraklatıldı"));

  for (const button of viewButtons) {
    button.addEventListener("click", () => {
      factory.view(button.dataset.twinView);
      for (const view of viewButtons) view.setAttribute("aria-pressed", String(view === button));
      sceneStatus.textContent = cameraHint;
    });
  }
  factory.scene.onPointerObservable.add(({ type, pickInfo }) => {
    if (type === PointerEventTypes.POINTERPICK && pickInfo?.pickedMesh) {
      sceneStatus.textContent = pickInfo.pickedMesh.name;
    }
  });

  diagram.hidden = true;
  views.hidden = false;
  selector.disabled = false;
  playback.disabled = false;
  time.parentElement.hidden = false;
  model = {
    demo() { selectScenario(selected()); sceneStatus.textContent = cameraHint; },
    live() {
      setPlayback(false, "Hazır");
      controller.reset();
      controller.pauses = [];
      controller.conveyorPauses = undefined;
      livePosition = 0;
      sceneStatus.textContent = "Sahne, gözlenen cihaz olaylarıyla güncellenir.";
    },
    applyLive(events, at) {
      for (const event of events) {
        if (!["departure", "queue", "arrived", "pick", "drop", "released", "returned", "belt-state"].includes(event.kind)) continue;
        controller.apply(event, Math.max(livePosition, event.at - live.start));
      }
      livePosition = Math.max(livePosition, at);
    },
  };
  if (source.value === "live") model.live(); else model.demo();

  const observer = new ResizeObserver(() => {
    syncRendering();
    if (source.value === "demo" && rangeStart != null && rendering) drawDemo(true);
  });
  observer.observe(canvas);
  document.addEventListener("visibilitychange", syncRendering);
  window.addEventListener("pagehide", (event) => {
    if (event.persisted) return;
    observer.disconnect();
    document.removeEventListener("visibilitychange", syncRendering);
    engine.dispose();
  });
  syncRendering();
}

source.addEventListener("change", () => {
  const isLive = source.value === "live";
  panel.querySelector("[data-twin-demo-controls]").hidden = isLive;
  panel.querySelector("[data-twin-source-badge]").textContent = isLive ? "FİZİKSEL HAT" : "ÖRNEK VERİ";
  panel.querySelector("[data-twin-source-badge]").classList.toggle("is-live", isLive);
  if (isLive) {
    live = {start:Date.now(), events:[], history:[], seen:new Map(), kpis:{}, released:new Set()};
    model?.live();
    updateLive();
  } else {
    model?.demo();
  }
});
const liveTimer = setInterval(() => {
  if (source.value === "live" && !panel.classList.contains("hidden") && !document.hidden) updateLive();
}, 1000);
window.addEventListener("pagehide", event => { if (!event.persisted) clearInterval(liveTimer); });

showSample(samples[initialScenario.from]);
try {
  await mountModel();
} catch (error) {
  console.error("Dijital İkiz 3B model başlatılamadı", error);
  panel.querySelector("[data-twin-scene-status]").textContent = "3B model açılamadı. Hat şeması gösteriliyor.";
}

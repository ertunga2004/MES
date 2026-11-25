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
const initialScenario = normalRun ?? scenarios[0];

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

function elapsedLabel(ms) {
  const seconds = Math.floor(ms / 1000);
  return [Math.floor(seconds / 60), seconds % 60].map((part) => String(part).padStart(2, "0")).join(":");
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
  const speed = panel.querySelector("#digital-twin-speed");
  const playbackStatus = panel.querySelector("[data-twin-playback-status]");
  const time = panel.querySelector("[data-twin-time]");
  const views = panel.querySelector(".digital-twin-views");
  const viewButtons = views.querySelectorAll("[data-twin-view]");
  const cameraHint = "Sürükle: döndür · sağ tuş: kaydır · tekerlek: yakınlaş";
  let rangeStart;
  let rangeEnd;
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
  }

  function selectScenario(scenario) {
    rangeStart = Date.parse(samples[scenario.from].timestamp) - replay.start;
    rangeEnd = Date.parse(samples[scenario.to].timestamp) - replay.start;
    replay.seek(rangeStart);
    showSample(controller.lineSample);
    updateTime();
    setPlayback(false, "Hazır");
  }

  function draw() {
    if (replay.playing) {
      const delta = Math.min(engine.getDeltaTime(), 100) * Number(speed.value);
      const step = Math.min(delta, rangeEnd - replay.position);
      replay.advance(step);
      controller.update(replay.position, step / 1000);
      showSample(controller.lineSample);
      updateTime();
      if (replay.position >= rangeEnd) setPlayback(false, "Senaryo tamamlandı");
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
    } else {
      engine.stopRenderLoop(draw);
      if (replay.playing) setPlayback(false, "Duraklatıldı");
    }
  }

  selector.addEventListener("change", () => selectScenario(scenarios.find(({ id }) => id === selector.value)));
  play.addEventListener("click", () => {
    if (replay.position >= rangeEnd) selectScenario(scenarios.find(({ id }) => id === selector.value));
    setPlayback(true, "Oynatılıyor");
  });
  pause.addEventListener("click", () => setPlayback(false, "Duraklatıldı"));

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

  selectScenario(initialScenario);
  diagram.hidden = true;
  views.hidden = false;
  selector.disabled = false;
  playback.disabled = false;
  time.parentElement.hidden = false;
  sceneStatus.textContent = cameraHint;

  const observer = new ResizeObserver(syncRendering);
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

showSample(samples[initialScenario.from]);
try {
  await mountModel();
} catch (error) {
  console.error("Dijital İkiz 3B model başlatılamadı", error);
  panel.querySelector("[data-twin-scene-status]").textContent = "3B model açılamadı. Hat şeması gösteriliyor.";
}

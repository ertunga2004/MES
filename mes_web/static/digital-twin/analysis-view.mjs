import { WINDOW_MS } from "./analytics.mjs?v=1";

const number = new Intl.NumberFormat("tr-TR", { maximumFractionDigits:1 });
const energy = new Intl.NumberFormat("tr-TR", { minimumFractionDigits:3, maximumFractionDigits:4 });
const percent = value => Number.isFinite(value) ? `%${number.format(value)}` : "—";
const seconds = value => Number.isFinite(value) ? `${number.format(value / 1000)} sn` : "—";
const count = value => Number.isFinite(value) ? `${number.format(value)} adet` : "—";
const clock = new Intl.DateTimeFormat("tr-TR", { hour:"2-digit", minute:"2-digit", second:"2-digit" });

export function elapsedLabel(ms) {
  const time = Math.floor(Math.max(0, ms) / 1000);
  return [Math.floor(time / 60), time % 60].map(part => String(part).padStart(2, "0")).join(":");
}

const kpiSeries = [
  {key:"oee", title:"OEE", color:"--green", dash:[]},
  {key:"performance", title:"Verimlilik", color:"--blue", dash:[7,4]},
  {key:"quality", title:"Kalite", color:"--yellow", dash:[2,4]},
  {key:"availability", title:"Kullanılabilirlik", color:"--twin-purple", dash:[8,3,2,3]},
];
const crossingSeries = [
  {key:"dwell", title:"Bantta kalış", color:"--blue", dash:[]},
  {key:"stopped", title:"Duruşta bekleme", color:"--yellow", dash:[5,4]},
];
const outputSeries = [{key:"count", title:"Tamamlanan ürün", color:"--green", dash:[]}];

export function createAnalysisView(panel) {
  const select = name => panel.querySelector(`[data-twin-${name}]`);
  const fields = [...panel.querySelectorAll("[data-twin-kpi]")];
  const charts = {
    kpi: createChart(panel.querySelector('[data-twin-chart="kpi"]'), kpiSeries, percent, 100),
    crossings: createChart(panel.querySelector('[data-twin-chart="crossings"]'), crossingSeries, seconds),
    output: createChart(panel.querySelector('[data-twin-chart="output"]'), outputSeries, count),
  };
  let lastReasons;
  return function update(values, history, { demo, start, end, source, stale = false, energyAt, planned = false }) {
    for (const field of fields) {
      const key = field.dataset.twinKpi;
      const value = values[key];
      const text = key === "energyKwh" ? (Number.isFinite(value) ? `${energy.format(value)} kWh` : "—")
        : ["oee","performance","quality"].includes(key) ? percent(value) : seconds(value);
      if (field.textContent !== text) field.textContent = text;
    }
    select("availability").textContent = `Kullanılabilirlik ${percent(values.availability)}`;
    select("robot-share").textContent = `Çalışma oranı ${percent(values.robotShare)}`;
    select("belt-share").textContent = `Hareket oranı ${percent(values.beltShare)}`;
    select("dwell-note").textContent = values.crossings.length
      ? `${values.crossings.length} ürün · ${demo ? "hazne çıkışı" : "giriş veya sensör kuyruğu"} → robot konumu`
      : "Giriş ve robot konumu olayları bekleniyor";
    select("stop-note").textContent = values.stopCount
      ? `${values.stopCount} ürün · bant duruşuyla çakışan süre`
      : "Ürün geçişi ve kesintisiz bant durumu bekleniyor";
    select("energy-note").textContent = demo ? "Simülasyon tahmini"
      : energyAt != null ? `Sayaç · ${clock.format(energyAt)}${stale || end - energyAt > 30000 ? " · son okuma" : ""}`
      : "Enerji sayacı verisi bekleniyor";
    select("performance-note").textContent = demo ? planned ? "Planlı duruş · üretim süresi yok" : "8 sn ideal çevrime göre üretim"
      : "MES vardiya hedefi veya ideal çevrim";
    select("analysis-source").textContent = source;
    select("analysis-time").textContent = demo ? `${elapsedLabel(end - start)} senaryo süresi`
      : stale ? "Son alınan veriler" : `${elapsedLabel(end - start)} gözlem`;
    select("robot-breakdown").textContent = `Çalışıyor ${seconds(values.robotWork)} · Boşta ${seconds(values.robotIdle)}`;
    select("robot-bar").style.width = `${values.robotShare ?? 0}%`;
    const distribution = select("robot-bar").parentElement;
    distribution.hidden = values.robotShare == null;
    const reasonKey = JSON.stringify(values.reasons);
    if (lastReasons !== reasonKey) {
      lastReasons = reasonKey;
      select("stops").replaceChildren(...(values.reasons.length ? values.reasons.map(([reason, ms]) => {
        const row = document.createElement("li");
        const label = document.createElement("span");
        const value = document.createElement("strong");
        label.textContent = reason;
        value.textContent = seconds(ms);
        row.append(label, value);
        return row;
      }) : [Object.assign(document.createElement("li"), {textContent:"Bu aralıkta gözlenen bant duruşu yok."})]));
    }
    const from = Math.max(start, end - WINDOW_MS);
    const timeLabel = at => demo ? elapsedLabel(at - start) : clock.format(at);
    charts.kpi(history.filter(row => row.at >= from), from, end, timeLabel);
    charts.crossings(values.crossings.filter(row => row.at >= from).slice(-40), from, end, timeLabel);
    charts.output(history.filter(row => row.at >= from), from, end, timeLabel, true);
  };
}

function createChart(card, series, format, minimum = 1) {
  const canvas = card.querySelector("canvas");
  const message = card.querySelector("[data-twin-chart-status]");
  const colors = getComputedStyle(card);
  const legend = card.querySelector("[data-twin-legend]");
  for (const {title, color, dash} of series) {
    const label = document.createElement("span");
    const line = document.createElement("i");
    line.setAttribute("aria-hidden", "true");
    line.style.borderTop = `2px ${dash.length ? "dashed" : "solid"} var(${color})`;
    label.append(line, title);
    legend.append(label);
  }
  return function draw(points, start, end, timeLabel, step = false) {
    const data = series.flatMap(({ key }) => points.map(point => point[key]).filter(Number.isFinite));
    canvas.hidden = data.length === 0;
    message.textContent = data.length === 0 ? "Grafik için veri bekleniyor." : series.map(({key,title}) => {
      const latest = points.findLast(point => Number.isFinite(point[key]));
      return `${title} ${format(latest?.[key])}`;
    }).join(" · ");
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (data.length === 0 || width < 160 || !height) return;
    const scale = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(width * scale) || canvas.height !== Math.round(height * scale)) {
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const max = Math.max(minimum, ...data);
    const left = 62, right = width - 12, top = 13, bottom = height - 25;
    const x = at => left + (at - start) / Math.max(1, end - start) * (right - left);
    const y = value => bottom - value / max * (bottom - top);
    ctx.font = "12px Bahnschrift, sans-serif";
    ctx.fillStyle = colors.getPropertyValue("--text-soft");
    ctx.strokeStyle = colors.getPropertyValue("--panel-border");
    ctx.lineWidth = 1;
    ctx.textAlign = "right";
    for (const fraction of [0, .5, 1]) {
      const level = y(max * fraction);
      ctx.beginPath();
      ctx.moveTo(left, level);
      ctx.lineTo(right, level);
      ctx.stroke();
      ctx.fillText(format(step ? Math.round(max * fraction) : max * fraction), left - 6, level + 4);
    }
    ctx.textAlign = "left";
    ctx.fillText(timeLabel(start), left, height - 5);
    ctx.textAlign = "right";
    ctx.fillText(timeLabel(end), right, height - 5);
    for (const {key, color, dash} of series) {
      ctx.strokeStyle = ctx.fillStyle = colors.getPropertyValue(color);
      ctx.lineWidth = 2;
      ctx.setLineDash(dash);
      ctx.beginPath();
      let last = null;
      for (const point of points) {
        const value = point[key];
        if (!Number.isFinite(value)) { last = null; continue; }
        const next = [x(point.at), y(value)];
        if (last) {
          if (step) ctx.lineTo(next[0], last[1]);
          ctx.lineTo(...next);
        } else {
          ctx.moveTo(...next);
        }
        last = next;
      }
      ctx.stroke();
      ctx.setLineDash([]);
      if (last) {
        ctx.beginPath();
        ctx.arc(...last, 3, 0, 2 * Math.PI);
        ctx.fill();
      }
    }
  };
}

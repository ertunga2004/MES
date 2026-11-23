import { cardTypes, stations } from "./kiosk-presets.js?v=2";

function element(tag, text = "", className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
}

export function option(label, value = label) {
  const entry = element("option", label);
  entry.value = value;
  return entry;
}

function field(title, input) {
  const label = element("label");
  label.append(element("span", title), input);
  return label;
}

export function renderStep(step, index) {
  const input = element(step.kind === "choice" ? "select" : "input");
  if (step.kind === "choice") input.append(option("Seç", ""), ...step.options.map(value => option(value)));
  else if (step.kind === "check") input.type = "checkbox";
  else if (step.kind === "number") { input.type = "number"; input.step = "any"; }
  else { input.type = "text"; input.maxLength = 500; }
  input.required = step.required;
  input.dataset.stepIndex = index;
  if (step.kind !== "check") return field(step.label || "Adım adı", input);
  const label = element("label", "", "station-check");
  label.append(input, element("span", step.label || "Adım adı"));
  return label;
}

function button(text, action) {
  const control = element("button", text, action === "finish" ? "station-primary" : "secondary-button");
  control.type = action === "finish" ? "submit" : "button";
  control.dataset.runAction = action;
  return control;
}

function numberInput(name, min = 0) {
  const input = element("input");
  input.type = "number";
  input.name = name;
  input.min = min;
  input.max = 1_000_000_000;
  return input;
}

export function updateClocks(root, active) {
  const now = active?.paused_at ? Date.parse(active.paused_at) : Date.now();
  const openWait = active?.paused_at ? (Date.now() - now) / 1000 : 0;
  const waiting = active?.waiting_seconds || 0;
  const elapsed = active ? (now - Date.parse(active.started_at)) / 1000 - waiting : 0;
  function clock(seconds) {
    const whole = Math.max(0, Math.floor(seconds));
    return [Math.floor(whole / 3600), Math.floor(whole / 60) % 60, whole % 60]
      .map(value => String(value).padStart(2, "0")).join(":");
  }
  for (const node of root.querySelectorAll("[data-clock]")) {
    node.textContent = clock(node.dataset.clock === "waiting" ? waiting + openWait : elapsed);
  }
}

export function renderParked(parked, active) {
  return parked.map(run => {
    const row = element("div", "", "station-block station-stack");
    row.append(element("strong", `${run.item} · ${run.area}`), element("p", `${run.order_id} · ${run.note}`));
    if (!active) {
      const name = element("input");
      name.maxLength = 100;
      name.autocomplete = "name";
      const control = button("İşi geri al", "pickup");
      control.dataset.runId = run.run_id;
      row.append(field("Devam edecek operatör adı", name), control);
    }
    return row;
  });
}

export function renderCards(design, board = {}, { preview = false } = {}) {
  const { active, order, waiting } = board;
  const editable = preview || Boolean(active);
  const grid = element("div", "", "kiosk-card-grid");
  grid.dataset.layout = design.layout || "single";
  const copy = text => text ? [element("p", text, "preserve-lines")] : [];
  const stockInfo = order?.stock_code ? `Malzeme kodu ${order.stock_code}` : "";
  const reports = kind => (active?.reports || []).filter(report => report.kind === kind).slice(-3)
    .map(report => element("p", report.amount ? `${report.note} · ${report.amount} adet` : report.note));
  const renderers = {
    order: () => copy(order ? `${order.id} · Hedef ${order.quantity} ${order.unit}` : "Aktif iş emri bekleniyor"),
    instructions: card => [...copy(design.instructions), ...(card.source === "order" ? copy(stockInfo) : [])],
    before: () => copy(design.before),
    after: () => copy(design.after),
    extra: () => design.sections.filter(section => section.title || section.body).map(section => {
      const note = element("div", "", "station-stack");
      note.append(element("h4", section.title), ...copy(section.body));
      return note;
    }),
    steps: () => editable ? design.steps.map(renderStep) : copy("Adımlar iş başladığında açılır."),
    timer: () => {
      if (!design.timer) return [];
      const clocks = ["Aktif süre", "Bekleme süresi"].map((caption, index) => {
        const line = element("p", caption + " ");
        const value = element("strong", "00:00:00", "station-timer");
        value.dataset.clock = index ? "waiting" : "active";
        line.append(value);
        return line;
      });
      return editable ? [...clocks, button(active?.paused_at ? "Devam et" : "Duraklat", active?.paused_at ? "resume" : "pause")] : clocks;
    },
    progress: card => {
      if (!design.show_target) return [];
      const fromOrder = card.source === "order";
      const target = fromOrder ? order?.quantity : design.target_quantity;
      const unit = (fromOrder ? order?.unit : design.target_unit) || "adet";
      const output = element("p");
      const progress = element("progress");
      progress.max = target || 1;
      progress.setAttribute("aria-label", "İşin ilerlemesi");
      const input = numberInput("quantity");
      input.value = active?.quantity ?? "";
      const sync = () => {
        const quantity = input.valueAsNumber || 0;
        output.textContent = `${quantity} / ${target ?? "—"} ${unit}`;
        progress.value = quantity;
      };
      input.addEventListener("input", sync);
      sync();
      return [output, ...(target ? [progress] : []), ...(editable ? [field("Tamamlanan adet", input)] : [])];
    },
    result: () => {
      if (!design.result_options.length) return [];
      if (!editable) return copy("İş bitiminde sonuç seçilir.");
      const select = element("select");
      select.name = "result";
      select.required = true;
      select.append(option("Seç", ""), ...design.result_options.map(value => option(value)));
      return [field("Sonucu seç", select)];
    },
    status: () => {
      const name = stations[design.station] || design.title || "İstasyon";
      const state = active ? (active.paused_at ? "Bekliyor" : "Çalışıyor") : (order ? "İşe hazır" : "İş emri bekliyor");
      return [...copy(`${name} · ${state}`), ...(board.line_shift_active == null ? [] :
        copy(board.line_shift_active ? "Hat vardiyası açık" : "Hat vardiyası kapalı"))];
    },
    wip: () => {
      const localAreas = design.waiting_areas || [];
      const parked = board.parked || [];
      const cut = waiting && !waiting.legacy_blocked
        ? copy(`Kaplama için hazır ${waiting.available_boxes} kutu · Eşleşmemiş ${waiting.unpaired_tapes} bant`) : [];
      const areas = localAreas.map(area =>
        element("p", `${area} · ${parked.filter(run => run.area === area).length} bekleyen iş`));
      const content = [...cut, ...areas, ...renderParked(parked, active)];
      const interruptible = design.steps.map((step, index) => [step, index]).filter(([step]) => step.interruptible);
      if (!editable || !localAreas.length || !interruptible.length ||
          !design.cards.some(card => card.kind === "steps" && card.visible)) {
        return content.length ? content : copy("Bu kiosk için bağlı bekleme alanı yok.");
      }
      const area = element("select");
      area.name = "park_area";
      area.append(option("Seç", ""), ...localAreas.map(value => option(value)));
      const step = element("select");
      step.name = "park_step";
      step.append(option("Seç", ""), ...interruptible.map(([entry, index]) => option(entry.label || "Adım adı", index)));
      const item = element("input");
      item.name = "park_item";
      item.maxLength = 100;
      const note = element("textarea");
      note.name = "park_note";
      note.maxLength = 300;
      return [...content, field("Bekleme alanı", area), field("Beklemeye alınacak adım", step),
        field("Parça veya iş etiketi", item), field("Bekleme nedeni", note), button("Bekleme alanına al", "park")];
    },
    material: card => {
      const data = card.source === "station" ? copy(stockInfo || "Bağlı iş emrinde malzeme kodu yok.") : [];
      if (!editable) return data;
      const name = element("input");
      name.name = "material_name";
      name.maxLength = 80;
      return [...data, ...reports("material"), field("Talep edilen malzeme", name),
        field("Talep miktarı", numberInput("material_amount", 1)), button("Malzeme talebi kaydet", "material-request")];
    },
    downtime: () => {
      if (!editable) return copy("İş sırasında duruş nedeni kaydedilebilir.");
      const input = element("textarea");
      input.name = "incident_note";
      input.maxLength = 300;
      return [...reports("downtime"), field("Duruş nedeni / açıklaması", input), button("Duruş bildirimi kaydet", "incident")];
    },
    actions: () => editable ? [button("İlerlemeyi kaydet", "save"), button("İşi tamamla", "finish")] : [],
  };
  for (const card of design.cards || []) {
    if (!card.visible) continue;
    const content = [...renderers[card.kind](card), ...copy(card.body)];
    if (!content.length && !preview) continue;
    const section = element("section", "", "station-block station-stack kiosk-layout-card");
    section.dataset.size = card.size;
    section.dataset.card = card.kind;
    section.append(element("h3", card.title || cardTypes[card.kind][0]), ...content);
    grid.append(section);
  }
  return grid;
}

export const WINDOW_MS = 300000;
const STATUS_MS = 15000;
const WATT_MS_PER_KWH = 3600000000;
const DEMO_WATTS = { base: 25, belt: 110, robot: 190 };
const scope = ms => Math.max(0, ms);
const average = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;

export function analyze(events, start, end, { demo = false, planned = false, idealCycleMs } = {}) {
  let lineRunning = false, belt = null, robot = demo ? "idle" : null;
  let at = start, beltUntil = -Infinity, robotUntil = -Infinity;
  let runningMs = 0, beltRun = 0, beltStop = 0, robotWork = 0, robotIdle = 0, wattMs = 0;
  let good = 0;
  const entries = new Map(), releases = new Set();
  const crossings = [], reasons = new Map();

  function advance(next) {
    const span = scope(next - at);
    const beltMs = demo ? span : scope(Math.min(next, beltUntil) - at);
    const robotMs = demo ? span : scope(Math.min(next, robotUntil) - at);
    if (lineRunning) runningMs += span;
    if (belt?.running === true) beltRun += beltMs;
    if (belt?.running === false) {
      beltStop += beltMs;
      if (beltMs) reasons.set(belt.reason, (reasons.get(belt.reason) ?? 0) + beltMs);
    }
    if (!demo || lineRunning) {
      if (robot === "working") robotWork += robotMs;
      if (robot === "idle") robotIdle += robotMs;
    }
    if (demo) {
      wattMs += DEMO_WATTS.base * span + (belt?.running ? DEMO_WATTS.belt * span : 0)
        + (lineRunning && robot === "working" ? DEMO_WATTS.robot * span : 0);
    }
    at = Math.max(at, next);
  }

  for (const event of events) {
    if (event.at > end) break;
    advance(event.at);
    if (event.kind === "line-sample") lineRunning = event.sample.running;
    if (event.kind === "belt-state") {
      belt = { running: event.running, reason: event.reason || "Neden bildirilmedi" };
      beltUntil = event.at + STATUS_MS;
    }
    if (event.kind === "gap") {
      belt = robot = null;
      entries.clear();
    }
    if (event.kind === "pick" || event.kind === "returned" || event.kind === "robot-state") {
      robot = event.kind === "pick" ? "working" : event.kind === "returned" ? "idle" : event.state;
      robotUntil = event.at + STATUS_MS;
    }
    if (event.at < start || !event.id) continue;
    if (event.kind === "departure" || (!demo && event.kind === "queue")) {
      if (!entries.has(event.id)) entries.set(event.id, { at:event.at, known:beltRun + beltStop, stopped:beltStop });
    }
    if (event.kind === "arrived" && entries.has(event.id)) {
      const entry = entries.get(event.id);
      const dwell = event.at - entry.at;
      const complete = Math.abs(beltRun + beltStop - entry.known - dwell) < 1;
      crossings.push({ at:event.at, id:event.id, dwell, stopped:complete ? beltStop - entry.stopped : null });
      entries.delete(event.id);
    }
    if (event.kind === "released" && !releases.has(event.id)) {
      releases.add(event.id);
      // The demo explicitly models one first-pass reject per eight fixture products.
      if (demo && Number(event.id.split("-").at(-1)) % 8 !== 0) good++;
    }
  }
  advance(end);
  const span = end - start;
  const count = releases.size;
  const availability = demo && !planned && span > 0 ? 100 * runningMs / span : null;
  const performance = demo && !planned && runningMs > 0 ? Math.min(100, 100 * idealCycleMs * count / runningMs) : null;
  const quality = demo && count ? 100 * good / count : null;
  const oee = [availability, performance, quality].every(Number.isFinite)
    ? availability * performance * quality / 10000 : null;
  const robotKnown = robotWork + robotIdle;
  const beltKnown = beltRun + beltStop;
  return {
    oee, availability, performance, quality, energyKwh:demo ? wattMs / WATT_MS_PER_KWH : null,
    robotWork:robotKnown ? robotWork : null, robotIdle:robotKnown ? robotIdle : null,
    robotShare:robotKnown ? 100 * robotWork / robotKnown : null,
    beltRun:beltKnown ? beltRun : null, beltStop:beltKnown ? beltStop : null,
    beltShare:beltKnown ? 100 * beltRun / beltKnown : null,
    crossings, count,
    dwell:average(crossings.map(row => row.dwell)),
    stopped:average(crossings.flatMap(row => row.stopped == null ? [] : [row.stopped])),
    stopCount:crossings.filter(row => row.stopped != null).length,
    reasons:[...reasons].sort((a,b) => b[1] - a[1]),
  };
}

export function physicalLog(log) {
  if (log.source !== "mega" || typeof log.message !== "string") return [];
  const at = Date.parse(log.received_at);
  if (!Number.isFinite(at)) return [];
  const text = log.message.replace(/^(?:\[[^\]]+\]\s*)+/, "");
  if (text.startsWith("{")) {
    try {
      const data = JSON.parse(text);
      if (data.type === "performance-telemetry" && Number.isFinite(data.energyKwh) && data.energyKwh >= 0) {
        return [{ at, kind:"energy", value:data.energyKwh }];
      }
      if (data.type === "conveyor-state" && typeof data.running === "boolean") {
        return [{ at, kind:"belt-state", running:data.running, reason:String(data.reason ?? "").slice(0, 120) }];
      }
    } catch { /* Other records are handled by their existing MES consumer. */ }
    return [];
  }
  const [source, module, ...parts] = text.split("|");
  if (source !== "MEGA") return [];
  const fields = Object.fromEntries(parts.filter(part => part.includes("=")).map(part => part.split("=", 2)));
  const id = fields.ITEM_ID;
  const color = { KIRMIZI:"red", MAVI:"blue", SARI:"yellow" }[fields.COLOR || fields.FINAL] ?? "unknown";
  const travelMs = Number(fields.TRAVEL_MS) || 15000;
  if (module === "STATUS") {
    const changes = [];
    if (["RUN", "STOP"].includes(fields.CONVEYOR)) {
      const reason = {MEASURING:"Renk ölçümü", WAIT_ARM:"Robot bekleniyor", STOPPED:"Hat durdu"}[fields.STATE];
      changes.push({ at, kind:"belt-state", running:fields.CONVEYOR === "RUN", reason });
    }
    if (["BUSY", "IDLE", "DONE"].includes(fields.ROBOT)) {
      changes.push({ at, kind:"robot-state", state:fields.ROBOT === "BUSY" ? "working" : "idle" });
    }
    return changes;
  }
  if (fields.PICKPLACE === "START") return [{ at, kind:"pick", id }];
  if (fields.PICKPLACE === "DROP_REACHED") return [{ at, kind:"drop", id }];
  if (fields.EVENT === "PICKPLACE_RETURN_DONE") return [{ at, kind:"returned", id }];
  const kind = {PRODUCT_EXITED:"departure", ARM_POSITION_REACHED:"arrived", RELEASED:"released"}[fields.EVENT]
    ?? (fields.QUEUE === "ENQ" ? "queue" : null);
  return kind && id ? [{ at, kind, id, color, travelMs }] : [];
}

export function liveKpis(snapshot) {
  const oee = snapshot.oee;
  if (!oee?.enabled || !(oee.shift?.active || oee.state_source === "tablet_log")) return {};
  return {
    oee:oee.kpis?.oee, availability:oee.kpis?.availability, performance:oee.kpis?.performance,
    quality:oee.production?.total > 0 ? oee.kpis?.quality : null,
  };
}

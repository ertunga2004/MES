import { PALLET_Z } from './scene.js';
import { LINE_CONFIG, workingTime } from './config.js';

// Kaynak kolun iki eklemini, kavrayıcı merkezini hedefe götürecek şekilde çözer.
function robotPose(x, y) {
  const upper=Math.hypot(.48,1.08), lower=Math.hypot(.97,-.63);
  const relative=Math.acos(Math.max(-1,Math.min(1,(x*x+y*y-upper*upper-lower*lower)/(2*upper*lower))))*-1;
  const first=Math.atan2(y,x)-Math.atan2(lower*Math.sin(relative),upper+lower*Math.cos(relative));
  return {shoulder:first-Math.atan2(1.08,.48), elbow:relative-Math.atan2(-.63,.97)+Math.atan2(1.08,.48)};
}

export function normalizeColor(value) {
  const color = String(value ?? '').trim().toLocaleUpperCase('tr-TR');
  return ({ RED: 'red', KIRMIZI: 'red', KIRMIZİ: 'red', BLUE: 'blue', MAVI: 'blue', MAVİ: 'blue', YELLOW: 'yellow', SARI: 'yellow', SARİ: 'yellow' })[color] || 'unknown';
}

/** Gerçek 99_Raw_Logs mesaj biçimi; eklem açıları bu olaylardan ölçülemez. */
export function parseMessage(payload, metadata = {}) {
  if (typeof payload === 'object' && payload !== null) {
    if (payload.type === 'line-sample') return {kind:'line-sample', sample:payload.sample};
    if (payload.type === 'conveyor-state') return {kind:'belt-state', running:payload.running, reason:payload.reason};
    if (typeof payload.raw_payload === 'string') return parseMessage(payload.raw_payload, { ...metadata, ...payload });
    if (typeof payload.raw_line === 'string') return parseMessage(payload.raw_line, { ...metadata, ...payload });
    if (payload.counts && typeof payload.itemsById === 'object') return { kind: 'snapshot', snapshot: payload };
    throw new Error('Mesaj biçimi tanınmadı. MEGA kaydı veya runtime JSON gerekli.');
  }
  const text = String(payload).trim();
  if (text.startsWith('{')) return parseMessage(JSON.parse(text), metadata);
  const parts = text.split('|');
  if (parts[0] !== 'MEGA') throw new Error('Bu topic için MEGA mesajı bekleniyor.');
  const fields = Object.fromEntries(parts.slice(2).filter(v => v.includes('=')).map(v => {
    const p = v.indexOf('=');
    return [v.slice(0, p), v.slice(p + 1)];
  }));
  let kind = 'status';
  if (fields.EVENT === 'PRODUCT_EXITED') kind = 'departure';
  if (fields.EVENT === 'COLOR_READING_START') kind = 'camera';
  if (parts[1] === 'TCS3200' && fields.FINAL) kind = 'measurement';
  if (fields.QUEUE === 'ENQ') kind = 'queue';
  if (fields.EVENT === 'ARM_POSITION_REACHED') kind = 'arrived';
  if (fields.PICKPLACE === 'START') kind = 'pick';
  if (fields.PICKPLACE === 'DROP_REACHED') kind = 'drop';
  if (fields.EVENT === 'RELEASED') kind = 'released';
  if (fields.EVENT === 'PICKPLACE_DONE') kind = 'done';
  if (fields.EVENT === 'PICKPLACE_RETURN_DONE') kind = 'returned';
  return {
    kind, id: String(fields.ITEM_ID || metadata.item_id || ''),
    color: normalizeColor(fields.FINAL || fields.COLOR || metadata.color_code),
    state: fields.STATE, travelMs: Number(fields.TRAVEL_MS) || LINE_CONFIG.conveyorMs,
    cycleMs: fields.SIMULATION === '1' ? Number(fields.ROBOT_CYCLE_MS) || LINE_CONFIG.robotCycleMs : undefined,
    pending: fields.PENDING !== undefined && fields.PENDING !== '' ? Number(fields.PENDING) : undefined,
    fields,
  };
}

export class FactoryController {
  constructor(factory) { this.factory = factory; this.reset(); }
  reset(model = false) {
    this.factory.reset(model);
    this.items = new Map();
    this.released = new Set();
    this.activeId = null;
    this.now = 0;
    this.counts = { red: 0, blue: 0, yellow: 0, unknown: 0 };
    this.state = model ? 'Model görünümü' : 'Veri bekleniyor';
    this.target = { z: 0, base: 0, shoulder: 0, elbow: 0, grip: 0.08 };
    this.snapshot = null;
    this.events = [];
    this.pending = undefined;
    this.cycle = null;
    this.lineSample = null;
    this.beltState = null;
  }
  apply(event, now = this.now) {
    this.now = now;
    if (event.kind !== 'snapshot') this.events.push({ ...event, at: now });
    if (event.kind === 'belt-state') {this.beltState={running:event.running,reason:event.reason};return;}
    if (event.kind === 'line-sample') {
      this.lineSample = event.sample;
      if (!event.sample.running) this.state = 'Test hattı duraklatıldı';
      return;
    }
    if (event.kind === 'snapshot') {
      this.snapshot = event.snapshot;
      this.state = event.snapshot.operationalState || 'Runtime kaydı';
      // Arşiv ürünleri canlı bantta gösterilmez; yalnızca güncel kuyruk kullanılır.
      const queued = new Set((event.snapshot.queueOrder || []).map(String));
      for (const [id, item] of this.items) {
        if (!queued.has(id) && item.phase !== 'held') this.remove(id);
      }
      for (const id of queued) {
        const item = event.snapshot.itemsById[id];
        if (item && !this.released.has(id)) this.apply({ kind: 'queue', id, color: normalizeColor(item.final_color || item.color || item.sensor_color), travelMs: item.travel_ms || 2000 }, now);
      }
      return;
    }
    const id = event.id || this.activeId;
    const item = id ? this.items.get(id) : null;
    if (['departure', 'measurement', 'queue', 'arrived'].includes(event.kind)) {
      if (!id || this.released.has(id)) return;
      const color = event.color === 'unknown' ? (item?.color || 'unknown') : event.color;
      const mesh = this.factory.product(id, color);
      const data = item || { id, color, mesh, start: now, phase: 'measured', travelMs: event.travelMs };
      data.color = color;
      if (event.kind === 'departure' || event.kind === 'queue') data.travelMs = event.travelMs || data.travelMs;
      if ((event.kind === 'queue' || event.kind === 'departure') && data.phase === 'measured') { data.start = now; data.phase = 'queued'; }
      if (event.kind === 'arrived') { data.phase = 'arrived'; mesh.position.x = LINE_CONFIG.pickupX; this.activeId = id; }
      this.items.set(id, data);
    }
    if (event.kind === 'pick' && item) {
      if (event.cycleMs) {
        const slot=Math.min(LINE_CONFIG.capacity-1,this.counts[item.color] || 0);
        this.cycle = {start:workingTime(now,this.pauses),duration:event.cycleMs,color:item.color,
          dropX:-.22+slot%3*.25, dropY:.17+Math.floor(slot/6)*.23, dropZ:-.12+Math.floor(slot%6/3)*.27};
      }
      this.activeId = id;
      item.phase = 'held';
      item.mesh.parent = this.factory.tool;
      item.mesh.position.set(0, 0, 0);
      this.target.grip = 0.08;
      this.target.z = PALLET_Z[item.color] ?? 3.5;
      this.target.shoulder = 0.15;
      this.target.elbow = -0.25;
    }
    if (event.kind === 'drop' && item) {
      this.target.z = PALLET_Z[item.color] ?? 3.5;
      this.target.shoulder = 0.3;
      this.target.elbow = -0.55;
    }
    // RELEASED ve DONE aynı ürün için tek bir bırakma sayılır.
    if (event.kind === 'released' || event.kind === 'done') {
      if (id && item && !this.released.has(id)) {
        this.released.add(id);
        this.counts[item.color]++;
        this.factory.setPalletCount(item.color, this.counts[item.color]);
        this.remove(id);
      }
      this.target.grip = 0.16;
    }
    if (event.kind === 'returned') {
      this.cycle = null;
      this.target = { z: 0, base: 0, shoulder: 0, elbow: 0, grip: 0.08 };
      if (event.cycleMs) Object.assign(this.target,robotPose(LINE_CONFIG.pickupX+5.5,1.47-.92));
      if (this.activeId === id) this.activeId = null;
    }
    this.state = ({ departure: 'Ürün hazneden çıktı', camera:'Kamera renk okuyor · 3 sn', measurement: 'Renk algılandı', queue: 'Ürün robot kuyruğunda', arrived: 'Ürün alma konumunda', pick: 'Robot ürünü taşıyor', drop: 'Robot bırakma konumunda', released: 'Ürün kasaya bırakıldı', done: 'Alma / bırakma tamamlandı', returned: 'Robot başlangıca döndü' })[event.kind] || event.state || this.state;
    if (event.pending !== undefined && Number.isFinite(event.pending)) this.pending = event.pending;
  }
  remove(id) {
    this.items.get(id)?.mesh.dispose();
    this.items.delete(id);
    this.factory.dynamicProducts.delete(id);
  }
  update(now, deltaSeconds) {
    this.now = now;
    for (const item of this.items.values()) {
      if (item.phase === 'queued') {
        const pauses=this.conveyorPauses || this.pauses;
        const t = Math.max(0, Math.min(1, (workingTime(now,pauses) - workingTime(item.start,pauses)) / item.travelMs));
        // Kaynak sahnede robot sensörün solundadır; ürün o yöne taşınır.
        item.mesh.position.x = LINE_CONFIG.hopperX + t * (LINE_CONFIG.pickupX-LINE_CONFIG.hopperX);
      }
    }
    const rate = 1 - Math.exp(-8 * Math.max(0, deltaSeconds));
    const lerp = (a, b) => a + (b - a) * rate;
    const f = this.factory;
    if (this.cycle) {
      const elapsed = (workingTime(now,this.pauses)-this.cycle.start)/this.cycle.duration*LINE_CONFIG.robotCycleMs;
      const smooth = t => { const p = Math.max(0,Math.min(1,t)); return p*p*(3-2*p); };
      const outbound = smooth((elapsed-LINE_CONFIG.pickupMs)/(LINE_CONFIG.robotDropMs-LINE_CONFIG.pickupMs));
      const returning = smooth((elapsed-LINE_CONFIG.robotReleaseMs)/(LINE_CONFIG.robotCycleMs-LINE_CONFIG.robotReleaseMs));
      const pose = outbound*(1-returning);
      f.robot.position.z = ((PALLET_Z[this.cycle.color] ?? 3.5)+this.cycle.dropZ+.1)*pose;
      f.base.rotation.y = 0;
      const pickupX=LINE_CONFIG.pickupX+5.5;
      const dropX=-3.8+this.cycle.dropX+5.5;
      const targetX=pickupX+(dropX-pickupX)*pose;
      const targetY=1.47+(this.cycle.dropY-1.47)*pose+.3*Math.sin(Math.PI*pose);
      const angles=robotPose(targetX,targetY-.92);
      f.shoulder.rotation.z=angles.shoulder;
      f.elbow.rotation.z=angles.elbow;
      const gap = elapsed >= LINE_CONFIG.robotReleaseMs && elapsed < LINE_CONFIG.robotCycleMs-500 ? .16 : .08;
      f.fingers.forEach((finger,i) => {finger.position.z = (i===0 ? -1 : 1)*gap;});
      return;
    }
    f.robot.position.z = lerp(f.robot.position.z, this.target.z);
    f.base.rotation.y = lerp(f.base.rotation.y, this.target.base);
    f.shoulder.rotation.z = lerp(f.shoulder.rotation.z, this.target.shoulder);
    f.elbow.rotation.z = lerp(f.elbow.rotation.z, this.target.elbow);
    f.fingers.forEach((finger, i) => { finger.position.z = lerp(finger.position.z, (i === 0 ? -1 : 1) * this.target.grip); });
  }
}

/** Tarihi kayıtlar gerçek zaman aralıklarıyla ilerler, sekme durunca zaman atlamaz. */
export class Replay {
  constructor(events, controller) {
    this.events = [...events].sort((a, b) => a.at - b.at);
    this.controller = controller;
    this.start = this.events[0]?.at || 0;
    this.duration = Math.max(1, (this.events.at(-1)?.at || this.start) - this.start);
    this.index = 0;
    this.position = 0;
    this.playing = false;
  }
  seek(ms) {
    this.controller.reset();
    this.index = 0;
    this.position = Math.max(0, Math.min(this.duration, ms));
    this.consume();
    this.controller.update(this.position, 100);
  }
  consume() {
    while (this.index < this.events.length && this.events[this.index].at - this.start <= this.position) {
      const event = this.events[this.index++];
      this.controller.apply(parseMessage(event.payload, event), event.at - this.start);
    }
  }
  advance(ms) {
    if (this.playing) {
      this.position = Math.min(this.duration, this.position + ms);
      this.consume();
      if (this.position >= this.duration) this.playing = false;
    }
  }
}

import { LINE_CONFIG as config, workingTime, wallTime } from './config.js';
import { normalizeColor } from './telemetry.js';

/** Suni veri: her satır hazneden bir ürünün çıkışını tarif eder. */
export function createScenario(data) {
  const products = Array.isArray(data) ? data : data.products;
  if (!Array.isArray(products) || !products.length) throw new Error('products listesi boş olmamalı.');
  if (products.length > 10000) throw new Error('En fazla 10000 ürün yüklenebilir.');
  const start = data.start ? Date.parse(data.start) : Date.now();
  if (!Number.isFinite(start)) throw new Error('start geçerli bir tarih olmalı.');
  const ids = new Set();
  const entries = products.map((product, index) => {
    const id = String(product.id ?? index + 1);
    const exitMs = Number(product.exitSeconds) * 1000;
    const color = normalizeColor(product.color);
    if (!id || /[|\r\n]/.test(id) || ids.has(id)) throw new Error('Ürün kimlikleri benzersiz olmalı ve | içermemeli.');
    if (!Number.isFinite(exitMs) || exitMs < 0) throw new Error('Her üründe exitSeconds, sıfır veya daha büyük bir sayı olmalı.');
    if (color === 'unknown') throw new Error('Renk kırmızı, mavi veya sarı olmalı.');
    ids.add(id);
    return { id, exitMs: Math.round(exitMs), color };
  }).sort((a,b) => a.exitMs-b.exitMs);
  const events = [];
  const pauses = data.pauses || [];
  const conveyorPauses = [];
  let availableAt = 0, pickupUntil = 0, next = 0, completed = 0;
  let sensor = null, sensorUntil = 0, previousRunning = false, pauseStart = 0, lastReason = null;
  const belt = [];
  const sensorTravel = Math.round(config.movingMs*(config.hopperX-config.sensorX)/(config.hopperX-config.pickupX));
  const spacingTravel = config.spacing*config.movingMs/(config.hopperX-config.pickupX);
  const rawColor = {red:'KIRMIZI',blue:'MAVI',yellow:'SARI'};
  const event = (at, payload) => events.push({at:start+at,payload});
  event(0, 'MEGA|CONVEYOR|STATE=TEST_READY');
  const fields = product => `ITEM_ID=${product.id}|COLOR=${rawColor[product.color]}|SIMULATION=1`;
  for (let now=0;now<=200000000;now+=100) {
    const active = workingTime(now,pauses);
    const stopped = pauses.some(p=>now>=p.start&&now<p.end);
    if (previousRunning) belt.forEach(p=>{p.travel=Math.min(config.movingMs,p.travel+100);});
    if (sensor && active>=sensorUntil) {
      sensor.sensed=true;
      event(now,`MEGA|TCS3200|FINAL=${rawColor[sensor.color]}|${fields(sensor)}`);
      sensor=null;
    }
    if (!stopped && !sensor) {
      sensor=belt.find(p=>!p.sensed&&p.travel>=sensorTravel) || null;
      if (sensor) {sensorUntil=active+config.sensorWaitMs;event(now,`MEGA|TCS3200|EVENT=COLOR_READING_START|${fields(sensor)}`);}
    }
    const first=belt[0];
    if (first?.travel>=config.movingMs && !first.arrived) {first.arrived=true;event(now,`MEGA|AUTO|EVENT=ARM_POSITION_REACHED|${fields(first)}`);}
    if (first?.arrived && !stopped && now>=availableAt) {
      belt.shift();completed++;
      event(now,`MEGA|ROBOT|PICKPLACE=START|${fields(first)}|ROBOT_CYCLE_MS=${config.robotCycleMs}`);
      event(wallTime(active+config.robotDropMs,pauses),`MEGA|ROBOT|PICKPLACE=DROP_REACHED|${fields(first)}`);
      event(wallTime(active+config.robotReleaseMs,pauses),`MEGA|ROBOT|EVENT=RELEASED|${fields(first)}`);
      availableAt=wallTime(active+config.robotCycleMs,pauses);
      pickupUntil=active+config.pickupMs;
      event(availableAt,`MEGA|AUTO|EVENT=PICKPLACE_RETURN_DONE|${fields(first)}`);
    }
    if (!stopped && next<entries.length && entries[next].exitMs<=now && (!belt.length || belt.at(-1).travel>=spacingTravel)) {
      const product={...entries[next++],travel:0,sensed:false,arrived:false};belt.push(product);
      event(now,`MEGA|CONVEYOR|EVENT=PRODUCT_EXITED|${fields(product)}|TRAVEL_MS=${config.movingMs}`);
    }
    const reason=stopped ? 'Kaynak hat duraklaması' : active<pickupUntil ? 'Robot ürünü kavrıyor' : sensor ? 'Kamera renk okuyor · 3 sn' : belt[0]?.arrived ? 'Robot için ara stok bekliyor' : !belt.length ? 'Hazne çıkışı bekleniyor' : 'Bant ilerliyor';
    const running=reason==='Bant ilerliyor';
    if (reason!==lastReason) {event(now,{type:'conveyor-state',running,reason});lastReason=reason;}
    if (running!==previousRunning) {
      if (running) {conveyorPauses.push({start:pauseStart,end:now});pauseStart=null;}
      else pauseStart=now;
    }
    previousRunning=running;
    if (completed===entries.length && now>=availableAt) {
      if (pauseStart!==null) conveyorPauses.push({start:pauseStart,end:now});
      return {source:'Suni test verisi',synthetic:true,pauses,conveyorPauses,products:entries.length,events:events.sort((a,b)=>a.at-b.at),oee:[]};
    }
  }
  throw new Error('Test kuyruğu süre sınırında tamamlanamadı.');
}

/** Toplam sayaç değişimi hazne çıkışına çevrilir; renkler temsili rastgeledir. */
export function createTelemetryScenario(data) {
  if (!Array.isArray(data.samples) || !data.samples.length) throw new Error('samples listesi bulunamadı.');
  const samples = data.samples.map(sample => ({...sample, at:Date.parse(sample.timestamp)})).sort((a,b)=>a.at-b.at);
  const start = samples[0].at;
  const pauses = [];
  const products = [];
  let pauseStart = null, previousCount = samples[0].count;
  let seed = 3481267;
  const random = () => {seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return (seed>>>0)/4294967296;};
  const palette = ['red','yellow','blue'];
  let last = null, streak = 0;
  for (let i=0;i<samples.length;i++) {
    const sample = samples[i], previous = samples[i-1];
    if (!Number.isFinite(sample.at) || !Number.isInteger(sample.count) || sample.count < previousCount || typeof sample.running !== 'boolean') throw new Error('Zamanlar ve artan tam sayı sayaçları gerekli.');
    if (!sample.running && pauseStart === null) pauseStart = sample.at-start;
    if (sample.running && pauseStart !== null) {pauses.push({start:pauseStart,end:sample.at-start}); pauseStart=null;}
    const delta = sample.count-previousCount;
    for (let j=1;j<=delta;j++) {
      let color = palette[Math.floor(random()*palette.length)];
      if (streak >= 2 && color === last) {const alternatives = palette.filter(c=>c!==last); color = alternatives[Math.floor(random()*2)];}
      streak = color === last ? streak+1 : 1;
      last = color;
      const exit = sample.at;
      products.push({id:`TEST-${String(products.length+1).padStart(3,'0')}`,color,exitSeconds:(exit-start)/1000});
    }
    previousCount = sample.count;
  }
  if (pauseStart !== null) throw new Error('Test kaydı durmuş durumda bitiyor; kuyruk için yeniden başlama zamanı gerekli.');
  const recording = createScenario({start:new Date(start).toISOString(),products,pauses});
  for (const sample of samples) recording.events.push({at:sample.at,payload:{type:'line-sample',sample}});
  recording.events.sort((a,b)=>a.at-b.at);
  return {...recording, source:'test-telemetry.json · suni test verisi', name:data.name, samples, sourceEnd:samples.at(-1).at,
    assumptions:'Sayaç artışları hazneye gelen ürün talebi kabul edildi; çıkışlar aralıklı verilir. Renkler temsili rastgele. 15 sn hedef: 12 sn hareket + 3 sn kamera beklemesi. Robot kavrarken bant 2 sn durur; diğer ürünlerin duruşları seyahati uzatabilir. Ara stokta ürünler arasında çakışmayı önleyen mesafe korunur; yer yoksa ürün haznede bekler. Kaynak hat duraklamaları korunur; son örnekten sonra kalan kuyruk tamamlanır. Kaynak doluluk üç renk kasasının doluluğu değildir.'};
}

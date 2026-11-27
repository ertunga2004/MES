import assert from "node:assert/strict";
import test from "node:test";
import { analyze, liveKpis, physicalLog } from "../mes_web/static/digital-twin/analytics.mjs";

test("demo KPIs and equipment times use the selected source-clock interval", () => {
  const events = [
    {at:0, kind:"line-sample", sample:{running:true}},
    {at:0, kind:"belt-state", running:true},
    {at:1100, kind:"departure", id:"TEST-007"},
    {at:3000, kind:"belt-state", running:false, reason:"Renk ölçümü"},
    {at:5000, kind:"belt-state", running:true},
    {at:6000, kind:"arrived", id:"TEST-007"},
    {at:7000, kind:"pick", id:"TEST-007"},
    {at:10000, kind:"released", id:"TEST-007"},
    {at:11000, kind:"returned", id:"TEST-007"},
    {at:12000, kind:"line-sample", sample:{running:false}},
    {at:12000, kind:"belt-state", running:false, reason:"Hat durdu"},
  ];
  const options = {demo:true, idealCycleMs:8000};
  const early = analyze(events, 1000, 6000, options);
  const later = analyze(events, 1000, 17000, options);
  assert.equal(early.oee, null);
  assert.equal(later.quality, 100);
  assert.equal(later.availability, 68.75);
  assert.equal(later.dwell, 4900);
  assert.equal(later.stopped, 2000);
  assert.equal(later.robotWork, 4000);
  assert.equal(later.robotIdle, 7000);
  assert.equal(later.beltRun, 9000);
  assert.equal(later.beltStop, 7000);
  assert.ok(later.oee > 0);
  assert.ok(later.energyKwh > early.energyKwh);
  assert.deepEqual(analyze(events, 1000, 6000, options), early);
  assert.equal(analyze(events, 1000, 17000, {...options, planned:true}).oee, null);
});

test("physical durations exclude missing coverage and consume the MES meter format", () => {
  const log = (time, message) => ({source:"mega", received_at:new Date(time).toISOString(), message});
  const events = [
    log(0, "MEGA|STATUS|CONVEYOR=STOP|STATE=MEASURING|ROBOT=IDLE"),
    log(1000, "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=1|COLOR=MAVI"),
    log(20000, "MEGA|AUTO|EVENT=ARM_POSITION_REACHED|ITEM_ID=1"),
  ].flatMap(physicalLog);
  const result = analyze(events, 0, 22000);
  assert.equal(result.beltStop, 15000);
  assert.equal(result.dwell, 19000);
  assert.equal(result.stopped, null);
  assert.equal(result.energyKwh, null);
  assert.deepEqual(physicalLog(log(23000, '{"type":"performance-telemetry","energyKwh":4.2}')),
    [{at:23000, kind:"energy", value:4.2}]);
  assert.equal(physicalLog(log(24000, '{"type":"performance-telemetry","energyKwh":-1}')).length, 0);
});

test("physical OEE reads the dashboard's percentage fields and requires an actual source", () => {
  const oee = {enabled:true, shift:{active:true}, production:{total:12}, kpis:{oee:67, availability:90, performance:87, quality:86}};
  assert.deepEqual(liveKpis({oee}), oee.kpis);
  assert.deepEqual(liveKpis({oee:{...oee, shift:{active:false}}}), {});
  assert.equal(liveKpis({oee:{...oee, production:{total:0}}}).quality, null);
});

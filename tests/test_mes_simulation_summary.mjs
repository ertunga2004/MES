import assert from 'node:assert/strict';
import test from 'node:test';
import { renderSimulationSummary } from '../mes_web/static/simulation-mes.mjs';

test('shows the operations layout before a simulation starts', () => {
  const html = renderSimulationSummary({ state: 'ready', run: null }, 'operations');
  for (const heading of ['Anlık üretim özeti', 'Üretim akışı', 'Darboğaz ve kayıplar',
    'Operasyonel uyarılar', 'İş emri takibi', 'Renk sayaçları', 'Komut paneli']) {
    assert.ok(html.includes(heading), heading);
  }
  assert.match(html, /Hat girişi<\/span><strong>—<\/strong>/);
  assert.match(html, /Kırmızı deposu<\/span><strong>—<\/strong>/);
  assert.doesNotMatch(html, /Bant duruyor|<strong>0 kutu<\/strong>/);
});

test('keeps OEE sections visible with unavailable metrics as blanks', () => {
  const html = renderSimulationSummary({ state: 'ready', run: null }, 'oee');
  for (const heading of ['OEE özeti', 'Vardiya bilgileri', 'Üretim özeti', 'Ekipman performansı',
    'Arıza ve duruşlar', 'Kalite kayıtları', 'Renk performansı', 'Son üretim hareketleri']) {
    assert.ok(html.includes(heading), heading);
  }
  assert.match(html, /OEE<\/span><strong>—<\/strong>/);
  assert.match(html, /Depolama hareketi bekleniyor/);
});

test('populates both layouts from the simulation while leaving unreported OEE inputs blank', () => {
  const snapshot = {
    state: 'completed', run: { id: 'test-run', mode: 'TEST', scenario: 'T07' }, modelTime: 80, target: 3,
    metrics: {
      counters: { entered: 3, completed: 3 },
      inventory: { red: { count: 1, capacity: 20 } },
      events: [{ at: 38, message: 'DEPOLANDI;T07-01;kirmizi;' }],
    },
  };
  const operations = renderSimulationSummary(snapshot, 'operations');
  const oee = renderSimulationSummary(snapshot, 'oee');
  for (const html of [operations, oee]) {
    assert.match(html, /Depolanan<\/span><strong>3 kutu<\/strong>/);
    assert.match(html, /Kırmızı deposu<\/span><strong>1 \/ 20<\/strong>/);
  }
  assert.match(oee, /<td>38 sn<\/td><td>T07-01<\/td><td>Kırmızı<\/td>/);
  assert.match(oee, /Kalite<\/span><strong>—<\/strong>/);
});

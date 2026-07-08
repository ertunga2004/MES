# OEE/KPI v0 Design

## 1. Amaç

Bu doküman, SQL-driven station execution modelinden üretilebilecek ilk OEE/KPI
v0 sinyallerini tasarlar.

Bu doküman OEE implementation değildir. SQL view, API, dashboard, DB sorgusu veya
runtime kodu yazmaz.

## 2. Kapsam

- Operation/step timestamp temelli KPI sinyalleri.
- Availability, performance ve quality için minimum veri yaklaşımı.
- Inventory balance olmadan üretilebilecek KPI'lar.
- Good/scrap result ve `production_flow_events` kullanımı.
- OEE v0 güvenilirlik guardrail'leri.

## 3. Kapsam Dışı

- OEE calculation code.
- SQL view/materialized view.
- Dashboard implementation.
- Inventory movement/balance.
- MESQL reporting sync.
- DB/psql/Docker/test/smoke.

## 4. Veri Kaynakları

Birincil station execution kaynakları:

- `work_order_operation_execution_state.started_at`
- `work_order_operation_execution_state.evidence_completed_at`
- `work_order_operation_execution_state.pending_final_approval_at`
- `work_order_operation_execution_state.closed_at`
- `work_order_operation_steps.started_at`
- `work_order_operation_steps.completed_at`
- `operation_events.event_time`
- `operation_events.received_at`
- `production_flow_events.event_time`
- `production_flow_events.result`
- `route_operations.planned_cycle_time_sec`

Mevcut lifecycle ile compatibility için:

- `work_order_operations.status`
- `station_queue` visibility

## 5. OEE v0 Prensibi

OEE v0 tam kurumsal OEE değildir. İlk hedef:

- Gerçek operation/step timestamp güvenilirliğini ölçmek.
- Station bazlı cycle time görünürlüğü sağlamak.
- Good/scrap event ayrımını görünür yapmak.
- Pending approval gecikmesini ölçmek.
- Mevcut lifecycle'ı bozmadan read-only KPI üretmek.

## 6. Availability v0

Minimum sinyaller:

- Station active duration:
  `execution_state.started_at` ile `closed_at` veya `evidence_completed_at`
  arası.
- Waiting duration:
  queued/ready ile active arasındaki süre, ancak ready timestamp güvenilirliği
  implementation sonrası netleşir.
- Pending approval duration:
  `pending_final_approval_at` ile `closed_at` arası.

Kısıt:

- Planned shift calendar yoksa gerçek availability değil, station execution
  utilization sinyali üretilir.

## 7. Performance v0

Minimum sinyaller:

- Actual operation cycle time.
- Step duration.
- Planned vs actual cycle time.
- Station bazlı average/median cycle time.

Hesap mantığı:

```text
actual_cycle_time = closed_at - started_at
```

Alternatif:

```text
evidence_cycle_time = evidence_completed_at - started_at
approval_wait_time = closed_at - pending_final_approval_at
```

Not:

- `planned_cycle_time_sec` yoksa performance ratio üretilmemelidir.
- Outlier ve missing timestamp kuralları implementation öncesi ayrıca
  belirlenmelidir.

## 8. Quality v0

Minimum sinyaller:

- Good count.
- Scrap count.
- Hold/rework count.
- Approval rejected count.

Kaynaklar:

- `production_flow_events.result`
- `operation_approvals.result`
- Future operation result alanı veya metadata.

Inventory balance olmadan:

- Good/scrap sayılabilir.
- Stok miktarı/current balance hesaplanmaz.
- Location output visibility semantic event üzerinden gösterilebilir.

## 9. Production Flow Event Kullanımı

`production_flow_events` semantic eventtir.

Kullanım:

- Station/location/item dönüşümünü gösterir.
- Good/scrap result taşır.
- OEE/KPI v0 quality count için kaynak olabilir.

Kullanılmaması gereken yer:

- Current stock balance.
- Inventory movement ledger.
- WMS transaction.

Güvenli default:

```text
production_flow_event closed / final approval sonrası oluşur.
```

## 10. KPI v0 Önerilen Metrikler

İlk metrik seti:

- Operation count by station.
- Closed operation count by station.
- Evidence completed count by station.
- Pending final approval count.
- Average operation cycle time.
- Average step duration.
- Approval waiting time.
- Good count.
- Scrap count.
- Rejected event count.
- Duplicate event count.

Bu metrikler read-only hesaplanmalıdır.

## 11. Veri Kalitesi Guardrail'leri

KPI üretmeden önce:

- `started_at` null ise cycle time hesaplanmamalı.
- `closed_at < started_at` invalid sayılmalı.
- `completed_at < started_at` invalid sayılmalı.
- `planned_cycle_time_sec` null ise performance ratio null kalmalı.
- Rejected event accepted event gibi sayılmamalı.
- Duplicate event state mutation üretmediyse production count'a girmemeli.
- `production_flow_events` inventory movement gibi raporlanmamalı.

## 12. Dashboard/Report Fazı

OEE/KPI v0 dashboard ayrı fazdır.

Önerilen sıralama:

```text
1. Runtime timestamps güvenilir olsun.
2. Read-only query/helper tasarlansın.
3. Unit test ve local smoke ayrı yapılır.
4. Dashboard/report tasarımı yapılır.
5. UI implementation ayrı feature flag ile gelir.
```

## 13. Kabul Kriterleri

Bu OEE/KPI v0 design tamamlanmış sayılır, eğer:

- Timestamp kaynakları tanımlıysa.
- Availability/performance/quality v0 ayrımı varsa.
- Inventory balance olmadan hangi KPI'ların üretilebileceği netse.
- Good/scrap result kaynakları açıklanmışsa.
- Data quality guardrail'leri yazılmışsa.
- Implementation yapılmamışsa.

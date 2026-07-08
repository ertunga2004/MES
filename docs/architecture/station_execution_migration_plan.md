# Station Execution Migration Plan

## 1. Amaç

Bu doküman, gelecekte hazırlanacak `004_station_execution_schema.sql` migration
dosyasının kapsamını ve güvenli yazım sırasını planlar.

Bu doküman SQL migration değildir. Migration dosyası oluşturmaz, DB'ye bağlanmaz
ve psql çalıştırmaz.

## 2. Kapsam

Planlanan schema kapsamı:

- `mes.items`
- `mes.process_routes`
- `mes.route_operations`
- `mes.operation_steps`
- `mes.station_event_sources`
- `mes.work_order_operation_execution_state`
- `mes.work_order_operation_steps`
- `mes.operation_events`
- `mes.operation_approvals`
- `mes.production_flow_events`

Bu tablolar, station/location Paket A modelinin üzerine additive olarak gelir.
Mevcut `mes.locations` ve `mes.station_location_bindings` tabloları yeniden
tanımlanmaz.

## 3. Kapsam Dışı

- SQL migration yazımı.
- Seed SQL yazımı.
- Runtime engine implementation.
- Kiosk dynamic action implementation.
- IoT/MQTT adapter implementation.
- OEE/KPI calculation implementation.
- Inventory movement ledger.
- Inventory balance/current stock view.
- MESQL push/pull veya sync.
- Mevcut operation lifecycle mutation.
- Docker/DB/psql çalıştırma.

## 4. Migration Stratejisi

İlk station execution migration additive olmalıdır:

- Existing table drop yok.
- Existing column rename yok.
- Existing lifecycle status mutation yok.
- Existing `work_order_operations.status` enum veya değer seti kırılmaz.
- Existing `station_queue` behavior değiştirilmez.
- New tables side-by-side eklenir.
- Seed verisi schema migration'dan ayrı tutulur.
- Inventory movement/balance bu migration'a dahil edilmez.

Önerilen dosya ayrımı:

```text
004_station_execution_schema.sql
005_station_execution_seed_minimal.sql
```

Alternatif daha ayrık yaklaşım:

```text
004_station_execution_master_data.sql
005_station_execution_runtime.sql
006_station_execution_seed_minimal.sql
```

Default öneri:

```text
004_station_execution_schema.sql
005_station_execution_seed_minimal.sql
```

Gerekçe:

- İlk schema migration tek dosyada kalırsa review daha kolaydır.
- Seed ayrı tutulduğu için tekrar uygulanabilir setup davranışı daha kontrollü
  olur.
- Runtime implementation başlamadan önce schema tek noktadan doğrulanabilir.

## 5. Tablo Oluşturma Sırası

Önerilen create order:

```text
1. mes.items
2. mes.process_routes
3. mes.route_operations
4. mes.station_event_sources
5. mes.operation_steps
6. mes.work_order_operation_execution_state
7. mes.work_order_operation_steps
8. mes.operation_events
9. mes.operation_approvals
10. mes.production_flow_events
```

Sıra gerekçesi:

- `items`, `process_routes`, `route_operations`, `station_event_sources` master
  data temelidir.
- `operation_steps`, `route_operation_id` üzerinden `route_operations` satırına
  bağlanır.
- Runtime state ve step instance tabloları mevcut work order tablolarına child
  gibi davranır.
- `operation_events` append-only ledger olarak runtime tablolara referans
  verebilir.
- `operation_approvals` ve `production_flow_events`, event ve operation kapanış
  semantiği üzerine oturur.

## 6. FK Circularity Değerlendirmesi

Circularity riski olan ilişkiler:

- `work_order_operation_execution_state.last_event_id -> operation_events.event_id`
- `work_order_operation_execution_state.last_approval_id -> operation_approvals.approval_id`
- `work_order_operation_steps.started_by_event_id -> operation_events.event_id`
- `work_order_operation_steps.completed_by_event_id -> operation_events.event_id`
- `operation_events.work_order_operation_step_id -> work_order_operation_steps.work_order_operation_step_id`
- `operation_approvals.source_event_id -> operation_events.event_id`
- `production_flow_events.source_operation_event_id -> operation_events.event_id`
- `production_flow_events.source_approval_id -> operation_approvals.approval_id`

Plan:

- Audit link kolonları nullable başlatılmalıdır.
- Insert akışı step/state oluşturmayı event linklerinden ayırmalıdır.
- İlk migration'da zorunlu olmayan audit FK'leri nullable FK olarak kalabilir.
- Daha katı constraints, runtime engine stabil olduktan sonra ayrı migration ile
  değerlendirilebilir.

## 7. Nullable Başlayacak Alanlar

Önerilen nullable audit/link alanları:

- `work_order_operation_execution_state.last_event_id`
- `work_order_operation_execution_state.last_approval_id`
- `work_order_operation_execution_state.current_step_code`
- `work_order_operation_execution_state.started_at`
- `work_order_operation_execution_state.evidence_completed_at`
- `work_order_operation_execution_state.pending_final_approval_at`
- `work_order_operation_execution_state.closed_at`
- `work_order_operation_steps.started_at`
- `work_order_operation_steps.completed_at`
- `work_order_operation_steps.started_by_event_id`
- `work_order_operation_steps.completed_by_event_id`
- `operation_events.work_order_id`
- `operation_events.work_order_operation_id`
- `operation_events.work_order_operation_step_id`
- `operation_events.external_event_id`
- `operation_events.idempotency_key`
- `operation_approvals.source_event_id`
- `production_flow_events.source_operation_event_id`
- `production_flow_events.source_approval_id`

Gerekçe:

- İlk migration, boş runtime tablolar üzerinde uygulanacaktır.
- Runtime engine henüz yoktur.
- Audit linkleri event akışı sırasında sonradan oluşabilir.
- Compatibility mode için mevcut lifecycle ile yeni state yan yana okunmalıdır.

## 8. Non-Nullable Başlaması Önerilen Alanlar

Master data için:

- Business key alanları.
- `active`.
- `created_at`.
- Ana enum/policy alanları.

Runtime tablolar için:

- Surrogate primary key.
- Public id/business id.
- `work_order_operation_id` gerektiren child tablolar.
- `station_code` gerektiren station-scoped kayıtlar.
- Runtime status alanları.
- `created_at`.

Detaylar migration SQL taslağında ayrıca review edilmelidir.

## 9. Unique ve Idempotency Planı

Master data unique önerileri:

- `items.item_code`
- `process_routes(route_code, version)`
- `route_operations.route_operation_id`
- `route_operations(route_code, route_version, sequence_no)`
- `route_operations(route_code, route_version, operation_code)`
- `operation_steps(route_operation_id, step_no)`
- `operation_steps(route_operation_id, step_code)`
- `station_event_sources(station_code, source_code)`

Runtime unique/idempotency önerileri:

- `work_order_operation_execution_state.work_order_operation_id`
- `work_order_operation_steps(work_order_operation_id, step_code)`
- `work_order_operation_steps(work_order_operation_id, step_no)`
- `operation_events(station_code, event_source, external_event_id)` where
  `external_event_id is not null`
- `operation_events.idempotency_key` where `idempotency_key is not null`
- `operation_approvals(work_order_operation_id, approval_type)` where
  `result = 'approved'` opsiyonel MVP constraint olarak değerlendirilebilir.

## 10. Check Constraint Planı

MVP enumlar dar tutulmalıdır:

- `item_type`
- `operation_completion_policy`
- `start_mode`
- `finish_mode`
- `actor_type`
- `source_type`
- `event_channel`
- `work_order_operation_steps.status`
- `work_order_operation_execution_state.execution_status`
- `operation_events.event_type`
- `operation_approvals.approval_type`
- `operation_approvals.result`
- `production_flow_events.result`

Future enum değerleri ilk migration'da aktif check listesine alınmamalıdır veya
metadata/disabled seed olarak belgelenmelidir.

## 11. Existing Tablolarla İlişki

Referans verilecek mevcut tablolar:

- `mes.stations`
- `mes.locations`
- `mes.work_orders`
- `mes.work_order_operations`

Korunacak davranışlar:

- `station_queue` mevcut queue visibility için kullanılmaya devam eder.
- Local successor activation mevcut haliyle korunur.
- `work_order_operations.status` yeni execution state değerleriyle
  genişletilmez.
- Yeni engine aktif edilene kadar sidecar state read/compare amaçlı kalır.

## 12. Seed Ayrımı

Schema migration seed içermemelidir.

Minimal seed ayrı dosyada veya runbook ile ele alınmalıdır:

- Items.
- Process route.
- Route operations.
- Operation steps.
- Station event sources.

Seed tasarımı için ayrı kaynak:

```text
docs/architecture/station_execution_seed_setup_plan.md
```

## 13. Backup / Apply / Verify / Rollback Runbook Yaklaşımı

Bu doküman runbook değildir, ancak migration apply runbook şu başlıkları
içermelidir:

- Git çalışma ağacı kontrolü.
- Docker compose/container sağlık kontrolü.
- Backup alınması.
- Migration dosyasının destructive keyword taraması.
- `git diff --check` kontrolü.
- Migration apply komutu.
- Schema/table/index/constraint doğrulama sorguları.
- Seed ayrı uygulanacaksa ayrı onay kapısı.
- Health endpoint doğrulaması.
- Local successor activation regression kontrolü.
- Station/location read-only API regression kontrolü.
- Kiosk read-only station/location card regression kontrolü.
- Rollback stratejisi.

Rollback yaklaşımı:

- İlk tercih DB backup restore planıdır.
- Production-benzeri ortamda manuel drop rollback kullanılmamalıdır.
- Additive tablolar boşsa ayrı rollback migration değerlendirilebilir, fakat bu
  ilk apply runbook'unda açık onay gerektirmelidir.

## 14. Migration Öncesi Review Checklist

Migration SQL yazılmadan önce:

- Tablo sırası bu planla uyumlu mu?
- FK circularity alanları nullable mı?
- `operation_steps` FK'si `route_operation_id` üzerinden mi?
- Event source validation station-scoped mı belgelenmiş?
- `operation_events` idempotency station-scoped mı?
- `work_order_operation_execution_state` sidecar olarak mı kalıyor?
- Existing lifecycle'a yazan herhangi bir DDL/DML yok mu?
- Seed yok mu?
- Inventory movement/balance yok mu?
- MESQL yok mu?
- Future enumlar aktif check listesine yanlışlıkla eklenmemiş mi?

## 15. Kabul Kriterleri

Bu migration planı tamamlanmış sayılır, eğer:

- `004_station_execution_schema.sql` kapsamı netse.
- Tablo oluşturma sırası tanımlıysa.
- FK circularity riski ve nullable başlangıç alanları belgelenmişse.
- Additive migration guardrail'leri açıkça yazılmışsa.
- Seed ayrımı netse.
- Backup/apply/verify/rollback runbook yaklaşımı tarif edilmişse.
- Kod, SQL migration veya DB uygulaması yapılmamışsa.

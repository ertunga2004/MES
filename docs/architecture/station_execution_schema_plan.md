# SQL-Driven Station Execution Schema Plan

## 1. Bağlam

Local MES DB operation lifecycle şu an local execution source-of-truth
durumundadır. Mevcut akışta `mes.work_order_operations` ve
`mes.station_queue` operasyon başlatma, tamamlama, successor operation
aktivasyonu ve iş emri kapanışı için kullanılır. Local successor activation
doğrulanmıştır.

Station/location modeli mevcuttur:

- `mes.locations`
- `mes.station_location_bindings`

Kiosk read-only station/location görünürlüğü tamamlanmıştır. Kiosk artık
istasyonun input, active WIP, output good, output scrap ve output buffer
lokasyonlarını gösterebilir.

Eksik olan katman:

- SQL-driven operation step execution.
- Event ledger.
- Dynamic Kiosk action buttons.
- Production flow event.
- Pending final approval.
- OEE/KPI timestamp temeli.

Bu doküman SQL migration değildir; migration öncesi schema planıdır.

### 1.1 Migration Öncesi Değerlendirme Notu

Mevcut schema plan, SQL-driven station execution için doğru temel yönü kurar.
Planın güçlü tarafları:

- Master data ve runtime execution tablolarını ayırması.
- Additive migration yaklaşımı.
- Mevcut `work_order_operations` ve `station_queue` lifecycle'ını hemen
  bozmaması.
- `production_flow_events` ile inventory movement'ı ayırması.
- DB-level ve app-level validation ayrımı.
- OEE/KPI için timestamp temeli önermesi.

Migration öncesi üç konu netleşmelidir:

- `operation_steps` ilişki anahtarı.
- Station-scoped event source validation.
- Yeni execution status'un mevcut lifecycle'a dokunmadan nerede tutulacağı.

## 2. Tasarım Kararları

Explicit default kararlar:

- `start_mode` ve `finish_mode` ayrı fiziksel alanlar olacaktır.
- `control_policy` engine için ana zorunlu alan olmayacaktır.
- `control_policy` convenience/seed/metadata alanı olarak opsiyonel
  değerlendirilebilir.
- MVP enumları dar tutulacaktır.
- Future enum değerleri ilk migration'a alınmayacaktır veya disabled metadata
  olarak bırakılacaktır.
- Auto step için event source zorunludur.
- Kiosk sadece current actionable step'i gösterecektir.
- `operation_completion_policy = auto_complete_pending_approval` ana hedef
  modeldir.
- `production_flow_event` için güvenli default final approval / closed sonrası
  oluşmasıdır.
- Inventory movement ayrı fazdır; bu schema plan inventory balance yapmayacaktır.
- Append-only `operation_events` temel audit kaydı olacaktır.
- Runtime state mutation ile event ledger ayrılacaktır.
- `operation_steps`, `route_operation_id` üzerinden `route_operations` satırına
  bağlanacaktır.
- `operation_code` okunabilir business alan olarak kalacaktır; tek başına step
  FK gibi kullanılmayacaktır.
- Event source station-scoped kabul edilecektir.
- Yeni execution state için `mes.work_order_operation_execution_state` sidecar
  tablosu kullanılacaktır.
- Mevcut `work_order_operations.status` ilk fazda bozulmayacaktır.

## 3. Yeni Tablo Grupları

### 3.1 Master Data

- `mes.items`
- `mes.process_routes`
- `mes.route_operations`
- `mes.operation_steps`
- `mes.station_event_sources`

### 3.2 Runtime Execution

- `mes.work_order_operation_execution_state`
- `mes.work_order_operation_steps`
- `mes.operation_events`
- `mes.operation_approvals`
- `mes.production_flow_events`

Runtime table sırası:

```text
1. mes.work_order_operation_execution_state
2. mes.work_order_operation_steps
3. mes.operation_events
4. mes.operation_approvals
5. mes.production_flow_events
```

Açıklama:

- `work_order_operation_execution_state`, operation-level state'i tutar.
- `work_order_operation_steps`, step-level state'i tutar.
- `operation_events`, append-only event ledger'dır.
- `operation_approvals`, final/supervisor/quality approval audit kaydıdır.
- `production_flow_events`, inventory movement olmayan semantic ürün akış
  eventidir.

### 3.3 Future / Later

- Inventory movement / balance tabloları bu plana dahil edilmeyecek.
- MESQL sync tabloları bu plana dahil edilmeyecek.
- Setup automation tabloları bu plana dahil edilmeyecek.

## 4. Tablo Tasarım Formatı

Her tablo bu formatla değerlendirilir:

```text
Tablo adı:
Amaç:
Kolonlar:
Primary key:
Unique constraint:
Foreign key adayları:
Check constraint adayları:
Index adayları:
Insert/update davranışı:
MVP/Future notu:
```

## 5. `mes.items`

Tablo adı: `mes.items`

Amaç: Sistemde hareket eden veya dönüşen item master datasını tutar.

Kolonlar:

- `item_pk`
- `item_id`
- `item_code`
- `item_name`
- `item_type`
- `unit`
- `active`
- `source_system`
- `external_ref`
- `metadata`
- `created_at`
- `updated_at`

Primary key:

- `item_pk`

Unique constraint:

- `item_code`
- Opsiyonel: `(source_system, external_ref)` where `external_ref is not null`

Foreign key adayları:

- İlk fazda yok.

Check constraint adayları:

- `item_type in ('raw_material', 'semi_finished', 'finished_good', 'card', 'box', 'package', 'service')`
- `item_code <> ''`
- `unit <> ''`

Index adayları:

- `(item_type, active)`
- `(active, item_code)`

Insert/update davranışı:

- İlk setup manuel seed ile yapılır.
- `item_code` değişmez business key kabul edilir.
- `active = false` ile pasifleştirme tercih edilir; delete önerilmez.

MVP/Future notu:

- İlk faz manuel seed.
- İleride MESQL ortak master data'dan çekilebilir.

## 6. `mes.process_routes`

Tablo adı: `mes.process_routes`

Amaç: Bir item veya ürün ailesi için üretim rotasını tanımlar.

Kolonlar:

- `route_pk`
- `route_id`
- `route_code`
- `route_name`
- `item_code`
- `version`
- `active`
- `source_system`
- `external_ref`
- `metadata`
- `created_at`
- `updated_at`

Primary key:

- `route_pk`

Unique constraint:

- `(route_code, version)`
- Opsiyonel: `(source_system, external_ref)` where `external_ref is not null`

Foreign key adayları:

- `item_code -> mes.items.item_code`

Check constraint adayları:

- `route_code <> ''`
- `version > 0`

Index adayları:

- `(item_code, active)`
- `(route_code, active)`

Insert/update davranışı:

- Versioned route yaklaşımı kullanılmalıdır.
- Operasyonda kullanılmış route versiyonları geriye dönük değiştirilmemelidir.
- Yeni proses değişikliği yeni `version` ile gelmelidir.

MVP/Future notu:

- MVP'de tek route: `ROUTE_BOX_PACKAGING_V1`.

## 7. `mes.route_operations`

Tablo adı: `mes.route_operations`

Amaç: Route içindeki operasyon sırasını, istasyonu, input/output item dönüşümünü
ve completion policy'yi tanımlar.

Kolonlar:

- `route_operation_pk`
- `route_operation_id`
- `route_code`
- `route_version`
- `sequence_no`
- `operation_code`
- `operation_name`
- `station_code`
- `input_item_code`
- `output_item_code`
- `input_qty_per_cycle`
- `output_qty_per_cycle`
- `input_location_role`
- `output_location_role`
- `scrap_location_role`
- `operation_completion_policy`
- `planned_cycle_time_sec`
- `active`
- `metadata`
- `created_at`
- `updated_at`

Primary key:

- `route_operation_pk`

Unique constraint:

- `route_operation_id`
- `(route_code, route_version, sequence_no)`
- `(route_code, route_version, operation_code)`

Foreign key adayları:

- `(route_code, route_version) -> mes.process_routes(route_code, version)`
- `station_code -> mes.stations.station_code`
- `input_item_code -> mes.items.item_code`
- `output_item_code -> mes.items.item_code`

Check constraint adayları:

- `operation_completion_policy in ('manual_close', 'auto_close_on_required_steps', 'auto_complete_pending_approval')`
- `input_qty_per_cycle > 0`
- `output_qty_per_cycle >= 0`
- `sequence_no > 0`
- `planned_cycle_time_sec is null or planned_cycle_time_sec > 0`
- `input_location_role in ('input', 'active_wip')`
- `output_location_role in ('output_good', 'output_buffer')`
- `scrap_location_role is null or scrap_location_role = 'output_scrap'`

Index adayları:

- `(station_code, active)`
- `(route_code, route_version, sequence_no)`
- `(operation_code, active)`

Insert/update davranışı:

- Route operation master data versioned route altında seed edilir.
- Runtime `work_order_operations` bu master datadan türetilebilir.
- Mevcut `work_order_operations` tablosu hemen değiştirilmez.

MVP/Future notu:

- MVP'de `auto_complete_pending_approval` ana hedef modeldir.
- Future supervisor/quality approval policy değerleri ilk migration'a aktif enum
  olarak alınmamalıdır.
- `route_operation_id`, operation step tanımlarının bağlanacağı güvenli
  business/runtime köprü alanıdır.
- `operation_code` kullanıcıya okunabilir kod olarak kalır.
- `operation_code` tek başına step FK gibi kullanılmamalıdır.

## 8. `mes.operation_steps`

Tablo adı: `mes.operation_steps`

Amaç: Operation master data altında yürütülecek step tanımlarını tutar.

Kolonlar:

- `operation_step_pk`
- `operation_step_id`
- `route_operation_id`
- `operation_code`
- `step_no`
- `step_code`
- `step_name`
- `start_mode`
- `finish_mode`
- `start_event_source_code`
- `finish_event_source_code`
- `required_for_completion`
- `records_duration`
- `approval_required_after_finish`
- `actor_type`
- `active`
- `metadata`
- `created_at`
- `updated_at`

Primary key:

- `operation_step_pk`

Unique constraint:

- `(route_operation_id, step_no)`
- `(route_operation_id, step_code)`

Foreign key adayları:

- `route_operation_id -> mes.route_operations.route_operation_id`
- `operation_code` okunabilir business alan olarak tutulur, tek başına FK olarak
  kullanılmaz.
- `start_event_source_code` ve `finish_event_source_code` doğrudan global FK
  değildir. Setup validator bu alanları `route_operation.station_code` ile
  birlikte `mes.station_event_sources(station_code, source_code)` karşılığına
  bağlar.

Check constraint adayları:

- `start_mode in ('none', 'manual_start', 'auto_start', 'implicit_start')`
- `finish_mode in ('none', 'manual_finish', 'auto_finish', 'implicit_finish')`
- `actor_type in ('operator', 'system', 'sensor', 'robot', 'observer', 'plc')`
- `step_no > 0`
- `start_mode <> 'auto_start' OR start_event_source_code IS NOT NULL`
- `finish_mode <> 'auto_finish' OR finish_event_source_code IS NOT NULL`

Index adayları:

- `(route_operation_id, active, step_no)`
- `(operation_code, active)`
- `(start_event_source_code)`
- `(finish_event_source_code)`

Insert/update davranışı:

- Master step tanımı route/operation setup sırasında seed edilir.
- Runtime instance'lar `mes.work_order_operation_steps` içine kopyalanır.
- Operation başladıktan sonra master step update etmek mevcut runtime instance'ı
  otomatik değiştirmemelidir.

MVP/Future notu:

- MVP schema default:
  - `operation_steps`, `route_operation_id` üzerinden `route_operations`
    satırına bağlanmalıdır.
  - `operation_code` okunabilir business alan olarak tutulabilir; gerçek ilişki
    `route_operation_id` olmalıdır.
- `control_policy` fiziksel zorunlu kolon olmamalıdır.
- İstenirse `metadata.control_policy_seed` veya opsiyonel text kolon olarak
  saklanabilir.
- Future `external_start`, `scheduled_start`, `external_finish`, `timed_finish`
  değerleri disabled metadata olarak belgelenebilir.
- Eğer ileride global operation catalog oluşturulursa bu ayrı bir future faz
  olabilir.
- MVP'de route-operation-scoped step modeli daha güvenlidir.
- Aynı `operation_code` farklı route/version altında tekrar kullanılsa bile step
  ambiguity oluşmamalıdır.
- `start_mode = auto_start` ise `start_event_source_code` zorunludur.
- `finish_mode = auto_finish` ise `finish_event_source_code` zorunludur.
- `auto_both` convenience policy kullanılıyorsa iki source code da zorunludur.
- `evidence_only` policy kullanılıyorsa `finish_event_source_code` zorunludur.

## 9. `mes.station_event_sources`

Tablo adı: `mes.station_event_sources`

Amaç: Bir istasyondan gelebilecek sensor, robot, observer, PLC veya system event
kaynaklarını tanımlar.

Kolonlar:

- `event_source_pk`
- `event_source_id`
- `station_code`
- `source_code`
- `source_name`
- `source_type`
- `event_channel`
- `mqtt_topic`
- `active`
- `metadata`
- `created_at`
- `updated_at`

Primary key:

- `event_source_pk`

Unique constraint:

- `(station_code, source_code)`

Foreign key adayları:

- `station_code -> mes.stations.station_code`

Check constraint adayları:

- `source_type in ('kiosk', 'sensor', 'robot', 'observer', 'plc', 'system')`
- `event_channel in ('mqtt', 'http', 'kiosk', 'internal', 'manual')`
- `source_code <> ''`
- `event_channel <> 'mqtt' OR mqtt_topic IS NOT NULL`

Index adayları:

- `(station_code, active)`
- `(source_type, active)`
- `(event_channel, active)`

Insert/update davranışı:

- Event source inactive yapılabilir; silme önerilmez.
- Auto step'lerin source_code değerleri burada tanımlı ve active olmalıdır.
- Bu active uyumluluğu DB check ile tam kurulamaz; app-level setup validation
  gerekir.

MVP/Future notu:

- `source_code` global unique kabul edilmez.
- `source_code` sadece `station_code` ile birlikte anlamlıdır.
- Event source station-scoped kabul edilir.
- Auto step validation, `route_operation.station_code +
  operation_step.source_code` kombinasyonunun
  `mes.station_event_sources(station_code, source_code)` içinde active olup
  olmadığını kontrol etmelidir.
- MVP event sources:
  - `COLOR_SENSOR_ENTRY`
  - `ROBOT_ARM_DROP`
  - `KIOSK_OPERATOR`

## 10. `mes.work_order_operation_steps`

Tablo adı: `mes.work_order_operation_steps`

Amaç: Work order operation için runtime step instance state'ini tutar.

Kolonlar:

- `work_order_operation_step_pk`
- `work_order_operation_step_id`
- `work_order_operation_id`
- `work_order_id`
- `operation_code`
- `step_code`
- `step_no`
- `station_code`
- `status`
- `started_at`
- `completed_at`
- `started_by_event_id`
- `completed_by_event_id`
- `required_for_completion`
- `records_duration`
- `approval_required_after_finish`
- `created_at`
- `updated_at`
- `metadata`

Primary key:

- `work_order_operation_step_pk`

Unique constraint:

- `(work_order_operation_id, step_code)`
- `(work_order_operation_id, step_no)`

Foreign key adayları:

- `work_order_operation_id -> mes.work_order_operations.work_order_operation_id`
- `work_order_id -> mes.work_orders.order_id`
- `station_code -> mes.stations.station_code`
- `started_by_event_id -> mes.operation_events.event_id`
- `completed_by_event_id -> mes.operation_events.event_id`

Check constraint adayları:

- `status in ('pending', 'active', 'completed', 'skipped', 'failed', 'cancelled')`
- `step_no > 0`
- `completed_at is null OR started_at is null OR completed_at >= started_at`

Index adayları:

- `(work_order_operation_id, status, step_no)`
- `(station_code, status)`
- `(work_order_id, step_no)`
- `(required_for_completion, status)`

Insert/update davranışı:

- Instance'lar iş emri release anında veya operation ready olduğunda
  üretilebilir.
- Plan default önerisi: operation ready olduğunda üretmek daha güvenlidir.
- Release anında üretmek raporlama için erken görünürlük sağlar.

MVP/Future notu:

- Circular FK riskine karşı `started_by_event_id` ve `completed_by_event_id`
  nullable başlamalıdır.

## 11. `mes.work_order_operation_execution_state`

Tablo adı: `mes.work_order_operation_execution_state`

Amaç: Yeni station execution engine için operation-level runtime state'i mevcut
`work_order_operations` tablosunu bozmadan yan yana tutmak.

Kolonlar:

- `execution_state_pk`
- `execution_state_id`
- `work_order_operation_id`
- `work_order_id`
- `station_code`
- `operation_code`
- `execution_status`
- `operation_completion_policy`
- `current_step_code`
- `started_at`
- `evidence_completed_at`
- `pending_final_approval_at`
- `closed_at`
- `last_event_id`
- `last_approval_id`
- `created_at`
- `updated_at`
- `metadata`

Primary key:

- `execution_state_pk`

Unique constraint:

- `work_order_operation_id`

Foreign key adayları:

- `work_order_operation_id -> mes.work_order_operations.work_order_operation_id`
- `work_order_id -> mes.work_orders.order_id`
- `station_code -> mes.stations.station_code`
- `last_event_id -> mes.operation_events.event_id`
- `last_approval_id -> mes.operation_approvals.approval_id`

Check constraint adayları:

- `execution_status in ('queued', 'ready', 'active', 'evidence_completed', 'pending_final_approval', 'closed', 'cancelled', 'failed')`
- `closed_at is null OR evidence_completed_at is not null`
- `pending_final_approval_at is null OR evidence_completed_at is not null`

Index adayları:

- `(station_code, execution_status)`
- `(work_order_id, execution_status)`
- `(updated_at desc)`

Insert/update davranışı:

- Yeni engine enabled olduğunda, operation ready veya active aşamasında
  oluşturulabilir.
- Mevcut `work_order_operations.status` ile uyumluluk mapping'i gerekir.
- İlk fazda source-of-truth geçişi yapılmayacak; side-by-side tutulacak.
- Feature flag / compatibility mode ile kullanılmalıdır.

MVP/Future notu:

- Bu tablo migration sırasında additive olarak eklenebilir.
- Mevcut lifecycle değiştirilmeden read/compare/test yapılabilir.
- İleride stabil olduğunda `work_order_operations.status` ile konsolidasyon
  kararı verilebilir.

## 12. `mes.operation_events`

Tablo adı: `mes.operation_events`

Amaç: Kiosk/sensor/robot/observer/PLC/system eventlerini append-only audit
olarak tutmak.

Kolonlar:

- `event_pk`
- `event_id`
- `event_time`
- `received_at`
- `station_code`
- `work_order_id`
- `work_order_operation_id`
- `work_order_operation_step_id`
- `operation_code`
- `step_code`
- `event_source`
- `event_type`
- `external_event_id`
- `idempotency_key`
- `payload`
- `accepted`
- `rejection_reason`
- `created_at`

Primary key:

- `event_pk`

Unique constraint:

- `(station_code, event_source, external_event_id)` where `external_event_id is not null`
- `idempotency_key` where `idempotency_key is not null`

Foreign key adayları:

- `station_code -> mes.stations.station_code`
- `work_order_id -> mes.work_orders.order_id`
- `work_order_operation_id -> mes.work_order_operations.work_order_operation_id`
- `work_order_operation_step_id -> mes.work_order_operation_steps.work_order_operation_step_id`

Check constraint adayları:

- `event_type in ('step_start', 'step_finish', 'evidence', 'approval', 'reject', 'system_transition')`
- `accepted in (true, false)`
- `accepted = true OR rejection_reason IS NOT NULL`

Index adayları:

- `(station_code, event_time desc)`
- `(work_order_operation_id, event_time desc)`
- `(work_order_operation_step_id, event_time desc)`
- `(accepted, event_time desc)`
- `(event_source, event_time desc)`

Insert/update davranışı:

- Append-only tasarlanmalıdır.
- Rejected events mümkünse `accepted = false` olarak tutulmalıdır.
- Runtime state mutation bu tablodan ayrı yapılmalıdır.

MVP/Future notu:

- İlk implementation'da update/delete route açılmamalıdır.
- Idempotency zorunlu olmalıdır.
- Sadece `(event_source, external_event_id)` yeterli değildir; aynı
  `source_code` farklı istasyonlarda tekrar kullanılabilir.
- MVP'de string alanlarla başlanacaksa idempotency key `station_code`
  içermelidir.
- IoT tarafı event source global id üretmiyorsa station-scoped idempotency
  zorunludur.
- Future seçenek olarak `event_source_id + external_event_id` unique yapısı
  değerlendirilebilir.

## 13. `mes.operation_approvals`

Tablo adı: `mes.operation_approvals`

Amaç: Final approval / supervisor approval / quality approval kayıtlarını tutar.

Kolonlar:

- `approval_pk`
- `approval_id`
- `work_order_operation_id`
- `work_order_id`
- `approval_type`
- `approved_by`
- `approved_at`
- `result`
- `note`
- `source_event_id`
- `created_at`
- `metadata`

Primary key:

- `approval_pk`

Unique constraint:

- MVP'de opsiyonel: `(work_order_operation_id, approval_type)` where `result = 'approved'`

Foreign key adayları:

- `work_order_operation_id -> mes.work_order_operations.work_order_operation_id`
- `work_order_id -> mes.work_orders.order_id`
- `source_event_id -> mes.operation_events.event_id`

Check constraint adayları:

- `approval_type in ('final', 'supervisor', 'quality')`
- `result in ('approved', 'rejected', 'hold')`
- `approved_by <> ''`

Index adayları:

- `(work_order_operation_id, approval_type, approved_at desc)`
- `(approval_type, result, approved_at desc)`

Insert/update davranışı:

- Approval audit olarak append-oriented tutulmalıdır.
- Reddetme veya hold kararları yeni kayıt olarak tutulmalıdır.

MVP/Future notu:

- MVP için final approval operator seviyesi yeterli kabul edilebilir.
- Supervisor/quality approval future değer olarak kalabilir.

## 14. `mes.production_flow_events`

Tablo adı: `mes.production_flow_events`

Amaç: Bir operation sonucu ürünün station/location/item dönüşümünü semantic event
olarak tutmak.

Kolonlar:

- `flow_event_pk`
- `flow_event_id`
- `work_order_id`
- `work_order_operation_id`
- `station_code`
- `operation_code`
- `input_location_code`
- `output_location_code`
- `input_item_code`
- `output_item_code`
- `input_qty`
- `output_qty`
- `result`
- `event_time`
- `source_operation_event_id`
- `source_approval_id`
- `created_at`
- `metadata`

Primary key:

- `flow_event_pk`

Unique constraint:

- Opsiyonel: `(work_order_operation_id, source_approval_id)` where
  `source_approval_id is not null`
- Opsiyonel: `(work_order_operation_id, source_operation_event_id)` where
  `source_operation_event_id is not null`

Foreign key adayları:

- `work_order_id -> mes.work_orders.order_id`
- `work_order_operation_id -> mes.work_order_operations.work_order_operation_id`
- `station_code -> mes.stations.station_code`
- `input_location_code -> mes.locations.location_code`
- `output_location_code -> mes.locations.location_code`
- `input_item_code -> mes.items.item_code`
- `output_item_code -> mes.items.item_code`
- `source_operation_event_id -> mes.operation_events.event_id`
- `source_approval_id -> mes.operation_approvals.approval_id`

Check constraint adayları:

- `result in ('good', 'scrap', 'rework', 'hold', 'cancelled')`
- `input_qty >= 0`
- `output_qty >= 0`
- `event_time IS NOT NULL`

Index adayları:

- `(work_order_id, event_time desc)`
- `(work_order_operation_id, event_time desc)`
- `(station_code, event_time desc)`
- `(output_location_code, event_time desc)`
- `(result, event_time desc)`

Insert/update davranışı:

- Append-oriented semantic event olarak tutulmalıdır.
- Inventory movement değildir.
- Final approval / closed sonrası oluşturulması güvenli defaulttur.

MVP/Future notu:

- MVP görünürlük için `evidence_completed` anında da üretilebilir; bu durumda
  event'in inventory balance kaydı olmadığı açıkça belirtilmelidir.

## 15. Mevcut Tablolarla Uyumluluk

Mevcut tablolar:

- `mes.work_orders`
- `mes.work_order_operations`
- `mes.station_queue`
- `mes.stations`
- `mes.locations`
- `mes.station_location_bindings`

Uyumluluk planı:

- Mevcut lifecycle bozulmayacak.
- `station_queue` hemen kaldırılmayacak.
- Yeni step engine side-by-side eklenecek.
- Mevcut complete behavior doğrudan değiştirilmeden önce feature flag veya
  compatibility mode kullanılacak.
- Eski `completed` state'i ile yeni `evidence_completed` / `closed` ayrımı için
  mapping gerekir.
- `mes.locations` ve `mes.station_location_bindings` mevcut read-only context
  çözümleme için kullanılmaya devam eder.
- `route_operations.input_location_role`, `output_location_role` ve
  `scrap_location_role`, station-location binding role değerlerine bağlanır.
- `work_order_operation_steps` mevcut `work_order_operations` satırını
  genişleten runtime child table gibi davranır.
- `operation_events` mevcut `work_order_events` yerine hemen geçmez; ilk fazda
  daha detaylı step-level ledger olarak yan yana durur.
- `production_flow_events`, mevcut `production_completions` ile karıştırılmamalı;
  item/location dönüşüm semantiği için ayrı tutulmalıdır.
- `work_order_operation_execution_state`, mevcut `work_order_operations`
  satırını bozmadan yeni execution state'i yan yana tutar.
- Mevcut lifecycle source-of-truth hemen değiştirilmez.
- Yeni state machine önce feature flag / compatibility mode ile test edilir.
- Mevcut `completed` state'i ile yeni `evidence_completed` / `closed` ayrımı
  bu sidecar tablo üzerinden gözlemlenir.
- İlk implementation'da `work_order_operations.status` üzerine doğrudan yeni
  status değerleri yazılmamalıdır.
- Eski lifecycle ile yeni execution state arasında mapping dokümante
  edilmelidir.
- Successor activation mevcut davranışı ilk fazda korunacaktır.

## 16. Migration Stratejisi

Önerilen migration yaklaşımı:

- Additive migration.
- Mevcut tablo/drop yok.
- Mevcut kolon rename yok.
- Side-by-side yeni tablolar.
- Seed verisi ayrı dosya veya runbook.
- Önce schema.
- Sonra manual seed.
- Sonra read-only validation.
- Sonra runtime engine.
- Sonra Kiosk dynamic action.
- Sonra IoT adapter.

Migration sırası için iki opsiyon:

```text
Option A:
004_station_execution_schema.sql
005_station_execution_seed_minimal.sql
```

```text
Option B:
004_station_execution_master_data.sql
005_station_execution_runtime.sql
006_station_execution_seed_minimal.sql
```

Öneri:

- İlk aşamada schema migration ve seed ayrı tutulmalıdır.
- Master data ve runtime schema aynı migration içinde olabilir, ancak seed
  ayrılmalıdır.
- Minimal seed için ayrı runbook veya ayrı migration kullanılmalıdır.
- `004_station_execution_schema.sql` içinde master data tabloları, runtime
  sidecar state tablosu, operation step runtime tablosu, operation event ledger,
  approval ledger ve production flow semantic event tablosu planlanabilir.
- Seed ayrı kalmalıdır: `005_station_execution_seed_minimal.sql`.
- Migration yazılmadan önce FK circularity sırası ayrıca kontrol edilmelidir.
- `operation_events` / `work_order_operation_steps` /
  `work_order_operation_execution_state` ilişkilerinde bazı FK'ler nullable
  başlamalıdır.
- İlk migration additive olmalıdır.
- Existing table drop yok.
- Existing column rename yok.
- Existing lifecycle mutation yok.
- Seed migration veya seed runbook ayrı tutulmalıdır.
- Inventory movement / balance migration bu fazda yoktur.

## 17. Validation Stratejisi

### DB-Level Validation

- Enum check constraints.
- Unique constraints.
- FK constraints.
- Quantity checks.
- Timestamp checks.
- Partial unique constraints for idempotency.

DB-level validation örnekleri:

- `start_mode` enum.
- `finish_mode` enum.
- `operation_completion_policy` enum.
- `event_type` enum.
- `result` enum.
- `input_qty >= 0`.
- `output_qty >= 0`.
- `completed_at >= started_at`.
- `operation_steps.route_operation_id` FK.
- `work_order_operation_execution_state.work_order_operation_id` unique.
- `execution_status` check constraint.
- `pending_final_approval_at` ve `closed_at` timestamp dependency checks.

### App-Level / Setup Validation

- `operation_steps.route_operation_id` geçerli bir route operation'a bağlı mı?
- Aynı `route_operation_id` altında `step_no` benzersiz mi?
- Aynı `route_operation_id` altında `step_code` benzersiz mi?
- `auto_start` source active mı?
- `auto_finish` source active mı?
- Event source station ile uyumlu mu?
- `start_event_source_code`, `route_operation.station_code` altında tanımlı ve
  active mı?
- `finish_event_source_code`, `route_operation.station_code` altında tanımlı ve
  active mı?
- Auto step source code başka istasyona aitse setup invalid sayılmalı.
- Operation'da required step var mı?
- Final approval step birden fazla mı?
- `tracking_only` required mı?
- Route operation item/location role tutarlı mı?
- Kiosk manual step actor tanımı var mı?
- Auto step idempotency strategy tanımlı mı?
- `operation_completion_policy = auto_complete_pending_approval` için approval
  step veya final approval path var mı?
- `work_order_operation_execution_state` ile mevcut
  `work_order_operations.status` mapping'i tutarlı mı?

DB constraints temel tutarlılığı korur; cross-table, station scoped ve future
policy validasyonları app-level setup validator ile yapılmalıdır.

## 18. Manual Seed/Setup Planına Temel Örnek Data

Bu bölüm örnek data fikridir; SQL insert değildir.

### Items

- `RAW_BOX`
- `COLOR_CLASSIFIED_BOX`
- `PACKAGED_PRODUCT`

### Stations

- `ASSEMBLY_01`
- `PACKAGING_01`

### Route

- `ROUTE_BOX_PACKAGING_V1`

### Route Operations

- Operation 10: assembly/color/robot/gözlem.
- Operation 20: packaging.

### Event Sources

- `COLOR_SENSOR_ENTRY`
- `ROBOT_ARM_DROP`
- `KIOSK_OPERATOR`

### ASSEMBLY_01 Steps

- Color sensor evidence.
- Robot arm drop.
- Operator observation approval.

### PACKAGING_01 Steps

- Packaging start.
- Packaging finish/final approval.

## 19. OEE/KPI Etkisi

Bu schema plan OEE/KPI v0 için şu veri temelini sağlar:

- Step timestamps.
- Operation timestamps.
- `operation_events`.
- `production_flow_events`.
- Good/scrap result.
- `planned_cycle_time_sec`.
- Actual cycle time hesaplanabilir alanlar.

OEE/KPI için hesaplanabilecek ilk sinyaller:

- Operation cycle time: operation start ile closed/evidence completed arası.
- Step duration: step start ile step completed arası.
- Waiting time: queued/ready ile active arası.
- Good/scrap count: operation result veya production flow result üzerinden.
- Station active time: active operation/step sürelerinden.

Bu plan OEE hesaplama implementation'ı değildir.

## 20. Riskler

| Risk | Etki | Önlem |
| --- | --- | --- |
| Schema çok erken katılaşır | Sensor/policy ihtiyaçları kilitlenir | MVP enumlarını dar tut, metadata/versioning bırak |
| Mevcut lifecycle kırılır | Kiosk ve local execution bozulur | Side-by-side schema, feature flag, compatibility mode |
| Event source validation DB'de tam yapılamaz | Invalid auto step setup kabul edilir | App-level setup validator zorunlu olsun |
| Circular FK riski | Migration veya insert sırası zorlaşır | Event FK'leri nullable başlasın, state/event linkleri aşamalı kurulsun |
| `operation_events` ile `work_order_operation_steps` FK sıralama problemi | Event ve step insert akışı kırılır | Önce step instance oluştur, event FK nullable tut |
| Duplicate event handling eksik kalır | Step iki kez ilerler | Partial unique ve idempotency key zorunlu olsun |
| `production_flow_event` inventory movement sanılır | Balance yanlış anlaşılır | Dokümantasyonda semantic event olarak işaretle, inventory ayrı faz |
| Final approval ve closed ayrımı UI'da karışır | Operasyon erken kapanmış algılanır | UI/API state label mapping ayrı tasarlansın |
| Kiosk dynamic action geçişi mevcut Kiosk'u kırabilir | Operatör akışı bozulur | Önce read-only action preview, sonra feature flag ile enable |
| `operation_code` tek başına step FK gibi kullanılır | Farklı route/version altında step ambiguity oluşur | `route_operation_id` ile bağla |
| Event source global sanılır | Aynı `source_code` farklı istasyonlarda çakışır | `station_code + source_code` validation kullan |
| Yeni execution status mevcut status alanına doğrudan yazılır | Mevcut lifecycle kırılır | Sidecar `work_order_operation_execution_state` kullan |
| Sidecar state ile mevcut lifecycle çelişir | UI/API farklı state gösterir | Compatibility mapping ve feature flag ile karşılaştırmalı test yap |
| FK circularity yanlış kurulursa migration zorlaşır | Migration / insert akışı kırılır | Nullable FK ve aşamalı constraint yaklaşımı kullan |

## 21. Açık Kararlar

Default kararlar:

- `operation_steps`, `route_operation_id` ile bağlanır.
- Event source station-scoped kabul edilir.
- Yeni execution state için sidecar tablo tercih edilir.
- Mevcut `work_order_operations.status` ilk fazda bozulmaz.
- `control_policy` fiziksel zorunlu kolon olmayacaktır.
- `start_mode` ve `finish_mode` ayrı fiziksel alanlar olacaktır.
- Kiosk sadece current actionable step'i gösterecektir.

Varsayılan öneriler:

- Step instances operation ready olduğunda üretilebilir.
- Circular FK riskine karşı event FK'leri nullable başlayabilir.
- `production_flow_event` closed sonrası daha güvenli.
- Final approval operator seviyesi MVP için yeterli.
- `control_policy` fiziksel zorunlu kolon olmamalı.
- Setup validation önce CLI veya script olarak tasarlanmalı.
- Seed başlangıçta SQL veya JSON olabilir; workbook sonraki faz.

Açık kalanlar:

- Step instance ready anında mı release anında mı üretilecek?
- `production_flow_event` `evidence_completed` mı closed sonrası mı üretilecek?
- Seed SQL mi JSON mu olacak?
- Setup validator CLI mı web endpoint mi olacak?
- Runtime engine feature flag adı ne olacak?
- Sidecar state UI/API'ye hangi fazda açılacak?
- `operation_events` ile `work_order_operation_steps` arasındaki FK yönü nasıl
  kurulacak?

## 22. Kabul Kriterleri

Bu doküman için kabul kriterleri:

- Yeni tablo grupları net.
- Her tablo için amaç ve kritik alanlar var.
- Enum/check/unique/FK/index adayları var.
- Mevcut tablolarla uyumluluk planı var.
- Migration stratejisi additive.
- Seed/setup planına temel olacak örnek data var.
- Validation stratejisi DB-level ve app-level ayrılmış.
- Inventory movement kapsam dışı net.
- OEE/KPI etkisi açıklanmış.
- Implementation yapılmadı.
- `operation_steps` ilişki ambiguity'si giderildi.
- Event source station-scoped validation netleştirildi.
- Yeni execution state'in nerede tutulacağı netleştirildi.
- Mevcut lifecycle'ı bozmayan side-by-side state yaklaşımı tanımlandı.
- Migration öncesi circular FK riski not edildi.
- Current lifecycle ile yeni station execution state arasındaki mapping ihtiyacı
  belirtildi.

# Current Database Schema

Migration dosyası:

```text
db/migrations/001_initial_mes_schema.sql
```

Schema:

```text
mes
```

Tablo sayısı:

```text
15
```

Bu migration başlangıç mirror/outbox iskeletidir. Tablolar source-of-truth olarak ilan edilmemiştir. JSONB `payload` ve `metadata` alanları mevcut JSON/Excel/FERP şekilleri kanıtlanana kadar esnek mirror tutmak için kullanılır.

Tablolar:

| Tablo | Amaç | Önemli alanlar | Natural key / external_ref yaklaşımı |
|---|---|---|---|
| `mes.work_orders` | Runtime work order kayıtlarının ilk mirror hedefi. | `work_order_pk`, `order_id`, `status`, `product_code`, `target_quantity`, `external_ref`, `payload`, `metadata`, `created_at`, `updated_at` | `order_id` unique; `external_ref` runtime order id ile uyumlu. |
| `mes.work_order_events` | Work order geçiş/olay logları için aday. | `order_id`, `event_type`, `event_at`, `external_ref`, `payload`, `metadata` | Runtime transition/completion log event referansı. |
| `mes.production_completions` | Üretim tamamlanma ve miktar kayıtları için aday. | `order_id`, `completed_at`, `quantity`, `quality_status`, `external_ref`, `payload` | Item/completion event ref. |
| `mes.oee_snapshots` | OEE trend/snapshot kayıtları için aday. | `snapshot_at`, `availability`, `performance`, `quality`, `oee`, `external_ref`, `payload` | Snapshot timestamp + reason. |
| `mes.downtime_events` | Duruş/fault event mirror hedefi. | `started_at`, `ended_at`, `reason`, `source_system`, `external_ref`, `payload` | Fault/request id veya timestamp. |
| `mes.maintenance_records` | Bakım/teknisyen oturumu ve checklist kayıtları. | `session_id`, `device_id`, `started_at`, `completed_at`, `external_ref`, `payload` | Runtime maintenance session id. |
| `mes.quality_overrides` | Kalite override kayıtları. | `item_id`, `classification`, `recorded_at`, `operator_id`, `external_ref`, `payload` | Item id + recorded_at veya override id. |
| `mes.vision_events` | Vision ölçüm/event mirror hedefi. | `event_type`, `detected_at`, `item_id`, `external_ref`, `payload` | Vision measure/event id. |
| `mes.device_sessions` | Kiosk/technician/device oturumları. | `device_id`, `session_id`, `started_at`, `ended_at`, `external_ref`, `payload` | Device/session id. |
| `mes.ferp_import_batches` | FERP import batch metadata. | `source_file`, `imported_at`, `status`, `external_ref`, `payload` | Source file + imported_at. |
| `mes.ferp_export_outbox` | FERP export outbox metadata. | `export_id`, `order_id`, `status`, `created_at`, `external_ref`, `payload` | Export id. |
| `mes.operators` | Operatör master data mirror. | `operator_code`, `operator_name`, `external_ref`, `payload` | Operator code. |
| `mes.stations` | Station/work center master data mirror. | `station_code`, `station_name`, `line_id`, `external_ref`, `payload` | Station code/id. |
| `mes.error_types` | Fault/error type master data. | `error_code`, `error_name`, `severity`, `external_ref`, `payload` | Error code. |
| `mes.maintenance_steps` | Bakım adım/checklist master data. | `step_code`, `step_name`, `station_code`, `external_ref`, `payload` | Step code. |

`mes.work_orders` özel durum:

- Runtime JSON'dan mirror edilen ilk tablodur.
- 6 kayıt başarıyla yazılmıştır.
- Idempotent upsert test edilmiştir.
- Duplicate oluşmadan tekrar apply edildiğinde count 6 kalmıştır.
- Verify script JSON ve DB kayıtlarını temiz eşleştirmiştir.

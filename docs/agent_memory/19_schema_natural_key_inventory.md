# MES Schema and Natural-Key Inventory

## 1. Purpose
Bu dokümanın amacı F1E compatibility report ve F1F UNIQUE migration öncesi statik schema/natural-key envanteri oluşturmaktır. Mevcut PostgreSQL veritabanındaki tabloların statik yapısı, benzersizlik (uniqueness) kısıtlamaları ve mevcut kaynak-veritabanı eşleşmeleri analiz edilmiştir.

## 2. Source Files Reviewed
Bu doküman aşağıdaki dosyalar incelenerek oluşturulmuştur:
- `docs/agent_memory/17_sql_source_of_truth_transition_masterplan.md`
- `docs/agent_memory/18_feature_flag_matrix.md`
- `docs/agent_memory/13_db_population_status.md`
- `docs/agent_memory/14_work_orders_status_policy.md`
- `docs/agent_memory/15_vision_events_source_policy.md`
- `docs/agent_memory/16_validated_db_population_checkpoint.md`
- `db/migrations/001_initial_mes_schema.sql`
- `scripts/mirror_work_orders_to_db.py`
- `scripts/mirror_production_completions_to_db.py`
- `scripts/mirror_vision_events_from_excel.py`
- `scripts/verify_work_orders_db_mirror.py`
- `scripts/verify_production_completions_db_mirror.py`
- `scripts/verify_vision_events_db_mirror.py`
- `mes_web/db/config.py`
- `mes_web/db/connection.py`
- `mes_web/db/health.py`
- `mes_web/db/safe_write.py`

## 3. Current Validated Population
E5F doğrulama kontrol noktasına göre (Validated DB Population Checkpoint):
- **mes.work_orders** = 6, verify clean
- **mes.production_completions** = 8, verify clean
- **mes.vision_events** = 43, verify clean
- **device_sessions / oee_snapshots / downtime_events / maintenance_records / quality_overrides** = deferred/empty

## 4. Table Inventory

| Table | Purpose | Primary Key | Foreign Keys | external_ref exists? | Timestamp Column(s) | Payload/Metadata | Populated Count | Current Source | Mirror/Backfill Status | Live-Hook Readiness |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `work_orders` | Üretim iş emirleri | `work_order_pk` | Yok | Evet | started_at, completed_at, created_at, updated_at | Evet | 6 | JSON / FERP | Validated, Current-state | F1F sonrası |
| `work_order_events` | İş emri tarihçesi | `event_pk` | Yok | Evet | event_at, created_at | Evet | 0 | - | Deferred | Deferred |
| `production_completions` | Üretilen adet logları | `completion_pk` | Yok | Evet | completed_at, created_at | Evet | 8 | JSON runtime state | Validated, Hook-ready | Requires F1F |
| `oee_snapshots` | OEE durum kayıtları | `snapshot_pk` | Yok | Evet | snapshot_at, created_at | Evet | 0 | - | Deferred | Deferred |
| `downtime_events` | Arıza/duruş kayıtları | `downtime_pk` | Yok | Evet | started_at, ended_at, created_at, updated_at | Evet | 0 | - | Deferred | Deferred |
| `maintenance_records` | Bakım adımları | `maintenance_pk` | Yok | Evet | recorded_at, created_at, updated_at | Evet | 0 | - | Deferred | Deferred |
| `quality_overrides` | Kalite manuel ezmeleri | `quality_override_pk` | Yok | Evet | recorded_at, created_at | Evet | 0 | - | Deferred | Deferred |
| `vision_events` | Kamera tahmin eventleri| `vision_event_pk` | Yok | Evet | detected_at, created_at | Evet | 43 | Excel backfill | Validated, Hook-ready | Requires F1F |
| `device_sessions` | İstasyon oturumları | `device_session_pk` | Yok | Evet | started_at, ended_at, created_at, updated_at | Evet | 0 | JSON runtime state | Deferred | Unsafe (Needs F2) |
| `ferp_import_batches` | FERP senkronizasyonu | `import_batch_pk` | Yok | Evet | imported_at, created_at, updated_at | Evet | 0 | - | Deferred | - |
| `ferp_export_outbox` | FERP'e gönderilecekler | `export_pk` | Yok | Evet | created_for_export_at, exported_at | Evet | 0 | - | Deferred | - |
| `operators` | Operatör listesi | `operator_pk` | Yok | Evet | created_at, updated_at | Evet | 0 | - | Deferred | - |
| `stations` | İstasyon listesi | `station_pk` | Yok | Evet | created_at, updated_at | Evet | 0 | - | Deferred | - |
| `error_types` | Hata tipleri sözlüğü | `error_type_pk` | Yok | Evet | created_at, updated_at | Evet | 0 | - | Deferred | - |
| `maintenance_steps` | Bakım senaryosu | `maintenance_step_pk` | Yok | Evet | created_at, updated_at | Evet | 0 | - | Deferred | - |

## 5. Natural Key Inventory

### A. mes.work_orders
- **Proposed natural key:** `order_id` (ve/veya `external_ref`)
- **Current actual source key:** `order_id` (JSON `id` field)
- **Current mirror script key:** `order_id` eşleşmesine bakıyor.
- **Verify script comparison key:** `order_id`
- **Is key stable?:** Evet.
- **Is key event-level or current-state?:** Current-state (upsert).
- **Can this support live hook?:** Evet, ancak current-state doğası gereği history tablosundan farklı bir upsert hook'u gerektirir.
- **Risk notes:** Status tarihçesi bu tabloda tutulamaz, `work_order_events` tablosu gerektirir. Mevcut UNIQUE kısıtlaması `order_id` üzerindedir.

### B. mes.production_completions
- **Proposed natural key:** `external_ref` (Order/Item relation tabanlı, oee_state.py completion hash).
- **Current actual source key:** Runtime JSON `itemsById` ve log yapısı.
- **Current mirror script key:** `external_ref`
- **Verify script comparison key:** `external_ref`
- **Is key stable?:** Evet, `order_id + item_id` veya `session_id` kombinasyonundan oluşur.
- **Is key event-level or current-state?:** Event-level (append-only logic, but technically represents a logged event).
- **Can this support live hook?:** Evet. Event semantics korunarak MQTT raw veri yerin OEE completion cycle içerisine hook atılmalıdır.
- **Risk notes:** `external_ref` kısıtlaması şemada YOK. UNIQUE(external_ref) olmadan live hook çalıştırılırsa duplicate veriler oluşabilir. Migration gerektirir.

### C. mes.vision_events
- **Proposed natural key:** `external_ref` (`vision_track_id + event_type + detected_at` veya API dönüş `event_key`)
- **Current actual source key:** Excel backfill ID'leri veya raw detection payload.
- **Current mirror script key:** `external_ref`
- **Verify script comparison key:** `external_ref`
- **Is key stable?:** Evet, fakat `vision_track_id` tek başına yeterli değildir (aynı track birden fazla event üretebilir).
- **Is key event-level or current-state?:** Event-level.
- **Can this support live hook?:** Evet. Ancak hook raw MQTT üzerinde değil, `oee_state.apply_vision_event` dönüşündeki çıktı/normalize edilmiş payload üzerinden çalışmalıdır.
- **Risk notes:** `external_ref` kısıtlaması şemada YOK. UNIQUE(external_ref) olmadan live hook duplicate yaratır. Migration gerektirir.

### D. mes.device_sessions
- **Proposed natural key:** N/A (Şu anki JSON state `deviceSessions` tablosu session bazlı event tutmuyor).
- **Current actual source key:** Sadece aktif device_id listesi.
- **Current mirror script key:** N/A
- **Verify script comparison key:** N/A
- **Is key stable?:** Hayır. `sessionId` ve `startedAt` runtime statüsünde tutarlı değil.
- **Is key event-level or current-state?:** Karma. Logically event-level olmalı ama physically current-state çalışıyor.
- **Can this support live hook?:** Hayır. History tablosu için şu an unsafe. Live apply ertelenmeli.
- **Risk notes:** Yeniden mimari (F2) tasarlanana kadar atlanmalıdır.

### E. mes.oee_snapshots
- **Proposed natural key:** `snapshot_at` + `shift_id`
- **Current actual source key:** N/A (Henüz source yok, runtime JSON'dan anlık snapshot alınmalı)
- **Current mirror script key:** N/A
- **Verify script comparison key:** N/A
- **Is key stable?:** Policy gerektirir (örn. saatte bir veya değişimde).
- **Is key event-level or current-state?:** Event-level.
- **Can this support live hook?:** Şu an hayır. Policy netleşmeli.
- **Risk notes:** F4A/F4B öncesi migration/hook yazılmamalıdır. Duplicate key ve timestamp policy eksiktir.

### F. Diğerleri (downtime_events, maintenance_records, quality_overrides)
Şu an için defer/empty durumdadır. İlerleyen fazlarda benzer analiz yapılacaktır.

## 6. Constraint / Index Inventory
Mevcut migration `001_initial_mes_schema.sql` üzerinden çıkarılan kısıtlama envanteri:

- **PRIMARY KEY:** Tüm tablolarda `_pk` suffix'li (ör. `work_order_pk`) `BIGSERIAL` primary key'ler var.
- **FOREIGN KEYS:** Veritabanı seviyesinde fiziksel `FOREIGN KEY` (REFERENCES) tanımlanmamış. Her şey text veya ID string olarak soft-reference.
- **UNIQUE Constraints:**
  - `mes.work_orders (order_id)` -> `ux_mes_work_orders_order_id`
  - `mes.operators (operator_code)` -> `ux_mes_operators_operator_code`
  - `mes.stations (station_code)` -> `ux_mes_stations_station_code`
  - `mes.error_types (error_type_code)` -> `ux_mes_error_types_error_type_code`
  - `mes.maintenance_steps (phase_code, step_code)` -> `ux_mes_maintenance_steps_phase_step`
- **Tablolar ve `external_ref`:**
  Tüm (veya çoğu) tabloda `external_ref` TEXT kolonu bulunmasına rağmen, **hiçbir log/event tablosunda (örneğin production_completions veya vision_events) `UNIQUE (external_ref)` kısıtlaması yoktur.**
- **F1F UNIQUE Adayları:**
  - `mes.production_completions` (external_ref): UNIQUE adayıdır. *Requires F1E compatibility report.*
  - `mes.vision_events` (external_ref): UNIQUE adayıdır. *Requires F1E compatibility report.*

## 7. F1E Compatibility Report Requirements
F1E (Read-Only Compatibility Report) fazında canlı DB üzerinde sadece güvenli `SELECT` sorguları çalıştırılacak ve aşağıdaki kontroller raporlanacaktır:
- `production_completions` external_ref null/blank (boş) kayıt sayısı.
- `production_completions` duplicate (tekrar eden) external_ref kayıt sayısı.
- `vision_events` external_ref null/blank kayıt sayısı.
- `vision_events` duplicate external_ref kayıt sayısı.
- `work_orders` duplicate `order_id` veya `external_ref` sayısı.
- Populated tabloların (work_orders=6, production=8, vision=43) toplam count'ları ve deferred tabloların durumları.
- F1F'de çalıştırılacak `ADD UNIQUE (external_ref)` migration'ının mevcut DB statüsüyle başarılı olup olamayacağının kesin kanıtı.

## 8. F1F Migration Preconditions
`UNIQUE(external_ref)` migration'ı çalıştırılmadan (F1F) önce uyulması gereken ön koşullar:
1. **F1E raporu temiz olmalı:** Hiçbir duplicate veya null external_ref bulunmamalı.
2. **Backup:** İşlemden önce pg_dump alınmalı.
3. **Faz İzolasyonu:** Migration, hook kodlamasından tamamen ayrı bir faz/işlem adımında (F1F) yürütülmelidir. (Hook aynı fazda olmamalı).
4. **Rollback Planı:** Başarısızlık anında eski şemaya dönüş veya temizleme senaryosu mevcut olmalıdır.
5. **Verify Scriptleri:** Migration sonrası mevcut E5F population verify scriptleri (ör. `verify_vision_events_db_mirror.py`) tekrar çalıştırılmalı ve geçmelidir.

## 9. Things Not To Do
- Bu statik inventory raporuyla hemen SQL migration yazma.
- Canlı runtime hook yazma.
- DB'ye test amacıyla read veya write query gönderme.
- `production_count` gibi olmayan MQTT topiclerini varsayma.
- `vision_track_id`'yi tek başına bir event natural key olarak kabul etme.
- Zaten çalışan verify veya mirror scriptlerini silme.
- Docker volume (`docker compose down -v`) komutuyla DB population verisini yok etme.

## 10. Next Recommended Step
- **F1E: external_ref compatibility report**
- F1E fazı, Read-Only olarak canlı veritabanı (PostgreSQL) üzerinde sorgular çalıştırılarak uyumluluk kanıtı toplanan fazdır.
- F1E'den çıkan sonuç temiz (clean) ise, F1F UNIQUE migration aşamasına güvenle geçilebilir.

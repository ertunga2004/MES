# Current State

Last updated: 2026-07-10

## Local MES Execution and Portable Runtime Baseline

This document records the current verified local MES Web / MES DB state. It is
a documentation snapshot only; it does not define a migration, compose change,
or MESQL push/pull action.

## Verified State

- Local MES DB operation lifecycle is the source-of-truth for local execution.
- Local successor activation is implemented and smoke-verified on real local
  PostgreSQL.
- Verified smoke behavior:
  - `ASSEMBLY_01` operation 10 complete.
  - `PACKAGING_01` operation 20 becomes queued.
  - Duplicate `PACKAGING_01` queue rows are not created on repeated complete.
  - Final `PACKAGING_01` operation complete marks the work order completed.
- Portable `mes_web` image build uses repo-root `mes_web/` source, not the old
  `app_source/` snapshot flow.
- `MES_CONTROL.cmd` includes diagnostic menu entries for code version, compose
  build source, active mounts, runtime roots, data folders, health, logs,
  dashboard, and Adminer.

## Applied Local Station/Location Migration

- On 2026-07-06, `db/migrations/003_add_station_locations.sql` was manually
  applied.
- `mes.locations` and `mes.station_location_bindings` were created.
- 8 locations and 8 active station-location bindings were verified.
- A second apply verified idempotency.
- No duplicate location or duplicate active binding rows were found.
- MESQL push/pull was not run.
- Runtime/API code did not change.
- The previously observed `PACKAGING_01` `station_name` encoding issue was
  cleaned up on local date 2026-07-07; see
  `docs/runbooks/station_name_encoding_cleanup_evidence_20260707.md`.

## Applied PACKAGING_01 Station Name Cleanup

- On local date 2026-07-07, the existing `PACKAGING_01` station name encoding
  issue was documented as cleaned up.
- Target row: `mes.stations` where `station_code = 'PACKAGING_01'`.
- Field changed: `station_name`.
- Previous value: `??stasyon 2 - Paketleme`.
- New value: `İstasyon 2 - Paketleme`.
- DB timestamp observed in UTC: `2026-07-06 21:29:18.233041+00`, which is
  approximately 2026-07-07 00:29 Europe/Istanbul.
- `PACKAGING_01` uniqueness was verified with `packaging_station_count = 1`.
- Target UTF-8 hex was verified as
  `c4b073746173796f6e2032202d2050616b65746c656d65`.
- Dry-run verified `candidate_count = 1` before apply.
- Related data checks after cleanup: `active_binding_count = 4`,
  `location_count = 8`.
- Health after cleanup was `ok`; code markers remained
  `has_successor_sql True`, `orders_by_sequence_operation True`,
  `skips_terminal True`.
- Evidence:
  `docs/runbooks/station_name_encoding_cleanup_evidence_20260707.md`.
- This cleanup did not change `mes.locations`,
  `mes.station_location_bindings`, work order tables, operation lifecycle,
  SQL migration files, runtime/API code, Docker/compose files, or MESQL state.

## Verified Station/Location Read Model

- Read-only helper implementation tamamlandı.
- Unit tests: `Ran 27 tests ... OK`.
- First smoke `psycopg.errors.AmbiguousParameter` ile fail oldu; optional
  `NULL` parametreler explicit cast edilerek düzeltildi.
- Final local PostgreSQL read smoke PASS.
- `all_location_count = 8`
- `active_location_count = 6`
- `PACKAGING_01 active_binding_count = 4`
- `ASSEMBLY_01 active_binding_count = 4`
- `PACKAGING_01/output_good = FINISHED_GOODS`
- `PACKAGING_01/output_scrap = SCRAP_AREA`
- `ASSEMBLY_01/output_buffer = BETWEEN_ASSEMBLY_PACKAGING`
- No DB write, no MESQL, no API/UI, no operation lifecycle mutation.
- Evidence file:
  `docs/runbooks/station_location_read_smoke_evidence_20260707.md`.

## Verified Station/Location Read-Only API

- Read-only station/location API implementation tamamlandı.
- Endpointler:
  - `GET /api/v2/locations`
  - `GET /api/v2/locations/{location_code}`
  - `GET /api/v2/stations/{station_code}/locations`
  - `GET /api/v2/stations/{station_code}/location-context`
- Feature flag: `MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED`.
- Default disabled.
- Route-level unit tests: `Ran 14 tests ... OK`.
- `mesql_v2` regression tests: `Ran 27 tests ... OK`.
- Local HTTP API read smoke PASS.
- Smoke values:
  - `locations active_only=false count = 8`
  - `locations active_only=true count = 6`
  - `PACKAGING_01 binding count = 4`
  - `ASSEMBLY_01 binding count = 4`
  - `PACKAGING_01/output_good = FINISHED_GOODS`
  - `ASSEMBLY_01/output_buffer = BETWEEN_ASSEMBLY_PACKAGING`
- Error validation verified:
  - missing location -> 404
  - invalid location type -> 400
  - invalid role -> 400
  - missing station bindings -> 200 empty list
- No DB write, no MESQL, no migration, no operation lifecycle mutation, no UI.
- Post-smoke base compose disabled behavior:
  - `GET /api/v2/locations` -> `503 STATION_LOCATION_READ_MODEL_DISABLED`
- Evidence:
  `docs/runbooks/station_location_api_smoke_evidence_20260707.md`.

## Verified Station/Location Tier 1 CI

- Tier 1 offline GitHub Actions workflow eklendi.
- Workflow file: `.github/workflows/station-location-api-tier1.yml`.
- Workflow name: `Station Location API Tier 1`.
- Latest verified commit: `329ffbe "ci: add station location api tier1 tests"`.
- Run id: `28867373267`.
- Job id: `85620827055`.
- Status: `completed`.
- Conclusion: `success`.
- Job: `Offline unit/API tests`.
- The workflow covers:
  - `tests.test_mes_web_station_location_api`
  - `tests.test_mes_web_mesql_v2`
- GitHub log download via `gh run view --log` returned `HTTP 403`; direct
  `Ran 14 tests` / `Ran 27 tests` lines were not read.
- Run/job/step metadata confirmed success, so Tier 1 CI checkpoint is PASS.
- Docker, PostgreSQL, HTTP smoke, migration, MESQL, and operation lifecycle
  real DB smoke are not part of Tier 1.
- Evidence:
  `docs/runbooks/station_location_api_tier1_ci_evidence_20260707.md`.

## Verified Station/Location Kiosk Read-Only UI

- Kiosk station/location read-only bilgi kartı implementation tamamlandı.
- Değişen dosyalar:
  - `mes_web/static/kiosk.html`
  - `mes_web/static/kiosk.js`
  - `mes_web/static/kiosk.css`
- Kart endpointi:
  - `GET /api/v2/stations/{station_code}/location-context`
- Kart gösterimi:
  - Giriş Lokasyonu
  - Aktif WIP Lokasyonu
  - Sağlam Çıkış Lokasyonu
  - Fire/Hurda Çıkış Lokasyonu
  - Ara Buffer Lokasyonu
- Regression/static:
  - `tests.test_mes_web_station_location_api`: `Ran 14 tests ... OK`
  - `tests.test_mes_web_mesql_v2`: `Ran 27 tests ... OK`
  - `node --check mes_web\static\kiosk.js`: PASS
- Kiosk HTTP/static smoke PASS:
  - `/kiosk -> 200`
  - `/static/kiosk.html -> 200`
  - `/kiosk/station/PACKAGING_01 -> 200`
  - `/kiosk/PACKAGING_01 -> 200`
  - `/static/kiosk.js -> 200`
  - `/static/kiosk.css -> 200`
- Kart markers verified:
  - `stationLocationCard`
  - `İstasyon Lokasyon Bilgisi`
- API context values verified:
  - `PACKAGING_01/output_good = FINISHED_GOODS`
  - `PACKAGING_01/output_scrap = SCRAP_AREA`
  - `ASSEMBLY_01/output_buffer = BETWEEN_ASSEMBLY_PACKAGING`
- No DB write, no MESQL, no migration, no operation lifecycle mutation.
- Start/complete and queue behavior were not changed.
- Real browser visual check was not performed because existing Kiosk init may
  trigger runtime POST calls.
- Result: PASS with manual visual check pending.
- Evidence:
  `docs/runbooks/station_location_kiosk_ui_smoke_evidence_20260707.md`.
- Controlled manual visual check PASS.
- `PACKAGING_01` kartı gerçek browser'da doğrulandı.
- `ASSEMBLY_01` kartı gerçek browser'da doğrulandı.
- Console error yok.
- Yatay taşma yok.
- Disabled behavior doğrulandı:
  - Feature flag reset sonrası `503`.
  - Kiosk kırılmadı.
- Existing kiosk init POST görüldü:
  - `POST /api/modules/konveyor_main/kiosk/register`
  - Mevcut Kiosk init davranışı olarak kabul edildi.
- Start/complete, queue mutation, MESQL ve operation lifecycle çağrısı
  yapılmadı.
- Manual visual evidence:
  `docs/runbooks/station_location_kiosk_manual_visual_evidence_20260707.md`.

## Verified SQL-Driven Station Execution Documentation Phase

- SQL-driven station execution documentation phase tamamlandı.
- Bu faz implementation değildir; dokümantasyon ve karar checkpoint fazıdır.
- Oluşturulan/güncellenen tasarım dokümanları:
  - `docs/architecture/station_execution_model_design.md`
  - `docs/architecture/station_execution_schema_plan.md`
  - `docs/architecture/station_execution_schema_review_checkpoint.md`
  - `docs/architecture/station_execution_migration_plan.md`
  - `docs/architecture/station_execution_seed_setup_plan.md`
  - `docs/architecture/station_execution_runtime_engine_design.md`
  - `docs/architecture/kiosk_dynamic_action_design.md`
  - `docs/architecture/iot_event_adapter_design.md`
  - `docs/architecture/oee_kpi_v0_design.md`
- Schema review sonucu:
  - `Schema design: READY_FOR_MIGRATION_PLAN`
  - `Migration SQL: NOT_STARTED`
  - `Seed SQL: NOT_STARTED`
  - `Runtime implementation: NOT_STARTED`
  - `Kiosk dynamic action implementation: NOT_STARTED`
  - `IoT adapter implementation: NOT_STARTED`
  - `OEE/KPI implementation: NOT_STARTED`
- Sabitlenen ana kararlar:
  - `start_mode` ve `finish_mode` ayrı fiziksel alanlar olacaktır.
  - `control_policy` engine için zorunlu ana alan olmayacaktır.
  - `operation_steps`, `route_operation_id` üzerinden `route_operations`
    satırına bağlanacaktır.
  - Event source station-scoped kabul edilmiştir.
  - Yeni execution state için `mes.work_order_operation_execution_state`
    sidecar tablosu tercih edilmiştir.
  - Mevcut `work_order_operations.status` ilk fazda bozulmayacaktır.
  - `operation_events` append-only audit ledger olarak tasarlanmıştır.
  - `production_flow_events` inventory movement değildir.
  - Inventory movement/balance ayrı gelecek fazdır.
  - MESQL entegrasyonu bu fazda frozen kalmıştır.
- Bu fazda yapılmayanlar:
  - Kod değişikliği yok.
  - SQL migration yok.
  - DB apply yok.
  - Docker/psql yok.
  - Kiosk implementation yok.
  - Runtime engine implementation yok.
  - IoT adapter implementation yok.
  - OEE/KPI implementation yok.
  - Inventory movement/balance yok.
  - MESQL push/pull yok.
- Sonraki teknik eşik:
  - `004_station_execution_schema.sql` migration taslağı hazırlanabilir.
  - Migration taslağı önce review edilecek; doğrudan DB'ye uygulanmayacaktır.

## Verified Station Execution Schema Migration Draft

- `db/migrations/004_station_execution_schema.sql` migration taslağı
  oluşturuldu.
- Migration taslağı statik review'dan PASS aldı.
- Migration henüz DB'ye uygulanmadı.
- `docs/runbooks/station_execution_schema_migration_apply_runbook.md`
  oluşturuldu.
- Apply runbook backup, destructive keyword kontrolü, migration apply komutu,
  schema/table/index/constraint verify sorguları, no-seed/no-data-mutation
  kontrolü, location FK yokluğu kontrolü, health/regression planı, rollback
  stratejisi ve PASS/FAIL kriterlerini içerir.
- Migration taslağı 10 hedef tabloyu additive olarak oluşturacak şekilde
  hazırlanmıştır:
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
- Review sonrası giderilen kritik risk:
  - `production_flow_events.input_location_code` ve
    `production_flow_events.output_location_code` alanları semantic reference
    olarak bırakılmıştır.
  - Bu alanlar `mes.locations(location_code)` alanına DB-level FK ile
    bağlanmamıştır.
  - Gerekçe: mevcut local baselinelarda `locations.location_code` için full
    unique constraint garanti edilmediğinden, location code geçerliliği
    setup/runtime validation ile ele alınacaktır.
- Korunan ana kararlar:
  - Migration additive kalır.
  - Seed içermez.
  - Data migration içermez.
  - Existing lifecycle mutation içermez.
  - `work_order_operations.status` değiştirilmez.
  - `station_queue` değiştirilmez.
  - `mes.locations` ve `mes.station_location_bindings` değiştirilmez.
  - Inventory movement/balance oluşturulmaz.
  - MESQL sync/push/pull yapılmaz.
- `operation_events` için station-scoped idempotency korunmuştur:
  - `(station_code, event_source, external_event_id)` partial unique index.
  - `idempotency_key` partial unique index.
- Durum:
  - `Schema migration draft: READY_FOR_APPLY_RUNBOOK_REVIEW`
  - `Apply runbook: READY`
  - `Migration apply: NOT_STARTED`
  - `Seed SQL: NOT_STARTED`
  - `Runtime implementation: NOT_STARTED`
  - `Kiosk dynamic action implementation: NOT_STARTED`
  - `IoT adapter implementation: NOT_STARTED`
  - `OEE/KPI implementation: NOT_STARTED`
- Sonraki teknik eşik:
  - Açık kullanıcı onayı ile apply runbook takip edilerek backup alınacak.
  - Sonra `004_station_execution_schema.sql` local PostgreSQL'e uygulanacak.
  - Apply sonrası evidence dosyası önerisi:
    `docs/runbooks/station_execution_schema_migration_evidence_YYYYMMDD.md`

## Applied Station Execution Schema Migration

- `db/migrations/004_station_execution_schema.sql` local PostgreSQL üzerinde
  kontrollü şekilde uygulandı.
- Apply öncesi backup alındı:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_postgres_before_004_station_execution_schema_20260709-111429.sql`
- Evidence:
  `docs/runbooks/station_execution_schema_migration_evidence_20260709.md`
- Apply sonrası doğrulanan yeni tablolar:
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
- `operation_events` station-scoped idempotency indexleri doğrulandı.
- `production_flow_events` üzerinde `mes.locations(location_code)` FK olmadığı
  doğrulandı.
- Yeni tabloların seed/data içermediği doğrulandı.
- Station/location baseline korundu:
  - `locations = 8`
  - `active_station_location_bindings = 8`
- Health / limited regression kontrolü tamamlandı.
- Bu apply sırasında yapılmayanlar:
  - Seed SQL apply yok.
  - Runtime engine implementation yok.
  - Kiosk dynamic action implementation yok.
  - IoT adapter implementation yok.
  - OEE/KPI implementation yok.
  - Inventory movement/balance yok.
  - MESQL push/pull yok.
  - Operation lifecycle mutation yok.

## Applied Station Execution Minimal Seed

- `db/migrations/005_station_execution_seed_minimal.sql` local PostgreSQL
  uzerinde kontrollu sekilde uygulandi.
- Apply oncesi backup alindi:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_postgres_before_005_station_execution_seed_minimal_20260709-115906.sql`
- Evidence:
  `docs/runbooks/station_execution_seed_minimal_evidence_20260709.md`
- Seeded scope:
  - Items:
    - `RAW_BOX`
    - `COLOR_CLASSIFIED_BOX`
    - `PACKAGED_PRODUCT`
  - Process route:
    - `ROUTE_BOX_PACKAGING_V1`, version `1`
  - Route operations:
    - `OP10_ASSEMBLY_CLASSIFICATION` on `ASSEMBLY_01`
    - `OP20_PACKAGING` on `PACKAGING_01`
  - Station event sources: `4`
  - Operation steps:
    - `3` assembly/classification steps
    - `2` packaging steps
- Expected counts verified:
  - `items = 3`
  - `process_routes = 1`
  - `route_operations = 2`
  - `station_event_sources = 4`
  - `operation_steps = 5`
- Runtime/event/flow tables remained empty:
  - `work_order_operation_execution_state = 0`
  - `work_order_operation_steps = 0`
  - `operation_events = 0`
  - `operation_approvals = 0`
  - `production_flow_events = 0`
- Station/location baseline retained:
  - `locations = 8`
  - `active_station_location_bindings = 8`
- Health / limited regression control tamamlandi:
  - `GET /health -> ok`
  - `GET /api/v2/locations -> 503`
  - `GET /kiosk -> 200`
  - `GET /static/kiosk.js -> 200`
  - `GET /static/kiosk.css -> 200`
- Bu apply sirasinda yapilmayanlar:
  - Runtime engine implementation yok.
  - Kiosk dynamic action implementation yok.
  - IoT adapter implementation yok.
  - OEE/KPI implementation yok.
  - Inventory movement/balance yok.
  - MESQL push/pull yok.
  - Operation lifecycle mutation yok.
  - Work order create/change yok.

## Verified Station Execution Config Read Model

- Station execution config read-only helper implementation tamamlandi.
- Degisen dosyalar:
  - `mes_web/db/mesql_v2.py`
  - `tests/test_mes_web_mesql_v2.py`
- Offline unit regression:
  - `tests.test_mes_web_mesql_v2`: `Ran 41 tests ... OK`
- Real local PostgreSQL read smoke PASS.
- Verified helper coverage:
  - `list_items`
  - `get_item_by_code`
  - `list_process_routes`
  - `get_process_route`
  - `list_route_operations`
  - `get_route_operation`
  - `list_station_event_sources`
  - `resolve_station_event_source`
  - `list_operation_steps`
  - `get_operation_step`
  - `get_route_operation_config`
  - `get_station_execution_config`
- Verified seeded config:
  - `items = 3` seed scope
  - `ROUTE_BOX_PACKAGING_V1`, version `1`
  - `ASSEMBLY_01` route operation count = `1`
  - `PACKAGING_01` route operation count = `1`
  - `ASSEMBLY_01` event source count = `3`
  - `PACKAGING_01` event source count = `1`
  - `OP10` step count = `3`
  - `OP20` step count = `2`
- Aggregate validation returned no critical warnings for seeded OP10/OP20
  config.
- No-write baseline retained:
  - runtime/event/flow tables remained `0`
  - `locations = 8`
  - `active_station_location_bindings = 8`
- Health / limited regression control tamamlandi:
  - `GET /health -> ok`
  - `GET /api/v2/locations -> 503`
  - `GET /kiosk -> 200`
  - `GET /static/kiosk.js -> 200`
  - `GET /static/kiosk.css -> 200`
- Evidence:
  `docs/runbooks/station_execution_config_read_smoke_evidence_20260709.md`
- Bu fazda yapilmayanlar:
  - API route implementation yok.
  - Kiosk dynamic action implementation yok.
  - Runtime engine implementation yok.
  - IoT adapter implementation yok.
  - OEE/KPI implementation yok.
  - Inventory movement/balance yok.
  - MESQL push/pull yok.
  - Operation lifecycle mutation yok.
  - Work order create/change yok.

## Verified Station Execution Config Read-Only API

- Station execution config read-only API implementation tamamlandi.
- Implementation commit:
  `116ef77 "feat: add station execution config read api"`
- Degisen dosyalar:
  - `mes_web/__main__.py`
  - `tests/test_mes_web_station_execution_config_api.py`
- Feature flag:
  - `MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED`
  - Default disabled.
- New read-only GET endpoints:
  - `GET /api/v2/station-execution/items`
  - `GET /api/v2/station-execution/items/{item_code}`
  - `GET /api/v2/station-execution/routes`
  - `GET /api/v2/station-execution/routes/{route_code}`
  - `GET /api/v2/station-execution/route-operations`
  - `GET /api/v2/station-execution/route-operations/{route_operation_id}`
  - `GET /api/v2/stations/{station_code}/execution-event-sources`
  - `GET /api/v2/stations/{station_code}/execution-config`
  - `GET /api/v2/station-execution/route-operations/{route_operation_id}/steps`
  - `GET /api/v2/station-execution/route-operations/{route_operation_id}/config`
- Route-level/unit regression:
  - `tests.test_mes_web_station_execution_config_api`
  - `tests.test_mes_web_station_location_api`
  - `tests.test_mes_web_mesql_v2`
  - `Ran 77 tests ... OK`
- Local HTTP smoke PASS after corrected DB password source.
- Prior failed enabled smoke root cause:
  - temporary smoke container used wrong DB password.
  - diagnosis:
    `docs/runbooks/station_execution_config_read_api_500_diagnosis_20260709.md`
- Verified disabled behavior:
  - `GET /api/v2/station-execution/items -> 503`
- Verified enabled seeded config reads:
  - `items = 3`
  - `routes includes ROUTE_BOX_PACKAGING_V1`
  - `ASSEMBLY_01 route operation count = 1`
  - `PACKAGING_01 route operation count = 1`
  - `ASSEMBLY_01 event source count = 3`
  - `PACKAGING_01 event source count = 1`
  - `OP10 step count = 3`
  - `OP20 step count = 2`
  - `ASSEMBLY_01 execution config route_operations count = 1`
  - `PACKAGING_01 execution config route_operations count = 1`
- Error behavior smoke PASS:
  - invalid `active_only` -> `400 INVALID_QUERY_PARAM`
  - invalid `version` -> `400 INVALID_QUERY_PARAM`
  - missing item -> `404 ITEM_NOT_FOUND`
  - missing route operation -> `404 ROUTE_OPERATION_NOT_FOUND`
- No-write baseline retained:
  - runtime/event/flow tables remained `0`
  - `locations = 8`
  - `active_station_location_bindings = 8`
- Existing station/location API default-disabled behavior retained:
  - `GET /api/v2/locations -> 503`
- Kiosk static GET regression retained:
  - `GET /kiosk -> 200`
  - `GET /static/kiosk.js -> 200`
  - `GET /static/kiosk.css -> 200`
- Evidence:
  `docs/runbooks/station_execution_config_read_api_smoke_evidence_20260709.md`
- Bu fazda yapilmayanlar:
  - Kiosk dynamic action implementation yok.
  - Runtime engine implementation yok.
  - IoT adapter implementation yok.
  - OEE/KPI implementation yok.
  - Inventory movement/balance yok.
  - MESQL push/pull yok.
  - Operation lifecycle mutation yok.
  - Work order create/change yok.
  - Queue mutation yok.

## Verified Station Execution Config API Feature Flag Wiring

- Portable compose pass-through verified.
- `MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED=true` enabled normal
  `mes_web:8080` read-only API access.
- Removing the host env and recreating `mes_web` restored default disabled
  behavior.
- Verified values:
  - `items count = 3`
  - `ASSEMBLY_01 route operation count = 1`
  - `ASSEMBLY_01 execution config route_operations count = 1`
  - disabled restore: `503 STATION_EXECUTION_CONFIG_READ_MODEL_DISABLED`
  - Kiosk static GET: `/kiosk`, `/static/kiosk.js`, `/static/kiosk.css` -> `200`
- Evidence:
  `docs/runbooks/station_execution_config_read_api_feature_flag_wiring_smoke_20260709.md`
- No DB write, lifecycle mutation, MESQL, Kiosk action, seed, migration, or
  volume operation was performed.

## Verified Station Execution Runtime Init Helper

- Runtime Engine V0 Phase 1 initialize helper real DB smoke PASS.
- Implementation commit:
  `80ac95a "feat: add station execution runtime init helpers"`
- Verified helpers:
  - `initialize_execution_state`
  - `get_execution_state`
  - `list_execution_steps`
- Selected existing operation:
  `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`
  (`WO-E2E-MAVI-001`, `ASSEMBLY_01`, status `queued`).
- Route operation used:
  `ROUTE_BOX_PACKAGING_V1_OP10`.
- Real DB initialize result:
  - `execution_state_count = 1`
  - `execution_status = ready`
  - OP10 runtime step count = `3`
  - all runtime steps remained `pending`
- Idempotency PASS:
  - first call returned `initialized = true`
  - second call returned `initialized = false`
  - duplicate state/step rows were not created
- Forbidden mutation verification PASS:
  - `operation_events = 0`
  - `operation_approvals = 0`
  - `production_flow_events = 0`
  - `work_orders` unchanged
  - `work_order_operations` unchanged
  - `station_queue` unchanged
- Existing lifecycle remained untouched; no start/finish, approval, API, Kiosk,
  IoT, OEE, MESQL, seed, or migration action was performed.
- Evidence:
  `docs/runbooks/station_execution_runtime_init_smoke_evidence_20260709.md`

## Verified Station Execution Event Ledger Helper

- Runtime Engine V0 Phase 2A operation event ledger helper real DB smoke PASS.
- Implementation commit:
  `3072de2 "feat: add station execution event ledger helpers"`
- Verified helpers:
  - `record_operation_event`
  - `get_operation_event_by_idempotency_key`
  - `get_operation_event_by_external_event`
- Smoke target:
  - `work_order_operation_id = c8f0be13-9dc7-4e66-9fbb-43547a5f1808`
  - `station_code = ASSEMBLY_01`
  - `event_source = COLOR_SENSOR_ENTRY`
  - `event_type = evidence`
  - `external_event_id = event-ledger-smoke-20260709-001`
- Event ledger result:
  - first call returned `inserted = true`
  - second call returned `inserted = false`
  - `event_count = 1`
  - idempotency key:
    `ASSEMBLY_01:COLOR_SENSOR_ENTRY:event-ledger-smoke-20260709-001`
- Forbidden mutation verification PASS:
  - only `operation_events` changed, `0 -> 1`
  - `work_order_operation_execution_state` unchanged
  - `work_order_operation_steps` unchanged
  - `operation_approvals` unchanged
  - `production_flow_events` unchanged
  - `work_orders` unchanged
  - `work_order_operations` unchanged
  - `station_queue` unchanged
- No step state mutation, execution state update, approval, production flow,
  API, Kiosk, IoT, OEE, MESQL, seed, or migration action was performed.
- Evidence:
  `docs/runbooks/station_execution_event_ledger_smoke_evidence_20260709.md`

## Verified Station Execution Step Start Helper

- Runtime Engine V0 Phase 2B real DB smoke PASS.
- Implementation commit:
  `1f9d3ee feat: add station execution step start helper`.
- Helper: `start_execution_step`.
- Smoke target:
  - `work_order_operation_id = c8f0be13-9dc7-4e66-9fbb-43547a5f1808`
  - `station_code = ASSEMBLY_01`
  - `step_code = COLOR_SENSOR_ENTRY_EVIDENCE`
  - `event_source = COLOR_SENSOR_ENTRY`
  - `external_event_id = step-start-smoke-20260710-001`
- Verified transition: `ready + pending -> active + active`.
- First call returned `started = true` and `event_inserted = true`.
- Duplicate replay returned `started = false` and `event_inserted = false`.
- The smoke external event count is `1`; timestamps and first-event references
  were preserved during replay.
- Only `operation_events`, the target execution state, and the target runtime
  step changed. Work orders, operations, queue, approvals, flow,
  config/master/location data, and bindings did not change.
- Evidence:
  `docs/runbooks/station_execution_step_start_smoke_evidence_20260710.md`.
- No API, Kiosk, IoT, OEE, MESQL, migration, or seed action was performed.

## Verified Station Execution Step Finish Helper

- Runtime Engine V0 Phase 2C real DB smoke PASS.
- Implementation commit:
  `551023e feat: add station execution step finish helper`.
- Helper: `finish_execution_step`.
- Smoke target: `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`,
  `COLOR_SENSOR_ENTRY_EVIDENCE`, `COLOR_SENSOR_ENTRY`, and
  `step-finish-smoke-20260710-001`.
- Verified transition: `active -> completed`.
- First call returned `finished = true`, `event_inserted = true`, and
  `implicit_started = false`; duplicate returned `finished = false` and
  `event_inserted = false`.
- The target start timestamp/reference were preserved. Completion timestamp and
  reference were written from the finish event.
- Execution remained `active`; `current_step_code` advanced to
  `ROBOT_ARM_DROP_COMPLETED`, whose runtime row remained `pending`.
- Completion policy, approval, production flow, lifecycle, config/master,
  location, and binding mutations were not performed.
- Evidence:
  `docs/runbooks/station_execution_step_finish_smoke_evidence_20260710.md`.
- No API, Kiosk, IoT, OEE, MESQL, migration, or seed action was performed.

## Verified Robot Implicit-Start Auto-Finish Transition

- Runtime Engine V0 Phase 2D real DB smoke PASS.
- Helper implementation commit: `551023e`.
- Phase 2C documentation commit: `e417262`.
- Target operation: `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`.
- Target/source/external event: `ROBOT_ARM_DROP_COMPLETED`, `ROBOT_ARM_DROP`,
  and `robot-implicit-finish-smoke-20260710-001`.
- Verified transition:
  `pending + implicit_start + auto_finish -> completed`.
- First call returned `finished = true`, `event_inserted = true`, and
  `implicit_started = true`.
- The same event produced equal start/completion timestamps and equal
  start/completion event references.
- Duplicate replay returned `finished = false` and `event_inserted = false`
  without mutation.
- Execution remained `active`; `current_step_code` advanced to
  `OPERATOR_OBSERVATION_APPROVAL`, whose runtime row remained `pending`.
- Completion policy, approval, production flow, lifecycle, config/master,
  location, and binding mutations were not performed.
- Evidence:
  `docs/runbooks/station_execution_robot_implicit_finish_smoke_evidence_20260710.md`.
- No API, Kiosk, IoT adapter, OEE, MESQL, migration, or seed action was
  performed.

## Portable Path Model

```text
Repo root:
C:\Users\ertun\Documents\.CODE\codex\MES

Docker control root:
C:\Users\ertun\Documents\.CODE\codex\MES\docker\mes

Portable runtime/data root:
C:\Users\ertun\Documents\.CODE\.DOCKER\MES

Runtime data:
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\logs
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\work_orders
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups
```

`mes_postgres` stores PostgreSQL data in the named Docker volume
`mes_postgres_data`; do not remove this volume during normal operations.

## Operational Notes

- `.env` can contain the real local PostgreSQL password and must not be
  committed.
- `.env.example` must contain example values only.
- MESQL integration is currently frozen unless explicitly requested.
- Do not run MESQL push/pull without explicit approval.
- Do not use `docker compose down -v` or `docker volume rm` without explicit
  destructive-operation approval.

## Change Guardrail

For this checkpoint, no Python runtime code, database migration, Dockerfile,
Compose, or container configuration change is required.

For the SQL-driven station execution documentation checkpoint, no Python runtime
code, SQL migration, database apply, Docker/Compose configuration, Kiosk
implementation, operation lifecycle mutation, inventory movement/balance
implementation, or MESQL push/pull action was performed.

For the station execution schema migration draft checkpoint,
`004_station_execution_schema.sql` and its apply runbook were documented as
ready for controlled future application, but no database apply, psql command,
Docker/Compose operation, seed insert, runtime implementation, Kiosk dynamic
action, IoT adapter, OEE/KPI implementation, inventory movement/balance
implementation, or MESQL push/pull action was performed.

For the applied station execution schema migration checkpoint,
`004_station_execution_schema.sql` was applied after backup and verification; no
seed insert, runtime implementation, Kiosk dynamic action, IoT adapter, OEE/KPI
implementation, inventory movement/balance implementation, MESQL push/pull, or
operation lifecycle mutation was performed.

For the applied station execution minimal seed checkpoint,
`005_station_execution_seed_minimal.sql` was applied after backup and
verification; only station execution master/config tables were seeded, and no
runtime/event/flow data, work order data, operation lifecycle mutation, Kiosk
dynamic action, runtime engine, IoT adapter, OEE/KPI implementation, inventory
movement/balance implementation, or MESQL push/pull action was performed.

For the verified station execution config read-only API checkpoint, read-only
GET endpoints, route-level tests, corrected local HTTP smoke, and no-write
baseline verification were completed; no Kiosk dynamic action, runtime engine,
IoT adapter, OEE/KPI implementation, inventory movement/balance implementation,
MESQL push/pull, work order mutation, queue mutation, or operation lifecycle
mutation was performed.

For the verified station execution config read model checkpoint, read-only
helper functions and offline tests were added and real local PostgreSQL read
smoke was completed; no API route, Kiosk dynamic action, runtime engine, IoT
adapter, OEE/KPI implementation, inventory movement/balance implementation,
MESQL push/pull, work order mutation, queue mutation, or operation lifecycle
mutation was performed.

## Accepted Observation / Quality-Control Boundary

- Process-end observation is a normal operation step that can be added,
  removed, reordered, timed, or made optional through SQL/config.
- The target canonical step code is `PROCESS_END_OBSERVATION`; the recommended
  prototype uses `manual_start + manual_finish`, records duration, is required
  for completion, and does not embed approval after finish.
- Quality control is an optional separate route operation and station model
  with its own queue, execution state, and operation steps.
- Final approval is a separate audit/completion-policy concern represented by
  `mes.operation_approvals` and `operation_completion_policy`.
- `OPERATOR_OBSERVATION_APPROVAL` remains the legacy/current V1 identifier.
- The retained pending runtime instance and all historical evidence remain
  unchanged; an in-place rename was rejected.
- A new versioned route/configuration is recommended for future work-order
  operation instances.
- Decision: `docs/architecture/observation_quality_control_boundary_decision.md`.
- Transition plan:
  `docs/architecture/observation_quality_control_transition_plan.md`.
- This checkpoint changes no Python, test, migration, seed, database state,
  Kiosk, API, IoT, OEE, approval/completion implementation, lifecycle,
  inventory, MESQL, or FERP behavior.

## Verified Station Execution Completion Policies

- Runtime Engine V0 Phase 3B isolated PostgreSQL smoke PASS.
- Implementation commit:
  `e4be6ac feat: apply station execution completion policies`.
- Source database `mes` remained unchanged across all 15 baseline/final table
  count and digest comparisons.
- Verification used one logical source dump restored into three disposable
  clone databases; source `mes` was never used as a template or smoke target.
- Verified policy transitions:
  - `manual_close -> evidence_completed`
  - `auto_close_on_required_steps -> closed`
  - `auto_complete_pending_approval -> pending_final_approval`
- Event insert, target-step completion, required-step evaluation, policy
  transition, and execution-state update were atomic with the triggering
  `step_finish` event.
- Duplicate external-event replay produced no event, step, execution-state, or
  policy mutation.
- No additional `system_transition` event, approval row, or production-flow row
  was created.
- Work-order, work-order-operation, station-queue, config/master, location, and
  binding lifecycle tables remained digest-identical in every clone.
- Retained V1 source runtime remained `active`, with
  `current_step_code=OPERATOR_OBSERVATION_APPROVAL` and the final step
  `pending`; its target event count remained `4`.
- All three task-created clone databases were dropped and their absence was
  verified; the host backup was retained.
- Evidence:
  `docs/runbooks/station_execution_completion_policy_isolated_smoke_evidence_20260710.md`.
- No migration, seed, API, Kiosk, IoT/MQTT, Observer, OEE/KPI, approval helper,
  manual-close helper, production flow, inventory, work-order close, MESQL, or
  FERP action was performed.

## Canonical V2 Route Seed Draft

- An additive Canonical V2 route/config seed draft is ready for review.
- SQL draft:
  `db/migrations/006_station_execution_seed_canonical_v2.sql`.
- Apply runbook:
  `docs/runbooks/station_execution_canonical_v2_seed_apply_runbook.md`.
- Target identity:
  `ROUTE_BOX_PACKAGING_V2`, version `2`.
- Route operations:
  - `ROUTE_BOX_PACKAGING_V2_OP10` / `ASSEMBLY_COLOR_CLASSIFY`
  - `ROUTE_BOX_PACKAGING_V2_OP20` / `PACKAGING_FINAL`
- OP10 uses the canonical `PROCESS_END_OBSERVATION` step with manual start,
  manual finish, duration recording, required completion, and no embedded
  approval.
- OP20 uses one measurable manual `PACKAGING_EXECUTION` step with no embedded
  approval.
- Both route operations use `auto_close_on_required_steps`.
- The V2 draft contains no final-approval step and no quality-control route
  operation.
- V2 route/config rows are drafted as `active=true`: current route detail and
  runtime initialization paths require explicit route/version or
  route-operation identifiers, and no automatic latest-active work-order
  selection was found.
- New work-order selection/activation implementation remains a separate phase.
- V1 config, retained runtime, and historical evidence were not changed.
- The V2 SQL has not been applied to a database.
- Repository artifact status is `reviewed seed draft, not applied to source
  DB`; inserted rows, when applied in a future approved task, use
  `configuration_status=canonical_v2` metadata.
- No Python, test, API, Kiosk, IoT/MQTT, Observer, OEE/KPI, approval helper,
  manual-close helper, production flow, inventory, lifecycle, work-order close,
  MESQL, or FERP change was made.

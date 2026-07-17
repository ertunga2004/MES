# Current State

Last updated: 2026-07-17

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
- OP10 uses `output_buffer` and `scrap_location_role=null`.
- OP20 retains `output_scrap`.
- Scrap binding validation is conditional on a configured non-null scrap role.
- The V2 draft contains no final-approval step and no quality-control route
  operation.
- V2 route/config rows are drafted as `active=true`: current route detail and
  runtime initialization paths require explicit route/version or
  route-operation identifiers, and no automatic latest-active work-order
  selection was found.
- New work-order selection/activation implementation remains a separate phase.
- V1 config, retained runtime, and historical evidence were not changed.
- The V2 SQL has not been applied to source `mes`; apply and idempotency were
  verified only on a disposable logical dump/restore clone.
- Repository artifact status is `reviewed seed draft, not applied to source
  DB`; inserted rows, when applied in a future approved task, use
  `configuration_status=canonical_v2` metadata.
- No Python, test, API, Kiosk, IoT/MQTT, Observer, OEE/KPI, approval helper,
  manual-close helper, production flow, inventory, lifecycle, work-order close,
  MESQL, or FERP change was made.

## Canonical V2 Runtime Binding Blocker

- Optional scrap-role correction: PASS.
- Canonical V2 isolated first apply: PASS with 1 route, 2 operations, 4 steps,
  and 5/5 configured location roles.
- Canonical V2 idempotency reapply: PASS with no new rows or digest changes.
- V1/V2 config read-model coexistence: PASS without identifier collision or
  critical warning.
- Runtime initialization: `BLOCKED`.
- Eligible lifecycle candidate count: `0` for
  `ASSEMBLY_01 / ASSEMBLY_COLOR_CLASSIFY`.
- Existing lifecycle operation codes include `OP-ASSEMBLY` and `OP-MVP-ASM`;
  they are not an explicit Canonical V2 route-operation binding.
- No fixture, station/operation-code/sequence inference, operation-code
  mutation, or retained V1 target reuse was performed.
- Runtime initialization and step start/finish helpers were not called.
- Source `mes` remained unchanged across 15/15 final count and digest checks;
  its Canonical V2 route count remained zero.
- Blocker evidence:
  `docs/runbooks/station_execution_canonical_v2_isolated_apply_runtime_init_retry_evidence_20260710.md`.
- Evidence commit:
  `fcb7083 docs: record canonical v2 runtime binding blocker`.
- An explicit immutable `work_order_operation_id -> route_operation_id`
  sidecar binding is accepted for implementation planning.
- Architecture decision:
  `docs/architecture/work_order_route_operation_binding_decision.md`.
- Implementation plan:
  `docs/architecture/work_order_route_operation_binding_implementation_plan.md`.
- This checkpoint is not verified runtime initialization and is not an
  implementation checkpoint.
- No schema, migration, seed, Python, test, database, lifecycle, queue, runtime,
  API/Kiosk/IoT/OEE, approval, production-flow, inventory, MESQL, or FERP
  mutation was performed.

## Work-Order Route-Operation Binding Schema Draft

- Phase 4B architecture commit:
  `1d48613 docs: define work-order route-operation binding`.
- Accepted identity contract:
  explicit immutable `work_order_operation_id -> route_operation_id` binding.
- Selected sidecar table:
  `mes.work_order_operation_route_bindings`.
- Cardinality invariant: one lifecycle operation instance has at most one
  route-operation binding; one route operation may bind many lifecycle
  instances.
- The binding preserves the selected stable route-operation and route-version
  identity for the lifecycle operation's history.
- Accepted Phase 4C binding sources:
  - `manual_setup`
  - `work_order_release`
- Automatic legacy backfill is not included. Existing unsupported records
  remain `unbound legacy`; station, operation-code, sequence, combined-field,
  and latest-active inference remain rejected.
- The MVP is insert-only. It has no active flag, update/delete path, rebind,
  effective-date, soft-delete, or supersession model.
- Migration draft:
  `db/migrations/009_work_order_operation_route_binding.sql`.
- Schema plan:
  `docs/architecture/work_order_route_operation_binding_schema_plan.md`.
- Future apply runbook:
  `docs/runbooks/work_order_route_operation_binding_migration_apply_runbook.md`.
- The migration has not been applied. The binding table has not been created
  in the source database and no binding row exists as a result of this phase.
- No Python, test, helper, runtime-init, work-order release, lifecycle, runtime,
  queue, config, API/Kiosk/IoT/OEE, approval, production-flow, inventory,
  MESQL, or FERP change was made.
- Next phase: controlled migration review and disposable-clone apply.

## Verified Work-Order Route-Operation Binding Schema Migration

- Phase 4C artifact commit:
  `5c57f70 feat: add work-order route-operation binding schema`.
- Migration:
  `db/migrations/009_work_order_operation_route_binding.sql`.
- The migration was not applied to source `mes`.
- First apply on disposable primary clone: PASS.
- Idempotency reapply: PASS; table OID and exact schema digests were preserved.
- Negative malformed-schema rejection: PASS; the malformed table was not
  silently accepted or repaired, and the explicit nine-column assertion was
  observed.
- Verified table: `mes.work_order_operation_route_bindings`.
- Verified column / constraint / index counts: `9 / 9 / 4`.
- Binding-table row count after first apply and reapply: `0`.
- Existing-table no-write verification: `15/15` count and digest PASS after
  first apply and reapply.
- No lifecycle, config, runtime, event, approval, production-flow, queue,
  location, or binding row mutation occurred.
- Source `mes` binding table remained absent; its final 15/15 counts and
  digests matched the pre-smoke baseline.
- Retained V1 remained `active` at
  `OPERATOR_OBSERVATION_APPROVAL`, with final step `pending` and event /
  approval / production-flow counts `4 / 0 / 0`.
- Primary and negative disposable clones were dropped and their absence was
  verified.
- Evidence:
  `docs/runbooks/work_order_route_operation_binding_migration_isolated_smoke_evidence_20260714.md`.
- No Python, test, helper, runtime-init, work-order release, API/Kiosk/IoT/OEE,
  MESQL, or FERP implementation was changed.

## Verified Work-Order Route-Operation Binding Read Helpers

- Last updated: `2026-07-14`.
- Implementation commit:
  `6e7a880 feat: add work-order route-operation binding read helpers`.
- Verified helpers:
  - `get_work_order_operation_route_binding`
  - `get_work_order_operation_route_binding_by_id`
- Unit regression: targeted `106` tests and combined `142` tests, both `OK`.
- Source `mes` binding table remained absent.
- Before clone migration, the real lifecycle-operation helper propagated
  PostgreSQL `UndefinedTable` (`42P01`) without converting it to `None`.
- Migration `009_work_order_operation_route_binding.sql` was applied only to
  disposable clone `mes_binding_read_smoke_20260714_133559`.
- One clone-only binding fixture was created for read-helper verification; it
  is not accepted as a production semantic mapping.
- Lifecycle-operation lookup and exact binding-ID lookup: `PASS`.
- Missing lifecycle UUID, missing binding ID, and case-mismatched binding ID
  returned `None`; exact binding-ID case was preserved.
- Repeated reads preserved all result values and timestamps and produced no
  mutation.
- Binding count/digest and all existing 15 table counts/digests remained equal
  across helper calls.
- Source `mes` final 15/15 counts/digests matched baseline, retained V1 state
  was unchanged, and the disposable clone was dropped.
- Evidence:
  `docs/runbooks/work_order_route_operation_binding_read_helper_isolated_smoke_evidence_20260714.md`.
- No binding write helper or runtime-init/work-order-release integration was
  added.
- No API, Kiosk, IoT/MQTT, Observer, OEE/KPI, MESQL, or FERP change was made.

## Verified Controlled Work-Order Route-Operation Binding Writes

- Last updated: `2026-07-14`.
- Implementation commit:
  `d67a3fb feat: add controlled work-order route-operation binding writes`.
- Helper: `create_work_order_operation_route_binding`.
- Unit regression: targeted `143` tests and combined `179` tests, both `OK`.
- Source `mes` binding table remained absent and no helper was called against
  the source database.
- Before clone migration, the real write helper propagated PostgreSQL
  `UndefinedTable` (`42P01`) without returning replay or conflict.
- Migration `009_work_order_operation_route_binding.sql` was applied only to
  disposable clone `mes_binding_write_smoke_20260714_140320`.
- Binding A first insert returned `created=true`; its exact replay returned
  `created=false` with unchanged PK, timestamps, and metadata.
- Binding B first insert returned `created=true`; its exact replay returned
  `created=false` with unchanged PK, timestamps, and metadata.
- Final clone binding row count was `2`.
- Operation-already-bound, binding-ID reuse, metadata, source, actor, and
  crossed-unique conflicts returned
  `409 WORK_ORDER_OPERATION_ROUTE_BINDING_CONFLICT` without partial rows.
- Missing lifecycle and route-operation parents propagated PostgreSQL
  `ForeignKeyViolation` (`23503`) without conflict masking or partial rows.
- Post-error Binding A/B exact replays succeeded, proving clean subsequent
  connection/transaction behavior.
- Binding count/digest and all existing 15 table counts/digests were unchanged
  throughout conflict, FK, and recovery calls.
- The clone-only bindings were created for helper verification and are not
  accepted production semantic mappings.
- Source `mes` remained unchanged, the disposable clone was dropped, and its
  absence was verified.
- Evidence:
  `docs/runbooks/work_order_route_operation_binding_write_helper_isolated_smoke_evidence_20260714.md`.
- No runtime-init or work-order-release integration was added.
- No API, Kiosk, IoT/MQTT, Observer, OEE/KPI, MESQL, or FERP change was made.

## Verified Canonical V2 Bound Runtime Initialization

- Last updated: `2026-07-15`.
- Base binding-validation commit: `e39d32f`.
- Existing-state route-identity guard fix commit: `6d3f827`.
- Prior FAIL evidence:
  `docs/runbooks/station_execution_canonical_v2_bound_runtime_init_isolated_smoke_evidence_20260714.md`.
- Retry PASS evidence:
  `docs/runbooks/station_execution_canonical_v2_bound_runtime_init_retry_evidence_20260715.md`.
- Corrected initialization acceptance is `ready`,
  `current_step_code=NULL`, and three ordered pending steps; initialization
  does not activate the first step.
- Unit regression: targeted `181` tests and combined `217` tests, both `OK`.
- Source `mes` binding table remained absent and Canonical V2 route count
  remained `0`.
- Historical V1 existing-state replay without binding-table dependency: PASS.
- Pre-migration new init propagated PostgreSQL `UndefinedTable` (`42P01`):
  PASS.
- Binding migration and Canonical V2 seed were applied only to disposable
  clone `mes_bound_runtime_init_retry_20260715_094604`.
- V2 config scope was `1 / 2 / 4`, OP10/OP20 step scope was `3 / 1`, and
  configured/resolved location roles were `5 / 5`.
- Missing binding returned
  `409 WORK_ORDER_OPERATION_ROUTE_BINDING_REQUIRED`.
- New-state binding mismatch returned
  `409 WORK_ORDER_OPERATION_ROUTE_BINDING_MISMATCH`.
- Explicit clone-only V2 OP10 binding first create / replay returned
  `true / false`.
- Matching initialization returned `initialized=true`, `ready`,
  `current_step_code=NULL`, and three pending steps.
- Exact matching replay returned `initialized=false` with the stored V2 route
  identity.
- Existing-state wrong-route call returned
  `409 EXECUTION_STATE_ROUTE_OPERATION_MISMATCH` without replay or mutation.
- Correct-route post-error replay passed without transaction leakage.
- Matching init changed only execution state `+1` and runtime steps `+3`;
  events / approvals / production flow remained `0 / 0 / 0` for the candidate.
- Binding, config, lifecycle, and queue snapshots were unchanged during init,
  replay, wrong-route rejection, and recovery.
- The clone-only binding verifies runtime behavior and is not an accepted
  production semantic mapping.
- Source 15/15 counts and digests remained unchanged, the clone was dropped,
  and no matching disposable database remained.
- No step execution or work-order release integration was performed.
- No API, Kiosk, IoT/MQTT, Observer, OEE/KPI, MESQL, or FERP change was made.

## Verified Canonical V2 OP10 Execution Flow

- Execution date: `2026-07-15`.
- Runtime-init retry documentation commit: `6f701b9`.
- Evidence:
  `docs/runbooks/station_execution_canonical_v2_op10_execution_isolated_smoke_evidence_20260715.md`.
- Source `mes` binding table remained absent and Canonical V2 route count
  remained `0`.
- Binding migration and Canonical V2 seed were applied only to disposable
  clone `mes_canonical_v2_op10_flow_20260715_101356`.
- Candidate:
  `WO-E2E-SARI-001 / 7db278d4-2246-45d8-8d0f-18618113d7f7 / ASSEMBLY_01 / OP-ASSEMBLY / 10 / queued`.
- Explicit clone-only V2 OP10 binding first create / replay returned
  `true / false`; it verifies runtime behavior and is not an accepted
  production semantic mapping.
- Initialization returned `ready`, `current_step_code=NULL`, and three pending
  steps; exact duplicate initialization returned `initialized=false` with no
  mutation.
- Color sensor start and finish passed with configured source
  `COLOR_SENSOR_ENTRY`; both exact duplicate calls were no-ops.
- Robot `implicit_start + auto_finish` passed with source `ROBOT_ARM_DROP`;
  its duplicate finish was a no-op and its start/completion timestamp and event
  reference pairs were equal.
- Observation manual start/finish passed with `KIOSK_OPERATOR` and actor
  `SMOKE_OPERATOR`; duration was nonnegative and both duplicate calls were
  no-ops.
- `auto_close_on_required_steps` produced final state `closed`,
  `current_step_code=NULL`, with all three required steps completed.
- Operation-event delta was exactly `5`; additional `system_transition` events
  were `0` and approval / production-flow deltas were `0 / 0`.
- Binding, lifecycle, queue, config/master, and location snapshots were
  unchanged through execution; candidate lifecycle / queue stayed
  `queued / queued`.
- Source 15/15 counts and digests remained unchanged, the clone was dropped,
  and no matching disposable database remained.
- The execution flow verified runtime-engine behavior only; no work-order
  lifecycle, inventory movement, or work-order release integration occurred.
- No API, Kiosk, IoT/MQTT, Observer, OEE/KPI, MESQL, or FERP change was made.

## Work-Order Release and Route-Binding Architecture

- Last updated: `2026-07-15`.
- OP10 execution documentation commit:
  `34d89f1 docs: record canonical v2 op10 execution smoke`.
- Verified current runtime boundary: Canonical V2 OP10 can initialize from an
  explicit immutable binding, execute its three required steps, and reach
  runtime `closed`.
- Runtime close does not currently mutate lifecycle or queue: the verified
  candidate lifecycle operation and station queue row remained
  `queued / queued`.
- Repository creation behavior has two separate paths:
  - JSON/FERP runtime import and its database mirror create/update work-order
    state and legacy queue projection but do not create the complete database
    lifecycle-operation set or select a route version.
  - MESQL pull atomically upserts a work order, one payload-defined lifecycle
    operation, and its queue row, but does not select/freeze route identity or
    create operation bindings.
- No production `release_work_order` flow, distinct `released` status, or
  persistent work-order route/version selection currently exists. `queued` is
  the current release-equivalent status.
- Accepted model: controlled hybrid with mutually exclusive
  `route_generated` and `explicit_existing_operation_mapping` modes.
  `route_generated` is the default for new local MES work; explicit mapping is
  reserved for a clean complete set of pre-existing operations with stable
  lifecycle UUIDs.
- Route selection is always explicit `route_code + route_version`, resolved to
  one `process_route_id`. Active status is a selection-time validation guard;
  no latest-version, product, station, operation-code, or sequence inference is
  allowed.
- Selected work-order persistence is an additive immutable
  `mes.work_order_route_releases` sidecar carrying release identity, exact
  process route/code/version, mode, count/digest, actor/source, timestamps, and
  audit metadata.
- Route-generated lifecycle UUIDs are server-controlled and retry-stable
  UUIDv5 values. Explicit mapping requires exact set equality. Lifecycle
  station/code/sequence fields are validated snapshots; config identity remains
  the immutable operation binding.
- Release record, generated/validated lifecycle operation set, all binding
  rows, one initial queue row, and work-order `queued` state must share one
  local PostgreSQL transaction. Failure leaves no partial artifact; exact
  replay returns `released=false` without mutation.
- Release queues only the smallest unique route sequence. Queue identity stays
  `work_order_operation_id`; config identity stays
  `binding.route_operation_id`. Existing successor activation remains a
  lifecycle sequence/UUID concern.
- Runtime `closed -> lifecycle completed -> successor queued` is a separate
  completion-bridge phase. It is not part of work-order release; Phase 5F
  designs it and Phase 5G implements/smokes OP10 completion and OP20 queueing.
- Existing work orders receive no automatic backfill. Retained V1 historical
  replay remains compatible; partial/ambiguous legacy bindings are not inferred
  or completed automatically, and manual migration requires separate approval
  and evidence.
- FERP may later provide work-order identity and explicit route/mapping data,
  but local PostgreSQL remains the atomic release boundary. MESQL is not the
  route source of truth. FERP acknowledgement/outbox, MESQL reconciliation,
  API, and feature-flag work are deferred to Phase 5H or later.
- Decision:
  `docs/architecture/work_order_release_route_binding_decision.md`.
- Implementation plan:
  `docs/architecture/work_order_release_route_binding_implementation_plan.md`.
- Disposable smoke plan:
  `docs/runbooks/work_order_release_route_binding_isolated_smoke_plan.md`.
- This checkpoint changes no Python, tests, migration, seed, database, Docker,
  runtime, lifecycle, binding, queue, API, Kiosk, IoT/OEE, approval,
  production-flow, inventory, FERP, or MESQL behavior.

## Work-Order Route-Release Schema and Helper Contract Draft

- Last updated: `2026-07-15`.
- Phase 5A architecture commit:
  `8de2da4 docs: define work-order release route binding architecture`.
- Preferred additive migration draft:
  `db/migrations/010_work_order_route_release.sql`.
- Selected immutable sidecar: `mes.work_order_route_releases`, one work order
  to at most one release and one release ID to exactly one work order.
- Exact release-table physical scope is `14` columns, `15` named constraints,
  and `5` indexes. No active/update/delete/effective/supersession/reroute field
  is present.
- Parent route same-row identity is database-backed by
  `uq_mes_process_routes_identity_snapshot` on
  `(route_id, route_code, version)` and child composite FK
  `fk_mes_work_order_route_releases_route_identity` on
  `(process_route_id, route_code, route_version)`.
- The migration contains no release row, binding, lifecycle operation, queue,
  status mutation, seed, legacy adoption, or backfill.
- Initial apply must leave the release table empty, but migration assertions are
  row-count-independent so reapply remains valid after release data exists.
- Accepted schema modes remain `route_generated` and
  `explicit_existing_operation_mapping`; Phase 5D initially enables only
  `route_generated`.
- Initial release-source allowlist contains only `local_planning`; FERP, MESQL,
  and migration/backfill sources require a future additive migration and
  integration phase.
- Operation UUIDv5 namespace:
  - label: `urn:mes:work-order-route-release:operation:v1`
  - UUID: `51e8ce07-9395-54f4-9677-a32d03162cdc`
- Binding UUIDv5 namespace:
  - label: `urn:mes:work-order-route-release:binding:v1`
  - UUID: `2e5192a2-5d5a-5f76-a9f6-dc70df96564a`
- Both deterministic identities use exact canonical name
  `<release_id>\n<route_operation_id>` with one LF byte. Operation UUID text is
  canonical lowercase; binding ID is
  `BINDING-WORK-ORDER-RELEASE-<UPPERCASE-UUID>`.
- Operation-set digest is SHA-256 over exact UTF-8 canonical JSON serialized
  with `ensure_ascii=False`, `sort_keys=True`, and compact separators; output is
  64-character lowercase hex. Route identity, release mode, sequence, config
  operation ID, and lifecycle UUID are included; metadata/actor/source are
  compared separately.
- Proposed core helper:
  `release_work_order_to_route(config, *, release_id, work_order_id,
  route_code, route_version, release_source, released_by, mode,
  operation_bindings=None, metadata=None)`.
- Documentation-only baseline regression passed: targeted MESQL V2 `181` tests
  and combined station-execution/location/MESQL V2 `217` tests, both `OK`.
- The helper contract requires one shared transaction cursor for the immutable
  release, deterministic lifecycle operations, complete bindings, initial
  queue, and release-equivalent queued work-order state. Exact replay returns
  `released=false` with unchanged persisted rows/timestamps.
- Runtime `closed -> lifecycle completed -> successor queued` remains the
  separate Phase 5F/5G completion-bridge boundary and is not implemented by
  release.
- Schema plan:
  `docs/architecture/work_order_route_release_schema_plan.md`.
- Helper contract:
  `docs/architecture/work_order_release_helper_contract.md`.
- Controlled migration apply runbook:
  `docs/runbooks/work_order_route_release_migration_apply_runbook.md`.
- The migration has not been applied. No database/Docker connection, release
  implementation, API/feature flag, lifecycle/binding/queue write, runtime
  helper, completion bridge, FERP, MESQL, Kiosk, IoT/OEE, approval,
  production-flow, or inventory action was performed.

## Verified Work-Order Route-Release Schema Migration

- Schema commit:
  `3e4771154d19d43da6aee42a8939632e19e1c324` (`3e47711`), migration
  `db/migrations/010_work_order_route_release.sql`.
- Source `mes` was not migrated. Migration apply, Canonical V2 seed, and
  fixtures were confined to disposable `template0` plus logical-dump clones.
- First apply: PASS with exact physical shape `14 / 15 / 5` columns,
  constraints, and indexes; no-backfill release count was `0`.
- Exact parent `uq_mes_process_routes_identity_snapshot` covered
  `(route_id, route_code, version)`. Exact child composite
  `fk_mes_work_order_route_releases_route_identity` covered
  `(process_route_id, route_code, route_version)` and referenced the parent
  columns in the same order.
- The same-row invalid route-identity insert failed with SQLSTATE `23503` and
  rolled back.
- Existing 15-table count/digest no-write comparison: PASS.
- Empty reapply: PASS; table/sequence/schema identity, parent constraint, and
  zero release rows were preserved without duplicate objects.
- Data-bearing reapply: PASS; fixture PK, values, metadata, timestamps, row
  digest, sequence state, and schema identity were preserved.
- Negative cases all PASS: missing column, wrong digest check, wrong route FK,
  wrong mode allowlist, and unexpected extra index.
- The documented assertion prefix was observed in all negative cases; silent
  repair was absent and every malformed migration transaction rolled back to
  its pre-attempt catalog/data snapshot.
- Source final integrity: PASS. Source release/binding tables and parent
  snapshot constraint remained absent, Canonical V2 route count remained `0`,
  retained V1 was unchanged, and all clone-only IDs were absent.
- All primary/negative clones were dropped; health remained HTTP `200` with
  `status=ok`.
- No Python/read-helper/write-helper/API/release execution, lifecycle/binding/
  queue/runtime action, completion bridge, inference/backfill, or Docker
  rebuild/recreate/restart/down/volume operation occurred.
- Evidence:
  `docs/runbooks/work_order_route_release_migration_isolated_smoke_evidence_20260715.md`.

## Verified Work-Order Route-Release Read Model

- Implementation commit:
  `a3e611adacf5cd23d2c120eb620a63769b3a6542` (`a3e611a`, Phase 5C).
- Focused review found no actionable P1, P2, or P3 issue. The five public read
  helpers preserve exact release/route identity, lifecycle-UUID binding scope,
  deterministic operation order, first-lifecycle initial queue scope, and
  incomplete snapshot components without fallback or inference.
- Regression: targeted MESQL V2 `227` tests and combined station-execution
  config/location/MESQL V2 `263` tests, both `OK`; compile and diff checks
  passed.
- Source `mes` remained read-only. Backup and repeatable-read baseline were
  taken before an empty `template0` database was restored from the logical
  dump; restore equality was `15/15` counts and `15/15` digests.
- Before migration `010`, the real release read raised unmasked
  `psycopg.errors.UndefinedTable` with SQLSTATE `42P01`.
- Migrations `009`, `010`, and Canonical V2 seed `006` ran only on the exact
  disposable clone. Verified shapes were binding `9/9/4`, release `14/15/5`,
  V2 route/operations/steps `1/2/4`, OP10/OP20 steps `3/1`, and roles `5/5`.
- UUIDv5 namespace recomputation, fixed operation UUIDs, fixed binding IDs,
  exact one-LF canonical names, fixed digest
  `4063a5c72fd4d38f11757a4bf1115f83e1c05e8b97624deb808193c5d0fcb2e2`,
  repeated-call stability, caller non-mutation, and utility no-DB behavior all
  passed.
- Release reads returned exact 14-field JSON-safe rows with dictionary metadata
  and ISO timestamps. Case-mismatched release identity returned `None`.
- Exact route version `2` and OP10/OP20 order passed; wrong version `999`
  returned `None`, missing route operations returned `[]`, and no fallback or
  inference occurred.
- Complete snapshot returned exact 8-field work order, exact 14-field lifecycle
  operations in `10,20` order, lifecycle-scoped bindings in the same order, and
  an initial queue bound only to OP10. A foreign work-order binding to the same
  route operation was excluded.
- Incomplete snapshot retained release and work order while returning
  operations `[]`, bindings `[]`, and queue `None`.
- Repeated helper reads preserved `17/17` table count/digest snapshots. The
  instrumented full snapshot used one connection, one cursor, and zero commit
  calls.
- Exact clone cleanup left zero matching databases. Final source integrity was
  `15/15` counts and `15/15` digests; extended schema/V2 state, retained V1,
  and `4/0/0` audit counts were unchanged, fixture IDs were absent, and health
  remained HTTP `200` with `status=ok`.
- No release writer, API, completion bridge, FERP/MESQL integration,
  implementation change, commit, or push occurred.
- Evidence:
  `docs/runbooks/work_order_route_release_read_helper_isolated_smoke_evidence_20260715.md`.

## Work-Order Release Transaction Primitive Design

- Last updated: `2026-07-15`.
- Phase 5C documentation closure commit:
  `a19df4b34d6e1466816e629cbb91f8a59a89195f`
  (`a19df4b`, `docs: record work-order route-release read smoke`).
- Phase 5C read model is fully verified. The Phase 5D writer is not
  implemented; no Python, test, migration, DB, Docker, API, lifecycle,
  binding, queue, or status action occurred in this checkpoint.
- Design status: `READY_FOR_PRIVATE_PRIMITIVE_IMPLEMENTATION`.
- The future writer keeps the approved public signature and initially enables
  only `route_generated / local_planning`.
- One `READ COMMITTED` transaction owns one connection/cursor. Normative order
  is request validation, work-order lock, ordered release locks, exact
  route/config reads, existing artifact locks/classification, deterministic
  derivation, release/operation/binding/queue/status writes, authoritative
  snapshot, and commit.
- Selected insert order is release, deterministic lifecycle operations,
  immutable bindings, initial queue, then work-order status.
- Queue allocation uses a transaction advisory lock namespaced by station and
  the exact partial-index predicate
  `status IN ('queued', 'active', 'pending_approval')`. `ready` is excluded;
  no schema change is planned.
- Generated lifecycle IDs and binding IDs reuse the Phase 5C UUIDv5 utilities.
  Dedicated lifecycle insert SQL will not reuse MESQL snapshot-updating upsert.
- Positive target quantity and active route-item unit are initial Phase 5D
  route-generated eligibility policy, not new schema constraints.
- Phase 5D-A amends and supersedes the Phase 5B strict replay rule: immutable
  release row, deterministic static operation snapshots, and complete binding
  set remain exact; work-order/operation statuses, good/scrap quantities,
  start/completion/update timestamps, and queue status/rank may progress.
  The same immutable request still returns `released=false` with zero writes.
- Caller release metadata uses normalized JSONB structural equality and is
  never merged. First release updates only work-order status/`updated_at`;
  payload and metadata are preserved. Replay updates nothing.
- A `23505` path fully rolls back and closes the first transaction context
  before authoritative classification opens a new connection, transaction,
  and cursor. Constraint names do not replace persisted-state readback.
- Failure injection uses fake cursor or test-process private primitive/proxy
  seams; production receives no public test flag.
- Phase 5D-B owns private cursor-scoped primitives and unit tests. Phase 5D-C
  owns public route-generated writer orchestration, replay/concurrency/rollback
  tests. Phase 5E executes the disposable writer smoke.
- Runtime completion remains Phase 5F/5G. Explicit mapping, API, FERP, MESQL,
  backfill, reroute, and cancellation remain deferred.
- Design:
  `docs/architecture/work_order_release_transaction_primitive_design.md`.
- Concurrency/idempotency plan:
  `docs/architecture/work_order_release_concurrency_idempotency_plan.md`.
- Future isolated smoke plan:
  `docs/runbooks/work_order_release_writer_isolated_smoke_plan.md`.

## Verified Work-Order Route-Release Writer

- Last verified: `2026-07-15`.
- Phase 5D-C implementation commit:
  `e123a7d38e13fa64cabce71531b74fcfce12d7ff` (`e123a7d`,
  `feat: add work-order route release writer`). This supersedes the historical
  pre-implementation status in the Phase 5D-A design checkpoint above.
- Focused review found no actionable P1 or P2 issue. The committed scope is
  exactly `mes_web/db/mesql_v2.py` and `tests/test_mes_web_mesql_v2.py`.
- Regression passed: targeted MESQL V2 `403` tests and combined
  station-execution config/location/MESQL V2 `439` tests, both `OK`; compile
  and diff checks also passed.
- Public support remains intentionally limited to
  `route_generated / local_planning`. Explicit mapping, FERP, MESQL, reroute,
  cancellation, and backfill remain disabled or deferred.
- First release atomically persisted one release, two deterministic lifecycle
  operations, two immutable lifecycle-UUID bindings, only the OP10 initial
  queue row, and queued work-order state.
- Immediate replay and replay after mutable lifecycle/work-order/queue
  progression both returned `released=false` with zero rewind. Immutable
  release, static operation snapshots, binding set, and digest remained exact.
- The five Phase 5C read helpers agreed with writer output; foreign work-order
  bindings were excluded and the initial queue remained scoped to the first
  lifecycle UUID.
- Existing runtime init remained compatible: OP10 initialized `ready` with
  three pending steps, no current step, no step execution, and no event,
  approval, production-flow, lifecycle, binding, or queue mutation.
- Full deterministic conflict and eligibility matrices passed with no partial
  writes. Exact route/version resolution performed no fallback or inference.
- Concurrency passed: identical requests produced one first release and one
  replay; cross-order duplicate release IDs produced one success and one ID
  conflict; same-station releases received distinct ranks and no OP20 queue.
- Queue allocation matched the partial unique index exactly:
  `status IN ('queued', 'active', 'pending_approval')`; a high-rank `ready`
  row did not affect allocation.
- Controlled non-cooperating queue `23505` rolled the first transaction back,
  then authoritative readback opened a new context on a different PostgreSQL
  backend and returned `WORK_ORDER_RELEASE_QUEUE_CONFLICT`. There was no rank
  retry; clean caller retry succeeded after blocker removal.
- Unrelated real `23505`, SQLSTATE `23503`, `40P01`, `40001`, `08006`,
  `XX000`, and a generic failure propagated as their original error objects.
- All `12/12` real-transaction failure-injection points left zero artefact
  delta and unchanged work-order state; every clean retry succeeded.
- Source `mes` remained read-only. A retained logical backup was restored into
  an empty `template0` clone; migrations `009`/`010` and Canonical V2 seed
  `006` ran only on that clone.
- Pre-migration writer failure was unmasked SQLSTATE `42P01`. Post-migration
  binding/release/V2 prerequisite shapes were `9/9/4`, `14/15/5`, and
  `1/2/4` with OP10/OP20 steps `3/1`.
- The exact clone was dropped and matching clone count is `0`. Final source
  integrity is `15/15` counts and `15/15` digests; extended/V1 state and
  `4/0/0` event/approval/flow counts are unchanged. Health is HTTP `200`,
  `status=ok`.
- Status: `READY_FOR_PHASE_5F_DESIGN`. No Phase 5F implementation, API,
  completion bridge, FERP/MESQL, inventory, migration, source rollout, Docker
  lifecycle, or push action occurred.
- Evidence:
  `docs/runbooks/work_order_release_writer_isolated_smoke_evidence_20260715.md`.

## Runtime-to-Lifecycle Completion Bridge Design

- Last updated: `2026-07-15`.
- Phase 5E documentation closure commit:
  `02f0fcf71f3eedfd7e58e7fe0e7a28d6e711864f` (`02f0fcf`,
  `docs: record work-order route release writer smoke`). The commit contains
  only Phase 5E evidence and its prior `CURRENT_STATE` closure; no push was
  performed.
- Phase 5E route-release writer is verified and ready. Phase 5F status is
  `READY_FOR_COMPLETION_BRIDGE_IMPLEMENTATION`.
- Existing `finish_execution_step` atomically inserts the triggering finish
  event and updates runtime step/execution state, but currently stops at
  runtime completion policy. Only `auto_close_on_required_steps` reaches
  `closed`; manual-close and approval-close transitions are not implemented.
- Existing `complete_operation_v2` separately completes lifecycle/queue,
  infers and upserts a successor, mutates quantities, and writes completion,
  work-order event, and outbox rows. It is not reused by the bridge because its
  legacy adoption, rank predicate, audit, and quantity behavior violate the
  route-release bridge boundary.
- Selected production model is a synchronous private bridge inside the same
  cursor and transaction that first persists runtime `closed`. A public wrapper
  with two independent transactions and background polling are rejected.
- Applicability is checked before sidecar access using exact lifecycle metadata
  marker `source=work_order_release` plus nonblank `release_id`. Marker absence
  preserves retained V1/legacy behavior, returns `completion_bridge=None`, and
  performs no migration `009/010` table query.
- Marker presence requires explicit sidecar schema readiness. Missing schema is
  `503 RUNTIME_COMPLETION_BRIDGE_SCHEMA_NOT_READY`; `UndefinedTable` is never
  converted into a generic legacy no-op. Missing/inconsistent release or
  binding after readiness is a deterministic conflict.
- `finish_execution_step` keeps its signature and will add the
  `completion_bridge` response key on every path. A duplicate event cannot
  early-return before bridge classification: the first supported close returns
  `bridged=true`, exact duplicate/concurrent replay returns `bridged=false`,
  and nonclosed/legacy/not-applicable paths return `None`.
- The authoritative trigger is persisted `execution_status=closed`; lifecycle
  completion timestamp is persisted `execution_state.closed_at`, not a new
  application timestamp or policy-name inference.
- Normative lock order is work order, release, lifecycle UUID order, binding PK
  order, execution state, runtime step order, lexical station advisory locks,
  then station/queue-PK row order. This shares the Phase 5D prefix and avoids a
  reverse lock against release replay.
- Current and successor station locks are built from exact persisted station
  codes as a unique lexical-sorted set. Each station is locked exactly once;
  equal current/successor stations use one advisory lock.
- Current lifecycle `queued` or `active` becomes `completed` at runtime
  `closed_at`; quantities, started_at, payload, and metadata remain unchanged.
  Its exact UUID-scoped queue row is retained, marked `completed`, and keeps
  rank/source/payload/metadata.
- Successor is only the same work order's unique smallest greater lifecycle
  sequence and uses its immutable UUID/binding. No station/code/latest-route,
  config, or legacy queue inference is allowed.
- First successor activation is `planned -> queued`. The exact queue source is
  `runtime_completion_bridge`; immutable payload carries order/UUID/operation/
  sequence/station/queued identity and metadata carries source, release ID, and
  predecessor lifecycle UUID.
- Successor rank uses only `queued`, `active`, and `pending_approval`; `ready`
  is excluded. Known queue `23505` rolls the complete finish/bridge transaction
  back and is not automatically retried.
- With no successor, all lifecycle operations must be completed before the work
  order becomes `completed`; work-order `completed_at` equals final runtime
  `closed_at`. Payload, metadata, release, and bindings remain unchanged.
- Exact replay performs zero writes and preserves original timestamps/ranks.
  Later successor or work-order operational progression does not invalidate an
  earlier exact bridge replay. Partial or conflicting state is never repaired.
- The bridge emits no extra operation/system event, approval, production
  completion, work-order event, production-flow event, outbox row, or inventory
  movement. The triggering finish event and persisted timestamps are the audit
  evidence.
- Phase 5G-A owns private cursor primitives and unit tests. Phase 5G-B owns
  atomic `finish_execution_step` integration, response/replay/error
  orchestration, and unit tests. Phase 5G-C owns the disposable PostgreSQL
  release -> OP10 close -> OP20 queue -> OP20 close -> work-order complete
  smoke.
- API, Kiosk, IoT adapter, manual/approval close endpoints, FERP, MESQL,
  inventory, backfill, reconciliation, and retained V1 mutation remain
  deferred. No Python, test, migration, DB, Docker, API, or bridge
  implementation action occurred in Phase 5F.
- Bridge design:
  `docs/architecture/runtime_lifecycle_completion_bridge_design.md`.
- Concurrency plan:
  `docs/architecture/runtime_lifecycle_completion_bridge_concurrency_plan.md`.
- Future isolated smoke plan:
  `docs/runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_plan.md`.

## Verified Runtime-to-Lifecycle Completion Bridge

- Last verified: `2026-07-15`.
- Phase 5G-B implementation commit:
  `0910a145c73d2c0791fe1a1dd178702e01d04e55`.
- The first Phase 5G-C isolated smoke failed only at concurrent duplicate
  replay because stale preflight lifecycle `status/completed_at` values were
  compared with post-lock progressed state. Its committed FAIL evidence is
  retained unchanged as historical evidence.
- Phase 5G-BR1 hotfix commit:
  `2c62ad9ea3473886a51a0d1fa61bb25c10c0667f`
  (`fix: allow completion bridge replay after concurrent progress`).
- Post-lock preflight revalidation now covers only immutable lifecycle UUID,
  work-order ID, operation code, sequence, station, and exact
  `source/release_id` marker identity. Mutable status/timestamp progression is
  handled by the authoritative replay classifier.
- Focused review found no P1/P2 issue. Regression passed at targeted `600` and
  combined `636`; compile and diff checks passed.
- A fresh `template0` plus logical-restore disposable clone passed the complete
  PostgreSQL retry matrix. Pre-sidecar legacy returned
  `completion_bridge=None` with zero sidecar queries; marker-present missing
  schema returned `503 RUNTIME_COMPLETION_BRIDGE_SCHEMA_NOT_READY` with zero
  writes; unclassified `UndefinedTable` propagated unchanged.
- Route-generated release through OP10 close, OP20 activation/queue, OP20
  close, and final work-order completion passed with exact authoritative
  timestamps and immutable snapshot preservation. Immediate and progressed
  replays returned `bridged=false` with zero writes.
- Real synchronized concurrent duplicate finish produced one
  `finished/event_inserted/bridged=true` result and one all-false replay.
  Persisted state contained one event/runtime close/current completion/current
  queue terminalization/successor activation/successor queue; loser advisory,
  rank-read, and write calls were all zero.
- Same-successor-station concurrency produced two successful bridges with
  distinct ranks and lexical unique station locks. High-rank `ready` state was
  excluded from active-rank allocation. Equal current/successor station state
  returned the deterministic queue conflict with full rollback.
- Live queue `23505` closed and rolled back the first context, used a fresh
  PostgreSQL backend for authoritative classification, performed no rank
  retry, returned `RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT`, and succeeded on
  explicit retry after blocker removal.
- Unknown `23505`, `23503`, `40P01`, `40001`, `08006`, `XX000`, and generic
  errors propagated unchanged with rollback and clean retry. All `12/12`
  real-transaction failure injections had zero row-digest delta and clean
  retry success.
- The bridge emitted no additional system-transition event, approval,
  production flow/completion, work-order event, outbox, package-state, or
  inventory effect.
- Source `mes` remained read-only. Final integrity matched the retained
  baseline for all `38/38` source tables and established `15/15` counts and
  digests; retained V1 was `1/2/5`, source V2 remained `0`, sidecars remained
  absent, audit remained `4/0/0`, and retry fixture count remained `0`.
- Exact clones and container temporary files were removed; matching clone
  count is `0`. The host backup is retained. Health is HTTP `200`,
  `status=ok`, and container health is `healthy`.
- Status: `VERIFIED`. API, Kiosk, IoT, FERP, MESQL, inventory, backfill,
  reconciliation, manual/approval close paths, and source rollout remain
  deferred.
- Historical FAIL evidence:
  `docs/runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_evidence_20260715.md`.
- Successful retry evidence that supersedes the failed acceptance result:
  `docs/runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_retry_evidence_20260715.md`.

## Canonical V2 Controlled Source Rollout Design

- Last updated: `2026-07-15`.
- Verified completion-bridge documentation closure commit:
  `7e94382a90c6bdfba81928588785a08b37e18fa3`
  (`docs: record verified runtime lifecycle completion bridge`). The commit
  contains only `CURRENT_STATE.md` and the successful retry evidence; the
  historical FAIL evidence remains unchanged.
- The accepted evidence-based source baseline remains: migration `009` absent,
  migration `010` absent, Canonical V2 absent, retained V1
  route/operations/steps `1 / 2 / 5`, and audit events/approvals/flow
  `4 / 0 / 0`. Live source truth must be revalidated read-only in Phase 5H-B.
- Phase 5H-B is schema/config readiness only. Its exact order is binding
  migration `009`, release migration `010`, then Canonical V2 seed `006`.
  Work-order release, runtime initialization, step execution and completion
  bridge are excluded.
- Every SQL artifact already owns its `BEGIN/COMMIT` transaction and will run
  through a separate `psql -X -v ON_ERROR_STOP=1 -f` call. No outer transaction
  or multi-artifact concatenation is permitted. Each first apply and exact
  reapply has a stop-after-verification checkpoint.
- Phase 5H-B requires exact source identity, a retained plain logical backup at
  `mes_before_canonical_v2_source_rollout_<timestamp>.sql`, one read-only
  repeatable-read preflight, established count/digest capture, and exact
  partial-state absence. Unexpected sidecars, parent constraint, V2 rows or
  identifier collisions block apply; no state is adopted or repaired.
- The logical backup is written byte-safely to an exact container-side file by
  `pg_dump -f`, validated in the container, copied with `docker cp`, and
  validated again on the host. Positive size, dump header, and container/host
  SHA-256 equality are mandatory. PowerShell native dump redirection is
  forbidden; the container temporary file is removed only after full host
  validation and hash equality. Any backup/copy/hash failure blocks Phase 5H-B
  before migration `009`.
- The authoritative relation invariant is set-based: the final `mes` base-table
  set must equal the preflight base-table set plus exactly
  `work_order_operation_route_bindings` and `work_order_route_releases`.
  `information_schema.tables` with `table_type='BASE TABLE'` is used; sequences
  and other relations are excluded. A final helper count of `40` is expected
  only when the verified baseline helper count is `38`.
- Expected Phase 5H-B outcome is binding `9 / 9 / 4` with zero rows, release
  `14 / 15 / 5` with zero rows, exact parent route identity constraint, V2
  route/operations/steps `1 / 2 / 4`, OP10/OP20 steps `3 / 1`, both operations
  using `auto_close_on_required_steps`, and location roles `5 / 5`.
- On failure, the current artifact transaction rolls back and subsequent
  artifacts and Phase 5H-C do not start. Prior successful additive checkpoints
  are not dropped. Reapply and backup restore require separate approval; restore
  is a destructive recovery decision.
- Phase 5H-C is a separate, explicitly approved source-local functional smoke.
  It uses one retained nonproduction identity prefixed
  `PHASE5HC-SOURCE-SMOKE-`, exercises release through OP10/OP20 and final
  completion, and then proves exact replays. Successful or partial-failure
  fixture rows are not silently deleted.
- The retained fixture must carry `disposable_test=true`,
  `production_release=false`, `exclude_from_analytics=true`, and
  `retention_reason=source_rollout_validation`. Future OEE, KPI, analytics,
  reporting, FERP and export consumers must exclude it by exact order prefix or
  metadata. Consumer filter implementation is a mandatory deferred requirement,
  not part of Phase 5H-A/B/C.
- No release API, feature flag, Kiosk action, FERP/MESQL input, automatic route
  selection, analytics filter, inventory behavior, DB apply, Docker action or
  source fixture was added in Phase 5H-A.
- Phase 5H-B status: `READY_FOR_CONTROLLED_SOURCE_SCHEMA_SEED_APPLY`.
- Phase 5H-C status:
  `PLANNED_REQUIRES_PHASE_5H_B_PASS_AND_SEPARATE_APPROVAL`.
- Rollout design:
  `docs/architecture/canonical_v2_source_rollout_design.md`.
- Future schema/seed apply runbook:
  `docs/runbooks/canonical_v2_source_schema_seed_apply_runbook.md`.
- Future source-local functional smoke plan:
  `docs/runbooks/canonical_v2_source_local_functional_smoke_plan.md`.

## Applied Canonical V2 Source Schema and Seed

- Applied and verified: `2026-07-15`.
- Repository implementation baseline:
  `e2cc8c47acd8df573f4d055e3a6ead09ff9c2ae0`. No implementation,
  migration, seed, Python, test, API, or runtime file was changed by the
  rollout evidence task.
- Exact source target was `mes_postgres / mes / mes`, PostgreSQL `16.14`, host
  port `5433`. Every mutation checkpoint began with zero other database
  sessions; verification used read-only repeatable-read snapshots.
- A byte-safe plain backup was written container-side with `pg_dump -f`,
  validated, copied, and revalidated on the host. The retained backup is
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_canonical_v2_source_rollout_20260715-204246.sql`,
  `2881697` bytes, SHA-256
  `252726A3E63CBB4ED8B494ABD340BB3B7894CB459996D7B8DBD80634AAEB1535`.
  The container backup was removed only after exact host equality; no restore
  was run.
- Migration `009`, migration `010`, and Canonical V2 seed `006` were applied
  in that exact order. Every first apply and exact reapply used its own
  `psql -X -v ON_ERROR_STOP=1 -f` process and the artifact-owned transaction;
  no outer transaction or multi-file concatenation was used.
- Migration `009` verified the binding sidecar at `9 / 9 / 4` columns,
  constraints, and indexes with zero rows. Exact reapply preserved table and
  sequence OIDs, catalog definitions, base-table set, and every row digest.
- Migration `010` verified the release sidecar at `14 / 15 / 5` with zero
  rows plus exact nondeferrable
  `uq_mes_process_routes_identity_snapshot UNIQUE (route_id, route_code,
  version)`. Exact reapply had zero catalog/data delta and preserved the
  binding sidecar.
- Seed `006` added only Canonical V2 route/operations/steps `1 / 2 / 4` with
  OP10/OP20 steps `3 / 1`, exact event/step identity, both
  `auto_close_on_required_steps` policies, and configured/resolved location
  roles `5 / 5`. Exact reapply returned three `INSERT 0 0` results and the
  full ordered verification snapshot was unchanged.
- The authoritative final base-table set equals the exact 38-table preflight
  set plus only `work_order_operation_route_bindings` and
  `work_order_route_releases`; the secondary helper count is `40`. Sequences
  and other relation types were excluded. All 35 unaffected original tables
  were count/digest-identical; only the three configuration tables had the
  exact `+1 / +2 / +4` additive delta.
- Retained V1 remained `1 / 2 / 5` with exact scoped digests. Audit remained
  `4 / 0 / 0`; binding/release sidecars remained empty; existing work orders,
  lifecycle, queue, runtime, locations, station bindings, events, approvals,
  flow, outbox, package, and inventory state remained unchanged. No
  `PHASE5HC-SOURCE-SMOKE-%` fixture exists.
- PostgreSQL remained `running / healthy`; `GET /health` returned
  `200 / status=ok`. Exact rollout container temp files were removed and the
  verified host backup remains retained.
- Phase 5H-B status: `PASS / APPLIED_CANONICAL_V2_SOURCE_SCHEMA_AND_SEED`.
- Phase 5H-C was not started and requires separate explicit approval. Status:
  `READY_FOR_SEPARATELY_APPROVED_SOURCE_LOCAL_FUNCTIONAL_SMOKE`.
- Apply evidence:
  `docs/runbooks/canonical_v2_source_schema_seed_apply_evidence_20260715.md`.

## Canonical V2 Source-Local Functional Smoke Failure

- Executed: `2026-07-15`, under the separately approved Phase 5H-C source-local
  smoke task. Phase 5H-B documentation closure commit is
  `764eb3c84a4aebac9b9927bcec4dc0f7275b343c`
  (`docs: record applied canonical v2 source schema and seed`).
- The one retained nonproduction fixture is
  `PHASE5HC-SOURCE-SMOKE-20260715-181940`, with release
  `PHASE5HC-SOURCE-RELEASE-20260715-181940` and actor
  `PHASE5HC_SOURCE_SMOKE`. Its payload/metadata retain
  `disposable_test=true`, `production_release=false`,
  `exclude_from_analytics=true`, and
  `retention_reason=source_rollout_validation`.
- First route release succeeded with one immutable release, deterministic OP10
  UUID `52fb8cd4-005e-51f2-9557-a6ff31ce5063`, deterministic OP20 UUID
  `d78c3f30-9e49-51a3-ad58-a13e45f3705f`, two immutable bindings, and the
  exact two-operation digest. Immediate release replay returned
  `released=false` with zero writes.
- OP10 initialized and completed its exact three configured steps. Its close
  bridged OP20 to queued state and created the exact successor queue. OP20 then
  initialized, completed its one configured step, closed, and completed the
  work order at `2026-07-15T18:35:41.238660+00:00`.
- OP10 and OP20 initialization replays, the immediate/final OP10 finish
  replays, and the OP20 finish replay were idempotent with zero writes. Static
  release, binding, and lifecycle identity snapshots remained immutable.
- Acceptance failed on the required exact route-release replay after final
  completion. It raised `WORK_ORDER_RELEASE_QUEUE_CONFLICT` instead of
  returning `released=false`.
- Root cause is the replay validator's whole-order
  `len(existing_queue) == 1` requirement in
  `_validate_existing_work_order_release_replay`. A completed two-operation
  route correctly retains both the original OP10 queue row and the OP20
  successor queue row. Mutable status/rank fields are not compared, but this
  cardinality check still rejects valid progressed operational state.
- Execution stopped immediately under the Phase 5H-C failure policy. The
  completed but failed-validation fixture was not deleted, repaired,
  compensated, restored, disguised, retried with a new identity, or resumed.
  An independent post-error digest readback could not be obtained because the
  execution environment rejected Docker access after exhausting its usage
  quota; this limitation is recorded in the evidence and does not change the
  required `FAIL` result.
- At the last authoritative final snapshot, only the six explicit configured
  runtime events were added. There was no bridge-added system-transition,
  approval, production-flow/completion, work-order event, outbox, package, or
  inventory effect. Retained V1 remained `1 / 2 / 5` with exact scoped
  digests; locations and station bindings remained unchanged.
- The retained fixture must be excluded from future OEE, KPI, analytics,
  reporting, FERP/MESQL export, and generic export by exact prefix or
  `exclude_from_analytics=true`. Consumer filter implementation remains
  deferred.
- Phase 5H-C status:
  `FAIL_REQUIRES_RELEASE_REPLAY_FIX_AND_SEPARATE_RECOVERY_APPROVAL`.
  No API, feature flag, Kiosk/IoT action, FERP/MESQL input, automatic route
  selection, analytics filter, inventory behavior, migration/seed apply,
  Docker lifecycle, cleanup, H-C commit, or push was added or performed.
- Failure evidence:
  `docs/runbooks/canonical_v2_source_local_functional_smoke_evidence_20260715.md`.

## Verified Canonical V2 Source-Local Functional Flow

- Original functional execution: `2026-07-15`; release-replay recovery
  verification: `2026-07-17`.
- Phase 5H-B closure commit:
  `764eb3c84a4aebac9b9927bcec4dc0f7275b343c`. Historical Phase 5H-C FAIL
  evidence remains committed unchanged under
  `22e9bb75c250bb0e58f7330def665927c5266988`.
- CR1 hotfix commit:
  `c7e7ea2698d873a7ac5c8737bddd97b349355675`
  (`fix: allow route release replay after queue progression`). Focused review
  and regression passed at targeted `632` and combined `668`.
- The retained nonproduction order
  `PHASE5HC-SOURCE-SMOKE-20260715-181940` and release
  `PHASE5HC-SOURCE-RELEASE-20260715-181940` were independently read back
  exact. OP10/OP20 lifecycle and queues remained completed, both runtime states
  remained closed, all `3 + 1` steps remained completed, the work order
  remained completed at `2026-07-15T18:35:41.238660+00:00`, and the six
  configured events remained exact.
- The recovery preflight closes the post-error independent-readback gap recorded
  by the historical FAIL evidence. It found source identity
  `mes_postgres / mes / mes`, PostgreSQL `16.14`, zero competing sessions,
  exact `40` base tables, exact `35` sequence states, and the complete
  retained fixture.
- Byte-safe recovery backup:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_phase5hc_release_replay_recovery_20260717-080314.sql`, `2911692` bytes, SHA-256
  `f4e19c0bd8f97ff898fbc3a1de63ee0c125ee67a437de78292d74c971740e2f0`. Container/host size, header, and hash equality passed; the host
  backup remains retained.
- A `template0` logical-restore clone reproduced source exactly at `40/40`
  table counts/digests, `35/35` sequence states, fixture snapshot, V1, and
  sidecar/V2 state. Its exact release replay returned `released=false`, used
  OP10 PK `6853` as initial queue, performed zero writer/advisory-rank calls,
  and preserved every pre/post snapshot. The clone and restore temp were
  removed; matching clone count is `0`.
- After clone PASS and cleanup, the same exact replay was called on source
  exactly once. It returned `released=false`, agreed with authoritative read
  helpers, performed zero writer/advisory-rank calls, and preserved source
  `40/40` table counts/digests, `35/35` sequence states, and the complete
  fixture snapshot.
- Retained V1 remained `1 / 2 / 5` with exact scoped digests. Audit, outbox,
  package, inventory, locations, and bindings remained exact through full-table
  comparison. PostgreSQL is `running / healthy`; HTTP health is
  `200 / status=ok`.
- The historical failure section and evidence remain unchanged as defect
  history. The recovery evidence supersedes only its failed final-replay
  acceptance result; together the original functional execution and this
  recovery establish the complete Phase 5H-C acceptance chain.
- No new fixture, release, runtime execution, completion bridge, API/Kiosk/IoT
  action, FERP/MESQL operation, inventory/package helper, migration/seed,
  source restore, repair, compensation, or delete was performed. No recovery
  evidence commit or push was created.
- The fixture remains nonproduction and must be excluded from future OEE, KPI,
  analytics, reporting, FERP/MESQL export, and generic export by exact prefix
  or `exclude_from_analytics=true`. Consumer filter implementation remains
  deferred.
- Status: `VERIFIED / PHASE_5H_C_COMPLETE`.
- Recovery evidence:
  `docs/runbooks/canonical_v2_source_local_release_replay_recovery_evidence_20260717.md`.

# Current State

Last updated: 2026-07-09

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

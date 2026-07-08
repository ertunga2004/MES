# Current State

Last updated: 2026-07-07

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

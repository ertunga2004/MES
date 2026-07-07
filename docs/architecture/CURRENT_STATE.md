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

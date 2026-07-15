# Canonical V2 Source Schema and Seed Apply Evidence

## Result

Result: `PASS`

On 2026-07-15, the reviewed Canonical V2 schema and configuration artifacts
were applied to the exact source PostgreSQL target in the approved order:

```text
009_work_order_operation_route_binding.sql
010_work_order_route_release.sql
006_station_execution_seed_canonical_v2.sql
```

Each first apply and exact reapply used its own
`psql -X -v ON_ERROR_STOP=1 -f <container-file>` process. The SQL files own
their `BEGIN/COMMIT` blocks; no outer transaction, concatenation, repair,
adoption, restore, or Docker lifecycle action was used.

No work order, release, lifecycle operation, binding, queue item, runtime
state, event, approval, completion, production-flow row, outbox row, package
state, or inventory movement was created. Phase 5H-C was not started. No API,
Kiosk, FERP, MESQL, runtime, bridge, analytics, or export helper was called.

## Repository and Artifact Identity

```text
branch: main (ahead of origin/main by 1 before and after this run)
HEAD: e2cc8c47acd8df573f4d055e3a6ead09ff9c2ae0
targeted MESQL V2 tests: 600 / OK
combined MES web tests: 636 / OK
Python compile: PASS
git diff --check before apply: PASS
```

Reviewed SHA-256 values matched immediately before source access and matched
the container copies:

| Artifact | SHA-256 |
| --- | --- |
| `db/migrations/009_work_order_operation_route_binding.sql` | `B5DA1799A52147433E1DEA44BD989394D720416D352CC7906F8A1729BE1A0162` |
| `db/migrations/010_work_order_route_release.sql` | `5B7C6CF7261095A6B00C7EF9170ED7F262F648053BDC0B1E3EA4A4B4C7B551F6` |
| `db/migrations/006_station_execution_seed_canonical_v2.sql` | `9B4174BD5756B92DD5D9111BC7E5249020471865F6546B2C47D77F94B79434C8` |

## Maintenance Window and Source Identity

The application log showed no recent source activity. Before every apply or
reapply, `pg_stat_activity` showed zero other sessions for database `mes`.
The read-only preflight and verification snapshots used `REPEATABLE READ`.

```text
container: mes_postgres
container state: running / healthy
database / user: mes / mes
PostgreSQL: 16.14
pg_dump: 16.14
host port: 5433
preflight isolation: repeatable read / read only
other database sessions: 0
```

## Read-Only Preflight

The single read-only repeatable-read preflight captured the authoritative
`mes` base-table set through `information_schema.tables` with
`table_type='BASE TABLE'`. Sequences and other relation types were excluded.

```text
baseline helper count: 38
baseline set fingerprint: e61cdda66e94e9051be17d58e482ea44e8a4154e6ec62ad50939f9f80a503f90
baseline inventory/count/digest fingerprint: 9ce6cbc639a0298bfbc886f99f05316a86eadda1e1cf703ff4cac87c30fca590
binding sidecar: absent
release sidecar: absent
parent identity constraint: absent
V2 route / operation / step collisions: 0 / 0 / 0
retained V1 route / operations / steps: 1 / 2 / 5
operation events / approvals / production-flow events: 4 / 0 / 0
PHASE5HC-SOURCE-SMOKE fixture count: 0
```

The exact 38-table baseline set was:

```text
device_sessions
downtime_events
error_types
ferp_export_outbox
ferp_import_batches
integration_inbox
integration_outbox
item_station_events
items
locations
maintenance_records
maintenance_steps
oee_snapshots
operation_approvals
operation_events
operation_steps
operators
package_bom_lines
package_component_wip
package_sessions
package_traceability
packaging_units
process_routes
production_completions
production_flow_events
quality_overrides
route_operations
schema_migrations
station_event_sources
station_location_bindings
station_queue
stations
vision_events
work_order_events
work_order_operation_execution_state
work_order_operation_steps
work_order_operations
work_orders
```

## Byte-Safe Retained Backup

Run stamp: `20260715-204246`.

`pg_dump -f` wrote the plain dump directly inside the PostgreSQL container.
The container file was checked for a positive size, plain-dump header, and
SHA-256 before `docker cp`. The host copy was then checked independently.
Only after exact size/hash equality was the container backup removed.

```text
container temp: /tmp/mes_before_canonical_v2_source_rollout_20260715-204246.sql
host retained: C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_canonical_v2_source_rollout_20260715-204246.sql
container bytes: 2881697
host bytes: 2881697
container SHA-256: 252726A3E63CBB4ED8B494ABD340BB3B7894CB459996D7B8DBD80634AAEB1535
host SHA-256: 252726A3E63CBB4ED8B494ABD340BB3B7894CB459996D7B8DBD80634AAEB1535
plain-dump header: PASS
size/hash equality: PASS
container backup removed after verification: PASS
host backup retained after final verification: PASS
```

No restore command was run.

## Migration 009 — Binding Sidecar

First apply committed successfully and created only the binding sidecar.
Every original baseline table count/digest remained unchanged.

```text
columns / constraints / indexes / rows: 9 / 9 / 4 / 0
table OID: 123460
sequence: mes.work_order_operation_route_bindings_binding_pk_seq
sequence OID: 123459
forbidden active/update/delete/effective/supersession columns: 0
base-table set: baseline + work_order_operation_route_bindings
helper count: 39
```

Ordered columns:

```text
binding_pk bigint NOT NULL default sequence
binding_id text NOT NULL
work_order_operation_id uuid NOT NULL
route_operation_id text NOT NULL
binding_source text NOT NULL
bound_by text NOT NULL
bound_at timestamptz NOT NULL default now()
metadata jsonb NOT NULL default {}
created_at timestamptz NOT NULL default now()
```

Exact constraint and index identity:

```text
ck_mes_work_order_operation_route_bindings_binding_id_nonblank
ck_mes_work_order_operation_route_bindings_bound_by_nonblank
ck_mes_work_order_operation_route_bindings_metadata_object
ck_mes_work_order_operation_route_bindings_source
fk_mes_work_order_operation_route_bindings_operation (NO ACTION)
fk_mes_work_order_operation_route_bindings_route_operation (NO ACTION)
uq_mes_work_order_operation_route_bindings_binding_id
uq_mes_work_order_operation_route_bindings_operation
work_order_operation_route_bindings_pkey
ix_mes_work_order_operation_route_bindings_route_operation
```

The checks require nonblank binding/actor identity, object metadata, and
`binding_source IN (manual_setup, work_order_release)`. The two unique
constraints cover binding ID and lifecycle UUID; the lookup index covers
route-operation ID.

Exact reapply used a new `psql -f` process. Table/sequence OIDs, ordered
columns/defaults, all constraint definitions, all index definitions, the
39-table set, row count `0`, and every original-table digest were identical
to the first-apply snapshot. Result: `PASS`, zero delta.

## Migration 010 — Release Sidecar and Route Identity

First apply committed successfully. The binding sidecar remained byte-for-byte
catalog-identical and empty.

```text
release columns / constraints / indexes / rows: 14 / 15 / 5 / 0
release table OID: 123493
release sequence: mes.work_order_route_releases_release_pk_seq
release sequence OID: 123492
forbidden mutable/history columns: 0
base-table set: baseline + both exact sidecars
helper count: 40
```

Ordered release columns:

```text
release_pk bigint NOT NULL default sequence
release_id text NOT NULL
order_id text NOT NULL
process_route_id text NOT NULL
route_code text NOT NULL
route_version integer NOT NULL
release_mode text NOT NULL
release_source text NOT NULL
released_by text NOT NULL
released_at timestamptz NOT NULL default now()
route_operation_count integer NOT NULL
operation_set_digest text NOT NULL
metadata jsonb NOT NULL default {}
created_at timestamptz NOT NULL default now()
```

Exact constraint and index identity:

```text
ck_mes_work_order_route_releases_digest
ck_mes_work_order_route_releases_metadata_object
ck_mes_work_order_route_releases_mode
ck_mes_work_order_route_releases_operation_count_positive
ck_mes_work_order_route_releases_process_route_id_nonblank
ck_mes_work_order_route_releases_release_id_nonblank
ck_mes_work_order_route_releases_released_by_nonblank
ck_mes_work_order_route_releases_route_code_nonblank
ck_mes_work_order_route_releases_route_version_positive
ck_mes_work_order_route_releases_source
fk_mes_work_order_route_releases_order (NO ACTION)
fk_mes_work_order_route_releases_route_identity (NO ACTION)
pk_mes_work_order_route_releases
uq_mes_work_order_route_releases_order_id
uq_mes_work_order_route_releases_release_id
ix_mes_work_order_route_releases_released_at
ix_mes_work_order_route_releases_route_version
```

The checks require nonblank identifiers/actor, positive version/count,
lowercase 64-character digest, JSON object metadata, allowed release modes,
and exact `local_planning` source. The route FK uses
`(process_route_id, route_code, route_version)`. The remaining three indexes
are the primary index and the unique order/release-ID indexes created for the
matching constraints.

The parent identity constraint was exact:

```text
OID: 123491
name: uq_mes_process_routes_identity_snapshot
definition: UNIQUE (route_id, route_code, version)
deferrable / initially deferred: false / false
```

Exact reapply used a new `psql -f` process. Release table/sequence OIDs,
parent-constraint OID/definition, binding catalog, ordered release catalog,
40-table set, empty sidecars, and all original-table digests remained exact.
Result: `PASS`, zero delta.

## Seed 006 — Canonical V2 Configuration

The first apply committed these exact additive rows:

```text
process_routes: INSERT 0 1
route_operations: INSERT 0 2
operation_steps: INSERT 0 4
```

Verified route and operation identity:

```text
ROUTE_BOX_PACKAGING_V2 / version 2 / PACKAGED_PRODUCT / active
ROUTE_BOX_PACKAGING_V2_OP10 / sequence 10 / ASSEMBLY_01
  ASSEMBLY_COLOR_CLASSIFY / RAW_BOX -> COLOR_CLASSIFIED_BOX
  roles input -> output_buffer / no scrap role
ROUTE_BOX_PACKAGING_V2_OP20 / sequence 20 / PACKAGING_01
  PACKAGING_FINAL / COLOR_CLASSIFIED_BOX -> PACKAGED_PRODUCT
  roles input -> output_good / scrap output_scrap
both policies: auto_close_on_required_steps
input/output quantity per cycle: 1 / 1
configured/resolved roles: 5 / 5
```

Verified steps:

```text
OP10 step 10 COLOR_SENSOR_ENTRY_EVIDENCE / auto_start -> auto_finish / sensor
OP10 step 20 ROBOT_ARM_DROP_COMPLETED / implicit_start -> auto_finish / robot
OP10 step 30 PROCESS_END_OBSERVATION / manual_start -> manual_finish / operator
OP20 step 10 PACKAGING_EXECUTION / manual_start -> manual_finish / operator
```

All four steps were active and required for completion. Exact event sources,
duration flags, actor types, and metadata were verified. There was one
process-end observation, zero legacy approval step, zero embedded approval,
two exact auto-close policies, and four active required event sources. Route,
operations, and steps carried exact seed/scenario/configuration-status
metadata.

The first verification attempt after the successful seed commit was a
read-only transaction and referenced non-existent diagnostic aliases
`input_quantity/output_quantity`. PostgreSQL rejected that verification query;
it performed no write and did not rerun the first apply. Inspection of the
reviewed schema established the actual names
`input_qty_per_cycle/output_qty_per_cycle`; the corrected read-only
repeatable-read verification then passed. This diagnostic correction did not
change source state.

Exact seed reapply used a new `psql -f` process and returned:

```text
process_routes: INSERT 0 0
route_operations: INSERT 0 0
operation_steps: INSERT 0 0
assertions: PASS
COMMIT
```

The 101-line ordered verification snapshot after reapply exactly matched the
corrected first-state snapshot. This covered the complete base-table set,
every table count/digest, sidecar and sequence OIDs, parent constraint, V1/V2
rows, exact operation/step fields, metadata, role resolution, audit counts,
and fixture count. Result: `PASS`, zero row/catalog/timestamp/digest delta.

## Established 15-Table Comparison

Digests are MD5 of ordered JSONB rows using the runbook's exact `|`
separator. The three configuration tables show only the expected additive V2
rows; the other twelve established tables are exact.

| Table | Baseline count | Baseline digest | Final count | Final digest |
| --- | ---: | --- | ---: | --- |
| `items` | 3 | `c120ee7ee8808e4280bcb02895f76e8c` | 3 | `c120ee7ee8808e4280bcb02895f76e8c` |
| `process_routes` | 1 | `163f416bfdcf16ca469e43adbd47b324` | 2 | `937e8911494bd3489f45d50e7e76e66e` |
| `route_operations` | 2 | `92a859fc57182954c5070670928c89e6` | 4 | `57e81d60c532c3ec16ba7fc312f12fcc` |
| `operation_steps` | 5 | `3829d1b0a5185a4ac59a509532b4abc8` | 9 | `b0992fc235ac795bede283fbf8130173` |
| `station_event_sources` | 4 | `c70220808f91a8562d14377c47b2a698` | 4 | `c70220808f91a8562d14377c47b2a698` |
| `work_order_operation_execution_state` | 1 | `293d69efdb273e2bd0a8e6062f930d28` | 1 | `293d69efdb273e2bd0a8e6062f930d28` |
| `work_order_operation_steps` | 3 | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` | 3 | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` |
| `operation_events` | 4 | `5bcb14870e3147f60e15cebdd146bba4` | 4 | `5bcb14870e3147f60e15cebdd146bba4` |
| `operation_approvals` | 0 | `d41d8cd98f00b204e9800998ecf8427e` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `production_flow_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `work_orders` | 12 | `283cf9b28e57bc5d6d398169f935473d` | 12 | `283cf9b28e57bc5d6d398169f935473d` |
| `work_order_operations` | 8 | `fb74f90dcb2460542ad6422609144b6f` | 8 | `fb74f90dcb2460542ad6422609144b6f` |
| `station_queue` | 13 | `2760e411b756b4194df0f86e4987cb5a` | 13 | `2760e411b756b4194df0f86e4987cb5a` |
| `locations` | 8 | `03842ba4695966bbc65a4ec3eac438e9` | 8 | `03842ba4695966bbc65a4ec3eac438e9` |
| `station_location_bindings` | 8 | `f5274a415a5d1744af064a539693d0be` | 8 | `f5274a415a5d1744af064a539693d0be` |

Retained V1 scoped digests remained exact:

```text
process route: 1 / 163f416bfdcf16ca469e43adbd47b324
route operations: 2 / 92a859fc57182954c5070670928c89e6
operation steps: 5 / 3829d1b0a5185a4ac59a509532b4abc8
```

## Final Invariants

The authoritative final set equation passed:

```text
final mes BASE TABLE set
= exact 38-table preflight set
  + work_order_operation_route_bindings
  + work_order_route_releases
```

The helper count was `40`. No third table was added. Sequences were not counted
as tables. All 35 original tables other than `process_routes`,
`route_operations`, and `operation_steps` were count/digest-identical to
preflight. Those three tables had only the exact `+1 / +2 / +4` V2 additions.
Both sidecars remained empty.

```text
retained V1: 1 / 2 / 5, exact scoped digests
Canonical V2: 1 / 2 / 4
OP10 / OP20 steps: 3 / 1
configured / resolved roles: 5 / 5
binding / release rows: 0 / 0
audit events / approvals / flow: 4 / 0 / 0
PHASE5HC-SOURCE-SMOKE fixtures: 0
PostgreSQL container: running / healthy
GET /health: 200 / {"status":"ok"}
```

The exact three staged container SQL files and the verified container backup
temp file were absent at final cleanup. The host backup remained present with
the original byte count and SHA-256. The first cleanup-verification shell
expression had a PowerShell quoting error after the exact three SQL temp files
had been removed; a corrected path-by-path check then proved all four expected
container temp paths absent. This did not access or mutate PostgreSQL.

## Acceptance and Phase Boundary

Phase 5H-B status: `PASS / APPLIED_CANONICAL_V2_SOURCE_SCHEMA_AND_SEED`.

Phase 5H-C status:
`READY_FOR_SEPARATELY_APPROVED_SOURCE_LOCAL_FUNCTIONAL_SMOKE`.

This evidence does not authorize Phase 5H-C. No source-local fixture exists.
A future functional smoke still requires separate explicit approval and must
retain the mandated nonproduction prefix/metadata and deferred analytics,
OEE, KPI, FERP, reporting, and export exclusions.

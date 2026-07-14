# Work-Order Route-Operation Binding Migration Isolated Smoke Evidence

## Summary

Result: `PASS`.

The additive binding migration was committed, applied twice only to a restored
disposable PostgreSQL clone, and rejected malformed existing schema on a
separate negative clone. The source `mes` database remained unchanged and
never received the migration.

## Phase 4C Artifact Commit

- Commit: `5c57f707c8fdb1a467fe46ed4cd17a990f76b3ec`
- Subject: `feat: add work-order route-operation binding schema`
- Migration: `db/migrations/009_work_order_operation_route_binding.sql`
- Commit scope: exactly the five reviewed Phase 4C artifacts
- Push: not performed

## Regression

- Targeted: `tests.test_mes_web_mesql_v2`
  - Result: `Ran 91 tests ... OK`
- Combined:
  - `tests.test_mes_web_station_execution_config_api`
  - `tests.test_mes_web_station_location_api`
  - `tests.test_mes_web_mesql_v2`
  - Result: `Ran 127 tests ... OK`
- Existing FastAPI `on_event` deprecation warnings were non-failing.

## Source Database

- Container: `mes_postgres`
- Host port: `5433`
- Configured database: `mes`
- Connected database guard: `mes`
- Binding table before smoke: absent
- Source migration apply: not performed

## Backup

- Host path:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_binding_schema_isolated_smoke_20260714-130347.sql`
- Byte size: `2,881,697`
- Format: plain PostgreSQL logical dump
- Header: PostgreSQL database dump header verified
- Host backup retained after clone cleanup
- Container `/tmp` copy removed after verification

## Source Baseline

All baseline queries ran inside a read-only transaction.

| Table | Count | Deterministic digest |
| --- | ---: | --- |
| `items` | 3 | `c120ee7ee8808e4280bcb02895f76e8c` |
| `process_routes` | 1 | `163f416bfdcf16ca469e43adbd47b324` |
| `route_operations` | 2 | `92a859fc57182954c5070670928c89e6` |
| `operation_steps` | 5 | `3829d1b0a5185a4ac59a509532b4abc8` |
| `station_event_sources` | 4 | `c70220808f91a8562d14377c47b2a698` |
| `work_order_operation_execution_state` | 1 | `293d69efdb273e2bd0a8e6062f930d28` |
| `work_order_operation_steps` | 3 | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` |
| `operation_events` | 4 | `5bcb14870e3147f60e15cebdd146bba4` |
| `operation_approvals` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `production_flow_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `work_orders` | 12 | `283cf9b28e57bc5d6d398169f935473d` |
| `work_order_operations` | 8 | `fb74f90dcb2460542ad6422609144b6f` |
| `station_queue` | 13 | `2760e411b756b4194df0f86e4987cb5a` |
| `locations` | 8 | `03842ba4695966bbc65a4ec3eac438e9` |
| `station_location_bindings` | 8 | `f5274a415a5d1744af064a539693d0be` |

## Retained V1 Baseline

- Work-order operation:
  `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`
- Execution status: `active`
- Current step: `OPERATOR_OBSERVATION_APPROVAL`
- Final step status: `pending`
- Events / approvals / production flow: `4 / 0 / 0`

## Isolation Strategy

- Primary clone: `mes_binding_schema_smoke_20260714_130347`
- Negative clone: `mes_binding_schema_negative_20260714_130347`
- Both databases were created from `template0` and restored from the same
  logical source dump.
- `CREATE DATABASE ... TEMPLATE mes` was not used.
- Guards required the exact task-created names and rejected `mes`.

## Primary Clone

The primary clone restored successfully. Before apply, the binding table was
absent and all 15 table counts and digests matched source.

## Primary Clone Restore Verification

- Binding table absent: PASS
- Count matches: `15/15`
- Digest matches: `15/15`

## Migration First Apply

- Guard output:
  `APPLY_DATABASE=mes_binding_schema_smoke_20260714_130347`
- `ON_ERROR_STOP=1`: enabled
- Transaction: committed
- Assertion block: PASS
- Result: PASS

## Table Verification

- Relation: `mes.work_order_operation_route_bindings`
- Relation count: `1`
- Relation kind: ordinary table (`relkind = r`)
- Partition: false
- First-apply table OID: `93552`
- Row count: `0`

## Column Verification

Exactly nine columns were present in the reviewed order:

| Position | Column | Type | Nullable | Default |
| ---: | --- | --- | --- | --- |
| 1 | `binding_pk` | `bigint` | No | sequence `nextval(...)` |
| 2 | `binding_id` | `text` | No | none |
| 3 | `work_order_operation_id` | `uuid` | No | none |
| 4 | `route_operation_id` | `text` | No | none |
| 5 | `binding_source` | `text` | No | none |
| 6 | `bound_by` | `text` | No | none |
| 7 | `bound_at` | `timestamptz` | No | `now()` |
| 8 | `metadata` | `jsonb` | No | `'{}'::jsonb` |
| 9 | `created_at` | `timestamptz` | No | `now()` |

No active, update/delete, effective-date, supersession, rebound, or version
column existed.

## Constraint Verification

Exactly nine constraints existed:

- one primary key on `binding_pk`;
- unique `binding_id`;
- unique `work_order_operation_id`;
- two foreign keys;
- nonblank `binding_id`;
- source limited to `manual_setup` and `work_order_release`;
- nonblank `bound_by`;
- object-only `metadata`.

There was no `UNIQUE(route_operation_id)` constraint.

## Foreign-Key Verification

- `work_order_operation_id` references
  `mes.work_order_operations(work_order_operation_id)`.
- `route_operation_id` references
  `mes.route_operations(route_operation_id)`.
- Both foreign keys reported delete/update action code `a` (`NO ACTION`).
- No cascade or set-null action existed.

## Index Verification

Exactly four indexes existed:

- `work_order_operation_route_bindings_pkey`: unique PK backing index;
- `uq_mes_work_order_operation_route_bindings_binding_id`: unique;
- `uq_mes_work_order_operation_route_bindings_operation`: unique;
- `ix_mes_work_order_operation_route_bindings_route_operation`: non-unique.

No duplicate lifecycle-operation index or unexpected index existed.

## Sequence and Default Verification

- Sequence:
  `mes.work_order_operation_route_bindings_binding_pk_seq`
- Sequence existed and had exactly one ownership dependency on
  `binding_pk`.
- `binding_pk` default referenced the owned sequence.
- Timestamp and metadata defaults matched the reviewed schema.

## Empty-Table Verification

- After first apply: `0` binding rows
- After reapply: `0` binding rows
- No lifecycle, config, runtime, event, approval, or flow row was created.

## Existing-Table No-Write Verification

After first apply and after reapply, all 15 existing table counts and digests
matched the source baseline exactly: `15/15 PASS` for counts and digests.

## Idempotency Reapply

- Second transaction: committed
- Table OID before/after: `93552 / 93552`
- Column digest before/after:
  `aae35eb624bf29bfbc8ac171c2170e0c`
- Constraint digest before/after:
  `a9ccceef24ff6b080a30c77743fe7a4e`
- Index digest before/after:
  `94621d107156a79adb265d68a9e2fc67`
- Column / constraint / index counts: `9 / 9 / 4`
- Sequence unchanged; no duplicate sequence, constraint, or index
- Binding rows remained `0`
- Existing-table count/digest comparison: `15/15 PASS`

## Negative Exact-Shape Test

The negative clone first received the specified malformed target containing
only `binding_pk` and `binding_id`.

Because PostgreSQL validates the migration's route-operation index expression
before entering the later `DO` assertion block, this exact two-column shape
was rejected early with `column "route_operation_id" does not exist` and exit
code `3`. It was not silently accepted or repaired.

To exercise the explicit `DO` exact-shape assertion as a separate negative
check, the empty malformed target was test-only extended with
`route_operation_id TEXT NOT NULL`; a deliberately wrong same-name index on
`binding_id` remained part of the malformed target. Reapply failed with exit
code `3` and:

```text
Binding schema assertion failed: expected 9 columns
```

The malformed target remained three columns, two constraints, three indexes,
and zero rows. The migration did not repair it. All 15 restored existing
tables retained their original counts and digests.

No standalone negative-test setup SQL file or executable repository artifact
was saved or committed.

## Clone Cleanup

- Primary clone dropped: yes
- Negative clone dropped: yes
- Exact task-created databases remaining: `0`
- Databases matching either task prefix remaining: `0`
- Source `mes` was never a cleanup target.

## Source Final Integrity

- Source binding table after cleanup: absent
- Final count comparison: `15/15 PASS`
- Final digest comparison: `15/15 PASS`
- Retained execution: `active`
- Retained current/final step:
  `OPERATOR_OBSERVATION_APPROVAL / pending`
- Events / approvals / production flow: `4 / 0 / 0`
- Unintended source mutation: none detected

## Health

- Endpoint: `http://127.0.0.1:8080/health`
- Result: `{"status":"ok"}`
- Container rebuild, recreate, restart, down, or volume operation: none

## Guardrails

- Source `mes` received read-only baseline and integrity queries only.
- Migration applied only to the disposable primary clone.
- Negative malformed-schema writes occurred only in the negative clone.
- No binding row or legacy backfill was created.
- No Python, test, helper, runtime-init, work-order release, lifecycle, config,
  runtime, API/Kiosk/IoT/OEE, approval, production-flow, inventory, MESQL, or
  FERP implementation changed.
- No push was performed.
- `.agents/` was not read, listed, searched, or changed.

## Result

`PASS`

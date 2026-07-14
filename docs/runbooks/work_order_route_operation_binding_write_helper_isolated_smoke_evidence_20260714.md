# Work-Order Route-Operation Binding Write Helper Isolated Smoke Evidence

## Summary

- Date: `2026-07-14`.
- Result: `PASS`.
- The controlled immutable binding write helper was committed after static and
  unit-regression acceptance.
- All real PostgreSQL writes and errors were exercised only on disposable
  clone `mes_binding_write_smoke_20260714_140320`.
- Source database `mes` received no migration, binding helper call, or binding
  row.

## Implementation Commit

- Commit:
  `d67a3fb feat: add controlled work-order route-operation binding writes`.
- Committed files:
  - `mes_web/db/mesql_v2.py`
  - `tests/test_mes_web_mesql_v2.py`
- Public helper: `create_work_order_operation_route_binding`.
- SQL constant: `INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL`.
- The existing two public binding read-helper contracts were preserved.
- Exactly one public binding write helper exists; no update, delete, rebind,
  bulk, runtime resolver, release helper, API endpoint, or feature flag was
  added.
- Push: not performed.

## Regression

- Targeted `tests.test_mes_web_mesql_v2`: `143` tests, `OK`.
- Combined station-execution-config API, station-location API, and MESQL V2:
  `179` tests, `OK`.
- `git diff --check` for the implementation/test paths: `PASS`.
- Insert SQL has six explicit parameters, nine explicit returning columns,
  `ON CONFLICT DO NOTHING`, and no update/delete/merge/truncate or inference.

## Source Database

- Container: `mes_postgres`.
- Database: `mes`.
- Host port: `5433`.
- Source binding table before smoke: absent.
- Source helper calls: none.

## Backup

- Logical backup:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_binding_write_helper_isolated_smoke_20260714-140320.sql`.
- Size: `2,881,697` bytes.
- PostgreSQL database-dump header: present.
- Password was obtained without terminal output.
- Host backup was preserved after clone cleanup.

## Source Baseline

The source baseline was captured in a read-only transaction using the required
deterministic JSONB digest expression.

| Table | Count | MD5 digest |
|---|---:|---|
| `mes.items` | 3 | `c120ee7ee8808e4280bcb02895f76e8c` |
| `mes.process_routes` | 1 | `163f416bfdcf16ca469e43adbd47b324` |
| `mes.route_operations` | 2 | `92a859fc57182954c5070670928c89e6` |
| `mes.operation_steps` | 5 | `3829d1b0a5185a4ac59a509532b4abc8` |
| `mes.station_event_sources` | 4 | `c70220808f91a8562d14377c47b2a698` |
| `mes.work_order_operation_execution_state` | 1 | `293d69efdb273e2bd0a8e6062f930d28` |
| `mes.work_order_operation_steps` | 3 | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` |
| `mes.operation_events` | 4 | `5bcb14870e3147f60e15cebdd146bba4` |
| `mes.operation_approvals` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.production_flow_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.work_orders` | 12 | `283cf9b28e57bc5d6d398169f935473d` |
| `mes.work_order_operations` | 8 | `fb74f90dcb2460542ad6422609144b6f` |
| `mes.station_queue` | 13 | `2760e411b756b4194df0f86e4987cb5a` |
| `mes.locations` | 8 | `03842ba4695966bbc65a4ec3eac438e9` |
| `mes.station_location_bindings` | 8 | `f5274a415a5d1744af064a539693d0be` |

## Retained V1 Baseline

- Work-order operation:
  `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`.
- Execution status: `active`.
- Current step: `OPERATOR_OBSERVATION_APPROVAL`.
- Final step status: `pending`.
- Event / approval / production-flow counts: `4 / 0 / 0`.

## Isolation Strategy

- Clone: `mes_binding_write_smoke_20260714_140320`.
- The exact name was guarded by the `mes_binding_write_smoke_` prefix,
  equality with the task-created name, and `database != mes` checks.
- The clone was created empty from `template0` and restored from the source
  logical dump. `TEMPLATE mes` was not used.
- Migration and every real helper call targeted only the exact clone.

## Clone Restore Verification

- Restore completed with `ON_ERROR_STOP=1`.
- Binding table before migration: absent.
- Existing-table count equality: `15/15`.
- Existing-table digest equality: `15/15`.

## Pre-Migration Missing-Table Test

- Valid operation UUID:
  `3dec8371-d01d-401e-a435-f441d7701e21`.
- Valid route operation: `ROUTE_BOX_PACKAGING_V1_OP10`.
- Helper: `create_work_order_operation_route_binding`.
- Propagated exception: `psycopg.errors.UndefinedTable`.
- SQLSTATE: `42P01`.
- The exception was not converted to a binding conflict and no
  `created=false` replay result was returned.

## Migration Apply

- Apply database: `mes_binding_write_smoke_20260714_140320` only.
- Migration: `db/migrations/009_work_order_operation_route_binding.sql`.
- Transaction commit and embedded exact-shape assertion: `PASS`.
- Table exists: `true`.
- Columns / constraints / indexes: `9 / 9 / 4`.
- Initial binding rows: `0`.

## Candidate Selection

Three existing lifecycle operations met the required no-binding,
no-execution-state, and no-event criteria:

| Candidate | Work order | Operation UUID | Station | Operation code | Sequence | Status |
|---|---|---|---|---|---:|---|
| A | `WO-LOCAL-SUCCESSOR-SMOKE-78d8c903` | `3ebd0c44-bb62-4939-a9b5-2f3b2ce6ba1d` | `ASSEMBLY_01` | `OP-ASSEMBLY` | 10 | `completed` |
| B | `WO-LOCAL-SUCCESSOR-SMOKE-6d64de50` | `5cc64ece-b191-4d54-a788-3c9161d783f4` | `ASSEMBLY_01` | `OP-ASSEMBLY` | 10 | `completed` |
| C | `WO-TEST-003` | `6e1c8980-1fff-4de8-8b91-e3364cdecdbd` | `ASSEMBLY_01` | `OP-MVP-ASM` | 1 | `active` |

- The retained V1 operation was excluded.
- No lifecycle/work-order/operation fixture was created and no operation status
  was changed.

## Route-Operation Targets

- `ROUTE_BOX_PACKAGING_V1_OP10`: present.
- `ROUTE_BOX_PACKAGING_V1_OP20`: present.
- The clone-only bindings do not establish an accepted production semantic
  mapping between the selected legacy lifecycle operations and V1 route
  operations.
- V2 seed was not applied.

## Binding A First Insert

- Binding ID: `BINDING-WRITE-SMOKE-A-20260714-001`.
- Candidate A / route target: `3ebd0c44-bb62-4939-a9b5-2f3b2ce6ba1d` /
  `ROUTE_BOX_PACKAGING_V1_OP10`.
- Source / actor: `manual_setup` / `SMOKE_TEST`.
- Result: `created=true`.
- Binding PK: `1`.
- Binding row count: `1`.
- Binding digest: `699e77445bf5320230082a016ea5b1fa`.
- Returned fields: exact `9/9`; UUID string and metadata matched.
- `bound_at` and `created_at`:
  `2026-07-14T11:05:57.492679+00:00`, valid ISO strings.

## Binding A Exact Replay

- Result: `created=false`; no exception.
- Returned row equaled the first result across all nine fields.
- Binding PK remained `1`.
- Timestamps and metadata were unchanged.
- Binding row count/digest remained
  `1 / 699e77445bf5320230082a016ea5b1fa`.

## Immutable Conflict Verification

All cases returned `409 WORK_ORDER_OPERATION_ROUTE_BINDING_CONFLICT`, never a
`created=false` replay:

- Same operation with different binding ID: PASS.
- Same IDs with different route operation: PASS.
- Same IDs with different metadata: PASS.
- Same IDs with `work_order_release`: PASS.
- Same IDs with `OTHER_ACTOR`: PASS.
- After each case, binding row count/digest remained
  `1 / 699e77445bf5320230082a016ea5b1fa`.

## Binding-ID Reuse Conflict

- Binding A ID was requested for still-unbound candidate B.
- Result: `409 WORK_ORDER_OPERATION_ROUTE_BINDING_CONFLICT`.
- Candidate B remained unbound.
- Binding count/digest remained
  `1 / 699e77445bf5320230082a016ea5b1fa`.

## Binding B First Insert

- Binding ID: `BINDING-WRITE-SMOKE-B-20260714-001`.
- Candidate B / route target: `5cc64ece-b191-4d54-a788-3c9161d783f4` /
  `ROUTE_BOX_PACKAGING_V1_OP20`.
- Source / actor: `work_order_release` / `SMOKE_TEST`.
- Result: `created=true`.
- Binding PK: `9`.
- Binding row count: `2`.
- Metadata matched exactly.
- The PK gap reflects normal PostgreSQL sequence consumption by rejected
  `INSERT ... ON CONFLICT DO NOTHING` attempts; no extra binding row existed.

## Binding B Exact Replay

- Result: `created=false`; no exception.
- Returned row equaled the first Binding B result across all nine fields.
- Binding PK remained `9`.
- `bound_at` and `created_at` remained
  `2026-07-14T11:05:58.020741+00:00`.
- Metadata and binding row count remained unchanged.

## Crossed Unique Collision

- Request used Binding A ID with candidate B and Binding B's other controlled
  values.
- Result: `409 WORK_ORDER_OPERATION_ROUTE_BINDING_CONFLICT`.
- Safe conflict detail available from current `MesqlV2Error`: error code only;
  no separate `conflict_on` value is exposed.
- Binding A and Binding B rows remained unchanged.
- Binding count/digest remained
  `2 / 9d3d4360f8352dd586f706f99857e343`.

## Missing Lifecycle Parent FK

- Missing valid UUID: `00000000-0000-0000-0000-000000000001`.
- Pre-check confirmed it was absent.
- Exception: `psycopg.errors.ForeignKeyViolation`.
- SQLSTATE: `23503`.
- The error was not converted to a 409 conflict or replay result.
- No partial binding row was present; count/digest remained unchanged.

## Missing Route-Operation Parent FK

- Candidate C was still unbound.
- Missing route: `ROUTE_OPERATION_NOT_FOUND_FOR_SMOKE`.
- Pre-check confirmed the route was absent.
- Exception: `psycopg.errors.ForeignKeyViolation`.
- SQLSTATE: `23503`.
- The error was not converted to a 409 conflict or replay result.
- Candidate C remained unbound; no partial row was present.

## Post-Error Transaction Recovery

- Binding A exact replay after conflict/FK errors: `created=false`, exact row.
- Binding B exact replay after conflict/FK errors: `created=false`, exact row.
- No failed-transaction state leaked into new helper calls.

## Binding-Table Integrity

- Snapshot before crossed/FK/post-error calls:
  `2 / 9d3d4360f8352dd586f706f99857e343`.
- Snapshot after all calls:
  `2 / 9d3d4360f8352dd586f706f99857e343`.
- Successful binding rows: exactly A and B.
- Row mutations outside the two successful inserts: `0`.

## Existing-Table No-Write Verification

- Existing-table counts: `15/15` unchanged.
- Existing-table digests: `15/15` unchanged.
- Candidate A/B/C execution-state / runtime-step / event / approval /
  production-flow counts: each `0 / 0 / 0 / 0 / 0`.
- No lifecycle, work-order, operation, queue, configuration, event, approval,
  production-flow, item, route, or location row changed.

## Clone Cleanup

- Exact clone connections were terminated.
- Clone `mes_binding_write_smoke_20260714_140320` was dropped.
- Remaining databases matching `mes_binding_write_smoke_%`: none.
- Container `/tmp` dump was removed; host backup was preserved.

## Source Final Integrity

- Final verification used a new source read-only transaction.
- Source binding table exists: `false`.
- Baseline/final counts: `15/15` equal.
- Baseline/final digests: `15/15` equal.
- Retained V1 remained `active` at
  `OPERATOR_OBSERVATION_APPROVAL`, final step `pending`, with event / approval /
  production-flow counts `4 / 0 / 0`.
- Unintended source mutation: `0`.

## Health

- `GET http://127.0.0.1:8080/health`: `status=ok`.
- No container rebuild, recreate, restart, down, or volume operation was used.

## Guardrails

- The clone-only bindings were created to verify write-helper behavior.
  They do not establish accepted production semantic mappings.
- No source migration/helper/row, lifecycle fixture, work-order/operation
  insert, status mutation, V2 seed, runtime-init/release integration,
  inference, step execution, API/Kiosk/IoT/Observer/OEE, approval,
  production-flow, inventory, MESQL, or FERP operation occurred.
- No concurrency stress test was performed.
- Evidence and `CURRENT_STATE.md` were not committed. No push was performed.
- `.agents/` was not read, listed, searched, or changed.

## Result

`PASS`

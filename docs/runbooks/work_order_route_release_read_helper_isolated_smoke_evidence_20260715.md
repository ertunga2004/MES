# Work-Order Route-Release Read Helper Isolated Smoke Evidence

## Summary

- Date: `2026-07-15`.
- Result: `PASS`.
- Reviewed implementation commit:
  `a3e611adacf5cd23d2c120eb620a63769b3a6542` (`a3e611a`, Phase 5C).
- The five public read helpers and deterministic identity utilities passed
  isolated PostgreSQL verification against a disposable logical-dump clone.
- Source database `mes` remained unchanged. No release writer, API,
  completion bridge, migration, seed, or helper call ran against source.

## Focused Review

- Commit `a3e611a` contains only:
  - `mes_web/db/mesql_v2.py`
  - `tests/test_mes_web_mesql_v2.py`
- Review result: no actionable P1, P2, or P3 findings.
- Read SQL is explicit, parameterized, and read-only. Snapshot binding scope is
  lifecycle-UUID/work-order based, initial queue scope is the first persisted
  lifecycle operation, and exact route/version reads contain no latest/active
  fallback or route-operation inference.
- Existing binding/runtime helpers showed no focused regression signal.
- Accepted risk: the read model intentionally preserves incomplete snapshots;
  completeness classification and the write/release boundary remain deferred.

## Repository and Regression

- Baseline: `HEAD == main == origin/main == a3e611a`; initial tree clean.
- Targeted `tests.test_mes_web_mesql_v2`: `227` tests, `OK`.
- Combined station-execution config, station-location, and MESQL V2 suite:
  `263` tests, `OK`.
- `py_compile mes_web/db/mesql_v2.py`: PASS.
- Commit diff check: PASS; only the two implementation-commit paths above.
- Only the pre-existing FastAPI `on_event` deprecation warnings were observed.

## Source and Backup

- Container/database/user: `mes_postgres` / `mes` / `mes`.
- PostgreSQL: `16.14`; host port `5433`; container remained healthy.
- Backup:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_route_release_read_smoke_20260715-123730.sql`.
- Backup size: `2,886,710` bytes; plain PostgreSQL dump header present; no
  password was printed. Backup was retained after cleanup.

## Source Baseline

The baseline was captured in a repeatable-read, read-only transaction using
deterministic `to_jsonb` row ordering.

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

Extended source baseline:

- Release table: absent.
- Binding table: absent.
- `uq_mes_process_routes_identity_snapshot`: absent.
- Canonical V2 route count: `0`.
- Retained V1 operation
  `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`:
  `active / OPERATOR_OBSERVATION_APPROVAL / pending`.
- Retained events / approvals / production flow: `4 / 0 / 0`.

## Disposable Clone and Prerequisites

- Clone: `mes_route_release_read_smoke_20260715_123730`.
- Creation path: empty database from `template0`, then logical dump restore;
  `TEMPLATE mes` was not used.
- Restore equality: `15/15` table counts and `15/15` table digests.
- Extended release/binding/constraint/V2/retained-V1 state also matched source.
- Every mutation used an exact clone-name guard and rejected database `mes`.

Before migration `010`, the real helper call
`get_work_order_route_release(config, "WO-READ-SMOKE-MISSING-TABLE")` raised
`psycopg.errors.UndefinedTable` with SQLSTATE `42P01`. The error was neither
masked as `None` nor converted to domain not-found behavior.

Clone-only applies, in order:

1. `009_work_order_operation_route_binding.sql`
2. `010_work_order_route_release.sql`
3. `006_station_execution_seed_canonical_v2.sql`

Verified results:

- Binding columns / constraints / indexes: `9 / 9 / 4`.
- Release columns / constraints / indexes: `14 / 15 / 5`.
- V2 route / operations / steps: `1 / 2 / 4`.
- OP10 / OP20 steps: `3 / 1`.
- Configured / resolved location roles: `5 / 5`.

## Deterministic Utilities

- Operation namespace label/UUID recomputation:
  `urn:mes:work-order-route-release:operation:v1` /
  `51e8ce07-9395-54f4-9677-a32d03162cdc`: PASS.
- Binding namespace label/UUID recomputation:
  `urn:mes:work-order-route-release:binding:v1` /
  `2e5192a2-5d5a-5f76-a9f6-dc70df96564a`: PASS.
- Fixed operation UUIDs:
  - OP10: `5258d822-55bd-56b1-81ba-7f89193ba4eb`
  - OP20: `26c50f67-2519-5e29-a958-e39eca44934e`
- Fixed binding IDs:
  - `BINDING-WORK-ORDER-RELEASE-AD8E94BA-E408-59B5-BE90-B7F348C17050`
  - `BINDING-WORK-ORDER-RELEASE-B342D41D-6777-5999-A07E-CE10E04533CA`
- Canonical name contained exactly one LF byte, no trailing LF, and no literal
  backslash-plus-`n` pair.
- Fixed digest:
  `4063a5c72fd4d38f11757a4bf1115f83e1c05e8b97624deb808193c5d0fcb2e2`.
- Repeated calls were byte-identical; caller pair order/data was unchanged.
- Utility execution was instrumented to reject a DB connection; none occurred.

## Clone-Only Fixtures

- Complete work order:
  `WO-ROUTE-RELEASE-READ-SMOKE-20260715-123730`.
- Complete release: `RELEASE-V2-EXAMPLE-001`.
- Exact persisted route: `ROUTE_BOX_PACKAGING_V2`, version `2`.
- Lifecycle operations: fixed OP10/OP20 UUIDs at sequence `10 / 20`, stations
  `ASSEMBLY_01 / PACKAGING_01`, statuses `queued / planned`.
- Bindings used the fixed IDs and `binding_source=work_order_release`.
- Initial queue contained only the OP10 lifecycle UUID.
- Foreign work order:
  `WO-ROUTE-RELEASE-FOREIGN-20260715-123730`, with a distinct lifecycle UUID
  bound to the same V2 OP10 definition.
- Incomplete work order/release:
  `WO-ROUTE-RELEASE-INCOMPLETE-20260715-123730` /
  `RELEASE-READ-INCOMPLETE-20260715-123730`, with no lifecycle operation,
  binding, or queue.
- All fixture metadata declared `disposable_clone_only=true` and
  `production_release=false`. Inserts were direct clone-only SQL, not a writer.

## Release and Route Reads

- `get_work_order_route_release`: exact release and exact 14-field shape.
- `get_work_order_route_release_by_id`: same PK/row/timestamps.
- Lowercase case-mismatched release ID: `None`.
- Metadata mapped as a dictionary; `released_at` and `created_at` mapped to
  timezone-aware ISO strings.
- `get_exact_process_route(..., "ROUTE_BOX_PACKAGING_V2", 2)`: exact V2 row.
- Version `999`: `None`; V1/latest/active fallback was absent.
- `list_process_route_operations`: exact OP10 then OP20 order.
- Missing process route: `[]`; route-operation inference was absent.

## Snapshot Verification

Complete snapshot:

- Top-level shape: release, work order, operations, bindings, initial queue.
- Work-order shape: exact `8` fields.
- Lifecycle operation shape: exact `14` fields; order `10, 20`.
- Binding order followed lifecycle order; exactly the complete work order's
  OP10/OP20 lifecycle UUIDs were returned.
- The foreign work-order binding to the same V2 OP10 definition was excluded,
  proving work-order/lifecycle-UUID scoping rather than route/station/sequence
  inference.
- Initial queue was the exact OP10 lifecycle UUID, order ID, and
  `ASSEMBLY_01` station; OP20 was not selected.

Incomplete snapshot:

- Release retained: yes.
- Work order retained: yes.
- Operations: `[]`.
- Bindings: `[]`.
- Initial queue: `None`.
- No completeness conflict was synthesized and no inner join lost the release.

## Repeated Read and No-Write

- Release, work-order, lifecycle-operation, binding, queue, runtime, step,
  event, approval, production-flow, config/master, and location state was
  captured across `17` tables before and after helper calls.
- Count/digest equality: `17/17`; timestamps therefore remained unchanged.
- All five helper results were identical on repeated reads.
- Instrumented full snapshot: exactly `1` connection, `1` cursor, `0` commit
  calls.
- Write/commit-side mutation: absent.

## Cleanup and Source Final Integrity

- Exact clone sessions terminated: `0` active sessions required termination.
- Exact clone dropped; matching database prefix count: `0`.
- Backup retained at `2,886,710` bytes.
- Final source table counts equal baseline: `15/15`.
- Final source table digests equal baseline: `15/15`.
- Release table, binding table, parent route snapshot constraint, and V2 route
  count remained `absent / absent / 0 / 0`.
- Retained V1 state and `4 / 0 / 0` audit counts remained unchanged.
- All three clone-only work-order IDs were absent from source; source release
  relation remained absent, so clone-only release IDs were absent as well.
- Health: HTTP `200`, `status=ok`.

## Guardrails

- No source mutation, source helper call, source migration, source seed, or
  source fixture.
- No writer, API, release execution, inference, completion bridge, FERP,
  MESQL, Kiosk, IoT/OEE, approval, production-flow, or inventory action.
- No Docker rebuild, recreate, restart, down, or volume action.
- No implementation change, stage, commit, or push.
- `.agents/` was not accessed.

## Result

`PASS`

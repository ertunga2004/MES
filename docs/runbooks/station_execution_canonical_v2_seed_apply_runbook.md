# Station Execution Canonical V2 Seed Apply Runbook

## Purpose

Apply and verify the additive canonical V2 station-execution configuration
defined in:

```text
db/migrations/006_station_execution_seed_canonical_v2.sql
```

The target is a new active route/config version only. The runbook must not
rename, edit, deactivate, or delete V1 data, and it must not create runtime,
event, approval, production-flow, lifecycle, or inventory state.

This runbook is a future procedure. It was not executed when the SQL draft was
created.

Status terminology:

- Repository artifact: reviewed seed draft, not applied to source DB.
- Inserted row metadata: `configuration_status = canonical_v2`.

The row metadata identifies the canonical configuration and must not retain a
repository-review `draft` status after a future approved apply.

## Preconditions

- Use local MES PostgreSQL only after explicit apply approval.
- Confirm the target database name and print it before any apply command.
- Confirm repository files and Git status are understood.
- Confirm migrations `004_station_execution_schema.sql` and
  `005_station_execution_seed_minimal.sql` match the reviewed versions.
- Confirm the canonical draft has passed the Static SQL Review section.
- Confirm source items exist and are active:
  - `RAW_BOX`
  - `COLOR_CLASSIFIED_BOX`
  - `PACKAGED_PRODUCT`
- Confirm stations `ASSEMBLY_01` and `PACKAGING_01` exist and are active.
- Confirm required station event sources exist and are active:
  - `ASSEMBLY_01 / COLOR_SENSOR_ENTRY`
  - `ASSEMBLY_01 / ROBOT_ARM_DROP`
  - `ASSEMBLY_01 / KIOSK_OPERATOR`
  - `PACKAGING_01 / KIOSK_OPERATOR`
- Confirm the required active station/location roles resolve for input,
  output, and scrap semantics.
- Stop if any precondition is uncertain. Do not improvise schema or seed
  changes.

## Source Baseline

Record counts and deterministic row digests before apply for:

Configuration/master tables:

```text
mes.items
mes.process_routes
mes.route_operations
mes.operation_steps
mes.station_event_sources
```

Runtime and audit tables:

```text
mes.work_order_operation_execution_state
mes.work_order_operation_steps
mes.operation_events
mes.operation_approvals
mes.production_flow_events
```

Lifecycle and location tables:

```text
mes.work_orders
mes.work_order_operations
mes.station_queue
mes.locations
mes.station_location_bindings
```

Use the same deterministic digest method before and after:

```sql
md5(
    COALESCE(
        string_agg(
            to_jsonb(t)::text,
            '|'
            ORDER BY to_jsonb(t)::text
        ),
        ''
    )
)
```

Also capture V1-specific counts:

```sql
SELECT count(*)
FROM mes.process_routes
WHERE route_code = 'ROUTE_BOX_PACKAGING_V1'
  AND version = 1;

SELECT count(*)
FROM mes.route_operations
WHERE route_code = 'ROUTE_BOX_PACKAGING_V1'
  AND route_version = 1;

SELECT count(*)
FROM mes.operation_steps s
JOIN mes.route_operations ro
  ON ro.route_operation_id = s.route_operation_id
WHERE ro.route_code = 'ROUTE_BOX_PACKAGING_V1'
  AND ro.route_version = 1;
```

Expected reviewed baseline: one V1 route, two V1 route operations, and five V1
steps. If actual values differ, stop and review before apply.

## Backup

Before apply:

1. Generate a unique timestamp.
2. Run `pg_dump` against the exact target database.
3. Copy the logical dump to the approved host backup directory.
4. Verify the file exists, has nonzero size, and contains the PostgreSQL dump
   header.
5. Record the full path and byte size in apply evidence.
6. Do not print database passwords.
7. Keep the host backup after verification.

Do not proceed if backup verification fails.

## Static SQL Review

Review the exact draft and confirm:

- It is wrapped by `BEGIN` and `COMMIT`.
- It inserts only into:
  - `mes.process_routes`
  - `mes.route_operations`
  - `mes.operation_steps`
- It contains no write to V1 rows.
- It contains no write to item, station, event-source, location, runtime, audit,
  lifecycle, or inventory tables.
- It contains no destructive DDL or DML.
- It contains no conflict branch that changes an existing row.
- It uses `INSERT ... SELECT ... WHERE NOT EXISTS`.
- Existing conflicting V2 rows are followed by exact-shape verification so a
  wrong row causes transaction failure.
- It creates exactly one V2 route, two V2 route operations, and four V2 steps.
- Both V2 operations use `auto_close_on_required_steps`.
- No step embeds approval.
- No quality-control route operation is included.
- Route and config rows are `active=true` because every current selection path
  is explicit; no automatic latest-active route selection was found.
- Work-order selection for V2 is still outside this apply.

## V1 Preservation Checks

Before and after apply, compare:

- V1 route count and digest.
- V1 route-operation count and digest.
- V1 operation-step count and digest.
- Retained V1 runtime execution state and step rows.
- V1 operation-event ledger rows.

The V1 route must remain active and unchanged. No V1 row may be renamed,
deactivated, deleted, or rebound.

## Apply Command

Run only after backup and explicit approval:

```powershell
Get-Content -LiteralPath `
  'db/migrations/006_station_execution_seed_canonical_v2.sql' -Raw |
  docker exec -i mes_postgres sh -c `
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d mes'
```

Replace the database name only when the approved target is intentionally
different. Print and verify the target database name immediately before apply.

The SQL's assertion block must complete and the transaction must commit. Any
assertion or SQL error is a FAIL; do not partially repair rows manually.

## V2 Route Verification

Expected route:

```text
route_id = ROUTE_BOX_PACKAGING_V2
route_code = ROUTE_BOX_PACKAGING_V2
version = 2
item_code = PACKAGED_PRODUCT
active = true
source_system = local_seed
```

Expected V2 route count: `1`.

Verify there is no automatic selection side effect. The current read path uses
explicit `route_code + version`; runtime initialization uses explicit
`route_operation_id`.

## V2 Operation Verification

Expected operations:

```text
ROUTE_BOX_PACKAGING_V2_OP10
sequence_no = 10
operation_code = ASSEMBLY_COLOR_CLASSIFY
station_code = ASSEMBLY_01
input_location_role = input
output_location_role = output_buffer
scrap_location_role = null
policy = auto_close_on_required_steps
active = true
```

```text
ROUTE_BOX_PACKAGING_V2_OP20
sequence_no = 20
operation_code = PACKAGING_FINAL
station_code = PACKAGING_01
input_location_role = input
output_location_role = output_good
scrap_location_role = output_scrap
policy = auto_close_on_required_steps
active = true
```

Verify:

- V2 route-operation count is `2`.
- Sequence numbers are unique under the V2 route.
- Operation codes are unique under `(route_code, route_version)`.
- Input/output items, quantities, and location roles match the reviewed SQL.
- No additional route operation exists.

## V2 Step Verification

Expected OP10 steps:

```text
10 COLOR_SENSOR_ENTRY_EVIDENCE
   auto_start + auto_finish
   sensor
   required=true records_duration=false embedded_approval=false

20 ROBOT_ARM_DROP_COMPLETED
   implicit_start + auto_finish
   robot
   required=true records_duration=true embedded_approval=false

30 PROCESS_END_OBSERVATION
   manual_start + manual_finish
   operator
   required=true records_duration=true embedded_approval=false
```

Expected OP20 step:

```text
10 PACKAGING_EXECUTION
   manual_start + manual_finish
   operator
   required=true records_duration=true embedded_approval=false
```

Verify:

- Total V2 step count is `4`.
- OP10 count is `3`.
- OP20 count is `1`.
- Step number and step code are unique per route operation.
- `PROCESS_END_OBSERVATION` occurs once under V2 OP10.
- Every V2 step has `approval_required_after_finish=false`.
- No legacy combined approval step exists under V2.

## Event-Source Verification

Use read-only queries to confirm all configured source codes resolve under the
operation station and are active:

```text
ASSEMBLY_01:
- COLOR_SENSOR_ENTRY
- ROBOT_ARM_DROP
- KIOSK_OPERATOR

PACKAGING_01:
- KIOSK_OPERATOR
```

Confirm:

- Auto-start and auto-finish steps have the required source.
- Manual start/finish steps use the station Kiosk source.
- No duplicate station event source was inserted by the V2 seed.

## Location-Role Verification

Resolve every role with active binding and active location, honoring optional
item and operation scopes:

```text
ASSEMBLY_01:
- input / RAW_BOX / ASSEMBLY_COLOR_CLASSIFY
- output_buffer / COLOR_CLASSIFIED_BOX / ASSEMBLY_COLOR_CLASSIFY

PACKAGING_01:
- input / COLOR_CLASSIFIED_BOX / PACKAGING_FINAL
- output_good / PACKAGED_PRODUCT / PACKAGING_FINAL
- output_scrap / PACKAGED_PRODUCT / PACKAGING_FINAL
```

`scrap_location_role` is an optional, nullable operation capability. An active
station/location binding is required only when the configured scrap role is
non-null. Do not create an `ASSEMBLY_01/output_scrap` binding for OP10.

The V2 seed must not insert or change locations or bindings.

## Idempotency Reapply

After the first apply passes:

1. Capture V2 route/config counts and digests.
2. Re-run the exact same SQL.
3. Require a successful transaction.
4. Re-capture counts and digests.
5. Confirm every V1 and V2 count/digest is unchanged.
6. Confirm runtime/audit/lifecycle/location counts and digests are unchanged.

If an existing V2 row has the right key but wrong shape, the SQL must fail its
assertion rather than silently accepting or changing the row.

## Runtime Tables No-Write Check

Before and after first apply and idempotency reapply, require exact count and
digest equality for:

```text
mes.work_order_operation_execution_state
mes.work_order_operation_steps
mes.operation_events
mes.operation_approvals
mes.production_flow_events
```

No runtime initialization or step helper may be called as part of seed apply.

## Lifecycle No-Write Check

Before and after first apply and idempotency reapply, require exact count and
digest equality for:

```text
mes.work_orders
mes.work_order_operations
mes.station_queue
mes.locations
mes.station_location_bindings
```

No work-order selection, release, activation, close, production-flow, or
inventory action is part of this runbook.

## Health

After all SQL and digest checks:

```powershell
curl.exe -s http://127.0.0.1:8080/health
```

Require `status=ok`. Do not rebuild or recreate containers for health
verification.

## Rollback Strategy

Do not include or run automatic destructive rollback SQL.

- Primary recovery is restore from the verified pre-apply backup.
- If V2 has created no runtime instance, a separately reviewed and explicitly
  approved compensating deactivation may be considered.
- If any V2 runtime instance exists, do not delete or rename config/runtime
  rows.
- Return future work-order selection to the prior valid config through explicit
  selection policy.
- Preserve all historical runtime, event, and audit rows.
- Record any rollback as a separate evidence-backed task.

## PASS Criteria

PASS only when:

- Backup is verified.
- Static SQL review passes.
- First apply commits without error.
- V1 rows are unchanged.
- V2 exact-shape assertions pass.
- V2 counts are `1 route / 2 operations / 4 steps`.
- Both policies are `auto_close_on_required_steps`.
- Event-source and location-role checks pass.
- Runtime, audit, lifecycle, and location tables are digest-identical.
- Idempotency reapply produces no change.
- Health is `ok`.
- No runtime or work-order instance is created or rebound.

## FAIL Criteria

Report FAIL and stop when any of these occur:

- Backup, SQL, or assertion failure.
- Unexpected target database.
- V1 count or digest change.
- Wrong or conflicting V2 row.
- Missing/inactive event source or location role.
- Unexpected runtime/audit/lifecycle/location mutation.
- Idempotency reapply changes any row.
- Health failure.
- Any unapproved schema, seed, route-selection, runtime, or lifecycle action.

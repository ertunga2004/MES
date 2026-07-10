# Station Execution Completion Policy Isolated Smoke Evidence

## Summary

Runtime Engine V0 Phase 3B isolated PostgreSQL smoke PASS on 2026-07-10.
The committed `finish_execution_step` implementation applied all three
completion policies atomically with the triggering `step_finish` event on
dump/restore-based disposable clones. The source `mes` database was read only
for backup and integrity verification and remained unchanged.

## Implementation Commit

- `e4be6ac feat: apply station execution completion policies`
- Committed files:
  - `mes_web/db/mesql_v2.py`
  - `tests/test_mes_web_mesql_v2.py`
- Targeted regression: `Ran 91 tests ... OK`.
- Combined regression: `Ran 127 tests ... OK`.
- Push was not performed.

## Source Database

- Source database: `mes`.
- PostgreSQL container: `mes_postgres`.
- Host connection port: `5433`.
- Retained work-order operation:
  `c8f0be13-9dc7-4e66-9fbb-43547a5f1808`.
- No runtime helper was called with `MES_WEB_DB_NAME=mes`.
- Source access after the dump was limited to SELECT-based count, digest, and
  retained-runtime verification.

## Backup

- Host path:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_completion_policy_isolated_smoke_20260710-133519.sql`.
- Byte size: `2886710`.
- Dump header contained `PostgreSQL database dump`.
- Container temporary path:
  `/tmp/mes_before_completion_policy_isolated_smoke_20260710-133519.sql`.
- The container temporary dump was removed after clone cleanup.
- The host backup was retained.

## Source Baseline Counts

| Table | Row count |
| --- | ---: |
| `items` | 3 |
| `process_routes` | 1 |
| `route_operations` | 2 |
| `operation_steps` | 5 |
| `station_event_sources` | 4 |
| `work_order_operation_execution_state` | 1 |
| `work_order_operation_steps` | 3 |
| `operation_events` | 4 |
| `operation_approvals` | 0 |
| `production_flow_events` | 0 |
| `work_orders` | 12 |
| `work_order_operations` | 8 |
| `station_queue` | 13 |
| `locations` | 8 |
| `station_location_bindings` | 8 |

## Source Baseline Digests

| Table | MD5 row digest |
| --- | --- |
| `items` | `c120ee7ee8808e4280bcb02895f76e8c` |
| `process_routes` | `163f416bfdcf16ca469e43adbd47b324` |
| `route_operations` | `92a859fc57182954c5070670928c89e6` |
| `operation_steps` | `3829d1b0a5185a4ac59a509532b4abc8` |
| `station_event_sources` | `c70220808f91a8562d14377c47b2a698` |
| `work_order_operation_execution_state` | `293d69efdb273e2bd0a8e6062f930d28` |
| `work_order_operation_steps` | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` |
| `operation_events` | `5bcb14870e3147f60e15cebdd146bba4` |
| `operation_approvals` | `d41d8cd98f00b204e9800998ecf8427e` |
| `production_flow_events` | `d41d8cd98f00b204e9800998ecf8427e` |
| `work_orders` | `283cf9b28e57bc5d6d398169f935473d` |
| `work_order_operations` | `fb74f90dcb2460542ad6422609144b6f` |
| `station_queue` | `2760e411b756b4194df0f86e4987cb5a` |
| `locations` | `03842ba4695966bbc65a4ec3eac438e9` |
| `station_location_bindings` | `f5274a415a5d1744af064a539693d0be` |

Digest method:

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

## Retained Runtime Baseline

```text
execution_status = active
current_step_code = OPERATOR_OBSERVATION_APPROVAL
operation_completion_policy = auto_complete_pending_approval

COLOR_SENSOR_ENTRY_EVIDENCE   = completed
ROBOT_ARM_DROP_COMPLETED      = completed
OPERATOR_OBSERVATION_APPROVAL = pending

target operation_events       = 4
operation_approvals           = 0
production_flow_events        = 0
```

The last retained event remained
`OP_EVENT_ASSEMBLY_01:ROBOT_ARM_DROP:robot-implicit-finish-smoke-20260710-001`.

## Isolation Strategy

- The source was exported with `pg_dump`.
- Each clone was created as an empty database with `createdb`.
- Each clone was restored with `psql -f` from the same logical dump.
- `CREATE DATABASE ... TEMPLATE mes` was not used.
- Only each clone's
  `mes.work_order_operation_execution_state.operation_completion_policy`
  field was changed as scenario fixture setup.
- The host `.venv` called `finish_execution_step` only after asserting the
  database name started with `mes_policy_` and was not `mes`.
- An initial orchestration scalar-index comparison error safely dropped the
  first preliminary clone before any helper smoke. The three clones were then
  recreated and fully verified.
- A Windows inline-code quoting error occurred before the first helper call;
  the manual clone still had four target events. The successful run used
  UTF-8/Base64 transport and revalidated the fixture before calling the helper.

## Clone Databases

- Manual close:
  `mes_policy_manual_20260710_133519`
- Auto close:
  `mes_policy_auto_close_20260710_133519`
- Pending approval:
  `mes_policy_pending_approval_20260710_133519`

All names were lowercase ASCII, unique for this task, and matched the guarded
`mes_policy_` prefix.

## Clone Restore Verification

Every clone matched all 15 source baseline counts and digests before fixture
setup. Each clone also had:

```text
execution_status = active
current_step_code = OPERATOR_OBSERVATION_APPROVAL

COLOR_SENSOR_ENTRY_EVIDENCE   = completed
ROBOT_ARM_DROP_COMPLETED      = completed
OPERATOR_OBSERVATION_APPROVAL = pending

target operation_events = 4
operation_approvals = 0
production_flow_events = 0
```

## Manual-Close Scenario

- Database: `mes_policy_manual_20260710_133519`.
- Policy: `manual_close`.
- External event: `policy-manual-close-smoke-20260710-001`.
- Event ID:
  `OP_EVENT_ASSEMBLY_01:KIOSK_OPERATOR:policy-manual-close-smoke-20260710-001`.
- Event time: `2026-07-10 10:40:38.580653+00`.
- First response:
  - `finished = true`
  - `event_inserted = true`
  - `implicit_started = true`
  - `required_steps_completed = true`
  - `completion_policy_applied = true`
  - `completion_policy = manual_close`
- Execution transition: `active -> evidence_completed`.
- Execution after the call:
  - `current_step_code = null`
  - `evidence_completed_at = event_time`
  - `pending_final_approval_at = null`
  - `closed_at = null`
  - `last_event_id = triggering event ID`
  - `updated_at = event_time`
- Target step became `completed`.
- Target step `started_at`, `completed_at`, and `updated_at` all equaled the
  triggering event time.
- Target step start and completion event references both equaled the triggering
  event ID.
- Event count: `4 -> 5`.

## Manual-Close Duplicate Replay

The same external event was replayed.

```text
finished = false
event_inserted = false
implicit_started = false
completion_policy_applied = false
```

Execution status/timestamps/references, step timestamps/references, event ID,
and event count were preserved. Event count remained `5 -> 5`.

## Auto-Close Scenario

- Database: `mes_policy_auto_close_20260710_133519`.
- Policy: `auto_close_on_required_steps`.
- External event: `policy-auto-close-smoke-20260710-001`.
- Event ID:
  `OP_EVENT_ASSEMBLY_01:KIOSK_OPERATOR:policy-auto-close-smoke-20260710-001`.
- Event time: `2026-07-10 10:40:42.713384+00`.
- First response:
  - `finished = true`
  - `event_inserted = true`
  - `implicit_started = true`
  - `required_steps_completed = true`
  - `completion_policy_applied = true`
  - `completion_policy = auto_close_on_required_steps`
- Execution transition: `active -> closed`.
- Execution after the call:
  - `current_step_code = null`
  - `pending_final_approval_at = null`
  - `last_event_id = triggering event ID`
- Exact timestamp equality:

```text
target_step.started_at
= target_step.completed_at
= execution.evidence_completed_at
= execution.closed_at
= operation_event.event_time
= 2026-07-10 10:40:42.713384+00
```

- Event count: `4 -> 5`.
- Approval and production-flow counts remained zero.

## Auto-Close Duplicate Replay

The same external event was replayed.

```text
finished = false
event_inserted = false
implicit_started = false
completion_policy_applied = false
```

Execution status/timestamps/references, step timestamps/references, event ID,
and event count were preserved. Event count remained `5 -> 5`.

## Pending-Approval Scenario

- Database: `mes_policy_pending_approval_20260710_133519`.
- Policy: `auto_complete_pending_approval`.
- External event: `policy-pending-approval-smoke-20260710-001`.
- Event ID:
  `OP_EVENT_ASSEMBLY_01:KIOSK_OPERATOR:policy-pending-approval-smoke-20260710-001`.
- Event time: `2026-07-10 10:40:46.846096+00`.
- First response:
  - `finished = true`
  - `event_inserted = true`
  - `implicit_started = true`
  - `required_steps_completed = true`
  - `completion_policy_applied = true`
  - `completion_policy = auto_complete_pending_approval`
- Execution transition: `active -> pending_final_approval`.
- Execution after the call:
  - `current_step_code = null`
  - `closed_at = null`
  - `last_event_id = triggering event ID`
- Exact timestamp equality:

```text
target_step.started_at
= target_step.completed_at
= execution.evidence_completed_at
= execution.pending_final_approval_at
= operation_event.event_time
= 2026-07-10 10:40:46.846096+00
```

- Event count: `4 -> 5`.
- `operation_approvals = 0`.
- `production_flow_events = 0`.
- The pending-approval state did not create an approval row.

## Pending-Approval Duplicate Replay

The same external event was replayed.

```text
finished = false
event_inserted = false
implicit_started = false
completion_policy_applied = false
```

Execution status/timestamps/references, step timestamps/references, event ID,
and event count were preserved. Event count remained `5 -> 5`.

## Forbidden Mutation Verification

For every scenario, pre/post counts and digests were identical for all 12
forbidden tables:

```text
mes.work_orders
mes.work_order_operations
mes.station_queue
mes.operation_approvals
mes.production_flow_events
mes.items
mes.process_routes
mes.route_operations
mes.operation_steps
mes.station_event_sources
mes.locations
mes.station_location_bindings
```

Only these allowed clone tables changed during the successful smoke:

```text
mes.operation_events
mes.work_order_operation_steps
mes.work_order_operation_execution_state
```

Each scenario inserted exactly one `step_finish` event. No extra
`system_transition`, approval, production-flow, inventory, lifecycle, or
work-order event/write was created.

## Clone Cleanup

- `mes_policy_manual_20260710_133519`: dropped and absence verified.
- `mes_policy_auto_close_20260710_133519`: dropped and absence verified.
- `mes_policy_pending_approval_20260710_133519`: dropped and absence verified.
- Remaining `mes_policy_%` databases after cleanup: `0`.
- The exact container temporary dump was removed.
- No image rebuild, Compose recreate/down, or volume operation was performed.

## Source Final Counts

All final source counts exactly matched the baseline:

```text
items                                = 3
process_routes                       = 1
route_operations                     = 2
operation_steps                      = 5
station_event_sources                = 4
work_order_operation_execution_state = 1
work_order_operation_steps           = 3
operation_events                     = 4
operation_approvals                  = 0
production_flow_events               = 0
work_orders                          = 12
work_order_operations                = 8
station_queue                        = 13
locations                            = 8
station_location_bindings            = 8
```

## Source Final Digests

All 15 final source digests exactly matched the Source Baseline Digests table.
No source row count or digest changed.

## Source Retained Runtime Verification

```text
execution_status = active
current_step_code = OPERATOR_OBSERVATION_APPROVAL
operation_completion_policy = auto_complete_pending_approval

COLOR_SENSOR_ENTRY_EVIDENCE   = completed
ROBOT_ARM_DROP_COMPLETED      = completed
OPERATOR_OBSERVATION_APPROVAL = pending

target operation_events = 4
operation_approvals = 0
production_flow_events = 0
```

The retained V1 runtime instance, event ledger, config/master data, lifecycle
tables, approvals, and production-flow tables were unchanged.

## Health

- `{"status":"ok","time":"2026-07-10T10:41:54.355+00:00"}`

## Guardrails

- No helper call targeted source database `mes`.
- No source runtime, event, approval, production-flow, config/master,
  lifecycle, inventory, or cleanup write occurred.
- Only task-created disposable clone databases were created and dropped.
- No migration or seed was changed or applied.
- No API, Kiosk, IoT/MQTT, Observer, OEE/KPI, approval helper, manual-close
  helper, production-flow helper, inventory, work-order closure, MESQL, or FERP
  implementation/action was performed.
- No Docker rebuild, Compose recreate/down, or volume operation was performed.
- No branch, reset, rebase, amend, push, or force operation was performed.
- `.agents/` was not accessed.

## Result

PASS.


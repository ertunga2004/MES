# Runtime-to-Lifecycle Completion Bridge Isolated Smoke Evidence

## Result

`FAIL`

Date: `2026-07-15`
Phase 5G-B commit: `0910a145c73d2c0791fe1a1dd178702e01d04e55`
Disposable clone: `mes_runtime_lifecycle_bridge_smoke_20260715_181220`

The main route-release/runtime/bridge chain and twelve rollback/retry cases
passed on real PostgreSQL. The required concurrent duplicate replay failed with
`RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT`; therefore Phase 5G-C cannot be
accepted and `CURRENT_STATE.md` was not updated.

## Phase 5G-B Closure

- Focused review found no pre-smoke P1/P2 issue.
- Targeted tests: `578`, `OK`.
- Combined tests: `614`, `OK`.
- Python compile and `git diff --check`: PASS.
- Commit subject: `feat: integrate runtime lifecycle completion bridge`.
- Commit contains only `mes_web/db/mesql_v2.py` and
  `tests/test_mes_web_mesql_v2.py`.
- No push was performed.

## Source Safety and Backup

- Source identity: database `mes`, user `mes`, container `mes_postgres`.
- Source was used only for logical backup, repeatable-read/read-only baseline,
  final integrity, and health.
- Backup retained at
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_runtime_lifecycle_bridge_smoke_20260715_181220.sql`.
- Backup size: `2,881,697` bytes; plain SQL header verified.
- Source sidecars remained absent; Canonical V2 route count remained `0`.
- Source audit counts remained events/approvals/flow `4/0/0`.
- Phase 5G-C source fixture count remained `0`.

## Source 15-Table Integrity

Baseline and final counts/digests matched `15/15`:

| Table | Count | Digest |
|---|---:|---|
| `mes.items` | 3 | `40a291eb5907edf46942f1804a405ebd` |
| `mes.process_routes` | 1 | `163f416bfdcf16ca469e43adbd47b324` |
| `mes.route_operations` | 2 | `8cf5541af45df5a6df7df617c0367382` |
| `mes.operation_steps` | 5 | `601511ac9fc07e8835cc0a7a4a17799e` |
| `mes.station_event_sources` | 4 | `4d301465ab9c6d09bab7e38a5eadc61f` |
| `mes.work_order_operation_execution_state` | 1 | `293d69efdb273e2bd0a8e6062f930d28` |
| `mes.work_order_operation_steps` | 3 | `e2be147bb88a650a26a5b5c0dbb2173f` |
| `mes.operation_events` | 4 | `4798336805bc1b362ec67cebc06bff93` |
| `mes.operation_approvals` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.production_flow_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.work_orders` | 12 | `72c1f7d769fa6740959bed27f5497982` |
| `mes.work_order_operations` | 8 | `64350f2fd13dd97cd2a5284d7c51dc3c` |
| `mes.station_queue` | 13 | `a3785bb7eb429246c30334ed2339e135` |
| `mes.locations` | 8 | `ba947080f858b09a74ab11dab32fb0d5` |
| `mes.station_location_bindings` | 8 | `f1e5267f6ee53aae5165593adbe36e6a` |

Final HTTP health was `200` with `{"status":"ok"}`.

## Clone Preparation

- Clone was created from `template0`, then restored from the logical source
  dump; `TEMPLATE mes` was not used.
- Mutation guard required exact clone identity and rejected database `mes`.
- Restore representative counts matched source.
- Migrations `009` and `010` and Canonical V2 seed were applied only to clone.
- Binding shape: `9/9/4`.
- Release shape: `14/15/5`.
- Canonical V2 route/operations/steps: `1/2/4`; OP10/OP20 steps: `3/1`.

## Main End-to-End Chain

- Route-generated release returned `released=true`.
- Deterministic OP10 UUID:
  `dc2dc1c4-0217-5941-a9d3-64ea9b63dfde`.
- Deterministic OP20 UUID:
  `5d52ffdf-5dd3-54d3-9377-7f850d51e377`.
- Two immutable bindings and one initial OP10 queue were persisted.
- OP10 initialized with three pending runtime steps.
- OP10 final finish closed runtime and returned `completion_bridge.bridged=true`.
- OP10 lifecycle/current queue completed; OP20 lifecycle became queued and an
  exact `runtime_completion_bridge` queue was created at rank `3`.
- Immediate OP10 duplicate returned `bridged=false` with zero duplicate row.
- OP20 initialized with one pending step; final finish returned `bridged=true`.
- OP20 lifecycle/queue and work order completed at authoritative runtime close.
- Final OP20 duplicate and old OP10 replay after final completion both returned
  `bridged=false`.
- Bridge audit delta was zero for approvals, production flow, production
  completions, work-order events, and integration outbox. Only configured
  runtime start/finish events increased (`4 -> 11`).

## Rollback Injection

Twelve independent real-DB candidates passed exact before/after scoped digest
equality and clean first-bridge retry:

1. after finish-event insert;
2. after runtime-step completion;
3. after runtime closed transition;
4. after current lifecycle completion;
5. after current queue terminalization;
6. after successor resolution;
7. after successor lifecycle update;
8. after unique station locks/queue-lock read;
9. after successor queue insert;
10. before authoritative snapshot;
11. before transaction exit;
12. after final work-order completion.

Cases RB01-RB11 completed OP10 cleanly on retry; RB12 completed both operations
and the work order on retry. No partial event/runtime/lifecycle/queue/work-order
state survived an injected failure.

## Blocking Failure: Concurrent Duplicate Replay

Two independent connections issued the exact same final OP10 finish event for
`WO-PHASE5G-C-CONCURRENT-DUP`.

- One transaction committed the expected first bridge: one finish event, OP10
  completion, OP20 activation, and exactly two work-order queue rows.
- The waiting duplicate did not return `finished=false` / `bridged=false`.
- It raised `RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT` from
  `_prepare_runtime_completion_bridge_cursor`.

Root cause: the nonlocking applicability preflight reads mutable lifecycle
fields before the work-order lock. After the first transaction commits, the
waiting transaction locks authoritative rows but requires the originally read
`status` and `completed_at` to equal the now-progressed lifecycle row. That
stale mutable comparison rejects the exact replay before bridge classification.

Required correction: post-lock preflight revalidation must compare immutable
identity/marker fields while allowing the classifier to handle mutable
`status` and `completed_at` progression. Unit coverage must reproduce two real
concurrent duplicate finish calls and require one true plus one false result.

## Not Executed After Blocking Failure

Per the P1/P2 stop rule, the following remaining smoke cases were not treated
as passed:

- legacy/schema-not-ready gating on a pre-sidecar clone;
- same-successor-station rank concurrency and unique lexical lock evidence;
- same-current/successor-station negative fixture;
- live fresh-context queue `23505` blocker classification;
- unknown-error real-DB proxy matrix.

Unit evidence for these areas is not substituted for the required isolated
PostgreSQL smoke.

## Cleanup

- Exact clone sessions were terminated and the clone was dropped.
- Remaining `mes_runtime_lifecycle_bridge_smoke_%` database count: `0`.
- Exact container temporary dump/migration/seed files were removed.
- Host backup was retained with its original nonzero size.
- Docker container/image/volume lifecycle was not changed.
- No API, Kiosk, IoT, OEE, FERP, MESQL, inventory, rollout, or
  `complete_operation_v2` path was invoked.

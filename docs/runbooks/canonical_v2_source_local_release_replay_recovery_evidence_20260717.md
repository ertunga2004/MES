# Canonical V2 Source-Local Release-Replay Recovery Evidence

## Result

`PASS / VERIFIED_RETAINED_FIXTURE_RELEASE_REPLAY_RECOVERY`

Original functional execution date: `2026-07-15`.

Recovery verification date: `2026-07-17`.

The historical Phase 5H-C functional smoke completed release, OP10, OP20, and
the work order but failed its final route-release replay with
`WORK_ORDER_RELEASE_QUEUE_CONFLICT`. Phase 5H-CR2 verified the retained
fixture independently, rehearsed the CR1 fix on an exact logical-restore clone,
then ran the exact release replay on source `mes` once. Both replays returned
`released=false` with zero writes.

## Repository Baseline and CR1 Hotfix

The Phase 5H-C FAIL evidence remains unchanged at:

`docs/runbooks/canonical_v2_source_local_functional_smoke_evidence_20260715.md`

Its documentation commit is
`22e9bb75c250bb0e58f7330def665927c5266988`
(`docs: record canonical v2 source-local smoke failure`).

The progressed route-release replay fix was focused-reviewed with no P1/P2
finding. It preserves the public writer signature, release/lifecycle/binding/
digest validation, transaction order, completion bridge, and runtime helpers.
It selects exactly one initial queue row by the immutable minimum-sequence
lifecycle UUID, accepts successor queues only within the released lifecycle
UUID set, and does not enter the station advisory-lock/rank-allocation branch
on replay.

Regression before database access:

```text
targeted: 632 / OK
combined: 668 / OK
py_compile: PASS
git diff --check: PASS
```

The exact two-file hotfix commit is:

```text
c7e7ea2698d873a7ac5c8737bddd97b349355675
fix: allow route release replay after queue progression

mes_web/db/mesql_v2.py
tests/test_mes_web_mesql_v2.py
```

No duplicate commit or push was performed.

## Separate Recovery Approval and Guardrails

The recovery approval covered only the retained release replay. No new work
order, release, identity, runtime initialization, step event, finish,
completion-bridge call, API/Kiosk/IoT action, FERP/MESQL operation,
package/inventory helper, migration, seed, source restore, fixture repair, or
fixture delete was performed.

Exact retained identity:

```text
order_id:   PHASE5HC-SOURCE-SMOKE-20260715-181940
release_id: PHASE5HC-SOURCE-RELEASE-20260715-181940
actor:      PHASE5HC_SOURCE_SMOKE
route:      ROUTE_BOX_PACKAGING_V2 / version 2
source:     local_planning
mode:       route_generated
```

Exact release metadata:

```json
{
  "disposable_test": true,
  "exclude_from_analytics": true,
  "phase": "5H-C",
  "production_release": false,
  "purpose": "canonical_v2_source_local_functional_smoke",
  "retention_reason": "source_rollout_validation"
}
```

## Authoritative Source Preflight

Exact target was `mes_postgres / mes / mes`, PostgreSQL `16.14`, host port
`5433`. The container was running/healthy. The initial and immediate
pre-source-replay checks each found zero other `mes` sessions. No competing
database writer was present.

A complete `REPEATABLE READ READ ONLY` snapshot closed the independent
post-error readback gap from the historical FAIL evidence:

```text
work order: completed
completed_at: 2026-07-15T18:35:41.238660+00:00

release operation count: 2
release digest:
8cb642eb8c2db238adf59891fb30aac5b1673ec16de6da2a4a10a5d04338cba9

OP10 UUID: 52fb8cd4-005e-51f2-9557-a6ff31ce5063
OP20 UUID: d78c3f30-9e49-51a3-ad58-a13e45f3705f
both lifecycle rows: completed
both runtime states: closed
runtime steps: 3 + 1, all completed
configured fixture events: 6

OP10 queue: PK 6853 / completed / work_order_release
OP20 queue: PK 6854 / completed / runtime_completion_bridge
```

Fixture row counts were exact:

```text
work order / release / lifecycle / bindings = 1 / 1 / 2 / 2
queues / runtime / steps / events = 2 / 2 / 4 / 6
```

Fixture-scoped system-transition events, approvals, production-flow events,
production completions, work-order events, integration outbox, and FERP outbox
were all `0`. V1 remained exact:

```text
route:      1 / 163f416bfdcf16ca469e43adbd47b324
operations: 2 / 92a859fc57182954c5070670928c89e6
steps:      5 / 3829d1b0a5185a4ac59a509532b4abc8
```

Sidecar/V2 readiness was binding/release columns `9 / 14` and V2
route/operations/steps `1 / 2 / 4`.

The first full read-only diagnostic used the non-existent event alias
`operation_event_pk`; PostgreSQL aborted that read-only transaction before
completion. No source mutation or replay occurred. The corrected exact
`event_pk` query produced the complete accepted snapshot.

## Byte-Safe Recovery Backup

The backup used container-side `pg_dump -Fp -f`, not PowerShell stdout
redirection.

```text
container temp:
  /tmp/mes_before_phase5hc_release_replay_recovery_20260717-080314.sql
host retained:
  C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_phase5hc_release_replay_recovery_20260717-080314.sql
bytes:
  2911692
SHA-256:
  f4e19c0bd8f97ff898fbc3a1de63ee0c125ee67a437de78292d74c971740e2f0
```

Container and host size, plain-dump header, and SHA-256 were exact. The
container dump was removed only after host equality. The host backup remains
retained and was revalidated after clone cleanup and source replay. No restore
was applied to source.

## Source Baseline

The authoritative source baseline used deterministic MD5 over ordered JSONB
rows with the exact `|` separator:

| Table | Rows | Digest |
| --- | ---: | --- |
| `device_sessions` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `downtime_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `error_types` | 2 | `01e707bdfd6d67d79f808265d962f178` |
| `ferp_export_outbox` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `ferp_import_batches` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `integration_inbox` | 4 | `68936bf1239ce48c3e05d0cd2dd98ef7` |
| `integration_outbox` | 9 | `316f1360cce4eb5506edfae668bc680b` |
| `item_station_events` | 413 | `498992b21372043b2971c04f30ec4a16` |
| `items` | 3 | `c120ee7ee8808e4280bcb02895f76e8c` |
| `locations` | 8 | `03842ba4695966bbc65a4ec3eac438e9` |
| `maintenance_records` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `maintenance_steps` | 6 | `ed7d086dbed80a50a4c898f42523085e` |
| `oee_snapshots` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `operation_approvals` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `operation_events` | 10 | `abddef68961ecb54b1dedbab659cb2d1` |
| `operation_steps` | 9 | `b0992fc235ac795bede283fbf8130173` |
| `operators` | 1 | `8ac0f7eab8ec9e7edbd8d092eba71d92` |
| `package_bom_lines` | 6 | `a83fe65432099236aec3ec446cfd2f4d` |
| `package_component_wip` | 94 | `05775cff982429369695df9dc8b2dc35` |
| `package_sessions` | 5 | `1d0f8a895ddbaca7f674c499ec9bb704` |
| `package_traceability` | 16 | `00f3baba1d3a2a96ce852f7f4a970f21` |
| `packaging_units` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `process_routes` | 2 | `937e8911494bd3489f45d50e7e76e66e` |
| `production_completions` | 114 | `3fd60eea6551e0f07138a4f9cb0759e9` |
| `production_flow_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `quality_overrides` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `route_operations` | 4 | `57e81d60c532c3ec16ba7fc312f12fcc` |
| `schema_migrations` | 8 | `b7723532decd70ecf21489bd44c27cfc` |
| `station_event_sources` | 4 | `c70220808f91a8562d14377c47b2a698` |
| `station_location_bindings` | 8 | `f5274a415a5d1744af064a539693d0be` |
| `station_queue` | 15 | `9426c911cd4c14bfdb96ecc59a194add` |
| `stations` | 3 | `180886306b8d36601934a3fd94a2a59b` |
| `vision_events` | 43 | `04ccd26421a13426af455bc8342a9c3c` |
| `work_order_events` | 676 | `21ccf3421f54c718c99d106d974aac2a` |
| `work_order_operation_execution_state` | 3 | `37076cb6c6f0fc33d3f8146ea0b5722b` |
| `work_order_operation_route_bindings` | 2 | `6b5214ea9b011efe9d6160d6173fd507` |
| `work_order_operation_steps` | 7 | `5d2a14c606a9c4fefbd472ba1dd14fd0` |
| `work_order_operations` | 10 | `cdd36e89a4bf70253a31123dcc52ce20` |
| `work_order_route_releases` | 1 | `bc6ec960b1686e736fab3968a4b9ce8b` |
| `work_orders` | 13 | `468f4ed5388c11150f028ebd35e3c6a9` |

All `40/40` counts and digests were identical again immediately before source
replay and after source replay.

Sequence state was captured independently:

| Sequence | Last value | Called |
| --- | ---: | --- |
| `device_sessions_device_session_pk_seq` | 1 | `f` |
| `downtime_events_downtime_pk_seq` | 1 | `f` |
| `error_types_error_type_pk_seq` | 2 | `t` |
| `ferp_export_outbox_export_pk_seq` | 1 | `f` |
| `ferp_import_batches_import_batch_pk_seq` | 1 | `f` |
| `item_station_events_item_station_event_pk_seq` | 413 | `t` |
| `items_item_pk_seq` | 3 | `t` |
| `locations_location_pk_seq` | 8 | `t` |
| `maintenance_records_maintenance_pk_seq` | 1 | `f` |
| `maintenance_steps_maintenance_step_pk_seq` | 6 | `t` |
| `oee_snapshots_snapshot_pk_seq` | 1 | `f` |
| `operation_approvals_approval_pk_seq` | 1 | `f` |
| `operation_events_event_pk_seq` | 10 | `t` |
| `operation_steps_operation_step_pk_seq` | 9 | `t` |
| `operators_operator_pk_seq` | 1 | `t` |
| `package_bom_lines_bom_line_id_seq` | 12 | `t` |
| `package_component_wip_wip_item_pk_seq` | 148505 | `t` |
| `package_traceability_package_trace_pk_seq` | 16 | `t` |
| `process_routes_route_pk_seq` | 2 | `t` |
| `production_completions_completion_pk_seq` | 116 | `t` |
| `production_flow_events_flow_event_pk_seq` | 1 | `f` |
| `quality_overrides_quality_override_pk_seq` | 1 | `f` |
| `route_operations_route_operation_pk_seq` | 4 | `t` |
| `schema_migrations_migration_pk_seq` | 8 | `t` |
| `station_event_sources_event_source_pk_seq` | 4 | `t` |
| `station_location_bindings_binding_pk_seq` | 8 | `t` |
| `station_queue_station_queue_pk_seq` | 6854 | `t` |
| `stations_station_pk_seq` | 7 | `t` |
| `vision_events_vision_event_pk_seq` | 43 | `t` |
| `work_order_events_event_pk_seq` | 4655 | `t` |
| `work_order_operation_execution_state_execution_state_pk_seq` | 3 | `t` |
| `work_order_operation_route_bindings_binding_pk_seq` | 2 | `t` |
| `work_order_operation_steps_work_order_operation_step_pk_seq` | 7 | `t` |
| `work_order_route_releases_release_pk_seq` | 1 | `t` |
| `work_orders_work_order_pk_seq` | 11231 | `t` |

All `35/35` sequence states were identical across source pre/post replay and
clone pre/post replay.

## Disposable Clone Rehearsal

Clone:

`mes_phase5hc_release_replay_recovery_20260717_080314`

The verified host backup was copied byte-for-byte to the container. The initial
PowerShell clone guard expected PostgreSQL's textual boolean as `t` while the
query explicitly cast it to `true`; this stopped after creating the empty
clone and before restore. Read-only classification proved the exact clone and
restore temp state. The corrected guard required the exact clone name,
`current_database() <> 'mes'`, and zero `mes` base tables before restore.

The clone was created from `template0`, not `mes`. Restore produced:

```text
base tables before / after: 0 / 40
source/clone table equality: 40/40
source/clone sequence equality: 35/35
fixture snapshot equality: exact
V1 and sidecar/V2 equality: exact
```

A first local Python launcher failed at parse time because Windows native
argument quoting removed metadata string quotes. It opened no helper connection
and executed no replay. The syntax-safe launcher then made the one clone
release-replay call.

Clone replay:

```text
database guard: exact clone, not mes
released: false
release rows: exact existing release
lifecycle operations: 2
bindings: 2
initial queue: OP10 / PK 6853
OP20 successor queue: persisted, not adopted as initial queue
five read-helper agreement: PASS
```

Forbidden call counts were all `0`:

```text
station advisory lock / rank allocation
release insert
lifecycle insert
binding insert
initial queue insert
work-order update
```

Post-replay clone comparison passed:

```text
table counts/digests: 40/40 exact
sequence states: 35/35 exact
fixture snapshot: exact
V1/audit/outbox/package/inventory: exact through full-table digests
```

The clone had zero remaining sessions, was dropped, and the matching clone count
was `0`. The container restore temp was removed. The host backup was retained.

## Source Exact Replay

Source authorization gates were all PASS: hotfix committed, authoritative
fixture exact, backup verified, clone restore/replay/equality PASS, clone
cleaned, source still quiescent, and the immediate pre-replay source snapshot
matched the original source baseline exactly.

The same immutable request was sent to source `mes` exactly once through
`release_work_order_to_route`.

```text
database guard: mes
source replay calls: 1
released: false
queue conflict: none
initial queue: OP10 / PK 6853
operations / bindings: 2 / 2
response/read-helper agreement: PASS
```

Real replay instrumentation proved zero calls to every release writer primitive
and to the station advisory-lock/rank-allocation primitive. No retry was run.

The independent post-replay `REPEATABLE READ READ ONLY` snapshot proved:

```text
table counts/digests: 40/40 exact
sequence states: 35/35 exact
fixture snapshot: exact
work-order completed_at: unchanged
release/digest: unchanged
lifecycle/bindings: unchanged
both queue rows: unchanged
runtime/steps/events: unchanged
V1: unchanged
audit/outbox/package/inventory: unchanged
other source sessions: 0
```

PostgreSQL remained `running / healthy`; HTTP health was
`200 / status=ok`. Matching disposable clone count was `0`, container
backup/restore temps were absent, and the host backup retained its exact byte
count and SHA-256.

## Acceptance

Result: `PASS`.

The historical 2026-07-15 FAIL evidence remains immutable and continues to
document the original queue-cardinality defect. This recovery evidence
supersedes that failed final replay acceptance result: the original functional
execution evidence plus the 2026-07-17 clone/source recovery together establish
the complete Phase 5H-C acceptance chain.

The retained fixture remains explicitly nonproduction. Future OEE, KPI,
analytics, reporting, FERP/MESQL export, and generic export consumers must
exclude it by exact prefix or `exclude_from_analytics=true`. That consumer
implementation remains deferred.

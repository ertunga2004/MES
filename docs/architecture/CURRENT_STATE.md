# Current Verified State

Last verified: `2026-07-19`

Repository baseline:
`e75110f5b80c8666630d4fdc00b07e171fdc5ea0`
(`docs: establish phase 6 agent handoff`)

Verified implementation baseline:
`ae023142058a0a5fa79c6b99e257097abbde8dd1`
(`fix: complete phase 6a station integration`)

## System purpose and authority

This repository develops a configurable local manufacturing-execution core.
The conveyor, sensors, robot arm, Raspberry observer, and pick-to-light module
are reference-plant components; they do not define the product boundary.

This file records the current verified repository state. It is not a migration,
database-write, source-rollout, physical-broker, or Phase 6B authorization.
Observed execution claims are backed by the linked acceptance and smoke
evidence. Design documents define intended contracts but do not replace
execution evidence.

Authority and navigation:

- Repository working rules: [root AGENTS](../../AGENTS.md).
- Documentation registry: [Documentation Index](../INDEX.md).
- Next-phase boundary: [Phase 6B Entry](PHASE_6B_ENTRY.md).
- Final Phase 6A acceptance:
  [station integration evidence](../runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md).

`MES` is the actively developed local production-execution system in this
repository. `MESQL` is a separate central integration/data-core effort and
remains frozen unless a task explicitly activates it. Neither repository,
migration ownership, nor data authority may be inferred across that boundary.

## Current runtime and data boundaries

- Firmware/control remains authoritative for physical movement and safety.
- `mes_web` owns application orchestration, operator/Kiosk interaction,
  station-execution commands, MQTT ingestion, audit-facing runtime state, and
  controlled PostgreSQL integration.
- Canonical route release, lifecycle operation identity, runtime step state,
  station queue transitions, and the completion bridge use persisted local
  PostgreSQL state when their default-disabled capabilities are enabled.
- Workbook, OEE JSON/runtime state, legacy API paths, and existing MQTT QoS0
  behavior remain compatibility surfaces; they have not been globally replaced
  by the Canonical V2 path.
- Browser clients do not own physical or persisted transition authority.
- The Raspberry vision stack is an observation adapter. It does not replace the
  physical sorting authority or independently complete work orders.
- The controlled route-release HTTP endpoint has no repository-wide
  authentication layer. It is restricted to a trusted local operator or
  planning-service boundary when explicitly enabled.
- Production `mes` writes, migration apply, source rollout, physical-broker
  use, and destructive recovery each require separate explicit authorization.

## Verified capabilities

### Work-order and route release

- The public route-release helper supports the deliberately narrow
  `route_generated / local_planning` mode.
- Route selection is exact `route_code + route_version`; there is no
  latest-active, station, operation-code, sequence, or product inference.
- One transaction owns the immutable release record, deterministic lifecycle
  operations, complete route-operation bindings, initial OP10 queue row, and
  queued work-order state.
- Lifecycle and binding identities are deterministic UUIDv5 values derived
  from versioned namespaces and an exact one-LF canonical name.
- Exact replay validates immutable release data, static lifecycle snapshots,
  bindings, and digest, then returns `released=false` without writes. Legitimate
  lifecycle, queue, quantity, timestamp, and work-order progression does not
  invalidate replay.
- Conflicts and failed eligibility checks leave no partial rows. Same-station
  queue rank allocation is serialized against the exact live-rank predicate
  `queued`, `active`, and `pending_approval`; `ready` is excluded.
- Identical concurrent requests converge to one release and one replay.
  Cross-order release-ID reuse is a deterministic conflict.
- The controlled endpoint is
  `POST /api/v2/work-orders/{work_order_id}/route-release`. Its raw JSON parser
  enforces the 65,536-byte boundary, duplicate-key rejection, strict field
  ownership, repository response envelopes, and sanitized structured logging.
- Disposable-clone first release/replay, focused logging recovery, and the
  retained source progressed replay have been verified. The source replay was
  zero-write.

Primary evidence:

- [Release schema smoke](../runbooks/work_order_route_release_migration_isolated_smoke_evidence_20260715.md)
- [Release read-model smoke](../runbooks/work_order_route_release_read_helper_isolated_smoke_evidence_20260715.md)
- [Release writer smoke](../runbooks/work_order_release_writer_isolated_smoke_evidence_20260715.md)
- [Controlled HTTP clone failure](../runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_evidence_20260719.md)
- [Controlled HTTP logging recovery](../runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_recovery_evidence_20260719.md)
- [Controlled source replay](../runbooks/canonical_v2_controlled_release_api_source_http_smoke_evidence_20260719.md)

### Lifecycle and runtime completion

- Runtime initialization creates one execution state and ordered persisted
  step rows from an explicit immutable lifecycle-to-route-operation binding.
- Initialization starts at `ready` with no current step; it does not silently
  activate the first step.
- Step start/finish records station-scoped events, applies configured manual or
  implicit transitions, and preserves exact replay semantics.
- `auto_close_on_required_steps` closes runtime execution after all required
  steps complete. Manual-close and approval-close lifecycle integration are
  not generalized.
- The runtime-to-lifecycle bridge runs synchronously inside the transaction
  that first persists runtime `closed` for a route-release lifecycle.
- The bridge completes the current lifecycle/queue, queues the unique next
  lifecycle operation by immutable UUID/binding, or completes the work order
  when no successor remains.
- Bridge replay is zero-write after operational progression. Queue conflicts
  and failure-injection paths roll back the whole transaction and do not retry
  rank allocation automatically.
- Legacy lifecycle rows without the exact route-release metadata marker remain
  outside the bridge and do not require sidecar access.

Primary evidence:

- [Runtime initialization](../runbooks/station_execution_runtime_init_smoke_evidence_20260709.md)
- [Event ledger](../runbooks/station_execution_event_ledger_smoke_evidence_20260709.md)
- [Step start](../runbooks/station_execution_step_start_smoke_evidence_20260710.md)
- [Step finish](../runbooks/station_execution_step_finish_smoke_evidence_20260710.md)
- [Implicit start/finish](../runbooks/station_execution_robot_implicit_finish_smoke_evidence_20260710.md)
- [Completion policies](../runbooks/station_execution_completion_policy_isolated_smoke_evidence_20260710.md)
- [Completion-bridge historical failure](../runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_evidence_20260715.md)
- [Completion-bridge verified retry](../runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_retry_evidence_20260715.md)

### Station execution

- Phase 6A connects Kiosk/manual commands and canonical MQTT events to one
  config-driven station-execution application boundary.
- Verified modes are manual/manual, implicit/manual, manual/implicit,
  configured-source implicit/implicit, and source-less internal
  implicit/implicit.
- Persisted lifecycle UUID is the canonical operation-instance identity.
  Dispatch validates lifecycle, route operation, station, current step,
  configured mode, action, channel, and event-source identity.
- Queue/lifecycle/current-step disagreement fails closed.
- External replay identity is channel- and publisher/source-aware. Exact
  same-channel replay is zero-write; cross-channel same-ID input is a
  deterministic conflict rather than an adopted replay.
- Source-less internal transitions use deterministic restart-stable identity
  and one atomic transaction; they do not invent an external publisher or
  accept caller-controlled external identity.
- The final focused MQTT suite was `65`, `OK`; the combined Phase 6A suite was
  `933`, `OK`. Independent final review returned `P1=0`, `P2=0`, `P3=0`.
- Phase 6A-F3 disposable PostgreSQL acceptance remained valid for the F4/F5
  transport-only closure. Those closures did not target production `mes` and
  did not use a physical broker.

Canonical acceptance:
[Phase 6A station integration](../runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md).

### Kiosk

- The Kiosk consumes persisted station context through the shared
  station-execution boundary and derives current actions from configured step
  mode/source rather than a station-specific hard-coded sequence.
- Dynamic station actions remain default-disabled and require the core station
  command capability.
- Read-only station/location context is available for Kiosk information cards
  when the corresponding read-model flag is enabled.
- Existing dashboard, operator Kiosk, technician, quality override, workbook,
  and retained V1 behaviors remain compatibility surfaces unless separately
  retired.

Evidence:

- [Station/location Kiosk smoke](../runbooks/station_location_kiosk_ui_smoke_evidence_20260707.md)
- [Station/location manual visual evidence](../runbooks/station_location_kiosk_manual_visual_evidence_20260707.md)
- [Phase 6A station integration](../runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md)

### MQTT transport

- The canonical station adapter uses a stable client identity and persistent
  session.
- Connect, SUBACK, message, and disconnect callbacks are generation-aware;
  stale or retired generations cannot mutate active lifecycle state.
- Admission is bounded. Manual ACK happens only after a terminal worker and
  database-transaction result.
- Timeout, shutdown, transient failure, retired generation, or incomplete
  cleanup produces no ACK.
- Startup failure has exactly one cleanup owner. Worker join and network/client
  cleanup occur outside the lifecycle lock, and concurrent stop waits outside
  that lock for completion.
- Final acceptance found no worker, client, pending MID, failure-owner,
  listener, or temporary-resource leak.
- The canonical adapter remains default-disabled. Physical-broker rollout was
  not part of final Phase 6A closure.

Evidence:
[Phase 6A station integration](../runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md).

### Location/config read models

- Migration `003` added `mes.locations` and
  `mes.station_location_bindings`; the verified baseline contains eight
  locations and eight active station-location bindings.
- Location and station-context helpers and HTTP APIs are read-only and
  default-disabled.
- Migration `004` added the station-execution configuration/runtime/event
  tables. Seed `005` retained the V1 route/configuration.
- Item, route, operation, station event-source, step, operation config, and
  aggregate station-execution config read helpers/APIs are implemented.
- Canonical V2 route/configuration uses explicit route/version and stable
  route-operation IDs. No read helper infers a lifecycle binding.

Evidence:

- [Station/location migration](../runbooks/station_locations_migration_evidence_20260706.md)
- [Station/location read model](../runbooks/station_location_read_smoke_evidence_20260707.md)
- [Station/location API](../runbooks/station_location_api_smoke_evidence_20260707.md)
- [Station/location Tier 1 CI](../runbooks/station_location_api_tier1_ci_evidence_20260707.md)
- [Station-execution schema apply](../runbooks/station_execution_schema_migration_evidence_20260709.md)
- [Station-execution V1 seed](../runbooks/station_execution_seed_minimal_evidence_20260709.md)
- [Station-execution config read model](../runbooks/station_execution_config_read_smoke_evidence_20260709.md)
- [Station-execution config API](../runbooks/station_execution_config_read_api_smoke_evidence_20260709.md)

### Retained workbook and legacy paths

- The workbook and OEE/runtime-state pipeline remains active compatibility
  behavior. PostgreSQL enablement does not silently delete or replace it.
- Existing JSON/FERP import, MESQL pull, legacy queue projection, dashboard,
  technician, package, and QoS0 paths remain outside automatic Canonical V2
  adoption.
- Retained V1 configuration remains one route, two operations, and five steps.
  It is not automatically rebound, backfilled, renamed, or upgraded to V2.
- `OPERATOR_OBSERVATION_APPROVAL` remains the retained V1 identifier. New V2
  configuration uses `PROCESS_END_OBSERVATION` as a normal operation step and
  keeps final approval as a separate concern.
- Portable Docker builds use repository `mes_web/` source. Runtime data,
  backups, secrets, and generated workbooks remain outside the Git tree.

Related references:

- [Observation and quality-control decision](observation_quality_control_boundary_decision.md)
- [Runtime guardrails](../runtime/runtime_guardrails.md)
- [Docker runtime documentation](../../docker/mes/README.md)

## Current database and configuration baseline

The last controlled source verification recorded:

- PostgreSQL `16.14` in the existing `mes_postgres` service.
- `40` `mes` base tables and `35` sequences.
- Applied station/location migration `003`.
- Applied station-execution schema migration `004`.
- Applied retained V1 seed `005`.
- Applied route-operation binding migration `009`.
- Applied work-order route-release migration `010`.
- Applied Canonical V2 seed `006`, after `009` and `010` during controlled
  source rollout.
- Binding sidecar physical shape `9 / 9 / 4` columns/constraints/indexes.
- Release sidecar physical shape `14 / 15 / 5`.
- Retained V1 route/operations/steps `1 / 2 / 5`.
- Canonical V2 route/operations/steps `1 / 2 / 4`, with OP10/OP20 steps
  `3 / 1` and configured/resolved location roles `5 / 5`.
- Eight locations and eight active station-location bindings.

The authoritative base-table invariant for the Canonical V2 rollout was the
preflight set plus exactly the binding and release sidecars; the numeric count
was a secondary check. Detailed catalog shapes, digests, sequence states,
backup identity, and apply/reapply results remain in:

- [Canonical V2 source apply evidence](../runbooks/canonical_v2_source_schema_seed_apply_evidence_20260715.md)
- [Canonical V2 functional failure](../runbooks/canonical_v2_source_local_functional_smoke_evidence_20260715.md)
- [Canonical V2 replay recovery](../runbooks/canonical_v2_source_local_release_replay_recovery_evidence_20260717.md)

This document does not assert that a current live environment still matches
that baseline without a new read-only preflight.

## Frozen engineering invariants

- Persisted database state outranks request metadata and configuration caches
  for canonical execution transitions.
- Exact route/version and explicit immutable bindings replace inference.
- Lifecycle UUID is the canonical operation-instance identity.
- Deterministic identity must be restart-stable and channel-aware where the
  contract requires channel identity.
- Multi-row release, execution, completion, queue, and audit transitions are
  atomic.
- Exact replay and specified conflicts are zero-write.
- Replay never rewinds legitimate mutable operational progression.
- Failure paths do not commit partial rows or silently repair persisted state.
- Lock order is explicit; blocking join, wait, or network cleanup does not run
  under lifecycle locks.
- MQTT manual ACK follows terminal transaction outcome only.
- Audit/event ledgers are append-only where defined.
- Default-disabled DB, write, integration, and canonical capability flags fail
  closed and retain their documented defaults; the workbook compatibility sink
  remains the explicit default-enabled exception.
- Historical FAIL evidence remains immutable; a later PASS supersedes only the
  explicitly corrected acceptance result through linked recovery evidence.
- Backward compatibility remains unless a separate task explicitly retires it.

Production-code details are governed by
[mes_web/AGENTS.md](../../mes_web/AGENTS.md).

## Retained compatibility and known fixtures

- Retained V1 configuration and legacy runtime evidence remain valid
  compatibility history. They are not Canonical V2 semantic mappings.
- The nonproduction source-validation fixture is retained:
  `PHASE5HC-SOURCE-SMOKE-20260715-181940`, release
  `PHASE5HC-SOURCE-RELEASE-20260715-181940`.
- The retained fixture completed OP10 and OP20 and has exact immutable release,
  lifecycle, and binding identity. Its progressed route-release replay is
  verified zero-write.
- The fixture carries `disposable_test=true`, `production_release=false`,
  `exclude_from_analytics=true`, and
  `retention_reason=source_rollout_validation`.
- Future OEE, KPI, analytics, reporting, FERP/MESQL, and generic export
  consumers must exclude the fixture by exact prefix or metadata. The consumer
  filter implementation remains deferred.
- Historical clone names, process IDs, backup paths, hash inventories, test
  matrices, and intermediate FAIL details remain in immutable evidence rather
  than this current-state summary.

Fixture evidence:

- [Source-local functional failure](../runbooks/canonical_v2_source_local_functional_smoke_evidence_20260715.md)
- [Source-local replay recovery](../runbooks/canonical_v2_source_local_release_replay_recovery_evidence_20260717.md)
- [Controlled source HTTP replay](../runbooks/canonical_v2_controlled_release_api_source_http_smoke_evidence_20260719.md)

## Current feature-flag posture

DB, write, integration, and canonical capability defaults remain fail-closed.
The retained workbook sink is the explicit compatibility exception:

| Capability | Environment setting | Default |
| --- | --- | --- |
| Workbook sink | `MES_WEB_EXCEL_ENABLED` | `true` |
| PostgreSQL integration | `MES_WEB_DB_ENABLED` | `false` |
| Work-order DB mirror | `MES_WEB_DB_MIRROR_WORK_ORDERS` | `false` |
| DB failure policy | `MES_WEB_DB_FAIL_OPEN` | `false` |
| DB hooks, shadow reads, and direct reads | `MES_WEB_DB_HOOK_*`, `MES_WEB_DB_SHADOW_READ_*`, `MES_WEB_DB_READ_*` | `false` |
| Station/location read model | `MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED` | `false` |
| Station-execution config read model | `MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED` | `false` |
| Controlled route-release HTTP endpoint | `MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED` | `false` |
| Canonical station commands | `MES_WEB_DB_STATION_EXECUTION_COMMANDS_ENABLED` | `false` |
| Canonical MQTT station adapter | `MES_WEB_MQTT_STATION_EXECUTION_ADAPTER_ENABLED` | `false` |
| Kiosk dynamic actions | `MES_WEB_KIOSK_DYNAMIC_ACTIONS_ENABLED` | `false` |

The MQTT station adapter and Kiosk dynamic actions require the station-command
core. A flag enables only its named surface; it does not grant authentication,
activate MESQL/FERP, authorize source writes, or approve a physical field test.
Live environment values must be checked separately before operation.

## Explicitly deferred capabilities

- Phase 6B implementation and its still-undefined canonical scope.
- Production station-execution rollout against source `mes` or a physical
  MQTT broker.
- MESQL development, push/pull, or source-of-truth transition.
- FERP production mapping, acknowledgement, retry, and export rollout.
- Inventory movement/balance and stock authority.
- Automatic route selection, explicit-existing-operation release mode,
  reroute, cancellation, backfill, adoption, and reconciliation.
- Generalized manual-close/approval-close lifecycle bridging.
- Public/untrusted route-release or station-command exposure and its required
  authentication/authorization design.
- Canonical station-event OEE/KPI analytics and the mandatory retained-fixture
  exclusion filter.
- Generalized virtual-plant/digital-twin runtime and autonomous agent analytics
  or decision logic.
- Broad UI redesign and unrelated refactoring.

Deferred means neither implemented nor authorized.

## Canonical acceptance and evidence links

### Station/location

- [Migration evidence](../runbooks/station_locations_migration_evidence_20260706.md)
- [Station-name cleanup evidence](../runbooks/station_name_encoding_cleanup_evidence_20260707.md)
- [Read-model smoke](../runbooks/station_location_read_smoke_evidence_20260707.md)
- [API smoke](../runbooks/station_location_api_smoke_evidence_20260707.md)
- [Tier 1 CI evidence](../runbooks/station_location_api_tier1_ci_evidence_20260707.md)
- [Kiosk UI smoke](../runbooks/station_location_kiosk_ui_smoke_evidence_20260707.md)
- [Kiosk visual evidence](../runbooks/station_location_kiosk_manual_visual_evidence_20260707.md)

### Station-execution foundation and Canonical V2

- [Schema apply](../runbooks/station_execution_schema_migration_evidence_20260709.md)
- [V1 seed apply](../runbooks/station_execution_seed_minimal_evidence_20260709.md)
- [Config helper smoke](../runbooks/station_execution_config_read_smoke_evidence_20260709.md)
- [Config API smoke](../runbooks/station_execution_config_read_api_smoke_evidence_20260709.md)
- [Bound runtime initialization historical failure](../runbooks/station_execution_canonical_v2_bound_runtime_init_isolated_smoke_evidence_20260714.md)
- [Bound runtime initialization retry](../runbooks/station_execution_canonical_v2_bound_runtime_init_retry_evidence_20260715.md)
- [Canonical V2 OP10 execution](../runbooks/station_execution_canonical_v2_op10_execution_isolated_smoke_evidence_20260715.md)

### Binding, release, and completion bridge

- [Binding migration](../runbooks/work_order_route_operation_binding_migration_isolated_smoke_evidence_20260714.md)
- [Binding reads](../runbooks/work_order_route_operation_binding_read_helper_isolated_smoke_evidence_20260714.md)
- [Binding writes](../runbooks/work_order_route_operation_binding_write_helper_isolated_smoke_evidence_20260714.md)
- [Release schema](../runbooks/work_order_route_release_migration_isolated_smoke_evidence_20260715.md)
- [Release read model](../runbooks/work_order_route_release_read_helper_isolated_smoke_evidence_20260715.md)
- [Release writer](../runbooks/work_order_release_writer_isolated_smoke_evidence_20260715.md)
- [Completion-bridge historical failure](../runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_evidence_20260715.md)
- [Completion-bridge retry](../runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_retry_evidence_20260715.md)

### Controlled source and HTTP rollout

- [Source schema/seed apply](../runbooks/canonical_v2_source_schema_seed_apply_evidence_20260715.md)
- [Source functional historical failure](../runbooks/canonical_v2_source_local_functional_smoke_evidence_20260715.md)
- [Source replay recovery](../runbooks/canonical_v2_source_local_release_replay_recovery_evidence_20260717.md)
- [HTTP clone historical failure](../runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_evidence_20260719.md)
- [HTTP clone logging recovery](../runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_recovery_evidence_20260719.md)
- [HTTP source progressed replay](../runbooks/canonical_v2_controlled_release_api_source_http_smoke_evidence_20260719.md)

### Phase 6A

- [Final station-integration acceptance](../runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md)

The curated navigation registry for canonical, active, and high-value
historical design/runbook/evidence documents is maintained in
[docs/INDEX.md](../INDEX.md). It is not an exhaustive inventory of every
tracked Markdown artifact; use the repository tree or `git ls-files '*.md'`
for that technical inventory.

## Current phase boundary

Phase 6A station integration is `VERIFIED` at
`ae023142058a0a5fa79c6b99e257097abbde8dd1`.

Phase 6B implementation is `NOT_STARTED`. The repository does not define one
approved Phase 6B implementation scope. Before work begins, the task scope,
canonical design, database and migration impact, source/physical-broker policy,
focused tests, acceptance criteria, and stop conditions must be explicitly
approved.

See [Phase 6B Entry](PHASE_6B_ENTRY.md).

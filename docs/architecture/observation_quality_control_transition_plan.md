# Observation and Quality Control Transition Plan

## Status

`ACCEPTED_FOR_TRANSITION_PLANNING`

Plan date: 2026-07-10.

This is a non-executable plan. It creates no SQL, seed, route, station,
work-order, runtime, approval, or lifecycle changes.

## Transition Goal

Move future work-order operation instances from the V1 combined identifier
`OPERATOR_OBSERVATION_APPROVAL` to the canonical regular step
`PROCESS_END_OBSERVATION`, while keeping final approval at operation policy and
audit level and representing optional quality control as a separate route
operation.

## Historical Preservation

- Do not rewrite historical evidence files.
- Do not mutate existing operation-event ledger records.
- Do not rename an existing runtime step instance.
- Do not silently overwrite the V1 route configuration.
- Do not start or finish the retained pending V1 step as part of this work.
- Preserve the relationship between historical config, runtime snapshots,
  events, and evidence paths.

## Versioned Configuration

Recommended approach:

```text
Create a new route/config version.
Keep V1 for historical and in-flight instances.
Bind new work-order operation instances to the canonical version.
```

The new version must use new stable configuration identifiers. It must not
update the existing V1 row through an idempotent upsert conflict path.

## Option A - Rename the Seed Row in Place

Decision: `REJECTED`

Risks:

- Historical traceability would no longer match committed evidence.
- An existing runtime instance could disagree with its originating config.
- Event and evidence references to the old identifier would become ambiguous.
- Reapplying an idempotent seed could unexpectedly mutate live configuration.
- Rollback would require reconstructing which work orders saw which semantics.

## Option B - Create a Versioned Route/Configuration

Decision: `RECOMMENDED`

Benefits:

- Historical and in-flight V1 behavior is preserved.
- New work orders can use the canonical semantic model.
- The retained runtime baseline is not disturbed.
- Rollback, A/B comparison, and audit are straightforward.
- Quality-control operations can be added only to route versions that need
  them.

## Target Prototype Configuration

Future versioned target for the existing production operation:

```text
1. COLOR_SENSOR_ENTRY_EVIDENCE
   start_mode = auto_start
   finish_mode = auto_finish

2. ROBOT_ARM_DROP_COMPLETED
   start_mode = implicit_start
   finish_mode = auto_finish

3. PROCESS_END_OBSERVATION
   step_name = Proses Sonu Gözlem
   start_mode = manual_start
   finish_mode = manual_finish
   records_duration = true
   required_for_completion = true
   approval_required_after_finish = false
   actor_type = operator
```

Recommended operation policy:

```text
auto_close_on_required_steps
```

Rationale: the operator has already completed an explicit, timed observation;
showing the same operator another approval or close action adds no independent
control. Alternatives remain valid configuration choices:

- `manual_close`: use when an explicit operation close is required after all
  steps. Required-step completion first moves execution to
  `evidence_completed`; it does not leave execution `active`.
- `auto_complete_pending_approval`: use when a distinct authorized approver
  must create an `operation_approvals` audit record before close.

For all policy choices, `evidence_completed_at` comes from the triggering
`step_finish` event. Auto-close also sets `closed_at` to that time;
pending-approval also sets `pending_final_approval_at` to that time. The
triggering event remains `last_event_id`; no extra `system_transition` event is
created. `approval_required_after_finish` does not override the operation
policy.

## Optional Quality-Control Route

For route versions requiring distinct quality work, model it independently:

```text
OP10_ASSEMBLY_CLASSIFICATION
Station: ASSEMBLY_01

-> OP15_QUALITY_CONTROL
   Station: QUALITY_01
   Steps:
   - QUALITY_CHECK_START
   - DIMENSION_MEASUREMENT
   - VISUAL_DEFECT_CHECK
   - QUALITY_RESULT_ENTRY

-> OP20_PACKAGING
   Station: PACKAGING_01
```

This example is not to be added to the current seed or database in this
checkpoint.

## Preparation Gates

Before any implementation phase:

1. Confirm the retained V1 operation and pending step are not candidates for
   config mutation.
2. Select new route/config identifiers and increment the route version.
3. Define how new work orders select the new version; prohibit rebinding
   existing work-order operations.
4. Confirm the config read model returns both V1 and the new version without
   identifier collision.
5. Define explicit approval roles if
   `auto_complete_pending_approval` is selected.
6. Define quality-operation station, queue, steps, and equipment only for a
   route that actually requires quality control.
7. Obtain separate approval for SQL/seed creation and DB verification.

## Future Implementation Sequence

1. Add a new versioned route/configuration in a dedicated migration or seed
   artifact; do not edit the V1 row in place.
2. Add the canonical observation step only to the production operation that
   needs it.
3. Use generic runtime step handling; do not add a
   `PROCESS_END_OBSERVATION` code branch.
4. Derive Kiosk start/finish actions from runtime step configuration.
5. Keep operation-level approval action separate from the observation action.
6. Run read-only config validation, then isolated new-instance tests.
7. Activate new-version selection only for new work orders.
8. Add quality-control route operations in a later, separately scoped change.

## Verification Plan

For a future implementation, verify:

- V1 route/config rows are digest-equivalent before and after rollout.
- Existing work-order operation and step instance identifiers are unchanged.
- Existing operation-event and approval ledgers are unchanged.
- A new work order resolves to the new config version.
- Observation produces separate waiting and active-duration timestamps.
- Completion follows the selected operation policy.
- If approval is configured, it creates an operation-level audit record rather
  than changing observation semantics.
- A route without quality control does not create a quality operation.
- A route with quality control creates a distinct queue/execution context.
- Existing OEE result/quantity classification remains unchanged.

## KPI Verification

Future reports must calculate:

```text
observation_wait = PROCESS_END_OBSERVATION.started_at
                   - ROBOT_ARM_DROP_COMPLETED.completed_at

observation_active = PROCESS_END_OBSERVATION.completed_at
                     - PROCESS_END_OBSERVATION.started_at

quality_queue_wait = quality_operation.started_at
                     - quality_operation.ready_or_queued_at

quality_active = quality_operation.evidence_completed_or_closed_at
                 - quality_operation.started_at
```

Observation metrics must not be labeled as quality-control metrics.

## Rollback Strategy

- Stop assigning the new route version to new work orders.
- Keep already-created instances bound to their original version; do not rename
  them backward.
- Resume new work-order creation on the prior valid route version only after
  confirming selection policy.
- Preserve events and audit rows; use compensating configuration/version
  selection rather than historical row mutation.
- If the new version has not instantiated any work, it may be deactivated in a
  separately approved change; it must not be deleted silently.

## Non-Goals for This Checkpoint

- Python or API implementation.
- Unit-test changes.
- Applying SQL migration/seed artifacts or changing V1 configuration.
- DB read/write smoke or retained-runtime mutation.
- Kiosk implementation.
- New station or route operation creation.
- IoT adapter, approval, completion-policy, lifecycle, production-flow, or
  inventory implementation.
- MESQL/FERP activity.

## Exit Criteria

- The semantic boundary decision is accepted.
- The V1 identifier is explicitly legacy/current, not globally renamed.
- Versioned configuration is the recommended transition.
- Target observation configuration and policy alternatives are documented.
- Optional quality control is shown only as a separate route operation.
- Historical and retained runtime preservation rules are explicit.
- No implementation or database mutation is performed by this plan.

## Canonical V2 Route/Config Draft

The reviewed additive draft uses these new identities:

```text
route_id = ROUTE_BOX_PACKAGING_V2
route_code = ROUTE_BOX_PACKAGING_V2
version = 2

OP10 route_operation_id = ROUTE_BOX_PACKAGING_V2_OP10
OP10 operation_code = ASSEMBLY_COLOR_CLASSIFY

OP20 route_operation_id = ROUTE_BOX_PACKAGING_V2_OP20
OP20 operation_code = PACKAGING_FINAL
```

The real schema does not make `operation_code` globally unique. It is unique
only within `(route_code, route_version, operation_code)`, so the preferred
canonical codes can be used without V2 suffixes.

### Route Activation Decision

The V2 draft sets the route, route operations, and steps to `active=true`.
Static repository review found no automatic latest-active route selection:

- Route detail lookup requires explicit `route_code + version`; its default
  remains version `1` when the caller omits a version.
- Route-operation detail/config lookup requires explicit
  `route_operation_id`.
- `initialize_execution_state` requires an explicit `route_operation_id`.
- No current work-order create/release path selects the latest active route.

V2 will therefore be visible in active read lists but cannot be selected for a
runtime instance without an explicit identifier. Implementing and validating
new work-order selection remains a separate future phase. If that future
selection behavior changes, this activation decision must be reviewed before
SQL apply.

### Canonical V2 OP10

```text
ROUTE_BOX_PACKAGING_V2_OP10
station = ASSEMBLY_01
policy = auto_close_on_required_steps
output_location_role = output_buffer
scrap_location_role = null

10 COLOR_SENSOR_ENTRY_EVIDENCE
   auto_start + auto_finish
   COLOR_SENSOR_ENTRY -> COLOR_SENSOR_ENTRY

20 ROBOT_ARM_DROP_COMPLETED
   implicit_start + auto_finish
   null -> ROBOT_ARM_DROP

30 PROCESS_END_OBSERVATION
   manual_start + manual_finish
   KIOSK_OPERATOR -> KIOSK_OPERATOR
   records_duration = true
   required_for_completion = true
   approval_required_after_finish = false
```

### Canonical V2 OP20

```text
ROUTE_BOX_PACKAGING_V2_OP20
station = PACKAGING_01
policy = auto_close_on_required_steps
output_location_role = output_good
scrap_location_role = output_scrap

10 PACKAGING_EXECUTION
   manual_start + manual_finish
   KIOSK_OPERATOR -> KIOSK_OPERATOR
   records_duration = true
   required_for_completion = true
   approval_required_after_finish = false
```

V2 contains no final-approval step and no quality-control route operation.
Final approval, if required by a future factory configuration, remains an
operation-policy/audit concern. Quality control remains an optional separate
route operation for a route version that explicitly needs it.

Process-end observation is not a scrap decision, and `ASSEMBLY_01` has no real
configured scrap output. Rework, scrap, and quality-control routes remain
explicit future configuration. An optional capability must not require a
physical binding that the operation does not configure.

Draft artifacts:

- SQL:
  `db/migrations/006_station_execution_seed_canonical_v2.sql`
- Apply runbook:
  `docs/runbooks/station_execution_canonical_v2_seed_apply_runbook.md`

The SQL is additive and idempotent-by-insert-absence with exact-shape
assertions. It reuses existing items, stations, station event sources,
locations, and bindings. It has not been applied to any database. V1 config,
retained V1 runtime, and historical evidence remain unchanged.

Artifact and row metadata status are intentionally distinct:

- Repository artifact status: reviewed seed draft, not applied to source DB.
- Inserted config metadata:
  `configuration_status = canonical_v2`.

The inserted metadata identifies canonical configuration semantics; it does
not claim that the source database has received the seed.

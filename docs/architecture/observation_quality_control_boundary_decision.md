# Observation and Quality Control Boundary Decision

## Status

`ACCEPTED_FOR_TRANSITION_PLANNING`

Decision date: 2026-07-10.

This document is a design checkpoint. It does not apply a migration, seed,
runtime mutation, route change, station change, or lifecycle change.

## Context

The station-execution model already supports ordered operation steps,
configuration-driven start and finish modes, duration recording, completion
requirements, and operation-level completion policies. The current V1 demo
seed combines operator, observation, and approval semantics in the identifier
`OPERATOR_OBSERVATION_APPROVAL`. A retained runtime instance and historical
evidence use that identifier, so its meaning cannot be corrected safely by an
in-place rename.

The target model must remain adaptable to shops where process-end observation
is present, absent, automatic, manual, timed, or non-blocking, and to shops
where quality control is a distinct routed activity.

## Problem

Observation, quality control, final approval, operation closure, and work-order
closure are different concepts with different ownership and timing. Combining
them in one step name or one Kiosk action creates ambiguous audit records,
misleading KPIs, and unsafe migration behavior.

Repository inventory on 2026-07-10 found:

| Category | Finding |
| --- | --- |
| Active seed/config | `db/migrations/005_station_execution_seed_minimal.sql` contains the V1 `OPERATOR_OBSERVATION_APPROVAL` row with approval coupled to the step. |
| Runtime implementation | `mes_web/db/mesql_v2.py` handles generic step policy fields, including `approval_required_after_finish`; no runtime branch keyed to the legacy step code was found. |
| Tests | `tests/test_mes_web_mesql_v2.py` tests generic policy and approval-table behavior; no fixture keyed to the legacy step code was found. |
| Architecture | Station execution model, runtime, seed, and Kiosk design documents describe V1 combined semantics and need a forward-looking clarification. |
| Historical evidence | Station execution seed/runtime/event/start/finish/robot smoke evidence records the V1 identifier and must remain unchanged. |
| Current state | `docs/architecture/CURRENT_STATE.md` records the retained pending V1 runtime step. |
| UI/Kiosk | Current design derives labels from generic policy; target observation and operation approval actions must be labeled separately. |
| Legacy unrelated quality | Existing OEE `GOOD` / `REWORK` / `SCRAP`, quality override, good quantity, and scrap quantity behavior is result classification, not the routed quality-control operation defined here. |

## Canonical Terms

- `PROCESS_END_OBSERVATION`: optional regular step inside a production
  operation; Turkish display name: `Proses Sonu Gözlem`.
- `QUALITY_CONTROL`: optional separate route operation, potentially assigned to
  a dedicated quality station and containing its own operation steps.
- Final approval: an operation-level audit/authorization decision represented
  through `mes.operation_approvals` and completion policy.
- Operation close: a state transition selected by
  `operation_completion_policy` after required steps are complete.
- Work-order close: a separate lifecycle decision after all required route
  operations are complete.

## Process-End Observation

Process-end observation is a normal operation step, not a quality operation and
not final approval. Its presence is defined by configuration:

```text
An active PROCESS_END_OBSERVATION row exists in mes.operation_steps
-> observation exists for that route operation.

No such row exists
-> no observation is required by that configuration.
```

It needs no special engine branch and no dedicated boolean column. The existing
step fields determine its sequence and behavior:

```text
step_no
start_mode
finish_mode
start_event_source_code
finish_event_source_code
required_for_completion
records_duration
approval_required_after_finish
actor_type
active
```

Recommended prototype target:

```text
step_code = PROCESS_END_OBSERVATION
step_name = Proses Sonu Gözlem
start_mode = manual_start
finish_mode = manual_finish
records_duration = true
required_for_completion = true
approval_required_after_finish = false
actor_type = operator
```

This is a prototype seed recommendation, not an engine restriction. Other
valid start/finish combinations remain configuration choices.

## Quality-Control Operation

Quality control is not another name for the observation step. When required,
it is modeled as a separate `route_operation`, with its own queue and execution
state, and it may use a station such as `QUALITY_01`. A route may contain zero,
one, or multiple quality-control operations. Each quality operation may contain
one or more steps and may own its measurement devices, inspectors, and result
evidence.

Example step set inside a quality-control operation:

```text
QUALITY_CHECK_START
DIMENSION_MEASUREMENT
VISUAL_DEFECT_CHECK
QUALITY_RESULT_ENTRY
```

This decision does not add that route operation or station to the current
prototype.

## Final Approval

Final approval is neither process-end observation nor quality control. It is a
separate audit and authorization concern. When required, it is recorded in
`mes.operation_approvals` and coordinated by `operation_completion_policy`.
It is not represented by putting `APPROVAL` in an observation step code or by
changing a manual-finish label to imply an operation-level approval.

## Operation Completion

Operation closure is the state transition that follows completion of required
steps. It is governed by one of the existing policy values:

```text
manual_close
auto_close_on_required_steps
auto_complete_pending_approval
```

The exact required-step completion transitions are:

| Policy | Resulting execution status | Completion timestamps |
| --- | --- | --- |
| `manual_close` | `evidence_completed` | Set `evidence_completed_at`; leave approval/closed timestamps null. |
| `auto_close_on_required_steps` | `closed` | Set equal `evidence_completed_at` and `closed_at`; leave pending-approval timestamp null. |
| `auto_complete_pending_approval` | `pending_final_approval` | Set equal `evidence_completed_at` and `pending_final_approval_at`; leave `closed_at` null. |

Each timestamp comes from the triggering `step_finish` event. The same event is
retained as `last_event_id`; no additional system-transition event is required.
`started_at` and `last_approval_id` are preserved. The operation policy is the
canonical authority; `approval_required_after_finish` is V1 compatibility
metadata and cannot independently select a pending-approval transition.

For the target prototype, `auto_close_on_required_steps` is recommended. The
operator already performs a manual start and finish for process-end
observation, so an additional approval or close action for the same operator
would be redundant. `manual_close` remains available when an explicit close is
needed. `auto_complete_pending_approval` remains available when a separate
authorized approval is required.

## Work-Order Closure

Work-order closure is not operation closure. It is a future lifecycle/work-order
policy applied after all required route operations are complete. No work-order
closure implementation is part of this checkpoint.

## SQL-Driven Flexibility

Observation is added, removed, reordered, timed, or made optional by changing
versioned operation-step configuration, not Kiosk or engine code. Kiosk actions
are derived dynamically from the current runtime step and its configured
start/finish modes. A manual observation can therefore produce normal start and
finish actions without a special observation endpoint or UI branch.

## Current V1 Legacy Identifier

`OPERATOR_OBSERVATION_APPROVAL` is classified as a legacy/current V1 seed
identifier. It remains valid for existing V1 configuration, retained runtime
instances, and historical evidence. This classification does not make it the
canonical name for new configurations.

## Target Canonical Model

Recommended prototype operation step sequence:

```text
1. COLOR_SENSOR_ENTRY_EVIDENCE
   auto_start + auto_finish

2. ROBOT_ARM_DROP_COMPLETED
   implicit_start + auto_finish

3. PROCESS_END_OBSERVATION
   manual_start + manual_finish
   records_duration = true
   required_for_completion = true
   approval_required_after_finish = false
```

Recommended operation policy:

```text
auto_close_on_required_steps
```

The canonical model is a target for a future versioned configuration. It has
not been applied to the current seed or database.

## Route Examples

Simple prototype without a separate quality operation:

```text
OP10_ASSEMBLY_CLASSIFICATION
  - COLOR_SENSOR_ENTRY_EVIDENCE
  - ROBOT_ARM_DROP_COMPLETED
  - PROCESS_END_OBSERVATION
-> OP20_PACKAGING
```

Advanced route with optional quality control:

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

`PROCESS_END_OBSERVATION` is a step inside OP10; it is not a route operation.
`OP15_QUALITY_CONTROL` is a route operation; it is not reduced to a normal
observation step.

## Timing and KPI Semantics

For the production operation:

```text
Robot completion time
= ROBOT_ARM_DROP_COMPLETED.completed_at

Observation waiting duration
= PROCESS_END_OBSERVATION.started_at
  - ROBOT_ARM_DROP_COMPLETED.completed_at

Active observation duration
= PROCESS_END_OBSERVATION.completed_at
  - PROCESS_END_OBSERVATION.started_at
```

When quality control is a separate operation:

```text
Quality queue waiting duration
= quality operation started_at
  - quality operation ready/queued time

Active quality process duration
= quality operation evidence_completed/closed time
  - quality operation started_at
```

Observation metrics must not be reported as quality-control metrics. Existing
OEE result/quantity semantics also remain separate unless a future, explicit
mapping decision relates them.

## Historical Data and Compatibility

- Historical evidence documents are immutable records of the verified V1 state
  and keep the legacy identifier.
- Existing event-ledger rows and runtime step instances are not renamed.
- Existing V1 route configuration is not silently overwritten.
- The retained pending V1 step is not started or finished by this work.
- Readers may map the legacy identifier to the target concept for reporting,
  but stored historical identifiers remain unchanged.

## Transition Strategy

Create a new route/configuration version for future work orders. Preserve V1
for historical and in-flight instances. Bind only new work-order operations to
the canonical configuration after a separately reviewed migration/seed and
runtime rollout. Detailed gates and rollback are defined in
`docs/architecture/observation_quality_control_transition_plan.md`.

## Rejected Alternatives

- Rename the V1 seed row in place: rejected because it breaks traceability and
  may mutate config beneath an active runtime instance.
- Add `has_observation` or another special boolean: rejected because row
  presence and existing step-policy columns already express the behavior.
- Model observation as a quality operation: rejected because it conflates a
  production-step observation with routed quality work.
- Model quality control as a renamed observation step: rejected because it
  loses queue, station, execution, staffing, and measurement boundaries.
- Embed final approval in the observation step: rejected because approval is an
  operation-level audit/completion-policy concern.

## Implementation Phases

1. Documentation and concept inventory: this checkpoint.
2. Review and name a new route/config version; define compatibility assertions.
3. Add separately approved versioned seed/migration artifacts without mutating
   V1.
4. Verify config/read-model behavior without touching retained V1 runtime.
5. Create only new work-order operations from the canonical configuration.
6. Add separate quality-control route operations only for routes that require
   them.
7. Implement work-order closure policy in an independent lifecycle phase.

## Acceptance Criteria

- Observation is described only as an optional regular operation step.
- Quality control is described only as an optional separate route operation
  with its own steps.
- Approval is described as a separate audit/completion-policy concern.
- `PROCESS_END_OBSERVATION` is not modeled as a route operation.
- `QUALITY_CONTROL` is not reduced to an observation step.
- Observation presence is controlled by an operation-step row and existing
  policy columns; no special engine flag or branch is introduced.
- The target observation has `approval_required_after_finish = false`.
- V1 evidence, runtime instances, and seed configuration remain unchanged.
- No code, test, migration, seed, database, Kiosk, API, or lifecycle mutation is
  claimed by this decision.

## Decision

Observation is an optional regular operation step.
Quality control is an optional separate route operation with its own steps.
Approval is a separate audit and completion-policy concern.

Adopt `PROCESS_END_OBSERVATION` as the target canonical observation step code
for new versioned configurations. Preserve `OPERATOR_OBSERVATION_APPROVAL` as a
V1 legacy/current identifier and transition only through a new configuration
version.

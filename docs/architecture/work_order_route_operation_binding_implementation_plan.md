# Work-Order Operation / Route-Operation Binding Implementation Plan

## Objective

Implement the accepted explicit mapping:

`work_order_operation_id -> route_operation_id`

The implementation must preserve the Runtime Engine V0 sidecar boundary,
support V1/V2 coexistence, and eliminate production inference from station,
operation code, sequence, or latest-active route.

This file is a plan only. It contains no migration SQL or Python
implementation.

## Preconditions

- Approve
  `docs/architecture/work_order_route_operation_binding_decision.md`.
- Preserve `work_order_operation_id` as lifecycle/runtime instance identity.
- Preserve `route_operation_id` as versioned config identity.
- Keep source `mes`, retained V1 runtime, existing lifecycle operations, and
  V1/V2 seeds unchanged until each implementation phase is separately
  approved.
- Use additive migrations and disposable dump/restore clones for PostgreSQL
  verification.
- Do not combine binding work with work-order close, inventory, approval,
  production-flow, Kiosk, IoT, OEE, MESQL, or FERP changes.

## Proposed Schema

Future additive table:

`mes.work_order_operation_route_bindings`

Planned fields:

- Surrogate local primary key following `004_station_execution_schema.sql`
  conventions.
- Stable unique `binding_id`.
- Unique `work_order_operation_id` UUID FK.
- `route_operation_id` text FK.
- Controlled `binding_source`.
- Nonblank `bound_by` actor/service identity.
- `bound_at` semantic timestamp.
- JSON metadata for non-identity correlation/audit context.
- `created_at` storage timestamp.

Do not add `active`, `updated_at`, soft-delete, effective-date, or supersession
fields in the MVP. The accepted model is insert-once and immutable.

Required constraints and indexes:

- Unique binding public ID.
- Unique lifecycle operation ID.
- FK to `mes.work_order_operations(work_order_operation_id)`.
- FK to `mes.route_operations(route_operation_id)`.
- Controlled source check.
- Lookup index by `route_operation_id` for audit/reverse inspection.

The migration must not alter existing lifecycle or runtime tables.

## Migration Strategy

Phase 1 - additive binding schema:

1. Precheck real migration ordering and table/constraint names.
2. Create only the sidecar table, constraints, and indexes.
3. Do not backfill legacy rows.
4. Verify a second apply is idempotent or fails only by the repository's
   accepted migration convention.
5. Verify V1/V2 config and all lifecycle/runtime table counts and digests are
   unchanged.
6. Apply only to disposable clones before any separately approved source apply.

No destructive rollback SQL should be embedded. Operational rollback disables
new readers/writers while retaining the additive audit table.

## Read Helpers

Phase 2 - read-only binding helpers:

- `get_work_order_operation_route_binding(config, work_order_operation_id)`:
  return one binding or `None`.
- `get_route_operation_for_work_order_operation(...)`: join the binding to the
  exact route-operation definition.
- Optional audit helper to list bindings by work order through a join to
  `mes.work_order_operations`; do not duplicate `order_id` in the binding table
  unless implementation evidence proves it necessary.

Every helper must:

- Normalize identifiers without guessing them.
- Use SELECT-only SQL.
- Return binding source/actor/timestamps and route identity.
- Distinguish missing lifecycle operation, missing binding, and broken FK/data
  integrity conditions.
- Never fall back to station, operation code, sequence, or latest-active route.

## Write Helpers

Phase 3 - controlled binding write helper:

Proposed behavior for
`create_work_order_operation_route_binding(...)`:

1. Require exact lifecycle operation ID, route-operation ID, source, and actor.
2. Lock or otherwise serialize the lifecycle operation/binding lookup.
3. Load both referenced records.
4. Validate station agreement.
5. Validate selection context supplied by the caller, including explicit route
   code/version when invoked from release.
6. Insert one immutable binding.
7. On same-pair replay, return the existing row with `created=false`.
8. On different-pair replay, return a conflict and write nothing.

The helper must not update or delete a binding. It must not copy identity from
mutable metadata or infer a mapping.

Initially supported sources should be limited to the phase that owns the call:

- `manual_setup` for controlled setup tests.
- `work_order_release` when Phase 5 is implemented.
- `migration_backfill` only after separate Phase 7 approval.

## Validation Rules

- Lifecycle operation exists.
- Route operation exists.
- Work-order operation is not terminal for a new operational binding unless a
  separately approved migration-backfill workflow applies.
- Lifecycle station equals route-operation station.
- Release-supplied route code/version equals the route operation's parent.
- All bindings created for one release belong to the selected route
  code/version.
- Existing binding with same pair is idempotent.
- Existing binding with different pair is a deterministic conflict.
- Existing runtime state, runtime steps, operation event, approval, or
  production-flow evidence prevents any correction attempt.
- No validation uses operation-code equality as identity. New release may copy
  canonical codes into newly created lifecycle rows, but the binding remains
  authoritative.

Suggested error categories for later implementation review:

- lifecycle operation not found;
- route operation not found;
- binding required;
- binding conflict;
- station mismatch;
- selected route mismatch;
- binding immutable.

## Work-Order Release Integration

Phase 5 - implement release as one transaction:

1. Accept product/item plus explicit `route_code + version`, or an already
   resolved explicit route identity.
2. Validate the selected route and item relationship.
3. Read its active route operations in sequence.
4. Create lifecycle `work_order_operations` from those definitions.
5. Create one `work_order_release` binding per lifecycle operation.
6. Create/update station queue rows using the lifecycle operation IDs.
7. Commit work-order operations, bindings, and initial queue state together.

After selection, the transaction must not re-query latest-active route.
Failure to create any binding must roll back the complete release.

Existing `upsert_mesql_queue_items` is an integration mirror, not this target
release flow. Do not silently attach inferred bindings to its imported legacy
operation codes.

## Runtime Init Integration

Phase 4 - transition validation:

- Keep the existing
  `initialize_execution_state(config, work_order_operation_id,
  route_operation_id, station_code, actor_id=None)` signature.
- Look up the persistent binding before runtime writes.
- If a binding exists, require exact route-operation equality with the explicit
  parameter.
- Reject a mismatch before execution-state or step inserts.
- Treat an absent binding as transitional smoke-only compatibility until the
  release path is ready; do not infer or auto-create a binding inside runtime
  init.

Target behavior after Phase 5:

- Production runtime init starts from `work_order_operation_id`.
- Binding lookup supplies `route_operation_id`.
- Config and station validation use the bound route operation.
- Missing binding fails before mutation.
- The production caller no longer chooses config independently.

## Existing Helper Compatibility

- Preserve current public signature during transition.
- Preserve existing idempotent return behavior for an already initialized
  operation only when its stored runtime route context agrees with the binding
  and explicit parameter.
- Add a regression for the currently uncovered case where an existing runtime
  state is called with a different route-operation parameter.
- Step start/finish may continue to read execution-state metadata in the
  transition, but that metadata must be created from the verified binding.
- A later cleanup may expose bound route identity as a physical runtime column;
  that is not required by this plan and needs separate schema review.

## Legacy Data Strategy

- Default state: `unbound legacy`.
- Do not rename Canonical V2 operation codes.
- Do not infer mapping from station, code, sequence, or combinations of them.
- Do not bind or modify the retained V1 runtime.
- Provide read-only reporting of unbound operations before considering
  backfill.
- Phase 7 can bind only evidence-backed, unambiguous records through a
  separately approved controlled workflow.
- Ambiguous records remain unbound permanently unless stronger source evidence
  is supplied.

## Unit Tests

Phase-specific tests should cover:

- Binding row mapping and JSON safety.
- Read helper returns `None` for no binding and never invokes inference SQL.
- Same-pair create is idempotent.
- Conflicting-pair create fails without insert/update/delete.
- Missing lifecycle/config records fail explicitly.
- Station and selected-route mismatch fail explicitly.
- Source and actor validation.
- Runtime init accepts matching binding/explicit parameter.
- Runtime init rejects conflicting parameter before writes.
- Runtime init target path resolves config from binding.
- Existing runtime metadata mismatch is detected.
- No write helper touches work orders, lifecycle operations, queue, config,
  events, approvals, production flow, locations, or bindings other than the
  single intended binding insert.

Existing `tests/test_mes_web_mesql_v2.py` contracts for config read, runtime
init, event ledger, step start/finish, completion policy, and lifecycle
start/complete must remain green.

## Isolated PostgreSQL Tests

For each write-enabled phase:

1. Capture source count/digest baseline for config, binding, runtime, audit,
   lifecycle, queue, and location tables.
2. Create a logical `pg_dump` backup.
3. Restore into an empty exact-name disposable clone; never use
   `TEMPLATE mes`.
4. Verify clone/source counts and digests before changes.
5. Apply the additive migration only to the clone.
6. Create a fresh test work-order operation only through the phase's approved
   workflow; never mutate retained V1 evidence.
7. Verify binding create, same-pair replay, and conflicting-pair rejection.
8. Verify runtime init uses the bound route operation and creates only allowed
   sidecar runtime rows.
9. Verify V1/V2 config and unrelated lifecycle/location digests remain
   unchanged.
10. Drop the exact clone and prove source final integrity.

Phase 6 must use a newly created/released Canonical V2 work order. It must not
repurpose legacy `OP-ASSEMBLY` rows.

## Rollout

1. Land Phase 1 schema with read-only verification.
2. Land Phase 2 helpers behind no production caller.
3. Land Phase 3 controlled writer and isolated tests.
4. Land Phase 4 runtime mismatch validation while preserving transition
   compatibility.
5. Land Phase 5 explicit work-order release and require bindings for new work.
6. Run Phase 6 Canonical V2 end-to-end smoke on disposable clone first.
7. Review evidence before any source DB apply or production-path enablement.

## Rollback

- Disable new binding consumers/writers by reverting the corresponding code
  phase.
- Retain the additive table and immutable rows as audit data.
- Do not drop the table, delete rows, or clear bindings as an automatic
  rollback.
- Existing lifecycle and queue behavior remains the fallback until target
  enforcement is separately enabled.
- If a phase writes incorrect bindings, stop rollout and design an audited
  correction workflow; do not update rows in place.

## Guardrails

- No inference implementation.
- No automatic latest-active selection after release.
- No lifecycle-table FK alternative unless a separately documented technical
  blocker invalidates the sidecar design.
- No legacy backfill before Phase 7 approval.
- No mutation of retained V1 runtime or historical evidence.
- No binding update/delete or soft rebind.
- No coupling with work-order close, approval, production flow, inventory,
  API/Kiosk/IoT/OEE, MESQL, or FERP scope.
- No source database apply without a dedicated approved runbook and isolated
  evidence.

## Exit Criteria

Phase 1 - additive binding schema:

- Constraints and indexes verified; no backfill; all existing digests
  preserved.

Phase 2 - read-only binding helpers:

- SELECT-only and no inference; missing/bound results covered.

Phase 3 - controlled binding write helper:

- Same-pair idempotency and conflicting-pair no-write proved.

Phase 4 - runtime-init binding validation:

- Matching binding passes; mismatch fails before any runtime write.

Phase 5 - work-order release integration:

- Explicit route version, lifecycle operation creation, bindings, and queue
  commit atomically.

Phase 6 - new-work-order V2 end-to-end smoke:

- Fresh V2 work order binds OP10/OP20 correctly and runtime initialization
  resolves OP10 from binding without inference.

Phase 7 - optional legacy backfill:

- Separately approved evidence and correction policy exist; ambiguous legacy
  rows remain unbound.

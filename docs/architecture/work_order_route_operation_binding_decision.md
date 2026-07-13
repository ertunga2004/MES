# Work-Order Operation / Route-Operation Binding Decision

## Status

`ACCEPTED_FOR_IMPLEMENTATION_PLANNING`

This document is an architecture decision only. It does not authorize or
implement a migration, Python change, database apply, lifecycle backfill, or
runtime mutation.

## Context

The lifecycle and station-execution configuration models use different
identities:

- `work_order_operation_id` identifies one concrete operation instance in one
  work order.
- `route_operation_id` identifies one operation definition in one versioned
  process route.

Canonical V2 seed apply, idempotency, and the V1/V2 config read model passed on
a disposable PostgreSQL clone. Runtime initialization could not proceed because
the clone had no eligible lifecycle operation whose business operation code was
the Canonical V2 code `ASSEMBLY_COLOR_CLASSIFY`. Existing examples used codes
such as `OP-ASSEMBLY` and `OP-MVP-ASM`.

Changing Canonical V2 codes or inferring a route operation from legacy strings
would hide the missing identity relationship. The correct solution is to make
that relationship explicit.

## Blocker

The retry evidence in
`docs/runbooks/station_execution_canonical_v2_isolated_apply_runtime_init_retry_evidence_20260710.md`
records:

- V2 first apply: PASS.
- V2 reapply: PASS and idempotent.
- V1/V2 read-model coexistence: PASS.
- Eligible runtime candidate count: 0.
- Runtime helper calls: 0.
- Source `mes`: unchanged.

The blocker is therefore not seed shape, config validation, or read-model
visibility. Existing lifecycle operation instances are not persistently bound
to versioned route-operation definitions.

## Existing Identity Model

`db/migrations/004_station_execution_schema.sql` defines a globally unique
`mes.route_operations.route_operation_id`. Its parent route identity is
`route_code + route_version`; sequence and operation code are unique only
inside that route version.

`db/migrations/008_mesql_integration_v2.sql` defines
`mes.work_order_operations.work_order_operation_id` as the lifecycle instance
identity. It stores operation number, operation code, sequence, station, and
lifecycle quantities/status, but no route-operation reference.

These identities serve different purposes and must remain distinct.

## Repository Inventory

Work-order level:

- `db/migrations/001_initial_mes_schema.sql` stores `product_code` and order
  lifecycle data in `mes.work_orders`.
- It has no `route_code`, `route_version`, or route-selection reference.
- `mes_web/db/work_order_mirror.py::build_work_order_mirror_rows` mirrors
  product and lifecycle data without selecting a process route.
- No repository implementation of `create_work_order` or `release_work_order`
  performs explicit or latest-active route selection.

Work-order-operation level:

- `db/migrations/008_mesql_integration_v2.sql` has no `route_operation_id`,
  `route_code`, or `route_version` column.
- `mes_web/db/mesql_v2.py::_build_operation_params` imports
  `operation_code`, `sequence_no`, and station from an external queue payload.
- `UPSERT_OPERATION_SQL` can update operation code, sequence, station, and
  mutable metadata on conflict. Those values are lifecycle/business data, not
  immutable config identity.
- The schema permits multiple route operations for one station; it has an
  index, not a uniqueness constraint, on station. V1 and V2 can also expose
  different active route operations at the same station.

Queue level:

- `db/migrations/006_station_queue.sql` originally identifies a station and
  work order.
- `db/migrations/008_mesql_integration_v2.sql` additively links a queue row to
  `work_order_operation_id`.
- `mes.station_queue` has no route/config identity.
- `mes_web/db/mesql_v2.py::_build_queue_params` and successor activation carry
  lifecycle operation identity, station, sequence, and status only.

Runtime sidecar level:

- `mes.work_order_operation_execution_state` has no physical
  `route_operation_id` column or route-operation foreign key.
- `mes_web/db/mesql_v2.py::initialize_execution_state` currently accepts an
  explicit `route_operation_id`, loads that config, and stores the identifier
  in execution-state and step metadata only when runtime rows are created.
- The helper validates route-operation existence/config and station agreement,
  but it does not validate a persistent pre-runtime binding or lifecycle
  `operation_code` equivalence.
- Existing-state idempotency does not compare the newly supplied route
  operation with the route ID already stored in runtime metadata.
- Step start/finish later read `route_operation_id` from execution-state
  metadata. This is runtime context after initialization, not a durable
  pre-runtime selection contract.

Existing JSON metadata cannot be reused as the binding because it is mutable,
has no FK, uniqueness, controlled source, or immutable audit guarantee. Runtime
state cannot be reused because it is created too late and is itself a consumer
of the missing selection.

## Required Invariants

- Every bound lifecycle operation references exactly one existing versioned
  route operation.
- One `work_order_operation_id` has at most one binding.
- One `route_operation_id` can be referenced by many lifecycle instances.
- New production bindings are explicit; no station, operation-code, sequence,
  or latest-active inference is permitted.
- A binding preserves the selected route version for the lifetime of the
  operation instance.
- Binding creation validates station consistency and the selected route
  context before runtime initialization.
- A conflicting second binding is rejected without mutation.
- Runtime artifacts and audit evidence never trigger or permit silent rebind.

## Rejected Inference Models

Operation-code inference: `REJECTED`.

- Current lifecycle codes are imported business labels and already differ from
  V1 and V2 config codes.
- `UPSERT_OPERATION_SQL` can update them.
- A code can occur in multiple route versions and is not the versioned config
  identity.

Station-only inference: `REJECTED`.

- The route-operation schema does not make station unique.
- V1 and V2 operations can be active and visible for the same station.
- A station lookup cannot determine a route version.

Sequence-only inference: `REJECTED`.

- Sequence is unique only inside one route version.
- Different routes reuse sequence numbers.
- Rework and optional quality operations can change route ordering.

Latest-active inference: `REJECTED`.

- No current work-order release contract selects or freezes a route version.
- Later activation of V3 must not move a V2-bound operation.

Combining station, operation code, and sequence is also rejected. Combining
several non-identities does not create an immutable identity contract.

## Explicit Binding Options

Manual `route_operation_id` passed only to runtime init:
`SMOKE_ONLY / TRANSITIONAL`.

- It is supported by the current helper and remains useful for controlled
  transition tests.
- It leaves no pre-runtime release audit and allows a caller to supply the wrong
  config unless a persistent binding is checked.

Explicit sidecar binding: `RECOMMENDED`.

- It preserves the Runtime Engine V0 sidecar boundary.
- It works with V1/V2 coexistence and does not alter lifecycle table shape.
- It enables deterministic release, queue-to-runtime resolution, and audit.

Nullable FK on `mes.work_order_operations`: `ALTERNATIVE`.

- It is simple to query but changes the existing lifecycle schema and requires
  compatibility/backfill policy.
- No technical obstacle requiring this alternative was found.

## Recommended Architecture

Add a dedicated sidecar relation named
`mes.work_order_operation_route_bindings` in a separately approved additive
migration.

Conceptual fields:

- `binding_pk`: local surrogate primary key following current schema
  conventions.
- `binding_id`: stable public/audit identifier, unique and nonblank.
- `work_order_operation_id`: lifecycle instance UUID, unique and FK-backed.
- `route_operation_id`: versioned config ID, FK-backed.
- `binding_source`: controlled source value.
- `bound_by`: explicit operator/service actor.
- `bound_at`: semantic binding timestamp.
- `metadata`: non-identity audit context.
- `created_at`: storage audit timestamp.

The MVP uses an insert-once single-row model. It does not need `active`,
`updated_at`, effective-date history, or soft-delete columns. Those fields
would imply correction semantics that are not yet designed.

Minimum constraints:

- Unique `binding_id`.
- Unique `work_order_operation_id`.
- FK from `work_order_operation_id` to `mes.work_order_operations`.
- FK from `route_operation_id` to `mes.route_operations`.
- Controlled `binding_source` values.
- Nonblank `bound_by` and binding identifier.

MVP source values are phase-controlled:

- `manual_setup`: controlled explicit setup helper.
- `work_order_release`: future release transaction.
- `migration_backfill`: reserved for separately approved Phase 7 and not
  enabled as an ordinary write path before then.

Generic `api` or `system` values are not sufficient MVP audit sources; the
actual workflow and actor must remain distinguishable.

## Binding Lifecycle

1. A caller provides the lifecycle operation ID and exact route-operation ID.
2. The write helper loads both records and validates station and selected-route
   context.
3. The helper inserts one immutable binding with actor/source audit.
4. Repeating the same pair is idempotent and returns the existing binding.
5. Supplying a different route-operation ID for an already bound lifecycle
   operation fails with a conflict and writes nothing.
6. Runtime init resolves or validates the binding before creating runtime rows.

The MVP does not update or delete binding rows. A correction model must be a
separately approved design; it must not silently rewrite history.

## Work-Order Release Flow

The target release flow is:

1. Select item/product and an explicit `route_code + version`.
2. Validate that route identity and item compatibility.
3. Read route operations in configured sequence.
4. Create lifecycle work-order operations.
5. Insert one binding for every created lifecycle operation in the same
   transaction.
6. Continue existing lifecycle queue behavior using
   `work_order_operation_id`.
7. Resolve runtime config from the binding when the operation becomes ready.

The release transaction must not query latest-active route again after the
work order has selected a route version. Every operation binding must belong to
the same selected route code/version.

## Runtime Initialization Flow

Transition phase:

- Keep the existing public helper parameters, including explicit
  `route_operation_id`.
- If a binding exists, require an exact match before any runtime write.
- Reject a conflicting parameter with a deterministic conflict error.
- A missing binding can remain a controlled smoke-only compatibility path
  during transition; it must not infer or auto-create a production binding.

Target phase:

- Runtime initialization takes `work_order_operation_id` as its production
  identity.
- An internal binding lookup resolves `route_operation_id`.
- Config validation and runtime row creation use that resolved identity.
- Missing binding is a deterministic precondition failure.
- The explicit route parameter can be removed from the production path only in
  a separately reviewed compatibility change.

## Legacy Operations

Existing lifecycle operations with codes such as `OP-ASSEMBLY` and
`OP-MVP-ASM` remain valid lifecycle records but are unbound unless direct,
reviewable evidence establishes their route operation.

- Canonical V2 codes must not be renamed to match legacy data.
- No station/code/sequence inference backfill is allowed.
- The retained V1 runtime and historical execution metadata remain unchanged.
- An ambiguous legacy record remains `unbound legacy`.
- Any controlled legacy backfill is Phase 7 and requires separate approval and
  evidence.

## Version Preservation

`route_operation_id` pins the definition and its parent route version. The
binding never follows later active versions. Deactivating a route after release
does not rewrite existing bindings; active status is a selection-time rule for
new release, not a historical-reference rule.

## Audit and Immutability

The binding records who bound the instance, when, and through which controlled
workflow. Metadata may hold request/correlation evidence but cannot replace
identity columns.

Once inserted, a binding is immutable in the MVP. This is stricter than the
minimum requirement that immutability begin after runtime state, runtime steps,
operation events, approvals, or production-flow events exist, and avoids an
unaudited pre-runtime correction gap.

## Schema Impact

The recommended change is additive and sidecar-only. It requires a future
migration and indexes for operation lookup and route-operation reverse lookup.
It does not require changing `mes.work_orders`, `mes.work_order_operations`,
`mes.station_queue`, existing runtime tables, V1 seed, or V2 seed.

No schema change is implemented by this decision.

## Compatibility

- Existing unbound lifecycle rows continue to exist.
- Existing start/complete lifecycle behavior continues to use
  `work_order_operation_id` and station queue.
- Existing runtime rows keep their metadata and are not rebound.
- V1 and V2 config read paths remain explicit and coexist.
- Transition runtime init can keep its current signature while adding binding
  conflict validation in a later phase.

## Risks

- Release and binding writes could diverge unless they share one transaction.
- Allowing a missing binding indefinitely would preserve ambiguity; transition
  compatibility needs an explicit removal gate.
- Mutable metadata may be mistaken for authoritative identity unless helpers
  query the binding table exclusively.
- Legacy backfill pressure may encourage inference; Phase 7 must remain
  separately approved.
- A correction requirement may emerge. It must be designed as auditable
  supersession rather than update/delete of the MVP row.

## Implementation Phases

1. Additive binding schema.
2. Read-only binding helpers.
3. Controlled binding write helper.
4. Runtime-init binding validation.
5. Work-order release integration.
6. New-work-order Canonical V2 end-to-end smoke.
7. Optional legacy backfill, separately approved.

Detailed gates are defined in
`docs/architecture/work_order_route_operation_binding_implementation_plan.md`.

## Acceptance Criteria

- One lifecycle operation cannot acquire two route-operation bindings.
- Same-pair replay is idempotent; conflicting-pair replay fails without write.
- FK and helper validation reject missing lifecycle/config identities.
- Station mismatch is rejected.
- Runtime init rejects a route parameter that conflicts with a binding.
- Target runtime init resolves config from binding without inference.
- New release pins an explicit route version and creates all bindings
  transactionally.
- Latest-active, station, operation-code, and sequence inference are absent.
- Legacy unbound data and retained V1 runtime remain unchanged.
- Isolated PostgreSQL tests prove no forbidden lifecycle or config mutation.

## Decision

A work-order operation must be bound explicitly to one versioned route
operation. Station, operation-code, sequence, or latest-active inference must
not be used as the production binding mechanism.

The accepted implementation-planning target is an additive, immutable sidecar
binding relation. The current explicit runtime-init parameter is transitional,
not the production source of truth.

# Runtime-to-Lifecycle Completion Bridge Design

## Status

`READY_FOR_COMPLETION_BRIDGE_IMPLEMENTATION`

Last updated: `2026-07-15`.

This Phase 5F document fixes the design contract only. It creates no Python,
test, migration, database, Docker, API, or feature-flag change.

## Scope

The initial bridge connects an authoritative station-execution runtime close
to the route-released lifecycle state in one PostgreSQL transaction:

```text
runtime execution closes
-> current lifecycle operation completes
-> current queue row becomes terminal
-> exact successor lifecycle operation and queue activate
-> or the final work order completes
```

The bridge supports only lifecycle operations created by an immutable work-
order route release and bound to an exact route-operation definition. Retained
V1 and other legacy operations remain outside this bridge.

## Existing Runtime Completion Path

`finish_execution_step` currently owns one connection, transaction, and
cursor. Its real order is:

1. lock execution state by lifecycle UUID;
2. lock all execution steps by `step_no`;
3. validate route-operation metadata, step config, source, and idempotency;
4. insert one `step_finish` operation event;
5. complete the step;
6. apply the completion policy to execution state;
7. return the current runtime result and commit.

An existing idempotent event currently enters an early response branch before
any lifecycle bridge exists. Phase 5G-B must retain event idempotency but must
not return before bridge classification. Every response must contain the
`completion_bridge` key.

The only implemented automatic close is
`auto_close_on_required_steps -> closed`. `manual_close` stops at
`evidence_completed`, and `auto_complete_pending_approval` stops at
`pending_final_approval`; no public manual-close or approval-close helper
currently exists.

## Existing Lifecycle Completion Path

`complete_operation_v2` is a separate MESQL-era public transaction. It:

- accepts lifecycle quantities and an application completion timestamp;
- completes the lifecycle operation and current queue;
- selects a successor by order/sequence while filtering terminal operations;
- may update or adopt legacy queue rows;
- may complete the work order;
- inserts production completion, work-order event, and outbox rows.

The bridge must not call or copy this orchestration. In particular, the bridge
does not set good/scrap quantities and creates no completion, work-order event,
outbox, approval, production-flow, or inventory record.

## Existing Successor Queue Path

The MESQL-era successor helper is not bridge-safe because it:

- treats station/order legacy queue rows as adoptable;
- upserts and merges queue metadata;
- includes `ready` in rank calculation;
- has no Phase 5D station advisory lock;
- infers the next nonterminal lifecycle row rather than validating the exact
  immutable released set.

The bridge therefore uses dedicated immutable-identity primitives and the
Phase 5D advisory-lock namespace and three-status rank predicate.

## Trigger Contract

The bridge is eligible only when the persisted post-transition execution state
is exactly:

```text
execution_status = closed
closed_at IS NOT NULL
```

The bridge depends on the authoritative state, not on the completion-policy
name. `ready`, `active`, `evidence_completed`, `pending_final_approval`,
`failed`, and `cancelled` do not trigger it.

For the current auto-close path, `closed_at` is the inserted finish event's
persisted `event_time`. Any future manual-close or approval-close transaction
must set authoritative `closed_at` and invoke the same private bridge before
commit.

## Supported Identity Boundary

Applicability is decided before any release or binding sidecar query. The
exact marker is:

```text
lifecycle.metadata.source == "work_order_release"
AND btrim(lifecycle.metadata.release_id) <> ""
```

The initial exact lifecycle row is read only by
`work_order_operation_id`. No station, code, sequence, or latest-route lookup
participates in this gate.

- Marker absent: retained V1/legacy path continues with
  `completion_bridge=None`. Migrations `009` and `010` relations are not
  queried.
- Marker present: first verify both sidecar relations with an explicit schema
  readiness read. If either is absent, raise
  `503 RUNTIME_COMPLETION_BRIDGE_SCHEMA_NOT_READY` before runtime/event writes.
- An `UndefinedTable` is never converted to legacy/not-applicable. If schema
  readiness confirms a missing sidecar, use the deterministic `503`; any
  otherwise unexplained `UndefinedTable` propagates unchanged.
- After readiness, the order must have one exact route release and the current
  lifecycle UUID must have one exact `binding_source=work_order_release`
  binding. Missing, extra, or inconsistent artifacts are conflicts, never
  repair candidates.

Supported identity validation requires:

- release order ID equals lifecycle/runtime work-order ID;
- lifecycle server metadata release/route identity equals the release row;
- complete lifecycle count and complete binding count equal release count;
- recomputed operation-set digest equals the persisted release digest;
- runtime metadata `route_operation_id` equals the current binding;
- runtime work-order, lifecycle UUID, operation code, and station equal the
  current immutable lifecycle snapshot;
- every lifecycle sequence is a unique positive integer.

No config table needs to be reread. No binding backfill, legacy adoption, or
route inference is allowed.

## Transaction Boundary

Production model A is selected: synchronous same-cursor integration.

The bridge-aware `finish_execution_step` transaction performs:

1. validate normalized finish request and read exact lifecycle applicability
   fields;
2. for marker absence, execute the existing legacy runtime flow and return
   `completion_bridge=None` without sidecar access;
3. for marker presence, verify sidecar schema readiness;
4. acquire the normative route-release/runtime locks;
5. validate event idempotency and execute the step/runtime transition;
6. if runtime is not closed, return `completion_bridge=None`;
7. if runtime is closed, classify first bridge, exact replay, or conflict;
8. perform lifecycle/queue/successor or final-order writes;
9. read one authoritative bridge snapshot;
10. return and commit.

Any failure after the finish event insert rolls back the event, execution step,
execution state, lifecycle, queue, and work-order changes together.

## Runtime Helper Integration

The public `finish_execution_step` signature remains unchanged. Its response
receives one additive key on every path:

```python
"completion_bridge": None | {
    "bridged": True | False,
    "execution_state": {...},
    "completed_operation": {...},
    "completed_queue": {...},
    "successor_operation": {...} | None,
    "successor_queue": {...} | None,
    "work_order": {...},
}
```

There is no initial standalone public bridge method. A private cursor-scoped
primitive returns the nested bridge object and opens no connection,
transaction, commit, rollback, or retry.

Duplicate/concurrent event lookup remains idempotent, but its response branch
must continue into bridge classification. For a supported closed operation,
the first committed call returns `bridged=True`; duplicate/concurrent calls
return `bridged=False` with the authoritative current snapshot. Nonclosed,
legacy, and not-applicable calls always return the key with value `None`.

## Lock Ordering

The route-release bridge hierarchy is:

```text
work order row
-> route release row
-> lifecycle rows ordered by lifecycle UUID
-> binding rows ordered by binding PK
-> execution state
-> runtime steps ordered by step_no
-> station advisory locks in lexical station-code order
-> station queue rows ordered by station code, then queue PK
```

The initial exact lifecycle applicability read and schema-readiness check are
nonlocking preflight reads. Every locked identity is revalidated after the
work-order lock.

For queue work, construct a unique set from the exact persisted current and
successor lifecycle `station_code` values, normalize neither by inference nor
fallback, sort lexically, and acquire each station advisory lock exactly once.
If both operations use the same station, acquire one advisory lock. Queue rows
are not locked before this advisory set is complete.

Phase 5G-A may split the current Phase 5D queue primitive into shared
advisory-lock, row-lock, and rank-read primitives, but the release writer's
public/private behavior must remain unchanged.

## Lifecycle Completion

First bridge accepts only canonical current lifecycle status `queued` or
`active`, with `completed_at IS NULL`:

```text
status = completed
completed_at = execution_state.closed_at
updated_at = now()
```

The bridge does not modify `started_at`, good/scrap quantities, planned
quantity, UOM, payload, or metadata. A current `completed` row with the exact
persisted close timestamp participates in replay. Any other terminal state,
non-null conflicting timestamp, or static identity mismatch is a conflict.

`queued -> completed` is intentionally supported because the current runtime
sidecar can close without the MESQL lifecycle start helper. `active ->
completed` remains supported for lifecycle flows that did call the start
helper.

## Current Queue Terminalization

The current queue is selected only by exact lifecycle UUID, work order, and
persisted station. Station/order legacy adoption is prohibited. Zero, multiple,
or wrong-identity rows are conflicts.

First bridge accepts current queue status `queued`, `ready`, `active`, or
`pending_approval` and performs:

```text
status = completed
updated_at = now()
```

The row is retained for audit. Rank, lifecycle UUID, station, order, source,
payload, metadata, and creation timestamp are preserved. `completed` is outside
the active-rank partial unique predicate.

For the first released operation, immutable queue identity must match source
`work_order_release` and the Phase 5D initial payload/metadata contract. For a
later operation, it must match the bridge-created successor contract below.

## Successor Resolution

All lifecycle rows for the exact work order are already locked and validated.
The successor is:

```text
the unique lifecycle row with the smallest sequence_no
greater than the completed row's sequence_no
```

Selection includes terminal rows; filtering them would hide replay and
corruption. Identity is the persisted lifecycle UUID. Route identity comes
only from its immutable binding. Duplicate sequences, missing binding, digest
mismatch, or static lifecycle/binding mismatch are deterministic conflicts.

## Successor Activation

First activation requires successor lifecycle status `planned`, null
`completed_at`, and no successor queue row. It performs:

```text
successor lifecycle: planned -> queued, updated_at = now()
successor queue: one new exact UUID-scoped queued row
```

Queue source is the single stable value:

```text
runtime_completion_bridge
```

Exact immutable payload:

```json
{
  "order_id": "<work-order-id>",
  "work_order_operation_id": "<successor-uuid>",
  "operation_no": 20,
  "sequence_no": 20,
  "station_code": "<persisted-successor-station>",
  "status": "queued"
}
```

Exact immutable metadata:

```json
{
  "source": "runtime_completion_bridge",
  "release_id": "<release-id>",
  "predecessor_work_order_operation_id": "<completed-uuid>"
}
```

Route/config IDs are not copied into queue state. After current queue
terminalization, rank is read under the advisory/row locks with exactly:

```text
status IN ('queued', 'active', 'pending_approval')
```

`ready` is excluded. There is no automatic rank retry. Existing schema also
forbids two rows for the same station/order; a released route that revisits the
same station therefore produces a deterministic queue conflict unless a
separate future schema decision changes that constraint.

## Final Work-Order Completion

When no successor exists, every locked lifecycle row must be `completed` after
the current transition. Otherwise the bridge raises conflict and rolls the
current runtime/lifecycle/queue changes back.

First final completion performs:

```text
work order status = completed
work order completed_at = final execution_state.closed_at
work order updated_at = now()
```

Work-order `started_at`, payload, metadata, release, and bindings remain
unchanged. Exact replay requires an already completed work order with the same
authoritative completion timestamp. A different terminal status or timestamp
is a conflict.

## Replay and Idempotency

Exact replay returns `bridged=False` and performs zero writes.

For a nonfinal operation it requires:

- runtime remains closed;
- current lifecycle is completed at exact `closed_at`;
- current queue is completed with exact immutable identity;
- successor queue immutable identity is exact;
- successor lifecycle state may have progressed through `queued`, `active`, or
  `completed`; its queue may have progressed through `queued`, `ready`,
  `active`, `pending_approval`, or `completed`;
- original timestamps and ranks remain unchanged.

Thus an OP10 finish replay remains valid after OP20 or the work order has
completed. For a final operation, exact completed work-order identity and
timestamp are additionally required.

A successor that is already activated while the current lifecycle is not yet
completed is partial/out-of-order state, not replay. The bridge never repairs,
adopts, re-ranks, or rewinds state.

## Error Classification

Existing request/runtime missing-parent errors remain unchanged. Bridge errors
use `MesqlV2Error`:

| Detail | HTTP | Meaning |
|---|---:|---|
| `RUNTIME_COMPLETION_BRIDGE_SCHEMA_NOT_READY` | 503 | applicability marker exists but sidecar schema is absent |
| `RUNTIME_COMPLETION_BRIDGE_RUNTIME_NOT_CLOSED` | 409 | private bridge called without authoritative closed state |
| `RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT` | 409 | missing, duplicate, or inconsistent release |
| `RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT` | 409 | missing, extra, orphan, or inconsistent binding set |
| `RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT` | 409 | runtime/lifecycle/release route identity mismatch |
| `RUNTIME_COMPLETION_BRIDGE_SEQUENCE_CONFLICT` | 409 | invalid or duplicate lifecycle sequence |
| `RUNTIME_COMPLETION_BRIDGE_OPERATION_STATE_CONFLICT` | 409 | incompatible current lifecycle state/timestamp |
| `RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT` | 409 | current/successor queue partial state or known queue `23505` |
| `RUNTIME_COMPLETION_BRIDGE_SUCCESSOR_CONFLICT` | 409 | incompatible successor lifecycle/static state |
| `RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT` | 409 | invalid final/incomplete/terminal work-order state |

Known station queue constraint `23505` is mapped only after the failed
transaction has fully exited. There is no rank retry. Unknown `23505`, FK,
deadlock, serialization, connectivity, and other DB errors propagate unchanged.

## Event and Audit Boundary

The triggering `step_finish` event is sufficient runtime evidence. The bridge
creates no additional:

- operation or system-transition event;
- operation approval;
- production completion or work-order event;
- production-flow event;
- MESQL outbox row;
- inventory movement.

Lifecycle `completed_at`, execution `closed_at`, queue terminal state, and work-
order completion fields are the persisted bridge audit state.

## Deferred Reconciliation

A future explicit reconciliation tool may inspect or report historical partial
state after a crash or pre-bridge deployment. It must be separately authorized,
idempotent, and audit-visible. It is not a substitute for the synchronous
transaction and is not implemented in Phase 5G-A/B.

## Out of Scope

- Phase 5F Python, test, migration, DB, Docker, API, or feature-flag changes;
- Phase 5G implementation in this documentation turn;
- public manual-close or approval-close endpoints;
- legacy binding adoption, release/binding backfill, or partial-state repair;
- route/config/station/code/sequence inference;
- quantities, production completion, approval, flow, inventory, FERP, MESQL,
  Kiosk, IoT, or OEE integration;
- automatic retry for queue conflict, deadlock, or serialization failure.

# Phase 6B Entry Boundary

Status: `NOT_STARTED`

This document is an entry boundary, not a Phase 6B implementation plan or
authorization.

## Verified entry baseline

- Phase 6A final commit:
  `ae023142058a0a5fa79c6b99e257097abbde8dd1`
  (`fix: complete phase 6a station integration`).
- The implementation commit contained the exact reviewed 14-file scope and
  left a clean tree.
- Final focused MQTT regression: `65`, `OK`.
- Final combined Phase 6A regression: `933`, `OK`.
- Final independent review: `P1=0`, `P2=0`, `P3=0`.
- Verified state: [CURRENT_STATE](CURRENT_STATE.md).
- Acceptance evidence:
  [Phase 6A station integration](../runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md).

## Frozen invariants

Phase 6B must not weaken these verified Phase 6A behaviors:

- One authoritative dispatch boundary for Kiosk and canonical MQTT station
  commands.
- Persisted lifecycle UUID and route/step/action identity; no queue-head or
  source inference fallback.
- Config-driven manual/implicit transition authorization.
- Atomic lifecycle, runtime, event-ledger, and successor-queue transitions.
- Channel-aware external replay identity, zero-write exact replay, and
  deterministic cross-channel conflict.
- Deterministic, restart-stable source-less internal transition identity.
- Persistent canonical MQTT session/client identity and generation-aware stale
  callback rejection.
- Manual ACK only after terminal result; no ACK for timeout, shutdown,
  transient failure, or retired generation.
- Exactly-once startup failure ownership, lock-free blocking cleanup, and
  completion-aware stop.
- No worker/client/pending-MID/listener/temporary-resource leak.
- Generic Kiosk actions and retained V1/legacy compatibility unless explicitly
  retired.

## Deferred areas

Phase 6A did not deliver:

- Production source or physical-broker station execution rollout.
- MESQL or FERP production integration.
- Inventory movement/balance.
- A generalized virtual-plant or digital-twin runtime.
- Agent analytics or autonomous decision logic.
- Broad UI redesign, reconciliation, backfill, or unrelated refactor.

Deferred does not mean approved for Phase 6B.

## Questions that must be decided before implementation

The repository does not yet define one canonical Phase 6B implementation
scope. The earlier Phase 6A task identified source/physical validation as a
separately approved future checkpoint, but that statement is not an automatic
Phase 6B authorization.

```text
Phase 6B implementation scope requires explicit design decision.
```

Before implementation, decide:

- The exact business/technical outcome and ingress channels in scope.
- Whether work is offline, disposable-clone, source, or physical-field
  validation.
- Which existing feature flags and compatibility paths remain closed.
- Whether persistence changes are required or explicitly prohibited.
- The expected evidence-retention and cleanup policy.

## Entry gate

Phase 6B may start only when all are true:

- Task scope is explicitly approved.
- One canonical design/contract is selected.
- Database impact is classified.
- Migration need is classified.
- Physical-broker and source-database policies are determined.
- Focused regression tests are identified.
- Acceptance and stop criteria are written before implementation.

## Out of scope

Unless the Phase 6B task explicitly requests them, do not begin:

- MESQL development or push/pull.
- FERP production integration.
- Inventory movement or balance.
- Agent layer or autonomous analytics.
- Virtual-plant implementation.
- Broad UI redesign.
- Unrelated refactor, migration, source rollout, or physical field test.

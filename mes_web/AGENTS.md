# MES Web Production-Code Instructions

These rules add production-code constraints under `mes_web/` and inherit the
root [`AGENTS.md`](../AGENTS.md). These scoped rules take precedence for files
in this subtree when wording differs.

## Transaction authority

- Persisted database state outranks config caches and request metadata.
- Derive transition action from lifecycle phase/status and configured mode;
  pending `requested_action` does not select a transition.
- Reject partial writes and use authoritative post-lock rereads when required.

## Identity and replay

- The lifecycle UUID is the canonical operation-instance identity.
- `external_event_id` alone is not replay identity. Include ingress channel,
  publisher/source, lifecycle, station, step, and action identity as required
  by the contract.
- A cross-channel same-ID event is not an exact replay.
- Do not invent random or incomplete fallback identity.
- Internal transition identity must be deterministic and restart-stable.

## Locking and concurrency

- Preserve the canonical advisory-lock and row-lock order.
- Document the global order before adding a lock.
- Never perform blocking join, wait, or network cleanup while holding the
  lifecycle lock.
- Leave no TOCTOU window between validation and its protected side effect.
- Concurrent results must be one-apply/one-replay or a deterministic conflict.

## MQTT

- Manual ACK follows a terminal worker/transaction result only.
- Timeout, shutdown, transient failure, and retired generations produce no ACK.
- Keep client, persistent-session, and generation identity explicit and stable.
- Stale connect, SUBACK, disconnect, and message callbacks have no effect.
- Leave no worker, client, pending-MID, listener, or lifecycle marker leak.
- Do not change legacy QoS0 behavior without an explicit decision.

## Compatibility

- Do not change retained V1 or legacy paths outside explicit scope.
- Do not flip feature-flag defaults without an explicit decision.
- Do not start FERP, MESQL, inventory, backfill, or reconciliation work outside
  its approved phase.
- Do not add a public production flag or bypass solely for tests.

See the [current verified state](../docs/architecture/CURRENT_STATE.md) and
[Phase 6A acceptance evidence](../docs/runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md).

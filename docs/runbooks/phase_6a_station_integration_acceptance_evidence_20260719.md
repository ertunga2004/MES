# Phase 6A Station Integration Acceptance Evidence

## Purpose

Record the final, repository-level acceptance of the Phase 6A station execution
vertical slice without erasing the F1-F4 failed review history. This document
summarizes verified outcomes; it is not a database apply or field-test
authorization.

## Baseline

- Implementation baseline before Phase 6A:
  `adb677490e497b7ce3ef90cc0d6b5ce093d6750d`
  (`docs: record controlled route release api source smoke`).
- Final implementation commit:
  `ae023142058a0a5fa79c6b99e257097abbde8dd1`
  (`fix: complete phase 6a station integration`).
- Final implementation scope: exact 14 reviewed files across config, runtime,
  MQTT, DB orchestration, Kiosk UI, compose examples, and focused tests.

## Implemented scope

- One authoritative station-execution dispatch boundary shared by Kiosk and
  canonical MQTT ingress.
- Persisted station/lifecycle/route-operation/current-step validation.
- Config-driven manual and implicit transition selection.
- Deterministic internal transition identity and channel-aware external event
  replay/conflict handling.
- Atomic step, execution-state, event-ledger, lifecycle completion, and
  successor-queue behavior where the command contract requires them.
- Generic Kiosk current-action support.
- Canonical MQTT mapping, bounded admission, worker execution, persistent
  session, generation retirement, and terminal-result manual ACK.

## Finding progression

The historical review iterations remain part of the acceptance record:

```text
F1 = FAIL
F2 = FAIL
F3 = FAIL
F4 = FAIL
F5 = PASS
```

Each retry preserved the previous implementation and narrowed the remaining
finding set. None of the failed checkpoints is reclassified as a PASS.

## F1 result

The initial vertical slice was not accepted. Independent review left
`P1=2` and `P2=7`, including worker shutdown, MQTT delivery ownership,
config-driven transition, identity/locking, and response/replay concerns. F2
was opened as a bounded corrective task.

## F2 result

F2 added fail-closed worker-stop semantics, bounded queue admission, terminal
manual ACK behavior, config-derived source/action handling, atomic implicit
transitions, and focused regression coverage. It remained a historical FAIL:
the implementation required further lifecycle/concurrency review before it
could be accepted or committed.

## F3 result

The fresh disposable PostgreSQL clone exercised the full 19-scenario Phase 6A
matrix successfully, including transaction semantics, cross-channel identity,
source-less internal atomic transition, and cleanup. Independent transport
review nevertheless ended at `P1=0`, `P2=1`, `P3=0`: connect admission and
subscribe could race with stop, and a late rejected SUBACK could initiate
invalid startup rollback. F3 therefore remained FAIL.

## F4 result

F4 made connect validation, generation selection, broker subscription, and MID
registration atomic with stop; stale/retired callbacks became no-ops and valid
current-generation rejection remained fail-closed. Focused MQTT regression was
`57`, `OK`, and combined regression was `925`, `OK`. Final review found one new
actionable `P2`: current-generation startup failure still held the lifecycle
lock while performing rollback and worker join. F4 therefore remained FAIL and
did not commit.

## F5 final result

F5 implemented `claim -> retire -> release -> cleanup -> finalize` ownership.
The failure owner snapshots the generation/client/worker state under a short
lifecycle critical section, retires admission, releases the lock, performs
blocking cleanup, and finalizes only its own snapshot.

The first F5 review found `P1=0`, `P2=1`, `P3=0`: concurrent `stop()` could
observe an owner and return success before cleanup completed. The one permitted
narrow correction added a dedicated completion event. Stop now waits outside
the lifecycle lock, verifies worker/client/owner cleanup, and returns failure on
timeout or incomplete cleanup. The second and final review returned:

```text
P1 = 0
P2 = 0
P3 = 0
```

## Final invariants

- Persisted state is authoritative; queue/lifecycle/current-step disagreement
  fails closed.
- Lifecycle UUID is the canonical operation instance identity.
- External replay identity includes channel and configured source context.
- Same-channel exact replay produces no second transition.
- Cross-channel same-ID input produces deterministic conflict and no partial
  write.
- Internal implicit transition identity is deterministic and restart-stable.
- State/event/lifecycle/queue changes owned by one command remain atomic.
- MQTT manual ACK occurs only after a terminal result.
- Timeout, shutdown, transient failure, and retired generation produce no ACK.
- Startup failure cleanup has exactly one owner and no blocking cleanup under
  the lifecycle lock.
- Concurrent stop is completion-aware.
- No worker, client, pending MID, generation, failure marker, listener, or test
  synchronization leak remains.

## Final test matrix

| Check | Result |
| --- | --- |
| Focused MQTT adapter suite | `65`, `OK` |
| Combined Phase 6A suite | `933`, `OK` |
| MQTT/runtime Python compile | `PASS` |
| Git whitespace check | `PASS` |
| Independent final review | `P1=0`, `P2=0`, `P3=0` |

The combined suite included station execution commands, MQTT adapter, Kiosk,
controlled route-release API, station-execution config API, station-location
API, and MESQL V2 helper regressions.

## PostgreSQL clone evidence

The F3 disposable clone completed the 19-scenario vertical matrix and verified
transaction, replay/conflict, lifecycle completion, successor queue, and
cross-channel identity behavior. Production `mes` was not targeted. Because F4
and F5 changed only MQTT transport lifecycle code and its tests, the approved
gate retained the F3 clone evidence instead of repeating DB E2E. No physical
broker was used in F4 or F5.

## Cleanup evidence

- Test workers, clients, pending subscriptions, listeners, and synchronization
  objects were released.
- No Phase 6A task process or temporary artefact remained.
- The existing PostgreSQL container and retained backups were unchanged.
- F4/F5 performed no database, migration, compose-lifecycle, or source write.

## Commit evidence

```text
Commit = ae023142058a0a5fa79c6b99e257097abbde8dd1
Subject = fix: complete phase 6a station integration
Files = 14
Tree = clean
Push = not performed
```

## Deferred scope

- MESQL and FERP production integration.
- Inventory movement and balance.
- Production source or physical-broker station-execution rollout.
- Generalized virtual-plant runtime and digital-twin adapters.
- Agent analytics or autonomous decision layer.
- Broad UI redesign or unrelated refactor.
- Phase 6B implementation.

## Acceptance decision

```text
Decision = PASS / VERIFIED_PHASE_6A_STATION_INTEGRATION
P1 = 0
P2 = 0
P3 = 0
Combined Phase 6A = 933 OK
Commit = ae023142058a0a5fa79c6b99e257097abbde8dd1
Tree = clean
Push = not performed
Phase 6B = not started
```

Canonical state:
[CURRENT_STATE](../architecture/CURRENT_STATE.md). Next-phase boundary:
[PHASE_6B_ENTRY](../architecture/PHASE_6B_ENTRY.md).

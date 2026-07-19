# MES Documentation

The authoritative documentation registry is [docs/INDEX.md](INDEX.md).
Start there instead of using directory age, filename, or incoming-link count
as an authority signal.

## Current entry points

- [Project README](../README.md) — concise repository purpose and startup.
- [Current Verified State](architecture/CURRENT_STATE.md) — current verified
  capabilities, database/configuration baseline, flags, compatibility, and
  deferred scope.
- [Phase 6B Entry](architecture/PHASE_6B_ENTRY.md) — next-phase boundary;
  status is `NOT_STARTED`.
- [Phase 6A acceptance](runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md)
  — final station-integration evidence.
- [Repository governance](../AGENTS.md) and
  [documentation governance](AGENTS.md).

## Main documentation areas

- `architecture/` — current state, phase boundaries, decisions, designs, and
  contracts.
- `runbooks/` — repeatable procedures plus immutable smoke/apply/failure/
  recovery evidence.
- `runtime/` — retained runtime, feature-flag, MQTT, hardware, and field-test
  references.
- `mesql/` — frozen MESQL planning and reference material unless explicitly
  reactivated.
- `erp/` and `bombop/` — deferred integration contracts and source-readiness
  material.
- `agent_memory/` — historical checkpoints pending manual consolidation;
  noncanonical for current Codex work.
- `archive/` — superseded context that must not override current state or
  evidence.
- `FERP_XLS/` and `db_pre_plan/` — retained source material, not active
  implementation instructions.

Runbooks do not grant permission to apply migrations, write source data,
operate Docker, use a physical broker, or perform destructive recovery. Those
actions require an explicit task and approval.

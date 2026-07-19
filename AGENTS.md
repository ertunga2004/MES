# MES Repository Instructions

## Project mission

Build a configurable production-execution core that can be adapted to
different manufacturing systems. The current conveyor is the reference plant,
not the product boundary. Preserve an industrial-engineering perspective while
supporting controlled integration with physical and virtual resources,
FERP/MESQL, and other manufacturing applications. Treat future digital-plant
and agent capabilities as roadmap items until they are implemented and
verified.

## MES and MESQL

- `MES` is the actively developed local production-execution system in this
  repository.
- `MESQL` is a separate central integration/data-core effort.
- Keep MESQL frozen/deferred unless the current task explicitly activates it.
- Do not mix repository ownership, data authority, migrations, or rollout
  decisions between MES and MESQL.
- `.agents/AGENTS.md` is an Antigravity-only instruction file and is not the
  Codex governance source for this repository.

## Canonical source order

When sources conflict, use this order:

1. The user's current task instructions.
2. A deeper scoped `AGENTS.md` for the files being changed.
3. This root `AGENTS.md`.
4. Verified facts in `docs/architecture/CURRENT_STATE.md`.
5. The relevant phase design or plan.
6. Acceptance or smoke evidence.
7. The general README.
8. Historical or superseded documents.

Historical FAIL evidence remains immutable history; it does not override a
later verified canonical state that explicitly supersedes its failed result.
The order above governs instructions, approved scope, and intended contracts.
For claims about what actually ran or passed, verified acceptance/smoke
evidence is the proof source; a design or plan cannot substitute for execution
evidence. If intended design and observed evidence differ, report the conflict
instead of treating either as proof of the other.

## Required workflow

1. Verify HEAD, branch, working-tree status, and staged state.
2. Read the relevant canonical documents.
3. Extract the allowed scope and phase boundary.
4. Inspect existing behavior and tests.
5. Make the smallest necessary change.
6. Run focused tests.
7. Run the required regression and static checks.
8. Inspect the diff and unexpected side effects.
9. Follow the task's commit and push rules.
10. Separate completed work from explicitly unperformed work in the final
    report.

## Safety boundaries

- Do not write to the production `mes` database without explicit permission.
- Prefer disposable clones for database validation.
- Do not apply migrations without an explicit apply task.
- Do not perform MESQL push/pull unless explicitly requested.
- Do not use a physical MQTT broker without an explicit field-test task; use a
  controlled harness otherwise.
- Do not delete or modify backups.
- Do not commit secrets, `.env`, dumps, runtime output, or machine-local paths.
- Do not use destructive Git commands or reset an existing dirty tree without
  explicit permission.
- Push only when the user explicitly requests it.
- Do not begin implementation beyond the approved phase boundary.

## Engineering invariants

- Fail closed.
- Use deterministic identity.
- Keep multi-row state changes atomic.
- Preserve idempotent replay and specified zero-write replay/conflict paths.
- Keep audit semantics append-only where defined.
- Prefer explicit configuration over inference.
- Preserve backward compatibility unless it is explicitly retired.
- Route physical and virtual events through explicit adapters and contracts.

More specific production-code rules are in
[`mes_web/AGENTS.md`](mes_web/AGENTS.md). Current details and evidence are in
the canonical documents below.

## Canonical documentation

- [Project README](README.md)
- [Current verified state](docs/architecture/CURRENT_STATE.md)
- [Phase 6B entry boundary](docs/architecture/PHASE_6B_ENTRY.md)
- [Phase 6A acceptance evidence](docs/runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md)

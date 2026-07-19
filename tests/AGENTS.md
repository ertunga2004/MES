# Test Instructions

These rules add constraints under `tests/` and inherit the root
[`AGENTS.md`](../AGENTS.md). These scoped rules take precedence for files in
this subtree when wording differs.

- Use deterministic events, barriers, or controlled fakes for race and
  concurrency tests; do not use timing sleeps as probabilistic proof.
- Prove exact replay with zero row, event, sequence, and state delta where the
  contract requires zero writes.
- Prove conflicts leave no partial write.
- Test rollback and a clean retry after failure injection.
- Keep the source database read-only when it is in scope; run PostgreSQL smoke
  against a disposable clone unless a source task is explicitly approved.
- Verify clone, session, worker, client, listener, synchronization object, and
  temporary-file cleanup.
- Use a physical broker only in an explicitly approved field-test task.
- Test count alone is not acceptance evidence; add a regression test that
  directly reproduces each actionable finding.
- Do not weaken an existing assertion merely to hide new behavior.
- Prefer contract and persisted-state assertions over implementation details.

Canonical offline commands verified in this repository include:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_mes_web_*.py'
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_station_execution_commands
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_station_execution_mqtt_adapter
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_mesql_v2
```

Select the focused command for the changed contract, then run the regression
set required by the task. Do not encode volatile test counts here. See the
[current verified state](../docs/architecture/CURRENT_STATE.md) and
[Phase 6A evidence](../docs/runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md).

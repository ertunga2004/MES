# Documentation Instructions

These rules add constraints under `docs/` and inherit the root
[`AGENTS.md`](../AGENTS.md). These scoped rules take precedence for files in
this subtree when wording differs.

- `architecture/CURRENT_STATE.md` contains verified facts only.
- A design plan is not implementation evidence; implementation tests are not a
  substitute for acceptance evidence.
- Never delete or rewrite historical FAIL evidence. A later PASS may supersede
  its failed conclusion only through explicit linked evidence.
- Verify dates, commit SHAs, test counts, and scope before recording them.
- Do not describe deferred features as implemented.
- State `NOT_STARTED` when a new phase has not begun.
- Update the canonical document instead of creating a competing copy.
- Do not introduce machine-specific absolute paths into canonical documents.
- Preserve existing language and technical terminology within each document.
- Do not rewrite historical evidence solely to modernize its wording or paths.
- Follow the [archive policy](archive/README.md) before moving superseded
  context. Historical execution evidence normally remains under `runbooks/`.

Canonical references:

- [Current verified state](architecture/CURRENT_STATE.md)
- [Phase 6B entry boundary](architecture/PHASE_6B_ENTRY.md)
- [Phase 6A acceptance evidence](runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md)

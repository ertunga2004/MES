# Documentation Archive

Documents under `docs/archive/` are retained historical or superseded context.
They are noncanonical.

## Rules

- Archived documents may describe superseded plans, assumptions, or system
  boundaries.
- They do not override
  [CURRENT_STATE](../architecture/CURRENT_STATE.md), an active design, or
  acceptance evidence.
- Historical execution, failure, recovery, migration, and smoke evidence
  normally remains under [`docs/runbooks/`](../runbooks/) and is not moved here.
- New work must not be based on an archived document without revalidating it
  against current repository behavior and canonical documents.
- Archival preserves history; it is not deletion and does not imply that every
  statement remains true.

## Archived documents

| Document | Reason retained |
| --- | --- |
| [Legacy roadmap](legacy_plans/roadmap.md) | Early project roadmap retained as historical planning context |
| [Superseded AI guide](legacy_plans/ai_guide.md) | Replaced by root/scoped `AGENTS.md` governance and the documentation authority registry |
| [Pre-Phase-6 architecture overview](legacy_plans/architecture_overview.md) | Workbook-first/reference-plant overview superseded by current verified state |
| [Pre-Phase-6 roadmap](legacy_plans/pre_phase6_roadmap.md) | Earlier transition roadmap superseded by completed Canonical V2 and Phase 6A evidence |

Current entry points:

- [Documentation Index](../INDEX.md)
- [Current Verified State](../architecture/CURRENT_STATE.md)
- [Phase 6B Entry](../architecture/PHASE_6B_ENTRY.md)
- [Repository governance](../../AGENTS.md)

# Antigravity-Only MES Workspace Rules

This file is only for Antigravity agents working inside the MES workspace.

Do not treat this file as a shared instruction file for Codex.

Codex must not be guided through this file. Codex will receive separate task packets, prompts, or explicitly prepared handoff documents when needed.

---

## 1. Primary Role

Your default role in this project is not primary implementation.

Your default role is:

- system analysis,
- documentation,
- project memory maintenance,
- Codex task-packet preparation,
- Codex diff review,
- regression-risk detection,
- verification planning,
- separating verified facts from assumptions.

Do not modify production code unless the user explicitly asks you to implement a specific change.

When in doubt, operate in read-only analysis mode.

---

## 2. MES / MESQL Boundary

MES and MESQL are different structures.

MES is the active development target.

MES is the production execution system designed to run the physical workshop/conveyor environment. Current active focus:

- MES runtime,
- MES local database / local state,
- station logic,
- work order flow,
- queue/state management,
- dashboard,
- operator kiosk,
- technician screen,
- MQTT/hardware flow,
- workbook persistence,
- OEE,
- Docker/PostgreSQL transition preparation,
- future FERP JSON contract preparation.

MESQL is a separate shared database/integration layer intended to let BOM/BOP, Integrated Work Study, and MES communicate with FERP.

MESQL is currently frozen.

Unless explicitly instructed:

- do not develop MESQL,
- do not redesign MESQL schema,
- do not treat MESQL as the active source-of-truth,
- do not turn MES tasks into MESQL refactor tasks.

---

## 3. Required Reading Order

Before any MES-related analysis, read these files first:

1. `docs/agent_memory/README.md`
2. `docs/agent_memory/00_masterplan.md`
3. `docs/agent_memory/01_current_progress.md`
4. `docs/agent_memory/02_system_architecture.md`
5. `docs/agent_memory/04_postgresql_transition_plan.md`
6. `docs/agent_memory/08_guardrails_and_do_not_touch.md`
7. `docs/agent_memory/09_antigravity_handoff.md`
8. `README.md`
9. `docs/README.md`
10. `TODO.md`

If a file is missing, stale, or contradictory, report it.

Do not invent missing content.

---

## 4. Main Project Memory

The main project memory is:

`docs/agent_memory/`

Do not create a parallel documentation hierarchy unless explicitly instructed.

Prefer updating or extending `docs/agent_memory/`.

Recommended future documentation files, only when explicitly requested:

- `docs/agent_memory/11_station_logic_update.md`
- `docs/agent_memory/12_antigravity_operating_protocol.md`
- `docs/agent_memory/13_task_packet_template.md`

Do not duplicate existing documents.

Do not split project memory across multiple competing folders.

---

## 5. Codex Separation Rule

Codex and Antigravity must not use the same instruction file.

This file is Antigravity-only.

Do not ask Codex to read `.agents/AGENTS.md`.

Do not assume Codex has read `.agents/AGENTS.md`.

If a task must be handed to Codex, prepare a separate task packet with:

- goal,
- background,
- scope,
- allowed files,
- forbidden files,
- implementation outline,
- validation commands,
- SQL checks if applicable,
- stop conditions,
- rollback notes,
- done criteria.

Codex should receive only the task packet or explicit user prompt prepared for that task.

Additional Codex handoff restrictions:

- Do not paste the contents of `.agents/AGENTS.md` into Codex prompts.
- Do not reference `.agents/AGENTS.md` as a required Codex context file.
- Do not include Antigravity-only operating rules inside Codex task packets.
- Codex task packets must contain only task-specific context, scope, constraints, validation steps, and done criteria.
- If Codex needs a guardrail, write it explicitly inside that task packet instead of pointing Codex to this file.
---

## 6. Concurrency Rule

This workspace may also be used by Codex.

If it is unclear whether Codex is active, assume Codex may be active and operate read-only until the user confirms otherwise.

Antigravity and Codex must not write to the same workspace at the same time.

If Codex is active:

- operate read-only,
- do not modify files,
- do not create files,
- do not write migrations,
- do not edit configuration,
- do not run destructive commands.

Before any write operation, check or request:

```powershell
git status -sb
git diff --stat
git diff --name-only
```

Before editing, state:

* which files you intend to modify,
* why each file needs to be modified,
* whether any of those files are already changed by the user or Codex.

Do not touch files currently modified by Codex or the user unless explicitly instructed.

---

## 7. Docker / PostgreSQL / Runtime Guardrails

Do not:

* use `git add .`,
* use `git reset --hard`,
* use `git push --force`,
* use `docker compose down -v`,
* delete database volumes,
* commit `.env`,
* commit `data`,
* commit `logs`,
* commit `exports`,
* commit `app_source`,
* commit SQL backups,
* commit SQL dumps,
* commit tar/archive/runtime output files,
* modify Docker Compose unless explicitly requested,
* attach migration execution to automatic startup,
* make PostgreSQL mandatory for MES runtime,
* set `MES_WEB_DB_ENABLED` default to `true`,
* set `MES_WEB_DB_MIRROR_WORK_ORDERS` default to `true`,
* perform source-of-truth transition without a written plan,
* add runtime DB read without a written plan,
* break Excel/JSON/FERP/MQTT runtime flows,
* modify product setup documents unless explicitly requested.

PostgreSQL transition exists, but runtime source-of-truth migration is not assumed complete.

Treat PostgreSQL as transitional or mirror unless the current task explicitly says otherwise.

Database failure must not crash MES runtime.

Before adding writes to a new table, prepare:

1. dry-run plan,
2. apply plan,
3. verify plan,
4. rollback risk analysis.

---

## 8. Work Modes

### 8.1 Read-Only Analysis Mode

Use this mode when the user says:

* analyze,
* inspect,
* review,
* understand,
* report,
* map,
* document before changing.

Rules:

* do not modify code,
* do not create files,
* do not edit documentation,
* only inspect and report,
* list inspected files,
* separate verified facts from assumptions,
* list risks,
* list open questions,
* recommend next steps.

### 8.2 Documentation-Only Mode

Use this mode only when the user explicitly asks for documentation changes.

Rules:

* edit only allowed `.md` files,
* do not modify code,
* do not write migrations,
* do not modify Docker/config/runtime files,
* include “Verified from” and “Open Questions” sections,
* avoid duplicating existing documentation.

### 8.3 Codex Task-Packet Mode

Use this mode when preparing work for Codex.

Every Codex task packet must include:

* Goal
* Background
* Scope
* Allowed files
* Forbidden files
* Implementation outline
* Validation commands
* SQL checks if applicable
* Stop conditions
* Rollback notes
* Done when

Task packets must be small, specific, and reviewable.

Do not prepare broad “fix the whole system” tasks.

### 8.4 Diff Review Mode

Use this mode after Codex or the user changes files.

Rules:

* list changed files,
* identify regression risks,
* identify missing tests,
* check runtime/workbook/MQTT/OEE/DB impact,
* avoid broad refactor suggestions,
* prefer narrow corrective recommendations.

---

## 9. Station Logic Focus

For station-logic tasks, inspect especially:

* work order lifecycle,
* station assignment,
* queue/ranking,
* operator kiosk station behavior,
* technician station behavior,
* dashboard station state,
* MQTT station/hardware events,
* runtime state,
* workbook persistence,
* PostgreSQL mirror impact,
* OEE impact.

Risk classes:

* station state mismatch,
* work order status mismatch,
* queue duplicate,
* orphan queue item,
* workbook/runtime divergence,
* DB mirror divergence,
* WebSocket snapshot inconsistency,
* MQTT/hardware event mismatch,
* OEE calculation impact.

---

## 10. Skill Usage

Use only relevant skills.

Allowed / relevant skills:

* docker-expert
* postgres-best-practices
* sql-pro
* python-pro
* python-patterns
* api-design-principles
* api-endpoint-builder
* debugger
* performance-optimizer
* clean-code
* code-simplifier
* react-best-practices
* react-patterns
* antigravity-agent-manager
* antigravity-skill-orchestrator
* antigravity-workflows
* workflow-skill-creator

Do not use these skill families for this MES project:

* biology,
* chemistry,
* clinical,
* protein,
* genomics,
* drug discovery,
* literature-search,
* science database skills.

Science and bioinformatics skills are noise for this repository.

---

## 11. Output Format

For analysis reports, use this structure:

```md
# Report Title

## 1. Files inspected

## 2. Verified facts

## 3. Assumptions

## 4. Current behavior

## 5. Affected modules

## 6. Risks

## 7. Open questions

## 8. Recommended next steps

## 9. Codex task packet if applicable
```

Do not present assumptions as verified facts.

Do not invent table names, endpoints, file names, hardware behavior, or business rules.

---

## 12. Project Priority Order

Priority order:

1. Preserve working MES runtime.
2. Preserve existing Excel/JSON/MQTT/FERP flow.
3. Keep Docker/PostgreSQL transition controlled and feature-flagged.
4. Keep MESQL frozen unless explicitly reactivated.
5. Document station logic and work order flow.
6. Prepare small Codex task packets.
7. Avoid broad architecture changes without written plan and user approval.

---

## 13. Default Response to Broad Tasks

For broad or ambiguous tasks:

1. Classify the task scope:

   * MES
   * MESQL
   * Docker
   * PostgreSQL
   * FERP
   * UI
   * hardware
   * OEE
   * workbook
2. Inspect repository files before making claims.
3. Produce a plan before implementation.
4. Break the work into small task packets.
5. Do not implement unless the user explicitly asks for implementation.

---

## 14. Final Rule

First read.

Then analyze.

Then document.

Then prepare task packets.

Only implement when explicitly instructed.

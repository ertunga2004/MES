# Canonical V2 Source Rollout Design

## Status

- Last updated: `2026-07-15`.
- Phase 5H-B: `READY_FOR_CONTROLLED_SOURCE_SCHEMA_SEED_APPLY`.
- Phase 5H-C:
  `PLANNED_REQUIRES_PHASE_5H_B_PASS_AND_SEPARATE_APPROVAL`.
- This document is a design contract. No source database apply or functional
  smoke was performed while it was prepared.

## Scope

This design defines the controlled rollout of the already reviewed Canonical
V2 route-release stack to the local source database `mes`:

1. `009_work_order_operation_route_binding.sql`;
2. `010_work_order_route_release.sql`;
3. `006_station_execution_seed_canonical_v2.sql`.

Phase 5H-B owns only schema and configuration readiness. Phase 5H-C is a
separately approved source-local functional validation. The two phases are not
one transaction, one approval, or one evidence run.

No public API, feature flag, automatic route selection, FERP/MESQL entry point,
Kiosk action, analytics filter, inventory behavior, or Docker lifecycle change
is part of Phase 5H-A or Phase 5H-B.

## Current Source State

The accepted source state is evidence-based and must be revalidated in a live,
read-only Phase 5H-B preflight:

- container/database/user: `mes_postgres / mes / mes`;
- host port: `5433`;
- migrations `004` and `005` are applied;
- binding migration `009` is absent;
- release migration `010` is absent;
- Canonical V2 route/config is absent;
- retained V1 route/operations/steps are `1 / 2 / 5`;
- operation events/approvals/production-flow events are `4 / 0 / 0`;
- the established 15-table baseline and the 38-table source inventory were
  unchanged in the last verified completion-bridge smoke.

This is not permission to infer the live source state. Any Phase 5H-B preflight
difference blocks apply and requires a separate review.

## Verified Implementation Baseline

- Completion-bridge documentation closure:
  `7e94382a90c6bdfba81928588785a08b37e18fa3`
  (`docs: record verified runtime lifecycle completion bridge`).
- Runtime bridge hotfix:
  `2c62ad9ea3473886a51a0d1fa61bb25c10c0667f`.
- Retry acceptance: targeted `600`, combined `636`, PostgreSQL end-to-end
  matrix PASS, source `38/38` and established `15/15` integrity PASS.
- Historical failed evidence remains unchanged and is superseded only as the
  acceptance result by the successful retry evidence.
- Migration `009` commit/SHA-256:
  `5c57f707c8fdb1a467fe46ed4cd17a990f76b3ec` /
  `b5da1799a52147433e1dea44bd989394d720416d352cc7906f8a1729be1a0162`.
- Migration `010` commit/SHA-256:
  `3e4771154d19d43da6aee42a8939632e19e1c324` /
  `5b7c6cf7261095a6b00c7ef9170ed7f262f648053bdc0b1e3ea4a4b4c7b551f6`.
- Seed `006` latest commit/SHA-256:
  `4750f92c8363d28bc515e44660fe54506d2dc399` /
  `9b4174bd5756b92dd5d9111bc7e5249020471865f6546b2c47d77f94b79434c8`.

Phase 5H-B must recompute and compare these hashes before copying or executing
SQL. A mismatch blocks the run; it is never accepted as an implicit upgrade.

## Rollout Phases

### Phase 5H-B — Schema and Seed Apply

Only the three reviewed SQL artifacts are applied. Work-order creation,
release, runtime initialization, step start/finish, completion bridge, API,
Kiosk, FERP/MESQL, inventory, and analytics operations are forbidden.

### Phase 5H-C — Source-Local Functional Validation

Only after a documented Phase 5H-B PASS and a new explicit approval, create one
clearly identified nonproduction source work order and exercise:

```text
route release
-> OP10 initialization and execution
-> OP20 activation
-> OP20 initialization and execution
-> work-order completion
-> exact release and finish replays
```

Phase 5H-C produces separate evidence and never changes the Phase 5H-B result.

## Dependency Order

The only permitted order is:

```text
009 binding schema
-> 010 release schema and parent route identity constraint
-> 006 Canonical V2 route/config seed
```

Migration `009` establishes the immutable lifecycle-to-route-operation sidecar.
Migration `010` establishes the release snapshot and exact same-row route
identity constraint. The release writer requires both sidecars. Seed `006`
then creates the exact route/config parents used by a future release. No
production or validation release may run before all three checkpoints pass.

## Backup Boundary

Phase 5H-B requires one retained plain logical dump:

```text
<portable-runtime-root>\data\db_backups\
mes_before_canonical_v2_source_rollout_<timestamp>.sql
```

The run must record exact container/database/user identity, PostgreSQL and
`pg_dump` versions and command exit status. `pg_dump -Fp` writes through its
`-f` option to one exact container-side temporary file. The run verifies its
existence, positive byte size, PostgreSQL dump header, and SHA-256 before
copying it with `docker cp` to the exact host path. Host existence, positive
size, header and SHA-256 are then verified, and host/container hashes must be
equal. PowerShell native stdout redirection is forbidden. The existing backup
launcher is not used because it generates a different filename.

The container temporary dump may be removed only after copy, host validation,
and SHA-256 equality all pass. Any creation, validation, copy, header or hash
failure blocks Phase 5H-B before migration `009`; no apply begins.

The verified host backup is retained. Restore is not automatic and is not an
executable step in the apply runbook. It requires a separate destructive
recovery decision after the exact source state is inspected.

## Preflight Boundary

Preflight runs in one `REPEATABLE READ, READ ONLY` source transaction and
records:

- `current_database() = mes`, `current_user = mes`, server version and source
  identity;
- the exact `mes` base-table set from `information_schema.tables` with
  `table_type = 'BASE TABLE'`;
- the established 15-table counts and deterministic ordered JSONB digests;
- the full baseline table inventory/fingerprint where applicable;
- retained V1 counts, identities and digests;
- event/approval/production-flow counts;
- location and station-location-binding state;
- target sidecar relation presence, row counts when present, and catalog shape;
- `uq_mes_process_routes_identity_snapshot` presence and definition;
- every Canonical V2 route, operation and step identifier/collision.

Expected first-rollout state is: both sidecar tables absent, the parent identity
constraint absent, all Canonical V2 IDs absent, and retained V1 unchanged.
Unexpected exact-looking objects are still an out-of-band partial state and
block the first rollout. Wrong shape, only one sidecar, any target row, a
partial V2 seed, a duplicate route/version, or a name-occupied parent constraint
also blocks. Phase 5H-B does not adopt or repair any partial state.

## Schema Apply Strategy

Each repository SQL file already contains its own `BEGIN` and `COMMIT`. It must
not be wrapped in an outer transaction or concatenated with another artifact.
After its reviewed host file is copied to an exact timestamped container temp
path, each artifact is executed by a separate command of this form:

```text
psql -X -v ON_ERROR_STOP=1 -f "<container-sql-file>"
```

The sequence is:

1. execute `009` once; verify exact `9 / 9 / 4` columns/constraints/indexes,
   zero rows, and unchanged baseline data;
2. execute exact `009` once more in a new `psql -f` call; require zero catalog
   and data delta;
3. execute `010` once; verify exact `14 / 15 / 5`, zero rows, exact parent
   unique and child composite FK, unchanged binding table and baseline data;
4. execute exact `010` once more in a new `psql -f` call; require zero catalog
   and data delta.

The base-table invariant is set-based, not count-based:

```text
after 009 set = baseline set
                + mes.work_order_operation_route_bindings

after 010 set = baseline set
                + mes.work_order_operation_route_bindings
                + mes.work_order_route_releases
```

An expected final count of `40` is only a secondary diagnostic when the
preflight base-table count was `38`. The authoritative comparison uses
`information_schema.tables`, `table_schema = 'mes'`, and
`table_type = 'BASE TABLE'`. Sequences, views, indexes, and other relation types
are excluded.

## Seed Apply Strategy

After both schema checkpoints pass, execute seed `006` through its own separate
`psql -X -v ON_ERROR_STOP=1 -f` call. Verify:

- route/operations/steps `1 / 2 / 4`;
- exact V2 route/version and OP10/OP20 identifiers;
- OP10/OP20 step counts `3 / 1`;
- both policies `auto_close_on_required_steps`;
- exact process-end observation, no embedded approval or QC operation;
- configured/resolved location roles `5 / 5`;
- retained V1 count and digest equality;
- zero release, binding, lifecycle, queue, runtime, event, or inventory rows
  created by the seed.

Execute exact seed `006` once more through a new `psql -f` call and require no
catalog or data change. Only the exact additive V2 rows in `process_routes`,
`route_operations`, and `operation_steps` may differ from the pre-rollout data.
All other baseline tables remain identical.

## Failure and Recovery

Any command, assertion, catalog, data, hash, identity, health, or comparison
failure stops the run. The failing SQL file's own transaction rolls back and
no later artifact or functional smoke is started.

A previously committed additive checkpoint is not dropped automatically. The
operator records the exact surviving schema/config state and obtains separate
approval before an idempotent reapply. No manual row repair, backfill, rename,
deactivation, or compensating delete is permitted. Backup restore is a separate
destructive recovery task, never an automatic reaction.

## Post-Apply Verification

Phase 5H-B PASS requires:

- final base-table set equals the baseline set plus exactly the two sidecars;
- `40` base tables only as the expected helper count for the accepted `38`
  baseline;
- binding `9 / 9 / 4`, zero rows;
- release `14 / 15 / 5`, zero rows;
- exact parent route identity constraint;
- V2 `1 / 2 / 4`, OP10/OP20 `3 / 1`, roles `5 / 5`;
- V1 `1 / 2 / 5` with unchanged rows/digests;
- existing work orders, lifecycle operations, queues, runtime state, events,
  locations and station bindings unchanged;
- audit baseline remains `4 / 0 / 0`;
- no API/helper/runtime/bridge call;
- container healthy and `GET /health` returns `200 / ok`.

## Source-Local Functional Validation

Phase 5H-C uses one persisted, clearly prefixed nonproduction work order. A
rollback-only outer transaction is not used because the public helpers own and
commit their own transactions. A dedicated validation database does not prove
the chain on actual source `mes` and therefore does not satisfy Phase 5H-C.

The functional plan fixes exact identity, helper order, immutable/readback
checks, replay behavior, audit boundaries, failure handling, and evidence. It
does not authorize execution.

## Test-Data Retention Decision

The selected policy is one persisted nonproduction audit fixture:

```text
order_id   = PHASE5HC-SOURCE-SMOKE-<yyyyMMdd-HHmmss>
release_id = PHASE5HC-SOURCE-RELEASE-<yyyyMMdd-HHmmss>
actor      = PHASE5HC_SOURCE_SMOKE
```

Fixture payload/release metadata must include:

```json
{
  "disposable_test": true,
  "exclude_from_analytics": true,
  "production_release": false,
  "retention_reason": "source_rollout_validation"
}
```

The successful fixture is retained and never silently deleted or represented
as production. A failed partial fixture is also retained pending a separate
resume/recovery decision.

Future OEE, KPI, FERP, export, reporting and analytics consumers must exclude
rows when either the order ID has prefix `PHASE5HC-SOURCE-SMOKE-` or the
nonproduction metadata marks `exclude_from_analytics=true`. Implementing those
filters is a mandatory deferred requirement, not Phase 5H-A/B/C implementation.

## API and Integration Boundary

Schema/seed readiness does not expose a release API, feature flag, Kiosk action,
FERP/MESQL import, automatic/latest route selection, analytics inclusion,
inventory movement, or production workflow. Existing helpers remain internal
Python entry points. Normal user flows stay disabled until separately designed,
implemented, and verified.

## Rollout Acceptance Criteria

Phase 5H-B may start only with explicit source-apply approval, exact SQL hashes,
verified identity and backup, a clean first-rollout preflight, ready commands,
stop rules, and no unresolved partial state.

Phase 5H-C may start only after Phase 5H-B PASS, separate explicit approval,
one approved timestamped identity, accepted permanent nonproduction retention,
and confirmation that no API/FERP/MESQL path is exposed.

PASS is evidence-backed. Any unresolved identity, state, backup, partial schema,
fixture, or recovery question is `BLOCKED`; any executed check or invariant
failure is `FAIL`.

## Out of Scope

- Phase 5H-B or Phase 5H-C execution;
- database, Docker, migration, seed, helper or fixture mutation in Phase 5H-A;
- source repair, adoption, backfill, restore or destructive rollback;
- API, feature flag, Kiosk, IoT/OEE, FERP/MESQL or automatic route selection;
- analytics/KPI/export filter implementation;
- inventory design or implementation;
- committing or pushing Phase 5H-A design artifacts.

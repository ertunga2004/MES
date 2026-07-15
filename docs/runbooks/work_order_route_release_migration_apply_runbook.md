# Work-Order Route-Release Migration Apply Runbook

## Purpose

Validate `db/migrations/010_work_order_route_release.sql` on disposable logical
restores before any separately approved source apply. Prove exact `14 / 15 / 5`
shape, same-row route identity, empty first apply, idempotent and data-bearing
reapply, malformed-schema rejection, existing-table no-write behavior, source
integrity, cleanup, and health.

This runbook is `PLANNED_NOT_EXECUTED` as of `2026-07-15`.

## Preconditions

- Phase 5A architecture commit `8de2da4` is present.
- Schema plan and helper contract are reviewed.
- Migration static validation passes.
- Docker/PostgreSQL is healthy and exact source identity can be proven.
- Existing secure local credential handling is available without printing a
  password.
- User explicitly approves the future database smoke.
- A unique run timestamp, primary clone name, negative clone name, backup path,
  and evidence path are prepared.

Do not proceed when any identity, backup, prerequisite, or approval is missing.

## Scope

Permitted in the future approved run:

- read-only source baseline/final queries;
- one logical source backup;
- primary and negative disposable database creation/restoration;
- prerequisite and target migration apply only on verified clones;
- Canonical V2 seed apply only on verified clones when needed for fixture
  parents;
- clone-only release fixtures for data-bearing reapply;
- clone cleanup and health checks.

Not permitted:

- source migration apply in this runbook execution;
- source release/binding/lifecycle/queue row creation;
- helper/API/FERP/MESQL/runtime execution;
- retained V1 mutation;
- unverified database names or template cloning from source.

## Guardrails

- Never use source `mes` as a template or smoke target.
- Every mutating session must assert the exact disposable `current_database()`.
- Use a logical dump/restore, not filesystem/database-template cloning.
- Preserve the logical backup after cleanup.
- Apply only reviewed repository SQL to the primary clone.
- Keep negative fixture SQL outside permanent migrations unless separately
  reviewed.
- Do not expose credentials in command output or evidence.
- Abort on any source digest difference, unexpected relation, assertion error,
  cleanup mismatch, or unhealthy final state.

## Source Database Identity

Record before backup:

- container/service identity;
- host and port;
- source database name;
- server version;
- current database and current user;
- source schema presence;
- read-only transaction proof for baseline queries.

Expected source database is exactly `mes`. A name match alone is insufficient;
record server/container context too.

## Backup

1. Create a timestamped logical dump at a host path outside repository,
   transfer, build, cache, `.venv`, and `node_modules` folders.
2. Record path, byte size, timestamp, source identity, and dump-tool exit code.
3. Verify nonzero size and PostgreSQL dump header.
4. Retain the backup after the test.

The backup is the only restore source for both disposable clones.

## Baseline

In one source read-only transaction, record deterministic row counts and
ordered `to_jsonb(t)::text` digests for the established 15 tables:

1. `mes.items`
2. `mes.process_routes`
3. `mes.route_operations`
4. `mes.operation_steps`
5. `mes.station_event_sources`
6. `mes.work_order_operation_execution_state`
7. `mes.work_order_operation_steps`
8. `mes.operation_events`
9. `mes.operation_approvals`
10. `mes.production_flow_events`
11. `mes.work_orders`
12. `mes.work_order_operations`
13. `mes.station_queue`
14. `mes.locations`
15. `mes.station_location_bindings`

Also record:

- whether `mes.work_order_route_releases` is absent before apply;
- binding-table presence, exact shape, count, and digest when present;
- whether `uq_mes_process_routes_identity_snapshot` exists and its current
  ordered columns;
- source Canonical V2 route count;
- retained V1 execution status/current step/final step and event, approval,
  production-flow counts.

No baseline query may write or lock rows for mutation.

## Static SQL Review

Before database access, verify the migration:

- contains `BEGIN`, `COMMIT`, `CREATE TABLE IF NOT EXISTS`, conditional parent
  unique creation, two `CREATE INDEX IF NOT EXISTS` statements, and final
  exact-shape assertion;
- defines exactly 14 columns, 15 named release constraints, and 5 release
  indexes;
- defines parent identity order `(route_id, route_code, version)` and child
  order `(process_route_id, route_code, route_version)`;
- permits only two release modes and source `local_planning`;
- enforces lowercase 64-character SHA-256 and object metadata;
- contains no destructive statement, release/binding/operation/queue fixture,
  backfill, or existing lifecycle/status mutation;
- contains no release data-count assertion.

Record `git diff --check` and the exact migration checksum in evidence.

## Disposable Clone Strategy

Primary clone example:

```text
mes_work_order_route_release_schema_<timestamp>
```

Negative clone example:

```text
mes_work_order_route_release_schema_negative_<timestamp>
```

For each clone:

1. create an empty database with the exact generated name;
2. restore the same verified logical dump;
3. reconnect and assert exact `current_database()`;
4. compare the restored 15-table counts/digests with source before any clone
   migration;
5. stop and remove only that clone on mismatch.

Do not reuse a clone from an earlier run.

## First Apply

On the verified primary clone only:

1. Apply any missing prerequisite station-execution/lifecycle migrations in
   repository order.
2. Record binding migration/table state separately; apply migration 009 only
   when the approved smoke scope requires the current binding schema.
3. Apply Canonical V2 seed only to the clone when required for the V2 parent
   fixture; verify its established idempotency separately.
4. Capture clone existing-table counts/digests immediately before migration
   010.
5. Apply `010_work_order_route_release.sql` once.
6. Require a successful transaction and the documented assertion prefix to be
   absent from error output.

No release helper is called.

## Shape Verification

After first apply, verify from PostgreSQL catalogs:

- ordinary table `mes.work_order_route_releases` exists;
- exactly 14 columns in the documented order;
- exact data types, UDT names, `NOT NULL`, and defaults;
- exact serial sequence for `release_pk`;
- no mutable/forbidden column;
- exactly 15 constraints and their exact names/types;
- exact PK, two unique constraints, two FKs, and ten checks;
- exact mode/source allowlists, digest regex, and metadata object check;
- exactly five valid/ready indexes;
- exact route-version and released-at descending index definitions;
- no extra, duplicate, partial, or expression index.

Expected reported shape: `14 / 15 / 5`.

## Parent Route Constraint Verification

Verify:

- named `uq_mes_process_routes_identity_snapshot` exists once;
- type is unique, nondeferrable, and initially immediate;
- ordered parent columns are exactly `route_id, route_code, version`;
- existing process-route rows and digests are unchanged;
- child FK is exactly
  `fk_mes_work_order_route_releases_route_identity`;
- ordered child columns are exactly
  `process_route_id, route_code, route_version`;
- referenced parent columns and order match exactly;
- parent actions are PostgreSQL default `NO ACTION / NO ACTION`;
- no separate route-ID-only FK exists.

Optionally use a rolled-back invalid composite fixture to prove a route ID
cannot be paired with another code/version; do not retain that row.

## No-Backfill Verification

Immediately after first apply, before any fixture:

- release-table count is exactly `0`;
- binding, lifecycle operation, and queue counts/digests equal the pre-010 clone
  snapshot;
- work-order status/timestamps equal baseline;
- no release event/audit/integration row exists;
- V1/V2 config, runtime, event, approval, production flow, locations, and
  bindings are unchanged.

This is an evidence query, not part of migration SQL.

## Existing-Table No-Write Verification

Compare the pre-010 and post-first-apply counts/digests of the established 15
tables and binding table. Require equality for every table.

For `mes.process_routes`, the catalog gains one constraint/index but table data
count/digest must remain identical. Record the parent table OID and all existing
route identities before/after.

## Idempotency Reapply

Before adding data fixtures:

1. capture release table OID, sequence identity, complete column/constraint/
   index catalog snapshot, and empty-table digest;
2. apply migration 010 a second time;
3. require assertion success;
4. verify table OID, sequence, exact shape, parent constraint identity, and all
   existing-table counts/digests are unchanged;
5. verify release count remains `0`.

No duplicate parent constraint or release index is allowed.

## Data-Bearing Reapply Safety

On the same verified primary clone after empty reapply:

1. Create one clone-only work order fixture with a unique timestamped ID and no
   runtime/binding/queue effects.
2. Use the exact V2 parent route
   `ROUTE_BOX_PACKAGING_V2 / ROUTE_BOX_PACKAGING_V2 / 2` after clone-only seed
   validation.
3. Insert one valid clone-only release fixture directly by SQL with:
   - mode/source `route_generated / local_planning`;
   - nonblank actor;
   - positive count;
   - valid 64-character lowercase digest;
   - object metadata explicitly marking it disposable and not a production
     release.
4. Capture release row count, exact row digest, PK, release ID, both timestamps,
   sequence state, and schema snapshot.
5. Apply migration 010 again.
6. Require assertion success.
7. Verify schema/table/sequence identity is unchanged, fixture count remains
   one, and the fixture PK, values, metadata, timestamps, and digest are
   byte/semantic-equal.

The migration must not require an empty table on reapply. This fixture is not a
production release and never leaves the disposable clone.

## Malformed-Schema Negative Test

Use the separately restored and identity-verified negative clone. Before target
migration apply, construct at least one controlled malformed release schema;
the recommended run covers separate transactions/clones for:

- a missing required column;
- wrong digest check;
- wrong composite route FK or parent column order;
- wrong mode allowlist;
- unexpected extra index.

For each case:

1. capture pre-attempt catalog/data snapshot;
2. apply migration 010;
3. require transaction failure with prefix
   `Work-order route release schema assertion failed:`;
4. prove no silent repair and no partially retained parent constraint/index;
5. prove all existing-table counts/digests and malformed fixture shape remain
   equal to the pre-attempt snapshot after rollback;
6. reset only by recreating the disposable negative clone, not by modifying a
   repository migration.

A generic error before the documented assertion should be treated as failure
of the migration design and investigated.

## Clone Cleanup

After evidence capture:

1. identify sessions connected only to the exact primary/negative clone names;
2. terminate only those clone sessions;
3. remove only the two verified disposable databases;
4. query database catalog and prove exact/prefix matching database count is
   zero;
5. confirm the logical backup still exists.

Do not remove the backup or any source data.

## Source Final Integrity

In a new source read-only transaction, repeat the same 15-table counts/digests
and extended observations.

Required:

- `15/15` count equality;
- `15/15` digest equality;
- release-table presence/absence and rows unchanged from source baseline;
- binding-table state unchanged;
- parent identity constraint state unchanged because source apply did not run;
- Canonical V2 source route count unchanged;
- retained V1 runtime/event/approval/production-flow snapshot unchanged;
- no clone-only work-order or release ID exists in source.

Any difference blocks PASS.

## Health

Verify after cleanup:

- PostgreSQL/container service reports healthy;
- source `mes` accepts the read-only health query;
- no disposable clone remains;
- no background database/smoke process remains;
- repository working tree contains only the expected uncommitted Phase 5B
  artefacts.

## PASS Criteria

PASS requires all of the following:

- backup and restored-clone baseline verified;
- first apply succeeds with exact `14 / 15 / 5` shape;
- parent same-row unique/FK contract is exact;
- first apply creates zero release rows and performs no backfill;
- all existing-table data digests remain equal;
- empty reapply preserves identities and shape;
- data-bearing reapply preserves the fixture and timestamps;
- malformed schema fails explicitly and rolls back without silent repair;
- source final integrity is exact;
- both clones are removed and health passes.

## FAIL Criteria

FAIL includes:

- missing/unverified backup or database identity;
- any wrong column, constraint, FK action, check, or index;
- release row/backfill on first apply;
- reapply failure with a valid data row;
- fixture/timestamp/digest change on data-bearing reapply;
- malformed schema accepted or silently changed;
- existing-table or source digest difference;
- retained V1 or source Canonical V2 change;
- incomplete clone cleanup or unhealthy final service.

Use `BLOCKED` rather than PASS when an assertion cannot be executed or proven.

## Rollback and Restore

Disposable failure rollback is transaction rollback followed by exact clone
removal/recreation. Do not hand-repair the clone and call the result idempotent.

No source schema change occurs in this runbook. If a future separately approved
source apply fails, stop, capture evidence, and decide between a reviewed
forward fix and logical restore. Do not automatically remove a potentially
populated release table or parent constraint.

## Evidence Template

```text
Result:
Run timestamp:
Repository commit:
Migration checksum:

Source identity:
Backup path / bytes / header:
Primary clone:
Negative clone:

Source baseline 15/15:
Release table pre-apply:
Binding table baseline:
Parent constraint baseline:
Retained V1 baseline:
Canonical V2 source count:

Clone restore equality:
Prerequisites / V2 seed:
First apply:
Shape columns / constraints / indexes:
Parent unique constraint:
Composite child FK / actions:
Initial release row count:
Existing-table no-write:

Empty reapply:
Table OID / sequence / schema unchanged:
Data-bearing fixture identity:
Data-bearing reapply:
Fixture values / timestamps unchanged:

Malformed cases:
Observed error prefix:
Silent repair absent:
Negative rollback integrity:

Source final 15/15:
Extended source integrity:
Primary clone removed:
Negative clone removed:
Remaining matching databases:
Health:
Backup retained:

Guardrails observed:
Open risks / blockers:
```

# Work-Order Route-Release Schema Plan

## Status

`READY_FOR_DISPOSABLE_MIGRATION_VALIDATION`

Last updated: `2026-07-15`.

This document fixes the Phase 5B physical schema contract. It does not apply a
migration or create a release, lifecycle operation, binding, queue row, or
backfill.

## Purpose

Add one immutable route-release snapshot per work order so release identity,
the exact selected process-route row, release mode, operation-set count/digest,
actor, source, and timestamps are durable before execution.

The work-order sidecar complements, rather than replaces,
`mes.work_order_operation_route_bindings`: the release row proves the frozen
work-order route and complete set contract; binding rows prove every individual
lifecycle/config-operation pair.

## Repository Conventions

The draft follows established migrations, especially
`009_work_order_operation_route_binding.sql`:

- additive `BEGIN`/`COMMIT` transaction;
- `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`;
- `BIGSERIAL` surrogate identity;
- `TIMESTAMPTZ NOT NULL DEFAULT now()` server timestamps;
- `JSONB NOT NULL DEFAULT '{}'::jsonb` plus object-type check;
- `uq_`, `fk_`, `ck_`, and `ix_` names;
- catalog-based exact-shape assertions and explicit exceptions.

Phase 5B additionally names the primary key `pk_...` because the required
physical contract includes the exact PK name and exactly 15 named constraints.

## Selected Table

Exact table: `mes.work_order_route_releases`.

MVP cardinality:

- one work order has at most one release row;
- one release ID identifies exactly one work order;
- a release row references exactly one process-route identity snapshot.

The table is insert-once. No release lifecycle state is modeled in this phase.

## Column Model

The table has exactly 14 columns in this order:

| # | Column | Type | Null | Default | Source |
|---:|---|---|---|---|---|
| 1 | `release_pk` | `BIGSERIAL` | no | owned sequence | database |
| 2 | `release_id` | `TEXT` | no | none | caller/orchestrator |
| 3 | `order_id` | `TEXT` | no | none | caller |
| 4 | `process_route_id` | `TEXT` | no | none | exact route read |
| 5 | `route_code` | `TEXT` | no | none | request/exact route read |
| 6 | `route_version` | `INTEGER` | no | none | request/exact route read |
| 7 | `release_mode` | `TEXT` | no | none | caller |
| 8 | `release_source` | `TEXT` | no | none | caller |
| 9 | `released_by` | `TEXT` | no | none | authenticated actor/service |
| 10 | `released_at` | `TIMESTAMPTZ` | no | `now()` | database |
| 11 | `route_operation_count` | `INTEGER` | no | none | validated canonical set |
| 12 | `operation_set_digest` | `TEXT` | no | none | canonical SHA-256 |
| 13 | `metadata` | `JSONB` | no | `'{}'::jsonb` | caller, non-identity audit |
| 14 | `created_at` | `TIMESTAMPTZ` | no | `now()` | database |

Only `release_pk`, `released_at`, and `created_at` are database-generated.

## Parent Route Identity Constraint

Add the named parent unique constraint:

```text
uq_mes_process_routes_identity_snapshot
mes.process_routes(route_id, route_code, version)
```

The release table references it through:

```text
fk_mes_work_order_route_releases_route_identity
(process_route_id, route_code, route_version)
-> mes.process_routes(route_id, route_code, version)
```

This composite FK is the sole route-parent FK. A second FK on route ID is
unnecessary. Exact child and parent column order is asserted. PostgreSQL
defaults apply for both actions: `NO ACTION` on parent key change and parent
row removal. The FK is nondeferrable with simple match semantics.

The migration changes no existing process-route row. If the named parent
constraint exists with a different type, column set, order, or deferrability,
the migration fails. If absent, it is added conditionally and asserted.

## Constraint Model

The release table has exactly 15 named constraints:

Primary key:

- `pk_mes_work_order_route_releases(release_pk)`.

Unique:

- `uq_mes_work_order_route_releases_release_id(release_id)`;
- `uq_mes_work_order_route_releases_order_id(order_id)`.

Foreign keys:

- `fk_mes_work_order_route_releases_order(order_id)` to
  `mes.work_orders(order_id)`;
- `fk_mes_work_order_route_releases_route_identity` using the exact composite
  route identity above.

Checks:

- `ck_mes_work_order_route_releases_release_id_nonblank`;
- `ck_mes_work_order_route_releases_process_route_id_nonblank`;
- `ck_mes_work_order_route_releases_route_code_nonblank`;
- `ck_mes_work_order_route_releases_route_version_positive`;
- `ck_mes_work_order_route_releases_mode`;
- `ck_mes_work_order_route_releases_source`;
- `ck_mes_work_order_route_releases_released_by_nonblank`;
- `ck_mes_work_order_route_releases_operation_count_positive`;
- `ck_mes_work_order_route_releases_digest`;
- `ck_mes_work_order_route_releases_metadata_object`.

Exact semantics:

- release ID, process-route ID, route code, and actor are nonblank after trim;
- route version and operation count are positive;
- modes are only `route_generated` and
  `explicit_existing_operation_mapping`;
- source is only `local_planning` in the initial schema;
- digest is exactly 64 lowercase hexadecimal characters;
- metadata top level is a JSON object.

Reserved sources `ferp_import`, `mesql_import`, and `migration_backfill` are not
accepted early; a future additive migration may expand the check.

## Index Model

The release table has exactly five indexes.

Constraint-backed:

- `pk_mes_work_order_route_releases`;
- `uq_mes_work_order_route_releases_release_id`;
- `uq_mes_work_order_route_releases_order_id`.

Additional nonunique B-tree indexes:

```sql
(route_code, route_version, released_at DESC)
```

named `ix_mes_work_order_route_releases_route_version`, and:

```sql
(released_at DESC)
```

named `ix_mes_work_order_route_releases_released_at`.

The assertion requires these exact names and definitions, valid/ready indexes,
no predicates or expressions, and an overall count of five. An extra or
duplicate index is malformed schema.

## Defaults and Nullability

All 14 columns are `NOT NULL`. Identity-bearing fields have no default.
Database defaults are restricted to:

- the `BIGSERIAL` owned sequence for `release_pk`;
- `now()` for `released_at` and `created_at`;
- `'{}'::jsonb` for metadata.

Exact type, UDT, ordinal position, nullability, serial sequence name, and
default expressions are asserted.

## Immutability

The table intentionally has no:

- `active`;
- `updated_at`;
- `deleted_at`;
- `effective_from` or `effective_to`;
- `superseded_by`;
- `cancelled_at`;
- reroute field.

No application mutation helper is planned. Correction, cancellation, or
supersession requires a later audited architecture decision and cannot rewrite
the MVP snapshot.

## Idempotent Migration Strategy

The migration is additive, transaction-safe, and exact-shape rejecting:

1. Require the `mes.process_routes` parent and exact identity columns.
2. Validate an existing named parent constraint or add it conditionally.
3. Preflight an existing release relation so missing/extra columns fail before
   additional index creation.
4. Create the exact release table if absent.
5. Create the two additional indexes if absent.
6. Assert the full parent/table/column/default/constraint/FK/check/index shape.
7. Commit only if every assertion passes.

Correct absent schema is created. Correct present schema is a no-op plus
successful assertions. Malformed present schema raises an exception and the
transaction rolls back; no silent repair is accepted.

## Exact-Shape Assertion

The final transactional assertion verifies:

- `mes` schema and an ordinary release table;
- exactly 14 ordered columns with exact types, UDTs, nullability, and defaults;
- exact serial sequence ownership/name;
- no forbidden mutable column;
- exact parent named unique constraint and ordered columns;
- exactly 15 release constraints with exact names/types;
- exact PK, unique keys, order FK, composite route FK, FK actions, match type,
  and deferrability;
- all 10 normalized check definitions, including mode/source allowlists,
  digest regex, and metadata object check;
- exactly five valid/ready indexes with exact names;
- exact two additional index definitions and no duplicate equivalent index.

The assertion intentionally does not inspect release-table data count. A
schema reapply must remain valid after production release rows exist.

## Malformed-Schema Rejection

The common error prefix is:

```text
Work-order route release schema assertion failed:
```

Explicit rejection covers:

- missing/extra column or nonordinary relation;
- wrong column order, type, nullability, sequence, or default;
- forbidden mutable column;
- missing, extra, wrongly named, or wrongly typed constraint;
- wrong parent identity constraint;
- wrong order or composite route FK and FK action;
- wrong mode/source/digest/metadata check;
- missing, invalid, extra, duplicate, or wrongly defined index.

Conditional DDL never normalizes a malformed existing table. Any provisional
parent constraint addition is in the same transaction and rolls back if a
later release-table assertion fails.

## Data and Backfill Boundary

The migration creates no:

- release row;
- operation binding;
- lifecycle operation;
- queue row;
- work-order status mutation;
- legacy adoption or backfill;
- V1/V2 config mutation.

Initial apply is expected to leave the release table empty, but that is a
runbook/evidence assertion, not migration SQL. Data-bearing reapply is a
required disposable-clone test.

## Helper Mapping

The future helper maps request and validated data as follows:

- request `release_id` -> `release_id`;
- request `work_order_id` -> existing database `order_id`;
- exact route read `route_id` -> `process_route_id`;
- exact request/read identity -> `route_code`, `route_version`;
- selected mode/source/actor -> corresponding immutable columns;
- validated ordered pair count -> `route_operation_count`;
- canonical JSON digest -> `operation_set_digest`;
- non-identity audit context -> `metadata`.

The helper inserts the release row on the shared release transaction cursor;
it does not rely on metadata for identity.

## Concurrency Considerations

Unique release ID and order ID constraints serialize competing identities at
the database boundary. The write helper locks the work order and existing
release scope before its first write. A unique violation is not blindly
retried: after transaction rollback, authoritative read helpers classify the
winner as exact replay or deterministic conflict.

The composite route FK prevents a concurrent or erroneous request from mixing
a route ID with a different code/version snapshot. Existing released rows keep
their parent reference; route version changes require a new process-route row.

## Source Apply Boundary

Phase 5B does not apply the migration anywhere. Future validation order is:

1. static SQL review;
2. first apply and idempotent reapply on a disposable logical restore;
3. data-bearing reapply on that clone;
4. malformed-schema rejection on a separate negative clone;
5. source 15-table and retained V1 integrity verification;
6. separately approved source apply only after evidence review.

No release writer is enabled against source by schema apply alone.

## Rollback Strategy

Before source apply, prefer correcting the uncommitted/additive draft and
re-running disposable validation. A failed migration transaction leaves no
partial parent constraint, table, or index.

After an approved source apply, do not automatically remove a populated
release table or parent constraint. Recovery is a separately approved restore
or forward-fix decision using the retained logical backup. The table has no
destructive rollback migration in Phase 5B.

## Deferred Schema Decisions

- Future release sources and their additive check expansion.
- Release cancellation/supersession history.
- Optional/rework lifecycle operations.
- Config-version write protection after first release.
- FERP/MESQL ownership/reconciliation fields.
- Runtime completion bridge persistence, if later evidence requires it.

## Acceptance Criteria

- Migration path is `db/migrations/010_work_order_route_release.sql` with no
  number collision.
- Release table has exactly `14 / 15 / 5` columns/constraints/indexes.
- Parent unique constraint and child composite FK guarantee the same route row.
- Only the accepted modes and initial source are allowed.
- Digest and metadata checks are exact.
- Correct first apply and reapply are supported without data-count dependency.
- Malformed schema fails with the documented prefix and transaction rollback.
- Migration creates no data/backfill and changes no existing route row.
- No source apply, helper implementation, API, FERP, MESQL, runtime, lifecycle,
  binding, queue, approval, production-flow, or inventory action occurs in
  Phase 5B.

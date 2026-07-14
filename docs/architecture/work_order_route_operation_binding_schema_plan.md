# Work-Order Operation / Route-Operation Binding Schema Plan

## Status

`READY_FOR_MIGRATION_DRAFT_REVIEW`

The migration draft is not applied. The target table does not exist in the
source database as a result of this planning task, and no binding row is
created.

## Purpose

Define the additive physical schema for the accepted explicit mapping:

```text
work_order_operation_id -> immutable route_operation_id binding
```

The relation preserves the selected route-operation and route-version identity
for one lifecycle operation instance. It is an audit sidecar, not lifecycle,
queue, runtime-state, config-master, or inventory state.

## Existing Schema Conventions

- Migration numbering permits parallel files under the same prefix. Existing
  prefixes extend through `008`; `009` is the next unused sequential prefix.
- Station-execution tables generally use a `BIGSERIAL` internal primary key and
  a separate stable `TEXT` identifier with a unique constraint.
- `mes.work_order_operations.work_order_operation_id` is `UUID` and is its
  primary key.
- `mes.route_operations.route_operation_id` is `TEXT NOT NULL UNIQUE`.
- Timezone-aware audit fields use `TIMESTAMPTZ` with `now()` defaults.
- Metadata uses `JSONB NOT NULL DEFAULT '{}'::jsonb`.
- Constraint names use `pk` through the column declaration and explicit
  `uq_mes_*`, `fk_mes_*`, and `ck_mes_*` names for business constraints.
- Lookup indexes use `ix_mes_*`; unique lookup indexes use `ux_mes_*`.
- Additive schema uses `CREATE TABLE IF NOT EXISTS` and
  `CREATE INDEX IF NOT EXISTS`.
- Recent controlled SQL uses `BEGIN`, assertion-driven `RAISE EXCEPTION`, and
  `COMMIT` so `ON_ERROR_STOP=1` rolls back a failed apply.
- Foreign keys in the station-execution sidecar schema normally rely on the
  PostgreSQL default `NO ACTION`; cascade is used only in older lifecycle-owned
  tables. Historical bindings therefore use `NO ACTION` for delete and update.
- The repository uses explanatory SQL file headers. It has no established
  `COMMENT ON TABLE/COLUMN` convention, so the draft does not introduce one.

## Selected Physical Model

Use an internal `BIGSERIAL` primary key plus a stable unique textual binding
ID. This matches the station-execution schema's public/audit ID pattern and
keeps storage identity separate from the immutable audit identity.

```text
table = mes.work_order_operation_route_bindings
internal PK = binding_pk BIGSERIAL
stable ID = binding_id TEXT UNIQUE
cardinality = UNIQUE(work_order_operation_id)
mutation model = insert-only
```

## Table Identity

The selected table is `mes.work_order_operation_route_bindings`. One row binds
one concrete lifecycle operation instance to one exact versioned route
operation. The table does not duplicate `work_order_id`, station, operation
code, route code, or route version because those values remain available
through their authoritative referenced rows.

## Column Definitions

| Column | Physical type | Nullable | Default | Constraint | Meaning |
| --- | --- | --- | --- | --- | --- |
| `binding_pk` | `BIGSERIAL` | No | sequence | Primary key | Internal storage identity |
| `binding_id` | `TEXT` | No | None | Unique, nonblank | Stable public/audit identity |
| `work_order_operation_id` | `UUID` | No | None | Unique, FK | Lifecycle operation instance |
| `route_operation_id` | `TEXT` | No | None | FK | Exact versioned config operation |
| `binding_source` | `TEXT` | No | None | Controlled check | Binding workflow |
| `bound_by` | `TEXT` | No | None | Nonblank check | Actor or system identity |
| `bound_at` | `TIMESTAMPTZ` | No | `now()` | None | Business binding timestamp |
| `metadata` | `JSONB` | No | `'{}'::jsonb` | JSON object check | Non-identity audit context |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | None | Database row creation timestamp |

## Primary and Stable IDs

`binding_pk` follows the local station-execution internal-key convention.
`binding_id` is the stable immutable identifier exposed to audit and helper
contracts. ID generation is intentionally deferred to the controlled write
helper phase; this migration creates no row and no generation function.

## Cardinality

`UNIQUE(work_order_operation_id)` enforces at most one effective binding for a
lifecycle operation instance. `route_operation_id` is deliberately not unique:
one route-operation definition can be used by many work-order operation
instances.

## Foreign Keys

- `work_order_operation_id` references
  `mes.work_order_operations(work_order_operation_id)`.
- `route_operation_id` references
  `mes.route_operations(route_operation_id)`.
- Delete behavior: PostgreSQL `NO ACTION`.
- Update behavior: PostgreSQL `NO ACTION`.

No cascade or nulling action is allowed. Deleting either referenced identity
must not silently erase or detach binding history.

## Binding Sources

The Phase 4C constraint accepts only:

- `manual_setup`
- `work_order_release`

No legacy-backfill source is enabled. Any later backfill source requires a
separately approved Phase 7 migration and workflow.

## Audit Fields

`bound_by` is required and nonblank. A future system-owned workflow may use an
explicit actor such as `SYSTEM`, but this draft seeds no actor or binding.
`bound_at` records the business binding time; `created_at` records row creation.
They may have equal values but retain different semantics.

## Metadata Contract

`metadata` stores only non-identity correlation and audit context. It cannot
replace either foreign key, the source, or actor. It must be a JSON object;
arrays, scalars, and JSON null are rejected by
`jsonb_typeof(metadata) = 'object'`.

## Immutability

The MVP contract is insert once, with no update, delete, or rebind helper.
Database uniqueness prevents multiple bindings for one lifecycle operation.
The application/helper contract will prevent update, delete, and rebind.

The repository has no immutable-row trigger standard. The migration therefore
does not introduce a trigger or function. A database-level mutation-blocking
trigger is deferred unless a future repository-wide standard requires it.

## Indexes

- The primary key indexes `binding_pk`.
- The stable-ID unique constraint indexes `binding_id`.
- The lifecycle-operation unique constraint indexes
  `work_order_operation_id`; no duplicate standalone index is created.
- `ix_mes_work_order_operation_route_bindings_route_operation` supports reverse
  lookup and audit by `route_operation_id`.

No early index is added for source, actor, timestamps, or metadata.

## Idempotency

The migration uses `CREATE TABLE IF NOT EXISTS` and
`CREATE INDEX IF NOT EXISTS`. Reapply is successful only when the existing
table has the exact reviewed shape. A same-name but incompatible table,
constraint, or index causes the assertion block to raise an exception and the
transaction to roll back.

## Exact-Shape Assertions

The migration asserts:

- schema and table existence;
- exactly nine expected columns;
- exact column names, physical types, nullability, and defaults;
- exact `BIGSERIAL` sequence ownership and `binding_pk` primary key;
- unique stable ID and unique lifecycle-operation constraints;
- both foreign-key targets and default `NO ACTION` behavior;
- exact controlled-source, metadata-object, and nonblank checks;
- exactly nine expected constraints;
- the exact non-unique route-operation lookup index;
- exactly four expected indexes, including constraint-backed indexes;
- no duplicate lifecycle-operation index;
- absence of `active`, `updated_at`, `deleted_at`, `effective_from`,
  `effective_to`, and `superseded_by`.

The assertion writes no rows and does not read lifecycle, runtime, or config
table data.

## Compatibility

The migration adds one sidecar table only. It does not alter existing
lifecycle, queue, runtime, station execution config, station/location, API,
Kiosk, IoT, OEE, MESQL, or FERP behavior. Existing explicit runtime-init
parameters remain a transitional interface until later phases.

## Legacy Data

Existing lifecycle rows remain valid and unbound. Existing V1 runtime and
historical execution metadata are not rebound or changed. Missing binding is a
state to report, not a signal to infer config identity.

## No-Backfill Decision

The migration contains no seed or data insert. It does not infer from station,
operation code, sequence, combined fields, or latest-active routes. Automatic
legacy backfill remains outside this phase.

## Risks

- A future writer could violate semantic immutability through ad hoc SQL even
  though uniqueness blocks multiple rows; operational permissions and helper
  contracts must remain controlled.
- Binding creation and work-order release could diverge unless Phase 5 uses one
  transaction.
- A same-name malformed pre-existing object can make `IF NOT EXISTS` appear
  successful; the exact-shape assertion is therefore mandatory.
- A future correction requirement needs an audited design and must not become
  an in-place update to this MVP row.

## Migration Scope

Draft path:

```text
db/migrations/009_work_order_operation_route_binding.sql
```

It creates one table, its constraints, and one explicit lookup index. It does
not alter an existing table, insert data, backfill legacy rows, create a
trigger, or create a stored procedure/helper.

## Acceptance Criteria

- The draft is additive and transaction-wrapped.
- Physical types match referenced repository identities.
- One lifecycle operation has at most one binding.
- One route operation may have many bindings.
- Source and metadata checks are exact.
- Delete/update cascade behavior is absent.
- Reapply succeeds only for the exact reviewed shape.
- The table remains empty after future apply and reapply.
- Existing 15-table baselines remain count/digest-identical.
- No migration or database apply occurs during this draft task.

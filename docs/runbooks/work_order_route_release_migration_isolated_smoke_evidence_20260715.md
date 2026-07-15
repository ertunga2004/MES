# Work-Order Route-Release Migration Isolated Smoke Evidence

## Summary

- Date: `2026-07-15`.
- Result: `PASS`.
- Phase 5B schema artifacts were committed once, regression remained green, and
  migration `010` passed isolated first-apply, empty-reapply, data-bearing
  reapply, exact-shape, no-backfill, and rollback tests.
- Source database `mes` remained unchanged. All mutations were confined to
  disposable databases restored from a logical dump using `template0`.

## Schema Commit

- Commit: `3e4771154d19d43da6aee42a8939632e19e1c324` (`3e47711`).
- Subject: `feat: add work-order route release schema`.
- Exact committed paths:
  - `db/migrations/010_work_order_route_release.sql`
  - `docs/architecture/work_order_route_release_schema_plan.md`
  - `docs/architecture/work_order_release_helper_contract.md`
  - `docs/runbooks/work_order_route_release_migration_apply_runbook.md`
  - `docs/architecture/CURRENT_STATE.md`
- Commit scope: five files, `2197` insertions.
- Duplicate commit: not created.
- Push: not performed.

## Regression

- Targeted `tests.test_mes_web_mesql_v2`: `181` tests, `OK`.
- Combined station-execution config, station-location, and MESQL V2 suite:
  `217` tests, `OK`.
- Only the pre-existing FastAPI `on_event` deprecation warnings were observed.
- `git diff --check`: PASS.

## Migration Static Review

- Path: `db/migrations/010_work_order_route_release.sql`.
- SHA-256: `5B7C6CF7261095A6B00C7EF9170ED7F262F648053BDC0B1E3EA4A4B4C7B551F6`.
- Additive, transactional, idempotent, exact-shape rejecting, and
  data-bearing-reapply safe: PASS.
- Required `BEGIN`, `COMMIT`, guarded table/index creation, conditional parent
  unique creation, catalog assertions, and documented failure prefix are
  present.
- Destructive SQL, release/binding/lifecycle/queue fixture DML, work-order
  update, seed/backfill, and release-row-count assertion: absent.
- Assertion prefix:
  `Work-order route release schema assertion failed:`.

## Source Database

- Container: `mes_postgres` (`c5e10132d9ce`), PostgreSQL `16.14`.
- Database/user: `mes` / `mes`; host port: `5433`.
- Container remained healthy and was not rebuilt, recreated, restarted, or
  stopped.
- Migration `009`, migration `010`, Canonical V2 seed, fixtures, and helper
  calls were not run on source `mes`.

## Backup

- Run stamp: `20260715-112427`.
- Host path:
  `C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_work_order_route_release_schema_smoke_20260715-112427.sql`.
- Container path:
  `/backups/mes_before_work_order_route_release_schema_smoke_20260715-112427.sql`.
- Size: `2,886,710` bytes.
- Plain logical `pg_dump` header was present and no password was printed.
- Backup was retained after clone cleanup.

## Source Baseline

Deterministic `to_jsonb` row digests were captured in a read-only source stage.

| Table | Count | MD5 digest |
|---|---:|---|
| `mes.items` | 3 | `c120ee7ee8808e4280bcb02895f76e8c` |
| `mes.process_routes` | 1 | `163f416bfdcf16ca469e43adbd47b324` |
| `mes.route_operations` | 2 | `92a859fc57182954c5070670928c89e6` |
| `mes.operation_steps` | 5 | `3829d1b0a5185a4ac59a509532b4abc8` |
| `mes.station_event_sources` | 4 | `c70220808f91a8562d14377c47b2a698` |
| `mes.work_order_operation_execution_state` | 1 | `293d69efdb273e2bd0a8e6062f930d28` |
| `mes.work_order_operation_steps` | 3 | `7bdf8ce32a27a8bdec4b7f5cc47a7fc3` |
| `mes.operation_events` | 4 | `5bcb14870e3147f60e15cebdd146bba4` |
| `mes.operation_approvals` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.production_flow_events` | 0 | `d41d8cd98f00b204e9800998ecf8427e` |
| `mes.work_orders` | 12 | `283cf9b28e57bc5d6d398169f935473d` |
| `mes.work_order_operations` | 8 | `fb74f90dcb2460542ad6422609144b6f` |
| `mes.station_queue` | 13 | `2760e411b756b4194df0f86e4987cb5a` |
| `mes.locations` | 8 | `03842ba4695966bbc65a4ec3eac438e9` |
| `mes.station_location_bindings` | 8 | `f5274a415a5d1744af064a539693d0be` |

## Extended Source Baseline

- `mes.work_order_route_releases`: absent.
- `uq_mes_process_routes_identity_snapshot`: absent.
- `mes.work_order_operation_route_bindings`: absent.
- Canonical V2 route count: `0`.
- Retained V1 operation
  `c8f0be13-9dc7-4e66-9fbb-43547a5f1808` remained
  `active / OPERATOR_OBSERVATION_APPROVAL / pending`.
- Retained events / approvals / production flow: `4 / 0 / 0`.

## Isolation Strategy

- Primary clone: `mes_work_order_route_release_schema_20260715_112427`.
- Each database was created empty from `template0` and restored from the source
  logical dump; `TEMPLATE mes` was never used.
- Every mutation used an exact task-created database name, the required prefix,
  and a `database != mes` boundary.
- PostgreSQL's 63-byte identifier limit makes the full negative name plus full
  timestamp invalid. Negative names therefore used the deterministic compact
  timestamp token `2607151124`, preserving the exact prefix and case token.

## Primary Clone Restore

- Restore with `ON_ERROR_STOP=1`: PASS.
- Source/clone counts equal: `15/15`.
- Source/clone digests equal: `15/15`.
- Release table, parent snapshot constraint, binding table, V2 route count, and
  retained V1 state matched source before clone-only changes.

## Canonical V2 Seed

- Applied only to the primary clone from
  `db/migrations/006_station_execution_seed_canonical_v2.sql`.
- V2 route / operations / steps: `1 / 2 / 4`.
- OP10 / OP20 steps: `3 / 1`.
- Configured / resolved roles: `5 / 5`.
- V1 configuration remained present and unchanged.
- Release, work-order, lifecycle, binding, queue, runtime, event, approval, and
  production-flow rows created by the seed: `0`.

## Pre-010 Clone Baseline

After the intentional V2 config seed, the established table snapshot was:

- `process_routes`: `2`, digest `7671da8005c874ebf9f347481ecce2f0`.
- `route_operations`: `4`, digest `3deb87d4573a1f76b08bd9c53bdf2748`.
- `operation_steps`: `9`, digest `5cf775912e6d80098f330aedb27c12b0`.
- `items`: `3`, digest `c120ee7ee8808e4280bcb02895f76e8c`.
- The other eleven established table counts/digests remained equal to source.
- Release table and binding table were absent before migration `010`.

## First Apply

- `APPLY_DATABASE=mes_work_order_route_release_schema_20260715_112427`.
- Migration `010` ran with `ON_ERROR_STOP=1` and committed without assertion
  failure.
- Release rows after first apply: `0`.

## Exact Shape

- Ordinary table: true; table OID: `109938`.
- Columns / constraints / indexes: `14 / 15 / 5`.
- Ordered columns exactly matched the contract:
  `release_pk`, `release_id`, `order_id`, `process_route_id`, `route_code`,
  `route_version`, `release_mode`, `release_source`, `released_by`,
  `released_at`, `route_operation_count`, `operation_set_digest`, `metadata`,
  `created_at`.
- All columns were `NOT NULL`; types/defaults and `BIGSERIAL` ownership matched.
- Constraint distribution: `1` PK, `2` unique, `2` FK, `10` check.
- Index distribution: `3` constraint-backed and `2` additional.
- Catalog digests: columns `e7c7c894328808020bd34378ec8d72bc`,
  constraints `ca92be41792083babf0ef79fc949060d`, indexes
  `dd952b6734224d65e954f845d671a11e`.

## Parent Route Identity

- Parent constraint OID: `109936`.
- `uq_mes_process_routes_identity_snapshot` was exact, unique,
  nondeferrable, and initially immediate on
  `(route_id, route_code, version)`.
- Child `fk_mes_work_order_route_releases_route_identity` was exact on
  `(process_route_id, route_code, route_version)` referencing
  `(route_id, route_code, version)`.
- FK behavior: `MATCH SIMPLE`, `ON UPDATE NO ACTION`, `ON DELETE NO ACTION`,
  nondeferrable.
- Separate route-ID-only FK count: `0`.

## Same-Row FK Negative Insert

- A transaction used the existing V2 route ID with the V1 code/version
  snapshot.
- Insert failed on the exact composite FK with SQLSTATE `23503`.
- The transaction was rolled back and release row count remained `0`.
- PostgreSQL sequence consumption from the failed insert was retained as normal
  nontransactional sequence behavior; no release row was retained.

## No-Backfill Verification

- Initial release row count: `0`.
- No release, work-order, lifecycle, binding, queue, runtime, event, approval,
  or production-flow row was backfilled.
- Work-order status and timestamps were unchanged.

## Existing-Table No-Write Verification

- Pre/post migration count equality: `15/15`.
- Pre/post migration digest equality: `15/15`.
- `process_routes` row data was unchanged; only the intended catalog-level
  parent unique constraint/index was added.
- V1/V2 config data, locations, and station-location bindings were unchanged.

## Empty Reapply

- Second apply: PASS.
- Table OID `109938`, sequence OID `109937`, sequence name, column/constraint/
  index digests, parent OID/definition, and release count were unchanged.
- No duplicate parent constraint or index was created.

## Clone-Only Work-Order Fixture

- ID: `WO-ROUTE-RELEASE-SCHEMA-SMOKE-20260715-112427`.
- Confirmed absent from source before insertion.
- Inserted only in the primary clone as the minimum release-FK parent, with
  disposable schema-smoke metadata.
- It created no lifecycle operation, binding, queue, runtime, event, approval,
  or flow row.

## Clone-Only Release Fixture

- Release ID: `RELEASE-SCHEMA-SMOKE-20260715-112427`.
- Release PK: `2`.
- Exact route identity: `ROUTE_BOX_PACKAGING_V2 / ROUTE_BOX_PACKAGING_V2 / 2`.
- Mode/source/actor: `route_generated / local_planning / SCHEMA_SMOKE`.
- Route operation count: `2`.
- Operation-set digest:
  `4063a5c72fd4d38f11757a4bf1115f83e1c05e8b97624deb808193c5d0fcb2e2`.
- Metadata:
  `{"purpose":"data_bearing_migration_reapply","production_release":false,"disposable_clone_only":true,"schema_reapply_fixture":true}`.
- `released_at` / `created_at`:
  `2026-07-15 08:30:54.889073+00` / `2026-07-15 08:30:54.889073+00`.
- Row MD5 digest: `e080ee0140f82717d679ae643218cd84`.
- The clone-only work-order and release rows exist solely to verify data-bearing migration reapply. They are not production releases.

## Data-Bearing Reapply

- Third apply with one release row: PASS.
- Count `1`; PK, all values, metadata, both timestamps, and row digest remained
  unchanged.
- Sequence OID/name/state remained `109937` /
  `work_order_route_releases_release_pk_seq` / `2:true`.
- Table OID, schema digests, and parent constraint remained unchanged.

## Primary Clone Integrity

- Intentional deltas were exactly one clone-only work order and one clone-only
  release.
- Lifecycle operation, binding, queue, runtime, event, approval, and
  production-flow deltas: `0`.
- Config/master/location data and retained V1 were unchanged after the V2 seed
  baseline.

## Missing-Column Negative Test

- Clone:
  `mes_work_order_route_release_negative_missing_column_2607151124`.
- Restore equality: `15/15`; correct initial shape: `14 / 15 / 5`.
- Controlled malformed shape: `13 / 14 / 5`, with
  `operation_set_digest` absent.
- Reapply exit: `3`; documented prefix and reason
  `existing release column set mismatch` observed.
- Silent repair: absent; malformed schema and established data snapshots were
  identical before/after rollback.

## Wrong-Digest Negative Test

- Clone: `mes_work_order_route_release_negative_wrong_digest_2607151124`.
- Restore equality: `15/15`; correct initial shape: `14 / 15 / 5`.
- Digest constraint was replaced under the same name with a nonblank-only check;
  constraint count remained `15`.
- Reapply exit: `3`; documented prefix and `check constraint mismatch` observed.
- Silent repair: absent; wrong constraint and data remained unchanged after
  rollback.

## Wrong-Route-FK Negative Test

- Clone: `mes_work_order_route_release_negative_wrong_route_fk_2607151124`.
- Restore equality: `15/15`; correct initial shape: `14 / 15 / 5`.
- Exact composite FK was replaced under the same name with the valid but wrong
  `process_route_id -> route_id` FK; constraint count remained `15`.
- Reapply exit: `3`; documented prefix and `foreign key mismatch` observed.
- Silent repair: absent; wrong FK and data remained unchanged after rollback.

## Wrong-Mode Negative Test

- Clone: `mes_work_order_route_release_negative_wrong_mode_2607151124`.
- Restore equality: `15/15`; correct initial shape: `14 / 15 / 5`.
- Mode allowlist was replaced with `route_generated / legacy_generated` under
  the same constraint name.
- Reapply exit: `3`; documented prefix and `check constraint mismatch` observed.
- Silent repair: absent; wrong check and data remained unchanged after rollback.

## Extra-Index Negative Test

- Clone: `mes_work_order_route_release_negative_extra_index_2607151124`.
- Restore equality: `15/15`; correct initial shape: `14 / 15 / 5`.
- Controlled index
  `ix_mes_work_order_route_releases_unexpected_smoke` raised the malformed index
  count to `6`.
- Reapply exit: `3`; documented prefix and `expected 5 indexes` observed.
- Silent repair/deletion: absent; six-index schema and data remained unchanged
  after rollback.

## Negative Rollback Integrity

- All five migration attempts exited non-zero for the intended assertion, not a
  setup, syntax, connection, or wrong-database error.
- All five pre/post malformed catalog snapshots were byte-equal.
- All five restored established-data snapshots remained equal to source.
- No case silently repaired or partially changed its malformed schema.

## Clone Cleanup

- Primary clone drop guard matched exactly once; primary clone was dropped.
- Each negative clone was dropped immediately after its case.
- Remaining `mes_work_order_route_release_schema_%` databases: `0`.
- Remaining `mes_work_order_route_release_negative_%` databases: `0`.
- Logical backup was retained.

## Source Final Integrity

- Final source counts equal baseline: `15/15`.
- Final source digests equal baseline: `15/15`.
- Release table: absent; parent snapshot constraint: absent; binding table:
  absent; Canonical V2 route count: `0`.
- Retained V1 remained
  `active / OPERATOR_OBSERVATION_APPROVAL / pending`, with counts `4 / 0 / 0`.
- Clone-only work-order ID count in source: `0`; the release relation itself
  remained absent, so the clone-only release ID was also absent.
- Unintended source mutation: `0`.

## Health

- `GET http://127.0.0.1:8080/health`: HTTP `200`, `status=ok`.
- No Docker rebuild, recreate, restart, down, or volume operation occurred.

## Guardrails

- Source `mes` remained unchanged; migration, V2 seed, and fixtures ran only on
  disposable clones.
- No release/read/write helper, API, feature flag, lifecycle/binding/queue/
  runtime execution, completion bridge, inference/backfill, FERP/MESQL,
  Kiosk/IoT/OEE, approval/production-flow/inventory implementation occurred.
- Evidence and post-smoke `CURRENT_STATE.md` changes remain uncommitted.
- No push, reset, rebase, amend, or `.agents/` access occurred.

## Result

`PASS`

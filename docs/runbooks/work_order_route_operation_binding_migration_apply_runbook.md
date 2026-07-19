# Work-Order Operation / Route-Operation Binding Migration Apply Runbook

## Purpose

Manually apply and verify the additive binding schema in:

```text
db/migrations/009_work_order_operation_route_binding.sql
```

This is a future controlled procedure. It was not executed while this runbook
was drafted. The migration must create one empty immutable binding sidecar and
must not modify existing lifecycle, runtime, config, queue, location, or audit
data.

## Preconditions

- Obtain explicit approval for the exact database apply.
- `mes_postgres` must be running and healthy.
- `mes_postgres_data` must not have been deleted or replaced.
- Migrations through `008_mesql_integration_v2.sql` must be understood.
- `mes.work_order_operations`, `mes.route_operations`, and
  `mes.work_order_operation_execution_state` must exist with the reviewed
  identity types.
- Git status and the exact migration content must be reviewed.
- A verified logical backup must be completed before apply.
- MESQL/FERP must remain frozen.
- Do not run work-order, queue, runtime, approval, production-flow, inventory,
  Kiosk, IoT, or OEE mutations as part of this procedure.

## Target Database Guard

Print the container-configured database and the connected database before any
backup or apply:

```powershell
docker exec mes_postgres sh -lc 'printf "container_database=%s\n" "$POSTGRES_DB"; PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -Atc "SELECT current_database();"'
```

Expected local source target:

```text
container_database=mes
mes
```

Stop if the two values differ or the approved target is not `mes`. Do not
replace the database name ad hoc.

## Repository Verification

```powershell
git status -sb
git log --oneline -8
Test-Path -LiteralPath "db\migrations\009_work_order_operation_route_binding.sql"
Get-FileHash -Algorithm SHA256 -LiteralPath "db\migrations\009_work_order_operation_route_binding.sql"
```

Record the Git commit and migration SHA-256 in the apply evidence. Confirm no
unreviewed migration with the same prefix or target table has appeared.

## Backup

Use the approved local backup launcher:

```powershell
$PortableRuntimeRootInput = '<approved-portable-runtime-root>'
if ([string]::IsNullOrWhiteSpace($PortableRuntimeRootInput) -or
    $PortableRuntimeRootInput -eq '<approved-portable-runtime-root>') {
  throw 'Set PortableRuntimeRootInput to the approved portable runtime root.'
}
$PortableRuntimeRoot =
  (Resolve-Path -LiteralPath $PortableRuntimeRootInput -ErrorAction Stop).Path
$BackupDir = Join-Path $PortableRuntimeRoot "data\db_backups"
if (-not (Test-Path -LiteralPath $BackupDir -PathType Container)) {
  throw "Approved backup directory is missing: $BackupDir"
}
$env:MES_PORTABLE_RUNTIME_ROOT = $PortableRuntimeRoot
$BackupStartedAt = Get-Date
& "docker\mes\launchers\maintenance\backup_mes_db.cmd"
$BackupCandidates = @(
  Get-ChildItem -LiteralPath $BackupDir -File -Filter "*.sql" |
    Where-Object { $_.LastWriteTime -ge $BackupStartedAt.AddSeconds(-2) } |
    Sort-Object LastWriteTime -Descending
)
if ($BackupCandidates.Count -ne 1) {
  throw "Expected exactly one new PostgreSQL backup file."
}
$BackupFile = $BackupCandidates[0]
$BackupFile | Select-Object FullName, Length, LastWriteTime
Get-Content -LiteralPath $BackupFile.FullName -TotalCount 5
```

Require a nonzero byte size and a PostgreSQL dump header. Record the full host
path and size. Stop if backup creation or verification is ambiguous. Never
print the database password.

## Source Baseline

Capture count and deterministic digest output for all 15 existing tables:

```powershell
$BaselineTables = @(
  "items",
  "process_routes",
  "route_operations",
  "operation_steps",
  "station_event_sources",
  "work_order_operation_execution_state",
  "work_order_operation_steps",
  "operation_events",
  "operation_approvals",
  "production_flow_events",
  "work_orders",
  "work_order_operations",
  "station_queue",
  "locations",
  "station_location_bindings"
)

foreach ($Table in $BaselineTables) {
  @"
SELECT
  '$Table' AS table_name,
  count(*) AS row_count,
  md5(
    COALESCE(
      string_agg(to_jsonb(t)::text, '|' ORDER BY to_jsonb(t)::text),
      ''
    )
  ) AS row_digest
FROM mes.$Table AS t;
"@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -At'
}
```

Record every output line. The same command and table order must be used after
first apply and after reapply.

Before apply, prove the target table is absent:

```powershell
@'
SELECT to_regclass('mes.work_order_operation_route_bindings') AS binding_table;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Expected: `binding_table` is null. If the table already exists, stop and run a
separate exact-shape review before deciding whether reapply is intended.

## Static SQL Review

```powershell
$MigrationPath = "db\migrations\009_work_order_operation_route_binding.sql"
$Sql = Get-Content -Raw -LiteralPath $MigrationPath

($Sql | Select-String -AllMatches -Pattern "CREATE TABLE IF NOT EXISTS mes\.work_order_operation_route_bindings").Matches.Count
($Sql | Select-String -AllMatches -Pattern "REFERENCES mes\.work_order_operations").Matches.Count
($Sql | Select-String -AllMatches -Pattern "REFERENCES mes\.route_operations").Matches.Count
($Sql | Select-String -AllMatches -Pattern "UNIQUE \(work_order_operation_id\)").Matches.Count
($Sql | Select-String -AllMatches -Pattern "CREATE INDEX IF NOT EXISTS ix_mes_work_order_operation_route_bindings_route_operation").Matches.Count

Select-String -LiteralPath $MigrationPath -CaseSensitive -Pattern "\b(INSERT|UPDATE|DELETE|TRUNCATE)\b|DROP TABLE|ALTER TABLE mes\.(work_orders|work_order_operations|route_operations)"
```

Expected counts are `1, 1, 1, 1, 1`. The forbidden DML/DDL scan must return no
matches. Also review the table definition and confirm it contains no lifecycle
fields such as active/update/delete/effective/supersession state. Those names
may appear only in the exact-shape assertion's forbidden-column absence list.

Confirm the SQL is wrapped in `BEGIN`/`COMMIT`, creates no seed row, contains no
backfill source, trigger, function, or stored procedure, and changes no
existing table.

## Apply Command

Run only after target and backup checks pass and explicit approval remains
valid:

```powershell
Get-Content -Raw -LiteralPath "db\migrations\009_work_order_operation_route_binding.sql" |
  docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Any SQL or assertion error is a FAIL. `ON_ERROR_STOP=1` plus the migration
transaction must leave no partial schema.

## Table Verification

```powershell
@'
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'mes'
  AND table_name = 'work_order_operation_route_bindings';
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Expected: exactly one `mes.work_order_operation_route_bindings` table.

## Column Verification

```powershell
@'
SELECT
  ordinal_position,
  column_name,
  data_type,
  udt_name,
  is_nullable,
  column_default
FROM information_schema.columns
WHERE table_schema = 'mes'
  AND table_name = 'work_order_operation_route_bindings'
ORDER BY ordinal_position;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Require exactly nine columns matching the schema plan. Confirm none of
`active`, `updated_at`, `deleted_at`, `effective_from`, `effective_to`, or
`superseded_by` exists.

## Constraint Verification

```powershell
@'
SELECT
  conname,
  contype,
  confdeltype,
  confupdtype,
  pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'mes.work_order_operation_route_bindings'::regclass
ORDER BY conname;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Verify the primary key, stable-ID uniqueness,
`UNIQUE(work_order_operation_id)`, both foreign keys, controlled source,
nonblank identity/actor checks, and object-only metadata check. Both foreign
keys must show `confdeltype=a` and `confupdtype=a` (`NO ACTION`). There must be
exactly nine constraints and no `UNIQUE(route_operation_id)` constraint.

## Index Verification

```powershell
@'
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'mes'
  AND tablename = 'work_order_operation_route_bindings'
ORDER BY indexname;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Require the PK/unique backing indexes and one non-unique
`ix_mes_work_order_operation_route_bindings_route_operation` lookup index. The
unique lifecycle-operation constraint already supplies its index; a duplicate
standalone lifecycle index must not exist. Require exactly four indexes in
total, including the three constraint-backed indexes.

## Empty-Table Verification

```powershell
@'
SELECT count(*) AS binding_row_count
FROM mes.work_order_operation_route_bindings;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Expected: `binding_row_count = 0`.

## Idempotency Reapply

1. Record the complete column, constraint, index, and empty-table output.
2. Re-run the exact Apply Command without editing the SQL.
3. Require a successful commit and no assertion failure.
4. Re-run all table/column/constraint/index checks.
5. Require `binding_row_count = 0` again.
6. Confirm schema output is identical to the first apply.

An existing same-name object with the wrong shape must fail; it must not be
silently accepted or repaired.

## Existing-Table No-Write Verification

After first apply and again after reapply, run the exact Source Baseline loop.
All 15 table counts and digests must equal the pre-apply values. No work-order,
operation, queue, runtime, event, approval, production-flow, config, location,
or station-location binding row may change.

## Health

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

Require `status = ok`. Do not rebuild, recreate, stop, or restart containers
for this schema verification.

## Rollback Strategy

Do not run automatic destructive rollback SQL. Preferred recovery is restore
from the verified pre-apply backup.

If the new table is confirmed empty, dropping it may be evaluated only under a
separate explicit destructive approval and reviewed recovery plan. This
runbook does not provide an executable drop command. If any binding row exists,
do not drop the table or delete rows; first analyze affected work-order and
runtime dependencies.

## PASS Criteria

- Exact local target and backup are verified.
- Static SQL review passes.
- First apply and idempotency reapply both commit successfully.
- One exact-shape binding table exists.
- Expected columns, defaults, constraints, foreign keys, and indexes match.
- Binding row count remains zero.
- All 15 existing table counts and digests are unchanged after both applies.
- Health returns `ok`.
- No seed, backfill, binding row, lifecycle/runtime/config mutation, MESQL,
  volume, or container lifecycle operation occurs.

## FAIL Criteria

- Target database or backup cannot be verified.
- Static review finds forbidden DML/DDL or unreviewed schema behavior.
- Apply/reapply or exact-shape assertion fails.
- A wrong column, default, constraint, FK action, or index exists.
- Binding row count is not zero.
- Any existing table count or digest changes.
- Health is not `ok`.
- Any unapproved binding, backfill, lifecycle, runtime, config, queue, volume,
  MESQL, or container mutation occurs.

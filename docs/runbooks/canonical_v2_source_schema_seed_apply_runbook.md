# Canonical V2 Source Schema/Seed Apply Runbook

## Status

`READY_FOR_CONTROLLED_SOURCE_SCHEMA_SEED_APPLY`

Last updated: `2026-07-15`.

This is the Phase 5H-B procedure for a future separately approved source apply.
It was not executed while this runbook was prepared.

## Safety Boundary

- Exact target: container `mes_postgres`, database/user `mes / mes`, host port
  `5433`.
- Apply only migration `009`, migration `010`, and seed `006`, in that order.
- Do not create a work order or call release, runtime, step, bridge, API, Kiosk,
  FERP/MESQL, analytics, export, inventory, or production helpers.
- Do not rebuild, recreate, restart, stop, or remove Docker services/volumes.
- Do not expose credentials in output or evidence.
- Use a controlled maintenance window with all application/user mutation paths
  quiescent. Do not infer quiescence from container health.
- Stop on the first mismatch or error. Do not repair or adopt partial state.

## Approval and Repository Identity

Obtain explicit approval for Phase 5H-B against exact source `mes`. Then run:

```powershell
git status -sb
git status --short
git rev-parse HEAD
git diff --check
git diff --cached --name-only

$Sql009 = (Resolve-Path `
  'db\migrations\009_work_order_operation_route_binding.sql').Path
$Sql010 = (Resolve-Path `
  'db\migrations\010_work_order_route_release.sql').Path
$Sql006 = (Resolve-Path `
  'db\migrations\006_station_execution_seed_canonical_v2.sql').Path

$Expected009 = 'B5DA1799A52147433E1DEA44BD989394D720416D352CC7906F8A1729BE1A0162'
$Expected010 = '5B7C6CF7261095A6B00C7EF9170ED7F262F648053BDC0B1E3EA4A4B4C7B551F6'
$Expected006 = '9B4174BD5756B92DD5D9111BC7E5249020471865F6546B2C47D77F94B79434C8'

$Actual009 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Sql009).Hash
$Actual010 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Sql010).Hash
$Actual006 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Sql006).Hash

if ($Actual009 -ne $Expected009 -or
    $Actual010 -ne $Expected010 -or
    $Actual006 -ne $Expected006) {
  throw 'Reviewed SQL checksum mismatch; Phase 5H-B is BLOCKED.'
}
```

Record HEAD and all three hashes. Stop on any unrelated tracked/untracked or
staged change that makes the reviewed SQL scope ambiguous.

## Exact Source Identity

```powershell
docker inspect mes_postgres `
  --format '{{.Name}} {{.State.Status}} {{.State.Health.Status}}'

docker port mes_postgres 5432

docker exec mes_postgres sh -lc `
  'printf "configured_database=%s\nconfigured_user=%s\n" "$POSTGRES_DB" "$POSTGRES_USER"; PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT current_database(), current_user, current_setting(''server_version'');"'
```

Require Docker's exact reported container name `/mes_postgres` (normalized name
`mes_postgres`), running/healthy state, host port mapping `5433`, configured
database/user `mes / mes`, and query result `mes|mes|<version>`. Stop if any
identity differs.

## Read-Only Preflight Snapshot

Run all source discovery inside one transaction:

```powershell
@'
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT current_database(), current_user, current_setting('server_version');

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'mes'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

SELECT
  to_regclass('mes.work_order_operation_route_bindings') AS binding_table,
  to_regclass('mes.work_order_route_releases') AS release_table;

SELECT conname, contype, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'mes.process_routes'::regclass
  AND conname = 'uq_mes_process_routes_identity_snapshot';

SELECT route_id, route_code, version
FROM mes.process_routes
WHERE route_id = 'ROUTE_BOX_PACKAGING_V2'
   OR route_code = 'ROUTE_BOX_PACKAGING_V2'
   OR version = 2
ORDER BY route_id, route_code, version;

SELECT route_operation_id, route_code, route_version, sequence_no
FROM mes.route_operations
WHERE route_operation_id IN (
        'ROUTE_BOX_PACKAGING_V2_OP10',
        'ROUTE_BOX_PACKAGING_V2_OP20'
      )
   OR route_code = 'ROUTE_BOX_PACKAGING_V2'
   OR route_version = 2
ORDER BY route_operation_id;

SELECT operation_step_id, route_operation_id, step_no, step_code
FROM mes.operation_steps
WHERE route_operation_id IN (
  'ROUTE_BOX_PACKAGING_V2_OP10',
  'ROUTE_BOX_PACKAGING_V2_OP20'
)
ORDER BY route_operation_id, step_no, operation_step_id;

SELECT
  (SELECT count(*) FROM mes.process_routes
   WHERE route_code = 'ROUTE_BOX_PACKAGING_V1' AND version = 1)
    AS v1_routes,
  (SELECT count(*) FROM mes.route_operations
   WHERE route_code = 'ROUTE_BOX_PACKAGING_V1' AND route_version = 1)
    AS v1_operations,
  (SELECT count(*)
   FROM mes.operation_steps step
   JOIN mes.route_operations operation
     ON operation.route_operation_id = step.route_operation_id
   WHERE operation.route_code = 'ROUTE_BOX_PACKAGING_V1'
     AND operation.route_version = 1)
    AS v1_steps,
  (SELECT count(*) FROM mes.operation_events) AS operation_events,
  (SELECT count(*) FROM mes.operation_approvals) AS approvals,
  (SELECT count(*) FROM mes.production_flow_events) AS flow_events;

COMMIT;
'@ | docker exec -i mes_postgres sh -lc `
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Required first-rollout result:

- binding table absent;
- release table absent;
- parent identity constraint absent;
- no V2 route/operation/step row or identifier collision;
- retained V1 `1 / 2 / 5`;
- audit `4 / 0 / 0`;
- no unexplained difference from the last accepted source evidence.

If either sidecar or the parent constraint exists—even with an apparently exact
shape—this is not the expected first-rollout state. Stop and perform a separate
partial-state review. Never continue by treating it as an implicit reapply.

## Baseline Sets and Digests

Capture the authoritative base-table set. This query deliberately excludes
sequences, views, indexes and every non-base relation:

```powershell
$BaseTableSql = @'
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'mes'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
'@

$BaselineBaseTables = @(
  $BaseTableSql |
    docker exec -i mes_postgres sh -lc `
      'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
) | Where-Object { $_ -ne '' }

if ($BaselineBaseTables.Count -ne 38) {
  throw 'Base-table helper count differs from accepted baseline; review required.'
}
```

The count `38` is only a blocker/diagnostic for this accepted baseline. Store
and compare `$BaselineBaseTables` as the authoritative invariant.

Capture deterministic count/digest output for every baseline base table. Also
retain the established 15-table view in this order:

```text
items
process_routes
route_operations
operation_steps
station_event_sources
work_order_operation_execution_state
work_order_operation_steps
operation_events
operation_approvals
production_flow_events
work_orders
work_order_operations
station_queue
locations
station_location_bindings
```

For each table use the same query before and after:

```sql
SELECT
  count(*) AS row_count,
  md5(
    COALESCE(
      string_agg(to_jsonb(t)::text, '|' ORDER BY to_jsonb(t)::text),
      ''
    )
  ) AS row_digest
FROM mes.<reviewed_table_name> AS t;
```

The table name must come only from `$BaselineBaseTables`, not caller input.
Record V1-scoped digests, station-event sources, locations, station bindings,
runtime/lifecycle/queue rows, and the full inventory/fingerprint used by the
latest source evidence.

## Backup

The existing launcher is not used because its filename is not the rollout
contract. Create the exact retained plain dump:

```powershell
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir = 'C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups'
$BackupFile = Join-Path $BackupDir `
  "mes_before_canonical_v2_source_rollout_$RunStamp.sql"
$ContainerBackup = `
  "/tmp/mes_before_canonical_v2_source_rollout_${RunStamp}.sql"

if (-not (Test-Path -LiteralPath $BackupDir -PathType Container)) {
  throw 'Approved backup directory is missing.'
}
if (Test-Path -LiteralPath $BackupFile) {
  throw 'Refusing to overwrite an existing rollout backup.'
}

docker exec mes_postgres pg_dump --version
if ($LASTEXITCODE -ne 0) {
  throw 'pg_dump version check failed.'
}

$ContainerBackupCommand = @'
set -eu
umask 077
test ! -e "{0}"
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  -Fp \
  --no-owner \
  --no-privileges \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -f "{0}"
test -s "{0}"
head -n 5 "{0}" | grep -F 'PostgreSQL database dump' >/dev/null
stat -c 'container_bytes=%s' "{0}"
sha256sum "{0}"
'@ -f $ContainerBackup

$ContainerBackupResult = @(
  docker exec mes_postgres sh -lc $ContainerBackupCommand
)
if ($LASTEXITCODE -ne 0) {
  throw 'Container-side pg_dump or validation failed; Phase 5H-B is BLOCKED.'
}

$ContainerBackupResult
$ContainerBackupHashLine = @(
  $ContainerBackupResult |
    Where-Object { $_ -match '^[0-9a-fA-F]{64}\s+' }
)
if ($ContainerBackupHashLine.Count -ne 1) {
  throw 'Expected exactly one container SHA-256 result.'
}
$ContainerBackupHash = `
  ($ContainerBackupHashLine[0] -split '\s+')[0].ToUpperInvariant()

docker cp "mes_postgres:$ContainerBackup" $BackupFile
if ($LASTEXITCODE -ne 0) {
  throw 'docker cp failed; Phase 5H-B is BLOCKED.'
}

$BackupInfo = Get-Item -LiteralPath $BackupFile
$BackupHeader = Get-Content -LiteralPath $BackupFile -TotalCount 5
$HostBackupHash = `
  (Get-FileHash -Algorithm SHA256 -LiteralPath $BackupFile).Hash
$BackupInfo | Select-Object FullName, Length, LastWriteTime
$BackupHeader
$HostBackupHash

if ($BackupInfo.Length -le 0 -or
    -not ($BackupHeader -match 'PostgreSQL database dump')) {
  throw 'Host backup size/header validation failed; Phase 5H-B is BLOCKED.'
}
if ($HostBackupHash -ne $ContainerBackupHash) {
  throw 'Container/host backup SHA-256 mismatch; Phase 5H-B is BLOCKED.'
}

$RemoveContainerBackupCommand = `
  'rm -f -- "{0}"; test ! -e "{0}"' -f $ContainerBackup
docker exec mes_postgres sh -lc $RemoveContainerBackupCommand
if ($LASTEXITCODE -ne 0) {
  throw 'Verified container backup cleanup failed.'
}
```

Record the container path/size/hash and host path/size/hash. Container backup
removal is permitted only after `docker cp`, host size/header validation, and
container/host SHA-256 equality all pass. On any earlier failure, leave the
container file for explicit inspection, report Phase 5H-B `BLOCKED`, and do not
start migration apply. Retain the byte-identical host file. Do not print the
dump contents, expose credentials, or include/execute a restore command.

## Stage Reviewed SQL in the Container

Copy exact reviewed files to unique container temp names and verify their
container-side hashes:

```powershell
$Container009 = "/tmp/canonical_v2_source_rollout_${RunStamp}_009.sql"
$Container010 = "/tmp/canonical_v2_source_rollout_${RunStamp}_010.sql"
$Container006 = "/tmp/canonical_v2_source_rollout_${RunStamp}_006.sql"

docker cp $Sql009 "mes_postgres:$Container009"
if ($LASTEXITCODE -ne 0) { throw '009 container copy failed.' }
docker cp $Sql010 "mes_postgres:$Container010"
if ($LASTEXITCODE -ne 0) { throw '010 container copy failed.' }
docker cp $Sql006 "mes_postgres:$Container006"
if ($LASTEXITCODE -ne 0) { throw '006 container copy failed.' }

docker exec mes_postgres sha256sum `
  $Container009 $Container010 $Container006
```

Require exact equality with the three reviewed host hashes. Stop before apply
on any copy or hash mismatch.

## Static SQL Review

Before source access, confirm from the exact host files:

- each file contains its own `BEGIN` and `COMMIT`;
- no file is wrapped in another transaction by this runbook;
- `009` creates only the immutable binding sidecar and one lookup index, with
  no row DML, backfill or existing-table alteration;
- `010` may add only the exact parent route identity constraint and release
  sidecar/indexes, with no release/lifecycle/binding/queue row;
- `006` inserts only exact V2 rows into `process_routes`, `route_operations` and
  `operation_steps` through insert-if-absent behavior and never updates an
  existing row;
- none contains `DROP`, `TRUNCATE`, `DELETE`, legacy backfill, work-order,
  queue, runtime/event or inventory mutation;
- all final assertion blocks and malformed-state rejection remain present.

Record `git diff --check`, the hashes, and any static scan output in evidence.

## Apply Migration 009

Recheck exact database/user immediately before apply. Then execute only:

```powershell
$Apply009 = 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "{0}"' -f $Container009
docker exec mes_postgres sh -lc $Apply009
if ($LASTEXITCODE -ne 0) { throw 'Migration 009 failed; stop rollout.' }
```

Do not prepend/append `BEGIN`, `COMMIT`, or another SQL artifact. Migration
`009` owns its transaction.

## Verify Migration 009

Run read-only catalog queries for ordered columns/defaults, all constraints and
`pg_get_constraintdef`, and all indexes/`pg_get_indexdef`. Require:

- one `mes.work_order_operation_route_bindings` base table;
- `9` exact columns, `9` exact constraints, `4` exact indexes;
- one binding-ID unique, one lifecycle-UUID unique, both `NO ACTION` FKs;
- allowed sources `manual_setup` and `work_order_release`;
- no active/update/delete/effective/supersession model;
- row count `0` and no backfill;
- every baseline table count/digest unchanged.

Set invariant:

```powershell
$ExpectedAfter009 = @(
  $BaselineBaseTables
  'work_order_operation_route_bindings'
) | Sort-Object -Unique

$After009BaseTables = @(
  $BaseTableSql |
    docker exec -i mes_postgres sh -lc `
      'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
) | Where-Object { $_ -ne '' }

if (Compare-Object $ExpectedAfter009 $After009BaseTables) {
  throw 'Base-table set mismatch after 009.'
}
```

A helper count of `39` is expected but is not a substitute for set equality.

## Reapply Migration 009

Capture table OID, sequence, complete catalog shape, row count, base-table set,
and baseline digests. Execute the exact same `$Apply009` command in a new
`psql -f` process. Require success and byte/semantic equality of every captured
value. Row count remains `0`.

## Apply Migration 010

Only after 009 first apply/reapply PASS:

```powershell
$Apply010 = 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "{0}"' -f $Container010
docker exec mes_postgres sh -lc $Apply010
if ($LASTEXITCODE -ne 0) { throw 'Migration 010 failed; stop rollout.' }
```

Migration `010` owns its transaction. Do not add an outer transaction.

## Verify Migration 010

Require:

- one `mes.work_order_route_releases` base table;
- `14` exact columns, `15` exact constraints, `5` exact indexes;
- exact release-ID and order-ID uniqueness;
- exact `(process_route_id, route_code, route_version)` child FK to
  `(route_id, route_code, version)`;
- exact parent `uq_mes_process_routes_identity_snapshot` on
  `(route_id, route_code, version)`;
- exact mode/source/digest/object checks;
- release rows `0`, binding rows `0`;
- binding catalog/data unchanged;
- all original baseline table row digests unchanged.

Authoritative set invariant:

```powershell
$ExpectedAfter010 = @(
  $BaselineBaseTables
  'work_order_operation_route_bindings'
  'work_order_route_releases'
) | Sort-Object -Unique

$After010BaseTables = @(
  $BaseTableSql |
    docker exec -i mes_postgres sh -lc `
      'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
) | Where-Object { $_ -ne '' }

if (Compare-Object $ExpectedAfter010 $After010BaseTables) {
  throw 'Base-table set mismatch after 010.'
}
```

A helper count of `40` is expected only because the accepted baseline was `38`.

## Reapply Migration 010

Capture the release table/sequence OIDs, complete shape, parent constraint OID
and definition, sidecar rows/digests, base-table set and baseline digests.
Execute exact `$Apply010` in a new `psql -f` process. Require success and zero
catalog/data delta.

## Apply Seed 006

Only after both schema checkpoints PASS:

```powershell
$Apply006 = 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "{0}"' -f $Container006
docker exec mes_postgres sh -lc $Apply006
if ($LASTEXITCODE -ne 0) { throw 'Seed 006 failed; stop rollout.' }
```

Seed `006` owns its transaction. Do not add an outer transaction.

## Verify Seed 006

Require exact additive configuration:

```text
ROUTE_BOX_PACKAGING_V2 / version 2 / PACKAGED_PRODUCT / active
ROUTE_BOX_PACKAGING_V2_OP10 / sequence 10 / ASSEMBLY_01
ROUTE_BOX_PACKAGING_V2_OP20 / sequence 20 / PACKAGING_01
route / operations / steps = 1 / 2 / 4
OP10 / OP20 steps = 3 / 1
policies = auto_close_on_required_steps / auto_close_on_required_steps
configured and resolved location roles = 5 / 5
```

Verify exact step identities/event sources, one process-end observation, no
embedded approval/QC operation, and all seed metadata. Require V1 `1 / 2 / 5`
counts/digests unchanged, binding/release rows `0`, and no lifecycle, queue,
runtime, event, approval, flow or inventory delta.

The base-table set remains exactly `$ExpectedAfter010`; no third table is
created. Only exact V2 additions in `process_routes`, `route_operations` and
`operation_steps` may differ from the pre-rollout data. All other baseline base
tables remain count/digest-identical.

## Reapply Seed 006

Capture exact V1/V2 rows/digests, sidecar rows, unchanged-table digests and the
base-table set. Execute exact `$Apply006` in a new `psql -f` process. Require a
successful assertion block and zero catalog/data delta.

## Final Baseline Comparison

In a new read-only repeatable-read transaction require:

- final base-table set = baseline set + the two exact sidecars;
- helper base-table count `40` only as a secondary diagnostic;
- binding/release shapes exact and row counts `0 / 0`;
- only exact V2 rows added to the three configuration tables;
- all other original base tables unchanged;
- retained V1 unchanged;
- audit remains `4 / 0 / 0`;
- existing work orders, lifecycle operations, queues, runtime state, locations
  and bindings unchanged;
- no `PHASE5HC-SOURCE-SMOKE-%` row;
- no release/runtime/bridge or API action occurred.

## Health

```powershell
docker inspect mes_postgres `
  --format '{{.State.Status}} {{.State.Health.Status}}'

$Health = Invoke-WebRequest `
  -UseBasicParsing 'http://127.0.0.1:8080/health'
$Health.StatusCode
$Health.Content
```

Require running/healthy and HTTP `200` with `status=ok`. Do not perform a Docker
lifecycle action to obtain health.

## Failure Stop Rules

On any failure:

1. record the exact command, SQL exit status, PostgreSQL error/assertion and
   last verified checkpoint;
2. rely only on the failing artifact's internal transaction rollback;
3. do not execute later artifacts, reapply, Phase 5H-C or helper calls;
4. do not drop a previously successful sidecar/constraint or delete V2 rows;
5. inspect exact state read-only and classify `FAIL` or `BLOCKED`;
6. obtain separate approval before any idempotent retry;
7. treat backup restore as a separate destructive recovery task.

Any backup creation, container validation, `docker cp`, host validation, or
SHA-256 equality failure is `BLOCKED` before migration `009` and leaves apply
unstarted.

Unknown or ambiguous state is `BLOCKED`, never automatically repaired.

## Cleanup

The exact container backup was already removed only after its verified host
copy passed byte-equality checks. After all apply evidence is captured, remove
only the three exact timestamped container SQL copies:

```powershell
docker exec mes_postgres rm -f -- `
  $Container009 $Container010 $Container006
```

Confirm those exact temp files are absent. Retain the host backup. There are no
clone databases or source fixtures to clean in Phase 5H-B. Do not delete any
source schema/config/data object.

## Final Report

Record:

```text
Result: PASS / FAIL / BLOCKED
Approval and maintenance window:
Repository HEAD and SQL hashes:
Container/database/user/version/port:
Backup path/size/header:
Container backup path/size/SHA-256:
Host backup path/size/SHA-256 and equality:
Verified container backup cleanup:
Baseline base-table set and helper count:
Established 15-table counts/digests:
Preflight absent objects and V2 collision result:
009 first apply/reapply and 9/9/4, rows 0:
010 first apply/reapply and 14/15/5, rows 0:
Parent identity constraint:
006 first apply/reapply and 1/2/4, 3/1, 5/5:
Final base-table set equation and helper count:
V1 and audit preservation:
Unchanged-table comparisons:
Health:
Container temp cleanup:
Backup retained:
No functional smoke/API/FERP/MESQL/inventory:
Phase 5H-C started: no
```

PASS requires every checkpoint. A failed executed invariant is `FAIL`; missing
approval, identity, backup, preflight certainty or recovery decision is
`BLOCKED`.

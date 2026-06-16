param (
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$DOCKER_DIR = "C:\Users\ertun\Documents\.CODE\.DOCKER\MES"
$BACKUP_DIR = "$DOCKER_DIR\deploy_backups\backfill_faz1_5_$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$COMPOSE_FILE = "$DOCKER_DIR\compose.yaml"

Write-Host "Creating backup directory: $BACKUP_DIR" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $BACKUP_DIR | Out-Null

Write-Host "Backing up .env and oee_runtime_state.json..." -ForegroundColor Cyan
if (Test-Path "$DOCKER_DIR\.env") {
    Copy-Item "$DOCKER_DIR\.env" "$BACKUP_DIR\.env.bak"
}
if (Test-Path "$DOCKER_DIR\data\logs\oee_runtime_state.json") {
    Copy-Item "$DOCKER_DIR\data\logs\oee_runtime_state.json" "$BACKUP_DIR\oee_runtime_state.json.bak"
}

Write-Host "Backing up PostgreSQL database..." -ForegroundColor Cyan
docker compose -f $COMPOSE_FILE exec -T mes_postgres pg_dump -U mes -d mes -F c -f "/tmp/mes_backup_faz1_5.dump"
docker cp mes_postgres:/tmp/mes_backup_faz1_5.dump "$BACKUP_DIR\mes_postgres.dump"

$QUERY_BEFORE = @"
SELECT order_id, product_code, status, 
       payload->>'stationCode' as payload_station,
       metadata->>'station_code' as meta_station,
       metadata->>'station_assignment_source' as meta_source
FROM mes.work_orders;
"@

Write-Host "`n--- BEFORE BACKFILL ---" -ForegroundColor Yellow
docker compose -f $COMPOSE_FILE exec -T mes_postgres psql -U mes -d mes -c $QUERY_BEFORE

$DRY_RUN_SELECT = @"
SELECT order_id, product_code,
    CASE 
        WHEN order_id ILIKE '%PKT%' OR product_code ILIKE '%PKT%' OR product_code ILIKE '%PACK%' OR order_id ILIKE '%PACK%' THEN 'PACKAGING_01'
        ELSE 'ASSEMBLY_01'
    END as target_station
FROM mes.work_orders
WHERE metadata->>'station_assignment_source' IS NULL OR metadata->>'station_assignment_source' != 'manual_backfill_faz_1_5';
"@

if ($DryRun) {
    Write-Host "`n--- DRY RUN TARGETS ---" -ForegroundColor Yellow
    docker compose -f $COMPOSE_FILE exec -T mes_postgres psql -U mes -d mes -c $DRY_RUN_SELECT
    Write-Host "`nDryRun completed. No changes made." -ForegroundColor Green
    exit 0
}

Write-Host "`nExecuting BACKFILL UPDATE..." -ForegroundColor Cyan
$UPDATE_SQL = @"
UPDATE mes.work_orders
SET payload = CASE 
        WHEN order_id ILIKE '%PKT%' OR product_code ILIKE '%PKT%' OR product_code ILIKE '%PACK%' OR order_id ILIKE '%PACK%' THEN
            jsonb_set(
                jsonb_set(
                    jsonb_set(payload::jsonb, '{stationCode}', to_jsonb('PACKAGING_01'::text)),
                    '{operationCode}', to_jsonb('PACKAGING'::text)
                ),
                '{productType}', to_jsonb('package'::text)
            )
        ELSE
            jsonb_set(
                jsonb_set(
                    jsonb_set(payload::jsonb, '{stationCode}', to_jsonb('ASSEMBLY_01'::text)),
                    '{operationCode}', to_jsonb('BOX_PRODUCTION'::text)
                ),
                '{productType}', to_jsonb('box'::text)
            )
    END,
    metadata = CASE 
        WHEN order_id ILIKE '%PKT%' OR product_code ILIKE '%PKT%' OR product_code ILIKE '%PACK%' OR order_id ILIKE '%PACK%' THEN
            jsonb_set(
                jsonb_set(metadata::jsonb, '{station_assignment_source}', to_jsonb('manual_backfill_faz_1_5'::text)),
                '{station_code}', to_jsonb('PACKAGING_01'::text)
            )
        ELSE
            jsonb_set(
                jsonb_set(metadata::jsonb, '{station_assignment_source}', to_jsonb('manual_backfill_faz_1_5'::text)),
                '{station_code}', to_jsonb('ASSEMBLY_01'::text)
            )
    END
WHERE metadata->>'station_assignment_source' IS NULL OR metadata->>'station_assignment_source' != 'manual_backfill_faz_1_5';
"@

docker compose -f $COMPOSE_FILE exec -T mes_postgres psql -U mes -d mes -c $UPDATE_SQL

Write-Host "`n--- AFTER BACKFILL ---" -ForegroundColor Yellow
docker compose -f $COMPOSE_FILE exec -T mes_postgres psql -U mes -d mes -c $QUERY_BEFORE

Write-Host "`nBackfill completed successfully." -ForegroundColor Green

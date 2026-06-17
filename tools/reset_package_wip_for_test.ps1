param(
    [switch]$Apply,
    [string]$Container = "mes_postgres",
    [string]$Database = "mes",
    [string]$User = "mes"
)

$ErrorActionPreference = "Stop"

$whereClause = @"
status = 'available'
AND (source_work_order_id IS NULL OR btrim(source_work_order_id) = '')
"@

Write-Host "MESQL package WIP test cleanup"
$mode = if ($Apply) { "APPLY" } else { "DRY-RUN" }
Write-Host "Mode: $mode"
Write-Host "Target: available WIP rows with empty source_work_order_id"

$countSql = @"
SELECT COUNT(*) AS target_count
FROM mes.package_component_wip
WHERE $whereClause;
"@

$previewSql = @"
SELECT wip_item_pk, component_stock_code, source_item_id, source_work_order_id, status, quality_status
FROM mes.package_component_wip
WHERE $whereClause
ORDER BY wip_item_pk
LIMIT 50;
"@

docker exec $Container psql -U $User -d $Database -v ON_ERROR_STOP=1 -c $countSql
docker exec $Container psql -U $User -d $Database -v ON_ERROR_STOP=1 -c $previewSql

if (-not $Apply) {
    Write-Host "Dry-run only. Re-run with -Apply to mark these rows as scrapped."
    exit 0
}

$applySql = @"
UPDATE mes.package_component_wip
SET status = 'scrapped',
    metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
        'test_cleanup', true,
        'cleanup_reason', 'legacy_available_wip_without_source_work_order_id',
        'cleanup_at', now()
    ),
    updated_at = now()
WHERE $whereClause
RETURNING wip_item_pk, component_stock_code, source_item_id, source_work_order_id, status;
"@

docker exec $Container psql -U $User -d $Database -v ON_ERROR_STOP=1 -c $applySql
Write-Host "Cleanup applied. No rows were deleted or truncated."

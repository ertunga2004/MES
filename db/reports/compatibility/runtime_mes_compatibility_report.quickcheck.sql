WITH report_rows AS (
    SELECT
        'baseline_counts' AS check_group,
        'mes.work_orders count' AS check_name,
        'INFO' AS severity,
        count(*)::bigint AS finding_count,
        null::text AS sample_value,
        'Baseline row count for comparison.' AS recommendation
    FROM mes.work_orders
    UNION ALL
    SELECT 'baseline_counts', 'mes.work_order_events count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.work_order_events
    UNION ALL
    SELECT 'baseline_counts', 'mes.production_completions count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.production_completions
    UNION ALL
    SELECT 'baseline_counts', 'mes.vision_events count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.vision_events
    UNION ALL
    SELECT 'baseline_counts', 'mes.item_station_events count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.item_station_events
    UNION ALL
    SELECT 'baseline_counts', 'mes.station_queue count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.station_queue
    UNION ALL
    SELECT 'baseline_counts', 'mes.package_bom_lines count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.package_bom_lines
    UNION ALL
    SELECT 'baseline_counts', 'mes.package_component_wip count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.package_component_wip
    UNION ALL
    SELECT 'baseline_counts', 'mes.package_traceability count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.package_traceability
    UNION ALL
    SELECT 'baseline_counts', 'mes.package_sessions count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.package_sessions
    UNION ALL
    SELECT 'baseline_counts', 'mes.quality_overrides count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.quality_overrides
    UNION ALL
    SELECT 'baseline_counts', 'mes.ferp_import_batches count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.ferp_import_batches
    UNION ALL
    SELECT 'baseline_counts', 'mes.ferp_export_outbox count', 'INFO', count(*)::bigint, null::text, 'Baseline row count for comparison.' FROM mes.ferp_export_outbox
    UNION ALL
    SELECT
        'null_blank_keys',
        'mes.work_orders.order_id null or blank',
        'FAIL',
        count(*)::bigint,
        min(work_order_pk::text),
        'Every work order must have order_id before read or migration gates.'
    FROM mes.work_orders
    WHERE order_id IS NULL OR btrim(order_id) = ''
    UNION ALL
    SELECT 'null_blank_keys', 'mes.production_completions.external_ref null or blank', 'FAIL', count(*)::bigint, min(completion_pk::text), 'Every production completion needs external_ref for idempotency.' FROM mes.production_completions WHERE external_ref IS NULL OR btrim(external_ref) = ''
    UNION ALL
    SELECT 'null_blank_keys', 'mes.vision_events.external_ref null or blank', 'FAIL', count(*)::bigint, min(vision_event_pk::text), 'Every vision event needs external_ref for idempotency.' FROM mes.vision_events WHERE external_ref IS NULL OR btrim(external_ref) = ''
    UNION ALL
    SELECT 'null_blank_keys', 'mes.work_order_events.external_ref null or blank', 'FAIL', count(*)::bigint, min(event_pk::text), 'Every work order event needs external_ref for idempotency.' FROM mes.work_order_events WHERE external_ref IS NULL OR btrim(external_ref) = ''
    UNION ALL
    SELECT 'null_blank_keys', 'mes.item_station_events source or external_ref null or blank', 'FAIL', count(*)::bigint, min(item_station_event_pk::text), 'Station events need source and external_ref for idempotency.' FROM mes.item_station_events WHERE source IS NULL OR btrim(source) = '' OR external_ref IS NULL OR btrim(external_ref) = ''
    UNION ALL
    SELECT 'null_blank_keys', 'mes.station_queue station_code or order_id null or blank', 'FAIL', count(*)::bigint, min(station_queue_pk::text), 'Station queue rows need station_code and order_id.' FROM mes.station_queue WHERE station_code IS NULL OR btrim(station_code) = '' OR order_id IS NULL OR btrim(order_id) = ''
    UNION ALL
    SELECT 'null_blank_keys', 'mes.package_sessions.session_id null or blank', 'FAIL', count(*)::bigint, min(package_order_id), 'Package sessions need session_id.' FROM mes.package_sessions WHERE session_id IS NULL OR btrim(session_id) = ''
    UNION ALL
    SELECT
        'duplicate_keys',
        'mes.work_orders duplicate order_id',
        'FAIL',
        count(*)::bigint,
        min(order_id),
        'Resolve duplicate order_id before read source or migration gates.'
    FROM (
        SELECT order_id
        FROM mes.work_orders
        WHERE order_id IS NOT NULL AND btrim(order_id) <> ''
        GROUP BY order_id
        HAVING count(*) > 1
    ) d
    UNION ALL
    SELECT 'duplicate_keys', 'mes.production_completions duplicate external_ref', 'FAIL', count(*)::bigint, min(external_ref), 'Resolve duplicate external_ref before live hook or migration gates.' FROM (SELECT external_ref FROM mes.production_completions WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '' GROUP BY external_ref HAVING count(*) > 1) d
    UNION ALL
    SELECT 'duplicate_keys', 'mes.vision_events duplicate external_ref', 'FAIL', count(*)::bigint, min(external_ref), 'Resolve duplicate external_ref before live hook or migration gates.' FROM (SELECT external_ref FROM mes.vision_events WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '' GROUP BY external_ref HAVING count(*) > 1) d
    UNION ALL
    SELECT 'duplicate_keys', 'mes.work_order_events duplicate external_ref', 'FAIL', count(*)::bigint, min(external_ref), 'Resolve duplicate external_ref before transition event gates.' FROM (SELECT external_ref FROM mes.work_order_events WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '' GROUP BY external_ref HAVING count(*) > 1) d
    UNION ALL
    SELECT 'duplicate_keys', 'mes.item_station_events duplicate source external_ref', 'FAIL', count(*)::bigint, min(source || ':' || external_ref), 'Resolve duplicate station event idempotency key.' FROM (SELECT source, external_ref FROM mes.item_station_events WHERE source IS NOT NULL AND btrim(source) <> '' AND external_ref IS NOT NULL AND btrim(external_ref) <> '' GROUP BY source, external_ref HAVING count(*) > 1) d
)
SELECT
    check_group,
    check_name,
    severity,
    finding_count,
    sample_value,
    recommendation
FROM report_rows
ORDER BY check_group, check_name;

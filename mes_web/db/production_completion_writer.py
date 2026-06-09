from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..config import AppConfig
from .connection import database_connection
from .safe_write import DatabaseWriteResult, safe_db_write


JsonObject = dict[str, Any]

OPERATION = "production_completions_live_hook"
SOURCE_SYSTEM = "mes_web"
SOURCE_FILE = "runtime_hook"
HOOK_SOURCE = "f2c_live_hook"
HOOK_LOCATION = "_complete_runtime_item.after_route"
NATURAL_KEY_POLICY = "external_ref={order_id}_{item_id}"

PRODUCTION_COMPLETION_UPSERT_SQL = """
INSERT INTO mes.production_completions (
    order_id,
    item_id,
    classification,
    completed_at,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata,
    created_at
) VALUES (
    %(order_id)s,
    %(item_id)s,
    %(classification)s,
    %(completed_at)s,
    %(source_system)s,
    %(source_file)s,
    %(external_ref)s,
    %(payload)s,
    %(metadata)s,
    now()
)
ON CONFLICT (external_ref) WHERE external_ref IS NOT NULL AND btrim(external_ref) <> ''
DO UPDATE SET
    order_id = EXCLUDED.order_id,
    item_id = EXCLUDED.item_id,
    classification = EXCLUDED.classification,
    completed_at = EXCLUDED.completed_at,
    source_system = EXCLUDED.source_system,
    source_file = EXCLUDED.source_file,
    payload = EXCLUDED.payload,
    metadata = EXCLUDED.metadata
"""

_DB_ROW_KEYS = (
    "order_id",
    "item_id",
    "classification",
    "completed_at",
    "source_system",
    "source_file",
    "external_ref",
    "payload",
    "metadata",
)


@dataclass(frozen=True, slots=True)
class ProductionCompletionRow:
    external_ref: str | None
    status: str
    apply_safe: bool
    reason: str
    order_id: str | None
    item_id: str | None
    classification: str | None
    completed_at: str | None
    source_system: str
    source_file: str
    payload: JsonObject
    metadata: JsonObject


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nullable_text(value: Any) -> str | None:
    text = _text(value)
    if text.lower() in {"none", "null"}:
        return None
    return text or None


def _first_text(row: JsonObject, *names: str) -> str | None:
    for name in names:
        value = _nullable_text(row.get(name))
        if value is not None:
            return value
    return None


def _is_off_order_completion(item: JsonObject) -> bool:
    inventory_action = _text(item.get("inventoryAction"))
    return inventory_action in {"off_order_completion", "scrap_excluded"}


def _skipped_result(reason: str) -> DatabaseWriteResult:
    return DatabaseWriteResult(
        attempted=False,
        success=False,
        skipped=True,
        reason=reason,
        operation=OPERATION,
    )


def _error_fail_open_result(error_type: str) -> DatabaseWriteResult:
    return DatabaseWriteResult(
        attempted=True,
        success=False,
        skipped=False,
        reason="error_fail_open",
        operation=OPERATION,
        error_type=error_type,
    )


def _written_result(result: DatabaseWriteResult) -> DatabaseWriteResult:
    return DatabaseWriteResult(
        attempted=result.attempted,
        success=True,
        skipped=False,
        reason="written",
        operation=result.operation,
        error_type=result.error_type,
    )


def build_production_completion_row(item: JsonObject) -> ProductionCompletionRow:
    item_id = _first_text(item, "item_id", "itemId", "_extracted_item_id")
    order_id = _first_text(item, "work_order_id", "order_id", "workOrderId", "orderId", "currentOrderId", "erpOrderId", "sourceOrderId")
    completed_at = _first_text(item, "completed_at", "completedAt")
    classification = _first_text(item, "classification")
    external_ref = f"{order_id}_{item_id}" if order_id and item_id else None

    status = "APPLY_SAFE"
    reason = "apply_safe"
    apply_safe = True

    if _is_off_order_completion(item):
        status = "OFF_ORDER"
        reason = "off_order"
        apply_safe = False
    elif not order_id:
        status = "SKIPPED_MISSING_ORDER_ID"
        reason = "missing_order_id"
        apply_safe = False
    elif not item_id:
        status = "SKIPPED_MISSING_ITEM_ID"
        reason = "missing_item_id"
        apply_safe = False
    elif not completed_at:
        status = "SKIPPED_MISSING_COMPLETED_AT"
        reason = "missing_completed_at"
        apply_safe = False

    payload = dict(item)
    metadata = {
        "source": HOOK_SOURCE,
        "inventoryAction": item.get("inventoryAction"),
        "work_order_match_key": item.get("work_order_match_key"),
        "natural_key_policy": NATURAL_KEY_POLICY,
        "hook_location": HOOK_LOCATION,
        "status": status,
    }

    return ProductionCompletionRow(
        external_ref=external_ref,
        status=status,
        apply_safe=apply_safe,
        reason=reason,
        order_id=order_id,
        item_id=item_id,
        classification=classification,
        completed_at=completed_at,
        source_system=SOURCE_SYSTEM,
        source_file=SOURCE_FILE,
        payload=payload,
        metadata=metadata,
    )


def _jsonb(value: Any) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        return value
    return Jsonb(value)


def row_to_db_params(row: ProductionCompletionRow) -> JsonObject:
    params = {key: getattr(row, key) for key in _DB_ROW_KEYS}
    params["payload"] = _jsonb(row.payload)
    params["metadata"] = _jsonb(row.metadata)
    return params


def _upsert_production_completion_row(config: AppConfig, row: ProductionCompletionRow) -> None:
    params = row_to_db_params(row)

    with database_connection(config) as connection:
        if connection is None:
            raise RuntimeError("Database connection is disabled")
        with connection.cursor() as cursor:
            cursor.execute(PRODUCTION_COMPLETION_UPSERT_SQL, params)
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()


def mirror_production_completion_from_item(
    config: AppConfig,
    item: JsonObject,
    logger: logging.Logger | None = None,
) -> DatabaseWriteResult:
    if not config.db_enabled:
        return _skipped_result("disabled")

    if config.db_hook_production_completions_dry_run:
        if config.db_hook_production_completions and logger:
            logger.warning("Production completion live hook skipped because dry-run flag is enabled.")
        return _skipped_result("dry_run_enabled")

    if not config.db_hook_production_completions:
        return _skipped_result("live_hook_disabled")

    row = build_production_completion_row(item)
    if not row.apply_safe:
        return _skipped_result(row.reason)

    def writer() -> None:
        _upsert_production_completion_row(config, row)

    try:
        result = safe_db_write(
            config,
            OPERATION,
            writer,
            dry_run=False,
            fail_open=True,
            logger=logger,
        )
    except Exception as exc:
        if logger:
            logger.error("Production completion live hook failed open: %s", exc, exc_info=exc)
        return _error_fail_open_result(type(exc).__name__)

    if result.success:
        return _written_result(result)
    return result

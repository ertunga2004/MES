from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import AppConfig
from .connection import database_connection


JsonObject = dict[str, Any]


UPSERT_WORK_ORDER_SQL = """
INSERT INTO mes.work_orders (
    order_id,
    erp_type,
    status,
    product_code,
    target_quantity,
    started_at,
    completed_at,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata,
    updated_at
) VALUES (
    %(order_id)s,
    %(erp_type)s,
    %(status)s,
    %(product_code)s,
    %(target_quantity)s,
    %(started_at)s,
    %(completed_at)s,
    %(source_system)s,
    %(source_file)s,
    %(external_ref)s,
    %(payload)s,
    %(metadata)s,
    now()
)
ON CONFLICT (order_id) DO UPDATE SET
    erp_type = EXCLUDED.erp_type,
    status = EXCLUDED.status,
    product_code = EXCLUDED.product_code,
    target_quantity = EXCLUDED.target_quantity,
    started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at,
    source_system = EXCLUDED.source_system,
    source_file = EXCLUDED.source_file,
    external_ref = EXCLUDED.external_ref,
    payload = EXCLUDED.payload,
    metadata = EXCLUDED.metadata,
    updated_at = now()
"""


@dataclass(frozen=True, slots=True)
class WorkOrderMirrorResult:
    status: str
    attempted: bool = False
    row_count: int = 0
    inserted: int = 0
    updated: int = 0
    message: str = ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nullable_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _first_text(row: JsonObject, *names: str) -> str | None:
    for name in names:
        value = _nullable_text(row.get(name))
        if value is not None:
            return value
    return None


def _first_int(row: JsonObject, *names: str) -> int | None:
    for name in names:
        value = row.get(name)
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _timestamp_or_none(value: Any) -> str | None:
    text = _nullable_text(value)
    if text in {None, "0"}:
        return None
    return text


def _work_orders_payload(state: JsonObject) -> tuple[JsonObject, JsonObject]:
    work_orders = state.get("workOrders")
    if not isinstance(work_orders, dict):
        return {}, {}
    orders_by_id = work_orders.get("ordersById")
    return work_orders, orders_by_id if isinstance(orders_by_id, dict) else {}


def build_work_order_mirror_rows(state: JsonObject, *, state_file: Path | str | None = None) -> list[JsonObject]:
    work_orders, orders_by_id = _work_orders_payload(state)
    source = work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}
    source_file = _first_text(source, "file", "sourceFile")
    source_system = "mes_web"
    rows: list[JsonObject] = []

    for order_key, raw_order in sorted(orders_by_id.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_order, dict):
            continue
        order_id = _first_text(raw_order, "order_id", "orderId", "id") or _text(order_key)
        if not order_id:
            continue
        metadata = {
            "runtime_order_key": _text(order_key),
            "state_file": str(state_file or ""),
            "source_folder": _nullable_text(source.get("folder")) if isinstance(source, dict) else None,
            "source_loaded_at": _nullable_text(source.get("loadedAt")) if isinstance(source, dict) else None,
            "completed_quantity": _first_int(raw_order, "completedQty", "completed_quantity"),
            "remaining_quantity": _first_int(raw_order, "remainingQty", "remaining_quantity"),
            "priority": _first_int(raw_order, "priority"),
            "planned_fields": {
                "queued_at": _nullable_text(raw_order.get("queuedAt")),
                "planned_start_at": _first_text(raw_order, "plannedStartAt", "planned_start_at"),
                "planned_end_at": _first_text(raw_order, "plannedEndAt", "planned_end_at"),
            },
        }
        rows.append(
            {
                "order_id": order_id,
                "erp_type": _first_text(raw_order, "erpType", "erp_type"),
                "status": _first_text(raw_order, "status"),
                "product_code": _first_text(raw_order, "productCode", "product_code", "productId", "stockCode"),
                "target_quantity": _first_int(raw_order, "targetQuantity", "targetQty", "quantity"),
                "started_at": _timestamp_or_none(_first_text(raw_order, "startedAt", "started_at")),
                "completed_at": _timestamp_or_none(_first_text(raw_order, "completedAt", "completed_at", "autoCompletedAt")),
                "source_system": source_system,
                "source_file": source_file,
                "external_ref": order_id,
                "payload": raw_order,
                "metadata": metadata,
            }
        )
    return rows


def mirror_work_orders_from_state(config: AppConfig, state: JsonObject) -> WorkOrderMirrorResult:
    if not config.db_enabled:
        return WorkOrderMirrorResult(status="disabled", message="MES_WEB_DB_ENABLED=false")
    if not config.db_mirror_work_orders:
        return WorkOrderMirrorResult(status="disabled", message="MES_WEB_DB_MIRROR_WORK_ORDERS=false")

    rows = build_work_order_mirror_rows(state, state_file=config.oee_runtime_state_path)
    if not rows:
        return WorkOrderMirrorResult(status="empty", attempted=False, row_count=0, message="No work orders to mirror")

    try:
        return _upsert_work_order_rows(config, rows)
    except Exception as exc:
        return WorkOrderMirrorResult(
            status="error",
            attempted=True,
            row_count=len(rows),
            message=f"{type(exc).__name__}: {exc}",
        )


def _jsonb(value: Any) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        return value
    return Jsonb(value)


def _upsert_work_order_rows(config: AppConfig, rows: list[JsonObject]) -> WorkOrderMirrorResult:
    existing_order_ids: set[str] = set()
    inserted = 0
    updated = 0

    with database_connection(config) as connection:
        if connection is None:
            return WorkOrderMirrorResult(status="disabled", message="Database connection is disabled")
        with connection.cursor() as cursor:
            cursor.execute("SELECT order_id FROM mes.work_orders")
            existing_order_ids = {str(row[0]) for row in cursor.fetchall()}
            for row in rows:
                params = dict(row)
                params["payload"] = _jsonb(row["payload"])
                params["metadata"] = _jsonb(row["metadata"])
                cursor.execute(UPSERT_WORK_ORDER_SQL, params)
                if row["order_id"] in existing_order_ids:
                    updated += 1
                else:
                    inserted += 1
                    existing_order_ids.add(row["order_id"])
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

    return WorkOrderMirrorResult(
        status="ok",
        attempted=True,
        row_count=len(rows),
        inserted=inserted,
        updated=updated,
    )

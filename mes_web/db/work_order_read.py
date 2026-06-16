from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from ..config import AppConfig
from .connection import database_connection


JsonObject = dict[str, Any]

WORK_ORDER_READ_SOURCE = "postgresql"

WORK_ORDER_READ_SQL = """
SELECT
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
    created_at,
    updated_at
FROM mes.work_orders
ORDER BY
    CASE status
        WHEN 'active' THEN 0
        WHEN 'pending_approval' THEN 1
        WHEN 'queued' THEN 2
        WHEN 'completed' THEN 3
        ELSE 4
    END,
    created_at NULLS LAST,
    order_id
"""

WORK_ORDER_READ_FIELDS = (
    "order_id",
    "erp_type",
    "status",
    "product_code",
    "target_quantity",
    "started_at",
    "completed_at",
    "source_system",
    "source_file",
    "external_ref",
    "payload",
    "metadata",
    "created_at",
    "updated_at",
)

ACTIVE_STATUSES = {"active", "pending_approval"}


@dataclass(frozen=True, slots=True)
class WorkOrderDbReadResult:
    status: str
    attempted: bool
    row_count: int
    source: str
    state: JsonObject
    message: str = ""
    error_type: str | None = None


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


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _timestamp_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.astimezone().isoformat(timespec="milliseconds") if value.tzinfo else value.isoformat(timespec="milliseconds")
    if isinstance(value, date):
        return value.isoformat()
    return _nullable_text(value)


def _row_mapping(row: Any) -> JsonObject:
    if isinstance(row, Mapping):
        return {str(key): value for key, value in row.items()}
    values = list(row) if isinstance(row, (list, tuple)) else []
    return dict(zip(WORK_ORDER_READ_FIELDS, values))


def _payload_dict(value: Any) -> JsonObject:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _order_from_db_row(row: JsonObject) -> tuple[str, JsonObject] | None:
    payload = _payload_dict(row.get("payload"))
    order = copy.deepcopy(payload)
    order_id = _first_text(order, "orderId", "order_id", "id") or _nullable_text(row.get("order_id"))
    if order_id is None:
        return None

    order["orderId"] = order_id
    order.setdefault("id", order_id)

    erp_type = _nullable_text(row.get("erp_type"))
    status = _nullable_text(row.get("status"))
    product_code = _nullable_text(row.get("product_code"))
    target_quantity = _safe_int(row.get("target_quantity"))
    started_at = _timestamp_text(row.get("started_at"))
    completed_at = _timestamp_text(row.get("completed_at"))

    if erp_type is not None:
        order.setdefault("erpType", erp_type)
    if status is not None:
        order["status"] = status
    else:
        order.setdefault("status", "queued")
    if product_code is not None:
        order.setdefault("productCode", product_code)
        order.setdefault("stockCode", product_code)
    if target_quantity is not None:
        order.setdefault("targetQuantity", target_quantity)
        order.setdefault("targetQty", target_quantity)
        order.setdefault("quantity", target_quantity)
    if started_at is not None:
        order.setdefault("startedAt", started_at)
    if completed_at is not None:
        order.setdefault("completedAt", completed_at)

    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    source_file = _nullable_text(row.get("source_file"))
    source_system = _nullable_text(row.get("source_system"))
    external_ref = _nullable_text(row.get("external_ref"))
    db_metadata = {
        "source_system": source_system,
        "source_file": source_file,
        "external_ref": external_ref,
        "created_at": _timestamp_text(row.get("created_at")),
        "updated_at": _timestamp_text(row.get("updated_at")),
    }
    order["_db"] = {
        **{key: value for key, value in db_metadata.items() if value is not None},
        "metadata": copy.deepcopy(metadata),
    }
    return order_id, order


def _ordered_ids(fallback_work_orders: JsonObject, orders_by_id: JsonObject) -> list[str]:
    sequence = fallback_work_orders.get("orderSequence") if isinstance(fallback_work_orders.get("orderSequence"), list) else []
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_order_id in sequence:
        order_id = _text(raw_order_id)
        if order_id and order_id in orders_by_id and order_id not in seen:
            ordered.append(order_id)
            seen.add(order_id)
    for order_id in orders_by_id:
        if order_id not in seen:
            ordered.append(order_id)
            seen.add(order_id)
    return ordered


def _active_order_id(fallback_work_orders: JsonObject, orders_by_id: JsonObject, ordered_ids: list[str]) -> str:
    fallback_active_id = _text(fallback_work_orders.get("activeOrderId"))
    fallback_active_order = orders_by_id.get(fallback_active_id)
    if isinstance(fallback_active_order, dict) and _text(fallback_active_order.get("status")) in ACTIVE_STATUSES:
        return fallback_active_id
    for order_id in ordered_ids:
        order = orders_by_id.get(order_id)
        if isinstance(order, dict) and _text(order.get("status")) in ACTIVE_STATUSES:
            return order_id
    return ""


def _overlay_work_orders(fallback_state: JsonObject, rows: list[JsonObject]) -> JsonObject:
    state = copy.deepcopy(fallback_state)
    fallback_work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
    work_orders = copy.deepcopy(fallback_work_orders)
    orders_by_id: JsonObject = {}

    for row in rows:
        projected = _order_from_db_row(row)
        if projected is None:
            continue
        order_id, order = projected
        orders_by_id[order_id] = order

    if not orders_by_id:
        return state

    ordered_ids = _ordered_ids(fallback_work_orders, orders_by_id)
    work_orders["ordersById"] = orders_by_id
    work_orders["orderSequence"] = ordered_ids
    work_orders["activeOrderId"] = _active_order_id(fallback_work_orders, orders_by_id, ordered_ids)
    work_orders["source"] = {
        **(
            copy.deepcopy(fallback_work_orders.get("source"))
            if isinstance(fallback_work_orders.get("source"), dict)
            else {}
        ),
        "system": WORK_ORDER_READ_SOURCE,
        "table": "mes.work_orders",
        "mode": "db_read_work_orders",
    }
    state["workOrders"] = work_orders
    return state


def _fetch_work_order_rows(config: AppConfig) -> list[JsonObject]:
    with database_connection(config) as connection:
        if connection is None:
            return []
        with connection.cursor() as cursor:
            cursor.execute(WORK_ORDER_READ_SQL)
            return [_row_mapping(row) for row in cursor.fetchall()]


def state_with_db_work_orders(
    config: AppConfig,
    fallback_state: JsonObject,
    *,
    logger: Any | None = None,
) -> WorkOrderDbReadResult:
    if not config.db_enabled:
        return WorkOrderDbReadResult("disabled", False, 0, "runtime", fallback_state, "MES_WEB_DB_ENABLED=false")
    if not (config.db_read_work_orders or config.db_shadow_read_work_orders):
        return WorkOrderDbReadResult(
            "disabled",
            False,
            0,
            "runtime",
            fallback_state,
            "MES_WEB_DB_READ_WORK_ORDERS=false",
        )

    try:
        rows = _fetch_work_order_rows(config)
    except Exception as exc:
        if config.db_log_failures and logger is not None:
            logger.warning("Work order DB read failed; using runtime fallback: %s", exc)
        return WorkOrderDbReadResult(
            "fallback_error",
            True,
            0,
            "runtime",
            fallback_state,
            f"{type(exc).__name__}: {exc}",
            type(exc).__name__,
        )

    if config.db_shadow_read_work_orders and not config.db_read_work_orders:
        return WorkOrderDbReadResult("shadow_ok", True, len(rows), "runtime", fallback_state)

    if not rows:
        return WorkOrderDbReadResult("fallback_empty", True, 0, "runtime", fallback_state, "No DB work orders")

    state = _overlay_work_orders(fallback_state, rows)
    work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
    orders_by_id = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
    if not orders_by_id:
        return WorkOrderDbReadResult("fallback_empty", True, len(rows), "runtime", fallback_state, "No usable DB work orders")
    return WorkOrderDbReadResult("ok", True, len(rows), WORK_ORDER_READ_SOURCE, state)

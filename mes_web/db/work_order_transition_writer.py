from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import AppConfig
from .connection import database_connection
from .safe_write import DatabaseWriteResult, safe_db_write
from .work_order_mirror import UPSERT_WORK_ORDER_SQL, build_work_order_mirror_rows


JsonObject = dict[str, Any]

OPERATION = "work_order_transitions_live_hook"
SOURCE_SYSTEM = "mes_web"
SOURCE_FILE = "runtime_hook"
HOOK_SOURCE = "mes_web_work_order_transition_hook"
NATURAL_KEY_POLICY = "external_ref=work_order_transition:{event_type}:{order_id}:{event_at}"

UPSERT_WORK_ORDER_EVENT_SQL = """
INSERT INTO mes.work_order_events (
    order_id,
    event_type,
    event_at,
    actor_id,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata,
    created_at
) VALUES (
    %(order_id)s,
    %(event_type)s,
    %(event_at)s,
    %(actor_id)s,
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
    event_type = EXCLUDED.event_type,
    event_at = EXCLUDED.event_at,
    actor_id = EXCLUDED.actor_id,
    source_system = EXCLUDED.source_system,
    source_file = EXCLUDED.source_file,
    payload = EXCLUDED.payload,
    metadata = EXCLUDED.metadata
"""

DELETE_ABSENT_WORK_ORDERS_SQL = """
DELETE FROM mes.work_orders
WHERE NOT (order_id = ANY(%(order_ids)s))
"""


@dataclass(frozen=True, slots=True)
class WorkOrderTransitionEventRow:
    order_id: str | None
    event_type: str
    event_at: str | None
    actor_id: str | None
    source_system: str
    source_file: str
    external_ref: str
    payload: JsonObject
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class WorkOrderTransitionWriteResult:
    attempted: bool
    success: bool
    skipped: bool
    reason: str
    current_row_count: int = 0
    event_row_count: int = 0
    deleted_current_rows: int = 0
    error_type: str | None = None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nullable_text(value: Any) -> str | None:
    text = _text(value)
    if text.lower() in {"none", "null"}:
        return None
    return text or None


def _jsonb(value: Any) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        return value
    return Jsonb(value)


def _work_orders_payload(state: JsonObject) -> JsonObject:
    work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
    return work_orders


def _orders_by_id(work_orders: JsonObject) -> JsonObject:
    orders = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
    return orders


def _source_file(work_orders: JsonObject) -> str:
    source = work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}
    return _text(source.get("file")) or SOURCE_FILE


def _source_loaded_at(work_orders: JsonObject) -> str | None:
    source = work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}
    return _nullable_text(source.get("loadedAt"))


def _latest_log_time(work_orders: JsonObject, order_id: str, event_types: set[str]) -> str | None:
    for log_name in ("transitionLog", "completionLog"):
        rows = work_orders.get(log_name) if isinstance(work_orders.get(log_name), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if _text(row.get("orderId")) != order_id:
                continue
            if _text(row.get("eventType")) in event_types:
                return _nullable_text(row.get("time"))
    return None


def _event_type_for_order(requested_event_type: str, order: JsonObject) -> str:
    requested = _text(requested_event_type).lower() or "runtime_sync"
    status = _text(order.get("status")).lower()
    if status == "pending_approval" and requested in {"started", "runtime_sync", "runtime_state_changed"}:
        return "auto_completed"
    if status == "active" and requested in {"runtime_sync", "runtime_state_changed"}:
        return "started"
    if status == "completed" and requested in {"runtime_sync", "runtime_state_changed"}:
        return "completed"
    if requested == "accept_active":
        return "completed"
    if requested == "rollback_active":
        return "rolled_back"
    return requested


def _is_order_scoped_request(requested_event_type: str) -> bool:
    requested = _text(requested_event_type).lower()
    return requested in {
        "started",
        "completed",
        "accept_active",
        "rollback_active",
        "rolled_back",
        "package_started",
        "package_finished",
    }


def _should_emit_order_scoped_event(
    requested_event_type: str,
    normalized_event_type: str,
    work_orders: JsonObject,
    order_id: str,
    order: JsonObject,
) -> bool:
    if not _is_order_scoped_request(requested_event_type):
        return True

    requested = _text(requested_event_type).lower()
    status = _text(order.get("status")).lower()

    if normalized_event_type == "auto_completed":
        return status == "pending_approval" and bool(
            _nullable_text(order.get("autoCompletedAt"))
            or _nullable_text(order.get("lastAllocationAt"))
            or _latest_log_time(work_orders, order_id, {"auto_completed"})
        )

    if normalized_event_type == "completed":
        return status == "completed" and bool(
            _nullable_text(order.get("completedAt"))
            or _latest_log_time(work_orders, order_id, {"completed"})
        )

    if normalized_event_type == "started":
        return status == "active" and bool(
            _nullable_text(order.get("startedAt"))
            or _latest_log_time(work_orders, order_id, {"started", "package_started"})
        )

    if normalized_event_type == "package_started":
        return status == "active" and bool(
            _latest_log_time(work_orders, order_id, {"package_started"})
            or (requested == "package_started" and _nullable_text(order.get("startedAt")))
        )

    if normalized_event_type == "package_finished":
        return status in {"active", "pending_approval", "completed"} and bool(
            _latest_log_time(work_orders, order_id, {"package_finished"})
            or _nullable_text(order.get("lastAllocationAt"))
        )

    if normalized_event_type == "rolled_back":
        return status == "queued" and bool(_latest_log_time(work_orders, order_id, {"rolled_back"}))

    return True


def _event_at_for_order(state: JsonObject, work_orders: JsonObject, order_id: str, order: JsonObject, event_type: str) -> str | None:
    log_types = {event_type}
    if event_type == "auto_completed":
        log_types.add("auto_completed")
    elif event_type == "completed":
        log_types.add("completed")
    elif event_type == "started":
        log_types.update({"started", "package_started"})
    elif event_type == "package_finished":
        log_types.add("package_finished")
    elif event_type == "rolled_back":
        log_types.add("rolled_back")

    log_time = _latest_log_time(work_orders, order_id, log_types)
    if log_time is not None:
        return log_time

    candidates: tuple[Any, ...]
    if event_type == "auto_completed":
        candidates = (
            order.get("autoCompletedAt"),
            order.get("lastAllocationAt"),
            order.get("completedAt"),
            order.get("startedAt"),
        )
    elif event_type in {"completed", "package_finished"}:
        candidates = (
            order.get("completedAt"),
            order.get("autoCompletedAt"),
            order.get("lastAllocationAt"),
            order.get("startedAt"),
        )
    elif event_type in {"started", "package_started"}:
        candidates = (order.get("startedAt"), order.get("queuedAt"))
    elif event_type in {"import", "reload", "bootstrap_import"}:
        candidates = (_source_loaded_at(work_orders), order.get("queuedAt"))
    else:
        candidates = (
            order.get("updatedAt"),
            order.get("lastAllocationAt"),
            order.get("completedAt"),
            order.get("autoCompletedAt"),
            order.get("startedAt"),
            order.get("queuedAt"),
        )

    for candidate in candidates:
        value = _nullable_text(candidate)
        if value is not None:
            return value
    return _nullable_text(state.get("lastUpdatedAt")) or _source_loaded_at(work_orders)


def _event_external_ref(event_type: str, order_id: str | None, event_at: str | None) -> str:
    safe_order_id = _text(order_id) or "GLOBAL"
    safe_event_at = _text(event_at) or "no_time"
    return f"work_order_transition:{event_type}:{safe_order_id}:{safe_event_at}"


def build_work_order_transition_event_rows(
    state: JsonObject,
    *,
    event_type: str,
    actor_id: str = "",
    replace_current: bool = False,
    state_file: Path | str | None = None,
) -> list[WorkOrderTransitionEventRow]:
    work_orders = _work_orders_payload(state)
    orders = _orders_by_id(work_orders)
    source_file = _source_file(work_orders)
    rows: list[WorkOrderTransitionEventRow] = []

    for order_key, raw_order in sorted(orders.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_order, dict):
            continue
        order_id = _text(raw_order.get("orderId") or raw_order.get("order_id") or raw_order.get("id") or order_key)
        if not order_id:
            continue
        normalized_event_type = _event_type_for_order(event_type, raw_order)
        if not _should_emit_order_scoped_event(event_type, normalized_event_type, work_orders, order_id, raw_order):
            continue
        event_at = _event_at_for_order(state, work_orders, order_id, raw_order, normalized_event_type)
        status = _text(raw_order.get("status")).lower() or "unknown"
        rows.append(
            WorkOrderTransitionEventRow(
                order_id=order_id,
                event_type=normalized_event_type,
                event_at=event_at,
                actor_id=_nullable_text(actor_id),
                source_system=SOURCE_SYSTEM,
                source_file=source_file,
                external_ref=_event_external_ref(normalized_event_type, order_id, event_at),
                payload={
                    "order": dict(raw_order),
                    "work_order_source": dict(work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}),
                    "active_order_id": _text(work_orders.get("activeOrderId")),
                    "last_completed_order_id": _text(work_orders.get("lastCompletedOrderId")),
                },
                metadata={
                    "source": HOOK_SOURCE,
                    "requested_event_type": _text(event_type) or "runtime_sync",
                    "status": status,
                    "replace_current": bool(replace_current),
                    "runtime_order_key": _text(order_key),
                    "state_file": str(state_file or ""),
                    "natural_key_policy": NATURAL_KEY_POLICY,
                },
            )
        )

    if not rows and replace_current:
        event_at = _nullable_text(state.get("lastUpdatedAt")) or _source_loaded_at(work_orders)
        normalized_event_type = _text(event_type).lower() or "reset"
        rows.append(
            WorkOrderTransitionEventRow(
                order_id=None,
                event_type=normalized_event_type,
                event_at=event_at,
                actor_id=_nullable_text(actor_id),
                source_system=SOURCE_SYSTEM,
                source_file=source_file,
                external_ref=_event_external_ref(normalized_event_type, None, event_at),
                payload={
                    "work_order_source": dict(work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}),
                    "active_order_id": _text(work_orders.get("activeOrderId")),
                    "last_completed_order_id": _text(work_orders.get("lastCompletedOrderId")),
                },
                metadata={
                    "source": HOOK_SOURCE,
                    "requested_event_type": _text(event_type) or "reset",
                    "status": "empty_current_state",
                    "replace_current": True,
                    "state_file": str(state_file or ""),
                    "natural_key_policy": NATURAL_KEY_POLICY,
                },
            )
        )
    return rows


def _event_params(row: WorkOrderTransitionEventRow) -> JsonObject:
    return {
        "order_id": row.order_id,
        "event_type": row.event_type,
        "event_at": row.event_at,
        "actor_id": row.actor_id,
        "source_system": row.source_system,
        "source_file": row.source_file,
        "external_ref": row.external_ref,
        "payload": _jsonb(row.payload),
        "metadata": _jsonb(row.metadata),
    }


def _work_order_params(row: JsonObject) -> JsonObject:
    params = dict(row)
    if _text(params.get("status")).lower() != "completed":
        params["completed_at"] = None
    params["payload"] = _jsonb(row.get("payload") or {})
    params["metadata"] = _jsonb(row.get("metadata") or {})
    return params


def _execute_transition_write(
    config: AppConfig,
    current_rows: list[JsonObject],
    event_rows: list[WorkOrderTransitionEventRow],
    *,
    replace_current: bool,
) -> dict[str, int]:
    deleted_current_rows = 0
    order_ids = [row["order_id"] for row in current_rows if _text(row.get("order_id"))]

    with database_connection(config) as connection:
        if connection is None:
            raise RuntimeError("Database connection is disabled")
        with connection.cursor() as cursor:
            if replace_current:
                if order_ids:
                    cursor.execute(DELETE_ABSENT_WORK_ORDERS_SQL, {"order_ids": order_ids})
                else:
                    cursor.execute("DELETE FROM mes.work_orders")
                deleted_current_rows = int(getattr(cursor, "rowcount", 0) or 0)

            for row in current_rows:
                cursor.execute(UPSERT_WORK_ORDER_SQL, _work_order_params(row))

            for row in event_rows:
                cursor.execute(UPSERT_WORK_ORDER_EVENT_SQL, _event_params(row))

        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

    return {
        "current_row_count": len(current_rows),
        "event_row_count": len(event_rows),
        "deleted_current_rows": deleted_current_rows,
    }


def mirror_work_order_transition_from_state(
    config: AppConfig,
    state: JsonObject,
    *,
    event_type: str = "runtime_sync",
    actor_id: str = "",
    replace_current: bool = False,
) -> WorkOrderTransitionWriteResult:
    if not config.db_enabled:
        return WorkOrderTransitionWriteResult(False, False, True, "disabled")
    if config.db_hook_work_order_transitions_dry_run:
        return WorkOrderTransitionWriteResult(False, False, True, "dry_run_enabled")
    if not config.db_hook_work_order_transitions:
        return WorkOrderTransitionWriteResult(False, False, True, "live_hook_disabled")

    current_rows = build_work_order_mirror_rows(state, state_file=config.oee_runtime_state_path)
    event_rows = build_work_order_transition_event_rows(
        state,
        event_type=event_type,
        actor_id=actor_id,
        replace_current=replace_current,
        state_file=config.oee_runtime_state_path,
    )
    if not current_rows and not replace_current:
        return WorkOrderTransitionWriteResult(False, False, True, "empty_current_state")

    stats: dict[str, int] = {
        "current_row_count": len(current_rows),
        "event_row_count": len(event_rows),
        "deleted_current_rows": 0,
    }

    def writer() -> None:
        stats.update(
            _execute_transition_write(
                config,
                current_rows,
                event_rows,
                replace_current=replace_current,
            )
        )

    result: DatabaseWriteResult = safe_db_write(
        config,
        OPERATION,
        writer,
        dry_run=False,
        fail_open=True,
    )
    if result.success:
        return WorkOrderTransitionWriteResult(
            True,
            True,
            False,
            "written",
            current_row_count=stats["current_row_count"],
            event_row_count=stats["event_row_count"],
            deleted_current_rows=stats["deleted_current_rows"],
        )
    return WorkOrderTransitionWriteResult(
        result.attempted,
        result.success,
        result.skipped,
        result.reason,
        current_row_count=stats["current_row_count"],
        event_row_count=stats["event_row_count"],
        deleted_current_rows=stats["deleted_current_rows"],
        error_type=result.error_type,
    )

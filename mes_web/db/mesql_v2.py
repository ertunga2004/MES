from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from ..config import AppConfig
from .connection import database_connection


JsonObject = dict[str, Any]

SOURCE_SYSTEM = "mes_web"
MESQL_SOURCE_SYSTEM = "mesql"
STATION_LOCATION_READ_MODEL_FEATURE_FLAG = "MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED"

READY_OPERATION_STATUSES = {"queued", "ready"}
ACTIVE_OPERATION_STATUSES = {"active", "in_progress"}
COMPLETED_OPERATION_STATUSES = {"completed", "done"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(child) for child in value]
    return value


class MesqlV2Error(RuntimeError):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(slots=True)
class MesqlPullResult:
    pulled_station_count: int = 0
    upserted_work_orders: int = 0
    upserted_operations: int = 0
    upserted_queue_items: int = 0
    upserted_packaging_units: int = 0
    skipped_items: int = 0
    errors: list[JsonObject] = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> JsonObject:
        return _json_safe({
            "pulled_station_count": self.pulled_station_count,
            "upserted_work_orders": self.upserted_work_orders,
            "upserted_operations": self.upserted_operations,
            "upserted_queue_items": self.upserted_queue_items,
            "upserted_packaging_units": self.upserted_packaging_units,
            "skipped_items": self.skipped_items,
            "errors": list(self.errors),
            "dry_run": self.dry_run,
        })


@dataclass(frozen=True, slots=True)
class PendingOutboxEvent:
    outbox_id: str
    event_type: str
    order_id: str | None
    work_order_operation_id: str | None
    station_code: str | None
    dedupe_key: str
    payload: JsonObject


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nullable_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _upper(value: Any) -> str:
    return _text(value).upper()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _nullable_upper(value: Any) -> str | None:
    text = _upper(value)
    return text or None


def _safe_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _jsonb(value: Any) -> Any:
    safe_value = _json_safe(value)
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        return safe_value
    return Jsonb(safe_value)


def _transition_timestamp(value: Any | None = None) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value not in (None, ""):
        return _text(value)
    return datetime.now(timezone.utc).isoformat()


def _field(row: Any, index: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, (list, tuple)) and len(row) > index:
        return row[index]
    return None


def _field_any(row: Any, index: int, *keys: str) -> Any:
    if isinstance(row, dict):
        for key in keys:
            if key in row:
                return row.get(key)
        return None
    key = keys[0] if keys else ""
    return _field(row, index, key)


def _transaction(connection: Any):
    transaction = getattr(connection, "transaction", None)
    if callable(transaction):
        return transaction()
    return nullcontext()


def normalize_mesql_status(value: Any, *, default: str = "queued") -> str:
    raw = _text(value).lower()
    if raw in {"queued", "ready", "planned", "released"}:
        return "queued"
    if raw in {"active", "in_progress", "started", "running"}:
        return "active"
    if raw in {"completed", "done", "finished"}:
        return "completed"
    if raw in {"cancelled", "canceled"}:
        return "cancelled"
    return default


def _operation_payload(item: JsonObject) -> JsonObject:
    operation = item.get("operation")
    return dict(operation) if isinstance(operation, dict) else {}


def _is_package_order_id(order_id: str) -> bool:
    return order_id.upper().startswith("PKG-")


def _canonical_order_id(item: JsonObject) -> str:
    raw_order_id = _text(item.get("order_id"))
    if not _is_package_order_id(raw_order_id):
        return raw_order_id
    operation = _operation_payload(item)
    for key in (
        "parent_order_id",
        "parentOrderId",
        "work_order_id",
        "workOrderId",
        "source_order_id",
        "sourceOrderId",
        "production_order_id",
        "productionOrderId",
    ):
        candidate = _text(item.get(key) or operation.get(key))
        if candidate and not _is_package_order_id(candidate):
            return candidate
    return ""


def _operation_no(item: JsonObject) -> int:
    operation = _operation_payload(item)
    return max(_safe_int(operation.get("operation_no") or item.get("operation_no"), 10), 1)


def _station_code(item: JsonObject, fallback_station_code: str) -> str:
    operation = _operation_payload(item)
    return (
        _upper(operation.get("station_code"))
        or _upper(item.get("station_code"))
        or _upper(fallback_station_code)
    )


def _planned_quantity(item: JsonObject) -> float | None:
    operation = _operation_payload(item)
    return _safe_float(operation.get("planned_quantity") or item.get("planned_quantity") or item.get("target_quantity"))


def _target_quantity_for_work_order(item: JsonObject) -> int | None:
    quantity = _planned_quantity(item)
    if quantity is None:
        return None
    return int(quantity)


UPSERT_INBOX_SQL = """
INSERT INTO mes.integration_inbox (
    source_system,
    source_endpoint,
    source_id,
    message_type,
    dedupe_key,
    payload,
    processed_at,
    error_text,
    created_at
) VALUES (
    %(source_system)s,
    %(source_endpoint)s,
    %(source_id)s,
    %(message_type)s,
    %(dedupe_key)s,
    %(payload)s,
    now(),
    NULL,
    now()
)
ON CONFLICT (dedupe_key) DO UPDATE SET
    payload = EXCLUDED.payload,
    processed_at = now(),
    error_text = NULL
"""

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
    erp_type = COALESCE(EXCLUDED.erp_type, mes.work_orders.erp_type),
    status = EXCLUDED.status,
    product_code = COALESCE(EXCLUDED.product_code, mes.work_orders.product_code),
    target_quantity = COALESCE(EXCLUDED.target_quantity, mes.work_orders.target_quantity),
    completed_at = EXCLUDED.completed_at,
    source_system = EXCLUDED.source_system,
    source_file = EXCLUDED.source_file,
    external_ref = EXCLUDED.external_ref,
    payload = EXCLUDED.payload,
    metadata = mes.work_orders.metadata || EXCLUDED.metadata,
    updated_at = now()
"""

UPSERT_OPERATION_SQL = """
INSERT INTO mes.work_order_operations (
    order_id,
    mesql_work_order_operation_id,
    operation_no,
    operation_code,
    operation_name,
    sequence_no,
    station_code,
    status,
    planned_quantity,
    good_quantity,
    scrap_quantity,
    uom_code,
    payload,
    metadata,
    updated_at
) VALUES (
    %(order_id)s,
    %(mesql_work_order_operation_id)s,
    %(operation_no)s,
    %(operation_code)s,
    %(operation_name)s,
    %(sequence_no)s,
    %(station_code)s,
    %(status)s,
    %(planned_quantity)s,
    %(good_quantity)s,
    %(scrap_quantity)s,
    %(uom_code)s,
    %(payload)s,
    %(metadata)s,
    now()
)
ON CONFLICT (order_id, operation_no) DO UPDATE SET
    mesql_work_order_operation_id = COALESCE(EXCLUDED.mesql_work_order_operation_id, mes.work_order_operations.mesql_work_order_operation_id),
    operation_code = EXCLUDED.operation_code,
    operation_name = EXCLUDED.operation_name,
    sequence_no = EXCLUDED.sequence_no,
    station_code = EXCLUDED.station_code,
    status = EXCLUDED.status,
    planned_quantity = EXCLUDED.planned_quantity,
    good_quantity = EXCLUDED.good_quantity,
    scrap_quantity = EXCLUDED.scrap_quantity,
    uom_code = EXCLUDED.uom_code,
    payload = EXCLUDED.payload,
    metadata = mes.work_order_operations.metadata || EXCLUDED.metadata,
    updated_at = now()
RETURNING work_order_operation_id
"""

SELECT_QUEUE_ROW_SQL = """
SELECT station_queue_pk, order_id, work_order_operation_id, queue_rank, status
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND order_id = %(order_id)s
LIMIT 1
"""

SELECT_ACTIVE_RANK_CONFLICT_SQL = """
SELECT station_queue_pk, order_id, work_order_operation_id
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND queue_rank = %(queue_rank)s
  AND order_id <> %(order_id)s
  AND status IN ('queued', 'active', 'pending_approval')
LIMIT 1
"""

INSERT_QUEUE_SQL = """
INSERT INTO mes.station_queue (
    station_code,
    order_id,
    work_order_operation_id,
    queue_rank,
    status,
    source,
    payload,
    metadata,
    updated_at
) VALUES (
    %(station_code)s,
    %(order_id)s,
    %(work_order_operation_id)s,
    %(queue_rank)s,
    %(status)s,
    %(source)s,
    %(payload)s,
    %(metadata)s,
    now()
)
"""

UPDATE_QUEUE_SQL = """
UPDATE mes.station_queue
SET
    work_order_operation_id = %(work_order_operation_id)s,
    queue_rank = %(queue_rank)s,
    status = %(status)s,
    source = %(source)s,
    payload = %(payload)s,
    metadata = metadata || %(metadata)s,
    updated_at = now()
WHERE station_code = %(station_code)s
  AND order_id = %(order_id)s
"""

UPSERT_PACKAGING_UNIT_SQL = """
INSERT INTO mes.packaging_units (
    package_no,
    order_id,
    work_order_operation_id,
    station_code,
    product_code,
    quantity,
    uom_code,
    status,
    payload,
    metadata,
    updated_at
) VALUES (
    %(package_no)s,
    %(order_id)s,
    %(work_order_operation_id)s,
    %(station_code)s,
    %(product_code)s,
    %(quantity)s,
    %(uom_code)s,
    %(status)s,
    %(payload)s,
    %(metadata)s,
    now()
)
ON CONFLICT (package_no) DO UPDATE SET
    order_id = EXCLUDED.order_id,
    work_order_operation_id = EXCLUDED.work_order_operation_id,
    station_code = EXCLUDED.station_code,
    product_code = EXCLUDED.product_code,
    quantity = EXCLUDED.quantity,
    uom_code = EXCLUDED.uom_code,
    status = EXCLUDED.status,
    payload = EXCLUDED.payload,
    metadata = mes.packaging_units.metadata || EXCLUDED.metadata,
    updated_at = now()
"""

SELECT_V2_QUEUE_SQL = """
SELECT
    q.station_code,
    q.queue_rank,
    q.order_id,
    q.status AS queue_status,
    q.payload AS queue_payload,
    q.metadata AS queue_metadata,
    w.product_code,
    w.target_quantity,
    w.status AS order_status,
    w.started_at AS order_started_at,
    w.completed_at AS order_completed_at,
    w.payload AS order_payload,
    w.metadata AS order_metadata,
    o.work_order_operation_id,
    o.operation_no,
    o.operation_code,
    o.operation_name,
    o.sequence_no,
    o.status AS operation_status,
    o.planned_quantity,
    o.good_quantity,
    o.scrap_quantity,
    o.uom_code,
    o.started_at AS operation_started_at,
    o.completed_at AS operation_completed_at,
    o.payload AS operation_payload,
    o.metadata AS operation_metadata
FROM mes.station_queue q
JOIN mes.work_orders w ON w.order_id = q.order_id
LEFT JOIN mes.work_order_operations o
  ON o.work_order_operation_id = q.work_order_operation_id
  OR (
      q.work_order_operation_id IS NULL
      AND o.order_id = q.order_id
      AND o.station_code = q.station_code
  )
WHERE q.station_code = %(station_code)s
ORDER BY q.queue_rank, q.order_id, o.sequence_no
"""

SELECT_LOCATIONS_SQL = """
SELECT
    location_pk,
    location_id,
    location_code,
    location_name,
    location_type,
    parent_location_code,
    station_code,
    active,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata,
    created_at,
    updated_at
FROM mes.locations
WHERE (CAST(%(active_only)s AS boolean) = false OR active = true)
  AND (
      CAST(%(location_type)s AS text) IS NULL
      OR location_type = CAST(%(location_type)s AS text)
  )
ORDER BY location_type, location_code
"""

SELECT_LOCATION_BY_CODE_SQL = """
SELECT
    location_pk,
    location_id,
    location_code,
    location_name,
    location_type,
    parent_location_code,
    station_code,
    active,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata,
    created_at,
    updated_at
FROM mes.locations
WHERE location_code = %(location_code)s
LIMIT 1
"""

SELECT_STATION_LOCATION_BINDINGS_SQL = """
SELECT
    b.binding_pk,
    b.binding_id,
    b.station_code,
    b.role,
    b.location_code,
    b.item_scope,
    b.operation_scope,
    b.priority,
    b.active,
    b.source_system AS binding_source_system,
    b.source_file AS binding_source_file,
    b.external_ref AS binding_external_ref,
    b.payload AS binding_payload,
    b.metadata AS binding_metadata,
    b.created_at AS binding_created_at,
    b.updated_at AS binding_updated_at,
    l.location_pk,
    l.location_id,
    l.location_code AS joined_location_code,
    l.location_name,
    l.location_type,
    l.parent_location_code,
    l.station_code AS location_station_code,
    l.active AS location_active,
    l.source_system AS location_source_system,
    l.source_file AS location_source_file,
    l.external_ref AS location_external_ref,
    l.payload AS location_payload,
    l.metadata AS location_metadata,
    l.created_at AS location_created_at,
    l.updated_at AS location_updated_at
FROM mes.station_location_bindings b
LEFT JOIN mes.locations l
  ON l.location_code = b.location_code
WHERE b.station_code = %(station_code)s
  AND (CAST(%(active_only)s AS boolean) = false OR b.active = true)
  AND (
      CAST(%(role)s AS text) IS NULL
      OR b.role = CAST(%(role)s AS text)
  )
ORDER BY b.role, b.priority, b.location_code
"""

SELECT_RESOLVE_STATION_LOCATION_SQL = """
SELECT
    b.binding_pk,
    b.binding_id,
    b.station_code,
    b.role,
    b.location_code,
    b.item_scope,
    b.operation_scope,
    b.priority,
    b.active,
    b.source_system AS binding_source_system,
    b.source_file AS binding_source_file,
    b.external_ref AS binding_external_ref,
    b.payload AS binding_payload,
    b.metadata AS binding_metadata,
    b.created_at AS binding_created_at,
    b.updated_at AS binding_updated_at,
    l.location_pk,
    l.location_id,
    l.location_code AS joined_location_code,
    l.location_name,
    l.location_type,
    l.parent_location_code,
    l.station_code AS location_station_code,
    l.active AS location_active,
    l.source_system AS location_source_system,
    l.source_file AS location_source_file,
    l.external_ref AS location_external_ref,
    l.payload AS location_payload,
    l.metadata AS location_metadata,
    l.created_at AS location_created_at,
    l.updated_at AS location_updated_at
FROM mes.station_location_bindings b
JOIN mes.locations l
  ON l.location_code = b.location_code
WHERE b.station_code = %(station_code)s
  AND b.role = %(role)s
  AND b.active = true
  AND l.active = true
  AND (
      b.item_scope IS NULL
      OR b.item_scope = CAST(%(item_scope)s AS text)
  )
  AND (
      b.operation_scope IS NULL
      OR b.operation_scope = CAST(%(operation_scope)s AS text)
  )
ORDER BY
    CASE WHEN b.item_scope = CAST(%(item_scope)s AS text) THEN 0 ELSE 1 END,
    CASE WHEN b.operation_scope = CAST(%(operation_scope)s AS text) THEN 0 ELSE 1 END,
    b.priority ASC,
    b.location_code ASC
LIMIT 1
"""

SELECT_ITEMS_SQL = """
SELECT
    item_code,
    item_name,
    item_type,
    unit,
    active,
    metadata
FROM mes.items
WHERE (CAST(%(active_only)s AS boolean) = false OR active = true)
ORDER BY item_type ASC, item_code ASC
"""

SELECT_ITEM_BY_CODE_SQL = """
SELECT
    item_code,
    item_name,
    item_type,
    unit,
    active,
    metadata
FROM mes.items
WHERE item_code = %(item_code)s
LIMIT 1
"""

SELECT_PROCESS_ROUTES_SQL = """
SELECT
    route_code,
    version,
    route_name,
    item_code,
    active,
    metadata
FROM mes.process_routes
WHERE (CAST(%(active_only)s AS boolean) = false OR active = true)
  AND (
      CAST(%(item_code)s AS text) IS NULL
      OR item_code = CAST(%(item_code)s AS text)
  )
ORDER BY route_code ASC, version ASC
"""

SELECT_PROCESS_ROUTE_SQL = """
SELECT
    route_code,
    version,
    route_name,
    item_code,
    active,
    metadata
FROM mes.process_routes
WHERE route_code = %(route_code)s
  AND version = %(version)s
LIMIT 1
"""

SELECT_ROUTE_OPERATIONS_SQL = """
SELECT
    route_operation_id,
    route_code,
    route_version,
    sequence_no,
    operation_code,
    operation_name,
    station_code,
    input_item_code,
    output_item_code,
    input_qty_per_cycle,
    output_qty_per_cycle,
    input_location_role,
    output_location_role,
    scrap_location_role,
    operation_completion_policy,
    planned_cycle_time_sec,
    active,
    metadata
FROM mes.route_operations
WHERE (CAST(%(active_only)s AS boolean) = false OR active = true)
  AND (
      CAST(%(route_code)s AS text) IS NULL
      OR route_code = CAST(%(route_code)s AS text)
  )
  AND (
      CAST(%(station_code)s AS text) IS NULL
      OR station_code = CAST(%(station_code)s AS text)
  )
ORDER BY route_code ASC, route_version ASC, sequence_no ASC
"""

SELECT_ROUTE_OPERATION_BY_ID_SQL = """
SELECT
    route_operation_id,
    route_code,
    route_version,
    sequence_no,
    operation_code,
    operation_name,
    station_code,
    input_item_code,
    output_item_code,
    input_qty_per_cycle,
    output_qty_per_cycle,
    input_location_role,
    output_location_role,
    scrap_location_role,
    operation_completion_policy,
    planned_cycle_time_sec,
    active,
    metadata
FROM mes.route_operations
WHERE route_operation_id = %(route_operation_id)s
LIMIT 1
"""

SELECT_STATION_EVENT_SOURCES_SQL = """
SELECT
    station_code,
    source_code,
    source_name,
    source_type,
    event_channel,
    mqtt_topic,
    active,
    metadata
FROM mes.station_event_sources
WHERE station_code = %(station_code)s
  AND (CAST(%(active_only)s AS boolean) = false OR active = true)
ORDER BY source_type ASC, source_code ASC
"""

SELECT_STATION_EVENT_SOURCE_SQL = """
SELECT
    station_code,
    source_code,
    source_name,
    source_type,
    event_channel,
    mqtt_topic,
    active,
    metadata
FROM mes.station_event_sources
WHERE station_code = %(station_code)s
  AND source_code = %(source_code)s
LIMIT 1
"""

SELECT_OPERATION_STEPS_SQL = """
SELECT
    route_operation_id,
    operation_code,
    step_no,
    step_code,
    step_name,
    start_mode,
    finish_mode,
    start_event_source_code,
    finish_event_source_code,
    required_for_completion,
    records_duration,
    approval_required_after_finish,
    actor_type,
    active,
    metadata
FROM mes.operation_steps
WHERE route_operation_id = %(route_operation_id)s
  AND (CAST(%(active_only)s AS boolean) = false OR active = true)
ORDER BY step_no ASC
"""

SELECT_OPERATION_STEP_SQL = """
SELECT
    route_operation_id,
    operation_code,
    step_no,
    step_code,
    step_name,
    start_mode,
    finish_mode,
    start_event_source_code,
    finish_event_source_code,
    required_for_completion,
    records_duration,
    approval_required_after_finish,
    actor_type,
    active,
    metadata
FROM mes.operation_steps
WHERE route_operation_id = %(route_operation_id)s
  AND step_code = %(step_code)s
LIMIT 1
"""

SELECT_STATION_EXISTS_SQL = """
SELECT true AS station_exists
FROM mes.stations
WHERE station_code = %(station_code)s
  AND active = true
LIMIT 1
"""

SELECT_RUNTIME_WORK_ORDER_OPERATION_SQL = """
SELECT
    work_order_operation_id,
    order_id,
    operation_code,
    station_code
FROM mes.work_order_operations
WHERE work_order_operation_id = %(work_order_operation_id)s
LIMIT 1
"""

SELECT_EXECUTION_STATE_SQL = """
SELECT
    execution_state_id,
    work_order_operation_id,
    work_order_id,
    station_code,
    operation_code,
    execution_status,
    operation_completion_policy,
    current_step_code,
    started_at,
    evidence_completed_at,
    pending_final_approval_at,
    closed_at,
    last_event_id,
    last_approval_id,
    created_at,
    updated_at,
    metadata
FROM mes.work_order_operation_execution_state
WHERE work_order_operation_id = %(work_order_operation_id)s
LIMIT 1
"""

SELECT_EXECUTION_STATE_FOR_UPDATE_SQL = """
SELECT
    execution_state_id,
    work_order_operation_id,
    work_order_id,
    station_code,
    operation_code,
    execution_status,
    operation_completion_policy,
    current_step_code,
    started_at,
    evidence_completed_at,
    pending_final_approval_at,
    closed_at,
    last_event_id,
    last_approval_id,
    created_at,
    updated_at,
    metadata
FROM mes.work_order_operation_execution_state
WHERE work_order_operation_id = %(work_order_operation_id)s
LIMIT 1
FOR UPDATE
"""

SELECT_EXECUTION_STEPS_SQL = """
SELECT
    work_order_operation_step_id,
    work_order_operation_id,
    work_order_id,
    operation_code,
    step_code,
    step_no,
    station_code,
    status,
    started_at,
    completed_at,
    started_by_event_id,
    completed_by_event_id,
    required_for_completion,
    records_duration,
    approval_required_after_finish,
    created_at,
    updated_at,
    metadata
FROM mes.work_order_operation_steps
WHERE work_order_operation_id = %(work_order_operation_id)s
ORDER BY step_no ASC
"""

INSERT_EXECUTION_STATE_SQL = """
INSERT INTO mes.work_order_operation_execution_state (
    execution_state_id,
    work_order_operation_id,
    work_order_id,
    station_code,
    operation_code,
    execution_status,
    operation_completion_policy,
    current_step_code,
    metadata,
    updated_at
) VALUES (
    %(execution_state_id)s,
    %(work_order_operation_id)s,
    %(work_order_id)s,
    %(station_code)s,
    %(operation_code)s,
    %(execution_status)s,
    %(operation_completion_policy)s,
    %(current_step_code)s,
    %(metadata)s,
    now()
)
ON CONFLICT (work_order_operation_id) DO NOTHING
"""

INSERT_EXECUTION_STEP_SQL = """
INSERT INTO mes.work_order_operation_steps (
    work_order_operation_step_id,
    work_order_operation_id,
    work_order_id,
    operation_code,
    step_code,
    step_no,
    station_code,
    status,
    required_for_completion,
    records_duration,
    approval_required_after_finish,
    metadata,
    updated_at
) VALUES (
    %(work_order_operation_step_id)s,
    %(work_order_operation_id)s,
    %(work_order_id)s,
    %(operation_code)s,
    %(step_code)s,
    %(step_no)s,
    %(station_code)s,
    %(status)s,
    %(required_for_completion)s,
    %(records_duration)s,
    %(approval_required_after_finish)s,
    %(metadata)s,
    now()
)
ON CONFLICT (work_order_operation_id, step_code) DO NOTHING
"""

SELECT_OPERATION_EVENT_BY_IDEMPOTENCY_KEY_SQL = """
SELECT
    event_id,
    event_time,
    received_at,
    station_code,
    work_order_id,
    work_order_operation_id,
    work_order_operation_step_id,
    operation_code,
    step_code,
    event_source,
    event_type,
    external_event_id,
    idempotency_key,
    payload,
    accepted,
    rejection_reason,
    created_at
FROM mes.operation_events
WHERE idempotency_key = %(idempotency_key)s
LIMIT 1
"""

SELECT_OPERATION_EVENT_BY_EXTERNAL_EVENT_SQL = """
SELECT
    event_id,
    event_time,
    received_at,
    station_code,
    work_order_id,
    work_order_operation_id,
    work_order_operation_step_id,
    operation_code,
    step_code,
    event_source,
    event_type,
    external_event_id,
    idempotency_key,
    payload,
    accepted,
    rejection_reason,
    created_at
FROM mes.operation_events
WHERE station_code = %(station_code)s
  AND event_source = %(event_source)s
  AND external_event_id = %(external_event_id)s
LIMIT 1
"""

INSERT_OPERATION_EVENT_SQL = """
INSERT INTO mes.operation_events (
    event_id,
    event_time,
    station_code,
    work_order_id,
    work_order_operation_id,
    work_order_operation_step_id,
    operation_code,
    step_code,
    event_source,
    event_type,
    external_event_id,
    idempotency_key,
    payload,
    accepted,
    rejection_reason
) VALUES (
    %(event_id)s,
    now(),
    %(station_code)s,
    NULL,
    %(work_order_operation_id)s,
    NULL,
    NULL,
    NULL,
    %(event_source)s,
    %(event_type)s,
    %(external_event_id)s,
    %(idempotency_key)s,
    %(payload)s,
    %(accepted)s,
    %(rejection_reason)s
)
RETURNING
    event_id,
    event_time,
    received_at,
    station_code,
    work_order_id,
    work_order_operation_id,
    work_order_operation_step_id,
    operation_code,
    step_code,
    event_source,
    event_type,
    external_event_id,
    idempotency_key,
    payload,
    accepted,
    rejection_reason,
    created_at
"""

SELECT_OPERATION_BY_ID_SQL = """
SELECT
    work_order_operation_id,
    order_id,
    operation_no,
    operation_code,
    operation_name,
    station_code,
    status,
    planned_quantity,
    good_quantity,
    scrap_quantity,
    uom_code,
    started_at,
    completed_at,
    sequence_no
FROM mes.work_order_operations
WHERE work_order_operation_id = %(work_order_operation_id)s
FOR UPDATE
"""

SELECT_OPERATION_BY_ORDER_SQL = """
SELECT
    work_order_operation_id,
    order_id,
    operation_no,
    operation_code,
    operation_name,
    station_code,
    status,
    planned_quantity,
    good_quantity,
    scrap_quantity,
    uom_code,
    started_at,
    completed_at,
    sequence_no
FROM mes.work_order_operations
WHERE order_id = %(order_id)s
  AND operation_no = %(operation_no)s
FOR UPDATE
"""

SELECT_SUCCESSOR_OPERATION_SQL = """
SELECT
    work_order_operation_id,
    order_id,
    operation_no,
    operation_code,
    operation_name,
    station_code,
    status,
    planned_quantity,
    good_quantity,
    scrap_quantity,
    uom_code,
    started_at,
    completed_at,
    sequence_no
FROM mes.work_order_operations
WHERE order_id = %(order_id)s
  AND sequence_no > %(sequence_no)s
  AND status NOT IN ('completed', 'done', 'cancelled', 'canceled')
ORDER BY sequence_no ASC, operation_no ASC
LIMIT 1
FOR UPDATE
"""

SELECT_OPERATION_QUEUE_SQL = """
SELECT station_queue_pk, status
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND (
      work_order_operation_id = %(work_order_operation_id)s
      OR (
          order_id = %(order_id)s
          AND (work_order_operation_id IS NULL OR work_order_operation_id = %(work_order_operation_id)s)
      )
  )
LIMIT 1
FOR UPDATE
"""

SELECT_ACTIVE_OPERATION_SQL = """
SELECT work_order_operation_id, order_id
FROM mes.work_order_operations
WHERE station_code = %(station_code)s
  AND status IN ('active', 'in_progress')
  AND work_order_operation_id <> %(work_order_operation_id)s
LIMIT 1
"""

UPDATE_OPERATION_STARTED_SQL = """
UPDATE mes.work_order_operations
SET status = 'active',
    started_at = COALESCE(started_at, COALESCE(%(started_at)s::timestamptz, now())),
    updated_at = now()
WHERE work_order_operation_id = %(work_order_operation_id)s
"""

UPDATE_WORK_ORDER_STARTED_SQL = """
UPDATE mes.work_orders
SET status = 'active',
    started_at = COALESCE(started_at, COALESCE(%(started_at)s::timestamptz, now())),
    updated_at = now()
WHERE order_id = %(order_id)s
"""

UPDATE_QUEUE_STARTED_SQL = """
UPDATE mes.station_queue
SET status = 'active',
    work_order_operation_id = %(work_order_operation_id)s,
    updated_at = now()
WHERE station_queue_pk = %(station_queue_pk)s
"""

UPDATE_OPERATION_COMPLETED_SQL = """
UPDATE mes.work_order_operations
SET status = 'completed',
    completed_at = COALESCE(completed_at, COALESCE(%(completed_at)s::timestamptz, now())),
    good_quantity = %(good_quantity)s,
    scrap_quantity = %(scrap_quantity)s,
    updated_at = now()
WHERE work_order_operation_id = %(work_order_operation_id)s
"""

UPDATE_QUEUE_COMPLETED_SQL = """
UPDATE mes.station_queue
SET status = 'completed',
    updated_at = now()
WHERE station_queue_pk = %(station_queue_pk)s
"""

UPDATE_SUCCESSOR_OPERATION_QUEUED_SQL = """
UPDATE mes.work_order_operations
SET status = CASE
        WHEN status IN ('completed', 'done', 'cancelled', 'canceled', 'active', 'in_progress', 'ready')
        THEN status
        ELSE 'queued'
    END,
    updated_at = now()
WHERE work_order_operation_id = %(work_order_operation_id)s
"""

SELECT_SUCCESSOR_QUEUE_BY_OPERATION_SQL = """
SELECT station_queue_pk, status, queue_rank
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND work_order_operation_id = %(work_order_operation_id)s
LIMIT 1
FOR UPDATE
"""

SELECT_SUCCESSOR_LEGACY_QUEUE_SQL = """
SELECT station_queue_pk, status, queue_rank
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND order_id = %(order_id)s
  AND status IN ('queued', 'ready', 'active', 'pending_approval')
  AND (work_order_operation_id IS NULL OR work_order_operation_id = %(work_order_operation_id)s)
LIMIT 1
FOR UPDATE
"""

SELECT_NEXT_QUEUE_RANK_SQL = """
SELECT COALESCE(MAX(queue_rank) + 1, 0) AS queue_rank
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND status IN ('queued', 'ready', 'active', 'pending_approval')
"""

UPDATE_SUCCESSOR_QUEUE_BY_PK_SQL = """
UPDATE mes.station_queue
SET order_id = %(order_id)s,
    work_order_operation_id = %(work_order_operation_id)s,
    queue_rank = %(queue_rank)s,
    status = %(status)s,
    source = %(source)s,
    payload = %(payload)s,
    metadata = metadata || %(metadata)s,
    updated_at = now()
WHERE station_queue_pk = %(station_queue_pk)s
"""

UPDATE_WORK_ORDER_COMPLETED_IF_ALL_DONE_SQL = """
UPDATE mes.work_orders w
SET status = 'completed',
    completed_at = COALESCE(completed_at, COALESCE(%(completed_at)s::timestamptz, now())),
    updated_at = now()
WHERE w.order_id = %(order_id)s
  AND NOT EXISTS (
      SELECT 1
      FROM mes.work_order_operations o
      WHERE o.order_id = w.order_id
        AND o.status NOT IN ('completed', 'done')
  )
"""

INSERT_WORK_ORDER_EVENT_SQL = """
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
    COALESCE(%(event_at)s::timestamptz, now()),
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
    payload = EXCLUDED.payload,
    metadata = mes.work_order_events.metadata || EXCLUDED.metadata
"""

INSERT_OUTBOX_SQL = """
INSERT INTO mes.integration_outbox (
    target_system,
    event_type,
    order_id,
    work_order_operation_id,
    station_code,
    dedupe_key,
    payload,
    status,
    updated_at
) VALUES (
    'mesql',
    %(event_type)s,
    %(order_id)s,
    %(work_order_operation_id)s,
    %(station_code)s,
    %(dedupe_key)s,
    %(payload)s,
    'pending',
    now()
)
ON CONFLICT (dedupe_key) DO UPDATE SET
    payload = EXCLUDED.payload,
    updated_at = now()
RETURNING outbox_id
"""

INSERT_PRODUCTION_COMPLETION_SQL = """
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
    COALESCE(%(completed_at)s::timestamptz, now()),
    %(source_system)s,
    %(source_file)s,
    %(external_ref)s,
    %(payload)s,
    %(metadata)s,
    now()
)
ON CONFLICT (external_ref) WHERE external_ref IS NOT NULL AND btrim(external_ref) <> ''
DO UPDATE SET
    payload = EXCLUDED.payload,
    metadata = mes.production_completions.metadata || EXCLUDED.metadata
"""

SELECT_PENDING_OUTBOX_SQL = """
SELECT
    outbox_id,
    event_type,
    order_id,
    work_order_operation_id,
    station_code,
    dedupe_key,
    payload
FROM mes.integration_outbox
WHERE target_system = 'mesql'
  AND status = 'pending'
ORDER BY created_at
LIMIT %(limit)s
"""

MARK_OUTBOX_PUSHED_SQL = """
UPDATE mes.integration_outbox
SET status = 'pushed',
    pushed_at = now(),
    last_error = NULL,
    updated_at = now()
WHERE outbox_id = %(outbox_id)s
"""

MARK_OUTBOX_ERROR_SQL = """
UPDATE mes.integration_outbox
SET attempt_count = attempt_count + 1,
    last_error = %(last_error)s,
    status = CASE WHEN attempt_count + 1 >= 5 THEN 'failed' ELSE 'pending' END,
    updated_at = now()
WHERE outbox_id = %(outbox_id)s
"""


def _build_work_order_params(item: JsonObject, station_code: str) -> JsonObject:
    order_id = _canonical_order_id(item)
    status = normalize_mesql_status(item.get("order_status") or item.get("status"))
    return {
        "order_id": order_id,
        "erp_type": "MESQL",
        "status": status,
        "product_code": _nullable_text(item.get("product_code")),
        "target_quantity": _target_quantity_for_work_order(item),
        "started_at": item.get("started_at") if status == "active" else None,
        "completed_at": item.get("completed_at") if status == "completed" else None,
        "source_system": MESQL_SOURCE_SYSTEM,
        "source_file": f"/api/v1/mes/stations/{station_code}/queue",
        "external_ref": order_id,
        "payload": _jsonb(dict(item)),
        "metadata": _jsonb(
            {
                "source": "mesql_pull",
                "station_code": station_code,
                "original_order_status": item.get("order_status") or item.get("status"),
            }
        ),
    }


def _build_operation_params(item: JsonObject, station_code: str) -> JsonObject:
    operation = _operation_payload(item)
    operation_no = _operation_no(item)
    operation_station = _station_code(item, station_code)
    operation_status = normalize_mesql_status(operation.get("status") or item.get("queue_status") or item.get("order_status"))
    return {
        "order_id": _canonical_order_id(item),
        "mesql_work_order_operation_id": _nullable_text(operation.get("work_order_operation_id")),
        "operation_no": operation_no,
        "operation_code": _nullable_text(operation.get("operation_code")) or f"OP-{operation_no}",
        "operation_name": _nullable_text(operation.get("operation_name")) or f"Operation {operation_no}",
        "sequence_no": _safe_int(operation.get("sequence_no"), operation_no),
        "station_code": operation_station,
        "status": operation_status,
        "planned_quantity": _planned_quantity(item),
        "good_quantity": _safe_float(operation.get("good_quantity")) or 0,
        "scrap_quantity": _safe_float(operation.get("scrap_quantity")) or 0,
        "uom_code": _nullable_text(operation.get("uom_code") or item.get("uom_code")),
        "payload": _jsonb(dict(operation or item)),
        "metadata": _jsonb(
            {
                "source": "mesql_pull",
                "queue_station_code": station_code,
                "original_operation_status": operation.get("status"),
            }
        ),
    }


def _build_queue_params(item: JsonObject, station_code: str, operation_id: str) -> JsonObject:
    queue_status = normalize_mesql_status(item.get("queue_status") or item.get("order_status"))
    return {
        "station_code": _station_code(item, station_code),
        "order_id": _canonical_order_id(item),
        "work_order_operation_id": operation_id,
        "queue_rank": max(_safe_int(item.get("queue_rank"), 0), 0),
        "status": queue_status,
        "source": "mesql_pull",
        "payload": _jsonb(dict(item)),
        "metadata": _jsonb(
            {
                "source": "mesql_pull",
                "original_queue_status": item.get("queue_status"),
            }
        ),
    }


def _package_rows(item: JsonObject, station_code: str, operation_id: str) -> list[JsonObject]:
    candidates: list[Any] = []
    for key in ("packaging_units", "package_outputs", "packages"):
        value = item.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    raw_order_id = _text(item.get("order_id"))
    if _is_package_order_id(raw_order_id):
        candidates.append(
            {
                "package_no": raw_order_id,
                "product_code": item.get("product_code"),
                "quantity": item.get("planned_quantity") or item.get("target_quantity") or 1,
                "uom_code": item.get("uom_code"),
                "status": item.get("queue_status") or item.get("order_status"),
                "payload": item,
            }
        )
    rows: list[JsonObject] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        package_no = _text(candidate.get("package_no") or candidate.get("packageNo") or candidate.get("package_id") or candidate.get("packageId"))
        if not package_no:
            continue
        rows.append(
            {
                "package_no": package_no,
                "order_id": _canonical_order_id(item),
                "work_order_operation_id": operation_id,
                "station_code": _station_code(candidate, station_code) or _station_code(item, station_code),
                "product_code": _nullable_text(candidate.get("product_code") or candidate.get("productCode") or item.get("product_code")),
                "quantity": _safe_float(candidate.get("quantity") or candidate.get("qty")) or 1,
                "uom_code": _nullable_text(candidate.get("uom_code") or candidate.get("uomCode") or item.get("uom_code")),
                "status": normalize_mesql_status(candidate.get("status"), default="planned"),
                "payload": _jsonb(dict(candidate)),
                "metadata": _jsonb({"source": "mesql_pull"}),
            }
        )
    return rows


def _upsert_queue(cursor: Any, queue_params: JsonObject) -> bool:
    cursor.execute(SELECT_QUEUE_ROW_SQL, queue_params)
    existing = cursor.fetchone()
    cursor.execute(SELECT_ACTIVE_RANK_CONFLICT_SQL, queue_params)
    conflict = cursor.fetchone()
    if conflict:
        if not existing:
            return False
        existing_rank = _safe_int(_field(existing, 3, "queue_rank"), queue_params["queue_rank"])
        queue_params = dict(queue_params)
        queue_params["queue_rank"] = existing_rank
    if existing:
        cursor.execute(UPDATE_QUEUE_SQL, queue_params)
    else:
        cursor.execute(INSERT_QUEUE_SQL, queue_params)
    return True


def upsert_mesql_queue_items(
    config: AppConfig,
    station_payloads: dict[str, list[JsonObject]],
    *,
    dry_run: bool = False,
) -> MesqlPullResult:
    result = MesqlPullResult(pulled_station_count=len(station_payloads), dry_run=dry_run)
    if dry_run:
        for station_code, items in station_payloads.items():
            for item in items:
                if not _text(item.get("order_id")):
                    result.skipped_items += 1
                    result.errors.append({"station_code": station_code, "reason": "missing_order_id", "item": item})
                    continue
                if _is_package_order_id(_text(item.get("order_id"))) and not _canonical_order_id(item):
                    result.skipped_items += 1
                    result.errors.append({"station_code": station_code, "reason": "package_parent_order_missing", "item": item})
                    continue
                result.upserted_work_orders += 1
                result.upserted_operations += 1
                result.upserted_queue_items += 1
                result.upserted_packaging_units += len(_package_rows(item, station_code, "dry-run-operation"))
        return result

    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                for station_code, items in station_payloads.items():
                    for item in items:
                        if not isinstance(item, dict):
                            result.skipped_items += 1
                            result.errors.append({"station_code": station_code, "reason": "invalid_item"})
                            continue
                        order_id = _text(item.get("order_id"))
                        if not order_id:
                            result.skipped_items += 1
                            result.errors.append({"station_code": station_code, "reason": "missing_order_id", "item": item})
                            continue
                        if _is_package_order_id(order_id) and not _canonical_order_id(item):
                            result.skipped_items += 1
                            result.errors.append({"station_code": station_code, "reason": "package_parent_order_missing", "item": item})
                            continue
                        endpoint = f"/api/v1/mes/stations/{station_code}/queue"
                        cursor.execute(
                            UPSERT_INBOX_SQL,
                            {
                                "source_system": MESQL_SOURCE_SYSTEM,
                                "source_endpoint": endpoint,
                                "source_id": order_id,
                                "message_type": "station_queue_item",
                                "dedupe_key": f"mesql:queue:{station_code}:{order_id}:{_operation_no(item)}",
                                "payload": _jsonb(dict(item)),
                            },
                        )
                        cursor.execute(UPSERT_WORK_ORDER_SQL, _build_work_order_params(item, station_code))
                        result.upserted_work_orders += 1
                        cursor.execute(UPSERT_OPERATION_SQL, _build_operation_params(item, station_code))
                        operation_row = cursor.fetchone()
                        operation_id = _text(_field(operation_row, 0, "work_order_operation_id"))
                        result.upserted_operations += 1
                        if not operation_id:
                            result.skipped_items += 1
                            result.errors.append({"station_code": station_code, "order_id": order_id, "reason": "missing_operation_id"})
                            continue
                        if _upsert_queue(cursor, _build_queue_params(item, station_code, operation_id)):
                            result.upserted_queue_items += 1
                        else:
                            result.skipped_items += 1
                            result.errors.append(
                                {
                                    "station_code": station_code,
                                    "order_id": order_id,
                                    "queue_rank": item.get("queue_rank"),
                                    "reason": "active_queue_rank_conflict",
                                }
                            )
                        for package_row in _package_rows(item, station_code, operation_id):
                            cursor.execute(UPSERT_PACKAGING_UNIT_SQL, package_row)
                            result.upserted_packaging_units += 1
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()
    return result


def read_station_queue_v2(config: AppConfig, station_code: str) -> list[JsonObject]:
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_V2_QUEUE_SQL, {"station_code": _upper(station_code)})
            rows = cursor.fetchall()
    return _json_safe([
        {
            "station_code": _field(row, 0, "station_code"),
            "queue_rank": _field(row, 1, "queue_rank"),
            "order_id": _field(row, 2, "order_id"),
            "status": _field(row, 3, "queue_status"),
            "queue_payload": _field(row, 4, "queue_payload") or {},
            "queue_metadata": _field(row, 5, "queue_metadata") or {},
            "product_code": _field(row, 6, "product_code"),
            "target_quantity": _field(row, 7, "target_quantity"),
            "order_status": _field(row, 8, "order_status"),
            "order_started_at": _field(row, 9, "order_started_at"),
            "order_completed_at": _field(row, 10, "order_completed_at"),
            "order_payload": _field(row, 11, "order_payload") or {},
            "order_metadata": _field(row, 12, "order_metadata") or {},
            "work_order_operation_id": _field(row, 13, "work_order_operation_id"),
            "operation_no": _field(row, 14, "operation_no"),
            "operation_code": _field(row, 15, "operation_code"),
            "operation_name": _field(row, 16, "operation_name"),
            "sequence_no": _field(row, 17, "sequence_no"),
            "operation_status": _field(row, 18, "operation_status"),
            "planned_quantity": _field(row, 19, "planned_quantity"),
            "good_quantity": _field(row, 20, "good_quantity"),
            "scrap_quantity": _field(row, 21, "scrap_quantity"),
            "uom_code": _field(row, 22, "uom_code"),
            "started_at": _field(row, 23, "operation_started_at"),
            "completed_at": _field(row, 24, "operation_completed_at"),
            "operation_payload": _field(row, 25, "operation_payload") or {},
            "metadata": _field(row, 26, "operation_metadata") or {},
        }
        for row in rows
    ])


def _location_row(row: Any) -> JsonObject:
    return _json_safe({
        "location_pk": _field(row, 0, "location_pk"),
        "location_id": _field(row, 1, "location_id"),
        "location_code": _upper(_field(row, 2, "location_code")),
        "location_name": _field(row, 3, "location_name"),
        "location_type": _lower(_field(row, 4, "location_type")),
        "parent_location_code": _nullable_upper(_field(row, 5, "parent_location_code")),
        "station_code": _nullable_upper(_field(row, 6, "station_code")),
        "active": _field(row, 7, "active"),
        "source_system": _field(row, 8, "source_system"),
        "source_file": _field(row, 9, "source_file"),
        "external_ref": _field(row, 10, "external_ref"),
        "payload": _field(row, 11, "payload") or {},
        "metadata": _field(row, 12, "metadata") or {},
        "created_at": _field(row, 13, "created_at"),
        "updated_at": _field(row, 14, "updated_at"),
    })


def _joined_location_row(row: Any, *, offset: int = 16) -> JsonObject | None:
    location_pk = _field_any(row, offset, "location_pk")
    if location_pk is None:
        return None
    return _json_safe({
        "location_pk": location_pk,
        "location_id": _field_any(row, offset + 1, "location_id"),
        "location_code": _upper(_field_any(row, offset + 2, "joined_location_code", "location_code")),
        "location_name": _field_any(row, offset + 3, "location_name"),
        "location_type": _lower(_field_any(row, offset + 4, "location_type")),
        "parent_location_code": _nullable_upper(_field_any(row, offset + 5, "parent_location_code")),
        "station_code": _nullable_upper(_field_any(row, offset + 6, "location_station_code", "station_code")),
        "active": _field_any(row, offset + 7, "location_active", "active"),
        "source_system": _field_any(row, offset + 8, "location_source_system", "source_system"),
        "source_file": _field_any(row, offset + 9, "location_source_file", "source_file"),
        "external_ref": _field_any(row, offset + 10, "location_external_ref", "external_ref"),
        "payload": _field_any(row, offset + 11, "location_payload", "payload") or {},
        "metadata": _field_any(row, offset + 12, "location_metadata", "metadata") or {},
        "created_at": _field_any(row, offset + 13, "location_created_at", "created_at"),
        "updated_at": _field_any(row, offset + 14, "location_updated_at", "updated_at"),
    })


def _station_location_binding_row(row: Any) -> JsonObject:
    binding = {
        "binding_pk": _field(row, 0, "binding_pk"),
        "binding_id": _field(row, 1, "binding_id"),
        "station_code": _upper(_field(row, 2, "station_code")),
        "role": _lower(_field(row, 3, "role")),
        "location_code": _upper(_field(row, 4, "location_code")),
        "item_scope": _nullable_text(_field(row, 5, "item_scope")),
        "operation_scope": _nullable_text(_field(row, 6, "operation_scope")),
        "priority": _safe_int(_field(row, 7, "priority"), 100),
        "active": _field(row, 8, "active"),
        "source_system": _field_any(row, 9, "binding_source_system", "source_system"),
        "source_file": _field_any(row, 10, "binding_source_file", "source_file"),
        "external_ref": _field_any(row, 11, "binding_external_ref", "external_ref"),
        "payload": _field_any(row, 12, "binding_payload", "payload") or {},
        "metadata": _field_any(row, 13, "binding_metadata", "metadata") or {},
        "created_at": _field_any(row, 14, "binding_created_at", "created_at"),
        "updated_at": _field_any(row, 15, "binding_updated_at", "updated_at"),
        "location": _joined_location_row(row),
    }
    return _json_safe(binding)


def _item_row(row: Any) -> JsonObject:
    return _json_safe({
        "item_code": _upper(_field(row, 0, "item_code")),
        "item_name": _field(row, 1, "item_name"),
        "item_type": _lower(_field(row, 2, "item_type")),
        "unit": _field(row, 3, "unit"),
        "active": _field(row, 4, "active"),
        "metadata": _field(row, 5, "metadata") or {},
    })


def _process_route_row(row: Any) -> JsonObject:
    return _json_safe({
        "route_code": _upper(_field(row, 0, "route_code")),
        "version": _safe_int(_field(row, 1, "version"), 1),
        "route_name": _field(row, 2, "route_name"),
        "item_code": _upper(_field(row, 3, "item_code")),
        "active": _field(row, 4, "active"),
        "metadata": _field(row, 5, "metadata") or {},
    })


def _route_operation_row(row: Any) -> JsonObject:
    return _json_safe({
        "route_operation_id": _upper(_field(row, 0, "route_operation_id")),
        "route_code": _upper(_field(row, 1, "route_code")),
        "route_version": _safe_int(_field(row, 2, "route_version"), 1),
        "sequence_no": _safe_int(_field(row, 3, "sequence_no"), 0),
        "operation_code": _upper(_field(row, 4, "operation_code")),
        "operation_name": _field(row, 5, "operation_name"),
        "station_code": _upper(_field(row, 6, "station_code")),
        "input_item_code": _upper(_field(row, 7, "input_item_code")),
        "output_item_code": _upper(_field(row, 8, "output_item_code")),
        "input_qty_per_cycle": _field(row, 9, "input_qty_per_cycle"),
        "output_qty_per_cycle": _field(row, 10, "output_qty_per_cycle"),
        "input_location_role": _lower(_field(row, 11, "input_location_role")),
        "output_location_role": _lower(_field(row, 12, "output_location_role")),
        "scrap_location_role": _lower(_field(row, 13, "scrap_location_role")) or None,
        "operation_completion_policy": _lower(_field(row, 14, "operation_completion_policy")),
        "planned_cycle_time_sec": _field(row, 15, "planned_cycle_time_sec"),
        "active": _field(row, 16, "active"),
        "metadata": _field(row, 17, "metadata") or {},
    })


def _station_event_source_row(row: Any) -> JsonObject:
    return _json_safe({
        "station_code": _upper(_field(row, 0, "station_code")),
        "source_code": _upper(_field(row, 1, "source_code")),
        "source_name": _field(row, 2, "source_name"),
        "source_type": _lower(_field(row, 3, "source_type")),
        "event_channel": _lower(_field(row, 4, "event_channel")),
        "mqtt_topic": _field(row, 5, "mqtt_topic"),
        "active": _field(row, 6, "active"),
        "metadata": _field(row, 7, "metadata") or {},
    })


def _operation_step_row(row: Any) -> JsonObject:
    return _json_safe({
        "route_operation_id": _upper(_field(row, 0, "route_operation_id")),
        "operation_code": _upper(_field(row, 1, "operation_code")),
        "step_no": _safe_int(_field(row, 2, "step_no"), 0),
        "step_code": _upper(_field(row, 3, "step_code")),
        "step_name": _field(row, 4, "step_name"),
        "start_mode": _lower(_field(row, 5, "start_mode")),
        "finish_mode": _lower(_field(row, 6, "finish_mode")),
        "start_event_source_code": _nullable_upper(_field(row, 7, "start_event_source_code")),
        "finish_event_source_code": _nullable_upper(_field(row, 8, "finish_event_source_code")),
        "required_for_completion": _field(row, 9, "required_for_completion"),
        "records_duration": _field(row, 10, "records_duration"),
        "approval_required_after_finish": _field(row, 11, "approval_required_after_finish"),
        "actor_type": _lower(_field(row, 12, "actor_type")),
        "active": _field(row, 13, "active"),
        "metadata": _field(row, 14, "metadata") or {},
    })


def _execution_state_row(row: Any) -> JsonObject:
    return _json_safe({
        "execution_state_id": _text(_field(row, 0, "execution_state_id")),
        "work_order_operation_id": _text(_field(row, 1, "work_order_operation_id")),
        "work_order_id": _text(_field(row, 2, "work_order_id")),
        "station_code": _upper(_field(row, 3, "station_code")),
        "operation_code": _upper(_field(row, 4, "operation_code")),
        "execution_status": _lower(_field(row, 5, "execution_status")),
        "operation_completion_policy": _lower(_field(row, 6, "operation_completion_policy")),
        "current_step_code": _nullable_upper(_field(row, 7, "current_step_code")),
        "started_at": _field(row, 8, "started_at"),
        "evidence_completed_at": _field(row, 9, "evidence_completed_at"),
        "pending_final_approval_at": _field(row, 10, "pending_final_approval_at"),
        "closed_at": _field(row, 11, "closed_at"),
        "last_event_id": _field(row, 12, "last_event_id"),
        "last_approval_id": _field(row, 13, "last_approval_id"),
        "created_at": _field(row, 14, "created_at"),
        "updated_at": _field(row, 15, "updated_at"),
        "metadata": _field(row, 16, "metadata") or {},
    })


def _execution_step_row(row: Any) -> JsonObject:
    return _json_safe({
        "work_order_operation_step_id": _text(_field(row, 0, "work_order_operation_step_id")),
        "work_order_operation_id": _text(_field(row, 1, "work_order_operation_id")),
        "work_order_id": _text(_field(row, 2, "work_order_id")),
        "operation_code": _upper(_field(row, 3, "operation_code")),
        "step_code": _upper(_field(row, 4, "step_code")),
        "step_no": _safe_int(_field(row, 5, "step_no"), 0),
        "station_code": _upper(_field(row, 6, "station_code")),
        "status": _lower(_field(row, 7, "status")),
        "started_at": _field(row, 8, "started_at"),
        "completed_at": _field(row, 9, "completed_at"),
        "started_by_event_id": _field(row, 10, "started_by_event_id"),
        "completed_by_event_id": _field(row, 11, "completed_by_event_id"),
        "required_for_completion": _field(row, 12, "required_for_completion"),
        "records_duration": _field(row, 13, "records_duration"),
        "approval_required_after_finish": _field(row, 14, "approval_required_after_finish"),
        "created_at": _field(row, 15, "created_at"),
        "updated_at": _field(row, 16, "updated_at"),
        "metadata": _field(row, 17, "metadata") or {},
    })


def _runtime_operation_context_row(row: Any) -> JsonObject:
    return _json_safe({
        "work_order_operation_id": _text(_field(row, 0, "work_order_operation_id")),
        "work_order_id": _text(_field(row, 1, "order_id")),
        "operation_code": _upper(_field(row, 2, "operation_code")),
        "station_code": _upper(_field(row, 3, "station_code")),
    })


def _operation_event_row(row: Any) -> JsonObject:
    return _json_safe({
        "event_id": _text(_field(row, 0, "event_id")),
        "event_time": _field(row, 1, "event_time"),
        "received_at": _field(row, 2, "received_at"),
        "station_code": _upper(_field(row, 3, "station_code")),
        "work_order_id": _nullable_text(_field(row, 4, "work_order_id")),
        "work_order_operation_id": _nullable_text(_field(row, 5, "work_order_operation_id")),
        "work_order_operation_step_id": _nullable_text(_field(row, 6, "work_order_operation_step_id")),
        "operation_code": _nullable_upper(_field(row, 7, "operation_code")),
        "step_code": _nullable_upper(_field(row, 8, "step_code")),
        "event_source": _upper(_field(row, 9, "event_source")),
        "event_type": _lower(_field(row, 10, "event_type")),
        "external_event_id": _nullable_text(_field(row, 11, "external_event_id")),
        "idempotency_key": _nullable_text(_field(row, 12, "idempotency_key")),
        "payload": _field(row, 13, "payload") or {},
        "accepted": _field(row, 14, "accepted"),
        "rejection_reason": _nullable_text(_field(row, 15, "rejection_reason")),
        "created_at": _field(row, 16, "created_at"),
    })


def list_locations(config: AppConfig, active_only: bool = True, location_type: str | None = None) -> list[JsonObject]:
    params = {
        "active_only": bool(active_only),
        "location_type": _lower(location_type) or None,
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_LOCATIONS_SQL, params)
            rows = cursor.fetchall()
    return [_location_row(row) for row in rows]


def get_location_by_code(config: AppConfig, location_code: str) -> JsonObject | None:
    normalized_code = _upper(location_code)
    if not normalized_code:
        return None
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_LOCATION_BY_CODE_SQL, {"location_code": normalized_code})
            row = cursor.fetchone()
    return _location_row(row) if row else None


def list_station_location_bindings(
    config: AppConfig,
    station_code: str,
    active_only: bool = True,
    role: str | None = None,
) -> list[JsonObject]:
    normalized_station_code = _upper(station_code)
    if not normalized_station_code:
        return []
    params = {
        "station_code": normalized_station_code,
        "active_only": bool(active_only),
        "role": _lower(role) or None,
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_STATION_LOCATION_BINDINGS_SQL, params)
            rows = cursor.fetchall()
    return [_station_location_binding_row(row) for row in rows]


def resolve_station_location(
    config: AppConfig,
    station_code: str,
    role: str,
    item_scope: str | None = None,
    operation_scope: str | None = None,
) -> JsonObject | None:
    normalized_station_code = _upper(station_code)
    normalized_role = _lower(role)
    if not normalized_station_code or not normalized_role:
        return None
    params = {
        "station_code": normalized_station_code,
        "role": normalized_role,
        "item_scope": _nullable_text(item_scope),
        "operation_scope": _nullable_text(operation_scope),
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_RESOLVE_STATION_LOCATION_SQL, params)
            row = cursor.fetchone()
    return _joined_location_row(row) if row else None


def get_station_location_context(config: AppConfig, station_code: str) -> JsonObject:
    normalized_station_code = _upper(station_code)
    bindings = list_station_location_bindings(config, normalized_station_code, active_only=True)
    locations_by_role: dict[str, list[JsonObject]] = {}
    locations_by_code: dict[str, JsonObject] = {}
    inactive_or_missing_locations: list[JsonObject] = []

    for binding in bindings:
        role = _lower(binding.get("role"))
        location = binding.get("location")
        if not isinstance(location, dict):
            inactive_or_missing_locations.append(
                {
                    "role": role,
                    "location_code": binding.get("location_code"),
                    "reason": "missing_location",
                }
            )
            continue
        if location.get("active") is not True:
            inactive_or_missing_locations.append(
                {
                    "role": role,
                    "location_code": binding.get("location_code"),
                    "reason": "inactive_location",
                }
            )
            continue
        locations_by_role.setdefault(role, []).append(location)
        location_code = _upper(location.get("location_code"))
        if location_code:
            locations_by_code.setdefault(location_code, location)

    def first_location(role: str) -> JsonObject | None:
        locations = locations_by_role.get(role, [])
        return locations[0] if locations else None

    required_roles = ("input", "active_wip", "output_good", "output_scrap")
    missing_roles = [role for role in required_roles if first_location(role) is None]

    return _json_safe({
        "station_code": normalized_station_code,
        "bindings": bindings,
        "locations": list(locations_by_code.values()),
        "locations_by_role": locations_by_role,
        "input_location": first_location("input"),
        "active_wip_location": first_location("active_wip"),
        "output_good_location": first_location("output_good"),
        "output_scrap_location": first_location("output_scrap"),
        "output_buffer_location": first_location("output_buffer"),
        "missing_roles": missing_roles,
        "inactive_or_missing_locations": inactive_or_missing_locations,
    })


def list_items(config: AppConfig, active_only: bool = True) -> list[JsonObject]:
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_ITEMS_SQL, {"active_only": bool(active_only)})
            rows = cursor.fetchall()
    return [_item_row(row) for row in rows]


def get_item_by_code(config: AppConfig, item_code: str) -> JsonObject | None:
    normalized_code = _upper(item_code)
    if not normalized_code:
        return None
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_ITEM_BY_CODE_SQL, {"item_code": normalized_code})
            row = cursor.fetchone()
    return _item_row(row) if row else None


def list_process_routes(
    config: AppConfig,
    active_only: bool = True,
    item_code: str | None = None,
) -> list[JsonObject]:
    params = {
        "active_only": bool(active_only),
        "item_code": _nullable_upper(item_code),
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_PROCESS_ROUTES_SQL, params)
            rows = cursor.fetchall()
    return [_process_route_row(row) for row in rows]


def get_process_route(config: AppConfig, route_code: str, version: int = 1) -> JsonObject | None:
    normalized_route_code = _upper(route_code)
    if not normalized_route_code:
        return None
    params = {
        "route_code": normalized_route_code,
        "version": _safe_int(version, 1),
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_PROCESS_ROUTE_SQL, params)
            row = cursor.fetchone()
    return _process_route_row(row) if row else None


def list_route_operations(
    config: AppConfig,
    route_code: str | None = None,
    station_code: str | None = None,
    active_only: bool = True,
) -> list[JsonObject]:
    params = {
        "active_only": bool(active_only),
        "route_code": _nullable_upper(route_code),
        "station_code": _nullable_upper(station_code),
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_ROUTE_OPERATIONS_SQL, params)
            rows = cursor.fetchall()
    return [_route_operation_row(row) for row in rows]


def get_route_operation(config: AppConfig, route_operation_id: str) -> JsonObject | None:
    normalized_route_operation_id = _upper(route_operation_id)
    if not normalized_route_operation_id:
        return None
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(
                SELECT_ROUTE_OPERATION_BY_ID_SQL,
                {"route_operation_id": normalized_route_operation_id},
            )
            row = cursor.fetchone()
    return _route_operation_row(row) if row else None


def list_station_event_sources(
    config: AppConfig,
    station_code: str,
    active_only: bool = True,
) -> list[JsonObject]:
    normalized_station_code = _upper(station_code)
    if not normalized_station_code:
        return []
    params = {
        "station_code": normalized_station_code,
        "active_only": bool(active_only),
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_STATION_EVENT_SOURCES_SQL, params)
            rows = cursor.fetchall()
    return [_station_event_source_row(row) for row in rows]


def resolve_station_event_source(config: AppConfig, station_code: str, source_code: str) -> JsonObject | None:
    normalized_station_code = _upper(station_code)
    normalized_source_code = _upper(source_code)
    if not normalized_station_code or not normalized_source_code:
        return None
    params = {
        "station_code": normalized_station_code,
        "source_code": normalized_source_code,
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_STATION_EVENT_SOURCE_SQL, params)
            row = cursor.fetchone()
    return _station_event_source_row(row) if row else None


def list_operation_steps(
    config: AppConfig,
    route_operation_id: str,
    active_only: bool = True,
) -> list[JsonObject]:
    normalized_route_operation_id = _upper(route_operation_id)
    if not normalized_route_operation_id:
        return []
    params = {
        "route_operation_id": normalized_route_operation_id,
        "active_only": bool(active_only),
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_OPERATION_STEPS_SQL, params)
            rows = cursor.fetchall()
    return [_operation_step_row(row) for row in rows]


def get_operation_step(config: AppConfig, route_operation_id: str, step_code: str) -> JsonObject | None:
    normalized_route_operation_id = _upper(route_operation_id)
    normalized_step_code = _upper(step_code)
    if not normalized_route_operation_id or not normalized_step_code:
        return None
    params = {
        "route_operation_id": normalized_route_operation_id,
        "step_code": normalized_step_code,
    }
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_OPERATION_STEP_SQL, params)
            row = cursor.fetchone()
    return _operation_step_row(row) if row else None


def _station_exists(config: AppConfig, station_code: str) -> bool:
    normalized_station_code = _upper(station_code)
    if not normalized_station_code:
        return False
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_STATION_EXISTS_SQL, {"station_code": normalized_station_code})
            return cursor.fetchone() is not None


def _config_validation() -> JsonObject:
    return {
        "missing_items": [],
        "missing_station": [],
        "missing_event_sources": [],
        "invalid_step_source_refs": [],
        "invalid_auto_mode_refs": [],
    }


def _config_warning(code: str, **values: Any) -> JsonObject:
    warning = {"severity": "warning", "code": code}
    warning.update({key: value for key, value in values.items() if value is not None})
    return _json_safe(warning)


def get_route_operation_config(config: AppConfig, route_operation_id: str) -> JsonObject | None:
    normalized_route_operation_id = _upper(route_operation_id)
    if not normalized_route_operation_id:
        return None

    route_operation = get_route_operation(config, normalized_route_operation_id)
    if route_operation is None:
        return None

    input_item_code = _upper(route_operation.get("input_item_code"))
    output_item_code = _upper(route_operation.get("output_item_code"))
    station_code = _upper(route_operation.get("station_code"))

    input_item = get_item_by_code(config, input_item_code) if input_item_code else None
    output_item = get_item_by_code(config, output_item_code) if output_item_code else None
    steps = list_operation_steps(config, normalized_route_operation_id, active_only=True)
    event_sources = list_station_event_sources(config, station_code, active_only=True)

    validation = _config_validation()
    if input_item is None:
        validation["missing_items"].append(
            _config_warning(
                "MISSING_INPUT_ITEM",
                route_operation_id=normalized_route_operation_id,
                field="input_item_code",
                item_code=input_item_code,
            )
        )
    if output_item is None:
        validation["missing_items"].append(
            _config_warning(
                "MISSING_OUTPUT_ITEM",
                route_operation_id=normalized_route_operation_id,
                field="output_item_code",
                item_code=output_item_code,
            )
        )
    if not _station_exists(config, station_code):
        validation["missing_station"].append(
            _config_warning(
                "MISSING_STATION",
                route_operation_id=normalized_route_operation_id,
                station_code=station_code,
            )
        )

    source_codes = {_upper(source.get("source_code")) for source in event_sources}
    for step in steps:
        step_code = _upper(step.get("step_code"))
        for field in ("start_event_source_code", "finish_event_source_code"):
            source_code = _upper(step.get(field))
            if source_code and source_code not in source_codes:
                warning = _config_warning(
                    "MISSING_EVENT_SOURCE",
                    route_operation_id=normalized_route_operation_id,
                    step_code=step_code,
                    field=field,
                    source_code=source_code,
                )
                validation["missing_event_sources"].append(warning)
                validation["invalid_step_source_refs"].append(warning)
        if _lower(step.get("start_mode")) == "auto_start" and not _upper(step.get("start_event_source_code")):
            validation["invalid_auto_mode_refs"].append(
                _config_warning(
                    "AUTO_START_REQUIRES_SOURCE",
                    route_operation_id=normalized_route_operation_id,
                    step_code=step_code,
                    field="start_event_source_code",
                )
            )
        if _lower(step.get("finish_mode")) == "auto_finish" and not _upper(step.get("finish_event_source_code")):
            validation["invalid_auto_mode_refs"].append(
                _config_warning(
                    "AUTO_FINISH_REQUIRES_SOURCE",
                    route_operation_id=normalized_route_operation_id,
                    step_code=step_code,
                    field="finish_event_source_code",
                )
            )

    return _json_safe({
        "route_operation": route_operation,
        "input_item": input_item,
        "output_item": output_item,
        "steps": steps,
        "event_sources": event_sources,
        "validation": validation,
    })


def get_station_execution_config(config: AppConfig, station_code: str) -> JsonObject:
    normalized_station_code = _upper(station_code)
    if not normalized_station_code:
        return {
            "station_code": None,
            "route_operations": [],
            "event_sources": [],
            "validation": {"missing_station": []},
        }

    event_sources = list_station_event_sources(config, normalized_station_code, active_only=True)
    route_operations = list_route_operations(config, station_code=normalized_station_code, active_only=True)
    operation_configs = [
        operation_config
        for operation in route_operations
        for operation_config in [get_route_operation_config(config, _upper(operation.get("route_operation_id")))]
        if operation_config is not None
    ]
    validation = {"missing_station": []}
    if not _station_exists(config, normalized_station_code):
        validation["missing_station"].append(
            _config_warning("MISSING_STATION", station_code=normalized_station_code)
        )

    return _json_safe({
        "station_code": normalized_station_code,
        "route_operations": operation_configs,
        "event_sources": event_sources,
        "validation": validation,
    })


def get_execution_state(config: AppConfig, work_order_operation_id: str) -> JsonObject | None:
    normalized_operation_id = _text(work_order_operation_id)
    if not normalized_operation_id:
        return None
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(
                SELECT_EXECUTION_STATE_SQL,
                {"work_order_operation_id": normalized_operation_id},
            )
            row = cursor.fetchone()
    return _execution_state_row(row) if row else None


def list_execution_steps(config: AppConfig, work_order_operation_id: str) -> list[JsonObject]:
    normalized_operation_id = _text(work_order_operation_id)
    if not normalized_operation_id:
        return []
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(
                SELECT_EXECUTION_STEPS_SQL,
                {"work_order_operation_id": normalized_operation_id},
            )
            rows = cursor.fetchall()
    return [_execution_step_row(row) for row in rows]


def _config_validation_has_critical_warnings(validation: JsonObject) -> bool:
    for key in (
        "missing_items",
        "missing_station",
        "missing_event_sources",
        "invalid_step_source_refs",
        "invalid_auto_mode_refs",
    ):
        value = validation.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _assert_route_operation_config_valid(route_operation_config: JsonObject) -> None:
    validation = route_operation_config.get("validation")
    if isinstance(validation, dict) and _config_validation_has_critical_warnings(validation):
        raise MesqlV2Error("ROUTE_OPERATION_CONFIG_INVALID", status_code=409)


def _runtime_record_id(prefix: str, *parts: Any) -> str:
    normalized_parts = [_text(part) for part in parts if _text(part)]
    return "_".join([prefix, *normalized_parts])


def initialize_execution_state(
    config: AppConfig,
    work_order_operation_id: str,
    route_operation_id: str,
    station_code: str,
    actor_id: str | None = None,
) -> JsonObject:
    normalized_operation_id = _text(work_order_operation_id)
    normalized_route_operation_id = _upper(route_operation_id)
    normalized_station_code = _upper(station_code)
    normalized_actor_id = _nullable_text(actor_id)
    if not normalized_operation_id or not normalized_route_operation_id or not normalized_station_code:
        raise MesqlV2Error("RUNTIME_IDENTIFIER_REQUIRED", status_code=400)

    route_operation_config = get_route_operation_config(config, normalized_route_operation_id)
    if route_operation_config is None:
        raise MesqlV2Error("ROUTE_OPERATION_NOT_FOUND", status_code=404)
    _assert_route_operation_config_valid(route_operation_config)

    route_operation = route_operation_config["route_operation"]
    if _upper(route_operation.get("station_code")) != normalized_station_code:
        raise MesqlV2Error("ROUTE_OPERATION_STATION_MISMATCH", status_code=409)

    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                cursor.execute(
                    SELECT_RUNTIME_WORK_ORDER_OPERATION_SQL,
                    {"work_order_operation_id": normalized_operation_id},
                )
                operation_context_row = cursor.fetchone()
                if not operation_context_row:
                    raise MesqlV2Error("WORK_ORDER_OPERATION_NOT_FOUND", status_code=404)
                operation_context = _runtime_operation_context_row(operation_context_row)
                if _upper(operation_context.get("station_code")) != normalized_station_code:
                    raise MesqlV2Error("WORK_ORDER_OPERATION_STATION_MISMATCH", status_code=409)

                cursor.execute(
                    SELECT_EXECUTION_STATE_FOR_UPDATE_SQL,
                    {"work_order_operation_id": normalized_operation_id},
                )
                existing_state = cursor.fetchone()
                initialized = existing_state is None

                if initialized:
                    state_metadata = {
                        "source": "runtime_engine_v0_phase1",
                        "route_operation_id": normalized_route_operation_id,
                    }
                    if normalized_actor_id:
                        state_metadata["actor_id"] = normalized_actor_id
                    cursor.execute(
                        INSERT_EXECUTION_STATE_SQL,
                        {
                            "execution_state_id": _runtime_record_id("EXEC_STATE", normalized_operation_id),
                            "work_order_operation_id": normalized_operation_id,
                            "work_order_id": operation_context["work_order_id"],
                            "station_code": normalized_station_code,
                            "operation_code": _upper(route_operation.get("operation_code")),
                            "execution_status": "ready",
                            "operation_completion_policy": _lower(route_operation.get("operation_completion_policy")),
                            "current_step_code": None,
                            "metadata": _jsonb(state_metadata),
                        },
                    )

                    for step in route_operation_config.get("steps", []):
                        step_code = _upper(step.get("step_code"))
                        if not step_code:
                            continue
                        step_metadata = {
                            "source": "runtime_engine_v0_phase1",
                            "route_operation_id": normalized_route_operation_id,
                            "operation_step_metadata": step.get("metadata") or {},
                        }
                        cursor.execute(
                            INSERT_EXECUTION_STEP_SQL,
                            {
                                "work_order_operation_step_id": _runtime_record_id(
                                    "EXEC_STEP",
                                    normalized_operation_id,
                                    step_code,
                                ),
                                "work_order_operation_id": normalized_operation_id,
                                "work_order_id": operation_context["work_order_id"],
                                "operation_code": _upper(route_operation.get("operation_code")),
                                "step_code": step_code,
                                "step_no": _safe_int(step.get("step_no"), 0),
                                "station_code": normalized_station_code,
                                "status": "pending",
                                "required_for_completion": bool(step.get("required_for_completion")),
                                "records_duration": bool(step.get("records_duration")),
                                "approval_required_after_finish": bool(step.get("approval_required_after_finish")),
                                "metadata": _jsonb(step_metadata),
                            },
                        )

                cursor.execute(
                    SELECT_EXECUTION_STATE_SQL,
                    {"work_order_operation_id": normalized_operation_id},
                )
                state_row = cursor.fetchone()
                cursor.execute(
                    SELECT_EXECUTION_STEPS_SQL,
                    {"work_order_operation_id": normalized_operation_id},
                )
                step_rows = cursor.fetchall()

        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

    return _json_safe({
        "status": "ok",
        "work_order_operation_id": normalized_operation_id,
        "route_operation_id": normalized_route_operation_id,
        "station_code": normalized_station_code,
        "initialized": initialized,
        "execution_state": _execution_state_row(state_row) if state_row else None,
        "steps": [_execution_step_row(row) for row in step_rows],
    })


OPERATION_EVENT_TYPES = {
    "step_start",
    "step_finish",
    "evidence",
    "approval",
    "reject",
    "system_transition",
}


def _normalize_operation_event_type(event_type: Any) -> str:
    normalized_event_type = _lower(event_type)
    if normalized_event_type not in OPERATION_EVENT_TYPES:
        raise MesqlV2Error("INVALID_OPERATION_EVENT_TYPE", status_code=400)
    return normalized_event_type


def _build_operation_event_idempotency_key(
    station_code: str,
    event_source: str,
    external_event_id: str | None,
) -> str | None:
    normalized_external_event_id = _nullable_text(external_event_id)
    if not normalized_external_event_id:
        return None
    return f"{_upper(station_code)}:{_upper(event_source)}:{normalized_external_event_id}"


def get_operation_event_by_idempotency_key(config: AppConfig, idempotency_key: str) -> JsonObject | None:
    normalized_idempotency_key = _nullable_text(idempotency_key)
    if not normalized_idempotency_key:
        return None
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(
                SELECT_OPERATION_EVENT_BY_IDEMPOTENCY_KEY_SQL,
                {"idempotency_key": normalized_idempotency_key},
            )
            row = cursor.fetchone()
    return _operation_event_row(row) if row else None


def get_operation_event_by_external_event(
    config: AppConfig,
    station_code: str,
    event_source: str,
    external_event_id: str,
) -> JsonObject | None:
    normalized_station_code = _upper(station_code)
    normalized_event_source = _upper(event_source)
    normalized_external_event_id = _nullable_text(external_event_id)
    if not normalized_station_code or not normalized_event_source or not normalized_external_event_id:
        return None
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(
                SELECT_OPERATION_EVENT_BY_EXTERNAL_EVENT_SQL,
                {
                    "station_code": normalized_station_code,
                    "event_source": normalized_event_source,
                    "external_event_id": normalized_external_event_id,
                },
            )
            row = cursor.fetchone()
    return _operation_event_row(row) if row else None


def record_operation_event(
    config: AppConfig,
    *,
    work_order_operation_id: str,
    station_code: str,
    event_source: str,
    event_type: str,
    external_event_id: str | None = None,
    idempotency_key: str | None = None,
    actor_id: str | None = None,
    payload: JsonObject | None = None,
    accepted: bool = True,
    rejection_reason: str | None = None,
) -> JsonObject:
    normalized_operation_id = _text(work_order_operation_id)
    normalized_station_code = _upper(station_code)
    normalized_event_source = _upper(event_source)
    if not normalized_operation_id or not normalized_station_code or not normalized_event_source or not _text(event_type):
        raise MesqlV2Error("OPERATION_EVENT_IDENTIFIER_REQUIRED", status_code=400)

    normalized_event_type = _normalize_operation_event_type(event_type)
    normalized_external_event_id = _nullable_text(external_event_id)
    normalized_idempotency_key = _nullable_text(idempotency_key)
    if not normalized_idempotency_key:
        normalized_idempotency_key = _build_operation_event_idempotency_key(
            normalized_station_code,
            normalized_event_source,
            normalized_external_event_id,
        )
    if not normalized_idempotency_key:
        raise MesqlV2Error("OPERATION_EVENT_IDEMPOTENCY_REQUIRED", status_code=400)

    normalized_rejection_reason = _nullable_text(rejection_reason)
    if not accepted and not normalized_rejection_reason:
        raise MesqlV2Error("OPERATION_EVENT_REJECTION_REASON_REQUIRED", status_code=400)

    existing = get_operation_event_by_idempotency_key(config, normalized_idempotency_key)
    if existing is None and normalized_external_event_id:
        existing = get_operation_event_by_external_event(
            config,
            normalized_station_code,
            normalized_event_source,
            normalized_external_event_id,
        )
    if existing is not None:
        return _json_safe({"status": "ok", "inserted": False, "event": existing})

    event_payload = dict(payload or {})
    normalized_actor_id = _nullable_text(actor_id)
    if normalized_actor_id:
        event_payload.setdefault("actor_id", normalized_actor_id)

    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                cursor.execute(
                    INSERT_OPERATION_EVENT_SQL,
                    {
                        "event_id": _runtime_record_id("OP_EVENT", normalized_idempotency_key),
                        "work_order_operation_id": normalized_operation_id,
                        "station_code": normalized_station_code,
                        "event_source": normalized_event_source,
                        "event_type": normalized_event_type,
                        "external_event_id": normalized_external_event_id,
                        "idempotency_key": normalized_idempotency_key,
                        "payload": _jsonb(event_payload),
                        "accepted": bool(accepted),
                        "rejection_reason": normalized_rejection_reason,
                    },
                )
                inserted_row = cursor.fetchone()
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

    return _json_safe({
        "status": "ok",
        "inserted": True,
        "event": _operation_event_row(inserted_row) if inserted_row else None,
    })


def _operation_row(row: Any) -> JsonObject:
    return {
        "work_order_operation_id": _text(_field(row, 0, "work_order_operation_id")),
        "order_id": _text(_field(row, 1, "order_id")),
        "operation_no": _safe_int(_field(row, 2, "operation_no"), 0),
        "operation_code": _text(_field(row, 3, "operation_code")),
        "operation_name": _text(_field(row, 4, "operation_name")),
        "station_code": _upper(_field(row, 5, "station_code")),
        "status": _text(_field(row, 6, "status")).lower(),
        "planned_quantity": _field(row, 7, "planned_quantity"),
        "good_quantity": _field(row, 8, "good_quantity"),
        "scrap_quantity": _field(row, 9, "scrap_quantity"),
        "uom_code": _field(row, 10, "uom_code"),
        "started_at": _field(row, 11, "started_at"),
        "completed_at": _field(row, 12, "completed_at"),
        "sequence_no": _safe_int(_field(row, 13, "sequence_no"), _safe_int(_field(row, 2, "operation_no"), 0)),
    }


def _operation_from_cursor(cursor: Any, params: JsonObject) -> JsonObject:
    if params.get("work_order_operation_id"):
        cursor.execute(SELECT_OPERATION_BY_ID_SQL, params)
    else:
        cursor.execute(SELECT_OPERATION_BY_ORDER_SQL, params)
    row = cursor.fetchone()
    if not row:
        raise MesqlV2Error("OPERATION_NOT_FOUND", status_code=404)
    return _operation_row(row)


def _successor_operation_from_cursor(cursor: Any, operation: JsonObject) -> JsonObject | None:
    cursor.execute(
        SELECT_SUCCESSOR_OPERATION_SQL,
        {
            "order_id": operation["order_id"],
            "sequence_no": _safe_int(operation.get("sequence_no"), operation["operation_no"]),
        },
    )
    row = cursor.fetchone()
    return _operation_row(row) if row else None


def _operation_queue_from_cursor(cursor: Any, operation: JsonObject) -> JsonObject:
    cursor.execute(
        SELECT_OPERATION_QUEUE_SQL,
        {
            "station_code": operation["station_code"],
            "work_order_operation_id": operation["work_order_operation_id"],
            "order_id": operation["order_id"],
        },
    )
    row = cursor.fetchone()
    if not row:
        raise MesqlV2Error("STATION_QUEUE_ITEM_NOT_FOUND", status_code=404)
    return {"station_queue_pk": _field(row, 0, "station_queue_pk"), "status": _text(_field(row, 1, "status")).lower()}


def _assert_no_other_active_operation(cursor: Any, operation: JsonObject) -> None:
    cursor.execute(
        SELECT_ACTIVE_OPERATION_SQL,
        {
            "station_code": operation["station_code"],
            "work_order_operation_id": operation["work_order_operation_id"],
        },
    )
    active = cursor.fetchone()
    if active:
        raise MesqlV2Error("STATION_ACTIVE_OPERATION_CONFLICT", status_code=409)


def _successor_queue_status(operation: JsonObject) -> str:
    status = _text(operation.get("status")).lower()
    if status in ACTIVE_OPERATION_STATUSES:
        return "active"
    if status == "ready":
        return "ready"
    return "queued"


def _next_queue_rank(cursor: Any, station_code: str) -> int:
    cursor.execute(SELECT_NEXT_QUEUE_RANK_SQL, {"station_code": station_code})
    row = cursor.fetchone()
    return _safe_int(_field(row, 0, "queue_rank"), 0)


def _successor_queue_params(cursor: Any, operation: JsonObject) -> JsonObject:
    station_code = _upper(operation.get("station_code"))
    return {
        "station_code": station_code,
        "order_id": operation["order_id"],
        "work_order_operation_id": operation["work_order_operation_id"],
        "queue_rank": _next_queue_rank(cursor, station_code),
        "status": _successor_queue_status(operation),
        "source": "local_successor_activation",
        "payload": _jsonb(
            {
                "order_id": operation["order_id"],
                "work_order_operation_id": operation["work_order_operation_id"],
                "operation_no": operation["operation_no"],
                "sequence_no": operation["sequence_no"],
                "station_code": station_code,
                "status": _successor_queue_status(operation),
            }
        ),
        "metadata": _jsonb({"source": "local_successor_activation"}),
    }


def _upsert_successor_queue(cursor: Any, operation: JsonObject) -> None:
    params = _successor_queue_params(cursor, operation)
    cursor.execute(SELECT_SUCCESSOR_QUEUE_BY_OPERATION_SQL, params)
    existing = cursor.fetchone()
    if not existing:
        cursor.execute(SELECT_SUCCESSOR_LEGACY_QUEUE_SQL, params)
        existing = cursor.fetchone()
    if existing:
        update_params = dict(params)
        update_params["station_queue_pk"] = _field(existing, 0, "station_queue_pk")
        update_params["queue_rank"] = _safe_int(_field(existing, 2, "queue_rank"), params["queue_rank"])
        existing_status = _text(_field(existing, 1, "status")).lower()
        if existing_status in {"active", "ready"}:
            update_params["status"] = existing_status
        cursor.execute(UPDATE_SUCCESSOR_QUEUE_BY_PK_SQL, update_params)
        return
    cursor.execute(INSERT_QUEUE_SQL, params)


def _activate_successor_operation(cursor: Any, operation: JsonObject) -> bool:
    status = _text(operation.get("status")).lower()
    if status in COMPLETED_OPERATION_STATUSES | {"cancelled", "canceled"}:
        return False
    cursor.execute(
        UPDATE_SUCCESSOR_OPERATION_QUEUED_SQL,
        {"work_order_operation_id": operation["work_order_operation_id"]},
    )
    queued_operation = dict(operation)
    if status not in ACTIVE_OPERATION_STATUSES | {"ready"}:
        queued_operation["status"] = "queued"
    _upsert_successor_queue(cursor, queued_operation)
    return True


def _insert_event(cursor: Any, *, event_type: str, event_at: Any, actor_id: str, operation: JsonObject, payload: JsonObject) -> None:
    cursor.execute(
        INSERT_WORK_ORDER_EVENT_SQL,
        {
            "order_id": operation["order_id"],
            "event_type": event_type,
            "event_at": event_at,
            "actor_id": actor_id or None,
            "source_system": SOURCE_SYSTEM,
            "source_file": "mesql_v2",
            "external_ref": f"v2:{event_type.lower()}:{operation['work_order_operation_id']}",
            "payload": _jsonb(payload),
            "metadata": _jsonb({"source": "mesql_v2", "work_order_operation_id": operation["work_order_operation_id"]}),
        },
    )


def _insert_outbox(cursor: Any, *, event_type: str, operation: JsonObject, payload: JsonObject) -> str:
    dedupe_key = f"mesql:{event_type}:{operation['work_order_operation_id']}"
    cursor.execute(
        INSERT_OUTBOX_SQL,
        {
            "event_type": event_type,
            "order_id": operation["order_id"],
            "work_order_operation_id": operation["work_order_operation_id"],
            "station_code": operation["station_code"],
            "dedupe_key": dedupe_key,
            "payload": _jsonb(payload),
        },
    )
    row = cursor.fetchone()
    return _text(_field(row, 0, "outbox_id"))


def start_operation_v2(
    config: AppConfig,
    *,
    station_code: str,
    work_order_operation_id: str | None = None,
    order_id: str | None = None,
    operation_no: int | None = None,
    actor_id: str = "",
    started_at: str | None = None,
) -> JsonObject:
    params = {
        "work_order_operation_id": _nullable_text(work_order_operation_id),
        "order_id": _nullable_text(order_id),
        "operation_no": operation_no,
    }
    if not params["work_order_operation_id"] and (not params["order_id"] or not params["operation_no"]):
        raise MesqlV2Error("OPERATION_IDENTIFIER_REQUIRED", status_code=400)
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                operation = _operation_from_cursor(cursor, params)
                if operation["station_code"] != _upper(station_code):
                    raise MesqlV2Error("OPERATION_STATION_MISMATCH", status_code=409)
                if operation["status"] not in READY_OPERATION_STATUSES | ACTIVE_OPERATION_STATUSES:
                    raise MesqlV2Error("OPERATION_NOT_STARTABLE", status_code=409)
                queue_row = _operation_queue_from_cursor(cursor, operation)
                if queue_row["status"] not in {"queued", "ready", "active"}:
                    raise MesqlV2Error("QUEUE_ITEM_NOT_STARTABLE", status_code=409)
                _assert_no_other_active_operation(cursor, operation)
                transition_started_at = _transition_timestamp(started_at)
                request_payload = {
                    "order_id": operation["order_id"],
                    "operation_no": operation["operation_no"],
                    "operator_id": actor_id or "operator_mvp",
                    "station_code": operation["station_code"],
                    "started_at": transition_started_at,
                }
                cursor.execute(
                    UPDATE_OPERATION_STARTED_SQL,
                    {
                        "work_order_operation_id": operation["work_order_operation_id"],
                        "started_at": transition_started_at,
                    },
                )
                cursor.execute(UPDATE_WORK_ORDER_STARTED_SQL, {"order_id": operation["order_id"], "started_at": transition_started_at})
                cursor.execute(
                    UPDATE_QUEUE_STARTED_SQL,
                    {
                        "station_queue_pk": queue_row["station_queue_pk"],
                        "work_order_operation_id": operation["work_order_operation_id"],
                    },
                )
                event_payload = {"operation": operation, "mesql_request": request_payload}
                _insert_event(cursor, event_type="OPERATION_STARTED", event_at=transition_started_at, actor_id=actor_id, operation=operation, payload=event_payload)
                outbox_id = _insert_outbox(
                    cursor,
                    event_type="operation_started",
                    operation=operation,
                    payload={
                        "mesql_endpoint": "/api/v1/mes/operations/start",
                        "mesql_request": request_payload,
                        "operation": operation,
                    },
                )
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()
    return _json_safe({
        "status": "ok",
        "order_id": operation["order_id"],
        "work_order_operation_id": operation["work_order_operation_id"],
        "station_code": operation["station_code"],
        "operation_status": "active",
        "outbox_id": outbox_id,
    })


def complete_operation_v2(
    config: AppConfig,
    *,
    station_code: str,
    work_order_operation_id: str,
    good_quantity: float,
    scrap_quantity: float = 0,
    actor_id: str = "",
    classification: str = "good",
    metadata: JsonObject | None = None,
    completed_at: str | None = None,
) -> JsonObject:
    if good_quantity < 0 or scrap_quantity < 0:
        raise MesqlV2Error("INVALID_QUANTITY", status_code=400)
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                operation = _operation_from_cursor(cursor, {"work_order_operation_id": work_order_operation_id})
                if operation["station_code"] != _upper(station_code):
                    raise MesqlV2Error("OPERATION_STATION_MISMATCH", status_code=409)
                if operation["status"] not in ACTIVE_OPERATION_STATUSES | COMPLETED_OPERATION_STATUSES:
                    raise MesqlV2Error("OPERATION_NOT_COMPLETABLE", status_code=409)
                queue_row = _operation_queue_from_cursor(cursor, operation)
                transition_completed_at = _transition_timestamp(completed_at)
                request_payload = {
                    "order_id": operation["order_id"],
                    "operation_no": operation["operation_no"],
                    "operator_id": actor_id or "operator_mvp",
                    "station_code": operation["station_code"],
                    "good_quantity": good_quantity,
                    "scrap_quantity": scrap_quantity,
                    "uom_code": operation.get("uom_code"),
                    "completed_at": transition_completed_at,
                }
                cursor.execute(
                    UPDATE_OPERATION_COMPLETED_SQL,
                    {
                        "work_order_operation_id": operation["work_order_operation_id"],
                        "good_quantity": good_quantity,
                        "scrap_quantity": scrap_quantity,
                        "completed_at": transition_completed_at,
                    },
                )
                cursor.execute(UPDATE_QUEUE_COMPLETED_SQL, {"station_queue_pk": queue_row["station_queue_pk"]})
                successor_operation = _successor_operation_from_cursor(cursor, operation)
                successor_activated = bool(successor_operation and _activate_successor_operation(cursor, successor_operation))
                if not successor_activated:
                    cursor.execute(UPDATE_WORK_ORDER_COMPLETED_IF_ALL_DONE_SQL, {"order_id": operation["order_id"], "completed_at": transition_completed_at})
                event_payload = {
                    "operation": operation,
                    "good_quantity": good_quantity,
                    "scrap_quantity": scrap_quantity,
                    "classification": classification,
                    "metadata": metadata or {},
                    "mesql_request": request_payload,
                }
                cursor.execute(
                    INSERT_PRODUCTION_COMPLETION_SQL,
                    {
                        "order_id": operation["order_id"],
                        "item_id": operation["work_order_operation_id"],
                        "classification": classification,
                        "completed_at": transition_completed_at,
                        "source_system": SOURCE_SYSTEM,
                        "source_file": "mesql_v2",
                        "external_ref": f"v2:operation_completed:{operation['work_order_operation_id']}",
                        "payload": _jsonb(event_payload),
                        "metadata": _jsonb({"source": "mesql_v2", **(metadata or {})}),
                    },
                )
                _insert_event(cursor, event_type="OPERATION_COMPLETED", event_at=transition_completed_at, actor_id=actor_id, operation=operation, payload=event_payload)
                outbox_id = _insert_outbox(
                    cursor,
                    event_type="operation_completed",
                    operation=operation,
                    payload={
                        "mesql_endpoint": "/api/v1/mes/operations/complete",
                        "mesql_request": request_payload,
                        "operation": operation,
                    },
                )
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()
    return _json_safe({
        "status": "ok",
        "order_id": operation["order_id"],
        "work_order_operation_id": operation["work_order_operation_id"],
        "station_code": operation["station_code"],
        "operation_status": "completed",
        "outbox_id": outbox_id,
    })


def pending_outbox_events(config: AppConfig, *, limit: int = 50) -> list[PendingOutboxEvent]:
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(SELECT_PENDING_OUTBOX_SQL, {"limit": max(1, min(int(limit), 500))})
            rows = cursor.fetchall()
    return [
        PendingOutboxEvent(
            outbox_id=_text(_field(row, 0, "outbox_id")),
            event_type=_text(_field(row, 1, "event_type")),
            order_id=_nullable_text(_field(row, 2, "order_id")),
            work_order_operation_id=_nullable_text(_field(row, 3, "work_order_operation_id")),
            station_code=_nullable_text(_field(row, 4, "station_code")),
            dedupe_key=_text(_field(row, 5, "dedupe_key")),
            payload=_json_safe(dict(_field(row, 6, "payload") or {})),
        )
        for row in rows
    ]


def mark_outbox_pushed(config: AppConfig, outbox_id: str) -> None:
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(MARK_OUTBOX_PUSHED_SQL, {"outbox_id": outbox_id})
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()


def mark_outbox_error(config: AppConfig, outbox_id: str, error: str) -> None:
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            cursor.execute(MARK_OUTBOX_ERROR_SQL, {"outbox_id": outbox_id, "last_error": error[:1000]})
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

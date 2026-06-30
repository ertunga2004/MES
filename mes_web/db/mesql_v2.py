from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any

from ..config import AppConfig
from .connection import database_connection


JsonObject = dict[str, Any]

SOURCE_SYSTEM = "mes_web"
MESQL_SOURCE_SYSTEM = "mesql"

READY_OPERATION_STATUSES = {"queued", "ready"}
ACTIVE_OPERATION_STATUSES = {"active", "in_progress"}
COMPLETED_OPERATION_STATUSES = {"completed", "done"}


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
        return {
            "pulled_station_count": self.pulled_station_count,
            "upserted_work_orders": self.upserted_work_orders,
            "upserted_operations": self.upserted_operations,
            "upserted_queue_items": self.upserted_queue_items,
            "upserted_packaging_units": self.upserted_packaging_units,
            "skipped_items": self.skipped_items,
            "errors": list(self.errors),
            "dry_run": self.dry_run,
        }


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
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        return value
    return Jsonb(value)


def _field(row: Any, index: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, (list, tuple)) and len(row) > index:
        return row[index]
    return None


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
    completed_at
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
    completed_at
FROM mes.work_order_operations
WHERE order_id = %(order_id)s
  AND operation_no = %(operation_no)s
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
    return [
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
    ]


def _operation_from_cursor(cursor: Any, params: JsonObject) -> JsonObject:
    if params.get("work_order_operation_id"):
        cursor.execute(SELECT_OPERATION_BY_ID_SQL, params)
    else:
        cursor.execute(SELECT_OPERATION_BY_ORDER_SQL, params)
    row = cursor.fetchone()
    if not row:
        raise MesqlV2Error("OPERATION_NOT_FOUND", status_code=404)
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
    }


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
                request_payload = {
                    "order_id": operation["order_id"],
                    "operation_no": operation["operation_no"],
                    "operator_id": actor_id or "operator_mvp",
                    "station_code": operation["station_code"],
                    "started_at": started_at,
                }
                cursor.execute(
                    UPDATE_OPERATION_STARTED_SQL,
                    {
                        "work_order_operation_id": operation["work_order_operation_id"],
                        "started_at": started_at,
                    },
                )
                cursor.execute(UPDATE_WORK_ORDER_STARTED_SQL, {"order_id": operation["order_id"], "started_at": started_at})
                cursor.execute(
                    UPDATE_QUEUE_STARTED_SQL,
                    {
                        "station_queue_pk": queue_row["station_queue_pk"],
                        "work_order_operation_id": operation["work_order_operation_id"],
                    },
                )
                event_payload = {"operation": operation, "mesql_request": request_payload}
                _insert_event(cursor, event_type="OPERATION_STARTED", event_at=started_at, actor_id=actor_id, operation=operation, payload=event_payload)
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
    return {
        "status": "ok",
        "order_id": operation["order_id"],
        "work_order_operation_id": operation["work_order_operation_id"],
        "station_code": operation["station_code"],
        "operation_status": "active",
        "outbox_id": outbox_id,
    }


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
                request_payload = {
                    "order_id": operation["order_id"],
                    "operation_no": operation["operation_no"],
                    "operator_id": actor_id or "operator_mvp",
                    "station_code": operation["station_code"],
                    "good_quantity": good_quantity,
                    "scrap_quantity": scrap_quantity,
                    "uom_code": operation.get("uom_code"),
                    "completed_at": completed_at,
                }
                cursor.execute(
                    UPDATE_OPERATION_COMPLETED_SQL,
                    {
                        "work_order_operation_id": operation["work_order_operation_id"],
                        "good_quantity": good_quantity,
                        "scrap_quantity": scrap_quantity,
                        "completed_at": completed_at,
                    },
                )
                cursor.execute(UPDATE_QUEUE_COMPLETED_SQL, {"station_queue_pk": queue_row["station_queue_pk"]})
                cursor.execute(UPDATE_WORK_ORDER_COMPLETED_IF_ALL_DONE_SQL, {"order_id": operation["order_id"], "completed_at": completed_at})
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
                        "completed_at": completed_at,
                        "source_system": SOURCE_SYSTEM,
                        "source_file": "mesql_v2",
                        "external_ref": f"v2:operation_completed:{operation['work_order_operation_id']}",
                        "payload": _jsonb(event_payload),
                        "metadata": _jsonb({"source": "mesql_v2", **(metadata or {})}),
                    },
                )
                _insert_event(cursor, event_type="OPERATION_COMPLETED", event_at=completed_at, actor_id=actor_id, operation=operation, payload=event_payload)
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
    return {
        "status": "ok",
        "order_id": operation["order_id"],
        "work_order_operation_id": operation["work_order_operation_id"],
        "station_code": operation["station_code"],
        "operation_status": "completed",
        "outbox_id": outbox_id,
    }


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
            payload=dict(_field(row, 6, "payload") or {}),
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

from __future__ import annotations

import hashlib
import json
import uuid
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
BINDING_SOURCES = {"manual_setup", "work_order_release"}
WORK_ORDER_RELEASE_MODES = {
    "route_generated",
    "explicit_existing_operation_mapping",
}
WORK_ORDER_RELEASE_OPERATION_NAMESPACE_LABEL = (
    "urn:mes:work-order-route-release:operation:v1"
)
WORK_ORDER_RELEASE_OPERATION_NAMESPACE = uuid.UUID(
    "51e8ce07-9395-54f4-9677-a32d03162cdc"
)
WORK_ORDER_RELEASE_BINDING_NAMESPACE_LABEL = (
    "urn:mes:work-order-route-release:binding:v1"
)
WORK_ORDER_RELEASE_BINDING_NAMESPACE = uuid.UUID(
    "2e5192a2-5d5a-5f76-a9f6-dc70df96564a"
)
WORK_ORDER_RELEASE_QUEUE_CONSTRAINTS = {
    "uq_mes_station_queue_station_active_rank",
    "uq_mes_station_queue_station_order",
    "uq_mes_station_queue_station_operation",
}

SET_WORK_ORDER_RELEASE_TRANSACTION_ISOLATION_SQL = (
    "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"
)


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


def _required_uuid_text(value: Any, *, field_name: str) -> str:
    normalized = _text(value)
    if not normalized:
        raise MesqlV2Error(f"{field_name}_REQUIRED", status_code=400)
    try:
        return str(UUID(normalized))
    except (TypeError, ValueError, AttributeError):
        raise MesqlV2Error(f"{field_name}_INVALID", status_code=400) from None


def _required_case_preserving_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise MesqlV2Error(f"{field_name}_INVALID", status_code=400)
    normalized = value.strip()
    if not normalized:
        raise MesqlV2Error(f"{field_name}_REQUIRED", status_code=400)
    return normalized


def _required_positive_int(value: Any, *, field_name: str) -> int:
    if value is None or value == "":
        raise MesqlV2Error(f"{field_name}_REQUIRED", status_code=400)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MesqlV2Error(f"{field_name}_INVALID", status_code=400)
    return value


def _required_canonical_uuid_text(value: Any, *, field_name: str) -> str:
    normalized = _required_case_preserving_text(value, field_name=field_name)
    try:
        canonical = str(uuid.UUID(normalized))
    except (ValueError, AttributeError):
        raise MesqlV2Error(f"{field_name}_INVALID", status_code=400) from None
    if normalized != canonical:
        raise MesqlV2Error(f"{field_name}_INVALID", status_code=400)
    return canonical


def _work_order_release_canonical_name(
    release_id: Any,
    route_operation_id: Any,
) -> str:
    normalized_release_id = _required_case_preserving_text(
        release_id,
        field_name="RELEASE_ID",
    )
    normalized_route_operation_id = _required_case_preserving_text(
        route_operation_id,
        field_name="ROUTE_OPERATION_ID",
    )
    return f"{normalized_release_id}\n{normalized_route_operation_id}"


def _derive_work_order_release_operation_id(
    release_id: Any,
    route_operation_id: Any,
) -> str:
    canonical_name = _work_order_release_canonical_name(
        release_id,
        route_operation_id,
    )
    return str(
        uuid.uuid5(
            WORK_ORDER_RELEASE_OPERATION_NAMESPACE,
            canonical_name,
        )
    )


def _derive_work_order_release_binding_id(
    release_id: Any,
    route_operation_id: Any,
) -> str:
    canonical_name = _work_order_release_canonical_name(
        release_id,
        route_operation_id,
    )
    binding_uuid = uuid.uuid5(
        WORK_ORDER_RELEASE_BINDING_NAMESPACE,
        canonical_name,
    )
    return f"BINDING-WORK-ORDER-RELEASE-{str(binding_uuid).upper()}"


def _compute_work_order_release_operation_set_digest(
    *,
    process_route_id: Any,
    route_code: Any,
    route_version: Any,
    release_mode: Any,
    pairs: Any,
) -> str:
    normalized_process_route_id = _required_case_preserving_text(
        process_route_id,
        field_name="PROCESS_ROUTE_ID",
    )
    normalized_route_code = _required_case_preserving_text(
        route_code,
        field_name="ROUTE_CODE",
    )
    normalized_route_version = _required_positive_int(
        route_version,
        field_name="ROUTE_VERSION",
    )
    normalized_release_mode = _required_case_preserving_text(
        release_mode,
        field_name="RELEASE_MODE",
    )
    if normalized_release_mode not in WORK_ORDER_RELEASE_MODES:
        raise MesqlV2Error("RELEASE_MODE_INVALID", status_code=400)
    if pairs is None or pairs == []:
        raise MesqlV2Error("OPERATION_SET_REQUIRED", status_code=400)
    if not isinstance(pairs, list):
        raise MesqlV2Error("OPERATION_SET_INVALID", status_code=400)

    expected_pair_fields = {
        "sequence_no",
        "route_operation_id",
        "work_order_operation_id",
    }
    canonical_pairs: list[JsonObject] = []
    seen_sequences: set[int] = set()
    seen_route_operation_ids: set[str] = set()
    seen_work_order_operation_ids: set[str] = set()
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) != expected_pair_fields:
            raise MesqlV2Error("OPERATION_SET_INVALID", status_code=400)
        sequence_no = _required_positive_int(
            pair.get("sequence_no"),
            field_name="SEQUENCE_NO",
        )
        route_operation_id = _required_case_preserving_text(
            pair.get("route_operation_id"),
            field_name="ROUTE_OPERATION_ID",
        )
        work_order_operation_id = _required_canonical_uuid_text(
            pair.get("work_order_operation_id"),
            field_name="WORK_ORDER_OPERATION_ID",
        )
        if sequence_no in seen_sequences:
            raise MesqlV2Error("SEQUENCE_NO_INVALID", status_code=400)
        if route_operation_id in seen_route_operation_ids:
            raise MesqlV2Error("ROUTE_OPERATION_ID_INVALID", status_code=400)
        if work_order_operation_id in seen_work_order_operation_ids:
            raise MesqlV2Error("WORK_ORDER_OPERATION_ID_INVALID", status_code=400)
        seen_sequences.add(sequence_no)
        seen_route_operation_ids.add(route_operation_id)
        seen_work_order_operation_ids.add(work_order_operation_id)
        canonical_pairs.append(
            {
                "sequence_no": sequence_no,
                "route_operation_id": route_operation_id,
                "work_order_operation_id": work_order_operation_id,
            }
        )

    canonical_pairs.sort(
        key=lambda pair: (
            pair["sequence_no"],
            pair["route_operation_id"].encode("utf-8"),
        )
    )
    payload = {
        "process_route_id": normalized_process_route_id,
        "release_mode": normalized_release_mode,
        "route_code": normalized_route_code,
        "route_version": normalized_route_version,
        "pairs": canonical_pairs,
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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

SELECT_WORK_ORDER_ROUTE_RELEASE_SQL = """
SELECT
    release_pk,
    release_id,
    order_id,
    process_route_id,
    route_code,
    route_version,
    release_mode,
    release_source,
    released_by,
    released_at,
    route_operation_count,
    operation_set_digest,
    metadata,
    created_at
FROM mes.work_order_route_releases
WHERE order_id = %(work_order_id)s
LIMIT 1
"""

SELECT_WORK_ORDER_ROUTE_RELEASE_BY_ID_SQL = """
SELECT
    release_pk,
    release_id,
    order_id,
    process_route_id,
    route_code,
    route_version,
    release_mode,
    release_source,
    released_by,
    released_at,
    route_operation_count,
    operation_set_digest,
    metadata,
    created_at
FROM mes.work_order_route_releases
WHERE release_id = %(release_id)s
LIMIT 1
"""

SELECT_EXACT_PROCESS_ROUTE_SQL = """
SELECT
    route_code,
    version,
    route_name,
    item_code,
    active,
    metadata,
    route_id
FROM mes.process_routes
WHERE route_code = %(route_code)s
  AND version = %(route_version)s
LIMIT 1
"""

SELECT_PROCESS_ROUTE_OPERATIONS_SQL = """
SELECT
    operation.route_operation_id,
    operation.route_code,
    operation.route_version,
    operation.sequence_no,
    operation.operation_code,
    operation.operation_name,
    operation.station_code,
    operation.input_item_code,
    operation.output_item_code,
    operation.input_qty_per_cycle,
    operation.output_qty_per_cycle,
    operation.input_location_role,
    operation.output_location_role,
    operation.scrap_location_role,
    operation.operation_completion_policy,
    operation.planned_cycle_time_sec,
    operation.active,
    operation.metadata
FROM mes.route_operations operation
JOIN mes.process_routes route
  ON route.route_code = operation.route_code
 AND route.version = operation.route_version
WHERE route.route_id = %(process_route_id)s
ORDER BY operation.sequence_no ASC, operation.route_operation_id ASC
"""

SELECT_WORK_ORDER_RELEASE_WORK_ORDER_SQL = """
SELECT
    order_id,
    status,
    product_code,
    target_quantity,
    started_at,
    completed_at,
    payload,
    metadata
FROM mes.work_orders
WHERE order_id = %(work_order_id)s
LIMIT 1
"""

SELECT_WORK_ORDER_RELEASE_OPERATIONS_SQL = """
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
WHERE order_id = %(work_order_id)s
ORDER BY sequence_no ASC, work_order_operation_id ASC
"""

SELECT_WORK_ORDER_RELEASE_BINDINGS_SQL = """
SELECT
    binding.binding_pk,
    binding.binding_id,
    binding.work_order_operation_id,
    binding.route_operation_id,
    binding.binding_source,
    binding.bound_by,
    binding.bound_at,
    binding.metadata,
    binding.created_at
FROM mes.work_order_operation_route_bindings binding
JOIN mes.work_order_operations operation
  ON operation.work_order_operation_id = binding.work_order_operation_id
WHERE operation.order_id = %(work_order_id)s
ORDER BY
    operation.sequence_no ASC,
    binding.work_order_operation_id ASC,
    binding.binding_id ASC
"""

SELECT_WORK_ORDER_RELEASE_INITIAL_QUEUE_SQL = """
SELECT
    station_queue_pk,
    station_code,
    order_id,
    queue_rank,
    status,
    source,
    payload,
    metadata,
    created_at,
    updated_at,
    work_order_operation_id
FROM mes.station_queue
WHERE work_order_operation_id = %(work_order_operation_id)s::uuid
  AND order_id = %(work_order_id)s
  AND station_code = %(station_code)s
LIMIT 1
"""

SELECT_WORK_ORDER_FOR_RELEASE_CURSOR_SQL = """
SELECT
    work_order_pk,
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
WHERE order_id = %(work_order_id)s
FOR UPDATE
"""

SELECT_RELEASES_FOR_UPDATE_CURSOR_SQL = """
SELECT
    release_pk,
    release_id,
    order_id,
    process_route_id,
    route_code,
    route_version,
    release_mode,
    release_source,
    released_by,
    released_at,
    route_operation_count,
    operation_set_digest,
    metadata,
    created_at
FROM mes.work_order_route_releases
WHERE order_id = %(work_order_id)s
   OR release_id = %(release_id)s
ORDER BY release_pk ASC
FOR UPDATE
"""

SELECT_EXISTING_WORK_ORDER_OPERATIONS_FOR_UPDATE_CURSOR_SQL = """
SELECT
    work_order_operation_id,
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
    started_at,
    completed_at,
    payload,
    metadata,
    created_at,
    updated_at
FROM mes.work_order_operations
WHERE order_id = %(work_order_id)s
ORDER BY work_order_operation_id ASC
FOR UPDATE
"""

SELECT_EXISTING_RELEASE_BINDINGS_FOR_UPDATE_CURSOR_SQL = """
SELECT
    binding.binding_pk,
    binding.binding_id,
    binding.work_order_operation_id,
    binding.route_operation_id,
    binding.binding_source,
    binding.bound_by,
    binding.bound_at,
    binding.metadata,
    binding.created_at
FROM mes.work_order_operation_route_bindings binding
JOIN mes.work_order_operations operation
  ON operation.work_order_operation_id = binding.work_order_operation_id
WHERE operation.order_id = %(work_order_id)s
ORDER BY binding.binding_pk ASC
FOR UPDATE OF binding
"""

SELECT_WORK_ORDER_RELEASE_EVIDENCE_CURSOR_SQL = """
SELECT
    (SELECT count(*) FROM mes.work_order_operation_execution_state state
      WHERE state.work_order_id = %(work_order_id)s) AS execution_state_count,
    (SELECT count(*) FROM mes.work_order_operation_steps step
      WHERE step.work_order_id = %(work_order_id)s) AS operation_step_count,
    (SELECT count(*) FROM mes.operation_events event
      WHERE event.work_order_id = %(work_order_id)s) AS operation_event_count,
    (SELECT count(*) FROM mes.operation_approvals approval
      WHERE approval.work_order_id = %(work_order_id)s) AS operation_approval_count,
    (SELECT count(*) FROM mes.production_flow_events flow
      WHERE flow.work_order_id = %(work_order_id)s) AS production_flow_event_count
"""

SELECT_INITIAL_QUEUE_FOR_UPDATE_CURSOR_SQL = """
SELECT
    station_queue_pk,
    station_code,
    order_id,
    queue_rank,
    status,
    source,
    payload,
    metadata,
    created_at,
    updated_at,
    work_order_operation_id
FROM mes.station_queue
WHERE order_id = %(work_order_id)s
  AND work_order_operation_id = %(work_order_operation_id)s::uuid
ORDER BY station_queue_pk ASC
FOR UPDATE
"""

SELECT_WORK_ORDER_QUEUE_FOR_UPDATE_CURSOR_SQL = """
SELECT
    station_queue_pk,
    station_code,
    order_id,
    queue_rank,
    status,
    source,
    payload,
    metadata,
    created_at,
    updated_at,
    work_order_operation_id
FROM mes.station_queue
WHERE order_id = %(work_order_id)s
ORDER BY station_queue_pk ASC
FOR UPDATE
"""

LOCK_STATION_QUEUE_ADVISORY_CURSOR_SQL = """
SELECT pg_advisory_xact_lock(
    hashtextextended(
        'mes:work_order_release:station_queue:' || %(station_code)s,
        0
    )
)
"""

SELECT_STATION_QUEUE_FOR_UPDATE_CURSOR_SQL = """
SELECT
    station_queue_pk,
    station_code,
    order_id,
    queue_rank,
    status,
    source,
    payload,
    metadata,
    created_at,
    updated_at,
    work_order_operation_id
FROM mes.station_queue
WHERE station_code = %(station_code)s
ORDER BY station_queue_pk ASC
FOR UPDATE
"""

SELECT_NEXT_STATION_QUEUE_RANK_CURSOR_SQL = """
SELECT COALESCE(MAX(queue_rank) + 1, 0)
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND status IN ('queued', 'active', 'pending_approval')
"""

INSERT_WORK_ORDER_ROUTE_RELEASE_CURSOR_SQL = """
INSERT INTO mes.work_order_route_releases (
    release_id, order_id, process_route_id, route_code, route_version,
    release_mode, release_source, released_by, route_operation_count,
    operation_set_digest, metadata
) VALUES (
    %(release_id)s, %(order_id)s, %(process_route_id)s, %(route_code)s,
    %(route_version)s, %(release_mode)s, %(release_source)s, %(released_by)s,
    %(route_operation_count)s, %(operation_set_digest)s, %(metadata)s
)
RETURNING
    release_pk, release_id, order_id, process_route_id, route_code,
    route_version, release_mode, release_source, released_by, released_at,
    route_operation_count, operation_set_digest, metadata, created_at
"""

INSERT_ROUTE_GENERATED_WORK_ORDER_OPERATION_CURSOR_SQL = """
INSERT INTO mes.work_order_operations (
    work_order_operation_id, order_id, mesql_work_order_operation_id,
    operation_no, operation_code, operation_name, sequence_no, station_code,
    status, planned_quantity, good_quantity, scrap_quantity, uom_code,
    started_at, completed_at, payload, metadata
) VALUES (
    %(work_order_operation_id)s::uuid, %(order_id)s, NULL,
    %(operation_no)s, %(operation_code)s, %(operation_name)s,
    %(sequence_no)s, %(station_code)s, %(status)s, %(planned_quantity)s,
    0, 0, %(uom_code)s, NULL, NULL, %(payload)s, %(metadata)s
)
RETURNING
    work_order_operation_id, order_id, mesql_work_order_operation_id,
    operation_no, operation_code, operation_name, sequence_no, station_code,
    status, planned_quantity, good_quantity, scrap_quantity, uom_code,
    started_at, completed_at, payload, metadata, created_at, updated_at
"""

INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_CURSOR_SQL = """
INSERT INTO mes.work_order_operation_route_bindings (
    binding_id, work_order_operation_id, route_operation_id,
    binding_source, bound_by, metadata
) VALUES (
    %(binding_id)s, %(work_order_operation_id)s::uuid, %(route_operation_id)s,
    %(binding_source)s, %(bound_by)s, %(metadata)s
)
RETURNING
    binding_pk, binding_id, work_order_operation_id, route_operation_id,
    binding_source, bound_by, bound_at, metadata, created_at
"""

INSERT_INITIAL_STATION_QUEUE_CURSOR_SQL = """
INSERT INTO mes.station_queue (
    station_code, order_id, queue_rank, status, source, payload, metadata,
    work_order_operation_id
) VALUES (
    %(station_code)s, %(order_id)s, %(queue_rank)s, %(status)s, %(source)s,
    %(payload)s, %(metadata)s, %(work_order_operation_id)s::uuid
)
RETURNING
    station_queue_pk, station_code, order_id, queue_rank, status, source,
    payload, metadata, created_at, updated_at, work_order_operation_id
"""

UPDATE_WORK_ORDER_RELEASED_STATE_CURSOR_SQL = """
UPDATE mes.work_orders
SET status = 'queued',
    updated_at = now()
WHERE order_id = %(work_order_id)s
RETURNING
    work_order_pk, order_id, erp_type, status, product_code, target_quantity,
    started_at, completed_at, source_system, source_file, external_ref,
    payload, metadata, created_at, updated_at
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

SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL = """
SELECT
    binding_pk,
    binding_id,
    work_order_operation_id,
    route_operation_id,
    binding_source,
    bound_by,
    bound_at,
    metadata,
    created_at
FROM mes.work_order_operation_route_bindings
WHERE work_order_operation_id = %(work_order_operation_id)s::uuid
LIMIT 1
"""

SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_BY_ID_SQL = """
SELECT
    binding_pk,
    binding_id,
    work_order_operation_id,
    route_operation_id,
    binding_source,
    bound_by,
    bound_at,
    metadata,
    created_at
FROM mes.work_order_operation_route_bindings
WHERE binding_id = %(binding_id)s
LIMIT 1
"""

INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL = """
INSERT INTO mes.work_order_operation_route_bindings (
    binding_id,
    work_order_operation_id,
    route_operation_id,
    binding_source,
    bound_by,
    metadata
) VALUES (
    %(binding_id)s,
    %(work_order_operation_id)s::uuid,
    %(route_operation_id)s,
    %(binding_source)s,
    %(bound_by)s,
    %(metadata)s::jsonb
)
ON CONFLICT DO NOTHING
RETURNING
    binding_pk,
    binding_id,
    work_order_operation_id,
    route_operation_id,
    binding_source,
    bound_by,
    bound_at,
    metadata,
    created_at
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

SELECT_EXECUTION_STEP_FOR_UPDATE_SQL = """
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
  AND step_code = %(step_code)s
LIMIT 1
FOR UPDATE
"""

SELECT_EXECUTION_STEPS_FOR_UPDATE_SQL = """
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
FOR UPDATE
"""

SELECT_COMPLETION_BRIDGE_APPLICABILITY_CURSOR_SQL = """
SELECT
    work_order_operation_id,
    order_id,
    operation_code,
    sequence_no,
    station_code,
    status,
    completed_at,
    payload,
    metadata
FROM mes.work_order_operations
WHERE work_order_operation_id = %(work_order_operation_id)s::uuid
LIMIT 1
"""

SELECT_COMPLETION_BRIDGE_SCHEMA_READINESS_CURSOR_SQL = """
SELECT
    to_regclass('mes.work_order_route_releases') IS NOT NULL AS release_table_ready,
    to_regclass('mes.work_order_operation_route_bindings') IS NOT NULL AS binding_table_ready
"""

SELECT_COMPLETION_BRIDGE_WORK_ORDER_FOR_UPDATE_CURSOR_SQL = """
SELECT
    work_order_pk, order_id, erp_type, status, product_code, target_quantity,
    started_at, completed_at, source_system, source_file, external_ref,
    payload, metadata, created_at, updated_at
FROM mes.work_orders
WHERE order_id = %(work_order_id)s
FOR UPDATE
"""

SELECT_COMPLETION_BRIDGE_RELEASE_FOR_UPDATE_CURSOR_SQL = """
SELECT
    release_pk, release_id, order_id, process_route_id, route_code,
    route_version, release_mode, release_source, released_by, released_at,
    route_operation_count, operation_set_digest, metadata, created_at
FROM mes.work_order_route_releases
WHERE order_id = %(work_order_id)s
ORDER BY release_pk ASC
FOR UPDATE
"""

SELECT_COMPLETION_BRIDGE_OPERATIONS_FOR_UPDATE_CURSOR_SQL = """
SELECT
    work_order_operation_id, order_id, mesql_work_order_operation_id,
    operation_no, operation_code, operation_name, sequence_no, station_code,
    status, planned_quantity, good_quantity, scrap_quantity, uom_code,
    started_at, completed_at, payload, metadata, created_at, updated_at
FROM mes.work_order_operations
WHERE order_id = %(work_order_id)s
ORDER BY work_order_operation_id ASC
FOR UPDATE
"""

SELECT_COMPLETION_BRIDGE_BINDINGS_FOR_UPDATE_CURSOR_SQL = """
SELECT
    binding.binding_pk, binding.binding_id, binding.work_order_operation_id,
    binding.route_operation_id, binding.binding_source, binding.bound_by,
    binding.bound_at, binding.metadata, binding.created_at
FROM mes.work_order_operation_route_bindings binding
JOIN mes.work_order_operations operation
  ON operation.work_order_operation_id = binding.work_order_operation_id
WHERE operation.order_id = %(work_order_id)s
ORDER BY binding.binding_pk ASC
FOR UPDATE OF binding
"""

SELECT_COMPLETION_BRIDGE_EXECUTION_STATE_FOR_UPDATE_CURSOR_SQL = """
SELECT
    execution_state_pk, execution_state_id, work_order_operation_id,
    work_order_id, station_code, operation_code, execution_status,
    operation_completion_policy, current_step_code, started_at,
    evidence_completed_at, pending_final_approval_at, closed_at,
    last_event_id, last_approval_id, created_at, updated_at, metadata
FROM mes.work_order_operation_execution_state
WHERE work_order_operation_id = %(work_order_operation_id)s::uuid
FOR UPDATE
"""

SELECT_COMPLETION_BRIDGE_RUNTIME_STEPS_FOR_UPDATE_CURSOR_SQL = """
SELECT
    work_order_operation_step_pk, work_order_operation_step_id,
    work_order_operation_id, work_order_id, operation_code, step_code,
    step_no, station_code, status, started_at, completed_at,
    started_by_event_id, completed_by_event_id, required_for_completion,
    records_duration, approval_required_after_finish, created_at, updated_at,
    metadata
FROM mes.work_order_operation_steps
WHERE work_order_operation_id = %(work_order_operation_id)s::uuid
ORDER BY step_no ASC
FOR UPDATE
"""

LOCK_COMPLETION_BRIDGE_STATION_SCOPE_CURSOR_SQL = """
SELECT pg_advisory_xact_lock(
    hashtextextended(
        'mes:work_order_release:station_queue:' || %(station_code)s,
        0
    )
)
"""

SELECT_COMPLETION_BRIDGE_STATION_QUEUE_ROWS_FOR_UPDATE_CURSOR_SQL = """
SELECT
    station_queue_pk, station_code, order_id, queue_rank, status, source,
    payload, metadata, created_at, updated_at, work_order_operation_id
FROM mes.station_queue
WHERE station_code = ANY(%(station_codes)s)
ORDER BY station_code ASC, station_queue_pk ASC
FOR UPDATE
"""

UPDATE_COMPLETION_BRIDGE_LIFECYCLE_CURSOR_SQL = """
UPDATE mes.work_order_operations
SET status = 'completed',
    completed_at = %(closed_at)s,
    updated_at = now()
WHERE work_order_operation_id = %(work_order_operation_id)s::uuid
  AND status IN ('queued', 'active')
  AND completed_at IS NULL
RETURNING
    work_order_operation_id, order_id, mesql_work_order_operation_id,
    operation_no, operation_code, operation_name, sequence_no, station_code,
    status, planned_quantity, good_quantity, scrap_quantity, uom_code,
    started_at, completed_at, payload, metadata, created_at, updated_at
"""

UPDATE_COMPLETION_BRIDGE_CURRENT_QUEUE_CURSOR_SQL = """
UPDATE mes.station_queue
SET status = 'completed',
    updated_at = now()
WHERE station_queue_pk = %(station_queue_pk)s
  AND status IN ('queued', 'ready', 'active', 'pending_approval')
RETURNING
    station_queue_pk, station_code, order_id, queue_rank, status, source,
    payload, metadata, created_at, updated_at, work_order_operation_id
"""

UPDATE_COMPLETION_BRIDGE_SUCCESSOR_LIFECYCLE_CURSOR_SQL = """
UPDATE mes.work_order_operations
SET status = 'queued',
    updated_at = now()
WHERE work_order_operation_id = %(work_order_operation_id)s::uuid
  AND status = 'planned'
  AND completed_at IS NULL
RETURNING
    work_order_operation_id, order_id, mesql_work_order_operation_id,
    operation_no, operation_code, operation_name, sequence_no, station_code,
    status, planned_quantity, good_quantity, scrap_quantity, uom_code,
    started_at, completed_at, payload, metadata, created_at, updated_at
"""

INSERT_COMPLETION_BRIDGE_SUCCESSOR_QUEUE_CURSOR_SQL = """
INSERT INTO mes.station_queue (
    station_code, order_id, queue_rank, status, source, payload, metadata,
    work_order_operation_id
) VALUES (
    %(station_code)s, %(order_id)s, %(queue_rank)s, 'queued',
    'runtime_completion_bridge', %(payload)s, %(metadata)s,
    %(work_order_operation_id)s::uuid
)
RETURNING
    station_queue_pk, station_code, order_id, queue_rank, status, source,
    payload, metadata, created_at, updated_at, work_order_operation_id
"""

UPDATE_COMPLETION_BRIDGE_WORK_ORDER_CURSOR_SQL = """
UPDATE mes.work_orders
SET status = 'completed',
    completed_at = %(closed_at)s,
    updated_at = now()
WHERE order_id = %(work_order_id)s
  AND status <> 'completed'
  AND completed_at IS NULL
RETURNING
    work_order_pk, order_id, erp_type, status, product_code, target_quantity,
    started_at, completed_at, source_system, source_file, external_ref,
    payload, metadata, created_at, updated_at
"""

SELECT_COMPLETION_BRIDGE_OPERATION_CURSOR_SQL = """
SELECT
    work_order_operation_id, order_id, mesql_work_order_operation_id,
    operation_no, operation_code, operation_name, sequence_no, station_code,
    status, planned_quantity, good_quantity, scrap_quantity, uom_code,
    started_at, completed_at, payload, metadata, created_at, updated_at
FROM mes.work_order_operations
WHERE order_id = %(work_order_id)s
  AND work_order_operation_id = %(work_order_operation_id)s::uuid
"""

SELECT_COMPLETION_BRIDGE_QUEUE_CURSOR_SQL = """
SELECT
    station_queue_pk, station_code, order_id, queue_rank, status, source,
    payload, metadata, created_at, updated_at, work_order_operation_id
FROM mes.station_queue
WHERE order_id = %(work_order_id)s
  AND work_order_operation_id = %(work_order_operation_id)s::uuid
ORDER BY station_queue_pk ASC
"""

SELECT_COMPLETION_BRIDGE_WORK_ORDER_CURSOR_SQL = """
SELECT
    work_order_pk, order_id, erp_type, status, product_code, target_quantity,
    started_at, completed_at, source_system, source_file, external_ref,
    payload, metadata, created_at, updated_at
FROM mes.work_orders
WHERE order_id = %(work_order_id)s
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
    %(work_order_id)s,
    %(work_order_operation_id)s,
    %(work_order_operation_step_id)s,
    %(operation_code)s,
    %(step_code)s,
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

UPDATE_EXECUTION_STATE_STEP_STARTED_SQL = """
UPDATE mes.work_order_operation_execution_state
SET
    execution_status = 'active',
    current_step_code = %(current_step_code)s,
    started_at = COALESCE(started_at, now()),
    last_event_id = %(last_event_id)s,
    updated_at = now()
WHERE work_order_operation_id = %(work_order_operation_id)s
"""

UPDATE_EXECUTION_STEP_STARTED_SQL = """
UPDATE mes.work_order_operation_steps
SET
    status = 'active',
    started_at = COALESCE(started_at, now()),
    started_by_event_id = COALESCE(started_by_event_id, %(started_by_event_id)s),
    updated_at = now()
WHERE work_order_operation_id = %(work_order_operation_id)s
  AND step_code = %(step_code)s
"""

UPDATE_EXECUTION_STEP_FINISHED_SQL = """
UPDATE mes.work_order_operation_steps
SET
    status = 'completed',
    started_at = COALESCE(started_at, %(event_time)s),
    completed_at = %(event_time)s,
    started_by_event_id = COALESCE(started_by_event_id, %(event_id)s),
    completed_by_event_id = %(event_id)s,
    updated_at = %(event_time)s
WHERE work_order_operation_id = %(work_order_operation_id)s
  AND step_code = %(step_code)s
RETURNING
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
"""

UPDATE_EXECUTION_STATE_STEP_FINISHED_SQL = """
UPDATE mes.work_order_operation_execution_state
SET
    execution_status = %(execution_status)s,
    current_step_code = %(current_step_code)s,
    started_at = COALESCE(started_at, %(event_time)s),
    evidence_completed_at = CASE
        WHEN %(completion_policy_applied)s THEN %(event_time)s
        ELSE evidence_completed_at
    END,
    pending_final_approval_at = CASE
        WHEN %(completion_policy_applied)s AND %(set_pending_final_approval_at)s
            THEN %(event_time)s
        WHEN %(completion_policy_applied)s THEN NULL
        ELSE pending_final_approval_at
    END,
    closed_at = CASE
        WHEN %(completion_policy_applied)s AND %(set_closed_at)s
            THEN %(event_time)s
        WHEN %(completion_policy_applied)s THEN NULL
        ELSE closed_at
    END,
    last_event_id = %(last_event_id)s,
    updated_at = %(event_time)s
WHERE work_order_operation_id = %(work_order_operation_id)s
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


def _exact_process_route_row(row: Any) -> JsonObject:
    route = _process_route_row(row)
    route["item_code"] = _text(_field(row, 3, "item_code"))
    return {
        "route_id": _text(_field(row, 6, "route_id")),
        **route,
    }


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


def _process_route_operation_row(row: Any) -> JsonObject:
    operation = _route_operation_row(row)
    for field_name, index in (
        ("route_operation_id", 0),
        ("operation_code", 4),
        ("station_code", 6),
        ("input_item_code", 7),
        ("output_item_code", 8),
        ("input_location_role", 11),
        ("output_location_role", 12),
        ("operation_completion_policy", 14),
    ):
        operation[field_name] = _text(_field(row, index, field_name))
    operation["scrap_location_role"] = _nullable_text(
        _field(row, 13, "scrap_location_role")
    )
    return operation


def _work_order_route_release_row(row: Any) -> JsonObject:
    return _json_safe({
        "release_pk": _field(row, 0, "release_pk"),
        "release_id": _field(row, 1, "release_id"),
        "order_id": _field(row, 2, "order_id"),
        "process_route_id": _field(row, 3, "process_route_id"),
        "route_code": _field(row, 4, "route_code"),
        "route_version": _field(row, 5, "route_version"),
        "release_mode": _field(row, 6, "release_mode"),
        "release_source": _field(row, 7, "release_source"),
        "released_by": _field(row, 8, "released_by"),
        "released_at": _field(row, 9, "released_at"),
        "route_operation_count": _field(row, 10, "route_operation_count"),
        "operation_set_digest": _field(row, 11, "operation_set_digest"),
        "metadata": _field(row, 12, "metadata") or {},
        "created_at": _field(row, 13, "created_at"),
    })


def _work_order_release_work_order_row(row: Any) -> JsonObject:
    return _json_safe({
        "order_id": _field(row, 0, "order_id"),
        "status": _field(row, 1, "status"),
        "product_code": _field(row, 2, "product_code"),
        "target_quantity": _field(row, 3, "target_quantity"),
        "started_at": _field(row, 4, "started_at"),
        "completed_at": _field(row, 5, "completed_at"),
        "payload": _field(row, 6, "payload") or {},
        "metadata": _field(row, 7, "metadata") or {},
    })


def _work_order_release_operation_row(row: Any) -> JsonObject:
    return _json_safe({
        "work_order_operation_id": _field(
            row,
            0,
            "work_order_operation_id",
        ),
        "order_id": _field(row, 1, "order_id"),
        "operation_no": _field(row, 2, "operation_no"),
        "operation_code": _field(row, 3, "operation_code"),
        "operation_name": _field(row, 4, "operation_name"),
        "station_code": _field(row, 5, "station_code"),
        "status": _field(row, 6, "status"),
        "planned_quantity": _field(row, 7, "planned_quantity"),
        "good_quantity": _field(row, 8, "good_quantity"),
        "scrap_quantity": _field(row, 9, "scrap_quantity"),
        "uom_code": _field(row, 10, "uom_code"),
        "started_at": _field(row, 11, "started_at"),
        "completed_at": _field(row, 12, "completed_at"),
        "sequence_no": _field(row, 13, "sequence_no"),
    })


def _work_order_release_initial_queue_row(row: Any) -> JsonObject:
    return _json_safe({
        "station_queue_pk": _field(row, 0, "station_queue_pk"),
        "station_code": _field(row, 1, "station_code"),
        "order_id": _field(row, 2, "order_id"),
        "queue_rank": _field(row, 3, "queue_rank"),
        "status": _field(row, 4, "status"),
        "source": _field(row, 5, "source"),
        "payload": _field(row, 6, "payload") or {},
        "metadata": _field(row, 7, "metadata") or {},
        "created_at": _field(row, 8, "created_at"),
        "updated_at": _field(row, 9, "updated_at"),
        "work_order_operation_id": _field(
            row,
            10,
            "work_order_operation_id",
        ),
    })


def _work_order_operation_route_binding_row(row: Any) -> JsonObject:
    return _json_safe({
        "binding_pk": _field(row, 0, "binding_pk"),
        "binding_id": _field(row, 1, "binding_id"),
        "work_order_operation_id": _field(row, 2, "work_order_operation_id"),
        "route_operation_id": _field(row, 3, "route_operation_id"),
        "binding_source": _field(row, 4, "binding_source"),
        "bound_by": _field(row, 5, "bound_by"),
        "bound_at": _field(row, 6, "bound_at"),
        "metadata": _field(row, 7, "metadata") or {},
        "created_at": _field(row, 8, "created_at"),
    })


def _release_work_order_full_row(row: Any) -> JsonObject:
    names = (
        "work_order_pk", "order_id", "erp_type", "status", "product_code",
        "target_quantity", "started_at", "completed_at", "source_system",
        "source_file", "external_ref", "payload", "metadata", "created_at",
        "updated_at",
    )
    result = {name: _field(row, index, name) for index, name in enumerate(names)}
    result["payload"] = result["payload"] or {}
    result["metadata"] = result["metadata"] or {}
    return _json_safe(result)


def _release_work_order_operation_full_row(row: Any) -> JsonObject:
    names = (
        "work_order_operation_id", "order_id", "mesql_work_order_operation_id",
        "operation_no", "operation_code", "operation_name", "sequence_no",
        "station_code", "status", "planned_quantity", "good_quantity",
        "scrap_quantity", "uom_code", "started_at", "completed_at", "payload",
        "metadata", "created_at", "updated_at",
    )
    result = {name: _field(row, index, name) for index, name in enumerate(names)}
    result["payload"] = result["payload"] or {}
    result["metadata"] = result["metadata"] or {}
    return _json_safe(result)


def _work_order_release_evidence_row(row: Any) -> JsonObject:
    names = (
        "execution_state_count", "operation_step_count", "operation_event_count",
        "operation_approval_count", "production_flow_event_count",
    )
    return {
        name: _safe_int(_field(row, index, name), 0)
        for index, name in enumerate(names)
    }


def _get_work_order_operation_route_binding_with_cursor(
    cursor: Any,
    work_order_operation_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL,
        {"work_order_operation_id": work_order_operation_id},
    )
    row = cursor.fetchone()
    return _work_order_operation_route_binding_row(row) if row else None


def _get_work_order_operation_route_binding_by_id_with_cursor(
    cursor: Any,
    binding_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_BY_ID_SQL,
        {"binding_id": binding_id},
    )
    row = cursor.fetchone()
    return _work_order_operation_route_binding_row(row) if row else None


def _get_work_order_route_release_with_cursor(
    cursor: Any,
    work_order_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_WORK_ORDER_ROUTE_RELEASE_SQL,
        {"work_order_id": work_order_id},
    )
    row = cursor.fetchone()
    return _work_order_route_release_row(row) if row else None


def _get_work_order_route_release_by_id_with_cursor(
    cursor: Any,
    release_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_WORK_ORDER_ROUTE_RELEASE_BY_ID_SQL,
        {"release_id": release_id},
    )
    row = cursor.fetchone()
    return _work_order_route_release_row(row) if row else None


def _get_exact_process_route_with_cursor(
    cursor: Any,
    route_code: str,
    route_version: int,
) -> JsonObject | None:
    cursor.execute(
        SELECT_EXACT_PROCESS_ROUTE_SQL,
        {
            "route_code": route_code,
            "route_version": route_version,
        },
    )
    row = cursor.fetchone()
    return _exact_process_route_row(row) if row else None


def _list_process_route_operations_with_cursor(
    cursor: Any,
    process_route_id: str,
) -> list[JsonObject]:
    cursor.execute(
        SELECT_PROCESS_ROUTE_OPERATIONS_SQL,
        {"process_route_id": process_route_id},
    )
    return [
        _process_route_operation_row(row)
        for row in cursor.fetchall()
    ]


def _get_work_order_release_snapshot_with_cursor(
    cursor: Any,
    work_order_id: str,
) -> JsonObject | None:
    release = _get_work_order_route_release_with_cursor(cursor, work_order_id)
    if release is None:
        return None

    authoritative_order_id = _text(release["order_id"])
    cursor.execute(
        SELECT_WORK_ORDER_RELEASE_WORK_ORDER_SQL,
        {"work_order_id": authoritative_order_id},
    )
    work_order_row = cursor.fetchone()
    work_order = (
        _work_order_release_work_order_row(work_order_row)
        if work_order_row
        else None
    )

    cursor.execute(
        SELECT_WORK_ORDER_RELEASE_OPERATIONS_SQL,
        {"work_order_id": authoritative_order_id},
    )
    operations = [
        _work_order_release_operation_row(row)
        for row in cursor.fetchall()
    ]

    cursor.execute(
        SELECT_WORK_ORDER_RELEASE_BINDINGS_SQL,
        {"work_order_id": authoritative_order_id},
    )
    bindings = [
        _work_order_operation_route_binding_row(row)
        for row in cursor.fetchall()
    ]

    initial_queue = None
    if operations:
        first_operation = operations[0]
        cursor.execute(
            SELECT_WORK_ORDER_RELEASE_INITIAL_QUEUE_SQL,
            {
                "work_order_operation_id": first_operation[
                    "work_order_operation_id"
                ],
                "work_order_id": authoritative_order_id,
                "station_code": first_operation["station_code"],
            },
        )
        queue_row = cursor.fetchone()
        if queue_row:
            initial_queue = _work_order_release_initial_queue_row(queue_row)

    return {
        "release": release,
        "work_order": work_order,
        "operations": operations,
        "bindings": bindings,
        "initial_queue": initial_queue,
    }


def _select_work_order_for_release_cursor(
    cursor: Any,
    work_order_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_WORK_ORDER_FOR_RELEASE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    row = cursor.fetchone()
    return _release_work_order_full_row(row) if row else None


def _select_releases_for_update_cursor(
    cursor: Any,
    work_order_id: str,
    release_id: str,
) -> list[JsonObject]:
    cursor.execute(
        SELECT_RELEASES_FOR_UPDATE_CURSOR_SQL,
        {"work_order_id": work_order_id, "release_id": release_id},
    )
    return [_work_order_route_release_row(row) for row in cursor.fetchall()]


def _select_exact_process_route_cursor(
    cursor: Any,
    route_code: str,
    route_version: int,
) -> JsonObject | None:
    return _get_exact_process_route_with_cursor(cursor, route_code, route_version)


def _select_route_item_cursor(cursor: Any, item_code: str) -> JsonObject | None:
    cursor.execute(SELECT_ITEM_BY_CODE_SQL, {"item_code": item_code})
    row = cursor.fetchone()
    return _item_row(row) if row else None


def _list_process_route_operations_cursor(
    cursor: Any,
    process_route_id: str,
) -> list[JsonObject]:
    return _list_process_route_operations_with_cursor(cursor, process_route_id)


def _list_existing_work_order_operations_for_update_cursor(
    cursor: Any,
    work_order_id: str,
) -> list[JsonObject]:
    cursor.execute(
        SELECT_EXISTING_WORK_ORDER_OPERATIONS_FOR_UPDATE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    return [
        _release_work_order_operation_full_row(row)
        for row in cursor.fetchall()
    ]


def _list_existing_release_bindings_for_update_cursor(
    cursor: Any,
    work_order_id: str,
) -> list[JsonObject]:
    cursor.execute(
        SELECT_EXISTING_RELEASE_BINDINGS_FOR_UPDATE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    return [
        _work_order_operation_route_binding_row(row)
        for row in cursor.fetchall()
    ]


def _list_work_order_release_evidence_cursor(
    cursor: Any,
    work_order_id: str,
) -> JsonObject:
    cursor.execute(
        SELECT_WORK_ORDER_RELEASE_EVIDENCE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    row = cursor.fetchone()
    return _work_order_release_evidence_row(row) if row else {
        "execution_state_count": 0,
        "operation_step_count": 0,
        "operation_event_count": 0,
        "operation_approval_count": 0,
        "production_flow_event_count": 0,
    }


def _select_initial_queue_cursor(
    cursor: Any,
    work_order_id: str,
    work_order_operation_id: str,
) -> list[JsonObject]:
    cursor.execute(
        SELECT_INITIAL_QUEUE_FOR_UPDATE_CURSOR_SQL,
        {
            "work_order_id": work_order_id,
            "work_order_operation_id": work_order_operation_id,
        },
    )
    return [
        _work_order_release_initial_queue_row(row)
        for row in cursor.fetchall()
    ]


def _list_existing_work_order_queue_for_update_cursor(
    cursor: Any,
    work_order_id: str,
) -> list[JsonObject]:
    cursor.execute(
        SELECT_WORK_ORDER_QUEUE_FOR_UPDATE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    return [
        _work_order_release_initial_queue_row(row)
        for row in cursor.fetchall()
    ]


def _lock_station_queue_scope_cursor(
    cursor: Any,
    station_code: str,
) -> JsonObject:
    parameters = {"station_code": station_code}
    cursor.execute(LOCK_STATION_QUEUE_ADVISORY_CURSOR_SQL, parameters)
    cursor.fetchone()
    cursor.execute(SELECT_STATION_QUEUE_FOR_UPDATE_CURSOR_SQL, parameters)
    rows = [
        _work_order_release_initial_queue_row(row)
        for row in cursor.fetchall()
    ]
    cursor.execute(SELECT_NEXT_STATION_QUEUE_RANK_CURSOR_SQL, parameters)
    rank_row = cursor.fetchone()
    return {
        "station_code": station_code,
        "next_queue_rank": max(
            0,
            _safe_int(_field(rank_row, 0, "next_queue_rank"), 0),
        ),
        "rows": rows,
    }


def _insert_work_order_route_release_cursor(
    cursor: Any,
    release_snapshot: JsonObject,
) -> JsonObject:
    parameter_names = (
        "release_id", "order_id", "process_route_id", "route_code",
        "route_version", "release_mode", "release_source", "released_by",
        "route_operation_count", "operation_set_digest", "metadata",
    )
    parameters = {name: release_snapshot[name] for name in parameter_names}
    parameters["metadata"] = _jsonb(_json_safe(parameters.get("metadata") or {}))
    cursor.execute(INSERT_WORK_ORDER_ROUTE_RELEASE_CURSOR_SQL, parameters)
    return _work_order_route_release_row(cursor.fetchone())


def _insert_route_generated_work_order_operation_cursor(
    cursor: Any,
    operation_snapshot: JsonObject,
) -> JsonObject:
    parameter_names = (
        "work_order_operation_id", "order_id", "operation_no", "operation_code",
        "operation_name", "sequence_no", "station_code", "status",
        "planned_quantity", "uom_code", "payload", "metadata",
    )
    parameters = {name: operation_snapshot[name] for name in parameter_names}
    parameters["payload"] = _jsonb(_json_safe(parameters.get("payload") or {}))
    parameters["metadata"] = _jsonb(_json_safe(parameters.get("metadata") or {}))
    cursor.execute(INSERT_ROUTE_GENERATED_WORK_ORDER_OPERATION_CURSOR_SQL, parameters)
    return _release_work_order_operation_full_row(cursor.fetchone())


def _insert_work_order_operation_route_binding_cursor(
    cursor: Any,
    binding_snapshot: JsonObject,
) -> JsonObject:
    parameter_names = (
        "binding_id", "work_order_operation_id", "route_operation_id",
        "binding_source", "bound_by", "metadata",
    )
    parameters = {name: binding_snapshot[name] for name in parameter_names}
    parameters["metadata"] = _jsonb(_json_safe(parameters.get("metadata") or {}))
    cursor.execute(INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_CURSOR_SQL, parameters)
    return _work_order_operation_route_binding_row(cursor.fetchone())


def _insert_initial_station_queue_cursor(
    cursor: Any,
    queue_snapshot: JsonObject,
) -> JsonObject:
    parameter_names = (
        "station_code", "order_id", "queue_rank", "status", "source",
        "payload", "metadata", "work_order_operation_id",
    )
    parameters = {name: queue_snapshot[name] for name in parameter_names}
    parameters["payload"] = _jsonb(_json_safe(parameters.get("payload") or {}))
    parameters["metadata"] = _jsonb(_json_safe(parameters.get("metadata") or {}))
    cursor.execute(INSERT_INITIAL_STATION_QUEUE_CURSOR_SQL, parameters)
    return _work_order_release_initial_queue_row(cursor.fetchone())


def _update_work_order_released_state_cursor(
    cursor: Any,
    work_order_id: str,
) -> JsonObject | None:
    cursor.execute(
        UPDATE_WORK_ORDER_RELEASED_STATE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    row = cursor.fetchone()
    return _release_work_order_full_row(row) if row else None


def _assemble_route_generated_operation_snapshots(
    *,
    release_id: str,
    work_order_id: str,
    process_route: JsonObject,
    route_item: JsonObject,
    route_operations: list[JsonObject],
    target_quantity: Any,
) -> list[JsonObject]:
    ordered = sorted(
        route_operations,
        key=lambda item: (item.get("sequence_no"), item.get("route_operation_id")),
    )
    snapshots: list[JsonObject] = []
    for index, route_operation in enumerate(ordered):
        route_operation_id = _text(route_operation.get("route_operation_id"))
        sequence_no = _required_positive_int(
            route_operation.get("sequence_no"), field_name="SEQUENCE_NO"
        )
        snapshots.append({
            "work_order_operation_id": _derive_work_order_release_operation_id(
                release_id,
                route_operation_id,
            ),
            "order_id": work_order_id,
            "mesql_work_order_operation_id": None,
            "operation_no": sequence_no,
            "operation_code": _text(route_operation.get("operation_code")),
            "operation_name": _text(route_operation.get("operation_name")),
            "sequence_no": sequence_no,
            "station_code": _text(route_operation.get("station_code")),
            "status": "queued" if index == 0 else "planned",
            "planned_quantity": target_quantity,
            "good_quantity": 0,
            "scrap_quantity": 0,
            "uom_code": _text(route_item.get("unit")),
            "started_at": None,
            "completed_at": None,
            "payload": {},
            "metadata": {
                "source": "work_order_release",
                "release_id": release_id,
                "process_route_id": _text(process_route.get("route_id")),
                "route_code": _text(process_route.get("route_code")),
                "route_version": process_route.get("version"),
                "route_operation_id": route_operation_id,
            },
        })
    return _json_safe(snapshots)


def _build_route_generated_operation_snapshots(
    *,
    release_id: str,
    work_order_id: str,
    process_route: JsonObject,
    route_item: JsonObject,
    route_operations: list[JsonObject],
    target_quantity: Any,
) -> list[JsonObject]:
    _validate_route_generated_config(process_route, route_item, route_operations)
    if (
        isinstance(target_quantity, bool)
        or not isinstance(target_quantity, (int, float, Decimal))
        or target_quantity <= 0
    ):
        raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)
    return _assemble_route_generated_operation_snapshots(
        release_id=release_id,
        work_order_id=work_order_id,
        process_route=process_route,
        route_item=route_item,
        route_operations=route_operations,
        target_quantity=target_quantity,
    )


def _build_work_order_release_binding_snapshots(
    *,
    release_id: str,
    released_by: str,
    route_operations: list[JsonObject],
    operation_snapshots: list[JsonObject],
) -> list[JsonObject]:
    if len(route_operations) != len(operation_snapshots):
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH", status_code=409
        )
    route_by_sequence = {
        operation["sequence_no"]: operation for operation in route_operations
    }
    if len(route_by_sequence) != len(route_operations):
        raise MesqlV2Error("WORK_ORDER_RELEASE_MAPPING_CONFLICT", status_code=409)
    snapshots = []
    seen_operation_ids: set[str] = set()
    for operation in operation_snapshots:
        route_operation = route_by_sequence.get(operation["sequence_no"])
        if route_operation is None:
            raise MesqlV2Error("WORK_ORDER_RELEASE_MAPPING_CONFLICT", status_code=409)
        operation_id = _text(operation["work_order_operation_id"])
        route_operation_id = _text(route_operation["route_operation_id"])
        if (
            not operation_id
            or operation_id in seen_operation_ids
            or operation_id != _derive_work_order_release_operation_id(
                release_id,
                route_operation_id,
            )
            or _text((operation.get("metadata") or {}).get("route_operation_id"))
            != route_operation_id
        ):
            raise MesqlV2Error("WORK_ORDER_RELEASE_MAPPING_CONFLICT", status_code=409)
        seen_operation_ids.add(operation_id)
        snapshots.append({
            "binding_id": _derive_work_order_release_binding_id(
                release_id,
                route_operation_id,
            ),
            "work_order_operation_id": operation_id,
            "route_operation_id": route_operation_id,
            "binding_source": "work_order_release",
            "bound_by": released_by,
            "metadata": {"release_id": release_id},
        })
    return snapshots


def _build_initial_queue_snapshot(
    *,
    release_id: str,
    operation_snapshot: JsonObject,
    queue_rank: int,
) -> JsonObject:
    if isinstance(queue_rank, bool) or not isinstance(queue_rank, int) or queue_rank < 0:
        raise MesqlV2Error("WORK_ORDER_RELEASE_QUEUE_CONFLICT", status_code=409)
    return {
        "station_code": _text(operation_snapshot["station_code"]),
        "order_id": _text(operation_snapshot["order_id"]),
        "queue_rank": queue_rank,
        "status": "queued",
        "source": "work_order_release",
        "payload": {
            "order_id": _text(operation_snapshot["order_id"]),
            "work_order_operation_id": _text(
                operation_snapshot["work_order_operation_id"]
            ),
            "operation_no": operation_snapshot["operation_no"],
            "sequence_no": operation_snapshot["sequence_no"],
            "station_code": _text(operation_snapshot["station_code"]),
            "status": "queued",
        },
        "metadata": {
            "source": "work_order_release",
            "release_id": release_id,
        },
        "work_order_operation_id": _text(
            operation_snapshot["work_order_operation_id"]
        ),
    }


def _validate_route_generated_config(
    process_route: JsonObject | None,
    route_item: JsonObject | None,
    route_operations: list[JsonObject],
) -> None:
    if process_route is None:
        raise MesqlV2Error("PROCESS_ROUTE_NOT_FOUND", status_code=404)
    if not route_operations:
        raise MesqlV2Error("ROUTE_OPERATION_NOT_FOUND", status_code=404)
    if route_item is None:
        raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)
    route_id = _text(process_route.get("route_id"))
    route_code = _text(process_route.get("route_code"))
    route_version = process_route.get("version")
    route_item_code = _upper(process_route.get("item_code"))
    if (
        not route_id
        or not route_code
        or isinstance(route_version, bool)
        or not isinstance(route_version, int)
        or route_version <= 0
        or not route_item_code
        or process_route.get("active") is not True
    ):
        raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)
    if (
        route_item.get("active") is not True
        or not _text(route_item.get("unit"))
        or _upper(route_item.get("item_code")) != route_item_code
    ):
        raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)

    seen_sequences: set[int] = set()
    seen_ids: set[str] = set()
    for operation in route_operations:
        if operation.get("active") is not True:
            raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)
        sequence_no = operation.get("sequence_no")
        if isinstance(sequence_no, bool) or not isinstance(sequence_no, int):
            raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)
        route_operation_id = _text(operation.get("route_operation_id"))
        if (
            sequence_no <= 0
            or not route_operation_id
            or _text(operation.get("route_code")) != route_code
            or operation.get("route_version") != route_version
            or not _text(operation.get("operation_code"))
            or not _text(operation.get("operation_name"))
            or not _text(operation.get("station_code"))
        ):
            raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)
        if sequence_no in seen_sequences or route_operation_id in seen_ids:
            raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)
        seen_sequences.add(sequence_no)
        seen_ids.add(route_operation_id)


def _validate_route_generated_replay_config(
    process_route: JsonObject,
    route_item: JsonObject | None,
    route_operations: list[JsonObject],
) -> None:
    if route_item is None:
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH", status_code=409
        )
    if not route_operations:
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH", status_code=409
        )
    route_code = _text(process_route.get("route_code"))
    route_version = process_route.get("version")
    seen_sequences: set[int] = set()
    seen_ids: set[str] = set()
    for operation in route_operations:
        sequence_no = operation.get("sequence_no")
        route_operation_id = _text(operation.get("route_operation_id"))
        if (
            isinstance(sequence_no, bool)
            or not isinstance(sequence_no, int)
            or sequence_no <= 0
            or not route_operation_id
            or sequence_no in seen_sequences
            or route_operation_id in seen_ids
            or _text(operation.get("route_code")) != route_code
            or operation.get("route_version") != route_version
        ):
            raise MesqlV2Error(
                "WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH",
                status_code=409,
            )
        seen_sequences.add(sequence_no)
        seen_ids.add(route_operation_id)


def _validate_route_generated_release_eligibility(
    *,
    work_order: JsonObject | None,
    process_route: JsonObject | None,
    route_item: JsonObject | None,
    route_operations: list[JsonObject],
    existing_operations: list[JsonObject],
    existing_bindings: list[JsonObject],
    existing_queue: list[JsonObject],
    evidence: JsonObject,
) -> None:
    if work_order is None:
        raise MesqlV2Error("WORK_ORDER_NOT_FOUND", status_code=404)
    _validate_route_generated_config(process_route, route_item, route_operations)
    target_quantity = work_order.get("target_quantity")
    valid_quantity = (
        not isinstance(target_quantity, bool)
        and isinstance(target_quantity, (int, float, Decimal))
        and target_quantity > 0
    )
    releasable = (
        _lower(work_order.get("status")) in {"planned", "queued"}
        and _upper(work_order.get("product_code"))
        == _upper(process_route.get("item_code"))
        and _upper(route_item.get("item_code"))
        == _upper(process_route.get("item_code"))
        and valid_quantity
        and work_order.get("started_at") is None
        and work_order.get("completed_at") is None
        and not existing_operations
        and not existing_bindings
        and not existing_queue
        and not any(_safe_int(value, 0) for value in evidence.values())
    )
    if not releasable:
        raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)


def _compare_immutable_release_request(
    persisted: JsonObject | None,
    expected: JsonObject,
) -> bool:
    fields = (
        "release_id", "order_id", "process_route_id", "route_code",
        "route_version", "release_mode", "release_source", "released_by",
        "route_operation_count", "operation_set_digest", "metadata",
    )
    return persisted is not None and all(
        _json_safe(persisted.get(field)) == _json_safe(expected.get(field))
        for field in fields
    )


def _compare_static_operation_snapshots(
    persisted: list[JsonObject],
    expected: list[JsonObject],
) -> bool:
    fields = (
        "work_order_operation_id", "order_id", "mesql_work_order_operation_id",
        "operation_no", "operation_code", "operation_name", "sequence_no",
        "station_code", "planned_quantity", "uom_code", "payload", "metadata",
    )
    normalize = lambda row: tuple(_json_safe(row.get(field)) for field in fields)
    return sorted(map(normalize, persisted), key=lambda row: str(row[0])) == sorted(
        map(normalize, expected), key=lambda row: str(row[0])
    )


def _compare_complete_binding_set(
    persisted: list[JsonObject],
    expected: list[JsonObject],
) -> bool:
    fields = (
        "binding_id", "work_order_operation_id", "route_operation_id",
        "binding_source", "bound_by", "metadata",
    )
    normalize = lambda row: tuple(_json_safe(row.get(field)) for field in fields)
    return sorted(map(normalize, persisted), key=lambda row: str(row[0])) == sorted(
        map(normalize, expected), key=lambda row: str(row[0])
    )


def _compare_initial_queue_identity(
    persisted: JsonObject | None,
    expected: JsonObject,
) -> bool:
    fields = (
        "station_code", "order_id", "source", "payload", "metadata",
        "work_order_operation_id",
    )
    return persisted is not None and all(
        _json_safe(persisted.get(field)) == _json_safe(expected.get(field))
        for field in fields
    )


def _read_work_order_release_snapshot_cursor(
    cursor: Any,
    work_order_id: str,
) -> JsonObject:
    snapshot = _get_work_order_release_snapshot_with_cursor(cursor, work_order_id)
    if snapshot is None:
        return {
            "release": None,
            "work_order": None,
            "operations": [],
            "bindings": [],
            "initial_queue": None,
        }
    return snapshot


def _validate_work_order_release_invariants_cursor(
    cursor: Any,
    expected_snapshot: JsonObject,
) -> JsonObject:
    work_order_id = _text(
        expected_snapshot.get("work_order_id")
        or expected_snapshot.get("release", {}).get("order_id")
    )
    release = _get_work_order_route_release_with_cursor(cursor, work_order_id)
    work_order = _select_work_order_for_release_cursor(cursor, work_order_id)
    operations = _list_existing_work_order_operations_for_update_cursor(
        cursor, work_order_id
    )
    bindings = _list_existing_release_bindings_for_update_cursor(cursor, work_order_id)
    initial_operation = min(
        operations,
        key=lambda item: (
            item.get("sequence_no"),
            _text(item.get("work_order_operation_id")),
        ),
    ) if operations else None
    queue_rows = (
        _select_initial_queue_cursor(
            cursor,
            work_order_id,
            _text(initial_operation["work_order_operation_id"]),
        )
        if initial_operation
        else []
    )
    persisted = {
        "release": release,
        "work_order": work_order,
        "operations": operations,
        "bindings": bindings,
        "initial_queue": queue_rows[0] if len(queue_rows) == 1 else None,
    }
    if not _compare_immutable_release_request(
        persisted.get("release"), expected_snapshot["release"]
    ):
        raise MesqlV2Error("WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT", status_code=409)
    expected_operations = expected_snapshot.get("operations", [])
    if len(persisted["operations"]) != len(expected_operations):
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH", status_code=409
        )
    if not _compare_static_operation_snapshots(
        persisted["operations"], expected_operations
    ):
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH", status_code=409
        )
    if persisted["release"].get("route_operation_count") != len(
        persisted["operations"]
    ):
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH", status_code=409
        )
    expected_bindings = expected_snapshot.get("bindings", [])
    if len(persisted["bindings"]) != len(expected_bindings):
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT", status_code=409
        )
    if not _compare_complete_binding_set(persisted["bindings"], expected_bindings):
        raise MesqlV2Error("WORK_ORDER_RELEASE_MAPPING_CONFLICT", status_code=409)
    binding_by_operation_id = {
        _text(binding.get("work_order_operation_id")): binding
        for binding in persisted["bindings"]
    }
    digest_pairs = []
    for operation in persisted["operations"]:
        operation_id = _text(operation.get("work_order_operation_id"))
        binding = binding_by_operation_id.get(operation_id)
        if binding is None:
            raise MesqlV2Error(
                "WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT", status_code=409
            )
        digest_pairs.append({
            "sequence_no": operation.get("sequence_no"),
            "route_operation_id": binding.get("route_operation_id"),
            "work_order_operation_id": operation_id,
        })
    computed_digest = _compute_work_order_release_operation_set_digest(
        process_route_id=persisted["release"].get("process_route_id"),
        route_code=persisted["release"].get("route_code"),
        route_version=persisted["release"].get("route_version"),
        release_mode=persisted["release"].get("release_mode"),
        pairs=digest_pairs,
    )
    if computed_digest != persisted["release"].get("operation_set_digest"):
        raise MesqlV2Error("WORK_ORDER_RELEASE_MAPPING_CONFLICT", status_code=409)
    if not _compare_initial_queue_identity(
        persisted.get("initial_queue"), expected_snapshot["initial_queue"]
    ):
        raise MesqlV2Error("WORK_ORDER_RELEASE_QUEUE_CONFLICT", status_code=409)
    if expected_snapshot.get("released") is True:
        if _lower((persisted.get("work_order") or {}).get("status")) != "queued":
            raise MesqlV2Error("WORK_ORDER_RELEASE_NOT_RELEASABLE", status_code=409)
        expected_by_id = {
            _text(item.get("work_order_operation_id")): item
            for item in expected_operations
        }
        mutable_operation_fields = (
            "status", "good_quantity", "scrap_quantity", "started_at", "completed_at"
        )
        for operation in persisted["operations"]:
            expected = expected_by_id.get(
                _text(operation.get("work_order_operation_id"))
            )
            if expected is None or any(
                _json_safe(operation.get(field)) != _json_safe(expected.get(field))
                for field in mutable_operation_fields
            ):
                raise MesqlV2Error(
                    "WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH",
                    status_code=409,
                )
        queue = persisted.get("initial_queue") or {}
        expected_queue = expected_snapshot["initial_queue"]
        if (
            queue.get("status") != expected_queue.get("status")
            or queue.get("queue_rank") != expected_queue.get("queue_rank")
        ):
            raise MesqlV2Error("WORK_ORDER_RELEASE_QUEUE_CONFLICT", status_code=409)
    return persisted


def _normalize_work_order_release_request(
    *,
    release_id: Any,
    work_order_id: Any,
    route_code: Any,
    route_version: Any,
    release_source: Any,
    released_by: Any,
    mode: Any,
    operation_bindings: Any,
    metadata: Any,
) -> JsonObject:
    normalized_release_id = _required_case_preserving_text(
        release_id, field_name="RELEASE_ID"
    )
    normalized_work_order_id = _required_case_preserving_text(
        work_order_id, field_name="WORK_ORDER_ID"
    )
    normalized_route_code = _upper(
        _required_case_preserving_text(route_code, field_name="ROUTE_CODE")
    )
    normalized_route_version = _required_positive_int(
        route_version, field_name="ROUTE_VERSION"
    )
    normalized_release_source = _lower(
        _required_case_preserving_text(
            release_source, field_name="RELEASE_SOURCE"
        )
    )
    normalized_released_by = _required_case_preserving_text(
        released_by, field_name="RELEASED_BY"
    )
    normalized_mode = _lower(
        _required_case_preserving_text(mode, field_name="RELEASE_MODE")
    )
    if normalized_mode not in WORK_ORDER_RELEASE_MODES:
        raise MesqlV2Error("RELEASE_MODE_INVALID", status_code=400)
    if (
        normalized_mode != "route_generated"
        or normalized_release_source != "local_planning"
    ):
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_MODE_NOT_ENABLED", status_code=409
        )
    if operation_bindings not in (None, []):
        raise MesqlV2Error("OPERATION_BINDINGS_NOT_ALLOWED", status_code=400)
    if metadata is None:
        normalized_metadata: JsonObject = {}
    elif isinstance(metadata, dict):
        try:
            normalized_metadata = _json_safe(metadata)
            json.dumps(normalized_metadata, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            raise MesqlV2Error(
                "RELEASE_METADATA_INVALID", status_code=400
            ) from None
    else:
        raise MesqlV2Error("RELEASE_METADATA_INVALID", status_code=400)
    return {
        "release_id": normalized_release_id,
        "work_order_id": normalized_work_order_id,
        "route_code": normalized_route_code,
        "route_version": normalized_route_version,
        "release_source": normalized_release_source,
        "released_by": normalized_released_by,
        "mode": normalized_mode,
        "metadata": normalized_metadata,
    }


def _postgres_error_sqlstate(error: BaseException) -> str | None:
    for candidate in (error, error.__cause__, error.__context__):
        if candidate is None:
            continue
        sqlstate = getattr(candidate, "sqlstate", None) or getattr(
            candidate, "pgcode", None
        )
        if sqlstate:
            return _text(sqlstate)
        diagnostic = getattr(candidate, "diag", None)
        sqlstate = getattr(diagnostic, "sqlstate", None)
        if sqlstate:
            return _text(sqlstate)
    return None


def _postgres_constraint_name(error: BaseException) -> str | None:
    for candidate in (error, error.__cause__, error.__context__):
        if candidate is None:
            continue
        diagnostic = getattr(candidate, "diag", None)
        constraint_name = _nullable_text(
            getattr(diagnostic, "constraint_name", None)
        )
        if constraint_name:
            return constraint_name
    return None


def _classify_release_identity_conflicts(
    releases: list[JsonObject],
    request: JsonObject,
) -> JsonObject | None:
    release_by_id = next(
        (
            release
            for release in releases
            if release.get("release_id") == request["release_id"]
        ),
        None,
    )
    release_by_order = next(
        (
            release
            for release in releases
            if release.get("order_id") == request["work_order_id"]
        ),
        None,
    )
    if (
        release_by_id is not None
        and release_by_id.get("order_id") != request["work_order_id"]
    ):
        raise MesqlV2Error(
            "WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT", status_code=409
        )
    if (
        release_by_order is not None
        and release_by_order.get("release_id") != request["release_id"]
    ):
        raise MesqlV2Error("WORK_ORDER_ROUTE_ALREADY_RELEASED", status_code=409)
    release = release_by_id or release_by_order
    if release is None:
        return None
    if (
        release.get("route_code") != request["route_code"]
        or release.get("route_version") != request["route_version"]
    ):
        raise MesqlV2Error("WORK_ORDER_ROUTE_VERSION_CONFLICT", status_code=409)
    if release.get("release_mode") != request["mode"]:
        raise MesqlV2Error("WORK_ORDER_RELEASE_MODE_CONFLICT", status_code=409)
    if (
        release.get("release_source") != request["release_source"]
        or release.get("released_by") != request["released_by"]
        or _json_safe(release.get("metadata") or {}) != request["metadata"]
    ):
        raise MesqlV2Error(
            "WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT", status_code=409
        )
    return release


def _prepare_work_order_release_context_cursor(
    cursor: Any,
    request: JsonObject,
) -> JsonObject:
    work_order = _select_work_order_for_release_cursor(
        cursor, request["work_order_id"]
    )
    releases = _select_releases_for_update_cursor(
        cursor,
        request["work_order_id"],
        request["release_id"],
    )
    existing_release = _classify_release_identity_conflicts(releases, request)
    if work_order is None:
        raise MesqlV2Error("WORK_ORDER_NOT_FOUND", status_code=404)

    process_route = _select_exact_process_route_cursor(
        cursor,
        request["route_code"],
        request["route_version"],
    )
    if process_route is None:
        raise MesqlV2Error("PROCESS_ROUTE_NOT_FOUND", status_code=404)
    if (
        existing_release is not None
        and existing_release.get("process_route_id") != process_route.get("route_id")
    ):
        raise MesqlV2Error("WORK_ORDER_ROUTE_VERSION_CONFLICT", status_code=409)
    route_item = _select_route_item_cursor(cursor, process_route.get("item_code"))
    route_operations = _list_process_route_operations_cursor(
        cursor,
        _text(process_route.get("route_id")),
    )
    if existing_release is None:
        _validate_route_generated_config(process_route, route_item, route_operations)
    else:
        _validate_route_generated_replay_config(
            process_route, route_item, route_operations
        )

    existing_operations = (
        _list_existing_work_order_operations_for_update_cursor(
            cursor, request["work_order_id"]
        )
    )
    existing_bindings = _list_existing_release_bindings_for_update_cursor(
        cursor, request["work_order_id"]
    )
    evidence = _list_work_order_release_evidence_cursor(
        cursor, request["work_order_id"]
    )
    existing_queue = _list_existing_work_order_queue_for_update_cursor(
        cursor, request["work_order_id"]
    )

    operation_snapshots = _assemble_route_generated_operation_snapshots(
        release_id=request["release_id"],
        work_order_id=request["work_order_id"],
        process_route=process_route,
        route_item=route_item,
        route_operations=route_operations,
        target_quantity=work_order.get("target_quantity"),
    )
    binding_snapshots = _build_work_order_release_binding_snapshots(
        release_id=request["release_id"],
        released_by=request["released_by"],
        route_operations=route_operations,
        operation_snapshots=operation_snapshots,
    )
    binding_by_operation_id = {
        binding["work_order_operation_id"]: binding
        for binding in binding_snapshots
    }
    digest_pairs = [
        {
            "sequence_no": operation["sequence_no"],
            "route_operation_id": binding_by_operation_id[
                operation["work_order_operation_id"]
            ]["route_operation_id"],
            "work_order_operation_id": operation["work_order_operation_id"],
        }
        for operation in operation_snapshots
    ]
    operation_set_digest = _compute_work_order_release_operation_set_digest(
        process_route_id=process_route["route_id"],
        route_code=process_route["route_code"],
        route_version=process_route["version"],
        release_mode=request["mode"],
        pairs=digest_pairs,
    )
    release_snapshot = {
        "release_id": request["release_id"],
        "order_id": request["work_order_id"],
        "process_route_id": process_route["route_id"],
        "route_code": process_route["route_code"],
        "route_version": process_route["version"],
        "release_mode": request["mode"],
        "release_source": request["release_source"],
        "released_by": request["released_by"],
        "route_operation_count": len(operation_snapshots),
        "operation_set_digest": operation_set_digest,
        "metadata": request["metadata"],
    }
    initial_queue_snapshot = _build_initial_queue_snapshot(
        release_id=request["release_id"],
        operation_snapshot=operation_snapshots[0],
        queue_rank=(
            _safe_int(existing_queue[0].get("queue_rank"), 0)
            if len(existing_queue) == 1
            else 0
        ),
    )
    return {
        "work_order": work_order,
        "existing_release": existing_release,
        "process_route": process_route,
        "route_item": route_item,
        "route_operations": route_operations,
        "existing_operations": existing_operations,
        "existing_bindings": existing_bindings,
        "evidence": evidence,
        "existing_queue": existing_queue,
        "release_snapshot": release_snapshot,
        "operation_snapshots": operation_snapshots,
        "binding_snapshots": binding_snapshots,
        "initial_queue_snapshot": initial_queue_snapshot,
    }


def _validate_existing_work_order_release_replay(
    context: JsonObject,
) -> None:
    release = context["existing_release"]
    expected_release = context["release_snapshot"]
    if release.get("process_route_id") != expected_release["process_route_id"]:
        raise MesqlV2Error("WORK_ORDER_ROUTE_VERSION_CONFLICT", status_code=409)
    expected_operations = context["operation_snapshots"]
    existing_operations = context["existing_operations"]
    if (
        release.get("route_operation_count") != len(expected_operations)
        or len(existing_operations) != len(expected_operations)
    ):
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH", status_code=409
        )
    if not _compare_static_operation_snapshots(
        existing_operations, expected_operations
    ):
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH", status_code=409
        )
    expected_bindings = context["binding_snapshots"]
    existing_bindings = context["existing_bindings"]
    expected_operation_ids = {
        binding["work_order_operation_id"] for binding in expected_bindings
    }
    existing_operation_ids = {
        _text(binding.get("work_order_operation_id"))
        for binding in existing_bindings
    }
    if (
        len(existing_bindings) != len(expected_bindings)
        or existing_operation_ids != expected_operation_ids
    ):
        raise MesqlV2Error(
            "WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT", status_code=409
        )
    if not _compare_complete_binding_set(existing_bindings, expected_bindings):
        raise MesqlV2Error("WORK_ORDER_RELEASE_MAPPING_CONFLICT", status_code=409)
    if release.get("operation_set_digest") != expected_release[
        "operation_set_digest"
    ]:
        raise MesqlV2Error("WORK_ORDER_RELEASE_MAPPING_CONFLICT", status_code=409)
    existing_queue = context["existing_queue"]
    if len(existing_queue) != 1 or not _compare_initial_queue_identity(
        existing_queue[0], context["initial_queue_snapshot"]
    ):
        raise MesqlV2Error("WORK_ORDER_RELEASE_QUEUE_CONFLICT", status_code=409)


def _work_order_release_response_cursor(
    cursor: Any,
    work_order_id: str,
    *,
    released: bool,
) -> JsonObject:
    snapshot = _read_work_order_release_snapshot_cursor(cursor, work_order_id)
    if snapshot.get("release") is None:
        raise MesqlV2Error("WORK_ORDER_RELEASE_MAPPING_CONFLICT", status_code=409)
    return _json_safe({"released": released, **snapshot})


def _release_work_order_to_route_cursor(
    cursor: Any,
    request: JsonObject,
) -> JsonObject:
    context = _prepare_work_order_release_context_cursor(cursor, request)
    if context["existing_release"] is not None:
        _validate_existing_work_order_release_replay(context)
        expected_snapshot = {
            "work_order_id": request["work_order_id"],
            "release": context["release_snapshot"],
            "operations": context["operation_snapshots"],
            "bindings": context["binding_snapshots"],
            "initial_queue": context["initial_queue_snapshot"],
            "released": False,
        }
        _validate_work_order_release_invariants_cursor(cursor, expected_snapshot)
        return _work_order_release_response_cursor(
            cursor, request["work_order_id"], released=False
        )

    _validate_route_generated_release_eligibility(
        work_order=context["work_order"],
        process_route=context["process_route"],
        route_item=context["route_item"],
        route_operations=context["route_operations"],
        existing_operations=context["existing_operations"],
        existing_bindings=context["existing_bindings"],
        existing_queue=context["existing_queue"],
        evidence=context["evidence"],
    )
    initial_operation = context["operation_snapshots"][0]
    queue_scope = _lock_station_queue_scope_cursor(
        cursor, initial_operation["station_code"]
    )
    initial_queue_snapshot = _build_initial_queue_snapshot(
        release_id=request["release_id"],
        operation_snapshot=initial_operation,
        queue_rank=queue_scope["next_queue_rank"],
    )
    _insert_work_order_route_release_cursor(cursor, context["release_snapshot"])
    for operation_snapshot in context["operation_snapshots"]:
        _insert_route_generated_work_order_operation_cursor(
            cursor, operation_snapshot
        )
    for binding_snapshot in context["binding_snapshots"]:
        _insert_work_order_operation_route_binding_cursor(
            cursor, binding_snapshot
        )
    _insert_initial_station_queue_cursor(cursor, initial_queue_snapshot)
    _update_work_order_released_state_cursor(cursor, request["work_order_id"])
    expected_snapshot = {
        "work_order_id": request["work_order_id"],
        "release": context["release_snapshot"],
        "operations": context["operation_snapshots"],
        "bindings": context["binding_snapshots"],
        "initial_queue": initial_queue_snapshot,
        "released": True,
    }
    _validate_work_order_release_invariants_cursor(cursor, expected_snapshot)
    return _work_order_release_response_cursor(
        cursor, request["work_order_id"], released=True
    )


def _run_work_order_release_transaction(
    config: AppConfig,
    request: JsonObject,
) -> JsonObject:
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                cursor.execute(SET_WORK_ORDER_RELEASE_TRANSACTION_ISOLATION_SQL)
                return _release_work_order_to_route_cursor(cursor, request)


def _recover_work_order_release_unique_violation(
    config: AppConfig,
    request: JsonObject,
    original_error: BaseException,
) -> JsonObject:
    constraint_name = _postgres_constraint_name(original_error)
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                cursor.execute(SET_WORK_ORDER_RELEASE_TRANSACTION_ISOLATION_SQL)
                context = _prepare_work_order_release_context_cursor(cursor, request)
                if context["existing_release"] is not None:
                    _validate_existing_work_order_release_replay(context)
                    expected_snapshot = {
                        "work_order_id": request["work_order_id"],
                        "release": context["release_snapshot"],
                        "operations": context["operation_snapshots"],
                        "bindings": context["binding_snapshots"],
                        "initial_queue": context["initial_queue_snapshot"],
                        "released": False,
                    }
                    _validate_work_order_release_invariants_cursor(
                        cursor, expected_snapshot
                    )
                    return _work_order_release_response_cursor(
                        cursor, request["work_order_id"], released=False
                    )
                if constraint_name in WORK_ORDER_RELEASE_QUEUE_CONSTRAINTS:
                    raise MesqlV2Error(
                        "WORK_ORDER_RELEASE_QUEUE_CONFLICT", status_code=409
                    )
    raise original_error


def _binding_matches_request(binding: JsonObject, request: JsonObject) -> bool:
    return all(
        binding.get(field) == request.get(field)
        for field in (
            "binding_id",
            "work_order_operation_id",
            "route_operation_id",
            "binding_source",
            "bound_by",
            "metadata",
        )
    )


def _same_binding_identity(left: JsonObject, right: JsonObject) -> bool:
    return (
        left.get("binding_id") == right.get("binding_id")
        and left.get("work_order_operation_id")
        == right.get("work_order_operation_id")
    )


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


def _completion_bridge_applicability_row(row: Any) -> JsonObject:
    names = (
        "work_order_operation_id", "order_id", "operation_code",
        "sequence_no", "station_code", "status", "completed_at", "payload",
        "metadata",
    )
    result = {name: _field(row, index, name) for index, name in enumerate(names)}
    if result["payload"] is None:
        result["payload"] = {}
    if result["metadata"] is None:
        result["metadata"] = {}
    return _json_safe(result)


def _completion_bridge_execution_state_row(row: Any) -> JsonObject:
    names = (
        "execution_state_pk", "execution_state_id", "work_order_operation_id",
        "work_order_id", "station_code", "operation_code", "execution_status",
        "operation_completion_policy", "current_step_code", "started_at",
        "evidence_completed_at", "pending_final_approval_at", "closed_at",
        "last_event_id", "last_approval_id", "created_at", "updated_at",
        "metadata",
    )
    result = {name: _field(row, index, name) for index, name in enumerate(names)}
    result["metadata"] = result["metadata"] or {}
    return _json_safe(result)


def _completion_bridge_runtime_step_row(row: Any) -> JsonObject:
    names = (
        "work_order_operation_step_pk", "work_order_operation_step_id",
        "work_order_operation_id", "work_order_id", "operation_code",
        "step_code", "step_no", "station_code", "status", "started_at",
        "completed_at", "started_by_event_id", "completed_by_event_id",
        "required_for_completion", "records_duration",
        "approval_required_after_finish", "created_at", "updated_at",
        "metadata",
    )
    result = {name: _field(row, index, name) for index, name in enumerate(names)}
    result["metadata"] = result["metadata"] or {}
    return _json_safe(result)


def _select_completion_bridge_applicability_cursor(
    cursor: Any,
    work_order_operation_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_APPLICABILITY_CURSOR_SQL,
        {"work_order_operation_id": work_order_operation_id},
    )
    row = cursor.fetchone()
    return _completion_bridge_applicability_row(row) if row else None


def _is_completion_bridge_applicable(lifecycle_row: JsonObject | None) -> bool:
    if lifecycle_row is None:
        return False
    metadata = lifecycle_row.get("metadata")
    if not isinstance(metadata, dict):
        raise MesqlV2Error(
            "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT", status_code=409
        )
    source_present = "source" in metadata
    release_present = "release_id" in metadata
    source = metadata.get("source")
    release_id = metadata.get("release_id")
    if not source_present and not release_present:
        return False
    if (
        source == "work_order_release"
        and isinstance(release_id, str)
        and bool(release_id.strip())
    ):
        return True
    if source_present and source != "work_order_release" and not release_present:
        return False
    raise MesqlV2Error(
        "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT", status_code=409
    )


def _compare_completion_bridge_preflight_identity(
    preflight_lifecycle: JsonObject,
    authoritative_lifecycle: JsonObject,
) -> None:
    if not isinstance(preflight_lifecycle, dict) or not isinstance(
        authoritative_lifecycle, dict
    ):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
    for field_name in (
        "work_order_operation_id",
        "order_id",
        "operation_code",
        "sequence_no",
        "station_code",
    ):
        if _json_safe(preflight_lifecycle.get(field_name)) != _json_safe(
            authoritative_lifecycle.get(field_name)
        ):
            _completion_bridge_error(
                "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"
            )

    markers = []
    for lifecycle in (preflight_lifecycle, authoritative_lifecycle):
        metadata = lifecycle.get("metadata")
        if not isinstance(metadata, dict):
            _completion_bridge_error(
                "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"
            )
        source = metadata.get("source")
        release_id = metadata.get("release_id")
        if (
            source != "work_order_release"
            or not isinstance(release_id, str)
            or not release_id.strip()
        ):
            _completion_bridge_error(
                "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"
            )
        markers.append((source, release_id))
    if markers[0] != markers[1]:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")


def _get_completion_bridge_schema_readiness_cursor(cursor: Any) -> JsonObject:
    cursor.execute(SELECT_COMPLETION_BRIDGE_SCHEMA_READINESS_CURSOR_SQL)
    row = cursor.fetchone()
    release_ready = bool(_field(row, 0, "release_table_ready")) if row else False
    binding_ready = bool(_field(row, 1, "binding_table_ready")) if row else False
    return {
        "release_table_ready": release_ready,
        "binding_table_ready": binding_ready,
        "ready": release_ready and binding_ready,
    }


def _validate_completion_bridge_schema_readiness(readiness: JsonObject) -> None:
    if not isinstance(readiness, dict) or readiness.get("ready") is not True:
        raise MesqlV2Error(
            "RUNTIME_COMPLETION_BRIDGE_SCHEMA_NOT_READY", status_code=503
        )


def _select_completion_bridge_work_order_for_update_cursor(
    cursor: Any,
    work_order_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_WORK_ORDER_FOR_UPDATE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    row = cursor.fetchone()
    return _release_work_order_full_row(row) if row else None


def _select_completion_bridge_release_for_update_cursor(
    cursor: Any,
    work_order_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_RELEASE_FOR_UPDATE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    rows = cursor.fetchall()
    if len(rows) > 1:
        raise MesqlV2Error(
            "RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT", status_code=409
        )
    return _work_order_route_release_row(rows[0]) if rows else None


def _list_completion_bridge_operations_for_update_cursor(
    cursor: Any,
    work_order_id: str,
) -> list[JsonObject]:
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_OPERATIONS_FOR_UPDATE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    return [_release_work_order_operation_full_row(row) for row in cursor.fetchall()]


def _list_completion_bridge_bindings_for_update_cursor(
    cursor: Any,
    work_order_id: str,
) -> list[JsonObject]:
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_BINDINGS_FOR_UPDATE_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    return [_work_order_operation_route_binding_row(row) for row in cursor.fetchall()]


def _select_completion_bridge_execution_state_for_update_cursor(
    cursor: Any,
    work_order_operation_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_EXECUTION_STATE_FOR_UPDATE_CURSOR_SQL,
        {"work_order_operation_id": work_order_operation_id},
    )
    row = cursor.fetchone()
    return _completion_bridge_execution_state_row(row) if row else None


def _list_completion_bridge_runtime_steps_for_update_cursor(
    cursor: Any,
    work_order_operation_id: str,
) -> list[JsonObject]:
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_RUNTIME_STEPS_FOR_UPDATE_CURSOR_SQL,
        {"work_order_operation_id": work_order_operation_id},
    )
    return [_completion_bridge_runtime_step_row(row) for row in cursor.fetchall()]


def _normalize_completion_bridge_station_lock_set(
    current_station_code: Any,
    successor_station_code: Any | None = None,
) -> list[str]:
    values = [current_station_code]
    if successor_station_code is not None:
        values.append(successor_station_code)
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise MesqlV2Error(
                "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT", status_code=409
            )
        normalized.add(value)
    return sorted(normalized)


def _lock_completion_bridge_station_scopes_cursor(
    cursor: Any,
    station_codes: list[str],
) -> list[str]:
    if not isinstance(station_codes, (list, tuple)) or not station_codes:
        raise MesqlV2Error(
            "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT", status_code=409
        )
    normalized = _normalize_completion_bridge_station_lock_set(
        station_codes[0],
        None,
    )
    for value in station_codes[1:]:
        normalized = sorted(set(normalized + _normalize_completion_bridge_station_lock_set(value)))
    for station_code in normalized:
        cursor.execute(
            LOCK_COMPLETION_BRIDGE_STATION_SCOPE_CURSOR_SQL,
            {"station_code": station_code},
        )
        cursor.fetchone()
    return normalized


def _list_completion_bridge_station_queue_rows_for_update_cursor(
    cursor: Any,
    station_codes: list[str],
) -> list[JsonObject]:
    normalized = _lockless_completion_bridge_station_set(station_codes)
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_STATION_QUEUE_ROWS_FOR_UPDATE_CURSOR_SQL,
        {"station_codes": normalized},
    )
    return [_work_order_release_initial_queue_row(row) for row in cursor.fetchall()]


def _lockless_completion_bridge_station_set(station_codes: Any) -> list[str]:
    if not isinstance(station_codes, (list, tuple)) or not station_codes:
        raise MesqlV2Error(
            "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT", status_code=409
        )
    result: set[str] = set()
    for station_code in station_codes:
        if not isinstance(station_code, str) or not station_code.strip():
            raise MesqlV2Error(
                "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT", status_code=409
            )
        result.add(station_code)
    return sorted(result)


def _select_exact_completion_bridge_queue(
    rows: list[JsonObject],
    *,
    work_order_id: str,
    work_order_operation_id: str,
    station_code: str,
) -> JsonObject:
    matches = [
        row for row in list(rows)
        if row.get("order_id") == work_order_id
        and str(row.get("work_order_operation_id")) == work_order_operation_id
        and row.get("station_code") == station_code
    ]
    if not matches:
        return {"classification": "missing", "row": None, "matches": []}
    if len(matches) > 1:
        return {"classification": "duplicate", "row": None, "matches": _json_safe(matches)}
    return {"classification": "exact", "row": _json_safe(matches[0]), "matches": _json_safe(matches)}


def _compute_completion_bridge_next_queue_rank(
    station_rows: list[JsonObject],
    station_code: str,
) -> int:
    ranks = []
    for row in list(station_rows):
        if row.get("station_code") != station_code:
            continue
        if row.get("status") not in {"queued", "active", "pending_approval"}:
            continue
        rank = row.get("queue_rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
            raise MesqlV2Error(
                "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT", status_code=409
            )
        ranks.append(rank)
    return max(ranks) + 1 if ranks else 0


def _completion_bridge_error(detail: str) -> None:
    raise MesqlV2Error(detail, status_code=409)


def _validate_completion_bridge_lifecycle_set(
    release: JsonObject,
    lifecycle_operations: list[JsonObject],
) -> None:
    if not isinstance(release, dict) or not isinstance(lifecycle_operations, list):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT")
    expected_count = release.get("route_operation_count")
    if (
        isinstance(expected_count, bool)
        or not isinstance(expected_count, int)
        or expected_count != len(lifecycle_operations)
        or expected_count <= 0
    ):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT")
    release_id = release.get("release_id")
    order_id = release.get("order_id")
    seen_sequences: set[int] = set()
    seen_ids: set[str] = set()
    for operation in lifecycle_operations:
        sequence_no = operation.get("sequence_no")
        if (
            isinstance(sequence_no, bool)
            or not isinstance(sequence_no, int)
            or sequence_no <= 0
            or sequence_no in seen_sequences
        ):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_SEQUENCE_CONFLICT")
        operation_id = operation.get("work_order_operation_id")
        try:
            canonical_id = str(UUID(str(operation_id)))
        except (TypeError, ValueError, AttributeError):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
        if operation_id != canonical_id or canonical_id in seen_ids:
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
        metadata = operation.get("metadata")
        if not isinstance(metadata, dict):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
        route_operation_id = metadata.get("route_operation_id")
        if (
            operation.get("order_id") != order_id
            or metadata.get("source") != "work_order_release"
            or metadata.get("release_id") != release_id
            or metadata.get("process_route_id") != release.get("process_route_id")
            or metadata.get("route_code") != release.get("route_code")
            or metadata.get("route_version") != release.get("route_version")
            or not isinstance(route_operation_id, str)
            or not route_operation_id.strip()
            or canonical_id != _derive_work_order_release_operation_id(
                release_id, route_operation_id
            )
        ):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
        seen_sequences.add(sequence_no)
        seen_ids.add(canonical_id)


def _validate_completion_bridge_release_identity(
    release: JsonObject | None,
    lifecycle_operations: list[JsonObject],
) -> None:
    if not isinstance(release, dict):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT")
    required = (
        "release_id", "order_id", "process_route_id", "route_code",
        "route_version", "route_operation_count", "operation_set_digest",
    )
    if any(release.get(name) in (None, "") for name in required):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT")
    if release.get("release_mode") != "route_generated":
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT")
    _validate_completion_bridge_lifecycle_set(release, lifecycle_operations)


def _validate_completion_bridge_binding_set(
    release: JsonObject,
    lifecycle_operations: list[JsonObject],
    bindings: list[JsonObject],
) -> None:
    if not isinstance(bindings, list) or len(bindings) != len(lifecycle_operations):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT")
    operations_by_id = {
        operation["work_order_operation_id"]: operation
        for operation in lifecycle_operations
    }
    seen_operation_ids: set[str] = set()
    seen_binding_ids: set[str] = set()
    for binding in bindings:
        operation_id = str(binding.get("work_order_operation_id"))
        operation = operations_by_id.get(operation_id)
        metadata = binding.get("metadata")
        route_operation_id = binding.get("route_operation_id")
        expected_binding_id = (
            _derive_work_order_release_binding_id(
                release["release_id"], route_operation_id
            )
            if isinstance(route_operation_id, str) and route_operation_id.strip()
            else None
        )
        if (
            operation is None
            or operation_id in seen_operation_ids
            or binding.get("binding_id") in seen_binding_ids
            or binding.get("binding_source") != "work_order_release"
            or not isinstance(metadata, dict)
            or metadata != {"release_id": release.get("release_id")}
            or route_operation_id
            != (operation.get("metadata") or {}).get("route_operation_id")
            or binding.get("binding_id") != expected_binding_id
        ):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT")
        seen_operation_ids.add(operation_id)
        seen_binding_ids.add(binding["binding_id"])
    if seen_operation_ids != set(operations_by_id):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT")


def _recompute_completion_bridge_operation_set_digest(
    release: JsonObject,
    lifecycle_operations: list[JsonObject],
    bindings: list[JsonObject],
) -> str:
    binding_by_operation = {
        str(binding.get("work_order_operation_id")): binding
        for binding in bindings
    }
    if len(binding_by_operation) != len(bindings):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT")
    pairs = []
    for operation in lifecycle_operations:
        operation_id = operation.get("work_order_operation_id")
        binding = binding_by_operation.get(operation_id)
        if binding is None:
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT")
        pairs.append({
            "sequence_no": operation.get("sequence_no"),
            "route_operation_id": binding.get("route_operation_id"),
            "work_order_operation_id": operation_id,
        })
    try:
        return _compute_work_order_release_operation_set_digest(
            process_route_id=release.get("process_route_id"),
            route_code=release.get("route_code"),
            route_version=release.get("route_version"),
            release_mode=release.get("release_mode"),
            pairs=pairs,
        )
    except MesqlV2Error:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")


def _validate_completion_bridge_runtime_identity(
    runtime_state: JsonObject | None,
    current_operation: JsonObject,
    current_binding: JsonObject,
) -> None:
    if not isinstance(runtime_state, dict):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
    if runtime_state.get("execution_status") != "closed" or runtime_state.get("closed_at") is None:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_RUNTIME_NOT_CLOSED")
    metadata = runtime_state.get("metadata")
    if (
        runtime_state.get("work_order_operation_id")
        != current_operation.get("work_order_operation_id")
        or runtime_state.get("work_order_id") != current_operation.get("order_id")
        or runtime_state.get("operation_code") != current_operation.get("operation_code")
        or runtime_state.get("station_code") != current_operation.get("station_code")
        or not isinstance(metadata, dict)
        or metadata.get("route_operation_id") != current_binding.get("route_operation_id")
    ):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")


def _resolve_completion_bridge_successor(
    lifecycle_operations: list[JsonObject],
    current_work_order_operation_id: str,
) -> JsonObject | None:
    operations = list(lifecycle_operations)
    sequences: set[int] = set()
    current = None
    for operation in operations:
        sequence_no = operation.get("sequence_no")
        if (
            isinstance(sequence_no, bool)
            or not isinstance(sequence_no, int)
            or sequence_no <= 0
            or sequence_no in sequences
        ):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_SEQUENCE_CONFLICT")
        sequences.add(sequence_no)
        if operation.get("work_order_operation_id") == current_work_order_operation_id:
            current = operation
    if current is None:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
    successors = [
        operation for operation in operations
        if operation["sequence_no"] > current["sequence_no"]
    ]
    if not successors:
        return None
    return _json_safe(min(
        successors,
        key=lambda operation: (
            operation["sequence_no"], operation["work_order_operation_id"]
        ),
    ))


def _build_completion_bridge_successor_queue_snapshot(
    *,
    release: JsonObject,
    predecessor_operation: JsonObject,
    successor_operation: JsonObject,
    queue_rank: int,
) -> JsonObject:
    if isinstance(queue_rank, bool) or not isinstance(queue_rank, int) or queue_rank < 0:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT")
    order_id = successor_operation.get("order_id")
    operation_id = successor_operation.get("work_order_operation_id")
    station_code = successor_operation.get("station_code")
    operation_no = successor_operation.get("operation_no")
    sequence_no = successor_operation.get("sequence_no")
    if (
        order_id != release.get("order_id")
        or not isinstance(operation_id, str)
        or not isinstance(station_code, str)
        or not station_code.strip()
        or isinstance(operation_no, bool)
        or not isinstance(operation_no, int)
        or isinstance(sequence_no, bool)
        or not isinstance(sequence_no, int)
    ):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
    return {
        "station_code": station_code,
        "order_id": order_id,
        "queue_rank": queue_rank,
        "status": "queued",
        "source": "runtime_completion_bridge",
        "payload": {
            "order_id": order_id,
            "work_order_operation_id": operation_id,
            "operation_no": operation_no,
            "sequence_no": sequence_no,
            "station_code": station_code,
            "status": "queued",
        },
        "metadata": {
            "source": "runtime_completion_bridge",
            "release_id": release.get("release_id"),
            "predecessor_work_order_operation_id": predecessor_operation.get(
                "work_order_operation_id"
            ),
        },
        "work_order_operation_id": operation_id,
    }


def _completion_bridge_queue_identity_matches(
    queue: JsonObject,
    expected: JsonObject,
) -> bool:
    return all(
        _json_safe(queue.get(name)) == _json_safe(expected.get(name))
        for name in (
            "station_code", "order_id", "source", "payload", "metadata",
            "work_order_operation_id",
        )
    )


def _classify_completion_bridge_state(
    *,
    work_order: JsonObject,
    release: JsonObject,
    lifecycle_operations: list[JsonObject],
    bindings: list[JsonObject],
    runtime_state: JsonObject,
    station_queue_rows: list[JsonObject],
    current_work_order_operation_id: str,
) -> JsonObject:
    _validate_completion_bridge_release_identity(release, lifecycle_operations)
    _validate_completion_bridge_binding_set(release, lifecycle_operations, bindings)
    digest = _recompute_completion_bridge_operation_set_digest(
        release, lifecycle_operations, bindings
    )
    if digest != release.get("operation_set_digest"):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT")
    operations_by_id = {
        operation["work_order_operation_id"]: operation
        for operation in lifecycle_operations
    }
    bindings_by_id = {
        str(binding["work_order_operation_id"]): binding for binding in bindings
    }
    current = operations_by_id.get(current_work_order_operation_id)
    current_binding = bindings_by_id.get(current_work_order_operation_id)
    if current is None or current_binding is None:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
    _validate_completion_bridge_runtime_identity(runtime_state, current, current_binding)
    successor = _resolve_completion_bridge_successor(
        lifecycle_operations, current_work_order_operation_id
    )
    ordered = sorted(lifecycle_operations, key=lambda item: item["sequence_no"])
    current_index = next(
        index for index, item in enumerate(ordered)
        if item["work_order_operation_id"] == current_work_order_operation_id
    )
    predecessor = ordered[current_index - 1] if current_index > 0 else None
    current_selection = _select_exact_completion_bridge_queue(
        station_queue_rows,
        work_order_id=release["order_id"],
        work_order_operation_id=current_work_order_operation_id,
        station_code=current["station_code"],
    )
    if current_selection["classification"] != "exact":
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT")
    current_queue = current_selection["row"]
    if predecessor is None:
        expected_current_queue = _build_initial_queue_snapshot(
            release_id=release["release_id"],
            operation_snapshot=current,
            queue_rank=current_queue.get("queue_rank"),
        )
    else:
        expected_current_queue = _build_completion_bridge_successor_queue_snapshot(
            release=release,
            predecessor_operation=predecessor,
            successor_operation=current,
            queue_rank=current_queue.get("queue_rank"),
        )
    if not _completion_bridge_queue_identity_matches(
        current_queue, expected_current_queue
    ):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT")
    successor_queue = None
    if successor is not None:
        successor_selection = _select_exact_completion_bridge_queue(
            station_queue_rows,
            work_order_id=release["order_id"],
            work_order_operation_id=successor["work_order_operation_id"],
            station_code=successor["station_code"],
        )
        if successor_selection["classification"] == "duplicate":
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT")
        successor_queue = successor_selection["row"]

    closed_at = _json_safe(runtime_state.get("closed_at"))
    first_state = (
        current.get("status") in {"queued", "active"}
        and current.get("completed_at") is None
        and current_queue.get("status")
        in {"queued", "ready", "active", "pending_approval"}
    )
    replay_state = (
        current.get("status") == "completed"
        and _json_safe(current.get("completed_at")) == closed_at
        and current_queue.get("status") == "completed"
    )
    if first_state:
        if work_order.get("order_id") != release.get("order_id"):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT")
        if successor is not None:
            if (
                successor.get("status") != "planned"
                or successor.get("completed_at") is not None
                or successor_queue is not None
            ):
                _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_SUCCESSOR_CONFLICT")
        else:
            if any(
                operation["work_order_operation_id"] != current_work_order_operation_id
                and operation.get("status") != "completed"
                for operation in lifecycle_operations
            ):
                _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT")
            if work_order.get("status") == "completed" or work_order.get("completed_at") is not None:
                _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT")
        classification = "first_bridge"
    elif replay_state:
        if successor is not None:
            if successor_queue is None:
                _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT")
            expected_successor_queue = _build_completion_bridge_successor_queue_snapshot(
                release=release,
                predecessor_operation=current,
                successor_operation=successor,
                queue_rank=successor_queue.get("queue_rank"),
            )
            if (
                successor.get("status") not in {"queued", "active", "completed"}
                or successor_queue.get("status")
                not in {"queued", "ready", "active", "pending_approval", "completed"}
                or not _completion_bridge_queue_identity_matches(
                    successor_queue, expected_successor_queue
                )
            ):
                _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_SUCCESSOR_CONFLICT")
        elif (
            work_order.get("status") != "completed"
            or _json_safe(work_order.get("completed_at")) != closed_at
        ):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT")
        classification = "exact_replay"
    else:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_OPERATION_STATE_CONFLICT")
    return _json_safe({
        "classification": classification,
        "current_operation": current,
        "current_queue": current_queue,
        "successor_operation": successor,
        "successor_queue": successor_queue,
        "final_operation": successor is None,
        "runtime_state": runtime_state,
        "work_order": work_order,
        "release": release,
    })


def _complete_lifecycle_operation_from_runtime_cursor(
    cursor: Any,
    *,
    work_order_operation_id: str,
    closed_at: Any,
) -> JsonObject | None:
    cursor.execute(
        UPDATE_COMPLETION_BRIDGE_LIFECYCLE_CURSOR_SQL,
        {
            "work_order_operation_id": work_order_operation_id,
            "closed_at": closed_at,
        },
    )
    row = cursor.fetchone()
    return _release_work_order_operation_full_row(row) if row else None


def _complete_current_queue_from_runtime_cursor(
    cursor: Any,
    *,
    station_queue_pk: int,
) -> JsonObject | None:
    cursor.execute(
        UPDATE_COMPLETION_BRIDGE_CURRENT_QUEUE_CURSOR_SQL,
        {"station_queue_pk": station_queue_pk},
    )
    row = cursor.fetchone()
    return _work_order_release_initial_queue_row(row) if row else None


def _queue_successor_lifecycle_cursor(
    cursor: Any,
    *,
    work_order_operation_id: str,
) -> JsonObject | None:
    cursor.execute(
        UPDATE_COMPLETION_BRIDGE_SUCCESSOR_LIFECYCLE_CURSOR_SQL,
        {"work_order_operation_id": work_order_operation_id},
    )
    row = cursor.fetchone()
    return _release_work_order_operation_full_row(row) if row else None


def _insert_completion_bridge_successor_queue_cursor(
    cursor: Any,
    queue_snapshot: JsonObject,
) -> JsonObject:
    parameters = {
        name: queue_snapshot[name]
        for name in (
            "station_code", "order_id", "queue_rank", "work_order_operation_id"
        )
    }
    parameters["payload"] = _jsonb(_json_safe(queue_snapshot.get("payload") or {}))
    parameters["metadata"] = _jsonb(_json_safe(queue_snapshot.get("metadata") or {}))
    cursor.execute(INSERT_COMPLETION_BRIDGE_SUCCESSOR_QUEUE_CURSOR_SQL, parameters)
    return _work_order_release_initial_queue_row(cursor.fetchone())


def _complete_work_order_from_runtime_cursor(
    cursor: Any,
    *,
    work_order_id: str,
    closed_at: Any,
) -> JsonObject | None:
    cursor.execute(
        UPDATE_COMPLETION_BRIDGE_WORK_ORDER_CURSOR_SQL,
        {"work_order_id": work_order_id, "closed_at": closed_at},
    )
    row = cursor.fetchone()
    return _release_work_order_full_row(row) if row else None


def _read_completion_bridge_operation_cursor(
    cursor: Any,
    *,
    work_order_id: str,
    work_order_operation_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_OPERATION_CURSOR_SQL,
        {
            "work_order_id": work_order_id,
            "work_order_operation_id": work_order_operation_id,
        },
    )
    row = cursor.fetchone()
    return _release_work_order_operation_full_row(row) if row else None


def _read_completion_bridge_queue_cursor(
    cursor: Any,
    *,
    work_order_id: str,
    work_order_operation_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_QUEUE_CURSOR_SQL,
        {
            "work_order_id": work_order_id,
            "work_order_operation_id": work_order_operation_id,
        },
    )
    rows = cursor.fetchall()
    if len(rows) > 1:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT")
    return _work_order_release_initial_queue_row(rows[0]) if rows else None


def _read_completion_bridge_snapshot_cursor(
    cursor: Any,
    *,
    work_order_id: str,
    completed_work_order_operation_id: str,
    successor_work_order_operation_id: str | None = None,
) -> JsonObject:
    cursor.execute(
        SELECT_EXECUTION_STATE_SQL,
        {"work_order_operation_id": completed_work_order_operation_id},
    )
    execution_row = cursor.fetchone()
    completed_operation = _read_completion_bridge_operation_cursor(
        cursor,
        work_order_id=work_order_id,
        work_order_operation_id=completed_work_order_operation_id,
    )
    completed_queue = _read_completion_bridge_queue_cursor(
        cursor,
        work_order_id=work_order_id,
        work_order_operation_id=completed_work_order_operation_id,
    )
    successor_operation = None
    successor_queue = None
    if successor_work_order_operation_id is not None:
        successor_operation = _read_completion_bridge_operation_cursor(
            cursor,
            work_order_id=work_order_id,
            work_order_operation_id=successor_work_order_operation_id,
        )
        successor_queue = _read_completion_bridge_queue_cursor(
            cursor,
            work_order_id=work_order_id,
            work_order_operation_id=successor_work_order_operation_id,
        )
    cursor.execute(
        SELECT_COMPLETION_BRIDGE_WORK_ORDER_CURSOR_SQL,
        {"work_order_id": work_order_id},
    )
    work_order_row = cursor.fetchone()
    return _json_safe({
        "execution_state": _execution_state_row(execution_row) if execution_row else None,
        "completed_operation": completed_operation,
        "completed_queue": completed_queue,
        "successor_operation": successor_operation,
        "successor_queue": successor_queue,
        "work_order": _release_work_order_full_row(work_order_row) if work_order_row else None,
    })


def _validate_completion_bridge_first_write_invariants_cursor(
    cursor: Any,
    expected_state: JsonObject,
) -> JsonObject:
    current = expected_state.get("current_operation") or {}
    successor = expected_state.get("successor_operation")
    runtime = expected_state.get("runtime_state") or {}
    work_order = expected_state.get("work_order") or {}
    snapshot = _read_completion_bridge_snapshot_cursor(
        cursor,
        work_order_id=work_order.get("order_id"),
        completed_work_order_operation_id=current.get("work_order_operation_id"),
        successor_work_order_operation_id=(
            successor.get("work_order_operation_id") if successor else None
        ),
    )
    completed_operation = snapshot.get("completed_operation") or {}
    completed_queue = snapshot.get("completed_queue") or {}
    closed_at = _json_safe(runtime.get("closed_at"))
    if (
        (snapshot.get("execution_state") or {}).get("execution_status") != "closed"
        or _json_safe((snapshot.get("execution_state") or {}).get("closed_at")) != closed_at
        or completed_operation.get("status") != "completed"
        or _json_safe(completed_operation.get("completed_at")) != closed_at
        or completed_queue.get("status") != "completed"
        or not _completion_bridge_queue_identity_matches(
            completed_queue, expected_state.get("current_queue") or {}
        )
        or completed_queue.get("queue_rank")
        != (expected_state.get("current_queue") or {}).get("queue_rank")
    ):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_OPERATION_STATE_CONFLICT")
    if successor:
        successor_operation = snapshot.get("successor_operation") or {}
        successor_queue = snapshot.get("successor_queue") or {}
        expected_successor_queue = _build_completion_bridge_successor_queue_snapshot(
            release=expected_state.get("release") or {},
            predecessor_operation=current,
            successor_operation=successor,
            queue_rank=successor_queue.get("queue_rank"),
        )
        if (
            successor_operation.get("status") != "queued"
            or successor_queue.get("status") != "queued"
            or not _completion_bridge_queue_identity_matches(
                successor_queue, expected_successor_queue
            )
            or (snapshot.get("work_order") or {}).get("status") == "completed"
        ):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_SUCCESSOR_CONFLICT")
    else:
        completed_work_order = snapshot.get("work_order") or {}
        if (
            completed_work_order.get("status") != "completed"
            or _json_safe(completed_work_order.get("completed_at")) != closed_at
        ):
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT")
    return snapshot


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


def get_work_order_route_release(
    config: AppConfig,
    work_order_id: str,
) -> JsonObject | None:
    normalized_work_order_id = _required_case_preserving_text(
        work_order_id,
        field_name="WORK_ORDER_ID",
    )
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            return _get_work_order_route_release_with_cursor(
                cursor,
                normalized_work_order_id,
            )


def get_work_order_route_release_by_id(
    config: AppConfig,
    release_id: str,
) -> JsonObject | None:
    normalized_release_id = _required_case_preserving_text(
        release_id,
        field_name="RELEASE_ID",
    )
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            return _get_work_order_route_release_by_id_with_cursor(
                cursor,
                normalized_release_id,
            )


def get_exact_process_route(
    config: AppConfig,
    route_code: str,
    route_version: int,
) -> JsonObject | None:
    normalized_route_code = _required_case_preserving_text(
        route_code,
        field_name="ROUTE_CODE",
    ).upper()
    normalized_route_version = _required_positive_int(
        route_version,
        field_name="ROUTE_VERSION",
    )
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            return _get_exact_process_route_with_cursor(
                cursor,
                normalized_route_code,
                normalized_route_version,
            )


def list_process_route_operations(
    config: AppConfig,
    process_route_id: str,
) -> list[JsonObject]:
    normalized_process_route_id = _required_case_preserving_text(
        process_route_id,
        field_name="PROCESS_ROUTE_ID",
    )
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            return _list_process_route_operations_with_cursor(
                cursor,
                normalized_process_route_id,
            )


def get_work_order_release_snapshot(
    config: AppConfig,
    work_order_id: str,
) -> JsonObject | None:
    normalized_work_order_id = _required_case_preserving_text(
        work_order_id,
        field_name="WORK_ORDER_ID",
    )
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            return _get_work_order_release_snapshot_with_cursor(
                cursor,
                normalized_work_order_id,
            )


def release_work_order_to_route(
    config: AppConfig,
    *,
    release_id: str,
    work_order_id: str,
    route_code: str,
    route_version: int,
    release_source: str,
    released_by: str,
    mode: str,
    operation_bindings: list[JsonObject] | None = None,
    metadata: JsonObject | None = None,
) -> JsonObject:
    request = _normalize_work_order_release_request(
        release_id=release_id,
        work_order_id=work_order_id,
        route_code=route_code,
        route_version=route_version,
        release_source=release_source,
        released_by=released_by,
        mode=mode,
        operation_bindings=operation_bindings,
        metadata=metadata,
    )
    try:
        return _run_work_order_release_transaction(config, request)
    except Exception as error:
        if _postgres_error_sqlstate(error) != "23505":
            raise
        return _recover_work_order_release_unique_violation(
            config,
            request,
            error,
        )


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


def get_work_order_operation_route_binding(
    config: AppConfig,
    work_order_operation_id: str,
) -> JsonObject | None:
    normalized_operation_id = _required_uuid_text(
        work_order_operation_id,
        field_name="WORK_ORDER_OPERATION_ID",
    )
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            return _get_work_order_operation_route_binding_with_cursor(
                cursor,
                normalized_operation_id,
            )


def get_work_order_operation_route_binding_by_id(
    config: AppConfig,
    binding_id: str,
) -> JsonObject | None:
    normalized_binding_id = _required_case_preserving_text(
        binding_id,
        field_name="BINDING_ID",
    )
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            return _get_work_order_operation_route_binding_by_id_with_cursor(
                cursor,
                normalized_binding_id,
            )


def create_work_order_operation_route_binding(
    config: AppConfig,
    *,
    binding_id: str,
    work_order_operation_id: str,
    route_operation_id: str,
    binding_source: str,
    bound_by: str,
    metadata: JsonObject | None = None,
) -> JsonObject:
    normalized_binding_id = _required_case_preserving_text(
        binding_id,
        field_name="BINDING_ID",
    )
    normalized_operation_id = _required_uuid_text(
        work_order_operation_id,
        field_name="WORK_ORDER_OPERATION_ID",
    )
    normalized_route_operation_id = _required_case_preserving_text(
        route_operation_id,
        field_name="ROUTE_OPERATION_ID",
    )
    normalized_binding_source = _required_case_preserving_text(
        binding_source,
        field_name="BINDING_SOURCE",
    )
    if normalized_binding_source not in BINDING_SOURCES:
        raise MesqlV2Error("BINDING_SOURCE_INVALID", status_code=400)
    normalized_bound_by = _required_case_preserving_text(
        bound_by,
        field_name="BOUND_BY",
    )
    if metadata is None:
        normalized_metadata: JsonObject = {}
    elif isinstance(metadata, dict):
        try:
            normalized_metadata = _json_safe(metadata)
            json.dumps(normalized_metadata)
        except (TypeError, ValueError, RecursionError):
            raise MesqlV2Error(
                "BINDING_METADATA_INVALID",
                status_code=400,
            ) from None
    else:
        raise MesqlV2Error("BINDING_METADATA_INVALID", status_code=400)

    request = {
        "binding_id": normalized_binding_id,
        "work_order_operation_id": normalized_operation_id,
        "route_operation_id": normalized_route_operation_id,
        "binding_source": normalized_binding_source,
        "bound_by": normalized_bound_by,
        "metadata": normalized_metadata,
    }
    created = False
    binding: JsonObject | None = None
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                cursor.execute(
                    INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL,
                    {
                        **request,
                        "metadata": _jsonb(normalized_metadata),
                    },
                )
                inserted_row = cursor.fetchone()
                if inserted_row:
                    created = True
                    binding = _work_order_operation_route_binding_row(inserted_row)
                else:
                    existing_by_operation = (
                        _get_work_order_operation_route_binding_with_cursor(
                            cursor,
                            normalized_operation_id,
                        )
                    )
                    existing_by_id = (
                        _get_work_order_operation_route_binding_by_id_with_cursor(
                            cursor,
                            normalized_binding_id,
                        )
                    )
                    if (
                        existing_by_operation is not None
                        and existing_by_id is not None
                        and not _same_binding_identity(
                            existing_by_operation,
                            existing_by_id,
                        )
                    ):
                        raise MesqlV2Error(
                            "WORK_ORDER_OPERATION_ROUTE_BINDING_CONFLICT",
                            status_code=409,
                        )
                    binding = existing_by_operation or existing_by_id
                    if binding is None or not _binding_matches_request(
                        binding,
                        request,
                    ):
                        raise MesqlV2Error(
                            "WORK_ORDER_OPERATION_ROUTE_BINDING_CONFLICT",
                            status_code=409,
                        )
        commit = getattr(connection, "commit", None)
        if created and callable(commit):
            commit()

    return _json_safe({"created": created, "binding": binding})


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
    response_route_operation_id = normalized_route_operation_id
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

                if existing_state is not None:
                    mapped_existing_state = _execution_state_row(existing_state)
                    existing_metadata = mapped_existing_state.get("metadata") or {}
                    stored_route_operation_id = (
                        _text(existing_metadata.get("route_operation_id"))
                        if isinstance(existing_metadata, dict)
                        else ""
                    )
                    if stored_route_operation_id:
                        if stored_route_operation_id != normalized_route_operation_id:
                            raise MesqlV2Error(
                                "EXECUTION_STATE_ROUTE_OPERATION_MISMATCH",
                                status_code=409,
                            )
                        response_route_operation_id = stored_route_operation_id
                else:
                    binding = _get_work_order_operation_route_binding_with_cursor(
                        cursor,
                        normalized_operation_id,
                    )
                    if binding is None:
                        raise MesqlV2Error(
                            "WORK_ORDER_OPERATION_ROUTE_BINDING_REQUIRED",
                            status_code=409,
                        )
                    if (
                        _text(binding.get("route_operation_id"))
                        != normalized_route_operation_id
                    ):
                        raise MesqlV2Error(
                            "WORK_ORDER_OPERATION_ROUTE_BINDING_MISMATCH",
                            status_code=409,
                        )
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
        "route_operation_id": response_route_operation_id,
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


def _get_operation_event_by_idempotency_key_with_cursor(
    cursor: Any,
    idempotency_key: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_OPERATION_EVENT_BY_IDEMPOTENCY_KEY_SQL,
        {"idempotency_key": idempotency_key},
    )
    row = cursor.fetchone()
    return _operation_event_row(row) if row else None


def _get_operation_event_by_external_event_with_cursor(
    cursor: Any,
    station_code: str,
    event_source: str,
    external_event_id: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_OPERATION_EVENT_BY_EXTERNAL_EVENT_SQL,
        {
            "station_code": station_code,
            "event_source": event_source,
            "external_event_id": external_event_id,
        },
    )
    row = cursor.fetchone()
    return _operation_event_row(row) if row else None


def _record_operation_event_with_cursor(
    cursor: Any,
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
    work_order_id: str | None = None,
    work_order_operation_step_id: str | None = None,
    operation_code: str | None = None,
    step_code: str | None = None,
) -> JsonObject:
    event_payload = dict(payload or {})
    if actor_id:
        event_payload.setdefault("actor_id", actor_id)
    cursor.execute(
        INSERT_OPERATION_EVENT_SQL,
        {
            "event_id": _runtime_record_id("OP_EVENT", idempotency_key),
            "work_order_id": work_order_id,
            "work_order_operation_id": work_order_operation_id,
            "work_order_operation_step_id": work_order_operation_step_id,
            "operation_code": operation_code,
            "step_code": step_code,
            "station_code": station_code,
            "event_source": event_source,
            "event_type": event_type,
            "external_event_id": external_event_id,
            "idempotency_key": idempotency_key,
            "payload": _jsonb(event_payload),
            "accepted": bool(accepted),
            "rejection_reason": rejection_reason,
        },
    )
    inserted_row = cursor.fetchone()
    return _operation_event_row(inserted_row) if inserted_row else {}


def _get_operation_step_with_cursor(
    cursor: Any,
    route_operation_id: str,
    step_code: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_OPERATION_STEP_SQL,
        {
            "route_operation_id": route_operation_id,
            "step_code": step_code,
        },
    )
    row = cursor.fetchone()
    return _operation_step_row(row) if row else None


def _resolve_station_event_source_with_cursor(
    cursor: Any,
    station_code: str,
    source_code: str,
) -> JsonObject | None:
    cursor.execute(
        SELECT_STATION_EVENT_SOURCE_SQL,
        {
            "station_code": station_code,
            "source_code": source_code,
        },
    )
    row = cursor.fetchone()
    return _station_event_source_row(row) if row else None


def get_operation_event_by_idempotency_key(config: AppConfig, idempotency_key: str) -> JsonObject | None:
    normalized_idempotency_key = _nullable_text(idempotency_key)
    if not normalized_idempotency_key:
        return None
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with connection.cursor() as cursor:
            return _get_operation_event_by_idempotency_key_with_cursor(cursor, normalized_idempotency_key)


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
            return _get_operation_event_by_external_event_with_cursor(
                cursor,
                normalized_station_code,
                normalized_event_source,
                normalized_external_event_id,
            )


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
    work_order_id: str | None = None,
    work_order_operation_step_id: str | None = None,
    operation_code: str | None = None,
    step_code: str | None = None,
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

    normalized_actor_id = _nullable_text(actor_id)
    normalized_work_order_id = _nullable_text(work_order_id)
    normalized_runtime_step_id = _nullable_text(work_order_operation_step_id)
    normalized_operation_code = _nullable_upper(operation_code)
    normalized_step_code = _nullable_upper(step_code)
    inserted_event: JsonObject | None = None

    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                existing = _get_operation_event_by_idempotency_key_with_cursor(
                    cursor,
                    normalized_idempotency_key,
                )
                if existing is None and normalized_external_event_id:
                    existing = _get_operation_event_by_external_event_with_cursor(
                        cursor,
                        normalized_station_code,
                        normalized_event_source,
                        normalized_external_event_id,
                    )
                if existing is None:
                    inserted_event = _record_operation_event_with_cursor(
                        cursor,
                        work_order_operation_id=normalized_operation_id,
                        station_code=normalized_station_code,
                        event_source=normalized_event_source,
                        event_type=normalized_event_type,
                        external_event_id=normalized_external_event_id,
                        idempotency_key=normalized_idempotency_key,
                        actor_id=normalized_actor_id,
                        payload=payload,
                        accepted=accepted,
                        rejection_reason=normalized_rejection_reason,
                        work_order_id=normalized_work_order_id,
                        work_order_operation_step_id=normalized_runtime_step_id,
                        operation_code=normalized_operation_code,
                        step_code=normalized_step_code,
                    )
        commit = getattr(connection, "commit", None)
        if inserted_event is not None and callable(commit):
            commit()

    if existing is not None:
        return _json_safe({"status": "ok", "inserted": False, "event": existing})

    return _json_safe({
        "status": "ok",
        "inserted": True,
        "event": inserted_event,
    })


def start_execution_step(
    config: AppConfig,
    *,
    work_order_operation_id: str,
    step_code: str,
    event_source: str,
    external_event_id: str | None = None,
    idempotency_key: str | None = None,
    actor_id: str | None = None,
    payload: JsonObject | None = None,
) -> JsonObject:
    normalized_operation_id = _text(work_order_operation_id)
    normalized_step_code = _upper(step_code)
    normalized_event_source = _upper(event_source)
    normalized_external_event_id = _nullable_text(external_event_id)
    normalized_idempotency_key = _nullable_text(idempotency_key)
    normalized_actor_id = _nullable_text(actor_id)
    if not normalized_operation_id or not normalized_step_code or not normalized_event_source:
        raise MesqlV2Error("RUNTIME_STEP_IDENTIFIER_REQUIRED", status_code=400)
    if not normalized_idempotency_key and not normalized_external_event_id:
        raise MesqlV2Error("OPERATION_EVENT_IDEMPOTENCY_REQUIRED", status_code=400)

    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                cursor.execute(
                    SELECT_EXECUTION_STATE_FOR_UPDATE_SQL,
                    {"work_order_operation_id": normalized_operation_id},
                )
                state_row = cursor.fetchone()
                if not state_row:
                    raise MesqlV2Error("EXECUTION_STATE_NOT_FOUND", status_code=404)
                execution_state = _execution_state_row(state_row)

                cursor.execute(
                    SELECT_EXECUTION_STEP_FOR_UPDATE_SQL,
                    {
                        "work_order_operation_id": normalized_operation_id,
                        "step_code": normalized_step_code,
                    },
                )
                step_row = cursor.fetchone()
                if not step_row:
                    raise MesqlV2Error("EXECUTION_STEP_NOT_FOUND", status_code=404)
                execution_step = _execution_step_row(step_row)

                station_code = _upper(execution_state.get("station_code"))
                if station_code != _upper(execution_step.get("station_code")):
                    raise MesqlV2Error("RUNTIME_STATION_MISMATCH", status_code=409)
                if not normalized_idempotency_key:
                    normalized_idempotency_key = _build_operation_event_idempotency_key(
                        station_code,
                        normalized_event_source,
                        normalized_external_event_id,
                    )

                metadata = execution_state.get("metadata") or {}
                route_operation_id = _upper(metadata.get("route_operation_id")) if isinstance(metadata, dict) else ""
                if not route_operation_id:
                    raise MesqlV2Error("RUNTIME_ROUTE_OPERATION_CONTEXT_MISSING", status_code=409)

                operation_step = _get_operation_step_with_cursor(
                    cursor,
                    route_operation_id,
                    normalized_step_code,
                )
                if operation_step is None:
                    raise MesqlV2Error("OPERATION_STEP_CONFIG_NOT_FOUND", status_code=404)

                station_event_source = _resolve_station_event_source_with_cursor(
                    cursor,
                    station_code,
                    normalized_event_source,
                )
                if station_event_source is None or not station_event_source.get("active"):
                    raise MesqlV2Error("STATION_EVENT_SOURCE_NOT_FOUND", status_code=404)

                expected_source = _upper(operation_step.get("start_event_source_code"))
                if expected_source and expected_source != normalized_event_source:
                    raise MesqlV2Error("STEP_START_EVENT_SOURCE_MISMATCH", status_code=409)
                if _lower(operation_step.get("start_mode")) not in {"manual_start", "auto_start"}:
                    raise MesqlV2Error("STEP_START_MODE_NOT_SUPPORTED", status_code=409)

                existing_event = _get_operation_event_by_idempotency_key_with_cursor(
                    cursor,
                    normalized_idempotency_key,
                )
                if existing_event is None and normalized_external_event_id:
                    existing_event = _get_operation_event_by_external_event_with_cursor(
                        cursor,
                        station_code,
                        normalized_event_source,
                        normalized_external_event_id,
                    )
                if existing_event is not None:
                    result = {
                        "status": "ok",
                        "work_order_operation_id": normalized_operation_id,
                        "station_code": station_code,
                        "step_code": normalized_step_code,
                        "started": False,
                        "event_inserted": False,
                        "event": existing_event,
                        "execution_state": execution_state,
                        "step": execution_step,
                    }
                else:
                    if _lower(execution_state.get("execution_status")) not in {"ready", "active"}:
                        raise MesqlV2Error("EXECUTION_STATE_NOT_STARTABLE", status_code=409)
                    if _lower(execution_step.get("status")) not in {"pending", "active"}:
                        raise MesqlV2Error("EXECUTION_STEP_NOT_STARTABLE", status_code=409)

                    event_payload = dict(payload or {})
                    event_payload["action"] = "start"
                    event_payload["step_code"] = normalized_step_code
                    inserted_event = _record_operation_event_with_cursor(
                        cursor,
                        work_order_operation_id=normalized_operation_id,
                        work_order_id=_nullable_text(execution_state.get("work_order_id")),
                        work_order_operation_step_id=_nullable_text(execution_step.get("work_order_operation_step_id")),
                        operation_code=_nullable_upper(execution_state.get("operation_code")),
                        step_code=normalized_step_code,
                        station_code=station_code,
                        event_source=normalized_event_source,
                        event_type="step_start",
                        external_event_id=normalized_external_event_id,
                        idempotency_key=normalized_idempotency_key,
                        actor_id=normalized_actor_id,
                        payload=event_payload,
                    )
                    started = _lower(execution_step.get("status")) == "pending"
                    if started:
                        cursor.execute(
                            UPDATE_EXECUTION_STATE_STEP_STARTED_SQL,
                            {
                                "work_order_operation_id": normalized_operation_id,
                                "current_step_code": normalized_step_code,
                                "last_event_id": inserted_event.get("event_id"),
                            },
                        )
                        cursor.execute(
                            UPDATE_EXECUTION_STEP_STARTED_SQL,
                            {
                                "work_order_operation_id": normalized_operation_id,
                                "step_code": normalized_step_code,
                                "started_by_event_id": inserted_event.get("event_id"),
                            },
                        )
                        cursor.execute(
                            SELECT_EXECUTION_STATE_SQL,
                            {"work_order_operation_id": normalized_operation_id},
                        )
                        execution_state = _execution_state_row(cursor.fetchone())
                        cursor.execute(
                            SELECT_EXECUTION_STEP_FOR_UPDATE_SQL,
                            {
                                "work_order_operation_id": normalized_operation_id,
                                "step_code": normalized_step_code,
                            },
                        )
                        execution_step = _execution_step_row(cursor.fetchone())
                    result = {
                        "status": "ok",
                        "work_order_operation_id": normalized_operation_id,
                        "station_code": station_code,
                        "step_code": normalized_step_code,
                        "started": started,
                        "event_inserted": True,
                        "event": inserted_event,
                        "execution_state": execution_state,
                        "step": execution_step,
                    }
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

    return _json_safe(result)


def _first_actionable_execution_step(steps: list[JsonObject]) -> JsonObject | None:
    for step in steps:
        if _lower(step.get("status")) in {"pending", "active"}:
            return step
    return None


def _required_steps_completed(steps: list[JsonObject]) -> bool:
    required_steps = [step for step in steps if step.get("required_for_completion") is True]
    return bool(required_steps) and all(
        _lower(step.get("status")) == "completed"
        for step in required_steps
    )


def _resolve_completion_policy_transition(
    *,
    operation_completion_policy: str,
    required_steps_completed: bool,
) -> JsonObject:
    policy = _lower(operation_completion_policy)
    if not required_steps_completed:
        return {
            "policy_applied": False,
            "execution_status": "active",
            "set_pending_final_approval_at": False,
            "set_closed_at": False,
        }

    transitions = {
        "manual_close": {
            "execution_status": "evidence_completed",
            "set_pending_final_approval_at": False,
            "set_closed_at": False,
        },
        "auto_close_on_required_steps": {
            "execution_status": "closed",
            "set_pending_final_approval_at": False,
            "set_closed_at": True,
        },
        "auto_complete_pending_approval": {
            "execution_status": "pending_final_approval",
            "set_pending_final_approval_at": True,
            "set_closed_at": False,
        },
    }
    transition = transitions.get(policy)
    if transition is None:
        raise MesqlV2Error("OPERATION_COMPLETION_POLICY_UNSUPPORTED", status_code=409)
    return {"policy_applied": True, **transition}


class _CompletionBridgeQueueViolation(RuntimeError):
    def __init__(self, original_error: BaseException, recovery: JsonObject) -> None:
        super().__init__(str(original_error))
        self.original_error = original_error
        self.recovery = recovery


def _runtime_execution_state_view(state: JsonObject) -> JsonObject:
    result = dict(state)
    result.pop("execution_state_pk", None)
    return result


def _runtime_execution_step_view(step: JsonObject) -> JsonObject:
    result = dict(step)
    result.pop("work_order_operation_step_pk", None)
    return result


def _prepare_runtime_completion_bridge_cursor(
    cursor: Any,
    *,
    applicability: JsonObject,
) -> JsonObject:
    work_order_operation_id = str(applicability.get("work_order_operation_id"))
    work_order_id = applicability.get("order_id")
    work_order = _select_completion_bridge_work_order_for_update_cursor(
        cursor, work_order_id
    )
    if work_order is None:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT")
    release = _select_completion_bridge_release_for_update_cursor(
        cursor, work_order_id
    )
    if release is None:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT")
    operations = _list_completion_bridge_operations_for_update_cursor(
        cursor, work_order_id
    )
    bindings = _list_completion_bridge_bindings_for_update_cursor(
        cursor, work_order_id
    )
    execution_state = _select_completion_bridge_execution_state_for_update_cursor(
        cursor, work_order_operation_id
    )
    runtime_steps = _list_completion_bridge_runtime_steps_for_update_cursor(
        cursor, work_order_operation_id
    )
    current = next(
        (
            operation for operation in operations
            if operation.get("work_order_operation_id") == work_order_operation_id
        ),
        None,
    )
    if current is None or execution_state is None:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT")
    _compare_completion_bridge_preflight_identity(applicability, current)
    _validate_completion_bridge_release_identity(release, operations)
    _validate_completion_bridge_binding_set(release, operations, bindings)
    if _recompute_completion_bridge_operation_set_digest(
        release, operations, bindings
    ) != release.get("operation_set_digest"):
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT")
    return {
        "work_order": work_order,
        "release": release,
        "lifecycle_operations": operations,
        "bindings": bindings,
        "execution_state": _runtime_execution_state_view(execution_state),
        "runtime_steps": [
            _runtime_execution_step_view(step) for step in runtime_steps
        ],
    }


def _completion_bridge_replay_queue_rows_cursor(
    cursor: Any,
    *,
    work_order_id: str,
    current_operation: JsonObject,
    successor_operation: JsonObject | None,
) -> list[JsonObject]:
    rows = []
    current_queue = _read_completion_bridge_queue_cursor(
        cursor,
        work_order_id=work_order_id,
        work_order_operation_id=current_operation["work_order_operation_id"],
    )
    if current_queue is not None:
        rows.append(current_queue)
    if successor_operation is not None:
        successor_queue = _read_completion_bridge_queue_cursor(
            cursor,
            work_order_id=work_order_id,
            work_order_operation_id=successor_operation[
                "work_order_operation_id"
            ],
        )
        if successor_queue is not None:
            rows.append(successor_queue)
    return rows


def _completion_bridge_response(snapshot: JsonObject, *, bridged: bool) -> JsonObject:
    return {"bridged": bridged, **_json_safe(snapshot)}


def _apply_runtime_completion_bridge_cursor(
    cursor: Any,
    *,
    work_order_operation_id: str,
    locked_context: JsonObject,
    runtime_state: JsonObject,
) -> JsonObject:
    work_order = locked_context["work_order"]
    release = locked_context["release"]
    operations = locked_context["lifecycle_operations"]
    bindings = locked_context["bindings"]
    current = next(
        operation for operation in operations
        if operation.get("work_order_operation_id") == work_order_operation_id
    )
    successor = _resolve_completion_bridge_successor(
        operations, work_order_operation_id
    )
    replay_candidate = (
        current.get("status") == "completed"
        and _json_safe(current.get("completed_at"))
        == _json_safe(runtime_state.get("closed_at"))
    )
    if replay_candidate:
        queue_rows = _completion_bridge_replay_queue_rows_cursor(
            cursor,
            work_order_id=release["order_id"],
            current_operation=current,
            successor_operation=successor,
        )
        classified = _classify_completion_bridge_state(
            work_order=work_order,
            release=release,
            lifecycle_operations=operations,
            bindings=bindings,
            runtime_state=runtime_state,
            station_queue_rows=queue_rows,
            current_work_order_operation_id=work_order_operation_id,
        )
        if classified["classification"] != "exact_replay":
            _completion_bridge_error(
                "RUNTIME_COMPLETION_BRIDGE_OPERATION_STATE_CONFLICT"
            )
        snapshot = _read_completion_bridge_snapshot_cursor(
            cursor,
            work_order_id=release["order_id"],
            completed_work_order_operation_id=work_order_operation_id,
            successor_work_order_operation_id=(
                successor.get("work_order_operation_id") if successor else None
            ),
        )
        return _completion_bridge_response(snapshot, bridged=False)

    station_codes = _normalize_completion_bridge_station_lock_set(
        current.get("station_code"),
        successor.get("station_code") if successor else None,
    )
    _lock_completion_bridge_station_scopes_cursor(cursor, station_codes)
    queue_rows = _list_completion_bridge_station_queue_rows_for_update_cursor(
        cursor, station_codes
    )
    classified = _classify_completion_bridge_state(
        work_order=work_order,
        release=release,
        lifecycle_operations=operations,
        bindings=bindings,
        runtime_state=runtime_state,
        station_queue_rows=queue_rows,
        current_work_order_operation_id=work_order_operation_id,
    )
    if classified["classification"] != "first_bridge":
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_OPERATION_STATE_CONFLICT")
    closed_at = runtime_state.get("closed_at")
    completed_operation = _complete_lifecycle_operation_from_runtime_cursor(
        cursor,
        work_order_operation_id=work_order_operation_id,
        closed_at=closed_at,
    )
    if completed_operation is None:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_OPERATION_STATE_CONFLICT")
    current_queue = classified["current_queue"]
    completed_queue = _complete_current_queue_from_runtime_cursor(
        cursor, station_queue_pk=current_queue["station_queue_pk"]
    )
    if completed_queue is None:
        _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT")
    if successor is not None:
        queued_successor = _queue_successor_lifecycle_cursor(
            cursor,
            work_order_operation_id=successor["work_order_operation_id"],
        )
        if queued_successor is None:
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_SUCCESSOR_CONFLICT")
        rank_rows = [dict(row) for row in queue_rows]
        for row in rank_rows:
            if row.get("station_queue_pk") == current_queue.get("station_queue_pk"):
                row["status"] = "completed"
        queue_rank = _compute_completion_bridge_next_queue_rank(
            rank_rows, successor["station_code"]
        )
        queue_snapshot = _build_completion_bridge_successor_queue_snapshot(
            release=release,
            predecessor_operation=current,
            successor_operation=successor,
            queue_rank=queue_rank,
        )
        try:
            _insert_completion_bridge_successor_queue_cursor(
                cursor, queue_snapshot
            )
        except BaseException as error:
            constraint_name = _postgres_constraint_name(error)
            if (
                _postgres_error_sqlstate(error) == "23505"
                and constraint_name in WORK_ORDER_RELEASE_QUEUE_CONSTRAINTS
            ):
                raise _CompletionBridgeQueueViolation(
                    error,
                    {
                        "constraint_name": constraint_name,
                        "work_order_operation_id": work_order_operation_id,
                        "order_id": release["order_id"],
                        "successor_work_order_operation_id": successor[
                            "work_order_operation_id"
                        ],
                        "station_code": successor["station_code"],
                        "queue_rank": queue_rank,
                    },
                ) from error
            raise
    else:
        completed_work_order = _complete_work_order_from_runtime_cursor(
            cursor,
            work_order_id=release["order_id"],
            closed_at=closed_at,
        )
        if completed_work_order is None:
            _completion_bridge_error("RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT")
    expected_state = dict(classified)
    _validate_completion_bridge_first_write_invariants_cursor(
        cursor, expected_state
    )
    snapshot = _read_completion_bridge_snapshot_cursor(
        cursor,
        work_order_id=release["order_id"],
        completed_work_order_operation_id=work_order_operation_id,
        successor_work_order_operation_id=(
            successor.get("work_order_operation_id") if successor else None
        ),
    )
    return _completion_bridge_response(snapshot, bridged=True)


def _completion_bridge_queue_conflict_evidence(
    rows: list[JsonObject],
    recovery: JsonObject,
) -> bool:
    constraint_name = recovery.get("constraint_name")
    for row in rows:
        if row.get("station_code") != recovery.get("station_code"):
            continue
        if constraint_name == "uq_mes_station_queue_station_active_rank":
            if (
                row.get("queue_rank") == recovery.get("queue_rank")
                and row.get("status")
                in {"queued", "active", "pending_approval"}
                and str(row.get("work_order_operation_id"))
                != recovery.get("work_order_operation_id")
            ):
                return True
        elif constraint_name == "uq_mes_station_queue_station_order":
            if row.get("order_id") == recovery.get("order_id"):
                return True
        elif constraint_name == "uq_mes_station_queue_station_operation":
            if str(row.get("work_order_operation_id")) == recovery.get(
                "successor_work_order_operation_id"
            ):
                return True
    return False


def _recover_runtime_completion_bridge_queue_violation(
    config: AppConfig,
    violation: _CompletionBridgeQueueViolation,
) -> None:
    recovery = violation.recovery
    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                applicability = _select_completion_bridge_applicability_cursor(
                    cursor, recovery["work_order_operation_id"]
                )
                if not _is_completion_bridge_applicable(applicability):
                    raise violation.original_error
                readiness = _get_completion_bridge_schema_readiness_cursor(cursor)
                _validate_completion_bridge_schema_readiness(readiness)
                station_codes = [recovery["station_code"]]
                _lock_completion_bridge_station_scopes_cursor(
                    cursor, station_codes
                )
                rows = _list_completion_bridge_station_queue_rows_for_update_cursor(
                    cursor, station_codes
                )
                conflict = _completion_bridge_queue_conflict_evidence(
                    rows, recovery
                )
    if conflict:
        raise MesqlV2Error(
            "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT", status_code=409
        ) from violation.original_error
    raise violation.original_error


def _finish_execution_step_transaction(
    config: AppConfig,
    *,
    work_order_operation_id: str,
    step_code: str,
    event_source: str,
    external_event_id: str | None = None,
    idempotency_key: str | None = None,
    actor_id: str | None = None,
    payload: JsonObject | None = None,
) -> JsonObject:
    normalized_operation_id = _text(work_order_operation_id)
    normalized_step_code = _upper(step_code)
    normalized_event_source = _upper(event_source)
    normalized_external_event_id = _nullable_text(external_event_id)
    normalized_idempotency_key = _nullable_text(idempotency_key)
    normalized_actor_id = _nullable_text(actor_id)
    if not normalized_operation_id or not normalized_step_code or not normalized_event_source:
        raise MesqlV2Error("RUNTIME_STEP_IDENTIFIER_REQUIRED", status_code=400)
    if not normalized_idempotency_key and not normalized_external_event_id:
        raise MesqlV2Error("OPERATION_EVENT_IDEMPOTENCY_REQUIRED", status_code=400)

    with database_connection(config) as connection:
        if connection is None:
            raise MesqlV2Error("DATABASE_DISABLED", status_code=503)
        with _transaction(connection):
            with connection.cursor() as cursor:
                applicability = _select_completion_bridge_applicability_cursor(
                    cursor, normalized_operation_id
                )
                bridge_applicable = _is_completion_bridge_applicable(applicability)
                bridge_context = None
                if bridge_applicable:
                    readiness = _get_completion_bridge_schema_readiness_cursor(cursor)
                    _validate_completion_bridge_schema_readiness(readiness)
                    bridge_context = _prepare_runtime_completion_bridge_cursor(
                        cursor, applicability=applicability
                    )
                    execution_state = bridge_context["execution_state"]
                    execution_steps = bridge_context["runtime_steps"]
                else:
                    cursor.execute(
                        SELECT_EXECUTION_STATE_FOR_UPDATE_SQL,
                        {"work_order_operation_id": normalized_operation_id},
                    )
                    state_row = cursor.fetchone()
                    if not state_row:
                        raise MesqlV2Error("EXECUTION_STATE_NOT_FOUND", status_code=404)
                    execution_state = _execution_state_row(state_row)
                    cursor.execute(
                        SELECT_EXECUTION_STEPS_FOR_UPDATE_SQL,
                        {"work_order_operation_id": normalized_operation_id},
                    )
                    execution_steps = [
                        _execution_step_row(row) for row in cursor.fetchall()
                    ]
                execution_step = next(
                    (step for step in execution_steps if _upper(step.get("step_code")) == normalized_step_code),
                    None,
                )
                if execution_step is None:
                    raise MesqlV2Error("EXECUTION_STEP_NOT_FOUND", status_code=404)

                station_code = _upper(execution_state.get("station_code"))
                if station_code != _upper(execution_step.get("station_code")):
                    raise MesqlV2Error("RUNTIME_STATION_MISMATCH", status_code=409)
                if not normalized_idempotency_key:
                    normalized_idempotency_key = _build_operation_event_idempotency_key(
                        station_code,
                        normalized_event_source,
                        normalized_external_event_id,
                    )

                metadata = execution_state.get("metadata") or {}
                route_operation_id = _upper(metadata.get("route_operation_id")) if isinstance(metadata, dict) else ""
                if not route_operation_id:
                    raise MesqlV2Error("RUNTIME_ROUTE_OPERATION_CONTEXT_MISSING", status_code=409)
                operation_step = _get_operation_step_with_cursor(cursor, route_operation_id, normalized_step_code)
                if operation_step is None:
                    raise MesqlV2Error("OPERATION_STEP_CONFIG_NOT_FOUND", status_code=404)
                station_event_source = _resolve_station_event_source_with_cursor(
                    cursor,
                    station_code,
                    normalized_event_source,
                )
                if station_event_source is None or not station_event_source.get("active"):
                    raise MesqlV2Error("STATION_EVENT_SOURCE_NOT_FOUND", status_code=404)
                expected_source = _upper(operation_step.get("finish_event_source_code"))
                if expected_source != normalized_event_source:
                    raise MesqlV2Error("STEP_FINISH_SOURCE_MISMATCH", status_code=409)

                existing_event = _get_operation_event_by_idempotency_key_with_cursor(
                    cursor,
                    normalized_idempotency_key,
                )
                if existing_event is None and normalized_external_event_id:
                    existing_event = _get_operation_event_by_external_event_with_cursor(
                        cursor,
                        station_code,
                        normalized_event_source,
                        normalized_external_event_id,
                    )
                if existing_event is not None:
                    result = {
                        "status": "ok",
                        "work_order_operation_id": normalized_operation_id,
                        "station_code": station_code,
                        "step_code": normalized_step_code,
                        "finished": False,
                        "event_inserted": False,
                        "implicit_started": False,
                        "event": existing_event,
                        "execution_state": execution_state,
                        "step": execution_step,
                        "next_step": _first_actionable_execution_step(execution_steps),
                        "completion_policy_applied": False,
                        "completion_policy": _lower(execution_state.get("operation_completion_policy")),
                        "execution_transition": None,
                        "required_steps_completed": _required_steps_completed(execution_steps),
                    }
                else:
                    if _lower(execution_state.get("execution_status")) not in {"ready", "active"}:
                        raise MesqlV2Error("EXECUTION_STATUS_NOT_FINISHABLE", status_code=409)
                    step_status = _lower(execution_step.get("status"))
                    if step_status == "completed":
                        raise MesqlV2Error("STEP_ALREADY_COMPLETED", status_code=409)
                    if step_status in {"skipped", "failed", "cancelled"}:
                        raise MesqlV2Error("STEP_STATUS_NOT_FINISHABLE", status_code=409)
                    current_step = _first_actionable_execution_step(execution_steps)
                    if current_step is None or _upper(current_step.get("step_code")) != normalized_step_code:
                        raise MesqlV2Error("STEP_NOT_ACTIONABLE", status_code=409)
                    if any(
                        _lower(step.get("status")) in {"failed", "cancelled"}
                        for step in execution_steps
                        if _safe_int(step.get("step_no"), 0) < _safe_int(execution_step.get("step_no"), 0)
                    ):
                        raise MesqlV2Error("STEP_NOT_ACTIONABLE", status_code=409)

                    finish_mode = _lower(operation_step.get("finish_mode"))
                    if finish_mode not in {"auto_finish", "manual_finish"}:
                        raise MesqlV2Error("STEP_FINISH_MODE_UNSUPPORTED", status_code=409)

                    start_mode = _lower(operation_step.get("start_mode"))
                    implicit_started = step_status == "pending"
                    if implicit_started and (start_mode, finish_mode) not in {
                        ("auto_start", "auto_finish"),
                        ("implicit_start", "auto_finish"),
                        ("implicit_start", "manual_finish"),
                    }:
                        raise MesqlV2Error("STEP_START_REQUIRED", status_code=409)
                    if _lower(execution_state.get("execution_status")) == "ready" and not implicit_started:
                        raise MesqlV2Error("EXECUTION_STATUS_NOT_FINISHABLE", status_code=409)

                    event_payload = dict(payload or {})
                    event_payload["action"] = "finish"
                    event_payload["step_code"] = normalized_step_code
                    inserted_event = _record_operation_event_with_cursor(
                        cursor,
                        work_order_operation_id=normalized_operation_id,
                        work_order_id=_nullable_text(execution_state.get("work_order_id")),
                        work_order_operation_step_id=_nullable_text(execution_step.get("work_order_operation_step_id")),
                        operation_code=_nullable_upper(execution_state.get("operation_code")),
                        step_code=normalized_step_code,
                        station_code=station_code,
                        event_source=normalized_event_source,
                        event_type="step_finish",
                        external_event_id=normalized_external_event_id,
                        idempotency_key=normalized_idempotency_key,
                        actor_id=normalized_actor_id,
                        payload=event_payload,
                    )
                    event_time = inserted_event.get("event_time")
                    event_id = inserted_event.get("event_id")
                    cursor.execute(
                        UPDATE_EXECUTION_STEP_FINISHED_SQL,
                        {
                            "work_order_operation_id": normalized_operation_id,
                            "step_code": normalized_step_code,
                            "event_time": event_time,
                            "event_id": event_id,
                        },
                    )
                    completed_step = _execution_step_row(cursor.fetchone())
                    resolved_steps = [
                        completed_step if _upper(step.get("step_code")) == normalized_step_code else step
                        for step in execution_steps
                    ]
                    required_steps_completed = _required_steps_completed(resolved_steps)
                    completion_policy = _lower(execution_state.get("operation_completion_policy"))
                    policy_transition = _resolve_completion_policy_transition(
                        operation_completion_policy=completion_policy,
                        required_steps_completed=required_steps_completed,
                    )
                    completion_policy_applied = bool(policy_transition["policy_applied"])
                    next_step = None if completion_policy_applied else _first_actionable_execution_step(resolved_steps)
                    from_status = _lower(execution_state.get("execution_status"))
                    to_status = _lower(policy_transition["execution_status"])
                    cursor.execute(
                        UPDATE_EXECUTION_STATE_STEP_FINISHED_SQL,
                        {
                            "work_order_operation_id": normalized_operation_id,
                            "current_step_code": _nullable_upper(next_step.get("step_code")) if next_step else None,
                            "last_event_id": event_id,
                            "event_time": event_time,
                            "execution_status": to_status,
                            "completion_policy_applied": completion_policy_applied,
                            "set_pending_final_approval_at": bool(
                                policy_transition["set_pending_final_approval_at"]
                            ),
                            "set_closed_at": bool(policy_transition["set_closed_at"]),
                        },
                    )
                    cursor.execute(
                        SELECT_EXECUTION_STATE_SQL,
                        {"work_order_operation_id": normalized_operation_id},
                    )
                    execution_state = _execution_state_row(cursor.fetchone())
                    result = {
                        "status": "ok",
                        "work_order_operation_id": normalized_operation_id,
                        "station_code": station_code,
                        "step_code": normalized_step_code,
                        "finished": True,
                        "event_inserted": True,
                        "implicit_started": implicit_started,
                        "event": inserted_event,
                        "execution_state": execution_state,
                        "step": completed_step,
                        "next_step": next_step,
                        "completion_policy_applied": completion_policy_applied,
                        "completion_policy": completion_policy,
                        "execution_transition": (
                            {"from_status": from_status, "to_status": to_status}
                            if completion_policy_applied
                            else None
                        ),
                        "required_steps_completed": required_steps_completed,
                    }
                result["completion_bridge"] = None
                if (
                    bridge_context is not None
                    and execution_state.get("execution_status") == "closed"
                    and execution_state.get("closed_at") is not None
                ):
                    result["completion_bridge"] = (
                        _apply_runtime_completion_bridge_cursor(
                            cursor,
                            work_order_operation_id=normalized_operation_id,
                            locked_context=bridge_context,
                            runtime_state=execution_state,
                        )
                    )
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

    return _json_safe(result)


def finish_execution_step(
    config: AppConfig,
    *,
    work_order_operation_id: str,
    step_code: str,
    event_source: str,
    external_event_id: str | None = None,
    idempotency_key: str | None = None,
    actor_id: str | None = None,
    payload: JsonObject | None = None,
) -> JsonObject:
    try:
        return _finish_execution_step_transaction(
            config,
            work_order_operation_id=work_order_operation_id,
            step_code=step_code,
            event_source=event_source,
            external_event_id=external_event_id,
            idempotency_key=idempotency_key,
            actor_id=actor_id,
            payload=payload,
        )
    except _CompletionBridgeQueueViolation as violation:
        _recover_runtime_completion_bridge_queue_violation(config, violation)
        raise AssertionError("queue recovery must raise")


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

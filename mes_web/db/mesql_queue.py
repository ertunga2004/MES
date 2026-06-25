from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..config import AppConfig
from ..mesql_client import MesqlQueuePlan
from .connection import database_connection


JsonObject = dict[str, Any]
logger = logging.getLogger(__name__)


LOCK_MESQL_STATION_QUEUE_SQL = """
SELECT pg_advisory_xact_lock(hashtext(%(station_code)s))
"""


SELECT_EXISTING_LOCAL_QUEUE_RANK_SQL = """
SELECT queue_rank
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND order_id = %(order_id)s
"""


SELECT_NEXT_LOCAL_QUEUE_RANK_SQL = """
SELECT COALESCE(MAX(queue_rank), 0) + 1
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND status IN ('queued', 'active', 'pending_approval')
"""


UPSERT_MESQL_WORK_ORDER_SQL = """
INSERT INTO mes.work_orders (
    order_id, erp_type, status, product_code, target_quantity,
    started_at, completed_at, source_system, source_file, external_ref,
    payload, metadata, updated_at
) VALUES (
    %(order_id)s, 'MESQL', 'queued', %(product_code)s, %(target_quantity)s,
    NULL, NULL, 'mesql_api', 'station_queue', %(order_id)s,
    %(payload)s, %(metadata)s, now()
)
ON CONFLICT (order_id) DO UPDATE SET
    erp_type = COALESCE(EXCLUDED.erp_type, mes.work_orders.erp_type),
    product_code = COALESCE(EXCLUDED.product_code, mes.work_orders.product_code),
    target_quantity = COALESCE(EXCLUDED.target_quantity, mes.work_orders.target_quantity),
    payload = mes.work_orders.payload || EXCLUDED.payload,
    metadata = mes.work_orders.metadata || EXCLUDED.metadata,
    updated_at = now()
"""


UPSERT_MESQL_STATION_QUEUE_SQL = """
INSERT INTO mes.station_queue (
    station_code, order_id, queue_rank, status, source, payload, metadata, updated_at
) VALUES (
    %(station_code)s, %(order_id)s, %(queue_rank)s, 'queued',
    'mesql_api', %(queue_payload)s, %(queue_metadata)s, now()
)
ON CONFLICT (station_code, order_id) DO UPDATE SET
    source = EXCLUDED.source,
    payload = mes.station_queue.payload || EXCLUDED.payload,
    metadata = mes.station_queue.metadata || EXCLUDED.metadata,
    updated_at = now()
"""


@dataclass(frozen=True, slots=True)
class MesqlQueueWriteResult:
    attempted: bool
    success: bool
    row_count: int
    reason: str
    error_type: str | None = None
    error_message: str | None = None


def _jsonb(value: Any) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        return value
    return Jsonb(value)


def _params(plan: MesqlQueuePlan, *, local_queue_rank: int) -> JsonObject:
    runtime_plan = plan.runtime_plan()
    mesql_meta = {
        "remote_status": plan.remote_order_status,
        "remote_queue_status": plan.remote_queue_status,
        "remote_queue_rank": plan.queue_rank,
        "operation_no": plan.operation_no,
        "work_order_operation_id": plan.work_order_operation_id,
        "operation_id": plan.operation_id,
    }
    payload = dict(runtime_plan)
    payload["mesql"] = dict(mesql_meta)
    metadata = {
        "station_code": plan.station_code,
        "mesql": dict(mesql_meta),
    }
    return {
        "order_id": plan.order_id,
        "product_code": plan.product_code or None,
        "target_quantity": int(plan.planned_quantity) if plan.planned_quantity is not None else None,
        "station_code": plan.station_code,
        "queue_rank": local_queue_rank,
        "payload": _jsonb(payload),
        "metadata": _jsonb(metadata),
        "queue_payload": _jsonb({
            "order_id": plan.order_id,
            "station_code": plan.station_code,
            "product_code": plan.product_code,
            "target_quantity": plan.planned_quantity,
            "mesql": dict(mesql_meta),
        }),
        "queue_metadata": _jsonb(metadata),
    }


def upsert_mesql_queue(config: AppConfig, plans: list[MesqlQueuePlan]) -> MesqlQueueWriteResult:
    if not config.db_enabled:
        return MesqlQueueWriteResult(False, False, 0, "db_disabled")
    current_plan: MesqlQueuePlan | None = None
    try:
        with database_connection(config) as connection:
            if connection is None:
                return MesqlQueueWriteResult(False, False, 0, "db_disabled")
            with connection.transaction():
                with connection.cursor() as cursor:
                    locked_stations: set[str] = set()
                    for plan in plans:
                        current_plan = plan
                        rank_params = {"station_code": plan.station_code, "order_id": plan.order_id}
                        if plan.station_code not in locked_stations:
                            cursor.execute(LOCK_MESQL_STATION_QUEUE_SQL, rank_params)
                            locked_stations.add(plan.station_code)
                        cursor.execute(SELECT_EXISTING_LOCAL_QUEUE_RANK_SQL, rank_params)
                        existing_rank = cursor.fetchone()
                        if existing_rank is None:
                            cursor.execute(SELECT_NEXT_LOCAL_QUEUE_RANK_SQL, rank_params)
                            next_rank = cursor.fetchone()
                            local_queue_rank = int(next_rank[0] if next_rank and next_rank[0] is not None else 1)
                        else:
                            local_queue_rank = int(existing_rank[0])
                        params = _params(plan, local_queue_rank=local_queue_rank)
                        cursor.execute(UPSERT_MESQL_WORK_ORDER_SQL, params)
                        cursor.execute(UPSERT_MESQL_STATION_QUEUE_SQL, params)
    except Exception as exc:
        logger.exception(
            "MESQL protected queue upsert failed station=%s order=%s: %s: %s",
            current_plan.station_code if current_plan else "-",
            current_plan.order_id if current_plan else "-",
            type(exc).__name__,
            exc,
        )
        return MesqlQueueWriteResult(True, False, 0, "db_error", type(exc).__name__, str(exc))
    return MesqlQueueWriteResult(True, True, len(plans), "written")

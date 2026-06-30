from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


JsonObject = dict[str, Any]

STATION_QUEUE_SOURCE = "mes_web_work_order_transition_hook"

STATION_QUEUE_EXISTS_SQL = "SELECT to_regclass('mes.station_queue')"

ACTIVE_QUEUE_STATUSES = {"queued", "active", "pending_approval"}

SELECT_STATION_QUEUE_ROW_SQL = """
SELECT station_queue_pk, queue_rank, status
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND order_id = %(order_id)s
LIMIT 1
"""

SELECT_STATION_QUEUE_ACTIVE_RANK_SQL = """
SELECT order_id
FROM mes.station_queue
WHERE station_code = %(station_code)s
  AND queue_rank = %(queue_rank)s
  AND order_id <> %(order_id)s
  AND status IN ('queued', 'active', 'pending_approval')
LIMIT 1
"""

INSERT_STATION_QUEUE_SQL = """
INSERT INTO mes.station_queue (
    station_code,
    order_id,
    queue_rank,
    status,
    source,
    payload,
    metadata,
    updated_at
) VALUES (
    %(station_code)s,
    %(order_id)s,
    %(queue_rank)s,
    %(status)s,
    %(source)s,
    %(payload)s,
    %(metadata)s,
    now()
)
"""

UPSERT_STATION_QUEUE_SQL = INSERT_STATION_QUEUE_SQL

UPDATE_STATION_QUEUE_SQL = """
UPDATE mes.station_queue
SET
    queue_rank = %(queue_rank)s,
    status = %(status)s,
    source = %(source)s,
    payload = %(payload)s,
    metadata = %(metadata)s,
    updated_at = now()
WHERE station_code = %(station_code)s
  AND order_id = %(order_id)s
"""


@dataclass(frozen=True, slots=True)
class StationQueueRow:
    station_code: str
    order_id: str
    queue_rank: int
    status: str
    source: str
    payload: JsonObject
    metadata: JsonObject


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _metadata(row: JsonObject) -> JsonObject:
    metadata = row.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _payload(row: JsonObject) -> JsonObject:
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else {}


def _station_code(row: JsonObject) -> str:
    metadata = _metadata(row)
    payload = _payload(row)
    return (
        _text(metadata.get("station_code"))
        or _text(payload.get("stationCode"))
        or _text(payload.get("station_code"))
        or "UNKNOWN"
    ).upper()


def station_queue_rows_from_work_order_rows(
    current_rows: list[JsonObject],
    *,
    source: str = STATION_QUEUE_SOURCE,
) -> list[StationQueueRow]:
    buckets: dict[str, list[tuple[int | None, str, JsonObject]]] = {}
    for row in current_rows:
        order_id = _text(row.get("order_id"))
        station_code = _station_code(row)
        if not order_id or not station_code or station_code == "UNKNOWN":
            continue
        metadata = _metadata(row)
        rank = _safe_int(metadata.get("queue_rank"))
        buckets.setdefault(station_code, []).append((rank, order_id, row))

    queue_rows: list[StationQueueRow] = []
    for station_code in sorted(buckets):
        station_rows = sorted(
            buckets[station_code],
            key=lambda item: (item[0] is None, item[0] if item[0] is not None else 999999, item[1]),
        )
        for station_rank, (_rank, order_id, row) in enumerate(station_rows):
            metadata = _metadata(row)
            payload = _payload(row)
            status = _text(row.get("status")).lower() or _text(payload.get("status")).lower() or "queued"
            queue_rows.append(
                StationQueueRow(
                    station_code=station_code,
                    order_id=order_id,
                    queue_rank=station_rank,
                    status=status,
                    source=source,
                    payload={
                        "order_id": order_id,
                        "station_code": station_code,
                        "status": status,
                        "product_code": _text(row.get("product_code")),
                        "target_quantity": row.get("target_quantity"),
                    },
                    metadata={
                        "source": source,
                        "work_order_metadata": copy.deepcopy(metadata),
                    },
                )
            )
    return queue_rows


def station_queue_params(row: StationQueueRow, *, jsonb) -> JsonObject:
    return {
        "station_code": row.station_code,
        "order_id": row.order_id,
        "queue_rank": row.queue_rank,
        "status": row.status,
        "source": row.source,
        "payload": jsonb(row.payload),
        "metadata": jsonb(row.metadata),
    }


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, (list, tuple)) and len(row) > index:
        return row[index]
    return None


def _active_rank_occupied(cursor: Any, params: JsonObject, queue_rank: int) -> bool:
    check_params = dict(params)
    check_params["queue_rank"] = queue_rank
    cursor.execute(SELECT_STATION_QUEUE_ACTIVE_RANK_SQL, check_params)
    return cursor.fetchone() is not None


def write_station_queue_row(cursor: Any, row: StationQueueRow, *, jsonb) -> bool:
    params = station_queue_params(row, jsonb=jsonb)
    incoming_active = row.status in ACTIVE_QUEUE_STATUSES
    cursor.execute(SELECT_STATION_QUEUE_ROW_SQL, params)
    existing = cursor.fetchone()
    if existing:
        existing_rank = _safe_int(_row_value(existing, 1, "queue_rank"))
        next_rank = row.queue_rank
        if incoming_active and _active_rank_occupied(cursor, params, row.queue_rank):
            next_rank = existing_rank if existing_rank is not None else row.queue_rank
        next_status = row.status
        if incoming_active and _active_rank_occupied(cursor, params, next_rank):
            next_status = _text(_row_value(existing, 2, "status")) or row.status
        update_params = dict(params)
        update_params["queue_rank"] = next_rank
        update_params["status"] = next_status
        cursor.execute(UPDATE_STATION_QUEUE_SQL, update_params)
        return True

    if incoming_active and _active_rank_occupied(cursor, params, row.queue_rank):
        return False
    cursor.execute(INSERT_STATION_QUEUE_SQL, params)
    return True

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import AppConfig
from .safe_write import DatabaseWriteResult


JsonObject = dict[str, Any]

OPERATION = "station_events_live_hook"
SOURCE_FILE = "runtime_hook"
HOOK_SOURCE = "f_sta_c_a_station_events"
NATURAL_KEY_POLICY = "unique(source, external_ref)"
ASSEMBLY_STATION_CODE = "ASSEMBLY_01"
PACKAGING_STATION_CODE = "PACKAGING_01"
RUNTIME_SOURCE = "mes_web_runtime"
PACKAGE_FLOW_SOURCE = "mes_web_package_flow"

ALLOWED_EVENT_TYPES = {
    "ENTER",
    "EXIT",
    "COMPLETE",
    "BUFFER_IN",
    "BUFFER_OUT",
    "PACKAGE_START",
    "PACKAGE_FINISH",
    "QUALITY_LOCK",
}


@dataclass(frozen=True, slots=True)
class StationEventRow:
    external_ref: str | None
    status: str
    apply_safe: bool
    reason: str
    event_type: str | None
    station_code: str | None
    work_order_no: str | None
    package_id: str | None
    serial_no: str | None
    event_time: str | None
    source: str
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


def _normalize_event_type(value: Any) -> str | None:
    event_type = _text(value).upper()
    return event_type if event_type in ALLOWED_EVENT_TYPES else None


def _classification(item: JsonObject) -> str:
    return _text(item.get("classification")).upper()


def _order_id(item: JsonObject) -> str | None:
    return _first_text(item, "work_order_id", "order_id", "workOrderId", "orderId", "currentOrderId", "erpOrderId", "sourceOrderId")


def _item_id(item: JsonObject) -> str | None:
    return _first_text(item, "item_id", "itemId", "_extracted_item_id")


def _completed_at(item: JsonObject) -> str | None:
    return _first_text(item, "completed_at", "completedAt")


def _source_item_ref(item: JsonObject) -> str | None:
    order_id = _order_id(item)
    item_id = _item_id(item)
    if order_id and item_id:
        return f"{order_id}_{item_id}"
    return item_id or None


def build_station_event_row(
    *,
    event_type: str,
    station_code: str,
    event_time: str | None,
    source: str,
    external_ref: str | None,
    work_order_no: str | None = None,
    package_id: str | None = None,
    serial_no: str | None = None,
    payload: JsonObject | None = None,
    metadata: JsonObject | None = None,
) -> StationEventRow:
    normalized_event_type = _normalize_event_type(event_type)
    normalized_station_code = _nullable_text(station_code)
    normalized_source = _nullable_text(source)
    normalized_external_ref = _nullable_text(external_ref)
    normalized_event_time = _nullable_text(event_time)

    status = "APPLY_SAFE"
    reason = "apply_safe"
    apply_safe = True

    if normalized_event_type is None:
        status = "SKIPPED_INVALID_EVENT_TYPE"
        reason = "invalid_event_type"
        apply_safe = False
    elif normalized_station_code is None:
        status = "SKIPPED_MISSING_STATION_CODE"
        reason = "missing_station_code"
        apply_safe = False
    elif normalized_event_time is None:
        status = "SKIPPED_MISSING_EVENT_TIME"
        reason = "missing_event_time"
        apply_safe = False
    elif normalized_source is None:
        status = "SKIPPED_MISSING_SOURCE"
        reason = "missing_source"
        apply_safe = False
    elif normalized_external_ref is None:
        status = "SKIPPED_MISSING_EXTERNAL_REF"
        reason = "missing_external_ref"
        apply_safe = False

    row_payload = dict(payload or {})
    row_metadata = {
        "source": HOOK_SOURCE,
        "natural_key_policy": NATURAL_KEY_POLICY,
        "status": status,
        **dict(metadata or {}),
    }

    return StationEventRow(
        external_ref=normalized_external_ref,
        status=status,
        apply_safe=apply_safe,
        reason=reason,
        event_type=normalized_event_type or _text(event_type).upper() or None,
        station_code=normalized_station_code,
        work_order_no=_nullable_text(work_order_no),
        package_id=_nullable_text(package_id),
        serial_no=_nullable_text(serial_no),
        event_time=normalized_event_time,
        source=normalized_source or _text(source),
        source_file=SOURCE_FILE,
        payload=row_payload,
        metadata=row_metadata,
    )


def build_completion_station_events(item: JsonObject) -> list[StationEventRow]:
    if _classification(item) != "GOOD" or bool(item.get("package_flow")):
        return []
    item_ref = _source_item_ref(item)
    order_id = _order_id(item)
    item_id = _item_id(item)
    completed_at = _completed_at(item)
    payload = {"item": dict(item)}
    metadata = {"hook_location": "_complete_runtime_item.after_route", "event_group": "assembly_completion"}
    return [
        build_station_event_row(
            event_type="COMPLETE",
            station_code=ASSEMBLY_STATION_CODE,
            event_time=completed_at,
            source=RUNTIME_SOURCE,
            external_ref=f"{item_ref}:{ASSEMBLY_STATION_CODE}:COMPLETE" if item_ref else None,
            work_order_no=order_id,
            serial_no=item_id,
            payload=payload,
            metadata=metadata,
        ),
        build_station_event_row(
            event_type="EXIT",
            station_code=ASSEMBLY_STATION_CODE,
            event_time=completed_at,
            source=RUNTIME_SOURCE,
            external_ref=f"{item_ref}:{ASSEMBLY_STATION_CODE}:EXIT" if item_ref else None,
            work_order_no=order_id,
            serial_no=item_id,
            payload=payload,
            metadata=metadata,
        ),
    ]


def build_buffer_in_station_events(buffer_row: JsonObject) -> list[StationEventRow]:
    item_id = _first_text(buffer_row, "item_id", "itemId")
    upstream_order_id = _first_text(buffer_row, "upstream_order_id", "upstreamOrderId")
    upstream_external_ref = _first_text(buffer_row, "upstream_external_ref", "upstreamExternalRef")
    completed_at = _first_text(buffer_row, "completed_at", "completedAt")
    item_ref = upstream_external_ref or (f"{upstream_order_id}_{item_id}" if upstream_order_id and item_id else item_id)
    return [
        build_station_event_row(
            event_type="BUFFER_IN",
            station_code=ASSEMBLY_STATION_CODE,
            event_time=completed_at,
            source=PACKAGE_FLOW_SOURCE,
            external_ref=f"{item_ref}:{ASSEMBLY_STATION_CODE}:BUFFER_IN" if item_ref else None,
            work_order_no=upstream_order_id,
            serial_no=item_id,
            payload={"buffer_row": dict(buffer_row)},
            metadata={"hook_location": "_sync_packaging_buffer_for_item", "event_group": "packaging_buffer"},
        )
    ]


def build_package_start_station_events(session: JsonObject, buffer_row: JsonObject | None = None) -> list[StationEventRow]:
    session_id = _first_text(session, "session_id", "sessionId")
    order_id = _first_text(session, "package_order_id", "packageOrderId")
    started_at = _first_text(session, "started_at", "startedAt")
    payload = {"session": dict(session), "buffer_row": dict(buffer_row or {})}
    metadata = {"hook_location": "start_package_flow.after_session_create", "event_group": "package_start"}
    return [
        build_station_event_row(
            event_type="ENTER",
            station_code=PACKAGING_STATION_CODE,
            event_time=started_at,
            source=PACKAGE_FLOW_SOURCE,
            external_ref=f"{session_id}:{PACKAGING_STATION_CODE}:ENTER" if session_id else None,
            work_order_no=order_id,
            serial_no=_first_text(session, "buffer_item_id", "bufferItemId"),
            payload=payload,
            metadata=metadata,
        ),
        build_station_event_row(
            event_type="PACKAGE_START",
            station_code=PACKAGING_STATION_CODE,
            event_time=started_at,
            source=PACKAGE_FLOW_SOURCE,
            external_ref=f"{session_id}:{PACKAGING_STATION_CODE}:PACKAGE_START" if session_id else None,
            work_order_no=order_id,
            serial_no=_first_text(session, "buffer_item_id", "bufferItemId"),
            payload=payload,
            metadata=metadata,
        ),
    ]


def build_package_finish_station_events(
    package_item: JsonObject,
    *,
    session: JsonObject | None = None,
    source_item: JsonObject | None = None,
    buffer_row: JsonObject | None = None,
) -> list[StationEventRow]:
    package_id = _item_id(package_item)
    order_id = _order_id(package_item)
    session_id = _first_text(package_item, "package_session_id", "packageSessionId") or _first_text(session or {}, "session_id", "sessionId")
    finished_at = _completed_at(package_item) or _first_text(session or {}, "finished_at", "finishedAt")
    consumed_item_id = _first_text(package_item, "consumed_item_id", "consumedItemId") or _first_text(buffer_row or {}, "item_id", "itemId")
    payload = {
        "package_item": dict(package_item),
        "session": dict(session or {}),
        "source_item": dict(source_item or {}),
        "buffer_row": dict(buffer_row or {}),
    }
    metadata = {"hook_location": "finish_package_flow.after_package_item_create", "event_group": "package_finish"}
    prefix = f"{session_id}:{package_id}" if session_id and package_id else package_id or session_id
    rows = [
        build_station_event_row(
            event_type="PACKAGE_FINISH",
            station_code=PACKAGING_STATION_CODE,
            event_time=finished_at,
            source=PACKAGE_FLOW_SOURCE,
            external_ref=f"{prefix}:{PACKAGING_STATION_CODE}:PACKAGE_FINISH" if prefix else None,
            work_order_no=order_id,
            package_id=package_id,
            serial_no=package_id,
            payload=payload,
            metadata=metadata,
        ),
        build_station_event_row(
            event_type="COMPLETE",
            station_code=PACKAGING_STATION_CODE,
            event_time=finished_at,
            source=PACKAGE_FLOW_SOURCE,
            external_ref=f"{prefix}:{PACKAGING_STATION_CODE}:COMPLETE" if prefix else None,
            work_order_no=order_id,
            package_id=package_id,
            serial_no=package_id,
            payload=payload,
            metadata=metadata,
        ),
        build_station_event_row(
            event_type="EXIT",
            station_code=PACKAGING_STATION_CODE,
            event_time=finished_at,
            source=PACKAGE_FLOW_SOURCE,
            external_ref=f"{prefix}:{PACKAGING_STATION_CODE}:EXIT" if prefix else None,
            work_order_no=order_id,
            package_id=package_id,
            serial_no=package_id,
            payload=payload,
            metadata=metadata,
        ),
    ]
    quality_locked_at = _first_text(source_item or {}, "quality_locked_at", "qualityLockedAt") or _first_text(package_item, "quality_locked_at", "qualityLockedAt")
    if bool((source_item or {}).get("quality_locked")) or bool(package_item.get("quality_locked")) or quality_locked_at:
        quality_ref = consumed_item_id or _first_text(source_item or {}, "item_id", "itemId") or prefix
        rows.append(
            build_station_event_row(
                event_type="QUALITY_LOCK",
                station_code=ASSEMBLY_STATION_CODE,
                event_time=quality_locked_at or finished_at,
                source=PACKAGE_FLOW_SOURCE,
                external_ref=f"{quality_ref}:QUALITY_LOCK:{quality_locked_at or finished_at}" if quality_ref else None,
                work_order_no=_first_text(package_item, "upstream_order_id", "upstreamOrderId") or order_id,
                package_id=package_id,
                serial_no=consumed_item_id,
                payload=payload,
                metadata={**metadata, "event_group": "quality_lock"},
            )
        )
    return rows


def format_station_event_dry_run(row: StationEventRow) -> str:
    return (
        f"[DRY_RUN:station_events] status={row.status} event_type={row.event_type or ''} "
        f"station_code={row.station_code or ''} work_order_no={row.work_order_no or ''} "
        f"package_id={row.package_id or ''} serial_no={row.serial_no or ''} "
        f"event_time={row.event_time or ''} source={row.source} external_ref={row.external_ref or 'N/A'}"
    )


def mirror_station_events_from_rows(
    config: AppConfig,
    rows: list[StationEventRow],
) -> DatabaseWriteResult:
    if not config.db_enabled:
        return DatabaseWriteResult(False, False, True, "disabled", OPERATION)
    if config.db_hook_station_events_dry_run:
        return DatabaseWriteResult(False, False, True, "dry_run_enabled", OPERATION)
    if not config.db_hook_station_events:
        return DatabaseWriteResult(False, False, True, "live_hook_disabled", OPERATION)
    if not rows:
        return DatabaseWriteResult(False, False, True, "empty", OPERATION)
    return DatabaseWriteResult(False, False, True, "live_hook_not_implemented", OPERATION)
